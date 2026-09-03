#!/bin/sh
set -eu
if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required; install it explicitly from https://docs.astral.sh/uv/" >&2
  exit 1
fi
uv python install 3.11
uv python pin 3.11
[ ! -f pyproject.toml ] || uv sync
