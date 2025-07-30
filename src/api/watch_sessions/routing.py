import logging
from fastapi import APIRouter, Request, Depends, HTTPException
from typing import List
from sqlmodel import Session, select

from api.db.session import get_session
from .models import WatchSession, WatchSessionCreate

# Set up logging
logger = logging.getLogger("watch_sessions")
logging.basicConfig(level=logging.INFO)

router = APIRouter()

@router.post("/", response_model=WatchSession)
def create_watch_session(
        request: Request, 
        payload: WatchSessionCreate,
        db_session: Session = Depends(get_session)  
    ):
    """Create a new watch session."""
    headers = request.headers
    referer = headers.get("referer")
    data = payload.model_dump()
    obj = WatchSession(**data)
    obj.referer = referer
    db_session.add(obj)
    db_session.commit()
    db_session.refresh(obj)
    logger.info(f"Created WatchSession: {obj.watch_session_id}")
    return obj

# List all sessions
@router.get("/", response_model=List[WatchSession])
def list_watch_sessions(db_session: Session = Depends(get_session)):
    """List all watch sessions."""
    sessions = db_session.exec(select(WatchSession)).all()
    logger.info(f"Listed {len(sessions)} watch sessions.")
    return sessions

# Get a specific session
@router.get("/{watch_session_id}", response_model=WatchSession)
def get_watch_session(watch_session_id: str, db_session: Session = Depends(get_session)):
    """Retrieve a specific watch session by its ID."""
    session = db_session.exec(select(WatchSession).where(WatchSession.watch_session_id == watch_session_id)).first()
    if not session:
        logger.warning(f"WatchSession not found: {watch_session_id}")
        raise HTTPException(status_code=404, detail="WatchSession not found")
    return session

# Update a session
@router.put("/{watch_session_id}", response_model=WatchSession)
def update_watch_session(watch_session_id: str, payload: WatchSessionCreate, db_session: Session = Depends(get_session)):
    """Update an existing watch session."""
    session = db_session.exec(select(WatchSession).where(WatchSession.watch_session_id == watch_session_id)).first()
    if not session:
        logger.warning(f"WatchSession not found for update: {watch_session_id}")
        raise HTTPException(status_code=404, detail="WatchSession not found")
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(session, key, value)
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    logger.info(f"Updated WatchSession: {watch_session_id}")
    return session

# Delete a session
@router.delete("/{watch_session_id}")
def delete_watch_session(watch_session_id: str, db_session: Session = Depends(get_session)):
    """Delete a watch session by its ID."""
    session = db_session.exec(select(WatchSession).where(WatchSession.watch_session_id == watch_session_id)).first()
    if not session:
        logger.warning(f"WatchSession not found for deletion: {watch_session_id}")
        raise HTTPException(status_code=404, detail="WatchSession not found")
    db_session.delete(session)
    db_session.commit()
    logger.info(f"Deleted WatchSession: {watch_session_id}")
    return {"ok": True, "deleted_id": watch_session_id}