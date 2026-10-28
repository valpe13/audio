# Audio XTTS offline/SFX installer support

This is the first practical offline installer layer for the Windows project. It does not replace the online installer in `audio_xtts_universal_installer.cmd`; it adds a local-payload path for cases where files have already been downloaded, cached, or manually staged.

## What is included

- `install_offline.cmd` starts the PowerShell offline installer.
- `install_offline.ps1` installs from `offline_payload` and verifies SHA256 values recorded in `offline_payload_manifest.json`.
- `tools/build_offline_payload.ps1` assembles an offline payload from local files only. It does not download multi-GB assets.
- `tools/build_offline_sfx.ps1` builds a 7-Zip self-extracting installer when `7z.exe` and a 7-Zip SFX module are available.

## Build a local payload

From the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_offline_payload.ps1 -Force
```

The default payload is written to `dist\offline_payload`. By default the builder creates `project\audio_project.zip` and checks for optional local components. Missing optional items are reported clearly and saved in the payload manifest.

Recommended full-payload inputs:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_offline_payload.ps1 `
  -OutputDir dist\offline_payload `
  -PythonInstaller C:\Installers\python-3.10.11-amd64.exe `
  -XttsAssetsZip C:\Installers\xtts_assets_v1.zip `
  -ComfyUIPortablePartsDir C:\Installers\comfyui-portable-v1 `
  -IncludeImageVideoModels `
  -Force
```

Notes:

- `-ComfyUIPortablePartsDir` should contain the part files named in `xtts_api\comfyui_portable_manifest.json`.
- `-ComfyUIPortableArchive` can be used instead when a full verified ComfyUI zip is available.
- `-IncludeImageVideoModels` copies only model files already present under `ComfyUI_windows_portable\ComfyUI\models` and listed in `xtts_api\image_video_models_manifest.json`.
- The builder intentionally does not download Python, XTTS assets, ComfyUI, or image/video models.
- The project archive is a clean application-source archive. It excludes local user/project/generated data such as `xtts_api\studio_projects`, generated `outputs`/`uploads`, local caches, `.env`/secret files, `fish_speech_api\config.json`, and local reference-audio folders. Required installers, source files, requirements, wheelhouses, and separately bundled model/assets remain included.

## Install from a payload folder

Copy `install_offline.cmd`, `install_offline.ps1`, and `offline_payload` to the target machine. Open Command Prompt in that folder first; paths with spaces are supported when you run the command from the installer folder:

```cmd
cd /d "C:\Users\MySkill.PC\Documents\generator 3"
install_offline.cmd -PayloadDir offline_payload -InstallDir audio
```

From PowerShell, run the `.cmd` explicitly:

```powershell
cd "C:\Users\MySkill.PC\Documents\generator 3"
.\install_offline.cmd -PayloadDir offline_payload -InstallDir audio
```

Useful options:

```cmd
install_offline.cmd -NoPause
install_offline.cmd -InPlace
install_offline.cmd -SkipPython -SkipVideoModels
install_offline.cmd -SkipModels
```

The offline installer:

1. Checks for Python 3.10 and uses the bundled Python installer if present.
2. Extracts the project archive from the payload, or uses existing project files if no archive is present.
3. Extracts bundled XTTS release assets and copies any bundled `tts` cache content to `%LOCALAPPDATA%\tts`.
4. Installs ComfyUI portable from a bundled full archive or verified split parts when present.
5. Copies bundled image/video model files when present.
6. Runs `install_models.cmd --offline --no-pause` to prepare the XTTS environment from local wheelhouse/cache where possible.

## Build a 7-Zip SFX installer

Install 7-Zip and the 7-Zip Extra SFX module package if your normal 7-Zip install does not include `7z.sfx` or `7zSD.sfx`.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_offline_sfx.ps1 `
  -PayloadDir dist\offline_payload `
  -OutputExe dist\AudioXTTS_Offline_Setup.exe `
  -SfxModule C:\Tools\7zip-extra\7z.sfx `
  -Force
```

The SFX contains:

- `install_offline.cmd`
- `install_offline.ps1`
- `README_OFFLINE_INSTALL.md`
- `offline_payload\...`

When launched, it extracts to a temporary folder and runs `install_offline.cmd -FromSfx`.

## Checksums and safety

- Payload files are recorded in `offline_payload_manifest.json` with SHA256 checksums.
- `install_offline.ps1` verifies checksums before using bundled installers, archives, parts, and models.
- Existing ComfyUI folders and model files are not destructively overwritten when they appear invalid or have mismatched checksums.
- The scripts do not run `git push`, upload release assets, or download huge files.

## Current limitations

- A fully offline Python dependency install requires an appropriate local wheelhouse or pre-populated pip cache. `install_models.cmd --offline` now prefers `xtts_api\wheelhouse` and disables network index access for the main XTTS requirements install.
- Microsoft C++ Build Tools are not bundled automatically. If a package must compile from source and no wheel is available, offline install can fail.
- ComfyUI custom-node dependency installation may still require network access unless those dependencies are already present in the bundled ComfyUI portable runtime.
- Multi-GB assets are not bundled by default. Stage them manually and rerun the payload builder.
