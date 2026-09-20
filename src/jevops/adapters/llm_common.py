"""Shared evidence-only prompt and bounded schema for LLM comparators."""

from __future__ import annotations

import json
from typing import Any

from jevops.adapters.rubric import rubric_for
from jevops.contracts import EvidenceSnapshot, ProviderStatus


def prompt_and_schema(evidence: EvidenceSnapshot) -> tuple[str, dict[str, Any]]:
    incident_criteria, action_criteria, incident_question, action_question = rubric_for(
        evidence.domain
    )
    prompt = "\n".join(
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
    schema = {
        "type": "object",
        "properties": {
            "incident_class": {"type": "string", "enum": list(incident_criteria)},
            "recommended_action": {"type": "string", "enum": list(action_criteria)},
        },
        "required": ["incident_class", "recommended_action"],
        "additionalProperties": False,
    }
    return prompt, schema


def provider_error_status(error: Exception) -> ProviderStatus:
    name = type(error).__name__.lower()
    if "timeout" in name:
        return ProviderStatus.TIMEOUT
    if getattr(error, "status_code", None) == 429 or "ratelimit" in name:
        return ProviderStatus.RATE_LIMITED
    return ProviderStatus.SERVICE_ERROR
