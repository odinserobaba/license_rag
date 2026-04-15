#!/usr/bin/env python3
import json
import math
import os
import re
import hashlib
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

import gradio as gr
try:
    import openai
except ImportError:
    openai = None


INDEX_PATH = Path("processed/lexical_index.json")
TOKEN_RE = re.compile(r"[a-zA-Zа-яА-Я0-9]{2,}")
LEGAL_NUMBER_RE = re.compile(r"(?:№|N)\s*([0-9]{1,5}(?:-[0-9A-Za-zА-Яа-я]+)?)")
LEGAL_REF_RE = re.compile(
    r"(пункт[а-я]*\s+\d+(?:\.\d+)?\s+стать[ьи]\s+\d+(?:\.\d+)?|"
    r"стать[ьяи]\s+\d+(?:\.\d+)?|"
    r"подпункт[а-я]*\s+\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
ARTICLE_REF_NUM_RE = re.compile(r"стать[ьяеи]\s+(\d+(?:\.\d+)?)", re.IGNORECASE)
CLAUSE_LINK_RE = re.compile(
    r"подпункт[а-я]*\s+[0-9\s\-,и]+пункт[а-я]*\s+[0-9.\s]+стать[ьи]\s+(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
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
    "лоценз",
    "приказ",
    "постановлен",
    "фз",
    "закон",
    "статья",
    "госпошлин",
    "заявлен",
    "егаис",
    "алкогол",
    "розничн",
    "продаж",
]
DISCLAIMER = (
    "Ответ сформирован автоматически. Для юридических действий рекомендуется "
    "свериться с официальными источниками: ФСРАР, КонсультантПлюс, Госуслуги."
)
OLLAMA_API_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_OLLAMA_MODEL = "qwen2.5:0.5b"
YANDEX_OPENAI_BASE_URL = "https://ai.api.cloud.yandex.net/v1"
DEFAULT_YANDEX_API_KEY = os.getenv(
    "YANDEX_CLOUD_API_KEY",
    "",
)
DEFAULT_YANDEX_FOLDER = os.getenv("YANDEX_CLOUD_FOLDER", "b1g80c8c8v3gh72ahsi7")
DEFAULT_YANDEX_MODEL = os.getenv("YANDEX_CLOUD_MODEL", "deepseek-v32/latest")
DEFAULT_LORA_BASE_MODEL = os.getenv("LOCAL_LORA_BASE_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
DEFAULT_LORA_ADAPTER_PATH = os.getenv("LOCAL_LORA_ADAPTER_PATH", "")
LOG_PATH = Path("processed/chat_logs.jsonl")
QA_LOG_PATH = Path("processed/qa_history.jsonl")
EMBEDDING_CACHE_PATH = Path("processed/embedding_cache.json")
DEFAULT_YANDEX_EMBEDDING_MODEL = os.getenv(
    "YANDEX_EMBEDDING_MODEL",
    "text-search-query/latest",
)

# Коды видов лицензируемой деятельности (справочник guide_license_activity_codes.md)
LICENSE_ACTIVITY_CODES: list[tuple[str, str]] = [
    ("ПХП_ВИНО_ЗГУ", "производство вина защищённое географическое указание наименование места происхождения"),
    ("ПХП_ВИНО", "производство хранение поставки вина игристого плодовая алкогольная продукция без этилового спирта"),
    ("ВРЗ", "временное разрешение завершение цикла производства дистиллятов выдержка винодельческая продукция"),
    ("РПО", "розничная продажа алкогольная продукция общественное питание"),
    ("РПА", "розничная продажа алкогольной продукции"),
    ("Т_ССНП", "перевозки нефасованная спиртосодержащая непищевой этиловый спирт более 25 процентов"),
    ("Т_ССПП", "перевозки нефасованная спиртосодержащая пищевая этиловый спирт более 25 процентов"),
    ("Т_ЭС", "перевозки этилового спирта"),
    ("Х_ССНП", "хранение спиртосодержащей непищевой продукции"),
    ("Х_ССПП", "хранение спиртосодержащей пищевой продукции"),
    ("Х_АП", "хранение алкогольной продукции"),
    ("Х_ЭС", "хранение этилового спирта"),
    ("ЗХП_ССНП", "закупка хранение поставки спиртосодержащей непищевой продукции"),
    ("ЗХП_ССПП", "закупка хранение поставки спиртосодержащей пищевой продукции"),
    ("ЗХП_АП", "закупка хранение поставки алкогольной продукции"),
    ("ПХП_ФАРМ", "производство этилового спирта фармацевтическая субстанция этанол"),
    ("ПХП_ССНП", "производство хранение поставки спиртосодержащей непищевой продукции"),
    ("ПХП_ССПП", "производство хранение поставки спиртосодержащей пищевой продукции"),
    ("ПХПРП_СХП", "производство хранение поставки розничная продажа винодельческая продукция сельхозпроизводитель"),
    ("ПХП_СХП", "производство хранение поставки винодельческая продукция сельхозпроизводитель"),
    ("ПХП_АП", "производство хранение поставки алкогольной продукции"),
    ("ПХП_ЭС", "производство хранение поставки этилового спирта"),
]

OFFICIAL_REFERENCE_LINKS: list[dict] = [
    {
        "label": "Росалкогольтабакконтроль (официальный сайт)",
        "url": "https://fsrar.gov.ru",
        "tokens": ["росалкогольтабакконтроль", "фсрар", "росалкогольрегулирование"],
    },
    {
        "label": "Государственный сводный реестр лицензий",
        "url": "https://fsrar.gov.ru/srrlic",
        "tokens": ["реестр лиценз", "сводный реестр", "srrlic"],
    },
    {
        "label": "Федеральный закон № 171-ФЗ от 22.11.1995",
        "url": "http://www.kremlin.ru/acts/bank/8506",
        "tokens": ["171-фз", "федеральный закон № 171", "федерального закона № 171"],
    },
    {
        "label": "Приказ Росалкогольрегулирования № 199 от 12.08.2019",
        "url": "http://publication.pravo.gov.ru/document/0001202002030031",
        "tokens": ["приказ №199", "приказ 199", "0001202002030031"],
    },
    {
        "label": "Портал официальных публикаций правовых актов",
        "url": "http://publication.pravo.gov.ru",
        "tokens": ["приказ", "постановление", "федеральный закон", "нпа"],
    },
]


def expand_query_for_activity_codes(query: str) -> str:
    q_low = query.lower()
    extra: list[str] = []
    for code, desc in LICENSE_ACTIVITY_CODES:
        if code.lower() in q_low:
            extra.append(f"{code} {desc}")
    if not extra:
        return query
    return f"{query}\n" + " ".join(extra)


def activity_code_match_boost(query: str, text_low: str) -> float:
    mul = 1.0
    q_low = query.lower()
    for code, _desc in LICENSE_ACTIVITY_CODES:
        c = code.lower()
        if c in q_low and c in text_low:
            mul *= 1.32
    return mul


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def is_legal_query(query: str) -> bool:
    q = query.lower()
    # Frequent user typo in Russian legal queries.
    q = q.replace("лоценз", "лиценз")
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


def extract_query_intent(query: str) -> tuple[str | None, set[str]]:
    q = query.lower()
    q = q.replace("лоценз", "лиценз")
    intent = None
    if "переоформ" in q:
        intent = "reissue"
    elif "продлен" in q:
        intent = "extension"
    elif "получ" in q or "выдач" in q:
        intent = "issuance"

    tags = set()
    if "госуслуг" in q or "епгу" in q:
        tags.add("epgu")
    if "госпошлин" in q:
        tags.add("fee")
    if "лаборатор" in q or "аккредитац" in q:
        tags.add("lab")
    if "розничн" in q and "продаж" in q:
        tags.add("retail")
    return intent, tags


def is_docs_required_query(query: str) -> bool:
    q = query.lower().replace("лоценз", "лиценз").replace("кикие", "какие")
    return (
        ("какие документы" in q)
        or ("перечень документов" in q)
        or ("что нужно для получения лицензии" in q)
        or ("какие нужны документы" in q)
    )


def is_transport_ethanol_query(query: str) -> bool:
    q = query.lower()
    return ("перевоз" in q) and ("этилов" in q or "спирт" in q)


def doc_weight(row: dict, official_only: bool) -> float:
    meta = row.get("metadata", {})
    source = (meta.get("source_file") or "").lower()
    doc_type = (meta.get("doc_type") or "").upper()
    source_kind = (meta.get("source_kind") or "").lower()

    is_official = doc_type in {"ПРИКАЗ", "ПОСТАНОВЛЕНИЕ", "РАСПОРЯЖЕНИЕ", "ФЕДЕРАЛЬНЫЙ ЗАКОН"}
    if official_only and not is_official and source_kind != "guide":
        return 0.0

    weight = 1.0
    if is_official:
        weight *= 1.25
    if source.startswith("guide_") or source_kind == "guide":
        weight *= 0.9
    if "unknown" in source:
        weight *= 0.65
    return weight


def score_query(
    query: str,
    index: dict,
    official_only: bool,
    retrieval_text: str | None = None,
) -> list[tuple[float, dict]]:
    q_source = (retrieval_text or query).strip()
    q_tf = Counter(tokenize(q_source))
    if not q_tf:
        return []
    query_entities = extract_query_entities(query)
    intent, query_tags = extract_query_intent(query)
    docs_required = is_docs_required_query(query)
    transport_ethanol = is_transport_ethanol_query(query)

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
        text_low = d.get("text", "").lower()
        if query_entities:
            entity_hits = sum(1 for ent in query_entities if ent in text_low)
            score *= 1.0 + 0.12 * entity_hits

        score *= activity_code_match_boost(query, text_low)

        # Query-adaptive boosts: prioritize fragments that actually list required documents.
        if docs_required:
            has_docs_pattern = ("документ" in text_low) and (
                "представ" in text_low or "заявлен" in text_low or "подпункт" in text_low
            )
            score *= 1.35 if has_docs_pattern else 0.78

        # For transportation-specific licenses, down-rank generic production-only chunks.
        if transport_ethanol:
            has_transport_pattern = ("перевоз" in text_low) or ("транспорт" in text_low)
            score *= 1.4 if has_transport_pattern else 0.7

        meta = d.get("metadata", {})
        if intent and (meta.get("procedure_type") == intent):
            score *= 1.35
        row_tags = set(meta.get("topic_tags") or [])
        if query_tags and row_tags:
            score *= 1.0 + 0.08 * len(query_tags & row_tags)
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


def doc_label(meta: dict) -> str:
    citation = (meta.get("doc_citation") or "").strip()
    if citation:
        return citation
    doc_type = (meta.get("doc_type") or "Документ").strip()
    number = meta.get("doc_number_text") or meta.get("doc_number_file")
    date = meta.get("doc_date_file")
    title = meta.get("doc_title") or meta.get("title_guess")
    parts = [doc_type]
    if number:
        parts.append(f"№{number}")
    if date:
        parts.append(f"от {date}")
    if title:
        parts.append(f"— {title}")
    return " ".join(parts).strip()


def format_context(matches: list[tuple[float, dict]]) -> str:
    lines = []
    for i, (score, row) in enumerate(matches, 1):
        meta = row.get("metadata", {})
        label = doc_label(meta)
        section_title = meta.get("section_title")
        article_number = meta.get("article_number")
        subpoints = meta.get("subpoint_refs") or []
        snippet = row["text"][:500].replace("\n", " ").strip()
        section_part = f" | раздел: {section_title}" if section_title else ""
        article_part = f" | статья: {article_number}" if article_number else ""
        subpoint_part = f" | подпункты: {', '.join(subpoints[:4])}" if subpoints else ""
        lines.append(
            f"[{i}] {label}{section_part}{article_part}{subpoint_part} | score={score:.3f}\n{snippet}"
        )
    return "\n\n".join(lines)


def extract_legal_refs(text: str, limit: int = 4) -> list[str]:
    refs = []
    seen = set()
    for m in LEGAL_REF_RE.finditer(text):
        ref = m.group(1).strip()
        key = ref.lower()
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
        if len(refs) >= limit:
            break
    return refs


def build_normative_digest(matches: list[tuple[float, dict]], limit: int = 4) -> str:
    lines = []
    for i, (_, row) in enumerate(matches[:limit], 1):
        meta = row.get("metadata", {})
        label = doc_label(meta)
        text = row.get("text", "").replace("\n", " ").strip()
        refs = extract_legal_refs(text, limit=3)
        ref_part = ", ".join(refs) if refs else "в явном виде статьи/пункты не выделены"
        quote = text[:260] + ("..." if len(text) > 260 else "")
        lines.append(
            f"- [{i}] {label}\n"
            f"  - Норма: {ref_part}\n"
            f"  - Суть фрагмента: {quote}"
        )
    return "\n".join(lines)


def collect_article19_text(matches: list[tuple[float, dict]]) -> str:
    parts: list[str] = []
    for _, row in matches:
        meta = row.get("metadata", {}) or {}
        article_number = str(meta.get("article_number") or "").strip()
        source = (meta.get("source_file") or "").lower()
        if article_number != "19":
            continue
        if "fz-22_11_1995" not in source and "фз171" not in source:
            continue
        parts.append(row.get("text", ""))
    return "\n".join(parts)


def extract_documents_items_from_article19(text: str, limit: int = 8) -> list[str]:
    if not text:
        return []
    lines = text.splitlines()
    items: list[str] = []
    cur = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^(\d+)\)\s+(.+)$", line)
        if m:
            if cur:
                items.append(cur.strip())
                if len(items) >= limit:
                    break
            cur = f"{m.group(1)}) {m.group(2)}"
            continue
        if cur:
            cur += " " + line
    if cur and len(items) < limit:
        items.append(cur.strip())

    # Keep unique concise items.
    out: list[str] = []
    seen = set()
    for item in items:
        normalized = re.sub(r"\s+", " ", item).strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized[:420] + ("..." if len(normalized) > 420 else ""))
        if len(out) >= limit:
            break
    return out


