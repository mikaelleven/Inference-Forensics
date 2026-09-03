# Architecture

## Overview

Small, deterministic benchmark harness for comparing coding models and coding-agent harnesses..

## System boundaries

Define system boundaries as implementation evolves. Keep external dependencies explicit.

## Design principles

- Prefer the simplest solution that satisfies current requirements.
- Apply YAGNI; do not add infrastructure without a concrete need.
- Keep concerns separated and dependencies explicit.
- Prefer deterministic and reproducible automation.
- Keep platform-specific behavior explicit.

## Technology decisions

- Primary technology: Python
- Primary language: python
- Secondary/support technology: Python
- Secondary language: python
- Framework: none selected
- Target platform(s): cross-platform

## Constraints and assumptions

Preserve deterministic fixture isolation and external Python evaluators.

## Deployment architecture

repository

Environment setup and routine commands belong in `DEVELOPER.md`.
