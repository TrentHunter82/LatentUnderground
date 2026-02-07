"""Tests for WebSocket endpoint."""

import json

import pytest
from httpx import ASGITransport, AsyncClient


class TestWebSocket:
    """Tests for WS /ws."""

    async def test_websocket_connect(self, app):
        """Test that WebSocket connection can be established."""
        from starlette.testclient import TestClient

        with TestClient(app) as tc:
            with tc.websocket_connect("/ws") as ws:
                # Send ping, expect pong
                ws.send_text("ping")
                resp = ws.receive_text()
                data = json.loads(resp)
                assert data["type"] == "pong"

    async def test_websocket_ping_pong(self, app):
        """Test ping/pong mechanism."""
        from starlette.testclient import TestClient

        with TestClient(app) as tc:
            with tc.websocket_connect("/ws") as ws:
                ws.send_text("ping")
                resp = json.loads(ws.receive_text())
                assert resp == {"type": "pong"}

    async def test_connection_manager_init(self):
        """Test that ConnectionManager initializes empty."""
        from app.routes.websocket import ConnectionManager

        mgr = ConnectionManager()
        assert mgr.active == []

    async def test_connection_manager_disconnect_noop(self):
        """Test that disconnecting non-existent connection doesn't error."""
        from app.routes.websocket import ConnectionManager

        mgr = ConnectionManager()
        mgr.disconnect(None)
        assert mgr.active == []

    async def test_connection_manager_broadcast_empty(self):
        """Test that broadcasting to no clients doesn't error."""
        from app.routes.websocket import ConnectionManager

        mgr = ConnectionManager()
        await mgr.broadcast({"type": "test"})
        # No error means success

    async def test_multiple_ping_pong(self, app):
        """Test multiple ping/pong exchanges."""
        from starlette.testclient import TestClient

        with TestClient(app) as tc:
            with tc.websocket_connect("/ws") as ws:
                for _ in range(3):
                    ws.send_text("ping")
                    resp = json.loads(ws.receive_text())
                    assert resp["type"] == "pong"
