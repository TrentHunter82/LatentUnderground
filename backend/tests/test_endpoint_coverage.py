"""Tests filling endpoint coverage gaps: API versioning, plugin errors, rate limiting, webhook SSRF."""

import os
import time

import pytest
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Group 1: API Versioning
# ---------------------------------------------------------------------------

class TestAPIVersioningCoverage:
    """Verify /api/v1/ routes return identical data and deprecation header behavior."""

    @pytest.mark.asyncio
    async def test_v1_projects_returns_same_data(self, client, sample_project_data):
        """GET /api/v1/projects should return the same data as GET /api/projects."""
        await client.post("/api/projects", json=sample_project_data)

        unversioned = await client.get("/api/projects")
        versioned = await client.get("/api/v1/projects")

        assert unversioned.status_code == 200
        assert versioned.status_code == 200
        # Both should return the same project list
        assert unversioned.json() == versioned.json()

    @pytest.mark.asyncio
    async def test_v1_health_returns_same_data(self, client):
        """GET /api/v1/health should return the same data as GET /api/health."""
        unversioned = await client.get("/api/health")
        versioned = await client.get("/api/v1/health")

        assert unversioned.status_code == 200
        assert versioned.status_code == 200

        udata = unversioned.json()
        vdata = versioned.json()
        # Core fields must match (uptime_seconds may differ by 1)
        assert udata["app"] == vdata["app"]
        assert udata["version"] == vdata["version"]
        assert udata["status"] == vdata["status"]
        assert udata["db"] == vdata["db"]

    @pytest.mark.asyncio
    async def test_unversioned_gets_deprecation_headers(self, client):
        """GET /api/projects should include x-api-deprecation and sunset headers."""
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        assert resp.headers.get("x-api-deprecation") == "true"
        assert resp.headers.get("sunset") == "2026-12-31"

    @pytest.mark.asyncio
    async def test_v1_no_deprecation_headers(self, client):
        """GET /api/v1/projects should NOT include deprecation headers."""
        resp = await client.get("/api/v1/projects")
        assert resp.status_code == 200
        assert resp.headers.get("x-api-deprecation") is None
        assert resp.headers.get("sunset") is None


# ---------------------------------------------------------------------------
# Group 2: Plugin Error Cases
# ---------------------------------------------------------------------------

class TestPluginErrorCases:
    """Tests for plugin endpoints returning proper error codes on missing plugins."""

    @pytest.fixture(autouse=True)
    def _clean_plugins(self):
        """Clear global plugin manager state between tests."""
        from app.plugins import plugin_manager

        original_dir = plugin_manager.plugins_dir
        plugin_manager._plugins.clear()
        plugin_manager._disabled.clear()
        yield
        plugin_manager._plugins.clear()
        plugin_manager._disabled.clear()
        plugin_manager.plugins_dir = original_dir

    @pytest.mark.asyncio
    async def test_get_nonexistent_plugin(self, client):
        """GET /api/plugins/nonexistent should return 404."""
        resp = await client.get("/api/plugins/nonexistent")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_enable_nonexistent_plugin(self, client):
        """POST /api/plugins/nonexistent/enable should return 404."""
        resp = await client.post("/api/plugins/nonexistent/enable")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Group 3: Rate Limiting
# ---------------------------------------------------------------------------

