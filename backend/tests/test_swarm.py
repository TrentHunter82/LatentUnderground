"""Tests for swarm API endpoints (launch, stop, status)."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


class TestSwarmStatus:
    """Tests for GET /api/swarm/status/{project_id}."""

    async def test_status_with_full_folder(self, client, project_with_folder):
        pid = project_with_folder["id"]
        resp = await client.get(f"/api/swarm/status/{pid}")
        assert resp.status_code == 200
        data = resp.json()

        assert data["project_id"] == pid
        assert data["status"] == "created"

        # Check agents (heartbeats)
        agents = {a["name"]: a for a in data["agents"]}
        assert "Claude-1" in agents
        assert "Claude-2" in agents
        assert agents["Claude-1"]["last_heartbeat"] == "2026-02-06 14:00:00"

        # Check signals
        assert data["signals"]["backend-ready"] is True
        assert data["signals"]["frontend-ready"] is False
        assert data["signals"]["tests-passing"] is False
        assert data["signals"]["phase-complete"] is False

        # Check tasks
        assert data["tasks"]["total"] == 4
        assert data["tasks"]["done"] == 2
        assert data["tasks"]["percent"] == 50.0

        # Check phase
        assert data["phase"]["Phase"] == 1
        assert data["phase"]["MaxPhases"] == 3

    async def test_status_not_found(self, client):
        resp = await client.get("/api/swarm/status/9999")
        assert resp.status_code == 404

    async def test_status_empty_folder(self, client, tmp_path):
        """Test status when project folder has no .claude directory."""
        empty_folder = tmp_path / "empty_project"
        empty_folder.mkdir()

        resp = await client.post("/api/projects", json={
            "name": "Empty Project",
            "goal": "Test empty",
            "folder_path": str(empty_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        resp = await client.get(f"/api/swarm/status/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agents"] == []
        assert all(v is False for v in data["signals"].values())
        assert data["tasks"]["total"] == 0
        assert data["phase"] is None


class TestSwarmLaunch:
    """Tests for POST /api/swarm/launch."""

    async def test_launch_project_not_found(self, client):
        resp = await client.post("/api/swarm/launch", json={"project_id": 9999})
        assert resp.status_code == 404

    async def test_launch_no_swarm_script(self, client, tmp_path):
        """Launch should fail if swarm.ps1 doesn't exist in project folder."""
        empty_folder = tmp_path / "no_swarm"
        empty_folder.mkdir()

        resp = await client.post("/api/projects", json={
            "name": "No Swarm",
            "goal": "Test missing script",
            "folder_path": str(empty_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        resp = await client.post("/api/swarm/launch", json={"project_id": pid})
        assert resp.status_code == 400
        assert "swarm.ps1 not found" in resp.json()["detail"]

    async def test_launch_with_swarm_script(self, client, mock_project_folder):
        """Launch should succeed when swarm.ps1 exists."""
        # Create swarm.ps1 in mock folder
        (mock_project_folder / "swarm.ps1").write_text("# Mock swarm script")

        resp = await client.post("/api/projects", json={
            "name": "Launchable",
            "goal": "Test launch",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_process = AsyncMock()
            mock_process.pid = 12345
            mock_exec.return_value = mock_process

            resp = await client.post("/api/swarm/launch", json={"project_id": pid})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "launched"
            assert data["pid"] == 12345
            assert data["project_id"] == pid

            # Verify project status was updated to 'running'
            resp = await client.get(f"/api/projects/{pid}")
            assert resp.json()["status"] == "running"


class TestSwarmStop:
    """Tests for POST /api/swarm/stop."""

    async def test_stop_project_not_found(self, client):
        resp = await client.post("/api/swarm/stop", json={"project_id": 9999})
        assert resp.status_code == 404

    async def test_stop_with_script(self, client, mock_project_folder):
        """Stop should call stop-swarm.ps1 and update project status."""
        (mock_project_folder / "stop-swarm.ps1").write_text("# Mock stop script")

        resp = await client.post("/api/projects", json={
            "name": "Stoppable",
            "goal": "Test stop",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_process = AsyncMock()
            mock_process.wait = AsyncMock()
            mock_exec.return_value = mock_process

            resp = await client.post("/api/swarm/stop", json={"project_id": pid})
            assert resp.status_code == 200
            assert resp.json()["status"] == "stopped"

            # Verify project status updated
            resp = await client.get(f"/api/projects/{pid}")
            assert resp.json()["status"] == "stopped"

    async def test_stop_without_script(self, client, tmp_path):
        """Stop should still succeed even without stop-swarm.ps1."""
        folder = tmp_path / "no_stop"
        folder.mkdir()

        resp = await client.post("/api/projects", json={
            "name": "No Stop Script",
            "goal": "Test graceful",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"
