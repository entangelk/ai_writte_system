# W3 증분 1 ordered unit 독립 검증

## Subject metadata

- **날짜**: 2026-07-19
- **요청자**: 오너 (commit `56a73a3` 결과에 대해 "검증하고 의심하고 또 의심해줄래?" 요청)
- **검증자**: 독립 AI worker (회의적·적대적 검증, 임의 수정 금지 범위)
- **검증 대상 slice/artifact**: Writing Workspace V2 W3 증분 1 — Draft `unit_kind`/`position`, full-permutation reorder, legacy migration
- **canonical spec reference**:
  - `docs/plans/writing-workspace-v2-w0-contract.md` §2 (ordered unit과 migration), §4 OU-01~14 named matrix
  - `schemas/writing-workspace-v2-w0.schema.json` `$defs/draftV2`, `draftOrderPutRequest`, `draftOrderPutResponse`, `unitKind`
  - `docs/system-contract-sot.md` v1.7.14 (W3 증분 1 row), v1.4 single-writer fallback 조항 (line 239, 426)
- **검증 대상 work source**: commit `56a73a3` ("feat: add W3 ordered draft units"), branch `main`, working tree clean

## Scope

본 검증은 W0 §2 + OU-01~14 named matrix가 govern하는 표면만 다룬다. WI(Writing Intent)와 SC-01/02의 OU fragment regression은 W3 다음 증분/closure로 명시적으로 예약된 영역으로, outstanding item으로만 다루고 contract 판정에 넣지 않는다.

1. **Spec contract**: W0 §2 prose(§2.1 Draft 확장, §2.2 reorder API, §2.3 migration)와 schema `$defs`의 내부 일관성, 그리고 OU boundary matrix(14행)의 완결성.
2. **구현 코드**: `core_sot/models.py`, `repository.py`, `mongo_repository.py`, `service.py`, `main.py`, `ordered_unit_migration.py`, `scripts/migrate_ordered_units.py`.
3. **OU 회귀 test**: `tests/test_ordered_units.py` (OU-01~14), `tests/test_core_sot_mongo.py` (live Mongo OU 회귀 3건 포함), `tests/test_core_sot_mongo_indexes.py`.
4. **HTTP envelope / public schema**: `CreateDraftRequest`, `DraftPayload`, `DraftOrderPutRequest`/`Response` Pydantic 모델과 generated OpenAPI의 OU fragment.
5. **Frontend**: `frontend/src/drafts/DraftList.tsx`, `DraftList.test.tsx` (단위 선택·position 표시·재정렬).
6. **전체 회귀 수치**: backend full, live Mongo, frontend, `gen:api` + `build`.

## Methodology

계약을 먼저 scope하고 boundary matrix를 구축한 뒤 코드를 읽었다(코드를 먼저 읽고 계약을 역추론하지 않음). 모든 수치와 동작 주장은 피감사 worker의 보고를 믿지 않고 독립 재도출했다.

- **계약 정독**: W0 §2(1~203행) 전문 정독, schema 파일 전체, SoT v1.7.14/v1.4 관련 조항.
- **boundary matrix**: OU-01~14 14행의 direction(fire/not-fire)·branch·literal을 lock list로 추출.
- **코드 정적 검증**: 각 OU 행이 가리키는 test node가 `tests/test_ordered_units.py`에 canonical 이름 그대로 존재하는지, assertion이 under-strict(버그 재주입 시 재실패)와 over-strict(정상 케이스 오탐) 양방향을 모두 잠그는지, public surface를 target하는지.
- **실제 동작 재현**: reorder invalid case의 HTTP status code를 `httpx.ASGITransport`로 직접 주입 재현 (`missing`, `duplicate`, `foreign`, `unknown`, `archived_project`).
- **OpenAPI ↔ catalog 대조**: `create_app().openapi()`의 OU fragment(`DraftPayload`, `CreateDraftRequest`, `DraftOrderPutRequest`/`Response`, `UnitKind`)를 schema `$defs`와 필드 단위로 비교 (SC-01/02가 OU를 다루지 않으므로 검증자가 직접 수행).
- **회귀 재실행 명령**:
  - `python3 -m pytest tests/test_ordered_units.py tests/test_core_sot_mongo_indexes.py -q -p no:cacheprovider`
  - `python3 -m pytest tests/test_ordered_units.py -v -p no:cacheprovider`
  - `python3 -m pytest tests/test_core_sot_mongo.py -q -p no:cacheprovider`
  - `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider`
  - `cd frontend && npm test -- --run`
  - `cd frontend && npm run gen:api && npm run build`
  - `python3 -c "...reorder invalid-case status code 재현..."` (본 기록 Reproduction 절에 전체 인라인)
