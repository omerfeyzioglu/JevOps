"""Shared precondition checks for simulated StreamGuard actions."""

from __future__ import annotations

from jevops.contracts import Action, DecisionResult, EvidenceSnapshot, GateResult, ProviderStatus


def validate_action(evidence: EvidenceSnapshot, decision: DecisionResult) -> GateResult:
    """Return the action allowed by observable facts, never hidden scenario truth."""

    raw = decision.recommended_action
    if decision.status is not ProviderStatus.OK or raw is None:
        return GateResult(raw, None, None, "provider did not return a valid decision")

    facts = evidence.facts
    if raw is Action.ESCALATE:
        return GateResult(raw, raw, raw, None)
    if raw is Action.WAIT:
        if facts["wait_budget_remaining"] > 0 and not facts["deadline_exceeded"]:
            return GateResult(raw, raw, raw, None)
        return GateResult(raw, Action.ESCALATE, Action.ESCALATE, "wait budget exhausted")
    if raw is Action.RETRY:
        if facts["retry_budget_remaining"] > 0 and facts["checkpoint_known"]:
            return GateResult(raw, raw, raw, None)
        return GateResult(raw, Action.ESCALATE, Action.ESCALATE, "retry preconditions not met")
    if raw is Action.PAUSE:
        if facts["capacity_headroom_events_per_second"] >= 0:
            return GateResult(raw, raw, raw, None)
        return GateResult(raw, Action.ESCALATE, Action.ESCALATE, "pause would exceed storage policy")
    if raw is Action.REPLAY:
        required = ("source_retained", "checkpoint_known", "sink_healthy")
        if all(bool(facts[name]) for name in required):
            return GateResult(raw, raw, raw, None)
        return GateResult(
            raw,
            Action.ESCALATE,
            Action.ESCALATE,
            "replay requires retained source, known checkpoint, and healthy sink",
        )
    return GateResult(raw, Action.ESCALATE, Action.ESCALATE, "unsupported action")
