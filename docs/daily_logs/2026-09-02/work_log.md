# 2026-09-02 Work Log

## Goals

- Dogfood에서 확인한 최종 저장 분석 진행 표시 공백을 닫는다.
- 미승인 기억 후보의 중복 정체성 처리 경계를 기술 검토한다.
- 검토함에서 candidate 내용을 읽고 즉시 승인/거절할 수 있게 한다.
- Chapter→Scene 목록에서 finality와 분석 상태를 구분한다.
- 독립 검증 `dogfood_review_ux.md`의 차단 결함과 값 수준 무셀을 폐쇄한다.

## Completed work

| 작업 | 변경 파일 | 핵심 변경 | 효과 |
|---|---|---|---|
| finalize 요청 중 진행 표시 | `frontend/src/drafts/DraftEditor.tsx` · `DraftEditor.test.tsx` | finalize 호출 직전 `analysisStatus=running`, 전체 요청 실패시 `failed`, 응답 성공시 서버 job 상태로 수렴. `running`은 stale/needs-attention 판정보다 먼저 표시 | 장시간 동기 분석 중에도 상태 바와 버튼에서 진행 확인. 완료 후 page reload 없이 자동 수렴 |
| Review Inbox 목록 요약 | `routers/analysis.py` · `frontend/src/api/client.ts` · `ReviewInbox.tsx` · `styles.css` · 회귀 | list item에 immutable candidate `payload` additive. 행을 유형/신뢰도·payload 필드·상세 링크·즉시 승인/거절 구조로 확장. 작은 화면은 단일 열로 수렴 | detail 페이지를 매번 열지 않고 목록에서 후보 내용을 읽고 처리 |
| Scene 목록 상태 | `api/models.py` · `routers/drafts.py` · generated `schema.d.ts` · `DraftList.tsx` · 회귀 | `ScenePayload` 에 latest/finalized/analysis snapshot·status를 additive. 최신 snapshot 동일성으로 finality 3상태와 analysis 4상태를 텍스트로 파생 | 최종 저장 후 수정본을 완료로 오인하지 않고, 장면 목록에서 진행/완료/필요 확인 |
| 미승인 candidate 중복 기술 검토 | `docs/plans/pending-candidate-identity-grouping-decisions.md` · `docs/plans/README.md` | 현 compare의 canonical-only 공백을 확인. 화면만 그룹/관계 저장/그룹 승인/물리 병합 4안을 비교하고 C(영속 identity group+그룹 승인)를 권장 | 출처 손실·canonical 오염을 막으며 owner-level 전이 계약을 임의로 고르지 않음 |
| 정본/변경 기록 | `docs/system-contract-sot.md` v1.8.15 · `final-save-analysis-decisions.md` · `frontend-review-inbox-decisions.md` · `CHANGELOG.md` · `HANDOFF.md` | dogfood 요구와 구현 경계, 중복 그룹 결정 대기를 정본에 반영 | 종전 “list에 payload 없음” 결정을 명시적으로 dogfood 개정 |
| 독립 검증 P0·가드 보강 | `routers/drafts.py` · `test_chapter_hierarchy.py` · `DraftEditor.tsx/test` · `ReviewInbox.test.tsx` | flat payload의 계약 밖 `latest_snapshot_id` 제거. nested exact job의 snapshot/status 값 단정. 첫 저장 전 finalize running 우선순위와 event/question payload 렌더 셀 추가 | 장면 생성·flat 목록·에디터 로드의 response validation 500을 제거하고 검증자가 찾은 무셀/코너 케이스를 잠금 |
| 미승인 후보 정체성 그룹 C 확정 | `docs/plans/pending-candidate-identity-grouping-decisions.md` · `docs/system-contract-sot.md` | 브리프 상태를 “C 채택”으로 확정하고 SoT v1.8.16에 영속 identity group + 그룹 승인/거절 정책을 등재 | 후보 목록 중복 표시와 승인 후 canonical 중복 방지를 같은 설계로 닫는 방향 확정 |
| Writing start-next 복구 채택 결함 폐쇄 | `api/models.py` · `routers/writing.py` · `writing/scratch*` · `writing/generation_job*` · `writing/generation_worker.py` · `writing/http_models.py` · `frontend/src/writing/*` · `frontend/src/api/*` · 회귀 | generate 요청에 `intent`/`next_unit` 추가. sync scratch·async job·worker result·scratch API가 둘을 보존. ScratchRecovery accept가 저장된 `next_unit`을 재전송. start-next generate는 provider 호출 전 next_unit binding 검증 | “다음 장면 이어쓰기” 후보가 패드/복구를 거쳐도 새 Scene을 열고, 이전 Scene 본문에 섞이지 않음 |
| start-next 검증 조건 보강 | `README.md` · `frontend/src/api/schema.d.ts` · `tests/test_writing.py` · `tests/test_writing_generation_job_mongo.py` | 조건부 합격 4건을 닫기 위해 README 정본 표기를 v1.8.16으로 갱신, `gen:api` 재생성, generate 400 경계 4분기 셀, generation_job_mongo `intent`/`next_unit` 실값 round-trip을 추가 | 검증자가 지목한 문서 red·생성물 drift·400 무셀·job Mongo 무잠금 축을 기계적으로 폐쇄 |
| 미승인 후보 identity group 구현 페이즈 계획 | `docs/plans/pending-candidate-identity-grouping-implementation-phases.md` · `docs/plans/README.md` | C 채택 구현을 저장 모델, shortlist+judge, runner 배선, Review Inbox 읽기면, 그룹 거절, 그룹 승인, grouped UI 7개 Slice로 분할 | 다음 구현을 Slice 0 저장 모델부터 작게 시작할 수 있게 착수 경계를 고정 |
| identity group 계획 하드닝 반영 | `docs/plans/pending-candidate-identity-grouping-implementation-phases.md` | 합격 검증의 비차단 4건을 계획에 반영: `contradicted` group 상태와 추이성 모순 셀, `uncertain` 표시 및 수동 해소 Deferred 트리거, `/analysis/review-inbox/groups/*` 액션 경로, Slice 4·5 operation 101·102 예상 | 브리프 Follow-up 미배정 두 건과 route/operation 착수 함정을 구현 전 문서 단계에서 폐쇄 |
| **identity group Slice 0(저장 모델과 수명) 구현** | `analysis/identity_groups.py`(신규) · `analysis/identity_groups_mongo.py`(신규) · `main.py` · `routers/admin.py`·`projects.py` · `tests/test_identity_groups.py`·`test_identity_groups_mongo.py`(신규 20셀) · purge 로스터/스파이 셀 | 세 컬렉션(그룹·멤버·관계)의 도메인·서비스·in-memory·Mongo 어댑터. 모든 unique/index 축에 `project_id`·`candidate_type` 선행. relation pair 좌우 정규화, member 재추가 멱등(`added_at` 불변), group `status open\|contradicted\|closed` 저장, `execute_project_purge` 합류(10계약/22컬렉션) | Slice 1(shortlist·판정 서비스)이 저장소 public service만으로 착수 가능. HTTP/OpenAPI 무변(HEAD 대비 dump 실측 IDENTICAL) |
| **identity group Slice 0 검증 B1 폐쇄 + 하드닝(H1~H4)** | `analysis/identity_groups.py`·`identity_groups_mongo.py` · `tests/test_identity_groups.py`·`test_identity_groups_mongo.py` · SoT v1.8.18 | **B1**: Mongo 읽기 naive datetime을 UTC 재라벨링(`_aware`, auth·core_sot와 같은 경계 정규화) + **서비스 클록 BSON ms 절단** → 실몽고 왕복이 데이터클래스 동등성 유지. 실몽고 셀은 µs≠0 클록(760724) 주입으로 `get_group`/`list_members`/`get_relation`(양 방향) 동등성을 결정적으로 단정. **H1** groups `_id`=server 생성 `group_id` 단독을 SoT에 명시 · **H2** self-pair 거절 문구화 · **H4** "member는 참조만" 기명 셀(미존재 candidate 추가 허용 — over-strict: 존재 검사를 끼우면 실패) | 검증 조건부 합격의 유일 차단 조건 폐쇄 — Slice 1 착수 가능. 변이 표 I1' 관측 오기도 정정(H3) |
| 계약 스키마 중복 전수조사 | `docs/plans/contract-schema-duplication-audit-decisions.md`(신규) · `docs/plans/README.md` · `README.md` · `HANDOFF.md` | 8개 `LlmCallSite` 호출부를 에코 호출·결정적 값 LLM 경유·호출 분산 3축으로 대조. Gate `decision`, analysis `source_anchors`, query planner `plan_id`, report bool 필드, writing 체인 context 반복을 결정 후보로 기명. `llm_call_audits`에는 프롬프트 본문이 없다는 HANDOFF 조사 재료 갭도 분리 | 코드 변경 없이 브리프 확정. 다음 구현 기준은 삭제 우선·서버 유도 후순위·KPI 의미 보존 |

