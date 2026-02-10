"""Tests for concurrent operations and data isolation under load.

Verifies that the backend handles simultaneous requests correctly without
cross-contamination between projects, webhooks, or mixed resource types.
"""

import asyncio

import pytest


class TestConcurrentProjectOperations:
    """Verify project CRUD operations remain correct under concurrent access."""

    async def test_create_10_projects_concurrently(self, client, tmp_path):
        """10 concurrent POSTs should each succeed with unique IDs."""

        async def create_project(i):
            data = {
                "name": f"Concurrent Project {i}",
                "goal": f"Test concurrent creation {i}",
                "folder_path": str(tmp_path / f"proj{i}").replace("\\", "/"),
            }
            return await client.post("/api/projects", json=data)

        responses = await asyncio.gather(*[create_project(i) for i in range(10)])

        assert all(r.status_code == 201 for r in responses), (
            f"Expected all 201, got: {[r.status_code for r in responses]}"
        )
        ids = [r.json()["id"] for r in responses]
        assert len(set(ids)) == 10, f"Expected 10 unique IDs, got {len(set(ids))}"

    async def test_get_all_projects_after_bulk_create(self, client, tmp_path):
        """After creating 10 projects, listing should return exactly 10."""
        for i in range(10):
            resp = await client.post("/api/projects", json={
                "name": f"Bulk Project {i}",
                "goal": f"Bulk test {i}",
                "folder_path": str(tmp_path / f"bulk{i}").replace("\\", "/"),
            })
            assert resp.status_code == 201

        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        projects = resp.json()
        assert len(projects) == 10, f"Expected 10 projects, got {len(projects)}"

    async def test_concurrent_status_polling(self, client, tmp_path):
        """Concurrent status checks must each return the correct project data (no cross-contamination)."""
        project_ids = []
        for i in range(5):
            resp = await client.post("/api/projects", json={
                "name": f"Status Project {i}",
                "goal": f"Status poll test {i}",
                "folder_path": str(tmp_path / f"status{i}").replace("\\", "/"),
            })
            assert resp.status_code == 201
            project_ids.append(resp.json()["id"])

        async def get_status(pid):
            return pid, await client.get(f"/api/swarm/status/{pid}")

        results = await asyncio.gather(*[get_status(pid) for pid in project_ids])

        for pid, resp in results:
            assert resp.status_code == 200, f"Status for project {pid} returned {resp.status_code}"
            data = resp.json()
            # The status response includes project_id at top level; verify no cross-contamination
            assert data["project_id"] == pid, (
                f"Expected project_id {pid}, got {data['project_id']} (cross-contamination)"
            )
            assert "status" in data
            assert "agents" in data
            assert "signals" in data

    async def test_concurrent_project_updates(self, client, tmp_path):
        """5 concurrent PATCHes to different projects should each apply correctly."""
        project_ids = []
        for i in range(5):
            resp = await client.post("/api/projects", json={
                "name": f"Update Project {i}",
                "goal": f"Concurrent update test {i}",
                "folder_path": str(tmp_path / f"update{i}").replace("\\", "/"),
            })
            assert resp.status_code == 201
            project_ids.append(resp.json()["id"])

        async def update_project(pid, new_name):
            return pid, new_name, await client.patch(
                f"/api/projects/{pid}", json={"name": new_name}
            )

        updates = [(pid, f"Renamed-{pid}") for pid in project_ids]
        results = await asyncio.gather(*[
            update_project(pid, name) for pid, name in updates
        ])

        for pid, expected_name, resp in results:
            assert resp.status_code == 200, f"Update for {pid} returned {resp.status_code}"
            assert resp.json()["name"] == expected_name

        # Verify with fresh GETs that each project kept its own name
        for pid, expected_name in updates:
            resp = await client.get(f"/api/projects/{pid}")
            assert resp.status_code == 200
            assert resp.json()["name"] == expected_name, (
                f"Project {pid}: expected '{expected_name}', got '{resp.json()['name']}'"
            )


