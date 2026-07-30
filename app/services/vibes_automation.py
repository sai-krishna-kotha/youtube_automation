import sys
import time
import re
import base64
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, Error as PlaywrightError
except ImportError:
    pass

# Custom exceptions to trigger specific reset behaviors
class RateLimitException(Exception):
    pass

class MetaAIErrorException(Exception):
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
        self.MIN_FAIL_TOAST_TIME = 10 

    def _handle_unexpected_login(self, page):
        try:
            login_btn = page.locator('button:has-text("Log in"), button:has-text("Login"), button:has-text("Sign in")').first
            if login_btn.is_visible(timeout=3000):
                print("  [System] Found a Login button. Attempting to click...")
                login_btn.click()
                time.sleep(3)
        except Exception:
            pass 

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
                
                base_filename = f"[{timestamp_str}]_clip.mp4"
                image_filename = f"[{timestamp_str}]_image.png"
                image_path = image_dir / image_filename

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
                    raise RateLimitException("Rate limit hit on current account.")
                for attempt in range(self.MAX_RETRIES):
                    try:
                        if page.is_closed():
                            try: browser.close()
                            except: pass
                            browser, page = launch_browser(self.session_dirs[self.current_session_index])
                            project_created = False 
                            clips_in_current_project = 0

                        # STEP 1: PROJECT CREATION LOGIC
                        if not project_created:
                            print("  -> Step 1: Navigating to Dashboard & Creating clean project instance...")
                            page.goto("about:blank") 
                            time.sleep(1)
                            
                            page.goto(self.VIBES_URL, wait_until="domcontentloaded", timeout=60000)
                            time.sleep(3)
                            self._handle_unexpected_login(page)
                            
                            create_new_btn = page.locator('button:has-text("Create new")').first
                            create_new_btn.wait_for(state="visible", timeout=35000)
                            create_new_btn.click()
                            time.sleep(4) 
                            project_created = True
                            known_video_srcs = set() # Reset memory bank on fresh project

                        # STEP 2: CLEAN PREVIOUS START FRAME
                        remove_btn = page.locator('button[aria-label="Remove start frame"], button[aria-label="Remove image"]')
                        if remove_btn.count() > 0 and remove_btn.first.is_visible():
                            print("  -> Step 2: Removing existing start frame from workspace...")
                            remove_btn.first.click()
                            time.sleep(1)

                        # STEP 3: REVEAL INLINE BUTTON
                        add_start_frame_btn = page.get_by_role("button", name="Add start frame").first
                        if not add_start_frame_btn.is_visible():
                            print("  -> Step 3: Expanding 'Start, end frame' toggle to reveal inline button...")
                            expand_ui_btn = page.locator('button[data-analytics-id="creation_gallery.start_end_frame_selection_click"]').first
                            expand_ui_btn.click()
                            add_start_frame_btn.wait_for(state="visible", timeout=5000)

                        # STEP 4: CLICK TO OPEN UPLOAD MODAL
                        print("  -> Step 4: Clicking 'Add start frame' to open upload modal...")
                        add_start_frame_btn.click()
                        time.sleep(2)

                        # STEP 5: UPLOAD FILE WITH RETRY LOGIC
                        print("  -> Step 5: Uploading image...")
                        modal_upload_btn = page.locator('button:has-text("Upload")').filter(has_text="Upload").last
                        modal_upload_btn.wait_for(state="visible", timeout=10000)
                        modal_upload_btn.click()
                        time.sleep(1)
                        
                        page.set_input_files('input[type="file"]', str(image_path), timeout=15000)
                        time.sleep(2) 
                        
                        confirm_upload_btn = page.locator('button:text-is("Upload")').last
                        if confirm_upload_btn.is_visible():
                            confirm_upload_btn.click()
                            
                        # --- ROBUST UPLOAD CHECKER ---
                        for _ in range(4): 
                            time.sleep(3)
                            # ADDED .first TO PREVENT STRICT MODE VIOLATIONS
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

                        # STEP 6: SELECT RECENT IMAGE
                        print("  -> Step 6: Selecting recently uploaded image from the active gallery...")
                        gallery_img = page.locator(f'img[alt="{image_path.name}"]').first 
                        gallery_img.wait_for(state="visible", timeout=20000)
                        
                        add_to_video_btn = page.locator('button:has-text("Add to video")').first
                        
                        is_selected = False
                        for click_attempt in range(5):
                            gallery_img.click(force=True)
                            time.sleep(1.5)
                            if not add_to_video_btn.is_disabled():
                                is_selected = True
                                break

                        if not is_selected:
                            raise Exception("Could not select image in gallery.")

                        # STEP 7: ADD TO VIDEO
                        print("  -> Step 7: Binding image to video...")
                        add_to_video_btn.click(force=True) 
                        time.sleep(2)

                        # STEP 8: PROMPT INSERTION
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

                        # STEP 9: GENERATE & RATE LIMIT POLLING
                        print("  -> Step 9: Clicking Generate and polling DOM for completely new video URLs...")
                        generate_btn = page.locator('button[aria-label="Generate"]').first
                        generate_btn.click()
                        
                        start_wait = time.time()
                        generation_failed = False
                        new_vid_srcs = set()
                        early_fail_ignored = False
                        
                        while True:
                            try:
                                current_vid_srcs = set(page.evaluate(js_get_vids))
                                new_vid_srcs = current_vid_srcs - known_video_srcs
                            except PlaywrightError:
                                pass 
                                
                            if len(new_vid_srcs) >= 4:
                                print(f"\n  [+] Success! Found {len(new_vid_srcs)} completely new video generations.")
                                break 
                                
                            # ADDED .first TO PREVENT STRICT MODE VIOLATIONS
                            if page.locator('text="Something went wrong!"').first.is_visible():
                                raise MetaAIErrorException("Meta AI threw a generic 'Something went wrong!' error.")

                            if page.locator('text=/rate limit|limit reached|too many|quota/i').first.is_visible():
                                print("\n  [🚨] DETECTED RATE LIMIT TOAST MESSAGE!")
                                raise RateLimitException("Rate limit hit on current account.")

                            if page.locator('text="Generation failed"').first.is_visible():
                                elapsed = time.time() - start_wait
                                if elapsed > self.MIN_FAIL_TOAST_TIME:
                                    generation_failed = True
                                    print(f"\n  [!] 'Generation failed' toast validated after {int(elapsed)}s. Aborting.")
                                    break
                                elif not early_fail_ignored:
                                    print(f"\n  [?] 'Generation failed' toast caught early ({int(elapsed)}s). Ignoring meta tweak...")
                                    early_fail_ignored = True 
                                
                            sys.stdout.write(f"\r  -> Polling DOM... Found {len(new_vid_srcs)}/4 required videos. Elapsed: {int(time.time() - start_wait)}s")
                            sys.stdout.flush()
                            time.sleep(3) 
                        
                        if generation_failed:
                            project_created = False 
                            clips_in_current_project = 0
                            raise Exception("Generation failed on Vibes AI server end. Triggering new project setup.")
                            
                        print("\n  -> Render complete! Downloading new assets...")
                        time.sleep(5) 

                        # =======================================================
                        # STEP 10: DIRECT URL DOWNLOAD (MEMORY BANK METHOD)
                        # =======================================================
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
                        
                    # --- META AI GENERIC ERROR SCREEN HANDLER ---
                    except MetaAIErrorException as me:
                        print(f"\n  [🚨] {me}")
                        print("  [System] Forcing a fresh project creation via Vibes.ai home...")
                        project_created = False
                        clips_in_current_project = 0
                        continue

                    # --- ACCOUNT SWITCHING CATCHER ---
                    except RateLimitException:
                        print(f"  [System] Initiating Account Swap...")
                        try: browser.close()
                        except: pass
                        
                        self.current_session_index += 1
                        if self.current_session_index >= len(self.session_dirs):
                            print("\n[FATAL] ALL ACCOUNTS HAVE HIT THEIR RATE LIMITS. Stopping execution.")
                            return
                        
                        print(f"  [System] Switched to '{self.session_dirs[self.current_session_index].name}'. Booting browser...")
                        browser, page = launch_browser(self.session_dirs[self.current_session_index])
                        project_created = False
                        clips_in_current_project = 0
                        swapped_account = True  
                        break 

                    except PlaywrightError as pe:
                        try:
                            # ADDED .first TO PREVENT STRICT MODE VIOLATIONS
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
                        try:
                            # ADDED .first TO PREVENT STRICT MODE VIOLATIONS
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