def build_documents_block_from_context(question: str, matches: list[tuple[float, dict]]) -> str:
    if not is_docs_required_query(question):
        return ""
    article19_text = collect_article19_text(matches)
    if not article19_text:
        # Fallback: direct pull from indexed chunks of 171-FZ article 19.
        direct = law_article_direct_matches(INDEX, "19", top_k=10)
        article19_text = "\n".join((row.get("text", "") for _, row in direct))
    items = extract_documents_items_from_article19(article19_text, limit=8)
    if not items:
        return ""
    body = "\n".join([f"- {x}" for x in items])
    return (
        "### Перечень документов (автоизвлечение из ст.19 171-ФЗ)\n"
        f"{body}\n\n"
        "Примечание: перечень соотносится с подпунктами статьи 19; для конкретного вида лицензии "
        "проверьте применимость подпунктов в профильном положении о лицензировании."
    )


def build_transport_docs_vs_requirements_block(question: str, matches: list[tuple[float, dict]]) -> str:
    if not is_transport_ethanol_query(question):
        return ""

    doc_items: list[str] = []
    doc_seen = set()
    requirements: list[str] = []
    req_seen = set()

    for _, row in matches:
        text = row.get("text", "")
        meta = row.get("metadata", {}) or {}
        text_low = text.lower()
        sec_title_low = (meta.get("section_title") or "").lower()

        # Prefer explicit list from transport license section in license.txt.
        if "для получения лицензии на перевозк" in sec_title_low:
            for raw in text.splitlines():
                line = raw.strip()
                if re.match(r"^\d+\)\s+.+", line):
                    clean = re.sub(r"\s+", " ", line)
                    if clean not in doc_seen:
                        doc_seen.add(clean)
                        doc_items.append(clean)
                if len(doc_items) >= 8:
                    break

        # Requirements are often described separately from submission docs.
        if "требован" in text_low or "соответств" in text_low:
            normalized = re.sub(r"\s+", " ", text).strip()
            if normalized and normalized not in req_seen:
                req_seen.add(normalized)
                requirements.append(normalized[:260] + ("..." if len(normalized) > 260 else ""))

    if not doc_items and not requirements:
        return ""

    docs_part = (
        "\n".join(f"- {item}" for item in doc_items[:6])
        if doc_items
        else "- В текущем retrieval-контексте не найден явный нумерованный перечень документов именно для подачи заявления на перевозки."
    )
    req_part = (
        "\n".join(f"- {item}" for item in requirements[:4])
        if requirements
        else "- В текущем retrieval-контексте отдельный блок лицензионных требований выражен частично."
    )
    return (
        "### Разделение: документы для подачи vs требования к лицензиату\n"
        "#### Документы, подаваемые заявителем\n"
        f"{docs_part}\n\n"
        "#### Требования к лицензиату (условия соответствия)\n"
        f"{req_part}\n\n"
        "Примечание: не смешивайте документы для подачи заявления с требованиями соответствия перевозчика."
    )


