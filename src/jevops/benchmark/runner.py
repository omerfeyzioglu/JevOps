"""Run common evidence through adapters and preserve an auditable result."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json
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


def run_smoke_suite(adapters: Iterable[DecisionAdapter]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for scenario, seed in SMOKE_CASES:
        episode = run_episode(scenario, seed)
        rows.extend(run_episode_with_adapters(episode, adapters))
    return rows


def write_jsonl(rows: Iterable[dict[str, object]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
