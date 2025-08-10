# Streamlens

Streamlens is a backend service for tracking and analyzing YouTube video watch events and sessions. It is built with FastAPI, SQLModel, and TimescaleDB, and is containerized for easy deployment.

---

## Project Structure

```bash
Streamlens-back/
├── boot/
│   └── docker-run.sh              # Entrypoint script for Docker
├── compose.yaml                   # Docker Compose configuration
├── Dockerfile.web                 # Dockerfile for the web service
├── requirements.txt               # Python dependencies
├── src/
│   ├── main.py                    # FastAPI application entrypoint
│   └── api/
│       ├── __init__.py
│       ├── utils.py               # Utility functions
│       ├── db/
│       │   ├── __init__.py
│       │   ├── models.py          # User model (with roles)
│       │   └── session.py         # DB session and initialization
│       ├── auth/
│       │   ├── __init__.py
│       │   ├── models.py          # Pydantic models for auth
│       │   ├── routing.py         # Auth endpoints (signup, login, me)
│       │   └── utils.py           # Password hashing, JWT, user extraction
│       ├── video_events/
│       │   ├── __init__.py
│       │   ├── models.py          # Models for video events
│       │   └── routing.py         # API endpoints for video events
│       └── watch_sessions/
│           ├── __init__.py
│           ├── models.py          # Models for watch sessions
│           └── routing.py         # API endpoints for watch sessions
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

3. **Run database migrations, build and start the services:**

```bash
docker compose up --build migrate && docker compose up --build app
```

- The API will be available at `http://localhost:8002`
- TimescaleDB will be available at `localhost:5432`

1. **API Documentation:**

- Visit `http://localhost:8002/docs` for the interactive Swagger UI.

---

## Code Linting and Formatting

To ensure code quality and consistency, use the following tools:

- **flake8**: Lint your code for style and errors
- **black**: Auto-format your code to a consistent style

### Install (already in requirements.txt)

If you haven't already, install all dependencies:

```sh
pip install -r requirements.txt
```

Or, if using Docker, dependencies are installed automatically when you build:

```sh
docker compose up --build
```

### Usage

**Lint your code:**

```bash
flake8 src/
```

**Auto-format your code:**

```bash
black src/
```

You can also add these commands to your CI or pre-commit hooks for ongoing code quality.

---

## Database

- Uses TimescaleDB for efficient time-series storage and analytics.
- Models are defined in `src/api/video_events/models.py` and `src/api/watch_sessions/models.py`.
- Database initialization and session management in `src/api/db/session.py`.
- Migrations are managed with Alembic (`alembic/`).

### Alembic: migrations cheat sheet

- Create a new migration (autogenerate):

```bash
alembic revision --autogenerate -m "<message>"
```

- Apply migrations locally (requires `DATABASE_URL`):

```bash
alembic upgrade head
```

- Using Docker Compose:

```bash
# Run only the migration service
docker compose up --build migrate

# Run app after migrations (recommended)
docker compose up --build app

# Or run both with dependencies
docker compose up --build
```

- Downgrade (rollback) last migration:

```bash
alembic downgrade -1
```

---

## Utility Scripts

- `boot/docker-run.sh`: Entrypoint for Docker containers, runs the app with Gunicorn and Uvicorn workers.
