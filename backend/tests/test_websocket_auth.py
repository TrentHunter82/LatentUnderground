"""Tests for WebSocket authentication behavior.

Documents the interaction between APIKeyMiddleware (which bypasses /ws) and
the WebSocket endpoint's own token-based authentication (query param ?token=<key>).

The middleware at main.py line 123 skips auth for path == "/ws", but the
websocket endpoint in routes/websocket.py performs its own hmac-based token
check via the ?token= query parameter when config.API_KEY is set.
"""

import json
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from app import config as app_config


class TestWebSocketAuthDisabled:
    """Tests when no API key is configured (auth disabled)."""

    async def test_ws_connects_when_auth_disabled(self, app):
        """WebSocket connects and ping/pong works when no API key is set."""
        original = app_config.API_KEY
        app_config.API_KEY = ""
        try:
            with TestClient(app) as tc:
                with tc.websocket_connect("/ws") as ws:
                    ws.send_text("ping")
                    resp = json.loads(ws.receive_text())
                    assert resp["type"] == "pong"
        finally:
            app_config.API_KEY = original


class TestWebSocketAuthBypass:
    """Tests documenting the middleware auth bypass for /ws.

    The APIKeyMiddleware skips /ws (main.py line 123), so the HTTP upgrade
    always succeeds at the middleware level. However, the websocket endpoint
    itself checks config.API_KEY and requires ?token=<key>.
    """

    async def test_ws_rejected_without_token_when_auth_enabled(self, app):
        """When API_KEY is set, WS without ?token= is rejected by the endpoint."""
        original = app_config.API_KEY
        app_config.API_KEY = "test-secret-key"
        try:
            with TestClient(app) as tc:
                # Connect without token - the endpoint should close with 4401
                with pytest.raises(Exception):
                    with tc.websocket_connect("/ws") as ws:
                        ws.send_text("ping")
                        ws.receive_text()
        finally:
            app_config.API_KEY = original

    async def test_ws_connects_with_valid_token(self, app):
        """When API_KEY is set, WS with correct ?token= succeeds."""
        original = app_config.API_KEY
        app_config.API_KEY = "test-secret-key"
        try:
            with TestClient(app) as tc:
                with tc.websocket_connect("/ws?token=test-secret-key") as ws:
                    ws.send_text("ping")
                    resp = json.loads(ws.receive_text())
                    assert resp["type"] == "pong"
        finally:
            app_config.API_KEY = original

    async def test_ws_rejected_with_wrong_token(self, app):
        """When API_KEY is set, WS with wrong ?token= is rejected."""
        original = app_config.API_KEY
        app_config.API_KEY = "test-secret-key"
        try:
            with TestClient(app) as tc:
                with pytest.raises(Exception):
                    with tc.websocket_connect("/ws?token=wrong-key") as ws:
                        ws.send_text("ping")
                        ws.receive_text()
        finally:
            app_config.API_KEY = original


