import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, delete
from sqlalchemy.exc import SQLAlchemyError

from api.db.session import get_session
from api.auth.utils import get_current_user
from api.db.models import User, VideoLike, VideoComment

# Set up logging
logger = logging.getLogger("social")

router = APIRouter()


# Video Likes Endpoints
@router.post("/videos/{video_id}/like")
def like_video(
    video_id: str,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Like a video. If already liked, this is a no-op.
    """
    try:
        # Check if user already liked this video
        existing_like = db_session.exec(
            select(VideoLike).where(
                VideoLike.user_id == current_user.id,
                VideoLike.video_id == video_id
            )
        ).first()

        if existing_like:
            # Already liked, return success
            return {"message": "Video already liked", "liked": True}

        # Create new like
        new_like = VideoLike(
            user_id=current_user.id,
            video_id=video_id
        )
        db_session.add(new_like)
        db_session.commit()
        db_session.refresh(new_like)

        logger.info(f"User {current_user.id} liked video {video_id}")
        return {"message": "Video liked successfully", "liked": True, "like_id": new_like.id}

    except SQLAlchemyError as e:
        logger.error(f"Database error in like_video: {e}")
        db_session.rollback()
        raise HTTPException(status_code=500, detail="Database error")


@router.delete("/videos/{video_id}/like")
def unlike_video(
    video_id: str,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Remove like from a video.
    """
    try:
        # Find and delete the like
        like = db_session.exec(
            select(VideoLike).where(
                VideoLike.user_id == current_user.id,
                VideoLike.video_id == video_id
            )
        ).first()

        if not like:
            return {"message": "Video not liked", "liked": False}

        db_session.delete(like)
        db_session.commit()

        logger.info(f"User {current_user.id} unliked video {video_id}")
        return {"message": "Video unliked successfully", "liked": False}

    except SQLAlchemyError as e:
        logger.error(f"Database error in unlike_video: {e}")
        db_session.rollback()
        raise HTTPException(status_code=500, detail="Database error")


@router.get("/videos/{video_id}/like/status")
def get_like_status(
    video_id: str,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Check if user has liked a video.
    """
    like = db_session.exec(
        select(VideoLike).where(
            VideoLike.user_id == current_user.id,
            VideoLike.video_id == video_id
        )
    ).first()

    return {
        "liked": like is not None,
        "like_id": like.id if like else None,
        "video_id": video_id
    }


@router.get("/videos/{video_id}/likes/count")
def get_likes_count(
    video_id: str,
    db_session: Session = Depends(get_session),
):
    """
    Get the number of likes for a video.
    """
    count = db_session.exec(
        select(VideoLike).where(VideoLike.video_id == video_id)
    ).all()

    return {"video_id": video_id, "likes_count": len(count)}


# Video Comments Endpoints
@router.post("/videos/{video_id}/comments")
def create_comment(
    video_id: str,
    content: str,
    timestamp: Optional[float] = None,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Create a comment on a video.
    """
    # Validate input
    if not content or not content.strip():
        raise HTTPException(status_code=400, detail="Comment content cannot be empty")

    if len(content.strip()) > 1000:
        raise HTTPException(status_code=400, detail="Comment content too long (max 1000 characters)")

    try:
        new_comment = VideoComment(
            user_id=current_user.id,
            video_id=video_id,
            content=content.strip(),
            timestamp=timestamp
        )
        db_session.add(new_comment)
        db_session.commit()
        db_session.refresh(new_comment)

        logger.info(f"User {current_user.id} commented on video {video_id}")
        return {
            "message": "Comment created successfully",
            "comment": {
                "id": new_comment.id,
                "user_id": new_comment.user_id,
                "video_id": new_comment.video_id,
                "content": new_comment.content,
                "timestamp": new_comment.timestamp,
                "created_at": new_comment.created_at.isoformat(),
                "username": current_user.username
            }
        }

    except SQLAlchemyError as e:
        logger.error(f"Database error in create_comment: {e}")
        db_session.rollback()
        raise HTTPException(status_code=500, detail="Database error")


@router.get("/videos/{video_id}/comments")
def get_video_comments(
    video_id: str,
    limit: int = 50,
    offset: int = 0,
    db_session: Session = Depends(get_session),
):
    """
    Get comments for a video.
    """
    limit = max(1, min(100, limit))  # Limit between 1 and 100
    offset = max(0, offset)

    comments = db_session.exec(
        select(VideoComment, User.username)
        .join(User, VideoComment.user_id == User.id)
        .where(VideoComment.video_id == video_id)
        .order_by(VideoComment.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    return {
        "video_id": video_id,
        "comments": [
            {
                "id": comment.id,
                "user_id": comment.user_id,
                "username": username,
                "content": comment.content,
                "timestamp": comment.timestamp,
                "created_at": comment.created_at.isoformat(),
                "updated_at": comment.updated_at.isoformat()
            }
            for comment, username in comments
        ],
        "total": len(comments),
        "limit": limit,
        "offset": offset
    }


@router.put("/comments/{comment_id}")
def update_comment(
    comment_id: int,
    content: str,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Update a comment (only by the comment author).
    """
    if not content or not content.strip():
        raise HTTPException(status_code=400, detail="Comment content cannot be empty")

    if len(content.strip()) > 1000:
        raise HTTPException(status_code=400, detail="Comment content too long (max 1000 characters)")

    try:
        comment = db_session.get(VideoComment, comment_id)

        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")

        if comment.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to edit this comment")

        comment.content = content.strip()
        comment.updated_at = datetime.utcnow()
        db_session.commit()
        db_session.refresh(comment)

        logger.info(f"User {current_user.id} updated comment {comment_id}")
        return {
            "message": "Comment updated successfully",
            "comment": {
                "id": comment.id,
                "content": comment.content,
                "updated_at": comment.updated_at.isoformat()
            }
        }

    except SQLAlchemyError as e:
        logger.error(f"Database error in update_comment: {e}")
        db_session.rollback()
        raise HTTPException(status_code=500, detail="Database error")


@router.delete("/comments/{comment_id}")
def delete_comment(
    comment_id: int,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a comment (only by the comment author).
    """
    try:
        comment = db_session.get(VideoComment, comment_id)

        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")

        if comment.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this comment")

        db_session.delete(comment)
        db_session.commit()

        logger.info(f"User {current_user.id} deleted comment {comment_id}")
        return {"message": "Comment deleted successfully"}

    except SQLAlchemyError as e:
        logger.error(f"Database error in delete_comment: {e}")
        db_session.rollback()
        raise HTTPException(status_code=500, detail="Database error")


@router.post("/videos/{video_id}/share")
def share_video(
    video_id: str,
    timestamp: Optional[float] = None,
    current_user: User = Depends(get_current_user),
):
    """
    Generate a shareable link for a video at a specific timestamp.
    """
    base_url = "http://localhost:3000"  # This should be configurable

    if timestamp and timestamp > 0:
        share_url = f"{base_url}/watch?v={video_id}&t={int(timestamp)}"
    else:
        share_url = f"{base_url}/watch?v={video_id}"

    return {
        "share_url": share_url,
        "video_id": video_id,
        "timestamp": timestamp,
        "shared_by": current_user.username
    }
