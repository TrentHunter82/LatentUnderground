"""Plugin system for loading custom swarm configs and extending behavior.

Plugins are JSON files in the plugins directory (configurable via LU_PLUGINS_DIR).
Each plugin file defines a swarm configuration that can be applied to projects.

Plugin JSON format:
{
    "name": "my-plugin",
    "description": "What this plugin does",
    "version": "1.0.0",
    "config": {
        "agent_count": 4,
        "max_phases": 12,
        "custom_prompts": "..."
    },
    "hooks": {
        "on_launch": "echo 'Swarm started'",
        "on_stop": "echo 'Swarm stopped'"
    }
}
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config

logger = logging.getLogger("latent.plugins")

# Default plugins directory
PLUGINS_DIR = Path(config._BACKEND_DIR / "plugins")


@dataclass
class Plugin:
    """A loaded plugin with its metadata and configuration."""
    name: str
    description: str = ""
    version: str = "1.0.0"
    config: dict[str, Any] = field(default_factory=dict)
    hooks: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    source_path: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "config": self.config,
            "hooks": self.hooks,
            "enabled": self.enabled,
            "source_path": self.source_path,
        }


class PluginManager:
    """Discovers, loads, and manages plugins from the plugins directory."""

    def __init__(self, plugins_dir: Path | None = None):
        self.plugins_dir = plugins_dir or PLUGINS_DIR
        self._plugins: dict[str, Plugin] = {}
        self._disabled: set[str] = set()

    @property
    def plugins(self) -> dict[str, Plugin]:
        return dict(self._plugins)

    def discover(self) -> list[Plugin]:
        """Scan the plugins directory for JSON plugin files and load them."""
        self._plugins.clear()
        if not self.plugins_dir.exists():
            logger.debug("Plugins directory %s does not exist, skipping", self.plugins_dir)
            return []

        loaded = []
        for path in sorted(self.plugins_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                plugin = Plugin(
                    name=data.get("name", path.stem),
                    description=data.get("description", ""),
                    version=data.get("version", "1.0.0"),
                    config=data.get("config", {}),
                    hooks=data.get("hooks", {}),
                    enabled=data.get("name", path.stem) not in self._disabled,
                    source_path=str(path),
                )
                self._plugins[plugin.name] = plugin
                loaded.append(plugin)
                logger.info("Loaded plugin: %s v%s from %s", plugin.name, plugin.version, path.name)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to load plugin %s: %s", path.name, e)
            except OSError as e:
                logger.warning("Failed to read plugin %s: %s", path.name, e)

        logger.info("Discovered %d plugin(s) in %s", len(loaded), self.plugins_dir)
        return loaded

    def get(self, name: str) -> Plugin | None:
        """Get a plugin by name."""
        return self._plugins.get(name)

    def list_plugins(self) -> list[Plugin]:
        """List all loaded plugins."""
        return list(self._plugins.values())

    def enable(self, name: str) -> bool:
        """Enable a plugin by name. Returns True if found."""
        plugin = self._plugins.get(name)
        if not plugin:
            return False
        plugin.enabled = True
        self._disabled.discard(name)
        logger.info("Enabled plugin: %s", name)
        return True

    def disable(self, name: str) -> bool:
        """Disable a plugin by name. Returns True if found."""
        plugin = self._plugins.get(name)
        if not plugin:
            return False
        plugin.enabled = False
        self._disabled.add(name)
        logger.info("Disabled plugin: %s", name)
        return True

    def get_config(self, name: str) -> dict[str, Any] | None:
        """Get the swarm config from a plugin. Returns None if not found or disabled."""
        plugin = self._plugins.get(name)
        if not plugin or not plugin.enabled:
            return None
        return plugin.config

    def get_hooks(self, event: str) -> list[str]:
        """Get all hook commands for a given event from enabled plugins."""
        hooks = []
        for plugin in self._plugins.values():
            if plugin.enabled and event in plugin.hooks:
                hooks.append(plugin.hooks[event])
        return hooks

    def create_plugin(self, name: str, description: str = "", config: dict | None = None,
                      hooks: dict | None = None) -> Plugin:
        """Create a new plugin JSON file in the plugins directory."""
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        plugin_data = {
            "name": name,
            "description": description,
            "version": "1.0.0",
            "config": config or {},
            "hooks": hooks or {},
        }
        path = self.plugins_dir / f"{name}.json"
        path.write_text(json.dumps(plugin_data, indent=2), encoding="utf-8")
        plugin = Plugin(
            name=name, description=description, config=config or {},
            hooks=hooks or {}, source_path=str(path),
        )
        self._plugins[name] = plugin
        logger.info("Created plugin: %s at %s", name, path)
        return plugin

    def delete_plugin(self, name: str) -> bool:
        """Delete a plugin file and remove from registry. Returns True if found."""
        plugin = self._plugins.pop(name, None)
        if not plugin:
            return False
        self._disabled.discard(name)
        try:
            path = Path(plugin.source_path)
            if path.exists():
                path.unlink()
                logger.info("Deleted plugin file: %s", path)
        except OSError as e:
            logger.warning("Failed to delete plugin file: %s", e)
        return True


# Global plugin manager instance
plugin_manager = PluginManager()
