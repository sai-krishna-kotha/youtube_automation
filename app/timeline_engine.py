import sys
import os
import re
import random
import subprocess
import shutil
import wave
import json
import uuid
import time
from datetime import datetime
from pathlib import Path
from pydub import AudioSegment

# ==========================================
# SYSTEM CONFIGURATION
# ==========================================
# Your exact path to the FFmpeg executable
FFMPEG_EXE = Path("C:/Users/kotha/Downloads/important/ffmpeg/bin/ffmpeg.exe")
AudioSegment.converter = str(FFMPEG_EXE)

# --- NEW: SHORT VIDEO HANDLING ---
# Options: "slomo" (stretches video to fit gap) OR "freeze" (holds last frame)
VIDEO_EXTEND_MODE = "slomo" 
# ==========================================

def get_project_workspace(base_dir: Path) -> Path:
    """CLI to select the channel and project."""
    terminal_width = os.get_terminal_size().columns if os.isatty(sys.stdout.fileno()) else 80
    print("\n" + "="*terminal_width)
    print("   ADVANCED CINEMATIC ASSEMBLY ENGINE (MODULE 3)")
    print("="*terminal_width)
    
    prompt_base = base_dir / "prompt_docs"
    existing_channels = [d.name for d in prompt_base.iterdir() if d.is_dir()]
    
    if not existing_channels:
        print("[!] No channels found. Run Module 1 first.")
        sys.exit(1)
        
    print("\nSelect Channel:")
    for idx, ch in enumerate(existing_channels):
        print(f"  {idx + 1}. {ch}")
        
    c_idx = int(input("\nChannel Number: ").strip()) - 1
    channel_slug = existing_channels[c_idx]
    
    channel_output_base = base_dir / "assets" / "outputs" / channel_slug
    existing_projects = [d for d in channel_output_base.iterdir() if d.is_dir()]
    
    if not existing_projects:
        print(f"[!] No projects found in {channel_slug}.")
        sys.exit(1)
        
    print(f"\nSelect Project in '{channel_slug}':")
    for idx, proj in enumerate(existing_projects):
        print(f"  {idx + 1}. {proj.name}")
        
    p_idx = int(input("\nProject Number: ").strip()) - 1
    return existing_projects[p_idx]

def get_audio_duration(wav_path: Path) -> float:
    with wave.open(str(wav_path), 'r') as f:
        frames = f.getnframes()
        rate = f.getframerate()
        return frames / float(rate)

def get_video_duration(video_path: Path) -> float:
    """Uses FFmpeg to extract the exact actual duration of a video file."""
    cmd = f'"{FFMPEG_EXE}" -i "{video_path}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
    if match:
        h, m, s = match.groups()
        return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0

def get_smart_motion_style(last_style: str) -> str:
    """Breathing Camera: Alternates Zooms and Pans"""
    if last_style in ["zoom_in", "zoom_out"]:
        return random.choice(["pan_lr", "pan_rl"])
    elif last_style in ["pan_lr", "pan_rl"]:
        return random.choice(["zoom_in", "zoom_out"])
    else:
        return "zoom_in"

def get_random_transition() -> str:
    """Weighted randomness for transitions. 40% black fade, 40% white fade, 20% hard cuts."""
    choices = ["hard_cut", "flash_white", "flash_white", "fade_black", "fade_black"]
    return random.choice(choices)

def mix_sfx_track(parsed_data, master_audio_path: Path, temp_dir: Path, base_dir: Path) -> Path:
    """Dynamically overlays sound effects onto the master audio track."""
    sfx_dir = base_dir / "assets" / "sfx"
    mixed_audio_path = temp_dir / "mixed_audio.wav"
    
    if not sfx_dir.exists():
        return master_audio_path
        
    sfx_files = list(sfx_dir.glob("*.wav")) + list(sfx_dir.glob("*.mp3"))
    if not sfx_files:
        return master_audio_path

    print("\n[Audio Engine] Mixing cinematic sound effects into master track...")
    
    main_audio = AudioSegment.from_file(str(master_audio_path))
    
    for i in range(1, len(parsed_data)):
        prev_duration = parsed_data[i-1]["duration"]
        start_time_sec = parsed_data[i]["time"]
        
        if prev_duration > 0.5:
            sfx_choice = random.choice(sfx_files)
            sfx = AudioSegment.from_file(str(sfx_choice))
            sfx = sfx - 4 
            
            insert_ms = int(start_time_sec * 1000) - 200 
            insert_ms = max(0, insert_ms)
            main_audio = main_audio.overlay(sfx, position=insert_ms)

    main_audio.export(str(mixed_audio_path), format="wav")
    print("[Audio Engine] Master track mixdown complete!")
    
    return mixed_audio_path

