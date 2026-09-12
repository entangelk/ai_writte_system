"""UserService with a fake hasher and the in-memory repository."""

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from services.application.app.auth.models import User
from services.application.app.auth.users import (
    DuplicateUsername, InMemoryUserRepository, InvalidUserInput,
    LastActiveAdmin, SignupNotPending, UserNotFound, UserService,
    WITHDRAWAL_GRACE_PERIOD, WithdrawalNotRequested,
    is_purge_due, purge_due_at,
    TERMS_VERSION,
    USER_STATUS_ACTIVE, USER_STATUS_PENDING, USER_STATUS_REJECTED,
)

_FIXED_TIME = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


class _FakeHasher:
    """Deterministic stand-in so service tests never pay Argon2's cost. The real
    primitive is covered in test_auth_password.py.

    Records verify() calls: the timing-side enumeration guard is only observable
    as "was a verify performed at all", so a fake that forgets its calls cannot
    lock it (that gap was the verification's B-1)."""

    def __init__(self) -> None:
        self.verify_calls: list[tuple[str, str]] = []

    def hash(self, password: str) -> str:
        return "H:" + password

    def verify(self, stored_hash: str, password: str) -> bool:
        self.verify_calls.append((stored_hash, password))
        return stored_hash == "H:" + password


def _seq_ids():
    counter = {"n": 0}

    def factory() -> str:
        counter["n"] += 1
        return f"user:{counter['n']}"

    return factory


def _service(
    repo: InMemoryUserRepository | None = None,
    hasher: _FakeHasher | None = None,
) -> UserService:
    return UserService(
        repo or InMemoryUserRepository(),
        hasher=hasher or _FakeHasher(),
        clock=lambda: _FIXED_TIME,
        id_factory=_seq_ids(),
    )


class CreateUserTest(unittest.TestCase):
    def test_stores_hashed_password_not_plaintext(self) -> None:
        service = _service()
        user = service.create_user(username="alice", password="pw123")
        self.assertEqual(user.username, "alice")
        # Delegated to the hasher (fake = "H:"+pw), not stored raw. The real
        # not-plaintext property is proven in test_auth_password.py.
        self.assertEqual(user.password_hash, "H:pw123")
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_admin)
        self.assertEqual(user.id, "user:1")
        self.assertEqual(user.created_at, _FIXED_TIME)

    def test_is_admin_flag_is_honored(self) -> None:
        user = _service().create_user(
            username="root", password="pw", is_admin=True
        )
        self.assertTrue(user.is_admin)

    def test_username_is_stripped(self) -> None:
        user = _service().create_user(username="  bob  ", password="pw")
        self.assertEqual(user.username, "bob")

    def test_duplicate_username_rejected(self) -> None:
        repo = InMemoryUserRepository()
        _service(repo).create_user(username="alice", password="pw")
        with self.assertRaises(DuplicateUsername):
            _service(repo).create_user(username="alice", password="other")

    def test_empty_username_rejected(self) -> None:
        for bad in ("", "   "):
            with self.assertRaises(InvalidUserInput):
                _service().create_user(username=bad, password="pw")

    def test_empty_password_rejected(self) -> None:
        with self.assertRaises(InvalidUserInput):
            _service().create_user(username="alice", password="")


class AuthenticateTest(unittest.TestCase):
    def test_correct_credentials_return_user(self) -> None:
        repo = InMemoryUserRepository()
        created = _service(repo).create_user(username="alice", password="pw123")
        got = _service(repo).authenticate(username="alice", password="pw123")
        self.assertEqual(got, created)

    def test_wrong_password_returns_none(self) -> None:
        repo = InMemoryUserRepository()
        _service(repo).create_user(username="alice", password="pw123")
        self.assertIsNone(
            _service(repo).authenticate(username="alice", password="nope")
        )

    def test_unknown_username_returns_none(self) -> None:
        self.assertIsNone(
            _service().authenticate(username="ghost", password="pw")
        )

    def test_inactive_user_cannot_authenticate(self) -> None:
        repo = InMemoryUserRepository()
        repo.insert(
            User(
                id="user:x", username="alice", password_hash="H:pw123",
                is_admin=False, is_active=False, created_at=_FIXED_TIME,
            )
        )
        # Right password, but disabled account (admin-disable, D6) must not log in.
        self.assertIsNone(
            _service(repo).authenticate(username="alice", password="pw123")
        )

    def test_username_stripped_on_authenticate(self) -> None:
        repo = InMemoryUserRepository()
        _service(repo).create_user(username="alice", password="pw123")
        self.assertIsNotNone(
            _service(repo).authenticate(username="  alice ", password="pw123")
        )


