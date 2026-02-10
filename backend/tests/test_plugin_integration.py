"""Deep integration tests for the plugin system.

Tests filesystem discovery edge cases, schema validation, config application,
hooks aggregation, and full lifecycle via the API. Complements the basic CRUD
coverage in test_phase10_features.py.
"""

import json

import pytest

from app.plugins import Plugin, PluginManager


# ---------------------------------------------------------------------------
# TestPluginFilesystemDiscovery
# ---------------------------------------------------------------------------

class TestPluginFilesystemDiscovery:
    """Verify that PluginManager.discover() correctly walks the plugins dir."""

    def test_discover_loads_valid_json_files(self, tmp_path):
        """Create 2 JSON plugin files, discover, verify both loaded with correct fields."""
        (tmp_path / "alpha.json").write_text(json.dumps({
            "name": "alpha",
            "description": "First plugin",
            "version": "2.0.0",
            "config": {"agent_count": 4},
            "hooks": {"on_launch": "echo alpha"},
        }), encoding="utf-8")
        (tmp_path / "beta.json").write_text(json.dumps({
            "name": "beta",
            "description": "Second plugin",
            "version": "0.5.0",
            "config": {"max_phases": 8},
            "hooks": {"on_stop": "echo bye"},
        }), encoding="utf-8")

        mgr = PluginManager(plugins_dir=tmp_path)
        loaded = mgr.discover()

        assert len(loaded) == 2
        names = {p.name for p in loaded}
        assert names == {"alpha", "beta"}

        alpha = mgr.get("alpha")
        assert alpha is not None
        assert alpha.description == "First plugin"
        assert alpha.version == "2.0.0"
        assert alpha.config == {"agent_count": 4}
        assert alpha.hooks == {"on_launch": "echo alpha"}
        assert alpha.enabled is True
        assert alpha.source_path.endswith("alpha.json")

        beta = mgr.get("beta")
        assert beta is not None
        assert beta.config == {"max_phases": 8}

    def test_discover_skips_non_json_files(self, tmp_path):
        """A .txt file alongside a .json file -- only JSON should be loaded."""
        (tmp_path / "readme.txt").write_text("not a plugin")
        (tmp_path / "legit.json").write_text(json.dumps({
            "name": "legit",
            "description": "The only real plugin",
        }), encoding="utf-8")
        (tmp_path / "notes.md").write_text("# Notes")
        (tmp_path / "data.yaml").write_text("key: value")

        mgr = PluginManager(plugins_dir=tmp_path)
        loaded = mgr.discover()

        assert len(loaded) == 1
        assert loaded[0].name == "legit"

    def test_discover_handles_unicode_content(self, tmp_path):
        """Plugin with unicode description and config values loads correctly."""
        (tmp_path / "intl.json").write_text(json.dumps({
            "name": "intl-plugin",
            "description": "Plage-in mit Umlauten: Gruesse an alle \u00fc\u00f6\u00e4",
            "version": "1.0.0",
            "config": {"greeting": "\u3053\u3093\u306b\u3061\u306f\u4e16\u754c", "emoji_key": "\u2764\ufe0f\u2728"},
            "hooks": {"on_launch": "echo '\u00a1Hola Mundo!'"},
        }), encoding="utf-8")

        mgr = PluginManager(plugins_dir=tmp_path)
        loaded = mgr.discover()

        assert len(loaded) == 1
        p = loaded[0]
        assert p.name == "intl-plugin"
        assert "\u00fc\u00f6\u00e4" in p.description
        assert p.config["greeting"] == "\u3053\u3093\u306b\u3061\u306f\u4e16\u754c"
        assert p.hooks["on_launch"] == "echo '\u00a1Hola Mundo!'"

    def test_discover_sorted_by_filename(self, tmp_path):
        """Files named b.json and a.json should be returned with a first (sorted glob)."""
        (tmp_path / "b-plugin.json").write_text(json.dumps({
            "name": "bravo",
            "description": "B plugin",
        }), encoding="utf-8")
        (tmp_path / "a-plugin.json").write_text(json.dumps({
            "name": "alpha",
            "description": "A plugin",
        }), encoding="utf-8")

        mgr = PluginManager(plugins_dir=tmp_path)
        loaded = mgr.discover()

        assert len(loaded) == 2
        assert loaded[0].name == "alpha"
        assert loaded[1].name == "bravo"


# ---------------------------------------------------------------------------
# TestPluginSchemaValidation
# ---------------------------------------------------------------------------

