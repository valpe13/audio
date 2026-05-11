@echo off
setlocal EnableExtensions

rem Safe installer wrapper for the SDXL/HotshotXL motion module used by XTTS Studio's generated_hotshotxl backend.

set "SCRIPT_DIR=%~dp0"
set "DEFAULT_COMFYUI_ROOT=%SCRIPT_DIR%..\ComfyUI_windows_portable"
set "DEFAULT_HOTSHOTXL_MOTION_MODEL_URL=https://huggingface.co/hotshotco/Hotshot-XL/resolve/main/hsxl_temporal_layers.safetensors"
set "DEFAULT_HOTSHOTXL_MOTION_MODEL_FILENAME=hsxl_temporal_layers.safetensors"

if "%COMFYUI_PORTABLE_ROOT%"=="" set "COMFYUI_PORTABLE_ROOT=%DEFAULT_COMFYUI_ROOT%"
if "%HOTSHOTXL_MOTION_MODEL_URL%"=="" set "HOTSHOTXL_MOTION_MODEL_URL=%DEFAULT_HOTSHOTXL_MOTION_MODEL_URL%"
if "%HOTSHOTXL_MOTION_MODEL_FILENAME%"=="" set "HOTSHOTXL_MOTION_MODEL_FILENAME=%DEFAULT_HOTSHOTXL_MOTION_MODEL_FILENAME%"

echo.
echo HotshotXL / SDXL AnimateDiff installer for ComfyUI
echo ----------------------------------------------------
echo ComfyUI portable root:
echo   %COMFYUI_PORTABLE_ROOT%
echo Motion model URL:
echo   %HOTSHOTXL_MOTION_MODEL_URL%
echo Motion model filename:
echo   %HOTSHOTXL_MOTION_MODEL_FILENAME%
echo.
echo IMPORTANT:
echo   Existing custom nodes and model files will not be overwritten.
echo   The Python helper asks for Y before downloading unless you pass --yes.
echo   You can override COMFYUI_PORTABLE_ROOT, HOTSHOTXL_MOTION_MODEL_URL,
echo   and HOTSHOTXL_MOTION_MODEL_FILENAME before running this script.
echo.

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python "%SCRIPT_DIR%install_hotshotxl_deps.py" --comfyui-root "%COMFYUI_PORTABLE_ROOT%" --motion-model-url "%HOTSHOTXL_MOTION_MODEL_URL%" --motion-model-filename "%HOTSHOTXL_MOTION_MODEL_FILENAME%" %*
    goto :done
)

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 "%SCRIPT_DIR%install_hotshotxl_deps.py" --comfyui-root "%COMFYUI_PORTABLE_ROOT%" --motion-model-url "%HOTSHOTXL_MOTION_MODEL_URL%" --motion-model-filename "%HOTSHOTXL_MOTION_MODEL_FILENAME%" %*
    goto :done
)

echo ERROR: Python 3 was not found in PATH.
echo Install Python 3 or run the helper manually with your Python executable:
echo   python "%SCRIPT_DIR%install_hotshotxl_deps.py"
exit /b 1

:done
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
    echo Installer finished with an error code: %EXIT_CODE%
)
exit /b %EXIT_CODE%
