import asyncio
import hmac
import logging
import sqlite3
import threading
import time
import traceback
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import aiosqlite
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from . import config
from . import database
from .database import init_db
from .routes import projects, swarm, files, logs, websocket, backup, templates, browse, plugins, webhooks
from .routes.backup import _create_backup
from .routes.swarm import _pid_alive
from .routes.watcher import router as watcher_router, cleanup_watchers
from .plugins import plugin_manager

logger = logging.getLogger("latent")


class JsonFormatter(logging.Formatter):
    """JSON lines log formatter for structured logging."""
    def format(self, record):
        import json
        return json.dumps({
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }, default=str)


_start_time = time.time()

# Track PID monitor threads so we can stop them on shutdown
_pid_monitors: list[threading.Event] = []

# Path to the built frontend
FRONTEND_DIST = config.FRONTEND_DIST

# Paths that skip authentication
_AUTH_SKIP_PATHS = {"/api/health", "/docs", "/redoc", "/openapi.json"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit POST API endpoints to prevent accidental rapid launches."""

    def __init__(self, app, rpm: int = 30):
        super().__init__(app)
        self.rpm = rpm
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        if self.rpm <= 0 or request.method != "POST" or not request.url.path.startswith("/api/"):
            return await call_next(request)

        # Use API key as rate limit identity when present, fall back to IP
        client_id = request.client.host if request.client else "unknown"
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            client_id = f"key:{auth_header[7:][:8]}"  # first 8 chars of key
        elif request.headers.get("x-api-key"):
            client_id = f"key:{request.headers['x-api-key'][:8]}"
        key = f"{client_id}:{request.url.path}"
        now = time.time()
        window = 60.0

        # Clean old entries
        self._requests[key] = [t for t in self._requests[key] if now - t < window]

        if len(self._requests[key]) >= self.rpm:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded. Max {self.rpm} requests per minute."},
            )

        self._requests[key].append(now)
        return await call_next(request)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Optional API key authentication. Disabled when LU_API_KEY is empty."""

    async def dispatch(self, request: Request, call_next):
        api_key = config.API_KEY
        if not api_key:
            return await call_next(request)

        # Skip auth for public paths and WebSocket upgrades
        path = request.url.path
        if path in _AUTH_SKIP_PATHS or path == "/ws":
            return await call_next(request)
        # Skip for frontend static files
        if not path.startswith("/api/"):
            return await call_next(request)

        # Check Authorization: Bearer <key> or X-API-Key: <key>
        provided_key = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            provided_key = auth_header[7:]
        if not provided_key:
            provided_key = request.headers.get("x-api-key")

        if not provided_key or not hmac.compare_digest(provided_key, api_key):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )

        return await call_next(request)