class TestPluginSchemaValidation:
    """Verify resilience against malformed or incomplete plugin files."""

    def test_malformed_json_file_skipped(self, tmp_path):
        """Broken JSON should not crash discover and should return 0 plugins."""
        (tmp_path / "broken.json").write_text("{name: invalid, ]]]", encoding="utf-8")

        mgr = PluginManager(plugins_dir=tmp_path)
        loaded = mgr.discover()

        assert len(loaded) == 0
        assert mgr.list_plugins() == []

    def test_missing_name_uses_filename_stem(self, tmp_path):
        """JSON without a 'name' field should use the filename stem as the name."""
        (tmp_path / "my-cool-plugin.json").write_text(json.dumps({
            "description": "No name field here",
            "config": {"x": 1},
        }), encoding="utf-8")

        mgr = PluginManager(plugins_dir=tmp_path)
        loaded = mgr.discover()

        assert len(loaded) == 1
        assert loaded[0].name == "my-cool-plugin"
        assert mgr.get("my-cool-plugin") is not None

    def test_empty_config_and_hooks_default(self, tmp_path):
        """JSON with only a name should get empty dicts for config and hooks."""
        (tmp_path / "minimal.json").write_text(json.dumps({
            "name": "minimal",
        }), encoding="utf-8")

        mgr = PluginManager(plugins_dir=tmp_path)
        loaded = mgr.discover()

        assert len(loaded) == 1
        p = loaded[0]
        assert p.name == "minimal"
        assert p.config == {}
        assert p.hooks == {}
        assert p.description == ""
        assert p.version == "1.0.0"

    def test_extra_fields_ignored(self, tmp_path):
        """JSON with extra unexpected fields should still load the plugin normally."""
        (tmp_path / "extras.json").write_text(json.dumps({
            "name": "extras",
            "description": "Plugin with extra stuff",
            "version": "3.0.0",
            "config": {"key": "val"},
            "hooks": {"on_launch": "echo go"},
            "author": "Test Author",
            "license": "MIT",
            "tags": ["experimental", "beta"],
            "homepage": "https://example.com",
        }), encoding="utf-8")

        mgr = PluginManager(plugins_dir=tmp_path)
        loaded = mgr.discover()

        assert len(loaded) == 1
        p = loaded[0]
        assert p.name == "extras"
        assert p.description == "Plugin with extra stuff"
        assert p.version == "3.0.0"
        assert p.config == {"key": "val"}
        assert p.hooks == {"on_launch": "echo go"}
        assert p.enabled is True


# ---------------------------------------------------------------------------
# TestPluginConfigApplication
# ---------------------------------------------------------------------------

class TestPluginConfigApplication:
    """Verify that get_config returns the right data based on plugin state."""

    def test_get_config_returns_correct_overrides(self, tmp_path):
        """Create plugin with agent_count/max_phases config, get_config returns it."""
        (tmp_path / "overrides.json").write_text(json.dumps({
            "name": "overrides",
            "config": {"agent_count": 6, "max_phases": 18, "custom_prompts": "be thorough"},
        }), encoding="utf-8")

        mgr = PluginManager(plugins_dir=tmp_path)
        mgr.discover()

        cfg = mgr.get_config("overrides")
        assert cfg is not None
        assert cfg["agent_count"] == 6
        assert cfg["max_phases"] == 18
        assert cfg["custom_prompts"] == "be thorough"

    def test_get_config_returns_none_for_disabled(self, tmp_path):
        """Disabling a plugin should make get_config return None."""
        (tmp_path / "toggle.json").write_text(json.dumps({
            "name": "toggle",
            "config": {"agent_count": 2},
        }), encoding="utf-8")

        mgr = PluginManager(plugins_dir=tmp_path)
        mgr.discover()

        # Initially enabled
        assert mgr.get_config("toggle") == {"agent_count": 2}

        # Disable
        mgr.disable("toggle")
        assert mgr.get_config("toggle") is None

        # Re-enable
        mgr.enable("toggle")
        assert mgr.get_config("toggle") == {"agent_count": 2}

    def test_get_config_returns_none_for_unknown(self, tmp_path):
        """get_config for a nonexistent plugin name returns None."""
        mgr = PluginManager(plugins_dir=tmp_path)
        assert mgr.get_config("does-not-exist") is None


# ---------------------------------------------------------------------------
# TestPluginHooksAggregation
# ---------------------------------------------------------------------------

