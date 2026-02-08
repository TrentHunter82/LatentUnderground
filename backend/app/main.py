import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from . import config
from .database import DB_PATH, init_db
from .routes import projects, swarm, files, logs, websocket, backup, templates
from .routes.swarm import _pid_alive
from .routes.watcher import router as watcher_router, cleanup_watchers

logger = logging.getLogger("latent")

_start_time = time.time()

# Path to the built frontend
FRONTEND_DIST = config.FRONTEND_DIST


def _ensure_directories():
    """Create required directories if they don't exist."""
    project_root = Path(__file__).parent.parent.parent
    for subdir in [
        ".claude/heartbeats",
        ".claude/signals",
        "tasks",
        "logs",
    ]:
        (project_root / subdir).mkdir(parents=True, exist_ok=True)


async def _reconcile_running_projects():
    """Check projects marked 'running' and reconcile with actual process state.

    On restart, we can't reattach to subprocess pipes, but we can:
    - Mark dead-PID projects as stopped and close orphan swarm_runs
    - Keep alive-PID projects as running (user can stop them normally)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT id, name, swarm_pid FROM projects WHERE status = 'running'"
        )).fetchall()

        for row in rows:
            pid = row["swarm_pid"]
            project_id = row["id"]

            if _pid_alive(pid):
                logger.info(
                    "Project %d (%s) has alive process pid=%s (cannot reattach pipes)",
                    project_id, row["name"], pid,
                )
            else:
                logger.warning(
                    "Project %d (%s) had stale pid=%s, marking as stopped",
                    project_id, row["name"], pid,
                )
                await db.execute(
                    "UPDATE projects SET status = 'stopped', swarm_pid = NULL, "
                    "updated_at = datetime('now') WHERE id = ?",
                    (project_id,),
                )
                await db.execute(
                    "UPDATE swarm_runs SET ended_at = datetime('now'), status = 'crashed' "
                    "WHERE project_id = ? AND status = 'running'",
                    (project_id,),
                )

        if rows:
            await db.commit()
            logger.info("Reconciled %d running project(s) on startup", len(rows))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _ensure_directories()
    await init_db()
    await _reconcile_running_projects()
    logger.info("Latent Underground started")
    yield
    await swarm.cancel_drain_tasks()
    await cleanup_watchers()
    logger.info("Latent Underground shutting down")


app = FastAPI(
    title="Latent Underground",
    description="GUI for managing Claude Swarm sessions",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(swarm.router)
app.include_router(files.router)
app.include_router(logs.router)
app.include_router(websocket.router)
app.include_router(watcher_router)
app.include_router(backup.router)
app.include_router(templates.router)


@app.get("/api/health", tags=["system"])
async def health():
    """System health check: database status, active processes, uptime, and version."""
    uptime_seconds = int(time.time() - _start_time)
    base = {"app": "Latent Underground", "version": "0.1.0", "uptime_seconds": uptime_seconds}
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("SELECT 1")
            db.row_factory = aiosqlite.Row
            active = (await (await db.execute(
                "SELECT COUNT(*) as cnt FROM projects WHERE status = 'running'"
            )).fetchone())["cnt"]
        return {**base, "status": "ok", "db": "ok", "active_processes": active}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={**base, "status": "degraded", "db": "error", "active_processes": 0},
        )


# --- Serve frontend static files ---
# Mount static assets (JS, CSS) if the frontend build exists
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve frontend SPA. Any non-API path falls through to index.html."""
        file_path = (FRONTEND_DIST / full_path).resolve()
        # Prevent path traversal outside of dist/
        if full_path and file_path.is_relative_to(FRONTEND_DIST.resolve()) and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
