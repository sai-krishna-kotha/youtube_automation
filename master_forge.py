import sys
import re
import os
import json
import textwrap
from pathlib import Path
from dotenv import load_dotenv
import time
import yaml
import shutil

SLEEP_TIME = 20

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

import app.asset_processor as m2
import app.timeline_engine as m3

# --- WORKSPACE CLEANUP MANAGERS ---
def unpack_system_data(run_dir: Path):
    """Temporarily pulls internal JSONs/Logs into the root so services can use them."""
    sys_dir = run_dir / "_system_data"
    if sys_dir.exists():
        for f in sys_dir.iterdir():
            if f.is_file():
                shutil.move(str(f), str(run_dir / f.name))

def pack_system_data(run_dir: Path):
    """Hides all JSONs, logs, and intermediary files into a hidden folder for the user."""
    sys_dir = run_dir / "_system_data"
    sys_dir.mkdir(exist_ok=True)
    
    # Scoop up all system files
    for ext in ["*.json", "*.log"]:
        for f in run_dir.glob(ext):
            shutil.move(str(f), str(sys_dir / f.name))
            
    # Also hide the redundant thumbnail text prompt
    old_thumb = run_dir / "thumbnail-image-prompts.txt"
    if old_thumb.exists():
        shutil.move(str(old_thumb), str(sys_dir / old_thumb.name))
# ---------------------------------------

def setup_channel(base_dir: Path) -> tuple[Path, Path, Path, str]:
    terminal_width = os.get_terminal_size().columns if os.isatty(sys.stdout.fileno()) else 80
    print("\n" + "="*terminal_width)
    print("   THE MASTER FORGE (ZERO-TOUCH AUTOMATION)")
    print("="*terminal_width)
    
    prompt_os_dir = base_dir / "promptss"
    master_prompts_dir = prompt_os_dir / "master_prompts"
    channels_dir = prompt_os_dir / "channels"
    
    master_prompts_dir.mkdir(parents=True, exist_ok=True)
    channels_dir.mkdir(parents=True, exist_ok=True)
    
    existing_channels = [d.name for d in channels_dir.iterdir() if d.is_dir()]
    
    if existing_channels:
        print("\nExisting Channels:")
        for idx, ch in enumerate(existing_channels):
            print(f"  {idx + 1}. {ch}")
        print(f"  {len(existing_channels) + 1}. [Create New Channel]")
        print("  0. To Exit")
    else:
        print("\nNo existing channels found in PromptOS/channels.")
        
    channel_input = input("\nEnter channel number or type a new channel name: ").strip()
    if channel_input == '0':
        sys.exit(0)
        
    is_new = False
    if channel_input.isdigit():
        idx = int(channel_input) - 1
        if 0 <= idx < len(existing_channels):
            channel_name = existing_channels[idx]
        elif idx == len(existing_channels):
            channel_name = input("Enter the exact new channel name (e.g., Tech Decoded): ").strip()
            is_new = True
        else:
            print("Invalid selection.")
            sys.exit(1)
    else:
        channel_name = channel_input
        if channel_name not in existing_channels:
            is_new = True

    channel_dir = channels_dir / channel_name
    channel_slug = re.sub(r'[^\w\s-]', '', channel_name).strip().replace(" ", "_").lower()
    channel_output_base = base_dir / "assets" / "outputs" / channel_slug
    
    if is_new:
        print(f"\n[*] Initializing NEW channel workspace: '{channel_name}'")
        channel_dir.mkdir(parents=True, exist_ok=True)
        (channel_dir / "Requests").mkdir(parents=True, exist_ok=True)
        channel_output_base.mkdir(parents=True, exist_ok=True)
        
        (channel_dir / "layer1.yaml").touch()
        (channel_dir / "layer2.yaml").touch()
        (channel_dir / "layer3.yaml").touch()
            
        print(f"[!] SYSTEM HALT: I have created empty YAML identity layers in '{channel_dir}'.")
        print("[!] Please configure your channel identity and run the script again.")
        sys.exit(0)
        
    return master_prompts_dir, channel_dir, channel_output_base, channel_slug


