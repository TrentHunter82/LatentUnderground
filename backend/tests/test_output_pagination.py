"""Tests for swarm output pagination (GET /api/swarm/output/{project_id}).

Tests offset parameter, empty buffers, buffer capping, and edge cases.
"""

import pytest
from app.routes.swarm import _output_buffers, _buffers_lock, _MAX_OUTPUT_LINES


class TestOutputPaginationBasic:
    """Basic output retrieval with offset parameter."""

    async def test_empty_buffer_returns_empty_lines(self, client, created_project):
        """No output buffer for project returns empty lines list."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/output/{pid}?offset=0")
        assert resp.status_code == 200
        body = resp.json()
        assert body["lines"] == []
        assert body["offset"] == 0
        assert body["next_offset"] == 0
        assert body["project_id"] == pid

    async def test_output_with_lines(self, client, created_project):
        """Buffer with lines returns them correctly."""
        pid = created_project["id"]
        with _buffers_lock:
            _output_buffers[pid] = ["[stdout] line 1", "[stdout] line 2", "[stdout] line 3"]

        resp = await client.get(f"/api/swarm/output/{pid}?offset=0")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["lines"]) == 3
        assert body["lines"][0] == "[stdout] line 1"
        assert body["next_offset"] == 3

    async def test_offset_skips_lines(self, client, created_project):
        """Offset parameter skips earlier lines."""
        pid = created_project["id"]
        with _buffers_lock:
            _output_buffers[pid] = [f"[stdout] line {i}" for i in range(10)]

        resp = await client.get(f"/api/swarm/output/{pid}?offset=5")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["lines"]) == 5
        assert body["lines"][0] == "[stdout] line 5"
        assert body["offset"] == 5
        assert body["next_offset"] == 10

    async def test_offset_beyond_buffer_returns_empty(self, client, created_project):
        """Offset past end of buffer returns empty lines."""
        pid = created_project["id"]
        with _buffers_lock:
            _output_buffers[pid] = ["line 1", "line 2"]

        resp = await client.get(f"/api/swarm/output/{pid}?offset=10")
        assert resp.status_code == 200
        body = resp.json()
        assert body["lines"] == []
        assert body["next_offset"] == 10

    async def test_default_offset_is_zero(self, client, created_project):
        """No offset parameter defaults to 0."""
        pid = created_project["id"]
        with _buffers_lock:
            _output_buffers[pid] = ["line 1"]

        resp = await client.get(f"/api/swarm/output/{pid}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["lines"]) == 1
        assert body["offset"] == 0


class TestOutputPaginationEdgeCases:
    """Edge cases and error conditions for output pagination."""

    async def test_nonexistent_project_returns_404(self, client):
        """Output for non-existent project returns 404."""
        resp = await client.get("/api/swarm/output/99999?offset=0")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    async def test_negative_offset(self, client, created_project):
        """Negative offset uses Python slice behavior (tail of list)."""
        pid = created_project["id"]
        with _buffers_lock:
            _output_buffers[pid] = ["line 1", "line 2", "line 3"]

        resp = await client.get(f"/api/swarm/output/{pid}?offset=-2")
        assert resp.status_code == 200
        body = resp.json()
        # Python list[-2:] gives last 2 elements
        assert len(body["lines"]) == 2

    async def test_buffer_capping_at_max_lines(self, client, created_project):
        """Buffer should not exceed _MAX_OUTPUT_LINES."""
        pid = created_project["id"]
        # Fill buffer beyond max
        with _buffers_lock:
            _output_buffers[pid] = [f"line {i}" for i in range(_MAX_OUTPUT_LINES + 100)]
            # Manually trim like _drain_stream_sync does
            buf = _output_buffers[pid]
            if len(buf) > _MAX_OUTPUT_LINES:
                del buf[: len(buf) - _MAX_OUTPUT_LINES]

        resp = await client.get(f"/api/swarm/output/{pid}?offset=0&limit={_MAX_OUTPUT_LINES}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["lines"]) == _MAX_OUTPUT_LINES

    async def test_incremental_polling(self, client, created_project):
        """Simulate incremental polling: get offset, add lines, poll again."""
        pid = created_project["id"]
        with _buffers_lock:
            _output_buffers[pid] = ["line 1", "line 2"]

        # First poll
        resp = await client.get(f"/api/swarm/output/{pid}?offset=0")
        next_offset = resp.json()["next_offset"]
        assert next_offset == 2

        # Add more lines
        with _buffers_lock:
            _output_buffers[pid].extend(["line 3", "line 4", "line 5"])

        # Second poll with previous next_offset
        resp = await client.get(f"/api/swarm/output/{pid}?offset={next_offset}")
        body = resp.json()
        assert len(body["lines"]) == 3
        assert body["lines"][0] == "line 3"
        assert body["next_offset"] == 5

    async def test_response_structure(self, client, created_project):
        """Verify all expected fields in the response."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/output/{pid}?offset=0")
        assert resp.status_code == 200
        body = resp.json()
        assert "project_id" in body
        assert "offset" in body
        assert "next_offset" in body
        assert "lines" in body
        assert "total" in body
        assert "limit" in body
        assert "has_more" in body
        assert isinstance(body["lines"], list)

    async def test_limit_parameter(self, client, created_project):
        """Limit parameter caps the number of returned lines."""
        pid = created_project["id"]
        with _buffers_lock:
            _output_buffers[pid] = [f"line {i}" for i in range(50)]

        resp = await client.get(f"/api/swarm/output/{pid}?offset=0&limit=10")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["lines"]) == 10
        assert body["has_more"] is True
        assert body["total"] == 50
        assert body["next_offset"] == 10

    async def test_limit_and_offset_combined(self, client, created_project):
        """Limit and offset work together for pagination."""
        pid = created_project["id"]
        with _buffers_lock:
            _output_buffers[pid] = [f"line {i}" for i in range(30)]

        # Get second page
        resp = await client.get(f"/api/swarm/output/{pid}?offset=10&limit=10")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["lines"]) == 10
        assert body["lines"][0] == "line 10"
        assert body["has_more"] is True
        assert body["next_offset"] == 20

    async def test_limit_capped_at_max(self, client, created_project):
        """Limit larger than _MAX_OUTPUT_LINES is capped."""
        pid = created_project["id"]
        with _buffers_lock:
            _output_buffers[pid] = ["line"]

        resp = await client.get(f"/api/swarm/output/{pid}?offset=0&limit=9999")
        assert resp.status_code == 200
        body = resp.json()
        assert body["limit"] == _MAX_OUTPUT_LINES
