import json
from pathlib import Path
from app.services.llm_client import GeminiClient
from app.models.script_schema import VideoMetadata, ThumbnailResponse, ThumbnailData

class PackagingService:
    def __init__(self, llm_client: GeminiClient, prompt_dir: Path, output_dir: Path):
        self.llm = llm_client
        self.prompt_dir = prompt_dir
        self.output_dir = output_dir

    def _read_prompt(self, filename: str) -> str:
        path = self.prompt_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"[!] Critical Error: Prompt document '{filename}' is missing.")
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def generate_thumbnail_prompts(self, raw_title: str, script: str) -> ThumbnailData:
        """Generates 5 concepts, saves them to JSON, and returns the highest-scoring one."""
        print(f"\n[Packaging] Generating 5 High-CTR Thumbnail Concepts for: '{raw_title}'")
        
        instructions = self._read_prompt("thumbnail_generator.txt")
        
        prompt = (
            f"Video Title: {raw_title}\n\n"
            f"Video Script: {script}\n\n"
            f"Instructions:\n{instructions}"
        )
        
        try:
            # 1. Force strict JSON schema
            json_string = self.llm.generate_json(prompt, response_model=ThumbnailResponse)
            
            # 2. Convert to Pydantic object AND standard dictionary
            response_data = ThumbnailResponse(**json.loads(json_string))
            thumb_data_dict = json.loads(json_string)
            
            # 3. Save correctly as thumbnail JSON (NOT metadata.json!)
            json_path = self.output_dir / "thumbnail-image-prompts.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(thumb_data_dict, f, indent=4)
                
            print(f"[Packaging] Success! Thumbnail concepts saved to: {json_path.name}")
            
        except Exception as e:
            print(f"\n[!] [Packaging Error] Failed to generate structured thumbnail data: {e}")
            raise e # Fail loudly so the pipeline doesn't continue with broken data
        
        # 4. Find the winner using the Pydantic object
        best_thumbnail = max(response_data.thumbnails, key=lambda t: t.score)
        print(f"[Packaging] Selected best thumbnail concept (Score {best_thumbnail.score}) for Metadata alignment.")
        
        image_prompt_path = self.output_dir / "thumbnail-image-prompts.txt"
        with open(image_prompt_path, "w", encoding="utf-8") as f:
            json.dump(best_thumbnail.image_prompt, f, indent=4)
        print(f"[Packaging] Success! Best Thumbnail saved to: {image_prompt_path.name}")
        
        return best_thumbnail

    def generate_metadata_json(self, script_text: str, transcript_timestamps: str, target_thumbnail: ThumbnailData):
        """Generates SEO metadata physically locked to the chosen thumbnail concept."""
        print("\n[Packaging] Analyzing script and aligning SEO Metadata with chosen Thumbnail...")
        
        instructions = self._read_prompt("metadata_generator.txt")
        
        # Inject the winning thumbnail directly into the Metadata prompt!
        prompt = (
            f"--- CRITICAL ALIGNMENT REQUIREMENT ---\n"
            f"The final video title MUST perfectly complement the following thumbnail concept. "
            f"Do not repeat the thumbnail text in the title. Create a curiosity gap between the two.\n"
            f"Thumbnail Text: \"{target_thumbnail.text}\"\n"
            f"Thumbnail Visual: {target_thumbnail.concept}\n"
            f"----------------------------------------\n\n"
            f"SCRIPT:\n{script_text}\n\n"
            f"TRANSCRIPT TIMESTAMPS:\n{transcript_timestamps}\n\n"
            f"Instructions:\n{instructions}"
        )
        
        try:
            json_string = self.llm.generate_json(prompt, response_model=VideoMetadata)
            metadata_dict = json.loads(json_string)
            
            json_path = self.output_dir / "metadata.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(metadata_dict, f, indent=4)
                
            print(f"[Packaging] Success! High-CTR metadata bundle saved to: {json_path.name}")
            
        except Exception as e:
            print(f"\n[!] [Packaging Error] Failed to generate structured data: {e}")