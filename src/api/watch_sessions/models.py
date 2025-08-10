import uuid
from datetime import datetime
from typing import Optional

from timescaledb import TimescaleModel
from timescaledb.utils import get_utc_now
from sqlmodel import SQLModel, Field

def generate_session_id():
    return str(uuid.uuid4())

class WatchSession(TimescaleModel, table=True):  # type: ignore[call-arg]
    """A session representing a user's watch activity."""
    id: Optional[int] = Field(default=None, primary_key=True)
    watch_session_id: str = Field(
        default_factory=generate_session_id,
        index=True,
        unique=True,
        min_length=1,
        max_length=64,
    )
    path: Optional[str] = Field(
        default="",
        index=True,
        min_length=1,
        max_length=255,
    )
    referer: Optional[str] = Field(default="", index=True, max_length=255)
    video_id: Optional[str] = Field(default="", index=True, min_length=1, max_length=32)
    last_active: Optional[datetime] = Field(default_factory=get_utc_now)
    user_id: int = Field(foreign_key="user.id")

    # timescaledb config
    __chunk_time_interval__ = "INTERVAL 30 days"
    __drop_after__ = "INTERVAL 3 years"

class WatchSessionCreate(SQLModel, table=False):
    """Schema for creating a new watch session. Requires a non-empty video_id and a valid path."""
    path: Optional[str] = Field(default="", min_length=1, max_length=255)
    video_id: str = Field(
        ..., min_length=1, max_length=32, description="YouTube video ID must not be empty."
    )


class WatchSessionResponse(SQLModel, table=False):
    """Response schema for watch sessions to avoid leaking internal fields."""
    id: Optional[int]
    watch_session_id: str
    path: Optional[str] = ""
    referer: Optional[str] = ""
    video_id: Optional[str] = ""
    last_active: Optional[datetime]