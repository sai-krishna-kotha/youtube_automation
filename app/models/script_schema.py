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
    length: int
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
    image_prompt: str = Field(
        description="Detailed production-ready, standalone image generation prompt."
    )

    text: str = Field(
        description="Thumbnail text. 2-5 words maximum."
    )

    concept: str = Field(
        description="Thumbnail visual concept and curiosity gap."
    )

    score: int = Field(
        description="Estimated CTR score from 0-100."
    )

    explanation: str = Field(
        description="Why this thumbnail is expected to perform well."
    )


class ThumbnailResponse(BaseModel):
    thumbnails: List[ThumbnailData]


# -----------------------------
# SEO
# -----------------------------

class SEOKeywords(BaseModel):

    primary: List[str] = Field(
        description="20-30 high volume primary search keywords."
    )

    secondary: List[str] = Field(
        description="40-60 long-tail keywords."
    )

    autocomplete: List[str] = Field(
        description="20-40 YouTube autocomplete style phrases."
    )

    questions: List[str] = Field(
        description="20-30 search questions users may type."
    )

    entities: List[str] = Field(
        description="Important people, companies, technologies, products, concepts and events from the script."
    )


# -----------------------------
# Metadata
# -----------------------------

class VideoMetadata(BaseModel):

    title: str = Field(
        description="50-55 character high CTR YouTube title. Must complement, not duplicate, thumbnail text."
    )

    description: str = Field(
        description=(
            "2500-4500 character SEO-optimized YouTube description. "
            "Must contain documentary-style introduction, chapters, research links, "
            "channel sections, production credits and hashtags."
        )
    )

    seo_keywords: SEOKeywords = Field(
        description="Complete structured SEO keyword package."
    )

    hashtags: List[str] = Field(
        description="15-25 lowercase hashtags."
    )

    tags: List[str] = Field(
        description=(
            "Comma-field tags as individual strings. "
            "Total combined characters should stay under YouTube's 500-character limit."
        )
    )

    score: int = Field(
        ge=0,
        le=100,
        description="Estimated SEO/CTR score."
    )

    explanation: str = Field(
        description="Why this metadata package should perform well."
    )