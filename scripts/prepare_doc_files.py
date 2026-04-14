#!/usr/bin/env python3
import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_docx_text(path: Path) -> str:
    with ZipFile(path, "r") as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<[^>]+>", " ", xml)
    return clean_text(xml)


def run_cmd(cmd: list[str]) -> str | None:
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except Exception:
        return None
    return cp.stdout


def extract_doc_text(path: Path) -> str | None:
    antiword = shutil.which("antiword")
    if antiword:
        out = run_cmd([antiword, str(path)])
        if out and out.strip():
            return clean_text(out)

    catdoc = shutil.which("catdoc")
    if catdoc:
        out = run_cmd([catdoc, str(path)])
        if out and out.strip():
            return clean_text(out)

    # Fallback via LibreOffice headless conversion, if installed
    lowriter = shutil.which("lowriter") or shutil.which("libreoffice")
    if lowriter:
        with tempfile.TemporaryDirectory(prefix="doc_convert_") as tmp:
            cmd = [lowriter, "--headless", "--convert-to", "txt:Text", "--outdir", tmp, str(path)]
            try:
                subprocess.run(cmd, capture_output=True, text=True, check=True)
            except Exception:
                return None
            txt_path = Path(tmp) / f"{path.stem}.txt"
            if txt_path.exists():
                return clean_text(txt_path.read_text(encoding="utf-8", errors="replace"))

    return None


def infer_doc_type(text: str) -> str | None:
    m = re.search(r"\b(ПРИКАЗ|ПОСТАНОВЛЕНИЕ|РАСПОРЯЖЕНИЕ|ФЕДЕРАЛЬНЫЙ\s+ЗАКОН)\b", text)
    return m.group(1) if m else None


def read_text_file(path: Path) -> str:
    for enc in ("utf-8", "cp1251", "windows-1251"):
        try:
            return clean_text(path.read_text(encoding=enc))
        except Exception:
            continue
    return clean_text(path.read_text(encoding="utf-8", errors="replace"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare extra corpus records from .doc/.docx/.txt/.md files")
    parser.add_argument("--input-dir", default="doc")
    parser.add_argument("--txt-dir", default="processed/clean_txt")
    parser.add_argument("--jsonl", default="processed/extra_docs.jsonl")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    txt_dir = Path(args.txt_dir)
    out_jsonl = Path(args.jsonl)
    txt_dir.mkdir(parents=True, exist_ok=True)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(
        list(input_dir.glob("*.doc"))
        + list(input_dir.glob("*.DOC"))
        + list(input_dir.glob("*.docx"))
        + list(input_dir.glob("*.DOCX"))
        + list(input_dir.glob("*.txt"))
        + list(input_dir.glob("*.TXT"))
        + list(input_dir.glob("*.md"))
        + list(input_dir.glob("*.MD"))
    )
    if not files:
        out_jsonl.write_text("", encoding="utf-8")
        print("No .doc/.docx/.txt/.md files found")
        print(f"JSONL file: {out_jsonl}")
        return

    records = []
    skipped: list[str] = []
    for path in files:
        suffix = path.suffix.lower()
        if suffix == ".docx":
            text = extract_docx_text(path)
        elif suffix == ".doc":
            text = extract_doc_text(path)
        else:
            text = read_text_file(path)

        if not text:
            skipped.append(path.name)
            continue

        rec_id = f"{path.stem}_extra"
        txt_path = txt_dir / f"{rec_id}.txt"
        txt_path.write_text(text, encoding="utf-8")
        meta = {
            "source_file": path.name,
            "doc_type": infer_doc_type(text),
            "doc_number_file": None,
            "doc_date_file": None,
            "doc_number_text": None,
            "title_guess": None,
        }
        records.append({"id": rec_id, "metadata": meta, "text": text})

    with out_jsonl.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Processed extra files (.doc/.docx/.txt/.md): {len(records)}")
    print(f"Skipped extra files: {len(skipped)}")
    if skipped:
        print("Skipped list:", ", ".join(skipped))
        print("Hint: install antiword/catdoc/libreoffice for .doc support")
    print(f"JSONL file: {out_jsonl}")


if __name__ == "__main__":
    main()
