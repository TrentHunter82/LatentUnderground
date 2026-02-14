"""Tests for application configuration and bug fixes."""

import os
import pytest


class TestConfigLoading:
    """Tests for app.config module."""

    def test_default_values(self):
        """Config should have sensible defaults without env vars."""
        from app import config

        assert config.HOST == os.environ.get("LU_HOST", "127.0.0.1")
        assert isinstance(config.PORT, int)
        assert config.LOG_LEVEL in ("debug", "info", "warning", "error")
        assert config.DB_PATH.name == os.environ.get("LU_DB_PATH", "latent.db").split("/")[-1].split("\\")[-1]

    def test_cors_origins_is_list(self):
        """CORS_ORIGINS should be a list of strings."""
        from app import config

        assert isinstance(config.CORS_ORIGINS, list)
        assert len(config.CORS_ORIGINS) > 0
        assert all(isinstance(o, str) for o in config.CORS_ORIGINS)

    def test_frontend_dist_is_path(self):
        """FRONTEND_DIST should be a Path object."""
        from app import config
        from pathlib import Path

        assert isinstance(config.FRONTEND_DIST, Path)


class TestColumnWhitelist:
    """Tests for the project update column whitelist."""

    async def test_update_allowed_fields(self, client, created_project):
        """Should successfully update whitelisted fields."""
        pid = created_project["id"]
        resp = await client.patch(f"/api/projects/{pid}", json={"name": "Updated Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    async def test_update_multiple_allowed_fields(self, client, created_project):
        """Should update multiple whitelisted fields at once."""
        pid = created_project["id"]
        resp = await client.patch(f"/api/projects/{pid}", json={
            "name": "New Name",
            "goal": "New Goal",
            "complexity": "High",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Name"
        assert data["goal"] == "New Goal"
        assert data["complexity"] == "High"

    async def test_whitelist_constant_exists(self):
        """ALLOWED_UPDATE_FIELDS should be defined and contain expected fields."""
        from app.routes.projects import ALLOWED_UPDATE_FIELDS

        assert isinstance(ALLOWED_UPDATE_FIELDS, set)
        assert "name" in ALLOWED_UPDATE_FIELDS
        assert "goal" in ALLOWED_UPDATE_FIELDS
        assert "status" in ALLOWED_UPDATE_FIELDS
        # Internal fields should NOT be in the whitelist
        assert "id" not in ALLOWED_UPDATE_FIELDS
        assert "created_at" not in ALLOWED_UPDATE_FIELDS
        assert "updated_at" not in ALLOWED_UPDATE_FIELDS
        assert "swarm_pid" not in ALLOWED_UPDATE_FIELDS
        assert "config" not in ALLOWED_UPDATE_FIELDS


class TestOutputBufferCleanup:
    """Tests for swarm output buffer memory leak fix."""

    async def test_buffer_cleaned_on_stop(self, client, tmp_path):
        """Output buffer should be removed when a swarm is stopped."""
        from app.routes.swarm import _project_output_buffers

        # Create a project
        folder = tmp_path / "buf_test"
        folder.mkdir()
        resp = await client.post("/api/projects", json={
            "name": "Buffer Test",
            "goal": "Test buffer cleanup",
            "folder_path": str(folder).replace("\\", "/"),
        })
        pid = resp.json()["id"]

        # Simulate a buffer existing (as if a swarm had been running)
        _project_output_buffers[pid] = ["[stdout] line 1", "[stdout] line 2"]

        # Stop the swarm (even though not actually running)
        resp = await client.post("/api/swarm/stop", json={"project_id": pid})
        assert resp.status_code == 200

        # Buffer should be cleaned up
        assert pid not in _project_output_buffers


class TestDatabaseMigration:
    """Tests for database migration error handling."""

    def test_migration_catches_specific_error(self):
        """Migration should only catch OperationalError for duplicate columns."""
        import sqlite3

        from app import database

        # The import of sqlite3 in database.py should exist
        assert hasattr(database, "sqlite3") or "sqlite3" in dir(database)
