"""Tests for process reconciliation on startup.

Tests _reconcile_running_projects(): dead PID cleanup, alive PID detection,
orphaned swarm_run closure.
"""

import pytest
import aiosqlite
from unittest.mock import patch


class TestReconcileDeadPID:
    """When a project has status='running' but the PID is dead."""

    async def test_dead_pid_marked_stopped(self, tmp_db):
        """Project with dead PID should be marked as stopped."""
        from app import database
        from app.main import _reconcile_running_projects

        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        try:
            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, status, swarm_pid) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("Dead PID Project", "test", "/tmp/test", "running", 999999),
                )
                await db.commit()

            with patch("app.main._pid_alive", return_value=False):
                await _reconcile_running_projects()

            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                row = await (await db.execute("SELECT * FROM projects WHERE id = 1")).fetchone()
                assert dict(row)["status"] == "stopped"
                assert dict(row)["swarm_pid"] is None
        finally:
            database.DB_PATH = original_db_path

    async def test_dead_pid_closes_orphaned_runs(self, tmp_db):
        """Orphaned swarm_runs should be marked as crashed."""
        from app import database
        from app.main import _reconcile_running_projects

        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        try:
            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, status, swarm_pid) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("Orphan Run Project", "test", "/tmp/test", "running", 999999),
                )
                await db.execute(
                    "INSERT INTO swarm_runs (project_id, status) VALUES (?, ?)",
                    (1, "running"),
                )
                await db.commit()

            with patch("app.main._pid_alive", return_value=False):
                await _reconcile_running_projects()

            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                run = await (await db.execute("SELECT * FROM swarm_runs WHERE id = 1")).fetchone()
                run_dict = dict(run)
                assert run_dict["status"] == "crashed"
                assert run_dict["ended_at"] is not None
        finally:
            database.DB_PATH = original_db_path


class TestReconcileAlivePID:
    """When a project has status='running' and the PID is alive."""

    async def test_alive_pid_stays_running(self, tmp_db):
        """Project with alive PID should remain running."""
        from app import database
        from app.main import _reconcile_running_projects

        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        try:
            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, status, swarm_pid) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("Alive PID Project", "test", "/tmp/test", "running", 12345),
                )
                await db.commit()

            with patch("app.main._pid_alive", return_value=True):
                await _reconcile_running_projects()

            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                row = await (await db.execute("SELECT * FROM projects WHERE id = 1")).fetchone()
                assert dict(row)["status"] == "running"
                assert dict(row)["swarm_pid"] == 12345
        finally:
            database.DB_PATH = original_db_path

    async def test_alive_pid_keeps_runs_open(self, tmp_db):
        """Running swarm_runs should stay running when PID is alive."""
        from app import database
        from app.main import _reconcile_running_projects

        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        try:
            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, status, swarm_pid) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("Alive Run Project", "test", "/tmp/test", "running", 12345),
                )
                await db.execute(
                    "INSERT INTO swarm_runs (project_id, status) VALUES (?, ?)",
                    (1, "running"),
                )
                await db.commit()

            with patch("app.main._pid_alive", return_value=True):
                await _reconcile_running_projects()

            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                run = await (await db.execute("SELECT * FROM swarm_runs WHERE id = 1")).fetchone()
                assert dict(run)["status"] == "running"
                assert dict(run)["ended_at"] is None
        finally:
            database.DB_PATH = original_db_path


class TestReconcileNoRunning:
    """When no projects are marked as running."""

    async def test_no_running_projects_is_noop(self, tmp_db):
        """Reconciliation with no running projects should be a no-op."""
        from app import database
        from app.main import _reconcile_running_projects

        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        try:
            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, status) "
                    "VALUES (?, ?, ?, ?)",
                    ("Stopped Project", "test", "/tmp/test", "stopped"),
                )
                await db.commit()

            await _reconcile_running_projects()

            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                row = await (await db.execute("SELECT * FROM projects WHERE id = 1")).fetchone()
                assert dict(row)["status"] == "stopped"
        finally:
            database.DB_PATH = original_db_path


