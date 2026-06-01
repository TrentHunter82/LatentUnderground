"""Tests for supervisor visibility (UI surfacing of the supervisor task).

The supervisor is a backend asyncio task, not a Claude agent, so its
coordination work is normally invisible in the UI. These tests cover the
emitters that surface it: a project-buffer line (polled by the Output view)
plus a live ``supervisor`` WebSocket event (rendered by the Logs view).
"""

import inspect
from unittest.mock import AsyncMock, patch

import pytest

from app.routes import swarm

# A project id unlikely to collide with fixture-created projects.
_PID = 987654


@pytest.fixture(autouse=True)
def _clean_buffers():
    """Prevent module-level buffer state from leaking across tests."""
    swarm._project_output_buffers.pop(_PID, None)
    yield
    swarm._project_output_buffers.pop(_PID, None)


class TestSupervisorEmitters:
    def test_buffer_emit_appends_supervisor_tagged_line(self):
        """_supervisor_buffer_emit tags lines so the UI can attribute them."""
        swarm._supervisor_buffer_emit(_PID, "Monitoring 2 agent(s), 2 alive")
        buf = list(swarm._project_output_buffers[_PID])
        assert buf == ["[supervisor] Monitoring 2 agent(s), 2 alive"]

    async def test_emit_writes_buffer_and_broadcasts_ws_event(self):
        """_supervisor_emit surfaces to BOTH the buffer and a live WS event."""
        with patch.object(swarm.ws_manager, "broadcast", new=AsyncMock()) as bcast:
            await swarm._supervisor_emit(_PID, "Supervisor started: monitoring agents")

        # Buffer line present and tagged
        buf = list(swarm._project_output_buffers[_PID])
        assert buf == ["[supervisor] Supervisor started: monitoring agents"]

        # WS event broadcast with the contract the frontend LogViewer consumes
        bcast.assert_awaited_once()
        payload = bcast.await_args.args[0]
        assert payload["type"] == "supervisor"
        assert payload["project_id"] == _PID
        assert payload["line"] == "Supervisor started: monitoring agents"

    async def test_emit_survives_broadcast_failure(self):
        """A WS broadcast failure must not break supervisor monitoring."""
        with patch.object(
            swarm.ws_manager, "broadcast", new=AsyncMock(side_effect=RuntimeError("ws down"))
        ):
            # Should not raise — buffer write still happens.
            await swarm._supervisor_emit(_PID, "Monitoring 1 agent(s), 1 alive")
        buf = list(swarm._project_output_buffers[_PID])
        assert buf == ["[supervisor] Monitoring 1 agent(s), 1 alive"]


class TestSupervisorLoopWiring:
    """Source-level guards that the loop actually uses the emitters."""

    def test_loop_announces_start_via_emit(self):
        source = inspect.getsource(swarm._supervisor_loop)
        assert 'await _supervisor_emit(project_id, "Supervisor started' in source

    def test_loop_emits_periodic_heartbeat(self):
        source = inspect.getsource(swarm._supervisor_loop)
        # Heartbeat is emitted while agents are alive, showing live coordination.
        assert "Monitoring " in source
        assert "_any_agent_alive(project_id)" in source
        assert "alive" in source

    def test_cancellation_uses_sync_buffer_emit(self):
        """Cancellation path must not await a broadcast (task is being torn down)."""
        source = inspect.getsource(swarm._supervisor_loop)
        assert '_supervisor_buffer_emit(project_id, "Supervisor cancelled")' in source
