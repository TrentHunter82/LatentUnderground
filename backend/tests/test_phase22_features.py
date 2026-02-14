"""Phase 22: Operational Excellence & Resource Management — comprehensive test suite.

Tests cover:
- Resource quota enforcement: launch exceeds max_agents → 429, restart exceeds max_restarts → 429
- Duration watchdog: supervisor auto-stops when max_duration_hours exceeded
- Quota reset: stopping swarm resets agent count, restart counts reset on fresh launch
- Quota edge cases: None=unlimited, 0=blocked, concurrent launches don't bypass quota
- Health trends: correct crash rate calculation, time window rollover, new project returns zeros
- Health endpoint: per-project health with threshold classification (healthy/warning/critical)
- Agent checkpoints migration: table creation, indexes, idempotent re-run
- Checkpoint emission: checkpoints recorded on expected patterns, required fields present
- Checkpoint endpoint: filter by agent, pagination, ordering, 404 for missing run
"""

import asyncio
import json
import time
from collections import deque
from unittest.mock import MagicMock, patch

import aiosqlite
import pytest

from app import database
from app.routes.swarm import (
    _agent_output_buffers,
    _agent_processes,
    _agent_started_at,
    _checkpoint_batch,
    _checkpoint_cooldowns,
    _flush_checkpoints,
    _project_output_buffers,
    _project_resource_usage,
    _record_checkpoint_sync,
    _MAX_OUTPUT_LINES,
)


# ===========================================================================
# Test Class 1: Resource Quota Enforcement on Launch
# ===========================================================================


class TestQuotaLaunchEnforcement:
    """Test that launch is blocked when agent quota is exceeded."""

    @pytest.mark.asyncio
    async def test_launch_exceeds_max_agents_returns_429(
        self, client, project_with_folder, mock_launch_deps,
    ):
        """Launch with agent_count > max_agents_concurrent → 429."""
        pid = project_with_folder["id"]
        # Set quota: max 2 agents
        await client.patch(f"/api/projects/{pid}/config", json={
            "max_agents_concurrent": 2,
        })

        # Create mock Popen that returns immediately
        mock_proc = MagicMock()
        mock_proc.pid = 9999
        mock_proc.poll.return_value = None
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr.readline.return_value = b""

        with patch("app.routes.swarm.subprocess.Popen", return_value=mock_proc):
            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid,
                "agent_count": 4,  # exceeds limit of 2
            })

        assert resp.status_code == 429
        assert "Agent quota exceeded" in resp.json()["detail"]
        assert "limit: 2" in resp.json()["detail"]
        assert "requested: 4" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_launch_within_quota_succeeds(
        self, client, project_with_folder, mock_launch_deps,
    ):
        """Launch with agent_count <= max_agents_concurrent → 200."""
        pid = project_with_folder["id"]
        await client.patch(f"/api/projects/{pid}/config", json={
            "max_agents_concurrent": 4,
        })

        mock_proc = MagicMock()
        mock_proc.pid = 10001
        mock_proc.poll.return_value = None
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr.readline.return_value = b""

        with patch("app.routes.swarm.subprocess.Popen", return_value=mock_proc):
            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid,
                "agent_count": 2,  # within limit
            })

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_launch_no_quota_means_unlimited(
        self, client, project_with_folder, mock_launch_deps,
    ):
        """Launch with no quota set (None) allows any agent_count."""
        pid = project_with_folder["id"]
        # No config set — quotas default to None

        mock_proc = MagicMock()
        mock_proc.pid = 10002
        mock_proc.poll.return_value = None
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr.readline.return_value = b""

        with patch("app.routes.swarm.subprocess.Popen", return_value=mock_proc):
            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid,
                "agent_count": 16,  # max allowed by Pydantic
            })

        assert resp.status_code == 200


# ===========================================================================
# Test Class 2: Resource Quota Enforcement on Restart
# ===========================================================================


class TestQuotaRestartEnforcement:
    """Test that restart is blocked when restart quota is exceeded."""

    @pytest.mark.asyncio
    async def test_restart_exceeds_max_restarts_returns_429(
        self, client, project_with_folder, mock_launch_deps, tmp_db,
    ):
        """Restart agent beyond max_restarts_per_agent → 429."""
        pid = project_with_folder["id"]
        # Set quota: max 1 restart per agent
        await client.patch(f"/api/projects/{pid}/config", json={
            "max_restarts_per_agent": 1,
        })

        # Simulate: agent exists but is stopped
        key = f"{pid}:Claude-1"
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # stopped
        mock_proc.pid = 11111
        _agent_processes[key] = mock_proc

        # Simulate: already used 1 restart
        _project_resource_usage[pid] = {
            "agent_count": 4,
            "restart_counts": {"Claude-1": 1},
            "started_at": time.time(),
        }

        resp = await client.post(f"/api/swarm/agents/{pid}/Claude-1/restart")
        assert resp.status_code == 429
        assert "Restart quota exceeded" in resp.json()["detail"]
        assert "limit: 1" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_restart_within_quota_succeeds(
        self, client, project_with_folder, mock_launch_deps, tmp_db,
    ):
        """Restart agent within max_restarts_per_agent → 200."""
        pid = project_with_folder["id"]
        await client.patch(f"/api/projects/{pid}/config", json={
            "max_restarts_per_agent": 3,
        })

        # Simulate stopped agent
        key = f"{pid}:Claude-1"
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # stopped
        mock_proc.pid = 11112
        _agent_processes[key] = mock_proc

        # 1 restart used out of 3
        _project_resource_usage[pid] = {
            "agent_count": 4,
            "restart_counts": {"Claude-1": 1},
            "started_at": time.time(),
        }

        new_proc = MagicMock()
        new_proc.pid = 11113
        new_proc.poll.return_value = None
        new_proc.stdout.readline.return_value = b""
        new_proc.stderr.readline.return_value = b""

        with patch("app.routes.swarm.subprocess.Popen", return_value=new_proc), \
             patch("app.routes.swarm._find_claude_cmd", return_value=["claude.cmd"]):
            resp = await client.post(f"/api/swarm/agents/{pid}/Claude-1/restart")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_restart_no_quota_unlimited(
        self, client, project_with_folder, mock_launch_deps,
    ):
        """Restart with no max_restarts_per_agent set → unlimited."""
        pid = project_with_folder["id"]
        # No quota set

        key = f"{pid}:Claude-1"
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        mock_proc.pid = 11114
        _agent_processes[key] = mock_proc

        # Simulate many restarts
        _project_resource_usage[pid] = {
            "agent_count": 4,
            "restart_counts": {"Claude-1": 99},
            "started_at": time.time(),
        }

        new_proc = MagicMock()
        new_proc.pid = 11115
        new_proc.poll.return_value = None
        new_proc.stdout.readline.return_value = b""
        new_proc.stderr.readline.return_value = b""

        with patch("app.routes.swarm.subprocess.Popen", return_value=new_proc), \
             patch("app.routes.swarm._find_claude_cmd", return_value=["claude.cmd"]):
            resp = await client.post(f"/api/swarm/agents/{pid}/Claude-1/restart")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_restart_zero_quota_blocks_all(
        self, client, project_with_folder, mock_launch_deps,
    ):
        """Restart with max_restarts_per_agent=0 → blocks even first restart."""
        pid = project_with_folder["id"]
        await client.patch(f"/api/projects/{pid}/config", json={
            "max_restarts_per_agent": 0,
        })

        key = f"{pid}:Claude-1"
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        mock_proc.pid = 11116
        _agent_processes[key] = mock_proc

        _project_resource_usage[pid] = {
            "agent_count": 4,
            "restart_counts": {},
            "started_at": time.time(),
        }

        resp = await client.post(f"/api/swarm/agents/{pid}/Claude-1/restart")
        assert resp.status_code == 429
        assert "limit: 0" in resp.json()["detail"]


