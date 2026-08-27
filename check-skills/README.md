# Check Skills

`check_skills.py` is an isolated, repeatable Codex CLI experiment for observing how prompt spellings and skill loading affect skill invocation and token usage. The reusable Codex invocation code lives in `codex_runner.py` so other test scripts can use the same isolated setup.

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

A timestamped directory under `check-skills/results/` contains the raw JSONL stream, parsed assistant response, extracted usage objects, and `summary.txt`. These artifacts support both behavioral review and token-usage comparison.

## Reuse the Codex runner

A separate test script can import `CodexWrapper` and provide either prompt text or a prompt file:

```python
from pathlib import Path

from codex_runner import CodexWrapper

runner = CodexWrapper(
    "codex",
    timeout_seconds=120,
    system_prompt_file=Path("custom-system-prompt.txt"),
    system_prompt_filename="experiment-instructions.txt",
)
result = runner.run("your test prompt", load_skills=False)
print(result.jsonl)  # Raw JSONL response
print(result.usage)  # Token-usage objects extracted from the JSONL
```

For one-off prompts, pass `system_prompt="..."` to `run` instead. `result.events` contains the parsed JSONL objects.

## Expected outcomes

The expectations in `skill_tests.json` are intentionally the supplied hypotheses. The runner does not alter them to match observed behavior: unexpected skill interpretation is reported as `fail` and preserved in the artifacts.

## Files

- `system-prompt.txt` — the custom control-output instruction supplied to Codex as `developer_instructions`.
- `.agents/skills/dummy-skill/SKILL.md` — the only skill fixture.
- `skill_tests.json` — the experiment matrix and expected control values.
- `codex_runner.py` — reusable isolated Codex CLI wrapper. It accepts prompt text or a custom prompt file, supports a custom temporary prompt filename, and exposes parsed JSONL events and usage data through `CodexResult`.
- `check_skills.py` — the skill-specific test runner.
