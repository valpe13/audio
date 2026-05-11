@echo off
setlocal EnableExtensions

rem Safe installer wrapper for the Juggernaut XL SDXL quality/balanced checkpoint used by ComfyUI.
rem This script does not download anything until the Python helper asks for
rem manual confirmation and the user enters Y.

set "SCRIPT_DIR=%~dp0"
set "DEFAULT_TARGET_DIR=%SCRIPT_DIR%..\ComfyUI_windows_portable\ComfyUI\models\checkpoints"
set "DEFAULT_FILENAME=juggernautXL.safetensors"

rem Hugging Face model file URLs may change or require accepting a model license.
rem Put a direct /resolve/main/*.safetensors URL here, or set the environment
rem variable JUGGERNAUT_XL_MODEL_URL before running this script.
set "MODEL_URL=%JUGGERNAUT_XL_MODEL_URL%"

echo.
echo Juggernaut XL SDXL quality/balanced checkpoint installer for ComfyUI
echo --------------------------------------------------------------------
echo Target folder:
echo   %DEFAULT_TARGET_DIR%
echo Output filename:
echo   %DEFAULT_FILENAME%
echo.
echo IMPORTANT:
echo   This script will not download anything unless you confirm with Y.
echo   If MODEL_URL is empty, open this .cmd file or set JUGGERNAUT_XL_MODEL_URL
echo   to a direct Hugging Face /resolve/main/*.safetensors URL first.
echo.

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python "%SCRIPT_DIR%install_juggernaut_xl_model.py" --target-dir "%DEFAULT_TARGET_DIR%" --filename "%DEFAULT_FILENAME%" --url "%MODEL_URL%"
    goto :done
)

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 "%SCRIPT_DIR%install_juggernaut_xl_model.py" --target-dir "%DEFAULT_TARGET_DIR%" --filename "%DEFAULT_FILENAME%" --url "%MODEL_URL%"
    goto :done
)

echo ERROR: Python 3 was not found in PATH.
echo Install Python 3 or run the helper manually with your Python executable:
echo   python "%SCRIPT_DIR%install_juggernaut_xl_model.py"
exit /b 1

:done
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
    echo Installer finished with an error code: %EXIT_CODE%
)
exit /b %EXIT_CODE%
