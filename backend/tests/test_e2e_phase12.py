"""E2E lifecycle tests for Phase 12.

Comprehensive integration tests covering complete user workflows end-to-end
through the API: project CRUD, config round-trips, archive/unarchive, swarm
status and history, template lifecycle, webhook lifecycle, file operations,
search/filter, and edge cases.
"""

import pytest


class TestProjectLifecycle:
    """Full project lifecycle: create -> configure -> archive -> unarchive -> delete."""

    @pytest.mark.asyncio
    async def test_create_get_update_verify_delete_verify404(self, client, tmp_path):
        """Create project -> get -> update name -> verify update -> delete -> verify 404."""
        folder = str(tmp_path / "LifecycleProj").replace("\\", "/")

        # 1. Create project
        resp = await client.post("/api/projects", json={
            "name": "Lifecycle Original",
            "goal": "Test full CRUD lifecycle",
            "project_type": "CLI Tool",
            "tech_stack": "Python",
            "complexity": "Simple",
            "folder_path": folder,
        })
        assert resp.status_code == 201
        project = resp.json()
        pid = project["id"]
        assert project["name"] == "Lifecycle Original"
        assert project["goal"] == "Test full CRUD lifecycle"
        assert project["status"] == "created"
        assert project["project_type"] == "CLI Tool"
        assert project["tech_stack"] == "Python"
        assert project["complexity"] == "Simple"
        assert "created_at" in project
        assert "updated_at" in project

        # 2. GET and verify
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == pid
        assert data["name"] == "Lifecycle Original"

        # 3. Update the name
        resp = await client.patch(f"/api/projects/{pid}", json={
            "name": "Lifecycle Renamed",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Lifecycle Renamed"

        # 4. Verify update persisted via GET
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Lifecycle Renamed"
        assert data["goal"] == "Test full CRUD lifecycle"
        assert data["project_type"] == "CLI Tool"
        assert data["tech_stack"] == "Python"
        assert data["complexity"] == "Simple"
        assert data["status"] == "created"

        # 5. Delete
        resp = await client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 204

        # 6. Verify 404 after deletion
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_save_config_verify_round_trip_delete(self, client, tmp_path):
        """Create project -> save config -> verify config round-trips -> delete."""
        import json as json_mod

        folder = str(tmp_path / "ConfigRTProj").replace("\\", "/")

        # Create project
        resp = await client.post("/api/projects", json={
            "name": "Config Round Trip",
            "goal": "Test config persistence",
            "folder_path": folder,
        })
        assert resp.status_code == 201
        pid = resp.json()["id"]

        # Save config
        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "agent_count": 6,
            "max_phases": 10,
            "custom_prompts": "Focus on API design",
        })
        assert resp.status_code == 200
        config_data = resp.json()
        assert config_data["config"]["agent_count"] == 6
        assert config_data["config"]["max_phases"] == 10
        assert config_data["config"]["custom_prompts"] == "Focus on API design"

        # Verify config persisted by reading the project
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        stored_config = json_mod.loads(resp.json()["config"])
        assert stored_config["agent_count"] == 6
        assert stored_config["max_phases"] == 10
        assert stored_config["custom_prompts"] == "Focus on API design"

        # Update config to different values
        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "agent_count": 2,
            "max_phases": 4,
        })
        assert resp.status_code == 200
        assert resp.json()["config"]["agent_count"] == 2
        assert resp.json()["config"]["max_phases"] == 4

        # Verify new config persisted
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        stored = json_mod.loads(resp.json()["config"])
        assert stored["agent_count"] == 2
        assert stored["max_phases"] == 4

        # Delete
        resp = await client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_archive_unarchive_lifecycle(self, client, tmp_path):
        """Create -> archive -> verify excluded from list -> verify still readable -> unarchive -> verify back in list -> delete."""
        folder = str(tmp_path / "ArchiveLifecycleProj").replace("\\", "/")

        # Create project
        resp = await client.post("/api/projects", json={
            "name": "Archive Lifecycle Project",
            "goal": "Test archive/unarchive flow",
            "folder_path": folder,
        })
        assert resp.status_code == 201
        pid = resp.json()["id"]

        # Verify in default list
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        assert any(p["id"] == pid for p in resp.json())

        # Archive
        resp = await client.post(f"/api/projects/{pid}/archive")
        assert resp.status_code == 200
        assert resp.json()["archived_at"] is not None

        # Excluded from default list
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        assert not any(p["id"] == pid for p in resp.json())

        # Still accessible via direct GET
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Archive Lifecycle Project"
        assert resp.json()["archived_at"] is not None

        # Included with include_archived=true
        resp = await client.get("/api/projects?include_archived=true")
        assert resp.status_code == 200
        assert any(p["id"] == pid for p in resp.json())

        # Unarchive
        resp = await client.post(f"/api/projects/{pid}/unarchive")
        assert resp.status_code == 200
        assert resp.json()["archived_at"] is None

        # Back in default list
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        assert any(p["id"] == pid for p in resp.json())

        # Delete
        resp = await client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 204


