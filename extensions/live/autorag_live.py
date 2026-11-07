#!/usr/bin/env python3
"""Run the same workshop corpus through the real AutoRAG Agent CLI.

Dry-run by default: prints every command and touches nothing. ``--run``
executes them with an isolated ``AUTORAG_HOME`` under ``out/live-home`` so your
personal ``~/.autorag`` config is left alone, and indexes a *copy* of
``data/corpus`` under ``out/live-corpus``.

Prerequisites for --run: Node.js >= 24 (or Bun) and ``npm install -g
@autorag/librarian`` (bins: ``autorag``, ``autorag-mcp``). ``autorag search``
also needs one chat model configured (``autorag tui`` then ``/login`` and
``/model``); the Lite steps (status, duplicates, MCP tools/list) are model-free.

Command shapes come from the upstream README (verified against
@autorag/librarian 2.13.x). Flags drift between releases: if a step fails,
check ``autorag --help`` for your version rather than trusting this script.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "data" / "corpus"
OUT = REPO / "out"
LIVE_CORPUS = OUT / "live-corpus"
LIVE_HOME = OUT / "live-home"

STEPS: list[tuple[str, list[str], bool]] = [
    # (label, argv, needs_model)
    ("init (model-free Lite workspace)", ["autorag", "lite", "init", "--search-paths", str(LIVE_CORPUS)], False),
    ("refresh: parse + MinSync sparse/dense chunks", ["autorag", "lite", "refresh"], False),
    ("status", ["autorag", "status", "--json"], False),
    ("duplicates (Lab 4 on the real engine)", ["autorag", "duplicates", str(LIVE_CORPUS / "docs"), "--json"], False),
    ("search (two-phase librarian, needs a model)", ["autorag", "search", "What budget did the final proposal settle on?", "--json"], True),
    (
        "search with the injection doc, permission gate in auto",
        ["autorag", "search", "What is planned for the quarterly offsite?", "--json", "--permission-mode", "auto"],
        True,
    ),
]

MCP_PROBE = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "workshop-probe", "version": "0"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
]


def env() -> dict[str, str]:
    e = dict(os.environ)
    e["AUTORAG_HOME"] = str(LIVE_HOME)
    e["AUTORAG_NO_UPDATE_CHECK"] = "1"
    return e


def mcp_tools(config: Path) -> list[str]:
    e = env() | {"AUTORAG_CONFIG": str(config)}
    payload = "".join(json.dumps(m) + "\n" for m in MCP_PROBE)
    proc = subprocess.run(["autorag-mcp"], input=payload, capture_output=True, text=True, env=e, timeout=60)
    names = []
    for line in proc.stdout.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == 2:
            names = [t["name"] for t in msg.get("result", {}).get("tools", [])]
    return names


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--run", action="store_true", help="execute (default: dry-run)")
    ap.add_argument("--with-model", action="store_true", help="also run steps that need a configured chat model")
    args = ap.parse_args()

    if not args.run:
        print("DRY RUN (pass --run to execute). Commands, with AUTORAG_HOME=out/live-home:\n")
        print(f"  cp -r {CORPUS.relative_to(REPO)} {LIVE_CORPUS.relative_to(REPO)}")
        for label, argv, needs_model in STEPS:
            tag = " [needs model: --with-model]" if needs_model else ""
            print(f"  # {label}{tag}\n  {' '.join(repr(a) if ' ' in a else a for a in argv)}")
        print("  # MCP discovery (read the tool list, never hard-code it)")
        print("  AUTORAG_CONFIG=<config.json> autorag-mcp  <<< initialize + tools/list")
        return 0

    if not shutil.which("autorag"):
        print("autorag not found. Install: npm install -g @autorag/librarian (Node >= 24)", file=sys.stderr)
        return 2
    if LIVE_CORPUS.exists():
        shutil.rmtree(LIVE_CORPUS)
    shutil.copytree(CORPUS, LIVE_CORPUS)
    LIVE_HOME.mkdir(parents=True, exist_ok=True)
    for label, argv, needs_model in STEPS:
        if needs_model and not args.with_model:
            print(f"-- skip: {label} (pass --with-model)")
            continue
        print(f"-- {label}\n$ {' '.join(argv)}", flush=True)
        rc = subprocess.run(argv, env=env()).returncode
        if rc != 0:
            print(f"step failed with exit {rc}; check `autorag --help` for your version", file=sys.stderr)
            return rc
    configs = sorted(LIVE_HOME.rglob("config.json"))
    if configs and shutil.which("autorag-mcp"):
        print(f"-- MCP tools/list via {configs[0]}")
        print("   " + ", ".join(mcp_tools(configs[0])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
