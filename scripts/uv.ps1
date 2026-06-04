param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $UvArgs
)

$OutputEncoding = [System.Text.UTF8Encoding]::new()
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot

if (-not $env:UV_CACHE_DIR) {
    $env:UV_CACHE_DIR = Join-Path $projectRoot ".uv-cache"
}

$uvCommand = Get-Command uv -ErrorAction SilentlyContinue

if (-not $uvCommand) {
    Write-Error @"
uv was not found on PATH.

Install uv, then rerun this command:
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
"@
}

& $uvCommand.Source @UvArgs
exit $LASTEXITCODE
