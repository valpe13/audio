@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHONUTF8=1"
set "COQUI_TOS_AGREED=1"
set "XTTS_VENV=xtts_api\.venv"
set "XTTS_PY=%XTTS_VENV%\Scripts\python.exe"

echo XTTS installer / model preloader
echo =================================
echo.
echo This installer prepares the current XTTS Studio workflow only.
echo ComfyUI is optional for this repository and is not required by XTTS Studio.
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python launcher "py" was not found.
  echo Install Python 3.10 for Windows, then run this file again.
  exit /b 1
)

if not exist "%XTTS_PY%" (
  echo Creating Python 3.10 virtual environment at %XTTS_VENV% ...
  py -3.10 -m venv "%XTTS_VENV%"
  if errorlevel 1 (
    echo ERROR: Could not create the XTTS virtual environment with Python 3.10.
    echo Install Python 3.10 and ensure "py -3.10" works.
    exit /b 1
  )
) else (
  echo Reusing existing virtual environment: %XTTS_VENV%
)

echo.
echo Upgrading pip tooling ...
"%XTTS_PY%" -m pip install --upgrade pip wheel "setuptools<81"
if errorlevel 1 exit /b 1

echo.
echo Installing XTTS Python dependencies ...
"%XTTS_PY%" -m pip install -r xtts_api\requirements.txt --extra-index-url https://download.pytorch.org/whl/cu121
if errorlevel 1 exit /b 1

echo.
echo Preparing the default Natalia Shtin XTTS reference audio ...
if not exist "xtts_api\reference_audio\natalia_shtin\natalia_shtin_clean_reference.wav" (
  "%XTTS_PY%" xtts_api\prepare_natalia_shtin_reference.py
  if errorlevel 1 (
    echo ERROR: Failed to prepare the default reference WAV.
    exit /b 1
  )
) else (
  echo Reference already exists: xtts_api\reference_audio\natalia_shtin\natalia_shtin_clean_reference.wav
)

echo.
echo Preloading Coqui XTTS v2 model into the local user cache ...
set "PRELOAD_SCRIPT=%TEMP%\preload_xtts_model.py"
> "%PRELOAD_SCRIPT%" echo import os
>> "%PRELOAD_SCRIPT%" echo from pathlib import Path
>> "%PRELOAD_SCRIPT%" echo os.environ.setdefault('COQUI_TOS_AGREED', '1')
>> "%PRELOAD_SCRIPT%" echo from TTS.api import TTS
>> "%PRELOAD_SCRIPT%" echo model_name = 'tts_models/multilingual/multi-dataset/xtts_v2'
>> "%PRELOAD_SCRIPT%" echo print('Loading/downloading', model_name)
>> "%PRELOAD_SCRIPT%" echo TTS(model_name, progress_bar=True, gpu=False)
>> "%PRELOAD_SCRIPT%" echo print('XTTS v2 is available in the Coqui user cache.')
>> "%PRELOAD_SCRIPT%" echo print('Typical Windows cache root:', Path.home() / 'AppData' / 'Local' / 'tts')
"%XTTS_PY%" "%PRELOAD_SCRIPT%"
if errorlevel 1 (
  echo ERROR: Failed to preload XTTS v2. Check internet access and the Python error above.
  exit /b 1
)

echo.
echo Done.
echo XTTS v2 model cache: %%LOCALAPPDATA%%\tts\tts_models--multilingual--multi-dataset--xtts_v2
echo Default reference: xtts_api\reference_audio\natalia_shtin\natalia_shtin_clean_reference.wav
echo Launch from the repository root with: run_audio_stack.cmd
echo.
if /i not "%~1"=="--no-pause" pause
endlocal
