# agentic_search_flow.md

# Personal Writing AI System — Agentic Search Flow

Version: `0.1.0-draft`  
Status: `architecture draft`  
Depends on:

- `contracts.md`
- `mongo_collections.md`

Primary SOT: `MongoDB`  
Semantic Cache: `ChromaDB`  
Lexical Index: `Elasticsearch`  
Primary Consumers:

- `Writing AI`
- `Analysis AI`
- `Gate / Verification Layer`
- `Editor / Chat UI`

---

## 0. Purpose

이 문서는 개인 글쓰기 AI 시스템에서 가장 중요한 검색 계층인 **Agentic Search System**의 설계와 실행 흐름을 정의한다.

Agentic Search는 단순 검색 API가 아니다.

이 시스템에서 Agentic Search는 다음 역할을 가진다.

```text
1. 사용자 요청 또는 AI 내부 요청을 검색 가능한 하위 문제로 분해한다.
2. MongoDB, ChromaDB, Elasticsearch 중 어떤 저장소를 어떤 순서로 사용할지 결정한다.
3. ChromaDB와 Elasticsearch의 검색 결과를 후보로만 취급한다.
4. 모든 최종 컨텍스트는 MongoDB SOT에서 재로드한다.
5. 검색 결과를 Writing AI / Analysis AI가 사용할 수 있는 ContextPackage로 조립한다.
6. Context Gate를 통해 오염, stale index, project boundary violation, 과잉 컨텍스트를 막는다.
7. 모든 검색 계획, 검색 결과, SOT 재로드, 압축, 제외 사유를 trace로 남긴다.
```

핵심 원칙은 다음이다.

```text
Writing AI는 검색하지 않는다.
Analysis AI도 검색하지 않는다.
AI들은 pointer를 요청하고, Agentic Search가 데이터를 공급한다.
MongoDB는 SOT다.
ChromaDB와 Elasticsearch는 검색 경로다.
ContextPackage는 AI에게 전달되는 유일한 지식 패키지다.
```

---

## 1. System Position

### 1.1 전체 구조에서의 위치

```text
User / Editor / Chat
        │
        ▼
Application API
        │
        ├── Writing AI
        │       │
        │       └── needs context
        │
        ├── Analysis AI
        │       │
        │       └── needs known entities / prior context
        │
        ▼
Agentic Search System
        │
        ├── Elasticsearch
        ├── ChromaDB
        └── MongoDB SOT
                │
                ▼
ContextPackage
        │
        ▼
Context Gate
        │
        ▼
Writing AI / Analysis AI / Gate
```

Agentic Search는 AI와 저장소 사이의 경계면이다.

AI가 직접 저장소를 탐색하면 다음 문제가 생긴다.

```text
- LLM hallucination으로 source_ref를 조작할 위험
- ChromaDB 결과를 SOT처럼 오해할 위험
- stale index 결과를 그대로 사용할 위험
- 프로젝트 간 기억 오염 위험
- 검색 trace가 불명확해지는 문제
- Writing AI prompt가 검색 로직으로 오염되는 문제
```

따라서 검색 책임은 Agentic Search에 고정한다.

---

## 2. Core Principles

### 2.1 Search Is Not Truth

검색 결과는 진실이 아니라 후보이다.

```text
Elasticsearch hit = lexical candidate
ChromaDB hit = semantic candidate
MongoDB reload = source-of-truth payload
ContextPackage = gated, selected, compressed context
```

Agentic Search는 다음을 금지한다.

```text
- ChromaDB document text를 그대로 canon으로 제공
- Elasticsearch document body를 그대로 canon으로 제공
- source_ref 없는 구조화 기억을 확정 정보처럼 제공
- project_id가 다른 데이터를 섞어 제공
- stale index 결과를 숨기고 제공
```

---

### 2.2 Always Reload SOT

Agentic Search의 기본 규칙:

```text
Any external index hit must be resolved through MongoDB before it enters ContextPackage.
```

즉:

```text
ChromaDB hit
→ vector metadata에서 mongo_collection, mongo_id, mongo_version 확보
→ MongoDB에서 해당 document reload
→ version 비교
→ source_refs 검증
→ ContextItem 생성

Elasticsearch hit
→ document metadata에서 mongo_collection, mongo_id, mongo_version 확보
→ MongoDB에서 해당 document reload
→ version 비교
→ source_refs 검증
→ ContextItem 생성
```

---

### 2.3 Pointer-First Context

AI에게는 거대한 DB가 아니라 pointer-backed context만 제공한다.

ContextItem은 항상 다음을 포함해야 한다.

```json
{
  "kind": "character",
  "payload": {},
  "pointers": [
    {
      "project_id": "project_001",
      "mongo_collection": "entities",
      "mongo_id": "char_arin",
      "mongo_version": 4,
      "source_refs": ["src_ch01_s02_020_090"]
    }
  ]
}
```

---

### 2.4 Plan Before Search

Agentic Search는 무작정 검색하지 않는다.

먼저 SearchPlan을 만든다.

```text
Request
→ Intent Classification
→ Need Decomposition
→ SearchPlan
→ Retrieval Execution
→ SOT Resolution
→ Ranking
→ Compression
→ ContextPackage
→ ContextGate
```

---

### 2.5 Search Must Be Explainable

모든 검색에는 trace가 있어야 한다.

Trace에는 다음이 남아야 한다.

```text
- 왜 검색했는가
- 어떤 tool을 썼는가
- 어떤 query를 썼는가
- 어떤 filter를 걸었는가
- 어떤 후보가 나왔는가
- 어떤 후보가 제외되었는가
- 어떤 MongoDB 문서를 재로드했는가
- 어떤 context item이 최종 포함되었는가
```

---

## 3. Agentic Search Responsibilities

### 3.1 Agentic Search가 해야 하는 일

```text
- 검색 의도 분류
- 검색 요구사항 분해
- 검색 계획 생성
- 저장소 라우팅
- Elasticsearch 쿼리 생성
- ChromaDB 쿼리 생성
- MongoDB SOT 재로드
- stale index 감지
- project boundary 검증
- 중복 결과 병합
- entity graph 확장
- timeline / POV constraint 조회
- context ranking
- context compression
- ContextPackage 생성
- Context Gate 호출
- search trace 저장
```

---

### 3.2 Agentic Search가 하면 안 되는 일

```text
- 최종 산문 작성
- draft text 생성
- canon 직접 변경
- analysis candidate 확정
- user preference 임의 변경
- ChromaDB / Elasticsearch 결과를 SOT처럼 취급
- source_ref 생성 또는 위조
- project_id가 다른 데이터 결합
```

---

## 4. Module Architecture

### 4.1 Internal Components

```text
AgenticSearchService
├── RequestNormalizer
├── SearchIntentClassifier
├── NeedDecomposer
├── QueryPlanner
├── ToolRouter
├── ElasticsearchRetriever
├── ChromaRetriever
├── MongoRetriever
├── MongoSOTResolver
├── EntityResolverClient
├── GraphExpander
├── TimelineResolver
├── POVResolver
├── CandidateMerger
├── ContextRanker
├── ContextCompressor
├── EvidenceFormatter
├── ContextPackageBuilder
├── ContextGateClient
└── TraceLogger
```

---

### 4.2 Component Responsibilities

