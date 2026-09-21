"""GPT-5.6 Luna structured-output benchmark comparator."""

from __future__ import annotations

import json
import os
from time import perf_counter
from typing import Any

from jevops.adapters.base import DecisionAdapter
from jevops.adapters.llm_common import prompt_and_schema, provider_error_status
from jevops.adapters.rubric import RUBRIC_VERSION
from jevops.contracts import Action, DecisionResult, EvidenceSnapshot, IncidentClass, ProviderStatus


class OpenAIAdapter(DecisionAdapter):
    name = "gpt-5.6-luna"
    version = "openai-responses-structured-v1"

    def __init__(self, model: str = "gpt-5.6-luna", timeout_seconds: float = 15.0) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds

    def decide(self, evidence: EvidenceSnapshot) -> DecisionResult:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return DecisionResult(
                engine=self.name,
                engine_version=self.version,
                status=ProviderStatus.UNAVAILABLE,
                error="OPENAI_API_KEY is not configured",
                metadata={"latency_kind": "api_end_to_end"},
            )
        started = perf_counter()
        try:
            from openai import OpenAI

            prompt, schema = prompt_and_schema(evidence)
            with OpenAI(api_key=api_key, timeout=self.timeout_seconds, max_retries=0) as client:
                response = client.responses.create(
                    model=self.model,
                    input=prompt,
                    reasoning={"effort": "none"},
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "bounded_triage_decision",
                            "schema": schema,
                            "strict": True,
                        }
                    },
                    store=False,
                )
            payload = json.loads(response.output_text)
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
                    "latency_kind": "api_end_to_end",
                    "usage": _usage(response.usage),
                },
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return self._error(ProviderStatus.INVALID_OUTPUT, started, exc)
        except Exception as exc:  # Provider exception types vary by SDK release.
            return self._error(provider_error_status(exc), started, exc)

    def _error(
        self, status: ProviderStatus, started: float, error: Exception
    ) -> DecisionResult:
        return DecisionResult(
            engine=self.name,
            engine_version=self.version,
            status=status,
            provider_model=self.model,
            elapsed_ms=(perf_counter() - started) * 1_000,
            error=str(error),
            metadata={"latency_kind": "api_end_to_end"},
        )


def _usage(usage: Any) -> dict[str, int]:
    if usage is None:
        return {}
    return {
        name: int(value)
        for name in ("input_tokens", "output_tokens", "total_tokens")
        if (value := getattr(usage, name, None)) is not None
    }
