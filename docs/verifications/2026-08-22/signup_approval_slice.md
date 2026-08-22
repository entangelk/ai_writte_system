# 자기 가입(승인제) 슬라이스 + 보안 점검 — 독립 검증

## Subject metadata

- 날짜: 2026-08-22 (검증 세션 — 구현 세션과 다른 AI 세션)
- 요청자: 오너 — *"작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?"*
- 대상: `bee4867…b6cee5d` 9커밋 (승인제 가입 1-a~1-g + 전수 가드 등재 + 문서).
  커밋 후보 전부 HEAD 에 포함, 작업 트리 클린에서 검증.
- 정규 스펙: [`plans/auth-signup-approval-decisions.md`](../../plans/auth-signup-approval-decisions.md)
  (Resolved 2026-08-22, 오너 3결정 + 파생 P-1~P-7) + SoT **v1.7.97** 변경이력.
- 소스: 커밋 `bee4867`·`4cc16f8`·`ab12fcd`·`99e0b2b`·`241896c`·`2b197f8`·`da9d5d5`·`8eab5c6`·`b6cee5d`.

## Scope

- 계약: 브리프 P-1~P-7 전 조항을 코드를 보기 전 경계 행렬로 먼저 세웠다
  (가입 201/409/400/재요청, 게이트 순서 「자격증명→status 403→C-6 409→세션」,
  틀린 비밀번호=401 통일, 잠금 중 정답 401, pending 행만 동작, ADMIN 8→11,
  TTL env 기동 거부, 레거시 행 active 기본 해석).
- ★ 최우선 의심 축: ① 로그인 게이트 순서(열거 방어가 403 앞에서 무너지는가)
  ② 승인 우회 경로(활성 행 덮어쓰기·비활성화 부활·재요청의 과잉/과소)
  ③ 잠금의 실제 강도(역치·리셋·라우터 조기 검사)
  ④ **SoT 본문 ↔ v1.7.97 버전 로그의 자기 일관성**(브리프 P-5가 "SoT 에 명시"를 요구).
- 구현: `auth/users.py`·`auth/models.py`·`auth/users_mongo.py`·`auth/login_guard.py`·
  `auth/login_guard_mongo.py`·`routers/auth.py`·`routers/admin.py`·`main.py`(조립·env 가드)·
  `api/models.py`·`api/errors.py`·`activity/actions.py`·프론트 3파일.
- 회귀셀: 신규 49셀(아래 Findings 대조) 전수 정독 — 감사의 대상.
- 전수 수트: 백엔드·프론트 독립 재실행.
- 뮤테이션: 검증자 자체 설계 10종(작업자 8종과 독립).
- 실서비스 관통: nginx 5520 경유 + 직접 8520 + Mongo 직접 관찰.
- 문서: work_log 세션 5·CHANGELOG·HANDOFF·SoT v1.7.97·plans 인덱스.

## Methodology

재현 환경(측정의 일부): WSL2, 메인 스택 10컨테이너 기동 중(재빌드 후 healthy 8+워커 2),
**test-mongo 기동**(`docker compose -f docker-compose.test.yml up -d` — 없으면 119 skip),
프론트는 반드시 `frontend/` 디렉터리에서(work_log 경고: 루트 실행 274 failed 는 아티팩트).

```bash
git status --short                       # 빈 것 확인(뮤테이션 전 게이트)
docker compose -f docker-compose.test.yml up -d
python3 -m pytest -q tests/              # 2480 passed, 4 skipped (3:26)
python3 -m pytest -q tests/              # 무인프라 대조: 2365 passed, 119 skipped
cd frontend && npx vitest run            # 331 passed (28 files, 76.6s)
cd frontend && npm run build             # 진입 425.35 kB — SoT 주장과 소수점까지 일치
# 뮤테이션: Edit 로 변이 → 표적 셀 실행(요약 count 줄로 판독) →
#   cd /mnt/f/devel/ai_writte_system && git checkout -- <path> → git status --short 빈 확인
# 실관통: curl http://localhost:5520/api/... (가입·로그인·잠금) +
#   docker exec …mongosh (status flip·login_failures·시드 관찰)
```

## Findings

### 1. 정량 클레임 — 전부 재현

