# SteamLens

SteamLens is a backend service for tracking and analyzing YouTube video watch events and sessions. It is built with FastAPI, SQLModel, and TimescaleDB, and is containerized for easy deployment.

---

## Project Structure

```bash
├── boot/
│   └── docker-run.sh         # Entrypoint script for Docker
├── compose.yaml              # Docker Compose configuration
├── Dockerfile.web            # Dockerfile for the web service
├── requirements.txt          # Python dependencies
├── src/
│   ├── main.py               # FastAPI application entrypoint
│   └── api/
│       ├── __init__.py
│       ├── utils.py          # Utility functions
│       ├── db/
│       │   ├── __init__.py
│       │   └── session.py    # DB session and initialization
│       ├── video_events/
│       │   ├── __init__.py
│       │   ├── models.py     # Models for video events
│       │   └── routing.py    # API endpoints for video events
│       └── watch_sessions/
│           ├── __init__.py
│           ├── models.py     # Models for watch sessions
│           └── routing.py    # API endpoints for watch sessions
```

---

## Features

- **Track YouTube video events**: Store and analyze watch events with TimescaleDB.
- **Session management**: Create and manage watch sessions.
- **REST API**: Endpoints for creating events, sessions, and retrieving statistics.
- **Dockerized**: Easy to run locally or deploy in production.

---

## API Overview

- `/api/video-events/` — Create and query YouTube video events.
- `/api/video-events/top` — Get top video stats (aggregated).
- `/api/video-events/{video_id}` — Get stats for a specific video.
- `/api/watch-sessions/` — Create a new watch session.
- `/` — Health check and root endpoint.

---

## Requirements

- Python 3.8+
- Docker (for containerized setup)
- TimescaleDB (or PostgreSQL with TimescaleDB extension)

Python dependencies (see `requirements.txt`):

- fastapi
- uvicorn
- gunicorn
- sqlmodel
- pydantic
- sqlalchemy
- timescaledb
- requests
- python-decouple
- psycopg[binary]

---

## Running with Docker Compose

1. **Clone the repository** and navigate to the project directory.

2. **Create a `.env.compose` file** with your environment variables (see `compose.yaml` for required variables).

3. **Build and start the services:**

   ```sh
   docker compose up --build
   ```

   - The API will be available at `http://localhost:8002`
   - TimescaleDB will be available at `localhost:5432`

4. **API Documentation:**
   - Visit `http://localhost:8002/docs` for the interactive Swagger UI.

---

## Running Locally (without Docker)

1. **Install Python dependencies:**

   ```sh
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Set environment variables:**
   - `DATABASE_URL` (e.g., `postgresql+psycopg://user:password@localhost:5432/timescaledb`)
   - `HOST`, `HOST_SCHEME`, `HOST_PORT` (for CORS)

3. **Start the database** (TimescaleDB/PostgreSQL).

4. **Run the API:**

   ```sh
   uvicorn main:app --host 0.0.0.0 --port 8002 --reload
   ```

---

## Database

- Uses TimescaleDB for efficient time-series storage and analytics.
- Models are defined in `src/api/video_events/models.py` and `src/api/watch_sessions/models.py`.
- Database initialization and session management in `src/api/db/session.py`.

---

## Utility Scripts

- `boot/docker-run.sh`: Entrypoint for Docker containers, runs the app with Gunicorn and Uvicorn workers.
