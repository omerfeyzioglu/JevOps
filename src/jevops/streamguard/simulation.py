"""A small, causal StreamGuard simulation used before adding a broker."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import random

from jevops.contracts import Action, EvidenceSnapshot, IncidentClass


class Scenario(str, Enum):
    NORMAL = "normal"
    SINK_SLOWDOWN_RECOVERABLE = "sink_slowdown_recoverable"
    SINK_FAILURE_PERSISTENT = "sink_failure_persistent"
    TRAFFIC_SPIKE = "traffic_spike"
    AMBIGUOUS_EARLY = "ambiguous_early"


@dataclass(frozen=True)
class ScenarioTruth:
    """Evaluator-only data. It must never be passed into an adapter."""

    scenario: Scenario
    acceptable_classes: frozenset[IncidentClass]
    acceptable_actions: frozenset[Action]
    unsafe_actions: frozenset[Action]
    identifiable: bool


@dataclass(frozen=True)
class Tick:
    second: int
    arrival_rate: int
    processed: int
    lag: int
    sink_latency_p95_ms: int
    sink_errors: int
    consecutive_breaches: int
    detector_open: bool
    observations: tuple[str, ...]


@dataclass(frozen=True)
class Episode:
    evidence: EvidenceSnapshot
    truth: ScenarioTruth
    timeline: tuple[Tick, ...]
    detector_opened_at: int | None
    recovered_by_end: bool


class LocalSink:
    """A deterministic, idempotent sink with observable latency and errors."""

    def __init__(self) -> None:
        self._committed: set[str] = set()

    @property
    def committed_count(self) -> int:
        return len(self._committed)

    def write(
        self, records: deque[str], capacity: int, *, fail_writes: bool, latency_ms: int
    ) -> tuple[int, int, int]:
        attempts = min(len(records), capacity)
        if fail_writes:
            return 0, attempts, latency_ms

        processed = 0
        for _ in range(attempts):
            event_id = records.popleft()
            if event_id not in self._committed:
                self._committed.add(event_id)
            processed += 1
        return processed, 0, latency_ms


def _truth_for(scenario: Scenario) -> ScenarioTruth:
    if scenario is Scenario.NORMAL:
        return ScenarioTruth(
            scenario,
            frozenset({IncidentClass.HEALTHY_OR_RECOVERING}),
            frozenset({Action.WAIT}),
            frozenset(),
            True,
        )
    if scenario is Scenario.TRAFFIC_SPIKE:
        return ScenarioTruth(
            scenario,
            frozenset({IncidentClass.LOAD_SURGE}),
            frozenset({Action.WAIT}),
            frozenset({Action.REPLAY}),
            True,
        )
    if scenario is Scenario.AMBIGUOUS_EARLY:
        return ScenarioTruth(
            scenario,
            frozenset({IncidentClass.UNKNOWN}),
            frozenset({Action.ESCALATE}),
            frozenset({Action.REPLAY}),
            False,
        )
    return ScenarioTruth(
        scenario,
        frozenset({IncidentClass.SINK_DEGRADED}),
        frozenset({Action.RETRY, Action.PAUSE}),
        frozenset({Action.REPLAY}),
        True,
    )


def _fault_profile(
    scenario: Scenario, second: int, baseline_arrival: int
) -> tuple[int, int, bool, tuple[str, ...]]:
    """Return arrival rate, sink capacity, failure state, and observed messages.

    The caller uses this to generate metrics. The profile itself is not model-facing.
    """

    arrival = baseline_arrival
    capacity = 120
    fail_writes = False
    observations: tuple[str, ...] = ("consumer heartbeat observed",)

    active = second >= 15
    if scenario is Scenario.SINK_SLOWDOWN_RECOVERABLE and 15 <= second < 30:
        capacity = 25
        observations = ("consumer heartbeat observed", "sink write latency above baseline")
    elif scenario is Scenario.SINK_FAILURE_PERSISTENT and active:
        fail_writes = True
        observations = ("consumer heartbeat observed", "sink write timeout observed")
    elif scenario is Scenario.TRAFFIC_SPIKE and 15 <= second < 29:
        arrival = baseline_arrival * 3
        observations = ("consumer heartbeat observed", "input throughput above baseline")
    elif scenario is Scenario.AMBIGUOUS_EARLY and 15 <= second < 18:
        # The observation system is intentionally sparse during this very early cue.
        capacity = 25
        observations = ("consumer heartbeat observed", "one telemetry sample unavailable")
    return arrival, capacity, fail_writes, observations


def _window(timeline: list[Tick], width: int = 5) -> list[Tick]:
    return timeline[-width:]


def _snapshot(
    timeline: list[Tick], *, seed: int, baseline_arrival: int, evidence_version: int
) -> EvidenceSnapshot:
    window = _window(timeline)
    current = window[-1]
    latest_observations = tuple(
        item for tick in window[-2:] for item in tick.observations
    )[-4:]
    sink_healthy = current.sink_errors == 0 and current.sink_latency_p95_ms <= 100
    capacity_headroom = max(0, 120 - current.arrival_rate)
    opaque = sha256(f"streamguard:{seed}:snapshot".encode()).hexdigest()[:12]
    facts = {
        "arrival_rate_events_per_second": current.arrival_rate,
        "baseline_arrival_rate_events_per_second": baseline_arrival,
        "processing_rate_events_per_second": current.processed,
        "queue_lag_records": current.lag,
        "lag_change_over_window_records": current.lag - window[0].lag,
        "sink_latency_p95_ms": current.sink_latency_p95_ms,
        "sink_error_count_window": sum(tick.sink_errors for tick in window),
        "consumer_heartbeat_age_seconds": 0,
        "checkpoint_age_seconds": 0,
        "partition_lag_records": {"0": current.lag, "1": 0, "2": 0},
        "duplicate_count_window": 0,
        "schema_rejection_count_window": 0,
        "telemetry_missing_samples_window": sum(
            "telemetry sample unavailable" in item
            for tick in window
            for item in tick.observations
        ),
        "sink_healthy": sink_healthy,
        "capacity_headroom_events_per_second": capacity_headroom,
        "source_retained": True,
        "checkpoint_known": True,
        "wait_budget_remaining": 1,
        "retry_budget_remaining": 1,
        "deadline_exceeded": False,
    }
    return EvidenceSnapshot(
        schema_version="streamguard-evidence-v1",
        domain="streamguard",
        incident_id=f"incident-{opaque}",
        evidence_version=evidence_version,
        observation_second=current.second,
        window_seconds=len(window),
        facts=facts,
        observations=latest_observations,
        policy={
            "allowed_actions": [
                Action.WAIT.value,
                Action.RETRY.value,
                Action.PAUSE.value,
                Action.REPLAY.value,
                Action.ESCALATE.value,
            ],
            "replay_requires": ["source_retained", "checkpoint_known", "sink_healthy"],
            "wait_interval_seconds": 10,
        },
    )


def run_episode(scenario: Scenario, seed: int, duration_seconds: int = 85) -> Episode:
    """Run a seeded event trajectory and freeze one evidence snapshot.

    The result stores private truth alongside the public snapshot only for the
    evaluator. Callers must pass `episode.evidence`, never the episode itself,
    to an adapter.
    """

    if duration_seconds < 20:
        raise ValueError("duration_seconds must cover warmup and fault onset")

    random_source = random.Random(seed)
    # Keep capacity safely above normal load while still changing the trajectory
    # between seeds. The range is a documented synthetic assumption, not a tune.
    baseline_arrival = random_source.randint(70, 80)
    records: deque[str] = deque()
    sink = LocalSink()
    timeline: list[Tick] = []
    sequence = 0
    consecutive_breaches = 0
    detector_opened_at: int | None = None
    evidence: EvidenceSnapshot | None = None

    for second in range(duration_seconds):
        arrival, capacity, fail_writes, observations = _fault_profile(
            scenario, second, baseline_arrival
        )
        for _ in range(arrival):
            records.append(f"{seed}-{sequence}")
            sequence += 1
        latency_ms = 1_000 if fail_writes else (350 if capacity < 120 else 12)
        processed, errors, observed_latency = sink.write(
            records, capacity, fail_writes=fail_writes, latency_ms=latency_ms
        )
        lag = len(records)
        if lag >= 100:
            consecutive_breaches += 1
        else:
            consecutive_breaches = 0
        detector_open = consecutive_breaches >= 3
        tick = Tick(
            second=second,
            arrival_rate=arrival,
            processed=processed,
            lag=lag,
            sink_latency_p95_ms=observed_latency,
            sink_errors=errors,
            consecutive_breaches=consecutive_breaches,
            detector_open=detector_open,
            observations=observations,
        )
        timeline.append(tick)
        if detector_open and detector_opened_at is None:
            detector_opened_at = second
            evidence = _snapshot(
                timeline, seed=seed, baseline_arrival=baseline_arrival, evidence_version=1
            )
        # This is a forced, predeclared early snapshot. It represents a triage
        # question before detection can reasonably identify a cause.
        if scenario is Scenario.AMBIGUOUS_EARLY and second == 16:
            evidence = _snapshot(
                timeline, seed=seed, baseline_arrival=baseline_arrival, evidence_version=1
            )

    if evidence is None:
        evidence = _snapshot(
            timeline, seed=seed, baseline_arrival=baseline_arrival, evidence_version=1
        )
    recovered_by_end = timeline[-1].lag == 0 and timeline[-1].sink_errors == 0
    return Episode(
        evidence=evidence,
        truth=_truth_for(scenario),
        timeline=tuple(timeline),
        detector_opened_at=detector_opened_at,
        recovered_by_end=recovered_by_end,
    )