| 클레임 | 실측 | 판정 |
|---|---|---|
| 백엔드 전수 2480 passed / 0 failed / skip 4 | 2480 / 0 / skip 4 (test-mongo 기동 조건) | 일치 — 단 **환경 조건이 숫자의 일부**: 무인프라면 2365/119 skip(총셀 2484로 동일) |
| 프론트 331 passed | 331 passed / 28 files | 일치 |
| build 진입 425.35 kB(+3.57) | 425.35 kB 직접 빌드 | 일치 |
| ADMIN 8→11, 총 operation 82, 공개 4→5 | tier 가드(`CombinedBoundaryMatrixTest` tiers=82)·에러 선언 가드(len=11)·공개 면제 셀로 확인 | 일치 |
| 컨테이너 healthy 8 + 워커 2 | healthy 8(healthcheck) + worker 2(up) | 일치 |

**SoT v1.7.97 신규 셀 수 주장은 부정확**: "신규 47셀(도메인 15·Mongo 4·가드 8·TTL 4·HTTP 16)"
→ 실측 **49셀**(Mongo **6**), "frontend 신규 8셀" → 실측 **5셀**(App 3 + AdminConsole 2).
총검증 판정에 영향 없는 기록 정확성 오류(H-4).

### 2. 코드 감각 감사 — 경계 행렬 전 셀 충족

