"""Structural pass: build the brain's map from frontmatter and hand-written links.

No model, no database, byte-identical output for unchanged input (D5, D6, D8).
Spec: requirements/spec-phase-1b-structural-pass.md

Usage:
    python -m yggdras.data.graph.structural BRAIN_REPO
    python -m yggdras.data.graph.structural BRAIN_ROOT --flat [--out PATH]

The first form reads only BRAIN_REPO/library/ (the numbered folders, minus the manual and
the inbox), checks the library rules, and writes the map and the relationship map to
library/00-manual/generated/. The second reads every node under a flat brain such as the
archived Apollo demo brain, without the library rules.
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

SCHEMA = "yggdras-map/3"
LIBRARY = "library"
# The library's folders, in order (D31 amendments A1, A17). The only list of folder names
# in code. 09 is left free for a future area.
SHELVES = (
    "00-manual",
    "01-health",
    "02-relationships",
    "03-work-career",
    "04-learning",
    "05-money",
    "06-purpose",
    "07-home-admin",
    "08-rest-joy",
    "10-ideas",
    "11-people",
    "12-places",
    "13-sources",
    "14-inbox",
    "15-journal",
)
NOT_MAPPED = ("00-manual", "14-inbox")
# Allowed values of a note's `area` and `also` (A18): the life-area folders, plus "cross".
AREAS = tuple(s for s in SHELVES if "01" <= s[:2] <= "08")
CROSS = "cross"
CONTENT_TYPES = (
    "person",
    "place",
    "project",
    "goal",
    "decision",
    "event",
    "source",
    "framework",
    "concept",
)
HUB, JOURNAL = "hub", "journal"  # structural types (A19, A20)
GENERATED = Path("00-manual") / "generated"
MAP_FILE = "map.json"
RELATIONSHIP_MAP = "relationship-map.md"

FACTS_HEADING = "## Facts"
LINKS_HEADING = "## Links"
HISTORY_HEADING = "## History"
WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
# Text after the [[slug]] (e.g. "— since 2026-01") is ignored for now.
LINK_LINE = re.compile(r"^- (.*?)\[\[([^\]]+)\]\]")
_NORM_EXTRA = {"ß": "ss", "ø": "o"}

# The fixed link verbs and their opposites (A5 as amended by A14 and A19). A link is
# written once; the relationship map adds the other direction.
VERBS = {
    "part_of": "has_part",
    "broader": "narrower",
    "related_to": "related_to",
    "about": "subject_of",
    "derived_from": "source_of",
    "cites": "cited_by",
    "supports": "supported_by",
    "contradicts": "contradicts",
    "supersedes": "superseded_by",
    "depends_on": "needed_by",
    "created_by": "created",
    "knows": "knows",
    "member_of": "has_member",
    "works_on": "worked_on_by",
    "took_part_in": "had_participant",
    "located_in": "location_of",
    "advances": "advanced_by",
    "informed_by": "informed",
    "uses": "used_in",
    "led_to": "caused_by",
    "precedes": "follows",
    "lists": "listed_in",
}
OPPOSITE = {**VERBS, **{back: verb for verb, back in VERBS.items()}}
# Hub links are kept apart so discovery can ignore them.
HUB_VERBS = ("lists", "listed_in")
# A [[link]] in a section other than Links or History is a plain mention (A6, A11).
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
    area: str = ""
    also: list[str] = field(default_factory=list)
    fact_lines: int = 0
    # (kind, line, reason, written_as); kind is "link", "hub" or "mention"
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


def sections(body: list[str], first_line: int) -> list[tuple[str | None, int, str]]:
    """Every body line as (heading it sits under, or None before the first one; number; text)."""
    out, current = [], None
    for offset, line in enumerate(body):
        if line.startswith("## "):
            current = line.strip()
            continue
        out.append((current, first_line + offset, line))
    return out


def _as_list(value) -> list[str]:
    if value is None:
        return []
    return [str(v) for v in value] if isinstance(value, list) else [str(value)]


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
        aliases=_as_list(fm.get("aliases")),
        area=str(fm.get("area") or ""),
        also=_as_list(fm.get("also")),
    )
    for heading, number, line in sections(body, first_line):
        if heading == LINKS_HEADING:
            m = LINK_LINE.match(line)
            if m:
                reason = m.group(1).strip()
                kind = "hub" if reason in HUB_VERBS else "link"
                node.links.append((kind, number, reason, m.group(2)))
        elif heading == HISTORY_HEADING:
            continue  # history is never current: its links stay out of the map
        elif heading is not None or node.type == JOURNAL:
            if heading == FACTS_HEADING and line.startswith("- "):
                node.fact_lines += 1
            for written in WIKILINK.findall(line):
                node.links.append(("mention", number, MENTION, written))
    return node, None


def mapped_shelves() -> tuple[str, ...]:
    return tuple(s for s in SHELVES if s not in NOT_MAPPED)


def node_files(root: Path, shelves: tuple[str, ...] | None = None) -> list[Path]:
    """Node files under *root*. With *shelves*, only files inside those top-level folders."""
    if shelves is None:
        return sorted(p for p in root.rglob("*.md") if p != root / "index.md")
    return sorted(p for s in shelves if (root / s).is_dir() for p in (root / s).rglob("*.md"))


def library_problems(root: Path) -> list[dict]:
    """Anything at the top of the library that is not one of the numbered folders."""
    return [
        {"path": p.name, "problem": "not a shelf: not in the numbered folder list"}
        for p in sorted(root.iterdir())
        if p.name not in SHELVES and not p.name.startswith(".")
    ]


def rule_problems(node: Node) -> list[str]:
    """The library's note rules: type, area, also, and no facts in a hub (A9-A21)."""
    problems = []
    if node.type not in (*CONTENT_TYPES, HUB, JOURNAL):
        problems.append(f"unknown type '{node.type}'")
    allowed = (*AREAS, CROSS)
    if not node.area:
        problems.append("missing area")
    elif node.area not in allowed:
        problems.append(f"area '{node.area}' is not one of {', '.join(allowed)}")
    bad_also = [a for a in node.also if a not in allowed]
    if bad_also:
        problems.append(f"also has unknown area(s): {', '.join(bad_also)}")
    if node.type == HUB and node.fact_lines:
        problems.append("a hub holds no facts of its own")
    return problems


