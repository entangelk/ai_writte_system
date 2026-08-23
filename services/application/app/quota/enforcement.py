"""유료 요청의 시행 — 정책·원장·잠금을 한 자리에서 조립한다 (Phase 8 Slice 8.3).

오너 결정 2026-08-04, 브리프 ``08-3-quota-enforcement-decisions.md``
**Q1=C · Q1-a=A · Q1-b=A · Q3=E · Q3-a=A · Q4=A · Q5=B · Q6=C · Q7=A · Q8=C ·
Q9=A**. 8.0(분류)·8.1(한도)·8.2(원장)·8.2b(잠금)가 재료를 만들고 아무도 조립하지
않은 채 끝났다 — 이 모듈이 그 넷을 붙인다. **HTTP 는 여기 없다**(상태코드 매핑은
``main.py`` 의 dependency 몫이다).

- **Q1=C — 성공차감.** 원장 행은 요청이 **성공했을 때만** 생긴다. 오너 근거는 회계가
  아니라 서비스 정책이다("실패에는 과금하지 않는다"). 그 대가로 검사와 차감 사이가
  요청 전체 길이(최대 91초)로 벌어지고, 그 창을 아래 둘이 닫는다.
- **Q1-a=A — "성공"은 상태코드가 아니다.** ``2xx`` **그리고** provider 를 실제로
  부른 경우만 센다. 상태코드만 보면 **양쪽으로** 틀린다: partial envelope 6곳은
  일을 하고도 4xx/5xx 이고, ``analysis_extract`` replay 는 provider 를 한 번도 안
  부르고 200 이다. 후자가 오너가 "절대 안 된다"고 못박은 사건이다. 판정 재료는
  ``main.py`` 가 넘겨준다(그 요청의 provider 호출 수).
- **Q3=E + Q3-a=A — 초과는 구조적으로 불가능하다.** 유효 사용량 = 원장 행 + 조정 합
  + **진행 중 잠금** + **대기·실행 중 async job**. 그 계산과 잠금 차지를 **회원 단위
  입장 뮤텍스** 안에서 하므로 다음 요청은 반드시 앞 요청의 잠금을 본다. 트랜잭션은
  이 문제를 못 푼다(스냅샷 격리는 count 술어를 직렬화하지 않는다) — 브리프 §Q3-a.
- **★ 뮤텍스를 쥔 채 provider 를 부르면 이 설계의 장점이 전부 사라진다.** 임계
  구역은 Mongo 왕복 두어 번(수 ms)이고 모델 호출은 그 **밖**이다. 회귀가 이것을
  over-strict 로 잠근다.
- **Q4=A — 전면 fail-closed.** 정책·원장·잠금 어느 하나라도 저장소가 실패하면
  예외가 그대로 올라가고 요청은 503 으로 끝난다(전역 handler). **계량 불능 = 무료
  제공**을 막는 쪽이 이 슬라이스의 방향이다. 뮤텍스 획득 실패도 같다.
- **Q1-b=A — 비동기 202 는 워커가 센다.** 202 는 "접수 성공"이지 "생성 성공"이
  아니다. 그래서 이 모듈은 async 차감용 진입점(``charge_completed_generation``)을
  따로 열고, 요청 경로의 정산은 202 를 과금하지 않는다.

**단 하나 남는 정직한 한계**: 잠금 lease(180초)가 만료됐는데 요청이 아직 살아
있으면 그 요청은 진행 중 계수에서 빠진다 — 8.2b §0.3 의 "최선 노력"을 그대로
상속한다. 뮤텍스는 **동시 입장**을 닫지 오래 걸리는 요청의 lease 만료까지 닫지
않는다.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Callable, Iterator, Protocol

from services.application.app.quota.ledger import UsageLedgerService
from services.application.app.quota.lock import (
    LockBlocked,
    RequestLock,
    RequestLockRepository,
    RequestLockService,
)
from services.application.app.quota.policy import (
    QuotaLimits,
    QuotaPolicyService,
    QuotaStatus,
    next_daily_boundary,
    next_week_boundary,
)

logger = logging.getLogger(__name__)

#: 입장 뮤텍스의 키 공간. 8.2b 의 세 축 키(``{user}:{action}:{project}``)와 접두가
#: 달라 충돌하지 않고, 진행 중 계수(``{user}:`` 접두 조회)에도 잡히지 않는다.
ADMISSION_KEY_PREFIX = "admission:"

#: 임계 구역이 수 ms 이므로 짧다(브리프 §Q3-a 구현 계약 2). 8.2b 의 lease(180초,
#: 크래시 회수용)와 **다른 축이다** — 길게 잡으면 크래시 한 번이 그 회원을 오래 막는다.
ADMISSION_LEASE_SECONDS = 5

#: 유한 재시도 뒤 실패면 fail-closed(§Q3-a 구현 계약 3). 8.2b ``CLAIM_ATTEMPTS`` 선례.
ADMISSION_ATTEMPTS = 5
ADMISSION_RETRY_SLEEP_SECONDS = 0.02


def admission_key(user_id: str) -> str:
    return f"{ADMISSION_KEY_PREFIX}{user_id}"


class QuotaRefusalReason(StrEnum):
    """거절 사유. **HTTP 상태코드는 여기 없다** — 매핑은 ``main.py`` 가 한다(Q5=B)."""

    SUSPENDED = "suspended"
    EXCEEDED = "exceeded"
    LOCKED = "locked"


class QuotaRefused(RuntimeError):
    """한도·정지·중복으로 요청을 받지 않는다. 저장소는 멀쩡하다(그쪽은 Q4=A)."""

    def __init__(
        self, reason: QuotaRefusalReason, detail: str, *,
        retry_after_seconds: int | None = None, in_flight: bool = False,
    ) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail
        #: 잠금 거절에만 있다(8.2b G5=A). 올림·최소 1.
        self.retry_after_seconds = retry_after_seconds
        #: ``True`` 면 아직 처리 중, ``False`` 면 방금 끝나 냉각 중이다.
        self.in_flight = in_flight


class AdmissionUnavailable(RuntimeError):
    """입장 뮤텍스를 유한 재시도 안에 못 잡았다 → fail-closed(§Q3-a 계약 3).

    초과를 허용하느니 요청을 실패시킨다. 저장소 장애와 같은 얼굴(503)로 답하는 것이
    Q4=A 와 같은 방향이다.
    """


@dataclass(frozen=True, slots=True)
class QuotaCharge:
    """입장 허가 영수증. 요청이 끝나면 이것을 들고 정산한다.

    ``holder`` 없이는 잠금을 풀 수 없다(8.2b §0.4 fencing) — 강제 재차지로 주인이
    바뀐 뒤 먼저 시작한 요청이 해제를 불러 새 주인의 보호를 지우는 것을 막는다.
    """

    user_id: str
    member_created_at: datetime
    action: str
    target_project_id: str
    dedupe_key: str
    holder: str


@dataclass(frozen=True, slots=True)
class QuotaSnapshot:
    """회원이 지금 볼 수 있는 자기 사용량 (8.4 W5=B).

    **표시 단위는 통합값 하나**(8.2 §0.2) — 두 창을 모두 통과해야 하므로 작은 쪽이
    실제로 남은 횟수다. 그렇다고 창별 값을 감추지는 않는다: "왜 20회가 아니라
    3회인가"의 답이 거기 있고, 그 답이 없으면 지원 대화가 성립하지 않는다.
    """

    status: QuotaStatus
    daily_limit: int | None
    weekly_limit: int | None
    daily_used: int
    weekly_used: int
    daily_resets_at: datetime
    weekly_resets_at: datetime

    @property
    def daily_remaining(self) -> int | None:
        return _remaining(self.daily_limit, self.daily_used)

    @property
    def weekly_remaining(self) -> int | None:
        return _remaining(self.weekly_limit, self.weekly_used)

    @property
    def unlimited(self) -> bool:
        return self.daily_limit is None and self.weekly_limit is None

    @property
    def remaining(self) -> int | None:
        """통합 잔여. 두 창이 모두 무제한일 때만 ``None`` 이다.

        한쪽만 무제한이면 **다른 쪽이 곧 실질 잔여**다 — 여기서 `None` 을 0 으로
        접으면 무제한 회원의 잔여가 0 이 되고, 반대로 `None` 을 이겨 버리면
        한도가 있는 창이 무시된다.
        """

        candidates = [
            value for value in (self.daily_remaining, self.weekly_remaining)
            if value is not None
        ]
        return min(candidates) if candidates else None


def _remaining(limit: int | None, used: int) -> int | None:
    if limit is None:
        return None
    # 음수는 표시하지 않는다 — 조정이나 한도 하향으로 사용량이 한도를 넘을 수
    # 있는데(8.2 는 그것을 허용한다), 화면의 "-2회 남음"은 잔여가 아니다.
    return max(limit - used, 0)


class ActiveJobCounter(Protocol):
    def count_active_for_user(self, *, user_id: str) -> int:
        """그 회원의 대기·실행 중 비동기 생성 job 수 (Q1-b=A)."""


class MemberLookup(Protocol):
    def get_by_id(self, user_id: str): ...


class AdmissionMutex:
    """회원 단위 입장 직렬화 (Q3-a=A).

    8.2b 잠금과 **같은 컬렉션·같은 원자적 차지 연산**을 키만 바꿔 쓴다 — 새 개념도
    새 청소 작업도 없고, lease 가 크래시를 자가 회수한다. 해제는 냉각 없이 즉시다:
    이것은 중복 방지 장치가 아니라 임계 구역이라, 냉각을 두면 같은 회원의 다음
    요청이 이유 없이 기다린다.
    """

    def __init__(
        self,
        repository: RequestLockRepository,
        *,
        lease_seconds: int = ADMISSION_LEASE_SECONDS,
        attempts: int = ADMISSION_ATTEMPTS,
        clock: Callable[[], datetime] | None = None,
        holder_factory: Callable[[], str] | None = None,
        sleep: Callable[[float], None] | None = None,
        retry_sleep_seconds: float = ADMISSION_RETRY_SLEEP_SECONDS,
    ) -> None:
        if attempts < 1:
            raise ValueError("the admission mutex needs at least one attempt")
        self._repo = repository
        self._lease = timedelta(seconds=lease_seconds)
        self._attempts = attempts
        self._clock = clock or (lambda: datetime.now(UTC))
        self._holder_factory = holder_factory or (lambda: uuid.uuid4().hex)
        self._sleep = sleep or time.sleep
        self._retry_sleep = retry_sleep_seconds

    @contextmanager
    def hold(self, user_id: str) -> Iterator[str]:
        """임계 구역. **해제는 ``finally`` 다** — 안에서 예외가 나도 반드시 푼다."""

        holder = self._acquire(user_id)
        try:
            yield holder
        finally:
            self._release(user_id, holder)

    def _acquire(self, user_id: str) -> str:
        key = admission_key(user_id)
        for attempt in range(self._attempts):
            now = self._clock()
            holder = self._holder_factory()
            current = self._repo.claim(
                RequestLock(
                    key=key,
                    holder=holder,
                    claimed_at=now,
                    expires_at=now + self._lease,
                    released_at=None,
                ),
                now=now,
            )
            if current.holder == holder:
                return holder
            if attempt + 1 < self._attempts:
                self._sleep(self._retry_sleep)
        raise AdmissionUnavailable(
            f"could not serialise admission for user {user_id}"
        )

    def _release(self, user_id: str, holder: str) -> None:
        # 최소 창 0 = 냉각 없이 즉시 반납. 소유권 검사는 저장소가 한다(남의 뮤텍스를
        # 풀지 않는다) — lease 만료 뒤 남이 잡았으면 이 해제는 아무것도 바꾸지 않는다.
        self._repo.release(
            admission_key(user_id),
            holder=holder,
            now=self._clock(),
            minimum_window=timedelta(0),
        )


class QuotaEnforcementService:
    """유료 요청 하나의 입장과 정산. **세 저장소를 endpoint 가 각자 부르지 않는다.**"""

    def __init__(
        self,
        *,
        policy: QuotaPolicyService,
        ledger: UsageLedgerService,
        locks: RequestLockService,
        mutex: AdmissionMutex,
        jobs: ActiveJobCounter | None = None,
    ) -> None:
        self._policy = policy
        self._ledger = ledger
        self._locks = locks
        self._mutex = mutex
        # None 이면 async job 을 세지 않는다 — 비동기 생성이 없는 조립(테스트·
        # 스크립트)에서 세울 것이 없기 때문이고, 배포 조립은 항상 넘긴다.
        self._jobs = jobs

    # 8.5-a: the admin read surface needs the stored policy row (stored limits,
    # pending reservation) next to the effective snapshot. Exposing the service
    # the enforcement itself uses — rather than assembling a second one — keeps
    # one interpretation path (same instance, same clock) by construction.
    @property
    def policy(self):
        return self._policy

    # ------------------------------------------------------------ 입장 (Q3-a)

    def admit(
        self, *, user_id: str, member_created_at: datetime, action: str,
        target_project_id: str, dedupe_key: str, confirmed: bool = False,
    ) -> QuotaCharge:
        """한도를 보고 잠금을 차지한다. 통과하지 못하면 ``QuotaRefused``.

        저장소가 실패하면 예외가 그대로 올라간다(Q4=A) — 잡아서 통과시키는 순간
        "계량할 수 없으면 무료"가 된다.
        """

        limits = self._policy.limits_for(user_id)
        if limits.status is QuotaStatus.SUSPENDED:
            # 정지는 동시성 문제가 아니라 계정 상태다 — 뮤텍스를 잡을 이유가 없고,
            # 한도(0회)와도 **다른 사건**이다(P5). 코드도 갈린다(Q5=B: 403).
            raise QuotaRefused(
                QuotaRefusalReason.SUSPENDED,
                "this account is suspended; an administrator must lift it",
            )
        with self._mutex.hold(user_id):
            # ★ 임계 구역 안에서 하는 일은 이 셋뿐이다: 센다 → 판정한다 → 차지한다.
            # provider 호출이 여기 들어오면 한 회원의 요청이 91초씩 직렬화된다.
            self._refuse_if_exhausted(
                user_id=user_id, member_created_at=member_created_at,
                limits=limits,
            )
            granted = self._claim(
                user_id=user_id, action=action,
                target_project_id=target_project_id, confirmed=confirmed,
            )
        return QuotaCharge(
            user_id=user_id,
            member_created_at=member_created_at,
            action=action,
            target_project_id=target_project_id,
            dedupe_key=dedupe_key,
            holder=granted,
        )

    def effective_usage(
        self, *, user_id: str, member_created_at: datetime
    ) -> tuple[int, int]:
        """(일, 주) 유효 사용량 = 원장 + 조정 + 진행 중 (Q3=E).

        진행 중은 **회원 단위**라 두 창에 같은 값이 더해진다 — 지금 처리 중인
        요청은 어느 창으로 세든 아직 어느 창에도 행이 없기 때문이다.
        """

        used = self._ledger.used(
            user_id=user_id, member_created_at=member_created_at)
        in_flight = self._locks.count_in_flight(user_id=user_id)
        if self._jobs is not None:
            in_flight += self._jobs.count_active_for_user(user_id=user_id)
        return used.daily + in_flight, used.weekly + in_flight

    def _refuse_if_exhausted(
        self, *, user_id: str, member_created_at: datetime, limits: QuotaLimits
    ) -> None:
        daily, weekly = self.effective_usage(
            user_id=user_id, member_created_at=member_created_at)
        # **두 창을 모두** 본다(P2). 일은 여유인데 주가 소진이면 막힌다, 그 역도.
        # ``limit=0`` 은 여기서 자연히 항상 막고(0 >= 0), ``None`` 은 무제한이다.
        for window, used, limit in (
            ("daily", daily, limits.daily_limit),
            ("weekly", weekly, limits.weekly_limit),
        ):
            if limit is not None and used >= limit:
                raise QuotaRefused(
                    QuotaRefusalReason.EXCEEDED,
                    f"{window} request quota exhausted ({used}/{limit})",
                )

    # ------------------------------------------------------------ 조회 (8.4 W5)

    def snapshot(
        self, *, user_id: str, member_created_at: datetime
    ) -> QuotaSnapshot:
        """회원이 자기 잔여를 보는 값. **읽기만 한다** (8.4 W5=B).

        ★ 이 함수의 존재 이유는 "잔여를 계산하는 두 번째 자리를 만들지 않는 것"이다.
        분자는 ``effective_usage``(= 입장 판정이 쓰는 그 값), 분모는
        ``limits_for``(= P6 예약을 해석하는 그 함수)다. 화면이 자기 나름대로 세면
        "3회 남음"을 보여 준 직후 402 를 내는데, 그것은 버그가 아니라 **불신**으로
        보인다.

        잠금도 뮤텍스도 잡지 않는다 — 조회가 한 칸을 차지하면 화면을 여는 것만으로
        한도가 줄고, 뮤텍스를 잡으면 조회 하나가 그 회원의 유료 요청을 직렬화한다.
        """

        limits = self._policy.limits_for(user_id)
        daily_used, weekly_used = self.effective_usage(
            user_id=user_id, member_created_at=member_created_at)
        now = self._policy.now()
        return QuotaSnapshot(
            status=limits.status,
            daily_limit=limits.daily_limit,
            weekly_limit=limits.weekly_limit,
            daily_used=daily_used,
            weekly_used=weekly_used,
            daily_resets_at=next_daily_boundary(now),
            weekly_resets_at=next_week_boundary(member_created_at, now),
        )

    def _claim(
        self, *, user_id: str, action: str, target_project_id: str,
        confirmed: bool,
    ) -> str:
        if confirmed:
            # G4=A: 확인된 요청은 잠금을 **끄는 것이 아니라 옮긴다** — 다음 클릭은
            # 다시 막히고, 크래시로 남은 잠금도 이 문으로 즉시 뚫린다.
            return self._locks.force_claim(
                user_id=user_id, action=action,
                target_project_id=target_project_id,
            ).holder
        result = self._locks.claim(
            user_id=user_id, action=action, target_project_id=target_project_id)
        if isinstance(result, LockBlocked):
            raise QuotaRefused(
                QuotaRefusalReason.LOCKED,
                "the same request is already in progress or was just made",
                retry_after_seconds=result.retry_after_seconds,
                in_flight=result.in_flight,
            )
        return result.holder

    # ------------------------------------------------------------ 정산 (Q1=C)

    def settle(self, charge: QuotaCharge, *, charged: bool) -> None:
        """요청 종료. **원장 삽입이 잠금 해제보다 먼저다**(Q3=E 구현 계약 2).

        순서가 뒤집히면 그 사이에 **행도 없고 잠금도 없는 한 칸**이 생겨 초과가
        정확히 그 틈으로 샌다. 그래서 해제는 ``finally`` 이고 차감은 그 앞이다.

        **정산은 요청의 결과를 바꾸지 않는다**(독립 검증 2026-08-04 H-1). 이 함수는
        응답이 이미 만들어진 뒤에 불리므로, 여기서 예외가 새어 나가면 **성공한
        2xx 가 5xx 로 뒤집힌다** — 사용자는 결과를 받았는데 실패로 통보받는 셈이다.
        원장 삽입은 처음부터 그렇게 다뤘고(Q2 잔여), 해제도 같은 규칙을 따른다:
        잠금은 lease 가 회수하므로 놓쳐도 정합성이 깨지지 않는다.
        """

        try:
            if charged:
                self._record(
                    user_id=charge.user_id,
                    member_created_at=charge.member_created_at,
                    target_project_id=charge.target_project_id,
                    action=charge.action,
                    dedupe_key=charge.dedupe_key,
                )
        finally:
            try:
                self._locks.release(
                    user_id=charge.user_id,
                    action=charge.action,
                    target_project_id=charge.target_project_id,
                    holder=charge.holder,
                )
            except Exception:  # noqa: BLE001 — 응답을 뒤집지 않는다(위 docstring)
                logger.exception(
                    "releasing the request lock failed after a settled request "
                    "(user=%s action=%s) — the lease will reclaim it",
                    charge.user_id, charge.action,
                )

    def charge_completed_generation(
        self, *, user_id: str, member_created_at: datetime,
        target_project_id: str, request_id: str,
    ) -> None:
        """비동기 생성이 실제로 성공했다 (Q1-b=A). 주체는 워커다.

        ``dedupe_key`` 는 요청 경로와 같은 ``request_id`` 다 — 그래서 재전송·retry
        가 몇 번을 돌아도 원장은 **한 행**이고, 이중 과금이 구조적으로 불가능하다
        (8.0 B5=A 가 재시도를 재차감하지 않기로 한 것과 같은 축).
        """

        self._record(
            user_id=user_id,
            member_created_at=member_created_at,
            target_project_id=target_project_id,
            action="writing_generate",
            dedupe_key=request_id,
        )

    def _record(
        self, *, user_id: str, member_created_at: datetime,
        target_project_id: str, action: str, dedupe_key: str,
    ) -> None:
        try:
            self._ledger.record_usage(
                user_id=user_id,
                member_created_at=member_created_at,
                target_project_id=target_project_id,
                action=action,
                dedupe_key=dedupe_key,
            )
        except Exception:  # noqa: BLE001 — 요청은 이미 성공했다
            # Q2 의 남은 한 자리: 성공 뒤 삽입이 실패하면 그 요청은 **무과금으로
            # 샌다**. 되돌릴 것이 없으므로 응답을 뒤집지 않되(사용자는 결과를 이미
            # 받았다), 조용히 삼키지도 않는다 — 이 로그가 그 손실의 유일한 흔적이다.
            logger.exception(
                "usage ledger insert failed after a successful billable request "
                "(user=%s action=%s dedupe_key=%s) — the request is NOT reversed",
                user_id, action, dedupe_key,
            )


class GenerationJobCharger:
    """워커가 job 을 성공시켰을 때 원장에 쓰는 다리 (Q1-b=A).

    워커는 회원 가입 시각을 모르는데 주 창이 가입일 기준이라(8.1 P2-b) 창 키를
    계산하려면 필요하다 — 그래서 job 의 ``user_id`` 로 회원을 한 번 읽는다.
    **주체를 모르는 job 은 세지 않는다**(8.3 이전 행): 추측해서 남의 사용량에
    얹느니 안 세는 편이 오너 정책과 같은 방향이다.
    """

    def __init__(
        self, *, enforcement: QuotaEnforcementService, users: MemberLookup
    ) -> None:
        self._enforcement = enforcement
        self._users = users

    def charge(self, job) -> None:
        """**절대 올리지 않는다.** 차감 실패가 job 을 실패시키면 안 된다.

        job 이 RUNNING 으로 남으면 lease 만료 뒤 재차지되어 **같은 생성을 다시
        돌린다** — 91초짜리 GPU 작업이 사용량 기록 하나 때문에 반복되는 것은
        어느 쪽으로도 옳지 않다. 손실은 로그로 남는다(요청 경로의 같은 자리와
        같은 처리).
        """

        try:
            if job.user_id is None:
                return
            member = self._users.get_by_id(job.user_id)
            if member is None:
                # 회원이 지워졌는데 job 이 남았다 — 사용량을 얹을 대상이 없다.
                logger.warning(
                    "generation job %s succeeded for an unknown user %s; "
                    "not charged", job.id, job.user_id,
                )
                return
            self._enforcement.charge_completed_generation(
                user_id=job.user_id,
                member_created_at=member.created_at,
                target_project_id=job.project_id,
                request_id=job.request_id,
            )
        except Exception:  # noqa: BLE001 — 차감은 생성을 실패시키지 않는다
            logger.exception(
                "charging the successful generation job %s failed", job.id
            )
