# Writing Workspace V2 W0 계약과 migration

> **2026-08-28 supersession:** §2의 평면 ordered unit, §3의 `next_unit.unit_kind`,
> §5의 `chapter→scene parent/child tree` 유예, §6의 unit_kind별 heading 미사용은
> [`chapter-scene-hierarchy-decisions.md`](chapter-scene-hierarchy-decisions.md)의 확정 계약으로
> 폐기됐다. 새 정본은 별도 Chapter + Scene(Draft), parent별 연속 순열, 같은 장의 다음 Scene,
> 계층 export다. 아래 기존 절은 v1.7.9~v1.7.17 구현 이력과 이관 전 계약을 설명하기 위해 보존한다.

상태: `Approved — W0~W4 구현 완료 (matrix PB/OU/WI/SC/EX 전부 채움)`

정본 버전: `system-contract-sot.md` v1.7.17

근거: 오너 승인 D1=A, D2=A, D3=C, D4=A, D5=A, D6=A, 전체 접근=C

기계 판독 schema: [`../../schemas/writing-workspace-v2-w0.schema.json`](../../schemas/writing-workspace-v2-w0.schema.json). 이 파일은 catalog이므로 request/response schema로 root 전체를 참조하지 않고 반드시 `#/$defs/...` fragment를 소비한다.

## 범위와 선행 관계

W0는 W1~W4가 소비할 public/data/migration 계약을 잠그는 문서 slice다. runtime API, Mongo collection, migration runner, frontend는 이 문서에서 구현하지 않는다.

- W1은 아래 의미를 바꾸지 않고 editor/right rail/source jump만 구현한다.
- W2가 `ProjectBrief` persistence/API/context/overview를 구현한다.
- W3가 ordered unit/reorder/migration과 두 Writing intent를 구현한다.
- W4가 ordered latest export와 manifest를 구현한다.
- W1~W4 구현은 이 계약의 named regression matrix에서 자기 slice에 해당하는 모든 행을 채워야 한다.
- W2/W3는 OpenAPI/Pydantic 모델이 catalog root가 아니라 대응 `$defs`와 같은 exact boundary를 노출하는지 schema integration 회귀로 잠근다.
- W1/W3의 active-only UI는 archived Draft가 차지한 내부 `position`을 화면의 연속 ordinal로 그대로 표시하지 않는다. 보관 원고 때문에 사용자에게 보이는 번호가 건너뛰지 않도록 visible ordinal과 canonical position을 구분한다.

## 1. `ProjectBrief` exact contract

### 1.1 정본과 version

`ProjectBrief`는 project 1:1 논리 정본이며 실제 저장은 append-only `ProjectBriefVersion`이다. 별도 mutable current document를 두지 않고 가장 큰 `version_number`가 current다.

| 필드 | public type | 규칙 |
|---|---|---|
| `id` | string | immutable brief version id |
| `project_id` | string | path project와 exact match |
| `version_number` | integer | project별 1부터 연속 증가 |
| `premise` | string \| null | optional, nonblank when string |
| `genre` | string \| null | optional, nonblank when string |
| `tone` | string \| null | optional, nonblank when string |
| `pov` | string \| null | optional, nonblank when string |
| `constraints` | string[] | ordered, 각 원소 nonblank, 중복 금지; empty 허용 |
| `style_rules` | string[] | ordered, 각 원소 nonblank, 중복 금지; empty 허용 (v1.7.21) |
| `preferred_patterns` | string[] | ordered, 각 원소 nonblank, 중복 금지; empty 허용 (v1.7.21) |
| `forbidden_patterns` | string[] | ordered, 각 원소 nonblank, 중복 금지; empty 허용 (v1.7.21) |
| `style_examples` | string[] | ordered 자유 텍스트 예시, 각 원소 nonblank, 중복 금지; empty 허용 (v1.7.21) |

저장 문서는 public 필드와 내부 `idempotency_key`를 가진다. `idempotency_key`는 read response에 노출하지 않는다. timestamp, character/event, synopsis, status, completion score는 W0 schema가 아니다.

