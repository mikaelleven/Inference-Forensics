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

The runner executes every case in its own temporary `CODEX_HOME`, always passes `--json`, and uses a new `codex exec --ephemeral` read-only, non-interactive process. The benchmark also loads `lean.config.toml` as the `lean` profile while ignoring the normal user config. The `--no-skills` cases receive an empty `CODEX_HOME`; the `--load-skills` cases receive only the included `dummy-skill` fixture.

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

## Run the benchmark

```powershell
python .\check-skills\benchmark.py
python .\check-skills\benchmark.py --passes 5 --payload-file .\check-skills\payload.txt
```

The benchmark runs tests 3–6 from `benchmark_tests.json` plus a custom-system-prompt test. Each run is logged in `runs.jsonl` and saved as an individual JSON artifact. Token usage is calculated as `actual = input + output`, `effective = actual - payload size`, and `billable = actual - cached`; payload size is the payload file size in bytes divided by 3. The default payload is `payload.txt`.

## Expected outcomes

The expectations in `skill_tests.json` are intentionally the supplied hypotheses. The runner does not alter them to match observed behavior: unexpected skill interpretation is reported as `fail` and preserved in the artifacts.

## Files

- `benchmark-system-prompt.txt` — the model-instructions file supplied through `model_instructions_file`; `developer_instructions` remains empty.
- `.agents/skills/dummy-skill/SKILL.md` — the only skill fixture.
- `skill_tests.json` — the complete skill experiment matrix and expected control values.
- `benchmark_tests.json` — benchmark matrix containing tests 3–6 plus the custom system-prompt test.
- `payload.txt` — default payload appended to each benchmark prompt.
- `benchmark-alternate-system-prompt.txt` — alternate model-instructions file used by the additional benchmark test.
- `lean.config.toml` — minimal benchmark profile with project instructions, web search, MCP/apps/plugins, subagents, and optional context blocks disabled; skill instructions remain enabled for the selective skill cases.
- `codex_runner.py` — reusable isolated Codex CLI wrapper. It accepts prompt text or a custom prompt file, supports a custom temporary prompt filename, and exposes parsed JSONL events and usage data through `CodexResult`.
- `check_skills.py` — the skill-specific test runner.
- `benchmark.py` — benchmark runner with multi-pass timing and token-usage statistics.
