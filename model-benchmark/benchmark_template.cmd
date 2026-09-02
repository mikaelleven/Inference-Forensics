@echo off
setlocal EnableExtensions

if "%~1"=="" (
    echo Usage: %~nx0 NAME [OUTPUT_DIR]
    exit /b 1
)

set "NAME=%~1"
if "%~2"=="" (
    set "OUTPUT_DIR=%~dp0data"
) else (
    set "OUTPUT_DIR=%~2"
)

rem Resolve relative output directories to an absolute path.
for %%I in ("%OUTPUT_DIR%") do set "OUTPUT_DIR=%%~fI"

for /f "delims=" %%I in ('powershell -NoProfile -Command "(Get-Date).ToString('yyyy-MM-dd_HH-mm-ss')"') do set "TIMESTAMP=%%I"
if not defined TIMESTAMP (
    echo Failed to generate timestamp.
    exit /b 1
)

set "RESULTS=%OUTPUT_DIR%\%NAME%\%TIMESTAMP%_%NAME%_results.jsonl"
if not exist "%OUTPUT_DIR%\%NAME%" mkdir "%OUTPUT_DIR%\%NAME%"

py "%~dp0ollama-bench.py" --model=phi4-mini:latest --warmup=0 --runs=1 --output="%RESULTS%" "%~dp0sample-data\prompt.md" "%~dp0sample-data\payload.txt"
if errorlevel 1 exit /b %errorlevel%

powershell -NoProfile -Command "Get-Content -LiteralPath $env:RESULTS | ForEach-Object { $_ | ConvertFrom-Json } | Select-Object model, thinking, @{N='Input'; E={$_.summary.input_tokens.median}}, @{N='Output'; E={$_.summary.output_tokens.median}}, @{N='Time (s)'; E={$_.summary.ollama_total_s.median}}, @{N='Prompt (tok/s)'; E={$_.summary.prompt_tokens_per_s.median}}, @{N='Generation (tok/s)'; E={$_.summary.generation_tokens_per_s.median}} | Format-Table -AutoSize"

endlocal
