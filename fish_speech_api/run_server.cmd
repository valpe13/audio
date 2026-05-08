@echo off
setlocal
cd /d "%~dp0"
if not exist config.json copy config.example.json config.json >nul
python -m uvicorn server:app --host 127.0.0.1 --port 7865

