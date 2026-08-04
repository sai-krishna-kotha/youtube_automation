import sys, os
import time
import base64
import random
from pathlib import Path

from app.utils.timeline_parser import TimelineParser

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    pass

class GoogleFlowScraper:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        
        # --- ACCOUNT CONFIGURATION ---
        self.account_order = [
            "session_1",
            "session_2",
            "session_3",
        ]
        
        self.session_directories = [base_dir / name for name in self.account_order]
        
        missing_folders = [d.name for d in self.session_directories if not d.exists()]
        if missing_folders:
            print(f"[Warning] The following account folders were not found in {base_dir}:")
            for missing in missing_folders:
                print(f" - {missing}")

        valid_sessions = [d for d in self.session_directories if d.exists()]
        if not valid_sessions:
            print("[Warning] No valid session folders found. Defaulting to session_1")
            self.session_directories = [base_dir / "session_1"]
        else:
            self.session_directories = valid_sessions

        self.session_dir = None
        self.current_session_idx = 0 # Tracks the active account in the array

        # --- FLOW CONFIGURATION ---
        self.FLOW_URL = "https://labs.google/fx/tools/flow"
        self.HEADLESS_MODE = False
        self.MAX_RETRIES = 3
        self.DOWNLOAD_DELAY = 1 
        
        # --- ⚙️ MASTER TOGGLE FOR IMAGE CHAINING ⚙️ ---
        self.ENABLE_IMAGE_CHAINING = False 
        self.GENERATE_TIMEOUT = 120000 if self.ENABLE_IMAGE_CHAINING else 90000 
        self.PROMPT_PREFIX = "Create an image based on the prompt below. Ensure every character has clear, expressive facial entities(EYES, MOUTH mandatory) appropriate for the situation. Do not generate blank or empty faces:\n\n"        
        self.CHAINED_PREFIX = "Maintain the exact character design, art style, and color palette from the attached reference image. Change the action, pose, and background strictly according to the prompt below. Ensure clear facial features:\n\n"

        self.PROMPT_BOX_SELECTOR = 'div[data-slate-editor="true"][role="textbox"]'
        self.GENERATE_BTN_SELECTOR = 'button:has(i:text-is("arrow_forward"))'

    def setup_session(self):
        """Phase 0: Log in to a specific account and save cookies."""
        print("\n--- GOOGLE FLOW MULTI-ACCOUNT SETUP ---")
        for d in self.account_order:
            status = "[Exists]" if (self.base_dir / d).exists() else "[Missing]"
            print(f" - {d} {status}")
            
        new_name = input("\nEnter folder name to setup/login (e.g., session_1): ").strip()
        if not new_name:
            print("Aborted.")
            return
            
        target_dir = self.base_dir / new_name

        with sync_playwright() as p:
            print(f"\nLaunching browser for '{new_name}'... Please log in.")
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(target_dir),
                headless=False,
                viewport={"width": 1280, "height": 720},
                args=["--disable-blink-features=AutomationControlled"],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.goto(self.FLOW_URL)
            
            input("\n[✓] Log in fully. Once you see the Google Flow dashboard, press ENTER here...")
            context.close()
            print(f"[System] Session '{new_name}' saved successfully!")

    def reset_workspace(self, page):
        print("  [System] Timeout detected. Forcing a hard UI reset via New Project...")
        try:
            page.goto(self.FLOW_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            new_btn = page.locator('text="New project"').first
            if new_btn.is_visible(timeout=7000):
                new_btn.click()
                time.sleep(3)
        except Exception as e:
            print(f"  [Error] Failed to reset workspace: {e}")

    def _launch_and_prep_session(self, p, session_dir):
        """Helper to hot-load a browser context and prep the workspace."""
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(session_dir),
            headless=self.HEADLESS_MODE,
            viewport={"width": 1280, "height": 720},
            args=["--disable-blink-features=AutomationControlled"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.goto(self.FLOW_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        try:
            sign_in_btn = page.locator('text="Sign in"').first
            if sign_in_btn.is_visible(timeout=5000):
                print("  -> 'Sign in' screen detected. Clicking to authenticate using saved session...")
                sign_in_btn.click()
                page.wait_for_load_state("networkidle", timeout=120000)
        except Exception:
            pass

        try:
            new_btn = page.locator('text="New project"').first
            if new_btn.is_visible(timeout=7000):
                new_btn.click()
                time.sleep(3)
        except Exception:
            pass
            
        return context, page

    def generate_images(self, input_file: Path, output_dir: Path):
        """Phase 1.5 Integration: Automated Image Generation with Auto-Rotation."""
        if not self.session_directories:
            raise Exception("\n[!] No session data found. Run setup_session() first!")
            
        output_dir.mkdir(parents=True, exist_ok=True)

        with open(input_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]

        print(f"\n[Scraper] Found {len(lines)} image prompts.")
        print(f"[Scraper] Active Account Pool: {len(self.session_directories)} sessions.")
        
        with sync_playwright() as p:
            # Try to find the first unlocked session
            self.current_session_idx = -1
            for idx, session_dir in enumerate(self.session_directories):
                lock_file = session_dir / "lockfile"
                is_locked = False
                if lock_file.exists():
                    try:
                        with open(lock_file, 'a'): pass
                    except OSError:
                        is_locked = True
                
                if not is_locked:
                    self.current_session_idx = idx
                    break
                    
            if self.current_session_idx == -1:
                raise Exception("\n[!] All sessions are locked or currently in use.")

            self.session_dir = self.session_directories[self.current_session_idx]
            print(f"\n[System] Locking initial session: '{self.session_dir.name}'")
            context, page = self._launch_and_prep_session(p, self.session_dir)

            line_idx = 0 
            previous_image_path = None 
            
            while line_idx < len(lines):
                line = lines[line_idx]
                
                parsed_clip = TimelineParser.parse_prompt_line(line)
                if not parsed_clip:
                    line_idx += 1
                    continue
                
                prompt = parsed_clip.content
                file_name = parsed_clip.expected_filename
                output_path = output_dir / file_name

                if output_path.exists():
                    print(f"\n[{line_idx+1}/{len(lines)}] SKIPPING: {file_name} already exists.")
                    previous_image_path = output_path 
                    line_idx += 1
                    continue

                print(f"\nProcessing [{line_idx+1}/{len(lines)}] via {self.session_dir.name}: {file_name}")
                success = False
                account_switched = False
                
                for attempt in range(self.MAX_RETRIES):
                    try:
                        clear_btn = page.locator('button:has(i:text-is("close"))').first
                        if clear_btn.is_visible(timeout=3000):
                            clear_btn.click()
                            time.sleep(1.0)

                        dynamic_prefix = self.PROMPT_PREFIX
                        
                        if self.ENABLE_IMAGE_CHAINING and previous_image_path and previous_image_path.exists():
                            try:
                                plus_btn = page.locator('button:has(i:text-is("add_2"))').first
                                if plus_btn.is_visible(timeout=5000):
                                    plus_btn.click()
                                    time.sleep(1.5) 

                                page.set_input_files('input[type="file"]', str(previous_image_path), timeout=10000)
                                add_prompt_btn = page.locator('button:has-text("Add to Prompt")').first
                                
                                button_found = False
                                for _ in range(20): 
                                    if add_prompt_btn.is_visible():
                                        button_found = True
                                        break
                                    time.sleep(1.0)
                                
                                if button_found:
                                    add_prompt_btn.click()
                                    time.sleep(2.0) 
                                    dynamic_prefix = self.CHAINED_PREFIX
                            except Exception:
                                page.keyboard.press("Escape")
                                time.sleep(1.0)

                        baseline_srcs = page.evaluate("() => Array.from(document.querySelectorAll('img')).map(i => i.src)")

                        box = page.locator(self.PROMPT_BOX_SELECTOR).first
                        box.wait_for(state="visible", timeout=45000)
                        box.fill("")
                        time.sleep(0.5)
                        
                        full_prompt = f"{dynamic_prefix}{prompt}"
                        prompt_lines = full_prompt.split('\n')
                        
                        for i, p_line in enumerate(prompt_lines):
                            if p_line:
                                page.keyboard.insert_text(p_line)
                            if i < len(prompt_lines) - 1:
                                page.keyboard.press("Shift+Enter")
                        
                        time.sleep(0.5)
                        page.keyboard.press("Space")
                        time.sleep(1)

                        try:
                            btn = page.locator(self.GENERATE_BTN_SELECTOR).first
                            btn.click(timeout=5000)
                        except Exception:
                            page.keyboard.press("Enter")
                            
                        print(f"  -> Prompt submitted. Waiting for NEW image...")

                        # --- NEW ACTIVE POLLING SYSTEM ---
                        start_wait = time.time()
                        image_rendered = False
                        limit_reached = False
                        
                        js_wait_for_new = """(baseline) => {
                            const imgs = Array.from(document.querySelectorAll('img')).filter(i => 
                                i.complete && (i.naturalWidth > 400 || i.width > 400) && !i.src.includes('avatar')
                            );
                            const newImgs = imgs.filter(i => !baseline.includes(i.src));
                            return newImgs.length > 0;
                        }"""
                        
                        while time.time() - start_wait < (self.GENERATE_TIMEOUT / 1000):
                            # 1. Check if image generated successfully
                            if page.evaluate(js_wait_for_new, arg=baseline_srcs):
                                image_rendered = True
                                break
                            
                            # 2. Check for the Daily Limit error specifically (Bypassing apostrophe issues)
                            if page.get_by_text("reached the daily limit", exact=False).is_visible():
                                limit_reached = True
                                break
                                
                            time.sleep(1.0)

                        if limit_reached:
                            raise Exception("DAILY_LIMIT_REACHED")
                            
                        if not image_rendered:
                            raise Exception("Timeout waiting for image generation.")

                        # --- EXTRACTION LOGIC ---
                        print(f"  -> Image rendered! Waiting {self.DOWNLOAD_DELAY}s for data to finalize...")
                        time.sleep(self.DOWNLOAD_DELAY)

                        js_extract_src = """(baseline) => {
                            const imgs = Array.from(document.querySelectorAll('img')).filter(i => 
                                i.complete && (i.naturalWidth > 400 || i.width > 400) && !i.src.includes('avatar')
                            );
                            const newImgs = imgs.filter(i => !baseline.includes(i.src));
                            return newImgs.length > 0 ? newImgs[0].src : null;
                        }"""
                        
                        img_src = page.evaluate(js_extract_src, arg=baseline_srcs)
                        extracted = False
                        
                        if img_src and img_src.startswith('http'):
                            try:
                                res = context.request.get(img_src)
                                with open(output_path, 'wb') as f:
                                    f.write(res.body())
                                extracted = True
                            except:
                                pass
                                
                        if not extracted:
                            js_canvas = """(baseline) => {
                                const imgs = Array.from(document.querySelectorAll('img')).filter(i => 
                                    i.complete && (i.naturalWidth > 400 || i.width > 400) && !i.src.includes('avatar')
                                );
                                const newImgs = imgs.filter(i => !baseline.includes(i.src));
                                if (newImgs.length === 0) return null;
                                const target = newImgs[0];
                                const canvas = document.createElement('canvas');
                                canvas.width = target.naturalWidth || target.width;
                                canvas.height = target.naturalHeight || target.height;
                                const ctx = canvas.getContext('2d');
                                ctx.drawImage(target, 0, 0);
                                return canvas.toDataURL('image/png');
                            }"""
                            data = page.evaluate(js_canvas, arg=baseline_srcs)
                            if data:
                                header, encoded = data.split(",", 1)
                                with open(output_path, 'wb') as f:
                                    f.write(base64.b64decode(encoded))
                                extracted = True

                        if extracted and output_path.exists():
                            print(f"  [✓] Verified on disk securely: {output_path.name}")
                            success = True
                            previous_image_path = output_path 
                            break
                        else:
                            raise Exception("Failed to extract data via Network and Canvas.")

                    except Exception as e:
                        error_msg = str(e)
                        
                        # --- NEW ACCOUNT ROTATION LOGIC ---
                        if "DAILY_LIMIT_REACHED" in error_msg:
                            print(f"\n  [🚨] DAILY LIMIT HIT on account: {self.session_dir.name}")
                            context.close()
                            
                            self.current_session_idx += 1
                            if self.current_session_idx >= len(self.session_directories):
                                raise Exception("\n[CRITICAL] All accounts have reached their daily limit! Exiting system.")
                                
                            self.session_dir = self.session_directories[self.current_session_idx]
                            print(f"  [🔄] Hot-swapping to next account: {self.session_dir.name}...")
                            
                            context, page = self._launch_and_prep_session(p, self.session_dir)
                            account_switched = True
                            break # Break retry loop to restart the exact same prompt
                        else:
                            print(f"  [Error] Attempt {attempt + 1}: {error_msg}")
                            if attempt < self.MAX_RETRIES - 1:
                                self.reset_workspace(page)
                
                # If we switched accounts, skip incrementing line_idx so we retry the current line
                if account_switched:
                    continue
                    
                if not success:
                    print(f"  [!] Failed after {self.MAX_RETRIES} attempts. Skipping to next.")

                line_idx += 1
                time.sleep(random.uniform(1.0, 2.0))

            context.close()
            print("\n[System] Image Batch processing complete!")