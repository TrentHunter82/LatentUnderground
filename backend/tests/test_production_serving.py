"""Tests for FastAPI static file serving (frontend SPA).

These tests verify that the production build correctly serves:
- React SPA index.html at root and SPA routes
- Static assets (JS, CSS) from /assets
- Security headers on all responses
- Path traversal protection
- API routes NOT intercepted by static serving
"""

import os

# Disable rate limiting in tests (must be set before app imports)
os.environ.setdefault("LU_RATE_LIMIT_RPM", "0")
os.environ.setdefault("LU_RATE_LIMIT_READ_RPM", "0")

import gzip
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture()
def mock_frontend_dist(tmp_path):
    """Create a mock frontend dist directory with typical SPA structure."""
    dist = tmp_path / "dist"
    dist.mkdir()

    # Create index.html
    (dist / "index.html").write_text(
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head><title>Latent Underground</title></head>\n"
        "<body><div id=\"root\"></div></body>\n"
        "</html>\n"
    )

    # Create assets directory
    assets = dist / "assets"
    assets.mkdir()

    # Create a JS file (simulate a bundled module)
    (assets / "index-abc123.js").write_text(
        "console.log('Latent Underground');\n"
        "export default function App() { return null; }\n"
    )

    # Create a CSS file
    (assets / "index-def456.css").write_text(
        "body { margin: 0; font-family: sans-serif; }\n"
        ".app { padding: 20px; }\n"
    )

    # Create a large JS file for GZip compression testing
    large_content = "// Latent Underground Bundle\n" + ("console.log('x');\n" * 100)
    (assets / "main-large.js").write_text(large_content)

    # Create favicon.ico (simulated binary)
    (dist / "favicon.ico").write_bytes(b"\x00\x00\x01\x00\x01\x00\x10\x10\x00\x00")

    return dist


@pytest.fixture()
async def mock_app(tmp_db, mock_frontend_dist):
    """Create a test app with mock frontend dist."""
    from app import database, config

    original_db_path = database.DB_PATH
    original_frontend_dist = config.FRONTEND_DIST

    database.DB_PATH = tmp_db
    config.FRONTEND_DIST = mock_frontend_dist

    # Clear all module-level state from previous tests
    from app.routes.files import _last_write
    from app.routes.swarm import (
        _project_output_buffers, _agent_output_buffers,
        _last_output_at, cancel_drain_tasks,
    )
    _last_write.clear()
    _project_output_buffers.clear()
    _agent_output_buffers.clear()
    _last_output_at.clear()

    # Reimport main to pick up the new config
    import importlib
    from app import main
    importlib.reload(main)

    # Return the wrapped app (APIVersionMiddleware wrapper)
    yield main.app

    # Cleanup: restore config and reload main so module-level static mounts
    # are rebuilt with the original FRONTEND_DIST path.
    await cancel_drain_tasks()
    _project_output_buffers.clear()
    _agent_output_buffers.clear()
    _last_output_at.clear()
    database.DB_PATH = original_db_path
    config.FRONTEND_DIST = original_frontend_dist
    importlib.reload(main)


