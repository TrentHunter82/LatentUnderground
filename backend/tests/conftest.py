"""Test fixtures for Latent Underground backend tests."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# Disable rate limiting in tests (must be set before app imports)
os.environ.setdefault("LU_RATE_LIMIT_RPM", "0")
os.environ.setdefault("LU_RATE_LIMIT_READ_RPM", "0")

import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture()
async def tmp_db(tmp_path):
    """Create a temporary SQLite database for testing."""
    db_path = tmp_path / "test.db"
    async with aiosqlite.connect(db_path) as db:
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
                label TEXT,
                notes TEXT,
                summary TEXT,
                guardrail_results TEXT,
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
        await db.commit()
    return db_path


@pytest.fixture()
async def app(tmp_db, tmp_path):
    """Create a FastAPI test app with test database."""
    from app import database
    from app.routes.files import _last_write
    from app.routes.swarm import (
        _project_output_buffers, _agent_processes, _agent_output_buffers,
        _agent_drain_threads, _agent_drain_events, _agent_started_at,
        _agent_log_files, _last_output_at, _project_locks, _agent_line_counts,
        _known_directives, _project_resource_usage, cancel_drain_tasks,
        _checkpoint_batch, _checkpoint_batch_lock, _checkpoint_cooldowns,
        _current_run_ids, _circuit_breakers, _supervisor_tasks,
    )

    original_db_path = database.DB_PATH
    database.DB_PATH = tmp_db

    # Clear rate limiter state between tests
    _last_write.clear()
    # Clear output buffers and tracking state from previous tests
    _project_output_buffers.clear()
    _agent_output_buffers.clear()
    _last_output_at.clear()

    try:
        from app.main import app as _app
    except (ImportError, ModuleNotFoundError):
        from fastapi import FastAPI
        from app.routes.projects import router as projects_router

        _app = FastAPI(title="Latent Underground Test")
        _app.include_router(projects_router)

    yield _app

    # Stop any drain threads and clear all module-level state on teardown
    await cancel_drain_tasks()
    _project_output_buffers.clear()
    _agent_output_buffers.clear()
    _agent_processes.clear()
    _agent_drain_threads.clear()
    _agent_drain_events.clear()
    _agent_started_at.clear()
    _agent_log_files.clear()
    _last_output_at.clear()
    _project_locks.clear()
    _agent_line_counts.clear()
    _known_directives.clear()
    _project_resource_usage.clear()
    _checkpoint_cooldowns.clear()
    _current_run_ids.clear()
    _circuit_breakers.clear()
    # Cancel any lingering supervisor tasks
    for task in _supervisor_tasks.values():
        task.cancel()
    _supervisor_tasks.clear()
    with _checkpoint_batch_lock:
        _checkpoint_batch.clear()
    database.DB_PATH = original_db_path


@pytest.fixture()
async def client(app):
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture()
def sample_project_data(tmp_path):
    """Return sample project creation data."""
    return {
        "name": "Test Swarm Project",
        "goal": "Build a test application",
        "project_type": "Web Application (frontend + backend)",
        "tech_stack": "Python FastAPI, React",
        "complexity": "Medium",
        "requirements": "Must have tests",
        "folder_path": str(tmp_path / "TestProject").replace("\\", "/"),
    }


@pytest.fixture()
def sample_project_minimal(tmp_path):
    """Return minimal project creation data (only required fields)."""
    return {
        "name": "Minimal Project",
        "goal": "Test minimal creation",
        "folder_path": str(tmp_path / "MinimalProject").replace("\\", "/"),
    }


@pytest.fixture()
async def created_project(client, sample_project_data):
    """Create and return a project (for tests that need an existing project)."""
    resp = await client.post("/api/projects", json=sample_project_data)
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture()
def mock_project_folder(tmp_path):
    """Create a mock project folder with swarm structure."""
    folder = tmp_path / "mock_project"
    folder.mkdir()

    # Create .claude directory structure
    claude_dir = folder / ".claude"
    claude_dir.mkdir()
    (claude_dir / "heartbeats").mkdir()
    (claude_dir / "signals").mkdir()

    # Create heartbeat files
    (claude_dir / "heartbeats" / "Claude-1.heartbeat").write_text("2026-02-06 14:00:00")
    (claude_dir / "heartbeats" / "Claude-2.heartbeat").write_text("2026-02-06 14:00:01")

    # Create a signal
    (claude_dir / "signals" / "backend-ready.signal").write_text("")

    # Create swarm-phase.json
    (claude_dir / "swarm-phase.json").write_text(json.dumps({
        "Phase": 1, "MaxPhases": 3, "StartedAt": "2026-02-06 13:53:02"
    }))

    # Create tasks directory with TASKS.md
    tasks_dir = folder / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "TASKS.md").write_text(
        "# Tasks\n- [x] Task 1\n- [x] Task 2\n- [ ] Task 3\n- [ ] Task 4\n"
    )
    (tasks_dir / "lessons.md").write_text("# Lessons\n")
    (tasks_dir / "todo.md").write_text("# Todo\n")

    # Create logs directory
    logs_dir = folder / "logs"
    logs_dir.mkdir()
    (logs_dir / "Claude-1.log").write_text("Line 1\nLine 2\nLine 3\n")
    (logs_dir / "Claude-2.log").write_text("Starting work\n")

    # Create prompt files (used by per-agent launch flow)
    prompts_dir = claude_dir / "prompts"
    prompts_dir.mkdir()
    for i in range(1, 5):
        (prompts_dir / f"Claude-{i}.txt").write_text(f"Mock prompt for Claude-{i}")

    # Create handoffs dir
    (claude_dir / "handoffs").mkdir(exist_ok=True)

    # Create AGENTS.md and progress.txt
    (folder / "AGENTS.md").write_text("# Agents\n")
    (folder / "progress.txt").write_text("Progress log\n")

    return folder


@pytest.fixture()
async def project_with_folder(client, mock_project_folder):
    """Create a project pointing to the mock project folder."""
    resp = await client.post("/api/projects", json={
        "name": "Mock Swarm Project",
        "goal": "Test with real folder",
        "folder_path": str(mock_project_folder).replace("\\", "/"),
    })
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture()
def mock_launch_deps():
    """Patches _run_setup_only and _find_claude_cmd for swarm launch tests.

    The mock _run_setup_only creates prompt files in .claude/prompts/ as the
    real swarm.ps1 -SetupOnly would. Tests still need to mock subprocess.Popen
    for the actual agent processes.
    """
    def setup_side_effect(folder, swarm_script, agent_count, max_phases):
        prompts_dir = folder / ".claude" / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        for i in range(1, agent_count + 1):
            pf = prompts_dir / f"Claude-{i}.txt"
            if not pf.exists():
                pf.write_text(f"Mock prompt for Claude-{i}")
        result = MagicMock()
        result.returncode = 0
        result.stdout = "Setup complete"
        result.stderr = ""
        return result

    with patch("app.routes.swarm._run_setup_only", side_effect=setup_side_effect), \
         patch("app.routes.swarm._find_claude_cmd", return_value=["claude.cmd"]):
        yield
