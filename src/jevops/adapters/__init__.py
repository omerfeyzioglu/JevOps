"""Decision adapters with a common, evidence-only interface."""

import os

from .base import DecisionAdapter
from .gemini import GeminiAdapter
from .jev import JevAdapter
from .laya import LayaAdapter
from .openai_llm import OpenAIAdapter
from .rules import RulesAdapter


def default_adapters() -> list[DecisionAdapter]:
    """Return configured decision engines for every product flow."""

    adapters: list[DecisionAdapter] = [RulesAdapter(), JevAdapter(), LayaAdapter()]
    if os.environ.get("OPENAI_ENABLED", "true").lower() not in {"0", "false", "no", "off"}:
        adapters.append(OpenAIAdapter())
    adapters.append(GeminiAdapter())
    return adapters


__all__ = [
    "DecisionAdapter",
    "GeminiAdapter",
    "JevAdapter",
    "LayaAdapter",
    "OpenAIAdapter",
    "RulesAdapter",
    "default_adapters",
]