- **P-3 재요청 행렬** ([`users.py:215-236`](../../services/application/app/auth/users.py#L215)):
  active→409 · pending→409 · rejected+활성→덮어씀(같은 id·새 created_at) ·
  **rejected+비활성→409**(D6 단방향 — 가입이 비활성화를 되살리지 않음) ·
  대체 행은 절대 admin 이 될 수 없음. 전 분기에 대응 셀 존재.
- **P-4 게이트 순서** ([`routers/auth.py:88-120`](../../services/application/app/routers/auth.py#L88)):
  자격증명 먼저 → `register_success`(403/409 포함 자격증명 통과 전경로) → status 403
  두 문구 → C-6 409 → 세션. 틀린 비밀번호의 pending 계정 = 401 통일(셀 존재).
  is_locked 는 Argon2 **앞**에서 조기 401 — 정답도 401(셀 존재).
- **P-7 pending 전용** ([`users.py:290-310`](../../services/application/app/auth/users.py#L290)):
  approve·reject 모두 `SignupNotPending` 가드(409)·미존재 404·비관리자 403×3(셀 존재).
  대체 행 must_change_password=False — 요청자가 비밀번호를 스스로 정하므로 C-6 흐름 없음.
- **레거시 행 방어** ([`users_mongo.py:113`](../../services/application/app/auth/users_mongo.py#L113)):
  `doc.get("status","active")` — 실서비스 Mongo에서 visual_demo·visual_user 가 status 필드
  없는 채 확인됨(프리승인 행). M7 뮤테이션(하드 서브스크립트)이 신규 셀+구 C-6 짝 셀을 물었다.
- **TTL 부채 폐쇄** ([`main.py:402-408`](../../services/application/app/main.py#L402)):
  `SessionTtlEnvGuardTest` 4셀(음수·0 거부·양수 반영·미설정 기본)이 M6(가드 삭제)를 물었다.
- 프론트: `signinErrorMessage`([`AuthGate.tsx`](../../frontend/src/auth/AuthGate.tsx))가 403 두
  detail 문구만 구분 — H3 예외의 유일 소비자 주장과 일치(grep 확인: 소비자 1곳).

### 3. 뮤테이션 10종(검증자 자체, 변이→셀 페어링)

| # | 변이(실제 diff) | 방향 | 물린 셀 |
|---|---|---|---|
| M1 | `login_guard.py` `failures >= max` → `>` (5회→6회 잠금) | under | 5셀: `test_the_fifth_failure_locks`·`test_locks_are_per_username`·`test_unknown_usernames_register_failures_too`·HTTP `test_the_sixth_attempt_…still_401`·`test_a_lock_is_per_username` |
| M2 | `routers/auth.py` `is_locked` 조기 검사 블록 삭제 | under | 2셀: HTTP `test_the_sixth_attempt…`·`test_a_lock_is_per_username` (401-문구 균일 셀들이 안 문 것은 정상 — 그 셀들은 메시지 균일성을 잠금) |
| M3 | `users.py` `or not existing.is_active` 삭제 | under | 1셀: `test_a_deactivated_rejected_row_is_not_resurrected` |
| M4 | 중복 검사 `if False:` (활성 행 덮어쓰기=계정 탈취 방향) | under | 4셀: 도메인 3 + HTTP `test_a_taken_active_username_is_409` |
| M5 | `approve_signup` pending 가드 삭제 | under | 3셀: 도메인 2 + HTTP `test_an_already_resolved_request_is_409` |
| M6 | `main.py` TTL `raise ValueError` 삭제 | under | 2셀: `test_a_negative_ttl_refuses_to_start`·`test_a_zero_ttl_refuses_to_start` |
| M7 | `users_mongo.py` `.get("status","active")` → `doc["status"]` | 방어 제거 | 2셀: 신규 레거시 셀 + 구 C-6 레거시 짝 셀 |
| M8 | `routers/auth.py` pending/rejected 403 분기 삭제(미승인 세션 발급) | under·치명 | 3셀: `test_a_pending_account_is_403_pending`·`test_a_rejected_account_is_403_rejected`·`test_rejection_keeps_the_account_403` |
| M9 | `login_guard.py` stale 리셋의 `clear` 제거 | over | **0셀 — 물지 않음**(아래 H-1: 잠금 소거 결함이 흡수) |
| M10 | 중복 검사 `if True:` (재요청 전면 차단) | over | 2셀: `test_a_rejected_username_can_be_re_requested`·`test_a_replacement_row_is_never_an_admin` |

각 복구 후 `git status --short` 빈 확인(전회 동일). 작업자 8종 목록은 SoT v1.7.97
변경이력에 기록돼 있으나 **변이→셀 페어링은 미기록** — 본 표가 보강한다.

### 4. M9 미물림의 규명 — 흡수층은 설계가 아니라 제2의 결함

순수 프로브(파일 변이 없이)로 원본 코드에서 실증:
**잠금 중 `register_failure` 한 번이 잠금 레코드를 지운다** — `register_failure`가
`locked_until`이 살아 있는 레코드를 읽고도 `{failures:1, locked_until:None}`으로
덮어쓴다(`login_guard.py:90-103`는 잠금 상태를 모른다). 정상 HTTP 경로에선 라우터의
조기 `is_locked` 401 덕에 도달 불가하고 **현재 배포(단일 uvicorn 워커·동기 핸들러)에서는
경쟁도 불가**하다. 그러나 (a) P-6이 Mongo 저장의 근거로 명시한 **다중 인스턴스** 확장 순간
경쟁으로 잠금이 지워질 수 있고, (b) 이 결함이 M9(stale 리셋 제거)을 삼켜
`test_a_stale_counter_resets_on_read`가 **단독으로는 자기 조항을 못 잠그고 있다**.
→ H-1(비차단)로 등재. 수리는 한 곳: `register_failure`가 살아 있는 `locked_until`을 보존.

### 5. 실서비스 관통(nginx 5520 — 2026-08-22 실측)

| 단계 | 기대 | 실측 |
|---|---|---|
| POST /api/auth/signup (verif_0822) | 201 pending | 201 `{"status":"pending"}` |
| 같은 username 재가입 | 409 | 409 |
| 정답 로그인(대기) | 403 "account approval pending"·쿠키 없음 | 403·no set-cookie |
| 오답 로그인 / 미지급 사용자 | 401 동일 detail | 401 "invalid credentials" 양쪽 동일 |
| Mongo status→active 후 로그인 | 200+세션 | 200·`Set-Cookie: session=…; HttpOnly; SameSite=lax; Secure` |
| GET /api/auth/me (쿠키) | 200 | 200 |
| status→rejected 후 로그인 | 403 "signup request rejected" | 403 |
| rejected 행 재요청 | 201(덮어씀) | 201 — 같은 `_id`·새 `created_at` |
| 오답 5회 → 정답 | 401(잠금) | 401×5 → 정답 401 |
| login_failures(Mongo) | 잠금 행 | `{failures:0, locked_until:+5분}` — "잠금 시점 리셋" 계약 그대로 |
| GET /api/admin/signup-requests (무세션) | 401 | 401 |
| 8520 직접 /admin/signup-requests | 404(표면 분리) | 404 |

배포 검증의 제약: 관리자 자격증명이 없어 **승인·거절 API의 라이브 호출과 "재승인 409"
라이브 재현은 하지 못했다** — 대신 Mongo 직접 status flip으로 배포 와이어링(실 Mongo
왕복·세션 발급)을 검증했고, API 계약 자체는 스위트 `SignupApprovalApiTest`(200·403·409·404·
비관리자 403×3)이 잠근다. 작업자 보고의 "승인 200·재승인 409" 중 승인 200 라이브 값은
본 검증의 Mongo flip 경로로 간접 실증.

### 6. 보안 점검 클레임 대조

- 쿠키 `HttpOnly; SameSite=lax; Secure` 실측 — 작업자 발견 ④(http LAN 배포 시 로그인 불가
  예고)는 플래그 관찰로 뒷받침됨.
- `/docs`·`/openapi.json` 무인증 200 — 8520 직접 **및 /api/docs·/api/openapi.json 으로
  공개 nginx 포트(5520)에서도 200**(61 paths 전체 열람). **작업자 발견 ③보다 노출이 넓다**
  — 오너 결정 대기 목록의 표현을 넓혀야 한다(H-3). 단 /api/admin/docs 는 404(admin 앱
  라우팅 미공개).
- 시드: `visual_demo`(admin·활성·status 필드 없음)·`visual_user`·`smoke_admin`(admin)·`bob`·
  `carol`(rejected) 확인 — "정리 대기" 클레임 사실. **검증 잔여 추가**: `verif_0822`(pending·
  이 검증이 만듦)도 같은 정리 목록에 포함할 것(login_failures 행은 5분 뒤 자연 소거).
- nginx 보안 헤더 부재(발견 ⑤) — default.conf 확인으로 뒷받침.

### 7. 문서 정합

- CHANGELOG·plans 인덱스 등재·work_log 세션 5 — 사실관계 대조 무사(셀 수 오류는 H-4).
- HANDOFF "미검증 커밋" 메모 — 본 검증으로 해소됨(아래 Outstanding).
- 브리프 슬라이스 표의 operation 추정(77→78 / 78→81)이 실제(78→79 / 79→82)와 어긋남 —
  브리프 작성 시점의 낡은 기준선(H-5, 계약 정본은 SoT 79→82 가 정확).

## Issues / Risks

### Blocking (계약 의무)

- **B1 — SoT 본문이 v1.7.97와 자기모순.** `b6cee5d`는 헤더+변경이력만 고쳤고 본문은 그대로다:
  - [`system-contract-sot.md:412`](../../docs/system-contract-sot.md#L412) §상태코드 의미론
    403 행: *"생산자는 **정확히 둘**… 이 둘 **외의** operation이 403을 선언하면 거짓 선언이다"* —
    버전 로그의 "생산자는 이제 셋"과 정면 충돌. 또한 "살아 있는 세션은 있으나"라는 의미 문장도
    셋째 생산자(세션 발급 **거부**)에 성립하지 않는다.
  - [`system-contract-sot.md:401`](../../docs/system-contract-sot.md#L401) H3 3층 규칙:
    *"문자열 패턴 매칭으로 분기하지 않는다"* — 로그인 화면 `signinErrorMessage`가 정확히 그
    분기를 한다. 버전 로그는 "등재된 유일 예외"라고 선언하지만 **본문 규칙에 예외가 등재되지
    않았다**.
  - [`system-contract-sot.md:326`](../../docs/system-contract-sot.md#L326) C-6 절도
    "403의 생산자는 정확히 둘"을 재인용 — 같은 모순의 두 번째 자리.
  v1.7.56 당시 두 번째 생산자 추가 시 본문 표를 갱신했던 선례와 다르게 이번엔 본문이 안 따라왔다.
  검증 가이드 기준 내부 계약 모순은 차단 사안 — 코드·셀은 건전하므로 판정은 조건부로 한다.

### Hardening (비차단)

- **H-1 — 잠금 소거 경쟁(제4절)**: `register_failure`가 살아 있는 잠금을 덮어 지운다.
  현재 단일 워커 배포에선 도달 불가·P-6이 지향하는 다중 인스턴스에서 현실화. 수리:
  잠금 중 실패는 `locked_until` 보존(또는 no-op). 수리 시 `test_a_stale_counter_resets_on_read`가
  비로소 단독으로 M9를 물 수 있게 된다(현재 그 셀은 이 결함에 가려져 있음 — 본 검증 실측).
- **H-2 — `login_failures` 무한 증가 가능**: 미지급 username 스프레이가 행을 계속 만든다(읽을 때만
  stale 정리·TTL 인덱스 없음 — 문서화된 트레이드오프). Argon2 더미 검증이 쓰기 속도를 묶고 있어
  완화는 충분하나, 공개 배포 전 상한/청소 검토 가치.
- **H-3 — /docs 노출은 5520 경유로도 열림**(제6절): 오너 결정 대기 항목의 범위를
  "8520"에서 "8520·5520(/api/docs)"으로 넓혀 결정할 것.
- **H-4 — SoT v1.7.97 기록의 산수 오류**: 신규 셀 47→실측 49(Mongo 4→6), 프론트 8→실측 5.
- **H-5 — 브리프 operation 추정 부정확**(77→78/78→81 vs 실제 79→82): SoT 가 정본이므로 무해하나
  브리프에 정정 각주 가치.
- **H-6 — [`AdminConsole.tsx:140`](../../frontend/src/admin/AdminConsole.tsx#L140)** `setError(null);    try {`
  같은 줄 서식 잔류 — 동작 무해, 다음 프론트 슬라이스에서 정리.

## Verdict

**조건부 합격** — SoT 본문(§HTTP 에러 응답 계약 403 행·H3 3층 규칙·C-6 절의 "생산자 둘"·
"detail 분기 금지" 문구)을 v1.7.97의 셋 생산자·등재 예외에 맞게 개정해야 한다(B1).

근거: 구현·회귀·전수 수트·라이브 관통은 경계 행렬 전 셀에서 계약(브리프 P-1~P-7)대로
작동했고 검증자 뮤테이션 10종 중 9종이 표적 셀을 물었다(미물림 1종은 제2 결함 발견으로
귀결 — H-1). 정량 클레임(2480/331/425.35kB/82/11) 전부 재현. 차단 사안은 문서 계약의
자기모순 하나뿐이며 코드 변경을 요구하지 않는다.

## Outstanding items

- **오너 결정 대기 3건(작업자 보고 그대로 + H-3 확대)**: ① 시드 정리 + 오너 admin 계정명 —
  정리 목록에 `verif_0822`(본 검증 잔여) 추가. ② `/docs`·`/openapi.json` 공개 여부
  — **범위에 5520 경유 포함**. ③ 홈서버 http 공개 시 Secure 쿠키 충돌 — HTTPS 또는
  `AUTH_COOKIE_SECURE=false`. (nginx 보안 헤더도 공개 전.)
- B1 개정시 셀 수 산수(H-4)를 같이 바로잡는 것이 자연스럽다(같은 SoT 터치).
- H-1 수리 여부는 오너 판단(현재 배포에 즉시 위험 없음 — 다중 인스턴스 전 확정 필요).

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system && git status --short        # 빈 것 확인
docker compose -f docker-compose.test.yml up -d               # 119 skip 방지
python3 -m pytest -q tests/ | tail -1                         # 2480 passed, 4 skipped
(cd frontend && npx vitest run 2>&1 | tail -3)                # 331 passed
# M9 규명 프로브(파일 변이 없음):
python3 - <<'EOF'
from datetime import UTC, datetime, timedelta
from services.application.app.auth.login_guard import InMemoryFailureRecordRepository, LoginFailureGuard
T0 = datetime(2026, 8, 22, 12, 0, tzinfo=UTC); clock = {"now": T0}
g = LoginFailureGuard(InMemoryFailureRecordRepository(), max_failures=5,
                      lockout=timedelta(seconds=300), clock=lambda: clock["now"])
for _ in range(5): g.register_failure("alice")
print("locked:", g.is_locked("alice"))          # True
g.register_failure("alice")
print("still locked:", g.is_locked("alice"))    # False — 잠금 소거(H-1)
EOF
# 실관통(순서 중요 — 잠금 테스트가 마지막):
curl -s -X POST localhost:5520/api/auth/signup -H 'Content-Type: application/json' \
  -d '{"username":"verif2_0822","password":"verify-long-pw-0822!"}'        # 201
curl -s -X POST localhost:5520/api/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"verif2_0822","password":"verify-long-pw-0822!"}'        # 403 pending
docker exec ai_writte_system-mongo-1 mongosh --quiet ai_writing_system \
  --eval 'db.users.updateOne({username:"verif2_0822"},{$set:{status:"active"}})'
curl -s -D - -X POST localhost:5520/api/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"verif2_0822","password":"verify-long-pw-0822!"}' -o /dev/null   # 200 + Secure 쿠키
```
