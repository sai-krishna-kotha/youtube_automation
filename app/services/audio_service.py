import os
import numpy as np
import soundfile as sf
from pathlib import Path

# Try to import Kokoro. We use a try/except so the pipeline doesn't crash 
# if you are still setting up the heavy PyTorch/Kokoro dependencies.
try:
    from kokoro import KPipeline
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False

class AudioGenerationService:
    def __init__(self, default_voice: str = "af_bella", default_speed: float = 0.9, output_dir: Path = None):
        """
        Initializes the service with default settings.
        These can be overridden per generation if the user wants to change them later.
        """
        self.default_voice = default_voice
        self.default_speed = default_speed
        
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        
        self.output_dir = output_dir or (self.base_dir / "assets" / "outputs")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        if KOKORO_AVAILABLE:
            print("[System] Initializing Kokoro TTS Pipeline (English)...")
            # 'a' is for American English. Use 'b' for British.
            self.pipeline = KPipeline(lang_code='a') 
        else:
            print("[WARNING] Kokoro library not found. Audio generation will run in mock mode.")

    def generate_audio(self, text: str, voice: str = None, speed: float = None) -> Path:
        """
        Generates the audio file. Allows passing custom voice/speed to override defaults.
        """
        # 1. Resolve which settings to use
        active_voice = voice if voice is not None else self.default_voice
        active_speed = speed if speed is not None else self.default_speed
        
        output_path = self.output_dir / "audio.wav"
        
        print(f"\n--- AUDIO GENERATION ---")
        print(f"Voice: {active_voice} | Speed: {active_speed}")
        
        if not KOKORO_AVAILABLE:
            print("[WARNING] Mock generation complete. Install Kokoro to generate real audio.")
            # Create a dummy file just so downstream processes don't break
            with open(output_path, 'wb') as f:
                f.write(b"Mock audio data")
            return output_path

        # 2. Generate Audio via Kokoro
        try:
            print("Synthesizing speech... This may take a moment.")
            
            # The pipeline returns a generator. We split by sentences/paragraphs.
            generator = self.pipeline(
                text, 
                voice=active_voice, 
                speed=active_speed, 
                split_pattern=r'\n+' # Splits text at line breaks for better processing
            )
            
            audio_chunks = []
            for i, (graphemes, phonemes, audio) in enumerate(generator):
                audio_chunks.append(audio)
            
            # 3. Stitch chunks together and save
            if audio_chunks:
                final_audio = np.concatenate(audio_chunks)
                # Kokoro outputs at 24000Hz sample rate
                sf.write(output_path, final_audio, 24000)
                print(f"Success! Audio saved to {output_path}")
            else:
                print("[ERROR] No audio chunks were generated.")
                
        except Exception as e:
            print(f"[ERROR] Failed to generate audio: {e}")
            
        return output_path