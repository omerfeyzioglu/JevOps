"""Explicit test-only adapters; never include them in a provider comparison."""

from __future__ import annotations

from jevops.adapters.base import DecisionAdapter
from jevops.contracts import Action, DecisionResult, EvidenceSnapshot, IncidentClass, ProviderStatus


class TimeoutFixtureAdapter(DecisionAdapter):
    name = "fixture_timeout"
    version = "test-only"

    def decide(self, evidence: EvidenceSnapshot) -> DecisionResult:
        return DecisionResult(
            engine=self.name,
            engine_version=self.version,
            status=ProviderStatus.TIMEOUT,
            provider_model="fixture",
            error="simulated provider deadline exceeded",
        )


class UnsafeReplayFixtureAdapter(DecisionAdapter):
    name = "fixture_unsafe_replay"
    version = "test-only"

    def decide(self, evidence: EvidenceSnapshot) -> DecisionResult:
        return DecisionResult(
            engine=self.name,
            engine_version=self.version,
            status=ProviderStatus.OK,
            incident_class=IncidentClass.UNKNOWN,
            recommended_action=Action.REPLAY,
            provider_model="fixture",
        )
