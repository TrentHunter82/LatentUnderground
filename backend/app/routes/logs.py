import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
from ..database import get_db

logger = logging.getLogger("latent.logs")

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("")
async def get_logs(project_id: int, lines: int = 100, db: aiosqlite.Connection = Depends(get_db)):
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    folder = Path(dict(row)["folder_path"])
    logs_dir = folder / "logs"

    result = []
    if logs_dir.exists():
        for log_file in sorted(logs_dir.glob("*.log")):
            try:
                all_lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
                recent = all_lines[-lines:] if len(all_lines) > lines else all_lines
                result.append({
                    "agent": log_file.stem,
                    "lines": recent,
                })
            except Exception:
                logger.error("Failed to read log file %s", log_file, exc_info=True)
                continue

    return {"logs": result}


@router.get("/search")
async def search_logs(
    project_id: int,
    q: str = "",
    agent: str | None = None,
    level: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Search log files with text, agent, and level filters."""
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    folder = Path(dict(row)["folder_path"])
    logs_dir = folder / "logs"

    results = []
    if logs_dir.exists():
        for log_file in sorted(logs_dir.glob("*.log")):
            agent_name = log_file.stem
            if agent and agent_name != agent:
                continue
            try:
                all_lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
                for line in all_lines:
                    if q and q.lower() not in line.lower():
                        continue
                    if level and f"[{level.upper()}]" not in line.upper():
                        continue
                    results.append({"text": line, "agent": agent_name})
            except Exception:
                logger.error("Failed to read log file %s", log_file, exc_info=True)
                continue

    # Apply pagination
    paginated = results[offset:offset + limit]
    return {"results": paginated, "total": len(results)}
