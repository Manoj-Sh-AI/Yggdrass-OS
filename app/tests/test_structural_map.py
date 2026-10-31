"""Structural pass: criteria 1-9 of requirements/spec-phase-1b-structural-pass.md."""

import hashlib
import json
from pathlib import Path

import pytest

from yggdras.data.graph import structural as st

FIXTURE = Path(__file__).resolve().parents[2] / "evals" / "fixture-brain"


def node(
    slug,
    *,
    links=(),
    facts=("- [stated] A fact (src: self, 2030-01-01)",),
    aliases=(),
    name=None,
    typ="topic",
    node_id=None,
):
    alias_list = ", ".join(f'"{a}"' for a in aliases)
    return "\n".join(
        [
            "---",
            f"id: {node_id or 'id-' + slug}",
            f"slug: {slug}",
            f'name: "{name or slug}"',
            f"type: {typ}",
            f"description: About {slug}",
            "created: 2030-01-01",
            "updated: 2030-01-01",
            f"aliases: [{alias_list}]",
            "---",
            "",
            "## Facts",
            "",
            *facts,
            "",
            "## Links",
            "",
            *links,
            "",
        ]
    )


@pytest.fixture
def brain(tmp_path):
    root = tmp_path / "brain"

    def write(rel, text):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    root.mkdir()
    write("index.md", "# Index\n\n| slug |\n|---|\n| [[not-a-link-source]] |\n")
    write(
        "areas/apollo-13.md",
        node(
            "apollo-13",
            typ="area",
            links=[
                "- crippled by [[oxygen-tank-2]]",
                "- crewed by [[Mattingly]]",
                "- returned on [[free-return]]",
            ],
        ),
    )
    write(
        "topics/oxygen-tank-2.md",
        node("oxygen-tank-2", aliases=["O2 tank 2"], links=["- crippled [[apollo-13]]"]),
    )
    write(
        "people/ken-mattingly.md",
        node("ken-mattingly", typ="person", aliases=["Mattingly", "Ken Mattingly"]),
    )
    return root, write


def test_input_nodes_match_frontmatter_and_skip_index(brain):
    root, _ = brain
    graph = st.build_map(root)
    assert [n["slug"] for n in graph["nodes"]] == ["apollo-13", "ken-mattingly", "oxygen-tank-2"]
    tank = next(n for n in graph["nodes"] if n["slug"] == "oxygen-tank-2")
    assert tank == {
        "id": "id-oxygen-tank-2",
        "slug": "oxygen-tank-2",
        "name": "oxygen-tank-2",
        "type": "topic",
        "path": "topics/oxygen-tank-2.md",
        "aliases": ["O2 tank 2"],
        "area": "",
        "description": "About oxygen-tank-2",
    }


def test_default_output_location_and_shape(brain):
    root, _ = brain
    st.main([str(root), "--flat"])
    out = root.parent / ".map" / "graph.json"
    graph = json.loads(out.read_text(encoding="utf-8"))
    assert graph["schema"] == "yggdras-map/3"
    assert set(graph) == {"schema", "nodes", "edges", "dangling", "errors", "unknown_verbs"}
    assert set(graph["edges"][0]) == {
        "from",
        "to",
        "from_slug",
        "to_slug",
        "kind",
        "reason",
        "written_as",
        "resolved_via",
        "line",
    }


def test_reason_text_is_kept(brain):
    root, _ = brain
    edge = next(e for e in st.build_map(root)["edges"] if e["to_slug"] == "oxygen-tank-2")
    assert (edge["reason"], edge["written_as"], edge["resolved_via"]) == (
        "crippled by",
        "oxygen-tank-2",
        "slug",
    )
    assert (
        edge["line"] == 18
    )  # 10 frontmatter lines, blank, Facts, blank, fact, blank, Links, blank


def test_alias_resolves_to_the_right_node(brain):
    root, write = brain
    write(
        "topics/notes.md", node("notes", links=["- see [[o2 TANK  2]]", "- see [[ken_mattingly]]"])
    )
    edges = st.build_map(root)["edges"]
    by_alias = next(e for e in edges if e["written_as"] == "Mattingly")
    assert (by_alias["to"], by_alias["resolved_via"]) == ("id-ken-mattingly", "alias")
    normalized_alias = next(e for e in edges if e["written_as"] == "o2 TANK  2")
    assert (normalized_alias["to_slug"], normalized_alias["resolved_via"]) == (
        "oxygen-tank-2",
        "alias",
    )
    normalized_slug = next(e for e in edges if e["written_as"] == "ken_mattingly")
    assert (normalized_slug["to_slug"], normalized_slug["resolved_via"]) == (
        "ken-mattingly",
        "slug",
    )


def test_output_is_byte_identical_across_runs(brain, tmp_path):
    root, _ = brain
    st.main([str(root), "--flat", "--out", str(tmp_path / "a.json")])
    st.main([str(root), "--flat", "--out", str(tmp_path / "b.json")])
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()


def test_dangling_links_are_reported_not_dropped(brain, capsys):
    root, _ = brain
    graph = st.build_map(root)
    assert graph["dangling"] == [
        {
            "from": "id-apollo-13",
            "from_slug": "apollo-13",
            "kind": "link",
            "reason": "returned on",
            "written_as": "free-return",
            "line": 20,
        }
    ]
    assert all(e["written_as"] != "free-return" for e in graph["edges"])
    st.main([str(root), "--flat"])
    assert "dangling 1" in capsys.readouterr().out


