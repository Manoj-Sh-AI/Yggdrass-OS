"""The connector catalog: MCP servers Manoj can switch on, whose tools arrive under the skill
that needs them (tool_gate.py), never all at once.

- The catalog is a local JSON file (YGGDRESS_CONNECTORS_FILE; git-ignored, never in the repo).
  Each entry names its MCP server (a command or a URL), the skill domain its tools belong to,
  and the NAMES of the .env variables it needs. Values come from the environment only.
- Switching one on or off registers or removes its tools in the live tool registry: no
  redeploy. Its tools are still unreachable until a skill in its domain is loaded, because
  the registry is the same one the gate filters.
- A tool's risk comes from its MCP annotations: read-only tools are safe; anything else is a
  write; destructive tools also delete. Unknown means risky (the checker stops it).
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .tool_gate import DELETE, WRITE, Tool, ToolRegistry

if TYPE_CHECKING:
    from .connector_auth import Auth
    from .connector_directory import App


class ConnectorError(ValueError):
    pass


@dataclass(frozen=True)
class Entry:
    name: str
    title: str
    domain: str
    command: tuple[str, ...] = ()
    url: str = ""
    env: tuple[str, ...] = ()
    enabled: bool = False

    def missing(self) -> list[str]:
        return [n for n in self.env if not os.environ.get(n, "").strip()]


def parse(raw: dict) -> Entry:
    name = str(raw.get("name", ""))
    if not name.replace("-", "").isalnum() or len(name) > 40:
        raise ConnectorError(f"connector name {name!r} must be short letters, digits or dashes")
    if bool(raw.get("command")) == bool(raw.get("url")):
        raise ConnectorError(f"{name}: give either a command or a url")
    env = tuple(str(v) for v in raw.get("env", []))
    if any("=" in v or not v.replace("_", "").isalnum() for v in env):
        raise ConnectorError(f"{name}: env lists variable NAMES only, never values")
    return Entry(name, str(raw.get("title") or name), str(raw.get("domain") or name),
                 tuple(str(c) for c in raw.get("command") or ()), str(raw.get("url") or ""),
                 env, bool(raw.get("enabled")))  # fmt: skip


def risks(annotations: dict) -> frozenset:
    if (annotations or {}).get("readOnlyHint") is True:
        return frozenset()
    return frozenset({WRITE, DELETE} if (annotations or {}).get("destructiveHint") else {WRITE})


def _tool(prefix: str, domain: str, spec: dict) -> Tool:
    return Tool(f"{prefix}__{spec['name']}"[:128], domain,
                str(spec.get("description", ""))[:1000],
                spec.get("inputSchema") or {"type": "object"},
                risks(spec.get("annotations") or {}))  # fmt: skip


@dataclass
class Catalog:
    """The built-in app directory plus the local catalog file, and the tools their enabled
    connectors put in the registry.

    Directory apps are connected by signing in (connector_auth.py); their tokens, on/off
    state and last tool list live in the encrypted vault. File entries keep the older
    switch-by-env behaviour.
    """

    path: Path
    registry: ToolRegistry
    lister: Callable[[Entry], list[dict]]  # an MCP tools/list for one file connector
    apps: tuple = ()  # connector_directory.APPS in the application; empty in old tests
    auth: Auth | None = None
    mcp_list: Callable[[str, str], list[dict]] | None = None  # (url, token) -> tool specs
    mcp_call: Callable[[str, str, str, dict], dict] | None = None  # (url, token, name, args)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _registered: dict[str, list[str]] = field(default_factory=dict)  # connector → tool names
    _owner: dict[str, tuple[str, str]] = field(default_factory=dict)  # tool → (app id, name)

    def entries(self) -> list[Entry]:
        if not self.path.is_file():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [parse(item) for item in data.get("connectors", [])]

    def app(self, app_id: str) -> App:
        match = next((a for a in self.apps if a.id == app_id), None)
        if match is None:
            raise ConnectorError(f"no app {app_id!r} in the directory")
        return match

    def _app_view(self, app: App, record: dict) -> dict:
        missing = self.auth.missing_env(app) if self.auth else []
        connected = bool(record.get("tokens"))
        status = ("unavailable" if app.auth == "unavailable" else "connected" if connected
                  else "needs_setup" if missing else "available")  # fmt: skip
        return {"name": app.id, "title": app.title, "group": app.group,
                "description": app.description, "domain": app.domain, "auth": app.auth,
                "status": status, "enabled": connected and bool(record.get("enabled")),
                "missing_env": missing, "setup": app.setup if app.auth == "client" else "",
                "tools": self._registered.get(app.id, []),
                "tool_count": len(record.get("tools") or []),
                "connected_at": record.get("connected_at")}  # fmt: skip

    def _file_view(self, e: Entry) -> dict:
        view = {
            "name": e.name,
            "title": e.title,
            "domain": e.domain,
            "enabled": e.enabled,
            "missing_env": e.missing(),
            "tools": self._registered.get(e.name, []),
        }
        if self.apps:  # the directory page shows file entries as "Your own"
            view.update(group="Your own", auth="file", setup="", connected_at=None,
                        status="connected" if e.enabled else "available",
                        description=e.url or " ".join(e.command),
                        tool_count=len(view["tools"]))  # fmt: skip
        return view

    def view(self) -> list[dict]:
        vault = self.auth.vault.all() if self.auth else {}
        apps = [self._app_view(a, vault.get(a.id, {})) for a in self.apps]
        return apps + [self._file_view(e) for e in self.entries()]

    # -- directory apps: sign in, list tools, switch, call, disconnect

    def connect_url(self, app_id: str, redirect_uri: str) -> str:
        if self.auth is None:
            raise ConnectorError("Connecting apps is not available in this service.")
        return self.auth.start(self.app(app_id), redirect_uri)

    def connected(self, state: str, code: str) -> dict:
        """The return from sign-in: store tokens, list the app's tools, switch it on."""
        app = self.auth.finish(state, code, self.app)
        self._load_tools(app)
        self.refresh()
        return next(v for v in self.view() if v["name"] == app.id)

    def _load_tools(self, app: App) -> None:
        token = self.auth.access(app)
        specs = self.mcp_list(app.url, token)
        keep = [{"name": t["name"], "description": str(t.get("description", ""))[:1000],
                 "inputSchema": t.get("inputSchema"), "annotations": t.get("annotations")}
                for t in specs][:200]  # fmt: skip
        self.auth.vault.update(app.id, tools=keep)

    def disconnect(self, app_id: str) -> dict:
        app = self.app(app_id)
        self.auth.disconnect(app)
        self.refresh()
        return next(v for v in self.view() if v["name"] == app.id)

    def call(self, tool_name: str, arguments: dict) -> dict:
        """Run one connector tool now. Results are returned, never stored."""
        owner = self._owner.get(tool_name)
        if owner is None:
            raise ConnectorError(f"{tool_name} is not a connected app's tool")
        app = self.app(owner[0])
        return self.mcp_call(app.url, self.auth.access(app), owner[1], arguments)

    def handlers(self) -> dict[str, Callable[[dict], object]]:
        return {name: (lambda values, n=name: self.call(n, values)) for name in self._owner}

    def owns(self, tool_name: str) -> bool:
        return tool_name in self._owner

    def switch(self, name: str, enabled: bool) -> dict:
        """Turn a connector on or off, live. Refuses to turn on one whose env is missing."""
        if any(a.id == name for a in self.apps):
            if not self.auth.vault.get(name).get("tokens"):
                raise ConnectorError(f"Connect {self.app(name).title} before switching it on.")
            self.auth.vault.update(name, enabled=enabled)
            self.refresh()
            return next(v for v in self.view() if v["name"] == name)
        with self._lock:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            items = data.get("connectors", [])
            match = [item for item in items if item.get("name") == name]
            if not match:
                raise ConnectorError(f"no connector {name!r} in the catalog")
            entry = parse({**match[0], "enabled": enabled})
            if enabled and entry.missing():
                raise ConnectorError(f"{name} needs {', '.join(entry.missing())} in .env first")
            match[0]["enabled"] = enabled
            self.path.write_text(json.dumps(data, indent=1), encoding="utf-8")
        self.refresh()
        return next(v for v in self.view() if v["name"] == name)

    def refresh(self) -> None:
        """Make the registry match the catalog: enabled connectors' tools in, others out."""
        with self._lock:
            for name, tools in list(self._registered.items()):
                for tool in tools:
                    self.registry.tools.pop(tool, None)
                del self._registered[name]
            self._owner.clear()
            vault = self.auth.vault.all() if self.auth else {}
            for app in self.apps:
                record = vault.get(app.id, {})
                if not (record.get("tokens") and record.get("enabled")):
                    continue
                names = []
                for spec in record.get("tools") or []:
                    tool = _tool(app.id, app.domain, spec)
                    if tool.name in self.registry.tools:
                        continue
                    self.registry.register(tool)
                    self._owner[tool.name] = (app.id, spec["name"])
                    names.append(tool.name)
                self._registered[app.id] = names
            for entry in self.entries():
                if not entry.enabled or entry.missing():
                    continue
                names = []
                for spec in self.lister(entry):
                    tool = _tool(entry.name, entry.domain, spec)
                    self.registry.register(tool)
                    names.append(tool.name)
                self._registered[entry.name] = names


def default_path() -> Path:
    configured = os.environ.get("YGGDRESS_CONNECTORS_FILE", "").strip()
    return Path(configured) if configured else Path.home() / ".yggdras" / "connectors.json"


def mcp_lister(entry: Entry) -> list[dict]:
    """tools/list from a real MCP server. Needs the MCP client library in this service."""
    try:
        import mcp  # noqa: F401
    except ImportError:
        raise ConnectorError(
            f"{entry.name}: the MCP client library is not installed in the app service yet"
        ) from None
    raise ConnectorError(f"{entry.name}: live MCP connections are wired when one is switched on")
