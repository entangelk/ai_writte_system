"""H1 probe — provider 호출 없는 InvalidIdentityJudgement의 재분류 오염(Slice 2 검증).

scope에 이미 성공 행(실제 run에서는 extractor 호출에 해당)이 있는 상태에서,
시드되지 않은 템플릿 서비스의 `TerminalJsonIdentityJudge`가 provider 호출 **없이**
`InvalidIdentityJudgement`를 내고 러너와 같은 D4 재분류를 돌리면 — 관계 없는
마지막 행이 `parse_error`로 바뀐다("마지막 호출이 곧 실패한 repair 호출"은
기본 조립에서만 성립하는 가정임을 보인다).

실행: python3 docs/verifications/2026-09-03/repro_reclassify_no_call_mislabel.py
기대 출력 마지막 줄: CONFIRMED: extractor success row corrupted to parse_error
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.application.app.analysis.identity_judge import TerminalJsonIdentityJudge
from services.application.app.analysis.identity_judging import (
    InvalidIdentityJudgement,
)
from services.application.app.analysis.prompt_templates import (
    InMemoryPromptTemplateRepository,
    PromptTemplateService,
)
from services.application.app.observability.llm_call_audit import (
    InMemoryLlmCallAuditRepository,
    LlmCallAuditService,
    LlmCallOutcome,
    LlmCallSite,
)
from services.application.app.observability.llm_call_scope import (
    current_scope,
    llm_call_scope,
)
from services.llm_gateway.app.payload import ChatCompletionRequest, ChatMessage
from tests.test_identity_judging import _candidate
from tests.test_llm_call_sites import _observed


async def main() -> int:
    audit = LlmCallAuditService(InMemoryLlmCallAuditRepository())
    # 시드하지 않은 템플릿 서비스 — get_template이 실패해 judge가 provider를
    # 부르기 전에 InvalidIdentityJudgement를 낸다.
    templates = PromptTemplateService(InMemoryPromptTemplateRepository())
    judge = TerminalJsonIdentityJudge(
        _observed(LlmCallSite.IDENTITY_JUDGE, "never reached"),
        prompt_templates=templates,
    )
    a = _candidate(candidate_id="a")
    b = _candidate(candidate_id="b")

    with llm_call_scope(audit, project_id=a.project_id, correlation_id="job-x"):
        prior = _observed(LlmCallSite.ANALYSIS_EXTRACTOR, "{}")
        await prior.generate(
            ChatCompletionRequest(messages=(ChatMessage(role="user", content="x"),))
        )
        try:
            await judge.judge(left=a, right=b)
        except InvalidIdentityJudgement as exc:
            scope = current_scope()
            scope.reclassify_last_as_parse_error(type(exc).__name__)

    calls = audit.list_calls(a.project_id)
    for c in calls:
        print(f"site={c.call_site} outcome={c.outcome} error_type={c.error_type}")
    if calls[0].call_site == "analysis_extractor" and calls[
        0
    ].outcome == LlmCallOutcome.PARSE_ERROR.value:
        print("CONFIRMED: extractor success row corrupted to parse_error")
        return 0
    print("NOT-REPRODUCED")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
