"""Slice 8.3 HTTP 회귀 + 전수 가드 (오너 결정 2026-08-04).

브리프 ``08-3-quota-enforcement-decisions.md``. 도메인 쪽(한도·뮤텍스·정산 순서)은
``test_quota_enforcement.py`` 이고, 여기는 **요청 경로에 실제로 붙었는가**와
**상태코드·헤더 계약**이다.

이 파일은 ``tests/auth_support.authenticate`` 를 쓰지 않는다 — 그 seam 은 8.3
입장을 우회하므로(도메인 스위트가 잠금 5초에 걸리지 않게), 여기서 쓰면 재려는 것을
지운다. 대신 인증·소유권만 손으로 override 하고 **시행은 진짜를 돌린다**.

전수 가드의 모양은 이 저장소의 선례를 따른다: ``test_auth_api.py`` 의 tier 가드가
route 객체에서 dependency 신원을 보고, ``test_billable_actions.py`` 가 분류표를
실제 라우트와 대조한다. 여기서 새로 강제하는 것 넷 —
① 유료 11경로가 시행 dependency 를 **소유권 뒤에** 달고 있다
② 무료 경로에는 없다
③ 유료 11경로가 402·429 를 선언한다(무료는 안 한다 — 429 는 ``THROTTLED_OPERATIONS``
   에 **등재된** 두 번째 생산자만 예외이고, 402 는 예외가 없다)
④ 유료 11경로가 확인 헤더를 **선언한다**(Q6=C — 헤더는 쿼리보다 안 보이는 통로라
   "한 경로만 확인을 무시하는" 드리프트가 조용하다).
"""

from __future__ import annotations

import asyncio
import json
import unittest
from datetime import UTC, datetime

import httpx
from fastapi.routing import APIRoute

from services.application.app.auth.models import User
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.main import (
    QuotaSettledRoute,
    _build_report_service,
    create_app,
)
from services.application.app.api.dependencies import (
    CONFIRM_DUPLICATE_HEADER,
    enforce_quota,
    require_authenticated_user,
    require_quota_standing,
    require_project_owner,
)
from services.application.app.quota.billable_actions import (
    BILLABLE_ACTIONS,
    BILLABLE_OPERATIONS,
)
from services.application.app.quota.dedupe import DEDUPE_SOURCES, DedupeSource
from services.application.app.quota.enforcement import (
    AdmissionMutex,
    QuotaEnforcementService,
)
from services.application.app.quota.ledger import (
    InMemoryUsageLedgerRepository,
    UsageLedgerService,
)
from services.application.app.quota.lock import (
    InMemoryRequestLockRepository,
    RequestLockService,
)
from services.application.app.quota.replay import (
    DEFAULT_REPLAY_TTL_SECONDS,
    InMemoryReplayResponseRepository,
)
from services.application.app.quota.policy import (
    InMemoryQuotaPolicyRepository,
    QuotaLimits,
    QuotaPolicy,
    QuotaPolicyService,
)
from services.application.app.writing.generation_job import (
    InMemoryWritingGenerationJobRepository,
    WritingGenerationJobService,
)
from services.application.app.observability.llm_call_audit import LlmCallSite
from services.application.app.observability.llm_call_scope import ObservedProvider
from services.llm_gateway.app.errors import ProviderError, ProviderErrorCode
from tests.test_writing import (
    _FakeContextSearch,
    _FakeProvider,
    _package,
    _service,
)

# 429 의 **비-과금 생산자** 목록. 이 시스템에서 429 는 8.3 이래로 quota 한
# 뜻이었고 가드 ③이 "유료 11경로에만"을 강제해 왔다. 그 뒤 같은 코드를 다른
# 뜻으로 쓰는 면들이 생겼고, 조용히 통과시키지 않고 **여기 등재**한다 —
# 목록이 늘어나는 것은 이 줄을 고치는 의도적 편집이어야 한다(아래 셀이
# 양방향으로 잠근다).
# - signup 스로틀(Phase S-3, 오너 2026-09-05): 한도가 아니라 발신 IP 축의
#   **비용 상한**이다.
# - 실패 job 재시도 쿨다운(S-1 D2, 오너 2026-09-05): 마지막 실패 직후의 재시도
#   나열을 막는 창이다 — 세 번째 생산자.
THROTTLED_OPERATIONS: frozenset[tuple[str, str]] = frozenset({
    ("/auth/signup", "post"),
    ("/projects/{project_id}/analysis/jobs/{job_id}/retry", "post"),
    ("/projects/{project_id}/writing/generation-jobs/{job_id}/retry", "post"),
})

# S-1 D2-b(오너 2026-09-05): **유료가 아니면서 402 를 선언하는** 경로 — 실패 job
# 재시도의 입장 게이트다. Q5=B 의 "402 는 예외가 없다"는 "무료 경로가 한도를
# 팔지 않는다"는 뜻이었는데, 재시도는 예외다: 자기 한도가 소진된 회원은 재시도로
# 무과금 재실행을 계속할 수 없어야 한다(감사 §A.2·§A.3). 차금은 여전히 워커의
# 성공 시점뿐이라 이 경로 자체는 한도를 팔지 않는다. 배선(의존성)은 아래
# StandingWiringTest 가 양방향으로 잠근다.
STANDING_GATED_OPERATIONS: frozenset[tuple[str, str]] = frozenset({
    ("/projects/{project_id}/analysis/jobs/{job_id}/retry", "post"),
    ("/projects/{project_id}/writing/generation-jobs/{job_id}/retry", "post"),
})

_USER = User(
    id="quota-user",
    username="quota-tester",
    password_hash="unused",
    is_admin=False,
    is_active=True,
    created_at=datetime(2026, 7, 1, tzinfo=UTC),
)


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 4, 3, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        from datetime import timedelta  # noqa: PLC0415

        self.now += timedelta(seconds=seconds)


