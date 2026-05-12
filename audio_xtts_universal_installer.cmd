@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul 2>nul

set "REPO_URL=https://github.com/valpe13/audio.git"
set "REPO_ZIP=https://github.com/valpe13/audio/archive/refs/heads/main.zip"
set "ASSETS_URL=https://github.com/valpe13/audio/releases/download/xtts-assets-v1/xtts_assets_v1.zip"
set "ASSETS_SHA256=4161134D93656ABFBD97C39AC2D6637001FE451643C616F37E6EA7310B23AFDC"
set "APP_DIR=audio"
set "PYTHON_VERSION=3.10.11"
set "PYTHON_INSTALLER=python-3.10.11-amd64.exe"
set "PYTHON_URL=https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe"
set "XTTS_CACHE=%LOCALAPPDATA%\tts\tts_models--multilingual--multi-dataset--xtts_v2"
set "XTTS_MODEL=%LOCALAPPDATA%\tts\tts_models--multilingual--multi-dataset--xtts_v2\model.pth"
set "XTTS_REFERENCE=xtts_api\reference_audio\natalia_shtin\natalia_shtin_clean_reference.wav"
set "CURRENT_INSTALLER=%~f0"
if exist "install_models.cmd" if exist "xtts_api\install_comfyui_portable.cmd" set "APP_DIR=."

call :parse_args %*
if errorlevel 1 exit /b 1
if defined SHOW_HELP (
  call :print_help
  exit /b 0
)

echo Универсальный установщик Audio XTTS
echo ===================================
echo.
echo Этот файл устанавливает или обновляет проект, Python 3.10 при необходимости,
echo XTTS-ресурсы, Python-библиотеки, Microsoft C++ Build Tools при необходимости,
echo а также проверяет/ремонтирует ComfyUI portable и загружает модели для
echo генерации изображений и видео.
echo Чтобы пропустить большие image/video модели, запустите с --skip-video-models.
echo.

where powershell >nul 2>nul
if errorlevel 1 (
  echo ОШИБКА: PowerShell необходим, но не найден.
  exit /b 1
)

call :ensure_python310
if errorlevel 1 goto fail

call :download_code
if errorlevel 1 goto fail

cd /d "%APP_DIR%"
if errorlevel 1 goto fail

if defined SKIP_ASSETS (
  echo Пропускаю загрузку XTTS-ресурсов и предзагрузку моделей/зависимостей, потому что указан --skip-assets.
) else (
  call :download_assets
  if errorlevel 1 goto fail

  call install_models.cmd --no-pause
  if errorlevel 1 goto fail
)

call :install_base_comfyui_runtime
if errorlevel 1 goto fail

call :install_default_video_resources

echo.
if defined INSTALL_MODE_UPDATE (
  echo Обновление успешно завершено.
) else (
  echo Новая установка успешно завершена.
)
echo Запуск: %CD%\run_audio_stack.cmd
echo Для XTTS Studio выберите пункт 1.
echo.
if not defined NO_PAUSE pause
exit /b 0

:parse_args
if "%~1"=="" exit /b 0
if /i "%~1"=="--no-pause" set "NO_PAUSE=1"& shift & goto parse_args
if /i "%~1"=="--with-video" set "WITH_VIDEO=1"& shift & goto parse_args
if /i "%~1"=="--no-video" set "SKIP_VIDEO_MODELS=1"& shift & goto parse_args
if /i "%~1"=="--skip-video-models" set "SKIP_VIDEO_MODELS=1"& shift & goto parse_args
if /i "%~1"=="--skip-assets" set "SKIP_ASSETS=1"& shift & goto parse_args
if /i "%~1"=="--help" set "SHOW_HELP=1"& shift & goto parse_args
if /i "%~1"=="/help" set "SHOW_HELP=1"& shift & goto parse_args
if /i "%~1"=="/?" set "SHOW_HELP=1"& shift & goto parse_args
echo ОШИБКА: Неизвестный параметр установщика: %~1
echo Запустите %~nx0 --help для справки.
exit /b 1

