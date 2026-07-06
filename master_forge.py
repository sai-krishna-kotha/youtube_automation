import sys
import re
import os
import json
import textwrap
from pathlib import Path
from dotenv import load_dotenv
import time
SLEEP_TIME = 5
# ==========================================
# THE SILENCER BLOCK
# ==========================================
import warnings
import logging
warnings.filterwarnings("ignore")
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
logging.getLogger("whisperx").setLevel(logging.ERROR)
logging.getLogger("pyannote").setLevel(logging.ERROR)
logging.getLogger("lightning").setLevel(logging.ERROR)
logging.getLogger("pytorch_lightning").setLevel(logging.ERROR)
# ==========================================

# Import all your custom services
from app.services.llm_client import GeminiClient
from app.services.brain_service import ScriptGenerationService
from app.services.audio_service import AudioGenerationService
from app.services.transcription_service import TranscriptionService
from app.services.image_prompt_service import ImagePromptService
from app.services.packaging_engine import PackagingService
from app.models.script_schema import ThumbnailData

# Import your Phase 2 engines
import app.asset_processor as m2
import app.timeline_engine as m3

def setup_channel(base_dir: Path) -> tuple[Path, Path, str]:
    """Step 1: Get or create the channel. Exits immediately if new."""
    terminal_width = os.get_terminal_size().columns if os.isatty(sys.stdout.fileno()) else 80
    print("\n" + "="*terminal_width)
    print("   THE MASTER FORGE (ZERO-TOUCH AUTOMATION)")
    print("="*terminal_width)
    
    prompt_base = base_dir / "prompt_docs"
    prompt_base.mkdir(exist_ok=True)
    existing_channels = [d.name for d in prompt_base.iterdir() if d.is_dir()]
    
    if existing_channels:
        print("\nExisting Channels:")
        for idx, ch in enumerate(existing_channels):
            print(f"  {idx + 1}. {ch}")
        print(f"  {len(existing_channels) + 1}. [Create New Channel]")
    else:
        print("\nNo existing channels found.")
        
    channel_input = input("\nEnter channel number or type a new channel name: ").strip()
    
    is_new = False
    if channel_input.isdigit():
        idx = int(channel_input) - 1
        if 0 <= idx < len(existing_channels):
            channel_name = existing_channels[idx]
        elif idx == len(existing_channels):
            channel_name = input("Enter the new channel name: ").strip()
            is_new = True
        else:
            print("Invalid selection.")
            sys.exit(1)
    else:
        channel_name = channel_input
        if channel_name not in existing_channels:
            is_new = True

    channel_slug = re.sub(r'[^\w\s-]', '', channel_name).strip().replace(" ", "_").lower()
    prompt_dir = prompt_base / channel_slug
    channel_output_base = base_dir / "assets" / "outputs" / channel_slug
    
    prompt_dir.mkdir(parents=True, exist_ok=True)
    channel_output_base.mkdir(parents=True, exist_ok=True)
    
    if is_new:
        print(f"\n[*] Initializing NEW channel workspace: '{channel_slug}'")
        files_to_create = [
            "script_instructions.txt",
            "script_reviewer.txt",
            "script_editor.txt",
            "image_prompts_instructions.txt",
            "thumbnail_generator.txt", # Module 4
            "metadata_generator.txt"   # Module 4
        ]
        for file in files_to_create:
            (prompt_dir / file).touch()
            
        print(f"[!] SYSTEM HALT: I have created empty prompt documents in '{prompt_dir}'.")
        print("[!] Please open them, paste your channel-specific instructions, and run this script again.")
        sys.exit(0)
        
    return prompt_dir, channel_output_base, channel_slug


