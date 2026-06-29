# Work Log — 2026-06-29

## Goals

- HANDOFF를 읽고 다음 작업을 진행한다.
- Phase 2A 착수 전에 구현자가 추측하지 않아야 할 결정을 좁혀 사용자 승인 가능한 브리프로 정리한다.

## Completed work

### Phase 2A 착수 결정 브리프 추가

- 변경 파일: `docs/plans/02-analysis-kickoff-decisions.md`, `docs/plans/README.md`, `HANDOFF.md`.
- `HANDOFF.md`의 다음 작업을 검토한 결과, archive 후 파생 인덱스 stale 이벤트는 Phase 3 계약이 `Draft`라 구현 범위 밖이고, 실제 Gemma benchmark는 외부 llama.cpp endpoint 가용성에 의존한다. Phase 2 source_ref/candidate 정책은 사용자 결정 없이는 추측 구현이 된다.
- 이에 Phase 2A 착수 전에 필요한 결정을 별도 브리프로 정리했다. 초기 추천안은 최소 taxonomy 3종(`character_observation`, `event_observation`, `open_question_observation`), Phase 2A `create` only, candidate `needs_review` 고정, `create_source_ref` primitive non-idempotent 유지와 candidate/job 저장층 idempotency 소유였다.
- `docs/plans/README.md` 읽는 순서에 브리프를 추가했고, `HANDOFF.md`의 Current Status/Next Tasks를 갱신했다. 이후 사용자 승인으로 아래 "Phase 2A 착수 계약 승인 반영" 항목에서 구현 계약으로 승격했다.
- 효과: Phase 2A 구현을 시작하기 전에 사용자가 승인 또는 수정해야 할 결정이 한 문서에 모였고, 같은 날 승인된 항목은 SoT v1.6으로 정본화됐다.

### Phase 2A 착수 계약 승인 반영

- 변경 파일: `docs/plans/02-analysis-kickoff-decisions.md`, `docs/plans/02-analysis-pipeline.md`, `docs/system-contract-sot.md`, `HANDOFF.md`, `CHANGELOG.md`.
- 사용자 결정: 브리프 항목 1은 추천 3종(`character_observation`, `event_observation`, `open_question_observation`)을 채택하되 후속 확장성을 염두에 둔다. 항목 2는 사용자 위임에 따라 Phase 2A에서는 `source_observed`/`ai_inferred`만 쓰고, `user_declared`는 WritingBrief/Product Shell 이후로 미룬다. 항목 3은 Phase 2A `create` only로 시작한다. 항목 4는 candidate status `needs_review` 고정으로 간다. 항목 5는 confidence range만 강제하고 threshold는 차후 테스트에서 정한다. 항목 6~7은 채택됐다.
- SoT를 v1.6으로 올려 Phase 2A 착수 최소 계약을 정본화했다. `create_source_ref` primitive는 non-idempotent로 유지하고 candidate/job 저장층이 logical candidate retry idempotency를 담당한다.
- `02-analysis-pipeline.md`의 Phase 2A 섹션과 착수 전 결정사항을 갱신해, 2A에서 확정된 부분과 2B로 남은 부분을 분리했다.
- `HANDOFF.md`의 Next Task를 "승인 필요"에서 "Phase 2A 구현 착수"로 바꿨고, 이후 domain model slice 완료 후 Snapshot Loader/source validation으로 다시 전진시켰다.

### Phase 2A domain model + in-memory repository 구현

