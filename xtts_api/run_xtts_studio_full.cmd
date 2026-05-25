@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Robust Windows launcher for XTTS Studio.
rem Usage:
rem   run_xtts_studio_full.cmd          Install/check deps, verify port 7870 is free, start server.
rem   run_xtts_studio_full.cmd --check  Validate environment and dependency state without starting server.

chcp 65001 >nul
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"
for %%I in ("%PROJECT_ROOT%\..") do set "PROJECT_PARENT=%%~fI"
if /I "%PROJECT_ROOT%"=="%PROJECT_PARENT%\audio" if exist "%PROJECT_PARENT%\xtts_api\studio_server.py" (
    echo [ERROR] This launcher is inside a nested duplicate checkout:
    echo         "%PROJECT_ROOT%"
    echo Use the workspace-root launcher instead:
    echo         "%PROJECT_PARENT%\xtts_api\run_xtts_studio_full.cmd"
    echo This prevents launching the stale nested XTTS Studio copy.
    exit /b 1
)
cd /d "%PROJECT_ROOT%"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "COQUI_TOS_AGREED=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cu121"

set "PORT=7870"
set "HOST=127.0.0.1"
set "STUDIO_URL=http://%HOST%:%PORT%/studio/"
set "HEALTH_URL=http://%HOST%:%PORT%/api/health"
set "API_DIR=%PROJECT_ROOT%\xtts_api"
set "VENV_DIR=%API_DIR%\.venv"
set "REQ_FILE=%API_DIR%\requirements.txt"
set "STAMP_FILE=%VENV_DIR%\.requirements.sha256"
set "CHECK_ONLY=0"

if /I "%~1"=="--check" set "CHECK_ONLY=1"
if /I "%~1"=="/check" set "CHECK_ONLY=1"

echo ============================================================
echo XTTS Studio full launcher
echo Workspace: %CD%
echo API dir:   %API_DIR%
echo Venv:      %VENV_DIR%
echo URL:       %STUDIO_URL%
echo ============================================================
echo.

if not exist "%API_DIR%\studio_server.py" (
    echo [ERROR] Cannot find "%API_DIR%\studio_server.py".
    echo Run this launcher from the project checkout or keep it in xtts_api.
    goto :fail
)

if not exist "%REQ_FILE%" (
    echo [ERROR] Cannot find "%REQ_FILE%".
    echo Dependency installation cannot continue without requirements.txt.
    goto :fail
)

call :ensure_python_and_venv || goto :fail
call :ensure_packaging_tools || goto :fail
call :ensure_requirements || goto :fail

echo.
echo [OK] Environment is ready.
"%PYTHON_EXE%" --version

if "%CHECK_ONLY%"=="1" (
    echo.
    echo [OK] Check-only mode completed. Server was not started and port %PORT% was not modified.
    goto :done
)

call :check_port_available || goto :fail
call :start_server || goto :fail
call :health_check

echo.
echo [OK] XTTS Studio launch sequence completed.
echo Open: %STUDIO_URL%
goto :done


:ensure_python_and_venv
echo [1/5] Detecting Python / virtual environment...

if exist "%VENV_DIR%\Scripts\python.exe" (
    set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
    echo Found existing venv Python: "!PYTHON_EXE!"
    "!PYTHON_EXE!" -c "import sys; raise SystemExit(0 if (sys.version_info >= (3, 10) and sys.version_info < (3, 12)) else 1)" >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Existing venv uses an unsupported Python version for TTS 0.22.0.
        "!PYTHON_EXE!" --version
        echo Delete "%VENV_DIR%" and rerun with Python 3.10 or 3.11 available.
        exit /b 1
    )
    exit /b 0
)

echo No XTTS venv found. Searching for Python 3.11/3.10...
set "BASE_PY="

py -3.11 -c "import sys; raise SystemExit(0 if (sys.version_info >= (3, 10) and sys.version_info < (3, 12)) else 1)" >nul 2>nul
if not errorlevel 1 set "BASE_PY=py -3.11"

if not defined BASE_PY (
    py -3.10 -c "import sys; raise SystemExit(0 if (sys.version_info >= (3, 10) and sys.version_info < (3, 12)) else 1)" >nul 2>nul
    if not errorlevel 1 set "BASE_PY=py -3.10"
)

if not defined BASE_PY (
    python -c "import sys; raise SystemExit(0 if (sys.version_info >= (3, 10) and sys.version_info < (3, 12)) else 1)" >nul 2>nul
    if not errorlevel 1 set "BASE_PY=python"
)

if not defined BASE_PY (
    echo [ERROR] Python 3.10 or 3.11 was not found.
    echo Install Python 3.11 for Windows, enable the py launcher or add python.exe to PATH, then rerun.
    echo TTS 0.22.0 is not expected to work on Python 3.12+.
    exit /b 1
)

echo Creating virtual environment with: !BASE_PY!
!BASE_PY! -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment at "%VENV_DIR%".
    exit /b 1
)

set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
if not exist "!PYTHON_EXE!" (
    echo [ERROR] Venv Python was not created: "!PYTHON_EXE!".
    exit /b 1
)
exit /b 0


:ensure_packaging_tools
echo.
echo [2/5] Checking packaging tools...
"%PYTHON_EXE%" -m pip --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] pip is not available in "%VENV_DIR%".
    echo Try deleting the venv and rerunning, or repair the base Python installation.
    exit /b 1
)

