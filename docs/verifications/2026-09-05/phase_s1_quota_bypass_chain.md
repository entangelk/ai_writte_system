# Phase S-1 — quota 우회 체인 폐쇄 독립 검증 (+ S-3 검증 조건 폐쇄 확인)

## Subject metadata

- 검증일: 2026-09-05
- 요청자: 오너("다음작업 검증해줘" — S-1 구현 보고 회신)
- 검증자: Claude Code 세션(구현 세션과 별개)
- 대상: **S-1** 커밋 `fb90914`(브리프)·`9ce8191`(D1)·`63b6c0d`(D2)·`3a2a3ee`(D3)·`11f90a8`·`82cd7e0`(전수 여파)·`6a10b70`(기록, SoT v1.8.32). 검증 시점 트리 공백. 보고서의 "커밋 6개"는 구현 5+기록 1 기준(브리프 제외) — 실제 슬라이스 전체는 7커밋.
- 함께 검증: **S-3 검증 조건 폐쇄** 커밋 `126bf42`(B1·B2·B4 셀)·`a492751`(B3 정정, SoT v1.8.31)·`2b0dedd`(폐쇄 기록) — 아래 Findings §1.
- 정규 스펙: 브리프 [`security-phase-s1-quota-dedupe-decisions.md`](../../plans/security-phase-s1-quota-dedupe-decisions.md)(Resolved) · SoT v1.8.32 행 + 429 상태코드 행 · 8.2b G4=A.
- 환경: WSL2 `/usr/bin/python3` pytest, 라이브 Mongo 없음(151 skipped — 구현 기록과 동일).

## Scope

1. ★ S-3 검증 조건(B1~B4)이 실질 폐쇄됐는가 — 폐쇄 셀에 내 변이를 재적용
2. S-1 계약 literal ↔ 구현·선언 대응(D1 409/429/+1·국소 C·D2 2회/60s/입장·D3 20쌍/이월)
3. 뮤테이션 — 구현자 11종(M-A~M-K) 재현 + 검증자 신규 5종(N-a~N-e)
4. 전수·tsc·프론트·gen:api·셀 산수(+27) 재계산
5. 가드 진화(THROTTLED 양방향·STANDING 1:1·409 얼굴 6경로 잠금)
6. 민감정보·기록 정합(HANDOFF·work_log·mongo_collections §43H)

## Methodology

- 전수: `python3 -m pytest tests/ -q` → **2720 passed / 151 skipped / 3206 subtests / 0 failed**(301초).
- 프론트: `npx tsc --noEmit` exit 0 · vitest **401/403**(2실패 = `typeScale`·`designTokens` — v1.8.27 이래 사전존재). `npm run gen:api` 재생성 무차이.
- 뮤테이션: 트리 공백에서 python 치환(count==1 단정)→포커스 실행→`git checkout --`→`git status --short` 공백 확인. 판독은 요약 라인.
- 셀 산수: `git diff bf71e3f..HEAD -- tests/`에서 `def test_` 증감 직접 집계.

## Findings

### 1. S-3 검증 조건 폐쇄 — **전건 실질 폐쇄 확인(조건 소멸)**

- **B1**: 신설 `test_the_throttled_429_answers_before_the_hasher_runs` — 내 S-3 M5(스로틀을 `request_signup` 뒤로) 재적용 시 **1 failed** 로 재실패. 셀 내용이 429 시 해셔 미도달을 행동으로 잠금.
- **B2**: `SignupEnvBootGuardTest` 7셀 — M6(`≤0` 가드 제거) 재적용 시 `test_a_non_positive_max_requests_refuses_to_start` **SUBFAILED(raw='0'·'-1')**. non-integer·빈 CIDR 목록·유효값 배선 셀까지.
- **B4**: `tests/test_auth_signup_guard_mongo.py` 7셀(가짜 몽고) — `_TTL_MULTIPLIER` 24→2 변이에 `test_declares_the_ttl_index_at_window_x24_with_a_one_day_floor` **SUBFAILED(window_seconds=3601·7200)** 재실패.
- **B3**: SoT v1.8.31에서 "유료 10경로"→**11** 정정, `billable_actions.py` 주석·quota 가드 헤더 4곳 동반 정정(`126bf42`). v1.8.32 429행도 11로 서술.
- 나의 S-3 기록(`phase_s3_signup_throttle.md`)의 조건은 이것으로 소멸한다(동 기록 Verdict 문구가 자체 서술한 대로).

