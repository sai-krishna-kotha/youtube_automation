import sys
import os
import time
import base64
import re
import shutil
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, Error as PlaywrightError
except ImportError:
    pass

class GoogleFlowVideoAutomator:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        
        # --- DYNAMIC MULTI-ACCOUNT DISCOVERY ---
        existing_sessions = sorted(
            [d for d in base_dir.iterdir() if d.is_dir() and d.name.startswith("session_")],
            key=lambda x: x.name
        )
        
        if existing_sessions:
            self.session_dirs = existing_sessions
        else:
            self.session_dirs = [base_dir / "session_1"]

        self.current_session_index = 0
        self.FLOW_URL = "https://labs.google/fx/tools/flow"
        self.HEADLESS_MODE = False
        self.MAX_RETRIES = 3
        
        # --- PROJECT LIMIT & LOCATORS ---
        self.PROJECT_CLIP_THRESHOLD = 1 
        self.NEW_PROJECT_BTN = 'text="New project"'
        self.START_BTN = 'div[type="button"]:has-text("Start")'
        self.UPLOAD_MEDIA_BTN = 'button:has-text("Upload media")'
        self.ADD_TO_PROMPT_BTN = 'button:has-text("Add to Prompt")'
        self.PROMPT_BOX_SELECTOR = 'div[data-slate-editor="true"][role="textbox"]'
        self.GENERATE_BTN_SELECTOR = 'button:has-text("Create"), button:has(i:text-is("arrow_forward"))'

    def setup_session(self):
        print("\n--- GOOGLE FLOW MULTI-ACCOUNT SETUP ---")
        existing_folders = [d.name for d in self.base_dir.iterdir() if d.is_dir()] if self.base_dir.exists() else []
        if existing_folders:
            print("Existing Session Folders:")
            for f_name in sorted(existing_folders):
                print(f" - {f_name}")
        else:
            print("No existing session folders found.")

        new_name = input("\nEnter folder name to setup/login (e.g., session_1): ").strip()
        if not new_name:
            print("Aborted.")
            return

        target_dir = self.base_dir / new_name
        target_dir.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as p:
            print(f"\nLaunching browser for '{new_name}'... Please log in.")
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(target_dir),
                headless=False,
                viewport={"width": 1280, "height": 720},
                args=["--disable-blink-features=AutomationControlled"],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = context.new_page()
            page.goto(self.FLOW_URL)
            
            input(f"\n[✓] Log in fully to '{new_name}'. Once you see Google Flow, press ENTER here...")
            context.close()
            print(f"[System] Session '{new_name}' saved successfully!")

    def _parse_animation_prompts(self, prompt_file: Path):
        clips = []
        with open(prompt_file, 'r', encoding='utf-8') as f:
            for line in f:
                match = re.match(r'\[([\d_]+-[\d_]+)\]\s*(.*)', line.strip())
                if match:
                    clips.append({
                        "timestamp": match.group(1),
                        "prompt": match.group(2)
                    })
        return clips

    def generate_animations(self, prompts_file: Path, image_dir: Path, output_dir: Path):
        self.session_dirs = sorted(
            [d for d in self.base_dir.iterdir() if d.is_dir() and d.name.startswith("session_")],
            key=lambda x: x.name,
            reverse=True
        )

        if not self.session_dirs or not self.session_dirs[0].exists():
            raise Exception("\n[!] No session data found in sessions/flow. Run setup_session() first!")
            
        clips_data = self._parse_animation_prompts(prompts_file)
        if not clips_data:
            print("[!] No valid animation prompts found in file.")
            return

        # Prepare variant directories 1 to 4
        variant_dirs = [output_dir / f"variant_{i}" for i in range(1, 5)]
        for v_dir in variant_dirs:
            v_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n[Google Flow Worker] Starting batch video generation for {len(clips_data)} clips...")
        print(f"[Google Flow Worker] Detected {len(self.session_dirs)} active session(s).")

        with sync_playwright() as p:
            def launch_browser(session_dir):
                print(f"  [System] Booting Browser for '{session_dir.name}'...")
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=str(session_dir), 
                    headless=self.HEADLESS_MODE,
                    viewport={"width": 1280, "height": 720},
                    args=["--disable-blink-features=AutomationControlled"]
                )
                return browser, browser.new_page()

            browser, page = launch_browser(self.session_dirs[self.current_session_index])
            
            project_created = False
            clips_in_current_project = 0 
            
            clip_idx = 0
            while clip_idx < len(clips_data):
                clip = clips_data[clip_idx]
                timestamp_str = clip['timestamp']
                anim_prompt = clip['prompt']
                
                base_filename = f"[{timestamp_str}]_clip.mp4"
                image_filename = f"[{timestamp_str}]_image.png"
                image_path = image_dir / image_filename

                # --- HYBRID OPTIMIZATION: INSTANT STATIC BYPASS ---
                if anim_prompt.strip().upper() == "STATIC":
                    all_images_exist = all((v_dir / image_filename).exists() for v_dir in variant_dirs)
                    if all_images_exist:
                        print(f"\n[Checkpoint] Clip [{timestamp_str}] (STATIC) already injected. Skipping.")
                    else:
                        print(f"\n[Google Flow] Clip [{timestamp_str}] marked as STATIC by AI Director. Bypassing render API...")
                        for v_dir in variant_dirs:
                            dest = v_dir / image_filename
                            if not dest.exists() and image_path.exists():
                                shutil.copy2(image_path, dest)
                    clip_idx += 1
                    continue

                # Check if video clip already exists in all variant folders
                all_exist = all((v_dir / base_filename).exists() for v_dir in variant_dirs)
                if all_exist:
                    print(f"\n[Checkpoint] Clip [{timestamp_str}] fully generated. Skipping.")
                    clip_idx += 1
                    continue

                if not image_path.exists():
                    print(f"\n[!] Error: Could not find reference image {image_filename}. Skipping.")
                    clip_idx += 1
                    continue

                print(f"\nProcessing Clip [{timestamp_str}] via Google Flow...")
                success = False

                for attempt in range(self.MAX_RETRIES):
                    try:
                        # 0. Force hard refresh for a completely clean workspace state if limit reached
                        if not project_created:
                            print("  -> Step 0: Refreshing and creating 'New project'...")
                            page.goto(self.FLOW_URL, wait_until="domcontentloaded", timeout=60000)
                            time.sleep(3)
                            
                            try:
                                new_btn = page.locator(self.NEW_PROJECT_BTN).first
                                if new_btn.is_visible(timeout=7000):
                                    new_btn.click()
                                    time.sleep(5)
                                    if new_btn.is_visible(timeout=5000):
                                        time.sleep(3)
                            except Exception:
                                pass
                                
                            try:
                                video_btn = page.locator('button:has-text("Video")').first
                                if video_btn.is_visible(timeout=3000):
                                    video_btn.click()
                                    time.sleep(1)
                            except Exception:
                                pass

                            project_created = True
                            clips_in_current_project = 0

                        # 1. Click "Start"
                        start_btn = page.locator(self.START_BTN).first
                        if start_btn.is_visible(timeout=5000):
                            start_btn.click()
                            time.sleep(1.5)
                        else:
                            print("  [?] 'Start' button not visible. Checking if Upload modal is already open...")

                        # 2. Click "Upload media" and intercept file dialog
                        upload_btn = page.locator(self.UPLOAD_MEDIA_BTN).first
                        upload_btn.wait_for(state="visible", timeout=10000)
                        
                        try:
                            with page.expect_file_chooser(timeout=5000) as fc_info:
                                upload_btn.click()
                            fc_info.value.set_files(str(image_path))
                        except Exception:
                            page.set_input_files('input[type="file"]', str(image_path), timeout=10000)

                        time.sleep(4.0) 

                        # 3. Click "Add to Prompt"
                        add_prompt_btn = page.locator(self.ADD_TO_PROMPT_BTN).first
                        add_prompt_btn.wait_for(state="visible", timeout=20000)
                        add_prompt_btn.click()
                        time.sleep(1.5)

                        # 4. Insert Prompt Text (FIXED: Using page.keyboard to type into Slate editor)
                        box = page.locator(self.PROMPT_BOX_SELECTOR).first
                        box.wait_for(state="visible", timeout=10000)
                        box.click() # Ensure the Slate editor is in focus
                        time.sleep(0.5)
                        
                        # Clear existing text safely
                        page.keyboard.press("Control+a")
                        page.keyboard.press("Meta+a")
                        page.keyboard.press("Backspace")
                        time.sleep(0.5)
                        
                        # Insert new prompt via keyboard
                        page.keyboard.insert_text(anim_prompt)
                        time.sleep(1.0)

                        js_get_vids = "Array.from(document.querySelectorAll('video')).map(v => v.currentSrc || v.src).filter(Boolean)"
                        baseline_vids = set(page.evaluate(js_get_vids))

                        # 5. Trigger Generation
                        btn = page.locator(self.GENERATE_BTN_SELECTOR).first
                        btn.click(timeout=5000)
                        print("  -> Prompt submitted. Waiting for generated video...")

                        # 6. Poll DOM for generated video element
                        start_time = time.time()
                        new_video_src = None
                        
                        while time.time() - start_time < 120:
                            current_vids = set(page.evaluate(js_get_vids))
                            diff = current_vids - baseline_vids
                            if diff:
                                new_video_src = list(diff)[0]
                                break
                            time.sleep(3)

                        if not new_video_src:
                            raise Exception("Timed out waiting for generated video element.")

                        print("  -> Video rendered! Downloading asset...")
                        primary_out_file = variant_dirs[0] / base_filename

                        # 7. Save generated video
                        if new_video_src.startswith("blob:"):
                            js_blob_fetch = f"""
                            async () => {{
                                const res = await fetch('{new_video_src}');
                                const blob = await res.blob();
                                return new Promise((resolve) => {{
                                    const reader = new FileReader();
                                    reader.onloadend = () => resolve(reader.result);
                                    reader.readAsDataURL(blob);
                                }});
                            }}
                            """
                            data_url = page.evaluate(js_blob_fetch)
                            header, encoded = data_url.split(",", 1)
                            with open(primary_out_file, 'wb') as f:
                                f.write(base64.b64decode(encoded))
                        else:
                            res = browser.request.get(new_video_src)
                            with open(primary_out_file, 'wb') as f:
                                f.write(res.body())

                        # 8. SYNC ONE VIDEO TO ALL 4 VARIANT FOLDERS
                        for v_dir in variant_dirs[1:]:
                            target_path = v_dir / base_filename
                            shutil.copy2(primary_out_file, target_path)

                        print(f"  [✓] Video saved and cloned across all 4 variants for [{timestamp_str}]")
                        
                        # Apply Threshold Logic
                        clips_in_current_project += 1
                        if clips_in_current_project >= self.PROJECT_CLIP_THRESHOLD:
                            print(f"\n  [System] Threshold reached ({self.PROJECT_CLIP_THRESHOLD} clips). Forcing clean project!")
                            project_created = False
                            
                        success = True
                        break

                    except Exception as e:
                        print(f"  [Error] Attempt {attempt + 1}: {e}")
                        project_created = False 
                        time.sleep(3)

                if not success:
                    print(f"  [!] Failed to generate video for [{timestamp_str}]. Skipping.")

                clip_idx += 1

            browser.close()
            print("\n[System] Google Flow Video Batch processing complete!")