| Component | Responsibility |
|---|---|
| `RequestNormalizer` | 요청을 표준 구조로 변환 |
| `SearchIntentClassifier` | 검색 목적 분류 |
| `NeedDecomposer` | 필요한 정보 유형 분해 |
| `QueryPlanner` | 검색 단계 계획 |
| `ToolRouter` | ES / Chroma / Mongo 사용 결정 |
| `ElasticsearchRetriever` | lexical / metadata 검색 |
| `ChromaRetriever` | semantic vector 검색 |
| `MongoRetriever` | 직접 SOT 쿼리 |
| `MongoSOTResolver` | index hit를 MongoDB 정본으로 재로드 |
| `GraphExpander` | 관계 기반 확장 |
| `TimelineResolver` | 사건 순서 및 유효 시점 조회 |
| `POVResolver` | 인물 지식 상태 조회 |
| `CandidateMerger` | 중복 후보 병합 |
| `ContextRanker` | 중요도 점수화 |
| `ContextCompressor` | token budget에 맞게 압축 |
| `EvidenceFormatter` | 원문 근거 formatting |
| `ContextPackageBuilder` | 최종 ContextPackage 생성 |
| `ContextGateClient` | Context Gate 호출 |
| `TraceLogger` | 전체 실행 기록 저장 |

---

## 5. Search Request Types

Agentic Search는 여러 consumer의 요청을 받는다.

### 5.1 Writing Context Search

Writing AI가 글을 쓰기 전에 필요한 맥락을 요청한다.

예:

```text
“아린이 노스워치에 도착하는 장면을 이어서 써줘.
단검 떡밥은 살짝만 건드리고,
레온의 배신은 아직 모르는 상태로.”
```

Required context:

```text
- current scene
- relevant characters
- current character state
- location context
- open foreshadowing
- timeline constraints
- POV knowledge constraints
- voice profile
- recent events
```

---

### 5.2 Analysis Context Search

Analysis AI가 저장된 글을 분석하기 전에 기존 entity/setting을 조회한다.

예:

```text
이번 장면에 등장한 “은빛 눈의 검사”가 기존 “아린”인지 확인하기 위한 known entities context.
```

Required context:

```text
- known entities
- aliases
- recent references
- existing relations
- existing unresolved foreshadowings
```

---

### 5.3 Continuity Check Search

Writing Gate 또는 Continuity Gate가 검증을 위해 검색한다.

예:

```text
생성된 문장: “아린은 레온의 배신을 떠올렸다.”
검증 질문: scene_014 시점에서 아린이 레온의 배신을 알고 있는가?
```

Required context:

```text
- timeline_facts
- character_knowledge
- relation status
- reveal event
```

---

### 5.4 Canon Lookup Search

사용자 또는 AI가 특정 설정을 조회한다.

예:

```text
“노스워치 설정 알려줘.”
“검은 태양 문양은 어디서 처음 나왔지?”
```

Required context:

```text
- canonical memory
- confirmed memory
- source_refs
- first_seen / introduced_at
```

---

### 5.5 Foreshadowing Search

미회수 떡밥을 찾는다.

예:

```text
“이번 장면에 넣을 만한 미회수 떡밥 찾아줘.”
```

Required context:

```text
- unresolved foreshadowings
- related items
- related organizations
- last mention
- possible payoff
```

---

### 5.6 Voice / Style Search

문체 샘플이나 스타일 규칙을 찾는다.

예:

```text
“내 예전 어두운 장면 문체로 고쳐줘.”
```

Required context:

```text
- voice_samples
- style_profiles
- style_rules
- forbidden_phrases
- preferred_patterns
```

---

## 6. Standard Input Contract

### 6.1 ContextSearchRequest

```json
{
  "search_request_id": "search_req_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "requesting_agent": "writing_ai",
  "purpose": "writing_context",
  "query": "아린이 노스워치에 도착하는 장면",
  "instruction": "단검 떡밥은 살짝만 건드리고, 레온의 배신은 아직 모르는 상태로.",
  "needs": [
    "character_state",
    "location_context",
    "open_foreshadowing",
    "timeline",
    "pov",
    "voice"
  ],
  "current_position": {
    "draft_id": "draft_003",
    "draft_version_id": "draft_v012",
    "snapshot_id": "snap_draft_003_v12",
    "chapter_id": "chapter_06",
    "scene_id": "scene_014",
    "cursor_offset": 1800
  },
  "context_budget": {
    "max_tokens": 6000,
    "macro_context_tokens": 2500,
    "micro_evidence_tokens": 2500,
    "reserve_tokens": 1000
  },
  "policies": {
    "always_reload_sot": true,
    "include_candidate_memory": false,
    "include_confirmed_memory": true,
    "include_canonical_memory": true,
    "allow_cross_project_memory": false,
    "include_source_quotes": true,
    "max_source_quotes": 8
  }
}
```

---

### 6.2 Required Fields

```text
search_request_id
project_id
user_id
requesting_agent
purpose
query
context_budget
policies
```

---

### 6.3 Optional but Important Fields

```text
instruction
needs
current_position
draft_pointer
selected_text
target_entities
target_scene
target_chapter
style_profile_id
writing_brief_id
```

---

## 7. Search Purpose Taxonomy

### 7.1 Purpose Values

```text
writing_context
analysis_context
continuity_check
canon_lookup
entity_lookup
scene_lookup
source_evidence_lookup
foreshadowing_lookup
timeline_lookup
relationship_lookup
voice_lookup
style_lookup
debug_trace_lookup
```

---

### 7.2 Need Values

```text
current_scene
recent_scenes
character_state
character_knowledge
location_context
event_context
open_foreshadowing
related_foreshadowing
timeline
pov
relationship
canon
source_quote
voice
style
user_preference
```

---

## 8. Full Flow Overview

### 8.1 Main Flow

```text
1. Receive ContextSearchRequest
2. Normalize request
3. Classify search intent
4. Decompose needs
5. Generate SearchPlan
6. Execute retrieval steps
7. Merge raw candidates
8. Resolve all candidates through MongoDB SOT
9. Detect stale or invalid candidates
10. Expand graph if needed
11. Resolve timeline and POV constraints
12. Rank context items
13. Compress context items
14. Build ContextPackage
15. Run Context Gate
16. Persist trace
17. Return ContextPackage
```

---

### 8.2 Sequence Diagram

```text
Consumer
  │
  │ ContextSearchRequest
  ▼
AgenticSearchService
  │
  ├─ RequestNormalizer
  │
  ├─ SearchIntentClassifier
  │
  ├─ NeedDecomposer
  │
  ├─ QueryPlanner
  │       │
  │       └── SearchPlan
  │
  ├─ ToolRouter
  │       ├── ElasticsearchRetriever
  │       ├── ChromaRetriever
  │       └── MongoRetriever
  │
  ├─ CandidateMerger
  │
  ├─ MongoSOTResolver
  │       └── MongoDB SOT
  │
  ├─ GraphExpander
  │
  ├─ TimelineResolver / POVResolver
  │
  ├─ ContextRanker
  │
  ├─ ContextCompressor
  │
  ├─ ContextPackageBuilder
  │
  ├─ ContextGateClient
  │
  └─ TraceLogger
          │
          ▼
ContextPackage
```

---

## 9. Request Normalization

### 9.1 Goal