def duplicate_aliases(nodes: dict[str, Node]) -> list[dict]:
    """An alias that matches another note's slug or alias, after D02 normalization."""
    owners: dict[str, set[str]] = {}
    for node in nodes.values():
        for name in (node.slug, *node.aliases):
            owners.setdefault(normalize(name), set()).add(node.slug)
    out = []
    for node in nodes.values():
        for alias in node.aliases:
            others = sorted(owners.get(normalize(alias), set()) - {node.slug})
            if others:
                out.append(
                    {
                        "path": node.path,
                        "problem": f"alias '{alias}' is also used by {', '.join(others)}",
                    }
                )
    return out


def build_map(root: Path, shelves: tuple[str, ...] | None = None) -> dict:
    """Build the map for the brain at *root*. Never writes to the brain.

    With *shelves* (a library), only those top-level folders are read and the library's
    note rules are checked; without, every node under *root* except `index.md` (a flat
    brain such as the Apollo demo).
    """
    library = shelves is not None
    nodes: dict[str, Node] = {}
    errors: list[dict] = library_problems(root) if library else []
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
            if library:
                errors += [{"path": rel, "problem": p} for p in rule_problems(node)]
    if library:
        errors += duplicate_aliases(nodes)

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
            if kind != "mention" and reason not in OPPOSITE:
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


def _note_type(fm_text: str) -> str:
    try:
        return str((yaml.safe_load(fm_text) or {}).get("type") or "")
    except yaml.YAMLError:
        return ""


def count_raw_links(root: Path, shelves: tuple[str, ...] | None = None) -> dict[str, int]:
    """Count every [[...]] across whole files by plain text, by where it sits.

    `in_links` and `in_history` are the Links and History sections; `in_sections` is every
    other section (mentions); `elsewhere` is outside any section, which stops the pass.
    """
    counts = {"total": 0, "in_links": 0, "in_history": 0, "in_sections": 0, "elsewhere": 0}
    for path in node_files(root, shelves):
        text = path.read_text(encoding="utf-8")
        counts["total"] += len(WIKILINK.findall(text))
        parts = _split(text)
        if not parts:
            continue
        journal = _note_type(parts[0]) == JOURNAL
        for heading, _, line in sections(parts[1], parts[2]):
            n = len(WIKILINK.findall(line))
            if heading == LINKS_HEADING:
                counts["in_links"] += n
            elif heading == HISTORY_HEADING:
                counts["in_history"] += n
            elif heading is not None or journal:
                counts["in_sections"] += n
            else:
                counts["elsewhere"] += n
    return counts


def relationship_map(graph: dict) -> str:
    """Every node's links in both directions: as written, plus each link's opposite."""
    names = {n["slug"]: n["name"] for n in graph["nodes"]}
    rows: dict[str, set[str]] = {n["slug"]: set() for n in graph["nodes"]}
    for e in graph["edges"]:
        hub = " (hub link)" if e["kind"] == "hub" else ""
        rows[e["from_slug"]].add(f"- {e['reason']} [[{e['to_slug']}]]{hub}")
        back = MENTIONED_IN if e["kind"] == "mention" else OPPOSITE.get(e["reason"])
        if back:
            note = "added: opposite, hub link" if hub else "added: opposite"
            rows[e["to_slug"]].add(f"- {back} [[{e['from_slug']}]] ({note})")
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
        " direction, added here. Lines marked `hub link` come from a hub's `lists`;"
        " discovery ignores them.",
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
        f"[[...]] in whole files: {raw['total']} ({raw['in_links']} in ## Links, "
        f"{raw['in_sections']} as mentions, {raw['in_history']} in ## History, "
        f"{raw['elsewhere']} outside any section)"
    )
    print(f"wrote {out}")
    if raw["elsewhere"]:
        print(
            "STOP: links found outside any section. This is a node-format question (D31), "
            "not a parser fix.",
            file=sys.stderr,
        )
    return 1 if graph["errors"] or raw["elsewhere"] else 0


if __name__ == "__main__":
    sys.exit(main())
