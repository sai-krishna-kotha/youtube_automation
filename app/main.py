import sys
import re
import os
import json
import textwrap
from pathlib import Path
from dotenv import load_dotenv

# ==========================================
# THE SILENCER BLOCK
# ==========================================
import warnings
import logging

# 1. Suppress all Python warnings (PyTorch, Pyannote, TorchCodec, etc.)
warnings.filterwarnings("ignore")

# 2. Suppress HuggingFace/Transformers chatter
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

# 3. Suppress INFO logs from third-party libraries (only show errors)
logging.getLogger("whisperx").setLevel(logging.ERROR)
logging.getLogger("pyannote").setLevel(logging.ERROR)
logging.getLogger("lightning").setLevel(logging.ERROR)
logging.getLogger("pytorch_lightning").setLevel(logging.ERROR)
# ==========================================


sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.services.llm_client import GeminiClient
from app.services.brain_service import ScriptGenerationService
from app.services.audio_service import AudioGenerationService
from app.services.transcription_service import TranscriptionService
from app.services.image_prompt_service import ImagePromptService

def setup_channel(base_dir: Path) -> tuple[Path, Path, str]:
    """
    Step 1: Get or create the channel. Exits immediately if new.
    """
    terminal_width = os.get_terminal_size().columns if os.isatty(sys.stdout.fileno()) else 80
    print("\n" + "="*terminal_width)
    print("   YOUTUBE AUTOMATION PIPELINE (MODULE 1)")
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
    
    # Determine if user selected an existing channel or typed a new one
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
            "image_prompts_instructions.txt"
        ]
        for file in files_to_create:
            (prompt_dir / file).touch()
            
        print(f"[!] SYSTEM HALT: I have created empty prompt documents in '{prompt_dir}'.")
        print("[!] Please open them, paste your channel-specific instructions, and run this script again.")
        sys.exit(0) # Exits cleanly without asking for video details!
        
    return prompt_dir, channel_output_base, channel_slug


def get_project_workspace(channel_output_base: Path) -> Path:
    """
    Step 2: Checkpoint Architecture. Pick a new or existing project.
    """
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
    theme_prompt = ("Enter the Core Theme / Premise (1-2 sentences or a full paragraph). "
                   "This is the precise lesson or feeling you want the audience to walk away with:")
    print(textwrap.fill(theme_prompt, width=terminal_width - 5))
    core_theme = input("> ").strip()
    print("-" * terminal_width)

    length_input = input("\nEnter target length in minutes (default 3): ").strip()
    video_length = int(length_input) if length_input.isdigit() else 3
    
    # Audio configuration injected right at the start
    print("\n--- Audio Configuration ---")
    voice = input("Enter TTS Voice (default: af_bella): ").strip() or "af_bella"
    speed_input = input("Enter Audio Speed (default: 1.0): ").strip()
    speed = float(speed_input) if speed_input else 1.0

    # Create directory
    clean_title = re.sub(r'[^\w\s]', '', topic).strip().lower()
    words = clean_title.split()[:3]
    base_name = "_".join(words) if words else "untitled_project"

    run_dir = channel_output_base / base_name
    counter = 1
    while run_dir.exists():
        run_dir = channel_output_base / f"{base_name}_{counter}"
        counter += 1
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Save checkpoint config
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
    base_dir = Path(__file__).resolve().parent.parent
    
    # 1. Channel Setup (will exit here if new)
    prompt_dir, channel_output_base, channel_slug = setup_channel(base_dir)
    
    # 2. Get Project Workspace (New or Resume)
    current_run_dir = get_project_workspace(channel_output_base)
    print(f"\n[System] Active Workspace: {current_run_dir}\n")
    
    # --- LEGACY PROJECT PATCH ---
    config_path = current_run_dir / "run_config.json"
    if not config_path.exists():
        print("[!] Legacy Project Detected: run_config.json is missing.")
        print("[*] Let's quickly patch this project so you can resume it.")
        
        # Guess the title from the folder name
        guessed_title = current_run_dir.name.replace("_", " ").title()
        topic_input = input(f"Enter video title [{guessed_title}]: ").strip()
        topic = topic_input if topic_input else guessed_title
        
        core_theme = input("Enter Core Theme (or leave blank): ").strip()
        audio_voice = input("Enter TTS Voice [af_bella]: ").strip() or "af_bella"
        
        # Create the missing config file
        config = {
            "title": topic,
            "core_theme": core_theme,
            "target_minutes": 3,
            "audio_voice": audio_voice,
            "audio_speed": 1.0
        }
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)
        print("[+] Legacy project patched successfully!\n")
        
    # Load configuration
    with open(config_path, "r") as f:
        config = json.load(f)
        
    topic = config["title"]
    core_theme = config["core_theme"]
    video_length = config["target_minutes"]
    audio_voice = config["audio_voice"]
    audio_speed = config.get("audio_speed", 1.0) # .get() protects against older JSON versions
    
    # --- SERVICE INITIALIZATION ---
    llm = GeminiClient()
    brain = ScriptGenerationService(llm, prompt_dir=prompt_dir, output_dir=current_run_dir)
    audio_engine = AudioGenerationService(output_dir=current_run_dir) 
    transcriber = TranscriptionService(device="cuda", output_dir=current_run_dir) 
    prompt_engine = ImagePromptService(llm, prompt_dir=prompt_dir, output_dir=current_run_dir) 
    
    # --- PIPELINE EXECUTION (WITH CHECKPOINTS) ---
    
    # Step 1: Script Generation
    script_path = current_run_dir / "final_script.txt"
    if script_path.exists():
        print("[Checkpoint] Found final_script.txt. Skipping Brain generation...")
        with open(script_path, "r", encoding="utf-8") as f:
            final_script = f.read()
    else:
        final_script = brain.generate_script(
            title=topic,
            core_theme=core_theme, 
            target_minutes=video_length, 
            max_retries=3
        )
    
    # Step 2: Audio Generation
    existing_audio = list(current_run_dir.glob("*.wav"))
    if existing_audio:
        print(f"[Checkpoint] Found existing audio ({existing_audio[0].name}). Skipping Kokoro generation...")
        audio_path = existing_audio[0] # REMOVED str()
    else:
        print(f"\n[Pipeline] Moving to audio... (Voice: {audio_voice}, Speed: {audio_speed})")
        audio_path = audio_engine.generate_audio(text=final_script, voice=audio_voice, speed=audio_speed)
    
    # Step 3: Transcription / Smart Batching
    existing_json = [f for f in current_run_dir.glob("*.json") if f.name != "run_config.json"]
    if existing_json:
        print(f"[Checkpoint] Found transcription JSON ({existing_json[0].name}). Skipping Whisper extraction...")
        batched_json_path = existing_json[0] # REMOVED str()
    else:
        print("\n[Pipeline] Audio complete. Extracting Smart Batches...")
        batched_json_path = transcriber.extract_and_batch(
            audio_path=audio_path, 
            min_duration=40.0, 
            max_duration=60.0
        )
    
    # Step 4: Image Prompt Generation
    prompt_path = current_run_dir / "time_stamped_prompts.txt"
    if prompt_path.exists():
        print("[Checkpoint] Found time_stamped_prompts.txt. Skipping Prompt Engine...")
    else:
        print("\n[Pipeline] Smart batching complete. Formatting visual timeline...")
        prompt_engine.generate_all_prompts(
            transcription_json_path=batched_json_path,
            raw_title=topic,
            script_text=final_script
        )
    
    print(f"\n--- MODULE 1 COMPLETE | SAVED TO: {current_run_dir.name} ---")

if __name__ == "__main__":
    main()