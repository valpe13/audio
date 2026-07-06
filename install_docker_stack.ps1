#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$RepoUrl = "https://github.com/valpe13/audio.git",
    [string]$Branch = "main",
    [string]$InstallRoot = (Get-Location).Path,
    [string]$ProjectDir = "",
    [switch]$UseGpu,
    [switch]$PreloadXtts,
    [switch]$UpdateProject,
    [switch]$SkipDockerInstall,
    [switch]$NoStartBrowser,
    [switch]$NoBuild,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
}

$DockerInstallerUrl = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Info {
    param([string]$Message)
    Write-Host "    $Message"
}

function Write-Warn {
    param([string]$Message)
    Write-Host "    WARNING: $Message" -ForegroundColor Yellow
}

function Invoke-External {
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [Parameter(Mandatory=$true)][string[]]$Arguments,
        [string]$WorkingDirectory = (Get-Location).Path,
        [switch]$AllowFailure
    )

    Write-Host ("> {0} {1}" -f $FilePath, ($Arguments -join " "))
    if ($DryRun) {
        return 0
    }

    Push-Location $WorkingDirectory
    try {
        & $FilePath @Arguments
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
    }

    if ($code -ne 0 -and -not $AllowFailure) {
        throw "Command failed with exit code $code`: $FilePath $($Arguments -join ' ')"
    }
    return $code
}

function Get-DockerExe {
    $candidates = @()
    $cmd = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        $candidates += $cmd.Source
    }
    $candidates += @(
        "$env:ProgramFiles\Docker\Docker\resources\bin\docker.exe",
        "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return $null
}

