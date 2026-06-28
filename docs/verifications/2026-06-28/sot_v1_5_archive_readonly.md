# SoT v1.5 §115 archive 읽기전용 명문화 독립 검증

## Subject Metadata

- **날짜**: 2026-06-28
- **요청자**: 사용자 ("이번 SoT 명문화를 새로 커밋했습니다 — 89f1f0a. … 이상한 부분 체크")
- **검증자**: Claude (본 세션)
- **대상 커밋**: `89f1f0a` — docs: clarify archive as read-only in SoT v1.5 (rename_api R1)
- **audit subject (이번 검증은 코드가 아니라 계약 문서)**:
  - `docs/system-contract-sot.md` **v1.5 §115** (archive 읽기전용 명문화, system-contract-sot.md:117-122)
  - `docs/system-contract-sot.md` 계약 버전 이력 v1.5 row(:36), 헤더(:4), 문서역할표(:47)
  - `tests/test_core_sot.py` source_ref carve-out 회귀(test_core_sot.py:406)
- **정본 spec 참조**: 본 검증의 대상이 곧 정본 spec 자체(v1.5 §115)이므로, 정합성 기준은 (a) §115 내부 자기일관, (b) §115 ↔ 다른 SoT clause(§99-100 snapshot 불변, §116 보존/stale, §132 추적성) 일관, (c) §115 ↔ 구현 코드 일관, (d) §115 ↔ 회귀 test 1:1 매핑.
- **작업 출처**: committed (`89f1f0a`) + 선행 follow-up 커밋 `781ced0`(version cross-project + archived read lock), `a735257`(rename_draft project-archived lock). `git status` clean.
- **검증 입장**: §115 prose가 자기모순 없는가(source_ref "쓰기"를 허용하는 carve-out이 "쓰기 차단" 프레임과 충돌하지 않는가), §115의 모든 경계가 코드 + 회귀에 매핑되는가, source_ref carve-out lock이 양방향(under-strict)으로 증명되는가, 직전 검증들의 미해소 findings가 폐쇄됐는가.

## Scope

1. **커밋 구조**: `89f1f0a`가 "문서 명문화 + carve-out 회귀 1건"이라는 작업자 주장이 맞는지
2. **§115 자기일관 (★)**: archive=읽기전용 프레임 내에서 source_ref "쓰기 허용" carve-out이 모순 없이 조율됐는지 (CLAUDE.md "contract 자기모순 = blocking")
3. **§115 ↔ 코드 boundary matrix (★)**: §115의 모든 경계가 코드에 구현 + 회귀에 lock되어 있는지 (빈칸 = blocking)
4. **source_ref carve-out**: create_source_ref가 실제로 archived 체크 안 하는지 + 회귀가 under-strict로 lock하는지(mutation 증명)
5. **이전 findings 폐쇄**: version_read Issue #1/#2, rename Issue #1/#2가 follow-up 커밋으로 닫혔는지
6. **계약 버전 이력 정합성**: v1.5 bump(헤더/이력/역할표) 일관
7. **실구동 숫자 재계산**: reported "202 / 27 skip"

## Methodology

### 1. 커밋 구조 + follow-up 추적

```bash
git show 89f1f0a --stat                          # 문서 4 + test 1
git log --oneline e34364b..89f1f0a               # follow-up 커밋 확인
git log -S "<test_name>" -- tests/              # 각 lock test의 추가 커밋
```

### 2. §115 자기일관 — contract 자기 교차 점검

§115(system-contract-sot.md:117-122)의 각 하위 clause를 읽고, (a) "쓰기 차단" vs "source_ref 허용" carve-out, (b) "본문 불변" vs "source_ref 허용", (c) §116 보존 vs :117 읽기전용, (d) §132 추적성 vs source_ref 허용 의 정합성을 점검.

### 3. §115 ↔ 코드 boundary matrix

§115의 모든 경계를 추출 → 코드 구현 라인 → 회귀 test에 1:1 매핑. 빈 칸 = finding.

### 4. source_ref carve-out mutation 증명 (`/tmp/repro_carveout_mutation.py`)

```bash
PYTHONPATH=. python3 /tmp/repro_carveout_mutation.py
```

create_source_ref를 monkey-patch로 archived 거부 버전으로 교체(working tree 미변경) → `test_source_ref_creation_allowed_on_archived`가 FAIL할 것(under-strict)을 증명.

### 5. 테스트 독립 재실행 + 숫자 교차 검증

