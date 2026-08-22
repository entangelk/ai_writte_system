"""OpenAPI 에러 선언(`responses=`) 과 그것을 조립하는 데코레이터.

`main.py` 에서 추출했다(공유 prelude 추출, 2026-08-06). 본문 byte-동일.

`_protected`/`_owned`/`_billable`/`_admin` 은 선언 dict 에 tier 별 상태코드를 더하는
**순수 함수**다 — FastAPI dependency 가 아니다(그쪽은 `dependencies.py`).
선언과 시행이 갈라지지 않도록 tier 전수 가드가 둘을 함께 본다.
"""

from __future__ import annotations

from services.application.app.writing.http_models import ErrorDetailResponse
from services.llm_gateway.app.errors import (
    ProviderError,
    ProviderErrorCode,
)
from typing import Union

from .models import AutoPromotePartialResponse


# HTTP error contract declarations (SoT v1.7.29 "HTTP 에러 응답 계약", H3 S2).
#
# Every error body in this app is the uniform ``{"detail": <string>}``
# (``ErrorDetailResponse``), so declaring a status documents *which* failures an
# endpoint can return — it never changes runtime behaviour. The status codes
# below are the realistic set each endpoint actually raises, not the full app
# vocabulary.
#
# 422 is deliberately absent everywhere: FastAPI documents request-schema
# validation automatically and its body shape (``{"detail": [ ... ]}``) differs.
_ERROR = {"model": ErrorDetailResponse}


# The only 503 in the CRUD family is the data-integrity face: stored drafts that
# predate the W3 ordered-unit invariant. The fix is the one-shot migration, not a
# corrected request, so the description says so rather than leaving the reader to
# infer it from a log (the exact gap H3 exists to close).
_MIGRATION_503 = {
    "model": ErrorDetailResponse,
    "description": "Stored draft metadata predates the ordered-unit invariant "
                   "(or is corrupt). Run scripts/migrate_ordered_units.py; "
                   "retrying the request alone cannot succeed.",
}


# SoT v1.7.35 D2=A: the third face of 503 — the canonical store is configured
# but *failing*. Unlike the other two faces the remedy is not a one-shot human
# action but storage recovery, after which retrying the same request is the
# correct recovery (promotion is idempotent, so a retry promotes only what is
# left).
#
# Resolved lazily and exactly once, because main.py must import without pymongo:
# the in-memory path needs no driver install (see _default_core_sot_service). A
# missing driver yields an empty tuple, and `except ()` matches nothing — which
# is the correct behaviour, since a deployment with no Mongo has no Mongo failure
# to classify.
#
# Deliberately ONE named seam rather than a clause per call site: it covers both
# the memory repository and the reindex outbox (each writes Mongo directly), and
# the deferred repository-level exception taxonomy replaces this single point
# instead of every endpoint (brief "Follow-up considerations").
def _resolve_storage_error_types() -> tuple[type[BaseException], ...]:
    try:
        from pymongo.errors import PyMongoError
    except ModuleNotFoundError:
        return ()
    return (PyMongoError,)


_STORAGE_ERRORS = _resolve_storage_error_types()


_AUTO_PROMOTE_503 = {
    "model": Union[AutoPromotePartialResponse, ErrorDetailResponse],
    "description": "The canonical store failed mid-promotion. Every memory this "
                   "call minted is returned in `promoted` — including one whose "
                   "mint succeeded but whose reindex enqueue then failed — and "
                   "none of them are rolled back, so `promoted` always matches "
                   "what is stored. `promotion_error` names the stage that "
                   "failed. Recover the store and retry the same request: "
                   "promotion is idempotent, so the retry promotes only what is "
                   "left — and a reindex enqueue lost after its mint is repaired "
                   "by that same retry, because a replayed promotion re-enqueues.",
}


# SoT v1.7.38: the storage face of 503 is reachable from *every* endpoint that
# touches Mongo — which is every endpoint except /health — because a global
# handler (see create_app) maps a driver failure to 503 instead of letting it
# leak as an opaque 500. Declaring it everywhere is what keeps OpenAPI the
# mechanical truth (D3=A): a status the runtime can return must appear here.
#
# Endpoints whose 503 already carried another face keep that wording and gain
# this sentence, because one status code gets one declaration and the reader
# needs to know both remedies apply.
_STORAGE_503_NOTE = (
    " The canonical store may also be unreachable or failing; in that case "
    "recover it and retry the same request unchanged."
)


_STORAGE_503 = {
    "model": ErrorDetailResponse,
    "description": "The canonical store is unreachable or failing. Recover it "
                   "and retry the same request; the request itself needs no "
                   "change.",
}


def _with_storage_note(declaration: dict) -> dict:
    return {**declaration, "description": declaration["description"] + _STORAGE_503_NOTE}


_MIGRATION_503 = _with_storage_note(_MIGRATION_503)


