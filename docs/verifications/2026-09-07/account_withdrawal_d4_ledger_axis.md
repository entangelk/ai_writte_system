# 독립 검증 기록 — 계정 탈퇴 D1~D6 확정 + D4 원장 소유 축 개명

## Subject metadata

- **일자**: 2026-09-07 · **요청자**: 오너("다음작업 검증해주소") · **검증자**: 독립 검증 세션(구현 세션 30·31 과 다른 세션)
- **대상 슬라이스**: 계정 탈퇴 착수 전 결정 D1~D6 확정 + 급선책 D4(원장 `user_id` → `target_user_id`). 커밋 `3cb07ce`(세션 30, 계획·브리프 초안)·`badc01a`(D1~D6 확정)·`6eeedf5`(D4 구현)·`db19e30`(기록). 소스 = main HEAD `db19e30`, 트리 clean, origin보다 19커밋 선행(push 대기 — 주장과 일치).
- **정규 스펙**: [`plans/account-withdrawal-implementation-phases.md`](../../plans/account-withdrawal-implementation-phases.md)(D1~D6 확정 표 + D4 완료 절) · SoT **v1.8.43** 행 · 선행 결정 8.2 L1=B(`target_project_id` 선례) · 오너 결정 원문(work_log 세션 31 "User Decisions and Rationale").

## Scope

★ = 가장 의심스러운 축.

1. ★ **D4 개명 범위** — 저장 필드·인덱스 키 3종·질의"만" 움직였는지(메서드 인자·`admin_user_id`·다른 컬렉션은 무변인지).
2. ★ **필드-이름-스위치 전제의 사실성** — `purge_reconciler` 의 발견 성질(`find_one({field: {$exists}})` 표본 한 건)이 원문 그대로인지.
3. 마이그레이션 스크립트 — 멱등·`--dry-run`·옛 인덱스 3개 제거·기본 URI/DB 관행. **실 mongo 왕복 실측** 포함.
4. D1 바로잡은 계약(유예 중 vs 취소 후)과 D3 재시도≠재호출 문언이 계획·work_log에 정확히 남았는지.
5. 셀 경계(이름 계약·키 집합 핀·마이그레이션 5)와 구현자 변이 표 MD-1~MD-4 정직성 — **4종 전부 직접 재유도**.
6. 백엔드 전수·focused 재실측(2903/1/3839).
7. 기록 일관성 — SoT v1.8.43·HANDOFF(배포 항목 마이그레이션 선행)·CHANGELOG·README 기준선·plans 인덱스.

## Methodology

전수·변이 모두 전량 파일 캡처 + 요약 라인 판독. 변이는 매회 프리플라이트 `git status --short` 공백 → Edit → focused → `git checkout --` 원복 → clean 확인(4회 모두). 백엔드 전수는 test-mongo ON(`docker compose -f docker-compose.test.yml up -d`, 127.0.0.1:27020)에서 실행 — skip 1(live Chroma)뿐임을 확인.

```bash
python3 -m pytest tests/test_ledger_user_axis_migration.py tests/test_quota_ledger_mongo.py \
  tests/test_quota_enforcement.py -q        # → 74 passed, 9 subtests
python3 -m pytest -q > /tmp/pytest_full_d4.log 2>&1; echo EXIT=$?
# → 2903 passed, 1 skipped, 3839 subtests in 2250.95s · EXIT=0
# 변이 focused: 위 3파일(MD-3·MD-4·MD-2는 마이그레이션 파일만) — 결과는 F5 표
# 실 mongo 실측(스크래치 DB verify_scratch_ledger_axis — 검증 후 drop):
#   PYTHONPATH=. python3 - <<'EOF' … create_index 같은-이름-다른-키 충돌 + migrate 왕복 EOF
```

## Findings

### F1. ★ D4 개명 범위 — 주장과 정확히 일치

`6eeedf5` diff 전 줄 감독(`ledger.py`·`ledger_mongo.py`):

- **옮긴 것**: 데이터클래스 필드(`UsageEntry`·`AdjustmentEntry`) · 저장 문서 `_usage_doc`/`_adjustment_doc` · 역직렬화 `usage_entry`/`adjustment_entry` · 질의 3종(`has_usage`·`count_usage`·`sum_adjustments`) · **인덱스 키 3종**(`request_usage_ledger_dedupe_unique`·`by_user_day`·`by_user_week`).
- **안 옮긴 것 확인**: ① 서비스 메서드 인자명 — `has_usage(self, user_id, …)` 그대로, `enforcement.py` 의 `user_id=user_id` 조합은 전부 **메서드 호출 kwargs**(저장 아님) ② `admin_user_id` — `_adjustment_doc`·`adjustment_entry` 에 그대로 ③ 다른 컬렉션(세션·job·한도 정책) — 이 슬라이스가 건드린 파일은 quota 원장 2파일·스크립트·테스트뿐(`git show --stat`). quota 패키지에 `"user_id"` 리터럴 잔류 0건(admin_user_id 제외).
- **소비자 오염 없음**: `request_usage_ledger` 컬렉션을 직접 질의하는 코드는 어댑터·마이그레이션·어댑터 테스트뿐. `UsageEntry(`/`AdjustmentEntry(` 외부 생성자 0건. `schema.d.ts`·OpenAPI 무변(operation 102) — 응답 계약을 안 건드린 내부 저장면 개명이다.