function Get-DockerDesktopExe {
    $candidates = @(
        "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
        "$env:ProgramFiles\Docker\Docker\frontend\Docker Desktop.exe",
        "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe",
        "$env:LOCALAPPDATA\Programs\DockerDesktop\frontend\Docker Desktop.exe"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return $null
}

function Test-DockerServerReady {
    $docker = Get-DockerExe
    if (-not $docker) {
        return $false
    }
    if ($DryRun) {
        return $true
    }
    & $docker version --format "{{.Server.Version}}" *> $null
    return ($LASTEXITCODE -eq 0)
}

function Install-DockerDesktopIfNeeded {
    Write-Step "Checking Docker Desktop"

    if (Test-DockerServerReady) {
        Write-Info "Docker engine is already running."
        return
    }

    $desktopExe = Get-DockerDesktopExe
    if (-not $desktopExe) {
        if ($SkipDockerInstall) {
            throw "Docker Desktop is not installed and -SkipDockerInstall was supplied."
        }

        Write-Info "Docker Desktop was not found. Downloading official installer..."
        $cacheDir = Join-Path $env:TEMP "audio-docker-stack-installer"
        $installerPath = Join-Path $cacheDir "DockerDesktopInstaller.exe"

        if ($DryRun) {
            Write-Info "[dry-run] Would download $DockerInstallerUrl to $installerPath"
        } else {
            New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
            Invoke-WebRequest -Uri $DockerInstallerUrl -OutFile $installerPath
        }

        Write-Info "Installing Docker Desktop in per-user WSL 2 mode."
        Write-Info "Windows may ask for permission or require a reboot if WSL is not ready."
        if (-not $DryRun) {
            $process = Start-Process -FilePath $installerPath `
                -ArgumentList @("install", "--user", "--quiet", "--accept-license", "--backend=wsl-2") `
                -Wait -PassThru
            if ($process.ExitCode -notin @(0, 3010, 1641)) {
                throw "Docker Desktop installer failed with exit code $($process.ExitCode)."
            }
            if ($process.ExitCode -in @(3010, 1641)) {
                throw "Docker Desktop installation requires a Windows reboot. Reboot and run install_docker_stack.cmd again."
            }
        }

        $env:Path = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin;$env:ProgramFiles\Docker\Docker\resources\bin;$env:Path"
        $desktopExe = Get-DockerDesktopExe
    }

    if ($DryRun) {
        Write-Info "[dry-run] Would start Docker Desktop and wait for the engine."
        return
    }

    if (-not $desktopExe -and -not $DryRun) {
        throw "Docker Desktop executable was not found after installation."
    }

    if (-not (Test-DockerServerReady)) {
        Write-Info "Starting Docker Desktop..."
        if (-not $DryRun) {
            Start-Process -FilePath $desktopExe -WindowStyle Minimized | Out-Null
        }
    }

    Write-Info "Waiting for Docker engine..."
    $deadline = (Get-Date).AddMinutes(15)
    do {
        if (Test-DockerServerReady) {
            Write-Info "Docker engine is ready."
            return
        }
        Start-Sleep -Seconds 5
        Write-Host "." -NoNewline
    } while ((Get-Date) -lt $deadline)
    Write-Host ""
    throw "Docker Desktop did not become ready in 15 minutes. Open Docker Desktop, finish its setup, then run this installer again."
}

function Test-ProjectDirectory {
    param([string]$Path)
    return (
        (Test-Path -LiteralPath (Join-Path $Path "Dockerfile")) -and
        (Test-Path -LiteralPath (Join-Path $Path "compose.yml")) -and
        (Test-Path -LiteralPath (Join-Path $Path "requirements-docker.txt"))
    )
}

function Get-GitExe {
    $cmd = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    return $null
}

function Get-GitHubZipUrl {
    param([string]$Url, [string]$RefName)
    if ($Url -match "^https://github\.com/([^/]+)/([^/\.]+)(?:\.git)?$") {
        return "https://github.com/$($Matches[1])/$($Matches[2])/archive/refs/heads/$RefName.zip"
    }
    throw "Cannot derive GitHub ZIP URL from RepoUrl: $Url. Install Git or pass a GitHub HTTPS repo URL."
}

function Download-ProjectZip {
    param([string]$TargetPath)
    $zipUrl = Get-GitHubZipUrl -Url $RepoUrl -RefName $Branch
    $tmpRoot = Join-Path $env:TEMP ("audio-repo-" + [guid]::NewGuid().ToString("N"))
    $zipPath = Join-Path $tmpRoot "repo.zip"
    $extractPath = Join-Path $tmpRoot "extract"

    Write-Info "Downloading project ZIP from $zipUrl"
    if ($DryRun) {
        Write-Info "[dry-run] Would expand ZIP into $TargetPath"
        return
    }

    New-Item -ItemType Directory -Force -Path $tmpRoot, $extractPath | Out-Null
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath
    Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force
    $inner = Get-ChildItem -Path $extractPath -Directory | Select-Object -First 1
    if (-not $inner) {
        throw "Downloaded ZIP did not contain a project directory."
    }
    Move-Item -LiteralPath $inner.FullName -Destination $TargetPath
}

function Ensure-Project {
    Write-Step "Preparing project files"

    $scriptDir = Split-Path -Parent $PSCommandPath
    if (-not $ProjectDir -and (Test-ProjectDirectory $scriptDir)) {
        Write-Info "Using project next to installer: $scriptDir"
        return (Resolve-Path -LiteralPath $scriptDir).Path
    }

    if ($ProjectDir) {
        $target = $ProjectDir
    } else {
        $target = Join-Path $InstallRoot "audio"
    }
    $target = [System.IO.Path]::GetFullPath($target)

    if (Test-ProjectDirectory $target) {
        Write-Info "Using existing project: $target"
        if ($UpdateProject -and (Test-Path -LiteralPath (Join-Path $target ".git")) -and (Get-GitExe)) {
            Write-Info "Updating existing git checkout with git pull --ff-only."
            Invoke-External -FilePath (Get-GitExe) -Arguments @("pull", "--ff-only") -WorkingDirectory $target -AllowFailure | Out-Null
        } elseif ($UpdateProject) {
            Write-Warn "Project update was requested, but this folder is not a git checkout or Git is missing."
        }
        return $target
    }

    if (Test-Path -LiteralPath $target) {
        $hasFiles = (Get-ChildItem -LiteralPath $target -Force | Select-Object -First 1) -ne $null
        if ($hasFiles) {
            throw "Target folder exists but is not this project: $target"
        }
        if (-not $DryRun) {
            Remove-Item -LiteralPath $target -Force
        }
    }

    $parent = Split-Path -Parent $target
    if (-not $DryRun) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }

    $git = Get-GitExe
    if ($git) {
        Write-Info "Cloning $RepoUrl ($Branch) into $target"
        Invoke-External -FilePath $git -Arguments @("clone", "--branch", $Branch, "--single-branch", $RepoUrl, $target) -WorkingDirectory $parent | Out-Null
    } else {
        Write-Warn "Git was not found; using GitHub ZIP download fallback."
        Download-ProjectZip -TargetPath $target
    }

    if (-not $DryRun -and -not (Test-ProjectDirectory $target)) {
        throw "Downloaded project is missing Docker files: $target"
    }

    return $target
}

function Read-DotEnv {
    param([string]$Path)
    $data = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        return $data
    }
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trim = $line.Trim()
        if (-not $trim -or $trim.StartsWith("#") -or $trim -notmatch "=") {
            continue
        }
        $parts = $trim.Split("=", 2)
        $data[$parts[0].Trim()] = $parts[1].Trim().Trim('"')
    }
    return $data
}

function Wait-HttpOk {
    param([string]$Uri, [int]$TimeoutSeconds = 180)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 10
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                return
            }
        } catch {
        }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for $Uri"
}

function Ensure-EnvFile {
    param([string]$ProjectPath)
    $envPath = Join-Path $ProjectPath ".env"
    $examplePath = Join-Path $ProjectPath "docker.env.example"
    if (-not (Test-Path -LiteralPath $envPath) -and (Test-Path -LiteralPath $examplePath)) {
        Write-Info "Creating .env from docker.env.example"
        if (-not $DryRun) {
            Copy-Item -LiteralPath $examplePath -Destination $envPath
        }
    }
}

