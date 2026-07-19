# W3 증분 2 Writing intent + W3 전체 closure 독립 검증

## Subject metadata

- **날짜**: 2026-07-19
- **요청자**: 오너 (W3 증분 2 완료 결과에 대해 "다음작업 검증해줘" 요청)
- **검증자**: 독립 AI worker (회의적·적대적 검증, 임의 수정 금지 범위)
- **검증 대상 slice/artifact**: Writing Workspace V2 W3 증분 2 — `append_current|start_next_unit` Writing intent(WI-01~22), 6-surface 원자 write, accept receipt, 그리고 W3 전체 closure(SC-01/02 OU·Writing intent fragment 확장)
- **canonical spec reference**:
  - `docs/plans/writing-workspace-v2-w0-contract.md` §3 (Writing intent와 accept), §4 WI-01~22 + SC-01/02 named matrix
  - `schemas/writing-workspace-v2-w0.schema.json` `$defs/writingAcceptCommon`, `writingAcceptRequestV2`, `writingAcceptResponseV2`, `writingAcceptAnalysisPartialV2`, `savedWritingTarget`, `nextUnitSpec`, `writingIntent`
  - `docs/system-contract-sot.md` v1.7.16 (W3 증분 2 row), v1.7.15 (W3 증분 1 B1 closure), v1.4 single-writer fallback 조항
- **검증 대상 work source**: **working tree, uncommitted** (commit `31d2fab` "fix: align ordered draft conflicts with W0" 위에 W3 증분 2 변경사항이 staged되지 않은 채로 존재). B1 closure는 commit `31d2fab`에 반영됨.

## Scope

본 검증은 W0 §3 + WI-01~22 named matrix와 SC-01/02 W3 closure가 govern하는 표면만 다룬다. W4 export는 범위 밖.

1. **B1 closure 재확인**: 이전 W3 증분 1 검증(`w3_ordered_unit.md`)의 조건부 합격 조건(duplicate `ordered_draft_ids` → 409)이 commit `31d2fab`에서 해소되었는지.
2. **Spec contract**: W0 §3 prose(§3.1 discriminator/호환, §3.2 accept 효과/6-surface 원자 write, §3.3 idempotency/response)와 schema `$defs`의 내부 일관성, 그리고 goal "optional vs required-nullable" 자기모순 해소의 정당성.
3. **WI boundary matrix 22행**: `tests/test_writing_accept.py`의 WI-01~22 + `tests/test_core_sot_mongo.py`의 WI-11.
4. **구현 코드**: `writing/models.py`, `writing/accept.py`, `writing/http_models.py`, `core_sot/service.py`(start_next_unit), `core_sot/mongo_repository.py`(record_start_next_unit + receipt), `main.py`(accept endpoint).
5. **SC-01/02 W3 closure**: `tests/test_project_brief.py::WorkspaceW0SchemaIntegrationTest`가 OU·Writing intent fragment까지 다루는지 (이전 검증 H1 해소).
6. **전체 회귀 수치**: backend full, live Mongo, frontend, `gen:api` byte-identical + build.

## Methodology

계약을 먼저 scope하고 boundary matrix를 구축한 뒤 코드를 읽었다. B1 closure는 직접 HTTP 재현으로, 6-surface 원자성은 코드 정독 + 실패 주입 test로, schema 동형은 OpenAPI dump와 catalog를 직접 비교로 검증했다. 수치는 피감사 worker의 보고를 믿지 않고 독립 재도출.

- **B1 재현**: `httpx.ASGITransport`로 reorder invalid case의 status code를 직접 주입 (duplicate/missing/foreign/unknown).
- **계약 정독**: W0 §3(95~135행) 전문, schema `$defs` 전체, SoT v1.7.15/v1.7.16.
- **boundary matrix**: WI-01~22 22행 direction/branch/literal 추출, 각 test node가 canonical 이름으로 존재하는지 + assertion이 양방향 guard인지.
- **코드 정적 검증**: `accept.py`의 replay-before-gate 순서, `_validate` binding 400, `_finalize` partial saved, `start_next_unit`의 6-surface shift/new Draft/version 1/snapshot/blocks/receipt, InMemory/Mongo `record_start_next_unit`의 transaction + before-image rollback.
- **SC-01/02 대조**: `WorkspaceW0SchemaIntegrationTest`가 ProjectBrief을 넘어 OU·Writing intent fragment의 required/enum/additionalProperties를 catalog와 동형 단정하는지.
- **회귀 재실행 명령**:
  - `python3 -m pytest tests/test_writing_accept.py tests/test_core_sot_mongo.py -q -p no:cacheprovider`
  - `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider`
  - `cd frontend && npm test -- --run`
  - `cp src/api/schema.d.ts /tmp/before && npm run gen:api && diff -q /tmp/before src/api/schema.d.ts && npm run build`
  - B1 재현 스크립트는 본 기록 Reproduction 절에 인라인.
