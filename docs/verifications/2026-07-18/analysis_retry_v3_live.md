# Verification Record — 선택 C: analysis_extract_v3 + 명시 retry + 프론트 failed 판별 (독립 검증)

## Subject metadata

- **날짜**: 2026-07-18
- **요청자**: 오너 ("다음작업 검증해줘. 선택 C 구현과 라이브 재검수까지 완료했습니다...")
- **검증자**: 독립 검증 AI(본 세션). 작업 AI(구현·재검수 주체)와 별개.
- **대상 슬라이스**: accept 후 재분석 `source_ref not found` 결함의 해결(Option C). (1) `analysis_extract_v3` immutable 프롬프트 승격(namespace 분리), (2) `POST /analysis/jobs/{job_id}/retry` 명시 retry(FAILED→PENDING만, 같은 job, failure clear, 타 상태 409), (3) 프론트 failed 판별(HTTP 200의 failed도 오류).
- **정본 계약 참조**: `docs/live_review_briefs/2026-07-18/analysis_retry_after_accept.md`(Option C 승인 브리프), `docs/system-contract-sot.md`(v1.7.8), `docs/plans/02-analysis-job-state-decisions.md`, `docs/plans/02-analysis-pipeline.md`, `docs/plans/02-analysis-provider-wiring-decisions.md`.
- **소스**: 기저 커밋 `99cd40a` 위 작업 트리 + 실행 중인 재배포 스택. 구현과 본 기록은 같은 closure 커밋에 포함한다.

## Scope

1. **retry 엔드포인트 계약**: FAILED→PENDING만, 같은 job ID, failure fields clear, 타 상태 409.
2. **v3 프롬프트**: immutable 승격, report pointer vs source_ref ID namespace 분리, 직렬화 순서, repair turn 구 namespace 미노출, strict/repair 1회.
3. **프론트**: failed job retry→run, HTTP 200의 failed도 오류 처리.
4. **acceptance matrix 8 경계**: 각 경계가 회귀 테스트로 잠겼는지(under/over-strict 양방향).
5. **라이브 재검수(독립)**: 원 실패 job `6a5aeba1...950`의 retry→succeeded, candidate 5, 중복 0가 Mongo 정본과 일치.
6. **테스트 재현**: 백엔드 1126 / 프론트 124 독립 재실행.

## Methodology

- 작업 AI 보고·브리프를 신뢰하지 않고 코드·테스트·Mongo 정본·컨테이너에서 재도출.
- **boundary matrix**: 브리프 Acceptance matrix(8 경계) → 각 cell을 named 회귀로 추적.
- **테스트 독립 재실행**: 백엔드 `python3 -m pytest --ignore=tests/test_memory_mongo.py`, 프론트 `vitest run`.
- **Mongo 정본 직조회**: `docker exec ai_writte_system-mongo-1 mongosh ai_writing_system`으로 job `6a5aeba1...950`·candidate·report·failure fields 조회.

## Findings

### 1. retry 엔드포인트 계약 — 코드 정확 (PASS)

- `main.py:1766` `POST /projects/{project_id}/analysis/jobs/{job_id}/retry` → `analysis.retry_failed_job`; `AnalysisNotFound/NotFound`→404, `InvalidJobStateTransition`→409.
- `service.py:105-114` `_ALLOWED_JOB_TRANSITIONS`: `FAILED→PENDING`만 허용. `SUCCEEDED/RUNNING/PENDING`→PENDING 시도 → `InvalidJobStateTransition`→**409**. (브리프 "다른 상태는 409" 일치.)
- `service.py:339-357` `_transition_job`: target=PENDING 시 `failure_reason=None, failure_detail=None`으로 `replace` → **failure fields clear**. non-failed 전이가 failure field를 set하면 reject(346-349). (브리프 "실패 필드 제거" 일치.)
- 같은 job ID 유지: `retry_failed_job`이 새 job을 만들지 않고 `_require_job`→`update_job`. (브리프 "같은 job ID 유지" 일치.)
- `run_analysis_job`(`main.py:1777`): PENDING 아니면 replay. 따라서 retry(→PENDING) 후 run은 실제 재실행.

### 2. v3 프롬프트 — namespace 분리 7축 모두 코드 구현 (PASS)

