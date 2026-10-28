[CmdletBinding()]
param(
    [string]$PayloadDir = "offline_payload",
    [string]$InstallDir = "audio",
    [switch]$InPlace,
    [switch]$SkipPython,
    [switch]$SkipModels,
    [switch]$SkipComfyUI,
    [switch]$SkipVideoModels,
    [switch]$NoPause,
    [switch]$FromSfx,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Section([string]$Title) {
    Write-Host ""
    Write-Host $Title
    Write-Host ("=" * $Title.Length)
}

function Resolve-ExistingPathOrDefault([string]$PathText, [string]$BasePath) {
    if ([System.IO.Path]::IsPathRooted($PathText)) { return $PathText }
    return (Join-Path $BasePath $PathText)
}

function Get-RelativePathCompat([string]$BasePath, [string]$TargetPath) {
    $baseFull = [System.IO.Path]::GetFullPath($BasePath)
    $targetFull = [System.IO.Path]::GetFullPath($TargetPath)
    if (-not $baseFull.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
        $baseFull += [System.IO.Path]::DirectorySeparatorChar
    }
    $baseUri = [Uri]$baseFull
    $targetUri = [Uri]$targetFull
    return [Uri]::UnescapeDataString($baseUri.MakeRelativeUri($targetUri).ToString()).Replace('/', [System.IO.Path]::DirectorySeparatorChar)
}

function Assert-SafeRelativePath([string]$RelativePath) {
    if ([string]::IsNullOrWhiteSpace($RelativePath)) { throw "Empty relative path in offline payload manifest." }
    if ([System.IO.Path]::IsPathRooted($RelativePath)) { throw "Unsafe rooted path in offline payload manifest: $RelativePath" }
    $parts = $RelativePath -replace '/', '\' -split '\\+'
    if ($parts -contains "..") { throw "Unsafe parent-relative path in offline payload manifest: $RelativePath" }
}

function Get-FileSha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Test-Sha256([string]$Path, [string]$ExpectedSha256) {
    if ([string]::IsNullOrWhiteSpace($ExpectedSha256)) { return $true }
    $actual = Get-FileSha256 $Path
    return ($actual -eq $ExpectedSha256.ToLowerInvariant())
}

function Get-OptionalProperty([object]$Object, [string]$Name) {
    if ($null -eq $Object) { return $null }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $null }
    return $prop.Value
}

function Set-Status([System.Collections.IDictionary]$Status, [string]$Name, [string]$Value) {
    $Status[$Name] = $Value
    Write-Host ("[{0}] {1}" -f $Name, $Value)
}

function Show-Help {
    Write-Host "Offline installer for Audio XTTS"
    Write-Host ""
    Write-Host "Usage: install_offline.cmd [options]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -PayloadDir <path>      Offline payload folder. Default: offline_payload"
    Write-Host "  -InstallDir <path>      Target install/update folder. Default: audio"
    Write-Host "  -InPlace                Install into the current script folder instead of -InstallDir."
    Write-Host "  -SkipPython             Do not install bundled Python even if present."
    Write-Host "  -SkipModels             Skip install_models.cmd."
    Write-Host "  -SkipComfyUI            Skip ComfyUI portable payload install."
    Write-Host "  -SkipVideoModels        Skip image/video model payload install."
    Write-Host "  -NoPause                Do not pause on exit."
    Write-Host "  -Help                   Show this help."
}

function Expand-ZipSafe([string]$ZipPath, [string]$DestinationPath) {
    New-Item -ItemType Directory -Path $DestinationPath -Force | Out-Null
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $DestinationPath -Force
}

function Test-ComfyUIRuntimeValid([string]$RootPath) {
    $required = @("ComfyUI\main.py", "ComfyUI\comfy\ldm\models\autoencoder.py", "run_nvidia_gpu.bat", "run_cpu.bat")
    foreach ($rel in $required) {
        if (-not (Test-Path -LiteralPath (Join-Path $RootPath $rel) -PathType Leaf)) { return $false }
    }
    return $true
}

function Expand-ComfyUIArchive([string]$ArchivePath, [string]$TargetPath) {
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("audio-offline-comfyui-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    try {
        Expand-Archive -LiteralPath $ArchivePath -DestinationPath $tempRoot -Force
        $runtimeRoot = $null
        if (Test-ComfyUIRuntimeValid $tempRoot) {
            $runtimeRoot = $tempRoot
        } else {
            foreach ($candidate in Get-ChildItem -LiteralPath $tempRoot -Directory -Force) {
                if (Test-ComfyUIRuntimeValid $candidate.FullName) { $runtimeRoot = $candidate.FullName; break }
            }
        }
        if ([string]::IsNullOrWhiteSpace($runtimeRoot)) { throw "Extracted ComfyUI archive does not contain the expected runtime files." }
        New-Item -ItemType Directory -Path (Split-Path -Path $TargetPath -Parent) -Force | Out-Null
        if ($runtimeRoot -eq $tempRoot) {
            New-Item -ItemType Directory -Path $TargetPath -Force | Out-Null
            Copy-DirectoryContents $tempRoot $TargetPath
        } else {
            Move-Item -LiteralPath $runtimeRoot -Destination $TargetPath
        }
    } finally {
        if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
    }
}

