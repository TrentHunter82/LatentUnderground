"""Phase 19 Performance Benchmarks - API Response Time Baselines.

Measures and documents baseline performance metrics for all critical API
endpoints. Complements test_performance_benchmarks.py (which covers basic CRUD).
Focuses on: dashboard endpoint, swarm status, metrics, system info, analytics,
search with filters, and pagination performance.

Thresholds are generous (500ms-2s) to accommodate test environments.
Production targets should be < 200ms for reads, < 500ms for writes.
"""

import asyncio
import time
from collections import deque

import aiosqlite
import pytest


class TestDashboardPerformance:
    """Benchmark the combined dashboard endpoint."""

    async def test_dashboard_endpoint_speed(self, client, created_project):
        """GET /api/projects/{id}/dashboard should respond in < 1s."""
        pid = created_project["id"]

        start = time.monotonic()
        resp = await client.get(f"/api/projects/{pid}/dashboard")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        data = resp.json()
        assert "project_id" in data
        assert elapsed < 1.0, f"Dashboard took {elapsed:.3f}s (max 1.0s)"

    async def test_dashboard_with_run_history(self, client, created_project, app):
        """Dashboard with swarm run history should still be fast."""
        pid = created_project["id"]

        # Create some swarm run history via direct DB access
        from app import database
        async with aiosqlite.connect(database.DB_PATH) as db:
            for i in range(10):
                await db.execute(
                    """INSERT INTO swarm_runs (project_id, started_at, ended_at, status, phase, tasks_completed)
                       VALUES (?, datetime('now', ?), datetime('now', ?), 'completed', ?, ?)""",
                    (pid, f'-{10-i} minutes', f'-{9-i} minutes', i + 1, i * 3),
                )
            await db.commit()

        start = time.monotonic()
        resp = await client.get(f"/api/projects/{pid}/dashboard")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert elapsed < 1.0, f"Dashboard with history took {elapsed:.3f}s (max 1.0s)"


class TestSwarmEndpointPerformance:
    """Benchmark swarm-related endpoints."""

    async def test_swarm_status_speed(self, client, created_project):
        """GET /api/swarm/status/{id} should respond quickly even with no active swarm."""
        pid = created_project["id"]

        start = time.monotonic()
        resp = await client.get(f"/api/swarm/status/{pid}")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert elapsed < 0.5, f"Swarm status took {elapsed:.3f}s (max 0.5s)"

    async def test_swarm_history_speed(self, client, created_project, app):
        """GET /api/swarm/history/{id} with 20 runs should respond in < 500ms."""
        pid = created_project["id"]

        from app import database
        async with aiosqlite.connect(database.DB_PATH) as db:
            for i in range(20):
                await db.execute(
                    """INSERT INTO swarm_runs (project_id, started_at, ended_at, status)
                       VALUES (?, datetime('now', ?), datetime('now', ?), 'completed')""",
                    (pid, f'-{20-i} hours', f'-{19-i} hours'),
                )
            await db.commit()

        start = time.monotonic()
        resp = await client.get(f"/api/swarm/history/{pid}")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert len(resp.json()["runs"]) == 20
        assert elapsed < 0.5, f"Swarm history (20 runs) took {elapsed:.3f}s (max 0.5s)"

    async def test_swarm_output_with_large_buffer(self, client, created_project):
        """GET /api/swarm/output with 1000-line buffer should respond in < 500ms."""
        pid = created_project["id"]

        from app.routes.swarm import _project_output_buffers
        _project_output_buffers[pid] = deque(
            [f"[Claude-1] Line {i}: Some output text here" for i in range(1000)],
            maxlen=5000,
        )

        try:
            start = time.monotonic()
            resp = await client.get(f"/api/swarm/output/{pid}?limit=100")
            elapsed = time.monotonic() - start

            assert resp.status_code == 200
            assert len(resp.json()["lines"]) == 100
            assert elapsed < 0.5, f"Output fetch (1000 buffer, 100 limit) took {elapsed:.3f}s"
        finally:
            _project_output_buffers.pop(pid, None)

    async def test_swarm_output_pagination_speed(self, client, created_project):
        """Paginated output fetch (offset + limit) should be efficient."""
        pid = created_project["id"]

        from app.routes.swarm import _project_output_buffers
        _project_output_buffers[pid] = deque(
            [f"[Claude-1] Line {i}" for i in range(5000)],
            maxlen=5000,
        )

        try:
            # Fetch from middle of buffer
            start = time.monotonic()
            resp = await client.get(f"/api/swarm/output/{pid}?offset=2500&limit=100")
            elapsed = time.monotonic() - start

            assert resp.status_code == 200
            assert elapsed < 0.5, f"Paginated output took {elapsed:.3f}s (max 0.5s)"
        finally:
            _project_output_buffers.pop(pid, None)


