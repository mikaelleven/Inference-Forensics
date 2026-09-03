#!/usr/bin/env python3
"""Run reproducible coding fixtures across Pi and Codex harness/model profiles."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from codex_runner import CodexResult, CodexWrapper
from pi_runner import PiResult, PiWrapper

ROOT = Path(__file__).resolve().parent


@dataclass
class Fixture:
    id: str
    name: str
    root: Path
    prompt_file: Path
    input_dir: Path
    evaluator: Path


@dataclass
class NormalizedRun:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0
    turns: int = 0
    tool_calls: int = 0
    cost: float = 0.0
    usage_available: bool = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="Benchmark YAML configuration.")
    parser.add_argument("--validate", action="store_true", help="Validate configuration and fixtures without running models.")
    parser.add_argument("--model", action="append", default=[], help="Run only named model profile(s); repeatable.")
    parser.add_argument("--fixture", action="append", default=[], help="Run only fixture id(s); repeatable.")
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Could not read YAML file {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return value


def resolve_config_path(config_file: Path, value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (config_file.parent / path).resolve()


def load_fixture(entry: Any, config_file: Path) -> Fixture:
    if isinstance(entry, str):
        fixture_id = entry
        fixture_root = ROOT / "fixtures" / fixture_id
    elif isinstance(entry, dict):
        fixture_id = str(entry.get("id", "")).strip()
        if not fixture_id:
            raise ValueError("Fixture entry is missing 'id'.")
        configured_path = entry.get("path")
        fixture_root = resolve_config_path(config_file, configured_path) if configured_path else ROOT / "fixtures" / fixture_id
    else:
        raise ValueError(f"Invalid fixture entry: {entry!r}")

    manifest_path = fixture_root / "fixture.yaml"
    manifest = load_yaml(manifest_path)
    manifest_id = str(manifest.get("id", "")).strip()
    if manifest_id != fixture_id:
        raise ValueError(f"Fixture id mismatch: config={fixture_id!r}, manifest={manifest_id!r}")

    prompt_file = fixture_root / str(manifest.get("prompt_file", "prompt.md"))
    input_dir = fixture_root / str(manifest.get("input_dir", "input"))
    evaluator = fixture_root / str(manifest.get("evaluator", "evaluator/evaluate.py"))
    for path, label in ((prompt_file, "prompt"), (input_dir, "input directory"), (evaluator, "evaluator")):
        if not path.exists():
            raise ValueError(f"Fixture {fixture_id}: {label} not found: {path}")

    return Fixture(
        id=fixture_id,
        name=str(manifest.get("name", fixture_id)),
        root=fixture_root.resolve(),
        prompt_file=prompt_file.resolve(),
        input_dir=input_dir.resolve(),
        evaluator=evaluator.resolve(),
    )


def enabled_entries(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        raise ValueError("'models' must be a list.")
    result: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict):
            raise ValueError(f"Invalid model profile: {value!r}")
        if value.get("enabled", True):
            result.append(value)
    return result


def validate_model(model: dict[str, Any]) -> None:
    for key in ("name", "harness", "model"):
        if not str(model.get(key, "")).strip():
            raise ValueError(f"Model profile is missing '{key}': {model}")
    harness = str(model["harness"]).lower()
    if harness not in {"pi", "codex"}:
        raise ValueError(f"Unsupported harness {harness!r} in profile {model['name']!r}")
    if harness == "pi" and not str(model.get("provider", "")).strip():
        raise ValueError(f"Pi model profile {model['name']!r} is missing 'provider'.")


def executable(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    path = Path(name)
    if path.is_file():
        return str(path.resolve())
    raise FileNotFoundError(f"Executable was not found: {name}")


def create_runner(model: dict[str, Any], timeout: int):
    harness = str(model["harness"]).lower()
    reasoning = reasoning_value(model.get("reasoning", "off"))
    if harness == "codex":
        return CodexWrapper(
            executable(str(model.get("codex_path", "codex"))),
            timeout,
            model=str(model["model"]),
            reasoning_effort=normalize_codex_reasoning(reasoning),
        )

    provider = str(model["provider"])
    ollama = model.get("ollama") if isinstance(model.get("ollama"), dict) else {}
    return PiWrapper(
        executable(str(model.get("pi_path", "pi"))),
        timeout,
        provider=provider,
        model=str(model["model"]),
        reasoning=reasoning,
        temperature=optional_float(model.get("temperature")),
        top_p=optional_float(model.get("top_p")),
        seed=optional_int(model.get("seed")),
        context_window=int(ollama.get("context_window", model.get("context_window", 65536))),
        max_tokens=int(ollama.get("max_tokens", model.get("max_tokens", 8192))),
        ollama_base_url=str(ollama.get("base_url", "http://localhost:11434/v1")),
        supports_reasoning=optional_bool(ollama.get("supports_reasoning", model.get("supports_reasoning"))),
        tools=[str(x) for x in model.get("tools", [])] or None,
        offline_startup=bool(model.get("offline_startup", True)),
    )


def reasoning_value(value: Any) -> str:
    if isinstance(value, bool):
        return "medium" if value else "off"
    if value is None:
        return "off"
    text = str(value).strip().lower()
    return {"none": "off", "on": "medium", "false": "off", "true": "medium"}.get(text, text)


def normalize_codex_reasoning(value: str) -> str:
    value = value.lower().strip()
    aliases = {"off": "none", "on": "medium"}
    return aliases.get(value, value)


def optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def optional_bool(value: Any) -> bool | None:
    return None if value is None else bool(value)


def codex_usage(result: CodexResult) -> NormalizedRun:
    def total(key: str) -> int:
        return sum(int(v.get(key, 0) or 0) for v in result.usage if isinstance(v, dict))

    input_tokens = total("input_tokens")
    output_tokens = total("output_tokens")
    cached = total("cached_input_tokens")
    return NormalizedRun(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached,
        total_tokens=input_tokens + output_tokens,
        usage_available=bool(result.usage),
    )


def pi_usage(result: PiResult) -> NormalizedRun:
    usage = result.usage
    return NormalizedRun(
        input_tokens=int(usage.get("input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
        cached_input_tokens=int(usage.get("cached_input_tokens", 0)),
        cache_write_tokens=int(usage.get("cache_write_tokens", 0)),
        total_tokens=int(usage.get("total_tokens", 0)),
        turns=int(usage.get("turns", 0)),
        tool_calls=sum(result.tool_calls.values()),
        cost=float(usage.get("cost", 0.0)),
        usage_available=bool(usage.get("usage_available", False)),
    )


def run_evaluator(fixture: Fixture, workspace: Path, timeout: int) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(fixture.evaluator), str(workspace)],
        cwd=fixture.root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    parsed: dict[str, Any] | None = None
    for line in reversed(completed.stdout.splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            parsed = candidate
            break
    return {
        "return_code": completed.returncode,
        "result": parsed or {"passed": False, "score": 0.0, "error": "Evaluator did not emit JSON."},
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def run_once(
    *,
    runner: Any,
    model: dict[str, Any],
    fixture: Fixture,
    system_prompt: str,
    timeout: int,
    artifact_dir: Path | None,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"benchmark-{fixture.id}-") as temp_dir:
        workspace = Path(temp_dir) / "workspace"
        shutil.copytree(fixture.input_dir, workspace)
        prompt = fixture.prompt_file.read_text(encoding="utf-8")

        started = time.perf_counter()
        if str(model["harness"]).lower() == "codex":
            result = runner.run(
                prompt,
                workdir=workspace,
                sandbox=str(model.get("sandbox", "workspace-write")),
                system_prompt=system_prompt,
                load_skills=False,
            )
            usage = codex_usage(result)
            tool_calls: dict[str, int] = {}
            applied = {"reasoning": reasoning_value(model.get("reasoning", "off")), "sandbox": model.get("sandbox", "workspace-write")}
            ignored = {key: model[key] for key in ("temperature", "top_p", "seed") if model.get(key) is not None}
        else:
            result = runner.run(prompt, workdir=workspace, system_prompt=system_prompt)
            usage = pi_usage(result)
            tool_calls = result.tool_calls
            applied = result.applied_settings
            ignored = result.ignored_settings
        duration = time.perf_counter() - started

        evaluation = run_evaluator(fixture, workspace, timeout)
        eval_result = evaluation["result"]
        task_passed = bool(eval_result.get("passed", False))
        score = float(eval_result.get("score", 1.0 if task_passed else 0.0) or 0.0)

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model_profile": str(model["name"]),
            "harness": str(model["harness"]).lower(),
            "provider": model.get("provider"),
            "model": str(model["model"]),
            "reasoning": reasoning_value(model.get("reasoning", "off")),
            "fixture": fixture.id,
            "fixture_name": fixture.name,
            "harness_return_code": result.return_code,
            "harness_ok": result.return_code == 0,
            "task_passed": task_passed,
            "success": result.return_code == 0 and task_passed,
            "score": score,
            "duration_seconds": round(duration, 4),
            **asdict(usage),
            "tool_breakdown": tool_calls,
            "applied_settings": applied,
            "ignored_settings": ignored,
            "evaluation": eval_result,
        }

        if artifact_dir is not None:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / "record.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            (artifact_dir / "assistant.txt").write_text(result.assistant_text + "\n", encoding="utf-8")
            (artifact_dir / "runner.jsonl").write_text(result.jsonl, encoding="utf-8")
            (artifact_dir / "stderr.txt").write_text(result.stderr, encoding="utf-8")
            (artifact_dir / "evaluation.json").write_text(json.dumps(evaluation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            if bool(model.get("save_workspace", True)):
                shutil.copytree(workspace, artifact_dir / "workspace")

        return record


def safe_component(value: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in value) or "unnamed"


def median(values: list[float | int]) -> float:
    return round(float(statistics.median(values)), 4) if values else 0.0


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault((record["model_profile"], record["fixture"]), []).append(record)

    rows: list[dict[str, Any]] = []
    for (profile, fixture), values in groups.items():
        rows.append({
            "model_profile": profile,
            "fixture": fixture,
            "runs": len(values),
            "successes": sum(1 for v in values if v["success"]),
            "success_rate": round(sum(1 for v in values if v["success"]) / len(values), 4),
            "median_score": median([v["score"] for v in values]),
            "median_time_s": median([v["duration_seconds"] for v in values]),
            "median_input_tokens": median([v["input_tokens"] for v in values]),
            "median_output_tokens": median([v["output_tokens"] for v in values]),
            "median_cached_tokens": median([v["cached_input_tokens"] for v in values]),
            "median_total_tokens": median([v["total_tokens"] for v in values]),
            "median_turns": median([v["turns"] for v in values]),
            "median_tool_calls": median([v["tool_calls"] for v in values]),
        })
    rows.sort(key=lambda r: (r["model_profile"], r["fixture"]))
    return {"by_model_fixture": rows}


def summary_markdown(summary: dict[str, Any]) -> str:
    rows = summary["by_model_fixture"]
    headers = ["Model profile", "Fixture", "Success", "Score", "Time s", "Input", "Output", "Cached", "Turns", "Tools"]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in rows:
        lines.append(
            "| " + " | ".join([
                str(r["model_profile"]), str(r["fixture"]), f"{r['successes']}/{r['runs']}",
                str(r["median_score"]), str(r["median_time_s"]), str(r["median_input_tokens"]),
                str(r["median_output_tokens"]), str(r["median_cached_tokens"]), str(r["median_turns"]),
                str(r["median_tool_calls"]),
            ]) + " |"
        )
    lines.extend([
        "",
        "> Token counts are exact only within the tokenizer/provider that reported them. Compare task success and wall-clock across different model families before comparing raw token counts directly.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    config_file = args.config.resolve()
    config = load_yaml(config_file)
    bench = config.get("benchmark") if isinstance(config.get("benchmark"), dict) else {}

    fixture_entries = config.get("fixtures")
    if not isinstance(fixture_entries, list):
        raise ValueError("'fixtures' must be a list.")
    fixtures = [load_fixture(entry, config_file) for entry in fixture_entries]
    if args.fixture:
        requested = set(args.fixture)
        fixtures = [f for f in fixtures if f.id in requested]

    models = enabled_entries(config.get("models"))
    for model in models:
        validate_model(model)
    if args.model:
        requested = set(args.model)
        models = [m for m in models if str(m["name"]) in requested]

    if not fixtures:
        raise ValueError("No fixtures selected.")
    if not models:
        raise ValueError("No model profiles selected.")

    system_prompt_path = resolve_config_path(config_file, bench.get("system_prompt_file", ROOT / "benchmark-system-prompt.md"))
    system_prompt = system_prompt_path.read_text(encoding="utf-8")

    print("Fixtures:", ", ".join(f.id for f in fixtures))
    print("Models  :", ", ".join(str(m["name"]) for m in models))
    if args.validate:
        print("Configuration and fixtures are valid.")
        return 0

    runs = int(bench.get("runs", 1))
    warmup_runs = int(bench.get("warmup_runs", 0))
    timeout = int(bench.get("timeout_seconds", 300))
    if runs < 1 or warmup_runs < 0 or timeout < 1:
        raise ValueError("runs must be >= 1, warmup_runs >= 0, timeout_seconds >= 1.")

    output_setting = bench.get("output_dir")
    if output_setting:
        output_root = resolve_config_path(config_file, output_setting)
    else:
        output_root = ROOT / "results"
    run_dir = output_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(config_file, run_dir / "benchmark.yaml")
    run_log = run_dir / "runs.jsonl"

    measured_records: list[dict[str, Any]] = []

    for model in models:
        profile = str(model["name"])
        runner = create_runner(model, timeout)
        for fixture in fixtures:
            for warmup in range(1, warmup_runs + 1):
                print(f"[warmup {warmup}/{warmup_runs}] {profile} / {fixture.id}", flush=True)
                run_once(
                    runner=runner, model=model, fixture=fixture, system_prompt=system_prompt,
                    timeout=timeout, artifact_dir=None,
                )

            for run_number in range(1, runs + 1):
                print(f"[run {run_number}/{runs}] {profile} / {fixture.id}", flush=True)
                artifact_dir = run_dir / "artifacts" / safe_component(profile) / fixture.id / f"run-{run_number:02d}"
                record = run_once(
                    runner=runner, model=model, fixture=fixture, system_prompt=system_prompt,
                    timeout=timeout, artifact_dir=artifact_dir,
                )
                measured_records.append(record)
                with run_log.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(
                    f"  success={record['success']} score={record['score']:.2f} "
                    f"time={record['duration_seconds']:.2f}s "
                    f"tokens={record['input_tokens']}+{record['output_tokens']} "
                    f"turns={record['turns']} tools={record['tool_calls']}",
                    flush=True,
                )

    summary = summarize(measured_records)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown = summary_markdown(summary)
    (run_dir / "summary.md").write_text(markdown, encoding="utf-8")
    print("\n" + markdown)
    print(f"Artifacts: {run_dir}")
    return 0 if all(record["success"] for record in measured_records) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileNotFoundError, NotADirectoryError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