- **sandbox 제약**: localhost Mongo socket이 sandbox에서 차단되어 `test_core_sot_mongo.py` 37개가 skip됨. 이는 W2 검증(`w2_operational_closure.md`)과 동일한 환경 패턴이며 false-positive가 아님. 코드와 test node 자체는 정적 검증으로 cover.

## Findings

### 1. Spec contract (W0 §2 + schema 내부 일관성)

W0 §2 prose와 schema `$defs`를 정독한 결과, OU 본 계약 자체는 내부 일관적이고 명확하다.

- §2.1: `unit_kind` enum `chapter|scene|other`, `position` integer `>=1`, archived 포함 project-wide contiguous `1..N`, list position ascending, archive slot 보존, create default `other`/`N+1`. schema `$defs/draftV2`(line 102-114), `$defs/unitKind`(line 19-21)과 literal 단위로 일치.
- §2.3 migration: repository list 순서(Mongo `_id` ASC, in-memory 삽입 순서) → `other`/`1..N`, archived 포함, fail-closed(mixed/unknown/duplicate/gapped), 전체 성공 시에만 `(project_id,position)` unique index 설치, non-transaction fallback single-writer before-image 복구. SoT v1.4(line 239) single-writer 제한과 일치.
- **OU boundary matrix 14행**: 모든 행이 `direction`/`branch`/`required named regression`을 갖추고 있으며, empty cell 없음.

**Cross-check the contract against itself — 1건 inconsistency 발견 (Blocking)**: §2.2와 schema `$defs/draftOrderPutRequest`가 duplicate `ordered_draft_ids`의 status code authority에 대해 충돌한다. 상세는 아래 Issues/Blocking 절.

### 2. OU 회귀 test (`tests/test_ordered_units.py`) — OU-01~14 boundary matrix 채움

14개 test node가 W0 §4의 canonical 이름 그대로 존재하며, 모두 PASS. 각 행의 assertion이 contract를 실제로 pin하는지 양방향 검증한 결과:

