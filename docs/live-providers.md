# From the lab to the real AutoRAG Agent

## 1. Run the real CLI on the workshop corpus

```bash
npm install -g @autorag/librarian      # Node >= 24, or: bun install -g @autorag/librarian
make live                              # dry-run: prints every command
make live-run                          # model-free steps: lite init, refresh, status, duplicates, MCP tools/list
python3 extensions/live/autorag_live.py --run --with-model   # also two `autorag search` calls
```

`--with-model` needs a chat model: `autorag tui`, then `/login` and `/model` (or a `model`
entry in the config). Check with `autorag health`. Do not re-run `autorag init --force` just to
pick a model -- it replaces the whole config.

The script sets `AUTORAG_HOME=out/live-home`, `AUTORAG_NO_UPDATE_CHECK=1`, and indexes a copy
at `out/live-corpus`. Command shapes come from the upstream README; verify flags with
`autorag --help` for your installed version.

## 2. Replace each stand-in

| Lab stand-in | Replace with | Where |
|---|---|---|
| `FakeModel.answer` / `revise` | a real chat model call that returns text with `[eN]` citations given the ledger | `src/autorag_lab/model.py` |
| `FakeJev.classify` | a judgment-model call returning the six probabilities + "covers the request" probability; keep the 15 s timeout -> ask | `src/autorag_lab/permissions.py` |
| `Index.sparse` / `dense` | MinSync (`autorag lite refresh`) through the MCP `autorag.search` tool | `src/autorag_lab/retrieval.py` |
| `memory.judge` | a model P(supports) per evidence, one batched call | `src/autorag_lab/memory.py` |
| `McpServer` | upstream `autorag-mcp` (`AUTORAG_CONFIG=... autorag-mcp`) | `src/autorag_lab/mcp.py` |

Keep `tests/test_labs.py` and `evals.py` unchanged when you swap an engine: the contracts are
the point. A real model will not be deterministic, so run the gate several times and gate on
the worst run.

## 3. Upstream references

- README: https://github.com/Marker-Inc-Korea/AutoRAG
- Permissions: `docs/permissions.md`
- Retrieval memory: `docs/retrieval-memory.md`
- Reranking (opt-in, remote): `docs/rerank.md`
- MinSync: `docs/minsync-setup.md`
- MCP contract source of truth: `src/mcp/server.ts`