사용자의 자연어 요청 또는 내부 AI 요청을 일관된 구조로 바꾼다.

입력 예:

```text
“아린이 노스워치 도착하는 장면 이어서. 단검 떡밥만 살짝.”
```

정규화 결과:

```json
{
  "normalized_query": "아린 노스워치 도착 장면 단검 떡밥",
  "entities_mentioned": ["아린", "노스워치", "단검"],
  "possible_needs": [
    "character_state",
    "location_context",
    "open_foreshadowing",
    "timeline",
    "pov"
  ],
  "task_hint": "continue_scene"
}
```

---

### 9.2 Normalization Tasks

```text
- Trim noisy text
- Extract named entities
- Extract explicit constraints
- Extract negative constraints
- Extract style hints
- Extract current document pointer
- Expand aliases if already known
- Determine likely purpose
```

---

## 10. Intent Classification

### 10.1 Classifier Output

```json
{
  "intent": "writing_context",
  "confidence": 0.94,
  "sub_intents": [
    {
      "name": "character_state",
      "target": "아린"
    },
    {
      "name": "location_context",
      "target": "노스워치"
    },
    {
      "name": "open_foreshadowing",
      "target": "단검"
    },
    {
      "name": "pov",
      "target": "아린"
    }
  ],
  "risk_level": "medium",
  "requires_sot_reload": true,
  "requires_context_gate": true
}
```

---

### 10.2 Risk Levels

```text
low
medium
high
critical
```

Risk Examples:

| Risk | Example |
|---|---|
| `low` | 분위기 참고, 문체 참고 |
| `medium` | 이어쓰기, 장소/인물 설정 사용 |
| `high` | 시점 지식, 사건 순서, 떡밥 회수 |
| `critical` | canon 변경, 중요한 반전 공개, 장기 세계관 변경 |

High or critical requests require stronger Gate checks.

---

## 11. Need Decomposition

### 11.1 Purpose

하나의 요청을 검색 가능한 필요 단위로 나눈다.

예시 요청:

```text
“아린이 노스워치에 도착하는 장면을 이어서 써줘.
단검 떡밥은 살짝만 건드리고,
레온의 배신은 아직 모르는 상태로.”
```

Need decomposition:

```json
[
  {
    "need_id": "need_character_arin",
    "type": "character_state",
    "target": "아린",
    "priority": "high"
  },
  {
    "need_id": "need_location_northwatch",
    "type": "location_context",
    "target": "노스워치",
    "priority": "high"
  },
  {
    "need_id": "need_knife_foreshadow",
    "type": "open_foreshadowing",
    "target": "단검",
    "priority": "high"
  },
  {
    "need_id": "need_pov_arin",
    "type": "pov",
    "target": "아린",
    "priority": "critical"
  },
  {
    "need_id": "need_recent_events",
    "type": "recent_scenes",
    "target": "scene_014",
    "priority": "medium"
  },
  {
    "need_id": "need_voice",
    "type": "voice",
    "target": "style_default",
    "priority": "medium"
  }
]
```

---

### 11.2 Need Priority

```text
critical
high
medium
low
optional
```

Priority affects:

```text
- search depth
- source quote inclusion
- ranking boost
- context budget allocation
- gate strictness
```

---

## 12. SearchPlan Generation

### 12.1 SearchPlan Schema

```json
{
  "search_plan_id": "search_plan_001",
  "project_id": "project_001",
  "search_request_id": "search_req_001",
  "purpose": "writing_context",
  "risk_level": "medium",
  "steps": [
    {
      "step_id": "step_001",
      "need_id": "need_character_arin",
      "target": "character_state",
      "query": "아린",
      "query_variants": ["아린", "은빛 눈의 검사"],
      "tools": ["elasticsearch", "mongo"],
      "filters": {
        "project_id": "project_001",
        "entity_type": "character",
        "memory_status": ["confirmed", "canonical"]
      },
      "top_k": 5,
      "must_reload_sot": true
    }
  ],
  "created_at": "2026-06-23T00:00:00Z"
}
```

---

### 12.2 SearchPlan Step Fields

| Field | Description |
|---|---|
| `step_id` | Unique step ID |
| `need_id` | Need this step satisfies |
| `target` | Target need type |
| `query` | Main query |
| `query_variants` | Alias or expanded queries |
| `tools` | Retrieval tools |
| `filters` | Project and status filters |
| `top_k` | Max candidates |
| `must_reload_sot` | Usually true |
| `rerank_policy` | Optional |
| `budget_hint` | Optional |

---

## 13. Tool Routing Strategy

### 13.1 Routing Table

| Need | Primary Tool | Secondary Tool | Final |
|---|---|---|---|
| `character_state` | Elasticsearch | MongoDB | MongoDB SOT |
| `character_knowledge` | MongoDB | Elasticsearch | MongoDB SOT |
| `location_context` | Elasticsearch | ChromaDB | MongoDB SOT |
| `event_context` | ChromaDB | Elasticsearch | MongoDB SOT |
| `open_foreshadowing` | MongoDB | ES + Chroma | MongoDB SOT |
| `timeline` | MongoDB | Elasticsearch | MongoDB SOT |
| `pov` | MongoDB | Elasticsearch | MongoDB SOT |
| `relationship` | MongoDB | ChromaDB | MongoDB SOT |
| `voice` | ChromaDB | MongoDB | MongoDB SOT |
| `style` | MongoDB | ChromaDB | MongoDB SOT |
| `source_quote` | Elasticsearch | MongoDB | MongoDB SOT |
| `scene_lookup` | Elasticsearch | ChromaDB | MongoDB SOT |

---

### 13.2 When to Prefer Elasticsearch

Use Elasticsearch when the query includes:

```text
- exact names
- aliases
- unique terms
- dialogue phrases
- symbolic objects
- chapter/scene filters
- status filters
- unresolved/resolved state
- specific source text
```

Examples:

```text
“검은 태양 문양”
“노스워치”
“은빛 눈의 검사”
“아직 회수 안 된 떡밥”
“chapter_05 이후 등장”
```

---

### 13.3 When to Prefer ChromaDB

Use ChromaDB when the query is semantic, atmospheric, or analogical.

Examples:

```text
“불길한 분위기의 장면”
“아린이 의심받던 때와 비슷한 장면”
“차갑고 폐쇄적인 도시 묘사”
“내 예전 어두운 문체”
“떡밥이 은근히 깔린 장면”
```

---

### 13.4 When to Prefer MongoDB Directly

Use MongoDB directly when the query is structural.

Examples:

```text
- character_id로 현재 상태 조회
- unresolved foreshadowings 조회
- current scene 이전 timeline fact 조회
- character knowledge 조회
- relation edge 조회
- confirmed/canonical memory 필터
- project settings / writing brief 조회
```

---

## 14. Retrieval Execution

### 14.1 Execution Model

SearchPlan steps can be executed:

```text
sequential
parallel
hybrid
conditional
```

Recommended default:

```text
1. Run independent lexical/semantic searches in parallel.
2. Run MongoDB structural queries in parallel.
3. Merge candidates.
4. Resolve through MongoDB.
5. If critical need is missing, issue follow-up query.
```

---

### 14.2 Parallelizable Steps

```text
- character lookup
- location lookup
- voice lookup
- source quote search
- semantic scene search
```