| ID | direction | test node (canonical 이름 그대로) | assertion이 contract를 pin? | 비고 |
|---|---|---|---|---|
| OU-01 | fire | `OrderedUnitMigrationTest::test_legacy_drafts_migrate_in_repository_order` | ✅ under-strict | order 보존 + kind/position + archived 포함 단정 |
| OU-02 | not-fire | `test_valid_project_rerun_is_noop` | ✅ over-strict | `drafts.values()` byte-for-byte 동등 + `metadata_writes` 불변 |
| OU-03 | fire | `test_invalid_partial_state_fails_without_write` | ✅ under-strict | mixed/duplicate/gapped/unknown 4 case 모두 + write 0 + index 미설치 |
| OU-04 | not-fire | `test_migration_preserves_existing_draft_artifacts` | ✅ over-strict | versions/snapshots/blocks/raw_text 동등 (id는 OU-01에서 간접 검증) |
| OU-05 | fire | `OrderedUnitContractTest::test_create_appends_ordered_unit` | ✅ under-strict | requested/default kind + N+1 + invalid kind `InvalidDraftOrder` |
| OU-06 | not-fire | `OrderedUnitApiTest::test_invalid_unit_metadata_rejected` | ✅ over-strict | bool/zero/unknown kind + client `position` 422 + write 0 |
| OU-07 | fire | `test_full_permutation_reorders_atomically` | ✅ under-strict | full permutation exact `1..N` + `metadata_writes==1` (single write 원자성) |
| OU-08 | not-fire | `test_invalid_permutation_rejected_without_write` | ⚠️ **느슨한 pin** | `assertIn(response.status_code, (409, 422))` — duplicate case의 422를 허용하여 §2.2 literal "409"를 잠그지 못함 (상세 Issues/Blocking) |
| OU-09 | not-fire | `test_same_permutation_is_naturally_idempotent` | ✅ over-strict | same-order `result == drafts` + `metadata_writes==0` |
| OU-10 | not-fire | `test_archive_preserves_total_order` | ✅ over-strict | archive 후 position `[1,2]` 보존 + listed 순서 |
| OU-11 | not-fire | `test_archived_project_reorder_rejected_without_write` | ✅ over-strict | archived project 409 + `metadata_writes==0` |
| OU-12 | not-fire | `test_missing_project_reorder_returns_not_found` | ✅ over-strict | missing project 404 분리 + `metadata_writes==0` |
| OU-13 | fire | `test_nontransaction_fallback_failure_leaves_no_partial_order` | ✅ under-strict | mid-write failure(`fail_after_metadata_write=2`) → before-image 복구 + index 미설치 |
| OU-14 | not-fire | `test_nontransaction_fallback_success_commits_exact_order` | ✅ over-strict | 정상 fallback `metadata_writes==1` + exact `[1,2,3]` (과잉 rollback 없음) |

test code는 auditor가 아니라 audit subject로 읽었다. OU-08을 제외한 13행은 assertion이 (a) contract를 직접 pin하고, (b) under-strict/over-strict 양방향 guard를 가지며, (c) public surface(`list_drafts`, `metadata_writes`, HTTP status)를 target한다. `CountingRepository` failure-injection seam(`fail_after_metadata_write`, `fail_with_set_change`)이 OU-08/13의 동시성/중간실패 회귀를 실제 동작으로 검증한다.

### 3. 구현 코드 ↔ spec literal 일치

- `models.py:20-23` `UnitKind` StrEnum = `chapter|scene|other` (schema `$defs/unitKind` exact 일치).
- `models.py:60-61` `Draft.unit_kind: UnitKind | None`, `position: int | None` — migration 동안에만 `None` 허용, runtime에는 항상 채워짐 (주석 명시).
- `service.py:282-304` `create_draft`: `isinstance(unit_kind, UnitKind)` guard, position = `len(drafts)+1` (N+1), default `UnitKind.OTHER`. §2.1 일치.
- `service.py:183-189`(in-memory) / `mongo_repository.py:210-215`(Mongo) `list_drafts`: position이 모두 채워진 경우에 한해 position ascending 정렬. §2.1 일치.
- `service.py:415-444` `reorder_drafts`: 길이/duplicate/set 불일치 → `InvalidDraftOrder`; 같은 순서 → return current(write 0); `replace_draft_metadata` 후 committed 재조회로 동시성 guard. §2.2 일치.
- `service.py:191-207`(in-memory) / `mongo_repository.py:217-233`(Mongo) `replace_draft_metadata`: in-memory는 dict before-image 복구, Mongo는 transaction path 또는 non-transaction before-image(`find` snapshot → `delete_many`+`insert_many(before)`). §2.3 조항 6 일치.
- `mongo_repository.py:244-251` negative position trick: full permutation 교체 시 `(project_id,position)` unique index 충돌을 피하기 위해 먼저 `-1..-N`으로 이동 후 `1..N`으로 확정. transaction 내에서 외부에 음수 position이 관찰되지 않음.
- `mongo_repository.py:270-280` `ensure_draft_position_index`: `(project_id,position)` unique index 설치. §2.3 조항 4 일치.
- `ordered_unit_migration.py:63-84` `_plan_project`: `all(missing)` → migrate, `any(missing)`/unknown kind/duplicate/gapped → `ValueError`(fail-closed), 모두 valid → `None`(no-op). §2.3 조항 5 exact 일치.
- `ordered_unit_migration.py:52-55` `run()`: `if not failures`일 때만 `ensure_draft_position_index`. 한 project 실패 시 index 미설치. §2.3 조항 4 일치.
- `main.py:1796-1812` `put_draft_order`: `NotFound`→404, `(Archived, InvalidDraftOrder)`→409. §2.2 "archived 409, missing 404" 일치.

