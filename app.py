#!/usr/bin/env python3
import json
import math
import re
from collections import Counter
from pathlib import Path

import gradio as gr


INDEX_PATH = Path("processed/lexical_index.json")
TOKEN_RE = re.compile(r"[a-zA-Zа-яА-Я0-9]{2,}")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


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


def answer(question: str, history: list[dict], top_k: int, official_only: bool) -> str:
    if not question.strip():
        return "Введите вопрос по лицензированию ЕГАИС."

    top_k = max(1, min(int(top_k), 12))
    matches = score_query(question, INDEX, official_only=official_only)[:top_k]
    if not matches:
        return (
            "Не нашел релевантные фрагменты в локальной базе.\n\n"
            "Попробуйте уточнить вопрос (например, тип лицензии, номер приказа, этап процедуры)."
        )

    intro = (
        "Найдены релевантные фрагменты из нормативной базы. "
        "Ниже источники для вашего ответа:\n\n"
    )
    context = format_context(matches)
    disclaimer = (
        "\n\n---\n"
        "Справочный ответ: проверьте актуальную редакцию норм и сведения в личном кабинете ЕГАИС."
    )
    return intro + context + disclaimer


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
