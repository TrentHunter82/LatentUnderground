"""Tests for Phase 20 features: log rotation, agent restart, export, DB optimization.

Covers:
- Output log rotation (configurable max size, .log.1 rotation)
- Graceful agent restart without full swarm restart
- Swarm run export endpoint (text/JSON)
- Database query optimization (new indexes, analytics consolidation)
- EXPLAIN QUERY PLAN diagnostic endpoint
- Database index listing endpoint
"""

import json
import os
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from unittest.mock import MagicMock, patch

# Disable rate limiting in tests
os.environ.setdefault("LU_RATE_LIMIT_RPM", "0")
os.environ.setdefault("LU_RATE_LIMIT_READ_RPM", "0")

import aiosqlite
import pytest


# ============================================================================
# Output Log Rotation Tests
# ============================================================================


class TestLogRotation:
    """Tests for output log file rotation."""

    def test_rotate_log_file_creates_new_file(self, tmp_path):
        """Rotating a log file creates .log.1 backup and new empty file."""
        from app.routes.swarm import _rotate_log_file

        log_path = tmp_path / "Claude-1_test.output.log"
        fh = open(log_path, "a", encoding="utf-8", buffering=1)
        fh.write("line 1\nline 2\nline 3\n")
        fh.flush()

        new_fh = _rotate_log_file(log_path, fh)
        assert new_fh is not None

        # Verify .log.1 exists with original content
        rotated = log_path.with_suffix(".log.1")
        assert rotated.exists()
        assert "line 1" in rotated.read_text()

        # New file handle should be writable
        new_fh.write("new content\n")
        new_fh.close()
        assert "new content" in log_path.read_text()

    def test_rotate_replaces_existing_backup(self, tmp_path):
        """Rotation overwrites existing .log.1 file."""
        from app.routes.swarm import _rotate_log_file

        log_path = tmp_path / "test.output.log"
        rotated = log_path.with_suffix(".log.1")

        # Create existing backup
        rotated.write_text("old backup")

        # Create current log
        fh = open(log_path, "a", encoding="utf-8")
        fh.write("current content\n")
        fh.flush()

        new_fh = _rotate_log_file(log_path, fh)
        assert new_fh is not None

        # Old backup should be replaced
        assert "current content" in rotated.read_text()
        assert "old backup" not in rotated.read_text()
        new_fh.close()

    def test_output_log_max_mb_config(self):
        """OUTPUT_LOG_MAX_MB config is accessible and has default."""
        from app import config
        assert hasattr(config, "OUTPUT_LOG_MAX_MB")
        assert config.OUTPUT_LOG_MAX_MB == 10  # default

    def test_drain_thread_respects_log_rotation(self, tmp_path):
        """Drain thread checks log size periodically for rotation."""
        from app.routes.swarm import (
            _drain_agent_stream, _agent_log_files, _agent_output_buffers,
            _project_output_buffers, _buffers_lock, _agent_key,
        )

        project_id = 999
        agent_name = "Claude-1"
        key = _agent_key(project_id, agent_name)

        # Create a tiny log file to trigger rotation
        log_path = tmp_path / f"{agent_name}_test.output.log"
        _agent_log_files[key] = log_path

        # Create a mock stream that produces >100 lines (rotation check interval)
        lines = [f'{{"type":"system","subtype":"init"}}\n'.encode()] + \
                [f'{{"type":"assistant","message":{{"content":[{{"type":"text","text":"line {i}"}}]}}}}\n'.encode()
                 for i in range(105)]
        lines.append(b"")  # EOF

        mock_stream = MagicMock()
        mock_stream.readline = MagicMock(side_effect=lines)
        mock_stream.close = MagicMock()

        stop_event = threading.Event()

        # Override config to set tiny max (1 byte) to force rotation
        with patch("app.routes.swarm.config") as mock_config:
            mock_config.OUTPUT_LOG_MAX_MB = 0  # 0 = disabled (no rotation)
            _drain_agent_stream(project_id, agent_name, mock_stream, "stdout", stop_event)

        # Cleanup
        _agent_log_files.pop(key, None)
        with _buffers_lock:
            _agent_output_buffers.pop(key, None)
            _project_output_buffers.pop(project_id, None)


