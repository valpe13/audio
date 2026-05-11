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
set "XTTS_CACHE=%LOCALAPPDATA%\tts\tts_models--multilingual--multi-dataset--xtts_v2"
set "XTTS_MODEL=%LOCALAPPDATA%\tts\tts_models--multilingual--multi-dataset--xtts_v2\model.pth"
set "XTTS_REFERENCE=xtts_api\reference_audio\natalia_shtin\natalia_shtin_clean_reference.wav"
set "CURRENT_INSTALLER=%~f0"

call :parse_args %*
if errorlevel 1 exit /b 1
if defined SHOW_HELP (
  call :print_help
  exit /b 0
)

echo Universal Audio XTTS installer
echo ==============================
echo.
echo This file downloads the project code, Python 3.10 if needed,
echo XTTS release assets, Python libraries, Microsoft C++ Build Tools if needed,
echo and prepares the local environment. Existing installs are updated in-place.
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

if defined SKIP_ASSETS (
  echo Skipping XTTS release asset download and model/dependency preload because --skip-assets was supplied.
) else (
  call :download_assets
  if errorlevel 1 goto fail

  call install_models.cmd --no-pause
  if errorlevel 1 goto fail
)

call :maybe_install_video_resources

echo.
if defined INSTALL_MODE_UPDATE (
  echo Update completed successfully.
) else (
  echo Fresh installation completed successfully.
)
echo Start the app with: %CD%\run_audio_stack.cmd
echo Choose option 1 to open XTTS Studio.
echo.
if not defined NO_PAUSE pause
exit /b 0

:parse_args
if "%~1"=="" exit /b 0
if /i "%~1"=="--no-pause" set "NO_PAUSE=1"& shift & goto parse_args
if /i "%~1"=="--with-video" set "WITH_VIDEO=1"& shift & goto parse_args
if /i "%~1"=="--skip-assets" set "SKIP_ASSETS=1"& shift & goto parse_args
if /i "%~1"=="--help" set "SHOW_HELP=1"& shift & goto parse_args
if /i "%~1"=="/help" set "SHOW_HELP=1"& shift & goto parse_args
if /i "%~1"=="/?" set "SHOW_HELP=1"& shift & goto parse_args
echo ERROR: Unknown installer option: %~1
echo Run %~nx0 --help for usage.
exit /b 1

:print_help
echo Universal Audio XTTS installer
echo.
echo Usage:
echo   %~nx0 [--no-pause] [--with-video] [--skip-assets] [--help]
echo.
echo Options:
echo   --no-pause     Do not wait for a final keypress.
echo   --with-video   Install optional ComfyUI video resources after XTTS setup.
echo   --skip-assets  Skip XTTS release assets and install_models.cmd preload.
echo   --help         Show this help text.
echo.
echo Existing installs are updated safely. User data, secrets, virtualenvs,
echo .installer_cache, reference audio, studio projects, local configs, and
echo ComfyUI_windows_portable are preserved during Git/ZIP refreshes.
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
  set "INSTALL_MODE_UPDATE=1"
  echo Existing project folder found: %APP_DIR%
  echo Updating in-place while preserving user projects, secrets, local configs, virtualenvs, cache, and ComfyUI.
  set "UPDATED_PROJECT="
  if exist "%APP_DIR%\.git" (
    where git >nul 2>nul
    if not errorlevel 1 (
      echo Updating existing project folder from GitHub...
      git -C "%APP_DIR%" reset --hard HEAD
      if errorlevel 1 exit /b 1
      git -C "%APP_DIR%" clean -fd -e .installer_cache/ -e ComfyUI_windows_portable/ -e xtts_api/.venv/ -e xtts_api/reference_audio/ -e xtts_api/studio_projects/ -e fish_speech_api/config.json -e **/project.secrets.json
      if errorlevel 1 exit /b 1
      git -C "%APP_DIR%" pull --ff-only
      if errorlevel 1 exit /b 1
      set "UPDATED_PROJECT=1"
    ) else (
      echo Git is not installed; keeping existing project folder as-is.
    )
  )
  if not defined UPDATED_PROJECT call :refresh_existing_project_from_zip
  if errorlevel 1 exit /b 1
  if exist "%CURRENT_INSTALLER%" (
    if /i not "%CURRENT_INSTALLER%"=="%CD%\%APP_DIR%\audio_xtts_universal_installer.cmd" copy /y "%CURRENT_INSTALLER%" "%APP_DIR%\audio_xtts_universal_installer.cmd" >nul
  )
  exit /b 0
)

where git >nul 2>nul
if not errorlevel 1 (
  echo No existing project folder found. Performing a fresh install into: %APP_DIR%
  echo Downloading project code with git...
  git clone "%REPO_URL%" "%APP_DIR%"
  exit /b %ERRORLEVEL%
)

echo Git was not found. Downloading repository ZIP instead...
echo No existing project folder found. Performing a fresh install into: %APP_DIR%
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

