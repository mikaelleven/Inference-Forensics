#!/usr/bin/env python3
"""Run the isolated Codex skill-invocation experiment."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .codex_runner import CodexResult, CodexWrapper
except ImportError:
    # The runner is also intended to be executed directly as a script.
    from codex_runner import CodexResult, CodexWrapper

ROOT = Path(__file__).resolve().parent
TESTS = json.loads((ROOT / "skill_tests.json").read_text(encoding="utf-8"))
SKILL_SOURCE = ROOT.parent / ".agents" / "skills" / "dummy-skill"


def control_values(text: str) -> tuple[str, str]:
    control = re.search(r"(?mi)^Control:\s*(\S+)\s*$", text)
    skill = re.search(r"(?mi)^Skill:\s*(\S+)\s*$", text)
    return (control.group(1) if control else "MISSING", skill.group(1) if skill else "MISSING")


def terminal_table(rows: list[tuple[dict[str, Any], str, str, str, str]]) -> str:
    headers = ("#", "Name", "Status", "Control:", "Skill:", "Response:")
    values = [
        (
            str(test["id"]),
            test["name"].replace("\n", " "),
            status,
            control,
            skill,
            assistant_text.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\r"),
        )
        for test, status, control, skill, assistant_text in rows
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in values))
        for index in range(len(headers))
    ]

    def format_row(row: tuple[str, str, str, str, str, str]) -> str:
        cells = [
            row[0].rjust(widths[0]),
            row[1].ljust(widths[1]),
            row[2].center(widths[2]),
            row[3].center(widths[3]),
            row[4].center(widths[4]),
            row[5].ljust(widths[5]),
        ]
        return " | ".join(cells)

    separator = "-+-".join("-" * width for width in widths)
    return "\n".join((format_row(headers), separator, *(format_row(row) for row in values)))


def save_result(directory: Path, test: dict[str, Any], result: CodexResult, control: str, skill: str) -> None:
    artifact = {
        "test": test,
        "command": result.command,
        "return_code": result.return_code,
        "assistant_text": result.assistant_text,
        "control": control,
        "skill": skill,
        "usage": result.usage,
        "events": result.events,
        "stderr": result.stderr,
        "jsonl": result.jsonl,
    }
    (directory / f"{test['id']:02d}.json").write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-path", default="codex", help="Codex executable or command path.")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per case in seconds.")
    parser.add_argument(
        "--system-prompt-file",
        type=Path,
        default=ROOT / "system-prompt.txt",
        help="System prompt file to pass to Codex.",
    )
    parser.add_argument(
        "--system-prompt-filename",
        default="system-prompt.txt",
        help="File name used for the prompt file in Codex's temporary environment.",
    )
    args = parser.parse_args()

    executable = shutil.which(args.codex_path) or args.codex_path
    if not shutil.which(args.codex_path) and not Path(args.codex_path).is_file():
        print(f"Codex executable was not found: {args.codex_path}", file=sys.stderr)
        return 2

    result_directory = ROOT / "results" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result_directory.mkdir(parents=True)
    wrapper = CodexWrapper(
        executable,
        args.timeout,
        system_prompt_file=args.system_prompt_file,
        system_prompt_filename=args.system_prompt_filename,
        skill_sources=(SKILL_SOURCE,),
    )
    rows: list[tuple[dict[str, Any], str, str, str, str]] = []

    for position, test in enumerate(TESTS, start=1):
        print(
            f"Starting Codex request {position}/{len(TESTS)}: {test['name']}",
            flush=True,
        )
        result = wrapper.run(test["prompt"], load_skills=test["mode"] == "--load-skills")
        print(
            f"Received Codex response for test {test['id']} (exit code {result.return_code}).",
            flush=True,
        )
        control, skill = control_values(result.assistant_text)
        expected = test["expected"]
        passed = result.return_code == 0 and control == expected["control"] and skill == expected["skill"]
        status = "pass" if passed else "fail"
        save_result(result_directory, test, result, control, skill)
        rows.append((test, status, control, skill, result.assistant_text))

    summary = terminal_table(rows)
    print(summary)
    (result_directory / "summary.txt").write_text(summary + "\n", encoding="utf-8")
    print(f"\nArtifacts: {result_directory}")
    return 0 if all(status == "pass" for _, status, _, _, _ in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
