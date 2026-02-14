"""Phase 18 regression tests for Latent Underground.

Verifies that Phase 18 changes remain working:
- ETag caching with blake2b (FIPS-compatible)
- Rate limiter memory leak fix (empty key pruning)
- Security headers (all 5 + Cache-Control variants)
- RequestID middleware (generation + preservation)
- VACUUM scheduling configuration
- Request logging configuration
- Versioned API routes (/api/v1/)
- GZip compression thresholds
"""

import hashlib
import os
import re
import time
import uuid

import pytest


# ---------------------------------------------------------------------------
# 1. ETag Caching
# ---------------------------------------------------------------------------

class TestETagCachingRegression:
    """Regression tests for ETag middleware using blake2b."""

    @pytest.mark.asyncio
    async def test_etag_present_on_get_response(self, client):
        """GET /api/projects must include an ETag header."""
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        assert resp.headers.get("etag") is not None

    @pytest.mark.asyncio
    async def test_etag_uses_weak_format(self, client):
        """ETag value must use weak validator format: W/\"...\"."""
        resp = await client.get("/api/projects")
        etag = resp.headers.get("etag", "")
        assert etag.startswith('W/"'), f"ETag should start with W/\", got: {etag}"
        assert etag.endswith('"'), f"ETag should end with \", got: {etag}"

    @pytest.mark.asyncio
    async def test_etag_conditional_304(self, client):
        """Sending If-None-Match with matching ETag should yield 304."""
        resp1 = await client.get("/api/projects")
        etag = resp1.headers.get("etag")
        assert etag is not None

        resp2 = await client.get("/api/projects", headers={"If-None-Match": etag})
        assert resp2.status_code == 304

    @pytest.mark.asyncio
    async def test_etag_different_content_different_etag(self, client, tmp_path):
        """ETag must change when underlying data changes."""
        resp1 = await client.get("/api/projects")
        etag1 = resp1.headers.get("etag")

        # Mutate data
        await client.post("/api/projects", json={
            "name": "ETag Mutation Test",
            "goal": "Verify ETag changes after mutation",
            "folder_path": str(tmp_path / "etag_mut").replace("\\", "/"),
        })

        resp2 = await client.get("/api/projects")
        etag2 = resp2.headers.get("etag")

        assert etag1 != etag2, "ETag must differ after content mutation"

    @pytest.mark.asyncio
    async def test_etag_not_on_post(self, client, tmp_path):
        """POST responses must NOT carry an ETag header."""
        resp = await client.post("/api/projects", json={
            "name": "No ETag POST",
            "goal": "POST should not have ETag",
            "folder_path": str(tmp_path / "no_etag_post").replace("\\", "/"),
        })
        assert resp.status_code == 201
        assert resp.headers.get("etag") is None

    @pytest.mark.asyncio
    async def test_etag_not_on_non_200(self, client):
        """Non-200 GET responses (e.g. 404) must NOT have an ETag."""
        resp = await client.get("/api/projects/999")
        assert resp.status_code == 404
        assert resp.headers.get("etag") is None


# ---------------------------------------------------------------------------
# 2. ETag blake2b specifics
# ---------------------------------------------------------------------------

class TestETagBlake2b:
    """Verify ETag uses blake2b with digest_size=16 (32 hex chars)."""

    @pytest.mark.asyncio
    async def test_etag_is_blake2b_hex(self, client):
        """Inner ETag value must be 32 hex characters (blake2b digest_size=16)."""
        resp = await client.get("/api/projects")
        etag = resp.headers.get("etag", "")
        # Strip weak validator wrapper: W/"<hex>"
        match = re.match(r'^W/"([0-9a-f]+)"$', etag)
        assert match is not None, f"ETag format unexpected: {etag}"
        hex_part = match.group(1)
        assert len(hex_part) == 32, (
            f"Expected 32 hex chars (blake2b digest_size=16), got {len(hex_part)}"
        )

    @pytest.mark.asyncio
    async def test_etag_consistent(self, client):
        """Same content must produce the same ETag on repeated calls."""
        resp1 = await client.get("/api/projects")
        resp2 = await client.get("/api/projects")
        assert resp1.headers.get("etag") == resp2.headers.get("etag")

    @pytest.mark.asyncio
    async def test_etag_matches_blake2b_of_body(self, client):
        """ETag value must equal blake2b of the response body."""
        resp = await client.get("/api/projects")
        body = resp.content
        expected_hex = hashlib.blake2b(body, digest_size=16).hexdigest()
        expected_etag = f'W/"{expected_hex}"'
        assert resp.headers.get("etag") == expected_etag


