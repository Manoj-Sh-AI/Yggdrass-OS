"""Viewer: our own offline page over the structural map (D32 as amended 2026-10-31)."""

import json
import math
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


def test_render_writes_page_script_and_fonts(library, tmp_path):
    graph = structural.build_map(library, structural.mapped_shelves())
    html = viewer.render(graph, library, tmp_path / "out")
    assert html.name == "graph.html"
    assert (tmp_path / "out" / "vis-network.min.js").read_bytes() == viewer.VIS_NETWORK.read_bytes()
    page = html.read_text(encoding="utf-8")
    for name in viewer.FONTS:
        assert (tmp_path / "out" / name).read_bytes() == (viewer.VENDOR / name).read_bytes()
        assert f'url("{name}")' in page


def test_vendored_fonts_match_their_pinned_hashes():
    for name, sha in viewer.FONTS.items():
        assert viewer.checked(viewer.VENDOR / name, sha)[:4] == b"wOF2"


def test_page_offers_four_styles_with_classic_first_and_default():
    template = viewer.TEMPLATE.read_text(encoding="utf-8")
    for style in ("classic", "graphite", "muted", "clouds"):
        assert f'<option value="{style}">' in template
    assert template.index('<option value="classic">') < template.index('<option value="graphite">')
    assert 'style: "classic"' in template
    for colour_by in ("group", "area"):
        assert f'<option value="{colour_by}">' in template


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


