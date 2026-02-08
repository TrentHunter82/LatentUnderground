"""Tests for log search endpoints (Phase 6)."""

import pytest


@pytest.mark.asyncio
async def test_search_logs_by_text(client, project_with_folder):
    """GET /api/logs/search?q=Line returns matching log lines."""
    pid = project_with_folder["id"]
    resp = await client.get(f"/api/logs/search?project_id={pid}&q=Line")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) > 0
    assert all("Line" in r["text"] for r in data["results"])


@pytest.mark.asyncio
async def test_search_logs_no_results(client, project_with_folder):
    """Search with no matches returns empty results."""
    pid = project_with_folder["id"]
    resp = await client.get(f"/api/logs/search?project_id={pid}&q=zzzznonexistent")
    assert resp.status_code == 200
    assert resp.json()["results"] == []


@pytest.mark.asyncio
async def test_search_logs_filter_by_agent(client, project_with_folder):
    """Filter logs to a specific agent."""
    pid = project_with_folder["id"]
    resp = await client.get(f"/api/logs/search?project_id={pid}&agent=Claude-1")
    assert resp.status_code == 200
    data = resp.json()
    assert all(r["agent"] == "Claude-1" for r in data["results"])


@pytest.mark.asyncio
async def test_search_logs_filter_by_level(client, project_with_folder):
    """Filter logs by severity level."""
    pid = project_with_folder["id"]
    resp = await client.get(f"/api/logs/search?project_id={pid}&level=error")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_search_logs_project_not_found(client):
    """Log search for non-existent project returns 404."""
    resp = await client.get("/api/logs/search?project_id=99999&q=test")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_search_logs_combined_filters(client, project_with_folder):
    """Text search + agent filter can be combined."""
    pid = project_with_folder["id"]
    resp = await client.get(f"/api/logs/search?project_id={pid}&q=Line&agent=Claude-1")
    assert resp.status_code == 200
    data = resp.json()
    assert all("Line" in r["text"] and r["agent"] == "Claude-1" for r in data["results"])


@pytest.mark.asyncio
async def test_search_logs_pagination(client, project_with_folder):
    """Log search supports offset/limit pagination."""
    pid = project_with_folder["id"]
    resp = await client.get(f"/api/logs/search?project_id={pid}&q=Line&limit=1&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) <= 1
