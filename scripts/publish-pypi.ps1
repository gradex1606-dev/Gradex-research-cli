# Manual PyPI publish (if GitHub Actions trusted publishing is not set up yet)
# Prerequisites: pip install build twine
# Set token: $env:TWINE_USERNAME = "__token__"; $env:TWINE_PASSWORD = "pypi-..."
#
# Usage from repo root:
#   .\scripts\publish-pypi.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not $env:TWINE_PASSWORD) {
    Write-Host "Set PyPI API token first:" -ForegroundColor Red
    Write-Host '  $env:TWINE_USERNAME = "__token__"' -ForegroundColor Yellow
    Write-Host '  $env:TWINE_PASSWORD = "pypi-..."' -ForegroundColor Yellow
    exit 1
}

python -m pytest tests/ -q --tb=no
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (Test-Path dist) { Remove-Item -Recurse -Force dist }
python -m build
python -m twine upload dist/*

Write-Host ""
Write-Host "Published. Verify: https://pypi.org/project/gradex/" -ForegroundColor Green
