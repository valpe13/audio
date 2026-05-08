@echo off
setlocal
cd /d "%~dp0\.."
set PYTHONUTF8=1
set COQUI_TOS_AGREED=1
echo Starting XTTS Studio at http://127.0.0.1:7870/studio/
echo Keep this window open while using the browser UI.
start "" "http://127.0.0.1:7870/studio/"
xtts_api\.venv\Scripts\python.exe -m uvicorn xtts_api.studio_server:app --host 127.0.0.1 --port 7870