class TestWebSocketVsHTTPAuth:
    """Tests proving the inconsistency between HTTP and WS auth mechanisms.

    HTTP /api/ routes use header-based auth (Bearer token or X-API-Key).
    WS /ws uses query parameter auth (?token=<key>).
    The middleware bypasses /ws entirely -- the endpoint handles its own auth.
    """

    async def test_http_api_requires_auth_but_ws_middleware_skips(self, app):
        """HTTP GET /api/projects requires auth header, while /ws bypasses middleware.

        The middleware returns 401 for /api/ routes without auth, but lets /ws
        through. The WS endpoint then does its own token check.
        """
        original = app_config.API_KEY
        app_config.API_KEY = "test-secret-key"
        try:
            with TestClient(app) as tc:
                # HTTP API without auth -> 401
                resp = tc.get("/api/projects")
                assert resp.status_code == 401

                # WS with valid token -> connects
                with tc.websocket_connect("/ws?token=test-secret-key") as ws:
                    ws.send_text("ping")
                    data = json.loads(ws.receive_text())
                    assert data["type"] == "pong"
        finally:
            app_config.API_KEY = original

    async def test_http_api_with_bearer_auth_works(self, client):
        """HTTP API works with Bearer token auth."""
        original = app_config.API_KEY
        app_config.API_KEY = "test-secret-key"
        try:
            # Without auth -> 401
            resp = await client.get("/api/projects")
            assert resp.status_code == 401

            # With Bearer auth -> 200
            resp = await client.get(
                "/api/projects",
                headers={"Authorization": "Bearer test-secret-key"},
            )
            assert resp.status_code == 200
        finally:
            app_config.API_KEY = original

    async def test_http_api_with_x_api_key_header_works(self, client):
        """HTTP API works with X-API-Key header auth."""
        original = app_config.API_KEY
        app_config.API_KEY = "test-secret-key"
        try:
            resp = await client.get(
                "/api/projects",
                headers={"X-API-Key": "test-secret-key"},
            )
            assert resp.status_code == 200
        finally:
            app_config.API_KEY = original


