# version read API 독립 검증 (version/snapshot 재조회 public 표면)

## Subject Metadata

- **날짜**: 2026-06-28
- **요청자**: 사용자 ("version read API 완료. 커밋 c43d945. … 의심하고 또 의심해줄래?")
- **검증자**: Claude (본 세션)
- **대상 커밋**: `c43d945` — feat: add draft version read API (version/snapshot read-back)
- **정본 spec 참조** (work_log의 "plan 01 §13/§30" 인용은 부정확 — plan 01은 § 기호를 쓰지 않고, SoT에도 §13/§30 절이 없음. 아래가 실제 canonical 범위):
  - `docs/system-contract-sot.md` **v1.4** — §96–118 Source of Truth / 저장·보존 계약(특히 §110 재조회 pointer/version/hash, §112 `idempotency_key` 필수, §115 archive 보존)
  - `docs/system-contract-sot.md` §128–134 추적성(§132 재조회)
  - `docs/plans/01-core-sot.md` — "수용 기준"(L89–95, 특히 L93 `project_id` 격리), "승인된 저장·보존 계약"(L73–87), "반드시 잠글 계약"(L50–59)
  - 선행 독립 검증 `docs/verifications/2026-06-28/project_draft_list_get_api.md`(read-allowed 해석, 정렬 일관성)
- **작업 출처**: committed (`c43d945`). `git status` clean.
- **검증 입장**: 방어 코드가 실제로 동작하는지(독립 재현), contract 분기가 회귀로 잠겼는지(boundary matrix 빈칸), reported 테스트 숫자가 재계산 가능한지, 계약 인용이 정확한지를 증명.

## Scope

1. **커밋 무결성**: `c43d945`가 service/repository/mongo/main/models/test 모두 포함하는지
2. **API 엔드포인트 2종**: `main.py` `GET .../versions`(목록, version_number 순)·`GET .../versions/{version_id}`(단건 read-back)
3. **격리 분기(boundary matrix)**: project_id·draft_id 양쪽 일치 강제 — should-fire(존재→200) / should-NOT-fire(없음·cross-draft·cross-project→404) 분기 각각이 명명 회귀에 1:1 매핑되는지
4. **archive read-allowed**: §115 보존 + 선행 검증의 read-allowed가 version read에도 적용되는 분기 추적
5. **payload 계약**: `idempotency_key` 미노출(list·detail 양쪽), detail = snapshot `raw_text` + blocks `text` read-back
6. **정렬 일관성**: in-memory(저장 순서) vs Mongo(`version_number` ASC)
7. **실구동 숫자 재계산**: reported "190 / 25 skip" 독립 재실행

## Methodology

### 0. 계약 읽기 전 스코핑

work_log/commit message가 "plan 01 §13 draft 조회·§30 draft_versions 계약"을 인용 → `grep -nE "^#{1,4} " docs/plans/01-core-sot.md`로 plan 01 전체 헤더 확인 → plan 01은 § 기호 미사용, 순차 마크다운 헤더. SoT `grep -nE`로 §13/§30 절 부재 확인. → canonical 범위를 SoT v1.4 §96–134 + plan 01 L50–95로 재설정(Subject Metadata에 명시).

### 1. 커밋 무결성 교차 증명

```bash
git show c43d945 --stat          # 10 files, +238/-4
git show c43d945                 # full diff
```

### 2. Boundary matrix (contract → 분기 → test trace)

get/list version 엔드포인트의 should-fire / should-NOT-fire 분기를 추출하고, 각 분기가 어느 test method에 매핑되는지 1:1 추적. 빈 칸 = finding.

### 3. 독립 재현 (본 세션에서 작성, `/tmp/repro_version.py`)

Mongo 없이도 service + API layer는 in-memory로 동작하므로, **회귀가 잠기지 않은 분기를 직접 구동**해 방어 존재 여부를 증명:

```bash
PYTHONPATH=. python3 /tmp/repro_version.py
```

재현 대상: (A) cross-project version read(service+API), (B) archived version read, (C) detail payload `idempotency_key` 비노출.

### 4. 테스트 독립 재실행 + 숫자 교차 검증

