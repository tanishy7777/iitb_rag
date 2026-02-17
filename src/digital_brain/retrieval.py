from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass
class SearchResult:
    score: float
    chunk_id: str
    doc_id: str
    machine_id: int | None
    doc_type: str
    text: str


@dataclass
class IndexedChunk:
    chunk_id: str
    doc_id: str
    machine_id: int | None
    doc_type: str
    text: str


class BM25Retriever:
    def __init__(self, chunks: list[IndexedChunk]) -> None:
        self.chunks = chunks
        self.doc_terms: list[Counter[str]] = []
        self.doc_lengths: list[int] = []
        self.df: Counter[str] = Counter()
        self.avg_doc_len = 1.0
        self._build()

    def _build(self) -> None:
        for chunk in self.chunks:
            tokens = tokenize(chunk.text)
            counts = Counter(tokens)
            self.doc_terms.append(counts)
            self.doc_lengths.append(sum(counts.values()))
            self.df.update(counts.keys())

        if self.doc_lengths:
            self.avg_doc_len = sum(self.doc_lengths) / len(self.doc_lengths)

    def search(self, query: str, machine_id: int | None = None, top_k: int = 5) -> list[SearchResult]:
        q_tokens = tokenize(query)
        if not q_tokens:
            return []

        n_docs = len(self.chunks)
        k1 = 1.5
        b = 0.75
        results: list[SearchResult] = []

        for idx, chunk in enumerate(self.chunks):
            if machine_id is not None and chunk.machine_id not in (None, machine_id):
                continue

            score = 0.0
            doc_len = self.doc_lengths[idx] if idx < len(self.doc_lengths) else 0
            denom_norm = k1 * (1 - b + b * (doc_len / self.avg_doc_len))
            terms = self.doc_terms[idx]

            for token in q_tokens:
                tf = terms.get(token, 0)
                if tf == 0:
                    continue
                df = self.df.get(token, 0)
                idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
                score += idf * ((tf * (k1 + 1.0)) / (tf + denom_norm))

            if score <= 0:
                continue

            results.append(
                SearchResult(
                    score=score,
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    machine_id=chunk.machine_id,
                    doc_type=chunk.doc_type,
                    text=chunk.text,
                )
            )

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:top_k]


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())
