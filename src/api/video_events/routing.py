import logging
import re
from typing import List, Any, cast, Tuple
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request, Depends, HTTPException

from sqlalchemy import func
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
    VideoStat
)

# Set up logging
logger = logging.getLogger("video_events")

router = APIRouter()

@router.post("/", response_model=YouTubeWatchEventResponseModel)
def create_video_event(
        request: Request, 
        payload: YouTubePlayerState,
        db_session: Session = Depends(get_session),
        current_user: User = Depends(get_current_user)
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
    if session_id is not None and (not re.match(r'^[\w\-]+$', session_id) or len(session_id) > 64):
        logger.warning("Missing or invalid x-session-id header in create_video_event")
        raise HTTPException(status_code=400, detail="Missing or invalid x-session-id header.")
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
        watch_session_query = select(WatchSession).where(WatchSession.watch_session_id==session_id)
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

# List all events
@router.get("/", response_model=List[YouTubeWatchEventResponseModel])
def list_video_events(
    limit: int = 100,
    offset: int = 0,
    db_session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    List all YouTube watch events.
    - Returns: List of YouTubeWatchEventResponseModel
    """
    limit = max(1, min(1000, limit))
    offset = max(0, offset)
    query = (
        select(YouTubeWatchEvent)
        .where(YouTubeWatchEvent.user_id == current_user.id)
        .offset(offset)
        .limit(limit)
    )
    events = db_session.exec(query).all()
    logger.info(f"Listed {len(events)} video events.")
    return events

# Get a specific event
@router.get("/{event_id}", response_model=YouTubeWatchEventResponseModel)
def get_video_event(event_id: int, db_session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
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




@router.get("/top", response_model=List[VideoStat])
def get_top_video_stats(
        request: Request,
        db_session: Session = Depends(get_session)  
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
    ) for x in results]
    return results



@router.get("/{video_id}", response_model=List[VideoStat])
def get_video_stats(
        video_id: str,
        request: Request,
        db_session: Session = Depends(get_session)  
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
    ) for x in results]
    return results