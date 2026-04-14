#!/usr/bin/env python3
import json
import math
import re
from collections import Counter
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

import gradio as gr


INDEX_PATH = Path("processed/lexical_index.json")
TOKEN_RE = re.compile(r"[a-zA-Zа-яА-Я0-9]{2,}")
LEGAL_NUMBER_RE = re.compile(r"(?:№|N)\s*([0-9]{1,5}(?:-[0-9A-Za-zА-Яа-я]+)?)")
ORG_KEYWORDS = [
    "фсрар",
    "росалкогольрегулирование",
    "правительство российской федерации",
    "министерство финансов",
    "егаис",
    "госуслуги",
    "консультантплюс",
]
LEGAL_QUERY_MARKERS = [
    "лиценз",
    "приказ",
    "постановлен",
    "фз",
    "закон",
    "статья",
    "госпошлин",
    "заявлен",
    "егаис",
]
DISCLAIMER = (
    "Ответ сформирован автоматически. Для юридических действий рекомендуется "
    "свериться с официальными источниками: ФСРАР, КонсультантПлюс, Госуслуги."
)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def is_legal_query(query: str) -> bool:
    q = query.lower()
    return any(marker in q for marker in LEGAL_QUERY_MARKERS)


def extract_query_entities(query: str) -> set[str]:
    entities = set()
    q = query.lower()
    for m in LEGAL_NUMBER_RE.finditer(query):
        entities.add(m.group(1).lower())
    for keyword in ORG_KEYWORDS:
        if keyword in q:
            entities.add(keyword)
    return entities


def doc_weight(row: dict, official_only: bool) -> float:
    meta = row.get("metadata", {})
    source = (meta.get("source_file") or "").lower()
    doc_type = (meta.get("doc_type") or "").upper()

    is_official = doc_type in {"ПРИКАЗ", "ПОСТАНОВЛЕНИЕ", "РАСПОРЯЖЕНИЕ", "ФЕДЕРАЛЬНЫЙ ЗАКОН"}
    if official_only and not is_official:
        return 0.0

    weight = 1.0
    if is_official:
        weight *= 1.25
    if source.startswith("guide_"):
        weight *= 0.75
    if "unknown" in source:
        weight *= 0.65
    return weight


def score_query(query: str, index: dict, official_only: bool) -> list[tuple[float, dict]]:
    q_tf = Counter(tokenize(query))
    if not q_tf:
        return []
    query_entities = extract_query_entities(query)

    idf = index["idf"]
    docs = index["docs"]
    scored: list[tuple[float, dict]] = []
    for d in docs:
        w = doc_weight(d, official_only)
        if w <= 0:
            continue
        score = 0.0
        d_tf = d["tf"]
        d_len = max(1, d["len"])
        for tok, qf in q_tf.items():
            if tok in d_tf and tok in idf:
                score += (qf * idf[tok]) * (d_tf[tok] * idf[tok] / math.sqrt(d_len))
        if query_entities:
            text_low = d.get("text", "").lower()
            entity_hits = sum(1 for ent in query_entities if ent in text_low)
            score *= 1.0 + 0.12 * entity_hits
        if score > 0:
            scored.append((score * w, d))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def load_index() -> dict:
    if not INDEX_PATH.exists():
        raise FileNotFoundError(
            "Индекс не найден: processed/lexical_index.json. "
            "Сначала запустите scripts/build_index.py."
        )
    with INDEX_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


INDEX = load_index()


def format_context(matches: list[tuple[float, dict]]) -> str:
    lines = []
    for i, (score, row) in enumerate(matches, 1):
        meta = row.get("metadata", {})
        doc_type = meta.get("doc_type", "Документ")
        doc_no = meta.get("doc_number_file") or meta.get("doc_number_text") or "n/a"
        source = meta.get("source_file", "n/a")
        snippet = row["text"][:500].replace("\n", " ").strip()
        lines.append(f"[{i}] {doc_type} №{doc_no} ({source}) | score={score:.3f}\n{snippet}")
    return "\n\n".join(lines)


