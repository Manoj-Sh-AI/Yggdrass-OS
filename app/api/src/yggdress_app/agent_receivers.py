"""Backend-only loopback adapter to existing authenticated receiving contracts."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from .agent_models import AgentError
from .notes_proxy import NoRedirect


class Receivers:
    def __init__(self, origin, tokens):
        target = urlsplit(origin)
        if (
            target.scheme != "http"
            or target.hostname != "127.0.0.1"
            or target.path
            or target.query
            or target.fragment
            or target.username
        ):
            raise ValueError("The local agent adapter requires an exact loopback API origin.")
        self.origin, self._tokens = origin, tokens

    def call(self, scope, path, payload=None):
        token = self._tokens.get(scope)
        if not token:
            raise AgentError("This private agent connection is not configured.")
        request = Request(
            self.origin + "/v1/receivers/" + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        )
        try:
            with build_opener(NoRedirect()).open(request, timeout=20) as response:
                raw = response.read(2500001)
            if len(raw) > 2500000:
                raise AgentError("The agent context exceeds its response limit.")
            return json.loads(raw)
        except HTTPError as error:
            if error.code == 409:
                raise AgentError(
                    "The source or destination changed during this request. Refresh before retrying."
                ) from None
            raise AgentError("The private application receiving connection failed.") from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise AgentError("The private application connection was interrupted.") from None

    def attachment(self, request_id, identifier):
        request = Request(
            self.origin + f"/v1/receivers/chat/requests/{request_id}/attachments/{identifier}",
            headers={"Authorization": "Bearer " + self._tokens["chat"]},
        )
        try:
            with build_opener(NoRedirect()).open(request, timeout=10) as response:
                raw = response.read(160001)
            if len(raw) > 160000:
                raise AgentError(
                    "This attachment exceeds the initial model-context limit. It remains saved; send a smaller excerpt."
                )
            return raw
        except (HTTPError, URLError, TimeoutError, OSError):
            raise AgentError("The selected attachment could not be read.") from None
