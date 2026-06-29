# Phase 2. Analysis Pipeline

상태: `Draft` — Phase 2A kickoff subset approved on `2026-06-29`  
선행 조건: Phase 1 snapshot/block/source_ref 계약. update-aware 분석은 Phase 3~4도 필요  
후속 소비자: Indexing, Agentic Search, Review UI

## 목표

저장된 snapshot에서 서사·문체·의도 정보를 근거가 있는 구조화 기억 후보로 추출하고, 기존 기억이 있으면 신규 생성·갱신·근거 추가·충돌·변경 없음 중 어떤 작업이 필요한지 제안한다.

Phase 2A 착수 최소 계약은 [`02-analysis-kickoff-decisions.md`](02-analysis-kickoff-decisions.md)에 승인됐다. 더 넓은 분석 대상과 저장 단위는 계속 [`analysis-memory-taxonomy.md`](analysis-memory-taxonomy.md)를 논의 기준으로 삼는다.

## 구현 slice

### Phase 2A: 최초 추출

- snapshot과 직접 근거만 사용해 초기 후보 생성
- schema/anchor/quote/confidence 검증
- 최소 taxonomy는 `character_observation`, `event_observation`, `open_question_observation` 3종으로 시작
- 후속 확장을 염두에 두되 location/relation/mood/style 등은 첫 slice에서 추측 구현하지 않음
- provenance는 `source_observed`/`ai_inferred`만 허용하고 `user_declared`는 WritingBrief/Product Shell 이후로 보류
- candidate action은 `create` only
- candidate status는 `needs_review` 고정
- confidence는 `0.0 <= confidence <= 1.0`만 강제하고 자동 reject threshold는 후속 품질 fixture 이후 결정. NaN은 범위 밖이므로 거절
- `create_source_ref` primitive는 non-idempotent로 유지하며, job/task retry idempotency는 candidate 저장층이 담당
- candidate retry identity는 `project_id + task_id + logical_key`. `logical_key`는 비어 있지 않은 string이고, schema/extraction slice의 기본 derivation은 `candidate_type + payload + source_anchors` canonical JSON의 SHA-256. 같은 `source_anchors` set은 provider 출력 순서 및 동일 anchor 중복과 무관하게 같은 identity로 정규화한다
- `CandidateSourceAnchor(source_ref_id, start_offset, end_offset, quote, content_hash)`를 같은 project의 Core SOT `SourceRef`와 대조해 source_ref 없음/cross-project/span mismatch/quote mismatch/hash mismatch를 거절
- Snapshot Loader는 같은 project의 snapshot raw text, content hash, source block ids를 제공하고 cross-project snapshot 접근을 거절
- 3종 taxonomy의 최소 payload schema는 `character_observation {name, observation}`, `event_observation {event}`, `open_question_observation {question}`이다. 모든 payload field는 non-empty string이며 추가 field나 누락 field는 malformed payload로 거절한다.
- fake-provider extraction adapter는 provider content를 top-level `{candidates: [...]}` JSON object로 파싱하고, 각 candidate의 approved type/provenance/confidence/source_anchors/payload를 검증한다. `logical_key`는 `candidate_type + payload + source_anchors` canonical JSON의 SHA-256으로 만들며 anchor 순서와 동일 anchor 중복은 identity에 포함하지 않는다. 순서 의미가 필요한 ordered evidence chain은 명시 필드 추가 후 별도 계약으로 다룬다.
- extraction runner는 source validation이 구성된 `AnalysisService`만 받는다. 실행 순서는 `AnalysisJob` idempotent 생성/재사용 → Snapshot Loader → provider extraction → `AnalysisTask` 생성/재사용 → 전체 draft 사전 검증 → candidate 저장이다. Task는 `project_id + job_id + candidate_type`으로 재사용하고, candidate write는 모든 draft의 logical_key/source/schema 검증 뒤 시작한다. 같은 run의 duplicate `(task_id, logical_key)` draft는 1개로 정규화한다. Job/task 실패 상태 저장은 후속이다.
- service batch API는 같은 batch 안의 동일 `project_id + task_id + logical_key` request를 idempotent replay로 정규화한다. 첫 request는 candidate를 만들고 이후 동일 request는 같은 candidate를 반환하며, logical_key가 다른 request는 같은 batch에서도 별도 candidate로 유지한다.
- candidate/needs_review 중심의 MongoDB 저장은 `analysis_jobs`, `analysis_tasks`, `analysis_candidates` collection에 기록한다. Required idempotency indexes는 `uniq_analysis_job_request`(`project_id`, `snapshot_id`, `idempotency_key`, unique), `uniq_analysis_task_request`(`project_id`, `job_id`, `candidate_type`, unique), `uniq_analysis_candidate_request`(`project_id`, `task_id`, `logical_key`, unique)이며, job candidate list는 `analysis_candidates_by_job`(`project_id`, `job_id`) index를 사용한다. Candidate batch write는 transaction 경로에서 한 트랜잭션으로 commit하고, non-transaction fallback은 single-writer local/test 전용으로 실패 시 이번 시도에서 새로 쓴 candidate만 rollback한다.

### Phase 2B: 기존 기억 대조와 변경 제안

