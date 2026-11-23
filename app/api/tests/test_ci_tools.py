"""The CI check scripts in tools/ci catch what they claim to (agentic-engineering items 30, 31, 51, 53)."""

import importlib.util
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[3] / "tools" / "ci"


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def migrations():
    return load("check_migrations")


@pytest.fixture(scope="module")
def decisions():
    return load("check_decisions")


@pytest.fixture(scope="module")
def tier():
    return load("pr_tier")


# ---- migrations ------------------------------------------------------------------------
def test_two_migrations_sharing_a_number_fail(migrations):
    found = migrations.problems(["040_a.sql", "041_b.sql", "041_c.sql"], [], {}, set())
    assert found == ["Two migrations share number 041; renumber the new one."]


def test_editing_an_applied_migration_fails(migrations):
    found = migrations.problems(["040_a.sql"], ["app/api/migrations/040_a.sql"], {}, set())
    assert "edited or removed" in found[0]


def test_not_null_column_on_existing_table_fails_and_cites_expand_contract(migrations):
    sql = "ALTER TABLE app.tasks ADD COLUMN owner text NOT NULL;"
    found = migrations.problems(["042_x.sql"], [], {"042_x.sql": sql}, set())
    assert len(found) == 1 and "Expand-contract" in found[0] and "NOT NULL" in found[0]


@pytest.mark.parametrize("sql", ["DROP TABLE app.old;", "ALTER TABLE a RENAME COLUMN b TO c;",
                                 "ALTER TABLE a ALTER COLUMN b SET NOT NULL;", "TRUNCATE app.x;"])  # fmt: skip
def test_destructive_ddl_is_detected(migrations, sql):
    assert migrations.destructive(sql)


@pytest.mark.parametrize("sql", [
    "CREATE TABLE app.t (id bigint PRIMARY KEY, name text NOT NULL);",
    "ALTER TABLE app.t ADD COLUMN flag boolean NOT NULL DEFAULT false;",
    "ALTER TABLE app.t ADD COLUMN note text;",
    "-- DROP TABLE app.t; is only a comment\nSELECT 1;",
])  # fmt: skip
def test_additive_ddl_passes(migrations, sql):
    assert migrations.destructive(sql) == []


def test_label_allows_a_reviewed_destructive_migration(migrations):
    found = migrations.problems(["042_x.sql"], [], {"042_x.sql": "DROP TABLE app.old;"},
                                {"destructive-migration-approved"})  # fmt: skip
    assert found == []


def test_committed_migrations_pass_today(migrations):
    folder = TOOLS.parents[1] / "app" / "api" / "migrations"
    names = [p.name for p in folder.glob("*.sql")]
    assert not [p for p in migrations.problems(names, [], {}, set()) if "share" in p]


# ---- decision records -----------------------------------------------------------------
def test_new_numbered_decision_record_fails(decisions):
    found = decisions.problems(["D44-x.md", "0043-foo.md"], ["0043-foo.md"])
    assert "YYYYMMDD-slug.md" in found[0]


def test_new_dated_decision_record_passes(decisions):
    assert decisions.problems(["D44-x.md", "20261122-ci-tools.md"], ["20261122-ci-tools.md"]) == []


def test_duplicate_slug_fails(decisions):
    found = decisions.problems(["chat-conductor.md", "20261122-chat-conductor.md"],
                               ["20261122-chat-conductor.md"])  # fmt: skip
    assert "share the slug 'chat-conductor'" in found[0]


def test_existing_records_are_grandfathered(decisions):
    names = [p.name for p in (TOOLS.parents[1] / "rationale" / "decisions").glob("*.md")]
    assert decisions.problems(names, names) == []


def test_a_new_undated_record_is_not_grandfathered(decisions):
    assert decisions.problems(["calendar-sync.md"], ["calendar-sync.md"])


# ---- review tier ----------------------------------------------------------------------
def test_docs_only_is_tier1(tier):
    assert tier.classify([(10, 2, "README.md"), (3, 0, "planning/x.md")])[0] == "tier1"


def test_ordinary_change_is_tier2(tier):
    assert tier.classify([(40, 5, "app/web/src/features/chat/thread.tsx")])[0] == "tier2"


def test_600_line_pr_is_tier3(tier):
    found, reasons = tier.classify([(600, 0, "app/web/src/features/chat/thread.tsx")])
    assert found == "tier3" and "600 changed lines > 400" in reasons


@pytest.mark.parametrize("path", ["app/api/migrations/042_x.sql", ".github/workflows/pr.yml",
                                  "app/api/src/yggdress_app/security.py", "railway.json",
                                  "app/api/src/yggdress_app/temporal_agent_workflow.py"])  # fmt: skip
def test_risky_paths_are_tier3(tier, path):
    assert tier.classify([(1, 0, path)])[0] == "tier3"


def test_too_many_files_or_dirs_is_tier3(tier):
    files = [(1, 0, f"d{i}/f.py") for i in range(6)]
    assert tier.classify(files)[0] == "tier3"
    assert tier.classify([(1, 0, f"app/web/f{i}.ts") for i in range(11)])[0] == "tier3"


def test_numstat_parsing_handles_binary_rows(tier):
    assert tier.parse("3\t1\ta.py\n-\t-\tlogo.png\n") == [(3, 1, "a.py"), (0, 0, "logo.png")]


# ---- dev ports ------------------------------------------------------------------------
def test_unknown_port_is_reported_with_its_line():
    ports = load("check_ports")
    found = ports.unknown_ports({"a.py": "x\nurl = 'http://127.0.0.1:4321'\n"}, {"3000"})
    assert found == ["a.py:2: port 4321 is not in dev-ports.json"]


def test_listed_ports_pass():
    ports = load("check_ports")
    assert ports.unknown_ports({"a.ts": "http://localhost:3000/x"}, {"3000"}) == []


# ---- per-worker scratch databases (items 17, 61) --------------------------------------
def scratch():
    spec = importlib.util.spec_from_file_location("scratch_db", TOOLS.parent / "scratch_db.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_two_workers_get_different_ports_folders_and_databases():
    db = scratch()
    a, b = "refactor-a", "refactor-b"
    assert db.port_for(a) != db.port_for(b)
    assert db.folder_for(a) != db.folder_for(b)
    assert db.url_for(a) != db.url_for(b) and "yggdress_test_refactor_a" in db.url_for(a)
    assert db.port_for(a) == db.port_for("Refactor A")  # stable per name


def test_scratch_urls_always_name_a_test_database():
    db = scratch()
    assert db.url_for("../../etc").rsplit("/", 1)[1].startswith("yggdress_test_")