def get_project_workspace(channel_dir: Path, channel_output_base: Path) -> Path:
    channel_output_base.mkdir(parents=True, exist_ok=True)
    existing_projects = [d for d in channel_output_base.iterdir() if d.is_dir()]
    requests_dir = channel_dir / "Requests"
    
    pending_requests = sorted(list(requests_dir.glob("*.yaml")), reverse=True)
    
    print(f"\n--- PROJECT MENU ---")
    print("  1. Create NEW Project from a Request YAML")
    if existing_projects:
        print("  2. Resume EXISTING Project (Checkpoint Recovery)")
    print("  0. To Exit")
    
    choice = input("\nSelect option: ").strip()
    if choice == '0':
        sys.exit(0)
        
    elif choice == '2' and existing_projects:
        print("\nExisting Projects:")
        for idx, proj in enumerate(existing_projects):
            print(f"  {idx + 1}. {proj.name}")
        print("  0. To Exit")
        
        p_choice = int(input("\nSelect project number to resume: ").strip()) - 1
        if p_choice == -1:
            sys.exit(0)
        if p_choice < 0 or p_choice >= len(existing_projects):
            sys.exit("Invalid entry!! Exiting the system")
        return existing_projects[p_choice]
        
    elif choice == '1':
        if not pending_requests:
            print(f"\n[!] No YAML files found in {requests_dir}. Please drop a request file there first.")
            sys.exit(1)
            
        page_size = 10
        total_pages = (len(pending_requests) + page_size - 1) // page_size
        current_page = 0
        selected_request_path = None
        
        while True:
            start_idx = current_page * page_size
            end_idx = start_idx + page_size
            page_items = pending_requests[start_idx:end_idx]
            
            print(f"\n--- Pending Requests (Page {current_page + 1}/{total_pages}) ---")
            for i, req in enumerate(page_items):
                print(f"  {i + 1}. {req.name}")
            
            print("-" * 40)
            if current_page > 0:
                print("  [P] Previous Page")
            if current_page < total_pages - 1:
                print("  [N] Next Page")
            print("  [0] To Exit")
            
            r_choice = input("\nSelect request number or navigate: ").strip().lower()
            
            if r_choice == '0':
                sys.exit(0)
            elif r_choice == 'n' and current_page < total_pages - 1:
                current_page += 1
            elif r_choice == 'p' and current_page > 0:
                current_page -= 1
            elif r_choice.isdigit():
                idx = int(r_choice) - 1
                if 0 <= idx < len(page_items):
                    selected_request_path = page_items[idx]
                    break
                else:
                    print("[!] Invalid selection. Try again.")
            else:
                print("[!] Invalid input. Try again.")

        with open(selected_request_path, 'r', encoding='utf-8') as f:
            request_data = yaml.safe_load(f) or {}
            
        video_data = request_data.get('video', {})
        voice_data = request_data.get('voice', {})
            
        topic = video_data.get('raw_title', 'Untitled')
        core_theme = video_data.get('core_theme', '')
        hook_paragraph = video_data.get('hook_paragraph')
        video_length = video_data.get('target_duration_minutes', 3)
        upscaler_model = video_data.get('upscaler_model', 'realesrgan-x4plus-anime')
        voice = voice_data.get('kokoro_model', 'af_bella')
        speed = voice_data.get('speed', 1.0)

        max_num = 0
        if channel_output_base.exists():
            for d in channel_output_base.iterdir():
                if d.is_dir():
                    match = re.match(r'^(\d+)_', d.name)
                    if match:
                        try:
                            max_num = max(max_num, int(match.group(1)))
                        except ValueError:
                            pass
        next_num = max_num + 1

        clean_title = re.sub(r'[^\w\s]', '', topic).strip().lower()
        words = clean_title.split()[:3]
        title_part = "_".join(words) if words else "untitled_project"

        base_name = f"{next_num}_{title_part}"
        run_dir = channel_output_base / base_name
        counter = 1
        while run_dir.exists():
            run_dir = channel_output_base / f"{base_name}_{counter}"
            counter += 1
        run_dir.mkdir(parents=True, exist_ok=True)
        
        config = {
            "title": topic,
            "core_theme": core_theme,
            "hook_paragraph": hook_paragraph,
            "target_minutes": video_length,
            "audio_voice": voice,
            "upscaler_model": upscaler_model, # <--- Add this line
            "audio_speed": speed,
            "request_file_used": selected_request_path.name
        }
        with open(run_dir / "run_config.json", "w") as f:
            json.dump(config, f, indent=4)
            
        print(f"\n[System] Created new workspace from {selected_request_path.name}")
        return run_dir


