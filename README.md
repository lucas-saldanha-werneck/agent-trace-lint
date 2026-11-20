# agent-trace-lint

Independent demo, not affiliated with Quantori.

A small command-line tool that reads a log of an LLM agent's tool calls and points out the mistakes that break agents in production: a retry that books twice, a call with the wrong arguments, a call that never got an answer.

I built it as a short demo for a Senior AI Engineer application. It uses the Python standard library only and has no network access.

## The problem

When an agent calls a tool and the call times out, the agent usually tries again. If the tool books a visit or opens a ticket, the second call can do the same thing a second time. The fix is an idempotency key, but nothing checks that the key is there. This tool does.

## What it checks

| Rule | Meaning |
| --- | --- |
| `duplicate-side-effect` | A tool that is not marked idempotent was called again with the same arguments and no `idempotency_key`. |
| `bad-arguments` | A missing required argument, an unknown argument, or the wrong type. |
| `unknown-tool` | The agent called a tool that is not in the tool spec. |
| `orphan-call` | A tool call never got a result. |
| `orphan-result` | A result points at a call that does not exist. |
| `double-result` | One call has more than one result. |
| `retry-storm` | The same call, with the same arguments, ran more than N times in a row (default 3). |

## Run it

```bash
pip install .
agent-trace-lint examples/trace_example.jsonl --tools examples/tools.json
```

The exit code is 1 if any finding is an error, 0 if not, and 2 if a file cannot be read. Add `--out report.md` to save the report.

The trace is JSON Lines: one `tool_call` event (`id`, `tool`, `args`) or `tool_result` event (`call_id`, `ok`) per line. Other events are ignored. See `examples/` for both files. The example trace is **invented sample data**, not a real conversation.

On the example trace the tool reports four findings, including a `book_visit` call retried after a timeout without an idempotency key.

## Tests

```bash
pip install pytest .
pytest -q
```

## What was tested

- 16 automated tests, all offline, run with pytest. They cover every rule, the edge cases (a boolean is not an integer, a retry with an idempotency key is allowed, an idempotent tool may repeat) and the command-line exit codes.
- The same tests and one run of the command on the example trace run in GitHub Actions on every push.

## What was not tested

- No real agent traces. The only input is the small invented example, so I do not know how many false alarms it gives on traces from a real framework.
- No trace format from any specific framework (LangGraph, OpenAI, Anthropic and others). You have to convert logs to the simple format above.
- Argument checking is basic: types only, no nested objects, enums or formats.
- Python 3.12 only in CI. It should work on 3.10 and later, but I did not run those.
- Large files: the whole trace is loaded into memory.