function Start-AudioStack {
    param([string]$ProjectPath)

    Write-Step "Building and starting Docker stack"
    $docker = Get-DockerExe
    if (-not $docker) {
        throw "docker.exe was not found after Docker Desktop setup."
    }

    Ensure-EnvFile -ProjectPath $ProjectPath

    $composeFiles = @()
    if ($UseGpu) {
        $composeFiles += @("-f", "compose.yml", "-f", "compose.gpu.yml")
    }

    Invoke-External -FilePath $docker -Arguments (@("compose") + $composeFiles + @("config", "--quiet")) -WorkingDirectory $ProjectPath | Out-Null

    $upArgs = @("compose") + $composeFiles + @("up")
    if ($NoBuild) {
        $upArgs += "--no-build"
    } else {
        $upArgs += "--build"
    }
    $upArgs += "-d"
    Invoke-External -FilePath $docker -Arguments $upArgs -WorkingDirectory $ProjectPath | Out-Null
}

function Warmup-Silero {
    param([int]$Port)
    Write-Step "Warming up Silero model"
    $payload = @{
        text = "Привет. Это проверка."
        speaker = "baya"
        sample_rate = 48000
        return_file = $false
        realism_enabled = $false
        seed = 42
    } | ConvertTo-Json -Compress

    if ($DryRun) {
        Write-Info "[dry-run] Would POST to http://localhost:$Port/v1/tts"
        return
    }

    try {
        Invoke-RestMethod -Method Post -Uri "http://localhost:$Port/v1/tts" `
            -ContentType "application/json; charset=utf-8" `
            -Body ([Text.Encoding]::UTF8.GetBytes($payload)) `
            -TimeoutSec 240 | Out-Null
        Write-Info "Silero model is downloaded and generated a smoke-test WAV."
    } catch {
        Write-Warn "Silero warmup failed: $($_.Exception.Message). The service is still installed; check docker compose logs."
    }
}

function Preload-XttsModel {
    param([string]$ProjectPath)
    Write-Step "Preloading XTTS model"
    $docker = Get-DockerExe
    $code = "from TTS.api import TTS; TTS('tts_models/multilingual/multi-dataset/xtts_v2', progress_bar=True, gpu=False); print('XTTS model preload complete')"
    Invoke-External -FilePath $docker -Arguments @("compose", "exec", "-T", "audio-stack", "python", "-c", $code) -WorkingDirectory $ProjectPath | Out-Null
}

function Verify-Stack {
    param([string]$ProjectPath)
    Write-Step "Verifying services"

    $envData = Read-DotEnv -Path (Join-Path $ProjectPath ".env")
    $xttsPort = if ($envData["AUDIO_XTTS_PORT"]) { [int]$envData["AUDIO_XTTS_PORT"] } else { 7870 }
    $sileroPort = if ($envData["AUDIO_SILERO_PORT"]) { [int]$envData["AUDIO_SILERO_PORT"] } else { 7866 }
    $fishPort = if ($envData["AUDIO_FISH_PORT"]) { [int]$envData["AUDIO_FISH_PORT"] } else { 7865 }

    if (-not $DryRun) {
        Wait-HttpOk -Uri "http://localhost:$xttsPort/api/health" -TimeoutSeconds 240
        Wait-HttpOk -Uri "http://localhost:$sileroPort/health" -TimeoutSeconds 120
        Wait-HttpOk -Uri "http://localhost:$fishPort/health" -TimeoutSeconds 120
    }

    Write-Info "XTTS Studio: http://localhost:$xttsPort/studio/"
    Write-Info "Silero API:  http://localhost:$sileroPort/health"
    Write-Info "Fish API:    http://localhost:$fishPort/health"

    Warmup-Silero -Port $sileroPort
    if ($PreloadXtts) {
        Preload-XttsModel -ProjectPath $ProjectPath
    }

    if (-not $NoStartBrowser -and -not $DryRun) {
        Start-Process "http://localhost:$xttsPort/studio/" | Out-Null
    }
}

try {
    if (-not $IsWindows -and $PSVersionTable.PSEdition -eq "Core") {
        throw "This installer is for Windows. On Linux/macOS, use docker compose up --build."
    }

    Install-DockerDesktopIfNeeded
    $projectPath = Ensure-Project
    Start-AudioStack -ProjectPath $projectPath
    Verify-Stack -ProjectPath $projectPath

    Write-Step "Done"
    Write-Info "Project path: $projectPath"
    Write-Info "Stop later with: docker compose down"
    exit 0
} catch {
    Write-Host ""
    Write-Host "INSTALL FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "If Docker Desktop asked for a reboot, reboot Windows and run install_docker_stack.cmd again."
    Write-Host "If the failure is during Docker build, run: docker compose logs --tail=200"
    exit 1
}
