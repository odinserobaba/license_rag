$ErrorActionPreference = "Stop"

param(
    [Parameter(Mandatory = $true)]
    [string]$GgufPath,
    [string]$ModelName = "qwen3-8b-gguf"
)

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Error "Ollama not found. Install Ollama first: https://ollama.com/download"
}

if (-not (Test-Path $GgufPath)) {
    Write-Error "GGUF file not found: $GgufPath"
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Modelfile = Join-Path $Root "Modelfile.qwen3-8b-gguf"
@"
FROM $GgufPath
PARAMETER temperature 0.1
PARAMETER repeat_penalty 1.1
"@ | Set-Content -Path $Modelfile -Encoding UTF8

ollama create $ModelName -f $Modelfile

Write-Host ""
Write-Host "Model imported: $ModelName"
Write-Host "Set for app:"
Write-Host "  `$env:OLLAMA_MODEL = '$ModelName'"
Write-Host "Then run:"
Write-Host "  .\run_windows.ps1"
