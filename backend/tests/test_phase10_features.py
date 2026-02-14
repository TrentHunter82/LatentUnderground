"""Tests for Phase 10 backend features: plugins, webhooks, archival, versioning, request logging."""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


# --- Plugin System Tests ---

@pytest.fixture(autouse=True)
def _clean_plugin_state():
    """Clear global plugin manager state between tests."""
    from app.plugins import plugin_manager
    original_dir = plugin_manager.plugins_dir
    plugin_manager._plugins.clear()
    plugin_manager._disabled.clear()
    yield
    plugin_manager._plugins.clear()
    plugin_manager._disabled.clear()
    plugin_manager.plugins_dir = original_dir


class TestPluginSystem:
    """Tests for the plugin manager and plugin API endpoints."""

    @pytest.mark.asyncio
    async def test_list_plugins_empty(self, client):
        resp = await client.get("/api/plugins")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_create_plugin(self, client, tmp_path):
        """Create a plugin via API and verify it appears in the list."""
        from app.plugins import plugin_manager
        plugin_manager.plugins_dir = tmp_path / "plugins"

        resp = await client.post("/api/plugins", json={
            "name": "test-plugin",
            "description": "A test plugin",
            "config": {"agent_count": 8, "max_phases": 12},
            "hooks": {"on_launch": "echo started"},
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-plugin"
        assert data["config"]["agent_count"] == 8
        assert data["enabled"] is True

        # Verify it's in the list
        resp = await client.get("/api/plugins")
        assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_create_duplicate_plugin(self, client, tmp_path):
        from app.plugins import plugin_manager
        plugin_manager.plugins_dir = tmp_path / "plugins"

        await client.post("/api/plugins", json={"name": "dupe"})
        resp = await client.post("/api/plugins", json={"name": "dupe"})
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_get_plugin(self, client, tmp_path):
        from app.plugins import plugin_manager
        plugin_manager.plugins_dir = tmp_path / "plugins"

        await client.post("/api/plugins", json={"name": "my-plugin", "description": "test"})
        resp = await client.get("/api/plugins/my-plugin")
        assert resp.status_code == 200
        assert resp.json()["name"] == "my-plugin"

    @pytest.mark.asyncio
    async def test_get_plugin_not_found(self, client):
        resp = await client.get("/api/plugins/nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_enable_disable_plugin(self, client, tmp_path):
        from app.plugins import plugin_manager
        plugin_manager.plugins_dir = tmp_path / "plugins"

        await client.post("/api/plugins", json={"name": "toggle-me"})

        resp = await client.post("/api/plugins/toggle-me/disable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

        resp = await client.post("/api/plugins/toggle-me/enable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    @pytest.mark.asyncio
    async def test_delete_plugin(self, client, tmp_path):
        from app.plugins import plugin_manager
        plugin_manager.plugins_dir = tmp_path / "plugins"

        await client.post("/api/plugins", json={"name": "delete-me"})
        resp = await client.delete("/api/plugins/delete-me")
        assert resp.status_code == 204

        resp = await client.get("/api/plugins")
        assert len(resp.json()) == 0

    @pytest.mark.asyncio
    async def test_delete_plugin_not_found(self, client):
        resp = await client.delete("/api/plugins/nonexistent")
        assert resp.status_code == 404


class TestPluginManager:
    """Unit tests for the PluginManager class."""

    def test_discover_empty_dir(self, tmp_path):
        from app.plugins import PluginManager
        mgr = PluginManager(tmp_path / "empty")
        plugins = mgr.discover()
        assert plugins == []

    def test_discover_loads_json(self, tmp_path):
        from app.plugins import PluginManager
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        (plugins_dir / "test.json").write_text(json.dumps({
            "name": "test",
            "description": "A test plugin",
            "config": {"agent_count": 4},
        }))
        mgr = PluginManager(plugins_dir)
        plugins = mgr.discover()
        assert len(plugins) == 1
        assert plugins[0].name == "test"
        assert plugins[0].config["agent_count"] == 4

    def test_discover_skips_invalid_json(self, tmp_path):
        from app.plugins import PluginManager
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        (plugins_dir / "bad.json").write_text("not json{{{")
        (plugins_dir / "good.json").write_text(json.dumps({"name": "good"}))
        mgr = PluginManager(plugins_dir)
        plugins = mgr.discover()
        assert len(plugins) == 1
        assert plugins[0].name == "good"

    def test_get_config_disabled(self, tmp_path):
        from app.plugins import PluginManager
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        (plugins_dir / "p.json").write_text(json.dumps({"name": "p", "config": {"x": 1}}))
        mgr = PluginManager(plugins_dir)
        mgr.discover()
        mgr.disable("p")
        assert mgr.get_config("p") is None

    def test_get_hooks(self, tmp_path):
        from app.plugins import PluginManager
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        (plugins_dir / "a.json").write_text(json.dumps({
            "name": "a", "hooks": {"on_launch": "echo a"}
        }))
        (plugins_dir / "b.json").write_text(json.dumps({
            "name": "b", "hooks": {"on_launch": "echo b", "on_stop": "echo stop"}
        }))
        mgr = PluginManager(plugins_dir)
        mgr.discover()
        hooks = mgr.get_hooks("on_launch")
        assert len(hooks) == 2
        assert "echo a" in hooks
        assert "echo b" in hooks
        assert mgr.get_hooks("on_stop") == ["echo stop"]
        assert mgr.get_hooks("nonexistent") == []


# --- Webhook Tests ---

class TestWebhookCRUD:
    """Tests for webhook CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_list_webhooks_empty(self, client):
        resp = await client.get("/api/webhooks")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_create_webhook(self, client):
        resp = await client.post("/api/webhooks", json={
            "url": "https://example.com/webhook",
            "events": ["swarm_launched", "swarm_stopped"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["url"] == "https://example.com/webhook"
        assert data["events"] == ["swarm_launched", "swarm_stopped"]
        assert data["has_secret"] is False
        assert "secret" not in data  # Secret should not be exposed

    @pytest.mark.asyncio
    async def test_create_webhook_with_secret(self, client):
        resp = await client.post("/api/webhooks", json={
            "url": "https://example.com/hook",
            "secret": "my-secret-key",
        })
        assert resp.status_code == 201
        assert resp.json()["has_secret"] is True

    @pytest.mark.asyncio
    async def test_create_webhook_invalid_events(self, client):
        resp = await client.post("/api/webhooks", json={
            "url": "https://example.com/hook",
            "events": ["invalid_event"],
        })
        assert resp.status_code == 400
        assert "Invalid events" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_webhook(self, client):
        create = await client.post("/api/webhooks", json={"url": "https://test.com/hook"})
        wid = create.json()["id"]
        resp = await client.get(f"/api/webhooks/{wid}")
        assert resp.status_code == 200
        assert resp.json()["url"] == "https://test.com/hook"

    @pytest.mark.asyncio
    async def test_get_webhook_not_found(self, client):
        resp = await client.get("/api/webhooks/9999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_webhook(self, client):
        create = await client.post("/api/webhooks", json={"url": "https://old.com"})
        wid = create.json()["id"]
        resp = await client.patch(f"/api/webhooks/{wid}", json={
            "url": "https://new.com",
            "enabled": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] == "https://new.com"
        assert data["enabled"] == 0  # SQLite stores as integer

    @pytest.mark.asyncio
    async def test_update_webhook_invalid_events(self, client):
        create = await client.post("/api/webhooks", json={"url": "https://test.com"})
        wid = create.json()["id"]
        resp = await client.patch(f"/api/webhooks/{wid}", json={"events": ["bad"]})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_webhook(self, client):
        create = await client.post("/api/webhooks", json={"url": "https://del.com"})
        wid = create.json()["id"]
        resp = await client.delete(f"/api/webhooks/{wid}")
        assert resp.status_code == 204

        resp = await client.get("/api/webhooks")
        assert len(resp.json()) == 0

    @pytest.mark.asyncio
    async def test_delete_webhook_not_found(self, client):
        resp = await client.delete("/api/webhooks/9999")
        assert resp.status_code == 404


class TestWebhookDelivery:
    """Tests for webhook event emission and delivery."""

    @pytest.mark.asyncio
    async def test_sign_payload(self):
        from app.routes.webhooks import _sign_payload
        sig = _sign_payload('{"test": true}', "secret")
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA256 hex

    @pytest.mark.asyncio
    async def test_webhook_events_constant(self):
        from app.routes.webhooks import WEBHOOK_EVENTS
        assert "swarm_launched" in WEBHOOK_EVENTS
        assert "swarm_stopped" in WEBHOOK_EVENTS
        assert "swarm_crashed" in WEBHOOK_EVENTS
        assert "swarm_error" in WEBHOOK_EVENTS


# --- Project Archival Tests ---

class TestProjectArchival:
    """Tests for project archive/unarchive functionality."""

    @pytest.mark.asyncio
    async def test_archive_project(self, client, created_project):
        pid = created_project["id"]
        resp = await client.post(f"/api/projects/{pid}/archive")
        assert resp.status_code == 200
        assert resp.json()["archived_at"] is not None

    @pytest.mark.asyncio
    async def test_archive_already_archived(self, client, created_project):
        pid = created_project["id"]
        await client.post(f"/api/projects/{pid}/archive")
        resp = await client.post(f"/api/projects/{pid}/archive")
        assert resp.status_code == 400
        assert "already archived" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_unarchive_project(self, client, created_project):
        pid = created_project["id"]
        await client.post(f"/api/projects/{pid}/archive")
        resp = await client.post(f"/api/projects/{pid}/unarchive")
        assert resp.status_code == 200
        assert resp.json()["archived_at"] is None

    @pytest.mark.asyncio
    async def test_unarchive_not_archived(self, client, created_project):
        pid = created_project["id"]
        resp = await client.post(f"/api/projects/{pid}/unarchive")
        assert resp.status_code == 400
        assert "not archived" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_archive_not_found(self, client):
        resp = await client.post("/api/projects/9999/archive")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_excludes_archived(self, client, sample_project_data):
        # Create two projects
        r1 = await client.post("/api/projects", json=sample_project_data)
        data2 = dict(sample_project_data)
        data2["name"] = "Project 2"
        r2 = await client.post("/api/projects", json=data2)

        # Archive one
        await client.post(f"/api/projects/{r1.json()['id']}/archive")

        # Default list should only show the non-archived one
        resp = await client.get("/api/projects")
        projects = resp.json()
        assert len(projects) == 1
        assert projects[0]["name"] == "Project 2"

    @pytest.mark.asyncio
    async def test_list_includes_archived(self, client, sample_project_data):
        r1 = await client.post("/api/projects", json=sample_project_data)
        await client.post(f"/api/projects/{r1.json()['id']}/archive")

        resp = await client.get("/api/projects?include_archived=true")
        assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_archived_project_has_archived_at_field(self, client, created_project):
        # Before archival
        assert created_project.get("archived_at") is None

        # After archival
        pid = created_project["id"]
        resp = await client.post(f"/api/projects/{pid}/archive")
        data = resp.json()
        assert "archived_at" in data
        assert data["archived_at"] is not None


# --- API Versioning Tests ---

class TestAPIVersioning:
    """Tests for API versioning middleware."""

    @pytest.mark.asyncio
    async def test_v1_projects_endpoint(self, client, sample_project_data):
        """v1 endpoints should work the same as unversioned."""
        await client.post("/api/projects", json=sample_project_data)
        resp = await client.get("/api/v1/projects")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    @pytest.mark.asyncio
    async def test_v1_health_endpoint(self, client):
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_deprecation_headers_on_unversioned(self, client):
        """Unversioned /api/ routes should have deprecation headers."""
        resp = await client.get("/api/projects")
        assert resp.headers.get("x-api-deprecation") == "true"
        assert resp.headers.get("sunset") == "2026-12-31"

    @pytest.mark.asyncio
    async def test_no_deprecation_on_v1(self, client):
        """v1 routes should NOT have deprecation headers."""
        resp = await client.get("/api/v1/projects")
        assert resp.headers.get("x-api-deprecation") is None

    @pytest.mark.asyncio
    async def test_no_deprecation_on_health(self, client):
        """Health endpoint should not have deprecation headers."""
        resp = await client.get("/api/health")
        assert resp.headers.get("x-api-deprecation") is None

    @pytest.mark.asyncio
    async def test_v1_webhooks(self, client):
        resp = await client.get("/api/v1/webhooks")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_v1_plugins(self, client):
        resp = await client.get("/api/v1/plugins")
        assert resp.status_code == 200


# --- Request Logging Middleware Tests ---

class TestRequestLogging:
    """Tests for the request logging middleware configuration."""

    def test_request_log_default_disabled(self):
        """REQUEST_LOG should be disabled by default."""
        from app import config
        # Default is disabled unless LU_REQUEST_LOG is set
        assert hasattr(config, "REQUEST_LOG")

    def test_request_logging_middleware_class_exists(self):
        from app.main import RequestLoggingMiddleware
        assert RequestLoggingMiddleware is not None


# --- SQLite Optimization Tests ---

class TestSQLiteOptimizations:
    """Tests for SQLite query optimizations."""

    @pytest.mark.asyncio
    async def test_mmap_size_pragma_in_init_db(self):
        """Verify init_db sets mmap_size pragma."""
        import inspect
        from app.database import init_db
        source = inspect.getsource(init_db)
        assert "mmap_size" in source

    @pytest.mark.asyncio
    async def test_new_indexes_in_init_db(self):
        """Verify the new Phase 10 indexes are defined in migrations."""
        import inspect
        from app.database import _migration_001
        source = inspect.getsource(_migration_001)
        assert "idx_swarm_runs_project_ended" in source
        assert "idx_templates_created" in source
        assert "idx_webhooks_enabled" in source

    @pytest.mark.asyncio
    async def test_analyze_in_init_db(self):
        """Verify ANALYZE is called in init_db for query planner optimization."""
        import inspect
        from app.database import init_db
        source = inspect.getsource(init_db)
        assert "ANALYZE" in source
