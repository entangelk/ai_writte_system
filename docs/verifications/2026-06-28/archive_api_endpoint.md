# archive (DELETE) API endpoint 독립 검증 (CRUD API 완성)

## Subject Metadata

- **날짜**: 2026-06-28
- **요청자**: 사용자 ("archive API endpoint 완료" — 커밋 해시는 본문에 없어 `git log 89f1f0a..HEAD`로 식별)
- **검증자**: Claude (본 세션)
- **대상 커밋**: `bc7d1bb` — feat: add archive (DELETE) API endpoints (CRUD complete)
- **정본 spec 참조**:
  - `docs/system-contract-sot.md` **v1.5 §115** — :116 "project/draft 삭제는 MVP에서 archive로 처리", :119 "본문 쓰기·메타 수정 차단… project archive는 그 하위 draft 쓰기까지 차단", :121 "archive/unarchive 같은 상태 전이는 본 쓰기 차단의 대상이 아니다"
  - `docs/plans/01-core-sot.md` L13 "프로젝트의 생성·조회·목록·수정·**보관/삭제**"(archive endpoint가 채우는 보관/삭제)
  - 선행 검증 `sot_v1_5_archive_readonly.md`(§115 해석 기준), `rename_api.md`(archived 차단 패턴)
- **작업 출처**: committed (`bc7d1bb`). `git status` clean.
- **검증 입장**: DELETE=archive 의미론이 §115 :116과 정합한가, 재archive idempotency가 lock됐는가, **archived project의 하위 draft archive** 분기(§115 :119 vs :121 해석)가 코드와 정합하고 회귀로 잠겼는지, CRUD API 완성 주장이 참인지.

## Scope

1. **커밋 무결성**: `bc7d1bb`가 main + test + docs 포함하는지
2. **DELETE=archive 의미론**: §115 :116 정합, REST DELETE idempotency
3. **boundary matrix**: DELETE project/draft → 200(archived), 읽기 허용, 이후 쓰기 409, 재archive idempotent, missing/cross-project 404
4. **★ archived project의 하위 draft archive**: §115 :119("하위 draft 쓰기 차단") vs :121("상태전이는 차단 아님") 해석 + 회귀 lock 여부
5. **idempotency lock 대칭성**: project 재archive는 lock, draft 재archive는?
6. **실구동 숫자 재계산**: reported "206 / 27 skip"

## Methodology

### 1. 커밋 식별 + 무결성

요청에 커밋 해시가 없어 `git log --oneline 89f1f0a..HEAD`로 `bc7d1bb` 식별. `git show bc7d1bb -- main.py` / `-- tests/test_application_api.py`로 코드/회귀 diff.

### 2. §115 :119 vs :121 해석 정밀 점검

`archive_draft`(service.py:347-352)가 `project.archived`를 체크하지 않는다는 것을 코드에서 확인 → archived project의 하위 draft archive가 허용되는지, 그것이 §115 :121(상태전이 예외)와 정합한지, :119("하위 draft 쓰기 차단")과 충돌하지 않는지를 prose 정밀 독해로 판정.

### 3. Boundary matrix → 분기 → test trace

DELETE 엔드포인트의 should-fire / should-NOT-fire 분기를 전개하고 각각 test에 매핑. 빈 칸 = finding.

### 4. 독립 재현 (`/tmp/repro_archive.py`)

```bash
PYTHONPATH=. python3 /tmp/repro_archive.py
```

회귀가 잠기지 않은 분기(archived project의 draft archive, draft 재archive, missing draft)를 직접 구동.

### 5. 테스트 독립 재실행 + 숫자 교차 검증

```bash
python3 -m unittest discover -s tests                 # reported 206/27 skip 재계산
python3 -m unittest tests.test_application_api -v     # archive 회귀 4종
```

## Findings

### Surface 1 — 커밋 무결성

`git show bc7d1bb --stat`: `main.py`(+18)·`test_application_api.py`(+85)·`system-contract-sot.md`(이전 검증 record 반영)·CHANGELOG·HANDOFF·work_log = 6 files, +321/-4. 작업자 주장(엔드포인트 2종 + 회귀 4종, SOT/계약 변경 없음)과 일치. ✓

### Surface 2 — DELETE 엔드포인트 + 상태코드 매핑 (main.py)

| 엔드포인트 | 동작 | 매핑 |
|---|---|---|
| `DELETE /projects/{id}` (main.py:144-152) | archive_project → 200(`_project_payload`, archived=true) | NotFound→404 |
| `DELETE /projects/{id}/drafts/{draft_id}` (main.py:154-161) | archive_draft → 200(`_draft_payload`, archived=true) | NotFound→404 |

