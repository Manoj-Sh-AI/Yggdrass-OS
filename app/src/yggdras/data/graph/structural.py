"""Structural pass: build the brain's map from frontmatter and hand-written links.

No model, no database, byte-identical output for unchanged input (D5, D6, D8).
Spec: requirements/spec-phase-1b-structural-pass.md

Usage:
    python -m yggdras.data.graph.structural BRAIN_REPO
    python -m yggdras.data.graph.structural BRAIN_ROOT --flat [--out PATH]

The first form reads only BRAIN_REPO/library/ (the numbered shelves, minus the manual and
the inbox) and writes the map and the relationship map to library/00-manual/generated/.
The second reads every node under a flat brain such as the archived Apollo demo brain.
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

SCHEMA = "yggdras-map/2"
LIBRARY = "library"
# The library's folders, in order (D31 amendment A1). The only list of shelf names in code.
SHELVES = (
    "00-manual",
    "01-health",
    "02-relationships",
    "03-work-career",
    "04-learning-growth",
    "05-money",
    "06-purpose-meaning",
    "07-projects",
    "08-home-daily-life",
    "09-rest-joy",
    "10-mind",
    "11-people",
    "12-places",
    "13-sources",
    "14-inbox",
)
NOT_MAPPED = ("00-manual", "14-inbox")
GENERATED = Path("00-manual") / "generated"
MAP_FILE = "map.json"
RELATIONSHIP_MAP = "relationship-map.md"

FACTS_HEADING = "## Facts"
LINKS_HEADING = "## Links"
WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
LINK_LINE = re.compile(r"^- (.*?)\[\[([^\]]+)\]\]")
_NORM_EXTRA = {"ß": "ss", "ø": "o"}

# The fixed link verbs and their opposites (D31 amendment A5). A link is written once,
# in either form; the relationship map adds the other direction.
VERBS = {
    "part of": "contains",
    "depends on": "needed by",
    "blocks": "blocked by",
    "advances": "advanced by",
    "uses": "used by",
    "replaces": "replaced by",
    "causes": "caused by",
    "learned from": "taught",
    "recommended by": "recommended",
    "introduced by": "introduced",
    "supervised by": "supervises",
    "works with": "works with",
    "located at": "location of",
    "attended": "attended by",
    "cites": "cited by",
    "about": "subject of",
    "decided in": "decision on",
    "applies": "applied in",
    "conflicts with": "conflicts with",
}
OPPOSITE = {**VERBS, **{back: verb for verb, back in VERBS.items()}}
# A [[link]] inside a fact line is a plain mention, never a typed link (amendment A6).
MENTION, MENTIONED_IN = "mentions", "mentioned in"


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
    # (kind, line, reason, written_as); kind is "link" or "mention"
    links: list[tuple[str, int, str, str]] = field(default_factory=list)


def _split(text: str) -> tuple[str, list[str], int] | None:
    """Return (frontmatter, body lines, line number of the first body line) or None."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), lines[i + 1 :], i + 2
    return None


def section(body: list[str], first_line: int, heading: str) -> list[tuple[int, str]]:
    """Lines (number, text) inside the section under *heading*, up to the next heading."""
    out, inside = [], False
    for offset, line in enumerate(body):
        if line.startswith("## "):
            inside = line.strip() == heading
            continue
        if inside:
            out.append((first_line + offset, line))
    return out


def links_section(body: list[str], first_line: int) -> list[tuple[int, str]]:
    return section(body, first_line, LINKS_HEADING)


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
    for number, line in section(body, first_line, FACTS_HEADING):
        for written in WIKILINK.findall(line):
            node.links.append(("mention", number, MENTION, written))
    for number, line in links_section(body, first_line):
        m = LINK_LINE.match(line)
        if m:
            node.links.append(("link", number, m.group(1).strip(), m.group(2)))
    return node, None


def mapped_shelves() -> tuple[str, ...]:
    return tuple(s for s in SHELVES if s not in NOT_MAPPED)


def node_files(root: Path, shelves: tuple[str, ...] | None = None) -> list[Path]:
    """Node files under *root*. With *shelves*, only files inside those top-level folders."""
    if shelves is None:
        return sorted(p for p in root.rglob("*.md") if p != root / "index.md")
    return sorted(p for s in shelves if (root / s).is_dir() for p in (root / s).rglob("*.md"))


def library_problems(root: Path) -> list[dict]:
    """Anything at the top of the library that is not one of the numbered shelves."""
    return [
        {"path": p.name, "problem": "not a shelf: not in the numbered folder list"}
        for p in sorted(root.iterdir())
        if p.name not in SHELVES and not p.name.startswith(".")
    ]