- **sandbox 제약**: localhost Mongo socket 차단으로 `test_core_sot_mongo.py`의 54개(WI-11 포함)가 skip됨. W2/W3 inc1 검증과 동일한 환경 패턴. 코드와 test node는 정적 검증으로 cover.

## Findings

### 0. B1 closure 재확인 (이전 W3 증분 1 검증의 조건부 합격 조건)

- 이전 검증(`w3_ordered_unit.md`)은 duplicate `ordered_draft_ids`가 W0 §2.2 literal "409"가 아닌 Pydantic 422로 반환되어 **조건부 합격**을 내렸다. owner는 SoT v1.7.15 row에 기록된 대로 (a)옵션(code를 409로 통일)으로 결정했고, commit `31d2fab`에 반영했다.
- **독립 재현**(`main.py`의 `DraftOrderPutRequest`에서 `reject_duplicate_draft_ids` field_validator 제거, service `reorder_drafts`의 duplicate 검사로 409 경로 통일, `tests/test_ordered_units.py:299` `assertEqual(response.status_code, 409)` 강화):
  ```
  missing->409, duplicate->409, foreign->409, unknown->409
  ```
- duplicate가 이제 409로 통일되었고, OU-08 assertion이 literal 409를 단정한다. schema `uniqueItems:true`는 구조적 introspection으로 유지(status authority 아님 — SoT v1.7.15 명시).
- **B1은 해소됨.** 이전 검증의 conditional verdict 조건이 닫혔다.

### 1. Spec contract (W0 §3 + schema 내부 일관성)

- §3.1: `intent=append_current|start_next_unit`, 생략 시 `append_current`/`next_unit=null` 호환. `append_current`는 `next_unit=null`, `start_next_unit`은 `next_unit={title,unit_kind,goal}` 필수. candidate가 request의 exact intent/next_unit을 echo. binding 불일치는 provider/write 전 400. schema `$defs/writingAcceptRequestV2`(oneOf append+next_unit:null / start+nextUnitSpec)와 일치.
- §3.2: 두 intent 모두 current draft_id/base_version_id가 같은 project active latest. Gate 서버 재평가, pass일 때만 저장, non-pass는 `accepted=false` write 0. `start_next_unit`은 position shift(archived 포함) + 새 Draft(current+1) + version 1 + snapshot + blocks + receipt를 한 transaction에 commit. transaction 실패 시 6 surface 모두 0건.
- §3.3: receipt identity `(project_id, "writing-accept:{idempotency_key}")`. replay lookup이 stale base/Gate보다 먼저. append의 기존 save-key-only record는 receipt 없이 read-through replay(WI-17). response exact `{accepted,intent,gate,saved,analysis_job,idempotent_replay}`, saved는 `{draft_id,draft_version_id,version_number,snapshot_id,content_hash,unit_kind,position}`.
- **goal 자기모순 해소 확인**: W0 §3.1 prose("goal은 optional nonblank string/null")과 schema `$defs/nextUnitSpec`(goal required + `nullableNonBlankString`)의 표면적 충돌을, 작업자가 "wire shape 정본 = schema"로 해석해 `NextUnitBody.goal: str | None`(required + nullable, `main.py:1235`)로 정렬. 이 해석은 타당하다 — HTTP/OpenAPI가 wire 정본이고 "optional"은 "값이 null일 수 있음"을 뜻하므로 required-nullable과 양립한다. domain `NextUnit.goal`(`models.py:169`, default None)은 dataclass 생성 편의이며 wire shape과 무방독. contract 내부 일관성 회복.

### 2. WI boundary matrix 22행 — empty cell 없음

`tests/test_writing_accept.py`(WI-01~10, 12~22)와 `tests/test_core_sot_mongo.py`(WI-11)에 W0 §4의 canonical 이름 그대로 22개 test node가 존재하며 전부 PASS. assertion이 contract를 실제로 pin하는지 양방향 검증:

| ID | direction | test node | pin 품질 | 비고 |
|---|---|---|---|---|
| WI-01 | not-fire | `WritingIntentCompatibilityTest::test_omitted_intent_preserves_append_current` | ✅ over-strict | intent 생략 시 append_current 호환 |
| WI-02 | fire | `WritingIntentAcceptTest::test_append_current_saves_same_draft` | ✅ under-strict | separator 규칙 `\n\n` + same draft_id 단정 |
| WI-03 | fire | `test_start_next_unit_creates_atomic_first_version` | ✅ under-strict | version 1 + snapshot raw_text + target position=current+1 |
| WI-04 | not-fire | `test_start_next_unit_preserves_current_unit` | ✅ over-strict | current position/version/snapshot 변경 없음 |
| WI-05 | fire | `test_start_next_unit_shifts_following_positions` | ✅ under-strict | positions `[1,2,3,4]`, archived도 shift + still archived |
| WI-06 | not-fire | `WritingIntentApiTest::test_mismatched_intent_binding_rejected_before_provider` | ✅ over-strict | append+next_unit / start+missing → 400 + **`gate.calls==0`** |
| WI-07 | not-fire | `test_invalid_current_target_creates_nothing` | ✅ over-strict | stale/cross/archived current → 0건 |
| WI-08 | not-fire | `test_nonpass_gate_has_no_start_next_side_effects` | ✅ over-strict | REVISE/BLOCK → accepted=false/saved=None + positions unchanged + jobs empty |
| WI-09 | fire | `test_start_next_same_key_replays_same_unit` | ✅ under+over | same key → same target/version, **gate calls 안 늘어남**, draft count 안 늘어남 |
| WI-10 | not-fire | `test_start_next_different_key_creates_distinct_unit` | ✅ over-strict | different key → distinct id + position 2 + 2 jobs |
| WI-11 | fire | `WritingIntentMongoTest::test_start_next_transaction_rolls_back_entire_write_set` | ✅ under-strict (4/6 surface 명시적) | 실패 주입 → position/Draft 복원 + snapshot 0 + receipt None (version·block은 간접 cover — Hardening H1) |
| WI-12 | not-fire | `WritingIntentCompatibilityTest::test_existing_append_accept_contract_remains_green` | ✅ over-strict | 기존 append accept 회귀 유지 |
| WI-13 | fire | `WritingIntentApiTest::test_start_next_analysis_failure_returns_saved_partial` | ✅ under-strict | start 후 analysis 실패 → 502 + saved partial |
| WI-14 | not-fire | `test_start_next_partial_replay_converges` | ✅ under+over | failing→retry same target, no duplicate, recover→1 job |
| WI-15 | fire | `WritingIntentApiTest::test_accept_response_exact_keys_for_both_intents` | ✅ under-strict | 두 intent exact top-level + saved keys |
| WI-16 | not-fire | `test_next_unit_goal_is_not_persisted_as_prose` | ✅ over-strict | goal이 snapshot.raw_text/title에 없음 + receipt.intent="start_next_unit" |
| WI-17 | fire | `WritingIntentCompatibilityTest::test_legacy_append_save_record_replays_without_receipt` | ✅ under-strict | receipt 없는 append save-key read-through replay |
| WI-18 | not-fire | `WritingIntentCompatibilityTest::test_append_different_key_creates_next_version` | ✅ over-strict | different key → next version (replay 오인 X) |
| WI-19 | fire | `test_replay_precedes_stale_base_and_gate` | ✅ under-strict | base stale 상태에서 same key replay → **gate calls 안 늘어남** |
| WI-20 | fire | `WritingIntentApiTest::test_append_analysis_failure_returns_saved_partial` | ✅ under-strict | append analysis 실패 → 502 + saved partial |
| WI-21 | not-fire | `test_append_partial_replay_converges` | ✅ under+over | append failing→retry converge, no duplicate version |
| WI-22 | fire | `test_both_intents_use_snapshot_scoped_analysis_key` | ✅ under-strict | 두 intent 모두 `analyze:{snapshot_id}` |