`Archived`→409 매핑이 **불필요**하다 — `archive_project`/`archive_draft`는 archived 검사 없이 `replace(archived=True)`만 수행(service.py:341-352)하므로 `Archived`를 raise하지 않는다. NotFound→404만 매핑. 다른 엔드포인트(create/save/rename)와 매핑이 일관하되, archive 경로는 쓰기차단 대상이 아니므로 409가 없는 게 정합. ✓

### Surface 3 — DELETE=archive 의미론

§115 :116 "project/draft 삭제는 MVP에서 archive로 처리한다"에 DELETE를 archive로 매핑. soft delete(hard delete 아님), SOT 본문 보존. HTTP DELETE의 idempotency(같은 요청 = 같은 결과)를 재archive 200으로 충족 — REST 의미론 정합. ✓

### Surface 4 — Boundary matrix (★ 핵심)

| # | 분기 | 기대 | 잠근 test | 상태 |
|---|---|---|---|---|
| 1 | DELETE project (active) → 200 + 이후 읽기 200 + 쓰기 409 | should-fire | `test_archive_project_via_delete_blocks_writes_keeps_reads` (:244) | ✓ |
| 2 | DELETE draft (active) → 200 + 쓰기 409 + 읽기 200 | should-fire | `test_archive_draft_via_delete` (:274) | ✓ |
| 3 | DELETE project 재archive → 200 idempotent | should-fire | `test_archive_is_idempotent` (:302) | ✓ |
| 4 | **DELETE draft 재archive → 200 idempotent** | should-fire | **(없음 — project만 lock)** | Issue #2 |
| 5 | **DELETE draft under ALREADY-ARCHIVED project → 200 (§115 :121)** | should-fire | **(없음)** | **★ Issue #1** |
| 6 | DELETE missing project → 404 | should-NOT-fire | `test_archive_missing_and_cross_project_returns_404` (:313) | ✓ |
| 7 | DELETE cross-project draft → 404 | should-NOT-fire | 동일 (:313) | ✓ |
| 8 | DELETE missing draft (존재 project) → 404 | should-NOT-fire | (명시 test 없음, `_require_draft`로 404 — 다른 엔드포인트에서 광범위 커버) | Issue #3 (trivial) |

빈칸 #4/#5/#8. #5가 핵심(아래 Issues).

### Surface 5 — 독립 재현 결과 (`/tmp/repro_archive.py`)

```
=== (A) archive draft under ALREADY-ARCHIVED project ===
  archive draft under archived project -> HTTP 200 (archived= True)
=== (B) idempotent re-archive of a DRAFT ===
  first: 200 second: 200 (archived= True)
=== (C) cross-project / missing 404 ===
  missing project: 404 / cross-project draft: 404 / missing draft (existing project): 404
=== (D) archived project -> new draft / save still 409 ===
  new draft under archived project: 409 / save under archived project: 409
```

(A) archived project의 draft archive → 200, (B) draft 재archive → 200/200. 방어/동작은 존재하지만 lock 없음. (C)(D)는 기존 회귀와 일치.

### Surface 6 — §115 :119 vs :121 정합성 (코드는 정합, prose는 함축적)

- **코드**: `archive_draft`(service.py:347-352)는 `_require_project` + `_require_draft`만 하고 `project.archived`를 검사하지 않는다 → archived project의 하위 draft도 archive(상태전이) 허용 → 200.
- **§115 정합**: :121 "archive/unarchive 같은 상태 전이는 본 쓰기 차단의 대상이 아니다"가 archive_draft(상태전이)를 차단 예외로 둔다. :119 "project archive는 그 하위 draft 쓰기까지 차단한다"의 "draft 쓰기"는 앞 문장이 명시적으로 열거한 "본문 쓰기(draft 생성·version 저장)·메타데이터 수정(rename)"을 가리킨다. archive_draft는 이 열거에 없고 :121이 별도 카테고리로 제외 → **코드 동작은 §115와 정합(버그 아님)**.
- **다만 prose 함축성**: :119 "하위 draft 쓰기까지 차단"을 archive_draft 포함으로 오독할 여지가 있다. "archive_draft 등 상태전이는 :121 예외"라는 명시적 연결이 prose에 없다 → CLAUDE.md "Spec-silent-but-code-enforced" 경향. 코드는 허용하지만 그 근거가 :121 함축 해석에 의존.

### Surface 7 — 숫자 재계산

```
python3 -m unittest discover -s tests   →  Ran 206 tests ... OK (skipped=27)
```

reported "206 / 27 skip"과 정확 일치. +4 test(archive 회귀 4종, 202→206). 27 skip = Mongo 미연결(mixin). ✓

## Issues / Risks

### Issue #1 (조건성 — archived project의 하위 draft archive 분기 lock 부재)