class EnumerationHardeningTest(unittest.TestCase):
    """`UserService.authenticate` runs a dummy verify for unknown/disabled
    accounts so they cost the same as a wrong password.

    Without it, Argon2's deliberate slowness makes a missing username measurably
    faster than a wrong password, which leaks which usernames exist. The failure
    is invisible to assertIsNone-style tests (all three cases return None either
    way), so it has to be locked on "was a verify actually performed".
    """

    def _run(self, *, username, password, seeded_active=True):
        repo = InMemoryUserRepository()
        hasher = _FakeHasher()
        _service(repo, hasher).create_user(username="alice", password="pw123")
        if not seeded_active:
            stored = repo.get_by_username("alice")
            repo._by_id[stored.id] = replace(stored, is_active=False)
        hasher.verify_calls.clear()  # ignore setup work
        result = _service(repo, hasher).authenticate(
            username=username, password=password
        )
        return result, hasher

    def test_unknown_and_disabled_cost_the_same_verify_as_a_wrong_password(self):
        # The property itself: all three failures perform the same amount of
        # hashing work. Deleting the dummy verify makes the unknown/disabled
        # counts drop to 0 and this fails.
        wrong, wrong_hasher = self._run(username="alice", password="WRONG")
        unknown, unknown_hasher = self._run(username="ghost", password="WRONG")
        disabled, disabled_hasher = self._run(
            username="alice", password="pw123", seeded_active=False
        )
        self.assertIsNone(wrong)
        self.assertIsNone(unknown)
        self.assertIsNone(disabled)

        self.assertEqual(len(wrong_hasher.verify_calls), 1)
        self.assertEqual(
            len(unknown_hasher.verify_calls), len(wrong_hasher.verify_calls)
        )
        self.assertEqual(
            len(disabled_hasher.verify_calls), len(wrong_hasher.verify_calls)
        )

    def test_dummy_verify_uses_a_throwaway_hash_not_a_real_users(self):
        # Over-strict guard. Equalizing the cost by verifying against a *real*
        # stored hash would let a lucky password match a disabled account, and
        # for the unknown-user case there is no real hash to use anyway. The
        # guard hash must be a throwaway no password can match.
        _, hasher = self._run(username="ghost", password="pw123")
        (guard_hash, attempted_password), = hasher.verify_calls
        self.assertEqual(attempted_password, "pw123")
        self.assertNotEqual(guard_hash, "H:pw123")

    def test_successful_login_still_verifies_against_the_stored_hash(self):
        # Over-strict guard in the other direction: the guard must not replace
        # the real check. A correct password must verify against what was stored.
        repo = InMemoryUserRepository()
        hasher = _FakeHasher()
        created = _service(repo, hasher).create_user(
            username="alice", password="pw123"
        )
        hasher.verify_calls.clear()
        self.assertIsNotNone(
            _service(repo, hasher).authenticate(username="alice", password="pw123")
        )
        self.assertEqual(hasher.verify_calls, [(created.password_hash, "pw123")])


class ListAndDeactivateTest(unittest.TestCase):
    """D8-5 admin operations at the service layer."""

    def setUp(self) -> None:
        self.repo = InMemoryUserRepository()
        self.service = _service(self.repo)

    def test_list_users_is_empty_before_anyone_is_created(self) -> None:
        self.assertEqual(self.service.list_users(), ())

    def test_list_users_returns_every_account(self) -> None:
        alice = self.service.create_user(username="alice", password="pw")
        root = self.service.create_user(
            username="root", password="pw", is_admin=True
        )
        self.assertEqual(self.service.list_users(), (alice, root))

    def test_deactivating_flips_the_flag_in_the_store(self) -> None:
        alice = self.service.create_user(username="alice", password="pw")

        updated = self.service.deactivate_user(alice.id)

        self.assertFalse(updated.is_active)
        self.assertFalse(self.repo.get_by_id(alice.id).is_active)

    def test_a_deactivated_user_can_no_longer_authenticate(self) -> None:
        # The reason the flag exists. `authenticate` already refused inactive
        # accounts; this pins that deactivation actually reaches that path.
        alice = self.service.create_user(username="alice", password="pw")
        self.service.deactivate_user(alice.id)

        self.assertIsNone(
            self.service.authenticate(username="alice", password="pw")
        )

    def test_deactivating_an_unknown_user_raises(self) -> None:
        with self.assertRaises(UserNotFound):
            self.service.deactivate_user("user:ghost")

    def test_the_last_active_admin_is_refused(self) -> None:
        # F2=A: the invariant is about the population of active admins, so this
        # fires even though the request names a perfectly valid user.
        root = self.service.create_user(
            username="root", password="pw", is_admin=True
        )
        self.service.create_user(username="alice", password="pw")

        with self.assertRaises(LastActiveAdmin):
            self.service.deactivate_user(root.id)

        self.assertTrue(self.repo.get_by_id(root.id).is_active)

    def test_a_second_active_admin_makes_the_first_removable(self) -> None:
        # Over-strict: admins are not undeletable, they are merely not
        # extinguishable. A rule that always refused would pass the test above.
        root = self.service.create_user(
            username="root", password="pw", is_admin=True
        )
        self.service.create_user(username="root2", password="pw", is_admin=True)

        self.assertFalse(self.service.deactivate_user(root.id).is_active)

    def test_an_inactive_admin_does_not_keep_the_last_one_removable(self) -> None:
        # Counting admins instead of *active* admins would allow the lockout.
        root = self.service.create_user(
            username="root", password="pw", is_admin=True
        )
        second = self.service.create_user(
            username="root2", password="pw", is_admin=True
        )
        self.service.deactivate_user(second.id)

        with self.assertRaises(LastActiveAdmin):
            self.service.deactivate_user(root.id)

    def test_deactivating_an_already_inactive_admin_is_allowed(self) -> None:
        # Idempotence at the boundary: the guard asks whether *this* account is
        # currently holding the deployment's last admin seat. An already
        # disabled one is not, so repeating the call must not start failing.
        root = self.service.create_user(
            username="root", password="pw", is_admin=True
        )
        self.service.create_user(username="root2", password="pw", is_admin=True)
        self.service.deactivate_user(root.id)

        self.assertFalse(self.service.deactivate_user(root.id).is_active)

    def test_a_non_admin_is_never_blocked_by_the_admin_rule(self) -> None:
        # The only user in the deployment, but not an admin: the rule must not
        # generalize into "the last user cannot be disabled".
        alice = self.service.create_user(username="alice", password="pw")

        self.assertFalse(self.service.deactivate_user(alice.id).is_active)


