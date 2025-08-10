import os
from typing import List


def _split_env_list(value: str) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item and item.strip()]


class Settings:
    """Centralized application settings loaded from environment variables.

    This keeps security-sensitive values (like JWT secrets) and cross-cutting
    config (like CORS) in one place.
    """

    # JWT / Auth
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    JWT_ISSUER: str | None = os.getenv("JWT_ISSUER") or None
    JWT_AUDIENCE: str | None = os.getenv("JWT_AUDIENCE") or None

    # CORS
    # Comma-separated list, e.g. "http://localhost:3000,http://localhost:5173"
    _cors_origins_env: str = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173,http://localhost:8000",
    )
    CORS_ORIGINS: List[str] = _split_env_list(_cors_origins_env)


settings = Settings()


