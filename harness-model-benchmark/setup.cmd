@echo off
setlocal EnableExtensions
where uv >nul 2>nul
if errorlevel 1 (
  echo uv is required; install it explicitly from https://docs.astral.sh/uv/ 1>&2
  exit /b 1
)
uv python install 3.11
if errorlevel 1 exit /b %errorlevel%
uv python pin 3.11
if errorlevel 1 exit /b %errorlevel%
if exist pyproject.toml uv sync
