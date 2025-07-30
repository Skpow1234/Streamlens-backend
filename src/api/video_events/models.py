from datetime import datetime
from typing import Optional
from pydantic import constr, conint, confloat

from timescaledb import TimescaleModel
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import SQLModel, Field

class YouTubeWatchEvent(TimescaleModel, table=True):
    """A time-series event representing a YouTube player's state change."""
    id: Optional[int] = Field(default=None, primary_key=True)
    is_ready: bool
    video_id: constr(min_length=1) = Field(index=True)
    video_title: constr(min_length=1)
    current_time: confloat(ge=0)
    video_state_label: constr(min_length=1)
    video_state_value: int
    referer: Optional[str] = Field(default="", index=True)
    watch_session_id: Optional[str] = Field(index=True)
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
    video_id: constr(min_length=1) = Field(index=True)
    video_title: constr(min_length=1)
    current_time: confloat(ge=0)
    video_state_label: constr(min_length=1)
    video_state_value: int

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