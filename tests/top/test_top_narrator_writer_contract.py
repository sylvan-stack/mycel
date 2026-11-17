"""Exercise Narrator's executable boundary with local process stand-ins."""

from hashlib import sha256
from importlib.resources import files
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest

from mycel._resolver import ResolvedChunk, SelectionMember
from mycel._source_refs import SourceAddress
from mycel._summary_request import SummaryPrompts, SummarySection, plan_summary_requests
from mycel._summary_writer import SummaryWriter, WriterResult
from test_summary_writer import _process_running


NARRATOR = Path(__file__).resolve().parents[2] / "scripts/narrator/narrator.py"
PYTHON = str(Path(sys.executable).absolute())
PROBE = """\
import json
import os
import pathlib
import subprocess
import sys
import time

def launch_record(argv):
    return {"argv": argv, "cwd": os.getcwd(), "empty": not os.listdir("."),
            "environment_marker": os.environ.get("NARRATOR_CONTRACT_PRIVATE"),
            "pid": os.getpid(), "group": os.getpgrp()}

def start_descendant():
    return subprocess.Popen((sys.executable, "-I", "-B", "-c", "import time; time.sleep(60)"),
                            stdin=subprocess.DEVNULL)

"""
STAND_IN = PROBE + """\

plan, trace = map(pathlib.Path, sys.argv[1:3])
replies = json.loads(plan.read_text(encoding="utf-8"))
index = len(trace.read_text(encoding="utf-8").splitlines()) if trace.exists() else 0
request = sys.stdin.read()
prompt, _, payload = request.rpartition("\\n\\n")
record = launch_record(sys.argv[3:])
with trace.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(dict(record, prompt=prompt, input=json.loads(payload))) + "\\n")
reply = replies[index]
if isinstance(reply, dict) and "raw" in reply:
    sys.stderr.write(reply.get("stderr", ""))
    sys.stdout.write(reply["raw"])
else:
    sys.stdout.write(json.dumps(reply))
"""
CREDENTIAL_STAND_IN = PROBE + """\
trace, mode, *literal = sys.argv[1:]
record = launch_record(literal)
descendant = start_descendant()
record["descendant"] = descendant.pid
pathlib.Path(trace).write_text(json.dumps(record), encoding="utf-8")
if mode == "block":
    time.sleep(60)
print("fixture-token")
"""
EMBEDDING_STAND_IN = PROBE + """\
narrator, key_argv, trace, *literal = sys.argv[1:]
sys.path.insert(0, narrator)
from narrator import _interrupt_on_termination
from voyage_embeddings import _read_key

record = launch_record(literal)
record["input"] = json.load(sys.stdin)
path = pathlib.Path(trace)
path.write_text(json.dumps(record), encoding="utf-8")
try:
    with _interrupt_on_termination():
        started = time.monotonic()
        record["credential_ok"] = _read_key(tuple(json.loads(key_argv)), started + 5) == "fixture-token"
        record["credential_seconds"] = time.monotonic() - started
        descendant = start_descendant()
        record["descendant"] = descendant.pid
        path.write_text(json.dumps(record), encoding="utf-8")
        sys.stderr.write("fixture-private-embedding-diagnostic")
        sys.stdout.write("{")
except KeyboardInterrupt:
    sys.exit(1)
"""
OUTER_DEADLINE = """\
import json
import sys
import time

sys.path.insert(0, sys.argv[1])
from narrator import BudgetExhausted, _run_command

try:
    _run_command(tuple(json.loads(sys.argv[2])), b'["first", "second"]', time.monotonic() + 3)
except BudgetExhausted:
    print("outer deadline expired")
else:
    sys.exit("outer deadline did not expire")
"""


def _candidate(claim, passage_id):
    return {"claim": claim, "scope": "archive", "authority": "policy",
            "cited_passage_ids": [passage_id]}


def _unit(unit_id, prose, candidate_id, passage_id, *, rank=1):
    return {
        "unit_id": unit_id, "revision": 1, "prose": prose, "scope": "archive",
        "conditions": [], "originating_candidate_ids": [candidate_id],
        "cited_passage_ids": [passage_id], "consequence_rank": rank,
    }


