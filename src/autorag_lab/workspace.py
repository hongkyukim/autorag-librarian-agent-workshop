"""A sandboxed toy executor for the agent's file tools.

It never invokes a shell. It understands a handful of commands (``ls``,
``cat``, ``mkdir``, ``touch``, ``cp``, ``mv``, ``rm``, ``sed -i``, ``echo >``)
joined by ``&&`` or ``;``, resolves every path inside one workspace root,
refuses anything outside it, sends deletions to a workspace trash folder
instead of removing them, and records every change as ``old -> new`` so it can
be undone -- the same guarantees upstream documents for the librarian.
"""

from __future__ import annotations

import re
import shlex
import shutil
from dataclasses import dataclass, field
from pathlib import Path

TRASH = ".autorag-trash"
_SPLIT = re.compile(r"\s*(?:&&|;)\s*")
_REDIRECT = re.compile(r"^(?P<cmd>.*?)\s*(?P<op>>>?)\s*(?P<path>\S+)\s*$")


class OutsideWorkspace(PermissionError):
    pass


@dataclass
class ToolCall:
    tool: str  # bash | write | edit
    command: str = ""
    path: str = ""
    content: str = ""
    origin: str = "model"  # model | evidence (set by the harness for tracing)


@dataclass
class Workspace:
    root: Path
    created: set[str] = field(default_factory=set)
    changes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()

    # ---- path helpers -------------------------------------------------
    def resolve(self, rel: str) -> Path:
        if rel.startswith("~"):
            raise OutsideWorkspace(rel)
        p = (self.root / rel).resolve()
        if p != self.root and self.root not in p.parents:
            raise OutsideWorkspace(rel)
        return p

    def rel(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()

    def exists(self, rel: str) -> bool:
        try:
            return self.resolve(rel).exists()
        except OutsideWorkspace:
            return True  # conservative: assume something real lives there

    # ---- execution ----------------------------------------------------
    def run(self, call: ToolCall) -> str:
        if call.tool == "write":
            return self._write(call.path, call.content, append=False)
        if call.tool == "edit":
            return self._edit(call.path, call.content)
        return "\n".join(self._bash(seg) for seg in _SPLIT.split(call.command.strip()) if seg)

    def _bash(self, segment: str) -> str:
        m = _REDIRECT.match(segment)
        if m and m["cmd"].startswith("echo"):
            text = " ".join(shlex.split(m["cmd"])[1:]) + "\n"
            return self._write(m["path"], text, append=m["op"] == ">>")
        argv = shlex.split(segment)
        verb, args = argv[0], [a for a in argv[1:] if not a.startswith("-")]
        handler = getattr(self, f"_cmd_{verb}", None)
        if handler is None:
            raise PermissionError(f"command not supported in the lab sandbox: {verb}")
        if verb == "sed":
            return self._cmd_sed(argv[1:])
        return handler(args)

    def _cmd_ls(self, args: list[str]) -> str:
        p = self.resolve(args[0] if args else ".")
        return "\n".join(sorted(c.name for c in p.iterdir() if c.name != TRASH))

    def _cmd_echo(self, args: list[str]) -> str:
        return " ".join(args)

    def _cmd_cat(self, args: list[str]) -> str:
        return "".join(self.resolve(a).read_text(encoding="utf-8") for a in args)

    def _cmd_mkdir(self, args: list[str]) -> str:
        for a in args:
            p = self.resolve(a)
            if not p.exists():
                p.mkdir(parents=True)
                self.created.add(self.rel(p))
                self.changes.append(f"created {self.rel(p)}/")
        return ""

    def _cmd_touch(self, args: list[str]) -> str:
        for a in args:
            p = self.resolve(a)
            if not p.exists():
                p.touch()
                self.created.add(self.rel(p))
                self.changes.append(f"created {self.rel(p)}")
        return ""

    def _cmd_cp(self, args: list[str]) -> str:
        src, dst = self.resolve(args[0]), self.resolve(args[1])
        existed = dst.exists()
        shutil.copy2(src, dst)
        if not existed:
            self.created.add(self.rel(dst))
        self.changes.append(f"{'overwrote' if existed else 'copied'} {self.rel(src)} -> {self.rel(dst)}")
        return ""

    def _cmd_mv(self, args: list[str]) -> str:
        src, dst = self.resolve(args[0]), self.resolve(args[1])
        shutil.move(src, dst)
        if self.rel(src) in self.created:
            self.created.discard(self.rel(src))
            self.created.add(self.rel(dst))
        self.changes.append(f"moved {self.rel(src)} -> {self.rel(dst)}")
        return ""

    def _cmd_rm(self, args: list[str]) -> str:
        trash = self.root / TRASH
        trash.mkdir(exist_ok=True)
        for a in args:
            src = self.resolve(a)
            dst = trash / src.name
            n = 1
            while dst.exists():
                dst = trash / f"{src.name}.{n}"
                n += 1
            shutil.move(src, dst)
            self.changes.append(f"trashed {self.rel(src)} -> {self.rel(dst)}")
        return ""

    _cmd_trash = _cmd_rm

    def _cmd_sed(self, argv: list[str]) -> str:
        if "-i" not in argv:
            raise PermissionError("only `sed -i 's/old/new/' file` is supported")
        expr, target = [a for a in argv if a != "-i"][:2]
        _, old, new, *_ = expr.split(expr[1])
        return self._edit(target, old + "\x00" + new)

    def _write(self, rel: str, text: str, append: bool) -> str:
        p = self.resolve(rel)
        existed = p.exists()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a" if append else "w", encoding="utf-8") as fh:
            fh.write(text)
        if not existed:
            self.created.add(self.rel(p))
        self.changes.append(f"{'edited' if existed and append else 'overwrote' if existed else 'created'} {self.rel(p)}")
        return ""

    def _edit(self, rel: str, spec: str) -> str:
        old, new = spec.split("\x00", 1)
        p = self.resolve(rel)
        p.write_text(p.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
        self.changes.append(f"edited {self.rel(p)}")
        return ""
