# EGAIS Licensing RAG Assistant

Быстрый onboarding за 5 минут.

---

## 1) Что это

RAG-ассистент по лицензированию алкогольной продукции и ЕГАИС:

- локальный корпус нормативных документов;
- retrieval по чанкам;
- генерация структурированного ответа с источниками.

---

## 2) Требования

- Linux/macOS (или WSL на Windows)
- Python 3.10+
- Интернет для установки зависимостей

---

## 3) Быстрый старт (5 минут)

```bash
chmod +x build.sh run.sh
./build.sh
./run.sh
```

Открыть в браузере:

- `http://127.0.0.1:7860`  
  (если порт занят, `run.sh` автоматически выберет следующий свободный)

---

## 4) Что делает build

`./build.sh` автоматически:

1. создает `.venv`;
2. ставит `requirements.txt`;
3. нормализует документы в `doc/`;
4. готовит очищенный корпус;
5. обрабатывает доп. форматы (`doc/docx/txt/md/pdf`);
6. объединяет и дедуплицирует корпус;
7. строит чанки и lexical-индекс.

Ключевые артефакты:

- `processed/cleaned_docs.jsonl`
- `processed/chunks.jsonl`
- `processed/lexical_index.json`

---

## 5) Как запускать тесты

```bash
./test.sh
```

---

## 6) Полезные файлы

- `README.md` — полный обзор проекта
- `docs/PIPELINE_DETAILED_RU.md` — очень подробный техразбор пайплайна
- `docs/DIPLOMA_DEFENSE_OVERVIEW_RU.md` — версия "для защиты диплома"
- `release/deploy/README_RU_DEPLOY.md` — инструкции по деплою

---

## 7) Публикация на GitHub (если еще не сделано)

```bash
git init
git add .
git commit -m "Initial standalone project"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```