**Spec-silent-but-enforced 탐지**: 별도 발견 없음. 구현이 contract가 명시하지 않은 boundary를 임의로 열거나 닫지 않는다(아래 Blocking은 contract가 *명시한* literal과 코드가 충돌하는 사례로, 방향이 다름).

### 4. OpenAPI ↔ schema catalog (SC-01/02 정신)

SC-01/02 regression(`tests/test_project_brief.py:283` `WorkspaceW0SchemaIntegrationTest`)은 ProjectBrief fragment만 검증하고 OU fragment를 다루지 않는다(→ Outstanding). 검증자가 직접 `create_app().openapi()`를 dump하여 catalog와 대조:

- `DraftPayload.required` == catalog `draftV2.required` (`archived,id,position,project_id,title,unit_kind`) ✅
- `DraftPayload.position` = `{type:integer, minimum:1}` (catalog와 동형, `title`은 FastAPI 자동 부여로 무해) ✅
- `UnitKind` component enum = `['chapter','scene','other']` ✅
- `CreateDraftRequest.required = ['title']`, `unit_kind` default `'other'`, `additionalProperties=False` (§2.1 생략 시 other + client position reject 근거) ✅
- `DraftOrderPutRequest.required` == catalog, `uniqueItems=True` (catalog와 일치 — 이 값이 duplicate→422의 근원, Issues/Blocking 참조) ✅동형
- `DraftOrderPutResponse.required = ['drafts']`, `additionalProperties=False` (catalog 일치) ✅
- catalog root(`writing-workspace-v2-w0.schema.json`)를 endpoint schema가 참조하지 않음 (SC-02 정신 만족) ✅

fragment 자체는 현재 catalog와 동형이다. 다만 OU fragment를 잠그는 regression이 없으므로 미래 drift가 감지되지 않는다(→ Hardening H1).

### 5. 회귀 수치 독립 재도출

| 항목 | 피감사 주장 | 검증자 독립 재도출 | 일치 |
|---|---|---|---|
| OU named + index focused | 111 passed / 27 subtests (work_log) | `test_ordered_units.py` 14 passed / 12 subtests + `test_core_sot_mongo_indexes.py` 3 passed = **17 passed / 12 subtests** | ✅ (work_log의 111은 adjacent Core/API focused 포함 폭넓은 실행; OU 자체는 14+12로 정확) |
| `test_ordered_units.py` | (명시 없음) | **14 passed, 12 subtests** — OU-01~14 전부 존재·PASS | ✅ |
| backend full | 1159 passed / 60 skipped / 293 subtests | **1159 passed / 56 skipped / 293 subtests** | ✅ passed·subtests 정확 일치; skipped 60→56은 live Mongo 가용성에 따른 환경 변동(false-positive 아님) |
| live replica-set Mongo | 37 passed / 0 skipped | sandbox 차단으로 **37 skipped** | ⚠️ 환경 제약으로 재현 불가. 코드·test node는 정적 검증 cover(Outstanding) |
| frontend | 144 passed / 10 files | **144 passed / 10 files** | ✅ 정확 일치 |
| `gen:api && build` | 96 modules; CSS 17.81 kB(gzip 4.00), JS 285.37 kB(gzip 88.19) | **96 modules; CSS 17.81 kB(gzip 4.00), JS 285.37 kB(gzip 88.19)** | ✅ byte-level 일치 |
| working tree | clean | `git status --short` 빈 출력, `git diff --check` OK | ✅ |

