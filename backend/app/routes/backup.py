"""Database backup endpoint - exports SQLite database as a download."""

import asyncio
import sqlite3
from datetime import datetime
from io import BytesIO

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .. import database

router = APIRouter(prefix="/api", tags=["backup"])


def _create_backup() -> BytesIO:
    """Create SQLite backup in a thread-safe, blocking context."""
    buf = BytesIO()
    source = sqlite3.connect(str(database.DB_PATH))
    try:
        dest = sqlite3.connect(":memory:")
        try:
            source.backup(dest)
            for line in dest.iterdump():
                buf.write((line + "\n").encode("utf-8"))
        finally:
            dest.close()
    finally:
        source.close()
    buf.seek(0)
    return buf


@router.get("/backup")
async def backup_database():
    """Export the SQLite database as a downloadable file.

    Uses SQLite's backup API for a consistent snapshot even during writes.
    """
    buf = await asyncio.to_thread(_create_backup)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"latent_underground_backup_{timestamp}.sql"

    return StreamingResponse(
        buf,
        media_type="application/sql",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
