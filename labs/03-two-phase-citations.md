# Lab 3 - Fast answer, verification, citations, steering (20 min)

Upstream: the model replies with inline `[eN]` citations; the harness resolves them against
the conversation's evidence ledger (retrieval-issued ids attach the harness-recorded source,
not model-written text). A verification phase follows the fast answer; typing during a search
(**Enter**) steers it and always runs verification.

Code: `src/autorag_lab/agent.py`

## Run

```bash
python3 -m autorag_lab ask "What is the uptime guarantee?"
python3 -m autorag_lab ask "What is the uptime guarantee?" --model hallucinate_citation
python3 -m autorag_lab ask "What is the budget?"
python3 -m autorag_lab ask "What is the budget?" --steer "I mean the data platform proposal"
python3 -m unittest tests.test_labs.Lab3TwoPhaseCitations -v
```

The unsteered budget answer drags in the invoice; the steer narrows it and the phases line
shows `verification`.

## Exercises

1. The hallucinating model ignores the revision request. Change the harness so an answer that
   still has unresolved citations after verification is *withheld* (replace the text with a
   refusal). Which capstone metric changes?
2. Add a "claim check": a sentence citing `[eN]` must share every number it contains with
   the evidence text. Write the failing test with a fake model that swaps 99.95% for 99.99%.
