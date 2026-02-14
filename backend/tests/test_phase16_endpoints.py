"""Tests for Phase 16 backend endpoints.

Covers:
- GET /api/projects/{id}/dashboard - Combined dashboard data
- GET /api/swarm/agents/{project_id}/metrics - Agent process metrics
- PATCH /api/swarm/runs/{run_id} - Swarm run annotations
- POST /api/projects/bulk/archive - Bulk archive
- POST /api/projects/bulk/unarchive - Bulk unarchive
- Auto-stop configuration
"""

import json
import time
from collections import deque
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


# ============================================================================
# Dashboard Endpoint Tests
# ============================================================================

class TestProjectDashboard:
    """Tests for GET /api/projects/{id}/dashboard."""

    async def test_dashboard_basic(self, client, project_with_folder):
        """Dashboard returns combined data for a project."""
        pid = project_with_folder["id"]
        resp = await client.get(f"/api/projects/{pid}/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == pid
        assert data["name"] == project_with_folder["name"]
        assert data["status"] == "created"
        assert "agents" in data
        assert "tasks" in data
        assert "total_runs" in data
        assert "recent_runs" in data
        assert "output_line_count" in data
        assert "last_output_lines" in data
        assert data["any_alive"] is False

    async def test_dashboard_task_progress(self, client, project_with_folder):
        """Dashboard reads task progress from TASKS.md."""
        pid = project_with_folder["id"]
        resp = await client.get(f"/api/projects/{pid}/dashboard")
        data = resp.json()
        # Mock project folder has 4 tasks (2 done, 2 pending)
        assert data["tasks"]["total"] == 4
        assert data["tasks"]["done"] == 2
        assert data["tasks"]["percent"] == 50.0

    async def test_dashboard_with_runs(self, client, project_with_folder, app):
        """Dashboard includes run stats and recent runs."""
        pid = project_with_folder["id"]
        from app import database
        import aiosqlite

        # Insert some test runs
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, started_at, ended_at) VALUES (?, 'completed', '2026-01-01 10:00:00', '2026-01-01 10:05:00')",
                (pid,),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, started_at, ended_at) VALUES (?, 'stopped', '2026-01-01 11:00:00', '2026-01-01 11:03:00')",
                (pid,),
            )
            await db.commit()

        resp = await client.get(f"/api/projects/{pid}/dashboard")
        data = resp.json()
        assert data["total_runs"] == 2
        assert data["avg_duration_seconds"] is not None
        assert len(data["recent_runs"]) == 2
        assert data["success_rate"] == 50.0  # 1 completed out of 2 finished

    async def test_dashboard_with_output(self, client, project_with_folder):
        """Dashboard includes output summary when agents have produced output."""
        pid = project_with_folder["id"]

        from app.routes.swarm import _project_output_buffers, _buffers_lock
        with _buffers_lock:
            buf = deque(maxlen=5000)
            for i in range(15):
                buf.append(f"[Claude-1] Output line {i}")
            _project_output_buffers[pid] = buf

        resp = await client.get(f"/api/projects/{pid}/dashboard")
        data = resp.json()
        assert data["output_line_count"] == 15
        assert len(data["last_output_lines"]) == 10  # Last 10 lines
        assert data["last_output_lines"][-1] == "[Claude-1] Output line 14"

    async def test_dashboard_404(self, client):
        """Dashboard returns 404 for nonexistent project."""
        resp = await client.get("/api/projects/9999/dashboard")
        assert resp.status_code == 404

    async def test_dashboard_with_agents(self, client, project_with_folder):
        """Dashboard includes live agent info when agents are tracked."""
        pid = project_with_folder["id"]
        from app.routes.swarm import (
            _agent_processes, _agent_output_buffers,
            _agent_started_at, _buffers_lock,
        )

        # Simulate a tracked agent
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # alive
        mock_proc.pid = 12345
        mock_proc.stdin = None
        key = f"{pid}:Claude-1"
        _agent_processes[key] = mock_proc
        _agent_started_at[key] = "2026-02-12T10:00:00"
        with _buffers_lock:
            _agent_output_buffers[key] = deque(["line1", "line2"], maxlen=5000)

        resp = await client.get(f"/api/projects/{pid}/dashboard")
        data = resp.json()
        assert data["any_alive"] is True
        assert len(data["agents"]) == 1
        assert data["agents"][0]["name"] == "Claude-1"
        assert data["agents"][0]["alive"] is True
        assert data["agents"][0]["output_lines"] == 2


