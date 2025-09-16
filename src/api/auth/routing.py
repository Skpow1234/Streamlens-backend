import re
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session, select
from api.db.session import get_session
from .models import UserCreate, UserLogin
from api.db.models import User
from .utils import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)

router = APIRouter(tags=["auth"])


@router.post("/signup")
def signup(user: UserCreate, db: Session = Depends(get_session)):
    # Input validation
    if not user.username or len(user.username.strip()) < 3 or len(user.username) > 50:
        raise HTTPException(status_code=400, detail="Username must be 3-50 characters long")

    if not user.email or not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', user.email):
        raise HTTPException(status_code=400, detail="Invalid email format")

    if not user.password or len(user.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")

    # Check for password complexity
    if not re.search(r'[A-Z]', user.password):
        raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter")
    if not re.search(r'[a-z]', user.password):
        raise HTTPException(status_code=400, detail="Password must contain at least one lowercase letter")
    if not re.search(r'\d', user.password):
        raise HTTPException(status_code=400, detail="Password must contain at least one number")

    existing = db.exec(
        select(User).where(
            (User.username == user.username.strip().lower()) | (User.email == user.email.strip().lower())
        )
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already registered")

    hashed = hash_password(user.password)
    db_user = User(username=user.username.strip(), email=user.email.strip().lower(), hashed_password=hashed)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    token = create_access_token({"sub": db_user.id})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/login")
def login(user: UserLogin, db: Session = Depends(get_session)):
    # Input validation
    if not user.username or len(user.username.strip()) < 3 or len(user.username) > 50:
        raise HTTPException(status_code=400, detail="Invalid username format")

    if not user.password or len(user.password) < 8:
        raise HTTPException(status_code=400, detail="Invalid password format")

    db_user = db.exec(select(User).where(User.username == user.username.strip())).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": db_user.id})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
    }
