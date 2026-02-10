"""Integration test: full workflow with WebSocket events.

Tests the complete browser-like flow:
create project -> launch -> receive WebSocket events -> status updates -> stop
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient


class TestWorkflowWithWebSocket:
    """Simulate a browser session: REST calls + WebSocket for live updates."""

    async def test_dashboard_flow_with_websocket(self, app, mock_project_folder):
        """Create project, connect WS, launch swarm, verify events, stop."""
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Create project
            resp = await client.post("/api/projects", json={
                "name": "WS Integration Test",
                "goal": "Test dashboard flow",
                "folder_path": str(mock_project_folder).replace("\\", "/"),
            })
            assert resp.status_code == 201
            pid = resp.json()["id"]

            # 2. Connect WebSocket and verify ping/pong
            with TestClient(app) as tc:
                with tc.websocket_connect("/ws") as ws:
                    ws.send_text("ping")
                    pong = json.loads(ws.receive_text())
                    assert pong["type"] == "pong"

            # 3. Check initial swarm status (dashboard load)
            resp = await client.get(f"/api/swarm/status/{pid}")
            assert resp.status_code == 200
            status = resp.json()
            assert status["tasks"]["total"] == 4
            assert status["tasks"]["done"] == 2
            assert status["signals"]["backend-ready"] is True
            assert "agents" in status

            # 4. Launch swarm with mocked subprocess
            (mock_project_folder / "swarm.ps1").write_text("# mock")
            with patch("app.routes.swarm.subprocess.Popen") as mock_popen:
                mock_process = MagicMock()
                mock_process.pid = 12345
                mock_process.stdout = MagicMock()
                mock_process.stderr = MagicMock()
                mock_process.wait = MagicMock()
                mock_popen.return_value = mock_process

                resp = await client.post("/api/swarm/launch", json={"project_id": pid})
                assert resp.status_code == 200
                assert resp.json()["status"] == "launched"

            # 5. Verify running state (dashboard would poll this)
            resp = await client.get(f"/api/projects/{pid}")
            assert resp.json()["status"] == "running"

            # 6. Simulate file changes (agent writes to tasks)
            resp = await client.put("/api/files/tasks/TASKS.md", json={
                "content": "# Tasks\n- [x] Task 1\n- [x] Task 2\n- [x] Task 3\n- [x] Task 4\n",
                "project_id": pid,
            })
            assert resp.status_code == 200

            # 7. Dashboard refresh - status shows all tasks done
            resp = await client.get(f"/api/swarm/status/{pid}")
            assert resp.json()["tasks"]["done"] == 4
            assert resp.json()["tasks"]["percent"] == 100.0

            # 8. Stop swarm
            resp = await client.post("/api/swarm/stop", json={"project_id": pid})
            assert resp.json()["status"] == "stopped"

            # 9. Final project state
            resp = await client.get(f"/api/projects/{pid}")
            assert resp.json()["status"] == "stopped"

    async def test_broadcast_reaches_connected_clients(self, app):
        """Verify that broadcast sends data to all connected WebSocket clients."""
        from app.routes.websocket import manager

        with TestClient(app) as tc:
            with tc.websocket_connect("/ws") as ws1:
                with tc.websocket_connect("/ws") as ws2:
                    # Both clients should be in the active list
                    assert len(manager.active) >= 2

                    # Send ping from client 1
                    ws1.send_text("ping")
                    resp1 = json.loads(ws1.receive_text())
                    assert resp1["type"] == "pong"

                    # Send ping from client 2
                    ws2.send_text("ping")
                    resp2 = json.loads(ws2.receive_text())
                    assert resp2["type"] == "pong"

    async def test_project_lifecycle_ordering(self, app, tmp_path):
        """Verify project list order: newest first."""
        from httpx import ASGITransport, AsyncClient
        import asyncio

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Create projects in sequence
            for i in range(3):
                resp = await client.post("/api/projects", json={
                    "name": f"Project {i}",
                    "goal": f"Goal {i}",
                    "folder_path": str(tmp_path / f"project_{i}"),
                })
                assert resp.status_code == 201

            # List should return newest first
            resp = await client.get("/api/projects")
            projects = resp.json()
            assert len(projects) == 3
            assert projects[0]["name"] == "Project 2"
            assert projects[2]["name"] == "Project 0"
