"""Run common evidence through adapters and preserve an auditable result."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json
import math
from statistics import median
from typing import Iterable

from jevops.adapters.base import DecisionAdapter
from jevops.benchmark.oracle import evaluate, truth_as_dict
from jevops.contracts import AuditRecord
from jevops.payrecon.actions import validate_action as validate_payrecon_action
from jevops.streamguard.actions import validate_action as validate_streamguard_action
from jevops.streamguard.simulation import Episode, Scenario, run_episode


def run_episode_with_adapters(
    episode: Episode, adapters: Iterable[DecisionAdapter]
) -> list[dict[str, object]]:
    """Run each engine against the same snapshot, then evaluate outside the engine."""

    rows: list[dict[str, object]] = []
    for adapter in adapters:
        decision = adapter.decide(episode.evidence)
        gate = (
            validate_streamguard_action(episode.evidence, decision)
            if episode.evidence.domain == "streamguard"
            else validate_payrecon_action(episode.evidence, decision)
        )
        audit = AuditRecord(episode.evidence.input_hash, decision, gate)
        score = evaluate(decision, episode.truth)
        rows.append(
            {
                "domain": "streamguard",
                "evidence": episode.evidence.model_state(),
                "evidence_hash": episode.evidence.input_hash,
                "audit": audit.as_dict(),
                "evaluation": asdict(score),
                "truth": truth_as_dict(episode.truth),
                "detector_opened_at": getattr(episode, "detector_opened_at", None),
                "recovered_by_end": getattr(
                    episode, "recovered_by_end", getattr(episode, "reconciled_by_end", False)
                ),
            }
        )
    return rows


SMOKE_CASES: tuple[tuple[Scenario, int], ...] = (
    (Scenario.NORMAL, 101),
    (Scenario.NORMAL, 102),
    (Scenario.SINK_SLOWDOWN_RECOVERABLE, 201),
    (Scenario.SINK_SLOWDOWN_RECOVERABLE, 202),
    (Scenario.SINK_SLOWDOWN_RECOVERABLE, 203),
    (Scenario.SINK_FAILURE_PERSISTENT, 301),
    (Scenario.SINK_FAILURE_PERSISTENT, 302),
    (Scenario.SINK_FAILURE_PERSISTENT, 303),
    (Scenario.TRAFFIC_SPIKE, 401),
    (Scenario.TRAFFIC_SPIKE, 402),
    (Scenario.AMBIGUOUS_EARLY, 501),
    (Scenario.AMBIGUOUS_EARLY, 502),
)

BENCHMARK_SEEDS: tuple[int, ...] = (101, 202, 303)
BENCHMARK_CASES: tuple[tuple[Scenario, int], ...] = tuple(
    (scenario, seed) for scenario in Scenario for seed in BENCHMARK_SEEDS
)


def run_smoke_suite(adapters: Iterable[DecisionAdapter]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for scenario, seed in SMOKE_CASES:
        episode = run_episode(scenario, seed)
        rows.extend(run_episode_with_adapters(episode, adapters))
    return rows


def run_benchmark(
    adapters: Iterable[DecisionAdapter],
    *,
    runs: int = 1,
    cases: Iterable[tuple[Scenario, int]] = BENCHMARK_CASES,
) -> list[dict[str, object]]:
    """Repeat the full matrix without sharing truth or caching provider calls."""

    if runs < 1:
        raise ValueError("runs must be at least 1")
    scheduled_adapters = tuple(adapters)
    scheduled_cases = tuple(cases)
    rows: list[dict[str, object]] = []
    for run_number in range(1, runs + 1):
        for scenario, seed in scheduled_cases:
            episode = run_episode(scenario, seed)
            for row in run_episode_with_adapters(episode, scheduled_adapters):
                row["benchmark"] = {"run": run_number, "seed": seed}
                rows.append(row)
    return rows


def summarize_results(rows: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    """Return compact, provider-neutral measurements grouped by engine."""

    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        decision = row["audit"]["decision"]  # type: ignore[index]
        grouped.setdefault(str(decision["engine"]), []).append(row)  # type: ignore[index]

    summary: list[dict[str, object]] = []
    for engine, engine_rows in grouped.items():
        evaluated = [
            row
            for row in engine_rows
            if row["evaluation"]["action_acceptable"] is not None  # type: ignore[index]
            and row["evaluation"]["class_acceptable"] is not None  # type: ignore[index]
        ]
        statuses = [
            _enum_value(row["audit"]["decision"]["status"])  # type: ignore[index]
            for row in engine_rows
        ]
        latencies = [
            float(row["audit"]["decision"]["elapsed_ms"])  # type: ignore[index]
            for row, status in zip(engine_rows, statuses, strict=True)
            if status != "UNAVAILABLE"
        ]
        action_correct = _count_true(evaluated, "action_acceptable")
        class_correct = _count_true(evaluated, "class_acceptable")
        unsafe = _count_true(evaluated, "unsafe_recommendation")
        unnecessary = _count_true(evaluated, "unnecessary_escalation")
        evaluated_count = len(evaluated)
        summary.append(
            {
                "engine": engine,
                "total_attempts": len(engine_rows),
                "total_evaluated_decisions": evaluated_count,
                "action_accuracy": _rate(action_correct, evaluated_count),
                "incident_class_accuracy": _rate(class_correct, evaluated_count),
                "unsafe_recommendation_count": unsafe,
                "unsafe_recommendation_rate": _rate(unsafe, evaluated_count),
                "unnecessary_escalation_count": unnecessary,
                "unnecessary_escalation_rate": _rate(unnecessary, evaluated_count),
                "median_latency_ms": _rounded(median(latencies)) if latencies else None,
                "p95_latency_ms": _rounded(_percentile(latencies, 0.95)) if latencies else None,
                "provider_failure_count": sum(
                    status not in {"OK", "TIMEOUT", "UNAVAILABLE"} for status in statuses
                ),
                "provider_timeout_count": statuses.count("TIMEOUT"),
                "provider_unavailable_count": statuses.count("UNAVAILABLE"),
            }
        )
    return summary


def write_jsonl(rows: Iterable[dict[str, object]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_json(value: object, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _count_true(rows: Iterable[dict[str, object]], field: str) -> int:
    return sum(row["evaluation"][field] is True for row in rows)  # type: ignore[index]


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _rounded(value: float) -> float:
    return round(value, 3)


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))
