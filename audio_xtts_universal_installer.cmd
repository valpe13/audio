@echo off
setlocal EnableExtensions

set "REPO_URL=https://github.com/valpe13/audio.git"
set "REPO_ZIP=https://github.com/valpe13/audio/archive/refs/heads/main.zip"
set "ASSETS_URL=https://github.com/valpe13/audio/releases/download/xtts-assets-v1/xtts_assets_v1.zip"
set "ASSETS_SHA256=4161134D93656ABFBD97C39AC2D6637001FE451643C616F37E6EA7310B23AFDC"
set "APP_DIR=audio"
set "PYTHON_VERSION=3.10.11"
set "PYTHON_INSTALLER=python-3.10.11-amd64.exe"
set "PYTHON_URL=https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe"

if /i "%~1"=="--no-pause" set "NO_PAUSE=1"

echo Universal Audio XTTS installer
echo ==============================
echo.
echo This file downloads the project code, Python 3.10 if needed,
echo XTTS release assets, Python libraries, and prepares the local environment.
echo.

where powershell >nul 2>nul
if errorlevel 1 (
  echo ERROR: PowerShell is required but was not found.
  exit /b 1
)

call :ensure_python310
if errorlevel 1 goto fail

call :download_code
if errorlevel 1 goto fail

cd /d "%APP_DIR%"
if errorlevel 1 goto fail

call :download_assets
if errorlevel 1 goto fail

call install_models.cmd --no-pause
if errorlevel 1 goto fail

echo.
echo Installation completed successfully.
echo Start the app with: %CD%\run_audio_stack.cmd
echo Choose option 1 to open XTTS Studio.
echo.
if not defined NO_PAUSE pause
exit /b 0

:ensure_python310
where py >nul 2>nul
if not errorlevel 1 (
  py -3.10 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 10) else 1)" >nul 2>nul
  if not errorlevel 1 (
    echo Python 3.10 found through py launcher.
    exit /b 0
  )
)

echo Python 3.10 was not found. Downloading Python %PYTHON_VERSION%...
set "DL_DIR=%TEMP%\audio_xtts_installer"
if not exist "%DL_DIR%" mkdir "%DL_DIR%"
set "PY_INSTALLER_PATH=%DL_DIR%\%PYTHON_INSTALLER%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PY_INSTALLER_PATH%'"
if errorlevel 1 exit /b 1

echo Installing Python %PYTHON_VERSION% for the current user...
"%PY_INSTALLER_PATH%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1 Include_test=0 SimpleInstall=1
if errorlevel 1 exit /b 1

echo Waiting for Python launcher registration...
timeout /t 5 /nobreak >nul
where py >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python launcher still not found after installation.
  exit /b 1
)
py -3.10 -c "import sys; print(sys.version)"
if errorlevel 1 exit /b 1
exit /b 0

:download_code
if exist "%APP_DIR%\install_models.cmd" (
  echo Project folder already exists: %APP_DIR%
  exit /b 0
)

where git >nul 2>nul
if not errorlevel 1 (
  echo Downloading project code with git...
  git clone "%REPO_URL%" "%APP_DIR%"
  exit /b %ERRORLEVEL%
)

echo Git was not found. Downloading repository ZIP instead...
set "ZIP_PATH=%TEMP%\audio-main.zip"
set "UNZIP_DIR=%TEMP%\audio-main-unzip"
if exist "%ZIP_PATH%" del /f /q "%ZIP_PATH%"
if exist "%UNZIP_DIR%" rmdir /s /q "%UNZIP_DIR%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%REPO_ZIP%' -OutFile '%ZIP_PATH%'; Expand-Archive -Path '%ZIP_PATH%' -DestinationPath '%UNZIP_DIR%' -Force"
if errorlevel 1 exit /b 1
if exist "%UNZIP_DIR%\audio-main" (
  move "%UNZIP_DIR%\audio-main" "%APP_DIR%" >nul
  exit /b %ERRORLEVEL%
)
echo ERROR: Could not find extracted audio-main folder.
exit /b 1

:download_assets
echo.
echo Downloading XTTS release assets from GitHub Releases...
set "ASSETS_DIR=%CD%\.installer_cache"
set "ASSETS_ZIP=%ASSETS_DIR%\xtts_assets_v1.zip"
if not exist "%ASSETS_DIR%" mkdir "%ASSETS_DIR%"
if exist "%ASSETS_ZIP%" del /f /q "%ASSETS_ZIP%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%ASSETS_URL%' -OutFile '%ASSETS_ZIP%'"
if errorlevel 1 exit /b 1

echo Verifying XTTS assets SHA256...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$h=(Get-FileHash '%ASSETS_ZIP%' -Algorithm SHA256).Hash; if($h -ne '%ASSETS_SHA256%'){Write-Error ('SHA256 mismatch: '+$h); exit 1}; Write-Host ('SHA256 OK: '+$h)"
if errorlevel 1 exit /b 1

echo Extracting XTTS assets...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '%ASSETS_ZIP%' -DestinationPath '%CD%' -Force; $cache=Join-Path $env:LOCALAPPDATA 'tts'; New-Item -ItemType Directory -Path $cache -Force | Out-Null; Copy-Item '.\tts\*' $cache -Recurse -Force; Remove-Item '.\tts' -Recurse -Force"
if errorlevel 1 exit /b 1
exit /b 0

:fail
echo.
echo Installation failed. Check the error above.
echo.
if not defined NO_PAUSE pause
exit /b 1