def _dom(html: Path, fragment: str = "", flags: tuple = ()) -> str:
    with tempfile.TemporaryDirectory() as profile:
        out = subprocess.run(
            [
                str(EDGE), "--headless=new", "--disable-gpu", "--virtual-time-budget=20000",
                "--host-resolver-rules=MAP * ~NOTFOUND", f"--user-data-dir={profile}", *flags,
                "--dump-dom", html.as_uri() + (f"#{fragment}" if fragment else ""),
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )  # fmt: skip
    return out.stdout


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
@pytest.mark.parametrize("style", ["classic", "graphite", "muted", "clouds"])
def test_page_runs_offline_without_errors_in_a_real_browser(library, tmp_path, style):
    html = viewer.render(
        structural.build_map(library, structural.mapped_shelves()), library, tmp_path
    )
    body = re.search(r"<body[^>]*>", _dom(html, f"style={style}&select=garden")).group(0)
    assert 'data-ready="1"' in body
    assert "data-error" not in body
    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
@pytest.mark.parametrize("colour", ["group", "area"])
def test_classic_is_the_default_with_counts_in_the_sidebar(library, tmp_path, colour):
    html = viewer.render(
        structural.build_map(library, structural.mapped_shelves()), library, tmp_path
    )
    dom = _dom(html, f"colour={colour}")
    body = re.search(r"<body[^>]*>", dom).group(0)
    assert 'data-ready="1"' in body and "data-error" not in body
    counts = re.search(r'<div id="counts"[^>]*>(.*?)</div>', dom, re.S)
    assert counts and "4 notes, " in counts.group(1) and "Drag to pan" in counts.group(1)
    assert "legend-card" not in dom


def test_classic_springs_follow_the_colouring():
    template = viewer.TEMPLATE.read_text(encoding="utf-8")
    assert 'if (state.style === "clouds") return "a";' in template
    assert 'return state.colourBy === "area" ? "b" : "g";' in template


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
def test_pure_note_stays_pure_and_bridge_note_is_blended(tmp_path):
    root = tmp_path / "brain" / "library"
    links = "## Facts\n\n- A fact. (src: self, 2030-01-01)\n\n## Links\n\n"
    files = {
        # alone links only to its own area: pure. home links to alone (same area) and to
        # study (another area): a bridge, so blended. The hub link must not count.
        "08-rest-joy/alone.md": note("alone", body=links + "- related_to [[home]]\n"),
        "08-rest-joy/home.md": note("home", body=links + "- related_to [[study]]\n"),
        "04-learning/study.md": note("study", area="04-learning", body=links),
        "04-learning/hub-learning.md": note(
            "hub-learning",
            typ="hub",
            area="04-learning",
            body="## Summary\n\nHub.\n\n## Links\n\n- lists [[alone]]\n",
        ),
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    html = viewer.render(
        structural.build_map(root, structural.mapped_shelves()), root, tmp_path / "out"
    )
    dom = _dom(html, "colour=area&debug=colours")
    raw = re.search(r'data-colours="([^"]*)"', dom).group(1)
    colours = json.loads(raw.replace("&quot;", '"').replace("&amp;", "&"))
    assert colours["alone"]["shown"] == colours["alone"]["pure"]
    assert colours["home"]["shown"] != colours["home"]["pure"]
    assert colours["study"]["shown"] != colours["study"]["pure"]
    assert colours["home"]["shown"].startswith("#")


def _body_json(dom: str, attr: str) -> dict:
    raw = re.search(rf'data-{attr}="([^"]*)"', dom).group(1)
    return json.loads(raw.replace("&quot;", '"').replace("&amp;", "&"))


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
def test_node_size_shrinks_as_the_brain_grows_with_a_floor(library, tmp_path):
    html = viewer.render(
        structural.build_map(library, structural.mapped_shelves()), library, tmp_path
    )
    sizes = _body_json(_dom(html, "debug=sizes"), "sizes")
    assert sizes["80"] > sizes["320"] > sizes["5000"]
    assert sizes["80"] == 1 and sizes["320"] == 0.5 and sizes["5000"] == 0.45


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
def test_grey_cross_area_notes_take_no_part_in_blending(tmp_path):
    root = tmp_path / "brain" / "library"
    links = "## Facts\n\n- A fact. (src: self, 2030-01-01)\n\n## Links\n\n"
    files = {
        # alone links only to a grey Cross-area note: it stays pure, and so does the grey note.
        "08-rest-joy/alone.md": note("alone", body=links + "- related_to [[me]]\n"),
        "11-people/me.md": note("me", typ="person", area="cross", body=links),
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    graph = structural.build_map(root, structural.mapped_shelves())
    html = viewer.render(graph, root, tmp_path / "out")
    colours = _body_json(_dom(html, "colour=area&debug=colours"), "colours")
    assert colours["alone"]["shown"] == colours["alone"]["pure"]
    assert colours["me"]["shown"] == colours["me"]["pure"]


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
def test_reduced_motion_loads_without_animation_errors(library, tmp_path):
    html = viewer.render(
        structural.build_map(library, structural.mapped_shelves()), library, tmp_path
    )
    dom = _dom(html, "select=garden", flags=("--force-prefers-reduced-motion",))
    body = re.search(r"<body[^>]*>", dom).group(0)
    assert 'data-ready="1"' in body and "data-error" not in body


def _layout(html: Path, fragment: str) -> dict:
    # Reduced motion: the positions are the same, and headless Edge need not play the glide.
    dom = _dom(html, fragment + "&debug=layout", flags=("--force-prefers-reduced-motion",))
    return _body_json(dom, "layout")


@pytest.fixture
def areas_brain(tmp_path):
    """Five life areas of different sizes, a hub each, links within and across, a centre note."""
    root = tmp_path / "brain" / "library"
    sizes = {
        "01-health": 3,
        "03-work-career": 12,
        "04-learning": 9,
        "05-money": 2,
        "08-rest-joy": 4,
    }
    files = {"11-people/me.md": note("me", typ="person", area="cross", body="## Links\n\n")}
    for area, count in sizes.items():
        tag = area[3:]
        files[f"{area}/{tag}-hub.md"] = note(
            f"{tag}-hub", typ="hub", area=area, body="## Links\n\n"
        )
        for i in range(count):
            links = f"- part_of [[{tag}-hub]]\n- related_to [[me]]\n"
            if i:
                links += f"- related_to [[{tag}-{i - 1}]]\n"
            if i == 1 and area != "01-health":
                links += "- related_to [[health-0]]\n"
            body = f"## Facts\n\n- A fact. (src: self, 2030-01-01)\n\n## Links\n\n{links}"
            files[f"{area}/{tag}-{i}.md"] = note(f"{tag}-{i}", area=area, body=body)
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
@pytest.mark.parametrize("colour", ["area", "group"])
def test_radial_sectors_keep_every_note_in_the_disc_and_its_sector(areas_brain, tmp_path, colour):
    graph = structural.build_map(areas_brain, structural.mapped_shelves())
    html = viewer.render(graph, areas_brain, tmp_path / "out")
    got = _layout(html, f"layout=radial&colour={colour}")
    radius, sectors = got["info"]["R"], got["info"]["sectors"]
    outside, stray, total = [], 0, 0
    for slug, n in got["nodes"].items():
        if math.hypot(n["x"], n["y"]) > radius * 1.001:
            outside.append(slug)
        if n["centre"]:
            continue
        total += 1
        start, end = sectors[n["key"]]
        angle = math.atan2(n["y"], n["x"])
        while angle < start:
            angle += 2 * math.pi
        if angle > end:
            stray += 1
    assert len(sectors) == (5 if colour == "area" else 2)
    assert outside == []
    assert stray <= 0.1 * total


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
@pytest.mark.parametrize("colour", ["area", "group"])
def test_circlepack_keeps_every_note_in_its_own_circle_inside_the_outer_one(
    areas_brain, tmp_path, colour
):
    graph = structural.build_map(areas_brain, structural.mapped_shelves())
    html = viewer.render(graph, areas_brain, tmp_path / "out")
    got = _layout(html, f"layout=circlepack&colour={colour}")
    radius, circles = got["info"]["R"], got["info"]["circles"]
    for slug, n in got["nodes"].items():
        assert math.hypot(n["x"], n["y"]) <= radius * 1.001, slug
        c = circles["cross" if n["centre"] else n["key"]]
        assert math.hypot(n["x"] - c["x"], n["y"] - c["y"]) <= c["r"] + 0.5, slug


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
def test_page_offers_three_layouts_with_force_as_the_default(library, tmp_path):
    html = viewer.render(
        structural.build_map(library, structural.mapped_shelves()), library, tmp_path
    )
    text = html.read_text(encoding="utf-8")
    assert '<option value="force">Force</option><option value="radial">Radial sectors' in text
    assert _layout(html, "")["layout"] == "force"
