# Lab 6 - Retrieval memory and the MCP server (15 min)

## Retrieval memory

Upstream `docs/retrieval-memory.md`: after the final answer, each cited evidence is judged
("does it directly support the sentence it backs?"); judged evidence is stored and later offered
as `<memory_context>` -- reference only, it never reorders results or overrides current evidence.

Code: `src/autorag_lab/memory.py` (threshold 0.7, token-overlap judge stand-in)

## AutoRAG Lite MCP

Upstream ships `autorag-mcp`, a model-free stdio server (`autorag.status`, `autorag.search`,
`autorag.search.files`, `autorag.datasources.list`, `autorag.evidence`, `autorag.refresh`,
`autorag.report`, ...). Clients discover tools with `tools/list` and must not hard-code a
count. Read-only mode omits mutating tools.

Code: `src/autorag_lab/mcp.py`

## Run

```bash
make mcp-probe
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"autorag.search","arguments":{"query":"Seoul","k":2}}}' \
  | PYTHONPATH=src python3 -m autorag_lab mcp --read-only
python3 -m unittest tests.test_labs.Lab6MemoryAndMcp -v
```

## Exercises

1. Make memory *reorder* results (boost remembered sources). Watch
   `test_memory_persists_and_is_advisory_only` fail. Why is advisory-only the safer contract?
   (Think: one wrong judged record poisoning every later search.)
2. Register the lab server in an MCP client in read-only mode and ask it a corpus question.
