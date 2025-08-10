import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from src.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


def test_video_event_validation_requires_title_and_id(client: TestClient):
    # First create a user and get token
    r = client.post(
        "/api/auth/signup",
        json={"username": "u2", "email": "u2@example.com", "password": "pass"},
    )
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "referer": "http://localhost"}

    # Missing title
    r = client.post(
        "/api/video-events/",
        headers=headers,
        json={
            "is_ready": True,
            "video_id": "abc",
            "current_time": 0,
            "video_state_label": "PLAYING",
            "video_state_value": 1,
        },
    )
    assert r.status_code == 422 or r.status_code == 400