class TestReconcileMultipleProjects:
    """Multiple projects with mixed PID states."""

    async def test_mixed_alive_and_dead(self, tmp_db):
        """Reconcile correctly handles mix of alive and dead PIDs."""
        from app import database
        from app.main import _reconcile_running_projects

        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        try:
            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                # Project 1: dead PID
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, status, swarm_pid) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("Dead Project", "test", "/tmp/dead", "running", 999999),
                )
                # Project 2: alive PID
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, status, swarm_pid) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("Alive Project", "test", "/tmp/alive", "running", 11111),
                )
                await db.commit()

            def mock_pid_alive(pid):
                return pid == 11111

            with patch("app.main._pid_alive", side_effect=mock_pid_alive):
                await _reconcile_running_projects()

            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                dead = await (await db.execute("SELECT * FROM projects WHERE id = 1")).fetchone()
                alive = await (await db.execute("SELECT * FROM projects WHERE id = 2")).fetchone()
                assert dict(dead)["status"] == "stopped"
                assert dict(dead)["swarm_pid"] is None
                assert dict(alive)["status"] == "running"
                assert dict(alive)["swarm_pid"] == 11111
        finally:
            database.DB_PATH = original_db_path


class TestReconcileEdgeCases:
    """Edge cases for process reconciliation."""

    async def test_null_swarm_pid_marked_stopped(self, tmp_db):
        """Project with status='running' but NULL swarm_pid gets stopped."""
        from app import database
        from app.main import _reconcile_running_projects

        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        try:
            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, status, swarm_pid) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("Null PID Project", "test", "/tmp/test", "running", None),
                )
                await db.commit()

            await _reconcile_running_projects()

            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                row = await (await db.execute("SELECT * FROM projects WHERE id = 1")).fetchone()
                assert dict(row)["status"] == "stopped"
                assert dict(row)["swarm_pid"] is None
        finally:
            database.DB_PATH = original_db_path

    async def test_multiple_orphaned_runs_all_closed(self, tmp_db):
        """All running swarm_runs for a dead PID should be marked crashed."""
        from app import database
        from app.main import _reconcile_running_projects

        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        try:
            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, status, swarm_pid) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("Multi Run Project", "test", "/tmp/test", "running", 999999),
                )
                # Create 3 orphaned running runs
                for _ in range(3):
                    await db.execute(
                        "INSERT INTO swarm_runs (project_id, status) VALUES (?, ?)",
                        (1, "running"),
                    )
                await db.commit()

            with patch("app.main._pid_alive", return_value=False):
                await _reconcile_running_projects()

            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                runs = await (await db.execute(
                    "SELECT * FROM swarm_runs WHERE project_id = 1"
                )).fetchall()
                assert len(runs) == 3
                for run in runs:
                    assert dict(run)["status"] == "crashed"
                    assert dict(run)["ended_at"] is not None
        finally:
            database.DB_PATH = original_db_path

    async def test_pid_alive_exception_marks_stopped(self, tmp_db):
        """If _pid_alive raises, project should be treated as dead."""
        from app import database
        from app.main import _reconcile_running_projects

        original_db_path = database.DB_PATH
        database.DB_PATH = tmp_db

        try:
            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                await db.execute(
                    "INSERT INTO projects (name, goal, folder_path, status, swarm_pid) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("Error PID Project", "test", "/tmp/test", "running", 12345),
                )
                await db.commit()

            with patch("app.main._pid_alive", side_effect=OSError("Permission denied")):
                await _reconcile_running_projects()

            async with aiosqlite.connect(tmp_db) as db:
                db.row_factory = aiosqlite.Row
                row = await (await db.execute("SELECT * FROM projects WHERE id = 1")).fetchone()
                # When _pid_alive throws, the except block logs and treats as dead
                assert dict(row)["status"] == "stopped"
        finally:
            database.DB_PATH = original_db_path
