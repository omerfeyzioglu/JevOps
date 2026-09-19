"""One structured-output general-purpose LLM comparator."""

from __future__ import annotations

import json
import os
from time import perf_counter
from typing import Any

from jevops.adapters.base import DecisionAdapter
from jevops.adapters.rubric import RUBRIC_VERSION, rubric_for
from jevops.contracts import Action, DecisionResult, EvidenceSnapshot, IncidentClass, ProviderStatus


class LlmAdapter(DecisionAdapter):
    name = "llm"
    version = "anthropic-structured-adapter-v1"

    def __init__(
        self, model: str = "claude-haiku-4-5-20251001", timeout_seconds: float = 15.0
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds

    def decide(self, evidence: EvidenceSnapshot) -> DecisionResult:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return DecisionResult(
                engine=self.name,
                engine_version=self.version,
                status=ProviderStatus.UNAVAILABLE,
                error="ANTHROPIC_API_KEY is not configured",
            )
        started = perf_counter()
        try:
            import anthropic

            incident_criteria, action_criteria, incident_question, action_question = rubric_for(
                evidence.domain
            )

            client = anthropic.Anthropic(
                api_key=api_key, timeout=self.timeout_seconds, max_retries=0
            )
            response = client.messages.create(
                model=self.model,
                max_tokens=256,
                temperature=0,
                messages=[
                    {
                        "role": "user",
                        "content": _prompt(
                            evidence, incident_criteria, action_criteria, incident_question, action_question
                        ),
                    }
                ],
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": _schema(incident_criteria, action_criteria),
                    }
                },
            )
            payload = json.loads(next(block.text for block in response.content if block.type == "text"))
            return DecisionResult(
                engine=self.name,
                engine_version=self.version,
                status=ProviderStatus.OK,
                incident_class=IncidentClass(payload["incident_class"]),
                recommended_action=Action(payload["recommended_action"]),
                provider_model=response.model,
                elapsed_ms=(perf_counter() - started) * 1_000,
                metadata={
                    "rubric_version": RUBRIC_VERSION,
                    "usage": {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                    },
                },
            )
        except TimeoutError as exc:
            return self._error(ProviderStatus.TIMEOUT, started, str(exc))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return self._error(ProviderStatus.INVALID_OUTPUT, started, str(exc))
        except Exception as exc:  # SDK exception classes vary by release.
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


def _prompt(
    evidence: EvidenceSnapshot,
    incident_criteria: dict[str, str],
    action_criteria: dict[str, str],
    incident_question: str,
    action_question: str,
) -> str:
    return "\n".join(
        [
            f"Make two bounded {evidence.domain} triage decisions using only this evidence.",
            incident_question,
            f"Incident classes: {json.dumps(incident_criteria, sort_keys=True)}",
            action_question,
            f"Actions: {json.dumps(action_criteria, sort_keys=True)}",
            "Evidence:",
            json.dumps(evidence.model_state(), sort_keys=True),
        ]
    )


def _schema(incident_criteria: dict[str, str], action_criteria: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "incident_class": {"type": "string", "enum": list(incident_criteria)},
            "recommended_action": {"type": "string", "enum": list(action_criteria)},
        },
        "required": ["incident_class", "recommended_action"],
        "additionalProperties": False,
    }
