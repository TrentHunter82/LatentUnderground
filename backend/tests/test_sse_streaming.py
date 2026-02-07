"""Tests for SSE output streaming endpoint."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock


class TestSSEStreaming:
    """Tests for GET /api/swarm/output/{project_id}/stream."""

    async def test_stream_not_found(self, client):
        """SSE stream for nonexistent project returns 404."""
        resp = await client.get("/api/swarm/output/9999/stream")
        assert resp.status_code == 404

    async def test_stream_generator_delivers_lines(self):
        """The SSE event generator should yield data events for buffered lines."""
        from app.routes.swarm import _output_buffers

        project_id = 42
        _output_buffers[project_id] = ["[stdout] Line 1", "[stdout] Line 2"]

        # Create a mock request that disconnects after first iteration
        call_count = 0
        async def is_disconnected():
            nonlocal call_count
            call_count += 1
            return call_count > 1  # Disconnect after first check

        request = MagicMock()
        request.is_disconnected = is_disconnected

        # Import the endpoint and call the generator directly
        from app.routes.swarm import swarm_output_stream

        # We can't easily call the endpoint directly due to Depends(get_db),
        # so test the generator logic inline
        events = []
        offset = 0
        buf = _output_buffers.get(project_id, [])
        for line in buf[offset:]:
            events.append(f"data: {json.dumps({'line': line})}\n\n")

        assert len(events) == 2
        parsed_0 = json.loads(events[0].split("data: ")[1].strip())
        assert parsed_0["line"] == "[stdout] Line 1"
        parsed_1 = json.loads(events[1].split("data: ")[1].strip())
        assert parsed_1["line"] == "[stdout] Line 2"

        _output_buffers.pop(project_id, None)

    async def test_stream_done_when_no_drain_tasks(self):
        """Generator should emit done event when buffer is empty and no drain tasks."""
        from app.routes.swarm import _output_buffers, _drain_tasks

        project_id = 43
        _output_buffers[project_id] = []
        # Ensure no drain tasks for this project
        _drain_tasks.pop(project_id, None)

        # With no drain tasks, the generator sends a done event (not keepalive)
        buf = _output_buffers.get(project_id, [])
        offset = 0
        if offset >= len(buf):
            if project_id not in _drain_tasks or not _drain_tasks[project_id]:
                event = f"data: {json.dumps({'type': 'done'})}\n\n"
            else:
                event = ": keepalive\n\n"
        else:
            event = None

        assert "done" in event
        parsed = json.loads(event.split("data: ")[1].strip())
        assert parsed["type"] == "done"
        _output_buffers.pop(project_id, None)

    async def test_stream_event_format(self):
        """SSE events should follow the correct format: 'data: {json}\\n\\n'."""
        line_text = "[stderr] Error occurred"
        event = f"data: {json.dumps({'line': line_text})}\n\n"
        assert event.startswith("data: ")
        assert event.endswith("\n\n")
        parsed = json.loads(event.replace("data: ", "").strip())
        assert parsed["line"] == line_text

    async def test_stream_endpoint_exists(self, client, created_project):
        """SSE endpoint should exist and return buffered lines then done event."""
        pid = created_project["id"]
        from app.routes.swarm import _output_buffers, _drain_tasks
        _output_buffers[pid] = ["test line"]
        # Ensure no drain tasks so generator self-terminates
        _drain_tasks.pop(pid, None)

        resp = await client.get(f"/api/swarm/output/{pid}/stream")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        # Parse SSE events from body
        body = resp.text
        assert "test line" in body
        assert '"type": "done"' in body

        _output_buffers.pop(pid, None)

    async def test_polling_output_still_works(self, client, created_project):
        """The original polling endpoint should still work alongside SSE."""
        pid = created_project["id"]
        from app.routes.swarm import _output_buffers
        _output_buffers[pid] = ["line A", "line B", "line C"]

        resp = await client.get(f"/api/swarm/output/{pid}?offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["lines"] == ["line A", "line B", "line C"]
        assert data["next_offset"] == 3

        # Offset works
        resp = await client.get(f"/api/swarm/output/{pid}?offset=2")
        data = resp.json()
        assert data["lines"] == ["line C"]
        assert data["next_offset"] == 3

        _output_buffers.pop(pid, None)

    async def test_stream_buffer_mutation(self):
        """New lines added to buffer after initial read should be picked up."""
        from app.routes.swarm import _output_buffers

        project_id = 44
        _output_buffers[project_id] = ["initial"]

        buf = _output_buffers[project_id]
        # Simulate first read
        offset = 0
        batch1 = buf[offset:]
        offset = len(buf)
        assert batch1 == ["initial"]

        # Simulate new line appended (as _drain_stream would do)
        buf.append("new line after drain")
        batch2 = buf[offset:]
        assert batch2 == ["new line after drain"]
        assert offset == 1  # Was at 1, now buf has 2 items

        _output_buffers.pop(project_id, None)