- 변경 파일: `services/application/app/analysis/__init__.py`, `models.py`, `repository.py`, `service.py`, `tests/test_analysis_phase2a.py`, `tests/test_core_sot_mongo.py`.
- SoT v1.6에 맞춰 `AnalysisJob`, `AnalysisTask`, `AnalysisCandidate`와 Phase 2A literal enum을 추가했다: `character_observation`/`event_observation`/`open_question_observation`, `source_observed`/`ai_inferred`, `create`, `needs_review`.
- method 기반 `AnalysisRepository` Protocol과 `InMemoryAnalysisRepository`를 추가했다. Core SOT의 저장소 분리 패턴을 따르되, Mongo adapter는 아직 만들지 않았다.
- `AnalysisService`가 job idempotency(`project_id + snapshot_id + idempotency_key`)와 candidate retry idempotency(`project_id + task_id + logical_key`)를 강제한다. 같은 logical candidate retry는 기존 candidate를 replay하고, 같은 source span을 다른 logical candidate가 참조하는 것은 허용한다.
- 런타임 literal 검증을 추가했다. Python 타입힌트만으로는 `"user_declared"` 같은 문자열 입력이 막히지 않기 때문에, candidate type/action/provenance를 enum instance로 검사한다.
- confidence는 `0.0 <= confidence <= 1.0`만 허용하고 bool/non-number를 거절한다. candidate status는 항상 `needs_review`로 기록된다.
- 전체 discovery 중 로컬 기본 Mongo가 인증 요구 상태일 때 `tests/test_core_sot_mongo.py`의 probe cleanup(`drop_database`)이 import 단계에서 실패하는 문제가 드러났다. skip-aware integration test 계약에 맞게 cleanup 실패도 Mongo 미가용으로 보고 skip되도록 test harness를 보강했다.

### Phase 2A Slice 1 독립 검증 조건 보강

- 변경 파일: `services/application/app/analysis/service.py`, `tests/test_analysis_phase2a.py`, `docs/system-contract-sot.md`, `docs/plans/02-analysis-kickoff-decisions.md`, `docs/plans/02-analysis-pipeline.md`, `HANDOFF.md`, `CHANGELOG.md`.
- 독립 검증 기록: `docs/verifications/2026-06-29/analysis_phase2a_slice1.md` 조건부 합격.
- F1/C1 해결: confidence `float("nan")`이 `0.0 <= confidence <= 1.0` 범위를 우회하던 문제를 `not (0.0 <= normalized <= 1.0)` 검사로 수정했다. NaN reject 회귀를 추가했다.
- F2/C2 해결: action≠`create` reject path를 `test_action_other_than_create_is_rejected`로 잠갔다.
- F3/C3 보강: candidate retry identity를 임시 `project_id + task_id + logical_key`로 SoT/kickoff/plan에 명시했다. `logical_key`는 비어 있지 않은 문자열이고, 첫 slice에서는 opaque key이며 derivation 규칙은 Snapshot Loader/source validation slice에서 확정한다. runtime도 non-string logical key를 거절하도록 보강했다.

### Phase 2A Snapshot Loader + candidate source validation 구현

- 변경 파일: `services/application/app/core_sot/models.py`, `core_sot/service.py`, `services/application/app/analysis/models.py`, `analysis/source.py`, `analysis/service.py`, `tests/test_analysis_source_validation.py`, 문서/HANDOFF/CHANGELOG.
- Core SOT에 `SourceSnapshotDetail`과 `CoreSotService.get_snapshot(project_id, snapshot_id)`를 추가했다. snapshot은 project_id가 맞을 때만 raw text/hash/blocks로 읽을 수 있다.
- `analysis/source.py`를 추가했다. `CoreSotSourceAdapter`는 Core SOT에서 `SourceRef`를 같은 project 기준으로 조회하고, snapshot raw text/hash/block ids를 `SnapshotText`로 로드한다.
- `CandidateSourceAnchor(source_ref_id, start_offset, end_offset, quote, content_hash)`를 추가했다.
- `AnalysisService`는 `source_ref_resolver`가 구성된 경우 `source_anchors`를 필수로 요구하고, 각 anchor를 실제 Core SOT `SourceRef`와 대조한다. source_ref 없음/cross-project/span mismatch/quote mismatch/hash mismatch/source_ref_ids-anchor mismatch를 거절한다.
- 기존 Phase 2A 순수 domain tests는 resolver 없는 service로 유지해, 인프라 없는 모델/idempotency 검증과 source validation 검증을 분리했다.

