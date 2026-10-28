@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul 2>nul

where powershell >nul 2>nul
if errorlevel 1 (
  echo ERROR: PowerShell is required for the offline installer but was not found.
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_offline.ps1" %*
set "INSTALL_EXIT=%ERRORLEVEL%"

if not "%INSTALL_EXIT%"=="0" (
  echo.
  echo Offline installation failed with exit code %INSTALL_EXIT%.
) else (
  echo.
  echo Offline installation completed successfully.
)

exit /b %INSTALL_EXIT%
