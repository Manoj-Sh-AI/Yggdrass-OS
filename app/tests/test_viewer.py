"""Viewer: our own offline page over the structural map (D32 as amended 2026-10-31)."""

import colorsys
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


def test_page_offers_three_styles_with_classic_first_and_default():
    template = viewer.TEMPLATE.read_text(encoding="utf-8")
    for style in ("classic", "graphite", "clouds"):
        assert f'<option value="{style}">' in template
    assert '<option value="muted">' not in template  # removed 2026-11-07
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


def _dom(
    html: Path, fragment: str = "", flags: tuple = (), as_is: bool = False, profile=None
) -> str:
    # 3D is the default map; tests of the 2D map ask for it, unless they name a map or want
    # the page exactly as it opens (as_is).
    if not as_is and "dim=" not in fragment:
        fragment = "dim=2d" + (f"&{fragment}" if fragment else "")
    with tempfile.TemporaryDirectory() as fresh:
        profile = profile or fresh  # a kept profile carries the page's storage between loads
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
@pytest.mark.parametrize("style", ["classic", "graphite", "clouds"])
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


def test_force_is_the_only_layout_so_there_is_no_layout_menu():
    template = viewer.TEMPLATE.read_text(encoding="utf-8")
    assert 'id="layout"' not in template and 'id="show-ring"' not in template
    assert "radialLayout" not in template and "circlepackLayout" not in template