def ensure_questions_to_applicant_block(answer_text: str, question: str) -> str:
    if "### Что нужно уточнить у заявителя" in answer_text:
        return answer_text

    base = [
        "- Тип продукции: этиловый спирт или нефасованная спиртосодержащая продукция (>25%).",
        "- Планируемый годовой объем перевозок (в дал/год).",
        "- Наличие собственного/арендованного транспорта и его реквизиты.",
    ]
    if is_transport_ethanol_query(question):
        base.append("- По какому адресу(ам) зарегистрированы транспортные средства и ПАК/оборудование учета.")
    return (
        f"{answer_text}\n\n"
        "### Что нужно уточнить у заявителя\n"
        + "\n".join(base)
    )


def strip_noise_citations(text: str) -> str:
    # Remove markdown numeric links like ](29), keep normal URLs intact.
    text = re.sub(r"\]\(\d{1,4}\)", "]", text)
    return text


def dedupe_sources_sections(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    sources: list[str] = []
    source_seen = set()
    in_sources = False

    for line in lines:
        if line.strip() == "### Источники":
            in_sources = True
            continue
        if in_sources:
            if line.startswith("### ") and line.strip() != "### Источники":
                in_sources = False
                out.append(line)
                continue
            m = re.match(r"^\s*[-*]\s+(.+)$", line)
            if m:
                src = m.group(1).strip()
                if src not in source_seen:
                    source_seen.add(src)
                    sources.append(f"- {src}")
            continue
        out.append(line)

    if not sources:
        return "\n".join(out)

    insert_at = len(out)
    for i, line in enumerate(out):
        if line.strip() in {
            "### Раскрытие норм из контекста",
            "### Разделение: документы для подачи vs требования к лицензиату",
            "### Рассуждение модели",
            "### Проверка источников",
        }:
            insert_at = i
            break

    source_block = ["### Источники", *sources, ""]
    merged = out[:insert_at] + source_block + out[insert_at:]
    return "\n".join(merged)


def build_prompt_context(matches: list[tuple[float, dict]], max_chars_per_chunk: int = 1000) -> str:
    blocks = []
    for i, (score, row) in enumerate(matches, 1):
        meta = row.get("metadata", {})
        label = doc_label(meta)
        article_number = meta.get("article_number")
        subpoints = meta.get("subpoint_refs") or []
        text = row.get("text", "").replace("\n", " ").strip()[:max_chars_per_chunk]
        refs = ", ".join(extract_legal_refs(text, limit=3))
        refs_part = f"\nНормы в фрагменте: {refs}" if refs else ""
        article_part = f"\nСтатья: {article_number}" if article_number else ""
        subpoint_part = f"\nПодпункты: {', '.join(subpoints[:6])}" if subpoints else ""
        blocks.append(f"[{i}] {label}{article_part}{subpoint_part}{refs_part}\n{text}")
    return "\n\n".join(blocks)


def build_legal_prompt(question: str, matches: list[tuple[float, dict]]) -> str:
    context = build_prompt_context(matches)
    return (
        "СИСТЕМНАЯ РОЛЬ:\n"
        "Ты юридический помощник по лицензированию и ЕГАИС.\n\n"
        "ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА:\n"
        "1) Отвечай только по предоставленному контексту.\n"
        "2) Не выдумывай реквизиты документов, номера статей и сроки.\n"
        "3) Если вопрос общий, сначала дай БАЗОВУЮ процедуру по найденным фрагментам.\n"
        "4) Отдельно укажи, какие пункты зависят от типа лицензии.\n"
        "5) Фразу 'Недостаточно данных в предоставленном контексте' используй только для отсутствующих деталей.\n"
        "6) Всегда указывай источники в конце ответа.\n"
        "7) Стиль: официальный, краткий, прикладной.\n\n"
        "8) В разделе 'Нормативное основание' обязательно раскрой КОНКРЕТНЫЕ нормы:\n"
        "   - минимум 3 пункта в формате: [источник] какая статья/пункт -> что это означает.\n"
        "   - если статья/пункт явно не указан в фрагменте, так и напиши.\n\n"
        "9) ЗАПРЕЩЕНО ссылаться на документы и номера НПА, которых нет в контексте.\n"
        "10) Не смешивай типы ссылок: 'статья' обычно для закона, 'пункт/раздел' для подзаконных актов.\n\n"
        "11) Если в контексте есть отсылка к подпунктам/пунктам статьи, но перечень не раскрыт,\n"
        "    сначала раскрой эту норму по фрагментам 171-ФЗ, потом давай общий вывод.\n\n"
        "ФОРМАТ ОТВЕТА:\n"
        "### Краткий ответ\n"
        "### Нормативное основание\n"
        "### Практические шаги\n"
        "### Что нужно уточнить у заявителя\n"
        "### Источники\n\n"
        f"Вопрос пользователя:\n{question}\n\n"
        f"Контекст:\n{context}\n"
    )


def append_log(record: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_qa_log(record: dict) -> None:
    QA_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with QA_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


_EMBEDDING_CACHE_MEM: dict[str, dict[str, list[float]]] | None = None
_EMBEDDING_CACHE_DIRTY = False


def _load_embedding_cache() -> dict[str, dict[str, list[float]]]:
    global _EMBEDDING_CACHE_MEM
    if _EMBEDDING_CACHE_MEM is not None:
        return _EMBEDDING_CACHE_MEM
    if not EMBEDDING_CACHE_PATH.exists():
        _EMBEDDING_CACHE_MEM = {}
        return _EMBEDDING_CACHE_MEM
    try:
        with EMBEDDING_CACHE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _EMBEDDING_CACHE_MEM = data
        else:
            _EMBEDDING_CACHE_MEM = {}
    except Exception:
        _EMBEDDING_CACHE_MEM = {}
    return _EMBEDDING_CACHE_MEM


def _flush_embedding_cache_if_dirty() -> None:
    global _EMBEDDING_CACHE_DIRTY
    if not _EMBEDDING_CACHE_DIRTY:
        return
    cache = _load_embedding_cache()
    EMBEDDING_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EMBEDDING_CACHE_PATH.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    _EMBEDDING_CACHE_DIRTY = False


def _normalize_embedding_text(text: str, max_len: int = 3500) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    return normalized[:max_len]


def _embedding_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def _yandex_full_model(folder: str, model: str) -> str:
    if model.startswith("emb://"):
        return model
    if model.startswith("gpt://"):
        # Be tolerant to legacy config: convert chat schema to embedding schema.
        return "emb://" + model[len("gpt://") :]
    return f"emb://{folder}/{model}"


def _fetch_embedding_yandex(text: str, api_key: str, folder: str, model: str) -> tuple[list[float] | None, str]:
    if openai is None:
        return None, "[EMBEDDINGS недоступны] не установлен пакет openai."
    if not api_key or not folder or not model:
        return None, "[EMBEDDINGS недоступны] не заданы api_key/folder/model."
    try:
        client = openai.OpenAI(
            api_key=api_key,
            base_url=YANDEX_OPENAI_BASE_URL,
            project=folder,
        )
        response = client.embeddings.create(
            model=_yandex_full_model(folder, model),
            input=[text],
            encoding_format="float",
        )
        vec = response.data[0].embedding if response and response.data else None
        if not vec:
            return None, "[EMBEDDINGS недоступны] пустой embedding-ответ."
        return [float(x) for x in vec], ""
    except Exception as e:  # noqa: BLE001
        return None, f"[EMBEDDINGS недоступны] ошибка Yandex Cloud: {e}"


def _get_or_create_embedding(
    text: str,
    *,
    api_key: str,
    folder: str,
    model: str,
) -> tuple[list[float] | None, bool, str]:
    global _EMBEDDING_CACHE_DIRTY
    normalized = _normalize_embedding_text(text)
    if not normalized:
        return None, False, ""

    cache = _load_embedding_cache()
    model_key = f"{folder}::{model}"
    model_cache = cache.setdefault(model_key, {})
    h = _embedding_hash(normalized)
    if h in model_cache:
        return model_cache[h], True, ""

    vec, err = _fetch_embedding_yandex(normalized, api_key=api_key, folder=folder, model=model)
    if vec is None:
        return None, False, err
    model_cache[h] = vec
    _EMBEDDING_CACHE_DIRTY = True
    return vec, False, ""


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / ((na ** 0.5) * (nb ** 0.5))


def rerank_with_embeddings(
    question: str,
    scored: list[tuple[float, dict]],
    *,
    api_key: str,
    folder: str,
    model: str,
    top_n: int = 40,
    emb_weight: float = 0.35,
) -> tuple[list[tuple[float, dict]], dict]:
    if not scored:
        return scored, {"enabled": True, "used": False, "reason": "no_candidates"}

    top_n = max(5, min(int(top_n), 120))
    candidates = scored[:top_n]
    rest = scored[top_n:]
    q_vec, q_from_cache, q_err = _get_or_create_embedding(
        question,
        api_key=api_key,
        folder=folder,
        model=model,
    )
    if q_vec is None:
        return scored, {"enabled": True, "used": False, "error": q_err}

    best_lex = max((s for s, _ in candidates), default=1.0) or 1.0
    reranked: list[tuple[float, dict]] = []
    emb_hits = 0
    cache_hits = 1 if q_from_cache else 0
    for lex_score, row in candidates:
        text = row.get("text", "")
        d_vec, d_from_cache, d_err = _get_or_create_embedding(
            text,
            api_key=api_key,
            folder=folder,
            model=model,
        )
        if d_vec is None:
            # keep lexical rank for failed embedding chunks
            reranked.append((lex_score, row))
            continue
        cache_hits += 1 if d_from_cache else 0
        emb_sim = _cosine_similarity(q_vec, d_vec)
        lex_norm = max(0.0, lex_score / best_lex)
        emb_norm = max(0.0, min(1.0, (emb_sim + 1.0) / 2.0))
        blended = (1.0 - emb_weight) * lex_norm + emb_weight * emb_norm
        final_score = blended * best_lex
        reranked.append((final_score, row))
        emb_hits += 1

    reranked.sort(key=lambda x: x[0], reverse=True)
    _flush_embedding_cache_if_dirty()
    return reranked + rest, {
        "enabled": True,
        "used": emb_hits > 0,
        "candidates": len(candidates),
        "embedded": emb_hits,
        "cache_hits": cache_hits,
    }


_LORA_RUNTIME: dict | None = None


def _load_local_lora_runtime(base_model: str, adapter_path: str) -> tuple[dict | None, str]:
    global _LORA_RUNTIME
    base_model = (base_model or "").strip()
    adapter_path = (adapter_path or "").strip()
    if not base_model:
        return None, "[LLM недоступна] не задана base model для local_lora."
    if not adapter_path:
        return None, "[LLM недоступна] не задан путь к LoRA adapter."
    if not Path(adapter_path).exists():
        return None, f"[LLM недоступна] adapter path не найден: {adapter_path}"

    cache_key = f"{base_model}::{adapter_path}"
    if _LORA_RUNTIME and _LORA_RUNTIME.get("key") == cache_key:
        return _LORA_RUNTIME, ""

    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except Exception as e:  # noqa: BLE001
        return None, (
            "[LLM недоступна] local_lora требует зависимости: "
            "pip install -r requirements-lora.txt. "
            f"Ошибка импорта: {e}"
        )

    try:
        dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        base = AutoModelForCausalLM.from_pretrained(
            base_model,
            torch_dtype=dtype,
            device_map="auto",
        )
        model = PeftModel.from_pretrained(base, adapter_path)
        tokenizer = AutoTokenizer.from_pretrained(base_model)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        _LORA_RUNTIME = {
            "key": cache_key,
            "model": model,
            "tokenizer": tokenizer,
            "torch": torch,
        }
        return _LORA_RUNTIME, ""
    except Exception as e:  # noqa: BLE001
        return None, f"[LLM недоступна] ошибка инициализации local_lora: {e}"


def generate_with_local_lora(
    prompt: str,
    base_model: str,
    adapter_path: str,
    max_tokens: int = 800,
) -> dict:
    runtime, err = _load_local_lora_runtime(base_model, adapter_path)
    if runtime is None:
        return {"text": "", "reasoning": "", "error": err}

    model = runtime["model"]
    tokenizer = runtime["tokenizer"]
    torch = runtime["torch"]

    try:
        inputs = tokenizer(prompt, return_tensors="pt")
        if torch.cuda.is_available():
            inputs = {k: v.to(model.device) for k, v in inputs.items()}
        with torch.inference_mode():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=max(128, min(int(max_tokens), 1600)),
                do_sample=False,
                temperature=0.1,
                pad_token_id=tokenizer.eos_token_id,
            )
        gen_ids = output_ids[0][inputs["input_ids"].shape[1] :]
        text = tokenizer.decode(gen_ids, skip_special_tokens=True).strip()
        if not text:
            return {"text": "", "reasoning": "", "error": "[LLM недоступна] local_lora вернула пустой ответ."}
        return {"text": text, "reasoning": "", "error": ""}
    except Exception as e:  # noqa: BLE001
        return {"text": "", "reasoning": "", "error": f"[LLM недоступна] ошибка local_lora: {e}"}


def generate_with_ollama(prompt: str, model: str, max_tokens: int = 500) -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": max_tokens,
        },
    }
    req = urlrequest.Request(
        OLLAMA_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "text": (data.get("response") or "").strip(),
                "reasoning": "",
                "error": "",
            }
    except urlerror.URLError as e:
        return {
            "text": "",
            "reasoning": "",
            "error": f"[LLM недоступна] {e}",
        }


