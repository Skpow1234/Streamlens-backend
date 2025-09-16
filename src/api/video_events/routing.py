import logging
import re
from typing import List, Any, cast, Tuple
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request, Depends, HTTPException

from sqlalchemy import func, or_, and_, desc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, select
from pydantic import ValidationError

from timescaledb.hyperfunctions import time_bucket
from timescaledb.utils import get_utc_now

from api.utils import parse_int_or_fallback
from api.db.session import get_session
from api.watch_sessions.models import WatchSession
from api.auth.utils import get_current_user
from api.db.models import User

from .models import (
    YouTubePlayerState,
    YouTubeWatchEvent,
    YouTubeWatchEventResponseModel,
    VideoStat,
)

# Set up logging
logger = logging.getLogger("video_events")

router = APIRouter()

@router.get("/", response_model=List[YouTubeWatchEventResponseModel])
def get_all_video_events(
    limit: int = 100,
    offset: int = 0,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Get all video events for the current user.
    - Query params: limit (int, default=100), offset (int, default=0)
    - Returns: List of YouTubeWatchEventResponseModel
    """
    limit = max(1, min(1000, limit))
    offset = max(0, offset)
    query = (
        select(YouTubeWatchEvent)
        .where(YouTubeWatchEvent.user_id == current_user.id)
        .order_by(YouTubeWatchEvent.time.desc())
        .offset(offset)
        .limit(limit)
    )
    events = db_session.exec(query).all()
    logger.info(f"Retrieved {len(events)} video events for user {current_user.id}")
    return events


@router.get("/stats/user", response_model=dict)
def get_user_statistics(
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Get comprehensive user statistics for dashboard.
    - Returns: User stats including total watch time, video count, session count, etc.
    """
    # Total videos watched (unique video IDs)
    unique_videos = db_session.exec(
        select(func.count(func.distinct(YouTubeWatchEvent.video_id)))
        .where(YouTubeWatchEvent.user_id == current_user.id)
    ).first()

    # Total watch sessions
    total_sessions = db_session.exec(
        select(func.count(func.distinct(YouTubeWatchEvent.watch_session_id)))
        .where(YouTubeWatchEvent.user_id == current_user.id)
    ).first()

    # Total watch time (sum of current_time for latest events per video)
    # This is a simplified calculation - in practice you'd want more sophisticated logic
    total_time_query = select(func.sum(YouTubeWatchEvent.current_time)).where(
        YouTubeWatchEvent.user_id == current_user.id
    )
    total_time = db_session.exec(total_time_query).first() or 0

    # Recent activity (last 10 events)
    recent_activity = db_session.exec(
        select(YouTubeWatchEvent)
        .where(YouTubeWatchEvent.user_id == current_user.id)
        .order_by(YouTubeWatchEvent.time.desc())
        .limit(10)
    ).all()

    # Most watched videos
    most_watched = db_session.exec(
        select(
            YouTubeWatchEvent.video_id,
            YouTubeWatchEvent.video_title,
            func.count().label("watch_count"),
            func.max(YouTubeWatchEvent.current_time).label("max_time")
        )
        .where(YouTubeWatchEvent.user_id == current_user.id)
        .group_by(YouTubeWatchEvent.video_id, YouTubeWatchEvent.video_title)
        .order_by(func.count().desc())
        .limit(5)
    ).all()

    # Watch time by day (last 30 days)
    thirty_days_ago = datetime.now() - timedelta(days=30)
    daily_stats = db_session.exec(
        select(
            func.date(YouTubeWatchEvent.time).label("date"),
            func.count().label("events_count"),
            func.sum(YouTubeWatchEvent.current_time).label("total_time")
        )
        .where(
            YouTubeWatchEvent.user_id == current_user.id,
            YouTubeWatchEvent.time >= thirty_days_ago
        )
        .group_by(func.date(YouTubeWatchEvent.time))
        .order_by(func.date(YouTubeWatchEvent.time))
    ).all()

    # Get hourly activity patterns (for heatmap)
    hourly_patterns = db_session.exec(
        select(
            func.extract('hour', YouTubeWatchEvent.time).label("hour"),
            func.extract('dow', YouTubeWatchEvent.time).label("day_of_week"),
            func.count().label("activity_count")
        )
        .where(
            YouTubeWatchEvent.user_id == current_user.id,
            YouTubeWatchEvent.time >= thirty_days_ago
        )
        .group_by(
            func.extract('hour', YouTubeWatchEvent.time),
            func.extract('dow', YouTubeWatchEvent.time)
        )
        .order_by(
            func.extract('dow', YouTubeWatchEvent.time),
            func.extract('hour', YouTubeWatchEvent.time)
        )
    ).all()

    # Get video engagement metrics (completion rates, average watch time)
    video_engagement = db_session.exec(
        select(
            YouTubeWatchEvent.video_id,
            YouTubeWatchEvent.video_title,
            func.count().label("total_events"),
            func.avg(YouTubeWatchEvent.current_time).label("avg_watch_time"),
            func.max(YouTubeWatchEvent.current_time).label("max_watch_time"),
            func.min(YouTubeWatchEvent.current_time).label("min_watch_time")
        )
        .where(YouTubeWatchEvent.user_id == current_user.id)
        .group_by(YouTubeWatchEvent.video_id, YouTubeWatchEvent.video_title)
        .having(func.count() >= 3)  # Only videos with multiple views
        .order_by(func.count().desc())
        .limit(10)
    ).all()

    # Get session duration analysis
    session_durations = db_session.exec(
        select(
            func.avg(YouTubeWatchEvent.current_time).label("avg_session_time"),
            func.min(YouTubeWatchEvent.current_time).label("min_session_time"),
            func.max(YouTubeWatchEvent.current_time).label("max_session_time"),
            func.count(func.distinct(YouTubeWatchEvent.watch_session_id)).label("session_count")
        )
        .where(YouTubeWatchEvent.user_id == current_user.id)
    ).all()

    return {
        "user_id": current_user.id,
        "username": current_user.username,
        "total_videos_watched": unique_videos,
        "total_sessions": total_sessions,
        "total_watch_time_seconds": total_time,
        "recent_activity": [
            {
                "id": activity.id,
                "video_id": activity.video_id,
                "video_title": activity.video_title,
                "current_time": activity.current_time,
                "time": activity.time.isoformat(),
                "video_state_label": activity.video_state_label
            }
            for activity in recent_activity
        ],
        "most_watched_videos": [
            {
                "video_id": video.video_id,
                "video_title": video.video_title,
                "watch_count": video.watch_count,
                "max_time": video.max_time
            }
            for video in most_watched
        ],
        "daily_stats": [
            {
                "date": stat.date.isoformat(),
                "events_count": stat.events_count,
                "total_time": stat.total_time
            }
            for stat in daily_stats
        ],
        "hourly_patterns": [
            {
                "hour": int(pattern.hour),
                "day_of_week": int(pattern.day_of_week),
                "activity_count": pattern.activity_count
            }
            for pattern in hourly_patterns
        ],
        "video_engagement": [
            {
                "video_id": video.video_id,
                "video_title": video.video_title,
                "total_events": video.total_events,
                "avg_watch_time": float(video.avg_watch_time or 0),
                "max_watch_time": float(video.max_watch_time or 0),
                "min_watch_time": float(video.min_watch_time or 0)
            }
            for video in video_engagement
        ],
        "session_analysis": {
            "avg_session_time": float(session_durations[0].avg_session_time or 0) if session_durations else 0,
            "min_session_time": float(session_durations[0].min_session_time or 0) if session_durations else 0,
            "max_session_time": float(session_durations[0].max_session_time or 0) if session_durations else 0,
            "total_sessions": int(session_durations[0].session_count or 0) if session_durations else 0
        }
    }


@router.get("/search", response_model=List[dict])
def search_video_events(
    query: str = "",
    video_title: str = "",
    min_watch_time: int = 0,
    max_watch_time: int = 0,
    start_date: datetime = None,
    end_date: datetime = None,
    sort_by: str = "time",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Advanced search for video events with full-text search capabilities.
    - Query parameters: query (general search), video_title, min_watch_time, max_watch_time, start_date, end_date, sort_by, sort_order, limit, offset
    - Returns: List of matching video events with metadata
    """
    limit = max(1, min(200, limit))
    offset = max(0, offset)

    # Build base query
    query_builder = select(
        YouTubeWatchEvent,
        func.count(YouTubeWatchEvent.id).label("watch_count"),
        func.sum(YouTubeWatchEvent.current_time).label("total_watch_time"),
        func.max(YouTubeWatchEvent.time).label("last_watched")
    ).where(YouTubeWatchEvent.user_id == current_user.id)

    # Apply filters
    if query:
        # Search in video_id and video_title
        query_builder = query_builder.where(
            or_(
                YouTubeWatchEvent.video_id.ilike(f"%{query}%"),
                YouTubeWatchEvent.video_title.ilike(f"%{query}%")
            )
        )

    if video_title:
        query_builder = query_builder.where(
            YouTubeWatchEvent.video_title.ilike(f"%{video_title}%")
        )

    if min_watch_time > 0:
        query_builder = query_builder.where(YouTubeWatchEvent.current_time >= min_watch_time)

    if max_watch_time > 0:
        query_builder = query_builder.where(YouTubeWatchEvent.current_time <= max_watch_time)

    if start_date:
        query_builder = query_builder.where(YouTubeWatchEvent.time >= start_date)

    if end_date:
        query_builder = query_builder.where(YouTubeWatchEvent.time <= end_date)

    # Group by video to get aggregated stats
    query_builder = query_builder.group_by(YouTubeWatchEvent.video_id)

    # Apply sorting
    if sort_by == "watch_count":
        query_builder = query_builder.order_by(
            desc(func.count(YouTubeWatchEvent.id)) if sort_order == "desc" else func.count(YouTubeWatchEvent.id)
        )
    elif sort_by == "total_watch_time":
        query_builder = query_builder.order_by(
            desc(func.sum(YouTubeWatchEvent.current_time)) if sort_order == "desc" else func.sum(YouTubeWatchEvent.current_time)
        )
    elif sort_by == "last_watched":
        query_builder = query_builder.order_by(
            desc(func.max(YouTubeWatchEvent.time)) if sort_order == "desc" else func.max(YouTubeWatchEvent.time)
        )
    else:  # default to time
        query_builder = query_builder.order_by(
            desc(func.max(YouTubeWatchEvent.time)) if sort_order == "desc" else func.max(YouTubeWatchEvent.time)
        )

    # Apply pagination
    query_builder = query_builder.offset(offset).limit(limit)

    results = db_session.exec(query_builder).all()

    # Format results
    search_results = []
    for event, watch_count, total_watch_time, last_watched in results:
        search_results.append({
            "video_id": event.video_id,
            "video_title": event.video_title or "Unknown Title",
            "watch_count": watch_count,
            "total_watch_time": int(total_watch_time or 0),
            "last_watched": last_watched.isoformat() if last_watched else None,
            "average_watch_time": round((total_watch_time or 0) / watch_count, 2) if watch_count > 0 else 0
        })

    logger.info(f"Search returned {len(search_results)} results for user {current_user.id}")
    return search_results

@router.get("/recommendations", response_model=List[dict])
def get_video_recommendations(
    limit: int = 10,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Get personalized video recommendations based on watch history.
    - Query parameters: limit (default 10)
    - Returns: List of recommended videos with similarity scores
    """
    limit = max(1, min(50, limit))

    # Get user's most watched videos to base recommendations on
    user_videos_query = select(
        YouTubeWatchEvent.video_id,
        YouTubeWatchEvent.video_title,
        func.count(YouTubeWatchEvent.id).label("watch_count"),
        func.avg(YouTubeWatchEvent.current_time).label("avg_watch_time")
    ).where(YouTubeWatchEvent.user_id == current_user.id)
    user_videos_query = user_videos_query.group_by(
        YouTubeWatchEvent.video_id,
        YouTubeWatchEvent.video_title
    ).order_by(desc("watch_count")).limit(20)

    user_videos = db_session.exec(user_videos_query).all()

    if not user_videos:
        return []

    # Find videos that are frequently watched together (simple co-occurrence)
    recommendations = []

    for video_id, title, watch_count, avg_watch_time in user_videos[:5]:  # Use top 5 most watched
        # Find other videos that appear in similar sessions
        related_query = select(
            YouTubeWatchEvent.video_id,
            YouTubeWatchEvent.video_title,
            func.count(YouTubeWatchEvent.id).label("co_occurrence")
        ).where(
            and_(
                YouTubeWatchEvent.user_id == current_user.id,
                YouTubeWatchEvent.video_id != video_id,
                YouTubeWatchEvent.time >= select(func.min(YouTubeWatchEvent.time)).where(
                    and_(
                        YouTubeWatchEvent.user_id == current_user.id,
                        YouTubeWatchEvent.video_id == video_id
                    )
                ).scalar_subquery()
            )
        ).group_by(
            YouTubeWatchEvent.video_id,
            YouTubeWatchEvent.video_title
        ).order_by(desc("co_occurrence")).limit(5)

        related_videos = db_session.exec(related_query).all()

        for rel_video_id, rel_title, co_occurrence in related_videos:
            # Avoid duplicates
            if not any(r["video_id"] == rel_video_id for r in recommendations):
                recommendations.append({
                    "video_id": rel_video_id,
                    "video_title": rel_title or "Unknown Title",
                    "similarity_score": min(100, co_occurrence * 20),  # Normalize to 0-100
                    "reason": f"Watched together with {title[:30]}..."
                })

    # If we don't have enough recommendations, add trending videos
    if len(recommendations) < limit:
        trending_query = select(
            YouTubeWatchEvent.video_id,
            YouTubeWatchEvent.video_title,
            func.count(YouTubeWatchEvent.id).label("total_views")
        ).where(
            and_(
                YouTubeWatchEvent.user_id != current_user.id,  # Other users' videos
                YouTubeWatchEvent.time >= datetime.utcnow() - timedelta(days=7),  # Last 7 days
                ~YouTubeWatchEvent.video_id.in_([r["video_id"] for r in recommendations])  # Not already recommended
            )
        ).group_by(
            YouTubeWatchEvent.video_id,
            YouTubeWatchEvent.video_title
        ).order_by(desc("total_views")).limit(limit - len(recommendations))

        trending_videos = db_session.exec(trending_query).all()

        for video_id, title, total_views in trending_videos:
            recommendations.append({
                "video_id": video_id,
                "video_title": title or "Unknown Title",
                "similarity_score": min(100, total_views),
                "reason": "Trending this week"
            })

    logger.info(f"Generated {len(recommendations)} recommendations for user {current_user.id}")
    return recommendations[:limit]

@router.get("/trending", response_model=List[dict])
def get_trending_videos(
    timeframe: str = "week",  # day, week, month
    limit: int = 20,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Get trending videos based on watch activity.
    - Query parameters: timeframe (day/week/month), limit (default 20)
    - Returns: List of trending videos with activity metrics
    """
    limit = max(1, min(100, limit))

    # Calculate timeframe
    now = datetime.utcnow()
    if timeframe == "day":
        start_time = now - timedelta(days=1)
    elif timeframe == "month":
        start_time = now - timedelta(days=30)
    else:  # week
        start_time = now - timedelta(days=7)

    # Get trending videos
    trending_query = select(
        YouTubeWatchEvent.video_id,
        YouTubeWatchEvent.video_title,
        func.count(YouTubeWatchEvent.id).label("total_views"),
        func.count(func.distinct(YouTubeWatchEvent.user_id)).label("unique_watchers"),
        func.avg(YouTubeWatchEvent.current_time).label("avg_watch_time"),
        func.max(YouTubeWatchEvent.time).label("last_activity")
    ).where(
        and_(
            YouTubeWatchEvent.time >= start_time,
            YouTubeWatchEvent.user_id != current_user.id  # Exclude user's own views
        )
    ).group_by(
        YouTubeWatchEvent.video_id,
        YouTubeWatchEvent.video_title
    ).having(
        func.count(YouTubeWatchEvent.id) >= 3  # At least 3 views to be considered trending
    ).order_by(desc("total_views")).limit(limit)

    trending_videos = db_session.exec(trending_query).all()

    results = []
    for video_id, title, total_views, unique_watchers, avg_watch_time, last_activity in trending_videos:
        # Calculate trending score (views * uniqueness * recency)
        hours_since_activity = (now - last_activity).total_seconds() / 3600
        recency_score = max(0.1, 1 - (hours_since_activity / 168))  # Decay over 7 days
        trending_score = int((total_views * unique_watchers * recency_score) / 10)

        results.append({
            "video_id": video_id,
            "video_title": title or "Unknown Title",
            "total_views": total_views,
            "unique_watchers": unique_watchers,
            "average_watch_time": round(avg_watch_time, 2) if avg_watch_time else 0,
            "trending_score": trending_score,
            "last_activity": last_activity.isoformat(),
            "timeframe": timeframe
        })

    logger.info(f"Found {len(results)} trending videos for timeframe: {timeframe}")
    return results


@router.post("/", response_model=YouTubeWatchEventResponseModel)
def create_video_event(
    request: Request,
    payload: YouTubePlayerState,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new YouTube watch event.
    - Requires headers: referer (str, required), x-session-id (str, optional)
    - Request body: YouTubePlayerState
    - Returns: The created YouTubeWatchEvent
    """
    headers = request.headers
    referer = headers.get("referer")
    session_id = headers.get('x-session-id')
    if not referer or len(referer) > 255:
        logger.warning("Missing or invalid referer header in create_video_event")
        raise HTTPException(status_code=400, detail="Missing or invalid referer header.")
    if session_id is not None and (
        not re.match(r'^[\w\-]+$', session_id) or len(session_id) > 64
    ):
        logger.warning("Missing or invalid x-session-id header in create_video_event")
        raise HTTPException(status_code=400, detail="Missing or invalid x-session-id header.")
    # Input validation
    if not payload.video_id or len(payload.video_id) < 1 or len(payload.video_id) > 32:
        raise HTTPException(status_code=400, detail="Invalid video_id: must be 1-32 characters")

    if not payload.video_title or len(payload.video_title) < 1 or len(payload.video_title) > 255:
        raise HTTPException(status_code=400, detail="Invalid video_title: must be 1-255 characters")

    if payload.current_time < 0:
        raise HTTPException(status_code=400, detail="Invalid current_time: must be non-negative")

    if not payload.video_state_label or len(payload.video_state_label) < 1 or len(payload.video_state_label) > 64:
        raise HTTPException(status_code=400, detail="Invalid video_state_label: must be 1-64 characters")

    if payload.video_state_value < -1 or payload.video_state_value > 5:
        raise HTTPException(status_code=400, detail="Invalid video_state_value: must be between -1 and 5")

    try:
        data = payload.model_dump()
        obj = YouTubeWatchEvent(**data)
    except ValidationError as e:
        logger.warning(f"Validation error in create_video_event: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid input: {e}")
    obj.referer = referer
    if current_user.id is None:
        raise HTTPException(status_code=401, detail="Invalid user")
    obj.user_id = current_user.id
    if session_id:
        watch_session_query = select(WatchSession).where(
            WatchSession.watch_session_id == session_id
        )
        watch_session_obj = db_session.exec(watch_session_query).first()
        if watch_session_obj:
            obj.watch_session_id = session_id  # type: ignore[assignment]
            watch_session_obj.last_active = get_utc_now()
            db_session.add(watch_session_obj)
    db_session.add(obj)
    try:
        db_session.commit()
    except Exception as e:
        logger.error(f"DB commit failed: {e}")
        db_session.rollback()
        raise HTTPException(status_code=500, detail="Database error")
    db_session.refresh(obj)
    logger.info(f"Created YouTubeWatchEvent: {obj.id}")
    return obj

@router.get("/top", response_model=List[VideoStat])
def get_top_video_stats(
    request: Request,
    db_session: Session = Depends(get_session),
):
    """
    Get top video statistics, aggregated by time bucket and video.
    - Query params: bucket (str), hours-ago (int), hours-until (int)
    - Returns: List of VideoStat
    """
    params = request.query_params
    bucket_param = params.get("bucket") or "1 day"
    bucket = time_bucket(bucket_param, YouTubeWatchEvent.time)
    hours_ago = parse_int_or_fallback(params.get("hours-ago"), fallback=10)
    hours_until = parse_int_or_fallback(params.get("hours-until"), fallback=0)
    start = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    end = datetime.now(timezone.utc) - timedelta(hours=hours_until)
    unique_views = func.count(func.distinct(YouTubeWatchEvent.watch_session_id)).label("unique_views")
    bucket_expr: ColumnElement[Any] = cast(ColumnElement[Any], bucket)
    video_id_expr: ColumnElement[Any] = cast(ColumnElement[Any], YouTubeWatchEvent.video_id)
    current_time_expr: ColumnElement[Any] = cast(ColumnElement[Any], YouTubeWatchEvent.current_time)
    time_expr: ColumnElement[Any] = cast(ColumnElement[Any], YouTubeWatchEvent.time)
    columns: Tuple[Any, ...] = (
        bucket_expr,
        video_id_expr,
        func.count().label("total_events"),
        func.max(current_time_expr).label("max_viewership"),
        func.avg(current_time_expr).label("avg_viewership"),
        unique_views,
    )
    query = (
        cast(Any, select(*columns))
        .where(
            time_expr > start,
            time_expr <= end,
            YouTubeWatchEvent.video_state_label != "CUED",
        )
        .group_by(
            bucket_expr,
            video_id_expr,
        )
        .order_by(
            bucket_expr.desc(),
            unique_views.desc(),
            video_id_expr,
        )
    )
    try:
        results = db_session.exec(query).fetchall()
    except SQLAlchemyError:
        raise HTTPException(status_code=400, detail='Invalid query')
    results = [
        VideoStat(
            time=x[0],
            video_id=x[1],
            total_events=x[2],
            max_viewership=x[3],
            avg_viewership=x[4],
            unique_views=x[5],
        )
        for x in results
    ]
    return results

# Update a specific event
@router.put("/{event_id}", response_model=YouTubeWatchEventResponseModel)
def update_video_event(
    event_id: int,
    payload: YouTubePlayerState,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Update an existing YouTube watch event.
    - Path param: event_id (int)
    - Request body: YouTubePlayerState
    - Returns: Updated YouTubeWatchEventResponseModel
    """
    event = db_session.get(YouTubeWatchEvent, event_id)
    if not event or event.user_id != current_user.id:
        logger.warning(f"YouTubeWatchEvent not found for update: {event_id}")
        raise HTTPException(status_code=404, detail="YouTubeWatchEvent not found")
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(event, key, value)
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    logger.info(f"Updated YouTubeWatchEvent: {event_id}")
    return event

# Delete a specific event
@router.delete("/{event_id}")
def delete_video_event(
    event_id: int,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a YouTube watch event by its integer ID.
    - Path param: event_id (int)
    - Returns: JSON with ok status and deleted_id
    """
    event = db_session.get(YouTubeWatchEvent, event_id)
    if not event or event.user_id != current_user.id:
        logger.warning(f"YouTubeWatchEvent not found for deletion: {event_id}")
        raise HTTPException(status_code=404, detail="YouTubeWatchEvent not found")
    db_session.delete(event)
    db_session.commit()
    logger.info(f"Deleted YouTubeWatchEvent: {event_id}")
    return {"ok": True, "deleted_id": event_id}




@router.get("/{event_id:int}", response_model=YouTubeWatchEventResponseModel)
def get_video_event(
    event_id: int,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve a specific YouTube watch event by its integer ID.
    - Path param: event_id (int)
    - Returns: YouTubeWatchEventResponseModel
    """
    event = db_session.get(YouTubeWatchEvent, event_id)
    if not event or event.user_id != current_user.id:
        logger.warning(f"YouTubeWatchEvent not found or forbidden: {event_id}")
        raise HTTPException(status_code=404, detail="YouTubeWatchEvent not found")
    return event



@router.get("/{video_id}", response_model=List[VideoStat])
def get_video_stats(
    video_id: str,
    request: Request,
    db_session: Session = Depends(get_session),
):
    """
    Get statistics for a specific video, aggregated by time bucket.
    - Path param: video_id (str)
    - Query params: bucket (str), hours-ago (int), hours-until (int)
    - Returns: List of VideoStat
    """
    params = request.query_params
    bucket_param = params.get("bucket") or "1 day"
    bucket = time_bucket(bucket_param, YouTubeWatchEvent.time)
    hours_ago = parse_int_or_fallback(params.get("hours-ago"), fallback=24 * 31 * 3)
    hours_until = parse_int_or_fallback(params.get("hours-until"), fallback=0)
    start = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    end = datetime.now(timezone.utc) - timedelta(hours=hours_until)
    bucket_expr: ColumnElement[Any] = cast(ColumnElement[Any], bucket)
    video_id_expr: ColumnElement[Any] = cast(ColumnElement[Any], YouTubeWatchEvent.video_id)
    current_time_expr: ColumnElement[Any] = cast(ColumnElement[Any], YouTubeWatchEvent.current_time)
    time_expr: ColumnElement[Any] = cast(ColumnElement[Any], YouTubeWatchEvent.time)
    unique_views_expr = func.count(func.distinct(YouTubeWatchEvent.watch_session_id)).label("unique_views")
    columns2: Tuple[Any, ...] = (
        bucket_expr,
        video_id_expr,
        func.count().label("total_events"),
        func.max(current_time_expr).label("max_viewership"),
        func.avg(current_time_expr).label("avg_viewership"),
        unique_views_expr,
    )
    query = (
        cast(Any, select(*columns2))
        .where(
            time_expr > start,
            time_expr <= end,
            YouTubeWatchEvent.video_state_label != "CUED",
            video_id_expr == video_id,
        )
        .group_by(
            bucket_expr,
            video_id_expr,
        )
        .order_by(
            bucket_expr.desc(),
            video_id_expr,
        )
    )
    try:
        results = db_session.exec(query).fetchall()
    except SQLAlchemyError:
        raise HTTPException(status_code=400, detail='Invalid query')
    results = [
        VideoStat(
            time=x[0],
            video_id=x[1],
            total_events=x[2],
            max_viewership=x[3],
            avg_viewership=x[4],
            unique_views=x[5],
        )
        for x in results
    ]
    return results


@router.get("/stats/{video_id}", response_model=List[VideoStat])
def get_video_stats_alias(
    video_id: str,
    request: Request,
    db_session: Session = Depends(get_session),
):
    """Public alias for per-video stats to avoid confusion with protected ID routes."""
    return get_video_stats(video_id, request, db_session)