### 2. 계약 literal ↔ 구현 (모두 일치)

| literal(SoT v1.8.32·브리프) | 구현 | 확인 |
|---|---|---|
| 정산 키 재제출 → 실행 **전** 409 | `enforcement.admit` 원장 포인트 리드(`enforcement.py:355-364`), HTTP 셀이 `provider.calls == 1` 로 재실행 부재까지 단정 | ✓ |
| 진행 중 → 잠금 429(기존) | 잠금 경로 무변, `DuplicateLockTest` 계약 갱신 | ✓ |
| 확인 재실행 → **+1 과금**(G4 첫 이행) | `QuotaCharge.confirmed` → `record_usage(force_new)` 접미 신규 행(`ledger.py:203-216`), 원본 행 보존 | ✓ — M-B로 2셀 재실패 |
| report 국소 C — 저장·재생, TTL 24h | `quota/replay.py`(인메모리 스윕+mongo TTL 인덱스), 재생 영수증은 잠금·차감·원장 전부 무시 | ✓ — 재생 셀이 `provider.calls`·원장 행 수까지 잠금 |
| accept replay 를 enrich 앞으로 | `accept.py:139-145`(조회→조기 반환→enrich) | ✓ — M-E로 1셀 |
| 경로별 처분표 | `dedupe.KEY_REPLAY_ACTIONS`(consume 5·handler 2·stored 1) — 전수 매핑 셀 + 미등록 fail-safe "pass" | ✓ |
| D2 상한 2회·쿨다운 60s | `retry_policy.py:20-23` 양 literal, analysis·generation 양쪽 동일 값 | ✓ — N-d(2→3)·M-H(2→1) 모두 재실패 |
| D2 입장 = `require_quota_standing`(정지 403·소진 402) | `dependencies.py` + `assert_standing`(등재 목록 계약과 충돌하지 않는 재사용 — 브리프에 제약 기록) | ✓ — M-I 2셀 |
| D3 run당 20쌍+이월 | `JudgingBudget` 공유 예산(`runner`가 run마다 1개 생성), 이월 셀 `test_a_fresh_budget_picks_up_the_deferred_pairs` | ✓ — N-e(20→40) 재실패 |
| 선언 — 6경로 +409, 재시도 2경로 +402·403·429 | `test_application_api.py` EXPECTED 행렬 6경로에 409 추가(assertEqual 양방향), `THROTTLED_OPERATIONS` 3경로·`STANDING_GATED_OPERATIONS` 1:1 배선 셀 | ✓ |
| B5 문장 갱신 | SoT v1.8.32 행 + `dedupe.py` 모듈 서술에 동일 문장 | ✓ |
| `quota_replay_responses` 등재 | `mongo_collections.md` §43H(TTL 86400 문서 포함) | ✓ |

### 3. 뮤테이션 (구현자 11종 전부 재현 — 셀 수까지 일치)

| # | 변이 | 결과(재실패 셀) | 구현자 기록 |
|---|---|---|---|
| M-A | 소비 검사 무력화(`False and` 선행) | **4** — `never_counted_twice`·`falls_back_after_ttl`·HTTP 409 2 | 4 ✓ |
| M-B | `force_new=charge.confirmed`→`False` | **2** — 도메인·HTTP +1 셀 | 2 ✓ |
| M-C | 재생 grant 무력화 | **2** — 재생 셀(도메인·HTTP) | 2 ✓ |
| M-D | `and not confirmed` 제거(과잉) | **2** — 확인 재실행 셀 | 2 ✓ |
| M-E | accept enrich 를 replay 앞으로 되돌림 | **1** — `does_not_re_run_the_reporter` | 1 ✓ |
| M-F | analysis 상한 검사 무력화 | **2** — 상한 셀(도메인·HTTP) | 2 ✓ |
| M-G | `cooldown_remaining` 항상 0 | **3** — 쿨다운 셀 | 3 ✓ |
| M-H | `MAX_JOB_RETRIES` 2→1(과잉) | **3** — 상한 셀 | 3 ✓ |
| M-I | `assert_standing` 본문 `return` | **2** — standing 셀 | 2 ✓ |
| M-J | 예산 검사 무력화 | **3** — 예산·이월·fanout | 3 ✓ |
| M-K | 재사용도 예산 차감(과잉) | **3** — 재사용 비과금·이월·fanout | 3 ✓ |

