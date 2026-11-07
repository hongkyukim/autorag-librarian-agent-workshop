"""Lab 6: an MCP-shaped server (JSON-RPC 2.0 over stdio).

Upstream ships ``autorag-mcp`` (AutoRAG Lite): model-free tools such as
``autorag.status``, ``autorag.search``, ``autorag.search.files``,
``autorag.datasources.list``, ``autorag.evidence``, ``autorag.refresh`` and
``autorag.report``. Clients discover tools with ``tools/list`` and must not
hard-code a tool count. Read-only mode omits mutating tools (refresh, report).

This is a minimal, dependency-free imitation of the protocol shape -- enough to
exercise discovery and the read-only contract. Point a real MCP client at the
upstream ``autorag-mcp`` for production (docs/live-providers.md).
"""

from __future__ import annotations

import fnmatch
import json
import sys
from pathlib import Path
from typing import IO, Any

from .agent import Librarian
from .corpus import read_source

PROTOCOL_VERSION = "2025-06-18"
MUTATING = {"autorag.refresh", "autorag.report"}

_TOOLS: dict[str, dict[str, Any]] = {
    "autorag.status": {"description": "Corpus freshness and index counts.", "properties": {}},
    "autorag.search": {
        "description": "Model-free hybrid search; returns raw chunks with source-native ids.",
        "properties": {"query": {"type": "string"}, "k": {"type": "integer"}, "mode": {"type": "string"}},
        "required": ["query"],
    },
    "autorag.search.files": {
        "description": "File-name search (glob) over the indexed roots.",
        "properties": {"pattern": {"type": "string"}},
        "required": ["pattern"],
    },
    "autorag.datasources.list": {"description": "Configured datasources and chunk counts.", "properties": {}},
    "autorag.evidence": {
        "description": "Re-read one chunk from its native source.",
        "properties": {"chunk_id": {"type": "string"}, "source": {"type": "string"}},
        "required": ["chunk_id", "source"],
    },
    "autorag.refresh": {"description": "Rebuild the index (mutating).", "properties": {}},
    "autorag.report": {
        "description": "Write a markdown report into the workspace (mutating).",
        "properties": {"name": {"type": "string"}, "body": {"type": "string"}},
        "required": ["name", "body"],
    },
}


class McpServer:
    def __init__(self, librarian: Librarian, read_only: bool = False, report_dir: str | Path | None = None):
        self.lib = librarian
        self.read_only = read_only
        self.report_dir = Path(report_dir) if report_dir else librarian.root / ".autorag" / "reports"

    def tools(self) -> list[dict]:
        return [
            {
                "name": name,
                "description": spec["description"],
                "inputSchema": {"type": "object", "properties": spec["properties"], "required": spec.get("required", [])},
            }
            for name, spec in _TOOLS.items()
            if not (self.read_only and name in MUTATING)
        ]

    # ---- tool handlers ------------------------------------------------
    def _call(self, name: str, args: dict) -> Any:
        if name not in {t["name"] for t in self.tools()}:
            raise KeyError(f"unknown tool: {name}")
        lib = self.lib
        if name == "autorag.status":
            return {"chunks": len(lib.chunks), "files": len(lib._files), "duplicateFamilies": len(lib.families)}
        if name == "autorag.search":
            hits = lib.retrieve(args["query"], int(args.get("k", 5)), args.get("mode", "hybrid"))
            return [{"id": h.chunk.id, "source": h.chunk.source, "score": round(h.score, 4), "text": h.chunk.text} for h in hits]
        if name == "autorag.search.files":
            return sorted(f for f in lib._files if fnmatch.fnmatch(f, args["pattern"]) or fnmatch.fnmatch(Path(f).name, args["pattern"]))
        if name == "autorag.datasources.list":
            counts: dict[str, int] = {}
            for c in lib.chunks:
                counts[c.datasource] = counts.get(c.datasource, 0) + 1
            return [{"name": k, "chunks": v} for k, v in sorted(counts.items())]
        if name == "autorag.evidence":
            return {"text": read_source(lib.root, args["chunk_id"], args["source"])}
        if name == "autorag.refresh":
            lib.refresh()
            return {"chunks": len(lib.chunks)}
        # autorag.report
        self.report_dir.mkdir(parents=True, exist_ok=True)
        path = self.report_dir / (Path(args["name"]).name + ".md")
        path.write_text(args["body"], encoding="utf-8")
        return {"path": str(path)}

    # ---- JSON-RPC -----------------------------------------------------
    def handle(self, req: dict) -> dict | None:
        rid, method, params = req.get("id"), req.get("method"), req.get("params") or {}
        if rid is None:
            return None  # notification
        try:
            if method == "initialize":
                result: Any = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "serverInfo": {"name": "autorag-lab-mcp", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                }
            elif method == "tools/list":
                result = {"tools": self.tools()}
            elif method == "tools/call":
                payload = self._call(params["name"], params.get("arguments") or {})
                result = {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}
            else:
                return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}}
        except KeyError as exc:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": str(exc)}}
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    def serve(self, stdin: IO[str] = sys.stdin, stdout: IO[str] = sys.stdout) -> None:
        for line in stdin:
            if not line.strip():
                continue
            resp = self.handle(json.loads(line))
            if resp is not None:
                stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                stdout.flush()
