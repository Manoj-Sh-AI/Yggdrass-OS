"""Lia's maps (planning/maps-design.md): atlas, shelf map, relationship map, checks."""

import datetime as dt

import pytest

from yggdras.data.graph import structural as st
from yggdras.data.maps import build, checks
from yggdras.data.maps.notes import load_notes

TAXONOMY = """# Taxonomy

### Life areas

| Folder | Holds | Not here |
|---|---|---|
| `01-health/` | Body, sleep, food | — |
| `02-relationships/` | Family and friends. The people are in `11-people/` | Person notes |
| `03-work-career/` | The job | Courses (`04-learning/`) |
| `04-learning/` | Courses and skills | Ideas themselves (`10-ideas/`) |
| `05-money/` | Income | — |
| `06-purpose/` | Values | — |
| `07-home-admin/` | The flat | — |
| `08-rest-joy/` | Hobbies | — |
"""


def note(
    slug,
    *,
    typ="project",
    area="08-rest-joy",
    description=None,
    aliases=(),
    extra="",
    body="## Summary\n\nA summary.\n\n## Facts\n\n- A fact. (src: self, 2030-01-01)\n",
):
    alias_list = ", ".join(f'"{a}"' for a in aliases)
    desc = description if description is not None else f"About {slug.replace('-', ' ')}"
    return (
        f"---\nid: id-{slug}\nslug: {slug}\nname: {slug.replace('-', ' ').title()}\n"
        f'type: {typ}\narea: {area}\n{extra}description: "{desc}"\naliases: [{alias_list}]\n'
        f"updated: 2030-01-02\n---\n\n# {slug}\n\n{body}"
    )


FACT = "- The garden plan has a budget of three hundred euros in total. (src: self, 2030-01-01)"


@pytest.fixture
def brain(tmp_path):
    repo = tmp_path / "brain-repo"

    def write(rel, text):
        path = repo / "library" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    write("00-manual/taxonomy.md", TAXONOMY)
    write(
        "08-rest-joy/hub-rest-joy.md",
        note(
            "hub-rest-joy",
            typ="hub",
            aliases=("hobbies",),
            body="## Summary\n\nRest and joy.\n\n## Links\n\n- lists [[garden-plan]]\n",
        ),
    )
    write(
        "08-rest-joy/garden-plan.md",
        note(
            "garden-plan",
            aliases=("garden",),
            extra="also: [06-purpose]\nreview: 2030-06-01\nstatus: active\n",
            body=f"## Summary\n\nWith [[ana]].\n\n## Facts\n\n{FACT}\n\n## Links\n\n"
            "- depends_on [[ana]]\n- advances [[home-goals]]\n\n## History\n\n"
            "- The plan was smaller. (src: self, 2030-01-01; until: 2030-02-01)\n",
        ),
    )
    write("06-purpose/home-goals.md", note("home-goals", typ="goal", area="06-purpose"))
    write(
        "11-people/ana.md",
        note("ana", typ="person", extra="sensitivity: high\n", description="A neighbour"),
    )
    write("13-sources/garden-book.md", note("garden-book", typ="source"))
    for i, nxt in ((1, 2), (2, 3), (3, None)):
        links = "- part_of [[garden-book]]\n" + (
            f"- precedes [[garden-book-ch-0{nxt}]]\n" if nxt else ""
        )
        write(
            f"13-sources/garden-book/garden-book-ch-0{i}.md",
            note(
                f"garden-book-ch-0{i}",
                typ="source",
                extra=f'pages: "{i}0 to {i}9"\n',
                body=f"## Facts\n\n- A fact. (src: self, 2030-01-01)\n\n## Links\n\n{links}",
            ),
        )
    write(
        "10-ideas/composting.md", note("composting", typ="concept", area="cross", body="## Links\n")
    )
    write("14-inbox/rough.md", "a rough capture\n")
    return repo, write


def maps_of(repo):
    return build.build_maps(repo / "library")


# ---------------------------------------------------------------- the three files


def test_atlas_comes_from_the_taxonomy(brain):
    repo, _ = brain
    atlas = maps_of(repo)["atlas.md"].splitlines()
    assert atlas[1] == "code|area|hub|notes|belongs here|not here|key aliases"
    assert (
        "02|relationships||0|Family and friends. The people are in 11-people/|Person notes|"
        in atlas
    )
    assert "08|rest-joy|hub-rest-joy|7|Hobbies|—|hobbies" in atlas
    assert atlas[-1] == (
        "registries|ideas 10 (1) · people 11 (1) · places 12 (0) · sources 13 (4)"
        " · journal 15 (0) · cross-area (1)"
    )


