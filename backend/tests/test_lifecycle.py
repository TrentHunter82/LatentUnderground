"""E2E lifecycle test: create -> configure -> launch -> stop -> history -> stats -> delete.

This test exercises the complete happy path through the API, verifying that
all the pieces work together correctly as an integrated system.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestFullProjectLifecycle:
    """Full project lifecycle: create, configure, launch, stop, verify history/stats, delete."""

    async def test_complete_lifecycle(self, client, mock_project_folder):
        """The complete happy path: every major API in sequence."""
        # -- 1. Create project --
        create_resp = await client.post("/api/projects", json={
            "name": "Lifecycle Test",
            "goal": "Prove end-to-end correctness",
            "project_type": "CLI Tool",
            "tech_stack": "Python",
            "complexity": "Simple",
            "requirements": "All tests pass",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        assert create_resp.status_code == 201
        project = create_resp.json()
        pid = project["id"]
        assert project["name"] == "Lifecycle Test"
        assert project["status"] == "created"

        # -- 2. Configure project --
        config_resp = await client.patch(f"/api/projects/{pid}/config", json={
            "agent_count": 6,
            "max_phases": 5,
            "custom_prompts": "Focus on integration tests",
        })
        assert config_resp.status_code == 200
        config_data = config_resp.json()
        assert config_data["config"]["agent_count"] == 6
        assert config_data["config"]["max_phases"] == 5
        assert config_data["config"]["custom_prompts"] == "Focus on integration tests"

        # -- 3. Verify config persists on project fetch --
        project_resp = await client.get(f"/api/projects/{pid}")
        assert project_resp.status_code == 200
        saved_config = json.loads(project_resp.json()["config"])
        assert saved_config["agent_count"] == 6
        assert saved_config["max_phases"] == 5

        # -- 4. Check initial status --
        status_resp = await client.get(f"/api/swarm/status/{pid}")
        assert status_resp.status_code == 200
        status = status_resp.json()
        assert status["status"] == "created"
        assert status["tasks"]["total"] == 4
        assert status["tasks"]["done"] == 2
        assert status["signals"]["backend-ready"] is True

        # -- 5. Launch swarm (mocked subprocess) --
        (mock_project_folder / "swarm.ps1").write_text("# Mock swarm script")

        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.stdout = MagicMock()
            mock_process.stderr = MagicMock()
            mock_popen.return_value = mock_process

            launch_resp = await client.post("/api/swarm/launch", json={
                "project_id": pid,
            })
            assert launch_resp.status_code == 200
            assert launch_resp.json()["status"] == "launched"
            assert launch_resp.json()["pid"] == 12345

        # -- 6. Verify project status is now 'running' --
        project_resp = await client.get(f"/api/projects/{pid}")
        assert project_resp.json()["status"] == "running"
        assert project_resp.json()["swarm_pid"] == 12345

        # -- 7. Check history shows a running run --
        history_resp = await client.get(f"/api/swarm/history/{pid}")
        assert history_resp.status_code == 200
        runs = history_resp.json()["runs"]
        assert len(runs) == 1
        assert runs[0]["status"] == "running"
        assert runs[0]["ended_at"] is None

        # -- 8. Stop swarm --
        stop_resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert stop_resp.status_code == 200
        assert stop_resp.json()["status"] == "stopped"

        # -- 9. Verify project is stopped --
        project_resp = await client.get(f"/api/projects/{pid}")
        assert project_resp.json()["status"] == "stopped"
        assert project_resp.json()["swarm_pid"] is None

        # -- 10. Check history shows stopped run with end time --
        history_resp = await client.get(f"/api/swarm/history/{pid}")
        runs = history_resp.json()["runs"]
        assert len(runs) == 1
        assert runs[0]["status"] == "stopped"
        assert runs[0]["ended_at"] is not None

        # -- 11. Check stats reflect the run --
        stats_resp = await client.get(f"/api/projects/{pid}/stats")
        assert stats_resp.status_code == 200
        stats = stats_resp.json()
        assert stats["total_runs"] == 1
        assert stats["avg_duration_seconds"] is not None

        # -- 12. Update project metadata --
        update_resp = await client.patch(f"/api/projects/{pid}", json={
            "name": "Lifecycle Test - Complete",
            "status": "completed",
        })
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "Lifecycle Test - Complete"
        assert update_resp.json()["status"] == "completed"

        # -- 13. Verify in project list --
        list_resp = await client.get("/api/projects")
        assert list_resp.status_code == 200
        found = [p for p in list_resp.json() if p["id"] == pid]
        assert len(found) == 1
        assert found[0]["name"] == "Lifecycle Test - Complete"

        # -- 14. Delete project --
        del_resp = await client.delete(f"/api/projects/{pid}")
        assert del_resp.status_code == 204

        # -- 15. Verify deletion --
        get_resp = await client.get(f"/api/projects/{pid}")
        assert get_resp.status_code == 404

    async def test_multiple_runs_accumulate_stats(self, client, mock_project_folder):
        """Multiple launch/stop cycles accumulate in history and stats."""
        (mock_project_folder / "swarm.ps1").write_text("# Mock")

        # Create project
        resp = await client.post("/api/projects", json={
            "name": "Multi-Run",
            "goal": "Test multiple runs",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        # Run 3 launch/stop cycles
        for i in range(3):
            with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
                mock_process = MagicMock()
                mock_process.pid = 10000 + i
                mock_process.stdout = MagicMock()
                mock_process.stderr = MagicMock()
                mock_process.wait = MagicMock()
                mock_popen.return_value = mock_process

                await client.post("/api/swarm/launch", json={"project_id": pid})
            await client.post("/api/swarm/stop", json={"project_id": pid})

        # Verify 3 runs in history
        history_resp = await client.get(f"/api/swarm/history/{pid}")
        assert len(history_resp.json()["runs"]) == 3

        # Verify stats
        stats_resp = await client.get(f"/api/projects/{pid}/stats")
        assert stats_resp.json()["total_runs"] == 3

    async def test_config_round_trip(self, client, sample_project_data):
        """Config saved via PATCH round-trips correctly through GET."""
        resp = await client.post("/api/projects", json=sample_project_data)
        pid = resp.json()["id"]

        # Save config
        config = {"agent_count": 8, "max_phases": 10, "custom_prompts": "Use TDD"}
        await client.patch(f"/api/projects/{pid}/config", json=config)

        # Fetch and verify
        project = (await client.get(f"/api/projects/{pid}")).json()
        stored = json.loads(project["config"])
        assert stored["agent_count"] == 8
        assert stored["max_phases"] == 10
        assert stored["custom_prompts"] == "Use TDD"

    async def test_stop_without_launch_is_safe(self, client, mock_project_folder):
        """Stopping a project that was never launched should not error."""
        resp = await client.post("/api/projects", json={
            "name": "Never Launched",
            "goal": "Test stop safety",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        # Stop without launching - should work fine
        stop_resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert stop_resp.status_code == 200
        assert stop_resp.json()["status"] == "stopped"

    async def test_history_empty_for_new_project(self, client, sample_project_data):
        """New project has empty history and zero stats."""
        resp = await client.post("/api/projects", json=sample_project_data)
        pid = resp.json()["id"]

        history = (await client.get(f"/api/swarm/history/{pid}")).json()
        assert history["runs"] == []

        stats = (await client.get(f"/api/projects/{pid}/stats")).json()
        assert stats["total_runs"] == 0
        assert stats["avg_duration_seconds"] is None
        assert stats["total_tasks_completed"] == 0

    async def test_status_with_live_agents(self, client, mock_project_folder):
        """Status endpoint returns agent heartbeats and signal data from filesystem."""
        resp = await client.post("/api/projects", json={
            "name": "Agent Status Test",
            "goal": "Verify status reads filesystem",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        status = (await client.get(f"/api/swarm/status/{pid}")).json()

        # Should have 2 agents from mock_project_folder fixture
        assert len(status["agents"]) == 2
        agent_names = {a["name"] for a in status["agents"]}
        assert "Claude-1" in agent_names
        assert "Claude-2" in agent_names

        # Should have phase info
        assert status["phase"] is not None
        assert status["phase"]["Phase"] == 1
        assert status["phase"]["MaxPhases"] == 3

        # Signals
        assert status["signals"]["backend-ready"] is True
        assert status["signals"]["frontend-ready"] is False

    async def test_file_operations_within_lifecycle(self, client, mock_project_folder):
        """File read/write works within the project lifecycle context."""
        resp = await client.post("/api/projects", json={
            "name": "File Ops Test",
            "goal": "Test file operations",
            "folder_path": str(mock_project_folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        # Read tasks file
        read_resp = await client.get(f"/api/files/tasks/TASKS.md?project_id={pid}")
        assert read_resp.status_code == 200
        assert "Task 1" in read_resp.json()["content"]

        # Write updated tasks
        new_content = "# Tasks\n- [x] All Done\n"
        write_resp = await client.put("/api/files/tasks/TASKS.md", json={
            "content": new_content,
            "project_id": pid,
        })
        assert write_resp.status_code == 200

        # Verify write persisted
        read_resp2 = await client.get(f"/api/files/tasks/TASKS.md?project_id={pid}")
        assert "All Done" in read_resp2.json()["content"]

        # Status should reflect updated task progress
        status = (await client.get(f"/api/swarm/status/{pid}")).json()
        assert status["tasks"]["done"] == 1
        assert status["tasks"]["total"] == 1
        assert status["tasks"]["percent"] == 100.0