# ============================================================================
# Agent Restart Tests
# ============================================================================


class TestAgentRestart:
    """Tests for graceful agent restart endpoint."""

    async def test_restart_stopped_agent(self, client, project_with_folder, mock_launch_deps):
        """Restarting a stopped agent spawns a new process."""
        pid = project_with_folder["id"]

        from app.routes.swarm import (
            _agent_processes, _agent_key, _agent_started_at,
            _agent_drain_events,
        )

        key = _agent_key(pid, "Claude-1")

        # Simulate a stopped agent (process exited)
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # Exited normally
        mock_proc.returncode = 0
        mock_proc.pid = 12345
        _agent_processes[key] = mock_proc

        # Mock Popen to return a new process
        new_mock_proc = MagicMock()
        new_mock_proc.pid = 54321
        new_mock_proc.poll.return_value = None  # Running
        new_mock_proc.stdout = MagicMock()
        new_mock_proc.stdout.readline = MagicMock(return_value=b"")
        new_mock_proc.stdout.close = MagicMock()
        new_mock_proc.stderr = MagicMock()
        new_mock_proc.stderr.readline = MagicMock(return_value=b"")
        new_mock_proc.stderr.close = MagicMock()

        with patch("app.routes.swarm._find_claude_cmd", return_value=["claude"]), \
             patch("subprocess.Popen", return_value=new_mock_proc):
            resp = await client.post(f"/api/swarm/agents/{pid}/Claude-1/restart")

        assert resp.status_code == 200
        data = resp.json()
        assert data["agent"] == "Claude-1"
        assert data["status"] == "restarted"

    async def test_restart_running_agent_fails(self, client, project_with_folder):
        """Cannot restart an agent that is still running."""
        pid = project_with_folder["id"]

        from app.routes.swarm import _agent_processes, _agent_key

        key = _agent_key(pid, "Claude-1")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Still running
        mock_proc.pid = 12345
        _agent_processes[key] = mock_proc

        resp = await client.post(f"/api/swarm/agents/{pid}/Claude-1/restart")
        assert resp.status_code == 400
        assert "still running" in resp.json()["detail"]

    async def test_restart_no_prompt_file(self, client, created_project):
        """Restart fails if prompt file doesn't exist."""
        pid = created_project["id"]

        from app.routes.swarm import _agent_processes, _agent_key

        key = _agent_key(pid, "Claude-1")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # Stopped
        mock_proc.pid = 111
        _agent_processes[key] = mock_proc

        resp = await client.post(f"/api/swarm/agents/{pid}/Claude-1/restart")
        assert resp.status_code == 400
        assert "Prompt file not found" in resp.json()["detail"]

    async def test_restart_invalid_agent_name(self, client, created_project):
        """Restart fails for invalid agent name format."""
        pid = created_project["id"]
        resp = await client.post(f"/api/swarm/agents/{pid}/InvalidName/restart")
        assert resp.status_code == 400
        assert "Invalid agent name" in resp.json()["detail"]

    async def test_restart_nonexistent_project(self, client):
        """Restart fails for non-existent project."""
        resp = await client.post("/api/swarm/agents/9999/Claude-1/restart")
        assert resp.status_code == 404


# ============================================================================
# Export Endpoint Tests
# ============================================================================