:print_help
echo Универсальный установщик Audio XTTS
echo.
echo Использование:
echo   %~nx0 [--no-pause] [--skip-video-models] [--skip-assets] [--help]
echo.
echo Параметры:
echo   --no-pause            Не ждать нажатия клавиши в конце.
echo   --skip-video-models   Пропустить большие модели/ресурсы ComfyUI для изображений и видео.
echo   --no-video            То же самое, что --skip-video-models.
echo   --with-video          Совместимость со старым запуском; теперь image/video модели ставятся по умолчанию.
echo   --skip-assets         Пропустить XTTS release assets и предзагрузку install_models.cmd.
echo   --help                Показать эту справку.
echo.
echo При запуске из git-клона установщик пробует безопасно выполнить git pull --ff-only.
echo Если git pull недоступен или пропущен из-за локальных/неотслеживаемых файлов,
echo проектные файлы синхронизируются из GitHub ZIP с сохранением пользовательских путей.
echo Базовый ComfyUI portable проверяется и ремонтируется автоматически; сломанная
echo папка ComfyUI_windows_portable переименовывается в backup установщиком ComfyUI.
echo Проверка включает ядро ComfyUI: ComfyUI\comfy\ldm\models\autoencoder.py.
echo По умолчанию установщик также скачивает image/video модели и доп. ресурсы ComfyUI.
echo Повторный запуск безопасен: существующие модели не перезаписываются без необходимости.
exit /b 0

:ensure_python310
where py >nul 2>nul
if not errorlevel 1 (
  py -3.10 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 10) else 1)" >nul 2>nul
  if not errorlevel 1 (
    echo Python 3.10 найден через py launcher.
    exit /b 0
  )
)

echo Python 3.10 не найден. Загружаю Python %PYTHON_VERSION%...
set "DL_DIR=%TEMP%\audio_xtts_installer"
if not exist "%DL_DIR%" mkdir "%DL_DIR%"
set "PY_INSTALLER_PATH=%DL_DIR%\%PYTHON_INSTALLER%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PY_INSTALLER_PATH%'"
if errorlevel 1 exit /b 1

echo Устанавливаю Python %PYTHON_VERSION% для текущего пользователя...
"%PY_INSTALLER_PATH%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1 Include_test=0 SimpleInstall=1
if errorlevel 1 exit /b 1

echo Жду регистрацию Python launcher...
timeout /t 5 /nobreak >nul
where py >nul 2>nul
if errorlevel 1 (
  echo ОШИБКА: Python launcher всё ещё не найден после установки.
  exit /b 1
)
py -3.10 -c "import sys; print(sys.version)"
if errorlevel 1 exit /b 1
exit /b 0

:download_code
if exist "%APP_DIR%\install_models.cmd" (
  set "INSTALL_MODE_UPDATE=1"
  echo Найдена существующая папка проекта: %APP_DIR%
  echo Обновляю на месте, сохраняя проекты пользователя, секреты, локальные настройки, virtualenv, cache и ComfyUI.
  set "UPDATED_PROJECT="
  set "GIT_CHECKOUT="
  if exist "%APP_DIR%\.git" (
    set "GIT_CHECKOUT=1"
    call :safe_git_update "%APP_DIR%"
    set "GIT_UPDATE_RESULT=%ERRORLEVEL%"
    if "%GIT_UPDATE_RESULT%"=="2" exit /b 1
    if "%GIT_UPDATE_RESULT%"=="0" (
      set "UPDATED_PROJECT=1"
    ) else (
      echo ПРЕДУПРЕЖДЕНИЕ: Git-обновление недоступно или пропущено; продолжаю установку/ремонт с существующими файлами проекта.
      echo Код проекта не был обновлён. Зависимости, ComfyUI и модели будут проверены без перезаписи локальных файлов через git.
    )
  )
  if not defined UPDATED_PROJECT call :refresh_existing_project_from_zip
  if errorlevel 1 exit /b 1
  if exist "%CURRENT_INSTALLER%" (
    if /i not "%CURRENT_INSTALLER%"=="%CD%\%APP_DIR%\audio_xtts_universal_installer.cmd" copy /y "%CURRENT_INSTALLER%" "%APP_DIR%\audio_xtts_universal_installer.cmd" >nul
  )
  exit /b 0
)

where git >nul 2>nul
if not errorlevel 1 (
  echo Существующая папка проекта не найдена. Выполняю новую установку в: %APP_DIR%
  echo Загружаю код проекта через git...
  git clone "%REPO_URL%" "%APP_DIR%"
  exit /b %ERRORLEVEL%
)

