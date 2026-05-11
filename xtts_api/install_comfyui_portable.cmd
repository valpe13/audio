@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

set "PYTHONUTF8=1"

where py >nul 2>nul
if not errorlevel 1 (
  py -3.10 xtts_api\install_comfyui_portable.py %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if not errorlevel 1 (
  python xtts_api\install_comfyui_portable.py %*
  exit /b %ERRORLEVEL%
)

echo ERROR: Python was not found. Install Python 3.10 or run audio_xtts_universal_installer.cmd first.
exit /b 1
