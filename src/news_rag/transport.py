import json
import re
from pathlib import Path
from typing import List


def split_text_by_paragraph_or_period(text: str, target_size: int = 300) -> List[str]:
    if not isinstance(text, str):
        return []

    clean_text = text.strip()
    if not clean_text:
        return []

    paragraphs = [paragraph.strip() for paragraph in re.split(r"\r?\n+", clean_text) if paragraph.strip()]

    units: List[str] = []
    for paragraph in paragraphs:
        sentences = [sentence.strip() for sentence in re.findall(r"[^???!??;]+[???!??;]?", paragraph) if sentence.strip()]
        units.extend(sentences if sentences else [paragraph])

    chunks: List[str] = []
    current = ""
    for unit in units:
        if len(unit) >= target_size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(unit)
            continue

        if not current:
            current = unit
            continue

        if len(current) + len(unit) <= target_size:
            current += unit
        else:
            chunks.append(current)
            current = unit

    if current:
        chunks.append(current)

    return chunks


def convert_articles_to_jsonl(input_file: str | Path, output_file: str | Path, chunk_size: int = 300) -> None:
    input_path = Path(input_file)
    output_path = Path(output_file)

    with input_path.open("r", encoding="utf-8") as infile, output_path.open("w", encoding="utf-8") as outfile:
        articles = json.load(infile)

        for article_index, article in enumerate(articles, start=1):
            title = article.get("title", "")
            url = article.get("url", "")
            publish_info = article.get("pusblish_info", "")
            content = article.get("content", "")

            chunks = split_text_by_paragraph_or_period(content, target_size=chunk_size)
            if not chunks:
                continue

            total = len(chunks)
            for chunk_id, chunk in enumerate(chunks, start=1):
                prompt = (
                    f"??: {title}\n"
                    f"URL: {url}\n"
                    f"????: {publish_info}\n"
                    f"??: {chunk_id}/{total}\n\n"
                )
                completion = f"??: {chunk}"
                json_line = json.dumps(
                    {
                        "prompt": prompt,
                        "completion": completion,
                        "doc_id": article_index,
                        "chunk_id": chunk_id,
                        "chunk_total": total,
                    },
                    ensure_ascii=False,
                )
                outfile.write(json_line + "\n")