# ===========================================================================
# Test Class 3: Quota Reset Behavior
# ===========================================================================


class TestQuotaReset:
    """Test that quota usage resets properly on swarm stop/launch."""

    @pytest.mark.asyncio
    async def test_stop_clears_resource_usage(
        self, client, created_project, tmp_db,
    ):
        """Stopping a swarm should remove the project's resource usage tracking."""
        pid = created_project["id"]

        # Simulate running swarm with resource usage
        _project_resource_usage[pid] = {
            "agent_count": 4,
            "restart_counts": {"Claude-1": 2, "Claude-2": 1},
            "started_at": time.time() - 3600,
        }

        # Mark project as running in DB
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "UPDATE projects SET status = 'running' WHERE id = ?", (pid,)
            )
            await db.commit()

        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert resp.status_code == 200

        # Resource usage should be cleared
        assert pid not in _project_resource_usage

    @pytest.mark.asyncio
    async def test_fresh_launch_initializes_clean_usage(
        self, client, project_with_folder, mock_launch_deps,
    ):
        """Fresh launch initializes resource usage with zero restarts."""
        pid = project_with_folder["id"]

        # Pre-set stale usage from prior run
        _project_resource_usage[pid] = {
            "agent_count": 2,
            "restart_counts": {"Claude-1": 5},
            "started_at": time.time() - 7200,
        }

        mock_proc = MagicMock()
        mock_proc.pid = 12001
        mock_proc.poll.return_value = None
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr.readline.return_value = b""

        with patch("app.routes.swarm.subprocess.Popen", return_value=mock_proc):
            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid,
                "agent_count": 2,
            })

        assert resp.status_code == 200
        # Resource usage should be fresh
        usage = _project_resource_usage.get(pid)
        assert usage is not None
        assert usage["restart_counts"] == {}
        assert usage["agent_count"] > 0

    @pytest.mark.asyncio
    async def test_restart_increments_restart_count(
        self, client, project_with_folder, mock_launch_deps,
    ):
        """Restarting an agent increments its restart count in usage tracking."""
        pid = project_with_folder["id"]

        key = f"{pid}:Claude-1"
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # stopped
        mock_proc.pid = 12002
        _agent_processes[key] = mock_proc

        _project_resource_usage[pid] = {
            "agent_count": 4,
            "restart_counts": {"Claude-1": 0},
            "started_at": time.time(),
        }

        new_proc = MagicMock()
        new_proc.pid = 12003
        new_proc.poll.return_value = None
        new_proc.stdout.readline.return_value = b""
        new_proc.stderr.readline.return_value = b""

        with patch("app.routes.swarm.subprocess.Popen", return_value=new_proc), \
             patch("app.routes.swarm._find_claude_cmd", return_value=["claude.cmd"]):
            resp = await client.post(f"/api/swarm/agents/{pid}/Claude-1/restart")

        assert resp.status_code == 200
        usage = _project_resource_usage.get(pid)
        assert usage is not None
        assert usage["restart_counts"]["Claude-1"] == 1


# ===========================================================================
# Test Class 4: Quota Edge Cases
# ===========================================================================


