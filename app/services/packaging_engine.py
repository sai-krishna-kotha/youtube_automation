import json
from pathlib import Path
from app.services.llm_client import GeminiClient
from app.models.script_schema import VideoMetadata, ThumbnailResponse, ThumbnailData
from ddgs import DDGS

class PackagingService:
    def __init__(self, llm_client: GeminiClient, master_prompts_dir: Path, channel_dir: Path, output_dir: Path):
        self.llm = llm_client
        self.master_prompts_dir = master_prompts_dir
        self.channel_dir = channel_dir
        self.output_dir = output_dir

    def _get_channel_context(self) -> str:
        """Injects Channel Identity so metadata matches the brand voice."""
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

    def _read_master_prompt(self, filename: str) -> str:
        path = self.master_prompts_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"[!] Critical Error: Master Prompt document '{filename}' is missing.")
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def generate_thumbnail_prompts(self, request_yaml: str, script: str) -> ThumbnailData:
        """Generates 5 concepts, saves them to JSON, and returns the highest-scoring one."""
        print(f"\n[Packaging] Generating 5 High-CTR Thumbnail Concepts...")
        
        channel_context = self._get_channel_context()
        instructions = self._read_master_prompt("thumbnail_generator.md")
        try:
            import yaml
            req_data = yaml.safe_load(request_yaml) or {}
            no_of_thumbnails = req_data.get('output', {}).get('thumbnail_count', 5)
        except:
            no_of_thumbnails = 5
        prompt = (
            f"{channel_context}"
            f"--- SPECIFIC VIDEO REQUEST (READ CAREFULLY) ---\n"
            f"{request_yaml}\n\n"
            f"--- FULL VIDEO SCRIPT ---\n{script}\n\n"
            f"--- MASTER INSTRUCTIONS ---\n{instructions}"
            f"---Give me {no_of_thumbnails} thumbnails in the given response model"
        )
        
        try:
            # 1. Force strict JSON schema
            json_string = self.llm.generate_json(prompt, response_model=ThumbnailResponse)
            
            # 2. Convert to Pydantic object AND standard dictionary
            response_data = ThumbnailResponse(**json.loads(json_string))
            thumb_data_dict = json.loads(json_string)
            
            # 3. Save correctly as thumbnail JSON
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
        
        best_thumb_path = self.output_dir / "best_thumbnail.txt"
        with open(best_thumb_path, "w", encoding="utf-8") as f:
            f.write(f"SCORE: {best_thumbnail.score}/10\n")
            f.write("="*40 + "\n\n")
            f.write(f"THUMBNAIL TEXT:\n{best_thumbnail.text}\n\n")
            f.write(f"VISUAL CONCEPT:\n{best_thumbnail.concept}\n\n")
            f.write(f"IMAGE PROMPT:\n{best_thumbnail.image_prompt}\n")
            
        print(f"[Packaging] Success! Best Thumbnail readable data saved to: {best_thumb_path.name}")
        
        
        return best_thumbnail
    
    def _auto_fetch_research_links(self, script_text: str) -> str:
        """Automatically searches the web for real links based on the script."""
        print("[Research] Automatically hunting for real source links...")
        
        # 1. Ask the LLM to extract the 2 best search queries from the script
        query_prompt = f"Extract exactly two highly specific scientific or historical Google search queries to find real research for this script. Return ONLY a comma-separated list of the two queries.\nSCRIPT: {script_text[:1000]}"
        search_queries_str = self.llm.generate_text(query_prompt)
        queries = [q.strip() for q in search_queries_str.split(',')]
        
        real_links = []
        
        # 2. Use a Search API to grab the top result for each query
        with DDGS() as ddgs:
            for query in queries:
                try:
                    # Grab the top 1 result for the query
                    results = list(ddgs.text(query, max_results=1))
                    if results:
                        title = results[0]['title']
                        url = results[0]['href']
                        real_links.append(f"- {title}: {url}")
                except Exception as e:
                    print(f"[Research] Search failed for '{query}': {e}")
                    
        # 3. Format it as a string to inject into the metadata prompt
        if real_links:
            formatted_sources = "\n[SOURCES TO CITE]\n" + "\n".join(real_links)
            return formatted_sources
        return ""
    
    def generate_metadata_json(self, request_yaml: str, script_text: str, transcript_timestamps: str, target_thumbnail: ThumbnailData):
        """Generates SEO metadata physically locked to the chosen thumbnail concept."""
        print("\n[Packaging] Analyzing script and aligning SEO Metadata with chosen Thumbnail...")
        auto_links = self._auto_fetch_research_links(script_text)
        full_payload = script_text + "\n\n" + auto_links
        channel_context = self._get_channel_context()
        instructions = self._read_master_prompt("metadata_generator.md")
        print(f"\n\n\n\nFull payload:\n\n{full_payload}\n\n\n\n")
        # Inject the winning thumbnail directly into the Metadata prompt!
        prompt = (
            f"{channel_context}"
            f"--- SPECIFIC VIDEO REQUEST ---\n"
            f"{request_yaml}\n\n"
            f"--- CRITICAL ALIGNMENT REQUIREMENT ---\n"
            f"The final video title MUST perfectly complement the following thumbnail concept. "
            f"Do not repeat the thumbnail text in the title. Create a curiosity gap between the two.\n"
            f"Thumbnail Text: \"{target_thumbnail.text}\"\n"
            f"Thumbnail Visual: {target_thumbnail.concept}\n"
            f"----------------------------------------\n\n"
            f"--- SCRIPT + Links ---\n{full_payload}\n\n"
            f"--- TRANSCRIPT TIMESTAMPS ---\n{transcript_timestamps}\n\n"
            f"--- MASTER INSTRUCTIONS ---\n{instructions}"
        )
        
        try:
            json_string = self.llm.generate_json(prompt, response_model=VideoMetadata)
            metadata_dict = json.loads(json_string)
            
            json_path = self.output_dir / "metadata.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(metadata_dict, f, indent=4)
            
            
            title = metadata_dict.get("title", "No Title Generated")
            description = metadata_dict.get("description", "No Description Generated")
            tags = metadata_dict.get("tags", [])
            
            # 3. Clean up formatting (forces double-escaped \n into actual line breaks)
            description_clean = description.replace('\\n', '\n')
            tags_clean = ", ".join(tags) if isinstance(tags, list) else str(tags)
            
            # 4. Save to a highly structured metadata.txt (For easy copy-pasting)
            txt_path = self.output_dir / "metadata.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write("=========================================\n")
                f.write("📋 YOUTUBE UPLOAD METADATA PACKAGE 📋\n")
                f.write("=========================================\n\n")
                
                f.write("--- [COPY TITLE BELOW] ---\n")
                f.write(f"{title}\n\n")
                
                f.write("--- [COPY DESCRIPTION BELOW] ---\n")
                f.write(f"{description_clean}\n\n")
                
                f.write("--- [COPY TAGS BELOW] ---\n")
                f.write(f"{tags_clean}\n")
                
            print(f"[Packaging] Success! High-CTR metadata bundle saved to: {json_path.name}")
            print(f"[Packaging] Success! Copy-paste ready format saved to: {txt_path.name}")
            
        except Exception as e:
            print(f"\n[!] [Packaging Error] Failed to generate structured data: {e}")