# ============================================================================
# Agent Metrics Endpoint Tests
# ============================================================================

class TestAgentMetrics:
    """Tests for GET /api/swarm/agents/{project_id}/metrics."""

    async def test_metrics_no_agents(self, client, created_project):
        """Metrics returns empty list when no agents are tracked."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/agents/{pid}/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == pid
        assert data["agents"] == []
        assert isinstance(data["psutil_available"], bool)

    async def test_metrics_with_dead_agent(self, client, created_project):
        """Metrics returns null values for dead agents."""
        pid = created_project["id"]
        from app.routes.swarm import _agent_processes

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # dead
        mock_proc.returncode = 1
        mock_proc.pid = 99999
        _agent_processes[f"{pid}:Claude-1"] = mock_proc

        resp = await client.get(f"/api/swarm/agents/{pid}/metrics")
        data = resp.json()
        assert len(data["agents"]) == 1
        assert data["agents"][0]["name"] == "Claude-1"
        assert data["agents"][0]["alive"] is False
        assert data["agents"][0]["cpu_percent"] is None

    async def test_metrics_with_alive_agent_no_psutil(self, client, created_project):
        """Metrics calculates uptime from started_at when psutil unavailable."""
        pid = created_project["id"]
        from app.routes.swarm import _agent_processes, _agent_started_at

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # alive
        mock_proc.pid = 99999
        key = f"{pid}:Claude-1"
        _agent_processes[key] = mock_proc
        _agent_started_at[key] = datetime.now().isoformat()

        with patch("app.routes.swarm._PSUTIL_AVAILABLE", False):
            resp = await client.get(f"/api/swarm/agents/{pid}/metrics")
            data = resp.json()
            assert data["psutil_available"] is False
            assert len(data["agents"]) == 1
            assert data["agents"][0]["alive"] is True
            # Uptime should be very small (just created)
            assert data["agents"][0]["uptime_seconds"] is not None
            assert data["agents"][0]["uptime_seconds"] < 10

    async def test_metrics_404(self, client):
        """Metrics returns 404 for nonexistent project."""
        resp = await client.get("/api/swarm/agents/9999/metrics")
        assert resp.status_code == 404


# ============================================================================
# Swarm Run Annotations Tests
# ============================================================================

class TestSwarmRunAnnotations:
    """Tests for PATCH /api/swarm/runs/{run_id}."""

    async def _create_run(self, db_path):
        """Helper to create a test swarm run."""
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "INSERT INTO swarm_runs (project_id, status, started_at, ended_at) "
                "VALUES (1, 'completed', '2026-01-01 10:00:00', '2026-01-01 10:05:00')"
            )
            await db.commit()
            return cursor.lastrowid

    async def test_annotate_label(self, client, created_project, app):
        """Can add a label to a run."""
        from app import database
        run_id = await self._create_run(database.DB_PATH)

        resp = await client.patch(f"/api/swarm/runs/{run_id}", json={"label": "v1.0 release"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["label"] == "v1.0 release"
        assert data["id"] == run_id

    async def test_annotate_notes(self, client, created_project, app):
        """Can add notes to a run."""
        from app import database
        run_id = await self._create_run(database.DB_PATH)

        resp = await client.patch(f"/api/swarm/runs/{run_id}", json={"notes": "Good run, all tests passed"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["notes"] == "Good run, all tests passed"

    async def test_annotate_both(self, client, created_project, app):
        """Can add label and notes simultaneously."""
        from app import database
        run_id = await self._create_run(database.DB_PATH)

        resp = await client.patch(f"/api/swarm/runs/{run_id}", json={
            "label": "hotfix",
            "notes": "Emergency fix for auth bug",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["label"] == "hotfix"
        assert data["notes"] == "Emergency fix for auth bug"

    async def test_annotate_update(self, client, created_project, app):
        """Can update existing annotations."""
        from app import database
        run_id = await self._create_run(database.DB_PATH)

        # Set initial
        await client.patch(f"/api/swarm/runs/{run_id}", json={"label": "draft"})
        # Update
        resp = await client.patch(f"/api/swarm/runs/{run_id}", json={"label": "final"})
        assert resp.status_code == 200
        assert resp.json()["label"] == "final"

    async def test_annotate_empty_body(self, client, created_project, app):
        """Empty update body returns current data without changes."""
        from app import database
        run_id = await self._create_run(database.DB_PATH)

        resp = await client.patch(f"/api/swarm/runs/{run_id}", json={})
        assert resp.status_code == 200
        assert resp.json()["id"] == run_id

    async def test_annotate_404(self, client):
        """Annotating nonexistent run returns 404."""
        resp = await client.patch("/api/swarm/runs/9999", json={"label": "test"})
        assert resp.status_code == 404

    async def test_annotations_in_history(self, client, created_project, app):
        """Annotations appear in swarm history endpoint."""
        from app import database
        run_id = await self._create_run(database.DB_PATH)

        await client.patch(f"/api/swarm/runs/{run_id}", json={
            "label": "tagged",
            "notes": "History test",
        })

        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/history/{pid}")
        assert resp.status_code == 200
        runs = resp.json()["runs"]
        assert len(runs) >= 1
        tagged = [r for r in runs if r["id"] == run_id][0]
        assert tagged["label"] == "tagged"
        assert tagged["notes"] == "History test"

    async def test_annotate_label_max_length(self, client, created_project, app):
        """Label exceeding max_length is rejected."""
        from app import database
        run_id = await self._create_run(database.DB_PATH)

        resp = await client.patch(f"/api/swarm/runs/{run_id}", json={"label": "x" * 101})
        assert resp.status_code == 422


# ============================================================================
# Bulk Archive/Unarchive Tests
# ============================================================================

class TestBulkArchive:
    """Tests for POST /api/projects/bulk/archive and /bulk/unarchive."""

    async def _create_projects(self, client, tmp_path, count=3):
        """Helper to create multiple test projects."""
        ids = []
        for i in range(count):
            resp = await client.post("/api/projects", json={
                "name": f"Project {i}",
                "goal": f"Goal {i}",
                "folder_path": str(tmp_path / f"proj_{i}").replace("\\", "/"),
            })
            assert resp.status_code == 201
            ids.append(resp.json()["id"])
        return ids

    async def test_bulk_archive(self, client, tmp_path):
        """Archive multiple projects at once."""
        ids = await self._create_projects(client, tmp_path)

        resp = await client.post("/api/projects/bulk/archive", json={"project_ids": ids})
        assert resp.status_code == 200
        data = resp.json()
        assert sorted(data["archived"]) == sorted(ids)
        assert data["already_archived"] == []
        assert data["not_found"] == []

    async def test_bulk_archive_mixed(self, client, tmp_path):
        """Bulk archive with mix of valid, already-archived, and nonexistent IDs."""
        ids = await self._create_projects(client, tmp_path, 2)

        # Archive the first one individually
        await client.post(f"/api/projects/{ids[0]}/archive")

        resp = await client.post("/api/projects/bulk/archive", json={
            "project_ids": [ids[0], ids[1], 9999],
        })
        data = resp.json()
        assert data["archived"] == [ids[1]]
        assert data["already_archived"] == [ids[0]]
        assert data["not_found"] == [9999]

    async def test_bulk_unarchive(self, client, tmp_path):
        """Unarchive multiple projects at once."""
        ids = await self._create_projects(client, tmp_path)

        # Archive all first
        await client.post("/api/projects/bulk/archive", json={"project_ids": ids})

        resp = await client.post("/api/projects/bulk/unarchive", json={"project_ids": ids})
        assert resp.status_code == 200
        data = resp.json()
        assert sorted(data["unarchived"]) == sorted(ids)

    async def test_bulk_unarchive_mixed(self, client, tmp_path):
        """Bulk unarchive with mix of archived, not-archived, and nonexistent."""
        ids = await self._create_projects(client, tmp_path, 2)
        await client.post(f"/api/projects/{ids[0]}/archive")

        resp = await client.post("/api/projects/bulk/unarchive", json={
            "project_ids": [ids[0], ids[1], 9999],
        })
        data = resp.json()
        assert data["unarchived"] == [ids[0]]
        assert data["not_archived"] == [ids[1]]
        assert data["not_found"] == [9999]

    async def test_bulk_archive_empty_list(self, client):
        """Empty project_ids list is rejected by validation."""
        resp = await client.post("/api/projects/bulk/archive", json={"project_ids": []})
        assert resp.status_code == 422

    async def test_bulk_archive_too_many(self, client):
        """More than 50 project_ids is rejected."""
        resp = await client.post("/api/projects/bulk/archive", json={
            "project_ids": list(range(1, 52)),
        })
        assert resp.status_code == 422

    async def test_bulk_unarchive_all_not_found(self, client):
        """Bulk unarchive with all nonexistent IDs."""
        resp = await client.post("/api/projects/bulk/unarchive", json={
            "project_ids": [9998, 9999],
        })
        data = resp.json()
        assert data["unarchived"] == []
        assert data["not_found"] == [9998, 9999]


# ============================================================================
# Auto-Stop Configuration Tests
# ============================================================================

class TestAutoStopConfig:
    """Tests for auto-stop configuration via project config."""

    async def test_config_accepts_auto_stop_minutes(self, client, created_project):
        """Project config accepts auto_stop_minutes field."""
        pid = created_project["id"]
        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "auto_stop_minutes": 30,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["config"]["auto_stop_minutes"] == 30

    async def test_config_auto_stop_zero_disables(self, client, created_project):
        """auto_stop_minutes=0 is valid (disabled)."""
        pid = created_project["id"]
        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "auto_stop_minutes": 0,
        })
        assert resp.status_code == 200
        assert resp.json()["config"]["auto_stop_minutes"] == 0

    async def test_config_auto_stop_max_1440(self, client, created_project):
        """auto_stop_minutes cannot exceed 1440 (24 hours)."""
        pid = created_project["id"]
        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "auto_stop_minutes": 1441,
        })
        assert resp.status_code == 422

    async def test_auto_stop_reads_project_config(self, app):
        """_get_project_auto_stop reads from project config."""
        from app import database
        from app.routes.swarm import _get_project_auto_stop
        import aiosqlite

        # Create a project with auto_stop_minutes config
        async with aiosqlite.connect(database.DB_PATH) as db:
            cursor = await db.execute(
                "INSERT INTO projects (name, goal, folder_path, config) VALUES (?, ?, ?, ?)",
                ("Test", "Test", "/tmp/test", json.dumps({"auto_stop_minutes": 15})),
            )
            await db.commit()
            pid = cursor.lastrowid

        result = await _get_project_auto_stop(pid)
        assert result == 15

    async def test_auto_stop_falls_back_to_global(self, app):
        """_get_project_auto_stop falls back to global config when not set."""
        from app.routes.swarm import _get_project_auto_stop

        with patch("app.routes.swarm.config") as mock_config:
            mock_config.AUTO_STOP_MINUTES = 45
            result = await _get_project_auto_stop(99999)
            assert result == 45


# ============================================================================
# API versioning for new endpoints
# ============================================================================

class TestPhase16ApiVersioning:
    """Verify new endpoints work under /api/v1/ prefix."""

    async def test_dashboard_v1(self, client, project_with_folder):
        """Dashboard works via /api/v1/ prefix."""
        pid = project_with_folder["id"]
        resp = await client.get(f"/api/v1/projects/{pid}/dashboard")
        assert resp.status_code == 200
        assert resp.json()["project_id"] == pid

    async def test_metrics_v1(self, client, created_project):
        """Agent metrics works via /api/v1/ prefix."""
        pid = created_project["id"]
        resp = await client.get(f"/api/v1/swarm/agents/{pid}/metrics")
        assert resp.status_code == 200

    async def test_annotate_run_v1(self, client, created_project, app):
        """Run annotation works via /api/v1/ prefix."""
        from app import database
        import aiosqlite
        async with aiosqlite.connect(database.DB_PATH) as db:
            cursor = await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (?, 'completed')",
                (created_project["id"],),
            )
            await db.commit()
            run_id = cursor.lastrowid

        resp = await client.patch(f"/api/v1/swarm/runs/{run_id}", json={"label": "v1test"})
        assert resp.status_code == 200

    async def test_bulk_archive_v1(self, client, created_project):
        """Bulk archive works via /api/v1/ prefix."""
        resp = await client.post("/api/v1/projects/bulk/archive", json={
            "project_ids": [created_project["id"]],
        })
        assert resp.status_code == 200
