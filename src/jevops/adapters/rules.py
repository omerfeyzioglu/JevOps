"""An explicit, reasonably capable deterministic triage baseline."""

from __future__ import annotations

from time import perf_counter

from jevops.adapters.base import DecisionAdapter
from jevops.adapters.rubric import RUBRIC_VERSION
from jevops.contracts import Action, DecisionResult, EvidenceSnapshot, IncidentClass, ProviderStatus


class RulesAdapter(DecisionAdapter):
    name = "rules"
    version = f"rules-{RUBRIC_VERSION}"

    def decide(self, evidence: EvidenceSnapshot) -> DecisionResult:
        started = perf_counter()
        if evidence.domain == "payrecon":
            return self._payrecon(evidence, started)
        if evidence.domain != "streamguard":
            return DecisionResult(
                engine=self.name,
                engine_version=self.version,
                status=ProviderStatus.INVALID_OUTPUT,
                error=f"unsupported evidence domain: {evidence.domain}",
            )
        facts = evidence.facts
        observations = " ".join(evidence.observations).lower()
        error_count = int(facts["sink_error_count_window"])
        latency = int(facts["sink_latency_p95_ms"])
        arrival = int(facts["arrival_rate_events_per_second"])
        baseline = int(facts["baseline_arrival_rate_events_per_second"])

        if facts["schema_rejection_count_window"] > 0:
            incident_class, action, rule_id = (
                IncidentClass.SCHEMA_REJECT,
                Action.PAUSE,
                "schema-rejections",
            )
        elif facts["consumer_heartbeat_age_seconds"] > 10:
            incident_class, action, rule_id = (
                IncidentClass.CONSUMER_UNAVAILABLE,
                Action.RETRY,
                "stale-heartbeat",
            )
        elif facts["telemetry_missing_samples_window"] > 0 and error_count == 0:
            incident_class, action, rule_id = (
                IncidentClass.UNKNOWN,
                Action.ESCALATE,
                "missing-telemetry",
            )
        elif error_count > 0 or latency >= 200 or "sink write" in observations:
            action = Action.RETRY if facts["retry_budget_remaining"] > 0 else Action.PAUSE
            incident_class, rule_id = IncidentClass.SINK_DEGRADED, "sink-health"
        elif arrival >= baseline * 3 // 2 and facts["sink_healthy"]:
            incident_class, action, rule_id = (
                IncidentClass.LOAD_SURGE,
                Action.WAIT,
                "healthy-input-surge",
            )
        elif facts["queue_lag_records"] == 0:
            incident_class, action, rule_id = (
                IncidentClass.HEALTHY_OR_RECOVERING,
                Action.WAIT,
                "no-lag",
            )
        else:
            incident_class, action, rule_id = (
                IncidentClass.UNKNOWN,
                Action.ESCALATE,
                "unclassified-anomaly",
            )

        return DecisionResult(
            engine=self.name,
            engine_version=self.version,
            status=ProviderStatus.OK,
            incident_class=incident_class,
            recommended_action=action,
            elapsed_ms=(perf_counter() - started) * 1_000,
            metadata={"rule_id": rule_id, "rubric_version": RUBRIC_VERSION},
        )

    def _payrecon(self, evidence: EvidenceSnapshot, started: float) -> DecisionResult:
        facts = evidence.facts
        if facts["integrity_conflict"]:
            incident_class, action, rule_id = (
                IncidentClass.INTEGRITY_CONFLICT,
                Action.ESCALATE,
                "integrity-conflict",
            )
        elif facts["complete_verified_source"] and facts["projection_mismatch"]:
            incident_class, action, rule_id = (
                IncidentClass.PROJECTION_MISMATCH,
                Action.RECONCILE,
                "complete-source-projection-mismatch",
            )
        elif facts["known_retained_missing_event"] and facts["grace_exceeded"]:
            incident_class, action, rule_id = (
                IncidentClass.DELIVERY_GAP,
                Action.REPLAY,
                "retained-delivery-gap",
            )
        elif facts["pending_prerequisite_count"] and not facts["grace_exceeded"]:
            incident_class, action, rule_id = (
                IncidentClass.OUT_OF_ORDER,
                Action.WAIT,
                "pending-prerequisite-inside-grace",
            )
        elif facts["processor_pending"] and not facts["grace_exceeded"]:
            incident_class, action, rule_id = (
                IncidentClass.EXPECTED_DELAY,
                Action.WAIT,
                "processor-delay-inside-grace",
            )
        elif facts["duplicate_count_window"] > 0 and not facts["projection_mismatch"]:
            incident_class, action, rule_id = (
                IncidentClass.BENIGN_DUPLICATE,
                Action.WAIT,
                "idempotent-duplicate",
            )
        else:
            incident_class, action, rule_id = (
                IncidentClass.UNKNOWN,
                Action.ESCALATE,
                "unclassified-reconciliation-exception",
            )
        return DecisionResult(
            engine=self.name,
            engine_version=self.version,
            status=ProviderStatus.OK,
            incident_class=incident_class,
            recommended_action=action,
            elapsed_ms=(perf_counter() - started) * 1_000,
            metadata={"rule_id": rule_id, "rubric_version": RUBRIC_VERSION},
        )
