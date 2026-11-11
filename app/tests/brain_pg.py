"""A throwaway PostgreSQL for the brain_db tests, and a small brain of INVENTED notes.

The cluster is made with initdb in a temp folder, started on a free localhost port with trust
auth, and stopped and deleted after the session. Tests skip when no PostgreSQL binaries are
found (YGGDRAS_PG_BIN, PATH, or C:\\Program Files\\PostgreSQL\\<n>\\bin). Never the user's
database, never BRAIN_DATABASE_URL.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path

from yggdras.data.graph import structural as st


def pg_bin() -> Path | None:
    configured = os.environ.get("YGGDRAS_PG_BIN")
    if configured and (Path(configured) / _exe("initdb")).is_file():
        return Path(configured)
    found = shutil.which("initdb")
    if found:
        return Path(found).parent
    roots = sorted(Path("C:/Program Files/PostgreSQL").glob("*/bin"), reverse=True)
    return next((r for r in roots if (r / _exe("initdb")).is_file()), None)


def _exe(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Cluster:
    def __init__(self, bin_dir: Path, data: Path):
        self.bin, self.data, self.port = bin_dir, data, free_port()

    def run(self, name: str, *args: str) -> None:
        # No pipes: the server pg_ctl starts would inherit them and keep them open.
        subprocess.run(
            [str(self.bin / _exe(name)), *args],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )

    def start(self) -> str:
        self.run("initdb", "-D", str(self.data), "-U", "postgres", "-A", "trust", "-E", "UTF8",
                 "--locale=C")  # fmt: skip
        self.run("pg_ctl", "-D", str(self.data), "-l", str(self.data / "server.log"), "-w",
                 "-o", f"-p {self.port} -h 127.0.0.1", "start")  # fmt: skip
        return f"postgresql://postgres@127.0.0.1:{self.port}/postgres"

    def stop(self) -> None:
        self.run("pg_ctl", "-D", str(self.data), "-m", "fast", "-w", "stop")


# ---------------------------------------------------------------- an invented brain

TAXONOMY = """# Taxonomy

