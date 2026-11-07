"""Lab 1: federated, in-place datasources.

AutoRAG never migrates data into a central store. Each datasource keeps its own
native format and results carry opaque, source-native ids (``/slack/...``,
``/mail/...``). This loader reads three formats in place -- markdown files,
a chat export (jsonl), and a mailbox file (.eml) -- and keeps only references
plus text in memory. ``read_source`` re-reads the original file on demand,
which is the "direct evidence reading" step of the upstream agent.
"""

from __future__ import annotations

import email
import email.policy
import fnmatch
import json
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path

IGNORE_FILE = ".autoragignore"


@dataclass(frozen=True)
class Chunk:
    id: str  # source-native id, opaque to the agent
    source: str  # path relative to the corpus root
    datasource: str  # local | slack | mail
    title: str
    text: str
    updated: str  # ISO date


def read_ignore(root: Path) -> list[str]:
    path = root / IGNORE_FILE
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]


def is_ignored(rel: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if pat.endswith("/") and (rel + "/").startswith(pat):
            return True
        if fnmatch.fnmatch(rel, pat):
            return True
    return False


def corpus_files(root: Path) -> list[str]:
    patterns = read_ignore(root)
    out = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(".") or is_ignored(rel, patterns):
            continue
        out.append(rel)
    return out


def _markdown_chunks(root: Path, rel: str) -> list[Chunk]:
    lines = (root / rel).read_text(encoding="utf-8").splitlines()
    title, updated, body = Path(rel).stem, "", []
    for line in lines:
        if line.startswith("# ") and title == Path(rel).stem:
            title = line[2:].strip()
        elif line.lower().startswith("updated:"):
            updated = line.split(":", 1)[1].strip()
        else:
            body.append(line)
    paragraphs = [p.strip() for p in "\n".join(body).split("\n\n") if p.strip()]
    return [Chunk(f"{rel}#p{i}", rel, "local", title, p, updated) for i, p in enumerate(paragraphs, 1)]


def _chat_chunks(root: Path, rel: str) -> list[Chunk]:
    channel = Path(rel).stem
    out = []
    for line in (root / rel).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        msg = json.loads(line)
        out.append(
            Chunk(
                f"/slack/{channel}/chunks/{msg['id']}",
                rel,
                "slack",
                f"#{channel}",
                f"{msg['user']}: {msg['text']}",
                msg["ts"][:10],
            )
        )
    return out


def _mail_chunks(root: Path, rel: str) -> list[Chunk]:
    msg = email.message_from_bytes((root / rel).read_bytes(), policy=email.policy.default)
    subject = str(msg["subject"] or Path(rel).stem)
    updated = parsedate_to_datetime(str(msg["date"])).date().isoformat() if msg["date"] else ""
    part = msg.get_body(preferencelist=("plain",))
    body = part.get_content() if part is not None else ""
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    stem = Path(rel).stem
    return [Chunk(f"/mail/{stem}/p{i}", rel, "mail", subject, p, updated) for i, p in enumerate(paragraphs, 1)]


_LOADERS = {".md": _markdown_chunks, ".txt": _markdown_chunks, ".jsonl": _chat_chunks, ".eml": _mail_chunks}


def load_file(root: Path, rel: str) -> list[Chunk]:
    loader = _LOADERS.get(Path(rel).suffix.lower())
    return loader(root, rel) if loader else []


def load_corpus(root: str | Path) -> list[Chunk]:
    root = Path(root)
    return [chunk for rel in corpus_files(root) for chunk in load_file(root, rel)]


def read_source(root: str | Path, chunk_id: str, source: str) -> str | None:
    """Re-read one chunk straight from its native file (ground truth)."""
    for chunk in load_file(Path(root), source):
        if chunk.id == chunk_id:
            return chunk.text
    return None