## Issues found

| 문제 | 원인 | 해결 | 결과 |
|---|---|---|---|
| finalize 요청 중 상태 바가 `분석 필요`로 남음 | `finalizing` 버튼 state만 올리고 `analysisStatus`를 올리지 않았음. 또 attention 분기가 local running보다 먼저였음 | 요청 직전 running + running 표시 우선순위 보정 | deferred response 회귀가 요청 중/완료 양 방향을 잠금 |
| Chapter 목록에 표시할 status 데이터가 없음 | `_scene_payload`/`ScenePayload`가 계층 metadata 6필드만 남겨 Draft read-model의 final/analysis 축을 버림 | latest version→snapshot·`analyze:{snapshot}` job을 조회해 additive read fields 제공 | 프론트가 시간 비교 없이 snapshot identity로 판정 |
| 검토함에 후보 내용이 없음 | `_review_inbox_payload(include_detail=False)`가 payload를 명시적으로 제외 | list payload에 candidate payload additive, detail은 source/conflict 전용 역할로 유지 | 목록 즉시 판단 가능 |
| 분석을 반복하면 미승인 중복이 쌓임 | job 내 logical key dedup만 있고, job 간 pending candidate는 compare 대상이 아님 | owner decision brief 생성. 원 candidate를 합치지 않고 정체성 그룹+그룹 승인 권장 | 2번은 결정 전 미구현 |
| flat Draft 경로가 `extra_forbidden` 500 | nested Scene 상태 필드를 옮기는 중 `_draft_payload`에도 `latest_snapshot_id` 출력을 추가했으나 `DraftPayload(extra="forbid")`에는 없었음 | flat 한 줄 제거, `DraftPayload.model_validate`와 `latest_snapshot_id` 부재를 기명 셀로 고정 | flat 계약은 무변, nested Scene만 latest snapshot을 수령 |
| nested scenes 상태 값 파생이 무셀 | 기존 셀은 네 필드 존재만 확인해 `analyze:{snapshot_id}` key가 깨져도 green | 실제 latest snapshot에 exact-key running job을 만들고 snapshot/status 값을 단정 | 잘못된 lookup이면 기명 셀이 실패 |
| 첫 저장 전 finalize 진행 라벨이 `미실행` | `latestSnapshotId === null` 분기가 local `analysisRunning`보다 먼저였음 | local running을 최우선으로 이동하고 zero-version deferred 셀 추가 | 버튼과 상태 바가 요청 중 동일하게 진행 표시 |
| 다음 장면 후보가 이전 장면에 섞임 | 생성 요청·scratch·async job이 `intent`/`next_unit`을 보존하지 않아, 패드 채택이 `append_current`/`next_unit=null` accept body로 재구성됨 | generate→candidate/scratch/job→worker→scratch API→ScratchRecovery accept 전 구간에 `intent`/`next_unit`을 보존 | start-next 후보 복구 채택이 `start_next_unit`으로 서버에 도달해 새 Scene을 생성 |
| 패드의 [채택]이 동작하지 않는 것처럼 보임 | start-next 항목은 서버가 `next_unit` 없는 accept를 400으로 거절하고, UI는 항목 아래 에러만 남김 | 패드가 저장된 next-unit metadata를 전송하고, 생성 단계에서 start-next binding을 사전 검증 | 정상 항목은 저장 성공으로 `onAccepted`가 호출되고, 잘못된 요청은 생성 전에 차단 |
| HANDOFF ⑦의 감사 재료 설명이 실제 schema와 어긋남 | `StoredLlmCall`은 토큰/창/상한/결과만 저장하고 prompt body/output body를 저장하지 않는다 | 브리프에 audit material gap을 별도 결정 항목으로 분리 | 입력↔출력 에코 대조는 기존 `llm_call_audits`만으로는 불가능. 1차는 진단 캡처 표본을 권장 |

