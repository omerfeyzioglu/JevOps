"""Local Laya choice adapter with process-wide model reuse."""

from __future__ import annotations

import os
import json
from threading import Lock
from time import perf_counter
from typing import Any, ClassVar, Mapping

from jevops.adapters.base import DecisionAdapter
from jevops.adapters.rubric import RUBRIC_VERSION, rubric_for
from jevops.contracts import Action, DecisionResult, EvidenceSnapshot, IncidentClass, ProviderStatus


class LayaAdapter(DecisionAdapter):
    """Run Laya locally; checkpoint loading is excluded from inference latency."""

    name = "laya"
    version = "laya-complete-evidence-v3"
    _models: ClassVar[dict[tuple[str, str | None, str | None], Any]] = {}
    _model_lock: ClassVar[Lock] = Lock()

    def __init__(
        self,
        model: str | None = None,
        *,
        subfolder: str | None = None,
        device: str | None = None,
    ) -> None:
        self.model = model or os.environ.get("LAYA_MODEL", "convaiinnovations/laya")
        configured_subfolder = subfolder if subfolder is not None else os.environ.get(
            "LAYA_SUBFOLDER", ""
        )
        self.subfolder = configured_subfolder or None
        self.device = device if device is not None else os.environ.get("LAYA_DEVICE") or None

    @property
    def provider_model(self) -> str:
        return f"{self.model}/{self.subfolder}" if self.subfolder else self.model

    def decide(self, evidence: EvidenceSnapshot) -> DecisionResult:
        if not _enabled():
            return DecisionResult(
                engine=self.name,
                engine_version=self.version,
                status=ProviderStatus.UNAVAILABLE,
                provider_model=self.provider_model,
                error="LAYA_ENABLED is disabled",
                metadata={"latency_kind": "local_inference"},
            )

        loading_started = perf_counter()
        try:
            agent = self._get_model()
        except Exception as exc:
            return self._error(ProviderStatus.SERVICE_ERROR, 0.0, exc)

        loading_ms = (perf_counter() - loading_started) * 1_000
        started = perf_counter()
        try:
            incident_criteria, action_criteria, incident_question, action_question = rubric_for(
                evidence.domain
            )
            # Lossless serialization: preserve every evidence field and value.
            state = json.dumps(evidence.model_state(), ensure_ascii=False, separators=(",", ":"))
            questions = {
                "incident_class": {
                    "type": "choice",
                    "instructions": incident_question,
                    "criteria": incident_criteria,
                },
                "recommended_action": {
                    "type": "choice",
                    "instructions": action_question,
                    "criteria": action_criteria,
                },
            }
            request_metadata = _check_token_budget(agent, state, questions)
            result = agent.predict(state, questions)
            elapsed_ms = (perf_counter() - started) * 1_000
            answers = result["answers"]
            incident = answers["incident_class"]
            action = answers["recommended_action"]
            return DecisionResult(
                engine=self.name,
                engine_version=self.version,
                status=ProviderStatus.OK,
                incident_class=IncidentClass(incident["choice"]),
                recommended_action=Action(action["choice"]),
                provider_model=str(result.get("model") or self.provider_model),
                elapsed_ms=elapsed_ms,
                metadata={
                    "rubric_version": RUBRIC_VERSION,
                    "latency_kind": "local_inference",
                    "local_inference_ms": elapsed_ms,
                    "checkpoint": self.provider_model,
                    "model_device": str(agent.device),
                    "model_load_or_lookup_ms": loading_ms,
                    **request_metadata,
                    "incident_confidence": incident.get("confidence"),
                    "incident_probabilities": dict(incident.get("probabilities", {})),
                    "action_confidence": action.get("confidence"),
                    "action_probabilities": dict(action.get("probabilities", {})),
                    "usage": _mapping(result.get("usage")),
                },
            )
        except (KeyError, TypeError, ValueError) as exc:
            return self._error(ProviderStatus.INVALID_OUTPUT, (perf_counter() - started) * 1_000, exc)
        except Exception as exc:  # Laya backend errors vary by Torch/device installation.
            return self._error(ProviderStatus.SERVICE_ERROR, (perf_counter() - started) * 1_000, exc)

    def _get_model(self) -> Any:
        key = (self.model, self.subfolder, self.device)
        with self._model_lock:
            model = self._models.get(key)
            if model is None:
                model = self._load_model(self.model, self.subfolder, self.device)
                self._models[key] = model
            return model

    @staticmethod
    def _load_model(model: str, subfolder: str | None, device: str | None) -> Any:
        import laya

        agent = laya.load(model, subfolder=subfolder, device=device)
        # The root checkpoint's 512/192 defaults cut our facts, policy, and
        # option descriptions. ModernBERT supports this larger context.
        agent.cfg["max_len"] = 1024
        agent.cfg["head_max_len"] = 384
        return agent

    @classmethod
    def clear_model_cache(cls) -> None:
        """Release cached references; intended for tests and controlled shutdowns."""

        with cls._model_lock:
            cls._models.clear()

    def _error(self, status: ProviderStatus, elapsed_ms: float, error: Exception) -> DecisionResult:
        return DecisionResult(
            engine=self.name,
            engine_version=self.version,
            status=status,
            provider_model=self.provider_model,
            elapsed_ms=elapsed_ms,
            error=str(error),
            metadata={"latency_kind": "local_inference"},
        )


def _enabled() -> bool:
    return os.environ.get("LAYA_ENABLED", "true").lower() not in {"0", "false", "no", "off"}


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _check_token_budget(agent: Any, state: str, questions: Mapping[str, Any]) -> dict[str, Any]:
    """Reject requests that Laya 0.3.4 would silently truncate.

    Match its sequence layout: CLS, instructions, SEP, MASK/options,
    SEP, state, SEP. Never hide missing input behind an OK decision.
    """
    def token_count(text: str) -> int:
        return len(agent.tok(text, add_special_tokens=False)["input_ids"])

    state_tokens = token_count(state)
    max_len = int(agent.cfg["max_len"])
    head_max_len = int(agent.cfg["head_max_len"])
    lengths: dict[str, int] = {}
    for name, question in questions.items():
        if agent.tok.mask_token in state or agent.tok.mask_token in question["instructions"]:
            raise ValueError("Laya input contains a reserved mask token")
        instruction_tokens = token_count("choice question: " + question["instructions"])
        option_tokens = []
        for label, description in question["criteria"].items():
            text = f" {label}: {description}"
            if agent.tok.mask_token in text:
                raise ValueError("Laya option contains a reserved mask token")
            length = token_count(text)
            if length > 48:
                raise ValueError(f"Laya option would be truncated: {name}/{label}")
            option_tokens.append(length + 1)
        options = sum(option_tokens)
        if head_max_len - options < max(16, instruction_tokens):
            raise ValueError(f"Laya question head would be truncated: {name}")
        lengths[name] = instruction_tokens + options + state_tokens + 4
        if lengths[name] > max_len:
            raise ValueError(f"Laya evidence would be truncated: {name} needs {lengths[name]} tokens, limit {max_len}")
    return {
        "input_serialization": "lossless-compact-json-v1",
        "max_sequence_tokens": max_len,
        "head_max_tokens": head_max_len,
        "request_tokens_by_question": lengths,
        "input_truncated": False,
    }
