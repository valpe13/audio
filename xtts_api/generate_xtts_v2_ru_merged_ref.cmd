@echo off
setlocal
set PYTHONUTF8=1
"%~dp0.venv\Scripts\python.exe" "%~dp0generate_xtts_v2_ru_merged_ref.py" %*
endlocal
