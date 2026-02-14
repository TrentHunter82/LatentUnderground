"""End-to-end tests: create project, check status, read files, check logs."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestEndToEnd:
    """Full workflow test: create project -> check status -> read/write files."""

    async def test_full_workflow(self, client, mock_project_folder):
        """Create a project, check status, read files, update files."""
        # 1. Create project
        resp = await client.post("/api/projects", json={
            "name": "E2E Test Project",
            "goal": "End-to-end test",
            "project_type": "Web Application",
            "tech_stack": "Python FastAPI",
            "complexity": "Simple",
            "requirements": "Must pass E2E tests",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        assert resp.status_code == 201
        project = resp.json()
        pid = project["id"]
        assert project["name"] == "E2E Test Project"
        assert project["status"] == "created"

        # 2. Check swarm status
        resp = await client.get(f"/api/swarm/status/{pid}")
        assert resp.status_code == 200
        status = resp.json()
        assert status["tasks"]["total"] == 4
        assert status["tasks"]["done"] == 2
        assert status["signals"]["backend-ready"] is True

        # 3. Read tasks file
        resp = await client.get(f"/api/files/tasks/TASKS.md?project_id={pid}")
        assert resp.status_code == 200
        assert "Task 1" in resp.json()["content"]

        # 4. Write updated tasks
        resp = await client.put("/api/files/tasks/TASKS.md", json={
            "content": "# Tasks\n- [x] Task 1\n- [x] Task 2\n- [x] Task 3\n- [ ] Task 4\n",
            "project_id": pid,
        })
        assert resp.status_code == 200

        # 5. Verify status updates reflect new task progress
        resp = await client.get(f"/api/swarm/status/{pid}")
        assert resp.status_code == 200
        assert resp.json()["tasks"]["done"] == 3
        assert resp.json()["tasks"]["percent"] == 75.0

        # 6. Read logs
        resp = await client.get(f"/api/logs?project_id={pid}")
        assert resp.status_code == 200
        assert len(resp.json()["logs"]) >= 2

        # 7. Update project status
        resp = await client.patch(f"/api/projects/{pid}", json={"status": "running"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

        # 8. List projects includes our project
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        assert any(p["id"] == pid for p in resp.json())

        # 9. Stop swarm (no stop-swarm.ps1 but should still work)
        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"

        # 10. Verify project status after stop
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.json()["status"] == "stopped"

    async def test_launch_and_stop_workflow(self, client, mock_project_folder, mock_launch_deps):
        """Test launch -> status -> stop flow with mocked subprocess."""
        # Create swarm.ps1 and stop-swarm.ps1
        (mock_project_folder / "swarm.ps1").write_text("# Mock swarm")
        (mock_project_folder / "stop-swarm.ps1").write_text("# Mock stop")

        resp = await client.post("/api/projects", json={
            "name": "Launch Test",
            "goal": "Test launch flow",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        # Launch with mocked subprocess
        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 99999
            mock_process.poll.return_value = None
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_process.wait = MagicMock()
            mock_popen.return_value = mock_process

            # Launch
            resp = await client.post("/api/swarm/launch", json={"project_id": pid})
            assert resp.status_code == 200
            assert resp.json()["status"] == "launched"

            # Verify running
            resp = await client.get(f"/api/projects/{pid}")
            assert resp.json()["status"] == "running"

            # Stop
            resp = await client.post("/api/swarm/stop", json={"project_id": pid})
            assert resp.status_code == 200
            assert resp.json()["status"] == "stopped"

            # Verify stopped
            resp = await client.get(f"/api/projects/{pid}")
            assert resp.json()["status"] == "stopped"

    async def test_health_endpoint(self, client):
        """Test the health check endpoint."""
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["app"] == "Latent Underground"

    async def test_security_file_access(self, client, mock_project_folder):
        """Verify that only allowlisted files can be accessed."""
        resp = await client.post("/api/projects", json={
            "name": "Security Test",
            "goal": "Test security",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        # These should work (allowlisted)
        for path in ["tasks/TASKS.md", "tasks/lessons.md", "tasks/todo.md", "AGENTS.md", "progress.txt"]:
            resp = await client.get(f"/api/files/{path}?project_id={pid}")
            assert resp.status_code == 200, f"Should allow: {path}"

        # These should be blocked (non-allowlisted paths)
        for path in [".claude/swarm-config.json", "swarm.ps1", "logs/Claude-1.log", "run.py"]:
            resp = await client.get(f"/api/files/{path}?project_id={pid}")
            assert resp.status_code == 403, f"Should block: {path}"