def _oklch_hue(hex_colour: str) -> float:
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    if hex_colour.startswith("#"):
        rgb = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    else:  # hsl(h, s%, l%)
        h, s, li = (float(x) for x in re.findall(r"[\d.]+", hex_colour))
        rgb = colorsys.hls_to_rgb(h / 360, li / 100, s / 100)
    r, g, b = (lin(c) for c in rgb)
    lm = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    mm = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    sm = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    a = 1.9779984951 * lm - 2.428592205 * mm + 0.4505937099 * sm
    bb = 0.0259040371 * lm + 0.7827717662 * mm - 0.808675766 * sm
    return math.degrees(math.atan2(bb, a))


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
def test_bridge_hue_turns_at_most_twenty_degrees(tmp_path):
    root = tmp_path / "brain" / "library"
    links = "## Facts\n\n- A fact. (src: self, 2030-01-01)\n\n## Links\n\n"
    # A Learning (yellow) note linked only to Work (blue) notes: uncapped, its hue would turn
    # about 60 degrees and read as green.
    files = {
        "04-learning/study.md": note(
            "study",
            area="04-learning",
            body=links + "- related_to [[job]]\n- related_to [[team]]\n",
        ),
        "03-work-career/job.md": note("job", area="03-work-career", body=links),
        "03-work-career/team.md": note("team", area="03-work-career", body=links),
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    graph = structural.build_map(root, structural.mapped_shelves())
    html = viewer.render(graph, root, tmp_path / "out")
    colours = _body_json(_dom(html, "colour=area&debug=colours"), "colours")
    study = colours["study"]
    turn = abs(_oklch_hue(study["shown"]) - _oklch_hue(study["pure"]))
    turn = min(turn, 360 - turn)
    assert study["shown"] != study["pure"]
    assert turn <= 21  # 20 degrees, plus rounding to hex


# ---------------------------------------------------------------- 3D view

WEBGL = ("--use-angle=swiftshader", "--enable-unsafe-swiftshader")
CALM = (*WEBGL, "--force-prefers-reduced-motion")


def _body(dom: str) -> str:
    return re.search(r"<body[^>]*>", dom).group(0)


def test_render_writes_the_3d_scripts_checked_against_their_pins(library, tmp_path):
    viewer.render(structural.build_map(library, structural.mapped_shelves()), library, tmp_path)
    three = (tmp_path / viewer.THREE_SCRIPT).read_bytes()
    assert three.startswith(b"(function () {") and three.rstrip().endswith(b"})();")
    assert viewer.checked(viewer.THREE, viewer.THREE_SHA384) in three
    force = (tmp_path / viewer.FORCE_3D_SCRIPT).read_bytes()
    assert force == viewer.checked(viewer.FORCE_3D, viewer.FORCE_3D_SHA384)


def test_tampered_3d_script_is_refused(tmp_path, monkeypatch):
    fake = tmp_path / "three.cjs"
    fake.write_bytes(viewer.THREE.read_bytes() + b"//")
    monkeypatch.setattr(viewer, "THREE", fake)
    with pytest.raises(viewer.ViewerError, match="does not match"):
        viewer.three_script()


def test_page_offers_the_2d_3d_switch_and_loads_3d_only_on_demand():
    template = viewer.TEMPLATE.read_text(encoding="utf-8")
    assert '<button id="dim-2d"' in template and '<button id="dim-3d"' in template
    assert '<script src="three.js"' not in template  # loaded lazily, not on page load


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
def test_3d_loads_offline_without_errors(library, tmp_path):
    html = viewer.render(
        structural.build_map(library, structural.mapped_shelves()), library, tmp_path
    )
    body = _body(_dom(html, "dim=3d&select=garden", flags=CALM))
    assert 'data-ready3d="1"' in body and 'data-dim="3d"' in body
    assert 'data-selected3d="garden"' in body
    assert "data-error" not in body


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
def test_switching_keeps_the_selected_note(library, tmp_path):
    html = viewer.render(
        structural.build_map(library, structural.mapped_shelves()), library, tmp_path
    )
    dom = _dom(html, "select=garden&debug=switch&filter=person&q=gar", flags=CALM)
    assert "data-error" not in _body(dom)
    got = _body_json(dom, "switch")
    assert (got["in3d"], got["back2d"]) == ("garden", "garden")
    before, during, after = got["before"], got["during"], got["after"]
    assert before["typeOff"] == ["person"] and before["search"] == "gar" and before["results"] > 0
    for state in (during, after):  # filters and search survive the switch, both ways
        assert {k: state[k] for k in before} == before
    assert during["shown3d"] == before["visible"]  # 3D shows exactly what the filters leave


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
def test_a_note_has_the_same_colour_in_2d_and_3d(library, tmp_path):
    html = viewer.render(
        structural.build_map(library, structural.mapped_shelves()), library, tmp_path
    )
    dom = _dom(html, "dim=3d&colour=area&debug=colours", flags=CALM)
    flat, deep = _body_json(dom, "colours2d"), _body_json(dom, "colours3d")
    assert set(deep) == set(flat) and deep == flat


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
def test_sensitive_facts_stay_hidden_in_3d(library, tmp_path):
    html = viewer.render(
        structural.build_map(library, structural.mapped_shelves()), library, tmp_path
    )
    dom = _dom(html, "dim=3d&select=ana", flags=CALM)
    assert 'data-selected3d="ana"' in _body(dom)
    info = re.search(r'<div id="info"[^>]*>(.*?)</aside>', dom, re.S) or re.search(
        r'<div id="info"[^>]*>(.*)', dom, re.S
    )
    panel = info.group(1)
    assert "Ana" in panel and "Show" in panel
    assert "private fact" not in panel and "Private summary" not in panel


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
def test_3d_labels_never_overlap_at_rest(tmp_path):
    # A crowded brain: 36 notes in three areas, each linked to its next five, so many
    # labels compete for room around the focused note.
    root = tmp_path / "brain" / "library"
    areas = ["04-learning", "06-work", "08-rest-joy"]
    for i in range(36):
        area = areas[i % 3]
        links = "".join(f"- related_to [[note-{(i + k) % 36:02d}]]\n" for k in range(1, 6))
        body = f"## Facts\n\n- Fact {i}. (src: self, 2030-01-01)\n\n## Links\n\n{links}"
        path = root / area / f"note-{i:02d}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(note(f"note-{i:02d}", area=area, body=body), encoding="utf-8")
    html = viewer.render(
        structural.build_map(root, structural.mapped_shelves()), root, tmp_path / "out"
    )
    dom = _dom(html, "dim=3d&select=note-00&debug=labels", flags=CALM)
    boxes = json.loads(re.search(r'data-boxes3d="([^"]*)"', dom).group(1).replace("&quot;", '"'))
    assert len(boxes) >= 2
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:  # rounded to whole pixels, so allow one
            overlap = a[0] < b[2] - 1 and a[2] > b[0] + 1 and a[1] < b[3] - 1 and a[3] > b[1] + 1
            assert not overlap, (a, b)


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
def test_reduce_motion_means_no_fly_animation_in_3d(library, tmp_path):
    html = viewer.render(
        structural.build_map(library, structural.mapped_shelves()), library, tmp_path
    )
    calm = _body(_dom(html, "dim=3d&select=garden", flags=CALM))
    assert 'data-fly-ms="0"' in calm and "data-error" not in calm


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
def test_3d_is_the_2d_map_with_depth(tmp_path):
    out = tmp_path / "out"
    viewer.main([str(FIXTURE), "--flat", "--out-dir", str(out)])
    same = _body_json(_dom(out / "graph.html", "dim=3d&debug=same", flags=CALM), "same")
    # Real depth: side-on, the map is at least half as deep as it is wide (not a flat sheet).
    assert same["depth"] >= 0.5
    # Head-on it is still recognisably the 2D map: notes move on average under half the map's
    # radius from their 2D place (0.15 on the real brain, 0.33 on this small fixture).
    assert same["off"] < 0.5
    # And no group is flung far out (unlinked groups stay near, as in 2D).
    assert same["far"] < 3


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
def test_3d_is_the_default_map(library, tmp_path):
    html = viewer.render(
        structural.build_map(library, structural.mapped_shelves()), library, tmp_path
    )
    body = _body(_dom(html, "", flags=CALM, as_is=True))
    assert 'data-dim="3d"' in body and 'data-ready3d="1"' in body
    assert "data-error" not in body


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
def test_3d_turns_slowly_but_never_with_reduce_motion(library, tmp_path):
    html = viewer.render(
        structural.build_map(library, structural.mapped_shelves()), library, tmp_path
    )
    assert 'data-spin="1"' in _body(_dom(html, "dim=3d", flags=WEBGL))
    assert 'data-spin="0"' in _body(_dom(html, "dim=3d", flags=CALM))
    # A selected note holds the map still.
    assert 'data-spin="0"' in _body(_dom(html, "dim=3d&select=garden", flags=WEBGL))


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
def test_the_turn_stops_on_interaction_and_stays_stopped(library, tmp_path):
    html = viewer.render(
        structural.build_map(library, structural.mapped_shelves()), library, tmp_path
    )
    got = _body_json(_dom(html, "dim=3d&debug=interact", flags=WEBGL), "interact")
    assert got == {"before": "1", "during": "0", "after": "0"}  # resumes only after quiet


@pytest.mark.skipif(not EDGE.exists(), reason="Microsoft Edge is not installed here")
def test_the_last_view_is_remembered(library, tmp_path):
    html = viewer.render(
        structural.build_map(library, structural.mapped_shelves()), library, tmp_path / "out"
    )
    profile = tmp_path / "profile"
    assert 'data-dim="3d"' in _body(_dom(html, "", flags=CALM, as_is=True, profile=profile))
    _dom(html, "debug=click2d", flags=CALM, as_is=True, profile=profile)  # Manoj picks 2D
    assert 'data-dim="2d"' in _body(_dom(html, "", flags=CALM, as_is=True, profile=profile))
