"""Phase S-3 — 공개 signup 표면 속박 회귀 (오너 결정 2026-09-05 = C).

브리프 ``docs/plans/security-phase-s3-signup-throttle-decisions.md``.
막는 결함은 감사 §A.5·§A.11 이다: 공개 ``POST /auth/signup`` 이 **승인 전에**
Argon2(t=3·m=64MiB·p=4)를 태우고, 앱은 단일 uvicorn 워커라 요청 하나가 이벤트
루프를 점유한다 — 즉 계정을 하나도 승인하지 않아도 미인증 요청자가 서비스를
세울 수 있었다.

이 파일이 잠그는 축 셋. 각 축은 **양방향**이다.

① ``ClientIpResolver`` — 헤더를 언제 믿는가. under-strict: XFF 의 **왼쪽**을
   읽으면(흔한 구현) 요청마다 버킷을 고를 수 있게 되어 IP 축이 0이 된다.
   over-strict: 신뢰 밖 직결에서 XFF 를 읽으면 LAN 의 누구나 버킷을 고른다.
② ``SignupThrottle`` — 창 안 N+1번째는 막고, N번째와 창 밖은 통과시킨다.
   막힌 요청이 창을 **연장하지 않는다**는 것까지 잰다(연장하면 두드리는 동안
   정직한 재시도자가 영구히 못 들어온다).
③ 입력 상한과 대기열 상한 — 둘 다 **해셔 앞**에서 거절된다.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from services.application.app.auth.client_ip import (
    DEFAULT_TRUSTED_PROXY_CIDRS,
    UNKNOWN_CLIENT,
    ClientIpResolver,
)
from services.application.app.auth.signup_guard import (
    InMemoryAttemptRecordRepository,
    SignupThrottle,
)
from services.application.app.auth.sessions import (
    InMemorySessionRepository,
    SessionService,
)
from services.application.app.auth.users import (
    MAX_PASSWORD_LENGTH,
    MAX_PENDING_SIGNUPS,
    MAX_USERNAME_LENGTH,
    InMemoryUserRepository,
    InvalidUserInput,
    SignupQueueFull,
    UserService,
)
from services.application.app.main import create_app


class _CountingHasher:
    """해시 호출 횟수를 센다. 이 가드의 요점은 **거절이 싸다**는 것이다."""

    def __init__(self) -> None:
        self.calls = 0

    def hash(self, password: str) -> str:
        self.calls += 1
        return "H:" + password

    def verify(self, stored_hash: str, password: str) -> bool:
        return stored_hash == "H:" + password


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now = self.now + timedelta(seconds=seconds)


# ── ① 헤더 신뢰 정책 ────────────────────────────────────────────────────────

class ClientIpResolverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = ClientIpResolver(DEFAULT_TRUSTED_PROXY_CIDRS)

    def test_an_untrusted_peer_is_the_client_and_its_header_is_ignored(self) -> None:
        """직결이면 XFF 를 **통째로** 버린다.

        over-strict 축: 배포 앱은 ``0.0.0.0:8520`` 으로 게시돼 있어(D8-7 G1=C)
        LAN 에서 nginx 를 우회해 직접 닿는다. 그 경로에서 XFF 를 읽으면 LAN 의
        누구나 헤더 한 줄로 자기 버킷을 고를 수 있다 — 스로틀이 조용히 0이 된다.
        """
        self.assertEqual(
            self.resolver.resolve(peer="192.168.1.50", forwarded_for="8.8.8.8"),
            "192.168.1.50",
        )

    def test_behind_a_trusted_proxy_the_rightmost_untrusted_entry_wins(self) -> None:
        """XFF 는 **오른쪽에서** 읽는다.

        under-strict 축, 그리고 이 모듈이 존재하는 이유. 2026-09-05 배포 실측:
        공개 도메인에 ``X-Forwarded-For: 1.2.3.4`` 를 보내면 origin 에
        ``"1.2.3.4,<진짜 클라이언트 IP>"`` 로 도착한다 — Cloudflare 엣지가
        클라이언트가 보낸 값을 **지우지 않고 오른쪽에 덧붙인다**. 왼쪽을 읽는
        구현(``split(",")[0]``)은 공격자가 요청마다 다른 버킷을 고르게 한다.
        """
        # 앱이 실제로 받는 모양: [공격자가 고른 값] , [진짜 IP] , [frontend nginx 가 붙인 홉]
        self.assertEqual(
            self.resolver.resolve(
                peer="172.19.0.10",
                forwarded_for="1.2.3.4, 203.0.113.9, 172.19.0.1",
            ),
            "203.0.113.9",
        )

    def test_a_trusted_peer_without_a_header_falls_back_to_the_peer(self) -> None:
        self.assertEqual(
            self.resolver.resolve(peer="172.19.0.10", forwarded_for=None),
            "172.19.0.10",
        )

    def test_an_all_trusted_chain_falls_back_to_the_peer(self) -> None:
        """전부 신뢰 대역이면 peer 로 접힌다 — 공유 버킷이지, 통과가 아니다."""
        self.assertEqual(
            self.resolver.resolve(
                peer="172.19.0.10", forwarded_for="172.19.0.5, 172.19.0.1"
            ),
            "172.19.0.10",
        )

    def test_garbage_entries_are_dropped_not_treated_as_a_client(self) -> None:
        """형식이 아닌 항목에서 멈추지 않는다.

        여기서 멈추면 공격자가 쓰레기 한 글자마다 새 버킷을 얻는다 — 왼쪽을
        읽는 것과 똑같은 우회가 다른 문으로 들어온다.
        """
        self.assertEqual(
            self.resolver.resolve(
                peer="172.19.0.10",
                forwarded_for="not-an-ip, 203.0.113.9, 172.19.0.1",
            ),
            "203.0.113.9",
        )
        self.assertEqual(
            self.resolver.resolve(
                peer="172.19.0.10", forwarded_for="not-an-ip, 172.19.0.1"
            ),
            "172.19.0.10",
        )

    def test_a_missing_peer_becomes_one_shared_bucket(self) -> None:
        self.assertEqual(
            self.resolver.resolve(peer=None, forwarded_for="8.8.8.8"),
            UNKNOWN_CLIENT,
        )

    def test_a_malformed_cidr_refuses_to_start(self) -> None:
        """조용히 무시하면 '신뢰 대역이 비었다' = 전원이 한 버킷이 된다.

        그 상태는 정상 동작과 로그로 구분되지 않는다 —
        ``AUTH_LOGIN_MAX_FAILURES`` 파싱과 같은 자세로 기동을 거부한다.
        """
        with self.assertRaises(ValueError):
            ClientIpResolver(("172.16.0.0/12", "not-a-cidr"))


# ── ② 고정창 스로틀 ─────────────────────────────────────────────────────────

class SignupThrottleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = _Clock(datetime(2026, 9, 5, 12, 0, tzinfo=UTC))
        self.throttle = SignupThrottle(
            InMemoryAttemptRecordRepository(),
            max_requests=3,
            window=timedelta(seconds=60),
            clock=self.clock,
        )

    def test_the_first_n_attempts_pass_and_the_next_one_is_refused(self) -> None:
        """under-strict: 상한이 사라지면 넷째가 통과해 실패한다.

        over-strict: 상한을 한 칸 당기면(예 ``>`` 를 ``>=`` 로) 셋째에서 이미
        막혀 앞의 세 단정이 실패한다.
        """
        for _ in range(3):
            self.assertIsNone(self.throttle.consume("203.0.113.9"))
        self.assertIsNotNone(self.throttle.consume("203.0.113.9"))

    def test_the_refusal_reports_seconds_until_the_window_resets(self) -> None:
        for _ in range(3):
            self.throttle.consume("203.0.113.9")
        self.clock.advance(20)
        self.assertEqual(self.throttle.consume("203.0.113.9"), 40)

    def test_a_refused_attempt_does_not_extend_the_window(self) -> None:
        """막힌 요청이 창을 밀면 두드리는 동안 창이 영원히 갱신된다.

        그러면 공격자는 어차피 못 들어오는데 **정직한 재시도자만** 영구히
        막힌다 — ``login_guard`` 가 잠금을 연장하지 않는 것과 같은 이유다.
        """
        for _ in range(3):
            self.throttle.consume("203.0.113.9")
        self.clock.advance(30)
        self.throttle.consume("203.0.113.9")   # 막힌다
        self.clock.advance(31)                 # 원래 창(60s)은 여기서 끝났다
        self.assertIsNone(self.throttle.consume("203.0.113.9"))

    def test_the_window_resets_after_it_passes(self) -> None:
        for _ in range(3):
            self.throttle.consume("203.0.113.9")
        self.clock.advance(60)
        self.assertIsNone(self.throttle.consume("203.0.113.9"))

    def test_each_sender_gets_its_own_bucket(self) -> None:
        for _ in range(3):
            self.throttle.consume("203.0.113.9")
        self.assertIsNone(self.throttle.consume("198.51.100.7"))


# ── ③ 입력 상한 · 대기열 상한 ───────────────────────────────────────────────

def _users(hasher: _CountingHasher) -> UserService:
    return UserService(InMemoryUserRepository(), hasher=hasher)


class SignupInputBoundsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.hasher = _CountingHasher()
        self.users = _users(self.hasher)

    def test_an_over_long_username_is_refused_before_hashing(self) -> None:
        with self.assertRaises(InvalidUserInput):
            self.users.request_signup(
                username="u" * (MAX_USERNAME_LENGTH + 1), password="long-enough-pw"
            )
        self.assertEqual(self.hasher.calls, 0)

    def test_an_over_long_password_is_refused_before_hashing(self) -> None:
        with self.assertRaises(InvalidUserInput):
            self.users.request_signup(
                username="bob", password="p" * (MAX_PASSWORD_LENGTH + 1)
            )
        self.assertEqual(self.hasher.calls, 0)

    def test_the_boundary_values_themselves_are_accepted(self) -> None:
        """over-strict 축: 상한을 한 글자 당기면 이 셀이 실패한다."""
        user = self.users.request_signup(
            username="u" * MAX_USERNAME_LENGTH, password="p" * MAX_PASSWORD_LENGTH
        )
        self.assertEqual(user.status, "pending")


class SignupQueueCeilingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.hasher = _CountingHasher()
        self.users = _users(self.hasher)

    def _fill(self, count: int) -> None:
        for index in range(count):
            self.users.request_signup(
                username=f"pending-{index}", password="long-enough-pw"
            )

    def test_the_queue_is_refused_at_the_ceiling_and_accepted_below_it(self) -> None:
        """under-strict: 상한이 사라지면 첫 단정이 실패한다.

        over-strict: 상한을 한 칸 당기면 ``_fill`` 자체가 예외로 죽는다.
        """
        self._fill(MAX_PENDING_SIGNUPS - 1)
        self.users.request_signup(username="last-one", password="long-enough-pw")
        before = self.hasher.calls
        with self.assertRaises(SignupQueueFull):
            self.users.request_signup(
                username="one-too-many", password="long-enough-pw"
            )
        # 거절이 해셔 앞이다 — 이 가드의 요점.
        self.assertEqual(self.hasher.calls, before)

    def test_a_re_request_over_a_rejected_row_survives_the_ceiling(self) -> None:
        """대기열 상한이 **거절당한 사람의 영구 밴**이 되면 안 된다.

        재요청은 이미 아는 username 을 요구하므로 홍수 통로가 아니고, 여기서
        막으면 오너 결정 *"거절은 밴이 아니다"*(SoT v1.7.97)가 뒤집힌다.
        """
        rejected = self.users.request_signup(
            username="comeback", password="long-enough-pw"
        )
        self.users.reject_signup(rejected.id)
        self._fill(MAX_PENDING_SIGNUPS)
        again = self.users.request_signup(
            username="comeback", password="long-enough-pw"
        )
        self.assertEqual(again.status, "pending")


# ── HTTP 계약 ───────────────────────────────────────────────────────────────

def _app(*, max_requests: int = 2, window_seconds: int = 60):
    users = UserService(InMemoryUserRepository(), hasher=_CountingHasher())
    sessions = SessionService(InMemorySessionRepository(), ttl=timedelta(hours=1))
    throttle = SignupThrottle(
        InMemoryAttemptRecordRepository(),
        max_requests=max_requests,
        window=timedelta(seconds=window_seconds),
    )
    return create_app(
        user_service=users,
        session_service=sessions,
        signup_throttle=throttle,
        # 테스트 클라이언트의 peer 를 신뢰 대역으로 잡아 XFF 축을 실제로 태운다.
        client_ip_resolver=ClientIpResolver(("172.16.0.0/12", "127.0.0.0/8")),
    )


class SignupThrottleHttpTest(unittest.TestCase):
    def _client(self, app, peer: str) -> TestClient:
        return TestClient(app, base_url="https://testserver", client=(peer, 50000))

    def test_the_throttled_request_is_429_with_retry_after(self) -> None:
        app = _app(max_requests=2)
        client = self._client(app, "203.0.113.9")
        for index in range(2):
            self.assertEqual(
                client.post(
                    "/auth/signup",
                    json={"username": f"u{index}", "password": "long-enough-pw"},
                ).status_code,
                201,
            )
        refused = client.post(
            "/auth/signup", json={"username": "u2", "password": "long-enough-pw"}
        )
        self.assertEqual(refused.status_code, 429)
        self.assertIn("Retry-After", refused.headers)
        self.assertGreater(int(refused.headers["Retry-After"]), 0)

    def test_the_axis_is_the_sender_not_the_username(self) -> None:
        """P-6 과 갈리는 지점.

        under-strict: 축이 username 으로 되돌아가면(= 매번 다른 이름이라 절대
        안 걸린다) 첫 단정이 실패한다. over-strict: 축이 전역 상한이면 다른
        발신자의 요청까지 막혀 둘째 단정이 실패한다.
        """
        app = _app(max_requests=2)
        attacker = self._client(app, "203.0.113.9")
        for index in range(2):
            attacker.post(
                "/auth/signup",
                json={"username": f"spray-{index}", "password": "long-enough-pw"},
            )
        self.assertEqual(
            attacker.post(
                "/auth/signup",
                json={"username": "spray-2", "password": "long-enough-pw"},
            ).status_code,
            429,
        )
        bystander = self._client(app, "198.51.100.7")
        self.assertEqual(
            bystander.post(
                "/auth/signup",
                json={"username": "honest", "password": "long-enough-pw"},
            ).status_code,
            201,
        )

    def test_a_forged_forwarded_for_cannot_buy_a_fresh_bucket(self) -> None:
        """신뢰 프록시 뒤에서도 왼쪽 위조는 통하지 않는다.

        엣지가 오른쪽에 붙이는 진짜 주소가 축이므로, 공격자가 XFF 왼쪽에 무엇을
        넣든 같은 버킷으로 접힌다. 왼쪽을 읽는 구현으로 되돌리면 이 셀이 실패한다.
        """
        app = _app(max_requests=2)
        # peer 는 신뢰 대역(= 프록시 홉), XFF 오른쪽 끝이 진짜 발신자다.
        client = TestClient(app, base_url="https://testserver",
                            client=("172.19.0.10", 50000))
        for index in range(3):
            response = client.post(
                "/auth/signup",
                json={"username": f"f{index}", "password": "long-enough-pw"},
                headers={
                    # 매 요청 왼쪽 값을 바꾼다 — 왼쪽을 읽으면 매번 새 버킷이다.
                    "X-Forwarded-For": f"10.9.9.{index}, 203.0.113.9, 172.19.0.1",
                },
            )
        self.assertEqual(response.status_code, 429)

    def test_the_queue_ceiling_answers_429_too(self) -> None:
        app = _app(max_requests=MAX_PENDING_SIGNUPS + 5)
        client = self._client(app, "203.0.113.9")
        for index in range(MAX_PENDING_SIGNUPS):
            self.assertEqual(
                client.post(
                    "/auth/signup",
                    json={"username": f"q{index}", "password": "long-enough-pw"},
                ).status_code,
                201,
            )
        self.assertEqual(
            client.post(
                "/auth/signup",
                json={"username": "one-too-many", "password": "long-enough-pw"},
            ).status_code,
            429,
        )

    def test_the_input_bounds_answer_400_not_422(self) -> None:
        """정책 거절은 한 얼굴이어야 한다.

        pydantic 에 ``max_length`` 를 걸면 422 가 되어, 가입 화면이 같은 뜻의
        거절을 두 모양으로 받게 된다 — 그래서 상한은 모델이 아니라 서비스에 있다.
        """
        app = _app()
        client = self._client(app, "203.0.113.9")
        self.assertEqual(
            client.post(
                "/auth/signup",
                json={
                    "username": "u" * (MAX_USERNAME_LENGTH + 1),
                    "password": "long-enough-pw",
                },
            ).status_code,
            400,
        )


if __name__ == "__main__":
    unittest.main()
