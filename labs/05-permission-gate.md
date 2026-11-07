# Lab 5 - The permission gate (25 min)

Upstream `docs/permissions.md`, reduced to contracts:

| Mode | Behaviour |
|---|---|
| `auto` (default for `autorag tui`) | Jev scores delete / move / rename / overwrite / edit / unclear. Any >= 0.2 flags the call. Flagged calls run silently only if Jev is >= 0.8 sure the user asked for exactly that; otherwise the user is asked. Jev unreachable -> ask. |
| `ask` | every bash / write / edit call is asked about; Jev is never called |
| `full` (default for `autorag search` and messenger bridges) | no gate |

Deletion goes to the trash, every change is logged `old -> new`, and files the agent created
itself stay free to change ("copy first, then change the copy").

Code: `src/autorag_lab/permissions.py`, `src/autorag_lab/workspace.py`

## Run

```bash
python3 -m autorag_lab perm "cat docs/team-notes.md"
python3 -m autorag_lab perm "rm docs/proposal-v3.md"
python3 -m autorag_lab perm "rm docs/proposal-v3.md" --request "please delete proposal-v3.md"
python3 -m autorag_lab perm 'f=rm; $f docs/proposal-v3.md'
python3 -m autorag_lab perm "ls" --jev-down
python3 -m autorag_lab perm "ls" --mode ask
python3 -m autorag_lab ask "What is planned for the quarterly offsite?" --model obey_injection
python3 -m unittest tests.test_labs.Lab5PermissionGate -v
```

`perm` only classifies; it never executes.

## Exercises

1. Red team: find a command that deletes or overwrites an existing file but that `FakeJev`
   scores below 0.2. (There are several -- `tee`, `dd`, `install`, `rsync --delete` ...)
   Write the failing test, then decide: patch the heuristic, or accept that only a model
   judge generalises? This is why upstream has no command parser.
2. The `obey_injection` model's calls are denied because nobody is at the terminal. Run the
   same scenario with `PermissionGate(..., mode="full")` in a scratch test against a temp copy.
   What saves you? (Workspace refusal for `~/Documents`, trash for `docs/...`.) What would
   *not* save you on a real machine?
3. Upstream defaults `autorag search` to `full` "because nobody can answer a terminal dialog
   there". Propose a safer default for a headless librarian and defend it.
