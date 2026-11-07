"""Note text edits for the write path (D36): pure functions, text in, text out.

Every edit keeps the note's shape (node.md): frontmatter, `# Title`, `## Summary`, `## Facts`,
the type's sections, `## Links`, `## History`. Nothing here touches a file or decides whether
an edit is allowed: the checker does that.
"""

from __future__ import annotations

import re

from yggdras.data.graph import structural as st
from yggdras.data.maps import checks

NOT_RECORDED = "Not recorded yet."
# node.md's essential sections per type (after Summary and Facts, before Links).
TYPE_SECTIONS = {
    "person": ("Who", "Commitments", "Log"),
    "place": ("What and where",),
    "project": ("Outcome", "Next action"),
    "goal": ("Outcome", "Why", "Obstacle", "If-then plans"),
    "decision": ("Context", "Options", "Choice and reasoning", "Expected outcome", "State"),
    "event": ("What happened", "Learned / felt"),
    "source": ("Key claims", "My reaction"),
    "framework": ("When to use", "When not to use", "Steps", "Use log"),
    "topic": (),
    "concept": ("Definition", "Where I have seen it"),
}
# node.md: status is essential for these, with these starting values.
FIRST_STATUS = {"project": "active", "goal": "active", "decision": "open"}
SRC = re.compile(r"\(src:[^()]*\)\s*\.?\s*$")


