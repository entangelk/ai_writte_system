"""부트스트랩 계정 생성 스크립트의 quota 계약 (Slice 8.4 W1, 오너 결정 2026-08-04).

오너 문언: *"면제 없음이되, 첫 시작 어드민 계정 만들 때부터 리미트 없이 none으로
바로 갈 수 있도록."* 그 결정의 형태가 여기서 정해진다 —

- 면제는 **코드의 tier 분기가 아니라 정책 행 하나**다. `enforce_quota` 는 여전히
  `is_admin` 을 보지 않는다(그쪽 over-strict 는 `test_quota_enforcement_api.py`).
- 그러므로 이 스크립트가 관리자를 만들 때 `limit=None` 행을 **함께** 쓴다.
- **일반 계정은 받지 않는다.** 받으면 "부트스트랩으로 만든 계정은 무제한"이 되어
  W1=A 가 거부한 자리로 돌아간다.

`must_change_password=True`(C-6)는 별개 축이며 `test_auth_api.py` 의 AST 가드가
지킨다 — 여기서 다시 재지 않는다.
"""

from __future__ import annotations

import unittest
from unittest import mock

from services.application.app.auth.models import User
from services.application.app.quota.policy import QuotaStatus


class _FakeUserRepo:
    def __init__(self) -> None:
        self.saved: list[User] = []

    @classmethod
    def from_uri(cls, _uri, *, db_name=None):  # noqa: ARG003
        return cls()


class _FakePolicyRepo:
    """`upsert` 만 받는다 — 스크립트가 정책을 **읽을** 이유는 없다."""

    instances: list["_FakePolicyRepo"] = []

    def __init__(self) -> None:
        self.upserted: list = []
        type(self).instances.append(self)

    @classmethod
    def from_uri(cls, _uri, *, db_name=None):  # noqa: ARG003
        return cls()

    def get(self, _user_id):
        return None

    def upsert(self, policy) -> None:
        self.upserted.append(policy)


def _run(argv: list[str]):
    """스크립트를 fake 저장소로 돌리고 (종료코드, 정책 upsert 목록) 을 돌려준다."""

    from scripts import create_user  # noqa: PLC0415

    _FakePolicyRepo.instances = []
    created: dict[str, User] = {}

    class _Service:
        def __init__(self, _repo, *, hasher):  # noqa: ARG002
            pass

        def create_user(self, *, username, password, is_admin, must_change_password):  # noqa: ARG002
            user = User(
                id="u-bootstrap", username=username, password_hash="hashed",
                is_admin=is_admin, is_active=True,
                created_at=__import__("datetime").datetime.now(
                    __import__("datetime").UTC),
            )
            created["user"] = user
            return user

    env = {
        "AUTH_BOOTSTRAP_PASSWORD": "correct-horse-battery",
        "CORE_SOT_MONGO_URI": "mongodb://localhost:27520",
    }
    with mock.patch.dict("os.environ", env, clear=False), \
            mock.patch.object(create_user, "UserService", _Service), \
            mock.patch.object(
                create_user, "MongoUserRepository", _FakeUserRepo), \
            mock.patch.object(
                create_user, "MongoQuotaPolicyRepository", _FakePolicyRepo), \
            mock.patch.object(create_user, "Argon2PasswordHasher", lambda: None):
        code = create_user.main(argv)
    upserts = [p for repo in _FakePolicyRepo.instances for p in repo.upserted]
    return code, upserts, created.get("user")


class BootstrapAdminQuotaTest(unittest.TestCase):
    def test_an_admin_gets_an_unlimited_policy_row(self) -> None:
        code, upserts, user = _run(["create_user.py", "root", "--admin"])
        self.assertEqual(code, 0)
        self.assertEqual(len(upserts), 1)
        policy = upserts[0]
        self.assertEqual(policy.user_id, user.id)
        self.assertIsNone(policy.limits.daily_limit)
        self.assertIsNone(policy.limits.weekly_limit)
        self.assertIs(policy.limits.status, QuotaStatus.ACTIVE)
        # 예약 변경 없이 **지금** 유효해야 한다 — P6 유예를 타면 부트스트랩 관리자가
        # 첫 주 동안 기본 한도로 막힌다(그러면 이 결정이 아무것도 안 한 셈이다).
        self.assertIsNone(policy.pending)

    def test_a_non_admin_account_gets_no_policy_row(self) -> None:
        # over-strict 짝. 여기서 행을 쓰면 "스크립트로 만든 계정은 무제한"이 되어
        # W1=A(면제 없음)가 우회된다 — 오너 문언은 **어드민** 계정이었다.
        code, upserts, _user = _run(["create_user.py", "writer"])
        self.assertEqual(code, 0)
        self.assertEqual(upserts, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
