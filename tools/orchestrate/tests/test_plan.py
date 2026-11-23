from orchestrate.plan import Check, Task, globs_overlap, schedule, validate


def task(id, touches, checks=("true",), deps=()):
    return Task(id, "x", list(touches), [Check(c) for c in checks], "x", list(deps))


def test_valid_plan_has_no_problems():
    assert validate([task("a", ["docs/a.md"]), task("b", ["docs/b.md"])]) == []


def test_task_without_checks_is_refused():
    assert any("no checks" in p for p in validate([task("a", ["docs/a.md"], checks=())]))


def test_empty_plan_and_too_many_tasks_are_refused():
    assert validate([]) == ["The plan has no tasks."]
    many = [task(f"t{i}", [f"docs/{i}.md"]) for i in range(7)]
    assert any("limit is 6" in p for p in validate(many))


def test_protected_paths_are_refused():
    for path in (".claude/settings.json", ".github/**", "app/api/migrations/042_x.sql", ".env",
                 "app/api/.env", "railway.json", "**"):  # fmt: skip
        assert any("protected" in p for p in validate([task("a", [path])])), path


def test_duplicate_ids_unknown_deps_and_cycles():
    assert any("used twice" in p for p in validate([task("a", ["x"]), task("a", ["y"])]))
    assert any("unknown task" in p for p in validate([task("a", ["x"], deps=["zz"])]))
    cyc = [task("a", ["x"], deps=["b"]), task("b", ["y"], deps=["a"])]
    assert validate(cyc) == ["The task dependencies form a cycle."]


def test_bad_slug_is_refused():
    assert any("slug" in p for p in validate([task("Bad Id", ["x"])]))


def test_glob_overlap():
    assert globs_overlap("docs/a.md", "docs/a.md")
    assert globs_overlap("docs/*", "docs/a.md")
    assert globs_overlap("tools/**", "tools/tests/test_x.py")
    assert globs_overlap("**/x.py", "a/b/x.py")
    assert not globs_overlap("docs/a.md", "docs/b.md")
    assert not globs_overlap("tools/tests/*", "app/web/*")
    assert globs_overlap("tools/*", "tools/te*")  # unsure means overlap


def test_phase2_task_file_is_a_valid_disjoint_plan():
    import json
    from pathlib import Path

    from orchestrate.plan import task_from_dict

    raw = json.loads((Path(__file__).parents[1] / "phase2-tasks.json").read_text())["tasks"]
    tasks = schedule([task_from_dict(t) for t in raw])
    assert validate(tasks) == []
    assert all(t.depends_on == [] for t in tasks)  # disjoint, so they may run in parallel
    assert tasks[0].holdout_checks  # the deliberate send-back


def test_overlapping_tasks_are_serialized_in_order():
    tasks = schedule(
        [task("a", ["tools/*.py"]), task("b", ["docs/x.md"]), task("c", ["tools/x.py"])]
    )
    assert tasks[0].depends_on == [] and tasks[1].depends_on == []
    assert tasks[2].depends_on == ["a"]
