"""유료 경로별 중복 방지 키 (Phase 8 Slice 8.3, Q9=A).

오너 결정 2026-08-04, 브리프 ``08-3-quota-enforcement-decisions.md`` §Q9.
8.2 의 원장은 ``(user_id, action, dedupe_key)`` 에 **부분 유니크 인덱스**를 걸어 두
었다 — 그 키를 무엇으로 채우느냐가 "아무 일도 안 한 요청에 과금하지 않는다"의 **1차
방어**다(2차는 Q1-a: provider 를 안 불렀으면 애초에 안 센다).

**표가 정본이다**(8.0 분류표와 같은 성격). 경로마다 다른 이유:

- 글쓰기 5경로 — ``body.request_id``. 프론트가 한 흐름에 uuid 하나를 쓰고 그것을
  generate·gate·revise-and-gate·accept 가 공유하지만, 원장 키에 ``action`` 이 함께
  들어가므로(8.2 L2=A) 네 동작이 하나로 접히지 않는다.
- ``writing_accept`` — ``body.idempotency_key``. 정본 저장의 멱등 replay 가 **같은
  키로** 오므로 그 replay 가 두 번 세지 않는다.
- ``analysis_extract`` — **경로 파라미터 ``job_id``**. 이 경로만 서버 생성이 아니다.
  job 이 ``PENDING`` 이 아니면 provider 를 한 번도 안 부르고 기존 후보를 200 으로
  돌려주는데, 서버 생성 키였다면 그 replay 가 **매번 과금**된다. **클라이언트가 바꿀
  수 없는 키**라는 점이 이 칸의 핵심이다.
- ``analysis_compare`` — 서버 생성. 재실행은 매번 provider 를 다시 부르는 **진짜
  재실행**이라 두 번 세는 것이 옳다. 네트워크 재전송은 8.2b 잠금이 덮는다.
- ``identity_group_approve`` — 서버 생성(2026-09-04, Slice 5). mid-failure 재개
  재호출은 남은 멤버만큼 provider 를 다시 부르는 진짜 재실행이라 같은 모양이다.
  ``(group_id, revision)`` 을 키로 접으면 나중의 새 revision 재승인이 무과금으로
  접히는데, 빈 키·접힌 키로 **다른 요청이 무과금** 되는 것이 이 표가 더 나쁜 쪽으로
  보는 실패다.
- ``context_search`` — ``body.idempotency_key``. 호출자가 재시도할 때 드는 키다.

값이 비어 있으면 **서버 생성으로 떨어진다**: 막지 못하는 것은 재전송 중복뿐이고
(그 자리는 잠금이 덮는다), 빈 키를 그대로 쓰면 서로 다른 요청 두 건이 한 행으로
접혀 **일한 요청이 무과금**이 된다 — 두 실패 중 후자가 더 나쁘다.

**S-1 (오너 2026-09-05 = A+D+report 국소 C) — BODY 키는 1회만 소비된다.** 위 신뢰
가정("프론트가 한 흐름에 uuid 하나")을 악성 클라이언트가 어기면 같은 키의 반복
재제출로 LLM 은 실제로 돌면서 과금은 1행으로 접힌다(감사 §A.1). 계약 문장은
*"같은 논리 요청은 한 번만 실행된다 — 정산된 키의 재제출은 실행 전 409, 진행 중
재전송은 잠금 429, 확인된(``X-Confirm-Duplicate``) 재실행은 +1 과금"* 이다.
경로별 처분은 :data:`KEY_REPLAY_ACTIONS` 이 정한다.
"""

from __future__ import annotations

from enum import StrEnum


class UnclassifiedBillableAction(RuntimeError):
    """유료 동작인데 이 표에 없다 (독립 검증 2026-08-04 H-3).

    **일어날 수 없어야 하는 상태**다 — 분류표(8.0)와 이 표의 1:1 을 가드가 단정
    하므로 둘 중 하나만 고치면 스위트가 먼저 실패한다. 그럼에도 이름 있는 예외인
    이유는 **도달했을 때의 얼굴** 때문이다: 시행 dependency 가 이것을 Q4=A 와 같은
    503(fail-closed)으로 옮기므로, 미매핑 500 이 공개 계약에 새지 않는다(H3 의
    "미매핑 500 부채 0건"). ``KeyError`` 였다면 그 자리가 500 이었고, 경로
    파라미터 조회 같은 무관한 ``KeyError`` 와도 구분되지 않았다.
    """