## Decisions

- 사용자는 dogfood 결과로 ① 최종 저장 분석 중/완료 확인 ② 서로 다른 분석의 같은
  인물·사건 후보 묶음·동일성 판정 ③ 검토함 목록 안 요약+즉시 승인/거절 ④ Scene
  목록 final/analysis 표시를 요구했다.
- finalize 완료 후 “리셋”은 전체 페이지 reload로 해석하지 않았다. 응답이 이미 서버의
  final/version/job 정본을 싣므로 그 값으로 state를 수렴시켜 편집 문맥을 보존했다.
- 같은 인물의 서로 다른 observation은 단순 문장 중복이 아니라 “같은 identity의 추가 근거”다.
  따라서 승인 전 candidate document 자체를 합치는 D안은 권장하지 않았다.
- 2번의 그룹 승인은 원자성·부분 실패·과금/judge 호출을 새로 정하는 owner-level fork라
  C 권장을 제시하고 구현을 멈췄다.
- 독립 검증 불합격을 확인하고 보강하라는 사용자 지시에 따라, 정본에 없는 flat 계약 확장보다
  최소 복원(출력 한 줄 제거)을 선택했다. `latest_snapshot_id`는 `ScenePayload`에만 유지한다.
- 사용자가 `pending-candidate-identity-grouping-decisions.md`의 C안을 채택한다고 확정했다.
  이에 따라 후보↔후보 중복은 영속 identity group과 그룹 승인/거절로 수렴시키며, 단순 UI
  그룹이나 후보 물리 병합은 정본 방향이 아니다.