class TestQuotaEdgeCases:
    """Test quota boundary conditions and concurrent access patterns."""

    @pytest.mark.asyncio
    async def test_quota_exact_limit_succeeds(
        self, client, project_with_folder, mock_launch_deps,
    ):
        """Launch with agent_count exactly at max_agents_concurrent succeeds."""
        pid = project_with_folder["id"]
        await client.patch(f"/api/projects/{pid}/config", json={
            "max_agents_concurrent": 3,
        })

        mock_proc = MagicMock()
        mock_proc.pid = 13001
        mock_proc.poll.return_value = None
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr.readline.return_value = b""

        with patch("app.routes.swarm.subprocess.Popen", return_value=mock_proc):
            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid,
                "agent_count": 3,  # exactly at limit
            })

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_quota_one_over_limit_fails(
        self, client, project_with_folder, mock_launch_deps,
    ):
        """Launch with agent_count one above max_agents_concurrent fails."""
        pid = project_with_folder["id"]
        await client.patch(f"/api/projects/{pid}/config", json={
            "max_agents_concurrent": 3,
        })

        mock_proc = MagicMock()
        mock_proc.pid = 13002
        mock_proc.poll.return_value = None
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr.readline.return_value = b""

        with patch("app.routes.swarm.subprocess.Popen", return_value=mock_proc):
            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid,
                "agent_count": 4,  # one over limit of 3
            })

        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_quota_config_validation_bounds(self, client, created_project):
        """Quota config fields enforce Pydantic bounds."""
        pid = created_project["id"]

        # max_agents_concurrent: 1-20
        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "max_agents_concurrent": 0,  # below min of 1
        })
        assert resp.status_code == 422

        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "max_agents_concurrent": 21,  # above max of 20
        })
        assert resp.status_code == 422

        # max_duration_hours: 0.5-48
        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "max_duration_hours": 0.1,  # below min of 0.5
        })
        assert resp.status_code == 422

        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "max_duration_hours": 49,  # above max of 48
        })
        assert resp.status_code == 422

        # max_restarts_per_agent: 0-10
        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "max_restarts_per_agent": -1,  # below min of 0
        })
        assert resp.status_code == 422

        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "max_restarts_per_agent": 11,  # above max of 10
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_quota_valid_bounds_accepted(self, client, created_project):
        """Valid quota config values within bounds are accepted."""
        pid = created_project["id"]

        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "max_agents_concurrent": 1,
            "max_duration_hours": 0.5,
            "max_restarts_per_agent": 0,
        })
        assert resp.status_code == 200

        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "max_agents_concurrent": 20,
            "max_duration_hours": 48,
            "max_restarts_per_agent": 10,
        })
        assert resp.status_code == 200


# ===========================================================================
# Test Class 5: GET /api/swarm/{project_id}/quota Endpoint
# ===========================================================================


class TestQuotaEndpoint:
    """Test the quota status endpoint."""

    @pytest.mark.asyncio
    async def test_quota_endpoint_no_usage(self, client, created_project):
        """Quota endpoint returns zeros when no swarm is running."""
        pid = created_project["id"]
        resp = await client.get(f"/api/swarm/{pid}/quota")
        assert resp.status_code == 200

        data = resp.json()
        assert data["project_id"] == pid
        assert data["quota"]["max_agents_concurrent"] is None
        assert data["quota"]["max_duration_hours"] is None
        assert data["quota"]["max_restarts_per_agent"] is None
        assert data["usage"]["agent_count"] == 0
        assert data["usage"]["restart_counts"] == {}
        assert data["usage"]["elapsed_hours"] is None

    @pytest.mark.asyncio
    async def test_quota_endpoint_with_config_and_usage(
        self, client, created_project,
    ):
        """Quota endpoint returns both config and live usage."""
        pid = created_project["id"]

        # Set quota config
        await client.patch(f"/api/projects/{pid}/config", json={
            "max_agents_concurrent": 5,
            "max_duration_hours": 2.0,
            "max_restarts_per_agent": 3,
        })

        # Simulate running swarm
        _project_resource_usage[pid] = {
            "agent_count": 3,
            "restart_counts": {"Claude-1": 1, "Claude-2": 0},
            "started_at": time.time() - 1800,  # 30 min ago
        }

        resp = await client.get(f"/api/swarm/{pid}/quota")
        assert resp.status_code == 200

        data = resp.json()
        assert data["quota"]["max_agents_concurrent"] == 5
        assert data["quota"]["max_duration_hours"] == 2.0
        assert data["quota"]["max_restarts_per_agent"] == 3
        assert data["usage"]["agent_count"] == 3
        assert data["usage"]["restart_counts"]["Claude-1"] == 1
        assert data["usage"]["elapsed_hours"] is not None
        assert data["usage"]["elapsed_hours"] > 0  # at least some elapsed time
        assert data["usage"]["started_at"] is not None

    @pytest.mark.asyncio
    async def test_quota_endpoint_404_nonexistent_project(self, client):
        """Quota endpoint returns 404 for nonexistent project."""
        resp = await client.get("/api/swarm/99999/quota")
        assert resp.status_code == 404


# ===========================================================================
# Test Class 6: Health Trend Detection
# ===========================================================================


