"""Tests for SecurityHeadersMiddleware.

Verifies that security headers (X-Content-Type-Options, X-Frame-Options,
Referrer-Policy, X-XSS-Protection, Cache-Control) are present on all API responses.
"""

import pytest


class TestSecurityHeadersOnGET:
    """Verify security headers on GET responses across endpoints."""

    @pytest.mark.asyncio
    async def test_x_content_type_options_nosniff(self, client):
        """X-Content-Type-Options: nosniff prevents MIME sniffing attacks."""
        resp = await client.get("/api/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    @pytest.mark.asyncio
    async def test_x_frame_options_deny(self, client):
        """X-Frame-Options: DENY prevents clickjacking via iframes."""
        resp = await client.get("/api/health")
        assert resp.headers.get("x-frame-options") == "DENY"

    @pytest.mark.asyncio
    async def test_referrer_policy(self, client):
        """Referrer-Policy limits referrer information leakage."""
        resp = await client.get("/api/health")
        assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    @pytest.mark.asyncio
    async def test_x_xss_protection_disabled(self, client):
        """X-XSS-Protection: 0 (modern best practice: rely on CSP, not legacy filter)."""
        resp = await client.get("/api/health")
        assert resp.headers.get("x-xss-protection") == "0"

    @pytest.mark.asyncio
    async def test_cache_control_no_store_on_api(self, client):
        """API responses should have Cache-Control: no-store to prevent caching sensitive data."""
        resp = await client.get("/api/health")
        assert resp.headers.get("cache-control") == "no-store"


class TestSecurityHeadersOnVariousEndpoints:
    """Verify security headers are applied consistently across different endpoints."""

    @pytest.mark.asyncio
    async def test_headers_on_projects_list(self, client):
        """Project list endpoint should have all security headers."""
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        # GET endpoints with ETag use 'private, no-cache'; others use 'no-store'
        assert resp.headers.get("cache-control") in ("no-store", "private, no-cache")

    @pytest.mark.asyncio
    async def test_headers_on_webhooks_list(self, client):
        """Webhook list endpoint should have all security headers."""
        resp = await client.get("/api/webhooks")
        assert resp.status_code == 200
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"

    @pytest.mark.asyncio
    async def test_headers_on_post_response(self, client, tmp_path):
        """Security headers should be on POST (201) responses."""
        resp = await client.post("/api/projects", json={
            "name": "Security Header Test",
            "goal": "Verify headers on creation",
            "folder_path": str(tmp_path / "sec_header").replace("\\", "/"),
        })
        assert resp.status_code == 201
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        assert resp.headers.get("cache-control") == "no-store"

    @pytest.mark.asyncio
    async def test_headers_on_404_error(self, client):
        """Security headers should be present even on 404 error responses."""
        resp = await client.get("/api/projects/99999")
        assert resp.status_code == 404
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"

    @pytest.mark.asyncio
    async def test_headers_on_422_validation_error(self, client):
        """Security headers should be on validation error responses."""
        resp = await client.post("/api/projects", json={})
        assert resp.status_code == 422
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"


class TestSecurityHeadersComprehensive:
    """Comprehensive tests for all 5 security headers on a single response."""

    @pytest.mark.asyncio
    async def test_all_five_security_headers_present(self, client):
        """All 5 expected security headers on a single API response."""
        resp = await client.get("/api/health")
        headers = {
            "x-content-type-options": "nosniff",
            "x-frame-options": "DENY",
            "referrer-policy": "strict-origin-when-cross-origin",
            "x-xss-protection": "0",
            "cache-control": "no-store",
        }
        for header, expected_value in headers.items():
            actual = resp.headers.get(header)
            assert actual == expected_value, (
                f"Header {header}: expected '{expected_value}', got '{actual}'"
            )

    @pytest.mark.asyncio
    async def test_headers_on_delete_response(self, client, tmp_path):
        """Security headers should be on DELETE (204) responses."""
        # Create then delete a project
        create_resp = await client.post("/api/projects", json={
            "name": "Delete Header Test",
            "goal": "Test headers on delete",
            "folder_path": str(tmp_path / "del_header").replace("\\", "/"),
        })
        pid = create_resp.json()["id"]

        resp = await client.delete(f"/api/projects/{pid}")
        assert resp.status_code == 204
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"

    @pytest.mark.asyncio
    async def test_headers_on_patch_response(self, client, created_project):
        """Security headers should be on PATCH (200) responses."""
        pid = created_project["id"]
        resp = await client.patch(f"/api/projects/{pid}", json={"name": "Patched"})
        assert resp.status_code == 200
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        assert resp.headers.get("cache-control") == "no-store"
