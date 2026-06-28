# project/draft rename API 독립 검증 (CRUD "수정" 완성)

## Subject Metadata

- **날짜**: 2026-06-28
- **요청자**: 사용자 ("project/draft rename API 완료. 커밋 e34364b. … 다음 작업 검증해줘")
- **검증자**: Claude (본 세션)
- **대상 커밋**: `e34364b` — feat: add project/draft rename API (CRUD update)
- **정본 spec 참조** (work_log "plan 01 §13" 인용은 § 기호가 부정확 — plan 01은 §를 쓰지 않음. 아래가 실제 canonical):
  - `docs/plans/01-core-sot.md` **L13–14** "프로젝트/draft의 … 생성·조회·목록·**수정** …" (rename이 채우는 "수정")
  - `docs/system-contract-sot.md` **v1.4** §115 (archive → 보존), §116 (파생 인덱스 stale)
  - 선행 독립 검증 `docs/verifications/2026-06-28/project_draft_list_get_api.md`(read-allowed 해석), `version_read_api.md`(cross-project 격리 boundary 기준)
- **작업 출처**: committed (`e34364b`). `git status` clean.
- **검증 입장**: archived 차단 분기의 세분성(project archived vs draft archived의 교차 4셀)이 회귀로 잠겼는지, replace가 다른 필드를 보존하는지, archive=쓰기차단의 spec 근거가 있는지, reported 숫자가 재계산되는지를 증명.

## Scope

1. **커밋 무결성**: `e34364b`가 service/main/test/docs 모두 포함하는지
2. **API 엔드포인트 2종**: `main.py` `PATCH /projects/{id}`(name)·`PATCH /projects/{id}/drafts/{draft_id}`(title)
3. **archived 차단 boundary matrix (★ 핵심)**: project.archived × draft.archived 교차 4셀이 각각 명명 회귀에 매핑되는지
4. **격리**: missing → 404, cross-project draft → 404
5. **replace 필드 보존**: rename이 id/project_id/archived를 유지하는지(immutable dataclass)
6. **archive=쓰기차단의 spec 근거**: SoT가 명시하는가, 아니면 create/save 구현 패턴의 연장인가
7. **실구동 숫자 재계산**: reported "199 / 27 skip"

## Methodology

### 0. 계약 읽기 전 스코핑

`grep -nE "수정|archiv|삭제|rename" docs/plans/01-core-sot.md` → plan 01 L13–14 "수정" 명시. `grep -nE "archiv|쓰기|차단" docs/system-contract-sot.md` → §115 보존만, **archived 쓰기차단 clause 부재**(§116 stale, §265 "보관 정책 미확정"). canonical 범위를 plan 01 L13–14 + SoT v1.4 §115로 확정.

### 1. 커밋 무결성

```bash
git show e34364b --stat   # 7 files, +171/-3
git show e34364b
```

### 2. Boundary matrix (archived 교차 4셀 → 분기 → test trace)

rename_project/rename_draft의 archived 분기를 project×draft 교차로 전개하고, 각 셀이 어느 test에 매핑되는지 추적. 빈 칸 = finding.

### 3. 독립 재현 (본 세션 `/tmp/repro_rename.py`)

회귀가 잠기지 않은 분기를 직접 구동해 방어 존재 여부 증명(service + API layer, in-memory):

```bash
PYTHONPATH=. python3 /tmp/repro_rename.py
```

재현 대상: (A) project archived + draft active → rename_draft, (B) draft archived + project active → rename_project, (C) cross-project draft → 404, (D) replace 필드 보존.

### 4. 테스트 독립 재실행 + 숫자 교차 검증

```bash
python3 -m unittest discover -s tests                 # reported 199/27 skip 재계산
python3 -m unittest tests.test_application_api -v     # rename 회귀 4종
```

## Findings

### Surface 1 — 커밋 무결성

`git show e34364b --stat`: `service.py`(+19)·`main.py`(+36)·`test_application_api.py`(+79)·`test_core_sot_mongo.py`(+16)·docs 3개 = 7 files, +171/-3. 작업자 주장(엔드포인트 2종 + service rename 2종 + 회귀)과 일치. ✓

### Surface 2 — API 엔드포인트 + 상태코드 매핑 (main.py)

| 엔드포인트 | 동작 | 매핑 |
|---|---|---|
| `PATCH /projects/{id}` (main.py:116–128) | name 갱신 | NotFound→404, Archived→409 |
| `PATCH /projects/{id}/drafts/{draft_id}` (main.py:130–142) | title 갱신 | NotFound→404, Archived→409 |

`NotFound`→404 / `Archived`→409 매핑이 기존 `create_draft`/`save_draft`(main.py:177-178, 194-195의 Archived→409)과 동일 패턴. 상태 코드 일관. ✓

### Surface 3 — archived 차단 boundary matrix (★ 핵심)

rename의 archived 분기는 project×draft 교차 4셀로 전개된다:

| # | project 상태 | draft 상태 | rename_project 기대 | rename_draft 기대 | 잠근 test | 상태 |
|---|---|---|---|---|---|---|
| a | active | active | 200 | 200 | `test_rename_project_and_draft_persist_via_get` (:131) | ✓ |
| b | active | **archived** | **200** (draft 무관) | 409 (draft.archived 절 service.py:192-193) | draft→`test_rename_on_archived` :194→:201 ✓ / **project→(없음)** | **★ Issue #2** |
| c | **archived** | active | 409 (project.archived 절 service.py:181-182) | **409** (rename_draft의 project.archived 절 service.py:189-190) | project→`test_rename_on_archived` :203→:208 ✓ / **draft→(없음)** | **★ Issue #1** |
| d | archived | archived | 409 | 409 | (간접: a/b/c 조합) | 부분 |

`test_rename_on_archived_is_blocked_404`(test_application_api.py:187)는 두 경로만 지난다:
- `:194 archive_draft` → `:201 rename_draft`(draft.archived 절만 발동, project는 active)
- `:203 archive_project` → `:208 rename_project`(rename_project의 project.archived 절)

즉 **rename_draft의 `project.archived` 절(service.py:189-190)** 과 **rename_project의 draft 무관성 should-fire** 두 분기가 test에 닿지 않는다. 아래 Issues.

### Surface 4 — 독립 재현 결과 (`/tmp/repro_rename.py`)

```
=== (A) project archived + draft ACTIVE -> rename_draft ===
  OK: rename_draft -> Archived on archived project (defense present)
  -> this branch (service.py rename_draft project.archived line) is NOT locked by a test
=== (B) draft archived + project ACTIVE -> rename_project (should-fire) ===
  rename_project result: P-new (archived flag preserved: False)
  -> should-fire behavior (project rename independent of draft state), NOT locked by a test
=== (C) cross-project draft rename (sanity; already locked) ===
  cross-project rename HTTP: 404  (defense present: True)
=== (D) active rename preserves id/project_id/archived ===
  draft id preserved: True / project_id preserved: True / archived preserved: True
  project id preserved: True / archived preserved: True
```

방어는 모두 존재. (A)의 rename_draft `project.archived` 절과 (B)의 rename_project draft 무관성이 동작하지만 회귀로 잠기지 않음.

### Surface 5 — replace 필드 보존 (immutable dataclass)

(D)에서 active rename 후 `id`/`project_id`/`archived` 모두 보존 확인. `replace(project, name=name)` / `replace(draft, title=title)`는 지정 필드만 변경하고 나머지 유지 → snapshot/version과 무관하게 metadata만 갱신. round-trip test(:131)와 Mongo persist test(test_core_sot_mongo.py:160 `test_rename_persists_for_project_and_draft`)로 양 경로 lock. ✓

### Surface 6 — cross-project / missing 404

- `test_rename_cross_project_draft_returns_404`(:172): draft_a를 project_b 경로로 rename → `_require_draft`(service.py:354-357)의 `draft.project_id != project_id` → NotFound 404. ✓
- `test_rename_missing_returns_404`(:158): missing project/draft → 404. ✓

### Surface 7 — 테스트 숫자 재계산

```
python3 -m unittest discover -s tests   →  Ran 199 tests ... OK (skipped=27)
```

reported "199 / 27 skip"과 정확 일치. 27 skip = `test_core_sot_mongo` FallbackMongoTest + TransactionMongoTest mixin(이전 25 + rename mixin 1 method × 2 class = +2 = 27). ✓

### Surface 8 — 선행 version_read_api Issue #1 폐쇄 확인 (이번 검증 범위 외, 긍정)

`test_get_version_cross_project_returns_404`가 test_application_api.py에 추가됐고(본 세션 focused 출력에서 확인), HANDOFF에 "mutation 증명: 절 제거 시 FAIL로 양방향 lock"으로 기록됨 → 직전 검증의 차단성 finding이 회귀 추가로 깨끗이 폐쇄됨. 이번 rename 검증에도 동일한 양방향 기준을 적용.

## Issues / Risks

### Issue #1 (차단성 — rename_draft의 project.archived 절 lock 부재)

- **현상**: `rename_draft`(service.py:187-194)의 `project.archived` 절(service.py:189-190)이 project archived + draft active 상태의 rename_draft를 409로 막지만, 이를 lock하는 test가 없다.
- **증명**: `test_rename_on_archived_is_blocked_409`(:187)는 `:194 archive_draft`(draft만 archived) → `:201 rename_draft`(draft.archived 절 발동)와 `:203 archive_project` → `:208 rename_project`(rename_project의 project.archived 절)만 지난다. **`:203 archive_project` 후 rename_draft를 호출하지 않는다** → rename_draft의 project.archived 절은 어느 test에서도 닿지 않는다.
- **독립 재현**: `/tmp/repro_rename.py` (A)로 project archived + draft active → rename_draft가 `Archived`로 막히는 것을 증명 → **방어는 존재, 버그는 아님.**
- **왜 차단성인가**: project archived인데 draft를 rename할 수 있으면 archive=쓰기차단이 우회된다. CLAUDE.md "untraced branch is a blocking finding regardless of the green bar" + under-strict guard 부재. 누군가 service.py:189-190의 절을 빼면 regression이 생기는데 현재 test suite로는 잡을 수 없다.
- **권장**: `test_rename_on_archived`에 `:203 archive_project` 직후 `rename_draft`도 409인지 단언 추가(또는 별도 test). 본 세션 (A) 재현이 뼈대.