- **현상**: `archive_draft`(service.py:347-352)가 `project.archived`를 검사하지 않아, archived project의 하위 draft도 DELETE(archive)가 200으로 통과한다. 이 동작을 lock하는 test가 없다.
- **정합성**: 코드는 §115 :121(상태전이 예외)와 정합하다(Surface 6). 버그가 아니다.
- **왜 조건성인가**: 이 분기는 §115 :119("하위 draft 쓰기 차단")와 :121("상태전이 차단 아님")의 해석 교차점으로, prose에 "archive_draft는 :121 예외"라는 명시적 연결이 없다. 회귀 관점에서 누군가 `archive_draft`에 `project.archived` 체크를 추가하면(over-correction, :119 literal 해석) archived project의 draft archive가 409로 바뀌는데 현재 test suite로는 잡을 수 없다 → under-strict/over-strict 양방향 guard 부재.
- **권고**: (a) 회귀 추가 — archived project에서 DELETE draft가 200(should-fire)을 단언; (b) (선택) §115에 "archive_draft/archive_project 상태전이는 :119 쓰기차단의 대상이 아님"을 명시적 clause로 추가해 함축 해석을 없앤다. (a)만으로 충분; (b)는 견고화. 본 세션 `/tmp/repro_archive.py` (A)가 test 뼈대.

### Issue #2 (비차단, minor — draft 재archive idempotent lock 부재)

- **현상**: `test_archive_is_idempotent`(:302)는 project 재archive만 다룬다. draft 재archive도 코드는 idempotent(archived 체크 없음)하지만 lock 없음.
- **독립 재현** (B): draft DELETE 두 번 → 200/200.
- **권고**: draft 재archive 200 단언 추가. 비차단(project 대칭성 차원의 사소한 보강).

### Issue #3 (비차단, trivial — missing draft DELETE 404)

- `test_archive_missing_and_cross_project`(:313)은 missing project + cross-project draft. missing draft(존재 project, 없는 draft)는 명시 test가 없으나, `_require_draft`(service.py)가 다른 엔드포인트에서 광범위하게 404를 잡으므로 회귀 위험 낮음. 독립 재현 (C)로 404 확인.

### Risk R1 (비차단 — DELETE=archive 의미론은 합의된 선택)

DELETE를 hard-delete가 아닌 archive로 매핑하는 것은 REST 순수주의 관점에서 논쟁적일 수 있으나, §115 :116이 "삭제는 archive로 처리"를 명시하므로 계약 정합. 응답이 200(archived=true)이지 204가 아닌 것도 soft-delete 의미론에 부합(상태를 반환). 비차단.

## Verdict

**조건부 합격**.

- load-bearing 긍정: 커밋 무결성 정확, DELETE 엔드포인트 + NotFound→404 매핑(409 불필요, 정합), DELETE=archive 의미론(§115 :116 + REST idempotency), 읽기 허용/쓰기 409 after archive lock(test #1/#2), project 재archive idempotent lock(test #3), cross-project/missing 404 lock(test #4), reported 206/27 skip 독립 재계산 일치, CRUD API(create·list·get·rename·archive) 완성 주장 확인.
- load-bearing 조건: **Issue #1(archived project의 하위 draft archive 분기 lock 부재) 해소 필요**. 코드는 §115 :121과 정합하나, 그 정합성이 :119/:121 함축 해석에 의존하고 회귀로 잠기지 않아 양방향 guard 부재. CLAUDE.md 기준 lock 추가 전 무조건 합격 불가. lock(±prose 명시) 추가 시 합격.
- 비차단: Issue #2(draft 재archive)/Issue #3(missing draft)/R1(DELETE=archive 의미론)은 verdict를 갈라놓지 않는다.

## Outstanding items

- Issue #1 회귀 추가 여부는 사용자 결정(검증자는 코드를 고치지 않음). `/tmp/repro_archive.py` (A)가 test 뼈대. prose 명시(§115 :119↔:121 연결)는 선택적 견고화.
- Mongo replica set 경로(27 skip)는 본 세션 미연결 — service/API layer는 in-memory로 독립 재현 완료. archive는 기존 `archive_project`/`archive_draft` 재사용이라 Mongo persist는 선행 검증(`mongo_adapter`, `source_ref_persistence`)이 잠금.
- 후속 후보: gateway compose 편입, plan 01 #7 fixture(Phase 2 소비자 생길 때) — 본 검증과 무관.

## Reproduction

```bash
# 1. 전체 숫자 재계산
python3 -m unittest discover -s tests                 # 206, 27 skip

# 2. archive 회귀 focused
python3 -m unittest tests.test_application_api -v     # archive 4종 포함 pass

# 3. 조건성 분기 독립 재현 (archived project draft archive / draft re-archive)
PYTHONPATH=. python3 /tmp/repro_archive.py            # 본 검증이 작성한 스크립트
```
