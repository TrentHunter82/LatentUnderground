"""Tests for swarm run history tracking and API."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestSwarmRunHistory:
    """Tests for GET /api/swarm/history/{project_id}."""

    async def test_history_empty(self, client, created_project):
        """History should be empty for a project with no runs."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/history/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == pid
        assert data["runs"] == []

    async def test_history_not_found(self, client):
        """History for nonexistent project returns 404."""
        resp = await client.get("/api/swarm/history/9999")
        assert resp.status_code == 404

    async def test_history_records_launch(self, client, mock_project_folder, mock_launch_deps):
        """Launching a swarm should create a history record."""
        (mock_project_folder / "swarm.ps1").write_text("# Mock")
        resp = await client.post("/api/projects", json={
            "name": "History Test",
            "goal": "Test history recording",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_popen.return_value = mock_process

            await client.post("/api/swarm/launch", json={"project_id": pid})

        resp = await client.get(f"/api/swarm/history/{pid}")
        data = resp.json()
        assert len(data["runs"]) == 1
        assert data["runs"][0]["status"] == "running"
        assert data["runs"][0]["project_id"] == pid
        assert data["runs"][0]["started_at"] is not None
        assert data["runs"][0]["ended_at"] is None

    async def test_history_records_stop(self, client, mock_project_folder, mock_launch_deps):
        """Stopping a swarm should close the run record."""
        (mock_project_folder / "swarm.ps1").write_text("# Mock")
        (mock_project_folder / "stop-swarm.ps1").write_text("# Mock stop")
        resp = await client.post("/api/projects", json={
            "name": "Stop History Test",
            "goal": "Test stop recording",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.wait = MagicMock()
            mock_popen.return_value = mock_process

            await client.post("/api/swarm/launch", json={"project_id": pid})
            await client.post("/api/swarm/stop", json={"project_id": pid})

        resp = await client.get(f"/api/swarm/history/{pid}")
        data = resp.json()
        assert len(data["runs"]) == 1
        run = data["runs"][0]
        assert run["status"] == "stopped"
        assert run["ended_at"] is not None
        assert run["duration_seconds"] is not None

    async def test_history_multiple_runs(self, client, mock_project_folder, mock_launch_deps):
        """Multiple launches create separate history records."""
        (mock_project_folder / "swarm.ps1").write_text("# Mock")
        (mock_project_folder / "stop-swarm.ps1").write_text("# Mock stop")
        resp = await client.post("/api/projects", json={
            "name": "Multi Run Test",
            "goal": "Test multiple runs",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 11111
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.wait = MagicMock()
            mock_popen.return_value = mock_process

            # Run 1: launch + stop
            await client.post("/api/swarm/launch", json={"project_id": pid})
            await client.post("/api/swarm/stop", json={"project_id": pid})

            # Run 2: launch only (still running)
            mock_process.pid = 22222
            await client.post("/api/swarm/launch", json={"project_id": pid})

        resp = await client.get(f"/api/swarm/history/{pid}")
        data = resp.json()
        assert len(data["runs"]) == 2
        # Most recent first
        assert data["runs"][0]["status"] == "running"
        assert data["runs"][1]["status"] == "stopped"

    async def test_history_ordered_by_started_at_desc(self, client, mock_project_folder, mock_launch_deps):
        """Runs should be ordered most-recent-first."""
        (mock_project_folder / "swarm.ps1").write_text("# Mock")
        resp = await client.post("/api/projects", json={
            "name": "Order Test",
            "goal": "Test ordering",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 100
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_popen.return_value = mock_process

            await client.post("/api/swarm/launch", json={"project_id": pid})
            await client.post("/api/swarm/launch", json={"project_id": pid})

        resp = await client.get(f"/api/swarm/history/{pid}")
        data = resp.json()
        assert len(data["runs"]) == 2
        # Most recent has higher id
        assert data["runs"][0]["id"] > data["runs"][1]["id"]

    async def test_history_isolated_per_project(self, client, mock_project_folder, tmp_path, mock_launch_deps):
        """Each project should only see its own history."""
        (mock_project_folder / "swarm.ps1").write_text("# Mock")

        # Create two projects
        resp1 = await client.post("/api/projects", json={
            "name": "Project A",
            "goal": "Test isolation A",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid_a = resp1.json()["id"]

        folder_b = tmp_path / "project_b"
        folder_b.mkdir()
        (folder_b / "swarm.ps1").write_text("# Mock")
        # Create prompt files for project_b (mock_launch_deps creates them based on folder)
        prompts_b = folder_b / ".claude" / "prompts"
        prompts_b.mkdir(parents=True, exist_ok=True)
        for i in range(1, 5):
            (prompts_b / f"Claude-{i}.txt").write_text(f"Mock prompt for Claude-{i}")
        resp2 = await client.post("/api/projects", json={
            "name": "Project B",
            "goal": "Test isolation B",
            "folder_path": str(folder_b).replace("\\", "/"),
        })
        pid_b = resp2.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 100
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_popen.return_value = mock_process

            await client.post("/api/swarm/launch", json={"project_id": pid_a})
            await client.post("/api/swarm/launch", json={"project_id": pid_a})
            await client.post("/api/swarm/launch", json={"project_id": pid_b})

        resp_a = await client.get(f"/api/swarm/history/{pid_a}")
        resp_b = await client.get(f"/api/swarm/history/{pid_b}")
        assert len(resp_a.json()["runs"]) == 2
        assert len(resp_b.json()["runs"]) == 1

    async def test_history_run_has_all_fields(self, client, mock_project_folder, mock_launch_deps):
        """Each run record should have the expected fields."""
        (mock_project_folder / "swarm.ps1").write_text("# Mock")
        resp = await client.post("/api/projects", json={
            "name": "Fields Test",
            "goal": "Test fields",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 999
            mock_process.poll.return_value = None
            mock_process.stdout.readline.return_value = b""
            mock_process.stderr.readline.return_value = b""
            mock_popen.return_value = mock_process
            await client.post("/api/swarm/launch", json={"project_id": pid})

        resp = await client.get(f"/api/swarm/history/{pid}")
        run = resp.json()["runs"][0]
        expected_fields = {"id", "project_id", "started_at", "ended_at", "status",
                          "phase", "tasks_completed", "task_summary", "duration_seconds",
                          "label", "notes", "summary", "guardrail_results"}
        assert set(run.keys()) == expected_fields
