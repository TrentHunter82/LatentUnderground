import logging
import time
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import aiosqlite
from ..database import get_db

logger = logging.getLogger("latent.files")

router = APIRouter(prefix="/api/files", tags=["files"])

# Rate limiting: track last write time per (project_id, path)
_last_write: dict[tuple[int, str], float] = {}
_WRITE_COOLDOWN = 2.0  # seconds between writes to same file

MAX_CONTENT_SIZE = 1_000_000  # 1MB limit for file writes

# Only allow access to these paths relative to project folder
ALLOWED_PATHS = {
    "tasks/TASKS.md",
    "tasks/lessons.md",
    "tasks/todo.md",
    "AGENTS.md",
    "progress.txt",
}


def _validate_path(rel_path: str) -> str:
    """Validate and normalize the requested path against the allowlist."""
    normalized = rel_path.replace("\\", "/").strip("/")
    if normalized not in ALLOWED_PATHS:
        raise HTTPException(status_code=403, detail=f"Access denied: {normalized}")
    return normalized


class FileWriteRequest(BaseModel):
    content: str
    project_id: int


@router.get("/{path:path}")
async def read_file(path: str, project_id: int, db: aiosqlite.Connection = Depends(get_db)):
    normalized = _validate_path(path)

    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    file_path = Path(dict(row)["folder_path"]) / normalized
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return {"path": normalized, "content": file_path.read_text(encoding="utf-8")}


@router.put("/{path:path}")
async def write_file(path: str, body: FileWriteRequest, db: aiosqlite.Connection = Depends(get_db)):
    normalized = _validate_path(path)

    # Content size limit
    if len(body.content) > MAX_CONTENT_SIZE:
        raise HTTPException(status_code=413, detail=f"Content too large ({len(body.content)} bytes, max {MAX_CONTENT_SIZE})")

    # Rate limit: prevent rapid-fire saves to the same file
    key = (body.project_id, normalized)
    now = time.monotonic()
    last = _last_write.get(key, 0)
    if now - last < _WRITE_COOLDOWN:
        logger.warning("Rate limit hit for file %s (project %d)", normalized, body.project_id)
        raise HTTPException(status_code=429, detail="Too many writes, please wait a moment")

    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (body.project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    file_path = Path(dict(row)["folder_path"]) / normalized
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body.content, encoding="utf-8")
    _last_write[key] = now

    logger.info("File written: %s (project %d, %d bytes)", normalized, body.project_id, len(body.content))
    return {"path": normalized, "status": "written"}