### Issue #2 (비차단 — rename_project의 draft 무관성 should-fire lock 부재)

- **현상**: rename_project는 project.archived만 보고 draft 상태와 무관 → "draft archived + project active → rename_project 200"이 작업자가 명시 주장한 동작이지만 lock된 test가 없다.
- **독립 재현**: (B)로 rename_project → 200, archived=False 보존 확인 → should-fire 동작 정확.
- **왜 비차단인가**: 이 분기는 코드에 "체크"가 존재하는 게 아니라 rename_project가 draft를 아예 보지 않는 구조적 특성이다. over-strict regression(rename_project에 draft 체크를 잘못 추가) 가능성은 낮다. 다만 작업자가 명시 주장한 동작이므로 boundary matrix 빈칸으로 기록.
- **권장**: `test_rename_on_archived`의 `:194 archive_draft` 직후 rename_project가 200인지(should-fire) 단언 추가.

### Risk R1 (비차단 — archive 쓰기차단은 spec-silent)

SoT §115는 archive 후 "보존"만 명시하고 archived entity에 대한 **쓰기 차단은 침묵**한다(§116 stale, §265 "보관 정책 미확정"). 따라서 create_draft·save_draft·rename_project·rename_draft의 archived→409 차단은 모두 **명시적 spec 근거가 없는 구현 패턴**이다. 작업자 주장 "spec-silent 신규 강제가 아님"은 **반쯤 정확**: create/save의 확립된 패턴을 따른 건 맞지만, 그 패턴 자체가 spec-silent다. 이건 rename만의 문제가 아니라 전체 Core SOT CRUD가 공유하므로 비차단. SoT에 "archived entity = read-only(쓰기차단)"를 명시 clause로 올리는 amendment를 권고(사용자 결정).

### Risk R2 (문서 — 계약 인용 부정확)

work_log·commit message가 "plan 01 §13 CRUD"를 인용하나, plan 01은 § 기호를 쓰지 않는다. "§13"은 plan 01 L13(프로젝트 CRUD 범위)을 느슨히 가리키는 것이라 직전 version_read 검증의 "§13/§30"만큼 심각하진 않으나 여전히 부정확. 본 검증은 canonical을 plan 01 L13–14 + SoT §115로 교정해 기록. SoT 계약 변경 없음(rename은 plan 01 "수정" 구현, archive 쓰기차단은 R1처럼 이미 확립된 패턴).

## Verdict

**조건부 합격**.

- load-bearing 긍정: 커밋 무결성 정확, 엔드포인트/상태코드 매핑(create/save와 일관), cross-project/missing 404 lock, replace 필드 보존(id/project_id/archived) 양 경로 round-trip lock, reported 199/27 skip 독립 재계산 일치, 방어 코드는 독립 재현으로 모두 동작 확인, 선행 version_read Issue #1 폐쇄 확인.
- load-bearing 조건: **Issue #1(rename_draft의 project.archived 절 lock 부재) 해소 필요**. 명시적 방어 라인(service.py:189-190)이 회귀로 잠기지 않아 under-strict guard 부재. CLAUDE.md 기준 무조건 합격 불가. lock 추가 시 합격.
- 비차단: Issue #2(rename_project draft 무관성 should-fire)/R1(archive 쓰기차단 spec-silent)/R2(인용 부정확)는 보강 후보이지만 verdict를 갈라놓지 않는다.

## Outstanding items

- Issue #1 회귀 추가 여부는 사용자 결정(검증자는 코드를 고치지 않음). `/tmp/repro_rename.py` (A)가 test 뼈대.
- Mongo replica set 경로(27 skip)는 본 세션 미연결 — service/API layer는 in-memory로 독립 재현 완료, Mongo rename persist는 코드 + mixin test(test_core_sot_mongo.py:160)로 정적 검증.
- 후속 후보(사용자에게 이미 제시됨): archive API endpoint(service-only → HTTP), gateway compose 편입, plan 01 #7 fixture(Phase 2 소비자 생길 때) — 본 검증과 무관.

## Reproduction

```bash
# 1. 전체 숫자 재계산
python3 -m unittest discover -s tests                 # 199, 27 skip

# 2. rename 회귀 focused
python3 -m unittest tests.test_application_api -v     # rename 4종 포함 12+ pass

# 3. 차단성 분기 독립 재현 (rename_draft project.archived / rename_project draft 무관성)
PYTHONPATH=. python3 /tmp/repro_rename.py             # 본 검증이 작성한 스크립트
```
