@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%.") do set "PROJECT_ROOT=%%~fI"
for %%I in ("%PROJECT_ROOT%\..") do set "PROJECT_PARENT=%%~fI"
if /I "%PROJECT_ROOT%"=="%PROJECT_PARENT%\audio" if exist "%PROJECT_PARENT%\xtts_api\studio_server.py" (
  echo [ERROR] This launcher is inside a nested duplicate checkout:
  echo         "%PROJECT_ROOT%"
  echo Use the workspace-root launcher instead:
  echo         "%PROJECT_PARENT%\run_audio_stack.cmd"
  echo This prevents launching the stale nested audio stack copy.
  pause
  exit /b 1
)
cd /d "%PROJECT_ROOT%"

echo Audio stack launcher
echo ====================
echo.
echo This menu starts local services in separate windows.
echo Keep the opened service windows running while you work.
echo.
echo 1. Start XTTS Studio (current workflow, http://127.0.0.1:7870/studio/)
echo 2. Start Silero TTS API (optional, http://127.0.0.1:7866)
echo 3. Start Fish Speech API (optional, http://127.0.0.1:7865)
echo 4. Start ComfyUI NVIDIA (optional bridge only)
echo 5. Start ComfyUI CPU (optional bridge only)
echo 6. Start XTTS Studio + optional Silero/Fish APIs (no ComfyUI)
echo 7. Exit
echo.
set /p choice=Choose an option [1-7]: 

if "%choice%"=="1" goto xtts
if "%choice%"=="2" goto silero
if "%choice%"=="3" goto fish
if "%choice%"=="4" goto comfy_gpu
if "%choice%"=="5" goto comfy_cpu
if "%choice%"=="6" goto all
goto end

:comfy_gpu
if exist "ComfyUI_windows_portable\run_nvidia_gpu.bat" (
  start "ComfyUI NVIDIA" cmd /k "cd /d "%~dp0ComfyUI_windows_portable" && call run_nvidia_gpu.bat"
) else (
  echo Missing ComfyUI_windows_portable\run_nvidia_gpu.bat
  pause
)
goto end

:comfy_cpu
if exist "ComfyUI_windows_portable\run_cpu.bat" (
  start "ComfyUI CPU" cmd /k "cd /d "%~dp0ComfyUI_windows_portable" && call run_cpu.bat"
) else (
  echo Missing ComfyUI_windows_portable\run_cpu.bat
  pause
)
goto end

:silero
if exist "silero_tts_api\run_server.cmd" (
  start "Silero TTS API" cmd /k "call "%~dp0silero_tts_api\run_server.cmd""
) else (
  echo Missing silero_tts_api\run_server.cmd
  pause
)
goto end

:fish
if exist "fish_speech_api\run_server.cmd" (
  start "Fish Speech API" cmd /k "call "%~dp0fish_speech_api\run_server.cmd""
) else (
  echo Missing fish_speech_api\run_server.cmd
  pause
)
goto end

:xtts
if exist "xtts_api\run_xtts_studio.cmd" (
  start "XTTS Studio" cmd /k "call "%~dp0xtts_api\run_xtts_studio.cmd""
) else (
  echo Missing xtts_api\run_xtts_studio.cmd
  pause
)
goto end

:all
call :start_silero_no_wait
call :start_fish_no_wait
call :start_xtts_no_wait
goto end

:start_comfy_gpu_no_wait
if exist "ComfyUI_windows_portable\run_nvidia_gpu.bat" start "ComfyUI NVIDIA" cmd /k "cd /d "%~dp0ComfyUI_windows_portable" && call run_nvidia_gpu.bat"
exit /b

:start_silero_no_wait
if exist "silero_tts_api\run_server.cmd" start "Silero TTS API" cmd /k "call "%~dp0silero_tts_api\run_server.cmd""
exit /b

:start_fish_no_wait
if exist "fish_speech_api\run_server.cmd" start "Fish Speech API" cmd /k "call "%~dp0fish_speech_api\run_server.cmd""
exit /b

:start_xtts_no_wait
if exist "xtts_api\run_xtts_studio.cmd" start "XTTS Studio" cmd /k "call "%~dp0xtts_api\run_xtts_studio.cmd""
exit /b

:end
endlocal