HTTP 경계는 string의 바깥 whitespace를 제거한다. optional scalar는 client가 값 없음에 `null`을 명시하며 whitespace-only string은 422다. `constraints`와 네 문체 배열도 각 원소를 trim한 뒤 blank/duplicate면 422다. content의 key 생략과 unknown key는 422다. JSON Schema의 `uniqueItems`는 전처리 전 raw array 중복만 표현하므로 `["a"," a"]` 같은 trim 후 중복의 422 authority는 HTTP validator다. Schema와 runtime validator는 모순이 아니라 각각 구조와 정규화 후 의미 검증을 담당한다.

`style_examples`의 runtime 상한은 write request에만 적용한다(기본 최대 3개·항목당 1,000자, env 조정). append-only 과거 version의 current/history/detail **read response에는 현재 runtime 상한을 적용하지 않는다**. 운영자가 상한을 낮춰도 이미 저장된 예시를 읽을 수 있어야 하며, 이 read 경계는 response model에 write validator를 대칭 복사하지 않는 것으로 구현한다.

### 1.2 API와 exact envelope

| Method/path | request | response/outcome |
|---|---|---|
| `GET /projects/{project_id}/brief` | 없음 | `200 {"brief": ProjectBriefVersion|null}`. project가 있으나 아직 version이 없으면 `brief=null`; project 없음/cross-project는 404 |
| `PUT /projects/{project_id}/brief` | `{base_version_id:string|null,idempotency_key:string,premise:string|null,genre:string|null,tone:string|null,pov:string|null,constraints:string[],style_rules:string[],preferred_patterns:string[],forbidden_patterns:string[],style_examples:string[]}` | `200 {"brief":ProjectBriefVersion,"idempotent_replay":bool}` |
| `GET /projects/{project_id}/brief/versions` | 없음 | `200 {"versions":ProjectBriefVersion[]}` version_number 오름차순 |
| `GET /projects/{project_id}/brief/versions/{version_id}` | 없음 | `200 {"brief":ProjectBriefVersion}`; 없음/cross-project 404 |

첫 PUT은 `base_version_id=null`만 허용한다. version이 이미 있는데 null이거나, base가 current가 아니면 409다. 같은 `(project_id,idempotency_key)` replay는 base stale 검사/provider 호출/version 생성 없이 최초 version을 반환한다. 다른 key는 current base를 요구하고 다음 version을 만든다. write는 active project만 허용하며 archived project는 409다.

별도 DELETE/hard delete는 없다. 모든 scalar 값 `null` + `constraints=[]` + 네 문체 배열 `[]`인 version이 “비어 있음/온보딩 건너뜀/내용 지움”을 표현하고 과거 version은 보존한다. 따라서 W2의 “CRUD”는 create/read/versioned replace/clear이며 정본 삭제를 뜻하지 않는다. W2 UI는 이를 “작품 정보 지우기(이력 보존)”로 설명하고 hard delete처럼 표현하지 않는다.

## 2. ordered unit과 migration

### 2.1 Draft 확장

기존 Draft public/persistence shape에 다음 required field를 더한다.

- `unit_kind`: exact enum `chapter|scene|other`
- `position`: boolean이 아닌 integer, `>=1`

한 project의 archived 포함 모든 Draft는 `position`이 unique하고 정확히 `1..N`의 연속 순열이어야 한다. `GET /projects/{project_id}/drafts`는 `position` 오름차순으로 반환한다. archive는 position을 제거하거나 재번호화하지 않는다. 일반 `POST .../drafts`는 `unit_kind`를 받되 생략 시 호환 기본값 `other`, position은 서버가 `N+1`로 정한다.

### 2.2 reorder API

`PUT /projects/{project_id}/draft-order`

- request: `{ordered_draft_ids:string[]}`
- response: `{drafts:Draft[]}`
- request는 archived 포함 현재 project의 Draft id 전체를 정확히 한 번씩 포함하는 완전 순열이어야 한다.
- 누락, 중복, foreign/unknown id, 요청 평가 중 Draft 집합 변경은 409이며 write 0건이다.
- 성공 시 배열 순서대로 position `1..N`을 한 Core SOT transaction에서 교체한다.
- 같은 완전 순열의 반복 PUT은 별도 version/write를 만들지 않는 자연 멱등이며 같은 response를 반환한다.
- archived project는 409, missing project는 404다.

부분 move API, fractional/gapped position, title에서 순서 파싱, chapter→scene nesting은 열지 않는다.

