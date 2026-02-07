"""Tests for edge cases: validation, rate limiting, stale PID, path traversal."""

import time
import pytest
from unittest.mock import patch


class TestFolderPathValidation:
    """Test that folder_path must be an absolute path."""

    async def test_relative_path_rejected(self, client):
        resp = await client.post("/api/projects", json={
            "name": "Bad Path",
            "goal": "Test validation",
            "folder_path": "relative/path/here",
        })
        assert resp.status_code == 400
        assert "absolute" in resp.json()["detail"].lower()

    async def test_dot_relative_path_rejected(self, client):
        resp = await client.post("/api/projects", json={
            "name": "Dot Path",
            "goal": "Test dots",
            "folder_path": "./local/folder",
        })
        assert resp.status_code == 400

    async def test_absolute_path_accepted(self, client, tmp_path):
        resp = await client.post("/api/projects", json={
            "name": "Absolute Path",
            "goal": "Test absolute",
            "folder_path": str(tmp_path).replace("\\", "/"),
        })
        assert resp.status_code == 201


class TestRateLimiting:
    """Test file write rate limiting (429 Too Many Requests)."""

    async def test_rapid_writes_rate_limited(self, client, project_with_folder):
        """Writing to the same file twice within cooldown should return 429."""
        pid = project_with_folder["id"]

        # First write should succeed
        resp = await client.put(
            "/api/files/tasks/TASKS.md",
            json={"content": "# First write\n", "project_id": pid},
        )
        assert resp.status_code == 200

        # Immediate second write should be rate-limited
        resp = await client.put(
            "/api/files/tasks/TASKS.md",
            json={"content": "# Second write\n", "project_id": pid},
        )
        assert resp.status_code == 429
        assert "Too many writes" in resp.json()["detail"]

    async def test_different_files_not_rate_limited(self, client, project_with_folder):
        """Writing to different files should not trigger rate limiting."""
        pid = project_with_folder["id"]

        resp = await client.put(
            "/api/files/tasks/TASKS.md",
            json={"content": "# Tasks\n", "project_id": pid},
        )
        assert resp.status_code == 200

        # Different file should not be rate-limited
        resp = await client.put(
            "/api/files/tasks/lessons.md",
            json={"content": "# Lessons\n", "project_id": pid},
        )
        assert resp.status_code == 200


class TestStalePidAutoCorrection:
    """Test that swarm status auto-corrects stale 'running' status when PID is dead."""

    async def test_stale_pid_auto_corrects(self, client, project_with_folder):
        """If project status is 'running' but PID is dead, status should auto-correct to 'stopped'."""
        pid = project_with_folder["id"]

        # Manually set project to 'running' with a fake dead PID
        from app import database
        import aiosqlite
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(
                "UPDATE projects SET status = 'running', swarm_pid = 99999 WHERE id = ?",
                (pid,),
            )
            await db.commit()

        # Status check should auto-correct
        resp = await client.get(f"/api/swarm/status/{pid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "stopped"
        assert data["swarm_pid"] is None
        assert data["process_alive"] is False

        # Verify project was updated in DB too
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.json()["status"] == "stopped"


class TestPathTraversal:
    """Test path traversal protection on file API."""

    async def test_backslash_path_normalization(self, client, project_with_folder):
        """Backslashes in paths should be normalized and still checked against allowlist."""
        pid = project_with_folder["id"]
        resp = await client.get(f"/api/files/tasks\\TASKS.md?project_id={pid}")
        # Should be normalized to tasks/TASKS.md and allowed
        assert resp.status_code == 200

    async def test_double_slash_path(self, client, project_with_folder):
        """Double slashes in path shouldn't bypass security."""
        pid = project_with_folder["id"]
        resp = await client.get(f"/api/files/tasks//TASKS.md?project_id={pid}")
        # The path gets cleaned up by the router, should work or be safely handled
        # The key thing is it shouldn't crash or bypass security
        assert resp.status_code in (200, 403, 404)

    async def test_non_allowlisted_nested_path(self, client, project_with_folder):
        """Deeply nested non-allowlisted paths should be blocked."""
        pid = project_with_folder["id"]
        resp = await client.get(f"/api/files/src/main.py?project_id={pid}")
        assert resp.status_code == 403


class TestHealthEndpoint:
    """Test health check endpoint returns expected fields."""

    async def test_health_returns_version(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["app"] == "Latent Underground"
        assert "version" in data