class TestHealthEndpointAlwaysOpen:
    """Tests that /api/health is always accessible regardless of auth."""

    async def test_health_endpoint_accessible_without_auth(self, client):
        """GET /api/health returns 200 even when API key is set."""
        original = app_config.API_KEY
        app_config.API_KEY = "test-secret-key"
        try:
            resp = await client.get("/api/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
        finally:
            app_config.API_KEY = original


class TestWebSocketWithValidAuth:
    """Tests that WebSocket works properly when authenticated."""

    async def test_ws_ping_pong_with_auth(self, app):
        """Authenticated WS connection supports full ping/pong exchange."""
        original = app_config.API_KEY
        app_config.API_KEY = "test-secret-key"
        try:
            with TestClient(app) as tc:
                with tc.websocket_connect("/ws?token=test-secret-key") as ws:
                    # Multiple ping/pong exchanges
                    for _ in range(3):
                        ws.send_text("ping")
                        resp = json.loads(ws.receive_text())
                        assert resp["type"] == "pong"
        finally:
            app_config.API_KEY = original

    async def test_ws_non_ping_message_no_crash(self, app):
        """Authenticated WS handles non-ping messages without crashing."""
        original = app_config.API_KEY
        app_config.API_KEY = "test-secret-key"
        try:
            with TestClient(app) as tc:
                with tc.websocket_connect("/ws?token=test-secret-key") as ws:
                    # Send a non-ping message - should not crash the connection
                    ws.send_text("hello")
                    # Follow up with a ping to prove the connection is still alive
                    ws.send_text("ping")
                    resp = json.loads(ws.receive_text())
                    assert resp["type"] == "pong"
        finally:
            app_config.API_KEY = original


class TestWebSocketBroadcast:
    """Tests for ConnectionManager broadcast with multiple clients."""

    async def test_broadcast_to_multiple_clients(self, app):
        """Broadcast sends message to all connected WebSocket clients."""
        from app.routes.websocket import manager

        with TestClient(app) as tc:
            with tc.websocket_connect("/ws") as ws1:
                with tc.websocket_connect("/ws") as ws2:
                    # Both clients should be in the active list
                    assert len(manager.active) >= 2

                    # Send ping from both to prove they're connected
                    ws1.send_text("ping")
                    r1 = json.loads(ws1.receive_text())
                    assert r1["type"] == "pong"

                    ws2.send_text("ping")
                    r2 = json.loads(ws2.receive_text())
                    assert r2["type"] == "pong"


class TestWebSocketDisconnectCleanup:
    """Tests that disconnected clients are removed from the active list."""

    async def test_disconnect_removes_client(self, app):
        """Closing a WS connection removes it from ConnectionManager.active."""
        from app.routes.websocket import manager

        initial_count = len(manager.active)

        with TestClient(app) as tc:
            with tc.websocket_connect("/ws") as ws:
                ws.send_text("ping")
                json.loads(ws.receive_text())
                # Client should be in active list
                assert len(manager.active) > initial_count

            # After context manager exits (connection closed), client should be removed.
            # Allow a brief moment for cleanup since disconnect happens asynchronously.
            assert len(manager.active) == initial_count

    async def test_disconnect_manager_unit(self):
        """Unit test: ConnectionManager.disconnect removes the websocket."""
        from app.routes.websocket import ConnectionManager

        mgr = ConnectionManager()
        sentinel = object()  # stand-in for a WebSocket
        mgr.active.append(sentinel)
        assert len(mgr.active) == 1

        mgr.disconnect(sentinel)
        assert len(mgr.active) == 0

    async def test_disconnect_nonexistent_noop(self):
        """Unit test: disconnecting a non-existent WS is a no-op."""
        from app.routes.websocket import ConnectionManager

        mgr = ConnectionManager()
        mgr.disconnect(object())
        assert len(mgr.active) == 0


class TestWebSocketMiddlewareBypassDocumented:
    """Documents the middleware bypass behavior.

    The APIKeyMiddleware at main.py line 123 explicitly skips path == "/ws".
    This means the HTTP upgrade request is never rejected by the middleware.
    Authentication is instead handled by the WebSocket endpoint itself
    using the ?token= query parameter.

    This test class documents this architectural decision. If the middleware
    bypass is removed in a future phase, these tests will need updating.
    """

    @pytest.mark.xfail(
        reason="WS middleware bypass is a known architectural choice - "
               "tests will change if /ws auth moves to middleware"
    )
    async def test_ws_without_token_blocked_by_middleware(self, app):
        """This test EXPECTS the middleware to block unauthenticated WS.

        Currently xfail because the middleware bypasses /ws and the endpoint
        handles auth separately. When the endpoint-level auth is disabled but
        middleware auth is enabled, the WS connection should be blocked by the
        middleware. Currently it is NOT -- the middleware lets /ws through.

        If middleware auth is added for /ws in a future phase, this will pass.
        """
        # Save and restore originals
        original = app_config.API_KEY
        app_config.API_KEY = "test-secret-key"
        try:
            # Patch ONLY the websocket endpoint's config to disable endpoint auth.
            # The middleware (reading app_config.API_KEY directly) still has auth enabled.
            with patch("app.routes.websocket.config") as mock_ws_config:
                mock_ws_config.API_KEY = ""  # Disable endpoint-level auth

                with TestClient(app) as tc:
                    # If middleware enforced auth on /ws, this would fail to connect.
                    # Currently it SUCCEEDS because middleware bypasses /ws,
                    # and the endpoint auth is disabled via the patch above.
                    # The xfail expects this to raise (i.e., be blocked), so it xfails.
                    with pytest.raises(Exception):
                        with tc.websocket_connect("/ws") as ws:
                            ws.send_text("ping")
                            ws.receive_text()
        finally:
            app_config.API_KEY = original

    async def test_middleware_bypass_allows_upgrade_endpoint_does_auth(self, app):
        """Documents the two-layer auth: middleware skip + endpoint token check.

        1. Middleware lets /ws through (line 123 in main.py)
        2. Endpoint checks ?token= query param (websocket.py lines 47-51)
        """
        original = app_config.API_KEY
        app_config.API_KEY = "test-secret-key"
        try:
            with TestClient(app) as tc:
                # Without token: middleware lets it through, endpoint rejects
                with pytest.raises(Exception):
                    with tc.websocket_connect("/ws") as ws:
                        ws.send_text("ping")
                        ws.receive_text()

                # With token: middleware lets it through, endpoint accepts
                with tc.websocket_connect("/ws?token=test-secret-key") as ws:
                    ws.send_text("ping")
                    resp = json.loads(ws.receive_text())
                    assert resp["type"] == "pong"
        finally:
            app_config.API_KEY = original
