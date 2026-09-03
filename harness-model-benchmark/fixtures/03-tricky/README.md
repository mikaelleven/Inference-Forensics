# 03-tricky benchmark fixture

A small deterministic benchmark for agentic coding/reasoning.

The agent should only receive a copy of `input/` as its writable workspace plus the contents of `prompt.md`.
Do **not** copy `evaluator/` into the agent workspace.

## Suggested benchmark flow

1. Copy `input/` to a fresh temporary directory.
2. Run Codex in that directory with `prompt.md`.
3. Run the visible tests.
4. Run the external evaluator against the modified workspace:

```bash
python path/to/03-tricky/evaluator/evaluate.py path/to/workspace
```

The evaluator emits one JSON object and exits with code 0 only for a full pass.

## Why this is "tricky"

The visible regression test exposes one symptom. The documented semantics imply additional edge cases that are
checked only by the external evaluator. A solution that patches only the visible assertion should not receive full credit.