def test_every_note_once_in_the_shelf_map_with_flags(brain):
    repo, _ = brain
    rows = [r for r in maps_of(repo)["shelf-map.md"].splitlines()[3:] if not r.startswith("## ")]
    slugs = [r.split("|")[0] for r in rows]
    notes = load_notes(repo / "library", st.mapped_shelves())
    assert sorted(slugs) == sorted(notes) and len(slugs) == len(set(slugs)) == 9
    by = {r.split("|")[0]: r.split("|") for r in rows}
    assert by["garden-plan"][7] == "H R:2030-06-01 A:06"
    assert by["garden-plan"][5:7] == ["active", "2030-01-02"]
    assert by["ana"][7] == "S"
    assert by["garden-book-ch-02"][7] == "C:garden-book P:20 to 29"
    assert [f for f in by if "S" in by[f][7].split()] == ["ana"]


def test_relationship_map_has_each_link_with_its_inverse_and_no_hub_links(brain):
    repo, _ = brain
    text = maps_of(repo)["relationship-map.md"]
    lines = dict(
        line.split(": ", 1) for line in text.splitlines() if ": " in line and "|" not in line
    )
    assert lines["garden-plan"] == "advances home-goals · depends_on ana · mentions ana"
    assert lines["ana"] == "mentioned_in garden-plan · needed_by garden-plan"
    assert lines["home-goals"] == "advanced_by garden-plan"
    assert lines["chain garden-book"] == "-ch-01 > -ch-02 > -ch-03"
    body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    assert "lists" not in body and "listed_in" not in body
    assert "part_of" not in body and "precedes" not in body  # folded into the chain


def test_every_non_hub_edge_appears_from_both_ends(brain):
    repo, _ = brain
    root = repo / "library"
    graph = st.build_map(root, st.mapped_shelves())
    text = maps_of(repo)["relationship-map.md"]
    lines = dict(
        line.split(": ", 1) for line in text.splitlines() if ": " in line and "|" not in line
    )
    for e in graph["edges"]:
        a, b = e["from_slug"], e["to_slug"]
        if e["kind"] == "hub" or (
            a.startswith("garden-book-ch") and e["reason"] in ("part_of", "precedes")
        ):
            continue
        assert b in lines[a].split(" · ")[0:] or any(
            x.endswith(" " + b) for x in lines[a].split(" · ")
        )
        assert any(x.endswith(" " + a) for x in lines[b].split(" · "))


# ---------------------------------------------------------------- determinism


def test_same_brain_same_bytes_and_version(brain, tmp_path):
    repo, _ = brain
    build.run(repo, tmp_path / "one")
    build.run(repo, tmp_path / "two")
    for name in (*build.MAP_FILES, build.LINT_FILE):
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()
    header = (tmp_path / "one" / "atlas.md").read_text(encoding="utf-8").splitlines()[0]
    assert "generated" not in header and "commit" not in header and "map_version" in header


def test_version_changes_only_when_inputs_change(brain):
    repo, write = brain
    version = lambda: maps_of(repo)["atlas.md"].splitlines()[0].rsplit(" ", 1)[1]  # noqa: E731
    first = version()
    write("14-inbox/rough.md", "a different rough capture\n")  # not mapped
    assert version() == first
    write("08-rest-joy/new-note.md", note("new-note"))
    assert version() != first


# ---------------------------------------------------------------- checks


def test_no_facts_in_maps(brain):
    repo, write = brain
    root = repo / "library"
    notes = load_notes(root, st.mapped_shelves())
    assert checks.facts_in_maps(maps_of(repo), notes, hard=True) == []
    write(
        "08-rest-joy/garden-plan.md",
        note(
            "garden-plan",
            description="The garden plan has a budget of three hundred euros in total",
            body=f"## Facts\n\n{FACT}\n\n## Links\n\n- depends_on [[ana]]\n",
        ),
    )
    notes = load_notes(root, st.mapped_shelves())
    found = checks.facts_in_maps(maps_of(repo), notes, hard=True)
    assert [(p.severity, p.slug) for p in found] == [("hard", "garden-plan")]


@pytest.mark.parametrize(
    ("description", "extra", "hard", "expected"),
    [
        ("A plan for the shared garden", "", True, []),
        ("Budget of 300 euros for the garden", "", True, [("hard", "dates or figures")]),
        ("Budget of 300 euros for the garden", "", False, [("warning", "dates or figures")]),
        ("Plan | budget", "", False, [("hard", "'|'")]),
        (
            "one two three four five six seven eight nine ten eleven twelve thirteen "
            "fourteen fifteen sixteen",
            "",
            True,
            [("warning", "16 words")],
        ),
        ("The neighbour who helps", "sensitivity: high\n", True, []),
        ("The neighbour with the 2 dogs", "sensitivity: high\n", True, [("hard", "sensitive")]),
        (
            "A neighbour who helps with the garden and its tools",
            "sensitivity: high\n",
            False,
            [("warning", "sensitive")],
        ),
    ],
)
def test_description_rules(brain, description, extra, hard, expected):
    repo, write = brain
    write("08-rest-joy/garden-plan.md", note("garden-plan", description=description, extra=extra))
    meta = load_notes(repo / "library", st.mapped_shelves())["garden-plan"]
    found = [(p.severity, p.message) for p in checks.description_problems(meta, hard)]
    assert len(found) == len(expected)
    for (severity, message), (want_severity, fragment) in zip(found, expected, strict=True):
        assert severity == want_severity and fragment in message