```bash
python3 -m unittest discover -s tests                 # reported 202/27 skip 재계산
python3 -m unittest tests.test_core_sot.CoreSotIsolationAndArchiveTest \
  .test_source_ref_creation_allowed_on_archived \
  tests.test_core_sot.CoreSotIsolationAndArchiveTest.test_archive_preserves_version_read \
  tests.test_application_api.ApplicationApiTest.test_rename_draft_blocked_when_only_project_archived -v
```

## Findings

### Surface 1 — 커밋 구조 + follow-up 추적

`git show 89f1f0a --stat`: `system-contract-sot.md`(+11/-2)·`test_core_sot.py`(+28)·CHANGELOG·HANDOFF·work_log = 5 files, +57/-5. 작업자 주장 "코드 변경은 carve-out 회귀 1건뿐, 나머지는 문서 정합화"와 정확 일치.

`git log e34364b..89f1f0a`로 직전 rename 검증 이후 follow-up 2개 확인:
- `781ced0` "test: lock cross-project version isolation + archive read" → `test_get_version_cross_project_returns_404` + `test_archive_preserves_version_read`
- `a735257` "test: lock rename_draft project-archived branch" → `test_rename_draft_blocked_when_only_project_archived`

즉 작업자가 **본 세션의 직전 두 검증에서 제기된 모든 findings를 별도 follow-up 커밋으로 폐쇄**한 뒤 SoT에 명문화했다. 아래 Surface 5.

### Surface 2 — §115 자기일관 (★ 핵심, 자기모순 점검)

§115(system-contract-sot.md:117-122) 하위 clause 교차 점검 결과 **자기모순 없음**:

| 점검 쌍 | 정합성 |
|---|---|
| :119 "본문 쓰기·메타(rename) 차단" vs :122 "source_ref 생성 허용" | ✓ :122가 "이는 본문/메타데이터 쓰기 차단의 **예외**다"로 명시적 조율. source_ref를 snapshot 파생 "주석" 카테고리로 분류하여 본문(snapshot/version/block)·메타(project.name/draft.title)과 구분. |
| :120 "SOT 본문 불변" vs :122 "source_ref 허용" | ✓ source_ref는 본문이 아닌 본문에 대한 주석 → 본문 불변을 위반하지 않음. |
| :119 "project archive는 하위 draft 쓰기까지 차단" vs :122 "source_ref 허용" | ✓ source_ref는 project archived 여부와 무관한 carve-out. project archived여도 같은 project_id면 허용. |
| §116 "보존" vs :117 "읽기전용" | ✓ 보존 + 읽기허용 + 쓰기차단은 정렬(데이터는 남고 읽힘, 새 쓰기만 막힘). |
| :121 "상태 전이(unarchive)는 차단 대상 아님, archived인 동안 차단" | ✓ 영구 불변이 아닌 "archived 동안" 한정 → unarchive 여지 보존, 자기모순 아님. |
| §99-100 "snapshot 불변" vs :120 "본문 불변" | ✓ 동일 계약 반복, 일관. |
| §132 "source_ref로 원문 재조회" vs :122 "source_ref 생성 허용" | ✓ 추적성 계약을 source_ref 허용이 지원. |

CLAUDE.md "internal contract inconsistency is blocking" 기준 — **blocking 자기모순 없음**. source_ref carve-out은 prose로 카테고리를 명확히 구분하여 "쓰기 차단" 프레임과 충돌하지 않는다.

### Surface 3 — §115 ↔ 코드 boundary matrix (★ 핵심)

