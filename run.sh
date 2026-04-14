#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -f "processed/lexical_index.json" ]]; then
  echo "Index not found: processed/lexical_index.json"
  echo "Run build first: ./build.sh"
  exit 1
fi

if [[ ! -d ".venv" ]]; then
  echo "Virtual environment not found: .venv"
  echo "Run build first: ./build.sh"
  exit 1
fi

exec ".venv/bin/python" app.py