---

### 14.3 Sequential Steps

Some steps depend on previous results.

Example:

```text
1. Search “아린”
2. Resolve char_arin
3. Use char_arin to query character_knowledge
4. Use char_arin + current_scene to query POV constraints
```

---

## 15. Elasticsearch Retrieval

### 15.1 ES Query Shape

```json
{
  "index": "writing_memory_search",
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "검은 태양 단검",
            "fields": ["title^3", "name^3", "aliases^4", "body", "summary"]
          }
        }
      ],
      "filter": [
        { "term": { "project_id": "project_001" } },
        { "terms": { "kind": ["foreshadowing", "item", "source_block"] } },
        { "terms": { "status": ["unresolved", "confirmed", "canonical"] } }
      ]
    }
  },
  "size": 10
}
```

---

### 15.2 ES Hit Contract

Every ES hit must include:

```json
{
  "mongo_collection": "foreshadowings",
  "mongo_id": "foreshadow_black_sun_knife",
  "mongo_version": 2,
  "project_id": "project_001",
  "kind": "foreshadowing",
  "score": 12.44
}
```

---

### 15.3 ES Result Handling

```text
1. Validate project_id.
2. Extract mongo pointer.
3. Record ES score.
4. Mark as lexical candidate.
5. Send to CandidateMerger.
```

---

## 16. ChromaDB Retrieval

### 16.1 Chroma Query Shape

```json
{
  "collection": "project_memory_vectors",
  "query_texts": [
    "불길하고 차가운 북부 도시 도착 장면"
  ],
  "where": {
    "project_id": "project_001",
    "kind": {
      "$in": ["source_block", "location", "scene_summary", "voice"]
    }
  },
  "n_results": 12
}
```

---

### 16.2 Chroma Hit Contract

Every Chroma hit must include metadata:

```json
{
  "vector_id": "vec_loc_northwatch_v1",
  "project_id": "project_001",
  "kind": "location",
  "mongo_collection": "locations",
  "mongo_id": "loc_northwatch",
  "mongo_version": 1,
  "source_refs": ["src_ch06_s01_000_160"],
  "distance": 0.18
}
```

---

### 16.3 Chroma Result Handling

```text
1. Validate project_id.
2. Extract mongo pointer.
3. Convert distance to semantic score.
4. Mark as semantic candidate.
5. Send to CandidateMerger.
```

---

## 17. MongoDB Direct Retrieval

### 17.1 Direct Query Examples

#### Unresolved foreshadowings

```javascript
db.foreshadowings.find({
  project_id: "project_001",
  status: { $in: ["unresolved", "developing"] },
  memory_status: { $in: ["confirmed", "canonical"] }
})
```

#### Character knowledge at scene

```javascript
db.character_knowledge.find({
  project_id: "project_001",
  character_id: "char_arin",
  "valid_at.chapter_id": { $lte: "chapter_06" }
})
```

#### Timeline constraints

```javascript
db.timeline_facts.find({
  project_id: "project_001",
  applies_to: "char_arin",
  memory_status: { $in: ["confirmed", "canonical"] }
})
```

#### Relations

```javascript
db.relations.find({
  project_id: "project_001",
  $or: [
    { from_id: "char_arin" },
    { to_id: "char_arin" }
  ],
  memory_status: { $in: ["confirmed", "canonical"] }
})
```

---

### 17.2 Mongo Direct Result Handling

Mongo direct results are already SOT, but still require:

```text
- project_id validation
- status validation
- source_refs validation
- version capture
- context suitability check
```

---

## 18. Candidate Model

### 18.1 RawCandidate

```json
{
  "candidate_id": "rawcand_001",
  "source_tool": "elasticsearch",
  "need_id": "need_knife_foreshadow",
  "project_id": "project_001",
  "kind": "foreshadowing",
  "mongo_collection": "foreshadowings",
  "mongo_id": "foreshadow_black_sun_knife",
  "mongo_version": 2,
  "score": {
    "lexical": 12.44,
    "semantic": null,
    "structural": null
  },
  "source_refs": ["src_ch02_s01_084_112"],
  "raw": {}
}
```

---

### 18.2 ResolvedCandidate

```json
{
  "candidate_id": "resolved_001",
  "raw_candidate_ids": ["rawcand_001", "rawcand_008"],
  "project_id": "project_001",
  "kind": "foreshadowing",
  "mongo_collection": "foreshadowings",
  "mongo_id": "foreshadow_black_sun_knife",
  "mongo_version": 2,
  "payload": {
    "title": "검은 태양 문양의 단검",
    "setup": "낡은 단검 손잡이에 검은 태양 문양이 새겨져 있다.",
    "status": "unresolved"
  },
  "source_refs": ["src_ch02_s01_084_112"],
  "scores": {
    "lexical": 12.44,
    "semantic": 0.82,
    "structural": 1.0,
    "final": 0.91
  },
  "validity": {
    "sot_loaded": true,
    "stale": false,
    "project_scope_valid": true,
    "source_refs_valid": true
  }
}
```

---

## 19. Candidate Merge

### 19.1 Why Merge?

Same memory can be found by:

```text
- ES exact alias search
- Chroma semantic search
- Mongo structural query
```

These should not produce duplicate context.

---

### 19.2 Merge Key

Default merge key:

```text
project_id + mongo_collection + mongo_id
```

For source blocks:

```text
project_id + snapshot_id + block_id
```

For source refs:

```text
project_id + source_ref_id
```

---

### 19.3 Merge Policy

```text
- Combine raw candidate IDs.
- Keep max lexical score.
- Keep max semantic score.
- Keep structural match flag.
- Preserve all source_refs.
- Preserve all matched needs.
- Deduplicate by mongo pointer.
```

---

## 20. MongoSOTResolver

### 20.1 Purpose

Converts raw candidates into resolved candidates by loading MongoDB truth.

---

### 20.2 Resolution Steps

```text
1. Validate candidate has project_id.
2. Validate candidate project_id equals request project_id.
3. Validate mongo_collection is allowed.
4. Validate mongo_id exists.
5. Load document from MongoDB.
6. Compare mongo_version if present.
7. Validate status / memory_status.
8. Validate source_refs.
9. Attach payload.
10. Mark stale/invalid candidates.
```

---

### 20.3 Stale Detection

```python
if candidate.mongo_version is not None:
    if candidate.mongo_version != mongo_doc.version:
        candidate.validity.stale = True
        exclude_from_context(candidate)
        create_index_sync_job(candidate)
```

---

### 20.4 Missing Document Handling

If MongoDB document does not exist:

```text
- Mark candidate as invalid.
- Exclude from ContextPackage.
- Write stale/missing finding to search_trace.
- Optionally enqueue index cleanup.
```

---

## 21. Graph Expansion

### 21.1 Purpose

Some context requires related memory.

Example:

```text
User asks for 아린 scene.
Search finds char_arin.
Graph expansion finds:
- relations involving char_arin
- current location
- items owned by char_arin
- unresolved foreshadowings related to char_arin
- recent events involving char_arin
```

---

### 21.2 Expansion Rules

Graph expansion should be controlled by:

```text
need type
risk level
context budget
current scene
max depth
allowed relation types
```

Default max depth:

```text
MVP: 1
Advanced: 2
Never default above 2
```

---

### 21.3 Expansion Example

