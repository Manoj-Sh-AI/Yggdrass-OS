"""Structural pass over a library: D31 amendments A1, A5, A6 and A9-A21."""

import hashlib

import pytest

from yggdras.data.graph import structural as st


def note(
    slug,
    *,
    typ="project",
    area="08-rest-joy",
    aliases=(),
    extra="",
    body=(
        "## Summary\n\nA summary.\n\n## Facts\n\n- A fact. (src: self, 2030-01-01)\n\n"
        "## Links\n\n- related_to [[ana]]\n"
    ),
):
    alias_list = ", ".join(f'"{a}"' for a in aliases)
    return (
        f"---\nid: id-{slug}\nslug: {slug}\nname: {slug}\ntype: {typ}\n"
        + (f"area: {area}\n" if area else "")
        + extra
        + f"description: About {slug}\naliases: [{alias_list}]\n---\n\n# {slug}\n\n{body}"
    )


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "brain-repo"

    def write(rel, text):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    write(
        "library/08-rest-joy/garden-plan.md",
        note(
            "garden-plan",
            body=(
                "## Summary\n\nStarted with [[ana]].\n\n"
                "## Facts\n\n- The garden plan has a budget of 300 euros."
                " (src: self, 2030-01-01)\n\n"
                "## Links\n\n- part_of [[home-goals]]\n- depends_on [[ana]] — since 2030-01\n"
            ),
        ),
    )
    write(
        "library/06-purpose/home-goals.md",
        note(
            "home-goals",
            typ="goal",
            area="06-purpose",
            body="## Facts\n\n- A fact. (src: self, 2030-01-01)\n\n## Links\n\n"
            "- related_to [[garden-plan]]\n",
        ),
    )
    write(
        "library/11-people/ana.md",
        note(
            "ana",
            typ="person",
            body="## Facts\n\n- A fact. (src: self, 2030-01-01)\n\n## Links\n\n"
            "- waters [[garden-plan]]\n",
        ),
    )
    # Never read: the manual, the inbox, and everything outside library/.
    write("library/00-manual/taxonomy.md", "# Taxonomy\n")
    write("library/14-inbox/rough.md", "a rough capture with [[ana]]\n")
    write("README.md", "# Brain\n")
    write("evals/hard-v1.md", "1. A question about [[ana]]?\n")
    write("archive/demo-brain/people/old.md", note("old"))
    write("private/notes.md", "private\n")
    write("brain/areas/scaffold.md", "no frontmatter\n")
    return root, write


def build(root):
    return st.build_map(root / "library", st.mapped_shelves())


def edges_from(graph, slug):
    return [e for e in graph["edges"] if e["from_slug"] == slug]


def problems(graph):
    return {(e["path"], e["problem"]) for e in graph["errors"]}