class TestConcurrentArchiveOperations:
    """Verify archive operations remain correct under concurrent access."""

    async def test_concurrent_archive_multiple(self, client, tmp_path):
        """5 concurrent archive requests should each succeed."""
        project_ids = []
        for i in range(5):
            resp = await client.post("/api/projects", json={
                "name": f"Archive Project {i}",
                "goal": f"Concurrent archive test {i}",
                "folder_path": str(tmp_path / f"archive{i}").replace("\\", "/"),
            })
            assert resp.status_code == 201
            project_ids.append(resp.json()["id"])

        async def archive_project(pid):
            return pid, await client.post(f"/api/projects/{pid}/archive")

        results = await asyncio.gather(*[archive_project(pid) for pid in project_ids])

        for pid, resp in results:
            assert resp.status_code == 200, f"Archive project {pid} returned {resp.status_code}"
            data = resp.json()
            assert data["archived_at"] is not None, f"Project {pid} archived_at is None"

        # Verify each project is truly archived via individual GETs
        for pid in project_ids:
            resp = await client.get(f"/api/projects/{pid}")
            assert resp.status_code == 200
            assert resp.json()["archived_at"] is not None

    async def test_archive_then_list_excludes(self, client, tmp_path):
        """After archiving 2 of 3 projects, default list should return only 1."""
        project_ids = []
        for i in range(3):
            resp = await client.post("/api/projects", json={
                "name": f"Filter Project {i}",
                "goal": f"Archive filter test {i}",
                "folder_path": str(tmp_path / f"filter{i}").replace("\\", "/"),
            })
            assert resp.status_code == 201
            project_ids.append(resp.json()["id"])

        # Archive the first two
        for pid in project_ids[:2]:
            resp = await client.post(f"/api/projects/{pid}/archive")
            assert resp.status_code == 200

        # Default listing excludes archived projects
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        listed = resp.json()
        assert len(listed) == 1, f"Expected 1 non-archived, got {len(listed)}"
        assert listed[0]["id"] == project_ids[2]


class TestConcurrentWebhookOperations:
    """Verify webhook CRUD operations remain correct under concurrent access."""

    async def test_create_multiple_webhooks(self, client):
        """5 concurrent webhook POSTs should each succeed with unique IDs."""

        async def create_webhook(i):
            data = {
                "url": f"https://example.com/hook/{i}",
                "events": ["swarm_launched", "swarm_stopped"],
            }
            return await client.post("/api/webhooks", json=data)

        responses = await asyncio.gather(*[create_webhook(i) for i in range(5)])

        assert all(r.status_code == 201 for r in responses), (
            f"Expected all 201, got: {[r.status_code for r in responses]}"
        )
        ids = [r.json()["id"] for r in responses]
        assert len(set(ids)) == 5, f"Expected 5 unique IDs, got {len(set(ids))}"

    async def test_concurrent_webhook_crud(self, client):
        """Concurrent get, update, and delete on different webhooks should all succeed."""
        # Create 3 webhooks sequentially first
        webhook_ids = []
        for i in range(3):
            resp = await client.post("/api/webhooks", json={
                "url": f"https://example.com/crud/{i}",
                "events": ["swarm_launched"],
            })
            assert resp.status_code == 201
            webhook_ids.append(resp.json()["id"])

        wh_get, wh_update, wh_delete = webhook_ids

        # Perform get, update, delete concurrently on different webhooks
        get_task = client.get(f"/api/webhooks/{wh_get}")
        update_task = client.patch(
            f"/api/webhooks/{wh_update}",
            json={"url": "https://example.com/updated"},
        )
        delete_task = client.delete(f"/api/webhooks/{wh_delete}")

        get_resp, update_resp, delete_resp = await asyncio.gather(
            get_task, update_task, delete_task,
        )

        assert get_resp.status_code == 200, f"GET returned {get_resp.status_code}"
        assert get_resp.json()["id"] == wh_get

        assert update_resp.status_code == 200, f"PATCH returned {update_resp.status_code}"
        assert update_resp.json()["url"] == "https://example.com/updated"

        assert delete_resp.status_code == 204, f"DELETE returned {delete_resp.status_code}"

        # Confirm deleted webhook is gone
        resp = await client.get(f"/api/webhooks/{wh_delete}")
        assert resp.status_code == 404


