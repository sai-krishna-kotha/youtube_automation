import sys, os
import time
import base64
import re
import random
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    pass

class GoogleFlowScraper:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        
        # --- ACCOUNT CONFIGURATION ---
        self.account_order = [
            "flow_session_1",
            "flow_session_2",
        ]
        
        self.session_directories = [base_dir / name for name in self.account_order]
        
        missing_folders = [d.name for d in self.session_directories if not d.exists()]
        if missing_folders:
            print(f"[Warning] The following account folders were not found in {base_dir}:")
            for missing in missing_folders:
                print(f" - {missing}")

        valid_sessions = [d for d in self.session_directories if d.exists()]
        if not valid_sessions:
            print("[Warning] No valid session folders found. Defaulting to flow_session_1")
            self.session_directories = [base_dir / "flow_session_1"]
        else:
            self.session_directories = valid_sessions

        # Default fallback (overridden dynamically during generate_images)
        self.session_dir = self.session_directories[0] if self.session_directories else None

        # --- FLOW CONFIGURATION ---
        self.FLOW_URL = "https://labs.google/fx/tools/flow"
        self.HEADLESS_MODE = False
        self.MAX_RETRIES = 3
        self.GENERATE_TIMEOUT = 80000 
        self.DOWNLOAD_DELAY = 4 
        
        # Optimized prompt prefix for maximum AI comprehension (Faces Only)
        self.PROMPT_PREFIX = "Create an image based on the prompt below. Ensure every character has clear, expressive facial features(eyes, mouth) appropriate for the situation. Do not generate blank or empty faces:\n\n"        
        
        self.PROMPT_BOX_SELECTOR = 'div[data-slate-editor="true"][role="textbox"]'
        self.GENERATE_BTN_SELECTOR = 'button:has(i:text-is("arrow_forward"))'

    def setup_session(self):
        """Phase 0: Log in to a specific account and save cookies."""
        print("\n--- GOOGLE FLOW MULTI-ACCOUNT SETUP ---")
        for d in self.account_order:
            status = "[Exists]" if (self.base_dir / d).exists() else "[Missing]"
            print(f" - {d} {status}")
            
        new_name = input("\nEnter folder name to setup/login (e.g., flow_session_1): ").strip()
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
        # CHANGED BACK: Uses the "New project" method to safely clear a stuck/timed-out generation.
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

    def generate_images(self, input_file: Path, output_dir: Path):
        """Phase 1.5 Integration: Automated Image Generation."""
        if not self.session_directories:
            raise Exception("\n[!] No session data found. Run setup_session() first!")
            
        output_dir.mkdir(parents=True, exist_ok=True)

        with open(input_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]

        print(f"\n[Scraper] Found {len(lines)} image prompts.")
        print(f"[Scraper] Active Account Pool: {len(self.session_directories)} sessions.")
        
        with sync_playwright() as p:
            # --- THE AUTO-DETECT LOAD BALANCER ---
            context = None
            active_session_dir = None
            
            print("\n[System] Searching for an available session...")
            for session_name in self.account_order:
                temp_dir = self.base_dir / session_name
                if not temp_dir.exists():
                    continue
                
                # --- OS LOCK CHECK ---
                is_locked = False
                lock_file = temp_dir / "lockfile" 
                
                if lock_file.exists():
                    try:
                        with open(lock_file, 'a'):
                            pass
                    except OSError:
                        is_locked = True

                if is_locked:
                    print(f"  [!] '{session_name}' is currently active in another window. Skipping...")
                    continue
                # ---------------------
                
                try:
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=str(temp_dir),
                        headless=self.HEADLESS_MODE,
                        viewport={"width": 1280, "height": 720},
                        args=["--disable-blink-features=AutomationControlled"],
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
                    active_session_dir = temp_dir
                    self.session_dir = active_session_dir
                    print(f"  [✓] Successfully locked '{session_name}' for this project!")
                    break
                except Exception as e:
                    print(f"  [!] Failed to launch '{session_name}': {e}")
            
            if not context:
                raise Exception("\n[!] All sessions are currently in use. Please wait for the other process to finish or add a new session.")
            
            page = context.new_page()
            page.goto(self.FLOW_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)

            # --- SMART SIGN-IN CHECK ---
            print("  -> Checking for 'Sign in' landing page...")
            try:
                sign_in_btn = page.locator('text="Sign in"').first
                if sign_in_btn.is_visible(timeout=5000):
                    print("  -> 'Sign in' screen detected. Clicking to authenticate using saved session...")
                    sign_in_btn.click()
                    page.wait_for_load_state("networkidle", timeout=30000)
                else:
                    print("  -> Active session verified.")
            except Exception:
                print("  -> No 'Sign in' button found. Proceeding...")

            # Initial "New project" click for starting the batch cleanly
            try:
                new_btn = page.locator('text="New project"').first
                new_btn.wait_for(state="visible", timeout=7000)
                new_btn.click()
                time.sleep(3)
            except Exception:
                pass

            line_idx = 0 
            while line_idx < len(lines):
                line = lines[line_idx]
                match = re.search(r"\[([\d_]+)-([\d_]+)\]\s*(.*)", line)
                if not match:
                    line_idx += 1
                    continue
                
                start_s, end_s, prompt = match.groups()
                file_name = f"[{start_s}-{end_s}]_image.png"
                output_path = output_dir / file_name

                if output_path.exists():
                    print(f"\n[{line_idx+1}/{len(lines)}] SKIPPING: {file_name} already exists.")
                    line_idx += 1
                    continue

                print(f"\nProcessing [{line_idx+1}/{len(lines)}] via {self.session_dir.name}: {file_name}")
                success = False
                
                for attempt in range(self.MAX_RETRIES):
                    try:
                        # 1. Clear old prompt immediately before starting
                        clear_btn = page.locator('button:has(i:text-is("close"))').first
                        if clear_btn.is_visible(timeout=3000):
                            clear_btn.click()
                            time.sleep(0.5)

                        # 2. Snapshot Baseline
                        baseline_srcs = page.evaluate("() => Array.from(document.querySelectorAll('img')).map(i => i.src)")

                        # 3. Inject Prompt Safely
                        box = page.locator(self.PROMPT_BOX_SELECTOR).first
                        box.wait_for(state="visible", timeout=45000)
                        box.fill("")
                        time.sleep(0.5)
                        
                        full_prompt = f"{self.PROMPT_PREFIX}{prompt}"
                        prompt_lines = full_prompt.split('\n')
                        
                        for i, p_line in enumerate(prompt_lines):
                            if p_line:
                                page.keyboard.insert_text(p_line)
                            if i < len(prompt_lines) - 1:
                                page.keyboard.press("Shift+Enter")
                        
                        time.sleep(0.5)
                        page.keyboard.press("Space")
                        time.sleep(1)

                        # 4. Generate
                        try:
                            btn = page.locator(self.GENERATE_BTN_SELECTOR).first
                            btn.click(timeout=5000)
                        except Exception:
                            print("  -> Button click failed. Falling back to Enter key submission...")
                            page.keyboard.press("Enter")
                            
                        print(f"  -> Prompt submitted. Waiting for NEW image...")

                        # 5. Wait for Render (Increased minimum width to avoid UI placeholders)
                        js_wait_for_new = """(baseline) => {
                            const imgs = Array.from(document.querySelectorAll('img')).filter(i => 
                                i.complete && (i.naturalWidth > 400 || i.width > 400) && !i.src.includes('avatar')
                            );
                            const newImgs = imgs.filter(i => !baseline.includes(i.src));
                            return newImgs.length > 0;
                        }"""
                        
                        page.wait_for_function(js_wait_for_new, arg=baseline_srcs, timeout=self.GENERATE_TIMEOUT)
                        print(f"  -> Image rendered! Waiting {self.DOWNLOAD_DELAY}s for data to finalize...")
                        time.sleep(self.DOWNLOAD_DELAY)

                        # 6. Extract
                        js_extract_src = """(baseline) => {
                            const imgs = Array.from(document.querySelectorAll('img')).filter(i => 
                                i.complete && (i.naturalWidth > 400 || i.width > 400) && !i.src.includes('avatar')
                            );
                            const newImgs = imgs.filter(i => !baseline.includes(i.src));
                            return newImgs.length > 0 ? newImgs[0].src : null;
                        }"""
                        
                        img_src = page.evaluate(js_extract_src, arg=baseline_srcs)
                        if not img_src:
                            raise Exception("Image element appeared but src was null.")
                            
                        extracted = False
                        if img_src.startswith('http'):
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

                        if extracted:
                            # 7. STRICT VERIFICATION: Do not continue until the file is physically on the drive
                            if output_path.exists():
                                print(f"  [✓] Verified on disk securely: {output_path.name}")
                                success = True
                                break
                            else:
                                raise Exception("Data extracted but file failed to write to disk.")
                        else:
                            raise Exception("Failed to extract data via Network and Canvas.")

                    except Exception as e:
                        print(f"  [Error] Attempt {attempt + 1}: {e}")
                        if attempt < self.MAX_RETRIES - 1:
                            self.reset_workspace(page)
                
                if not success:
                    print(f"  [!] Failed after {self.MAX_RETRIES} attempts. Skipping to next.")

                line_idx += 1
                
                # Added an explicit tiny wait before starting the next loop iteration
                # to ensure the UI is fully stable after the download.
                time.sleep(random.uniform(1.0, 2.0))

            context.close()
            print("\n[System] Image Batch processing complete!")