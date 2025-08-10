import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from src.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


def _signup(client: TestClient, username: str, email: str):
    r = client.post(
        "/api/auth/signup",
        json={"username": username, "email": email, "password": "pass"},
    )
    assert r.status_code in (200, 201)
    return r.json()["access_token"]


def test_cannot_modify_other_users_event(client: TestClient):
    token1 = _signup(client, "u3", "u3@example.com")
    token2 = _signup(client, "u4", "u4@example.com")

    headers1 = {"Authorization": f"Bearer {token1}", "referer": "http://localhost"}
    payload = {
        "is_ready": True,
        "video_id": "abc",
        "video_title": "t",
        "current_time": 0,
        "video_state_label": "PLAYING",
        "video_state_value": 1,
    }
    r = client.post("/api/video-events/", headers=headers1, json=payload)
    assert r.status_code == 200
    event_id = r.json()["id"]

    headers2 = {"Authorization": f"Bearer {token2}"}
    r = client.delete(f"/api/video-events/{event_id}", headers=headers2)
    assert r.status_code == 404


