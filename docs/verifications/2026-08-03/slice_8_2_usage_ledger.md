# 독립 검증 — Phase 8 Slice 8.2 사용량 원장 (L1=B·L2~L5=A)

- **날짜**: 2026-08-03
- **요청자**: 오너("8.2 완료했습니다 (652aa0a) … 검증해줘")
- **검증자**: Claude Code(본 세션, 구현에 관여 안 함)
- **대상**: Slice 8.2 — 회원 사용량 원장(`request_usage_ledger`). 8.0이 "무엇을 세는지", 8.1이 "얼마나 쓸 수 있는지"를 닫았고, 이 슬라이스가 그 사이 **"이번 창에서 몇 번 썼는가"**를 기록·집계한다(차단 없음).
- **정본 계약**: [`docs/plans/08-2-usage-ledger-decisions.md`](../../plans/08-2-usage-ledger-decisions.md)(L1~L5) + [`docs/plans/08-member-request-quota.md`](../../plans/08-member-request-quota.md) §4·§5 + [`docs/system-contract-sot.md`](../../system-contract-sot.md) **v1.7.85** + [`docs/mongo_collections.md`](../../mongo_collections.md) §43D
- **검증 대상 소스**: 커밋 `652aa0a`. HEAD `652aa0a`, 작업 트리 clean(뮤테이션 전부 원복).
- **머신**: 베탠(GTX 1060 3GB), test-mongo(rs-test, `127.0.0.1:27020`) ON.

## Scope

1. 원장 도메인 — `quota/ledger.py`(사용 행·조정 행·창 집계, 차단 없음).
2. Mongo 어댑터 — `quota/ledger_mongo.py`(부분 유니크 인덱스·`_aware`·`target_project_id`).
3. **★ 가장 의심한 축 — `target_project_id`와 파기 reconciler의 크로스 슬라이스 상호작용.** "이름이 `project_id`면 파기 reconciler가 과금 기록을 지운다"는 주장이 참이려면 reconciler가 실제로 `project_id` 필드로 컬렉션을 **DB에서 발견**해야 한다(하드코딩 목록이면 근거가 다르다).
4. **L2 근거 실측** — "프론트가 한 흐름에서 4개 유료 동작에 같은 uuid를 쓴다"는 사실 주장을 프론트 코드로 확인.
5. 부분(partial) 유니크 인덱스 함정 — 조정 행의 (user,null,null) 중복 거부.
6. 음수 사용량·미-clamp·naive 재부착·창 키 위임.
7. 회귀 — 집중(29 cells) 및 전체 suite.

## Methodology

계약을 먼저 읽고 경계 매트릭스를 세운 뒤, 각 분기를 코드·크로스 슬라이스 실측·뮤테이션으로 채웠다.

- 집중: `python3 -m pytest -q tests/test_quota_ledger.py tests/test_quota_ledger_mongo.py`.
- **뮤테이션 7종(백업→적용→실행→원복→`git diff` 0 확인)**.
- 크로스 슬라이스: `scripts/purge_reconciler.py` 발견 로직 직독, `main.py` purge_project 호출 목록, `auth/admin_audit.py` 선례, 프론트 `DraftEditor.tsx`/test uuid 공유.
- 전체: `python3 -m pytest -q tests/`(test-mongo ON, 832s).

## Findings

### F1. ★ `target_project_id` 크로스 슬라이스 주장 — 실측으로 참 (이 슬라이스의 핵심)

과금 기록이 project 파기에서 살아남는다는 오너 결정("삭제돼도 사용 기록은 남는다")이 **필드 이름 하나에 달려 있다**는 주장을 직접 실측:

- [`scripts/purge_reconciler.py:43`](../../../scripts/purge_reconciler.py#L43) `_PROJECT_ID_FIELD = "project_id"` — 발견 기준 필드는 글자 그대로 `project_id`.
- [:53-56](../../../scripts/purge_reconciler.py#L53) `list_collection_names()` + `find_one({"project_id": {"$exists": True}})` — 컬렉션 목록을 **하드코딩하지 않고 DB에서 발견**한다. `project_id` 필드를 가진 컬렉션만 고아 sweep 대상.
- [:67-77](../../../scripts/purge_reconciler.py#L67) `distinct(project_id)` + `delete_many({"project_id": ...})`.
- [`main.py:3160-3172`](../../../services/application/app/main.py#L3160) 파기 endpoint가 각 서비스 `purge_project(project_id=...)`를 명시적으로 부르는데, **원장은 이 목록에 없다**(미배선).

→ `request_usage_ledger`는 전 행이 `target_project_id`를 쓰고 `project_id` 필드가 없으므로 발견 대상이 아니라 **두 파기 경로(명시 호출·고아 reconciler) 모두에서 살아남는다**. [`auth/admin_audit.py:1-7`](../../../services/application/app/auth/admin_audit.py#L1)의 D8-6 tombstone 선례와 같은 패턴. 작업자 주장 정확.

### F2. L2 근거 — 프론트가 한 흐름의 uuid를 공유한다 (실측)

"dedupe 키에 action이 필요한 이유는 프론트가 generate·gate·revise·accept에 같은 uuid를 싣기 때문"을 프론트 코드로 확인: [`frontend/src/drafts/DraftEditor.tsx:226`](../../../frontend/src/drafts/DraftEditor.tsx#L226)가 intent마다 `crypto.randomUUID()` 하나를 만들고 [:232] `idempotency_key: intent.key`로 쓰며, [`DraftEditor.test.tsx:348-349`](../../../frontend/src/drafts/DraftEditor.test.tsx#L348)가 **calls[3]·calls[4]가 같은 "intent-1"**을 보낸다고 단정한다. 즉 한 흐름의 여러 유료 호출이 같은 uuid를 공유 → `(user, dedupe_key)`만으로 잡으면 8.0의 "요청 1건=1회"가 조용히 접힌다. `action` 포함은 필수이며 [`test_quota_ledger.py:61`](../../../tests/test_quota_ledger.py#L61)가 못박는다.

### F3. 부분 유니크 인덱스 — 코드·하네스·뮤테이션으로 입증

[`ledger_mongo.py:44-50`](../../../services/application/app/quota/ledger_mongo.py#L44) 유니크 인덱스가 `partialFilterExpression={"kind": "usage"}`로 제한된다 — 조정 행(action/dedupe_key 없음)은 (user,null,null)로 보여 전체 인덱스면 2번째 조정 행이 거부된다(L5가 만든 함정). 가짜 collection [`test_quota_ledger_mongo.py:42-61`](../../../tests/test_quota_ledger_mongo.py#L42)가 `insert_one`에서 `partialFilterExpression`을 검사해 **부분 인덱스 규칙을 실제로 흉내** 내고, `test_many_adjustments_coexist_despite_the_unique_index`([`:147`](../../../tests/test_quota_ledger_mongo.py#L147))가 3 조정 행 공존을 단정한다.

### F4. 나머지 계약 — 음수·naive·창 키 위임·비중복 필드

- **음수 미-clamp**: [`ledger.py:83-94`](../../../services/application/app/quota/ledger.py#L83) `WindowUsage`가 daily/weekly를 그대로 둬 환급>사용이면 음수가 된다. "한도 넘는 보너스는 관리자가 만든 정당한 상태" — 잔여 해석은 8.3.
- **naive 재부착**: [`ledger_mongo.py:33-36`](../../../services/application/app/quota/ledger_mongo.py#L33) `_aware`, 가짜 하네스가 naive 반환 + `test_the_fake_really_returns_naive_dates` 가드의 가드(8.1·8.2 동일 패턴).
- **창 키 위임**: [`ledger.py:158-160`](../../../services/application/app/quota/ledger.py#L158) `_windows`가 8.1의 `daily_key`/`weekly_key`를 부른다(여기서 재계산 안 함) — KST 단일 지점 결정이 유지.
- **비중복 필드**: [`test_quota_ledger.py:200`](../../../tests/test_quota_ledger.py#L200)가 UsageEntry∩AdjustmentEntry 필드 차를 구조 단정(사용={action,dedupe_key} / 조정={delta,reason,admin_user_id}).
- **미배선**: `create_app`·main.py에 `UsageLedger`/`request_usage_ledger` 참조 0건(소비자는 8.3).

### F5. 회귀 — 작업자 주장과 정확히 일치

- 집중: **29 passed / 2 subtests**.
- 전체 backend(test-mongo ON): **1984 passed / 1 skipped / 1717 subtests**(832s, exit 0). 작업자 주장과 정확히 일치, 회귀 0.

### F6. 뮤테이션 7종 — 전부 작업자 주장과 **정확히** 일치 (직접 실증)

| 뮤테이션 | 작업자 주장 | 내 실측 |
|---|---|---|
| dedupe 키에서 `action` 제거 | 3 fail | **3 fail** |
| `target_project_id`→`project_id` 개명 | 26 fail | **26 fail** |
| 부분 인덱스 조건 제거 | 2 fail | **2 fail** |
| `_total`에서 조정 합 누락 | 2 fail | **2 fail** |
| 사용량 0 clamp | 1 fail | **1 fail** |
| 창 키 자체(UTC) 계산 | 1 fail | **1 fail** |
| `_aware` 제거 | 2 fail | **2 fail** |

전부 원복 뒤 `git diff` 0라인, 29 passed 복귀. **7종 전두 카운트 정확히 일치** — 이번 슬라이스는 뮤테이션 주장이 한 건도 어긋나지 않았다.

## Issues / Risks

### Blocking (계약 의무)

- **없음.** 경계 매트릭스(dedupe=(user,action,key)·두 종류 비중복·부분 인덱스·음수 미-clamp·target_project_id·회원/창 격리·창 키 위임·naive 왕복·차단 없음)에 빈 칸이 없고, 7종 뮤테이션이 정확히 물리며, 핵심 크로스 슬라이스 주장이 실측 참이다.

### Hardening recommendations (비차단)

- **H1(8.1에서 이어짐, 실위험 낮음)** — `record_usage`/`record_adjustment`가 받는 `member_created_at`는 caller 책택인데, 원천인 `users_mongo.py`가 UTC 재부착하므로 aware로 들어온다. 창 키 위임이 8.1 함수를 부르므로 동일하게 안전.
- **H2 — 파기 reconciler 발견은 표본 샘플이다.** `find_one({project_id: {$exists}})`로 한 문서라도 `project_id`가 있으면 그 컬렉션 전체가 sweep 대상이 된다. 지금 원장은 전 행이 `target_project_id`라 안전하나, 향후 원장 문서에 실수로 `project_id`가 섞이면 컬렉션이 발견돼 과금 기록이 지워질 수 있다. 필드명 계약 셀(213·170)이 dataclass 수준에서 지키지만, mongo doc 수준의 회귀(예: 저장 직후 `project_id` 부재 단정)를 8.3 배선 시 보강 후보로 남긴다.
- **H3(정보, 본 슬라이스 비관여) — 8.2b의 TTL 함정이 이미 HANDOFF에 박혀 있다.** 다음 슬라이스(5초 중복 가드 DB 잠금)의 핵심 함정 "TTL을 판정에 쓰면 안 된다(Mongo TTL 삭제는 ~60s 주기라 5초가 아니라 최대 1분 잠김; TTL은 청소용, 판정은 expires_at 비교)"와 회귀에 들어갈 셀 둘이 HANDOFF에 명시돼 있다 — 8.2b 검증 때 직접 볼 것.

## Verdict

**합격(PASS).**

하중 이유: ① **핵심 크로스 슬라이스 주장(target_project_id ↔ 파기 reconciler)이 실측으로 참** — reconciler가 `project_id` 필드 DB 발견 방식이라 원장은 파기에서 살아남는다 ② L2(action 포함)의 프론트 근거(uuid 공유)를 프론트 코드로 입증 ③ 부분 유니크 인덱스 함정을 코드·하네스·뮤테이션으로 세 겹 확인 ④ naive/창키위임/음수/비중복필드 전부 단정 ⑤ 뮤테이션 7종이 주장 카운트와 **한 건도 어긋나지 않게** 물린다 ⑥ 회귀 1984/1/1717 정확히 일치·회귀 0. H1~H3은 비차단(실위험 낮음·본 슬라이스 비관여 또는 8.3 보강 후보).

## Outstanding items

- **test-mongo를 검증을 위해 올렸다**(`127.0.0.1:27020` PRIMARY). 검증 종료 후 베타 원 상태(down)로 내린다.
- `652aa0a`는 push되지 않았다.
- 원장(기록·집계)만 닫혔고 시행은 없다(미배선). 다음은 **8.2b(L7 — 5초 중복 가드 DB 잠금)**, 그리고 8.3 시행. 핵심 함정(TTL≠판정)이 HANDOFF에 이미 박혀 있다.
- (참고) L6·L7은 브리프에 8.2c·8.2b로 명시돼 있다(L1~L5만 이번에 구현).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
docker compose -f docker-compose.test.yml up -d      # 127.0.0.1:27020, rs-test

# 1. 집중 가드
python3 -m pytest -q tests/test_quota_ledger.py tests/test_quota_ledger_mongo.py  # 29 passed

# 2. 전체 회귀
python3 -m pytest -q tests/                          # 1984 passed / 1 skipped / 1717 subtests

# 3. 뮤테이션(백업 후 원복) — 예: 부분 인덱스 제거
LM=services/application/app/quota/ledger_mongo.py
cp "$LM" /tmp/lm.bak
# partialFilterExpression={"kind":"usage"} 줄을 지우면 → 2 failed → cp /tmp/lm.bak "$LM"
git diff -- "$LM" | wc -l                             # 0

# 4. 핵심 크로스 슬라이스 실측 — reconciler 발견 방식
grep -n "_PROJECT_ID_FIELD\|list_collection_names\|find_one" scripts/purge_reconciler.py

docker compose -f docker-compose.test.yml down
```
