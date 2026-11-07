"""Lab 3 + capstone: the librarian harness.

Upstream flow, reduced to its contracts:
1. Retrieve (hybrid), collapse duplicate families to their latest member.
2. Every retrieved chunk enters an evidence ledger with an id ``eN``.
3. Fast phase: the model answers with inline ``[eN]`` citations.
4. Verification phase: the harness resolves every citation against the ledger
   (or a corpus file for ``[file:path]``), flags unresolved and stale ones, and
   asks the model to revise. A user *steer* always forces verification and
   re-retrieves with the correction.
5. Tool calls the model proposes go through the permission gate.
6. Cited evidence is judged and stored in retrieval memory (advisory only).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .corpus import corpus_files, load_corpus, read_source
from .dedupe import Family, find_duplicates
from .memory import Citation, RetrievalMemory
from .model import Evidence, FakeModel, Reply
from .permissions import Outcome, PermissionGate
from .retrieval import Hit, Index
from .workspace import Workspace

_CITE = re.compile(r"\[(e\d+|file:[^\]]+)\]")


@dataclass
class Answer:
    question: str
    text: str
    fast_text: str
    citations: list[Citation]
    unresolved: list[str]
    stale: list[str]
    verification_ran: bool
    phases: list[str] = field(default_factory=list)
    tool_outcomes: list[Outcome] = field(default_factory=list)
    memory_stored: int = 0
    memory_dropped: int = 0


class EvidenceLedger:
    def __init__(self) -> None:
        self.items: dict[str, Evidence] = {}
        self._by_chunk: dict[str, str] = {}

    def add(self, hit: Hit, family_members: list[str]) -> Evidence:
        if hit.chunk.id in self._by_chunk:
            return self.items[self._by_chunk[hit.chunk.id]]
        eid = f"e{len(self.items) + 1}"
        ev = Evidence(eid, hit.chunk, family_members)
        self.items[eid] = ev
        self._by_chunk[hit.chunk.id] = eid
        return ev


class Librarian:
    def __init__(
        self,
        root: str | Path,
        model: FakeModel | None = None,
        gate: PermissionGate | None = None,
        memory: RetrievalMemory | None = None,
        k: int = 4,
    ):
        self.root = Path(root)
        self.k = k
        self.refresh()
        self.model = model or FakeModel()
        if self.model.read_file is None:
            self.model.read_file = self.read_file
        self.gate = gate or PermissionGate(Workspace(self.root))
        self.memory = memory or RetrievalMemory()

    # ---- indexing -----------------------------------------------------
    def refresh(self) -> None:
        self.chunks = load_corpus(self.root)
        self.index = Index(self.chunks)
        self.families: list[Family] = find_duplicates(self.root, self.chunks)
        self._family_of = {m: f for f in self.families for m in f.members}
        self._files = set(corpus_files(self.root))

    def read_file(self, rel: str) -> str:
        """Direct evidence read (the upstream agent uses ``bash cat``)."""
        if rel not in self._files:
            return ""
        return "\n".join(c.text for c in self.chunks if c.source == rel)

    # ---- retrieval with duplicate collapse ----------------------------
    def retrieve(self, query: str, k: int | None = None, mode: str = "hybrid") -> list[Hit]:
        k = k or self.k
        out: list[Hit] = []
        seen: set[str] = set()
        for hit in self.index.search(query, k * 3, mode):
            fam = self._family_of.get(hit.chunk.source)
            if fam and hit.chunk.source != fam.latest:
                same = hit.chunk.id.split("#")[-1]
                swap = next((c for c in self.chunks if c.source == fam.latest and c.id.endswith("#" + same)), None)
                if swap is None:
                    continue
                hit = Hit(swap, hit.score, hit.method)
            if hit.chunk.id not in seen:
                seen.add(hit.chunk.id)
                out.append(hit)
            if len(out) == k:
                break
        return out

    # ---- citation resolution ------------------------------------------
    def resolve(self, text: str, ledger: EvidenceLedger) -> tuple[list[Citation], list[str], list[str]]:
        citations, unresolved, stale = [], [], []
        for label in dict.fromkeys(_CITE.findall(text)):
            if label.startswith("file:"):
                rel = label[5:]
                if rel in self._files:
                    citations.append(Citation(label, rel, rel, self.read_file(rel)))
                else:
                    unresolved.append(label)
            elif label in ledger.items:
                ch = ledger.items[label].chunk
                grounded = read_source(self.root, ch.id, ch.source)
                if grounded is None:
                    unresolved.append(label)
                else:
                    citations.append(Citation(label, ch.source, ch.id, grounded))
            else:
                unresolved.append(label)
        for c in citations:
            fam = self._family_of.get(c.source)
            if fam and c.source != fam.latest:
                stale.append(c.label)
        return citations, unresolved, stale

    # ---- the two-phase search -----------------------------------------
    def _evidence(self, query: str, ledger: EvidenceLedger) -> list[Evidence]:
        evs = []
        for hit in self.retrieve(query):
            fam = self._family_of.get(hit.chunk.source)
            evs.append(ledger.add(hit, fam.members if fam else []))
        return evs

    def ask(self, question: str, steer: str | None = None) -> Answer:
        ledger = EvidenceLedger()
        phases = ["retrieve"]
        evidence = self._evidence(question, ledger)
        reply: Reply = self.model.answer(question, evidence, self.memory.context(question))
        fast_text = reply.text
        phases.append("fast-answer")
        citations, unresolved, stale = self.resolve(reply.text, ledger)

        problems = [f"unresolved citation {u}" for u in unresolved] + [f"stale version cited {s}" for s in stale]
        verification_ran = bool(problems or steer)
        if verification_ran:
            phases.append("verification")
            query = question
            if steer:
                query = f"{question} {steer}"
                problems.append(f"user steer: {steer}")
                evidence = self._evidence(steer, ledger) + self._evidence(query, ledger)
            revised = self.model.revise(query, evidence, reply, problems)
            revised.tool_calls = reply.tool_calls + revised.tool_calls
            reply = revised
            citations, unresolved, stale = self.resolve(reply.text, ledger)

        user_messages = [question] + ([steer] if steer else [])
        outcomes = [self.gate.submit(call, user_messages) for call in reply.tool_calls]
        stored, dropped = self.memory.judge_and_store(question, reply.text, citations, uuid.uuid4().hex[:8])
        phases.append("final-answer")
        return Answer(
            question, reply.text, fast_text, citations, unresolved, stale, verification_ran,
            phases, outcomes, len(stored), len(dropped),
        )