def get_project_workspace(channel_output_base: Path) -> Path:
    """Step 2: Checkpoint Architecture. Pick a new or existing project."""
    existing_projects = [d for d in channel_output_base.iterdir() if d.is_dir()]
    
    print(f"\n--- PROJECT MENU ---")
    print("  1. Create NEW Video Project")
    if existing_projects:
        print("  2. Resume EXISTING Project (Checkpoint Recovery)")
        
    choice = input("\nSelect option (1 or 2): ").strip()
    
    if choice == '2' and existing_projects:
        print("\nExisting Projects:")
        for idx, proj in enumerate(existing_projects):
            print(f"  {idx + 1}. {proj.name}")
        p_choice = int(input("\nSelect project number to resume: ").strip()) - 1
        return existing_projects[p_choice]
        
    # --- Create New Project Flow ---
    terminal_width = os.get_terminal_size().columns if os.isatty(sys.stdout.fileno()) else 80
    topic = input("\nEnter video title/topic: ").strip()

    print("\n" + "-"*terminal_width)
    theme_prompt = ("Enter the Core Theme / Premise (1-2 sentences).")
    print(textwrap.fill(theme_prompt, width=terminal_width - 5))
    core_theme = input("> ").strip()
    print("-" * terminal_width)

    length_input = input("\nEnter target length in minutes (default 3): ").strip()
    video_length = int(length_input) if length_input.isdigit() else 3
    
    print("\n--- Audio Configuration ---")
    voice = input("Enter TTS Voice (default: af_bella): ").strip() or "af_bella"
    speed_input = input("Enter Audio Speed (default: 1.0): ").strip()
    speed = float(speed_input) if speed_input else 1.0

    clean_title = re.sub(r'[^\w\s]', '', topic).strip().lower()
    words = clean_title.split()[:3]
    base_name = "_".join(words) if words else "untitled_project"

    run_dir = channel_output_base / base_name
    counter = 1
    while run_dir.exists():
        run_dir = channel_output_base / f"{base_name}_{counter}"
        counter += 1
    run_dir.mkdir(parents=True, exist_ok=True)
    
    config = {
        "title": topic,
        "core_theme": core_theme,
        "target_minutes": video_length,
        "audio_voice": voice,
        "audio_speed": speed
    }
    with open(run_dir / "run_config.json", "w") as f:
        json.dump(config, f, indent=4)
        
    return run_dir


