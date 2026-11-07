# Agenda (2 hours)

| Time | Segment | Output |
|---|---|---|
| 0:00-0:10 | What AutoRAG Agent is; why "librarian" not "search" | Lab 0 green |
| 0:10-0:25 | Lab 1: federate in place | a new datasource file indexed with no code change |
| 0:25-0:45 | Lab 2: sparse / dense / hybrid | an RRF experiment and one new concept test |
| 0:45-1:05 | Lab 3: two-phase answer, citations, steering | withhold-on-unresolved patch |
| 1:05-1:15 | Break |  |
| 1:15-1:30 | Lab 4: duplicate families | a draft version labelled correctly |
| 1:30-1:55 | Lab 5: permission gate + red team | one bypass found and a test for it |
| 1:55-2:00 | Lab 6 + capstone wrap-up | `make gate` and `make gate-bad` explained |

Half-day version: give Lab 5 and the capstone 45 minutes each and run `make live-run` on a
facilitator laptop with a configured model.

Facilitator notes:
- Keep stressing *contract vs implementation*: every lab engine is a stand-in; the tests are
  the part attendees should take home.
- Lab 5 red-team exercise always finds bypasses. That is the lesson, not a bug in the lab.
- Do not run `autorag init` against a real home folder during the workshop; the live extension
  isolates `AUTORAG_HOME` under `out/` and indexes a copy of the corpus.
