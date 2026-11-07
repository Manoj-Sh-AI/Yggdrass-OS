"""Uploaded markdown, split by its own headings (node.md "Long sources"; D37). Free code.

A file is long when it is more than about two pages (LONG_CHARS) and has at least three
sections: it becomes one source note plus chunk notes of about a page each (sections merged
in order until a chunk reaches PAGE_CHARS). A short file stays whole.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PAGE_CHARS = 3000  # about a page
LONG_CHARS = 6000  # about two pages
MIN_SECTIONS = 3
MARKDOWN = (".md", ".markdown")


@dataclass(frozen=True)
class Section:
    title: str
    text: str  # the section's own text, its heading line included


@dataclass(frozen=True)
class Chunk:
    n: int  # 1-based
    titles: tuple[str, ...]
    text: str

    @property
    def title(self) -> str:
        return self.titles[0] if len(self.titles) == 1 else f"{self.titles[0]} to {self.titles[-1]}"


def sections(text: str) -> tuple[str, list[Section]]:
    """(text before the first heading, the sections) at the file's main heading level: ## if it
    has any, else #."""
    lines = text.splitlines(keepends=True)
    level = "## " if any(ln.startswith("## ") for ln in lines) else "# "
    intro, out, title, body = [], [], None, []
    for ln in lines:
        if ln.startswith(level):
            if title is not None:
                out.append(Section(title, "".join(body)))
            title, body = ln[len(level) :].strip().strip("#").strip(), [ln]
        elif title is None:
            intro.append(ln)
        else:
            body.append(ln)
    if title is not None:
        out.append(Section(title, "".join(body)))
    return "".join(intro), out


def is_long(text: str) -> bool:
    return len(text) > LONG_CHARS and len(sections(text)[1]) >= MIN_SECTIONS


def chunks(text: str) -> list[Chunk]:
    """Sections merged in order into chunks of about a page (a long section stays whole)."""
    _, secs = sections(text)
    out, titles, body = [], [], ""
    for s in secs:
        if titles and len(body) + len(s.text) > PAGE_CHARS:
            out.append(Chunk(len(out) + 1, tuple(titles), body))
            titles, body = [], ""
        titles.append(s.title)
        body += s.text
    if titles:
        out.append(Chunk(len(out) + 1, tuple(titles), body))
    return out


def is_markdown(filename: str) -> bool:
    return filename.lower().endswith(MARKDOWN)


def raw_name(filename: str, today: str) -> str:
    """The verbatim copy's file name in the brain's raw/ folder: "<date>-<safe name>"."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", filename.strip()).strip("-.") or "upload.md"
    return f"{today}-{safe}"