### 4. 검증자 신규 변이 5종 — 2종 무물림

| # | 변이 | 결과 |
|---|---|---|
| N-a | `THROTTLED_OPERATIONS`에서 signup 제거 | **2 failed**(가드③ SUBFAILED + `test_non_billable_429_producers_stay_enrolled_exactly`) — 양방향 잠금 실증 |
| N-b | `STANDING_GATED_OPERATIONS`에 가짜(`/auth/login`) 추가 | **1 failed**(`test_standing_gated_operations_match_the_wiring_exactly`) — 1:1 배선 잠금 실증 |
| N-c | `DEFAULT_REPLAY_TTL_SECONDS` 86400→**3600** | **0 failed(98 passed)** — ★TTL literal 의 하방이 잠겨 있지 않다(→ B1) |
| N-d | `MAX_JOB_RETRIES` 2→**3**(하방) | 2 failed — literal 드리프트 잠힘 |
| N-e | `DEFAULT_MAX_NEW_RELATIONS_PER_RUN` 20→**40**(하방) | 1 failed — literal 드리프트 잠힘 |

상한·예산 literal 은 양방향으로 잠히는데 **재생 TTL 만 하방(짧아지는 방향)이 열려 있다**: 기존 셀들은 "TTL 경과 후 409"(86401 진행)만 잊아 TTL 이 길어지면 실패하지만 짧아지면 통과한다. SoT v1.8.32 와 §43H 가 등재한 "TTL 24시간"의 회복 보증 창이 1시간으로 조용히 줄어도 아무 셀이 안 물린다.

### 5. 전수·산수·스키마·민감정보

- 전수 **2720/151/3206/0**(정상 코드) — 주장과 동일. 셀 산수 독립 재계산: bf71e3f 이후 순증 **42 = S-3 폐쇄 15 + S-1 27** ✓("2693+27" 기록과 일치).
- tsc 0 · 프론트 401/403(사전존재 2)·`gen:api` 재생성 무차이.
- 민감정보: 커밋 전체 diff 의 IP 는 TEST-NET(203.0.113.x·198.51.100.x)·loopback·10.9.0.x 픽스처뿐. 도메인·키 경로·토큰 0건.
- 1차 전수 3실패 → 수리(`82cd7e0`) 후 그린 과정이 work_log 세션 9 에 기록돼 있고 수정 내용(retry_policy 임포트·S12 프로브 쿨다운 반영)이 커밋과 일치.

## Issues / Risks

### Blocking (계약 의무)

- **B1 — 재생 TTL 24시간 literal 의 하방 무셀.** N-c 실측: 86400→3600 변이에 0 실패. 등재된 literal(SoT v1.8.32 "TTL 24시간"·§43H `expireAfterSeconds: 86400`)은 "경과 후 409" 방향으로만 잠혀 있다. 폐쇄: 경계 안(예: 86399 진행 후 재생 성공)을 잰 셀 하나.
- **B2 — `MongoReplayResponseRepository`·`ledger_mongo.has_usage` 테스트 0건.** SoT 가 "인메모리+mongo" 저장을 등재했고 quota 영역에 몽고 테스트 파일 선례(`test_quota_ledger_mongo.py` 등)가 있으며, S-3 폐쇄 슬라이스가 같은 날 `test_auth_signup_guard_mongo.py`(가짜 몽고 7셀)로 규범을 다시 세웠는데 S-1 의 신규 몽고 저장소는 무셀. TTL 인덱스 86400·`has_usage` 포인트 리드가 리팩터링으로 사라져도 무엇도 안 물린다. 폐쇄: 가짜 몽고 셀(인덱스 선언 + round-trip + has_usage).

