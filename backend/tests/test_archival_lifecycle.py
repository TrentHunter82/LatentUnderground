"""Tests for project archival lifecycle.

Verifies the complete archive/unarchive flow: archiving excludes projects from
default listing, unarchiving restores them, swarm history is preserved through
the cycle, and edge cases are handled correctly.
"""

import aiosqlite
import pytest


class TestArchiveUnarchiveCycle:
    """Verify the full archive and unarchive lifecycle."""

    @pytest.mark.asyncio
    async def test_archive_sets_archived_at(self, client, created_project):
        """POST /archive should set archived_at timestamp."""
        pid = created_project["id"]
        resp = await client.post(f"/api/projects/{pid}/archive")
        assert resp.status_code == 200
        data = resp.json()
        assert data["archived_at"] is not None

    @pytest.mark.asyncio
    async def test_archived_project_excluded_from_default_list(self, client, created_project):
        """Archived projects should not appear in GET /api/projects by default."""
        pid = created_project["id"]

        # Archive the project
        resp = await client.post(f"/api/projects/{pid}/archive")
        assert resp.status_code == 200

        # Default listing should exclude it
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        ids = [p["id"] for p in resp.json()]
        assert pid not in ids

    @pytest.mark.asyncio
    async def test_unarchive_restores_project_to_listing(self, client, created_project):
        """Unarchiving should restore the project to default listing."""
        pid = created_project["id"]

        # Archive
        await client.post(f"/api/projects/{pid}/archive")
        # Verify excluded
        resp = await client.get("/api/projects")
        assert pid not in [p["id"] for p in resp.json()]

        # Unarchive
        resp = await client.post(f"/api/projects/{pid}/unarchive")
        assert resp.status_code == 200
        assert resp.json()["archived_at"] is None

        # Verify restored to listing
        resp = await client.get("/api/projects")
        ids = [p["id"] for p in resp.json()]
        assert pid in ids

    @pytest.mark.asyncio
    async def test_archive_unarchive_full_cycle(self, client, created_project):
        """Full cycle: create -> archive -> verify excluded -> unarchive -> verify included."""
        pid = created_project["id"]

        # Step 1: Project exists in listing
        resp = await client.get("/api/projects")
        assert pid in [p["id"] for p in resp.json()]

        # Step 2: Archive
        resp = await client.post(f"/api/projects/{pid}/archive")
        assert resp.status_code == 200
        assert resp.json()["archived_at"] is not None

        # Step 3: Excluded from listing
        resp = await client.get("/api/projects")
        assert pid not in [p["id"] for p in resp.json()]

        # Step 4: Still accessible via direct GET
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["archived_at"] is not None

        # Step 5: Unarchive
        resp = await client.post(f"/api/projects/{pid}/unarchive")
        assert resp.status_code == 200
        assert resp.json()["archived_at"] is None

        # Step 6: Back in listing
        resp = await client.get("/api/projects")
        assert pid in [p["id"] for p in resp.json()]


class TestArchivalEdgeCases:
    """Edge cases for project archival."""

    @pytest.mark.asyncio
    async def test_archive_nonexistent_project(self, client):
        """Archiving a nonexistent project should return 404."""
        resp = await client.post("/api/projects/99999/archive")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_unarchive_nonexistent_project(self, client):
        """Unarchiving a nonexistent project should return 404."""
        resp = await client.post("/api/projects/99999/unarchive")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_double_archive_returns_400(self, client, created_project):
        """Archiving an already-archived project should return 400 (already archived)."""
        pid = created_project["id"]

        resp1 = await client.post(f"/api/projects/{pid}/archive")
        assert resp1.status_code == 200

        resp2 = await client.post(f"/api/projects/{pid}/archive")
        assert resp2.status_code == 400

    @pytest.mark.asyncio
    async def test_archived_project_still_readable(self, client, created_project):
        """An archived project should still be fetchable via GET /api/projects/{id}."""
        pid = created_project["id"]
        await client.post(f"/api/projects/{pid}/archive")

        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == created_project["name"]

    @pytest.mark.asyncio
    async def test_archived_project_updatable(self, client, created_project):
        """An archived project should still accept PATCH updates."""
        pid = created_project["id"]
        await client.post(f"/api/projects/{pid}/archive")

        resp = await client.patch(f"/api/projects/{pid}", json={"name": "Archived But Updated"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Archived But Updated"

    @pytest.mark.asyncio
    async def test_archived_project_deletable(self, client, created_project):
        """An archived project should still be deletable."""
        pid = created_project["id"]
        await client.post(f"/api/projects/{pid}/archive")

        resp = await client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 204

        # Confirm gone
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 404


class TestArchivalWithHistory:
    """Verify archival preserves project history and stats."""

    @pytest.mark.asyncio
    async def test_archived_project_history_accessible(self, client, created_project):
        """Swarm history should still be accessible for archived projects."""
        pid = created_project["id"]
        await client.post(f"/api/projects/{pid}/archive")

        resp = await client.get(f"/api/swarm/history/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        # History returns {project_id, runs: []}
        assert "runs" in data
        assert isinstance(data["runs"], list)

    @pytest.mark.asyncio
    async def test_archived_project_stats_accessible(self, client, created_project):
        """Project stats should still be accessible for archived projects."""
        pid = created_project["id"]
        await client.post(f"/api/projects/{pid}/archive")

        resp = await client.get(f"/api/projects/{pid}/stats")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_archived_project_status_accessible(self, client, created_project):
        """Swarm status should still be accessible for archived projects."""
        pid = created_project["id"]
        await client.post(f"/api/projects/{pid}/archive")

        resp = await client.get(f"/api/swarm/status/{pid}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_archived_project_preserves_swarm_runs(self, client, created_project, tmp_db):
        """Swarm runs created before archival should be preserved and queryable."""
        pid = created_project["id"]

        # Insert swarm runs directly into the test DB
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, tasks_completed, task_summary) "
                "VALUES (?, 'completed', 5, 'Built auth system')",
                (pid,),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, tasks_completed, task_summary) "
                "VALUES (?, 'completed', 3, 'Added tests')",
                (pid,),
            )
            await db.commit()

        # Archive the project
        resp = await client.post(f"/api/projects/{pid}/archive")
        assert resp.status_code == 200

        # History should still return both runs
        resp = await client.get(f"/api/swarm/history/{pid}")
        assert resp.status_code == 200
        runs = resp.json()["runs"]
        assert len(runs) == 2

        # Stats should reflect the completed runs
        resp = await client.get(f"/api/projects/{pid}/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["total_runs"] == 2
        assert stats["total_tasks_completed"] >= 8  # 5 + 3

    @pytest.mark.asyncio
    async def test_include_archived_query_param(self, client, created_project):
        """GET /api/projects?include_archived=true should include archived projects."""
        pid = created_project["id"]
        await client.post(f"/api/projects/{pid}/archive")

        # Default excludes
        resp = await client.get("/api/projects")
        assert pid not in [p["id"] for p in resp.json()]

        # With include_archived=true
        resp = await client.get("/api/projects?include_archived=true")
        assert resp.status_code == 200
        ids = [p["id"] for p in resp.json()]
        assert pid in ids
