import json
from pathlib import Path

import pytest

from agent_trace_lint import lint_trace, load_trace
from agent_trace_lint.cli import main

ROOT = Path(__file__).resolve().parent.parent
TOOLS = json.loads((ROOT / "examples/tools.json").read_text())


def run(lines, **kw):
    text = "\n".join(json.dumps(x) for x in lines)
    return lint_trace(load_trace(text), TOOLS, **kw)


def rules(findings):
    return [f.rule for f in findings]


def call(i, tool, **args):
    return {"type": "tool_call", "id": i, "tool": tool, "args": args}


def res(i, ok=True):
    return {"type": "tool_result", "call_id": i, "ok": ok}


def test_clean_trace_has_no_findings():
    assert run([call("a", "lookup_customer", phone="1"), res("a")]) == []


def test_orphan_call():
    assert rules(run([call("a", "lookup_customer", phone="1")])) == ["orphan-call"]


def test_orphan_result():
    assert rules(run([res("zzz")])) == ["orphan-result"]


def test_double_result():
    f = run([call("a", "lookup_customer", phone="1"), res("a"), res("a")])
    assert rules(f) == ["double-result"]


def test_unknown_tool():
    assert "unknown-tool" in rules(run([call("a", "send_sms", to="x"), res("a")]))


def test_missing_required_and_unknown_arg():
    f = run([call("a", "book_visit", slot="s", colour="red"), res("a")])
    msgs = " ".join(x.message for x in f)
    assert "missing required argument 'customer_id'" in msgs
    assert "unknown argument 'colour'" in msgs


def test_wrong_type_and_bool_is_not_integer():
    f = run([call("a", "open_ticket", customer_id="c", summary="s", priority="high"), res("a")])
    assert any("should be integer" in x.message for x in f)
    f = run([call("a", "open_ticket", customer_id="c", summary="s", priority=True), res("a")])
    assert any("should be integer" in x.message for x in f)


def test_duplicate_side_effect_after_timeout():
    f = run([
        call("a", "book_visit", customer_id="c", slot="s"), res("a", ok=False),
        call("b", "book_visit", customer_id="c", slot="s"), res("b"),
    ])
    assert rules(f) == ["duplicate-side-effect"]
    assert f[0].line == 3


def test_idempotency_key_makes_retry_safe():
    f = run([
        call("a", "book_visit", customer_id="c", slot="s", idempotency_key="k"), res("a", ok=False),
        call("b", "book_visit", customer_id="c", slot="s", idempotency_key="k"), res("b"),
    ])
    assert f == []


def test_idempotent_tool_may_repeat():
    f = run([call("a", "lookup_customer", phone="1"), res("a"),
             call("b", "lookup_customer", phone="1"), res("b")])
    assert f == []


def test_different_args_are_not_duplicates():
    f = run([call("a", "book_visit", customer_id="c", slot="s1"), res("a"),
             call("b", "book_visit", customer_id="c", slot="s2"), res("b")])
    assert f == []


def test_retry_storm_only_past_threshold():
    ev = []
    for i in range(4):
        ev += [call(f"c{i}", "lookup_customer", phone="1"), res(f"c{i}")]
    assert rules(run(ev, max_repeats=3)) == ["retry-storm"]
    assert run(ev, max_repeats=4) == []


def test_invalid_json_reports_line():
    with pytest.raises(ValueError, match="line 2"):
        load_trace('{"type":"message"}\nnot json')


def test_example_trace_findings():
    events = load_trace((ROOT / "examples/trace_example.jsonl").read_text())
    f = lint_trace(events, TOOLS)
    assert sorted(rules(f)) == ["bad-arguments", "duplicate-side-effect", "orphan-call", "unknown-tool"]
    assert [x.line for x in f if x.rule == "duplicate-side-effect"] == [6]


def test_cli_exit_codes_and_report(tmp_path, capsys):
    out = tmp_path / "r.md"
    code = main([str(ROOT / "examples/trace_example.jsonl"), "--tools", str(ROOT / "examples/tools.json"), "--out", str(out)])
    assert code == 1
    assert "duplicate-side-effect" in out.read_text()
    clean = tmp_path / "t.jsonl"
    clean.write_text(json.dumps(call("a", "lookup_customer", phone="1")) + "\n" + json.dumps(res("a")) + "\n")
    assert main([str(clean), "--tools", str(ROOT / "examples/tools.json")]) == 0


def test_cli_bad_file_returns_2(tmp_path):
    assert main([str(tmp_path / "nope.jsonl"), "--tools", str(ROOT / "examples/tools.json")]) == 2