def generate_capcut_id():
    """Generates a CapCut-compliant UUID."""
    import uuid
    return str(uuid.uuid4()).upper()

def export_capcut_draft(parsed_data, project_dir: Path, audio_path: Path):
    """Duplicates a blank CapCut template and safely injects timeline data with native UI physics."""
    import json
    import time
    import shutil
    import os
    
    print("\n[CapCut Engine] Initializing Golden Template Injection...")
    
    local_appdata = os.getenv('LOCALAPPDATA')
    if not local_appdata:
        print("  [!] ERROR: Could not locate LOCALAPPDATA environment variable.")
        return

    base_drafts_path = Path(local_appdata) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
    template_path = base_drafts_path / "Golden_Template"
    
    if not template_path.exists():
        print("  [!] ERROR: 'Golden_Template' not found in CapCut!")
        print("  [!] Please create a blank project named 'Golden_Template' and close CapCut.")
        return

    project_name = f"AutoDraft_{project_dir.name}"
    draft_path = base_drafts_path / project_name

    if draft_path.exists():
        print(f"  [!] Draft '{project_name}' already exists. Overwriting...")
        shutil.rmtree(draft_path)

    try:
        shutil.copytree(template_path, draft_path)
        
        meta_file = draft_path / "draft_meta_info.json"
        if meta_file.exists():
            with open(meta_file, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
                
            meta_data["draft_name"] = project_name
            meta_data["draft_root_path"] = str(draft_path.parent)
            meta_data["draft_fold_path"] = str(draft_path)
            meta_data["tm_draft_modified"] = int(time.time() * 1000000)
            
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=4)

        content_file = draft_path / "draft_content.json"
        if content_file.exists():
            with open(content_file, "r", encoding="utf-8") as f:
                content_data = json.load(f)

            content_data["materials"] = {
                "videos": [],
                "audios": [],
                "canvases": [],
                "speeds": []
            }

            video_segments = []
            audio_segments = []
            current_time_us = 0

            for clip in parsed_data:
                clip_id = generate_capcut_id()
                canvas_id = generate_capcut_id()
                speed_id = generate_capcut_id()
                
                duration_us = int(clip["duration"] * 1000000)
                file_path_str = str(clip["path"].resolve())
                
                content_data["materials"]["videos"].append({
                    "id": clip_id,
                    "type": "video",
                    "path": file_path_str,
                    "duration": duration_us,
                    "material_name": clip["path"].name,
                    "width": 1920,  
                    "height": 1080, 
                    "volume": 1.0 
                })
                
                content_data["materials"]["canvases"].append({
                    "id": canvas_id,
                    "type": "canvas_color",
                    "color": "",
                    "blur": 0.0,
                    "album_image": "",
                    "image": "",
                    "image_id": "",
                    "image_name": "",
                    "source_platform": 0,
                    "team_id": "",
                    "material_name": file_path_str
                })

                content_data["materials"]["speeds"].append({
                    "id": speed_id,
                    "type": "speed",
                    "mode": 0,
                    "speed": 1.0,
                    "curve_speed": None,
                    "material_name": file_path_str
                })
                
                video_segments.append({
                    "id": generate_capcut_id(),
                    "material_id": clip_id,
                    "source_timerange": {"start": 0, "duration": duration_us},
                    "target_timerange": {"start": current_time_us, "duration": duration_us},
                    "speed": 1.0,
                    "volume": 1.0, 
                    "visible": True,
                    "clip": {        
                        "alpha": 1.0,
                        "flip": {"horizontal": False, "vertical": False},
                        "rotation": 0.0,
                        "scale": {"x": 1.0, "y": 1.0},
                        "transform": {"x": 0.0, "y": 0.0}
                    },
                    "extra_material_refs": [canvas_id, speed_id]
                })
                current_time_us += duration_us

            audio_id = generate_capcut_id()
            audio_duration_us = int(get_audio_duration(audio_path) * 1000000)
            audio_path_str = str(audio_path.resolve())
            
            content_data["materials"]["audios"].append({
                "id": audio_id,
                "type": "audio",
                "path": audio_path_str,
                "duration": audio_duration_us,
                "material_name": audio_path.name,
                "volume": 1.0
            })
            
            audio_segments.append({
                "id": generate_capcut_id(),
                "material_id": audio_id,
                "source_timerange": {"start": 0, "duration": audio_duration_us},
                "target_timerange": {"start": 0, "duration": audio_duration_us},
                "speed": 1.0,
                "volume": 1.0,
                "visible": True,
                "clip": {
                    "alpha": 1.0,
                    "flip": {"horizontal": False, "vertical": False},
                    "rotation": 0.0,
                    "scale": {"x": 1.0, "y": 1.0},
                    "transform": {"x": 0.0, "y": 0.0}
                },
                "extra_material_refs": []  
            })

            content_data["tracks"] = [
                {
                    "attribute": 0,
                    "flag": 0,
                    "id": generate_capcut_id(), 
                    "is_default_name": True,
                    "name": "",
                    "segments": video_segments,
                    "type": "video"
                },
                {
                    "attribute": 0,
                    "flag": 0,
                    "id": generate_capcut_id(), 
                    "is_default_name": True,
                    "name": "",
                    "segments": audio_segments,
                    "type": "audio"
                }
            ]
            
            content_data["duration"] = max(current_time_us, audio_duration_us)

            with open(content_file, "w", encoding="utf-8") as f:
                json.dump(content_data, f, indent=4)

        print(f"  [+] Golden Template successfully hijacked for: {project_name} (Using Golden UIDs)")
        print(f"  [SUCCESS] Open CapCut Desktop to verify your fully working draft!")
        
    except Exception as e:
        print(f"  [!] Golden Template Injection Failed: {e}")

