import json
import time
from pathlib import Path
from app.models.script_schema import BatchPromptResponse, SingleShotPrompt

SLEEP_TIME = 20

class ImagePromptService:
    def __init__(self, llm_client, prompt_dir: Path, output_dir: Path = None):
        self.llm = llm_client
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        self.prompt_dir = prompt_dir
        
        self.output_dir = output_dir or (self.base_dir / "assets" / "outputs")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _read_prompt_instructions(self) -> str:
        with open(self.prompt_dir / "image_prompts_instructions.txt", 'r', encoding='utf-8') as f:
            return f.read()

    def generate_all_prompts(self, transcription_json_path: Path, raw_title: str, script_text: str):
        print("\n--- GENERATING HIERARCHICAL IMAGE PROMPTS ---")
        
        with open(transcription_json_path, 'r', encoding='utf-8') as f:
            transcription_data = json.load(f)
            
        instructions = self._read_prompt_instructions()
        
        batches = transcription_data.get("batches", [])
        total_batches = len(batches)
        
        checkpoint_path = self.output_dir / "prompts_checkpoint.json"
        completed_batches = {}
        
        if checkpoint_path.exists():
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                completed_batches = json.load(f)
            
        # If all batches are done, exit early!
        if len(completed_batches) == total_batches and total_batches > 0:
            print(f"[Checkpoint] All {total_batches} image batches are already completed.")
            return self.output_dir / "time_stamped_prompts.txt"
            
        if completed_batches:
            print(f"[Checkpoint] Found {len(completed_batches)} previously completed image batches. Resuming...")

        for idx, batch in enumerate(batches):
            batch_id_str = str(batch['batch_id'])
            
            if batch_id_str in completed_batches:
                print(f"\n[Checkpoint] Batch {batch['batch_id']} already processed. Skipping API call.")
                continue 
                
            print(f"\nProcessing Audio Batch {batch['batch_id']} of {total_batches} ({batch['duration']}s)...")
            
            batch_segments_context = json.dumps(batch["segments"], indent=2)
            user_prompt = (
                f"Video Raw Title: {raw_title}\n\n"
                f"Full Narration Script:\n{script_text}\n\n"
                f"--- CURRENT BATCH SEGMENTS TO PROCESS ---\n"
                f"{batch_segments_context}\n\n"
                f"--- INSTRUCTIONS ---\n"
                f"{instructions}"
            )

            print(f"Sending Batch {batch['batch_id']} to Gemini API...")
            raw_response = self.llm.generate_json(user_prompt, response_model=BatchPromptResponse)
            
            try:
                validated_batch = BatchPromptResponse(**json.loads(raw_response))
                print(f"Successfully processed {len(validated_batch.shots)} shots for Batch {batch['batch_id']}.")
                
                # 1. Update JSON Checkpoint
                completed_batches[batch_id_str] = [shot.model_dump() for shot in validated_batch.shots]
                with open(checkpoint_path, 'w', encoding='utf-8') as f:
                    json.dump(completed_batches, f, indent=4)
                    
                # 2. INCREMENTAL TXT SAVE
                # Rebuild all completed shots so far and sort them chronologically
                all_shots_so_far = []
                for b_id, shots in completed_batches.items():
                    for s in shots:
                        all_shots_so_far.append(SingleShotPrompt(**s))
                        
                all_shots_so_far.sort(key=lambda x: x.start_time)
                
                txt_output_path = self.output_dir / "time_stamped_prompts.txt"
                with open(txt_output_path, 'w', encoding='utf-8') as txt_file:
                    for shot in all_shots_so_far:
                        txt_file.write(f"[{shot.start_time}] {shot.image_prompt}\n")
                        
                print(f" -> Incremental save: time_stamped_prompts.txt updated.")
                    
            except Exception as e:
                print(f"[ERROR] Failed parsing responses for Batch {batch['batch_id']}: {e}")
                print("[!] Halting pipeline. Fix the issue and re-run to resume.")
                raise e 

            if idx < total_batches - 1:
                print(f"Waiting {SLEEP_TIME} seconds to protect API rate limits...")
                time.sleep(SLEEP_TIME)

        print(f"\n[Success] Finalized production-ready layout saved to: {self.output_dir / 'time_stamped_prompts.txt'}")
        return self.output_dir / "time_stamped_prompts.txt"