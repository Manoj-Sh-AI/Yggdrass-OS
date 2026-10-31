"""Structural pass over a library: amendments A1, A5 and A6 (2026-10-31)."""

import hashlib

import pytest

from test_structural_map import node
from yggdras.data.graph import structural as st


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "brain-repo"

    def write(rel, text):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    write(
        "library/07-projects/garden/garden-plan.md",
        node(
            "garden-plan",
            typ="project",
            facts=["- [stated] Started with [[ana]] (src: self, 2030-01-01)"],
            links=["- part of [[home-goals]]", "- supervised by [[ana]]"],
        ),
    )
    write(
        "library/06-purpose-meaning/long-term-goals/home-goals.md",
        node("home-goals", typ="goal", links=["- conflicts with [[garden-plan]]"]),
    )
    write("library/11-people/ana.md", node("ana", typ="person", links=["- waters [[garden-plan]]"]))
    # Never read: the manual, the inbox, and everything outside library/.
    write("library/00-manual/taxonomy.md", "# Taxonomy\n")
    write("library/14-inbox/rough.md", "a rough capture with [[ana]]\n")
    write("README.md", "# Brain\n")
    write("life-evals/hard-v1.md", "1. A question about [[ana]]?\n")
    write("archive/demo-brain/people/old.md", node("old", links=["- part of [[ana]]"]))
    write("private/notes.md", "private\n")
    write("brain/areas/scaffold.md", "no frontmatter\n")
    return root, write


def test_shelf_names_are_the_numbered_list():
    assert st.SHELVES == (
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
    assert st.mapped_shelves() == st.SHELVES[1:-1]


def test_reads_only_library_minus_manual_and_inbox(repo):
    root, _ = repo
    assert st.main([str(root)]) == 0
    graph = st.build_map(root / "library", st.mapped_shelves())
    assert [n["path"] for n in graph["nodes"]] == [
        "11-people/ana.md",
        "07-projects/garden/garden-plan.md",
        "06-purpose-meaning/long-term-goals/home-goals.md",
    ]
    assert graph["errors"] == []


def test_unknown_folder_in_library_is_an_error(repo):
    root, write = repo
    write("library/15-extra/note.md", node("extra"))
    graph = st.build_map(root / "library", st.mapped_shelves())
    assert graph["errors"] == [
        {"path": "15-extra", "problem": "not a shelf: not in the numbered folder list"}
    ]
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
    added = sorted(set(after) - set(before))
    assert added == [
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


def test_relationship_map_adds_each_opposite(repo):
    root, _ = repo
    st.main([str(root)])
    text = (root / "library/00-manual/generated/relationship-map.md").read_text(encoding="utf-8")
    sections = dict((block.split("\n", 1)[0], block) for block in text.split("\n## ")[1:])
    goals = sections["home-goals (`home-goals`)"]
    assert "- contains [[garden-plan]] (added: opposite)" in goals
    assert "- conflicts with [[garden-plan]]\n" in goals
    garden = sections["garden-plan (`garden-plan`)"]
    assert "- part of [[home-goals]]" in garden
    assert "- conflicts with [[home-goals]] (added: opposite)" in garden  # symmetric verb
    ana = sections["ana (`ana`)"]
    assert "- supervises [[garden-plan]] (added: opposite)" in ana
    assert "- mentioned in [[garden-plan]] (added: opposite)" in ana


def test_unknown_verb_is_flagged_and_gets_no_opposite(repo):
    root, _ = repo
    graph = st.build_map(root / "library", st.mapped_shelves())
    assert graph["unknown_verbs"] == [{"path": "11-people/ana.md", "line": 18, "verb": "waters"}]
    text = st.relationship_map(graph)
    assert "- [[ana]] waters this (no opposite: verb not in the list)" in text


@pytest.mark.parametrize("verb", sorted(st.OPPOSITE))
def test_every_verb_round_trips_through_its_opposite(verb):
    assert st.OPPOSITE[st.OPPOSITE[verb]] == verb


def test_nineteen_verbs():
    assert len(st.VERBS) == 19
