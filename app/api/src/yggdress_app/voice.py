"""Calls with Yggdras: LiveKit room access, push delivery, and the rule for what may notify.

LiveKit Cloud (free Build plan) carries the audio; this module only signs a short-lived room
token with LIVEKIT_API_KEY / LIVEKIT_API_SECRET (an HS256 JWT, LiveKit's documented access
token format), so no secret ever reaches a client. Without the keys every call runs against
the simulated room, which tests and the browser checks use; nothing is spent.

Push: Android through Firebase Cloud Messaging (FIREBASE_* keys), web/desktop through the
open event stream. iPhone (PushKit/CallKit) is deferred by decision: `IosVoipPusher` is the
interface to fill in later.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

LIVEKIT_VARS = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
FIREBASE_VARS = ("FIREBASE_PROJECT_ID", "FIREBASE_SERVICE_ACCOUNT_FILE")


def missing(names) -> list[str]:
    return [n for n in names if not os.environ.get(n, "").strip()]


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def room_token(identity: str, room: str, *, key: str, secret: str, ttl: int = 600,
               now: float | None = None) -> str:  # fmt: skip
    """A LiveKit access token for one participant in one room (join, talk, listen)."""
    issued = int(now if now is not None else time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    claims = {"iss": key, "sub": identity, "nbf": issued, "exp": issued + ttl,
              "video": {"room": room, "roomJoin": True, "canPublish": True,
                        "canSubscribe": True, "canPublishData": False, "canPublishSources": ["microphone"]}}  # fmt: skip
    signing = f"{_b64(json.dumps(header, separators=(',', ':')).encode())}." + _b64(
        json.dumps(claims, separators=(",", ":")).encode()
    )
    signature = hmac.new(secret.encode(), signing.encode(), hashlib.sha256).digest()
    return f"{signing}.{_b64(signature)}"


@dataclass(frozen=True)
class RoomAccess:
    url: str
    token: str
    room: str
    simulated: bool


def join(identity: str, room: str) -> RoomAccess:
    """Room access for a client; simulated (and free) until LiveKit keys are in .env."""
    if missing(LIVEKIT_VARS):
        return RoomAccess("sim://livekit", f"simulated:{room}:{identity}", room, True)
    token = room_token(identity, room, key=os.environ["LIVEKIT_API_KEY"],
                       secret=os.environ["LIVEKIT_API_SECRET"])  # fmt: skip
    return RoomAccess(os.environ["LIVEKIT_URL"], token, room, False)


# ---------------------------------------------------------------- push


class PushNotConfigured(RuntimeError):
    pass


class PushDeviceExpired(PushNotConfigured):
    pass


@dataclass
class SimulatedPusher:
    """Records what would have been pushed; used until FIREBASE_* keys exist, and in tests."""

    sent: list[dict] = field(default_factory=list)

    def send(self, device: dict, message: dict) -> None:
        self.sent.append({"device": device["id"], "platform": device["platform"], **message})


class FcmPusher:
    """Android: a high-priority FCM data message wakes the app's full-screen call screen."""

    def __init__(self):
        if missing(FIREBASE_VARS):
            raise PushNotConfigured("FIREBASE_PROJECT_ID and FIREBASE_SERVICE_ACCOUNT_FILE")

    def send(self, device: dict, message: dict) -> None:  # pragma: no cover - needs Firebase
        try:
            import firebase_admin
            from firebase_admin import credentials, messaging

            try:
                app = firebase_admin.get_app("yggdras-calls")
            except ValueError:
                app = firebase_admin.initialize_app(
                    credentials.Certificate(os.environ["FIREBASE_SERVICE_ACCOUNT_FILE"]),
                    {"projectId": os.environ["FIREBASE_PROJECT_ID"]},
                    name="yggdras-calls",
                )
            try:
                messaging.send(
                    messaging.Message(
                        token=device["push_token"],
                        data={k: str(v) for k, v in {"type": "yggdras_call", **message}.items()},
                        android=messaging.AndroidConfig(priority="high", ttl=timedelta(seconds=45)),
                    ),
                    app=app,
                )
            except messaging.UnregisteredError:
                raise PushDeviceExpired("This device push token expired.") from None
        except ImportError:
            raise PushNotConfigured(
                "Install the application voice dependencies before enabling push."
            ) from None


class IosVoipPusher:
    """iPhone: PushKit VoIP push to CallKit. Deferred (Manoj, 2026-11-16); fill in later."""

    def send(self, device: dict, message: dict) -> None:
        raise PushNotConfigured("iPhone calls are deferred: PushKit/CallKit not built yet")


# ---------------------------------------------------------------- what may notify

KINDS = ("approval", "call", "time_critical", "deadline")
MAX_PER_HOUR = 4
QUIET = (22, 7)  # 22:00 to 07:00: only calls ring
APPROVAL_WAIT = timedelta(minutes=30)


@dataclass(frozen=True)
class Verdict:
    send: bool
    why: str


def focused(kind: str, *, now: datetime, sent_last_hour: int, duplicate: bool,
            waiting_since: datetime | None = None, starts_at: datetime | None = None) -> Verdict:  # fmt: skip
    """A notification earns its place or it is not sent. The rule, in order:
    1. never twice: the same thing (dedupe key) is notified once;
    2. a call always rings (Manoj chose to be called, or asked to be);
    3. quiet hours (22:00-07:00): nothing else;
    4. at most 4 per hour, so a busy hour can't become noise;
    5. an approval card notifies only after waiting 30 minutes unseen;
    6. time-critical only within 10 minutes of the start; a deadline only on its day.
    Progress, success and "FYI" never notify."""
    if kind not in KINDS:
        return Verdict(False, "not a notifying kind: progress and FYI never notify")
    if duplicate:
        return Verdict(False, "already notified")
    if kind == "call":
        return Verdict(True, "a call rings")
    hour = now.hour
    if hour >= QUIET[0] or hour < QUIET[1]:
        return Verdict(False, "quiet hours")
    if sent_last_hour >= MAX_PER_HOUR:
        return Verdict(False, "hourly limit reached")
    if kind == "approval":
        ok = waiting_since is not None and now - waiting_since >= APPROVAL_WAIT
        return Verdict(ok, "waiting 30 minutes" if ok else "not waiting long enough")
    if kind == "time_critical":
        ok = starts_at is not None and timedelta(0) <= starts_at - now <= timedelta(minutes=10)
        return Verdict(ok, "starts within 10 minutes" if ok else "not imminent")
    ok = starts_at is not None and starts_at.date() == now.date()
    return Verdict(ok, "due today" if ok else "not due today")
