# analysis_pipeline.md

# Personal Writing AI System — Analysis Pipeline

> **이 문서는 2026-06 설계 원본이다 — 현재 계약 정본이 아니다.** 확정된 계약은 [`system-contract-sot.md`](system-contract-sot.md) 를 본다. **다만 폐기되지 않았다**: 프로덕션 코드가 이 문서를 **절 번호로 인용**하므로(직접 인용은 없고 `plans/02-analysis-pipeline.md` 등 계획 문서가 참조한다) **절 번호와 절 제목을 바꾸지 말 것.** 여기 적힌 서술은 *그때의 설계 근거*로 읽는다.

Version: `0.1.0-draft`  
Status: `architecture draft`  
Depends on:

- `contracts.md`
- `mongo_collections.md`
- `agentic_search_flow.md`

Primary SOT: `MongoDB`  
Semantic Cache: `ChromaDB`  
Lexical Index: `Elasticsearch`  
Primary Producer: `Analysis AI`  
Primary Consumers:

- `Agentic Search`
- `Writing AI`
- `Continuity Gate`
- `POV Gate`
- `Foreshadowing Gate`
- `Project Memory UI`

---

## 0. Purpose

이 문서는 개인 글쓰기 AI 시스템에서 **저장된 글을 구조화 기억으로 변환하는 Analysis Pipeline**을 정의한다.

이 시스템에서 글은 단순히 저장되는 텍스트가 아니다.

저장된 글은 다음 과정을 거쳐 다음 글쓰기의 재료가 된다.

```text
Draft Save
→ Source Snapshot
→ Source Blocks
→ Analysis Job
→ Analysis Tasks
→ Analysis AI Extraction
→ Analysis Candidates
→ Analysis Gate
→ Entity Resolution
→ Memory Upsert
→ Index Sync
→ Agentic Search에서 재사용
```

핵심 아이디어는 다음이다.

```text
Writing AI는 글을 생성한다.
Analysis AI는 저장된 글을 구조화 기억으로 컴파일한다.
MongoDB는 원문과 분석 결과를 SOT로 저장한다.
ChromaDB와 Elasticsearch는 분석 결과를 검색 가능하게 만드는 파생 인덱스다.
```

---

## 1. Analysis Pipeline의 역할

### 1.1 Analysis Pipeline이 하는 일

Analysis Pipeline은 저장된 글에서 다음을 추출한다.

```text
- 장면 구조
- 인물
- 사건
- 장소
- 조직
- 물건
- 개념
- 떡밥
- 열린 질문
- 관계
- 타임라인 사실
- 인물별 지식 상태
- 세계관 규칙
- 문체 신호
```

추출 결과는 MongoDB에 candidate로 저장된다.

그 후 Gate와 Review를 거쳐 다음 상태 중 하나가 된다.

```text
candidate
confirmed
canonical
needs_review
rejected
deprecated
```

---

### 1.2 Analysis Pipeline이 하지 않는 일

Analysis Pipeline은 다음을 직접 하지 않는다.

```text
- Writing AI 대신 글을 쓰지 않는다.
- AI 추출 결과를 무조건 canon으로 승격하지 않는다.
- ChromaDB나 Elasticsearch를 SOT처럼 취급하지 않는다.
- source_ref를 LLM에게 임의 생성하게 하지 않는다.
- 원문에 없는 추측을 confirmed fact로 저장하지 않는다.
- 사용자의 승인 없이 고위험 canon 변경을 확정하지 않는다.
```

---

## 2. Core Principles

### 2.1 Source Snapshot First

분석은 항상 immutable snapshot을 기준으로 수행한다.

```text
draft_version
→ source_snapshot
→ source_blocks
→ source_refs
→ analysis
```

Analysis AI는 live editor text를 직접 분석하지 않는다.  
항상 snapshot ID를 기준으로 분석한다.

이유:

```text
- 같은 입력에 대해 재현 가능한 분석 가능
- source_ref가 안정적으로 유지됨
- 분석 결과가 어느 버전의 글에서 나온 것인지 추적 가능
- rollback / diff / review가 가능
```

---

### 2.2 SourceRef Anchoring

모든 분석 결과는 원문 근거를 가져야 한다.

예:

```json
{
  "fact": "아린은 노스워치에 도착했다.",
  "source_refs": ["src_ch06_s01_020_088"]
}
```

SourceRef 없는 추출 결과는 다음 중 하나로 처리한다.

```text
- reject
- needs_review
- hypothesis로 저장
- user_canon_note로 별도 저장
```

---

### 2.3 AI Output Is Candidate

Analysis AI의 출력은 정답이 아니다.

```text
Analysis AI Output = AnalysisCandidate
Analysis Gate = 검증
Entity Resolver = 병합 판단
User Review = canon 승격 가능
```

---

### 2.4 MongoDB Owns Derived Memory

분석 결과는 파생 데이터지만, MongoDB 안에서는 SOT로 저장된다.

구분:

```text
source_snapshot = primary SOT
analysis_candidate = derived candidate
confirmed memory = derived SOT
canonical memory = accepted canon
```

---

### 2.5 Analysis Must Be Incremental

전체 프로젝트를 매번 다시 분석하지 않는다.

기본 단위:

```text
draft_version
snapshot
chapter
scene
block
span
```

MVP에서는 `draft_version saved` 단위로 분석하고, 내부적으로 scene/block 단위로 나눈다.

향후 확장:

```text
- changed block only analysis
- diff-based reanalysis
- dependency-aware reanalysis
- affected memory invalidation
```

---

## 3. High-Level Flow

### 3.1 Full Pipeline

```text
1. Draft Save Trigger
2. Create Draft Version
3. Create Immutable Source Snapshot
4. Split Snapshot into Blocks
5. Generate SourceRefs
6. Create Analysis Job
7. Create Analysis Tasks
8. Load Analysis Context
9. Run Analysis AI
10. Validate Raw Output Schema
11. Create Analysis Candidates
12. Run Analysis Gate
13. Resolve Entities and Relations
14. Upsert Memory Collections
15. Create Review Requests if needed
16. Sync ChromaDB and Elasticsearch
17. Persist Trace and Metrics
```

---

### 3.2 Sequence Diagram