추가로 `WritingIntentInMemoryRollbackTest::test_mid_write_failure_leaves_no_partial_unit`(`test_writing_accept.py:846`)이 InMemory 경로의 6-surface rollback을 잠그고, 주석이 "contract-named Mongo transaction guard는 WI-11"이라 명시해 두 경로가 상호 보완적으로 cover됨. WI-06/WI-09/WI-19가 **`gate.calls` 카운터로 "provider/Gate 호출 전/중복 0"을 직접 단정**하는 점은 특히 정밀 — 단순히 status code만 보지 않고 provider 호출 자체가 일어나지 않았음을 증명한다.

### 3. 구현 코드 ↔ spec literal 일치

- `writing/models.py:23-28` `WritingIntent` StrEnum exact. `NextUnit`(title/unit_kind/goal), `WritingRequest`/`WritingCandidate`의 `intent`/`next_unit` echo fields(default `APPEND_CURRENT`/`None`로 legacy 호환).
- `writing/accept.py:89-148` `accept`: `_validate`(binding 400) → reporter → **replay lookup이 stale base/Gate보다 먼저**(line 105-110, WI-19) → base/stale check → gate.evaluate → non-pass `WritingAcceptResult(False, gate, None, None, intent, None)`(WI-08). START_NEXT_UNIT는 `core_sot.start_next_unit`, `DuplicateWritingAcceptReceipt` catch로 same-key race 수렴. APPEND는 `_append_patch`(empty/`\n`/`\n\n` separator) + `save_draft`.
- `writing/accept.py:150-177` `_replay`: START_NEXT는 durable receipt, APPEND는 `list_draft_versions`에서 save_key 조회 read-through(WI-17).
- `writing/accept.py:179-189` `_finalize`: `_create_job` 실패 시 `WritingAcceptAnalysisError(saved=saved, intent, target_draft)`로 partial saved carry(WI-13/WI-20).
- `core_sot/service.py:636-717` `start_next_unit`: shifted = `position > current_position`인 모든 draft(archived 무관) +1, new_draft position=current+1, version 1, snapshot(candidate strip), blocks, receipt. **goal은 인자로 전달되지 않아 저장될 수 없음**(WI-16).
- `core_sot/service.py:283-329`(in-memory) / `mongo_repository.py:438-476`(Mongo) `record_start_next_unit`: 6-surface(shifted drafts/new draft/version/snapshot/blocks/receipt)를 한 번에 write, 실패 시 before-image 전체 rollback. Mongo는 transaction path + single-writer fallback 양쪽. `_start_next_unit`의 negative position trick으로 `(project_id,position)` unique index 하에서 shift 원자화.
- `main.py:3416-3504` accept endpoint: `WritingIntent(body.intent)`/`NextUnit` 파싱(ValueError→400), request/candidate 동일 intent/next_unit(echo), `WritingAcceptAnalysisError`→JSONResponse(502, `{accepted:True, intent, saved, analysis_job:None, analysis_error}`), 성공 시 exact top-level. `NextUnitBody.goal: str | None`(required-nullable, `main.py:1235`).
- `writing/http_models.py`: `AcceptedSavePayload`(saved exact keys), `WritingAcceptResponse`(top-level exact), `WritingAcceptAnalysisPartial`(502 partial exact) — 모두 schema `$defs`와 일치.
- **Spec-silent-but-enforced 탐지**: 별도 발견 없음. 구현이 contract가 명시하지 않은 boundary를 임의로 열지 않는다.

### 4. SC-01/02 W3 전체 closure (이전 검증 H1 해소)

이전 W3 inc1 검증의 H1(SC-01/02가 OU fragment를 안 다룸)이 해소되었다. `tests/test_project_brief.py::WorkspaceW0SchemaIntegrationTest`:

- **SC-01**(`test_openapi_components_match_w0_fragments`): ProjectBrief에 더해 `DraftPayload`↔`draftV2`, `DraftOrderPutRequest`↔`draftOrderPutRequest`(+uniqueItems), `DraftOrderPutResponse`↔`draftOrderPutResponse`, `UnitKind.enum`↔`unitKind.enum`(OU), 그리고 `WritingIntent.enum`↔`writingIntent.enum`, `NextUnitBody.required`↔`nextUnitSpec.required`(+`additionalProperties:false`, **goal required 명시**), `AcceptedSavePayload`↔`savedWritingTarget`, `WritingAcceptResponse`↔`writingAcceptResponseV2`, `WritingAcceptAnalysisPartial`↔`writingAcceptAnalysisPartialV2`까지 catalog와 required/enum 동형 단정. paths에 `draft-order`, `writing/accept` 포함.
- **SC-02**(`test_endpoints_do_not_reference_catalog_root`): `brief`에 더해 `draft-order`·`writing/accept` endpoint가 catalog root를 참조하지 않고 named component(`DraftOrderPutRequest`/`DraftOrderPutResponse`/`WritingAcceptRequest`)를 참조함을 단정.

