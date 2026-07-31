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
    sys_dir = run_dir / "_system_data"
    if sys_dir.exists():
        for f in sys_dir.iterdir():
            if f.is_file():
                shutil.move(str(f), str(run_dir / f.name))

def pack_system_data(run_dir: Path):
    sys_dir = run_dir / "_system_data"
    sys_dir.mkdir(exist_ok=True)
    for ext in ["*.json", "*.log"]:
        for f in run_dir.glob(ext):
            shutil.move(str(f), str(sys_dir / f.name))
    old_thumb = run_dir / "thumbnail-image-prompts.txt"
    if old_thumb.exists():
        shutil.move(str(old_thumb), str(sys_dir / old_thumb.name))
# ---------------------------------------

def setup_channel(base_dir: Path) -> tuple[Path, Path, Path, str]:
    terminal_width = os.get_terminal_size().columns if os.isatty(sys.stdout.fileno()) else 80
    print("\n" + "="*terminal_width)
    print("   THE MASTER FORGE (ZERO-TOUCH AUTOMATION)")
    print("="*terminal_width)
    
    prompt_os_dir = base_dir / "prompts"
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
        channel_name = channel_input.strip()
        if channel_name and (channel_name not in existing_channels):
            is_new = True
        else:
            print("Enter a valid Channel number or name!!")
            sys.exit(0)

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
        video_length = video_data.get('target_duration_minutes', 4)
        upscaler_model = video_data.get('upscaler_model', 'realesrgan-x4plus-anime')
        
        voice = voice_data.get('voice_model', voice_data.get('kokoro_model', 'af_bella'))
        speed = voice_data.get('speed', 1.0)
        enable_wm_remover = video_data.get('enable_watermark_remover', True)
        
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
            "upscaler_model": upscaler_model, 
            "audio_speed": speed,
            "enable_watermark_remover": enable_wm_remover,
            "request_file_used": selected_request_path.name
        }
        with open(run_dir / "run_config.json", "w") as f:
            json.dump(config, f, indent=4)
            
        print(f"\n[System] Created new workspace from {selected_request_path.name}")
        return run_dir

