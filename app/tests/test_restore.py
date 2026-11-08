"""Restoring an archived note (D38): free code, written at once with Undo. The note returns to
its shelf, and exactly what archiving took from other notes (link lines, [[mentions]], the hub
listing) comes back; a line changed since is reported, never overwritten."""

import pytest

from test_brain_write import TODAY, commits, git, make_brain, tree
from test_lia import FakeClient, text, tool_use
from yggdras.data.brain.ops import build_change
from yggdras.data.brain.pending import Store
from yggdras.data.brain.write_path import WritePath
from yggdras.processing.lia.library import Library
from yggdras.processing.lia.write import WriteSide

THESIS = "library/04-learning/masters-thesis.md"
ARCHIVED = "archive/library/04-learning/masters-thesis.md"


@pytest.fixture
def brain(tmp_path):
    return make_brain(tmp_path)


def wp(repo, tmp_path):
    return WritePath(repo, repo / "library", tmp_path / "locks", today=TODAY)


def apply(repo, tmp_path, ops):
    w = wp(repo, tmp_path)
    return w.apply(build_change(w.root, False, ops, TODAY), "test")


def side(repo, tmp_path, replies=()):
    client = FakeClient(list(replies))
    root = repo / "library"
    return WriteSide(
        client, Library(root), wp(repo, tmp_path), Store(tmp_path / "y.db"), today=TODAY
    ), client


def archived_then_touched(repo, tmp_path):
    """Archive the thesis, then change a note the archive touched (so Undo is blocked)."""
    before = tree(repo)
    out = apply(repo, tmp_path, [{"op": "archive_note", "slug": "masters-thesis"}])
    assert out.status == "written"
    apply(repo, tmp_path, [{"op": "add_fact", "slug": "ana", "text": "Ana likes tea"}])
    assert wp(repo, tmp_path).undo(out.sha, "test").status == "blocked"
    return before


def test_restore_brings_back_the_note_its_links_mentions_and_hub_listing(brain, tmp_path):
    before = archived_then_touched(brain, tmp_path)
    s, client = side(brain, tmp_path)
    card = s.restore("masters-thesis", "test")
    assert card.kind == "summary", card.text
    assert client.sent == []  # free: no model call
    assert commits(brain)[0] == "lia: restore masters-thesis"
    assert (brain / THESIS).is_file() and not (brain / ARCHIVED).exists()
    assert tree(brain)[THESIS] == before[THESIS]  # the note itself, exactly as it was
    ana = (brain / "library/11-people/ana.md").read_text(encoding="utf-8")
    assert "- knows [[masters-thesis]]" in ana  # the link line, back in ## Links
    assert "Ana supervises the [[masters-thesis]]." in ana  # the mention, back as it was
    assert "Ana likes tea" in ana  # the later change stays
    savings = (brain / "library/05-money/savings.md").read_text(encoding="utf-8")
    assert "- related_to [[masters-thesis]]" in savings
    hub = (brain / "library/04-learning/hub-learning.md").read_text(encoding="utf-8")
    assert "- lists [[masters-thesis]]" in hub and "Notes so far: 2." in hub
    assert git(brain, "status", "--porcelain") == ""
    assert "yggdras undo" in card.text


def test_a_line_changed_since_the_archive_is_reported_not_overwritten(brain, tmp_path):
    apply(brain, tmp_path, [{"op": "archive_note", "slug": "masters-thesis"}])
    ana_path = brain / "library/11-people/ana.md"
    plain = "Ana supervises the Masters Thesis."
    old = next(ln[2:] for ln in ana_path.read_text(encoding="utf-8").splitlines() if plain in ln)
    out = apply(
        brain,
        tmp_path,
        [
            {
                "op": "replace_fact",
                "slug": "ana",
                "old": old,
                "text": "Ana co-supervises the thesis",
                "mode": "until",
            }
        ],
    )
    assert out.status == "written"
    s, _ = side(brain, tmp_path)
    card = s.restore("masters-thesis", "test")
    assert card.kind == "summary", card.text
    assert "changed since the archive, left as they are" in card.text
    ana = ana_path.read_text(encoding="utf-8")
    assert "Ana co-supervises the thesis" in ana and "- knows [[masters-thesis]]" in ana


