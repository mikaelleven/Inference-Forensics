#!/usr/bin/env python3
"""Run ollama-bench.py for several models and print a combined summary.

The configuration file is TOML, for example:

    runs = 3
    warmup = 1
    max_thinking = "off"
    temperature = 0
    prompt_file = "sample-data/prompt.md"
    payload_file = "sample-data/payload.txt"
    output_dir = "data"
    name = "local-models"

    # Compact form when no per-model overrides are needed:
    # models = ["qwen3.5:4b", "qwen2.5:7b"]

    [[models]]
    model = "qwen3.5:4b"

    [[models]]
    model = "qwen2.5:7b"
    max_thinking = "on"

Paths in the configuration are relative to the configuration file's directory.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


THINKING_VALUES = {"off", "on", "max"}
ExpectedType = type | tuple[type, ...]
BENCHMARK_SCRIPT = Path(__file__).resolve().with_name("ollama-bench.py")


class ConfigurationError(ValueError):
    """Raised when a benchmark configuration is invalid."""


@dataclass(frozen=True)
class ModelConfig:
    name: str
    thinking: str


@dataclass(frozen=True)
class BenchmarkConfig:
    path: Path
    name: str
    runs: int
    warmup: int
    thinking: str
    temperature: float
    prompt_file: Path
    payload_file: Path
    output_dir: Path
    models: tuple[ModelConfig, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run ollama-bench.py for every model in a TOML benchmark "
            "configuration and print a combined summary."
        )
    )
    _ = parser.add_argument(
        "config",
        type=Path,
        help="Benchmark TOML file, or a directory containing one TOML file.",
    )
    return parser.parse_args()


def resolve_config_path(argument: Path) -> tuple[Path, bool]:
    """Return the config path and whether the user supplied a directory."""
    path = argument.expanduser().resolve()

    if path.is_dir():
        candidates = sorted(
            candidate
            for candidate in path.iterdir()
            if candidate.is_file() and candidate.suffix.lower() == ".toml"
        )

        if not candidates:
            raise ConfigurationError(f"No TOML configuration file found in {path}")
        if len(candidates) > 1:
            names = ", ".join(candidate.name for candidate in candidates)
            raise ConfigurationError(
                f"Directory {path} contains multiple TOML files ({names}); pass "
                + "the configuration filename instead"
            )
        return candidates[0], True

    if not path.exists():
        raise ConfigurationError(f"Configuration path does not exist: {path}")
    if not path.is_file():
        raise ConfigurationError(f"Configuration path is not a file: {path}")
    if path.suffix.lower() != ".toml":
        raise ConfigurationError("The benchmark configuration must be a TOML file")

    return path, False


def read_config_value(
    table: Mapping[str, Any],
    key: str,
    expected_type: ExpectedType,
    *,
    default: Any = None,
    required: bool = False,
) -> Any:
    if key not in table:
        if required:
            raise ConfigurationError(f"Missing required configuration value: {key}")
        return default

    value = table[key]
    if isinstance(value, bool) or not isinstance(value, expected_type):
        raise ConfigurationError(
            f"Configuration value {key!r} has an invalid type (expected "
            + f"{_type_name(expected_type)})"
        )
    return value


def _type_name(expected_type: ExpectedType) -> str:
    if isinstance(expected_type, tuple):
        return " or ".join(item.__name__ for item in expected_type)
    return expected_type.__name__


def read_non_empty_string(
    table: Mapping[str, Any], key: str, *, default: str | None = None
) -> str:
    value = read_config_value(
        table, key, str, default=default, required=default is None
    )
    if not value.strip():
        raise ConfigurationError(f"Configuration value {key!r} must not be empty")
    return value.strip()


def read_thinking(table: Mapping[str, Any], key: str, default: str) -> str:
    value = read_non_empty_string(table, key, default=default).lower()
    if value not in THINKING_VALUES:
        choices = ", ".join(sorted(THINKING_VALUES))
        raise ConfigurationError(
            f"Configuration value {key!r} must be one of: {choices}"
        )
    return value


def resolve_relative_path(value: str, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base_dir / path).resolve()


def validate_output_name(name: str) -> str:
    if not name:
        raise ConfigurationError("Benchmark name must not be empty")

    invalid_characters = '<>:"/\\|?*'
    if any(character in invalid_characters or ord(character) < 32 for character in name):
        raise ConfigurationError(
            "Benchmark name contains characters that are invalid in a filename"
        )
    if name in {".", ".."} or name != name.rstrip(" ."):
        raise ConfigurationError(
            "Benchmark name must not end with a space or period"
        )
    return name


def load_config(argument: Path) -> BenchmarkConfig:
    config_path, supplied_directory = resolve_config_path(argument)

    try:
        with config_path.open("rb") as file:
            raw_config = tomllib.load(file)
    except OSError as exc:
        raise ConfigurationError(f"Failed to read {config_path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(f"Invalid TOML in {config_path}: {exc}") from exc

    if not isinstance(raw_config, dict):
        raise ConfigurationError("The configuration root must be a TOML table")

    runs = read_config_value(raw_config, "runs", int, default=3)
    warmup = read_config_value(raw_config, "warmup", int, default=1)
    temperature = read_config_value(raw_config, "temperature", (int, float), default=0)
    if runs < 1:
        raise ConfigurationError("Configuration value 'runs' must be >= 1")
    if warmup < 0:
        raise ConfigurationError("Configuration value 'warmup' must be >= 0")
    if temperature < 0 or not math.isfinite(float(temperature)):
        raise ConfigurationError(
            "Configuration value 'temperature' must be a finite number >= 0"
        )

    thinking = read_thinking(raw_config, "max_thinking", "off")
    prompt_value = read_non_empty_string(raw_config, "prompt_file")
    payload_value = read_non_empty_string(raw_config, "payload_file")
    prompt_file = resolve_relative_path(prompt_value, config_path.parent)
    payload_file = resolve_relative_path(payload_value, config_path.parent)

    if not prompt_file.is_file():
        raise ConfigurationError(f"Prompt file does not exist: {prompt_file}")
    if not payload_file.is_file():
        raise ConfigurationError(f"Payload file does not exist: {payload_file}")

    configured_output = raw_config.get("output_dir")
    if configured_output is None:
        output_dir = config_path.parent
    else:
        if not isinstance(configured_output, str) or not configured_output.strip():
            raise ConfigurationError(
                "Configuration value 'output_dir' must be a non-empty string"
            )
        output_dir = resolve_relative_path(configured_output, config_path.parent)

    configured_name = raw_config.get("name")
    if configured_name is not None:
        if not isinstance(configured_name, str) or not configured_name.strip():
            raise ConfigurationError(
                "Configuration value 'name' must be a non-empty string"
            )
        name = configured_name.strip()
    elif supplied_directory:
        name = config_path.parent.name
    else:
        name = config_path.stem
    name = validate_output_name(name)

    raw_models = raw_config.get("models")
    if not isinstance(raw_models, list) or not raw_models:
        raise ConfigurationError(
            "Configuration value 'models' must be a non-empty array of strings "
            "or tables"
        )

    models: list[ModelConfig] = []
    for index, raw_model in enumerate(raw_models, start=1):
        if isinstance(raw_model, str):
            model_value = raw_model
            model_thinking = thinking
        elif isinstance(raw_model, dict):
            model_value = raw_model.get("model", raw_model.get("name"))
            model_thinking = read_thinking(raw_model, "max_thinking", thinking)
        else:
            raise ConfigurationError(
                f"Model entry {index} must be a string or TOML table"
            )

        if not isinstance(model_value, str) or not model_value.strip():
            raise ConfigurationError(
                f"Model entry {index} requires a non-empty model name"
            )

        models.append(
            ModelConfig(name=model_value.strip(), thinking=model_thinking)
        )

    return BenchmarkConfig(
        path=config_path,
        name=name,
        runs=runs,
        warmup=warmup,
        thinking=thinking,
        temperature=float(temperature),
        prompt_file=prompt_file,
        payload_file=payload_file,
        output_dir=output_dir,
        models=tuple(models),
    )


def format_temperature(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def make_output_path(config: BenchmarkConfig) -> Path:
    try:
        config.output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigurationError(
            f"Failed to create output directory {config.output_dir}: {exc}"
        ) from exc

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    output_path = config.output_dir / f"{timestamp}_{config.name}_results.jsonl"

    if output_path.exists():
        raise ConfigurationError(
            f"Results file already exists (timestamp collision): {output_path}"
        )
    return output_path


def run_model(config: BenchmarkConfig, model: ModelConfig, output_path: Path) -> None:
    command = [
        sys.executable,
        str(BENCHMARK_SCRIPT),
        "--model",
        model.name,
        "--thinking",
        model.thinking,
        "--temperature",
        format_temperature(config.temperature),
        "--warmup",
        str(config.warmup),
        "--runs",
        str(config.runs),
        "--output",
        str(output_path),
        str(config.prompt_file),
        str(config.payload_file),
    ]

    completed = subprocess.run(command, check=False)
    if completed.returncode:
        raise RuntimeError(
            f"Benchmark failed for model {model.name!r} (exit code "
            + f"{completed.returncode})"
        )


def format_number(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise RuntimeError(f"Expected a numeric benchmark value, got {value!r}")
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def read_results(output_path: Path) -> list[Mapping[str, Any]]:
    results: list[Mapping[str, Any]] = []
    try:
        with output_path.open(encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                result = json.loads(line)
                if not isinstance(result, dict):
                    raise RuntimeError(
                        f"Result line {line_number} is not a JSON object"
                    )
                results.append(result)
    except OSError as exc:
        raise RuntimeError(f"Failed to read results file {output_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON in results file {output_path}: {exc}"
        ) from exc

    if not results:
        raise RuntimeError(f"Results file is empty: {output_path}")
    return results


def result_median(result: Mapping[str, Any], metric: str) -> Any:
    try:
        return result["summary"][metric]["median"]
    except (KeyError, TypeError):
        raise RuntimeError(
            f"Result for model {result.get('model', '<unknown>')!r} does not "
            + f"contain summary metric {metric!r}"
        ) from None


def format_summary(results: list[Mapping[str, Any]]) -> str:
    headers = [
        "model",
        "thinking",
        "Input",
        "Output",
        "Total",
        "Time (s)",
        "Prompt (tok/s)",
        "Generation (tok/s)",
    ]
    rows: list[list[str]] = []
    for result in results:
        model = result.get("model")
        thinking = result.get("thinking")
        if not isinstance(model, str) or not isinstance(thinking, str):
            raise RuntimeError("Each result must contain model and thinking strings")
        rows.append(
            [
                model,
                thinking,
                format_number(result_median(result, "input_tokens")),
                format_number(result_median(result, "output_tokens")),
                format_number(result_median(result, "total_tokens")),
                format_number(result_median(result, "ollama_total_s")),
                format_number(result_median(result, "prompt_tokens_per_s")),
                format_number(result_median(result, "generation_tokens_per_s")),
            ]
        )

    widths = [
        max(len(header), *(len(row[index]) for row in rows))
        for index, header in enumerate(headers)
    ]

    def render(row: list[str], *, header: bool = False) -> str:
        cells = []
        for index, value in enumerate(row):
            align_left = header or index < 2
            cells.append(
                value.ljust(widths[index])
                if align_left
                else value.rjust(widths[index])
            )
        return "  ".join(cells).rstrip()

    return "\n".join(
        [render(headers, header=True), render(["-" * width for width in widths])]
        + [render(row) for row in rows]
    )


def main() -> int:
    args = parse_args()

    try:
        config = load_config(args.config)
        if not BENCHMARK_SCRIPT.is_file():
            raise RuntimeError(f"Benchmark script not found: {BENCHMARK_SCRIPT}")
        output_path = make_output_path(config)

        print(f"Benchmark: {config.name}")
        print(f"Results: {output_path}")
        print()

        for index, model in enumerate(config.models, start=1):
            print(
                f"[{index}/{len(config.models)}] Running {model.name} "
                + f"(thinking: {model.thinking})"
            )
            run_model(config, model, output_path)

        results = read_results(output_path)
        print()
        print(format_summary(results))
        return 0
    except (ConfigurationError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
