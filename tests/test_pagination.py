import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from src.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


def _signup(client: TestClient):
    r = client.post(
        "/api/auth/signup",
        json={"username": "u5", "email": "u5@example.com", "password": "pass"},
    )
    return r.json()["access_token"]


def test_list_video_events_pagination(client: TestClient):
    token = _signup(client)
    headers = {"Authorization": f"Bearer {token}", "referer": "http://localhost"}
    payload = {
        "is_ready": True,
        "video_id": "abc",
        "video_title": "t",
        "current_time": 0,
        "video_state_label": "PLAYING",
        "video_state_value": 1,
    }
    for _ in range(3):
        client.post("/api/video-events/", headers=headers, json=payload)

    r = client.get("/api/video-events/?limit=2&offset=0", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert len(r.json()) == 2
    r = client.get("/api/video-events/?limit=2&offset=2", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert len(r.json()) >= 1