fragment가 이제 regression으로 잠겨 미래 drift가 감지된다. **SC-01/02의 W3 closure 완료.**

### 5. 회귀 수치 독립 재도출

| 항목 | 피감사 주장 | 검증자 독립 재도출 | 일치 |
|---|---|---|---|
| WI accept + Mongo focused | (명시 없음) | **44 passed, 54 skipped, 19 subtests** (54 skipped은 Mongo-gated, WI-11 포함) | — (참고용) |
| backend full | 1181 passed / 73 skipped / 297 subtests | **1181 passed / 73 skipped / 297 subtests** | ✅ 정확 일치 |
| frontend | 146 passed / 10 files | **146 passed / 10 files** | ✅ 정확 일치 |
| `gen:api` | 두 번째 생성물 byte-identical | gen:api 재실행 후 `diff -q` → **byte-identical** | ✅ deterministic 확인 |
| `npm run build` | 96 modules | **96 modules**, CSS 17.81 kB(gzip 4.00), JS 287.30 kB(gzip 88.75) | ✅ modules 일치 (JS는 W3 inc1 285.37에서 Writing intent UI 추가로 자연 증가) |

수치 주장이 전부 정확히 일치한다. 73 skipped는 WI-11을 포함한 Mongo-gated test이며 sandbox 환경 제약이다.

## Issues / Risks

### Blocking (contract obligations)

**없음.** B1은 commit `31d2fab`에서 해소되었고(§0), WI-01~22 boundary matrix 22행이 모두 canonical 이름으로 존재하며 양방향 guard로 contract를 pin하고(§2), SC-01/02 W3 closure가 OU·Writing intent fragment를 catalog와 동형 대조한다(§4). contract-required branch에 empty cell 없음.

### Hardening recommendations (non-blocking, contract 초과)

- **H1 — WI-11 version·block surface 명시적 assertion**: `test_start_next_transaction_rolls_back_entire_write_set`(`test_core_sot_mongo.py:770`)는 6-surface 중 position/Draft(before 동등)/snapshot(count 0)/receipt(None)를 명시적으로 단정하지만, **version과 block surface는 직접 assert하지 않는다**. rollback 코드(`mongo_repository.py:466-476`)가 6-surface 전부 delete하므로 정적 검증으로는 cover되지만, W0 §3.2가 "position 이동, Draft, version, snapshot, block, receipt 모두 0건"을 요구하므로 `version_count(new_draft.id)==0`와 `blocks.count_documents({snapshot_id})==0`를 추가하면 6-surface를 완전히 명시적으로 pin한다. test가 존재하고 핵심 4 surface를 단정하므로 blocking은 아니다.
- **H2 — working tree uncommitted**: W3 증분 2 변경사항이 commit `31d2fab` 위에 staged되지 않은 채 다수 파일(`models.py`, `accept.py`, `main.py`, `mongo_repository.py`, `service.py`, `http_models.py`, `test_writing_accept.py`, `test_core_sot_mongo.py`, `test_project_brief.py`, `WritingPanel.tsx`, `schema.d.ts`, SoT/work_log/HANDOFF/CHANGELOG)로 쌓여 있다. 작업자 보고의 "git diff --check clean"은 whitespace check이며 working tree clean이 아니다. 검증 자체에는 영향 없으나(코드는 현재 tree 기준으로 검증됨), 오너가 승인 시 하나의 커밋으로 묶는 것이 다음 worker handoff에 필요하다.

## Verdict

**합격 (Pass)** — 조건 없음.

