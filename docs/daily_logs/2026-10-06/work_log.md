# 2026-10-06 Work Log

## Goals
- 프로젝트 세부정보의 "승인된 작품 기억"이 제목만 보여 무엇이 승인됐는지 알 수 없고 수정도 불가능하다는 오너 지점을 보강한다: 승인된 기억의 목록·상세·이력 표시와 직접 수정 경로.

## Completed work

### 1. 결정 브리프 → 오너 결정 (B안)
- 문제: memory 라우터는 읽기 전용 2 operation이고 canonical 쓰기는 분석 후보 경로(confirm/edit/auto-promote/versioned apply)로만 흐른다. "사람이 직접 정본을 고치는" 쓰기 경로는 기존 계약·선례에서 유도 불가한 정책 방향이었다.
- 선택지 A(읽기 전용)·B(수동 버전 편집 API)·C(폐기만)·D(B+되돌리기) 브리프를 제시, 오너가 **B**를 선택.
- 기록: `docs/plans/canonical-memory-manual-edit-decisions.md` 신설, SoT v1.8.80.

### 2. 백엔드 — 수동 버전 편집 API
- `services/application/app/analysis/models.py`: `AnalysisProvenance.HUMAN_EDITED = "human_edited"` 추가(사람이 고친 값에 기존 두 값은 거짓말).
- `services/application/app/memory/service.py`: `edit_canonical_version()` — append-only 유지(새 canonical 버전 발행 + 대상 `SUPERSEDED` 보존), `provenance=human_edited`, `source_candidate_id="manual:{idempotency_key}"`(후보 유일 인덱스가 곧 멱등 저장소 — 재시도는 replay), `scope` payload 재계산, 근거·신뢰도·분석 잡 이어받기, 재색인 outbox 초크 포인트 통과, 후보 taxonomy 검증 재사용.
- `services/application/app/api/models.py`: `EditMemoryRequest`(`base_version` ge=1 · `idempotency_key` · `payload`, extra 금지).
- `services/application/app/routers/memory.py`: `PUT /projects/{project_id}/memory/{memory_id}` — 400(taxonomy 위반)·404(없는 기억·프로젝트)·409(낡은 base_version·비-canonical 대상·**보관 프로젝트**). 보관 409 가드는 brief PUT 선례(승격 경로엔 없음 — SoT에 차이 명시).
- `services/application/app/main.py`·`activity/actions.py`: 라우터 조립에 activity 연결, `canonical_memory_edited` 등재(검토 결정 12→13).
- 효과: 승인된 정본 기억을 검토함을 거치지 않고 직접 교정해도 감사 사슬이 보존된다.

### 3. 프런트엔드 — 작품 기억 탭
- `frontend/src/projects/CanonicalMemoryPage.tsx` 신설: canonical 목록(타입·버전·출처 라벨 + 관찰 본문), 상태 확장(payload 전 필드·근거 수), `supersedes` 사슬 이력(v1 보존됨 → v2 현재 정본), 수정 폼(기존 키 집합 그대로 편집, 빈 값 저장 잠금, 성공 시 새 version 안내 + 목록 재로드, 409 오류 노출, 보관 읽기 전용).
- `ProjectSettingsPage.tsx`: 탭 4개로(작품 기억 추가, `?tab=memory`). `ProjectOverview.tsx`: 요약 그리드 유지 + "전체 보기 →" 링크; 라벨 표를 `memoryPresentation.ts`로 추출해 두 화면이 공유.
- `client.ts`: `CanonicalMemory` 전 필드화 + `putCanonicalMemory`.
- 효과: 오너 지점("무엇이 승인됐는지 볼 곳이 없다")이 해소된다.

### 4. main 의 기존 빨간 셀 수선
- `tests/test_application_api.py`: v1.8.78(2026-09-30)의 correct-name endpoint가 분석 OpenAPI 잠금 목록에 등재되지 않아 closure 셀이 **c22c239(main)에서 이미 실패 중**이었다(임시 worktree 로 HEAD~1 재현 확인). memory PUT 행과 함께 등재(memory track 7→8, analysis 23→24).