class DedupeSource(StrEnum):
    """키를 어디서 얻는가. 값은 ``BODY``/``PATH`` 의 필드 이름과 함께 쓴다."""

    BODY = "body"
    PATH = "path"
    SERVER = "server"


#: 유료 동작 → (출처, 필드명). ``SERVER`` 는 필드가 없다.
DEDUPE_SOURCES: dict[str, tuple[DedupeSource, str | None]] = {
    "writing_generate": (DedupeSource.BODY, "request_id"),
    "writing_gate": (DedupeSource.BODY, "request_id"),
    "writing_revise": (DedupeSource.BODY, "request_id"),
    "writing_revise_and_gate": (DedupeSource.BODY, "request_id"),
    "writing_report": (DedupeSource.BODY, "request_id"),
    "writing_accept": (DedupeSource.BODY, "idempotency_key"),
    "analysis_extract": (DedupeSource.PATH, "job_id"),
    "draft_finalize": (DedupeSource.BODY, "idempotency_key"),
    "analysis_compare": (DedupeSource.SERVER, None),
    "identity_group_approve": (DedupeSource.SERVER, None),
    "context_search": (DedupeSource.BODY, "idempotency_key"),
}

#: S-1 D1 — BODY 키가 **이미 정산됐을 때**의 재제출 처분(서버·경로 키는 해당 없음).
#:
#: - ``"consume"``(기본): 입장에서 409 로 거부한다. 글쓰기 4경로(generate·gate·
#:   revise·revise-and-gate)와 ``context_search`` — 결과가 서버에 지속되거나 애초에
#:   재생할 것이 없어, 정직한 재시도는 상태 재조회 또는 새 키로 회복된다.
#: - ``"handler"``: 입장은 통과시키고 핸들러가 **자기 replay 장치**로 저장 결과를
#:   돌려준다(``writing_accept`` — 멱등 receipt 조회를 enrich 앞으로 옮긴 순서
#:   교정. ``draft_finalize`` — ``idempotent_replay`` 면 runner 를 안 돌린다).
#: - ``"stored"``: 입장에서 **응답 저장소**를 조회한다(``writing_report`` — 응답을
#:   지속하지 않는 유일한 경로라 국소 C). 저장 응답이 있으면 재생하고, TTL 로
#:   사라졌으면 409 — 어느 쪽이든 provider 는 다시 안 돈다.
KEY_REPLAY_ACTIONS: dict[str, str] = {
    "writing_accept": "handler",
    "draft_finalize": "handler",
    "writing_report": "stored",
}


def key_resubmission_policy(action: str) -> str:
    """BODY 키 경로의 재제출 처분. ``"pass"`` 는 검증 대상이 아니라는 뜻이다.

    서버 생성 키(클라이언트가 못 고른다)와 경로 파라미터 키(``job_id``)는 감사
    §A.1 의 결함이 성립하지 않으므로 입장에서 아무것도 묻지 않는다.
    """

    source, _ = DEDUPE_SOURCES.get(action, (None, None))
    if source is not DedupeSource.BODY:
        return "pass"
    return KEY_REPLAY_ACTIONS.get(action, "consume")


def resolve_dedupe_key(
    action: str, *, body: dict, path_params: dict, server_key: str
) -> str:
    """표대로 키를 뽑는다. 분류되지 않은 동작은 **fail-closed** 로 거절한다.

    분류 없는 유료 동작이 조용히 서버 생성 키로 도는 것을 막는다 — 그 상태는
    "중복 방지가 꺼진 유료 경로"이고, 조용하다는 점에서 가장 나쁜 형태다.
    """

    if action not in DEDUPE_SOURCES:
        raise UnclassifiedBillableAction(
            f"no dedupe key mapping for billable action {action!r}"
        )
    source, field = DEDUPE_SOURCES[action]
    if source is DedupeSource.SERVER:
        return server_key
    holder = body if source is DedupeSource.BODY else path_params
    value = holder.get(field) if isinstance(holder, dict) else None
    if not isinstance(value, str) or not value.strip():
        return server_key
    return value
