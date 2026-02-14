"""Tests for production hardening changes: file size limit, logging, drain thread tracking."""

import logging
import subprocess
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestFileSizeLimit:
    """Tests for file content size limit (413)."""

    async def test_write_within_limit(self, client, project_with_folder):
        pid = project_with_folder["id"]
        resp = await client.put(
            "/api/files/tasks/TASKS.md",
            json={"content": "small content", "project_id": pid},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "written"

    async def test_write_exceeds_limit(self, client, project_with_folder):
        pid = project_with_folder["id"]
        huge_content = "x" * 1_000_001
        resp = await client.put(
            "/api/files/tasks/TASKS.md",
            json={"content": huge_content, "project_id": pid},
        )
        assert resp.status_code == 413
        assert "Content too large" in resp.json()["detail"]

    async def test_write_at_exact_limit(self, client, project_with_folder):
        pid = project_with_folder["id"]
        content = "x" * 1_000_000
        resp = await client.put(
            "/api/files/tasks/TASKS.md",
            json={"content": content, "project_id": pid},
        )
        assert resp.status_code == 200


class TestLogging:
    """Tests for structured logging output."""

    async def test_swarm_launch_logs(self, client, mock_project_folder, mock_launch_deps, caplog):
        (mock_project_folder / "swarm.ps1").write_text("# Mock")
        resp = await client.post("/api/projects", json={
            "name": "Log Test",
            "goal": "Test logging",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 99999
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_popen.return_value = mock_process

            with caplog.at_level(logging.INFO, logger="latent.swarm"):
                await client.post("/api/swarm/launch", json={"project_id": pid})

            assert any("Swarm launched" in r.message for r in caplog.records)

    async def test_swarm_stop_logs(self, client, tmp_path, caplog):
        folder = tmp_path / "log_stop_test"
        folder.mkdir()
        resp = await client.post("/api/projects", json={
            "name": "Stop Log",
            "goal": "Test stop logging",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with caplog.at_level(logging.INFO, logger="latent.swarm"):
            await client.post("/api/swarm/stop", json={"project_id": pid})

        assert any("Swarm stopped" in r.message for r in caplog.records)

    async def test_file_write_logs(self, client, project_with_folder, caplog):
        pid = project_with_folder["id"]
        with caplog.at_level(logging.INFO, logger="latent.files"):
            await client.put(
                "/api/files/tasks/TASKS.md",
                json={"content": "logged write", "project_id": pid},
            )
        assert any("File written" in r.message for r in caplog.records)

    async def test_stale_pid_warning(self, client, mock_project_folder, caplog):
        resp = await client.post("/api/projects", json={
            "name": "Stale PID",
            "goal": "Test stale PID",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        from app import database
        import aiosqlite
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE projects SET status = 'running', swarm_pid = 99999 WHERE id = ?",
                (pid,),
            )
            await db.commit()

        with caplog.at_level(logging.WARNING, logger="latent.swarm"):
            await client.get(f"/api/swarm/status/{pid}")

        assert any("No live agents" in r.message or "auto-correcting" in r.message for r in caplog.records)


class TestDrainThreadTracking:
    """Tests for per-agent drain thread tracking and cancellation."""

    async def test_agent_drain_events_cleaned_on_stop(self, client, created_project):
        """Agent drain events are cleaned up when stop is called."""
        from app.routes.swarm import (
            _agent_drain_events, _agent_processes, _agent_key,
            _cleanup_project_agents,
        )
        pid = created_project["id"]
        key = _agent_key(pid, "Claude-1")
        _agent_drain_events[key] = threading.Event()
        _agent_processes[key] = MagicMock(poll=MagicMock(return_value=0))  # already exited

        _cleanup_project_agents(pid)

        assert key not in _agent_drain_events
        assert key not in _agent_processes

    async def test_cancel_all_drain_tasks(self):
        """cancel_drain_tasks(None) cleans up all projects."""
        from app.routes.swarm import (
            _agent_drain_events, _agent_processes, _agent_key,
            cancel_drain_tasks,
        )

        evt1 = threading.Event()
        evt2 = threading.Event()
        key1 = _agent_key(100, "Claude-1")
        key2 = _agent_key(200, "Claude-1")
        _agent_drain_events[key1] = evt1
        _agent_drain_events[key2] = evt2
        _agent_processes[key1] = MagicMock(poll=MagicMock(return_value=0))
        _agent_processes[key2] = MagicMock(poll=MagicMock(return_value=0))

        await cancel_drain_tasks()

        assert evt1.is_set()
        assert evt2.is_set()
        assert len(_agent_drain_events) == 0
        assert len(_agent_processes) == 0

    async def test_cleanup_terminates_alive_process(self):
        """Cleanup should terminate processes that are still alive."""
        from app.routes.swarm import (
            _agent_processes, _agent_key, _cleanup_project_agents,
        )

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Still alive
        mock_proc.wait.return_value = 0
        key = _agent_key(999, "Claude-1")
        _agent_processes[key] = mock_proc

        _cleanup_project_agents(999)

        mock_proc.terminate.assert_called_once()
        assert key not in _agent_processes


class TestStopEndpoint:
    """Tests for POST /api/swarm/stop."""

    async def test_stop_returns_200(self, client, created_project):
        """Stop endpoint returns 200 and updates DB status."""
        pid = created_project["id"]
        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"

    async def test_stop_cleans_up_agents(self, client, created_project):
        """Stop endpoint cleans up per-agent tracking data."""
        from app.routes.swarm import (
            _agent_processes, _agent_key, _project_output_buffers,
        )
        pid = created_project["id"]
        key = _agent_key(pid, "Claude-1")
        _agent_processes[key] = MagicMock(poll=MagicMock(return_value=0))
        _project_output_buffers[pid] = ["test"]

        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert resp.status_code == 200
        assert key not in _agent_processes
        assert pid not in _project_output_buffers
