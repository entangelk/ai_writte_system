"""컨텍스트 항목 한 줄의 **정본** 렌더링 — 프롬프트와 예산 회계가 공유한다.

회계가 렌더링보다 작으면 예산이 창을 넘기는 프롬프트를 통과시킨다(2026-07-29 베타 실측:
포인터 JSON을 세지 않아 회계가 12.7배 과소평가했고 `writing_report`가 400으로 죽었다).
그래서 형식을 두 벌로 갖지 않고 여기 한 곳에 둔다.

**왜 이제서야 한 곳이 됐나**: 종전 정본 렌더러는 `writing/prompt.py`에 있었고 포인터 JSON을
싣기 위해 `writing/context_pointer.py`를 썼는데, 그 모듈이 `context_search.service`를
import하므로 회계가 되돌려 import하면 순환이었다(그래서 사본을 뒀다). K-6=R-e가 포인터
렌더링을 없애면서 이 렌더러의 의존성이 `ContextItemStatus` 하나로 줄어 합칠 수 있게 됐다.
"""

from __future__ import annotations

from services.application.app.context_search.models import ContextItemStatus


def render_context_item(
    *, text: str, status: ContextItemStatus, number: int | None = None
) -> str:
    """항목 한 줄.

    ``number``가 있으면 그 항목의 **인용 번호**를 앞에 단다 — report extractor가 claim의
    근거를 그 번호로 지목하고(K-6=R-e), 번호→포인터 매핑은 서버(`report.parse_report`)가
    한다. 번호를 주지 않는 소비자(생성·revise)는 평문 프롬프트라 인용이 없다.

    Candidate-origin 항목은 라벨로 표시해 모델이 승인된 지식으로 다루지 않게 한다
    (writing_agent_prompt.md §2.2).
    """
    label = (
        "candidate (uncertain)"
        if status is ContextItemStatus.CANDIDATE
        else "canonical"
    )
    if number is None:
        return f"- [{label}] {text}"
    return f"- [{number}] [{label}] {text}"
