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
- ``context_search`` — ``body.idempotency_key``. 호출자가 재시도할 때 드는 키다.

값이 비어 있으면 **서버 생성으로 떨어진다**: 막지 못하는 것은 재전송 중복뿐이고
(그 자리는 잠금이 덮는다), 빈 키를 그대로 쓰면 서로 다른 요청 두 건이 한 행으로
접혀 **일한 요청이 무과금**이 된다 — 두 실패 중 후자가 더 나쁘다.
"""

from __future__ import annotations

from enum import StrEnum


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
    "analysis_compare": (DedupeSource.SERVER, None),
    "context_search": (DedupeSource.BODY, "idempotency_key"),
}


def resolve_dedupe_key(
    action: str, *, body: dict, path_params: dict, server_key: str
) -> str:
    """표대로 키를 뽑는다. 분류되지 않은 동작은 **fail-closed** 로 거절한다.

    분류 없는 유료 동작이 조용히 서버 생성 키로 도는 것을 막는다 — 그 상태는
    "중복 방지가 꺼진 유료 경로"이고, 조용하다는 점에서 가장 나쁜 형태다.
    """

    if action not in DEDUPE_SOURCES:
        raise KeyError(f"no dedupe key mapping for billable action {action!r}")
    source, field = DEDUPE_SOURCES[action]
    if source is DedupeSource.SERVER:
        return server_key
    holder = body if source is DedupeSource.BODY else path_params
    value = holder.get(field) if isinstance(holder, dict) else None
    if not isinstance(value, str) or not value.strip():
        return server_key
    return value