- `start_next_unit`의 next-unit title/goal은 accept 때 갑자기 생기는 값이 아니라 generate 시점의
  사용자 선택이다. 따라서 sync 후보·async job·scratch 복구 저장소가 이를 보존하는 것이 계약이다.
- **(identity group Slice 0) 계획 문서 내부 충돌을 오너 결정으로 확정했다**: relation 필드 목록에는
  `candidate_type`이 없는데 "모든 unique/index 축에 포함" 문장은 전부 포함을 요구한다. 물어본 결과
  **relation에 `candidate_type`을 더해 상위집합으로** 가기로 했다(2026-09-02, 대안: 필드 목록
  그대로 두고 축 문장을 느슨하게 읽기). 구현 중 유도된 나머지 리터럴은 Slice 0 완료 기록에
  남겼다(`member_status` 초기값 `active`·`revision` 0 시작·relation 재기록 upsert에 `created_at`
  첫 판정 유지).
- **(identity group Slice 0) "candidate purge"는 현재 코드에 없는 경로다** — 후보 문서를 hard delete
  하는 곳은 project purge(`analysis.purge_project`)뿐이므로, 계획의 "candidate purge/project purge
  고아 없음"은 identity store의 `purge_project` 한 벌로 닫힌다. 후보 단위 파기 경로가 생기면 그때
  `purge_candidate`를 별도 슬라이스로 연다.
- **(계약 스키마 중복 조사) 코드는 바꾸지 않고 결정 브리프를 먼저 둔다.** Gate `decision` 제거,
  analysis anchor 축소, prompt body 감사 저장은 모두 계약/관측 정책 변경이라 오너 선택 전 구현하지
  않는다. 권장은 서버 유도 + mismatch 관측(B)이고, 호출 재배치는 dogfood token 표본 뒤 별도 slice로 연다.
