# Check Skills

`check_skills.py` is an isolated, repeatable Codex CLI experiment for observing how prompt spellings and skill loading affect skill invocation and token usage. The reusable Codex invocation code lives in `codex_runner.py` so other test scripts can use the same isolated setup.

## Purpose and goals

These tests investigate how Codex CLI interprets skill references under controlled conditions. They compare explicit and implicit skill names, the presence or absence of loaded skills, and an equivalent custom system prompt.

The goals are to:

- establish evidence for when a skill is invoked, rather than assuming that a prompt spelling guarantees it;
- measure the context and billable-token cost of loading skills compared with placing equivalent instructions in a custom system prompt;
- check whether context size materially affects execution time; and
- provide isolated, reviewable artifacts that can support future experiments with harness configuration and agent behaviour.

## Test cases and expected outcomes

A **match** means that the `dummy-skill` completed its intended task. **Pass** and **fail** describe whether the test produced its expected outcome, regardless of whether there was a skill match.

| Test | Invocation and setup | Expected outcome |
| --- | --- | --- |
| Explicit (no skills) | `/$<skill-name>`; no skills loaded | No match, because no skills are loaded. |
| Implicit (no skills) | `<skill-name>`; no skills loaded | No match, because no skills are loaded. |
| Explicit 1 (skills loaded) | `/$<skill-name>`; skills loaded | Match, because the skill is loaded. |
| Explicit 2 (skills loaded) | `$<skill-name>`; skills loaded | Match, because the skill is loaded. |
| Implicit (skills loaded) | `<skill-name>`; skills loaded | A match may occur, because the skill is loaded. |
| No match (skills loaded) | `<random-name>`; skills loaded | No match, despite skills being loaded, because the referenced name is misspelled as `n1o-sk2ill`. |
| System prompt (no skills) | Custom system prompt; no skills loaded | Match, because the custom system prompt includes instructions equivalent to the skill. |
| System prompt (skills) | The same custom system prompt; skills loaded | Match, because the custom system prompt includes instructions equivalent to the skill. |

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

The benchmark runs tests 3–6 from `benchmark_tests.json` plus the custom-system-prompt cases with and without skills loaded. Each run is logged in `runs.jsonl` and saved as an individual JSON artifact. Token usage is calculated as `actual = input + output`, `effective = actual - payload size`, and `billable = actual - cached`; payload size is the payload file size in bytes divided by 3. The default payload is `payload.txt`.

## Observed results

The following is an observed benchmark snapshot, not a universal guarantee. The results aggregate three passes per test. The payload size was approximately 39 tokens per run. An `x` denotes a match in every pass; `*` denotes mixed match results across passes.

| Name | Match | Pass | Fail | Input | Effective | Billable | Time (avg / min / max) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Explicit (no skills) | – | 3 | 0 | 12,234 | 12,189 | 4,626 | 7.1s / 6.2s / 8.3s |
| Implicit (no skills) | – | 3 | 0 | 12,231 | 12,186 | 783 | 8.6s / 7.7s / 9.9s |
| Explicit 1 (skills loaded) | x | 3 | 0 | 15,079 | 15,055 | 7,492 | 9.3s / 7.6s / 11.4s |
| Explicit 2 (skills loaded) | x | 2 | 1 | 15,065 | 15,041 | 4,662 | 8.1s / 7.8s / 8.5s |
| Implicit (skills loaded) | * | 2 | 1 | 14,520 | 14,490 | 3,087 | 7.7s / 6.9s / 8.1s |
| No match (skills loaded) | – | 2 | 1 | 58,757 | 58,881 | 26,742 | 10.0s / 6.6s / 16.1s |
| System prompt (no skills) | x | 3 | 0 | 12,174 | 12,156 | 3,825 | 7.0s / 6.8s / 7.3s |
| System prompt (skills) | x | 3 | 0 | 14,463 | 14,445 | 5,090 | 7.5s / 6.5s / 9.2s |

### Conclusions from the current observations

- Even with a short, strict system prompt, outputs can vary between runs. These tests cannot always be made 100% reproducible.
- A relatively narrow profile can be created in about 4,000 input tokens per pass.
- Within this small sample, execution time does not appear to be materially affected by context size.
- Disabling skills and then referring to `/$<skill-name>` does not force Codex CLI to read a particular skill.
- With skills loaded, explicit references generally work with both `/$<skill-name>` and `$<skill-name>`. Naming the skill directly as `<skill-name>` also often works. The failed `Explicit 2` row demonstrates that this behaviour is not perfectly deterministic.
- `Implicit (skills loaded)` produced mixed match results across its three passes, further demonstrating the difficulty of obtaining fully reproducible results from implicit skill references.
- The tailored system prompt with skills disabled remains the most stable and token-efficient observed configuration. Loading skills with the same system prompt increased effective token usage from 12,156 to 14,445—about 19%, or approximately 20%. This is consistent with the roughly 20% token overhead observed for comparable skill-loaded cases.

These are empirical observations from the current setup and model state. Repeat the benchmark with multiple passes before treating them as broadly generalisable.

## Expected outcomes

The expectations in `skill_tests.json` are intentionally the supplied hypotheses. The runner does not alter them to match observed behavior: unexpected skill interpretation is reported as `fail` and preserved in the artifacts.

## Files

- `benchmark-system-prompt.txt` — the model-instructions file supplied through `model_instructions_file`; `developer_instructions` remains empty.
- `.agents/skills/dummy-skill/SKILL.md` — the only skill fixture.
- `skill_tests.json` — the complete skill experiment matrix and expected control values.
- `benchmark_tests.json` — benchmark matrix containing tests 3–6 plus the custom-system-prompt cases with and without skills loaded.
- `payload.txt` — default payload appended to each benchmark prompt.
- `benchmark-alternate-system-prompt.txt` — alternate model-instructions file used by the additional benchmark test.
- `lean.config.toml` — minimal benchmark profile with project instructions, web search, MCP/apps/plugins, subagents, and optional context blocks disabled; skill instructions remain enabled for the selective skill cases.
- `codex_runner.py` — reusable isolated Codex CLI wrapper. It accepts prompt text or a custom prompt file, supports a custom temporary prompt filename, and exposes parsed JSONL events and usage data through `CodexResult`.
- `check_skills.py` — the skill-specific test runner.
- `benchmark.py` — benchmark runner with multi-pass timing and token-usage statistics.
