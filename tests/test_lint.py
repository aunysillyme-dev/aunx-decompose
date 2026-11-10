import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.gettempdir()).resolve()
SCRIPT = ROOT / "skills/decompose/scripts/decompose.py"
EXAMPLES = SCRIPT.parents[1] / "examples"
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPT.parent))
import decompose
import unitmap


def unit(ident, deps=(), **extra):
    row = {"id": ident, "type": "coding", "speed": "standard", "clause_ids": ["C1"],
           "inputs": [d + "-out" for d in deps] or ["source"],
           "outputs": [ident + "-out"], "deps": list(deps), "paths": [],
           "verify": "check the output"}
    row.update(extra)
    return row


class LintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=TMP)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        patcher = mock.patch.dict(os.environ, {
            "DECOMPOSE_RECIPES": str(self.directory / "recipes.json")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def compute(self, units, **limits):
        plan = unitmap.normalize({"clauses": ["C1"], "units": units})
        self.assertEqual(unitmap.validate(plan, decompose.same_path, decompose.path_inside), [])
        return unitmap.compute(plan, unitmap.defaults(limits))

    def run_plan(self, data, *extra):
        path = self.directory / "plan.json"
        path.write_text(json.dumps(data))
        return subprocess.run([sys.executable, str(SCRIPT), "--plan", str(path), *extra],
                              capture_output=True, text=True)

    def orphan_fixture(self):
        return [unit("producer", outputs=["producer-out", "unused-a", "unused-b"]),
                unit("consumer", ["producer"], outputs=["final-a", "final-b"])]

    def reader_fixture(self):
        return [unit("seed")] + [unit("reader%d" % i, ["seed"]) for i in range(3)]

    def assert_question(self, result, *fragments):
        self.assertTrue(result["advisor"]["required"])
        self.assertEqual(len(result["questions"]), len(result["advisor"]["reasons"]))
        self.assertEqual(len(result["questions"]), 1)
        for fragment in fragments:
            self.assertIn(fragment, result["questions"][0])

    def test_wave_wide_top_level_writers(self):
        units = [unit(name, paths=[str(self.directory / name)]) for name in ("a", "b", "c")]
        units.append(unit("read"))
        original = copy.deepcopy(units)
        result = self.compute(units)
        rows = {u["id"]: u for u in result["units"]}
        for name in ("a", "b", "c"):
            self.assertEqual(rows[name]["shape"], "split-worktrees")
            self.assertEqual(rows[name]["shape_reason"], "3 writers in this wave on disjoint paths")
        self.assertEqual(rows["read"]["shape"], "single")
        self.assertEqual(units, original)

    def test_wave_wide_preserves_hints_and_other_shapes(self):
        units = [unit(name, paths=[str(self.directory / name)]) for name in ("a", "b", "hint", "batch")]
        units[2]["dispatch_hint"] = "single"
        units[3]["item_count"] = 4
        rows = {u["id"]: u for u in self.compute(units)["units"]}
        for name in ("a", "b"):
            self.assertEqual(rows[name]["shape"], "split-worktrees")
            self.assertEqual(rows[name]["shape_reason"], "2 writers in this wave on disjoint paths")
        self.assertEqual(rows["hint"]["shape"], "single")
        self.assertEqual(rows["hint"]["shape_reason"], "dispatch_hint")
        self.assertEqual(rows["batch"]["shape"], "subagents")

    def test_writers_in_different_waves_stay_single(self):
        units = [unit("a", paths=[str(self.directory / "a")]),
                 unit("b", ["a"], paths=[str(self.directory / "b")])]
        self.assertEqual([u["shape"] for u in self.compute(units)["units"]], ["single", "single"])

    def test_sibling_shapes_keep_existing_rule(self):
        units = [unit("S.1", parent_id="S", paths=[str(self.directory / "a")]),
                 unit("S.2", parent_id="S", paths=[str(self.directory / "b")])]
        for row in self.compute(units)["units"]:
            self.assertEqual(row["shape"], "split-worktrees")
            self.assertEqual(row["shape_reason"], "2 writers on disjoint paths")
        units[1]["paths"] = []
        self.assertEqual([u["shape"] for u in self.compute(units)["units"]], ["single", "single"])

    def test_orphan_outputs_warn_per_unused_output(self):
        result = self.compute(self.orphan_fixture())
        self.assertFalse(result["advisor"]["required"])
        self.assertEqual(len(result["warnings"]), 2)
        for warning, output in zip(result["warnings"], ("unused-a", "unused-b")):
            self.assertIn("producer", warning)
            self.assertIn(output, warning)
        self.assertFalse(any("final-" in w for w in result["warnings"]))

    def test_consumed_outputs_and_terminal_deliverables_stay_silent(self):
        units = [unit("a", outputs=["a-out", "extra"]), unit("b", ["a"]),
                 unit("c", ["a"], inputs=["extra"])]
        self.assertEqual(self.compute(units)["warnings"], [])
        self.assertEqual(self.compute([unit("final", outputs=["one", "two"])])["warnings"], [])

    def test_no_invalidator_warning_names_all_triggers_once(self):
        units = [unit("S%d" % i, ["S%d" % (i - 1)] if i else []) for i in range(6)]
        result = self.compute(units)
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("invalidator", result["warnings"][0])
        self.assertEqual(len(result["advisor"]["reasons"]), 2)
        for reason in result["advisor"]["reasons"]:
            self.assertIn(reason, result["warnings"][0])
        self.assertEqual(len(result["questions"]), 2)
        units[0]["is_invalidator"] = True
        self.assertEqual(self.compute(units)["warnings"], [])

    def test_step_question_names_two_smallest_steps(self):
        units = [unit("small-a"), unit("small-b")]
        units += [unit("S%d.%d" % (s, i), parent_id="S%d" % s)
                  for s in range(4) for i in range(2)]
        result = self.compute(units)
        self.assert_question(result, "steps=6", "small-a", "small-b", "1 unit", "merge")
        self.assertNotIn("S0.0", result["questions"][0])

    def test_unit_question_names_largest_type_and_speed_group(self):
        units = [unit("S.%d" % i, parent_id="S", type="research", speed="fast") for i in range(8)]
        units += [unit("S.%d" % i, parent_id="S", type="research") for i in range(8, 11)]
        units.append(unit("S.11", parent_id="S", type="data", speed="fast"))
        result = self.compute(units)
        self.assert_question(result, "units=12", "research", "fast", "8 units", "item_count")
        for i in range(8):
            self.assertIn("S.%d" % i, result["questions"][0])
        self.assertNotIn("S.8", result["questions"][0])

    def test_serial_question_names_critical_path_and_metric(self):
        units = [unit("S%d" % i, ["S%d" % (i - 1)] if i else [], needs={"minutes": i + 1})
                 for i in range(4)]
        result = self.compute(units)
        self.assert_question(result, "4 step waves", "4 steps", "S0 -> S1 -> S2 -> S3",
                             "10 minutes", "data edge", "partial output")

    def test_reader_question_names_unit_and_reader_count(self):
        result = self.compute(self.reader_fixture())
        self.assert_question(result, "seed", "3", "verified", "readers start", "invalidator")

    def test_threshold_overrides_drive_questions(self):
        result = self.compute([unit("a"), unit("b")], advisor_max_steps=1)
        self.assert_question(result, "steps=2", "a", "b", "merge")
        result = self.compute([unit("a"), unit("b")], advisor_min_units=2)
        self.assert_question(result, "units=2", "2 units", "item_count")
        result = self.compute([unit("a"), unit("b", ["a"])], advisor_serial_min_steps=2)
        self.assert_question(result, "2 step waves", "a -> b", "2 units", "partial output")
        result = self.compute([unit("a"), unit("b", ["a"])], advisor_min_readers=1)
        self.assert_question(result, "a", "1", "invalidator")

    def test_no_gate_no_questions_including_threshold_boundaries(self):
        units = [unit("S.%d" % i, parent_id="S") for i in range(11)]
        for fixture in ([unit("final")], [unit("S%d" % i) for i in range(5)], units,
                        [unit("a"), unit("b", ["a"]), unit("c", ["a"])],
                        [unit("a"), unit("b", ["a"]), unit("c", ["b"]), unit("d")]):
            with self.subTest(ids=[u["id"] for u in fixture]):
                result = self.compute(fixture)
                self.assertFalse(result["advisor"]["required"])
                self.assertEqual(result["questions"], [])
                self.assertEqual(result["warnings"], [])

    def test_interleaving_gate_also_has_a_question(self):
        units = [unit("A.1", parent_id="A"), unit("B.1", ["A.1"], parent_id="B"),
                 unit("A.2", ["B.1"], parent_id="A")]
        result = self.compute(units, advisor_serial_min_steps=2)
        self.assert_question(result, "A.1 -> B.1 -> A.2", "2 steps", "interleave", "data edge")

    def test_example_has_no_warnings_and_expected_reader_question(self):
        example = json.loads((EXAMPLES / "plan.json").read_text())
        result = self.run_plan(example, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["warnings"], [])
        self.assert_question(data, "S1", "3", "verified before its readers start")
        # S1 is already an invalidator, so the question does not suggest making it one.
        self.assertNotIn("should it be an invalidator", data["questions"][0])

    def test_table_sections_follow_coverage_and_do_not_change_exit(self):
        units = self.orphan_fixture() + self.reader_fixture()
        result = self.run_plan({"clauses": ["C1"], "units": units})
        self.assertEqual(result.returncode, 0, result.stderr)
        text = result.stdout
        self.assertLess(text.index("Clause coverage:"), text.index("Warnings:"))
        self.assertLess(text.index("Warnings:"), text.index("Advisor questions:"))
        self.assertIn("unused-a", text)
        self.assertIn("seed", text)
        for fixture, warnings, questions in (([unit("final")], False, False),
                                              (self.orphan_fixture(), True, False)):
            result = self.run_plan({"clauses": ["C1"], "units": fixture})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual("Warnings:" in result.stdout, warnings)
            self.assertEqual("Advisor questions:" in result.stdout, questions)

    def test_json_keys_always_present_and_saved_json_round_trips(self):
        for units in ([unit("final")], self.orphan_fixture() + self.reader_fixture()):
            result = self.run_plan({"clauses": ["C1"], "units": units}, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertIsInstance(data["warnings"], list)
            self.assertIsInstance(data["questions"], list)
            rerun = self.run_plan(data, "--json")
            self.assertEqual(rerun.returncode, 0, rerun.stderr)
            self.assertEqual(json.loads(rerun.stdout), data)

    def test_patched_json_round_trips_with_questions(self):
        example = json.loads((EXAMPLES / "plan.json").read_text())
        result = self.run_plan(example, "--apply-patch", str(EXAMPLES / "patch.json"), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["patched"])
        self.assertTrue(data["questions"])
        rerun = self.run_plan(data, "--json")
        self.assertEqual(rerun.returncode, 0, rerun.stderr)
        expected = dict(data, patched=False)
        self.assertEqual(json.loads(rerun.stdout), expected)


if __name__ == "__main__":
    unittest.main()
