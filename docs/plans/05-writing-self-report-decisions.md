# 착수 결정 브리프 — Phase 5.4 Writing candidate structured report

상태: `Resolved` (D1=A·D4=A·D6=A first→C, D2=A first→B, D3=A then B committed, D5=B)
관련: SoT v1.6.70, `05-writing-generation-decisions.md` Q2(평문 prose), `05-writing-gate-decisions.md`, `writing_agent_prompt.md` §12, agent-loop top-level `self_report=finalize|defer` 종료채널(별도 계약)

## Decision needed

WritingCandidate의 `self_reported_constraints`, `candidate_claims`, `new_memory_hints`, `risk_notes`를 실제로 채울 주체·wire schema·생성 실패 의미를 확정해야 한다. 평문 prose 계약을 JSON 생성으로 되돌리면 v1.6.68 결정과 충돌하고, 아이디에이션의 context pointer를 그대로 허용하면 모델이 보지 못한 Mongo id를 만들 수 있다.

## Owner decisions — 2026-07-12

- **D1=A, D4=A**: 별도 1-turn extractor, strict parse+1회 repair/계속 실패 502.
- **D2=A first→B**: 첫 slice는 pointer 없는 최소 typed schema. stable ContextPackage pointer가 extractor 입력에 제공되는 후속에서 full `related_context_pointers` schema로 확장한다.
- **D3=A then B committed**: generate 기본 합성을 먼저 구현하고, 동일 extractor를 재사용하는 별도 `/writing/report` 재평가 API를 후속 필수 기능으로 확정한다.
- **D5=B**: Gate와 Analysis가 candidate report를 모두 소비한다. Analysis 소비의 authority/provenance 방식은 D6에서 확정한다.
- **D6=A first→C**: accepted report를 AnalysisJob에 immutable advisory copy로 영속하고 snapshot 독립 extraction의 보조 prompt로만 사용한다. WritingCandidate/stable candidate id 영속화 후 별도 report entity(C)+`report_id` 참조로 승격한다. direct candidate/memory mint는 금지한다.

## Options table

### D1 — 구조 필드 생성 주체

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. prose 후 별도 1-turn report extractor | 평문 candidate와 ContextPackage를 별도 LLM이 JSON으로 분석한다 | 평문 생성 계약 보존, 창작과 자기보고 책임 분리 | LLM 호출 1회 증가 |
| B. 생성 응답을 prose+JSON wrapper로 변경 | 생성 모델이 한 응답에 모두 출력한다 | 호출 수가 적다 | v1.6.68 Q2를 뒤집고 긴 한국어 prose JSON fragility가 돌아온다 |
| C. Writing Gate가 report도 생성 | Gate 한 turn이 판정과 report를 함께 반환한다 | 호출 수 절약, Gate가 이미 candidate를 읽음 | 검증 finding과 분석용 hint 책임이 결합되고 Gate schema가 비대해진다 |

추천: **A**. 내부 LLM 호출 수보다 정확도를 우선한다는 기존 결정과 맞고, 각 컴포넌트의 실패/repair를 독립 검증할 수 있다.

### D2 — 첫 slice schema

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 최소 typed schema, pointer 제외 | constraints=`str[]`; claim=`{text,type,requires_gate_check}`; hint=`{type,text,confidence,should_analyze_after_save}`; risk=`{type,severity,message}` | 모델이 실제로 판별 가능한 필드만 엄격 검증 | source pointer 연결은 후속 |
| B. 아이디에이션 full schema | claim에 `related_context_pointers`까지 포함 | 장기 schema와 가까움 | 현재 compact ContextPackage가 pointer id를 모델에 제공하지 않아 hallucinated id 위험 |
| C. 전부 자유문자열 배열 | 네 필드를 모두 `str[]`로 둔다 | 구현이 작다 | Gate/Analysis가 type·severity·confidence를 기계적으로 소비하기 어렵다 |

채택: **A first→B**. claim type=`narrative_event|character_state|location_state|relation_change|timeline_fact|foreshadowing_use|factual_claim|interpretation`; hint type=`event|character_fact|location_fact|relation|foreshadowing|timeline_fact|style_signal`; risk type=`pov|timeline|canon|foreshadowing|relation|style|factuality`, severity=`low|medium|high|critical`, confidence=`0..1`로 잠근다. stable pointer 입력이 생기면 B로 확장한다.

### D3 — generate API 결합

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. `/writing/generate`가 prose→report를 순차 실행해 enriched candidate 반환 | H1의 필드가 실제 기본 생성물에 항상 채워진다 | generate latency 증가, report 장애 시 partial candidate 의미 필요 |
| B. 별도 `/writing/report` API | 기존 generate 응답/latency 불변 | 클라이언트가 호출을 빼먹으면 필드가 계속 비어 있음 |
| C. A+B 동시 제공 | orchestration과 재평가 모두 가능 | 첫 slice에 중복 public surface |

채택: **A then B committed**. `WritingService`는 평문 생성 책임을 유지하고 상위 `WritingCandidateReportService`를 generate endpoint가 후속 호출하는 느슨한 합성으로 둔다. 동일 extractor의 별도 `/writing/report` 재평가 API는 후속 필수 기능으로 구현한다.