def test_folder_names_are_the_numbered_list():
    assert st.SHELVES == (
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
    assert st.mapped_shelves() == tuple(s for s in st.SHELVES if s not in ("00-manual", "14-inbox"))
    assert st.AREAS == st.SHELVES[1:9]


def test_reads_only_library_minus_manual_and_inbox(repo):
    root, _ = repo
    assert st.main([str(root)]) == 0
    graph = build(root)
    assert [n["path"] for n in graph["nodes"]] == [
        "11-people/ana.md",
        "08-rest-joy/garden-plan.md",
        "06-purpose/home-goals.md",
    ]
    assert graph["errors"] == []


@pytest.mark.parametrize("folder", ["15-extra", "07-projects", "10-mind", "04-learning-growth"])
def test_unknown_or_old_folder_is_an_error(repo, folder):
    root, write = repo
    write(f"library/{folder}/note.md", note("extra"))
    graph = build(root)
    assert (folder, "not a shelf: not in the numbered folder list") in problems(graph)
    assert "extra" not in {n["slug"] for n in graph["nodes"]}


def test_maps_are_written_to_generated_and_nowhere_else(repo, tmp_path):
    root, _ = repo

    def snapshot():
        return {
            p.relative_to(tmp_path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in tmp_path.rglob("*")
            if p.is_file()
        }

    before = snapshot()
    st.main([str(root)])
    after = snapshot()
    assert sorted(set(after) - set(before)) == [
        "brain-repo/library/00-manual/generated/map.json",
        "brain-repo/library/00-manual/generated/relationship-map.md",
    ]
    assert {k: v for k, v in after.items() if k in before} == before


def test_out_is_refused_for_a_library(repo, tmp_path, capsys):
    root, _ = repo
    assert st.main([str(root), "--out", str(tmp_path / "elsewhere.json")]) == 2
    assert not (tmp_path / "elsewhere.json").exists()
    assert "--flat only" in capsys.readouterr().err


def test_missing_library_folder(tmp_path):
    assert st.main([str(tmp_path)]) == 2


def test_summary_links_are_mentions_and_since_until_text_is_ignored(repo):
    root, _ = repo
    edges = {(e["kind"], e["reason"], e["to_slug"]) for e in edges_from(build(root), "garden-plan")}
    assert edges == {
        ("mention", "mentions", "ana"),
        ("link", "part_of", "home-goals"),
        ("link", "depends_on", "ana"),
    }


def test_links_in_type_sections_are_mentions(repo):
    root, write = repo
    write(
        "library/08-rest-joy/garden-plan.md",
        note(
            "garden-plan",
            body="## Facts\n\n- A fact. (src: self, 2030-01-01)\n\n"
            "## Next action\n\nAsk [[ana]] for approval.\n\n## Links\n\n- part_of [[home-goals]]\n",
        ),
    )
    edges = {(e["kind"], e["to_slug"]) for e in edges_from(build(root), "garden-plan")}
    assert edges == {("mention", "ana"), ("link", "home-goals")}
    assert st.count_raw_links(root / "library", st.mapped_shelves())["elsewhere"] == 0


def test_history_links_stay_out_of_the_map(repo):
    root, write = repo
    write(
        "library/08-rest-joy/garden-plan.md",
        note(
            "garden-plan",
            body="## Facts\n\n- A fact. (src: self, 2030-01-01)\n\n## Links\n\n"
            "- part_of [[home-goals]]\n\n## History\n\n"
            "- The plan was led by [[ana]]. (src: self, 2030-01-01; until: 2030-02-01)\n"
            "- depends_on [[gone-note]]\n",
        ),
    )
    graph = build(root)
    assert [e["to_slug"] for e in edges_from(graph, "garden-plan")] == ["home-goals"]
    assert graph["dangling"] == []
    raw = st.count_raw_links(root / "library", st.mapped_shelves())
    assert (raw["in_history"], raw["elsewhere"]) == (2, 0)
    assert st.main([str(root)]) == 0


def test_link_outside_any_section_stops_the_run(repo, capsys):
    root, write = repo
    write(
        "library/08-rest-joy/stray.md",
        note("stray", body="See [[ana]] before any section.\n\n## Links\n\n- related_to [[ana]]\n"),
    )
    assert st.count_raw_links(root / "library", st.mapped_shelves())["elsewhere"] == 1
    assert st.main([str(root)]) == 1
    assert "STOP: links found outside any section" in capsys.readouterr().err


def test_relationship_map_adds_each_opposite(repo):
    root, _ = repo
    st.main([str(root)])
    text = (root / "library/00-manual/generated/relationship-map.md").read_text(encoding="utf-8")
    sections = dict((block.split("\n", 1)[0], block) for block in text.split("\n## ")[1:])
    goals = sections["home-goals (`home-goals`)"]
    assert "- has_part [[garden-plan]] (added: opposite)" in goals
    assert "- related_to [[garden-plan]]\n" in goals
    garden = sections["garden-plan (`garden-plan`)"]
    assert "- part_of [[home-goals]]" in garden
    assert "- related_to [[home-goals]] (added: opposite)" in garden  # symmetric verb
    ana = sections["ana (`ana`)"]
    assert "- needed_by [[garden-plan]] (added: opposite)" in ana
    assert "- mentioned in [[garden-plan]] (added: opposite)" in ana


def test_unknown_verb_is_flagged_and_gets_no_opposite(repo):
    root, _ = repo
    graph = build(root)
    assert [(u["path"], u["verb"]) for u in graph["unknown_verbs"]] == [
        ("11-people/ana.md", "waters")
    ]
    assert "- [[ana]] waters this (no opposite: verb not in the list)" in st.relationship_map(graph)


def test_hub_lists_are_hub_links(repo):
    root, write = repo
    write(
        "library/08-rest-joy/hub-rest-joy.md",
        note(
            "hub-rest-joy",
            typ="hub",
            body="## Summary\n\nWhat rest and joy holds.\n\n## Links\n\n- lists [[garden-plan]]\n",
        ),
    )
    graph = build(root)
    assert graph["errors"] == []
    (edge,) = edges_from(graph, "hub-rest-joy")
    assert (edge["kind"], edge["reason"]) == ("hub", "lists")
    text = st.relationship_map(graph)
    assert "- lists [[garden-plan]] (hub link)" in text
    assert "- listed_in [[hub-rest-joy]] (added: opposite, hub link)" in text


def test_a_hub_holds_no_facts(repo):
    root, write = repo
    write("library/08-rest-joy/hub-rest-joy.md", note("hub-rest-joy", typ="hub"))
    assert ("08-rest-joy/hub-rest-joy.md", "a hub holds no facts of its own") in problems(
        build(root)
    )


def test_journal_free_text_links_are_mentions(repo):
    root, write = repo
    write(
        "library/15-journal/2026/2026-11-03.md",
        note("2026-11-03", typ="journal", area="cross", body="Watered the beds with [[ana]].\n"),
    )
    graph = build(root)
    assert graph["errors"] == []
    assert [(e["kind"], e["to_slug"]) for e in edges_from(graph, "2026-11-03")] == [
        ("mention", "ana")
    ]
    assert st.main([str(root)]) == 0


@pytest.mark.parametrize(
    "kwargs, problem",
    [
        ({"typ": "area"}, "unknown type 'area'"),
        ({"area": ""}, "missing area"),
        ({"area": "04-learning-growth"}, "area '04-learning-growth' is not one of"),
        ({"extra": "also: [03-work-career, 09-future]\n"}, "also has unknown area(s): 09-future"),
    ],
)
def test_note_rules_are_checked(repo, kwargs, problem):
    root, write = repo
    write("library/08-rest-joy/rule.md", note("rule", **kwargs))
    found = [p for path, p in problems(build(root)) if path == "08-rest-joy/rule.md"]
    assert len(found) == 1 and found[0].startswith(problem)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"typ": "concept", "area": "cross"},
        {"typ": "topic"},
        {"extra": "also: [03-work-career]\n"},
        {"extra": "also: 04-learning\n"},
    ],
)
def test_allowed_values_pass(repo, kwargs):
    root, write = repo
    write("library/10-ideas/ok.md", note("ok", **kwargs))
    assert build(root)["errors"] == []