def test_errors_are_reported_and_the_rest_still_maps(brain):
    root, write = brain
    write("topics/broken.md", "---\nid: x\nslug: [unclosed\n---\n\n## Facts\n")
    write("topics/no-frontmatter.md", "just text\n")
    write("topics/dupe.md", node("oxygen-tank-2", node_id="id-dupe"))
    graph = st.build_map(root)
    problems = {e["path"]: e["problem"] for e in graph["errors"]}
    assert problems["topics/broken.md"].startswith("unparseable frontmatter")
    assert problems["topics/no-frontmatter.md"] == "no frontmatter block"
    assert (
        "duplicate slug 'oxygen-tank-2'"
        in problems[
            "topics/oxygen-tank-2.md" if "topics/oxygen-tank-2.md" in problems else "topics/dupe.md"
        ]
    )
    assert {n["slug"] for n in graph["nodes"]} >= {"apollo-13", "ken-mattingly"}
    assert st.main([str(root), "--flat"]) == 1


def test_missing_required_field_is_an_error(brain):
    root, write = brain
    write("topics/nameless.md", "---\nid: n1\nslug: nameless\ntype: topic\n---\n")
    assert any(
        "missing frontmatter field(s): name" in e["problem"] for e in st.build_map(root)["errors"]
    )


def test_brain_is_never_modified(brain):
    root, _ = brain

    def snapshot():
        return {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*")
            if p.is_file()
        }

    before = snapshot()
    st.main([str(root), "--flat"])
    assert snapshot() == before


def test_links_in_facts_become_mention_edges(brain):
    root, write = brain
    write(
        "topics/stray.md",
        node(
            "stray", facts=["- [stated] Mentions [[apollo-13]] in a fact (src: self, 2030-01-01)"]
        ),
    )
    raw = st.count_raw_links(root)
    assert raw == {"total": 5, "inside_links": 4, "inside_facts": 1, "elsewhere": 0}
    (edge,) = [e for e in st.build_map(root)["edges"] if e["from_slug"] == "stray"]
    assert (edge["kind"], edge["reason"], edge["to_slug"], edge["line"]) == (
        "mention",
        "mentions",
        "apollo-13",
        14,
    )
    assert st.main([str(root), "--flat"]) == 0


def test_typed_verbs_come_only_from_links_section(brain):
    root, write = brain
    write(
        "topics/both.md",
        node(
            "both",
            facts=["- [stated] Part of [[apollo-13]] (src: self, 2030-01-01)"],
            links=["- part of [[apollo-13]]"],
        ),
    )
    kinds = {
        (e["kind"], e["reason"]) for e in st.build_map(root)["edges"] if e["from_slug"] == "both"
    }
    assert kinds == {("mention", "mentions"), ("link", "part of")}


def test_links_outside_facts_and_links_are_counted_and_stop_the_run(brain, capsys):
    root, write = brain
    write("topics/stray.md", node("stray") + "\n## Notes\n\n- see [[apollo-13]]\n")
    raw = st.count_raw_links(root)
    assert raw["elsewhere"] == 1
    assert not any(e["from_slug"] == "stray" for e in st.build_map(root)["edges"])
    assert st.main([str(root), "--flat"]) == 1
    assert "STOP: links found outside ## Facts and ## Links" in capsys.readouterr().err


def test_ambiguous_alias_is_an_error_not_a_guess(brain):
    root, write = brain
    write("people/other.md", node("other-person", typ="person", aliases=["Mattingly"]))
    graph = st.build_map(root)
    assert any("[[Mattingly]] is ambiguous" in e["problem"] for e in graph["errors"])
    assert all(e["written_as"] != "Mattingly" for e in graph["edges"])


@pytest.mark.parametrize(
    "line, reason, target",
    [
        ("- relevant to the orchards of [[campo]] today", "relevant to the orchards of", "campo"),
        ("- self [[loop]]", "self", "loop"),
    ],
)
def test_link_line_edge_cases(brain, line, reason, target):
    root, write = brain
    write("topics/loop.md", node("loop", links=[line]))
    write("topics/campo.md", node("campo"))
    edge = next(e for e in st.build_map(root)["edges"] if e["from_slug"] == "loop")
    assert (edge["reason"], edge["to_slug"]) == (reason, target)


def test_empty_brain_gives_a_valid_empty_map(tmp_path):
    (tmp_path / "empty").mkdir()
    assert st.build_map(tmp_path / "empty") == {
        "schema": "yggdras-map/3",
        "nodes": [],
        "edges": [],
        "dangling": [],
        "errors": [],
        "unknown_verbs": [],
    }


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Bank Work", "bank-work"),
        ("Universität", "universitat"),
        ("Straße", "strasse"),
        ("Power BI - Reports", "power-bi-reports"),
        (" Søren ", "soren"),
        ("---", ""),
    ],
)
def test_normalize_follows_d02(text, expected):
    assert st.normalize(text) == expected


def test_fixture_brain_every_hand_link_becomes_an_edge():
    graph = st.build_map(FIXTURE)
    raw = st.count_raw_links(FIXTURE)
    assert raw["elsewhere"] == 0
    assert len(graph["edges"]) == raw["inside_links"] + raw["inside_facts"]
    assert raw["inside_links"] > 0
    assert graph["dangling"] == [] and graph["errors"] == []
    assert len(graph["nodes"]) == 10