Input:

```json
{
  "seed": {
    "mongo_collection": "entities",
    "mongo_id": "char_arin"
  },
  "expansion_policy": {
    "max_depth": 1,
    "relation_types": [
      "former_ally",
      "owns",
      "located_at",
      "knows",
      "does_not_know",
      "related_foreshadowing"
    ]
  }
}
```

Output:

```json
{
  "expanded_candidates": [
    {
      "mongo_collection": "relations",
      "mongo_id": "rel_arin_leon_001"
    },
    {
      "mongo_collection": "character_knowledge",
      "mongo_id": "knowledge_arin_001"
    },
    {
      "mongo_collection": "foreshadowings",
      "mongo_id": "foreshadow_black_sun_knife"
    }
  ]
}
```

---

## 22. Timeline Resolution

### 22.1 Purpose

Writing context must be valid at the current narrative point.

TimelineResolver determines:

```text
- Which events already happened
- Which events have not happened yet
- Which facts are valid now
- Which character states are valid now
- Which reveals are still hidden
```

---

### 22.2 Input

```json
{
  "project_id": "project_001",
  "current_position": {
    "chapter_id": "chapter_06",
    "scene_id": "scene_014"
  },
  "targets": ["char_arin", "char_leon"]
}
```

---

### 22.3 Output

```json
{
  "timeline_context": {
    "already_happened": [
      "event_border_battle"
    ],
    "not_yet_happened": [
      "event_leon_betrayal_revealed"
    ],
    "active_constraints": [
      {
        "mongo_collection": "timeline_facts",
        "mongo_id": "timeline_fact_023",
        "text": "아린은 chapter_08 이전에는 레온의 배신을 알지 못한다."
      }
    ]
  }
}
```

---

## 23. POV Resolution

### 23.1 Purpose

POVResolver protects narrative perspective.

It answers:

```text
At this scene, what does this character know?
What does this character not know?
What must not appear in their dialogue or inner monologue?
```

---

### 23.2 Input

```json
{
  "project_id": "project_001",
  "character_id": "char_arin",
  "current_position": {
    "chapter_id": "chapter_06",
    "scene_id": "scene_014"
  }
}
```

---

### 23.3 Output

```json
{
  "pov_context": {
    "character_id": "char_arin",
    "knows": [
      "레온이 북부 전투에 참여했다."
    ],
    "does_not_know": [
      "레온이 왕실과 거래했다.",
      "레온이 배신자라는 사실."
    ],
    "do_not_use": [
      {
        "reason": "future_knowledge",
        "text": "아린의 내면이나 대사에 레온의 배신을 직접 넣지 말 것.",
        "pointers": [
          {
            "mongo_collection": "timeline_facts",
            "mongo_id": "timeline_fact_023"
          }
        ]
      }
    ]
  }
}
```

---

## 24. Ranking

### 24.1 Ranking Goals

Agentic Search must rank context by usefulness, not just search score.

Useful context means:

```text
- directly relevant to current request
- valid at current narrative time
- confirmed or canonical
- not stale
- not redundant
- within context budget
- has strong source refs
- matches requested tone or task
```

---

### 24.2 Ranking Features

```text
lexical_score
semantic_score
structural_score
recency_score
canon_score
source_strength_score
timeline_validity_score
pov_relevance_score
foreshadowing_relevance_score
voice_relevance_score
need_priority_score
```

---

### 24.3 Suggested Scoring Formula

For MVP:

```text
final_score =
  0.25 * lexical_score_norm
+ 0.25 * semantic_score_norm
+ 0.20 * structural_score
+ 0.15 * need_priority_score
+ 0.10 * canon_score
+ 0.05 * source_strength_score
```

For continuity or POV requests:

```text
final_score =
  0.15 * lexical_score_norm
+ 0.10 * semantic_score_norm
+ 0.30 * structural_score
+ 0.20 * timeline_validity_score
+ 0.15 * pov_relevance_score
+ 0.10 * canon_score
```

For voice/style requests:

```text
final_score =
  0.15 * lexical_score_norm
+ 0.40 * semantic_score_norm
+ 0.10 * structural_score
+ 0.20 * voice_relevance_score
+ 0.10 * recency_score
+ 0.05 * user_preference_score
```

---

## 25. Context Budgeting

### 25.1 Budget Types

```json
{
  "max_tokens": 6000,
  "macro_context_tokens": 2500,
  "micro_evidence_tokens": 2500,
  "reserve_tokens": 1000
}
```

---

### 25.2 Budget Allocation by Purpose

#### writing_context

```text
Macro context: 40%
Micro evidence: 40%
Constraints/do_not_use: 15%
Trace hints: 5%
```

#### continuity_check

```text
Constraints: 40%
Micro evidence: 40%
Macro context: 15%
Trace hints: 5%
```

#### voice_lookup

```text
Voice samples: 50%
Style rules: 30%
Forbidden/preferred patterns: 15%
Trace hints: 5%
```

---

### 25.3 Compression Policy

If context exceeds budget:

```text
1. Keep critical constraints.
2. Keep canonical/confirmed facts.
3. Keep direct source quotes.
4. Compress summaries.
5. Drop low-priority candidate memory.
6. Drop duplicate context.
7. Drop weak semantic matches.
```

Never drop:

```text
- do_not_use constraints
- critical POV constraints
- current scene summary
- directly requested entity state
```

---

## 26. ContextPackage Structure

### 26.1 Standard Output

```json
{
  "context_package_id": "ctx_001",
  "project_id": "project_001",
  "search_request_id": "search_req_001",
  "purpose": "writing_context",
  "macro_context": {
    "current_scene_summary": "...",
    "relevant_characters": [],
    "relevant_locations": [],
    "recent_events": [],
    "open_foreshadowings": [],
    "timeline_constraints": [],
    "pov_constraints": [],
    "voice_profile": {},
    "style_rules": []
  },
  "micro_evidence": [
    {
      "source_ref": "src_ch02_s01_084_112",
      "quote": "낡은 단검 손잡이에 검은 태양 문양이 새겨져 있었다.",
      "supports": "foreshadow_black_sun_knife",
      "pointers": [
        {
          "mongo_collection": "foreshadowings",
          "mongo_id": "foreshadow_black_sun_knife",
          "mongo_version": 2
        }
      ]
    }
  ],
  "constraints": [
    {
      "type": "pov",
      "priority": "critical",
      "text": "아린은 현재 시점에서 레온의 배신을 모른다.",
      "pointers": [
        {
          "mongo_collection": "timeline_facts",
          "mongo_id": "timeline_fact_023"
        }
      ]
    }
  ],
  "do_not_use": [
    {
      "reason": "future_knowledge",
      "text": "레온의 배신 사실을 아린의 내면이나 대사에 넣지 말 것.",
      "pointers": [
        {
          "mongo_collection": "timeline_facts",
          "mongo_id": "timeline_fact_023"
        }
      ]
    }
  ],
  "excluded": [
    {
      "reason": "stale_index",
      "source_tool": "chroma",
      "mongo_collection": "entities",
      "mongo_id": "char_leon",
      "index_version": 2,
      "mongo_version": 3
    }
  ],
  "trace": {
    "search_plan_id": "search_plan_001",
    "search_trace_id": "search_trace_001",
    "retrieval_ids": [],
    "resolved_mongo_ids": []
  },
  "status": "candidate"
}
```

