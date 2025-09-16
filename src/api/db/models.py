from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    email: str = Field(index=True, unique=True)
    hashed_password: str


class VideoLike(SQLModel, table=True):
    """Tracks user likes for videos."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    video_id: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = {'extend_existing': True}


class VideoComment(SQLModel, table=True):
    """Stores comments on videos."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    video_id: str = Field(index=True)
    content: str = Field(max_length=1000)
    timestamp: Optional[float] = Field(default=None)  # Video timestamp where comment was made
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = {'extend_existing': True}


class Playlist(SQLModel, table=True):
    """User-created playlists for organizing videos."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str = Field(max_length=100)
    description: Optional[str] = Field(default="", max_length=500)
    is_public: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = {'extend_existing': True}


class PlaylistItem(SQLModel, table=True):
    """Items in playlists."""
    id: Optional[int] = Field(default=None, primary_key=True)
    playlist_id: int = Field(foreign_key="playlist.id", index=True)
    video_id: str = Field(index=True)
    video_title: str = Field(max_length=255)
    added_at: datetime = Field(default_factory=datetime.utcnow)
    position: int = Field(default=0)  # For ordering items in playlist

    __table_args__ = {'extend_existing': True}
