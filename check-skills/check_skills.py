#!/usr/bin/env python3
"""Run the isolated Codex skill-invocation experiment."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SYSTEM_PROMPT = (ROOT / "system-prompt.txt").read_text(encoding="utf-8").strip()
TESTS = json.loads((ROOT / "tests.json").read_text(encoding="utf-8"))
SKILL_SOURCE = ROOT.parent / ".agents" / "skills" / "dummy-skill"


@dataclass
class CodexResult:
    command: list[str]
    return_code: int
    stdout: str
    stderr: str
    assistant_text: str
    usage: list[dict[str, Any]]


class CodexWrapper:
    """Run one minimal, isolated Codex CLI session."""

    def __init__(self, codex_path: str, timeout_seconds: int) -> None:
        self.codex_path = codex_path
        self.timeout_seconds = timeout_seconds

    def run(self, prompt: str, *, load_skills: bool = False) -> CodexResult:
        """Run a prompt with no skills unless load_skills is explicitly true."""
        with tempfile.TemporaryDirectory(prefix="check-skills-") as temp_dir:
            temp_root = Path(temp_dir)
            codex_home = temp_root / "codex-home"
            workdir = temp_root / "workdir"
            codex_home.mkdir()
            workdir.mkdir()
            self._copy_authentication(codex_home)
            instructions_file = self._write_instructions_file(temp_root)

            if load_skills:
                destination = codex_home / "skills" / "dummy-skill"
                destination.parent.mkdir()
                shutil.copytree(SKILL_SOURCE, destination)

            environment = os.environ.copy()
            environment["CODEX_HOME"] = str(codex_home)
            executable_directory = str(Path(self.codex_path).parent)
            if executable_directory not in ("", "."):
                environment["PATH"] = executable_directory + os.pathsep + environment.get("PATH", "")
            # Keep this invocation aligned with the PowerShell harness. In
            # particular, skills are disabled unless this test explicitly
            # requests them with --load-skills.
            include_skills = str(load_skills).lower()
            command = [
                self.codex_path,
                "exec",
                "--ignore-user-config",
                "-m",
                "gpt-5.6-luna",
                "-c",
                "model_reasoning_effort='none'",
                "-c",
                f"model_instructions_file='{instructions_file.as_posix()}'",
                "-c",
                "developer_instructions=''",
                "-c",
                "include_permissions_instructions=false",
                "-c",
                "include_apps_instructions=false",
                "-c",
                "include_collaboration_mode_instructions=false",
                "-c",
                "include_environment_context=false",
                "-c",
                f"skills.include_instructions={include_skills}",
                "--json",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                prompt,
            ]
            try:
                completed = subprocess.run(
                    command,
                    cwd=workdir,
                    env=environment,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                stdout = text_output(error.stdout)
                stderr = text_output(error.stderr) + f"\nTimed out after {self.timeout_seconds} seconds."
                return CodexResult(command, 124, stdout, stderr, "", [])

            events = parse_json_lines(completed.stdout)
            return CodexResult(
                command=command,
                return_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                assistant_text=extract_assistant_text(events),
                usage=extract_usage(events),
            )

    @staticmethod
    def _write_instructions_file(temp_root: Path) -> Path:
        instructions_file = (temp_root / "system-prompt.txt").resolve()
        instructions_file.write_text(SYSTEM_PROMPT + "\n", encoding="utf-8")
        return instructions_file

    @staticmethod
    def _copy_authentication(codex_home: Path) -> None:
        source_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        auth_file = source_home / "auth.json"
        if auth_file.is_file():
            shutil.copy2(auth_file, codex_home / "auth.json")


def text_output(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def parse_json_lines(raw_output: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in raw_output.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def extract_assistant_text(events: list[dict[str, Any]]) -> str:
    messages: list[str] = []
    for event in events:
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "agent_message":
            continue
        text = item.get("text")
        if isinstance(text, str):
            messages.append(text)
            continue
        content = item.get("content")
        if isinstance(content, str):
            messages.append(content)
    return "\n".join(messages).strip()


def extract_usage(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    usages: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            usage = value.get("usage")
            if isinstance(usage, dict):
                usages.append(usage)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(events)
    return usages


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
        "stderr": result.stderr,
        "jsonl": result.stdout,
    }
    (directory / f"{test['id']:02d}.json").write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-path", default="codex", help="Codex executable or command path.")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per case in seconds.")
    args = parser.parse_args()

    executable = shutil.which(args.codex_path) or args.codex_path
    if not shutil.which(args.codex_path) and not Path(args.codex_path).is_file():
        print(f"Codex executable was not found: {args.codex_path}", file=sys.stderr)
        return 2

    result_directory = ROOT / "results" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result_directory.mkdir(parents=True)
    wrapper = CodexWrapper(executable, args.timeout)
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