def generate_with_yandex_openai(
    prompt: str,
    api_key: str,
    folder: str,
    model: str,
    max_tokens: int = 1200,
) -> dict:
    if openai is None:
        return {
            "text": "",
            "reasoning": "",
            "error": "[LLM недоступна] не установлен пакет openai. Установите: pip install openai",
        }
    api_key = (api_key or "").strip()
    folder = (folder or "").strip()
    model = (model or "").strip()
    if not api_key:
        return {"text": "", "reasoning": "", "error": "[LLM недоступна] не указан API key для Yandex Cloud."}
    if not folder or not model:
        return {"text": "", "reasoning": "", "error": "[LLM недоступна] не указаны folder/model для Yandex Cloud."}

    full_model = f"gpt://{folder}/{model}"
    client = openai.OpenAI(
        api_key=api_key,
        base_url=YANDEX_OPENAI_BASE_URL,
        project=folder,
    )
    # For deepseek-v32, Yandex may return reasoning-only output first.
    # We use chat.completions and allow a larger token budget to get final content.
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=full_model,
                temperature=0.2,
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты юридический ассистент. Отвечай строго по контексту, "
                            "без выдуманных фактов и реквизитов."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            choice = response.choices[0].message
            text = (choice.content or "").strip()
            reasoning_text = (getattr(choice, "reasoning_content", None) or "").strip()
            if text:
                return {"text": text, "reasoning": reasoning_text, "error": ""}
            if reasoning_text:
                return {
                    "text": "",
                    "reasoning": reasoning_text,
                    "error": (
                        "[LLM вернула только reasoning без финального текста. "
                        "Увеличьте max_tokens или попробуйте другую модель Yandex.]"
                    ),
                }
            return {"text": "", "reasoning": "", "error": "[LLM недоступна] пустой ответ модели Yandex Cloud."}
        except Exception as e:  # noqa: BLE001
            err_text = str(e)
            is_connection = "Connection error" in err_text or "ConnectError" in err_text
            if attempt == 0 and is_connection:
                continue
            return {"text": "", "reasoning": "", "error": f"[LLM недоступна] ошибка Yandex Cloud: {e}"}
    return {"text": "", "reasoning": "", "error": "[LLM недоступна] ошибка Yandex Cloud: не удалось выполнить запрос."}


def chat_with_yandex_openai(
    api_key: str,
    folder: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int = 400,
) -> dict:
    if openai is None:
        return {"text": "", "reasoning": "", "error": "[LLM недоступна] не установлен пакет openai."}
    api_key = (api_key or "").strip()
    folder = (folder or "").strip()
    model = (model or "").strip()
    if not api_key or not folder or not model:
        return {"text": "", "reasoning": "", "error": "[LLM недоступна] не заданы параметры Yandex."}
    full_model = f"gpt://{folder}/{model}"
    client = openai.OpenAI(
        api_key=api_key,
        base_url=YANDEX_OPENAI_BASE_URL,
        project=folder,
    )
    try:
        response = client.chat.completions.create(
            model=full_model,
            temperature=0.1,
            max_tokens=max_tokens,
            messages=messages,
        )
        choice = response.choices[0].message
        return {
            "text": (choice.content or "").strip(),
            "reasoning": (getattr(choice, "reasoning_content", None) or "").strip(),
            "error": "",
        }
    except Exception as e:  # noqa: BLE001
        return {"text": "", "reasoning": "", "error": f"[LLM недоступна] {e}"}


OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"


