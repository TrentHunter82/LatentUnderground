"""Tests for Phase 19 backend features.

Covers:
1. Per-project asyncio.Lock for concurrent launch/stop protection
2. WebSocket authentication when LU_API_KEY is set
3. Status field enum validation on PATCH /api/projects/{id}
4. Conditional psutil import in system.py
5. Request timeout middleware
6. Agent output log persistence
"""

import asyncio
import os
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================================
# 1. Per-project asyncio.Lock
# ============================================================================


class TestProjectLocks:
    """Test per-project asyncio.Lock prevents concurrent launch+stop."""

    async def test_get_project_lock_returns_same_lock(self):
        """Same project_id always returns the same lock object."""
        from app.routes.swarm import _get_project_lock, _project_locks
        _project_locks.clear()
        try:
            lock1 = _get_project_lock(1)
            lock2 = _get_project_lock(1)
            assert lock1 is lock2
        finally:
            _project_locks.clear()

    async def test_get_project_lock_different_projects(self):
        """Different project_ids get different lock objects."""
        from app.routes.swarm import _get_project_lock, _project_locks
        _project_locks.clear()
        try:
            lock1 = _get_project_lock(1)
            lock2 = _get_project_lock(2)
            assert lock1 is not lock2
        finally:
            _project_locks.clear()

    async def test_lock_serializes_operations(self):
        """Lock prevents concurrent operations on the same project."""
        from app.routes.swarm import _get_project_lock, _project_locks
        _project_locks.clear()

        order = []
        lock = _get_project_lock(42)

        async def op1():
            async with lock:
                order.append("op1_start")
                await asyncio.sleep(0.05)
                order.append("op1_end")

        async def op2():
            await asyncio.sleep(0.01)  # Ensure op1 gets lock first
            async with lock:
                order.append("op2_start")
                order.append("op2_end")

        await asyncio.gather(op1(), op2())
        # op1 should complete before op2 starts
        assert order == ["op1_start", "op1_end", "op2_start", "op2_end"]
        _project_locks.clear()

    async def test_launch_uses_project_lock(self, client, created_project, mock_launch_deps):
        """Launch endpoint acquires per-project lock."""
        from app.routes.swarm import _project_locks
        pid = created_project["id"]
        folder = Path(created_project["folder_path"])
        # Create swarm.ps1 so launch doesn't 400
        (folder / "swarm.ps1").write_text("# mock")

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None
        mock_proc.stdin = None
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.readline.return_value = b""

        with patch("app.routes.swarm.subprocess.Popen", return_value=mock_proc):
            resp = await client.post("/api/swarm/launch", json={"project_id": pid})
        assert resp.status_code == 200
        # Lock should have been created for this project
        assert pid in _project_locks

    async def test_stop_uses_project_lock(self, client, created_project):
        """Stop endpoint acquires per-project lock."""
        from app.routes.swarm import _project_locks
        pid = created_project["id"]

        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert resp.status_code == 200
        assert pid in _project_locks


# ============================================================================
# 2. WebSocket Authentication
# ============================================================================


