"""Tests for watcher API endpoints (watch/unwatch)."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture(autouse=True)
def patch_watcher_db(tmp_db):
    """Patch the DB_PATH used by watcher routes to use the test database."""
    with patch("app.routes.watcher.DB_PATH", tmp_db):
        yield


@pytest.fixture(autouse=True)
def clear_watchers():
    """Clear the _watchers dict between tests to avoid cross-test state."""
    from app.routes.watcher import _watchers
    _watchers.clear()
    yield
    _watchers.clear()


class TestStartWatching:
    """Tests for POST /api/watch/{project_id}."""

    async def test_watch_project_not_found(self, client):
        resp = await client.post("/api/watch/9999")
        assert resp.status_code == 404

    async def test_watch_starts_watcher(self, client, project_with_folder):
        pid = project_with_folder["id"]

        with patch("app.routes.watcher.FolderWatcher") as MockWatcher:
            mock_instance = AsyncMock()
            MockWatcher.return_value = mock_instance

            resp = await client.post(f"/api/watch/{pid}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "watching"
            mock_instance.start.assert_awaited_once()

    async def test_watch_already_watching(self, client, project_with_folder):
        """Second watch call for same project returns already_watching."""
        pid = project_with_folder["id"]

        with patch("app.routes.watcher.FolderWatcher") as MockWatcher:
            mock_instance = AsyncMock()
            MockWatcher.return_value = mock_instance

            # First call starts watching
            resp = await client.post(f"/api/watch/{pid}")
            assert resp.status_code == 200
            assert resp.json()["status"] == "watching"

            # Second call returns already_watching
            resp = await client.post(f"/api/watch/{pid}")
            assert resp.status_code == 200
            assert resp.json()["status"] == "already_watching"


class TestStopWatching:
    """Tests for POST /api/unwatch/{project_id}."""

    async def test_unwatch_project_not_found(self, client):
        resp = await client.post("/api/unwatch/9999")
        assert resp.status_code == 404

    async def test_unwatch_not_watching(self, client, project_with_folder):
        """Unwatching a project that's not being watched returns not_watching."""
        pid = project_with_folder["id"]
        resp = await client.post(f"/api/unwatch/{pid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "not_watching"

    async def test_unwatch_stops_watcher(self, client, project_with_folder):
        """Unwatching a watched project stops the watcher and returns stopped."""
        pid = project_with_folder["id"]

        with patch("app.routes.watcher.FolderWatcher") as MockWatcher:
            mock_instance = AsyncMock()
            MockWatcher.return_value = mock_instance

            # Start watching first
            resp = await client.post(f"/api/watch/{pid}")
            assert resp.status_code == 200

            # Then unwatch
            resp = await client.post(f"/api/unwatch/{pid}")
            assert resp.status_code == 200
            assert resp.json()["status"] == "stopped"
            mock_instance.stop.assert_awaited_once()

    async def test_watch_then_unwatch_then_rewatch(self, client, project_with_folder):
        """Full lifecycle: watch -> unwatch -> watch again."""
        pid = project_with_folder["id"]

        with patch("app.routes.watcher.FolderWatcher") as MockWatcher:
            mock_instance = AsyncMock()
            MockWatcher.return_value = mock_instance

            # Watch
            resp = await client.post(f"/api/watch/{pid}")
            assert resp.status_code == 200
            assert resp.json()["status"] == "watching"

            # Unwatch
            resp = await client.post(f"/api/unwatch/{pid}")
            assert resp.status_code == 200
            assert resp.json()["status"] == "stopped"

            # Watch again
            resp = await client.post(f"/api/watch/{pid}")
            assert resp.status_code == 200
            assert resp.json()["status"] == "watching"