### D4 — report 실패와 repair

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. strict parse + 1회 repair, 계속 실패하면 502 | 필드가 비어 있는데 성공처럼 반환하지 않고 local model JSON 흔들림을 1회 복구 | prose는 생성됐지만 응답 전체가 실패한다 |
| B. strict parse, repair 없음 | 단순하고 호출 수가 고정 | 로컬 모델의 사소한 JSON 오류에 취약 |
| C. 실패 시 빈 report로 degrade success | prose 가용성을 우선 | 구조 필드가 실제 채워진다는 계약을 깨고 Gate가 위험 신호를 잃는다 |

추천: **A**. generate는 아직 candidate를 영속하지 않으므로 실패한 prose commit은 없고, 재요청 비용만 발생한다. 정확도 우선·성공 위장 금지 원칙과 맞는다.

### D5 — 첫 소비 경계

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. Gate는 report를 입력으로 소비, Analysis는 accepted snapshot 재분석 유지 | risk/claim을 즉시 Gate 검증 보조로 쓰고 canon write는 기존 Analysis 근거 경로를 보존 | new_memory_hints가 Analysis 입력으로 직접 전달되지는 않음 |
| B. Gate와 Analysis job 모두 report를 직접 소비 | 원래 의도에 가장 가까움 | Analysis job schema/persistence/source grounding을 동시에 변경해야 함 |
| C. 필드만 채우고 소비 없음 | 최소 producer slice | 소비자 없는 speculative data가 됨 |

채택: **B**. Gate와 Analysis가 report를 모두 소비한다. 단, Analysis에서 report가 advisory인지 candidate 직접 mint 입력인지는 D6에서 확정한다.

### D6 — Analysis의 report 소비 authority

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. advisory report를 AnalysisJob에 영속, runner가 snapshot 독립 extraction의 보조 prompt로 소비 | accepted snapshot/source_ref가 계속 정본이고 report는 누락 후보를 알려주는 힌트다 | AnalysisJob schema/repository/prompt 확장 필요 | report가 직접 candidate가 되지는 않는다 |
| B. report claim/hint에서 AnalysisCandidate 직접 mint | report가 즉시 분석 후보가 된다 | 빠르고 중복 LLM extraction을 줄임 | source_ref grounding 없이 AI 자기주장을 candidate로 승격해 기존 Analysis validation 경계를 우회한다 |
| C. report를 별도 advisory store에 저장하고 Analysis는 id만 참조 | 책임 분리가 가장 명확하고 재사용 가능 | 신규 persistence/entity/API가 필요해 slice가 커진다 |

추천: **A**. report는 `ai_inferred` advisory 입력이며 Analysis runner는 accepted snapshot을 다시 읽고 기존 source_ref/schema validation을 통과한 candidate만 기록한다. report 내용 자체로 candidate를 직접 만들거나 memory에 쓰지 않는다. accept가 report를 서버에서 재검증/재추출한 뒤 새 pending job에 immutable copy로 연결하고, replay는 같은 copy를 재사용한다.

## Recommendation + reason

**D1=A, D2=A first→B, D3=A then B committed, D4=A, D5=B, D6=A**를 추천한다. 평문 창작 품질을 보존하면서 구조 필드를 실제 생성 경로에 채우고, Gate와 Analysis 정확도를 높이되 Analysis/canon 경계를 우회하지 않는 방향이다.

## Follow-up considerations

- compact ContextPackage에 stable pointer를 제공하는 계약이 생기면 claim pointer를 additive로 연다.
- 별도 report 재평가 API는 candidate persistence/identity가 생긴 뒤 같은 extractor를 재사용한다.
- Analysis ingestion은 hint provenance=`ai_inferred`, accepted snapshot source anchors, 중복 extraction 우선순위를 별도 결정한다.
- 이 candidate report는 agent-loop 종료채널 top-level `self_report=finalize|defer`와 이름·책임이 완전히 다르다. wire에서 `self_report`라는 field를 재사용하지 않는다.

## Deferred / out of scope

- context pointer 생성/검증
- new_memory_hints의 직접 memory write 또는 Analysis candidate mint
- candidate/report 영속화
- agent-loop runner 통합과 종료채널 변경
- revise/outline/critique task report variants

## 승인 후 첫 회귀 경계

1. prose 생성 평문 계약 불변; 별도 extractor request가 candidate+ContextPackage를 포함.
2. 네 report field가 enriched WritingCandidate와 HTTP response에 나타남.
3. enum/required/exact fields/confidence range strict parser; NaN/bool confidence 거부.
4. malformed first output→repair 1회→valid 성공; repair도 invalid→502.
5. provider fault/timeout은 성공 위장 없이 기존 502/504.
6. project/request/candidate identity mismatch는 provider 호출 전 400.
7. 빈 배열은 유효; unsupported fact가 없는 정상 prose를 억지 claim으로 만들 필요 없음.
8. Gate prompt가 report를 받지만 report만으로 pass/block을 결정하지 않고 기존 strict Gate schema 유지.
9. candidate report는 agent-loop `self_report` 종료채널로 파싱되지 않음.
10. 기존 accept는 enriched/legacy-empty candidate 모두 text 기준 재평가 가능하며 canon 직접 write 없음.