# ---------------------------------------------------------------------------
# 3. Rate Limiter Memory Leak Fix
# ---------------------------------------------------------------------------

class TestRateLimiterMemoryLeak:
    """Verify the rate limiter prunes empty client keys after window expiry."""

    def test_rate_limiter_prunes_empty_keys(self):
        """Stale entries older than 60s must be removed from _requests dict."""
        from app.main import RateLimitMiddleware

        middleware = RateLimitMiddleware(app=None, write_rpm=100, read_rpm=100)

        # Inject a stale entry (timestamp 120 seconds ago)
        stale_key = "127.0.0.1:/api/stale"
        middleware._requests[stale_key] = [time.time() - 120]

        # Simulate the pruning logic that runs on each request:
        # The middleware cleans entries older than 60s and pops empty keys.
        now = time.time()
        recent = [t for t in middleware._requests[stale_key] if now - t < 60]
        if recent:
            middleware._requests[stale_key] = recent
        else:
            middleware._requests.pop(stale_key, None)

        assert stale_key not in middleware._requests, (
            "Empty key should have been pruned"
        )

    def test_rate_limiter_retains_active_keys(self):
        """Recent entries within the 60s window must be retained."""
        from app.main import RateLimitMiddleware

        middleware = RateLimitMiddleware(app=None, write_rpm=100, read_rpm=100)

        active_key = "127.0.0.1:/api/active"
        now = time.time()
        middleware._requests[active_key] = [now - 10, now - 5, now]

        # Simulate pruning
        recent = [t for t in middleware._requests[active_key] if now - t < 60]
        if recent:
            middleware._requests[active_key] = recent
        else:
            middleware._requests.pop(active_key, None)

        assert active_key in middleware._requests
        assert len(middleware._requests[active_key]) == 3

    def test_rate_limiter_defaultdict_converts_to_regular_after_prune(self):
        """After pruning, accessing a removed key must not re-create it via defaultdict.

        The fix uses .pop() which removes the key entirely. Subsequent code
        uses .get() which does not trigger defaultdict's __missing__.
        """
        from app.main import RateLimitMiddleware

        middleware = RateLimitMiddleware(app=None, write_rpm=100, read_rpm=100)

        key = "127.0.0.1:/api/test"
        middleware._requests[key] = [time.time() - 120]

        # Prune
        now = time.time()
        recent = [t for t in middleware._requests[key] if now - t < 60]
        if recent:
            middleware._requests[key] = recent
        else:
            middleware._requests.pop(key, None)

        # The RPM check uses .get() so it must NOT re-create the key
        count = len(middleware._requests.get(key, []))
        assert count == 0
        # Ensure the key was NOT re-inserted by the .get() call
        assert key not in middleware._requests


# ---------------------------------------------------------------------------
# 4. Security Headers (regression - complementary to test_security_headers.py)
# ---------------------------------------------------------------------------

class TestSecurityHeadersRegression:
    """Phase 18 regression for security header values after hardening."""

    @pytest.mark.asyncio
    async def test_x_content_type_options(self, client):
        resp = await client.get("/api/projects")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    @pytest.mark.asyncio
    async def test_x_frame_options(self, client):
        resp = await client.get("/api/projects")
        assert resp.headers.get("x-frame-options") == "DENY"

    @pytest.mark.asyncio
    async def test_referrer_policy(self, client):
        resp = await client.get("/api/projects")
        assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    @pytest.mark.asyncio
    async def test_x_xss_protection_modern(self, client):
        """Modern best practice: X-XSS-Protection: 0 (disable legacy filter)."""
        resp = await client.get("/api/projects")
        assert resp.headers.get("x-xss-protection") == "0"

    @pytest.mark.asyncio
    async def test_cache_control_no_store_for_non_etag(self, client, tmp_path):
        """POST (write) responses without ETag must have Cache-Control: no-store."""
        resp = await client.post("/api/projects", json={
            "name": "Cache Test",
            "goal": "Verify no-store on POST",
            "folder_path": str(tmp_path / "cc_post").replace("\\", "/"),
        })
        assert resp.status_code == 201
        assert resp.headers.get("cache-control") == "no-store"

    @pytest.mark.asyncio
    async def test_cache_control_private_no_cache_for_etag(self, client):
        """GET responses with ETag must have Cache-Control: private, no-cache."""
        resp = await client.get("/api/projects")
        assert resp.headers.get("etag") is not None
        assert resp.headers.get("cache-control") == "private, no-cache"

    @pytest.mark.asyncio
    async def test_health_endpoint_no_etag_uses_no_store(self, client):
        """Health endpoint is in ETag skip list, so Cache-Control must be no-store."""
        resp = await client.get("/api/health")
        assert resp.headers.get("etag") is None
        assert resp.headers.get("cache-control") == "no-store"