### Hardening recommendations (비차단)

- **H1 — SoT v1.8.32 행의 근거 서술 오류 2건**(계약 literal 은 전부 정확): ① 셀 내역 괄호의 산수(7+4+1+8+3+1+1+4=**29** ≠ +27 — 총수·전수는 정확), ② "뮤테이션 표는 work_log **세션 8**" → 실제는 **세션 9**. 각 한 줄 정정.
- **H2 — 확인 재실행의 report 경로가 저장 응답을 덮어쓴다**(confirmed 재실행 → 새 응답 저장). 설계상 자연스럽지만 "마지막 응답이 재생된다"가 계약 문구에 없으면 미래 독자가 첫 응답 재생으로 오독할 수 있음 — 문구 명시 권고.
- **H3 — `store_replay_response` 가 `getattr(response, "body", None)` 로만 읽는다** — 표준 `Response` 외 객체(스트리밍 등)는 조용히 미저장 → 재제출이 409. 지금 경로(writing_report)는 전부 `JSONResponse` 라 무해하나, "stored" 처분을 받는 신규 경로가 생길 때의 함정으로 HANDOFF 에 한 줄 가치.

## Verdict

**조건부 합격** — B1 재생 TTL 하방 경계 셀과 B2 몽고 재생 저장소·has_usage 셀을 보강할 때까지.

근거: 구현·검증의 밀도는 S-3 때보다 한 단계 높다 — "실행 전 409"를 HTTP 셀이 `provider.calls` 로 행동 잠금하고(S-3 B1급 공백이 이번엔 없음), +1 과금·재생 무과금·이월까지 전부 기명 셀과 뮤테이션 쌍으로 못박혔다. 구현자 11종 뮤테이션은 전부 재현됐고, 등재 목록 양방향·1:1 배선·409 얼굴 6경로 선언도 실증됐다(N-a·N-b). S-3 검증 조건 4건도 전부 실질 폐쇄를 확인했다. 남은 것은 등재 literal 2개의 사각(하방 TTL·몽고 저장소)이다.

## Outstanding items

- B1·B2 폐쇄는 미실시(검증자는 고치지 않고 보고). 폐쇄 슬라이스가 셀을 더하면 이 기록의 조건은 소멸한다.
- 관찰 반영 확인: `signup_attempts` 의 `mongo_collections.md` 미등재는 S-3 부채로 work_log 에 정확히 기록돼 있음(이번 검증에서 재확인 — §43H 에 `quota_replay_responses` 만 등재). S-0 문서 스윕에서 채울 것.
- 낡은 vhost: HANDOFF 에 "타 프로젝트 AI 처리 중(오너 확인 반영)" — 이 저장소 밖 사안, 대기.

## Reproduction

```bash
# 포커스(키 소비·재시도·판정·가드)
python3 -m pytest tests/test_quota_enforcement.py tests/test_quota_enforcement_api.py \
  tests/test_analysis_job_state.py tests/test_writing_generation_job.py \
  tests/test_identity_judging.py tests/test_identity_judge_runner_wiring.py \
  tests/test_writing_accept.py tests/test_signup_throttle.py tests/test_auth_signup_guard_mongo.py -q

# B1 재현 — quota/replay.py: DEFAULT_REPLAY_TTL_SECONDS = 86400 → 3600 후:
python3 -m pytest tests/test_quota_enforcement.py tests/test_quota_enforcement_api.py -q
# → 98 passed, 0 failed (무물림 입증)

# B2 재현 — tests/ 전체에서:
grep -rn "MongoReplayResponseRepository\|has_usage" tests/   # → 0건

# 전수·프론트
python3 -m pytest tests/ -q          # 2720/151/3206/0
cd frontend && npx tsc --noEmit && npm test   # tsc 0 · 401/403(사전존재 2)
```
