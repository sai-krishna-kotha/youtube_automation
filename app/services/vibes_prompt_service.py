import json
import time
import re
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List

# ==========================================
# PYDANTIC SCHEMAS FOR STRICT LLM JSON
# ==========================================
class AnimationShot(BaseModel):
    timestamp: str = Field(description="The exact timestamp block provided, e.g., '0_00-4_50'")
    motion_prompt: str = Field(description="The generated cinematic motion prompt (under 30 words)")

class AnimationBatchResponse(BaseModel):
    shots: List[AnimationShot] = Field(description="List of animation shots for the current batch")

# ==========================================
# CONSTANTS
# ==========================================
SLEEP_TIME = 10

class VibesPromptService:
    def __init__(self, llm_client, output_dir: Path):
        self.llm = llm_client
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_animation_prompts(self, transcription_json_path: Path, static_prompts_path: Path):
        print("\n--- VIBES AI: GENERATING BATCH-WISE ANIMATION PROMPTS ---")
        
        # 1. Load the transcription batches
        if not transcription_json_path.exists():
            print("[FATAL] Transcription JSON missing. Cannot run context-aware batches.")
            return None
            
        with open(transcription_json_path, 'r', encoding='utf-8') as f:
            transcription_data = json.load(f)
            
        batches = transcription_data.get("batches", [])
        total_batches = len(batches)
        
        if total_batches == 0:
            print("[FATAL] No batches found in the transcription JSON.")
            return None

        # 2. Load and parse the static image prompts
        if not static_prompts_path.exists():
            print("[FATAL] Static prompts file missing.")
            return None
            
        parsed_static_prompts = []
        with open(static_prompts_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                match = re.match(r'\[([\d_]+-[\d_]+)\]\s*(.*)', line)
                if match:
                    parsed_static_prompts.append({
                        "timestamp": match.group(1),
                        "prompt": match.group(2)
                    })

        # 3. Setup Checkpointing
        checkpoint_path = self.output_dir / "animation_prompts_checkpoint.json"
        completed_batches = {}
        
        if checkpoint_path.exists():
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                completed_batches = json.load(f)
            
        if len(completed_batches) == total_batches and total_batches > 0:
            print(f"[Checkpoint] All {total_batches} animation batches are already completed.")
            return self.output_dir / "animation_prompts.txt"
            
        if completed_batches:
            print(f"[Checkpoint] Found {len(completed_batches)} previously completed animation batches. Resuming...")

        # 4. Process Batch by Batch
        static_idx = 0  # To track our place in the static prompts list
        
        for idx, batch in enumerate(batches):
            batch_id_str = str(batch.get('batch_id', idx))
            expected_shot_count = len(batch.get("segments", []))
            
            # Fast-forward our static_idx index if we are skipping this batch
            if batch_id_str in completed_batches:
                print(f"\n[Checkpoint] Batch {batch_id_str} already processed. Skipping API call.")
                static_idx += expected_shot_count
                continue 
                
            print(f"\nProcessing Animation Batch {batch_id_str} of {total_batches} (Expecting {expected_shot_count} shots)...")
            
            # Map the exact static images to this batch's audio segments
            batch_scenes_context = ""
            for i in range(expected_shot_count):
                if static_idx < len(parsed_static_prompts):
                    audio_text = batch["segments"][i].get("text", "")
                    img_time = parsed_static_prompts[static_idx]["timestamp"]
                    img_prompt = parsed_static_prompts[static_idx]["prompt"]
                    
                    batch_scenes_context += (
                        f"Scene {i+1} (Timestamp: {img_time}):\n"
                        f"  Spoken Audio: \"{audio_text}\"\n"
                        f"  Static Image Look: \"{img_prompt}\"\n\n"
                    )
                    static_idx += 1
                else:
                    print("[!] Warning: Ran out of static prompts before audio segments finished!")
                    break
            
            # The Master Prompt for the AI
            user_prompt = (
                "You are a cinematic AI video prompt engineer.\n"
                "I will provide a batch of scenes. Each scene has a STATIC IMAGE LOOK, SPOKEN AUDIO, and a specific TIMESTAMP duration.\n"
                "Your job is to write a highly effective animation prompt to make the static image move.\n"
                "CRITICAL: The motion MUST match the tone, pacing, and context of the spoken audio.\n"
                "TIMING & TRIMMING RULES: The described motion and emotion MUST begin immediately at the start of the clip and fit entirely within the specific duration. "
                "These clips may be trimmed down by a video engine, so the action/emotion MUST be instantly visible from frame one.\n"
                "SAFETY & MODERATION (CRITICAL): Avoid words depicting violence, extreme distress, or aggression. Use safe, neutral equivalents (e.g., 'speaks passionately' instead of 'shouts fiercely'). Keep it PG-rated.\n"
                "STYLE (META AI FRIENDLY): Keep the vocabulary very simple, direct, and Meta AI-friendly. Do not use complex narrative sentences. Use universally understood cinematography and motion keywords separated by commas (e.g., 'slow pan right, soft warm lighting, gentle hair movement in breeze, subtle smile').\n"
                "LENGTH: Keep each motion prompt under 100 words. Focus strictly on CAMERA MOVEMENT, LIGHTING, and SUBTLE CHARACTER MOTION. Do not describe the static background.\n\n"
                "--- CURRENT BATCH SCENES ---\n"
                f"{batch_scenes_context}"
            )

            # --- BULLETPROOF RETRY LOOP ---
            while True:
                print(f"Sending Batch {batch_id_str} to LLM API (Expecting exactly {expected_shot_count} shots)...")
                raw_response = self.llm.generate_json(user_prompt, response_model=AnimationBatchResponse)
                
                try:
                    validated_batch = AnimationBatchResponse(**json.loads(raw_response))
                    actual_shot_count = len(validated_batch.shots)
                    
                    # STRICT VALIDATION: Did the LLM give us a prompt for every single segment?
                    if actual_shot_count == expected_shot_count:
                        print(f"  [✓] Success! Exact match: {actual_shot_count}/{expected_shot_count} shots generated.")
                        break # Break out of the while loop, we got perfect data!
                    else:
                        print(f"  [!] Mismatch: LLM returned {actual_shot_count} shots, but we demand {expected_shot_count}.")
                        print(f"  [!] Recalling the batch in {SLEEP_TIME} seconds...")
                        time.sleep(SLEEP_TIME)
                        
                except Exception as e:
                    print(f"  [ERROR] Failed parsing responses for Batch {batch_id_str}: {e}")
                    print(f"  [!] LLM hallucinated JSON structure. Recalling the batch in {SLEEP_TIME} seconds...")
                    time.sleep(SLEEP_TIME)
            # ------------------------------

            # Save the perfectly validated batch to the checkpoint JSON
            completed_batches[batch_id_str] = [shot.model_dump() for shot in validated_batch.shots]
            with open(checkpoint_path, 'w', encoding='utf-8') as f:
                json.dump(completed_batches, f, indent=4)

            # --- INCREMENTAL SAVE FOR THE TEXT FILE (Mirroring image_prompt_service) ---
            all_shots_so_far = []
            
            # Extract them in the exact order of the sequential batches
            for batch_ordered in batches:
                b_id = str(batch_ordered.get('batch_id'))
                if b_id in completed_batches:
                    shots = completed_batches[b_id]
                    for s in shots:
                        all_shots_so_far.append(AnimationShot(**s))
                        
            txt_output_path = self.output_dir / "animation_prompts.txt"
            
            with open(txt_output_path, 'w', encoding='utf-8') as txt_file:
                for shot in all_shots_so_far:
                    txt_file.write(f"[{shot.timestamp}] {shot.motion_prompt}\n")
                    
            print(f"  -> Incremental save: animation_prompts.txt updated.")

            # Sleep to protect API limits
            if idx < total_batches - 1:
                print(f"Waiting {SLEEP_TIME} seconds to protect API rate limits before next batch...")
                time.sleep(SLEEP_TIME)

        print(f"\n[Success] Finalized animation prompts saved to: {txt_output_path}")
        return txt_output_path