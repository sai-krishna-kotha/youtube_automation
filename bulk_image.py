import os
import time
import base64
import re
import random
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
INPUT_FILE = "prompts.txt"
OUTPUT_DIR = "generated_assets"
NEW_CHAT_EVERY_X = 5          # Refreshes the chat context to prevent token bloat
MAX_RETRIES = 2               # How many times to retry a failed prompt before skipping
LIMIT_COOLDOWN_SECONDS = 300  # 5 minutes pause if Gemini says "limit reached" or "try again"

# --- THE TOGGLE ---
HEADLESS_MODE = False         # Set to True to run invisibly, Set to False to watch the browser
# ---------------------

def get_clean_name(timestamp):
    # Converts 64.88 -> 64_88
    return timestamp.replace(".", "_")

def click_new_chat(page):
    """Navigates to the root URL to force a pristine chat session."""
    try:
        print("Resetting context: Starting a fresh chat...")
        page.goto("https://gemini.google.com/", wait_until="domcontentloaded")
        page.wait_for_selector('div[role="textbox"]', timeout=15000)
        time.sleep(2)
    except Exception as e:
        print(f"Warning: Failed to reset chat. Error: {e}")

def get_latest_response_text(page):
    """Scrapes the text of Gemini's most recent response to check for errors."""
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

def process_batch():
    if not os.path.exists("gemini_session"):
        raise Exception("Session data missing. Run auth_session.py first!")
    
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    with open(INPUT_FILE, 'r') as f:
        lines = [line.strip() for line in f if line.strip()]

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir="gemini_session",
            headless=HEADLESS_MODE, # Now controlled by the toggle at the very top!
            viewport={"width": 1280, "height": 720},
            args=["--disable-blink-features=AutomationControlled"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()
        print(f"Navigating to Gemini (Headless: {HEADLESS_MODE})...")
        page.goto("https://gemini.google.com", wait_until="domcontentloaded")
        page.wait_for_selector('div[role="textbox"]', timeout=15000)

        for i, line in enumerate(lines):
            # 1. Parse line
            match = re.search(r"\[([\d\.]+)\]\s*(.*)", line)
            if not match:
                print(f"Skipping malformed line: {line}")
                continue
            
            timestamp, prompt = match.groups()
            file_name = f"{get_clean_name(timestamp)}_image.png"
            output_path = os.path.join(OUTPUT_DIR, file_name)

            # --- SMART RESUME: Skip if already exists ---
            if os.path.exists(output_path):
                print(f"\n[{i+1}/{len(lines)}] SKIPPING: {file_name} already exists in folder.")
                continue

            # 2. Reset Chat Context if threshold is reached
            if i > 0 and i % NEW_CHAT_EVERY_X == 0:
                click_new_chat(page)

            print(f"\nProcessing [{i+1}/{len(lines)}]: {file_name}")
            
            # --- RETRY LOOP FOR RESILIENCY ---
            for attempt in range(MAX_RETRIES):
                try:
                    js_count = """() => {
                        return Array.from(document.querySelectorAll('img')).filter(img => img.width > 150).length;
                    }"""
                    existing_count = page.evaluate(js_count)
                    
                    # Wait for Gemini to be idle
                    try:
                        page.wait_for_selector('button[aria-label*="Stop"], button[aria-label*="stop"]', state="hidden", timeout=30000)
                    except Exception:
                        pass # Ignore and try to proceed

                    # Type Prompt
                    box = page.locator('div[role="textbox"]')
                    box.wait_for(state="visible", timeout=10000)
                    box.click()
                    box.fill("") 
                    box.press_sequentially(prompt, delay=random.randint(2, 5), timeout=0)
                    
                    # Click Send
                    send_button = page.locator('button[aria-label*="Send message"], button[aria-label*="Send"], button[title*="Send"]')
                    send_button.wait_for(state="visible", timeout=15000)
                    time.sleep(0.5)
                    send_button.click()
                    
                    # Wait for generation
                    print(f"Generating (Attempt {attempt + 1}/{MAX_RETRIES})...")
                    start = time.time()
                    found = False
                    
                    while time.time() - start < 75:
                        if page.evaluate(js_count) > existing_count:
                            found = True
                            time.sleep(3) # Let pixels paint
                            break
                        time.sleep(1)
                    
                    # Extract & Save
                    if found:
                        js_extract = f"""() => {{
                            const imgs = Array.from(document.querySelectorAll('img')).filter(i => i.width > 150);
                            if (imgs.length <= {existing_count}) return null;
                            
                            // Grab the first newly generated image
                            const targetImg = imgs[{existing_count}];
                            if (!targetImg) return null;
                            
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
                            print(f"Success! Saved to: {output_path}")
                            break # Break out of retry loop, move to next prompt!
                        else:
                            raise Exception("Failed to pull canvas data.")
                    
                    else:
                        # --- ERROR DIAGNOSTICS ---
                        latest_text = get_latest_response_text(page)
                        
                        if "limit" in latest_text or "try again" in latest_text or "quota" in latest_text:
                            print(f"RATE LIMIT DETECTED. Pausing script for {LIMIT_COOLDOWN_SECONDS / 60} minutes...")
                            time.sleep(LIMIT_COOLDOWN_SECONDS)
                            click_new_chat(page)
                            continue 
                            
                        elif "can't" in latest_text or "cannot" in latest_text or "policy" in latest_text:
                            print("CONTENT POLICY BLOCK: Gemini refused to generate this image. Skipping prompt.")
                            break 
                            
                        else:
                            raise Exception("Generation timed out without a clear text error from Gemini.")

                except Exception as e:
                    print(f"Error on attempt {attempt + 1}: {e}")
                    if attempt < MAX_RETRIES - 1:
                        print("Network drop, block, or crash detected. Reloading page and retrying...")
                        click_new_chat(page)
                        time.sleep(3)
                    else:
                        print(f"Failed completely after {MAX_RETRIES} attempts. Moving to next prompt.")

            # Throttle between successful outputs
            print("Cooling down before next prompt...")
            time.sleep(random.uniform(5, 10))

        context.close()
        print("\nBatch processing complete!")

if __name__ == "__main__":
    process_batch()