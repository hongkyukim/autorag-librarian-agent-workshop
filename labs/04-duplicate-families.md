# Lab 4 - Spot the twins: duplicate families (15 min)

Upstream: `autorag duplicates` (backed by `dupey`) labels members Latest / Similar / Identical
so the librarian cites the newest version instead of whichever copy ranked first.

Code: `src/autorag_lab/dedupe.py`, duplicate collapse in `Librarian.retrieve`

## Run

```bash
python3 -m autorag_lab dupes
python3 -m autorag_lab ask "What budget did the final proposal settle on?"
python3 -m autorag_lab ask "What budget did the final proposal settle on?" --model stale_version
python3 -m unittest tests.test_labs.Lab4Duplicates -v
```

## Exercises

1. Add `docs/proposal-draft.md` dated 2026-05-01. Which label does it get? Is name-based
   grouping enough, or do you need content similarity across differently named files?
2. Set both proposals to the same `updated:` date. Which one wins and why? Is that the
   behaviour you want?
3. The stale model bypasses retrieval by reading the old file directly. The harness *detects*
   it but does not block it. Should it? Argue both sides.
