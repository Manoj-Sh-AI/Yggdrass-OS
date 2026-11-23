"""Signing in to a connector's MCP server (the MCP authorization spec, OAuth 2.1).

discover → register (dynamic client registration, or Manoj's own OAuth app from the
environment) → authorize with PKCE → exchange the code → refresh when it expires → revoke.

Tokens live only in an encrypted file on this laptop (`Vault`), outside OneDrive and the
repository. They never appear in a response, a log line or the database. Each sign-in has a
one-time `state` that expires after ten minutes.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken

from .connector_directory import App

STATE_TTL = 600


class AuthError(ValueError):
    """A plain message for Manoj; never contains a token or secret."""


def default_vault_dir() -> Path:
    configured = os.environ.get("YGGDRESS_CONNECTOR_STORE", "").strip()
    if configured:
        return Path(configured)
    local = os.environ.get("LOCALAPPDATA")
    return (Path(local) / "Yggdras" if local else Path.home() / ".yggdras") / "connectors"


@dataclass
class Vault:
    """Encrypted per-app records: client registration, tokens, enabled flag, tool list."""

    folder: Path = field(default_factory=default_vault_dir)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _fernet(self) -> Fernet:
        self.folder.mkdir(parents=True, exist_ok=True)
        key_file = self.folder / "vault.key"
        if not key_file.exists():
            key_file.write_bytes(Fernet.generate_key())
        return Fernet(key_file.read_bytes())

    def _read(self) -> dict:
        path = self.folder / "vault.bin"
        if not path.exists():
            return {}
        try:
            return json.loads(self._fernet().decrypt(path.read_bytes()))
        except InvalidToken as exc:
            raise AuthError("The connector vault could not be opened; reconnect apps.") from exc

    def _write(self, data: dict) -> None:
        path = self.folder / "vault.bin"
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(self._fernet().encrypt(json.dumps(data).encode()))
        tmp.replace(path)

    def get(self, app_id: str) -> dict:
        with self._lock:
            return dict(self._read().get(app_id, {}))

    def all(self) -> dict:
        with self._lock:
            return self._read()

    def update(self, app_id: str, **values) -> dict:
        with self._lock:
            data = self._read()
            record = {**data.get(app_id, {}), **values}
            data[app_id] = record
            self._write(data)
            return dict(record)

    def forget(self, app_id: str, keep_client: bool = True) -> None:
        with self._lock:
            data = self._read()
            old = data.pop(app_id, {})
            if keep_client and old.get("client"):
                data[app_id] = {"client": old["client"]}
            self._write(data)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _get_json(client: httpx.Client, url: str) -> dict | None:
    try:
        response = client.get(url, headers={"Accept": "application/json"})
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        data = response.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def discover(client: httpx.Client, mcp_url: str) -> tuple[dict, dict]:
    """Protected-resource metadata (RFC 9728), then the authorization server's (RFC 8414)."""
    parts = urlsplit(mcp_url)
    base = f"{parts.scheme}://{parts.netloc}"
    path = parts.path.rstrip("/")
    resource = None
    for candidate in ([f"{base}/.well-known/oauth-protected-resource{path}"] if path else []) + [
        f"{base}/.well-known/oauth-protected-resource"
    ]:
        resource = _get_json(client, candidate)
        if resource and resource.get("authorization_servers"):
            break
    if not resource or not resource.get("authorization_servers"):
        raise AuthError("This app's server did not say where to sign in.")
    issuer = urlsplit(str(resource["authorization_servers"][0]))
    ibase, ipath = f"{issuer.scheme}://{issuer.netloc}", issuer.path.rstrip("/")
    for candidate in (
        f"{ibase}/.well-known/oauth-authorization-server{ipath}",
        f"{ibase}/.well-known/openid-configuration{ipath}",
        f"{ibase}{ipath}/.well-known/openid-configuration",
        f"{ibase}/.well-known/oauth-authorization-server",
    ):
        meta = _get_json(client, candidate)
        if meta and meta.get("authorization_endpoint") and meta.get("token_endpoint"):
            return resource, meta
    raise AuthError("This app's sign-in server could not be found.")


@dataclass
class Pending:
    app_id: str
    verifier: str
    redirect_uri: str
    created: float


