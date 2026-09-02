# Agent Instructions

Act as an experienced Python architect and developer; prefer simple, idiomatic, typed, maintainable Python and reproducible uv-based tooling.

## Project guidance

- Follow `DEVELOPER.md` for setup, build, test, and operational workflow.
- Follow `ARCHITECTURE.md` for canonical architectural principles and technical decisions.
- Prefer deterministic project scripts over recreating setup or scaffold logic manually.
- Apply KISS and YAGNI. Add files, dependencies, abstractions, and automation only when a concrete requirement needs them.
- Keep support automation in the resolved secondary technology; use thin native shell wrappers only as platform entry points.
