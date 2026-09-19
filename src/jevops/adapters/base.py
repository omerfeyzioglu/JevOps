from __future__ import annotations

from abc import ABC, abstractmethod

from jevops.contracts import DecisionResult, EvidenceSnapshot


class DecisionAdapter(ABC):
    """An engine sees an immutable snapshot and returns a bounded recommendation."""

    name: str
    version: str

    @abstractmethod
    def decide(self, evidence: EvidenceSnapshot) -> DecisionResult:
        raise NotImplementedError