:refresh_existing_project_from_zip
echo Refreshing existing project folder from GitHub ZIP because Git update is unavailable...
echo Preserving local-only paths during ZIP refresh.
set "ZIP_PATH=%TEMP%\audio-main.zip"
set "UNZIP_DIR=%TEMP%\audio-main-unzip"
if exist "%ZIP_PATH%" del /f /q "%ZIP_PATH%"
if exist "%UNZIP_DIR%" rmdir /s /q "%UNZIP_DIR%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%REPO_ZIP%' -OutFile '%ZIP_PATH%'; Expand-Archive -Path '%ZIP_PATH%' -DestinationPath '%UNZIP_DIR%' -Force"
if errorlevel 1 exit /b 1
if not exist "%UNZIP_DIR%\audio-main\install_models.cmd" (
  echo ERROR: Could not find install_models.cmd in downloaded project ZIP.
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$src='%UNZIP_DIR%\audio-main'; $dst='%CD%\%APP_DIR%'; $preserve=@('.git','.installer_cache','ComfyUI_windows_portable','xtts_api\.venv','xtts_api\reference_audio','xtts_api\studio_projects','fish_speech_api\config.json'); Get-ChildItem -LiteralPath $src -Force | ForEach-Object { $rel=$_.Name; if($preserve -contains $rel){ return }; Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $dst $rel) -Recurse -Force };"
if errorlevel 1 exit /b 1
exit /b 0

:download_assets
echo.
if exist "%XTTS_MODEL%" if exist "%XTTS_REFERENCE%" (
  echo XTTS model and default reference already exist. Skipping release asset download.
  exit /b 0
)

echo Some XTTS assets are missing. Downloading release assets from GitHub Releases...
set "ASSETS_DIR=%CD%\.installer_cache"
set "ASSETS_ZIP=%ASSETS_DIR%\xtts_assets_v1.zip"
if not exist "%ASSETS_DIR%" mkdir "%ASSETS_DIR%"

if exist "%ASSETS_ZIP%" (
  echo Found cached asset archive. Verifying before reuse...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$h=(Get-FileHash '%ASSETS_ZIP%' -Algorithm SHA256).Hash; if($h -ne '%ASSETS_SHA256%'){exit 2}; Write-Host ('Cached archive SHA256 OK: '+$h)"
  if errorlevel 2 (
    echo Cached archive is incomplete or outdated. Downloading a fresh copy...
    del /f /q "%ASSETS_ZIP%"
  )
)

if not exist "%ASSETS_ZIP%" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%ASSETS_URL%' -OutFile '%ASSETS_ZIP%'"
  if errorlevel 1 exit /b 1
)

echo Verifying XTTS assets SHA256...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$h=(Get-FileHash '%ASSETS_ZIP%' -Algorithm SHA256).Hash; if($h -ne '%ASSETS_SHA256%'){Write-Error ('SHA256 mismatch: '+$h); exit 1}; Write-Host ('SHA256 OK: '+$h)"
if errorlevel 1 exit /b 1

echo Extracting XTTS assets...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '%ASSETS_ZIP%' -DestinationPath '%CD%' -Force; $cache=Join-Path $env:LOCALAPPDATA 'tts'; New-Item -ItemType Directory -Path $cache -Force | Out-Null; if(Test-Path '.\tts'){Copy-Item '.\tts\*' $cache -Recurse -Force; Remove-Item '.\tts' -Recurse -Force}"
if errorlevel 1 exit /b 1
exit /b 0

:maybe_install_video_resources
echo.
if defined WITH_VIDEO (
  call :install_video_resources
  exit /b 0
)
if defined NO_PAUSE (
  echo Optional video resources were not requested. Skipping ComfyUI video setup.
  exit /b 0
)
choice /C YN /N /M "Install optional ComfyUI video resources now? [Y/N] "
if errorlevel 2 (
  echo Optional video resources skipped.
  exit /b 0
)
call :install_video_resources
exit /b 0

:install_video_resources
echo.
echo Installing optional ComfyUI video resources. Failures here will not fail the XTTS install.
if not exist "ComfyUI_windows_portable\ComfyUI\main.py" (
  echo WARNING: ComfyUI_windows_portable\ComfyUI\main.py was not found.
  echo Optional resource scripts may fail until ComfyUI portable is installed or unpacked at that path.
)
if exist "install_optional_video_resources.cmd" (
  call install_optional_video_resources.cmd --no-pause
) else (
  echo WARNING: install_optional_video_resources.cmd was not found. Skipping optional resources.
  exit /b 0
)
if errorlevel 1 (
  echo WARNING: Optional video resource setup reported errors, but the base XTTS install is complete.
) else (
  echo Optional video resource setup finished.
)
exit /b 0

:fail
echo.
echo Installation failed. Check the error above.
echo.
if not defined NO_PAUSE pause
exit /b 1
