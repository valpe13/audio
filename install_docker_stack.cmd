@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%install_docker_stack.ps1"
set "PS_SCRIPT_URL=https://raw.githubusercontent.com/valpe13/audio/main/install_docker_stack.ps1"

if not exist "%PS_SCRIPT%" (
  echo install_docker_stack.ps1 was not found next to this file.
  echo Downloading it from:
  echo %PS_SCRIPT_URL%
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PS_SCRIPT_URL%' -OutFile '%PS_SCRIPT%'"
  if errorlevel 1 (
    echo.
    echo [ERROR] Failed to download install_docker_stack.ps1.
    pause
    exit /b 1
  )
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Installer failed with exit code %EXIT_CODE%.
  echo Read the error above. If Docker Desktop asked for a reboot, reboot Windows and run this file again.
  pause
  exit /b %EXIT_CODE%
)

echo.
echo Done. XTTS Studio should be available at http://localhost:7870/studio/
pause
exit /b 0
