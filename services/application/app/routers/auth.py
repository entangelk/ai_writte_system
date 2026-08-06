"""Auth + 회원 셀프서비스 route (``/auth/*`` · ``/me/quota``).

``main.py`` 의 ``create_app()`` 에서 옮겨온 register 함수(R1). handler 본문은
byte-동일이다 — 서비스(``users``·``sessions``)만 명시 인자로 받고, 공유 심볼은
``..main`` 과 ``auth.cookies`` 에서 가져온다.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, Response

from services.application.app.auth.cookies import SESSION_COOKIE_NAME, cookie_kwargs
from services.application.app.auth.users import InvalidUserInput

from ..api.models import (
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    MyQuotaResponse,
    UserPayload,
)
from ..api.errors import (
    _ERRORS_401,
    _ERRORS_LOGIN_409,
    _ERRORS_LOGOUT,
)
from ..api.dependencies import (
    _REQUIRE_AUTH,
    current_user_or_none,
    require_authenticated_user,
)
from services.application.app.quota.enforcement import QuotaEnforcementService


def register_auth(app, *, users, sessions) -> None:
    # --- Auth (multi-user D8) ---------------------------------------------
    # D8-3a: authentication is now enforced. Every operation except /health and
    # the three below declares ``dependencies=_REQUIRE_AUTH``, so a sessionless
    # request is 401 before the handler runs.
    #
    # The three exceptions each have a *stated* policy rather than an accident:
    #   /auth/login  — public: it is how a session is obtained.
    #   /auth/logout — public and idempotent: a client must always be able to
    #                  reach a known-logged-out state, including from a cookie
    #                  the server has already forgotten.
    #   /auth/me     — requires a session but answers 401 itself, because it is
    #                  the endpoint the frontend uses to *ask* whether it has one.
    #
    # Ownership (403) is enforced separately on every project-scoped route.

    def _user_payload(user) -> dict[str, object]:
        return {
            "id": user.id, "username": user.username, "is_admin": user.is_admin
        }

    @app.post("/auth/login", response_model=LoginResponse,
              responses=_ERRORS_LOGIN_409)
    async def login(request: LoginRequest, response: Response) -> dict[str, object]:
        user = users.authenticate(
            username=request.username, password=request.password
        )
        if user is None:
            # One message for every failure mode (unknown user, wrong password,
            # disabled account). Distinguishing them here would undo the timing
            # hardening in UserService.authenticate.
            raise HTTPException(status_code=401, detail="invalid credentials")
        # C-6 (owner 2026-08-02): an administrator-set password is single-use and
        # can only be spent on replacing itself. **Enforced here rather than on
        # every operation**: no session is issued at all, so the other 73
        # operations gain neither a check nor a new declared status — and the
        # "403 has exactly two producers" invariant stays intact.
        #
        # The credentials were already verified above, so this branch cannot be
        # used to probe: a wrong password is 401 whether or not a change is due.
        if user.must_change_password:
            if request.new_password is None:
                raise HTTPException(
                    status_code=409,
                    detail="password set by an administrator must be replaced "
                           "before signing in",
                )
            try:
                user = users.change_password(
                    user_id=user.id, new_password=request.new_password
                )
            except InvalidUserInput as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        elif request.new_password is not None:
            # Refused rather than ignored: a client that believes it changed the
            # password must not be told "ok" while nothing happened.
            raise HTTPException(
                status_code=409, detail="this account has no pending password change"
            )
        raw_token, session = sessions.create_session(user_id=user.id)
        max_age = int((session.expires_at - session.created_at).total_seconds())
        response.set_cookie(value=raw_token, **cookie_kwargs(max_age=max_age))
        return {"user": _user_payload(user)}

    @app.post("/auth/logout", response_model=LogoutResponse,
              responses=_ERRORS_LOGOUT)
    async def logout(request: Request, response: Response) -> dict[str, object]:
        # Idempotent by design: logging out without a session is not an error,
        # so a client can always reach a known-logged-out state.
        raw_token = request.cookies.get(SESSION_COOKIE_NAME)
        if raw_token:
            sessions.revoke(raw_token)
        response.delete_cookie(**cookie_kwargs())
        return {"ok": True}

    @app.get("/auth/me", response_model=UserPayload, responses=_ERRORS_401)
    async def read_current_user(request: Request) -> dict[str, object]:
        # Deliberately not `dependencies=_REQUIRE_AUTH`: this is the endpoint the
        # frontend calls to find out whether it has a session, so it must be able
        # to answer "no" as its own 401 rather than through a shared guard.
        user = current_user_or_none(request)
        if user is None:
            raise HTTPException(status_code=401, detail="not authenticated")
        return _user_payload(user)

    # --- Member self-service quota (Slice 8.4 W5=B) -----------------------
    # 시행은 8.3에서 켜졌고 화면은 그것을 볼 수 없었다 — 한도가 걸린 채 잔여를
    # 알 통로가 0개였다. 이 endpoint 가 그 구멍을 닫는다.
    #
    # ★ 집계를 여기서 새로 하지 않는다. 분자는 시행이 쓰는 ``effective_usage``,
    # 분모는 P6 예약을 해석하는 ``limits_for`` 이며 둘 다 ``snapshot()`` 한 곳을
    # 지난다 — 화면이 자기 나름대로 세면 "3회 남음"을 보여 준 직후 402 를 낸다.
    @app.get("/me/quota", response_model=MyQuotaResponse,
             responses=_ERRORS_401, dependencies=_REQUIRE_AUTH)
    async def read_my_quota(
        request: Request,
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        # `create_project` 과 같은 이유로 주체를 **dependency 가 이미 해석한 값**
        # 에서 받는다 — 쿠키를 다시 읽는 것은 "누구인가"에 대한 두 번째 답이다.
        enforcement: QuotaEnforcementService | None = getattr(
            request.app.state, "quota", None)
        if enforcement is None:
            # 시행이 조립되지 않은 배포에서 "무제한"이라 답하면 거짓말이 된다
            # (Q4=A 와 같은 방향: 계량 불능은 무료가 아니다).
            raise HTTPException(
                status_code=503, detail="request quota enforcement is not configured"
            )
        snapshot = enforcement.snapshot(
            user_id=current.id, member_created_at=current.created_at)
        return {
            "remaining": snapshot.remaining,
            "unlimited": snapshot.unlimited,
            "status": snapshot.status.value,
            "daily": {
                "limit": snapshot.daily_limit,
                "used": snapshot.daily_used,
                "remaining": snapshot.daily_remaining,
                "resets_at": snapshot.daily_resets_at,
            },
            "weekly": {
                "limit": snapshot.weekly_limit,
                "used": snapshot.weekly_used,
                "remaining": snapshot.weekly_remaining,
                "resets_at": snapshot.weekly_resets_at,
            },
        }