def build_single_video(project_dir: Path, media_mode: str, target_folder: Path, variant_tag: str = "", enable_capcut: bool = False, enable_ffmpeg: bool = True):
    """Assembles a single complete video file from a target directory supporting Hybrid (Video + Image) mode."""
    audio_path = project_dir / "audio.wav"
    temp_dir = project_dir / f"temp_video_clips_{variant_tag}"
    channel_name = project_dir.parent.name.lower()
    
    timestamp = datetime.now().strftime("%Y-%m-%d_at_%I-%M-%p")
    tag_suffix = f"_{variant_tag}" if variant_tag else ""
    base_video_name = f"video_{timestamp}{tag_suffix}"

    # DYNAMIC FILE DISCOVERY: Collects both videos and images
    valid_exts = ['.mp4', '.mov', '.png', '.jpg', '.jpeg']
    if media_mode == "video":
        valid_exts = ['.mp4', '.mov']
    elif media_mode == "image":
        valid_exts = ['.png', '.jpg', '.jpeg']

    all_files = [f for f in target_folder.iterdir() if f.suffix.lower() in valid_exts]
    pattern = re.compile(r'\[([\d_]+)-([\d_]+)\]')
    
    timestamp_map = {}
    for m_file in all_files:
        match = pattern.search(m_file.name)
        if match:
            ts_key = match.group(0)
            start_sec = float(match.group(1).replace('_', '.'))
            end_sec = float(match.group(2).replace('_', '.'))
            duration = max(0.5, round(end_sec - start_sec, 3))
            is_vid = m_file.suffix.lower() in ['.mp4', '.mov']
            
            # Prefer video files over images if both exist for the same timestamp block
            if ts_key in timestamp_map:
                if is_vid and not timestamp_map[ts_key]["is_video"]:
                    timestamp_map[ts_key] = {
                        "path": m_file, 
                        "time": start_sec, 
                        "duration": duration,
                        "is_video": True
                    }
            else:
                timestamp_map[ts_key] = {
                    "path": m_file, 
                    "time": start_sec, 
                    "duration": duration,
                    "is_video": is_vid
                }

    parsed_data = list(timestamp_map.values())

    if not parsed_data:
        print(f"\n[!] Warning: Found no valid files in: {target_folder}")
        return

    parsed_data.sort(key=lambda x: x["time"])
    total_audio_time = get_audio_duration(audio_path)

    print(f"\n--- PROCESSING: {target_folder.name.upper()} ---")
    print(f"[Engine] Media Mode: {media_mode.upper()}")
    print(f"[Engine] Audio Duration: {total_audio_time:.2f} seconds")

    if enable_capcut:
        export_capcut_draft(parsed_data, project_dir, audio_path)

    if not enable_ffmpeg:
        print("\n[Engine] FFmpeg rendering bypassed as requested. Factory pipeline complete!")
        return

    if not FFMPEG_EXE.exists():
        print(f"\n[!] ERROR: FFmpeg not found at {FFMPEG_EXE}")
        sys.exit(1)

    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(exist_ok=True)
    base_dir = project_dir.parent.parent.parent.parent
    
    sfx_enabled_channels = ["tech", "huh", "doodle", "stick"]
    audio_tracks = [] 
    
    if any(keyword in channel_name for keyword in sfx_enabled_channels):
        print(f"\n[Audio Engine] Fast-paced channel detected ({channel_name}). Enabling SFX...")
        mixed_audio_path = mix_sfx_track(parsed_data, audio_path, temp_dir, base_dir)
        audio_tracks.append((mixed_audio_path, "_WITH_SFX"))
        audio_tracks.append((audio_path, "_CLEAN"))
    else:
        print(f"\n[Audio Engine] Storytelling channel detected ({channel_name}). Bypassing SFX for clean audio.")
        audio_tracks.append((audio_path, "_CLEAN"))
        
    blueprint_lines = []
    is_raw_mode = any(keyword in channel_name for keyword in ["huh", "tech", "doodle", "stick"])
    
    last_motion = ""
    incoming_transition = "hard_cut" 
    
    for i, data in enumerate(parsed_data):
        m_path = data["path"]
        duration = data["duration"]
        is_clip_video = data["is_video"]
        clip_name = f"clip_{i:03d}.mp4"
        clip_path = temp_dir / clip_name
        
        if is_raw_mode:
            out_transition = "hard_cut"
        else:
            out_transition = "hard_cut" if i == len(parsed_data) - 1 else get_random_transition()

        vf_chain = "scale=3840:2160,fps=30"
        
        if not is_clip_video and not is_raw_mode:
            motion_style = get_smart_motion_style(last_motion)
            last_motion = motion_style
            total_frames = int(duration * 30)

            if motion_style == "zoom_in":
                motion_filter = f"zoompan=z='min(1.5,1.02+0.0003*on)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30"
            elif motion_style == "zoom_out":
                motion_filter = f"zoompan=z='max(1.001,1.15-0.0003*on)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30"
            elif motion_style == "pan_lr":
                motion_filter = f"zoompan=z='1.08':d={total_frames}:x='min(iw-iw/zoom,0.4*on)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30"
            else: 
                motion_filter = f"zoompan=z='1.08':d={total_frames}:x='max(0,(iw-iw/zoom)-0.4*on)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30"

            vf_chain = f"scale=8000:4500,{motion_filter},noise=alls=2:allf=t"
            
        elif is_clip_video:
            motion_style = "video_trim" 
            actual_vid_dur = get_video_duration(m_path)
            
            # --- THE FIX: SMART SHORT VIDEO EXTENSION ---
            if 0 < actual_vid_dur < duration:
                if VIDEO_EXTEND_MODE == "slomo":
                    stretch_factor = duration / actual_vid_dur
                    vf_chain += f",setpts={stretch_factor}*PTS"
                    motion_style = "video_slomo"
                elif VIDEO_EXTEND_MODE == "freeze":
                    vf_chain += ",tpad=stop_mode=clone:stop=-1"
                    motion_style = "video_freeze"
        else:
            motion_style = "static"

        if not is_raw_mode:
            fade_duration = 0.3
            fade_start = max(0.0, duration - fade_duration)

            if incoming_transition == "flash_white":
                vf_chain += f",fade=t=in:st=0:d={fade_duration}:color=white"
            elif incoming_transition == "fade_black":
                vf_chain += f",fade=t=in:st=0:d={fade_duration}:color=black"

            if out_transition == "flash_white":
                vf_chain += f",fade=t=out:st={fade_start}:d={fade_duration}:color=white"
            elif out_transition == "fade_black":
                vf_chain += f",fade=t=out:st={fade_start}:d={fade_duration}:color=black"

        sys.stdout.write(f"\r  -> [{motion_style.upper()}] | Ends w/ {out_transition} | Rendering clip {i+1}/{len(parsed_data)} ({duration}s)...")
        sys.stdout.flush()

        if not is_clip_video:
            cmd = (
                f'"{FFMPEG_EXE}" -loop 1 -i "{m_path}" '
                f'-vf "{vf_chain}" -c:v h264_nvenc -b:v 30M -maxrate 35M -bufsize 35M -t {duration} -pix_fmt yuv420p -y "{clip_path}"'
            )
        else:
            cmd = (
                f'"{FFMPEG_EXE}" -i "{m_path}" '
                f'-vf "{vf_chain}" -c:v h264_nvenc -b:v 30M -maxrate 35M -bufsize 35M -t {duration} -pix_fmt yuv420p -y "{clip_path}"'
            )
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"\n\n[FATAL ERROR] FFmpeg failed on {clip_name}:")
            print(result.stderr)
            sys.exit(1)
            
        blueprint_lines.append(f"file '{clip_path.name}'")
        incoming_transition = out_transition

    print("\n  [+] Micro-clips rendered successfully.")

    blueprint_path = temp_dir / "blueprint.txt"
    with open(blueprint_path, "w") as f:
        f.write("\n".join(blueprint_lines))

    for audio_track_path, suffix in audio_tracks:
        final_output = project_dir / f"{base_video_name}{suffix}.mp4"
        
        concat_cmd = (
            f'"{FFMPEG_EXE}" -f concat -safe 0 -i "{blueprint_path}" -i "{audio_track_path}" '
            f'-c:v copy -c:a aac -shortest -y "{final_output}"'
        )
        
        final_result = subprocess.run(concat_cmd, shell=True, capture_output=True, text=True)
        if final_result.returncode != 0:
            print(f"\n[FATAL ERROR] FFmpeg Concat Failed for {suffix}:")
            print(final_result.stderr)
            sys.exit(1)
            
        print(f"  [SUCCESS] Master Video Saved: {final_output.name}")

    shutil.rmtree(temp_dir)