def test_digits_in_the_title_or_an_alias_are_allowed(brain):
    repo, write = brain
    write(
        "08-rest-joy/job-search-2027.md",
        note(
            "job-search-2027",
            description="Search for a full-time role in 2027",
            aliases=("Resume-3",),
        ),
    )
    meta = load_notes(repo / "library", st.mapped_shelves())["job-search-2027"]
    assert checks.description_problems(meta, hard=True) == []


def test_a_framework_keeps_its_claim_in_the_summary(brain):
    repo, _ = brain
    meta = load_notes(repo / "library", st.mapped_shelves())["composting"]
    assert [p.message for p in checks.description_problems(meta, hard=True)] == [
        "a concept keeps its claim or definition in ## Summary, which is empty"
    ]


def test_hard_switch_turns_rules_into_failures(brain, monkeypatch):
    repo, write = brain
    write("08-rest-joy/garden-plan.md", note("garden-plan", description="Budget of 300 euros"))
    monkeypatch.delenv("YGGDRAS_HARD_DESCRIPTION_RULES", raising=False)
    assert build.main([str(repo)]) == 0
    lint = (repo / "library/00-manual/generated/lint.md").read_text(encoding="utf-8")
    assert "hard rules OFF" in lint and "- warning: `garden-plan`: dates or figures" in lint
    monkeypatch.setenv("YGGDRAS_HARD_DESCRIPTION_RULES", "1")
    assert build.main([str(repo)]) == 1


def test_lint_lists_sensitive_descriptions_and_warns_on_size(brain, monkeypatch):
    repo, write = brain
    build.run(repo)
    lint = (repo / "library/00-manual/generated/lint.md").read_text(encoding="utf-8")
    assert "- `ana`: A neighbour" in lint and "WARNING" not in lint
    monkeypatch.setattr(build, "WARN_TOKENS", 10)
    build.run(repo)
    lint = (repo / "library/00-manual/generated/lint.md").read_text(encoding="utf-8")
    assert "**WARNING:** over 10" in lint


def test_size_log_appends_one_dated_line(brain):
    repo, _ = brain
    build.run(repo, log_day=dt.date(2030, 2, 1))
    build.run(repo, log_day=dt.date(2030, 3, 1))
    log = (repo / "library/00-manual/generated/map-size-log.md").read_text(encoding="utf-8")
    assert log.count("- 2030-") == 2 and "- 2030-03-01: 9 notes" in log
    assert log.startswith("# Map size log")


def test_the_brain_notes_are_never_written(brain):
    repo, _ = brain
    before = {p: p.read_bytes() for p in (repo / "library").rglob("*.md")}
    build.run(repo)
    assert all(p.read_bytes() == b for p, b in before.items())


def test_structural_pass_writes_the_maps(brain):
    repo, _ = brain
    st.main([str(repo)])
    out = repo / "library/00-manual/generated"
    assert {p.name for p in out.iterdir()} == {"map.json", *build.MAP_FILES, build.LINT_FILE}


# ---------------------------------------------------------------- citation check (D34)

GARDEN = note(
    "garden-plan",
    body=f"## Facts\n\n{FACT}\n\n## History\n\n"
    "- The plan was smaller. (src: self, 2030-01-01; until: 2030-02-01)\n",
)


def test_citation_check():
    opened = {"garden-plan": GARDEN}
    answer = (
        'It costs three hundred. [[garden-plan]] "The garden plan has a budget of three hundred '
        'euros in total." It was smaller. [[garden-plan]] "The plan was  smaller" '
        'It has a pond. [[garden-plan]] "The garden plan has a pond." '
        'Ana helps. [[ana]] "Ana helps with the garden."'
    )
    results = [(c.ok, c.reason) for c in checks.check_citations(answer, opened)]
    assert results == [
        (True, ""),
        (True, ""),  # History counts; whitespace and the final full stop are normalised
        (False, "not a fact line of that note, word for word"),
        (False, "note was not opened for this question"),
    ]


def test_citation_must_be_the_whole_line_not_a_fragment():
    opened = {"garden-plan": GARDEN}
    (result,) = checks.check_citations('[[garden-plan]] "a budget of three hundred"', opened)
    assert not result.ok
