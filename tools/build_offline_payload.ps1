[CmdletBinding()]
param(
    [string]$OutputDir = "dist\offline_payload",
    [string]$PythonInstaller = "",
    [string]$XttsAssetsZip = "",
    [string]$ComfyUIPortableArchive = "",
    [string]$ComfyUIPortablePartsDir = "",
    [switch]$IncludeImageVideoModels,
    [switch]$NoProjectArchive,
    [switch]$Force,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Show-Help {
    Write-Host "Build an offline installer payload without downloading large assets."
    Write-Host ""
    Write-Host "Usage: powershell -File tools\build_offline_payload.ps1 [options]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -OutputDir <path>              Payload output folder. Default: dist\offline_payload"
    Write-Host "  -PythonInstaller <path>        Optional local python-3.10.11-amd64.exe."
    Write-Host "  -XttsAssetsZip <path>          Optional local xtts_assets_v1.zip."
    Write-Host "  -ComfyUIPortableArchive <path> Optional full ComfyUI portable zip."
    Write-Host "  -ComfyUIPortablePartsDir <dir> Optional folder containing manifest split parts."
    Write-Host "  -IncludeImageVideoModels       Copy already-present ComfyUI model files listed by manifest."
    Write-Host "  -NoProjectArchive              Do not create payload\project\audio_project.zip."
    Write-Host "  -Force                         Reuse/overwrite existing files in OutputDir."
}

function Get-RepoRoot {
    return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
}

function Get-FileSha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
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

function Add-ZipEntryFromFile([System.IO.Compression.ZipArchive]$Archive, [string]$SourcePath, [string]$EntryName) {
    $normalizedEntry = $EntryName.Replace('\', '/')
    $entry = $Archive.CreateEntry($normalizedEntry, [System.IO.Compression.CompressionLevel]::Optimal)
    $entryStream = $entry.Open()
    try {
        $fileStream = [System.IO.File]::OpenRead($SourcePath)
        try { $fileStream.CopyTo($entryStream) } finally { $fileStream.Dispose() }
    } finally {
        $entryStream.Dispose()
    }
}

function Add-FileComponent([string]$Source, [string]$DestinationRoot, [string]$RelativeDestination) {
    $destination = Join-Path $DestinationRoot $RelativeDestination
    New-Item -ItemType Directory -Path (Split-Path -Path $destination -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $destination -Force
    return [ordered]@{
        path = ($RelativeDestination -replace '\\','/')
        size_bytes = (Get-Item -LiteralPath $destination).Length
        sha256 = Get-FileSha256 $destination
    }
}

function Assert-OptionalFile([string]$Path, [string]$Label) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "$Label not found: $Path" }
    return $true
}

function New-ProjectArchive([string]$RepoRoot, [string]$OutputRoot) {
    $projectDir = Join-Path $OutputRoot "project"
    New-Item -ItemType Directory -Path $projectDir -Force | Out-Null
    $archivePath = Join-Path $projectDir "audio_project.zip"
    if (Test-Path -LiteralPath $archivePath) { Remove-Item -LiteralPath $archivePath -Force }

    $excludeTop = @(
        ".git",
        ".agents",
        ".codex",
        ".roo",
        "1",
        "docker-data",
        "verification",
        ".installer_cache",
        ".venv",
        ".venv-fish",
        ".venv-silero",
        "audio",
        "dist",
        "fish_speech_runtime",
        "release_assets",
        "ComfyUI_windows_portable",
        "outputs",
        "uploads",
        "tts"
    )
    $excludeNames = @(
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".cache",
        "cache",
        "hf_cache",
        "huggingface",
        "torch_cache",
        "outputs",
        "uploads"
    )
    $excludeExtensions = @(".pyc", ".pyo", ".log", ".tmp", ".temp", ".ckpt", ".safetensors", ".pth", ".pt", ".bin", ".onnx", ".gguf", ".zip", ".7z")
    $excludeRelative = @(
        "xtts_api/studio_projects",
        "xtts_api/outputs",
        "xtts_api/reference_audio",
        "fish_speech_api/reference_audio",
        "silero_tts_api/outputs",
        "fish_speech_api/outputs",
        "xtts_api/pronunciation_dictionary.json",
        "fish_speech_api/config.json"
    )
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    # Prune excluded directories before recursion; an installed tree can contain
    # hundreds of thousands of runtime files that are not part of the source.
    function Get-SourceCandidates([string]$Directory) {
        foreach ($item in Get-ChildItem -LiteralPath $Directory -Force) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
            $rel = (Get-RelativePathCompat $RepoRoot $item.FullName).Replace('\', '/')
            if ($Directory -eq $RepoRoot -and $item.Name -in $excludeTop) { continue }
            if ($item.Name -in $excludeNames -or $item.Name -match '^\.venv') { continue }
            if ($rel -in $excludeRelative) { continue }
            if ($item.PSIsContainer) { Get-SourceCandidates $item.FullName } else { $item }
        }
    }
    $sourceFiles = @(Get-SourceCandidates $RepoRoot | Where-Object {
        $rel = Get-RelativePathCompat $RepoRoot $_.FullName
        $relNormalized = ($rel -replace '\\','/').TrimStart('/')
        $parts = $rel -split '[\\/]+'
        if ($parts[0] -in $excludeTop) { return $false }
        foreach ($part in $parts) { if ($part -in $excludeNames) { return $false } }
        foreach ($excluded in $excludeRelative) {
            if ($relNormalized.Equals($excluded, [System.StringComparison]::OrdinalIgnoreCase) -or $relNormalized.StartsWith($excluded + "/", [System.StringComparison]::OrdinalIgnoreCase)) { return $false }
        }
        if ($_.FullName -match '\\.venv(\\|$)' -or $_.FullName -match '\\.venv-silero(\\|$)' -or $_.FullName -match '\\.venv-fish(\\|$)') { return $false }
        if ($_.Name -like ".env*" -or $_.Name -like "*.secret" -or $_.Name -in @("secrets.json", "project_secrets.json", "project.secrets.json", "local-storage-audit.json", "2.3.0")) { return $false }
        if ($excludeExtensions -contains $_.Extension.ToLowerInvariant()) { return $false }
        return $true
    })
    $zipStream = [System.IO.File]::Open($archivePath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::ReadWrite)
    try {
        $archive = New-Object System.IO.Compression.ZipArchive($zipStream, [System.IO.Compression.ZipArchiveMode]::Create)
        try {
            $index = 0
            foreach ($file in $sourceFiles) {
                $index++
                $rel = Get-RelativePathCompat $RepoRoot $file.FullName
                Add-ZipEntryFromFile $archive $file.FullName $rel
                if (($index % 200) -eq 0) { Write-Host "Archived $index/$($sourceFiles.Count) project files..." }
            }
        } finally { $archive.Dispose() }
    } finally { $zipStream.Dispose() }
    return [ordered]@{
        path = "project/audio_project.zip"
        size_bytes = (Get-Item -LiteralPath $archivePath).Length
        sha256 = Get-FileSha256 $archivePath
        file_count = @($sourceFiles).Count
    }
}

function Copy-ComfyUIParts([string]$PartsDir, [object]$ComfyManifest, [string]$OutputRoot) {
    $items = @()
    foreach ($part in $ComfyManifest.parts) {
        $name = [string]$part.name
        $source = Join-Path $PartsDir $name
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "ComfyUI manifest part missing from parts dir: $source" }
        $component = Add-FileComponent $source $OutputRoot ("comfyui-portable\" + $name)
        if ($component.sha256 -ne ([string]$part.sha256).ToLowerInvariant()) { throw "SHA256 mismatch for ComfyUI part $name" }
        $items += $component
    }
    return [ordered]@{
        archive_name = [string]$ComfyManifest.archive_base_name
        sha256 = ([string]$ComfyManifest.sha256).ToLowerInvariant()
        size_bytes = [int64]$ComfyManifest.size_bytes
        parts = $items
    }
}

function Copy-ImageVideoModels([string]$RepoRoot, [object]$ModelsManifest, [string]$OutputRoot) {
    $modelsRoot = Join-Path $RepoRoot "ComfyUI_windows_portable\ComfyUI\models"
    $files = @()
    $missing = @()
    foreach ($model in $ModelsManifest.models) {
        $targetRel = [string]$model.target_relative_path
        $source = Join-Path $modelsRoot $targetRel
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { $missing += $targetRel; continue }
        $component = Add-FileComponent $source $OutputRoot ("image-video-models\" + ([string]$model.filename))
        if (-not [string]::IsNullOrWhiteSpace([string]$model.sha256) -and $component.sha256 -ne ([string]$model.sha256).ToLowerInvariant()) {
            throw "SHA256 mismatch for local model $targetRel"
        }
        $component.target_relative_path = $targetRel -replace '\\','/'
        $component.name = [string]$model.name
        $files += $component
    }
    return [ordered]@{ files = $files; missing = $missing }
}

if ($Help) { Show-Help; exit 0 }

$repoRoot = Get-RepoRoot
$outputRoot = if ([System.IO.Path]::IsPathRooted($OutputDir)) { $OutputDir } else { Join-Path $repoRoot $OutputDir }
$outputRoot = [System.IO.Path]::GetFullPath($outputRoot)

if ((Test-Path -LiteralPath $outputRoot) -and -not $Force) {
    throw "OutputDir already exists: $outputRoot. Use -Force to update it."
}
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

$components = [ordered]@{}
$missingRecommended = New-Object System.Collections.Generic.List[string]

if (-not $NoProjectArchive) {
    Write-Host "Creating project source archive..."
    $components.project = New-ProjectArchive $repoRoot $outputRoot
}

if (Assert-OptionalFile $PythonInstaller "Python installer") {
    Write-Host "Adding Python installer..."
    $components.python_installer = Add-FileComponent $PythonInstaller $outputRoot "installers\python-3.10.11-amd64.exe"
} else {
    $missingRecommended.Add("Python installer: download python-3.10.11-amd64.exe manually and rerun with -PythonInstaller")
}

if (Assert-OptionalFile $XttsAssetsZip "XTTS assets zip") {
    Write-Host "Adding XTTS assets zip..."
    $components.xtts_assets = Add-FileComponent $XttsAssetsZip $outputRoot "xtts-assets\xtts_assets_v1.zip"
} else {
    $candidate = Join-Path $repoRoot ".installer_cache\xtts_assets_v1.zip"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        Write-Host "Adding XTTS assets zip from .installer_cache..."
        $components.xtts_assets = Add-FileComponent $candidate $outputRoot "xtts-assets\xtts_assets_v1.zip"
    } else {
        $missingRecommended.Add("XTTS assets zip: provide xtts_assets_v1.zip with -XttsAssetsZip")
    }
}

$comfyManifestPath = Join-Path $repoRoot "xtts_api\comfyui_portable_manifest.json"
$comfyManifest = Get-Content -LiteralPath $comfyManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (Assert-OptionalFile $ComfyUIPortableArchive "ComfyUI portable archive") {
    Write-Host "Adding full ComfyUI portable archive..."
    $c = Add-FileComponent $ComfyUIPortableArchive $outputRoot ("comfyui-portable\" + [string]$comfyManifest.archive_base_name)
    $c.archive_path = $c.path
    $components.comfyui_portable = [ordered]@{ archive_path = $c.path; sha256 = $c.sha256; size_bytes = $c.size_bytes }
} elseif (-not [string]::IsNullOrWhiteSpace($ComfyUIPortablePartsDir)) {
    if (-not (Test-Path -LiteralPath $ComfyUIPortablePartsDir -PathType Container)) { throw "ComfyUI parts dir not found: $ComfyUIPortablePartsDir" }
    Write-Host "Adding ComfyUI portable split parts..."
    $components.comfyui_portable = Copy-ComfyUIParts $ComfyUIPortablePartsDir $comfyManifest $outputRoot
} else {
    $candidatePartsDir = Join-Path $repoRoot ".installer_cache\comfyui-portable"
    $haveAll = $true
    foreach ($part in $comfyManifest.parts) { if (-not (Test-Path -LiteralPath (Join-Path $candidatePartsDir ([string]$part.name)) -PathType Leaf)) { $haveAll = $false } }
    if ($haveAll) {
        Write-Host "Adding ComfyUI portable split parts from .installer_cache..."
        $components.comfyui_portable = Copy-ComfyUIParts $candidatePartsDir $comfyManifest $outputRoot
    } else {
        $missingRecommended.Add("ComfyUI portable: provide full archive with -ComfyUIPortableArchive or split parts with -ComfyUIPortablePartsDir")
    }
}

if ($IncludeImageVideoModels) {
    Write-Host "Adding locally-present image/video models listed in manifest..."
    $modelsManifestPath = Join-Path $repoRoot "xtts_api\image_video_models_manifest.json"
    $modelsManifest = Get-Content -LiteralPath $modelsManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $modelResult = Copy-ImageVideoModels $repoRoot $modelsManifest $outputRoot
    $components.image_video_models = [ordered]@{ files = $modelResult.files }
    foreach ($missing in $modelResult.missing) { $missingRecommended.Add("Image/video model missing locally: $missing") }
}

$manifest = [ordered]@{
    schema_version = 1
    created_utc = (Get-Date).ToUniversalTime().ToString("o")
    project = "audio"
    builder = "tools/build_offline_payload.ps1"
    components = $components
    missing_recommended_items = @($missingRecommended)
    notes = @(
        "This manifest references local files inside the offline_payload folder.",
        "The builder does not download large assets; provide them explicitly or from an existing installer cache.",
        "The offline installer verifies SHA256 before using payload files when a checksum is present."
    )
}
$manifestPath = Join-Path $outputRoot "offline_payload_manifest.json"
($manifest | ConvertTo-Json -Depth 20) + "`n" | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host ""
Write-Host "Offline payload written: $outputRoot"
Write-Host "Manifest: $manifestPath"
if ($missingRecommended.Count -gt 0) {
    Write-Host ""
    Write-Host "Missing recommended payload items:"
    foreach ($item in $missingRecommended) { Write-Host "  - $item" }
    Write-Host "The payload is still usable for components that were included, but a fully offline install may fail or skip missing components."
}
exit 0