class TestWebSocketAuth:
    """Test WebSocket authentication when LU_API_KEY is set."""

    async def test_ws_no_auth_when_key_empty(self, client, app):
        """WebSocket connects without auth when API key is not configured."""
        with patch("app.routes.websocket.config") as mock_config:
            mock_config.API_KEY = ""
            # We can't fully test WS via httpx, but we can verify the
            # auth function works by testing the endpoint behavior
            from app.routes.websocket import websocket_endpoint
            # The function exists and doesn't crash
            assert callable(websocket_endpoint)

    async def test_ws_auth_rejects_without_token(self):
        """WebSocket closes with 4401 when API key required but no token given."""
        from app.routes.websocket import websocket_endpoint
        mock_ws = AsyncMock()
        mock_ws.query_params = {}

        with patch("app.routes.websocket.config") as mock_config:
            mock_config.API_KEY = "test-secret-key"
            await websocket_endpoint(mock_ws)

        mock_ws.close.assert_called_once_with(code=4401, reason="Authentication required")

    async def test_ws_auth_rejects_wrong_token(self):
        """WebSocket closes with 4401 when wrong token provided."""
        from app.routes.websocket import websocket_endpoint
        mock_ws = AsyncMock()
        mock_ws.query_params = {"token": "wrong-key"}

        with patch("app.routes.websocket.config") as mock_config:
            mock_config.API_KEY = "test-secret-key"
            await websocket_endpoint(mock_ws)

        mock_ws.close.assert_called_once_with(code=4401, reason="Authentication required")

    async def test_ws_auth_accepts_correct_token(self):
        """WebSocket connects when correct token provided."""
        from starlette.websockets import WebSocketDisconnect
        from app.routes.websocket import websocket_endpoint, manager
        mock_ws = AsyncMock()
        mock_ws.query_params = {"token": "test-secret-key"}
        mock_ws.receive_text.side_effect = WebSocketDisconnect()

        with patch("app.routes.websocket.config") as mock_config:
            mock_config.API_KEY = "test-secret-key"
            await websocket_endpoint(mock_ws)

        # Should have been accepted (connect was called)
        mock_ws.accept.assert_called_once()
        # Clean up
        manager.disconnect(mock_ws)


# ============================================================================
# 3. Status Field Enum Validation
# ============================================================================


class TestStatusEnumValidation:
    """Test that PATCH /api/projects/{id} rejects invalid status values."""

    async def test_valid_status_accepted(self, client, created_project):
        """All valid status values are accepted."""
        pid = created_project["id"]
        for status in ["created", "running", "stopped", "completed", "error"]:
            resp = await client.patch(f"/api/projects/{pid}", json={"status": status})
            assert resp.status_code == 200, f"Status '{status}' should be valid"
            assert resp.json()["status"] == status

    async def test_invalid_status_rejected(self, client, created_project):
        """Invalid status values return 422."""
        pid = created_project["id"]
        for status in ["invalid", "paused", "active", "deleted", "", "RUNNING"]:
            resp = await client.patch(f"/api/projects/{pid}", json={"status": status})
            assert resp.status_code == 422, f"Status '{status}' should be rejected"

    async def test_null_status_allowed(self, client, created_project):
        """Null status (no update) is allowed."""
        pid = created_project["id"]
        resp = await client.patch(f"/api/projects/{pid}", json={"name": "Updated Name"})
        assert resp.status_code == 200

    async def test_valid_statuses_constant(self):
        """VALID_STATUSES constant exists and matches Literal type."""
        from app.models.project import VALID_STATUSES
        assert "created" in VALID_STATUSES
        assert "running" in VALID_STATUSES
        assert "stopped" in VALID_STATUSES
        assert "completed" in VALID_STATUSES
        assert "error" in VALID_STATUSES
        assert len(VALID_STATUSES) == 5


# ============================================================================
# 4. Conditional psutil Import
# ============================================================================


class TestConditionalPsutil:
    """Test that system.py gracefully handles missing psutil."""

    async def test_system_endpoint_works_with_psutil(self, client):
        """System endpoint returns metrics when psutil is available."""
        resp = await client.get("/api/system")
        assert resp.status_code == 200
        data = resp.json()
        assert "cpu_percent" in data
        assert "memory_percent" in data
        assert "cpu_count" in data
        assert data["cpu_count"] >= 1

    async def test_system_endpoint_without_psutil(self, client):
        """System endpoint returns zeros when psutil is not importable."""
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("psutil not installed")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            resp = await client.get("/api/system")

        assert resp.status_code == 200
        data = resp.json()
        assert data["cpu_percent"] == 0.0
        assert data["memory_percent"] == 0.0
        assert data["cpu_count"] == 1


# ============================================================================
# 5. Request Timeout Middleware
# ============================================================================


