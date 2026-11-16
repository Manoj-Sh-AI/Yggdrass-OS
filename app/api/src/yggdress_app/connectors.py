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

from .tool_gate import DELETE, WRITE, Tool, ToolRegistry


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


@dataclass
class Catalog:
    """The catalog file and the tools its enabled connectors put in the registry."""

    path: Path
    registry: ToolRegistry
    lister: Callable[[Entry], list[dict]]  # an MCP tools/list for one connector
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _registered: dict[str, list[str]] = field(default_factory=dict)  # connector → tool names

    def entries(self) -> list[Entry]:
        if not self.path.is_file():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [parse(item) for item in data.get("connectors", [])]

    def view(self) -> list[dict]:
        return [{"name": e.name, "title": e.title, "domain": e.domain, "enabled": e.enabled,
                 "missing_env": e.missing(), "tools": self._registered.get(e.name, [])}
                for e in self.entries()]  # fmt: skip

    def switch(self, name: str, enabled: bool) -> dict:
        """Turn a connector on or off, live. Refuses to turn on one whose env is missing."""
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
            for entry in self.entries():
                if not entry.enabled or entry.missing():
                    continue
                names = []
                for spec in self.lister(entry):
                    tool = Tool(f"{entry.name}__{spec['name']}", entry.domain,
                                str(spec.get("description", ""))[:1000],
                                spec.get("inputSchema") or {"type": "object"},
                                risks(spec.get("annotations") or {}))  # fmt: skip
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
