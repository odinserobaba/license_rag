#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".env.final" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env.final"
  set +a
fi

export WEB_DEFAULT_TOP_K="${WEB_DEFAULT_TOP_K:-12}"
export WEB_DEFAULT_OFFICIAL_ONLY="${WEB_DEFAULT_OFFICIAL_ONLY:-true}"
export WEB_DEFAULT_USE_LLM="${WEB_DEFAULT_USE_LLM:-true}"
export WEB_DEFAULT_LLM_BACKEND="${WEB_DEFAULT_LLM_BACKEND:-yandex_openai}"
export WEB_DEFAULT_EMBEDDINGS_RERANK="${WEB_DEFAULT_EMBEDDINGS_RERANK:-true}"
export WEB_DEFAULT_EMBEDDINGS_TOP_N="${WEB_DEFAULT_EMBEDDINGS_TOP_N:-80}"
export WEB_DEFAULT_SHOW_REASONING="${WEB_DEFAULT_SHOW_REASONING:-true}"
export WEB_DEFAULT_MULTI_STEP="${WEB_DEFAULT_MULTI_STEP:-true}"
export WEB_DEFAULT_ANSWER_MODE="${WEB_DEFAULT_ANSWER_MODE:-full}"
export YANDEX_CLOUD_MODEL="${YANDEX_CLOUD_MODEL:-yandexgpt-5-lite/latest}"

exec "./run.sh"
