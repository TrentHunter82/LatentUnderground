"""Pydantic models for the inter-agent message bus.

These models define the schema for sending, receiving, and acknowledging
messages between agents, humans, and the system via the message bus API.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# --- Type aliases for validation ---

ChannelType = Literal["general", "critical", "review", "handoff", "lessons"]
PriorityType = Literal["low", "normal", "high", "critical"]
MessageType = Literal["info", "request", "response", "blocker", "handoff", "lesson"]


# --- Request Models ---

class BusSendRequest(BaseModel):
    """Request body for POST /api/bus/{project_id}/send."""

    from_agent: str = Field(
        min_length=1,
        max_length=50,
        description="Sender identifier (e.g., 'Claude-1', 'human', 'system')",
    )
    to_agent: str = Field(
        min_length=1,
        max_length=50,
        description="Recipient: agent name, 'all' for broadcast, or 'channel:<name>'",
    )
    channel: ChannelType = Field(
        default="general",
        description="Message channel: general, critical, review, handoff, lessons",
    )
    priority: PriorityType = Field(
        default="normal",
        description="Priority level: low, normal, high, critical",
    )
    msg_type: MessageType = Field(
        default="info",
        description="Message type: info, request, response, blocker, handoff, lesson",
    )
    body: str = Field(
        min_length=1,
        max_length=10000,
        description="Message content",
    )
    thread_id: Optional[str] = Field(
        default=None,
        max_length=36,
        description="Optional thread UUID for reply threading",
    )


# --- Response Models ---

class BusMessageOut(BaseModel):
    """Single message in API responses."""

    id: str
    project_id: int
    from_agent: str
    to_agent: str
    channel: str
    priority: str
    msg_type: str
    body: str
    thread_id: Optional[str] = None
    created_at: str
    acked_at: Optional[str] = None
    acked_by: Optional[str] = None


class BusSendOut(BaseModel):
    """Response for POST /api/bus/{project_id}/send."""

    id: str
    status: str


class BusInboxOut(BaseModel):
    """Response for GET /api/bus/{project_id}/inbox/{agent}."""

    project_id: int
    agent: str
    messages: list[BusMessageOut]
    total: int


class BusAckRequest(BaseModel):
    """Request body for POST /api/bus/{project_id}/ack/{message_id}."""

    agent: str = Field(
        min_length=1,
        max_length=50,
        description="Agent acknowledging the message",
    )


class BusAckOut(BaseModel):
    """Response for POST /api/bus/{project_id}/ack/{message_id}."""

    id: str
    acked: bool


class BusChannelOut(BaseModel):
    """Response for GET /api/bus/{project_id}/channels/{channel}/messages."""

    project_id: int
    channel: str
    messages: list[BusMessageOut]
    total: int
