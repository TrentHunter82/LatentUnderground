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

# API key for authentication (empty = auth disabled)
API_KEY: str = os.environ.get("LU_API_KEY", "")

# Rate limiting: max requests per minute per client per endpoint (0 = disabled)
# Write RPM applies to POST/PUT/PATCH/DELETE, Read RPM applies to GET
RATE_LIMIT_RPM: int = int(os.environ.get("LU_RATE_LIMIT_RPM", "30"))
RATE_LIMIT_READ_RPM: int = int(os.environ.get("LU_RATE_LIMIT_READ_RPM", "120"))

# Structured logging: "json" for JSON lines, "text" for human-readable (default)
LOG_FORMAT: str = os.environ.get("LU_LOG_FORMAT", "text")

# Log retention: auto-delete project log files older than N days on startup (0 = disabled)
LOG_RETENTION_DAYS: int = int(os.environ.get("LU_LOG_RETENTION_DAYS", "0"))

# Automatic backups: interval in hours (0 = disabled), max backups to keep
BACKUP_INTERVAL_HOURS: int = int(os.environ.get("LU_BACKUP_INTERVAL_HOURS", "0"))
BACKUP_KEEP: int = int(os.environ.get("LU_BACKUP_KEEP", "5"))

# Request logging: log all HTTP requests with method, path, status, duration (default disabled)
REQUEST_LOG: bool = os.environ.get("LU_REQUEST_LOG", "").lower() in ("1", "true", "yes")
