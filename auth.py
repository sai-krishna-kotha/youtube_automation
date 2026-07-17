from playwright.sync_api import sync_playwright

def save_session():
    with sync_playwright() as p:
        print("Launching browser... Please log in to your Google account.")
        # Creates a local profile directory to persist cookies and logins
        context = p.chromium.launch_persistent_context(
            user_data_dir="gemini_session_sm",
            headless=False,  # Must be visible so you can type your password/2FA
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = context.new_page()
        page.goto("https://gemini.google.com")
        
        input("\n👉 Log in fully. Once you see the Gemini dashboard, press ENTER here to save and exit...")
        context.close()
        print("Session saved successfully!")

if __name__ == "__main__":
    save_session()