- `prompt_templates.py:25` `ANALYSIS_EXTRACT_PROMPT_VERSION = "analysis_extract_v3"`(기본값). v1/v2는 `seed_analysis_extract_v1/v2`로 보존, `seed_template`이 immutable(`PromptTemplateConflict` on version-exists-with-diff). v3만 `seed_analysis_extract_v3`가 기본 template 사용.
- `ANALYSIS_EXTRACT_TEMPLATE` 본문: "Treat writing_candidate_report source_blocks and related pointers as **advisory provenance only**", "**Never copy** document_id, block_id... into source_anchors", "Use source_ref_id values **only from the current source_ref_catalog**", 정확한 taxonomy(`character_observation/event_observation/open_question_observation`)·full-anchor(`source_ref_id/start_offset/end_offset/quote/content_hash`)·payload shape 명시.
- `prompt_builder.py:45-52`: serialized user payload에서 `writing_candidate_report`(advisory) **뒤에** `source_ref_catalog`(authoritative) 배치(주석이 의도 명시). (브리프 57행 일치.)
- `extractor.py::_repair_request`: repair turn은 `snapshot_raw_text` + `authoritative_source_ref_catalog`만 전달, **writing_candidate_report(구 snapshot pointer namespace) 제외**. 주석: "Keeping those IDs out of the repair turn prevents the exact namespace collision". Post-verification closure에서 system prompt도 실제 payload key `authoritative_source_ref_catalog`를 정확히 지칭하도록 교정했다.
- strict validation 유지: `extractor.py:176 _catalog_anchor_error`가 catalog 밖 anchor 검출→`source_invalid`. 자동 remap 없음.
- repair 1회: `extractor.py:133 _repair_once`(단일 호출). (브리프 "repair 1회 유지" 일치.)

### 3. 프론트 failed 판별 — 정확 (PASS)

- `client.ts:582-599` `analyzeVersion`: `job.status === "failed"` → `POST .../retry`(같은 job.id) → `job.status !== "pending"`이면 409 throw → run → **`run.job.status !== "succeeded"`이면 ApiError throw**(HTTP 200이어도). (브리프 "HTTP 200의 failed도 오류 처리" 일치.)

### 4. acceptance matrix — 8 경계 전부 named 회귀로 잠금 (PASS, 빈 cell 없음)

| 경계 | 회귀(추적) | 방향 |
|---|---|---|
| 구 report pointer + 새 catalog → v3 namespace 분리/정상 추출 | `test_v2_separates_old_report_pointers_from_current_source_ref_ids` + `test_versioned_prompt_adapter_repairs_catalog_id_drift_once`(구 `old-snapshot:block:4`가 repair turn에 없음) | under-strict |
| report 없는 snapshot → 정상 | 기존 extractor 회귀 | over-strict |
| catalog 밖 anchor → strict source_invalid, candidate 0 | `_catalog_anchor_error` + extractor 회귀 | fail-closed |
| FAILED 일반 create/run replay → failed 그대로 | `test_analysis_job_state.py`(replay terminal) | over-strict |
| FAILED 명시 retry → 같은 job pending, failure clear | `test_analysis_job_state.py::test_explicit_retry_failed_to_pending_clears_failure_fields` + `test_application_api.py::test_analysis_retry_endpoint_resets_only_failed_job_in_place` + `AnalysisTrigger.test.tsx`(190) | under-strict |
| retry 성공 후 재클릭 → succeeded replay, ID/수 불변 | `AnalysisTrigger.test.tsx`(207) + D5=A 회귀 | 양방향 |
| SUCCEEDED/RUNNING/PENDING retry → 409 | `test_explicit_retry_rejects_every_non_failed_state` + `test_analysis_retry_endpoint_rejects_non_failed_and_cross_project` | over-strict |
| HTTP 200 failed run envelope → 프론트 오류 | `AnalysisTrigger.test.tsx::treats a 200 failed run envelope as an error`(224) | under-strict |

빈 cell 없음. cross-project isolation도 `test_explicit_retry_enforces_project_isolation`(171) + E2E(1250)로 잠김.

### 5. 라이브 재검수 — Mongo 정본과 일치 (PASS)

작업 AI 보고 원 실패 job `6a5aeba1b339f88750c0a950`:

| 항목 | 작업 AI 보고 | Mongo 정본(독립) | 일치 |
|---|---|---|---|
| job status | retry→succeeded | **succeeded** | ✓ |
| idempotency_key | analyze:{snap} | `analyze:6a5aeba0...94f` | ✓ D5=A |
| failure_reason/detail | clear | **null / null** | ✓ |
| writing_candidate_report | (accept로 심김) | **present**(claims 4, related pointer = `source_blocks` namespace) | ✓ |
| candidate 수 | 5 | **5** | ✓ |
| candidate 중복 | 0 | unique ID 5 = length 5 | ✓ |
| snapshot job 수 | 1(D5=A) | **1** | ✓ |

candidate 타입 분포(character_observation 3·event_observation 2)가 v3 taxonomy에 부합. 직전 `d5a_live_deploy.md` 후속 hardening에서 accept-report 소비 자체는 이미 라이브로 확인됐고, 이번에는 **구 `source_blocks` pointer를 실제 보유한 원 실패 job**이 current catalog와 공존하면서도 succeeded한 추가 경계를 정본으로 확증했다.

### 6. 테스트 독립 재실행 — 보고 일치 (PASS)

