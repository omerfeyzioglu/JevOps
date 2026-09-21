"""Command-line entry point for the local StreamGuard vertical slice."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from jevops.adapters import default_adapters
from jevops.adapters.fixtures import TimeoutFixtureAdapter, UnsafeReplayFixtureAdapter
from jevops.benchmark.runner import (
    run_benchmark,
    run_episode_with_adapters,
    run_smoke_suite,
    summarize_results,
    write_json,
    write_jsonl,
)
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

    benchmark = subcommands.add_parser(
        "benchmark", help="Run the full multi-seed Rules/Jev/Laya/GPT/Gemini comparison."
    )
    benchmark.add_argument("--runs", type=_positive_int, default=1)
    benchmark.add_argument("--output", type=Path, default=Path("artifacts/benchmark.jsonl"))

    payrecon = subcommands.add_parser("payrecon", help="Run one deterministic reconciliation exception.")
    payrecon.add_argument("--scenario", choices=[item.value for item in PayReconScenario], required=True)
    payrecon.add_argument("--seed", type=int, default=601)
    payrecon.add_argument("--show-truth", action="store_true")
    return parser


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _adapters(include_fixtures: bool = False):
    adapters = default_adapters()
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
    if args.command == "benchmark":
        rows = run_benchmark(_adapters(), runs=args.runs)
        summary = summarize_results(rows)
        summary_output = args.output.with_suffix(".summary.json")
        write_jsonl(rows, args.output)
        write_json(summary, summary_output)
        for engine_summary in summary:
            print(json.dumps(engine_summary, sort_keys=True))
        print(f"wrote {len(rows)} raw results to {args.output}", file=sys.stderr)
        print(f"wrote summary to {summary_output}", file=sys.stderr)
        return 0
    if args.command == "payrecon":
        episode = run_payrecon_episode(PayReconScenario(args.scenario), args.seed)
        _display_rows(run_episode_with_adapters(episode, _adapters()), show_truth=args.show_truth)
        return 0
    raise AssertionError(f"unhandled command: {args.command}")
