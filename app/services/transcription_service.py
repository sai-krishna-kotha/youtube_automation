import json
import time
import wave
import yaml
from pathlib import Path
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

from app.models.script_schema import (
    AudioSegment,
    AudioBatch,
    TimestampedTranscription
)

try:
    import whisperx
    WHISPERX_AVAILABLE = True
except ImportError:
    WHISPERX_AVAILABLE = False

SLEEP_TIME = 5

# ==========================================
# LLM RESPONSE SCHEMAS FOR CHUNKING (V3 - SINGLE TRACK)
# ==========================================
class BaseSegmentLLM(BaseModel):
    text: str = Field(..., description="Exact original source text for this base segment.")
    visual_type: Literal["IMAGE_ONLY", "TEXT_ONLY", "MIXED"] = Field(
        ..., 
        description="IMAGE_ONLY (pure visuals), TEXT_ONLY (large font text card), or MIXED."
    )
    display_text: Optional[str] = Field(
        None, 
        description="The large font text to display on screen if visual_type is TEXT_ONLY or MIXED."
    )

class SemanticChunkResponse(BaseModel):
    segments: List[BaseSegmentLLM]


class TranscriptionService:
    def __init__(self, llm_client, device: str = "cpu", output_dir: Path = None):
        self.llm = llm_client
        self.device = device
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        self.master_prompts_dir = self.base_dir / "prompts" / "master_prompts" / "transcript_prompts"
                
        self.output_dir = output_dir or (self.base_dir / "assets" / "outputs")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # ---------------------------------------------------------
        # 🎛️ CHANNEL PACING & TEXT DISPLAY CONTROL
        # ---------------------------------------------------------
        self.FAST_PACED_CHANNELS = ["tech", "huh", "doodle", "stick", "decoded"]
        self.FORCE_FAST_PACED: Optional[bool] = None  # True/False forces mode; None auto-detects
        self.MAX_DISPLAY_WORDS: int = 5  # Word limit control for large-font display text
        # ---------------------------------------------------------

        if WHISPERX_AVAILABLE:
            print(f"[System] Initializing WhisperX (Device: {self.device})...")
            compute_type = "float16" if self.device == "cuda" else "int8"
            self.model = whisperx.load_model("base", self.device, compute_type=compute_type)
        else:
            print("[WARNING] WhisperX not found. Service will run in mock mode.")

    def _is_fast_paced_channel(self, channel_name: str) -> bool:
        """Determines channel pace mode."""
        if self.FORCE_FAST_PACED is not None:
            return self.FORCE_FAST_PACED
        ch_lower = channel_name.lower()
        return any(keyword in ch_lower for keyword in self.FAST_PACED_CHANNELS)

    def _get_audio_total_duration(self, audio_path: Path) -> float:
        """Helper to get exact audio duration from wave file."""
        try:
            with wave.open(str(audio_path), 'rb') as f:
                frames = f.getnframes()
                rate = f.getframerate()
                return round(frames / float(rate), 2)
        except Exception:
            return 0.0

    def _load_master_prompt(self, is_fast_paced: bool, target_freq: float, word_timestamps_json: str) -> str:
        """Loads and formats the prompt template."""
        prompt_filename = "semantic_chunking_fast_pace.md" if is_fast_paced else "semantic_chunking_slow_pace.md" 
        prompt_path = self.master_prompts_dir / prompt_filename

        if not prompt_path.exists():
            print(f"[!] Warning: Prompt file {prompt_path.name} missing. Using fallback dynamic prompt.")
            return self._generate_fallback_prompt(is_fast_paced, target_freq, word_timestamps_json)

        with open(prompt_path, "r", encoding="utf-8") as f:
            template = f.read()

        formatted_prompt = template.replace("{target_freq}", str(target_freq))
        formatted_prompt = formatted_prompt.replace("{max_display_words}", str(self.MAX_DISPLAY_WORDS))
        formatted_prompt = formatted_prompt.replace("{word_timestamps_json}", word_timestamps_json)
        return formatted_prompt
        
    def _generate_fallback_prompt(self, is_fast_paced: bool, target_freq: float, word_timestamps_json: str) -> str:
        """Dynamic fallback prompt generator."""
        if is_fast_paced:
            return f"""
            You are a video pacing director for a FAST-PACED channel.
            1. Target segment duration: ~{target_freq} seconds based on word timestamps.
            2. Alternate visual types: IMAGE_ONLY, TEXT_ONLY, or MIXED.
            3. For TEXT_ONLY or MIXED, include display_text (max {self.MAX_DISPLAY_WORDS} words).
            4. Retain EXACT original words from transcript without changing order.
            
            WORD TIMESTAMPS:
            {word_timestamps_json}
            """
        else:
            return f"""
            You are a video pacing director for a SLOW-PACED storytelling channel.
            1. Target segment duration: ~{target_freq} seconds based on word timestamps.
            2. ALL segments MUST be "IMAGE_ONLY". Set display_text to null.
            3. Retain EXACT original words from transcript.
            
            WORD TIMESTAMPS:
            {word_timestamps_json}
            """

    def _execute_llm_chunking_with_checkpoint(
        self, 
        prompt: str, 
        full_transcript: str
    ) -> List[BaseSegmentLLM]:
        """Calls Gemini API with full retry safety, checkpointing, and strict word validation."""
        checkpoint_path = self.output_dir / "transcription_ai_checkpoint.json"

        if checkpoint_path.exists():
            try:
                print("[Checkpoint] Found existing transcription AI checkpoint. Loading...")
                with open(checkpoint_path, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                    return [BaseSegmentLLM(**seg) for seg in cached_data.get("segments", [])]
            except Exception as e:
                print(f"[WARNING] Failed reading checkpoint ({e}). Requesting fresh API call...")

        expected_word_count = len(full_transcript.split())
        print(f"[AI Pacing] Requesting semantic chunking from Gemini API (Expecting exactly {expected_word_count} words)...")

        while True:
            try:
                raw_response = self.llm.generate_json(prompt, response_model=SemanticChunkResponse)
                parsed_response = SemanticChunkResponse(**json.loads(raw_response))
                
                if parsed_response.segments:
                    reconstructed_text = " ".join([seg.text for seg in parsed_response.segments])
                    actual_word_count = len(reconstructed_text.split())
                    
                    if actual_word_count == expected_word_count:
                        print(f"  [✓] Success! Perfect match: {actual_word_count}/{expected_word_count} words retained across {len(parsed_response.segments)} base segments.")
                        
                        with open(checkpoint_path, "w", encoding="utf-8") as f:
                            json.dump(parsed_response.model_dump(), f, indent=4)
                        
                        return parsed_response.segments
                    else:
                        print(f"  [!] Hallucination Detected: LLM returned {actual_word_count} words, but source transcript has {expected_word_count} words.")
                        print(f"  [!] Retrying chunking batch in {SLEEP_TIME} seconds...")
                        time.sleep(SLEEP_TIME)
                else:
                    print(f"  [!] LLM returned empty segments array. Retrying in {SLEEP_TIME}s...")
                    time.sleep(SLEEP_TIME)

            except Exception as e:
                print(f"  [ERROR] LLM Chunking failed: {e}. Retrying in {SLEEP_TIME}s...")
                time.sleep(SLEEP_TIME)
                
    def _align_and_build_segments(
        self, 
        llm_segments: List[BaseSegmentLLM], 
        all_words: list,
        is_fast_paced: bool
    ) -> List[AudioSegment]:
        """Maps LLM text chunks to WhisperX word timestamps and applies formatting rules."""
        refined_audio_segments = []
        word_idx = 0
        total_words = len(all_words)

        for seg_id, llm_seg in enumerate(llm_segments, start=1):
            chunk_words_raw = llm_seg.text.split()
            if not chunk_words_raw:
                continue

            words_to_consume = len(chunk_words_raw)
            consumed = 0
            chunk_words_data = []

            while consumed < words_to_consume and word_idx < total_words:
                chunk_words_data.append(all_words[word_idx])
                word_idx += 1
                consumed += 1

            if not chunk_words_data:
                continue

            # First segment ALWAYS starts at 0.0s regardless of initial audio silence
            if seg_id == 1:
                seg_start = 0.0
            else:
                seg_start = round(chunk_words_data[0].get("start", 0.0), 2)

            # Enforce visual type & display_text rules based on pace mode
            if not is_fast_paced:
                v_type = "IMAGE_ONLY"
                disp_text = None
            else:
                v_type = llm_seg.visual_type
                disp_text = llm_seg.display_text
                # Truncate display text to max display words limit if provided
                if disp_text and v_type in ["TEXT_ONLY", "MIXED"]:
                    words = disp_text.split()
                    if len(words) > self.MAX_DISPLAY_WORDS:
                        disp_text = " ".join(words[:self.MAX_DISPLAY_WORDS])
                else:
                    disp_text = None

            audio_seg = AudioSegment(
                segment_id=seg_id,
                start=seg_start,
                text=llm_seg.text.strip(),
                visual_type=v_type,
                display_text=disp_text,
                b_roll_overlays=[]
            )
            refined_audio_segments.append(audio_seg)

        return refined_audio_segments

    def extract_and_batch(
        self, 
        audio_path: Path, 
        request_yaml: str = None, 
        min_duration: float = 40.0, 
        max_duration: float = 60.0
    ) -> Path:
        print("\n--- AUDIO TRANSCRIPTION & AI SMART BATCHING (V3) ---")
        output_path = self.output_dir / "time_stamped_transcription.json"

        if not WHISPERX_AVAILABLE:
            print("[WARNING] WhisperX unavailable. Returning cached output path...")
            return output_path

        # 1. Pace Detection & Dynamic YAML Frequency Extraction
        channel_name = self.output_dir.parent.name
        is_fast_paced = self._is_fast_paced_channel(channel_name)
        
        target_freq = 2.5 if is_fast_paced else 6.0

        if request_yaml:
            try:
                req_data = yaml.safe_load(request_yaml) or {}
                delivery_data = req_data.get('delivery', {})
                if 'timestamp_frequency_seconds' in delivery_data:
                    target_freq = float(delivery_data['timestamp_frequency_seconds'])
            except Exception as e:
                print(f"[!] YAML pacing parse error: {e}. Defaulting to {target_freq}s.")

        pace_label = "FAST-PACED" if is_fast_paced else "SLOW-PACED"
        print(f"[System] Channel Mode: '{channel_name}' -> {pace_label} (Target: ~{target_freq}s cuts)")

        total_audio_duration = self._get_audio_total_duration(audio_path)

        # 2. WhisperX Wave Alignment
        print(f"Loading audio file: {audio_path.name}")
        audio = whisperx.load_audio(str(audio_path))

        print("Transcribing audio with WhisperX...")
        result = self.model.transcribe(audio, batch_size=8, language="en")

        print("Aligning timestamps to wave...")
        model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=self.device)
        aligned_result = whisperx.align(result["segments"], model_a, metadata, audio, self.device, return_char_alignments=False)

        all_words = []
        last_time = 0.0
        for seg in aligned_result.get("segments", []):
            for w in seg.get("words", []):
                word_text = w.get("word", "").strip()
                if not word_text:
                    continue
                w_start = w.get("start", last_time)
                w_end = w.get("end", w_start + 0.2)
                all_words.append({"word": word_text, "start": w_start, "end": w_end})
                last_time = w_end

        if not all_words:
            print("[!] No words transcribed.")
            return None

        if total_audio_duration <= 0.0:
            total_audio_duration = round(all_words[-1]["end"], 2)

        word_timestamps_json = json.dumps([
            {"w": w["word"], "s": round(w["start"], 2), "e": round(w["end"], 2)} 
            for w in all_words
        ])

        # 3. AI Semantic Chunking
        full_transcript = " ".join([w["word"] for w in all_words])
        prompt = self._load_master_prompt(is_fast_paced, target_freq, word_timestamps_json)
        llm_segments = self._execute_llm_chunking_with_checkpoint(prompt, full_transcript)

        # 4. Map Timestamps and Build AudioSegments
        paced_segments = self._align_and_build_segments(llm_segments, all_words, is_fast_paced)

        # 5. Smart Batching (~40s - 60s windows with STRICT Sentence Boundaries)
        print("Executing Smart Audio Batching (Sentence-Boundary Enforced)...")
        batches = []
        current_batch = []
        
        if not paced_segments:
            return None

        batch_start_time = 0.0

        for i, seg in enumerate(paced_segments):
            current_batch.append(seg)
            
            next_start = paced_segments[i + 1].start if (i + 1 < len(paced_segments)) else total_audio_duration
            current_duration = next_start - batch_start_time
            
            # --- THE BATCH BOUNDARY FIX ---
            # Check if this segment ends with a full stop, exclamation mark, or question mark
            clean_text = seg.text.strip()
            ends_sentence = clean_text.endswith('.') or clean_text.endswith('!') or clean_text.endswith('?')
            is_last_segment = (i + 1 == len(paced_segments))

            # Only break the batch if we've passed the minimum duration AND we found a sentence end
            if current_duration >= min_duration:
                # Fallback: if we go 15 seconds over max_duration, force cut to prevent infinite batches
                if ends_sentence or is_last_segment or (current_duration >= max_duration + 15.0):
                    new_batch = AudioBatch(
                        batch_id=len(batches) + 1,
                        length=len(current_batch),
                        start_time=batch_start_time,
                        end_time=round(next_start, 2),
                        duration=round(current_duration, 2),
                        segments=current_batch
                    )
                    batches.append(new_batch)
                    print(f"   -> Batch {new_batch.batch_id}: {new_batch.duration}s ({len(current_batch)} segments)")
                    current_batch = []
                    batch_start_time = next_start

        # --- THE FINAL BATCH AUDIO ALIGNMENT ---
        if current_batch:
            new_batch = AudioBatch(
                batch_id=len(batches) + 1,
                length=len(current_batch),
                start_time=batch_start_time,
                end_time=total_audio_duration,
                duration=round(total_audio_duration - batch_start_time, 2),
                segments=current_batch
            )
            batches.append(new_batch)
            print(f"   -> Final Batch {new_batch.batch_id}: {new_batch.duration}s ({len(current_batch)} segments) [Aligned to total audio duration]")

        final_transcription = TimestampedTranscription(batches=batches)

        # 6. Serialization Clean-Up
        dump_data = final_transcription.model_dump(exclude_none=True)
        for batch in dump_data.get("batches", []):
            for segment in batch.get("segments", []):
                segment.pop("end", None)
                segment.pop("end_time", None)
                segment.pop("b_roll_overlays", None)
                segment.pop("base_prompt_context", None)  

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(dump_data, f, indent=4)

        print(f"[Success] Single-Track JSON saved to {output_path}")
        return output_path