class TestConcurrentMixedOperations:
    """Verify mixed resource operations do not interfere with each other."""

    async def test_mixed_project_and_webhook_operations(self, client, tmp_path):
        """Concurrent project create, webhook create, project list, and webhook list should all succeed."""
        project_task = client.post("/api/projects", json={
            "name": "Mixed Op Project",
            "goal": "Mixed operation test",
            "folder_path": str(tmp_path / "mixed").replace("\\", "/"),
        })
        webhook_task = client.post("/api/webhooks", json={
            "url": "https://example.com/mixed",
            "events": ["swarm_launched"],
        })
        list_projects_task = client.get("/api/projects")
        list_webhooks_task = client.get("/api/webhooks")

        proj_resp, wh_resp, proj_list_resp, wh_list_resp = await asyncio.gather(
            project_task, webhook_task, list_projects_task, list_webhooks_task,
        )

        assert proj_resp.status_code == 201, f"Create project: {proj_resp.status_code}"
        assert wh_resp.status_code == 201, f"Create webhook: {wh_resp.status_code}"
        assert proj_list_resp.status_code == 200, f"List projects: {proj_list_resp.status_code}"
        assert wh_list_resp.status_code == 200, f"List webhooks: {wh_list_resp.status_code}"

        # Verify the created resources are retrievable
        proj_id = proj_resp.json()["id"]
        wh_id = wh_resp.json()["id"]
        assert (await client.get(f"/api/projects/{proj_id}")).status_code == 200
        assert (await client.get(f"/api/webhooks/{wh_id}")).status_code == 200

    async def test_rapid_create_delete_cycle(self, client, tmp_path):
        """Create and immediately delete 5 projects in sequence -- stress test for DB consistency."""
        for i in range(5):
            # Create
            create_resp = await client.post("/api/projects", json={
                "name": f"Ephemeral Project {i}",
                "goal": f"Rapid cycle test {i}",
                "folder_path": str(tmp_path / f"ephemeral{i}").replace("\\", "/"),
            })
            assert create_resp.status_code == 201, f"Create {i}: {create_resp.status_code}"
            pid = create_resp.json()["id"]

            # Immediately delete
            delete_resp = await client.delete(f"/api/projects/{pid}")
            assert delete_resp.status_code == 204, f"Delete {i}: {delete_resp.status_code}"

            # Confirm gone
            get_resp = await client.get(f"/api/projects/{pid}")
            assert get_resp.status_code == 404, f"Get after delete {i}: {get_resp.status_code}"

        # After all cycles, project list should be empty
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        assert resp.json() == [], f"Expected empty list, got {len(resp.json())} projects"


class TestConcurrentSwarmStatusPolling:
    """Verify concurrent swarm status polling at scale."""

    async def test_10_concurrent_status_polls(self, client, tmp_path):
        """10 concurrent status polls on the same project should all succeed without cross-contamination."""
        resp = await client.post("/api/projects", json={
            "name": "Status Poll Project",
            "goal": "Test 10 concurrent status polls",
            "folder_path": str(tmp_path / "status_poll").replace("\\", "/"),
        })
        assert resp.status_code == 201
        pid = resp.json()["id"]

        async def poll_status(i):
            return i, await client.get(f"/api/swarm/status/{pid}")

        results = await asyncio.gather(*[poll_status(i) for i in range(10)])

        for i, resp in results:
            assert resp.status_code == 200, f"Poll {i}: expected 200, got {resp.status_code}"
            data = resp.json()
            assert data["project_id"] == pid, f"Poll {i}: project_id mismatch"
            assert "status" in data
            assert "agents" in data
            assert "signals" in data

    async def test_10_concurrent_status_polls_different_projects(self, client, tmp_path):
        """10 concurrent status polls on 10 different projects should each return correct data."""
        project_ids = []
        for i in range(10):
            resp = await client.post("/api/projects", json={
                "name": f"Multi-Poll Project {i}",
                "goal": f"Concurrent poll test {i}",
                "folder_path": str(tmp_path / f"multi_poll{i}").replace("\\", "/"),
            })
            assert resp.status_code == 201
            project_ids.append(resp.json()["id"])

        async def poll_status(pid):
            return pid, await client.get(f"/api/swarm/status/{pid}")

        results = await asyncio.gather(*[poll_status(pid) for pid in project_ids])

        for pid, resp in results:
            assert resp.status_code == 200, f"Project {pid}: status returned {resp.status_code}"
            data = resp.json()
            assert data["project_id"] == pid, (
                f"Cross-contamination: expected project_id {pid}, got {data['project_id']}"
            )

    async def test_concurrent_health_checks(self, client):
        """10 concurrent health checks should all return consistently."""
        results = await asyncio.gather(*[client.get("/api/health") for _ in range(10)])

        for resp in results:
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["db"] == "ok"
            assert "uptime_seconds" in data
