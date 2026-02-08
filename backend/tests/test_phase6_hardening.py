"""Tests for Phase 6 hardening: validation constraints and safety constants."""

import threading

import pytest


# ── Swarm Launch Validation ──────────────────────────────────────────────


class TestSwarmLaunchValidation:
    """Verify SwarmLaunchRequest Field constraints (agent_count, max_phases)."""

    @pytest.mark.asyncio
    async def test_agent_count_zero_rejected(self, client, created_project):
        """agent_count=0 should be rejected (minimum is 1)."""
        resp = await client.post("/api/swarm/launch", json={
            "project_id": created_project["id"],
            "agent_count": 0,
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_agent_count_over_max_rejected(self, client, created_project):
        """agent_count=17 should be rejected (maximum is 16)."""
        resp = await client.post("/api/swarm/launch", json={
            "project_id": created_project["id"],
            "agent_count": 17,
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_max_phases_zero_rejected(self, client, created_project):
        """max_phases=0 should be rejected (minimum is 1)."""
        resp = await client.post("/api/swarm/launch", json={
            "project_id": created_project["id"],
            "max_phases": 0,
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_max_phases_over_max_rejected(self, client, created_project):
        """max_phases=25 should be rejected (maximum is 24)."""
        resp = await client.post("/api/swarm/launch", json={
            "project_id": created_project["id"],
            "max_phases": 25,
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_boundary_values_accepted(self, client, created_project):
        """agent_count=1 and max_phases=1 pass validation (404 on swarm.ps1 is fine)."""
        resp = await client.post("/api/swarm/launch", json={
            "project_id": created_project["id"],
            "agent_count": 1,
            "max_phases": 1,
        })
        # Should pass validation but fail on missing swarm.ps1 -> 400
        assert resp.status_code == 400
        assert "swarm.ps1" in resp.json()["detail"]


# ── Project Create Validation ────────────────────────────────────────────


class TestProjectCreateValidation:
    """Verify ProjectCreate Field constraints."""

    @pytest.mark.asyncio
    async def test_empty_name_rejected(self, client):
        """Empty name should be rejected (min_length=1)."""
        resp = await client.post("/api/projects", json={
            "name": "",
            "goal": "Valid goal",
            "folder_path": "F:/Test",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_name_over_max_rejected(self, client):
        """Name exceeding 200 chars should be rejected."""
        resp = await client.post("/api/projects", json={
            "name": "x" * 201,
            "goal": "Valid goal",
            "folder_path": "F:/Test",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_goal_over_max_rejected(self, client):
        """Goal exceeding 2000 chars should be rejected."""
        resp = await client.post("/api/projects", json={
            "name": "Valid name",
            "goal": "x" * 2001,
            "folder_path": "F:/Test",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_folder_path_rejected(self, client):
        """Empty folder_path should be rejected (min_length=1)."""
        resp = await client.post("/api/projects", json={
            "name": "Valid name",
            "goal": "Valid goal",
            "folder_path": "",
        })
        assert resp.status_code == 422


# ── Buffer/Lock Constants ────────────────────────────────────────────────


class TestBufferLockExists:
    """Verify swarm module safety constants and lock type."""

    def test_buffers_lock_is_threading_lock(self):
        from app.routes.swarm import _buffers_lock
        assert isinstance(_buffers_lock, type(threading.Lock()))

    def test_max_output_lines(self):
        from app.routes.swarm import _MAX_OUTPUT_LINES
        assert _MAX_OUTPUT_LINES == 500

    def test_max_content_size(self):
        from app.routes.files import MAX_CONTENT_SIZE
        assert MAX_CONTENT_SIZE == 1_000_000
