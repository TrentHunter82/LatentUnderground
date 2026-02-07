from fastapi import APIRouter, HTTPException
import aiosqlite

from ..database import DB_PATH
from ..routes.websocket import manager
from ..services.watcher import FolderWatcher

router = APIRouter(tags=["watcher"])

# Active watchers keyed by project folder
_watchers: dict[str, FolderWatcher] = {}


async def cleanup_watchers():
    """Stop all active watchers. Called during app shutdown."""
    for w in _watchers.values():
        await w.stop()
    _watchers.clear()


@router.post("/api/watch/{project_id}")
async def start_watching(project_id: int):
    """Start filesystem watcher for a project folder."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Project not found")
        folder = dict(row)["folder_path"]

    if folder in _watchers:
        return {"status": "already_watching", "folder": folder}

    watcher = FolderWatcher(folder, manager.broadcast)
    _watchers[folder] = watcher
    await watcher.start()

    return {"status": "watching", "folder": folder}


@router.post("/api/unwatch/{project_id}")
async def stop_watching(project_id: int):
    """Stop filesystem watcher for a project folder."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Project not found")
        folder = dict(row)["folder_path"]

    if folder in _watchers:
        await _watchers[folder].stop()
        del _watchers[folder]
        return {"status": "stopped", "folder": folder}

    return {"status": "not_watching", "folder": folder}
