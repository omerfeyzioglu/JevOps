"""Centrally versioned labels and model-facing decision definitions."""

from __future__ import annotations

from jevops.contracts import Action, IncidentClass

RUBRIC_VERSION = "streamguard-v1"

INCIDENT_CRITERIA = {
    IncidentClass.HEALTHY_OR_RECOVERING.value: (
        "No active anomaly is supported, or backlog is draining while sink health is normal."
    ),
    IncidentClass.SINK_DEGRADED.value: (
        "Sink latency or write failures explain reduced processing and growing backlog."
    ),
    IncidentClass.CONSUMER_UNAVAILABLE.value: (
        "Consumer heartbeat is stale or worker availability is absent while input continues."
    ),
    IncidentClass.LOAD_SURGE.value: (
        "Input rate increased beyond normal while sink health and consumer heartbeat remain healthy."
    ),
    IncidentClass.NETWORK_DEGRADED.value: "Transport delay or timeout observations dominate.",
    IncidentClass.SCHEMA_REJECT.value: "Schema validation failures dominate observed processing failures.",
    IncidentClass.PARTITION_SKEW.value: "One partition has materially more lag than peers.",
    IncidentClass.DUPLICATE_BURST.value: "Duplicate delivery work dominates the anomaly.",
    IncidentClass.MIXED.value: "More than one active cause is supported and neither alone explains it.",
    IncidentClass.UNKNOWN.value: "Evidence is insufficient or conflicting; do not infer a hidden cause.",
}

ACTION_CRITERIA = {
    Action.WAIT.value: "Observe for one bounded interval while wait budget remains and no integrity risk is present.",
    Action.RETRY.value: "One idempotent, bounded retry of the available sink operation; never a blind replay.",
    Action.PAUSE.value: "Pause the affected consumer to prevent repeated harmful writes while storage headroom remains.",
    Action.REPLAY.value: "Replay a known retained range only after sink health, checkpoint, and idempotency are verified.",
    Action.ESCALATE.value: "Create a review ticket when no safe automated action is justified or evidence is insufficient.",
}

INCIDENT_QUESTION = (
    "Which StreamGuard incident interpretation is best supported by the current evidence only? "
    "Select UNKNOWN when the evidence cannot distinguish a cause, and MIXED only when multiple active causes are supported."
)
ACTION_QUESTION = (
    "Which next bounded StreamGuard triage action is justified by the current evidence and supplied policy? "
    "Do not assume missing prerequisites; use ESCALATE when no safe automated action is justified."
)

PAYRECON_INCIDENT_CRITERIA = {
    IncidentClass.HEALTHY_OR_RECOVERING.value: "The local projection agrees with complete processor evidence and no active exception is present.",
    "BENIGN_DUPLICATE": "A repeated event has identical content and deterministic deduplication has preserved state.",
    "EXPECTED_DELAY": "A required processor transition is pending inside its grace period with fresh source evidence.",
    "OUT_OF_ORDER": "A later lifecycle event arrived while a known prerequisite remains pending inside its grace period.",
    "DELIVERY_GAP": "A retained source event is known but has not reached the local projection after its grace period.",
    "PROJECTION_MISMATCH": "Complete verified source facts are present but the local disposable projection differs.",
    "INTEGRITY_CONFLICT": "Conflicting event identity, amount, currency, or lifecycle facts are observed.",
    "MIXED": "Several exception causes are supported and no single one explains the state.",
    "UNKNOWN": "Evidence is stale, absent, or insufficient for a safe exception interpretation.",
}

PAYRECON_ACTION_CRITERIA = {
    Action.WAIT.value: "Recheck inside the bounded grace period; do not extend a hard exception deadline.",
    Action.REPLAY.value: "Redeliver a known retained lifecycle event to the idempotent local projection only.",
    Action.RECONCILE.value: "Deterministically rebuild or compare the disposable local projection from verified complete source facts.",
    Action.ESCALATE.value: "Create a review ticket when source facts conflict, are incomplete, or automated repair is unsafe.",
}

PAYRECON_INCIDENT_QUESTION = (
    "Which PayRecon exception interpretation is best supported by current evidence only? "
    "Select UNKNOWN when freshness or evidence is insufficient."
)
PAYRECON_ACTION_QUESTION = (
    "Which next bounded PayRecon triage action is justified by current evidence and supplied policy? "
    "REPLAY only redelivers known retained events; it never reissues a payment."
)


def rubric_for(domain: str) -> tuple[dict[str, str], dict[str, str], str, str]:
    if domain == "streamguard":
        return INCIDENT_CRITERIA, ACTION_CRITERIA, INCIDENT_QUESTION, ACTION_QUESTION
    if domain == "payrecon":
        return (
            PAYRECON_INCIDENT_CRITERIA,
            PAYRECON_ACTION_CRITERIA,
            PAYRECON_INCIDENT_QUESTION,
            PAYRECON_ACTION_QUESTION,
        )
    raise ValueError(f"unsupported evidence domain: {domain}")
