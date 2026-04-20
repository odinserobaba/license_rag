$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$ChunkSize = 3200
$ChunkOverlap = 700

Write-Host "[1/7] Ensure virtual environment (.venv)"
if (-not (Test-Path ".venv")) {
    py -3 -m venv .venv
}

$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Pip = Join-Path $Root ".venv\Scripts\pip.exe"

Write-Host "[2/7] Install Python dependencies"
& $Pip install --upgrade pip | Out-Null
& $Pip install -r requirements.txt | Out-Null

Write-Host "[3/7] Rename source files in doc/"
& $Py scripts/rename_all_docs.py

Write-Host "[4/7] Prepare RTF corpus"
& $Py scripts/prepare_corpus.py `
    --input-dir doc `
    --txt-dir processed/clean_txt `
    --jsonl processed/cleaned_docs_rtf.jsonl

Write-Host "[5/7] Prepare DOC/DOCX/TXT/MD/PDF corpus"
& $Py scripts/prepare_doc_files.py `
    --input-dir doc `
    --txt-dir processed/clean_txt `
    --jsonl processed/extra_docs.jsonl

Write-Host "[6/7] Merge corpora and chunk"
& $Py -c @"
from pathlib import Path
rtf = Path("processed/cleaned_docs_rtf.jsonl")
extra = Path("processed/extra_docs.jsonl")
merged = Path("processed/cleaned_docs.jsonl")
with merged.open("w", encoding="utf-8") as out:
    if rtf.exists():
        out.write(rtf.read_text(encoding="utf-8"))
    if extra.exists():
        extra_text = extra.read_text(encoding="utf-8")
        if extra_text:
            if not extra_text.endswith("\n"):
                extra_text += "\n"
            out.write(extra_text)
print(f"Merged corpus: {merged}")
"@

& $Py scripts/chunk_corpus.py `
    --input-jsonl processed/cleaned_docs.jsonl `
    --output-jsonl processed/chunks.jsonl `
    --chunk-size $ChunkSize `
    --overlap $ChunkOverlap

Write-Host "[7/7] Build lexical index"
& $Py scripts/build_index.py `
    --chunks-jsonl processed/chunks.jsonl `
    --output processed/lexical_index.json

Write-Host ""
Write-Host "Build complete."
Write-Host "Run app with: .\run_windows.ps1"