def build_video(project_dir: Path, media_mode: str = "hybrid", enable_capcut: bool = False, enable_ffmpeg: bool = True, bulk_choice: str = "M"):
    upscale_dir = project_dir / "3_upscaled"
    if not upscale_dir.exists():
        print("\n[!] ERROR: '3_upscaled' folder is missing. Check your workspace.")
        return

    variant_folders = sorted([d for d in upscale_dir.iterdir() if d.is_dir() and d.name.startswith("variant_")])

    if variant_folders:
        print("\n" + "="*50)
        print("   🎬 INTERACTIVE DIRECTOR'S CUT")
        print("="*50)
        
        curated_dir = upscale_dir / "curated_master"
        curated_dir.mkdir(exist_ok=True)
        base_files = sorted([f.name for f in variant_folders[0].iterdir() if f.is_file()])

        if bulk_choice not in ["1", "2", "3", "4", "M"]:
            print("How would you like to select your variants?")
            while bulk_choice not in ["1", "2", "3", "4", "M"]:
                bulk_choice = input("Enter a number (1-4) to Auto-Apply to ALL scenes, OR press 'M' for Manual Selection: ").strip().upper()

        if bulk_choice in ["1", "2", "3", "4"]:
            print(f"\n[System] Bulk Auto-Applying Variant {bulk_choice} to all scenes...")
            for clip_name in base_files:
                if (curated_dir / clip_name).exists():
                    continue
                
                choice = bulk_choice
                if not (upscale_dir / f"variant_{choice}" / clip_name).exists():
                    print(f"  [!] Variant {choice} missing for {clip_name}. Falling back to Variant 1.")
                    choice = "1"
                    
                src_file = upscale_dir / f"variant_{choice}" / clip_name
                shutil.copy2(src_file, curated_dir / clip_name)
                print(f"  [Bulk] Copied Variant {choice} -> {clip_name}")
        else:
            print("\n[System] Initiating Manual Clip-by-Clip Selection...")
            for clip_name in base_files:
                if (curated_dir / clip_name).exists():
                    continue

                print(f"\n[Scene] {clip_name}")
                valid_choices = []
                
                for i in range(1, 5):
                    if (upscale_dir / f"variant_{i}" / clip_name).exists():
                        valid_choices.append(str(i))
                
                if not valid_choices:
                    print(f"  -> No variants found. Skipping.")
                    continue

                choice = ""
                while choice not in valid_choices:
                    choice = input(f"Which variant is best? ({'/'.join(valid_choices)}): ").strip()

                src_file = upscale_dir / f"variant_{choice}" / clip_name
                shutil.copy2(src_file, curated_dir / clip_name)
                print(f"  [✓] Kept Variant {choice}")

        print("\n[System] Curation complete! Assembling your final masterpiece...")
        build_single_video(project_dir, media_mode, curated_dir, variant_tag="DIRECTORS_CUT", enable_capcut=enable_capcut, enable_ffmpeg=enable_ffmpeg)
    else:
        build_single_video(project_dir, media_mode, upscale_dir, enable_capcut=enable_capcut, enable_ffmpeg=enable_ffmpeg)

    if enable_ffmpeg:
        print(f"\n[SUCCESS] Factory Pipeline Complete!")

