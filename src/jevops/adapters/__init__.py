"""Decision adapters with a common, evidence-only interface."""

from .base import DecisionAdapter
from .gemini import GeminiAdapter
from .jev import JevAdapter
from .laya import LayaAdapter
from .openai_llm import OpenAIAdapter
from .rules import RulesAdapter


def default_adapters() -> list[DecisionAdapter]:
    """Return the five decision engines used by every product flow."""

    return [RulesAdapter(), JevAdapter(), LayaAdapter(), OpenAIAdapter(), GeminiAdapter()]


__all__ = [
    "DecisionAdapter",
    "GeminiAdapter",
    "JevAdapter",
    "LayaAdapter",
    "OpenAIAdapter",
    "RulesAdapter",
    "default_adapters",
]