### 2.3 기존 데이터 migration

migration은 W3 배포 전에 명시적으로 실행하는 idempotent one-shot이다. read-time lazy default는 사용하지 않는다.

1. project별 기존 Draft를 **현재 repository list 순서**로 읽는다. Mongo의 현재 구현은 `_id` 오름차순이고 애플리케이션 발급 ObjectId가 생성 순서를 보존하며, in-memory는 삽입 순서다. 정본 선례는 `test_lists_preserve_creation_order`가 잠근 **list 결과의 생성 순서**다. 향후 id 체계를 바꾸면 `_id` 가정에 기대지 말고 이 행동 계약을 보존하거나 별도 migration-order source를 먼저 계약한다.
2. 순서대로 `unit_kind=other`, `position=1..N`을 부여한다. archived Draft도 같은 순열에 포함한다. W3 UI는 migration 직후 legacy `other`를 오류로 보지 않고 chapter/scene 재분류를 선택적으로 안내한다.
3. migration은 application write를 받지 않는 maintenance window에서 단일 runner로 실행한다. 동시 migration과 migration 중 Draft create/reorder/archive는 허용하지 않는다.
4. project 단위 transaction으로 전부 기록한다. 모든 project가 성공한 뒤에만 unique index `(project_id,position)`을 설치한다. 한 project라도 실패하면 index를 설치하지 않고 non-zero로 종료하며, 이미 성공한 project는 다음 실행에서 valid no-op으로 재사용한다.
5. 모든 Draft가 field 없음이면 migration, 모두 valid면 no-op이다. missing/present 혼합, unknown kind, duplicate/gapped position은 부분 보정하지 않고 project 전체를 fail-closed한다.
6. 실패한 project는 write 0건이고 다른 project의 성공 여부와 구분해 보고한다. 정상 Docker runtime은 transaction을 요구한다. non-transaction fallback은 SoT v1.4의 single-writer 제한을 그대로 적용하며 local/test에서만 허용한다. 선택한 구현은 project 전체 before-image 복원 또는 commit marker-last를 failure-injection 회귀로 증명하고, 정상 fallback 성공도 과잉 rollback 없이 순서를 commit하는지 반대 방향으로 잠근다.

migration 뒤 기존 단일 draft edit/save/history/single-version export와 `continue_scene` flow의 id/version/snapshot/body는 변하지 않는다. migration은 Draft metadata만 보강한다.

## 3. Writing intent와 accept

### 3.1 discriminator와 호환

public literal은 `intent=append_current|start_next_unit`이다. 기존 client가 `intent`를 생략하면 `append_current`, `next_unit`을 생략하면 `null`로 해석해 현재 `continue_scene`/`draft_patch` 동작을 보존한다. 새 client는 두 key를 명시한다.

- `append_current`: `next_unit=null`; 현 `draft_id/base_version_id` latest에 결정적 paragraph append.
- `start_next_unit`: `next_unit={title,unit_kind,goal}` 필수. `title` nonblank, `unit_kind=chapter|scene|other`, `goal`은 optional nonblank string/null이다.

`intent`는 generate/gate/report/revise-and-gate/accept의 같은 request identity에 포함되고 WritingCandidate가 exact `intent`와 `next_unit`을 echo한다. server context assembler와 prompt가 구조화 값을 소비하되 prompt는 target을 재결정하지 않는다. 두 intent 모두 기존 `task_type=continue_scene`, `output_type=draft_patch`를 유지한다. 저장 target 의미는 오직 `intent`가 소유한다.

append에서 non-null `next_unit`, start에서 missing/null `next_unit`, candidate와 accept의 intent/next_unit/request_id/project 불일치는 provider 또는 write 전에 400이다.

### 3.2 accept 효과

두 intent 모두 current `draft_id`와 `base_version_id`가 같은 project의 active latest여야 한다. Gate를 서버에서 다시 평가해 `pass`일 때만 저장하며 non-pass는 기존처럼 `200 accepted=false`, write 0건이다.

`append_current`는 기존 계약을 그대로 사용한다.

- candidate 외곽 whitespace를 strip한다.
- base가 empty면 candidate만, base가 newline으로 끝나면 exact concat, 그 외 `\n\n` separator 뒤 append한다.
- save key는 `writing-accept:{idempotency_key}`다.

