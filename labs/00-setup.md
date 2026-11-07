# Lab 0 - Setup and orientation (10 min)

1. Python 3.11+ and `make`. Nothing else.
2. `make test` -> 35 tests OK. `make demo` -> seven numbered sections ending in `GATE: PASS`.
3. Skim the upstream README sections "Core Values" and "Architecture & How It Works"
   (https://github.com/Marker-Inc-Korea/AutoRAG). Every lab maps to one of them.

Mental model of a single question:

```text
question -> retrieve (hybrid, duplicate collapse) -> evidence ledger e1..eN
         -> fast answer with [eN] -> verification (resolve, stale check, steer)
         -> tool calls through the permission gate -> judged evidence into memory
```

The model is injected (`src/autorag_lab/model.py`). The harness is what you are testing.
