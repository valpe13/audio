@echo off
setlocal EnableExtensions

rem Safe installer wrapper for AnimateDiff custom nodes and a motion module used by ComfyUI.
rem By default this script targets ..\ComfyUI_windows_portable and asks for manual confirmation.

set "SCRIPT_DIR=%~dp0"
set "DEFAULT_COMFYUI_ROOT=%SCRIPT_DIR%..\ComfyUI_windows_portable"
set "DEFAULT_MOTION_MODEL_URL=https://huggingface.co/guoyww/animatediff/resolve/main/mm_sd_v15_v2.ckpt"
set "DEFAULT_MOTION_MODEL_FILENAME=mm_sd_v15_v2.ckpt"

if "%COMFYUI_PORTABLE_ROOT%"=="" set "COMFYUI_PORTABLE_ROOT=%DEFAULT_COMFYUI_ROOT%"
if "%ANIMATEDIFF_MOTION_MODEL_URL%"=="" set "ANIMATEDIFF_MOTION_MODEL_URL=%DEFAULT_MOTION_MODEL_URL%"
if "%ANIMATEDIFF_MOTION_MODEL_FILENAME%"=="" set "ANIMATEDIFF_MOTION_MODEL_FILENAME=%DEFAULT_MOTION_MODEL_FILENAME%"

echo.
echo AnimateDiff dependency installer for ComfyUI
echo ------------------------------------------
echo ComfyUI portable root:
echo   %COMFYUI_PORTABLE_ROOT%
echo Motion model URL:
echo   %ANIMATEDIFF_MOTION_MODEL_URL%
echo Motion model filename:
echo   %ANIMATEDIFF_MOTION_MODEL_FILENAME%
echo.
echo IMPORTANT:
echo   Existing custom nodes and model files will not be overwritten.
echo   The Python helper asks for Y before installing unless you pass --yes.
echo   You can override COMFYUI_PORTABLE_ROOT, ANIMATEDIFF_MOTION_MODEL_URL,
echo   and ANIMATEDIFF_MOTION_MODEL_FILENAME before running this script.
echo.

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python "%SCRIPT_DIR%install_animatediff_deps.py" --comfyui-root "%COMFYUI_PORTABLE_ROOT%" --motion-model-url "%ANIMATEDIFF_MOTION_MODEL_URL%" --motion-model-filename "%ANIMATEDIFF_MOTION_MODEL_FILENAME%" %*
    goto :done
)

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 "%SCRIPT_DIR%install_animatediff_deps.py" --comfyui-root "%COMFYUI_PORTABLE_ROOT%" --motion-model-url "%ANIMATEDIFF_MOTION_MODEL_URL%" --motion-model-filename "%ANIMATEDIFF_MOTION_MODEL_FILENAME%" %*
    goto :done
)

echo ERROR: Python 3 was not found in PATH.
echo Install Python 3 or run the helper manually with your Python executable:
echo   python "%SCRIPT_DIR%install_animatediff_deps.py"
exit /b 1

:done
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
    echo Installer finished with an error code: %EXIT_CODE%
)
exit /b %EXIT_CODE%