- Phase 3~4의 Agentic Search/RAG로 같은 프로젝트의 관련 기억 검색
- 원문 근거와 기존 기억의 version/status/source를 함께 대조
- `create`, `update`, `add_evidence`, `no_change`, `conflict` 작업 후보 생성
- 필요 시 `merge`/`split`은 자동 실행하지 않고 review 후보로 제안
- 승인된 변경만 versioned upsert와 재색인으로 연결
- 비교 작업은 [`flat-loop-gate.md`](flat-loop-gate.md)의 `analysis_compare` allowlist만 쓰는 bounded flat loop로 수행하며 sub-agent를 생성하지 않음
- `compare_memory`/`validate_candidate`는 loop 중 preflight이며, 종료 후 Analysis Gate 검사를 대체하지 않음

2A와 2B는 별도 milestone로 나눈다. 기존 기억의 의미적 대조와 안전한 update 제안은 Phase 3~4 이후 2B에서 확정한다.

## 공통 MVP 범위

- `AnalysisJob` 생성과 상태 관리
- Snapshot Loader와 span map
- 확정된 분석 taxonomy에 따른 task 분해
- 유형별 schema/anchor/quote/confidence 검증
- 기존 기억의 검색·대조와 변경 작업 후보
- candidate/needs_review 중심의 MongoDB 저장
- 분석 trace와 실패 정보

후속 증분:

- TimelineFact와 CharacterKnowledge
- style signal과 Voice RAG 입력
- diff 기반 증분 재분석
- 복잡한 graph resolution과 자동 canon 승격

## 핵심 흐름

```text
snapshot_id → AnalysisJob → Snapshot Loader
→ 분석 목적별 기존 기억 검색(2B) → task별 AI 추출/대조
→ raw schema + source anchor validation
→ entity/memory resolution → 변경 작업 후보 생성
→ Analysis Gate → review 또는 versioned upsert → Index Sync
```

## Analysis AI 경계

- snapshot pointer와 loader가 제공한 text만 분석한다.
- 원문에 없는 사실을 보충하지 않는다.
- 모든 결과에 source span/ref와 confidence를 낸다.
- 기존 대상과 같아 보이면 관련 기억과 근거를 대조하고 변경 작업을 제안한다.
- 기존 기억을 직접 덮어쓰거나 merge하지 않는다.
- canon을 확정하지 않는다.

## Analysis Gate 최소 검사

- JSON/schema 유효성
- source_ref 존재와 동일 project 확인
- span boundary와 quote/hash 일치
- 필수 필드 및 허용 literal
- confidence threshold
- 기존 기억과의 명백한 충돌
- update 대상의 version/status 일치와 stale comparison 방지
- 근거가 없는 overwrite 또는 정보 손실 여부
- 중복 후보와 retry idempotency

## 산출물

1. AnalysisJob/Task/Result/Candidate 계약
2. 합의된 taxonomy별 추출 schema와 prompt
3. Snapshot Loader
4. prior memory search/context 계약
5. schema/anchor validator
6. entity/memory resolver와 변경 작업 후보
7. Analysis Gate와 상태 전이
8. versioned upsert, 후보 저장 및 trace

## 수용 기준

- 합의된 각 후보 유형이 유형에 맞는 근거와 해석 수준을 표시해 저장된다.
- 근거 없는 추론, 잘못된 span, 다른 프로젝트 ref는 거절되거나 review로 간다.
- 기존 기억과 같은 내용은 불필요한 새 기억을 만들지 않고 `no_change` 또는 근거 추가로 처리된다.
- 새 근거가 기존 값을 바꾸면 과거 값을 덮어쓰지 않고 update/conflict 후보와 version 이력을 남긴다.
- 같은 job 재시도는 후보를 무단 중복 생성하지 않는다.
- 정상적인 낮은 확신 후보를 사실로 승격하지 않고 보존할 수 있다.
- 실패한 task가 전체 job/다른 task에 미치는 영향이 계약과 일치한다.

## 착수 전 결정사항

- [x] Phase 2A 최소 taxonomy와 scope 확정: `character_observation`, `event_observation`, `open_question_observation`
- [x] Phase 2A provenance literal 확정: `source_observed`, `ai_inferred`; `user_declared`는 WritingBrief/Product Shell 이후
- [x] Phase 2A candidate action 확정: `create` only
- [x] Phase 2A confidence 최소 계약 확정: `0.0 <= confidence <= 1.0`, 자동 reject threshold 없음
- [ ] `confirmed` 자동 승격을 MVP에서 허용할지
- [ ] entity resolution을 Phase 2에서 어디까지 자동화할지
- [ ] 부분 성공 job의 최종 상태와 재시도 단위
- [x] 2A/2B milestone 분리
- [ ] Phase 2B taxonomy 확장과 prior context 계약
- [ ] Phase 2B `update`/`add_evidence`/`no_change`/`conflict` 판정 경계

마지막 항목은 구현 순서상 중요하다. 최초 추출은 prior memory 없이 가능하지만, 기존 기억의 의미적 대조와 안전한 update 제안은 Phase 3~4 이후에야 완성된다.

## 원문 및 상세 참고

- [`../abstract.md`](../abstract.md) §4.2, §7, §8.8~8.13, §12.3 일부, §13.4, §14.2
- [`../analysis_pipeline.md`](../analysis_pipeline.md)
- [`../contracts.md`](../contracts.md) §4, §6.3, §9
- [`gemma4-reuse.md`](gemma4-reuse.md)
