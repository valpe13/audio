@echo off
setlocal EnableExtensions

rem Safe installer wrapper for the Stability AI SVD-XT 1.1 checkpoint used by ComfyUI.
rem This script does not download anything until the Python helper asks for
rem manual confirmation and the user enters Y.

set "SCRIPT_DIR=%~dp0"
set "DEFAULT_TARGET_DIR=%SCRIPT_DIR%..\ComfyUI_windows_portable\ComfyUI\models\checkpoints"
set "DEFAULT_FILENAME=svd_xt.safetensors"
set "DEFAULT_MODEL_URL=https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt-1-1/resolve/main/svd_xt_1_1.safetensors"

rem Hugging Face model file URLs may change or require accepting model terms.
rem Override the default direct /resolve/main/*.safetensors URL by setting
rem SVD_XT_MODEL_URL before running this script.
set "MODEL_URL=%SVD_XT_MODEL_URL%"
if "%MODEL_URL%"=="" set "MODEL_URL=%DEFAULT_MODEL_URL%"

echo.
echo Stability AI SVD-XT 1.1 checkpoint installer for ComfyUI
echo ---------------------------------------------------------
echo Target folder:
echo   %DEFAULT_TARGET_DIR%
echo Output filename:
echo   %DEFAULT_FILENAME%
echo Model URL:
echo   %MODEL_URL%
echo.
echo IMPORTANT:
echo   This script will not download anything unless you confirm with Y.
echo   The default download is saved as svd_xt.safetensors to match XTTS Studio.
echo   Hugging Face may require login and accepting model terms first.
echo   You can override the URL with SVD_XT_MODEL_URL.
echo.

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python "%SCRIPT_DIR%install_svd_xt_model.py" --target-dir "%DEFAULT_TARGET_DIR%" --filename "%DEFAULT_FILENAME%" --url "%MODEL_URL%"
    goto :done
)

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 "%SCRIPT_DIR%install_svd_xt_model.py" --target-dir "%DEFAULT_TARGET_DIR%" --filename "%DEFAULT_FILENAME%" --url "%MODEL_URL%"
    goto :done
)

echo ERROR: Python 3 was not found in PATH.
echo Install Python 3 or run the helper manually with your Python executable:
echo   python "%SCRIPT_DIR%install_svd_xt_model.py"
exit /b 1

:done
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
    echo Installer finished with an error code: %EXIT_CODE%
)
exit /b %EXIT_CODE%
