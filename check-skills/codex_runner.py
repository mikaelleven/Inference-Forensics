#!/usr/bin/env python3
"""Reusable helpers for running isolated Codex CLI requests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PathLike = str | os.PathLike[str]


@dataclass
class CodexResult:
    """The raw and commonly used parts of one Codex JSONL response."""

    command: list[str]
    return_code: int
    jsonl: str
    stderr: str
    assistant_text: str
    events: list[dict[str, Any]]
    usage: list[dict[str, Any]]

    @property
    def stdout(self) -> str:
        """Backward-compatible alias for the raw JSONL response."""
        return self.jsonl


class CodexWrapper:
    """Run isolated, non-interactive Codex CLI sessions.

    ``system_prompt`` and ``system_prompt_file`` are alternatives. A prompt
    file is copied into the temporary Codex environment before invocation,
    which means callers can use a custom source file without exposing its
    original path to Codex. ``system_prompt_filename`` controls the name of
    that copied file.

    Each path in ``skill_sources`` must point to one skill directory. Those
    directories are copied into the temporary ``CODEX_HOME`` only when
    ``load_skills`` is true. A profile config can be supplied with
    ``profile_config_file``; it is copied as ``<name>.config.toml`` and loaded
    with ``--profile <name>`` for each isolated process.
    """

    def __init__(
        self,
        codex_path: str,
        timeout_seconds: int,
        *,
        model: str = "gpt-5.6-luna",
        reasoning_effort: str = "none",
        system_prompt: str | None = None,
        system_prompt_file: PathLike | None = None,
        system_prompt_filename: str = "system-prompt.txt",
        skill_sources: Iterable[PathLike] = (),
        profile_config_file: PathLike | None = None,
    ) -> None:
        if system_prompt is not None and system_prompt_file is not None:
            raise ValueError("Pass either system_prompt or system_prompt_file, not both.")

        filename = Path(system_prompt_filename).name
        if not filename or filename in (".", ".."):
            raise ValueError("system_prompt_filename must be a file name.")

        self.codex_path = codex_path
        self.timeout_seconds = timeout_seconds
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.system_prompt = system_prompt
        self.system_prompt_file = Path(system_prompt_file) if system_prompt_file else None
        self.system_prompt_filename = filename
        self.skill_sources = tuple(Path(source) for source in skill_sources)
        self.profile_config_file = Path(profile_config_file) if profile_config_file else None
        if self.profile_config_file is not None and not self.profile_config_file.name.endswith(
            ".config.toml"
        ):
            raise ValueError("profile_config_file must use the <name>.config.toml format.")

    def run(
        self,
        prompt: str,
        *,
        load_skills: bool = False,
        system_prompt: str | None = None,
        system_prompt_file: PathLike | None = None,
        system_prompt_filename: str | None = None,
    ) -> CodexResult:
        """Run one prompt and return its raw JSONL and extracted data.

        A system prompt supplied to this method overrides the default prompt
        configured on the wrapper. ``system_prompt_file`` is an alternative
        to prompt text and may be used for a per-request custom prompt.
        """
        if system_prompt is not None and system_prompt_file is not None:
            raise ValueError("Pass either system_prompt or system_prompt_file, not both.")

        if system_prompt is not None:
            prompt_text = system_prompt
            prompt_file = None
        elif system_prompt_file is not None:
            prompt_text = None
            prompt_file = Path(system_prompt_file)
        else:
            prompt_text = self.system_prompt
            prompt_file = self.system_prompt_file

        prompt_filename = system_prompt_filename or self.system_prompt_filename
        prompt_filename = Path(prompt_filename).name
        if not prompt_filename or prompt_filename in (".", ".."):
            raise ValueError("system_prompt_filename must be a file name.")

        with tempfile.TemporaryDirectory(prefix="codex-run-") as temp_dir:
            temp_root = Path(temp_dir)
            codex_home = temp_root / "codex-home"
            workdir = temp_root / "workdir"
            codex_home.mkdir()
            workdir.mkdir()
            self._copy_authentication(codex_home)
            profile_name = self._copy_profile(codex_home)
            instructions_file = self._write_instructions_file(
                temp_root,
                prompt_text=prompt_text,
                prompt_file=prompt_file,
                filename=prompt_filename,
            )

            if load_skills:
                self._copy_skills(codex_home)

            environment = os.environ.copy()
            environment["CODEX_HOME"] = str(codex_home)
            executable_directory = str(Path(self.codex_path).parent)
            if executable_directory not in ("", "."):
                environment["PATH"] = executable_directory + os.pathsep + environment.get("PATH", "")

            include_skills = str(load_skills).lower()
            command = [
                self.codex_path,
                "exec",
                "--ignore-user-config",
            ]
            if profile_name is not None:
                command.extend(("--profile", profile_name))
            command.extend([
                "-m",
                self.model,
                "-c",
                f"model_reasoning_effort='{self.reasoning_effort}'",
                "-c",
                f"model_instructions_file='{instructions_file.as_posix()}'",
                "-c",
                "developer_instructions=''",
                "-c",
                "web_search='disabled'",
                "-c",
                "project_doc_max_bytes=0",
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
            ])
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
                jsonl = text_output(error.stdout)
                stderr = text_output(error.stderr) + f"\nTimed out after {self.timeout_seconds} seconds."
                return CodexResult(command, 124, jsonl, stderr, "", [], [])

            events = parse_json_lines(completed.stdout)
            return CodexResult(
                command=command,
                return_code=completed.returncode,
                jsonl=completed.stdout,
                stderr=completed.stderr,
                assistant_text=extract_assistant_text(events),
                events=events,
                usage=extract_usage(events),
            )

    def _copy_profile(self, codex_home: Path) -> str | None:
        if self.profile_config_file is None:
            return None
        if not self.profile_config_file.is_file():
            raise FileNotFoundError(f"Profile config was not found: {self.profile_config_file}")
        profile_filename = self.profile_config_file.name
        shutil.copy2(self.profile_config_file, codex_home / profile_filename)
        return profile_filename.removesuffix(".config.toml")

    def _copy_skills(self, codex_home: Path) -> None:
        skills_directory = codex_home / "skills"
        skills_directory.mkdir()
        for source in self.skill_sources:
            destination = skills_directory / source.name
            shutil.copytree(source, destination)

    def _write_instructions_file(
        self,
        temp_root: Path,
        *,
        prompt_text: str | None,
        prompt_file: Path | None,
        filename: str,
    ) -> Path:
        instructions_file = (temp_root / filename).resolve()
        if prompt_file is not None:
            contents = prompt_file.read_text(encoding="utf-8")
        else:
            contents = prompt_text or ""
        instructions_file.write_text(contents.rstrip() + "\n", encoding="utf-8")
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
    """Parse valid JSON objects from a Codex JSONL response."""
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
    """Return every usage object found in the parsed JSONL events."""
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
