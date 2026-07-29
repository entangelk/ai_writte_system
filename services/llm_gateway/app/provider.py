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
    # 이 호출이 실제로 쓴 서버의 컨텍스트 창(llama.cpp `n_ctx`). **`None`은 "모른다"**
    # 이며 어떤 기본값도 아니다 — 창을 못 읽었는데 8192 같은 값을 채우면 헤드룸이
    # 지어낸 숫자 위에서 계산되어 "여유가 있다/없다"를 거짓으로 말한다.
    # repo가 이 값을 통제하지 못하는 배포가 있으므로(베타는 외부 서버) 상수로 박지 않는다.
    context_window: int | None = None


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
