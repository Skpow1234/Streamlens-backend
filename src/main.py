import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from api.config import settings
from prometheus_fastapi_instrumentator import Instrumentator

from api.db.session import init_db
from api.video_events.routing import router as video_events_router
from api.watch_sessions.routing import router as watch_sessions_router
from api.auth.routing import router as auth_router

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

app.include_router(video_events_router, prefix='/api/video-events')
app.include_router(watch_sessions_router, prefix='/api/watch-sessions')
app.include_router(auth_router)

@app.get("/")
def read_root():
    return RedirectResponse(url=settings.LOGIN_URL, status_code=302)

@app.get("/healthChecker")
def read_api_health():
    return {"status": "ok"}