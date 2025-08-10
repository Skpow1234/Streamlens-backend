import timescaledb
from timescaledb import create_engine
from sqlmodel import SQLModel, Session
from api.config import settings

DATABASE_URL = settings.DATABASE_URL
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be set in the environment")

engine = create_engine(DATABASE_URL, timezone="UTC")

def init_db():
    SQLModel.metadata.create_all(engine)
    timescaledb.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session