`start_next_unit`은 candidate 외곽 whitespace를 strip한 값 전체를 새 unit의 첫 snapshot raw text로 쓴다.

1. current unit 뒤의 모든 position을 +1 한다(archived 포함).
2. `next_unit.title/unit_kind`로 새 active Draft를 current position+1에 만든다. `goal`은 generation 입력이며 Draft/본문에 저장하지 않는다.
3. 새 Draft의 version 1, immutable snapshot, blocks를 만든다.
4. accept receipt와 위 Core SOT write set을 한 transaction에서 commit한다.

transaction 실패는 position 이동, Draft, version, snapshot, block, receipt 모두 0건이어야 한다. 이 여섯 표면은 현재 append의 기존 3-surface transaction을 기술하는 문장이 아니라 **W3가 start-next path에 구현해야 할 신규 원자 범위**다. Analysis job은 기존 독립 저장소 경계를 유지해 Core SOT commit 뒤 새 snapshot key `analyze:{snapshot_id}`로 생성한다. job 생성 실패는 두 intent 모두 기존과 같은 `502 partial-success`이며 committed target을 숨기지 않고 replay로 같은 job 생성에 수렴한다.

### 3.3 idempotency와 response

accept receipt identity는 `(project_id,"writing-accept:{idempotency_key}")`다. replay lookup은 stale base/Gate보다 먼저 일어나며 최초 결과의 intent와 target을 반환한다. client는 현재 C1 선례대로 key를 exact accept body에서 파생해 body 변경 시 새 key를 사용한다.

- 같은 key replay: 같은 target Draft/version/snapshot/position, Gate/Core SOT side effect 중복 0.
- 다른 key: 별도 사용자 intent. start는 새 next unit을 만들 수 있다.
- append의 기존 save-key-only record는 receipt migration 없이 계속 replay 가능해야 한다. W3 구현은 이를 read-through해 동일 response를 구성한다.

accepted response는 exact top-level `{accepted,intent,gate,saved,analysis_job,idempotent_replay}`다. `saved`가 있으면 `{draft_id,draft_version_id,version_number,snapshot_id,content_hash,unit_kind,position}`다. append도 target Draft의 kind/position을 채운다. Gate non-pass는 `saved=null`, `analysis_job=null`; Analysis partial은 기존처럼 `accepted=true`, `intent`, non-null `saved`, `analysis_job=null`, `analysis_error`를 가진다.

## 4. named bidirectional regression matrix

아래 이름은 W2/W3 구현 때 만들 test node의 canonical 이름이다. `should fire`는 under-strict, `should NOT fire`는 over-strict guard다. 한 행도 구현 없이 완료 처리하지 않는다.

