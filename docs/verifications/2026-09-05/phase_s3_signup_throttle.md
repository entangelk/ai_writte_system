# Phase S-3 — 공개 signup 표면 속박 독립 검증

## Subject metadata

- 검증일: 2026-09-05
- 요청자: 오너("검증하고 의심하고 또 의심해줘" — 구현자 보고 전문 회신)
- 검증자: Claude Code 세션(구현 세션과 별개 — 구현 커밋의 author와 다른 컨텍스트)
- 대상: 커밋 `be54124`(브리프) · `79515fd`(모듈 셋) · `7e5ee23`(배선·계약·회귀) · `34367db`(기록, SoT v1.8.30). 검증 시점 작업 트리 공백.
- 정규 스펙: [`docs/plans/security-phase-s3-signup-throttle-decisions.md`](../../plans/security-phase-s3-signup-throttle-decisions.md)(Resolved 판 + "확정된 계약 literal" 표) · [`docs/system-contract-sot.md`](../../system-contract-sot.md) v1.8.30(변경이력 행 + 상태코드 429 행) · 회귀 `tests/test_signup_throttle.py` · 계약 가드 `tests/test_quota_enforcement_api.py`.
- 환경: WSL2, `/usr/bin/python3` pytest, **라이브 Mongo 없음**(전수 151 skipped — 구현자 기록과 동일 조건).

## Scope

1. ★ 계약 literal ↔ 구현·테스트 대응(브리프 literal 표 전 항목)
2. 회귀 22셀 + 계약 가드 1셀의 실재·양방향성
3. 뮤테이션 — 구현자 4종 재현 + 검증자 신규 5종(라우터 순서·env 기동거부·등재 목록 제거/추가·신뢰 대역 기본값)
4. 전수·tsc·프론트 재실행(구현자 수치와 대조)
5. 계약 자기모순(SoT ↔ 코드 ↔ 가드 상호 대조)
6. 민감정보 기록 0건 주장(커밋 4개 전체 diff grep)
7. 기록 정합성(HANDOFF·work_log·CHANGELOG·계획 인덱스)

## Methodology

- 계약 읽기: 브리프 + SoT v1.8.30 행을 먼저 읽고 경계 행렬을 세운 뒤 코드를 봄(가이드의 스코프-퍼스트 순서).
- 포커스: `python3 -m pytest tests/test_signup_throttle.py tests/test_quota_enforcement_api.py tests/test_docs_indexes.py -q` → **76 passed / 527 subtests**(22+39+15 셀, 서브테스트 236+291 — work_log 수치와 정확히 일치).
- 전수: `python3 -m pytest tests/ -q`(정상 코드) → **2678 passed / 151 skipped / 3187 subtests / 0 failed**(349초). M5 뮤테이션 아래에서도 동일 명령 1회(253초).
- 프론트: `npx tsc --noEmit`(exit 0) · `npm test`(vitest) → **401 passed / 2 failed (403)**, 실패 파일 `src/typeScale.test.ts`·`src/designTokens.test.ts`.
- schema 동일성: `cd frontend && npm run gen:api` 후 `git status` — **무차이**(커밋된 `schema.d.ts`가 현 코드 산출과 byte-동일).
- 뮤테이션: 트리 공백 상태에서 Edit → 실행 → `git checkout -- <path>` → `git status --short` 공백 확인(가이드 clean-tree 분기). 판독은 요약 라인(`FAILED|SUBFAILED`) 기준.
- 민감정보: `git diff be54124^..34367db | grep ^+` 에서 IPv4·도메인·키경로·토큰 패턴 추출 후 전건 분류.

## Findings

### 1. 계약 literal ↔ 구현 (모두 일치)

