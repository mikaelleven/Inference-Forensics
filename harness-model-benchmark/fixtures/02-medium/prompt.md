# Task: Fix the job queue

The job queue violates several documented scheduling guarantees.

Fix the implementation so it follows `README.md`.

Constraints:
- Do not modify tests.
- Keep the existing public API.
- Do not add dependencies.
- Preserve the in-memory design; do not replace the queue with a different subsystem.
- Make focused changes rather than rewriting the package.

Run the visible tests with:

```bash
python -m unittest discover -s tests -v
```