def test_duplicate_alias_is_an_error(repo):
    root, write = repo
    write("library/08-rest-joy/garden-two.md", note("garden-two", aliases=["Garden Plan"]))
    write("library/08-rest-joy/garden-three.md", note("garden-three", aliases=["the beds"]))
    write("library/08-rest-joy/garden-four.md", note("garden-four", aliases=["The Beds"]))
    found = problems(build(root))
    assert ("08-rest-joy/garden-two.md", "alias 'Garden Plan' is also used by garden-plan") in found
    assert ("08-rest-joy/garden-three.md", "alias 'the beds' is also used by garden-four") in found
    assert ("08-rest-joy/garden-four.md", "alias 'The Beds' is also used by garden-three") in found


def test_flat_mode_skips_the_library_rules(tmp_path):
    root = tmp_path / "flat"
    (root / "topics").mkdir(parents=True)
    (root / "topics" / "t.md").write_text(note("t", typ="topic", area=""), encoding="utf-8")
    assert st.build_map(root)["errors"] == []


@pytest.mark.parametrize("verb", sorted(st.OPPOSITE))
def test_every_verb_round_trips_through_its_opposite(verb):
    assert st.OPPOSITE[st.OPPOSITE[verb]] == verb


def test_twenty_two_verbs_including_precedes_and_lists():
    assert len(st.VERBS) == 22
    assert (st.VERBS["precedes"], st.VERBS["lists"]) == ("follows", "listed_in")
