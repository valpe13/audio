@echo off
setlocal EnableExtensions

rem Safe installer wrapper for an SD1.5 checkpoint used by AnimateDiff in ComfyUI.
rem This script does not download anything until the Python helper asks for
rem manual confirmation and the user enters Y, unless --yes is passed through.

set "SCRIPT_DIR=%~dp0"
set "DEFAULT_TARGET_DIR=%SCRIPT_DIR%..\ComfyUI_windows_portable\ComfyUI\models\checkpoints"
set "DEFAULT_FILENAME=DreamShaper_8_pruned.safetensors"
set "DEFAULT_MODEL_URL=https://huggingface.co/Lykon/DreamShaper/resolve/main/DreamShaper_8_pruned.safetensors"

rem Override the default direct /resolve/main/*.safetensors URL by setting
rem ANIMATEDIFF_SD15_CHECKPOINT_URL before running this script.
set "MODEL_URL=%ANIMATEDIFF_SD15_CHECKPOINT_URL%"
if "%MODEL_URL%"=="" set "MODEL_URL=%DEFAULT_MODEL_URL%"

set "MODEL_FILENAME=%ANIMATEDIFF_SD15_CHECKPOINT_FILENAME%"
if "%MODEL_FILENAME%"=="" set "MODEL_FILENAME=%DEFAULT_FILENAME%"

echo.
echo AnimateDiff SD1.5 checkpoint installer for ComfyUI
echo --------------------------------------------------
echo Target folder:
echo   %DEFAULT_TARGET_DIR%
echo Output filename:
echo   %MODEL_FILENAME%
echo Model URL:
echo   %MODEL_URL%
echo.
echo IMPORTANT:
echo   This script will not overwrite existing checkpoints.
echo   The default download is DreamShaper 8 pruned, an SD1.5 checkpoint.
echo   You can override the URL with ANIMATEDIFF_SD15_CHECKPOINT_URL.
echo   You can override the filename with ANIMATEDIFF_SD15_CHECKPOINT_FILENAME.
echo.

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python "%SCRIPT_DIR%install_animatediff_sd15_checkpoint.py" --target-dir "%DEFAULT_TARGET_DIR%" --filename "%MODEL_FILENAME%" --url "%MODEL_URL%" %*
    goto :done
)

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 "%SCRIPT_DIR%install_animatediff_sd15_checkpoint.py" --target-dir "%DEFAULT_TARGET_DIR%" --filename "%MODEL_FILENAME%" --url "%MODEL_URL%" %*
    goto :done
)

echo ERROR: Python 3 was not found in PATH.
echo Install Python 3 or run the helper manually with your Python executable:
echo   python "%SCRIPT_DIR%install_animatediff_sd15_checkpoint.py"
exit /b 1

:done
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
    echo Installer finished with an error code: %EXIT_CODE%
)
exit /b %EXIT_CODE%