수치 주장은 passed/subtests/build byte에서 전부 일치한다. 유일한 환경 의존 항목은 live Mongo(sandbox에서 재현 불가)이며, W2 closure 기록과 동일한 환경 패턴이다.

## Issues / Risks

### Blocking (contract obligations)

**B1 — duplicate `ordered_draft_ids` 의 status code authority가 §2.2 prose와 충돌**

- **현상**: reorder API에 중복 draft id를 보내면 **422**(Pydantic `DraftOrderPutRequest.reject_duplicate_draft_ids` field_validator, `main.py:1110-1115`)가 반환된다. 누락/foreign/unknown id는 **409**(`InvalidDraftOrder` → `main.py:1810-1811`)이다.
- **직접 재현**(본 기록 Reproduction 절): `duplicate → 422`, `missing/foreign/unknown/archived → 409`.
- **contract 위반**: W0 §2.2(line 75)는 "누락, **중복**, foreign/unknown id, 요청 평가 중 Draft 집합 변경은 **409**이며 write 0건이다"라고 명시. duplicate에 대해 prose는 409, schema `$defs/draftOrderPutRequest`(line 122)는 `uniqueItems:true`이고 Pydantic validator는 이를 422로 반환.
- **contract 내부 충돌**: §2.2 prose(409) ↔ schema `uniqueItems`(422 경로). 이것은 "Cross-check the contract against itself — internal contract inconsistency is a **blocking** finding"에 해당.
- **test가 이것을 숨김**: `tests/test_ordered_units.py:299` `assertIn(response.status_code, (409, 422))`가 duplicate case의 422를 허용한다. 즉 OU-08 행은 test node가 존재하지만 contract-required literal "409"를 pin하지 못한다(under-strict guard의 정밀도 결손). "write 0"은 단정하지만 status code는 단정하지 않는다.
- **주의**: W0 §1.1(line 42)은 ProjectBrief `constraints`에 대해 "uniqueItems는 raw array 중복만 표현... 422 authority는 HTTP validator"라고 명시하며, 이 패턴을 ordered_draft_ids에까지 확대 해석하면 422가 일관적일 수 있다. 그러나 §2.2는 ordered_draft_ids에 대해 **명시적으로** 409를 요구하므로, §1.1 주석이 자동으로 §2.2를 override하지 않는다. 이것은 owner decision이 필요한 genuine fork이다:
  - (a) §2.2 prose literal을 고집 → `DraftOrderPutRequest`에서 `reject_duplicate_draft_ids` field_validator를 제거/완화하고 service `reorder_drafts`의 duplicate 검사(`len(set(...)) != len(...)`)로 409를 내도록 변경 + OU-08 assertion을 `assertEqual(..., 409)`로 강화.
  - (b) §1.1 constraints 패턴으로 통일 → §2.2 prose를 amend하여 duplicate의 422 authority를 명시 + schema에 주석 추가 + OU-08 assertion에서 422를 정당화하는 분기 명시.
  - 어느 쪽이든 **matching regression으로 literal을 잠가야** empty cell이 닫힌다.
- **판정 영향**: contract-required literal(OU-08 duplicate→409)이 현재 unlocked이므로 본 slice는 합격이 아닌 **조건부 합격**이다. 조건은 위 (a) 또는 (b) 중 하나로 duplicate status code authority를 owner가 확정하고 matching regression을 추가하는 것.

### Hardening recommendations (non-blocking, contract 초과)

