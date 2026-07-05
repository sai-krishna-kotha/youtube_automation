from pydantic import BaseModel, Field
from typing import List

class RetentionMapItem(BaseModel):
    section: str = Field(description="The section of the video (e.g., 'First 30s Hook', 'Middle Context', 'Ending')")
    score: float = Field(description="Retention score out of 10.0 for this specific section")

class ReviewResponse(BaseModel):
    score: float = Field(description="Overall script score out of 10.0")
    publish: bool = Field(description="True if the script is ready to be published, False otherwise")
    reason: str = Field(description="A single sentence explaining the main reason for the publish decision")
    retention_map: List[RetentionMapItem] = Field(description="A heat map of viewer retention across the script")
    must_fix: List[str] = Field(description="Critical, non-negotiable editing tasks that must be executed")
    should_fix: List[str] = Field(description="Minor improvements or stylistic suggestions")
    preserve: List[str] = Field(description="Specific paragraphs, jokes, or metaphors that are perfect and MUST NOT be changed")
    editor_strategy: str = Field(description="The macroscopic directive for the editor (e.g., 'Increase pace in the middle, keep the hook intact')")


class AudioSegment(BaseModel):
    segment_id: int
    start: float
    end: float
    text: str

class AudioBatch(BaseModel):
    batch_id: int
    start_time: float
    end_time: float
    duration: float
    segments: List[AudioSegment]

class TimestampedTranscription(BaseModel):
    batches: List[AudioBatch]
    
class SingleShotPrompt(BaseModel):
    start_time: float = Field(..., description="The exact start time from the transcript segment.")
    image_prompt: str = Field(..., description="A completely self-contained visual prompt using the required style, characters, props, and words constraints.")

class BatchPromptResponse(BaseModel):
    shots: list[SingleShotPrompt] = Field(..., description="The list of generated image prompts mapping 1:1 to the transcript segment timestamps.")
    
    