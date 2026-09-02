#!/usr/bin/env python3

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_USER_PROMPT = "Execute the task described in the system prompt."


def parse_args():
    parser = argparse.ArgumentParser(
        description="Benchmark an Ollama model using a static system prompt and payload."
    )

    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--thinking",
        default="off",
        choices=["off", "on", "low", "medium", "high", "max"],
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-predict", type=int, default=None)
    parser.add_argument("--keep-alive", default="5m")

    parser.add_argument(
        "--warmup",
        type=int,
        default=1,
        help="Number of warmup runs excluded from statistics (default: 1)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Number of measured benchmark runs (default: 5)",
    )

    parser.add_argument(
        "--output",
        default="benchmark-results.jsonl",
    )
    parser.add_argument(
        "--user-prompt",
        default=DEFAULT_USER_PROMPT,
    )
    parser.add_argument(
        "--show-thinking",
        action="store_true",
    )

    parser.add_argument("prompt_file", type=Path)
    parser.add_argument("payload_file", type=Path)

    args = parser.parse_args()

    if args.warmup < 0:
        parser.error("--warmup must be >= 0")

    if args.runs < 1:
        parser.error("--runs must be >= 1")

    return args


def ollama_url():
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    if not host.startswith(("http://", "https://")):
        host = "http://" + host

    return host.rstrip("/") + "/api/generate"


def parse_thinking(value):
    if value == "off":
        return False
    if value == "on":
        return True
    return value


def read_text(path):
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        print(f"Failed to read {path}: {exc}", file=sys.stderr)
        sys.exit(1)


def seconds(ns):
    return ns / 1_000_000_000 if ns else 0.0


def rate(tokens, ns):
    duration = seconds(ns)
    return tokens / duration if duration else 0.0


def call_ollama(request_data):
    body = json.dumps(request_data).encode("utf-8")

    request = urllib.request.Request(
        ollama_url(),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.perf_counter()

    try:
        with urllib.request.urlopen(request, timeout=3600) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(f"Ollama HTTP error {exc.code}: {error_body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"Could not connect to Ollama: {exc}", file=sys.stderr)
        sys.exit(1)

    wall_time = time.perf_counter() - started

    return data, wall_time


def extract_run(run_number, response, wall_time):
    input_tokens = response.get("prompt_eval_count", 0)
    output_tokens = response.get("eval_count", 0)

    total_duration = response.get("total_duration", 0)
    load_duration = response.get("load_duration", 0)
    prompt_eval_duration = response.get("prompt_eval_duration", 0)
    eval_duration = response.get("eval_duration", 0)

    return {
        "run": run_number,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "wall_time_s": seconds_from_float(wall_time),
        "ollama_total_s": round(seconds(total_duration), 4),
        "load_s": round(seconds(load_duration), 4),
        "prompt_eval_s": round(seconds(prompt_eval_duration), 4),
        "generation_s": round(seconds(eval_duration), 4),
        "prompt_tokens_per_s": round(
            rate(input_tokens, prompt_eval_duration), 2
        ),
        "generation_tokens_per_s": round(
            rate(output_tokens, eval_duration), 2
        ),
        "thinking_text": response.get("thinking", ""),
        "response": response.get("response", ""),
        "done_reason": response.get("done_reason"),
    }


def seconds_from_float(value):
    return round(value, 4)


def aggregate(runs, key):
    values = [run[key] for run in runs]

    return {
        "min": round(min(values), 4),
        "median": round(statistics.median(values), 4),
        "max": round(max(values), 4),
    }


def main():
    args = parse_args()

    system_prompt = read_text(args.prompt_file).rstrip()
    payload = read_text(args.payload_file)

    combined_system_prompt = (
        system_prompt
        + "\n\n"
        + "--- PAYLOAD ---\n"
        + payload
        + "\n--- END PAYLOAD ---"
    )

    options = {
        "temperature": args.temperature,
        "seed": args.seed,
    }

    if args.num_predict is not None:
        options["num_predict"] = args.num_predict

    request_data = {
        "model": args.model,
        "system": combined_system_prompt,
        "prompt": args.user_prompt,
        "think": parse_thinking(args.thinking),
        "stream": False,
        "keep_alive": args.keep_alive,
        "options": options,
    }

    #
    # Warmup
    #

    if args.warmup:
        print(f"Warmup: {args.warmup} run(s)")

    for index in range(args.warmup):
        print(f"  warmup {index + 1}/{args.warmup}")
        call_ollama(request_data)

    #
    # Measured runs
    #

    print(f"Benchmark: {args.runs} run(s)")

    runs = []

    for index in range(args.runs):
        print(f"  run {index + 1}/{args.runs}")

        response, wall_time = call_ollama(request_data)

        runs.append(
            extract_run(
                index + 1,
                response,
                wall_time,
            )
        )

    #
    # Aggregate statistics
    #

    metric_keys = [
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "wall_time_s",
        "ollama_total_s",
        "load_s",
        "prompt_eval_s",
        "generation_s",
        "prompt_tokens_per_s",
        "generation_tokens_per_s",
    ]

    summary = {
        key: aggregate(runs, key)
        for key in metric_keys
    }

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "thinking": args.thinking,
        "prompt_file": str(args.prompt_file),
        "payload_file": str(args.payload_file),
        "settings": {
            "temperature": args.temperature,
            "seed": args.seed,
            "num_predict": args.num_predict,
            "keep_alive": args.keep_alive,
            "warmup": args.warmup,
            "runs": args.runs,
        },
        "summary": summary,
        "runs": runs,
    }

    #
    # Persist
    #

    output_path = Path(args.output)

    with output_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(result, ensure_ascii=False) + "\n")

    #
    # Console summary
    #

    def print_metric(label, key, unit=""):
        metric = summary[key]

        print(
            f"{label:<18}"
            f"{metric['min']:>10} "
            f"{metric['median']:>10} "
            f"{metric['max']:>10} {unit}"
        )

    print()
    print(f"Model    : {args.model}")
    print(f"Thinking : {args.thinking}")
    print(f"Warmup   : {args.warmup}")
    print(f"Runs     : {args.runs}")
    print()

    print(f"{'Metric':<18}{'Min':>10} {'Median':>10} {'Max':>10}")
    print("-" * 52)

    print_metric("Input tokens", "input_tokens")
    print_metric("Output tokens", "output_tokens")
    print_metric("Total tokens", "total_tokens")

    print()
    print_metric("Total time", "ollama_total_s", "s")
    print_metric("Wall clock", "wall_time_s", "s")
    print_metric("Model load", "load_s", "s")
    print_metric("Prompt eval", "prompt_eval_s", "s")
    print_metric("Generation", "generation_s", "s")

    print()
    print_metric("Prompt speed", "prompt_tokens_per_s", "tok/s")
    print_metric("Generation speed", "generation_tokens_per_s", "tok/s")

    #
    # Show last response
    #

    last_run = runs[-1]

    if args.show_thinking and last_run["thinking_text"]:
        print()
        print("=== THINKING (LAST RUN) ===")
        print(last_run["thinking_text"])

    print()
    print("=== RESPONSE (LAST RUN) ===")
    print(last_run["response"])

    print()
    print(f"Result appended to: {output_path}")


if __name__ == "__main__":
    main()