### Phase 2A 최소 taxonomy schema + fake-provider extraction adapter 구현

- 변경 파일: `services/application/app/analysis/schema.py`, `analysis/extractor.py`, `analysis/service.py`, `tests/test_analysis_extractor_schema.py`, 기존 Phase 2A/source validation tests, 문서/HANDOFF/CHANGELOG.
- 3종 taxonomy의 최소 payload schema를 확정해 SoT/plan/kickoff에 명시했다: `character_observation {name, observation}`, `event_observation {event}`, `open_question_observation {question}`. 모든 field는 non-empty string이고, 추가 field/누락 field는 malformed payload로 거절한다.
- `AnalysisService.record_candidate()`에 payload validator를 연결해 provider adapter를 우회한 저장 경로에서도 malformed payload가 저장되지 않게 했다.
- `AnalysisExtractionAdapter`를 추가했다. LLM provider(fake 포함)에 snapshot raw text를 보내고, provider content의 top-level `{candidates: [...]}` JSON object를 파싱한다.
- adapter는 candidate마다 approved type/provenance, confidence range, source_anchors shape/offset, taxonomy payload schema를 검증한다. schema 오류는 public adapter 오류인 `AnalysisExtractionError`로 통일한다.
- `logical_key` derivation을 `candidate_type + payload + source_anchors` canonical JSON SHA-256으로 잠갔다. 같은 provider retry payload는 같은 key가 되고, 같은 인물의 다른 관찰처럼 payload나 anchor가 다르면 별도 candidate가 된다.

### Phase 2A Slice2 독립 검증 G1 보강

- 변경 파일: `services/application/app/analysis/extractor.py`, `tests/test_analysis_extractor_schema.py`, `docs/system-contract-sot.md`, `docs/plans/02-analysis-kickoff-decisions.md`, `docs/plans/02-analysis-pipeline.md`, `HANDOFF.md`, `CHANGELOG.md`.
- 독립 검증 기록: `docs/verifications/2026-06-29/analysis_phase2a_slice2.md` 조건부 합격.
- G1 해결: `logical_key` derivation에서 같은 `source_anchors` set은 provider 출력 순서와 무관하게 같은 identity가 되도록 정규화했다. extractor는 anchor canonical dict를 만들고 `(source_ref_id, start_offset, end_offset, quote, content_hash)` 기준으로 정렬한 뒤 hash 입력에 넣는다.
- `test_logical_key_treats_same_anchor_set_as_order_insensitive`를 추가했다. 같은 anchor set의 순서만 바뀐 provider output은 같은 key를 만들고, anchor 내용이 달라지면 다른 key를 만든다.
- SoT를 v1.6.2로 올리고 kickoff/plan 문서에 "anchor 순서는 identity에 포함하지 않는다"를 명시해 spec-silent gap을 닫았다.

### Phase 2A Slice3 독립 검증 non-blocking 보강

- 변경 파일: `services/application/app/analysis/extractor.py`, `tests/test_analysis_extractor_schema.py`, `docs/system-contract-sot.md`, `docs/plans/02-analysis-kickoff-decisions.md`, `docs/plans/02-analysis-pipeline.md`, `HANDOFF.md`, `CHANGELOG.md`.
- 독립 검증 기록: `docs/verifications/2026-06-29/analysis_phase2a_slice3.md` 합격.
- D1 보강: `source_anchors`를 identity에서 unordered set으로 끝까지 취급하기 위해 동일 anchor 중복을 정규화한다. adapter parsing 단계에서 duplicate anchor를 하나로 접고, `_logical_key()` 직접 호출 경로도 `_dedupe_source_anchors()`를 거친다.
- `test_logical_key_treats_duplicate_anchor_as_same_set_member`를 추가했다. `[A]`와 `[A, A]`는 같은 logical_key이며 parsed draft의 anchor도 하나로 접힌다. `[A, B]`는 `[A]`와 다른 key다.
- D2 보강: SoT 상단 계약 버전과 문서 역할 표를 `v1.6.3`으로 갱신했다.
- D3 보강: ordered evidence chain이 필요해지면 provider 배열 순서를 암묵적으로 쓰지 않고 `sequence`/`evidence_order` 같은 명시 필드로 후속 계약화한다고 SoT/plan/kickoff에 남겼다.