"%PYTHON_EXE%" -c "import setuptools, wheel" >nul 2>nul
if errorlevel 1 (
    echo Installing/upgrading pip, setuptools, and wheel...
    "%PYTHON_EXE%" -m pip install --upgrade pip setuptools wheel
    if errorlevel 1 (
        echo [ERROR] Failed to install core packaging tools.
        exit /b 1
    )
) else (
    echo Packaging tools are present.
)
exit /b 0


:ensure_requirements
echo.
echo [3/5] Checking XTTS Studio dependencies...

set "REQ_HASH="
for /f "usebackq delims=" %%H in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-FileHash -Algorithm SHA256 -LiteralPath $env:REQ_FILE).Hash.ToLowerInvariant()"`) do set "REQ_HASH=%%H"
if not defined REQ_HASH (
    echo [ERROR] Could not compute requirements hash for "%REQ_FILE%".
    exit /b 1
)

set "OLD_HASH="
if exist "%STAMP_FILE%" set /p "OLD_HASH="<"%STAMP_FILE%"

set "NEED_INSTALL=0"
if not "%REQ_HASH%"=="%OLD_HASH%" set "NEED_INSTALL=1"

"%PYTHON_EXE%" -c "import fastapi, uvicorn, soundfile, numpy, librosa; import TTS; import multipart" >nul 2>nul
if errorlevel 1 set "NEED_INSTALL=1"

if "%NEED_INSTALL%"=="0" (
    echo Requirements are already installed and requirements.txt is unchanged.
    exit /b 0
)

echo Installing/updating dependencies from "%REQ_FILE%".
echo This can take a long time on the first run, especially Torch/CUDA and Coqui TTS.
echo PyTorch CUDA wheels are resolved via: %PIP_EXTRA_INDEX_URL%

"%PYTHON_EXE%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo [ERROR] Failed to update packaging tools before dependency install.
    exit /b 1
)

"%PYTHON_EXE%" -m pip install --upgrade -r "%REQ_FILE%"
if errorlevel 1 (
    echo.
    echo [ERROR] Dependency installation failed.
    echo Notes:
    echo   - The requirements request torch/torchaudio CUDA 12.1 wheels.
    echo   - If CUDA wheels are unavailable for your Python, install Python 3.10/3.11 and rerun.
    echo   - Check network access to https://download.pytorch.org/whl/cu121 and PyPI.
    exit /b 1
)

"%PYTHON_EXE%" -c "import fastapi, uvicorn, soundfile, numpy, librosa; import TTS; import multipart" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Dependencies installed, but import validation still failed.
    echo Run: "%PYTHON_EXE%" -c "import fastapi, uvicorn, soundfile, numpy, librosa; import TTS; import multipart"
    exit /b 1
)

>"%STAMP_FILE%" echo %REQ_HASH%
echo Dependencies are installed and stamp was updated.
exit /b 0


:check_port_available
echo.
echo [4/5] Checking for existing listener on %HOST%:%PORT%...
set "FOUND_LISTENER=0"
for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":%PORT% .*LISTENING"') do (
    set "FOUND_LISTENER=1"
    echo [ERROR] Port %HOST%:%PORT% is already in use by PID %%P.
)

if "%FOUND_LISTENER%"=="0" echo No existing listener found on port %PORT%.
if "%FOUND_LISTENER%"=="1" (
    echo.
    echo Another server is already bound to %HOST%:%PORT%.
    echo Identify it with:
    echo   netstat -ano ^| findstr :%PORT%
    echo   tasklist /FI "PID eq ^<PID^>"
    echo Stop it manually only if appropriate:
    echo   taskkill /PID ^<PID^> /F
    exit /b 1
)
exit /b 0


:start_server
echo.
echo [5/5] Starting XTTS Studio server...
echo Server logs will appear in a separate window named "XTTS Studio Server".
start "XTTS Studio Server" cmd /k ""%PYTHON_EXE%" -m uvicorn xtts_api.studio_server:app --host %HOST% --port %PORT%"
if errorlevel 1 (
    echo [ERROR] Failed to start the XTTS Studio server window.
    exit /b 1
)
exit /b 0


:health_check
echo.
echo Waiting for health endpoint: %HEALTH_URL%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$url=$env:HEALTH_URL; $ok=$false; for($i=1; $i -le 30; $i++){ try { $r=Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2; if($r.StatusCode -eq 200){ Write-Host ('[OK] Health check passed on attempt {0}.' -f $i); $ok=$true; break } } catch { Start-Sleep -Seconds 1 } }; if(-not $ok){ Write-Host '[WARN] Health check did not pass within 30 seconds. The server may still be loading models or dependencies.'; exit 2 }"
if errorlevel 1 (
    echo [WARN] Health endpoint is not ready yet. Watch the XTTS Studio Server window for details.
) else (
    start "" "%STUDIO_URL%"
)
exit /b 0


:fail
echo.
echo ============================================================
echo XTTS Studio launcher failed.
echo Review the messages above. Common fixes:
echo   - Install Python 3.10 or 3.11 for Windows.
echo   - Ensure network access to PyPI and PyTorch CUDA 12.1 wheels.
echo   - Delete "%VENV_DIR%" and rerun if the venv is corrupt.
echo   - Close any existing application using port %PORT%, then rerun.
echo ============================================================
exit /b 1


:done
echo.
echo Done.
exit /b 0
