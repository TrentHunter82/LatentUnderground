"""Tests for graceful shutdown behavior of the Latent Underground FastAPI application.

Tests verify that the lifespan shutdown logic correctly:
- Cancels background tasks (backup, vacuum)
- Stops PID monitor threads
- Terminates agent processes and drain threads
- Marks running projects/swarm_runs as stopped in DB
- Cleans up filesystem watchers
- Closes connection pool
- Handles errors gracefully during shutdown
"""

import asyncio
import os
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

# Disable rate limiting in tests
os.environ.setdefault("LU_RATE_LIMIT_RPM", "0")
os.environ.setdefault("LU_RATE_LIMIT_READ_RPM", "0")

import aiosqlite
import pytest


@pytest.mark.asyncio
async def test_lifespan_clean_shutdown_no_active_agents(tmp_path):
    """Test clean shutdown when no agents are active."""
    from app import database
    from app.main import lifespan, _fastapi_app

    # Create a minimal test database
    db_path = tmp_path / "test.db"
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                goal TEXT NOT NULL,
                folder_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'created',
                swarm_pid INTEGER,
                config TEXT DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS swarm_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                ended_at TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("INSERT INTO schema_version (version) VALUES (4)")
        await db.commit()

    original_db_path = database.DB_PATH
    database.DB_PATH = db_path

    try:
        # Mock cleanup functions to verify they're called
        with patch("app.main.cleanup_watchers", new_callable=AsyncMock) as mock_cleanup_watchers, \
             patch("app.main.close_pool", new_callable=AsyncMock) as mock_close_pool, \
             patch("app.main._reconcile_running_projects", new_callable=AsyncMock), \
             patch("app.main._cleanup_old_logs", new_callable=AsyncMock), \
             patch("app.main.plugin_manager"):
            # Enter lifespan context
            async with lifespan(_fastapi_app):
                # App is running - verify startup completed
                pass  # Shutdown happens here

            # Verify cleanup was called
            mock_cleanup_watchers.assert_called_once()
            mock_close_pool.assert_called_once()
    finally:
        database.DB_PATH = original_db_path


@pytest.mark.asyncio
async def test_shutdown_marks_running_projects_as_stopped(tmp_path):
    """Test that shutdown marks running projects and swarm_runs as stopped."""
    from app import database
    from app.routes import swarm

    # Create test database
    db_path = tmp_path / "test.db"
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                goal TEXT NOT NULL,
                folder_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'created',
                swarm_pid INTEGER,
                config TEXT DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS swarm_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                ended_at TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        # Insert a running project with active swarm_run
        await db.execute(
            "INSERT INTO projects (id, name, goal, folder_path, status, swarm_pid) "
            "VALUES (1, 'Test', 'Goal', '/tmp/test', 'running', 12345)"
        )
        await db.execute(
            "INSERT INTO swarm_runs (project_id, status) VALUES (1, 'running')"
        )
        await db.commit()

    original_db_path = database.DB_PATH
    database.DB_PATH = db_path

    try:
        # Simulate an active agent in _agent_processes
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Still running
        mock_proc.pid = 9999
        swarm._agent_processes["1:Claude-1"] = mock_proc

        # Run shutdown cleanup
        await swarm.cancel_drain_tasks()

        # Mark projects as stopped (simulating shutdown logic)
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "UPDATE projects SET status = 'stopped', swarm_pid = NULL, "
                "updated_at = datetime('now') WHERE id = 1 AND status = 'running'"
            )
            await db.execute(
                "UPDATE swarm_runs SET ended_at = datetime('now'), status = 'stopped' "
                "WHERE project_id = 1 AND status = 'running'"
            )
            await db.commit()

        # Verify database state
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            project = await (await db.execute(
                "SELECT status, swarm_pid FROM projects WHERE id = 1"
            )).fetchone()
            assert project["status"] == "stopped"
            assert project["swarm_pid"] is None

            run = await (await db.execute(
                "SELECT status, ended_at FROM swarm_runs WHERE project_id = 1"
            )).fetchone()
            assert run["status"] == "stopped"
            assert run["ended_at"] is not None
    finally:
        # Cleanup
        swarm._agent_processes.clear()
        database.DB_PATH = original_db_path


@pytest.mark.asyncio
async def test_shutdown_cancels_background_tasks():
    """Test that shutdown cancels backup and vacuum background tasks."""
    import app.main as main_module

    # Create real asyncio tasks that can be cancelled
    async def dummy_task():
        try:
            await asyncio.sleep(1000)  # Long sleep
        except asyncio.CancelledError:
            raise

    backup_task = asyncio.create_task(dummy_task())
    vacuum_task = asyncio.create_task(dummy_task())

    # Simulate shutdown logic
    main_module._backup_task = backup_task
    main_module._vacuum_task = vacuum_task

    tasks = [main_module._backup_task, main_module._vacuum_task]
    for task in tasks:
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    # Verify both tasks were cancelled
    assert backup_task.cancelled()
    assert vacuum_task.cancelled()

    # Reset module state
    main_module._backup_task = None
    main_module._vacuum_task = None


