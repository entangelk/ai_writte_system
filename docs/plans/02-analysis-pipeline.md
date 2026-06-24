# Phase 2. Analysis Pipeline

상태: `Draft`  
선행 조건: Phase 1 snapshot/block/source_ref 계약. update-aware 분석은 Phase 3~4도 필요  
후속 소비자: Indexing, Agentic Search, Review UI

## 목표

저장된 snapshot에서 서사·문체·의도 정보를 근거가 있는 구조화 기억 후보로 추출하고, 기존 기억이 있으면 신규 생성·갱신·근거 추가·충돌·변경 없음 중 어떤 작업이 필요한지 제안한다.

분석 대상과 저장 단위는 아직 확정하지 않는다. 논의 기준은 [`analysis-memory-taxonomy.md`](analysis-memory-taxonomy.md)를 따른다.

## 구현 slice

### Phase 2A: 최초 추출

- snapshot과 직접 근거만 사용해 초기 후보 생성
- schema/anchor/quote/confidence 검증
- 원문 초안이 제시한 Character, Event, Location, Foreshadowing, Relation은 최소 출발 후보이며 확정 목록이 아님
- candidate/needs_review 중심의 MongoDB 저장

### Phase 2B: 기존 기억 대조와 변경 제안

- Phase 3~4의 Agentic Search/RAG로 같은 프로젝트의 관련 기억 검색
- 원문 근거와 기존 기억의 version/status/source를 함께 대조
- `create`, `update`, `add_evidence`, `no_change`, `conflict` 작업 후보 생성
- 필요 시 `merge`/`split`은 자동 실행하지 않고 review 후보로 제안
- 승인된 변경만 versioned upsert와 재색인으로 연결
- 비교 작업은 [`flat-loop-gate.md`](flat-loop-gate.md)의 `analysis_compare` allowlist만 쓰는 bounded flat loop로 수행하며 sub-agent를 생성하지 않음
- `compare_memory`/`validate_candidate`는 loop 중 preflight이며, 종료 후 Analysis Gate 검사를 대체하지 않음

2A와 2B를 하나의 Phase로 구현할지, Phase 4 전후의 별도 milestone로 나눌지는 착수 전에 확정한다.

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

- [ ] [`analysis-memory-taxonomy.md`](analysis-memory-taxonomy.md)의 MVP 분석 대상과 scope 확정
- [ ] 사실·해석·의도를 구분하는 공통 provenance 계약
- [ ] create/update/add_evidence/no_change/conflict literal과 판정 경계
- [ ] confidence threshold를 공통값으로 둘지 유형별로 둘지
- [ ] `confirmed` 자동 승격을 MVP에서 허용할지
- [ ] entity resolution을 Phase 2에서 어디까지 자동화할지
- [ ] 부분 성공 job의 최종 상태와 재시도 단위
- [ ] 2A/2B를 별도 milestone로 나눌지와 2B의 prior context 계약

마지막 항목은 구현 순서상 중요하다. 최초 추출은 prior memory 없이 가능하지만, 기존 기억의 의미적 대조와 안전한 update 제안은 Phase 3~4 이후에야 완성된다.

## 원문 및 상세 참고

- [`../abstract.md`](../abstract.md) §4.2, §7, §8.8~8.13, §12.3 일부, §13.4, §14.2
- [`../analysis_pipeline.md`](../analysis_pipeline.md)
- [`../contracts.md`](../contracts.md) §4, §6.3, §9
- [`gemma4-reuse.md`](gemma4-reuse.md)