function Copy-DirectoryContents([string]$SourceDir, [string]$DestinationDir) {
    if (-not (Test-Path -LiteralPath $SourceDir -PathType Container)) { throw "Source directory not found: $SourceDir" }
    New-Item -ItemType Directory -Path $DestinationDir -Force | Out-Null
    Get-ChildItem -LiteralPath $SourceDir -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $DestinationDir $_.Name) -Recurse -Force
    }
}

function Install-PythonFromPayload([object]$Manifest, [string]$PayloadRoot, [System.Collections.IDictionary]$Status) {
    if ($SkipPython) { Set-Status $Status "Python" "SKIPPED - requested by -SkipPython"; return }
    $pyOk = $false
    try {
        & py -3.10 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 10) else 1)" *> $null
        if ($LASTEXITCODE -eq 0) { $pyOk = $true }
    } catch { $pyOk = $false }
    if ($pyOk) { Set-Status $Status "Python" "OK - Python 3.10 already available"; return }

    $components = Get-OptionalProperty $Manifest "components"
    $pythonItem = Get-OptionalProperty $components "python_installer"
    if ($null -eq $pythonItem -or [string]::IsNullOrWhiteSpace([string]$pythonItem.path)) {
        throw "Python 3.10 is not available and no python_installer component exists in the payload."
    }
    Assert-SafeRelativePath ([string]$pythonItem.path)
    $installer = Join-Path $PayloadRoot ([string]$pythonItem.path)
    if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) { throw "Bundled Python installer missing: $installer" }
    if (-not (Test-Sha256 $installer ([string]$pythonItem.sha256))) { throw "SHA256 mismatch for bundled Python installer: $installer" }
    Write-Host "Installing bundled Python 3.10 for the current user..."
    $proc = Start-Process -FilePath $installer -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1 Include_test=0 SimpleInstall=1" -Wait -PassThru
    if ($proc.ExitCode -ne 0) { throw "Bundled Python installer failed with exit code $($proc.ExitCode)." }
    Start-Sleep -Seconds 5
    & py -3.10 -c "import sys; print(sys.version)"
    if ($LASTEXITCODE -ne 0) { throw "Python 3.10 was installed but py -3.10 still does not work." }
    Set-Status $Status "Python" "OK - bundled Python installer completed"
}

function Install-ProjectFiles([object]$Manifest, [string]$PayloadRoot, [string]$TargetRoot, [System.Collections.IDictionary]$Status) {
    $components = Get-OptionalProperty $Manifest "components"
    $project = Get-OptionalProperty $components "project"
    if ($null -ne $project -and -not [string]::IsNullOrWhiteSpace([string]$project.path)) {
        Assert-SafeRelativePath ([string]$project.path)
        $projectZip = Join-Path $PayloadRoot ([string]$project.path)
        if (-not (Test-Path -LiteralPath $projectZip -PathType Leaf)) { throw "Project archive missing from payload: $projectZip" }
        if (-not (Test-Sha256 $projectZip ([string]$project.sha256))) { throw "SHA256 mismatch for project archive: $projectZip" }
        New-Item -ItemType Directory -Path $TargetRoot -Force | Out-Null
        Write-Host "Extracting project payload into: $TargetRoot"
        Expand-ZipSafe $projectZip $TargetRoot
        Set-Status $Status "Project" "OK - project archive extracted"
        return
    }
    if (Test-Path -LiteralPath (Join-Path $TargetRoot "install_models.cmd") -PathType Leaf) {
        Set-Status $Status "Project" "OK - using existing project files"
        return
    }
    throw "Payload has no project archive and target does not contain install_models.cmd: $TargetRoot"
}

