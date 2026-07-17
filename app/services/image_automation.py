import os
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
        self.session_dir = base_dir / "gemini_session"
        self.new_chat_every_x = 15
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

    def setup_session(self):
        """Phase 0: Run this once to log in and save the authentication cookie."""
        print("\n--- GEMINI AUTHENTICATION SETUP ---")
        with sync_playwright() as p:
            print("Launching browser... Please log in to your Google account.")
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self.session_dir),
                headless=self.HEADLESS_MODE, # Now controlled by the toggle at the very top!
                viewport={"width": 1280, "height": 720},
                args=["--disable-blink-features=AutomationControlled"],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

            )
            page = context.new_page()
            page.goto("https://gemini.google.com")
            
            input("\n👉 Log in fully. Once you see the Gemini dashboard, press ENTER here to save and exit...")
            context.close()
            print("[System] Session saved successfully! You can now run Phase 2.")

    def generate_images(self, input_file: Path, output_dir: Path):
        """Phase 2: The automated image scraping loop."""
        if not self.session_dir.exists():
            raise Exception("\n[!] Session data missing. Please run the 'Setup Gemini Login' from the main menu first!")
        
        output_dir.mkdir(parents=True, exist_ok=True)

        with open(input_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]

        print(f"\n[Scraper] Found {len(lines)} image prompts. Booting up headless browser...")

        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self.session_dir),
                headless=self.HEADLESS_MODE, # Now controlled by the toggle at the very top!
                viewport={"width": 1280, "height": 720},
                args=["--disable-blink-features=AutomationControlled"],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            page = context.new_page()
            print("Navigating to Gemini...")
            page.goto("https://gemini.google.com", wait_until="domcontentloaded")
            page.wait_for_selector('div[role="textbox"]', timeout=15000)

            for i, line in enumerate(lines):
                match = re.search(r"\[([\d\.]+)\]\s*(.*)", line)
                if not match:
                    continue
                
                timestamp, prompt = match.groups()
                file_name = f"[{self._get_clean_name(timestamp)}]_image.png"
                output_path = output_dir / file_name

                # --- SMART RESUME ---
                if output_path.exists():
                    print(f"\n[{i+1}/{len(lines)}] SKIPPING: {file_name} already exists.")
                    continue

                if i > 0 and i % self.new_chat_every_x == 0:
                    self._click_new_chat(page)

                print(f"\nProcessing [{i+1}/{len(lines)}]: {file_name}")
                
                # --- RETRY LOOP ---
                for attempt in range(self.max_retries):
                    try:
                        # 1. BUBBLE ISOLATION: Count response bubbles BEFORE we ask for a new one
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
                        
                        # Type the prefix first
                        box.press_sequentially("Create an image with this below prompt:", delay=random.randint(2, 5), timeout=0)
                        
                        # Simulate Shift+Enter to drop down a line without submitting
                        page.keyboard.down("Shift")
                        page.keyboard.press("Enter")
                        page.keyboard.up("Shift")
                        
                        # Now type the actual prompt
                        box.press_sequentially(prompt, delay=random.randint(2, 5), timeout=0)
                        
                        send_button = page.locator('button[aria-label*="Send message"], button[aria-label*="Send"], button[title*="Send"]')
                        send_button.wait_for(state="visible", timeout=15000)
                        time.sleep(0.5)
                        send_button.click()
                        
                        print(f"Generating (Attempt {attempt + 1}/{self.max_retries})...")
                        start = time.time()
                        found = False
                        
                        # 3. POLL EXCLUSIVELY FOR THE NEW BUBBLE
                        while time.time() - start < 85:
                            # This JS checks if a NEW bubble has appeared, and if it has a fully loaded image inside it
                            js_check_new_bubble = f"""() => {{
                                const blocks = document.querySelectorAll('message-content, [data-message-author-role="model"]');
                                if (blocks.length <= {bubble_count_before}) return false; // New bubble hasn't appeared yet
                                
                                const latestBlock = blocks[blocks.length - 1];
                                // Check for images > 150px that are fully painted (complete)
                                const imgs = Array.from(latestBlock.querySelectorAll('img')).filter(i => i.width > 150 && i.complete);
                                return imgs.length > 0;
                            }}"""
                            
                            if page.evaluate(js_check_new_bubble):
                                found = True
                                time.sleep(3) # Extra buffer for canvas rendering
                                break
                            time.sleep(2)
                        
                        if found:
                            # 4. EXTRACT ONLY FROM THE NEW BUBBLE
                            time.sleep(4)
                            js_extract = f"""() => {{
                                const blocks = document.querySelectorAll('message-content, [data-message-author-role="model"]');
                                const latestBlock = blocks[blocks.length - 1];
                                const imgs = Array.from(latestBlock.querySelectorAll('img')).filter(i => i.width > 150 && i.complete);
                                
                                if (imgs.length === 0) return null;
                                const targetImg = imgs[0]; // Isolate the first image in the NEW bubble
                                
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
                                print(f"RATE LIMIT DETECTED. Pausing script for {self.limit_cooldown_seconds / 60} minutes...")
                                time.sleep(self.limit_cooldown_seconds)
                                self._click_new_chat(page) 
                                continue 
                            elif "can't" in latest_text or "cannot" in latest_text or "policy" in latest_text:
                                print("CONTENT POLICY BLOCK: Gemini refused to generate this image. Skipping prompt.")
                                break 
                            else:
                                raise Exception("Generation timed out.")

                    except Exception as e:
                        print(f"Error on attempt {attempt + 1}: {e}")
                        
                        # STATE SEVERING: If it failed for ANY reason, nuke the chat to prevent the ghost image from arriving late
                        print("Clearing state to prevent image bleed-over...")
                        self._click_new_chat(page)
                        
                        if attempt >= self.max_retries - 1:
                            print(f"Failed completely after {self.max_retries} attempts. Moving to next prompt.")

                print("Cooling down before next prompt...")
                time.sleep(random.uniform(3, 6))

            context.close()
            print("\n[System] Image Batch processing complete!")