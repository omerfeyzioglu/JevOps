"""Regression checks for tampered and incomplete published benchmark records."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.verify_results import _verify_benchmark
from jevops.adapters.rules import RulesAdapter
from jevops.benchmark.runner import run_benchmark, summarize_results, write_json, write_jsonl
from jevops.streamguard.simulation import Scenario


class PublishedResultIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.raw = Path(self.directory.name) / "benchmark.jsonl"
        self.summary = self.raw.with_suffix(".summary.json")
        self.rows = run_benchmark([RulesAdapter()], cases=[(s, 101) for s in Scenario])
        self.metadata = {"runs_per_case": 1, "seeds": [101]}

    def write(self):
        write_jsonl(self.rows, self.raw)
        write_json(summarize_results(self.rows), self.summary)

    def test_recomputed_summary_cannot_hide_a_tampered_oracle_score(self):
        self.rows[0]["evaluation"]["action_acceptable"] = False
        self.write()
        with self.assertRaisesRegex(SystemExit, "scoring differs from oracle"):
            _verify_benchmark(self.raw, self.summary, self.metadata, "streamguard", ["rules"])

    def test_recomputed_summary_cannot_hide_duplicate_cases(self):
        self.rows.append(self.rows[0])
        self.write()
        with self.assertRaisesRegex(SystemExit, "missing, duplicate, or unexpected cases"):
            _verify_benchmark(self.raw, self.summary, self.metadata, "streamguard", ["rules"])


if __name__ == "__main__":
    unittest.main()