- **(계약 스키마 중복 조사) 오너가 브리프 기준을 확정했다**: 불필요 schema는 삭제 우선, 삭제가
  맞지 않고 서버 유도가 가능하면 서버 유도 후순위 선, id값도 서버 통제 가능하면 제외 대상,
  모든 변경은 KPI 의미에 영향 없음이 gate다. 호출 재배치는 확인 뒤 필요하면 곧바로 구현 후보로
  올리되, 실제 작업은 다른 날 한다.

## Verification

- 프론트 관련 3파일 집중 회귀 → **86 passed**: Review Inbox payload 표시·즉시 액션,
  Scene final/analysis 상태(최종 저장 후 수정의 over-strict 방향 포함), finalize in-flight
  `분석 진행 중`→완료 양방향을 포함한다.
- Chapter API + 문서 인덱스/링크 + OpenAPI schema 조각 → **15 passed, 279 subtests passed**.
- `npm run gen:api` 성공, `npx tsc --noEmit` 성공, `npm run build` 성공,
  `git diff --check` 성공.
- Review Inbox API의 기존 통합 셀
  `ReviewInboxApiTest::test_list_unifies_candidate_with_open_conflict`는 두 차례 각각
  180초/50초 timeout. faulthandler에서 변경한 inbox GET/assertion 전이 아니라 `_build()`의
  project 생성 POST(`tests/test_analysis_apply_api.py:115`)에서 anyio queue wait로 멈춤을 확인했다.
  따라서 새 list payload assertion은 이 환경에서 실행 완료되지 않았으며, 제품 코드 실패로
  오인하지 않되 후속 독립 검증에서 다시 돌린다.
- 결함 패턴 sweep: top-level Draft read-model에는 이미 final/analysis snapshot 필드가 있었고
  Chapter nested `_scene_payload` 한 곳만 누락돼 있었다. 해당 원행 blame은 계층화 도입
  `54192679`이며, 같은 snapshot identity 판정을 nested payload에도 맞췄다.
- 독립 검증 보강 후 `tests/test_chapter_hierarchy.py` → **18 passed, 4 subtests passed**,
  프론트 관련 3파일 → **88 passed**.
- 최종 복원 후 Chapter+문서 인덱스 → **31 passed, 284 subtests passed**,
  `npm run build` → **711 modules**, `git diff --check` 성공.
- P0 수정 전 신규 셀은 `DraftPayload latest_snapshot_id extra_forbidden`으로 **1 failed**,
  수정 후 **1 passed**로 전환했다.
- broader TestClient 재실행 명령은
  `timeout 240s python3 -m pytest -q tests/test_scene_notes_api.py tests/test_final_save_analysis.py tests/test_analysis_apply_api.py tests/test_chapter_hierarchy.py`이며,
  이 세션에서는 첫 project 생성 POST에서 무출력 대기해 중단했다. 분리 진단
  `timeout 50s python3 -m pytest -vv -s -o faulthandler_timeout=20 tests/test_scene_notes_api.py`도
  첫 셀 `setUp`의 `tests/test_scene_notes_api.py:74` → Starlette TestClient
  `anyio.from_thread` 대기로 timeout(124)했다. 독립 검증자의 같은 호스트 green과 상충하므로
  제품 실패나 성공으로 환산하지 않고 재검증 대상으로 남긴다.
- 최초 작업의 **15 passed, 279 subtests** 명령은
  `python3 -m pytest -q tests/test_chapter_hierarchy.py::ChapterHierarchyApiTest::test_create_list_and_parent_scoped_reorder tests/test_docs_indexes.py tests/test_project_brief.py::WorkspaceW0SchemaIntegrationTest::test_openapi_components_match_w0_fragments`였다.
  검증 기록이 지적한 재현 명령 누락을 보완한다.

## Verification — start-next verifier conditions

