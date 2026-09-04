from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pi_runner import PiWrapper


class PiWrapperTests(unittest.TestCase):
    def test_multiline_system_prompt_is_passed_as_file(self) -> None:
        system_prompt = "first line\n\n- second line\nthird line"

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            observed_prompt_path: Path | None = None

            def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal observed_prompt_path
                prompt_argument_index = command.index("--system-prompt") + 1
                observed_prompt_path = Path(command[prompt_argument_index])
                self.assertTrue(observed_prompt_path.is_file())
                self.assertEqual(observed_prompt_path.read_text(encoding="utf-8"), system_prompt)
                self.assertEqual(kwargs["cwd"], workspace.resolve())
                return subprocess.CompletedProcess(command, 0, '{"type":"session"}\n', "")

            with patch("pi_runner.subprocess.run", side_effect=fake_run):
                result = PiWrapper(
                    "pi",
                    30,
                    provider="ollama",
                    model="qwen3.5:4b",
                ).run("Do the task", workdir=workspace, system_prompt=system_prompt)

            self.assertEqual(result.return_code, 0)
            self.assertIsNotNone(observed_prompt_path)
            self.assertNotEqual(result.command[result.command.index("--system-prompt") + 1], system_prompt)


if __name__ == "__main__":
    unittest.main()
