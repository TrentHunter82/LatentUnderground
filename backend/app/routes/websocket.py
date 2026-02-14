import asyncio
import hmac
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from .. import config

logger = logging.getLogger("latent.websocket")

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict):
        message = json.dumps(data)
        disconnected = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                logger.debug("WebSocket send failed, removing connection", exc_info=True)
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # Authenticate WebSocket connections when API key is configured
    api_key = config.API_KEY
    if api_key:
        # Accept token via query parameter: /ws?token=<key>
        token = ws.query_params.get("token", "")
        if not token or not hmac.compare_digest(token, api_key):
            await ws.close(code=4401, reason="Authentication required")
            return

    await manager.connect(ws)
    try:
        while True:
            # Keep connection alive, listen for client messages
            data = await ws.receive_text()
            # Client can send ping, we respond with pong
            if data == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        manager.disconnect(ws)
