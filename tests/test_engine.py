"""Engine tests. Run with: python -m unittest discover -s tests"""
import io
import json
import sys
import tarfile
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from orbifex import checks, harbor, verify  # noqa: E402
from orbifex.cli import build_tier  # noqa: E402
from orbifex.world import build_world, load_pack  # noqa: E402

PACK = load_pack(ROOT / "personas" / "cpa-solo.toml")
STUDIO = load_pack(ROOT / "personas" / "studio-retainer.toml")


def core_truth(world):
    return {c.fid: (c.role, c.final("meeting"), c.meeting_minutes, c.meeting_mode, c.invoice_no, c.final("hours"),
                    c.final("amount"), c.final("due"), c.paid_at, c.paid_amount, c.docs_at, c.issued_at)
            for c in world.core_cycles}


class WorldTests(unittest.TestCase):
    def test_core_truth_is_the_same_at_every_tier(self):
        for seed in range(1, 21):
            base = core_truth(build_world(PACK, 1, seed))
            for tier in (2, 3, 4):
                self.assertEqual(core_truth(build_world(PACK, tier, seed)), base, f"seed {seed} tier {tier}")

    def test_higher_tiers_add_history_not_new_truth(self):
        t1, t4 = build_world(PACK, 1, 7), build_world(PACK, 4, 7)
        self.assertTrue(all(len(c.meeting) == 1 and len(c.amount) == 1 and len(c.due) == 1 for c in t1.core_cycles))
        self.assertGreater(sum(len(c.meeting) + len(c.amount) + len(c.due) - 3 for c in t4.core_cycles), 6)

    def test_same_seed_same_bytes(self):
        a = build_tier(PACK, 3, 7)
        b = build_tier(PACK, 3, 7)
        self.assertEqual(harbor.world_tarball(a[0], a[1]), harbor.world_tarball(b[0], b[1]))


