"""FastAPI dependency — 인증·소유권·관리자·quota 시행.

`main.py` 에서 추출했다(공유 prelude 추출, 2026-08-06). 본문 byte-동일.

**두 겹 구조를 유지한다**: project route 는 `_REQUIRE_PROJECT_OWNER` 로 인증을 먼저
선언하고 `require_project_owner` 도 같은 dependency 를 하위로 갖는다. 어느 한 겹을
지워도 관측 상태코드가 안 변하므로 요청 구동 테스트로는 안 보인다
(`CombinedBoundaryMatrixTest` 의 격리 셀이 그 자리다).
"""

from __future__ import annotations

import uuid

from fastapi import (
    Depends,
    HTTPException,
    Header,
    Request,
)
from services.application.app.auth.cookies import SESSION_COOKIE_NAME
from services.application.app.core_sot.service import NotFound
from services.application.app.quota.billable_actions import BILLABLE_ACTION_BY_OPERATION
from services.application.app.quota.dedupe import (
    UnclassifiedBillableAction,
    resolve_dedupe_key,
)
from services.application.app.quota.enforcement import (
    AdmissionUnavailable,
    QuotaCharge,
    QuotaEnforcementService,
    QuotaRefusalReason,
    QuotaRefused,
)
from typing import Annotated


# --- Authentication enforcement (D8-3a) --------------------------------------
# D7=A: enforcement is a FastAPI *dependency* declared per operation, backed by
# an exhaustive guard — not middleware (path patterns become the policy and new
# routes open silently) and not the service layer (every signature changes).
#
# Module level rather than a create_app closure on purpose. A closure would be a
# different function object per app, so neither ``app.dependency_overrides`` nor
# the exhaustive guard could name it; the guard has to look for exactly one
# identity on every route or it cannot tell a protected route from an open one.
def current_user_or_none(request: Request):
    """Resolve the session cookie to a live, still-active user, or None."""
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw_token:
        return None
    session = request.app.state.sessions.resolve(raw_token)
    if session is None:
        return None
    user = request.app.state.users.get_by_id(session.user_id)
    # A user disabled or deleted after the session was minted must not keep
    # working just because the cookie is still within its TTL.
    if user is None or not user.is_active:
        return None
    return user


def require_authenticated_user(request: Request):
    """Fail closed: no live session means the operation does not run at all."""
    user = current_user_or_none(request)
    if user is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


# C-2 read-only. HEAD rides along with GET because Starlette answers it from the
# same route; both are side-effect free by HTTP contract.
_GRANTED_METHODS = frozenset({"GET", "HEAD"})