class SignupApprovalTest(unittest.TestCase):
    """관리자 승인·거절 (슬라이스 1-d, P-7).

    under-strict: 이미 처리된 요청이 다시 승인되면(상태 재변경) 짝 셀이 실패한다.
    over-strict: pending 아닌 것까지 거부하며 정상 승인을 막으면 첫 셀이 실패한다.
    """

    def setUp(self) -> None:
        self.repo = InMemoryUserRepository()
        self.hasher = _FakeHasher()
        # One id factory across every service this test builds: two factories
        # each start at user:1 and later writes silently overwrite earlier rows.
        self.ids = _seq_ids()
        self.service = UserService(
            self.repo, hasher=self.hasher,
            clock=lambda: _FIXED_TIME, id_factory=self.ids,
        )

    def _pending(self, username: str):
        return self.service.request_signup(
            username=username, password="long-enough-pw",
            agreed_terms_version=TERMS_VERSION,
        )

    def test_approval_moves_pending_to_active(self) -> None:
        pending = self._pending("bob")
        approved = self.service.approve_signup(pending.id)
        self.assertEqual(approved.status, USER_STATUS_ACTIVE)

    def test_rejection_moves_pending_to_rejected(self) -> None:
        pending = self._pending("bob")
        rejected = self.service.reject_signup(pending.id)
        self.assertEqual(rejected.status, USER_STATUS_REJECTED)

    def test_an_approved_request_cannot_be_approved_twice(self) -> None:
        pending = self._pending("bob")
        self.service.approve_signup(pending.id)
        with self.assertRaises(SignupNotPending):
            self.service.approve_signup(pending.id)

    def test_an_approved_request_cannot_be_rejected_afterwards(self) -> None:
        # The invariant that keeps session semantics sane: no resolved account
        # ever changes status again. Deactivation is the one-way door for
        # active accounts, not rejection.
        pending = self._pending("bob")
        self.service.approve_signup(pending.id)
        with self.assertRaises(SignupNotPending):
            self.service.reject_signup(pending.id)

    def test_an_admin_created_account_is_not_approvable(self) -> None:
        # Administrator-created rows are active from birth (pre-signup rows
        # read back active); approval only ever targets signup requests.
        admin_made = self.service.create_user(username="carol", password="pw123")
        with self.assertRaises(SignupNotPending):
            self.service.approve_signup(admin_made.id)

    def test_approving_an_unknown_user_raises_not_found(self) -> None:
        with self.assertRaises(UserNotFound):
            self.service.approve_signup("user:ghost")

    def test_pending_list_shows_only_pending_oldest_first(self) -> None:
        later = datetime(2026, 8, 23, 8, 0, tzinfo=UTC)
        first = self._pending("bob")
        second = UserService(
            self.repo, hasher=self.hasher,
            clock=lambda: later, id_factory=self.ids,
        ).request_signup(
            username="dave", password="long-enough-pw",
            agreed_terms_version=TERMS_VERSION,
        )
        # An active account and a rejected row must not appear in the queue.
        self.service.create_user(username="admin", password="pw123")
        rejected = self._pending("erin")
        self.service.reject_signup(rejected.id)

        queue = self.service.list_pending_signups()
        self.assertEqual([u.username for u in queue], ["bob", "dave"])
        self.assertEqual(queue[0].id, first.id)
        self.assertEqual(queue[1].id, second.id)


