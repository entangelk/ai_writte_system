"""Auth + 회원 셀프서비스 route (``/auth/*`` · ``/me/quota`` · ``/me/activity``).

``main.py`` 의 ``create_app()`` 에서 옮겨온 register 함수(R1). handler 본문은
byte-동일이다 — 서비스(``users``·``sessions``)만 명시 인자로 받고, 공유 심볼은
``..main`` 과 ``auth.cookies`` 에서 가져온다.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, Response

from services.application.app.auth.cookies import SESSION_COOKIE_NAME, cookie_kwargs

from ..api.models import (
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    MyQuotaResponse,
    PersonalActivityLogResponse,
    SignupRequest,
    SignupResponse,
    UserPayload,
)
from ..api.errors import (
    _ERRORS_401,
    _ERRORS_LOGIN,
    _ERRORS_LOGOUT,
    _ERRORS_SIGNUP,
)
from ..auth.users import (
    DuplicateUsername,
    InvalidUserInput,
    SignupQueueFull,
    USER_STATUS_PENDING,
    USER_STATUS_REJECTED,
)
from ..api.dependencies import (
    _REQUIRE_AUTH,
    current_user_or_none,
    require_authenticated_user,
)
from services.application.app.quota.enforcement import QuotaEnforcementService


def register_auth(app, *, users, sessions, core_sot, activity, login_guard,
                  signup_throttle, client_ip_resolver) -> None:
    # --- Auth (multi-user D8) ---------------------------------------------
    # D8-3a: authentication is now enforced. Every operation except /health and
    # the three below declares ``dependencies=_REQUIRE_AUTH``, so a sessionless
    # request is 401 before the handler runs.
    #
    # The three exceptions each have a *stated* policy rather than an accident:
    #   /auth/login  — public: it is how a session is obtained.
    #   /auth/signup — public (2026-08-22): requesting an account is how an
    #                  account begins to exist. It grants nothing — the row is
    #                  pending until an administrator approves it.
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

    @app.post("/auth/signup", status_code=201, response_model=SignupResponse,
              responses=_ERRORS_SIGNUP)
    async def signup(
        request: SignupRequest, http_request: Request
    ) -> dict[str, object]:
        # Public by design (owner 2026-08-22): requesting an account is how an
        # account begins to exist. What the request *grants* is nothing — the
        # row is pending and no session can be issued against it until an
        # administrator approves (1-d).
        #
        # Phase S-3 (owner 2026-09-05, option C): what the request *costs* was
        # the hole. Argon2 (t=3·m=64MiB·p=4) runs before any approval and the
        # deployed app is a single uvicorn worker, so an unauthenticated caller
        # could stall the whole service without ever holding an account. The
        # throttle answers **before** `request_signup` so a refused attempt
        # never reaches the hasher — that cheapness is the entire defense.
        client_ip = client_ip_resolver.resolve(
            peer=http_request.client.host if http_request.client else None,
            forwarded_for=http_request.headers.get("x-forwarded-for"),
        )
        retry_after = signup_throttle.consume(client_ip)
        if retry_after is not None:
            raise HTTPException(
                status_code=429,
                detail="too many signup requests",
                headers={"Retry-After": str(retry_after)},
            )
        try:
            user = users.request_signup(
                username=request.username, password=request.password
            )
        except DuplicateUsername as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except SignupQueueFull as exc:
            # Same 429 face as the throttle above (S-3): "not now" either way.
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except InvalidUserInput as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"username": user.username, "status": user.status}

    @app.post("/auth/login", response_model=LoginResponse,
              responses=_ERRORS_LOGIN)
    async def login(request: LoginRequest, response: Response) -> dict[str, object]:
        username = request.username.strip()
        # Brute-force bound (P-6, 2026-08-22): checked before Argon2 runs, and
        # the answer is the unified 401 — whether an account is locked is a
        # state the attacker's own failures created, so nothing new leaks.
        if login_guard.is_locked(username):
            raise HTTPException(status_code=401, detail="invalid credentials")
        user = users.authenticate(
            username=request.username, password=request.password
        )
        if user is None:
            # One message for every failure mode (unknown user, wrong password,
            # disabled account). Distinguishing them here would undo the timing
            # hardening in UserService.authenticate.
            login_guard.register_failure(username)
            raise HTTPException(status_code=401, detail="invalid credentials")
        # Credentials verified from here on — every path below proves the caller
        # holds the right password, so the failure counter clears (the guard
        # slows password *guessing*, not legitimate sign-ins).
        login_guard.register_success(username)
        # Signup approval gate (P-4): checked only *after* credentials verify,
        # so a wrong password on a pending account is a plain 401 — the status
        # is visible to nobody who does not already hold the right password
        # (owner 2026-08-22: the 403 is effectively addressed to the account
        # owner alone). The two details are consumed by the login screen (1-e);
        # this is the one enrolled exception to H3's "never branch on detail".
        if user.status == USER_STATUS_PENDING:
            raise HTTPException(
                status_code=403, detail="account approval pending"
            )
        if user.status == USER_STATUS_REJECTED:
            raise HTTPException(
                status_code=403, detail="signup request rejected"
            )
        # C-6 (owner 2026-08-02): an administrator-set password is single-use and
        # can only be spent on replacing itself. **Enforced here rather than on
        # every operation**: no session is issued at all, so the other 73
        # operations gain neither a check nor a new declared status — and 403's
        # producers stay exactly three (ownership · admin · signup status above).
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

    @app.get("/me/activity", response_model=PersonalActivityLogResponse,
             responses=_ERRORS_401, dependencies=_REQUIRE_AUTH)
    async def read_my_activity(
        current=Depends(require_authenticated_user),
    ) -> dict[str, object]:
        # Slice 9.2 P1=ⓐ (operation 78). 개인 허브가 "내 것들에 무슨 일이 있었나"에
        # 한 번의 요청으로 답한다.
        #
        # **★ P8=ⓐ 소유 기준이며 그 범위는 여기서만 정해진다.** 경로가 project id 를
        # 받지 않는 것이 S-3 이다 — 남의 프로젝트를 요청할 문법 자체가 없고, 주체는
        # 세션이 해석한 값에서만 온다(``create_project``·``/me/quota`` 와 같은 이유:
        # 쿠키를 다시 읽는 것은 "누구인가"에 대한 두 번째 답이다).
        #
        # **오너 확정(2026-08-10): 다중 사용자가 되어도 범위는 소유 기준이다.** 그때
        # 바뀌는 것은 범위가 아니라 **표시**이며(F4 = 행위자 열), 여기를 actor 기준으로
        # 뒤집는 것이 아니다.
        owned = core_sot.list_projects_for_owner(owner_id=current.id)
        events = activity.list_for_projects(
            project_ids=tuple(project.id for project in owned))
        return {"events": [
            {
                "id": event.id,
                "project_id": event.project_id,
                "actor_user_id": event.actor_user_id,
                "action": event.action,
                "target_type": event.target_type,
                "target_id": event.target_id,
                "at": event.at,
                "before": event.before,
                "after": event.after,
            }
            for event in events
        ]}