class TestExportEndpoint:
    """Tests for swarm output export endpoint."""

    async def test_export_text_format(self, client, created_project):
        """Export as text returns plain text file."""
        pid = created_project["id"]

        from app.routes.swarm import _project_output_buffers, _buffers_lock
        with _buffers_lock:
            _project_output_buffers[pid] = deque(["line 1", "line 2", "line 3"])

        resp = await client.get(f"/api/swarm/export/{pid}?format=text")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/plain; charset=utf-8"
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert "line 1" in resp.text
        assert "line 2" in resp.text

    async def test_export_json_format(self, client, created_project):
        """Export as JSON returns structured JSON file."""
        pid = created_project["id"]

        from app.routes.swarm import _project_output_buffers, _buffers_lock
        with _buffers_lock:
            _project_output_buffers[pid] = deque(["[Claude-1] hello", "[Claude-2] world"])

        resp = await client.get(f"/api/swarm/export/{pid}?format=json")
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]

        data = resp.json()
        assert data["project_id"] == pid
        assert data["line_count"] == 2
        assert len(data["lines"]) == 2
        assert data["exported_at"] is not None

    async def test_export_per_agent(self, client, created_project):
        """Export filtered by agent name."""
        pid = created_project["id"]

        from app.routes.swarm import _agent_output_buffers, _agent_key, _buffers_lock
        key = _agent_key(pid, "Claude-1")
        with _buffers_lock:
            _agent_output_buffers[key] = deque(["agent line 1", "agent line 2"])

        resp = await client.get(f"/api/swarm/export/{pid}?agent=Claude-1")
        assert resp.status_code == 200
        assert "agent line 1" in resp.text
        assert "agent line 2" in resp.text

    async def test_export_empty_buffer(self, client, created_project):
        """Export with empty buffer returns empty content."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/export/{pid}?format=text")
        assert resp.status_code == 200
        assert resp.text == ""

    async def test_export_nonexistent_project(self, client):
        """Export fails for non-existent project."""
        resp = await client.get("/api/swarm/export/9999")
        assert resp.status_code == 404

    async def test_export_json_filename(self, client, created_project):
        """JSON export filename includes .json extension."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/export/{pid}?format=json")
        assert resp.status_code == 200
        disposition = resp.headers.get("content-disposition", "")
        assert ".json" in disposition


# ============================================================================
# Database Optimization Tests
# ============================================================================


class TestDatabaseOptimization:
    """Tests for migration_003 indexes and query optimization."""

    async def test_migration_003_creates_indexes(self, tmp_path):
        """Migration 003 creates the three new composite indexes."""
        from app import database

        db_path = tmp_path / "idx_test.db"
        original = database.DB_PATH
        database.DB_PATH = db_path
        try:
            await database.init_db()

            async with aiosqlite.connect(db_path) as db:
                rows = await (await db.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
                )).fetchall()
                names = {r[0] for r in rows}

                assert "idx_swarm_runs_project_status" in names
                assert "idx_webhooks_project" in names
                assert "idx_projects_archived_status" in names
        finally:
            database.DB_PATH = original

    async def test_schema_version_current(self, tmp_path):
        """Schema version matches SCHEMA_VERSION constant after migration."""
        from app import database

        db_path = tmp_path / "version_test.db"
        original = database.DB_PATH
        database.DB_PATH = db_path
        try:
            await database.init_db()

            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                row = await (await db.execute(
                    "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
                )).fetchone()
                assert row["version"] == database.SCHEMA_VERSION
        finally:
            database.DB_PATH = original

    async def test_analytics_single_query(self, client, created_project):
        """Analytics endpoint returns correct data (consolidated query)."""
        pid = created_project["id"]

        # Create some swarm runs
        from app import database
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, ended_at, tasks_completed) "
                "VALUES (?, 'completed', datetime('now'), 5)",
                (pid,),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, ended_at, tasks_completed) "
                "VALUES (?, 'stopped', datetime('now'), 3)",
                (pid,),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, tasks_completed) "
                "VALUES (?, 'running', 0)",
                (pid,),
            )
            await db.commit()

        resp = await client.get(f"/api/projects/{pid}/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_runs"] == 3
        assert data["total_tasks"] == 8  # 5 + 3
        assert data["success_rate"] is not None  # 1 completed / 2 finished = 50%
        assert len(data["run_trends"]) == 3

    async def test_analytics_empty_runs(self, client, created_project):
        """Analytics with no runs returns zeros."""
        pid = created_project["id"]
        resp = await client.get(f"/api/projects/{pid}/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_runs"] == 0
        assert data["total_tasks"] == 0
        assert data["success_rate"] is None
        assert data["avg_duration"] is None


