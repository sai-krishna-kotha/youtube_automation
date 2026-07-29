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

def build_video(project_dir: Path):
    if not FFMPEG_EXE.exists():
        print(f"\n[!] ERROR: FFmpeg not found at {FFMPEG_EXE}")
        sys.exit(1)
    raw_images = project_dir / "1_raw_images"
    upscale_dir = project_dir / "3_upscaled"
    audio_path = project_dir / "audio.wav"
    temp_dir = project_dir / "temp_video_clips"
    channel_name = project_dir.parent.name.lower()
    
    timestamp = datetime.now().strftime("%Y-%m-%d_at_%I-%M-%p")    
    base_video_name = f"video_{timestamp}"

    if not upscale_dir.exists() or not any(upscale_dir.iterdir()):
        print("\n[!] ERROR: '3_upscaled' folder is empty. Run Module 2 first.")
        return

    # --- 1. PARSE TIMESTAMPS & EXACT DURATIONS ---
    images = [f for f in upscale_dir.iterdir() if f.suffix.lower() in ['.png', '.jpg', '.jpeg']]
    
    # FIXED: Made the brackets strictly required. 
    # This prevents the regex from accidentally grabbing hyphenated numbers (like resolutions) at the end of filenames.
    pattern = re.compile(r'\[([\d_]+)-([\d_]+)\]')
    
    parsed_data = []
    for img in images:
        match = pattern.search(img.name)
        if match:
            start_sec = float(match.group(1).replace('_', '.'))
            end_sec = float(match.group(2).replace('_', '.'))
            
            duration = max(0.5, round(end_sec - start_sec, 3))
            
            parsed_data.append({
                "path": img, 
                "time": start_sec, 
                "duration": duration
            })

    # --- CRITICAL SAFETY CHECK ---
    if not parsed_data:
        print(f"\n[FATAL ERROR] The Timeline Engine couldn't find any images with the gapless [start-end] format in:")
        print(f"  -> {upscale_dir}")
        print("\n[!] Diagnosis: You are likely testing an OLD project folder (e.g., '3_why_you_cant') that still has images named with the old single-timestamp format (like '[0_43]_image.png').")
        print("[!] Fix: Please generate a brand new project end-to-end to test the new gapless architecture, or rename a few images to '[0_00-4_52]_image.png' to test this folder.")
        sys.exit(1)
    # -----------------------------

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
    
    print(f"\n[Engine] Channel Detected: {channel_name.upper()}")
    print(f"[Engine] Audio Duration: {total_audio_time:.2f} seconds")
    
    if not is_raw_mode:
        print("\n=== ACTIVE CINEMATIC EFFECT POOLS ===")
        print(" -> Camera Motions: [Zoom In, Zoom Out, Pan Left->Right, Pan Right->Left]")
        print(" -> Math Profile: Constant Speed (Frame-Locked, Crash-Proof Bounds)")
        print(" -> Transitions: [Hard Cut (20%), White Flash (40%), Black Fade (40%)]")
        print(" -> Texture: 2% Subtle 35mm Film Grain")
        print("=====================================\n")
    else:
        print("\n=== RAW PRESET ACTIVE ===")
        print(" -> Effects disabled. Pure 4K static upscaling.")
        print("=========================\n")

    last_motion = ""
    incoming_transition = "hard_cut" 
    
    for i, data in enumerate(parsed_data):
        img_path = data["path"]
        duration = data["duration"]
        clip_name = f"clip_{i:03d}.mp4"
        clip_path = temp_dir / clip_name
        
        if is_raw_mode:
            motion_style = "static"
            out_transition = "hard_cut"
            vf_chain = f"scale=3840:2160,fps=30"
        else:
            motion_style = get_smart_motion_style(last_motion)
            last_motion = motion_style
            total_frames = int(duration * 30)
            
            if i == len(parsed_data) - 1:
                out_transition = "hard_cut" 
            else:
                out_transition = get_random_transition()

            if motion_style == "zoom_in":
                motion_filter = f"zoompan=z='min(1.5,1.02+0.0003*on)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30"
            elif motion_style == "zoom_out":
                motion_filter = f"zoompan=z='max(1.001,1.15-0.0003*on)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30"
            elif motion_style == "pan_lr":
                motion_filter = f"zoompan=z='1.08':d={total_frames}:x='min(iw-iw/zoom,0.4*on)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30"
            else: 
                motion_filter = f"zoompan=z='1.08':d={total_frames}:x='max(0,(iw-iw/zoom)-0.4*on)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30"

            vf_chain = f"scale=8000:4500,{motion_filter},noise=alls=2:allf=t"

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

        cmd = (
            f'"{FFMPEG_EXE}" -loop 1 -i "{img_path}" '
            f'-vf "{vf_chain}" -c:v h264_nvenc -t {duration} -pix_fmt yuv420p -y "{clip_path}"'
        )
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"\n\n[FATAL ERROR] FFmpeg failed on {clip_name}:")
            print(result.stderr)
            sys.exit(1)
            
        blueprint_lines.append(f"file '{clip_path.name}'")
        incoming_transition = out_transition

    print("\n\n[Engine] Clean micro-clips generated successfully!")

    blueprint_path = temp_dir / "blueprint.txt"
    with open(blueprint_path, "w") as f:
        f.write("\n".join(blueprint_lines))

    print("\n[Engine] Executing lightning timeline merge and mapping master studio audio...")
    
    for audio_track_path, suffix in audio_tracks:
        final_output = project_dir / f"{base_video_name}{suffix}.mp4"
        print(f"  -> Rendering {suffix.replace('_', ' ').strip()} version...")
        
        concat_cmd = (
            f'"{FFMPEG_EXE}" -f concat -safe 0 -i "{blueprint_path}" -i "{audio_track_path}" '
            f'-c:v copy -c:a aac -shortest -y "{final_output}"'
        )
        
        final_result = subprocess.run(concat_cmd, shell=True, capture_output=True, text=True)
        if final_result.returncode != 0:
            print(f"\n\n[FATAL ERROR] FFmpeg Concat Failed for {suffix}:")
            print(final_result.stderr)
            sys.exit(1)
            
        print(f"  [SUCCESS] Saved: {final_output.name}")

    shutil.rmtree(temp_dir)
    print(f"\n[SUCCESS] Factory Pipeline Complete!")

def main():
    base_dir = Path(__file__).resolve().parent.parent
    project_dir = get_project_workspace(base_dir)
    build_video(project_dir)

if __name__ == "__main__":
    main()