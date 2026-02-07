"""Application configuration loaded from environment variables.

Reads from a .env file in the backend directory if present, then
overrides with actual environment variables. No extra dependencies needed.
"""

import os
from pathlib import Path

_BACKEND_DIR = Path(__file__).parent.parent
_PROJECT_ROOT = _BACKEND_DIR.parent


def _load_dotenv():
    """Load .env file from backend directory if it exists."""
    env_file = _BACKEND_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        # Don't override existing env vars
        if key not in os.environ:
            os.environ[key] = value


_load_dotenv()


# --- Settings ---

HOST: str = os.environ.get("LU_HOST", "127.0.0.1")
PORT: int = int(os.environ.get("LU_PORT", "8000"))
DB_PATH: Path = Path(os.environ.get("LU_DB_PATH", str(_BACKEND_DIR / "latent.db")))
LOG_LEVEL: str = os.environ.get("LU_LOG_LEVEL", "info")

# Comma-separated list of allowed origins
_default_origins = (
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:8000,http://127.0.0.1:8000"
)
CORS_ORIGINS: list[str] = [
    o.strip() for o in os.environ.get("LU_CORS_ORIGINS", _default_origins).split(",") if o.strip()
]

# Frontend dist path
FRONTEND_DIST: Path = Path(os.environ.get(
    "LU_FRONTEND_DIST", str(_PROJECT_ROOT / "frontend" / "dist")
))
