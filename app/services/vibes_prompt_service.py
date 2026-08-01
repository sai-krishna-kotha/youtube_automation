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
    is_video: bool = Field(description="True if the system flag says MUST BE VIDEO. False if the flag says MUST BE STATIC.")
    motion_prompt: str = Field(description="The cinematic motion prompt. If is_video is False, just write the exact word 'STATIC'.")

class AnimationBatchResponse(BaseModel):
    shots: List[AnimationShot] = Field(description="List of animation shots for the current batch")

# ==========================================
# CONSTANTS & UTILS
# ==========================================
SLEEP_TIME = 10

def _time_str_to_seconds(time_str: str) -> float:
    """Converts a timestamp like '3_51' into 3.51 seconds for precise logic checks."""
    try:
        # Replace the underscore with a decimal point and convert to float
        return float(time_str.replace('_', '.'))
    except Exception:
        return 0.0

class VibesPromptService:
    def __init__(self, llm_client, output_dir: Path, master_prompts_dir: Path):
        self.llm = llm_client
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.master_prompts_dir = master_prompts_dir
        
        # ==========================================
        # 🎛️ HYBRID VIDEO CONTROL PANEL 🎛️
        # ==========================================
        self.RETENTION_SECONDS = 40.0   # Mandatory video window at start of video
        self.MIN_VIDEO_DURATION = 1.5   # Any clip shorter than this is ALWAYS a static image
        self.TARGET_VIDEO_RATIO = 0.35  # Target 35% of total clips as video
        # ==========================================

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
            
        # Parse all static prompts and calculate exact durations
        parsed_static_prompts = []
        with open(static_prompts_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                match = re.match(r'\[([\d_]+)-([\d_]+)\]\s*(.*)', line)
                if match:
                    start_s = _time_str_to_seconds(match.group(1))
                    end_s = _time_str_to_seconds(match.group(2))
                    dur = end_s - start_s
                    
                    parsed_static_prompts.append({
                        "timestamp": f"{match.group(1)}-{match.group(2)}",
                        "prompt": match.group(3),
                        "start_s": start_s,
                        "duration": dur,
                        "is_video": False, # Default
                        "locked": False    # Track if rule is firmly applied
                    })

        # ==========================================
        # HYBRID DISTRIBUTION MATH
        # ==========================================
        total_clips = len(parsed_static_prompts)
        videos_assigned = 0

        # Pass 1: Apply Strict Rules (Short Clip rule vs Retention Rule)
        for scene in parsed_static_prompts:
            if scene["duration"] < self.MIN_VIDEO_DURATION:
                scene["is_video"] = False
                scene["locked"] = True
            elif scene["start_s"] < self.RETENTION_SECONDS:
                scene["is_video"] = True
                scene["locked"] = True
                videos_assigned += 1

        # Pass 2: Fill remaining quota with the LONGEST available clips
        target_video_count = int(total_clips * self.TARGET_VIDEO_RATIO)
        remaining_quota = max(0, target_video_count - videos_assigned)

        if remaining_quota > 0:
            # Grab all unlocked clips, sort by duration descending
            eligible_clips = [s for s in parsed_static_prompts if not s["locked"]]
            eligible_clips.sort(key=lambda x: x["duration"], reverse=True)
            
            for scene in eligible_clips[:remaining_quota]:
                scene["is_video"] = True
                scene["locked"] = True
                videos_assigned += 1

        print(f"[System] Hybrid Math: Total Clips={total_clips} | Target Videos={target_video_count} | Actual Assigned={videos_assigned}")
        # ==========================================

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

        prompt_file = self.master_prompts_dir / "vibes_hybrid_director.md"
        if not prompt_file.exists():
            print(f"[FATAL] Master prompt missing at: {prompt_file}")
            return None
        
        with open(prompt_file, 'r', encoding='utf-8') as pf:
            base_director_prompt = pf.read()

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
                    scene_data = parsed_static_prompts[static_idx]
                    audio_text = batch["segments"][i].get("text", "")
                    
                    if scene_data["is_video"]:
                        rule_flag = "[CRITICAL: MUST BE VIDEO (Write a 15-30 word motion prompt)]"
                    else:
                        rule_flag = "[CRITICAL: MUST BE STATIC (Return exactly the word 'STATIC')]"
                    
                    batch_scenes_context += (
                        f"Scene {i+1} (Timestamp: {scene_data['timestamp']}, Duration: {scene_data['duration']:.2f}s) {rule_flag}:\n"
                        f"  Spoken Audio: \"{audio_text}\"\n"
                        f"  Static Image Look: \"{scene_data['prompt']}\"\n\n"
                    )
                    static_idx += 1
                else:
                    print("[!] Warning: Ran out of static prompts before audio segments finished!")
                    break
            
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
                for i, shot in enumerate(all_shots_so_far):
                    
                    # --- THE IRONCLAD OVERRIDE ---
                    # We strip the LLM's power and strictly enforce our Python math logic!
                    if i < len(parsed_static_prompts):
                        actual_scene = parsed_static_prompts[i]
                        
                        if actual_scene["is_video"]:
                            # If LLM wrote "STATIC" by mistake, give a default prompt to prevent crash
                            final_prompt = shot.motion_prompt if shot.motion_prompt.upper() != "STATIC" else "A very slow push-in camera movement."
                        else:
                            final_prompt = "STATIC"
                            
                        txt_file.write(f"[{actual_scene['timestamp']}] {final_prompt}\n")
                    
            print(f"  -> Incremental save: animation_prompts.txt updated.")

            if idx < total_batches - 1:
                time.sleep(SLEEP_TIME)

        print(f"\n[Success] Finalized hybrid animation prompts saved to: {txt_output_path}")
        return txt_output_path