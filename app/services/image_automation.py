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
        # Add your folder names here in the EXACT order you want them used.
        # Do NOT include the accounts you use for daily coding/urgent tasks to protect their rate limits.
        self.account_order = [
            "gemini_session_sm",
            "gemini_session",
            "gemini_session_pp",
            "gemini_session_jio",
            # Add more here as needed: "Gemini_Session_Burner1", etc.
        ]
        
        # Map the folder names to actual Path objects
        self.session_directories = [base_dir / name for name in self.account_order]
        
        # Verify the folders actually exist before starting
        missing_folders = [d.name for d in self.session_directories if not d.exists()]
        if missing_folders:
            print(f"[Warning] The following account folders were not found in {base_dir}:")
            for missing in missing_folders:
                print(f" - {missing}")
            print("Make sure to run setup_session() for these accounts if you want to use them.\n")

        # Fallback just in case the list is empty or folders don't exist
        valid_sessions = [d for d in self.session_directories if d.exists()]
        if not valid_sessions:
            print("[Warning] No valid session folders found. Defaulting to Gemini_Session_1")
            self.session_directories = [base_dir / "Gemini_Session_1"]
        else:
            self.session_directories = valid_sessions

        self.current_session_idx = 0
        # Renamed back to session_dir so master_forge.py doesn't crash!
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
            time.sleep(2)
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
        """Closes the current session and boots up the next available Google account."""
        print(f"\n[Engine] Closing rate-limited session: {self.session_dir.name}")
        current_context.close()

        # Rotate to the next index
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
        """Phase 0: Run this to log in to a specific account and save its cookies."""
        print("\n--- GEMINI MULTI-ACCOUNT SETUP ---")
        print("Your configured priority list:")
        for d in self.account_order:
            status = "[Exists]" if (self.base_dir / d).exists() else "[Missing]"
            print(f" - {d} {status}")
            
        new_name = input("\nEnter the folder name to setup/login (must match your list, e.g., Gemini_Session_SM): ").strip()
        if not new_name:
            print("Aborted.")
            return
            
        target_dir = self.base_dir / new_name

        with sync_playwright() as p:
            print(f"\nLaunching browser for '{new_name}'... Please log in to your Google account.")
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(target_dir),
                headless=False, # Force visible for manual login
                viewport={"width": 1280, "height": 720},
                args=["--disable-blink-features=AutomationControlled"],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.goto("https://gemini.google.com")
            
            input("\n👉 Log in fully. Once you see the Gemini dashboard, press ENTER here to save and exit...")
            context.close()
            print(f"[System] Session '{new_name}' saved successfully!")

    def generate_images(self, input_file: Path, output_dir: Path):
        """Phase 2: The automated image scraping loop with Auto-Account Rotation."""
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

            # Using a while loop so we can retry the EXACT same line if an account swaps
            line_idx = 0 
            while line_idx < len(lines):
                line = lines[line_idx]
                match = re.search(r"\[([\d\.]+)\]\s*(.*)", line)
                if not match:
                    line_idx += 1
                    continue
                
                timestamp, prompt = match.groups()
                file_name = f"[{self._get_clean_name(timestamp)}]_image.png"
                output_path = output_dir / file_name

                # --- SMART RESUME ---
                if output_path.exists():
                    print(f"\n[{line_idx+1}/{len(lines)}] SKIPPING: {file_name} already exists.")
                    line_idx += 1
                    continue

                if line_idx > 0 and line_idx % self.new_chat_every_x == 0:
                    self._click_new_chat(page)

                print(f"\nProcessing [{line_idx+1}/{len(lines)}] via {self.session_dir.name}: {file_name}")
                
                rate_limit_triggered = False

                # --- RETRY LOOP ---
                for attempt in range(self.max_retries):
                    try:
                        # 1. BUBBLE ISOLATION
                        js_get_bubble_count = "() => document.querySelectorAll('message-content, [data-message-author-role=\"model\"]').length"
                        bubble_count_before = page.evaluate(js_get_bubble_count)
                        
                        try:
                            page.wait_for_selector('button[aria-label*="Stop"], button[aria-label*="stop"]', state="hidden", timeout=30000)
                        except Exception:
                            pass 

                        # 2. Type and send the prompt
                        box = page.locator('div[role="textbox"]')
                        box.wait_for(state="visible", timeout=10000)
                        box.click()
                        box.fill("") 
                        
                        box.press_sequentially("Directly Create an image with this below prompt:", delay=random.randint(2, 5), timeout=0)
                        
                        page.keyboard.down("Shift")
                        page.keyboard.press("Enter")
                        page.keyboard.up("Shift")
                        
                        box.press_sequentially(prompt, delay=random.randint(2, 5), timeout=0)
                        
                        send_button = page.locator('button[aria-label*="Send message"], button[aria-label*="Send"], button[title*="Send"]')
                        send_button.wait_for(state="visible", timeout=15000)
                        time.sleep(0.5)
                        send_button.click()
                        
                        print(f"Generating (Attempt {attempt + 1}/{self.max_retries})...")
                        start = time.time()
                        found = False
                        
                        # 3. POLL FOR IMAGE BUBBLE
                        while time.time() - start < 85:
                            js_check_new_bubble = f"""() => {{
                                const blocks = document.querySelectorAll('message-content, [data-message-author-role="model"]');
                                if (blocks.length <= {bubble_count_before}) return false; 
                                
                                const latestBlock = blocks[blocks.length - 1];
                                const imgs = Array.from(latestBlock.querySelectorAll('img')).filter(i => i.width > 150 && i.complete);
                                return imgs.length > 0;
                            }}"""
                            
                            if page.evaluate(js_check_new_bubble):
                                found = True
                                time.sleep(3) 
                                break
                            time.sleep(2)
                        
                        if found:
                            # 4. EXTRACT IMAGE
                            time.sleep(4)
                            js_extract = f"""() => {{
                                const blocks = document.querySelectorAll('message-content, [data-message-author-role="model"]');
                                const latestBlock = blocks[blocks.length - 1];
                                const imgs = Array.from(latestBlock.querySelectorAll('img')).filter(i => i.width > 150 && i.complete);
                                
                                if (imgs.length === 0) return null;
                                const targetImg = imgs[0]; 
                                
                                const canvas = document.createElement('canvas');
                                canvas.width = targetImg.naturalWidth || targetImg.width;
                                canvas.height = targetImg.naturalHeight || targetImg.height;
                                canvas.getContext('2d').drawImage(targetImg, 0, 0);
                                return canvas.toDataURL('image/png');
                            }}"""
                            
                            data = page.evaluate(js_extract)
                            if data:
                                header, encoded = data.split(",", 1)
                                with open(output_path, 'wb') as f:
                                    f.write(base64.b64decode(encoded))
                                print(f"Success! Saved to: {output_path.name}")
                                break 
                            else:
                                raise Exception("Failed to pull canvas data.")
                        else:
                            latest_text = self._get_latest_response_text(page)
                            if "limit" in latest_text or "try again" in latest_text or "quota" in latest_text:
                                print(f"[!] RATE LIMIT DETECTED on account: {self.session_dir.name}")
                                rate_limit_triggered = True
                                break # Break the attempt loop to trigger account rotation
                                
                            elif "can't" in latest_text or "cannot" in latest_text or "policy" in latest_text:
                                print("[!] CONTENT POLICY BLOCK: Gemini refused to generate this image. Skipping prompt.")
                                break 
                            else:
                                raise Exception("Generation timed out.")

                    except Exception as e:
                        print(f"Error on attempt {attempt + 1}: {e}")
                        print("Clearing state to prevent image bleed-over...")
                        self._click_new_chat(page)
                        
                        if attempt >= self.max_retries - 1:
                            print(f"Failed completely after {self.max_retries} attempts. Moving to next prompt.")

                # --- MULTI-ACCOUNT ROTATION LOGIC ---
                if rate_limit_triggered:
                    if len(self.session_directories) > 1:
                        # Swap accounts and loop back around. We DO NOT increment line_idx, 
                        # so the engine tries this exact same image prompt again on the new account.
                        context, page = self._switch_account(p, context)
                        continue 
                    else:
                        print(f"Only 1 account configured. Pausing script for {self.limit_cooldown_seconds / 60} minutes...")
                        time.sleep(self.limit_cooldown_seconds)
                        self._click_new_chat(page)
                        continue
                
                # If we successfully made the image (or got a hard policy block), move to the next prompt
                line_idx += 1
                
                print("Cooling down before next prompt...")
                time.sleep(random.uniform(3, 6))

            context.close()
            print("\n[System] Image Batch processing complete!")