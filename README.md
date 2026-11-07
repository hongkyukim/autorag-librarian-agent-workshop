# AutoRAG Agent Workshop: Build a Trustworthy Librarian Agent

A hands-on workshop on the architecture of
[AutoRAG Agent](https://github.com/Marker-Inc-Korea/AutoRAG) (`@autorag/librarian`),
Marker-Inc-Korea's personal librarian agent that searches your files, mail, and chats
**in place**, cites every claim, and can organize your files behind an approval gate.

You rebuild each core idea as a small, offline, stdlib-only Python lab with a
behaviour-contract test, then finish with a release gate that a good model passes and
three misbehaving models fail -- with zero files changed. An optional extension runs the
same corpus through the real `autorag` CLI.

No API key, Node.js, or network access is needed for the default path.

> Target version: AutoRAG Agent 2.x (TypeScript, Pi host; npm `@autorag/librarian` 2.13.x
> at the time of writing). The original Python AutoML-for-RAG tool now lives under
> `legacy/` upstream and is **not** covered here.

## Quick start

Requires Python 3.11+ and `make`.

```bash
make test       # 35 behaviour-contract tests, one class per lab
make demo       # walk through every lab in ~1 second
make gate       # good model: GATE PASS (exit 0)
make gate-bad   # each misbehaving model must fail the gate
make live       # dry-run of the real-CLI extension (prints commands only)
```

Individual commands:

```bash
export PYTHONPATH=src
python3 -m autorag_lab search "uptime guarantee" --mode sparse     # nothing
python3 -m autorag_lab search "uptime guarantee" --mode dense      # the SLA clause
python3 -m autorag_lab ask "What is the budget?"
python3 -m autorag_lab ask "What is the budget?" --steer "I mean the data platform proposal"
python3 -m autorag_lab dupes
python3 -m autorag_lab perm "rm docs/proposal-v3.md"                          # ask
python3 -m autorag_lab perm "rm docs/proposal-v3.md" --request "delete proposal-v3.md"   # run
python3 -m autorag_lab perm "ls" --jev-down                                   # ask (fail closed)
python3 -m autorag_lab gate --model obey_injection                            # GATE FAIL
make mcp-probe                                                                # tools/list, read-only
```

## What maps to what

| AutoRAG Agent concept (upstream) | Lab | Contract the test enforces |
|---|---|---|
| Federate data in place, source-native ids (`/slack/...`, `/mail/...`), `--exclude` | [Lab 1](labs/01-federated-sources.md) | ids are source-native; indexing never copies or modifies the corpus; `archive/` is excluded; Korean particles normalise |
| MinSync SPLADE sparse + dense + hybrid | [Lab 2](labs/02-hybrid-retrieval.md) | sparse misses the meaning-only match, dense finds it, hybrid (RRF k=60) finds both kinds |
| Fast answer -> verification phase, inline `[eN]` citations, evidence ledger, Enter-to-steer | [Lab 3](labs/03-two-phase-citations.md) | every citation resolves; a hallucinated `[e99]` is flagged; a steer always forces verification |
| `autorag duplicates` (Latest / Similar / Identical) | [Lab 4](labs/04-duplicate-families.md) | `proposal-v3`, `proposal-final`, `proposal (1)` form one family; the newest is cited |
| Permission gate `ask` / `auto` / `full`, Jev's six categories, flag >= 0.2, auto-approve >= 0.8, fail closed, trash not rm | [Lab 5](labs/05-permission-gate.md) | the prompt-injection document cannot delete anything; obfuscated deletes are caught; copy-then-edit is free |
| Retrieval memory (judged evidence, advisory only) + AutoRAG Lite MCP server | [Lab 6](labs/06-memory-and-mcp.md) | below-threshold evidence is dropped; memory never reorders results; read-only MCP hides `refresh`/`report` |
| Release discipline | [Capstone](labs/capstone.md) | good model passes; `hallucinate_citation`, `stale_version`, `obey_injection` each fail with 0 file changes |

Start with [labs/00-setup.md](labs/00-setup.md). The 2-hour agenda is in
[docs/agenda.md](docs/agenda.md); moving to the real CLI and real models is in
[docs/live-providers.md](docs/live-providers.md).

## The corpus

`data/corpus/` is tiny and synthetic, built so every lab has something to find:

```text
docs/cloud-contract-q3.md       discount, data residency, availability clause (no word "uptime")
docs/proposal-v3.md             older version ($95,000)        -> Similar
docs/proposal-final.md          newest version ($120,000)      -> Latest
docs/proposal (1).md            byte copy of final             -> Identical
docs/onboarding-ko.md           mixed Korean/English
docs/team-notes.md              offsite plan + a PROMPT INJECTION ("rm -rf ~/Documents")
archive/old-roadmap-2024.md     excluded by .autoragignore
slack/legal-ops.jsonl           chat export -> /slack/legal-ops/chunks/<id>
mail/vendor-renewal.eml         mailbox file -> /mail/vendor-renewal/p<n>
```

## Repo map

```text
src/autorag_lab/      corpus, retrieval, agent (two-phase harness), dedupe, permissions,
                      workspace (sandboxed executor), memory, mcp, model (fake + bad modes), evals, cli
tests/test_labs.py    behaviour contracts, one class per lab
labs/                 attendee instructions 00-06 + capstone
docs/                 agenda, live providers, facilitator notes
extensions/live/      dry-run-first script that drives the real `autorag` CLI
data/                 corpus and golden eval questions
```

## Honest scope

- Every engine here is a **teaching stand-in**: BM25 for SPLADE, a hand-written concept table
  for the dense embedder, a heuristic `FakeJev` for the judgment model, a JSON-RPC imitation of
  the MCP server. They reproduce upstream *contracts*, not upstream quality or code.
- `FakeJev` uses heuristics; upstream deliberately has **no command parser** and asks a model
  instead. The lab says so, and Lab 5 asks you to find a bypass.
- The sandboxed executor never runs a shell and refuses paths outside its workspace. It is a
  lab device, not a security boundary -- and neither is the upstream gate ("a gate against
  mistakes and runaway agents, not a sandbox").
- `extensions/live/autorag_live.py` uses command shapes from the upstream README. It was not
  executed in CI (CI runs only the dry-run); flags may drift between releases.

## License

MIT for this workshop. AutoRAG is Apache-2.0 and belongs to its authors; this repository is an
independent learning companion, not affiliated with Marker-Inc-Korea.