## Files changed
- 백엔드: `analysis/models.py`, `memory/service.py`, `api/models.py`, `routers/memory.py`, `main.py`, `activity/actions.py`
- 프런트: `CanonicalMemoryPage.tsx`(신설), `CanonicalMemoryPage.test.tsx`(신설), `memoryPresentation.ts`(신설), `ProjectSettingsPage.tsx`, `ProjectOverview.tsx`, `client.ts`, `activityActions.ts`, `styles.css`
- 테스트: `test_memory_manual_edit.py`(신설 12셀), `test_memory_mongo.py`(수동 편집 패리티 +1), `test_activity_actions.py`(30→31), `test_auth_api.py`(78/109), `test_application_api.py`(잠금 목록 2행), `ProjectSettingsPage.test.tsx`(탭 4개), `navigationLinks.test.ts`(보조 링크 집합 +1)
- 문서: `plans/canonical-memory-manual-edit-decisions.md`(신설), `system-contract-sot.md` v1.8.80

## Issues found
- **correct-name 잠금 목록 누락(사전 존재)** — 문제: v1.8.78 슬라이스가 분석 트랙 closure 셀을 갱신하지 않아 main 이 빨간 채로 남음. 원인: 슬라이스가 OpenAPI 선언은 만들고 잠금 목록 등재를 빠뜨림. 해결: 이번 슬라이스에서 등재(범위 자잘함). 결과: `test_application_api.py` 전수 초록.
- **승격 경로(promote)에 보관 가드 없음(인지된 차이)** — 이번 PUT 은 보관 409 가드를 뒀다(brief 선례). 승격 경로가 보관 프로젝트에서 열려 있는 것은 별개 사안이므로 조용히 손대지 않았다. 후속 검토 후보.

## Decisions / User Decisions and Rationale
- 오너 결정 2026-10-06: 수정 경로 = **B. 수동 버전 편집 API**. append-only 보존과 직접 수정 요구를 함께 만족하는 유일한 최소 모양. 되돌리기·폐기·수동 신규 생성·근거 인용문 본문 표시는 유예(결정 문서 "승인 전 보류").
- 조회 확장은 fork 아님 판정: GET 응답에 이미 전 필드가 실리므로 계약 무변 렌더만으로 충분. 탭 배치는 "개요는 이미 길다" 선례(observability-dashboard-decisions)를 따름.

## Verification
- 백엔드: `test_memory_manual_edit.py` 12 passed · `test_memory_api.py`·`test_memory_phase2b.py`·`test_memory_apply.py`·`test_activity_actions.py`·`test_activity_ui_labels.py` 70 passed · `test_auth_api.py` 154 passed(1248 subtests) · `test_application_api.py` 129 passed(595 subtests) · 분석 계열 5종 103 passed.
- **전수(회귀 기준선 재측정, test-mongo ON)**: backend **3107 passed / 1 skipped / 4345 subtests · EXIT=0 · 388.87초**(+27 passed = 이 슬라이스 +13 · 2026-09-14 이후 미재측정 슬라이스들의 미청구분 +14). 프런트 **517 passed / 44 files · EXIT=0**. HANDOFF·README 기준선 행을 같은 수로 갱신했다.
- **전수가 잡은 것 한 건**: `navigationLinks.test.ts` 의 보조 이동 링크 집합 가드가 새 `CanonicalMemoryPage.tsx`(머리의 "검토함 →" 링크)를 등재 요구했다 — 첫 전수에서 붉어진 것을 확인하고 집합에 등재해 닫았다. 종전 `tail` 파이프가 실패를 가린 일도 함께 격리: `npx vitest run 2>&1 | tail` 은 파이프라인 종료코드가 tail 의 것이 되므로 전수 판정에는 쓰지 않는다(이 슬라이스의 측정 교훈).
- 프런트: `CanonicalMemoryPage.test.tsx` 7 passed · `ProjectOverview.test.tsx`·`ProjectSettingsPage.test.tsx` 15 passed · `npm run build`(tsc --noEmit) 통과.
- 변이 검증(커밋 `0fa2a4c` 위에서 실시, 각 변이 후 `git checkout --` 복원, 복원 뒤 12 passed 재확인):

