import sys
import re
import os
import textwrap # For beautiful terminal formatting
from pathlib import Path
from dotenv import load_dotenv

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.services.llm_client import GeminiClient
from app.services.brain_service import ScriptGenerationService
from app.services.audio_service import AudioGenerationService
from app.services.transcription_service import TranscriptionService
from app.services.image_prompt_service import ImagePromptService

def setup_channel(channel_name: str, base_dir: Path) -> tuple[Path, Path]:
    """
    Ensures the channel-specific prompt and output directories exist.
    If it's a new channel, it scaffolds the required blank .txt files.
    """
    channel_slug = re.sub(r'[^\w\s-]', '', channel_name).strip().replace(" ", "_").lower()
    
    prompt_dir = base_dir / "prompt_docs" / channel_slug
    channel_output_base = base_dir / "assets" / "outputs" / channel_slug
    
    is_new_channel = not prompt_dir.exists()
    
    prompt_dir.mkdir(parents=True, exist_ok=True)
    channel_output_base.mkdir(parents=True, exist_ok=True)
    
    if is_new_channel:
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
        sys.exit(0)
        
    return prompt_dir, channel_output_base

def create_run_directory(base_output_dir: Path, title: str) -> Path:
    """Creates a unique folder for this specific video run."""
    clean_title = re.sub(r'[^\w\s]', '', title).strip().lower()
    words = clean_title.split()[:3]
    base_name = "_".join(words) if words else "untitled_project"

    run_dir = base_output_dir / base_name
    counter = 1
    
    while run_dir.exists():
        run_dir = base_output_dir / f"{base_name}_{counter}"
        counter += 1

    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir

def get_user_inputs(base_dir: Path) -> tuple[str, str, str, int]:
    """
    Interactive CLI for the user to configure the run.
    Now prompts for the Core Theme.
    """
    terminal_width = os.get_terminal_size().columns if os.isatty(sys.stdout.fileno()) else 80
    
    print("\n" + "="*terminal_width)
    print("   YOUTUBE AUTOMATION PIPELINE (MULTI-CHANNEL)")
    print("="*terminal_width)
    
    prompt_base = base_dir / "prompt_docs"
    prompt_base.mkdir(exist_ok=True)
    existing_channels = [d.name for d in prompt_base.iterdir() if d.is_dir()]
    
    if existing_channels:
        print("\nExisting Channels:")
        for idx, ch in enumerate(existing_channels):
            print(f"  {idx + 1}. {ch}")
    else:
        print("\nNo existing channels found.")
        
    channel_input = input("\nEnter channel name (or select number): ").strip()
    if channel_input.isdigit() and 1 <= int(channel_input) <= len(existing_channels):
        channel_name = existing_channels[int(channel_input) - 1]
    else:
        channel_name = channel_input
        
    topic = input("Enter video title/topic: ").strip()

    # --- THE DIRECTED AI UPGRADE: CORE THEME PROMPT ---
    print("\n" + "-"*terminal_width)
    theme_prompt = ("Enter the Core Theme / Premise (1-2 sentences). "
                   "This is the precise lesson or feeling you want the audience to walk away with:")
    wrapped_theme_prompt = textwrap.fill(theme_prompt, width=terminal_width - 5)
    print(wrapped_theme_prompt)
    core_theme = input("> ").strip()
    print("-"*terminal_width + "\n")

    length_input = input("Enter target length in minutes (default 2): ").strip()
    video_length = int(length_input) if length_input.isdigit() else 2
    
    return channel_name, topic, core_theme, video_length

def main():
    load_dotenv()
    base_dir = Path(__file__).resolve().parent.parent
    
    # 1. Get user configuration (Now returns 4 items)
    channel_name, topic, core_theme, video_length = get_user_inputs(base_dir)
    
    # 2. Setup Channel Directories
    prompt_dir, channel_output_base = setup_channel(channel_name, base_dir)
    
    # 3. Create Unique Run Directory
    current_run_dir = create_run_directory(channel_output_base, topic)
    print(f"\n[System] Active Workspace: {current_run_dir}\n")
    
    # --- SERVICE INITIALIZATION ---
    llm = GeminiClient()
    
    # Brain and Prompt services now receive prompt_dir
    brain = ScriptGenerationService(llm, prompt_dir=prompt_dir, output_dir=current_run_dir)
    audio_engine = AudioGenerationService(output_dir=current_run_dir) 
    transcriber = TranscriptionService(device="cpu", output_dir=current_run_dir) 
    prompt_engine = ImagePromptService(llm, prompt_dir=prompt_dir, output_dir=current_run_dir) 
    
    # --- PIPELINE EXECUTION ---
    # Brain service is updated to accept core_theme
    final_script = brain.generate_script(
        title=topic,
        core_theme=core_theme, # Directed AI variable injected here
        target_minutes=video_length, 
        max_retries=4
    )
    
    print("\n[Pipeline] Script complete. Moving to audio...")
    audio_path = audio_engine.generate_audio(text=final_script)
    
    print("\n[Pipeline] Audio complete. Extracting Smart Batches...")
    batched_json_path = transcriber.extract_and_batch(
        audio_path=audio_path, 
        min_duration=40.0, 
        max_duration=60.0
    )
    
    print("\n[Pipeline] Smart batching complete. Formatting visual timeline...")
    prompt_engine.generate_all_prompts(
        transcription_json_path=batched_json_path,
        raw_title=topic,
        script_text=final_script
    )
    
    print(f"\n--- MODULE 1 COMPLETE | SAVED TO: {current_run_dir.name} ---")

if __name__ == "__main__":
    main()