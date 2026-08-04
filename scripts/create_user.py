"""Create a user (bootstrap the first admin before the admin API exists).

The admin API is a later slice (D8 step 5), so this is the only way to mint the
first account. Password is read from the AUTH_BOOTSTRAP_PASSWORD environment
variable rather than argv so it does not land in shell history or `ps` output.

    AUTH_BOOTSTRAP_PASSWORD='...' \
    CORE_SOT_MONGO_URI=mongodb://localhost:27520 \
    python3 scripts/create_user.py <username> [--admin]
"""

from __future__ import annotations

import os
import sys

from datetime import UTC, datetime

from services.application.app.auth.password import Argon2PasswordHasher
from services.application.app.auth.users import DuplicateUsername, UserService
from services.application.app.auth.users_mongo import MongoUserRepository
from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
from services.application.app.quota.policy import (
    QuotaLimits,
    QuotaPolicy,
    QuotaStatus,
)
from services.application.app.quota.policy_mongo import MongoQuotaPolicyRepository


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    is_admin = "--admin" in argv[1:]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    username = args[0]

    password = os.environ.get("AUTH_BOOTSTRAP_PASSWORD")
    if not password:
        print("AUTH_BOOTSTRAP_PASSWORD is required", file=sys.stderr)
        return 2

    uri = os.environ.get("CORE_SOT_MONGO_URI")
    if not uri:
        # Refuse to run against the in-memory store: it would report success and
        # persist nothing.
        print("CORE_SOT_MONGO_URI is required", file=sys.stderr)
        return 2

    service = UserService(
        MongoUserRepository.from_uri(
            uri, db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
        ),
        hasher=Argon2PasswordHasher(),
    )
    try:
        user = service.create_user(
            username=username, password=password, is_admin=is_admin,
            # C-6: this password is chosen by whoever runs the script, not by the
            # account's owner, so it is single-use — the account replaces it at
            # first sign-in and cannot obtain a session until then.
            must_change_password=True,
        )
    except DuplicateUsername:
        print(f"user already exists: {username}", file=sys.stderr)
        return 1
    if is_admin:
        # 8.4 W1 (오너 2026-08-04): 첫 부트스트랩 관리자는 만들 때부터 무제한이다.
        # **면제는 코드가 아니라 데이터다** — `enforce_quota` 에는 tier 분기가 0줄이고
        # (그쪽은 회귀가 잠근다), 이 계정이 안 막히는 이유는 신분이 아니라 이 행이다.
        # 행을 지우면 이 계정도 기본 한도(일 20 / 주 100)를 받는다.
        #
        # `QuotaPolicyService.set_limits` 를 쓰지 않는 것은 의도적이다: P6 은 불리한
        # 변경을 주 경계로 유예하는데, 여기는 **신규 계정의 최초 상태**라 유예할
        # 이전 상태가 없다. 유예 경로를 타면 부트스트랩 관리자가 첫 주 동안 기본
        # 한도로 막힌다.
        policies = MongoQuotaPolicyRepository.from_uri(
            uri, db_name=os.environ.get("CORE_SOT_MONGO_DB", DEFAULT_DB_NAME)
        )
        policies.upsert(QuotaPolicy(
            user_id=user.id,
            limits=QuotaLimits(
                daily_limit=None, weekly_limit=None, status=QuotaStatus.ACTIVE),
            pending=None,
            updated_at=datetime.now(UTC),
        ))

    print(f"created {user.id} username={user.username} is_admin={user.is_admin}")
    if is_admin:
        print("관리자 계정이라 요청 quota 무제한 정책 행을 함께 만들었다"
              " (request_quota_policies, 8.4 W1).")
    print("이 비밀번호는 1회용이다 — 첫 로그인 때 새 비밀번호를 함께 보내야 세션이 발급된다"
          " (POST /auth/login 의 new_password).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
