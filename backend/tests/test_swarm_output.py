"""Tests for swarm output endpoint (GET /api/swarm/output/{project_id})."""

import pytest
from unittest.mock import patch


class TestSwarmOutput:
    """Tests for GET /api/swarm/output/{project_id}."""

    async def test_output_project_not_found(self, client):
        resp = await client.get("/api/swarm/output/9999")
        assert resp.status_code == 404

    async def test_output_empty_buffer(self, client, project_with_folder):
        """Output should return empty lines when no process has run."""
        pid = project_with_folder["id"]
        resp = await client.get(f"/api/swarm/output/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == pid
        assert data["offset"] == 0
        assert data["next_offset"] == 0
        assert data["lines"] == []

    async def test_output_with_buffered_lines(self, client, project_with_folder):
        """Output should return lines when buffer has content."""
        pid = project_with_folder["id"]

        # Manually populate the output buffer
        from app.routes.swarm import _output_buffers
        _output_buffers[pid] = [
            "[stdout] Starting swarm...",
            "[stdout] Phase 1 initiated",
            "[stderr] Warning: something",
        ]

        try:
            resp = await client.get(f"/api/swarm/output/{pid}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["project_id"] == pid
            assert data["offset"] == 0
            assert data["next_offset"] == 3
            assert len(data["lines"]) == 3
            assert "[stdout] Starting swarm..." in data["lines"][0]
        finally:
            _output_buffers.pop(pid, None)

    async def test_output_with_offset(self, client, project_with_folder):
        """Output with offset should skip earlier lines."""
        pid = project_with_folder["id"]

        from app.routes.swarm import _output_buffers
        _output_buffers[pid] = [
            "[stdout] Line 1",
            "[stdout] Line 2",
            "[stdout] Line 3",
            "[stdout] Line 4",
        ]

        try:
            resp = await client.get(f"/api/swarm/output/{pid}?offset=2")
            assert resp.status_code == 200
            data = resp.json()
            assert data["offset"] == 2
            assert data["next_offset"] == 4
            assert len(data["lines"]) == 2
            assert data["lines"][0] == "[stdout] Line 3"
            assert data["lines"][1] == "[stdout] Line 4"
        finally:
            _output_buffers.pop(pid, None)

    async def test_output_offset_beyond_buffer(self, client, project_with_folder):
        """Offset beyond buffer length returns empty lines."""
        pid = project_with_folder["id"]

        from app.routes.swarm import _output_buffers
        _output_buffers[pid] = ["[stdout] Only line"]

        try:
            resp = await client.get(f"/api/swarm/output/{pid}?offset=100")
            assert resp.status_code == 200
            data = resp.json()
            assert data["lines"] == []
            assert data["next_offset"] == 100
        finally:
            _output_buffers.pop(pid, None)
