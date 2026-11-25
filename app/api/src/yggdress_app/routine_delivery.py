"""Browser and Android push outboxes for daily routines."""

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import Field, field_validator

from .planning_models import Model
from .security import token_hash


def vapid():
    return tuple(
        os.environ.get("YGGDRAS_VAPID_" + name, "").strip()
        for name in ("PUBLIC_KEY", "PRIVATE_KEY", "SUBJECT")
    )


def provider_endpoint(value: str) -> str:
    url = urlsplit(value)
    host = url.hostname or ""
    # A signed-in browser supplies the destination. Accept only browser push services.
    hosts = (
        "fcm.googleapis.com",
        "updates.push.services.mozilla.com",
        "push.services.mozilla.com",
        "web.push.apple.com",
        "notify.windows.com",
    )
    if (
        url.scheme != "https"
        or url.port not in (443, None)
        or url.username is not None
        or url.password is not None
        or url.fragment
        or not url.path.strip("/")
        or not any(host == provider or host.endswith("." + provider) for provider in hosts)
    ):
        raise ValueError("Unsupported browser notification service.")
    return value


class SubscriptionKeys(Model):
    auth: str = Field(pattern=r"^[A-Za-z0-9_-]{22}={0,2}$")
    p256dh: str = Field(pattern=r"^[A-Za-z0-9_-]{87}=?$")

    @field_validator("p256dh")
    @classmethod
    def public_point(cls, value):
        ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), base64.urlsafe_b64decode(value + "===")
        )
        return value


class Subscription(Model):
    endpoint: str = Field(min_length=1, max_length=2000)
    keys: SubscriptionKeys
    _provider = field_validator("endpoint")(provider_endpoint)


class Ack(Model):
    token: str = Field(pattern=r"^[a-zA-Z0-9_-]{32}\.[a-f0-9]{64}$")
    action: Literal["started", "not_yet"]


class AndroidDevice(Model):
    push_token: str = Field(min_length=10, max_length=4096)


class AndroidAck(Model):
    delivery_id: UUID
    action: Literal["started", "not_yet"]


class AndroidTest(Model):
    device_id: UUID


def firebase_ready():
    from . import voice
    from .side_effects import side_effects_allowed

    return (
        not voice.missing(voice.FIREBASE_VARS)
        and os.path.isfile(os.environ.get("FIREBASE_SERVICE_ACCOUNT_FILE", ""))
        and side_effects_allowed()
    )


def queue_notice(db, *, key: str, escalation_id: UUID | None = None, kind="pre_task"):
    """Enqueue once per enrolled destination in the scheduler transaction."""
    browser_count = db.execute(
        """
        INSERT INTO app.web_push_deliveries(id,subscription,dedupe_key,kind,escalation_id,expires_at)
        SELECT gen_random_uuid(),s.id,%s,%s,%s,now()+interval '4 minutes'
        FROM app.web_push_subscriptions s JOIN app.sessions a ON a.token_hash=s.session_hash
        WHERE a.expires_at>now() ON CONFLICT(subscription,dedupe_key) DO NOTHING
        """,
        (key, kind, escalation_id),
    ).rowcount
    # Incoming calls have their own FCM outbox and native call screen.
    if kind == "incoming_call":
        return browser_count
    android_count = db.execute(
        """
        INSERT INTO app.android_routine_deliveries
            (id,device,dedupe_key,kind,escalation_id,expires_at,action_expires_at)
        SELECT gen_random_uuid(),d.id,%s,%s,%s,
               now()+interval '4 minutes',now()+interval '20 minutes'
        FROM app.routine_android_devices d
        JOIN app.sessions s ON s.token_hash=d.session_hash
        WHERE s.expires_at>now() AND s.password_fingerprint=d.password_fingerprint
        ON CONFLICT(device,dedupe_key) DO NOTHING
        """,
        (key, kind, escalation_id),
    ).rowcount
    return browser_count + android_count


def signature(nonce, key):
    return hmac.new(key.encode(), ("routine-ack-v1:" + nonce).encode(), hashlib.sha256).hexdigest()


def claim(db, fingerprint, key):
    db.execute("""UPDATE app.web_push_deliveries SET status='expired'
               WHERE status IN ('pending','sending') AND expires_at<=now()""")
    row = db.execute(
        """
        SELECT d.*,s.endpoint,s.keys FROM app.web_push_deliveries d
        JOIN app.web_push_subscriptions s ON s.id=d.subscription
        JOIN app.sessions a ON a.token_hash=s.session_hash
        WHERE d.status='pending' AND a.expires_at>now() AND a.password_fingerprint=%s
          AND d.expires_at>now()
        ORDER BY d.expires_at,d.id LIMIT 1 FOR UPDATE OF d SKIP LOCKED
        """,
        (fingerprint,),
    ).fetchone()
    if not row:
        return None
    db.execute("UPDATE app.web_push_deliveries SET status='sending' WHERE id=%s", (row["id"],))
    payload = {"kind": row["kind"], "tag": str(row["id"])}
    if row["escalation_id"] and row["kind"] == "pre_task":
        nonce = secrets.token_urlsafe(24)
        token = nonce + "." + signature(nonce, key)
        db.execute(
            "INSERT INTO app.web_push_tokens(digest,delivery,expires_at) VALUES (%s,%s,now()+interval '20 minutes')",
            (token_hash(token), row["id"]),
        )
        payload["token"] = token
    return row, payload


