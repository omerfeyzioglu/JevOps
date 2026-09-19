"""Command-line entry point for the local StreamGuard vertical slice."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from jevops.adapters import JevAdapter, LlmAdapter, RulesAdapter
from jevops.adapters.fixtures import TimeoutFixtureAdapter, UnsafeReplayFixtureAdapter
from jevops.benchmark.runner import run_episode_with_adapters, run_smoke_suite, write_jsonl
from jevops.payrecon.simulation import PayReconScenario, run_episode as run_payrecon_episode
from jevops.streamguard.simulation import Scenario, run_episode


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local StreamGuard triage slice.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    simulate = subcommands.add_parser("simulate", help="Run one seeded scenario.")
    simulate.add_argument("--scenario", choices=[item.value for item in Scenario], required=True)
    simulate.add_argument("--seed", type=int, default=201)
    simulate.add_argument("--output", type=Path)
    simulate.add_argument("--show-truth", action="store_true")
    simulate.add_argument(
        "--exercise-fixtures",
        action="store_true",
        help="Add timeout and unsafe-replay test fixtures; never use for provider benchmarks.",
    )

    suite = subcommands.add_parser("smoke-suite", help="Run the 12-episode local contract suite.")
    suite.add_argument("--output", type=Path, default=Path("artifacts/streamguard-smoke.jsonl"))

    payrecon = subcommands.add_parser("payrecon", help="Run one deterministic reconciliation exception.")
    payrecon.add_argument("--scenario", choices=[item.value for item in PayReconScenario], required=True)
    payrecon.add_argument("--seed", type=int, default=601)
    payrecon.add_argument("--show-truth", action="store_true")
    return parser


def _adapters(include_fixtures: bool = False):
    adapters = [RulesAdapter(), JevAdapter(), LlmAdapter()]
    if include_fixtures:
        adapters.extend([TimeoutFixtureAdapter(), UnsafeReplayFixtureAdapter()])
    return adapters


def _display_rows(rows: list[dict[str, object]], *, show_truth: bool) -> None:
    for row in rows:
        audit = row["audit"]
        decision = audit["decision"]
        gate = audit["gate"]
        line = {
            "engine": decision["engine"],
            "status": decision["status"],
            "class": decision["incident_class"],
            "raw_action": gate["raw_action"],
            "effective_action": gate["effective_action"],
            "override_reason": gate["override_reason"],
            "evidence_hash": row["evidence_hash"],
            "detector_opened_at": row["detector_opened_at"],
            "recovered_by_end": row["recovered_by_end"],
        }
        if show_truth:
            line["truth"] = row["truth"]
        print(json.dumps(line, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "simulate":
        episode = run_episode(Scenario(args.scenario), args.seed)
        rows = run_episode_with_adapters(episode, _adapters(args.exercise_fixtures))
        _display_rows(rows, show_truth=args.show_truth)
        if args.output:
            write_jsonl(rows, args.output)
            print(f"wrote {len(rows)} audit records to {args.output}", file=sys.stderr)
        return 0
    if args.command == "smoke-suite":
        rows = run_smoke_suite(_adapters())
        write_jsonl(rows, args.output)
        print(f"wrote {len(rows)} audit records to {args.output}")
        print("API-key-absent providers are recorded as UNAVAILABLE, not mocked.")
        return 0
    if args.command == "payrecon":
        episode = run_payrecon_episode(PayReconScenario(args.scenario), args.seed)
        _display_rows(run_episode_with_adapters(episode, _adapters()), show_truth=args.show_truth)
        return 0
    raise AssertionError(f"unhandled command: {args.command}")
