"""Tests for project stats and config endpoints."""

import json
import pytest
from unittest.mock import AsyncMock, patch


class TestProjectStats:
    """Tests for GET /api/projects/{id}/stats."""

    async def test_stats_no_runs(self, client, created_project):
        """Stats with no runs should show zeros."""
        pid = created_project["id"]
        resp = await client.get(f"/api/projects/{pid}/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == pid
        assert data["total_runs"] == 0
        assert data["avg_duration_seconds"] is None
        assert data["total_tasks_completed"] == 0

    async def test_stats_not_found(self, client):
        """Stats for nonexistent project returns 404."""
        resp = await client.get("/api/projects/9999/stats")
        assert resp.status_code == 404

    async def test_stats_with_completed_runs(self, client, mock_project_folder):
        """Stats should aggregate completed run data."""
        (mock_project_folder / "swarm.ps1").write_text("# Mock")
        (mock_project_folder / "stop-swarm.ps1").write_text("# Mock stop")
        resp = await client.post("/api/projects", json={
            "name": "Stats Test",
            "goal": "Test stats",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_process = AsyncMock()
            mock_process.pid = 100
            mock_process.wait = AsyncMock()
            mock_exec.return_value = mock_process

            # Run 1: launch + stop
            await client.post("/api/swarm/launch", json={"project_id": pid})
            await client.post("/api/swarm/stop", json={"project_id": pid})

        resp = await client.get(f"/api/projects/{pid}/stats")
        data = resp.json()
        assert data["total_runs"] == 1
        # Duration should be 0 or near 0 since launch+stop are near-instant
        assert data["avg_duration_seconds"] is not None

    async def test_stats_total_runs_count(self, client, mock_project_folder):
        """total_runs should count all runs (running and stopped)."""
        (mock_project_folder / "swarm.ps1").write_text("# Mock")
        resp = await client.post("/api/projects", json={
            "name": "Count Test",
            "goal": "Test run counting",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_process = AsyncMock()
            mock_process.pid = 200
            mock_exec.return_value = mock_process

            await client.post("/api/swarm/launch", json={"project_id": pid})
            await client.post("/api/swarm/launch", json={"project_id": pid})
            await client.post("/api/swarm/launch", json={"project_id": pid})

        resp = await client.get(f"/api/projects/{pid}/stats")
        assert resp.json()["total_runs"] == 3

    async def test_stats_has_expected_fields(self, client, created_project):
        """Stats response should have all expected fields."""
        pid = created_project["id"]
        resp = await client.get(f"/api/projects/{pid}/stats")
        data = resp.json()
        assert set(data.keys()) == {"project_id", "total_runs", "avg_duration_seconds", "total_tasks_completed"}


class TestProjectConfig:
    """Tests for PATCH /api/projects/{id}/config."""

    async def test_config_update(self, client, created_project):
        """Config should save agent settings."""
        pid = created_project["id"]
        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "agent_count": 6,
            "max_phases": 5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == pid
        assert data["config"]["agent_count"] == 6
        assert data["config"]["max_phases"] == 5

    async def test_config_not_found(self, client):
        """Config for nonexistent project returns 404."""
        resp = await client.patch("/api/projects/9999/config", json={"agent_count": 4})
        assert resp.status_code == 404

    async def test_config_partial_update(self, client, created_project):
        """Should accept partial config (only some fields)."""
        pid = created_project["id"]
        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "agent_count": 8,
        })
        assert resp.status_code == 200
        assert resp.json()["config"]["agent_count"] == 8
        # max_phases and custom_prompts should not be present (None excluded)
        assert "max_phases" not in resp.json()["config"]

    async def test_config_with_custom_prompts(self, client, created_project):
        """Should save custom prompts text."""
        pid = created_project["id"]
        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "agent_count": 4,
            "max_phases": 3,
            "custom_prompts": "Focus on backend performance",
        })
        assert resp.status_code == 200
        assert resp.json()["config"]["custom_prompts"] == "Focus on backend performance"

    async def test_config_empty_body(self, client, created_project):
        """Empty config should succeed with empty result."""
        pid = created_project["id"]
        resp = await client.patch(f"/api/projects/{pid}/config", json={})
        assert resp.status_code == 200
        assert resp.json()["config"] == {}