def _quote(value: str) -> str:
    """A YAML double-quoted string."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def new_note(
    *,
    id: str,
    slug: str,
    name: str,
    type: str,
    area: str,
    description: str,
    aliases: list[str],
    created: str,
    summary: str = "",
    facts: list[str] = (),
    links: list[tuple[str, str]] = (),
    sensitive: bool = False,
    also: list[str] = (),
) -> str:
    """A new note in node.md's shape. Facts are full lines without "- " (their source bracket
    included); links are (verb, slug). Essential sections the type needs and Lia has no text
    for say "Not recorded yet." (a lint warning, never a failure)."""
    fm = [
        "---",
        f"id: {id}",
        f"slug: {slug}",
        f"name: {_quote(name)}",
        f"type: {type}",
        f"area: {area}",
    ]
    if also:
        fm.append("also: [" + ", ".join(also) + "]")
    fm.append(f"description: {_quote(description)}")
    fm.append("aliases: [" + ", ".join(_quote(a) for a in aliases) + "]")
    if type in FIRST_STATUS:
        fm.append(f"status: {FIRST_STATUS[type]}")
    if sensitive:
        fm.append("sensitivity: high")
    fm += [f"created: {created}", f"updated: {created}", "---"]
    body = ["", f"# {name}", "", "## Summary", "", summary.strip() or NOT_RECORDED, ""]
    if type != st.HUB:
        body += ["## Facts", ""] + [f"- {f}" for f in facts] + ([""] if facts else [])
    for heading in TYPE_SECTIONS.get(type, ()):
        body += [f"## {heading}", "", NOT_RECORDED, ""]
    body += ["## Links", ""] + [f"- {verb} [[{target}]]" for verb, target in links]
    return "\n".join(fm + body).rstrip() + "\n"


# ---------------------------------------------------------------- sections


def _lines(text: str) -> list[str]:
    return text.split("\n")


def _join(lines: list[str]) -> str:
    out = "\n".join(lines)
    return out if out.endswith("\n") else out + "\n"


def _body_start(lines: list[str]) -> int:
    """Index of the first line after the frontmatter (0 if there is none)."""
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return i + 1
    return 0


def _section_span(lines: list[str], heading: str) -> tuple[int, int] | None:
    """(index of the heading line, index after the section's last line)."""
    start = _body_start(lines)
    for i in range(start, len(lines)):
        if lines[i].strip() == heading:
            end = i + 1
            while end < len(lines) and not lines[end].startswith("## "):
                end += 1
            return i, end
    return None


def _ensure_section(lines: list[str], heading: str, before: tuple[str, ...]) -> tuple[int, int]:
    """The span of *heading*, adding an empty section first if needed: just before the first
    heading in *before* that exists, else at the end."""
    span = _section_span(lines, heading)
    if span:
        return span
    at = next((s[0] for s in (_section_span(lines, o) for o in before) if s), None)
    if at is None:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ["", heading, ""]
    else:
        lines[at:at] = [heading, "", ""]
    return _section_span(lines, heading)


def _insert_item(lines: list[str], span: tuple[int, int], item: str) -> None:
    """*item* after the section's last item, keeping one blank line after the heading and one
    before the next heading."""
    head, end = span
    last = None
    for i in range(head + 1, end):
        if lines[i].strip():
            last = i
    if last is None:  # an empty section
        at = head + 1
        if at < len(lines) and not lines[at].strip():
            at += 1
        else:
            lines.insert(at, "")
            at += 1
    else:
        at = last + 1
    lines.insert(at, item)
    if at + 1 < len(lines) and lines[at + 1].startswith("## "):
        lines.insert(at + 1, "")


# ---------------------------------------------------------------- facts


def fact_lines(text: str) -> list[str]:
    """The note's current Facts lines, without "- "."""
    lines = _lines(text)
    span = _section_span(lines, st.FACTS_HEADING)
    if not span:
        return []
    return [ln[2:].strip() for ln in lines[span[0] + 1 : span[1]] if ln.startswith("- ")]


def history_lines(text: str) -> list[str]:
    lines = _lines(text)
    span = _section_span(lines, st.HISTORY_HEADING)
    if not span:
        return []
    return [ln[2:].strip() for ln in lines[span[0] + 1 : span[1]] if ln.startswith("- ")]


def _find_fact(lines: list[str], fact: str) -> int | None:
    span = _section_span(lines, st.FACTS_HEADING)
    if not span:
        return None
    unit = checks.quote_unit(fact)
    found = [
        i
        for i in range(span[0] + 1, span[1])
        if lines[i].startswith("- ") and checks.quote_unit(lines[i]) == unit
    ]
    return found[0] if len(found) == 1 else None


def add_fact(text: str, fact: str) -> str:
    """*fact* (a full line without "- ") at the end of ## Facts."""
    lines = _lines(text)
    span = _ensure_section(lines, st.FACTS_HEADING, (st.LINKS_HEADING, st.HISTORY_HEADING))
    _insert_item(lines, span, f"- {fact.strip()}")
    return _join(lines)


def tagged(fact: str, tag: str) -> str:
    """The fact line with *tag* ("until: 2026-11-07" or "wrong: <reason>") added inside its
    source bracket, as node.md writes History lines."""
    line = fact.strip()
    m = SRC.search(line)
    if not m:
        return f"{line.rstrip('.')}. ({tag})"
    bracket = m.group(0).strip().rstrip(".").rstrip()
    return line[: m.start()].rstrip() + " " + bracket[:-1] + f"; {tag})"


def to_history(text: str, fact: str, tag: str, replacement: str | None = None) -> str | None:
    """Move *fact* from Facts to History with *tag*; with *replacement*, the new line takes
    its place in Facts. None if the fact is not (exactly once) in Facts."""
    lines = _lines(text)
    i = _find_fact(lines, fact)
    if i is None:
        return None
    old = lines[i][2:].strip()
    if replacement is None:
        del lines[i]
    else:
        lines[i] = f"- {replacement.strip()}"
    span = _ensure_section(lines, st.HISTORY_HEADING, ())
    _insert_item(lines, span, f"- {tagged(old, tag)}")
    return _join(lines)


# ---------------------------------------------------------------- links


def link_lines(text: str) -> list[tuple[str, str]]:
    """(verb, target as written) for each link line in ## Links."""
    lines = _lines(text)
    span = _section_span(lines, st.LINKS_HEADING)
    if not span:
        return []
    out = []
    for ln in lines[span[0] + 1 : span[1]]:
        m = st.LINK_LINE.match(ln)
        if m:
            out.append((m.group(1).strip(), m.group(2)))
    return out


def add_link(text: str, verb: str, target: str) -> str:
    lines = _lines(text)
    span = _ensure_section(lines, st.LINKS_HEADING, (st.HISTORY_HEADING,))
    _insert_item(lines, span, f"- {verb} [[{target}]]")
    return _join(lines)


def remove_link(text: str, verb: str | None, target: str) -> tuple[str, int]:
    """Remove the ## Links lines to *target* (with *verb*, or any verb when None). Returns the
    text and how many lines went."""
    lines = _lines(text)
    span = _section_span(lines, st.LINKS_HEADING)
    if not span:
        return text, 0
    keep, gone = [], 0
    for i, ln in enumerate(lines):
        m = st.LINK_LINE.match(ln) if span[0] < i < span[1] else None
        if (
            m
            and st.normalize(m.group(2)) == st.normalize(target)
            and (verb is None or m.group(1).strip() == verb)
        ):
            gone += 1
            continue
        keep.append(ln)
    return _join(keep), gone


def unwrap_mentions(text: str, target: str, name: str) -> tuple[str, int]:
    """Outside ## Links and ## History, "[[target]]" becomes the plain *name* (the note it
    named is archived). Returns the text and how many mentions changed."""
    lines = _lines(text)
    start, heading, count = _body_start(lines), None, 0
    pattern = re.compile(r"\[\[([^\]|]+)\]\]")
    for i in range(start, len(lines)):
        if lines[i].startswith("## "):
            heading = lines[i].strip()
            continue
        if heading in (st.LINKS_HEADING, st.HISTORY_HEADING):
            continue

        def swap(m):
            nonlocal count
            if st.normalize(m.group(1)) == st.normalize(target):
                count += 1
                return name
            return m.group(0)

        lines[i] = pattern.sub(swap, lines[i])
    return _join(lines), count


# ---------------------------------------------------------------- frontmatter and hubs


def set_field(text: str, name: str, value: str) -> str:
    """Set a scalar frontmatter field (added before the closing --- if missing)."""
    lines = _lines(text)
    end = _body_start(lines) - 1
    if end <= 0:
        return text
    for i in range(1, end):
        if re.match(rf"{re.escape(name)}\s*:", lines[i]):
            lines[i] = f"{name}: {value}"
            return _join(lines)
    lines.insert(end, f"{name}: {value}")
    return _join(lines)


def hub_listing(text: str, slug: str, add: bool) -> str:
    """Add or remove "- lists [[slug]]" in a hub, keeping the list sorted, and keep its
    "Notes so far: N." count in step."""
    if add:
        lines = _lines(text)
        span = _ensure_section(lines, st.LINKS_HEADING, (st.HISTORY_HEADING,))
        items = [i for i in range(span[0] + 1, span[1]) if lines[i].startswith("- lists [[")]
        new = f"- lists [[{slug}]]"
        at = next((i for i in items if lines[i] > new), None)
        if at is None:
            _insert_item(lines, span, new)
        else:
            lines.insert(at, new)
        text = _join(lines)
    else:
        text, _ = remove_link(text, "lists", slug)
    count = sum(1 for verb, _ in link_lines(text) if verb == "lists")
    return re.sub(r"Notes so far: \d+\.", f"Notes so far: {count}.", text)
