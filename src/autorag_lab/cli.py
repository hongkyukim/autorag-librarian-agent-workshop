"""Command line: ``python -m autorag_lab <command>``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent import Librarian
from .evals import GATE, check_gate, load_golden, run_eval
from .model import MODES as MODEL_MODES
from .model import FakeModel
from .permissions import MODES as PERMISSION_MODES
from .permissions import FakeJev, PermissionGate
from .retrieval import MODES as RETRIEVAL_MODES
from .workspace import ToolCall, Workspace

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "data" / "corpus"
GOLDEN = REPO / "data" / "eval" / "golden.jsonl"


def _h(title: str) -> None:
    print(f"\n=== {title} ===")


def cmd_search(a: argparse.Namespace) -> int:
    lib = Librarian(a.corpus)
    for hit in lib.retrieve(a.query, a.k, a.mode):
        print(f"{hit.score:7.4f}  {hit.chunk.id:<38} {hit.chunk.text[:70]}")
    return 0


def cmd_ask(a: argparse.Namespace) -> int:
    lib = Librarian(a.corpus, model=FakeModel(a.model))
    ans = lib.ask(a.question, steer=a.steer)
    print(f"phases: {' -> '.join(ans.phases)}")
    if ans.verification_ran:
        print(f"fast answer: {ans.fast_text}")
    print(f"answer: {ans.text}")
    for c in ans.citations:
        print(f"  [{c.label}] {c.chunk_id}")
    for label in ans.unresolved:
        print(f"  [{label}] UNRESOLVED")
    for o in ans.tool_outcomes:
        print(f"  tool call {o.call.command!r}: {o.decision.action} -> {o.result} ({o.decision.reason})")
    return 0


def cmd_dupes(a: argparse.Namespace) -> int:
    lib = Librarian(a.corpus)
    for fam in lib.families:
        print(f"family {fam.key}")
        for m in reversed(fam.members):
            print(f"  {fam.labels[m]:<9} {m}")
    return 0


def cmd_perm(a: argparse.Namespace) -> int:
    ws = Workspace(a.corpus)
    gate = PermissionGate(ws, a.mode, FakeJev(reachable=not a.jev_down))
    d = gate.decide(ToolCall("bash", a.command), [a.request] if a.request else [])
    print(json.dumps({"mode": a.mode, "action": d.action, "flagged": d.flagged, "reason": d.reason}, indent=2))
    return 0


def _report(result: dict) -> tuple[bool, list[str]]:
    ok, failures = check_gate(result["metrics"])
    print(f"model={result['model']}")
    for name, value in result["metrics"].items():
        op, threshold = GATE[name]
        print(f"  {name:<20} {value!s:<6} (gate {op} {threshold})")
    return ok, failures


def cmd_eval(a: argparse.Namespace) -> int:
    result = run_eval(a.corpus, load_golden(a.golden), a.model)
    if a.verbose:
        for row in result["rows"]:
            print(json.dumps(row, ensure_ascii=False))
    _report(result)
    return 0


def cmd_gate(a: argparse.Namespace) -> int:
    ok, failures = _report(run_eval(a.corpus, load_golden(a.golden), a.model))
    print("GATE: PASS" if ok else "GATE: FAIL\n  " + "\n  ".join(failures))
    return 0 if ok else 1


def cmd_mcp(a: argparse.Namespace) -> int:
    from .mcp import McpServer

    McpServer(Librarian(a.corpus), read_only=a.read_only).serve()
    return 0


def cmd_demo(a: argparse.Namespace) -> int:
    lib = Librarian(a.corpus)
    _h("1. Federated sources, source-native ids (no ETL)")
    for c in lib.chunks[:: max(1, len(lib.chunks) // 6)]:
        print(f"  {c.datasource:<6} {c.id}")
    _h("2. Sparse vs dense vs hybrid: 'uptime guarantee'")
    for mode in RETRIEVAL_MODES:
        print(f"  {mode:<7} {[h.chunk.id for h in lib.index.search('uptime guarantee', 2, mode)]}")
    _h("3. Two-phase answer with [eN] citations, then a steer")
    ans = lib.ask("What is the budget?")
    print(f"  fast:    {ans.text}")
    ans = lib.ask("What is the budget?", steer="I mean the data platform proposal")
    print(f"  steered: {ans.text}  phases={ans.phases}")
    _h("4. Duplicate family: newest version is cited")
    cmd_dupes(a)
    _h("5. Permission gate (auto) vs the prompt-injection document")
    bad = Librarian(a.corpus, model=FakeModel("obey_injection"))
    for o in bad.ask("What is planned for the quarterly offsite?").tool_outcomes:
        print(f"  {o.call.command!r}: {o.decision.action} -> {o.result}")
    print(f"  files changed: {len(bad.gate.ws.changes)}")
    _h("6. Retrieval memory is advisory")
    print(f"  stored={len(lib.memory.records)} judged records; context for a repeat question:")
    print("  " + (lib.memory.context("What is the budget?") or "(none)").replace("\n", "\n  "))
    _h("7. Release gate (good model)")
    ok, _ = _report(run_eval(a.corpus, load_golden(GOLDEN), "good"))
    print("GATE: PASS" if ok else "GATE: FAIL")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="autorag_lab", description="AutoRAG Agent workshop labs (offline, stdlib only)")
    p.add_argument("--corpus", type=Path, default=CORPUS)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="walk through every lab").set_defaults(fn=cmd_demo)
    s = sub.add_parser("search", help="model-free retrieval (AutoRAG Lite)")
    s.add_argument("query")
    s.add_argument("--mode", choices=RETRIEVAL_MODES, default="hybrid")
    s.add_argument("-k", type=int, default=5)
    s.set_defaults(fn=cmd_search)
    s = sub.add_parser("ask", help="two-phase librarian answer with citations")
    s.add_argument("question")
    s.add_argument("--steer")
    s.add_argument("--model", choices=MODEL_MODES, default="good")
    s.set_defaults(fn=cmd_ask)
    sub.add_parser("dupes", help="duplicate families (Latest/Similar/Identical)").set_defaults(fn=cmd_dupes)
    s = sub.add_parser("perm", help="classify one bash call through the permission gate (never executes)")
    s.add_argument("command")
    s.add_argument("--mode", choices=PERMISSION_MODES, default="auto")
    s.add_argument("--request", help="what the user asked for in this conversation")
    s.add_argument("--jev-down", action="store_true", help="simulate an unreachable judgment model")
    s.set_defaults(fn=cmd_perm)
    for name, fn in (("eval", cmd_eval), ("gate", cmd_gate)):
        s = sub.add_parser(name)
        s.add_argument("--model", choices=MODEL_MODES, default="good")
        s.add_argument("--golden", type=Path, default=GOLDEN)
        s.add_argument("-v", "--verbose", action="store_true")
        s.set_defaults(fn=fn)
    s = sub.add_parser("mcp", help="JSON-RPC MCP-shaped server on stdio")
    s.add_argument("--read-only", action="store_true")
    s.set_defaults(fn=cmd_mcp)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
