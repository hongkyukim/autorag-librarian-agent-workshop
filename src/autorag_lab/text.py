"""Tokenizer and a toy concept embedder shared by every lab (stdlib only).

Stand-ins, labelled as such:
- ``tokens`` plays the role of MinSync's SPLADE sparse encoder. Like SPLADE it
  matches Korean inflected forms (``인증서를`` -> ``인증서``) without a tokenizer
  library, here through a tiny particle-stripping rule.
- ``embed`` plays the role of the local dense embedder: a hand-written concept
  table plus hashed character trigrams. It is enough to show a meaning-only
  match ("uptime guarantee" -> "availability commitment") that keyword search
  misses. It is not a real embedding model.
"""

from __future__ import annotations

import math
import re

_TOKEN = re.compile(r"[a-z0-9]+(?:[-.][a-z0-9]+)*|[\uac00-\ud7a3]+")
_KO_SUFFIXES = sorted(
    ["으로", "합니다", "하는", "하다", "에서", "를", "을", "는", "은", "이", "가", "의", "에", "로", "와", "과", "도"],
    key=len,
    reverse=True,
)
STOPWORDS = frozenset(
    "a an and are as at be by did do does for from how in is it its of on or that the this to was were "
    "what when where which who will with our we us you your has have after then there".split()
)

CONCEPTS: dict[str, set[str]] = {
    "uptime": {"uptime", "availability", "available", "outage", "downtime", "sla"},
    "guarantee": {"guarantee", "guaranteed", "commitment", "promise"},
    "money": {"price", "cost", "budget", "spend", "discount", "fee", "pricing", "invoice"},
    "location": {"stored", "storage", "store", "residency", "region", "located", "location", "stay", "reside"},
    "renewal": {"renewal", "renew", "expire", "expiry", "deadline", "due", "lapse", "갱신"},
    "certificate": {"certificate", "cert", "tls", "ssl", "인증서"},
    "event": {"offsite", "retreat", "meeting", "agenda"},
    "proposal": {"proposal", "bid", "quote"},
    "contract": {"contract", "agreement", "addendum", "clause"},
    "procedure": {"procedure", "step", "process", "절차", "portal"},
    "korea": {"seoul", "korea", "서울", "busan"},
    "schedule": {"timeline", "schedule", "week", "duration", "long"},
}
_WORD_TO_CONCEPT = {w: c for c, words in CONCEPTS.items() for w in words}


def _normalize(tok: str) -> str:
    if "\uac00" <= tok[0] <= "\ud7a3":
        for suffix in _KO_SUFFIXES:
            if tok.endswith(suffix) and len(tok) > len(suffix) + 1:
                return tok[: -len(suffix)]
        return tok
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss") and tok.isalpha():
        return tok[:-1]
    return tok


def tokens(text: str, keep_stop: bool = False) -> list[str]:
    out = []
    for raw in _TOKEN.findall(text.lower()):
        tok = _normalize(raw)
        if keep_stop or tok not in STOPWORDS:
            out.append(tok)
    return out


def concepts(text: str) -> set[str]:
    return {_WORD_TO_CONCEPT[t] for t in tokens(text, keep_stop=True) if t in _WORD_TO_CONCEPT}


def embed(text: str) -> dict[str, float]:
    vec: dict[str, float] = {"c:" + c: 1.0 for c in concepts(text)}
    for tok in tokens(text):
        padded = f"#{tok}#"
        for i in range(len(padded) - 2):
            key = "g:" + padded[i : i + 3]
            vec[key] = vec.get(key, 0.0) + 0.08
    return vec


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text) if s.strip()]