| ID | direction | contract branch | required named regression |
|---|---|---|---|
| PB-01 | fire | 최초 null base PUT이 version 1 생성 | `ProjectBriefContractTest::test_first_put_creates_version_one` |
| PB-02 | not fire | brief 없음 GET은 project 404가 아니라 `brief=null` | `ProjectBriefApiTest::test_existing_project_without_brief_returns_null` |
| PB-03 | fire | current base+새 key가 다음 append-only version 생성 | `ProjectBriefContractTest::test_current_base_creates_next_version` |
| PB-04 | not fire | stale/null base는 기존 version을 바꾸지 않고 409 | `ProjectBriefApiTest::test_stale_base_rejected_without_write` |
| PB-05 | fire | same key replay는 같은 version, duplicate 0 | `ProjectBriefContractTest::test_same_key_replays_original_version` |
| PB-06 | not fire | 다른 key는 replay로 오인하지 않고 새 version | `ProjectBriefContractTest::test_different_key_creates_distinct_version` |
| PB-07 | fire | optional scalar/5개 배열 trim과 exact public keys | `ProjectBriefApiTest::test_put_normalizes_and_returns_exact_envelope` |
| PB-08 | not fire | blank/duplicate 배열·unknown/missing key·예시 write 상한 위반은 422/write 0 | `ProjectBriefApiTest::test_invalid_content_rejected_without_write` |
| PB-09 | fire | all-null/empty version은 clear하되 history 보존 | `ProjectBriefContractTest::test_empty_version_clears_current_and_preserves_history` |
| PB-10 | not fire | cross-project version read 미노출 | `ProjectBriefApiTest::test_version_read_is_project_isolated` |
| PB-11 | not fire | archived project PUT은 409, GET/history는 유지 | `ProjectBriefApiTest::test_archived_project_blocks_write_but_allows_read` |
| PB-12 | not fire | missing/cross-project current brief GET은 null로 위장하지 않고 404 | `ProjectBriefApiTest::test_current_brief_read_is_project_isolated` |
| PB-13 | not fire | runtime 예시 상한 하향은 기존 current/history/detail read를 거부하지 않음 | `ProjectBriefApiTest::test_lowered_style_example_limits_do_not_break_existing_reads` |
| OU-01 | fire | legacy creation order→other/1..N(archived 포함) | `OrderedUnitMigrationTest::test_legacy_drafts_migrate_in_repository_order` |
| OU-02 | not fire | valid migrated project rerun은 byte-for-byte no-op | `OrderedUnitMigrationTest::test_valid_project_rerun_is_noop` |
| OU-03 | fire | mixed/duplicate/gapped/unknown은 fail-closed | `OrderedUnitMigrationTest::test_invalid_partial_state_fails_without_write` |
| OU-04 | not fire | migration은 versions/snapshots/body/id를 변경하지 않음 | `OrderedUnitMigrationTest::test_migration_preserves_existing_draft_artifacts` |
| OU-05 | fire | create는 requested/default kind와 N+1 부여 | `OrderedUnitContractTest::test_create_appends_ordered_unit` |
| OU-06 | not fire | bool/zero/unknown kind는 저장 불가 | `OrderedUnitApiTest::test_invalid_unit_metadata_rejected` |
| OU-07 | fire | full permutation reorder가 exact 1..N으로 원자 반영 | `OrderedUnitContractTest::test_full_permutation_reorders_atomically` |
| OU-08 | not fire | missing/duplicate/foreign/unknown id는 409/write 0 | `OrderedUnitApiTest::test_invalid_permutation_rejected_without_write` |
| OU-09 | not fire | 같은 permutation 반복은 추가 mutation 없음 | `OrderedUnitContractTest::test_same_permutation_is_naturally_idempotent` |
| OU-10 | not fire | archive가 position을 재번호화하지 않음 | `OrderedUnitContractTest::test_archive_preserves_total_order` |
| OU-11 | not fire | archived project reorder는 409/write 0 | `OrderedUnitApiTest::test_archived_project_reorder_rejected_without_write` |
| OU-12 | not fire | missing project reorder는 404로 분리 | `OrderedUnitApiTest::test_missing_project_reorder_returns_not_found` |
| OU-13 | fire | non-transaction fallback failure가 project 전체 before-image/commit 경계를 복구 | `OrderedUnitMigrationTest::test_nontransaction_fallback_failure_leaves_no_partial_order` |
| OU-14 | not fire | 정상 non-transaction fallback은 과잉 rollback 없이 exact order commit | `OrderedUnitMigrationTest::test_nontransaction_fallback_success_commits_exact_order` |
| WI-01 | not fire | legacy intent 생략은 기존 append 결과와 동일 | `WritingIntentCompatibilityTest::test_omitted_intent_preserves_append_current` |
| WI-02 | fire | explicit append가 same draft 최신에 기존 separator 규칙 적용 | `WritingIntentAcceptTest::test_append_current_saves_same_draft` |
| WI-03 | fire | start가 current 바로 뒤 Draft+v1을 원자 생성 | `WritingIntentAcceptTest::test_start_next_unit_creates_atomic_first_version` |
| WI-04 | not fire | start가 current body/version을 수정하지 않음 | `WritingIntentAcceptTest::test_start_next_unit_preserves_current_unit` |
| WI-05 | fire | 뒤 unit(archived 포함)을 shift하고 연속 uniqueness 유지 | `WritingIntentAcceptTest::test_start_next_unit_shifts_following_positions` |
| WI-06 | not fire | intent/next_unit/candidate binding 불일치는 provider/write 전 400 | `WritingIntentApiTest::test_mismatched_intent_binding_rejected_before_provider` |
| WI-07 | not fire | stale/cross-project/archived current는 새 unit 0건 | `WritingIntentAcceptTest::test_invalid_current_target_creates_nothing` |
| WI-08 | not fire | Gate non-pass는 position/Draft/version/job 모두 0건 | `WritingIntentAcceptTest::test_nonpass_gate_has_no_start_next_side_effects` |
| WI-09 | fire | same key start replay는 same target, Gate/write 중복 0 | `WritingIntentAcceptTest::test_start_next_same_key_replays_same_unit` |
| WI-10 | not fire | different key는 별도 next-unit intent | `WritingIntentAcceptTest::test_start_next_different_key_creates_distinct_unit` |
| WI-11 | fire | injected transaction failure가 여섯 Core SOT 표면 rollback | `WritingIntentMongoTest::test_start_next_transaction_rolls_back_entire_write_set` |
| WI-12 | not fire | append transaction/response 호환이 유지됨 | `WritingIntentCompatibilityTest::test_existing_append_accept_contract_remains_green` |
| WI-13 | fire | committed start 뒤 analysis failure가 saved partial을 노출 | `WritingIntentApiTest::test_start_next_analysis_failure_returns_saved_partial` |
| WI-14 | not fire | partial replay가 unit을 중복하지 않고 same job으로 수렴 | `WritingIntentAcceptTest::test_start_next_partial_replay_converges` |
| WI-15 | fire | response exact keys와 saved target metadata 노출 | `WritingIntentApiTest::test_accept_response_exact_keys_for_both_intents` |
| WI-16 | not fire | goal은 generation context만 소비하고 Draft/body에 삽입 안 됨 | `WritingIntentAcceptTest::test_next_unit_goal_is_not_persisted_as_prose` |
| WI-17 | fire | legacy append save-key-only record를 receipt 없이 read-through replay | `WritingIntentCompatibilityTest::test_legacy_append_save_record_replays_without_receipt` |
| WI-18 | not fire | 다른 key append는 legacy replay로 오인하지 않고 다음 version 생성 | `WritingIntentCompatibilityTest::test_append_different_key_creates_next_version` |
| WI-19 | fire | same-key replay lookup이 stale base/Gate보다 우선해 provider 미호출 | `WritingIntentAcceptTest::test_replay_precedes_stale_base_and_gate` |
| WI-20 | fire | committed append 뒤 analysis failure가 exact 502 saved partial 노출 | `WritingIntentApiTest::test_append_analysis_failure_returns_saved_partial` |
| WI-21 | not fire | append partial replay가 version을 중복하지 않고 same job으로 수렴 | `WritingIntentAcceptTest::test_append_partial_replay_converges` |
| WI-22 | fire | 두 intent 모두 Analysis job key가 exact `analyze:{snapshot_id}` | `WritingIntentAcceptTest::test_both_intents_use_snapshot_scoped_analysis_key` |
| SC-01 | fire | W2/W3 OpenAPI가 각 exact `$defs`와 동형 request/response schema 노출 | `WorkspaceW0SchemaIntegrationTest::test_openapi_components_match_w0_fragments` |
| SC-02 | not fire | schema catalog root 전체를 permissive endpoint schema로 사용 금지 | `WorkspaceW0SchemaIntegrationTest::test_endpoints_do_not_reference_catalog_root` |
| EX-01 | fire | 비archived unit을 position 순으로 latest version body를 이어 붙임 | `ProjectExportContractTest::test_export_joins_ordered_latest_non_archived` |
| EX-02 | not fire | archived unit은 기본 body/manifest에서 제외 | `ProjectExportContractTest::test_archived_units_excluded_by_default` |
| EX-03 | fire | `include_archived=true`가 archived unit을 position 순으로 포함 | `ProjectExportContractTest::test_include_archived_flag_includes_archived_units` |
| EX-04 | fire | unit별 latest version 선택(과거 version 아님) | `ProjectExportContractTest::test_export_uses_latest_version_per_unit` |
| EX-05 | not fire | body에 AI metadata 미삽입, 제목 heading + verbatim body만 | `ProjectExportContractTest::test_body_has_headings_and_verbatim_bodies_only` |
| EX-06 | fire | markdown `# {title}`·txt 제목 줄, unit body는 포맷 무관 동일 | `ProjectExportContractTest::test_txt_and_markdown_heading_shapes` |
| EX-07 | not fire | version 없는 unit은 순서 변형 없이 body/manifest에서 skip | `ProjectExportContractTest::test_versionless_unit_is_skipped` |
| EX-08 | fire | manifest가 body 순서와 동형인 project/unit/version/snapshot/hash 기록 | `ProjectExportApiTest::test_manifest_records_traceability_for_included_units` |
| EX-09 | not fire | `manifest` 미요청 시 응답 manifest는 null | `ProjectExportApiTest::test_manifest_omitted_unless_requested` |
| EX-10 | not fire | unsupported format 400, missing project 404 | `ProjectExportApiTest::test_unsupported_format_and_missing_project_rejected` |
| EX-11 | not fire | archived project export는 read라 200 유지 | `ProjectExportApiTest::test_archived_project_export_survives` |
| EX-12 | fire | 응답 top-level·manifest·unit exact keys | `ProjectExportApiTest::test_export_response_exact_keys` |
| EX-13 | not fire | 내보낼 unit 0개 project는 빈 body·빈 units(합성 없음) | `ProjectExportContractTest::test_empty_project_returns_empty_body` |

