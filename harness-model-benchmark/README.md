# Harness / Model Benchmark

A reproducible benchmark for comparing coding models, coding-agent harnesses, and reasoning settings on deterministic, real-world-style agent tasks.

## Purpose

This sub-project evaluates how a **model + harness + thinking/reasoning** combination performs when it must complete a specific task in an isolated workspace. It is designed to answer three related, but distinct, questions:

1. **Model comparison under a common harness** — run different cloud or local models through Pi against identical fixtures.
2. **Harness comparison** — run the same model and fixture through Pi and native Codex to measure the practical effects of the harness.
3. **Efficiency comparison** — benchmark input, output, and cached-token use alongside wall-clock time, turns, and tool calls for each combination.

The primary quality signal is the fixture's deterministic external evaluator: did the agent complete the task, and what score did it earn? Token usage and operational metrics are secondary signals that describe the cost and execution profile of a successful or unsuccessful attempt.

LLM inference can still vary by provider and model. The suite makes the *benchmark process* as deterministic as practical: fixtures and prompts are versioned, every run begins from the same input tree, evaluators are deterministic Python code, and supported sampling controls are fixed. Run multiple repetitions and compare success rates rather than treating any single LLM run as conclusive.

## Principles

- Static, versioned fixtures; every measured run starts from the same pristine `input/` tree.
- Hidden evaluator code is never copied into the agent workspace.
- Deterministic evaluation in Python; no LLM-as-judge.
- No Pi extensions, skills, prompt templates, themes or context files during benchmark runs.
- Pi uses an explicit built-in tool allowlist and an ephemeral session.
- Codex uses an isolated temporary `CODEX_HOME`, ignores user config, disables skills and runs against an explicit workspace.
- Raw harness output is preserved beside normalized metrics.
- Different tokenizers make cross-family raw token counts imperfect; success rate and wall-clock are the stronger cross-model signals.

## Layout

```text
benchmark.py
pi_runner.py
codex_runner.py
benchmark-system-prompt.md
benchmark.example.yaml
benchmark_baseline.yaml  # setup validation only; not a benchmark configuration
fixtures/
  00-validate/           # setup validation only; not a benchmark fixture
  01-simple/
  02-medium/
  03-tricky/
results/
```

## Setup validation

`benchmark_baseline.yaml` and the `00-validate` fixture validate that the test bench itself is working: the configured harnesses can run, an isolated fixture workspace is created correctly, the agent receives the task, and the fixture evaluator can produce a result. They are intentionally small checks of harness and fixture structure, not measures of agent capability.

Run this validation configuration after setup or when changing runner/fixture infrastructure:

```powershell
uv run python benchmark.py benchmark_baseline.yaml
```

Do **not** include `benchmark_baseline.yaml` or `00-validate` in an actual benchmark run, aggregate, or capability comparison. Use `benchmark.example.yaml` (copied to `benchmark.yaml`) and the numbered task fixtures such as `01-simple`, `02-medium`, and `03-tricky` for those measurements.

## Fixtures

A **fixture** is one self-contained benchmark task. It defines the task presented to the agent, the starting files it may inspect or modify, and an external program that evaluates the completed workspace. Fixtures represent concrete agent work such as validating output, repairing code, or making a specified change—not open-ended chat questions.

Each fixture contains:

```text
fixture.yaml           # id, prompt, input directory, and evaluator entry point
prompt.md              # task instructions shown to the agent
input/                 # copied to a fresh temporary workspace for every run
evaluator/             # external; never copied into the agent workspace
```

To use a benchmark fixture, add its `id` to the `fixtures` list in `benchmark.yaml`, then run the benchmark:

```yaml
fixtures:
  - id: 01-simple
  - id: 03-tricky
```

Run one benchmark fixture while developing or comparing profiles:

```powershell
uv run python benchmark.py benchmark.yaml --fixture 03-tricky
```

