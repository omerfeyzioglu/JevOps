"""Jev Choice integration. Imported only when a configured request is made."""

from __future__ import annotations

import os
from time import perf_counter
from typing import Any

from jevops.adapters.base import DecisionAdapter
from jevops.adapters.rubric import RUBRIC_VERSION, rubric_for
from jevops.contracts import Action, DecisionResult, EvidenceSnapshot, IncidentClass, ProviderStatus


class JevAdapter(DecisionAdapter):
    name = "jev"
    version = "jev-adapter-v1"

    def __init__(self, model: str = "jev-1.13.0", timeout_seconds: float = 15.0) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds

    def decide(self, evidence: EvidenceSnapshot) -> DecisionResult:
        api_key = os.environ.get("TYPESAFE_API_KEY")
        if not api_key:
            return DecisionResult(
                engine=self.name,
                engine_version=self.version,
                status=ProviderStatus.UNAVAILABLE,
                error="TYPESAFE_API_KEY is not configured",
            )
        started = perf_counter()
        try:
            incident_criteria, action_criteria, incident_question, action_question = rubric_for(
                evidence.domain
            )
            # The official SDK exposes typed Choice questions. Keep this import
            # lazy so offline simulations have no API dependency or side effect.
            from typesafe_sdk import Choice, RetryPolicy, TypeSafeClient

            with TypeSafeClient(
                api_key=api_key,
                model=self.model,
                timeout=self.timeout_seconds,
                retry=RetryPolicy(max_retries=0, timeout=self.timeout_seconds),
            ) as client:
                response = client.system_one(
                    state=evidence.model_state(),
                    questions={
                        "incident_class": Choice(
                            instructions=incident_question, criteria=incident_criteria
                        ),
                        "action": Choice(instructions=action_question, criteria=action_criteria),
                    },
                )
            answers: dict[str, Any] = response.answers
            incident = answers["incident_class"]
            action = answers["action"]
            return DecisionResult(
                engine=self.name,
                engine_version=self.version,
                status=ProviderStatus.OK,
                incident_class=IncidentClass(incident.choice),
                recommended_action=Action(action.choice),
                provider_model=getattr(response, "model", self.model),
                elapsed_ms=(perf_counter() - started) * 1_000,
                metadata={
                    "rubric_version": RUBRIC_VERSION,
                    "incident_confidence": incident.confidence,
                    "incident_probabilities": dict(incident.probabilities),
                    "action_confidence": action.confidence,
                    "action_probabilities": dict(action.probabilities),
                    "usage": _usage(response),
                },
            )
        except TimeoutError as exc:
            return self._error(ProviderStatus.TIMEOUT, started, str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            return self._error(ProviderStatus.INVALID_OUTPUT, started, str(exc))
        except Exception as exc:  # Provider exception classes are SDK-version specific.
            return self._error(ProviderStatus.SERVICE_ERROR, started, str(exc))

    def _error(self, status: ProviderStatus, started: float, message: str) -> DecisionResult:
        return DecisionResult(
            engine=self.name,
            engine_version=self.version,
            status=status,
            provider_model=self.model,
            elapsed_ms=(perf_counter() - started) * 1_000,
            error=message,
        )


def _usage(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    return {
        name: getattr(usage, name)
        for name in ("input_tokens", "output_tokens", "cost")
        if getattr(usage, name, None) is not None
    }
