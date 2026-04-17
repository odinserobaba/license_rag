#!/usr/bin/env python3
"""
Прогон набора вопросов через app.answer с Yandex Cloud и эвристической оценкой.

Пример (максимум возможностей retrieval + длинный ответ):
  YANDEX_CLOUD_MODEL=yandexgpt-5-lite/latest \\
  YANDEX_CLOUD_MAX_TOKENS=4000 \\
  ./.venv/bin/python scripts/eval_yandex_suite.py \\
    --questions data/test/eval_questions.jsonl \\
    --out-jsonl processed/yandex_eval_20.jsonl \\
    --out-md processed/yandex_eval_20_report.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as app_module  # noqa: E402


def heuristic_score(answer: str, expected: list[str]) -> tuple[float, int, int]:
    low = (answer or "").lower()
    hits = 0
    for token in expected:
        t = (token or "").strip().lower()
        if not t:
            continue
        if t in low:
            hits += 1
    n = len([x for x in expected if (x or "").strip()])
    if n == 0:
        return 1.0, 0, 0
    return hits / n, hits, n


def suspicious_doc_hits(text: str) -> list[str]:
    """Грубая эвристика: номера НПА в ответе, которых нет в типовом наборе проекта."""
    known = {
        "171",
        "199",
        "2466",
        "1720",
        "648",
        "735",
        "268",
        "398",
        "402",
        "405",
        "397",
        "423",
        "453",
        "99",
    }
    found = set(re.findall(r"№\s*(\d{3,4})\b", text, flags=re.IGNORECASE))
    found |= set(re.findall(r"\b(\d{3,4})-ФЗ\b", text, flags=re.IGNORECASE))
    return sorted(x for x in found if x not in known)


def verdict_from_score(ratio: float, susp: list[str]) -> str:
    if susp and len(susp) >= 3:
        # Strong content hit but noisy references -> partial, not hard fail.
        return "partial" if ratio >= 0.85 else "bad"
    if ratio >= 0.85:
        return "ok"
    if ratio >= 0.5:
        return "partial"
    return "bad"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", default="data/test/eval_questions.jsonl")
    parser.add_argument("--out-jsonl", default="processed/yandex_eval_20.jsonl")
    parser.add_argument("--out-md", default="processed/yandex_eval_20_report.md")
    parser.add_argument("--top-k", type=int, default=12)
    parser.add_argument("--embeddings-top-n", type=int, default=80)
    parser.add_argument(
        "--full-corpus",
        action="store_true",
        help="Не ограничивать выборку только НПА (official_only=False), подтянуть guide/прочее",
    )
    parser.add_argument(
        "--exclude-topics",
        default="",
        help="Список тем через запятую для исключения из прогона (пример: розница,помещения)",
    )
    parser.add_argument(
        "--exclude-ids",
        default="",
        help="Список id вопросов через запятую для исключения из прогона (пример: q06,q08)",
    )
    args = parser.parse_args()

    qpath = ROOT / args.questions
    out_jsonl = ROOT / args.out_jsonl
    out_md = ROOT / args.out_md
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    with qpath.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    exclude_topics = {
        x.strip().lower()
        for x in (args.exclude_topics or "").split(",")
        if x.strip()
    }
    exclude_ids = {
        x.strip().lower()
        for x in (args.exclude_ids or "").split(",")
        if x.strip()
    }
    if exclude_topics or exclude_ids:
        filtered_rows: list[dict] = []
        for rec in rows:
            topic = str(rec.get("topic") or "").strip().lower()
            qid = str(rec.get("id") or "").strip().lower()
            if topic in exclude_topics or qid in exclude_ids:
                continue
            filtered_rows.append(rec)
        rows = filtered_rows

    meta = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "model": app_module.DEFAULT_YANDEX_MODEL,
        "embedding_model": app_module.DEFAULT_YANDEX_EMBEDDING_MODEL,
        "max_output_tokens": app_module.YANDEX_MAX_OUTPUT_TOKENS,
        "top_k": args.top_k,
        "embeddings_top_n": args.embeddings_top_n,
        "official_only": not args.full_corpus,
        "multi_step_retrieval": True,
        "use_embeddings_rerank": True,
        "answer_mode": "full",
        "exclude_topics": sorted(exclude_topics),
        "exclude_ids": sorted(exclude_ids),
        "questions_total": len(rows),
    }

    summary_rows: list[dict] = []

    with out_jsonl.open("w", encoding="utf-8") as jout:
        jout.write(json.dumps({"type": "run_meta", **meta}, ensure_ascii=False) + "\n")
        for rec in rows:
            qid = rec.get("id", "")
            question = rec.get("question", "")
            expected = rec.get("expected_sources") or []
            topic = rec.get("topic", "")

            reply = app_module.answer(
                question=question,
                history=[],
                top_k=args.top_k,
                official_only=not args.full_corpus,
                use_embeddings_rerank=True,
                embeddings_top_n=args.embeddings_top_n,
                use_llm=True,
                llm_backend="yandex_openai",
                llm_model=app_module.DEFAULT_OLLAMA_MODEL,
                lora_base_model=app_module.DEFAULT_LORA_BASE_MODEL,
                lora_adapter_path=app_module.DEFAULT_LORA_ADAPTER_PATH,
                yandex_api_key=app_module.DEFAULT_YANDEX_API_KEY,
                yandex_folder=app_module.DEFAULT_YANDEX_FOLDER,
                yandex_model=app_module.DEFAULT_YANDEX_MODEL,
                yandex_embedding_model=app_module.DEFAULT_YANDEX_EMBEDDING_MODEL,
                enable_logging=False,
                show_reasoning=True,
                multi_step_retrieval=True,
                answer_mode="full",
            )

            ratio, hits, nexp = heuristic_score(reply, expected)
            susp = suspicious_doc_hits(reply)
            v = verdict_from_score(ratio, susp)
            out_rec = {
                "id": qid,
                "topic": topic,
                "question": question,
                "expected_sources": expected,
                "answer": reply,
                "score_ratio": round(ratio, 3),
                "expected_hits": hits,
                "expected_total": nexp,
                "suspicious_doc_numbers": susp,
                "verdict": v,
            }
            jout.write(json.dumps(out_rec, ensure_ascii=False) + "\n")
            summary_rows.append(
                {
                    "id": qid,
                    "topic": topic,
                    "hit_ratio": f"{hits}/{nexp}",
                    "score": f"{ratio:.2f}",
                    "susp": len(susp),
                    "verdict": v,
                }
            )

    # Markdown report
    lines = [
        "# Yandex Cloud: прогон eval-набора",
        "",
        f"- Время (UTC): `{meta['ts']}`",
        f"- Модель: `{meta['model']}`",
        f"- Embeddings: `{meta['embedding_model']}`, top-N={meta['embeddings_top_n']}, re-rank=ON",
        f"- Retrieval: top_k={meta['top_k']}, multi_step=ON, official_only={meta['official_only']}",
        f"- max_output_tokens (YANDEX_CLOUD_MAX_TOKENS): {meta['max_output_tokens']}",
        "",
        "## Сводка",
        "",
        "| id | Тема | Попадание expected | Оценка | Подозр. № | Вердикт |",
        "|---|---|---|---|---|---|",
    ]
    for s in summary_rows:
        lines.append(
            f"| {s['id']} | {s['topic']} | {s['hit_ratio']} | {s['score']} | {s['susp']} | {s['verdict']} |"
        )
    ok = sum(1 for s in summary_rows if s["verdict"] == "ok")
    partial = sum(1 for s in summary_rows if s["verdict"] == "partial")
    bad = sum(1 for s in summary_rows if s["verdict"] == "bad")
    lines.extend(
        [
            "",
            f"Итого: ok={ok}, partial={partial}, bad={bad} (из {len(summary_rows)}).",
            "",
            "Эвристика: доля вхождений `expected_sources` в тексте ответа (нижний регистр); "
            "«подозрительные» номера — вне короткого whitelist проекта.",
            "",
            f"Полные ответы: `{out_jsonl.relative_to(ROOT)}`",
        ]
    )
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_jsonl} and {out_md}")


if __name__ == "__main__":
    main()