function Install-XttsAssets([object]$Manifest, [string]$PayloadRoot, [string]$TargetRoot, [System.Collections.IDictionary]$Status) {
    $components = Get-OptionalProperty $Manifest "components"
    $assets = Get-OptionalProperty $components "xtts_assets"
    if ($null -eq $assets -or [string]::IsNullOrWhiteSpace([string]$assets.path)) {
        Set-Status $Status "XTTS assets" "SKIPPED - payload component not present"
        return
    }
    Assert-SafeRelativePath ([string]$assets.path)
    $zip = Join-Path $PayloadRoot ([string]$assets.path)
    if (-not (Test-Path -LiteralPath $zip -PathType Leaf)) { throw "XTTS assets archive missing: $zip" }
    if (-not (Test-Sha256 $zip ([string]$assets.sha256))) { throw "SHA256 mismatch for XTTS assets archive: $zip" }
    Write-Host "Extracting bundled XTTS assets into project and LOCALAPPDATA cache when applicable..."
    Expand-ZipSafe $zip $TargetRoot
    $ttsFolder = Join-Path $TargetRoot "tts"
    if (Test-Path -LiteralPath $ttsFolder -PathType Container) {
        $localTts = Join-Path $env:LOCALAPPDATA "tts"
        New-Item -ItemType Directory -Path $localTts -Force | Out-Null
        Copy-DirectoryContents $ttsFolder $localTts
        Write-Host "Copied bundled tts cache files to: $localTts"
    }
    Set-Status $Status "XTTS assets" "OK - bundled assets extracted"
}

function Install-ComfyUIPortable([object]$Manifest, [string]$PayloadRoot, [string]$TargetRoot, [System.Collections.IDictionary]$Status) {
    if ($SkipComfyUI) { Set-Status $Status "ComfyUI portable" "SKIPPED - requested by -SkipComfyUI"; return }
    $components = Get-OptionalProperty $Manifest "components"
    $component = Get-OptionalProperty $components "comfyui_portable"
    if ($null -eq $component) { Set-Status $Status "ComfyUI portable" "SKIPPED - payload component not present"; return }
    $archivePath = Get-OptionalProperty $component "archive_path"
    $archiveName = Get-OptionalProperty $component "archive_name"
    $parts = Get-OptionalProperty $component "parts"
    $target = Join-Path $TargetRoot "ComfyUI_windows_portable"
    if (Test-ComfyUIRuntimeValid $target) { Set-Status $Status "ComfyUI portable" "OK - existing runtime already valid"; return }
    if (Test-Path -LiteralPath $target) { throw "Existing ComfyUI_windows_portable is present but invalid. Offline installer will not overwrite it; move or rename it, then rerun." }

    if (-not [string]::IsNullOrWhiteSpace([string]$archivePath)) {
        Assert-SafeRelativePath ([string]$archivePath)
        $archive = Join-Path $PayloadRoot ([string]$archivePath)
        if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) { throw "ComfyUI portable archive missing: $archive" }
        if (-not (Test-Sha256 $archive ([string]$component.sha256))) { throw "SHA256 mismatch for ComfyUI archive: $archive" }
        Expand-ComfyUIArchive $archive $target
    } elseif ($parts -is [System.Collections.IEnumerable]) {
        $cache = Join-Path $TargetRoot ".installer_cache\offline-comfyui"
        New-Item -ItemType Directory -Path $cache -Force | Out-Null
        if ([string]::IsNullOrWhiteSpace([string]$archiveName)) { throw "ComfyUI portable split-parts component is missing archive_name." }
        $archive = Join-Path $cache ([string]$archiveName)
        $tmpArchive = "$archive.reassemble"
        if (Test-Path -LiteralPath $tmpArchive) { Remove-Item -LiteralPath $tmpArchive -Force }
        $out = [System.IO.File]::Open($tmpArchive, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
        try {
            foreach ($part in $parts) {
                Assert-SafeRelativePath ([string]$part.path)
                $partPath = Join-Path $PayloadRoot ([string]$part.path)
                if (-not (Test-Path -LiteralPath $partPath -PathType Leaf)) { throw "ComfyUI portable part missing: $partPath" }
                if (-not (Test-Sha256 $partPath ([string]$part.sha256))) { throw "SHA256 mismatch for ComfyUI part: $partPath" }
                $in = [System.IO.File]::OpenRead($partPath)
                try { $in.CopyTo($out) } finally { $in.Dispose() }
            }
        } finally { $out.Dispose() }
        if (-not (Test-Sha256 $tmpArchive ([string]$component.sha256))) { throw "SHA256 mismatch for reassembled ComfyUI archive: $tmpArchive" }
        Move-Item -LiteralPath $tmpArchive -Destination $archive -Force
        Expand-ComfyUIArchive $archive $target
    } else {
        throw "ComfyUI portable component exists but has neither archive_path nor parts."
    }
    if (-not (Test-ComfyUIRuntimeValid $target)) { throw "Installed ComfyUI portable is missing required files." }
    Set-Status $Status "ComfyUI portable" "OK - installed from local payload"
}