class TestPluginHooksAggregation:
    """Verify that get_hooks aggregates hook commands across enabled plugins."""

    def test_get_hooks_aggregates_across_enabled_plugins(self, tmp_path):
        """Two plugins both providing on_launch hooks -- both should be returned."""
        (tmp_path / "hook-a.json").write_text(json.dumps({
            "name": "hook-a",
            "hooks": {"on_launch": "echo starting hook-a"},
        }), encoding="utf-8")
        (tmp_path / "hook-b.json").write_text(json.dumps({
            "name": "hook-b",
            "hooks": {"on_launch": "echo starting hook-b", "on_stop": "echo cleanup"},
        }), encoding="utf-8")

        mgr = PluginManager(plugins_dir=tmp_path)
        mgr.discover()

        launch_hooks = mgr.get_hooks("on_launch")
        assert len(launch_hooks) == 2
        assert "echo starting hook-a" in launch_hooks
        assert "echo starting hook-b" in launch_hooks

    def test_get_hooks_excludes_disabled_plugins(self, tmp_path):
        """Two plugins with on_launch hooks; disable one -- only enabled hook returned."""
        (tmp_path / "enabled.json").write_text(json.dumps({
            "name": "enabled",
            "hooks": {"on_launch": "echo enabled-hook"},
        }), encoding="utf-8")
        (tmp_path / "to-disable.json").write_text(json.dumps({
            "name": "to-disable",
            "hooks": {"on_launch": "echo disabled-hook"},
        }), encoding="utf-8")

        mgr = PluginManager(plugins_dir=tmp_path)
        mgr.discover()
        mgr.disable("to-disable")

        launch_hooks = mgr.get_hooks("on_launch")
        assert len(launch_hooks) == 1
        assert launch_hooks[0] == "echo enabled-hook"

    def test_get_hooks_returns_empty_for_unknown_event(self, tmp_path):
        """Requesting hooks for a nonexistent event returns an empty list."""
        (tmp_path / "some-plugin.json").write_text(json.dumps({
            "name": "some-plugin",
            "hooks": {"on_launch": "echo hi"},
        }), encoding="utf-8")

        mgr = PluginManager(plugins_dir=tmp_path)
        mgr.discover()

        assert mgr.get_hooks("on_explode") == []
        assert mgr.get_hooks("") == []
        assert mgr.get_hooks("on_launch_typo") == []


# ---------------------------------------------------------------------------
# TestPluginLifecycle
# ---------------------------------------------------------------------------

class TestPluginLifecycle:
    """End-to-end lifecycle test via the HTTP API."""

    @pytest.fixture(autouse=True)
    def _clean_global_plugin_state(self):
        """Clear global plugin manager state before and after each test."""
        from app.plugins import plugin_manager
        original_dir = plugin_manager.plugins_dir
        plugin_manager._plugins.clear()
        plugin_manager._disabled.clear()
        yield
        plugin_manager._plugins.clear()
        plugin_manager._disabled.clear()
        plugin_manager.plugins_dir = original_dir

    @pytest.mark.asyncio
    async def test_full_lifecycle_create_enable_config_disable_delete(self, client, tmp_path):
        """Full lifecycle: create via API, enable, get config, disable, verify config None, delete, verify gone."""
        from app.plugins import plugin_manager
        plugin_manager.plugins_dir = tmp_path / "plugins"

        # 1. Create plugin via API
        resp = await client.post("/api/plugins", json={
            "name": "lifecycle-test",
            "description": "Full lifecycle plugin",
            "config": {"agent_count": 3, "max_phases": 10},
            "hooks": {"on_launch": "echo lifecycle-start", "on_stop": "echo lifecycle-end"},
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "lifecycle-test"
        assert data["enabled"] is True
        assert data["config"]["agent_count"] == 3

        # 2. Verify it appears in list
        resp = await client.get("/api/plugins")
        assert resp.status_code == 200
        plugins = resp.json()
        assert len(plugins) == 1
        assert plugins[0]["name"] == "lifecycle-test"

        # 3. Verify get_config returns correct data while enabled
        cfg = plugin_manager.get_config("lifecycle-test")
        assert cfg is not None
        assert cfg["agent_count"] == 3
        assert cfg["max_phases"] == 10

        # 4. Verify hooks are available
        launch_hooks = plugin_manager.get_hooks("on_launch")
        assert "echo lifecycle-start" in launch_hooks

        # 5. Disable via API
        resp = await client.post("/api/plugins/lifecycle-test/disable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

        # 6. Verify config returns None when disabled
        assert plugin_manager.get_config("lifecycle-test") is None

        # 7. Verify hooks excluded when disabled
        assert plugin_manager.get_hooks("on_launch") == []

        # 8. Re-enable
        resp = await client.post("/api/plugins/lifecycle-test/enable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True
        assert plugin_manager.get_config("lifecycle-test") == {"agent_count": 3, "max_phases": 10}

        # 9. Delete via API
        resp = await client.delete("/api/plugins/lifecycle-test")
        assert resp.status_code == 204

        # 10. Verify gone from list
        resp = await client.get("/api/plugins")
        assert resp.json() == []

        # 11. Verify get returns 404
        resp = await client.get("/api/plugins/lifecycle-test")
        assert resp.status_code == 404

        # 12. Verify JSON file was removed from disk
        plugin_file = tmp_path / "plugins" / "lifecycle-test.json"
        assert not plugin_file.exists()
