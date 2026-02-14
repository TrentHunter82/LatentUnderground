"""Endpoint coverage gap-fill tests for Phase 12.

Fills edge cases and under-tested paths across logs, webhooks, archives,
API versioning, browse, analytics, and swarm output endpoints.
"""

import pytest
import aiosqlite

from app.routes.swarm import _project_output_buffers, _buffers_lock


# ---------------------------------------------------------------------------
# Log Endpoint Gaps
# ---------------------------------------------------------------------------

class TestLogEndpointGaps:
    """Fill coverage gaps for GET /api/logs and GET /api/logs/search."""

    @pytest.mark.asyncio
    async def test_logs_returns_200_with_project_with_folder(self, client, project_with_folder):
        """GET /api/logs returns 200 and log entries for a project with log files."""
        resp = await client.get(f"/api/logs?project_id={project_with_folder['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert "logs" in data
        assert isinstance(data["logs"], list)
        assert len(data["logs"]) >= 1
        # Each entry should have agent and lines
        for entry in data["logs"]:
            assert "agent" in entry
            assert "lines" in entry
            assert isinstance(entry["lines"], list)

    @pytest.mark.asyncio
    async def test_logs_returns_empty_list_for_project_with_no_logs(self, client, tmp_path):
        """GET /api/logs returns 200 with empty logs for project whose folder has no log files."""
        folder = tmp_path / "no_log_files"
        folder.mkdir()
        # Create logs dir but leave it empty (no .log files)
        (folder / "logs").mkdir()

        resp = await client.post("/api/projects", json={
            "name": "Empty Logs Project",
            "goal": "Test empty log directory",
            "folder_path": str(folder).replace("\\", "/"),
        })
        assert resp.status_code == 201
        pid = resp.json()["id"]

        resp = await client.get(f"/api/logs?project_id={pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["logs"] == []

    @pytest.mark.asyncio
    async def test_log_search_empty_query_returns_all_lines(self, client, project_with_folder):
        """GET /api/logs/search with empty q returns all log lines (no text filter)."""
        pid = project_with_folder["id"]
        resp = await client.get(f"/api/logs/search?project_id={pid}&q=")
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert "total" in data
        # With empty query, all lines from all agents should be returned
        assert data["total"] >= 4  # Claude-1 has 3 lines + Claude-2 has 1 line


# ---------------------------------------------------------------------------
# Webhook Edge Cases
# ---------------------------------------------------------------------------

class TestWebhookEdgeCases:
    """Fill coverage gaps for webhook CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_delete_webhook_returns_204(self, client):
        """DELETE /api/webhooks/{id} returns 204 on successful deletion."""
        # Create a webhook first
        create_resp = await client.post("/api/webhooks", json={
            "url": "https://delete-me.example.com/hook",
            "events": ["swarm_launched"],
        })
        assert create_resp.status_code == 201
        wid = create_resp.json()["id"]

        # Delete it
        del_resp = await client.delete(f"/api/webhooks/{wid}")
        assert del_resp.status_code == 204

        # Confirm it's gone
        get_resp = await client.get(f"/api/webhooks/{wid}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_webhook_returns_404(self, client):
        """DELETE /api/webhooks/99999 returns 404 for non-existent webhook."""
        resp = await client.delete("/api/webhooks/99999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_patch_webhook_disable(self, client):
        """PATCH /api/webhooks/{id} with enabled=false disables the webhook."""
        # Create a webhook (enabled by default)
        create_resp = await client.post("/api/webhooks", json={
            "url": "https://disable-test.example.com/hook",
            "events": ["swarm_launched"],
        })
        assert create_resp.status_code == 201
        wid = create_resp.json()["id"]
        assert create_resp.json()["enabled"] == 1

        # Disable it via PATCH
        patch_resp = await client.patch(f"/api/webhooks/{wid}", json={
            "enabled": False,
        })
        assert patch_resp.status_code == 200
        assert patch_resp.json()["enabled"] == 0

        # Confirm via GET
        get_resp = await client.get(f"/api/webhooks/{wid}")
        assert get_resp.status_code == 200
        assert get_resp.json()["enabled"] == 0

    @pytest.mark.asyncio
    async def test_create_webhook_without_secret_has_secret_false(self, client):
        """Creating a webhook with no secret sets has_secret to false in the response."""
        resp = await client.post("/api/webhooks", json={
            "url": "https://no-secret.example.com/hook",
            "events": ["swarm_stopped"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["has_secret"] is False
        # The raw "secret" field should not be in the response
        assert "secret" not in data


# ---------------------------------------------------------------------------
# Archive Edge Cases
# ---------------------------------------------------------------------------

class TestArchiveEdgeCases:
    """Fill coverage gaps for project archival endpoints."""

    @pytest.mark.asyncio
    async def test_unarchive_non_archived_project_returns_400(self, client, created_project):
        """POST /api/projects/{id}/unarchive on a non-archived project returns 400."""
        pid = created_project["id"]
        resp = await client.post(f"/api/projects/{pid}/unarchive")
        assert resp.status_code == 400
        assert "not archived" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_double_archive_returns_400(self, client, created_project):
        """Archiving an already-archived project returns 400."""
        pid = created_project["id"]

        # First archive succeeds
        resp1 = await client.post(f"/api/projects/{pid}/archive")
        assert resp1.status_code == 200
        assert resp1.json()["archived_at"] is not None

        # Second archive fails
        resp2 = await client.post(f"/api/projects/{pid}/archive")
        assert resp2.status_code == 400
        assert "already archived" in resp2.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_archived_project_visible_with_include_archived(self, client, created_project):
        """Archived project still appears in GET /api/projects?include_archived=true."""
        pid = created_project["id"]

        # Archive the project
        archive_resp = await client.post(f"/api/projects/{pid}/archive")
        assert archive_resp.status_code == 200

        # Default listing excludes it
        default_resp = await client.get("/api/projects")
        assert default_resp.status_code == 200
        assert pid not in resp_ids(default_resp)

        # include_archived=true includes it
        inclusive_resp = await client.get("/api/projects?include_archived=true")
        assert inclusive_resp.status_code == 200
        ids = [p["id"] for p in inclusive_resp.json()]
        assert pid in ids

        # Verify the archived_at field is populated
        project = next(p for p in inclusive_resp.json() if p["id"] == pid)
        assert project["archived_at"] is not None


# ---------------------------------------------------------------------------
# API Versioning
# ---------------------------------------------------------------------------

class TestAPIVersioningGaps:
    """Fill coverage gaps for API v1 versioned endpoints."""

    @pytest.mark.asyncio
    async def test_v1_projects_returns_same_data(self, client, created_project):
        """GET /api/v1/projects returns same project list as /api/projects."""
        unversioned = await client.get("/api/projects")
        versioned = await client.get("/api/v1/projects")

        assert unversioned.status_code == 200
        assert versioned.status_code == 200
        assert unversioned.json() == versioned.json()

    @pytest.mark.asyncio
    async def test_v1_health_returns_same_core_fields(self, client):
        """GET /api/v1/health returns same core fields as /api/health."""
        unversioned = await client.get("/api/health")
        versioned = await client.get("/api/v1/health")

        assert unversioned.status_code == 200
        assert versioned.status_code == 200

        u = unversioned.json()
        v = versioned.json()
        assert u["app"] == v["app"]
        assert u["version"] == v["version"]
        assert u["status"] == v["status"]
        assert u["db"] == v["db"]

    @pytest.mark.asyncio
    async def test_unversioned_api_includes_deprecation_headers(self, client):
        """Unversioned /api/projects includes x-api-deprecation and sunset headers."""
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        assert resp.headers.get("x-api-deprecation") == "true"
        assert resp.headers.get("sunset") == "2026-12-31"

    @pytest.mark.asyncio
    async def test_v1_api_no_deprecation_headers(self, client):
        """Versioned /api/v1/projects does NOT include deprecation headers."""
        resp = await client.get("/api/v1/projects")
        assert resp.status_code == 200
        assert resp.headers.get("x-api-deprecation") is None
        assert resp.headers.get("sunset") is None

    @pytest.mark.asyncio
    async def test_v1_webhooks_creates_successfully(self, client):
        """POST /api/v1/webhooks should work the same as POST /api/webhooks."""
        resp = await client.post("/api/v1/webhooks", json={
            "url": "https://v1-test.example.com/hook",
            "events": ["swarm_launched"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["url"] == "https://v1-test.example.com/hook"
        assert "id" in data


# ---------------------------------------------------------------------------
# Browse Edge Cases
# ---------------------------------------------------------------------------

class TestBrowseEdgeCases:
    """Fill coverage gaps for GET /api/browse."""

    @pytest.mark.asyncio
    async def test_browse_truncated_flag_under_500(self, client, tmp_path):
        """When directory has fewer than 500 subdirs, truncated should be false."""
        for i in range(5):
            (tmp_path / f"dir_{i:03d}").mkdir()

        resp = await client.get("/api/browse", params={"path": str(tmp_path)})
        assert resp.status_code == 200
        data = resp.json()
        assert data["truncated"] is False
        assert len(data["dirs"]) == 5

    @pytest.mark.asyncio
    async def test_browse_nonexistent_path_returns_404(self, client, tmp_path):
        """GET /api/browse with non-existent path returns 404."""
        fake_path = str(tmp_path / "this_does_not_exist")
        resp = await client.get("/api/browse", params={"path": fake_path})
        assert resp.status_code == 404
        data = resp.json()
        assert "not found" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_browse_empty_path_returns_200(self, client):
        """GET /api/browse with empty path returns 200 (drive list or home dir)."""
        resp = await client.get("/api/browse", params={"path": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert "dirs" in data
        assert isinstance(data["dirs"], list)

    @pytest.mark.asyncio
    async def test_browse_response_includes_path_and_parent(self, client, tmp_path):
        """Browse response includes both path and parent fields."""
        child = tmp_path / "browse_child"
        child.mkdir()

        resp = await client.get("/api/browse", params={"path": str(child)})
        assert resp.status_code == 200
        data = resp.json()
        assert "path" in data
        assert "parent" in data
        assert "dirs" in data
        # Parent should point to tmp_path
        assert data["parent"] is not None


# ---------------------------------------------------------------------------
# Analytics Edge Cases
# ---------------------------------------------------------------------------

class TestAnalyticsEdgeCases:
    """Fill coverage gaps for GET /api/projects/{id}/analytics."""

    @pytest.mark.asyncio
    async def test_analytics_zero_runs_returns_zero_data(self, client, created_project):
        """Analytics for a project with zero runs returns zero/null defaults."""
        pid = created_project["id"]
        resp = await client.get(f"/api/projects/{pid}/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == pid
        assert data["total_runs"] == 0
        assert data["avg_duration"] is None
        assert data["total_tasks"] == 0
        assert data["success_rate"] is None
        assert data["run_trends"] == []

    @pytest.mark.asyncio
    async def test_analytics_nonexistent_project_returns_404(self, client):
        """Analytics for a nonexistent project returns 404."""
        resp = await client.get("/api/projects/99999/analytics")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_analytics_with_mixed_statuses(self, client, created_project, tmp_db):
        """Analytics correctly calculates success rate with mixed run statuses."""
        pid = created_project["id"]
        async with aiosqlite.connect(tmp_db) as db:
            # Two completed runs
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, tasks_completed, "
                "started_at, ended_at) VALUES (?, 'completed', 4, "
                "datetime('now', '-30 minutes'), datetime('now', '-20 minutes'))",
                (pid,),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, tasks_completed, "
                "started_at, ended_at) VALUES (?, 'completed', 6, "
                "datetime('now', '-15 minutes'), datetime('now', '-5 minutes'))",
                (pid,),
            )
            # One crashed run
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, tasks_completed, "
                "started_at, ended_at) VALUES (?, 'crashed', 1, "
                "datetime('now', '-60 minutes'), datetime('now', '-55 minutes'))",
                (pid,),
            )
            await db.commit()

        resp = await client.get(f"/api/projects/{pid}/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_runs"] == 3
        assert data["total_tasks"] == 11  # 4 + 6 + 1
        # 2 completed out of 3 finished = 66.7%
        assert data["success_rate"] is not None
        assert 66.0 <= data["success_rate"] <= 67.0
        assert data["avg_duration"] is not None
        assert len(data["run_trends"]) == 3


# ---------------------------------------------------------------------------
# Swarm Output Edge Cases
# ---------------------------------------------------------------------------

class TestSwarmOutputEdgeCases:
    """Fill coverage gaps for GET /api/swarm/output/{id}."""

    @pytest.mark.asyncio
    async def test_output_no_buffer_returns_empty(self, client, created_project):
        """GET /api/swarm/output/{id} with no buffer returns empty output."""
        pid = created_project["id"]
        # Ensure buffer is clear
        with _buffers_lock:
            _project_output_buffers.pop(pid, None)

        resp = await client.get(f"/api/swarm/output/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["lines"] == []
        assert data["total"] == 0
        assert data["has_more"] is False
        assert data["project_id"] == pid

    @pytest.mark.asyncio
    async def test_output_pagination_offset_limit(self, client, created_project):
        """GET /api/swarm/output/{id}?offset=0&limit=10 respects pagination."""
        pid = created_project["id"]
        with _buffers_lock:
            _project_output_buffers[pid] = [f"[stdout] line {i}" for i in range(25)]

        resp = await client.get(f"/api/swarm/output/{pid}?offset=0&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["lines"]) == 10
        assert data["offset"] == 0
        assert data["limit"] == 10
        assert data["total"] == 25
        assert data["next_offset"] == 10
        assert data["has_more"] is True

        # Fetch second page
        resp2 = await client.get(f"/api/swarm/output/{pid}?offset=10&limit=10")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert len(data2["lines"]) == 10
        assert data2["lines"][0] == "[stdout] line 10"
        assert data2["next_offset"] == 20
        assert data2["has_more"] is True

        # Fetch third (partial) page
        resp3 = await client.get(f"/api/swarm/output/{pid}?offset=20&limit=10")
        assert resp3.status_code == 200
        data3 = resp3.json()
        assert len(data3["lines"]) == 5
        assert data3["has_more"] is False

    @pytest.mark.asyncio
    async def test_output_nonexistent_project_returns_404(self, client):
        """GET /api/swarm/output/99999 returns 404 for non-existent project."""
        resp = await client.get("/api/swarm/output/99999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Stats Edge Cases
# ---------------------------------------------------------------------------

class TestStatsEdgeCases:
    """Fill coverage gaps for GET /api/projects/{id}/stats."""

    @pytest.mark.asyncio
    async def test_stats_zero_runs(self, client, created_project):
        """Stats for a project with zero runs returns proper zero defaults."""
        pid = created_project["id"]
        resp = await client.get(f"/api/projects/{pid}/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == pid
        assert data["total_runs"] == 0
        assert data["avg_duration_seconds"] is None
        assert data["total_tasks_completed"] == 0

    @pytest.mark.asyncio
    async def test_stats_nonexistent_project_returns_404(self, client):
        """Stats for a nonexistent project returns 404."""
        resp = await client.get("/api/projects/99999/stats")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Webhook List & GET Gaps
# ---------------------------------------------------------------------------

class TestWebhookListGaps:
    """Fill coverage gaps for webhook listing and retrieval."""

    @pytest.mark.asyncio
    async def test_list_webhooks_empty(self, client):
        """GET /api/webhooks returns empty list when none exist."""
        resp = await client.get("/api/webhooks")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_webhooks_multiple(self, client):
        """GET /api/webhooks returns all created webhooks in order."""
        await client.post("/api/webhooks", json={
            "url": "https://first.example.com/hook",
            "events": ["swarm_launched"],
        })
        await client.post("/api/webhooks", json={
            "url": "https://second.example.com/hook",
            "events": ["swarm_stopped"],
        })

        resp = await client.get("/api/webhooks")
        assert resp.status_code == 200
        webhooks = resp.json()
        assert len(webhooks) == 2
        urls = {wh["url"] for wh in webhooks}
        assert "https://first.example.com/hook" in urls
        assert "https://second.example.com/hook" in urls

    @pytest.mark.asyncio
    async def test_get_nonexistent_webhook_returns_404(self, client):
        """GET /api/webhooks/99999 returns 404."""
        resp = await client.get("/api/webhooks/99999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_webhook_with_secret_has_secret_true(self, client):
        """Creating a webhook WITH a secret sets has_secret to true."""
        resp = await client.post("/api/webhooks", json={
            "url": "https://with-secret.example.com/hook",
            "events": ["swarm_launched"],
            "secret": "my-super-secret",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["has_secret"] is True
        assert "secret" not in data

    @pytest.mark.asyncio
    async def test_patch_nonexistent_webhook_returns_404(self, client):
        """PATCH /api/webhooks/99999 returns 404."""
        resp = await client.patch("/api/webhooks/99999", json={"enabled": False})
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Swarm History Edge Cases
# ---------------------------------------------------------------------------

class TestSwarmHistoryGaps:
    """Fill coverage gaps for GET /api/swarm/history/{id}."""

    @pytest.mark.asyncio
    async def test_history_empty_returns_empty_list(self, client, created_project):
        """History for a project with no runs returns empty list."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/history/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == pid
        assert data["runs"] == []

    @pytest.mark.asyncio
    async def test_history_nonexistent_project_returns_404(self, client):
        """History for nonexistent project returns 404."""
        resp = await client.get("/api/swarm/history/99999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_history_calculates_duration(self, client, created_project, tmp_db):
        """History entries with both start and end times include duration_seconds."""
        pid = created_project["id"]
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, tasks_completed, "
                "started_at, ended_at) VALUES (?, 'completed', 3, "
                "datetime('now', '-10 minutes'), datetime('now'))",
                (pid,),
            )
            await db.commit()

        resp = await client.get(f"/api/swarm/history/{pid}")
        assert resp.status_code == 200
        runs = resp.json()["runs"]
        assert len(runs) == 1
        assert runs[0]["duration_seconds"] is not None
        assert runs[0]["duration_seconds"] > 0


# ---------------------------------------------------------------------------
# Log Search Date Range Gaps
# ---------------------------------------------------------------------------

class TestLogSearchDateRangeGaps:
    """Fill coverage gaps for log search date range filtering."""

    @pytest.mark.asyncio
    async def test_log_search_invalid_from_date_returns_400(self, client, project_with_folder):
        """GET /api/logs/search with invalid from_date returns 400."""
        pid = project_with_folder["id"]
        resp = await client.get(
            f"/api/logs/search?project_id={pid}&q=test&from_date=not-a-date"
        )
        assert resp.status_code == 400
        assert "from_date" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_log_search_invalid_to_date_returns_400(self, client, project_with_folder):
        """GET /api/logs/search with invalid to_date returns 400."""
        pid = project_with_folder["id"]
        resp = await client.get(
            f"/api/logs/search?project_id={pid}&q=test&to_date=bad-date"
        )
        assert resp.status_code == 400
        assert "to_date" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_log_search_valid_date_range(self, client, project_with_folder):
        """GET /api/logs/search with valid date range returns 200."""
        pid = project_with_folder["id"]
        resp = await client.get(
            f"/api/logs/search?project_id={pid}&from_date=2020-01-01&to_date=2030-12-31"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert "total" in data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resp_ids(resp):
    """Extract project IDs from a list response."""
    if resp.status_code != 200:
        return []
    return [p["id"] for p in resp.json()]
