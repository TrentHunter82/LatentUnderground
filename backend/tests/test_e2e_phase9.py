"""E2E Phase 9 tests: template lifecycle, browse integration, output pagination flow."""

import json
from unittest.mock import MagicMock, patch

import pytest


class TestTemplateLifecycle:
    """Create template -> apply to project -> launch with template config -> verify."""

    async def test_template_to_project_flow(self, client, mock_project_folder):
        """Full flow: create template, create project with template config, launch, verify."""
        # 1. Create template
        tmpl_resp = await client.post("/api/templates", json={
            "name": "Full Stack Template",
            "description": "Standard 6-agent full stack setup",
            "config": {
                "agent_count": 6,
                "max_phases": 12,
                "project_type": "Full Stack",
                "tech_stack": "React + FastAPI",
            },
        })
        assert tmpl_resp.status_code == 201
        template = tmpl_resp.json()
        assert template["name"] == "Full Stack Template"
        tid = template["id"]

        # 2. Verify template appears in list
        list_resp = await client.get("/api/templates")
        assert list_resp.status_code == 200
        assert any(t["id"] == tid for t in list_resp.json())

        # 3. Create project (frontend would use template config to populate form)
        folder = str(mock_project_folder).replace("\\", "/")
        (mock_project_folder / "swarm.ps1").write_text("# mock")
        proj_resp = await client.post("/api/projects", json={
            "name": "Template Project",
            "goal": "Test template application",
            "project_type": "Full Stack",
            "tech_stack": "React + FastAPI",
            "folder_path": folder,
        })
        assert proj_resp.status_code == 201
        pid = proj_resp.json()["id"]

        # 4. Apply template config to project
        config_resp = await client.patch(f"/api/projects/{pid}/config", json={
            "agent_count": template["config"]["agent_count"],
            "max_phases": template["config"]["max_phases"],
        })
        assert config_resp.status_code == 200
        assert config_resp.json()["config"]["agent_count"] == 6

        # 5. Launch with template-derived config
        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 55555
            mock_proc.stdout = MagicMock()
            mock_proc.stderr = MagicMock()
            mock_popen.return_value = mock_proc

            launch_resp = await client.post("/api/swarm/launch", json={
                "project_id": pid,
                "agent_count": 6,
                "max_phases": 12,
            })
            assert launch_resp.status_code == 200
            assert launch_resp.json()["pid"] == 55555

        # 6. Stop and verify history
        await client.post("/api/swarm/stop", json={"project_id": pid})
        history = (await client.get(f"/api/swarm/history/{pid}")).json()
        assert len(history["runs"]) == 1
        assert history["runs"][0]["status"] == "stopped"

        # 7. Update template
        await client.patch(f"/api/templates/{tid}", json={
            "name": "Full Stack v2",
            "config": {"agent_count": 8, "max_phases": 16},
        })
        updated = (await client.get(f"/api/templates/{tid}")).json()
        assert updated["name"] == "Full Stack v2"
        assert updated["config"]["agent_count"] == 8

        # 8. Delete template
        del_resp = await client.delete(f"/api/templates/{tid}")
        assert del_resp.status_code == 204

        # Verify template is gone
        gone_resp = await client.get(f"/api/templates/{tid}")
        assert gone_resp.status_code == 404

        # 9. Cleanup project
        del_proj = await client.delete(f"/api/projects/{pid}")
        assert del_proj.status_code == 204

    async def test_multiple_templates_isolation(self, client):
        """Creating and deleting templates does not affect others."""
        # Create two templates
        r1 = await client.post("/api/templates", json={
            "name": "Template A",
            "config": {"agent_count": 2},
        })
        r2 = await client.post("/api/templates", json={
            "name": "Template B",
            "config": {"agent_count": 4},
        })
        assert r1.status_code == 201
        assert r2.status_code == 201
        tid_a = r1.json()["id"]
        tid_b = r2.json()["id"]

        # Delete first template
        await client.delete(f"/api/templates/{tid_a}")

        # Second template still intact
        resp = await client.get(f"/api/templates/{tid_b}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Template B"
        assert resp.json()["config"]["agent_count"] == 4

        # List only has template B
        all_templates = (await client.get("/api/templates")).json()
        assert not any(t["id"] == tid_a for t in all_templates)
        assert any(t["id"] == tid_b for t in all_templates)

    async def test_template_update_preserves_unset_fields(self, client):
        """PATCH with partial fields preserves the others."""
        resp = await client.post("/api/templates", json={
            "name": "Partial Update",
            "description": "Keep this description",
            "config": {"agent_count": 4, "max_phases": 8},
        })
        tid = resp.json()["id"]

        # Update only the name
        await client.patch(f"/api/templates/{tid}", json={"name": "New Name"})
        updated = (await client.get(f"/api/templates/{tid}")).json()
        assert updated["name"] == "New Name"
        assert updated["description"] == "Keep this description"
        assert updated["config"]["agent_count"] == 4


class TestBrowseAndProjectCreation:
    """Browse filesystem -> select folder -> create project with that path."""

    async def test_browse_then_create_project(self, client, tmp_path):
        """Browse a real temp directory then create a project pointing to it."""
        # Create a project directory structure (no dot-prefix so browse returns it)
        project_dir = tmp_path / "my-new-project"
        project_dir.mkdir()

        # Browse the parent directory
        browse_path = str(tmp_path).replace("\\", "/")
        browse_resp = await client.get(f"/api/browse?path={browse_path}")
        assert browse_resp.status_code == 200
        data = browse_resp.json()
        assert "dirs" in data
        dirs = data["dirs"]
        found = [d for d in dirs if d["name"] == "my-new-project"]
        assert len(found) == 1

        # Create project with browsed path
        folder_path = found[0]["path"].replace("\\", "/")
        proj_resp = await client.post("/api/projects", json={
            "name": "Browsed Project",
            "goal": "Created from browse",
            "folder_path": folder_path,
        })
        assert proj_resp.status_code == 201
        assert proj_resp.json()["name"] == "Browsed Project"

        # Verify the created project has the correct folder
        pid = proj_resp.json()["id"]
        get_resp = await client.get(f"/api/projects/{pid}")
        assert get_resp.status_code == 200

    async def test_browse_empty_dir_returns_no_subdirs(self, client, tmp_path):
        """Browsing an empty directory returns an empty dirs list."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        browse_resp = await client.get(f"/api/browse?path={str(empty_dir)}")
        assert browse_resp.status_code == 200
        assert browse_resp.json()["dirs"] == []

    async def test_browse_nonexistent_path_returns_404(self, client, tmp_path):
        """Browsing a path that does not exist returns 404."""
        fake_path = str(tmp_path / "does_not_exist").replace("\\", "/")
        resp = await client.get(f"/api/browse?path={fake_path}")
        assert resp.status_code == 404

    async def test_browse_skips_hidden_dirs(self, client, tmp_path):
        """Browse filters out directories starting with '.' or '$'."""
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "$system").mkdir()
        (tmp_path / "visible").mkdir()

        resp = await client.get(f"/api/browse?path={str(tmp_path)}")
        assert resp.status_code == 200
        names = [d["name"] for d in resp.json()["dirs"]]
        assert "visible" in names
        assert ".hidden" not in names
        assert "$system" not in names


class TestOutputPaginationFlow:
    """Full output pagination flow: launch -> generate output -> paginate through it."""

    async def test_paginated_output_polling(self, client, mock_project_folder):
        """Simulate the frontend polling pattern with pagination."""
        from app.routes.swarm import _buffers_lock, _output_buffers

        folder = str(mock_project_folder).replace("\\", "/")
        (mock_project_folder / "swarm.ps1").write_text("# mock")

        # Create project
        resp = await client.post("/api/projects", json={
            "name": "Pagination Test",
            "goal": "Test output pagination",
            "folder_path": folder,
        })
        assert resp.status_code == 201
        pid = resp.json()["id"]

        # Simulate output buffer (as if swarm is running)
        with _buffers_lock:
            _output_buffers[pid] = [f"[stdout] line {i}" for i in range(100)]

        try:
            # First page
            page1 = (await client.get(f"/api/swarm/output/{pid}?offset=0&limit=20")).json()
            assert len(page1["lines"]) == 20
            assert page1["has_more"] is True
            assert page1["total"] == 100

            # Second page using next_offset
            page2 = (await client.get(
                f"/api/swarm/output/{pid}?offset={page1['next_offset']}&limit=20"
            )).json()
            assert len(page2["lines"]) == 20
            assert page2["lines"][0] == "[stdout] line 20"

            # Last page
            page5 = (await client.get(f"/api/swarm/output/{pid}?offset=80&limit=20")).json()
            assert len(page5["lines"]) == 20
            assert page5["has_more"] is False

            # Beyond buffer
            beyond = (await client.get(f"/api/swarm/output/{pid}?offset=100&limit=20")).json()
            assert len(beyond["lines"]) == 0
            assert beyond["has_more"] is False
        finally:
            # Cleanup
            with _buffers_lock:
                _output_buffers.pop(pid, None)

    async def test_incremental_polling_with_growing_buffer(self, client, mock_project_folder):
        """Simulate realistic frontend polling where new lines appear between polls."""
        from app.routes.swarm import _buffers_lock, _output_buffers

        folder = str(mock_project_folder).replace("\\", "/")
        (mock_project_folder / "swarm.ps1").write_text("# mock")

        resp = await client.post("/api/projects", json={
            "name": "Growing Buffer Test",
            "goal": "Test incremental polling",
            "folder_path": folder,
        })
        pid = resp.json()["id"]

        try:
            # Start with 5 lines
            with _buffers_lock:
                _output_buffers[pid] = [f"[stdout] batch1-{i}" for i in range(5)]

            poll1 = (await client.get(f"/api/swarm/output/{pid}?offset=0&limit=100")).json()
            assert len(poll1["lines"]) == 5
            assert poll1["next_offset"] == 5
            assert poll1["has_more"] is False

            # More output arrives
            with _buffers_lock:
                _output_buffers[pid].extend([f"[stdout] batch2-{i}" for i in range(3)])

            poll2 = (await client.get(
                f"/api/swarm/output/{pid}?offset={poll1['next_offset']}&limit=100"
            )).json()
            assert len(poll2["lines"]) == 3
            assert poll2["lines"][0] == "[stdout] batch2-0"
            assert poll2["next_offset"] == 8
        finally:
            with _buffers_lock:
                _output_buffers.pop(pid, None)

    async def test_pagination_response_structure(self, client, mock_project_folder):
        """Verify all expected fields are present in paginated output response."""
        folder = str(mock_project_folder).replace("\\", "/")
        (mock_project_folder / "swarm.ps1").write_text("# mock")

        resp = await client.post("/api/projects", json={
            "name": "Structure Test",
            "goal": "Check response fields",
            "folder_path": folder,
        })
        pid = resp.json()["id"]

        out_resp = await client.get(f"/api/swarm/output/{pid}?offset=0&limit=50")
        assert out_resp.status_code == 200
        body = out_resp.json()
        # Verify all pagination fields exist
        assert "project_id" in body
        assert "offset" in body
        assert "limit" in body
        assert "total" in body
        assert "next_offset" in body
        assert "has_more" in body
        assert "lines" in body
        assert isinstance(body["lines"], list)


class TestSearchAndFilterIntegration:
    """Test project search, filter, and sort work together."""

    async def test_search_filter_sort_combined(self, client, tmp_path):
        """Create multiple projects and test combined search+filter+sort."""
        folder = str(tmp_path).replace("\\", "/")

        # Create projects with different statuses
        pids = []
        for name, status in [
            ("Alpha API", "created"),
            ("Beta Backend", "running"),
            ("Gamma CLI", "completed"),
        ]:
            resp = await client.post("/api/projects", json={
                "name": name,
                "goal": f"Test {name}",
                "folder_path": folder,
            })
            assert resp.status_code == 201
            pid = resp.json()["id"]
            pids.append(pid)
            if status != "created":
                patch_resp = await client.patch(
                    f"/api/projects/{pid}", json={"status": status}
                )
                assert patch_resp.status_code == 200

        # Search by name
        resp = await client.get("/api/projects?search=Beta")
        assert resp.status_code == 200
        results = resp.json()
        assert any(p["name"] == "Beta Backend" for p in results)

        # Filter by status
        resp = await client.get("/api/projects?status=completed")
        assert resp.status_code == 200
        results = resp.json()
        assert all(p["status"] == "completed" for p in results)
        assert any(p["name"] == "Gamma CLI" for p in results)

        # Sort by name
        resp = await client.get("/api/projects?sort=name")
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert names == sorted(names)

    async def test_search_combined_with_status(self, client, tmp_path):
        """Search + status filter returns intersection of both filters."""
        folder = str(tmp_path).replace("\\", "/")

        await client.post("/api/projects", json={
            "name": "API Server", "goal": "Build API", "folder_path": folder,
        })
        r2 = await client.post("/api/projects", json={
            "name": "API Client", "goal": "Build client", "folder_path": folder,
        })
        pid2 = r2.json()["id"]
        await client.patch(f"/api/projects/{pid2}", json={"status": "completed"})

        # Search "API" + status "completed" should find only API Client
        resp = await client.get("/api/projects?search=API&status=completed")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["name"] == "API Client"

    async def test_search_no_results(self, client, tmp_path):
        """Search for nonexistent string returns empty list."""
        folder = str(tmp_path).replace("\\", "/")
        await client.post("/api/projects", json={
            "name": "Real Project", "goal": "Exists", "folder_path": folder,
        })

        resp = await client.get("/api/projects?search=zzzznonexistent")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_empty_search_returns_all(self, client, tmp_path):
        """Empty search string acts as no filter."""
        folder = str(tmp_path).replace("\\", "/")
        await client.post("/api/projects", json={
            "name": "Project One", "goal": "First", "folder_path": folder,
        })
        await client.post("/api/projects", json={
            "name": "Project Two", "goal": "Second", "folder_path": folder,
        })

        resp = await client.get("/api/projects?search=")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2


class TestAnalyticsIntegration:
    """Test analytics endpoint with real project data."""

    async def test_analytics_with_runs(self, client, mock_project_folder):
        """Create project, run multiple launch/stop cycles, check analytics."""
        folder = str(mock_project_folder).replace("\\", "/")
        (mock_project_folder / "swarm.ps1").write_text("# mock")

        resp = await client.post("/api/projects", json={
            "name": "Analytics Test",
            "goal": "Check analytics data",
            "folder_path": folder,
        })
        assert resp.status_code == 201
        pid = resp.json()["id"]

        # Run 2 launch/stop cycles
        for i in range(2):
            with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
                mock_proc = MagicMock()
                mock_proc.pid = 30000 + i
                mock_proc.stdout = MagicMock()
                mock_proc.stderr = MagicMock()
                mock_popen.return_value = mock_proc
                launch_resp = await client.post("/api/swarm/launch", json={
                    "project_id": pid,
                })
                assert launch_resp.status_code == 200
            stop_resp = await client.post("/api/swarm/stop", json={
                "project_id": pid,
            })
            assert stop_resp.status_code == 200

        # Check analytics
        analytics_resp = await client.get(f"/api/projects/{pid}/analytics")
        assert analytics_resp.status_code == 200
        data = analytics_resp.json()
        assert data["total_runs"] >= 2
        assert data["project_id"] == pid
        # run_trends should contain history entries
        assert "run_trends" in data
        assert len(data["run_trends"]) >= 2

    async def test_analytics_empty_project(self, client, tmp_path):
        """Analytics for a project with no runs returns zero counts."""
        folder = str(tmp_path).replace("\\", "/")
        resp = await client.post("/api/projects", json={
            "name": "Empty Analytics",
            "goal": "No runs yet",
            "folder_path": folder,
        })
        pid = resp.json()["id"]

        analytics_resp = await client.get(f"/api/projects/{pid}/analytics")
        assert analytics_resp.status_code == 200
        data = analytics_resp.json()
        assert data["total_runs"] == 0
        assert data["run_trends"] == []
        assert data["success_rate"] is None

    async def test_stats_endpoint_matches_analytics(self, client, mock_project_folder):
        """Stats and analytics endpoints both reflect the same run data."""
        folder = str(mock_project_folder).replace("\\", "/")
        (mock_project_folder / "swarm.ps1").write_text("# mock")

        resp = await client.post("/api/projects", json={
            "name": "Stats vs Analytics",
            "goal": "Compare endpoints",
            "folder_path": folder,
        })
        pid = resp.json()["id"]

        # Single launch/stop cycle
        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 40000
            mock_proc.stdout = MagicMock()
            mock_proc.stderr = MagicMock()
            mock_popen.return_value = mock_proc
            await client.post("/api/swarm/launch", json={"project_id": pid})
        await client.post("/api/swarm/stop", json={"project_id": pid})

        stats_resp = await client.get(f"/api/projects/{pid}/stats")
        analytics_resp = await client.get(f"/api/projects/{pid}/analytics")
        assert stats_resp.status_code == 200
        assert analytics_resp.status_code == 200

        stats = stats_resp.json()
        analytics = analytics_resp.json()
        assert stats["total_runs"] == analytics["total_runs"]
        assert stats["total_runs"] >= 1


class TestFullProjectLifecycle:
    """End-to-end: create -> configure -> launch -> monitor -> stop -> analytics -> delete."""

    async def test_complete_lifecycle(self, client, mock_project_folder):
        """Full lifecycle from project creation to deletion."""
        folder = str(mock_project_folder).replace("\\", "/")
        (mock_project_folder / "swarm.ps1").write_text("# mock")

        # 1. Create project
        create_resp = await client.post("/api/projects", json={
            "name": "Lifecycle Test",
            "goal": "Full E2E lifecycle",
            "project_type": "CLI Tool",
            "folder_path": folder,
        })
        assert create_resp.status_code == 201
        project = create_resp.json()
        pid = project["id"]
        assert project["status"] == "created"

        # 2. Configure the project
        config_resp = await client.patch(f"/api/projects/{pid}/config", json={
            "agent_count": 4,
            "max_phases": 6,
        })
        assert config_resp.status_code == 200
        assert config_resp.json()["config"]["agent_count"] == 4

        # 3. Launch swarm
        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 99999
            mock_proc.stdout = MagicMock()
            mock_proc.stderr = MagicMock()
            mock_popen.return_value = mock_proc

            launch_resp = await client.post("/api/swarm/launch", json={
                "project_id": pid,
                "agent_count": 4,
                "max_phases": 6,
            })
            assert launch_resp.status_code == 200
            assert launch_resp.json()["status"] == "launched"

        # 4. Check output (may be empty since process is mocked)
        output_resp = await client.get(f"/api/swarm/output/{pid}?offset=0&limit=50")
        assert output_resp.status_code == 200
        assert "lines" in output_resp.json()

        # 5. Stop swarm
        stop_resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert stop_resp.status_code == 200
        assert stop_resp.json()["status"] == "stopped"

        # 6. Check status after stop (should be stopped now)
        status_resp = await client.get(f"/api/swarm/status/{pid}")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["project_id"] == pid
        assert status_data["status"] == "stopped"
        assert "agents" in status_data
        assert "signals" in status_data
        assert "tasks" in status_data

        # 7. Check history
        history_resp = await client.get(f"/api/swarm/history/{pid}")
        assert history_resp.status_code == 200
        runs = history_resp.json()["runs"]
        assert len(runs) >= 1
        assert runs[0]["status"] == "stopped"

        # 8. Check stats
        stats_resp = await client.get(f"/api/projects/{pid}/stats")
        assert stats_resp.status_code == 200
        assert stats_resp.json()["total_runs"] >= 1

        # 9. Check analytics
        analytics_resp = await client.get(f"/api/projects/{pid}/analytics")
        assert analytics_resp.status_code == 200
        assert analytics_resp.json()["total_runs"] >= 1

        # 10. Delete project
        del_resp = await client.delete(f"/api/projects/{pid}")
        assert del_resp.status_code == 204

        # 11. Verify project is gone
        gone_resp = await client.get(f"/api/projects/{pid}")
        assert gone_resp.status_code == 404

    async def test_project_update_then_launch(self, client, mock_project_folder):
        """Update project metadata, then launch swarm and verify it runs."""
        folder = str(mock_project_folder).replace("\\", "/")
        (mock_project_folder / "swarm.ps1").write_text("# mock")

        # Create
        resp = await client.post("/api/projects", json={
            "name": "Update Then Launch",
            "goal": "Initial goal",
            "folder_path": folder,
        })
        pid = resp.json()["id"]

        # Update fields
        await client.patch(f"/api/projects/{pid}", json={
            "goal": "Updated goal with more detail",
            "tech_stack": "Python + Rust",
        })
        updated = (await client.get(f"/api/projects/{pid}")).json()
        assert updated["goal"] == "Updated goal with more detail"
        assert updated["tech_stack"] == "Python + Rust"

        # Launch
        with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 77777
            mock_proc.stdout = MagicMock()
            mock_proc.stderr = MagicMock()
            mock_popen.return_value = mock_proc

            launch_resp = await client.post("/api/swarm/launch", json={
                "project_id": pid,
            })
            assert launch_resp.status_code == 200

        # Stop
        await client.post("/api/swarm/stop", json={"project_id": pid})

        # History should have 1 run
        history = (await client.get(f"/api/swarm/history/{pid}")).json()
        assert len(history["runs"]) == 1


class TestHealthAndSystemIntegration:
    """Test health endpoint reflects system state during E2E operations."""

    async def test_health_during_idle(self, client):
        """Health endpoint returns ok when no swarms are running."""
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")
        assert "uptime" in data or "uptime_seconds" in data or "db" in data
