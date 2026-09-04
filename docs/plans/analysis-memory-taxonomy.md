# 분석 대상과 Narrative Memory 분류 논의안

상태: **이행됨 — 설계 근거로 보존**. 논의안이 taxonomy 3종(`character_observation`·`event_observation`·`open_question_observation`)으로 확정·구현됐다.  
결정 시점: Phase 2 착수 전  
목적: “무엇을 분석하고 어떤 단위로 저장할지”를 먼저 합의하기 위한 검토 목록이다. 아래 항목은 구현 확정 schema가 아니다.

## 먼저 구분할 세 가지

분석 결과를 모두 같은 종류의 사실로 저장하지 않는다.

| 성격 | 예시 | 필요한 보호 장치 |
|---|---|---|
| 원문 사실 | 인물 이름, 실제 발생 사건, 등장 장소 | 정확한 span/quote와 entity resolution |
| 해석적 분석 | 분위기, 주제, 감정 변화, 장면 기능 | 분석 관점, confidence, 복수 해석 허용 |
| 창작 의도/계획 | 작품 목표, 장면 목표, 예정된 떡밥 회수 | 사용자 입력 출처와 AI 추론을 분리 |

같은 “분위기”라도 사용자가 WritingBrief에 지정한 의도와 완성된 장면에서 AI가 관찰한 분위기는 서로 다른 값이다. 같은 “목표”도 작품 목표, 인물 목표, 장면 목표를 섞어 저장하면 안 된다.

## 분석 대상 후보

| 영역 | 세부 후보 | 가능한 scope | 주요 논점 |
|---|---|---|---|
| 작품 정체성 | premise, genre, audience, theme | project/work | 사용자 설정과 AI 관찰을 분리할지 |
| 분위기·톤 | mood, tone, tension, emotional color | work/arc/chapter/scene/span | 단일 label, 복수 label, 시간에 따른 변화 |
| 목표·의도 | project goal, character goal, scene purpose, desired effect | project/character/scene | 명시된 의도와 추론된 목표의 구분 |
| 줄거리·구조 | synopsis, plot arc, chapter summary, scene beat | work/arc/chapter/scene | 요약 version과 원문 version 연결 |
| 인물 | identity, traits, motivation, goal, state, voice | character + time/scene | 변하지 않는 특성과 시점 상태 구분 |
| 사건 | event, cause, consequence, participants | event/scene/timeline | 서술 순서와 작품 내 시간 구분 |
| 장소·세계관 | location, organization, item, concept, world rule | entity/project | 설정 사실과 장면에서 관찰된 상태 구분 |
| 관계 | relationship type, attitude, change, history | entity pair + time/scene | 방향성과 유효 기간, 양측 관점 |
| 떡밥·질문 | setup, clue, open question, intended payoff, resolution | work/arc/scene | 실제 암시와 AI가 제안한 가능성 구분 |
| 시점·지식 | POV holder, known/unknown facts, reveal point | scene/character/time | 부재를 “모른다”로 과잉 추론하지 않기 |
| 문체·표현 | narration style, sentence rhythm, dialogue style, motifs | work/chapter/character | 본문 근거와 선호 규칙 분리 |
| 품질·위험 | contradiction, ambiguity, continuity risk | finding scope | 기억 자체가 아니라 finding으로 둘지 |

## 저장 모델 논의

모든 항목을 별도 MongoDB collection으로 만들 필요는 없다. 다음 세 계층을 비교해 결정한다.

1. 독립 identity와 lifecycle이 있는 대상: character, location, event처럼 독립 문서 후보
2. 특정 대상/장면에 종속된 속성: mood observation, character state처럼 scoped observation 후보
3. 검토 과정의 판단: contradiction, ambiguity처럼 gate/review finding 후보

공통적으로 검토할 필드는 다음과 같다.

```text
project_id
memory_type / subtype
scope_type / scope_id
value or structured payload
provenance: user_declared | source_observed | ai_inferred
source_refs
confidence
status
valid_from / valid_until 또는 scene range
version / supersedes
analysis_job_id
```

