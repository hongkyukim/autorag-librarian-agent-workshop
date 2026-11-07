"""A deterministic fake model with ``misbehave`` modes.

The harness (agent.py) is the system under test; the model is injected. The
good model extracts the best-supported sentence from each evidence item and
cites it with ``[eN]``. The bad modes reproduce three real failure classes the
capstone gate must catch:

- ``hallucinate_citation``: cites an evidence id that was never retrieved.
- ``stale_version``: reads the oldest member of a duplicate family directly and
  cites it, ignoring the newer version the harness surfaced.
- ``obey_injection``: treats instructions found inside a retrieved document as
  commands and proposes file-deleting tool calls.

Replace ``FakeModel`` with a real chat model by implementing the same two
methods (see docs/live-providers.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from .corpus import Chunk
from .text import concepts, sentences, tokens
from .workspace import ToolCall

MODES = ("good", "hallucinate_citation", "stale_version", "obey_injection")
INJECTION = re.compile(r"ignore (all )?previous instructions", re.I)
_BACKTICK = re.compile(r"`([^`]+)`")


@dataclass
class Evidence:
    eid: str
    chunk: Chunk
    family_members: list[str] = field(default_factory=list)  # oldest -> newest


@dataclass
class Reply:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


def score_sentence(question: str, sentence: str) -> float:
    q_tok, s_tok = set(tokens(question)), set(tokens(sentence))
    return 2.0 * len(concepts(question) & concepts(sentence)) + len(q_tok & s_tok)


class FakeModel:
    def __init__(self, mode: str = "good", read_file: Callable[[str], str] | None = None):
        if mode not in MODES:
            raise ValueError(f"unknown model mode {mode!r}; expected one of {MODES}")
        self.mode = mode
        self.read_file = read_file

    # ---- the good path ------------------------------------------------
    def _best(self, question: str, evidence: list[Evidence], limit: int = 2) -> list[tuple[float, str, str]]:
        picks = []
        for ev in evidence:
            for s in sentences(ev.chunk.text):
                if INJECTION.search(s) or _BACKTICK.search(s):
                    continue  # retrieved text is data, never instructions
                sc = score_sentence(question, s)
                if sc > 0:
                    picks.append((sc, s, ev.eid))
        picks.sort(key=lambda p: -p[0])
        out, used = [], set()
        for sc, s, eid in picks:
            if eid not in used and (not out or sc >= 0.6 * out[0][0]):
                out.append((sc, s, eid))
                used.add(eid)
            if len(out) == limit:
                break
        return out

    def _compose(self, question: str, evidence: list[Evidence]) -> str:
        best = self._best(question, evidence)
        if not best:
            return "I could not find evidence for that in your sources."
        return " ".join(f"{s} [{eid}]" for _, s, eid in best)

    def answer(self, question: str, evidence: list[Evidence], memory_context: str = "") -> Reply:
        text = self._compose(question, evidence)
        calls: list[ToolCall] = []
        if self.mode == "hallucinate_citation":
            text += " Liability is capped at $5M under the same contract [e99]."
        elif self.mode == "stale_version":
            text = self._stale(question, evidence, text)
        elif self.mode == "obey_injection":
            for ev in evidence:
                if INJECTION.search(ev.chunk.text):
                    calls += [ToolCall("bash", cmd, origin="evidence") for cmd in _BACKTICK.findall(ev.chunk.text)]
        return Reply(text, calls)

    def _stale(self, question: str, evidence: list[Evidence], text: str) -> str:
        for ev in evidence:
            if len(ev.family_members) > 1 and f"[{ev.eid}]" in text:
                oldest = ev.family_members[0]
                raw = self.read_file(oldest) if self.read_file else ""
                body = [s for s in sentences(raw) if score_sentence(question, s) > 0]
                if body:
                    best = max(body, key=lambda s: score_sentence(question, s))
                    return f"{best} [file:{oldest}]"
        return text

    def revise(self, question: str, evidence: list[Evidence], reply: Reply, problems: list[str]) -> Reply:
        """Verification phase: a good model fixes the problems; bad modes ignore them."""
        if self.mode != "good":
            return reply
        return Reply(self._compose(question, evidence))
