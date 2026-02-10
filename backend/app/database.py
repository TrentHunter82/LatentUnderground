import sqlite3

import aiosqlite

from . import config

DB_PATH = config.DB_PATH


async def get_db():
    """Yield an aiosqlite connection with retry on transient failures."""
    import asyncio
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
                await asyncio.sleep(delay)
                delay *= 3  # exponential backoff: 0.1, 0.3, 0.9
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
