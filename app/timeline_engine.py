import sys
import os
import re
import random
import subprocess
import shutil
import wave
from datetime import datetime
from pathlib import Path

# ==========================================
# SYSTEM CONFIGURATION
# ==========================================
# Your exact path to the FFmpeg executable
FFMPEG_EXE = Path("C:/Users/kotha/Downloads/important/ffmpeg/bin/ffmpeg.exe")
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
    """Weighted randomness for transitions. Hard cuts are most common to keep it professional."""
    choices = ["hard_cut", "hard_cut", "hard_cut", "flash_white", "fade_black"]
    return random.choice(choices)

def build_video(project_dir: Path):
    if not FFMPEG_EXE.exists():
        print(f"\n[!] ERROR: FFmpeg not found at {FFMPEG_EXE}")
        sys.exit(1)

    upscale_dir = project_dir / "3_upscaled"
    audio_path = project_dir / "audio.wav"
    temp_dir = project_dir / "temp_video_clips"
    channel_name = project_dir.parent.name.lower()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_output = project_dir / f"FINAL_{project_dir.name}_{timestamp}.mp4"

    if not upscale_dir.exists() or not any(upscale_dir.iterdir()):
        print("\n[!] ERROR: '3_upscaled' folder is empty. Run Module 2 first.")
        return

    # --- 1. PARSE TIMESTAMPS ---
    images = [f for f in upscale_dir.iterdir() if f.suffix.lower() in ['.png', '.jpg', '.jpeg']]
    pattern = re.compile(r'\[(\d+)_(\d+)\]')
    
    parsed_data = []
    for img in images:
        match = pattern.search(img.name)
        if match:
            absolute_time = float(f"{int(match.group(1))}.{int(match.group(2))}")
            parsed_data.append({"path": img, "time": absolute_time})

    parsed_data.sort(key=lambda x: x["time"])
    
    # --- 2. DURATIONS ---
    total_audio_time = get_audio_duration(audio_path)
    parsed_data[0]["time"] = 0.0

    for i in range(len(parsed_data)):
        start_time = parsed_data[i]["time"]
        if i == len(parsed_data) - 1:
            duration = total_audio_time - start_time
        else:
            duration = parsed_data[i+1]["time"] - start_time
        parsed_data[i]["duration"] = max(0.5, round(duration, 3))

    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(exist_ok=True)
    
    blueprint_lines = []
    
    # --- CHANNEL LOGIC & POOL PRINTING ---
    is_raw_mode = "second" in channel_name
    
    print(f"\n[Engine] Channel Detected: {channel_name.upper()}")
    print(f"[Engine] Audio Duration: {total_audio_time:.2f} seconds")
    
    if not is_raw_mode:
        print("\n=== ACTIVE CINEMATIC EFFECT POOLS ===")
        print(" -> Camera Motions: [Zoom In, Zoom Out, Pan Left->Right, Pan Right->Left]")
        print(" -> Math Profile: Constant Speed (Frame-Locked, Crash-Proof Bounds)")
        print(" -> Transitions: [Hard Cut (60%), White Flash (20%), Black Fade (20%)]")
        print(" -> Texture: 2% Subtle 35mm Film Grain")
        print("=====================================\n")
    else:
        print("\n=== RAW PRESET ACTIVE ===")
        print(" -> Effects disabled. Pure 4K static upscaling.")
        print("=========================\n")

    # --- 3. GENERATE MICRO-CLIPS ---
    last_motion = ""
    incoming_transition = "hard_cut" # The first clip always starts normally
    
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

            # CRASH-PROOF CONSTANT SPEED MATH (NO SPACES ALLOWED IN MATH STRINGS)
            # 'on' is the Output Frame Number.
            if motion_style == "zoom_in":
                motion_filter = f"zoompan=z='min(1.5,1.02+0.0003*on)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30"
            elif motion_style == "zoom_out":
                motion_filter = f"zoompan=z='max(1.001,1.15-0.0003*on)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30"
            elif motion_style == "pan_lr":
                motion_filter = f"zoompan=z='1.08':d={total_frames}:x='min(iw-iw/zoom,0.4*on)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30"
            else: # pan_rl
                motion_filter = f"zoompan=z='1.08':d={total_frames}:x='max(0,(iw-iw/zoom)-0.4*on)':y='ih/2-(ih/zoom/2)':s=3840x2160:fps=30"

            # Base visual chain
            vf_chain = f"scale=8000:4500,{motion_filter},noise=alls=2:allf=t"

            fade_duration = 0.3
            fade_start = max(0.0, duration - fade_duration)

            # Apply IN transition
            if incoming_transition == "flash_white":
                vf_chain += f",fade=t=in:st=0:d={fade_duration}:color=white"
            elif incoming_transition == "fade_black":
                vf_chain += f",fade=t=in:st=0:d={fade_duration}:color=black"

            # Apply OUT transition
            if out_transition == "flash_white":
                vf_chain += f",fade=t=out:st={fade_start}:d={fade_duration}:color=white"
            elif out_transition == "fade_black":
                vf_chain += f",fade=t=out:st={fade_start}:d={fade_duration}:color=black"

        sys.stdout.write(f"\r  -> [{motion_style.upper()}] | Ends w/ {out_transition} | Rendering clip {i+1}/{len(parsed_data)} ({duration}s)...")
        sys.stdout.flush()

        cmd = (
            f'"{FFMPEG_EXE}" -loop 1 -i "{img_path}" '
            f'-vf "{vf_chain}" -c:v libx264 -t {duration} -pix_fmt yuv420p -y "{clip_path}"'
        )
        
        # ERROR TRAP
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"\n\n[FATAL ERROR] FFmpeg failed on {clip_name}:")
            print(result.stderr)
            sys.exit(1)
            
        blueprint_lines.append(f"file '{clip_path.absolute().as_posix()}'")
        incoming_transition = out_transition

    print("\n\n[Engine] Clean micro-clips generated successfully!")

    blueprint_path = temp_dir / "blueprint.txt"
    with open(blueprint_path, "w") as f:
        f.write("\n".join(blueprint_lines))

    print("[Engine] Executing lightning timeline merge and mapping master studio audio...")
    concat_cmd = (
        f'"{FFMPEG_EXE}" -f concat -safe 0 -i "{blueprint_path}" -i "{audio_path}" '
        f'-c:v copy -c:a aac -shortest -y "{final_output}"'
    )
    
    final_result = subprocess.run(concat_cmd, shell=True, capture_output=True, text=True)
    if final_result.returncode != 0:
        print(f"\n\n[FATAL ERROR] FFmpeg Concat Failed:")
        print(final_result.stderr)
        sys.exit(1)

    print(f"\n[SUCCESS] Final Video Rendered: {final_output.name}")
    shutil.rmtree(temp_dir)

def main():
    base_dir = Path(__file__).resolve().parent.parent
    project_dir = get_project_workspace(base_dir)
    build_video(project_dir)

if __name__ == "__main__":
    main()