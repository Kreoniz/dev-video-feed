from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)


class SkippedReason(StrEnum):
    SHORT = "short"
    STREAM = "stream"
    NON_YOUTUBE = "non_youtube"
    MISSING_VIDEO_ID = "missing_video_id"
    DUPLICATE = "duplicate"
    OTHER = "other"


class Confidence(StrEnum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Priority(StrEnum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class HealthResponse(CamelModel):
    ok: bool
    service: str
    version: str
    generated_at: datetime = Field(alias="generatedAt")


class ChannelFailure(CamelModel):
    channel: str
    feed_url: str = Field(alias="feedUrl")
    error: str


class SkippedItem(CamelModel):
    channel: str | None = None
    title: str | None = None
    video_id: str | None = Field(default=None, alias="videoId")
    reason: SkippedReason


class ParsedVideo(CamelModel):
    video_id: str = Field(alias="videoId")
    title: str
    url: str
    source_url: str | None = Field(default=None, alias="sourceUrl")
    published: datetime
    channel: str
    description: str
    thumbnail: str | None = None


class SampleItem(CamelModel):
    title: str
    video_id: str = Field(alias="videoId")
    url: str
    published: datetime
    description_snippet: str = Field(alias="descriptionSnippet")
    channel: str
    thumbnail: str | None = None


class FeedItem(CamelModel):
    video_id: str = Field(alias="videoId")
    title: str
    url: str
    published: datetime
    channel: str
    description: str
    description_snippet: str = Field(alias="descriptionSnippet")
    thumbnail: str | None = None
    duration: str = "Unknown"
    source: str = "YouTube RSS"
    confidence: Confidence
    topics: list[str]
    priority: Priority
    score: int
    summary: str
    why_watch: str = Field(alias="whyWatch")


class FeedResponse(CamelModel):
    generated_at: datetime = Field(alias="generatedAt")
    count: int
    channels_checked: list[str] = Field(alias="channelsChecked")
    channels_failed: list[ChannelFailure] = Field(alias="channelsFailed")
    items: list[FeedItem]
    skipped: list[SkippedItem]


class SampleResponse(CamelModel):
    generated_at: datetime = Field(alias="generatedAt")
    count: int
    channels_checked: list[str] = Field(alias="channelsChecked")
    channels_failed: list[ChannelFailure] = Field(alias="channelsFailed")
    items: list[SampleItem]
    skipped: list[SkippedItem]
