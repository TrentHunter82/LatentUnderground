"""Performance regression tests for Latent Underground API.

Measures response times for critical endpoints and operations to catch
performance regressions early. Thresholds are generous to accommodate
test environments (ASGI transport overhead, concurrent tests, shared event loop).
Production targets are tighter (< 200ms) but test guards use 500ms+ to avoid flakiness.
"""

import asyncio
import time

import pytest


class TestPerformanceBenchmarks:
    """Benchmark tests for API endpoint response times."""

    async def test_health_endpoint_speed(self, client):
        """GET /api/health should respond in < 500ms (test env guard)."""
        start = time.monotonic()
        resp = await client.get("/api/health")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert elapsed < 0.5, f"Health endpoint took {elapsed:.3f}s (max 0.5s)"

    async def test_project_create_speed(self, client, tmp_path):
        """POST /api/projects should respond in < 500ms (test env guard)."""
        payload = {
            "name": "Speed Test Project",
            "goal": "Benchmark project creation speed",
            "folder_path": str(tmp_path / "speed_create").replace("\\", "/"),
        }

        start = time.monotonic()
        resp = await client.post("/api/projects", json=payload)
        elapsed = time.monotonic() - start

        assert resp.status_code == 201
        assert elapsed < 0.5, f"Project create took {elapsed:.3f}s (max 0.5s)"

    async def test_project_list_speed(self, client, tmp_path):
        """Create 20 projects, then GET /api/projects should respond in < 500ms."""
        # Seed 20 projects
        for i in range(20):
            resp = await client.post("/api/projects", json={
                "name": f"Perf Test {i}",
                "goal": f"Performance testing project {i}",
                "folder_path": str(tmp_path / f"perf_{i}").replace("\\", "/"),
            })
            assert resp.status_code == 201

        # Measure list speed
        start = time.monotonic()
        resp = await client.get("/api/projects")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 20, f"Expected 20 projects, got {len(data)}"
        assert elapsed < 0.5, f"Project list (20 items) took {elapsed:.3f}s (max 0.5s)"

    async def test_project_get_speed(self, client, created_project):
        """GET /api/projects/{id} should respond in < 500ms (test env guard)."""
        pid = created_project["id"]

        start = time.monotonic()
        resp = await client.get(f"/api/projects/{pid}")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert resp.json()["id"] == pid
        assert elapsed < 0.5, f"Project get took {elapsed:.3f}s (max 0.5s)"

    async def test_template_crud_speed(self, client):
        """Full template CRUD cycle (create, get, list, update, delete) in < 2s."""
        start = time.monotonic()

        # Create
        create_resp = await client.post("/api/templates", json={
            "name": "Benchmark Template",
            "description": "Template for performance testing",
            "config": {"agent_count": 4, "max_phases": 3},
        })
        assert create_resp.status_code == 201
        tid = create_resp.json()["id"]

        # Get
        get_resp = await client.get(f"/api/templates/{tid}")
        assert get_resp.status_code == 200

        # List
        list_resp = await client.get("/api/templates")
        assert list_resp.status_code == 200

        # Update
        update_resp = await client.patch(f"/api/templates/{tid}", json={
            "name": "Updated Benchmark Template",
            "config": {"agent_count": 8, "max_phases": 5},
        })
        assert update_resp.status_code == 200

        # Delete
        delete_resp = await client.delete(f"/api/templates/{tid}")
        assert delete_resp.status_code == 204

        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"Template CRUD cycle took {elapsed:.3f}s (max 2.0s)"

    async def test_concurrent_reads_scale(self, client, tmp_path):
        """10 concurrent GET /api/projects should complete in < 2s total."""
        # Seed a few projects so the list is non-trivial
        for i in range(5):
            resp = await client.post("/api/projects", json={
                "name": f"Concurrent Read {i}",
                "goal": f"Concurrent read test {i}",
                "folder_path": str(tmp_path / f"concurrent_{i}").replace("\\", "/"),
            })
            assert resp.status_code == 201

        start = time.monotonic()
        results = await asyncio.gather(*[client.get("/api/projects") for _ in range(10)])
        elapsed = time.monotonic() - start

        for resp in results:
            assert resp.status_code == 200
            assert len(resp.json()) == 5

        assert elapsed < 2.0, f"10 concurrent reads took {elapsed:.3f}s (max 2.0s)"

    async def test_webhook_crud_speed(self, client):
        """Create + list + delete webhook in < 1s total."""
        start = time.monotonic()

        # Create
        create_resp = await client.post("/api/webhooks", json={
            "url": "https://example.com/webhook",
            "events": ["swarm_launched"],
        })
        assert create_resp.status_code == 201
        wid = create_resp.json()["id"]

        # List
        list_resp = await client.get("/api/webhooks")
        assert list_resp.status_code == 200
        assert any(w["id"] == wid for w in list_resp.json())

        # Delete
        delete_resp = await client.delete(f"/api/webhooks/{wid}")
        assert delete_resp.status_code == 204

        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"Webhook CRUD took {elapsed:.3f}s (max 1.0s)"

    async def test_search_with_many_projects(self, client, tmp_path):
        """Create 50 projects, search by name should respond in < 500ms."""
        # Seed 50 projects with varied names
        for i in range(50):
            resp = await client.post("/api/projects", json={
                "name": f"SearchBench Project {i:03d}",
                "goal": f"Search benchmark project {i}",
                "folder_path": str(tmp_path / f"search_{i}").replace("\\", "/"),
            })
            assert resp.status_code == 201

        # Search for a specific substring
        start = time.monotonic()
        resp = await client.get("/api/projects?search=SearchBench")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 50, f"Expected 50 search results, got {len(data)}"
        assert elapsed < 0.5, f"Search with 50 projects took {elapsed:.3f}s (max 0.5s)"
