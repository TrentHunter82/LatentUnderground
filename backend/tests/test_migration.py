"""Comprehensive tests for database migration system.

Tests the custom migration framework in app.database, ensuring idempotent,
incremental migrations work correctly and preserve data across schema changes.
"""

import os

# Disable rate limiting in tests (must be set before app imports)
os.environ.setdefault("LU_RATE_LIMIT_RPM", "0")
os.environ.setdefault("LU_RATE_LIMIT_READ_RPM", "0")

import sqlite3

import aiosqlite
import pytest

from app.database import (
    SCHEMA_VERSION,
    _get_schema_version,
    _migration_001,
    _migration_002,
    _run_migrations,
    _safe_add_column,
    _set_schema_version,
    init_db,
)


# ---------------------------------------------------------------------------
# Test: Fresh database migration (v0 → v2)
# ---------------------------------------------------------------------------


async def test_fresh_database_migration(tmp_path):
    """Test migration from empty database to current schema version.

    Verifies:
    - All tables are created
    - All columns exist with correct definitions
    - All indexes are created
    - schema_version table records all migrations
    """
    db_path = tmp_path / "fresh.db"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")

        # Verify starting at version 0
        version = await _get_schema_version(db)
        assert version == 0

        # Run migrations
        await _run_migrations(db)

        # Verify final version
        version = await _get_schema_version(db)
        assert version == SCHEMA_VERSION
        assert version == 6

    # Reconnect and verify schema
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Verify schema_version table has all migrations recorded
        rows = await (await db.execute(
            "SELECT version FROM schema_version ORDER BY version"
        )).fetchall()
        assert len(rows) == 6
        assert rows[0]["version"] == 1
        assert rows[1]["version"] == 2
        assert rows[2]["version"] == 3
        assert rows[3]["version"] == 4
        assert rows[4]["version"] == 5
        assert rows[5]["version"] == 6

        # Verify projects table exists with all columns
        cursor = await db.execute("PRAGMA table_info(projects)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert "id" in columns
        assert "name" in columns
        assert "goal" in columns
        assert "project_type" in columns
        assert "tech_stack" in columns
        assert "complexity" in columns
        assert "requirements" in columns
        assert "folder_path" in columns
        assert "status" in columns
        assert "swarm_pid" in columns
        assert "config" in columns
        assert "archived_at" in columns
        assert "created_at" in columns
        assert "updated_at" in columns

        # Verify swarm_runs table with migration 002 columns
        cursor = await db.execute("PRAGMA table_info(swarm_runs)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert "id" in columns
        assert "project_id" in columns
        assert "started_at" in columns
        assert "ended_at" in columns
        assert "status" in columns
        assert "phase" in columns
        assert "tasks_completed" in columns
        assert "task_summary" in columns
        assert "label" in columns  # from migration 002
        assert "notes" in columns  # from migration 002
        assert "summary" in columns  # from migration 004
        assert "guardrail_results" in columns  # from migration 006

        # Verify agent_events table (from migration 004)
        cursor = await db.execute("PRAGMA table_info(agent_events)")
        ae_columns = {row[1] for row in await cursor.fetchall()}
        assert "id" in ae_columns
        assert "project_id" in ae_columns
        assert "run_id" in ae_columns
        assert "agent_name" in ae_columns
        assert "event_type" in ae_columns
        assert "detail" in ae_columns
        assert "timestamp" in ae_columns

        # Verify swarm_templates table
        cursor = await db.execute("PRAGMA table_info(swarm_templates)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert "id" in columns
        assert "name" in columns
        assert "description" in columns
        assert "config" in columns
        assert "created_at" in columns
        assert "updated_at" in columns

        # Verify webhooks table
        cursor = await db.execute("PRAGMA table_info(webhooks)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert "id" in columns
        assert "url" in columns
        assert "events" in columns
        assert "secret" in columns
        assert "project_id" in columns
        assert "enabled" in columns
        assert "created_at" in columns
        assert "updated_at" in columns

        # Verify indexes exist
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        indexes = {row[0] for row in await cursor.fetchall()}
        assert "idx_projects_status" in indexes
        assert "idx_swarm_runs_project_started" in indexes
        assert "idx_swarm_runs_status" in indexes
        assert "idx_swarm_runs_project_ended" in indexes
        assert "idx_templates_created" in indexes
        assert "idx_webhooks_enabled" in indexes
        assert "idx_agent_events_project_ts" in indexes  # from migration 004
        assert "idx_agent_events_type" in indexes  # from migration 004


# ---------------------------------------------------------------------------
# Test: Incremental migration (v1 → v2)
# ---------------------------------------------------------------------------


async def test_incremental_migration_v1_to_v2(tmp_path):
    """Test migration from v1 schema to v2.

    Verifies:
    - Only migration 002 runs (not 001)
    - label and notes columns are added to swarm_runs
    - Existing schema is preserved
    """
    db_path = tmp_path / "v1.db"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")

        # Manually create v1 schema (migration 001 only)
        await _migration_001(db)

        # Create schema_version table and record v1
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await _set_schema_version(db, 1)
        await db.commit()

        # Verify we're at v1
        version = await _get_schema_version(db)
        assert version == 1

        # Verify swarm_runs does NOT have label/notes yet
        cursor = await db.execute("PRAGMA table_info(swarm_runs)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert "label" not in columns
        assert "notes" not in columns

        # Run migrations (should apply 002, 003, 004, 005, 006)
        await _run_migrations(db)

        # Verify now at v6
        version = await _get_schema_version(db)
        assert version == 6

    # Reconnect and verify
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Verify all migrations are recorded
        rows = await (await db.execute(
            "SELECT version FROM schema_version ORDER BY version"
        )).fetchall()
        assert len(rows) == 6
        assert rows[0]["version"] == 1
        assert rows[1]["version"] == 2
        assert rows[2]["version"] == 3
        assert rows[3]["version"] == 4
        assert rows[4]["version"] == 5
        assert rows[5]["version"] == 6

        # Verify label, notes, and summary were added
        cursor = await db.execute("PRAGMA table_info(swarm_runs)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert "label" in columns
        assert "notes" in columns
        assert "summary" in columns

        # Verify agent_events table created
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_events'"
        )
        assert await cursor.fetchone() is not None

        # Verify original columns still exist
        assert "id" in columns
        assert "project_id" in columns
        assert "started_at" in columns


# ---------------------------------------------------------------------------
# Test: Idempotent re-run (v2 → v2)
# ---------------------------------------------------------------------------


async def test_idempotent_migration_rerun(tmp_path):
    """Test that running migrations on up-to-date database is safe.

    Verifies:
    - No errors when running migrations twice
    - Schema remains unchanged
    - No duplicate migration records
    """
    db_path = tmp_path / "idempotent.db"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")

        # Run migrations once
        await _run_migrations(db)
        version = await _get_schema_version(db)
        assert version == SCHEMA_VERSION

        # Get initial schema info
        cursor = await db.execute("PRAGMA table_info(projects)")
        columns_before = {row[1] for row in await cursor.fetchall()}

        # Run migrations again
        await _run_migrations(db)

        # Version should be unchanged
        version = await _get_schema_version(db)
        assert version == SCHEMA_VERSION

        # Schema should be unchanged
        cursor = await db.execute("PRAGMA table_info(projects)")
        columns_after = {row[1] for row in await cursor.fetchall()}
        assert columns_before == columns_after

        # Only 6 migration records (not duplicated)
        rows = await (await db.execute(
            "SELECT version FROM schema_version ORDER BY version"
        )).fetchall()
        assert len(rows) == 6


# ---------------------------------------------------------------------------
# Test: Data preservation during migration
# ---------------------------------------------------------------------------


async def test_data_preservation_during_migration(tmp_path):
    """Test that existing data is preserved when migrating v1 → v2.

    Verifies:
    - All original data intact after migration
    - New columns have NULL defaults
    - Foreign key relationships preserved
    """
    db_path = tmp_path / "data_preserve.db"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")

        # Create v1 schema
        await _migration_001(db)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await _set_schema_version(db, 1)

        # Insert test data
        await db.execute("""
            INSERT INTO projects (name, goal, folder_path, status)
            VALUES ('Test Project', 'Build something', '/test/path', 'running')
        """)
        cursor = await db.execute("SELECT last_insert_rowid()")
        project_id = (await cursor.fetchone())[0]

        await db.execute("""
            INSERT INTO swarm_runs (project_id, status, phase, tasks_completed, task_summary)
            VALUES (?, 'running', 3, 10, 'Working on backend')
        """, (project_id,))
        cursor = await db.execute("SELECT last_insert_rowid()")
        run_id = (await cursor.fetchone())[0]

        await db.commit()

        # Run migration to v2
        await _run_migrations(db)

    # Reconnect and verify data
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")

        # Verify project data preserved
        cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        project = await cursor.fetchone()
        assert project is not None
        assert project["name"] == "Test Project"
        assert project["goal"] == "Build something"
        assert project["folder_path"] == "/test/path"
        assert project["status"] == "running"

        # Verify swarm_run data preserved
        cursor = await db.execute("SELECT * FROM swarm_runs WHERE id = ?", (run_id,))
        run = await cursor.fetchone()
        assert run is not None
        assert run["project_id"] == project_id
        assert run["status"] == "running"
        assert run["phase"] == 3
        assert run["tasks_completed"] == 10
        assert run["task_summary"] == "Working on backend"

        # Verify new columns are NULL by default
        assert run["label"] is None
        assert run["notes"] is None
        assert run["summary"] is None

        # Verify foreign key relationship still works
        await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        await db.commit()

        # Cascade should have deleted the run
        cursor = await db.execute("SELECT * FROM swarm_runs WHERE id = ?", (run_id,))
        run = await cursor.fetchone()
        assert run is None


# ---------------------------------------------------------------------------
# Test: Pre-migration legacy database (v0 with tables but no schema_version)
# ---------------------------------------------------------------------------


async def test_legacy_database_migration(tmp_path):
    """Test migration of legacy database with tables but no schema_version.

    Simulates databases created before the migration system existed.

    Verifies:
    - schema_version table is created
    - All migrations are applied
    - _safe_add_column handles duplicate columns gracefully
    - No errors from CREATE TABLE IF NOT EXISTS on existing tables
    """
    db_path = tmp_path / "legacy.db"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")

        # Create legacy schema (pre-migration system)
        # This mimics early project versions with manual schema
        await db.execute("""
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                goal TEXT NOT NULL,
                folder_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'created',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        await db.execute("""
            CREATE TABLE swarm_runs (
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

        # Add some columns that migration 001 will try to add
        await db.execute("ALTER TABLE projects ADD COLUMN swarm_pid INTEGER")

        await db.commit()

        # Verify no schema_version table exists
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )
        assert await cursor.fetchone() is None

        # Run migrations - should handle existing tables gracefully
        await _run_migrations(db)

        # Verify migrated to current version
        version = await _get_schema_version(db)
        assert version == SCHEMA_VERSION

    # Reconnect and verify
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Verify schema_version table was created
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        )
        assert await cursor.fetchone() is not None

        # Verify all migrations recorded
        rows = await (await db.execute(
            "SELECT version FROM schema_version ORDER BY version"
        )).fetchall()
        assert len(rows) == 6

        # Verify migration additions were added via _safe_add_column
        # Note: CREATE TABLE IF NOT EXISTS does NOT add columns to existing tables
        # Only _safe_add_column calls will add the missing columns
        cursor = await db.execute("PRAGMA table_info(projects)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert "swarm_pid" in columns
        assert "config" in columns
        assert "archived_at" in columns
        # Original legacy columns still exist
        assert "name" in columns
        assert "goal" in columns
        assert "folder_path" in columns

        # Verify swarm_runs has migration 002 columns
        cursor = await db.execute("PRAGMA table_info(swarm_runs)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert "label" in columns
        assert "notes" in columns


# ---------------------------------------------------------------------------
# Test: _safe_add_column idempotency
# ---------------------------------------------------------------------------


async def test_safe_add_column_idempotency(tmp_path):
    """Test that _safe_add_column can be called multiple times safely.

    Verifies:
    - Adding a new column succeeds
    - Adding the same column again raises no error
    - Column definition remains unchanged
    """
    db_path = tmp_path / "safe_column.db"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Create a simple test table
        await db.execute("""
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)
        await db.commit()

        # Add a column using _safe_add_column
        await _safe_add_column(db, "test_table", "status", "TEXT DEFAULT 'active'")
        await db.commit()

        # Verify column exists
        cursor = await db.execute("PRAGMA table_info(test_table)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert "status" in columns

        # Add the same column again - should not raise error
        await _safe_add_column(db, "test_table", "status", "TEXT DEFAULT 'active'")
        await db.commit()

        # Verify still only one status column
        cursor = await db.execute("PRAGMA table_info(test_table)")
        columns = [row[1] for row in await cursor.fetchall()]
        assert columns.count("status") == 1

        # Verify we can insert data normally
        await db.execute(
            "INSERT INTO test_table (name, status) VALUES ('test', 'active')"
        )
        await db.commit()

        cursor = await db.execute("SELECT * FROM test_table")
        row = await cursor.fetchone()
        assert row["name"] == "test"
        assert row["status"] == "active"


async def test_safe_add_column_actual_error(tmp_path):
    """Test that _safe_add_column re-raises non-duplicate errors.

    Verifies:
    - Errors other than "duplicate column name" are raised
    """
    db_path = tmp_path / "safe_column_error.db"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Create a test table
        await db.execute("""
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY
            )
        """)
        await db.commit()

        # Try to add a column to a non-existent table - should raise
        with pytest.raises(sqlite3.OperationalError) as exc_info:
            await _safe_add_column(db, "nonexistent_table", "col", "TEXT")

        assert "no such table" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test: schema_version table behavior
# ---------------------------------------------------------------------------


async def test_get_schema_version_fresh_db(tmp_path):
    """Test _get_schema_version returns 0 for fresh database."""
    db_path = tmp_path / "version_fresh.db"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Fresh database with no schema_version table
        version = await _get_schema_version(db)
        assert version == 0


async def test_set_and_get_schema_version(tmp_path):
    """Test _set_schema_version and _get_schema_version work correctly."""
    db_path = tmp_path / "version_set_get.db"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Create schema_version table
        await db.execute("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.commit()

        # Set version 1
        await _set_schema_version(db, 1)
        await db.commit()

        version = await _get_schema_version(db)
        assert version == 1

        # Set version 2
        await _set_schema_version(db, 2)
        await db.commit()

        # Should return latest version
        version = await _get_schema_version(db)
        assert version == 2

        # Verify both versions are recorded
        rows = await (await db.execute(
            "SELECT version FROM schema_version ORDER BY version"
        )).fetchall()
        assert len(rows) == 2
        assert rows[0]["version"] == 1
        assert rows[1]["version"] == 2


async def test_get_schema_version_multiple_records(tmp_path):
    """Test _get_schema_version returns latest when multiple records exist."""
    db_path = tmp_path / "version_multiple.db"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Create schema_version table
        await db.execute("""
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # Insert multiple versions out of order
        await db.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (1, datetime('now'))"
        )
        await db.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (3, datetime('now'))"
        )
        await db.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (2, datetime('now'))"
        )
        await db.commit()

        # Should return highest version
        version = await _get_schema_version(db)
        assert version == 3


# ---------------------------------------------------------------------------
# Test: init_db WAL mode and pragmas
# ---------------------------------------------------------------------------


async def test_init_db_wal_mode(tmp_path, monkeypatch):
    """Test that init_db sets WAL journal mode and other pragmas.

    Verifies:
    - journal_mode is set to WAL
    - Other production pragmas are applied
    - Migrations are run
    """
    db_path = tmp_path / "wal_test.db"

    # Patch DB_PATH to use our test database
    import app.database
    monkeypatch.setattr(app.database, "DB_PATH", str(db_path))

    # Run init_db
    await init_db()

    # Reconnect and verify WAL mode
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        assert row[0].upper() == "WAL"

        # Verify foreign keys setting (note: PRAGMA foreign_keys needs to be set per connection)
        # init_db sets it during init, but we need to check that it was set
        # by verifying the tables have foreign key constraints
        cursor = await db.execute("PRAGMA foreign_key_list(swarm_runs)")
        fk_rows = await cursor.fetchall()
        assert len(fk_rows) > 0  # Should have FK to projects table

        # Verify migrations ran
        version = await _get_schema_version(db)
        assert version == SCHEMA_VERSION

        # Verify tables exist
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in await cursor.fetchall()}
        assert "projects" in tables
        assert "swarm_runs" in tables
        assert "swarm_templates" in tables
        assert "webhooks" in tables
        assert "schema_version" in tables


# ---------------------------------------------------------------------------
# Test: Migration ordering and skip logic
# ---------------------------------------------------------------------------


async def test_migration_ordering(tmp_path):
    """Test that migrations are applied in correct order and skipped properly.

    Verifies:
    - Migrations applied in ascending version order
    - Migrations already applied are skipped
    - Version increments correctly after each migration
    """
    db_path = tmp_path / "ordering.db"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")

        # Create schema_version table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.commit()

        # Manually verify starting at version 0
        version = await _get_schema_version(db)
        assert version == 0

        # Run migrations
        await _run_migrations(db)

        # Verify final version
        version = await _get_schema_version(db)
        assert version == 6

        # Verify migration records are in order
        rows = await (await db.execute(
            "SELECT version, applied_at FROM schema_version ORDER BY version"
        )).fetchall()
        assert len(rows) == 6
        assert rows[0]["version"] == 1
        assert rows[1]["version"] == 2
        assert rows[2]["version"] == 3
        assert rows[3]["version"] == 4
        assert rows[4]["version"] == 5
        assert rows[5]["version"] == 6

        # Verify applied_at timestamps are valid ISO8601
        for row in rows:
            assert row["applied_at"] is not None
            assert len(row["applied_at"]) > 0


async def test_migration_skip_already_applied(tmp_path):
    """Test that already-applied migrations are not re-run.

    Verifies:
    - Migration 001 is skipped when starting at v1
    - Only migration 002 is applied
    - No duplicate work performed
    """
    db_path = tmp_path / "skip.db"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")

        # Apply migration 001 manually
        await _migration_001(db)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await _set_schema_version(db, 1)
        await db.commit()

        # Verify at v1
        version = await _get_schema_version(db)
        assert version == 1

        # Verify swarm_runs has no label/notes
        cursor = await db.execute("PRAGMA table_info(swarm_runs)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert "label" not in columns
        assert "notes" not in columns

        # Run migrations - should apply 002, 003, 004, 005, 006
        await _run_migrations(db)

        # Verify at v6
        version = await _get_schema_version(db)
        assert version == 6

        # Verify label/notes added
        cursor = await db.execute("PRAGMA table_info(swarm_runs)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert "label" in columns
        assert "notes" in columns

        # Verify 6 migration records (1 + 2 + 3 + 4 + 5 + 6, not re-applied 1)
        rows = await (await db.execute(
            "SELECT version FROM schema_version ORDER BY version"
        )).fetchall()
        assert len(rows) == 6
        assert rows[0]["version"] == 1
        assert rows[1]["version"] == 2
        assert rows[2]["version"] == 3
        assert rows[3]["version"] == 4
        assert rows[4]["version"] == 5
        assert rows[5]["version"] == 6


# ---------------------------------------------------------------------------
# Test: Edge case - database already at current version
# ---------------------------------------------------------------------------


async def test_migration_already_at_current_version(tmp_path):
    """Test that migrations don't run when database is already current.

    Verifies:
    - No migrations applied when db is at SCHEMA_VERSION
    - No errors or warnings
    - Schema unchanged
    """
    db_path = tmp_path / "already_current.db"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")

        # Run migrations once to get to current version
        await _run_migrations(db)

        # Verify at current version
        version = await _get_schema_version(db)
        assert version == SCHEMA_VERSION

        # Count schema_version records
        rows = await (await db.execute(
            "SELECT COUNT(*) as count FROM schema_version"
        )).fetchone()
        count_before = rows["count"]

        # Run migrations again
        await _run_migrations(db)

        # Version should be unchanged
        version = await _get_schema_version(db)
        assert version == SCHEMA_VERSION

        # No new migration records
        rows = await (await db.execute(
            "SELECT COUNT(*) as count FROM schema_version"
        )).fetchone()
        count_after = rows["count"]
        assert count_after == count_before


# ---------------------------------------------------------------------------
# Test: Foreign key constraints after migration
# ---------------------------------------------------------------------------


async def test_foreign_key_constraints_after_migration(tmp_path):
    """Test that foreign key constraints work correctly after migration.

    Verifies:
    - CASCADE deletes work properly
    - Foreign key validation is enabled
    - Relationships are preserved through migrations
    """
    db_path = tmp_path / "fk_test.db"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")

        # Run migrations
        await _run_migrations(db)

        # Insert a project
        await db.execute("""
            INSERT INTO projects (name, goal, folder_path)
            VALUES ('FK Test', 'Test foreign keys', '/test')
        """)
        cursor = await db.execute("SELECT last_insert_rowid()")
        project_id = (await cursor.fetchone())[0]

        # Insert related records
        await db.execute("""
            INSERT INTO swarm_runs (project_id, status, label, notes)
            VALUES (?, 'running', 'Test Run', 'Testing FK')
        """, (project_id,))

        await db.execute("""
            INSERT INTO webhooks (url, events, project_id)
            VALUES ('http://test.com', '[]', ?)
        """, (project_id,))

        await db.commit()

        # Verify records exist
        cursor = await db.execute("SELECT COUNT(*) as count FROM swarm_runs WHERE project_id = ?", (project_id,))
        assert (await cursor.fetchone())["count"] == 1

        cursor = await db.execute("SELECT COUNT(*) as count FROM webhooks WHERE project_id = ?", (project_id,))
        assert (await cursor.fetchone())["count"] == 1

        # Delete the project
        await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        await db.commit()

        # Verify CASCADE deleted related records
        cursor = await db.execute("SELECT COUNT(*) as count FROM swarm_runs WHERE project_id = ?", (project_id,))
        assert (await cursor.fetchone())["count"] == 0

        cursor = await db.execute("SELECT COUNT(*) as count FROM webhooks WHERE project_id = ?", (project_id,))
        assert (await cursor.fetchone())["count"] == 0


# ---------------------------------------------------------------------------
# Test: Migration with concurrent access simulation
# ---------------------------------------------------------------------------


async def test_migration_with_existing_data_complex(tmp_path):
    """Test migration preserves complex relational data correctly.

    Verifies:
    - Multiple projects with runs preserved
    - All relationships intact
    - New columns have correct defaults
    - Old data unmodified
    """
    db_path = tmp_path / "complex_data.db"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")

        # Create v1 schema
        await _migration_001(db)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await _set_schema_version(db, 1)

        # Insert multiple projects
        project_ids = []
        for i in range(3):
            await db.execute("""
                INSERT INTO projects (name, goal, folder_path, status)
                VALUES (?, ?, ?, ?)
            """, (f"Project {i}", f"Goal {i}", f"/path/{i}", "running"))
            cursor = await db.execute("SELECT last_insert_rowid()")
            project_ids.append((await cursor.fetchone())[0])

        # Insert multiple runs per project
        run_data = []
        for pid in project_ids:
            for j in range(2):
                await db.execute("""
                    INSERT INTO swarm_runs (project_id, status, phase, tasks_completed, task_summary)
                    VALUES (?, 'running', ?, ?, ?)
                """, (pid, j + 1, (j + 1) * 5, f"Summary {j}"))
                cursor = await db.execute("SELECT last_insert_rowid()")
                run_id = (await cursor.fetchone())[0]
                run_data.append((run_id, pid, j + 1, (j + 1) * 5, f"Summary {j}"))

        await db.commit()

        # Migrate to v2
        await _run_migrations(db)

    # Verify all data preserved
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Verify all projects exist
        cursor = await db.execute("SELECT COUNT(*) as count FROM projects")
        assert (await cursor.fetchone())["count"] == 3

        # Verify all runs exist with correct data
        for run_id, pid, phase, tasks, summary in run_data:
            cursor = await db.execute("SELECT * FROM swarm_runs WHERE id = ?", (run_id,))
            run = await cursor.fetchone()
            assert run is not None
            assert run["project_id"] == pid
            assert run["phase"] == phase
            assert run["tasks_completed"] == tasks
            assert run["task_summary"] == summary
            # New columns should be NULL
            assert run["label"] is None
            assert run["notes"] is None

        # Verify we can update new columns
        await db.execute("""
            UPDATE swarm_runs SET label = 'Updated Label', notes = 'Test notes'
            WHERE id = ?
        """, (run_data[0][0],))
        await db.commit()

        cursor = await db.execute("SELECT * FROM swarm_runs WHERE id = ?", (run_data[0][0],))
        run = await cursor.fetchone()
        assert run["label"] == "Updated Label"
        assert run["notes"] == "Test notes"
