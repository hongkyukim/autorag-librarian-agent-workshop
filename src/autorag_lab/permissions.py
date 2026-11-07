"""Lab 5: the permission gate (ask / auto / full).

Mirrors upstream ``docs/permissions.md``:
- ``auto`` (default): a judgment model ("Jev") scores six categories --
  delete, move, rename, overwrite, edit, unclear -- each a probability that the
  call does that to a file that existed before it ran. A category >= 0.2
  flags the call. A flagged call runs silently only when Jev is >= 0.8 sure the
  user's request covers exactly that change; otherwise the user is asked.
  If Jev is unreachable, the call is asked about (fail closed).
- ``ask``: every bash/write/edit call is asked about; Jev is never consulted.
- ``full``: no gate.
Files the agent created itself stay free to change (copy first, change the copy).

``FakeJev`` is a heuristic stand-in for the model. It is a teaching device,
not a parser you should ship; upstream deliberately has no command parser.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Callable

from .workspace import ToolCall, Workspace

CATEGORIES = ("delete", "move", "rename", "overwrite", "edit", "unclear")
MODES = ("ask", "auto", "full")
FLAG = 0.2
AUTO_APPROVE = 0.8
_SEGMENTS = re.compile(r"\s*(?:&&|\|\||;|\|)\s*")
_REDIRECT = re.compile(r"(>>?)\s*(\S+)")
_INTERPRETERS = {"python", "python3", "perl", "ruby", "node", "sh", "bash", "zsh", "make", "eval", "xargs"}
_READ_ONLY = {"ls", "cat", "grep", "head", "tail", "wc", "mkdir", "touch", "echo", "pwd", "stat", "file"}
_REQUEST_VERBS = {
    "delete": ("delete", "remove", "trash", "clean up"),
    "move": ("move",),
    "rename": ("rename",),
    "overwrite": ("overwrite", "replace"),
    "edit": ("edit", "fix", "change", "update"),
}


class JevUnavailable(RuntimeError):
    pass


@dataclass
class Judgment:
    probs: dict[str, float]
    covers: float
    targets: list[str]
    reason: str


class FakeJev:
    def __init__(self, reachable: bool = True):
        self.reachable = reachable

    def classify(self, call: ToolCall, user_messages: list[str], ws: Workspace) -> Judgment:
        if not self.reachable:
            raise JevUnavailable("judgment model timed out")
        probs: dict[str, float] = {c: 0.0 for c in CATEGORIES}
        targets: list[str] = []

        def bump(cat: str, p: float, paths: list[str]) -> None:
            fresh = [x for x in paths if ws.exists(x) and x not in ws.created]
            if paths and not fresh:
                return  # only agent-created or non-existent paths: free
            probs[cat] = max(probs[cat], p)
            targets.extend(fresh)

        if call.tool == "write":
            bump("overwrite", 0.9, [call.path])
        elif call.tool == "edit":
            bump("edit", 0.9, [call.path])
        else:
            for seg in _SEGMENTS.split(call.command):
                self._segment(seg, bump)
        flagged = [c for c in CATEGORIES if probs[c] >= FLAG]
        covers = self._covers(flagged, targets, user_messages)
        reason = f"flagged {flagged} on {sorted(set(targets))}" if flagged else "changes no existing file"
        return Judgment(probs, covers, sorted(set(targets)), reason)

    @staticmethod
    def _segment(seg: str, bump: Callable[[str, float, list[str]], None]) -> None:
        for op, path in _REDIRECT.findall(seg):
            bump("overwrite" if op == ">" else "edit", 0.9 if op == ">" else 0.6, [path])
        seg = _REDIRECT.sub("", seg).strip()
        if not seg:
            return
        try:
            argv = shlex.split(seg)
        except ValueError:
            bump("unclear", 0.9, [])
            return
        verb = PurePosixPath(argv[0]).name
        args = [a for a in argv[1:] if not a.startswith("-")]
        if "$" in seg or "base64" in seg or verb in _INTERPRETERS:
            deletes = any(w in seg for w in ("remove", "unlink", "rmtree", "trash", "rm "))
            bump("delete" if deletes else "unclear", 0.9 if deletes else 0.7, [])
        elif verb in ("rm", "rmdir", "unlink", "trash", "shred") or (verb == "find" and "-delete" in argv):
            bump("delete", 0.95, args)
        elif verb == "mv" and len(args) >= 2:
            same_dir = PurePosixPath(args[0]).parent == PurePosixPath(args[1]).parent
            bump("rename" if same_dir else "move", 0.9, args[:1])
        elif verb == "cp" and len(args) >= 2:
            bump("overwrite", 0.9, args[-1:])
        elif verb == "sed" and "-i" in argv:
            bump("edit", 0.9, args[-1:])
        elif verb not in _READ_ONLY and verb != "find":
            bump("unclear", 0.5, [])

    @staticmethod
    def _covers(flagged: list[str], targets: list[str], user_messages: list[str]) -> float:
        if not flagged:
            return 1.0
        said = " ".join(user_messages).lower()
        verbs_ok = all(any(v in said for v in _REQUEST_VERBS.get(c, ())) for c in flagged)
        paths_ok = bool(targets) and all(PurePosixPath(t).name.lower() in said for t in targets)
        return 0.9 if verbs_ok and paths_ok else 0.1


@dataclass
class Decision:
    action: str  # run | ask
    reason: str
    flagged: list[str] = field(default_factory=list)


@dataclass
class Outcome:
    call: ToolCall
    decision: Decision
    executed: bool
    result: str


def deny_all(call: ToolCall, decision: Decision) -> bool:
    """Non-interactive approver: nobody is at the terminal, so the answer is no."""
    return False


class PermissionGate:
    def __init__(
        self,
        workspace: Workspace,
        mode: str = "auto",
        jev: FakeJev | None = None,
        approver: Callable[[ToolCall, Decision], bool] = deny_all,
    ):
        if mode not in MODES:
            raise ValueError(f"unknown permission mode {mode!r}; expected one of {MODES}")
        self.ws, self.mode, self.jev, self.approver = workspace, mode, jev or FakeJev(), approver
        self.log: list[Outcome] = []

    def decide(self, call: ToolCall, user_messages: list[str]) -> Decision:
        if self.mode == "full":
            return Decision("run", "full mode: no gate")
        if self.mode == "ask":
            return Decision("ask", "ask mode: every bash/write/edit call is approved by the user")
        try:
            j = self.jev.classify(call, user_messages, self.ws)
        except JevUnavailable as exc:
            return Decision("ask", f"unclassified ({exc}); nothing is let through on a failure", ["unclear"])
        flagged = [c for c in CATEGORIES if j.probs[c] >= FLAG]
        if not flagged:
            return Decision("run", j.reason)
        if j.covers >= AUTO_APPROVE:
            return Decision("run", f"{j.reason}; request covers it (p={j.covers:.2f})", flagged)
        return Decision("ask", f"{j.reason}; not requested by the user (p={j.covers:.2f})", flagged)

    def submit(self, call: ToolCall, user_messages: list[str]) -> Outcome:
        decision = self.decide(call, user_messages)
        approved = decision.action == "run" or self.approver(call, decision)
        if not approved:
            outcome = Outcome(call, decision, False, "denied")
        else:
            try:
                outcome = Outcome(call, decision, True, self.ws.run(call))
            except PermissionError as exc:  # includes OutsideWorkspace
                outcome = Outcome(call, decision, False, f"refused: {exc}")
        self.log.append(outcome)
        return outcome
