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
            self._write_config(codex_home)

            if load_skills:
                destination = codex_home / "skills" / "dummy-skill"
                destination.parent.mkdir()
                shutil.copytree(SKILL_SOURCE, destination)

            environment = os.environ.copy()
            environment["CODEX_HOME"] = str(codex_home)
            command = [
                self.codex_path,
                "exec",
                "--json",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--ask-for-approval",
                "never",
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
    def _write_config(codex_home: Path) -> None:
        escaped_prompt = SYSTEM_PROMPT.replace('"""', '\\\"\\\"\\\"')
        (codex_home / "config.toml").write_text(
            f'developer_instructions = """{escaped_prompt}"""\n', encoding="utf-8"
        )

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


def markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


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
    rows: list[tuple[dict[str, Any], str, str, str]] = []

    for test in TESTS:
        result = wrapper.run(test["prompt"], load_skills=test["mode"] == "--load-skills")
        control, skill = control_values(result.assistant_text)
        expected = test["expected"]
        passed = result.return_code == 0 and control == expected["control"] and skill == expected["skill"]
        status = "pass" if passed else "fail"
        save_result(result_directory, test, result, control, skill)
        rows.append((test, status, control, skill))

    lines = [
        "| # | Name | Status | Control: | Skill: |",
        "| -: | --- | --- | --- | --- |",
    ]
    for test, status, control, skill in rows:
        lines.append(
            f"| {test['id']} | {markdown_cell(test['name'])} | {status} | "
            f"{markdown_cell(control)} | {markdown_cell(skill)} |"
        )
    summary = "\n".join(lines)
    print(summary)
    (result_directory / "summary.md").write_text(summary + "\n", encoding="utf-8")
    print(f"\nArtifacts: {result_directory}")
    return 0 if all(status == "pass" for _, status, _, _ in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
