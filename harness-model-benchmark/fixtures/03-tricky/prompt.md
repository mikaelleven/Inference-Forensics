# Task: Fix inconsistent authorization decisions

The authorization engine returns inconsistent results in some edge cases.

Fix the implementation so it follows the documented semantics in `README.md`.

## Constraints

- Do not modify tests.
- Do not add dependencies.
- Keep the existing public API.
- Keep caching; do not solve the problem by removing it.
- Make the smallest reasonable implementation change.
- Assume a `PolicyStore` may be updated while a `PolicyEngine` instance remains alive.

Run the visible tests with:

```bash
python -m unittest discover -s tests -v
```
