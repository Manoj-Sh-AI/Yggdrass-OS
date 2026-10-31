"""Viewer: our map drawn by Graphify's HTML view, offline (D32 as amended 2026-10-31)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from yggdras.data.graph import structural, viewer

FIXTURE = Path(__file__).resolve().parents[2] / "evals" / "fixture-brain"
CDN_TAG = (
    '<script src="https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js"\n'
    '        integrity="sha384-Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1"\n'
    '        crossorigin="anonymous"></script>'
)
PAGE = f"<!DOCTYPE html><html><head>{CDN_TAG}</head><body></body></html>"


@pytest.fixture
def graph():
    return structural.build_map(FIXTURE)


def test_conversion_keeps_every_node_link_and_verb(graph):
    data, labels = viewer.to_graphify(graph)
    assert len(data["nodes"]) == len(graph["nodes"])
    assert len(data["links"]) == len(graph["edges"])
    assert [link["relation"] for link in data["links"]] == [e["reason"] for e in graph["edges"]]
    first = graph["edges"][0]
    assert (data["links"][0]["_src"], data["links"][0]["_tgt"]) == (first["from"], first["to"])
    assert data["multigraph"] is True
    assert {link["confidence"] for link in data["links"]} == {"EXTRACTED"}


def test_communities_are_shelves(graph):
    data, labels = viewer.to_graphify(graph)
    assert sorted(labels.values()) == ["areas", "people", "sources", "topics"]
    for n, src in zip(data["nodes"], graph["nodes"], strict=True):
        assert labels[str(n["community"])] == src["path"].split("/")[0]


def test_local_vis_network_matches_the_pinned_hash():
    assert viewer.vis_network_bytes().startswith(b"/**\n * vis-network")


def test_tampered_vis_network_is_refused(tmp_path, monkeypatch):
    fake = tmp_path / "vis.js"
    fake.write_bytes(viewer.VIS_NETWORK.read_bytes() + b"//")
    monkeypatch.setattr(viewer, "VIS_NETWORK", fake)
    with pytest.raises(viewer.ViewerError, match="does not match"):
        viewer.vis_network_bytes()


def test_localize_points_the_script_tag_at_the_local_copy():
    out = viewer.localize(PAGE)
    assert '<script src="vis-network.min.js"></script>' in out
    assert "unpkg" not in out


@pytest.mark.parametrize(
    "page, problem",
    [
        ("<html></html>", "found 0"),
        (PAGE + '<script src="https://cdn.example/x.js"></script>', "from the internet"),
    ],
)
def test_localize_refuses_unexpected_pages(page, problem):
    with pytest.raises(viewer.ViewerError, match=problem):
        viewer.localize(page)


class FakeGraphify:
    def __init__(self, version="0.9.95"):
        self.version, self.calls = version, []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs["env"]))
        if args[1] == "--version":
            return subprocess.CompletedProcess(args, 0, stdout=f"graphify {self.version}\n")
        Path(args[-1]).with_name("graph.html").write_text(PAGE, encoding="utf-8")
        return subprocess.CompletedProcess(args, 0)


def test_render_writes_an_offline_page(graph, tmp_path, monkeypatch):
    fake = FakeGraphify()
    monkeypatch.setattr(viewer.subprocess, "run", fake)
    html = viewer.render(graph, tmp_path)
    assert "unpkg" not in html.read_text(encoding="utf-8")
    assert (tmp_path / "vis-network.min.js").read_bytes() == viewer.VIS_NETWORK.read_bytes()
    written = json.loads((tmp_path / "graph.json").read_text(encoding="utf-8"))
    assert len(written["links"]) == len(graph["edges"])
    export = fake.calls[-1]
    assert export[0][1:4] == ["export", "html", "--graph"]
    for _args, env in fake.calls:
        assert env["GRAPHIFY_BACKEND"] == "none"
        assert env["GRAPHIFY_QUERY_LOG_DISABLE"] == "1"


def test_render_refuses_another_graphify_version(graph, tmp_path, monkeypatch):
    fake = FakeGraphify(version="0.9.96")
    monkeypatch.setattr(viewer.subprocess, "run", fake)
    with pytest.raises(viewer.ViewerError, match="0.9.95 is pinned"):
        viewer.render(graph, tmp_path)
    assert len(fake.calls) == 1  # only the version check ran
    assert not (tmp_path / "graph.html").exists()


def test_main_writes_into_the_library_generated_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(viewer.subprocess, "run", FakeGraphify())
    (tmp_path / "library" / "11-people").mkdir(parents=True)
    assert viewer.main([str(tmp_path)]) == 0
    assert (tmp_path / "library/00-manual/generated/graph.html").exists()


def test_main_flat_needs_out_dir(tmp_path):
    assert viewer.main([str(FIXTURE), "--flat"]) == 2


def _real_graphify():
    exe = shutil.which("graphify")
    try:
        return exe if exe and viewer.graphify_version(exe) == viewer.GRAPHIFY_VERSION else None
    except (OSError, subprocess.CalledProcessError):
        return None


@pytest.mark.skipif(_real_graphify() is None, reason="Graphify 0.9.95 is not installed here")
def test_real_graphify_renders_the_fixture_offline(graph, tmp_path):
    html = viewer.render(graph, tmp_path, _real_graphify()).read_text(encoding="utf-8")
    assert '<script src="vis-network.min.js"></script>' in html
    assert "https://unpkg.com" not in html
    assert f"{len(graph['nodes'])} nodes" in html
