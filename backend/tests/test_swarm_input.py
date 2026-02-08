"""Tests for POST /api/swarm/input endpoint (Phase 7)."""

from unittest.mock import MagicMock, patch

import pytest


class TestSwarmInput:
    """Tests for stdin input to running swarm processes."""

    async def test_input_project_not_found(self, client):
        """POST /api/swarm/input returns 404 for non-existent project."""
        resp = await client.post("/api/swarm/input", json={
            "project_id": 9999,
            "text": "hello",
        })
        assert resp.status_code == 404
        assert "Project not found" in resp.json()["detail"]

    async def test_input_swarm_not_running(self, client, created_project):
        """POST /api/swarm/input returns 400 when project status is not 'running'."""
        pid = created_project["id"]
        resp = await client.post("/api/swarm/input", json={
            "project_id": pid,
            "text": "hello",
        })
        assert resp.status_code == 400
        assert "not running" in resp.json()["detail"]

    async def test_input_no_process_object(self, client, created_project):
        """Returns 400 when project is 'running' but no Popen in _swarm_processes."""
        pid = created_project["id"]
        # Manually set status to running
        from app import database
        import aiosqlite
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE projects SET status = 'running' WHERE id = ?", (pid,)
            )
            await db.commit()

        resp = await client.post("/api/swarm/input", json={
            "project_id": pid,
            "text": "hello",
        })
        assert resp.status_code == 400
        assert "exited" in resp.json()["detail"]

    async def test_input_process_exited(self, client, created_project):
        """Returns 400 when process exists but has already exited (poll() != None)."""
        pid = created_project["id"]
        from app import database
        from app.routes.swarm import _swarm_processes
        import aiosqlite

        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE projects SET status = 'running' WHERE id = ?", (pid,)
            )
            await db.commit()

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # Process has exited
        _swarm_processes[pid] = mock_proc
        try:
            resp = await client.post("/api/swarm/input", json={
                "project_id": pid,
                "text": "hello",
            })
            assert resp.status_code == 400
            assert "exited" in resp.json()["detail"]
        finally:
            _swarm_processes.pop(pid, None)

    async def test_input_success(self, client, created_project):
        """Successful stdin write returns 200 with status=sent."""
        pid = created_project["id"]
        from app import database
        from app.routes.swarm import _swarm_processes, _output_buffers
        import aiosqlite

        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE projects SET status = 'running' WHERE id = ?", (pid,)
            )
            await db.commit()

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Still running
        mock_proc.stdin = MagicMock()
        _swarm_processes[pid] = mock_proc
        try:
            resp = await client.post("/api/swarm/input", json={
                "project_id": pid,
                "text": "test command",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "sent"
            assert data["project_id"] == pid

            # Verify stdin was written correctly
            mock_proc.stdin.write.assert_called_once_with(b"test command\n")
            mock_proc.stdin.flush.assert_called_once()
        finally:
            _swarm_processes.pop(pid, None)

    async def test_input_echo_in_buffer(self, client, created_project):
        """Input text is echoed in output buffer with [stdin] prefix."""
        pid = created_project["id"]
        from app import database
        from app.routes.swarm import _swarm_processes, _output_buffers
        import aiosqlite

        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE projects SET status = 'running' WHERE id = ?", (pid,)
            )
            await db.commit()

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        _swarm_processes[pid] = mock_proc
        try:
            await client.post("/api/swarm/input", json={
                "project_id": pid,
                "text": "my input",
            })

            # Check the output buffer has the echoed input
            assert pid in _output_buffers
            assert "[stdin] my input" in _output_buffers[pid]
        finally:
            _swarm_processes.pop(pid, None)

    async def test_input_broken_pipe(self, client, created_project):
        """Returns 500 when stdin write raises BrokenPipeError."""
        pid = created_project["id"]
        from app import database
        from app.routes.swarm import _swarm_processes
        import aiosqlite

        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE projects SET status = 'running' WHERE id = ?", (pid,)
            )
            await db.commit()

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.write.side_effect = BrokenPipeError("Broken pipe")
        _swarm_processes[pid] = mock_proc
        try:
            resp = await client.post("/api/swarm/input", json={
                "project_id": pid,
                "text": "hello",
            })
            assert resp.status_code == 500
            assert "stdin" in resp.json()["detail"].lower()
        finally:
            _swarm_processes.pop(pid, None)

    async def test_input_text_too_long(self, client, created_project):
        """Pydantic rejects text longer than 1000 characters with 422."""
        pid = created_project["id"]
        resp = await client.post("/api/swarm/input", json={
            "project_id": pid,
            "text": "x" * 1001,
        })
        assert resp.status_code == 422
