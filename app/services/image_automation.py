import sys
import time
import base64
import re
import random
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    pass


class GeminiImageScraper:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        
        # --- STRICT ACCOUNT PRIORITY LIST ---
        self.account_order = [
            "gemini_session_sm",
            "gemini_session",
            "gemini_session_pp",
            "gemini_session_jio",
        ]
        
        self.session_directories = [base_dir / name for name in self.account_order]
        
        missing_folders = [d.name for d in self.session_directories if not d.exists()]
        if missing_folders:
            print(f"[Warning] The following account folders were not found in {base_dir}:")
            for missing in missing_folders:
                print(f" - {missing}")

        valid_sessions = [d for d in self.session_directories if d.exists()]
        if not valid_sessions:
            print("[Warning] No valid session folders found. Defaulting to Gemini_Session_1")
            self.session_directories = [base_dir / "Gemini_Session_1"]
        else:
            self.session_directories = valid_sessions

        self.current_session_idx = 0
        self.session_dir = self.session_directories[self.current_session_idx]

        self.new_chat_every_x = 12
        self.max_retries = 1
        self.limit_cooldown_seconds = 300
        self.HEADLESS_MODE = False

    def _get_clean_name(self, timestamp: str) -> str:
        return timestamp.replace(".", "_")

    def _click_new_chat(self, page):
        try:
            print("Resetting context: Severing state to prevent bleed-over...")
            page.goto("https://gemini.google.com/", wait_until="domcontentloaded")
            page.wait_for_selector('div[role="textbox"]', timeout=15000)
            time.sleep(2.5) # Giving a human-like pause after loading
        except Exception as e:
            print(f"Warning: Failed to reset chat. Error: {e}")

    def _get_latest_response_text(self, page):
        try:
            js_text = """() => {
                const blocks = document.querySelectorAll('message-content, .message-content, [data-message-author-role="model"]');
                if (blocks.length > 0) {
                    return blocks[blocks.length - 1].innerText.toLowerCase();
                }
                return "";
            }"""
            return page.evaluate(js_text)
        except Exception:
            return ""

    def _switch_account(self, playwright_instance, current_context):
        """Closes current session and boots up the next available Google account."""
        print(f"\n[Engine] Closing rate-limited session: {self.session_dir.name}")
        current_context.close()

        self.current_session_idx = (self.current_session_idx + 1) % len(self.session_directories)
        self.session_dir = self.session_directories[self.current_session_idx]

        print(f"[Engine] 🔄 PIVOTING TO NEW ACCOUNT: {self.session_dir.name}")

        new_context = playwright_instance.chromium.launch_persistent_context(
            user_data_dir=str(self.session_dir),
            headless=self.HEADLESS_MODE,
            viewport={"width": 1280, "height": 720},
            args=["--disable-blink-features=AutomationControlled"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        new_page = new_context.new_page()
        print(f"Navigating to Gemini as {self.session_dir.name}...")
        new_page.goto("https://gemini.google.com", wait_until="domcontentloaded")
        new_page.wait_for_selector('div[role="textbox"]', timeout=15000)
        
        return new_context, new_page

    def setup_session(self):
        """Phase 0: Log in to a specific account and save cookies."""
        print("\n--- GEMINI MULTI-ACCOUNT SETUP ---")
        for d in self.account_order:
            status = "[Exists]" if (self.base_dir / d).exists() else "[Missing]"
            print(f" - {d} {status}")
            
        new_name = input("\nEnter folder name to setup/login (e.g., gemini_session_sm): ").strip()
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
            page.goto("https://gemini.google.com")
            
            input("\n👉 Log in fully. Once you see the Gemini dashboard, press ENTER here...")
            context.close()
            print(f"[System] Session '{new_name}' saved successfully!")

    def generate_images(self, input_file: Path, output_dir: Path):
        """Phase 2: High-speed reactive image scraping loop with Human Pacing."""
        if not self.session_directories:
            raise Exception("\n[!] No session data found. Run setup_session() first!")
        
        output_dir.mkdir(parents=True, exist_ok=True)

        with open(input_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]

        print(f"\n[Scraper] Found {len(lines)} image prompts.")
        print(f"[Scraper] Active Account Pool: {len(self.session_directories)} sessions.")
        print(f"[Scraper] Starting with: {self.session_dir.name}")

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self.session_dir),
                headless=self.HEADLESS_MODE,
                viewport={"width": 1280, "height": 720},
                args=["--disable-blink-features=AutomationControlled"],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            page = context.new_page()
            page.goto("https://gemini.google.com", wait_until="domcontentloaded")
            page.wait_for_selector('div[role="textbox"]', timeout=15000)

            line_idx = 0 
            while line_idx < len(lines):
                line = lines[line_idx]
                # Update regex to capture the gapless [start-end] format
                match = re.search(r"\[([\d_]+)-([\d_]+)\]\s*(.*)", line)
                if not match:
                    line_idx += 1
                    continue
                
                # Extract the pre-formatted timestamps
                safe_start, safe_end, prompt = match.groups()
                file_name = f"[{safe_start}-{safe_end}]_image.png"
                output_path = output_dir / file_name

                if output_path.exists():
                    print(f"\n[{line_idx+1}/{len(lines)}] SKIPPING: {file_name} already exists.")
                    line_idx += 1
                    continue

                if line_idx > 0 and line_idx % self.new_chat_every_x == 0:
                    self._click_new_chat(page)

                print(f"\nProcessing [{line_idx+1}/{len(lines)}] via {self.session_dir.name}: {file_name}")
                rate_limit_triggered = False

                for attempt in range(self.max_retries):
                    try:
                        # 1. BUBBLE ISOLATION
                        js_get_bubble_count = "() => document.querySelectorAll('message-content, [data-message-author-role=\"model\"]').length"
                        bubble_count_before = page.evaluate(js_get_bubble_count)
                        
                        try:
                            page.wait_for_selector('button[aria-label*="Stop"], button[aria-label*="stop"]', state="hidden", timeout=15000)
                        except Exception:
                            pass 

                        # 2. HYBRID PROMPT INJECTION (Human-paced typing + instant prompt paste)
                        box = page.locator('div[role="textbox"]')
                        box.wait_for(state="visible", timeout=10000)
                        box.click()
                        box.fill("")
                        time.sleep(1)
                        
                        # Step A: Type prefix slowly like a real human (50ms to 100ms per character)
                        prefix = "Directly Create an image with this below prompt:"
                        box.press_sequentially(prefix, delay=random.randint(50, 100))
                        time.sleep(0.5) # Take a breath
                        
                        # Step B: Perform explicit Shift + Enter
                        page.keyboard.down("Shift")
                        page.keyboard.press("Enter")
                        page.keyboard.up("Shift")
                        time.sleep(0.5) # Take a breath
                        
                        # Step C: Instant insert of the 800-character prompt
                        page.keyboard.insert_text(prompt)
                        time.sleep(1.0) # Pause after pasting a huge wall of text
                        
                        # Step D: Type final space to ensure UI state activation
                        page.keyboard.press("Space")
                        time.sleep(1.0) # Hover over the send button...

                        send_button = page.locator('button[aria-label*="Send message"], button[aria-label*="Send"], button[title*="Send"]')
                        send_button.wait_for(state="visible", timeout=10000)
                        send_button.click()
                        
                        print(f"Generating (Attempt {attempt + 1}/{self.max_retries})... Waiting for image DOM node...")

                        # 3. REACTIVE DOM OBSERVER
                        js_wait_condition = f"""() => {{
                            const blocks = document.querySelectorAll('message-content, [data-message-author-role="model"]');
                            if (blocks.length <= {bubble_count_before}) return false;
                            
                            const latestBlock = blocks[blocks.length - 1];
                            
                            // Check for fully loaded image node
                            const imgs = Array.from(latestBlock.querySelectorAll('img')).filter(i => 
                                i.complete && (i.naturalWidth > 150 || i.width > 150)
                            );
                            if (imgs.length > 0) return "IMAGE_READY";
                            
                            // Check for error text / policy / rate limit
                            const txt = latestBlock.innerText.toLowerCase();
                            if (txt.includes("limit") || txt.includes("quota") || txt.includes("try again")) return "RATE_LIMIT";
                            if (txt.includes("can't") || txt.includes("cannot") || txt.includes("policy") || txt.includes("refuse")) return "POLICY_BLOCK";
                            
                            return false;
                        }}"""

                        try:
                            dom_status = page.wait_for_function(js_wait_condition, timeout=120000).json_value()
                        except Exception:
                            dom_status = "TIMEOUT"

                        if dom_status == "IMAGE_READY":
                            # 🛑 DEFINITE HARD WAIT: Gives the browser GPU plenty of time to paint the pixels
                            print("  [Wait] Image detected. Giving it 6 seconds to fully render to prevent corruption...")
                            time.sleep(10.0)
                            
                            # 4. EXTRACT CANVAS DATA
                            js_extract = """() => {
                                const blocks = document.querySelectorAll('message-content, [data-message-author-role="model"]');
                                const latestBlock = blocks[blocks.length - 1];
                                const imgs = Array.from(latestBlock.querySelectorAll('img')).filter(i => 
                                    i.complete && (i.naturalWidth > 150 || i.width > 150)
                                );
                                
                                if (imgs.length === 0) return null;
                                const targetImg = imgs[0]; 
                                
                                const canvas = document.createElement('canvas');
                                canvas.width = targetImg.naturalWidth || targetImg.width;
                                canvas.height = targetImg.naturalHeight || targetImg.height;
                                const ctx = canvas.getContext('2d');
                                ctx.drawImage(targetImg, 0, 0);
                                return canvas.toDataURL('image/png');
                            }"""
                            
                            data = page.evaluate(js_extract)
                            if data:
                                header, encoded = data.split(",", 1)
                                with open(output_path, 'wb') as f:
                                    f.write(base64.b64decode(encoded))
                                print(f"  [✓] Success! Image rendered & saved perfectly to: {output_path.name}")
                                break 
                            else:
                                raise Exception("Failed to pull canvas data.")

                        elif dom_status == "RATE_LIMIT":
                            print(f"  [!] RATE LIMIT DETECTED on account: {self.session_dir.name}")
                            rate_limit_triggered = True
                            break

                        elif dom_status == "POLICY_BLOCK":
                            print("  [!] CONTENT POLICY BLOCK: Gemini refused this prompt. Skipping.")
                            break

                        else:
                            raise Exception("Generation timed out (No image node created within 120s).")

                    except Exception as e:
                        print(f"  [Error] Attempt {attempt + 1}: {e}")
                        self._click_new_chat(page)
                        if attempt >= self.max_retries - 1:
                            print(f"  [!] Prompt failed after {self.max_retries} attempts. Moving on.")

                # --- MULTI-ACCOUNT ROTATION LOGIC ---
                if rate_limit_triggered:
                    if len(self.session_directories) > 1:
                        context, page = self._switch_account(p, context)
                        continue 
                    else:
                        print(f"Only 1 account configured. Pausing script for {self.limit_cooldown_seconds / 60} minutes...")
                        time.sleep(self.limit_cooldown_seconds)
                        self._click_new_chat(page)
                        continue
                
                line_idx += 1
                
                # Human wait between prompts
                cooldown = random.uniform(3.0, 7.0)
                print(f"Cooling down for {cooldown:.1f}s before next prompt...")
                time.sleep(cooldown)

            context.close()
            print("\n[System] Image Batch processing complete!")