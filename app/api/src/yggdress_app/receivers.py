"""Private receiving endpoints; never expose their credentials to the browser."""

import hashlib
import hmac
import json
import os

from fastapi import Header, HTTPException


def payload_fingerprint(model):
    """JSON object order is not event identity, including after JSONB round trips."""
    return hashlib.sha256(
        json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def receiver_access(scope, tokens=None):
    token = (tokens or {}).get(scope) or os.environ.get(
        "YGGDRESS_" + scope.upper() + "_RECEIVER_TOKEN", ""
    )
    configured = len(token) >= 32

    def authenticated(authorization: str | None = Header(default=None)):
        if not configured:
            raise HTTPException(503, "This receiving connection is not configured.")
        supplied = (authorization or "").removeprefix("Bearer ")
        if not (authorization or "").startswith("Bearer ") or not hmac.compare_digest(
            supplied.encode(), token.encode()
        ):
            raise HTTPException(401, "Receiver authentication required.")

    return authenticated, configured
