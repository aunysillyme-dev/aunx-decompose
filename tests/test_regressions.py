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
EXAMPLES = SCRIPT.parent.parent / "examples"
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPT.parent))
import decompose
import unitmap


def unit(ident, inputs, outputs, deps=(), **extra):
    row = {"id": ident, "type": "data", "speed": "fast", "clause_ids": ["C1"], "inputs": list(inputs),
           "outputs": list(outputs), "deps": list(deps), "paths": [], "verify": "check it"}
    row.update(extra)
    return row


class UnitMapRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=TMP)
        self.addCleanup(self.temp.cleanup)
        patcher = mock.patch.dict(os.environ, {"DECOMPOSE_RECIPES": str(Path(self.temp.name) / "r.json")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_plan(self, data, *extra):
        path = Path(self.temp.name) / "plan.json"
        path.write_text(json.dumps(data))
        return subprocess.run([sys.executable, str(SCRIPT), "--plan", str(path), *map(str, extra)],
                              capture_output=True, text=True)

    def test_plan_json_round_trip(self):
        example = json.loads((EXAMPLES / "plan.json").read_text())
        for patched in (False, True):
            with self.subTest(patched=patched):
                extra = ["--apply-patch", EXAMPLES / "patch.json"] if patched else []
                first = self.run_plan(example, "--json", *extra)
                self.assertEqual(first.returncode, 0, first.stderr)
                data = json.loads(first.stdout)
                self.assertEqual(set(data), {"ask", "clauses", "units", "advisor", "waves",
                                             "critical_path", "coverage", "steps", "patched", "warnings", "questions"})
                self.assertEqual(data["patched"], patched)
                for row in data["units"]:
                    row.update(model="chosen-model", machine="chosen-machine", runner_up="alternate-model")
                before = copy.deepcopy(data)
                second = self.run_plan(data, "--json")
                self.assertEqual(second.returncode, 0, second.stderr)
                expected = copy.deepcopy(data)
                expected["patched"] = False
                self.assertEqual(json.loads(second.stdout), expected)
                for source in (data, {k: data[k] for k in ("ask", "clauses", "units")}):
                    clean = unitmap.normalize(source)
                    self.assertEqual(set(clean), {"ask", "clauses", "units"})
                    for row in clean["units"]:
                        self.assertFalse(set(row) & {"wave", "parallel_group", "downstream_readers",
                                                     "shape", "shape_reason"})
                self.assertEqual(data, before)

    def test_split_review_children_gate_all_readers(self):
        plan = unitmap.normalize({"clauses": ["C1"], "units": [
            unit("S0", ["source"], ["seed"]),
            unit("S1", ["source"], ["draft", "data"]),
            unit("S2", ["draft", "seed"], ["published"], ["S1", "S0"]),
            unit("S3", ["data"], ["report"], ["S1"]),
            unit("S4", ["source"], ["unrelated"]),
        ]})
        advice = {"split": [{"id": "S1", "into": [
            {"id": "S1.1", "outputs": ["draft"]},
            {"id": "S1.2", "outputs": ["data"]},
            {"id": "S1.3", "type": "review", "inputs": ["draft"], "deps": ["S1.1"],
             "outputs": ["review-ok", "review-notes"]},
            {"id": "S1.4", "type": "review", "inputs": ["data"], "deps": ["S1.2"],
             "outputs": ["data-ok"]},
        ]}]}
        original = copy.deepcopy(plan)
        original_advice = copy.deepcopy(advice)
        self.assertEqual(unitmap.validate(plan, decompose.same_path, decompose.path_inside), [])
        patched = unitmap.apply_patch(plan, advice)
        rows = {row["id"]: row for row in patched["units"]}
        for ident, feeder, inputs, other_deps in (
                ("S2", "S1.1", ["draft", "seed"], ["S0"]),
                ("S3", "S1.2", ["data"], [])):
            with self.subTest(reader=ident):
                self.assertEqual(rows[ident]["deps"], other_deps + [feeder, "S1.3", "S1.4"])
                self.assertEqual(rows[ident]["inputs"], inputs + ["review-ok", "review-notes", "data-ok"])
        self.assertEqual(rows["S4"], original["units"][-1])
        self.assertEqual(unitmap.validate(patched, decompose.same_path, decompose.path_inside), [])
        waves = unitmap.compute(patched, unitmap.defaults())["waves"]
        positions = {ident: index for index, wave in enumerate(waves) for ident in wave}
        for reader in ("S2", "S3"):
            for review in ("S1.3", "S1.4"):
                self.assertGreater(positions[reader], positions[review])
        self.assertEqual(plan, original)
        self.assertEqual(advice, original_advice)
        invalid = copy.deepcopy(advice)
        invalid["needs"] = [{"id": "missing", "needs": {"minutes": 1}}]
        with self.assertRaisesRegex(ValueError, "needs: unknown unit missing"):
            unitmap.apply_patch(plan, invalid)
        self.assertEqual(plan, original)

    def test_unknown_fields_still_rejected(self):
        plan = {"clauses": ["C1"], "units": [unit("S1", ["source"], ["result"])]}
        bad = copy.deepcopy(plan)
        bad["not_computed"] = True
        result = self.run_plan(bad)
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown plan field: not_computed", result.stderr)
        bad = copy.deepcopy(plan)
        bad["units"][0]["not_computed"] = True
        result = self.run_plan(bad)
        self.assertEqual(result.returncode, 2)
        self.assertIn("S1: unknown field not_computed", result.stderr)


if __name__ == "__main__":
    unittest.main()
