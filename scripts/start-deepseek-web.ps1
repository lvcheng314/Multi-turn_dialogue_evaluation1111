param(
    [switch]$NoLaunch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir

function Write-Step {
    param([string]$Message)
    Write-Host "[dialogue-eval] $Message" -ForegroundColor Cyan
}

function Invoke-UvSync {
    $uvScript = Join-Path $projectRoot "scripts\uv.cmd"
    if (-not (Test-Path -LiteralPath $uvScript)) {
        throw "Missing scripts\uv.cmd."
    }

    Write-Step "Syncing Python dependencies with uv..."
    & $uvScript sync
    if ($LASTEXITCODE -ne 0) {
        throw "uv sync failed. Run `cd /d `"$projectRoot`"` then `scripts\uv.cmd sync` and review the output."
    }
}

function Test-EnvValue {
    param(
        [string]$Content,
        [string]$Key
    )

    $match = [regex]::Match($Content, "(?m)^$Key=(.*)$")
    if (-not $match.Success) {
        return $false
    }

    $value = $match.Groups[1].Value.Trim()
    if (-not $value) {
        return $false
    }
    if ($value -like "replace-with-*") {
        return $false
    }
    return $true
}

Push-Location $projectRoot

try {
    $envPath = Join-Path $projectRoot ".env"
    if (-not (Test-Path -LiteralPath $envPath)) {
        throw "Missing .env. Copy .env.example to .env and fill in the DeepSeek configuration first."
    }

    $envContent = Get-Content -LiteralPath $envPath -Raw -Encoding UTF8
    if (-not (Test-EnvValue -Content $envContent -Key "MODEL_PROVIDER")) {
        throw "Missing MODEL_PROVIDER in .env."
    }
    if ($envContent -notmatch "(?m)^MODEL_PROVIDER=deepseek\s*$") {
        throw "MODEL_PROVIDER must be deepseek in .env for this launcher."
    }
    if (-not (Test-EnvValue -Content $envContent -Key "MODEL_BASE_URL")) {
        throw "Missing MODEL_BASE_URL in .env."
    }
    if (-not (Test-EnvValue -Content $envContent -Key "MODEL_API_KEY") -and -not (Test-EnvValue -Content $envContent -Key "DEEPSEEK_API_KEY")) {
        throw "Missing MODEL_API_KEY or DEEPSEEK_API_KEY in .env."
    }

    $venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $venvPython)) {
        Write-Step "Virtual environment not found. It will be created now."
    }
    Invoke-UvSync
    $venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $venvPython)) {
        throw "Python virtual environment is still missing after uv sync."
    }

    $frontendDir = Join-Path $projectRoot "frontend"
    $nodeModulesDir = Join-Path $frontendDir "node_modules"
    if (-not (Test-Path -LiteralPath $nodeModulesDir)) {
        Write-Step "Installing frontend dependencies..."
        Push-Location $frontendDir
        try {
            & npm.cmd install
            if ($LASTEXITCODE -ne 0) {
                throw "npm install failed."
            }
        }
        finally {
            Pop-Location
        }
    }

    Write-Step "Building frontend..."
    Push-Location $frontendDir
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) {
            throw "npm run build failed."
        }
    }
    finally {
        Pop-Location
    }

    if ($NoLaunch) {
        Write-Step "Preflight completed. Skipping app launch."
        return
    }

    Write-Step "Starting local web app..."
    & $venvPython "desktop_app.py"
    if ($LASTEXITCODE -ne 0) {
        throw "desktop_app.py exited with code $LASTEXITCODE."
    }
}
catch {
    Write-Host ""
    Write-Host "[dialogue-eval] Launch failed." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Recommended recovery commands:" -ForegroundColor Yellow
    Write-Host "  cd /d `"$projectRoot`""
    Write-Host "  scripts\uv.cmd sync"
    Write-Host "  cd frontend"
    Write-Host "  npm.cmd run build"
    Write-Host "  cd .."
    Write-Host "  .venv\Scripts\python.exe desktop_app.py"
    exit 1
}
finally {
    Pop-Location
}
