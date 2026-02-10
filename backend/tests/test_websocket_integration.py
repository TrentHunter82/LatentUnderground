"""WebSocket integration tests.

Tests the WebSocket endpoint (/ws) including connection lifecycle,
ping/pong protocol, broadcast delivery, and ConnectionManager edge cases.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.testclient import TestClient


class TestWebSocketConnectAndPingPong:
    """Test basic WebSocket connection and the ping/pong protocol."""

    async def test_websocket_connect_and_ping_pong(self, app):
        """Connect to /ws, send 'ping', and verify a {"type": "pong"} response."""
        with TestClient(app) as tc:
            with tc.websocket_connect("/ws") as ws:
                ws.send_text("ping")
                data = json.loads(ws.receive_text())
                assert data == {"type": "pong"}


class TestWebSocketManagerTracksConnections:
    """Test that the ConnectionManager tracks active connections correctly."""

    async def test_websocket_manager_tracks_connections(self, app):
        """Connect a client, verify manager.active grows, then disconnect and verify it shrinks."""
        from app.routes.websocket import manager

        initial_count = len(manager.active)

        with TestClient(app) as tc:
            with tc.websocket_connect("/ws") as ws:
                # After connecting, the manager should have one more active connection
                assert len(manager.active) == initial_count + 1

                # Send a ping to confirm the connection is alive
                ws.send_text("ping")
                resp = json.loads(ws.receive_text())
                assert resp["type"] == "pong"

            # After the websocket_connect context exits, the connection is closed
            # and the manager should clean it up via the WebSocketDisconnect handler
            assert len(manager.active) == initial_count


class TestWebSocketBroadcastToMultipleClients:
    """Test that broadcast delivers messages to all connected clients."""

    async def test_websocket_broadcast_to_multiple_clients(self, app):
        """Connect 2 clients, broadcast a message via manager, verify both receive it."""
        import asyncio
        import concurrent.futures
        from app.routes.websocket import manager

        broadcast_data = {"type": "event", "payload": "hello"}

        with TestClient(app) as tc:
            with tc.websocket_connect("/ws") as ws1:
                with tc.websocket_connect("/ws") as ws2:
                    # Both should be tracked
                    assert len(manager.active) >= 2

                    # The TestClient's event loop is running in a background thread.
                    # Schedule the broadcast coroutine onto that loop via a new thread
                    # that creates its own event loop for the async call.
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(asyncio.run, manager.broadcast(broadcast_data))
                        future.result(timeout=5)

                    # Both clients should receive the broadcast
                    msg1 = json.loads(ws1.receive_text())
                    msg2 = json.loads(ws2.receive_text())

                    assert msg1 == broadcast_data
                    assert msg2 == broadcast_data


class TestWebSocketDisconnectCleanup:
    """Test that closing a WebSocket connection removes it from the manager."""

    async def test_websocket_disconnect_cleanup(self, app):
        """Connect, then close the connection and verify manager removes it."""
        from app.routes.websocket import manager

        initial_count = len(manager.active)

        with TestClient(app) as tc:
            with tc.websocket_connect("/ws") as ws:
                assert len(manager.active) == initial_count + 1
                ws.send_text("ping")
                json.loads(ws.receive_text())  # consume pong

            # Connection closed - manager should have cleaned up
            assert len(manager.active) == initial_count


class TestWebSocketMultiplePings:
    """Test sending multiple pings in sequence."""

    async def test_websocket_multiple_pings(self, app):
        """Connect and send 3 pings, verify 3 pong responses are received in order."""
        with TestClient(app) as tc:
            with tc.websocket_connect("/ws") as ws:
                for i in range(3):
                    ws.send_text("ping")
                    data = json.loads(ws.receive_text())
                    assert data == {"type": "pong"}, f"Pong #{i+1} mismatch"


class TestWebSocketArbitraryText:
    """Test that non-ping text does not crash the endpoint."""

    async def test_websocket_arbitrary_text(self, app):
        """Send non-ping text, verify the connection stays open and no response is sent for it."""
        with TestClient(app) as tc:
            with tc.websocket_connect("/ws") as ws:
                # Send arbitrary text - the endpoint receives it but only responds to "ping"
                ws.send_text("hello world")
                ws.send_text("some arbitrary data")
                ws.send_text('{"action": "subscribe"}')

                # Now send a ping to prove the connection is still alive
                ws.send_text("ping")
                data = json.loads(ws.receive_text())
                assert data == {"type": "pong"}


class TestManagerBroadcastRemovesDeadConnections:
    """Unit test: broadcast should remove connections that raise on send."""

    async def test_manager_broadcast_removes_dead_connections(self):
        """Add a mock WebSocket that raises on send_text, broadcast, verify it's removed."""
        from app.routes.websocket import ConnectionManager

        mgr = ConnectionManager()

        # Create a mock "dead" WebSocket that raises when sent to
        dead_ws = MagicMock()
        dead_ws.send_text = AsyncMock(side_effect=Exception("connection closed"))

        # Create a mock "alive" WebSocket that works fine
        alive_ws = MagicMock()
        alive_ws.send_text = AsyncMock(return_value=None)

        # Manually add both to the active list (bypassing accept() handshake)
        mgr.active.append(dead_ws)
        mgr.active.append(alive_ws)
        assert len(mgr.active) == 2

        # Broadcast a message
        await mgr.broadcast({"type": "test", "data": "hello"})

        # The dead connection should have been removed
        assert dead_ws not in mgr.active
        # The alive connection should still be there
        assert alive_ws in mgr.active
        assert len(mgr.active) == 1

        # Verify the alive ws actually received the message
        alive_ws.send_text.assert_called_once_with(
            json.dumps({"type": "test", "data": "hello"})
        )


class TestManagerDisconnectIdempotent:
    """Unit test: disconnect should be safe to call with unknown WebSocket objects."""

    async def test_manager_disconnect_idempotent(self):
        """Call disconnect with a WebSocket not in active list and verify no error."""
        from app.routes.websocket import ConnectionManager

        mgr = ConnectionManager()
        assert mgr.active == []

        # Disconnect something that was never connected - should not raise
        fake_ws = MagicMock()
        mgr.disconnect(fake_ws)
        assert mgr.active == []

        # Add one, disconnect it twice - second call should be safe
        another_ws = MagicMock()
        mgr.active.append(another_ws)
        assert len(mgr.active) == 1

        mgr.disconnect(another_ws)
        assert len(mgr.active) == 0

        # Second disconnect of the same ws - should not raise
        mgr.disconnect(another_ws)
        assert len(mgr.active) == 0
