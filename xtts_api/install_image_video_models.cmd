@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

python xtts_api\install_image_video_models.py %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Image/video model manifest installer exited with code %EXIT_CODE%.
  echo Existing model files were not overwritten or deleted.
)

exit /b %EXIT_CODE%
