import json
import time
import wave
import yaml
from pathlib import Path
from typing import List, Dict, Any

from app.models.script_schema import BatchPromptResponse, SingleShotPrompt

SLEEP_TIME = 10

class ImagePromptService:
    def __init__(self, llm_client, master_prompts_dir: Path, channel_dir: Path, output_dir: Path = None):
        self.llm = llm_client
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        self.master_prompts_dir = master_prompts_dir
        self.channel_dir = channel_dir
        
        self.output_dir = output_dir or (self.base_dir / "assets" / "outputs")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_channel_context(self) -> str:
        """Injects Channel Identity to ensure visual style matching."""
        l1_path = self.channel_dir / "layer1.yaml"
        l2_path = self.channel_dir / "layer2.yaml"
        l3_path = self.channel_dir / "layer3.yaml"
        
        context = "--- CHANNEL IDENTITY (LAYER 1) ---\n"
        if l1_path.exists():
            with open(l1_path, 'r', encoding='utf-8') as f:
                context += f.read().strip() + "\n"
                print("Layer 1 Loaded successfully")

        context += "\n--- CONTENT STRATEGY (LAYER 2) ---\n"
        if l2_path.exists():
            with open(l2_path, 'r', encoding='utf-8') as f:
                context += f.read().strip() + "\n\n"
                print("Layer 2 Loaded successfully")
                
        context += "\n--- VISUAL STRATEGY (LAYER 3) ---\n"
        if l3_path.exists():
            with open(l3_path, 'r', encoding='utf-8') as f:
                context += f.read().strip() + "\n\n"
                print("Layer 3 Loaded successfully")
        return context

    def _read_master_prompt(self) -> str:
        path = self.master_prompts_dir / "image_prompt_generator.md"
        if not path.exists():
            raise FileNotFoundError(f"[!] Master Prompt missing: {path}")
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def generate_all_prompts(self, transcription_json_path: Path, request_yaml: str, script_text: str, audio_path: Path = None):
        print("\n--- GENERATING SINGLE-TRACK IMAGE PROMPTS (V3 ARCHITECTURE) ---")
        
        with open(transcription_json_path, 'r', encoding='utf-8') as f:
            transcription_data = json.load(f)
            
        channel_context = self._get_channel_context()
        instructions = self._read_master_prompt()
        
        batches = transcription_data.get("batches", [])
        total_batches = len(batches)
        
        try:
            req_data = yaml.safe_load(request_yaml) or {}
            length_of_image_prompt = req_data.get('output', {}).get('image_prompt_length', {}).get('target_characters', 700)
        except Exception:
            length_of_image_prompt = 700
            
        checkpoint_path = self.output_dir / "prompts_checkpoint.json"
        completed_batches = {}
        
        if checkpoint_path.exists():
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                completed_batches = json.load(f)
            
        if len(completed_batches) == total_batches and total_batches > 0:
            print(f"[Checkpoint] All {total_batches} image batches are already completed.")
            return self._compile_final_prompts(transcription_data, completed_batches, audio_path)
            
        if completed_batches:
            print(f"[Checkpoint] Found {len(completed_batches)} previously completed image batches. Resuming...")

        for idx, batch in enumerate(batches):
            batch_id_str = str(batch['batch_id'])
            
            if batch_id_str in completed_batches:
                print(f"\n[Checkpoint] Batch {batch['batch_id']} already processed. Skipping API call.")
                continue 
                
            segments = batch.get("segments", [])
            expected_shot_count = len(segments)
            
            print(f"\nProcessing Audio Batch {batch['batch_id']} of {total_batches} ({batch.get('duration', 0)}s, {expected_shot_count} segments)...")
            
            segments_json = json.dumps(segments, indent=2)
            
            user_prompt = (
                f"{channel_context}\n"
                f"--- SPECIFIC VIDEO REQUEST ---\n"
                f"{request_yaml}\n\n"
                f"Full Narration Script:\n{script_text}\n\n"
                f"--- CURRENT SINGLE-TRACK SEGMENTS TO PROCESS ---\n"
                f"{segments_json}\n\n"
                f"--- MASTER INSTRUCTIONS ---\n"
                f"{instructions}\n\n"
                f"--- TARGET IMAGE PROMPT CHARACTER LENGTH ---\n"
                f"{length_of_image_prompt}"
            )

            # --- BULLETPROOF RETRY LOOP ---
            while True:
                print(f"Sending Batch {batch['batch_id']} to Gemini API (Expecting exactly {expected_shot_count} shots)...")
                raw_response = self.llm.generate_json(user_prompt, response_model=BatchPromptResponse)
                
                try:
                    validated_batch = BatchPromptResponse(**json.loads(raw_response))
                    actual_shot_count = len(validated_batch.shots)
                    
                    if actual_shot_count == expected_shot_count:
                        print(f"  [✓] Success! Perfect match: {actual_shot_count}/{expected_shot_count} single-track prompts generated.")
                        break 
                    else:
                        print(f"  [!] Mismatch: LLM returned {actual_shot_count} shots, expected {expected_shot_count}.")
                        print(f"  [!] Retrying batch in {SLEEP_TIME} seconds...")
                        time.sleep(SLEEP_TIME)
                        
                except Exception as e:
                    print(f"  [ERROR] Failed parsing response for Batch {batch['batch_id']}: {e}")
                    print(f"  [!] Retrying batch in {SLEEP_TIME} seconds...")
                    time.sleep(SLEEP_TIME) 

            completed_batches[batch_id_str] = [shot.model_dump() for shot in validated_batch.shots]
            with open(checkpoint_path, 'w', encoding='utf-8') as f:
                json.dump(completed_batches, f, indent=4)
                
            self._compile_final_prompts(transcription_data, completed_batches, audio_path)

            if idx < total_batches - 1:
                print(f"Waiting {SLEEP_TIME} seconds to protect API rate limits before next batch...")
                time.sleep(SLEEP_TIME)

        print(f"\n[Success] Finalized production-ready layout saved to: {self.output_dir / 'time_stamped_prompts.txt'}")
        return self.output_dir / "time_stamped_prompts.txt"

    def _compile_final_prompts(self, transcription_data: dict, completed_batches: dict, audio_path: Path = None):
        """
        Maps raw SingleShotPrompts returned by LLM to single-track segment timestamps,
        calculates lookahead end durations, and writes clean [BASE] lines to time_stamped_prompts.txt.
        """
        all_segments = []
        for batch in transcription_data.get("batches", []):
            if str(batch['batch_id']) in completed_batches:
                all_segments.extend(batch.get("segments", []))
                
        all_segments.sort(key=lambda x: x["start"])
        
        all_shots_so_far = []
        for b_id, shots in completed_batches.items():
            for s in shots:
                all_shots_so_far.append(SingleShotPrompt(**s))
        
        all_shots_so_far.sort(key=lambda x: x.start_time if hasattr(x, 'start_time') else 0.0)

        # Enforce exact 0.0s start for the very first clip
        if all_segments:
            all_segments[0]["start"] = 0.0

        # Retrieve exact total audio duration
        final_end_time = 0.0
        if audio_path and audio_path.exists():
            try:
                with wave.open(str(audio_path), 'rb') as w:
                    frames = w.getnframes()
                    rate = w.getframerate()
                    final_end_time = frames / float(rate)
            except Exception:
                final_end_time = transcription_data.get("batches", [])[-1].get('end_time', 0.0) if transcription_data.get("batches") else 0.0
        else:
            final_end_time = transcription_data.get("batches", [])[-1].get('end_time', 0.0) if transcription_data.get("batches") else 0.0

        txt_output_path = self.output_dir / "time_stamped_prompts.txt"
        
        with open(txt_output_path, 'w', encoding='utf-8') as txt_file:
            for i, seg in enumerate(all_segments):
                start = seg["start"]
                next_start = all_segments[i + 1]["start"] if i < len(all_segments) - 1 else final_end_time
                
                safe_start = str(round(start, 3)).replace('.', '_')
                safe_end = str(round(next_start, 3)).replace('.', '_')
                
                # Fetch corresponding shot generated by Gemini
                shot_prompt = all_shots_so_far[i].image_prompt if i < len(all_shots_so_far) else ""
                
                txt_file.write(f"[BASE] [{safe_start}-{safe_end}] {shot_prompt}\n")

        print(" -> Incremental save: time_stamped_prompts.txt updated.")
        return txt_output_path