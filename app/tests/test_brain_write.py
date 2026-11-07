"""The write path (D22, D36): note edits, the checker, operations, commits, the lock, Undo."""

import hashlib
import subprocess
import time

import pytest

from yggdras.data.brain import detect
from yggdras.data.brain import notefile as nf
from yggdras.data.brain import repo as git_repo
from yggdras.data.brain.checker import Checker
from yggdras.data.brain.ops import OpError, build_change, needs_confirm
from yggdras.data.brain.pending import Store
from yggdras.data.brain.placement import flat_folder, shelf_for
from yggdras.data.brain.write_path import WritePath

TODAY = "2030-11-07"
SRC = "(src: self, 2030-01-01)"


def lib_note(
    slug,
    *,
    typ="project",
    area="04-learning",
    name=None,
    aliases=(),
    body="",
    sensitive=False,
    description=None,
):
    alias_list = ", ".join(f'"{a}"' for a in aliases)
    extra = "sensitivity: high\n" if sensitive else ""
    return (
        f'---\nid: id-{slug}\nslug: {slug}\nname: "{name or slug.replace("-", " ").title()}"\n'
        f"type: {typ}\narea: {area}\n{extra}"
        f'description: "{description or "About " + slug.replace("-", " ")}"\n'
        f"aliases: [{alias_list}]\ncreated: 2030-01-01\nupdated: 2030-01-01\n---\n\n"
        f"# {name or slug}\n\n## Summary\n\nSummary.\n\n{body}"
    )


