"""Tests for API key authentication middleware (Phase 7)."""

from unittest.mock import patch

import pytest


class TestAuthMiddleware:
    """Tests for APIKeyMiddleware in app.main."""

    async def test_auth_disabled_when_empty_key(self, client):
        """When LU_API_KEY is empty (default), all requests pass through."""
        with patch("app.main.config") as mock_config:
            mock_config.API_KEY = ""
            resp = await client.get("/api/projects")
            assert resp.status_code == 200

    async def test_auth_valid_bearer_token(self, client):
        """Valid Bearer token allows the request through."""
        with patch("app.main.config") as mock_config:
            mock_config.API_KEY = "test-secret-key"
            mock_config.CORS_ORIGINS = ["http://localhost:5173"]
            resp = await client.get(
                "/api/projects",
                headers={"Authorization": "Bearer test-secret-key"},
            )
            assert resp.status_code == 200

    async def test_auth_valid_x_api_key(self, client):
        """Valid X-API-Key header allows the request through."""
        with patch("app.main.config") as mock_config:
            mock_config.API_KEY = "test-secret-key"
            mock_config.CORS_ORIGINS = ["http://localhost:5173"]
            resp = await client.get(
                "/api/projects",
                headers={"X-API-Key": "test-secret-key"},
            )
            assert resp.status_code == 200

    async def test_auth_invalid_key(self, client):
        """Invalid API key returns 401."""
        with patch("app.main.config") as mock_config:
            mock_config.API_KEY = "correct-key"
            mock_config.CORS_ORIGINS = ["http://localhost:5173"]
            resp = await client.get(
                "/api/projects",
                headers={"Authorization": "Bearer wrong-key"},
            )
            assert resp.status_code == 401
            assert "Invalid or missing" in resp.json()["detail"]

    async def test_auth_missing_key(self, client):
        """Missing auth headers returns 401 when API key is configured."""
        with patch("app.main.config") as mock_config:
            mock_config.API_KEY = "some-key"
            mock_config.CORS_ORIGINS = ["http://localhost:5173"]
            resp = await client.get("/api/projects")
            assert resp.status_code == 401

    async def test_auth_health_bypass(self, client):
        """GET /api/health bypasses auth even when key is set."""
        with patch("app.main.config") as mock_config:
            mock_config.API_KEY = "some-key"
            mock_config.CORS_ORIGINS = ["http://localhost:5173"]
            resp = await client.get("/api/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    async def test_auth_docs_bypass(self, client):
        """GET /docs bypasses auth."""
        with patch("app.main.config") as mock_config:
            mock_config.API_KEY = "some-key"
            mock_config.CORS_ORIGINS = ["http://localhost:5173"]
            resp = await client.get("/docs")
            # /docs returns HTML redirect or page
            assert resp.status_code in (200, 307)

    async def test_auth_non_api_bypass(self, client):
        """Non-/api/ paths (frontend static) bypass auth."""
        with patch("app.main.config") as mock_config:
            mock_config.API_KEY = "some-key"
            mock_config.CORS_ORIGINS = ["http://localhost:5173"]
            # A non-API path should not get 401
            resp = await client.get("/some-frontend-path")
            # Will be 404 or 200 (SPA catch-all) but NOT 401
            assert resp.status_code != 401
