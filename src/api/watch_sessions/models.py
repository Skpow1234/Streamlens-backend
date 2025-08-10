import uuid
from datetime import datetime
from typing import Optional
from pydantic import constr

from timescaledb import TimescaleModel
from timescaledb.utils import get_utc_now
from sqlmodel import SQLModel, Field

def generate_session_id():
    return str(uuid.uuid4())

class WatchSession(TimescaleModel, table=True):
    """A session representing a user's watch activity."""
    id: Optional[int] = Field(default=None, primary_key=True)
    watch_session_id: constr(min_length=1, max_length=64, pattern=r'^[\w\-]+$') = Field(
        default_factory=generate_session_id, index=True
    )
    path: Optional[constr(min_length=1, max_length=255, pattern=r'^[\w\-/]+$')] = Field(default="", index=True)
    referer: Optional[constr(max_length=255)] = Field(default="", index=True)
    video_id: Optional[constr(min_length=1, max_length=32)] = Field(default="", index=True)
    last_active: Optional[datetime] = Field(default_factory=get_utc_now)
    user_id: int = Field(foreign_key="user.id")

    # timescaledb config
    __chunk_time_interval__ = "INTERVAL 30 days"
    __drop_after__ = "INTERVAL 3 years"

class WatchSessionCreate(SQLModel, table=False):
    """Schema for creating a new watch session. Requires a non-empty video_id and a valid path."""
    path: Optional[constr(min_length=1, max_length=255, pattern=r'^[\w\-/]+$')] = Field(default="")
    video_id: constr(min_length=1, max_length=32) = Field(..., description="YouTube video ID must not be empty.")