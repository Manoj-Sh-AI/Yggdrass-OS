"""Eval runner: loading, composition rules, rendering, recording. It never grades."""

import datetime as dt

import pytest
import yaml

from yggdras.tooling import eval_runner as er


def make_set(**overrides):
    """A question set that meets the composition rules: 20 questions, 10 exit."""
    kinds = ["negative"] * 5 + ["multi-hop"] * 3 + ["page-precise"] * 2 + ["temporal"] * 2
    kinds += ["direct"] * 8
    questions = []
    for i, kind in enumerate(kinds):
        q = {
            "id": f"q{i:02d}",
            "kind": kind,
            "exit": i < 10,
            "question": f"Question {i}?",
            "expected_answer": "I don't have that" if kind == "negative" else f"Answer {i}",
        }
        if kind != "negative":
            q["required_facts"] = [f"fact {i}"]
            q["expected_nodes"] = ["index.md", f"topics/node-{i}.md"]
        questions.append(q)
    questions[0].update(overrides)
    return {"questions": questions}


@pytest.fixture
def qfile(tmp_path):
    def write(data):
        path = tmp_path / "questions.yaml"
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
        return path

    return write


def test_valid_set_has_no_problems(qfile):
    questions = er.load_questions(qfile(make_set()))
    assert len(questions) == 20
    assert er.composition_problems(questions) == []


def test_missing_required_field_is_rejected(qfile):
    data = make_set()
    del data["questions"][3]["expected_answer"]
    with pytest.raises(ValueError, match="expected_answer"):
        er.load_questions(qfile(data))


def test_missing_questions_list_is_rejected(qfile):
    with pytest.raises(ValueError, match="questions"):
        er.load_questions(qfile({"other": []}))


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda qs: qs.__setitem__(slice(None), qs[:19]), "needs 20-30"),
        (lambda qs: qs[0].update(kind="direct"), "4 negative"),
        (lambda qs: qs[5].update(kind="direct"), "2 multi-hop"),
        (lambda qs: qs[8].update(kind="direct"), "1 page-precise"),
        (lambda qs: qs[10].update(kind="direct"), "1 temporal"),
        (lambda qs: qs[12].update(exit=True), "11 exit"),
        (lambda qs: qs[1].update(id="q00"), "duplicate id q00"),
        (lambda qs: qs[12].update(kind="trivia"), "unknown kind"),
        (lambda qs: qs[12].update(required_facts=[]), "no required facts"),
        (lambda qs: qs[12].update(expected_nodes=["index.md"]), "no expected node"),
    ],
)
def test_composition_rules(qfile, mutate, expected):
    data = make_set()
    mutate(data["questions"])
    problems = er.composition_problems(er.load_questions(qfile(data)))
    assert any(expected in p for p in problems), problems


def test_render_shows_everything_but_prompt_only_hides_answers(qfile):
    q = er.load_questions(qfile(make_set()))[12]
    full = er.render(q)
    assert "Expected: Answer 12" in full and "fact 12" in full and "node-12" in full
    assert er.render(q, prompt_only=True) == "Question 12?"


def test_record_writes_dated_result_and_reports_gate(qfile, tmp_path):
    path = qfile(make_set())
    questions = er.load_questions(path)
    verdicts = {q.id: er.Verdict(True, ["index.md"]) for q in questions}
    verdicts["q03"] = er.Verdict(False, ["index.md", "areas/x.md"], "answered from wrong node")
    result = er.build_result(questions, verdicts, path, "fixture", dt.date(2030, 1, 2))
    assert result["summary"] == {"total": 20, "passed": 19, "failed": 1}
    assert result["gate_met"] is False
    first = er.write_result(result, tmp_path / "out")
    second = er.write_result(result, tmp_path / "out")
    assert first.name == "2030-01-02-run-1.yaml" and second.name == "2030-01-02-run-2.yaml"
    saved = yaml.safe_load(first.read_text(encoding="utf-8"))
    assert saved["results"][3]["notes"] == "answered from wrong node"


def test_record_refuses_incomplete_verdicts(qfile):
    path = qfile(make_set())
    questions = er.load_questions(path)
    verdicts = {q.id: er.Verdict(True, []) for q in questions[1:]}
    with pytest.raises(ValueError, match="q00"):
        er.build_result(questions, verdicts, path, None, dt.date(2030, 1, 2))


def test_verdict_file_needs_boolean_pass(tmp_path):
    path = tmp_path / "v.yaml"
    path.write_text(yaml.safe_dump({"q00": {"pass": "yes"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="boolean"):
        er.load_verdicts(path)


def test_prompt_verdicts_records_typed_answers(qfile):
    questions = er.load_questions(qfile(make_set()))[:1]
    answers = iter(["maybe", "y", "index.md, topics/node-0.md", "fine"])
    verdicts = er.prompt_verdicts(questions, ask=lambda _: next(answers), say=lambda _: None)
    assert verdicts["q00"] == er.Verdict(True, ["index.md", "topics/node-0.md"], "fine")


def test_cli_check_and_record(qfile, tmp_path, capsys):
    path = qfile(make_set())
    assert er.main(["check", str(path)]) == 0
    vfile = tmp_path / "v.yaml"
    vfile.write_text(yaml.safe_dump({f"q{i:02d}": {"pass": True} for i in range(20)}))
    assert (
        er.main(["record", str(path), "--out", str(tmp_path / "res"), "--verdicts", str(vfile)])
        == 0
    )
    assert "20/20 passed; gate met" in capsys.readouterr().out
