"""Viewer: our own offline page over the structural map (D32 as amended 2026-10-31)."""

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from yggdras.data.graph import structural, viewer

FIXTURE = Path(__file__).resolve().parents[2] / "evals" / "fixture-brain"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


def note(slug, *, typ="project", area="08-rest-joy", extra="", body=""):
    return (
        f"---\nid: id-{slug}\nslug: {slug}\nname: {slug.title()}\ntype: {typ}\narea: {area}\n"
        f"{extra}description: About {slug}\naliases: [{slug}-alias]\n---\n\n# {slug}\n\n{body}"
    )


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "brain" / "library"
    files = {
        "08-rest-joy/garden.md": note(
            "garden",
            body="## Summary\n\nA shared garden.\n\n## Facts\n\n"
            "- The garden has four beds; [[ana]] helps. (src: self, 2030-01-01)\n\n"
            "## Links\n\n- part_of [[plans]]\n",
        ),
        "08-rest-joy/plans.md": note(
            "plans",
            typ="goal",
            body="## Facts\n\n- A plan. (src: self, 2030-01-01)\n\n"
            "## Links\n\n- related_to [[garden]]\n",
        ),
        "11-people/ana.md": note(
            "ana",
            typ="person",
            extra="sensitivity: high\n",
            body="## Summary\n\nPrivate summary.\n\n## Facts\n\n"
            "- Ana has a private fact. (src: self, 2030-01-01)\n\n## Links\n\n- knows [[garden]]\n",
        ),
        "08-rest-joy/hub-rest-joy.md": note(
            "hub-rest-joy", typ="hub", body="## Summary\n\nHub.\n\n## Links\n\n- lists [[garden]]\n"
        ),
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def view_of(root, out_dir):
    return viewer.build_view(structural.build_map(root, structural.mapped_shelves()), root, out_dir)


def test_nodes_carry_text_area_and_a_relative_link_to_the_file(library, tmp_path):
    out = library / "00-manual" / "generated"
    view = view_of(library, out)
    garden = next(n for n in view["nodes"] if n["slug"] == "garden")
    assert garden["summary"] == "A shared garden."
    assert garden["facts"] == ["The garden has four beds; [[ana]] helps. (src: self, 2030-01-01)"]
    assert (garden["type"], garden["area"], garden["shelf"]) == (
        "project",
        "08-rest-joy",
        "08-rest-joy",
    )
    assert garden["aliases"] == ["garden-alias"]
    assert garden["href"] == "../../08-rest-joy/garden.md"
    assert (out / garden["href"]).resolve() == (library / "08-rest-joy/garden.md").resolve()
    assert garden["degree"] == 5


def test_edges_use_plain_words_and_keep_their_line(library, tmp_path):
    view = view_of(library, tmp_path)
    names = {n["id"]: n["slug"] for n in view["nodes"]}
    edges = {(names[e["from"]], e["verb"], names[e["to"]]): e for e in view["edges"]}
    part = edges[("garden", "part_of", "plans")]
    assert (part["label"], part["back"], part["kind"]) == ("part of", "has part", "link")
    assert part["line"] == "- part_of [[plans]]"
    mention = edges[("garden", "mentions", "ana")]
    assert (mention["label"], mention["back"], mention["kind"]) == (
        "mentions",
        "mentioned in",
        "mention",
    )
    assert mention["line"].startswith("- The garden has four beds")
    hub = edges[("hub-rest-joy", "lists", "garden")]
    assert (hub["kind"], hub["back"]) == ("hub", "listed in")
    assert not any("EXTRACTED" in json.dumps(e) for e in view["edges"])


def test_sensitive_notes_are_flagged(library, tmp_path):
    view = view_of(library, tmp_path)
    flags = {n["slug"]: n["sensitive"] for n in view["nodes"]}
    assert flags == {"ana": True, "garden": False, "hub-rest-joy": False, "plans": False}


def test_page_embeds_data_safely_and_loads_nothing_from_the_internet(library, tmp_path):
    graph = structural.build_map(library, structural.mapped_shelves())
    graph["nodes"][0]["name"] = "</script><script>alert(1)</script>"
    html = viewer.page(viewer.build_view(graph, library, tmp_path))
    assert "</script><script>alert(1)" not in html
    data = re.search(r"const DATA = (.*?);\n", html).group(1)
    assert json.loads(data)["nodes"][0]["name"] == "</script><script>alert(1)</script>"
    assert '<script src="vis-network.min.js"></script>' in html
    assert not re.search(r"""(src|href)=["']https?://""", html)
    assert "@import" not in html and "fonts.googleapis" not in html


def test_template_holds_the_data_token_once():
    assert viewer.TEMPLATE.read_text(encoding="utf-8").count(viewer.DATA_TOKEN) == 1


def test_render_writes_page_and_local_script(library, tmp_path):
    graph = structural.build_map(library, structural.mapped_shelves())
    html = viewer.render(graph, library, tmp_path / "out")
    assert html.name == "graph.html"
    assert (tmp_path / "out" / "vis-network.min.js").read_bytes() == viewer.VIS_NETWORK.read_bytes()


def test_local_vis_network_matches_the_pinned_hash():
    assert viewer.vis_network_bytes().startswith(b"/**\n * vis-network")


def test_tampered_vis_network_is_refused(tmp_path, monkeypatch):
    fake = tmp_path / "vis.js"
    fake.write_bytes(viewer.VIS_NETWORK.read_bytes() + b"//")
    monkeypatch.setattr(viewer, "VIS_NETWORK", fake)
    with pytest.raises(viewer.ViewerError, match="does not match"):
        viewer.vis_network_bytes()


def test_main_writes_into_the_library_generated_folder(library):
    assert viewer.main([str(library.parent)]) == 0
    assert (library / "00-manual/generated/graph.html").exists()


def test_main_flat_needs_out_dir():
    assert viewer.main([str(FIXTURE), "--flat"]) == 2


def test_flat_brain_renders(tmp_path):
    assert viewer.main([str(FIXTURE), "--flat", "--out-dir", str(tmp_path)]) == 0
    html = (tmp_path / "graph.html").read_text(encoding="utf-8")
    assert '"schema": "yggdras-map/3"' in html


def _dom(html: Path) -> str:
    with tempfile.TemporaryDirectory() as profile:
        out = subprocess.run(
            [
                str(EDGE), "--headless=new", "--disable-gpu", "--virtual-time-budget=20000",
                "--host-resolver-rules=MAP * ~NOTFOUND", f"--user-data-dir={profile}",
                "--dump-dom", html.as_uri(),
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )  # fmt: skip
    return out.stdout


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
def test_page_runs_offline_without_errors_in_a_real_browser(library, tmp_path):
    html = viewer.render(
        structural.build_map(library, structural.mapped_shelves()), library, tmp_path
    )
    body = re.search(r"<body[^>]*>", _dom(html)).group(0)
    assert 'data-ready="1"' in body
    assert "data-error" not in body
    shutil.rmtree(tmp_path, ignore_errors=True)
