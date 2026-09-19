"""Seeded operational event profiles for the Kafka demo."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import random
from typing import Iterator

from jevops.streamguard.simulation import Scenario


@dataclass(frozen=True)
class OperationalEvent:
    schema_version: str
    run_id: str
    sequence: int
    timestamp: str
    baseline_events_per_second: int
    records_received: int
    records_processed: int
    queue_depth: int
    sink_latency_ms: int
    sink_errors: int
    source_available: bool
    checkpoint_available: bool
    checkpoint_age_seconds: int
    consumer_heartbeat_age_seconds: int
    telemetry_available: bool
    source_retained: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def generate_events(
    scenario: Scenario,
    seed: int,
    duration_seconds: int,
    run_id: str,
) -> Iterator[OperationalEvent]:
    """Yield a causal stream; scenario identity is never included in an event."""

    random_source = random.Random(seed)
    baseline = random_source.randint(70, 80)
    queue_depth = 0

    for second in range(duration_seconds):
        received, capacity, failing, latency, telemetry = _profile(
            scenario, second, baseline
        )
        attempted = min(queue_depth + received, capacity)
        sink_errors = attempted if failing else 0
        processed = 0 if failing else attempted
        queue_depth = max(0, queue_depth + received - processed)
        yield OperationalEvent(
            schema_version="streamguard-event-v1",
            run_id=run_id,
            sequence=second,
            timestamp=datetime.now(timezone.utc).isoformat(),
            baseline_events_per_second=baseline,
            records_received=received,
            records_processed=processed,
            queue_depth=queue_depth,
            sink_latency_ms=latency,
            sink_errors=sink_errors,
            source_available=True,
            checkpoint_available=True,
            checkpoint_age_seconds=0,
            consumer_heartbeat_age_seconds=0,
            telemetry_available=telemetry,
            source_retained=True,
        )


def _profile(
    scenario: Scenario, second: int, baseline: int
) -> tuple[int, int, bool, int, bool]:
    received, capacity, failing, latency, telemetry = baseline, 120, False, 12, True

    if scenario is Scenario.SINK_SLOWDOWN_RECOVERABLE and 15 <= second < 35:
        capacity, latency = 25, 380
    elif scenario is Scenario.SINK_FAILURE_PERSISTENT and second >= 15:
        failing, latency = True, 1_000
    elif scenario is Scenario.TRAFFIC_SPIKE and 15 <= second < 35:
        received = baseline * 3
    elif scenario is Scenario.AMBIGUOUS_EARLY and 15 <= second < 22:
        capacity, latency, telemetry = 45, 240, second % 2 == 0
    elif scenario is Scenario.INTERMITTENT_FAILURE and 15 <= second < 48:
        failing = second % 5 in (0, 1)
        capacity, latency = (120, 900) if failing else (55, 260)
    elif scenario is Scenario.FALSE_RECOVERY and 15 <= second < 52:
        failing = second < 28 or second >= 35
        capacity, latency = (120, 1_000) if failing else (60, 45)
    elif scenario is Scenario.TRAFFIC_SPIKE_SINK_DEGRADATION and 15 <= second < 45:
        received, capacity, latency = baseline * 3, 40, 480

    return received, capacity, failing, latency, telemetry