| 브리프 literal | 구현 | 확인 |
|---|---|---|
| 발신 IP당 시간당 5건 고정창 | `signup_guard.py:29-30`(`DEFAULT_MAX_REQUESTS=5`·`3600`) | ✓ |
| 막힌 요청 창 미연장 | `signup_guard.py:84-88` — 차단 분기가 저장소를 건드리지 않음 | ✓ |
| 모든 시도 계수(409 포함) | `consume()`에 결과 개념 없음(`signup_guard.py:71-78`) | ✓ |
| 신뢰 대역 기본 `127/8`·`::1`·`172.16/12`, env, 깨진 CIDR 기동 거부 | `client_ip.py:50`·`main.py:524-539` | ✓ |
| XFF 오른쪽→왼쪽, 신뢰 항목 스킵, 형식 불량 항목은 버림(멈추지 않음) | `client_ip.py:80-93` | ✓ |
| username 64·password 256 → 400(서비스 시행, 모델 아님) | `users.py:76-77`·`users.py:242-253` | ✓ — pydantic이 아니라 서비스라 400이 나옴(HTTP 셀 `..._answers_400_not_422`) |
| pending 200 → 429, 재요청 면제 | `users.py:86`·`users.py:276-284`(재요청 분기 **뒤**) | ✓ |
| 거절은 해셔 앞 | 서비스 레벨: 모든 거절이 `self._hasher.hash` 앞(`users.py:254` 이전). 라우터 레벨: 아래 B1 | 부분 ✓ |
| 429+Retry-After, THROTTLED_OPERATIONS 등재·양방향 잠금 | `routers/auth.py:90-96`·`errors.py`·`test_quota_enforcement_api.py` | ✓ |
| Mongo `signup_attempts` / in-memory, TTL=창×24 최소 1일 | `signup_guard_mongo.py:27-30`·`:49-54`, `main.py:565-577` | 구현 ✓, 잠금은 B4 |

### 2. 회귀 셀 실재·양방향성

22셀(해석 7·스로틀 5·상한 5·HTTP 5) 전부 실재하고 각 축 양방향 docstring 보유. 계약 가드 신설 셀 `test_the_second_429_producer_stays_exactly_one_operation`은 `assertEqual(actually_declared, THROTTLED_OPERATIONS)` — 진짜 등가호 양방향.

### 3. 뮤테이션 (구현자 4종 재현 ✓ + 신규 5종 중 3종 미물림 ★)

| # | 뮤테이션(적용 diff) | 결과 |
|---|---|---|
| M1 | `client_ip.py:80` `reversed(...)` 제거(왼쪽 읽기) | **2 failed** — `rightmost_untrusted_entry_wins`·`forged_forwarded_for_cannot_buy_a_fresh_bucket` (구현자 기록과 동일 셀) |
| M2 | `client_ip.py:77` `if not self._is_trusted(peer)` → `and False`(직결 XFF 신뢰) | **1 failed** — `untrusted_peer_is_the_client_and_its_header_is_ignored` (동일) |
| M3 | `signup_guard.py:84` 차단 분기에 `put(window_started_at=now)` 삽입(remaining은 stale local 계산) | **1 failed** — `refused_attempt_does_not_extend_the_window`. ※구현자 기록은 2셀(Retry-After 셀 포함) — 그 변이는 local 재할당형으로 remaining까지 밀었을 것. **변이 형태가 셀 수를 가르는 사례**(가이드 "diff 를 적어라" 규칙의 실증). 핵심 잠금은 양쪽 다 물림 |
| M4 | `users.py` 대기열 상한 블록을 기존 행 조회 앞으로 이동 | **1 failed** — `re_request_over_a_rejected_row_survives_the_ceiling` (동일) |
| M5★ | `routers/auth.py` throttle 블록(resolve+consume+429)을 `request_signup` try/except **뒤**로 이동 | **0 failed — 전수 2678 통과.** 429 응답이 나오기 전 Argon2 해싱+pending 행 생성이 실행됨 = 감사 §A.5 원결함 그대로 재등장해도 아무 셀이 안 물림 → **B1** |
| M6★ | `main.py:555-556` `parsed <= 0 → raise` → `parsed = DEFAULT_MAX_REQUESTS` | **0 failed.** 양성 대조: 현행 코드는 `AUTH_SIGNUP_MAX_REQUESTS=0` import 시 `ValueError` 로 기동 거부(실측), 변이 후 조용히 기동. 테스트의 env 참조 자체가 0건(grep) → **B2** |
| M7a★ | `THROTTLED_OPERATIONS`에서 signup 제거 | **2 failed** — 가드③ `SUBFAILED` + 신설 셀. `grep ^FAILED` 만으로는 1개로 보인다(가이드 SUBFAILED 규칙의 실증) |
| M7b★ | `THROTTLED_OPERATIONS`에 `("/auth/login","post")` 추가 | **1 failed** — 신설 셀 |
| M8★ | `DEFAULT_TRUSTED_PROXY_CIDRS`에 `"192.168.0.0/16"` 추가 | **1 failed** — `untrusted_peer_is_the_client...`("LAN 제외" 기본값 literal 은 잠겨 있음) |