function Install-ImageVideoModels([object]$Manifest, [string]$PayloadRoot, [string]$TargetRoot, [System.Collections.IDictionary]$Status) {
    if ($SkipVideoModels) { Set-Status $Status "Image/video models" "SKIPPED - requested by -SkipVideoModels"; return }
    $components = Get-OptionalProperty $Manifest "components"
    $component = Get-OptionalProperty $components "image_video_models"
    if ($null -eq $component -or $null -eq $component.files) { Set-Status $Status "Image/video models" "SKIPPED - payload component not present"; return }
    $modelsRoot = Join-Path $TargetRoot "ComfyUI_windows_portable\ComfyUI\models"
    New-Item -ItemType Directory -Path $modelsRoot -Force | Out-Null
    $copied = 0
    $verified = 0
    foreach ($file in $component.files) {
        Assert-SafeRelativePath ([string]$file.path)
        Assert-SafeRelativePath ([string]$file.target_relative_path)
        $src = Join-Path $PayloadRoot ([string]$file.path)
        $dst = Join-Path $modelsRoot ([string]$file.target_relative_path)
        if (-not (Test-Path -LiteralPath $src -PathType Leaf)) { throw "Image/video model payload file missing: $src" }
        if (-not (Test-Sha256 $src ([string]$file.sha256))) { throw "SHA256 mismatch for image/video model: $src" }
        if (Test-Path -LiteralPath $dst -PathType Leaf) {
            if (Test-Sha256 $dst ([string]$file.sha256)) { $verified++; continue }
            throw "Existing model has different SHA256 and was left untouched: $dst"
        }
        New-Item -ItemType Directory -Path (Split-Path -Path $dst -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $src -Destination $dst -Force
        $copied++
    }
    Set-Status $Status "Image/video models" "OK - copied $copied, already verified $verified"
}

function Invoke-ProjectInstallers([string]$TargetRoot, [System.Collections.IDictionary]$Status) {
    Push-Location $TargetRoot
    try {
        if ($SkipModels) {
            Set-Status $Status "XTTS Python/models" "SKIPPED - requested by -SkipModels"
        } elseif (Test-Path -LiteralPath "install_models.cmd" -PathType Leaf) {
            $env:XTTS_OFFLINE = "1"
            $env:XTTS_SKIP_PIP_PREFLIGHT = "1"
            Write-Host "Running install_models.cmd in offline mode..."
            & cmd.exe /c "install_models.cmd --offline --no-pause"
            if ($LASTEXITCODE -ne 0) { throw "install_models.cmd failed with exit code $LASTEXITCODE." }
            Set-Status $Status "XTTS Python/models" "OK - install_models.cmd completed"
        } else {
            throw "install_models.cmd not found in target project."
        }
    } finally {
        Pop-Location
    }
}

if ($Help) { Show-Help; exit 0 }

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$payloadRoot = Resolve-ExistingPathOrDefault $PayloadDir $scriptRoot
$payloadRoot = [System.IO.Path]::GetFullPath($payloadRoot)
$targetRoot = if ($InPlace) { $scriptRoot } else { Resolve-ExistingPathOrDefault $InstallDir $scriptRoot }
$targetRoot = [System.IO.Path]::GetFullPath($targetRoot)
$status = [ordered]@{}
$failed = $false

Write-Section "Audio XTTS offline installer"
Write-Host "Script folder: $scriptRoot"
Write-Host "Payload:       $payloadRoot"
Write-Host "Install dir:   $targetRoot"
Write-Host "From SFX:      $FromSfx"

try {
    if (-not (Test-Path -LiteralPath $payloadRoot -PathType Container)) { throw "Offline payload folder not found: $payloadRoot" }
    $manifestPath = Join-Path $payloadRoot "offline_payload_manifest.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "Offline payload manifest not found: $manifestPath" }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json

    Write-Section "Verifying and installing local payload"
    Install-PythonFromPayload $manifest $payloadRoot $status
    Install-ProjectFiles $manifest $payloadRoot $targetRoot $status
    Install-XttsAssets $manifest $payloadRoot $targetRoot $status
    Install-ComfyUIPortable $manifest $payloadRoot $targetRoot $status
    Install-ImageVideoModels $manifest $payloadRoot $targetRoot $status
    Invoke-ProjectInstallers $targetRoot $status
} catch {
    $failed = $true
    Write-Host ""
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Section "Offline installation status"
foreach ($key in $status.Keys) { Write-Host ("  {0}: {1}" -f $key, $status[$key]) }
if ($failed) {
    Write-Host ""
    Write-Host "Offline installation failed. No destructive cleanup was performed. Existing user files were left in place."
    if (-not $NoPause) { Read-Host "Press Enter to exit" | Out-Null }
    exit 1
}

Write-Host ""
Write-Host "Offline installation finished. Launch with: $targetRoot\run_audio_stack.cmd"
if (-not $NoPause) { Read-Host "Press Enter to exit" | Out-Null }
exit 0
