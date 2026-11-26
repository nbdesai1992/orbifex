"""The README's numbers must be the ones counted from the run records.

Run with: python -m unittest discover -s tests
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import make_readme_figure  # noqa: E402
import results_table  # noqa: E402
import tree_sha256  # noqa: E402

README = (ROOT / "README.md").read_text()


def block(name: str) -> str:
    start, end = f"<!-- {name}:start -->\n", f"<!-- {name}:end -->"
    return README.split(start)[1].split(end)[0]


class CountingTests(unittest.TestCase):
    def test_tally_counts_correct_runs_per_tier(self):
        records = [{"tier": 1, "correct": True}, {"tier": 1, "correct": False}, {"tier": 2, "correct": True}]
        self.assertEqual(results_table.tally(records), {1: (1, 2), 2: (1, 1)})
        self.assertEqual(results_table.total(results_table.tally(records)), (2, 3))
        self.assertEqual(results_table.total(results_table.tally(records), tiers=(2,)), (1, 1))

    def test_interval_and_exact_test(self):
        low, high = results_table.wilson(1, 156)
        self.assertAlmostEqual(low, 0.00113, places=5)
        self.assertAlmostEqual(high, 0.03541, places=5)
        self.assertAlmostEqual(results_table.fisher_two_sided(4, 8, 12, 0), 2 * 1820 / 2704156, places=9)
        self.assertAlmostEqual(results_table.fisher_two_sided(3, 3, 3, 3), 1.0, places=9)


class PublishedNumbers(unittest.TestCase):
    """The pilot as it was run. These change only if the committed records change."""

    @classmethod
    def setUpClass(cls):
        cls.s = results_table.summarize()

    def test_runs_correct_by_size(self):
        s = self.s
        self.assertEqual([s["lookup"][t] for t in (1, 2, 3, 4)], [(39, 39), (39, 39), (38, 39), (39, 39)])
        self.assertEqual([s["sweep"][t] for t in (1, 2, 3, 4)], [(24, 24), (24, 24), (18, 24), (21, 24)])
        self.assertEqual([s["late"][t] for t in (1, 2, 3, 4)], [(6, 6), (6, 6), (1, 6), (3, 6)])
        self.assertEqual(s["ablation"], {3: (6, 6), 4: (6, 6)})

    def test_every_record_names_one_model(self):
        self.assertEqual(self.s["model_ids"], ["claude-haiku-5-5"])
        self.assertEqual(self.s["runs"]["all"], 616)

    def test_all_question_policy_rates_are_the_ones_in_ladder_json(self):
        ladder = json.loads((results_table.V2 / "ladder.json").read_text())
        for name in ("first_hit", "latest_wins"):
            rates = [round(c / n, 3) for c, n in self.s["policies"][name, "all"].values()]
            self.assertEqual(rates, ladder[f"monotone_probe_{name}"]["values"])
            self.assertEqual({n for _, n in self.s["policies"][name, "lookup"].values()}, {39})

    def test_readme_tables_match_the_records(self):
        self.assertEqual(block("results-table"), results_table.table(self.s))
        self.assertEqual(block("policy-table"), results_table.policy_table(self.s))

    def test_readme_states_the_headline_numbers(self):
        facts = results_table.facts(self.s)
        for key in ("model", "runs correct, eight-source version", "lookup runs correct",
                    "misses on the late-payer sweep question", "late-payer sweep at the two largest sizes",
                    "the same runs with invoicing/ deleted", "growth in tokens", "tokens, smallest to largest",
                    "recorded cost of the pilot", "recorded cost of the ablation",
                    "mean facts a sweep answer needs, smallest to largest", "mean facts a lookup answer needs",
                    "lookup error rate, 95% Wilson interval",
                    "ablation against unablated runs, Fisher exact, two-sided"):
            self.assertTrue(facts[key] in README, f"README does not state {key}: {facts[key]}")
        first, last = facts["files, smallest to largest"].split(" to ")
        for phrase in (f"from {first} files to {last}", facts["four-source version"].split(" (")[0],
                       f"{self.s['runs']['all']} in all"):
            self.assertTrue(phrase in README, f"README does not state: {phrase}")

    def test_readme_figure_is_drawn_from_the_records(self):
        self.assertEqual(make_readme_figure.OUT.read_text(), make_readme_figure.render(self.s))


class TreeChecksumTests(unittest.TestCase):
    def test_checksum_depends_on_paths_and_contents_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            for root in (a, b):
                (root / "set-t1" / "task").mkdir(parents=True)
                (root / "set-t1" / "task" / "x.txt").write_text("one\n")
                (root / "set-t1" / "y.txt").write_text("two\n")
            (b / "NOTES.md").write_text("not part of the set\n")
            first, second = tree_sha256.manifest(a, "set-t*"), tree_sha256.manifest(b, "set-t*")
            self.assertEqual(list(first), ["set-t1/task/x.txt", "set-t1/y.txt"])
            self.assertEqual(tree_sha256.digest(first), tree_sha256.digest(second))
            self.assertEqual(tree_sha256.differences(first, second), [])
            self.assertEqual(tree_sha256.differences(first, tree_sha256.manifest(b)), ["only in the second tree: NOTES.md"])
            (b / "set-t1" / "y.txt").write_text("changed\n")
            changed = tree_sha256.manifest(b, "set-t*")
            self.assertNotEqual(tree_sha256.digest(first), tree_sha256.digest(changed))
            self.assertEqual(tree_sha256.differences(first, changed), ["contents differ: set-t1/y.txt"])


if __name__ == "__main__":
    unittest.main()