# Auth (multi-user D2=A). 401 first appeared on the login endpoint (bad
# credentials) and the session-reading endpoint (missing/expired/revoked cookie).
# Project-scoped declarations gain 403 through ``_owned`` below.
_ERRORS_401: dict[int | str, dict] = {401: _ERROR, 503: _STORAGE_503}


# C-6: login additionally answers 409 when the account still carries a password
# somebody else chose. Only /auth/login declares it — no other operation gains a
# status, because the enforcement point is *obtaining a session*, not using one.
_ERRORS_LOGIN_409: dict[int | str, dict] = {
    400: _ERROR, 401: _ERROR, 409: _ERROR, 503: _STORAGE_503,
}


# Logout is the one non-/health operation that stays reachable without a session:
# it is idempotent by design so a client can always reach a known-logged-out
# state. It therefore keeps a declaration with no 401 — hence its own constant,
# so that adding 401 to the shared storage declaration cannot reach it.
_ERRORS_LOGOUT: dict[int | str, dict] = {503: _STORAGE_503}


# Signup request (2026-08-22) is public like /auth/login: it is how an account
# begins to exist. 400 = policy (empty username, password under 12 chars),
# 409 = username taken (an intentional disclosure — the requester needs to pick
# another username), 503 = session store unavailable (the Mongo insert happens
# under the same envelope as every other auth write).
_ERRORS_SIGNUP: dict[int | str, dict] = {
    400: _ERROR, 409: _ERROR, 503: _STORAGE_503,
}


# D8-3a: every protected operation can answer 401, so the declaration is added
# once here instead of 61 times at the call sites. H3 (D3=A) makes OpenAPI the
# mechanical truth about what a request can get back, and after this slice a
# sessionless request to any of them gets 401 before the handler runs.
#
# Central, but not a substitute for the guard: the wrapper only makes the
# *declaration* right. An operation that gets the declaration and forgets
# ``dependencies=_REQUIRE_AUTH`` would be documented as protected while staying
# open — which is why the exhaustive guard checks the route, not the spec.
def _protected(declaration: dict[int | str, dict]) -> dict[int | str, dict]:
    return {401: _ERROR, **declaration}


def _owned(declaration: dict[int | str, dict]) -> dict[int | str, dict]:
    """Declare the 403 face added by the project ownership dependency."""
    return {403: _ERROR, **declaration}


def _billable(declaration: dict[int | str, dict]) -> dict[int | str, dict]:
    """Declare the faces request-quota enforcement adds (Phase 8 Slice 8.3, Q5=B).

    Three statuses because the frontend has to *do* three different things:

    * ``402`` — the window's quota is spent. Nothing the caller can do until it
      resets (or an administrator raises the limit / a plan is bought, which is
      the 8.6 axis this code deliberately points at).
    * ``429`` — the same request is already in progress, or was just made. This
      one is retryable *right now* by re-sending with ``X-Confirm-Duplicate``.
    * ``503`` — the quota stores could not answer (Q4=A, fail-closed). It rides
      the storage face every protected operation already declares.

    ``403`` is deliberately **not** added here: project-scoped operations already
    declare it through ``_owned``, and a suspended account reuses that status
    (Q5=B) rather than inventing a fourth. The two are told apart by ``detail``
    for display only — H3 still forbids branching on that string.
    """
    return {402: _ERROR, 429: _ERROR, **declaration}


def _admin(declaration: dict[int | str, dict]) -> dict[int | str, dict]:
    """Declare the 403 face added by the admin dependency (D8-5).

    Same status as ``_owned`` and deliberately a separate helper: the two 403s
    answer different questions ("not your project" vs "not an admin"), and a
    single shared helper would make the declaration guards unable to say which
    boundary an operation is behind.
    """
    return {403: _ERROR, **declaration}


_ERRORS_STORAGE: dict[int | str, dict] = _protected({503: _STORAGE_503})


_ERRORS_404: dict[int | str, dict] = _protected({404: _ERROR, 503: _STORAGE_503})


_ERRORS_404_502: dict[int | str, dict] = _protected(
    {404: _ERROR, 502: _ERROR, 503: _STORAGE_503}
)


_ERRORS_404_STORAGE: dict[int | str, dict] = _protected(
    {404: _ERROR, 503: _AUTO_PROMOTE_503}
)


_ERRORS_400_404: dict[int | str, dict] = _protected({
    400: _ERROR, 404: _ERROR, 503: _STORAGE_503,
})


_ERRORS_404_409: dict[int | str, dict] = _protected({
    404: _ERROR, 409: _ERROR, 503: _STORAGE_503,
})


_ERRORS_400_404_409: dict[int | str, dict] = _protected({
    400: _ERROR, 404: _ERROR, 409: _ERROR, 503: _STORAGE_503,
})


# D8-5 admin surface. 403 = "not an admin" (see _admin), and it is additive over
# the same 401/503 every protected operation carries.
_ERRORS_ADMIN: dict[int | str, dict] = _admin(_protected({503: _STORAGE_503}))


_ERRORS_ADMIN_400_409: dict[int | str, dict] = _admin(_protected({
    400: _ERROR, 409: _ERROR, 503: _STORAGE_503,
}))