THESIS_FACT = f"The thesis is due in March 2031. {SRC}"
BUDGET_FACT = f"The savings goal is 4000 euros. {SRC}"
FILES = {
    "library/00-manual/taxonomy.md": "# Taxonomy\n",
    "library/00-manual/node.md": "# Node\n",
    "library/00-manual/log.md": "# Log\n\n- 2030-01-01 start (setup)\n",
    "library/04-learning/hub-learning.md": lib_note(
        "hub-learning",
        typ="hub",
        name="Learning hub",
        body="Notes so far: 2.\n\n## Links\n\n- lists [[german-learning]]\n"
        "- lists [[masters-thesis]]\n",
    ),
    "library/04-learning/masters-thesis.md": lib_note(
        "masters-thesis",
        aliases=["thesis"],
        body=f"## Facts\n\n- {THESIS_FACT}\n\n## Links\n\n- related_to [[german-learning]]\n",
    ),
    "library/04-learning/german-learning.md": lib_note(
        "german-learning",
        typ="topic",
        aliases=["German"],
        body=f"## Facts\n\n- German class is on Mondays. {SRC}\n\n## Links\n\n",
    ),
    "library/11-people/ana.md": lib_note(
        "ana",
        typ="person",
        body=f"## Facts\n\n- Ana supervises the [[masters-thesis]]. {SRC}\n\n## Links\n\n"
        "- knows [[masters-thesis]]\n",
    ),
    "library/05-money/savings.md": lib_note(
        "savings",
        typ="goal",
        area="05-money",
        sensitive=True,
        description="Savings goal",
        body=f"## Facts\n\n- {BUDGET_FACT}\n\n## Links\n\n- related_to [[masters-thesis]]\n",
    ),
}


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def make_brain(tmp_path):
    """A small library brain in a git repo, maps built and committed (like the real one)."""
    repo = tmp_path / "brain"
    for rel, text in FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8", newline="\n")
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    from yggdras.data.maps.build import run as write_maps

    write_maps(repo)
    ignored = ("map.json", "*.html", "vis-network.min.js", "*.woff2")  # as the real brain
    (repo / ".gitignore").write_text(
        "".join(f"library/00-manual/generated/{p}\n" for p in ignored), encoding="utf-8"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    return repo


@pytest.fixture
def brain(tmp_path):
    return make_brain(tmp_path)


def wp(repo, tmp_path, **kw):
    return WritePath(repo, repo / "library", tmp_path / "locks", today=TODAY, **kw)


def apply(repo, tmp_path, ops):
    w = wp(repo, tmp_path)
    return w.apply(build_change(w.root, False, ops, TODAY), "test", "a request")


def tree(repo):
    """Every note's content (line endings normalised: git for Windows writes CRLF on revert)."""
    return {
        p.relative_to(repo).as_posix(): hashlib.sha256(
            p.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        for folder in ("library", "archive")
        if (repo / folder).exists()
        for p in (repo / folder).rglob("*")
        if p.is_file() and "generated" not in p.parts
    }


def commits(repo):
    return git(repo, "log", "--format=%s").splitlines()


# ---------------------------------------------------------------- note edits


def test_a_replaced_fact_goes_to_history_with_until_or_wrong():
    text = lib_note("x", body=f"## Facts\n\n- {THESIS_FACT}\n\n## Links\n\n")
    new = "The thesis is due in April 2031. (src: manoj, 2030-11-07)"
    out = nf.to_history(text, THESIS_FACT, "until: 2030-11-07", replacement=new)
    assert nf.fact_lines(out) == [new]
    assert nf.history_lines(out) == [
        "The thesis is due in March 2031. (src: self, 2030-01-01; until: 2030-11-07)"
    ]
    wrong = nf.to_history(text, "The thesis is due in March 2031", "wrong: misread")
    assert nf.fact_lines(wrong) == []
    assert nf.history_lines(wrong)[0].endswith("; wrong: misread)")
    assert out.index("## Links") < out.index("## History")


def test_hub_listing_stays_sorted_and_counted():
    hub = FILES["library/04-learning/hub-learning.md"]
    out = nf.hub_listing(hub, "algebra", add=True)
    assert [t for _, t in nf.link_lines(out)] == ["algebra", "german-learning", "masters-thesis"]
    assert "Notes so far: 3." in out
    back = nf.hub_listing(out, "algebra", add=False)
    assert "Notes so far: 2." in back and "algebra" not in back


def test_links_are_added_and_removed_by_verb_and_target():
    text = FILES["library/11-people/ana.md"]
    out = nf.add_link(text, "member_of", "german-learning")
    assert ("member_of", "german-learning") in nf.link_lines(out)
    out, gone = nf.remove_link(out, "knows", "masters-thesis")
    assert gone == 1 and ("knows", "masters-thesis") not in nf.link_lines(out)


# ---------------------------------------------------------------- placement and detection


def test_placement_follows_the_taxonomy_type_first():
    assert shelf_for("person", "04-learning") == "11-people"
    assert shelf_for("concept", "cross") == "10-ideas"
    assert shelf_for("event", "04-learning") == "04-learning"
    assert shelf_for("project", "cross") is None  # unsure: Lia asks
    notes = [("person", "people"), ("person", "people"), ("topic", "topics")]
    assert flat_folder("person", notes) == "people"
    assert flat_folder("event", notes) == "people"  # most notes, when no note has the type


def test_duplicates_and_conflicts_are_found_by_free_code():
    from yggdras.data.graph import structural as st
    from yggdras.data.maps.notes import load_notes

    root = None
    notes = {"masters-thesis": type("N", (), {"name": "Masters Thesis", "aliases": ["thesis"]})()}
    assert detect.likely_duplicates(notes, "Thesis")[0].why.startswith("same name or alias")
    assert detect.likely_duplicates(notes, "Master's thesis plan")[0].slug == "masters-thesis"
    assert detect.likely_duplicates(notes, "Garden") == []
    exams = {"a2-exam": type("N", (), {"name": "A2 exam", "aliases": []})()}
    assert detect.likely_duplicates(exams, "B1 exam") == []  # A2 and B1 differ
    clash = detect.conflicting_facts([THESIS_FACT], "The thesis is due in May 2031.")
    assert clash == [THESIS_FACT]
    assert detect.conflicting_facts([THESIS_FACT], "Ana likes tea.") == []
    del root, load_notes, st


# ---------------------------------------------------------------- the checker


def checker(repo):
    return Checker(repo / "library")


def test_the_checker_refuses_each_broken_rule(brain):
    c = checker(brain)
    thesis = (brain / "library/04-learning/masters-thesis.md").read_text(encoding="utf-8")
    cases = {
        "path": {"00-manual/x.md": lib_note("x")},
        "placement": {"08-rest-joy/ana2.md": lib_note("ana2", typ="person", area="08-rest-joy")},
        "frontmatter": {"04-learning/wrong-name.md": lib_note("other")},
        "links": {
            "04-learning/masters-thesis.md": nf.add_link(thesis, "flew", "ana"),
        },
        "history": {
            "04-learning/masters-thesis.md": thesis.replace(f"- {THESIS_FACT}\n", ""),
        },
        "sensitivity": {
            "05-money/savings.md": FILES["library/05-money/savings.md"].replace(
                "sensitivity: high\n", ""
            ),
        },
        "description": {
            "04-learning/exam.md": lib_note("exam", typ="event", description="Exam on 2031-01-14")
            + "## Facts\n\n## Links\n\n- part_of [[german-learning]]\n"
        },
    }
    for rule, change in cases.items():
        verdict = c.check(change)
        assert not verdict.ok, rule
        assert rule in {i.rule for i in verdict.hard}, (rule, [str(i) for i in verdict.hard])


def test_the_checker_refuses_a_link_written_twice_or_dangling(brain):
    c = checker(brain)
    german = (brain / "library/04-learning/german-learning.md").read_text(encoding="utf-8")
    twice = c.check(
        {"04-learning/german-learning.md": nf.add_link(german, "related_to", "masters-thesis")}
    )
    assert any("already written" in i.message for i in twice.hard)
    dangling = c.check({"04-learning/german-learning.md": nf.add_link(german, "uses", "pond")})
    assert any("points to no note" in i.message for i in dangling.hard)


def test_the_checker_passes_a_good_new_note_with_lint_warnings(brain):
    text = nf.new_note(
        id="id-exam",
        slug="a2-exam",
        name="A2 exam",
        type="event",
        area="04-learning",
        description="German A2 exam",
        aliases=["A2 test"],
        created=TODAY,
        facts=[f"The A2 exam is booked for 2031-01-14. (src: manoj, {TODAY})"],
        links=[("part_of", "german-learning")],
    )
    verdict = checker(brain).check({"04-learning/a2-exam.md": text})
    assert verdict.ok, [str(i) for i in verdict.hard]
    assert any("Not recorded yet" in w.message for w in verdict.warnings)


# ---------------------------------------------------------------- operations


def test_adding_is_direct_and_changing_needs_confirm():
    assert not needs_confirm([{"op": "add_fact"}, {"op": "link"}, {"op": "create_note"}])
    for op in ("replace_fact", "remove_fact", "unlink", "archive_note"):
        assert needs_confirm([{"op": "add_fact"}, {"op": op}])


def test_a_fact_line_gets_one_full_stop_even_after_a_quote():
    from yggdras.data.brain.ops import fact_line

    assert fact_line('Log: "Stop now."', TODAY) == f'Log: "Stop now." (src: manoj, {TODAY})'
    assert fact_line("Ana likes tea.", TODAY) == f"Ana likes tea. (src: manoj, {TODAY})"


def test_a_replacement_that_changes_nothing_is_refused(brain):
    with pytest.raises(OpError, match="use remove_fact"):
        build_change(
            brain / "library",
            False,
            [
                {
                    "op": "replace_fact",
                    "slug": "masters-thesis",
                    "old": THESIS_FACT,
                    "text": "The thesis is due in March 2031",
                    "mode": "wrong",
                }
            ],
            TODAY,
        )


def test_an_unknown_note_or_fact_is_an_op_error(brain):
    root = brain / "library"
    with pytest.raises(OpError, match="no note"):
        build_change(root, False, [{"op": "add_fact", "slug": "pond", "text": "x"}], TODAY)
    with pytest.raises(OpError, match="not .exactly once"):
        build_change(
            root,
            False,
            [
                {
                    "op": "remove_fact",
                    "slug": "masters-thesis",
                    "old": "Nothing like this.",
                    "mode": "until",
                }
            ],
            TODAY,
        )
    with pytest.raises(OpError, match="mode"):
        build_change(
            root,
            False,
            [{"op": "remove_fact", "slug": "masters-thesis", "old": THESIS_FACT, "mode": "later"}],
            TODAY,
        )


# ---------------------------------------------------------------- the write path


def test_one_request_is_one_commit_with_log_and_maps(brain, tmp_path):
    out = apply(
        brain,
        tmp_path,
        [
            {"op": "add_fact", "slug": "masters-thesis", "text": "Ana reviews chapter two"},
            {"op": "link", "from": "masters-thesis", "verb": "advances", "to": "german-learning"},
        ],
    )
    assert out.status == "written", out.message
    assert commits(brain)[0].startswith("lia: add fact to masters-thesis; link masters-thesis")
    assert git(brain, "status", "--porcelain") == ""  # maps committed with the change
    changed = git(brain, "show", "--name-only", "--pretty=format:", "HEAD").split()
    assert "library/00-manual/log.md" in changed
    assert any("generated/" in p for p in changed)
    log = (brain / "library/00-manual/log.md").read_text(encoding="utf-8")
    assert f"- {TODAY} add fact to masters-thesis (asked by Manoj via test)" in log
    text = (brain / "library/04-learning/masters-thesis.md").read_text(encoding="utf-8")
    assert f"- Ana reviews chapter two. (src: manoj, {TODAY})" in text
    assert f"updated: {TODAY}" in text


def test_a_new_note_is_placed_listed_in_its_hub_and_checked(brain, tmp_path):
    out = apply(
        brain,
        tmp_path,
        [
            {
                "op": "create_note",
                "type": "person",
                "name": "Ben Ortiz",
                "area": "04-learning",
                "description": "Thesis co-supervisor",
                "aliases": ["Ben"],
                "facts": [{"text": "Ben Ortiz co-supervises the thesis"}],
                "links": [{"verb": "knows", "to": "ana"}],
            }
        ],
    )
    assert out.status == "written", [str(i) for i in out.issues]
    assert (brain / "library/11-people/ben-ortiz.md").is_file()
    hub = (brain / "library/04-learning/hub-learning.md").read_text(encoding="utf-8")
    assert "- lists [[ben-ortiz]]" in hub and "Notes so far: 3." in hub


def test_a_new_note_is_in_the_viewers_data_after_the_write_and_gone_after_undo(brain, tmp_path):
    served = tmp_path / "local-data" / "viewer"
    w = WritePath(brain, brain / "library", tmp_path / "locks", today=TODAY, viewer_dirs=(served,))
    ops = [
        {
            "op": "create_note",
            "type": "event",
            "name": "India trip",
            "area": "02-relationships",
            "description": "Family trip to India",
            "aliases": ["India visit"],
            "links": [{"verb": "related_to", "to": "ana"}],
        }
    ]
    out = w.apply(build_change(w.root, False, ops, TODAY), "test")
    assert out.status == "written" and out.viewer_error == ""
    pages = [served / "graph.html", brain / "library/00-manual/generated/graph.html"]
    for page in pages:
        assert '"slug": "india-trip"' in page.read_text(encoding="utf-8"), page
    assert git(brain, "status", "--porcelain") == ""  # the brain's page is git-ignored
    w.undo(out.sha, "test")
    for page in pages:
        assert '"slug": "india-trip"' not in page.read_text(encoding="utf-8"), page


def test_a_viewer_failure_never_undoes_the_write(brain, tmp_path, monkeypatch):
    from yggdras.data.graph import viewer

    def broken(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(viewer, "render", broken)
    out = apply(brain, tmp_path, [{"op": "add_fact", "slug": "ana", "text": "Ana likes tea"}])
    assert out.status == "written" and "disk full" in out.viewer_error
    assert "Ana likes tea" in (brain / "library/11-people/ana.md").read_text(encoding="utf-8")


def test_hand_edits_block_the_write_and_nothing_is_written(brain, tmp_path):
    path = brain / "library/04-learning/german-learning.md"
    path.write_text(path.read_text(encoding="utf-8") + "\nhand edit\n", encoding="utf-8")
    before = tree(brain)
    out = apply(brain, tmp_path, [{"op": "add_fact", "slug": "ana", "text": "Ana likes tea"}])
    assert out.status == "blocked" and out.dirty == ["library/04-learning/german-learning.md"]
    assert tree(brain) == before and commits(brain) == ["base"]


def test_dirty_generated_maps_do_not_block(brain, tmp_path):
    gen = brain / "library/00-manual/generated/atlas.md"
    gen.write_text("stale\n", encoding="utf-8")
    out = apply(brain, tmp_path, [{"op": "add_fact", "slug": "ana", "text": "Ana likes tea"}])
    assert out.status == "written"


def test_one_write_at_a_time(brain, tmp_path):
    with git_repo.write_lock(tmp_path / "locks"):
        out = apply(brain, tmp_path, [{"op": "add_fact", "slug": "ana", "text": "Ana likes tea"}])
    assert out.status == "blocked" and "another change" in out.message
    assert commits(brain) == ["base"]


def test_a_failed_write_leaves_the_tree_as_it_was(brain, tmp_path, monkeypatch):
    before = tree(brain)

    def boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(git_repo, "commit", boom)
    with pytest.raises(RuntimeError):
        apply(
            brain,
            tmp_path,
            [
                {
                    "op": "create_note",
                    "type": "concept",
                    "name": "Edge AI",
                    "area": "cross",
                    "description": "Edge AI",
                    "aliases": ["TinyML"],
                }
            ],
        )
    assert tree(brain) == before
    assert (
        git(brain, "status", "--porcelain", "--", "library/04-learning", "library/10-ideas") == ""
    )


def test_sensitivity_is_kept_when_a_fact_is_added(brain, tmp_path):
    out = apply(brain, tmp_path, [{"op": "add_fact", "slug": "savings", "text": "Saving started"}])
    assert out.status == "written"
    text = (brain / "library/05-money/savings.md").read_text(encoding="utf-8")
    assert "sensitivity: high" in text


def test_archive_removes_inbound_links_and_undo_restores_everything(brain, tmp_path):
    before = tree(brain)
    out = apply(brain, tmp_path, [{"op": "archive_note", "slug": "masters-thesis"}])
    assert out.status == "written", [str(i) for i in out.issues]
    assert (brain / "archive/library/04-learning/masters-thesis.md").is_file()
    assert not (brain / "library/04-learning/masters-thesis.md").exists()
    ana = (brain / "library/11-people/ana.md").read_text(encoding="utf-8")
    assert "[[masters-thesis]]" not in ana and "supervises the Masters Thesis" in ana
    hub = (brain / "library/04-learning/hub-learning.md").read_text(encoding="utf-8")
    assert "masters-thesis" not in hub and "Notes so far: 1." in hub
    undone = wp(brain, tmp_path).undo(out.sha, "test")
    assert undone.status == "written", undone.message
    after = tree(brain)
    log = "library/00-manual/log.md"
    assert {k: v for k, v in after.items() if k != log} == {
        k: v for k, v in before.items() if k != log
    }
    text = (brain / log).read_text(encoding="utf-8")
    assert "archive masters-thesis" in text and "undone archive masters-thesis" in text
    assert git(brain, "status", "--porcelain") == ""
    assert commits(brain)[0].startswith("lia: undo ")


def test_undo_stops_when_a_later_change_touched_the_same_note(brain, tmp_path):
    first = apply(brain, tmp_path, [{"op": "add_fact", "slug": "ana", "text": "Ana likes tea"}])
    apply(brain, tmp_path, [{"op": "add_fact", "slug": "ana", "text": "Ana likes cake"}])
    out = wp(brain, tmp_path).undo(first.sha, "test")
    assert out.status == "blocked" and out.later
    assert "Ana likes tea" in (brain / "library/11-people/ana.md").read_text(encoding="utf-8")


def test_only_lias_changes_can_be_undone(brain, tmp_path):
    base = git(brain, "rev-parse", "HEAD").strip()
    assert wp(brain, tmp_path).undo(base, "test").status == "blocked"


def test_a_flat_brain_gets_new_notes_in_the_folder_of_their_type(tmp_path):
    repo = tmp_path / "flat"
    for rel, body in {
        "brain/people/ada.md": "---\nid: a\nslug: ada\nname: Ada\ntype: person\n"
        'description: "A person"\naliases: []\n---\n\n## Facts\n\n- Ada flew. (src: x, '
        "2030-01-01)\n\n## Links\n\n- flew [[moon]]\n",
        "brain/topics/moon.md": "---\nid: m\nslug: moon\nname: Moon\ntype: topic\n"
        'description: "The Moon"\naliases: []\n---\n\n## Facts\n\n## Links\n',
    }.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(body, encoding="utf-8", newline="\n")
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    w = WritePath(repo, repo / "brain", tmp_path / "locks", flat=True, today=TODAY)
    ops = [
        {
            "op": "create_note",
            "type": "person",
            "name": "Bob",
            "description": "A pilot",
            "aliases": ["Robert"],
            "links": [{"verb": "knows", "to": "ada"}],
        }
    ]
    out = w.apply(build_change(w.root, True, ops, TODAY), "test")
    assert out.status == "written", [str(i) for i in out.issues]  # old free verbs don't block
    assert (repo / "brain/people/bob.md").is_file()


# ---------------------------------------------------------------- the pending store


def test_previews_expire_after_a_day_and_carry_a_random_token(tmp_path):
    store = Store(tmp_path / "y.db")
    now = time.time()
    a = store.add("change x", "test", [{"op": "unlink"}], "- preview", now=now)
    b = store.add("change y", "test", [], "", now=now)
    assert a.token != b.token and len(a.token) >= 20
    assert store.get(a.id, now + 3600).state == "pending"
    assert store.get(a.id, now + 25 * 3600).state == "expired"
    assert [p.id for p in store.open_items(now + 3600)] == [b.id]


def test_unlink_finds_the_line_whichever_note_holds_it(brain, tmp_path):
    # ana holds "knows [[masters-thesis]]"; asked the other way round (knows is symmetric)
    out = apply(
        brain, tmp_path, [{"op": "unlink", "from": "masters-thesis", "verb": "knows", "to": "ana"}]
    )
    assert out.status == "written", out.message
    ana = (brain / "library/11-people/ana.md").read_text(encoding="utf-8")
    assert "- knows [[masters-thesis]]" not in ana
