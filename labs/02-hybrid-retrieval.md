# Lab 2 - Sparse + dense + hybrid (20 min)

Upstream: MinSync fuses SPLADE sparse (replaced BM25 in MinSync 0.6) and dense vectors over the
same CDC chunks. Here: BM25, a toy concept embedder, and Reciprocal Rank Fusion (k=60).

Code: `src/autorag_lab/retrieval.py`, `src/autorag_lab/text.py`

## Run

```bash
for m in sparse dense hybrid; do python3 -m autorag_lab search "uptime guarantee" --mode $m -k 2; done
python3 -m autorag_lab search "INV-2026-0042" --mode sparse -k 2
python3 -m autorag_lab search "인증서를 갱신하는 절차" --mode sparse -k 2
python3 -m unittest tests.test_labs.Lab2HybridRetrieval -v
```

The contract clause says "availability commitment" and "outage" -- never "uptime" or
"guarantee". Sparse cannot see it; dense can. The invoice id is the opposite case.

## Exercises

1. Change `RRF_K` to 1 and to 1000. Which test breaks first and why?
2. Add a synonym to `CONCEPTS` so "how long is the pilot" finds the timeline paragraph by
   meaning. Write the test first.
3. Upstream notes SPLADE ranks exact identifiers among look-alike files *less* reliably than
   BM25. Add `mail/vendor-renewal-2.eml` with `INV-2026-0043` and check that sparse still ranks
   the right invoice first.