```bash
python3 -m unittest discover -s tests                    # reported 190/25 skip 재계산
python3 -m unittest tests.test_application_api -v        # 새 version test 3종 포함 12개
python3 -m unittest tests.test_core_sot_mongo -v         # mixin 25개 skip 출처 확인
```

## Findings

### Surface 1 — 커밋 무결성

`git show c43d945 --stat`: `models.py`(+7)·`mongo_repository.py`(+6)·`repository.py`(+2)·`service.py`(+33)·`main.py`(+56)·`test_application_api.py`(+71)·`test_core_sot_mongo.py`(+40)·docs 3개 = 10 files, +238/-4. 작업자 주장(엔드포인트 2종 + 지원 계층)과 일치. ✓

### Surface 2 — API 엔드포인트 + 404 매핑 (main.py)

| 엔드포인트 | 동작 | NotFound 매핑 |
|---|---|---|
| `GET .../versions` (main.py:124–132) | list, `version_number` 순, 빈 시 `{"versions": []}` | 404(project/draft 없음) |
| `GET .../versions/{version_id}` (main.py:134–167) | 단건 read-back(snapshot raw_text + blocks text) | 404(없음/cross-draft/cross-project) |

NotFound → 404 매핑이 기존 create/get_draft와 동일한 패턴(`HTTPException(status_code=404, ...)`). `Archived`는 read 경로에서 발생하지 않으므로 매핑 불필요(아래 Surface 4 참조). 상태 코드 일관. ✓

### Surface 3 — Boundary matrix (★ 핵심)

| # | 분기 (contract) | 기대 | 잠근 test | 상태 |
|---|---|---|---|---|
| 1 | list — 존재 draft (L92/L132 재조회) | 200, version_number 순 | `test_version_list_and_detail_read_back_saved_content` (test_application_api.py:131) | ✓ |
| 2 | detail — 존재 version (L92/L132) | 200, raw_text+blocks read-back | 동일 (:131) + `test_version_read_back_from_persisted_store` (test_core_sot_mongo.py:160) | ✓ |
| 3 | 없는 version_id | 404 | `test_get_missing_version_returns_404` (:164) + Mongo NotFound (:193) | ✓ |
| 4 | 없는 draft (list) | 404 | 동일 (:164, `missing_list`) | ✓ |
| 5 | cross-draft version (L93 격리) | 404 | `test_get_version_cross_draft_returns_404` (:181) | ✓ (draft_id 체크 service.py:209) |
| 6 | **cross-project version (L93 격리)** | **404** | **(없음)** | **★ Issue #1** |
| 7 | **archived project/draft version read (§115 read-allowed)** | **200** | **(없음)** | **★ Issue #2** |
| 8 | `idempotency_key` 미노출 — list | 키 부재 | `assertNotIn` (:155) | ✓ |
| 9 | `idempotency_key` 미노출 — detail | 키 부재 | **(assertion 없음)** | Issue #3 (사소) |
| 10 | 빈 draft version list | 200, `[]` | (명시 test 없음, 동작은 자명) | 사소 |