- 조건 ① README 정본 표기: `docs/system-contract-sot.md` 현재 버전과 맞춰 `README.md`를
  **v1.8.16**으로 갱신했다.
- 조건 ② OpenAPI 생성물: `cd frontend && npm run gen:api`로 `schema.d.ts`를 재생성해
  수동 drift를 제거했다.
- 조건 ③ 400 경계: `WritingGenerateApiTest::test_start_next_intent_binding_rejects_invalid_pairs_before_provider`
  에서 append+next_unit, start missing next_unit, blank title, blank goal 네 분기를 모두
  400/detail/provider 미호출로 잠갔다.
- 조건 ④ generation_job_mongo 신규 필드: round-trip fixture가 `intent="start_next_unit"`와
  `next_unit={"title": ..., "goal": ...}` 실값을 넣어 `_doc`/`_entry` 어느 한쪽의 필드 유실도
  실패하게 했다.
- 재현:
  `python3 -m pytest -q tests/test_docs_indexes.py` → **13 passed, 282 subtests**.
  `python3 -m unittest tests.test_writing.WritingGenerateApiTest tests.test_writing_generation_job_mongo.MongoWritingGenerationJobRepositoryTest`
  → **22 tests OK**.
  `python3 -m unittest tests.test_writing_scratch tests.test_writing_generation_job tests.test_writing_generation_worker tests.test_writing tests.test_writing_revise`
  → **192 tests OK**.
  `python3 -m unittest tests.test_writing_generation_job_mongo` → **14 tests OK**.
  `npm test -- --run src/writing/WritingPanel.test.tsx src/writing/ScratchRecovery.test.tsx`
  → **72 passed**.
  `npm run build` → **711 modules**, 성공.
  `git diff --check` → 성공.

### Mutation checks after checkpoint `61cd7a1`

| 변이 | 적용 diff | 재실패 셀 | 결과 |
|---|---|---|---|
| M8 flat 계약 회귀 | `routers/drafts.py::_draft_payload`에 `"latest_snapshot_id": None if latest is None else latest.snapshot_id` 재삽입 | `ChapterHierarchyApiTest::test_flat_contract_and_nested_analysis_values` | `DraftPayload extra_forbidden`, 1 failed |
| M9 nested lookup 파손 | `_scene_payload`의 `analyze:`를 `analyze-broken:`로 교체 | 같은 셀 | `analysis_snapshot_id: None != source-snapshot-1`, 1 failed |
| M10 zero-version 우선순위 회귀 | `analysisLabel`에서 `latestSnapshotId === null`을 `analysisRunning`보다 앞으로 이동 | `저장본이 없는 첫 최종 저장도 요청 중에는 분석 진행으로 표시한다` | `분석 진행 중` 부재·`미실행` 관측, 1 failed |
| M11 payload 라벨 제거 | `PAYLOAD_FIELD_LABELS`의 `event`·`question` 두 행 삭제 | `renders event and open-question summaries inside their list rows` | 사건 라벨 2개 기대→1개, 1 failed |

## Verification — start-next scratch recovery

- Python 컴파일:
  `python3 -m py_compile services/application/app/api/models.py services/application/app/routers/writing.py services/application/app/writing/scratch.py services/application/app/writing/scratch_mongo.py services/application/app/writing/generation_job.py services/application/app/writing/generation_job_mongo.py services/application/app/writing/generation_worker.py services/application/app/writing/http_models.py` → 통과.
- Python 집중 회귀:
  `python3 -m unittest tests.test_writing_scratch tests.test_writing_generation_job tests.test_writing_generation_worker tests.test_writing tests.test_writing_revise` → **191 tests OK**.
- 프론트 집중 회귀:
  `npm test -- --run src/writing/WritingPanel.test.tsx src/writing/ScratchRecovery.test.tsx` → **72 tests passed**.
- 프론트 타입/빌드:
  `npm run build` → `tsc --noEmit` + Vite build 통과.
