# Check Skills

`check_skills.py` is an isolated, repeatable Codex CLI experiment for observing how prompt spellings and skill loading affect skill invocation and token usage.

## Prerequisites

- Python 3.10 or later
- Codex CLI available as `codex` on `PATH`
- An authenticated Codex CLI session

## Run

```powershell
python .\\check-skills\\check_skills.py
```

Use `--codex-path` when the executable is not named `codex`:

```powershell
python .\check-skills\check_skills.py --codex-path C:\Tools\codex.cmd
```

The runner executes every case in its own temporary `CODEX_HOME`, always passes `--json`, and uses an ephemeral, read-only, non-interactive Codex session. The `--no-skills` cases receive an empty `CODEX_HOME`; the `--load-skills` cases receive only the included `dummy-skill` fixture.

A timestamped directory under `check-skills/results/` contains the raw JSONL stream, parsed assistant response, extracted usage objects, and `summary.md`. These artifacts support both behavioral review and token-usage comparison.

## Expected outcomes

The expectations in `tests.json` are intentionally the supplied hypotheses. The runner does not alter them to match observed behavior: unexpected skill interpretation is reported as `fail` and preserved in the artifacts.

## Files

- `system-prompt.txt` — the custom control-output instruction supplied to Codex as `developer_instructions`.
- `skills/dummy-skill/SKILL.md` — the only skill fixture.
- `tests.json` — the experiment matrix and expected control values.
- `check_skills.py` — reusable Codex CLI wrapper and test runner.