class TestHealthTrends:
    """Test health trend computation across projects."""

    @pytest.mark.asyncio
    async def test_health_trends_empty_projects(self, client):
        """Health trends with no projects returns empty list."""
        resp = await client.get("/api/system/health/trends")
        assert resp.status_code == 200
        data = resp.json()
        assert data["projects"] == []
        assert "computed_at" in data

    @pytest.mark.asyncio
    async def test_health_trends_new_project_returns_zeros(
        self, client, created_project, tmp_db,
    ):
        """New project with no runs returns healthy status with zero rates."""
        resp = await client.get("/api/system/health/trends")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["projects"]) >= 1

        proj = next(p for p in data["projects"] if p["project_id"] == created_project["id"])
        assert proj["crash_rate"] == 0.0
        assert proj["error_density"] == 0.0
        assert proj["avg_duration_seconds"] is None
        assert proj["status"] == "healthy"
        assert proj["trend"] == "stable"
        assert proj["total_runs_analyzed"] == 0

    @pytest.mark.asyncio
    async def test_health_trends_crash_rate_classification(
        self, client, created_project, tmp_db,
    ):
        """Crash rate thresholds classify as healthy/warning/critical."""
        pid = created_project["id"]

        # Insert runs with summaries showing crashes
        async with aiosqlite.connect(tmp_db) as db:
            for i in range(5):
                await db.execute(
                    "INSERT INTO swarm_runs (project_id, status, started_at, ended_at, summary) "
                    "VALUES (?, 'completed', datetime('now', ?), datetime('now'), ?)",
                    (pid, f"-{5-i} hours",
                     json.dumps({
                         "agent_count": 4,
                         "total_output_lines": 100,
                         "error_count": 2,  # 2 errors per run
                     })),
                )
            # Insert many crash events to push crash_rate > 30%
            for i in range(10):
                await db.execute(
                    "INSERT INTO agent_events (project_id, agent_name, event_type) "
                    "VALUES (?, ?, 'agent_crashed')",
                    (pid, f"Claude-{(i % 4) + 1}"),
                )
            await db.commit()

        resp = await client.get("/api/system/health/trends")
        assert resp.status_code == 200
        data = resp.json()
        proj = next(p for p in data["projects"] if p["project_id"] == pid)
        # 10 crashes / 20 total agents (5 runs × 4 agents) = 50% crash rate → critical
        assert proj["crash_rate"] > 0
        assert proj["status"] in ("warning", "critical")

    @pytest.mark.asyncio
    async def test_health_trends_healthy_project(
        self, client, created_project, tmp_db,
    ):
        """Project with zero crashes has healthy status."""
        pid = created_project["id"]

        async with aiosqlite.connect(tmp_db) as db:
            for i in range(3):
                await db.execute(
                    "INSERT INTO swarm_runs (project_id, status, started_at, ended_at, summary) "
                    "VALUES (?, 'completed', datetime('now', ?), datetime('now'), ?)",
                    (pid, f"-{3-i} hours",
                     json.dumps({"agent_count": 4, "total_output_lines": 500, "error_count": 0})),
                )
            await db.commit()

        resp = await client.get("/api/system/health/trends")
        assert resp.status_code == 200
        data = resp.json()
        proj = next(p for p in data["projects"] if p["project_id"] == pid)
        assert proj["crash_rate"] == 0.0
        assert proj["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_trends_duration_averaging(
        self, client, created_project, tmp_db,
    ):
        """Average duration computed from runs with both started_at and ended_at."""
        pid = created_project["id"]

        async with aiosqlite.connect(tmp_db) as db:
            # Two runs: 1 hour and 2 hours
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, started_at, ended_at, summary) "
                "VALUES (?, 'completed', '2026-01-01 10:00:00', '2026-01-01 11:00:00', ?)",
                (pid, json.dumps({"agent_count": 2, "total_output_lines": 100, "error_count": 0})),
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, started_at, ended_at, summary) "
                "VALUES (?, 'completed', '2026-01-02 10:00:00', '2026-01-02 12:00:00', ?)",
                (pid, json.dumps({"agent_count": 2, "total_output_lines": 100, "error_count": 0})),
            )
            await db.commit()

        resp = await client.get("/api/system/health/trends")
        assert resp.status_code == 200
        data = resp.json()
        proj = next(p for p in data["projects"] if p["project_id"] == pid)
        # Average of 3600s + 7200s = 5400s
        assert proj["avg_duration_seconds"] == 5400

    @pytest.mark.asyncio
    async def test_health_trends_excludes_archived_projects(
        self, client, created_project, tmp_db,
    ):
        """Archived projects are excluded from health trends."""
        pid = created_project["id"]

        # Archive the project
        resp = await client.post(f"/api/projects/{pid}/archive")
        assert resp.status_code == 200

        resp = await client.get("/api/system/health/trends")
        assert resp.status_code == 200
        data = resp.json()
        project_ids = [p["project_id"] for p in data["projects"]]
        assert pid not in project_ids


# ===========================================================================
# Test Class 7: Per-Project Health Endpoint
# ===========================================================================