class SignupRequestTest(unittest.TestCase):
    """승인제 가입 요청 (2026-08-22, plans/auth-signup-approval-decisions.md P-2·P-3).

    under-strict 방향: 요청이 active 행을 만들면(승인 우회) 1·7번 셀이 실패한다.
    over-strict 방향: rejected 재요청을 막거나(5) deactivated 행을 되살리면(6)
    실패한다 — 거절은 밴이 아니고 비활성화는 단방향이다.
    """

    def setUp(self) -> None:
        self.repo = InMemoryUserRepository()
        self.hasher = _FakeHasher()
        self.service = UserService(
            self.repo, hasher=self.hasher,
            clock=lambda: _FIXED_TIME, id_factory=_seq_ids(),
        )

    def test_a_signup_request_creates_a_pending_row(self) -> None:
        user = self.service.request_signup(
            username="bob", password="long-enough-pw",
            agreed_terms_version=TERMS_VERSION,
        )
        self.assertEqual(user.status, USER_STATUS_PENDING)
        # The request grants nothing: enabled as a row, but not sign-in-able and
        # carrying no administrator flag and no forced-change flag (the
        # requester owns the password from the start — no C-6 flow).
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_admin)
        self.assertFalse(user.must_change_password)
        self.assertEqual(user.password_hash, "H:long-enough-pw")

    def test_a_short_password_is_refused(self) -> None:
        with self.assertRaises(InvalidUserInput):
            self.service.request_signup(
                username="bob", password="short",
                agreed_terms_version=TERMS_VERSION,
            )
        # Nothing was written — the refusal is not a pending row.
        self.assertIsNone(self.repo.get_by_username("bob"))

    def test_an_empty_username_is_refused(self) -> None:
        with self.assertRaises(InvalidUserInput):
            self.service.request_signup(
                username="  ", password="long-enough-pw",
                agreed_terms_version=TERMS_VERSION,
            )

    def test_an_active_username_cannot_be_requested(self) -> None:
        self.service.create_user(username="alice", password="pw123")
        with self.assertRaises(DuplicateUsername):
            self.service.request_signup(
                username="alice", password="long-enough-pw",
                agreed_terms_version=TERMS_VERSION,
            )

    def test_a_pending_username_cannot_be_requested_twice(self) -> None:
        self.service.request_signup(
            username="bob", password="long-enough-pw",
            agreed_terms_version=TERMS_VERSION,
        )
        with self.assertRaises(DuplicateUsername):
            self.service.request_signup(
                username="bob", password="another-long-pw",
                agreed_terms_version=TERMS_VERSION,
            )

    def test_a_rejected_username_can_be_re_requested(self) -> None:
        first = self.service.request_signup(
            username="bob", password="long-enough-pw",
            agreed_terms_version=TERMS_VERSION,
        )
        # An admin's rejection (1-d writes this via set_status; simulated here
        # because this slice's domain only owns the request side).
        rejected = User(
            id=first.id, username=first.username,
            password_hash=first.password_hash, is_admin=False,
            is_active=True, created_at=first.created_at,
            must_change_password=False, status=USER_STATUS_REJECTED,
        )
        self.repo.replace(rejected)

        later = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
        second = UserService(
            self.repo, hasher=self.hasher,
            clock=lambda: later, id_factory=_seq_ids(),
        ).request_signup(
            username="bob", password="different-long-pw",
            agreed_terms_version=TERMS_VERSION,
        )

        # Same row overwritten (not a second row), fresh request evidence:
        # new hash, new created_at, back to pending.
        self.assertEqual(second.id, first.id)
        self.assertEqual(second.status, USER_STATUS_PENDING)
        self.assertEqual(second.password_hash, "H:different-long-pw")
        self.assertEqual(second.created_at, later)
        self.assertEqual(
            [u.username for u in self.repo.list_all()], ["bob"]
        )

    def test_a_deactivated_rejected_row_is_not_resurrected(self) -> None:
        first = self.service.request_signup(
            username="bob", password="long-enough-pw",
            agreed_terms_version=TERMS_VERSION,
        )
        deactivated_and_rejected = User(
            id=first.id, username=first.username,
            password_hash=first.password_hash, is_admin=False,
            is_active=False, created_at=first.created_at,
            must_change_password=False, status=USER_STATUS_REJECTED,
        )
        self.repo.replace(deactivated_and_rejected)
        # Deactivation is one-way (D6=A): a re-request must not flip is_active
        # back — that would make signup an un-deactivation surface.
        with self.assertRaises(DuplicateUsername):
            self.service.request_signup(
                username="bob", password="yet-another-long-pw",
                agreed_terms_version=TERMS_VERSION,
            )
        self.assertFalse(self.repo.get_by_username("bob").is_active)

    def test_a_replacement_row_is_never_an_admin(self) -> None:
        first = self.service.request_signup(
            username="bob", password="long-enough-pw",
            agreed_terms_version=TERMS_VERSION,
        )
        rejected_admin = User(
            id=first.id, username=first.username,
            password_hash=first.password_hash, is_admin=True,
            is_active=True, created_at=first.created_at,
            must_change_password=False, status=USER_STATUS_REJECTED,
        )
        self.repo.replace(rejected_admin)
        second = self.service.request_signup(
            username="bob", password="long-enough-pw-2",
            agreed_terms_version=TERMS_VERSION,
        )
        self.assertFalse(second.is_admin)


