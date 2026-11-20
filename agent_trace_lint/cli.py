from __future__ import annotations

import argparse
import json
import sys

from .lint import lint_trace, load_trace


def render(findings, total_events: int) -> str:
    lines = [f"# agent-trace-lint report", "", f"Events read: {total_events}", f"Findings: {len(findings)}", ""]
    for f in findings:
        lines.append(f"- [{f.severity}] line {f.line} `{f.rule}`: {f.message}")
    if not findings:
        lines.append("No findings.")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="agent-trace-lint", description=__doc__)
    p.add_argument("trace", help="JSONL trace file")
    p.add_argument("--tools", required=True, help="JSON tool spec file")
    p.add_argument("--max-repeats", type=int, default=3)
    p.add_argument("--out", help="write the report to this file too")
    a = p.parse_args(argv)
    try:
        with open(a.tools, encoding="utf-8") as fh:
            tools = json.load(fh)
        with open(a.trace, encoding="utf-8") as fh:
            events = load_trace(fh.read())
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    findings = lint_trace(events, tools, a.max_repeats)
    report = render(findings, len(events))
    print(report, end="")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(report)
    return 1 if any(f.severity == "error" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