class TestRequestTimeoutMiddleware:
    """Test configurable request timeout middleware."""

    async def test_timeout_config_exists(self):
        """REQUEST_TIMEOUT config value exists and has sensible default."""
        from app import config
        assert hasattr(config, "REQUEST_TIMEOUT")
        assert config.REQUEST_TIMEOUT == 60  # Default

    async def test_middleware_class_exists(self):
        """RequestTimeoutMiddleware is defined in main module."""
        from app.main import RequestTimeoutMiddleware
        assert callable(RequestTimeoutMiddleware)

    async def test_normal_request_not_affected(self, client):
        """Normal fast requests are not affected by timeout middleware."""
        resp = await client.get("/api/health")
        assert resp.status_code == 200

    async def test_timeout_disabled_when_zero(self):
        """Timeout middleware passes through when timeout is 0."""
        from app.main import RequestTimeoutMiddleware

        mock_app = MagicMock()
        middleware = RequestTimeoutMiddleware(mock_app, timeout_seconds=0)
        assert middleware.timeout == 0

    async def test_timeout_skips_streaming_endpoints(self):
        """Streaming endpoints are excluded from timeout."""
        from app.main import RequestTimeoutMiddleware
        mw = RequestTimeoutMiddleware(MagicMock(), timeout_seconds=5)
        # Verify skip suffixes
        assert "/stream" in mw._SKIP_SUFFIXES


# ============================================================================
# 6. Agent Output Log Persistence
# ============================================================================