- `git diff --check` → 통과.
- 패턴 스윕:
  `rg -n "intent: entry.intent|next_unit: null|intent=job.intent|writing_scratch.save\\(|scratch.save\\(|WritingRequest\\(" services frontend/src tests ...`
  로 generate/scratch/job/worker 외 유사 누락을 확인. 남은 `WritingRequest(...)` 직접 호출은 테스트·gate/revise의 기본 append 경로라 이번 결함의 start-next 복구 경로와 무관.

각 변이 전 checkpoint+clean gate를 확인했고, 변이마다 `git checkout -- <path>` 복원 후
`git status --short` 0줄을 확인했다.

## Verification — identity group Slice 0

- 테스트 먼저 → 최소 구현 → focused → broader → commit(`183af60`) → 변이 → 복원 순서로 진행했다.
- Python 컴파일: 신규/수정 모듈 `python3 -m py_compile` 통과.
- Focused: `PYTHONPATH=. pytest tests/test_identity_groups.py tests/test_identity_groups_mongo.py`
  → **20 passed**(도메인 14 · Mongo fake 5 · 실몽고 round-trip 1 — test-mongo rs-test 기동 중 실측).
- Purge 그래프: `test_purge_project_coverage`(로스터 10) · `test_owner_project_purge` ·
  `test_draft_purge` · `test_purge_reconciler` → **29 passed**. `test_auth_api` 전체 →
  **132 passed / 999 subtests**(admin purge 스파이 포함).
- **OpenAPI 무변 실측**: `scripts/dump_openapi.py` 출력을 HEAD(stash) 대비 diff → **IDENTICAL**
  (`schema.d.ts` 재생성 불요 — 이 Slice는 HTTP 표면이 없다).
- 전수(베타, test-mongo ON): **2696 passed / 1 skipped / 3124 subtests, exit 0**.
  검산: HEAD 컬렉션 실측 2677 → working tree 2697 = **순수 +20셀**(신규 두 파일 전부).
  skip 1은 이 머신 관례(ES 패키지 탑재).
- 변이 9종(각각 기명 재실패 확인 후 `git checkout --` 복원, 트리 clean 확인):

| 변이 | 내용 | 재실패 셀 | 관측 |
|---|---|---|---|
| I1 pair 정규화 제거 | `normalize_relation_pair` 정렬 분기 제거 | `test_relation_pair_is_normalized_across_directions`·`test_relation_round_trip` | 2 failed |
| I1' 정규화 제거(실몽고) | 같은 변이로 실몽고 셀 | `MongoCandidateIdentityGroupLiveRoundTripTest::test_round_trip_isolation_and_purge` | ~~unique 인덱스 위반~~ → **정정(2026-09-02 검증 H3)**: 실측 재실패 메커니즘은 len 단얫 2 != 1 — (b,a)는 (a,b)와 **다른 인덱스 키**라 유일성 위반이 아니라 별도 행으로 쌓인다. 가드는 유효(관측 서술만 오기). 1 failed |
| I2 member 멱등 제거 | 기존 행 short-circuit 제거 | `test_add_member_is_idempotent` | 1 failed |
| I3 created_at 보존 제거 | 재기록마다 clock | `test_relation_pair_is_normalized_across_directions` | 1 failed |
| I4 project 격리 제거 | `get_group` 프로젝트 비교 제거 | `test_get_group_is_project_scoped`·`test_set_group_status_is_project_scoped` | 2 failed |
| I5 member type 가드 제거 | 그룹 type 불일치 검사 제거 | `test_add_member_rejects_missing_group_and_type_mismatch` | 1 failed |
| I6 상태 저장 제거 | `set_group_status`가 save 생략 | `test_group_status_round_trip_including_contradicted` | 1 failed |
| I7 purge 호출 누락 | `execute_project_purge`에서 identity purge 제거 | 소유자 purge 그래프 셀·`test_admin_purge_fans_out_to_derived_services` | 2 failed |
| I8 unique 축 type 제거 | member unique 인덱스에서 `candidate_type` 제거 | `test_installs_indexes_with_stable_names_and_scoped_axes` | 1 failed(과잉 방향) |