---

### 26.2 ContextPackage Rules

```text
- Must include project_id.
- Must include search_request_id.
- Must include purpose.
- Must include trace.
- Must distinguish macro_context from micro_evidence.
- Must distinguish constraints from do_not_use.
- Must not include stale index data.
- Must not include cross-project data.
- Must label candidate memory clearly if included.
```

---

## 27. Context Gate

### 27.1 Purpose

Before AI receives context, Context Gate validates it.

---

### 27.2 Checks

```text
Project Scope Check:
- Every item project_id == request.project_id

SOT Check:
- Every ES/Chroma result has MongoDB reload

Stale Check:
- index mongo_version == current mongo version

SourceRef Check:
- source_refs exist
- quote matches source span when quote is included

Status Check:
- candidate memory is excluded unless policy allows it
- rejected/deprecated memory is excluded by default

Budget Check:
- token budget is respected

Leakage Check:
- no cross-project private memory
- no future knowledge in normal context
- future knowledge only allowed in do_not_use or Gate-only context

Completeness Check:
- critical needs have at least one answer or explicit missing finding
```

---

### 27.3 Gate Output

```json
{
  "gate_result_id": "ctx_gate_001",
  "gate_type": "context_gate",
  "context_package_id": "ctx_001",
  "decision": "pass",
  "findings": []
}
```

Possible decisions:

```text
pass
retrieve_more
needs_user_review
block
```

---

## 28. Search Trace

### 28.1 Purpose

Trace is required for observability and debugging.

---

### 28.2 SearchTrace Schema

```json
{
  "search_trace_id": "search_trace_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "search_request_id": "search_req_001",
  "search_plan_id": "search_plan_001",
  "purpose": "writing_context",
  "query": "아린이 노스워치에 도착하는 장면",
  "steps": [
    {
      "step_id": "step_001",
      "need_id": "need_character_arin",
      "tool": "elasticsearch",
      "query": "아린",
      "filters": {
        "entity_type": "character"
      },
      "result_count": 3,
      "candidate_ids": ["rawcand_001"],
      "duration_ms": 18
    },
    {
      "step_id": "step_002",
      "need_id": "need_location_northwatch",
      "tool": "chroma",
      "query": "노스워치 차가운 북부 도시",
      "result_count": 8,
      "candidate_ids": ["rawcand_008"],
      "duration_ms": 44
    },
    {
      "step_id": "step_003",
      "tool": "mongo",
      "action": "sot_reload",
      "result_count": 6,
      "resolved_ids": ["char_arin", "loc_northwatch"],
      "stale_ids": [],
      "duration_ms": 12
    }
  ],
  "excluded": [
    {
      "candidate_id": "rawcand_009",
      "reason": "stale_index"
    }
  ],
  "context_package_id": "ctx_001",
  "gate_result_id": "ctx_gate_001",
  "status": "completed",
  "created_at": "2026-06-23T00:00:00Z"
}
```

---

## 29. Follow-up Search

### 29.1 When to Run Follow-up Search

Agentic Search may run follow-up search when:

```text
- critical need has no result
- Context Gate returns retrieve_more
- ambiguous entity resolution
- too many stale results
- high-risk writing task lacks timeline/POV constraints
- user explicitly asks for more evidence
```

---

### 29.2 Follow-up Search Example

Initial search failed to identify “단검”.

Follow-up plan:

```json
{
  "reason": "critical_need_missing",
  "missing_need": "open_foreshadowing",
  "expanded_queries": [
    "단검",
    "낡은 단검",
    "문양 손잡이",
    "검은 태양 문양",
    "칼 손잡이"
  ],
  "tools": ["elasticsearch", "chroma"]
}
```

---

## 30. Error Handling

### 30.1 Standard Error Shape

```json
{
  "error": {
    "code": "SOT_RELOAD_FAILED",
    "message": "Failed to reload MongoDB source document.",
    "details": {
      "mongo_collection": "entities",
      "mongo_id": "char_arin"
    },
    "retryable": true
  }
}
```

---

### 30.2 Error Codes

```text
INVALID_SEARCH_REQUEST
PROJECT_SCOPE_VIOLATION
SEARCH_PLAN_FAILED
ELASTICSEARCH_ERROR
CHROMA_ERROR
MONGO_ERROR
SOT_RELOAD_FAILED
STALE_INDEX_RESULT
SOURCE_REF_MISMATCH
ENTITY_RESOLUTION_AMBIGUOUS
CONTEXT_BUDGET_EXCEEDED
CONTEXT_GATE_FAILED
NO_RELEVANT_CONTEXT
```

---

### 30.3 Failure Policy

| Error | Policy |
|---|---|
| ES unavailable | Use Chroma + Mongo fallback |
| Chroma unavailable | Use ES + Mongo fallback |
| Mongo unavailable | Fail closed |
| SOT reload failed | Exclude candidate |
| Context Gate blocked | Do not send context to AI |
| Critical need missing | retrieve_more or ask user |
| Project scope violation | block and audit |

---

## 31. Fallback Strategy

### 31.1 MongoDB Must Not Be Optional

If MongoDB is unavailable, Agentic Search must fail closed.

Reason:

```text
MongoDB is SOT.
Without MongoDB, the system cannot verify search results.
```

---

### 31.2 ES Failure

If Elasticsearch fails:

```text
- Continue with ChromaDB for semantic search.
- Use MongoDB direct filters for known structural needs.
- Mark lexical coverage degraded in trace.
```

---

### 31.3 Chroma Failure

If ChromaDB fails:

```text
- Continue with Elasticsearch for lexical search.
- Use MongoDB direct filters.
- Mark semantic coverage degraded in trace.
```

---

### 31.4 Both ES and Chroma Fail

If both indices fail:

```text
- Use MongoDB direct queries only.
- Limit functionality to structural queries.
- Do not perform broad semantic search.
- Return degraded ContextPackage if enough structural context exists.
```

---

## 32. Extensibility Design

### 32.1 Retriever Plugin Interface

Agentic Search should support new retrieval tools.

Examples:

```text
MongoRetriever
ElasticsearchRetriever
ChromaRetriever
GraphRetriever
FilesystemRetriever
WebRetriever
CalendarRetriever
GmailRetriever
CustomLoreRetriever
```

Interface:

```python
class Retriever:
    name: str
    supported_needs: list[str]

    def can_handle(self, step: SearchStep) -> bool:
        ...

    def retrieve(self, step: SearchStep, request: ContextSearchRequest) -> list[RawCandidate]:
        ...

    def healthcheck(self) -> RetrieverHealth:
        ...
```

---

### 32.2 New Memory Type Extension

To add a new memory type, define:

```text
1. MongoDB collection or entity type
2. ChromaDB representation
3. Elasticsearch document representation
4. Search need type
5. Tool routing rule
6. ContextItem formatter
7. Gate rules
```

Example: `theme_motif`

```text
MongoDB:
- concepts or motifs collection

ChromaDB:
- motif summary embedding

Elasticsearch:
- motif name / symbol / repeated phrase

Search need:
- motif_context

Gate:
- avoid overusing motif
```

---

### 32.3 New Index Extension

If adding a new index, it must follow this rule:

```text
NewIndex hit → MongoDB pointer → MongoSOTResolver → ContextItem
```

