"""Lab 2: sparse + dense + hybrid retrieval.

Upstream: MinSync fuses SPLADE sparse and dense vector ranking over the same
CDC chunks. Here: BM25 (sparse stand-in), the toy concept embedder (dense
stand-in), and Reciprocal Rank Fusion with k=60 for hybrid.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from .corpus import Chunk
from .text import cosine, embed, tokens

RRF_K = 60
MODES = ("sparse", "dense", "hybrid")


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float
    method: str


class Index:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.k1, self.b = k1, b
        self._tf = [Counter(tokens(f"{c.title} {c.text}")) for c in chunks]
        self._len = [sum(tf.values()) for tf in self._tf]
        self._avg = (sum(self._len) / len(self._len)) if chunks else 0.0
        df: Counter[str] = Counter()
        for tf in self._tf:
            df.update(tf.keys())
        n = len(chunks)
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self._vec = [embed(f"{c.title} {c.text}") for c in chunks]

    def sparse(self, query: str, k: int = 5) -> list[Hit]:
        q = tokens(query)
        scored = []
        for i, tf in enumerate(self._tf):
            s = 0.0
            for t in q:
                f = tf.get(t, 0)
                if f:
                    norm = 1 - self.b + self.b * self._len[i] / self._avg
                    s += self._idf[t] * f * (self.k1 + 1) / (f + self.k1 * norm)
            if s > 0:
                scored.append(Hit(self.chunks[i], s, "sparse"))
        return sorted(scored, key=lambda h: -h.score)[:k]

    def dense(self, query: str, k: int = 5, floor: float = 0.05) -> list[Hit]:
        qv = embed(query)
        scored = [Hit(c, cosine(qv, v), "dense") for c, v in zip(self.chunks, self._vec)]
        return sorted([h for h in scored if h.score > floor], key=lambda h: -h.score)[:k]

    def hybrid(self, query: str, k: int = 5, depth: int = 50) -> list[Hit]:
        fused: dict[str, float] = {}
        by_id: dict[str, Chunk] = {}
        for ranking in (self.sparse(query, depth), self.dense(query, depth)):
            for rank, hit in enumerate(ranking, 1):
                fused[hit.chunk.id] = fused.get(hit.chunk.id, 0.0) + 1.0 / (RRF_K + rank)
                by_id[hit.chunk.id] = hit.chunk
        ranked = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
        return [Hit(by_id[cid], score, "hybrid") for cid, score in ranked]

    def search(self, query: str, k: int = 5, mode: str = "hybrid") -> list[Hit]:
        if mode not in MODES:
            raise ValueError(f"unknown retrieval mode {mode!r}; expected one of {MODES}")
        return getattr(self, mode)(query, k)