def test_a_note_is_found_by_name_or_alias_and_an_unknown_one_lists_the_archive(brain, tmp_path):
    apply(brain, tmp_path, [{"op": "archive_note", "slug": "masters-thesis"}])
    s, _ = side(brain, tmp_path)
    nothing = s.restore("garden plan", "test")
    assert nothing.kind == "refused" and "Masters Thesis (masters-thesis)" in nothing.text
    assert s.restore("thesis", "test").kind == "summary"  # its alias


def test_two_archived_notes_that_both_fit_are_never_guessed(brain, tmp_path):
    apply(brain, tmp_path, [{"op": "archive_note", "slug": "masters-thesis"}])
    apply(brain, tmp_path, [{"op": "archive_note", "slug": "german-learning"}])
    w = wp(brain, tmp_path)
    from yggdras.data.brain.ops import Builder

    b = Builder(w.root, False, TODAY)
    assert {a["slug"] for a in b.archived()} == {"masters-thesis", "german-learning"}
    with pytest.raises(Exception, match="no archived note matches"):
        b.find_archived("garden")


def test_restoring_twice_or_a_live_note_is_refused(brain, tmp_path):
    s, _ = side(brain, tmp_path)
    assert s.restore("masters-thesis", "test").kind == "refused"  # never archived
    apply(brain, tmp_path, [{"op": "archive_note", "slug": "masters-thesis"}])
    assert s.restore("masters-thesis", "test").kind == "summary"
    assert s.restore("masters-thesis", "test").kind == "refused"


def test_undo_of_a_restore_archives_it_again(brain, tmp_path):
    apply(brain, tmp_path, [{"op": "archive_note", "slug": "masters-thesis"}])
    s, _ = side(brain, tmp_path)
    card = s.restore("masters-thesis", "test")
    assert s.undo(card.sha, card.token, "test").kind == "summary"
    assert (brain / ARCHIVED).is_file() and not (brain / THESIS).exists()
    ana = (brain / "library/11-people/ana.md").read_text(encoding="utf-8")
    assert "[[masters-thesis]]" not in ana


def test_an_old_format_note_comes_back_without_the_new_note_rules(brain, tmp_path):
    apply(brain, tmp_path, [{"op": "archive_note", "slug": "masters-thesis"}])
    arch = brain / ARCHIVED
    old_format = arch.read_text(encoding="utf-8").replace("## Summary\n\nSummary.\n\n", "")
    arch.write_text(old_format, encoding="utf-8", newline="\n")
    git(brain, "commit", "-qam", "an older note, no Summary")
    s, _ = side(brain, tmp_path)
    assert s.restore("masters-thesis", "test").kind == "summary"


def test_lia_restores_through_tell_lia_at_once(brain, tmp_path):
    apply(brain, tmp_path, [{"op": "archive_note", "slug": "masters-thesis"}])
    replies = [[tool_use("restore_note", {"slug": "my thesis"})], [text("Brought it back.")]]
    s, _ = side(brain, tmp_path, replies)
    card = s.tell("Bring back my thesis note.")
    assert card.kind == "summary", card.text  # adding back: no preview
    assert commits(brain)[0] == "lia: restore masters-thesis"


def test_the_connector_and_cli_restore_for_free(tmp_path, monkeypatch):
    import asyncio

    from test_mcp import write_service
    from yggdras.interface.mcp_server import build_server

    monkeypatch.setenv("YGGDRAS_LOCAL_DATA", str(tmp_path / "local"))
    repo = make_brain(tmp_path)
    apply(repo, tmp_path, [{"op": "archive_note", "slug": "masters-thesis"}])
    service = write_service(repo, tmp_path, [])  # a model that would fail if called
    server = build_server(service)
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert "restore_note" in tools and not tools["restore_note"].annotations.read_only_hint
    out = asyncio.run(server._tool_manager.get_tool("restore_note").fn(note="thesis", ctx=None))
    assert out.structured_content["kind"] == "summary", out.structured_content["text"]
    assert (repo / THESIS).is_file()
    from yggdras.interface import cli

    apply(repo, tmp_path, [{"op": "archive_note", "slug": "masters-thesis"}])
    assert cli.main(["restore", "masters-thesis", "--brain", str(repo)]) == 0
    assert (repo / THESIS).is_file()