No index may bypass MongoDB.

---

### 32.4 New Agent Extension

If adding another agent, such as `PlotPlannerAI`, it must consume Agentic Search through ContextSearchRequest.

```text
PlotPlannerAI
→ requests plot_context
→ receives ContextPackage
→ outputs plot_candidate
→ PlotGate validates
```

---

## 33. Security and Isolation

### 33.1 Project Boundary

Every query must include:

```json
{
  "project_id": "project_001"
}
```

Every retrieved item must match the same `project_id`.

If not:

```text
- exclude item
- mark PROJECT_SCOPE_VIOLATION
- block if violation is systemic
```

---

### 33.2 User Boundary

For single-user local MVP, user boundary may be simple.

For multi-user use:

```text
- verify user_id owns project_id
- verify all loaded documents belong to user
- never use cross-user indices
```

---

### 33.3 Private Memory Leakage

Some memory may be marked private.

Example:

```json
{
  "privacy": {
    "level": "private",
    "allowed_purposes": ["writing_context"],
    "disallowed_purposes": ["export", "public_summary"]
  }
}
```

Agentic Search must respect privacy policy.

---

## 34. API Design

### 34.1 Context Search API

```http
POST /api/projects/{project_id}/search/context
```

Request:

```json
{
  "requesting_agent": "writing_ai",
  "purpose": "writing_context",
  "query": "아린이 노스워치에 도착하는 장면",
  "instruction": "단검 떡밥은 살짝만 건드리고, 레온의 배신은 아직 모르는 상태로.",
  "needs": [
    "character_state",
    "location_context",
    "open_foreshadowing",
    "timeline",
    "pov",
    "voice"
  ],
  "current_position": {
    "draft_id": "draft_003",
    "draft_version_id": "draft_v012",
    "snapshot_id": "snap_draft_003_v12",
    "chapter_id": "chapter_06",
    "scene_id": "scene_014"
  },
  "context_budget": {
    "max_tokens": 6000
  }
}
```

Response:

```json
{
  "context_package_id": "ctx_001",
  "gate_decision": "pass",
  "context_package": {},
  "trace_id": "search_trace_001"
}
```

---

### 34.2 Search Plan Preview API

Useful for debugging.

```http
POST /api/projects/{project_id}/search/plan
```

Response:

```json
{
  "search_plan_id": "search_plan_preview_001",
  "steps": []
}
```

---

### 34.3 Search Trace API

```http
GET /api/projects/{project_id}/search/traces/{trace_id}
```

---

### 34.4 SOT Resolve API

Internal only.

```http
POST /api/projects/{project_id}/search/resolve
```

Input:

```json
{
  "candidates": [
    {
      "mongo_collection": "entities",
      "mongo_id": "char_arin",
      "mongo_version": 4
    }
  ]
}
```

---

## 35. Pseudocode

### 35.1 Main Service

```python
def build_context(request: ContextSearchRequest) -> ContextPackage:
    normalized = normalize_request(request)

    intent = classify_intent(normalized)

    needs = decompose_needs(normalized, intent)

    plan = query_planner.create_plan(
        request=normalized,
        intent=intent,
        needs=needs,
    )

    raw_candidates = []

    for batch in plan.execution_batches():
        batch_results = run_retrieval_batch(batch, request)
        raw_candidates.extend(batch_results)

    merged_candidates = candidate_merger.merge(raw_candidates)

    resolved_candidates = sot_resolver.resolve(
        candidates=merged_candidates,
        project_id=request.project_id,
    )

    expanded_candidates = graph_expander.expand_if_needed(
        candidates=resolved_candidates,
        needs=needs,
        budget=request.context_budget,
    )

    timeline_context = timeline_resolver.resolve_if_needed(
        request=request,
        candidates=expanded_candidates,
        needs=needs,
    )

    pov_context = pov_resolver.resolve_if_needed(
        request=request,
        candidates=expanded_candidates,
        needs=needs,
    )

    ranked = context_ranker.rank(
        candidates=expanded_candidates,
        timeline_context=timeline_context,
        pov_context=pov_context,
        needs=needs,
    )

    compressed = context_compressor.compress(
        ranked_items=ranked,
        budget=request.context_budget,
        must_keep=critical_constraints(timeline_context, pov_context),
    )

    package = context_package_builder.build(
        request=request,
        intent=intent,
        needs=needs,
        items=compressed,
        timeline_context=timeline_context,
        pov_context=pov_context,
    )

    gate_result = context_gate.validate(package)

    trace_logger.persist(
        request=request,
        plan=plan,
        raw_candidates=raw_candidates,
        resolved_candidates=resolved_candidates,
        package=package,
        gate_result=gate_result,
    )

    if gate_result.decision == "pass":
        return package

    if gate_result.decision == "retrieve_more":
        return run_followup_search(request, gate_result)

    raise ContextGateError(gate_result)
```

---

### 35.2 Retriever Batch

```python
def run_retrieval_batch(batch: list[SearchStep], request: ContextSearchRequest) -> list[RawCandidate]:
    results = []

    for step in batch:
        for tool_name in step.tools:
            retriever = retriever_registry.get(tool_name)

            if not retriever.can_handle(step):
                continue

            try:
                tool_results = retriever.retrieve(step, request)
                results.extend(tool_results)
            except RetrieverError as e:
                trace_logger.record_retriever_error(step, tool_name, e)

                if step.is_required and tool_name == "mongo":
                    raise

    return results
```

---

### 35.3 SOT Resolution

```python
def resolve_candidates(candidates: list[RawCandidate], project_id: str) -> list[ResolvedCandidate]:
    resolved = []

    for candidate in candidates:
        if candidate.project_id != project_id:
            mark_excluded(candidate, "PROJECT_SCOPE_VIOLATION")
            continue

        doc = mongo.load(
            collection=candidate.mongo_collection,
            id=candidate.mongo_id,
            project_id=project_id,
        )

        if doc is None:
            mark_excluded(candidate, "SOT_RELOAD_FAILED")
            enqueue_index_cleanup(candidate)
            continue

        if candidate.mongo_version and candidate.mongo_version != doc.version:
            mark_excluded(candidate, "STALE_INDEX_RESULT")
            enqueue_index_sync(doc)
            continue

        if not is_allowed_status(doc):
            mark_excluded(candidate, "STATUS_NOT_ALLOWED")
            continue

        resolved.append(make_resolved_candidate(candidate, doc))

    return resolved
```

---

## 36. Example End-to-End Flow

### 36.1 User Request

```text
아린이 노스워치에 도착하는 장면 이어서 써줘.
단검 떡밥은 살짝만 건드리고,
레온의 배신은 아직 모르는 상태로.
```

---

### 36.2 Intent

```json
{
  "intent": "writing_context",
  "risk_level": "high",
  "sub_intents": [
    "character_state",
    "location_context",
    "open_foreshadowing",
    "timeline",
    "pov",
    "voice"
  ]
}
```

---

### 36.3 SearchPlan