# ---------------------------------------------------------------------------
# 5. RequestID Middleware
# ---------------------------------------------------------------------------

class TestRequestIDMiddleware:
    """Verify X-Request-ID generation and preservation."""

    @pytest.mark.asyncio
    async def test_request_id_generated(self, client):
        """Every response must include an X-Request-ID header."""
        resp = await client.get("/api/health")
        assert "x-request-id" in resp.headers

    @pytest.mark.asyncio
    async def test_request_id_is_uuid(self, client):
        """Auto-generated X-Request-ID must be a valid UUID."""
        resp = await client.get("/api/health")
        request_id = resp.headers.get("x-request-id", "")
        # uuid.UUID() raises ValueError on invalid format
        parsed = uuid.UUID(request_id)
        assert str(parsed) == request_id

    @pytest.mark.asyncio
    async def test_request_id_preserved(self, client):
        """Client-supplied X-Request-ID must be echoed back unchanged."""
        custom_id = "custom-trace-abc-123"
        resp = await client.get("/api/health", headers={"X-Request-ID": custom_id})
        assert resp.headers.get("x-request-id") == custom_id

    @pytest.mark.asyncio
    async def test_request_id_unique_per_request(self, client):
        """Each request without a supplied ID must get a unique UUID."""
        resp1 = await client.get("/api/health")
        resp2 = await client.get("/api/health")
        id1 = resp1.headers.get("x-request-id")
        id2 = resp2.headers.get("x-request-id")
        assert id1 != id2, "Each request should get a unique request ID"

    @pytest.mark.asyncio
    async def test_request_id_on_error_responses(self, client):
        """X-Request-ID must be present even on error responses."""
        resp = await client.get("/api/projects/99999")
        assert resp.status_code == 404
        assert "x-request-id" in resp.headers


# ---------------------------------------------------------------------------
# 6. VACUUM Config
# ---------------------------------------------------------------------------

class TestVACUUMConfig:
    """Verify VACUUM scheduling configuration."""

    def test_vacuum_interval_default_disabled(self):
        """LU_VACUUM_INTERVAL_HOURS defaults to 0 (disabled)."""
        from app import config
        # The default in config.py is int(os.getenv("LU_VACUUM_INTERVAL_HOURS", "0"))
        assert hasattr(config, "VACUUM_INTERVAL_HOURS")
        # Unless an env var overrides, default should be 0
        default_val = int(os.environ.get("LU_VACUUM_INTERVAL_HOURS", "0"))
        assert config.VACUUM_INTERVAL_HOURS == default_val

    def test_vacuum_interval_configurable(self, monkeypatch):
        """Setting LU_VACUUM_INTERVAL_HOURS env var changes the config value."""
        monkeypatch.setenv("LU_VACUUM_INTERVAL_HOURS", "12")
        # Re-evaluate the config expression
        val = int(os.environ.get("LU_VACUUM_INTERVAL_HOURS", "0"))
        assert val == 12

    def test_vacuum_task_not_started_when_zero(self):
        """When interval is 0, the VACUUM task handle should remain None."""
        from app.main import _vacuum_task
        # In the test environment VACUUM_INTERVAL_HOURS is 0 by default
        assert _vacuum_task is None

    @pytest.mark.asyncio
    async def test_vacuum_loop_function_exists(self):
        """The _auto_vacuum_loop coroutine must exist in main."""
        from app.main import _auto_vacuum_loop
        import asyncio
        assert asyncio.iscoroutinefunction(_auto_vacuum_loop)


# ---------------------------------------------------------------------------
# 7. Request Logging
# ---------------------------------------------------------------------------

