@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if exist "..\.venv-silero\Scripts\python.exe" (
  "..\.venv-silero\Scripts\python.exe" -m uvicorn server:app --host 127.0.0.1 --port 7866
) else (
  python -m uvicorn server:app --host 127.0.0.1 --port 7866
)

