"""Webhook integration tests - HMAC verification, delivery, event filtering, and edge cases.

Goes deeper than test_phase10_features.py webhook CRUD coverage to test the
actual signing, delivery retry logic, event filtering, and payload structure.
"""

import asyncio
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest


# ---------------------------------------------------------------------------
# TestWebhookHMACVerification
# ---------------------------------------------------------------------------

class TestWebhookHMACVerification:
    """Verify HMAC-SHA256 signing produces correct, deterministic signatures."""

    @pytest.mark.asyncio
    async def test_sign_payload_deterministic(self):
        """Same input produces the same signature every time."""
        from app.routes.webhooks import _sign_payload

        payload = '{"event": "swarm_launched", "project_id": 1}'
        secret = "test-secret-key"
        sig1 = _sign_payload(payload, secret)
        sig2 = _sign_payload(payload, secret)
        assert sig1 == sig2
        assert isinstance(sig1, str)
        assert len(sig1) == 64  # SHA256 hex digest length

    @pytest.mark.asyncio
    async def test_sign_payload_different_secrets(self):
        """Different secrets produce different signatures for the same payload."""
        from app.routes.webhooks import _sign_payload

        payload = '{"event": "swarm_launched"}'
        sig_a = _sign_payload(payload, "secret-a")
        sig_b = _sign_payload(payload, "secret-b")
        assert sig_a != sig_b

    @pytest.mark.asyncio
    async def test_sign_payload_different_payloads(self):
        """Different payloads produce different signatures with the same secret."""
        from app.routes.webhooks import _sign_payload

        secret = "shared-secret"
        sig_a = _sign_payload('{"event": "swarm_launched"}', secret)
        sig_b = _sign_payload('{"event": "swarm_stopped"}', secret)
        assert sig_a != sig_b

    @pytest.mark.asyncio
    async def test_verify_signature_roundtrip(self):
        """Sign a payload then verify it matches using hmac.compare_digest."""
        from app.routes.webhooks import _sign_payload

        payload = '{"project_id": 42, "status": "ok"}'
        secret = "roundtrip-secret"
        signature = _sign_payload(payload, secret)

        # Manually compute expected HMAC to verify
        expected = hmac.new(
            secret.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()

        assert hmac.compare_digest(signature, expected)


# ---------------------------------------------------------------------------
# TestWebhookDeliveryMock
# ---------------------------------------------------------------------------

def _make_mock_httpx_client(post_side_effect=None, post_return=None):
    """Build a mock httpx module whose AsyncClient context manager returns a mock client.

    The mock client's .post is configured with the given side_effect or return_value.
    """
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    if post_side_effect is not None:
        mock_client.post = AsyncMock(side_effect=post_side_effect)
    else:
        mock_client.post = AsyncMock(
            return_value=post_return or MagicMock(status_code=200)
        )

    mock_httpx_module = MagicMock()
    mock_httpx_module.AsyncClient.return_value = mock_client
    return mock_httpx_module, mock_client


class TestWebhookDeliveryMock:
    """Test _deliver_webhook with mocked httpx to verify retry and header logic.

    Because httpx is imported *inside* _deliver_webhook via ``import httpx``,
    we patch it at the sys.modules / builtins level so the local import picks
    up our mock.  The simplest reliable way is ``patch.dict("sys.modules", ...)``.
    """

    @pytest.mark.asyncio
    async def test_deliver_webhook_success(self):
        """Successful delivery (200) should call post once and return."""
        from app.routes.webhooks import _deliver_webhook

        mock_httpx, mock_client = _make_mock_httpx_client(
            post_return=MagicMock(status_code=200)
        )

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            await _deliver_webhook(
                webhook_id=1,
                url="https://example.com/hook",
                payload={"event": "swarm_launched"},
                secret=None,
            )

        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_deliver_webhook_with_signature(self):
        """When a secret is provided, X-Webhook-Signature header must be set."""
        from app.routes.webhooks import _deliver_webhook, _sign_payload

        mock_httpx, mock_client = _make_mock_httpx_client(
            post_return=MagicMock(status_code=200)
        )

        payload = {"event": "swarm_launched", "project_id": 5}
        secret = "my-webhook-secret"

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            await _deliver_webhook(
                webhook_id=2,
                url="https://example.com/signed",
                payload=payload,
                secret=secret,
            )

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        # headers is passed as keyword arg
        headers = call_kwargs.kwargs.get("headers", {})
        assert "X-Webhook-Signature" in headers

        # Verify the signature value matches what _sign_payload would produce
        body = json.dumps(payload, default=str)
        expected_sig = f"sha256={_sign_payload(body, secret)}"
        assert headers["X-Webhook-Signature"] == expected_sig

    @pytest.mark.asyncio
    async def test_deliver_webhook_retries_on_500(self):
        """A 500 response triggers retry; should attempt 3 times total."""
        from app.routes.webhooks import _deliver_webhook

        mock_httpx, mock_client = _make_mock_httpx_client(
            post_return=MagicMock(status_code=500)
        )

        with patch.dict("sys.modules", {"httpx": mock_httpx}), \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await _deliver_webhook(
                webhook_id=3,
                url="https://example.com/failing",
                payload={"event": "swarm_error"},
                secret=None,
            )

        assert mock_client.post.call_count == 3
        # Backoff sleeps: 2^0=1s, 2^1=2s (only between retries, so 2 sleeps)
        assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_deliver_webhook_retries_on_connection_error(self):
        """A connection error triggers retry; should attempt 3 times total."""
        from app.routes.webhooks import _deliver_webhook

        mock_httpx, mock_client = _make_mock_httpx_client(
            post_side_effect=ConnectionError("refused")
        )

        with patch.dict("sys.modules", {"httpx": mock_httpx}), \
             patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await _deliver_webhook(
                webhook_id=4,
                url="https://unreachable.example.com/hook",
                payload={"event": "swarm_crashed"},
                secret=None,
            )

        assert mock_client.post.call_count == 3
        assert mock_sleep.call_count == 2


# ---------------------------------------------------------------------------
# TestWebhookEventFiltering
# ---------------------------------------------------------------------------

class TestWebhookEventFiltering:
    """Test that webhooks are correctly filtered by event type and project."""

    @pytest.mark.asyncio
    async def test_create_webhook_with_specific_events(self, client):
        """Create a webhook subscribed to only swarm_launched and verify stored events."""
        resp = await client.post("/api/webhooks", json={
            "url": "https://example.com/launched-only",
            "events": ["swarm_launched"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["events"] == ["swarm_launched"]

        # Verify via GET
        wid = data["id"]
        resp2 = await client.get(f"/api/webhooks/{wid}")
        assert resp2.status_code == 200
        assert resp2.json()["events"] == ["swarm_launched"]

    @pytest.mark.asyncio
    async def test_webhook_filters_by_event_type(self, client, tmp_db):
        """Create two webhooks for different events; emit one event and verify only matching fires."""
        from app.routes.webhooks import emit_webhook_event

        # Create webhook for swarm_launched
        r1 = await client.post("/api/webhooks", json={
            "url": "https://launch-listener.example.com",
            "events": ["swarm_launched"],
        })
        assert r1.status_code == 201

        # Create webhook for swarm_stopped
        r2 = await client.post("/api/webhooks", json={
            "url": "https://stop-listener.example.com",
            "events": ["swarm_stopped"],
        })
        assert r2.status_code == 201

        launched_id = r1.json()["id"]
        stopped_id = r2.json()["id"]

        delivered_ids = []

        async def fake_deliver(webhook_id, url, payload, secret):
            delivered_ids.append(webhook_id)

        with patch("app.routes.webhooks._deliver_webhook", new=fake_deliver), \
             patch("app.database.DB_PATH", tmp_db):
            await emit_webhook_event(
                event="swarm_launched",
                project_id=1,
                payload={"detail": "test"},
            )
            # Yield to event loop so asyncio.create_task fires
            await asyncio.sleep(0)

        assert launched_id in delivered_ids
        assert stopped_id not in delivered_ids

    @pytest.mark.asyncio
    async def test_webhook_filters_by_project_id(self, client, tmp_db, created_project):
        """Webhook scoped to project_id=X should not fire for project_id=Y."""
        from app.routes.webhooks import emit_webhook_event

        project_id = created_project["id"]

        # Create webhook scoped to this project
        r1 = await client.post("/api/webhooks", json={
            "url": "https://project-scoped.example.com",
            "events": ["swarm_launched"],
            "project_id": project_id,
        })
        assert r1.status_code == 201
        scoped_id = r1.json()["id"]

        delivered_ids = []

        async def fake_deliver(webhook_id, url, payload, secret):
            delivered_ids.append(webhook_id)

        # Emit event for a DIFFERENT project ID
        other_project_id = project_id + 999
        with patch("app.routes.webhooks._deliver_webhook", new=fake_deliver), \
             patch("app.database.DB_PATH", tmp_db):
            await emit_webhook_event(
                event="swarm_launched",
                project_id=other_project_id,
                payload={"detail": "wrong project"},
            )
            # Yield to event loop so asyncio.create_task fires
            await asyncio.sleep(0)

        assert scoped_id not in delivered_ids


# ---------------------------------------------------------------------------
# TestWebhookEmitIntegration
# ---------------------------------------------------------------------------

class TestWebhookEmitIntegration:
    """Test emit_webhook_event integration with the database and delivery."""

    @pytest.mark.asyncio
    async def test_emit_webhook_event_queries_enabled_webhooks(self, tmp_db):
        """Insert an enabled webhook directly in DB; emit event; verify delivery attempted."""
        from app.routes.webhooks import emit_webhook_event

        # Insert webhook directly into the test DB
        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO webhooks (url, events, secret, project_id, enabled) "
                "VALUES (?, ?, ?, ?, ?)",
                ("https://direct-insert.example.com",
                 json.dumps(["swarm_launched"]),
                 None, None, 1),
            )
            await db.commit()

        delivered = []

        async def fake_deliver(webhook_id, url, payload, secret):
            delivered.append({"webhook_id": webhook_id, "url": url, "payload": payload})

        with patch("app.routes.webhooks._deliver_webhook", new=fake_deliver), \
             patch("app.database.DB_PATH", tmp_db):
            await emit_webhook_event(
                event="swarm_launched",
                project_id=10,
                payload={"info": "test emit"},
            )
            await asyncio.sleep(0)

        assert len(delivered) == 1
        assert delivered[0]["url"] == "https://direct-insert.example.com"

    @pytest.mark.asyncio
    async def test_emit_webhook_event_skips_disabled(self, tmp_db):
        """A disabled webhook (enabled=0) should not be delivered."""
        from app.routes.webhooks import emit_webhook_event

        async with aiosqlite.connect(tmp_db) as db:
            await db.execute(
                "INSERT INTO webhooks (url, events, secret, project_id, enabled) "
                "VALUES (?, ?, ?, ?, ?)",
                ("https://disabled.example.com",
                 json.dumps(["swarm_launched"]),
                 None, None, 0),
            )
            await db.commit()

        delivered = []

        async def fake_deliver(webhook_id, url, payload, secret):
            delivered.append(webhook_id)

        with patch("app.routes.webhooks._deliver_webhook", new=fake_deliver), \
             patch("app.database.DB_PATH", tmp_db):
            await emit_webhook_event(
                event="swarm_launched",
                project_id=10,
                payload={"info": "should not fire"},
            )
            await asyncio.sleep(0)

        assert len(delivered) == 0

    @pytest.mark.asyncio
    async def test_emit_webhook_event_includes_metadata(self, tmp_db):
        """Emitted payload should contain event, project_id, timestamp, and webhook_id."""
        from app.routes.webhooks import emit_webhook_event

        async with aiosqlite.connect(tmp_db) as db:
            cursor = await db.execute(
                "INSERT INTO webhooks (url, events, secret, project_id, enabled) "
                "VALUES (?, ?, ?, ?, ?)",
                ("https://meta.example.com",
                 json.dumps(["swarm_stopped"]),
                 "meta-secret", None, 1),
            )
            inserted_id = cursor.lastrowid
            await db.commit()

        captured_payloads = []

        async def fake_deliver(webhook_id, url, payload, secret):
            captured_payloads.append(payload)

        before = time.time()

        with patch("app.routes.webhooks._deliver_webhook", new=fake_deliver), \
             patch("app.database.DB_PATH", tmp_db):
            await emit_webhook_event(
                event="swarm_stopped",
                project_id=77,
                payload={"extra": "data"},
            )
            await asyncio.sleep(0)

        after = time.time()

        assert len(captured_payloads) == 1
        p = captured_payloads[0]
        assert p["event"] == "swarm_stopped"
        assert p["project_id"] == 77
        assert p["webhook_id"] == inserted_id
        assert "timestamp" in p
        assert before <= p["timestamp"] <= after
        # User-supplied payload fields are merged in
        assert p["extra"] == "data"


# ---------------------------------------------------------------------------
# TestWebhookAPIEdgeCases
# ---------------------------------------------------------------------------

class TestWebhookAPIEdgeCases:
    """Edge-case tests for the webhook REST API."""

    @pytest.mark.asyncio
    async def test_webhook_secret_not_exposed_in_list(self, client):
        """Create a webhook with a secret; GET list should return has_secret=True but no secret field."""
        await client.post("/api/webhooks", json={
            "url": "https://secret-test.example.com",
            "secret": "super-secret-value",
            "events": ["swarm_launched"],
        })

        resp = await client.get("/api/webhooks")
        assert resp.status_code == 200
        webhooks = resp.json()
        assert len(webhooks) >= 1

        wh = webhooks[0]
        assert wh["has_secret"] is True
        assert "secret" not in wh

    @pytest.mark.asyncio
    async def test_webhook_update_events_validation(self, client):
        """PATCH with an invalid event name should return 400."""
        create_resp = await client.post("/api/webhooks", json={
            "url": "https://valid.example.com",
            "events": ["swarm_launched"],
        })
        assert create_resp.status_code == 201
        wid = create_resp.json()["id"]

        resp = await client.patch(f"/api/webhooks/{wid}", json={
            "events": ["swarm_launched", "totally_fake_event"],
        })
        assert resp.status_code == 400
        assert "Invalid events" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# TestWebhookHMACEdgeCases
# ---------------------------------------------------------------------------

class TestWebhookHMACEdgeCases:
    """Edge cases for HMAC signing: tampered payloads, empty payloads, unicode."""

    @pytest.mark.asyncio
    async def test_tampered_payload_fails_verification(self):
        """If the payload is modified after signing, verification must fail."""
        from app.routes.webhooks import _sign_payload

        secret = "tamper-test-secret"
        original = '{"event": "swarm_launched", "project_id": 1}'
        tampered = '{"event": "swarm_launched", "project_id": 2}'

        sig_original = _sign_payload(original, secret)
        sig_tampered = _sign_payload(tampered, secret)

        assert not hmac.compare_digest(sig_original, sig_tampered)

    @pytest.mark.asyncio
    async def test_sign_empty_payload(self):
        """Empty payload should still produce a valid 64-char hex signature."""
        from app.routes.webhooks import _sign_payload

        sig = _sign_payload("", "secret")
        assert len(sig) == 64
        expected = hmac.new(b"secret", b"", hashlib.sha256).hexdigest()
        assert hmac.compare_digest(sig, expected)

    @pytest.mark.asyncio
    async def test_sign_unicode_payload(self):
        """Unicode characters in payload should be signed correctly."""
        from app.routes.webhooks import _sign_payload

        payload = '{"name": "projet d\u00e9ploiement", "emoji": "\u2605\u2606"}'
        sig = _sign_payload(payload, "unicode-secret")
        assert len(sig) == 64

        # Verify deterministic
        sig2 = _sign_payload(payload, "unicode-secret")
        assert sig == sig2

    @pytest.mark.asyncio
    async def test_reserialization_changes_signature(self):
        """Re-serializing JSON (different formatting) should produce different signature.

        This documents why raw body signing matters: JSON serialization is not
        deterministic (key ordering, whitespace can vary).
        """
        from app.routes.webhooks import _sign_payload

        body = '{"event":"swarm_launched","project_id":1}'
        secret = "format-test"
        sig_compact = _sign_payload(body, secret)

        # Re-serialize with different formatting
        reparsed = json.dumps(json.loads(body), indent=2)
        sig_formatted = _sign_payload(reparsed, secret)

        assert sig_compact != sig_formatted

    @pytest.mark.asyncio
    async def test_sign_large_payload(self):
        """Large payloads should be signed without issues."""
        from app.routes.webhooks import _sign_payload

        # 100KB payload
        payload = json.dumps({"data": "x" * 100_000})
        sig = _sign_payload(payload, "large-secret")
        assert len(sig) == 64
