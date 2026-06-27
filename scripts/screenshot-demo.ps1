# GradeX screenshot walkthrough for X / social posts (PowerShell)
# Run from repo root after: pip install -e ".[dev]"
#
# Usage:
#   .\scripts\screenshot-demo.ps1              # interactive setup + models
#   .\scripts\screenshot-demo.ps1 -WithDiscover  # also runs discover (needs API key)
#   .\scripts\screenshot-demo.ps1 -WithReport    # also opens HTML report (needs prior run)

param(
    [switch]$WithDiscover,
    [switch]$WithReport,
    [string]$Provider = "",
    [string]$ApiKey = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host ""
Write-Host "=== GradeX screenshot demo ===" -ForegroundColor Cyan
Write-Host "Tip: Win+Shift+S to capture each step. Redact API keys before posting.`n"

$configPath = Join-Path $env:USERPROFILE ".gradex\config.toml"
if (Test-Path $configPath) {
    Write-Host "[1] Existing config found at $configPath" -ForegroundColor Yellow
    Write-Host "    Delete it first for a fresh install wizard, or run configure to overwrite.`n"
} else {
    Write-Host "[1] No saved config — configure will show full first-time setup.`n" -ForegroundColor Green
}

Write-Host "[2] gradex configure  (SCREENSHOT: provider + model + saved message)" -ForegroundColor Green
Write-Host "    Press Enter when ready..."
Read-Host | Out-Null
gradex configure
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "[3] gradex models --provider openrouter  (SCREENSHOT: curated models)" -ForegroundColor Green
Write-Host "    Press Enter when ready..."
Read-Host | Out-Null
gradex models --provider openrouter

Write-Host ""
Write-Host "[4] gradex --version" -ForegroundColor Green
gradex --version

if ($WithDiscover) {
    $key = $ApiKey
    if (-not $key) { $key = $env:GROQ_API_KEY }
    if (-not $key) { $key = $env:OPENROUTER_API_KEY }
    if (-not $key) {
        Write-Host ""
        Write-Host "Set GROQ_API_KEY or OPENROUTER_API_KEY, or pass -ApiKey" -ForegroundColor Red
        exit 1
    }
    $prov = if ($Provider) { $Provider } else { "groq" }
    Write-Host ""
    Write-Host "[5] gradex discover  (SCREENSHOT: discover output)" -ForegroundColor Green
    Write-Host "    Press Enter when ready..."
    Read-Host | Out-Null
    gradex discover "make this repo faster" --provider $prov --api-key $key
}

if ($WithReport) {
    Write-Host ""
    Write-Host "[6] gradex report  (SCREENSHOT: browser with gradex-report.html)" -ForegroundColor Green
    Write-Host "    Press Enter when ready..."
    Read-Host | Out-Null
    gradex report -o gradex-report.html
    if (Test-Path gradex-report.html) {
        Start-Process gradex-report.html
    }
}

Write-Host ""
Write-Host "Done. Suggested X post: OpenRouter + configure + report shipped in v0.1.1" -ForegroundColor Cyan
Write-Host "GitHub: https://github.com/gradex1606-dev/Gradex-research-cli`n"
