# EGAIS Licensing RAG Assistant (Diploma Project)

Учебный проект юридического ассистента по лицензированию алкогольной продукции и ЕГАИС.

Проект реализует полный контур:
- сбор и очистка корпуса нормативных документов;
- юридически-ориентированный chunking с метаданными;
- гибридный retrieval (TF-IDF + embeddings + multi-step + иерархическое расширение);
- генерация ответов в пользовательском формате с guardrails;
- автоматическая оценка качества (`smoke-3`, `extra10`, `20 + extra10`, `100+ load test`);
- подготовка к деплою на Linux-сервер в РФ.

---

## 1. Цель проекта

Сделать практичный RAG-ассистент, который:
- отвечает на типовые вопросы заявителя по лицензированию;
- опирается на локальную нормативную базу;
- явно показывает источники;
- минимизирует галлюцинации и “шум шаблонов”;
- подходит для демонстрации в рамках дипломной работы.

Целевой baseline модели: `yandexgpt-5-lite/latest`.

---

## 2. Что было сделано (подробно по этапам)

### Этап A: базовый RAG-контур

- Подготовлен pipeline обработки документов из `doc/` и дополнительных форматов.
- Реализован индекс `processed/lexical_index.json`.
- Поднят веб-интерфейс на Gradio (`app.py`) с retrieval + генерацией.

### Этап B: улучшение retrieval-качества

- Включен гибридный retrieval:
  - TF-IDF (основной поиск),
  - embeddings re-rank (`text-search-query/latest`),
  - multi-step retrieval (follow-up queries).
- Добавлены retries/fallback для внешних API, чтобы не падать при временной недоступности.
- Добавлен `official_only`-режим для фильтрации источников.

### Этап C: улучшение чанкинга (юридическая структура)

- Добавлен list-preserving chunking.
- В метаданные чанков добавлены:
  - `article_key`,
  - `article_part_index/total`,
  - `norm_refs`,
  - `list_density`,
  - neighbor-поля (`neighbor_prev_chunk_id`, `neighbor_next_chunk_id`),
  - иерархические признаки для post-retrieval расширения.
- В retrieval добавлено иерархическое расширение по статье/соседям (light chunk graph).

### Этап D: user-mode и юридические guardrails

- Ответы стандартизированы в блоки:
  - `### Краткий ответ`
  - `### Что сделать заявителю сейчас`
  - `### Какие документы подготовить`
  - `### Что нужно уточнить у заявителя`
  - `### Проверка актуальности норм`
  - `### Источники`
  - (опционально) `### Цитата нормы`
- Добавлены критические фактовые проверки (fact guards), в т.ч. по компетенции розницы и каналу подачи.
- Добавлена санитарка источников:
  - дедуп,
  - удаление будущих/мусорных ссылок,
  - приоритизация официальных НПА.
- Добавлены антишаблонные правила для действий/уточнений/документов.

### Этап E: контроль галлюцинаций и улучшение цитат

- Введен quality scoring для блока `Цитата нормы`.
- Добавлена фильтрация “сервисного шума” (Consultant overlays, технические хвосты).
- Добавлена жесткая проверка цитаты по реквизитам вопроса (если вопрос содержит номер НПА).

### Этап F: кеширование и производительность

- Реализован L2-кеш на SQLite:
  - answer cache,
  - retrieval cache.
- Добавлен fingerprint индекса для корректной инвалидации кеша.
- Добавлен post-expansion rerank для улучшения финального порядка после hierarchy expansion.

### Этап G: инженерный цикл и оценка

- Добавлены:
  - `scripts/run_fast_cycle.sh`,
  - `scripts/compare_eval_runs.py`,
  - `scripts/eval_chunking_grid.py`,
  - `scripts/run_load_test_100.sh`,
  - `scripts/build_loadtest_set.py`.
- Сформирован экономичный цикл разработки:
  - сначала `pytest` + `smoke-3`,
  - только после этого большие прогоны.

### Этап H: подготовка к защите/деплою

- Добавлены deployment-артефакты (`release/deploy`):
  - `systemd` unit,
  - `nginx` конфиг,
  - `provision_ubuntu.sh`,
  - `README_RU_DEPLOY.md`.
- Добавлены:
  - `release/DEPLOY_CHECKLIST.md`,
  - `release/LOAD_TEST_100_PROTOCOL.md`,
  - `release/cleanup_coursework_artifacts.sh`.

---

## 3. Финальная архитектура (кратко)