### Phase 2A extraction runner/job orchestration 구현

- 변경 파일: `services/application/app/analysis/runner.py`, `analysis/service.py`, `analysis/repository.py`, `tests/test_analysis_runner.py`, `tests/test_analysis_phase2a.py`, 문서/HANDOFF/CHANGELOG.
- `AnalysisExtractionRunner`를 추가했다. runner는 `AnalysisJob` idempotent 생성/재사용 → Snapshot Loader → provider extraction → `AnalysisTask` 생성/재사용 → 전체 draft 사전 검증 → candidate 저장 순서로 실행한다.
- `AnalysisTask`를 `project_id + job_id + candidate_type` 단위로 재사용하게 했다. candidate retry identity가 `project_id + task_id + logical_key`이므로, same job retry에서 task_id가 흔들리면 중복 candidate가 생길 수 있기 때문이다.
- `AnalysisService.validate_candidate()`를 추가해 runner가 모든 draft를 사전 검증한 뒤 candidate write를 시작할 수 있게 했다. Job/task 생성은 idempotent setup으로 허용하지만, candidate write는 logical_key/source/schema validation이 전부 통과한 뒤 실행한다.
- runner 회귀를 추가했다. load→extract→logical_key/source validation→candidate 저장 흐름, same job retry의 job/task/candidate replay, invalid second draft가 있을 때 첫 candidate가 부분 저장되지 않음을 잠갔다.

## Issues found

- 문제: Phase 2A는 `02-analysis-pipeline.md`와 `analysis-memory-taxonomy.md` 모두에서 taxonomy와 candidate 경계를 미확정으로 남기고 있다.
- 원인: Phase 2는 최초 추출(2A)과 기존 기억 대조(2B)가 같은 문서에 있어, prior memory가 필요한 literal(`update`, `add_evidence`, `no_change`, `conflict`)을 2A에서 구현할지 모호하다.
- Resolution: 2A/2B milestone 분리와 2A `create` only를 먼저 추천안으로 명시했고, 이후 사용자 승인에 따라 SoT v1.6 계약으로 승격했다.
- Outcome: 추측 구현 대신 결정 브리프를 거쳐 승인된 Phase 2A 최소 계약을 남겼다.

- 문제: 전체 `unittest discover`가 로컬 Mongo 인증 요구 때문에 `tests/test_core_sot_mongo.py` import 단계에서 실패했다.
- 원인: `_probe_mongo()`는 `ping` 성공 뒤 transaction probe cleanup의 `drop_database`가 `OperationFailure: Unauthorized`를 내는 경우를 skip 조건으로 처리하지 않았다.
- Resolution: `drop_database` cleanup에서 `PyMongoError`가 나면 client를 닫고 `(False, False)`를 반환해 integration tests를 skip하도록 했다.
- Outcome: 전체 discovery가 다시 인프라 없이 통과한다.

- 문제: 독립 검증이 confidence NaN 관통, action≠`create` reject 회귀 부재, `logical_key` identity spec gap을 발견했다.
- 원인: Python NaN 비교는 `<`/`>`가 모두 False라 range guard를 우회했고, action reject path와 logical key 의미는 구현에는 있었지만 boundary matrix/정본에 빈칸이 있었다.
- Resolution: NaN reject 코드와 회귀, action reject 회귀, `logical_key` 임시 identity 계약 및 runtime string validation을 추가했다.
- Outcome: 검증 조건 C1/C2/C3 보강 완료. focused test는 15개에서 18개로 증가했다.

