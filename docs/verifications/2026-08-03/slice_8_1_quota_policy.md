# 독립 검증 — Phase 8 Slice 8.1 요청 한도 정책 저장 계약 (P1~P8)

- **날짜**: 2026-08-03
- **요청자**: 오너("8.1 완료했습니다 (77d3254). 결정 7개가 다 닫혀서 브리프에서 멈추지 않고 구현까지 갔습니다 … 검증해줘")
- **검증자**: Claude Code(본 세션, 구현에 관여 안 함)
- **대상**: Slice 8.1 — 회원별 요청 한도 정책 저장 계약(이중 창·KST 경계·파생·P6 필드별 발효·naive 재부착). 8.0이 "무엇을 1회로 세는가"를 닫았고, 이 슬라이스는 그 숫자에 **한도를 붙이는 저장 계약**이다(시행 없음).
- **정본 계약**: [`docs/plans/08-1-request-quota-policy-decisions.md`](../../plans/08-1-request-quota-policy-decisions.md)(P1~P8) + [`docs/plans/08-member-request-quota.md`](../../plans/08-member-request-quota.md) §4·§5 + [`docs/system-contract-sot.md`](../../system-contract-sot.md) **v1.7.84** + [`docs/mongo_collections.md`](../../mongo_collections.md) §43C
- **검증 대상 소스**: 커밋 `77d3254`. HEAD `77d3254`, 작업 트리 clean(뮤테이션 전부 원복).
- **머신**: 베타(GTX 1060 3GB), test-mongo(rs-test, `127.0.0.1:27020`) ON.

## Scope

1. 정책 도메인 — `quota/policy.py`(창 파생·한도 표현·기본값 해석·P6 필드별 발효·서비스, 시행 코드 부재).
2. Mongo 어댑터 — `quota/policy_mongo.py`(`_aware` 재부착, `_id`=`user_id` 1행 강제, 추가 인덱스 없음).
3. 가장 의심한 축 — **naive/aware 함정**(이 레포의 반복 사고, 2026-07-27 `GET /auth/me` 500의 원인)을 하네스가 재현하는가, `_aware`가 실 Mongo에서만 날 TypeError를 잡는가.
4. 경계 산술 — 일(KST 자정)·주(가입일 자정 기준 7일)의 floor/반개구간 `[start,end)`, `<`↔`<=` 함정.
5. 정지 유예 안전망 — "정지 1주 유예가 안전한 이유는 계정 비활성화가 매 요청 `is_active`를 본다"는 근거가 참인가.
6. "도는 작업 없음" 주장 — 파생 창 + 순수함수 발효로 스케줄러/배경작업이 진짜 없는가, `create_app` 미배선인가.
7. 회귀 — 집중(26 cells) 및 전체 backend suite.

## Methodology

계약을 먼저 읽고 경계 매트릭스를 세운 뒤, 각 분기를 코드·테스트·뮤테이션·실측로 채웠다. 작업자 주장은 가설로 취급.

- 집중: `python3 -m pytest -q tests/test_quota_policy.py tests/test_quota_policy_mongo.py`.
- **뮤테이션 8종(백업→적용→실행→원복→`git diff` 0 확인)**: `_aware` 제거 · `BOUNDARY_TIMEZONE`→UTC · `split_change` 즉시화(유예 제거) · `_rank` None=−∞ 뒤집기 · 주 기준 가입 시각화 · `_env_limit` 미설정=None · 덩어리 판정 · None→0 직렬화.
- 전체: `python3 -m pytest -q tests/`(test-mongo ON, 953s).
- 안전망 실측: `main.py:1456` `is_active` 직독, `users_mongo.py` created_at aware 확인, `create_app`/스케줄러 grep.

## Findings

### F1. 결정 7개(P1~P8) 전부 확정·구현, 브리프↔코드↔SoT 일치

