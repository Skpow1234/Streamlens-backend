import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import and_, func

from api.db.session import get_session
from api.auth.utils import get_current_user
from api.db.models import User, Playlist, PlaylistItem

# Set up logging
logger = logging.getLogger("playlists")

router = APIRouter()


# Playlist CRUD Endpoints
@router.post("/", response_model=dict)
def create_playlist(
    name: str,
    description: Optional[str] = None,
    is_public: bool = False,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new playlist.
    """
    # Validate input
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Playlist name cannot be empty")

    if len(name.strip()) > 100:
        raise HTTPException(status_code=400, detail="Playlist name too long (max 100 characters)")

    if description and len(description) > 500:
        raise HTTPException(status_code=400, detail="Description too long (max 500 characters)")

    try:
        new_playlist = Playlist(
            user_id=current_user.id,
            name=name.strip(),
            description=description.strip() if description else "",
            is_public=is_public
        )
        db_session.add(new_playlist)
        db_session.commit()
        db_session.refresh(new_playlist)

        logger.info(f"User {current_user.id} created playlist '{name}'")
        return {
            "message": "Playlist created successfully",
            "playlist": {
                "id": new_playlist.id,
                "name": new_playlist.name,
                "description": new_playlist.description,
                "is_public": new_playlist.is_public,
                "created_at": new_playlist.created_at.isoformat()
            }
        }

    except SQLAlchemyError as e:
        logger.error(f"Database error in create_playlist: {e}")
        db_session.rollback()
        raise HTTPException(status_code=500, detail="Database error")


@router.get("/", response_model=dict)
def get_user_playlists(
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Get all playlists for the current user.
    """
    try:
        playlists = db_session.exec(
            select(Playlist).where(Playlist.user_id == current_user.id)
            .order_by(Playlist.updated_at.desc())
        ).all()

        playlists_with_counts = []
        for playlist in playlists:
            # Get item count for each playlist
            item_count = db_session.exec(
                select(func.count()).where(PlaylistItem.playlist_id == playlist.id)
            ).first()

            playlists_with_counts.append({
                "id": playlist.id,
                "name": playlist.name,
                "description": playlist.description,
                "is_public": playlist.is_public,
                "created_at": playlist.created_at.isoformat(),
                "updated_at": playlist.updated_at.isoformat(),
                "item_count": item_count or 0
            })

        return {
            "playlists": playlists_with_counts,
            "total": len(playlists_with_counts)
        }

    except SQLAlchemyError as e:
        logger.error(f"Database error in get_user_playlists: {e}")
        raise HTTPException(status_code=500, detail="Database error")


@router.get("/{playlist_id}", response_model=dict)
def get_playlist_details(
    playlist_id: int,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Get detailed information about a playlist including its items.
    """
    try:
        playlist = db_session.get(Playlist, playlist_id)

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        if playlist.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to view this playlist")

        # Get playlist items
        items = db_session.exec(
            select(PlaylistItem)
            .where(PlaylistItem.playlist_id == playlist_id)
            .order_by(PlaylistItem.position, PlaylistItem.added_at)
        ).all()

        return {
            "playlist": {
                "id": playlist.id,
                "name": playlist.name,
                "description": playlist.description,
                "is_public": playlist.is_public,
                "created_at": playlist.created_at.isoformat(),
                "updated_at": playlist.updated_at.isoformat()
            },
            "items": [
                {
                    "id": item.id,
                    "video_id": item.video_id,
                    "video_title": item.video_title,
                    "added_at": item.added_at.isoformat(),
                    "position": item.position
                }
                for item in items
            ],
            "total_items": len(items)
        }

    except SQLAlchemyError as e:
        logger.error(f"Database error in get_playlist_details: {e}")
        raise HTTPException(status_code=500, detail="Database error")


@router.put("/{playlist_id}", response_model=dict)
def update_playlist(
    playlist_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    is_public: Optional[bool] = None,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Update playlist information.
    """
    try:
        playlist = db_session.get(Playlist, playlist_id)

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        if playlist.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to edit this playlist")

        # Validate and update fields
        if name is not None:
            if not name.strip():
                raise HTTPException(status_code=400, detail="Playlist name cannot be empty")
            if len(name.strip()) > 100:
                raise HTTPException(status_code=400, detail="Playlist name too long (max 100 characters)")
            playlist.name = name.strip()

        if description is not None:
            if len(description) > 500:
                raise HTTPException(status_code=400, detail="Description too long (max 500 characters)")
            playlist.description = description

        if is_public is not None:
            playlist.is_public = is_public

        playlist.updated_at = datetime.utcnow()
        db_session.commit()
        db_session.refresh(playlist)

        logger.info(f"User {current_user.id} updated playlist {playlist_id}")
        return {
            "message": "Playlist updated successfully",
            "playlist": {
                "id": playlist.id,
                "name": playlist.name,
                "description": playlist.description,
                "is_public": playlist.is_public,
                "updated_at": playlist.updated_at.isoformat()
            }
        }

    except SQLAlchemyError as e:
        logger.error(f"Database error in update_playlist: {e}")
        db_session.rollback()
        raise HTTPException(status_code=500, detail="Database error")


@router.delete("/{playlist_id}", response_model=dict)
def delete_playlist(
    playlist_id: int,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a playlist and all its items.
    """
    try:
        playlist = db_session.get(Playlist, playlist_id)

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        if playlist.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this playlist")

        # Delete playlist items first (due to foreign key constraint)
        db_session.exec(delete(PlaylistItem).where(PlaylistItem.playlist_id == playlist_id))

        # Delete playlist
        db_session.delete(playlist)
        db_session.commit()

        logger.info(f"User {current_user.id} deleted playlist {playlist_id}")
        return {"message": "Playlist deleted successfully"}

    except SQLAlchemyError as e:
        logger.error(f"Database error in delete_playlist: {e}")
        db_session.rollback()
        raise HTTPException(status_code=500, detail="Database error")


# Playlist Item Management
@router.post("/{playlist_id}/items", response_model=dict)
def add_video_to_playlist(
    playlist_id: int,
    video_id: str,
    video_title: str,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Add a video to a playlist.
    """
    # Validate input
    if not video_id or not video_id.strip():
        raise HTTPException(status_code=400, detail="Video ID cannot be empty")

    if len(video_id.strip()) > 32:
        raise HTTPException(status_code=400, detail="Video ID too long")

    if not video_title or not video_title.strip():
        raise HTTPException(status_code=400, detail="Video title cannot be empty")

    if len(video_title.strip()) > 255:
        raise HTTPException(status_code=400, detail="Video title too long")

    try:
        # Check if playlist exists and belongs to user
        playlist = db_session.get(Playlist, playlist_id)
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        if playlist.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to modify this playlist")

        # Check if video is already in playlist
        existing_item = db_session.exec(
            select(PlaylistItem).where(
                and_(
                    PlaylistItem.playlist_id == playlist_id,
                    PlaylistItem.video_id == video_id.strip()
                )
            )
        ).first()

        if existing_item:
            return {"message": "Video already in playlist", "item_id": existing_item.id}

        # Get next position
        max_position = db_session.exec(
            select(func.max(PlaylistItem.position))
            .where(PlaylistItem.playlist_id == playlist_id)
        ).first() or 0

        new_item = PlaylistItem(
            playlist_id=playlist_id,
            video_id=video_id.strip(),
            video_title=video_title.strip(),
            position=max_position + 1
        )

        db_session.add(new_item)
        db_session.commit()
        db_session.refresh(new_item)

        # Update playlist's updated_at timestamp
        playlist.updated_at = datetime.utcnow()
        db_session.commit()

        logger.info(f"User {current_user.id} added video {video_id} to playlist {playlist_id}")
        return {
            "message": "Video added to playlist successfully",
            "item": {
                "id": new_item.id,
                "video_id": new_item.video_id,
                "video_title": new_item.video_title,
                "position": new_item.position,
                "added_at": new_item.added_at.isoformat()
            }
        }

    except SQLAlchemyError as e:
        logger.error(f"Database error in add_video_to_playlist: {e}")
        db_session.rollback()
        raise HTTPException(status_code=500, detail="Database error")


@router.delete("/{playlist_id}/items/{item_id}", response_model=dict)
def remove_video_from_playlist(
    playlist_id: int,
    item_id: int,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Remove a video from a playlist.
    """
    try:
        # Check if playlist belongs to user
        playlist = db_session.get(Playlist, playlist_id)
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        if playlist.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to modify this playlist")

        # Find and delete the item
        item = db_session.get(PlaylistItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Playlist item not found")

        if item.playlist_id != playlist_id:
            raise HTTPException(status_code=400, detail="Item does not belong to this playlist")

        db_session.delete(item)
        db_session.commit()

        # Update playlist's updated_at timestamp
        playlist.updated_at = datetime.utcnow()
        db_session.commit()

        logger.info(f"User {current_user.id} removed video from playlist {playlist_id}")
        return {"message": "Video removed from playlist successfully"}

    except SQLAlchemyError as e:
        logger.error(f"Database error in remove_video_from_playlist: {e}")
        db_session.rollback()
        raise HTTPException(status_code=500, detail="Database error")


@router.put("/{playlist_id}/items/{item_id}/position", response_model=dict)
def update_item_position(
    playlist_id: int,
    item_id: int,
    position: int,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Update the position of an item in a playlist.
    """
    if position < 0:
        raise HTTPException(status_code=400, detail="Position must be non-negative")

    try:
        # Check if playlist belongs to user
        playlist = db_session.get(Playlist, playlist_id)
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        if playlist.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to modify this playlist")

        # Find and update the item
        item = db_session.get(PlaylistItem, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Playlist item not found")

        if item.playlist_id != playlist_id:
            raise HTTPException(status_code=400, detail="Item does not belong to this playlist")

        item.position = position
        db_session.commit()
        db_session.refresh(item)

        logger.info(f"User {current_user.id} updated item position in playlist {playlist_id}")
        return {
            "message": "Item position updated successfully",
            "item": {
                "id": item.id,
                "position": item.position
            }
        }

    except SQLAlchemyError as e:
        logger.error(f"Database error in update_item_position: {e}")
        db_session.rollback()
        raise HTTPException(status_code=500, detail="Database error")
