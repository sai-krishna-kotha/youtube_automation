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
    is_video: bool = Field(description="True if this scene requires motion (ALWAYS True for first 60s). False if a static image is enough.")
    motion_prompt: str = Field(description="The cinematic motion prompt. If is_video is False, just write the exact word 'STATIC'.")

class AnimationBatchResponse(BaseModel):
    shots: List[AnimationShot] = Field(description="List of animation shots for the current batch")

# ==========================================
# CONSTANTS & UTILS
# ==========================================
SLEEP_TIME = 10

def _time_str_to_seconds(time_str: str) -> int:
    """Converts a timestamp like '1_15' into 75 seconds for logic checks."""
    try:
        parts = time_str.split('_')
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        pass
    return 0

class VibesPromptService:
    def __init__(self, llm_client, output_dir: Path, master_prompts_dir: Path):
        self.llm = llm_client
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.master_prompts_dir = master_prompts_dir

    def generate_animation_prompts(self, transcription_json_path: Path, static_prompts_path: Path):
        print("\n--- VIBES AI: GENERATING BATCH-WISE HYBRID PROMPTS ---")
        
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

        # --- LOAD MASTER PROMPT FILE ---
        prompt_file = self.master_prompts_dir / "vibes_hybrid_director.md"
        if not prompt_file.exists():
            print(f"[FATAL] Master prompt missing at: {prompt_file}")
            return None
        
        with open(prompt_file, 'r', encoding='utf-8') as pf:
            base_director_prompt = pf.read()
        # -------------------------------

        static_idx = 0  
        
        for idx, batch in enumerate(batches):
            batch_id_str = str(batch.get('batch_id', idx))
            expected_shot_count = len(batch.get("segments", []))
            
            if batch_id_str in completed_batches:
                print(f"\n[Checkpoint] Batch {batch_id_str} already processed. Skipping API call.")
                static_idx += expected_shot_count
                continue 
                
            print(f"\nProcessing Animation Batch {batch_id_str} of {total_batches} (Expecting {expected_shot_count} shots)...")
            
            batch_scenes_context = ""
            for i in range(expected_shot_count):
                if static_idx < len(parsed_static_prompts):
                    audio_text = batch["segments"][i].get("text", "")
                    img_time = parsed_static_prompts[static_idx]["timestamp"]
                    img_prompt = parsed_static_prompts[static_idx]["prompt"]
                    
                    start_time_str = img_time.split('-')[0]
                    start_sec = _time_str_to_seconds(start_time_str)
                    
                    if start_sec < 60:
                        rule_flag = "[CRITICAL: MUST BE VIDEO (First 60s Retention)]"
                    else:
                        rule_flag = "[OPTIONAL: AI DECIDES - Video OR Static Image]"
                    
                    batch_scenes_context += (
                        f"Scene {i+1} (Timestamp: {img_time}) {rule_flag}:\n"
                        f"  Spoken Audio: \"{audio_text}\"\n"
                        f"  Static Image Look: \"{img_prompt}\"\n\n"
                    )
                    static_idx += 1
                else:
                    print("[!] Warning: Ran out of static prompts before audio segments finished!")
                    break
            
            # --- INJECT CONTEXT INTO THE MARKDOWN PROMPT ---
            user_prompt = base_director_prompt.replace("{batch_scenes_context}", batch_scenes_context)

            while True:
                print(f"Sending Batch {batch_id_str} to LLM API (Expecting exactly {expected_shot_count} shots)...")
                raw_response = self.llm.generate_json(user_prompt, response_model=AnimationBatchResponse)
                
                try:
                    validated_batch = AnimationBatchResponse(**json.loads(raw_response))
                    actual_shot_count = len(validated_batch.shots)
                    
                    if actual_shot_count == expected_shot_count:
                        print(f"  [✓] Success! Exact match: {actual_shot_count}/{expected_shot_count} shots evaluated.")
                        break 
                    else:
                        print(f"  [!] Mismatch: LLM returned {actual_shot_count} shots, but we demand {expected_shot_count}.")
                        time.sleep(SLEEP_TIME)
                        
                except Exception as e:
                    print(f"  [ERROR] Failed parsing responses for Batch {batch_id_str}: {e}")
                    time.sleep(SLEEP_TIME)

            completed_batches[batch_id_str] = [shot.model_dump() for shot in validated_batch.shots]
            with open(checkpoint_path, 'w', encoding='utf-8') as f:
                json.dump(completed_batches, f, indent=4)

            all_shots_so_far = []
            for batch_ordered in batches:
                b_id = str(batch_ordered.get('batch_id'))
                if b_id in completed_batches:
                    shots = completed_batches[b_id]
                    for s in shots:
                        all_shots_so_far.append(AnimationShot(**s))
                        
            txt_output_path = self.output_dir / "animation_prompts.txt"
            
            with open(txt_output_path, 'w', encoding='utf-8') as txt_file:
                for shot in all_shots_so_far:
                    # Write exact file format for the Automator to parse
                    final_prompt = shot.motion_prompt if shot.is_video else "STATIC"
                    txt_file.write(f"[{shot.timestamp}] {final_prompt}\n")
                    
            print(f"  -> Incremental save: animation_prompts.txt updated.")

            if idx < total_batches - 1:
                time.sleep(SLEEP_TIME)

        print(f"\n[Success] Finalized hybrid animation prompts saved to: {txt_output_path}")
        return txt_output_path