| 변이 | 위치(file:line 당시) | 실패한 셀 |
|---|---|---|
| M1 `provenance=target.provenance`(이어받기로 교체) | `memory/service.py` edit_canonical_version | `ManualEditHappyPathTest::test_edit_mints_a_new_canonical_version_and_supersedes_the_target` |
| M2 `scope=target.scope`(이어받기로 교체) | 〃 | `ManualEditHappyPathTest::test_rederives_the_scope_from_the_edited_payload` |
| M3 supersede write(`update_memory(replace(target, SUPERSEDED))`) 제거 | 〃 | happy path(보존 단정) · `test_different_key_on_the_stale_base_is_rejected` · `test_editing_a_superseded_version_is_a_409` · `test_second_edit_versions_the_new_canonical_entry` — 4셀 |
| M4 stale-base guard(`base_version != target.version` 분기) 제거 | 〃 | `ManualEditRejectionTest::test_stale_base_version_is_a_409` |

- 셀은 under-strict(보존·재계산·가드 부재 시 재실패)와 over-strict(replay 가 version 3 를 만들면 실패하는 `test_same_key_replays_...`, 보관 프로젝트 수정 버튼 노출 시 실패하는 프런트 셀) 양방향으로 물었다.

## Next steps
- 되돌리기 버전 재발행(유예 D)·폐기(retire)는 결정 문서의 후속 경로가 열려 있다.
- 승격 경로(promote)의 보관 프로젝트 가드 부재를 별도 검토한다.
- 근거 인용문 본문 조회는 memory↔source_ref 교차 계약이 필요하다(유예).

## 세션 2 — 정본 기억 병합 (오너 결정 A안)

### Goals
- 같은 인물이 분석 표기("나"/"주인공")에 따라 별개 canonical 으로 갈라져 살아 있는 사례를 하나로 통합하는 경로 — "수정 및 통합, 이어져 있어야지, 인물의 별도 상태도 포함"(오너).

### Completed work
- 사전 확인: 기존 병합 기계(`analysis/reconciliation.py`)는 **후보→정본** 흡수뿐 — 정본↔정본 경로는 없었다. 상세·이력의 v1/v2가 본문 버전(payload 사슬)임을 오너에게 확인.
- 브리프(사슬 연결 3안) → 오너 결정 **A. 생존 사슬 승계 + `merged_into` 포인터**.
- 백엔드: `MemoryEntry.merged_into`(옛 행 결측=None, Mongo reader `.get`) · `MemoryService.merge_canonical_entries()` — 병합 결과 = 생존 쪽 다음 버전, 흡수 항목 SUPERSEDED+앞링크, 근거 양쪽 유니온, `provenance=human_edited`, 합성 멱등 키 `manual:{key}`, `scope` 재계산 · `POST /projects/{id}/memory/merge`(양쪽 base 각각 검사, 오류 메시지가 survivor/absorbed 축을 밝힘; 자기 병합·타입 불일치·인물 외·비-canonical·보관 409, 스키마 400) · 활동 로그 `canonical_memory_merged`(`after="version=N, absorbed=1"`, replay 무행).
- 프런트: 작품 기억 탭에 병합 흐름 — 인물 항목의 "다른 기억과 병합…" → 같은 종류 상대 선택("이 항목과 병합") → **양쪽 관찰이 이어져 미리 채워진 편집 폼**(하나의 문장으로 다듬음) → 저장; 병합 결과 상세에 "병합으로 합쳐진 기억" 절(흡수 사슬 + `병합됨 → 결과(vN)` 앞링크 표시).
- 가드 카운트: 검토 결정 13→14(기록 31→32) · 프로젝트 tier 78→79/전체 109→110 · memory OpenAPI 잠금 목록 8→9.

