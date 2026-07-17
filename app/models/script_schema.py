from pydantic import BaseModel, Field
from typing import List
from typing import Literal

location: Literal[
    "Opening",
    "Chapter 1",
    "Chapter 2",
    "Chapter 3",
    "Chapter 4",
    "Chapter 5",
    "Chapter 6",
    "Chapter 7",
    "Chapter 8",
    "Chapter 9",
    "Chapter 10",
    "Ending",
    "Entire Script"
]

class FixItem(BaseModel):
    location: str
    instruction: str

class PreserveItem(BaseModel):
    location: str
    reason: str


class RetentionMapItem(BaseModel):
    section: str
    score: float


class ReviewResponse(BaseModel):
    score: float
    publish: bool
    publish_reason: str
    configuration_violations: List[str]
    retention_map: List[RetentionMapItem]
    must_fix: List[FixItem]
    should_fix: List[FixItem]
    preserve: List[PreserveItem]
    editor_strategy: str
    
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
    

class ThumbnailData(BaseModel):
    image_prompt: str = Field(description="The highly detailed, exact image generation prompt for an AI tool to create this visual (including lighting, style, and composition).")
    text: str = Field(description="The exact text embedded in the thumbnail. Maximum 2-5 words.")
    concept: str = Field(description="A concise description of the thumbnail concept, including the visual scene and the curiosity gap it creates.")
    score: int = Field(description="Estimated thumbnail CTR score from 0 to 100.")
    explanation: str = Field(description="Brief explanation of why this thumbnail concept and title are expected to achieve a high click-through rate.")
    
class ThumbnailResponse(BaseModel):
    thumbnails: List[ThumbnailData] = Field(description="List of exactly 5 distinct thumbnail concepts.")

class VideoMetadata(BaseModel):
    title: str = Field(description="A 50-0 character high-CTR title maximizing curiosity gaps, directly related to the thumbnail text/concept.")
    description: str = Field(description="A compelling 2-paragraph hook, followed strictly by timestamped CHAPTERS formatted as 'MM:SS Title', KEYWORDS, and HASHTAGS with clear double line breaks.")
    tags: str = Field(description="Comma-separated SEO tags for tags input field.")
    score: int = Field(description="Estimated CTR/SEO score out of 100 based on title curiosity and keyword volume.")
    explanation: str = Field(description="Brief explanation of why this title and metadata will perform well on YouTube.")
    
class VideoMetadata(BaseModel):
    title: str = Field(description="A 50-60 character high-CTR title maximizing curiosity gaps.")
    description: str = Field(description="A compelling 2-paragraph hook, followed strictly by timestamped CHAPTERS formatted as 'MM:SS Title', KEYWORDS, and HASHTAGS with clear double line breaks.")
    tags: str = Field(description="Comma-separated SEO tags for tags input field.")
    score: int = Field(description="Estimated CTR/SEO score out of 100 based on title curiosity and keyword volume.")
    explanation: str = Field(description="Brief explanation of why this title and metadata will perform well on YouTube.")