def send_push(subscription, payload, ttl):
    from pywebpush import WebPushException, webpush
    from requests import Session

    class NoRedirect(Session):
        def request(self, *args, **kwargs):
            kwargs["allow_redirects"] = False
            return super().request(*args, **kwargs)

    _, key, subject = vapid()
    with NoRedirect() as client:
        try:
            response = webpush(
                subscription_info=subscription,
                data=json.dumps(payload),
                vapid_private_key=key,
                vapid_claims={"sub": subject},
                ttl=ttl,
                timeout=5,
                requests_session=client,
            )
            return response.status_code
        except WebPushException as error:
            return getattr(error.response, "status_code", None)


def drain_notices(database, fingerprint, *, sender=None, limit=12):
    """No network calls inside a transaction. An ambiguous send is never replayed."""
    public, key, subject = vapid()
    if not (public and key and subject):
        return 0
    count = 0
    for _ in range(limit):
        with database.connect() as db:
            claimed = claim(db, fingerprint, key)
        if not claimed:
            break
        row, payload = claimed
        ttl = int((row["expires_at"] - datetime.now(UTC)).total_seconds())
        try:
            status = (
                (sender or send_push)(
                    {"endpoint": provider_endpoint(row["endpoint"]), "keys": row["keys"]},
                    payload,
                    ttl,
                )
                if ttl > 0
                else None
            )
        except Exception:  # noqa: BLE001 -- provider errors may contain credentials or endpoints
            status = None
        with database.connect() as db:
            if status in (404, 410):
                db.execute(
                    "DELETE FROM app.web_push_subscriptions WHERE id=%s AND keys=%s",
                    (row["subscription"], Jsonb(row["keys"])),
                )
            else:
                result = "accepted" if status in (200, 201, 202) else "failed"
                db.execute(
                    "UPDATE app.web_push_deliveries SET status=%s WHERE id=%s", (result, row["id"])
                )
        count += 1
    return count


def drain_android_notices(database, fingerprint, *, sender=None, limit=12):
    """Send generic FCM data messages; an ambiguous send is never replayed."""
    from . import voice
    from .side_effects import side_effects_allowed

    if sender is None:
        if (
            voice.missing(voice.FIREBASE_VARS)
            or not os.path.isfile(os.environ.get("FIREBASE_SERVICE_ACCOUNT_FILE", ""))
            or not side_effects_allowed()
        ):
            return 0
        sender = voice.FcmPusher().send_routine
    count = 0
    for _ in range(limit):
        with database.connect() as db:
            db.execute(
                "UPDATE app.android_routine_deliveries SET status='expired' "
                "WHERE status='pending' AND expires_at<=now()"
            )
            db.execute(
                "UPDATE app.android_routine_deliveries SET status='failed' "
                "WHERE status='sending' AND expires_at<=now()"
            )
            row = db.execute(
                """
                SELECT n.*,d.push_token FROM app.android_routine_deliveries n
                JOIN app.routine_android_devices d ON d.id=n.device
                JOIN app.sessions s ON s.token_hash=d.session_hash
                WHERE n.status='pending' AND n.expires_at>now()
                  AND s.expires_at>now() AND s.password_fingerprint=%s
                  AND d.password_fingerprint=%s
                ORDER BY n.expires_at,n.id LIMIT 1 FOR UPDATE OF n SKIP LOCKED
                """,
                (fingerprint, fingerprint),
            ).fetchone()
            if row:
                db.execute(
                    "UPDATE app.android_routine_deliveries SET status='sending' WHERE id=%s",
                    (row["id"],),
                )
        if not row:
            break
        state = "failed"
        ttl = max(0, int((row["expires_at"] - datetime.now(UTC)).total_seconds()))
        if ttl:
            try:
                sender(
                    row["push_token"],
                    {
                        "deliveryId": str(row["id"]),
                        "kind": row["kind"],
                        "expiresAt": row["expires_at"].isoformat(),
                    },
                    ttl,
                )
                state = "accepted"
            except voice.PushDeviceExpired:
                with database.connect() as db:
                    db.execute(
                        "DELETE FROM app.routine_android_devices WHERE id=%s", (row["device"],)
                    )
            except Exception:  # noqa: BLE001 -- provider errors may contain token data
                state = "failed"
        with database.connect() as db:
            db.execute(
                "UPDATE app.android_routine_deliveries SET status=%s WHERE id=%s",
                (state, row["id"]),
            )
        count += 1
    return count