class GateTests(unittest.TestCase):
    def test_every_gate_passes_and_the_ladder_is_monotone(self):
        for seed in (7, 11, 23):
            reports, tasks = {}, {}
            for tier in (1, 2, 3, 4):
                _, _, tasks[tier], reports[tier] = build_tier(PACK, tier, seed)
                failed = [k for k, g in reports[tier]["gates"].items() if isinstance(g, dict) and not g["passed"]]
                self.assertEqual(failed, [], f"seed {seed} tier {tier}")
            ladder = checks.ladder_checks(reports, tasks)
            self.assertTrue(ladder["answers_preserved"]["passed"], f"seed {seed}")
            self.assertTrue(ladder["passed"], f"seed {seed}: {ladder}")

    def test_a_second_persona_passes_the_same_gates(self):
        reports, tasks = {}, {}
        for tier in (1, 2, 3, 4):
            _, _, tasks[tier], reports[tier] = build_tier(STUDIO, tier, 7)
            self.assertTrue(reports[tier]["gates"]["passed"], f"tier {tier}")
        self.assertTrue(checks.ladder_checks(reports, tasks)["passed"])

    def test_a_different_seed_gives_different_answers(self):
        a = {t.id.split("-")[0]: t.gold for t in build_tier(PACK, 1, 7)[2]}
        b = {t.id.split("-")[0]: t.gold for t in build_tier(PACK, 1, 8)[2]}
        self.assertGreater(sum(a[k] != b[k] for k in a), len(a) // 2)


class VerifierTests(unittest.TestCase):
    def test_grading(self):
        gold = {"amount": 1040.0, "invoice_number": "INV-2031", "before": True, "ids": ["INV-1", "INV-2"],
                "start_time": "14:00", "date": "2026-05-14"}
        self.assertTrue(verify.grade(dict(gold), gold)[0])
        self.assertTrue(verify.grade({**gold, "amount": "$1,040.00", "invoice_number": "inv-2031",
                                      "ids": ["inv-2", "INV-1"], "start_time": "14:00:00"}, gold)[0])
        for wrong in ({**gold, "amount": 1040.01}, {**gold, "before": False}, {**gold, "ids": ["INV-1"]},
                      {**gold, "date": "2026-05-15"}, {k: v for k, v in gold.items() if k != "date"}, [], None, "x"):
            self.assertFalse(verify.grade(wrong, gold)[0], wrong)


class ExportTests(unittest.TestCase):
    def test_exported_task_layout_and_isolation(self):
        world, rendered, tasks, report = build_tier(PACK, 2, 7)
        with tempfile.TemporaryDirectory() as tmp:
            out = harbor.export(world, rendered, tasks, report["measure"], Path(tmp) / "ds")
            task = tasks[0]
            d = out / task.id
            for rel in ("instruction.md", "task.toml", "environment/Dockerfile",
                        "tests/Dockerfile", "tests/test.sh", "tests/verify.py",
                        "solution/solve.sh", "solution/oracle.py", "solution/spec.json"):
                self.assertTrue((d / rel).is_file(), rel)
            for pattern in ("environment/world.*.tar.gz", "tests/gold.*.json", "tests/negatives.*.json"):
                self.assertEqual(len(list(d.glob(pattern))), 1, pattern)
            cfg = tomllib.loads((d / "task.toml").read_text())
            self.assertEqual(cfg["schema_version"], "1.4")
            self.assertEqual(cfg["verifier"]["environment_mode"], "separate")
            self.assertEqual(cfg["artifacts"], ["/workspace/answer.json"])
            self.assertEqual(cfg["metadata"]["tier"], 2)
            names = tarfile.open(fileobj=io.BytesIO(next((d / "environment").glob("world.*.tar.gz")).read_bytes())).getnames()
            self.assertFalse([n for n in names if "gold" in n or "manifest" in n or "answer" in n])
            self.assertNotIn("gold", json.dumps(json.loads((d / "solution" / "spec.json").read_text())))
            self.assertEqual(sorted(p.name for p in out.iterdir()), sorted(t.id for t in tasks))

class BuildContextTests(unittest.TestCase):
    """Docker reuses a build-context file from another folder of the same name when path, size and
    timestamp match. Files that sit in a build context must therefore never share a path across
    tasks unless they also share their content."""

    def test_same_path_in_a_build_context_means_same_content(self):
        import hashlib
        seen: dict[tuple[str, str], str] = {}
        with tempfile.TemporaryDirectory() as tmp:
            for tier in (2, 3):
                world, rendered, tasks, report = build_tier(PACK, tier, 7)
                out = harbor.export(world, rendered, tasks, report["measure"], Path(tmp) / f"t{tier}")
                for context in out.glob("*/environment"), out.glob("*/tests"):
                    for folder in context:
                        for f in folder.iterdir():
                            key = (folder.name, f.name)
                            digest = hashlib.sha256(f.read_bytes()).hexdigest()
                            self.assertEqual(seen.setdefault(key, digest), digest, f"{key} differs between tasks")

    def test_verifier_refuses_a_key_that_is_not_its_own(self):
        with tempfile.TemporaryDirectory() as tmp:
            tests_dir, out = Path(tmp) / "tests", Path(tmp) / "logs"
            tests_dir.mkdir()
            (Path(tmp) / "answer.json").write_text('{"date": "2026-05-14"}')
            (tests_dir / "gold.000000000000.json").write_text('{"date": "2026-05-14"}\n')   # name does not match content
            with self.assertRaises(SystemExit):
                verify.main(str(Path(tmp) / "answer.json"), str(tests_dir), str(out))
            self.assertFalse((out / "reward.txt").exists())
            (tests_dir / "gold.111111111111.json").write_text("{}")                          # two keys present
            with self.assertRaises(SystemExit):
                verify.main(str(Path(tmp) / "answer.json"), str(tests_dir), str(out))


if __name__ == "__main__":
    unittest.main()
