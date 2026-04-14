#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

CHUNK_SIZE=1700
CHUNK_OVERLAP=260

echo "[1/7] Ensure virtual environment"
if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

echo "[2/7] Install Python dependencies"
".venv/bin/pip" install --upgrade pip >/dev/null
".venv/bin/pip" install -r requirements.txt >/dev/null

echo "[3/7] Rename all source files in doc/"
".venv/bin/python" scripts/rename_all_docs.py

echo "[4/7] Prepare RTF corpus"
".venv/bin/python" scripts/prepare_corpus.py \
  --input-dir doc \
  --txt-dir processed/clean_txt \
  --jsonl processed/cleaned_docs_rtf.jsonl

echo "[5/7] Prepare DOC/DOCX corpus (if any)"
".venv/bin/python" scripts/prepare_doc_files.py \
  --input-dir doc \
  --txt-dir processed/clean_txt \
  --jsonl processed/extra_docs.jsonl

echo "[6/7] Merge corpora and chunk"
".venv/bin/python" - <<'PY'
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
PY

".venv/bin/python" scripts/chunk_corpus.py \
  --input-jsonl processed/cleaned_docs.jsonl \
  --output-jsonl processed/chunks.jsonl \
  --chunk-size "$CHUNK_SIZE" \
  --overlap "$CHUNK_OVERLAP"

echo "[7/7] Build lexical index"
".venv/bin/python" scripts/build_index.py \
  --chunks-jsonl processed/chunks.jsonl \
  --output processed/lexical_index.json

echo
echo "Build complete."
echo "Run app with: ./run.sh"