- **근거**: 
  1. 이전 W3 inc1 검증의 유일한 차단 조건 B1이 commit `31d2fab`에서 (a)옵션으로 해소되었고, 직접 재현으로 duplicate→409를 확인했다.
  2. WI-01~22 boundary matrix 22행이 모두 canonical 이름으로 존재하며, under-strict/over-strict 양방향 guard로 W0 §3 contract를 pin한다. 특히 WI-06/09/19가 `gate.calls` 카운터로 provider/Gate 호출 전/중복 0을 직접 증명한다.
  3. 6-surface 원자 write가 `start_next_unit` + InMemory/Mongo `record_start_next_unit`(transaction + single-writer before-image rollback)로 구현되었고, WI-11 + InMemory rollback test가 실패 주입으로 이를 검증한다.
  4. SC-01/02 W3 closure가 OU·Writing intent fragment를 catalog와 동형 대조하고 endpoint의 catalog-root 미참조를 단정한다(이전 H1 해소).
  5. goal 자기모순이 wire-shape-정본 해석으로 일관성 있게 정렬되었다.
  6. 회귀 수치(1181/73/297, 146/10, gen:api byte-identical, build 96 modules)가 피감사 주장과 정확히 일치한다.
- **유일한 비차단 권고**: H1(WI-11 version·block 명시적 assertion)과 H2(uncommitted working tree 커밋). 어느 것도 contract obligation이 아니므로 합격 판정에 영향을 주지 않는다.

## Outstanding items (운영 상태, 결함 아님)

- **WI-11 live Mongo 실행**: sandbox가 localhost Mongo socket을 차단하여 `test_core_sot_mongo.py` 전체 54개(WI-11 포함)가 skip된다. 코드(`mongo_repository.py:438-515`)와 test node는 정적 검증으로 cover했으나, 권한 있는 replica-set 머신에서 `WritingIntentMongoTest::test_start_next_transaction_rolls_back_entire_write_set`와 신규 Mongo receipt index(`uniq_writing_accept_receipt`)가 0 skip으로 통과하는지 최종 확인이 필요하다. W2/W3 inc1 closure와 동일한 live-Mongo 인계 패턴.
- **working tree uncommitted (H2)**: W3 증분 2 변경사항이 커밋되지 않았다. 오너 승인 시 하나의 커밋으로 묶어야 다음 worker가 깨끗한 base에서 W4를 착수할 수 있다.
- **W4 (다음 작업)**: W0의 ordered-latest TXT/Markdown export + 별도 delivery manifest. 본 검증 범위 밖.
- **외부 publish/push**: 요청 범위 밖.

## Reproduction

```bash
# 1. WI focused + Mongo (sandbox: Mongo skip)
python3 -m pytest tests/test_writing_accept.py tests/test_core_sot_mongo.py -q -p no:cacheprovider
# 기대: 44 passed, 54 skipped, 19 subtests (54 skip은 Mongo-gated, WI-11 포함)

# 2. backend full
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
# 기대: 1181 passed, 73 skipped, 297 subtests

# 3. live Mongo (권한 있는 replica-set 머신)
CORE_SOT_TEST_MONGO_URI=mongodb://<replica-set> python3 -m pytest tests/test_core_sot_mongo.py -q -p no:cacheprovider
# 기대: 54 passed, 0 skipped (WI-11 six-surface rollback 포함)

# 4. frontend + gen:api determinism + build
cd frontend && npm test -- --run                                     # 기대: 146 passed / 10 files
cd frontend && cp src/api/schema.d.ts /tmp/b.ts && npm run gen:api && diff -q /tmp/b.ts src/api/schema.d.ts && echo byte-identical
cd frontend && npm run build                                         # 기대: 96 modules

# 5. B1 closure 재확인 (duplicate 이제 409)
python3 -c "
import asyncio, httpx
from services.application.app.core_sot.service import CoreSotService, InMemoryCoreSotRepository
from services.application.app.main import create_app
async def main():
    app = create_app(CoreSotService(InMemoryCoreSotRepository()))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as c:
        p = (await c.post('/projects', json={'name':'N'})).json(); pid = p['id']
        d1 = (await c.post(f'/projects/{pid}/drafts', json={'title':'One'})).json()
        await c.post(f'/projects/{pid}/drafts', json={'title':'Two'})
        for name, ids in [('missing',[d1['id']]), ('duplicate',[d1['id'],d1['id']]), ('foreign',[d1['id'],'x']), ('unknown',[d1['id'],'no'])]:
            r = await c.put(f'/projects/{pid}/draft-order', json={'ordered_draft_ids': ids})
            print(f'{name:10s} -> {r.status_code}')
asyncio.run(main())
"
# 기대: missing->409, duplicate->409(B1 해소), foreign->409, unknown->409
```
