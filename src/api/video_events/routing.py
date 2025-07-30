import logging
import re
from typing import List
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request, Depends, HTTPException

from sqlalchemy import func
from sqlmodel import Session, select
from pydantic import ValidationError

from timescaledb.hyperfunctions import time_bucket
from timescaledb.utils import get_utc_now

from api.utils import parse_int_or_fallback
from api.db.session import get_session
from api.watch_sessions.models import WatchSession

from .models import (
    YouTubePlayerState, 
    YouTubeWatchEvent, 
    YouTubeWatchEventResponseModel,
    VideoStat
)

# Set up logging
logger = logging.getLogger("video_events")
logging.basicConfig(level=logging.INFO)

router = APIRouter()

@router.post("/", response_model=YouTubeWatchEventResponseModel)
def create_video_event(
        request: Request, 
        payload: YouTubePlayerState,
        db_session: Session = Depends(get_session)  
    ):
    """Create a new YouTube watch event."""
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
    if session_id:
        watch_session_query = select(WatchSession).where(WatchSession.watch_session_id==session_id)
        watch_session_obj = db_session.exec(watch_session_query).first()
        if watch_session_obj:
            obj.watch_session_id = session_id
            watch_session_obj.last_active = get_utc_now()
            db_session.add(watch_session_obj)
    db_session.add(obj)
    db_session.commit()
    db_session.refresh(obj)
    logger.info(f"Created YouTubeWatchEvent: {obj.id}")
    return obj

# List all events
@router.get("/", response_model=List[YouTubeWatchEventResponseModel])
def list_video_events(db_session: Session = Depends(get_session)):
    """List all YouTube watch events."""
    events = db_session.exec(select(YouTubeWatchEvent)).all()
    logger.info(f"Listed {len(events)} video events.")
    return events

# Get a specific event
@router.get("/{event_id}", response_model=YouTubeWatchEventResponseModel)
def get_video_event(event_id: int, db_session: Session = Depends(get_session)):
    """Retrieve a specific YouTube watch event by its ID."""
    event = db_session.get(YouTubeWatchEvent, event_id)
    if not event:
        logger.warning(f"YouTubeWatchEvent not found: {event_id}")
        raise HTTPException(status_code=404, detail="YouTubeWatchEvent not found")
    return event

# Update a specific event
@router.put("/{event_id}", response_model=YouTubeWatchEventResponseModel)
def update_video_event(event_id: int, payload: YouTubePlayerState, db_session: Session = Depends(get_session)):
    """Update an existing YouTube watch event."""
    event = db_session.get(YouTubeWatchEvent, event_id)
    if not event:
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
def delete_video_event(event_id: int, db_session: Session = Depends(get_session)):
    """Delete a YouTube watch event by its ID."""
    event = db_session.get(YouTubeWatchEvent, event_id)
    if not event:
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
    params = request.query_params
    bucket_param = params.get("bucket") or "1 day"
    bucket = time_bucket(bucket_param, YouTubeWatchEvent.time)
    hours_ago = parse_int_or_fallback(params.get("hours-ago"), fallback=10)
    hours_until = parse_int_or_fallback(params.get("hours-until"), fallback=0)
    start = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    end = datetime.now(timezone.utc) - timedelta(hours=hours_until)
    unique_views = func.count(func.distinct(YouTubeWatchEvent.watch_session_id)).label("unique_views")
    query = (
        select(
            bucket, # 0
            YouTubeWatchEvent.video_id, # 1
            func.count().label("total_events"), # 2
            func.max(YouTubeWatchEvent.current_time).label("max_viewership"), # in seconds
            func.avg(YouTubeWatchEvent.current_time).label("avg_viewership"), # in seconds
            unique_views
        )
        .where(
            YouTubeWatchEvent.time > start,
            YouTubeWatchEvent.time <= end,
            YouTubeWatchEvent.video_state_label != "CUED",
        )
        .group_by(
            bucket,
            YouTubeWatchEvent.video_id
        )
        .order_by(
            bucket.desc(),
            unique_views.desc(),
            YouTubeWatchEvent.video_id
        )

    )
    try:
        results = db_session.exec(query).fetchall()
    except:
        raise HTTPException(
            status_code=400,
            detail='Invalid query'
        )
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
        video_id:str,
        request: Request,
        db_session: Session = Depends(get_session)  
    ):
    params = request.query_params
    bucket_param = params.get("bucket") or "1 day"
    bucket = time_bucket(bucket_param, YouTubeWatchEvent.time)
    hours_ago = parse_int_or_fallback(params.get("hours-ago"), fallback=24 * 31 * 3)
    hours_until = parse_int_or_fallback(params.get("hours-until"), fallback=0)
    start = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    end = datetime.now(timezone.utc) - timedelta(hours=hours_until)
    query = (
        select(
            bucket, # 0
            YouTubeWatchEvent.video_id, # 1
            func.count().label("total_events"), # 2
            func.max(YouTubeWatchEvent.current_time).label("max_viewership"), # in seconds
            func.avg(YouTubeWatchEvent.current_time).label("avg_viewership"), # in seconds
            func.count(func.distinct(YouTubeWatchEvent.watch_session_id)).label("unique_views")
        )
        .where(
            YouTubeWatchEvent.time > start,
            YouTubeWatchEvent.time <= end,
            YouTubeWatchEvent.video_state_label != "CUED",
            YouTubeWatchEvent.video_id == video_id
        )
        .group_by(
            bucket,
            YouTubeWatchEvent.video_id
        )
        .order_by(
            bucket.desc(),
            YouTubeWatchEvent.video_id
        )

    )
    try:
        results = db_session.exec(query).fetchall()
    except:
        raise HTTPException(
            status_code=400,
            detail='Invalid query'
        )
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