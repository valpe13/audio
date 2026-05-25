@echo off
setlocal
cd /d "%~dp0"
if not exist config.json copy config.example.json config.json >nul
if exist "..\.venv-fish\Scripts\python.exe" (
  "..\.venv-fish\Scripts\python.exe" -m uvicorn server:app --host 127.0.0.1 --port 7865
) else (
  python -m uvicorn server:app --host 127.0.0.1 --port 7865
)
