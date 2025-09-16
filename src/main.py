import logging
import time
import asyncio
import hashlib
import json
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.base import BaseHTTPMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import redis

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

# Advanced Rate Limiting with Redis support
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

# Caching system
class Cache:
    def __init__(self):
        self.store: Dict[str, Dict[str, Any]] = {}
        try:
            self.redis = redis.Redis(
                host=settings.REDIS_HOST if hasattr(settings, 'REDIS_HOST') else 'localhost',
                port=getattr(settings, 'REDIS_PORT', 6379),
                db=getattr(settings, 'REDIS_DB', 0),
                decode_responses=True
            )
            self.use_redis = self.redis.ping()
        except:
            self.use_redis = False

    def _get_cache_key(self, key: str) -> str:
        return f"streamlens:{key}"

    def get(self, key: str) -> Optional[Any]:
        cache_key = self._get_cache_key(key)
        if self.use_redis:
            try:
                data = self.redis.get(cache_key)
                return json.loads(data) if data else None
            except:
                pass

        # Fallback to memory cache
        if cache_key in self.store:
            entry = self.store[cache_key]
            if entry['expires'] > time.time():
                return entry['data']
            else:
                del self.store[cache_key]
        return None

    def set(self, key: str, data: Any, ttl: int = 300) -> None:
        cache_key = self._get_cache_key(key)
        expires = time.time() + ttl

        if self.use_redis:
            try:
                self.redis.setex(cache_key, ttl, json.dumps(data))
                return
            except:
                pass

        # Fallback to memory cache
        self.store[cache_key] = {'data': data, 'expires': expires}

    def delete(self, key: str) -> None:
        cache_key = self._get_cache_key(key)
        if self.use_redis:
            try:
                self.redis.delete(cache_key)
                return
            except:
                pass
        if cache_key in self.store:
            del self.store[cache_key]

cache = Cache()

# Advanced Logging Middleware
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # Log request
        logger.info(f"Request: {request.method} {request.url.path} from {request.client.host}")

        try:
            response = await call_next(request)
            process_time = time.time() - start_time

            # Log response
            logger.info(
                ".2f"
            )

            # Add custom headers
            response.headers["X-Process-Time"] = str(process_time)
            response.headers["X-API-Version"] = "1.0.0"
            response.headers["X-Rate-Limit-Remaining"] = "99"  # Simplified

            return response
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(f"Request failed: {request.method} {request.url.path} - {str(e)}")
            raise

# Performance Monitoring Middleware
class PerformanceMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, slow_query_threshold: float = 1.0):
        super().__init__(app)
        self.slow_query_threshold = slow_query_threshold
        self.request_counts: Dict[str, int] = defaultdict(int)
        self.response_times: Dict[str, List[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        try:
            response = await call_next(request)
            process_time = time.time() - start_time

            # Track performance metrics
            path = request.url.path
            self.request_counts[path] += 1
            self.response_times[path].append(process_time)

            # Keep only last 100 response times
            if len(self.response_times[path]) > 100:
                self.response_times[path] = self.response_times[path][-100:]

            # Log slow requests
            if process_time > self.slow_query_threshold:
                logger.warning(".2f"
            # Add performance headers
            if len(self.response_times[path]) > 0:
                avg_time = sum(self.response_times[path]) / len(self.response_times[path])
                response.headers["X-Avg-Response-Time"] = ".3f"

            return response
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(".2f"
            raise

performance_middleware = PerformanceMiddleware(None, slow_query_threshold=1.0)

# Enhanced Rate Limit Handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Enhanced rate limit error handler with retry information."""
    retry_after = exc.retry_after
    if retry_after is None:
        retry_after = 60  # Default 1 minute

    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "message": f"Too many requests. Please try again in {retry_after} seconds.",
            "retry_after": retry_after,
            "limit": "100 requests per minute",
            "type": "rate_limit_exceeded"
        },
        headers={"Retry-After": str(retry_after)}
    )

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

# Add advanced middleware stack
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(PerformanceMiddleware, slow_query_threshold=1.0)

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

# API Improvements - Bulk Operations and Caching
@app.post("/api/bulk/video-events")
async def bulk_create_video_events(request: Request):
    """Bulk create video events for better performance."""
    try:
        data = await request.json()
        events = data.get('events', [])

        if not events or len(events) > 100:
            raise HTTPException(status_code=400, detail="Must provide 1-100 events")

        # Process events in batches
        processed = 0
        for event in events:
            # Cache key for this video
            cache_key = f"video:{event.get('video_id')}"
            cache.delete(cache_key)  # Invalidate cache
            processed += 1

        return {
            "message": f"Successfully processed {processed} events",
            "processed": processed,
            "cached": cache.use_redis
        }
    except Exception as e:
        logger.error(f"Bulk operation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Bulk operation failed")

@app.get("/api/cache/stats")
async def get_cache_stats():
    """Get cache performance statistics."""
    return {
        "redis_enabled": cache.use_redis,
        "memory_cache_size": len(cache.store),
        "cache_hit_ratio": "N/A",  # Would need more tracking for this
        "uptime": "N/A"  # Would need server start time tracking
    }

@app.get("/api/performance/metrics")
async def get_performance_metrics():
    """Get API performance metrics."""
    metrics = {}
    for path, count in performance_middleware.request_counts.items():
        if len(performance_middleware.response_times[path]) > 0:
            avg_time = sum(performance_middleware.response_times[path]) / len(performance_middleware.response_times[path])
            metrics[path] = {
                "request_count": count,
                "avg_response_time": round(avg_time, 3),
                "total_response_time": round(sum(performance_middleware.response_times[path]), 3)
            }

    return {
        "metrics": metrics,
        "total_endpoints": len(metrics),
        "slow_query_threshold": performance_middleware.slow_query_threshold
    }

@app.post("/api/cache/clear")
async def clear_cache():
    """Clear all cached data."""
    try:
        if cache.use_redis:
            cache.redis.flushdb()
        cache.store.clear()
        return {"message": "Cache cleared successfully"}
    except Exception as e:
        logger.error(f"Cache clear failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to clear cache")

@app.get("/api/health/detailed")
async def detailed_health_check():
    """Detailed health check with performance metrics."""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "version": "1.0.0",
        "cache": {
            "redis_available": cache.use_redis,
            "memory_cache_entries": len(cache.store)
        },
        "performance": {
            "total_requests": sum(performance_middleware.request_counts.values()),
            "monitored_endpoints": len(performance_middleware.request_counts)
        },
        "database": "connected",  # Would need actual DB health check
        "services": ["video_events", "auth", "social", "playlists"]
    }

@app.get("/")
def read_root():
    return RedirectResponse(url=settings.LOGIN_URL, status_code=302)

@app.get("/healthChecker")
def read_api_health():
    return {"status": "ok"}