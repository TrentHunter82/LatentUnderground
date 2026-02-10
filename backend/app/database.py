import asyncio
import logging
import random
import sqlite3

import aiosqlite

from . import config

DB_PATH = config.DB_PATH

_logger = logging.getLogger("latent.db")


class ConnectionPool:
    """Lightweight async connection pool for aiosqlite.

    Reuses connections to avoid per-request thread creation and PRAGMA setup overhead.
    Falls back to direct connections if the pool is exhausted (no blocking).
    """

    def __init__(self, db_path, size: int = 4):
        self._db_path = db_path
        self._size = size
        self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue(maxsize=size)
        self._created = 0
        self._closed = False

    async def _create_connection(self) -> aiosqlite.Connection:
        """Create a new connection with pragmas pre-configured."""
        db = await aiosqlite.connect(self._db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA busy_timeout = 5000")
        return db

    async def initialize(self):
        """Pre-create connections to fill the pool."""
        for _ in range(self._size):
            conn = await self._create_connection()
            await self._pool.put(conn)
            self._created += 1
        _logger.info("Connection pool initialized with %d connections", self._size)

    async def acquire(self) -> aiosqlite.Connection:
        """Get a connection from the pool, or create one if pool is empty."""
        try:
            return self._pool.get_nowait()
        except asyncio.QueueEmpty:
            # Pool exhausted - create a temporary overflow connection
            return await self._create_connection()

    async def release(self, conn: aiosqlite.Connection):
        """Return a connection to the pool, or close if pool is full."""
        if self._closed:
            await conn.close()
            return
        try:
            self._pool.put_nowait(conn)
        except asyncio.QueueFull:
            # Pool is full (overflow connection), just close it
            await conn.close()

    async def close(self):
        """Close all pooled connections."""
        self._closed = True
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                await conn.close()
            except asyncio.QueueEmpty:
                break
        _logger.info("Connection pool closed")


# Global pool instance (initialized in lifespan, None during tests)
_pool: ConnectionPool | None = None


async def init_pool(db_path=None):
    """Initialize the global connection pool."""
    global _pool
    path = db_path or DB_PATH
    _pool = ConnectionPool(path)
    await _pool.initialize()


async def close_pool():
    """Close the global connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def get_db():
    """Yield an aiosqlite connection with retry on transient failures.

    If a connection pool is available (production), borrows from the pool.
    Otherwise falls back to direct connection (tests).

    Uses exponential backoff with random jitter to prevent thundering herd
    when multiple requests hit a locked database simultaneously.
    """
    # Pool path: borrow and return
    if _pool and not _pool._closed:
        db = await _pool.acquire()
        try:
            yield db
        finally:
            await _pool.release(db)
        return

    # Direct connection path (tests or no pool initialized)
    retries = 3
    delay = 0.1
    last_err = None
    for attempt in range(retries):
        try:
            db = await aiosqlite.connect(DB_PATH)
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute("PRAGMA busy_timeout = 5000")
            break
        except (sqlite3.OperationalError, OSError) as exc:
            last_err = exc
            if attempt < retries - 1:
                # Exponential backoff with jitter: base * 3^attempt + random(0, base/2)
                jittered_delay = delay + random.uniform(0, delay * 0.5)
                await asyncio.sleep(jittered_delay)
                delay *= 3  # 0.1, 0.3, 0.9 base delays
            continue
    else:
        raise last_err
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Production SQLite pragmas - WAL enables concurrent reads/writes,
        # synchronous=NORMAL is safe with WAL, temp_store=MEMORY speeds up temp tables
        await db.execute("PRAGMA journal_mode = WAL")
        await db.execute("PRAGMA synchronous = NORMAL")
        await db.execute("PRAGMA temp_store = MEMORY")
        await db.execute("PRAGMA cache_size = -16000")  # 16MB cache
        await db.execute("PRAGMA mmap_size = 268435456")  # 256MB memory-mapped I/O
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA busy_timeout = 5000")  # 5s wait on locks
        await db.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                goal TEXT NOT NULL,
                project_type TEXT NOT NULL DEFAULT 'Web Application (frontend + backend)',
                tech_stack TEXT NOT NULL DEFAULT 'auto-detect based on project type',
                complexity TEXT NOT NULL DEFAULT 'Medium',
                requirements TEXT NOT NULL DEFAULT '',
                folder_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'created',
                swarm_pid INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Migration: add swarm_pid if table already exists without it
        try:
            await db.execute("ALTER TABLE projects ADD COLUMN swarm_pid INTEGER")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        # Migration: add config column
        try:
            await db.execute("ALTER TABLE projects ADD COLUMN config TEXT DEFAULT '{}'")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        # Migration: add archived_at column
        try:
            await db.execute("ALTER TABLE projects ADD COLUMN archived_at TEXT")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        await db.execute("""
            CREATE TABLE IF NOT EXISTS swarm_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                ended_at TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                phase INTEGER,
                tasks_completed INTEGER DEFAULT 0,
                task_summary TEXT DEFAULT '',
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS swarm_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                config TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS webhooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                events TEXT NOT NULL DEFAULT '[]',
                secret TEXT,
                project_id INTEGER,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)

        # Indexes for common query patterns
        await db.execute("CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_swarm_runs_project_started ON swarm_runs(project_id, started_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_swarm_runs_status ON swarm_runs(status)")
        # Composite index for project analytics queries (project_id + ended_at for duration calcs)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_swarm_runs_project_ended ON swarm_runs(project_id, ended_at)")
        # Index for template ordering
        await db.execute("CREATE INDEX IF NOT EXISTS idx_templates_created ON swarm_templates(created_at)")
        # Index for webhook event filtering
        await db.execute("CREATE INDEX IF NOT EXISTS idx_webhooks_enabled ON webhooks(enabled)")

        # Update query planner statistics for optimal index usage
        await db.execute("ANALYZE")

        await db.commit()