class SignupConsentGateTest(unittest.TestCase):
    """가입 동의 게이트 (방침 제3조, 오너 2026-09-07 · 구현 2026-09-12).

    계약은 방침 문장 그대로다: *가입 절차에서 확인하고 동의*하며, 운영자는
    **동의한 시각과 동의한 문서의 버전을 기록**한다.

    under-strict 방향: 동의 축이 없어도(2번) 시행 버전과 다른 청구이면(3번)
    가입이 되면 실패한다 — 게이트가 없는 것이므로.
    over-strict 방향: 동의한 정상 가입에서 스탬프가 안 찍히거나(1번) 관리자가
    만든 계정에 소급으로 동의가 박히면(5번) 실패한다 — 소급 동의를 받지
    않는다는 방침 제3조 안내 상자와 어긋난다.
    """

    def setUp(self) -> None:
        self.repo = InMemoryUserRepository()
        self.hasher = _FakeHasher()
        self.service = UserService(
            self.repo, hasher=self.hasher,
            clock=lambda: _FIXED_TIME, id_factory=_seq_ids(),
        )

    def test_consent_is_stamped_with_the_server_clock_and_version(self) -> None:
        user = self.service.request_signup(
            username="bob", password="long-enough-pw",
            agreed_terms_version=TERMS_VERSION,
        )
        # 시각은 서버 시계다 — 클라이언트가 시각을 보낸 적도 없고, 보냈다면
        # 그 값을 믿는 이유가 없다. 버전은 서버 상수다(아래 3번과 짝).
        self.assertEqual(user.terms_agreed_at, _FIXED_TIME)
        self.assertEqual(user.terms_version_agreed, TERMS_VERSION)

    def test_a_signup_without_a_version_is_refused(self) -> None:
        with self.assertRaises(InvalidUserInput):
            self.service.request_signup(
                username="bob", password="long-enough-pw",
            )
        # 거절은 행을 남기지 않는다 — 동의 없는 pending 행이 생기면 그 행의
        # 승인은 "동의한 적 없는 계정"을 만든다.
        self.assertIsNone(self.repo.get_by_username("bob"))

    def test_a_stale_version_claim_is_refused(self) -> None:
        # 게이트가 보여 준 문서가 서버가 시행하는 판본이 아닌 순간의 요청이다
        # (옛 캐시의 폼). 동의의 대상이 무엇이었는지 서버가 보증할 수 없으므로
        # 가입 자체를 거부한다 — 저장을 서버 상수로 대체하는 것으로는 부족하다.
        with self.assertRaises(InvalidUserInput):
            self.service.request_signup(
                username="bob", password="long-enough-pw",
                agreed_terms_version="0.9",
            )
        self.assertIsNone(self.repo.get_by_username("bob"))

    def test_a_re_request_stamps_a_fresh_consent(self) -> None:
        first = self.service.request_signup(
            username="bob", password="long-enough-pw",
            agreed_terms_version=TERMS_VERSION,
        )
        # 재요청은 거절된 username 에만 열린다(위 SignupRequestTest 5번 축).
        rejected = User(
            id=first.id, username=first.username,
            password_hash=first.password_hash, is_admin=False,
            is_active=True, created_at=first.created_at,
            must_change_password=False, status=USER_STATUS_REJECTED,
        )
        self.repo.replace(rejected)
        later = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)
        second = UserService(
            self.repo, hasher=self.hasher,
            clock=lambda: later, id_factory=_seq_ids(),
        ).request_signup(
            username="bob", password="different-long-pw",
            agreed_terms_version=TERMS_VERSION,
        )
        # 재요청은 새 가입이다 — 거절된 옛 행이 동의를 남긴 적 없다면(None
        # 이라기보다는 이 테스트에서는 첫 동의가 있었지만) 스탬프는 재요청
        # 시각으로 다시 찍힌다. 첫 동의 시각이 승계되면 재요청자가 옛 판본에
        # 동의한 것으로 기록된 채 계정이 열린다.
        self.assertEqual(second.id, first.id)
        self.assertEqual(second.terms_agreed_at, later)
        self.assertEqual(second.terms_version_agreed, TERMS_VERSION)

    def test_an_admin_created_account_carries_no_consent(self) -> None:
        # 소급 동의를 받지 않는다(방침 제3조 안내 상자). 관리자가 만든 계정과
        # 게이트 이전 계정의 None 은 "동의하지 않은 인구"라는 방침적 사실이지
        # 결함이 아니다 — 이 셀은 그 축이 게이트에 의해 조용히 채워지지
        # 않는지를 잠근다.
        made = self.service.create_user(username="carol", password="pw123")
        self.assertIsNone(made.terms_agreed_at)
        self.assertIsNone(made.terms_version_agreed)