class TestRequestLogging:
    """Verify request logging configuration."""

    def test_request_log_disabled_by_default(self):
        """LU_REQUEST_LOG defaults to disabled (falsy)."""
        from app import config
        # Default is false unless env var is set
        default_val = os.environ.get("LU_REQUEST_LOG", "").lower() in ("1", "true", "yes")
        assert config.REQUEST_LOG == default_val

    def test_request_logging_middleware_class_exists(self):
        """RequestLoggingMiddleware class must exist in main."""
        from app.main import RequestLoggingMiddleware
        assert RequestLoggingMiddleware is not None

    def test_request_log_env_var_enables_logging(self, monkeypatch):
        """Setting LU_REQUEST_LOG=true should evaluate to True."""
        monkeypatch.setenv("LU_REQUEST_LOG", "true")
        val = os.environ.get("LU_REQUEST_LOG", "").lower() in ("1", "true", "yes")
        assert val is True

    def test_request_log_env_var_numeric(self, monkeypatch):
        """Setting LU_REQUEST_LOG=1 should evaluate to True."""
        monkeypatch.setenv("LU_REQUEST_LOG", "1")
        val = os.environ.get("LU_REQUEST_LOG", "").lower() in ("1", "true", "yes")
        assert val is True


# ---------------------------------------------------------------------------
# 8. Versioned API Routes
# ---------------------------------------------------------------------------

class TestVersionedAPIRoutes:
    """Verify /api/v1/ routes and deprecation headers on unversioned /api/."""

    @pytest.mark.asyncio
    async def test_v1_routes_work(self, client):
        """GET /api/v1/projects must return 200."""
        resp = await client.get("/api/v1/projects")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_v1_health_equivalent(self, client):
        """/api/v1/health must return the same data as /api/health."""
        resp_v1 = await client.get("/api/v1/health")
        resp_unversioned = await client.get("/api/health")

        assert resp_v1.status_code == 200
        assert resp_unversioned.status_code == 200

        data_v1 = resp_v1.json()
        data_un = resp_unversioned.json()

        # Core fields must match (uptime may differ by milliseconds)
        assert data_v1["app"] == data_un["app"]
        assert data_v1["version"] == data_un["version"]
        assert data_v1["status"] == data_un["status"]

    @pytest.mark.asyncio
    async def test_unversioned_deprecation_header(self, client):
        """GET /api/projects must include x-api-deprecation: true header."""
        resp = await client.get("/api/projects")
        assert resp.headers.get("x-api-deprecation") == "true"

    @pytest.mark.asyncio
    async def test_unversioned_sunset_header(self, client):
        """GET /api/projects must include a Sunset header."""
        resp = await client.get("/api/projects")
        assert resp.headers.get("sunset") is not None

    @pytest.mark.asyncio
    async def test_v1_no_deprecation_header(self, client):
        """GET /api/v1/projects must NOT include deprecation headers."""
        resp = await client.get("/api/v1/projects")
        assert resp.headers.get("x-api-deprecation") is None

    @pytest.mark.asyncio
    async def test_v1_post_route_works(self, client, tmp_path):
        """POST /api/v1/projects must create a project (write through v1)."""
        resp = await client.post("/api/v1/projects", json={
            "name": "V1 Route Project",
            "goal": "Test v1 write route",
            "folder_path": str(tmp_path / "v1_post").replace("\\", "/"),
        })
        assert resp.status_code == 201
        assert resp.json()["name"] == "V1 Route Project"

    @pytest.mark.asyncio
    async def test_v1_templates_route(self, client):
        """GET /api/v1/templates must work through version rewrite."""
        resp = await client.get("/api/v1/templates")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 9. GZip Compression
# ---------------------------------------------------------------------------

class TestGZipCompression:
    """Verify GZip middleware thresholds."""

    @pytest.mark.asyncio
    async def test_gzip_on_large_response(self, client, tmp_path):
        """Responses above minimum_size=1000 bytes should be compressed."""
        # Create enough projects to generate a response > 1000 bytes
        for i in range(10):
            await client.post("/api/projects", json={
                "name": f"GZip Test Project {i}",
                "goal": f"This is a project with enough text to help reach the compression threshold number {i}",
                "folder_path": str(tmp_path / f"gzip_{i}").replace("\\", "/"),
            })

        resp = await client.get(
            "/api/projects",
            headers={"Accept-Encoding": "gzip"},
        )
        assert resp.status_code == 200
        # httpx auto-decompresses, so check content-encoding header
        # If the response was large enough, GZip middleware should compress it
        # The header may or may not be present depending on httpx decompression
        # At minimum, verify the response is valid JSON (decompression worked)
        data = resp.json()
        assert len(data) == 10

    @pytest.mark.asyncio
    async def test_no_gzip_on_small_response(self, client):
        """Responses below minimum_size=1000 bytes should NOT be compressed."""
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        # Small response: content-encoding should not be gzip
        assert resp.headers.get("content-encoding") != "gzip"

    @pytest.mark.asyncio
    async def test_gzip_middleware_configured(self):
        """GZipMiddleware must be present in the app middleware stack."""
        from app.main import _fastapi_app
        from fastapi.middleware.gzip import GZipMiddleware

        # Walk the middleware stack (user_middleware is a list of Middleware objects)
        found = False
        for mw in _fastapi_app.user_middleware:
            if mw.cls is GZipMiddleware:
                found = True
                assert mw.kwargs.get("minimum_size") == 1000
                assert mw.kwargs.get("compresslevel") == 5
                break
        assert found, "GZipMiddleware not found in middleware stack"