| §115 경계 (system-contract-sot.md) | 코드 구현 | 회귀 test | 상태 |
|---|---|---|---|
| 읽기 허용(get/list, version/snapshot/block 재조회) :118 | get/list 계열 + list_draft_versions/get_draft_version — archived 체크 없음 | `test_archived_project_and_draft_remain_listable_and_gettable` (test_application_api.py:339), `test_archive_preserves_version_read` (test_core_sot.py:381) | ✓ |
| 본문 쓰기 차단 — draft 생성 :119 | `create_draft` project.archived (service.py:169-170) | `test_project_archive_blocks_new_draft_and_save_but_preserves_history` (test_core_sot.py:320) | ✓ |
| 본문 쓰기 차단 — version 저장 :119 | `save_draft` `_require_active_project_and_draft` (service.py:248) | `test_archive_blocks_new_save_but_preserves_snapshot_and_version` (test_core_sot.py:296), `test_archive_preserves_version_snapshot_and_blocks` (test_core_sot_mongo.py:310) | ✓ |
| 메타 수정 차단 — rename :119 | `rename_project` project.archived (service.py:181-182), `rename_draft` project+draft.archived (service.py:189-193) | `test_rename_on_archived_is_blocked_409` (test_application_api.py:187), `test_rename_draft_blocked_when_only_project_archived` (:210), `test_rename_project_allowed_when_only_draft_archived` (:229) | ✓ |
| project archive는 하위 draft 쓰기까지 차단 :119 | `rename_draft` project.archived 먼저 (service.py:189-190), `save_draft`/`create_draft` project.archived | `test_rename_draft_blocked_when_only_project_archived` (:210) | ✓ |
| SOT 본문 불변(archive 무관) :120 | snapshot/version/source_block immutable dataclass | 기존 불변 회귀(Known SHA-256 vector, immutable snapshot/hash/block) | ✓ |
| source_ref 생성 허용(carve-out) :122 | `create_source_ref` archived 체크 **없음** (service.py:299-317) | `test_source_ref_creation_allowed_on_archived` (test_core_sot.py:406) | ✓ |
| 상태 전이(unarchive) 범위 밖 :121 | unarchive 구현 없음 | — (명시적 범위 한정, N/A) | ✓ |

**boundary matrix 빈칸 없음.** §115의 모든 경계가 코드 + 명명 회귀에 1:1 매핑된다.

### Surface 4 — source_ref carve-out 코드 정합 + mutation 증명

- **코드 정합**: `create_source_ref`(service.py:299-317)는 `snapshot.project_id != project_id` + span 무결성만 체크하고 archived 검사가 없다 → §115 :122 "archived 상태에서도 허용"과 정확 일치.
- **mutation 증명** (`/tmp/repro_carveout_mutation.py`):
  ```
  baseline (carve-out honored): create_source_ref succeeded, quote = 'Paragraph'
  under-strict proven: simulated regression raises Archived ->
    test_source_ref_creation_allowed_on_archived (asserts success) would FAIL
  restored: create_source_ref succeeds again (monkey-patch reverted)
  ```
  create_source_ref를 archived 거부 버전으로 monkey-patch(working tree 미변경)하면 `Archived`가 raise → 성공을 단언하는 회귀가 FAIL → **under-strict 방향 lock 증명**. monkey-patch는 복원됨.

### Surface 5 — 이전 검증 findings 전부 폐쇄 (긍정)

본 세션 직전 두 검증에서 제기된 findings가 follow-up 커밋으로 전부 닫혔다:

| 이전 검증 finding | 폐쇄 커밋 | lock test | mutation |
|---|---|---|---|
| `version_read_api` Issue #1 (cross-project version 격리 미lock) | `781ced0` | `test_get_version_cross_project_returns_404` | HANDOFF에 "절 제거 시 FAIL" 기록 |
| `version_read_api` Issue #2 (archived version read 미lock) | `781ced0` | `test_archive_preserves_version_read` (test_core_sot.py:381) | — |
| `rename_api` Issue #1 (rename_draft project.archived 절 미lock, **차단성**) | `a735257` | `test_rename_draft_blocked_when_only_project_archived` (test_application_api.py:210) | docstring "Removing that guard would wrongly allow…" 명시 |
| `rename_api` Issue #2 (rename_project draft 무관성 should-fire 미lock, 비차단) | `a735257` | `test_rename_project_allowed_when_only_draft_archived` (test_application_api.py:229) | — |

4/4 폐쇄. 차단성이었던 rename Issue #1까지 docstring에 mutation을 명시한 격리 test로 닫혔다.

### Surface 6 — 계약 버전 이력 정합성

- 헤더: `v1.4` → `v1.5` (system-contract-sot.md:4)
- 이력 row 추가: `v1.5 | 2026-06-28 | archive를 읽기 전용 상태로 명문화… | 사용자 결정, docs/verifications/2026-06-28/rename_api.md R1` (:36) — 근거가 직전 rename 검증 R1을 정확히 인용
- 문서역할표: `Approved SoT v1.4` → `Approved SoT v1.5` (:47)
- HANDOFF Next Tasks #9(R1 권고) 제거(해소), #5에 "archive 후 source_ref 생성 허용은 v1.5에서 확정·회귀 lock됨" 반영

3개 지점(헤더/이력/역할표) + HANDOFF 모두 정합. CLAUDE.md "사용자 결정이 정본 계약을 바꾸면 계약 버전 갱신 + 변경 이력에 근거" 충족.

### Surface 7 — 숫자 재계산

```
python3 -m unittest discover -s tests   →  Ran 202 tests ... OK (skipped=27)
```

