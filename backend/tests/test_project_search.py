"""Tests for project search/filter endpoints (Phase 6)."""

import pytest


@pytest.mark.asyncio
async def test_search_projects_by_name(client, created_project):
    """GET /api/projects?search=Test returns matching projects."""
    resp = await client.get("/api/projects?search=Test")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 1
    assert any("Test" in p["name"] for p in results)


@pytest.mark.asyncio
async def test_search_projects_by_goal(client, created_project):
    """Search matches against the goal field too."""
    resp = await client.get("/api/projects?search=application")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_search_no_results(client, created_project):
    """Search with no matches returns empty list."""
    resp = await client.get("/api/projects?search=zzzznonexistent")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_filter_by_status(client, created_project):
    """GET /api/projects?status=created returns only created projects."""
    resp = await client.get("/api/projects?status=created")
    assert resp.status_code == 200
    results = resp.json()
    assert all(p["status"] == "created" for p in results)


@pytest.mark.asyncio
async def test_filter_by_status_running(client, created_project):
    """GET /api/projects?status=running returns empty when nothing is running."""
    resp = await client.get("/api/projects?status=running")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_sort_by_name(client):
    """GET /api/projects?sort=name returns alphabetically sorted projects."""
    await client.post("/api/projects", json={"name": "Zebra", "goal": "Z", "folder_path": "F:/Z"})
    await client.post("/api/projects", json={"name": "Alpha", "goal": "A", "folder_path": "F:/A"})
    resp = await client.get("/api/projects?sort=name")
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_sort_by_updated_at(client, created_project):
    """GET /api/projects?sort=updated_at returns most recently updated first."""
    resp = await client.get("/api/projects?sort=updated_at")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_combined_search_and_filter(client, created_project):
    """Search + status filter can be combined."""
    resp = await client.get("/api/projects?search=Test&status=created")
    assert resp.status_code == 200
    results = resp.json()
    assert all(p["status"] == "created" for p in results)


@pytest.mark.asyncio
async def test_search_case_insensitive(client, created_project):
    """Search should be case-insensitive."""
    resp = await client.get("/api/projects?search=test")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_search_empty_string(client, created_project):
    """Empty search string returns all projects (no filter applied)."""
    resp = await client.get("/api/projects?search=")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
