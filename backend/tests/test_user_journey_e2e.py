"""
Phase 16 - Complete User Journey E2E Test
Tests the full lifecycle: create project → configure → launch → monitor → stop → view history
All through the web API, simulating exactly what the frontend does.
"""
import pytest
import aiosqlite
from unittest.mock import MagicMock, patch, AsyncMock

pytestmark = pytest.mark.asyncio


class TestCompleteUserJourney:
    """
    Simulates the complete user journey through the web UI:
    1. Create a new project
    2. Configure agent settings
    3. Launch swarm
    4. Monitor status and agents
    5. View output (per-agent and combined)
    6. Stop individual agent
    7. Stop entire swarm
    8. View run history and stats
    9. Archive the project
    """

    async def test_full_lifecycle(self, client, mock_project_folder, mock_launch_deps):
        """Complete lifecycle from project creation to archival."""
        folder = str(mock_project_folder).replace("\\", "/")

        # === Step 1: Create project ===
        resp = await client.post("/api/projects", json={
            "name": "Journey Test",
            "goal": "Test the complete user journey",
            "type": "feature",
            "stack": "python,fastapi",
            "complexity": "medium",
            "requirements": "Must work end-to-end",
            "folder_path": folder,
        })
        assert resp.status_code == 201, f"Create failed: {resp.text}"
        project = resp.json()
        pid = project["id"]
        assert project["name"] == "Journey Test"
        assert project["status"] == "created"

        # === Step 2: Configure agent settings ===
        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "agent_count": 2,
            "max_phases": 5,
            "custom_prompts": "Focus on testing",
        })
        assert resp.status_code == 200
        config_data = resp.json()
        assert config_data["config"]["agent_count"] == 2

        # Verify config was persisted
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        import json
        saved_config = json.loads(resp.json()["config"])
        assert saved_config["agent_count"] == 2
        assert saved_config["max_phases"] == 5

        # === Step 3: Launch swarm ===
        # mock_launch_deps fixture is active (patches _run_setup_only and _find_claude_cmd)

        mock_proc = MagicMock()
        mock_proc.pid = 9999
        mock_proc.poll.return_value = None  # Process alive
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.readline.return_value = b""
        mock_proc.terminate = MagicMock()
        mock_proc.wait = MagicMock(return_value=0)

        with patch("app.routes.swarm.subprocess.Popen", return_value=mock_proc):
            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid,
            })
        assert resp.status_code == 200, f"Launch failed: {resp.text}"
        launch_data = resp.json()
        assert launch_data["status"] == "launched"

        # === Step 4: Check swarm status ===
        resp = await client.get(f"/api/swarm/status/{pid}")
        assert resp.status_code == 200
        status_data = resp.json()
        assert status_data["status"] == "running"

        # === Step 5: List agents ===
        resp = await client.get(f"/api/swarm/agents/{pid}")
        assert resp.status_code == 200
        agents_data = resp.json()
        assert "agents" in agents_data

        # === Step 6: Get combined output ===
        resp = await client.get(f"/api/swarm/output/{pid}")
        assert resp.status_code == 200
        output_data = resp.json()
        assert "lines" in output_data
        assert "total" in output_data

        # === Step 7: Get per-agent output ===
        resp = await client.get(f"/api/swarm/output/{pid}?agent=Claude-1")
        assert resp.status_code == 200

        # === Step 8: Stop swarm ===
        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"

        # === Step 9: View history ===
        resp = await client.get(f"/api/swarm/history/{pid}")
        assert resp.status_code == 200
        history = resp.json()
        assert "runs" in history
        assert len(history["runs"]) >= 1
        assert history["runs"][0]["status"] in ("completed", "stopped", "running")

        # === Step 10: View project stats ===
        resp = await client.get(f"/api/projects/{pid}/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert "total_runs" in stats
        assert stats["total_runs"] >= 1

        # === Step 11: Archive project ===
        resp = await client.post(f"/api/projects/{pid}/archive")
        assert resp.status_code == 200

        # Verify project is archived (archived_at is set, status stays as swarm state)
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["archived_at"] is not None

        # === Step 12: Unarchive project ===
        resp = await client.post(f"/api/projects/{pid}/unarchive")
        assert resp.status_code == 200

        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["archived_at"] is None


class TestProjectDiscoveryJourney:
    """Tests the project listing and search journey."""

    async def test_list_search_filter(self, client, mock_project_folder):
        """Create multiple projects, then list/search/filter them."""
        folder = str(mock_project_folder).replace("\\", "/")

        # Create 3 projects with different names
        for name in ["Alpha Project", "Beta Feature", "Gamma Bug Fix"]:
            resp = await client.post("/api/projects", json={
                "name": name, "goal": f"Goal for {name}",
                "type": "feature", "stack": "python",
                "complexity": "simple", "folder_path": folder,
            })
            assert resp.status_code == 201

        # List all projects
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        projects = resp.json()
        assert len(projects) >= 3

        # Search by name
        resp = await client.get("/api/projects?search=Beta")
        assert resp.status_code == 200
        results = resp.json()
        assert any("Beta" in p["name"] for p in results)

    async def test_project_update_journey(self, client, mock_project_folder):
        """Create project, update it, verify changes."""
        folder = str(mock_project_folder).replace("\\", "/")

        resp = await client.post("/api/projects", json={
            "name": "Update Test", "goal": "Original goal",
            "type": "feature", "stack": "python",
            "complexity": "simple", "folder_path": folder,
        })
        assert resp.status_code == 201
        pid = resp.json()["id"]

        # Update the project
        resp = await client.patch(f"/api/projects/{pid}", json={
            "name": "Updated Name",
            "goal": "Updated goal",
        })
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["name"] == "Updated Name"
        assert updated["goal"] == "Updated goal"

        # Verify persistence
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"


class TestSwarmMonitoringJourney:
    """Tests the swarm monitoring workflow the frontend performs."""

    async def test_status_polling_pattern(self, client, created_project, mock_launch_deps):
        """Simulate the frontend's polling pattern for status updates."""
        pid = created_project["id"]

        # Initial status should be created/stopped
        resp = await client.get(f"/api/swarm/status/{pid}")
        assert resp.status_code == 200
        assert resp.json()["status"] in ("created", "stopped")

    async def test_output_pagination_pattern(self, client, created_project):
        """Test the frontend's output pagination pattern."""
        pid = created_project["id"]

        # First fetch with offset=0
        resp = await client.get(f"/api/swarm/output/{pid}?offset=0&limit=50")
        assert resp.status_code == 200
        data = resp.json()
        assert "lines" in data
        assert "total" in data
        assert "has_more" in data


class TestErrorRecoveryJourney:
    """Tests error scenarios a user might encounter."""

    async def test_launch_missing_project(self, client):
        """Launch swarm for nonexistent project returns 404."""
        resp = await client.post("/api/swarm/launch", json={"project_id": 99999})
        assert resp.status_code == 404

    async def test_stop_not_running(self, client, created_project):
        """Stop swarm that isn't running returns appropriate status."""
        pid = created_project["id"]
        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        # Should handle gracefully (200 or 400 depending on implementation)
        assert resp.status_code in (200, 400)

    async def test_config_invalid_values(self, client, created_project):
        """Invalid config values are rejected."""
        pid = created_project["id"]

        # Agent count too high
        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "agent_count": 100,
        })
        assert resp.status_code == 422

        # Max phases too high
        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "max_phases": 100,
        })
        assert resp.status_code == 422

    async def test_delete_archived_project(self, client, created_project):
        """Can delete an archived project."""
        pid = created_project["id"]

        # Archive first
        resp = await client.post(f"/api/projects/{pid}/archive")
        assert resp.status_code == 200

        # Delete (returns 204 No Content on success)
        resp = await client.delete(f"/api/projects/{pid}")
        assert resp.status_code in (200, 204)

        # Verify gone
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 404

    async def test_agents_for_nonexistent_project(self, client):
        """Get agents for nonexistent project returns 404."""
        resp = await client.get("/api/swarm/agents/99999")
        assert resp.status_code == 404

    async def test_history_for_nonexistent_project(self, client):
        """Get history for nonexistent project returns 404."""
        resp = await client.get("/api/swarm/history/99999")
        assert resp.status_code == 404


