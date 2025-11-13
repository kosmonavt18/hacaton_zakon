#!/usr/bin/env python3
"""
split_articles.py

Разбивает .docx файлы на отдельные статьи (батчи) и сохраняет в JSONL.
Запуск:
  python split_articles.py --input-dir ./docs --output-dir ./out

Зависимости:
  pip install python-docx
"""
import argparse
import json
import re
from pathlib import Path
from docx import Document

# Подберите/добавьте паттерны под ваши документы
DEFAULT_PATTERNS = [
    r'(?m)^(Статья|СТАТЬЯ|Стаття|Article)\s+№?\s*\d+[\s\.\-–—:]',  # "Статья 1."
    r'(?m)^Ст\.\?\s*\d+[\s\.\-–—:]',  # "Ст. 1."
    r'(?m)^Статья\s+№?\s*\d+\b',     # "Статья №1"
]

def paragraphs_to_text(doc):
    paras = []
    for p in doc.paragraphs:
        text = p.text.strip()
        if text:
            paras.append({
                "text": text,
                "style": getattr(p.style, "name", ""),
                "is_bold": any((run.bold or False) for run in p.runs if run.text.strip())
            })
    return paras

def split_by_paragraph_markers(paras, patterns):
    pattern = re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE | re.MULTILINE)
    boundaries = []
    for idx, p in enumerate(paras):
        txt = p["text"]
        # Стиль заголовка
        if p["style"] and "heading" in p["style"].lower() and re.search(r'статья|стаття|article', txt, re.I):
            boundaries.append(idx); continue
        # Жирный заголовок, если совпадает по regex
        if p["is_bold"] and re.search(r'^\s*(Статья|Стаття|Article)\s+№?\s*\d+', txt, re.I):
            boundaries.append(idx); continue
        # Текстовый паттерн в отдельном параграфе
        if pattern.search(txt):
            boundaries.append(idx)
    if not boundaries:
        return None
    articles = []
    for i, start_idx in enumerate(boundaries):
        end_idx = boundaries[i+1] if i+1 < len(boundaries) else len(paras)
        chunk_text = "\n".join(p["text"] for p in paras[start_idx:end_idx]).strip()
        header = paras[start_idx]["text"].split("\n", 1)[0]
        articles.append({"header": header, "text": chunk_text, "start_para": start_idx, "end_para": end_idx-1})
    return articles

def split_by_text_regex(full_text, patterns):
    combined = "(" + ")|(".join(patterns) + ")"
    pattern = re.compile(combined, re.IGNORECASE | re.MULTILINE)
    matches = list(pattern.finditer(full_text))
    if not matches:
        return None
    articles = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i+1].start() if i+1 < len(matches) else len(full_text)
        chunk = full_text[start:end].strip()
        header_line = chunk.splitlines()[0] if chunk.splitlines() else ""
        articles.append({"header": header_line, "text": chunk, "start_char": start, "end_char": end})
    return articles

def extract_articles_from_docx(path, patterns):
    doc = Document(path)
    paras = paragraphs_to_text(doc)
    articles = split_by_paragraph_markers(paras, patterns)
    if articles:
        return articles
    full_text = "\n".join(p["text"] for p in paras)
    articles = split_by_text_regex(full_text, patterns)
    if articles:
        return articles
    # Фоллбек: весь документ как одна запись
    return [{"header": "(full document)", "text": full_text, "fallback": True}]

def save_articles_jsonl(articles, source_path, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = Path(source_path).stem
    out_file = out_dir / f"{base}.jsonl"
    with out_file.open("a", encoding="utf-8") as fh:
        for i, a in enumerate(articles, start=1):
            m = re.search(r'(?:Статья|Стаття|Article)\s+№?\s*(\d+)', a["header"], re.IGNORECASE)
            num = m.group(1) if m else str(i)
            obj = {
                "id": f"{base}_article_{num}",
                "article_number": num,
                "title": a["header"],
                "text": a["text"],
                "source_file": str(source_path),
                "meta": {k: v for k, v in a.items() if k not in ("header", "text")}
            }
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return out_file

def process_dir(input_dir, output_dir, patterns):
    input_dir = Path(input_dir)
    files = list(input_dir.glob("*.docx"))
    if not files:
        print("Нет .docx файлов в каталоге:", input_dir)
        return
    for p in files:
        print("Обрабатываю:", p.name)
        try:
            articles = extract_articles_from_docx(p, patterns)
            out_file = save_articles_jsonl(articles, p, output_dir)
            print(f"  -> сохранено {len(articles)} записей в {out_file}")
        except Exception as e:
            print("  Ошибка при обработке", p.name, e)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", "-i", required=True, help="Папка с .docx")
    ap.add_argument("--output-dir", "-o", required=True, help="Куда сохранять JSONL")
    ap.add_argument("--add-pattern", "-p", action="append", help="Добавить regex паттерн (raw python regex). Можно несколько")
    args = ap.parse_args()

    patterns = DEFAULT_PATTERNS.copy()
    if args.add_pattern:
        patterns = args.add_pattern + patterns

    process_dir(args.input_dir, args.output_dir, patterns)

if __name__ == "__main__":
    main()