class TestRateLimiting:
    """Tests for the RateLimitMiddleware behavior with rate limiting enabled."""

    @pytest.mark.asyncio
    async def test_rate_limit_returns_429(self, client, sample_project_data):
        """With write_rpm=2, the third POST to the same endpoint should get 429."""
        from app.main import RateLimitMiddleware

        # Find the RateLimitMiddleware instance in the middleware stack and
        # temporarily enable rate limiting with a very low threshold.
        middleware = _find_rate_limit_middleware(client)
        original_write_rpm = middleware.write_rpm
        original_requests = dict(middleware._requests)
        middleware.write_rpm = 2
        middleware._requests.clear()

        try:
            # First two requests should succeed (201 = created)
            r1 = await client.post("/api/projects", json=sample_project_data)
            assert r1.status_code == 201

            data2 = dict(sample_project_data)
            data2["name"] = "Second Project"
            r2 = await client.post("/api/projects", json=data2)
            assert r2.status_code == 201

            # Third POST to the same path should be rate limited
            data3 = dict(sample_project_data)
            data3["name"] = "Third Project"
            r3 = await client.post("/api/projects", json=data3)
            assert r3.status_code == 429
            assert "Rate limit exceeded" in r3.json()["detail"]
        finally:
            middleware.write_rpm = original_write_rpm
            middleware._requests.clear()
            middleware._requests.update(original_requests)

    @pytest.mark.asyncio
    async def test_rate_limit_skips_get_requests(self, client):
        """GET requests use read_rpm, not write_rpm. With read_rpm=0 (disabled), GETs pass."""
        from app.main import RateLimitMiddleware

        middleware = _find_rate_limit_middleware(client)
        original_write_rpm = middleware.write_rpm
        original_read_rpm = middleware.read_rpm
        middleware.write_rpm = 1  # Very low write limit
        middleware.read_rpm = 0  # Read limiting disabled
        middleware._requests.clear()

        try:
            # Multiple GET requests should all succeed (not rate limited)
            for _ in range(5):
                resp = await client.get("/api/projects")
                assert resp.status_code == 200
        finally:
            middleware.write_rpm = original_write_rpm
            middleware.read_rpm = original_read_rpm
            middleware._requests.clear()

    @pytest.mark.asyncio
    async def test_rate_limit_per_endpoint(self, client, sample_project_data, tmp_path):
        """Different POST endpoints each have their own rate limit bucket."""
        from app.main import RateLimitMiddleware

        middleware = _find_rate_limit_middleware(client)
        original_write_rpm = middleware.write_rpm
        middleware.write_rpm = 1
        middleware._requests.clear()

        try:
            # First POST to /api/projects should succeed
            r1 = await client.post("/api/projects", json=sample_project_data)
            assert r1.status_code == 201

            # Second POST to /api/projects should be rate-limited
            data2 = dict(sample_project_data)
            data2["name"] = "Another Project"
            r2 = await client.post("/api/projects", json=data2)
            assert r2.status_code == 429

            # But POST to a different endpoint (/api/webhooks) should still work
            r3 = await client.post("/api/webhooks", json={
                "url": "https://example.com/hook",
                "events": ["swarm_launched"],
            })
            assert r3.status_code == 201
        finally:
            middleware.write_rpm = original_write_rpm
            middleware._requests.clear()


# ---------------------------------------------------------------------------
# Group 4: Webhook SSRF Validation
# ---------------------------------------------------------------------------

class TestWebhookSSRF:
    """Tests for webhook URL validation preventing SSRF attacks."""

    @pytest.mark.asyncio
    async def test_webhook_rejects_localhost_url(self, client):
        """POST webhook with http://localhost/hook should return 400."""
        resp = await client.post("/api/webhooks", json={
            "url": "http://localhost/hook",
            "events": ["swarm_launched"],
        })
        assert resp.status_code == 400
        assert "localhost" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_webhook_rejects_private_ip(self, client):
        """POST webhook with http://10.0.0.1/hook should return 400."""
        resp = await client.post("/api/webhooks", json={
            "url": "http://10.0.0.1/hook",
            "events": ["swarm_launched"],
        })
        assert resp.status_code == 400
        assert "private" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_webhook_rejects_ftp_scheme(self, client):
        """POST webhook with ftp://example.com/hook should return 400."""
        resp = await client.post("/api/webhooks", json={
            "url": "ftp://example.com/hook",
            "events": ["swarm_launched"],
        })
        assert resp.status_code == 400
        assert "http" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_rate_limit_middleware(client: AsyncClient):
    """Walk the ASGI middleware stack to find the RateLimitMiddleware instance.

    The app is wrapped as: APIVersionMiddleware -> FastAPI(middleware_stack).
    FastAPI's middleware stack is built internally. We need to dig through
    the ASGI layers to find our RateLimitMiddleware.
    """
    from app.main import RateLimitMiddleware

    # The transport holds the ASGI app reference
    asgi_app = client._transport.app  # type: ignore[attr-defined]

    # Walk through known wrapper layers
    candidates = [asgi_app]
    visited = set()

    while candidates:
        obj = candidates.pop()
        obj_id = id(obj)
        if obj_id in visited:
            continue
        visited.add(obj_id)

        if isinstance(obj, RateLimitMiddleware):
            return obj

        # Check common attributes that hold nested apps/middleware
        for attr_name in ("app", "middleware_stack"):
            inner = getattr(obj, attr_name, None)
            if inner is not None and id(inner) not in visited:
                candidates.append(inner)

    raise RuntimeError("RateLimitMiddleware not found in middleware stack")