빈칸 3건(#6, #7, #9). #6은 명시적 계약 분기(L93 `project_id` 격리)이므로 **차단성**(Issue #1). #7·#9는 비차단 보강 후보. 아래 Issues 참조.

### Surface 4 — 독립 재현 결과 (`/tmp/repro_version.py`)

```
=== (A) cross-PROJECT version read — SERVICE layer ===
  OK: cross-project version read -> NotFound (defense present)
  (v_a.project_id = project-1 ; requested project = project-2)
=== (A2) cross-PROJECT version read — API layer ===
  cross-project version HTTP status: 404   (defense present at API: True)
=== (B) archived version read (should-fire) ===
  OK: archived version read returns detail (raw_text = 'text')
  -> behavior is should-fire under §115 read-allowed, but NO regression locks it
=== (C) detail payload idempotency_key non-exposure ===
  detail.draft_version keys: ['draft_id','id','project_id','snapshot_id','version_number']  (idempotency_key 없음)
  idempotency_key in detail.draft_version: False
```

즉: **코드는 정확하다.** cross-project 방어(service.py:208 `version.project_id != project_id` → NotFound, API 404)와 archive read-allowed(동작), detail `idempotency_key` 비노출 모두 독립 재현으로 확인됨. 문제는 이 분기들이 **회귀 test로 잠기지 않았다는 것**이다.

### Surface 5 — 정렬 일관성

- in-memory `list_versions` (service.py:95–99): `_version_ids_by_draft` append 순서. save는 `version_count+1`로 `version_number` 단조 증가 + idempotent replay는 append 안 함 → 저장 순서 == version_number 순. ✓
- Mongo `list_versions` (mongo_repository.py:147–151): `find({"draft_id": ...}).sort("version_number", ASCENDING)`. draft_id filter 후 정렬이므로 타 draft와 `version_number` 충돌 없음. ✓
- 양 경로 test로 lock(:131 list 순서, :160 Mongo 순서). 선행 `project_draft_list_get_api` 검증이 다룬 정렬 이슈(in-memory 삽입 순 vs Mongo `_id` ASC)와 동일 구조. 일관. ✓

### Surface 6 — content_hash 독립 재계산

`test_version_read_back_from_persisted_store` (test_core_sot_mongo.py:189): `detail.snapshot.content_hash == content_hash(raw_text)` — fixture hash가 아닌 원문 재계산으로 비교. ✓ (단 saved2("second")에 대한 detail read-back는 생략 — 사소)

### Surface 7 — 테스트 숫자 재계산

```
python3 -m unittest discover -s tests   →  Ran 190 tests ... OK (skipped=25)
```

reported "190 / 25 skip"과 정확 일치. 25 skip의 출처: `test_core_sot_mongo`의 `FallbackMongoTest`(mixin 12 + 자체 2) + `TransactionMongoTest`(mixin 12 + 자체 1) = 25, 모두 "no MongoDB reachable"/"needs a replica set"로 skip. ✓

## Issues / Risks

### Issue #1 (차단성 — cross-project version 격리 회귀 부재)

- **현상**: `get_draft_version`의 `version.project_id != project_id` 분기(service.py:208)를 잠그는 회귀 test가 없다.
- **증명**: `test_get_version_cross_draft_returns_404`(test_application_api.py:181)는 **project가 같고 draft만 다른** 케이스 → `version.draft_id != draft_id`(service.py:209)만 발동. cross-project(project만 다른) 시나리오에서만 발동하는 `version.project_id != project_id` 분기는 cross-draft test에서 절대 닿지 않는다.
- **독립 재현**: 본 세션 `/tmp/repro_version.py` (A)/(A2)로 cross-project version read가 service `NotFound`·API 404로 막히는 것을 증명 → **방어는 존재, 버그는 아님.**
- **왜 차단성인가**: CLAUDE.md "An untraced branch is a blocking finding regardless of the green bar" + 양방향 회귀 guard의 under-strict 방향 부재. 누군가 service.py:208의 `version.project_id != project_id` 절을 실수로 빼면 cross-project version이 노출되는데 현재 test suite로는 잡을 수 없다. `project_id` 격리는 plan 01 L93 + SoT의 명시적 MVP 계약.
- **권장**: `test_get_version_cross_project_returns_404` 추가 — 서로 다른 project/draft에 version_a를 저장 후 `GET /projects/{pb}/drafts/{db}/versions/{v_a}`가 404인지 단언. 본 세션 재현 스크립트가 그대로 뼈대.

### Issue #2 (비차단 — archived version read 회귀 부재)

- **현상**: §115 보존 + 선행 `project_draft_list_get_api` 검증이 확립한 read-allowed가 version read에도 적용되어야 하나, archived project/draft의 version read(list·detail)를 잠근 test가 없다.
- **독립 재현**: (B)에서 `archive_project` 후 `get_draft_version`이 정상 detail을 반환(raw_text='text') → should-fire 동작 확인.
- **왜 비차단인가**: §115는 "보존"을 명시하되 read 표면에 대한 "허용"은 침묵. 다만 동일 repo의 project/draft list/get은 archived read-allowed를 명시적 회귀로 잠갔으므로(`test_archived_project_and_draft_remain_listable_and_gettable` test_application_api.py:202), 일관성 차원에서 version read도 같은 over-strict guard가 있어야 한다(누군가 version read 경로에 archived 차단을 추가하면 정상 케이스가 깨짐).
- **권장**: archived 후 `GET .../versions` 및 `GET .../versions/{id}`가 200인지 lock.

### Issue #3 (사소 — detail payload `idempotency_key` assertion 부재)

- **현상**: list payload는 `assertNotIn("idempotency_key", listed[0])`(test_application_api.py:155)로 잠갔으나, detail의 `draft_version` 필드에 대한 동일 assertion이 없다.
- **독립 재현**: (C)에서 detail payload에 `idempotency_key` 부재 확인 → 동작은 정확. 두 표면이 같은 `_version_meta_payload`(main.py:80–89)를 공유하므로 실제 회귀 위험은 낮다.
- **권장**: detail body에도 `assertNotIn` 추가(1줄).

### Risk R1 (사소 — `assert snapshot is not None`)

`get_draft_version`(service.py:213)이 `assert snapshot is not None`로 snapshot 부재 시 `AssertionError`→500을 낸다. save 원자성(in-memory / Mongo transaction / fallback ordered write)으로 snapshot은 항상 존재해야 하므로 합리적 invariant이며, `_save_result`(service.py:339)도 동일 패턴으로 일관. over-handling 영역이므로 비차단. 단 Mongo fallback 부분 실패 시나리오는 선행 `mongo_adapter` 검증이 잠갔음.

### Risk R2 (문서 품질 — 계약 인용 부정확)

work_log·commit message·HANDOFF가 "plan 01 §13 draft 조회·§30 draft_versions 계약"을 인용하나, plan 01은 § 기호를 쓰지 않고 SoT에도 §13/§30 절이 없다. 코드에 영향은 없으나, 미래 verifier가 잘못된 anchor를 찾게 된다. 본 검증은 canonical을 SoT v1.4 §96–134 + plan 01 L50–95로 교정해 기록. (Slice 1 결정이 정본 계약을 바꾸지 않는 한 SoT 버전은 갱신 불필요 — 본 변경은 SoT 계약 변경 없음.)

## Verdict

**조건부 합격**.

- load-bearing 긍정: 커밋 무결성 정확, 엔드포인트/404 매핑 일관, 정렬 일관성(in-memory vs Mongo) 양 경로 lock, content_hash 독립 재계산, reported 190/25 skip 독립 재계산 일치, 방어 코드는 독립 재현으로 모두 동작 확인.
- load-bearing 조건: **Issue #1(cross-project version 격리 회귀 부재) 해소 필요**. CLAUDE.md "untraced branch is a blocking finding regardless of the green bar"에 따라, 명시적 `project_id` 격리 계약 분기(plan 01 L93)가 회귀로 잠기지 않은 상태로는 무조건 합격을 줄 수 없다. `test_get_version_cross_project_returns_404` 추가 시 합격.
- 비차단: Issue #2(archived read)/Issue #3(detail idempotency_key assertion)/Risk R1/R2는 보강 후보이지만 verdict를 갈라놓지 않는다.

## Outstanding items

- Issue #1 회귀 test 추가 여부는 사용자 결정(검증자는 코드를 고치지 않음). 본 세션 `/tmp/repro_version.py`가 test 뼈대를 제공.
- Mongo replica set 경로(25 skip)는 본 세션에서 미연결 — service/API layer는 in-memory로 독립 재현 완료, Mongo `list_versions` 정렬·`_to_version` round-trip은 코드 + mixin test(test_core_sot_mongo.py:160)로 정적 검증. live Mongo 검증은 환경이 허락할 때 `CORE_SOT_TEST_MONGO_URI=...`로 보강 가능.
- 후속 후보(사용자에게 이미 제시됨): plan 01 #7 fixture / rename API / gateway compose 편입 — 본 검증과 무관.

## Reproduction

```bash
# 1. 전체 숫자 재계산
python3 -m unittest discover -s tests                    # 190, 25 skip

# 2. 새 version 회귀 focused
python3 -m unittest tests.test_application_api -v        # 12 pass
python3 -m unittest tests.test_core_sot_mongo -v         # 25 skip (no Mongo)

# 3. 차단성 분기 독립 재현 (cross-project / archived / detail payload)
PYTHONPATH=. python3 /tmp/repro_version.py               # 본 검증이 작성한 스크립트
```