class TestTemplateWorkflow:
    """Tests the template management workflow."""

    async def test_create_use_delete_template(self, client):
        """Full template lifecycle: create, list, update, delete."""
        # Create
        resp = await client.post("/api/templates", json={
            "name": "Fast Build",
            "description": "Quick builds with 2 agents",
            "config": {"agent_count": 2, "max_phases": 3},
        })
        assert resp.status_code in (200, 201)
        tmpl = resp.json()
        tid = tmpl["id"]

        # List
        resp = await client.get("/api/templates")
        assert resp.status_code == 200
        templates = resp.json()
        assert any(t["id"] == tid for t in templates)

        # Update
        resp = await client.patch(f"/api/templates/{tid}", json={
            "name": "Fast Build v2",
            "description": "Updated description",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Fast Build v2"

        # Delete (returns 204 No Content on success)
        resp = await client.delete(f"/api/templates/{tid}")
        assert resp.status_code in (200, 204)

        # Verify gone
        resp = await client.get(f"/api/templates/{tid}")
        assert resp.status_code == 404


class TestHealthAndSystemJourney:
    """Tests system monitoring endpoints the dashboard uses."""

    async def test_health_check(self, client):
        """Health endpoint returns system status."""
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] == "ok"

    async def test_system_metrics(self, client):
        """System endpoint returns resource metrics."""
        resp = await client.get("/api/system")
        assert resp.status_code == 200
        data = resp.json()
        assert "cpu_percent" in data
        assert "memory_percent" in data
        assert "uptime_seconds" in data