### 4. 전수·프론트·스키마

- 전수 정상 코드 **2678/151/3187/0** — 구현자 수치와 동일.
- tsc exit 0. 프론트 401/403, 2실패 = `typeScale`·`designTokens` — **사전존재 등재가 이 슬라이스 이전**(SoT v1.8.27 행, 2026-09-04: "HEAD~1 재현 확인")에 존재하므로 구현자 자기등록이 아님. 인과 관계도 없음(스타일 토큰 테스트).
- `gen:api` 재생성 무차이 — `schema.d.ts` +9줄이 429 엔트리 정확히 하나분임을 기계적으로 확인.

### 5. 계약 자기모숈 — 경로 수 (→ B3)

`BILLABLE_OPERATIONS` 실측 **11개**(`python3 -c` AST 집계). 추이: `b00ad12`(8.3) 9 → `832089b`(09-01, finalize) **10** → `ea55474`(09-04, v1.8.29) **11**. 그런데:
- SoT v1.8.29 행은 "유료 9→10경로, BILLABLE_ACTIONS 10번째 행" — **그 커밋 시점에 이미 11**(09-01 등재분이 서술에 안 반영된 선결함).
- 이 슬라이스가 **새로 쓴** 텍스트가 오류를 반복: SoT v1.8.30 상태코드 429 행 "`① quota(8.3, v1.7.87) — 유료 10경로의 창 소진…`"(실제 11)·`errors.py` 신규 주석 "'유료 9경로에만' 429 가드"(S-3 직전 기준 10).
- 작동 가드(`BILLABLE_OPERATIONS`/`THROTTLED_OPERATIONS` 집합 ↔ 실제 라우트 등가 비교)는 정확해서 동작은 문제없음 — **정본 서술의 숫자만 틀림**.

### 6. 민감정보

커밋 4개 추가 라인의 IP 전건 분류: `203.0.113.x`·`198.51.100.x`(TEST-NET 문서대역), `172.19.0.x`·`192.168.1.50`·`1.2.3.4`·`8.8.8.8`(테스트 픽스처 예시), `172.16.0.0/12`·`127.0.0.0/8`·`0.0.0.0`(계약 literal·바인딩 서술). 도메인 패턴 히트는 `services.application.app`(파이썬 패키지 경로, 오탐). 계정명·키 경로·토큰 패턴 0건. **"민감정보 0건" 주장 확인.**

### 7. 기록 정합성

HANDOFF(S-3 ✅ 닫힘·낡은 vhost 오너 확인 항목·S-1 다음 순서)·계획 인덱스(Proposed→Resolved)·CHANGELOG·README 버전 주장 전부 갱신돼 있고 상호 모순 없음. 커밋 4개·트리 공백 주장도 확인(세션 시작 스냅샷의 dirty 상태는 마지막 docs 커밋 `34367db` 이전 것이었음).

