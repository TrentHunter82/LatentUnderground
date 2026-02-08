"""Tests for the /api/health endpoint."""

import pytest
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_health_ok(client):
    """Health endpoint returns 200 with status=ok when DB is reachable."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["db"] == "ok"


@pytest.mark.asyncio
async def test_health_has_all_fields(client):
    """Health response contains exactly the expected fields."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"status", "db", "app", "version", "uptime_seconds", "active_processes"}
    assert data["app"] == "Latent Underground"
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_health_degraded_on_db_failure(client):
    """Health endpoint returns 503 with status=degraded when DB is unreachable."""
    with patch("app.main.aiosqlite") as mock_aiosqlite:
        # Make aiosqlite.connect raise an exception
        mock_aiosqlite.connect.side_effect = Exception("DB connection failed")
        resp = await client.get("/api/health")

    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["db"] == "error"
    assert data["app"] == "Latent Underground"
    assert data["version"] == "0.1.0"
