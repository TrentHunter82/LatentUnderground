"""Tests for per-agent orchestration: launch, list, stop, output, input."""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAgentsList:
    """Tests for GET /api/swarm/agents/{project_id}."""

    async def test_returns_empty_when_no_agents(self, client, created_project):
        """No agents should return empty list."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/agents/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == pid
        assert data["agents"] == []

    async def test_returns_404_for_nonexistent_project(self, client):
        """Should 404 for unknown project."""
        resp = await client.get("/api/swarm/agents/99999")
        assert resp.status_code == 404

    async def test_lists_tracked_agents(self, client, created_project):
        """Should list agents that are being tracked."""
        from app.routes.swarm import _agent_processes, _agent_key, _agent_output_buffers

        pid = created_project["id"]
        key1 = _agent_key(pid, "Claude-1")
        key2 = _agent_key(pid, "Claude-2")
        mock1 = MagicMock()
        mock1.poll.return_value = None  # alive
        mock1.pid = 1001
        mock2 = MagicMock()
        mock2.poll.return_value = 0  # exited
        mock2.pid = 1002
        _agent_processes[key1] = mock1
        _agent_processes[key2] = mock2
        _agent_output_buffers[key1] = ["line1", "line2"]
        _agent_output_buffers[key2] = ["line3"]

        resp = await client.get(f"/api/swarm/agents/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["agents"]) == 2

        agents_by_name = {a["name"]: a for a in data["agents"]}
        assert agents_by_name["Claude-1"]["alive"] is True
        assert agents_by_name["Claude-1"]["pid"] == 1001
        assert agents_by_name["Claude-1"]["output_lines"] == 2
        assert agents_by_name["Claude-2"]["alive"] is False
        assert agents_by_name["Claude-2"]["pid"] == 1002
        assert agents_by_name["Claude-2"]["output_lines"] == 1

        # Cleanup
        _agent_processes.pop(key1, None)
        _agent_processes.pop(key2, None)
        _agent_output_buffers.pop(key1, None)
        _agent_output_buffers.pop(key2, None)

    async def test_does_not_show_other_project_agents(self, client, created_project):
        """Agent list should be scoped to the requested project only."""
        from app.routes.swarm import _agent_processes, _agent_key

        pid = created_project["id"]
        other_key = _agent_key(99999, "Claude-1")
        mock = MagicMock()
        mock.poll.return_value = None
        mock.pid = 9999
        _agent_processes[other_key] = mock

        resp = await client.get(f"/api/swarm/agents/{pid}")
        assert resp.status_code == 200
        assert resp.json()["agents"] == []

        _agent_processes.pop(other_key, None)


class TestStopAgent:
    """Tests for POST /api/swarm/agents/{project_id}/{agent_name}/stop."""

    async def test_stop_running_agent(self, client, created_project):
        """Should stop a running agent and return status."""
        from app.routes.swarm import (
            _agent_processes, _agent_key, _agent_drain_events, _project_output_buffers,
        )

        pid = created_project["id"]
        key = _agent_key(pid, "Claude-1")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # alive
        mock_proc.pid = 2001
        mock_proc.wait.return_value = 0
        _agent_processes[key] = mock_proc
        _agent_drain_events[key] = threading.Event()
        _project_output_buffers[pid] = []

        resp = await client.post(f"/api/swarm/agents/{pid}/Claude-1/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent"] == "Claude-1"
        assert data["project_id"] == pid
        assert data["status"] == "stopped"

        # Process should have been terminated
        mock_proc.terminate.assert_called_once()
        # Key should be removed from tracking
        assert key not in _agent_processes

    async def test_stop_already_exited_agent(self, client, created_project):
        """Should handle stopping an agent that already exited."""
        from app.routes.swarm import _agent_processes, _agent_key

        pid = created_project["id"]
        key = _agent_key(pid, "Claude-1")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # already exited
        mock_proc.pid = 2002
        _agent_processes[key] = mock_proc

        resp = await client.post(f"/api/swarm/agents/{pid}/Claude-1/stop")
        assert resp.status_code == 200
        # Should not call terminate since already exited
        mock_proc.terminate.assert_not_called()

    async def test_stop_nonexistent_agent(self, client, created_project):
        """Should 404 for unknown agent."""
        pid = created_project["id"]
        resp = await client.post(f"/api/swarm/agents/{pid}/Claude-99/stop")
        assert resp.status_code == 404

    async def test_stop_adds_message_to_output(self, client, created_project):
        """Stopping agent should add a message to the project output buffer."""
        from app.routes.swarm import _agent_processes, _agent_key, _project_output_buffers

        pid = created_project["id"]
        key = _agent_key(pid, "Claude-3")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        mock_proc.pid = 2003
        _agent_processes[key] = mock_proc
        _project_output_buffers[pid] = []

        await client.post(f"/api/swarm/agents/{pid}/Claude-3/stop")

        assert any("Claude-3" in line and "stopped" in line.lower() for line in _project_output_buffers.get(pid, []))

    async def test_stop_nonexistent_project(self, client):
        """Should 404 for unknown project."""
        resp = await client.post("/api/swarm/agents/99999/Claude-1/stop")
        assert resp.status_code == 404


class TestAgentFilteredOutput:
    """Tests for GET /api/swarm/output/{project_id}?agent=..."""

    async def test_output_without_filter_returns_project_buffer(self, client, created_project):
        """Without agent param, should return combined project output."""
        from app.routes.swarm import _project_output_buffers

        pid = created_project["id"]
        _project_output_buffers[pid] = [
            "[Claude-1] hello",
            "[Claude-2] world",
            "[Claude-1] line 2",
        ]

        resp = await client.get(f"/api/swarm/output/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["lines"]) == 3
        assert data["agent"] is None

    async def test_output_with_agent_filter(self, client, created_project):
        """With ?agent=Claude-1, should return only that agent's buffer."""
        from app.routes.swarm import _agent_output_buffers, _agent_key

        pid = created_project["id"]
        key = _agent_key(pid, "Claude-1")
        _agent_output_buffers[key] = ["agent1 line1", "agent1 line2"]

        resp = await client.get(f"/api/swarm/output/{pid}?agent=Claude-1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["lines"]) == 2
        assert data["agent"] == "Claude-1"
        assert data["lines"][0] == "agent1 line1"

        _agent_output_buffers.pop(key, None)

    async def test_output_empty_for_unknown_agent(self, client, created_project):
        """Filtering by unknown agent should return empty lines."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/output/{pid}?agent=Claude-99")
        assert resp.status_code == 200
        assert resp.json()["lines"] == []

    async def test_output_pagination_with_agent(self, client, created_project):
        """Pagination should work with agent filter."""
        from app.routes.swarm import _agent_output_buffers, _agent_key

        pid = created_project["id"]
        key = _agent_key(pid, "Claude-2")
        _agent_output_buffers[key] = [f"line-{i}" for i in range(10)]

        resp = await client.get(f"/api/swarm/output/{pid}?agent=Claude-2&offset=5&limit=3")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["lines"]) == 3
        assert data["lines"][0] == "line-5"
        assert data["next_offset"] == 8
        assert data["has_more"] is True

        _agent_output_buffers.pop(key, None)


class TestAgentTargetedInput:
    """Tests for POST /api/swarm/input with agent targeting."""

    async def test_input_to_specific_agent_with_stdin(self, client, created_project):
        """Sending input with agent field should target only that agent."""
        from app.routes.swarm import _agent_processes, _agent_key, _project_output_buffers
        import aiosqlite
        from app import database

        pid = created_project["id"]

        # Mark project as running
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute("UPDATE projects SET status = 'running' WHERE id = ?", (pid,))
            await db.commit()

        key1 = _agent_key(pid, "Claude-1")
        key2 = _agent_key(pid, "Claude-2")
        mock1 = MagicMock()
        mock1.poll.return_value = None
        mock1.stdin = MagicMock()
        mock2 = MagicMock()
        mock2.poll.return_value = None
        mock2.stdin = MagicMock()
        _agent_processes[key1] = mock1
        _agent_processes[key2] = mock2
        _project_output_buffers[pid] = []

        resp = await client.post("/api/swarm/input", json={
            "project_id": pid,
            "text": "hello",
            "agent": "Claude-1",
        })
        assert resp.status_code == 200

        # Only Claude-1 should have received input
        mock1.stdin.write.assert_called_once()
        mock2.stdin.write.assert_not_called()

        _agent_processes.pop(key1, None)
        _agent_processes.pop(key2, None)

    async def test_input_rejected_for_print_mode_agents(self, client, created_project):
        """Agents in --print mode (stdin=DEVNULL) should reject input with 400."""
        from app.routes.swarm import _agent_processes, _agent_key
        import aiosqlite
        from app import database

        pid = created_project["id"]

        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute("UPDATE projects SET status = 'running' WHERE id = ?", (pid,))
            await db.commit()

        key1 = _agent_key(pid, "Claude-1")
        key2 = _agent_key(pid, "Claude-2")
        mock1 = MagicMock()
        mock1.poll.return_value = None
        mock1.stdin = None  # --print mode
        mock2 = MagicMock()
        mock2.poll.return_value = None
        mock2.stdin = None  # --print mode
        _agent_processes[key1] = mock1
        _agent_processes[key2] = mock2

        resp = await client.post("/api/swarm/input", json={
            "project_id": pid,
            "text": "hello all",
        })
        assert resp.status_code == 400
        assert "print mode" in resp.json()["detail"].lower()

        _agent_processes.pop(key1, None)
        _agent_processes.pop(key2, None)

    async def test_input_to_dead_agent_returns_400(self, client, created_project):
        """Targeting a dead agent should return 400."""
        from app.routes.swarm import _agent_processes, _agent_key
        import aiosqlite
        from app import database

        pid = created_project["id"]

        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute("UPDATE projects SET status = 'running' WHERE id = ?", (pid,))
            await db.commit()

        key = _agent_key(pid, "Claude-1")
        mock = MagicMock()
        mock.poll.return_value = 0  # exited
        _agent_processes[key] = mock

        resp = await client.post("/api/swarm/input", json={
            "project_id": pid,
            "text": "hello",
            "agent": "Claude-1",
        })
        assert resp.status_code == 400

        _agent_processes.pop(key, None)

    async def test_input_echo_includes_agent_label(self, client, created_project):
        """Targeted input should echo with agent label in project buffer."""
        from app.routes.swarm import _agent_processes, _agent_key, _project_output_buffers
        import aiosqlite
        from app import database

        pid = created_project["id"]

        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute("UPDATE projects SET status = 'running' WHERE id = ?", (pid,))
            await db.commit()

        key = _agent_key(pid, "Claude-1")
        mock = MagicMock()
        mock.poll.return_value = None
        mock.stdin = MagicMock()  # has stdin for this test
        _agent_processes[key] = mock
        _project_output_buffers[pid] = []

        await client.post("/api/swarm/input", json={
            "project_id": pid,
            "text": "test input",
            "agent": "Claude-1",
        })

        buf = _project_output_buffers.get(pid, [])
        assert any("[stdin:Claude-1]" in line for line in buf)

        _agent_processes.pop(key, None)


class TestCleanupHelpers:
    """Tests for _cleanup_project_agents and cancel_drain_tasks."""

    async def test_cleanup_terminates_alive_processes(self):
        """Should terminate processes that are still alive."""
        from app.routes.swarm import (
            _agent_processes, _agent_key, _cleanup_project_agents,
        )

        key = _agent_key(500, "Claude-1")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # alive
        mock_proc.wait.return_value = 0
        _agent_processes[key] = mock_proc

        _cleanup_project_agents(500)

        mock_proc.terminate.assert_called_once()
        assert key not in _agent_processes

    async def test_cleanup_clears_all_tracking_state(self):
        """Should clear all per-agent tracking state."""
        from app.routes.swarm import (
            _agent_processes, _agent_output_buffers,
            _agent_drain_events, _project_output_buffers,
            _agent_key, _cleanup_project_agents,
        )

        pid = 501
        key1 = _agent_key(pid, "Claude-1")
        key2 = _agent_key(pid, "Claude-2")

        _agent_processes[key1] = MagicMock(poll=MagicMock(return_value=0))
        _agent_processes[key2] = MagicMock(poll=MagicMock(return_value=0))
        _agent_output_buffers[key1] = ["line1"]
        _agent_output_buffers[key2] = ["line2"]
        _agent_drain_events[key1] = threading.Event()
        _agent_drain_events[key2] = threading.Event()
        _project_output_buffers[pid] = ["combined"]

        _cleanup_project_agents(pid)

        assert key1 not in _agent_processes
        assert key2 not in _agent_processes
        assert key1 not in _agent_output_buffers
        assert key2 not in _agent_output_buffers
        assert key1 not in _agent_drain_events
        assert key2 not in _agent_drain_events
        assert pid not in _project_output_buffers

    async def test_cancel_drain_tasks_all_projects(self):
        """cancel_drain_tasks() with no args should clean all projects."""
        from app.routes.swarm import (
            _agent_processes, _agent_drain_events, _agent_key,
            cancel_drain_tasks,
        )

        key_a = _agent_key(600, "Claude-1")
        key_b = _agent_key(700, "Claude-1")
        evt_a = threading.Event()
        evt_b = threading.Event()
        _agent_drain_events[key_a] = evt_a
        _agent_drain_events[key_b] = evt_b
        _agent_processes[key_a] = MagicMock(poll=MagicMock(return_value=0))
        _agent_processes[key_b] = MagicMock(poll=MagicMock(return_value=0))

        await cancel_drain_tasks()

        assert evt_a.is_set()
        assert evt_b.is_set()
        assert len(_agent_processes) == 0
        assert len(_agent_drain_events) == 0


class TestSupervisorCancellation:
    """Tests for supervisor task lifecycle."""

    async def test_cleanup_cancels_supervisor(self):
        """_cleanup_project_agents should cancel the supervisor task."""
        from app.routes.swarm import _supervisor_tasks, _cleanup_project_agents

        pid = 800
        mock_task = MagicMock()
        mock_task.done.return_value = False
        _supervisor_tasks[pid] = mock_task

        _cleanup_project_agents(pid)

        mock_task.cancel.assert_called_once()
        assert pid not in _supervisor_tasks


class TestCleanupOrder:
    """Tests verifying cleanup terminates process before joining threads."""

    async def test_cleanup_terminates_before_join(self):
        """Cleanup should terminate the process (which unblocks drain threads on readline)."""
        from app.routes.swarm import _agent_processes, _agent_key, _cleanup_project_agents

        key = _agent_key(810, "Claude-1")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = 0
        mock_proc.stdin = None  # --print mode uses DEVNULL
        _agent_processes[key] = mock_proc

        _cleanup_project_agents(810)

        mock_proc.terminate.assert_called_once()
        assert key not in _agent_processes

    async def test_cleanup_handles_already_exited(self):
        """Cleanup should handle processes that already exited gracefully."""
        from app.routes.swarm import _agent_processes, _agent_key, _cleanup_project_agents

        key = _agent_key(811, "Claude-1")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # already exited
        mock_proc.stdin = None
        _agent_processes[key] = mock_proc

        _cleanup_project_agents(811)
        assert key not in _agent_processes
        mock_proc.terminate.assert_not_called()

    async def test_stop_agent_terminates(self, client, created_project):
        """stop_agent should terminate the process."""
        from app.routes.swarm import _agent_processes, _agent_key, _project_output_buffers

        pid = created_project["id"]
        key = _agent_key(pid, "Claude-1")
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 3001
        mock_proc.wait.return_value = 0
        mock_proc.stdin = None
        _agent_processes[key] = mock_proc
        _project_output_buffers[pid] = []

        resp = await client.post(f"/api/swarm/agents/{pid}/Claude-1/stop")
        assert resp.status_code == 200

        mock_proc.terminate.assert_called_once()


class TestSupervisorPartialFailure:
    """Tests for supervisor reporting individual agent exits."""

    async def test_supervisor_reports_crashed_agent_in_buffer(self):
        """When an agent crashes, the supervisor should add a message to the project buffer."""
        from app.routes.swarm import (
            _agent_processes, _agent_key, _project_output_buffers,
            _supervisor_loop,
        )

        pid = 820
        key1 = _agent_key(pid, "Claude-1")
        key2 = _agent_key(pid, "Claude-2")

        # Both agents already exited: Claude-1 crashed, Claude-2 exited normally
        mock1 = MagicMock()
        mock1.poll.return_value = 1  # crashed
        mock1.returncode = 1
        mock2 = MagicMock()
        mock2.poll.return_value = 0  # exited normally
        mock2.returncode = 0

        _agent_processes[key1] = mock1
        _agent_processes[key2] = mock2
        _project_output_buffers[pid] = []

        # Mock aiosqlite with proper async context manager
        mock_db_ctx = AsyncMock()
        mock_db_ctx.__aenter__.return_value = mock_db_ctx
        mock_db_ctx.row_factory = None

        # Call _supervisor_loop directly — since all agents are already exited,
        # it will detect them on the first iteration and exit the loop
        with patch("app.routes.swarm.asyncio.sleep", new_callable=AsyncMock), \
             patch("app.routes.swarm.aiosqlite") as mock_aiosqlite, \
             patch("app.routes.swarm.emit_webhook_event", new_callable=AsyncMock):
            mock_aiosqlite.connect.return_value = mock_db_ctx
            mock_aiosqlite.Row = None

            await asyncio.wait_for(_supervisor_loop(pid), timeout=2.0)

        buf = _project_output_buffers.get(pid, [])
        crash_msgs = [l for l in buf if "crashed" in l.lower() or "exit code" in l.lower()]
        assert len(crash_msgs) >= 1
        assert "Claude-1" in crash_msgs[0]
        # Claude-2 should have a normal exit message
        normal_msgs = [l for l in buf if "exited normally" in l.lower()]
        assert len(normal_msgs) >= 1
        assert "Claude-2" in normal_msgs[0]

        # Cleanup
        _agent_processes.pop(key1, None)
        _agent_processes.pop(key2, None)
        _project_output_buffers.pop(pid, None)


class TestAgentHelpers:
    """Tests for _agent_key, _project_agent_keys, _any_agent_alive."""

    def test_agent_key_format(self):
        """Key should be '{project_id}:{agent_name}'."""
        from app.routes.swarm import _agent_key
        assert _agent_key(42, "Claude-1") == "42:Claude-1"

    def test_project_agent_keys_filters_correctly(self):
        """Should only return keys for the given project."""
        from app.routes.swarm import _agent_processes, _agent_key, _project_agent_keys

        key1 = _agent_key(100, "Claude-1")
        key2 = _agent_key(100, "Claude-2")
        key3 = _agent_key(200, "Claude-1")
        _agent_processes[key1] = MagicMock()
        _agent_processes[key2] = MagicMock()
        _agent_processes[key3] = MagicMock()

        keys = _project_agent_keys(100)
        assert sorted(keys) == sorted([key1, key2])

        _agent_processes.pop(key1, None)
        _agent_processes.pop(key2, None)
        _agent_processes.pop(key3, None)

    def test_any_agent_alive_true_when_one_alive(self):
        """Should return True if at least one agent is alive."""
        from app.routes.swarm import _agent_processes, _agent_key, _any_agent_alive

        key1 = _agent_key(300, "Claude-1")
        key2 = _agent_key(300, "Claude-2")
        mock1 = MagicMock()
        mock1.poll.return_value = 0  # exited
        mock2 = MagicMock()
        mock2.poll.return_value = None  # alive
        _agent_processes[key1] = mock1
        _agent_processes[key2] = mock2

        assert _any_agent_alive(300) is True

        _agent_processes.pop(key1, None)
        _agent_processes.pop(key2, None)

    def test_any_agent_alive_false_when_all_exited(self):
        """Should return False when all agents have exited."""
        from app.routes.swarm import _agent_processes, _agent_key, _any_agent_alive

        key = _agent_key(400, "Claude-1")
        mock = MagicMock()
        mock.poll.return_value = 0
        _agent_processes[key] = mock

        assert _any_agent_alive(400) is False

        _agent_processes.pop(key, None)

    def test_any_agent_alive_false_when_no_agents(self):
        """Should return False when no agents are tracked."""
        from app.routes.swarm import _any_agent_alive
        assert _any_agent_alive(999) is False


class TestLaunchFlow:
    """Tests for the full launch flow with per-agent spawning."""

    async def test_launch_creates_agents(self, client, tmp_path, mock_launch_deps):
        """Launch should spawn per-agent processes."""
        folder = tmp_path / "orchestration_test"
        folder.mkdir()
        (folder / "swarm.ps1").write_text("# mock")

        resp = await client.post("/api/projects", json={
            "name": "Agent Launch Test",
            "goal": "Test per-agent launch",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 55555
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.stdout.readline.return_value = b""
            mock_process.stderr.readline.return_value = b""
            mock_popen.return_value = mock_process

            resp = await client.post("/api/swarm/launch", json={"project_id": pid})
            assert resp.status_code == 200

            # Should have spawned 4 agents (default agent_count)
            assert mock_popen.call_count == 4

    async def test_launch_returns_first_pid(self, client, tmp_path, mock_launch_deps):
        """Launch should return the first agent's PID."""
        folder = tmp_path / "pid_test"
        folder.mkdir()
        (folder / "swarm.ps1").write_text("# mock")

        resp = await client.post("/api/projects", json={
            "name": "PID Test",
            "goal": "Test PID return",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 77777
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.stdout.readline.return_value = b""
            mock_process.stderr.readline.return_value = b""
            mock_popen.return_value = mock_process

            resp = await client.post("/api/swarm/launch", json={"project_id": pid})
            assert resp.status_code == 200
            assert resp.json()["pid"] == 77777

    async def test_launch_populates_output_buffer(self, client, tmp_path, mock_launch_deps):
        """Launch should add setup and agent launch messages to output buffer."""
        from app.routes.swarm import _project_output_buffers

        folder = tmp_path / "buffer_test"
        folder.mkdir()
        (folder / "swarm.ps1").write_text("# mock")

        resp = await client.post("/api/projects", json={
            "name": "Buffer Test",
            "goal": "Test output buffer",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 66666
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.stdout.readline.return_value = b""
            mock_process.stderr.readline.return_value = b""
            mock_popen.return_value = mock_process

            resp = await client.post("/api/swarm/launch", json={"project_id": pid})
            assert resp.status_code == 200

        buf = _project_output_buffers.get(pid, [])
        # Should have setup output and agent launch messages
        assert any("Launched" in line for line in buf)

    async def test_launch_uses_claude_cmd(self, client, tmp_path, mock_launch_deps):
        """Launch should use the found claude CLI path."""
        folder = tmp_path / "claude_cmd_test"
        folder.mkdir()
        (folder / "swarm.ps1").write_text("# mock")

        resp = await client.post("/api/projects", json={
            "name": "Claude CMD",
            "goal": "Test claude path",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 44444
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.stdout.readline.return_value = b""
            mock_process.stderr.readline.return_value = b""
            mock_popen.return_value = mock_process

            await client.post("/api/swarm/launch", json={"project_id": pid})

            # First call's first positional arg should be the command list
            call_args = mock_popen.call_args_list[0]
            cmd_list = call_args[0][0]
            assert cmd_list[0] == "claude.cmd"  # from mock_launch_deps
            assert "--dangerously-skip-permissions" in cmd_list


class TestExitCodeTracking:
    """Tests for exit_code in agent status responses."""

    async def test_alive_agent_has_no_exit_code(self, client, created_project):
        """Alive agents should have exit_code=None."""
        from app.routes.swarm import _agent_processes, _agent_key, _agent_output_buffers

        pid = created_project['id']
        key = _agent_key(pid, 'Claude-1')
        mock = MagicMock()
        mock.poll.return_value = None  # alive
        mock.pid = 5001
        _agent_processes[key] = mock
        _agent_output_buffers[key] = []

        resp = await client.get(f'/api/swarm/agents/{pid}')
        assert resp.status_code == 200
        agent = resp.json()['agents'][0]
        assert agent['alive'] is True
        assert agent['exit_code'] is None

        _agent_processes.pop(key, None)
        _agent_output_buffers.pop(key, None)

    async def test_crashed_agent_has_nonzero_exit_code(self, client, created_project):
        """Crashed agents should report their non-zero exit code."""
        from app.routes.swarm import _agent_processes, _agent_key, _agent_output_buffers

        pid = created_project['id']
        key = _agent_key(pid, 'Claude-1')
        mock = MagicMock()
        mock.poll.return_value = 1  # crashed
        mock.returncode = 1
        mock.pid = 5002
        _agent_processes[key] = mock
        _agent_output_buffers[key] = []

        resp = await client.get(f'/api/swarm/agents/{pid}')
        assert resp.status_code == 200
        agent = resp.json()['agents'][0]
        assert agent['alive'] is False
        assert agent['exit_code'] == 1

        _agent_processes.pop(key, None)
        _agent_output_buffers.pop(key, None)

    async def test_normal_exit_has_zero_exit_code(self, client, created_project):
        """Normally exited agents should have exit_code=0."""
        from app.routes.swarm import _agent_processes, _agent_key, _agent_output_buffers

        pid = created_project['id']
        key = _agent_key(pid, 'Claude-1')
        mock = MagicMock()
        mock.poll.return_value = 0  # exited normally
        mock.returncode = 0
        mock.pid = 5003
        _agent_processes[key] = mock
        _agent_output_buffers[key] = []

        resp = await client.get(f'/api/swarm/agents/{pid}')
        assert resp.status_code == 200
        agent = resp.json()['agents'][0]
        assert agent['alive'] is False
        assert agent['exit_code'] == 0

        _agent_processes.pop(key, None)
        _agent_output_buffers.pop(key, None)


class TestAgentNameValidation:
    """Tests for agent name format validation."""

    async def test_valid_agent_names(self, client, created_project):
        """Valid names like Claude-1 through Claude-16 should be accepted."""
        from app.routes.swarm import _validate_agent_name
        assert _validate_agent_name('Claude-1') is True
        assert _validate_agent_name('Claude-4') is True
        assert _validate_agent_name('Claude-10') is True
        assert _validate_agent_name('Claude-16') is True

    async def test_invalid_agent_names(self, client, created_project):
        """Invalid names should be rejected."""
        from app.routes.swarm import _validate_agent_name
        assert _validate_agent_name('') is False
        assert _validate_agent_name('Agent-1') is False
        assert _validate_agent_name('Claude-') is False
        assert _validate_agent_name('Claude-abc') is False
        assert _validate_agent_name('../etc/passwd') is False
        assert _validate_agent_name('Claude-1; rm -rf /') is False
        assert _validate_agent_name('Claude-999') is False  # 3 digits

    async def test_stop_rejects_invalid_agent_name(self, client, created_project):
        """Stop endpoint should reject malformed agent names."""
        pid = created_project['id']
        resp = await client.post(f'/api/swarm/agents/{pid}/../etc/passwd/stop')
        # This hits 404 because of path routing, but explicit names get 400
        resp2 = await client.post(f'/api/swarm/agents/{pid}/INVALID-NAME/stop')
        assert resp2.status_code == 400

    async def test_input_rejects_invalid_agent_name(self, client, created_project):
        """Input endpoint should reject malformed agent names."""
        pid = created_project['id']
        # Set project status to running so we get past the status check
        await client.patch(f'/api/projects/{pid}', json={'status': 'running'})

        resp = await client.post('/api/swarm/input', json={
            'project_id': pid, 'text': 'hello', 'agent': 'INVALID',
        })
        assert resp.status_code == 400
        assert 'Invalid agent name' in resp.json()['detail']