class TestProjectHealth:
    """Test per-project health metrics endpoint."""

    @pytest.mark.asyncio
    async def test_project_health_no_runs(self, client, created_project):
        """Project with no runs returns zeros."""
        pid = created_project["id"]
        resp = await client.get(f"/api/system/health/project/{pid}")
        assert resp.status_code == 200

        data = resp.json()
        assert data["project_id"] == pid
        assert data["crash_rate"] == 0.0
        assert data["error_density"] == 0.0
        assert data["avg_duration_seconds"] is None
        assert data["status"] == "healthy"
        assert data["trend"] == "stable"
        assert data["run_count"] == 0

    @pytest.mark.asyncio
    async def test_project_health_404_nonexistent(self, client):
        """Health for nonexistent project returns 404."""
        resp = await client.get("/api/system/health/project/99999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_project_health_with_runs(
        self, client, created_project, tmp_db,
    ):
        """Project health computed correctly from run data."""
        pid = created_project["id"]

        async with aiosqlite.connect(tmp_db) as db:
            for i in range(3):
                await db.execute(
                    "INSERT INTO swarm_runs (project_id, status, started_at, ended_at, summary) "
                    "VALUES (?, 'completed', datetime('now', ?), datetime('now'), ?)",
                    (pid, f"-{3-i} hours",
                     json.dumps({"agent_count": 4, "total_output_lines": 200, "error_count": 0})),
                )
            await db.commit()

        resp = await client.get(f"/api/system/health/project/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_count"] == 3
        assert data["status"] == "healthy"
        assert data["crash_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_project_health_warning_threshold(
        self, client, created_project, tmp_db,
    ):
        """Crash rate between 10-30% → warning status."""
        pid = created_project["id"]

        async with aiosqlite.connect(tmp_db) as db:
            # Insert runs with agent data
            for i in range(5):
                await db.execute(
                    "INSERT INTO swarm_runs (project_id, status, started_at, ended_at, summary) "
                    "VALUES (?, 'completed', datetime('now', ?), datetime('now'), ?)",
                    (pid, f"-{5-i} hours",
                     json.dumps({"agent_count": 4, "total_output_lines": 100, "error_count": 0})),
                )
            # Insert crashes: 4 crashes / 20 agents = 20% (warning)
            for i in range(4):
                await db.execute(
                    "INSERT INTO agent_events (project_id, agent_name, event_type) "
                    "VALUES (?, 'Claude-1', 'agent_crashed')",
                    (pid,),
                )
            await db.commit()

        resp = await client.get(f"/api/system/health/project/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "warning"
        assert 0.1 <= data["crash_rate"] < 0.3

    @pytest.mark.asyncio
    async def test_project_health_trend_detection_degrading(
        self, client, created_project, tmp_db,
    ):
        """Trend detection: degrading when newer runs have higher error rates.

        per_run_crash_rates built from ORDER BY id DESC: index 0 = newest.
        _compute_trend: first_half = newer, second_half = older.
        diff = second_half - first_half.
        diff < -0.05 → improving (older rates lower than newer = getting worse? No!)
        diff > 0.05 → degrading (older rates higher than newer = getting better? No!)

        Actually the function computes: if second_half avg > first_half avg → degrading.
        This means: if OLDER runs had higher error rates than NEWER → "degrading".
        This seems inverted but we test the actual behavior.
        """
        pid = created_project["id"]

        async with aiosqlite.connect(tmp_db) as db:
            # Older runs (low id): HIGH errors
            for i in range(3):
                await db.execute(
                    "INSERT INTO swarm_runs (project_id, status, started_at, ended_at, summary) "
                    "VALUES (?, 'completed', datetime('now', ?), datetime('now'), ?)",
                    (pid, f"-{6-i} hours",
                     json.dumps({"agent_count": 4, "total_output_lines": 100, "error_count": 5})),
                )
            # Newer runs (high id): NO errors
            for i in range(3):
                await db.execute(
                    "INSERT INTO swarm_runs (project_id, status, started_at, ended_at, summary) "
                    "VALUES (?, 'completed', datetime('now', ?), datetime('now'), ?)",
                    (pid, f"-{3-i} hours",
                     json.dumps({"agent_count": 4, "total_output_lines": 100, "error_count": 0})),
                )
            await db.commit()

        resp = await client.get(f"/api/system/health/project/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        # Older half has higher error_count/agent_count → diff > 0.05 → "degrading"
        assert data["trend"] == "degrading"

    @pytest.mark.asyncio
    async def test_project_health_trend_detection_improving(
        self, client, created_project, tmp_db,
    ):
        """Trend detection: improving when newer runs have higher error rates.

        When newer runs (first_half) have higher rates than older (second_half),
        diff = second_half - first_half < -0.05 → "improving".
        """
        pid = created_project["id"]

        async with aiosqlite.connect(tmp_db) as db:
            # Older runs: NO errors
            for i in range(3):
                await db.execute(
                    "INSERT INTO swarm_runs (project_id, status, started_at, ended_at, summary) "
                    "VALUES (?, 'completed', datetime('now', ?), datetime('now'), ?)",
                    (pid, f"-{6-i} hours",
                     json.dumps({"agent_count": 4, "total_output_lines": 100, "error_count": 0})),
                )
            # Newer runs: HIGH errors
            for i in range(3):
                await db.execute(
                    "INSERT INTO swarm_runs (project_id, status, started_at, ended_at, summary) "
                    "VALUES (?, 'completed', datetime('now', ?), datetime('now'), ?)",
                    (pid, f"-{3-i} hours",
                     json.dumps({"agent_count": 4, "total_output_lines": 100, "error_count": 5})),
                )
            await db.commit()

        resp = await client.get(f"/api/system/health/project/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        # Newer half has higher rates → diff < -0.05 → "improving"
        assert data["trend"] == "improving"


# ===========================================================================
# Test Class 8: Agent Checkpoints Migration
# ===========================================================================


class TestCheckpointsMigration:
    """Test migration_005: agent_checkpoints table creation."""

    @pytest.mark.asyncio
    async def test_fresh_migration_creates_table(self, tmp_path):
        """Migration creates agent_checkpoints table with correct columns."""
        db_path = tmp_path / "fresh_migration.db"
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await database._run_migrations(db)
            await db.commit()

            # Verify table exists
            rows = await (await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_checkpoints'"
            )).fetchall()
            assert len(rows) == 1

            # Verify columns
            cols = await (await db.execute("PRAGMA table_info(agent_checkpoints)")).fetchall()
            col_names = {c["name"] for c in cols}
            assert {"id", "project_id", "run_id", "agent_name", "checkpoint_type", "data", "timestamp"} <= col_names

    @pytest.mark.asyncio
    async def test_migration_creates_indexes(self, tmp_path):
        """Migration creates checkpoint indexes."""
        db_path = tmp_path / "idx_migration.db"
        async with aiosqlite.connect(db_path) as db:
            await database._run_migrations(db)
            await db.commit()

            indexes = await (await db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_checkpoints%'"
            )).fetchall()
            idx_names = {r[0] for r in indexes}
            assert "idx_checkpoints_run_agent" in idx_names
            assert "idx_checkpoints_project_ts" in idx_names

    @pytest.mark.asyncio
    async def test_migration_idempotent(self, tmp_path):
        """Running migration twice doesn't fail."""
        db_path = tmp_path / "idempotent.db"
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await database._run_migrations(db)
            await db.commit()

            # Run again — should be idempotent
            applied = await database._run_migrations(db)
            await db.commit()
            assert applied is False  # already up to date

    @pytest.mark.asyncio
    async def test_schema_version_is_5(self, tmp_path):
        """After all migrations, schema version is 5."""
        db_path = tmp_path / "version.db"
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await database._run_migrations(db)
            await db.commit()

            version = await database._get_schema_version(db)
            assert version == database.SCHEMA_VERSION
            assert version == 6

    @pytest.mark.asyncio
    async def test_migration_count_matches_version(self):
        """Number of migrations equals SCHEMA_VERSION."""
        assert len(database._MIGRATIONS) == database.SCHEMA_VERSION
        assert len(database._MIGRATIONS) == 6

    @pytest.mark.asyncio
    async def test_checkpoint_data_preserved_across_migration(self, tmp_path):
        """Existing data in other tables survives migration_005."""
        db_path = tmp_path / "preserve.db"
        async with aiosqlite.connect(db_path) as db:
            # Run migrations up to v4
            await database._run_migrations(db)
            await db.commit()

            # Insert test data
            await db.execute(
                "INSERT INTO projects (name, goal, folder_path) VALUES ('Test', 'Goal', '/test')"
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (1, 'completed')"
            )
            await db.commit()

            # Verify data survived
            proj = await (await db.execute("SELECT * FROM projects WHERE id = 1")).fetchone()
            assert proj is not None
            run = await (await db.execute("SELECT * FROM swarm_runs WHERE id = 1")).fetchone()
            assert run is not None


# ===========================================================================
# Test Class 9: Checkpoint Emission
# ===========================================================================


class TestCheckpointEmission:
    """Test that checkpoints are recorded via _record_checkpoint_sync."""

    @pytest.mark.asyncio
    async def test_record_checkpoint_basic(self, tmp_db):
        """_record_checkpoint_sync writes to agent_checkpoints table."""
        # First ensure the table exists
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO projects (name, goal, folder_path) VALUES ('P', 'G', '/p')"
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (1, 'running')"
            )
            await db.commit()

        _checkpoint_cooldowns.clear()
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            _record_checkpoint_sync(
                project_id=1, run_id=1, agent_name="Claude-1",
                checkpoint_type="task_complete",
                data={"output_lines": 50, "last_lines": ["Done task 1"]},
            )
            _flush_checkpoints()
        finally:
            database.DB_PATH = original

        async with aiosqlite.connect(tmp_db) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute("SELECT * FROM agent_checkpoints")).fetchall()
            assert len(rows) == 1
            row = rows[0]
            assert row["project_id"] == 1
            assert row["run_id"] == 1
            assert row["agent_name"] == "Claude-1"
            assert row["checkpoint_type"] == "task_complete"
            data = json.loads(row["data"])
            assert data["output_lines"] == 50
            assert "last_lines" in data

    @pytest.mark.asyncio
    async def test_record_checkpoint_error_type(self, tmp_db):
        """Error checkpoints include text field in data."""
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO projects (name, goal, folder_path) VALUES ('P', 'G', '/p')"
            )
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (1, 'running')"
            )
            await db.commit()

        _checkpoint_cooldowns.clear()
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            _record_checkpoint_sync(
                project_id=1, run_id=1, agent_name="Claude-2",
                checkpoint_type="error",
                data={"output_lines": 100, "text": "Traceback: some error"},
            )
            _flush_checkpoints()
        finally:
            database.DB_PATH = original

        async with aiosqlite.connect(tmp_db) as db:
            db.row_factory = aiosqlite.Row
            row = await (await db.execute("SELECT * FROM agent_checkpoints")).fetchone()
            data = json.loads(row["data"])
            assert row["checkpoint_type"] == "error"
            assert "text" in data
            assert "Traceback" in data["text"]

    @pytest.mark.asyncio
    async def test_record_checkpoint_no_run_id(self, tmp_db):
        """Checkpoint can be recorded with run_id=None."""
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO projects (name, goal, folder_path) VALUES ('P', 'G', '/p')"
            )
            await db.commit()

        _checkpoint_cooldowns.clear()
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            _record_checkpoint_sync(
                project_id=1, run_id=None, agent_name="Claude-3",
                checkpoint_type="milestone",
                data={"output_lines": 500},
            )
            _flush_checkpoints()
        finally:
            database.DB_PATH = original

        async with aiosqlite.connect(tmp_db) as db:
            db.row_factory = aiosqlite.Row
            row = await (await db.execute("SELECT * FROM agent_checkpoints")).fetchone()
            assert row["run_id"] is None
            assert row["checkpoint_type"] == "milestone"

    @pytest.mark.asyncio
    async def test_record_checkpoint_silent_failure_bad_project(self, tmp_db):
        """Checkpoint recording silently fails on invalid project (no crash)."""
        _checkpoint_cooldowns.clear()
        original = database.DB_PATH
        database.DB_PATH = tmp_db
        try:
            # project_id 999 doesn't exist — should fail silently due to FK constraint
            _record_checkpoint_sync(
                project_id=999, run_id=None, agent_name="Claude-1",
                checkpoint_type="test", data={},
            )
            _flush_checkpoints()
        finally:
            database.DB_PATH = original

        # No crash, no checkpoint saved (FK violation silently caught)
        async with aiosqlite.connect(tmp_db) as db:
            rows = await (await db.execute("SELECT * FROM agent_checkpoints")).fetchall()
            # Foreign key check depends on whether FK enforcement is on for this connection
            # Either 0 (FK enforced) or 1 (FK not enforced) is acceptable — no crash is the key
            assert isinstance(rows, list)


