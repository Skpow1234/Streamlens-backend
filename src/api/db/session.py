import os
import timescaledb
from timescaledb import create_engine
from sqlmodel import SQLModel, Session
from api.config import settings

DATABASE_URL = settings.DATABASE_URL
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be set in the environment")

engine = create_engine(DATABASE_URL, timezone="UTC")

def init_db():
    """Initialize database schema in local/dev when explicitly enabled.

    Prefer running Alembic migrations in non-dev environments. To enable
    automatic table creation for local development, set DB_AUTO_CREATE=1.
    """
    if os.environ.get("DB_AUTO_CREATE", "0") in {"1", "true", "True"}:
        SQLModel.metadata.create_all(engine)
        timescaledb.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
