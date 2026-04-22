$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path "processed/lexical_index.json")) {
    Write-Error "Index not found: processed/lexical_index.json. Run .\build_windows.ps1 first."
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Error "Virtual environment missing. Run .\build_windows.ps1 first."
}

& ".venv\Scripts\python.exe" app.py
