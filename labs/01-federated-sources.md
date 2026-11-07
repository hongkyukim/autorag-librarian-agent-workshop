# Lab 1 - Federate in place, never migrate (15 min)

Upstream principle 1: "Never migrate your data to search it." Datasources stay in their native
stores (`slacrawl`, `mailcrawl`, ...) and results keep opaque, source-native ids.

Code: `src/autorag_lab/corpus.py`

## Run

```bash
export PYTHONPATH=src
python3 -m autorag_lab search "Seoul region" -k 3
python3 -m unittest tests.test_labs.Lab1FederatedSources -v
```

Note the three id shapes: `docs/...#p2`, `/slack/legal-ops/chunks/318`, `/mail/vendor-renewal/p2`.

## Exercises

1. Add `data/corpus/slack/eng-infra.jsonl` with two messages. Re-run search. No code change
   should be needed -- that is the point of a per-format loader.
2. `read_source` re-reads the native file. Why does the agent verify against the native file
   instead of the indexed copy? (Hint: upstream "Direct Evidence Reading".)
3. Remove `archive/` from `.autoragignore` and ask "What was on the 2024 roadmap?". Which golden
   case now fails, and why does excluding stale folders matter for a librarian?

## Discuss

Source-native ids preserve access control: the agent can cite `/slack/...` without the harness
ever owning the Slack data. What breaks if you ETL everything into one vector DB instead?