## 5. Deferred / out of scope

- W0 runtime code와 UI
- chapter→scene parent/child tree
- fractional position, partial move API, collaborative ordering
- ProjectBrief character/event 자동 동기화, AI synopsis canon화
- ProjectBrief version→Draft generation provenance. W2 overview에서 실제 추적 요구가 확인되기 전 `brief_version_id`를 Draft에 추측 추가하지 않는다.
- 미채택 Writing candidate 영속
- saved publication manifest: W4의 요청 시 생성되는 **export delivery manifest**와 달리 version 선택을 저장하는 별도 정본 publication manifest를 뜻한다.
- cross-store Core SOT+Analysis transaction

## 6. W4 export exact contract (D6=A)

D6=A는 방향(ordered-latest export + 별도 delivery manifest)만 확정했고, heading separator·manifest 전달·archived 포함은 브리프가 W4로 명시 이관했다. 아래는 구현 착수 시 오너가 확정한 리터럴이다.

### 6.1 API

`GET /projects/{project_id}/export?format=txt|markdown&manifest=<bool>&include_archived=<bool>`

- `format` 미지정 기본 `txt`. `_EXPORT_FORMATS`(txt=`text/plain; charset=utf-8`, markdown=`text/markdown; charset=utf-8`)를 단일 version export와 공유한다. 지원 밖 format은 400.
- missing/cross-project는 404. archived project는 read이므로 200(export는 읽기).
- 응답 exact top-level: `{format,filename,content_type,body,project_id,include_archived,manifest}`. `filename`은 `{project_id}.{txt|md}`.