## Issues / Risks

### Blocking (계약 의무)

- **B1 — 라우터 순서("거절은 `request_signup` 앞 = 해셔 미도달")에 잠금 셀 없음.** SoT v1.8.30("해셔에 닿지 않는 것이 이 가드의 전부다")·커밋 메시지·라우터 주석(`routers/auth.py:80-85`)이 이 순서를 슬라이스의 핵심 계약으로 명시. M5 실측: 순서를 뒤집어(429 확정 전 Argon2+행 생성) **전수 2678 전부 통과**. 서비스 레벨 상한 셀들은 입력·대기열 거절의 해셔-미달만 잠그고 IP 스로틀의 그것은 못 잠금. 잠금 방법 예: HTTP 셀에서 스로틀 429 응답 후 `hasher.calls` 불변(또는 users 저장소 행 수 불변) 단정.
- **B2 — env 기동 거부 literal에 셀 없음.** 브리프 literal 표("파싱 실툇·0 이하는 기동 거부")와 SoT v1.8.30이 등재했으나 `AUTH_SIGNUP_MAX_REQUESTS`·`AUTH_SIGNUP_WINDOW_SECONDS`·`AUTH_TRUSTED_PROXY_CIDRS`의 테스트 참조 0건(grep). M6 실측: 가드 제거 시 조용히 기동, 무엇도 안 물림. 모듈 레벨 `ClientIpResolver(("not-a-cidr",))` 셀만 있고 `main.py` 조립기(env 파싱)는 무셀. 선례 `login_guard`도 무셀이지만, S-3은 이 동작을 literal 표에 올렸다는 점이 다르다.
- **B3 — SoT v1.8.30 429 행 "유료 10경로"는 실제 11경로.** 이 슬라이스가 정본에 새로 쓴 서술의 사실 오류(뿌리는 09-01 `832089b`의 SoT 무갱신이라는 선결함이지만, v1.8.30 행과 `errors.py` 신규 주석은 이 슬라이스 산출물). 정정은 숫자 1개 교체 수준이나 정본 계약 텍스트의 부정확은 이 저장소 규정상 차단 사유.
- **B4 — `signup_guard_mongo.py`에 테스트 파일 자체가 없음**(전 suite에서 참조 0건, 스킵셀조차 없음). TTL 인덱스 존재·`expireAfterSeconds = max(86400, 창×24)`·`_aware` 재라벨링이 SoT 등재 literal인데 리팩터링으로 `create_index`가 사라져도 무엇도 안 물림. 이 저장소의 다른 Mongo 저장소(sessions·users·identity_group_approvals 등)는 전용 테스트 파일을 둔다는 점에서 규범과도 어긋남.

### Hardening recommendations (비차단)

- **H1 — 신뢰 대역 `172.16.0.0/12`는 docker 사설 풀 전체.** 공유 호스트의 **타 프로젝트 컨테이너**도 이 대역에서 `:8520`에 직접 닿으면 신뢰 홉 취급을 받아 XFF 로 자기 버킷을 고를 수 있다(호스트발 hairpin 연결의 게이트웨이 주소도 같은 대역). 실측 위협 모델(인터넷·LAN 10/8·192.168/16)에는 성립하나 "같은 호스트의 이웃 컨테이너"는 열려 있음. 브리프가 "컨테이너 주소가 재기동마다 바뀌므로 대역으로 잡는다"고 인지한 트레이드오프 — 최소한 Follow-up 등재 또는 compose 네트워크 서브넷으로 좁히는 검토 권고.
- **H2 — 두 429 생산자의 `detail` 문구가 다르다**("too many signup requests" vs "too many pending signup requests; try again later"). `SignupQueueFull` docstring은 "응답에서 구분하면 홍수 쪽에 정보"라 논리하는데 문구는 구분됨. 프론트는 한 문구로 통일(계약 준수)이라 노출은 API detail 뿐 — 통일 여부는 오너 취향.
- **H3 — B3 정정 시 함께:** `test_quota_enforcement_api.py` 헤더 ③ "유료 9경로가"(8.3 집필 시점엔 맞았으나 09-01부터 낡음 — 이 슬라이스가 같은 줄에 괄호를 붙이며 지나침)와 SoT v1.8.29 행·HANDOFF:227 "유료 10번째 경로"의 뿌리가 같은 무갱신. v1.8.29 행 정정 여부(변경이력 소급)는 오너 판단.
- **H4 — `list_pending()` 전건 적재로 상한 검사**(`users.py:281`) — 200 상한이라 유계, 성능 무해. 관찰 기록만.

