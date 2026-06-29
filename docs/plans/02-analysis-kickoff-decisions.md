# Phase 2A 착수 결정 브리프

상태: `Approved for Phase 2A kickoff`  
기준 문서: [`system-contract-sot.md`](../system-contract-sot.md), [`02-analysis-pipeline.md`](02-analysis-pipeline.md), [`analysis-memory-taxonomy.md`](analysis-memory-taxonomy.md)  
승인일: `2026-06-29`  
목적: Phase 2A 구현 전에 추측 구현을 피하기 위해 필요한 최소 결정을 한 화면에 모은다.

## 현재 확정된 경계

- Phase 2A는 prior memory 없이 저장된 snapshot과 직접 근거만 사용한다.
- 모든 분석 출력은 `analysis_candidate`이며 Gate 또는 사용자 승인 없이 canonical이 되지 않는다.
- Analysis AI는 원문에 없는 사실을 보충하지 않고, 기존 기억을 직접 덮어쓰거나 merge하지 않는다.
- 모든 후보는 같은 `project_id`의 `source_ref`로 원문 근거를 다시 찾을 수 있어야 한다.
- archive 상태에서 `source_ref` 생성은 허용되어 있다.
- `create_source_ref` primitive는 non-idempotent로 유지하고, Phase 2A candidate/job 저장층이 retry idempotency를 소유한다.

## 승인된 착수 결정

### 1. Phase 2A 최소 taxonomy

결정: 소설 원고 MVP의 최초 추출은 다음 3종으로 시작한다.

| 후보 유형 | 성격 | 이유 |
|---|---|---|
| `character_observation` | 원문 사실 + 제한적 해석 | Writing/Search가 가장 먼저 소비하고 source span으로 검증하기 쉽다. |
| `event_observation` | 원문 사실 | 줄거리 continuity와 장면 요약의 기본 단위다. |
| `open_question_observation` | 해석적 분석 | 떡밥/미해결 질문을 canonical 사실로 승격하지 않고 후보로 보존하기 좋다. |

확장 후보: mood/tone, theme, voice/style, location/world rule, relation, character goal/state. 첫 구현은 3종으로 제한하지만, schema와 저장 모델은 이 후보들이 후속 taxonomy로 추가될 수 있게 닫힌 단일 타입 구조로 만들지 않는다.

### 2. provenance literal

결정: Phase 2A에서는 `source_observed`와 `ai_inferred`만 허용한다.

- `source_observed`: 원문에 직접 명시된 사실이다.
- `ai_inferred`: 원문 근거에서 추론한 해석이다. canonical 사실처럼 취급하지 않는다.

사용자 위임에 따른 작업자 결정: `user_declared`는 WritingBrief/Product Shell 입력 계약이 생긴 뒤 추가한다. Phase 2A는 저장된 snapshot 분석이므로 사용자 의도 입력까지 provenance에 섞지 않는다.

### 3. candidate action literal

결정: Phase 2A candidate action은 `create`만 허용한다.

이유: prior memory 대조가 없으므로 `update`, `add_evidence`, `no_change`, `conflict`를 판단할 근거가 없다. 이 literal들은 Phase 2B에서 Phase 3~4 search/context 계약과 함께 확정한다.

### 4. candidate 상태

결정: Phase 2A 저장 상태는 `needs_review`로 고정한다.

이유: `confirmed`와 `canonical`의 의미 및 자동 승격 여부가 SoT 미확정 목록에 남아 있다. 첫 slice에서는 추출 결과를 저장하되 사용자 검토 전 canon으로 보이지 않게 하는 것이 안전하다.

### 5. confidence threshold

결정: 공통 최소값 `0.0 <= confidence <= 1.0`만 schema로 강제하고, 자동 reject threshold는 두지 않는다.

이유: 후보 상태가 `needs_review` 고정이면 낮은 confidence도 근거와 함께 검토 대상으로 남길 수 있다. 자동 차단 임계값은 유형별 품질 fixture를 만든 뒤 정한다.

NaN confidence는 `0.0 <= confidence <= 1.0` 범위 밖이므로 거절한다.

### 6. source_ref idempotency

결정: `create_source_ref` 자체는 계속 non-idempotent primitive로 둔다. Phase 2A candidate 저장소가 idempotency boundary를 소유하고, 같은 job/task retry는 같은 logical candidate를 중복 저장하지 않도록 한다.

이유: 같은 span을 여러 후보가 참조할 수 있고, source_ref는 immutable snapshot 주석에 가깝다. 원시 `create_source_ref`에 dedupe를 넣으면 후보별 trace와 재시도 의미가 섞인다.

첫 slice의 candidate retry identity는 `project_id + task_id + logical_key`다. `logical_key`는 비어 있지 않은 문자열이며, Snapshot Loader와 taxonomy별 schema가 확정되기 전까지 caller가 제공하는 opaque key로 취급한다. logical key derivation 규칙은 다음 source validation/schema slice에서 확정한다.

검증 방향:

- 같은 analysis task retry가 동일 logical candidate를 중복 생성하지 않음.
- 서로 다른 candidate가 같은 source span을 참조하는 정상 사례를 과도하게 막지 않음.

### 7. 2A/2B milestone 분리

결정: 2A와 2B를 별도 milestone로 분리한다.

이유: 2B의 prior memory 대조는 Phase 3 indexing과 Phase 4 context/search 계약이 있어야 안전하다. 2A를 먼저 끝내면 snapshot loader, candidate schema, source_ref 검증, job 상태 관리까지 독립적으로 검증할 수 있다.

## 추천 최소 slice

다음 순서로 진행한다.

1. `AnalysisJob`/`AnalysisTask`/`AnalysisCandidate` domain model과 in-memory repository 추가  
   검증: project isolation, job retry idempotency, `needs_review` 고정.
2. Snapshot Loader와 candidate source validation 추가  
   검증: 같은 project source_ref만 허용, quote/hash/span mismatch 거절.  
   완료: `CandidateSourceAnchor(source_ref_id, start_offset, end_offset, quote, content_hash)`와 Core SOT adapter로 잠금.
3. 3종 taxonomy의 최소 schema와 fake-provider extraction adapter 추가  
   검증: under-strict/over-strict 회귀, malformed payload 거절.

## 승인된 결정 요약

- 최소 taxonomy는 3종(`character_observation`, `event_observation`, `open_question_observation`)으로 시작한다.
- 후속 확장을 염두에 두되, 첫 slice에서 넓은 taxonomy를 추측 구현하지 않는다.
- provenance는 `source_observed`/`ai_inferred`만 허용하고 `user_declared`는 WritingBrief/Product Shell 이후로 미룬다.
- Phase 2A candidate action은 `create` only다.
- 모든 Phase 2A candidate는 `needs_review`로 저장하고 자동 승격은 미룬다.
- `create_source_ref` primitive는 non-idempotent로 유지하고 candidate/job 저장층에서 retry idempotency를 맡는다.
- candidate retry identity는 `project_id + task_id + logical_key`이며, `logical_key`는 비어 있지 않은 문자열이다. 첫 slice에서는 opaque key로 두고 derivation 규칙은 다음 slice에서 확정한다.
- Phase 2A와 2B는 별도 milestone로 분리한다.
