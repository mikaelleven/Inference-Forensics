@echo off
setlocal

set SCRIPT=%~dp0ollama-bench.py
set PROMPT=%~dp0sample-data\prompt.md
set PAYLOAD=%~dp0sample-data\payload.txt
set RESULTS=%~dp0data\benchmark-results.jsonl

py "%SCRIPT%" --model=phi4-mini:latest --warmup=0 --runs=1 --output="%RESULTS%" "%PROMPT%" "%PAYLOAD%"

endlocal
