@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHONUTF8=1"
set "COQUI_TOS_AGREED=1"
set "XTTS_VENV=xtts_api\.venv"
set "XTTS_PY=%XTTS_VENV%\Scripts\python.exe"
set "XTTS_CACHE=%LOCALAPPDATA%\tts\tts_models--multilingual--multi-dataset--xtts_v2"
set "XTTS_MODEL=%LOCALAPPDATA%\tts\tts_models--multilingual--multi-dataset--xtts_v2\model.pth"

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
echo Checking XTTS Python dependencies ...
"%XTTS_PY%" -c "import TTS, torch, torchaudio, fastapi, uvicorn, soundfile, transformers, tokenizers" >nul 2>nul
if errorlevel 1 (
  call :ensure_cpp_build_tools
  if errorlevel 1 exit /b 1
  echo Installing missing XTTS Python dependencies ...
  call :pip_install_xtts_requirements
  if errorlevel 1 exit /b 1
) else (
  echo XTTS Python dependencies already look installed.
)

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
if exist "%XTTS_MODEL%" (
  echo XTTS v2 model already exists in the local user cache: %XTTS_CACHE%
  goto done
)

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

:done
echo.
echo Done.
echo XTTS v2 model cache: %%LOCALAPPDATA%%\tts\tts_models--multilingual--multi-dataset--xtts_v2
echo Default reference: xtts_api\reference_audio\natalia_shtin\natalia_shtin_clean_reference.wav
echo Launch from the repository root with: run_audio_stack.cmd
echo.
if /i not "%~1"=="--no-pause" pause
endlocal
exit /b 0

:ensure_cpp_build_tools
echo.
echo Checking Microsoft C++ Build Tools, required when pip builds Coqui TTS from source ...
where cl >nul 2>nul
if not errorlevel 1 (
  echo Microsoft C++ compiler is available in PATH.
  exit /b 0
)

set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if exist "%VSWHERE%" (
  "%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath >nul 2>nul
  if not errorlevel 1 (
    echo Microsoft C++ Build Tools are already installed.
    exit /b 0
  )
)

echo Microsoft C++ Build Tools were not found.
echo They are required because Coqui TTS may need to build a native extension on this PC.
echo Downloading and installing Visual Studio Build Tools workload VCTools ...
set "BT_DIR=%TEMP%\audio_xtts_installer"
if not exist "%BT_DIR%" mkdir "%BT_DIR%"
set "BT_EXE=%BT_DIR%\vs_BuildTools.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vs_BuildTools.exe' -OutFile '%BT_EXE%'"
if errorlevel 1 (
  echo ERROR: Failed to download Microsoft C++ Build Tools installer.
  exit /b 1
)

echo Running Build Tools installer. This can take 10-30 minutes and may require administrator approval.
"%BT_EXE%" --quiet --wait --norestart --nocache --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended
if errorlevel 1 (
  echo ERROR: Microsoft C++ Build Tools installation failed.
  echo You can install it manually from https://visualstudio.microsoft.com/visual-cpp-build-tools/
  exit /b 1
)

echo Microsoft C++ Build Tools installation finished.
echo If pip still cannot find the compiler, close this window and run the installer again.
exit /b 0

:pip_install_xtts_requirements
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
set "VSINSTALL="
if exist "%VSWHERE%" (
  for /f "usebackq delims=" %%I in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSINSTALL=%%I"
)

if defined VSINSTALL if exist "%VSINSTALL%\Common7\Tools\VsDevCmd.bat" (
  echo Running pip inside Visual Studio compiler environment ...
  call "%VSINSTALL%\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64
  if errorlevel 1 exit /b 1
  "%XTTS_PY%" -m pip install -r xtts_api\requirements.txt --extra-index-url https://download.pytorch.org/whl/cu121
  exit /b %ERRORLEVEL%
)

echo Visual Studio developer environment was not found; trying normal pip install ...
"%XTTS_PY%" -m pip install -r xtts_api\requirements.txt --extra-index-url https://download.pytorch.org/whl/cu121
exit /b %ERRORLEVEL%