def select_diverse_matches(scored: list[tuple[float, dict]], top_k: int) -> list[tuple[float, dict]]:
    selected = []
    used_sources = set()
    for score, row in scored:
        source = row.get("metadata", {}).get("source_file", "")
        if source in used_sources:
            continue
        selected.append((score, row))
        used_sources.add(source)
        if len(selected) >= top_k:
            return selected
    if len(selected) < top_k:
        for score, row in scored:
            if (score, row) not in selected:
                selected.append((score, row))
                if len(selected) >= top_k:
                    break
    return selected


def template_legal_answer(question: str, matches: list[tuple[float, dict]]) -> str:
    refs = []
    for score, row in matches[:3]:
        meta = row.get("metadata", {})
        doc_type = meta.get("doc_type", "Документ")
        doc_no = meta.get("doc_number_file") or meta.get("doc_number_text") or "n/a"
        source = meta.get("source_file", "n/a")
        snippet = row.get("text", "").replace("\n", " ")[:280]
        refs.append((doc_type, doc_no, source, snippet))

    basis = "\n".join([f"- {d} №{n} ({s}): {t}..." for d, n, s, t in refs])
    sources = "\n".join([f"- {d} №{n} ({s})" for d, n, s, _ in refs])
    return (
        f"**Краткий ответ**\n"
        f"По вопросу: \"{question}\" релевантные нормы найдены в официальных источниках.\n\n"
        f"**Нормативное основание**\n{basis}\n\n"
        f"**Практические шаги**\n"
        f"- Уточните тип лицензируемой деятельности и статус заявителя.\n"
        f"- Подготовьте комплект документов согласно найденным нормам.\n"
        f"- Проверьте сроки и основания отказа/приостановления по релевантным пунктам.\n\n"
        f"**Источники**\n{sources}"
    )


def validate_answer_content(answer_text: str, matches: list[tuple[float, dict]]) -> str:
    expected_numbers = []
    for _, row in matches:
        meta = row.get("metadata", {})
        n = meta.get("doc_number_file") or meta.get("doc_number_text")
        if n:
            expected_numbers.append(str(n).lower())
    check = any(num in answer_text.lower() for num in expected_numbers[:3]) if expected_numbers else False
    return "Проверка: " + ("есть ссылки на реквизиты документов." if check else "реквизиты документов явно не найдены.")


def answer(question: str, history: list[dict], top_k: int, official_only: bool) -> str:
    if not question.strip():
        return "Введите вопрос по лицензированию ЕГАИС."

    top_k = max(1, min(int(top_k), 12))
    scored = score_query(question, INDEX, official_only=official_only)
    matches = select_diverse_matches(scored, top_k)
    if not matches:
        return (
            "Не нашел релевантные фрагменты в локальной базе.\n\n"
            "Попробуйте уточнить вопрос (например, тип лицензии, номер приказа, этап процедуры)."
        )

    if is_legal_query(question):
        main_answer = template_legal_answer(question, matches)
    else:
        main_answer = "Найдены релевантные фрагменты из базы:\n\n" + format_context(matches)

    validation = validate_answer_content(main_answer, matches)
    return f"{main_answer}\n\n{validation}\n\n---\n{DISCLAIMER}"


demo = gr.ChatInterface(
    fn=answer,
    additional_inputs=[
        gr.Slider(
            minimum=1,
            maximum=12,
            value=6,
            step=1,
            label="Top-K (количество найденных фрагментов)",
        ),
        gr.Checkbox(
            value=True,
            label="Только официальные НПА (рекомендуется)",
        ),
    ],
    title="EGAIS Normatives Assistant (локально)",
    description=(
        "Локальный поиск по нормативным документам ЕГАИС. "
        "Модель не используется: выдаются релевантные фрагменты и источники."
    ),
)


if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860)