1) **Corpus build**  
`prepare_corpus.py` + `prepare_doc_files.py` -> JSONL документов с метаданными (включая даты).

2) **Chunking**  
`chunk_corpus.py` -> юридические чанки + `norm_refs` + иерархические связи.

3) **Index**  
`build_index.py` -> TF-IDF индекс.

4) **Retrieval в `app.py`**  
TF-IDF -> embeddings rerank -> multi-step -> parent/child + neighbor expansion -> post-expansion rerank.

5) **Generation + post-processing**  
LLM -> guardrails -> sanitization -> структурирование user-mode -> источники/цитаты.

6) **Evaluation**  
`eval_yandex_suite.py` + сравнение прогонов + load-test 100+.

---

## 4. Ключевые файлы проекта

- `app.py` — ядро веб-приложения, retrieval/generation/guardrails/cache.
- `build.sh`, `run.sh` — сборка и запуск.
- `scripts/prepare_corpus.py` — очистка RTF-корпуса.
- `scripts/prepare_doc_files.py` — импорт doc/docx/txt/md/pdf.
- `scripts/merge_corpora.py` — дедуп и приоритизация источников.
- `scripts/chunk_corpus.py` — юридический chunking.
- `scripts/build_index.py` — сборка TF-IDF индекса.
- `scripts/eval_yandex_suite.py` — основной eval.
- `scripts/eval_chunking_grid.py` — оценка конфигураций чанкинга.
- `scripts/run_fast_cycle.sh` — быстрый цикл проверки.
- `scripts/build_loadtest_set.py`, `scripts/run_load_test_100.sh` — нагрузочный тест 100+.
- `tests/test_rag_critical_guard.py` — критические тесты guardrails.
- `release/` — финальные инструкции, deploy-артефакты и чек-листы.

---

## 5. Быстрый старт (Linux)

```bash
chmod +x build.sh run.sh
./build.sh
./run.sh
```

Откройте: [http://127.0.0.1:7860](http://127.0.0.1:7860)

---

## 6. Режим финального baseline

Рекомендуемые параметры:
- backend: `yandex_openai`
- модель: `yandexgpt-5-lite/latest`
- `top_k=12`
- `official_only=ON`
- embeddings rerank: `ON`, `top_n=80`
- `multi_step=ON`

Готовый запуск:

```bash
cp release/.env.final.example .env.final
chmod +x release/run_final_web.sh
./release/run_final_web.sh
```

---

## 7. Как оценивать качество

### Smoke (дешевый регресс)

```bash
./scripts/run_fast_cycle.sh
```

### Extra10

```bash
./.venv/bin/python scripts/eval_yandex_suite.py \
  --llm-backend yandex_openai \
  --answer-mode user \
  --questions data/test/eval_questions_extra10.jsonl \
  --out-jsonl processed/eval_extra10.jsonl \
  --out-md processed/eval_extra10_report.md \
  --out-qa processed/eval_extra10_qa.md
```

### Load-test 100+

```bash
TARGET_SIZE=120 OUT_PREFIX=processed/loadtest_100 ./scripts/run_load_test_100.sh
```

Протокол: `release/LOAD_TEST_100_PROTOCOL.md`.

---

## 8. Деплой на сервер в РФ

См. `release/deploy/README_RU_DEPLOY.md`.

В составе уже есть:
- `release/deploy/provision_ubuntu.sh`
- `release/deploy/systemd/normatives-rag.service`
- `release/deploy/nginx/normatives-rag.conf`

Для защиты: `release/DEPLOY_CHECKLIST.md`.

---

## 9. Финальная папка для GitHub

Для сборки отдельной финальной директории проекта используйте:

```bash
chmod +x release/build_final_github_package.sh
./release/build_final_github_package.sh
```

На выходе:
- `release/final_project_full/` — готовая папка проекта для публикации на GitHub.

---

## 10. Ограничения и честные оговорки

- Проект учебный, ответы требуют юридической верификации.
- Внешняя LLM может быть временно недоступна; в этом случае система возвращает fallback из локального контекста.
- Качество зависит от полноты корпуса и актуальности редакций НПА.

---

## 11. Дополнительная документация

- `docs/readme_parts/00_INDEX.md`
- `release/README.md`
- `release/FINAL_SCHEMA_YANDEXGPT5LITE.md`
- `release/CORPUS_RETRIEVAL_PIPELINE.md`
- `release/FINAL_VERSION_MANIFEST.md`
