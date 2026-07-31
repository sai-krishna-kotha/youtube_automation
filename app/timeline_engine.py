import sys
import os
import re
import random
import subprocess
import shutil
import wave
from datetime import datetime
from pathlib import Path
from pydub import AudioSegment

# ==========================================
# SYSTEM CONFIGURATION
# ==========================================
# Your exact path to the FFmpeg executable
FFMPEG_EXE = Path("C:/Users/kotha/Downloads/important/ffmpeg/bin/ffmpeg.exe")
AudioSegment.converter = str(FFMPEG_EXE)
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
            print(f"\t\tsfx: {sfx_choice.name} added at {start_time_sec: 05.2f} for {prev_duration: 05.2f} duration")
            main_audio = main_audio.overlay(sfx, position=insert_ms)

    main_audio.export(str(mixed_audio_path), format="wav")
    print("[Audio Engine] Master track mixdown complete!")
    
    return mixed_audio_path

def build_single_video(project_dir: Path, media_mode: str, target_folder: Path, variant_tag: str = ""):
    """Assembles a single complete video file from a target directory."""
    if not FFMPEG_EXE.exists():
        print(f"\n[!] ERROR: FFmpeg not found at {FFMPEG_EXE}")
        sys.exit(1)
        
    audio_path = project_dir / "audio.wav"
    temp_dir = project_dir / f"temp_video_clips_{variant_tag}"
    channel_name = project_dir.parent.name.lower()
    
    timestamp = datetime.now().strftime("%Y-%m-%d_at_%I-%M-%p")
    tag_suffix = f"_{variant_tag}" if variant_tag else ""
    base_video_name = f"video_{timestamp}{tag_suffix}"

    # Parse media files
    if media_mode == "video":
        media_files = [f for f in target_folder.iterdir() if f.suffix.lower() in ['.mp4', '.mov']]
    else:
        media_files = [f for f in target_folder.iterdir() if f.suffix.lower() in ['.png', '.jpg', '.jpeg']]
    
    pattern = re.compile(r'\[([\d_]+)-([\d_]+)\]')
    
    parsed_data = []
    for m_file in media_files:
        match = pattern.search(m_file.name)
        if match:
            start_sec = float(match.group(1).replace('_', '.'))
            end_sec = float(match.group(2).replace('_', '.'))
            duration = max(0.5, round(end_sec - start_sec, 3))
            
            parsed_data.append({
                "path": m_file, 
                "time": start_sec, 
                "duration": duration
            })

    if not parsed_data:
        print(f"\n[!] Warning: Found no valid {media_mode} files in: {target_folder}")
        return

    parsed_data.sort(key=lambda x: x["time"])
    total_audio_time = get_audio_duration(audio_path)

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
    
    print(f"\n--- PROCESSING: {target_folder.name.upper()} ---")
    print(f"[Engine] Media Mode: {media_mode.upper()}")
    print(f"[Engine] Audio Duration: {total_audio_time:.2f} seconds")

    last_motion = ""
    incoming_transition = "hard_cut" 
    
    for i, data in enumerate(parsed_data):
        m_path = data["path"]
        duration = data["duration"]
        clip_name = f"clip_{i:03d}.mp4"
        clip_path = temp_dir / clip_name
        
        if is_raw_mode:
            out_transition = "hard_cut"
        else:
            out_transition = "hard_cut" if i == len(parsed_data) - 1 else get_random_transition()

        vf_chain = "scale=3840:2160,fps=30"
        
        if media_mode == "image" and not is_raw_mode:
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
        elif media_mode == "image" and is_raw_mode:
            motion_style = "static"
        else:
            motion_style = "video_trim" 

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

        if media_mode == "image":
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

def build_video(project_dir: Path, media_mode: str = "image"):
    upscale_dir = project_dir / "3_upscaled"
    if not upscale_dir.exists():
        print("\n[!] ERROR: '3_upscaled' folder is missing. Check your workspace.")
        return

    # Look for variant folders
    variant_folders = sorted([d for d in upscale_dir.iterdir() if d.is_dir() and d.name.startswith("variant_")])

    if variant_folders:
        print("\n" + "="*50)
        print("   🎬 INTERACTIVE DIRECTOR'S CUT")
        print("="*50)
        print("Go check your variant folders! For each scene,")
        print("enter the number of the variant you want to keep.")
        print("Your chosen clips will be copied to 'curated_master'.\n")

        curated_dir = upscale_dir / "curated_master"
        curated_dir.mkdir(exist_ok=True)

        # Grab all the filenames from the first available variant folder to iterate through
        base_files = sorted([f.name for f in variant_folders[0].iterdir() if f.is_file()])

        for clip_name in base_files:
            # Skip if we already curated this clip (useful if you stop and resume)
            if (curated_dir / clip_name).exists():
                continue

            print(f"\n[Scene] {clip_name}")
            valid_choices = []
            
            # Check which variants actually have this file
            for i in range(1, 5):
                if (upscale_dir / f"variant_{i}" / clip_name).exists():
                    valid_choices.append(str(i))
            
            if not valid_choices:
                print(f"  -> No variants found. Skipping.")
                continue

            # Force the user to pick a valid number
            choice = ""
            while choice not in valid_choices:
                choice = input(f"Which variant is best? ({'/'.join(valid_choices)}): ").strip()

            # Copy the winner to the curated folder
            src_file = upscale_dir / f"variant_{choice}" / clip_name
            shutil.copy2(src_file, curated_dir / clip_name)
            print(f"  [✓] Kept Variant {choice}")

        print("\n[System] Curation complete! Assembling your final masterpiece...")
        
        # Build the final video using ONLY the hand-picked clips
        build_single_video(project_dir, media_mode, curated_dir, variant_tag="DIRECTORS_CUT")
    else:
        # Fallback if there are no variants, just render what's in 3_upscaled
        build_single_video(project_dir, media_mode, upscale_dir)

    print(f"\n[SUCCESS] Factory Pipeline Complete!")

def main():
    base_dir = Path(__file__).resolve().parent.parent
    
    print("\n=== MEDIA TYPE SELECTION ===")
    print("1. Image Mode (Upscaled static images)")
    print("2. Video Mode (Pre-rendered Vibes AI clips)")
    m_choice = input("Select Media Type (1 or 2): ").strip()
    
    media_mode = "video" if m_choice == '2' else "image"
    
    project_dir = get_project_workspace(base_dir)
    build_video(project_dir, media_mode)

if __name__ == "__main__":
    main()