- 문제: resolver가 구성된 AnalysisService에서도 source_anchors 없이 source_ref_ids만 넘기면 Core SOT 대조 없이 candidate가 저장될 수 있었다.
- 원인: 이전 slice의 source_ref_ids-only 경로를 유지하면서 resolver 구성 여부에 따른 강제 조건을 두지 않았다.
- Resolution: `source_ref_resolver`가 있으면 `source_anchors`를 필수로 요구하고 회귀를 추가했다.
- Outcome: source validation slice에서 검증 없는 source_ref_ids-only 저장 경로를 닫았다.

- 문제: taxonomy별 payload field는 정본에 아직 없었고, 그대로 구현하면 다음 검증에서 spec-silent-but-code-enforced gap이 된다.
- 원인: kickoff은 taxonomy literal 3종까지만 승인했고 `analysis-memory-taxonomy.md`는 discussion 문서라 구현 schema가 아니라고 명시한다.
- Resolution: 소설 MVP 최초 추출의 최소 field만 SoT v1.6.1/plan/kickoff에 명시했다. 넓은 taxonomy 확장은 validator registry 구조로 후속 추가하도록 두고, 첫 schema는 타입별 필수 field만 닫았다.
- Outcome: code/test/doc이 같은 minimal payload boundary를 공유한다.

- 문제: 독립 검증이 `logical_key` derivation의 anchor 순서 민감성을 발견했다.
- 원인: canonical JSON에서 dict key는 정렬했지만 `source_anchors` list 순서는 그대로 hash 입력에 들어갔다. real provider가 같은 관찰의 anchor 순서만 바꾸면 retry idempotency가 깨질 수 있다.
- Resolution: 옵션 (a) 순서 무관 정규화를 채택했다. 같은 anchor set은 순서와 무관하게 같은 key를 만들고, anchor 내용이 다르면 별도 candidate identity가 된다.
- Outcome: Phase 2A idempotency 경계가 provider 출력 순서 흔들림에 안정적이 됐다.

- 문제: slice3 독립 검증이 source anchor set 의미론의 잔여 edge와 문서 누락을 non-blocking으로 지적했다(D1 duplicate anchor, D2 SoT version field, D3 ordered evidence forward path).
- 원인: G1 보강은 순서 무관 정규화에 집중했고, 동일 anchor 중복과 상단 version field/후속 ordered-evidence 확장 정책까지는 같이 닫지 않았다.
- Resolution: 동일 anchor 중복을 adapter/dedup key에서 정규화하고, SoT v1.6.3과 Phase 2A 문서에 unordered set 및 ordered-evidence 명시 필드 확장 방침을 기록했다.
- Outcome: Phase 2A `source_anchors` identity는 순서와 중복 모두에 안정적인 set 의미론으로 닫혔다.

- 문제: extraction runner가 매 retry마다 새 task를 만들면 candidate idempotency key의 `task_id`가 달라져 같은 logical candidate가 중복 저장될 수 있다.
- 원인: 이전 slice의 `create_task()`는 idempotent하지 않았고 task identity 규칙이 없었다.
- Resolution: `create_task(project_id, job_id, candidate_type)`를 job+type 단위 replay로 바꾸고, runner가 이 task를 재사용해 candidate를 저장하도록 했다.
- Outcome: same job retry가 job/task/candidate 모두를 재사용한다.

- 문제: provider extraction 결과 중 뒤쪽 candidate가 source validation에 실패하면 앞쪽 candidate만 저장되는 부분 저장이 생길 수 있다.
- 원인: job/task 실패 상태와 부분 성공 정책이 아직 미확정이다.
- Resolution: runner는 모든 draft를 먼저 `validate_candidate()`로 logical_key/source/schema 사전 검증하고, 전부 통과한 뒤에 candidate 저장을 시작한다. Job/task setup은 남을 수 있지만 candidate 부분 저장은 막는다.
- Outcome: Phase 2A runner slice는 실패 상태 저장을 추측 구현하지 않고 candidate write만 보수적으로 all-or-nothing 처리한다.