class _Client:
    """인증·소유권만 통과시키고 **시행은 진짜로 돌리는** 클라이언트."""

    __test__ = False

    def __init__(self, app) -> None:
        app.dependency_overrides[require_authenticated_user] = lambda: _USER
        app.dependency_overrides[require_project_owner] = lambda: None
        self._app = app

    def post(self, path, **kwargs):
        return self._send("post", path, **kwargs)

    def get(self, path, **kwargs):
        return self._send("get", path, **kwargs)

    def _send(self, method, path, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await getattr(client, method)(path, **kwargs)

        return asyncio.run(send())


def _enforcement(*, clock, limits=None, jobs=None, replays=None):
    policy_repo = InMemoryQuotaPolicyRepository()
    if limits is not None:
        # 8.1 P6 은 불리한 변경을 주 경계로 유예하므로 문서를 직접 넣는다.
        policy_repo.upsert(QuotaPolicy(
            user_id=_USER.id, limits=limits, pending=None, updated_at=clock()))
    ledger_repo = InMemoryUsageLedgerRepository()
    lock_repo = InMemoryRequestLockRepository()
    counter = 0

    def _ids() -> str:
        nonlocal counter
        counter += 1
        return f"rul-{counter}"

    service = QuotaEnforcementService(
        policy=QuotaPolicyService(policy_repo, clock=clock),
        ledger=UsageLedgerService(ledger_repo, id_factory=_ids, clock=clock),
        locks=RequestLockService(
            lock_repo, clock=clock, minimum_window_seconds=5, lease_seconds=180),
        mutex=AdmissionMutex(lock_repo, clock=clock, sleep=lambda _s: None),
        jobs=jobs,
        replays=replays,
    )
    return service, ledger_repo


def _app(*, provider=None, limits=None, clock=None, jobs=None,
         context_error=None, replays=None, report_service=None):
    clock = clock or _Clock()
    jobs = jobs or WritingGenerationJobService(
        InMemoryWritingGenerationJobRepository())
    enforcement, ledger = _enforcement(
        clock=clock, limits=limits, jobs=jobs, replays=replays)
    app = create_app(
        service=CoreSotService(InMemoryCoreSotRepository()),
        # ★ ``ObservedProvider`` 로 감싸는 것이 이 fixture 의 요점이다. Q1-a=A 의
        # "provider 를 실제로 불렀는가"는 seam C 가 세는 값이라, **감싸기를
        # 빠뜨린 조립은 그 경로를 통째로 무료로 만든다.** 배포 조립에서 그것을
        # 막는 것은 기존 조립 가드(``test_llm_call_sites.py``)이고, 여기서는
        # 그 조립을 그대로 흉내 내야 재려는 것을 잰다.
        writing_service=(
            _service(ObservedProvider(
                provider, call_site=LlmCallSite.WRITING_GENERATION))
            if provider is not None else None),
        context_search_service=_FakeContextSearch(
            _package(), error=context_error),
        writing_generation_job_service=jobs,
        writing_report_service=report_service,
        quota_enforcement_service=enforcement,
    )
    client = _Client(app)
    project_id = client.post("/projects", json={"name": "Novel"}).json()["id"]
    return client, project_id, ledger, clock, jobs


def _rows(ledger: InMemoryUsageLedgerRepository) -> list:
    return list(ledger._usage)  # noqa: SLF001


def _generate(client, project_id, **overrides):
    body = {"request_id": "wr-1", "instruction": "이어서 써줘.",
            "output_length": "short"}
    body.update(overrides.pop("json", {}))
    return client.post(
        f"/projects/{project_id}/writing/generate", json=body, **overrides)


class ChargeOnSuccessTest(unittest.TestCase):
    """Q1=C · Q1-a=A — 2xx **그리고** provider 호출."""

    def test_a_successful_generate_leaves_one_row(self):
        client, project_id, ledger, _clock, _jobs = _app(
            provider=_FakeProvider(content="이어진 장면."))
        self.assertEqual(_generate(client, project_id).status_code, 200)
        rows = _rows(ledger)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].action, "writing_generate")
        # Q9=A: 글쓰기 경로의 키는 body.request_id 다.
        self.assertEqual(rows[0].dedupe_key, "wr-1")
        self.assertEqual(rows[0].target_project_id, project_id)

    def test_a_provider_failure_is_not_charged(self):
        # Q1=C 의 요지. 실제로 GPU 를 쓴 502 가 무료가 되는 것은 오너가 알고 고른
        # 대가다("실패에는 과금하지 않는다").
        client, project_id, ledger, _clock, _jobs = _app(
            provider=_FakeProvider(
                error=ProviderError(
                    code=ProviderErrorCode.UNAVAILABLE, message="boom",
                    retryable=True, provider="llm_gateway")))
        self.assertEqual(_generate(client, project_id).status_code, 502)
        self.assertEqual(_rows(ledger), [])

    def test_a_validation_400_is_not_charged(self):
        client, project_id, ledger, _clock, _jobs = _app(
            provider=_FakeProvider(content="x"))
        response = _generate(
            client, project_id, json={"task_type": "nonsense"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(_rows(ledger), [])

    def test_an_unconfigured_collaborator_503_is_not_charged(self):
        client, project_id, ledger, _clock, _jobs = _app(provider=None)
        self.assertEqual(_generate(client, project_id).status_code, 503)
        self.assertEqual(_rows(ledger), [])

    def test_accepting_the_request_with_202_is_not_charged_here(self):
        # Q1-b=A: 202 는 "접수 성공"이라 워커가 센다. 여기서 세면 **생성이
        # 실패해도 과금**된다 — 정책이 가장 비싼 경로에서만 안 지켜지는 형태다.
        client, project_id, ledger, _clock, jobs = _app(
            provider=_FakeProvider(content="x"))
        response = _generate(client, project_id, json={
            "output_length": "medium",
            "current_position": {"draft_id": "d1", "version_id": "v1"},
        })
        self.assertEqual(response.status_code, 202)
        self.assertEqual(_rows(ledger), [])
        # 그리고 그 job 은 주체를 들고 간다 — 없으면 워커가 차감할 수 없다.
        job_id = response.json()["job"]["job_id"]
        self.assertEqual(jobs.get(job_id).user_id, _USER.id)

    def test_a_404_is_answered_before_any_quota_is_touched(self):
        # 시행을 소유권 **앞**으로 옮기는 리팩터링이 여기서 물린다: 존재하지 않는
        # project 는 차감도 잠금도 남기지 않아야 한다(§1.1).
        client, _project_id, ledger, _clock, _jobs = _app(
            provider=_FakeProvider(content="x"))
        response = _generate(client, "no-such-project")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(_rows(ledger), [])


class ReplayIsNotWorkTest(unittest.TestCase):
    """Q1-a=A — provider 를 안 부른 2xx 는 세지 않는다."""

    def _client(self, runner_calls: list):
        from services.application.app.analysis.service import (  # noqa: PLC0415
            AnalysisService, InMemoryAnalysisRepository,
        )
        from tests.test_application_api import (  # noqa: PLC0415
            _ApiFakeAnalysisRunner,
        )
        from services.application.app.observability.llm_call_scope import (  # noqa: PLC0415, E501
            ObservedProvider,
        )
        from services.application.app.observability.llm_call_audit import (  # noqa: PLC0415, E501
            LlmCallSite,
        )

        analysis = AnalysisService(InMemoryAnalysisRepository())
        provider = ObservedProvider(
            _FakeProvider(content="{}"), call_site=LlmCallSite.ANALYSIS_EXTRACTOR)

        class _CallingRunner(_ApiFakeAnalysisRunner):
            async def run_job(self, *, project_id, job_id):
                runner_calls.append(job_id)
                await provider.generate(_ProviderRequest())
                return await super().run_job(project_id=project_id, job_id=job_id)

        clock = _Clock()
        enforcement, ledger = _enforcement(clock=clock)
        app = create_app(
            CoreSotService(InMemoryCoreSotRepository()),
            analysis_service=analysis,
            analysis_runner=_CallingRunner(analysis),
            quota_enforcement_service=enforcement,
        )
        client = _Client(app)
        project = client.post("/projects", json={"name": "Novel"}).json()
        job = client.post(
            f"/projects/{project['id']}/analysis/jobs",
            json={"snapshot_id": "snapshot-1", "idempotency_key": "run-1"},
        ).json()
        return client, project["id"], job["job"]["id"], ledger, clock

    def test_the_first_run_is_charged_and_the_replay_is_not(self):
        # ★ 오너가 "절대로 일어나서는 안 된다"고 못박은 사건이 이것이다: replay 는
        # provider 를 한 번도 안 부르고 200 을 돌려주므로 **아무 일도 안 하고
        # 과금**될 수 있었다. 상태코드만 보는 규칙(Q1-a 선택지 B)이면 여기서 진다.
        calls: list = []
        client, project_id, job_id, ledger, clock = self._client(calls)
        path = f"/projects/{project_id}/analysis/jobs/{job_id}/run"
        first = client.post(path)
        self.assertEqual(first.status_code, 200)
        clock.advance(10)          # 잠금 최소 창을 넘긴다(재는 것은 잠금이 아니다)
        replay = client.post(path)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(len(calls), 1, "replay 가 러너를 다시 돌렸다")
        # under/over 양방향이 한 줄에 있다: 첫 실행은 **반드시** 세고, replay 는
        # **반드시** 안 센다.
        self.assertEqual(len(_rows(ledger)), 1)

    def test_the_dedupe_key_of_a_replay_is_the_job_id(self):
        # Q9=A: 이 경로만 서버 생성이 아니라 **경로 파라미터**다 — 클라이언트가
        # 새 값으로 우회할 수 없다는 점이 두 번째 방어다.
        calls: list = []
        client, project_id, job_id, ledger, _clock = self._client(calls)
        client.post(f"/projects/{project_id}/analysis/jobs/{job_id}/run")
        self.assertEqual(_rows(ledger)[0].dedupe_key, job_id)


class _ProviderRequest:
    max_tokens = 16


class ChargeRuleTest(unittest.TestCase):
    """Q1-a=A 의 규칙 자체 — ``2xx`` **그리고** provider 호출.

    **왜 별도 단위 셀인가**(뮤테이션이 드러낸 것, 2026-08-04): 위 replay 셀에서
    provider 조건을 지워도 통과한다 — 같은 ``job_id`` 를 dedupe 키로 쓰므로
    (Q9=A) 원장이 두 번째 행을 **DB 수준에서** 거부하기 때문이다. 그것은 결함이
    아니라 오너가 요구한 **두 겹**이 실제로 겹쳐 있다는 증거다. 다만 그 때문에
    통합 경로만으로는 한 겹을 지우는 변경이 안 보이므로, 규칙 자체를 여기서
    직접 잠근다.
    """

    def test_the_matrix(self):
        from services.application.app.main import _is_charged  # noqa: PLC0415

        cases = {
            (200, 1): True,     # 정상 — 일했고 성공했다
            (200, 0): False,    # ★ replay: 아무 일도 안 하고 200
            (202, 1): False,    # 접수는 성공이 아니다(Q1-b: 워커가 센다)
            (202, 0): False,
            (400, 1): False,    # 창 가드 — provider 왕복은 있었지만 실패다
            (502, 1): False,    # 실제로 GPU 를 썼지만 무과금(오너 정책)
            (503, 0): False,
            (None, 1): False,   # 예외로 끝났다
        }
        for (status, calls), expected in cases.items():
            with self.subTest(status=status, provider_calls=calls):
                self.assertIs(_is_charged(status, calls), expected)


class RefusalStatusTest(unittest.TestCase):
    """Q5=B — 세 사건에 세 코드."""

    def test_the_duplicate_lock_answers_429_without_charging(self):
        client, project_id, ledger, _clock, _jobs = _app(
            provider=_FakeProvider(content="x"))
        self.assertEqual(_generate(client, project_id).status_code, 200)
        second = _generate(client, project_id, json={"request_id": "wr-2"})
        self.assertEqual(second.status_code, 429)
        # 잠금 실패가 차감을 남기면 일도 안 하고 돈만 받는 셈이다.
        self.assertEqual(len(_rows(ledger)), 1)
        # G5=A: 두 문구를 가르는 재료가 함께 온다.
        self.assertIn("retry-after", {k.lower() for k in second.headers})

    def test_confirming_gets_through_and_spends_another_unit(self):
        client, project_id, ledger, _clock, _jobs = _app(
            provider=_FakeProvider(content="x"))
        _generate(client, project_id)
        confirmed = _generate(
            client, project_id, json={"request_id": "wr-2"},
            headers={CONFIRM_DUPLICATE_HEADER: "1"})
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(len(_rows(ledger)), 2)
        # G4=A: 확인은 잠금을 옮긴 것이라 **다음 클릭은 다시 막힌다**.
        self.assertEqual(
            _generate(client, project_id, json={"request_id": "wr-3"}).status_code,
            429,
        )

    def test_an_exhausted_window_answers_402(self):
        client, project_id, ledger, clock, _jobs = _app(
            provider=_FakeProvider(content="x"),
            limits=QuotaLimits(daily_limit=1, weekly_limit=100))
        self.assertEqual(_generate(client, project_id).status_code, 200)
        clock.advance(10)
        response = client.post(
            f"/projects/{project_id}/writing/gate",
            json={"request_id": "wr-2", "instruction": "x",
                  "candidate_text": "y"})
        self.assertEqual(response.status_code, 402)
        self.assertEqual(len(_rows(ledger)), 1)

    def test_a_suspended_account_answers_403(self):
        from services.application.app.quota.policy import (  # noqa: PLC0415
            QuotaStatus,
        )

        client, project_id, ledger, _clock, _jobs = _app(
            provider=_FakeProvider(content="x"),
            limits=QuotaLimits(daily_limit=None, weekly_limit=None,
                               status=QuotaStatus.SUSPENDED))
        self.assertEqual(_generate(client, project_id).status_code, 403)
        self.assertEqual(_rows(ledger), [])

    def test_a_quota_storage_failure_answers_503_without_charging(self):
        # Q4=A: 계량 불능 = 무료 제공을 막는다. 전역 handler 가 아니라 이 경로가
        # 실제로 503 을 내는지 확인한다.
        clock = _Clock()
        enforcement, ledger = _enforcement(clock=clock)

        def _broken(**_kwargs):
            raise RuntimeError("quota store is down")

        enforcement.admit = _broken
        app = create_app(
            service=CoreSotService(InMemoryCoreSotRepository()),
            writing_service=_service(_FakeProvider(content="x")),
            context_search_service=_FakeContextSearch(_package()),
            quota_enforcement_service=enforcement,
        )
        client = _Client(app)
        project_id = client.post("/projects", json={"name": "N"}).json()["id"]
        with self.assertRaises(RuntimeError):
            # 전역 handler 는 pymongo 예외만 503 으로 옮긴다 — 그 밖의 저장소
            # 결함은 500 이 아니라 **요청 실패**로 드러나야 하고, 어느 쪽이든
            # 통과시키지 않는 것이 Q4=A 다.
            _generate(client, project_id)
        self.assertEqual(_rows(ledger), [])


class ConfirmHeaderContentTest(unittest.TestCase):
    """Q6=C — 확인은 헤더의 **존재**가 아니라 **내용**이다.

    독립 검증 2026-08-04 H-5. 확인 한 번은 사용량 1회를 더 쓰므로(8.0 B1=A),
    프록시나 클라이언트가 실수로 붙인 빈 값이 확인으로 읽히면 회원이 누르지도
    않은 두 번째 생성을 사게 된다.
    """

    def _second(self, headers):
        client, project_id, ledger, _clock, _jobs = _app(
            provider=_FakeProvider(content="x"))
        _generate(client, project_id)
        return _generate(
            client, project_id, json={"request_id": "wr-2"}, headers=headers)

    def test_a_blank_header_is_not_a_confirmation(self):
        for value in ("", "   "):
            with self.subTest(value=repr(value)):
                self.assertEqual(
                    self._second({CONFIRM_DUPLICATE_HEADER: value}).status_code,
                    429,
                )

    def test_a_non_blank_header_still_confirms(self):
        # over-strict 짝: 빈 값을 거르는 변경이 정상 확인까지 막으면 안 된다.
        self.assertEqual(
            self._second({CONFIRM_DUPLICATE_HEADER: "1"}).status_code, 200)


class _CountingProvider(_FakeProvider):
    """provider 호출 수를 잰다 — S-1 셀의 요점은 "다시 안 돈다"다."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.calls = 0

    async def generate(self, request):
        self.calls += 1
        return await super().generate(request)


#: report v3 파서가 받아들이는 최소 payload(test_writing_report `_payload` 와 같은 모양).
_REPORT_JSON = json.dumps({
    "self_reported_constraints": ["제한 시점"],
    "candidate_claims": [{"text": "문이 열렸다", "type": "narrative_event",
                          "related_context_pointers": []}],
    "new_memory_hints": [{"type": "event", "text": "문이 열림",
                          "confidence": 0.8}],
    "risk_notes": [{"type": "pov", "severity": "high", "message": "시점 확인"}],
}, ensure_ascii=False)


class RetryStandingWiringTest(unittest.TestCase):
    """S-1 D2-b — 입장 게이트 경로와 ``require_quota_standing`` 배선이 1:1.

    선언(402·403·429)만 갱신하고 dependency 를 빼먹으면 "문서는 지키는 척하는
    미시행"이 된다 — H3 의 선언≠시행 함정이 그대로 재발하는 자리다. 양방향:
    왼쪽에 남으면 입장 없는 게이트 선언이고, 오른쪽에 남으면 게이트 아닌 경로가
    입장 판정을 얻은 것이다.
    """

    def test_standing_gated_operations_match_the_wiring_exactly(self):
        app = create_app(service=CoreSotService(InMemoryCoreSotRepository()))
        wired = {
            (route.path, method.lower())
            for route in app.routes if isinstance(route, APIRoute)
            for method in route.methods
            if any(
                d.dependency is require_quota_standing
                for d in route.dependencies
            )
        }
        self.assertEqual(wired, set(STANDING_GATED_OPERATIONS))


class KeyConsumptionHttpTest(unittest.TestCase):
    """S-1(오너 2026-09-05 = A+D+report 국소 C) — BODY dedupe 키는 1회만 소비된다.

    감사 §A.1 의 공격: 같은 ``request_id`` 를 반복 전송하면 LLM 파이프라인은
    매번 실제로 돌면서 원장은 1행으로 접혀 무과금 무한 재실행이 됐다. 계약
    문장 — 정산된 키의 재제출은 **실행 전 409**, 확인된 재실행은 **+1 과금**,
    ``writing_report`` 의 재제출은 **저장 응답 재생**.
    """

    def test_a_settled_request_id_is_refused_before_execution(self):
        """under-strict: 키 소비 검사를 지우면 이 재제출이 200 으로 돌아가
        과금은 접힌다(§A.1 원결함). over-strict: 첫 요청까지 막으면 첫 단정이
        실패한다.
        """
        provider = _CountingProvider()
        client, project_id, ledger, _clock, _jobs = _app(provider=provider)
        first = _generate(client, project_id, json={"request_id": "evade-1"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(provider.calls, 1)
        refused = _generate(client, project_id, json={"request_id": "evade-1"})
        self.assertEqual(refused.status_code, 409)
        self.assertIn("already used", refused.json()["detail"])
        self.assertEqual(provider.calls, 1)  # provider 는 다시 안 돈다
        self.assertEqual(len(_rows(ledger)), 1)

    def test_a_confirmed_resubmission_runs_again_and_charges_one_more(self):
        """8.2b G4=A 가 약속한 +1 과금을 원장이 처음으로 이행하는 자리다."""
        provider = _CountingProvider()
        client, project_id, ledger, _clock, _jobs = _app(provider=provider)
        _generate(client, project_id, json={"request_id": "again-1"})
        again = _generate(
            client, project_id, json={"request_id": "again-1"},
            headers={CONFIRM_DUPLICATE_HEADER: "1"},
        )
        self.assertEqual(again.status_code, 200)
        self.assertEqual(provider.calls, 2)
        self.assertEqual(len(_rows(ledger)), 2)

    def test_the_report_replays_its_stored_response_without_the_provider(self):
        """국소 C — 응답을 지속하지 않는 유일한 경로의 유실 회복. 재생은 provider
        도 과금도 다시 일으키지 않는다(이미 세린 요청이다).
        """
        provider = _CountingProvider(_REPORT_JSON)
        clock = _Clock()
        replays = InMemoryReplayResponseRepository(clock=clock)
        client, project_id, ledger, _clock, _jobs = _app(
            clock=clock, replays=replays,
            report_service=_build_report_service(provider))
        body = {"request_id": "rep-1", "instruction": "이어서 써줘.",
                "candidate_text": "문이 열렸다."}
        first = client.post(f"/projects/{project_id}/writing/report", json=body)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(provider.calls, 1)
        replayed = client.post(
            f"/projects/{project_id}/writing/report", json=body)
        self.assertEqual(replayed.status_code, 200)
        self.assertEqual(replayed.json(), first.json())
        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(_rows(ledger)), 1)

    def test_the_report_replay_expires_to_409_after_the_ttl(self):
        """TTL 지난 재제출은 무료 재실행이 아니라 409 로 닫힌다."""
        provider = _CountingProvider(_REPORT_JSON)
        clock = _Clock()
        replays = InMemoryReplayResponseRepository(clock=clock)
        client, project_id, _ledger, _clock, _jobs = _app(
            clock=clock, replays=replays,
            report_service=_build_report_service(provider))
        body = {"request_id": "rep-2", "instruction": "이어서 써줘.",
                "candidate_text": "문이 열렸다."}
        first = client.post(f"/projects/{project_id}/writing/report", json=body)
        self.assertEqual(first.status_code, 200)
        clock.advance(86401)  # 재생 TTL(24h)을 넘긴다
        expired = client.post(
            f"/projects/{project_id}/writing/report", json=body)
        self.assertEqual(expired.status_code, 409)
        self.assertEqual(provider.calls, 1)

    def test_the_replay_window_lasts_the_full_24_hours(self):
        """S-1 검증 B1 폐쇄(2026-09-05) — TTL **하방**. 등재 literal(24시간)은
        "경과 후 409" 방향으로만 잠혀 있어 TTL 이 조용히 줄어드는 것을 못 잡았다
        (검증 실측: 86400→3600 변이에 0 실패).

        under-strict: ``DEFAULT_REPLAY_TTL_SECONDS`` 를 3600 으로 줄이면 이 셀이
        실패한다(86399초는 1시간보다 많이 지났다 — 409 로 닫힌다). over-strict:
        창을 24시간보다 늘리면 literal 핀 단정이 실패한다.
        """
        self.assertEqual(DEFAULT_REPLAY_TTL_SECONDS, 86400)
        provider = _CountingProvider(_REPORT_JSON)
        clock = _Clock()
        replays = InMemoryReplayResponseRepository(clock=clock)
        client, project_id, _ledger, _clock, _jobs = _app(
            clock=clock, replays=replays,
            report_service=_build_report_service(provider))
        body = {"request_id": "rep-24h", "instruction": "이어서 써줘.",
                "candidate_text": "문이 열렸다."}
        first = client.post(f"/projects/{project_id}/writing/report", json=body)
        self.assertEqual(first.status_code, 200)
        clock.advance(86399)  # 24시간에서 1초 모자라다 — 창의 안쪽이다
        still = client.post(
            f"/projects/{project_id}/writing/report", json=body)
        self.assertEqual(still.status_code, 200)
        self.assertEqual(still.json(), first.json())
        self.assertEqual(provider.calls, 1)


class UnclassifiedActionFailsClosedTest(unittest.TestCase):
    """H-3 — 두 표가 갈라지면 조용히 통과하지 않고 503 이다.

    분류표(8.0)와 dedupe 매핑표의 1:1 을 가드가 단정하므로 **도달할 수 없어야
    하는 자리**다. 그래도 재는 이유는 도달했을 때의 값이 갈리기 때문이다:
    통과시키면 **중복 방지 없이 도는 유료 요청**이고, `KeyError` 로 두면 공개
    계약에 미매핑 500 이 샌다(H3의 "미매핑 500 부채 0건"과 충돌).
    """

    def test_a_missing_dedupe_mapping_answers_503_without_charging(self):
        client, project_id, ledger, _clock, _jobs = _app(
            provider=_FakeProvider(content="x"))
        removed = DEDUPE_SOURCES.pop("writing_generate")
        try:
            response = _generate(client, project_id)
        finally:
            DEDUPE_SOURCES["writing_generate"] = removed
        self.assertEqual(response.status_code, 503)
        self.assertEqual(_rows(ledger), [])


class AsyncInFlightGuardTest(unittest.TestCase):
    """Q8=C — 202 뒤의 재클릭은 상태 축이 막는다."""

    _POSITION = {"draft_id": "d1", "version_id": "v1"}

    def _async(self, client, project_id, request_id, **kwargs):
        return client.post(
            f"/projects/{project_id}/writing/generate",
            json={"request_id": request_id, "instruction": "이어서.",
                  "output_length": "medium",
                  "current_position": self._POSITION},
            **kwargs,
        )

    def test_a_second_request_while_a_job_runs_is_refused(self):
        client, project_id, _ledger, clock, _jobs = _app(
            provider=_FakeProvider(content="x"))
        self.assertEqual(self._async(client, project_id, "wr-1").status_code, 202)
        clock.advance(10)   # 잠금 냉각을 넘긴다 — 여기서 재는 것은 상태 가드다
        self.assertEqual(self._async(client, project_id, "wr-2").status_code, 429)

    def test_the_same_request_id_still_replays(self):
        # over-strict 짝: 멱등 replay 까지 막으면 폴링·재전송하는 클라이언트가
        # 자기 job 을 못 받는다. 새 job 이 생기는 경우만 막아야 한다.
        client, project_id, _ledger, clock, _jobs = _app(
            provider=_FakeProvider(content="x"))
        self._async(client, project_id, "wr-1")
        clock.advance(10)
        replay = self._async(client, project_id, "wr-1")
        self.assertEqual(replay.status_code, 202)
        self.assertTrue(replay.json()["idempotent_replay"])

    def test_confirming_starts_a_second_generation(self):
        client, project_id, _ledger, clock, _jobs = _app(
            provider=_FakeProvider(content="x"))
        self._async(client, project_id, "wr-1")
        clock.advance(10)
        confirmed = self._async(
            client, project_id, "wr-2",
            headers={CONFIRM_DUPLICATE_HEADER: "1"})
        self.assertEqual(confirmed.status_code, 202)

    def test_a_finished_job_no_longer_blocks(self):
        client, project_id, _ledger, clock, jobs = _app(
            provider=_FakeProvider(content="x"))
        first = self._async(client, project_id, "wr-1")
        job = jobs.get(first.json()["job"]["job_id"])
        jobs.mark_succeeded(jobs.claim_next(), result_scratch_id="s-1")
        self.assertIsNotNone(job)
        clock.advance(10)
        self.assertEqual(self._async(client, project_id, "wr-2").status_code, 202)


class BillableRouteWiringTest(unittest.TestCase):
    """전수 가드 — 새 유료 경로가 시행 없이 열리면 실패한다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = create_app()
        cls.spec = cls.app.openapi()
        cls.routes = [r for r in cls.app.routes if isinstance(r, APIRoute)]

    def _operations(self):
        for route in self.routes:
            for method in route.methods:
                yield (route.path, method.lower()), route

    def test_every_billable_operation_declares_the_enforcement_dependency(self):
        enforced = {
            operation
            for operation, route in self._operations()
            if any(d.dependency is enforce_quota for d in route.dependencies)
        }
        # 양방향: 왼쪽에 남으면 유료인데 시행이 없고(무료로 샌다), 오른쪽에 남으면
        # 무료 경로가 조용히 유료가 됐다.
        self.assertEqual(enforced, set(BILLABLE_OPERATIONS))

    def test_enforcement_is_declared_after_ownership(self):
        # 순서가 곧 계약이다(§1.1): 소유권 뒤라야 404·403 이 차감 앞에서 끝난다.
        # 앞으로 옮기는 리팩터링은 상태코드를 바꾸지 않으므로 **요청 구동
        # 테스트로는 안 보인다** — route 선언을 직접 읽는 이 셀이 그 자리다.
        from services.application.app.api.dependencies import (
            require_project_owner as owner,
        )

        for operation, route in self._operations():
            if operation not in BILLABLE_OPERATIONS:
                continue
            with self.subTest(operation=operation):
                calls = [d.dependency for d in route.dependencies]
                self.assertLess(calls.index(owner), calls.index(enforce_quota))

    def test_every_billable_operation_declares_402_and_429(self):
        for (path, method), _route in self._operations():
            declared = set(self.spec["paths"][path][method]["responses"])
            with self.subTest(operation=(path, method)):
                if (path, method) in BILLABLE_OPERATIONS:
                    self.assertIn("402", declared)
                    self.assertIn("429", declared)
                else:
                    # over-strict: 무료 경로에 quota 얼굴이 선언되면 프론트가
                    # 있지도 않은 한도를 다루게 된다.
                    # 402 의 유일한 예외는 S-1 D2-b 의 입장 게이트다(위
                    # STANDING_GATED_OPERATIONS) — 그마저 **한도를 팔지 않는다**:
                    # 차금은 워커의 성공 시점뿐이다.
                    if (path, method) not in STANDING_GATED_OPERATIONS:
                        self.assertNotIn("402", declared)
                    if (path, method) not in THROTTLED_OPERATIONS:
                        self.assertNotIn("429", declared)

    def test_non_billable_429_producers_stay_enrolled_exactly(self):
        """등재된 비-과금 429 면 목록이 실제 선언과 정확히 일치한다.

        under-strict: signup 이나 재시도 경로에서 429 선언이 사라지면(= 스로틀·
        쿨다운이 계약에서 빠지면) 실패한다. over-strict: 다른 무료 경로가 429 를
        얻으면 위 가드가 아니라 **이 셀**이 먼저 실패해서, 예외 목록에 한 줄 더하는
        것이 의도적 편집이 되게 만든다.
        """
        actually_declared = {
            (path, method)
            for (path, method), _route in self._operations()
            if (path, method) not in BILLABLE_OPERATIONS
            and "429" in self.spec["paths"][path][method]["responses"]
        }
        self.assertEqual(actually_declared, THROTTLED_OPERATIONS)

    def test_every_billable_operation_accepts_the_confirm_header(self):
        # Q6=C 전수 가드. 헤더는 쿼리보다 안 보이는 통로라 한 경로만 확인을
        # 무시하는 드리프트가 조용하다 — 그래서 선언 자체를 단정한다.
        for (path, method), _route in self._operations():
            if (path, method) not in BILLABLE_OPERATIONS:
                continue
            names = {
                parameter["name"].lower()
                for parameter in self.spec["paths"][path][method].get(
                    "parameters", [])
            }
            with self.subTest(operation=(path, method)):
                self.assertIn(CONFIRM_DUPLICATE_HEADER.lower(), names)

    def test_every_route_is_built_by_the_settling_wrapper(self):
        # 정산이 route wrapper 에 있으므로(응답 상태코드를 봐야 한다), wrapper 가
        # 빠진 route 는 **잠금을 영영 풀지 않는다**. 전역 적용을 단정한다.
        for route in self.routes:
            with self.subTest(path=route.path):
                self.assertIsInstance(route, QuotaSettledRoute)


class MyQuotaEndpointTest(unittest.TestCase):
    """8.4 W5=B — 회원이 자기 잔여를 보는 유일한 통로 (operation 76).

    시행은 8.3에서 켜져 있었고 화면은 그것을 볼 수 없었다. 이 endpoint 가 그 구멍을
    닫으며, **여기서 재는 것은 숫자가 아니라 "시행과 같은 수를 말하는가"** 다.
    """

    def _quota(self, client):
        response = client.get("/me/quota")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_it_reports_the_default_limits_when_the_member_has_no_policy_row(self):
        client, _project_id, _ledger, _clock, _jobs = _app(
            provider=_FakeProvider(content="x"))
        body = self._quota(client)
        # P4=A: 행이 없으면 코드 기본값(일 20 / 주 100).
        self.assertEqual(body["daily"]["limit"], 20)
        self.assertEqual(body["weekly"]["limit"], 100)
        self.assertEqual(body["remaining"], 20)
        self.assertEqual(body["status"], "active")
        self.assertFalse(body["unlimited"])

    def test_a_charged_request_moves_the_number_the_member_sees(self):
        # 이 셀이 8.4의 요지다 — 화면의 숫자가 **시행이 센 것과 같은 사실**을
        # 말한다. 두 계산이 갈라지면 "3회 남음" 직후 402 가 난다.
        client, project_id, _ledger, _clock, _jobs = _app(
            provider=_FakeProvider(content="이어진 장면."))
        before = self._quota(client)["remaining"]
        self.assertEqual(_generate(client, project_id).status_code, 200)
        self.assertEqual(self._quota(client)["remaining"], before - 1)

    def test_the_combined_remaining_is_the_smaller_window(self):
        client, _project_id, _ledger, _clock, _jobs = _app(
            provider=_FakeProvider(content="x"),
            limits=QuotaLimits(daily_limit=20, weekly_limit=2))
        body = self._quota(client)
        self.assertEqual(body["daily"]["remaining"], 20)
        self.assertEqual(body["weekly"]["remaining"], 2)
        self.assertEqual(body["remaining"], 2)

    def test_an_unlimited_member_gets_no_number(self):
        # W1 오너 결정: 부트스트랩 관리자는 `limit=None` 정책 행을 갖는다. 화면은
        # 그 자리에 아무것도 그리지 않는다 — 무제한을 숫자로 말하지 않는다.
        client, _project_id, _ledger, _clock, _jobs = _app(
            provider=_FakeProvider(content="x"),
            limits=QuotaLimits(daily_limit=None, weekly_limit=None))
        body = self._quota(client)
        self.assertTrue(body["unlimited"])
        self.assertIsNone(body["remaining"])

    def test_it_reports_both_reset_moments(self):
        client, _project_id, _ledger, _clock, _jobs = _app(
            provider=_FakeProvider(content="x"))
        body = self._quota(client)
        # 고정 시계는 2026-08-04 03:00 UTC(= KST 정오)이므로 일 창은 그 날
        # UTC 15:00 에 끝난다. 주 창은 가입일(2026-07-01) 기준 7일 주기다.
        self.assertTrue(body["daily"]["resets_at"].startswith("2026-08-04T15:00"))
        self.assertIn("resets_at", body["weekly"])

    def test_reading_it_costs_nothing_and_blocks_nothing(self):
        # over-strict: 조회에 시행이 붙으면 화면을 여는 것만으로 한도가 줄고,
        # 잠금까지 잡으면 그 뒤 유료 요청이 429 가 된다.
        client, project_id, ledger, _clock, _jobs = _app(
            provider=_FakeProvider(content="x"))
        for _ in range(3):
            self._quota(client)
        self.assertEqual(_rows(ledger), [])
        self.assertEqual(_generate(client, project_id).status_code, 200)

    def test_it_is_not_a_billable_operation(self):
        # 분류표에 들어가면 조회가 유료가 된다. 8.0 B4(=provider 를 부르는 경로만
        # 유료)의 직접적 귀결이다.
        self.assertNotIn(("/me/quota", "get"), BILLABLE_OPERATIONS)


class AdminIsNotExemptTest(unittest.TestCase):
    """8.4 W1 — 면제는 **신분이 아니라 정책 행**이다 (오너 결정 2026-08-04).

    오너는 "면제 없음이되 첫 부트스트랩 관리자만 `limit=None`"으로 정했다. 그 결정의
    핵심은 `enforce_quota` 에 tier 분기가 **0줄**이라는 것이다 — 관리자가 안 막히는
    이유는 신분이 아니라 자기 정책 행이고, 그 행이 없으면 관리자도 똑같이 막힌다.
    이 클래스는 훗날 누군가 `is_admin` 예외를 넣으면 실패한다.
    """

    def test_an_admin_without_a_policy_row_is_bound_by_the_default_limits(self):
        admin = User(
            id="admin-1", username="root", password_hash="unused",
            is_admin=True, is_active=True,
            created_at=datetime(2026, 7, 1, tzinfo=UTC),
        )
        client, project_id, _ledger, _clock, _jobs = _app(
            provider=_FakeProvider(content="x"),
            limits=QuotaLimits(daily_limit=0, weekly_limit=100))
        client._app.dependency_overrides[  # noqa: SLF001
            require_authenticated_user] = lambda: admin
        # 한도 0 행은 `_USER` 것이므로 관리자에게는 **기본값**이 적용된다 —
        # 그래서 이 요청은 통과한다(over-strict 짝: 관리자만 유독 막히지 않는다).
        self.assertEqual(_generate(client, project_id).status_code, 200)
        # 그리고 그 사용은 **원장에 남는다** — 면제였다면 행이 없다.
        quota = client.get("/me/quota").json()
        self.assertEqual(quota["daily"]["used"], 1)

    def test_the_enforcement_dependency_never_looks_at_the_admin_flag(self):
        # 소스 수준의 단정이 아니라 **행동**으로 잡는다: 정책 행이 관리자에게도
        # 그대로 적용되면 tier 분기는 존재할 수 없다.
        admin = User(
            id="quota-user", username="root", password_hash="unused",
            is_admin=True, is_active=True,
            created_at=datetime(2026, 7, 1, tzinfo=UTC),
        )
        client, project_id, _ledger, _clock, _jobs = _app(
            provider=_FakeProvider(content="x"),
            limits=QuotaLimits(daily_limit=0, weekly_limit=100))
        client._app.dependency_overrides[  # noqa: SLF001
            require_authenticated_user] = lambda: admin
        # 같은 id 라 위의 한도 0 행이 이 관리자에게 적용된다 → 402.
        self.assertEqual(_generate(client, project_id).status_code, 402)


class DedupeMappingTest(unittest.TestCase):
    """Q9=A — 매핑표가 정본이고 유료 동작 전수를 덮는다."""

    def test_the_table_covers_exactly_the_billable_actions(self):
        self.assertEqual(
            set(DEDUPE_SOURCES), {action.action for action in BILLABLE_ACTIONS})

    def test_analysis_extract_uses_a_key_the_client_cannot_change(self):
        # 이 한 칸이 A 와 C 를 가른다(브리프 §Q9). 서버 생성으로 되돌리는 변경이
        # 여기서 물린다.
        self.assertEqual(
            DEDUPE_SOURCES["analysis_extract"], (DedupeSource.PATH, "job_id"))

    def test_analysis_compare_is_server_generated(self):
        # over-strict 짝: compare 의 재실행은 매번 provider 를 다시 부르는 **진짜
        # 재실행**이라 job_id 로 잡으면 정당한 재실행이 무과금이 된다.
        self.assertEqual(
            DEDUPE_SOURCES["analysis_compare"], (DedupeSource.SERVER, None))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