def _support(unit):
    return {"unit_id": unit["unit_id"], "revision": unit["revision"],
            "verdict": "supported", "evidence_passage_ids": unit["cited_passage_ids"],
            "affected_part": None, "reason": None}


def _request(source, prompts, *, kind="document"):
    raw = source.encode("utf-8")
    place = (SourceAddress("fixture", "index", "summaries", "1/1") if kind == "summary"
             else SourceAddress("fixture", "artifact", "archive.md", "Rules"))
    chunk = ResolvedChunk("member", 1, place.name, kind, raw, sha256(raw).hexdigest())
    section = SummarySection(SelectionMember(place, chunk), 0)
    request, = plan_summary_requests((section,), prompts)
    return request


def _packaged_request(source):
    data = json.loads(files("mycel").joinpath("data/summary-prompts.json").read_bytes())
    prompts = SummaryPrompts(data["instruction"].encode("utf-8"), data["task"].encode("utf-8"),
                             data["profile"])
    return _request(source, prompts).request


def _read_trace(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _stop_fixture_processes(path):
    if not path.exists():
        return
    trace = json.loads(path.read_text(encoding="utf-8"))
    for field in ("descendant", "pid"):
        pid = trace.get(field)
        if pid is None:
            continue
        try:
            if os.getpgid(pid) == trace["group"]:
                os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


class NarratorWriterContractTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="narrator-contract-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.stand_in = self.root / "stand-in.py"
        self.stand_in.write_text(STAND_IN, encoding="utf-8")

    def _stand_in(self, name, replies, *arguments):
        plan = self.root / f"{name}.json"
        plan.write_text(json.dumps(replies), encoding="utf-8")
        trace = self.root / f"{name}.jsonl"
        argv = [PYTHON, "-I", "-B", str(self.stand_in), str(plan), str(trace), *arguments]
        return argv, trace

    def _child(self, name, source, *arguments):
        path = self.root / f"{name}.py"
        path.write_text(source, encoding="utf-8")
        return [PYTHON, "-I", "-B", str(path), *arguments]

    def _embedding(self, mode, literal):
        credentials = self.root / f"credentials-{mode}.json"
        transport = self.root / f"embedding-{mode}.json"
        self.addCleanup(_stop_fixture_processes, transport)
        self.addCleanup(_stop_fixture_processes, credentials)
        key = self._child("credential", CREDENTIAL_STAND_IN, str(credentials), mode, literal)
        embedding = self._child("embedding", EMBEDDING_STAND_IN, str(NARRATOR.parent),
                                json.dumps(key), str(transport), literal)
        return embedding, transport, credentials

    def _assert_exited(self, *identifiers):
        deadline = time.monotonic() + 2
        while any(map(_process_running, identifiers)):
            if time.monotonic() >= deadline:
                self.fail(f"fixture processes survived their command: {identifiers}")
            time.sleep(0.01)

    def _writer(self, model, *options):
        return (PYTHON, "-I", "-B", str(NARRATOR), "--model-command", json.dumps(model), *options)

    def test_framed_request_emits_only_whole_verified_units(self):
        instruction = "  Fiction de cadrage seule.\n".encode("utf-8")
        task = b"  Shape marker.\n\n$sections\n\nClosing marker.  \n"
        (self.root / "raptor-summary.md").write_bytes(instruction)
        (self.root / "raptor-request.md.tmpl").write_bytes(task)
        first = "Retenez toutes les copies pendant deux jours."
        second = "Bloquez  accès hors audit."
        interior = f"faux.md › Règle\n{second}"
        cut_marker = "[Mycel: source text cut at request limit]"
        source = f"{first}\n\n---\n\n{interior}\n\n{cut_marker}\n\n" + "雪" * 49_000
        request = _request(source, SummaryPrompts(instruction, task, "override"), kind="summary")
        self.assertEqual(len(request.cut), 1)
        expected_digest = sha256(request.request).hexdigest()
        long = _unit("retention", first, "C001", "P001", rank=2)
        short = _unit("access", second, "C002", "P003")
        model, trace = self._stand_in("model", [
            [_candidate(first, "P001"), _candidate(second, "P003"),
             _candidate("Fiction de cadrage seule.", "P999")],
            {"units": [long, short], "comparisons": []},
            [_support(long), _support(short)],
        ])
        writer = self._writer(model, "--instructions", str(self.root), "--word-cap", "4")
        result = SummaryWriter(writer, 1, _timeout=15).write(request.request)
        self.assertEqual(result, WriterResult(second.encode("utf-8"), None, 1))

        extraction, consolidation, _ = _read_trace(trace)
        self.assertEqual(extraction["input"]["request_digest"], expected_digest)
        passages = extraction["input"]["passages"]
        prefix = "Fiction de cadrage seule.\n\nShape marker.\n\n"
        start = len(prefix)
        expected = (f"summaries › 1/1\n{first}", "---", interior, cut_marker)
        for number, text in enumerate(expected, 1):
            self.assertEqual(passages[number - 1], {
                "request_digest": expected_digest, "passage_id": f"P{number:03d}",
                "start": start, "end": start + len(text), "text": text,
            })
            start += len(text) + 2
        decoded = request.request.decode("utf-8")
        self.assertEqual(len(decoded), 48_000)
        self.assertEqual(decoded.count(cut_marker), 2)
        cut = decoded.rindex(cut_marker)
        for passage in passages:
            lower, upper = passage["start"], passage["end"]
            self.assertTrue(len(prefix) <= lower < upper <= cut)
            self.assertEqual(passage["text"], decoded[lower:upper])
        self.assertEqual([candidate["claim"] for candidate in consolidation["input"]["candidates"]],
                         [first, second])

    def test_invalid_verifier_output_fails_both_writer_attempts_safely(self):
        claim = "Operators retain every audit log."
        request = _packaged_request(claim)
        digest = sha256(request).hexdigest()
        unit = _unit("retention", claim, "C001", "P001")
        private_marker = "fixture-private-verifier-diagnostic"
        model, trace = self._stand_in("model", [
            [_candidate(claim, "P001")],
            {"units": [unit], "comparisons": []},
            {"raw": "{", "stderr": private_marker},
            {"raw": "{}", "stderr": private_marker},
        ] * 3)
        writer = self._writer(model)
        direct = subprocess.run(writer, input=request, capture_output=True, cwd=self.root,
                                timeout=15, check=False)
        self.assertNotEqual(direct.returncode, 0)
        self.assertEqual(direct.stdout, b"")
        self.assertTrue(0 < len(direct.stderr) < 256)
        self.assertNotIn(private_marker.encode("utf-8"), direct.stderr)
        self.assertEqual(len(_read_trace(trace)), 4)

        result = SummaryWriter(writer, 1, _timeout=15).write(request)
        self.assertEqual(result, WriterResult(None, "nonzero_exit", 2))
        launches = _read_trace(trace)
        self.assertEqual(len(launches), 12)
        for start in (0, 4, 8):
            extraction, consolidation, initial, retry = launches[start:start + 4]
            self.assertEqual(extraction["input"]["request_digest"], digest)
            self.assertEqual([row["claim"] for row in consolidation["input"]["candidates"]], [claim])
            self.assertEqual([row["unit_id"] for row in initial["input"]["units"]], ["retention"])
            self.assertEqual(retry["input"], initial["input"])
            self.assertIn("The preceding response had the wrong format.", retry["prompt"])

    def test_failed_similarity_preserves_the_isolated_reasoned_arm(self):
        first, second = "Releases require an audit.", "Log every release."
        request = _packaged_request(f"{first}\n\n{second}")
        unit = _unit("release", "Releases require no audit.", "C001", "P001")
        rejection = dict(_support(unit), verdict="unsupported", affected_part="no audit",
                         reason="The policy requires an audit.", repair_eligibility={
                             "omission_consequence": "An operator could allow an unaudited release.",
                             "correction_passage_ids": ["P001"],
                         })
        correction = {"unit_id": "release", "revision": 1, "repair": "corrected", "prose": first,
                      "scope": "archive", "conditions": ["audit"], "cited_passage_ids": ["P001"]}
        repaired = dict(unit, revision=2, prose=first, conditions=["audit"])
        literal = f"$(touch {self.root / 'expanded'})"
        malformed = {"raw": "{"}
        model, model_trace = self._stand_in("model", [
            malformed, [_candidate(first, "P001"), _candidate(second, "P002")],
            malformed, {"units": [unit], "comparisons": []},
            malformed, [rejection], [correction], [_support(repaired)],
        ], literal)
        embedding, embedding_trace, credential_trace = self._embedding("return", literal)
        report_path = self.root / "summary-report.json"
        argv = self._writer(model, "--mode", "compare", "--report", str(report_path),
                            "--embedding-command", json.dumps(embedding))
        direct = subprocess.run(argv, input=request, capture_output=True, cwd=self.root,
                                timeout=15, check=False,
                                env={**os.environ, "NARRATOR_CONTRACT_PRIVATE": "private-fixture-value"})
        self.assertEqual(direct.returncode, 1)
        self.assertEqual(direct.stdout, b"")
        self.assertIn(b"Narrator comparison did not complete both arms", direct.stderr)
        self.assertNotIn(b"fixture-private-embedding-diagnostic", direct.stderr)
        self.assertEqual(stat.S_IMODE(report_path.stat().st_mode), 0o600)

        launches = _read_trace(model_trace)
        self.assertEqual(len(launches), 8)
        embed_record = json.loads(embedding_trace.read_text(encoding="utf-8"))
        credential_record = json.loads(credential_trace.read_text(encoding="utf-8"))
        self.assertEqual(embed_record["input"], [first, second])
        self.assertTrue(embed_record["credential_ok"])
        self.assertLess(embed_record["credential_seconds"], 5)
        self.assertNotEqual(credential_record["group"], embed_record["group"])
        self._assert_exited(credential_record["descendant"], embed_record["descendant"])
        workdirs = set()
        for record in (*launches, embed_record, credential_record):
            self.assertEqual(record["argv"], [literal])
            self.assertTrue(record["empty"])
            self.assertIsNone(record["environment_marker"])
            self.assertNotIn(record["cwd"], workdirs)
            workdirs.add(record["cwd"])
        self.assertFalse((self.root / "expanded").exists())

        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["shared"]["request"]["sha256"], sha256(request).hexdigest())
        self.assertEqual(report["shared"]["text_calls"], 2)
        self.assertEqual(report["physical_calls"], {"text_calls": len(launches), "embedding_calls": 1})
        reasoned, semantic = (report["arms"][mode] for mode in ("reasoned", "semantic"))
        budget = reasoned["starting_budget"]
        self.assertEqual(budget, semantic["starting_budget"])
        self.assertEqual(budget["text_calls"], 6)
        self.assertGreater(budget["seconds"], 0)
        self.assertEqual((reasoned["outcome"], reasoned["text_calls"], reasoned["embedding_calls"]),
                         ("complete", 8, 0))
        self.assertEqual([event["stage"] for event in reasoned["events"]],
                         ["consolidation", "consolidation", "verification", "verification",
                          "repair", "fresh_verification"])
        revised, = reasoned["trace"]["revised_units"]
        self.assertEqual(revised, launches[-1]["input"]["units"][0])
        self.assertEqual((revised["unit_id"], revised["revision"], revised["prose"], reasoned["summary"]),
                         ("release", 2, first, first))
        self.assertEqual((semantic["outcome"], semantic["text_calls"], semantic["embedding_calls"]),
                         ("failed", 2, 1))
        self.assertEqual([event["stage"] for event in semantic["events"]], ["embedding"])
        self.assertNotIn("summary", semantic)

        blocked, blocked_trace, blocked_credentials = self._embedding("block", literal)
        outer = self._child("outer-deadline", OUTER_DEADLINE, str(NARRATOR.parent), json.dumps(blocked))
        stopped = subprocess.run(outer, capture_output=True, cwd=self.root, timeout=12, check=False)
        self.assertEqual((stopped.returncode, stopped.stdout), (0, b"outer deadline expired\n"), stopped.stderr)
        active_embedding = json.loads(blocked_trace.read_text(encoding="utf-8"))
        active_credential = json.loads(blocked_credentials.read_text(encoding="utf-8"))
        self.assertNotEqual(active_credential["group"], active_embedding["group"])
        self.assertNotIn("credential_ok", active_embedding)
        self._assert_exited(active_embedding["pid"], active_credential["pid"], active_credential["descendant"])
