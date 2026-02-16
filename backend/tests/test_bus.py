"""Tests for the inter-agent message bus API."""

import pytest
from pathlib import Path


@pytest.fixture()
async def running_project(client, sample_project_data, tmp_path):
    """Create a project with running status for bus tests."""
    # Create project
    resp = await client.post("/api/projects", json=sample_project_data)
    assert resp.status_code == 201
    project = resp.json()

    # Create required directories
    folder = Path(sample_project_data["folder_path"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ".claude").mkdir(exist_ok=True)
    (folder / ".claude" / "attention").mkdir(exist_ok=True)
    (folder / ".swarm").mkdir(exist_ok=True)
    (folder / ".swarm" / "bus").mkdir(exist_ok=True)

    # Update project to running status (bypass swarm launch)
    from app import database
    async with database.aiosqlite.connect(database.DB_PATH) as db:
        await db.execute(
            "UPDATE projects SET status = 'running' WHERE id = ?",
            (project["id"],),
        )
        # Create a swarm run
        await db.execute(
            "INSERT INTO swarm_runs (project_id, status) VALUES (?, 'running')",
            (project["id"],),
        )
        await db.commit()

    return project


class TestBusSendMessage:
    """Tests for POST /api/bus/{project_id}/send."""

    async def test_send_message_success(self, client, running_project):
        """Send a message to another agent."""
        resp = await client.post(
            f"/api/bus/{running_project['id']}/send",
            json={
                "from_agent": "Claude-1",
                "to_agent": "Claude-2",
                "channel": "general",
                "priority": "normal",
                "msg_type": "info",
                "body": "API endpoints are ready",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "sent"
        assert "id" in data

    async def test_send_broadcast(self, client, running_project):
        """Send a broadcast message to all agents."""
        resp = await client.post(
            f"/api/bus/{running_project['id']}/send",
            json={
                "from_agent": "Claude-1",
                "to_agent": "all",
                "channel": "general",
                "priority": "normal",
                "msg_type": "info",
                "body": "Starting integration tests",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "sent"

    async def test_send_critical_creates_attention_file(self, client, running_project, sample_project_data):
        """Critical priority message creates attention file."""
        folder = Path(sample_project_data["folder_path"])

        resp = await client.post(
            f"/api/bus/{running_project['id']}/send",
            json={
                "from_agent": "Claude-1",
                "to_agent": "Claude-2",
                "channel": "critical",
                "priority": "critical",
                "msg_type": "blocker",
                "body": "STOP: Found circular dependency",
            },
        )
        assert resp.status_code == 201

        # Check attention file was created
        attention_file = folder / ".claude" / "attention" / "Claude-2.attention"
        assert attention_file.exists()

    async def test_send_to_channel(self, client, running_project):
        """Send message to a channel."""
        resp = await client.post(
            f"/api/bus/{running_project['id']}/send",
            json={
                "from_agent": "Claude-1",
                "to_agent": "channel:lessons",
                "channel": "lessons",
                "priority": "normal",
                "msg_type": "lesson",
                "body": "Always run typecheck before committing",
            },
        )
        assert resp.status_code == 201

    async def test_send_project_not_found(self, client):
        """404 for non-existent project."""
        resp = await client.post(
            "/api/bus/99999/send",
            json={
                "from_agent": "Claude-1",
                "to_agent": "Claude-2",
                "channel": "general",
                "priority": "normal",
                "msg_type": "info",
                "body": "Test",
            },
        )
        assert resp.status_code == 404

    async def test_send_invalid_channel(self, client, running_project):
        """Validation error for invalid channel."""
        resp = await client.post(
            f"/api/bus/{running_project['id']}/send",
            json={
                "from_agent": "Claude-1",
                "to_agent": "Claude-2",
                "channel": "invalid",
                "priority": "normal",
                "msg_type": "info",
                "body": "Test",
            },
        )
        assert resp.status_code == 422


class TestBusInbox:
    """Tests for GET /api/bus/{project_id}/inbox/{agent}."""

    async def test_inbox_empty(self, client, running_project):
        """Empty inbox returns empty list."""
        resp = await client.get(
            f"/api/bus/{running_project['id']}/inbox/Claude-1",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["messages"] == []
        assert data["total"] == 0
        assert data["agent"] == "Claude-1"

    async def test_inbox_receives_direct_message(self, client, running_project):
        """Agent inbox receives direct messages."""
        # Send message
        await client.post(
            f"/api/bus/{running_project['id']}/send",
            json={
                "from_agent": "Claude-1",
                "to_agent": "Claude-2",
                "channel": "general",
                "priority": "normal",
                "msg_type": "info",
                "body": "Hello Claude-2",
            },
        )

        # Check inbox
        resp = await client.get(
            f"/api/bus/{running_project['id']}/inbox/Claude-2",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert any(m["body"] == "Hello Claude-2" for m in data["messages"])

    async def test_inbox_receives_broadcast(self, client, running_project):
        """Agent inbox receives broadcast messages."""
        # Send broadcast
        await client.post(
            f"/api/bus/{running_project['id']}/send",
            json={
                "from_agent": "Claude-1",
                "to_agent": "all",
                "channel": "general",
                "priority": "normal",
                "msg_type": "info",
                "body": "Broadcast to all",
            },
        )

        # Check inbox for different agent
        resp = await client.get(
            f"/api/bus/{running_project['id']}/inbox/Claude-3",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert any(m["body"] == "Broadcast to all" for m in data["messages"])

    async def test_inbox_since_filter(self, client, running_project):
        """Inbox since parameter filters old messages."""
        from datetime import datetime, timedelta

        # Send old message
        await client.post(
            f"/api/bus/{running_project['id']}/send",
            json={
                "from_agent": "Claude-1",
                "to_agent": "Claude-2",
                "channel": "general",
                "priority": "normal",
                "msg_type": "info",
                "body": "Old message",
            },
        )

        # Future timestamp
        future = (datetime.now() + timedelta(hours=1)).isoformat()

        resp = await client.get(
            f"/api/bus/{running_project['id']}/inbox/Claude-2?since={future}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0


class TestBusAck:
    """Tests for POST /api/bus/{project_id}/ack/{message_id}."""

    async def test_ack_message(self, client, running_project):
        """Acknowledge a message."""
        # Send message
        send_resp = await client.post(
            f"/api/bus/{running_project['id']}/send",
            json={
                "from_agent": "Claude-1",
                "to_agent": "Claude-2",
                "channel": "general",
                "priority": "normal",
                "msg_type": "info",
                "body": "Ack test",
            },
        )
        message_id = send_resp.json()["id"]

        # Ack
        resp = await client.post(
            f"/api/bus/{running_project['id']}/ack/{message_id}?agent=Claude-2",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["acked"] is True
        assert data["id"] == message_id

    async def test_ack_already_acked(self, client, running_project):
        """Re-acknowledging returns acked=false."""
        # Send message
        send_resp = await client.post(
            f"/api/bus/{running_project['id']}/send",
            json={
                "from_agent": "Claude-1",
                "to_agent": "Claude-2",
                "channel": "general",
                "priority": "normal",
                "msg_type": "info",
                "body": "Double ack test",
            },
        )
        message_id = send_resp.json()["id"]

        # First ack
        await client.post(
            f"/api/bus/{running_project['id']}/ack/{message_id}?agent=Claude-2",
        )

        # Second ack
        resp = await client.post(
            f"/api/bus/{running_project['id']}/ack/{message_id}?agent=Claude-2",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["acked"] is False

    async def test_ack_not_found(self, client, running_project):
        """404 for non-existent message."""
        resp = await client.post(
            f"/api/bus/{running_project['id']}/ack/fake-uuid-12345?agent=Claude-2",
        )
        assert resp.status_code == 404


class TestBusChannels:
    """Tests for GET /api/bus/{project_id}/channels/{channel}/messages."""

    async def test_get_channel_messages(self, client, running_project):
        """Get messages from a channel."""
        # Post to channel
        await client.post(
            f"/api/bus/{running_project['id']}/send",
            json={
                "from_agent": "Claude-1",
                "to_agent": "channel:lessons",
                "channel": "lessons",
                "priority": "normal",
                "msg_type": "lesson",
                "body": "Test lesson",
            },
        )

        # Read channel
        resp = await client.get(
            f"/api/bus/{running_project['id']}/channels/lessons/messages",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["channel"] == "lessons"
        assert any(m["body"] == "Test lesson" for m in data["messages"])

    async def test_get_channel_empty(self, client, running_project):
        """Empty channel returns empty list."""
        resp = await client.get(
            f"/api/bus/{running_project['id']}/channels/review/messages",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["messages"] == []


class TestBusAllMessages:
    """Tests for GET /api/bus/{project_id}/messages."""

    async def test_get_all_messages(self, client, running_project):
        """Get all messages for a project."""
        # Send a few messages
        for i in range(3):
            await client.post(
                f"/api/bus/{running_project['id']}/send",
                json={
                    "from_agent": "Claude-1",
                    "to_agent": f"Claude-{i+2}",
                    "channel": "general",
                    "priority": "normal",
                    "msg_type": "info",
                    "body": f"Message {i}",
                },
            )

        resp = await client.get(
            f"/api/bus/{running_project['id']}/messages",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 3

    async def test_get_all_messages_filter_channel(self, client, running_project):
        """Filter all messages by channel."""
        # Send to different channels
        await client.post(
            f"/api/bus/{running_project['id']}/send",
            json={
                "from_agent": "Claude-1",
                "to_agent": "Claude-2",
                "channel": "critical",
                "priority": "high",
                "msg_type": "blocker",
                "body": "Critical issue",
            },
        )
        await client.post(
            f"/api/bus/{running_project['id']}/send",
            json={
                "from_agent": "Claude-1",
                "to_agent": "Claude-2",
                "channel": "general",
                "priority": "normal",
                "msg_type": "info",
                "body": "Normal message",
            },
        )

        resp = await client.get(
            f"/api/bus/{running_project['id']}/messages?channel=critical",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert all(m["channel"] == "critical" for m in data["messages"])


class TestBusPriorityOrdering:
    """Tests for priority ordering in inbox."""

    async def test_critical_priority_first(self, client, running_project):
        """Critical priority messages appear first in inbox."""
        # Send low priority first
        await client.post(
            f"/api/bus/{running_project['id']}/send",
            json={
                "from_agent": "Claude-1",
                "to_agent": "Claude-2",
                "channel": "general",
                "priority": "low",
                "msg_type": "info",
                "body": "Low priority",
            },
        )
        # Send critical second
        await client.post(
            f"/api/bus/{running_project['id']}/send",
            json={
                "from_agent": "Claude-1",
                "to_agent": "Claude-2",
                "channel": "critical",
                "priority": "critical",
                "msg_type": "blocker",
                "body": "Critical issue",
            },
        )

        resp = await client.get(
            f"/api/bus/{running_project['id']}/inbox/Claude-2",
        )
        assert resp.status_code == 200
        data = resp.json()
        messages = data["messages"]
        assert len(messages) >= 2
        # Critical should be first
        assert messages[0]["priority"] == "critical"