```text
Editor / Save API
    │
    │ save draft
    ▼
Draft Storage
    │
    ├── draft_versions
    ├── source_snapshots
    ├── source_blocks
    └── source_refs
    │
    ▼
AnalysisJobFactory
    │
    ├── analysis_jobs
    └── analysis_tasks
    │
    ▼
AnalysisOrchestrator
    │
    ├── SnapshotLoader
    ├── Agentic Search for prior context
    ├── Analysis AI
    ├── Schema Validator
    ├── Analysis Gate
    ├── Entity Resolver
    ├── Memory Upserter
    └── Index Sync Dispatcher
    │
    ▼
MongoDB Memory Collections
    │
    ├── entities
    ├── events
    ├── locations
    ├── foreshadowings
    ├── relations
    ├── timeline_facts
    └── character_knowledge
    │
    ▼
ChromaDB / Elasticsearch Index Sync
```

---

## 4. Module Architecture

### 4.1 Analysis Pipeline Components

```text
AnalysisPipeline
├── DraftSaveTrigger
├── SnapshotBuilder
├── BlockSplitter
├── SourceRefGenerator
├── AnalysisJobFactory
├── AnalysisTaskPlanner
├── SnapshotLoader
├── PriorContextLoader
├── AnalysisPromptBuilder
├── AnalysisModelRunner
├── RawOutputParser
├── SchemaValidator
├── SourceAnchorValidator
├── AnalysisCandidateBuilder
├── AnalysisGate
├── EntityResolver
├── RelationResolver
├── MemoryUpserter
├── ReviewRequestBuilder
├── IndexSyncDispatcher
├── AnalysisTraceLogger
└── MetricsCollector
```

---

### 4.2 Component Responsibilities

| Component | Responsibility |
|---|---|
| `DraftSaveTrigger` | 저장 이벤트 발생 |
| `SnapshotBuilder` | immutable snapshot 생성 |
| `BlockSplitter` | chapter/scene/paragraph/block 분할 |
| `SourceRefGenerator` | span 기반 source_ref 생성 |
| `AnalysisJobFactory` | analysis job 생성 |
| `AnalysisTaskPlanner` | 분석 task 분해 |
| `SnapshotLoader` | 분석 대상 text와 span map 로드 |
| `PriorContextLoader` | 기존 entity/setting 조회 |
| `AnalysisPromptBuilder` | task별 prompt 생성 |
| `AnalysisModelRunner` | LLM 호출 |
| `RawOutputParser` | JSON 출력 파싱 |
| `SchemaValidator` | task별 schema 검증 |
| `SourceAnchorValidator` | source_ref/quote 검증 |
| `AnalysisCandidateBuilder` | candidate 문서 생성 |
| `AnalysisGate` | candidate 검증 |
| `EntityResolver` | 기존 entity와 병합 판단 |
| `RelationResolver` | 관계 edge 생성/갱신 |
| `MemoryUpserter` | MongoDB memory collection 갱신 |
| `ReviewRequestBuilder` | 사용자 검토 요청 생성 |
| `IndexSyncDispatcher` | ES/Chroma 인덱싱 요청 |
| `AnalysisTraceLogger` | 분석 trace 저장 |
| `MetricsCollector` | 품질 및 성능 지표 수집 |

---

## 5. Trigger Types

### 5.1 Draft Saved

가장 일반적인 트리거.

```text
User saves draft
→ new draft_version
→ new source_snapshot
→ analysis_job
```

---

### 5.2 Manual Reanalysis

사용자가 특정 범위를 다시 분석한다.

```text
- 특정 장면 재분석
- 특정 chapter 재분석
- 특정 entity 관련 정보 재분석
- 이전 분석 결과가 마음에 들지 않을 때 재분석
```

---

### 5.3 Import Source

외부 문서, 설정 노트, 과거 글, 문체 샘플을 import할 때.

```text
external document
→ source_snapshot
→ source_blocks
→ analysis_job
```

---

### 5.4 Review Accepted

사용자가 candidate를 confirm/canonical로 승격하면 관련 인덱스를 갱신한다.

```text
review_result.confirm
→ memory update
→ index sync
```

---

### 5.5 Canon Changed

canon이 변경되면 영향을 받는 기억을 재검토한다.

```text
canon update
→ affected memory detection
→ reanalysis or deprecation
→ index sync
```

---

## 6. Analysis Job Design

### 6.1 AnalysisJob

```json
{
  "_id": "analysis_job_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "snapshot_id": "snap_draft_003_v12",
  "trigger": "draft_saved",
  "scope": {
    "draft_id": "draft_003",
    "chapter_id": "chapter_06",
    "scene_ids": ["scene_014"]
  },
  "tasks": [
    "scene_split",
    "entity_extraction",
    "event_extraction",
    "location_extraction",
    "foreshadowing_extraction",
    "relation_extraction",
    "timeline_extraction",
    "character_knowledge_extraction",
    "style_signal_extraction"
  ],
  "status": "queued",
  "created_at": "2026-06-23T00:00:00Z",
  "started_at": null,
  "finished_at": null
}
```

---

### 6.2 AnalysisJob Status

```text
queued
running
completed
failed
cancelled
partial
```

---

### 6.3 Job Scope

Job scope determines what text is analyzed.

```json
{
  "scope": {
    "type": "scene",
    "draft_id": "draft_003",
    "snapshot_id": "snap_draft_003_v12",
    "chapter_id": "chapter_06",
    "scene_ids": ["scene_014"],
    "block_ids": ["block_ch06_s01_p001", "block_ch06_s01_p002"]
  }
}
```

Scope types:

```text
project
draft
draft_version
chapter
scene
block_range
selected_span
voice_sample
imported_document
```

---

## 7. Analysis Task Planning

### 7.1 Why Task Decomposition?

하나의 LLM 호출로 모든 구조를 뽑으려 하면 다음 문제가 생긴다.

```text
- JSON schema가 커져서 실패율 증가
- token budget 초과
- 세부 추출 품질 저하
- task별 검증 불가능
- 특정 실패만 재시도하기 어려움
```

따라서 분석은 task로 나눈다.

---

### 7.2 Task Types

