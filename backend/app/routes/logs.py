import logging
import re
from datetime import datetime
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


_TIMESTAMP_RE = re.compile(r"^[\[(\s]*(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})")


def _parse_log_timestamp(line: str) -> datetime | None:
    """Extract a timestamp from the beginning of a log line."""
    m = _TIMESTAMP_RE.match(line)
    if not m:
        return None
    try:
        return datetime.fromisoformat(m.group(1))
    except ValueError:
        return None


def _parse_date_param(value: str) -> datetime:
    """Parse a date/datetime string from query params. Raises ValueError on bad input."""
    # Accept YYYY-MM-DD (treat as start of day) or full ISO datetime
    value = value.strip()
    if len(value) == 10:  # YYYY-MM-DD
        return datetime.fromisoformat(value + "T00:00:00")
    return datetime.fromisoformat(value)


@router.get("/search")
async def search_logs(
    project_id: int,
    q: str = "",
    agent: str | None = None,
    level: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Search log files with text, agent, level, and date range filters."""
    limit = min(limit, 1000)
    offset = max(offset, 0)
    row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    # Parse date range params
    parsed_from = None
    parsed_to = None
    if from_date:
        try:
            parsed_from = _parse_date_param(from_date)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid from_date: {from_date}")
    if to_date:
        try:
            parsed_to = _parse_date_param(to_date)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid to_date: {to_date}")

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
                    # Date range filter: skip lines with timestamps outside range
                    if parsed_from or parsed_to:
                        ts = _parse_log_timestamp(line)
                        if ts:
                            if parsed_from and ts < parsed_from:
                                continue
                            if parsed_to and ts > parsed_to:
                                continue
                        # Lines without parseable timestamps are included
                    results.append({"text": line, "agent": agent_name})
            except Exception:
                logger.error("Failed to read log file %s", log_file, exc_info=True)
                continue

    # Apply pagination
    paginated = results[offset:offset + limit]
    return {"results": paginated, "total": len(results)}
