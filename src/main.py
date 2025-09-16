import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from api.config import settings
from prometheus_fastapi_instrumentator import Instrumentator

from api.db.session import init_db
from api.video_events.routing import router as video_events_router
from api.watch_sessions.routing import router as watch_sessions_router
from api.auth.routing import router as auth_router
from api.social.routing import router as social_router
from api.playlists.routing import router as playlists_router

# Logging
_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(
    level=_level,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
)
for _logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logging.getLogger(_logger_name).setLevel(_level)

# CORS
# Use env-driven origins with safe local defaults from settings
origins = [origin for origin in settings.CORS_ORIGINS if origin]

# In production, be more restrictive with CORS
if not origins or origins == ["http://localhost:3000", "http://localhost:5173", "http://localhost:8000"]:
    # Development defaults - allow common dev ports
    origins = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ]
else:
    # Production - only allow explicitly configured origins
    origins = [origin for origin in settings.CORS_ORIGINS if origin]

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

# Rate limiting storage
rate_limit_store = defaultdict(list)

def rate_limit_middleware(request: Request, call_next):
    """Simple rate limiting middleware."""
    client_ip = request.client.host
    current_time = time.time()

    # Clean old requests (older than 60 seconds)
    rate_limit_store[client_ip] = [
        timestamp for timestamp in rate_limit_store[client_ip]
        if current_time - timestamp < 60
    ]

    # Check rate limit (100 requests per minute)
    if len(rate_limit_store[client_ip]) >= 100:
        raise HTTPException(status_code=429, detail="Too many requests")

    # Add current request timestamp
    rate_limit_store[client_ip].append(current_time)

    response = call_next(request)
    return response

app = FastAPI(
    title="Streamlens API",
    description=(
        "Streamlens is a backend service for tracking and analyzing YouTube video watch events and sessions. "
        "It is built with FastAPI, SQLModel, and TimescaleDB, and is containerized for easy deployment.\n\n"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Add rate limiting middleware
app.middleware("http")(rate_limit_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Prometheus metrics
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

app.include_router(video_events_router, prefix='/api/video-events')
app.include_router(watch_sessions_router, prefix='/api/watch-sessions')
app.include_router(auth_router, prefix='/api/auth')
app.include_router(social_router, prefix='/api/social')
app.include_router(playlists_router, prefix='/api/playlists')

@app.get("/")
def read_root():
    return RedirectResponse(url=settings.LOGIN_URL, status_code=302)

@app.get("/healthChecker")
def read_api_health():
    return {"status": "ok"}