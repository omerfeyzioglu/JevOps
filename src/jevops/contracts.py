"""Stable contracts shared by simulation, engines, and audit code."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Mapping


class IncidentClass(str, Enum):
    HEALTHY_OR_RECOVERING = "HEALTHY_OR_RECOVERING"
    SINK_DEGRADED = "SINK_DEGRADED"
    CONSUMER_UNAVAILABLE = "CONSUMER_UNAVAILABLE"
    LOAD_SURGE = "LOAD_SURGE"
    NETWORK_DEGRADED = "NETWORK_DEGRADED"
    SCHEMA_REJECT = "SCHEMA_REJECT"
    PARTITION_SKEW = "PARTITION_SKEW"
    DUPLICATE_BURST = "DUPLICATE_BURST"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"
    BENIGN_DUPLICATE = "BENIGN_DUPLICATE"
    EXPECTED_DELAY = "EXPECTED_DELAY"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    DELIVERY_GAP = "DELIVERY_GAP"
    PROJECTION_MISMATCH = "PROJECTION_MISMATCH"
    INTEGRITY_CONFLICT = "INTEGRITY_CONFLICT"


class Action(str, Enum):
    WAIT = "WAIT"
    RETRY = "RETRY"
    PAUSE = "PAUSE"
    REPLAY = "REPLAY"
    RECONCILE = "RECONCILE"
    ESCALATE = "ESCALATE"


class ProviderStatus(str, Enum):
    OK = "OK"
    UNAVAILABLE = "UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    REFUSAL = "REFUSAL"
    SERVICE_ERROR = "SERVICE_ERROR"


@dataclass(frozen=True)
class EvidenceSnapshot:
    """The only information a decision engine may receive.

    Simulator truth, seeds, scenario names, and future schedule are intentionally
    absent. `facts` contain values calculated once by deterministic code.
    """

    schema_version: str
    domain: str
    incident_id: str
    evidence_version: int
    observation_second: int
    window_seconds: int
    facts: Mapping[str, Any]
    observations: tuple[str, ...]
    policy: Mapping[str, Any]

    def model_state(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "domain": self.domain,
            "incident_id": self.incident_id,
            "evidence_version": self.evidence_version,
            "observation_second": self.observation_second,
            "window_seconds": self.window_seconds,
            "facts": dict(self.facts),
            "observations": list(self.observations),
            "policy": dict(self.policy),
        }

    @property
    def input_hash(self) -> str:
        encoded = json.dumps(
            self.model_state(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class DecisionResult:
    engine: str
    engine_version: str
    status: ProviderStatus
    incident_class: IncidentClass | None = None
    recommended_action: Action | None = None
    provider_model: str | None = None
    elapsed_ms: float = 0.0
    attempts: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class GateResult:
    raw_action: Action | None
    effective_action: Action | None
    applied_action: Action | None
    override_reason: str | None


@dataclass(frozen=True)
class AuditRecord:
    evidence_hash: str
    decision: DecisionResult
    gate: GateResult

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_hash": self.evidence_hash,
            "decision": asdict(self.decision),
            "gate": asdict(self.gate),
        }
