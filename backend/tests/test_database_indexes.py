"""Tests for database indexes (Phase 7)."""

import aiosqlite
import pytest

from app.database import init_db


@pytest.mark.asyncio
async def test_indexes_created(tmp_path):
    """init_db creates all expected indexes."""
    from app import database

    db_path = tmp_path / "idx_test.db"
    original = database.DB_PATH
    database.DB_PATH = db_path
    try:
        await init_db()

        async with aiosqlite.connect(db_path) as db:
            rows = await (await db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            )).fetchall()
            index_names = {row[0] for row in rows}

        assert "idx_projects_status" in index_names
        assert "idx_swarm_runs_project_started" in index_names
        assert "idx_swarm_runs_status" in index_names
    finally:
        database.DB_PATH = original


@pytest.mark.asyncio
async def test_index_columns_correct(tmp_path):
    """Indexes are on the correct columns."""
    from app import database

    db_path = tmp_path / "idx_cols.db"
    original = database.DB_PATH
    database.DB_PATH = db_path
    try:
        await init_db()

        async with aiosqlite.connect(db_path) as db:
            # Check idx_projects_status is on projects table
            rows = await (await db.execute(
                "SELECT tbl_name FROM sqlite_master WHERE type='index' AND name='idx_projects_status'"
            )).fetchall()
            assert rows[0][0] == "projects"

            # Check idx_swarm_runs_project_started is on swarm_runs table
            rows = await (await db.execute(
                "SELECT tbl_name FROM sqlite_master WHERE type='index' AND name='idx_swarm_runs_project_started'"
            )).fetchall()
            assert rows[0][0] == "swarm_runs"

            # Check idx_swarm_runs_status is on swarm_runs table
            rows = await (await db.execute(
                "SELECT tbl_name FROM sqlite_master WHERE type='index' AND name='idx_swarm_runs_status'"
            )).fetchall()
            assert rows[0][0] == "swarm_runs"
    finally:
        database.DB_PATH = original


@pytest.mark.asyncio
async def test_indexes_idempotent(tmp_path):
    """Calling init_db twice doesn't fail (IF NOT EXISTS)."""
    from app import database

    db_path = tmp_path / "idx_idem.db"
    original = database.DB_PATH
    database.DB_PATH = db_path
    try:
        await init_db()
        await init_db()  # Should not raise

        async with aiosqlite.connect(db_path) as db:
            rows = await (await db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            )).fetchall()
            assert len(rows) == 3
    finally:
        database.DB_PATH = original
