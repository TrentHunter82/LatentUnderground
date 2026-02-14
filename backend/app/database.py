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
        await db.execute("PRAGMA synchronous = NORMAL")
        await db.execute("PRAGMA temp_store = MEMORY")
        await db.execute("PRAGMA cache_size = -16000")
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
    # Cache reference to avoid TOCTOU race with close_pool()
    pool = _pool
    if pool and not pool._closed:
        db = await pool.acquire()
        try:
            yield db
        finally:
            await pool.release(db)
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


# ---------------------------------------------------------------------------
# Schema Migration System
# ---------------------------------------------------------------------------

# Current schema version — increment when adding new migrations
SCHEMA_VERSION = 6


async def _get_schema_version(db: aiosqlite.Connection) -> int:
    """Get the current schema version from the database."""
    try:
        row = await (await db.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        )).fetchone()
        return row["version"] if row else 0
    except sqlite3.OperationalError:
        # Table doesn't exist yet — version 0 (fresh database)
        return 0


async def _set_schema_version(db: aiosqlite.Connection, version: int):
    """Record a migration version as applied."""
    await db.execute(
        "INSERT INTO schema_version (version, applied_at) VALUES (?, datetime('now'))",
        (version,),
    )


def _add_column_if_missing(col_name: str, col_def: str, table: str = "projects") -> str:
    """Generate ALTER TABLE ADD COLUMN SQL that's safe to re-run."""
    return f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"


async def _safe_add_column(db: aiosqlite.Connection, table: str, col_name: str, col_def: str):
    """Add a column to a table, silently ignoring if it already exists."""
    try:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e).lower():
            raise


# --- Migration functions ---
# Each migration receives an aiosqlite.Connection and applies changes.
# Migrations are applied in order and are idempotent.

async def _migration_001(db: aiosqlite.Connection):
    """Initial schema: projects, swarm_runs, templates, webhooks, indexes.

    Also includes all pre-migration-system column additions that were
    previously done via ad-hoc ALTER TABLE statements.
    """
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
            config TEXT DEFAULT '{}',
            archived_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    # Backwards-compat: add columns in case table exists from before migration system
    await _safe_add_column(db, "projects", "swarm_pid", "INTEGER")
    await _safe_add_column(db, "projects", "config", "TEXT DEFAULT '{}'")
    await _safe_add_column(db, "projects", "archived_at", "TEXT")

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

    # Indexes
    await db.execute("CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_swarm_runs_project_started ON swarm_runs(project_id, started_at)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_swarm_runs_status ON swarm_runs(status)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_swarm_runs_project_ended ON swarm_runs(project_id, ended_at)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_templates_created ON swarm_templates(created_at)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_webhooks_enabled ON webhooks(enabled)")


async def _migration_002(db: aiosqlite.Connection):
    """Add label and notes columns to swarm_runs for run annotations."""
    await _safe_add_column(db, "swarm_runs", "label", "TEXT")
    await _safe_add_column(db, "swarm_runs", "notes", "TEXT")


async def _migration_003(db: aiosqlite.Connection):
    """Add composite indexes for common query patterns.

    - swarm_runs(project_id, status): analytics, supervisor, status checks
    - webhooks(project_id): CASCADE deletes, per-project webhook lookups
    - projects(archived_at, status): list_projects default filter
    """
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_swarm_runs_project_status "
        "ON swarm_runs(project_id, status)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_webhooks_project "
        "ON webhooks(project_id)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_projects_archived_status "
        "ON projects(archived_at, status)"
    )


async def _migration_004(db: aiosqlite.Connection):
    """Add agent_events table and swarm_runs.summary column.

    agent_events: structured event log for agent lifecycle events.
    summary: JSON blob for auto-generated run summaries.
    """
    await db.execute("""
        CREATE TABLE IF NOT EXISTS agent_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            run_id INTEGER,
            agent_name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            detail TEXT DEFAULT '',
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (run_id) REFERENCES swarm_runs(id) ON DELETE CASCADE
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_events_project_ts "
        "ON agent_events(project_id, timestamp)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_events_type "
        "ON agent_events(event_type)"
    )
    await _safe_add_column(db, "swarm_runs", "summary", "TEXT")


async def _migration_005(db: aiosqlite.Connection):
    """Add agent_checkpoints table for debug/replay checkpoint data."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS agent_checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            run_id INTEGER,
            agent_name TEXT NOT NULL,
            checkpoint_type TEXT NOT NULL,
            data TEXT DEFAULT '{}',
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (run_id) REFERENCES swarm_runs(id) ON DELETE CASCADE
        )
    """)
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_checkpoints_run_agent "
        "ON agent_checkpoints(run_id, agent_name)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_checkpoints_project_ts "
        "ON agent_checkpoints(project_id, timestamp)"
    )


async def _migration_006(db: aiosqlite.Connection):
    """Add guardrail_results column to swarm_runs for output guardrail validation."""
    await _safe_add_column(db, "swarm_runs", "guardrail_results", "TEXT")


# Ordered list of all migrations
_MIGRATIONS = [
    (1, _migration_001),
    (2, _migration_002),
    (3, _migration_003),
    (4, _migration_004),
    (5, _migration_005),
    (6, _migration_006),
]


async def _run_migrations(db: aiosqlite.Connection) -> bool:
    """Apply pending migrations in order.

    Returns True if migrations were applied, False if schema was already current.
    """
    # Create schema_version table if it doesn't exist
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    current = await _get_schema_version(db)
    if current >= SCHEMA_VERSION:
        _logger.info("Database schema is up to date (version %d)", current)
        return False

    _logger.info("Database schema version %d, applying migrations up to %d", current, SCHEMA_VERSION)

    for version, migration_fn in _MIGRATIONS:
        if version <= current:
            continue
        _logger.info("Applying migration %d...", version)
        await migration_fn(db)
        await _set_schema_version(db, version)
        _logger.info("Migration %d applied successfully", version)

    await db.commit()
    _logger.info("All migrations applied, schema now at version %d", SCHEMA_VERSION)
    return True


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Production SQLite pragmas - WAL enables concurrent reads/writes,
        # synchronous=NORMAL is safe with WAL, temp_store=MEMORY speeds up temp tables
        await db.execute("PRAGMA journal_mode = WAL")
        await db.execute("PRAGMA synchronous = NORMAL")
        await db.execute("PRAGMA temp_store = MEMORY")
        await db.execute("PRAGMA cache_size = -16000")  # 16MB cache
        await db.execute("PRAGMA mmap_size = 268435456")  # 256MB memory-mapped I/O
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA busy_timeout = 5000")  # 5s wait on locks

        # Run migrations (returns True if schema changed)
        schema_changed = await _run_migrations(db)

        # Only run ANALYZE when schema changed (new indexes/tables) to save startup time
        if schema_changed:
            await db.execute("ANALYZE")
            _logger.info("ANALYZE completed after schema migration")

        await db.commit()