### Files changed
- 백엔드: `memory/models.py`, `memory/service.py`, `memory/mongo_repository.py`, `api/payloads.py`, `api/models.py`, `routers/memory.py`, `activity/actions.py`
- 프런트: `api/client.ts`, `CanonicalMemoryPage.tsx`, `styles.css`, `activityActions.ts`
- 테스트: `test_memory_merge.py`(신설 12셀), `test_memory_mongo.py`(병합 패리티 +1), `test_activity_actions.py`·`test_auth_api.py`·`test_application_api.py`(카운트), `CanonicalMemoryPage.test.tsx`(병합 4셀 추가)
- 문서: 결정 문서 §4·SoT v1.8.81·CHANGELOG·본 로그

### Decisions / User Decisions and Rationale
- 오너 결정 2026-10-06(두 번째): 병합 사슬 연결 = **A**. 생존 사슬 승계(버전 리셋 없음) + `merged_into` 앞링크 — "이어져 있어야지"를 데이터로 보존. B는 로그 검색으로만 만족, C는 버전 리셋.
- 인물(character_observation) 한정은 `reconciliation` 의 character-only 선례와 같은 이유 — 사건·떡밥의 통합 의미는 미정의(유예).

### Verification
- `test_memory_merge.py` 12 passed · `test_activity_actions.py`·`test_activity_ui_labels.py`·`test_application_api.py`·`test_memory_api.py`·`test_memory_manual_edit.py` 194 passed(748 subtests) · `test_auth_api.py` 154 passed(1261 subtests) · 분석 계열 68 passed. 프런트 `CanonicalMemoryPage.test.tsx` 11 passed · `npm run build` 통과 · **전수 521 passed / 44 files · EXIT=0**.
- 변이 검증(커밋 `1242d92` 위, 각 후 `git checkout --` 복원, 복원 후 12 passed 재확인):

| 변이 | 위치(file:line 당시) | 실패한 셀 |
|---|---|---|
| M5 흡수 항목 업데이트에서 `merged_into=merged.id` 제거 | `memory/service.py` merge_canonical_entries | `MergeHappyPathTest::test_merge_continues_the_survivor_chain_and_links_the_absorbed_one` |
| M6 `version=1`·`supersedes=None`(사슬 리셋) | 〃 | happy path · `test_merge_enqueues_a_reindex_and_records_one_activity_row` · `test_the_merged_chain_accepts_a_later_edit_as_v3` — 3셀 |
| M7 근거 유니온을 생존 쪽만으로 | 〃 | happy path(유니온 단정) |

- over-strict: replay 가 재발행하면 실패(`test_same_key_replays_...`), 낡은 base 양축 각각 409, 자기 병합·타입 불일치·인물 외 409, 사건 항목에 병합 버튼 없음(프런트).
- **Mongo 패리티 셀 정정**: 첫 전수(test-mongo ON)에서 신규 병합 패리티 셀이 실패했다 — 원인은 구현이 아니라 **테스트 기대값의 순서 오류**였다(근거 유니온은 순서 보존으로 생존 쪽이 먼저 오는데 흡수 쪽 순서로 적었음). 기대값을 고치고 같은 서버에서 7/7 재확인, 전수를 다시 돌렸다(테스트 한 줄이 바뀌어도 재측정이 규칙).

### Issues found
- 병합 재발 가능성: 분석이 같은 표기("나")를 다시 승격하면 중복이 재생된다 — 별칭 매처 축에서 병합 뒤 지속을 검토해야 한다(유예 등재).

### Next steps
- (마무리됨) 전수 재측정: backend **3120 passed / 1 skipped / 4372 subtests · EXIT=0 · 384.86초**(test-mongo ON, +13 passed = 이 슬라이스 전부). HANDOFF·README 기준선 행을 같은 수로 갱신했다.
