"""Exercise Narrator's executable boundary with local process stand-ins."""

from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest

from mycel._resolver import ResolvedChunk, SelectionMember
from mycel._source_refs import SourceAddress
from mycel._summary_request import SummaryPrompts, SummarySection, plan_summary_requests
from mycel._summary_writer import SummaryWriter, WriterResult


NARRATOR = Path(__file__).resolve().parents[2] / "scripts/narrator/narrator.py"
PYTHON = str(Path(sys.executable).absolute())
STAND_IN = """\
import json
import pathlib
import sys

plan, trace = map(pathlib.Path, sys.argv[1:3])
replies = json.loads(plan.read_text(encoding="utf-8"))
index = len(trace.read_text(encoding="utf-8").splitlines()) if trace.exists() else 0
request = sys.stdin.read()
prompt, _, payload = request.rpartition("\\n\\n")
with trace.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({"prompt": prompt, "input": json.loads(payload)}) + "\\n")
sys.stdout.write(json.dumps(replies[index]))
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


def _read_trace(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class NarratorWriterContractTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="narrator-contract-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.stand_in = self.root / "stand-in.py"
        self.stand_in.write_text(STAND_IN, encoding="utf-8")

    def _stand_in(self, name, replies):
        plan = self.root / f"{name}.json"
        plan.write_text(json.dumps(replies), encoding="utf-8")
        trace = self.root / f"{name}.jsonl"
        argv = [PYTHON, "-I", "-B", str(self.stand_in), str(plan), str(trace)]
        return argv, trace

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
        source = f"{first}\n\n---\n\n{interior}\n\n" + "雪" * 49_000
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
        for number, text in enumerate((f"summaries › 1/1\n{first}", "---", interior), 1):
            self.assertEqual(passages[number - 1], {
                "request_digest": expected_digest, "passage_id": f"P{number:03d}",
                "start": start, "end": start + len(text), "text": text,
            })
            start += len(text) + 2
        decoded = request.request.decode("utf-8")
        cut = decoded.index("[Mycel: source text cut at request limit]")
        for passage in passages:
            lower, upper = passage["start"], passage["end"]
            self.assertTrue(len(prefix) <= lower < upper <= cut)
            self.assertEqual(passage["text"], decoded[lower:upper])
        self.assertEqual([candidate["claim"] for candidate in consolidation["input"]["candidates"]],
                         [first, second])
