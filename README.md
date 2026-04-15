# EGAIS Normatives Assistant (Local)

Локальный проект для поиска по нормативным документам ЕГАИС:
- подготовка корпуса из `doc/*.rtf` (MHTML внутри),
- очистка и чанкинг,
- офлайн лексический индекс (TF-IDF),
- локальный веб-чат на Gradio.

Подробная разбитая документация:

- `docs/readme_parts/00_INDEX.md`

## Быстрый запуск (5 минут)

### Вариант A: одной командой (рекомендуется)

```bash
chmod +x build.sh run.sh
./build.sh
./run.sh
```

Скрипт `build.sh`:
- поднимет `.venv`,
- установит зависимости,
- обработает `doc/*.rtf`,
- дополнительно обработает `doc/*.doc` и `doc/*.docx` (если есть),
- дополнительно обработает `doc/*.doc`, `doc/*.docx`, `doc/*.txt`, `doc/*.md`, `doc/*.pdf` (если есть),
- соберет `processed/lexical_index.json`.

Текущие параметры retrieval:
- `chunk_size=2200`
- `overlap=320`
- `top_k` в интерфейсе по умолчанию `6` (регулируется слайдером).
- включен режим `Только официальные НПА` (по умолчанию ON).

### Вариант B: вручную по шагам

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

python3 scripts/rename_all_docs.py
python3 scripts/prepare_corpus.py --input-dir doc --txt-dir processed/clean_txt --jsonl processed/cleaned_docs_rtf.jsonl
python3 scripts/prepare_doc_files.py --input-dir doc --txt-dir processed/clean_txt --jsonl processed/extra_docs.jsonl
python3 - <<'PY'
from pathlib import Path
rtf=Path("processed/cleaned_docs_rtf.jsonl")
extra=Path("processed/extra_docs.jsonl")
merged=Path("processed/cleaned_docs.jsonl")
with merged.open("w", encoding="utf-8") as out:
    if rtf.exists():
        out.write(rtf.read_text(encoding="utf-8"))
    if extra.exists():
        out.write(extra.read_text(encoding="utf-8"))
print("merged:", merged)
PY
python3 scripts/chunk_corpus.py --input-jsonl processed/cleaned_docs.jsonl --output-jsonl processed/chunks.jsonl --chunk-size 2200 --overlap 320
python3 scripts/build_index.py --chunks-jsonl processed/chunks.jsonl --output processed/lexical_index.json
```

### Запуск веб-чата

```bash
./run.sh
```

Откройте в браузере:
- http://127.0.0.1:7860

## Что умеет текущая версия

- Находит релевантные фрагменты по вопросу.
- Возвращает источники по метаданным документа (без имен файлов).
- Работает полностью локально.
- Поддерживает гибридный retrieval:
  - этап 1: TF-IDF поиск по всему индексу,
  - этап 2 (опционально): embeddings re-rank top-N кандидатов через Yandex Cloud API
    с кэшированием в `processed/embedding_cache.json`.

## Две версии LLM-оценки

### 1) Colab (T4) версия

- Ноутбук: `notebooks/llm_eval_colab_t4.ipynb`
- В Colab загрузите:
  - `processed/lexical_index.json`
  - `data/test/eval_questions.jsonl`
- Выход:
  - `eval_colab_t4.jsonl`

### 2) Локальная версия (Ollama)

```bash
python3 scripts/llm_eval_local.py \
  --index processed/lexical_index.json \
  --questions data/test/eval_questions.jsonl \
  --top-k 6 \
  --model qwen2.5:7b-instruct \
  --output processed/eval_local_llm.jsonl
```

Требуется запущенный локальный Ollama на `http://127.0.0.1:11434`.

## Embeddings re-rank (гибридный retrieval)

В UI доступны поля:
- `Embeddings re-rank (гибридный retrieval)` — включает второй этап ранжирования.
- `Embeddings re-rank top-N кандидатов` — сколько TF-IDF кандидатов отправлять на re-rank.
- `Yandex embedding model` — модель эмбеддингов (по умолчанию `text-search-query/latest`).

Поведение:
- если embeddings недоступны (нет ключа/модель не отвечает), система автоматически
  откатывается на TF-IDF и продолжает работать;
- вычисленные вектора кэшируются в `processed/embedding_cache.json`.

A/B оценка retrieval:

```bash
python3 scripts/eval_retrieval_ab.py \
  --questions data/test/eval_questions.jsonl \
  --top-k 6 \
  --official-only \
  --embeddings-top-n 40 \
  --yandex-api-key "$YANDEX_CLOUD_API_KEY" \
  --yandex-folder "$YANDEX_CLOUD_FOLDER" \
  --embedding-model text-search-query/latest \
  --output-jsonl processed/eval_retrieval_ab.jsonl \
  --output-summary processed/eval_retrieval_ab_summary.json
```

## LoRA / QLoRA workflow

### 1) Собрать датасет из истории диалогов

```bash
python3 scripts/build_lora_dataset.py \
  --input processed/qa_history.jsonl \
  --out-train data/lora/train.jsonl \
  --out-eval data/lora/eval.jsonl \
  --eval-ratio 0.1
```

### 2) Обучить адаптер в Colab (T4)

- Ноутбук: `notebooks/lora_qlora_colab.ipynb`
- В Colab загрузите/подмонтируйте:
  - `data/lora/train.jsonl`
  - `data/lora/eval.jsonl`
- На выходе получите папку адаптера LoRA.

### 3) Локальный инференс адаптера

```bash
python3 scripts/lora_infer_local.py \
  --base-model Qwen/Qwen2.5-1.5B-Instruct \
  --adapter-path /path/to/adapter \
  --question "какие документы нужны для перевозки этилового спирта"
```

Для запуска через веб-приложение выберите backend `local_lora` и задайте:
- `Local LoRA base model`
- `Local LoRA adapter path`

Зависимости для LoRA/PEFT вынесены отдельно:

```bash
pip install -r requirements-lora.txt
```

## Структура проекта

```text
doc/                     # исходные нормативные документы
processed/
  clean_txt/             # очищенные txt
  cleaned_docs.jsonl     # очищенные документы с метаданными
  chunks.jsonl           # чанки для retrieval
  lexical_index.json     # офлайн индекс
scripts/
  build_lora_dataset.py
  rename_all_docs.py
  rename_unknown_docs.py
  prepare_corpus.py
  prepare_doc_files.py
  chunk_corpus.py
  build_index.py
  lora_infer_local.py
  eval_retrieval_ab.py
  test_retrieval.py
notebooks/
  lora_qlora_colab.ipynb
app.py                   # локальный веб-интерфейс
build.sh                 # полная сборка индекса
run.sh                   # запуск приложения
```

## Smoke test retrieval

```bash
python3 scripts/test_retrieval.py --index processed/lexical_index.json --top-k 6
```

## Важно

- Это учебный юридический ассистент; ответы нужно проверять по официальным источникам.
- LoRA обучается в Colab, локально используется инференс адаптера.
- Для слабых машин рекомендуется оставить базовый retrieval и включать embeddings re-rank
  только для сложных запросов.