@dataclass
class Auth:
    """The sign-in flows. `http` is injectable so tests use an invented local server."""

    vault: Vault
    http: httpx.Client = field(default_factory=lambda: httpx.Client(timeout=20))
    environ: dict = field(default_factory=lambda: os.environ)  # type: ignore[assignment]
    _pending: dict[str, Pending] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def missing_env(self, app: App) -> list[str]:
        if app.auth != "client":
            return []
        return [n for n in app.client_env if not str(self.environ.get(n, "")).strip()]

    def _client_for(self, app: App, meta: dict, redirect_uri: str) -> dict:
        if app.auth == "client":
            missing = self.missing_env(app)
            if missing:
                raise AuthError(f"{app.title} needs {', '.join(missing)} in .env first.")
            cid, secret = (self.environ[n].strip() for n in app.client_env)
            return {"client_id": cid, "client_secret": secret}
        saved = self.vault.get(app.id).get("client")
        if saved and redirect_uri in saved.get("redirect_uris", []):
            return saved
        endpoint = meta.get("registration_endpoint")
        if not endpoint:
            raise AuthError(f"{app.title} does not allow automatic sign-in setup.")
        try:
            response = self.http.post(endpoint, json={
                "client_name": "Yggdras", "redirect_uris": [redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"], "token_endpoint_auth_method": "none",
            })  # fmt: skip
        except httpx.HTTPError as exc:
            raise AuthError(f"{app.title} could not be reached to register Yggdras.") from exc
        if response.status_code not in (200, 201):
            raise AuthError(f"{app.title} refused to register Yggdras ({response.status_code}).")
        data = response.json()
        client = {"client_id": data["client_id"], "redirect_uris": [redirect_uri]}
        if data.get("client_secret"):
            client["client_secret"] = data["client_secret"]
        self.vault.update(app.id, client=client)
        return client

    def start(self, app: App, redirect_uri: str) -> str:
        """The address Manoj opens to sign in. Nothing is stored until he comes back."""
        if app.auth == "unavailable":
            raise AuthError(f"{app.title} cannot be connected yet.")
        resource, meta = discover(self.http, app.url)
        if "S256" not in (meta.get("code_challenge_methods_supported") or ["S256"]):
            raise AuthError(f"{app.title} does not support a safe sign-in (PKCE).")
        client = self._client_for(app, meta, redirect_uri)
        verifier = _b64(secrets.token_bytes(48))
        state = _b64(secrets.token_bytes(24))
        with self._lock:
            now = time.time()
            for key in [k for k, p in self._pending.items() if now - p.created > STATE_TTL]:
                del self._pending[key]
            self._pending[state] = Pending(app.id, verifier, redirect_uri, now)
        self.vault.update(app.id, endpoints={
            "token": meta["token_endpoint"], "revoke": meta.get("revocation_endpoint", ""),
            "resource": resource.get("resource") or app.url})  # fmt: skip
        params = {
            "response_type": "code", "client_id": client["client_id"],
            "redirect_uri": redirect_uri, "state": state,
            "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
            "code_challenge_method": "S256",
            "resource": resource.get("resource") or app.url, **app.extra,
        }  # fmt: skip
        if app.scopes:
            params["scope"] = " ".join(app.scopes)
        return f"{meta['authorization_endpoint']}?{urlencode(params)}"

    def finish(self, state: str, code: str, lookup) -> App:
        """The return from sign-in: a one-time state, then the code becomes tokens."""
        with self._lock:
            pending = self._pending.pop(state or "", None)
        if pending is None or time.time() - pending.created > STATE_TTL:
            raise AuthError("This sign-in link has expired or was already used. Try again.")
        app: App = lookup(pending.app_id)
        record = self.vault.get(app.id)
        client = self._client_for(app, {}, pending.redirect_uri) if app.auth == "client" \
            else record.get("client", {})  # fmt: skip
        body = {
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": pending.redirect_uri, "client_id": client.get("client_id", ""),
            "code_verifier": pending.verifier, "resource": record["endpoints"]["resource"],
        }  # fmt: skip
        if client.get("client_secret"):
            body["client_secret"] = client["client_secret"]
        self._store(app, self._token(record["endpoints"]["token"], body, app))
        self.vault.update(app.id, enabled=True, connected_at=int(time.time()))
        return app

    def _token(self, endpoint: str, body: dict, app: App) -> dict:
        try:
            response = self.http.post(endpoint, data=body, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            raise AuthError(f"{app.title} could not be reached to finish signing in.") from exc
        if response.status_code != 200:
            raise AuthError(f"{app.title} refused the sign-in ({response.status_code}).")
        data = response.json()
        if not data.get("access_token"):
            raise AuthError(f"{app.title} sent no access token.")
        return data

    def _store(self, app: App, data: dict) -> None:
        old = self.vault.get(app.id).get("tokens", {})
        self.vault.update(app.id, tokens={
            "access": data["access_token"],
            "refresh": data.get("refresh_token") or old.get("refresh", ""),
            "expires": int(time.time()) + int(data.get("expires_in") or 3600),
        })  # fmt: skip

    def access(self, app: App) -> str:
        """A current access token, refreshed when it is about to expire."""
        record = self.vault.get(app.id)
        tokens = record.get("tokens")
        if not tokens:
            raise AuthError(f"{app.title} is not connected.")
        if tokens["expires"] - 60 > time.time():
            return tokens["access"]
        if not tokens.get("refresh"):
            raise AuthError(f"{app.title}'s sign-in expired. Connect it again.")
        client = self._client_for(app, {}, "") if app.auth == "client" else record["client"]
        body = {
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh"],
            "client_id": client["client_id"],
            "resource": record["endpoints"]["resource"],
        }
        if client.get("client_secret"):
            body["client_secret"] = client["client_secret"]
        self._store(app, self._token(record["endpoints"]["token"], body, app))
        return self.vault.get(app.id)["tokens"]["access"]

    def disconnect(self, app: App) -> None:
        """Revoke at the app when it offers that, then forget the tokens here."""
        record = self.vault.get(app.id)
        revoke = (record.get("endpoints") or {}).get("revoke")
        token = (record.get("tokens") or {}).get("refresh") or (record.get("tokens") or {}).get(
            "access"
        )
        if revoke and token:
            client = record.get("client") or {}
            try:
                self.http.post(
                    revoke, data={"token": token, "client_id": client.get("client_id", "")}
                )
            except httpx.HTTPError:
                pass  # forgetting locally still disconnects Yggdras
        self.vault.forget(app.id)
