"""Lab 4: duplicate document families ("Spot the twins").

Upstream: ``autorag duplicates`` (backed by ``dupey``) groups exact and
near-duplicate documents and labels each member Latest / Similar / Identical.
Here: files whose names normalise to the same stem (``proposal-v3``,
``proposal-final``, ``proposal (1)``) form a family; identical content is
detected by hash, near-duplicates by word-set Jaccard, and the newest
``updated:`` date wins (a copy-suffixed name loses a tie).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from .corpus import Chunk
from .text import tokens

_COPY = re.compile(r"\s*\(\d+\)$")
_VERSION = re.compile(r"[-_ ]+(v\d+|final|draft|copy|latest|rev\d*)$")
SIMILAR_JACCARD = 0.6


def family_key(rel: str) -> str:
    p = Path(rel)
    stem = p.stem.lower()
    while True:
        new = _VERSION.sub("", _COPY.sub("", stem))
        if new == stem:
            break
        stem = new
    return (p.parent / stem).as_posix()


@dataclass
class Family:
    key: str
    members: list[str]  # sorted oldest -> newest
    latest: str
    labels: dict[str, str] = field(default_factory=dict)


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def find_duplicates(root: str | Path, chunks: list[Chunk]) -> list[Family]:
    root = Path(root)
    updated: dict[str, str] = {}
    for c in chunks:
        if c.datasource == "local":
            updated.setdefault(c.source, c.updated)
    groups: dict[str, list[str]] = {}
    for rel in updated:
        groups.setdefault(family_key(rel), []).append(rel)

    families = []
    for key, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        has_copy_marker = lambda rel: bool(_COPY.search(Path(rel).stem))  # noqa: E731
        members.sort(key=lambda rel: (updated[rel], not has_copy_marker(rel), rel))
        latest = members[-1]
        text = {rel: (root / rel).read_text(encoding="utf-8") for rel in members}
        digest = {rel: hashlib.sha256(" ".join(t.split()).lower().encode()).hexdigest() for rel, t in text.items()}
        words = {rel: set(tokens(" ".join(c.text for c in chunks if c.source == rel))) for rel in members}
        labels = {latest: "Latest"}
        for rel in members:
            if rel == latest:
                continue
            if digest[rel] == digest[latest]:
                labels[rel] = "Identical"
            elif _jaccard(words[rel], words[latest]) >= SIMILAR_JACCARD:
                labels[rel] = "Similar"
            else:
                labels[rel] = "Related"
        families.append(Family(key, members, latest, labels))
    return families