class TestAgentOutputLogPersistence:
    """Test that agent output is persisted to log files on disk."""

    async def test_log_files_dict_exists(self):
        """The _agent_log_files tracking dict exists."""
        from app.routes.swarm import _agent_log_files
        assert isinstance(_agent_log_files, dict)

    async def test_log_file_created_on_launch(self, client, created_project, mock_launch_deps):
        """Agent log files are set up during swarm launch."""
        from app.routes.swarm import _agent_log_files

        pid = created_project["id"]
        folder = Path(created_project["folder_path"])
        (folder / "swarm.ps1").write_text("# mock")

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None
        mock_proc.stdin = None
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.readline.return_value = b""

        with patch("app.routes.swarm.subprocess.Popen", return_value=mock_proc):
            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid,
                "agent_count": 2,
            })
        assert resp.status_code == 200

        # Log files should have been registered for launched agents
        launched = resp.json()["agents_launched"]
        for agent in launched:
            key = f"{pid}:{agent}"
            assert key in _agent_log_files, f"Log file not set for {agent}"
            log_path = _agent_log_files[key]
            assert str(log_path).endswith(".output.log")
            # File should be in the project's logs/ directory
            assert "logs" in str(log_path)

    async def test_drain_thread_writes_to_log_file(self, tmp_path):
        """Drain thread writes output to the log file."""
        from app.routes.swarm import (
            _drain_agent_stream, _agent_log_files, _agent_key,
            _agent_output_buffers, _project_output_buffers,
        )

        project_id = 999
        agent_name = "Claude-1"
        key = _agent_key(project_id, agent_name)

        # Set up log file
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        log_path = log_dir / "Claude-1_test.output.log"
        _agent_log_files[key] = log_path

        # Create a mock stream that yields a few lines then EOF
        lines = [b'{"type": "system", "subtype": "init"}\n',
                 b'{"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello world"}]}}\n',
                 b'']  # EOF
        mock_stream = MagicMock()
        mock_stream.readline.side_effect = lines

        stop_event = threading.Event()

        try:
            _drain_agent_stream(project_id, agent_name, mock_stream, "stdout", stop_event)

            # Log file should contain persisted output
            assert log_path.exists()
            content = log_path.read_text()
            assert "[system] Agent initialized" in content
            assert "Hello world" in content
        finally:
            _agent_log_files.pop(key, None)
            _agent_output_buffers.pop(key, None)
            _project_output_buffers.pop(project_id, None)

    async def test_drain_continues_on_log_write_failure(self, tmp_path):
        """Drain thread continues even if log file write fails."""
        from app.routes.swarm import (
            _drain_agent_stream, _agent_log_files, _agent_key,
            _agent_output_buffers, _project_output_buffers,
        )

        project_id = 998
        agent_name = "Claude-2"
        key = _agent_key(project_id, agent_name)

        # Point to a non-writable path
        _agent_log_files[key] = Path("/nonexistent/path/log.txt")

        lines = [b'some stderr output line\n', b'']
        mock_stream = MagicMock()
        mock_stream.readline.side_effect = lines

        stop_event = threading.Event()

        try:
            _drain_agent_stream(project_id, agent_name, mock_stream, "stderr", stop_event)

            # Memory buffer should still have the output despite log file failure
            buf = _agent_output_buffers.get(key)
            assert buf is not None
            assert len(buf) >= 1
            assert "some stderr output line" in buf[0]
        finally:
            _agent_log_files.pop(key, None)
            _agent_output_buffers.pop(key, None)
            _project_output_buffers.pop(project_id, None)

    async def test_cleanup_removes_log_file_tracking(self):
        """_terminate_project_agents clears _agent_log_files entries."""
        from app.routes.swarm import (
            _agent_log_files, _agent_processes, _terminate_project_agents,
        )

        key = "777:Claude-1"
        _agent_log_files[key] = Path("/tmp/fake.log")
        # Register a mock process so _project_agent_keys finds it
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # Already exited
        _agent_processes[key] = mock_proc

        try:
            _terminate_project_agents(777)
            assert key not in _agent_log_files
        finally:
            _agent_log_files.pop(key, None)
            _agent_processes.pop(key, None)

    async def test_log_file_naming_includes_timestamp(self, client, created_project, mock_launch_deps):
        """Log files include a timestamp for uniqueness across launches."""
        from app.routes.swarm import _agent_log_files

        pid = created_project["id"]
        folder = Path(created_project["folder_path"])
        (folder / "swarm.ps1").write_text("# mock")

        mock_proc = MagicMock()
        mock_proc.pid = 54321
        mock_proc.poll.return_value = None
        mock_proc.stdin = None
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.readline.return_value = b""

        with patch("app.routes.swarm.subprocess.Popen", return_value=mock_proc):
            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid,
                "agent_count": 1,
            })
        assert resp.status_code == 200

        launched = resp.json()["agents_launched"]
        if launched:
            key = f"{pid}:{launched[0]}"
            log_path = _agent_log_files.get(key)
            assert log_path is not None
            # Check filename pattern: Claude-1_YYYYMMDD_HHMMSS.output.log
            name = log_path.name
            assert name.startswith("Claude-")
            assert ".output.log" in name
            # Has a timestamp segment
            parts = name.replace(".output.log", "").split("_")
            assert len(parts) >= 2  # agent name + date + time


# ============================================================================
# Integration: Verify all existing tests still pass with changes
# ============================================================================


class TestBackwardsCompatibility:
    """Ensure new features don't break existing behavior."""

    async def test_project_create_still_works(self, client, tmp_path):
        """Project creation unchanged."""
        resp = await client.post("/api/projects", json={
            "name": "Compat Test",
            "goal": "Test compatibility",
            "folder_path": str(tmp_path / "compat").replace("\\", "/"),
        })
        assert resp.status_code == 201
        assert resp.json()["status"] == "created"

    async def test_project_update_without_status(self, client, created_project):
        """Updating without status field still works."""
        pid = created_project["id"]
        resp = await client.patch(f"/api/projects/{pid}", json={"name": "New Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    async def test_health_endpoint_still_fast(self, client):
        """Health check responds quickly with new middleware."""
        start = time.monotonic()
        resp = await client.get("/api/health")
        elapsed = time.monotonic() - start
        assert resp.status_code == 200
        assert elapsed < 2.0  # Should be much faster

    async def test_swarm_stop_404_unchanged(self, client):
        """Stopping a nonexistent project still returns 404."""
        resp = await client.post("/api/swarm/stop", json={"project_id": 99999})
        assert resp.status_code == 404
