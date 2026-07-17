import json
import yaml
from pathlib import Path
from app.models.script_schema import AudioSegment, AudioBatch, TimestampedTranscription

try:
    import whisperx
    WHISPERX_AVAILABLE = True
except ImportError:
    WHISPERX_AVAILABLE = False

class TranscriptionService:
    def __init__(self, device: str = "cpu", output_dir: Path = None):
        self.device = device
        self.base_dir = Path(__file__).resolve().parent.parent.parent
                
        self.output_dir = output_dir or (self.base_dir / "assets" / "outputs")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        if WHISPERX_AVAILABLE:
            print(f"[System] Initializing WhisperX (Device: {self.device})...")
            compute_type = "float16" if self.device == "cuda" else "int8"
            self.model = whisperx.load_model("base", self.device, compute_type=compute_type)
        else:
            print("[WARNING] WhisperX not found. Service will run in mock mode.")

    def _enforce_segment_pacing(
        self, 
        raw_segments: list, 
        punc_limit: float = 1.5, 
        conj_limit: float = 3.0, 
        max_duration: float = 4.5
    ) -> list:
        """
        Advanced Dynamic Pacing Enforcer
        """
        refined_segments = []
        conjunctions = {'and', 'but', 'so', 'because', 'or', 'that', 'if', 'when', 'while', 'then'}
        
        for seg in raw_segments:
            if "words" not in seg:
                refined_segments.append(seg)
                continue
                
            current_text = []
            words = seg["words"]
            
            current_start = words[0].get("start", seg["start"]) 
            last_end = current_start
            
            for word_data in words:
                word_text = word_data["word"]
                w_start = word_data.get("start", last_end)
                w_end = word_data.get("end", w_start + 0.2)
                
                current_duration_pre = w_start - current_start
                clean_word = word_text.lower().strip(' .,!?;:"\'')
                is_conjunction = clean_word in conjunctions
                
                if current_duration_pre >= conj_limit and is_conjunction and current_text:
                    refined_segments.append({
                        "start": current_start,
                        "end": w_start,
                        "text": " ".join(current_text).strip()
                    })
                    current_text = []
                    current_start = w_start
                
                current_text.append(word_text)
                last_end = w_end
                
                current_duration_post = w_end - current_start
                has_punctuation = any(p in word_text for p in ['.', ',', '!', '?', ';', ':'])
                
                if current_duration_post >= punc_limit and has_punctuation:
                    refined_segments.append({
                        "start": current_start,
                        "end": w_end,
                        "text": " ".join(current_text).strip()
                    })
                    current_text = []
                    current_start = w_end
                    
                elif current_duration_post >= max_duration:
                    refined_segments.append({
                        "start": current_start,
                        "end": w_end,
                        "text": " ".join(current_text).strip()
                    })
                    current_text = []
                    current_start = w_end
                    
            if current_text:
                refined_segments.append({
                    "start": current_start,
                    "end": last_end,
                    "text": " ".join(current_text).strip()
                })
                
        return refined_segments
    
    
    def extract_and_batch(self, audio_path: Path, request_yaml: str = None, min_duration: float = 40.0, max_duration: float = 60.0) -> Path:
        print("\n--- AUDIO TRANSCRIPTION & SMART BATCHING ---")
        output_path = self.output_dir / "time_stamped_transcription.json"
        
        if not WHISPERX_AVAILABLE:
            print("[WARNING] Mocking Smart Batching...")
            return output_path

        # Parse the YAML to grab the dynamic pacing frequency
        try:
            req_data = yaml.safe_load(request_yaml) if request_yaml else {}
            target_freq = float(req_data.get('delivery', {}).get('timestamp_frequency_seconds', 4.5))
        except Exception:
            target_freq = 4.5
            
        print(f"[System] Pacing visual segments dynamically at ~{target_freq}s gaps based on YAML request...")

        print(f"Loading audio file: {audio_path.name}")
        audio = whisperx.load_audio(str(audio_path))
        
        print("Transcribing audio...")
        result = self.model.transcribe(audio, batch_size=8, language="en")
        
        print("Aligning timestamps to audio wave (WhisperX)...")
        model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=self.device)
        aligned_result = whisperx.align(result["segments"], model_a, metadata, audio, self.device, return_char_alignments=False)
        
        # Calculate intelligent back-off limits based on the requested frequency
        punc_limit = max(1.5, target_freq * 0.75)
        conj_limit = max(3.0, target_freq * 0.90)
        
        print("Enforcing dynamic visual pacing at grammatical breaks...")
        paced_segments = self._enforce_segment_pacing(
            aligned_result["segments"], 
            punc_limit=punc_limit,   
            conj_limit=conj_limit,   
            max_duration=target_freq 
        )
        
        print("Executing Semantic Chunking (Smart Batching)...")
        batches = []
        current_batch = []
        
        if not paced_segments:
            return None
            
        batch_start_time = paced_segments[0]['start']
        
        for i, seg in enumerate(paced_segments):
            clean_seg = AudioSegment(
                segment_id=i + 1,
                start=round(seg['start'], 2),
                end=round(seg['end'], 2),
                text=seg['text'].strip()
            )
            current_batch.append(clean_seg)
            
            current_duration = clean_seg.end - batch_start_time
            
            if current_duration >= min_duration:
                gap = 0.0
                is_last_segment = (i + 1 == len(paced_segments))
                
                if not is_last_segment:
                    gap = paced_segments[i+1]['start'] - clean_seg.end
                
                if gap >= 0.5 or current_duration >= max_duration or is_last_segment:
                    new_batch = AudioBatch(
                        batch_id=len(batches) + 1,
                        start_time=batch_start_time,
                        end_time=clean_seg.end,
                        duration=round(current_duration, 2),
                        segments=current_batch
                    )
                    batches.append(new_batch)
                    print(f"  -> Created Batch {new_batch.batch_id}: {new_batch.duration}s (Segments {current_batch[0].segment_id} to {current_batch[-1].segment_id})")
                    
                    current_batch = []
                    if not is_last_segment:
                        batch_start_time = paced_segments[i+1]['start']

        if current_batch:
            remaining_duration = current_batch[-1].end - batch_start_time
            new_batch = AudioBatch(
                batch_id=len(batches) + 1,
                start_time=batch_start_time,
                end_time=current_batch[-1].end,
                duration=round(remaining_duration, 2),
                segments=current_batch
            )
            batches.append(new_batch)
            print(f"  -> Flushed Final Batch {new_batch.batch_id}: {new_batch.duration}s (Segments {current_batch[0].segment_id} to {current_batch[-1].segment_id})")

        final_transcription = TimestampedTranscription(batches=batches)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(final_transcription.model_dump_json(indent=4))
            
        print(f"Success! Smart Batched JSON saved to {output_path}")
        return output_path