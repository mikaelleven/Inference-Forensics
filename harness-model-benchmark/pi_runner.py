#!/usr/bin/env python3
"""Minimal, isolated wrapper around the Pi coding-agent CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PathLike = str | os.PathLike[str]


@dataclass
class PiResult:
    command: list[str]
    return_code: int
    jsonl: str
    stderr: str
    assistant_text: str
    events: list[dict[str, Any]]
    usage: dict[str, Any]
    tool_calls: dict[str, int]
    applied_settings: dict[str, Any] = field(default_factory=dict)
    ignored_settings: dict[str, Any] = field(default_factory=dict)


class PiWrapper:
    """Run one non-interactive Pi coding-agent session in a supplied workspace.

    The wrapper deliberately disables Pi resource discovery (extensions, skills,
    prompt templates, themes, and context files) and creates a temporary Pi
    agent directory. For ChatGPT/Codex, only the existing Pi auth.json is copied.
    For Ollama, an isolated models.json is generated for the selected model.
    """

    def __init__(
        self,
        pi_path: str,
        timeout_seconds: int,
        *,
        provider: str,
        model: str,
        reasoning: str = "off",
        temperature: float | None = None,
        top_p: float | None = None,
        seed: int | None = None,
        context_window: int = 65536,
        max_tokens: int = 8192,
        ollama_base_url: str = "http://localhost:11434/v1",
        supports_reasoning: bool | None = None,
        tools: list[str] | None = None,
        offline_startup: bool = True,
    ) -> None:
        self.pi_path = pi_path
        self.timeout_seconds = timeout_seconds
        self.provider = provider
        self.model = model
        self.reasoning = reasoning
        self.temperature = temperature
        self.top_p = top_p
        self.seed = seed
        self.context_window = context_window
        self.max_tokens = max_tokens
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.supports_reasoning = supports_reasoning
        self.tools = tools
        self.offline_startup = offline_startup

    def run(
        self,
        prompt: str,
        *,
        workdir: PathLike,
        system_prompt: str | None = None,
    ) -> PiResult:
        workspace = Path(workdir).resolve()
        if not workspace.is_dir():
            raise NotADirectoryError(f"Work directory was not found or is not a directory: {workspace}")

        with tempfile.TemporaryDirectory(prefix="pi-run-") as temp_dir:
            temp_root = Path(temp_dir)
            agent_dir = temp_root / "pi-agent"
            agent_dir.mkdir()

            if self.provider != "ollama":
                self._copy_authentication(agent_dir)
            applied, ignored = self._configure_provider(agent_dir)

            environment = os.environ.copy()
            environment["PI_CODING_AGENT_DIR"] = str(agent_dir)

            command = [
                self.pi_path,
                "--mode", "json",
                "--no-session",
                "--no-extensions",
                "--no-skills",
                "--no-prompt-templates",
                "--no-themes",
                "--no-context-files",
                "--no-approve",
            ]
            if self.offline_startup:
                command.append("--offline")

            tool_names = self.tools or default_tools()
            command.extend(("--tools", ",".join(tool_names)))
            command.extend(("--provider", self.provider, "--model", self.model))

            if self.reasoning:
                command.extend(("--thinking", normalize_pi_reasoning(self.reasoning)))
            if system_prompt:
                command.extend(("--system-prompt", system_prompt))

            command.extend(("-p", prompt))

            try:
                completed = subprocess.run(
                    command,
                    cwd=workspace,
                    env=environment,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                raw = text_output(error.stdout)
                events = parse_json_lines(raw)
                return PiResult(
                    command=command,
                    return_code=124,
                    jsonl=raw,
                    stderr=text_output(error.stderr) + f"\nTimed out after {self.timeout_seconds} seconds.",
                    assistant_text=extract_assistant_text(events),
                    events=events,
                    usage=extract_usage(events),
                    tool_calls=extract_tool_calls(events),
                    applied_settings=applied,
                    ignored_settings=ignored,
                )

            events = parse_json_lines(completed.stdout)
            return PiResult(
                command=command,
                return_code=completed.returncode,
                jsonl=completed.stdout,
                stderr=completed.stderr,
                assistant_text=extract_assistant_text(events),
                events=events,
                usage=extract_usage(events),
                tool_calls=extract_tool_calls(events),
                applied_settings=applied,
                ignored_settings=ignored,
            )

    def _configure_provider(self, agent_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        applied: dict[str, Any] = {"reasoning": self.reasoning}
        ignored: dict[str, Any] = {}

        if self.provider != "ollama":
            for key, value in (
                ("temperature", self.temperature),
                ("top_p", self.top_p),
                ("seed", self.seed),
            ):
                if value is not None:
                    ignored[key] = value
            return applied, ignored

        sampling: dict[str, Any] = {}
        if self.temperature is not None:
            sampling["temperature"] = self.temperature
            applied["temperature"] = self.temperature
        if self.top_p is not None:
            sampling["top_p"] = self.top_p
            applied["top_p"] = self.top_p
        if self.seed is not None:
            sampling["seed"] = self.seed
            applied["seed"] = self.seed

        supports_reasoning = True if self.supports_reasoning is None else self.supports_reasoning
        model_entry: dict[str, Any] = {
            "id": self.model,
            "reasoning": supports_reasoning,
            "input": ["text"],
            "contextWindow": self.context_window,
            "maxTokens": self.max_tokens,
        }
        if sampling:
            model_entry["samplingParams"] = sampling
        if supports_reasoning:
            # Ollama's OpenAI-compatible endpoint currently accepts none/low/medium/high/max.
            model_entry["thinkingLevelMap"] = {
                "off": "none",
                "minimal": "low",
                "low": "low",
                "medium": "medium",
                "high": "high",
                "xhigh": "max",
                "max": "max",
            }

        config = {
            "providers": {
                "ollama": {
                    "baseUrl": self.ollama_base_url,
                    "api": "openai-completions",
                    "apiKey": "ollama",
                    "compat": {
                        "supportsDeveloperRole": False,
                        "supportsReasoningEffort": supports_reasoning,
                    },
                    "models": [model_entry],
                }
            }
        }
        (agent_dir / "models.json").write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        applied["ollama_base_url"] = self.ollama_base_url
        applied["context_window"] = self.context_window
        applied["max_tokens"] = self.max_tokens
        applied["supports_reasoning"] = supports_reasoning
        return applied, ignored

    @staticmethod
    def _copy_authentication(agent_dir: Path) -> None:
        source_dir = Path(os.environ.get("PI_CODING_AGENT_DIR", Path.home() / ".pi" / "agent"))
        auth_file = source_dir / "auth.json"
        if auth_file.is_file():
            shutil.copy2(auth_file, agent_dir / "auth.json")


def default_tools() -> list[str]:
    common = ["read", "edit", "write", "grep", "find", "ls"]
    return common + (["powershell"] if os.name == "nt" else ["bash"])


def normalize_pi_reasoning(value: str) -> str:
    value = value.lower().strip()
    aliases = {"none": "off", "on": "medium"}
    value = aliases.get(value, value)
    allowed = {"off", "minimal", "low", "medium", "high", "xhigh", "max"}
    if value not in allowed:
        raise ValueError(f"Unsupported Pi reasoning level: {value}")
    return value


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


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts)


def extract_assistant_text(events: list[dict[str, Any]]) -> str:
    messages: list[str] = []
    for event in events:
        if event.get("type") != "message_end":
            continue
        message = event.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        text = _message_text(message)
        if text:
            messages.append(text)
    return messages[-1].strip() if messages else ""


def extract_usage(events: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "cache_write_tokens": 0,
        "total_tokens": 0,
        "cost": 0.0,
        "turns": 0,
        "usage_available": False,
    }
    for event in events:
        if event.get("type") != "message_end":
            continue
        message = event.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        totals["usage_available"] = True
        totals["turns"] += 1
        totals["input_tokens"] += int(usage.get("input", 0) or 0)
        totals["output_tokens"] += int(usage.get("output", 0) or 0)
        totals["cached_input_tokens"] += int(usage.get("cacheRead", 0) or 0)
        totals["cache_write_tokens"] += int(usage.get("cacheWrite", 0) or 0)
        totals["total_tokens"] += int(usage.get("totalTokens", 0) or 0)
        cost = usage.get("cost")
        if isinstance(cost, dict):
            totals["cost"] += float(cost.get("total", 0.0) or 0.0)
    if totals["total_tokens"] == 0:
        totals["total_tokens"] = totals["input_tokens"] + totals["output_tokens"]
    totals["cost"] = round(float(totals["cost"]), 8)
    return totals


def extract_tool_calls(events: list[dict[str, Any]]) -> dict[str, int]:
    calls: dict[str, int] = {}
    for event in events:
        if event.get("type") != "tool_execution_end":
            continue
        name = event.get("toolName")
        if isinstance(name, str):
            calls[name] = calls.get(name, 0) + 1
    return calls