```text
scene_split
entity_extraction
event_extraction
location_extraction
organization_extraction
item_extraction
concept_extraction
foreshadowing_extraction
open_question_extraction
relation_extraction
timeline_extraction
character_knowledge_extraction
style_signal_extraction
summary_generation
```

---

### 7.3 MVP Task Types

MVP에서는 다음만 필수다.

```text
scene_split
entity_extraction
event_extraction
location_extraction
foreshadowing_extraction
relation_extraction
timeline_extraction
character_knowledge_extraction
```

Optional:

```text
style_signal_extraction
summary_generation
```

---

### 7.4 AnalysisTask

```json
{
  "_id": "analysis_task_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "analysis_job_id": "analysis_job_001",
  "task_type": "entity_extraction",
  "snapshot_id": "snap_draft_003_v12",
  "scope": {
    "scene_id": "scene_014",
    "block_ids": ["block_ch06_s01_p001", "block_ch06_s01_p002"]
  },
  "input_policy": {
    "include_prior_entities": true,
    "include_prior_relations": true,
    "include_candidate_memory": false
  },
  "status": "queued",
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

---

## 8. Snapshot Loading

### 8.1 SnapshotLoader Input

```json
{
  "project_id": "project_001",
  "snapshot_id": "snap_draft_003_v12",
  "scope": {
    "scene_id": "scene_014"
  }
}
```

---

### 8.2 SnapshotLoader Output

```json
{
  "snapshot_id": "snap_draft_003_v12",
  "project_id": "project_001",
  "text_package": {
    "text": "아린은 해가 기울 무렵 노스워치의 성문 앞에 도착했다...",
    "blocks": [
      {
        "block_id": "block_ch06_s01_p001",
        "order": 1,
        "text": "...",
        "start_offset": 0,
        "end_offset": 120
      }
    ],
    "span_map": [
      {
        "span_id": "span_001",
        "block_id": "block_ch06_s01_p001",
        "start_offset": 0,
        "end_offset": 120,
        "source_ref": "src_ch06_s01_000_120"
      }
    ]
  }
}
```

---

### 8.3 Loading Rules

```text
- Only load text from source_snapshots and source_blocks.
- Do not load live editor content.
- Preserve offset and source_ref mapping.
- Preserve block order.
- Include chapter_id and scene_id if available.
```

---

## 9. Prior Context Loading

### 9.1 Why Prior Context Is Needed

Analysis AI needs existing memory to avoid duplicates.

Example:

```text
Text says “은빛 눈의 검사”.
Existing entity says:
- char_arin
- aliases: ["은빛 눈의 검사"]

Analysis AI should propose matched_existing_entity_id = char_arin.
```

---

### 9.2 PriorContextLoader Uses Agentic Search

Prior context is loaded through Agentic Search.

Analysis AI does not search DB directly.

```text
AnalysisTask
→ PriorContextLoader
→ Agentic Search purpose: analysis_context
→ ContextPackage
→ Analysis AI
```

---

### 9.3 Prior Context Types

```text
known_entities
known_aliases
known_locations
known_items
known_organizations
recent_relations
open_foreshadowings
timeline_constraints
character_knowledge
```

---

### 9.4 PriorContext Package Example

```json
{
  "purpose": "analysis_context",
  "known_entities": [
    {
      "entity_id": "char_arin",
      "name": "아린",
      "aliases": ["은빛 눈의 검사"],
      "entity_type": "character"
    }
  ],
  "known_locations": [
    {
      "location_id": "loc_northwatch",
      "name": "노스워치",
      "aliases": ["북부 감시성"]
    }
  ],
  "open_foreshadowings": [
    {
      "foreshadowing_id": "foreshadow_black_sun_knife",
      "title": "검은 태양 문양의 단검",
      "status": "unresolved"
    }
  ]
}
```

---

## 10. Analysis AI Input Contract

### 10.1 Standard Input

```json
{
  "analysis_task_id": "analysis_task_001",
  "analysis_job_id": "analysis_job_001",
  "task_type": "entity_extraction",
  "project_id": "project_001",
  "snapshot_id": "snap_draft_003_v12",
  "text_package": {
    "text": "...",
    "span_map": []
  },
  "prior_context": {},
  "output_schema": "EntityExtractionResult",
  "rules": {
    "must_use_source_refs": true,
    "do_not_invent": true,
    "weak_inference_as_hypothesis": true,
    "candidate_only": true
  }
}
```

---

### 10.2 General Analysis AI System Contract

```text
너는 개인 글쓰기 시스템의 Analysis AI이다.

역할:
- 저장된 글에서 구조화 기억 후보를 추출한다.
- 원문에 명시되거나 강하게 지지되는 정보만 추출한다.
- 모든 후보는 source_ref 또는 span 근거를 가져야 한다.
- 기존 entity와 같은 대상일 가능성이 있으면 matched_existing_id를 제안한다.
- 약한 추론은 fact가 아니라 hypothesis로 표시한다.

금지:
- source_ref를 꾸며내지 않는다.
- 원문에 없는 정보를 확정하지 않는다.
- candidate를 confirmed/canonical로 표시하지 않는다.
- canon을 변경하지 않는다.
- ChromaDB/Elasticsearch를 직접 업데이트하지 않는다.

