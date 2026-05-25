@echo off
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"
for %%I in ("%PROJECT_ROOT%\..") do set "PROJECT_PARENT=%%~fI"
if /I "%PROJECT_ROOT%"=="%PROJECT_PARENT%\audio" if exist "%PROJECT_PARENT%\xtts_api\studio_server.py" (
  echo [ERROR] This launcher is inside a nested duplicate checkout:
  echo         "%PROJECT_ROOT%"
  echo Use the workspace-root launcher instead:
  echo         "%PROJECT_PARENT%\xtts_api\run_xtts_studio.cmd"
  echo This prevents launching the stale nested XTTS Studio copy.
  pause
  exit /b 1
)
cd /d "%PROJECT_ROOT%"

set "PYTHONUTF8=1"
set "COQUI_TOS_AGREED=1"
set "HOST=127.0.0.1"
set "PORT=7870"
set "STUDIO_URL=http://%HOST%:%PORT%/studio/"
set "API_DIR=%PROJECT_ROOT%\xtts_api"
set "SERVER_FILE=%API_DIR%\studio_server.py"
set "PYTHON_EXE=%API_DIR%\.venv\Scripts\python.exe"

echo Starting XTTS Studio at %STUDIO_URL%
echo Workspace: %CD%
echo Server file: %SERVER_FILE%
echo Keep this window open while using the browser UI.

if not exist "%SERVER_FILE%" (
  echo [ERROR] Cannot find "%SERVER_FILE%".
  echo This launcher must be run from the current project checkout, not an old copied folder.
  pause
  exit /b 1
)

if not exist "%PYTHON_EXE%" (
  echo [ERROR] Cannot find "%PYTHON_EXE%".
  echo Run xtts_api\run_xtts_studio_full.cmd --check to create or repair the virtual environment.
  pause
  exit /b 1
)

set "FOUND_LISTENER=0"
for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":%PORT% .*LISTENING"') do (
  set "FOUND_LISTENER=1"
  echo [ERROR] Port %HOST%:%PORT% is already in use by PID %%P.
)
if "%FOUND_LISTENER%"=="1" (
  echo Close the existing XTTS Studio window, or identify it with:
  echo   netstat -ano ^| findstr :%PORT%
  echo   tasklist /FI "PID eq ^<PID^>"
  echo Stop it manually only if appropriate:
  echo   taskkill /PID ^<PID^> /F
  pause
  exit /b 1
)

start "" "%STUDIO_URL%"
"%PYTHON_EXE%" -m uvicorn xtts_api.studio_server:app --host %HOST% --port %PORT%

