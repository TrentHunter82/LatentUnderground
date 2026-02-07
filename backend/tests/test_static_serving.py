"""Tests for frontend static serving from FastAPI."""

import pytest
from pathlib import Path


class TestStaticServing:
    """Test that FastAPI correctly serves the built frontend."""

    async def test_root_serves_index_html(self, client):
        """GET / should return index.html content."""
        dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
        if not dist.exists():
            pytest.skip("frontend/dist not built")

        resp = await client.get("/")
        assert resp.status_code == 200
        # index.html should contain typical React app markers
        assert "<!doctype html>" in resp.text.lower() or "<html" in resp.text.lower()

    async def test_spa_fallback_for_client_routes(self, client):
        """Non-API paths like /projects/1 should fall back to index.html."""
        dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
        if not dist.exists():
            pytest.skip("frontend/dist not built")

        resp = await client.get("/projects/42")
        assert resp.status_code == 200
        # Should still get index.html for SPA routing
        assert "<html" in resp.text.lower() or "<!doctype" in resp.text.lower()

    async def test_api_routes_not_intercepted_by_spa(self, client):
        """API routes should still work and not be caught by the SPA handler."""
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["app"] == "Latent Underground"

    async def test_api_projects_not_intercepted(self, client):
        """GET /api/projects should return JSON, not index.html."""
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_assets_serve_correctly(self, client):
        """Static assets under /assets/ should be served from dist/assets/."""
        dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
        if not dist.exists():
            pytest.skip("frontend/dist not built")

        assets_dir = dist / "assets"
        if not assets_dir.exists():
            pytest.skip("dist/assets not found")

        # Find a real asset file to test
        asset_files = list(assets_dir.iterdir())
        if not asset_files:
            pytest.skip("No asset files found")

        asset_name = asset_files[0].name
        resp = await client.get(f"/assets/{asset_name}")
        assert resp.status_code == 200

    async def test_nonexistent_asset_returns_404(self, client):
        """Request for a specific nonexistent asset should return 404."""
        dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
        if not dist.exists():
            pytest.skip("frontend/dist not built")

        resp = await client.get("/assets/nonexistent-file-xyz.js")
        assert resp.status_code == 404