```json
{
  "steps": [
    {
      "target": "character_state",
      "query": "아린",
      "tools": ["elasticsearch", "mongo"]
    },
    {
      "target": "location_context",
      "query": "노스워치 북부 도시",
      "tools": ["elasticsearch", "chroma"]
    },
    {
      "target": "open_foreshadowing",
      "query": "단검 검은 태양 문양",
      "tools": ["mongo", "elasticsearch", "chroma"]
    },
    {
      "target": "pov",
      "query": "아린 레온 배신 지식 상태",
      "tools": ["mongo"]
    },
    {
      "target": "voice",
      "query": "차분하고 불길한 장면 문체",
      "tools": ["chroma", "mongo"]
    }
  ]
}
```

---

### 36.4 Retrieval

```text
ES:
- char_arin
- loc_northwatch
- foreshadow_black_sun_knife

Chroma:
- 북부 도시 장면
- 단검 암시 장면
- 어두운 문체 샘플

Mongo:
- char_arin
- loc_northwatch
- timeline_fact_023
- knowledge_arin_001
- foreshadow_black_sun_knife
```

---

### 36.5 ContextPackage Result

```json
{
  "macro_context": {
    "relevant_characters": [
      {
        "name": "아린",
        "state": "노스워치에 도착함. 레온의 배신은 아직 모름."
      }
    ],
    "relevant_locations": [
      {
        "name": "노스워치",
        "mood": ["춥다", "군사적", "폐쇄적"]
      }
    ],
    "open_foreshadowings": [
      {
        "title": "검은 태양 문양의 단검",
        "status": "unresolved",
        "use_hint": "직접 회수하지 말고 이미지로만 암시"
      }
    ]
  },
  "constraints": [
    {
      "type": "pov",
      "text": "아린은 현재 시점에서 레온의 배신을 모른다."
    }
  ],
  "do_not_use": [
    {
      "reason": "future_knowledge",
      "text": "아린의 내면이나 대사에 레온의 배신을 넣지 말 것."
    }
  ]
}
```

---

## 37. Advanced Features

### 37.1 Multi-hop Search

For complex requests, Agentic Search may perform multi-hop reasoning.

Example:

```text
“아린과 레온의 관계가 어색해진 뒤 처음 등장한 단검 관련 장면 찾아줘.”
```

Plan:

```text
1. Resolve 아린 → char_arin
2. Resolve 레온 → char_leon
3. Find relation change event
4. Find scenes after relation change
5. Search for 단검 within those scenes
6. Reload SOT
7. Return evidence
```

---

### 37.2 Query Expansion

Query expansion sources:

```text
- aliases
- related entities
- source_refs
- prior successful queries
- user-defined synonyms
- writing brief terminology
```

Example:

```text
단검
→ 낡은 단검
→ 검은 태양 문양
→ 손잡이 문양
→ 검은 태양단
```

---

### 37.3 Memory-Aware Reranking

Reranking can consider:

```text
- entity importance
- recent mention
- unresolved status
- user manually pinned memory
- canonical memory
- current chapter relevance
- gate severity history
```

---

### 37.4 Pinned Context

User may pin context.

Pinned context must be kept unless invalid.

```json
{
  "pinned_context": [
    {
      "mongo_collection": "foreshadowings",
      "mongo_id": "foreshadow_black_sun_knife"
    }
  ]
}
```

---

### 37.5 Negative Retrieval

Sometimes Agentic Search must find what must not be used.

Examples:

```text
- future reveals
- facts unknown to POV character
- deprecated canon
- rejected analysis candidates
```

Negative context goes to:

```text
do_not_use
constraints
Gate-only context
```

It should not be mixed into normal macro context.

---

## 38. Observability and Metrics

### 38.1 Metrics

Track:

```text
search_latency_ms
es_latency_ms
chroma_latency_ms
mongo_reload_latency_ms
context_gate_latency_ms
candidate_count
resolved_candidate_count
stale_candidate_count
excluded_candidate_count
context_token_estimate
gate_pass_rate
retrieve_more_rate
no_relevant_context_rate
```

---

### 38.2 Quality Metrics

Track:

```text
user_acceptance_rate
writing_candidate_revision_rate
continuity_violation_rate
pov_violation_rate
hallucinated_context_rate
stale_index_rate
manual_review_rate
```

---

### 38.3 Debug Views

Useful debug UI:

```text
- SearchPlan viewer
- Raw candidates viewer
- SOT reload viewer
- Excluded candidates viewer
- ContextPackage viewer
- Gate findings viewer
```

---

## 39. MVP Scope

### 39.1 MVP Agentic Search Components

Implement first:

```text
RequestNormalizer
SearchIntentClassifier
NeedDecomposer
QueryPlanner
ToolRouter
ElasticsearchRetriever
ChromaRetriever
MongoRetriever
MongoSOTResolver
CandidateMerger
ContextRanker
ContextCompressor
ContextPackageBuilder
ContextGateClient
TraceLogger
```

Can defer:

```text
GraphExpander depth > 1
Advanced reranker
Pinned context
Negative retrieval UI
Multi-hop search planner
Learning-to-rank
Cross-project memory
```

---

### 39.2 MVP Search Purposes

```text
writing_context
analysis_context
continuity_check
canon_lookup
foreshadowing_lookup
voice_lookup
```

---

### 39.3 MVP Need Types

```text
current_scene
recent_scenes
character_state
location_context
open_foreshadowing
timeline
pov
relationship
voice
style
```

---

### 39.4 MVP Retrieval Rules

```text
- All requests require project_id.
- All index hits must reload MongoDB SOT.
- Candidate memory is excluded by default.
- confirmed and canonical memory are allowed.
- stale index hits are excluded.
- source quotes are limited.
- Context Gate is mandatory.
```

---

## 40. Implementation Roadmap

### Phase 1: Basic Hybrid Context

```text
1. ContextSearchRequest schema
2. SearchPlan schema
3. ES Retriever
4. Chroma Retriever
5. MongoSOTResolver
6. ContextPackageBuilder
7. SearchTrace logging
```

---

### Phase 2: Writing Integration

```text
1. Writing AI calls Agentic Search
2. ContextPackage inserted into Writing prompt
3. Writing Gate consumes same context
4. user accept → save draft
```

---

### Phase 3: Analysis Integration

```text
1. Analysis AI requests known entities context
2. Entity resolution aided by Agentic Search
3. Analysis candidates linked to existing memory
```

---

### Phase 4: Continuity and POV

```text
1. TimelineResolver
2. POVResolver
3. do_not_use context generation
4. Continuity Gate integration
```

---

### Phase 5: Extensibility

```text
1. Retriever plugin registry
2. New memory type registration
3. Multi-hop planner
4. Reranking policy plugins
5. Debug UI
```

---

## 41. Final Summary

Agentic Search is the memory orchestration brain of the writing system.

Its core loop is:

```text
Request
→ Intent
→ Needs
→ Plan
→ Retrieve
→ Merge
→ MongoDB SOT Reload
→ Expand
→ Rank
→ Compress
→ ContextPackage
→ ContextGate
→ Consumer
```

The most important invariant:

```text
No AI agent receives unverified index output.
No index output bypasses MongoDB.
No context enters Writing AI without Context Gate.
```

The system becomes extensible because every new memory type, retriever, or agent follows the same rule:

```text
New source
→ pointer
→ MongoDB SOT resolution
→ ContextItem
→ ContextPackage
→ Gate
```

In short:

```text
Agentic Search does not merely search.
It plans, retrieves, verifies, ranks, compresses, explains, and safely supplies memory.
```
