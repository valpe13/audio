@echo off
setlocal EnableExtensions
cd /d "%~dp0"

chcp 65001 >nul 2>nul
set "NO_PAUSE="
set "WITH_VIDEO="
set "SKIP_GIT="
set "SHOW_HELP="

call :parse_args %*
if errorlevel 1 exit /b 1
if defined SHOW_HELP (
  call :print_help
  exit /b 0
)

echo Обновление и ремонт Audio/ComfyUI
echo =================================
echo.
echo Этот файл безопасно обновляет репозиторий, если он запущен из git-клона,
echo затем проверяет и при необходимости чинит ComfyUI_windows_portable.
echo Сломанная папка ComfyUI не удаляется: установщик переименует ее в backup.
echo.

if not defined SKIP_GIT (
  call :update_from_git
  if errorlevel 1 goto fail
) else (
  echo Обновление через git пропущено по параметру --skip-git.
)

echo.
echo Проверяю/чиню ComfyUI portable...
if not exist "xtts_api\install_comfyui_portable.cmd" (
  echo ОШИБКА: Не найден xtts_api\install_comfyui_portable.cmd.
  echo Запустите этот файл из корня репозитория audio.
  goto fail
)
call xtts_api\install_comfyui_portable.cmd --yes --force
if errorlevel 1 goto fail

echo.
if defined WITH_VIDEO (
  echo Устанавливаю/обновляю дополнительные видео-ресурсы ComfyUI...
  if exist "install_optional_video_resources.cmd" (
    call install_optional_video_resources.cmd --no-pause
    if errorlevel 1 (
      echo ПРЕДУПРЕЖДЕНИЕ: Дополнительные видео-ресурсы завершились с ошибками.
      echo Базовый ремонт ComfyUI уже выполнен; подробности смотрите выше.
    )
  ) else (
    echo ПРЕДУПРЕЖДЕНИЕ: install_optional_video_resources.cmd не найден; пропускаю.
  )
) else (
  echo Дополнительные видео-ресурсы не запрошены.
  echo Если они нужны, запустите: update_repair_comfyui.cmd --with-video
  echo Или отдельно: install_optional_video_resources.cmd
)

echo.
echo Готово. Для запуска используйте: run_audio_stack.cmd
echo Если нужен XTTS Studio, выберите пункт 1.
echo.
if not defined NO_PAUSE pause
endlocal
exit /b 0

:parse_args
if "%~1"=="" exit /b 0
if /i "%~1"=="--no-pause" set "NO_PAUSE=1"& shift & goto parse_args
if /i "%~1"=="--with-video" set "WITH_VIDEO=1"& shift & goto parse_args
if /i "%~1"=="--skip-git" set "SKIP_GIT=1"& shift & goto parse_args
if /i "%~1"=="--help" set "SHOW_HELP=1"& shift & goto parse_args
if /i "%~1"=="/help" set "SHOW_HELP=1"& shift & goto parse_args
if /i "%~1"=="/?" set "SHOW_HELP=1"& shift & goto parse_args
echo ОШИБКА: Неизвестный параметр: %~1
call :print_help
exit /b 1

:print_help
echo Использование:
echo   update_repair_comfyui.cmd [--with-video] [--skip-git] [--no-pause]
echo.
echo Параметры:
echo   --with-video  После ремонта ComfyUI запустить install_optional_video_resources.cmd.
echo   --skip-git    Не выполнять git pull, только проверить/починить ComfyUI.
echo   --no-pause    Не ждать нажатия клавиши в конце.
exit /b 0

:update_from_git
where git >nul 2>nul
if errorlevel 1 (
  echo Git не найден. Пропускаю автоматическое обновление кода.
  echo Чтобы обновлять код автоматически, установите Git for Windows или заново скачайте репозиторий.
  exit /b 0
)

git rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
  echo Эта папка не является git-клоном. Пропускаю git pull, чтобы не повредить файлы.
  exit /b 0
)

git diff --quiet -- . >nul 2>nul
if errorlevel 1 (
  echo Найдены локальные изменения в файлах. Автообновление через git пропущено.
  echo Изменения не тронуты. Проверьте их вручную командой: git status --short
  exit /b 0
)

git diff --cached --quiet -- . >nul 2>nul
if errorlevel 1 (
  echo Найдены подготовленные к коммиту изменения. Автообновление через git пропущено.
  echo Изменения не тронуты. Проверьте их вручную командой: git status --short
  exit /b 0
)

for /f "delims=" %%U in ('git ls-files --others --exclude-standard') do (
  echo Найдены новые неотслеживаемые файлы. Автообновление через git пропущено.
  echo Файлы не тронуты. Проверьте их вручную командой: git status --short
  exit /b 0
)

git rev-parse --abbrev-ref --symbolic-full-name @{u} >nul 2>nul
if errorlevel 1 (
  echo У текущей ветки не настроен upstream. Пропускаю git pull.
  echo Проверьте remote/branch вручную командой: git remote -v
  exit /b 0
)

echo Загружаю последние изменения из GitHub...
git pull --ff-only
if errorlevel 1 (
  echo ОШИБКА: git pull не смог выполнить fast-forward обновление.
  echo Локальные файлы не сбрасывались и не удалялись.
  exit /b 1
)
echo Git-обновление завершено.
exit /b 0

:fail
echo.
echo ОШИБКА: Обновление/ремонт не завершены. Проверьте сообщения выше.
echo.
if not defined NO_PAUSE pause
endlocal
exit /b 1
