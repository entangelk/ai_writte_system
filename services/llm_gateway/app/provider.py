"""Provider boundary and deterministic test double for LLM generation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Protocol, runtime_checkable

from .payload import ChatCompletionRequest


@dataclass(frozen=True, slots=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True, slots=True)
class GenerationResult:
    model: str
    content: str
    finish_reason: str
    usage: TokenUsage = field(default_factory=TokenUsage)


@runtime_checkable
class LLMProvider(Protocol):
    async def generate(
        self,
        request: ChatCompletionRequest,
    ) -> GenerationResult:
        """Generate one non-streaming completion."""

        ...


class FakeProviderExhausted(RuntimeError):
    """Raised when a test calls the fake more times than configured."""


ProviderOutcome = GenerationResult | Exception


class FakeLLMProvider:
    """Return queued results or errors in deterministic FIFO order."""

    def __init__(self, outcomes: Iterable[ProviderOutcome]) -> None:
        self._outcomes = deque(outcomes)
        self.requests: list[ChatCompletionRequest] = []

    async def generate(
        self,
        request: ChatCompletionRequest,
    ) -> GenerationResult:
        self.requests.append(request)
        if not self._outcomes:
            raise FakeProviderExhausted("fake provider has no queued outcome")

        outcome = self._outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
