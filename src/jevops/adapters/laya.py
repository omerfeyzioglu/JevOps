"""Local Laya typed-decision adapter with process-wide model reuse."""

from __future__ import annotations

import os
from threading import Lock
from time import perf_counter
from typing import Any, ClassVar, Mapping

from jevops.adapters.base import DecisionAdapter
from jevops.adapters.rubric import RUBRIC_VERSION, rubric_for
from jevops.contracts import Action, DecisionResult, EvidenceSnapshot, IncidentClass, ProviderStatus


class LayaAdapter(DecisionAdapter):
    """Run Laya locally; checkpoint loading is excluded from inference latency."""

    name = "laya"
    version = "laya-local-typed-decisions-v1"
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
            "LAYA_SUBFOLDER", "typed-decisions"
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

        try:
            agent = self._get_model()
        except Exception as exc:
            return self._error(ProviderStatus.SERVICE_ERROR, 0.0, exc)

        started = perf_counter()
        try:
            incident_criteria, action_criteria, incident_question, action_question = rubric_for(
                evidence.domain
            )
            result = agent.predict(
                evidence.model_state(),
                {
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
                },
            )
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

        return laya.load(model, subfolder=subfolder, device=device)

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
