"""Tests for production hardening changes: file size limit, logging, drain task tracking."""

import asyncio
import logging
from unittest.mock import AsyncMock, patch

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

    async def test_swarm_launch_logs(self, client, mock_project_folder, caplog):
        (mock_project_folder / "swarm.ps1").write_text("# Mock")
        resp = await client.post("/api/projects", json={
            "name": "Log Test",
            "goal": "Test logging",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_process = AsyncMock()
            mock_process.pid = 99999
            mock_exec.return_value = mock_process

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

        assert any("Stale PID" in r.message for r in caplog.records)


class TestDrainTaskTracking:
    """Tests for background drain task tracking and cancellation."""

    async def test_drain_tasks_tracked_on_launch(self, client, mock_project_folder):
        from app.routes.swarm import _drain_tasks

        (mock_project_folder / "swarm.ps1").write_text("# Mock")
        resp = await client.post("/api/projects", json={
            "name": "Drain Track",
            "goal": "Test drain tracking",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_process = AsyncMock()
            mock_process.pid = 11111
            mock_exec.return_value = mock_process

            await client.post("/api/swarm/launch", json={"project_id": pid})

        assert pid in _drain_tasks
        assert len(_drain_tasks[pid]) == 2

        for t in _drain_tasks.pop(pid, []):
            t.cancel()

    async def test_drain_tasks_cancelled_on_stop(self, client, mock_project_folder):
        from app.routes.swarm import _drain_tasks

        (mock_project_folder / "swarm.ps1").write_text("# Mock")
        resp = await client.post("/api/projects", json={
            "name": "Drain Cancel",
            "goal": "Test drain cancel",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_process = AsyncMock()
            mock_process.pid = 22222
            mock_process.wait = AsyncMock()
            mock_exec.return_value = mock_process

            await client.post("/api/swarm/launch", json={"project_id": pid})
            assert pid in _drain_tasks

            await client.post("/api/swarm/stop", json={"project_id": pid})

        assert pid not in _drain_tasks

    async def test_cancel_all_drain_tasks(self):
        from app.routes.swarm import _drain_tasks, cancel_drain_tasks

        task1 = AsyncMock(spec=asyncio.Task)
        task2 = AsyncMock(spec=asyncio.Task)
        _drain_tasks[100] = [task1]
        _drain_tasks[200] = [task2]

        await cancel_drain_tasks()

        task1.cancel.assert_called_once()
        task2.cancel.assert_called_once()
        assert len(_drain_tasks) == 0


class TestStopTimeout:
    """Tests for stop_swarm process.wait() timeout."""

    async def test_stop_timeout_kills_process(self, client, mock_project_folder, caplog):
        (mock_project_folder / "stop-swarm.ps1").write_text("# Mock")
        resp = await client.post("/api/projects", json={
            "name": "Timeout Test",
            "goal": "Test stop timeout",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_process = AsyncMock()
            mock_process.wait = AsyncMock(side_effect=asyncio.TimeoutError)
            mock_process.kill = AsyncMock()
            mock_exec.return_value = mock_process

            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                with caplog.at_level(logging.WARNING, logger="latent.swarm"):
                    resp = await client.post("/api/swarm/stop", json={"project_id": pid})

            assert resp.status_code == 200
            assert resp.json()["status"] == "stopped"
            mock_process.kill.assert_called_once()
            assert any("timed out" in r.message for r in caplog.records)
