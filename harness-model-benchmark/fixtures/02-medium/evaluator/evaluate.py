from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_suite(module) -> tuple[unittest.TestResult, str]:
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    return result, stream.getvalue()


def passed_count(result: unittest.TestResult) -> int:
    failed = len(result.failures) + len(result.errors) + len(result.unexpectedSuccesses)
    return result.testsRun - failed


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: evaluate.py <workspace>", file=sys.stderr)
        return 2

    workspace = Path(sys.argv[1]).resolve()
    evaluator_dir = Path(__file__).resolve().parent
    fixture_root = evaluator_dir.parent
    pristine = fixture_root / "input"
    sys.path.insert(0, str(workspace))

    visible_module = load_module("fixture_visible_tests", workspace / 'tests/test_job_queue.py')
    hidden_module = load_module("fixture_hidden_tests", evaluator_dir / "hidden_tests.py")
    visible_result, visible_output = run_suite(visible_module)
    hidden_result, hidden_output = run_suite(hidden_module)

    protected_relpaths = ['README.md', 'tests/test_job_queue.py', 'job_queue/models.py', 'job_queue/__init__.py']
    changed_protected = []
    for relative_str in protected_relpaths:
        relative = Path(relative_str)
        candidate = workspace / relative
        original = pristine / relative
        if not candidate.exists() or not original.exists() or sha256(candidate) != sha256(original):
            changed_protected.append(str(relative))

    protected_unchanged = not changed_protected
    total_tests = visible_result.testsRun + hidden_result.testsRun
    tests_passed = passed_count(visible_result) + passed_count(hidden_result)
    test_score = tests_passed / total_tests if total_tests else 0.0
    score = test_score if protected_unchanged else 0.0
    passed = visible_result.wasSuccessful() and hidden_result.wasSuccessful() and protected_unchanged

    result = {
        "fixture": '02-medium',
        "passed": passed,
        "score": round(score, 4),
        "tests_passed": tests_passed,
        "tests_total": total_tests,
        "visible": {"passed": passed_count(visible_result), "total": visible_result.testsRun, "ok": visible_result.wasSuccessful()},
        "hidden": {"passed": passed_count(hidden_result), "total": hidden_result.testsRun, "ok": hidden_result.wasSuccessful()},
        "protected_files_unchanged": protected_unchanged,
        "changed_protected_files": changed_protected,
        "visible_output": visible_output,
        "hidden_output": hidden_output,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