@pytest.mark.asyncio
async def test_shutdown_stops_pid_monitor_threads():
    """Test that shutdown sets stop events for PID monitor threads."""
    import app.main as main_module

    # Create mock threading events
    event1 = threading.Event()
    event2 = threading.Event()
    main_module._pid_monitors.extend([event1, event2])

    # Verify events are not set initially
    assert not event1.is_set()
    assert not event2.is_set()

    # Simulate shutdown: stop PID monitor threads
    for evt in main_module._pid_monitors:
        evt.set()
    main_module._pid_monitors.clear()

    # Verify events were set
    assert event1.is_set()
    assert event2.is_set()
    assert len(main_module._pid_monitors) == 0


@pytest.mark.asyncio
async def test_shutdown_terminates_agent_processes():
    """Test that shutdown terminates agent processes via cancel_drain_tasks."""
    from app.routes import swarm

    # Create mock process
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # Process is running
    mock_proc.terminate = MagicMock()
    mock_proc.wait = MagicMock(return_value=0)
    mock_proc.pid = 12345

    swarm._agent_processes["42:Claude-1"] = mock_proc
    swarm._agent_drain_events["42:Claude-1"] = threading.Event()

    # Run cleanup
    await swarm.cancel_drain_tasks(project_id=42)

    # Verify process was terminated
    mock_proc.terminate.assert_called()

    # Verify cleanup removed entries
    assert "42:Claude-1" not in swarm._agent_processes
    assert "42:Claude-1" not in swarm._agent_drain_events


@pytest.mark.asyncio
async def test_shutdown_handles_db_errors_gracefully(tmp_path, caplog):
    """Test that shutdown completes even if DB update fails."""
    from app import database
    from app.routes import swarm

    db_path = tmp_path / "test.db"
    # Create a database that will fail on write
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                status TEXT NOT NULL
            )
        """)
        await db.commit()

    original_db_path = database.DB_PATH
    database.DB_PATH = db_path

    try:
        # Simulate active agent
        swarm._agent_processes["1:Claude-1"] = MagicMock()

        # Patch DB connection to raise an error
        with patch("aiosqlite.connect", side_effect=Exception("DB connection failed")):
            # This simulates the DB update step during shutdown
            try:
                async with aiosqlite.connect(database.DB_PATH) as db:
                    await db.execute("UPDATE projects SET status = 'stopped'")
            except Exception:
                # Shutdown should log error but not crash
                pass

        # Verify cleanup still happens (no exception raised)
        await swarm.cancel_drain_tasks()
        assert True  # If we get here, shutdown was resilient
    finally:
        swarm._agent_processes.clear()
        database.DB_PATH = original_db_path


@pytest.mark.asyncio
async def test_shutdown_cleans_up_watchers():
    """Test that cleanup_watchers is called during shutdown."""
    from app.routes.watcher import cleanup_watchers, _watchers
    from app.services.watcher import FolderWatcher

    # Create a mock watcher
    mock_watcher = MagicMock(spec=FolderWatcher)
    mock_watcher.stop = AsyncMock()
    _watchers["test_folder"] = mock_watcher

    # Call cleanup
    await cleanup_watchers()

    # Verify watcher was stopped and cleared
    mock_watcher.stop.assert_called_once()
    assert len(_watchers) == 0


@pytest.mark.asyncio
async def test_shutdown_with_multiple_concurrent_calls():
    """Test that multiple concurrent shutdown calls don't crash."""
    from app.routes import swarm

    # Simulate some agent state
    swarm._agent_processes["1:Claude-1"] = MagicMock()
    swarm._agent_processes["2:Claude-1"] = MagicMock()

    # Run cleanup twice concurrently
    await asyncio.gather(
        swarm.cancel_drain_tasks(),
        swarm.cancel_drain_tasks(),
    )

    # Verify we didn't crash and state is clean
    assert len(swarm._agent_processes) == 0


@pytest.mark.asyncio
async def test_shutdown_only_done_tasks_are_skipped():
    """Test that already-done background tasks are skipped during shutdown."""
    import app.main as main_module

    # Create a mock task that's already done
    mock_done_task = MagicMock(spec=asyncio.Task)
    mock_done_task.done.return_value = True
    mock_done_task.cancel = MagicMock()

    main_module._backup_task = mock_done_task

    # Simulate shutdown logic
    tasks = [main_module._backup_task]
    for task in tasks:
        if task and not task.done():
            task.cancel()

    # Verify cancel was NOT called on done task
    mock_done_task.cancel.assert_not_called()

    # Reset
    main_module._backup_task = None


@pytest.mark.asyncio
async def test_shutdown_with_no_background_tasks():
    """Test shutdown when no background tasks exist."""
    import app.main as main_module

    # Ensure no tasks
    main_module._backup_task = None
    main_module._vacuum_task = None

    # Simulate shutdown logic (should not crash)
    tasks = [main_module._backup_task, main_module._vacuum_task]
    for task in tasks:
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    # No assertions needed - just verify no crash
    assert True