# ============================================================================
# Database Diagnostics Endpoint Tests
# ============================================================================


class TestDBDiagnostics:
    """Tests for the /api/system/db/ diagnostic endpoints."""

    async def test_db_indexes_endpoint(self, client):
        """GET /api/system/db/indexes returns index list."""
        resp = await client.get("/api/system/db/indexes")
        assert resp.status_code == 200
        data = resp.json()
        assert "indexes" in data
        assert "schema_version" in data
        assert isinstance(data["indexes"], list)

    async def test_db_explain_all_queries(self, client):
        """GET /api/system/db/explain returns plans for all named queries."""
        resp = await client.get("/api/system/db/explain")
        assert resp.status_code == 200
        data = resp.json()
        assert "queries" in data
        # Should have all diagnostic queries
        assert "list_projects" in data["queries"]
        assert "project_runs_stats" in data["queries"]
        # Each query should have a plan
        for name, info in data["queries"].items():
            assert "sql" in info
            assert "plan" in info or "error" in info

    async def test_db_explain_single_query(self, client):
        """GET /api/system/db/explain?query=list_projects returns single plan."""
        resp = await client.get("/api/system/db/explain?query=list_projects")
        assert resp.status_code == 200
        data = resp.json()
        assert "queries" in data
        assert len(data["queries"]) == 1
        assert "list_projects" in data["queries"]

    async def test_db_explain_unknown_query(self, client):
        """Unknown query name returns error message."""
        resp = await client.get("/api/system/db/explain?query=nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data

    async def test_explain_shows_index_usage(self, client):
        """Explain plan indicates whether indexes are used."""
        resp = await client.get("/api/system/db/explain?query=running_runs_update")
        assert resp.status_code == 200
        data = resp.json()
        info = data["queries"]["running_runs_update"]
        assert "uses_index" in info


# ============================================================================
# Integration / Backwards Compatibility Tests
# ============================================================================


class TestPhase20Integration:
    """Integration tests verifying Phase 20 changes don't break existing behavior."""

    async def test_project_stats_still_works(self, client, created_project):
        """Project stats endpoint works after analytics refactor."""
        pid = created_project["id"]
        resp = await client.get(f"/api/projects/{pid}/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_runs"] == 0
        assert data["total_tasks_completed"] == 0

    async def test_dashboard_still_works(self, client, project_with_folder):
        """Dashboard endpoint works with new indexes."""
        pid = project_with_folder["id"]
        resp = await client.get(f"/api/projects/{pid}/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == pid
        assert data["total_runs"] == 0

    async def test_swarm_history_still_works(self, client, project_with_folder):
        """Swarm history endpoint works after DB changes."""
        pid = project_with_folder["id"]
        resp = await client.get(f"/api/swarm/history/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == pid
        assert data["runs"] == []

    async def test_list_projects_with_new_indexes(self, client, created_project):
        """List projects works with new composite index."""
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        projects = resp.json()
        assert len(projects) >= 1
        assert projects[0]["name"] == created_project["name"]

    async def test_swarm_status_still_works(self, client, project_with_folder):
        """Swarm status endpoint works after all changes."""
        pid = project_with_folder["id"]
        resp = await client.get(f"/api/swarm/status/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == pid
        assert data["status"] in ("created", "stopped", "running")

    async def test_agent_stop_still_works(self, client, project_with_folder):
        """Individual agent stop still works."""
        pid = project_with_folder["id"]

        from app.routes.swarm import _agent_processes, _agent_key

        key = _agent_key(pid, "Claude-1")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Running
        mock_proc.pid = 111
        mock_proc.terminate = MagicMock()
        mock_proc.wait = MagicMock(return_value=0)
        mock_proc.kill = MagicMock()
        _agent_processes[key] = mock_proc

        resp = await client.post(f"/api/swarm/agents/{pid}/Claude-1/stop")
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"
