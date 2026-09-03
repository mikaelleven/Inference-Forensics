# Harness / Model Benchmark

Small, deterministic benchmark harness for comparing coding models and coding-agent harnesses.

## Purpose

The suite answers two different questions without mixing them:

1. **Model comparison under a common harness** — run different cloud/local models through Pi against the same fixtures.
2. **Harness comparison** — run the same model/fixture through Pi and native Codex and compare the practical outcome.

The primary quality signal is the fixture's external evaluator. Token usage, wall-clock time, turns and tool calls are secondary metrics.

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
fixtures/
  01-simple/
  02-medium/
  03-tricky/
results/
```

Each fixture contains:

```text
fixture.yaml
prompt.md
input/                 # copied to a fresh temporary workspace for every run
evaluator/             # external; never copied into the workspace
```

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
```

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
  summary.md
  artifacts/<model>/<fixture>/run-XX/
    record.json
    runner.jsonl
    stderr.txt
    assistant.txt
    evaluation.json
    workspace/
```

The summary reports success rate, evaluator score, time, token usage, turns, and tool calls. For Codex, turn/tool-call counts may be unavailable depending on the CLI JSON event schema, so they remain zero rather than being guessed.

## Isolation / fairness decisions

Pi and Codex are both pointed at a temporary workspace containing only `fixture/input`. The shared benchmark prompt instructs the agent not to access parent or unrelated directories. This is practical benchmark isolation, not a general-purpose OS security boundary. If strict read isolation is required, run the benchmark inside a container/VM and mount only the workspace plus required executables/auth.

For model-vs-model comparisons, prefer **Pi for all models**. For practical harness comparisons, include native Codex as a separate baseline. Do not mix those conclusions: `Pi + model A` vs `Pi + model B` is closer to a model comparison; `Pi + model A` vs `Codex + model A` measures harness effects too.

## Pi / OpenAI Codex caveat

Pi's built-in `openai-codex` catalog and routing can lag account/model availability. Before enabling a newly released model profile, verify it with Pi, for example:

```powershell
pi --list-models gpt-5.6
```

If a model works in native Codex but not through Pi, keep the native Codex profile as the baseline and treat the Pi profile as unavailable rather than as a model-quality failure.
