"""Tests for POST /api/swarm/input endpoint (Phase 7, updated for per-agent)."""

from unittest.mock import MagicMock

import pytest


class TestSwarmInput:
    """Tests for stdin input to running swarm agent processes."""

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

    async def test_input_no_agent_processes(self, client, created_project):
        """Returns 400 when project is 'running' but no agents are tracked."""
        pid = created_project["id"]
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
        assert "running" in resp.json()["detail"].lower()

    async def test_input_agent_exited(self, client, created_project):
        """Returns 400 when targeting a specific agent that has exited."""
        pid = created_project["id"]
        from app import database
        from app.routes.swarm import _agent_processes, _agent_key
        import aiosqlite

        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE projects SET status = 'running' WHERE id = ?", (pid,)
            )
            await db.commit()

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # Process has exited
        key = _agent_key(pid, "Claude-1")
        _agent_processes[key] = mock_proc
        try:
            resp = await client.post("/api/swarm/input", json={
                "project_id": pid,
                "text": "hello",
                "agent": "Claude-1",
            })
            assert resp.status_code == 400
            assert "not running" in resp.json()["detail"].lower()
        finally:
            _agent_processes.pop(key, None)

    async def test_input_success(self, client, created_project):
        """Successful bus message returns 200 with status=sent."""
        pid = created_project["id"]
        from app import database
        from app.routes.swarm import _agent_processes, _agent_key
        import aiosqlite

        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE projects SET status = 'running' WHERE id = ?", (pid,)
            )
            await db.commit()

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Still running
        mock_proc.pid = 12345
        key = _agent_key(pid, "Claude-1")
        _agent_processes[key] = mock_proc
        try:
            resp = await client.post("/api/swarm/input", json={
                "project_id": pid,
                "text": "test command",
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "sent"
            assert data["project_id"] == pid

            # Verify bus message was created
            async with aiosqlite.connect(database.DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                row = await (await db.execute(
                    "SELECT * FROM bus_messages WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                    (pid,),
                )).fetchone()
                assert row is not None
                assert row["body"] == "test command"
                assert row["to_agent"] == "all"
        finally:
            _agent_processes.pop(key, None)

    async def test_input_echo_in_buffer(self, client, created_project):
        """Input text is echoed in project output buffer."""
        pid = created_project["id"]
        from app import database
        from app.routes.swarm import _agent_processes, _project_output_buffers, _agent_key
        import aiosqlite

        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE projects SET status = 'running' WHERE id = ?", (pid,)
            )
            await db.commit()

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345
        key = _agent_key(pid, "Claude-1")
        _agent_processes[key] = mock_proc
        try:
            await client.post("/api/swarm/input", json={
                "project_id": pid,
                "text": "my input",
            })

            # Check the project output buffer has the echoed input
            assert pid in _project_output_buffers
            assert any("[bus:human->" in line and "my input" in line for line in _project_output_buffers[pid])
        finally:
            _agent_processes.pop(key, None)

    async def test_input_bus_message_has_critical_priority(self, client, created_project):
        """Bus messages from /input are created with critical channel and high priority."""
        pid = created_project["id"]
        from app import database
        from app.routes.swarm import _agent_processes, _agent_key
        import aiosqlite

        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE projects SET status = 'running' WHERE id = ?", (pid,)
            )
            await db.commit()

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345
        key = _agent_key(pid, "Claude-1")
        _agent_processes[key] = mock_proc
        try:
            resp = await client.post("/api/swarm/input", json={
                "project_id": pid,
                "text": "urgent message",
            })
            assert resp.status_code == 200

            async with aiosqlite.connect(database.DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                row = await (await db.execute(
                    "SELECT * FROM bus_messages WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                    (pid,),
                )).fetchone()
                assert row["channel"] == "critical"
                assert row["priority"] == "high"
                assert row["from_agent"] == "human"
        finally:
            _agent_processes.pop(key, None)

    async def test_input_text_too_long(self, client, created_project):
        """Pydantic rejects text longer than 1000 characters with 422."""
        pid = created_project["id"]
        resp = await client.post("/api/swarm/input", json={
            "project_id": pid,
            "text": "x" * 1001,
        })
        assert resp.status_code == 422

    async def test_input_to_specific_agent(self, client, created_project):
        """Sending input to a specific agent creates bus message targeting that agent."""
        pid = created_project["id"]
        from app import database
        from app.routes.swarm import _agent_processes, _agent_key
        import aiosqlite

        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE projects SET status = 'running' WHERE id = ?", (pid,)
            )
            await db.commit()

        mock_proc1 = MagicMock()
        mock_proc1.poll.return_value = None
        mock_proc1.pid = 111

        mock_proc2 = MagicMock()
        mock_proc2.poll.return_value = None
        mock_proc2.pid = 222

        key1 = _agent_key(pid, "Claude-1")
        key2 = _agent_key(pid, "Claude-2")
        _agent_processes[key1] = mock_proc1
        _agent_processes[key2] = mock_proc2
        try:
            resp = await client.post("/api/swarm/input", json={
                "project_id": pid,
                "text": "targeted input",
                "agent": "Claude-1",
            })
            assert resp.status_code == 200

            async with aiosqlite.connect(database.DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                row = await (await db.execute(
                    "SELECT * FROM bus_messages WHERE project_id = ? AND to_agent = 'Claude-1' "
                    "ORDER BY created_at DESC LIMIT 1",
                    (pid,),
                )).fetchone()
                assert row is not None
                assert row["body"] == "targeted input"
        finally:
            _agent_processes.pop(key1, None)
            _agent_processes.pop(key2, None)
