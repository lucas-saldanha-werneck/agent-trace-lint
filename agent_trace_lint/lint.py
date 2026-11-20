"""Lint a JSONL trace of LLM agent tool calls.

Trace events (one JSON object per line):
  {"type": "tool_call",   "id": "c1", "tool": "book_visit", "args": {...}}
  {"type": "tool_result", "call_id": "c1", "ok": true, "error": null}
  {"type": "message", ...}   # ignored

Tool spec (JSON): {"tool": {"required": [...], "properties": {"arg": "string"},
                            "idempotent": false}}
"""
from __future__ import annotations

import json
from dataclasses import dataclass

TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
}


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str  # "error" or "warning"
    line: int
    message: str


def load_trace(text: str) -> list[dict]:
    events = []
    for n, raw in enumerate(text.splitlines(), 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {n}: invalid JSON ({exc.msg})") from exc
        if not isinstance(ev, dict):
            raise ValueError(f"line {n}: event must be a JSON object")
        ev["_line"] = n
        events.append(ev)
    return events


def _key(call: dict) -> str:
    return call["tool"] + json.dumps(call.get("args", {}), sort_keys=True)


def _check_args(call: dict, spec: dict) -> list[str]:
    problems = []
    args = call.get("args", {})
    if not isinstance(args, dict):
        return ["args is not an object"]
    for name in spec.get("required", []):
        if name not in args:
            problems.append(f"missing required argument '{name}'")
    props = spec.get("properties", {})
    for name, value in args.items():
        if name not in props:
            problems.append(f"unknown argument '{name}'")
            continue
        want = TYPES.get(props[name])
        if want is None:
            continue
        # bool is a subclass of int in Python; do not accept True as integer
        bad = not isinstance(value, want) or (
            isinstance(value, bool) and props[name] in ("integer", "number")
        )
        if bad:
            problems.append(f"argument '{name}' should be {props[name]}")
    return problems


def lint_trace(events: list[dict], tools: dict, max_repeats: int = 3) -> list[Finding]:
    out: list[Finding] = []
    calls: dict[str, dict] = {}
    answered: set[str] = set()
    seen_effects: dict[str, dict] = {}
    streak_key, streak = None, 0

    for ev in events:
        kind, line = ev.get("type"), ev["_line"]
        if kind == "tool_call":
            cid, tool = ev.get("id"), ev.get("tool")
            calls[cid] = ev
            spec = tools.get(tool)
            if spec is None:
                out.append(Finding("unknown-tool", "error", line, f"tool '{tool}' is not in the spec"))
                continue
            for p in _check_args(ev, spec):
                out.append(Finding("bad-arguments", "error", line, f"{tool}: {p}"))

            k = _key(ev)
            if k == streak_key:
                streak += 1
            else:
                streak_key, streak = k, 1
            if streak == max_repeats + 1:
                out.append(Finding("retry-storm", "warning", line,
                                   f"{tool} called with identical arguments more than {max_repeats} times in a row"))

            if not spec.get("idempotent", False):
                prev = seen_effects.get(k)
                if prev is not None and "idempotency_key" not in ev.get("args", {}):
                    out.append(Finding(
                        "duplicate-side-effect", "error", line,
                        f"{tool} repeated with the same arguments as line {prev['_line']} "
                        "and no idempotency_key: a retry can run the action twice"))
                seen_effects.setdefault(k, ev)
        elif kind == "tool_result":
            cid = ev.get("call_id")
            if cid not in calls:
                out.append(Finding("orphan-result", "error", line, f"result for unknown call '{cid}'"))
            elif cid in answered:
                out.append(Finding("double-result", "warning", line, f"call '{cid}' has more than one result"))
            answered.add(cid)

    for cid, call in calls.items():
        if cid not in answered:
            out.append(Finding("orphan-call", "error", call["_line"],
                               f"call '{cid}' ({call.get('tool')}) never got a result"))
    return sorted(out, key=lambda f: (f.line, f.rule))
