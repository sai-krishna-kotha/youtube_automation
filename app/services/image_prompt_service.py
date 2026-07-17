import json
import time
from pathlib import Path
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

    def generate_all_prompts(self, transcription_json_path: Path, request_yaml: str, script_text: str):
        print("\n--- GENERATING HIERARCHICAL IMAGE PROMPTS ---")
        
        with open(transcription_json_path, 'r', encoding='utf-8') as f:
            transcription_data = json.load(f)
            
        channel_context = self._get_channel_context()
        instructions = self._read_master_prompt()
        
        batches = transcription_data.get("batches", [])
        total_batches = len(batches)
        try:
            import yaml
            req_data = yaml.safe_load(request_yaml) or {}
            length_of_image_prompt = req_data.get('output', {}).get('image_prompt_length', {}).get('target_characters', 700)
        except :
            length_of_image_prompt = 700
        checkpoint_path = self.output_dir / "prompts_checkpoint.json"
        completed_batches = {}
        
        if checkpoint_path.exists():
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                completed_batches = json.load(f)
            
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
            
            # Replaced raw_title with the entire request_yaml!
            user_prompt = (
                f"{channel_context}"
                f"--- SPECIFIC VIDEO REQUEST (READ CAREFULLY) ---\n"
                f"{request_yaml}\n\n"
                f"Full Narration Script:\n{script_text}\n\n"
                f"--- CURRENT BATCH SEGMENTS TO PROCESS ---\n"
                f"{batch_segments_context}\n\n"
                f"--- MASTER INSTRUCTIONS ---\n"
                f"{instructions}"
                f"--- Length of the image prompts with prefix, middle, suffix parts---\n"
                f"{length_of_image_prompt}"
            )

            print(f"Sending Batch {batch['batch_id']} to Gemini API...")
            raw_response = self.llm.generate_json(user_prompt, response_model=BatchPromptResponse)
            
            try:
                validated_batch = BatchPromptResponse(**json.loads(raw_response))
                print(f"Successfully processed {len(validated_batch.shots)} shots for Batch {batch['batch_id']}.")
                
                completed_batches[batch_id_str] = [shot.model_dump() for shot in validated_batch.shots]
                with open(checkpoint_path, 'w', encoding='utf-8') as f:
                    json.dump(completed_batches, f, indent=4)
                    
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