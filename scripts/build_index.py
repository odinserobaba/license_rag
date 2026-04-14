#!/usr/bin/env python3
import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path


TOKEN_RE = re.compile(r"[a-zA-Zа-яА-Я0-9]{2,}")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build lightweight lexical TF-IDF index from chunks")
    parser.add_argument("--chunks-jsonl", default="processed/chunks.jsonl")
    parser.add_argument("--output", default="processed/lexical_index.json")
    args = parser.parse_args()

    chunks_path = Path(args.chunks_jsonl)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    docs = []
    df = defaultdict(int)

    with chunks_path.open("r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            tokens = tokenize(rec["text"])
            if not tokens:
                continue
            tf = Counter(tokens)
            docs.append(
                {
                    "chunk_id": rec["chunk_id"],
                    "doc_id": rec["doc_id"],
                    "text": rec["text"],
                    "metadata": rec.get("metadata", {}),
                    "tf": dict(tf),
                    "len": len(tokens),
                }
            )
            for tok in tf:
                df[tok] += 1

    n_docs = len(docs)
    idf = {tok: math.log((n_docs + 1) / (freq + 1)) + 1.0 for tok, freq in df.items()}

    out = {
        "n_docs": n_docs,
        "idf": idf,
        "docs": docs,
    }
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)

    print(f"Indexed chunks: {n_docs}")
    print(f"Saved index: {out_path}")


if __name__ == "__main__":
    main()