echo Git не найден. Вместо этого загружаю ZIP репозитория...
echo Существующая папка проекта не найдена. Выполняю новую установку в: %APP_DIR%
set "ZIP_PATH=%TEMP%\audio-main.zip"
set "UNZIP_DIR=%TEMP%\audio-main-unzip"
if exist "%ZIP_PATH%" del /f /q "%ZIP_PATH%"
if exist "%UNZIP_DIR%" rmdir /s /q "%UNZIP_DIR%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%REPO_ZIP%' -OutFile '%ZIP_PATH%'; Expand-Archive -Path '%ZIP_PATH%' -DestinationPath '%UNZIP_DIR%' -Force"
if errorlevel 1 exit /b 1
if exist "%UNZIP_DIR%\audio-main" (
  move "%UNZIP_DIR%\audio-main" "%APP_DIR%" >nul
  exit /b %ERRORLEVEL%
)
echo ОШИБКА: Не удалось найти распакованную папку audio-main.
exit /b 1

:refresh_existing_project_from_zip
echo Синхронизирую существующую папку проекта из GitHub ZIP, потому что git pull недоступен или пропущен...
echo Локальные пользовательские пути сохраняются; проектные файлы обновляются из GitHub ZIP.
set "ZIP_PATH=%TEMP%\audio-main.zip"
set "UNZIP_DIR=%TEMP%\audio-main-unzip"
if exist "%ZIP_PATH%" del /f /q "%ZIP_PATH%"
if exist "%UNZIP_DIR%" rmdir /s /q "%UNZIP_DIR%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%REPO_ZIP%' -OutFile '%ZIP_PATH%'; Expand-Archive -Path '%ZIP_PATH%' -DestinationPath '%UNZIP_DIR%' -Force"
if errorlevel 1 exit /b 1
if not exist "%UNZIP_DIR%\audio-main\install_models.cmd" (
  echo ОШИБКА: Не удалось найти install_models.cmd в загруженном ZIP проекта.
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$src='%UNZIP_DIR%\audio-main'; $dst='%CD%\%APP_DIR%'; $preserve=@('.git','.installer_cache','ComfyUI_windows_portable','xtts_api\.venv','xtts_api\reference_audio','xtts_api\studio_projects','fish_speech_api\config.json'); Get-ChildItem -LiteralPath $src -Force | ForEach-Object { $rel=$_.Name; if($preserve -contains $rel){ return }; Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $dst $rel) -Recurse -Force };"
if errorlevel 1 exit /b 1
exit /b 0

:safe_git_update
set "GIT_DIR_TARGET=%~1"
where git >nul 2>nul
if errorlevel 1 (
  echo Git не найден. Пропускаю автоматическое обновление кода через git.
  exit /b 1
)

git -C "%GIT_DIR_TARGET%" rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
  echo Эта папка не является git-клоном. Пропускаю git pull, чтобы не повредить файлы.
  exit /b 1
)

git -C "%GIT_DIR_TARGET%" diff --quiet -- . >nul 2>nul
if errorlevel 1 (
  echo ПРЕДУПРЕЖДЕНИЕ: Найдены локальные изменения в файлах. Автообновление через git пропущено.
  echo Изменения не тронуты. Проверьте их вручную командой: git status --short
  exit /b 1
)

git -C "%GIT_DIR_TARGET%" diff --cached --quiet -- . >nul 2>nul
if errorlevel 1 (
  echo ПРЕДУПРЕЖДЕНИЕ: Найдены подготовленные к коммиту изменения. Автообновление через git пропущено.
  echo Изменения не тронуты. Проверьте их вручную командой: git status --short
  exit /b 1
)

for /f "delims=" %%U in ('git -C "%GIT_DIR_TARGET%" ls-files --others --exclude-standard') do (
  echo ПРЕДУПРЕЖДЕНИЕ: Найдены новые неотслеживаемые файлы. Автообновление через git пропущено.
  echo Файлы не тронуты. Проверьте их вручную командой: git status --short
  exit /b 1
)

git -C "%GIT_DIR_TARGET%" rev-parse --abbrev-ref --symbolic-full-name @{u} >nul 2>nul
if errorlevel 1 (
  echo У текущей ветки не настроен upstream. Пропускаю git pull.
  echo Проверьте remote/branch вручную командой: git remote -v
  exit /b 1
)

echo Загружаю последние изменения из GitHub через git pull --ff-only...
git -C "%GIT_DIR_TARGET%" pull --ff-only
if errorlevel 1 (
  echo ОШИБКА: git pull не смог выполнить fast-forward обновление.
  echo Локальные файлы не сбрасывались и не удалялись.
  exit /b 2
)
echo Git-обновление завершено.
exit /b 0