## Decisions

- 작업자 판단: 승인 전에는 Phase 2A candidate 저장소나 schema를 구현하지 않았다. 승인 후에는 첫 slice를 domain model + in-memory repository + idempotency 회귀로 제한했다. Snapshot Loader/source validation은 다음 slice로 남긴다.
- 작업자 추천: `create_source_ref` 자체는 non-idempotent primitive로 유지하고, 같은 analysis job/task retry 중복 방지는 Phase 2 candidate/job 저장층에서 담당한다. 같은 span을 여러 candidate가 합법적으로 참조할 수 있으므로 source_ref 원시 API에 dedupe를 넣으면 후보 trace와 idempotency 의미가 섞인다.
- 사용자 결정: Phase 2A는 3종 taxonomy로 시작하되 확장 가능한 구조로 구현한다. `create` only, `needs_review`, confidence range-only, 2A/2B 분리, candidate/job 저장층 idempotency를 채택한다. provenance는 사용자 위임에 따라 2A에서 `source_observed`/`ai_inferred`만 적용하고 `user_declared`는 WritingBrief/Product Shell 이후로 보류한다.
- 작업자 판단: taxonomy payload 확장성은 느슨한 additional field 허용이 아니라 타입별 validator registry로 확보한다. Phase 2A 첫 schema는 malformed provider output을 빨리 잡기 위해 추가 field를 거절한다.
- 작업자 판단: `logical_key`는 사용자가 직접 넣는 opaque key에서 adapter 파생 기본값으로 전진했다. 파생 입력은 `candidate_type + payload + source_anchors`로 제한해 같은 retry는 dedupe하고 서로 다른 관찰은 과도하게 합치지 않는다.
- 작업자 판단: G1은 옵션 (a) 순서 무관 정규화로 닫는다. source anchor의 출력 순서는 후보 의미가 아니라 provider formatting 흔들림이므로 identity에 포함하지 않는다.
- 작업자 판단: duplicate anchor도 같은 이유로 identity에 포함하지 않는다. 순서나 중복이 의미가 되는 분석이 필요해지면 배열 위치가 아니라 명시적인 순서/역할 필드를 schema에 추가해야 한다.
- 작업자 판단: extraction runner slice에서는 job/task 실패 상태 저장을 구현하지 않는다. 해당 상태 전이는 아직 계약이 없으므로 candidate write 부분 저장을 막는 사전 검증까지만 구현한다.

## Verification