이 필드 이름과 literal도 아직 확정 계약은 아니다.

## 기존 기억과의 대조

새 snapshot 분석은 관련 기억을 먼저 검색한 뒤 다음 작업 중 하나를 제안한다.

| 작업 후보 | 의미 | 예시 |
|---|---|---|
| `create` | 대응하는 기존 기억이 없음 | 새 인물 또는 새 떡밥 등장 |
| `update` | 같은 기억의 값이나 유효 상태가 바뀜 | 인물 목표 변화, 떡밥 회수 |
| `add_evidence` | 값은 같고 새 원문 근거가 추가됨 | 기존 성격 특성을 다른 장면이 보강 |
| `no_change` | 기존 기억과 의미 있는 차이가 없음 | 같은 설정의 반복 언급 |
| `conflict` | 기존 canon/confirmed 기억과 양립하기 어려움 | 장소 설정 또는 timeline 모순 |
| `merge/split proposal` | identity 경계가 잘못되었을 가능성 | 별칭 인물을 중복 생성했거나 동명이인 발견 |

AI는 이 작업을 직접 실행하지 않고 근거와 비교 결과를 포함한 candidate로 낸다. 특히 `update`는 기존 문서를 덮어쓰지 않고 이전 version과 source를 보존해야 한다.

## Agentic 분석 + RAG 대조 흐름

```text
새 snapshot과 분석 task
→ 검색 질의 생성: type/scope/name/semantic clues
→ ES/Chroma 후보 검색
→ MongoDB에서 기존 기억과 version/status/source 재조회
→ 새 근거와 기존 기억을 함께 Analysis AI에 제공
→ create/update/add_evidence/no_change/conflict 제안
→ schema/source/comparison Gate
→ 사용자 검토 또는 허용된 versioned upsert
→ 영향받은 index 재생성
```

비교용 ContextPackage는 Writing AI용 ContextPackage와 목적이 다르다. 기존 값, 상태, source, version, 비교 이유가 반드시 포함되어야 하며 Phase 2B/4에서 별도 계약을 정한다.

## 유형별로 따로 결정할 것

각 분석 대상은 최소한 다음 질문에 답한 뒤 MVP schema에 들어간다.

- 어떤 scope에서 존재하는가?
- 원문 사실, 해석, 사용자 의도 중 무엇인가?
- source_ref가 항상 가능한가? 불가능하면 어떤 provenance가 필요한가?
- 시간이나 scene에 따라 변하는가?
- 같은 대상인지 판별하는 key는 무엇인가?
- update와 새 record의 경계는 무엇인가?
- conflict가 발생하면 자동 처리 가능한가?
- Writing/Search/Gate 중 실제 소비자가 있는가?

마지막 질문에 답하지 못하는 분석 항목은 “나중에 쓸지도 모르는 데이터”가 되기 쉬우므로 MVP에서 제외한다.

## 우선 논의할 질문

- [ ] 첫 제품은 소설 중심 taxonomy로 제한할지
- [ ] 분위기를 사용자 의도와 AI 관찰 두 종류로 저장할지
- [ ] 목표를 project/character/scene 중 어디까지 추출할지
- [ ] 줄거리 요약을 work/arc/chapter/scene 중 어느 레벨까지 유지할지
- [ ] 떡밥의 `possible_payoff`처럼 추론적인 값의 저장 위치와 상태
- [ ] update 자동 적용을 허용할 memory type이 있는지
- [ ] 복수 해석을 병렬 candidate로 유지할지
- [ ] Phase 2A 최초 추출의 최소 대상과 Phase 2B 이후 대상

## 관련 계획과 아이디에이션

- [`02-analysis-pipeline.md`](02-analysis-pipeline.md)
- [`04-agentic-search.md`](04-agentic-search.md)
- [`06-review-ui.md`](06-review-ui.md)
- [`../analysis_pipeline.md`](../analysis_pipeline.md)
- [`../mongo_collections.md`](../mongo_collections.md)