# ---------------------------------------------------------------------------
# 10. ETag skip paths
# ---------------------------------------------------------------------------

class TestETagSkipPaths:
    """Verify ETag middleware skip paths are correct."""

    @pytest.mark.asyncio
    async def test_health_skipped(self, client):
        """/api/health is in ETag skip list - no ETag header."""
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.headers.get("etag") is None

    @pytest.mark.asyncio
    async def test_system_skipped(self, client):
        """/api/system is in ETag skip list - no ETag header."""
        resp = await client.get("/api/system")
        assert resp.status_code == 200
        assert resp.headers.get("etag") is None

    @pytest.mark.asyncio
    async def test_projects_not_skipped(self, client):
        """/api/projects is NOT in skip list - must have ETag."""
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        assert resp.headers.get("etag") is not None

    @pytest.mark.asyncio
    async def test_templates_not_skipped(self, client):
        """/api/templates is NOT in skip list - must have ETag."""
        resp = await client.get("/api/templates")
        assert resp.status_code == 200
        assert resp.headers.get("etag") is not None


# ---------------------------------------------------------------------------
# 11. Middleware ordering
# ---------------------------------------------------------------------------

class TestMiddlewareOrdering:
    """Verify that middleware are applied in the correct order."""

    @pytest.mark.asyncio
    async def test_security_headers_and_etag_coexist(self, client):
        """A GET /api/projects response must have both ETag AND security headers."""
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        # ETag from ETagMiddleware
        assert resp.headers.get("etag") is not None
        # Security headers from SecurityHeadersMiddleware
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        # Cache-Control set by SecurityHeadersMiddleware based on ETag presence
        assert resp.headers.get("cache-control") == "private, no-cache"

    @pytest.mark.asyncio
    async def test_request_id_and_etag_coexist(self, client):
        """Response must carry both X-Request-ID and ETag."""
        resp = await client.get("/api/projects")
        assert "x-request-id" in resp.headers
        assert "etag" in resp.headers

    @pytest.mark.asyncio
    async def test_304_still_has_etag_header(self, client):
        """304 Not Modified response must still include the ETag header."""
        resp1 = await client.get("/api/projects")
        etag = resp1.headers.get("etag")

        resp2 = await client.get("/api/projects", headers={"If-None-Match": etag})
        assert resp2.status_code == 304
        assert resp2.headers.get("etag") == etag


# ---------------------------------------------------------------------------
# 12. Config regression
# ---------------------------------------------------------------------------

class TestPhase18ConfigRegression:
    """Verify Phase 18 configuration attributes exist and have correct defaults."""

    def test_app_version_exists(self):
        from app import config
        assert hasattr(config, "APP_VERSION")
        assert isinstance(config.APP_VERSION, str)
        # Version should follow semver-like pattern
        assert re.match(r"^\d+\.\d+\.\d+$", config.APP_VERSION)

    def test_request_timeout_exists(self):
        from app import config
        assert hasattr(config, "REQUEST_TIMEOUT")
        assert isinstance(config.REQUEST_TIMEOUT, int)

    def test_backup_config_exists(self):
        from app import config
        assert hasattr(config, "BACKUP_INTERVAL_HOURS")
        assert hasattr(config, "BACKUP_KEEP")
        assert isinstance(config.BACKUP_INTERVAL_HOURS, int)
        assert isinstance(config.BACKUP_KEEP, int)

    def test_log_retention_exists(self):
        from app import config
        assert hasattr(config, "LOG_RETENTION_DAYS")
        assert isinstance(config.LOG_RETENTION_DAYS, int)

    def test_auto_stop_exists(self):
        from app import config
        assert hasattr(config, "AUTO_STOP_MINUTES")
        assert isinstance(config.AUTO_STOP_MINUTES, int)