브리프 [`08-1…:3`](../../plans/08-1-request-quota-policy-decisions.md#L3) 상태 `Resolved`, P1~P8(＋P2-a/P2-b) 전부 오너 확정. P8=위임받아 **A(8.6으로 미룸)**, 신규 Phase 계획서 없음(부모 계획 8.6 결제 seam이 이미 잡음). SoT v1.7.84·mongo §43C·CHANGELOG·HANDOFF·plans index 전부 갱신. 코드는 `policy.py`·`policy_mongo.py` 두 파일이 전부(시행 코드 0줄 — `NoEnforcementHereTest`가 `consume/charge/deduct/counter/usage` 심볼 부재를 단정).

### F2. 파생 창 — 스케줄러 없음, `create_app` 미배전, 주장 정확

- `daily_key`([`policy.py:97`](../../../services/application/app/quota/policy.py#L97))·`weekly_cycle_bounds`([`:103`](../../../services/application/app/quota/policy.py#L103))·`effective_limits`([`:166`](../../../services/application/app/quota/policy.py#L166))는 전부 **순수 함수**. 리셋/발효는 키가 바뀌는 것이지 도는 것이 아니다.
- `effective_limits`가 P6 예약을 **읽는 쪽에서** 해석(`now >= effective_at`이면 pending) → 발효를 위한 배경 작업 불필요. `clear_pending`([`:291`](../../../services/application/app/quota/policy.py#L291))은 선택적 정리(해석은 이미 pending을 반영).
- `grep`: `create_app`·main.py 어디서도 `QuotaPolicy`/`request_quota_policies` 참조 0건 — **미조립**(소비자는 8.3). 스케줄러/cron이 quota를 참조 0건. 오너 주장(Q5) 정확.

### F3. naive/aware 함정 — 하네스가 진짜로 재현하고, `_aware`가 실 Mongo 함정을 잡는다

이 레포의 반복 사고(pymongo naive ↔ aware `TypeError`, fake는 재현 못 함)를 이 슬라이스가 정확히 방어:

- [`policy_mongo.py:25-34`](../../../services/application/app/quota/policy_mongo.py#L25) `_aware`: naive에 UTC 재부착(`replace(tzinfo=UTC)` — BSON은 UTC라 재명명). `effective_at`·`updated_at` 읽기 때 적용.
- 테스트 하네스 [`test_quota_policy_mongo.py:45-50`](../../../tests/test_quota_policy_mongo.py#L45) `_strip_tzinfo`: 저장 시 tzinfo를 벗겨 **드라이버처럼 naive로 돌려준다**.
- [`test_the_fake_really_returns_naive_dates`](../../../tests/test_quota_policy_mongo.py#L127)가 "하네스가 naive를 돌려줄 것"을 못박음 → 가드의 가드(하네스가 aware로 바뀌면 `_aware`를 지워도 green이 되는 함정 원천 차단).
- [`test_dates_come_back_comparable_to_an_aware_now`](../../../tests/test_quota_policy_mongo.py#L112)이 `_aware` 제거 시 실 Mongo에서만 날 `TypeError`를 여기서 잡는다.

### F4. 경계 산술 — floor·반개구간·`<`↔`<=` 함정, 직전/직후 단정

`weekly_cycle_bounds`는 `elapsed // _WEEK`(floor)로 `[start, start+7일)` 반개구간. 경계 순간은 **새 주기 귀속**(`test_the_week_turns_over_exactly_seven_days_later`가 just_before→옛 키·at end→새 키를 함께 단정, [`test_quota_policy.py:65`](../../../tests/test_quota_policy.py#L65)). `effective_limits`의 `now >= effective_at`도 같은 귀속(`test_lowering…`가 effective_at→pending값·just_before→옛값 단정, [`:151`](../../../tests/test_quota_policy.py#L151)). 한쪽만 보면 `<`↔`<=` 실수가 통과하지만, 두 셀이 양쪽을 못박는다.

### F5. 정지 유예 안전망 — 오너 근거가 실측으로 참

"정지가 최대 1주 늦어도 즉시 차단 수단이 있다"는 근거를 직접 확인: [`main.py:1456`](../../../services/application/app/main.py#L1456) `current_user_or_none`가 매 요청 `if user is None or not user.is_active: return None` — 비활성화된 계정의 **기존 세션까지 즉시** 끊긴다(주석 명시). quota 정지(요금 정책) ≠ 계정 비활성화(출입 차단)라는 분리가 성립. `_favorable_status`(ACTIVE→SUSPENDED는 불리→유예, SUSPENDED→ACTIVE는 유리→즉시)가 이를 반영, `test_suspending_waits_but_lifting_a_suspension_is_immediate`가 단정.

### F6. 회귀 — 작업자 주장과 정확히 일치

- 집중: **26 passed**(policy 20 + policy_mongo 6).
- 전체 backend(test-mongo ON): **1952 passed / 1 skipped / 1715 subtests**(953.5s, exit 0). 작업자 주장과 정확히 일치, 회귀 0.

### F7. 뮤테이션 — 8종 전부 가드가 문다 (직접 실증)

| 뮤테이션 | 작업자 주장 | 내 실측 | 비고 |
|---|---|---|---|
| `_aware` 제거 | 2 fail | **2 fail** | 일치 |
| `BOUNDARY_TIMEZONE`→UTC | 4 fail | **4 fail** | 일치 |
| 유예 제거(전부 즉시) | 7 fail | **7 fail** | 일치 |
| `_rank` None=−∞ 뒤집기 | 1 fail | **1 fail** | 일치 |
| 주 기준 가입 시각화 | 2 fail | **2 fail** | 일치 |
| env 미설정=None(무제한) | 6 fail | **6 fail** | 일치 |
| 덩어리 판정 | 1 fail | **7 fail** | 내 변형이 더 공격적 — 핵심 `test_a_mixed_change_splits_per_field` 깨짐 확인(카운트는 뮤테이션 모양 의존) |
| None→0 직렬화 | 1 fail | **2 fail** | 두 필드 모두 바꿔 round-trip 셀까지 잡음(모양 차이) |

전부 원복 뒤 `git diff` 0라인, 26 passed 복귀. **8종 전두 가드가 물며**, 6종은 주장 카운트와 정확히 일치한다. 나머지 2종도 가드는 확실히 문다(카운트 차이는 내 뮤테이션 모양이 달라서이지 가드 결함이 아니다).

## Issues / Risks

### Blocking (계약 의무)

- **없음.** 경계 매트릭스(일/주 창 경계·무제한/0/정지 구분·행 없음→기본값·P6 필드별 발효·pending 1건·naive 왕복·시행 코드 부재·1행 강제)에 빈 칸이 없고, 뮤테이션 8종이 물며, 안전망 근거가 실측 참이다.

### Hardening recommendations (비차단)

- **H1 — 창 순수 함수가 aware 입력을 가정(단정은 없음), 그러나 현재 입력 경로는 전부 aware라 실위험 낮다.** `_local`([`policy.py:93`](../../../services/application/app/quota/policy.py#L93))이 `astimezone`를 쓰는데, naive가 오면 시스템 로컬로 해석해 비-UTC 호스트에서 조용히 잘못 anchor한다. 단, (a) 기본 clock은 `datetime.now(UTC)`(aware), (b) `created_at` 입력원인 `users_mongo.py:92-94`가 created_at에 UTC를 재부착한다 — 그래들 8.3 배선이 `user.created_at`을 넘기면 aware로 들어온다. 따라서 지금은 live 위험이 아니다. 다만 순수 함수 자체에 awareness 단정이 없으므로, 향후 naive `now`/`created_at`을 넘기는 호출부가 생기면 함정이 되살아난다 — 입력 다양화 시 awareness assert를 고려.
- **H2 — `clear_pending`은 자동 호출되지 않는다(설계상, 스케줄러 없음).** `pending` 필드는 다음 쓰기 또는 명시적 호출 전까지 문서에 남지만, `effective_limits`가 이미 pending을 반영하므로 정합성에는 영향 없다. 8.5 관리자가 원본 문서를 직접 읽으면( effective_limits가 아니라) 만료된 pending이 "대기 중"으로 보일 수 있으니, 관리자 조회는 `effective_limits`를 거치라는 점을 8.5에서 명시 권장.
- **H3(정보) — 뮤테이션 카운트는 모양 의존적.** 덩어리/None→0 두 종은 내 변형이 작업자 주장 카운트(1/1)와 달랐다(7/2). 가드 존재·효과는 확증했으나, "N fail" 보고는 특정 뮤테이션 모양에 묶인 값임을 독자가 알 것.

## Verdict

**합격(PASS).**

하중 이유: ① 결정 7개 전부 확정·구현, 브리프↔코드↔SoT↔§43C 일치 ② naive/aware 함정(이 레포의 반복 사고)을 하네스가 진짜로 재현하고 `_aware`가 잡는다 ③ 경계 산술이 floor·반개구간·`<`↔`<=` 함정을 직전/직후 셀로 못박는다 ④ 정지 유예 안전망 근거(`main.py:1456` is_active)가 실측 참 ⑤ "도는 작업 없음·미배선" 주장 정확 ⑥ 회귀 1952/1/1715 정확히 일치·회귀 0 ⑦ 뮤테이션 8종 전부 물린다(6종 카운트 정확). H1~H3은 비차단(본 슬라이스 비관여 또는 정보).

## Outstanding items

- **test-mongo를 검증을 위해 올렸다**(`127.0.0.1:27020` PRIMARY). 검증 종료 후 베타 원 상태(down)로 내린다.
- `77d3254`는 push되지 않았다(오너 push 규칙).
- 저장 계약만 닫혔고 시행은 없다 — 다음은 **8.2 사용량 원장 브리프**(입력: 8.1의 `daily_key`/`weekly_key` + 8.0의 `action` 리터럴). **8.3이 함께 다룰 미결**: P6 부작용인 "이미 쓴 양 > 새 한도" 상태에서의 거부 동작(거부만·회수 없음)이 HANDOFF에 명시돼 있다.
- (참고) 직전 8.0 검증의 비차단 지적 H1~H4는 작업자가 `80c24a5`에서 폐쇄했으며, 본 8.1 작업이 README 기준선(1,952)·SoT(v1.7.84)·`일치` 가드 강화까지 마쳤다 — 검증 피드백 루프가 닫혔다.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
docker compose -f docker-compose.test.yml up -d      # 127.0.0.1:27020, rs-test

# 1. 집중 가드
python3 -m pytest -q tests/test_quota_policy.py tests/test_quota_policy_mongo.py  # 26 passed

# 2. 전체 회귀
python3 -m pytest -q tests/                          # 1952 passed / 1 skipped / 1715 subtests

# 3. 뮤테이션 8종(백업 후 원복, diff로 확인) — 예: naive 함정
M=services/application/app/quota/policy_mongo.py
cp "$M" /tmp/m.bak
# _aware(...) 랩을 벗기면 → 2 failed → cp /tmp/m.bak "$M"
git diff -- "$M" | wc -l                             # 0

# 4. 안전망·미배선 실측
sed -n '1448,1458p' services/application/app/main.py # is_active per request
grep -rn "QuotaPolicy\|request_quota_policies" services/application/app/main.py  # (없음)

docker compose -f docker-compose.test.yml down
```