- 백엔드 `python3 -m pytest --ignore=tests/test_memory_mongo.py` → **1126 passed / 48 skipped / 276 subtests**(이전 1119 + 7 신규). 작업 AI 보고 일치.
- 프론트 `vitest run` → **8 files / 124 passed**(이전 121 + 3 신규 retry/failed 회귀). 작업 AI 보고 일치.
- `git diff --check` 통과(독립 확인).

## Issues / Risks

### Blocking (계약 의무)

- **검증 후 발견·커밋 전 폐쇄**: repair user payload는 `authoritative_source_ref_catalog`를 보내는데 system prompt가 존재하지 않는 `current source_ref_catalog in original_user_payload`를 지칭했다. 실제 payload와 prompt literal의 내부 모순이므로 차단성 드리프트로 재분류했다. system prompt를 `authoritative_source_ref_catalog in the repair payload`로 교정하고, 구 report pointer가 든 fixture에서 (a) old document ID 미노출, (b) authoritative catalog ID 노출, (c) system prompt의 실제 key 지칭을 한 회귀로 잠갔다. focused test 통과 후 전체 스위트를 재실행해 폐쇄했다.
- 미해결 blocking 없음.

### Hardening recommendations (non-blocking)

- **비결정적 malformed JSON (첫 v3 라이브)**: 작업 AI 보고 "첫 v3 live run이 source_ref not found가 아닌 별도 비결정적 malformed JSON으로 1회 실패, 명시 retry로 succeeded". raw provider output 미저장이라 독립 확증 불가(관찰로만 수용). 브리프 follow-up이 "재발 시 raw Analysis output 관측 도구를 별도 브리프로 연다"로 남긴 것과 일치 — 재발 시 raw output 캡처 도구 추가 권장.
- **원 source_ref not found의 부정적 증명**: "v3에서 재현 안 됨"은 발생하지 않았다는 관찰이지 완전 증명은 아님. 다만 v3의 namespace 분리(advisory vs authoritative·repair turn 제외)가 혼동의 근원을 구조적으로 제거하므로 예방 메커니즘은 코드로 확증.

## Verdict

**합격(Pass).** Option C의 세 축 — (1) `analysis_extract_v3` namespace 분리 프롬프트(advisory report vs authoritative catalog, repair turn 구 namespace 제외, strict·repair 1회 유지), (2) 명시 retry 엔드포인트(FAILED→PENDING만, 같은 job, failure clear, 타 상태 409), (3) 프론트 failed 판별(HTTP 200 failed도 오류) — 이 모두 코드·acceptance matrix(8 경계 빈 cell 없음)·독립 테스트 재실행(백엔드 1126·프론트 124)·라이브 Mongo 정본(job succeeded·candidate 5·중복 0·report 보유·failure clear)에서 일관 확증됐다. 작업 AI 보고와 정확히 일치.

커밋 전 보강에서 발견한 repair prompt/payload key 모순도 전용 회귀와 전체 재실행으로 폐쇄했으므로 최종 verdict는 **합격 유지**다.

## Outstanding items

- **커밋 상태**: 검증 시점에는 미커밋이었으며, 구현·보강·본 기록을 같은 closure 커밋으로 묶는다.
- **raw provider output 관측**: 비결정적 malformed JSON 재발 시 별도 diagnostics 브리프/도구(브리프 follow-up과 일치).
- **스택 실행 중**: 오너 종료 미선택.

## Reproduction

```bash
# 1) retry 엔드포인트 상태계약(단위)
python3 -m pytest tests/test_analysis_job_state.py -k "explicit_retry" -q
#   기대: retry FAILED→PENDING(failure clear)·non-failed 409·project isolation 전 PASS

# 2) retry 엔드포인트 E2E
python3 -m pytest tests/test_application_api.py -k "analysis_retry" -q

# 3) 프론트 failed/retry 회귀
cd frontend && npm test -- --run AnalysisTrigger
#   기대: retry same failed job·succeeded replay no-retry·200-failed-as-error PASS

# 4) 전체 스위트
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider  # 1126 passed/48 skipped/276 subtests
cd frontend && npm test -- --run                            # 124 passed/8 files

# 5) 라이브 Mongo 직조회(retry로 succeeded된 원 실패 job)
docker exec ai_writte_system-mongo-1 mongosh --quiet ai_writing_system --eval '
  const j="6a5aeba1b339f88750c0a950"; const job=db.analysis_jobs.findOne({_id:j});
  print("status:",job.status,"| key:",job.idempotency_key,
        "| failure_reason:",job.failure_reason,
        "| has_report:",job.writing_candidate_report!=null);
  const c=db.analysis_candidates.find({job_id:j}).toArray();
  print("candidates:",c.length,"unique:",new Set(c.map(x=>x._id)).size);
  print("snapshot job count:",db.analysis_jobs.countDocuments({snapshot_id:job.snapshot_id}));'
#   기대: succeeded | analyze:{snap} | null | true | 5 5 | 1
```