_ERRORS_ADMIN_404_409: dict[int | str, dict] = _admin(_protected({
    404: _ERROR, 409: _ERROR, 503: _STORAGE_503,
}))


# Access-grant issuance: the target project must exist, but there is no project
# lifecycle conflict on this surface. Purge has its own 404/409 declaration.
_ERRORS_ADMIN_404: dict[int | str, dict] = _admin(_protected({
    404: _ERROR, 503: _STORAGE_503,
}))


_ERRORS_404_MIGRATION: dict[int | str, dict] = _protected(
    {404: _ERROR, 503: _MIGRATION_503}
)


_ERRORS_400_404_MIGRATION: dict[int | str, dict] = _protected({
    400: _ERROR, 404: _ERROR, 503: _MIGRATION_503,
})


_ERRORS_404_409_MIGRATION: dict[int | str, dict] = _protected({
    404: _ERROR, 409: _ERROR, 503: _MIGRATION_503,
})


# The analysis track's 503 is the *other* face: a collaborator the endpoint needs
# (the extraction runner, the compare judge) is absent from this deployment. The
# request is fine, so — like the migration face — retrying alone cannot help; the
# operator action is a deployment change. One constant covers both endpoints
# because the runtime ``detail`` already names which collaborator is missing, and
# the semantics are identical.
_CONFIG_503 = _with_storage_note({
    "model": ErrorDetailResponse,
    "description": "A collaborator this endpoint requires is not configured in "
                   "this deployment. Configure it in the deployment environment; "
                   "retrying the request alone cannot succeed.",
})


def _provider_error_status(error: ProviderError) -> int:
    """ProviderError → 이 API의 상태코드. **한 곳에만 둔다.**

    종전에는 이 매핑이 `504 if TIMEOUT else 502` 형태로 **9개 호출부에 복제**돼 있었다.
    K-3 창 가드가 세 번째 분기를 더하면서 복제본 하나만 놓쳐도 같은 사건이 endpoint마다
    다른 상태코드로 나가게 되므로 한 함수로 모았다.

    - `TIMEOUT` → **504**: 상류가 제때 답하지 않았다(v1.6.34 taxonomy).
    - `CONTEXT_WINDOW_EXCEEDED` → **400**: 창 가드가 **모델을 부르기 전에** 거부했다
      (K-3, 오너 2026-07-30). 상류 장애가 아니라 **요청이 너무 큰 것**이므로 4xx이며,
      같은 요청의 재시도는 반드시 같은 실패로 끝난다. `detail`이 입력·출력상한·창 수치를
      실어 나르므로 그 자체가 오너가 말한 "경고"다.
    - 그 밖의 provider 실패 → **502**: 상류는 있는데 실패했다. 여기에는 `KEY_REJECTED`
      (401/403 — 상류가 **우리의 API 키**를 거부, 오너 2026-08-22)가 포함된다: 이 API의
      클라이언트는 게이트웨이에 자격증명이 없으므로 401은 "너의 인증을 고쳐라"라는 거짓
      메시지가 된다.
    """
    if error.code is ProviderErrorCode.TIMEOUT:
        return 504
    if error.code is ProviderErrorCode.CONTEXT_WINDOW_EXCEEDED:
        return 400
    return 502


# 400은 K-3 창 가드가 이 endpoint에도 닿기 때문에 있다(오너 2026-07-30) — 요청이 창을
# 넘으면 모델을 부르기 전에 거부되고, 그 얼굴은 상류 장애(502)가 아니라 4xx다.
_ERRORS_404_502_CONFIG: dict[int | str, dict] = _protected({
    400: _ERROR, 404: _ERROR, 502: _ERROR, 503: _CONFIG_503,
})


_ERRORS_400_404_409_502_CONFIG: dict[int | str, dict] = _protected({
    400: _ERROR, 404: _ERROR, 409: _ERROR, 502: _ERROR, 503: _CONFIG_503,
})


# context-search is the only endpoint outside the writing track that can exhaust
# its own budget, so 504 first appears in the declared surface here.
_ERRORS_400_404_502_504_CONFIG: dict[int | str, dict] = _protected({
    400: _ERROR, 404: _ERROR, 502: _ERROR, 503: _CONFIG_503, 504: _ERROR,
})


# Slice 8.3: the same three declarations, plus the quota faces, for the nine
# billable operations. Separate constants rather than widening the ones above,
# because those are shared with free operations — adding 402/429 there would
# document a quota on endpoints that have none.
_BILLABLE_404_502_CONFIG: dict[int | str, dict] = _billable(
    _ERRORS_404_502_CONFIG)


_BILLABLE_400_404_409_502_CONFIG: dict[int | str, dict] = _billable(
    _ERRORS_400_404_409_502_CONFIG)


_BILLABLE_400_404_502_504_CONFIG: dict[int | str, dict] = _billable(
    _ERRORS_400_404_502_504_CONFIG)
