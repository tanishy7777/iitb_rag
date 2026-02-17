from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TextChunk:
    chunk_id: str
    doc_id: str
    machine_id: int | None
    doc_type: str
    text: str


def build_chunks(
    doc_id: str,
    machine_id: int | None,
    doc_type: str,
    text: str,
    max_chars: int = 700,
    overlap: int = 120,
) -> list[TextChunk]:
    normalized = "\n".join(line.rstrip() for line in text.splitlines())
    paragraphs = [p.strip() for p in normalized.split("\n\n") if p.strip()]

    chunks: list[TextChunk] = []
    idx = 0
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            chunk_texts = [paragraph]
        else:
            chunk_texts = _split_long(paragraph, max_chars=max_chars, overlap=overlap)

        for piece in chunk_texts:
            chunk_id = f"{doc_id}::chunk-{idx}"
            chunks.append(
                TextChunk(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    machine_id=machine_id,
                    doc_type=doc_type,
                    text=piece,
                )
            )
            idx += 1

    return chunks


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    parts: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            split_at = text.rfind(" ", start, end)
            if split_at > start + 120:
                end = split_at
        chunk = text[start:end].strip()
        if chunk:
            parts.append(chunk)
        if end >= n:
            break
        start = max(0, end - overlap)
    return parts
