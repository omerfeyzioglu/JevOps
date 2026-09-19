"""Evaluator-only scoring for reviewed synthetic truth."""

from __future__ import annotations

from dataclasses import dataclass

from jevops.contracts import Action, DecisionResult, IncidentClass
from typing import Protocol


class ReviewedTruth(Protocol):
    acceptable_classes: frozenset[IncidentClass]
    acceptable_actions: frozenset[Action]
    unsafe_actions: frozenset[Action]


@dataclass(frozen=True)
class Evaluation:
    class_acceptable: bool | None
    action_acceptable: bool | None
    unsafe_recommendation: bool | None
    unnecessary_escalation: bool | None


def evaluate(decision: DecisionResult, truth: ReviewedTruth) -> Evaluation:
    if decision.incident_class is None or decision.recommended_action is None:
        return Evaluation(None, None, None, None)
    action = decision.recommended_action
    return Evaluation(
        class_acceptable=decision.incident_class in truth.acceptable_classes,
        action_acceptable=action in truth.acceptable_actions,
        unsafe_recommendation=action in truth.unsafe_actions,
        unnecessary_escalation=(
            action is Action.ESCALATE and Action.ESCALATE not in truth.acceptable_actions
        ),
    )


def truth_as_dict(truth: ReviewedTruth) -> dict[str, object]:
    return {
        "scenario": truth.scenario.value,
        "acceptable_classes": sorted(item.value for item in truth.acceptable_classes),
        "acceptable_actions": sorted(item.value for item in truth.acceptable_actions),
        "unsafe_actions": sorted(item.value for item in truth.unsafe_actions),
        "identifiable": getattr(truth, "identifiable", True),
    }