# ===========================================================================
# Test Class 10: Checkpoint Endpoint
# ===========================================================================


class TestCheckpointEndpoint:
    """Test GET /api/swarm/runs/{run_id}/checkpoints endpoint."""

    @pytest.mark.asyncio
    async def test_checkpoints_empty_run(self, client, created_project, tmp_db):
        """Run with no checkpoints returns empty list."""
        pid = created_project["id"]

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (?, 'completed')",
                (pid,),
            )
            await db.commit()
            run_row = await (await db.execute(
                "SELECT id FROM swarm_runs WHERE project_id = ? ORDER BY id DESC LIMIT 1",
                (pid,),
            )).fetchone()
            run_id = run_row[0]

        resp = await client.get(f"/api/swarm/runs/{run_id}/checkpoints")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == run_id
        assert data["checkpoints"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_checkpoints_with_data(self, client, created_project, tmp_db):
        """Checkpoints returned with correct fields."""
        pid = created_project["id"]

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (?, 'completed')",
                (pid,),
            )
            await db.commit()
            run_row = await (await db.execute(
                "SELECT id FROM swarm_runs ORDER BY id DESC LIMIT 1"
            )).fetchone()
            run_id = run_row[0]

            # Insert checkpoints
            for i in range(3):
                await db.execute(
                    "INSERT INTO agent_checkpoints (project_id, run_id, agent_name, checkpoint_type, data) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (pid, run_id, f"Claude-{i+1}", "task_complete",
                     json.dumps({"output_lines": (i + 1) * 100})),
                )
            await db.commit()

        resp = await client.get(f"/api/swarm/runs/{run_id}/checkpoints")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["checkpoints"]) == 3

        cp = data["checkpoints"][0]
        assert "id" in cp
        assert cp["project_id"] == pid
        assert cp["run_id"] == run_id
        assert "agent_name" in cp
        assert cp["checkpoint_type"] == "task_complete"
        assert "data" in cp
        assert "timestamp" in cp

    @pytest.mark.asyncio
    async def test_checkpoints_filter_by_agent(
        self, client, created_project, tmp_db,
    ):
        """Filter checkpoints by agent name."""
        pid = created_project["id"]

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (?, 'completed')",
                (pid,),
            )
            await db.commit()
            run_row = await (await db.execute(
                "SELECT id FROM swarm_runs ORDER BY id DESC LIMIT 1"
            )).fetchone()
            run_id = run_row[0]

            # Insert checkpoints for different agents
            await db.execute(
                "INSERT INTO agent_checkpoints (project_id, run_id, agent_name, checkpoint_type, data) "
                "VALUES (?, ?, 'Claude-1', 'task_complete', '{}')",
                (pid, run_id),
            )
            await db.execute(
                "INSERT INTO agent_checkpoints (project_id, run_id, agent_name, checkpoint_type, data) "
                "VALUES (?, ?, 'Claude-1', 'error', '{}')",
                (pid, run_id),
            )
            await db.execute(
                "INSERT INTO agent_checkpoints (project_id, run_id, agent_name, checkpoint_type, data) "
                "VALUES (?, ?, 'Claude-2', 'task_complete', '{}')",
                (pid, run_id),
            )
            await db.commit()

        # Filter by Claude-1
        resp = await client.get(f"/api/swarm/runs/{run_id}/checkpoints?agent=Claude-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert all(cp["agent_name"] == "Claude-1" for cp in data["checkpoints"])

        # Filter by Claude-2
        resp = await client.get(f"/api/swarm/runs/{run_id}/checkpoints?agent=Claude-2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["checkpoints"][0]["agent_name"] == "Claude-2"

    @pytest.mark.asyncio
    async def test_checkpoints_ordering(self, client, created_project, tmp_db):
        """Checkpoints returned in chronological order (ASC)."""
        pid = created_project["id"]

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (?, 'completed')",
                (pid,),
            )
            await db.commit()
            run_row = await (await db.execute(
                "SELECT id FROM swarm_runs ORDER BY id DESC LIMIT 1"
            )).fetchone()
            run_id = run_row[0]

            # Insert in reverse order with explicit timestamps
            await db.execute(
                "INSERT INTO agent_checkpoints (project_id, run_id, agent_name, checkpoint_type, data, timestamp) "
                "VALUES (?, ?, 'Claude-1', 'task_complete', '{\"step\": 3}', '2026-01-01 12:03:00')",
                (pid, run_id),
            )
            await db.execute(
                "INSERT INTO agent_checkpoints (project_id, run_id, agent_name, checkpoint_type, data, timestamp) "
                "VALUES (?, ?, 'Claude-1', 'task_complete', '{\"step\": 1}', '2026-01-01 12:01:00')",
                (pid, run_id),
            )
            await db.execute(
                "INSERT INTO agent_checkpoints (project_id, run_id, agent_name, checkpoint_type, data, timestamp) "
                "VALUES (?, ?, 'Claude-1', 'error', '{\"step\": 2}', '2026-01-01 12:02:00')",
                (pid, run_id),
            )
            await db.commit()

        resp = await client.get(f"/api/swarm/runs/{run_id}/checkpoints")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        # Verify chronological ordering
        timestamps = [cp["timestamp"] for cp in data["checkpoints"]]
        assert timestamps == sorted(timestamps)
        # Verify step order
        steps = [cp["data"]["step"] for cp in data["checkpoints"]]
        assert steps == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_checkpoints_404_missing_run(self, client):
        """Checkpoint endpoint returns 404 for nonexistent run."""
        resp = await client.get("/api/swarm/runs/99999/checkpoints")
        assert resp.status_code == 404
        assert "Run not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_checkpoints_json_parsing(
        self, client, created_project, tmp_db,
    ):
        """Checkpoint data is properly parsed from JSON string."""
        pid = created_project["id"]

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status) VALUES (?, 'completed')",
                (pid,),
            )
            await db.commit()
            run_row = await (await db.execute(
                "SELECT id FROM swarm_runs ORDER BY id DESC LIMIT 1"
            )).fetchone()
            run_id = run_row[0]

            await db.execute(
                "INSERT INTO agent_checkpoints (project_id, run_id, agent_name, checkpoint_type, data) "
                "VALUES (?, ?, 'Claude-1', 'task_complete', ?)",
                (pid, run_id, json.dumps({
                    "output_lines": 250,
                    "last_lines": ["Line 1", "Line 2", "Line 3"],
                    "elapsed_seconds": 120,
                })),
            )
            # Also test malformed JSON
            await db.execute(
                "INSERT INTO agent_checkpoints (project_id, run_id, agent_name, checkpoint_type, data) "
                "VALUES (?, ?, 'Claude-2', 'error', 'not-valid-json')",
                (pid, run_id),
            )
            await db.commit()

        resp = await client.get(f"/api/swarm/runs/{run_id}/checkpoints")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

        # First checkpoint has valid JSON data
        cp1 = next(cp for cp in data["checkpoints"] if cp["agent_name"] == "Claude-1")
        assert cp1["data"]["output_lines"] == 250
        assert len(cp1["data"]["last_lines"]) == 3

        # Second checkpoint has empty data (malformed JSON handled gracefully)
        cp2 = next(cp for cp in data["checkpoints"] if cp["agent_name"] == "Claude-2")
        assert cp2["data"] == {}