`00-validate` is reserved for setup validation through `benchmark_baseline.yaml`; see [Setup validation](#setup-validation).

The runner copies only `input/` into a new temporary workspace for each attempt and invokes the evaluator afterward. Keep evaluator code and expected answers outside `input/`; the agent must not be able to read them. Create a new fixture by following this structure, choosing a unique directory/id, writing a focused `prompt.md`, providing its pristine `input/`, and declaring the evaluator in `fixture.yaml`.

## Requirements

- Python 3.11+
- `uv sync` (or `pip install -r requirements.txt`)
- Pi when using `harness: pi`
- Codex CLI when using `harness: codex`
- Ollama when using `provider: ollama`

Current Pi installation:

```powershell
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
```

For ChatGPT/Codex through Pi, start `pi`, run `/login`, and select **ChatGPT Plus/Pro (Codex)**. The runner copies only Pi's existing `auth.json` into a temporary agent directory for each run.

For Ollama:

```powershell
ollama pull qwen3.5:4b
ollama serve
```

The Pi runner generates a temporary `models.json` pointing at Ollama's OpenAI-compatible `/v1` endpoint. Sampling parameters such as `temperature`, `top_p`, and `seed` are applied there. Reasoning levels are mapped to Ollama's `none/low/medium/high/max` values.

## Configuration

Copy the example and edit it:

```powershell
Copy-Item benchmark.example.yaml benchmark.yaml
```

Important model fields:

```yaml
- name: qwen35-4b-pi
  harness: pi
  provider: ollama
  model: qwen3.5:4b
  reasoning: low
  temperature: 0.0
  top_p: 1.0
  seed: 42
```

```yaml
- name: terra-low-codex
  harness: codex
  model: gpt-5.6-terra
  reasoning: low
  sandbox: workspace-write
  approve_for_me: true
```

`approve_for_me` is `false` by default. Set it to `true` only with
`sandbox: workspace-write` for an unattended agent task that must modify its
isolated workspace. Codex CLI uses `--approve-for-me` to select that sandbox,
so the runner does not also pass `--sandbox`. Read-only profiles must leave it
disabled.

`temperature`, `top_p`, and `seed` are currently applied by this suite only to Pi+Ollama profiles. If configured for Pi+OpenAI/Codex or native Codex, they are recorded under `ignored_settings` instead of silently pretending they were applied.

## Run

Validate only:

```powershell
uv run python benchmark.py benchmark.yaml --validate
```

Run everything:

```powershell
uv run python benchmark.py benchmark.yaml
```

Filter profiles/fixtures:

```powershell
uv run python benchmark.py benchmark.yaml --model terra-low-pi --model qwen35-4b-pi --fixture 03-tricky
```

## Output

A run creates:

```text
results/<timestamp>/
  benchmark.yaml
  runs.jsonl
  summary.json
  summary.txt
  artifacts/<model>/<fixture>/run-XX/
    record.json
    runner.jsonl
    stderr.txt
    assistant.txt
    evaluation.json
    workspace/
```

The plain-text summary table reports success rate, evaluator score, time, token usage, turns, and tool calls. `Input`, `Output`, and `Cached` show the token accounting provided by the selected harness; use them to compare the token profile of comparable model/harness/reasoning runs. Because tokenizers and provider accounting differ, raw token totals are not exact cross-family cost comparisons. Numeric values are compacted dynamically for terminal readability (for example, `10.5K` for large token counts). For Codex, turn/tool-call counts may be unavailable depending on the CLI JSON event schema, so they remain zero rather than being guessed.

The following is an example **setup-validation** summary for `00-validate`; it demonstrates the report format only and must not be used to compare benchmark capability:

| Model profile | Fixture | Success | Score | Time s | Input | Output | Cached | Turns | Tools |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| luna-high-codex | 00-validate | 1/1 | 1 | 21.94 | 22.8K | 434 | 14.6K | 0 | 0 |
| luna-high-pi | 00-validate | 1/1 | 1 | 20.73 | 4.2K | 163 | 0 | 4 | 3 |
| luna-none-pi | 00-validate | 1/1 | 1 | 20.01 | 4.1K | 127 | 0 | 4 | 3 |

## Isolation / fairness decisions

Pi and Codex are both pointed at a temporary workspace containing only `fixture/input`. The shared benchmark prompt instructs the agent not to access parent or unrelated directories. This is practical benchmark isolation, not a general-purpose OS security boundary. If strict read isolation is required, run the benchmark inside a container/VM and mount only the workspace plus required executables/auth.

For model-vs-model comparisons, prefer **Pi for all models**. For practical harness comparisons, include native Codex as a separate baseline. Do not mix those conclusions: `Pi + model A` vs `Pi + model B` is closer to a model comparison; `Pi + model A` vs `Codex + model A` measures harness effects too.

## Pi / OpenAI Codex caveat

Pi's built-in `openai-codex` catalog and routing can lag account/model availability. Before enabling a newly released model profile, verify it with Pi, for example:

```powershell
pi --list-models gpt-5.6
```

If a model works in native Codex but not through Pi, keep the native Codex profile as the baseline and treat the Pi profile as unavailable rather than as a model-quality failure.
