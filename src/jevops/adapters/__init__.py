"""Decision adapters with a common, evidence-only interface."""

from .base import DecisionAdapter
from .gemini import GeminiAdapter
from .jev import JevAdapter
from .openai_llm import OpenAIAdapter
from .rules import RulesAdapter


def default_adapters() -> list[DecisionAdapter]:
    """Return the four decision engines used by every product flow."""

    return [RulesAdapter(), JevAdapter(), OpenAIAdapter(), GeminiAdapter()]


__all__ = [
    "DecisionAdapter",
    "GeminiAdapter",
    "JevAdapter",
    "OpenAIAdapter",
    "RulesAdapter",
    "default_adapters",
]
