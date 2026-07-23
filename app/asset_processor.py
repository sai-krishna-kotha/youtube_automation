import sys
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

# ==========================================
# SYSTEM CONFIGURATION
# ==========================================
# UPDATE THIS PATH to wherever your upscaler .exe is stored!
UPSCALER_EXE = Path("C:/Users/kotha/Downloads/important/upscaler/realesrgan-ncnn-vulkan.exe")
UPSCALER_MODEL = "realesrgan-x4plus-anime"
# ==========================================

def get_project_workspace(base_dir: Path) -> Path:
    """CLI to select the channel and project."""
    terminal_width = os.get_terminal_size().columns if os.isatty(sys.stdout.fileno()) else 80
    print("\n" + "="*terminal_width)
    print("   ASSET PROCESSING FACTORY (MODULE 2)")
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


def run_watermark_removal(raw_dir: Path, output_dir: Path):
    """Executes the node-based gwr image utility to strip watermarks locally."""
    print("\n[Factory] Starting Watermark Removal...")
    output_dir.mkdir(exist_ok=True)
    
    images = [f for f in raw_dir.iterdir() if f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']]
    if not images:
        print("[!] No images found in raw_images folder!")
        return

    for img in images:
        out_path = output_dir / img.name
        if out_path.exists():
            continue # Smart resume: Skip if already processed
            
        print(f"  -> Stripping watermark: {img.name}")
        
        cmd = f'pnpm exec gwr remove "{img.absolute()}" --output "{out_path.absolute()}"'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if not out_path.exists():
            print(f"  [!] Failed {img.name}: {result.stderr.strip() or 'No error output'}")
            continue

    print("[Factory] Watermark Removal Complete!")


def run_upscaler(input_dir: Path, output_dir: Path, temp_dir: Path, upscaler_model: str = "realesrgan-x4plus-anime"):
    """Executes Real-ESRGAN in a safe temp directory with Smart Resume and dynamic models."""
    print(f"\n[Factory] Starting 4K Upscaling (Model: {upscaler_model})...")
    
    if not UPSCALER_EXE.exists():
        print(f"[!] ERROR: Upscaler not found at {UPSCALER_EXE}")
        print("[!] Please update the UPSCALER_EXE path at the top of asset_processor.py")
        return

    output_dir.mkdir(exist_ok=True)
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(exist_ok=True)
    
    images = [f for f in input_dir.iterdir() if f.suffix.lower() in ['.png', '.jpg', '.jpeg']]
    
    # SMART RESUME: Predict the exact .png output name Real-ESRGAN will create
    images_to_process = []
    for img in images:
        expected_out_name = img.with_suffix('.png').name
        if not (output_dir / expected_out_name).exists():
            images_to_process.append(img)
    
    if not images_to_process:
        print("[Factory] All images are already upscaled! Skipping to next step.")
        return

    print(f"  -> Prepping {len(images_to_process)} images for batch processing...")
    for img in images_to_process:
        shutil.copy2(img, temp_dir / img.name)

    print(f"  -> Firing up Real-ESRGAN ({upscaler_model}). This will take a while...\n")
    command = [
        str(UPSCALER_EXE),
        "-i", str(temp_dir),
        "-o", str(output_dir),
        "-n", upscaler_model,
        "-s", "4",
        "-f", "png"
    ]
    
    try:
        subprocess.run(command, check=True)
        print("\n[Factory] 4K Upscaling Complete!")
    except subprocess.CalledProcessError as e:
        print(f"\n[X] Upscaling failed with error code {e.returncode}")
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            
            
def run_renamer(input_dir: Path, output_dir: Path):
    """Converts [0_43-41_62]_image.png to human-readable Clip_00m00s_to_00m41s.png with Smart Resume"""
    print("\n[Factory] Translating timestamps for human editors...")
    output_dir.mkdir(exist_ok=True)
    
    images = [f for f in input_dir.iterdir() if f.is_file()]
    
    # Regex to catch both the old format [0_45] and the new gapless format [0_45-41_62]
    pattern = re.compile(r'\[(\d+)_(\d+)(?:-(\d+)_(\d+))?\]')
    
    processed_count = 0
    skipped_count = 0
    
    for img in images:
        match = pattern.search(img.name)
        if match:
            start_sec = int(match.group(1))
            start_ms = match.group(2)
            
            s_mins = start_sec // 60
            s_secs = start_sec % 60
            
            # If the new [start-end] format is detected
            if match.group(3) and match.group(4):
                end_sec = int(match.group(3))
                end_ms = match.group(4)
                
                e_mins = end_sec // 60
                e_secs = end_sec % 60
                
                new_name = f"Clip_{s_mins:02d}m{s_secs:02d}s_{start_ms}_to_{e_mins:02d}m{e_secs:02d}s_{end_ms}{img.suffix}"
            else:
                # Fallback for old format
                new_name = f"{s_mins:02d}_{s_secs:02d}_{start_ms}_01{img.suffix}"
                
            target_path = output_dir / new_name
            
            # SMART RESUME CHECK
            if target_path.exists():
                skipped_count += 1
                continue
                
            shutil.copy2(img, target_path)
            processed_count += 1
        else:
            target_path = output_dir / img.name
            if target_path.exists():
                skipped_count += 1
                continue
                
            shutil.copy2(img, target_path)
            processed_count += 1
            
    print(f"[Factory] Timeline formatting complete! Translated {processed_count} files (Skipped {skipped_count} existing).")
    
    
def main():
    base_dir = Path(__file__).resolve().parent.parent
    project_dir = get_project_workspace(base_dir)
    
    # Define Factory Directories
    raw_dir = project_dir / "1_raw_images"
    wm_dir = project_dir / "2_watermark_removed"
    up_dir = project_dir / "3_upscaled"
    final_dir = project_dir / "4_final_production"
    temp_dir = project_dir / "temp_upscale_processing"
    
    # Ensure raw directory exists so user can drop files there
    if not raw_dir.exists():
        raw_dir.mkdir(parents=True)
        print(f"\n[!] SYSTEM HALT: I have created the '1_raw_images' folder in:")
        print(f"    {project_dir}")
        print("\n[!] Please drop your downloaded Gemini images into that folder and run this script again.")
        sys.exit(0)
        
    raw_count = len([f for f in raw_dir.iterdir() if f.is_file()])
    if raw_count == 0:
        print(f"\n[!] The '1_raw_images' folder is empty. Please add your images first.")
        sys.exit(0)

    # Checkpoint UI
    wm_count = len([f for f in wm_dir.iterdir() if f.is_file()]) if wm_dir.exists() else 0
    up_count = len([f for f in up_dir.iterdir() if f.is_file()]) if up_dir.exists() else 0
    
    print("\n--- FACTORY CHECKPOINT STATUS ---")
    print(f"  [✓] {raw_count} images in 1_raw_images")
    print(f"  [{'✓' if wm_count > 0 else ' '}] {wm_count} images in 2_watermark_removed")
    print(f"  [{'✓' if up_count > 0 else ' '}] {up_count} images in 3_upscaled")
    
    print("\n--- ACTION MENU ---")
    print("  1. Run Full Pipeline (Watermark -> Upscale -> Rename)")
    print("  2. Run Watermark Removal Only")
    print("  3. Run Upscaler Only (Resumes from watermark folder)")
    print("  4. Run Timeline Renamer Only (Resumes from upscaled folder)")
    
    choice = input("\nSelect action (1-4): ").strip()
    
    if choice in ['1', '2']:
        run_watermark_removal(raw_dir, wm_dir)
        
    if choice in ['1', '3']:
        # If they skipped watermark, fallback to raw images if wm_dir is empty
        source_dir = wm_dir if wm_dir.exists() and any(wm_dir.iterdir()) else raw_dir
        run_upscaler(source_dir, up_dir, temp_dir)
        
    if choice in ['1', '4']:
        source_dir = up_dir if up_dir.exists() and any(up_dir.iterdir()) else wm_dir
        if not source_dir.exists() or not any(source_dir.iterdir()):
            source_dir = raw_dir
        run_renamer(source_dir, final_dir)

    print(f"\n[System] Module 2 processing complete. Check your project folder!")

if __name__ == "__main__":
    main()