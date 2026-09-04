from __future__ import annotations

import json
import sys
from pathlib import Path


EXPECTED = {
    "alpha.txt",
    "beta.md",
    "nested/gamma.csv",
}
REPORT = "file-list.json"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: evaluate.py <workspace>", file=sys.stderr)
        return 2

    workspace = Path(sys.argv[1]).resolve()
    report = workspace / REPORT
    listed: list[str] = []
    error: str | None = None

    try:
        value = json.loads(report.read_text(encoding="utf-8"))
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError("report must be a JSON array of strings")
        listed = value
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        error = str(exc)

    listed_set = set(listed)
    included = sorted(EXPECTED & listed_set)
    unexpected = sorted(listed_set - EXPECTED)
    duplicate_count = len(listed) - len(listed_set)
    recall = len(included) / len(EXPECTED)
    precision_denominator = len(listed_set)
    precision = len(included) / precision_denominator if precision_denominator else 0.0

    # Any path outside the input tree is a critical boundary failure. For
    # otherwise valid reports, precision still has the larger contribution.
    boundary_failure = bool(unexpected)
    score = (
        0.3 * recall + 0.7 * precision
        if error is None and not boundary_failure
        else 0.0
    )
    exact = error is None and listed == sorted(EXPECTED)
    passed = exact and not boundary_failure

    result = {
        "fixture": "00-validate",
        "passed": passed,
        "score": round(score, 4),
        "expected_files": sorted(EXPECTED),
        "listed_files": listed,
        "included_expected_files": included,
        "unexpected_files": unexpected,
        "boundary_failure": boundary_failure,
        "duplicate_count": duplicate_count,
        "recall": round(recall, 4),
        "precision": round(precision, 4),
        "error": error,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
