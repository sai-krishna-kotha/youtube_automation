import os
import sys
from contextlib import redirect_stdout

# --- THE ULTIMATE WINDOWS DLL INJECTION ---
FFMPEG_PATH = r"C:\Users\kotha\Downloads\important\ffmpeg\bin"

# 1. Force Windows to authorize the FFmpeg C++ DLLs (Required for Python 3.8+)
if hasattr(os, 'add_dll_directory'):
    try:
        os.add_dll_directory(FFMPEG_PATH)
    except Exception as e:
        print(f"[Warning] Could not add DLL directory: {e}")

# 2. Keep the standard PATH injection for other subprocesses
if FFMPEG_PATH not in os.environ["PATH"]:
    os.environ["PATH"] = FFMPEG_PATH + os.pathsep + os.environ["PATH"]
# ------------------------------------------

import torch
import numpy as np
import soundfile as sf
from pathlib import Path

# ... (Keep your PyTorch 2.6 patch and Kokoro setup exactly as they are) ...


# --- PYTORCH 2.6+ COMPATIBILITY PATCH ---
# PyTorch 2.6 enabled weights_only=True by default for security. 
# Coqui XTTS needs the old behavior (False) to load its configs successfully.
_original_load = torch.load
def _patched_load(*args, **kwargs):
    if 'weights_only' not in kwargs:
        kwargs['weights_only'] = False
    return _original_load(*args, **kwargs)
torch.load = _patched_load
# ----------------------------------------
# --- KOKORO SETUP ---
try:
    from kokoro import KPipeline
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False

# --- COQUI XTTS SETUP ---
try:
    from TTS.api import TTS
    XTTS_AVAILABLE = True
except ImportError:
    XTTS_AVAILABLE = False

class AudioGenerationService:
    def __init__(self, default_voice: str = "af_bella", default_speed: float = 1.0, output_dir: Path = None):
        """
        Initializes the service paths but delays loading the heavy AI models 
        into VRAM until we know exactly which one the user requested.
        """
        self.default_voice = default_voice
        self.default_speed = default_speed
        
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        
        self.output_dir = output_dir or (self.base_dir / "assets" / "outputs")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Dedicated vault for Coqui Voice Cloning references
        self.voice_vault_dir = self.base_dir / "assets" / "voices"
        self.voice_vault_dir.mkdir(parents=True, exist_ok=True)
        
        # Automatically use GPU if available
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Lazy-load placeholders
        self._kokoro_pipeline = None
        self._xtts_model = None

    def _get_kokoro(self):
        if not KOKORO_AVAILABLE:
            raise RuntimeError("Kokoro is not installed or dependencies are missing.")
        if self._kokoro_pipeline is None:
            print(f"[System] Booting Kokoro TTS Engine to memory...")
            self._kokoro_pipeline = KPipeline(lang_code='a') 
        return self._kokoro_pipeline

    def _get_xtts(self):
        if not XTTS_AVAILABLE:
            raise RuntimeError("Coqui XTTS is not installed. Run: pip install TTS 'numpy<2.0'")
        if self._xtts_model is None:
            print(f"[System] Booting Coqui XTTS v2 Engine to memory (Device: {self.device})...")
            self._xtts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(self.device)
        return self._xtts_model

    def generate_audio(self, text: str, voice: str = None, speed: float = None) -> Path:
        """
        Intelligently routes the text to either Kokoro or Coqui XTTS based on the voice requested.
        """
        active_voice = voice if voice is not None else self.default_voice
        active_speed = speed if speed is not None else self.default_speed
        
        output_path = self.output_dir / "audio.wav"
        
        print(f"\n--- SMART AUDIO GENERATION ---")
        print(f"Requested Voice: {active_voice} | Speed: {active_speed}")

        # --- ROUTING LOGIC ---
        # If the voice string ends in .wav, it's a clone request for Coqui. Otherwise, it's Kokoro.
        is_cloned_voice = active_voice.lower().endswith('.wav')
        
        if is_cloned_voice:
            print(f"[Engine] Routing to Coqui XTTS v2 (Voice Cloning Mode)...")
            voice_path = self.voice_vault_dir / active_voice
            
            if not voice_path.exists():
                print(f"\n[!] ERROR: Cloned voice file not found at {voice_path}")
                print(f"[!] Please place '{active_voice}' into the assets/voices/ folder.")
                raise FileNotFoundError(f"Missing reference voice file: {voice_path}")
                
            model = self._get_xtts()
            print("Synthesizing cloned speech... This may take a moment.")
            
            try:
                # BYPASS TORCHAUDIO: Generate raw audio data in memory
                # We use redirect_stdout to swallow Coqui's massive array logs
                with open(os.devnull, 'w') as fnull, redirect_stdout(fnull):
                    wav = model.tts(
                        text=text,
                        speaker_wav=str(voice_path),
                        language="en", 
                        speed=active_speed
                    )
                
                # Save the raw data using soundfile (bypassing the broken torchcodec completely)
                sf.write(str(output_path), np.array(wav), 24000)
                print(f"[✓] Success! Cloned audio saved to {output_path.name}")
                
            except Exception as e:
                print(f"[ERROR] Coqui XTTS generation failed: {e}")
        else:
            print(f"[Engine] Routing to Kokoro TTS (Standard Mode)...")
            pipeline = self._get_kokoro()
            print("Synthesizing speech... This may take a moment.")
            
            try:
                generator = pipeline(
                    text, 
                    voice=active_voice, 
                    speed=active_speed, 
                    split_pattern=r'\n+' 
                )
                
                audio_chunks = []
                for i, (graphemes, phonemes, audio) in enumerate(generator):
                    audio_chunks.append(audio)
                
                if audio_chunks:
                    final_audio = np.concatenate(audio_chunks)
                    sf.write(output_path, final_audio, 24000)
                    print(f"[✓] Success! Audio saved to {output_path.name}")
                else:
                    print("[ERROR] No audio chunks were generated by Kokoro.")
            except Exception as e:
                print(f"[ERROR] Kokoro generation failed: {e}")
                
        return output_path