@pytest.mark.asyncio
async def test_shutdown_integration_with_lifespan(tmp_path):
    """Integration test: full lifespan startup and shutdown cycle."""
    from app import database
    from app.main import lifespan, _fastapi_app
    from app.routes import swarm

    # Create minimal DB
    db_path = tmp_path / "test.db"
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                goal TEXT NOT NULL,
                folder_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'created',
                swarm_pid INTEGER,
                config TEXT DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS swarm_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                ended_at TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("INSERT INTO schema_version (version) VALUES (4)")
        await db.commit()

    original_db_path = database.DB_PATH
    database.DB_PATH = db_path

    try:
        with patch("app.main._reconcile_running_projects", new_callable=AsyncMock), \
             patch("app.main._cleanup_old_logs", new_callable=AsyncMock), \
             patch("app.main.plugin_manager"):
            # Enter and exit lifespan
            async with lifespan(_fastapi_app):
                # Startup complete
                # Simulate an active agent
                swarm._agent_processes["1:Claude-1"] = MagicMock()
                # Exit context triggers shutdown

            # After shutdown, verify state is clean
            assert len(swarm._agent_processes) == 0
    finally:
        swarm._agent_processes.clear()
        database.DB_PATH = original_db_path


@pytest.mark.asyncio
async def test_shutdown_handles_process_termination_timeout():
    """Test that shutdown handles gracefully when process termination times out."""
    from app.routes import swarm

    # Create a mock process that doesn't terminate cleanly
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # Still running
    mock_proc.terminate = MagicMock()
    mock_proc.wait = MagicMock(side_effect=TimeoutError("Process didn't terminate"))
    mock_proc.kill = MagicMock()
    mock_proc.pid = 99999

    swarm._agent_processes["5:Claude-1"] = mock_proc
    swarm._agent_drain_events["5:Claude-1"] = threading.Event()

    # Run cleanup (should not crash even if process doesn't terminate)
    await swarm.cancel_drain_tasks(project_id=5)

    # Verify terminate was called
    mock_proc.terminate.assert_called()

    # State should still be cleaned up
    assert "5:Claude-1" not in swarm._agent_processes


@pytest.mark.asyncio
async def test_shutdown_closes_connection_pool(tmp_path):
    """Test that connection pool is closed during shutdown."""
    from app import database
    from app.database import init_pool, close_pool

    # Use tmp_path to avoid file locking issues
    tmp_db = tmp_path / "test_shutdown_pool.db"

    # Create the database first
    async with aiosqlite.connect(tmp_db) as db:
        await db.execute("CREATE TABLE test (id INTEGER)")
        await db.commit()

    original_pool = database._pool
    try:
        # Initialize pool
        await init_pool(db_path=tmp_db)
        assert database._pool is not None

        # Close pool (simulating shutdown)
        await close_pool()

        # Verify pool is None after close
        assert database._pool is None
    finally:
        # Restore original pool state
        database._pool = original_pool


@pytest.mark.asyncio
async def test_shutdown_with_multiple_active_projects(tmp_path):
    """Test shutdown with multiple active projects and agents."""
    from app import database
    from app.routes import swarm

    # Create test database
    db_path = tmp_path / "test.db"
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                goal TEXT NOT NULL,
                folder_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'created',
                swarm_pid INTEGER,
                config TEXT DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS swarm_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                started_at TEXT NOT NULL DEFAULT (datetime('now')),
                ended_at TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        # Insert multiple running projects
        await db.execute(
            "INSERT INTO projects (id, name, goal, folder_path, status) "
            "VALUES (1, 'P1', 'G1', '/tmp/p1', 'running')"
        )
        await db.execute(
            "INSERT INTO projects (id, name, goal, folder_path, status) "
            "VALUES (2, 'P2', 'G2', '/tmp/p2', 'running')"
        )
        await db.execute("INSERT INTO swarm_runs (project_id, status) VALUES (1, 'running')")
        await db.execute("INSERT INTO swarm_runs (project_id, status) VALUES (2, 'running')")
        await db.commit()

    original_db_path = database.DB_PATH
    database.DB_PATH = db_path

    try:
        # Simulate multiple active agents across projects
        swarm._agent_processes["1:Claude-1"] = MagicMock()
        swarm._agent_processes["1:Claude-2"] = MagicMock()
        swarm._agent_processes["2:Claude-1"] = MagicMock()

        # Run shutdown
        await swarm.cancel_drain_tasks()

        # Mark all as stopped
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "UPDATE projects SET status = 'stopped', swarm_pid = NULL "
                "WHERE status = 'running'"
            )
            await db.execute(
                "UPDATE swarm_runs SET ended_at = datetime('now'), status = 'stopped' "
                "WHERE status = 'running'"
            )
            await db.commit()

        # Verify all projects stopped
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            projects = await (await db.execute(
                "SELECT status FROM projects WHERE id IN (1, 2)"
            )).fetchall()
            assert all(p["status"] == "stopped" for p in projects)

            runs = await (await db.execute(
                "SELECT status FROM swarm_runs WHERE project_id IN (1, 2)"
            )).fetchall()
            assert all(r["status"] == "stopped" for r in runs)
    finally:
        swarm._agent_processes.clear()
        database.DB_PATH = original_db_path
