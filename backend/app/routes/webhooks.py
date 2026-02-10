"""Webhook notification endpoints - configurable POST webhooks on swarm events."""

import hashlib
import hmac
import ipaddress
import json
import logging
import time
from typing import Optional
from urllib.parse import urlparse

import aiosqlite
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..database import get_db

logger = logging.getLogger("latent.webhooks")

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# Supported webhook event types
WEBHOOK_EVENTS = {"swarm_launched", "swarm_stopped", "swarm_crashed", "swarm_error"}


class WebhookCreate(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    events: list[str] = Field(default_factory=lambda: list(WEBHOOK_EVENTS))
    secret: Optional[str] = Field(None, max_length=200)
    project_id: Optional[int] = None  # None = all projects


class WebhookUpdate(BaseModel):
    url: Optional[str] = Field(None, min_length=1, max_length=2000)
    events: Optional[list[str]] = None
    secret: Optional[str] = Field(None, max_length=200)
    enabled: Optional[bool] = None


def _row_to_dict(row: aiosqlite.Row) -> dict:
    """Convert a webhook row to a response dict."""
    d = dict(row)
    try:
        d["events"] = json.loads(d["events"])
    except (json.JSONDecodeError, TypeError):
        d["events"] = list(WEBHOOK_EVENTS)
    # Don't expose secret in responses
    d["has_secret"] = bool(d.pop("secret", None))
    return d


def _validate_webhook_url(url: str) -> None:
    """Validate webhook URL to prevent SSRF attacks."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "Webhook URL must use http or https scheme")
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(400, "Webhook URL must have a valid hostname")
    # Block localhost and loopback
    if hostname.lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise HTTPException(400, "Webhook URL cannot target localhost")
    # Block private/reserved IP ranges
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise HTTPException(400, "Webhook URL cannot target private/reserved IP addresses")
    except ValueError:
        pass  # hostname is a domain name, not an IP - that's fine


def _sign_payload(payload: str, secret: str) -> str:
    """Create HMAC-SHA256 signature for a webhook payload."""
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


async def _deliver_webhook(webhook_id: int, url: str, payload: dict, secret: str | None):
    """Deliver a webhook with optional HMAC signing. Runs as background task."""
    import httpx

    body = json.dumps(payload, default=str)
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Webhook-Signature"] = f"sha256={_sign_payload(body, secret)}"

    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, content=body, headers=headers, timeout=10.0)
                if resp.status_code < 400:
                    logger.info("Webhook %d delivered to %s (status=%d)", webhook_id, url, resp.status_code)
                    return
                logger.warning("Webhook %d got %d from %s (attempt %d/%d)",
                               webhook_id, resp.status_code, url, attempt + 1, max_retries)
        except Exception as e:
            logger.warning("Webhook %d delivery failed to %s: %s (attempt %d/%d)",
                           webhook_id, url, e, attempt + 1, max_retries)

        if attempt < max_retries - 1:
            import asyncio
            await asyncio.sleep(2 ** attempt)  # 1s, 2s backoff

    logger.error("Webhook %d failed after %d attempts to %s", webhook_id, max_retries, url)


async def emit_webhook_event(event: str, project_id: int, payload: dict,
                              background_tasks: BackgroundTasks | None = None):
    """Emit a webhook event to all matching registered webhooks.

    Called from swarm.py on launch/stop/crash events.
    """
    from ..database import get_db, DB_PATH

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(
                "SELECT * FROM webhooks WHERE enabled = 1"
            )).fetchall()

        for row in rows:
            wh = dict(row)
            try:
                events = json.loads(wh["events"])
            except (json.JSONDecodeError, TypeError):
                events = list(WEBHOOK_EVENTS)

            if event not in events:
                continue
            # Filter by project_id if webhook is project-specific
            if wh["project_id"] is not None and wh["project_id"] != project_id:
                continue

            full_payload = {
                "event": event,
                "project_id": project_id,
                "timestamp": time.time(),
                "webhook_id": wh["id"],
                **payload,
            }

            if background_tasks:
                background_tasks.add_task(
                    _deliver_webhook, wh["id"], wh["url"], full_payload, wh["secret"]
                )
            else:
                # Fire-and-forget via asyncio task
                import asyncio
                asyncio.create_task(
                    _deliver_webhook(wh["id"], wh["url"], full_payload, wh["secret"])
                )
    except Exception:
        logger.error("Failed to emit webhook event %s", event, exc_info=True)


@router.post("", status_code=201)
async def create_webhook(body: WebhookCreate, db: aiosqlite.Connection = Depends(get_db)):
    """Register a new webhook endpoint."""
    # Validate URL (SSRF prevention)
    _validate_webhook_url(body.url)
    # Validate event types
    invalid = set(body.events) - WEBHOOK_EVENTS
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid events: {', '.join(invalid)}. "
                            f"Valid: {', '.join(sorted(WEBHOOK_EVENTS))}")

    events_json = json.dumps(body.events)
    cursor = await db.execute(
        "INSERT INTO webhooks (url, events, secret, project_id) VALUES (?, ?, ?, ?)",
        (body.url, events_json, body.secret, body.project_id),
    )
    await db.commit()
    row = await (await db.execute("SELECT * FROM webhooks WHERE id = ?", (cursor.lastrowid,))).fetchone()
    return _row_to_dict(row)


@router.get("")
async def list_webhooks(db: aiosqlite.Connection = Depends(get_db)):
    """List all registered webhooks."""
    rows = await (await db.execute(
        "SELECT * FROM webhooks ORDER BY created_at DESC, id DESC"
    )).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.get("/{webhook_id}")
async def get_webhook(webhook_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Get a webhook by ID."""
    row = await (await db.execute("SELECT * FROM webhooks WHERE id = ?", (webhook_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return _row_to_dict(row)


@router.patch("/{webhook_id}")
async def update_webhook(webhook_id: int, body: WebhookUpdate, db: aiosqlite.Connection = Depends(get_db)):
    """Update a webhook."""
    row = await (await db.execute("SELECT * FROM webhooks WHERE id = ?", (webhook_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Webhook not found")

    updates = []
    params = []
    if body.url is not None:
        _validate_webhook_url(body.url)
        updates.append("url = ?")
        params.append(body.url)
    if body.events is not None:
        invalid = set(body.events) - WEBHOOK_EVENTS
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid events: {', '.join(invalid)}")
        updates.append("events = ?")
        params.append(json.dumps(body.events))
    if body.secret is not None:
        updates.append("secret = ?")
        params.append(body.secret)
    if body.enabled is not None:
        updates.append("enabled = ?")
        params.append(1 if body.enabled else 0)

    if updates:
        updates.append("updated_at = datetime('now')")
        params.append(webhook_id)
        await db.execute(
            f"UPDATE webhooks SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        await db.commit()

    row = await (await db.execute("SELECT * FROM webhooks WHERE id = ?", (webhook_id,))).fetchone()
    return _row_to_dict(row)


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(webhook_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Delete a webhook."""
    row = await (await db.execute("SELECT * FROM webhooks WHERE id = ?", (webhook_id,))).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await db.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
    await db.commit()
    return Response(status_code=204)