class APIVersionMiddleware:
    """API versioning: /api/v1/ routes are rewritten to /api/, unversioned /api/ gets deprecation headers.

    This allows all existing routes to be accessed via both /api/ and /api/v1/.
    Unversioned /api/ routes include deprecation headers encouraging migration to /api/v1/.
    """

    def __init__(self, app):
        self.app = app

    def __getattr__(self, name):
        """Proxy attribute access to the wrapped FastAPI app."""
        return getattr(self.app, name)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope["path"]
            if path.startswith("/api/v1/"):
                # Rewrite v1 path to unversioned path for route matching
                scope = dict(scope)
                scope["path"] = "/api/" + path[8:]
                if "raw_path" in scope:
                    scope["raw_path"] = scope["path"].encode("latin-1")
            elif path.startswith("/api/") and path not in _AUTH_SKIP_PATHS:
                # Add deprecation headers to unversioned API routes
                async def send_with_deprecation(message):
                    if message["type"] == "http.response.start":
                        headers = list(message.get("headers", []))
                        headers.append((b"x-api-deprecation", b"true"))
                        headers.append((b"sunset", b"2026-12-31"))
                        message = dict(message)
                        message["headers"] = headers
                    await send(message)
                await self.app(scope, receive, send_with_deprecation)
                return
        await self.app(scope, receive, send)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log HTTP requests with method, path, status code, and duration."""

    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        logger.info(
            "%s %s %d %.1fms",
            request.method, request.url.path, response.status_code, duration_ms,
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all API responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        # Apply security headers to all responses
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # X-XSS-Protection: 0 is modern best practice (rely on CSP, not legacy filter)
        response.headers["X-XSS-Protection"] = "0"
        # Cache-Control: no-store for API responses to prevent caching of sensitive data
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response


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


def _monitor_pid(project_id: int, pid: int, name: str, stop_event: threading.Event):
    """Background thread that monitors a running PID and marks project stopped when it dies.

    Since we can't reattach to subprocess pipes after restart, this thread
    watches the PID and updates the database when the process exits.
    """
    while not stop_event.is_set():
        stop_event.wait(15)  # Check every 15 seconds
        if stop_event.is_set():
            break
        if not _pid_alive(pid):
            logger.warning(
                "Monitored PID %d for project %d (%s) has died, marking stopped",
                pid, project_id, name,
            )
            try:
                conn = sqlite3.connect(str(database.DB_PATH))
                conn.execute(
                    "UPDATE projects SET status = 'stopped', swarm_pid = NULL, "
                    "updated_at = datetime('now') WHERE id = ?",
                    (project_id,),
                )
                conn.execute(
                    "UPDATE swarm_runs SET ended_at = datetime('now'), status = 'crashed' "
                    "WHERE project_id = ? AND status = 'running'",
                    (project_id,),
                )
                conn.commit()
                conn.close()
            except Exception:
                logger.error("Failed to update DB for dead PID %d", pid, exc_info=True)
            break


async def _reconcile_running_projects():
    """Check projects marked 'running' and reconcile with actual process state.

    On restart, we can't reattach to subprocess pipes, but we can:
    - Mark dead-PID projects as stopped and close orphan swarm_runs
    - Start monitor threads for alive-PID projects to detect when they exit
    """
    async with aiosqlite.connect(database.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute(
            "SELECT id, name, swarm_pid FROM projects WHERE status = 'running'"
        )).fetchall()

        for row in rows:
            pid = row["swarm_pid"]
            project_id = row["id"]

            try:
                is_alive = _pid_alive(pid)
            except Exception:
                logger.error("Failed to check PID %s for project %d, treating as dead",
                             pid, project_id, exc_info=True)
                is_alive = False

            if is_alive:
                logger.info(
                    "Project %d (%s) has alive process pid=%s, starting monitor thread",
                    project_id, row["name"], pid,
                )
                stop_event = threading.Event()
                _pid_monitors.append(stop_event)
                t = threading.Thread(
                    target=_monitor_pid,
                    args=(project_id, pid, row["name"], stop_event),
                    daemon=True,
                )
                t.start()
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


async def _cleanup_old_logs():
    """Delete project log files older than LU_LOG_RETENTION_DAYS."""
    days = config.LOG_RETENTION_DAYS
    if days <= 0:
        return
    cutoff = time.time() - (days * 86400)
    removed = 0
    async with aiosqlite.connect(database.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await (await db.execute("SELECT folder_path FROM projects")).fetchall()
    for row in rows:
        try:
            logs_dir = Path(row["folder_path"]) / "logs"
            if not logs_dir.is_dir():
                continue
            for log_file in logs_dir.glob("*.log"):
                try:
                    if log_file.stat().st_mtime < cutoff:
                        log_file.unlink()
                        removed += 1
                except OSError:
                    pass
        except OSError:
            logger.debug("Failed to access logs in %s", row["folder_path"], exc_info=True)
    if removed:
        logger.info("Log retention: removed %d log file(s) older than %d days", removed, days)


# Background task handle for auto-backups
_backup_task: asyncio.Task | None = None


async def _auto_backup_loop():
    """Periodically create database backups."""
    interval = config.BACKUP_INTERVAL_HOURS * 3600
    keep = config.BACKUP_KEEP
    backup_dir = Path(__file__).parent.parent / "backups"
    backup_dir.mkdir(exist_ok=True)

    while True:
        await asyncio.sleep(interval)
        try:
            buf = await asyncio.to_thread(_create_backup)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = backup_dir / f"auto_backup_{timestamp}.sql"
            dest.write_bytes(buf.read())
            logger.info("Auto-backup saved: %s", dest.name)

            # Prune old backups
            backups = sorted(backup_dir.glob("auto_backup_*.sql"), key=lambda p: p.stat().st_mtime)
            while len(backups) > keep:
                oldest = backups.pop(0)
                oldest.unlink()
                logger.info("Auto-backup pruned: %s", oldest.name)
        except Exception:
            logger.error("Auto-backup failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    if config.LOG_FORMAT == "json":
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logging.basicConfig(level=log_level, handlers=[handler])
    else:
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    _ensure_directories()
    await init_db()
    await _reconcile_running_projects()
    await _cleanup_old_logs()

    # Start auto-backup if configured
    global _backup_task
    if config.BACKUP_INTERVAL_HOURS > 0:
        _backup_task = asyncio.create_task(_auto_backup_loop())
        logger.info("Auto-backup enabled: every %dh, keep %d", config.BACKUP_INTERVAL_HOURS, config.BACKUP_KEEP)

    # Discover plugins
    plugin_manager.discover()

    logger.info("Latent Underground started")
    yield

    # --- Graceful shutdown ---
    logger.info("Latent Underground shutting down...")

    # Cancel auto-backup task
    if _backup_task and not _backup_task.done():
        _backup_task.cancel()
        try:
            await _backup_task
        except asyncio.CancelledError:
            pass

    # Stop PID monitor threads with timeout
    for evt in _pid_monitors:
        evt.set()
    _pid_monitors.clear()

    # Drain output buffers and stop drain threads
    await swarm.cancel_drain_tasks()
    await cleanup_watchers()
    logger.info("Latent Underground shutdown complete")


app = FastAPI(
    title="Latent Underground",
    description="GUI for managing Claude Swarm sessions",
    version="0.11.0",
    lifespan=lifespan,
)


# --- Global exception handlers ---

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return structured 422 responses for Pydantic/FastAPI validation errors."""
    logger.warning(
        "Validation error on %s %s: %s",
        request.method, request.url.path, exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "errors": [
                {
                    "field": ".".join(str(loc) for loc in err.get("loc", [])),
                    "message": err.get("msg", ""),
                    "type": err.get("type", ""),
                }
                for err in exc.errors()
            ],
        },
    )