def main():
    base_dir = Path(__file__).resolve().parent.parent
    
    print("\n=== MEDIA TYPE SELECTION ===")
    print("1. Image Mode (Upscaled static images)")
    print("2. Video Mode (Pre-rendered Vibes AI clips)")
    print("3. Hybrid Mode (Mixed Static Images + Vibes AI Videos - DEFAULT)")
    m_choice = input("Select Media Type (1, 2, or 3) [Press Enter for 3]: ").strip()
    
    print("\n=== OUTPUT PIPELINE SELECTION ===")
    print("1. FFmpeg Master Render Only (DEFAULT)")
    print("2. CapCut Draft Injection Only")
    print("3. BOTH (FFmpeg Render + CapCut Draft)")
    p_choice = input("Select Output Pipeline (1, 2, or 3) [Press Enter for 1]: ").strip()
    
    if m_choice == '1':
        media_mode = "image"
    elif m_choice == '2':
        media_mode = "video"
    else:
        media_mode = "hybrid"
    
    enable_ffmpeg = True
    enable_capcut = False
    
    if p_choice == '2':
        enable_ffmpeg = False
        enable_capcut = True
    elif p_choice == '3':
        enable_ffmpeg = True
        enable_capcut = True
        
    project_dir = get_project_workspace(base_dir)
    
    print("\n=== DIRECTOR'S CUT MODE ===")
    bulk_choice = input("Enter variant (1-4) to Auto-Apply, OR press 'M' for Manual [Press Enter for M]: ").strip().upper()
    if bulk_choice not in ["1", "2", "3", "4"]:
        bulk_choice = "M"
        
    build_video(project_dir, media_mode, enable_capcut, enable_ffmpeg, bulk_choice)

if __name__ == "__main__":
    main()