def require_project_owner(
    request: Request,
    project_id: str,
    current=Depends(require_authenticated_user),
):
    """Allow the owning user, or an administrator holding a live access grant.

    Missing projects retain their 404 face.

    D8-5e (F1=C, owner 2026-08-02): the grant is the *only* way past ownership,
    and it is narrower than ownership in two ways that are both enforced here:

    * **read-only (C-2)** — a grant admits GET/HEAD and nothing else. Anything
      that could write is refused even while the grant is live, so an
      administrator can never edit someone else's manuscript. The test is the
      HTTP method rather than a hand-kept list of "read operations": a list
      would silently misclassify the next endpoint someone adds, and failing
      closed on an unlisted method is the safe direction.
    * **still an administrator** — the grant is checked *together with*
      ``is_admin``, not instead of it. A grant issued to someone who has since
      lost the role stops working immediately rather than outliving it.

    ``owner_id is None`` keeps denying everyone (E1=A) — a grant does not adopt
    an unowned project.
    """
    try:
        project = request.app.state.core_sot.get_project(project_id=project_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if project.owner_id is not None and project.owner_id == current.id:
        return project
    if (
        # E1=A first, on this branch too. Omitting it here (while the owner
        # branch had it) was the 2026-08-02 verification Blocking: an unowned
        # project opened to any admin holding a grant, contradicting the three
        # places the SoT says otherwise — including the docstring above.
        project.owner_id is not None
        and current.is_admin
        and request.method in _GRANTED_METHODS
        and (grant := request.app.state.access_grants.active(
            admin_user_id=current.id, project_id=project_id
        ))
        is not None
    ):
        # C-3: record what the grant was actually used for. This dependency is
        # the single choke point — the grant is honoured nowhere else — so the
        # record cannot be bypassed by adding an endpoint.
        #
        # Deliberately **not** isolated: a failure here propagates and the
        # request fails (storage 503 face). An access nobody can account for is
        # what F1=C exists to prevent, so letting the read through unrecorded
        # would quietly restore the state C was chosen over.
        request.app.state.access_grants.record_use(
            grant, method=request.method, path=request.url.path
        )
        return project
    raise HTTPException(status_code=403, detail="forbidden")


# --- Request quota enforcement (Phase 8 Slice 8.3) ---------------------------
# 오너 결정 2026-08-04, 브리프 ``08-3-quota-enforcement-decisions.md``.
# Q7=A: 시행은 **operation 마다 선언하는 dependency** 다 — 인증(D7=A)이 미들웨어를
# 기각한 이유가 그대로 적용된다(경로 패턴이 정책이 되고 새 route 가 조용히 열린다).
# ``_REQUIRE_PROJECT_OWNER`` **뒤에** 선언하므로 404·403 은 차감 앞에서 끝난다.
#
# ★ 정산(원장 → 잠금 해제)이 dependency 의 ``yield`` 뒤가 아니라 **route wrapper**
# 에 있는 이유(구현이 드러낸 제약, 결정 변경 아님): Q1-a=A 는 "2xx 그리고 provider
# 호출"을 요구하는데 **yield dependency 는 응답 상태코드를 볼 수 없다.** 이 앱의
# partial envelope 6곳과 async 202 는 예외가 아니라 ``JSONResponse`` 를 *반환*하므로
# dependency 의 exit 에는 아무 신호도 오지 않는다 — 그 자리에서 정산하면 **일하고도
# 실패한 응답(partial envelope)과 접수만 한 202 가 과금된다.** 그래서 입장은
# dependency(선언·전수 가드 가능)가, 정산은 실제 응답을 보는 wrapper 가 맡는다.
# wrapper 는 정책을 **정하지 않는다**: dependency 가 ``request.state`` 에 남긴
# 영수증이 있을 때만 동작하므로 무료 경로는 그대로 지나간다.
_QUOTA_STATE = "quota_charge"


#: Q6=C. 확인은 헤더로 받는다 — 이 저장소의 쿼리 파라미터 선례가 전부 GET/DELETE 라
#: POST 의 상태 변경 의도를 URL 에 싣지 않는다. 값의 존재만 본다(비밀이 아니다).
CONFIRM_DUPLICATE_HEADER = "X-Confirm-Duplicate"


#: Q5=B — 프론트가 **다르게 행동해야 하는 사건이 셋**이라 코드가 셋이다.
#: 429 "확인하면 지금 통과" / 402 "이번 창에는 방법이 없다" / 403 "관리자만 푼다".
_QUOTA_REFUSAL_STATUS: dict[QuotaRefusalReason, int] = {
    QuotaRefusalReason.LOCKED: 429,
    QuotaRefusalReason.EXCEEDED: 402,
    QuotaRefusalReason.SUSPENDED: 403,
}


def _billable_action(request: Request) -> str:
    """이 요청이 소비하는 유료 동작. 분류표(8.0 B6)가 정본이다.

    시행 dependency 가 분류되지 않은 route 에 붙는 것은 배선 결함이며, 그때
    ``dedupe.py`` 와 **같은 예외**를 올린다 — 두 표(분류·매핑) 중 어느 쪽이
    비어 있든 호출자가 같은 얼굴(503)로 닫을 수 있게(독립 검증 2026-08-04 H-3).
    """
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    try:
        return BILLABLE_ACTION_BY_OPERATION[(path, request.method.lower())]
    except KeyError as exc:
        raise UnclassifiedBillableAction(
            f"{request.method} {path} is not in the billable action table"
        ) from exc


async def _request_body_mapping(request: Request) -> dict:
    """이미 읽힌 본문을 dict 로. 본문 없는 두 경로(analysis_*)는 ``{}`` 다.

    FastAPI 는 dependency 를 풀기 **전에** 본문을 읽고 Starlette 이 그것을 캐시하므로
    여기서 다시 읽어도 endpoint 의 파싱을 굶기지 않는다(Q7=A 의 구현 확인 항목).
    """
    raw = await request.body()
    if not raw:
        return {}
    try:
        parsed = await request.json()
    except Exception:  # noqa: BLE001 — 본문이 JSON 이 아니면 키가 없는 것과 같다
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def enforce_quota(
    request: Request,
    x_confirm_duplicate: Annotated[
        str | None, Header(alias=CONFIRM_DUPLICATE_HEADER)
    ] = None,
    current=Depends(require_authenticated_user),
):
    """유료 요청 1건의 입장 (Q1=C·Q3=E·Q3-a=A·Q4=A·Q5=B·Q6=C·Q9=A).

    통과하면 영수증을 ``request.state`` 에 남기고, 그 요청이 실제로 성공했을 때만
    wrapper 가 원장에 한 행을 쓴다. 저장소가 실패하면 예외가 그대로 올라가
    전역 handler 의 503 이 된다(Q4=A — 계량 불능은 무료 제공이 아니다).
    """
    enforcement: QuotaEnforcementService | None = getattr(
        request.app.state, "quota", None
    )
    if enforcement is None:
        # 조립되지 않은 배포는 유료 경로를 열지 않는다(fail-closed). 인증·소유권과
        # 달리 여기는 "없으면 통과"가 곧 무료 제공이라 503 이 옳은 얼굴이다.
        raise HTTPException(
            status_code=503, detail="request quota enforcement is not configured"
        )
    body = await _request_body_mapping(request)
    # 분류·매핑 조회를 admit 밖에 둔다: 여기서 나는 실패는 저장소 장애가 아니라
    # **배선 결함**이고(유료 route 인데 표에 없다), 그 얼굴을 아래에서 따로 정한다.
    try:
        action = _billable_action(request)
        dedupe_key = resolve_dedupe_key(
            action,
            body=body,
            path_params=request.path_params,
            server_key=uuid.uuid4().hex,
        )
    except UnclassifiedBillableAction as exc:
        # 독립 검증 2026-08-04 H-3. 가드가 분류표와 매핑표의 1:1 을 단정하므로
        # **도달할 수 없어야 하는 자리**지만, 도달한다면 그 요청은 중복 방지 없이
        # 도는 유료 요청이다 — 통과시키지 않고 Q4=A 와 같은 503 으로 닫는다
        # (미매핑 500 을 공개 계약에 흘리지 않는다).
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    # Q6=C: 값의 존재가 아니라 **내용**이 확인이다. 빈 헤더를 확인으로 읽으면
    # 프록시나 클라이언트가 실수로 붙인 빈 값이 사용량 1회를 더 쓰게 된다
    # (독립 검증 2026-08-04 H-5).
    confirmed = bool(x_confirm_duplicate and x_confirm_duplicate.strip())
    try:
        charge = enforcement.admit(
            user_id=current.id,
            member_created_at=current.created_at,
            action=action,
            target_project_id=request.path_params["project_id"],
            dedupe_key=dedupe_key,
            confirmed=confirmed,
        )
    except QuotaRefused as exc:
        headers = (
            {"Retry-After": str(exc.retry_after_seconds)}
            if exc.retry_after_seconds is not None else None
        )
        raise HTTPException(
            status_code=_QUOTA_REFUSAL_STATUS[exc.reason],
            detail=exc.detail,
            headers=headers,
        ) from exc
    except AdmissionUnavailable as exc:
        # §Q3-a 계약 3: 초과를 허용하느니 요청을 실패시킨다.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    setattr(request.state, _QUOTA_STATE, charge)
    # Q6=C: 확인은 잠금만 뚫는 것이 아니라 Q8=C 의 상태 가드도 함께 통과시킨다 —
    # 사용자에게는 통로가 하나여야 한다. endpoint 가 이 값을 읽는다.
    request.state.quota_confirmed = confirmed
    return charge


def quota_confirmed(request: Request) -> bool:
    """이 요청이 확인 헤더를 달고 왔는가(무료 경로에서는 항상 ``False``)."""
    return bool(getattr(request.state, "quota_confirmed", False))


def quota_charge(request: Request) -> QuotaCharge:
    """이 요청의 입장 영수증. 유료 경로에서만 존재한다(없으면 배선 결함이다)."""
    return getattr(request.state, _QUOTA_STATE)


def require_admin_user(current=Depends(require_authenticated_user)):
    """Allow only administrators (D8-5, D6=A).

    403 rather than 401: the session is live and re-logging in changes nothing,
    which is the same distinction the ownership boundary draws. It is also *not*
    404 — hiding the admin surface would mean the frontend could not tell "no
    such endpoint" from "not for you".
    """
    if not current.is_admin:
        raise HTTPException(status_code=403, detail="forbidden")
    return current


# One shared list so every protected operation declares the *same* dependency
# object. ``dependencies=`` copies it per route, so sharing is safe.
_REQUIRE_AUTH = [Depends(require_authenticated_user)]


_REQUIRE_PROJECT_OWNER = [
    Depends(require_authenticated_user),
    Depends(require_project_owner),
]


# D8-5: the admin surface is a third tier, layered the same way — the outer list
# names the authentication dependency so the exhaustive guard can see it on the
# route, and the inner dependency re-declares it so the check cannot run against
# an unauthenticated request even if the outer layer is ever dropped.
_REQUIRE_ADMIN = [
    Depends(require_authenticated_user),
    Depends(require_admin_user),
]


# Slice 8.3 (Q7=A): the nine billable operations. Enforcement is declared **after**
# ownership so 404 (no such project) and 403 (not yours) are answered before any
# quota is touched — that ordering is the whole reason those two statuses are
# structurally free, and reversing it is what the over-strict guard watches for.
_REQUIRE_PROJECT_OWNER_BILLABLE = [
    *_REQUIRE_PROJECT_OWNER,
    Depends(enforce_quota),
]