| Folder | Holds | Not here |
|---|---|---|
| `01-health/` | Body and sleep | — |
| `02-relationships/` | Friends and family | Person notes |
| `03-work-career/` | The day job | Courses (`04-learning/`) |
| `04-learning/` | Courses and crafts being learned | Ideas themselves (`10-ideas/`) |
| `05-money/` | Budgets | — |
| `06-purpose/` | Values | — |
| `07-home-admin/` | Papers | — |
| `08-rest-joy/` | Hobbies and fun | — |
"""


def node_rules() -> str:
    rows = [
        f"| {i} | `{verb}` | `{inverse}` | invented use {i} |"
        for i, (verb, inverse) in enumerate(st.VERBS.items(), 1)
    ]
    return "# Node\n\n## Link verbs\n\n| # | Verb | Inverse | Use |\n|---|---|---|---|\n" + (
        "\n".join(rows) + "\n\n## After\n"
    )


def note(slug, name, type_, area, *, folder, extra="", aliases=(), facts=(), history=(),
         links=(), summary="Summary.") -> tuple[str, str]:  # fmt: skip
    head = [
        "---",
        f"id: {slug}-id",
        f"slug: {slug}",
        f"name: {name}",
        f"type: {type_}",
        f"area: {area}",
        f"description: {name} in a few invented words",
        "aliases: [" + ", ".join(aliases) + "]",
        "created: 2030-01-01",
        "updated: 2030-03-02",
    ]
    head += [line for line in extra.splitlines() if line]
    body = [*head, "---", "", "## Summary", "", summary, "", "## Facts", ""]
    body += [f"- {f}" if "(src:" in f else f"- {f} (src: self, 2030-01-05)" for f in facts]
    if history:
        body += ["", "## History", ""] + [f"- {h} (src: self, 2030-01-05; until: 2030-02-01)"
                                          for h in history]  # fmt: skip
    body += ["", "## Links", ""] + [f"- {link}" for link in links]
    return f"{folder}/{slug}.md", "\n".join(body) + "\n"


def brain_files(*, messy: bool = False) -> dict[str, str]:
    """An invented pottery-hobby brain: 12 notes, hubs, a chunked source, an inverse-verb
    link, mentions, a cross note, several secondary areas, aliases out of alphabetical order
    and dates inside fact lines. *messy* adds what the loader must refuse to place."""
    notes = [
        note("hub-learning", "Learning hub", "hub", "04-learning", folder="04-learning",
             aliases=["learning hub"], facts=(),
             links=["lists [[pottery-course]]", "lists [[glaze-chemistry]]"]),
        note("pottery-course", "Pottery Course", "project", "04-learning", folder="04-learning",
             extra="status: active\nreview: 2030-05-01", aliases=["pottery", "clay class"],
             facts=["The course runs on Saturdays", "Taught by [[ada-lin]] at the studio",
                    "The exhibition is on 2030-07-15"],
             history=["The course ran on Fridays"],
             links=["related_to [[glaze-chemistry]]", "uses [[wheel-throwing]]",
                    "created_by [[ada-lin]]"]),
        note("glaze-chemistry", "Glaze Chemistry", "concept", "04-learning", folder="10-ideas",
             extra="also: [08-rest-joy, 01-health]", facts=["Glazes melt into glass"],
             links=["broader [[wheel-throwing]]", "has_part [[pottery-course]]"]),
        note("wheel-throwing", "Wheel Throwing", "framework", "08-rest-joy", folder="10-ideas",
             facts=["Centre the clay first"], links=["related_to [[ada-lin]]"]),
        note("ada-lin", "Ada Lin", "person", "08-rest-joy", folder="11-people",
             extra="sensitivity: high", aliases=["Ada"],
             facts=["Ada teaches pottery",
                    "Ada runs the studio (src: self, 2030-01-05; valid: 2030-02..)"],
             links=["knows [[pottery-course]]"]),
        note("hub-rest-joy", "Rest and joy hub", "hub", "08-rest-joy", folder="08-rest-joy",
             aliases=["fun hub"], links=["lists [[kiln-decision]]", "lists [[studio-open-day]]"]),
        note("kiln-decision", "Kiln Decision", "decision", "08-rest-joy", folder="08-rest-joy",
             extra="status: decided\ndecided: 2030-02-10\nreview: 2030-06-01",
             facts=["Chose the shared kiln", "The kiln arrives in March 2030"],
             links=["uses [[wheel-throwing]]", "informed_by [[clay-handbook]]"]),
        note("studio-open-day", "Studio Open Day", "event", "08-rest-joy", folder="08-rest-joy",
             extra="date: 2030-04-12\nend: 2030-04-13", facts=["Open day at the studio"],
             links=["about [[pottery-course]]"]),
        note("clay-handbook", "Clay Handbook", "source", "04-learning", folder="13-sources",
             facts=["A handbook about clay bodies"], links=["about [[glaze-chemistry]]"]),
        note("clay-handbook-part-1", "Clay Handbook, part 1", "source", "04-learning",
             folder="13-sources/clay-handbook", extra='pages: "1 to 20"',
             facts=["Part one covers clay types"],
             links=["part_of [[clay-handbook]]", "precedes [[clay-handbook-part-2]]"]),
        note("clay-handbook-part-2", "Clay Handbook, part 2", "source", "04-learning",
             folder="13-sources/clay-handbook", extra='pages: "21 to 40"',
             facts=["Part two covers firing"], links=["part_of [[clay-handbook]]"]),
    ]  # fmt: skip
    notes.append(
        note("odd-idea", "Odd Idea", "concept", "cross", folder="10-ideas",
             extra="also: [04-learning]", aliases=["odd one"],
             summary="An idea that came from [[wheel-throwing]].",
             facts=["An idea for no single area"], links=["related_to [[glaze-chemistry]]"])
    )  # fmt: skip
    if messy:
        notes += [
            note("night-walks", "Night Walks", "topic", "01-health", folder="01-health",
                 extra="review: someday", aliases=["Ada"], facts=["Walks help sleep"],
                 links=["related_to [[night-walks]]", "related_to [[missing-note]]",
                        "frobs [[ada-lin]]"]),
            note("lost-book-part-1", "Lost Book, part 1", "source", "04-learning",
                 folder="13-sources/lost-book", extra='pages: "1 to 9"',
                 facts=["A chunk whose source note is missing"], links=["about [[odd-idea]]"]),
        ]  # fmt: skip
    files = {f"library/{rel}": text for rel, text in notes}
    files["library/00-manual/taxonomy.md"] = TAXONOMY
    files["library/00-manual/node.md"] = node_rules()
    return files


def make_brain(root: Path, *, messy: bool = False) -> Path:
    for rel, text in brain_files(messy=messy).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8", newline="\n")
    return root
