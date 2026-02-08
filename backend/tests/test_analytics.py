"""Tests for project analytics endpoints (Phase 6)."""

import pytest


@pytest.mark.asyncio
async def test_analytics_empty_data(client, created_project):
    """Analytics for a project with no runs returns zero-value defaults."""
    resp = await client.get(f"/api/projects/{created_project['id']}/analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_runs"] == 0
    assert data["avg_duration"] is None


@pytest.mark.asyncio
async def test_analytics_not_found(client):
    """Analytics for non-existent project returns 404."""
    resp = await client.get("/api/projects/99999/analytics")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_analytics_multi_run_aggregation(client, created_project, tmp_db):
    """Analytics correctly aggregates across multiple swarm runs."""
    import aiosqlite

    pid = created_project["id"]
    async with aiosqlite.connect(tmp_db) as db:
        await db.execute(
            "INSERT INTO swarm_runs (project_id, status, tasks_completed, "
            "started_at, ended_at) VALUES (?, 'completed', 5, "
            "datetime('now', '-10 minutes'), datetime('now'))",
            (pid,),
        )
        await db.execute(
            "INSERT INTO swarm_runs (project_id, status, tasks_completed, "
            "started_at, ended_at) VALUES (?, 'completed', 3, "
            "datetime('now', '-20 minutes'), datetime('now', '-15 minutes'))",
            (pid,),
        )
        await db.commit()

    resp = await client.get(f"/api/projects/{pid}/analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_runs"] == 2
    assert data["total_tasks"] == 8
    assert data["avg_duration"] is not None


@pytest.mark.asyncio
async def test_analytics_response_fields(client, created_project):
    """Analytics response contains the expected field set."""
    resp = await client.get(f"/api/projects/{created_project['id']}/analytics")
    assert resp.status_code == 200
    data = resp.json()
    expected = {"total_runs", "avg_duration", "total_tasks", "success_rate", "project_id"}
    assert expected.issubset(set(data.keys()))
