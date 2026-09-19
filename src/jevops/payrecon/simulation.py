"""Synthetic lifecycle delivery faults with deterministic reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256

from jevops.contracts import Action, EvidenceSnapshot, IncidentClass


class PayReconScenario(str, Enum):
    NORMAL = "normal"
    DUPLICATE_DELIVERY = "duplicate_delivery"
    LATE_SETTLEMENT = "late_settlement"
    OUT_OF_ORDER = "out_of_order"
    MISSING_RETAINED = "missing_retained"
    PROJECTION_MISMATCH = "projection_mismatch"
    INTEGRITY_CONFLICT = "integrity_conflict"


@dataclass(frozen=True)
class PayReconTruth:
    scenario: PayReconScenario
    acceptable_classes: frozenset[IncidentClass]
    acceptable_actions: frozenset[Action]
    unsafe_actions: frozenset[Action]


@dataclass(frozen=True)
class PayReconEpisode:
    evidence: EvidenceSnapshot
    truth: PayReconTruth
    reconciled_by_end: bool


def _truth(scenario: PayReconScenario) -> PayReconTruth:
    mapping = {
        PayReconScenario.NORMAL: (IncidentClass.HEALTHY_OR_RECOVERING, Action.WAIT, frozenset()),
        PayReconScenario.DUPLICATE_DELIVERY: (IncidentClass.BENIGN_DUPLICATE, Action.WAIT, frozenset()),
        PayReconScenario.LATE_SETTLEMENT: (IncidentClass.EXPECTED_DELAY, Action.WAIT, frozenset({Action.REPLAY})),
        PayReconScenario.OUT_OF_ORDER: (IncidentClass.OUT_OF_ORDER, Action.WAIT, frozenset({Action.RECONCILE})),
        PayReconScenario.MISSING_RETAINED: (IncidentClass.DELIVERY_GAP, Action.REPLAY, frozenset({Action.WAIT})),
        PayReconScenario.PROJECTION_MISMATCH: (IncidentClass.PROJECTION_MISMATCH, Action.RECONCILE, frozenset({Action.REPLAY})),
        PayReconScenario.INTEGRITY_CONFLICT: (IncidentClass.INTEGRITY_CONFLICT, Action.ESCALATE, frozenset({Action.REPLAY, Action.RECONCILE})),
    }
    incident_class, action, unsafe = mapping[scenario]
    return PayReconTruth(scenario, frozenset({incident_class}), frozenset({action}), unsafe)


def run_episode(scenario: PayReconScenario, seed: int) -> PayReconEpisode:
    """Build a state-machine exception at a fixed observation point.

    Processor source facts and local projection are separate observations. The
    synthetic scenario name is evaluator-only and never reaches evidence.
    """

    source = ["AUTHORIZED", "CAPTURED", "SETTLED"]
    delivered = ["AUTHORIZED", "CAPTURED", "SETTLED"]
    projection = "SETTLED"
    duplicate_count = 0
    pending_prerequisites = 0
    known_retained_missing = False
    projection_mismatch = False
    integrity_conflict = False
    processor_pending = False
    grace_exceeded = False
    observations = ["processor snapshot observed", "local projection observed"]

    if scenario is PayReconScenario.DUPLICATE_DELIVERY:
        delivered.insert(2, "CAPTURED")
        duplicate_count = 1
        observations.append("identical processor event delivered twice")
    elif scenario is PayReconScenario.LATE_SETTLEMENT:
        source = ["AUTHORIZED", "CAPTURED"]
        projection = "CAPTURED"
        processor_pending = True
        observations.append("processor reports settlement pending")
    elif scenario is PayReconScenario.OUT_OF_ORDER:
        delivered = ["AUTHORIZED", "SETTLED"]
        projection = "AUTHORIZED"
        pending_prerequisites = 1
        observations.append("settlement received before capture")
    elif scenario is PayReconScenario.MISSING_RETAINED:
        delivered = ["AUTHORIZED", "SETTLED"]
        projection = "AUTHORIZED"
        known_retained_missing = True
        grace_exceeded = True
        observations.append("retained capture event absent from local delivery")
    elif scenario is PayReconScenario.PROJECTION_MISMATCH:
        projection = "CAPTURED"
        projection_mismatch = True
        observations.append("all lifecycle events received but projection differs")
    elif scenario is PayReconScenario.INTEGRITY_CONFLICT:
        integrity_conflict = True
        observations.append("same processor event id observed with a conflicting amount")

    opaque = sha256(f"payrecon:{seed}:snapshot".encode()).hexdigest()[:12]
    facts = {
        "received_lifecycle_events": delivered,
        "processor_lifecycle_state": source[-1],
        "local_projection_state": projection,
        "pending_prerequisite_count": pending_prerequisites,
        "missing_transition_age_seconds": 35 if known_retained_missing else 0,
        "duplicate_count_window": duplicate_count,
        "integrity_conflict": integrity_conflict,
        "processor_snapshot_age_seconds": 1,
        "processor_pending": processor_pending,
        "known_retained_missing_event": known_retained_missing,
        "complete_verified_source": len(source) == 3,
        "projection_mismatch": projection_mismatch,
        "grace_exceeded": grace_exceeded,
        "source_retained": True,
        "local_projection_disposable": True,
        "deadline_exceeded": False,
    }
    evidence = EvidenceSnapshot(
        schema_version="payrecon-evidence-v1",
        domain="payrecon",
        incident_id=f"exception-{opaque}",
        evidence_version=1,
        observation_second=12,
        window_seconds=5,
        facts=facts,
        observations=tuple(observations),
        policy={
            "allowed_actions": [Action.WAIT.value, Action.REPLAY.value, Action.RECONCILE.value, Action.ESCALATE.value],
            "delivery_grace_seconds": 30,
            "replay_scope": "local projection only",
        },
    )
    reconciled = scenario in {PayReconScenario.NORMAL, PayReconScenario.DUPLICATE_DELIVERY}
    return PayReconEpisode(evidence, _truth(scenario), reconciled)
