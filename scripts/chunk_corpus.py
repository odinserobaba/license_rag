#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


BOUNDARY_RE = re.compile(
    r"^(Глава\s+\d+|Статья\s+\d+|Раздел\s+[IVXLC]+|\d+\.\s|[а-я]\)\s)",
    re.IGNORECASE,
)
ARTICLE_HEADING_RE = re.compile(r"^Статья\s+(\d+(?:\.\d+)?)\.?\s*(.*)$", re.IGNORECASE)
CHAPTER_HEADING_RE = re.compile(r"^(Глава\s+\S+(?:\s+.+)?)$", re.IGNORECASE)
SUBPOINT_LINE_RE = re.compile(r"^\s*((?:\d+(?:\.\d+)?[.)])|(?:[а-я]\)))\s*", re.IGNORECASE)
ARTICLE_REF_RE = re.compile(r"стать[ьяеи]\s+(\d+(?:\.\d+)?)", re.IGNORECASE)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[\.\!\?;:])\s+")


def split_to_paragraphs(text: str) -> list[str]:
    lines = text.splitlines()
    parts: list[str] = []
    cur: list[str] = []

    def flush() -> None:
        if not cur:
            return
        block = re.sub(r"\s+", " ", " ".join(cur)).strip()
        if block:
            parts.append(block)
        cur.clear()

    for raw in lines:
        line = raw.strip()
        if not line:
            flush()
            continue

        is_heading = bool(
            BOUNDARY_RE.match(line)
            or ARTICLE_HEADING_RE.match(line)
            or CHAPTER_HEADING_RE.match(line)
        )

        # Keep legal headings and list-item starters as separate semantic units.
        if is_heading and cur:
            flush()
        if is_heading:
            parts.append(line)
            continue

        cur.append(line)
    flush()

    if len(parts) < 2:
        # Fallback for noisy OCR-like texts.
        return [p.strip() for p in text.split("\n") if p.strip()]
    return parts


def is_federal_law_doc(rec: dict) -> bool:
    meta = rec.get("metadata", {}) or {}
    doc_type = (meta.get("doc_type") or "").upper()
    source_file = (meta.get("source_file") or "").lower()
    text = rec.get("text", "")
    return (
        doc_type == "ФЕДЕРАЛЬНЫЙ ЗАКОН"
        or "фз" in source_file
        or bool(re.search(r"\b171-ФЗ\b", text, re.IGNORECASE))
    )


def split_article_blocks(paragraphs: list[str]) -> list[dict]:
    blocks: list[dict] = []
    cur = {"article_number": None, "article_title": None, "chapter_title": None, "paragraphs": []}
    chapter_title = None

    for p in paragraphs:
        ch = CHAPTER_HEADING_RE.match(p)
        if ch:
            chapter_title = ch.group(1).strip()
            if cur["paragraphs"]:
                blocks.append(cur)
                cur = {
                    "article_number": None,
                    "article_title": None,
                    "chapter_title": chapter_title,
                    "paragraphs": [],
                }
            else:
                cur["chapter_title"] = chapter_title
            cur["paragraphs"].append(p)
            continue

        art = ARTICLE_HEADING_RE.match(p)
        if art:
            if cur["paragraphs"]:
                blocks.append(cur)
            cur = {
                "article_number": art.group(1).strip(),
                "article_title": p.strip(),
                "chapter_title": chapter_title,
                "paragraphs": [p],
            }
            continue

        cur["paragraphs"].append(p)

    if cur["paragraphs"]:
        blocks.append(cur)
    return blocks


def extract_subpoint_refs(text: str, limit: int = 25) -> list[str]:
    refs: list[str] = []
    for line in text.split("\n"):
        m = SUBPOINT_LINE_RE.match(line)
        if not m:
            continue
        token = m.group(1).strip()
        if token not in refs:
            refs.append(token)
        if len(refs) >= limit:
            break
    return refs


def extract_cited_article_refs(text: str, limit: int = 25) -> list[str]:
    refs: list[str] = []
    for m in ARTICLE_REF_RE.finditer(text):
        token = m.group(1).strip()
        if token not in refs:
            refs.append(token)
        if len(refs) >= limit:
            break
    return refs


