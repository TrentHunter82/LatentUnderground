"""Inter-agent message bus API.

Provides reliable message passing between agents, humans, and the system.
Replaces unreliable file-based inbox polling with database-backed message queue.
"""

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from ..database import get_db
from ..models.bus import (
    BusSendRequest,
    BusSendOut,
    BusMessageOut,
    BusInboxOut,
    BusAckRequest,
    BusAckOut,
    BusChannelOut,
)
from ..models.responses import ErrorDetail
from .websocket import manager as ws_manager

logger = logging.getLogger("latent.bus")

router = APIRouter(prefix="/api/bus", tags=["bus"])

_404 = {404: {"model": ErrorDetail}}


def _row_to_message(row: aiosqlite.Row) -> BusMessageOut:
    """Convert a database row to a BusMessageOut model."""
    return BusMessageOut(
        id=row["id"],
        project_id=row["project_id"],
        from_agent=row["from_agent"],
        to_agent=row["to_agent"],
        channel=row["channel"],
        priority=row["priority"],
        msg_type=row["msg_type"],
        body=row["body"],
        thread_id=row["thread_id"],
        created_at=row["created_at"],
        acked_at=row["acked_at"],
        acked_by=row["acked_by"],
    )


async def _get_project_folder(db: aiosqlite.Connection, project_id: int) -> Path:
    """Get project folder path, raising 404 if not found."""
    row = await (
        await db.execute("SELECT folder_path FROM projects WHERE id = ?", (project_id,))
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return Path(row["folder_path"])


async def _get_current_run_id(db: aiosqlite.Connection, project_id: int) -> Optional[int]:
    """Get the current running swarm run_id if any."""
    row = await (
        await db.execute(
            "SELECT id FROM swarm_runs WHERE project_id = ? AND status = 'running' "
            "ORDER BY started_at DESC LIMIT 1",
            (project_id,),
        )
    ).fetchone()
    return row["id"] if row else None


def _create_attention_file(folder: Path, to_agent: str, message_id: str):
    """Create attention file for high-priority message delivery.

    Agents check for this file before each task to detect urgent messages.
    For broadcasts (to_agent='all'), creates attention files for all agents
    found in the heartbeats directory, falling back to standard agent names.
    """
    attention_dir = folder / ".claude" / "attention"
    attention_dir.mkdir(parents=True, exist_ok=True)

    content = f"{message_id}\n{datetime.now().isoformat()}"

    if to_agent == "all":
        # Discover agents from heartbeats directory (dynamic) or use defaults
        heartbeats_dir = folder / ".claude" / "heartbeats"
        if heartbeats_dir.exists():
            agent_names = [f.stem for f in heartbeats_dir.glob("*.heartbeat")]
        else:
            agent_names = []
        # Fall back to standard agents if none found
        if not agent_names:
            agent_names = ["Claude-1", "Claude-2", "Claude-3", "Claude-4"]
        for agent_name in agent_names:
            attention_file = attention_dir / f"{agent_name}.attention"
            attention_file.write_text(content, encoding="utf-8")
    else:
        attention_file = attention_dir / f"{to_agent}.attention"
        attention_file.write_text(content, encoding="utf-8")


async def _count_messages(
    db: aiosqlite.Connection,
    conditions: list[str],
    params: list,
) -> int:
    """Count messages matching conditions (excludes LIMIT param from params)."""
    count_query = f"""
        SELECT COUNT(*) as cnt FROM bus_messages
        WHERE {' AND '.join(conditions)}
    """
    # params[:-1] excludes the LIMIT value added at the end
    count_row = await (await db.execute(count_query, params[:-1])).fetchone()
    return count_row["cnt"] if count_row else 0


# ---------------------------------------------------------------------------
# POST /{project_id}/send — Send a message to the bus
# ---------------------------------------------------------------------------

@router.post(
    "/{project_id}/send",
    response_model=BusSendOut,
    status_code=201,
    summary="Send a message",
    responses=_404,
)
async def send_message(
    project_id: int,
    req: BusSendRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Send a message to an agent, all agents, or a channel.

    - **to_agent**: Agent name (e.g., 'Claude-2'), 'all' for broadcast,
      or 'channel:<name>' to post to a channel.
    - **channel**: Message channel for categorization.
    - **priority**: 'critical' creates an attention file for immediate pickup.
    """
    # Validate project exists and get folder path
    folder = await _get_project_folder(db, project_id)
    run_id = await _get_current_run_id(db, project_id)

    # Generate message ID
    message_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()

    # Insert message into database
    await db.execute(
        """INSERT INTO bus_messages
           (id, project_id, run_id, from_agent, to_agent, channel, priority, msg_type, body, thread_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            message_id,
            project_id,
            run_id,
            req.from_agent,
            req.to_agent,
            req.channel,
            req.priority,
            req.msg_type,
            req.body,
            req.thread_id,
            created_at,
        ),
    )
    await db.commit()

    # Create attention file for critical/high priority messages
    if req.priority in ("critical", "high"):
        try:
            _create_attention_file(folder, req.to_agent, message_id)
        except OSError as e:
            logger.warning("Failed to create attention file: %s", e)

    # Broadcast via WebSocket for real-time UI updates
    await ws_manager.broadcast({
        "type": "bus_message",
        "project_id": project_id,
        "message": {
            "id": message_id,
            "from_agent": req.from_agent,
            "to_agent": req.to_agent,
            "channel": req.channel,
            "priority": req.priority,
            "msg_type": req.msg_type,
            "body": req.body[:200] + "..." if len(req.body) > 200 else req.body,
            "created_at": created_at,
        },
    })

    logger.info(
        "Message sent: %s -> %s [%s/%s]",
        req.from_agent,
        req.to_agent,
        req.channel,
        req.priority,
    )

    return BusSendOut(id=message_id, status="sent")


# ---------------------------------------------------------------------------
# GET /{project_id}/inbox/{agent} — Get pending messages for an agent
# ---------------------------------------------------------------------------

@router.get(
    "/{project_id}/inbox/{agent}",
    response_model=BusInboxOut,
    summary="Get agent inbox",
    responses=_404,
)
async def get_inbox(
    project_id: int,
    agent: str,
    since: Optional[str] = Query(
        None,
        description="ISO timestamp to filter messages created after this time",
    ),
    unacked_only: bool = Query(
        True,
        description="Only return messages not yet acknowledged",
    ),
    limit: int = Query(50, ge=1, le=500, description="Maximum messages to return"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Get pending messages for an agent.

    Returns messages where:
    - to_agent matches the agent name, OR
    - to_agent is 'all' (broadcast), OR
    - to_agent starts with 'channel:' (channel post)
    """
    # Validate project exists
    _ = await _get_project_folder(db, project_id)

    # Build query conditions
    conditions = ["project_id = ?"]
    params: list = [project_id]

    # Match direct messages, broadcasts, and channel posts
    conditions.append("(to_agent = ? OR to_agent = 'all' OR to_agent LIKE 'channel:%')")
    params.append(agent)

    if since:
        conditions.append("created_at > ?")
        params.append(since)

    if unacked_only:
        # For broadcasts/channels, check if THIS agent has acked
        # For direct messages, check acked_at is NULL
        conditions.append(
            "(acked_at IS NULL OR (to_agent IN ('all') AND acked_by IS NULL))"
        )

    params.append(limit)

    query = f"""
        SELECT * FROM bus_messages
        WHERE {' AND '.join(conditions)}
        ORDER BY
            CASE priority
                WHEN 'critical' THEN 0
                WHEN 'high' THEN 1
                WHEN 'normal' THEN 2
                WHEN 'low' THEN 3
            END,
            created_at DESC, id DESC
        LIMIT ?
    """

    rows = await (await db.execute(query, params)).fetchall()
    total = await _count_messages(db, conditions, params)
    messages = [_row_to_message(row) for row in rows]

    return BusInboxOut(
        project_id=project_id,
        agent=agent,
        messages=messages,
        total=total,
    )


# ---------------------------------------------------------------------------
# POST /{project_id}/ack/{message_id} — Acknowledge a message
# ---------------------------------------------------------------------------

@router.post(
    "/{project_id}/ack/{message_id}",
    response_model=BusAckOut,
    summary="Acknowledge a message",
    responses=_404,
)
async def ack_message(
    project_id: int,
    message_id: str,
    agent: str = Query(..., description="Agent acknowledging the message"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Mark a message as acknowledged by an agent.

    For broadcast messages (to_agent='all'), stores the acknowledging agent
    in acked_by but doesn't prevent other agents from seeing the message.
    """
    # Check message exists and belongs to this project
    row = await (
        await db.execute(
            "SELECT id, to_agent, acked_at FROM bus_messages WHERE id = ? AND project_id = ?",
            (message_id, project_id),
        )
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Message not found")

    # Already acknowledged?
    if row["acked_at"]:
        return BusAckOut(id=message_id, acked=False)

    # Update acknowledgment
    acked_at = datetime.now().isoformat()
    await db.execute(
        "UPDATE bus_messages SET acked_at = ?, acked_by = ? WHERE id = ?",
        (acked_at, agent, message_id),
    )
    await db.commit()

    logger.debug("Message %s acknowledged by %s", message_id, agent)

    return BusAckOut(id=message_id, acked=True)


# ---------------------------------------------------------------------------
# GET /{project_id}/channels/{channel}/messages — Get messages in a channel
# ---------------------------------------------------------------------------

@router.get(
    "/{project_id}/channels/{channel}/messages",
    response_model=BusChannelOut,
    summary="Get channel messages",
    responses=_404,
)
async def get_channel_messages(
    project_id: int,
    channel: str,
    since: Optional[str] = Query(
        None,
        description="ISO timestamp to filter messages created after this time",
    ),
    limit: int = Query(50, ge=1, le=500, description="Maximum messages to return"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Get messages posted to a specific channel.

    Channel messages are visible to all agents and don't require acknowledgment.
    """
    # Validate project exists
    _ = await _get_project_folder(db, project_id)

    # Build query
    conditions = ["project_id = ?", "channel = ?"]
    params: list = [project_id, channel]

    if since:
        conditions.append("created_at > ?")
        params.append(since)

    params.append(limit)

    query = f"""
        SELECT * FROM bus_messages
        WHERE {' AND '.join(conditions)}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
    """

    rows = await (await db.execute(query, params)).fetchall()
    total = await _count_messages(db, conditions, params)
    messages = [_row_to_message(row) for row in rows]

    return BusChannelOut(
        project_id=project_id,
        channel=channel,
        messages=messages,
        total=total,
    )


# ---------------------------------------------------------------------------
# GET /{project_id}/messages — Get all messages (for UI message feed)
# ---------------------------------------------------------------------------

@router.get(
    "/{project_id}/messages",
    response_model=BusChannelOut,
    summary="Get all messages",
    responses=_404,
)
async def get_all_messages(
    project_id: int,
    since: Optional[str] = Query(
        None,
        description="ISO timestamp to filter messages created after this time",
    ),
    channel: Optional[str] = Query(None, description="Filter by channel"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum messages to return"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Get all messages for a project (for UI message feed).

    Supports filtering by channel and priority.
    """
    # Validate project exists
    _ = await _get_project_folder(db, project_id)

    # Build query
    conditions = ["project_id = ?"]
    params: list = [project_id]

    if since:
        conditions.append("created_at > ?")
        params.append(since)

    if channel:
        conditions.append("channel = ?")
        params.append(channel)

    if priority:
        conditions.append("priority = ?")
        params.append(priority)

    params.append(limit)

    query = f"""
        SELECT * FROM bus_messages
        WHERE {' AND '.join(conditions)}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
    """

    rows = await (await db.execute(query, params)).fetchall()
    total = await _count_messages(db, conditions, params)
    messages = [_row_to_message(row) for row in rows]

    # Reuse BusChannelOut but with "all" as channel
    return BusChannelOut(
        project_id=project_id,
        channel=channel or "all",
        messages=messages,
        total=total,
    )
