$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Get-ChildItem "$repo/*.ps1", "$repo/tools/*.ps1" | ForEach-Object {
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$errors) | Out-Null
    if ($errors) { throw ($errors | Out-String) }
}
Write-Output 'PowerShell parsing OK'