def delivery_router(database, session, fingerprint, ack, *, calls=None, android_sender=None):
    router = APIRouter(prefix="/v1/routine-delivery")
    authenticated = Depends(session)

    @router.get("/android/status")
    def android_status(auth=authenticated):
        with database.connect() as db:
            enrolled = db.execute(
                """SELECT 1 FROM app.routine_android_devices d JOIN app.sessions s
                   ON s.token_hash=d.session_hash WHERE s.csrf=%s""",
                (auth["csrf"],),
            ).fetchone()
        return {
            "configured": firebase_ready() or android_sender is not None,
            "registered": bool(enrolled),
        }

    @router.post("/android/devices")
    def register_android(body: AndroidDevice, auth=authenticated):
        with database.connect() as db:
            db.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,4318))",
                (body.push_token,),
            )
            current_session = db.execute(
                """SELECT token_hash FROM app.sessions WHERE csrf=%s AND expires_at>now()
                   AND password_fingerprint=%s""",
                (auth["csrf"], fingerprint),
            ).fetchone()
            if not current_session:
                raise HTTPException(401, "Sign in again before enabling reminders.")
            prior = db.execute(
                """SELECT id,session_hash,password_fingerprint FROM app.routine_android_devices
                   WHERE push_token=%s FOR UPDATE""",
                (body.push_token,),
            ).fetchone()
            if prior and (
                prior["session_hash"] != current_session["token_hash"]
                or prior["password_fingerprint"] != fingerprint
            ):
                db.execute(
                    "DELETE FROM app.android_routine_deliveries WHERE device=%s",
                    (prior["id"],),
                )
            registered = db.execute(
                """
                INSERT INTO app.routine_android_devices
                    (id,push_token,session_hash,password_fingerprint)
                SELECT %s,%s,token_hash,password_fingerprint FROM app.sessions
                WHERE csrf=%s AND expires_at>now() AND password_fingerprint=%s
                ON CONFLICT(push_token) DO UPDATE SET
                    session_hash=EXCLUDED.session_hash,
                    password_fingerprint=EXCLUDED.password_fingerprint,
                    last_seen_at=now() RETURNING id
                """,
                (uuid4(), body.push_token, auth["csrf"], fingerprint),
            ).fetchone()
        return {"id": registered["id"]}

    @router.delete("/android/devices/{identifier}")
    def unregister_android(identifier: UUID, auth=authenticated):
        with database.connect() as db:
            db.execute(
                """DELETE FROM app.routine_android_devices d USING app.sessions s
                   WHERE d.id=%s AND d.session_hash=s.token_hash AND s.csrf=%s""",
                (identifier, auth["csrf"]),
            )
        return {"registered": False}

    @router.post("/android/test")
    def test_android(body: AndroidTest, auth=authenticated):
        if not firebase_ready() and android_sender is None:
            raise HTTPException(503, "Firebase delivery is awaiting server credentials.")
        identifier = uuid4()
        with database.connect() as db:
            created = db.execute(
                """
                INSERT INTO app.android_routine_deliveries
                    (id,device,dedupe_key,kind,expires_at,action_expires_at)
                SELECT %s,d.id,%s,'test',now()+interval '4 minutes',now()+interval '4 minutes'
                FROM app.routine_android_devices d
                JOIN app.sessions s ON s.token_hash=d.session_hash
                WHERE d.id=%s AND s.csrf=%s AND s.expires_at>now()
                  AND s.password_fingerprint=%s AND d.password_fingerprint=%s
                RETURNING id
                """,
                (
                    identifier,
                    "test:" + str(identifier),
                    body.device_id,
                    auth["csrf"],
                    fingerprint,
                    fingerprint,
                ),
            ).fetchone()
        if not created:
            raise HTTPException(410, "Enable reminders on this phone before testing.")
        drain_android_notices(database, fingerprint, sender=android_sender, limit=30)
        with database.connect() as db:
            status = db.execute(
                "SELECT status FROM app.android_routine_deliveries WHERE id=%s", (identifier,)
            ).fetchone()
        if not status or status["status"] != "accepted":
            raise HTTPException(503, "The test notification was not accepted. Try again.")
        return {"sent": True}

    @router.post("/android/respond")
    def android_respond(body: AndroidAck, auth=authenticated):
        with database.connect() as db:
            row = db.execute(
                """
                SELECT n.escalation_id FROM app.android_routine_deliveries n
                JOIN app.routine_android_devices d ON d.id=n.device
                JOIN app.sessions s ON s.token_hash=d.session_hash
                WHERE n.id=%s AND n.status='accepted' AND n.action_expires_at>now()
                  AND n.kind='pre_task' AND n.escalation_id IS NOT NULL
                  AND s.csrf=%s AND s.expires_at>now()
                  AND s.password_fingerprint=%s AND d.password_fingerprint=%s
                FOR UPDATE OF n
                """,
                (body.delivery_id, auth["csrf"], fingerprint, fingerprint),
            ).fetchone()
            if not row:
                raise HTTPException(410, "This reminder has expired or was already answered.")
            ack(db, row["escalation_id"], body.action)
            db.execute(
                "UPDATE app.android_routine_deliveries SET action_expires_at=now() WHERE id=%s",
                (body.delivery_id,),
            )
        return {"recorded": True}

    if calls is not None:
        from .routine_voice import internal_router

        router.include_router(internal_router(database, calls, fingerprint))

    @router.get("/status")
    def status(auth=authenticated):
        public, key, subject = vapid()
        with database.connect() as db:
            active = db.execute(
                """
                SELECT 1 FROM app.web_push_subscriptions s JOIN app.sessions a ON a.token_hash=s.session_hash
                WHERE a.csrf=%s""",
                (auth["csrf"],),
            ).fetchone()
        return {
            "configured": bool(public and key and subject),
            "public_key": public,
            "subscribed": bool(active),
        }

    @router.post("/subscribe")
    def subscribe(body: Subscription, auth=authenticated):
        if not all(vapid()):
            raise HTTPException(503, "Web Push is awaiting configuration.")
        with database.connect() as db:
            # A browser re-enrolling after sign-in or a key rotation cannot inherit old action tokens.
            db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,4317))", (body.endpoint,))
            db.execute(
                """DELETE FROM app.web_push_subscriptions s
                       WHERE s.endpoint=%s AND (s.keys<>%s OR s.session_hash<>(
                           SELECT token_hash FROM app.sessions WHERE csrf=%s))""",
                (body.endpoint, Jsonb(body.keys.model_dump()), auth["csrf"]),
            )
            db.execute(
                """
                INSERT INTO app.web_push_subscriptions(id,endpoint,keys,session_hash)
                SELECT %s,%s,%s,token_hash FROM app.sessions WHERE csrf=%s
                ON CONFLICT(endpoint) DO UPDATE SET keys=EXCLUDED.keys, session_hash=EXCLUDED.session_hash
                """,
                (uuid4(), body.endpoint, Jsonb(body.keys.model_dump()), auth["csrf"]),
            )
        return {"subscribed": True}

    @router.post("/unsubscribe")
    def unsubscribe(auth=authenticated):
        with database.connect() as db:
            db.execute(
                """DELETE FROM app.web_push_subscriptions s USING app.sessions a
                       WHERE s.session_hash=a.token_hash AND a.csrf=%s""",
                (auth["csrf"],),
            )
        return {"subscribed": False}

    @router.post("/respond")
    def respond(body: Ack):
        nonce, sig = body.token.split(".")
        _, secret, _ = vapid()
        if not secret or not hmac.compare_digest(sig, signature(nonce, secret)):
            raise HTTPException(403, "This reminder action is unavailable.")
        with database.connect() as db:
            row = db.execute(
                """
                SELECT d.escalation_id FROM app.web_push_tokens t
                JOIN app.web_push_deliveries d ON d.id=t.delivery
                JOIN app.web_push_subscriptions s ON s.id=d.subscription
                JOIN app.sessions a ON a.token_hash=s.session_hash
                WHERE t.digest=%s AND t.used_at IS NULL AND t.expires_at>now()
                  AND a.expires_at>now() AND a.password_fingerprint=%s FOR UPDATE OF t
                """,
                (token_hash(body.token), fingerprint),
            ).fetchone()
            if not row:
                raise HTTPException(410, "This reminder has expired or was already answered.")
            ack(db, row["escalation_id"], body.action)
            db.execute(
                "UPDATE app.web_push_tokens SET used_at=now() WHERE digest=%s",
                (token_hash(body.token),),
            )
        return {"recorded": True}

    return router


def ring_reminder(db, calls, escalation_id, summary, context):
    from .call_service import LOCK

    if calls.mode == "live" and not os.environ.get("YGGDRAS_REMINDER_LLM"):
        raise HTTPException(503, "The reminder voice model is awaiting configuration.")
    db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
    row = calls.create(db, direction="outbound", reason="Important task reminder")
    db.execute(
        """INSERT INTO app.routine_voice_bindings(call_id,escalation_id,summary,context)
               VALUES (%s,%s,%s,%s)""",
        (row["id"], escalation_id, summary[:2500], context[:8000]),
    )
    queue_notice(db, key=f"ring:{row['id']}", kind="incoming_call")
    return row["id"]
