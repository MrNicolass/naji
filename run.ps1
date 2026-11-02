$ErrorActionPreference = "Stop"

$venv = Join-Path $env:LOCALAPPDATA "Naji\.venv"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "Criando ambiente virtual em $venv"
    python -m venv $venv
    & $python -m pip install --upgrade pip --quiet
    & $python -m pip install -r (Join-Path $PSScriptRoot "requirements.txt") --quiet
}

& $python (Join-Path $PSScriptRoot "app.py") @args