reported "202 / 27 skip"과 정확 일치. 27 skip = Mongo 미연결(test_core_sot_mongo Fallback+Transaction mixin). +1 test(carve-out 회귀, 199→200... 실제 follow-up 2개 커밋의 test 포함 202). ✓

## Issues / Risks

**차단성 finding 없음.**

### Risk R1 (비차단 — 명시적 범위 한정, 정상)

§115 :122가 `create_source_ref` idempotency(같은 span 재호출 시 매번 새 ref)와 분석 후보(candidate)의 archived 정책을 "Phase 2/6에서 별도로 정한다"고 명시. 이는 HANDOFF Next Tasks #5/#7과 일치하며, CLAUDE.md "No silent caps" 원칙에 따라 범위 밖을 명시적으로 기록한 것이다. candidate 모델이 아직 없으므로 N/A이고, source_ref idempotency는 기존부터 Phase 2 추적 항목.

### Risk R2 (비차단 — prose 조밀도)

§115 :117-122는 6개 하위 clause로 조밀하지만, 각 clause가 카테고리(읽기/본문 쓰기/메타 수정/본문 불변/상태전이/source_ref carve-out)를 명확히 구분하여 모순을 피한다. 가독성 차원에서 향후 세분화 여지는 있으나 정합성에는 영향 없음.

### Risk R3 (비차단 — follow-up 커밋이 본 검증 대상 커밋 외부)

이전 findings를 닫은 `781ced0`/`a735257`는 `89f1f0a`와 별개 커밋이다. 본 검증은 두 follow-up이 이미 main에 merge된 상태에서 수행했으므로 현 시스템 상태 기준으로 합격 판정이 유효하다. 단, "89f1f0a 단독으로 직전 findings를 폐쇄했다"는 오해를 피하기 위해 본 record에 follow-up 커밋을 명시적으로 분리 기록한다(Surface 1, 5).

## Verdict

**합격**.

- load-bearing 긍정: (1) §115 자기일관 — source_ref carve-out이 "쓰기 차단" 프레임과 모순 없이 prose로 카테고리 조율(blocking 자기모순 없음), (2) §115 ↔ 코드 boundary matrix 빈칸 없음 — 모든 경계가 코드 + 명명 회귀에 1:1 매핑, (3) source_ref carve-out 코드 정합 + under-strict mutation 증명, (4) 계약 버전 이력(헤더/이력/역할표/HANDOFF) 정합, (5) 직전 두 검증의 findings 4/4 전부 폐쇄(차단성이었던 rename Issue #1 포함), (6) reported 202/27 skip 독립 재계산 일치.
- 차단성 finding 없음. 비차단 R1/R2/R3는 verdict에 영향 없음.
- 본 검증은 audit subject가 "계약 문서 정합성"인 사례로, CLAUDE.md "Cross-check the contract against itself" + "boundary matrix에 빈 칸 없음" + "Test code is part of the audit subject" 기준을 모두 충족한다.

## Outstanding items

- §115가 명시적으로 범위 밖으로 둔 항목(unarchive 상태전이, source_ref idempotency, candidate archived 정책)은 Phase 2/6에서 결정 — 본 검증 시점에 미해소가 아니라 의도적 연기.
- Mongo replica set 경로(27 skip)는 본 세션 미연결 — source_ref carve-out은 in-memory로 mutation 증명 완료, Mongo persist 경로의 archive 보존은 선행 `mongo_adapter`/`source_ref_persistence` 검증이 잠금.
- 후보: unarchive 연산 필요 시 명시적 named 연산으로 추가(작업자가 "지금 일반화하지 않음"으로 결정, 본 검증 동의 — 범위 밖 명시가 정합).

## Reproduction

```bash
# 1. 전체 숫자 재계산
python3 -m unittest discover -s tests                 # 202, 27 skip

# 2. carve-out + 이전 findings lock 회귀 focused
python3 -m unittest tests.test_core_sot.CoreSotIsolationAndArchiveTest \
  .test_source_ref_creation_allowed_on_archived \
  tests.test_core_sot.CoreSotIsolationAndArchiveTest.test_archive_preserves_version_read \
  tests.test_application_api.ApplicationApiTest.test_rename_draft_blocked_when_only_project_archived -v

# 3. source_ref carve-out under-strict mutation 증명 (working tree 미변경)
PYTHONPATH=. python3 /tmp/repro_carveout_mutation.py

# 4. 계약 문서 정합 (자기 일관 + 버전 일관)
sed -n '114,124p;36p;47p' docs/system-contract-sot.md
```
