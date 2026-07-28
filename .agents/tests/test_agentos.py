from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".agents"))

from agentos.core import (
    assess_clarity, suggested_questions, save_task, approve_task,
    check_write, enforce_tool_budget, record_tool_call, prepare_change,
    instruction_check, docs_check
)


def test_ambiguous_request_is_blocked():
    a = assess_clarity({
        "intent": "modify_existing_feature",
        "target": None,
        "expected_behavior": None,
        "current_behavior": None,
        "acceptance_criteria": [],
        "scope": None,
        "risk": "medium",
    })
    assert a.status == "needs_clarification"
    assert suggested_questions(a)


def test_ready_task_can_be_approved_and_prepared(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# test", encoding="utf-8")
    (tmp_path / ".agents/config").mkdir(parents=True)
    governance = json.loads((ROOT / ".agents/config/governance.json").read_text(encoding="utf-8"))
    (tmp_path / ".agents/config/governance.json").write_text(json.dumps(governance), encoding="utf-8")
    (tmp_path / "src/demo").mkdir(parents=True)
    (tmp_path / "src/demo/a.py").write_text("def existing():\n    return 1\n", encoding="utf-8")

    a = assess_clarity({
        "intent": "modify_existing_feature",
        "target": "src/demo/a.py",
        "expected_behavior": "Return 2",
        "current_behavior": "Returns 1",
        "acceptance_criteria": ["existing() returns 2"],
        "scope": "src/demo/a.py and tests",
        "risk": "low",
    })
    save_task(tmp_path, "T1", "Change return value", a)
    approve_task(tmp_path, "T1")
    out = prepare_change(tmp_path, "T1", "modify", "src/demo/a.py", "return value", ["existing"])
    assert out["allowed"]


def test_write_is_blocked_before_clarification(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# test", encoding="utf-8")
    (tmp_path / ".agents/config").mkdir(parents=True)
    governance = json.loads((ROOT / ".agents/config/governance.json").read_text(encoding="utf-8"))
    (tmp_path / ".agents/config/governance.json").write_text(json.dumps(governance), encoding="utf-8")
    a = assess_clarity({"intent": "fix", "risk": "medium"})
    save_task(tmp_path, "T2", "Fix it", a)
    out = check_write(tmp_path, "T2", "src/x.py")
    assert not out["allowed"]
    assert out["reason"] == "task_needs_clarification"


def test_identical_tool_call_is_denied(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# test", encoding="utf-8")
    (tmp_path / ".agents/config").mkdir(parents=True)
    governance = json.loads((ROOT / ".agents/config/governance.json").read_text(encoding="utf-8"))
    (tmp_path / ".agents/config/governance.json").write_text(json.dumps(governance), encoding="utf-8")
    a = assess_clarity({
        "intent": "inspect", "target": "src/x.py", "expected_behavior": "Understand x",
        "acceptance_criteria": ["Relevant symbol found"], "scope": "read-only", "risk": "low"
    })
    save_task(tmp_path, "T3", "Inspect x", a)
    args = {"path": "src/x.py", "start": 1, "end": 80}
    assert enforce_tool_budget(tmp_path, "T3", "read", args)["allowed"]
    record_tool_call(tmp_path, "T3", "read", args, True, output_summary="done")
    assert not enforce_tool_budget(tmp_path, "T3", "read", args)["allowed"]


def test_single_instruction_source():
    assert instruction_check(ROOT)["ok"]


def test_bilingual_documentation_is_synchronized():
    out = docs_check(ROOT)
    assert out["ok"], out
    assert out["version"]["consistent"]
    assert out["bilingual_markers"]["vi"]
    assert out["bilingual_markers"]["en"]
    assert out["changelog_has_current_version"]