def main():
    load_dotenv()
    base_dir = Path(__file__).resolve().parent
    
    # --- SMART SESSION DIRECTORY ARCHITECTURE ---
    sessions_dir = base_dir / "sessions"
    sessions_dir.mkdir(exist_ok=True)
    (sessions_dir / "flow").mkdir(exist_ok=True)
    (sessions_dir / "gemini").mkdir(exist_ok=True)
    (sessions_dir / "vibes").mkdir(exist_ok=True)
    # ------------------------------------------

    master_prompts_dir, channel_dir, channel_output_base, channel_slug = setup_channel(base_dir)
    current_run_dir = get_project_workspace(channel_dir, channel_output_base)
    
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
    target_upscaler = config.get("upscaler_model", "realesrgan-x4plus-anime") 
    enable_watermark_remover = config.get("enable_watermark_remover", True)
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
    print("  1. FULLY AUTOMATED (Seamless Run)")
    print("  2. MANUAL MODE (Step-by-step with pauses)")
    print("  3. Run Phase 1 Only (Build Core Assets)")
    print("  4. Run Phase 2 Only (Generate Static Images)")
    print("  5. Run Phase 3 Only (Vibes AI Video Generation) [OPTIONAL]")
    print("  6. Run Phase 4 Only (Final Render & Assembly)")
    print("  7. Setup Gemini Authentication (Run Once)")
    print("  8. Setup Google Flow Authentication (Run Once)")
    print("  9. Setup Vibes AI Authentication (Run Once)")
    print("  0. To Exit")
    
    phase_choice = input("\nSelect Option (0-9): ").strip()
    
    if phase_choice == '0':
        pack_system_data(current_run_dir)
        sys.exit(0)
        
    # --- ONE-TIME AUTHENTICATION SETUP ---
    if phase_choice == '7':
        from app.services.image_automation import GeminiImageScraper
        scraper = GeminiImageScraper(base_dir=sessions_dir / "gemini")
        scraper.setup_session()
        sys.exit(0)

    if phase_choice == '8':
        from app.services.flow_automation import GoogleFlowScraper
        scraper = GoogleFlowScraper(base_dir=sessions_dir / "flow")
        scraper.setup_session()
        sys.exit(0)
        
    if phase_choice == '9':
        from app.services.vibes_automation import VibesAIAutomator
        scraper = VibesAIAutomator(base_dir=sessions_dir / "vibes")
        scraper.setup_session()
        sys.exit(0)
        
    # --- PIPELINE ROUTING FLAGS ---
    run_phase1 = phase_choice in ['1', '2', '3']
    run_phase2 = phase_choice in ['1', '2', '4']
    run_phase3 = phase_choice in ['2', '5']
    run_phase4 = phase_choice in ['1', '2', '6']
    manual_mode = phase_choice == '2'

    if phase_choice == '1':
        ans = input("\n[?] Do you want to include optional Vibes AI Video generation? (1: Yes, 0: No): ").strip()
        if ans == '1':
            run_phase3 = True
            
    # --- NEW: EXPLICIT MEDIA TYPE & OUTPUT SELECTION ---
    enable_ffmpeg = True
    enable_capcut = False
    media_mode_sel = "hybrid"
    
    if run_phase4:
        print("\n" + "-"*40)
        print("   SELECT MEDIA TYPE (PHASE 4)")
        print("-" * 40)
        print("  1. Image Mode (Upscaled static images)")
        print("  2. Video Mode (Pre-rendered Vibes AI clips)")
        print("  3. Hybrid Mode (Mixed Static Images + Vibes AI Videos - DEFAULT)")
        
        m_choice = input("\nSelect Media Type (1, 2, or 3) [Press Enter for 3]: ").strip()
        
        if m_choice == '1':
            media_mode_sel = "image"
        elif m_choice == '2':
            media_mode_sel = "video"
        else:
            media_mode_sel = "hybrid"

        print("\n" + "-"*40)
        print("   SELECT OUTPUT PIPELINE (PHASE 4)")
        print("-" * 40)
        print("  1. FFmpeg Master Render Only (DEFAULT)")
        print("  2. CapCut Draft Injection Only")
        print("  3. BOTH (FFmpeg Render + CapCut Draft)")
        
        p_choice = input("\nSelect Output Pipeline (1, 2, or 3) [Press Enter for 1]: ").strip()
        
        if p_choice == '2':
            enable_ffmpeg = False
            enable_capcut = True
        elif p_choice == '3':
            enable_ffmpeg = True
            enable_capcut = True

    # ==============================================================
    # PHASE 1: ASSET CREATION (Core Script, Audio, Prompts)
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
        
        script_path = current_run_dir / "final_script.txt"
        if script_path.exists():
            print("[Checkpoint] final_script.txt found. Skipping Brain...")
            with open(script_path, "r", encoding="utf-8") as f:
                final_script = f.read()
        else:
            final_script = brain.generate_script(request_yaml=raw_yaml_request, max_retries=3)
        
        # --- AUDIO CONTROL BLOCK ---
        run_audio = True
        if manual_mode:
            ans = input("\nProceed to Audio Generation? (1: Yes, 3: Skip, 0: Exit, 2: Switch to Auto): ").strip()
            if ans == '0': pack_system_data(current_run_dir); sys.exit(0)
            elif ans == '2': manual_mode = False; print("[System] Switched to Fully Automated mode.")
            elif ans == '3': run_audio = False; print("[System] Skipping Audio generation...")

        audio_path = None
        existing_audio = list(current_run_dir.glob("*.wav"))
        
        if run_audio:
            if existing_audio:
                print(f"[Checkpoint] Existing audio found ({existing_audio[0].name}). Skipping TTS Initialization...")
                audio_path = existing_audio[0] 
            else:
                print("\n[Engine] Initializing Smart TTS Pipeline...")
                from app.services.audio_service import AudioGenerationService
                audio_engine = AudioGenerationService(output_dir=current_run_dir) 
                audio_path = audio_engine.generate_audio(text=final_script, voice=audio_voice, speed=audio_speed)
        else:
            if existing_audio:
                audio_path = existing_audio[0]
        
        # --- TRANSCRIPTION CONTROL BLOCK ---
        run_transcription = True
        if manual_mode:
            ans = input("\nProceed to Transcription? (1: Yes, 3: Skip, 0: Exit, 2: Switch to Auto): ").strip()
            if ans == '0': pack_system_data(current_run_dir); sys.exit(0)
            elif ans == '2': manual_mode = False; print("[System] Switched to Fully Automated mode.")
            elif ans == '3': run_transcription = False; print("[System] Skipping Transcription...")
        
        batched_json_path = None
        existing_json = [f for f in current_run_dir.glob("*.json") if f.name not in [
            "run_config.json", 
            "metadata.json", 
            "prompts_checkpoint.json", 
            "thumbnail-image-prompts.json",
            "script_checkpoint.json"
        ]]
        
        if run_transcription:
            if existing_json:
                print(f"[Checkpoint] Transcription JSON found ({existing_json[0].name}). Skipping Whisper Initialization...")
                batched_json_path = existing_json[0] 
            else:
                if audio_path:
                    print("\n[Engine] Initializing WhisperX Transcription Pipeline...")
                    from app.services.transcription_service import TranscriptionService
                    transcriber = TranscriptionService(device="cuda", output_dir=current_run_dir) 
                    batched_json_path = transcriber.extract_and_batch(
                        audio_path=audio_path, 
                        request_yaml=raw_yaml_request,
                        min_duration=30.0, 
                        max_duration=40.0
                    )
                else:
                    print("[!] No audio found. Cannot execute Transcription pipeline.")
        else:
            if existing_json:
                batched_json_path = existing_json[0]
            
        # --- IMAGE PROMPT CONTROL BLOCK ---
        run_image_prompts = True
        if manual_mode:
            ans = input("\nProceed to Image Prompts generation? (1: Yes, 3: Skip, 0: Exit, 2: Switch to Auto): ").strip()
            if ans == '0': pack_system_data(current_run_dir); sys.exit(0)
            elif ans == '2': manual_mode = False; print("[System] Switched to Fully Automated mode.")
            elif ans == '3': run_image_prompts = False; print("[System] Skipping Image Prompt generation...")
        
        if run_image_prompts:
            if batched_json_path and audio_path:
                print("\n[Pipeline] Validating/Generating Image Prompts...")
                prompt_engine.generate_all_prompts(
                    transcription_json_path=batched_json_path, 
                    request_yaml=raw_yaml_request, 
                    script_text=final_script,
                    audio_path=audio_path
                )
            else:
                print("[!] Required inputs (JSON/Audio) missing. Cannot generate image prompts.")
        
        # --- PACKAGING ENGINE CONTROL BLOCK ---
        run_packaging = True
        if manual_mode:
            ans = input("\nProceed to Packaging Engine (Thumbnails & Metadata)? (1: Yes, 3: Skip, 0: Exit, 2: Switch to Auto): ").strip()
            if ans == '0': pack_system_data(current_run_dir); sys.exit(0)
            elif ans == '2': manual_mode = False; print("[System] Switched to Fully Automated mode.")
            elif ans == '3': run_packaging = False; print("[System] Skipping Packaging Engine...")
                
        if run_packaging:
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
                if batched_json_path:
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
                else:
                    print("[!] No transcript JSON found. Cannot generate Metadata.")
            
        raw_dir = current_run_dir / "1_raw_images"
        raw_dir.mkdir(parents=True, exist_ok=True)
        print("\n[System] Phase 1 Complete.")
        
        if not (run_phase2 or run_phase3 or run_phase4):
            print("\n[System] Packing internal data files into _system_data folder...")
            pack_system_data(current_run_dir)
            print("============================================================")
            print("CHECKPOINT REACHED: ASSET GENERATION COMPLETE")
            print("============================================================\n")
            sys.exit(0) 

        if run_phase2 and manual_mode:
            ans = input("\nProceed to Phase 2 (Auto-Generate Images via Playwright)? (1: Yes, 0: Exit, 2: Switch to Auto): ").strip()
            if ans == '0': pack_system_data(current_run_dir); sys.exit(0)
            elif ans == '2': manual_mode = False; print("[System] Switched to Fully Automated mode.")

    # ==============================================================
    # PHASE 2: STATIC IMAGE SCRAPER WITH SMART SELF-HEALING RETRIES
    # ==============================================================
    if run_phase2:
        print("\n" + "-"*40)
        print("   SELECT IMAGE AUTOMATION TOOL")
        print("-" * 40)
        print("  1. Gemini (Default)")
        print("  2. Google Flow")
        tool_sel = input("\nSelect Tool (1/2): ").strip()
        ai_tool_choice = "flow" if tool_sel == '2' else "gemini"

        print(f"\n[Engine] Initializing {ai_tool_choice.title()} Image Automation...")
        
        if ai_tool_choice == "flow":
            from app.services.flow_automation import GoogleFlowScraper
            scraper = GoogleFlowScraper(base_dir=sessions_dir / "flow")
        else:
            from app.services.image_automation import GeminiImageScraper
            scraper = GeminiImageScraper(base_dir=sessions_dir / "gemini")
        
        # --- THE AUTO-AUTH INTERCEPT ---
        if not scraper.session_directories or not scraper.session_directories[0].exists():
            print(f"\n[!] {ai_tool_choice.title()} Authentication missing! Pausing pipeline to authenticate...")
            scraper.setup_session()
            
            auth_proceed = input("\nAuthentication complete. Do you want to proceed with image generation? (1: Yes, 0: Exit): ").strip()
            if auth_proceed != '1':
                pack_system_data(current_run_dir)
                sys.exit(0)
        # -------------------------------

        prompts_file = current_run_dir / "time_stamped_prompts.txt"
        raw_output_dir = current_run_dir / "1_raw_images"
        raw_output_dir.mkdir(parents=True, exist_ok=True)
        
        if not prompts_file.exists():
            print(f"\n[!] ERROR: Cannot find {prompts_file.name}. Ensure Phase 1 ran successfully.")
            pack_system_data(current_run_dir)
            sys.exit(1)
            
        max_repair_passes = 10
        
        for pass_num in range(1, max_repair_passes + 1):
            print(f"\n[Engine] Image Generation Pass {pass_num}/{max_repair_passes}...")
            
            scraper.generate_images(input_file=prompts_file, output_dir=raw_output_dir)
            
            expected_prompts = []
            with open(prompts_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        match = re.search(r"\[([\d_]+)-([\d_]+)\]", line)
                        if match:
                            start_s, end_s = match.groups()
                            filename = f"[{start_s}-{end_s}]_image.png"
                            expected_prompts.append((filename, line.strip()))
                            
            expected_count = len(expected_prompts)
            missing_prompts_file = current_run_dir / "missing_prompts_retry.txt"
            missing_items = [item for item in expected_prompts if not (raw_output_dir / item[0]).exists()]
            
            actual_count = expected_count - len(missing_items)
            
            if len(missing_items) == 0:
                print(f"\n[System] Verification Passed! All {actual_count}/{expected_count} images successfully generated.")
                if missing_prompts_file.exists():
                    missing_prompts_file.unlink() 
                break
            else:
                print(f"\n[!] Verification Warning: Missing {len(missing_items)} out of {expected_count} images.")
                if pass_num < max_repair_passes:
                    print(f"[!] Generating temporary patch file for the {len(missing_items)} missing clips...")
                    with open(missing_prompts_file, 'w', encoding='utf-8') as mf:
                        for _, full_line in missing_items:
                            mf.write(full_line + "\n")
                            
                    print(f"[!] Re-running scraper specifically for missing assets (Attempt {pass_num + 1})...")
                    scraper.generate_images(input_file=missing_prompts_file, output_dir=raw_output_dir)
                    if missing_prompts_file.exists():
                        missing_prompts_file.unlink()
                else:
                    print("[!] Max repair passes reached. Proceeding with currently available images.")
        
        if not (run_phase3 or run_phase4):
            print("\n[System] Packing internal data files into _system_data folder...")
            pack_system_data(current_run_dir)
            print("\n[System] Phase 2 Complete. Exiting as requested.")
            sys.exit(0) 
            
        if run_phase3 and manual_mode:
            ans = input("\nProceed to Phase 3 (Vibes AI Video Generation)? (1: Yes, 0: Exit, 2: Switch to Auto): ").strip()
            if ans == '0': pack_system_data(current_run_dir); sys.exit(0)
            elif ans == '2': manual_mode = False; print("[System] Switched to Fully Automated mode.")

    # ==============================================================
    # PHASE 3: VIBES AI VIDEO GENERATION [OPTIONAL]
    # ==============================================================
    if run_phase3:
        print("\n" + "="*50)
        print("   PHASE 3: VIBES AI VIDEO GENERATION")
        print("="*50)
        
        from app.services.vibes_prompt_service import VibesPromptService
        from app.services.vibes_automation import VibesAIAutomator
        from app.services.llm_client import GeminiClient
        
        # --- THE FIX: Ignore system config files and specifically grab the transcription batch file ---
        existing_jsons = [f for f in current_run_dir.glob("*.json") if f.name not in [
            "run_config.json", 
            "metadata.json", 
            "prompts_checkpoint.json", 
            "thumbnail-image-prompts.json",
            "script_checkpoint.json",
            "animation_prompts_checkpoint.json"
        ]]
        transcription_json = existing_jsons[0] if existing_jsons else None
        
        if not transcription_json:
            print("\n[!] Failed to find transcription JSON. Aborting Phase 3.")
            sys.exit(1)
            
        static_prompts_file = current_run_dir / "time_stamped_prompts.txt"
        raw_images_dir = current_run_dir / "1_raw_images"
        upscale_dir = current_run_dir / "3_upscaled" # Target directory for videos
        
        # 1. Generate Animation Prompts
        llm = GeminiClient()
        prompt_service = VibesPromptService(llm_client=llm, output_dir=current_run_dir, master_prompts_dir=master_prompts_dir)
        animation_prompts_file = prompt_service.generate_animation_prompts(
            transcription_json_path=transcription_json,
            static_prompts_path=static_prompts_file
        )
        
        if not animation_prompts_file:
            print("\n[!] Failed to generate animation prompts. Aborting Phase 3.")
            pack_system_data(current_run_dir)
            sys.exit(1)
            
        # 2. Initialize Vibes Automator
        print("\n[Engine] Initializing Vibes AI Automation...")
        vibes_scraper = VibesAIAutomator(base_dir=sessions_dir / "vibes")
        
        # --- THE AUTO-AUTH INTERCEPT ---
        if not vibes_scraper.session_dirs[0].exists():
            print(f"\n[!] Vibes AI Authentication missing! Pausing pipeline to authenticate...")
            vibes_scraper.setup_session()
            
            auth_proceed = input("\nAuthentication complete. Do you want to proceed with video generation? (1: Yes, 0: Exit): ").strip()
            if auth_proceed != '1':
                pack_system_data(current_run_dir)
                sys.exit(0)
        # --------------------------------
        
        # 3. Generate Videos
        vibes_scraper.generate_animations(
            prompts_file=animation_prompts_file,
            image_dir=raw_images_dir,
            output_dir=upscale_dir
        )
        
        if not run_phase4:
            print("\n[System] Packing internal data files into _system_data folder...")
            pack_system_data(current_run_dir)
            print("\n[System] Phase 3 Complete. Exiting as requested.")
            sys.exit(0)
            
        if run_phase4 and manual_mode:
            ans = input("\nProceed to Phase 4 (Final Render Pipeline)? (1: Yes, 0: Exit, 2: Switch to Auto): ").strip()
            if ans == '0': pack_system_data(current_run_dir); sys.exit(0)
            elif ans == '2': manual_mode = False; print("[System] Switched to Fully Automated mode.")

    # ==============================================================
    # PHASE 4: FINAL RENDER
    # ==============================================================
    if run_phase4:
        print("\n[Engine] Initializing Phase 4 (Asset Processing & Render)...")
        
        raw_dir = current_run_dir / "1_raw_images"
        wm_dir = current_run_dir / "2_watermark_removed"
        up_dir = current_run_dir / "3_upscaled"
        final_dir = current_run_dir / "4_final_production"
        temp_dir = current_run_dir / "temp_upscale"
        
        raw_count = len([f for f in raw_dir.iterdir() if f.is_file()]) if raw_dir.exists() else 0
        wm_count = len([f for f in wm_dir.iterdir() if f.is_file()]) if wm_dir.exists() else 0
        
        # Count files across upscaled dir (including subfolders for AI variants)
        up_count = 0
        if up_dir.exists():
            for root, dirs, files in os.walk(up_dir):
                up_count += len([f for f in files if not f.startswith('.')])
                
        final_count = len([f for f in final_dir.iterdir() if f.is_file()]) if final_dir.exists() else 0
        
        if raw_count == 0 and wm_count == 0 and up_count == 0 and final_count == 0:
            print("\n[!] ERROR: '1_raw_images' is completely empty! Run Phase 2 first.")
            pack_system_data(current_run_dir)
            sys.exit(1)
            
        print("\n--- FACTORY CHECKPOINT STATUS ---")
        print(f"  [{'✓' if raw_count > 0 else ' '}] {raw_count} images in 1_raw_images")
        print(f"  [{'✓' if wm_count > 0 else ' '}] {wm_count} files in 2_watermark_removed")
        print(f"  [{'✓' if up_count > 0 else ' '}] {up_count} files in 3_upscaled")
        print(f"  [{'✓' if final_count > 0 else ' '}] {final_count} files in 4_final_production")
        
        if manual_mode or phase_choice == '6':
            print("\n--- PHASE 4 ACTION MENU ---")
            print("  1. Run Full Render Pipeline (Watermark -> Upscale -> Rename -> Assembly)")
            print("  2. Run Watermark Removal Only")
            print("  3. Run Upscaler Only (Resumes from watermark folder)")
            print("  4. Run Timeline Renamer Only (Resumes from upscaled folder)")
            print("  5. Run Timeline Assembly Only (Bypasses image processing)")
            print("  0. To Exit")
            
            p4_choice = input("\nSelect action: ").strip()
            if p4_choice == '0':
                pack_system_data(current_run_dir)
                sys.exit(0)
                
            generate_video = input("\nDo you want to generate video now? (1: Yes, 0: No): ").strip()
        else:
            print("\n[System] Fully Automated Mode: Executing Full Render Pipeline...")
            p4_choice = '1'
            generate_video = '1'
            
            # SMART BYPASS: Skip static image upscaling if we are working with pre-rendered variants
            if media_mode_sel in ["video", "hybrid"] and (run_phase3 or (up_dir.exists() and any(d.name.startswith("variant_") for d in up_dir.iterdir() if d.is_dir()))):
                print("\n[System] Pre-rendered variants detected for Video/Hybrid mode. Bypassing static image upscaling...")
                p4_choice = '5' # Jump straight to Assembly Engine!
        
        if p4_choice in ['1', '2']:
            if manual_mode:
                current_state = "1" if enable_watermark_remover else "0"
                override = input(f"\nRun watermark remover? (1: Yes, 0: No) [Current: {current_state}]: ").strip()
                if override == '0':
                    enable_watermark_remover = False
                elif override == '1':
                    enable_watermark_remover = True

            if enable_watermark_remover:
                m2.run_watermark_removal(raw_dir, wm_dir)
            else:
                print("\n[System] Watermark removal toggled OFF. Bypassing directly to upscaler...")
            
        if p4_choice in ['1', '3']:
            source_dir = wm_dir if wm_dir.exists() and any(wm_dir.iterdir()) else raw_dir
            m2.run_upscaler(source_dir, up_dir, temp_dir, target_upscaler)
            
        if p4_choice in ['1', '4']:
            source_dir = up_dir if up_dir.exists() and any(up_dir.iterdir()) else wm_dir
            if not source_dir.exists() or not any(source_dir.iterdir()):
                source_dir = raw_dir
            m2.run_renamer(source_dir, final_dir)
            
        if p4_choice in ['1', '5']:
            if generate_video == '1':
                print("\n[Engine] Assets processed. Handing off to Cinematic Timeline Engine...")
                
                # Verify that the required files actually exist in the up_dir based on user's manual selection
                has_images = False
                has_videos = False
                if up_dir.exists():
                    for root, dirs, files in os.walk(up_dir):
                        for f in files:
                            ext = f.lower().split('.')[-1]
                            if ext in ['png', 'jpg', 'jpeg']:
                                has_images = True
                            elif ext in ['mp4', 'mov']:
                                has_videos = True
                
                # Safety checks to gracefully catch empty/missing folders instead of crashing FFmpeg
                if media_mode_sel == "video" and not has_videos:
                    print(f"\n[!] ERROR: You selected 'Video Mode', but no video files (.mp4/.mov) were found in '{up_dir.name}'.")
                    print("  -> Skipping timeline assembly. Please run Vibes AI (Phase 3) first!")
                elif media_mode_sel == "image" and not has_images:
                    print(f"\n[!] ERROR: You selected 'Image Mode', but no image files (.png/.jpg) were found in '{up_dir.name}'.")
                    print("  -> Skipping timeline assembly. Please ensure Phase 2/Upscaler ran successfully.")
                elif media_mode_sel == "hybrid" and not (has_images or has_videos):
                    print(f"\n[!] ERROR: You selected 'Hybrid Mode', but no media files were found in '{up_dir.name}'.")
                    print("  -> Skipping timeline assembly.")
                else:
                    m3.build_video(current_run_dir, media_mode=media_mode_sel, enable_capcut=enable_capcut, enable_ffmpeg=enable_ffmpeg)
            else:
                print("\n[!] Video generation skipped. Your assets are ready !!")
                
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