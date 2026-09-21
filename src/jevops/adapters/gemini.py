"""Gemini 2.5 Flash-Lite structured-output benchmark comparator."""

from __future__ import annotations

import json
import os
from time import perf_counter
from typing import Any

from jevops.adapters.base import DecisionAdapter
from jevops.adapters.llm_common import prompt_and_schema, provider_error_status
from jevops.adapters.rubric import RUBRIC_VERSION
from jevops.contracts import Action, DecisionResult, EvidenceSnapshot, IncidentClass, ProviderStatus


class GeminiAdapter(DecisionAdapter):
    name = "gemini-2.5-flash-lite"
    version = "google-genai-structured-v1"

    def __init__(
        self, model: str = "gemini-2.5-flash-lite", timeout_seconds: float = 15.0
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds

    def decide(self, evidence: EvidenceSnapshot) -> DecisionResult:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return DecisionResult(
                engine=self.name,
                engine_version=self.version,
                status=ProviderStatus.UNAVAILABLE,
                error="GEMINI_API_KEY is not configured",
                metadata={"latency_kind": "api_end_to_end"},
            )
        started = perf_counter()
        try:
            from google import genai

            prompt, schema = prompt_and_schema(evidence)
            with genai.Client(
                api_key=api_key,
                http_options={"timeout": int(self.timeout_seconds * 1_000)},
            ) as client:
                response = client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config={
                        "temperature": 0,
                        "response_mime_type": "application/json",
                        "response_json_schema": schema,
                    },
                )
            payload = json.loads(response.text)
            return DecisionResult(
                engine=self.name,
                engine_version=self.version,
                status=ProviderStatus.OK,
                incident_class=IncidentClass(payload["incident_class"]),
                recommended_action=Action(payload["recommended_action"]),
                provider_model=self.model,
                elapsed_ms=(perf_counter() - started) * 1_000,
                metadata={
                    "rubric_version": RUBRIC_VERSION,
                    "latency_kind": "api_end_to_end",
                    "usage": _usage(response.usage_metadata),
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
    names = {
        "input_tokens": "prompt_token_count",
        "output_tokens": "candidates_token_count",
        "total_tokens": "total_token_count",
        "thoughts_tokens": "thoughts_token_count",
        "cached_input_tokens": "cached_content_token_count",
    }
    return {
        output_name: int(value)
        for output_name, source_name in names.items()
        if (value := getattr(usage, source_name, None)) is not None
    }