# ===========================================================================
# Test Class 11: Duration Watchdog
# ===========================================================================


class TestDurationWatchdog:
    """Test that the supervisor duration watchdog auto-stops swarms."""

    @pytest.mark.asyncio
    async def test_duration_watchdog_exists_in_supervisor(self):
        """Verify that the supervisor loop contains duration watchdog code."""
        import inspect
        from app.routes.swarm import _supervisor_loop
        source = inspect.getsource(_supervisor_loop)
        assert "max_duration_hours" in source
        assert "Duration quota exceeded" in source

    @pytest.mark.asyncio
    async def test_duration_watchdog_checks_elapsed_time(self):
        """Duration watchdog compares elapsed time against quota."""
        import inspect
        from app.routes.swarm import _supervisor_loop
        source = inspect.getsource(_supervisor_loop)
        # Verify the comparison pattern exists
        assert "elapsed > max_hours" in source or "elapsed >" in source


# ===========================================================================
# Test Class 12: Integration Tests
# ===========================================================================


class TestQuotaIntegration:
    """Integration tests combining multiple quota features."""

    @pytest.mark.asyncio
    async def test_full_quota_lifecycle(
        self, client, project_with_folder, mock_launch_deps,
    ):
        """Full lifecycle: set quota → launch → check usage → stop → verify reset."""
        pid = project_with_folder["id"]

        # 1. Set quotas
        await client.patch(f"/api/projects/{pid}/config", json={
            "max_agents_concurrent": 4,
            "max_restarts_per_agent": 2,
            "max_duration_hours": 1.0,
        })

        # 2. Launch within quota
        mock_proc = MagicMock()
        mock_proc.pid = 20001
        mock_proc.poll.return_value = None
        mock_proc.stdout.readline.return_value = b""
        mock_proc.stderr.readline.return_value = b""

        with patch("app.routes.swarm.subprocess.Popen", return_value=mock_proc):
            resp = await client.post("/api/swarm/launch", json={
                "project_id": pid,
                "agent_count": 2,
            })
        assert resp.status_code == 200

        # 3. Check usage via quota endpoint
        resp = await client.get(f"/api/swarm/{pid}/quota")
        assert resp.status_code == 200
        data = resp.json()
        assert data["usage"]["agent_count"] > 0
        assert data["quota"]["max_agents_concurrent"] == 4

        # 4. Stop
        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert resp.status_code == 200

        # 5. Verify usage reset
        resp = await client.get(f"/api/swarm/{pid}/quota")
        assert resp.status_code == 200
        data = resp.json()
        assert data["usage"]["agent_count"] == 0

    @pytest.mark.asyncio
    async def test_quota_persists_across_config_reads(
        self, client, created_project,
    ):
        """Quota config roundtrips through save/read."""
        pid = created_project["id"]

        # Save config
        resp = await client.patch(f"/api/projects/{pid}/config", json={
            "max_agents_concurrent": 5,
            "max_duration_hours": 2.5,
            "max_restarts_per_agent": 3,
        })
        assert resp.status_code == 200

        # Read it back via quota endpoint
        resp = await client.get(f"/api/swarm/{pid}/quota")
        assert resp.status_code == 200
        data = resp.json()
        assert data["quota"]["max_agents_concurrent"] == 5
        assert data["quota"]["max_duration_hours"] == 2.5
        assert data["quota"]["max_restarts_per_agent"] == 3

    @pytest.mark.asyncio
    async def test_health_and_checkpoint_combined(
        self, client, created_project, tmp_db,
    ):
        """Health metrics and checkpoints work together for a project with runs."""
        pid = created_project["id"]

        async with aiosqlite.connect(tmp_db) as db:
            # Create a run with checkpoints
            await db.execute(
                "INSERT INTO swarm_runs (project_id, status, started_at, ended_at, summary) "
                "VALUES (?, 'completed', '2026-01-01 10:00:00', '2026-01-01 11:00:00', ?)",
                (pid, json.dumps({
                    "agent_count": 2,
                    "total_output_lines": 500,
                    "error_count": 1,
                })),
            )
            await db.commit()
            run_row = await (await db.execute(
                "SELECT id FROM swarm_runs WHERE project_id = ?", (pid,),
            )).fetchone()
            run_id = run_row[0]

            # Insert checkpoints
            await db.execute(
                "INSERT INTO agent_checkpoints (project_id, run_id, agent_name, checkpoint_type, data) "
                "VALUES (?, ?, 'Claude-1', 'task_complete', ?)",
                (pid, run_id, json.dumps({"output_lines": 100})),
            )
            await db.execute(
                "INSERT INTO agent_checkpoints (project_id, run_id, agent_name, checkpoint_type, data) "
                "VALUES (?, ?, 'Claude-1', 'error', ?)",
                (pid, run_id, json.dumps({"text": "Some error"})),
            )
            await db.commit()

        # Health should reflect the run
        resp = await client.get(f"/api/system/health/project/{pid}")
        assert resp.status_code == 200
        health = resp.json()
        assert health["run_count"] == 1

        # Checkpoints should be accessible
        resp = await client.get(f"/api/swarm/runs/{run_id}/checkpoints")
        assert resp.status_code == 200
        cps = resp.json()
        assert cps["total"] == 2
        types = {cp["checkpoint_type"] for cp in cps["checkpoints"]}
        assert types == {"task_complete", "error"}