class WithdrawalGracePeriodLiteralTest(unittest.TestCase):
    """유예 기간 30일은 오너가 고른 계약 리터럴이다(2026-09-07).

    상징 참조로는 못 잠근다 — `WITHDRAWAL_GRACE_PERIOD` 를 쓰는 셀은 상수를 60일로
    바꿔도 전부 초록이다(자기 자신과 비교하기 때문이다). 이 저장소의 다른 계약
    리터럴(`MIN_PASSWORD_LENGTH`·`SCENE_NOTE_MAX_CHARS`)과 같은 모양으로 **값을
    직접 박는 핀 셀**을 둔다.

    ★ **시행되면 이 셀의 자리가 바뀐다.** 정책 문서 §6 이 이 상수를 가리키게 되는
    순간(Slice 5) `tests/test_service_policy_contract.py` 가 문서-상수 대조를
    맡는다. 그때까지는 §8(정해졌으나 미시행)이라 포인터가 없고, 그래서 여기다.
    """

    def test_the_grace_period_is_thirty_days(self) -> None:
        self.assertEqual(WITHDRAWAL_GRACE_PERIOD, timedelta(days=30))


class WithdrawalStateAxisTest(unittest.TestCase):
    """Slice 0 — 상태 축과 경계 판정. **이 슬라이스는 아무것도 지우지 않는다.**"""

    def setUp(self) -> None:
        self.repo = InMemoryUserRepository()
        self.service = _service(self.repo)

    def _member(self) -> User:
        return self.service.create_user(username="alice", password="pw")

    # --- 전이: 활성 → 탈퇴 요청 → 취소 → 활성 -------------------------------

    def test_a_new_account_is_not_withdrawing(self) -> None:
        self.assertIsNone(self._member().withdrawal_requested_at)

    def test_requesting_stamps_the_clock_and_persists(self) -> None:
        user = self._member()
        requested = self.service.request_withdrawal(user.id)
        self.assertEqual(requested.withdrawal_requested_at, _FIXED_TIME)
        # 반환값만 맞고 저장이 안 되는 구현을 막는다.
        self.assertEqual(
            self.repo.get_by_id(user.id).withdrawal_requested_at, _FIXED_TIME
        )

    def test_requesting_deletes_nothing_and_keeps_the_account_usable(self) -> None:
        """Slice 0 의 인계 문장 그대로 — 상태만 만든다.

        유예 중 접근 제한은 Slice 2(D1=C)의 몫이고, 계정 자체는 **여전히 활성**
        이어야 취소하러 로그인할 수 있다. 여기서 `is_active=False` 로 만드는
        과잉 교정은 취소 경로를 통째로 잠근다.
        """
        user = self._member()
        self.service.request_withdrawal(user.id)
        stored = self.repo.get_by_id(user.id)
        self.assertTrue(stored.is_active)
        self.assertEqual(stored.status, USER_STATUS_ACTIVE)
        self.assertIsNotNone(self.service.authenticate(
            username="alice", password="pw"
        ))

    def test_cancelling_clears_the_stamp(self) -> None:
        user = self._member()
        self.service.request_withdrawal(user.id)
        cancelled = self.service.cancel_withdrawal(user.id)
        self.assertIsNone(cancelled.withdrawal_requested_at)
        self.assertIsNone(
            self.repo.get_by_id(user.id).withdrawal_requested_at
        )

    def test_a_cancelled_account_is_indistinguishable_from_one_that_never_asked(self):
        # D5=A 의 성질: 취소 뒤에는 제한을 걷는 두 번째 규칙이 필요 없다 —
        # 상태 자체가 사라지기 때문이다.
        never = self.service.create_user(username="never", password="pw")
        user = self._member()
        self.service.request_withdrawal(user.id)
        self.service.cancel_withdrawal(user.id)
        after = self.repo.get_by_id(user.id)
        self.assertEqual(
            (after.is_active, after.status, after.withdrawal_requested_at),
            (never.is_active, never.status, never.withdrawal_requested_at),
        )

    def test_cancelling_then_requesting_again_starts_a_new_grace_period(self) -> None:
        clock = {"now": _FIXED_TIME}
        service = UserService(
            self.repo, hasher=_FakeHasher(),
            clock=lambda: clock["now"], id_factory=_seq_ids(),
        )
        user = service.create_user(username="alice", password="pw")
        service.request_withdrawal(user.id)
        service.cancel_withdrawal(user.id)
        clock["now"] = _FIXED_TIME + timedelta(days=5)
        again = service.request_withdrawal(user.id)
        self.assertEqual(
            again.withdrawal_requested_at, _FIXED_TIME + timedelta(days=5)
        )

    # --- 멱등: 두 번 눌러도 삭제 예정일이 밀리지 않는다 ----------------------

    def test_a_repeat_request_keeps_the_first_stamp(self) -> None:
        """under-strict 짝: 재요청이 시각을 다시 찍으면 회원이 두 번 누르는 것만
        으로 자기 삭제일을 미룬다(화면의 '남은 N일'이 이유 없이 되돌아간다)."""
        clock = {"now": _FIXED_TIME}
        service = UserService(
            self.repo, hasher=_FakeHasher(),
            clock=lambda: clock["now"], id_factory=_seq_ids(),
        )
        user = service.create_user(username="alice", password="pw")
        service.request_withdrawal(user.id)
        clock["now"] = _FIXED_TIME + timedelta(days=7)
        second = service.request_withdrawal(user.id)
        self.assertEqual(second.withdrawal_requested_at, _FIXED_TIME)

    # --- 없는 계정 · 잘못된 전이 -------------------------------------------

    def test_requesting_for_an_unknown_user_raises(self) -> None:
        with self.assertRaises(UserNotFound):
            self.service.request_withdrawal("user:ghost")

    def test_cancelling_for_an_unknown_user_raises(self) -> None:
        with self.assertRaises(UserNotFound):
            self.service.cancel_withdrawal("user:ghost")

    def test_cancelling_an_account_that_never_asked_is_refused(self) -> None:
        user = self._member()
        with self.assertRaises(WithdrawalNotRequested):
            self.service.cancel_withdrawal(user.id)

    # --- D6: 마지막 활성 관리자 --------------------------------------------

    def test_the_last_active_admin_cannot_withdraw(self) -> None:
        admin = self.service.create_user(
            username="root", password="pw", is_admin=True
        )
        with self.assertRaises(LastActiveAdmin):
            self.service.request_withdrawal(admin.id)
        self.assertIsNone(
            self.repo.get_by_id(admin.id).withdrawal_requested_at
        )

    def test_a_second_active_admin_makes_the_first_able_to_withdraw(self) -> None:
        # over-strict 짝: D6 을 "관리자는 탈퇴 못 한다"로 넓히면 이 셀이 문다.
        first = self.service.create_user(
            username="root", password="pw", is_admin=True
        )
        self.service.create_user(username="root2", password="pw", is_admin=True)
        self.assertIsNotNone(
            self.service.request_withdrawal(first.id).withdrawal_requested_at
        )

    def test_a_plain_member_is_never_blocked_by_the_admin_rule(self) -> None:
        self.service.create_user(username="root", password="pw", is_admin=True)
        member = self._member()
        self.assertIsNotNone(
            self.service.request_withdrawal(member.id).withdrawal_requested_at
        )