class TestAnalyticsPerformance:
    """Benchmark analytics and stats endpoints."""

    async def test_project_stats_speed(self, client, created_project, app):
        """GET /api/projects/{id}/stats should respond in < 500ms."""
        pid = created_project["id"]

        # Add some run data
        from app import database
        async with aiosqlite.connect(database.DB_PATH) as db:
            for i in range(5):
                await db.execute(
                    """INSERT INTO swarm_runs (project_id, started_at, ended_at, status, tasks_completed)
                       VALUES (?, datetime('now', ?), datetime('now', ?), 'completed', ?)""",
                    (pid, f'-{5-i} hours', f'-{4-i} hours', i * 5),
                )
            await db.commit()

        start = time.monotonic()
        resp = await client.get(f"/api/projects/{pid}/stats")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert elapsed < 0.5, f"Project stats took {elapsed:.3f}s (max 0.5s)"

    async def test_project_analytics_speed(self, client, created_project, app):
        """GET /api/projects/{id}/analytics with history should respond in < 1s."""
        pid = created_project["id"]

        from app import database
        async with aiosqlite.connect(database.DB_PATH) as db:
            for i in range(15):
                await db.execute(
                    """INSERT INTO swarm_runs (project_id, started_at, ended_at, status, tasks_completed)
                       VALUES (?, datetime('now', ?), datetime('now', ?), ?, ?)""",
                    (pid, f'-{15-i} hours', f'-{14-i} hours',
                     'completed' if i % 3 != 0 else 'stopped', i * 2),
                )
            await db.commit()

        start = time.monotonic()
        resp = await client.get(f"/api/projects/{pid}/analytics")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert elapsed < 1.0, f"Project analytics took {elapsed:.3f}s (max 1.0s)"


class TestSystemEndpointPerformance:
    """Benchmark system/operational endpoints."""

    async def test_metrics_endpoint_speed(self, client):
        """GET /api/metrics should respond in < 500ms."""
        start = time.monotonic()
        resp = await client.get("/api/metrics")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert elapsed < 0.5, f"Metrics took {elapsed:.3f}s (max 0.5s)"

    async def test_system_info_speed(self, client):
        """GET /api/system should respond in < 1s (psutil may be slow)."""
        start = time.monotonic()
        resp = await client.get("/api/system")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert elapsed < 1.0, f"System info took {elapsed:.3f}s (max 1.0s)"

    async def test_health_with_db_check_speed(self, client):
        """GET /api/health should be fast even with DB health check."""
        start = time.monotonic()
        resp = await client.get("/api/health")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert elapsed < 0.5, f"Health with DB check took {elapsed:.3f}s"


class TestSearchAndFilterPerformance:
    """Benchmark search and filtering operations."""

    async def test_project_search_speed(self, client, tmp_path):
        """Search across 30 projects should respond in < 500ms."""
        for i in range(30):
            await client.post("/api/projects", json={
                "name": f"Alpha Project {i}" if i % 2 == 0 else f"Beta Project {i}",
                "goal": f"Benchmark goal {i}",
                "folder_path": str(tmp_path / f"search_perf_{i}").replace("\\", "/"),
            })

        start = time.monotonic()
        resp = await client.get("/api/projects?search=Alpha")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert len(resp.json()) == 15  # Half are Alpha
        assert elapsed < 0.5, f"Search took {elapsed:.3f}s (max 0.5s)"

    async def test_project_sort_speed(self, client, tmp_path):
        """Sorted project list should respond in < 500ms."""
        for i in range(20):
            await client.post("/api/projects", json={
                "name": f"Sort Test {i}",
                "goal": f"Sort testing {i}",
                "folder_path": str(tmp_path / f"sort_perf_{i}").replace("\\", "/"),
            })

        start = time.monotonic()
        resp = await client.get("/api/projects?sort=name")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert elapsed < 0.5, f"Sorted list took {elapsed:.3f}s (max 0.5s)"

    async def test_project_status_filter_speed(self, client, tmp_path):
        """Filtered project list should respond in < 500ms."""
        for i in range(20):
            await client.post("/api/projects", json={
                "name": f"Filter Test {i}",
                "goal": f"Filter testing {i}",
                "folder_path": str(tmp_path / f"filter_perf_{i}").replace("\\", "/"),
            })

        start = time.monotonic()
        resp = await client.get("/api/projects?status=created")
        elapsed = time.monotonic() - start

        assert resp.status_code == 200
        assert elapsed < 0.5, f"Filtered list took {elapsed:.3f}s (max 0.5s)"


class TestConcurrentPerformance:
    """Benchmark concurrent access patterns."""

    async def test_concurrent_mixed_operations(self, client, tmp_path):
        """Mixed concurrent reads + writes should complete in < 3s."""
        # Create base project
        resp = await client.post("/api/projects", json={
            "name": "Concurrent Base",
            "goal": "Concurrent testing",
            "folder_path": str(tmp_path / "concurrent_base").replace("\\", "/"),
        })
        assert resp.status_code == 201
        pid = resp.json()["id"]

        async def read_op():
            return await client.get(f"/api/projects/{pid}")

        async def list_op():
            return await client.get("/api/projects")

        async def health_op():
            return await client.get("/api/health")

        async def status_op():
            return await client.get(f"/api/swarm/status/{pid}")

        # 20 mixed operations
        ops = [read_op() for _ in range(5)]
        ops += [list_op() for _ in range(5)]
        ops += [health_op() for _ in range(5)]
        ops += [status_op() for _ in range(5)]

        start = time.monotonic()
        results = await asyncio.gather(*ops)
        elapsed = time.monotonic() - start

        for r in results:
            assert r.status_code == 200

        assert elapsed < 3.0, f"20 mixed ops took {elapsed:.3f}s (max 3.0s)"

    async def test_rapid_sequential_creates(self, client, tmp_path):
        """10 rapid sequential creates should complete in < 3s total."""
        start = time.monotonic()
        for i in range(10):
            resp = await client.post("/api/projects", json={
                "name": f"Rapid Create {i}",
                "goal": f"Sequential speed test {i}",
                "folder_path": str(tmp_path / f"rapid_{i}").replace("\\", "/"),
            })
            assert resp.status_code == 201
        elapsed = time.monotonic() - start

        assert elapsed < 3.0, f"10 sequential creates took {elapsed:.3f}s (max 3.0s)"
