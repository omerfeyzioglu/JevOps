"""Safe action gate for local payment-event reconciliation only."""

from __future__ import annotations

from jevops.contracts import Action, DecisionResult, EvidenceSnapshot, GateResult, ProviderStatus


def validate_action(evidence: EvidenceSnapshot, decision: DecisionResult) -> GateResult:
    raw = decision.recommended_action
    if decision.status is not ProviderStatus.OK or raw is None:
        return GateResult(raw, None, None, "provider did not return a valid decision")
    facts = evidence.facts
    if raw is Action.ESCALATE:
        return GateResult(raw, raw, raw, None)
    if raw is Action.WAIT:
        if not facts["deadline_exceeded"] and not facts["grace_exceeded"]:
            return GateResult(raw, raw, raw, None)
        return GateResult(raw, Action.ESCALATE, Action.ESCALATE, "wait is outside the delivery policy")
    if raw is Action.REPLAY:
        if facts["source_retained"] and facts["known_retained_missing_event"] and not facts["integrity_conflict"]:
            return GateResult(raw, raw, raw, None)
        return GateResult(raw, Action.ESCALATE, Action.ESCALATE, "replay requires a known retained, non-conflicting event")
    if raw is Action.RECONCILE:
        if (facts["complete_verified_source"] and facts["local_projection_disposable"]
                and facts["pending_prerequisite_count"] == 0
                and facts["projection_mismatch"] and not facts["integrity_conflict"]):
            return GateResult(raw, raw, raw, None)
        return GateResult(raw, Action.ESCALATE, Action.ESCALATE, "reconciliation requires a verified source, a projection mismatch, and no pending prerequisites or conflict")
    return GateResult(raw, Action.ESCALATE, Action.ESCALATE, "action is not permitted for reconciliation")