class WithdrawalFirstStampRaceTest(unittest.TestCase):
    """첫 시각 보존이 **저장소에서** 결정되는가 (독립 검증 H2, 2026-09-08).

    서비스의 조기 반환만으로는 부족하다 — 읽기와 쓰기 사이가 열려 있으면 동시 첫
    요청 둘이 **모두** 그 반환을 지나고, 무조건 쓰기였다면 나중 시각이 이겨
    삭제 예정일이 그만큼 밀린다. 조건을 저장소로 내려야 닫힌다.

    ★ 이 클래스가 있는 이유: 처방만 넣고 셀을 안 두면 `only_if_absent=True` 를
    `False` 로 되돌려도 **83셀이 전부 초록이었다**(실측 MW-4). 검증자의 X1 과
    같은 종류의 빈 자리다.
    """

    def setUp(self) -> None:
        self.repo = InMemoryUserRepository()

    def _stored(self, at: datetime | None) -> User:
        user = User(
            id="user:1", username="alice", password_hash="H:pw",
            is_admin=False, is_active=True, created_at=_FIXED_TIME,
            withdrawal_requested_at=at,
        )
        self.repo.insert(user)
        return user

    # --- seam 자체 -----------------------------------------------------------

    def test_a_conditional_stamp_refuses_to_overwrite_an_existing_one(self) -> None:
        self._stored(_FIXED_TIME)
        later = _FIXED_TIME + timedelta(days=7)
        self.assertIsNone(self.repo.set_withdrawal_requested_at(
            "user:1", at=later, only_if_absent=True
        ))
        self.assertEqual(
            self.repo.get_by_id("user:1").withdrawal_requested_at, _FIXED_TIME
        )

    def test_a_conditional_stamp_lands_when_there_is_none(self) -> None:
        # over-strict 짝: 조건을 "항상 거부" 로 만드는 과잉 교정이면 첫 요청조차
        # 못 찍는다.
        self._stored(None)
        updated = self.repo.set_withdrawal_requested_at(
            "user:1", at=_FIXED_TIME, only_if_absent=True
        )
        self.assertEqual(updated.withdrawal_requested_at, _FIXED_TIME)

    def test_an_unconditional_write_still_overwrites(self) -> None:
        # 취소(`at=None`)가 지나는 경로다 — 조건을 전역으로 켜는 과잉 교정이면
        # 취소가 안 먹는다.
        self._stored(_FIXED_TIME)
        cleared = self.repo.set_withdrawal_requested_at("user:1", at=None)
        self.assertIsNone(cleared.withdrawal_requested_at)

    # --- 서비스가 그 조건을 실제로 쓰는가 ------------------------------------

    def test_the_service_survives_a_stale_read_of_a_withdrawing_account(self) -> None:
        """경쟁 재현: 조기 반환을 **지나가게** 만들고 저장소만 남긴다.

        `get_by_id` 가 한 번 낡은(탈퇴 전) 값을 돌려주게 해서 서비스가 조기
        반환을 지나치게 한다 — 동시 요청 둘 중 늦게 쓰는 쪽이 정확히 이 상태다.
        그 뒤로 계정을 지키는 것은 **조건부 쓰기 하나뿐**이고, 그것을 무조건으로
        되돌리면(MW-4) 이 셀이 나중 시각을 보고 실패한다.
        """
        self._stored(_FIXED_TIME)
        stale = replace(self.repo.get_by_id("user:1"), withdrawal_requested_at=None)

        class _StaleOnce:
            """첫 `get_by_id` 만 낡은 값을 준다. 나머지는 진짜 저장소."""

            def __init__(self, inner, stale_user):
                self._inner, self._stale, self._served = inner, stale_user, False

            def get_by_id(self, user_id):
                if not self._served:
                    self._served = True
                    return self._stale
                return self._inner.get_by_id(user_id)

            def __getattr__(self, name):
                return getattr(self._inner, name)

        service = UserService(
            _StaleOnce(self.repo, stale), hasher=_FakeHasher(),
            clock=lambda: _FIXED_TIME + timedelta(days=7),
            id_factory=_seq_ids(),
        )
        returned = service.request_withdrawal("user:1")
        # 늦은 요청이 **먼저 찍힌 시각을 그대로** 받아야 한다.
        self.assertEqual(returned.withdrawal_requested_at, _FIXED_TIME)
        self.assertEqual(
            self.repo.get_by_id("user:1").withdrawal_requested_at, _FIXED_TIME
        )


