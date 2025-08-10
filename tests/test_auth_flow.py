import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from src.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


def test_signup_login_me(client: TestClient):
    # signup
    r = client.post(
        "/api/auth/signup",
        json={"username": "u1", "email": "u1@example.com", "password": "pass"},
    )
    assert r.status_code in (200, 201)
    token = r.json()["access_token"]

    # me
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "u1"

    # login
    r = client.post("/api/auth/login", json={"username": "u1", "password": "pass"})
    assert r.status_code == 200
    assert "access_token" in r.json()


