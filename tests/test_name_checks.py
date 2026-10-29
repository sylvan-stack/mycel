# Shared fixtures only; test bodies are in top/ and mid/. See TESTS.md.
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import runpy
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
NAMING = runpy.run_path(str(ROOT / "scripts/name_checks.py"))
SETTLED = "11111111-1111-4111-8111-111111111111"
SHARED = "22222222-2222-4222-8222-222222222222"
MEASURED = "33333333-3333-4333-8333-333333333333"
WITHDRAWN = "44444444-4444-4444-8444-444444444444"
DRAFTED = "55555555-5555-4555-8555-555555555555"
TABLE = "| ID | Mycel must… | From v1 | Verified by |\n|---|---|---|---|\n"


def chapter(spec, status, rows):
    return (f"---\nrole: authored\nspec: {spec}\nstatus: {status}\n---\n# {spec}\n\n## Requirements\n\n"
            + TABLE + "".join(f"| {spec}.{number} <!-- {uuid} --> | {text} | New | {kind} |\n"
                              for number, uuid, text, kind in rows)
            + "\n## Decisions\n\nNone.\n")


def link(name, uuid):
    module, symbol = name.split(".", 1)
    return {"chunk": f"fix:@code/tests/{module}.py#{symbol}", "origin": f"[fix:req:{uuid}:dGl0bGU=]",
            "method": "proven"}


class NameChecksTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.specs = root / "specs"
        self.specs.mkdir()
        self.rows = {
            "01-water.md": chapter("FIX-1", "accepted", [
                (1, SETTLED, "keep the water level", "store"),
                (2, SHARED, "report the water level", "unit"),
                (3, WITHDRAWN, "Withdrawn 8 October 2026; moved to FIX-2.1", "unit")]),
            "02-light.md": chapter("FIX-2", "accepted", [
                (1, SHARED, "report the light", "unit"),
                (2, MEASURED, "find the brightest window", "eval")]),
            "03-soil.md": chapter("FIX-3", "draft", [(1, DRAFTED, "test the soil", "unit")]),
        }
        for name, text in self.rows.items():
            (self.specs / name).write_text(text, encoding="utf-8")
        (self.specs / "README.md").write_text(
            "# Fixture\n\n| Spec | Title | Status |\n|---|---|---|\n"
            "| [FIX-1](01-water.md) | Water | accepted |\n| [FIX-2](02-light.md) | Light | accepted |\n"
            "| [FIX-3](03-soil.md) | Soil | draft |\n", encoding="utf-8")
        self.checks = {
            "test_level.LevelStoreTests.test_keeps": "store",
            "test_level.LevelTests.test_rounds": "unit",
            "test_level.LevelTests.test_reports": "unit",
            "test_shared.ReportTests.test_a": "unit",
            "test_shared.ReportTests.test_b": "unit",
            "test_shared.ReportTests.test_c": "unit",
            "test_shared.ReportTests.test_d": "unit",
            "test_light.LightTests.test_reports": "unit",
            "test_soil.SoilTests.test_tests": "unit",
        }
        self.report = self.write_report(root / "report.json", self.checks)
        links = [link("test_level.LevelTests.test_rounds", SETTLED), link("test_level.LevelStoreTests.test_keeps", SETTLED),
                 link("test_level.LevelTests.test_reports", SETTLED), link("test_level.LevelTests.test_reports", SHARED),
                 link("test_light.LightTests.test_reports", SHARED), link("test_soil.SoilTests.test_tests", DRAFTED),
                 link("test_gone.GoneTests.test_removed", SHARED)]
        links += [link(f"test_shared.ReportTests.test_{letter}", SHARED) for letter in "abcd"]
        links += [link("test_shared.ReportTests.test_a", DRAFTED), {**link("test_level.LevelTests.test_rounds", SHARED),
                                                                    "method": "stated"}]
        self.origins = root / "origins.json"
        self.origins.write_text(json.dumps({"scope": {"repository": "fix"},
                                            "chunks": [{"chunk": item["chunk"], "links": [item]} for item in links]}))

    def tearDown(self):
        self.directory.cleanup()

    def write_report(self, path, checks, passed=True):
        path.write_text(json.dumps({"schema_version": 2, "passed": passed, "errors": [], "checks": [
            {"name": name, "kind": kind, "requirements": [], "status": "passed", "detail": None}
            for name, kind in checks.items()]}))
        return path

    def run_script(self, *arguments):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = NAMING["main"](list(arguments))
        return status, out.getvalue(), err.getvalue()

    def fill(self):
        return self.run_script("fill", "--specifications", str(self.specs), "--origins", str(self.origins),
                               "--report", str(self.report))

    def check(self, *reports):
        return self.run_script("check", "--specifications", str(self.specs),
                               *[part for report in (reports or (self.report,)) for part in ("--report", str(report))])
