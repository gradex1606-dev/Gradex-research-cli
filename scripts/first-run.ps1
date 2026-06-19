# GradeX first-run walkthrough (PowerShell)
# Usage:
#   $env:GROQ_API_KEY = "gsk_your_key_here"
#   .\scripts\first-run.ps1
#
# Optional flags:
#   -RepoPath demo\payment-service   (default)
#   -SkipOptimize                    (discover + dashboard only)

param(
    [string]$RepoPath = "demo\payment-service",
    [switch]$SkipOptimize
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Target = Join-Path $Root $RepoPath

if (-not $env:GROQ_API_KEY) {
    Write-Host ""
    Write-Host "ERROR: Set your Groq API key first:" -ForegroundColor Red
    Write-Host '  $env:GROQ_API_KEY = "gsk_your_key_here"' -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

Write-Host "`n=== GradeX first-run walkthrough ===" -ForegroundColor Cyan
Write-Host "Repo: $Target`n"

Set-Location $Target

if (-not (Test-Path .git)) {
    Write-Host "[1/6] git init" -ForegroundColor Green
    git init | Out-Null
} else {
    Write-Host "[1/6] git repo OK" -ForegroundColor Green
}

$Gradex = Join-Path $Root ".venv\Scripts\gradex.exe"
if (-not (Test-Path $Gradex)) {
    Write-Host "ERROR: Run 'uv sync --all-extras' in $Root first." -ForegroundColor Red
    exit 1
}

Write-Host "[2/6] pip install -r requirements.txt (if needed)" -ForegroundColor Green
pip install -q -r requirements.txt

Write-Host "[3/6] gradex discover (from demo repo)" -ForegroundColor Green
& $Gradex discover "make parse_payment_ids faster" --provider groq --api-key $env:GROQ_API_KEY
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n[4/6] Verify benchmark prints a number:" -ForegroundColor Green
python .gradex\benchmark.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Benchmark failed — fix .gradex\benchmark.py then re-run discover." -ForegroundColor Red
    exit 1
}

Write-Host "`n[5/6] Start dashboard (new terminal):" -ForegroundColor Green
Write-Host "  cd $Target" -ForegroundColor Yellow
Write-Host "  $Gradex dashboard" -ForegroundColor Yellow

if ($SkipOptimize) {
    Write-Host "`nSkipped optimize (-SkipOptimize). When ready:" -ForegroundColor Cyan
    Write-Host "  $Gradex optimize --provider groq --api-key `$env:GROQ_API_KEY --subagents 2 --budget 1 --stall 2" -ForegroundColor Yellow
    exit 0
}

Write-Host "`n[6/6] gradex optimize (small demo: 2 agents, 1 round each)" -ForegroundColor Green
& $Gradex optimize --provider groq --api-key $env:GROQ_API_KEY --subagents 2 --budget 1 --stall 2

Write-Host "`nDone. Review results:" -ForegroundColor Cyan
Write-Host "  $Gradex stats" -ForegroundColor Yellow
Write-Host "  $Gradex dashboard" -ForegroundColor Yellow