## Verdict

**조건부 합격** — B1 라우터 순서 잠금 셀·B2 env 기동거부 셀·B4 Mongo TTL 인덱스 셀의 3종 무셀을 보강하고 B3 SoT 429행 경로 수(10→11, `errors.py` 주석 포함)를 정정할 때까지.

근거: 구현·문서·뮤테이션은 충실하다 — 브리프 literal 전항이 코드에 그대로 있고(§1), 구현자 뮤테이션 4종은 전부 재현 재실패했으며(§3 M1-M4), 등재 목록 양방향·LAN 제외 기본값도 진짜로 잠겨 있다(M7·M8). 그러나 검증자 뮤테이션 3종(M5·M6·B4의 TTL 제거 상당)이 전부 무물림이고, 그중 M5 는 **이 슬라이스가 막으러 온 결함(§A.5)의 전면 재등장**이다 — "거절이 싸다"는 주장이 현재 테스트로는 증명 불가능하다. 경계 행렬의 빈 칸 3과 정본 숫자 오류 1이 닫히면 합격으로 올린다.

## Outstanding items

- **오너 확인 항목(구현자 슬라이스가 정상 등재함)**: 공유 호스트 공용 리버스 프록시의 **낡은 vhost** — HANDOFF·브리프 Follow-up·work_log Next steps 3곳에 올라 있음(타 프로젝트 저장소 소관).
- 본 검증의 B1-B4 폐쇄는 미실시(검증자는 결함을 고치지 않고 보고한다 — 가이드). 폐쇄 슬라이스가 위 4건을 닫으면 이 기록의 조건은 소멸한다.
- M5 아래 전수 2678 통과는 **정상 상태 전수와 숫자가 동일**하다는 점에 유의 — 전수 그린바만으로는 어떤 주문도 잠기지 않는다는 이 슬라이스의 사례적 증거.

## Reproduction

```bash
# 포커스 (녹색 기준선)
python3 -m pytest tests/test_signup_throttle.py tests/test_quota_enforcement_api.py tests/test_docs_indexes.py -q
# → 76 passed, 527 subtests

# B1 재현 (트리 공백 상태에서; 복원은 git checkout -- <path> + git status 공백 확인)
# services/application/app/routers/auth.py — signup 핸들러에서 throttle 블록(86-96)을
# try/except 뒤 return 직전으로 이동 →
python3 -m pytest tests/ -q   # → 2678 passed (0 failed) — 잠금 없음 입증

# B2 재현 — main.py:555-556 의 raise 를 parsed = DEFAULT_MAX_REQUESTS 로 교체 후:
AUTH_SIGNUP_MAX_REQUESTS=0 python3 -c "from services.application.app.main import _default_signup_throttle; _default_signup_throttle()"
# 현행: ValueError / 변이: 조용히 기동

# B3 재현
python3 -c "from services.application.app.quota.billable_actions import BILLABLE_OPERATIONS as B; print(len(B))"  # → 11

# 전수·프론트
python3 -m pytest tests/ -q          # 2678/151/3187/0
cd frontend && npx tsc --noEmit && npm test   # tsc 0 · 401/403 (typeScale·designTokens 사전존재)
```
