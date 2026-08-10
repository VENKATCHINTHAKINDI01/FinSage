"""Async LLM access — DEM-005.

Two defects fixed here.

**Blocking the event loop.** Six modules held a module-level `Groq(...)` and
called `client.chat.completions.create(...)` — the SYNCHRONOUS client — from
inside `async def`. That blocks the entire event loop for the full duration of
the call. With agents chained sequentially and two or more LLM calls each, a
handful of concurrent users serialise into a queue behind one another. The
symptom looks like a slow model; the cause is a busy thread.

**Import-time construction.** `client = Groq(api_key=settings.llm.api_key)` at
module scope means importing the module reads config, which makes the module
unmockable in tests and crashes on a missing key even for code paths that never
call a model. Every test in `backend/tests` inherited that coupling.

The client is now built lazily, once, and is injectable. Nothing is constructed
at import.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    """No usable model. Raised rather than returning a plausible-looking
    default, because a fabricated answer is the failure mode this whole
    project exists to prevent."""


@dataclass(slots=True)
class LLMResponse:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    truncated: bool = False

    def json(self) -> Any:
        """Parse as JSON, tolerating the fenced-code wrapper models add."""
        raw = self.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.lstrip().lower().startswith("json"):
                raw = raw.lstrip()[4:]
        return json.loads(raw.strip())


class LLM(Protocol):
    """What agents depend on. Deliberately narrow so a fake is trivial."""

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> LLMResponse: ...


class GroqLLM:
    """AsyncGroq wrapper with a timeout and bounded retries."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        if not api_key:
            raise LLMUnavailable("no Groq API key configured")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries
        self._client: Any | None = None

    def _ensure(self) -> Any:
        if self._client is None:
            from groq import AsyncGroq

            self._client = AsyncGroq(api_key=self._api_key, timeout=self._timeout)
        return self._client

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> LLMResponse:
        client = self._ensure()
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            # Defaults to 0. Tax explanation is not a creative writing task,
            # and reproducibility matters more than variety.
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        last: Exception | None = None
        for attempt in range(self._max_retries + 1):
            started = time.perf_counter()
            try:
                resp = await client.chat.completions.create(**kwargs)
            except Exception as exc:
                last = exc
                if attempt < self._max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise LLMUnavailable(f"model call failed: {exc}") from exc

            choice = resp.choices[0]
            usage = getattr(resp, "usage", None)
            return LLMResponse(
                text=choice.message.content or "",
                model=self._model,
                prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                latency_ms=(time.perf_counter() - started) * 1000,
                truncated=getattr(choice, "finish_reason", None) == "length",
            )

        raise LLMUnavailable(f"model call failed: {last}")


@dataclass(slots=True)
class FakeLLM:
    """Deterministic stand-in for tests and fixture replay.

    Its existence is the point of the Protocol: agents can be tested without a
    key, a network, or a bill.
    """

    responses: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    model: str = "fake"

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> LLMResponse:
        self.calls.append(prompt)
        if not self.responses:
            raise LLMUnavailable("FakeLLM has no scripted responses left")
        return LLMResponse(text=self.responses.pop(0), model=self.model)


# ── provider ────────────────────────────────────────────────────────────────
# One instance per process, built on first use. Not at import time.

_instance: LLM | None = None


def get_llm() -> LLM:
    global _instance
    if _instance is None:
        from backend.config import settings

        _instance = GroqLLM(
            api_key=settings.llm.api_key,
            model=settings.llm.model,
            timeout=float(settings.llm.timeout),
        )
    return _instance


def set_llm(llm: LLM | None) -> None:
    """Override the provider — used by tests and the eval harness."""
    global _instance
    _instance = llm


def is_configured() -> bool:
    """Whether a model is usable, without constructing one or raising."""
    try:
        from backend.config import settings

        return bool(settings.llm.api_key)
    except Exception:
        return False
