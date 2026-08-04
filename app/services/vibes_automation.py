import sys
import time
import base64
import shutil
from pathlib import Path

# --- NEW: Injecting Centralized Parser ---
from app.utils.timeline_parser import TimelineParser

try:
    from playwright.sync_api import sync_playwright, Error as PlaywrightError
except ImportError:
    pass

# Custom exceptions to trigger specific reset behaviors
class RateLimitException(Exception):
    pass

class MetaAIErrorException(Exception):
    pass

class BrowserRelaunchException(Exception):
    pass

class VibesAIAutomator:
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
        self.VIBES_URL = "https://vibes.ai" 
        self.MAX_RETRIES = 3
        self.HEADLESS_MODE = False
        self.PROJECT_CLIP_THRESHOLD = 1 
        self.MIN_FAIL_TOAST_TIME = 30 
        
        # --- NEW: GENERATION TIMEOUT THRESHOLD (IN SECONDS) ---
        self.GENERATION_TIMEOUT = 120  # Max wait time for video render before hard reset

    def _handle_unexpected_login(self, page):
        """Checks for random validation/login popups and clicks them to recover."""
        try:
            login_btn = page.locator('button:has-text("Log in"), button:has-text("Login"), button:has-text("Sign in")').first
            if login_btn.is_visible(timeout=2000):
                print("\n  [System] Session Validation / Login button detected! Clicking to recover...")
                login_btn.click()
                time.sleep(5) # Give it time to route back to home
                return True
        except Exception:
            pass 
        return False

    def _check_error_toasts(self, page):
        """Scans DOM for error/failure toast messages."""
        try:
            error_toast = page.locator('text=/error|something went wrong|failed to create|try again|unable to/i').first
            if error_toast.is_visible(timeout=1000):
                toast_text = error_toast.inner_text()
                print(f"\n  [!] Error Toast Detected: '{toast_text}'")
                return True
        except Exception:
            pass
        return False

    def setup_session(self):
        print("\n--- VIBES AI MULTI-ACCOUNT SETUP ---")
        
        existing_folders = [d.name for d in self.base_dir.iterdir() if d.is_dir()] if self.base_dir.exists() else []
        if existing_folders:
            print("Existing Session Folders:")
            for f_name in sorted(existing_folders):
                print(f" - {f_name}")
        else:
            print("No existing session folders found.")

        new_name = input("\nEnter folder name to setup/login (e.g., session_1, session_3): ").strip()
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
            page.goto(self.VIBES_URL)
            
            self._handle_unexpected_login(page)
            
            input(f"\n[✓] Log in fully to '{new_name}'. Once you see the Vibes dashboard, press ENTER here...")
            context.close()
            print(f"[System] Session '{new_name}' saved successfully!")

    def _parse_animation_prompts(self, prompt_file: Path):
        """V2: Parses the animation prompts using TimelineParser for tag resilience."""
        clips = []
        with open(prompt_file, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                parsed_clip = TimelineParser.parse_prompt_line(line)
                if parsed_clip:
                    clips.append({
                        "timestamp": f"{parsed_clip.start_str}-{parsed_clip.end_str}",
                        "prompt": parsed_clip.content,
                        "clip_type": parsed_clip.clip_type,
                        "image_filename": parsed_clip.expected_filename,
                        "video_filename": parsed_clip.expected_filename.replace("_image.png", "_clip.mp4")
                    })
        return clips

    def generate_animations(self, prompts_file: Path, image_dir: Path, output_dir: Path):
        self.session_dirs = sorted(
            [d for d in self.base_dir.iterdir() if d.is_dir() and d.name.startswith("session_")],
            key=lambda x: x.name
        )

        if not self.session_dirs or not self.session_dirs[0].exists():
            raise Exception("\n[!] No session data found. Run setup_session() first!")
            
        clips_data = self._parse_animation_prompts(prompts_file)
        if not clips_data:
            print("[!] No valid animation prompts found in file.")
            return

        variant_dirs = [output_dir / f"variant_{i}" for i in range(1, 5)]
        for v_dir in variant_dirs:
            v_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n[Vibes Worker] Starting batch generation for {len(clips_data)} clips...")
        print(f"[Vibes Worker] Detected {len(self.session_dirs)} active account sessions.")

        with sync_playwright() as p:
            def launch_browser(session_dir):
                print(f"  [System] Booting Browser Context for '{session_dir.name}' (Account {self.current_session_index + 1}/{len(self.session_dirs)})...")
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
            known_video_srcs = set() 
            
            clip_idx = 0
            while clip_idx < len(clips_data):
                clip = clips_data[clip_idx]
                timestamp_str = clip['timestamp']
                anim_prompt = clip['prompt']
                
                # --- V2 FILENAME MAPPING ---
                base_filename = clip['video_filename']
                image_filename = clip['image_filename']
                image_path = image_dir / image_filename

                # --- HYBRID OPTIMIZATION: INSTANT STATIC BYPASS (Includes B-Rolls) ---
                if anim_prompt.strip().upper() == "STATIC":
                    all_images_exist = all((v_dir / image_filename).exists() for v_dir in variant_dirs)
                    if all_images_exist:
                        print(f"\n[Checkpoint] Clip [{timestamp_str}] (STATIC) already injected. Skipping.")
                    else:
                        tag_msg = f"[{clip['clip_type']}] " if clip['clip_type'] != "DEFAULT" else ""
                        print(f"\n[Vibes Worker] {tag_msg}Clip [{timestamp_str}] marked as STATIC by AI Director. Bypassing render API...")
                        for v_dir in variant_dirs:
                            dest = v_dir / image_filename
                            if not dest.exists() and image_path.exists():
                                shutil.copy2(image_path, dest)
                    clip_idx += 1
                    continue
                # --------------------------------------------------

                all_exist = all((v_dir / base_filename).exists() for v_dir in variant_dirs)
                if all_exist:
                    print(f"\n[Checkpoint] Clip [{timestamp_str}] fully generated. Skipping.")
                    clip_idx += 1
                    continue

                if not image_path.exists():
                    print(f"\n[!] Error: Could not find matching reference image {image_filename}. Skipping.")
                    clip_idx += 1
                    continue

                print(f"\nProcessing Clip [{timestamp_str}] via '{self.session_dirs[self.current_session_index].name}'...")
                success = False
                swapped_account = False  
                time.sleep(5)
                
                if page.locator('text=/rate limit|limit reached|too many|quota/i').first.is_visible():
                    print("\n  [🚨] DETECTED RATE LIMIT TOAST MESSAGE!")
                    time.sleep(5)
                    raise RateLimitException("Rate limit hit on current account.")
                    
                for attempt in range(self.MAX_RETRIES):
                    try:
                        if page.is_closed():
                            try: browser.close()
                            except: pass
                            browser, page = launch_browser(self.session_dirs[self.current_session_index])
                            project_created = False 
                            clips_in_current_project = 0

                        # --- STEP 1: CREATE NEW PROJECT WITH VERIFICATION ---
                        if not project_created:
                            print("  -> Step 1: Navigating to Dashboard & Creating clean project instance...")
                            page.goto("about:blank") 
                            time.sleep(1)
                            
                            page.goto(self.VIBES_URL, wait_until="domcontentloaded", timeout=60000)
                            time.sleep(6)
                            
                            if self._handle_unexpected_login(page):
                                print("  [System] Re-syncing dashboard after login navigation...")
                                page.goto(self.VIBES_URL, wait_until="domcontentloaded", timeout=60000)
                                time.sleep(6)
                            
                            create_new_btn = page.locator('button:has-text("Create new")').first
                            try:
                                create_new_btn.wait_for(state="visible", timeout=35000)
                                create_new_btn.click()
                                time.sleep(3)
                                
                                workspace_check = page.locator('button[data-analytics-id="creation_gallery.start_end_frame_selection_click"], button:has-text("Add start frame"), div[data-lexical-editor="true"]').first
                                workspace_check.wait_for(state="visible", timeout=15000)
                                
                            except Exception as proj_err:
                                if self._check_error_toasts(page):
                                    raise BrowserRelaunchException("Toast error detected during project creation!")
                                raise Exception(f"Failed to enter project workspace: {proj_err}")

                            if self._check_error_toasts(page):
                                raise BrowserRelaunchException("Toast error detected after entering workspace!")

                            project_created = True
                            known_video_srcs = set() 

                        remove_btn = page.locator('button[aria-label="Remove start frame"], button[aria-label="Remove image"]')
                        if remove_btn.count() > 0 and remove_btn.first.is_visible():
                            print("  -> Step 2: Removing existing start frame from workspace...")
                            remove_btn.first.click()
                            time.sleep(1)

                        add_start_frame_btn = page.get_by_role("button", name="Add start frame").first
                        if not add_start_frame_btn.is_visible():
                            print("  -> Step 3: Expanding 'Start, end frame' toggle to reveal inline button...")
                            expand_ui_btn = page.locator('button[data-analytics-id="creation_gallery.start_end_frame_selection_click"]').first
                            expand_ui_btn.click()
                            add_start_frame_btn.wait_for(state="visible", timeout=5000)

                        print("  -> Step 4: Clicking 'Add start frame' to open upload modal...")
                        add_start_frame_btn.click()
                        time.sleep(2)

                        print("  -> Step 5: Uploading image...")
                        modal_upload_btn = page.locator('button:has-text("Upload")').filter(has_text="Upload").last
                        
                        try:
                            modal_upload_btn.wait_for(state="visible", timeout=12000)
                        except Exception as e:
                            raise BrowserRelaunchException("UI Glitch: Upload button completely missing from modal!")

                        modal_upload_btn.click()
                        time.sleep(1)
                        
                        page.set_input_files('input[type="file"]', str(image_path), timeout=15000)
                        time.sleep(2) 
                        
                        confirm_upload_btn = page.locator('button:text-is("Upload")').last
                        if confirm_upload_btn.is_visible():
                            confirm_upload_btn.click()
                            
                        for _ in range(4): 
                            time.sleep(3)
                            if page.locator('text="Something went wrong!"').first.is_visible():
                                raise MetaAIErrorException("Meta AI crashed during the upload phase.")

                            if page.locator('text=/upload failed|upload unsuccessful|failed to upload/i').first.is_visible():
                                print("\n  [!] 'Upload failed' toast detected! Retrying direct Upload click...")
                                if confirm_upload_btn.is_visible():
                                    confirm_upload_btn.click()
                                time.sleep(2)
                            else:
                                break
                        time.sleep(7) 

                        print("  -> Step 6: Selecting recently uploaded image from the active gallery...")
                        gallery_img = page.locator(f'img[alt="{image_path.name}"]').first 
                        
                        try:
                            gallery_img.wait_for(state="visible", timeout=20000)
                        except Exception as e:
                            print("  [!] Timeout waiting for image to load in gallery.")
                            raise e 
                        
                        add_to_video_btn = page.locator('button:has-text("Add to video")').first
                        
                        is_selected = False
                        for click_attempt in range(5):
                            gallery_img.click(force=True)
                            time.sleep(2)
                            if not add_to_video_btn.is_disabled():
                                is_selected = True
                                break

                        if not is_selected:
                            print("  [!] Could not select image in gallery.")
                            raise Exception("Could not select image in gallery.")

                        print("  -> Step 7: Binding image to video...")
                        add_to_video_btn.click(force=True) 
                        time.sleep(2)

                        print("  -> Step 8: Entering animation prompt...")
                        prompt_box = page.locator('div[data-lexical-editor="true"]').first
                        prompt_box.wait_for(state="visible", timeout=10000)
                        prompt_box.click()
                        
                        page.keyboard.press("Control+a")
                        page.keyboard.press("Meta+a") 
                        page.keyboard.press("Backspace")
                        time.sleep(1)
                        
                        page.keyboard.insert_text(anim_prompt)
                        time.sleep(1)

                        js_get_vids = "Array.from(document.querySelectorAll('video')).map(v => v.currentSrc || v.src).filter(Boolean)"
                        
                        if page.locator('text=/rate limit|limit reached|too many|quota/i').first.is_visible():
                                print("\n  [🚨] DETECTED RATE LIMIT TOAST MESSAGE!")
                                raise RateLimitException("Rate limit hit on current account.")

                        print("  -> Step 9: Configuring 720p and generating...")

                        generate_btn = page.locator('button[aria-label="Generate"]').first
                        advanced_btn = page.locator('button[title="Advanced settings"]').first

                        if advanced_btn.is_visible():
                            advanced_btn.click()
                            page.wait_for_timeout(500)

                            btn_720p = page.get_by_role("button", name="720p")

                            if btn_720p.is_visible():
                                btn_720p.click()
                                page.wait_for_timeout(300)

                            page.evaluate("""
                            () => {
                                const backdrop = document.querySelector(
                                    'div[style*="position: fixed"][style*="inset: 0px"][style*="pointer-events: auto"]'
                                );

                                if (backdrop) {
                                    backdrop.dispatchEvent(new PointerEvent("pointerdown", {
                                        bubbles: true,
                                        cancelable: true,
                                        composed: true,
                                        pointerType: "mouse",
                                        clientX: 10,
                                        clientY: 10,
                                        button: 0,
                                        buttons: 1,
                                        isPrimary: true
                                    }));
                                }
                            }
                            """)

                            page.wait_for_timeout(500)

                        generate_btn.wait_for(state="visible")
                        generate_btn.click()
                        start_wait = time.time()
                        generation_failed = False
                        new_vid_srcs = set()
                        early_fail_ignored = False

                        while True:
                            elapsed = time.time() - start_wait

                            if elapsed > self.GENERATION_TIMEOUT:
                                print(f"\n  [🚨] TIMEOUT THRESHOLD EXCEEDED ({int(elapsed)}s > {self.GENERATION_TIMEOUT}s)!")
                                raise BrowserRelaunchException(f"Generation parsing hung for {int(elapsed)}s. Nuke browser and retry.")

                            try:
                                current_vid_srcs = set(page.evaluate(js_get_vids))
                                new_vid_srcs = current_vid_srcs - known_video_srcs
                            except PlaywrightError:
                                pass 
                                
                            if len(new_vid_srcs) >= 4:
                                print(f"\n  [+] Success! Found {len(new_vid_srcs)} completely new video generations.")
                                break 
                                
                            if page.locator('text="Something went wrong!"').first.is_visible():
                                raise MetaAIErrorException("Meta AI threw a generic 'Something went wrong!' error.")

                            if page.locator('text=/rate limit|limit reached|too many|quota/i').first.is_visible():
                                print("\n  [🚨] DETECTED RATE LIMIT TOAST MESSAGE!")
                                raise RateLimitException("Rate limit hit on current account.")

                            if page.locator('button:has-text("Log in"), button:has-text("Login")').first.is_visible():
                                raise Exception("Login validation triggered during generation polling.")

                            if page.locator('text="Generation failed"').first.is_visible():
                                if elapsed > self.MIN_FAIL_TOAST_TIME:
                                    generation_failed = True
                                    print(f"\n  [!] 'Generation failed' toast validated after {int(elapsed)}s. Aborting.")
                                    break
                                elif not early_fail_ignored:
                                    print(f"\n  [?] 'Generation failed' toast caught early ({int(elapsed)}s). Ignoring meta tweak...")
                                    early_fail_ignored = True 
                                
                            sys.stdout.write(f"\r  -> Polling DOM... Found {len(new_vid_srcs)}/4 required videos. Elapsed: {int(elapsed)}s / {self.GENERATION_TIMEOUT}s max")
                            sys.stdout.flush()
                            time.sleep(3) 
                        
                        if generation_failed:
                            project_created = False 
                            clips_in_current_project = 0
                            raise Exception("Generation failed on Vibes AI server end. Triggering new project setup.")
                            
                        print("\n  -> Render complete! Downloading new assets...")
                        time.sleep(5) 

                        new_urls = list(new_vid_srcs)
                        
                        if len(new_urls) < 4:
                            raise Exception(f"Expected 4 new video URLs, but only found {len(new_urls)}.")

                        for i, vid_src in enumerate(new_urls[:4]):
                            v_dir = variant_dirs[i]
                            out_file = v_dir / base_filename
                            if out_file.exists(): continue

                            if vid_src.startswith("blob:"):
                                js_blob_fetch = f"""
                                async () => {{
                                    const res = await fetch('{vid_src}');
                                    const blob = await res.blob();
                                    return new Promise((resolve) => {{
                                        const reader = new FileReader();
                                        reader.onloadend = () => resolve(reader.result);
                                        reader.readAsDataURL(blob);
                                    }});
                                }}
                                """
                                try:
                                    data_url = page.evaluate(js_blob_fetch)
                                    header, encoded = data_url.split(",", 1)
                                    with open(out_file, 'wb') as f:
                                        f.write(base64.b64decode(encoded))
                                except Exception as e:
                                    raise Exception(f"Failed to fetch blob string {vid_src}: {e}")
                            else:
                                dl_success = False
                                for dl_attempt in range(3):
                                    try:
                                        response = browser.request.get(vid_src, timeout=60000)
                                        with open(out_file, 'wb') as f:
                                            f.write(response.body())
                                        dl_success = True
                                        break
                                    except Exception as dl_e:
                                        print(f"     [Download Warning] Network blip, retrying... ({dl_e})")
                                        time.sleep(3)
                                        
                                if not dl_success:
                                    raise Exception(f"Failed to download Video {i+1} over HTTP.")

                        print(f"  [✓] Successfully downloaded 4 exactly matched variants for Clip [{timestamp_str}]")
                        
                        known_video_srcs.update(new_urls[:4])
                        
                        success = True
                        break 
                        
                    except BrowserRelaunchException as bre:
                        print(f"\n  [🚨] {bre}")
                        print("  [System] Tearing down corrupted browser instance and relaunching...")
                        try: browser.close()
                        except: pass
                        
                        browser, page = launch_browser(self.session_dirs[self.current_session_index])
                        project_created = False
                        clips_in_current_project = 0
                        continue

                    except MetaAIErrorException as me:
                        print(f"\n  [🚨] {me}")
                        print("  [System] Forcing a fresh project creation via Vibes.ai home...")
                        project_created = False
                        clips_in_current_project = 0
                        continue

                    except RateLimitException:
                        print(f"  [System] Initiating Account Swap...")
                        try: browser.close()
                        except: pass
                        
                        self.current_session_index += 1
                        if self.current_session_index >= len(self.session_dirs):
                            print("\n[FATAL] ALL ACCOUNTS HAVE HIT THEIR RATE LIMITS. Stopping execution.")
                            return
                        
                        print(f"  [System] Switched to '{self.session_dirs[self.current_session_index].name}'. Booting browser...")
                        browser, page = launch_browser(self.current_session_index)
                        project_created = False
                        clips_in_current_project = 0
                        swapped_account = True  
                        break 

                    except PlaywrightError as pe:
                        if self._handle_unexpected_login(page):
                            project_created = False
                            clips_in_current_project = 0
                            continue

                        try:
                            print("  [System] Attempting Escape to clear any frozen modals...")
                            page.keyboard.press("Escape")
                            time.sleep(1.5)
                        except: pass

                        try:
                            if not page.is_closed() and page.locator('text="Something went wrong!"').first.is_visible():
                                print("\n  [🚨] Meta AI Error Screen detected behind the timeout!")
                                print("  [System] Forcing a fresh project creation via Vibes.ai home...")
                                project_created = False
                                clips_in_current_project = 0
                                continue
                        except: pass

                        print(f"  [Error - Playwright] Attempt {attempt + 1}: {pe}")
                        if "closed" in str(pe).lower():
                            try: page.close() 
                            except: pass
                            project_created = False
                            clips_in_current_project = 0
                        time.sleep(5)

                    except Exception as e:
                        if self._handle_unexpected_login(page):
                            project_created = False
                            clips_in_current_project = 0
                            continue

                        try:
                            print("  [System] Attempting Escape to clear any frozen modals...")
                            page.keyboard.press("Escape")
                            time.sleep(1.5)
                        except: pass

                        try:
                            if not page.is_closed() and page.locator('text="Something went wrong!"').first.is_visible():
                                print("\n  [🚨] Meta AI Error Screen detected!")
                                print("  [System] Forcing a fresh project creation via Vibes.ai home...")
                                project_created = False
                                clips_in_current_project = 0
                                continue
                        except: pass

                        print(f"  [Error] Attempt {attempt + 1}: {e}")
                        if attempt < self.MAX_RETRIES - 1:
                            page.reload()
                            time.sleep(5)
                
                if not success and not swapped_account:
                    print(f"\n[FATAL] Failed to generate Clip [{timestamp_str}]. Skipping to keep the batch moving.")
                    clip_idx += 1
                elif success:
                    clip_idx += 1
                    clips_in_current_project += 1
                    if clips_in_current_project >= self.PROJECT_CLIP_THRESHOLD:
                        print(f"\n[System] Threshold reached ({self.PROJECT_CLIP_THRESHOLD} clips). Forcing clean project!")
                        project_created = False
                        clips_in_current_project = 0
                
            browser.close()
            print("\n[System] Vibes AI Batch processing complete!")