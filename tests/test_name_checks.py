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

    def test_fill_names_passing_checks_of_the_own_kind_and_most_specific_first(self):
        status, out, err = self.fill()
        self.assertEqual((status, err), (0, ""))
        self.assertIn("1 of 2 specifications implemented", out)
        self.assertIn("FIX-2 held back by FIX-2.2", out)
        water = (self.specs / "01-water.md").read_text(encoding="utf-8")
        self.assertIn("| `FIX-1.1` | store | `test_level.LevelStoreTests.test_keeps`, "
                      "`test_level.LevelTests.test_rounds`, `test_level.LevelTests.test_reports` |\n", water)
        self.assertIn("| `FIX-1.2` | unit | `test_light.LightTests.test_reports`, `test_shared.ReportTests.test_b`, "
                      "`test_shared.ReportTests.test_c` and 3 more |\n", water)
        self.assertNotIn("FIX-1.3", water.split("## Named checks")[1])
        self.assertNotIn("test_gone", water)
        light = (self.specs / "02-light.md").read_text(encoding="utf-8")
        self.assertIn("| `FIX-2.2` | eval | no on-demand report yet |\n", light)
        self.assertTrue(water.startswith("---\nrole: authored\nspec: FIX-1\nstatus: implemented\n---\n"))
        self.assertIn("status: accepted\n", light)
        index = (self.specs / "README.md").read_text(encoding="utf-8")
        self.assertIn("| [FIX-1](01-water.md) | Water | implemented |\n", index)
        self.assertIn("| [FIX-2](02-light.md) | Light | accepted, held back by FIX-2.2 |\n", index)
        self.assertIn("| [FIX-3](03-soil.md) | Soil | draft |\n", index)

    def test_fill_changes_no_requirement_row_or_draft_and_is_repeatable(self):
        self.assertEqual(self.fill()[0], 0)
        for name in ("01-water.md", "02-light.md"):
            text = (self.specs / name).read_text(encoding="utf-8")
            before = self.rows[name].replace("status: accepted", "status: implemented") if name == "01-water.md" else self.rows[name]
            self.assertEqual(text.split("\n\n## Named checks")[0] + "\n", before)
        self.assertEqual((self.specs / "03-soil.md").read_text(encoding="utf-8"), self.rows["03-soil.md"])
        first = {path.name: path.read_bytes() for path in self.specs.iterdir()}
        self.assertEqual(self.fill()[0], 0)
        self.assertEqual({path.name: path.read_bytes() for path in self.specs.iterdir()}, first)
        self.assertEqual(self.check()[0], 0)

    def test_check_refuses_a_named_check_that_did_not_pass_or_no_longer_exists(self):
        self.assertEqual(self.fill()[0], 0)
        remaining = {name: kind for name, kind in self.checks.items() if name != "test_level.LevelStoreTests.test_keeps"}
        status, _, err = self.check(self.write_report(Path(self.directory.name) / "later.json", remaining))
        self.assertEqual(status, 1)
        self.assertIn("FIX-1.1: test_level.LevelStoreTests.test_keeps did not pass in the reports", err)
        self.assertIn("01-water.md: status implemented, its Named checks say accepted", err)
        self.assertIn("README.md: an index status differs from its chapter", err)

    def test_check_refuses_hand_edits_and_status_drift(self):
        self.assertEqual(self.fill()[0], 0)
        water = self.specs / "01-water.md"
        original = water.read_text(encoding="utf-8")
        water.write_text(original.replace("`test_level.LevelTests.test_reports` |", "`test_level.LevelTests.test_reports` (best) |"),
                         encoding="utf-8")
        status, _, err = self.check()
        self.assertEqual(status, 1)
        self.assertIn("unreadable Checks cell", err)
        water.write_text(original.replace("store |", "unit |", 1), encoding="utf-8")
        self.assertIn("the Named checks rows differ from its active requirements", self.check()[2])
        water.write_text(original.replace("status: implemented", "status: accepted"), encoding="utf-8")
        self.assertIn("01-water.md: status accepted, its Named checks say implemented", self.check()[2])

    def test_check_accepts_an_on_demand_report_only_for_named_checks(self):
        self.assertEqual(self.fill()[0], 0)
        light = self.specs / "02-light.md"
        light.write_text(light.read_text(encoding="utf-8").replace(
            "| eval | no on-demand report yet |", "| eval | `test_eval.EvalSetTests.test_finds_windows` |")
            .replace("status: accepted", "status: implemented"), encoding="utf-8")
        index = self.specs / "README.md"
        index.write_text(index.read_text(encoding="utf-8").replace("accepted, held back by FIX-2.2", "implemented"),
                         encoding="utf-8")
        self.assertIn("FIX-2.2: test_eval.EvalSetTests.test_finds_windows did not pass in the reports", self.check()[2])
        on_demand = self.write_report(Path(self.directory.name) / "eval.json",
                                      {"test_eval.EvalSetTests.test_finds_windows": "eval"})
        status, out, err = self.check(self.report, on_demand)
        self.assertEqual((status, err), (0, ""))
        self.assertIn("2 of 2 specifications implemented", out)

    def test_fill_refuses_a_failed_report_or_a_row_without_one_kind_and_writes_nothing(self):
        failed = self.write_report(Path(self.directory.name) / "failed.json", self.checks, passed=False)
        status, _, err = self.run_script("fill", "--specifications", str(self.specs), "--origins", str(self.origins),
                                         "--report", str(failed))
        self.assertEqual(status, 1)
        self.assertIn("not a passing schema 2 check report", err)
        (self.specs / "02-light.md").write_text(self.rows["02-light.md"].replace("| eval |", "| eval, live |"),
                                                encoding="utf-8")
        status, _, err = self.fill()
        self.assertEqual(status, 1)
        self.assertIn("FIX-2.2 has Verified by 'eval, live', not one kind", err)
        self.assertEqual((self.specs / "01-water.md").read_text(encoding="utf-8"), self.rows["01-water.md"])


if __name__ == "__main__":
    unittest.main()