### 6.2 unit 선택과 순서

- project의 Draft를 `position` 오름차순으로 읽는다(W0 §2의 contiguous 1..N 보장 재사용).
- archived Draft는 **기본 제외**, `include_archived=true`일 때만 같은 position 순으로 포함한다(오너 결정).
- 각 unit은 **latest version**(최대 `version_number`)의 snapshot을 쓴다. version이 하나도 없는 Draft는 내보낼 snapshot이 없어 body/manifest 양쪽에서 skip한다(순서 변형 없음).

### 6.3 body 조립

- 각 unit block = `{heading}\n\n{raw_text}`. unit block들을 `\n\n`으로 잇는다.
- heading은 **Markdown = `# {title}`**, **TXT = 제목 줄(plain)**(오너 결정). unit_kind별 heading 레벨 매핑은 하지 않는다.
- `raw_text`는 snapshot 원문 그대로다. 단일 version export 선례처럼 **AI metadata를 삽입하지 않는다**. 제목 heading이 유일한 합성 텍스트다.
- 포함 unit이 0개면 body는 빈 문자열이다.

### 6.4 delivery manifest

- **요청 시에만**(같은 endpoint `manifest=true`) 응답 `manifest`에 실리고, 미요청 시 `manifest=null`이다(오너 결정: 별도 endpoint 아님).
- shape: `{project_id,format,include_archived,units[]}`. 각 unit = `{draft_id,title,unit_kind,position,version_id,version_number,snapshot_id,content_hash}`로 body에 실린 unit과 같은 순서·집합이다.
- 이는 export 재현용 traceability manifest이며 version 선택을 저장하는 **saved publication manifest(§5 Deferred)**와 다르다.