출력:
- JSON만 출력한다.
- task별 schema를 따른다.
- 모든 candidate에는 confidence와 source_refs를 포함한다.
```

---

## 11. Task-Specific Schemas

### 11.1 scene_split

Purpose:

```text
텍스트를 장면 단위로 나누고 각 장면의 요약과 목적을 추출한다.
```

Output schema:

```json
{
  "scenes": [
    {
      "scene_id_hint": "scene_014",
      "title": "노스워치 도착",
      "summary": "아린이 해질 무렵 노스워치 성문 앞에 도착한다.",
      "scene_type": "arrival",
      "start_source_ref": "src_ch06_s01_000_020",
      "end_source_ref": "src_ch06_s01_600_660",
      "participants": ["아린"],
      "locations": ["노스워치"],
      "mood": ["차가움", "불길함"],
      "confidence": 0.91
    }
  ]
}
```

---

### 11.2 entity_extraction

Purpose:

```text
등장 인물, 조직, 물건, 개념 후보를 추출한다.
```

Output schema:

```json
{
  "entities": [
    {
      "name": "아린",
      "entity_type": "character",
      "aliases": [],
      "matched_existing_id": "char_arin",
      "new_entity_suggested": false,
      "summary": "노스워치에 도착한 검사.",
      "observed_facts": [
        {
          "fact": "아린은 노스워치에 도착했다.",
          "source_refs": ["src_ch06_s01_020_088"],
          "confidence": 0.92
        }
      ],
      "source_refs": ["src_ch06_s01_020_088"],
      "confidence": 0.94
    }
  ]
}
```

---

### 11.3 event_extraction

Purpose:

```text
장면 안에서 발생한 사건과 그 결과를 추출한다.
```

Output schema:

```json
{
  "events": [
    {
      "name": "아린의 노스워치 도착",
      "event_type": "arrival",
      "summary": "아린이 해질 무렵 노스워치 성문에 도착한다.",
      "participants": ["char_arin"],
      "location_id": "loc_northwatch",
      "story_time": "해질 무렵",
      "narrative_order_hint": 14,
      "causes": [],
      "consequences": [
        "아린은 노스워치 내부로 들어갈 준비를 한다."
      ],
      "source_refs": ["src_ch06_s01_020_088"],
      "confidence": 0.9
    }
  ]
}
```

---

### 11.4 location_extraction

Purpose:

```text
장소와 장소 특성을 추출한다.
```

Output schema:

```json
{
  "locations": [
    {
      "name": "노스워치",
      "location_type": "city",
      "matched_existing_id": "loc_northwatch",
      "summary": "북부 국경의 폐쇄적인 도시.",
      "mood": ["춥다", "군사적", "폐쇄적"],
      "features": ["성문", "성벽", "검문소"],
      "source_refs": ["src_ch06_s01_000_160"],
      "confidence": 0.88
    }
  ]
}
```

---

### 11.5 foreshadowing_extraction

Purpose:

```text
떡밥, 반복 상징, 아직 설명되지 않은 단서, 잠재적 회수 포인트를 추출한다.
```

Output schema:

```json
{
  "foreshadowings": [
    {
      "title": "검은 태양 문양의 단검",
      "setup": "낡은 단검 손잡이에 검은 태양 문양이 희미하게 떠오른다.",
      "matched_existing_id": "foreshadow_black_sun_knife",
      "status_hint": "developing",
      "possible_payoff": "검은 태양단과의 연결 가능성",
      "related_entities": ["item_black_sun_knife", "org_black_sun"],
      "source_refs": ["src_ch06_s01_240_306"],
      "confidence": 0.86,
      "is_explicit": false
    }
  ]
}
```

Foreshadowing extraction rule:

```text
명시적 떡밥과 약한 상징을 구분한다.
약한 상징은 confidence를 낮게 주고 candidate 또는 needs_review로 둔다.
```

---

### 11.6 relation_extraction

Purpose:

```text
인물, 장소, 사건, 물건 사이의 관계를 추출한다.
```

Output schema:

```json
{
  "relations": [
    {
      "from": {
        "id": "char_arin",
        "name": "아린",
        "collection": "entities"
      },
      "to": {
        "id": "item_black_sun_knife",
        "name": "검은 태양 문양의 단검",
        "collection": "items"
      },
      "relation_type": "carries",
      "status_label": "current",
      "summary": "아린은 검은 태양 문양의 단검을 지니고 있다.",
      "valid_from": {
        "chapter_id": "chapter_06",
        "scene_id": "scene_014"
      },
      "valid_until": null,
      "source_refs": ["src_ch06_s01_240_306"],
      "confidence": 0.84
    }
  ]
}
```

---

### 11.7 timeline_extraction

Purpose:

```text
사건 순서, 유효 기간, 시점 제약, reveal 여부를 추출한다.
```

Output schema:

```json
{
  "timeline_facts": [
    {
      "fact": "아린은 chapter_06 scene_014 시점에 노스워치에 도착했다.",
      "constraint_type": "location_presence",
      "applies_to": ["char_arin", "loc_northwatch"],
      "valid_from": {
        "chapter_id": "chapter_06",
        "scene_id": "scene_014"
      },
      "valid_until": null,
      "source_refs": ["src_ch06_s01_020_088"],
      "confidence": 0.9
    }
  ]
}
```

---

### 11.8 character_knowledge_extraction

Purpose:

```text
현재 장면 기준으로 인물이 알고 있는 것과 모르는 것을 추출한다.
```

Output schema:

```json
{
  "character_knowledge": [
    {
      "character_id": "char_arin",
      "valid_at": {
        "chapter_id": "chapter_06",
        "scene_id": "scene_014"
      },
      "knows": [
        {
          "fact": "아린은 노스워치의 위치와 성문을 알고 있다.",
          "source_refs": ["src_ch06_s01_020_088"],
          "confidence": 0.8
        }
      ],
      "does_not_know": [
        {
          "fact": "아린은 아직 레온의 배신을 모른다.",
          "reason": "prior canonical constraint",
          "source_refs": ["src_ch05_s03_100_144"],
          "confidence": 0.95
        }
      ]
    }
  ]
}
```

---

### 11.9 style_signal_extraction

Purpose:

```text
사용자의 문체 신호를 추출한다.
```

Output schema:

```json
{
  "style_signals": [
    {
      "signal_type": "tone",
      "value": "차분하고 불길함",
      "examples": [
        {
          "quote": "성문 위의 깃발은 바람도 없이 천천히 흔들렸다.",
          "source_ref": "src_ch06_s01_100_140"
        }
      ],
      "confidence": 0.82
    }
  ]
}
```

---

## 12. Raw Output Parsing

### 12.1 Rules

Analysis AI output must be JSON.

Parser must handle:

```text
- strict JSON
- JSON with trailing prose
- malformed JSON retry
- schema mismatch
- partial output
```

MVP rule:

```text
If JSON parse fails, retry once with repair prompt.
If still fails, mark analysis_task failed.
```

---

### 12.2 Raw Output Storage

Store raw output in `analysis_results`.

```json
{
  "_id": "analysis_result_001",
  "analysis_run_id": "analysis_run_012",
  "raw_output": {},
  "schema_valid": true,
  "status": "processed"
}
```

Raw output must be preserved for debugging.

---

## 13. Schema Validation

### 13.1 Validator Responsibilities

```text
- Required fields present
- Correct data types
- confidence range 0.0 to 1.0
- source_refs are arrays
- status is not confirmed/canonical from AI
- no unknown dangerous fields
```

---

### 13.2 Validation Result

```json
{
  "schema_valid": true,
  "errors": [],
  "warnings": [
    {
      "field": "possible_payoff",
      "message": "Weak inference; should remain candidate."
    }
  ]
}
```

---

## 14. Source Anchor Validation

### 14.1 Purpose

Validates that candidate evidence actually exists in source snapshot.

---

### 14.2 Checks

```text
- source_ref exists in MongoDB
- source_ref.project_id == analysis_job.project_id
- source_ref.snapshot_id == analysis_job.snapshot_id
- quote matches source_ref span
- source_ref is within task scope
```

---

### 14.3 Failure Policy

| Failure | Action |
|---|---|
| missing source_ref | reject or needs_review |
| source_ref outside snapshot | reject |
| quote mismatch | reject |
| weak source support | candidate or needs_review |
| source exists but ambiguous | needs_review |

---

## 15. AnalysisCandidate Construction

### 15.1 Candidate Document

```json
{
  "_id": "analysis_candidate_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "analysis_result_id": "analysis_result_001",
  "analysis_job_id": "analysis_job_001",
  "analysis_task_id": "analysis_task_001",
  "candidate_type": "character_fact",
  "target_collection": "entities",
  "matched_existing_id": "char_arin",
  "proposed_new_id": null,
  "payload": {
    "fact": "아린은 노스워치에 도착했다.",
    "fact_type": "location_arrival",
    "character_id": "char_arin",
    "location_id": "loc_northwatch"
  },
  "source_refs": ["src_ch06_s01_020_088"],
  "confidence": 0.92,
  "status": "candidate",
  "gate_result_id": null,
  "review_result_id": null,
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

---

### 15.2 Candidate Type to Target Collection

| Candidate Type | Target Collection |
|---|---|
| `character` | `entities` |
| `character_fact` | `entities` or `character_knowledge` |
| `event` | `events` |
| `location` | `locations` |
| `organization` | `organizations` |
| `item` | `items` |
| `concept` | `concepts` |
| `foreshadowing` | `foreshadowings` |
| `open_question` | `open_questions` |
| `relation` | `relations` |
| `timeline_fact` | `timeline_facts` |
| `character_knowledge` | `character_knowledge` |
| `style_signal` | `style_rules` or `voice_samples` |

---

## 16. Analysis Gate

### 16.1 Purpose

Analysis Gate decides whether candidates can update memory.

---

### 16.2 Gate Inputs

```json
{
  "gate_request_id": "analysis_gate_req_001",
  "project_id": "project_001",
  "analysis_job_id": "analysis_job_001",
  "candidate_ids": ["analysis_candidate_001"]
}
```

---

### 16.3 Checks

```text
Schema Check:
- candidate payload matches expected schema

Source Check:
- source_refs exist
- quote span is valid
- source_refs are in current snapshot

Confidence Check:
- confidence >= threshold

Status Check:
- AI did not claim confirmed/canonical

Contradiction Check:
- candidate does not contradict canonical memory
- candidate does not invalidate existing timeline without review

Entity Resolution Check:
- matched_existing_id is plausible
- new entity is not duplicate

Scope Check:
- project_id matches
- source belongs to project

Risk Check:
- canon-changing candidate requires review
```

---

### 16.4 Thresholds

Recommended default thresholds:

```text
auto_reject_below = 0.45
needs_review_below = 0.75
eligible_for_confirmed_above = 0.85
auto_canonical = never by default
```

MVP policy:

```text
- Below 0.45: rejected
- 0.45 to 0.75: needs_review
- 0.75 to 0.85: candidate
- 0.85+: confirmed if no contradiction and source_refs valid
- canonical: user review only
```

---

### 16.5 Gate Output

```json
{
  "gate_result_id": "analysis_gate_001",
  "gate_type": "analysis_gate",
  "decision": "pass",
  "accepted_candidates": ["analysis_candidate_001"],
  "needs_review_candidates": [],
  "rejected_candidates": [],
  "findings": []
}
```

Possible decisions:

```text
pass
needs_user_review
block
partial
```

---

## 17. Entity Resolution

### 17.1 Purpose

Entity Resolution decides whether extracted objects are new or existing.

Example:

```text
“은빛 눈의 검사”
→ existing char_arin alias
```

---

### 17.2 Resolution Inputs

```json
{
  "candidate_id": "analysis_candidate_001",
  "candidate": {
    "name": "은빛 눈의 검사",
    "entity_type": "character",
    "aliases": [],
    "source_refs": ["src_ch06_s01_020_088"]
  },
  "known_entities_context": [
    {
      "entity_id": "char_arin",
      "name": "아린",
      "aliases": ["은빛 눈의 검사"]
    }
  ]
}
```

---

### 17.3 Resolution Output

```json
{
  "resolution": "match_existing",
  "matched_entity_id": "char_arin",
  "confidence": 0.94,
  "reason": "Alias matches existing character."
}
```

Allowed resolutions:

```text
match_existing
create_new
needs_review
reject
```

---

### 17.4 Resolution Strategy

Use multiple signals:

```text
- exact name match
- alias match
- source proximity
- co-occurring traits
- entity type
- relation context
- prior mentions
- semantic similarity
```

---

### 17.5 Ambiguity Handling

If multiple possible matches:

```text
- mark candidate as needs_review
- do not merge automatically
- create review_request
```

---

## 18. Memory Upsert

### 18.1 Purpose

After candidates pass Analysis Gate and Entity Resolution, memory collections are updated.

---

### 18.2 Upsert Policies

#### New entity

```text
create new document in target collection
status = confirmed or candidate depending on gate
source_refs = candidate.source_refs
version = 1
```

#### Existing entity fact update

```text
append new source_refs
update summary if needed
add observed fact
increment version
create index sync event
```

#### Relation update

```text
if same from/to/relation_type exists:
    update status_label or source_refs
else:
    create relation
```

#### Foreshadowing update

```text
if matched_existing_id exists:
    update status from unresolved → developing if appropriate
    append source_ref
else:
    create new foreshadowing as candidate/confirmed
```

---

### 18.3 Memory Versioning

Every memory document should include:

```json
{
  "version": 4,
  "created_from_analysis_run": "analysis_run_001",
  "updated_from_analysis_run": "analysis_run_012",
  "source_refs": []
}
```

When modified:

```text
- increment version
- preserve prior source_refs
- append new source_refs
- update updated_at
- write system_event
```

---

## 19. Review Request Creation

### 19.1 When to Create Review Request

Create review request when:

```text
- candidate conflicts with canonical memory
- entity resolution is ambiguous
- candidate would change canon
- confidence is moderate
- source evidence is weak
- timeline contradiction exists
- user policy requires review
```

---

### 19.2 ReviewRequest Example

```json
{
  "_id": "review_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "object_type": "analysis_candidate",
  "object_id": "analysis_candidate_001",
  "reason": "새로운 타임라인 사실이 기존 canon과 충돌할 수 있음.",
  "options": ["confirm", "reject", "edit", "defer"],
  "status": "open",
  "created_at": "2026-06-23T00:00:00Z"
}
```

---

### 19.3 Review Result Effects

| Decision | Effect |
|---|---|
| `confirm` | candidate → confirmed |
| `reject` | candidate → rejected |
| `edit` | create edited memory, candidate → superseded or confirmed |
| `defer` | keep needs_review |

---

## 20. Index Sync

### 20.1 Purpose

After MongoDB memory update, derived indices must be synced.

Direction:

```text
MongoDB → ChromaDB
MongoDB → Elasticsearch
```

Never:

```text
ChromaDB → MongoDB
Elasticsearch → MongoDB
```

---

### 20.2 IndexSyncRequest

```json
{
  "sync_request_id": "sync_req_001",
  "project_id": "project_001",
  "event": "analysis_completed",
  "source": {
    "mongo_collection": "foreshadowings",
    "mongo_id": "foreshadow_black_sun_knife",
    "mongo_version": 2
  },
  "targets": ["chroma", "elasticsearch"]
}
```

---

### 20.3 What to Index

#### ChromaDB

Index semantic representations:

```text
- source block text
- scene summary
- character summary
- event summary
- location summary
- foreshadowing summary
- relation summary
- style sample
```

#### Elasticsearch

Index lexical and metadata fields:

```text
- names
- aliases
- titles
- body text
- summaries
- statuses
- chapter_id
- scene_id
- source_refs
- mongo pointer
```

---

### 20.4 Index Metadata Requirements

All index records must include:

```json
{
  "project_id": "project_001",
  "kind": "foreshadowing",
  "mongo_collection": "foreshadowings",
  "mongo_id": "foreshadow_black_sun_knife",
  "mongo_version": 2,
  "source_refs": ["src_ch02_s01_084_112"],
  "status": "unresolved"
}
```

---

## 21. Analysis Trace

### 21.1 Purpose

Every analysis job must be traceable.

---

### 21.2 Trace Items

Trace should capture:

```text
- trigger
- snapshot_id
- task list
- model/provider
- prompt version
- source blocks
- raw output parse status
- schema validation result
- source anchor validation result
- candidate IDs
- gate result
- upserted memory IDs
- review request IDs
- index sync IDs
```

---

### 21.3 Trace Example

```json
{
  "analysis_trace_id": "analysis_trace_001",
  "project_id": "project_001",
  "analysis_job_id": "analysis_job_001",
  "snapshot_id": "snap_draft_003_v12",
  "tasks": [
    {
      "task_type": "entity_extraction",
      "analysis_run_id": "analysis_run_012",
      "raw_output_valid": true,
      "candidate_count": 4,
      "accepted_count": 3,
      "needs_review_count": 1,
      "rejected_count": 0
    }
  ],
  "upserted": [
    {
      "collection": "entities",
      "id": "char_arin"
    }
  ],
  "index_sync_ids": ["sync_001"],
  "created_at": "2026-06-23T00:00:00Z"
}
```

---

## 22. Error Handling

### 22.1 Standard Error

```json
{
  "error": {
    "code": "ANALYSIS_SCHEMA_INVALID",
    "message": "Analysis AI output did not match expected schema.",
    "details": {
      "analysis_task_id": "analysis_task_001",
      "task_type": "entity_extraction"
    },
    "retryable": true
  }
}
```

---

### 22.2 Error Codes

```text
SNAPSHOT_NOT_FOUND
SOURCE_BLOCKS_NOT_FOUND
SOURCE_REF_INVALID
ANALYSIS_MODEL_ERROR
ANALYSIS_OUTPUT_PARSE_FAILED
ANALYSIS_SCHEMA_INVALID
SOURCE_ANCHOR_INVALID
ENTITY_RESOLUTION_AMBIGUOUS
ANALYSIS_GATE_BLOCKED
MEMORY_UPSERT_FAILED
INDEX_SYNC_FAILED
REVIEW_REQUIRED
```

---

### 22.3 Failure Policy

| Failure | Policy |
|---|---|
| snapshot missing | fail job |
| block split failed | fail job |
| LLM call failed | retry task |
| parse failed | repair once, then fail task |
| schema invalid | retry with stricter prompt |
| source_ref invalid | reject candidate |
| entity ambiguous | needs_review |
| memory upsert failed | fail task and preserve candidates |
| index sync failed | memory remains valid, retry sync |

---

## 23. Retry Policy

### 23.1 Retryable Stages

```text
AnalysisModelRunner
RawOutputParser repair
IndexSyncDispatcher
MemoryUpserter if transient DB error
```

---

### 23.2 Non-Retryable Stages

```text
source_ref mismatch caused by hallucinated span
project_id mismatch
canonical contradiction requiring user review
invalid snapshot
```

---

### 23.3 Retry Counts

MVP default:

```text
LLM call: 2 retries
JSON repair: 1 retry
Index sync: 3 retries
Mongo transient error: 2 retries
```

---

## 24. Concurrency and Idempotency

### 24.1 Idempotency Keys

Use idempotency keys for:

```text
draft save analysis job
analysis task
candidate creation
memory upsert
index sync
```

Example:

```text
analysis_job_id + task_type + snapshot_id + block_range_hash
```

---

### 24.2 Duplicate Prevention

```text
- Do not create duplicate candidates for same analysis_result + payload hash.
- Do not create duplicate source_refs for same snapshot/span.
- Do not upsert same relation twice.
- Do not index same mongo_id/version twice unless forced.
```

---

### 24.3 Parallel Task Execution

Safe to run in parallel:

```text
entity_extraction
location_extraction
event_extraction
style_signal_extraction
```

Should run after entity resolution:

```text
relation_extraction
timeline_extraction
character_knowledge_extraction
```

Recommended MVP ordering:

```text
1. scene_split
2. entity_extraction + location_extraction + item/organization extraction
3. entity resolution
4. event_extraction
5. relation_extraction
6. foreshadowing_extraction
7. timeline_extraction
8. character_knowledge_extraction
9. style_signal_extraction
```

---

## 25. Incremental Analysis

### 25.1 MVP Strategy

Analyze full saved draft version or selected scene.

This is simpler and reliable.

---

### 25.2 Advanced Strategy

Use diff between draft versions.

```text
draft_v011
draft_v012
→ changed spans
→ affected blocks
→ affected source_refs
→ affected memory candidates
→ selective reanalysis
```

---

### 25.3 Dependency Invalidation

When a source block changes, dependent memory may need update.

Track dependencies:

```text
source_ref → analysis_candidate
analysis_candidate → memory document
memory document → index records
```

If source_ref is deprecated:

```text
- mark dependent candidate deprecated or needs_review
- update memory source_refs
- re-run analysis if necessary
- sync indices
```

---

## 26. Prompt Design

### 26.1 Prompt Sections

Every task prompt should include:

```text
1. Role
2. Task objective
3. Strict output schema
4. Source anchoring rules
5. Known prior context
6. Text package
7. Extraction rules
8. Confidence rules
9. Examples
```

---

### 26.2 Example Prompt Skeleton

```text
ROLE
You are Analysis AI for a personal writing memory system.

TASK
Extract foreshadowing candidates from the provided scene.

RULES
- Use only the provided text.
- Every candidate must include source_refs.
- Do not invent future payoff.
- If payoff is speculative, mark it as possible_payoff and keep confidence below 0.8.
- Output JSON only.

KNOWN CONTEXT
{prior_context}

TEXT PACKAGE
{text_package}

OUTPUT SCHEMA
{schema}
```

---

## 27. Confidence Guidelines

### 27.1 Confidence Scale

```text
0.95 - 1.00:
Explicitly stated, source_ref exact, no ambiguity.

0.85 - 0.94:
Strongly supported by text, minor interpretation.

0.75 - 0.84:
Likely but not fully explicit.

0.60 - 0.74:
Plausible but interpretive.

0.45 - 0.59:
Weak inference, review required.

below 0.45:
Do not store except as rejected/debug.
```

---

### 27.2 Confidence by Candidate Type

| Candidate Type | Default Required Confidence |
|---|---:|
| character | 0.80 |
| event | 0.80 |
| location | 0.80 |
| relation | 0.85 |
| timeline_fact | 0.88 |
| character_knowledge | 0.88 |
| foreshadowing | 0.75 |
| open_question | 0.70 |
| style_signal | 0.70 |

---

## 28. Risk Classification

### 28.1 Low Risk

```text
style signal
scene mood
minor location feature
non-canon summary
```

### 28.2 Medium Risk

```text
new character fact
new event
new relation
new location feature
```

### 28.3 High Risk

```text
timeline fact
character knowledge
relationship status change
foreshadowing payoff
world rule
```

### 28.4 Critical Risk

```text
canon contradiction
death / resurrection
betrayal reveal
major identity reveal
core worldbuilding rule change
```

High and critical candidates should create review requests unless policy explicitly allows auto-confirm.

---

## 29. Gate to Memory Mapping

### 29.1 Candidate State Transition

```text
AnalysisCandidate(candidate)
    │
    ├── AnalysisGate reject
    │       └── rejected
    │
    ├── AnalysisGate weak / ambiguous
    │       └── needs_review
    │
    ├── AnalysisGate pass
    │       └── confirmed
    │
    └── User review confirm as canon
            └── canonical
```

---

### 29.2 Transition Rules

```text
candidate → confirmed:
- source_refs valid
- confidence high enough
- no canon conflict

candidate → needs_review:
- ambiguous entity
- moderate confidence
- potential canon impact

candidate → rejected:
- invalid source_ref
- hallucinated claim
- duplicate invalid
- contradicts canon with no evidence

confirmed → canonical:
- user review or explicit canon note

confirmed/canonical → deprecated:
- later canon supersedes it
```

---

## 30. Integration With Agentic Search

### 30.1 Analysis Uses Agentic Search

Before extraction, Analysis Pipeline may request context:

```json
{
  "requesting_agent": "analysis_ai",
  "purpose": "analysis_context",
  "query": "known entities and aliases for scene_014",
  "needs": [
    "known_entities",
    "known_locations",
    "open_foreshadowing",
    "recent_relations"
  ]
}
```

---

### 30.2 Analysis Produces Searchable Memory

After confirmed memory is written:

```text
MemoryUpserter
→ IndexSyncDispatcher
→ ChromaDB / Elasticsearch
→ Agentic Search can retrieve it later
```

---

### 30.3 Feedback Loop

```text
Write
→ Save
→ Analyze
→ Store memory
→ Index memory
→ Search memory
→ Write better
```

This is the system's core learning loop.

---

## 31. Integration With Writing Gate

Writing Gate uses analysis-derived memory to validate draft candidates.

Example:

```text
WritingCandidate:
“아린은 레온의 배신을 떠올렸다.”

Writing Gate:
Agentic Search continuity_check
→ timeline_facts
→ character_knowledge
→ finding: POV violation
```

---

## 32. Integration With Review UI

### 32.1 Review UI Lists

UI should show:

```text
- New candidates
- Needs review
- Confirmed memories
- Canon conflicts
- Ambiguous entity matches
- New foreshadowings
- Potential timeline facts
```

---

### 32.2 Review Card Example

```json
{
  "title": "새 타임라인 사실 후보",
  "candidate_text": "아린은 노스워치에 도착했다.",
  "source_quote": "아린은 해가 기울 무렵 노스워치의 성문 앞에 도착했다.",
  "confidence": 0.92,
  "actions": ["confirm", "reject", "edit", "defer"]
}
```

---

## 33. Data Quality Metrics

Track:

```text
analysis_job_success_rate
analysis_task_failure_rate
json_parse_failure_rate
schema_validation_failure_rate
source_ref_failure_rate
candidate_acceptance_rate
candidate_rejection_rate
needs_review_rate
entity_resolution_ambiguity_rate
canon_conflict_rate
index_sync_success_rate
```

---

## 34. MVP Scope

### 34.1 MVP Pipeline

Implement:

```text
Draft Save Trigger
SnapshotBuilder
BlockSplitter
SourceRefGenerator
AnalysisJobFactory
AnalysisTaskPlanner
SnapshotLoader
PriorContextLoader
AnalysisPromptBuilder
AnalysisModelRunner
RawOutputParser
SchemaValidator
SourceAnchorValidator
AnalysisCandidateBuilder
AnalysisGate
EntityResolver
MemoryUpserter
IndexSyncDispatcher
```

---

### 34.2 MVP Task Order

```text
1. scene_split
2. entity_extraction
3. location_extraction
4. event_extraction
5. foreshadowing_extraction
6. relation_extraction
7. timeline_extraction
8. character_knowledge_extraction
```

---

### 34.3 MVP Candidate Types

```text
character
event
location
foreshadowing
relation
timeline_fact
character_knowledge
```

---

### 34.4 MVP Auto-Confirm Policy

Recommended:

```text
- Auto-confirm low/medium risk candidates above 0.85 if source_refs valid.
- Never auto-canonical.
- High risk candidates go to needs_review.
- Critical risk candidates always go to needs_review.
```

---

## 35. Advanced Roadmap

### 35.1 Diff-Based Reanalysis

Analyze only changed spans between versions.

---

### 35.2 Memory Dependency Graph

Track dependencies:

```text
source_ref
→ analysis_candidate
→ memory document
→ index record
→ context_package
```

---

### 35.3 Multi-Agent Analysis

Separate agents:

```text
Character Analyst
Timeline Analyst
Foreshadowing Analyst
Continuity Analyst
Style Analyst
```

Each outputs candidates to the same pipeline.

---

### 35.4 Human-in-the-Loop Canon Editor

User can:

```text
- approve candidate
- reject candidate
- edit candidate
- merge entities
- split entities
- deprecate memory
- pin canon
```

---

### 35.5 Continuous Memory Maintenance

Periodic jobs:

```text
- stale candidate cleanup
- duplicate entity detection
- unresolved foreshadowing summary
- timeline consistency scan
- index freshness check
```

---

## 36. Pseudocode

### 36.1 Main Pipeline

```python
def run_analysis_pipeline(job_id: str) -> None:
    job = analysis_jobs.get(job_id)

    snapshot = snapshot_loader.load(job.snapshot_id)

    tasks = task_planner.plan(job, snapshot)

    for task in tasks:
        try:
            text_package = snapshot_loader.load_task_text(task)

            prior_context = prior_context_loader.load(
                task=task,
                purpose="analysis_context",
            )

            prompt = prompt_builder.build(
                task=task,
                text_package=text_package,
                prior_context=prior_context,
            )

            run = model_runner.run(prompt)

            raw_result = output_parser.parse_or_repair(run.output)

            schema_result = schema_validator.validate(
                task_type=task.task_type,
                raw_result=raw_result,
            )

            if not schema_result.valid:
                mark_task_failed(task, "ANALYSIS_SCHEMA_INVALID")
                continue

            anchor_result = source_anchor_validator.validate(
                raw_result=raw_result,
                snapshot=snapshot,
            )

            candidates = candidate_builder.build(
                task=task,
                raw_result=raw_result,
                schema_result=schema_result,
                anchor_result=anchor_result,
            )

            gate_result = analysis_gate.evaluate(candidates)

            resolution_result = entity_resolver.resolve(candidates)

            upserted = memory_upserter.apply(
                candidates=candidates,
                gate_result=gate_result,
                resolution_result=resolution_result,
            )

            review_request_builder.create_if_needed(
                candidates=candidates,
                gate_result=gate_result,
                resolution_result=resolution_result,
            )

            index_sync_dispatcher.dispatch(upserted)

            mark_task_completed(task)

        except RetryableError as e:
            retry_task(task, e)

        except Exception as e:
            mark_task_failed(task, e)

    finalize_job(job)
```

---

### 36.2 Candidate Upsert

```python
def apply_candidates(candidates, gate_result, resolution_result):
    upserted = []

    for candidate in candidates:
        decision = gate_result.decision_for(candidate.id)

        if decision == "rejected":
            update_candidate_status(candidate.id, "rejected")
            continue

        if decision == "needs_review":
            update_candidate_status(candidate.id, "needs_review")
            continue

        if decision == "confirmed":
            resolved_target = resolution_result.target_for(candidate.id)

            doc = upsert_memory(
                target_collection=candidate.target_collection,
                target_id=resolved_target.id,
                payload=candidate.payload,
                source_refs=candidate.source_refs,
            )

            update_candidate_status(candidate.id, "confirmed")
            upserted.append(doc)

    return upserted
```

---

## 37. Final Summary

Analysis Pipeline is the system's memory compiler.

It turns saved writing into structured, searchable, gate-validated memory.

The invariant is:

```text
No extracted memory becomes trusted without source_ref.
No AI output becomes canon by itself.
No index is updated before MongoDB memory exists.
No future writing context is built from unverified analysis.
```

The full loop is:

```text
Write
→ Save
→ Snapshot
→ Analyze
→ Candidate
→ Gate
→ Confirm
→ MongoDB Memory
→ Index
→ Agentic Search
→ Better Writing
```

In short:

```text
Writing AI creates text.
Analysis AI compiles text into memory.
Agentic Search retrieves memory.
Gate protects truth.
MongoDB owns the record.
```