def chat_with_ollama(messages: list[dict[str, str]], model: str, max_tokens: int = 400) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": max_tokens},
    }
    req = urlrequest.Request(
        OLLAMA_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            msg = (data.get("message") or {})
            return {
                "text": (msg.get("content") or "").strip(),
                "reasoning": "",
                "error": "",
            }
    except urlerror.URLError as e:
        return {"text": "", "reasoning": "", "error": f"[LLM недоступна] {e}"}


def planner_messages(question: str, matches: list[tuple[float, dict]]) -> list[dict[str, str]]:
    lines = []
    for i, (sc, row) in enumerate(matches[:10], 1):
        meta = row.get("metadata", {})
        src = doc_label(meta)
        sec = meta.get("section_title") or ""
        snip = row.get("text", "").replace("\n", " ")[:160]
        lines.append(f"[{i}] score={sc:.3f} | {src} | {sec}\n{snip}")
    ctx = "\n".join(lines)
    user = (
        f"Вопрос пользователя:\n{question}\n\n"
        f"Текущие фрагменты из поиска:\n{ctx}\n\n"
        "Верни ТОЛЬКО один JSON-объект без пояснений и без markdown:\n"
        '{"follow_up_searches":["краткий поисковый запрос 1", ...], "reason":"кратко зачем"}\n'
        "Правила: follow_up_searches — от 0 до 4 строк на русском (3–14 слов), чтобы найти недостающие нормы/документы/процедуру. "
        "Если контекста достаточно, верни пустой массив follow_up_searches."
    )
    sys = (
        "Ты планировщик поиска для юридического RAG. Ты не отвечаешь пользователю. "
        "Только валидный JSON в одной строке или нескольких строках внутри объекта."
    )
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def parse_follow_up_searches(text: str) -> tuple[list[str], str]:
    raw = (text or "").strip()
    if not raw:
        return [], ""
    if "```" in raw:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
    brace = raw.find("{")
    if brace >= 0:
        raw = raw[brace:]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [], ""
    searches = data.get("follow_up_searches") or data.get("queries") or []
    reason = str(data.get("reason", "") or "").strip()
    if not isinstance(searches, list):
        return [], reason
    out = [str(x).strip() for x in searches if str(x).strip()][:4]
    return out, reason


def chunk_row_key(row: dict) -> str:
    return str(row.get("chunk_id") or row.get("metadata", {}).get("chunk_id") or "")


def merge_scored_matches(
    primary: list[tuple[float, dict]],
    extra: list[tuple[float, dict]],
    max_total: int,
) -> list[tuple[float, dict]]:
    seen: set[str] = set()
    merged: list[tuple[float, dict]] = []
    for score, row in primary + extra:
        key = chunk_row_key(row) or str(id(row))
        if key in seen:
            continue
        seen.add(key)
        merged.append((score, row))
        if len(merged) >= max_total:
            break
    return merged


def run_follow_up_retrieval(
    question: str,
    follow_queries: list[str],
    index: dict,
    official_only: bool,
    per_query_k: int,
) -> list[tuple[float, dict]]:
    collected: list[tuple[float, dict]] = []
    for fq in follow_queries:
        q = f"{question} {fq}".strip()
        scored = score_query(q, index, official_only, retrieval_text=expand_query_for_activity_codes(q))
        picked = select_diverse_matches(scored, per_query_k)
        collected.extend(picked)
    return collected


def referenced_article_numbers(question: str, matches: list[tuple[float, dict]]) -> list[str]:
    q_low = question.lower()
    joined = " ".join((row.get("text", "") for _, row in matches))
    refs: list[str] = []

    # Strong signal: clause-to-article links ("подпункты ... пункта ... статьи X").
    for m in CLAUSE_LINK_RE.finditer(joined):
        n = m.group(1).strip()
        if n and n not in refs:
            refs.append(n)

    # Fallback from generic "статья X" mentions in context and question.
    for src in (joined, q_low):
        for m in ARTICLE_REF_NUM_RE.finditer(src):
            n = m.group(1).strip()
            if n and n not in refs:
                refs.append(n)

    # Prioritize article 19 for document-list queries.
    if is_docs_required_query(question) and "19" in refs:
        refs = ["19"] + [x for x in refs if x != "19"]
    return refs[:6]


def reference_anchor_queries(question: str, matches: list[tuple[float, dict]]) -> list[str]:
    """
    Deterministic follow-up queries for unresolved legal references.
    Works across different license types (not only transport).
    """
    anchors: list[str] = []
    article_nums = referenced_article_numbers(question, matches)
    docs_query = is_docs_required_query(question)

    for n in article_nums:
        anchors.append(f"171-фз статья {n} полный текст актуальная редакция")
        if docs_query:
            anchors.append(f"171-фз статья {n} документы и сведения для лицензии")

    q_low = question.lower()
    for code, desc in LICENSE_ACTIVITY_CODES:
        if code.lower() in q_low:
            anchors.append(f"{code} {desc} лицензия требования документы")
            anchors.append(f"171-фз статья 18 пункт 2 {desc}")

    if is_transport_ethanol_query(question) or ("перевоз" in q_low and "спирт" in q_low):
        anchors.append("приказ 397 перевозка этилового спирта требования к транспорту егаис")

    out: list[str] = []
    seen = set()
    for a in anchors:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out[:8]


def law_article_direct_matches(index: dict, article_number: str, top_k: int = 8) -> list[tuple[float, dict]]:
    """
    Hard pull of a specific article from 171-FZ chunks by metadata.
    """
    article = (article_number or "").strip()
    if not article:
        return []
    picked: list[tuple[float, dict]] = []
    for d in index.get("docs", []):
        meta = d.get("metadata", {}) or {}
        src = (meta.get("source_file") or "").lower()
        if "fz-22_11_1995" not in src and "фз171" not in src:
            continue
        if str(meta.get("article_number") or "").strip() != article:
            continue
        score = 1000.0 - float(meta.get("chunk_index") or 0) * 0.01
        picked.append((score, d))
        if len(picked) >= top_k:
            break
    return picked


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
        source = doc_label(meta)
        snippet = row.get("text", "").replace("\n", " ")[:280]
        refs.append((source, snippet))

    basis = "\n".join([f"- {s}: {t}..." for s, t in refs])
    sources = "\n".join([f"- {s}" for s, _ in refs])
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


def sources_block(matches: list[tuple[float, dict]], limit: int = 4) -> str:
    lines = []
    used = set()
    for _, row in matches[:limit]:
        meta = row.get("metadata", {})
        article_number = meta.get("article_number")
        key = (doc_label(meta), article_number)
        if key in used:
            continue
        used.add(key)
        lines.append(f"- {key[0]}")
        if len(lines) >= limit:
            break
    return "### Источники\n" + "\n".join(lines)


def allowed_doc_numbers(matches: list[tuple[float, dict]]) -> set[str]:
    nums = set()
    for _, row in matches:
        meta = row.get("metadata", {})
        for v in (meta.get("doc_number_file"), meta.get("doc_number_text")):
            if v:
                nums.add(str(v).lower())
    return nums


def find_doc_numbers_in_text(text: str) -> set[str]:
    return {m.group(1).lower() for m in LEGAL_NUMBER_RE.finditer(text)}


def check_hallucinated_sources(answer_text: str, matches: list[tuple[float, dict]]) -> list[str]:
    allowed = allowed_doc_numbers(matches)
    if not allowed:
        return []
    used = find_doc_numbers_in_text(answer_text)
    return sorted([n for n in used if n not in allowed])


def validate_answer_content(answer_text: str, matches: list[tuple[float, dict]]) -> str:
    expected_numbers = []
    for _, row in matches:
        meta = row.get("metadata", {})
        n = meta.get("doc_number_file") or meta.get("doc_number_text")
        if n:
            expected_numbers.append(str(n).lower())
    has_doc_number = any(num in answer_text.lower() for num in expected_numbers[:3]) if expected_numbers else False
    has_org = any(k in answer_text.lower() for k in ORG_KEYWORDS)
    if has_doc_number and has_org:
        return "Проверка: есть ключевые сущности (реквизиты и органы)."
    if has_doc_number:
        return "Проверка: есть реквизиты документов, но не найдено упоминаний органов."
    return "Проверка: ключевые сущности найдены частично или отсутствуют."


def build_official_links_block(question: str, answer_text: str, matches: list[tuple[float, dict]]) -> str:
    parts = [question or "", answer_text or ""]
    for _, row in matches[:8]:
        meta = row.get("metadata", {}) or {}
        parts.append(doc_label(meta))
        parts.append(row.get("text", "")[:300])
    hay = "\n".join(parts).lower()

    lines: list[str] = []
    for ref in OFFICIAL_REFERENCE_LINKS:
        if any(tok in hay for tok in ref["tokens"]):
            lines.append(f"- [{ref['label']}]({ref['url']})")

    # Keep at least core official links for legal answers.
    if not lines and is_legal_query(question):
        lines = [
            "- [Росалкогольтабакконтроль (официальный сайт)](https://fsrar.gov.ru)",
            "- [Портал официальных публикаций правовых актов](http://publication.pravo.gov.ru)",
        ]
    if not lines:
        return ""
    return "### Официальные ссылки\n" + "\n".join(lines)


def answer(
    question: str,
    history: list[dict],
    top_k: int,
    official_only: bool,
    use_embeddings_rerank: bool,
    embeddings_top_n: int,
    use_llm: bool,
    llm_backend: str,
    llm_model: str,
    lora_base_model: str,
    lora_adapter_path: str,
    yandex_api_key: str,
    yandex_folder: str,
    yandex_model: str,
    yandex_embedding_model: str,
    enable_logging: bool,
    show_reasoning: bool,
    multi_step_retrieval: bool,
) -> str:
    if not question.strip():
        return "Введите вопрос по лицензированию ЕГАИС."

    top_k = max(1, min(int(top_k), 12))
    retrieval_boost = expand_query_for_activity_codes(question)
    scored = score_query(
        question,
        INDEX,
        official_only=official_only,
        retrieval_text=retrieval_boost,
    )
    embedding_diag: dict = {"enabled": bool(use_embeddings_rerank), "used": False}
    if use_embeddings_rerank:
        scored, embedding_diag = rerank_with_embeddings(
            question,
            scored,
            api_key=(yandex_api_key or "").strip(),
            folder=(yandex_folder or "").strip(),
            model=(yandex_embedding_model or "").strip(),
            top_n=embeddings_top_n,
        )
    matches = select_diverse_matches(scored, top_k)
    if not matches:
        return (
            "Не нашел релевантные фрагменты в локальной базе.\n\n"
            "Попробуйте уточнить вопрос (например, тип лицензии, номер приказа, этап процедуры)."
        )

    follow_up_trace: list[str] = []
    last_planner_reason = ""
    if use_llm and multi_step_retrieval:
        cur_matches = list(matches)
        per_q = max(2, min(6, top_k // 2 + 1))
        for _round in range(2):
            msgs = planner_messages(question, cur_matches)
            if llm_backend == "yandex_openai":
                pr = chat_with_yandex_openai(
                    api_key=yandex_api_key,
                    folder=yandex_folder,
                    model=yandex_model,
                    messages=msgs,
                    max_tokens=380,
                )
            else:
                pr = chat_with_ollama(msgs, (llm_model or DEFAULT_OLLAMA_MODEL).strip(), max_tokens=380)
            if pr.get("error") or not pr.get("text"):
                break
            follow, last_planner_reason = parse_follow_up_searches(pr["text"])
            if not follow:
                break
            follow_up_trace.extend(follow)
            extra = run_follow_up_retrieval(
                question,
                follow,
                INDEX,
                official_only=official_only,
                per_query_k=per_q,
            )
            cur_matches = merge_scored_matches(cur_matches, extra, max_total=min(22, top_k * 3))

        anchor_queries = reference_anchor_queries(question, cur_matches)
        if anchor_queries:
            follow_up_trace.extend(anchor_queries)
            anchor_extra = run_follow_up_retrieval(
                question,
                anchor_queries,
                INDEX,
                official_only=official_only,
                per_query_k=max(3, min(6, top_k)),
            )
            cur_matches = merge_scored_matches(cur_matches, anchor_extra, max_total=min(28, top_k * 4))

        article_targets = referenced_article_numbers(question, cur_matches)
        if article_targets:
            direct_hits: list[tuple[float, dict]] = []
            for article_num in article_targets[:3]:
                direct_hits.extend(law_article_direct_matches(INDEX, article_num, top_k=6))
            if direct_hits:
                cur_matches = merge_scored_matches(direct_hits, cur_matches, max_total=min(32, top_k * 4))
        matches = cur_matches

    model_name = (llm_model or DEFAULT_OLLAMA_MODEL).strip()
    prompt = ""
    llm_answer = ""
    llm_reasoning = ""
    llm_error = ""
    if use_llm:
        prompt = build_legal_prompt(question, matches)
        if llm_backend == "yandex_openai":
            llm_result = generate_with_yandex_openai(
                prompt=prompt,
                api_key=yandex_api_key,
                folder=yandex_folder,
                model=yandex_model,
            )
        elif llm_backend == "local_lora":
            llm_result = generate_with_local_lora(
                prompt=prompt,
                base_model=lora_base_model,
                adapter_path=lora_adapter_path,
                max_tokens=1000,
            )
        else:
            llm_result = generate_with_ollama(prompt, model_name)
        llm_answer = llm_result.get("text", "")
        llm_reasoning = llm_result.get("reasoning", "")
        llm_error = llm_result.get("error", "")
        if llm_answer and not llm_error:
            main_answer = llm_answer
            if "### Источники" not in main_answer:
                main_answer = f"{main_answer}\n\n{sources_block(matches)}"
        else:
            main_answer = template_legal_answer(question, matches) + "\n\n" + (llm_error or "")
    elif is_legal_query(question):
        main_answer = template_legal_answer(question, matches)
    else:
        main_answer = "Найдены релевантные фрагменты из базы:\n\n" + format_context(matches)

    if is_legal_query(question):
        digest = build_normative_digest(matches, limit=min(5, len(matches)))
        main_answer = (
            f"{main_answer}\n\n"
            f"### Раскрытие норм из контекста\n"
            f"{digest}"
        )

    docs_block = build_documents_block_from_context(question, matches)
    if docs_block:
        main_answer = f"{main_answer}\n\n{docs_block}"

    docs_vs_req_block = build_transport_docs_vs_requirements_block(question, matches)
    if docs_vs_req_block:
        main_answer = f"{main_answer}\n\n{docs_vs_req_block}"

    main_answer = ensure_questions_to_applicant_block(main_answer, question)

    if show_reasoning:
        reasoning_text = llm_reasoning.strip() if llm_reasoning else "Рассуждение не предоставлено моделью."
        main_answer = (
            f"{main_answer}\n\n"
            f"### Рассуждение модели\n"
            f"{reasoning_text}"
        )

    hallucinated_nums = check_hallucinated_sources(main_answer, matches)
    if hallucinated_nums:
        main_answer += (
            "\n\n### Проверка источников\n"
            "Обнаружены номера НПА, которых нет в текущем retrieval-контексте: "
            + ", ".join(hallucinated_nums)
            + ". Используйте блок 'Раскрытие норм из контекста' как приоритетный."
        )

    main_answer = strip_noise_citations(main_answer)
    main_answer = dedupe_sources_sections(main_answer)
    official_links_block = build_official_links_block(question, main_answer, matches)
    if official_links_block and "### Официальные ссылки" not in main_answer:
        main_answer = f"{main_answer}\n\n{official_links_block}"

    validation = validate_answer_content(main_answer, matches)
    search_note = ""
    if follow_up_trace:
        reason_tail = f"\n(планировщик: {last_planner_reason})" if last_planner_reason else ""
        search_note = (
            "### Уточняющий поиск по индексу\n"
            + "\n".join(f"- {q}" for q in follow_up_trace)
            + f"{reason_tail}\n\n"
        )
    result = f"{search_note}{main_answer}\n\n{validation}\n\n---\n{DISCLAIMER}"
    if use_embeddings_rerank and embedding_diag.get("error"):
        result = (
            f"{result}\n\n"
            "### Embeddings re-rank\n"
            f"Отключен для этого запроса: {embedding_diag.get('error')}"
        )

    selected_model_name = (
        yandex_model
        if llm_backend == "yandex_openai"
        else (f"{(lora_base_model or '').strip()} + adapter" if llm_backend == "local_lora" else model_name)
    )

    qa_record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "question": question,
        "answer": result,
        "backend": llm_backend if use_llm else "template_only",
        "model": selected_model_name,
        "top_k": top_k,
        "official_only": official_only,
        "use_embeddings_rerank": bool(use_embeddings_rerank),
        "embeddings_top_n": int(embeddings_top_n),
        "embedding_model": (yandex_embedding_model or "").strip(),
        "embedding_diag": embedding_diag,
        "multi_step_retrieval": multi_step_retrieval,
    }
    append_qa_log(qa_record)

    if enable_logging:
        record = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "question": question,
            "backend": llm_backend if use_llm else "template_only",
            "model": selected_model_name,
            "top_k": top_k,
            "official_only": official_only,
            "use_llm": use_llm,
            "multi_step_retrieval": multi_step_retrieval,
            "use_embeddings_rerank": bool(use_embeddings_rerank),
            "embeddings_top_n": int(embeddings_top_n),
            "embedding_model": (yandex_embedding_model or "").strip(),
            "embedding_diag": embedding_diag,
            "follow_up_searches": follow_up_trace,
            "prompt": prompt,
            "response_preview": main_answer[:800],
            "reasoning_preview": llm_reasoning[:500],
            "validation": validation,
        }
        append_log(record)
    return result


CYBERPUNK_CSS = """
:root {
  --cp-bg: #070912;
  --cp-surface: #0c1324;
  --cp-text: #d8ecff;
  --cp-neon-cyan: #00f0ff;
  --cp-neon-pink: #ff2fd1;
  --cp-neon-lime: #a8ff60;
}

body.cp-theme-cyberpunk, body.cp-theme-cyberpunk .gradio-container {
  background:
    radial-gradient(circle at 20% 15%, rgba(0, 240, 255, 0.14), transparent 45%),
    radial-gradient(circle at 80% 5%, rgba(255, 47, 209, 0.14), transparent 40%),
    linear-gradient(180deg, #05070f 0%, #0b1020 55%, #060910 100%);
  color: var(--cp-text);
}

body.cp-theme-classic, body.cp-theme-classic .gradio-container {
  background: #f4f6fb !important;
  color: #1e2a3a !important;
}

.gradio-container .prose, .gradio-container .prose p, .gradio-container .prose li {
  color: #cfe6ff !important;
}

.gradio-container .message, .gradio-container .panel, .gradio-container .block {
  border-radius: 14px !important;
}

body.cp-theme-cyberpunk .gradio-container .message.bot {
  background: linear-gradient(135deg, rgba(12, 19, 36, 0.95), rgba(7, 11, 22, 0.95)) !important;
  border: 1px solid rgba(0, 240, 255, 0.35) !important;
  box-shadow: 0 0 14px rgba(0, 240, 255, 0.16), inset 0 0 30px rgba(0, 240, 255, 0.04);
}

body.cp-theme-cyberpunk .gradio-container .message.user {
  background: linear-gradient(135deg, rgba(26, 9, 35, 0.92), rgba(14, 7, 22, 0.92)) !important;
  border: 1px solid rgba(255, 47, 209, 0.35) !important;
  box-shadow: 0 0 14px rgba(255, 47, 209, 0.14), inset 0 0 24px rgba(255, 47, 209, 0.05);
}

body.cp-theme-classic .gradio-container .message.bot {
  background: #ffffff !important;
  border: 1px solid #dce6ff !important;
  box-shadow: 0 4px 16px rgba(22, 42, 88, 0.08);
}

body.cp-theme-classic .gradio-container .message.user {
  background: #edf2ff !important;
  border: 1px solid #c9d8ff !important;
  box-shadow: 0 4px 16px rgba(22, 42, 88, 0.08);
}

body.cp-theme-cyberpunk .gradio-container textarea, body.cp-theme-cyberpunk .gradio-container input {
  background: rgba(7, 12, 24, 0.9) !important;
  border: 1px solid rgba(0, 240, 255, 0.35) !important;
  color: var(--cp-text) !important;
  box-shadow: inset 0 0 10px rgba(0, 240, 255, 0.08);
}

body.cp-theme-classic .gradio-container textarea,
body.cp-theme-classic .gradio-container input {
  background: #ffffff !important;
  border: 1px solid #cfdbff !important;
  color: #162130 !important;
}

body.cp-theme-cyberpunk .gradio-container button.primary {
  background: linear-gradient(90deg, rgba(0, 240, 255, 0.2), rgba(255, 47, 209, 0.22)) !important;
  border: 1px solid rgba(0, 240, 255, 0.6) !important;
  color: #ecfbff !important;
  box-shadow: 0 0 14px rgba(0, 240, 255, 0.28);
}

body.cp-theme-classic .gradio-container button.primary {
  background: linear-gradient(90deg, #4978ff, #6ea1ff) !important;
  border: 1px solid #335de0 !important;
  color: #fff !important;
}

body.cp-theme-cyberpunk .gradio-container h1,
body.cp-theme-cyberpunk .gradio-container h2,
body.cp-theme-cyberpunk .gradio-container h3 {
  color: #e9f7ff !important;
  text-shadow: 0 0 10px rgba(0, 240, 255, 0.42);
}

.cp-term {
  display: inline-block;
  padding: 0.06rem 0.36rem;
  margin: 0 0.12rem;
  border: 1px solid rgba(0, 240, 255, 0.55);
  border-radius: 8px;
  background: linear-gradient(90deg, rgba(0, 240, 255, 0.16), rgba(168, 255, 96, 0.14));
  color: #eefffa;
  text-shadow: 0 0 8px rgba(0, 240, 255, 0.45);
  cursor: pointer;
  transition: all 0.16s ease;
}

.cp-term:hover {
  border-color: rgba(255, 47, 209, 0.8);
  box-shadow: 0 0 12px rgba(255, 47, 209, 0.35), 0 0 18px rgba(0, 240, 255, 0.28);
  transform: translateY(-1px);
}

body.cp-theme-classic .cp-term {
  border-color: #4c79ff;
  background: linear-gradient(90deg, rgba(73, 120, 255, 0.14), rgba(83, 170, 255, 0.12));
  color: #163067;
  text-shadow: none;
}

@keyframes cpMessageIn {
  from {
    opacity: 0;
    transform: translateY(8px) scale(0.99);
    filter: blur(1px);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
    filter: blur(0);
  }
}

.cp-msg-animated {
  animation: cpMessageIn 0.3s ease-out;
}

#cp-theme-toggle {
  position: fixed;
  top: 16px;
  right: 18px;
  z-index: 9999;
  border: 1px solid rgba(0, 240, 255, 0.5);
  border-radius: 999px;
  background: rgba(6, 11, 22, 0.78);
  color: #dff8ff;
  font-size: 12px;
  letter-spacing: .03em;
  padding: 8px 12px;
  cursor: pointer;
  box-shadow: 0 0 12px rgba(0, 240, 255, 0.2);
}

body.cp-theme-classic #cp-theme-toggle {
  background: #ffffff;
  color: #1f345b;
  border-color: #8eadff;
  box-shadow: 0 6px 16px rgba(26, 49, 102, 0.15);
}

#cp-term-panel {
  position: fixed;
  right: 16px;
  bottom: 20px;
  width: min(320px, 40vw);
  max-height: 48vh;
  overflow: auto;
  z-index: 9998;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid rgba(0, 240, 255, 0.35);
  background: linear-gradient(165deg, rgba(8, 14, 27, 0.92), rgba(12, 10, 26, 0.92));
  box-shadow: 0 0 18px rgba(0, 240, 255, 0.16);
  backdrop-filter: blur(6px);
}

body.cp-theme-classic #cp-term-panel {
  border: 1px solid #c6d8ff;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 10px 24px rgba(26, 49, 102, 0.14);
}

.cp-term-panel-title {
  font-size: 12px;
  margin-bottom: 8px;
  opacity: 0.9;
  text-transform: uppercase;
  letter-spacing: .06em;
}

.cp-term-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.cp-term-pill {
  border: 1px solid rgba(0, 240, 255, 0.48);
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
  background: rgba(0, 240, 255, 0.12);
  color: #dff9ff;
}

body.cp-theme-classic .cp-term-pill {
  border-color: #8ea9ff;
  background: #edf3ff;
  color: #1f345b;
}

@media (max-width: 960px) {
  #cp-term-panel {
    width: calc(100vw - 20px);
    right: 10px;
    left: 10px;
    bottom: 10px;
  }
}
"""

CYBERPUNK_JS = r"""
() => {
  if (window.__cpTermClickBound) return;
  window.__cpTermClickBound = true;

  const root = document.querySelector('.gradio-container') || document.body;
  const THEME_KEY = 'egais_theme_mode';
  const TERMS_KEY = 'egais_term_history';
  const MAX_TERMS = 20;
  const TERM_WORDS = [
    'Федеральный закон', 'Постановление', 'Приказ',
    'Росалкогольтабакконтроль', 'Росалкогольрегулирование',
    'ЕГАИС', 'Госуслуги', 'лицензия', 'лицензируемой деятельности',
    'заявление', 'госпошлина', 'переоформление', 'продление'
  ];

  const escapeRegExp = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const containsCpTerm = (node) => !!(node.parentElement && node.parentElement.closest('.cp-term'));
  const inCodeBlock = (node) => !!(node.parentElement && node.parentElement.closest('code, pre'));

  const createHighlightedFragment = (text) => {
    const patterns = [
      /(№\s*[0-9]{1,5}(?:-[0-9A-Za-zА-Яа-я]+)?)/gi,
      /(стать[ьяи]\s+\d+(?:\.\d+)?)/gi,
      /(пункт[а-я]*\s+\d+(?:\.\d+)?)/gi,
      /(подпункт[а-я]*\s+\d+(?:\.\d+)?)/gi,
    ];
    const termsRe = new RegExp(`\\b(${TERM_WORDS.sort((a, b) => b.length - a.length).map(escapeRegExp).join('|')})\\b`, 'gi');
    patterns.push(termsRe);

    let html = text;
    patterns.forEach((re) => {
      html = html.replace(re, (m) => `<span class="cp-term" data-term="${m.replace(/"/g, '&quot;')}">${m}</span>`);
    });
    if (html === text) return null;
    const tpl = document.createElement('template');
    tpl.innerHTML = html;
    return tpl.content;
  };

  const sendTerm = (term) => {
    const localRoot = document.querySelector('.gradio-container');
    if (!localRoot) return;
    const textarea = localRoot.querySelector('textarea');
    if (!textarea) return;
    textarea.focus();
    textarea.value = term;
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    const sendBtn = [...localRoot.querySelectorAll('button')].find((btn) => {
      const label = ((btn.getAttribute('aria-label') || '') + ' ' + (btn.textContent || '')).toLowerCase();
      return /submit|send|отправ/.test(label);
    });
    if (sendBtn) setTimeout(() => sendBtn.click(), 50);
  };

  const highlightTermsInMessages = () => {
    const messageBodies = document.querySelectorAll('.gradio-container .message .prose, .gradio-container .message .message-body');
    messageBodies.forEach((msg) => {
      const walker = document.createTreeWalker(msg, NodeFilter.SHOW_TEXT);
      const targets = [];
      let n;
      while ((n = walker.nextNode())) {
        if (!n.nodeValue || !n.nodeValue.trim()) continue;
        if (containsCpTerm(n) || inCodeBlock(n)) continue;
        targets.push(n);
      }
      targets.forEach((textNode) => {
        const frag = createHighlightedFragment(textNode.nodeValue);
        if (frag) textNode.replaceWith(frag);
      });
    });
  };

  const getTerms = () => {
    try {
      const data = JSON.parse(localStorage.getItem(TERMS_KEY) || '[]');
      return Array.isArray(data) ? data : [];
    } catch (_) {
      return [];
    }
  };

  const saveTerms = (terms) => {
    localStorage.setItem(TERMS_KEY, JSON.stringify(terms.slice(0, MAX_TERMS)));
  };

  const renderTermPanel = () => {
    let panel = document.getElementById('cp-term-panel');
    if (!panel) {
      panel = document.createElement('aside');
      panel.id = 'cp-term-panel';
      panel.innerHTML = '<div class="cp-term-panel-title">Term Matrix</div><div class="cp-term-list"></div>';
      document.body.appendChild(panel);
    }
    const list = panel.querySelector('.cp-term-list');
    const terms = getTerms();
    list.innerHTML = '';
    if (!terms.length) {
      const empty = document.createElement('div');
      empty.style.opacity = '0.7';
      empty.style.fontSize = '12px';
      empty.textContent = 'Кликните термин в чате, чтобы добавить сюда.';
      list.appendChild(empty);
      return;
    }
    terms.forEach((term) => {
      const el = document.createElement('button');
      el.type = 'button';
      el.className = 'cp-term-pill';
      el.textContent = term;
      el.addEventListener('click', () => sendTerm(term));
      list.appendChild(el);
    });
  };

  const pushTerm = (term) => {
    if (!term) return;
    const current = getTerms().filter((x) => x.toLowerCase() !== term.toLowerCase());
    current.unshift(term);
    saveTerms(current);
    renderTermPanel();
  };

  const applyTheme = (mode) => {
    document.body.classList.remove('cp-theme-cyberpunk', 'cp-theme-classic');
    document.body.classList.add(mode === 'classic' ? 'cp-theme-classic' : 'cp-theme-cyberpunk');
    localStorage.setItem(THEME_KEY, mode);
    const toggle = document.getElementById('cp-theme-toggle');
    if (toggle) {
      toggle.textContent = mode === 'classic' ? 'Theme: Classic' : 'Theme: Cyberpunk';
    }
  };

  const ensureThemeToggle = () => {
    let toggle = document.getElementById('cp-theme-toggle');
    if (!toggle) {
      toggle = document.createElement('button');
      toggle.id = 'cp-theme-toggle';
      toggle.type = 'button';
      document.body.appendChild(toggle);
      toggle.addEventListener('click', () => {
        const isClassic = document.body.classList.contains('cp-theme-classic');
        applyTheme(isClassic ? 'cyberpunk' : 'classic');
      });
    }
    const saved = localStorage.getItem(THEME_KEY) || 'cyberpunk';
    applyTheme(saved);
  };

  const animateNewMessages = () => {
    const nodes = document.querySelectorAll('.gradio-container .message');
    nodes.forEach((node) => {
      if (node.dataset.cpAnimated) return;
      node.dataset.cpAnimated = '1';
      node.classList.add('cp-msg-animated');
      setTimeout(() => node.classList.remove('cp-msg-animated'), 420);
    });
  };

  const observer = new MutationObserver(() => {
    animateNewMessages();
    highlightTermsInMessages();
  });
  observer.observe(root, { childList: true, subtree: true });

  document.addEventListener('click', (evt) => {
    const chip = evt.target.closest('.cp-term');
    if (!chip) return;
    const term = (chip.dataset.term || chip.textContent || '').trim();
    if (!term) return;
    pushTerm(term);
    sendTerm(term);
  });

  ensureThemeToggle();
  renderTermPanel();
  animateNewMessages();
  highlightTermsInMessages();
}
"""

with gr.Blocks() as demo:
    with gr.Accordion("Настройки", open=False):
        top_k_input = gr.Slider(
            minimum=1,
            maximum=12,
            value=6,
            step=1,
            label="Top-K (количество найденных фрагментов)",
        )
        official_only_input = gr.Checkbox(
            value=True,
            label="Только официальные НПА (рекомендуется)",
        )
        embeddings_rerank_input = gr.Checkbox(
            value=False,
            label="Embeddings re-rank (гибридный retrieval)",
        )
        embeddings_top_n_input = gr.Slider(
            minimum=10,
            maximum=80,
            value=40,
            step=1,
            label="Embeddings re-rank top-N кандидатов",
        )
        use_llm_input = gr.Checkbox(
            value=True,
            label="LLM-режим",
        )
        llm_backend_input = gr.Radio(
            choices=["ollama", "yandex_openai", "local_lora"],
            value="yandex_openai",
            label="LLM backend",
        )
        ollama_model_input = gr.Textbox(
            value=DEFAULT_OLLAMA_MODEL,
            label="Модель Ollama",
            placeholder="например: qwen2.5:0.5b",
        )
        lora_base_model_input = gr.Textbox(
            value=DEFAULT_LORA_BASE_MODEL,
            label="Local LoRA base model",
            placeholder="например: Qwen/Qwen2.5-1.5B-Instruct",
        )
        lora_adapter_path_input = gr.Textbox(
            value=DEFAULT_LORA_ADAPTER_PATH,
            label="Local LoRA adapter path",
            placeholder="/path/to/adapter",
        )
        yandex_api_key_input = gr.Textbox(
            value=DEFAULT_YANDEX_API_KEY,
            type="password",
            label="Yandex Cloud API key",
            placeholder="AQV...",
        )
        yandex_folder_input = gr.Textbox(
            value=DEFAULT_YANDEX_FOLDER,
            label="Yandex Cloud folder",
            placeholder="b1g...",
        )
        yandex_model_input = gr.Textbox(
            value=DEFAULT_YANDEX_MODEL,
            label="Yandex Cloud model",
            placeholder="deepseek-v32/latest",
        )
        yandex_embedding_model_input = gr.Textbox(
            value=DEFAULT_YANDEX_EMBEDDING_MODEL,
            label="Yandex embedding model",
            placeholder="text-search-query/latest",
        )
        enable_logging_input = gr.Checkbox(
            value=False,
            label="Логирование в файл",
        )
        show_reasoning_input = gr.Checkbox(
            value=False,
            label="Показывать рассуждение модели",
        )
        multi_step_input = gr.Checkbox(
            value=False,
            label="Многошаговый retrieval (модель может запросить уточняющий поиск)",
        )

    gr.ChatInterface(
        fn=answer,
        additional_inputs=[
            top_k_input,
            official_only_input,
            embeddings_rerank_input,
            embeddings_top_n_input,
            use_llm_input,
            llm_backend_input,
            ollama_model_input,
            lora_base_model_input,
            lora_adapter_path_input,
            yandex_api_key_input,
            yandex_folder_input,
            yandex_model_input,
            yandex_embedding_model_input,
            enable_logging_input,
            show_reasoning_input,
            multi_step_input,
        ],
        title="EGAIS Normatives Assistant (локально)",
        description=(
            "Локальный поиск по нормативным документам ЕГАИС с юридическим шаблоном. "
            "LLM: Ollama или Yandex Cloud (OpenAI-compatible API)."
        ),
    )


if __name__ == "__main__":
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        css=CYBERPUNK_CSS,
        js=CYBERPUNK_JS,
    )
