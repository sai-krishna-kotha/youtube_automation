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
    
from pydantic import BaseModel, Field
from typing import List

class ThumbnailData(BaseModel):
    image_prompt: str = Field(description="The highly detailed, exact image generation prompt for an AI tool to create this visual (including lighting, style, and composition).")
    text: str = Field(description="The exact text embedded in the thumbnail. Maximum 2-5 words.")
    concept: str = Field(description="A concise description of the thumbnail concept, including the visual scene and the curiosity gap it creates.")
    score: int = Field(description="Estimated thumbnail CTR score from 0 to 100.")
    explanation: str = Field(description="Brief explanation of why this thumbnail concept and title are expected to achieve a high click-through rate.")
    
class ThumbnailResponse(BaseModel):
    thumbnails: List[ThumbnailData] = Field(description="List of exactly 5 distinct thumbnail concepts.")

class VideoMetadata(BaseModel):
    title: str = Field(description="A 50-60 character high-CTR title maximizing curiosity gaps, directly related to the thumbnail text/concept.")
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