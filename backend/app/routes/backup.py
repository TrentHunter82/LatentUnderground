"""Database backup endpoint - exports SQLite database as a download."""

import sqlite3
from datetime import datetime
from io import BytesIO

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .. import database

router = APIRouter(prefix="/api", tags=["backup"])


@router.get("/backup")
async def backup_database():
    """Export the SQLite database as a downloadable file.

    Uses SQLite's backup API for a consistent snapshot even during writes.
    """
    buf = BytesIO()

    # Use SQLite backup API for a consistent copy
    source = sqlite3.connect(str(database.DB_PATH))
    dest = sqlite3.connect(":memory:")
    source.backup(dest)
    source.close()

    # Dump the in-memory copy to bytes
    for line in dest.iterdump():
        buf.write((line + "\n").encode("utf-8"))
    dest.close()

    buf.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"latent_underground_backup_{timestamp}.sql"

    return StreamingResponse(
        buf,
        media_type="application/sql",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