- **H1 — SC-01/02 regression이 OU fragment를 다루지 않음**: `WorkspaceW0SchemaIntegrationTest`(`tests/test_project_brief.py:283`)는 ProjectBrief fragment만 검증한다. W0 §4의 SC-01/02는 "W2/**W3** OpenAPI가 각 exact `$defs`와 동형 schema 노출"을 요구하므로, OU fragment(`draftV2`, `draftOrderPutRequest`/`Response`, `CreateDraftRequest`)에 대한 fragment 동형 regression과 catalog-root 미참조 regression이 W3 closure 시점에 필요하다. 현재 fragment는 catalog와 동형임을 검증자가 직접 확인했으나(§4), regression이 없으면 미래 drift가 감지되지 않는다. SoT v1.7.14에 "WI 완료 뒤 ... SC-01/02로 다시 대조하고 W3 전체 closure"로 명시적으로 연기되어 있으므로 이번 증분의 결함은 아니나, W3 다음 증분에서 반드시 닫아야 한다.
- **H2 — `DraftList.tsx` position 표시와 visible ordinal 구분**: `frontend/src/drafts/DraftList.tsx:188`이 canonical `draft.position`을 그대로 표시한다. W0 §2.1(line 21)은 "visible ordinal과 canonical position을 구분"하라고 하나, 현재 UI는 archived draft를 목록에서 숨기지 않아 canonical position = visible ordinal이 되고 번호가 건너뛰지 않는다(정신은 만족). 그러나 (i) line 21이 글자 그대로 요구하는 "구분"이 구현되지 않았고, (ii) `DraftList.test.tsx` 일부 fixture(line 45-46, 86, 145)가 `unit_kind`/`position` 없이 작성되어 line 188의 position 렌더링이 해당 test에서 검증되지 않는다. archived filtering 도입 시 canonical position이 노출될 잠재 위험이 있으므로, visible ordinal 매핑 또는 fixture 정비를 후속 보강 후보로 기록한다. W3 다음 증분(WI)에서 editor workspace가 단위를 본격 소비할 때 함께 정비하는 것이 자연스럽다.
- **H3 — OU-04 id 보존 명시적 assertion 누락**: `test_migration_preserves_existing_draft_artifacts`는 versions/snapshots/blocks/raw_text 보존을 단정하지만 draft `id` 보존을 명시적으로 assert하지 않는다. OU-01에서 id 순서 보존이 간접 검증되므로 현재 빈칸은 아니나, id 보존을 OU-04에 한 줄 추가하면 migration이 id 재발급을 하지 않음을 직접 잠글 수 있다.

## Verdict

**조건부 합격 (Conditional Pass)**

- **근거**: OU-01~14 boundary matrix 14행 중 13행이 under-strict/over-strict 양방향 guard로 contract를 정확히 pin하고 있고, 구현 코드가 W0 §2 literal과 필드 단위로 일치하며, 회귀 수치(1159 passed / 293 subtests, frontend 144/10, build byte)가 피감사 주장과 독립 재도출 결과 일치한다. migration fail-closed/원자성/before-image 복구, unique index 조건부 설치, transaction path 모두 계약대로 구현됐다.
- **유일한 차단 조건 (B1)**: duplicate `ordered_draft_ids`의 status code가 §2.2 prose literal "409"가 아닌 422로 반환되며, OU-08 test가 이것을 `(409, 422)`로 허용해 contract-required literal을 pin하지 못한다. 이것은 spec 내부(prose↔schema) 불일치이자 spec↔code mismatch로, owner decision으로 authority를 확정하고 matching regression을 추가하기 전까지 contract-required literal이 unlocked 상태다.
- **합격 전환 조건**: B1의 (a) code를 409로 통일하거나 (b) §2.2/schema를 amend하여 422를 명시하는 것 중 하나를 owner가 선택하고, 그 선택을 잠그는 regression(OU-08의 duplicate assertion을 literal로 강화)을 추가할 것.

