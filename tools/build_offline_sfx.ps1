[CmdletBinding()]
param(
    [string]$PayloadDir = "dist\offline_payload",
    [string]$OutputExe = "dist\AudioXTTS_Offline_Setup.exe",
    [string]$SevenZipExe = "",
    [string]$SfxModule = "",
    [switch]$Force,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Show-Help {
    Write-Host "Build a 7-Zip SFX installer from an existing offline payload."
    Write-Host ""
    Write-Host "Usage: powershell -File tools\build_offline_sfx.ps1 [options]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -PayloadDir <path>   Existing offline_payload folder. Default: dist\offline_payload"
    Write-Host "  -OutputExe <path>    Output SFX exe. Default: dist\AudioXTTS_Offline_Setup.exe"
    Write-Host "  -SevenZipExe <path>  Optional explicit 7z.exe path."
    Write-Host "  -SfxModule <path>    Optional explicit 7z SFX module path, for example 7z.sfx or 7zSD.sfx."
    Write-Host "  -Force               Replace existing output/archive staging files."
}

function Find-7ZipExe([string]$Explicit) {
    if (-not [string]::IsNullOrWhiteSpace($Explicit)) {
        if (Test-Path -LiteralPath $Explicit -PathType Leaf) { return (Resolve-Path -LiteralPath $Explicit).Path }
        throw "7z.exe not found: $Explicit"
    }
    $candidates = @(
        (Join-Path $env:ProgramFiles "7-Zip\7z.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "7-Zip\7z.exe")
    )
    foreach ($candidate in $candidates) { if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate } }
    $cmd = Get-Command 7z.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "7z.exe was not found. Install 7-Zip or pass -SevenZipExe."
}

function Find-SfxModule([string]$Explicit, [string]$SevenZipPath) {
    if (-not [string]::IsNullOrWhiteSpace($Explicit)) {
        if (Test-Path -LiteralPath $Explicit -PathType Leaf) { return (Resolve-Path -LiteralPath $Explicit).Path }
        throw "SFX module not found: $Explicit"
    }
    $sevenZipDir = Split-Path -Parent $SevenZipPath
    $candidates = @(
        (Join-Path $sevenZipDir "7z.sfx"),
        (Join-Path $sevenZipDir "7zCon.sfx"),
        (Join-Path $sevenZipDir "7zSD.sfx"),
        (Join-Path $PSScriptRoot "7z.sfx"),
        (Join-Path $PSScriptRoot "7zSD.sfx")
    )
    foreach ($candidate in $candidates) { if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate } }
    throw "7-Zip SFX module was not found. Install the 7-Zip Extra package or pass -SfxModule."
}

if ($Help) { Show-Help; exit 0 }

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$payloadRoot = if ([System.IO.Path]::IsPathRooted($PayloadDir)) { $PayloadDir } else { Join-Path $repoRoot $PayloadDir }
$payloadRoot = [System.IO.Path]::GetFullPath($payloadRoot)
$outputExePath = if ([System.IO.Path]::IsPathRooted($OutputExe)) { $OutputExe } else { Join-Path $repoRoot $OutputExe }
$outputExePath = [System.IO.Path]::GetFullPath($outputExePath)

if (-not (Test-Path -LiteralPath $payloadRoot -PathType Container)) { throw "PayloadDir not found: $payloadRoot" }
if (-not (Test-Path -LiteralPath (Join-Path $payloadRoot "offline_payload_manifest.json") -PathType Leaf)) { throw "offline_payload_manifest.json not found in PayloadDir: $payloadRoot" }

$sevenZip = Find-7ZipExe $SevenZipExe
$sfx = Find-SfxModule $SfxModule $sevenZip
$distDir = Split-Path -Parent $outputExePath
New-Item -ItemType Directory -Path $distDir -Force | Out-Null
if ((Test-Path -LiteralPath $outputExePath) -and -not $Force) { throw "Output exe already exists: $outputExePath. Use -Force to replace it." }

$stage = Join-Path $distDir "offline_sfx_stage"
if (Test-Path -LiteralPath $stage) {
    if (-not $Force) { throw "SFX staging folder already exists: $stage. Use -Force to replace/update it." }
    Remove-Item -LiteralPath $stage -Recurse -Force
}
New-Item -ItemType Directory -Path $stage -Force | Out-Null

Copy-Item -LiteralPath (Join-Path $repoRoot "install_offline.cmd") -Destination (Join-Path $stage "install_offline.cmd") -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "install_offline.ps1") -Destination (Join-Path $stage "install_offline.ps1") -Force
if (Test-Path -LiteralPath (Join-Path $repoRoot "README_OFFLINE_INSTALL.md") -PathType Leaf) {
    Copy-Item -LiteralPath (Join-Path $repoRoot "README_OFFLINE_INSTALL.md") -Destination (Join-Path $stage "README_OFFLINE_INSTALL.md") -Force
}
Copy-Item -LiteralPath $payloadRoot -Destination (Join-Path $stage "offline_payload") -Recurse -Force

$archivePath = Join-Path $distDir "AudioXTTS_Offline_Setup.7z"
$configPath = Join-Path $distDir "AudioXTTS_Offline_Setup.sfxconfig.txt"
if (Test-Path -LiteralPath $archivePath) {
    if (-not $Force) { throw "Archive already exists: $archivePath. Use -Force to replace it." }
    Remove-Item -LiteralPath $archivePath -Force
}
if (Test-Path -LiteralPath $outputExePath) { Remove-Item -LiteralPath $outputExePath -Force }

$config = @"
;!@Install@!UTF-8!
Title="Audio XTTS Offline Installer"
BeginPrompt="This self-extracting installer contains the offline payload and will run install_offline.cmd."
RunProgram="install_offline.cmd -FromSfx"
;!@InstallEnd@!
"@
$config | Set-Content -LiteralPath $configPath -Encoding UTF8

Push-Location $stage
try {
    & $sevenZip a -t7z -mx=7 $archivePath *
    if ($LASTEXITCODE -ne 0) { throw "7z archive creation failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

$out = [System.IO.File]::Open($outputExePath, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write)
try {
    foreach ($piece in @($sfx, $configPath, $archivePath)) {
        $in = [System.IO.File]::OpenRead($piece)
        try { $in.CopyTo($out) } finally { $in.Dispose() }
    }
} finally { $out.Dispose() }

Write-Host "SFX installer written: $outputExePath"
Write-Host "7-Zip executable:      $sevenZip"
Write-Host "SFX module:            $sfx"
Write-Host "Staging folder:        $stage"
Write-Host "Archive:               $archivePath"
Write-Host "No payload downloads were performed."
exit 0