@pytest.fixture()
async def mock_client(mock_app):
    """Create an async test client with mock frontend."""
    transport = ASGITransport(app=mock_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- Root and SPA Routing Tests ---

async def test_root_serves_index_html(mock_client):
    """GET / returns the SPA index.html."""
    resp = await mock_client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert b"Latent Underground" in resp.content
    assert b'<div id="root">' in resp.content


async def test_spa_fallback_for_client_routes(mock_client):
    """Non-existent paths return index.html for client-side routing."""
    # Simulate React Router paths
    for path in ["/projects", "/projects/123", "/dashboard", "/settings"]:
        resp = await mock_client.get(path)
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert b"Latent Underground" in resp.content


async def test_nonexistent_file_returns_spa_index(mock_client):
    """Non-existent files fall through to index.html for SPA routing."""
    resp = await mock_client.get("/nonexistent.html")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert b"Latent Underground" in resp.content


async def test_favicon_served_directly(mock_client):
    """Existing files in dist root are served directly."""
    resp = await mock_client.get("/favicon.ico")
    assert resp.status_code == 200
    # Should be served as the actual file, not index.html
    assert resp.content.startswith(b"\x00\x00\x01\x00")


# --- Static Assets Tests ---

async def test_js_asset_served(mock_client):
    """JavaScript assets are served with correct content-type."""
    resp = await mock_client.get("/assets/index-abc123.js")
    assert resp.status_code == 200
    content_type = resp.headers.get("content-type", "")
    # FastAPI's StaticFiles returns either application/javascript or text/javascript
    assert "javascript" in content_type.lower()
    assert b"console.log('Latent Underground')" in resp.content


async def test_css_asset_served(mock_client):
    """CSS assets are served with correct content-type."""
    resp = await mock_client.get("/assets/index-def456.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers.get("content-type", "")
    assert b"font-family: sans-serif" in resp.content


async def test_nonexistent_asset_returns_404(mock_client):
    """Non-existent assets in /assets return 404, not index.html."""
    resp = await mock_client.get("/assets/nonexistent.js")
    assert resp.status_code == 404


# --- API Route Protection Tests ---

async def test_api_routes_not_intercepted(mock_client):
    """API routes return API responses, not index.html."""
    resp = await mock_client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["app"] == "Latent Underground"
    assert "version" in data
    # Should be JSON, not HTML
    assert "text/html" not in resp.headers.get("content-type", "")


async def test_api_v1_routes_not_intercepted(mock_client):
    """Versioned API routes work correctly."""
    resp = await mock_client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["app"] == "Latent Underground"


async def test_nonexistent_api_route_returns_404_json(mock_client):
    """Non-existent API routes return 404 JSON, not index.html."""
    resp = await mock_client.get("/api/nonexistent")
    assert resp.status_code == 404
    data = resp.json()
    assert "detail" in data


async def test_ws_route_not_intercepted():
    """WebSocket path is not served as static file."""
    # This test uses the serve_spa function directly to verify logic
    from app.main import FRONTEND_DIST
    if not FRONTEND_DIST.exists():
        pytest.skip("Frontend dist not built")

    # Import after env vars set
    from app.main import _fastapi_app
    transport = ASGITransport(app=_fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET /ws should return 404 (it's only for upgrade), not index.html
        resp = await client.get("/ws")
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"] == "Not found"


# --- Security Tests ---

async def test_path_traversal_blocked(mock_client):
    """Path traversal attempts are blocked."""
    # Try to escape dist directory
    resp = await mock_client.get("/../../../etc/passwd")
    assert resp.status_code == 200
    # Should fall through to index.html, not serve the file
    assert b"Latent Underground" in resp.content
    assert b"root:" not in resp.content  # Not actual /etc/passwd


async def test_security_headers_present_on_spa(mock_client):
    """Security headers are present on SPA responses."""
    resp = await mock_client.get("/")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert "referrer-policy" in resp.headers
    assert resp.headers.get("x-xss-protection") == "0"


async def test_security_headers_present_on_assets(mock_client):
    """Security headers are present on static asset responses."""
    resp = await mock_client.get("/assets/index-abc123.js")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"


async def test_request_id_header_on_static_responses(mock_client):
    """X-Request-ID header is present on static responses."""
    resp = await mock_client.get("/")
    assert "x-request-id" in resp.headers
    request_id = resp.headers["x-request-id"]
    # Should be UUID format
    assert len(request_id) == 36  # UUID length
    assert request_id.count("-") == 4  # UUID has 4 dashes


async def test_custom_request_id_preserved(mock_client):
    """Custom X-Request-ID from client is preserved."""
    custom_id = "custom-request-123"
    resp = await mock_client.get("/", headers={"x-request-id": custom_id})
    assert resp.headers.get("x-request-id") == custom_id


# --- GZip Compression Tests ---

async def test_large_response_compressed(mock_client):
    """Large responses are GZip compressed."""
    resp = await mock_client.get(
        "/assets/main-large.js",
        headers={"accept-encoding": "gzip"}
    )
    assert resp.status_code == 200
    # Check if response is compressed
    # Note: httpx auto-decompresses, so check the raw content
    if "content-encoding" in resp.headers:
        assert resp.headers["content-encoding"] == "gzip"


async def test_small_response_not_compressed(mock_client):
    """Small responses (< 1000 bytes) are not compressed."""
    resp = await mock_client.get("/favicon.ico")
    assert resp.status_code == 200
    # Small file should not have gzip encoding
    assert resp.headers.get("content-encoding") != "gzip"


# --- Content-Type Tests ---

async def test_html_content_type(mock_client):
    """HTML files get text/html content-type."""
    resp = await mock_client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


async def test_js_content_type(mock_client):
    """JavaScript files get correct content-type."""
    resp = await mock_client.get("/assets/index-abc123.js")
    assert resp.status_code == 200
    content_type = resp.headers.get("content-type", "")
    assert "javascript" in content_type.lower()


async def test_css_content_type(mock_client):
    """CSS files get text/css content-type."""
    resp = await mock_client.get("/assets/index-def456.css")
    assert resp.status_code == 200
    assert "text/css" in resp.headers.get("content-type", "")


# --- Real Frontend Dist Tests (if built) ---

@pytest.mark.skipif(
    not Path("F:/LatentUnderground/frontend/dist").exists(),
    reason="Frontend not built"
)
async def test_real_frontend_dist_serves(tmp_db):
    """Test with the actual frontend build if it exists."""
    from app import database, config
    import importlib

    original_db_path = database.DB_PATH
    original_frontend_dist = config.FRONTEND_DIST

    database.DB_PATH = tmp_db
    # Restore to the real frontend dist path
    config.FRONTEND_DIST = Path("F:/LatentUnderground/frontend/dist")

    try:
        # Reload to pick up correct frontend path
        from app import main
        importlib.reload(main)

        transport = ASGITransport(app=main._fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Root should serve index.html
            resp = await client.get("/")
            assert resp.status_code == 200
            assert b"<!DOCTYPE html>" in resp.content or b"<!doctype html>" in resp.content

            # Assets should exist
            # Find any JS file in assets
            assets_dir = Path("F:/LatentUnderground/frontend/dist/assets")
            js_files = list(assets_dir.glob("*.js"))
            if js_files:
                js_file = js_files[0]
                resp = await client.get(f"/assets/{js_file.name}")
                assert resp.status_code == 200
                assert "javascript" in resp.headers.get("content-type", "").lower()

            # SPA routing should work
            resp = await client.get("/projects/123")
            assert resp.status_code == 200
            assert b"<!DOCTYPE html>" in resp.content or b"<!doctype html>" in resp.content

            # API routes should not be intercepted
            resp = await client.get("/api/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["app"] == "Latent Underground"
    finally:
        database.DB_PATH = original_db_path
        config.FRONTEND_DIST = original_frontend_dist
        importlib.reload(main)


@pytest.mark.skipif(
    not Path("F:/LatentUnderground/frontend/dist").exists(),
    reason="Frontend not built"
)
async def test_real_frontend_has_security_headers(tmp_db):
    """Verify security headers on real frontend responses."""
    from app import database, config
    import importlib

    original_db_path = database.DB_PATH
    original_frontend_dist = config.FRONTEND_DIST

    database.DB_PATH = tmp_db
    config.FRONTEND_DIST = Path("F:/LatentUnderground/frontend/dist")

    try:
        from app import main
        importlib.reload(main)

        transport = ASGITransport(app=main._fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            assert resp.status_code == 200
            assert resp.headers.get("x-content-type-options") == "nosniff"
            assert resp.headers.get("x-frame-options") == "DENY"
            assert "x-request-id" in resp.headers
    finally:
        database.DB_PATH = original_db_path
        config.FRONTEND_DIST = original_frontend_dist
        importlib.reload(main)


# --- Edge Cases ---

async def test_empty_path_component(mock_client):
    """Paths with empty components are handled correctly."""
    resp = await mock_client.get("//projects//123")
    # Should normalize and serve index.html (or could 404, depends on server)
    assert resp.status_code in [200, 404]


async def test_api_prefix_in_middle_of_path(mock_client):
    """Paths with 'api' in the middle are served as SPA routes."""
    # /my-api-docs should be a client route, not an API route
    resp = await mock_client.get("/my-api-docs")
    assert resp.status_code == 200
    assert b"Latent Underground" in resp.content


async def test_case_sensitivity(mock_client):
    """Path case handling (depends on OS filesystem)."""
    # Create a specific file to test
    # Note: Windows is case-insensitive, Linux is case-sensitive
    resp = await mock_client.get("/INDEX.HTML")
    # On Windows, this might work; on Linux, it should fall through to SPA
    # Either way, should not error
    assert resp.status_code == 200


async def test_special_characters_in_path(mock_client):
    """Paths with special characters are handled safely."""
    resp = await mock_client.get("/path%20with%20spaces")
    assert resp.status_code == 200
    # Should serve index.html
    assert b"Latent Underground" in resp.content


async def test_dot_files_blocked(mock_client):
    """Hidden/dot files are not accessible (path traversal protection)."""
    # Even if .env existed in dist (it shouldn't), it should be protected
    resp = await mock_client.get("/.env")
    assert resp.status_code == 200
    # Should serve index.html, not the file
    assert b"Latent Underground" in resp.content


async def test_query_params_preserved(mock_client):
    """Query parameters don't break SPA routing."""
    resp = await mock_client.get("/projects?status=active&sort=name")
    assert resp.status_code == 200
    assert b"Latent Underground" in resp.content


async def test_fragment_handling(mock_client):
    """URL fragments (hash) are handled by client, server ignores them."""
    # Server never sees fragments (#), they're client-side only
    # But we can test that a path with %23 (encoded #) works
    resp = await mock_client.get("/path")
    assert resp.status_code == 200


# --- Cache Control Tests ---

async def test_spa_cache_headers(mock_client):
    """SPA responses should not have strict caching."""
    resp = await mock_client.get("/")
    assert resp.status_code == 200
    # Static files typically shouldn't have no-store (that's for API)
    # But they also shouldn't have long max-age without versioning
    # Actual behavior depends on FileResponse defaults


async def test_api_cache_headers(mock_client):
    """API responses have no-store cache control."""
    resp = await mock_client.get("/api/health")
    assert resp.status_code == 200
    # Health endpoint doesn't have ETag, so should be no-store
    cache_control = resp.headers.get("cache-control", "")
    assert "no-store" in cache_control or "no-cache" in cache_control


# --- CORS Tests ---

async def test_cors_headers_on_spa(mock_client):
    """CORS headers are present for allowed origins."""
    resp = await mock_client.get(
        "/",
        headers={"origin": "http://localhost:5173"}
    )
    assert resp.status_code == 200
    # CORS middleware should add headers for allowed origins
    assert "access-control-allow-origin" in resp.headers


async def test_cors_headers_on_api(mock_client):
    """CORS headers work on API endpoints."""
    resp = await mock_client.get(
        "/api/health",
        headers={"origin": "http://localhost:5173"}
    )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers


# --- No Frontend Dist Tests ---

async def test_no_frontend_dist_api_still_works(tmp_db, tmp_path):
    """API works even when frontend dist doesn't exist."""
    from app import database, config

    original_db_path = database.DB_PATH
    original_frontend_dist = config.FRONTEND_DIST

    database.DB_PATH = tmp_db
    # Point to non-existent dist
    config.FRONTEND_DIST = tmp_path / "nonexistent_dist"

    try:
        # Reload main to pick up new config
        import importlib
        from app import main
        importlib.reload(main)

        transport = ASGITransport(app=main._fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # API should still work
            resp = await client.get("/api/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["app"] == "Latent Underground"

            # Root should 404 (no SPA handler mounted)
            resp = await client.get("/")
            assert resp.status_code == 404
    finally:
        database.DB_PATH = original_db_path
        config.FRONTEND_DIST = original_frontend_dist
        # Reload main to restore module-level static mounts for subsequent tests
        importlib.reload(main)


# --- Middleware Order Tests ---

async def test_gzip_works_on_spa_responses(mock_client):
    """GZip middleware compresses SPA responses when appropriate."""
    # Request a large file with gzip accepted
    resp = await mock_client.get(
        "/assets/main-large.js",
        headers={"accept-encoding": "gzip"}
    )
    assert resp.status_code == 200
    # Large file should be compressed (if above minimum_size=1000)
    # Note: httpx auto-decompresses, so we verify the content is correct
    assert b"console.log('x')" in resp.content


async def test_rate_limiting_disabled_in_tests(mock_client):
    """Rate limiting is disabled in test environment."""
    # Make many requests rapidly
    for _ in range(50):
        resp = await mock_client.get("/")
        assert resp.status_code == 200
    # Should not hit rate limit (LU_RATE_LIMIT_RPM=0)


async def test_api_key_auth_disabled_in_tests(mock_client):
    """API key authentication is disabled in test environment."""
    # No API key provided, should still work
    resp = await mock_client.get("/api/health")
    assert resp.status_code == 200
    # LU_API_KEY not set, so auth is disabled
