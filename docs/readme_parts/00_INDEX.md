# EGAIS Assistant Docs (Index)

Этот каталог содержит подробную, разбитую по темам документацию проекта.

## Как читать

- Если нужно быстро запустить проект: начните с `01_PROJECT_OVERVIEW.md`, затем `02_DATA_PREPARATION_AND_INDEX.md`.
- Если цель улучшить качество ответов: смотрите `03_APP_AND_RAG_PIPELINE.md` и `04_HYBRID_RETRIEVAL_EMBEDDINGS.md`.
- Если цель дообучение роли ассистента: переходите к `05_LORA_WORKFLOW_END_TO_END.md`.
- Если цель эксплуатация и стабильность: `06_OPERATION_MONITORING_TROUBLESHOOTING.md`.
- Если цель довести проект до итоговой демонстрации: `07_IMPLEMENTATION_PLAN_TURNKEY.md`.

## Состав документации

1. `01_PROJECT_OVERVIEW.md`  
   Полный обзор системы, архитектуры, ограничений и принципов проектирования.

2. `02_DATA_PREPARATION_AND_INDEX.md`  
   Подготовка корпуса документов, очистка, разметка, чанкинг и построение индекса.

3. `03_APP_AND_RAG_PIPELINE.md`  
   Логика `app.py`, формирование ответа, фильтрация и анти-галлюцинационные правила.

4. `04_HYBRID_RETRIEVAL_EMBEDDINGS.md`  
   Гибридный retrieval (TF-IDF + embeddings re-rank), кэширование и практические параметры.

5. `05_LORA_WORKFLOW_END_TO_END.md`  
   Подготовка SFT-датасета из `processed/qa_history.jsonl`, QLoRA в Colab, локальный инференс адаптера.

6. `06_OPERATION_MONITORING_TROUBLESHOOTING.md`  
   Эксплуатация, логи, типовые сбои и быстрые действия.

7. `07_IMPLEMENTATION_PLAN_TURNKEY.md`  
   Пошаговый план "под ключ": что и в каком порядке делать, чтобы получить финальную версию для защиты.

8. `08_ANALYTICAL_ETHANOL_REGULATORY_FRAMEWORK_2026_DRAFT.md`  
   Черновик системного обзора регулирования оборота этилового спирта (вне RAG-корпуса; требует сверки с официальными НПА перед использованием как источник фактов).

9. `08_ANALYTICAL_ETHANOL_REGULATORY_FRAMEWORK_2026_VERIFICATION.md`  
   Отчёт проверки черновика (п. 8): какие утверждения неверны и куда смотреть за официальными текстами.

## Основные файлы проекта

- `build.sh` — полный rebuild индекса и корпуса.
- `run.sh` — запуск веб-приложения Gradio.
- `app.py` — retrieval + LLM + форматирование ответа.
- `scripts/prepare_corpus.py` — подготовка RTF/MHTML-корпуса.
- `scripts/prepare_doc_files.py` — подготовка DOC/DOCX/TXT/MD/PDF и спец-обработка `license.txt`.
- `scripts/chunk_corpus.py` — чанкинг (в том числе article-aware режим).
- `scripts/build_index.py` — TF-IDF индекс.
- `scripts/build_lora_dataset.py` — генерация датасета для LoRA.
- `scripts/lora_infer_local.py` — локальный инференс base + adapter.

## Текущий статус (кратко)

- Базовый retrieval и веб-чат работают локально.
- Реализован гибридный re-rank через embeddings API с кэшем.
- Реализован конвейер подготовки данных для QLoRA.
- Для production-уровня осталось закрыть этапы в `07_IMPLEMENTATION_PLAN_TURNKEY.md`.
