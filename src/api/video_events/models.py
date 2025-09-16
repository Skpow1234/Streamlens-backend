from datetime import datetime
from typing import Optional

from timescaledb import TimescaleModel
from pydantic import BaseModel, Field as PydanticField, field_validator
from sqlmodel import SQLModel, Field
import re

class YouTubeWatchEvent(TimescaleModel, table=True):  # type: ignore[call-arg]
    """A time-series event representing a YouTube player's state change."""
    id: Optional[int] = Field(default=None, primary_key=True)
    is_ready: bool
    video_id: str = Field(index=True, min_length=1, max_length=32)
    video_title: str = Field(min_length=1, max_length=255)
    current_time: float = Field(ge=0)
    video_state_label: str = Field(min_length=1, max_length=64)
    video_state_value: int
    referer: Optional[str] = Field(default="", index=True, max_length=255)
    watch_session_id: Optional[str] = Field(
        default=None, index=True, min_length=1, max_length=64
    )
    user_id: int = Field(foreign_key="user.id")
    time: datetime = Field(default_factory=datetime.utcnow, nullable=False, index=True)

    # timescaledb config
    __chunk_time_interval__ = "INTERVAL 7 days"
    __drop_after__ = "INTERVAL 1 year"
    __enable_compression__ = True
    __compress_orderby__ = "time DESC"
    __compress_segmentby__ = "video_id"
    __migrate_data__ = True
    __if_not_exists__ = True

class YouTubePlayerState(SQLModel, table=False):
    """Schema for YouTube player state input. Used for creating/updating events."""
    is_ready: bool
    video_id: str = Field(index=True, min_length=1, max_length=32)
    video_title: str = Field(min_length=1, max_length=255)
    current_time: float = Field(ge=0)
    video_state_label: str = Field(min_length=1, max_length=64)
    video_state_value: int

    @field_validator('video_id')
    @classmethod
    def validate_video_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Video ID cannot be empty')
        if len(v) > 32:
            raise ValueError('Video ID must be less than 32 characters')
        # Basic YouTube video ID validation (11 characters, alphanumeric + hyphens + underscores)
        if not re.match(r'^[a-zA-Z0-9_-]{11}$', v):
            raise ValueError('Invalid YouTube video ID format')
        return v.strip()

    @field_validator('video_title')
    @classmethod
    def validate_video_title(cls, v):
        if not v or not v.strip():
            raise ValueError('Video title cannot be empty')
        if len(v) > 255:
            raise ValueError('Video title must be less than 255 characters')
        return v.strip()

    @field_validator('current_time')
    @classmethod
    def validate_current_time(cls, v):
        if v < 0:
            raise ValueError('Current time cannot be negative')
        return v

    @field_validator('video_state_label')
    @classmethod
    def validate_video_state_label(cls, v):
        if not v or not v.strip():
            raise ValueError('Video state label cannot be empty')
        if len(v) > 64:
            raise ValueError('Video state label must be less than 64 characters')
        return v.strip()

    @field_validator('video_state_value')
    @classmethod
    def validate_video_state_value(cls, v):
        if v < -1 or v > 5:
            raise ValueError('Video state value must be between -1 and 5')
        return v

class YouTubeWatchEventResponseModel(SQLModel, table=False):
    id: int = Field(primary_key=True)
    video_id: str = Field(index=True)
    current_time: float
    time: datetime

class VideoStat(BaseModel):
    time: datetime
    video_id: str
    total_events: int
    max_viewership: Optional[float] = PydanticField(default=-1)
    avg_viewership: Optional[float] = PydanticField(default=-1)
    unique_views: Optional[int] = PydanticField(default=-1)