:install_base_comfyui_runtime
echo.
echo Проверяю/чиню базовый ComfyUI portable для генерации изображений...
echo Если отсутствует ComfyUI\comfy\ldm\models\autoencoder.py, это сломанное ядро ComfyUI; папка будет переустановлена через backup.
if not exist "xtts_api\install_comfyui_portable.cmd" (
  echo ОШИБКА: Не найден xtts_api\install_comfyui_portable.cmd.
  echo Без него нельзя автоматически установить или починить ComfyUI portable.
  exit /b 1
)
call xtts_api\install_comfyui_portable.cmd --yes --force
if errorlevel 1 (
  echo ОШИБКА: Базовый ComfyUI portable не удалось установить или починить.
  exit /b 1
)
echo Базовый ComfyUI portable готов.
exit /b 0

:download_assets
echo.
if exist "%XTTS_MODEL%" if exist "%XTTS_REFERENCE%" (
  echo XTTS-модель и стандартный reference уже существуют. Пропускаю загрузку release assets.
  exit /b 0
)

echo Часть XTTS-ресурсов отсутствует. Загружаю release assets из GitHub Releases...
set "ASSETS_DIR=%CD%\.installer_cache"
set "ASSETS_ZIP=%ASSETS_DIR%\xtts_assets_v1.zip"
if not exist "%ASSETS_DIR%" mkdir "%ASSETS_DIR%"

if exist "%ASSETS_ZIP%" (
  echo Найден кэшированный архив ресурсов. Проверяю перед повторным использованием...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$h=(Get-FileHash '%ASSETS_ZIP%' -Algorithm SHA256).Hash; if($h -ne '%ASSETS_SHA256%'){exit 2}; Write-Host ('Cached archive SHA256 OK: '+$h)"
  if errorlevel 2 (
    echo Кэшированный архив неполный или устарел. Загружаю свежую копию...
    del /f /q "%ASSETS_ZIP%"
  )
)

if not exist "%ASSETS_ZIP%" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%ASSETS_URL%' -OutFile '%ASSETS_ZIP%'"
  if errorlevel 1 exit /b 1
)

echo Проверяю SHA256 для XTTS-ресурсов...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$h=(Get-FileHash '%ASSETS_ZIP%' -Algorithm SHA256).Hash; if($h -ne '%ASSETS_SHA256%'){Write-Error ('SHA256 mismatch: '+$h); exit 1}; Write-Host ('SHA256 OK: '+$h)"
if errorlevel 1 exit /b 1

echo Распаковываю XTTS-ресурсы...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '%ASSETS_ZIP%' -DestinationPath '%CD%' -Force; $cache=Join-Path $env:LOCALAPPDATA 'tts'; New-Item -ItemType Directory -Path $cache -Force | Out-Null; if(Test-Path '.\tts'){Copy-Item '.\tts\*' $cache -Recurse -Force; Remove-Item '.\tts' -Recurse -Force}"
if errorlevel 1 exit /b 1
exit /b 0

:install_default_video_resources
echo.
if defined SKIP_VIDEO_MODELS (
  echo Пропускаю большие image/video модели и дополнительные ресурсы ComfyUI, потому что указан --skip-video-models/--no-video.
  exit /b 0
)
if defined WITH_VIDEO (
  echo Параметр --with-video больше не нужен: image/video модели ставятся по умолчанию.
)
call :install_video_resources
exit /b 0

:install_video_resources
echo.
echo Устанавливаю image/video модели и дополнительные ресурсы ComfyUI. Ошибки здесь не отменяют установку XTTS.
if exist "install_optional_video_resources.cmd" (
  call install_optional_video_resources.cmd --no-pause
) else (
  echo ПРЕДУПРЕЖДЕНИЕ: install_optional_video_resources.cmd не найден. Пропускаю image/video ресурсы.
  exit /b 0
)
if errorlevel 1 (
  echo ПРЕДУПРЕЖДЕНИЕ: Установка image/video ресурсов сообщила об ошибках, но базовая установка XTTS завершена.
) else (
  echo Установка image/video ресурсов завершена.
)
exit /b 0

:fail
echo.
echo Установка не завершена. Проверьте ошибку выше.
echo.
if not defined NO_PAUSE pause
exit /b 1