- 문서 링크 확인: `docs/plans/README.md`에서 신규 브리프를 읽는 순서에 추가했다.
- 계약 충돌 확인: `docs/system-contract-sot.md`의 미확정 목록과 `02-analysis-pipeline.md` 착수 전 결정사항을 대조했고, 승인 전 브리프는 추천안으로 표시했다.
- 승인 반영 확인: SoT v1.6, `02-analysis-kickoff-decisions.md`, `02-analysis-pipeline.md`, `HANDOFF.md`가 같은 Phase 2A literal을 가리키는지 확인했다.
- focused: `python3 -m py_compile services/application/app/analysis/models.py services/application/app/analysis/repository.py services/application/app/analysis/service.py tests/test_analysis_phase2a.py` 통과.
- focused: `python3 -m unittest tests.test_analysis_phase2a -v` → 18개 통과.
- focused + Mongo skip harness: `python3 -m unittest tests.test_analysis_phase2a tests.test_core_sot_mongo -v` → 45개 중 18개 통과, Mongo 통합 27개 skip.
- 전체: `python3 -m unittest discover -s tests` → 241개 통과(27 skip).
- pattern sweep: Phase 2A literal/idempotency/source_ref 패턴을 검색했고, `user_declared` 문자열이 런타임에서 통과할 수 있는 경계를 발견해 enum instance 검증과 회귀를 추가했다. Mongo probe cleanup line은 `git blame`상 2026-06-28 skip-aware integration slice에서 들어온 것으로 확인했다.
- 검증 보강 후 pattern sweep: `nan`/`_validate_action`/`logical_key`/`user_declared` 경계를 재검색해 코드·테스트·정본 문서에 매핑됨을 확인했다.
- source validation focused: `python3 -m py_compile services/application/app/analysis/source.py services/application/app/analysis/models.py services/application/app/analysis/service.py services/application/app/core_sot/models.py services/application/app/core_sot/service.py tests/test_analysis_source_validation.py` 통과.
- source validation focused: `python3 -m unittest tests.test_analysis_source_validation tests.test_analysis_phase2a -v` → 25개 통과.
- 전체: `python3 -m unittest discover -s tests` → 248개 통과(27 skip).
- source validation pattern sweep: `source_anchors`/`CandidateSourceAnchor`/`load_snapshot`/`source_ref_ids`를 검색해 source_ref 없음, cross-project, span/quote/hash mismatch, anchor id mismatch, resolver 구성 시 anchors 필수 경계가 코드·테스트·문서에 매핑됨을 확인했다.
- taxonomy schema focused: `python3 -m py_compile services/application/app/analysis/schema.py services/application/app/analysis/extractor.py services/application/app/analysis/service.py tests/test_analysis_extractor_schema.py tests/test_analysis_phase2a.py tests/test_analysis_source_validation.py` 통과.
- taxonomy schema focused: `python3 -m unittest tests.test_analysis_extractor_schema tests.test_analysis_source_validation tests.test_analysis_phase2a -v` → 30개 통과.
- 전체: `python3 -m unittest discover -s tests` → 253개 통과(27 skip).
- G1 보강 focused: `python3 -m unittest tests.test_analysis_extractor_schema tests.test_analysis_source_validation tests.test_analysis_phase2a -v` → 31개 통과.
- G1 보강 focused: `python3 -m py_compile services/application/app/analysis/extractor.py tests/test_analysis_extractor_schema.py` 통과.
- G1 보강 pattern sweep: `logical_key`/`source_anchors`/anchor 순서 문구를 검색해 code/test/SoT/plan/kickoff에 순서 무관 계약이 매핑됨을 확인했다.
- 전체: `python3 -m unittest discover -s tests` → 254개 통과(27 skip).
- Slice3 보강 focused: `python3 -m unittest tests.test_analysis_extractor_schema tests.test_analysis_source_validation tests.test_analysis_phase2a -v` → 32개 통과.
- Slice3 보강 focused: `python3 -m py_compile services/application/app/analysis/extractor.py tests/test_analysis_extractor_schema.py` 통과.
- Slice3 보강 pattern sweep: `v1.6.3`/`unordered set`/`동일 anchor 중복`/`sequence`/`evidence_order`/`_dedupe_source_anchors`를 검색해 code/test/SoT/plan/kickoff에 매핑됨을 확인했다.
- 전체: `python3 -m unittest discover -s tests` → 255개 통과(27 skip).
- runner focused: `python3 -m unittest tests.test_analysis_runner tests.test_analysis_extractor_schema tests.test_analysis_source_validation tests.test_analysis_phase2a -v` → 37개 통과.
- runner focused: `python3 -m py_compile services/application/app/analysis/runner.py services/application/app/analysis/service.py services/application/app/analysis/repository.py tests/test_analysis_runner.py tests/test_analysis_phase2a.py` 통과.
- 전체: `python3 -m unittest discover -s tests` → 260개 통과(27 skip).

## Next steps

- Analysis Mongo repository/persistence를 추가한다. candidate/needs_review 중심 Mongo 저장, job/task/candidate idempotency index, runner replay를 Mongo 양 경로에서 잠근다.
- 실제 llama.cpp endpoint가 준비되면 `scripts/benchmark_llm_provider.py`를 실행해 budget/retry production 기본 숫자를 확정한다.