class TestSwarmStatusAndHistory:
    """Swarm status and history queries against newly created projects."""

    @pytest.mark.asyncio
    async def test_idle_status_and_empty_history(self, client, tmp_path):
        """Create project -> get status (should be idle/not running) -> verify empty history."""
        folder = str(tmp_path / "IdleStatusProj").replace("\\", "/")

        resp = await client.post("/api/projects", json={
            "name": "Idle Status Project",
            "goal": "Test idle swarm status",
            "folder_path": folder,
        })
        assert resp.status_code == 201
        pid = resp.json()["id"]

        # Status should show not running
        resp = await client.get(f"/api/swarm/status/{pid}")
        assert resp.status_code == 200
        status = resp.json()
        assert status["project_id"] == pid
        assert status["status"] == "created"
        assert status["swarm_pid"] is None
        assert status["process_alive"] is False
        assert "agents" in status
        assert "signals" in status
        assert "tasks" in status

        # History should be empty
        resp = await client.get(f"/api/swarm/history/{pid}")
        assert resp.status_code == 200
        history = resp.json()
        assert history["project_id"] == pid
        assert history["runs"] == []

    @pytest.mark.asyncio
    async def test_zero_stats_for_new_project(self, client, tmp_path):
        """Create project -> get stats (should be all zeros) -> verify response structure."""
        folder = str(tmp_path / "ZeroStatsProj").replace("\\", "/")

        resp = await client.post("/api/projects", json={
            "name": "Zero Stats Project",
            "goal": "Test zero-state stats",
            "folder_path": folder,
        })
        assert resp.status_code == 201
        pid = resp.json()["id"]

        # Stats should be all zeros
        resp = await client.get(f"/api/projects/{pid}/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["project_id"] == pid
        assert stats["total_runs"] == 0
        assert stats["avg_duration_seconds"] is None
        assert stats["total_tasks_completed"] == 0

        # Analytics should also be empty
        resp = await client.get(f"/api/projects/{pid}/analytics")
        assert resp.status_code == 200
        analytics = resp.json()
        assert analytics["project_id"] == pid
        assert analytics["total_runs"] == 0
        assert analytics["success_rate"] is None
        assert analytics["run_trends"] == []

    @pytest.mark.asyncio
    async def test_status_with_mock_folder_structure(self, client, project_with_folder):
        """Create project with mock folder -> get status -> verify agents/signals from folder structure."""
        pid = project_with_folder["id"]

        resp = await client.get(f"/api/swarm/status/{pid}")
        assert resp.status_code == 200
        status = resp.json()
        assert status["project_id"] == pid

        # Agents from heartbeat files
        agent_names = [a["name"] for a in status["agents"]]
        assert "Claude-1" in agent_names
        assert "Claude-2" in agent_names

        # Signals from .claude/signals directory
        assert "backend-ready" in status["signals"]
        assert status["signals"]["backend-ready"] is True

        # Task progress from tasks/TASKS.md (2 done, 4 total)
        tasks = status["tasks"]
        assert tasks["total"] == 4
        assert tasks["done"] == 2
        assert tasks["percent"] == 50.0

        # Phase info from swarm-phase.json
        assert status["phase"] is not None
        assert status["phase"]["Phase"] == 1
        assert status["phase"]["MaxPhases"] == 3


class TestTemplateLifecycle:
    """Template CRUD: create, list, update, get, delete."""

    @pytest.mark.asyncio
    async def test_full_template_crud(self, client):
        """Create template -> list -> update -> get by id -> delete -> verify 404."""
        # 1. Create template
        resp = await client.post("/api/templates", json={
            "name": "E2E Template",
            "description": "Full lifecycle test template",
            "config": {"agent_count": 4, "max_phases": 12},
        })
        assert resp.status_code == 201
        template = resp.json()
        tid = template["id"]
        assert template["name"] == "E2E Template"
        assert template["description"] == "Full lifecycle test template"
        assert template["config"]["agent_count"] == 4
        assert template["config"]["max_phases"] == 12
        assert "created_at" in template
        assert "updated_at" in template

        # 2. List templates: should contain the new one
        resp = await client.get("/api/templates")
        assert resp.status_code == 200
        templates = resp.json()
        assert isinstance(templates, list)
        assert any(t["id"] == tid for t in templates)

        # 3. Update name and config
        resp = await client.patch(f"/api/templates/{tid}", json={
            "name": "E2E Template v2",
            "config": {"agent_count": 8, "max_phases": 20},
        })
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["name"] == "E2E Template v2"
        assert updated["config"]["agent_count"] == 8
        assert updated["config"]["max_phases"] == 20
        # Description should be preserved (partial update)
        assert updated["description"] == "Full lifecycle test template"

        # 4. Get by ID to verify persistence
        resp = await client.get(f"/api/templates/{tid}")
        assert resp.status_code == 200
        fetched = resp.json()
        assert fetched["name"] == "E2E Template v2"
        assert fetched["description"] == "Full lifecycle test template"
        assert fetched["config"]["agent_count"] == 8

        # 5. Delete
        resp = await client.delete(f"/api/templates/{tid}")
        assert resp.status_code == 204

        # 6. Verify 404
        resp = await client.get(f"/api/templates/{tid}")
        assert resp.status_code == 404

        # 7. Verify not in list
        resp = await client.get("/api/templates")
        assert resp.status_code == 200
        assert not any(t["id"] == tid for t in resp.json())

    @pytest.mark.asyncio
    async def test_template_config_applied_to_project(self, client, tmp_path):
        """Create template -> create project using template config -> verify config applied."""
        # Create template
        resp = await client.post("/api/templates", json={
            "name": "Full Stack Template",
            "description": "Standard full stack setup",
            "config": {"agent_count": 6, "max_phases": 16, "project_type": "Full Stack"},
        })
        assert resp.status_code == 201
        template = resp.json()
        tid = template["id"]

        # Create project
        folder = str(tmp_path / "TemplatedProject").replace("\\", "/")
        resp = await client.post("/api/projects", json={
            "name": "Templated Project",
            "goal": "Test template config application",
            "project_type": "Full Stack",
            "folder_path": folder,
        })
        assert resp.status_code == 201
        pid = resp.json()["id"]

        # Apply template config to project
        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "agent_count": template["config"]["agent_count"],
            "max_phases": template["config"]["max_phases"],
        })
        assert resp.status_code == 200
        assert resp.json()["config"]["agent_count"] == 6
        assert resp.json()["config"]["max_phases"] == 16

        # Verify config persisted on project
        import json as json_mod
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        stored = json_mod.loads(resp.json()["config"])
        assert stored["agent_count"] == 6
        assert stored["max_phases"] == 16

        # Cleanup
        await client.delete(f"/api/templates/{tid}")
        await client.delete(f"/api/projects/{pid}")


