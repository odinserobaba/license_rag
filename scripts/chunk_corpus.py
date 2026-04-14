#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


BOUNDARY_RE = re.compile(
    r"^(Глава\s+\d+|Статья\s+\d+|Раздел\s+[IVXLC]+|\d+\.\s|[а-я]\)\s)",
    re.IGNORECASE,
)


def split_to_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in text.split("\n") if p.strip()]
    return parts


def chunk_paragraphs(paragraphs: list[str], chunk_size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0

    for p in paragraphs:
        p_len = len(p)
        # Start new chunk on explicit legal boundary when current chunk is non-trivial
        if cur and BOUNDARY_RE.match(p) and cur_len >= max(250, chunk_size // 3):
            chunks.append("\n".join(cur).strip())
            # overlap by tail characters from previous chunk
            tail = chunks[-1][-overlap:] if overlap > 0 else ""
            cur = [tail, p] if tail else [p]
            cur_len = len("\n".join(cur))
            continue

        if cur_len + p_len + 1 > chunk_size and cur:
            chunks.append("\n".join(cur).strip())
            tail = chunks[-1][-overlap:] if overlap > 0 else ""
            cur = [tail, p] if tail else [p]
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
    parser.add_argument("--chunk-size", type=int, default=1700)
    parser.add_argument("--overlap", type=int, default=260)
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
            chunks = chunk_paragraphs(paragraphs, args.chunk_size, args.overlap)
            total_docs += 1

            for idx, chunk_text in enumerate(chunks, 1):
                chunk = {
                    "chunk_id": f"{doc_id}::chunk_{idx:04d}",
                    "doc_id": doc_id,
                    "text": chunk_text,
                    "metadata": {
                        **metadata,
                        "chunk_index": idx,
                        "chunk_chars": len(chunk_text),
                    },
                }
                out.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                total_chunks += 1

    print(f"Chunked docs: {total_docs}")
    print(f"Total chunks: {total_chunks}")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