- 복원 후 focused 재실행 **20 passed**, `git status --short` 코드 0줄(문서만 남음) 확인.

## Verification — identity group Slice 0 검증 보강(B1 폐쇄)

- 독립 검증(`verifications/2026-09-02/identity_group_slice_0.md`, 조건부 합격)의 차단 B1과
  비차단 H1~H4를 오너 지시로 폐쇄했다. 착수 전 red 실측: 보강 단얫을 넣은 라이브 셀이 현재
  구현에서 실패(315행 `get_group == group` — naive tzinfo·µs 잘림) → 정규화+절단 구현 → green.
- Focused: `PYTHONPATH=. pytest tests/test_identity_groups.py tests/test_identity_groups_mongo.py`
  → **21 passed**(신규 H4 셀 +1, 실몽고 충실도는 기존 셀 강화로 셀 수 무변).
- Purge 그래프 broader: `test_owner_project_purge`·`AdminProjectPurgeTest`·
  `test_purge_project_coverage` → **27 passed / 2 subtests**.
- 변이 2종(B1 양방향, 기명 재실패 후 복원·트리 clean 확인):

| 변이 | 내용 | 재실패 셀 | 관측 |
|---|---|---|---|
| J1 `_aware` 제거 | naive 통과 | 라이브 `test_round_trip_isolation_and_purge` | tzinfo 불일치로 `==` False, 1 failed |
| J2 ms 절단 제거 | 서비스 클록 raw 통과 | 같은 셀 | µs 760724↔760000 잘림으로 `==` False, 1 failed |

- H3 정정: 위 변이 표 I1' 행의 관측 문구("unique 인덱스 위반")를 실측(len 단얫 2 != 1)으로
  교체했고, 라이브 셀의 293-294행 주석도 같은 오기라 정정했다.
- OpenAPI는 이번에도 무변(라우트 무변 — dump 대상 경로 변화 없음).

## Verification — 계약 스키마 중복 전수조사

- HANDOFF ⑦과 SoT v1.8.18의 LLM 관측 계약을 읽고, `LlmCallSite` 8종과 조립 배선을 `rg`/Serena로
  대조했다.
- 각 호출부의 prompt builder/parser를 확인했다: `analysis_extractor`, `compare_judge`,
  `query_planner`, `writing_generation`, `writing_gate`, `writing_retrieval_planner`,
  `writing_revision`, `writing_report`.
- 문서 인덱스에 브리프를 등재했다. 첫 `tests.test_docs_indexes` 실행은 계획/브리프 카운트
  `117/97`이 `118/98`로 늘어난 것을 잡아 실패했고, `README.md`와 `docs/plans/README.md`의
  카운트를 갱신했다. 코드와 public OpenAPI/`schema.d.ts`는 변경하지 않았다.
- 오너 확정 기준 반영 뒤 `tests.test_docs_indexes`와 `git diff --check`를 재실행했다.

## Next steps

1. start-next 검증 조건 폐쇄 재검증은 완료됐다(합격, `a57b380`).
2. identity group은 **Slice 0 완료 + 검증 B1 폐쇄(2026-09-02, SoT v1.8.18)** — Slice 1 착수
   보류 사유가 사라졌다. 다음은 `pending-candidate-identity-grouping-implementation-phases.md`의
   **Slice 1(shortlist와 판정 서비스)**. 저장소 public service만 사용하고, fake judge로
   `same`→member 연결·추이성 모순 `contradicted` 전이를 잠근다.
3. 각 Slice가 끝날 때 독립 검증을 받고, grouped Inbox UI 이후 실 dogfood로 상태·목록 가독성을 육안 확인한다.
4. 계약 스키마 중복 브리프는 확정됐다. 다음 구현일의 기준은 삭제 우선 → 서버 유도 후순위 →
   현행 유지 최후순위이며, id류도 서버 통제 가능하면 제외한다. KPI 의미를 바꾸지 않아야 하고,
   호출 재배치는 확인 뒤 필요하면 곧바로 구현 후보로 올린다.