def main():
    load_dotenv()
    base_dir = Path(__file__).resolve().parent
    
    master_prompts_dir, channel_dir, channel_output_base, channel_slug = setup_channel(base_dir)
    current_run_dir = get_project_workspace(channel_dir, channel_output_base)
    
    # --- PREPARE WORKSPACE FOR SERVICES ---
    unpack_system_data(current_run_dir)
    print(f"\n[System] Active Workspace: {current_run_dir}")
    
    config_path = current_run_dir / "run_config.json"
    
    with open(config_path, "r") as f:
        config = json.load(f)
        
    topic = config["title"]
    core_theme = config["core_theme"]
    hook_paragraph = config.get("hook_paragraph", "")
    video_length = config["target_minutes"]
    audio_voice = config["audio_voice"]
    audio_speed = config.get("audio_speed", 1.0) 
    target_upscaler = config.get("upscaler_model", "realesrgan-x4plus-anime") # <--- Add this line
    
    request_filename = config.get("request_file_used")
    
    if not request_filename:
        print("\n[!] Legacy Project Detected: This project doesn't know which YAML request it belongs to.")
        requests_dir = channel_dir / "Requests"
        available_yamls = sorted(list(requests_dir.glob("*.yaml")))
        
        if not available_yamls:
            print(f"[!] Critical Error: No YAML files found in {requests_dir}. Please add one to resume.")
            sys.exit(1)
            
        print("Please link this project to its original YAML request:")
        for idx, yf in enumerate(available_yamls):
            print(f"  {idx + 1}. {yf.name}")
            
        yaml_choice = int(input("\nSelect the correct request number: ").strip()) - 1
        request_filename = available_yamls[yaml_choice].name
        
        config["request_file_used"] = request_filename
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)
        print(f"  -> Linked successfully to {request_filename}!")
    
    request_path = channel_dir / "Requests" / request_filename
    
    if not request_path.exists():
        print(f"\n[!] ERROR: Cannot find the request file '{request_filename}' in {channel_dir}/Requests/")
        sys.exit(1)
        
    with open(request_path, "r", encoding="utf-8") as f:
        raw_yaml_request = f.read()
        
    print("\n" + "-"*40)
    print("   SELECT FACTORY PIPELINE")
    print("-" * 40)
    print("  1. FULLY AUTOMATED (Phase 1 -> 1.5 -> 2)")
    print("  2. MANUAL MODE (Step-by-step with pauses)")
    print("  3. Run Phase 1 Only (Build Assets)")
    print("  4. Run Phase 1.5 Only (Auto-Generate Images)")
    print("  5. Run Phase 2 Only (Final Render)")
    print("  6. Setup Gemini Authentication (Run Once)")
    print("  0. To Exit")
    
    phase_choice = input("\nSelect Option (0-6): ").strip()
    
    if phase_choice == '0':
        pack_system_data(current_run_dir)
        sys.exit(0)
        
    if phase_choice == '6':
        from app.services.image_automation import GeminiImageScraper
        scraper = GeminiImageScraper(base_dir=base_dir)
        scraper.setup_session()
        sys.exit(0)
        
    # --- PIPELINE ROUTING FLAGS ---
    run_phase1 = phase_choice in ['1', '2', '3']
    run_phase1_5 = phase_choice in ['1', '2', '4']
    run_phase2 = phase_choice in ['1', '2', '5']
    manual_mode = phase_choice == '2'

    # ==============================================================
    # PHASE 1: ASSET CREATION
    # ==============================================================
    if run_phase1:
        print("\n[Engine] Initializing Phase 1 Pipeline...")
        
        from app.services.llm_client import GeminiClient
        from app.services.brain_service import ScriptGenerationService
        from app.services.image_prompt_service import ImagePromptService
        from app.services.packaging_engine import PackagingService
        from app.models.script_schema import ThumbnailData
        
        llm = GeminiClient()
        brain = ScriptGenerationService(llm, master_prompts_dir=master_prompts_dir, channel_dir=channel_dir, output_dir=current_run_dir)
        prompt_engine = ImagePromptService(llm, master_prompts_dir=master_prompts_dir, channel_dir=channel_dir, output_dir=current_run_dir)
        packager = PackagingService(llm, master_prompts_dir=master_prompts_dir, channel_dir=channel_dir, output_dir=current_run_dir)
        
        # --- MODULE 1: SCRIPT ---
        script_path = current_run_dir / "final_script.txt"
        if script_path.exists():
            print("[Checkpoint] final_script.txt found. Skipping Brain...")
            with open(script_path, "r", encoding="utf-8") as f:
                final_script = f.read()
        else:
            final_script = brain.generate_script(request_yaml=raw_yaml_request, max_retries=3)
        
        if manual_mode:
            ans = input("\nProceed to Audio Generation? (1: Yes, 0: Exit, 2: Switch to Auto): ").strip()
            if ans == '0': pack_system_data(current_run_dir); sys.exit(0)
            elif ans == '2': manual_mode = False; print("[System] Switched to Fully Automated mode.")

        # --- MODULE 2: AUDIO ---
        existing_audio = list(current_run_dir.glob("*.wav"))
        if existing_audio:
            print(f"[Checkpoint] Existing audio found ({existing_audio[0].name}). Skipping Kokoro Initialization...")
            audio_path = existing_audio[0] 
        else:
            print("\n[Engine] Initializing Kokoro TTS Pipeline...")
            from app.services.audio_service import AudioGenerationService
            audio_engine = AudioGenerationService(output_dir=current_run_dir) 
            audio_path = audio_engine.generate_audio(text=final_script, voice=audio_voice, speed=audio_speed)
        
        if manual_mode:
            ans = input("\nProceed to Transcription? (1: Yes, 0: Exit, 2: Switch to Auto): ").strip()
            if ans == '0': pack_system_data(current_run_dir); sys.exit(0)
            elif ans == '2': manual_mode = False; print("[System] Switched to Fully Automated mode.")
        
        # --- MODULE 3: TRANSCRIPTION ---
        existing_json = [f for f in current_run_dir.glob("*.json") if f.name not in [
            "run_config.json", 
            "metadata.json", 
            "prompts_checkpoint.json", 
            "thumbnail-image-prompts.json",
            "script_checkpoint.json"
        ]]
        
        if existing_json:
            print(f"[Checkpoint] Transcription JSON found ({existing_json[0].name}). Skipping Whisper Initialization...")
            batched_json_path = existing_json[0] 
        else:
            print("\n[Engine] Initializing WhisperX Transcription Pipeline...")
            from app.services.transcription_service import TranscriptionService
            transcriber = TranscriptionService(device="cuda", output_dir=current_run_dir) 
            batched_json_path = transcriber.extract_and_batch(
                audio_path=audio_path, 
                request_yaml=raw_yaml_request,
                min_duration=40.0, 
                max_duration=60.0
            )
            
        if manual_mode:
            ans = input("\nProceed to Image Prompts generation? (1: Yes, 0: Exit, 2: Switch to Auto): ").strip()
            if ans == '0': pack_system_data(current_run_dir); sys.exit(0)
            elif ans == '2': manual_mode = False; print("[System] Switched to Fully Automated mode.")
        
        # --- MODULE 4: IMAGE PROMPTS ---
        print("\n[Pipeline] Validating/Generating Image Prompts...")
        prompt_engine.generate_all_prompts(
            transcription_json_path=batched_json_path, 
            request_yaml=raw_yaml_request, 
            script_text=final_script
        )
        
        if manual_mode:
            ans = input("\nProceed to Packaging Engine (Thumbnails & Metadata)? (1: Yes, 0: Exit, 2: Switch to Auto): ").strip()
            if ans == '0': pack_system_data(current_run_dir); sys.exit(0)
            elif ans == '2': manual_mode = False; print("[System] Switched to Fully Automated mode.")
                
        # --- MODULE 5: PACKAGING ---
        thumbnail_prompts_path = current_run_dir / "thumbnail-image-prompts.json"
        is_calling_generate_thumbnail_prompts = not thumbnail_prompts_path.exists()
        
        if thumbnail_prompts_path.exists():
            print("\n[Checkpoint] thumbnail-image-prompts.json found. Loading best concept...")
            with open(thumbnail_prompts_path, "r", encoding="utf-8") as f:
                saved_thumbs = json.load(f)
                
            thumbnails_list = [ThumbnailData(**t) for t in saved_thumbs["thumbnails"]]
            winning_thumbnail = max(thumbnails_list, key=lambda t: t.score)
            print(f"  -> Resumed Thumbnail Concept: '{winning_thumbnail.text}' (Score: {winning_thumbnail.score})")
            
        else: 
            winning_thumbnail = packager.generate_thumbnail_prompts(request_yaml=raw_yaml_request, script=final_script)
        
        meta_path = current_run_dir / "metadata.json"
        if meta_path.exists():
            print("[Checkpoint] metadata.json found. Skipping Packaging Engine...")
        else:
            with open(batched_json_path, "r", encoding="utf-8") as f:
                timestamp_content = f.read() 
            
            if is_calling_generate_thumbnail_prompts: 
                print(f"Waiting {SLEEP_TIME} seconds to protect API rate limits...")
                time.sleep(SLEEP_TIME) 
            
            packager.generate_metadata_json(
                request_yaml=raw_yaml_request,
                script_text=final_script, 
                transcript_timestamps=timestamp_content,
                target_thumbnail=winning_thumbnail
            )
            
        raw_dir = current_run_dir / "1_raw_images"
        raw_dir.mkdir(parents=True, exist_ok=True)
        print("\n[System] Phase 1 Complete.")
        
        if not run_phase1_5:
            print("\n[System] Packing internal data files into _system_data folder...")
            pack_system_data(current_run_dir)
            print("============================================================")
            print("CHECKPOINT REACHED: ASSET GENERATION COMPLETE")
            print("============================================================\n")

        if run_phase1_5 and manual_mode:
            ans = input("\nProceed to Phase 1.5 (Auto-Generate Images via Playwright)? (1: Yes, 0: Exit, 2: Switch to Auto): ").strip()
            if ans == '0': pack_system_data(current_run_dir); sys.exit(0)
            elif ans == '2': manual_mode = False; print("[System] Switched to Fully Automated mode.")

    # ==============================================================
    # PHASE 1.5: PLAYWRIGHT IMAGE SCRAPER
    # ==============================================================
    if run_phase1_5:
        print("\n[Engine] Initializing Playwright Image Automation...")
        from app.services.image_automation import GeminiImageScraper
        
        scraper = GeminiImageScraper(base_dir=base_dir)
        
        # --- THE AUTO-AUTH INTERCEPT ---
        if not scraper.session_dir.exists():
            print("\n[!] Gemini Authentication missing! Pausing pipeline to authenticate...")
            scraper.setup_session()
            
            auth_proceed = input("\nAuthentication complete. Do you want to proceed with image generation? (1: Yes, 0: Exit): ").strip()
            if auth_proceed != '1':
                pack_system_data(current_run_dir)
                sys.exit(0)
        # -------------------------------

        prompts_file = current_run_dir / "time_stamped_prompts.txt"
        raw_output_dir = current_run_dir / "1_raw_images"
        
        if not prompts_file.exists():
            print(f"\n[!] ERROR: Cannot find {prompts_file.name}. Ensure Phase 1 ran successfully.")
            pack_system_data(current_run_dir)
            sys.exit(1)
            
        # --- NEW: AUTO-REPAIR LOOP FOR MISSING IMAGES ---
        max_repair_passes = 4
        for pass_num in range(1, max_repair_passes + 1):
            scraper.generate_images(input_file=prompts_file, output_dir=raw_output_dir)
            
            # Verify Counts
            with open(prompts_file, 'r', encoding='utf-8') as f:
                expected_count = len([line for line in f if line.strip() and re.search(r"\[([\d\.]+)\]", line)])
            
            actual_count = len(list(raw_output_dir.glob("*.png")))
            
            if actual_count >= expected_count:
                print(f"\n[System] Verification Passed: {actual_count}/{expected_count} images generated successfully!")
                break
            else:
                print(f"\n[!] Verification Failed (Pass {pass_num}/{max_repair_passes}): Found {actual_count} images, expected {expected_count}.")
                if pass_num < max_repair_passes:
                    print("[!] Re-running scraper to patch missing images...")
                    time.sleep(3)
                else:
                    print("[!] Max repair passes reached. Proceeding with missing images (likely blocked by Gemini policy).")
        # ------------------------------------------------
        
        if not run_phase2:
            pack_system_data(current_run_dir)
            
        if run_phase2 and manual_mode:
            ans = input("\nProceed to Phase 2 (Final Render Pipeline)? (1: Yes, 0: Exit, 2: Switch to Auto): ").strip()
            if ans == '0': pack_system_data(current_run_dir); sys.exit(0)
            elif ans == '2': manual_mode = False; print("[System] Switched to Fully Automated mode.")

    # ==============================================================
    # PHASE 2: FINAL RENDER
    # ==============================================================
    if run_phase2:
        print("\n[Engine] Initializing Phase 2 (Asset Processing & Render)...")
        
        raw_dir = current_run_dir / "1_raw_images"
        wm_dir = current_run_dir / "2_watermark_removed"
        up_dir = current_run_dir / "3_upscaled"
        final_dir = current_run_dir / "4_final_production"
        temp_dir = current_run_dir / "temp_upscale"
        
        raw_count = len([f for f in raw_dir.iterdir() if f.is_file()]) if raw_dir.exists() else 0
        wm_count = len([f for f in wm_dir.iterdir() if f.is_file()]) if wm_dir.exists() else 0
        up_count = len([f for f in up_dir.iterdir() if f.is_file()]) if up_dir.exists() else 0
        final_count = len([f for f in final_dir.iterdir() if f.is_file()]) if final_dir.exists() else 0
        
        if raw_count == 0 and wm_count == 0 and up_count == 0 and final_count == 0:
            print("\n[!] ERROR: '1_raw_images' is completely empty! Run Phase 1.5 first.")
            pack_system_data(current_run_dir)
            sys.exit(1)
            
        print("\n--- FACTORY CHECKPOINT STATUS ---")
        print(f"  [{'✓' if raw_count > 0 else ' '}] {raw_count} images in 1_raw_images")
        print(f"  [{'✓' if wm_count > 0 else ' '}] {wm_count} images in 2_watermark_removed")
        print(f"  [{'✓' if up_count > 0 else ' '}] {up_count} images in 3_upscaled")
        print(f"  [{'✓' if final_count > 0 else ' '}] {final_count} images in 4_final_production")
        
        if manual_mode or phase_choice == '5':
            print("\n--- PHASE 2 ACTION MENU ---")
            print("  1. Run Full Render Pipeline (Watermark -> Upscale -> Rename -> Assembly)")
            print("  2. Run Watermark Removal Only")
            print("  3. Run Upscaler Only (Resumes from watermark folder)")
            print("  4. Run Timeline Renamer Only (Resumes from upscaled folder)")
            print("  5. Run Timeline Assembly Only (Bypasses image processing)")
            print("  0. To Exit")
            
            p2_choice = input("\nSelect action: ").strip()
            if p2_choice == '0':
                pack_system_data(current_run_dir)
                sys.exit(0)
                
            generate_video = input("\nDo you want to generate video now? (1: Yes, 0: No): ").strip()
        else:
            # If Fully Automated, force the full pipeline
            print("\n[System] Fully Automated Mode: Executing Full Render Pipeline...")
            p2_choice = '1'
            generate_video = '1'
        
        if p2_choice in ['1', '2']:
            m2.run_watermark_removal(raw_dir, wm_dir)
            
        if p2_choice in ['1', '3']:
            source_dir = wm_dir if wm_dir.exists() and any(wm_dir.iterdir()) else raw_dir
            m2.run_upscaler(source_dir, up_dir, temp_dir, target_upscaler)
            
        if p2_choice in ['1', '4']:
            source_dir = up_dir if up_dir.exists() and any(up_dir.iterdir()) else wm_dir
            if not source_dir.exists() or not any(source_dir.iterdir()):
                source_dir = raw_dir
            m2.run_renamer(source_dir, final_dir)
            
        if p2_choice in ['1', '5']:
            if generate_video == '1':
                print("\n[Engine] Assets processed. Handing off to Cinematic Timeline Engine...")
                m3.build_video(current_run_dir)
            else:
                print("\n[!] Video generation skipped. Your assets are ready !!")
                
        # --- BULLETPROOF WORKSPACE CLEANUP ---
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            print("  [Cleanup] Trashed temporary upscale files.")
            
        print("  [Cleanup] Packing internal data files into _system_data folder...")
        pack_system_data(current_run_dir)
            
        print("\n" + "="*50)
        print(" 🎉 FULLY AUTOMATED RENDER COMPLETE!")
        print("="*50 + "\n")

if __name__ == "__main__":
    main()