def build_map(root: Path, shelves: tuple[str, ...] | None = None) -> dict:
    """Build the map for the brain at *root*. Never writes to the brain.

    With *shelves* (a library), only those top-level folders are read; without, every node
    under *root* except `index.md` (a flat brain such as the Apollo demo).
    """
    nodes: dict[str, Node] = {}
    errors: list[dict] = library_problems(root) if shelves is not None else []
    for path in node_files(root, shelves):
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

    edges, dangling, unknown = [], [], []
    for node in nodes.values():
        for kind, line, reason, written in node.links:
            if kind == "link" and reason not in OPPOSITE:
                unknown.append({"path": node.path, "line": line, "verb": reason})
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
                            "kind": kind,
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
                    "kind": kind,
                    "reason": reason,
                    "written_as": written,
                    "resolved_via": via,
                    "line": line,
                }
            )

    order = lambda e: (e["from_slug"], e["line"], e["written_as"])  # noqa: E731
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
        "unknown_verbs": sorted(unknown, key=lambda u: (u["path"], u["line"])),
    }


def count_raw_links(root: Path, shelves: tuple[str, ...] | None = None) -> dict[str, int]:
    """Count every [[...]] across whole files by plain text, independently of the parser."""
    total = inside = facts = 0
    for path in node_files(root, shelves):
        text = path.read_text(encoding="utf-8")
        total += len(WIKILINK.findall(text))
        parts = _split(text)
        if parts:
            body, first = parts[1], parts[2]
            inside += sum(len(WIKILINK.findall(line)) for _, line in links_section(body, first))
            facts += sum(
                len(WIKILINK.findall(line)) for _, line in section(body, first, FACTS_HEADING)
            )
    return {
        "total": total,
        "inside_links": inside,
        "inside_facts": facts,
        "elsewhere": total - inside - facts,
    }


def relationship_map(graph: dict) -> str:
    """Every node's links in both directions: as written, plus each link's opposite."""
    names = {n["slug"]: n["name"] for n in graph["nodes"]}
    rows: dict[str, set[str]] = {n["slug"]: set() for n in graph["nodes"]}
    for e in graph["edges"]:
        rows[e["from_slug"]].add(f"- {e['reason']} [[{e['to_slug']}]]")
        back = MENTIONED_IN if e["kind"] == "mention" else OPPOSITE.get(e["reason"])
        if back:
            rows[e["to_slug"]].add(f"- {back} [[{e['from_slug']}]] (added: opposite)")
        else:
            rows[e["to_slug"]].add(
                f"- [[{e['from_slug']}]] {e['reason']} this (no opposite: verb not in the list)"
            )
    out = [
        "# Relationship map",
        "",
        "Generated by code (`yggdras.data.graph.structural`) from `library/`. Never edit by"
        " hand; edits are overwritten on the next build.",
        "",
        "Each link is written once, in one note. Lines marked `(added: opposite)` are the other"
        " direction, added here.",
    ]
    for slug in sorted(rows):
        out += ["", f"## {names[slug]} (`{slug}`)", ""]
        out += sorted(rows[slug]) or ["- no links"]
    return "\n".join(out) + "\n"


def render(graph: dict) -> str:
    return json.dumps(graph, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def default_out(root: Path) -> Path:
    return root.resolve().parent / ".map" / "graph.json"


def generated_dir(repo: Path) -> Path:
    return repo / LIBRARY / GENERATED


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="structural", description=__doc__.splitlines()[0])
    parser.add_argument("brain", type=Path, help="the brain repo, or a flat brain with --flat")
    parser.add_argument("--flat", action="store_true", help="read every node under BRAIN")
    parser.add_argument("--out", type=Path, help="map path, --flat only")
    args = parser.parse_args(argv)
    if args.out and not args.flat:
        print("--out is for --flat only: library maps stay in the brain repo", file=sys.stderr)
        return 2
    root = args.brain if args.flat else args.brain / LIBRARY
    if not root.is_dir():
        print(f"not a folder: {root}", file=sys.stderr)
        return 2
    shelves = None if args.flat else mapped_shelves()
    graph = build_map(root, shelves)
    out = (args.out or default_out(root)) if args.flat else generated_dir(args.brain) / MAP_FILE
    _write(out, render(graph))
    if not args.flat:
        _write(out.with_name(RELATIONSHIP_MAP), relationship_map(graph))
    raw = count_raw_links(root, shelves)
    counts = {k: len(graph[k]) for k in ("nodes", "edges", "dangling", "errors", "unknown_verbs")}
    print(", ".join(f"{k} {v}" for k, v in counts.items()))
    print(
        f"[[...]] in whole files: {raw['total']} ({raw['inside_links']} in ## Links, "
        f"{raw['inside_facts']} in ## Facts, {raw['elsewhere']} elsewhere)"
    )
    print(f"wrote {out}")
    if raw["elsewhere"]:
        print(
            "STOP: links found outside ## Facts and ## Links. This is a node-format question "
            "(D31), not a parser fix.",
            file=sys.stderr,
        )
    return 1 if graph["errors"] or raw["elsewhere"] else 0


if __name__ == "__main__":
    sys.exit(main())
