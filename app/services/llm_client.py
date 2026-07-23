import os
import json
import time
from datetime import datetime
from pathlib import Path
from google import genai
from google.genai import types
from pydantic import BaseModel

class GeminiClient:
    def __init__(self):
        # 1. Load API keys from environment
        keys_env = os.getenv("GEMINI_API_KEYS", os.getenv("GEMINI_API_KEY", ""))
        self.api_keys = [k.strip() for k in keys_env.split(",") if k.strip()]
        
        if not self.api_keys:
            raise ValueError("[!] GEMINI_API_KEYS not found in environment variables. Please check your .env file.")

        # 2. Read Toggle Settings from .env
        self.enable_fallback = os.getenv("ENABLE_MODEL_FALLBACK", "true").lower() == "true"
        self.pinned_model = os.getenv("PINNED_MODEL", "gemini-2.5-flash")

        # 3. Model Hierarchy Setup
        if self.enable_fallback:
            self.models = [
                "gemini-3.6-flash",
                "gemini-2.5-flash",
                "gemini-3.5-flash-lite",
                "gemini-3.1-flash-lite"
                "gemini-3-flash-preview",
                "gemini-3.5-flash",
                "gemini-2.5-flash-lite",
            ]
        else:
            # Fallback DISABLED: Lock strictly to the pinned model
            self.models = [self.pinned_model]
            print(f"[API Client] Smart Fallback DISABLED. Pinned strictly to model: '{self.pinned_model}'")

        # 4. Checkpoint File Path
        self.base_dir = Path(__file__).resolve().parent.parent
        self.checkpoint_path = self.base_dir / "api_state_checkpoint.json"
        
        # 5. State Trackers
        self.current_model_idx = 0
        self.current_key_idx = 0
        
        # Load or Auto-Reset State
        self._load_or_reset_state()
        
        # Initialize active client
        self._update_client()

    def _get_today_str(self) -> str:
        """Returns current date in YYYY-MM-DD format."""
        return datetime.now().strftime("%Y-%m-%d")

    def _load_or_reset_state(self):
        """Loads state from checkpoint JSON or auto-resets on new day / manual reset."""
        today = self._get_today_str()
        
        if self.checkpoint_path.exists():
            try:
                with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    
                saved_date = state.get("last_updated_date", "")
                
                if saved_date != today:
                    print(f"\n[API Checkpoint] New day detected ({today} vs {saved_date}). Resetting Model & Key indices!")
                    self.current_model_idx = 0
                    self.current_key_idx = 0
                    self._save_checkpoint()
                else:
                    # Ensure saved model index doesn't exceed array if fallback was toggled off
                    saved_m_idx = state.get("current_model_idx", 0)
                    self.current_model_idx = saved_m_idx if saved_m_idx < len(self.models) else 0
                    self.current_key_idx = state.get("current_key_idx", 0)
                    
                    active_m = self.models[self.current_model_idx]
                    print(f"[API Checkpoint] Resuming state: Model '{active_m}' | Key #{self.current_key_idx + 1}")
                    
            except Exception as e:
                print(f"[API Checkpoint] Corrupt checkpoint ({e}). Resetting state...")
                self.current_model_idx = 0
                self.current_key_idx = 0
                self._save_checkpoint()
        else:
            print(f"[API Checkpoint] Fresh state initialized (Model 0 & Key 0).")
            self.current_model_idx = 0
            self.current_key_idx = 0
            self._save_checkpoint()

    def _save_checkpoint(self):
        """Saves current state to disk."""
        state = {
            "fallback_enabled": self.enable_fallback,
            "current_model_idx": self.current_model_idx,
            "current_key_idx": self.current_key_idx,
            "active_model": self.models[self.current_model_idx],
            "last_updated_date": self._get_today_str(),
            "last_updated_time": datetime.now().strftime("%I:%M:%S %p")
        }
        with open(self.checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=4)

    def _update_client(self):
        """Initializes the SDK client with active API key."""
        active_key = self.api_keys[self.current_key_idx]
        self.client = genai.Client(api_key=active_key)

    def _execute_with_fallback(self, call_func, *args, **kwargs):
        """
        Executes API calls with clean error catching, key rotation, 
        and graceful pipeline termination without raw stack dumps.
        """
        max_retries_per_key = 1
        last_error_summary = "Unknown Error"
        
        for m_idx in range(self.current_model_idx, len(self.models)):
            self.current_model_idx = m_idx
            model_name = self.models[m_idx]
            
            keys_tested = 0
            temp_key_idx = self.current_key_idx
            
            while keys_tested < len(self.api_keys):
                active_key = self.api_keys[temp_key_idx]
                self.client = genai.Client(api_key=active_key)
                masked_key = f"Key #{temp_key_idx + 1} (...{active_key[-4:]})"
                
                for attempt in range(1, max_retries_per_key + 1):
                    try:
                        # 🔍 Real-time Debug Log
                        print(f"  [LLM Request] Model: '{model_name}' | {masked_key}")
                        
                        result = call_func(model_name, *args, **kwargs)
                        self._save_checkpoint()
                        self._update_client()
                        return result
                        
                    except Exception as e:
                        # Extract first line of error message to prevent multi-line dumps
                        raw_err_line = str(e).split('\n')[0]
                        error_msg = str(e).lower()
                        last_error_summary = raw_err_line
                        
                        print(f"  [API Error] Model: {model_name} | {masked_key} | Attempt {attempt}/{max_retries_per_key}")
                        print(f"  -> {raw_err_line}")
                        
                        if attempt < max_retries_per_key:
                            time.sleep(2 ** attempt)
                        else:
                            if "429" in error_msg or "quota" in error_msg or "exhausted" in error_msg:
                                print(f"  [!] {masked_key} out of quota (429). Permanently rotating key...")
                                self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
                                temp_key_idx = self.current_key_idx
                                self._save_checkpoint()
                            elif "403" in error_msg or "permission" in error_msg:
                                print(f"  [!] {masked_key} permission denied / invalid key (403). Rotating key...")
                                self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
                                temp_key_idx = self.current_key_idx
                                self._save_checkpoint()
                            else:
                                print(f"  [!] {masked_key} hit temporary server issue. Borrowing backup key...")
                                temp_key_idx = (temp_key_idx + 1) % len(self.api_keys)
                                
                            break
                
                keys_tested += 1
                
            # --- MODEL EXHAUSTION HANDLER ---
            if self.enable_fallback:
                print(f"\n[!] All API keys exhausted for '{model_name}'. Downgrading model hierarchy...\n")
                self.current_key_idx = 0
                self._update_client()
                self._save_checkpoint()
            else:
                # 🛑 CLEAN HALT FOR TOGGLED-OFF CASE
                print("\n" + "="*80)
                print(f"[SYSTEM HALT] All API keys exhausted for pinned model: '{model_name}'")
                print(f"  -> Status / Reason: {last_error_summary}")
                print(f"  -> Model Fallback is TOGGLED OFF (ENABLE_MODEL_FALLBACK=false).")
                print("  -> Service stopped cleanly. Reset your API keys or enable fallback to proceed.")
                print("="*80 + "\n")
                
                # Gracefully stop the Python execution cleanly without stack traces
                import sys
                sys.exit(1)

        print("\n[SYSTEM HALT] All available Gemini models and keys have been exhausted for today!")
        import sys
        sys.exit(1)
    def generate_text(self, prompt: str) -> str:
        """Generates raw text for Creator and Editor agents."""
        def _call(model_name, p):
            response = self.client.models.generate_content(
                model=model_name,
                contents=p,
            )
            return response.text
            
        return self._execute_with_fallback(_call, prompt)

    def generate_json(self, prompt: str, response_model: type[BaseModel]) -> str:
        """Forces structured JSON output adhering to a Pydantic schema."""
        def _call(model_name, p, rm):
            response = self.client.models.generate_content(
                model=model_name,
                contents=p,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=rm,
                ),
            )
            return response.text
            
        return self._execute_with_fallback(_call, prompt, response_model)