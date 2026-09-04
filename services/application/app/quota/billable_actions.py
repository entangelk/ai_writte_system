"""어떤 제품 동작이 회원 요청 1회를 소비하는가 (Phase 8 Slice 8.0).

오너 결정 2026-08-03, 브리프 ``08-0-billable-request-boundary-decisions.md``
**B1~B6 전부 A**. 이 모듈은 **분류만** 한다 — 차감 시점·기간·한도·원장은
8.1~8.3의 결정이고 여기에는 카운터가 없다.

- **B1 — 단위는 요청 1건이다.** 아래 표의 endpoint 요청 1건이 회원 사용량 1회다.
  provider 호출 수가 아니다. 같은 버튼이 내부적으로 3번을 부르든 15번을 부르든
  회원에게는 1회이며, **원가 차이는 요금 단위가 아니라 내부 BM(요금제 설계·원가
  관리)에서 흡수한다**(오너: "우리는 사용자에게 쉬운 서비스를 제공해야 한다").
  그래서 이 표의 값은 사람이 읽는 이름 하나뿐이고 가중치 열이 없다.
- **B2 — 내부 repair 재시도와 설계된 루프 라운드는 그 1회에 포함한다.** 모델이
  JSON을 어겨서 다시 부른 것은 회원이 요청한 일이 아니다. **다만 과금하지 않는 것과
  안 보이는 것은 다르다** (오너 단서): 내부 호출은 전부 관측 안에 있어야 하고, 그
  구조적 근거는 ① 아래 모든 경로가 ``llm_call_scope``를 연다 ② seam C의
  ``ObservedProvider``가 repair를 포함한 provider 호출마다 레코드를 남긴다.
  ①은 ``tests/test_billable_actions.py``가, ②는 ``tests/test_llm_call_sites.py``·
  ``tests/test_llm_call_scope.py``가 잠근다.
- **B3 — 비용이 항목 수에 비례하는 경로도 1회다.** ``fan_out=True``는 표시일 뿐
  차감을 바꾸지 않는다. 요청당 내부 호출 상한을 둘지는 8.3이 판단한다.
- **B4 — LLM provider를 부르는 경로만 유료다.** 판정 기준은 "``llm_call_scope``를
  여는가"이며, 그 기준에 대해서는 가드가 기계적으로 판정한다. **다만 그것이
  "provider를 부르는 route는 반드시 잡힌다"를 뜻하지는 않는다** — scope를 아예 열지
  않는 route는 관측도 분류도 비껴간다(``ObservedProvider.generate``가 scope 없는
  호출을 미기록 통과시키는 것은 worker·script를 위한 계약이다). 현재 유료 10경로는
  per-endpoint 관측 셀로 덮여 있고(``BillableActionObservabilityCoverageTest``),
  남은 것은 관습 위반 미래 route에 대한 잔존 한계다(2026-08-03 독립 검증 H1,
  HANDOFF 추적 부채). 임베딩·색인(색인 rebuild·재색인 outbox·색인 worker)은 이번
  Phase에서 무료다.
- **B5 — 같은 논리 요청은 ``(user, project, 멱등키)``다.** 그래서 이 표에 **없는**
  것이 둘 있다: 비동기 생성을 실제로 실행하는 ``generation_worker``와
  ``POST …/writing/generation-jobs/{job_id}/retry``. 둘 다 provider를 쓰지만
  ``writing_generate``로 이미 센 **같은 논리 요청**이므로 재차감하지 않는다.
- **B6 — 이 표가 정본이다.** LLM을 부르는 경로가 분류 없이 추가되면 가드가 실패한다.

**알고 받은 것**(브리프 §1.4): ``/writing/accept``는 멱등 replay에서도 자기보고서
호출이 이미 나간 뒤라 "멱등 = 무과금"이 원가와 어긋난다. B5=A는 그 사실을 알고
차감하지 않기로 한 것이며, 보고서 호출을 replay 조회 뒤로 옮기는 수정은 별도 증분이다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BillableAction:
    """회원 사용량 1회를 소비하는 제품 동작 하나."""

    action: str
    """원장·회원 화면에 쓰일 리터럴. 조용히 바뀌면 과거 사용량과 대조가 끊긴다."""

    method: str
    path: str
    fan_out: bool = False
    """B3: 한 요청의 내부 호출이 데이터 항목 수 N에 비례하는 경로."""


#: 유료 동작 전수. 순서는 제품 흐름(글쓰기 → 분석 → 검색) 순.
BILLABLE_ACTIONS: tuple[BillableAction, ...] = (
    # 이어쓰기. short 는 동기, medium/long 은 202 뒤 generation_worker 가 실행한다 —
    # **어느 쪽이든 요청 1건이 1회**이고 워커 실행은 재차감하지 않는다(B5).
    BillableAction("writing_generate", "POST",
                   "/projects/{project_id}/writing/generate"),
    # Gate 단독 검사.
    BillableAction("writing_gate", "POST",
                   "/projects/{project_id}/writing/gate"),
    # 지적 1건에 대한 단독 수정.
    BillableAction("writing_revise", "POST",
                   "/projects/{project_id}/writing/revise"),
    # 수정→재검사 루프. 내부 라운드(revise ≤2 · gate ≤3 · retrieve ≤1)는 전부 이
    # 1회에 포함된다(B2).
    BillableAction("writing_revise_and_gate", "POST",
                   "/projects/{project_id}/writing/revise-and-gate"),
    # 후보 자기보고서 단독 요청.
    BillableAction("writing_report", "POST",
                   "/projects/{project_id}/writing/report"),
    # 승인(보고서 + Gate + 정본 저장).
    BillableAction("writing_accept", "POST",
                   "/projects/{project_id}/writing/accept"),
    # 원고 분석 추출. 이미 실행된 job 의 replay 는 provider 를 부르지 않지만,
    # 분류는 경로 단위이고 차감 시점은 8.3 이 정한다.
    BillableAction("analysis_extract", "POST",
                   "/projects/{project_id}/analysis/jobs/{job_id}/run"),
    BillableAction("draft_finalize", "POST",
                   "/projects/{project_id}/drafts/{draft_id}/finalize"),
    # 기존 기억과의 대조. 매칭된 후보 1건마다 판정을 부른다 → fan-out(B3).
    BillableAction("analysis_compare", "POST",
                   "/projects/{project_id}/analysis/jobs/{job_id}/compare",
                   fan_out=True),
    # 정체성 그룹 승인(2026-09-04, identity group Slice 5) — 남은 멤버마다 판정을
    # 부른다 → fan-out(B3). mid-failure 재개 재호출도 provider를 다시 부르는 진짜
    # 재실행이라 analysis_compare와 같은 서버 생성 키다(dedupe 참조).
    BillableAction("identity_group_approve", "POST",
                   "/projects/{project_id}/analysis/review-inbox/groups/"
                   "{group_id}/approve",
                   fan_out=True),
    # 컨텍스트 검색(질의 플래너가 LLM 이다).
    BillableAction("context_search", "POST",
                   "/projects/{project_id}/context-search"),
)

#: ``(path, method)`` → ``action`` 리터럴. 8.3 시행이 route 에서 동작 이름을 얻는
#: 자리이며, 가드와 **같은 정본**을 본다(분류되지 않은 경로는 여기 없으므로
#: 시행 dependency 가 그 경로에 붙으면 조회에서 즉시 드러난다).
BILLABLE_ACTION_BY_OPERATION: dict[tuple[str, str], str] = {
    (action.path, action.method.lower()): action.action
    for action in BILLABLE_ACTIONS
}

#: ``(path, method)`` 조회용 — 가드와 8.3 시행이 같은 정본을 본다.
BILLABLE_OPERATIONS: frozenset[tuple[str, str]] = frozenset(
    BILLABLE_ACTION_BY_OPERATION
)
