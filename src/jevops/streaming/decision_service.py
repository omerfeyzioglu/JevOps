"""Kafka evidence consumer, bounded decision runner, audit publisher, and metrics server."""

from __future__ import annotations

import json
import logging
import os
import signal
from typing import Any

from jevops.adapters import JevAdapter, LlmAdapter, RulesAdapter
from jevops.streaming.processor import (
    decide_and_audit,
    decisions_disagree,
    evidence_from_payload,
)

LOGGER = logging.getLogger("jevops.decision-service")


class LiveMetrics:
    def __init__(self) -> None:
        from prometheus_client import Counter, Gauge, Histogram

        self.events_per_second = Gauge(
            "jevops_events_per_second", "Current StreamGuard event rate", ["kind"]
        )
        self.queue_lag = Gauge(
            "jevops_queue_lag_records", "Current queue/backlog depth in records"
        )
        self.error_rate = Gauge(
            "jevops_sink_error_rate", "Sink error rate over the Flink evidence window"
        )
        self.sink_latency = Gauge(
            "jevops_sink_latency_milliseconds", "Sink p95 latency over the evidence window"
        )
        self.decisions = Counter(
            "jevops_decisions_total",
            "Bounded decision results",
            ["engine", "raw_action", "effective_action", "status"],
        )
        self.decision_latency = Histogram(
            "jevops_decision_latency_seconds",
            "Decision adapter latency",
            ["engine"],
            buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 2.5, 5, 10, 20),
        )
        self.confidence = Gauge(
            "jevops_decision_confidence", "Latest provider confidence when available", ["engine"]
        )
        self.disagreements = Counter(
            "jevops_decision_disagreements_total", "Evidence snapshots with conflicting actions"
        )
        self.comparable = Counter(
            "jevops_comparable_decision_sets_total", "Evidence snapshots with two or more decisions"
        )
        self.disagreement_rate = Gauge(
            "jevops_decision_disagreement_rate", "Running fraction of comparable decision sets that disagree"
        )
        self.rejections = Counter(
            "jevops_safety_gate_rejections_total", "Actions changed or rejected by the safety gate", ["engine"]
        )
        self.latest = Gauge(
            "jevops_latest_decision",
            "Latest decision by engine (the active label set has value one)",
            ["engine", "raw_action", "effective_action", "status", "incident_class"],
        )
        self.evidence_version = Gauge(
            "jevops_evidence_version", "Latest processed evidence version", ["incident_id"]
        )
        self._latest_labels: dict[str, tuple[str, str, str, str]] = {}
        self._comparables = 0
        self._disagreements = 0

    def observe_evidence(self, evidence: Any) -> None:
        facts = evidence.facts
        self.events_per_second.labels("arrival").set(
            float(facts.get("arrival_rate_events_per_second", 0))
        )
        self.events_per_second.labels("processing").set(
            float(facts.get("processing_rate_events_per_second", 0))
        )
        self.queue_lag.set(float(facts.get("queue_lag_records", 0)))
        self.error_rate.set(float(facts.get("sink_error_rate", 0)))
        self.sink_latency.set(float(facts.get("sink_latency_p95_ms", 0)))
        self.evidence_version.labels(evidence.incident_id).set(evidence.evidence_version)

    def observe_decisions(self, rows: list[dict[str, object]]) -> None:
        valid = 0
        for row in rows:
            audit = row["audit"]
            decision = audit["decision"]
            gate = audit["gate"]
            engine = str(decision["engine"])
            status = _enum_value(decision["status"])
            raw = _enum_value(gate["raw_action"], "NONE")
            effective = _enum_value(gate["effective_action"], "NONE")
            incident_class = _enum_value(decision["incident_class"], "NONE")
            if effective != "NONE":
                valid += 1
            self.decisions.labels(engine, raw, effective, status).inc()
            self.decision_latency.labels(engine).observe(float(decision["elapsed_ms"]) / 1_000)
            if row["confidence"] is not None:
                self.confidence.labels(engine).set(float(row["confidence"]))
            if raw != "NONE" and (gate["override_reason"] is not None or raw != effective):
                self.rejections.labels(engine).inc()

            prior = self._latest_labels.get(engine)
            if prior is not None:
                self.latest.labels(engine, *prior).set(0)
            current = (raw, effective, status, incident_class)
            self.latest.labels(engine, *current).set(1)
            self._latest_labels[engine] = current

        if valid >= 2:
            self._comparables += 1
            self.comparable.inc()
            if decisions_disagree(rows):
                self._disagreements += 1
                self.disagreements.inc()
            self.disagreement_rate.set(self._disagreements / self._comparables)


def _enum_value(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(getattr(value, "value", value))


def main() -> int:
    from confluent_kafka import Consumer, Producer
    from prometheus_client import start_http_server

    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    evidence_topic = os.environ.get("STREAMGUARD_EVIDENCE_TOPIC", "streamguard.evidence")
    decisions_topic = os.environ.get("STREAMGUARD_DECISIONS_TOPIC", "streamguard.decisions")
    metrics_port = int(os.environ.get("METRICS_PORT", "8000"))
    every = max(1, int(os.environ.get("DECISION_EVERY_N_SNAPSHOTS", "5")))

    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap,
            "group.id": os.environ.get("KAFKA_DECISION_GROUP", "streamguard-decisions-v1"),
            "auto.offset.reset": "latest",
            "enable.auto.commit": False,
        }
    )
    producer = Producer({"bootstrap.servers": bootstrap, "client.id": "streamguard-decisions"})
    metrics = LiveMetrics()
    adapters = [RulesAdapter(), JevAdapter(), LlmAdapter()]
    running = True

    def stop(*_: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    start_http_server(metrics_port)
    consumer.subscribe([evidence_topic])
    LOGGER.info("consuming %s; metrics on :%d", evidence_topic, metrics_port)

    try:
        while running:
            message = consumer.poll(1.0)
            if message is None:
                continue
            if message.error():
                LOGGER.warning("Kafka consumer error: %s", message.error())
                continue
            try:
                evidence = evidence_from_payload(json.loads(message.value()))
                metrics.observe_evidence(evidence)
                if evidence.evidence_version % every != 0:
                    consumer.commit(message=message, asynchronous=False)
                    continue
                rows = decide_and_audit(evidence, adapters)
                metrics.observe_decisions(rows)
                for row in rows:
                    encoded = json.dumps(row, default=_enum_value, separators=(",", ":")).encode()
                    producer.produce(decisions_topic, key=evidence.incident_id.encode(), value=encoded)
                    LOGGER.info("audit=%s", encoded.decode())
                producer.flush(10)
                consumer.commit(message=message, asynchronous=False)
            except Exception:
                LOGGER.exception("failed to process evidence; offset left uncommitted")
    finally:
        producer.flush(10)
        consumer.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
