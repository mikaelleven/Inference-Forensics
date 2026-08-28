#!/usr/bin/env python3
"""Benchmark the selected skill tests and compare their token usage."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .codex_runner import CodexResult, CodexWrapper
except ImportError:
    # The benchmark is also intended to be executed directly as a script.
    from codex_runner import CodexResult, CodexWrapper

ROOT = Path(__file__).resolve().parent
TESTS = json.loads((ROOT / "benchmark_tests.json").read_text(encoding="utf-8"))
SKILL_SOURCE = ROOT.parent / ".agents" / "skills" / "dummy-skill"
LEAN_PROFILE = ROOT / "lean.config.toml"
MODEL = "gpt-5.6-luna"
THINKING_LEVEL = "none"


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def control_values(text: str) -> tuple[str, str]:
    control = re.search(r"(?mi)^Control:\s*(\S+)\s*$", text)
    skill = re.search(r"(?mi)^Skill:\s*(\S+)\s*$", text)
    return (control.group(1) if control else "MISSING", skill.group(1) if skill else "MISSING")


def resolve_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else ROOT / path


def build_prompt(test: dict[str, Any], payload: str) -> str:
    prompt = str(test["prompt"]).rstrip()
    payload = payload.rstrip()
    if not payload:
        return prompt
    return f"{prompt} {payload}"


def usage_total(usages: list[dict[str, Any]], key: str) -> int:
    return sum(
        int(value[key])
        for value in usages
        if isinstance(value.get(key), (int, float))
    )


def run_usage(result: CodexResult, payload_size: float) -> dict[str, Any]:
    input_tokens = usage_total(result.usage, "input_tokens")
    output_tokens = usage_total(result.usage, "output_tokens")
    cached_tokens = usage_total(result.usage, "cached_input_tokens")
    actual_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached_tokens,
        "actual_tokens": actual_tokens,
        "effective_tokens": round(actual_tokens - payload_size),
        "billable_tokens": round(actual_tokens - cached_tokens),
        "usage_available": bool(result.usage),
    }


def format_number(value: int | float) -> str:
    return str(round(value))


def format_duration(value: float) -> str:
    rounded = round(value, 1)
    return f"{rounded:.1f}" if rounded < 1000 else str(round(rounded))


def format_response(text: str) -> str:
    single_line = " ".join(text.split())
    return single_line if len(single_line) <= 80 else single_line[:77] + "..."


def match_found(text: str, word: str | None) -> bool:
    if not word:
        return False
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.IGNORECASE) is not None


def match_marker(matches: list[bool]) -> str:
    if all(matches):
        return "x"
    if any(matches):
        return "*"
    return "-"


def terminal_table(rows: list[tuple[str, str, int, int, str, str, str, str]]) -> str:
    headers = (
        "Name",
        "Match",
        "Pass",
        "Fail",
        "Input",
        "Effective",
        "Billable",
        "Time (avg / min / max)",
    )
    values = [
        (name, match, str(passed), str(failed), input_tokens, effective_tokens, billable_tokens, timing)
        for name, match, passed, failed, input_tokens, effective_tokens, billable_tokens, timing in rows
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in values))
        for index in range(len(headers))
    ]

    def format_row(row: tuple[str, str, str, str, str, str, str, str]) -> str:
        cells = [
            row[0].ljust(widths[0]),
            row[1].rjust(widths[1]),
            row[2].rjust(widths[2]),
            row[3].rjust(widths[3]),
            row[4].rjust(widths[4]),
            row[5].rjust(widths[5]),
            row[6].rjust(widths[6]),
            row[7].rjust(widths[7]),
        ]
        return " | ".join(cells)

    separator = "-+-".join("-" * width for width in widths)
    return "\n".join((format_row(headers), separator, *(format_row(row) for row in values)))


def save_run_artifact(directory: Path, test: dict[str, Any], record: dict[str, Any], result: CodexResult) -> None:
    artifact = {
        "run": record,
        "test": test,
        "command": result.command,
        "assistant_text": result.assistant_text,
        "usage": result.usage,
        "events": result.events,
        "stderr": result.stderr,
        "jsonl": result.jsonl,
    }
    filename = f"pass-{record['pass']:02d}-test-{test['id']:02d}.json"
    (directory / filename).write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-path", default="codex", help="Codex executable or command path.")
    parser.add_argument("--timeout", type=positive_int, default=120, help="Timeout per case in seconds.")
    parser.add_argument("--passes", type=positive_int, default=1, help="Number of passes over all tests.")
    parser.add_argument(
        "--payload-file",
        type=Path,
        default=ROOT / "payload.txt",
        help="Payload file appended to every test prompt.",
    )
    args = parser.parse_args()

    print(f"Model: {MODEL}\nThinking level: {THINKING_LEVEL}\n", flush=True)

    executable = shutil.which(args.codex_path) or args.codex_path
    if not shutil.which(args.codex_path) and not Path(args.codex_path).is_file():
        print(f"Codex executable was not found: {args.codex_path}", file=sys.stderr)
        return 2

    payload_file = args.payload_file
    if not payload_file.is_absolute():
        payload_file = Path.cwd() / payload_file
    if not payload_file.is_file():
        print(f"Payload file was not found: {payload_file}", file=sys.stderr)
        return 2

    payload = payload_file.read_text(encoding="utf-8")
    payload_size = payload_file.stat().st_size / 3
    result_directory = ROOT / "results" / ("benchmark-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    result_directory.mkdir(parents=True)
    run_log = result_directory / "runs.jsonl"
    run_log.write_text("", encoding="utf-8")

    wrapper = CodexWrapper(
        executable,
        args.timeout,
        model=MODEL,
        reasoning_effort=THINKING_LEVEL,
        system_prompt_file=ROOT / "benchmark-system-prompt.txt",
        skill_sources=(SKILL_SOURCE,),
        profile_config_file=LEAN_PROFILE,
    )
    metrics: dict[str, list[dict[str, Any]]] = {str(test["name"]): [] for test in TESTS}

    for pass_number in range(1, args.passes + 1):
        print(f"Starting pass {pass_number}/{args.passes}\n", flush=True)
        for position, test in enumerate(TESTS, start=1):
            name = str(test["name"])
            prompt = build_prompt(test, payload)
            run_options: dict[str, Any] = {}
            if test.get("system_prompt_file"):
                run_options["system_prompt_file"] = resolve_path(test["system_prompt_file"])
            if test.get("system_prompt_filename"):
                run_options["system_prompt_filename"] = test["system_prompt_filename"]

            started = time.perf_counter()
            result = wrapper.run(
                prompt,
                load_skills=test["mode"] == "--load-skills",
                **run_options,
            )
            duration_seconds = time.perf_counter() - started
            control, skill = control_values(result.assistant_text)
            expected = test["expected"]
            passed = result.return_code == 0 and control == expected["control"] and skill == expected["skill"]
            match_word = test.get("match", expected.get("match"))
            if match_word is not None:
                match_word = str(match_word)
            matched = match_found(result.assistant_text, match_word)
            usage = run_usage(result, payload_size)
            record = {
                "pass": pass_number,
                "test_id": test["id"],
                "name": name,
                "mode": test["mode"],
                "duration_seconds": duration_seconds,
                "return_code": result.return_code,
                "passed": passed,
                "control": control,
                "skill": skill,
                "match": match_word,
                "matched": matched,
                "expected": expected,
                "payload_size": payload_size,
                **usage,
            }
            metrics[name].append(record)
            with run_log.open("a", encoding="utf-8") as log_file:
                log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            save_run_artifact(result_directory, test, record, result)
            print(
                f"{position}/{len(TESTS)}: {name}: "
                f"{'pass' if passed else 'fail'}, "
                f"time={duration_seconds:.3f}s, "
                f"tokens(in={usage['input_tokens']}, out={usage['output_tokens']}, "
                f"actual={usage['actual_tokens']}, cached={usage['cached_tokens']}, "
                f"effective={format_number(usage['effective_tokens'])}, "
                f"billable={usage['billable_tokens']})\n"
                f"{format_response(result.assistant_text)}\n",
                flush=True,
            )

    table_rows: list[tuple[str, str, int, int, str, str, str, str]] = []
    for test in TESTS:
        name = str(test["name"])
        runs = metrics[name]
        passed_count = sum(1 for run in runs if run["passed"])
        failed_count = len(runs) - passed_count
        match_status = match_marker([run["matched"] for run in runs])
        input_tokens = sum(run["input_tokens"] for run in runs)
        effective_tokens = sum(run["effective_tokens"] for run in runs)
        billable_tokens = sum(run["billable_tokens"] for run in runs)
        durations = [run["duration_seconds"] for run in runs]
        input_usage = format_number(input_tokens)
        effective_usage = format_number(effective_tokens)
        billable_usage = format_number(billable_tokens)
        timing = (
            f"{format_duration(sum(durations) / len(durations))}s / "
            f"{format_duration(min(durations))}s / {format_duration(max(durations))}s"
        )
        table_rows.append(
            (name, match_status, passed_count, failed_count, input_usage, effective_usage, billable_usage, timing)
        )

    summary = terminal_table(table_rows)
    print("\n" + summary)
    payload_summary = f"payload size: ~{format_number(payload_size)} tokens/run"
    print(f"\n{payload_summary}")
    print(f"\nArtifacts: {result_directory}")
    (result_directory / "summary.txt").write_text(
        summary + f"\n\n{payload_summary}\n",
        encoding="utf-8",
    )
    return 0 if all(run["passed"] for runs in metrics.values() for run in runs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