### F2. ★ 필드-이름-스위치 전제 — 원문 그대로

`scripts/purge_reconciler.py:56`: `db[name].find_one({_PROJECT_ID_FIELD: {"$exists": True}}, {"_id": 1})` — **표본 한 건**으로 컬렉션을 고르는 발견 방식이 실제 코드다. 따라서 "원장이 `user_id` 를 들면 사용자 축 reconciler 가 통째로 쓸린다"는 D4 의 위험 서술은 구조적으로 정확하다(활동 로그가 `project_id` 를 일부러 유지하는 것과 대칭 — `activity/log.py:31`). 개명의 존재 이유는 성립한다.

### F3. 마이그레이션 — 단위 셀 + 실 mongo 실측 둘 다 통과

- 실측(스크래치 DB, test-mongo 27020): **dry-run** `{documents_with_old_field: 1, renamed: 0}` (무변경) → **적용** `{renamed: 1, dropped_indexes: [옛 dedupe 인덱스]}` → **재실행** `{0, 0, []}` (멱등) → 문서 필드 `target_user_id` 정상. 주장(멱등·dry-run·옛 인덱스 제거) 전부 재현.
- 기본 URI `mongodb://localhost:27520`·DB `DEFAULT_DB_NAME`·컬렉션 상수 import — `purge_reconciler.py`·`migrate_ordered_units.py` 등 선례 스크립트와 같은 패턴(compose `${MONGO_PORT:-27520}` 이 정준).
- **★ 실측으로 확보한 사실 하나**: 같은 이름·다른 키의 인덱스 생성은 MongoDB 가 **code=86 OperationFailure** 로 거부한다. 즉 옛 인덱스가 남으면 새 어댑터의 기동 시 `create_index` 가 깨진다 — "배포 시 마이그레이션 선행"이 권고가 아니라 필요조건임이 서버 동작 수준에서 확인됐다(아래 H1 과 연결).

### F4. D1·D3 문언 — 계획·work_log·SoT 상호 일치

- D1 바로잡은 계약(유예 중 = 로그인 O·조회 O·쓰기 X·유료 X·취소 O / 취소 후 = 제한 전부 소멸)이 계획 D1 행·work_log 세션 31 결정 표(오너 발언 원문 인용 포함)·HANDOFF 11번에 같은 문언으로 있고, **오독 원인(추천 근거가 취소 이후를 가리켰다)이 표에 남았다**.
- D3 "그 버튼은 `execute_project_purge` 재호출이 아니다(404 로 끝난다) — reconciler 경로, DB 발견 성질 유지"도 세 곳(계획 Slice 3 ★실패 처리·D3 행·HANDOFF 11)에 일치한다. 재호출-404 의 근거(core_sot 선킭제)는 `execute_project_purge` 주석의 알려진 한계 서술과 부합한다.
- "2327초는 머신-로컬 값이라 333초와 비교하지 말 것" — 타당한 프레이밍으로 확인: 본 검증의 초록 전수도 **2250.95s**(같은 기계급). 333초 기준선은 다른 머신 값이다. 이번엔 부하를 원인으로 주장한 자리가 없어 교정할 서술도 없다.

### F5. 변이 4종 전부 재유도 — 표는 셀 수까지 정직

| 변이 | 적용 diff | 재유도 결과 | 표와 |
|---|---|---|---|
| MD-1 저장 키 되돌리기 | `_usage_doc` 의 `"target_user_id"` → `"user_id"` | **7 재실패**(6 FAILED + 1 SUBFAILED — 멤버 축 계약·키 집합 핀·왕복·`has_usage`·집계 분리·타 회원 미계수·aware 날짜) | 일치(7) |
| MD-2 옛 인덱스 미제거 | `for name in _STALE_INDEXES` → `for name in ()` | **1 재실패**(인덱스 제거 셀) | 일치(1) |
| MD-3 행위자 오개명(over) | `$rename` 대상을 `admin_user_id` 로 | **4 재실패**(행위자 보존 셀 포함) | 일치(4) |
| MD-4 dry-run 무력화 | `if dry_run or pending == 0` → `if pending == 0` | **1 재실패**(dry-run 셀) | 일치(1) |

MD-1 의 7에는 SUBFAILED 가 포함된다 — 요약 라인(`7 failed`)을 읽었지 `grep FAILED`(6만 보임)에 의존하지 않았다(가이드의 실측 교훈 적용).

### F6. 전수·기준선 산술

