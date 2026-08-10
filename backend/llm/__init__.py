"""Async LLM access, lazily constructed and injectable.

Nothing here is built at import time. Agents depend on the `LLM` protocol, not
on Groq, so they can be tested without a key, a network or a bill.
"""

from backend.llm.client import (
    LLM,
    FakeLLM,
    GroqLLM,
    LLMResponse,
    LLMUnavailable,
    get_llm,
    is_configured,
    set_llm,
)

__all__ = [
    "LLM",
    "FakeLLM",
    "GroqLLM",
    "LLMResponse",
    "LLMUnavailable",
    "get_llm",
    "is_configured",
    "set_llm",
]