class TestWebhookLifecycle:
    """Webhook CRUD: create, list, toggle, update, delete."""

    @pytest.mark.asyncio
    async def test_full_webhook_crud(self, client):
        """Create webhook -> list -> toggle enabled -> update url -> delete."""
        # 1. Create webhook
        resp = await client.post("/api/webhooks", json={
            "url": "https://hooks.example.com/test-e2e",
            "events": ["swarm_launched", "swarm_stopped"],
        })
        assert resp.status_code == 201
        webhook = resp.json()
        wid = webhook["id"]
        assert webhook["url"] == "https://hooks.example.com/test-e2e"
        assert set(webhook["events"]) == {"swarm_launched", "swarm_stopped"}
        assert webhook["has_secret"] is False
        assert "created_at" in webhook
        assert "updated_at" in webhook

        # 2. List webhooks
        resp = await client.get("/api/webhooks")
        assert resp.status_code == 200
        webhooks = resp.json()
        assert isinstance(webhooks, list)
        assert any(w["id"] == wid for w in webhooks)

        # 3. Toggle enabled to false
        resp = await client.patch(f"/api/webhooks/{wid}", json={
            "enabled": False,
        })
        assert resp.status_code == 200
        assert resp.json()["enabled"] == 0  # SQLite stores as int

        # 4. Toggle enabled back to true
        resp = await client.patch(f"/api/webhooks/{wid}", json={
            "enabled": True,
        })
        assert resp.status_code == 200
        assert resp.json()["enabled"] == 1

        # 5. Update URL
        resp = await client.patch(f"/api/webhooks/{wid}", json={
            "url": "https://hooks.example.com/updated-e2e",
        })
        assert resp.status_code == 200
        assert resp.json()["url"] == "https://hooks.example.com/updated-e2e"

        # 6. Verify via GET
        resp = await client.get(f"/api/webhooks/{wid}")
        assert resp.status_code == 200
        assert resp.json()["url"] == "https://hooks.example.com/updated-e2e"

        # 7. Delete
        resp = await client.delete(f"/api/webhooks/{wid}")
        assert resp.status_code == 204

        # 8. Verify gone
        resp = await client.get(f"/api/webhooks/{wid}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_webhook_with_secret_hides_secret(self, client):
        """Create webhook with secret -> verify has_secret=true in response (no secret exposed)."""
        resp = await client.post("/api/webhooks", json={
            "url": "https://hooks.example.com/secret-test",
            "events": ["swarm_launched"],
            "secret": "my-super-secret-key-123",
        })
        assert resp.status_code == 201
        webhook = resp.json()
        wid = webhook["id"]

        # has_secret should be true
        assert webhook["has_secret"] is True

        # The actual secret string should NOT be in the response
        assert "my-super-secret-key-123" not in str(webhook)

        # Verify via GET also hides secret
        resp = await client.get(f"/api/webhooks/{wid}")
        assert resp.status_code == 200
        fetched = resp.json()
        assert fetched["has_secret"] is True
        assert "my-super-secret-key-123" not in str(fetched)

        # Verify in list response too
        resp = await client.get("/api/webhooks")
        assert resp.status_code == 200
        for w in resp.json():
            if w["id"] == wid:
                assert w["has_secret"] is True
                assert "my-super-secret-key-123" not in str(w)
                break

        # Cleanup
        await client.delete(f"/api/webhooks/{wid}")


class TestFileOperations:
    """File read operations through the API."""

    @pytest.mark.asyncio
    async def test_read_tasks_md(self, client, project_with_folder):
        """Create project with mock folder -> read TASKS.md -> verify content."""
        pid = project_with_folder["id"]

        resp = await client.get(f"/api/files/tasks/TASKS.md?project_id={pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["path"] == "tasks/TASKS.md"
        assert "# Tasks" in data["content"]
        assert "- [x] Task 1" in data["content"]
        assert "- [x] Task 2" in data["content"]
        assert "- [ ] Task 3" in data["content"]
        assert "- [ ] Task 4" in data["content"]

    @pytest.mark.asyncio
    async def test_read_logs_from_project(self, client, project_with_folder):
        """Create project with mock folder -> read logs -> verify log lines exist."""
        pid = project_with_folder["id"]

        resp = await client.get(f"/api/logs?project_id={pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert "logs" in data
        assert isinstance(data["logs"], list)

        # Should have logs from Claude-1 and Claude-2
        agent_names = [log["agent"] for log in data["logs"]]
        assert "Claude-1" in agent_names
        assert "Claude-2" in agent_names

        # Verify Claude-1 log content
        claude1_log = next(log for log in data["logs"] if log["agent"] == "Claude-1")
        assert "Line 1" in claude1_log["lines"]
        assert "Line 2" in claude1_log["lines"]
        assert "Line 3" in claude1_log["lines"]

        # Verify Claude-2 log content
        claude2_log = next(log for log in data["logs"] if log["agent"] == "Claude-2")
        assert "Starting work" in claude2_log["lines"]


class TestSearchAndFilter:
    """Search, filter, and archive interactions across multiple projects."""

    @pytest.mark.asyncio
    async def test_search_projects_by_name(self, client, tmp_path):
        """Create 3 projects -> search by name -> verify filtered results."""
        folder = str(tmp_path / "SearchByNameProj").replace("\\", "/")

        # Create 3 projects with distinct names
        names = ["Alpha Service", "Beta Engine", "Gamma Toolkit"]
        pids = []
        for name in names:
            resp = await client.post("/api/projects", json={
                "name": name,
                "goal": f"Test project {name}",
                "folder_path": folder,
            })
            assert resp.status_code == 201
            pids.append(resp.json()["id"])

        # Search for "Beta" - should only find Beta Engine
        resp = await client.get("/api/projects?search=Beta")
        assert resp.status_code == 200
        results = resp.json()
        assert any(p["name"] == "Beta Engine" for p in results)
        assert not any(p["name"] == "Alpha Service" for p in results)
        assert not any(p["name"] == "Gamma Toolkit" for p in results)

        # Search for "a" - should find Alpha and Gamma (case-insensitive LIKE)
        resp = await client.get("/api/projects?search=alpha")
        assert resp.status_code == 200
        results = resp.json()
        assert any(p["name"] == "Alpha Service" for p in results)

        # Search for nonexistent term - empty results
        resp = await client.get("/api/projects?search=zzzznonexistent")
        assert resp.status_code == 200
        assert not any(p["id"] in pids for p in resp.json())

    @pytest.mark.asyncio
    async def test_archive_filtering_in_list(self, client, tmp_path):
        """Create 3 projects -> archive one -> list (should exclude archived) -> list with include_archived."""
        folder = str(tmp_path / "ArchiveFilterProj").replace("\\", "/")

        pids = []
        for name in ["Active One", "Active Two", "Will Archive"]:
            resp = await client.post("/api/projects", json={
                "name": name,
                "goal": f"Test {name}",
                "folder_path": folder,
            })
            assert resp.status_code == 201
            pids.append(resp.json()["id"])

        # Archive the third project
        resp = await client.post(f"/api/projects/{pids[2]}/archive")
        assert resp.status_code == 200

        # Default list should exclude archived
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        default_ids = [p["id"] for p in resp.json()]
        assert pids[0] in default_ids
        assert pids[1] in default_ids
        assert pids[2] not in default_ids

        # include_archived=true should include all
        resp = await client.get("/api/projects?include_archived=true")
        assert resp.status_code == 200
        all_ids = [p["id"] for p in resp.json()]
        assert pids[0] in all_ids
        assert pids[1] in all_ids
        assert pids[2] in all_ids


class TestEdgeCases:
    """Edge cases: double archive, unarchive non-archived, nonexistent project ops."""

    @pytest.mark.asyncio
    async def test_double_archive_returns_400(self, client, tmp_path):
        """Archiving an already-archived project returns 400."""
        folder = str(tmp_path / "DoubleArchiveProj").replace("\\", "/")

        resp = await client.post("/api/projects", json={
            "name": "Double Archive Test",
            "goal": "Test double archive error",
            "folder_path": folder,
        })
        assert resp.status_code == 201
        pid = resp.json()["id"]

        # First archive: succeeds
        resp = await client.post(f"/api/projects/{pid}/archive")
        assert resp.status_code == 200

        # Second archive: should fail with 400
        resp = await client.post(f"/api/projects/{pid}/archive")
        assert resp.status_code == 400
        assert "already archived" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_unarchive_non_archived_returns_400(self, client, tmp_path):
        """Unarchiving a project that is not archived returns 400."""
        folder = str(tmp_path / "UnarchiveNotArchived").replace("\\", "/")

        resp = await client.post("/api/projects", json={
            "name": "Not Archived Project",
            "goal": "Test unarchive non-archived error",
            "folder_path": folder,
        })
        assert resp.status_code == 201
        pid = resp.json()["id"]

        # Unarchive without archiving first: should fail
        resp = await client.post(f"/api/projects/{pid}/unarchive")
        assert resp.status_code == 400
        assert "not archived" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_nonexistent_project_returns_404(self, client):
        """Getting a project that does not exist returns 404."""
        resp = await client.get("/api/projects/99999")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body

    @pytest.mark.asyncio
    async def test_delete_nonexistent_project_returns_404(self, client):
        """Deleting a project that does not exist returns 404."""
        resp = await client.delete("/api/projects/99999")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body

    @pytest.mark.asyncio
    async def test_get_nonexistent_template_returns_404(self, client):
        """Getting a template that does not exist returns 404."""
        resp = await client.get("/api/templates/99999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_template_returns_404(self, client):
        """Deleting a template that does not exist returns 404."""
        resp = await client.delete("/api/templates/99999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_nonexistent_webhook_returns_404(self, client):
        """Getting a webhook that does not exist returns 404."""
        resp = await client.get("/api/webhooks/99999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_webhook_returns_404(self, client):
        """Deleting a webhook that does not exist returns 404."""
        resp = await client.delete("/api/webhooks/99999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_status_nonexistent_project_returns_404(self, client):
        """Getting swarm status for nonexistent project returns 404."""
        resp = await client.get("/api/swarm/status/99999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_history_nonexistent_project_returns_404(self, client):
        """Getting swarm history for nonexistent project returns 404."""
        resp = await client.get("/api/swarm/history/99999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_stats_nonexistent_project_returns_404(self, client):
        """Getting stats for nonexistent project returns 404."""
        resp = await client.get("/api/projects/99999/stats")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_analytics_nonexistent_project_returns_404(self, client):
        """Getting analytics for nonexistent project returns 404."""
        resp = await client.get("/api/projects/99999/analytics")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_archive_nonexistent_project_returns_404(self, client):
        """Archiving a nonexistent project returns 404."""
        resp = await client.post("/api/projects/99999/archive")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_unarchive_nonexistent_project_returns_404(self, client):
        """Unarchiving a nonexistent project returns 404."""
        resp = await client.post("/api/projects/99999/unarchive")
        assert resp.status_code == 404
