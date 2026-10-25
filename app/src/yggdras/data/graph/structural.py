"""Structural pass: build the brain's map from frontmatter and hand-written links.

No model, no database, byte-identical output for unchanged input (D5, D6, D8).
Spec: requirements/spec-phase-1b-structural-pass.md

Usage:
    python -m yggdras.data.graph.structural BRAIN_ROOT [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SCHEMA = "yggdras-map/1"
LINKS_HEADING = "## Links"
WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
LINK_LINE = re.compile(r"^- (.*?)\[\[([^\]]+)\]\]")
_NORM_EXTRA = {"ß": "ss", "ø": "o"}


def normalize(text: str) -> str:
    """D02 normalization: lowercase, accents stripped, ß/ø mapped, hyphens, punctuation dropped."""
    s = text.lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = "".join(_NORM_EXTRA.get(c, c) for c in s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^\w-]", "", s)
    return re.sub(r"-{2,}", "-", s).strip("-")


@dataclass
class Node:
    id: str
    slug: str
    name: str
    type: str
    path: str
    aliases: list[str]
    links: list[tuple[int, str, str]] = field(default_factory=list)  # (line, reason, written_as)


def _split(text: str) -> tuple[str, list[str], int] | None:
    """Return (frontmatter, body lines, line number of the first body line) or None."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), lines[i + 1 :], i + 2
    return None


def links_section(body: list[str], first_line: int) -> list[tuple[int, str]]:
    """Lines (number, text) inside the `## Links` section, up to the next heading."""
    out, inside = [], False
    for offset, line in enumerate(body):
        if line.startswith("## "):
            inside = line.strip() == LINKS_HEADING
            continue
        if inside:
            out.append((first_line + offset, line))
    return out


def parse_node(path: Path, root: Path) -> tuple[Node | None, str | None]:
    rel = path.relative_to(root).as_posix()
    parts = _split(path.read_text(encoding="utf-8"))
    if parts is None:
        return None, "no frontmatter block"
    fm_text, body, first_line = parts
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        return None, f"unparseable frontmatter: {exc.__class__.__name__}"
    missing = [k for k in ("id", "slug", "name", "type") if not fm.get(k)]
    if missing:
        return None, f"missing frontmatter field(s): {', '.join(missing)}"
    node = Node(
        id=str(fm["id"]),
        slug=str(fm["slug"]),
        name=str(fm["name"]),
        type=str(fm["type"]),
        path=rel,
        aliases=[str(a) for a in fm.get("aliases") or []],
    )
    for number, line in links_section(body, first_line):
        m = LINK_LINE.match(line)
        if m:
            node.links.append((number, m.group(1).strip(), m.group(2)))
    return node, None


def node_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.md") if p != root / "index.md")


def build_map(root: Path) -> dict:
    """Build the map for the brain at *root*. Never writes to the brain."""
    nodes: dict[str, Node] = {}
    errors: list[dict] = []
    for path in node_files(root):
        node, problem = parse_node(path, root)
        rel = path.relative_to(root).as_posix()
        if problem:
            errors.append({"path": rel, "problem": problem})
        elif node.slug in nodes:
            errors.append(
                {
                    "path": rel,
                    "problem": f"duplicate slug '{node.slug}' (also {nodes[node.slug].path})",
                }
            )
        else:
            nodes[node.slug] = node

    # Normalized key -> {node id: how it matched}
    keys: dict[str, dict[str, str]] = {}
    for node in nodes.values():
        keys.setdefault(normalize(node.slug), {})[node.id] = "slug"
        for alias in node.aliases:
            keys.setdefault(normalize(alias), {}).setdefault(node.id, "alias")
    by_id = {n.id: n for n in nodes.values()}

    edges, dangling = [], []
    for node in nodes.values():
        for line, reason, written in node.links:
            if written in nodes:
                target, via = nodes[written], "slug"
            else:
                matches = keys.get(normalize(written), {})
                if len(matches) > 1:
                    errors.append(
                        {
                            "path": node.path,
                            "problem": f"line {line}: [[{written}]] is ambiguous, matching "
                            + ", ".join(sorted(by_id[i].slug for i in matches)),
                        }
                    )
                    continue
                if not matches:
                    dangling.append(
                        {
                            "from": node.id,
                            "from_slug": node.slug,
                            "reason": reason,
                            "written_as": written,
                            "line": line,
                        }
                    )
                    continue
                ((target_id, via),) = matches.items()
                target = by_id[target_id]
            edges.append(
                {
                    "from": node.id,
                    "to": target.id,
                    "from_slug": node.slug,
                    "to_slug": target.slug,
                    "reason": reason,
                    "written_as": written,
                    "resolved_via": via,
                    "line": line,
                }
            )

    order = lambda e: (e["from_slug"], e["line"])  # noqa: E731
    return {
        "schema": SCHEMA,
        "nodes": [
            {
                "id": n.id,
                "slug": n.slug,
                "name": n.name,
                "type": n.type,
                "path": n.path,
                "aliases": n.aliases,
            }
            for n in sorted(nodes.values(), key=lambda n: n.slug)
        ],
        "edges": sorted(edges, key=order),
        "dangling": sorted(dangling, key=order),
        "errors": sorted(errors, key=lambda e: (e["path"], e["problem"])),
    }


def count_raw_links(root: Path) -> dict[str, int]:
    """Count every [[...]] across whole files by plain text, independently of the parser."""
    total = inside = 0
    for path in node_files(root):
        text = path.read_text(encoding="utf-8")
        total += len(WIKILINK.findall(text))
        parts = _split(text)
        if parts:
            inside += sum(
                len(WIKILINK.findall(line)) for _, line in links_section(parts[1], parts[2])
            )
    return {"total": total, "inside_links": inside, "outside_links": total - inside}


def render(graph: dict) -> str:
    return json.dumps(graph, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def default_out(root: Path) -> Path:
    return root.resolve().parent / ".map" / "graph.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="structural", description=__doc__.splitlines()[0])
    parser.add_argument("brain", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if not args.brain.is_dir():
        print(f"not a folder: {args.brain}", file=sys.stderr)
        return 2
    graph = build_map(args.brain)
    out = args.out or default_out(args.brain)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(graph), encoding="utf-8", newline="\n")
    raw = count_raw_links(args.brain)
    counts = {k: len(graph[k]) for k in ("nodes", "edges", "dangling", "errors")}
    print(", ".join(f"{k} {v}" for k, v in counts.items()))
    print(
        f"[[...]] in whole files: {raw['total']} ({raw['inside_links']} inside ## Links, "
        f"{raw['outside_links']} outside)"
    )
    print(f"wrote {out}")
    if raw["outside_links"]:
        print(
            "STOP: links found outside ## Links sections. This is a node-format question (D31), "
            "not a parser fix.",
            file=sys.stderr,
        )
    return 1 if graph["errors"] or raw["outside_links"] else 0


if __name__ == "__main__":
    sys.exit(main())