## Outstanding items (운영 상태, 결함 아님)

- **live Mongo 37 passed**: sandbox가 localhost Mongo socket을 차단하여 이 환경에서 `test_core_sot_mongo.py` 37개가 skip된다. 피감사 worker는 권한 있는 머신에서 37 passed/0 skipped를 확보했다고 보고했으며(W2 closure와 동일 패턴). 코드(`mongo_repository.py`)와 test node(OU-13/14 fallback, archived-inclusive live reorder, index 설치)는 정적 검증으로 cover했으므로, 권한 있는 Mongo 머신에서 `tests/test_core_sot_mongo.py` 전체(특히 `test_ordered_unit_migration_fallback_restores_raw_before_image`, `test_ordered_unit_migration_fallback_commits_and_installs_index`, `test_ordered_unit_fields_and_full_reorder_persist`)가 0 skip으로 통과하는지 최종 확인이 필요하다.
- **W3 미완료 (scope 예약)**: W0 §3의 `append_current|start_next_unit` Writing Intent WI-01~22, 그리고 SC-01/02의 OU fragment regression(H1)은 다음 증분/W3 전체 closure로 명시적으로 예약됨. SoT v1.7.14와 work_log 모두 "W3는 미완료"로 기록. 본 검증은 OU-01~14 증분에 한정한다.
- **working tree**: commit `56a73a3` 이후 clean, `git diff --check` OK. 외부 publish/push는 요청 범위 밖.

## Reproduction

```bash
# 1. OU named + index focused
python3 -m pytest tests/test_ordered_units.py tests/test_core_sot_mongo_indexes.py -q -p no:cacheprovider
# 기대: 17 passed, 12 subtests passed

# 2. OU matrix 개별 확인
python3 -m pytest tests/test_ordered_units.py -v -p no:cacheprovider
# 기대: OU-01~14 14 test 모두 PASSED (canonical 이름 그대로)

# 3. backend full (live Mongo 없는 환경)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
# 기대: 1159 passed, (live Mongo 가용 시 37 포함 passed / 불가 시 skipped), 293 subtests

# 4. live Mongo (권한 있는 replica-set 머신에서만)
CORE_SOT_TEST_MONGO_URI=mongodb://<replica-set> python3 -m pytest tests/test_core_sot_mongo.py -q -p no:cacheprovider
# 기대: 37 passed, 0 skipped

# 5. frontend
cd frontend && npm test -- --run   # 기대: 144 passed / 10 files
cd frontend && npm run gen:api && npm run build   # 기대: 96 modules, CSS 17.81/gzip 4.00, JS 285.37/gzip 88.19

# 6. B1 재현 — duplicate id status code (422) vs §2.2 literal(409)
python3 -c "
import asyncio, httpx
from services.application.app.core_sot.service import CoreSotService, InMemoryCoreSotRepository
from services.application.app.main import create_app
async def main():
    app = create_app(CoreSotService(InMemoryCoreSotRepository()))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as c:
        p = (await c.post('/projects', json={'name':'N'})).json(); pid = p['id']
        d1 = (await c.post(f'/projects/{pid}/drafts', json={'title':'One'})).json()
        d2 = (await c.post(f'/projects/{pid}/drafts', json={'title':'Two'})).json()
        for name, ids in [('missing',[d1['id']]), ('duplicate',[d1['id'],d1['id']]),
                          ('foreign',[d1['id'],'x']), ('unknown',[d1['id'],'no'])]:
            r = await c.put(f'/projects/{pid}/draft-order', json={'ordered_draft_ids': ids})
            print(f'{name:10s} -> {r.status_code}')
asyncio.run(main())
"
# 기대 출력: missing->409, duplicate->422(B1), foreign->409, unknown->409
# §2.2 literal은 duplicate도 409를 요구 → B1 위반 재현.
```
