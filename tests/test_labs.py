"""Behaviour-contract tests, one class per lab. Run: make test"""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from autorag_lab.agent import Librarian
from autorag_lab.corpus import load_corpus, read_source
from autorag_lab.dedupe import family_key
from autorag_lab.evals import check_gate, load_golden, run_eval, snapshot
from autorag_lab.mcp import MUTATING, McpServer
from autorag_lab.memory import Citation, RetrievalMemory
from autorag_lab.model import FakeModel
from autorag_lab.permissions import FakeJev, PermissionGate
from autorag_lab.text import tokens
from autorag_lab.workspace import TRASH, OutsideWorkspace, ToolCall, Workspace

REPO = Path(__file__).resolve().parents[1]
CORPUS = REPO / "data" / "corpus"
GOLDEN = load_golden(REPO / "data" / "eval" / "golden.jsonl")


class SandboxCase(unittest.TestCase):
    """Every test that could write gets its own copy of the corpus."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="autorag-lab-test-")
        self.root = Path(self._tmp.name) / "corpus"
        shutil.copytree(CORPUS, self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()


class Lab1FederatedSources(unittest.TestCase):
    def test_ids_are_source_native(self):
        ids = {c.id for c in load_corpus(CORPUS)}
        self.assertIn("/slack/legal-ops/chunks/318", ids)
        self.assertTrue(any(i.startswith("/mail/vendor-renewal/") for i in ids))
        self.assertIn("docs/cloud-contract-q3.md#p3", ids)

    def test_indexing_never_copies_or_modifies_the_corpus(self):
        before = snapshot(CORPUS)
        Librarian(CORPUS)
        self.assertEqual(before, snapshot(CORPUS))

    def test_every_chunk_resolves_back_to_its_native_file(self):
        for c in load_corpus(CORPUS):
            self.assertEqual(read_source(CORPUS, c.id, c.source), c.text)

    def test_excluded_folder_is_not_indexed(self):
        self.assertFalse(any(c.source.startswith("archive/") for c in load_corpus(CORPUS)))

    def test_korean_particles_are_normalised(self):
        self.assertEqual(tokens("인증서를 갱신합니다"), ["인증서", "갱신"])


class Lab2HybridRetrieval(unittest.TestCase):
    lib = Librarian(CORPUS)

    def ids(self, q, mode, k=3):
        return [h.chunk.id for h in self.lib.index.search(q, k, mode)]

    def test_sparse_misses_meaning_only_match(self):
        self.assertNotIn("docs/cloud-contract-q3.md#p3", self.ids("uptime guarantee", "sparse"))

    def test_dense_finds_meaning_only_match(self):
        self.assertEqual(self.ids("uptime guarantee", "dense")[0], "docs/cloud-contract-q3.md#p3")

    def test_sparse_finds_exact_identifier(self):
        self.assertTrue(self.ids("INV-2026-0042", "sparse")[0].startswith("/mail/vendor-renewal/"))

    def test_hybrid_finds_both_kinds(self):
        got = self.ids("INV-2026-0042 uptime guarantee", "hybrid", 4)
        self.assertIn("docs/cloud-contract-q3.md#p3", got)
        self.assertTrue(any(i.startswith("/mail/vendor-renewal/") for i in got))

    def test_unknown_mode_is_an_error(self):
        with self.assertRaises(ValueError):
            self.lib.index.search("x", 3, "bm42")


class Lab3TwoPhaseCitations(unittest.TestCase):
    def test_every_citation_resolves_to_the_ledger(self):
        ans = Librarian(CORPUS).ask("What is the uptime guarantee?")
        self.assertIn("99.95%", ans.text)
        self.assertEqual(ans.unresolved, [])
        self.assertTrue(ans.citations)

    def test_hallucinated_citation_is_flagged_and_triggers_verification(self):
        ans = Librarian(CORPUS, model=FakeModel("hallucinate_citation")).ask("What is the uptime guarantee?")
        self.assertIn("e99", ans.unresolved)
        self.assertTrue(ans.verification_ran)

    def test_steer_always_forces_verification(self):
        lib = Librarian(CORPUS)
        plain = lib.ask("What is the uptime guarantee?")
        steered = lib.ask("What is the uptime guarantee?", steer="the monthly figure")
        self.assertFalse(plain.verification_ran)
        self.assertTrue(steered.verification_ran)

    def test_steer_narrows_an_ambiguous_question(self):
        ans = Librarian(CORPUS).ask("What is the budget?", steer="I mean the data platform proposal")
        self.assertIn("$120,000", ans.text)
        self.assertNotIn("INV-2026-0042", ans.text)


class Lab4Duplicates(unittest.TestCase):
    def test_versions_collapse_into_one_family(self):
        keys = {family_key(n) for n in ("docs/proposal-v3.md", "docs/proposal-final.md", "docs/proposal (1).md")}
        self.assertEqual(keys, {"docs/proposal"})

    def test_labels(self):
        (fam,) = Librarian(CORPUS).families
        self.assertEqual(fam.latest, "docs/proposal-final.md")
        self.assertEqual(fam.labels["docs/proposal (1).md"], "Identical")
        self.assertEqual(fam.labels["docs/proposal-v3.md"], "Similar")

    def test_newest_version_is_cited(self):
        ans = Librarian(CORPUS).ask("What budget did the final proposal settle on?")
        self.assertEqual({c.source for c in ans.citations}, {"docs/proposal-final.md"})
        self.assertEqual(ans.stale, [])

    def test_stale_citation_is_detected(self):
        ans = Librarian(CORPUS, model=FakeModel("stale_version")).ask("What budget did the final proposal settle on?")
        self.assertEqual(ans.stale, ["file:docs/proposal-v3.md"])


class Lab5PermissionGate(SandboxCase):
    def gate(self, mode="auto", reachable=True):
        return PermissionGate(Workspace(self.root), mode, FakeJev(reachable))

    def test_reads_and_new_files_run_without_asking(self):
        g = self.gate()
        for cmd in ("ls docs", "cat docs/team-notes.md", "mkdir drafts", "cp docs/proposal-final.md drafts/p.md"):
            self.assertEqual(g.decide(ToolCall("bash", cmd), []).action, "run", cmd)

    def test_delete_without_request_asks(self):
        d = self.gate().decide(ToolCall("bash", "rm docs/proposal-v3.md"), ["summarise the proposal"])
        self.assertEqual((d.action, d.flagged), ("ask", ["delete"]))

    def test_delete_that_user_requested_runs_and_goes_to_trash(self):
        g = self.gate()
        out = g.submit(ToolCall("bash", "rm docs/proposal-v3.md"), ["please delete proposal-v3.md"])
        self.assertTrue(out.executed)
        self.assertFalse((self.root / "docs/proposal-v3.md").exists())
        self.assertTrue((self.root / TRASH / "proposal-v3.md").exists())
        self.assertIn("trashed docs/proposal-v3.md", g.ws.changes[0])

    def test_obfuscated_delete_is_caught(self):
        for cmd in ("f=rm; $f docs/proposal-v3.md", "python3 -c 'import os; os.remove(\"docs/proposal-v3.md\")'"):
            self.assertEqual(self.gate().decide(ToolCall("bash", cmd), []).action, "ask", cmd)

    def test_copy_first_then_edit_the_copy_is_free(self):
        g = self.gate()
        g.submit(ToolCall("bash", "cp docs/proposal-final.md docs/proposal-edited.md"), [])
        d = g.decide(ToolCall("bash", "sed -i 's/120,000/125,000/' docs/proposal-edited.md"), [])
        self.assertEqual(d.action, "run")

    def test_unreachable_judge_fails_closed(self):
        d = self.gate(reachable=False).decide(ToolCall("bash", "ls"), [])
        self.assertEqual(d.action, "ask")

    def test_ask_mode_asks_even_for_ls(self):
        self.assertEqual(self.gate("ask").decide(ToolCall("bash", "ls"), []).action, "ask")

    def test_outside_workspace_is_refused_even_in_full_mode(self):
        g = self.gate("full")
        out = g.submit(ToolCall("bash", "rm -rf ~/Documents"), [])
        self.assertFalse(out.executed)
        with self.assertRaises(OutsideWorkspace):
            g.ws.resolve("../../etc/passwd")

    def test_injection_document_cannot_delete_anything(self):
        before = snapshot(self.root)
        lib = Librarian(self.root, model=FakeModel("obey_injection"), gate=self.gate())
        ans = lib.ask("What is planned for the quarterly offsite?")
        self.assertTrue(ans.tool_outcomes)
        self.assertFalse(any(o.executed for o in ans.tool_outcomes))
        self.assertEqual(before, snapshot(self.root))

    def test_good_model_never_proposes_tool_calls_from_evidence(self):
        ans = Librarian(self.root, gate=self.gate()).ask("What is planned for the quarterly offsite?")
        self.assertEqual(ans.tool_outcomes, [])
        self.assertIn("Busan", ans.text)
        self.assertNotIn("rm ", ans.text)


class Lab6MemoryAndMcp(SandboxCase):
    def test_below_threshold_evidence_is_dropped(self):
        mem = RetrievalMemory()
        cite = Citation("e1", "docs/x.md", "docs/x.md#p1", "completely unrelated text about laptops")
        stored, dropped = mem.judge_and_store("q", "The budget is $120,000 [e1]", [cite], "s1")
        self.assertEqual((len(stored), len(dropped)), (0, 1))

    def test_memory_persists_and_is_advisory_only(self):
        path = self.root / ".autorag" / "memory.json"
        lib = Librarian(self.root, memory=RetrievalMemory(path))
        before = [h.chunk.id for h in lib.retrieve("What is the budget?")]
        lib.ask("What is the budget?")
        self.assertTrue(path.exists())
        reloaded = Librarian(self.root, memory=RetrievalMemory(path))
        self.assertIn("<memory_context>", reloaded.memory.context("What is the budget?"))
        self.assertEqual(before, [h.chunk.id for h in reloaded.retrieve("What is the budget?")])

    def rpc(self, server, method, params=None, rid=1) -> dict:
        resp = server.handle({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        assert resp is not None
        return resp

    def test_tools_list_and_search(self):
        srv = McpServer(Librarian(self.root))
        names = {t["name"] for t in self.rpc(srv, "tools/list")["result"]["tools"]}
        self.assertTrue(MUTATING <= names)
        res = self.rpc(srv, "tools/call", {"name": "autorag.search", "arguments": {"query": "INV-2026-0042"}})
        hits = json.loads(res["result"]["content"][0]["text"])
        self.assertTrue(hits[0]["id"].startswith("/mail/"))

    def test_read_only_mode_hides_and_refuses_mutating_tools(self):
        srv = McpServer(Librarian(self.root), read_only=True)
        names = {t["name"] for t in self.rpc(srv, "tools/list")["result"]["tools"]}
        self.assertFalse(MUTATING & names)
        res = self.rpc(srv, "tools/call", {"name": "autorag.report", "arguments": {"name": "x", "body": "y"}})
        self.assertIn("error", res)

    def test_stdio_transport(self):
        srv = McpServer(Librarian(self.root), read_only=True)
        out = io.StringIO()
        srv.serve(io.StringIO('{"jsonrpc":"2.0","id":7,"method":"initialize"}\n{"jsonrpc":"2.0","method":"notifications/initialized"}\n'), out)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["id"], 7)


class CapstoneGate(unittest.TestCase):
    def test_good_model_passes(self):
        ok, failures = check_gate(run_eval(CORPUS, GOLDEN, "good")["metrics"])
        self.assertTrue(ok, failures)

    def test_each_bad_mode_fails_with_zero_file_changes(self):
        expected = {
            "hallucinate_citation": "citation_resolution",
            "stale_version": "stale_citations",
            "obey_injection": "injection_actions",
        }
        for mode, metric in expected.items():
            metrics = run_eval(CORPUS, GOLDEN, mode)["metrics"]
            ok, failures = check_gate(metrics)
            self.assertFalse(ok, mode)
            self.assertTrue(any(f.startswith(metric) for f in failures), (mode, failures))
            self.assertEqual(metrics["file_changes"], 0, mode)


if __name__ == "__main__":
    unittest.main()
