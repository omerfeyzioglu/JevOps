"""Decision and audit core shared by the live worker and unit tests."""

from __future__ import annotations

from typing import Iterable

from jevops.adapters.base import DecisionAdapter
from jevops.contracts import AuditRecord, EvidenceSnapshot
from jevops.streamguard.actions import validate_action


def evidence_from_payload(payload: dict[str, object]) -> EvidenceSnapshot:
    return EvidenceSnapshot(
        schema_version=str(payload["schema_version"]),
        domain=str(payload["domain"]),
        incident_id=str(payload["incident_id"]),
        evidence_version=int(payload["evidence_version"]),
        observation_second=int(payload["observation_second"]),
        window_seconds=int(payload["window_seconds"]),
        facts=dict(payload["facts"]),  # type: ignore[arg-type]
        observations=tuple(payload["observations"]),  # type: ignore[arg-type]
        policy=dict(payload["policy"]),  # type: ignore[arg-type]
    )


def decide_and_audit(
    evidence: EvidenceSnapshot, adapters: Iterable[DecisionAdapter]
) -> list[dict[str, object]]:
    """Give every adapter the exact same immutable snapshot, then gate it."""

    rows: list[dict[str, object]] = []
    for adapter in adapters:
        decision = adapter.decide(evidence)
        gate = validate_action(evidence, decision)
        audit = AuditRecord(evidence.input_hash, decision, gate)
        rows.append(
            {
                "domain": evidence.domain,
                "incident_id": evidence.incident_id,
                "evidence_version": evidence.evidence_version,
                "evidence_hash": evidence.input_hash,
                "audit": audit.as_dict(),
                "confidence": _confidence(decision.metadata),
            }
        )
    return rows


def decisions_disagree(rows: list[dict[str, object]]) -> bool:
    actions = {
        row["audit"]["gate"]["effective_action"]  # type: ignore[index]
        for row in rows
        if row["audit"]["gate"]["effective_action"] is not None  # type: ignore[index]
    }
    return len(actions) > 1


def _confidence(metadata: object) -> float | None:
    if not isinstance(metadata, dict):
        return None
    for name in ("action_confidence", "confidence", "incident_confidence"):
        value = metadata.get(name)
        if isinstance(value, (int, float)):
            return float(value)
    return None
