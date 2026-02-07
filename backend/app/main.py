import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from . import config
from .database import init_db
from .routes import projects, swarm, files, logs, websocket, backup
from .routes.watcher import router as watcher_router, cleanup_watchers

logger = logging.getLogger("latent")

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _ensure_directories()
    await init_db()
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


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": "Latent Underground", "version": "0.1.0"}


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
