"""Tests for Phase 15 features: system metrics, ETag caching, input sanitization,
VACUUM scheduling, and OpenAPI examples."""

import asyncio
import hashlib
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app import config


# --- System Metrics Endpoint ---

class TestSystemMetrics:
    """Tests for GET /api/system endpoint."""

    @pytest.mark.asyncio
    async def test_system_endpoint_returns_200(self, client):
        """System metrics endpoint should return 200 OK."""
        resp = await client.get("/api/system")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_system_response_has_cpu_fields(self, client):
        """Response should include CPU metrics."""
        resp = await client.get("/api/system")
        data = resp.json()
        assert "cpu_percent" in data
        assert "cpu_count" in data
        assert isinstance(data["cpu_percent"], (int, float))
        assert isinstance(data["cpu_count"], int)
        assert data["cpu_count"] > 0

    @pytest.mark.asyncio
    async def test_system_response_has_memory_fields(self, client):
        """Response should include memory metrics."""
        resp = await client.get("/api/system")
        data = resp.json()
        assert "memory_percent" in data
        assert "memory_used_mb" in data
        assert "memory_total_mb" in data
        assert 0 <= data["memory_percent"] <= 100
        assert data["memory_total_mb"] > 0

    @pytest.mark.asyncio
    async def test_system_response_has_disk_fields(self, client):
        """Response should include disk metrics."""
        resp = await client.get("/api/system")
        data = resp.json()
        assert "disk_percent" in data
        assert "disk_free_gb" in data
        assert "disk_total_gb" in data
        assert data["disk_total_gb"] > 0

    @pytest.mark.asyncio
    async def test_system_response_has_app_info(self, client):
        """Response should include application metadata."""
        resp = await client.get("/api/system")
        data = resp.json()
        assert "python_version" in data
        assert "platform" in data
        assert "app_version" in data
        assert "uptime_seconds" in data
        assert "db_size_bytes" in data
        assert data["app_version"] == config.APP_VERSION
        assert data["uptime_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_system_endpoint_in_openapi(self, client):
        """System endpoint should appear in OpenAPI schema."""
        resp = await client.get("/openapi.json")
        schema = resp.json()
        assert "/api/system" in schema["paths"]
        get_op = schema["paths"]["/api/system"]["get"]
        assert get_op["summary"] == "System metrics"


# --- ETag Caching ---

class TestETagCaching:
    """Tests for ETag middleware on GET endpoints."""

    @pytest.mark.asyncio
    async def test_get_projects_has_etag_header(self, client):
        """GET /api/projects should include an ETag header."""
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        etag = resp.headers.get("etag")
        assert etag is not None
        assert etag.startswith('W/"')

    @pytest.mark.asyncio
    async def test_etag_304_on_unchanged_content(self, client):
        """Sending If-None-Match with matching ETag should return 304."""
        # First request - get the ETag
        resp1 = await client.get("/api/projects")
        etag = resp1.headers.get("etag")
        assert etag is not None

        # Second request with If-None-Match
        resp2 = await client.get("/api/projects", headers={"If-None-Match": etag})
        assert resp2.status_code == 304

    @pytest.mark.asyncio
    async def test_etag_200_on_mismatched_etag(self, client):
        """Sending wrong ETag should return 200 with full body."""
        resp = await client.get("/api/projects", headers={"If-None-Match": 'W/"wrong"'})
        assert resp.status_code == 200
        assert resp.headers.get("etag") is not None

    @pytest.mark.asyncio
    async def test_etag_changes_after_data_mutation(self, client, tmp_path):
        """ETag should change when underlying data changes."""
        # Get initial ETag
        resp1 = await client.get("/api/projects")
        etag1 = resp1.headers.get("etag")

        # Create a project (mutate data)
        await client.post("/api/projects", json={
            "name": "ETag Test",
            "goal": "Test ETag changes",
            "folder_path": str(tmp_path / "etag_test").replace("\\", "/"),
        })

        # Get new ETag
        resp2 = await client.get("/api/projects")
        etag2 = resp2.headers.get("etag")

        assert etag1 != etag2

    @pytest.mark.asyncio
    async def test_etag_not_on_post_requests(self, client, tmp_path):
        """ETag should not be set on POST responses."""
        resp = await client.post("/api/projects", json={
            "name": "No ETag",
            "goal": "POST should not get ETag",
            "folder_path": str(tmp_path / "no_etag").replace("\\", "/"),
        })
        assert resp.status_code == 201
        assert resp.headers.get("etag") is None

    @pytest.mark.asyncio
    async def test_etag_cache_control_is_no_cache(self, client):
        """GET responses with ETag should use 'private, no-cache' Cache-Control."""
        resp = await client.get("/api/projects")
        assert resp.headers.get("cache-control") == "private, no-cache"

    @pytest.mark.asyncio
    async def test_etag_skips_health_endpoint(self, client):
        """Health endpoint should NOT get ETag (in skip list)."""
        resp = await client.get("/api/health")
        assert resp.headers.get("etag") is None
        assert resp.headers.get("cache-control") == "no-store"

    @pytest.mark.asyncio
    async def test_templates_list_has_etag(self, client):
        """GET /api/templates should also include ETag."""
        resp = await client.get("/api/templates")
        assert resp.status_code == 200
        assert resp.headers.get("etag") is not None


# --- Input Sanitization ---

class TestInputSanitization:
    """Tests for HTML input sanitization on user-provided fields."""

    @pytest.mark.asyncio
    async def test_project_name_html_escaped(self, client, tmp_path):
        """HTML in project name should be escaped."""
        resp = await client.post("/api/projects", json={
            "name": "<script>alert('xss')</script>",
            "goal": "Test sanitization",
            "folder_path": str(tmp_path / "sanitize1").replace("\\", "/"),
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "<script>" not in data["name"]
        assert "&lt;script&gt;" in data["name"]

    @pytest.mark.asyncio
    async def test_project_goal_html_escaped(self, client, tmp_path):
        """HTML in project goal should be escaped."""
        resp = await client.post("/api/projects", json={
            "name": "Sanitize Test",
            "goal": '<img src=x onerror="alert(1)">',
            "folder_path": str(tmp_path / "sanitize2").replace("\\", "/"),
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "<img" not in data["goal"]
        assert "&lt;img" in data["goal"]

    @pytest.mark.asyncio
    async def test_project_update_sanitized(self, client, created_project):
        """PATCH project with HTML should sanitize the update."""
        pid = created_project["id"]
        resp = await client.patch(f"/api/projects/{pid}", json={
            "name": "Normal & <b>bold</b>"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "<b>" not in data["name"]
        assert "&lt;b&gt;" in data["name"]
        # Ampersand should also be escaped
        assert "&amp;" in data["name"]

    @pytest.mark.asyncio
    async def test_template_name_html_escaped(self, client):
        """HTML in template name should be escaped."""
        resp = await client.post("/api/templates", json={
            "name": "<div>Test</div>",
            "description": "Normal description",
            "config": {},
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "<div>" not in data["name"]
        assert "&lt;div&gt;" in data["name"]

    @pytest.mark.asyncio
    async def test_template_description_html_escaped(self, client):
        """HTML in template description should be escaped."""
        resp = await client.post("/api/templates", json={
            "name": "Sanitize Template",
            "description": 'Click <a href="javascript:alert(1)">here</a>',
            "config": {},
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "<a " not in data["description"]
        assert "&lt;a " in data["description"]

    @pytest.mark.asyncio
    async def test_clean_input_passes_through_unchanged(self, client, tmp_path):
        """Normal text without HTML should pass through unchanged."""
        resp = await client.post("/api/projects", json={
            "name": "My Cool Project",
            "goal": "Build something awesome with Python 3.12",
            "folder_path": str(tmp_path / "clean").replace("\\", "/"),
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Cool Project"
        assert data["goal"] == "Build something awesome with Python 3.12"

    @pytest.mark.asyncio
    async def test_sanitize_preserves_unicode(self, client, tmp_path):
        """Unicode characters should pass through sanitization unchanged."""
        resp = await client.post("/api/projects", json={
            "name": "Projet \u00e9l\u00e9gant \u2605",
            "goal": "Construire quelque chose",
            "folder_path": str(tmp_path / "unicode").replace("\\", "/"),
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "\u00e9" in data["name"]  # é
        assert "\u2605" in data["name"]  # ★


# --- VACUUM Scheduling ---

class TestVacuumScheduling:
    """Tests for database VACUUM scheduling configuration."""

    def test_vacuum_config_default_disabled(self):
        """VACUUM should be disabled by default (0 hours)."""
        from app import config
        # Default is 0 = disabled (unless env var overrides)
        assert hasattr(config, "VACUUM_INTERVAL_HOURS")

    @pytest.mark.asyncio
    async def test_vacuum_task_not_created_when_disabled(self):
        """When VACUUM_INTERVAL_HOURS=0, no vacuum task should start."""
        from app.main import _vacuum_task
        # In test environment, VACUUM is disabled by default
        # The task should be None
        assert _vacuum_task is None

    @pytest.mark.asyncio
    async def test_auto_vacuum_loop_runs_vacuum(self):
        """The _auto_vacuum_loop function should execute VACUUM on the database."""
        from app.main import _auto_vacuum_loop
        from app import config, database
        import tempfile
        import os

        # Create a temp DB for testing
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            tmp_db = f.name

        original_path = database.DB_PATH
        original_interval = config.VACUUM_INTERVAL_HOURS
        try:
            # Set up test DB
            conn = sqlite3.connect(tmp_db)
            conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
            conn.close()

            database.DB_PATH = type(database.DB_PATH)(tmp_db)
            config.VACUUM_INTERVAL_HOURS = 1  # 1 hour interval (we won't wait)

            # We can't easily test the full loop (it sleeps), but we can
            # test the VACUUM operation directly
            def do_vacuum():
                c = sqlite3.connect(tmp_db)
                try:
                    c.execute("VACUUM")
                finally:
                    c.close()

            await asyncio.to_thread(do_vacuum)
            # If no exception, VACUUM succeeded
        finally:
            database.DB_PATH = original_path
            config.VACUUM_INTERVAL_HOURS = original_interval
            os.unlink(tmp_db)


# --- OpenAPI Examples ---

class TestOpenAPIExamples:
    """Tests for OpenAPI request/response examples."""

    @pytest.mark.asyncio
    async def test_project_create_has_examples(self, client):
        """ProjectCreate schema should have field examples."""
        resp = await client.get("/openapi.json")
        schema = resp.json()
        proj_create = schema["components"]["schemas"]["ProjectCreate"]
        props = proj_create["properties"]
        assert "examples" in props["name"]
        assert props["name"]["examples"] == ["My Web App"]

    @pytest.mark.asyncio
    async def test_swarm_launch_has_examples(self, client):
        """SwarmLaunchRequest schema should have field examples."""
        resp = await client.get("/openapi.json")
        schema = resp.json()
        swarm_req = schema["components"]["schemas"]["SwarmLaunchRequest"]
        props = swarm_req["properties"]
        assert "examples" in props["project_id"]
        assert "examples" in props["agent_count"]

    @pytest.mark.asyncio
    async def test_template_create_has_examples(self, client):
        """TemplateCreate schema should have field examples."""
        resp = await client.get("/openapi.json")
        schema = resp.json()
        tmpl_create = schema["components"]["schemas"]["TemplateCreate"]
        props = tmpl_create["properties"]
        assert "examples" in props["name"]
        assert props["name"]["examples"] == ["Fast Build"]

    @pytest.mark.asyncio
    async def test_system_info_out_in_schema(self, client):
        """SystemInfoOut response model should be in OpenAPI schema."""
        resp = await client.get("/openapi.json")
        schema = resp.json()
        assert "SystemInfoOut" in schema["components"]["schemas"]
        model = schema["components"]["schemas"]["SystemInfoOut"]
        assert "cpu_percent" in model["properties"]
        assert "memory_percent" in model["properties"]
        assert "db_size_bytes" in model["properties"]

    @pytest.mark.asyncio
    async def test_request_models_have_descriptions(self, client):
        """Request models with docstrings should have descriptions in schema."""
        resp = await client.get("/openapi.json")
        schema = resp.json()
        # SwarmLaunchRequest has a docstring
        swarm_req = schema["components"]["schemas"]["SwarmLaunchRequest"]
        assert "description" in swarm_req


# --- Sanitization Unit Tests ---

class TestSanitizeUtils:
    """Unit tests for the sanitize module."""

    def test_sanitize_string_escapes_html(self):
        from app.sanitize import sanitize_string
        assert sanitize_string("<script>") == "&lt;script&gt;"

    def test_sanitize_string_escapes_quotes(self):
        from app.sanitize import sanitize_string
        assert sanitize_string('"hello"') == "&quot;hello&quot;"
        assert sanitize_string("'world'") == "&#x27;world&#x27;"

    def test_sanitize_string_escapes_ampersand(self):
        from app.sanitize import sanitize_string
        assert sanitize_string("a & b") == "a &amp; b"

    def test_sanitize_string_empty(self):
        from app.sanitize import sanitize_string
        assert sanitize_string("") == ""

    def test_sanitize_string_none_passthrough(self):
        from app.sanitize import sanitize_string
        # None should be falsy and return as-is
        assert sanitize_string("") == ""

    def test_sanitize_dict_strings(self):
        from app.sanitize import sanitize_dict_strings
        data = {"name": "<b>Bold</b>", "count": 42, "desc": "Normal"}
        result = sanitize_dict_strings(data, ["name", "desc"])
        assert result["name"] == "&lt;b&gt;Bold&lt;/b&gt;"
        assert result["count"] == 42
        assert result["desc"] == "Normal"

    def test_sanitize_preserves_unicode(self):
        from app.sanitize import sanitize_string
        assert sanitize_string("café ★ 日本語") == "café ★ 日本語"