@app.exception_handler(sqlite3.OperationalError)
async def db_exception_handler(request: Request, exc: sqlite3.OperationalError):
    """Return structured 503 responses for database errors."""
    logger.error(
        "Database error on %s %s: %s",
        request.method, request.url.path, str(exc),
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Database temporarily unavailable", "error": "db_error"},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Return structured 500 responses for unhandled exceptions."""
    logger.error(
        "Unhandled exception on %s %s: %s\n%s",
        request.method, request.url.path, str(exc),
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# --- Middleware ---

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(APIKeyMiddleware)
if config.REQUEST_LOG:
    app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware, rpm=config.RATE_LIMIT_RPM)
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
app.include_router(browse.router)
app.include_router(plugins.router)
app.include_router(webhooks.router)


@app.get("/api/health", tags=["system"])
async def health():
    """System health check: database status, active processes, uptime, and version."""
    uptime_seconds = int(time.time() - _start_time)
    base = {"app": "Latent Underground", "version": "0.11.0", "uptime_seconds": uptime_seconds}
    try:
        async with aiosqlite.connect(database.DB_PATH) as db:
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
        # Never intercept API or WebSocket routes
        if full_path.startswith("api/") or full_path == "ws":
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        file_path = (FRONTEND_DIST / full_path).resolve()
        # Prevent path traversal outside of dist/
        if full_path and file_path.is_relative_to(FRONTEND_DIST.resolve()) and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")


# API versioning: wrap complete ASGI app (must be last after all routes defined)
# /api/v1/X -> rewrites to /api/X, /api/X -> adds deprecation headers
_fastapi_app = app
app = APIVersionMiddleware(_fastapi_app)