def main():
    load_dotenv()
    # Script is now in the root directory
    base_dir = Path(__file__).resolve().parent
    
    # 1. Channel Setup
    prompt_dir, channel_output_base, channel_slug = setup_channel(base_dir)
    
    # 2. Get Project Workspace
    current_run_dir = get_project_workspace(channel_output_base)
    print(f"\n[System] Active Workspace: {current_run_dir}")
    
    # --- LEGACY PROJECT PATCH ---
    config_path = current_run_dir / "run_config.json"
    if not config_path.exists():
        print("[*] Patching config...")
        with open(config_path, "w") as f:
            config = {
                "title": current_run_dir.name.replace("_", " ").title(),
                "core_theme": "",
                "target_minutes": 3,
                "audio_voice": "af_bella",
                "audio_speed": 1.0
            }
            json.dump(config, f, indent=4)
            
    # Load configuration
    with open(config_path, "r") as f:
        config = json.load(f)
        
    topic = config["title"]
    core_theme = config["core_theme"]
    video_length = config["target_minutes"]
    audio_voice = config["audio_voice"]
    audio_speed = config.get("audio_speed", 1.0) 
    
    print("\n" + "-"*40)
    print("   SELECT FACTORY PHASE")
    print("-" * 40)
    print("  1. PHASE 1: Build Assets (Script, Audio, Prompts, Metadata)")
    print("  2. PHASE 2: Final Render (Watermarks, Upscale, Video Assembly)")
    
    phase = input("\nSelect Phase (1-2): ").strip()
    
    if phase == "1":
        print("\n[Engine] Initializing Phase 1 Pipeline...")
        llm = GeminiClient()
        brain = ScriptGenerationService(llm, prompt_dir=prompt_dir, output_dir=current_run_dir)
        audio_engine = AudioGenerationService(output_dir=current_run_dir) 
        transcriber = TranscriptionService(device="cuda", output_dir=current_run_dir) 
        prompt_engine = ImagePromptService(llm, prompt_dir=prompt_dir, output_dir=current_run_dir)
        packager = PackagingService(llm, prompt_dir=prompt_dir, output_dir=current_run_dir)
        
        # --- MODULE 1: CHECKPOINT EXECUTION ---
        script_path = current_run_dir / "final_script.txt"
        if script_path.exists():
            print("[Checkpoint] final_script.txt found. Skipping Brain...")
            with open(script_path, "r", encoding="utf-8") as f:
                final_script = f.read()
        else:
            final_script = brain.generate_script(title=topic, core_theme=core_theme, target_minutes=video_length, max_retries=3)
        
        existing_audio = list(current_run_dir.glob("*.wav"))
        if existing_audio:
            print(f"[Checkpoint] Existing audio found ({existing_audio[0].name}). Skipping Kokoro...")
            audio_path = existing_audio[0] 
        else:
            audio_path = audio_engine.generate_audio(text=final_script, voice=audio_voice, speed=audio_speed)
        
        existing_json = [f for f in current_run_dir.glob("*.json") if f.name not in ["run_config.json", "metadata.json"]]
        if existing_json:
            print(f"[Checkpoint] Transcription JSON found ({existing_json[0].name}). Skipping Whisper...")
            batched_json_path = existing_json[0] 
        else:
            batched_json_path = transcriber.extract_and_batch(audio_path=audio_path, min_duration=40.0, max_duration=60.0)
        
        prompt_path = current_run_dir / "time_stamped_prompts.txt"
        if prompt_path.exists():
            print("[Checkpoint] time_stamped_prompts.txt found. Skipping Image Prompts...")
        else:
            prompt_engine.generate_all_prompts(transcription_json_path=batched_json_path, raw_title=topic, script_text=final_script)
            
        # --- MODULE 4: PACKAGING (Thumbnails & Metadata) ---
        
        # CHECKPOINT 4A: Thumbnails
        thumbnail_prompts_path = current_run_dir / "thumbnail-image-prompts.json"
        
        is_calling_generate_thumbnail_prompts = not thumbnail_prompts_path.exists()
        
        if thumbnail_prompts_path.exists():
            print("[Checkpoint] thumbnail-image-prompts.json found. Loading best concept...")
            # We have to actually read the file and figure out the winner!
            with open(thumbnail_prompts_path, "r", encoding="utf-8") as f:
                saved_thumbs = json.load(f)
                
            # Import your schema at the top of master_forge if not already there, 
            # or just parse the dictionary directly like this:
            
            # Rebuild the Pydantic objects and find the max score
            thumbnails_list = [ThumbnailData(**t) for t in saved_thumbs["thumbnails"]]
            winning_thumbnail = max(thumbnails_list, key=lambda t: t.score)
            print(f"  -> Resumed Thumbnail Concept: '{winning_thumbnail.text}' (Score: {winning_thumbnail.score})")
            
            image_prompt_path = current_run_dir / "thumbnail-image-prompts.txt"
            with open(image_prompt_path, "w", encoding="utf-8") as f:
                f.write(winning_thumbnail.image_prompt)
            print(f"[Checkpoint] Success! Best Thumbnail saved to: {image_prompt_path.name}")
            
        else: 
            # 1. Generate Thumbnails AND capture the best one
            winning_thumbnail = packager.generate_thumbnail_prompts(raw_title=topic, script=final_script)
        
        
        # CHECKPOINT 4B: Metadata
        meta_path = current_run_dir / "metadata.json"
        if meta_path.exists():
            print("[Checkpoint] metadata.json found. Skipping Packaging Engine...")
        else:
            with open(batched_json_path, "r", encoding="utf-8") as f:
                timestamp_content = f.read() 
            
            if is_calling_generate_thumbnail_prompts: 
                time.sleep(SLEEP_TIME) # Adding your sleep buffer
            
            # 2. Pass the winning thumbnail into the Metadata generator
            packager.generate_metadata_json(
                script_text=final_script, 
                transcript_timestamps=timestamp_content,
                target_thumbnail=winning_thumbnail
            )
        # --- THE AIR GAP ---
        raw_dir = current_run_dir / "1_raw_images"
        raw_dir.mkdir(parents=True, exist_ok=True)
        
        print("\n" + "="*60)
        print("CHECKPOINT REACHED: PIPELINE PAUSED")
        print("="*60)
        print(f" 1. Phase 1 and Module 4 (Metadata/Thumbnails) complete.")
        print(f" 2. An empty folder was just created for you at:")
        print(f"    {raw_dir.absolute()}")
        print(" 3. ACTION REQUIRED: Run your Chrome Extension, download your images,")
        print("    and drop all of them into that folder.")
        print(" 4. Once pasted, run this Master Forge again and select PHASE 2.")
        print("============================================================\n")

    elif phase == "2":
        print("\n[Engine] Initializing Phase 2 (Zero-Touch Render)...")
        
        raw_dir = current_run_dir / "1_raw_images"
        watermark_dir = current_run_dir / "2_watermark_removed"
        upscale_dir = current_run_dir / "3_upscaled"
        temp_dir = current_run_dir / "temp_upscale"
        
        if not raw_dir.exists() or not any(raw_dir.iterdir()):
            print("\n[!] ERROR: '1_raw_images' is empty! Did you forget to paste your Chrome Extension images?")
            sys.exit(1)
            
        # 1. Run Asset Processor (Module 2)
        m2.run_watermark_removal(raw_dir, watermark_dir)
        m2.run_upscaler(watermark_dir, upscale_dir, temp_dir)
        m2.run_renamer(upscale_dir, current_run_dir) # Formats to timeline standard
        
        # 2. Run Timeline Engine (Module 3)
        print("\n[Engine] Assets processed. Handing off to Cinematic Timeline Engine...")
        m3.build_video(current_run_dir)
        
        print("\n" + "="*50)
        print(" 🎉 FULLY AUTOMATED RENDER COMPLETE!")
        print("="*50 + "\n")
        
    else:
        print("\n[!] Invalid selection. Exiting.")

if __name__ == "__main__":
    main()