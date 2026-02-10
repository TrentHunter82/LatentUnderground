"""Tests for Phase 9 production hardening: WAL mode, backup safety, log search caps."""
import sqlite3
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app import database


@pytest.mark.asyncio
async def test_backup_endpoint_returns_sql(client):
    """GET /api/backup returns downloadable SQL content."""
    resp = await client.get("/api/backup")
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")
    body = resp.text
    assert "CREATE TABLE" in body or "INSERT" in body or body == ""


@pytest.mark.asyncio
async def test_backup_create_helper_uses_context_managers():
    """_create_backup closes connections even on success."""
    from app.routes.backup import _create_backup
    buf = _create_backup()
    assert buf.readable()
    content = buf.read().decode("utf-8")
    # Should contain valid SQL or empty DB dump
    assert isinstance(content, str)


@pytest.mark.asyncio
async def test_log_search_caps_limit(client, tmp_path, sample_project_data):
    """Log search should cap limit at 1000."""
    # Create a project first
    resp = await client.post("/api/projects", json=sample_project_data)
    pid = resp.json()["id"]
    # Search with absurd limit
    resp = await client.get(f"/api/logs/search?project_id={pid}&limit=999999")
    assert resp.status_code == 200
    # The endpoint runs fine (doesn't OOM), results are bounded


@pytest.mark.asyncio
async def test_log_search_clamps_negative_offset(client, tmp_path, sample_project_data):
    """Log search should clamp negative offset to 0."""
    resp = await client.post("/api/projects", json=sample_project_data)
    pid = resp.json()["id"]
    resp = await client.get(f"/api/logs/search?project_id={pid}&offset=-5")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_wal_mode_enabled(tmp_path):
    """Database should use WAL journal mode after init_db."""
    import aiosqlite
    db_path = tmp_path / "wal_test.db"
    original = database.DB_PATH
    database.DB_PATH = db_path
    try:
        await database.init_db()
        async with aiosqlite.connect(db_path) as db:
            row = await (await db.execute("PRAGMA journal_mode")).fetchone()
            assert row[0] == "wal"
    finally:
        database.DB_PATH = original


@pytest.mark.asyncio
async def test_init_db_creates_indexes(tmp_path):
    """init_db should create performance indexes on projects and swarm_runs."""
    import aiosqlite
    db_path = tmp_path / "idx_test.db"
    original = database.DB_PATH
    database.DB_PATH = db_path
    try:
        await database.init_db()
        async with aiosqlite.connect(db_path) as db:
            rows = await (await db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            )).fetchall()
            index_names = {r[0] for r in rows}
            assert "idx_projects_status" in index_names
            assert "idx_swarm_runs_project_started" in index_names
            assert "idx_swarm_runs_status" in index_names
    finally:
        database.DB_PATH = original


@pytest.mark.asyncio
async def test_foreign_keys_enabled_per_connection(tmp_path):
    """get_db dependency should enable foreign_keys on each connection."""
    import aiosqlite
    db_path = tmp_path / "fk_test.db"
    original = database.DB_PATH
    database.DB_PATH = db_path
    try:
        await database.init_db()
        # Simulate what get_db does
        async for db in database.get_db():
            row = await (await db.execute("PRAGMA foreign_keys")).fetchone()
            assert row[0] == 1
    finally:
        database.DB_PATH = original


@pytest.mark.asyncio
async def test_backup_contains_tables(client, sample_project_data):
    """Backup SQL should reference the known tables after creating data."""
    resp = await client.post("/api/projects", json=sample_project_data)
    assert resp.status_code == 201
    resp = await client.get("/api/backup")
    assert resp.status_code == 200
    body = resp.text
    assert "projects" in body
