"""report 입력이 창에 들어가도록 컨텍스트 예산을 **유도**한다 (R-a, 오너 2026-07-31).

**왜 상수가 아닌가**: 오너 결정은 `(ii) 창에서 유도 + (iii) 후보 길이에서 유도`다. 상수안은
창이 다른 세 머신을 옮겨 다니는 이 프로젝트에서 **머신-로컬 값을 코드에 박는** 일이고,
후보 길이만 보는 안은 실측으로 부족했다(medium 후보로도 예산 8192는 −784로 거부됐다).

**무엇을 푸는 식인가**(2026-07-31 베타 실측, `scripts/report_budget_measure.py`):

    입력 = 컨텍스트 패키지 + report system 템플릿 + 후보 산문 + 포장
    가드(K-3) = 입력 + report 출력 상한 ≤ 창

그래서 컨텍스트에 쓸 수 있는 실제 토큰은 `창 − 출력상한 − system − 후보 − 포장`이고,
예산은 그것을 **회계 단위**로 옮긴 값이다.

**이 경로가 왜 report 하나만의 문제가 아닌가**: 생성 경로는 같은 패키지로 생성하고 그
결과를 곧바로 report에 태운다(`WritingService.generate` → `reporter.enrich`). report 쪽이
더 무거우므로(출력 상한 6144 + 후보 산문) **구속하는 것은 항상 report 다리**다. 생성
시점에는 후보가 아직 없지만 **상한은 출력 프리셋**이므로 그 값을 쓴다.

**모르면 건드리지 않는다.** 창을 모르면(게이트웨이 조회 실패·비-llama provider) 요청이 준
예산을 그대로 쓴다 — 종전 동작이다. 그리고 유도는 **줄이기만 한다**: 요청보다 큰 값을
돌려주지 않는다. 예산을 조용히 넓히는 것은 호출자가 요청하지 않은 비용이다.
"""

from __future__ import annotations

from typing import Protocol

from services.application.app.context_search.service import estimate_tokens


class _Capabilities(Protocol):
    async def context_window(self) -> int | None: ...
    async def count_tokens(self, text: str) -> int | None: ...


# 채팅 템플릿 + JSON 포장 몫. **실측 94**(2026-07-31, 여섯 예산 전 구간에서 동일) 위에 여유를
# 얹은 값이다. 항목 수·예산과 무관한 고정 프레이밍이라 예산에 비례해 커지지 않는다.
FRAMING_RESERVE_TOKENS = 150

# 회계 단위 ↔ 실제 렌더링 토큰의 비. 회계는 항목별 추정(`len/1.7`)의 합이고 실제 렌더링은
# 구조적 래퍼(`<context_package>`·섹션 태그)까지 포함하므로 둘은 정확히 같지 않다.
# **실측 0.965(작은 패키지) ~ 0.979(만재)** 중 **낮은 쪽**을 쓴다 — 낮게 잡을수록 실제
# 렌더링이 여유 안에 남는다(과대평가가 버그 방향이라는 §2-4 원칙과 같은 방향).
PACKAGE_ACCOUNTING_RATIO = 0.96

# 유도 결과가 0 이하가 되는 배포(창이 고정 오버헤드보다 작다)에서도 요청은 형태를 유지해야
# 한다 — `ContextBudget.max_tokens`는 양수여야 하기 때문이다. 그런 배포에서 남는 초과는
# 여기서 숨기지 않고 **K-3 가드가 400으로** 말한다. 예산을 억지로 맞춰 통과시키는 것이
# 아니라, 정직하게 거부되게 두는 것이 이 하한의 뜻이다.
MIN_CONTEXT_BUDGET_TOKENS = 256


async def derive_context_budget(
    *,
    requested_tokens: int,
    capabilities: _Capabilities | None,
    report_output_cap: int,
    report_system_template: str,
    candidate_tokens_upper_bound: int,
) -> int:
    """요청 예산을 창에 맞게 줄인다(늘리지 않는다). 판단할 수 없으면 요청값 그대로."""
    if capabilities is None:
        return requested_tokens
    window = await capabilities.context_window()
    if window is None:
        return requested_tokens
    # system 템플릿은 **고정 문자열**이라 프로세스당 한 번만 서버에 센다. 서버가 못 세면
    # 자체 추정으로 떨어지는데, 이 템플릿은 영문이라 `len/1.7`이 2배 넘게 과대평가한다
    # (1,660자 → 추정 976 vs 실측 465). 과대평가는 예산을 좁히는 쪽이라 안전하다.
    system_tokens = await capabilities.count_tokens(report_system_template)
    if system_tokens is None:
        system_tokens = estimate_tokens(report_system_template)
    allowance = (
        window
        - report_output_cap
        - system_tokens
        - candidate_tokens_upper_bound
        - FRAMING_RESERVE_TOKENS
    )
    derived = int(allowance * PACKAGE_ACCOUNTING_RATIO)
    return max(MIN_CONTEXT_BUDGET_TOKENS, min(requested_tokens, derived))


def candidate_tokens_from_text(text: str) -> int:
    """이미 있는 후보 산문의 토큰 추정.

    한글 산문 밀도(1.7)로 보정된 추정이며, 남는 오차는 K-3 가드가 받는다 — 그래서 여기서
    토크나이저 왕복을 요청마다 하지 않는다(후보는 요청마다 다르므로 캐시가 안 듣는다).
    """
    return estimate_tokens(text)