- 백엔드 전수 **2903 passed / 1 skipped / 3839 subtests · EXIT=0**(본 검증 캡처, 2250.95s). skip 1 = live Chroma ✓.
- 산술: 2892(09-06 기준선) + 정책 문서 슬라이스 5(v1.8.40 +3·v1.8.42 +2) + D4 6 = **2903** ✓. subtests 3798 + 28 + 2 + 11 = **3839** ✓. HANDOFF 기준선 행·README 절차 표 갱신 일치.
- focused 3파일 74 passed / 9 subtests. plans 인덱스·문서 위생 가드는 전수 초록으로 간접 확인(세션 30 이 카운트 혼동(106/106)으로 걸렸던 자리는 현재 정합).

### F7. 기록 일관성

SoT v1.8.43(헤더·변경이력 행 — 범위·마이그레이션·opt-in/opt-out 관점 기재) · CHANGELOG 행 · HANDOFF 5번(**배포 시 마이그레이션 선행** + "안 돌리면 사용량이 0으로 보인다") · 11번(D4 폐쇄 + 마이그레이션 경고) · work_log 세션 30·31(오너 발언 원문·Issues found 2건 정직). "커밋 3개 push 안 함" ✓(세션 31분 3커밋; 세션 30분 `3cb07ce`까지 합치면 4 — 보고 문언과 모순 아님).

## Issues / Risks

### Blocking (계약 의무)

**없음.**

### Hardening (비차단)

1. **H1 — 마이그레이션의 부분 실패 창(실측 근거).** `update_many`(문서 개명)와 `drop_index` 사이에 프로세스가 죽으면, 재실행은 `pending == 0` 조기 반환이라 **옛 인덱스를 영원히 안 지운다** — 그 상태로 앱을 기동하면 어댑터의 같은-이름-다른-키 `create_index` 가 **code=86**으로 거부돼 기동이 깨진다(F3 실측). 정상 경로 멱등 셀은 통과하므로 계약 위반은 아니나, 실패 모양이 "사용량 0"보다 더 성가신 "기동 불가"다. 처방: 옛 인덱스 제거를 `pending > 0` 게이트가 아니라 **실제 키로 판정**(`list_indexes` → 키에 `user_id` 가 있는 것만 drop)하면 ① 크래시 창이 닫히고 ② 어댑터가 새 키 인덱스를 같은 이름으로 만든 뒤의 재실행도 안전해진다. 겸하여 `except Exception: continue` 는 권한 오류 같은 실제 실패도 삼키니, report 의 `dropped_indexes` 가 비면 경고를 인쇄하는 편이 저렴하다.
2. **H2 — 멱등 셀이 `dropped_indexes == []` 다리를 안 잠근다.** `test_running_it_twice_changes_nothing_the_second_time` 은 문서 무변만 단정한다. 재실행이 drop 을 *시도*해도 가짜 컬렉션이 `KeyError` 를 내고 스크립트가 이를 삼켜 셀은 그대로 통과한다 — "재실행은 어댑터가 새로 만든 인덱스를 건드리지 않는다"는 성질이 무가드다(H1 처방과 함께 `second["dropped_indexes"] == []` 한 줄이면 닫힘).

## Verdict

**합격** — D4 의 개명 범위가 주장과 한 줄 차이 없이 저장면에 한정됐고, 개명의 존재 이유(필드-이름-스위치)가 `purge_reconciler` 원문에서 성립하며, 마이그레이션이 단위 셀과 실 mongo 왕복 양쪽에서 멱등·dry-run·옛 인덱스 제거를 재현했다. 구현자 변이 4종을 전부 재유도해 셀 수까지 일치했다. 전수 2903/1/3839·EXIT=0 재현, 기준선 산술·기록 4건 상호 일치. D1 바로잡은 계약과 D3 재시도 문언이 계획·work_log·HANDOFF에 일치한다.

## Outstanding items

- **배포 대기**: 마이그레이션 선행(`python scripts/migrate_ledger_user_axis.py` — 앱 기동 전, HANDOFF 5번 명시됨) + 프론트 이미지 재빌드(장면 메모 후속분, 누적).
- 하드닝 H1·H2는 비차단 — Slice 3(사용자 축 reconciler) 착수 전에 닫으면 마이그레이션을 다시 만질 일이 없다(유예 항목엔 트리거를 붙이는 저장소 규범상 그대로 둔다).
- 계정 탈퇴 Slice 0~5 미착수(D1~D6 전부 확정 — 착수 가능).

## Reproduction

```bash
docker compose -f docker-compose.test.yml up -d   # test-mongo 27020
python3 -m pytest tests/test_ledger_user_axis_migration.py tests/test_quota_ledger_mongo.py \
  tests/test_quota_enforcement.py -q              # 74 passed / 9 subtests
python3 -m pytest -q > /tmp/v.log 2>&1; echo EXIT=$?   # 2903/1/3839, ~2250s
# 실 mongo 실측: 스크래치 DB 에서 (a) 같은-이름-다른-키 create_index → code=86,
#   (b) migrate() dry-run→적용→재실행 왕복 — 본 기록 Methodology 의 heredoc 참조
# 변이: F5 표의 diff 로 Edit → focused → git checkout -- → git status --short 공백
```
