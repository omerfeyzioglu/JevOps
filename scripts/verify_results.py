"""Verify that committed benchmark summaries match their raw audit records."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from jevops.benchmark.runner import summarize_results, BENCHMARK_SNAPSHOT_SECONDS
from jevops.benchmark.oracle import evaluate, truth_as_dict
from jevops.contracts import Action, DecisionResult, EvidenceSnapshot, IncidentClass, ProviderStatus
from jevops.streamguard.simulation import Scenario, run_episode
from jevops.payrecon.simulation import PayReconScenario, run_episode as run_payrecon_episode
from jevops.streamguard.actions import validate_action as streamguard_gate
from jevops.payrecon.actions import validate_action as payrecon_gate


def _latest_results_dir(root: Path) -> Path:
    candidates = sorted(path for path in root.iterdir() if path.is_dir())
    if not candidates:
        raise SystemExit(f"no result directories found under {root}")
    return candidates[-1]


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _verify_benchmark(raw_path: Path, summary_path: Path, metadata: dict, domain: str, engines: list[str]) -> None:
    rows = _read_jsonl(raw_path)
    expected_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    actual_summary = summarize_results(rows)
    if actual_summary != expected_summary:
        raise SystemExit(f"summary does not match raw records: {summary_path}")

    evidence_by_case: dict[tuple[object, object, object], set[object]] = {}
    records: Counter = Counter()
    for row in rows:
        benchmark = row["benchmark"]
        truth = row["truth"]
        key = (benchmark["run"], truth["scenario"], benchmark["seed"])
        evidence_by_case.setdefault(key, set()).add(row["evidence_hash"])
        records[(*key, row["audit"]["decision"]["engine"])] += 1
        scenario = truth["scenario"]
        episode = (
            run_episode(Scenario(scenario), benchmark["seed"], snapshot_second=BENCHMARK_SNAPSHOT_SECONDS.get(Scenario(scenario)))
            if domain == "streamguard"
            else run_payrecon_episode(PayReconScenario(scenario), benchmark["seed"])
        )
        if row["evidence"] != episode.evidence.model_state() or row["evidence_hash"] != episode.evidence.input_hash:
            raise SystemExit(f"evidence differs from seeded simulation: {raw_path}, {key}")
        if truth != truth_as_dict(episode.truth):
            raise SystemExit(f"truth differs from seeded simulation: {raw_path}, {key}")
        raw_decision = dict(row["audit"]["decision"])
        raw_decision["status"] = ProviderStatus(raw_decision["status"])
        raw_decision["incident_class"] = IncidentClass(raw_decision["incident_class"]) if raw_decision["incident_class"] else None
        raw_decision["recommended_action"] = Action(raw_decision["recommended_action"]) if raw_decision["recommended_action"] else None
        decision = DecisionResult(**raw_decision)
        if row["evaluation"] != asdict(evaluate(decision, episode.truth)):
            raise SystemExit(f"scoring differs from oracle: {raw_path}, {key}")
        gate = streamguard_gate if domain == "streamguard" else payrecon_gate
        if row["audit"]["gate"] != asdict(gate(episode.evidence, decision)):
            raise SystemExit(f"gate differs from policy: {raw_path}, {key}")
        if row["audit"]["evidence_hash"] != row["evidence_hash"]:
            raise SystemExit(f"audit hash mismatch: {raw_path}, {key}")
    if any(len(hashes) != 1 for hashes in evidence_by_case.values()):
        raise SystemExit(f"engines did not share one evidence hash per case: {raw_path}")

    scenarios = Scenario if domain == "streamguard" else PayReconScenario
    expected = Counter({(run, scenario.value, seed, engine): 1
                        for run in range(1, metadata["runs_per_case"] + 1)
                        for scenario in scenarios for seed in metadata["seeds"] for engine in engines})
    if records != expected:
        raise SystemExit(f"missing, duplicate, or unexpected cases: {raw_path}")
    attempts = {item["total_attempts"] for item in actual_summary}
    print(
        f"verified {raw_path}: {len(rows)} decisions, "
        f"{len(evidence_by_case)} cases, {len(engines)} engines, attempts={sorted(attempts)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path)
    args = parser.parse_args()
    results_dir = args.results_dir or _latest_results_dir(Path("results"))
    directories = [results_dir]
    diagnostics = results_dir / "diagnostics"
    if diagnostics.exists():
        directories.extend(p.parent for p in sorted(diagnostics.rglob("run-metadata.json")))
    for directory in directories:
        metadata = json.loads((directory / "run-metadata.json").read_text())
        for domain in ("streamguard", "payrecon"):
            stem = directory / f"benchmark-{domain}"
            _verify_benchmark(stem.with_suffix(".jsonl"), stem.with_suffix(".summary.json"), metadata, domain, metadata["engines"])
            if metadata.get("cpu_comparison"):
                cpu_stem = directory / f"benchmark-{domain}-laya-cpu"
                _verify_benchmark(cpu_stem.with_suffix(".jsonl"), cpu_stem.with_suffix(".summary.json"), metadata, domain, ["laya-cpu"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
