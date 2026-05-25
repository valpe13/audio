@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "NO_PAUSE="
if /i "%~1"=="--no-pause" set "NO_PAUSE=1"

echo Optional XTTS Studio video/ComfyUI resource installer
echo =====================================================
echo.
echo This helper installs optional video resources only. It is safe to run
echo repeatedly; the underlying helpers avoid overwriting existing models.
echo.

if not exist "ComfyUI_windows_portable\ComfyUI\main.py" (
  echo WARNING: ComfyUI_windows_portable\ComfyUI\main.py was not found.
  echo Install or unpack ComfyUI portable there before using video workflows.
  echo The helper will still call resource installers so they can create folders
  echo or print more specific instructions.
  echo.
)

set "OPTIONAL_FAILURES=0"

echo.
echo Running optional installer: ComfyUI portable runtime from GitHub Releases
call xtts_api\install_comfyui_portable.cmd --yes --force
if errorlevel 1 (
  echo WARNING: ComfyUI portable runtime installer could not complete.
  echo          This is non-fatal; valid local ComfyUI folders are never overwritten.
  echo          Invalid local ComfyUI folders are renamed to timestamped backups when repair is possible.
  echo          If redistribution was approved, update xtts_api\comfyui_portable_manifest.json first.
  echo          Model/custom-node installers will continue below where possible.
  set /a OPTIONAL_FAILURES+=1
) else (
  echo OK: ComfyUI portable runtime is present or was installed
)

echo.
echo Running optional installer: project ComfyUI custom nodes and API bridges
call xtts_api\install_comfyui_project_nodes.cmd --yes
if errorlevel 1 (
  echo WARNING: Project ComfyUI custom-node installer could not complete.
  echo          Bridge nodes and external manager/XTTS nodes may need manual installation.
  set /a OPTIONAL_FAILURES+=1
) else (
  echo OK: Project ComfyUI custom nodes and API bridges are present
)

echo.
echo Running optional installer: manifest-based image/video models from GitHub Releases
call xtts_api\install_image_video_models.cmd --yes
if errorlevel 1 (
  echo WARNING: Manifest model installer could not install all resources.
  echo          This is non-fatal; GitHub Release assets may be temporarily unavailable.
  echo          Custom-node installers will continue below.
  set /a OPTIONAL_FAILURES+=1
) else (
  echo OK: Manifest image/video model installer finished
)

echo.
echo Running optional installer: AnimateDiff custom nodes and motion model
call xtts_api\install_animatediff_deps.cmd --yes
if errorlevel 1 (
  echo WARNING: Optional installer failed: AnimateDiff custom nodes and motion model
  set /a OPTIONAL_FAILURES+=1
) else (
  echo OK: AnimateDiff custom nodes and motion model
)

echo.
echo Running optional installer: AnimateDiff SD1.5 checkpoint
call xtts_api\install_animatediff_sd15_checkpoint.cmd --yes
if errorlevel 1 (
  echo WARNING: Optional installer failed: AnimateDiff SD1.5 checkpoint
  set /a OPTIONAL_FAILURES+=1
) else (
  echo OK: AnimateDiff SD1.5 checkpoint
)

echo.
echo Running optional installer: HotshotXL / SDXL AnimateDiff resources
call xtts_api\install_hotshotxl_deps.cmd --yes
if errorlevel 1 (
  echo WARNING: Optional installer failed: HotshotXL / SDXL AnimateDiff resources
  set /a OPTIONAL_FAILURES+=1
) else (
  echo OK: HotshotXL / SDXL AnimateDiff resources
)

if "%OPTIONAL_FAILURES%"=="0" (
  echo Optional video resource installer finished without required-helper errors.
) else (
  echo Optional video resource installer finished with %OPTIONAL_FAILURES% warning/error(s).
  echo Base XTTS Studio installation is not affected.
)

if not defined NO_PAUSE pause
endlocal
exit /b 0