class PurgeDueBoundaryTest(unittest.TestCase):
    """30일 경계. **양방향**이라 `>` 도 `>=` 도 한쪽만 고르면 기명 셀이 문다."""

    def _withdrawing(self, requested_at: datetime | None) -> User:
        return User(
            id="user:1", username="alice", password_hash="H:pw",
            is_admin=False, is_active=True, created_at=_FIXED_TIME,
            withdrawal_requested_at=requested_at,
        )

    def test_an_account_that_never_asked_has_no_due_date(self) -> None:
        self.assertIsNone(purge_due_at(self._withdrawing(None)))

    def test_an_account_that_never_asked_is_never_due(self) -> None:
        # 이 셀이 없으면 `is_purge_due` 가 None 을 만나 터지거나 True 를 낸다 —
        # 후자는 탈퇴를 요청한 적 없는 계정을 파기 대상으로 만든다.
        self.assertFalse(
            is_purge_due(self._withdrawing(None), now=_FIXED_TIME)
        )

    def test_the_due_date_is_the_request_plus_the_grace_period(self) -> None:
        user = self._withdrawing(_FIXED_TIME)
        self.assertEqual(purge_due_at(user), _FIXED_TIME + timedelta(days=30))

    def test_day_29_is_not_due(self) -> None:
        # under-strict: 유예를 짧게 만드는 변이(`- 1`·29일 상수)가 여기서 문다.
        self.assertFalse(is_purge_due(
            self._withdrawing(_FIXED_TIME), now=_FIXED_TIME + timedelta(days=29)
        ))

    def test_exactly_day_30_is_due(self) -> None:
        # over-strict: `>=` → `>` 또는 유예에 `+1` 을 얹는 과잉 교정이 여기서 문다.
        self.assertTrue(is_purge_due(
            self._withdrawing(_FIXED_TIME), now=_FIXED_TIME + timedelta(days=30)
        ))

    def test_day_31_is_due(self) -> None:
        self.assertTrue(is_purge_due(
            self._withdrawing(_FIXED_TIME), now=_FIXED_TIME + timedelta(days=31)
        ))

    def test_a_moment_before_day_30_is_not_due(self) -> None:
        self.assertFalse(is_purge_due(
            self._withdrawing(_FIXED_TIME),
            now=_FIXED_TIME + timedelta(days=30) - timedelta(microseconds=1),
        ))


if __name__ == "__main__":
    unittest.main()