def chunk_paragraphs(paragraphs: list[str], chunk_size: int, overlap: int) -> list[str]:
    def split_long_paragraph(p: str) -> list[str]:
        if len(p) <= chunk_size:
            return [p]
        sentences = SENTENCE_SPLIT_RE.split(p)
        if len(sentences) <= 1:
            return [p[i : i + chunk_size] for i in range(0, len(p), chunk_size)]

        out: list[str] = []
        cur_sent: list[str] = []
        cur_len = 0
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if cur_sent and cur_len + len(s) + 1 > chunk_size:
                out.append(" ".join(cur_sent).strip())
                cur_sent = [s]
                cur_len = len(s)
            else:
                cur_sent.append(s)
                cur_len += len(s) + 1
        if cur_sent:
            out.append(" ".join(cur_sent).strip())
        return out or [p]

    def overlap_tail(prev: list[str], overlap_chars: int) -> list[str]:
        if overlap_chars <= 0 or not prev:
            return []
        acc: list[str] = []
        total = 0
        for para in reversed(prev):
            acc.insert(0, para)
            total += len(para) + 1
            if total >= overlap_chars:
                break
        return acc

    normalized: list[str] = []
    for p in paragraphs:
        normalized.extend(split_long_paragraph(p))

    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    min_chunk = max(300, chunk_size // 3)

    for p in normalized:
        p_len = len(p)
        # Start new chunk on explicit legal boundary when current chunk is non-trivial
        if cur and BOUNDARY_RE.match(p) and cur_len >= min_chunk:
            chunks.append("\n".join(cur).strip())
            tail = overlap_tail(cur, overlap)
            cur = tail + [p]
            cur_len = len("\n".join(cur))
            continue

        if cur_len + p_len + 1 > chunk_size and cur:
            chunks.append("\n".join(cur).strip())
            tail = overlap_tail(cur, overlap)
            cur = tail + [p]
            cur_len = len("\n".join(cur))
        else:
            cur.append(p)
            cur_len += p_len + 1

    if cur:
        chunks.append("\n".join(cur).strip())
    return [c for c in chunks if c]


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunk cleaned legal corpus into RAG-ready fragments")
    parser.add_argument("--input-jsonl", default="processed/cleaned_docs.jsonl")
    parser.add_argument("--output-jsonl", default="processed/chunks.jsonl")
    parser.add_argument("--chunk-size", type=int, default=2200)
    parser.add_argument("--overlap", type=int, default=320)
    args = parser.parse_args()

    input_path = Path(args.input_jsonl)
    output_path = Path(args.output_jsonl)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_docs = 0
    total_chunks = 0

    with input_path.open("r", encoding="utf-8") as src, output_path.open("w", encoding="utf-8") as out:
        for line in src:
            if not line.strip():
                continue
            rec = json.loads(line)
            doc_id = rec["id"]
            text = rec["text"]
            metadata = rec.get("metadata", {})
            paragraphs = split_to_paragraphs(text)
            article_blocks = split_article_blocks(paragraphs) if is_federal_law_doc(rec) else None
            total_docs += 1

            if article_blocks:
                chunk_idx = 0
                for block in article_blocks:
                    block_chunks = chunk_paragraphs(block["paragraphs"], args.chunk_size, args.overlap)
                    for chunk_text in block_chunks:
                        chunk_idx += 1
                        article_number = block.get("article_number")
                        cited_refs = extract_cited_article_refs(chunk_text)
                        if article_number and article_number not in cited_refs:
                            cited_refs.insert(0, article_number)
                        chunk = {
                            "chunk_id": f"{doc_id}::chunk_{chunk_idx:04d}",
                            "doc_id": doc_id,
                            "text": chunk_text,
                            "metadata": {
                                **metadata,
                                "chunk_index": chunk_idx,
                                "chunk_chars": len(chunk_text),
                                "chapter_title": block.get("chapter_title"),
                                "article_number": article_number,
                                "article_title": block.get("article_title"),
                                "subpoint_refs": extract_subpoint_refs(chunk_text),
                                "cited_article_refs": cited_refs,
                            },
                        }
                        out.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                        total_chunks += 1
            else:
                chunks = chunk_paragraphs(paragraphs, args.chunk_size, args.overlap)
                for idx, chunk_text in enumerate(chunks, 1):
                    chunk = {
                        "chunk_id": f"{doc_id}::chunk_{idx:04d}",
                        "doc_id": doc_id,
                        "text": chunk_text,
                        "metadata": {
                            **metadata,
                            "chunk_index": idx,
                            "chunk_chars": len(chunk_text),
                            "subpoint_refs": extract_subpoint_refs(chunk_text),
                            "cited_article_refs": extract_cited_article_refs(chunk_text),
                        },
                    }
                    out.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                    total_chunks += 1

    print(f"Chunked docs: {total_docs}")
    print(f"Total chunks: {total_chunks}")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
