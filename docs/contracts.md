# contracts.md

# Personal Writing AI System Contracts

Version: `0.1.0-draft`  
Status: `ideation / architecture draft`  
Primary SOT: `MongoDB`  
Vector Cache: `ChromaDB`  
Lexical Search Index: `Elasticsearch`  
LLM Provider: `Gemma / llama.cpp compatible provider`  
Core Principle: `AI outputs are candidates until gated`

---

## 0. Purpose

This document defines the contracts between the major components of the Personal Writing AI System.

The system combines:

- Writing AI
- Analysis AI
- Agentic Search
- MongoDB Source of Truth
- ChromaDB semantic vector cache
- Elasticsearch lexical and metadata index
- Gate / Verification layer
- Editor and Chat interface

The contracts in this document are intended to prevent responsibility leakage between components.

In particular:

```text
Writing AI does not own memory.
Analysis AI does not define canon by itself.
ChromaDB and Elasticsearch are not sources of truth.
MongoDB is the source of truth.
Agentic Search is the only component that assembles retrieval context for AI agents.
Gate components decide whether candidates can pass.
```

---

## 1. Global Contract Principles

### 1.1 MongoDB Is the Source of Truth

MongoDB stores all canonical and derived project data.

MongoDB stores:

- Projects
- Writing briefs
- Drafts
- Draft versions
- Source snapshots
- Source blocks
- Source refs
- Entities
- Events
- Locations
- Organizations
- Items
- Concepts
- Foreshadowings
- Open questions
- Relations
- Timeline facts
- Character knowledge
- Style profiles
- Voice samples
- Analysis runs
- Analysis candidates
- Gate results
- Search traces
- Index sync logs
- Context packages

ChromaDB and Elasticsearch must never be treated as final truth.

Any data retrieved from ChromaDB or Elasticsearch must be reloaded from MongoDB before it is supplied to a writing or analysis agent as grounded context.

---

### 1.2 ChromaDB Is a Semantic Cache

ChromaDB stores semantic representations for retrieval.

ChromaDB may store:

- Embedded text chunks
- Scene summaries
- Character summaries
- Event summaries
- Location summaries
- Foreshadowing summaries
- Relation summaries
- Voice samples
- Project memories

ChromaDB records must include a MongoDB pointer.

ChromaDB records must not be used as canonical data.

Minimum ChromaDB metadata:

```json
{
  "project_id": "project_001",
  "kind": "character | event | location | source_block | foreshadowing | relation | voice | memory",
  "mongo_collection": "entities",
  "mongo_id": "char_arin",
  "mongo_version": 4,
  "source_refs": ["src_ch01_s02_020_090"],
  "status": "confirmed"
}
```

---

### 1.3 Elasticsearch Is a Lexical and Metadata Index

Elasticsearch supports:

- Exact name search
- Alias search
- Dialogue search
- Keyword search
- BM25 ranking
- Korean lexical search
- Status filters
- Project filters
- Chapter and scene filters
- Entity type filters
- Canon status filters

Elasticsearch documents must include MongoDB pointers.

Elasticsearch records must not be used as canonical data.

Minimum Elasticsearch document metadata:

```json
{
  "project_id": "project_001",
  "kind": "foreshadowing",
  "mongo_collection": "foreshadowings",
  "mongo_id": "foreshadow_black_sun_knife",
  "mongo_version": 2,
  "status": "unresolved",
  "source_refs": ["src_ch02_s01_084_112"]
}
```

---

### 1.4 All AI Outputs Are Candidates

No AI component directly creates final truth.

Writing AI outputs are `draft_candidate`.

Analysis AI outputs are `analysis_candidate`.

Agentic Search outputs are `context_candidate`.

Gate components evaluate candidates.

Candidate states:

```text
candidate
confirmed
canonical
needs_review
rejected
deprecated
```

State definitions:

| State | Meaning |
|---|---|
| `candidate` | AI-generated or derived result, not yet fully trusted |
| `confirmed` | Passed validation against source refs and project constraints |
| `canonical` | Accepted as project-level truth, usually by user review or strict rule |
| `needs_review` | Requires user or stronger verifier decision |
| `rejected` | Invalid or incorrect candidate |
| `deprecated` | Previously valid but superseded by later canon |

---

### 1.5 Every Grounded Fact Needs a Pointer

Any factual or narrative-memory item supplied to AI must be traceable.

Minimum pointer structure:

```json
{
  "mongo_collection": "source_blocks",
  "mongo_id": "block_ch06_s01_p003",
  "source_ref": "src_ch06_s01_240_306",
  "snapshot_id": "snap_draft_003_v12",
  "project_id": "project_001"
}
```

For structured memory:

```json
{
  "mongo_collection": "entities",
  "mongo_id": "char_arin",
  "source_refs": ["src_ch01_s02_020_090"],
  "project_id": "project_001"
}
```

---

## 2. Shared Types

### 2.1 Pointer

```json
{
  "project_id": "project_001",
  "mongo_collection": "entities",
  "mongo_id": "char_arin",
  "mongo_version": 4,
  "source_refs": ["src_ch01_s02_020_090"]
}
```

Required fields:

| Field | Required | Description |
|---|---:|---|
| `project_id` | yes | Project boundary |
| `mongo_collection` | yes | MongoDB collection name |
| `mongo_id` | yes | MongoDB document ID |
| `mongo_version` | recommended | Version for stale index detection |
| `source_refs` | recommended | Source span evidence |

---

### 2.2 SourceRef

```json
{
  "source_ref_id": "src_ch06_s01_240_306",
  "project_id": "project_001",
  "snapshot_id": "snap_draft_003_v12",
  "block_id": "block_ch06_s01_p003",
  "start_offset": 240,
  "end_offset": 306,
  "quote": "낡은 단검 손잡이에는 검은 태양 문양이 희미하게 떠올라 있었다.",
  "hash": "sha256:..."
}
```

Contract rules:

- A `source_ref_id` must point to one exact span.
- The quote must match the source span.
- The hash must be used to detect stale or mutated source text.
- Source refs must not be fabricated by LLMs.
- Source refs are generated by the storage/snapshot layer.

---

### 2.3 ContextItem

```json
{
  "context_item_id": "ctx_item_001",
  "kind": "character",
  "status": "confirmed",
  "trust_level": "high",
  "payload": {},
  "pointers": [
    {
      "project_id": "project_001",
      "mongo_collection": "entities",
      "mongo_id": "char_arin",
      "mongo_version": 4,
      "source_refs": ["src_ch01_s02_020_090"]
    }
  ],
  "usage_hint": "Use as character state constraint."
}
```

Allowed `kind` values:

```text
source_block
scene_summary
character
event
location
organization
item
concept
foreshadowing
open_question
relation
timeline_fact
character_knowledge
voice_sample
style_rule
user_preference
```

---

### 2.4 GateDecision

```json
{
  "decision": "pass",
  "severity": "none",
  "findings": []
}
```

Allowed decisions:

```text
pass
revise
retrieve_more
needs_user_review
block
```

Meaning:

| Decision | Meaning |
|---|---|
| `pass` | Candidate can be used or shown |
| `revise` | Candidate should be revised before use |
| `retrieve_more` | Context is insufficient; Agentic Search should run again |
| `needs_user_review` | Ambiguous or high-impact result requires user decision |
| `block` | Candidate must not be used |

---

## 3. Writing AI Contract

### 3.1 Responsibility

Writing AI generates text candidates.

It may perform:

- Drafting
- Outlining
- Continuing
- Rewriting
- Expanding
- Compressing
- Style adaptation
- Critique
- Scene proposal
- Dialogue improvement

It must not perform:

- Direct MongoDB access
- Direct ChromaDB access
- Direct Elasticsearch access
- Canon creation
- Source ref generation
- Memory mutation
- Index mutation
- User preference mutation
- Final gate approval

---

### 3.2 Input: WritingRequest

```json
{
  "request_id": "write_req_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "task_type": "continue_scene",
  "instruction": "아린이 노스워치에 도착하는 장면을 이어서 써줘.",
  "draft_pointer": {
    "draft_id": "draft_003",
    "version": 12,
    "snapshot_id": "snap_draft_003_v12",
    "selection": {
      "start": 1200,
      "end": 1800
    }
  },
  "writing_brief_id": "brief_001",
  "context_policy": {
    "use_agentic_search": true,
    "include_voice": true,
    "include_timeline": true,
    "include_foreshadowing": true,
    "include_recent_scenes": true,
    "include_character_knowledge": true
  },
  "generation_options": {
    "language": "ko",
    "length": "1200-1800자",
    "output_mode": "draft_patch",
    "tone": ["차분함", "불길함"],
    "temperature": 0.7
  }
}
```

Required fields:

```text
request_id
project_id
user_id
task_type
instruction
writing_brief_id
```

---

### 3.3 Input: WritingContextPackage

Writing AI receives context only through a context package.

```json
{
  "context_package_id": "ctx_001",
  "project_id": "project_001",
  "request_id": "write_req_001",
  "purpose": "continue_scene",
  "macro_context": {
    "current_scene_summary": "...",
    "project_summary": "...",
    "relevant_characters": [],
    "relevant_locations": [],
    "recent_events": [],
    "open_foreshadowings": [],
    "voice_profile": {},
    "style_rules": []
  },
  "micro_evidence": [
    {
      "source_ref": "src_ch02_s01_084_112",
      "quote": "낡은 단검 손잡이에는 검은 태양 문양이 새겨져 있었다.",
      "supports": "foreshadow_black_sun_knife",
      "pointers": []
    }
  ],
  "constraints": [
    {
      "type": "pov",
      "text": "아린은 현재 시점에서 레온의 배신을 모른다.",
      "pointers": []
    }
  ],
  "do_not_use": [
    {
      "reason": "future_knowledge",
      "text": "레온의 배신 사실을 아린의 내면이나 대사에 직접 넣지 말 것."
    }
  ],
  "trace": {
    "search_plan_id": "search_plan_001",
    "search_trace_id": "search_trace_001"
  }
}
```

---

### 3.4 Output: WritingCandidate

```json
{
  "candidate_id": "draft_candidate_001",
  "request_id": "write_req_001",
  "project_id": "project_001",
  "output_type": "draft_patch",
  "text": "...",
  "used_context_package_id": "ctx_001",
  "self_reported_constraints": [
    "아린은 레온의 배신을 모르는 상태로 작성함",
    "단검 떡밥은 암시만 하고 회수하지 않음"
  ],
  "candidate_claims": [
    {
      "claim_id": "claim_001",
      "claim_text": "아린은 노스워치에 도착했다.",
      "claim_type": "narrative_event",
      "requires_gate_check": true
    }
  ],
  "status": "candidate"
}
```

---

### 3.5 Writing AI System Prompt Contract

```text
너는 개인 글쓰기 시스템의 Writing AI이다.

너의 역할:
- 사용자의 요청과 WritingBrief를 바탕으로 글쓰기 후보를 생성한다.
- 제공된 WritingContextPackage 안의 정보만 근거로 사용한다.
- 현재 프로젝트의 문체, 세계관, 타임라인, 인물 지식 상태를 따른다.

절대 하지 말 것:
- MongoDB, ChromaDB, Elasticsearch에 직접 접근하지 않는다.
- source_ref를 새로 만들거나 꾸며내지 않는다.
- candidate 정보를 canonical truth처럼 단정하지 않는다.
- do_not_use 항목을 직접 서술하지 않는다.
- 현재 시점의 인물이 알 수 없는 사실을 대사나 내면에 넣지 않는다.
- 사용자가 요청하지 않은 떡밥 회수나 설정 변경을 하지 않는다.

출력:
- 최종 글이 아니라 draft_candidate를 출력한다.
- 필요한 경우 자신이 지킨 제약과 잠재 claim을 함께 보고한다.
```

---

## 4. Analysis AI Contract

### 4.1 Responsibility

Analysis AI converts saved writing into structured memory candidates.

It may extract:

- Characters
- Events
- Locations
- Organizations
- Items
- Concepts
- Foreshadowings
- Open questions
- Relations
- Timeline facts
- Character knowledge
- Style signals

It must not:

- Directly mutate canon
- Directly update ChromaDB
- Directly update Elasticsearch
- Invent source refs
- Treat weak inference as fact
- Confirm its own output as canonical

---

### 4.2 Input: AnalysisJob

```json
{
  "analysis_job_id": "analysis_job_001",
  "project_id": "project_001",
  "snapshot_id": "snap_draft_003_v12",
  "trigger": "draft_saved",
  "tasks": [
    "scene_split",
    "entity_extraction",
    "event_extraction",
    "location_extraction",
    "foreshadowing_extraction",
    "relationship_extraction",
    "timeline_extraction",
    "character_knowledge_extraction",
    "style_signal_extraction"
  ],
  "status": "queued"
}
```

---

### 4.3 Input: AnalysisTaskPayload

```json
{
  "analysis_task_id": "analysis_task_001",
  "analysis_job_id": "analysis_job_001",
  "task_type": "entity_extraction",
  "project_id": "project_001",
  "snapshot_pointer": {
    "snapshot_id": "snap_draft_003_v12",
    "scene_id": "scene_014"
  },
  "text_package": {
    "text": "...",
    "span_map": [
      {
        "span_id": "span_001",
        "start": 0,
        "end": 120,
        "source_ref": "src_ch06_s01_000_120"
      }
    ]
  },
  "known_entities_context": [
    {
      "entity_id": "char_arin",
      "name": "아린",
      "aliases": ["은빛 눈의 검사"]
    }
  ],
  "output_schema": "AnalysisCandidate[]"
}
```

---

### 4.4 Output: AnalysisResult

```json
{
  "analysis_result_id": "analysis_result_001",
  "analysis_task_id": "analysis_task_001",
  "project_id": "project_001",
  "snapshot_id": "snap_draft_003_v12",
  "task_type": "entity_extraction",
  "candidates": [
    {
      "candidate_id": "analysis_candidate_001",
      "candidate_type": "character_fact",
      "matched_existing_entity_id": "char_arin",
      "payload": {
        "fact": "아린은 노스워치에 도착했다.",
        "fact_type": "location_arrival",
        "character_id": "char_arin",
        "location_id": "loc_northwatch"
      },
      "source_refs": ["src_ch06_s01_020_088"],
      "confidence": 0.92,
      "status": "candidate"
    }
  ]
}
```

---

### 4.5 Analysis AI System Prompt Contract

```text
너는 개인 글쓰기 시스템의 Analysis AI이다.

너의 역할:
- 저장된 글을 읽고 구조화된 기억 후보를 추출한다.
- 원문에서 명시되거나 강하게 지지되는 정보만 추출한다.
- 모든 추출 결과는 source_ref 또는 span 근거를 가져야 한다.
- 기존 entity와 같은 대상일 가능성이 있으면 matched_existing_entity_id를 제안한다.

절대 하지 말 것:
- source_ref를 꾸며내지 않는다.
- 원문에 없는 설정을 fact로 저장하지 않는다.
- 약한 추측을 confirmed나 canonical로 표시하지 않는다.
- canon을 직접 변경하지 않는다.
- ChromaDB나 Elasticsearch를 직접 업데이트하지 않는다.

출력:
- analysis_candidate 배열을 출력한다.
- 각 candidate에는 confidence, source_refs, status를 포함한다.
```

---

## 5. Agentic Search Contract

### 5.1 Responsibility

Agentic Search is the retrieval brain of the system.

It performs:

- Search intent classification
- Query planning
- Search tool routing
- Elasticsearch retrieval
- ChromaDB retrieval
- MongoDB SOT reload
- Stale index detection
- Context ranking
- Context compression
- Context package creation
- Search trace logging

It must not:

- Generate final prose
- Mutate canon
- Treat vector records as truth
- Treat Elasticsearch records as truth
- Provide unverified context to Writing AI
- Cross project boundaries

---

### 5.2 Input: ContextSearchRequest

```json
{
  "search_request_id": "search_req_001",
  "project_id": "project_001",
  "requesting_agent": "writing_ai",
  "purpose": "writing_context",
  "query": "아린이 노스워치에 도착하는 장면",
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
    "version": 12,
    "scene_id": "scene_014"
  },
  "context_budget": {
    "max_tokens": 6000,
    "macro_context_tokens": 2500,
    "micro_evidence_tokens": 2500,
    "reserve_tokens": 1000
  }
}
```

---

### 5.3 Output: SearchPlan

```json
{
  "search_plan_id": "search_plan_001",
  "project_id": "project_001",
  "steps": [
    {
      "step_id": "step_001",
      "target": "character_state",
      "query": "아린",
      "tools": ["elasticsearch", "mongo"],
      "filters": {
        "entity_type": "character",
        "status": ["confirmed", "canonical"]
      }
    },
    {
      "step_id": "step_002",
      "target": "location_context",
      "query": "노스워치",
      "tools": ["elasticsearch", "chroma", "mongo"],
      "filters": {
        "entity_type": "location"
      }
    },
    {
      "step_id": "step_003",
      "target": "open_foreshadowing",
      "query": "단검 검은 태양 문양",
      "tools": ["elasticsearch", "chroma", "mongo"],
      "filters": {
        "status": ["unresolved", "active"]
      }
    }
  ]
}
```

---

### 5.4 Output: ContextPackage

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
    "voice_profile": {}
  },
  "micro_evidence": [
    {
      "source_ref": "src_ch02_s01_084_112",
      "quote": "낡은 단검 손잡이에 검은 태양 문양이 새겨져 있었다.",
      "supports": "foreshadow_black_sun_knife",
      "pointers": []
    }
  ],
  "constraints": [
    {
      "type": "pov",
      "text": "아린은 현재 시점에서 레온의 배신을 모른다.",
      "pointers": []
    }
  ],
  "do_not_use": [
    {
      "reason": "future_knowledge",
      "text": "레온의 배신 사실을 직접 서술하지 말 것."
    }
  ],
  "trace": {
    "search_plan_id": "search_plan_001",
    "retrieval_ids": [],
    "resolved_mongo_ids": []
  },
  "status": "candidate"
}
```

---

### 5.5 Agentic Search System Prompt Contract

```text
너는 개인 글쓰기 시스템의 Agentic Search이다.

너의 역할:
- 요청을 검색 가능한 하위 문제로 분해한다.
- Elasticsearch, ChromaDB, MongoDB를 적절히 조합한다.
- ChromaDB와 Elasticsearch 결과는 후보로만 취급한다.
- 최종 컨텍스트는 반드시 MongoDB SOT에서 재로드한 데이터를 기반으로 만든다.
- ContextPackage에는 AI가 사용해야 할 정보와 사용하면 안 되는 정보를 분리해 담는다.
- 모든 항목에는 trace 가능한 pointer를 포함한다.

절대 하지 말 것:
- vector record 자체를 정본처럼 사용하지 않는다.
- Elasticsearch document 자체를 정본처럼 사용하지 않는다.
- project_id가 다른 데이터를 섞지 않는다.
- Writing AI 대신 글을 작성하지 않는다.
- Analysis AI 대신 구조화 기억을 확정하지 않는다.
```

---

## 6. Gate Contracts

### 6.1 Context Gate

Context Gate validates ContextPackage before it reaches Writing AI or Analysis AI.

Input:

```json
{
  "gate_request_id": "ctx_gate_req_001",
  "gate_type": "context_gate",
  "context_package_id": "ctx_001",
  "project_id": "project_001"
}
```

Output:

```json
{
  "gate_result_id": "ctx_gate_001",
  "decision": "pass",
  "findings": []
}
```

Checks:

```text
- All items have matching project_id.
- All index results were reloaded from MongoDB SOT.
- No stale index result remains.
- Candidate information is clearly labeled.
- Canonical information is not mixed with weak inference.
- Context budget is respected.
- Required source_refs are present.
- Sensitive or cross-project data is absent.
```

---

### 6.2 Writing Gate

Writing Gate validates draft candidates.

Input:

```json
{
  "gate_request_id": "writing_gate_req_001",
  "gate_type": "writing_gate",
  "candidate_id": "draft_candidate_001",
  "project_id": "project_001",
  "context_package_id": "ctx_001"
}
```

Output:

```json
{
  "gate_result_id": "writing_gate_001",
  "decision": "block",
  "findings": [
    {
      "type": "pov",
      "severity": "error",
      "message": "아린은 현재 scene_014 시점에서 레온의 배신을 알 수 없음.",
      "evidence": "아린은 레온의 배신을 떠올렸다.",
      "recommended_decision": "block"
    }
  ]
}
```

Finding shape는 SoT v1.6.69의 exact API 계약이다. Gate result persistence와
canonical pointer 추가는 별도 후속이며 현재 응답 finding에 임의 필드를 더하지 않는다.

Checks:

```text
- Intent match
- Length and format match
- Canon consistency
- Timeline consistency
- POV consistency
- Foreshadowing control
- Voice and style match
- Forbidden pattern detection
- Cross-project memory contamination
```

---

### 6.3 Analysis Gate

Analysis Gate validates analysis candidates.

Input:

```json
{
  "gate_request_id": "analysis_gate_req_001",
  "gate_type": "analysis_gate",
  "analysis_result_id": "analysis_result_001",
  "project_id": "project_001"
}
```

Output:

```json
{
  "gate_result_id": "analysis_gate_001",
  "decision": "needs_user_review",
  "accepted_candidates": [],
  "needs_review_candidates": [
    "analysis_candidate_001"
  ],
  "rejected_candidates": [],
  "findings": [
    {
      "type": "weak_inference",
      "severity": "medium",
      "message": "원문 근거가 약해 confirmed로 승격할 수 없음."
    }
  ]
}
```

Checks:

```text
- JSON schema validity
- source_ref existence
- source_ref belongs to snapshot
- quote matches source span
- confidence threshold
- entity resolution quality
- contradiction with confirmed memory
- contradiction with canonical memory
```

---

### 6.4 Index Gate

Index Gate validates index writes.

Checks:

```text
- MongoDB source exists.
- MongoDB version is current.
- Required pointer metadata exists.
- ChromaDB vector metadata includes mongo pointer.
- Elasticsearch document includes mongo pointer.
- Project boundary is preserved.
```

---

## 7. Indexing Contract

### 7.1 Index Direction

Indexing is one-way.

```text
MongoDB → ChromaDB
MongoDB → Elasticsearch
```

Never:

```text
ChromaDB → MongoDB
Elasticsearch → MongoDB
```

Exception:

Search and index health findings may be written to MongoDB logs.

---

### 7.2 IndexSyncRequest

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

### 7.3 IndexSyncResult

```json
{
  "sync_result_id": "sync_001",
  "sync_request_id": "sync_req_001",
  "project_id": "project_001",
  "targets": {
    "chroma": {
      "status": "success",
      "vector_ids": ["vec_foreshadow_black_sun_knife_v2"]
    },
    "elasticsearch": {
      "status": "success",
      "document_ids": ["es_foreshadow_black_sun_knife_v2"]
    }
  },
  "started_at": "2026-06-23T00:00:00Z",
  "finished_at": "2026-06-23T00:00:02Z"
}
```

---

## 8. Storage Contract

### 8.1 Draft Save Contract

Saving a draft must create:

```text
- draft_version
- source_snapshot
- source_blocks
- source_refs
- analysis_job, if trigger_analysis is true
```

Input:

```json
{
  "project_id": "project_001",
  "draft_id": "draft_003",
  "content": "...",
  "message": "노스워치 도착 장면 추가",
  "trigger_analysis": true
}
```

Output:

```json
{
  "draft_version_id": "draft_v012",
  "snapshot_id": "snap_draft_003_v12",
  "analysis_job_id": "analysis_job_001"
}
```

---

### 8.2 Snapshot Contract

Snapshot must be immutable.

A snapshot may be deprecated, but not mutated.

```json
{
  "snapshot_id": "snap_draft_003_v12",
  "project_id": "project_001",
  "source_type": "draft_version",
  "source_id": "draft_v012",
  "content_hash": "sha256:...",
  "normalized_text_hash": "sha256:...",
  "version": 12,
  "status": "active"
}
```

---

### 8.3 SourceBlock Contract

Source blocks are derived from snapshots.

```json
{
  "block_id": "block_ch06_s01_p003",
  "project_id": "project_001",
  "snapshot_id": "snap_draft_003_v12",
  "block_type": "paragraph",
  "chapter_id": "chapter_06",
  "scene_id": "scene_014",
  "order": 3,
  "text": "...",
  "start_offset": 240,
  "end_offset": 306,
  "hash": "sha256:..."
}
```

---

## 9. Entity Resolution Contract

Entity Resolver decides whether an extracted candidate maps to an existing entity.

Input:

```json
{
  "project_id": "project_001",
  "candidate": {
    "name": "은빛 눈의 검사",
    "entity_type": "character",
    "source_refs": ["src_ch06_s01_020_088"]
  },
  "known_candidates": [
    {
      "entity_id": "char_arin",
      "name": "아린",
      "aliases": ["은빛 눈의 검사"]
    }
  ]
}
```

Output:

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

## 10. Review Contract

Some candidates require user review.

Reviewable objects:

```text
analysis_candidate
writing_candidate
canon_change
entity_merge
foreshadowing_resolution
timeline_conflict
style_rule_change
```

Review request:

```json
{
  "review_request_id": "review_001",
  "project_id": "project_001",
  "object_type": "analysis_candidate",
  "object_id": "analysis_candidate_001",
  "reason": "Possible new canon conflicts with existing timeline.",
  "options": [
    "confirm",
    "reject",
    "edit",
    "defer"
  ]
}
```

Review result:

```json
{
  "review_result_id": "review_result_001",
  "review_request_id": "review_001",
  "decision": "confirm",
  "user_edit": null,
  "created_at": "2026-06-23T00:00:00Z"
}
```

---

## 11. API Boundary Contracts

### 11.1 Write API

```http
POST /api/projects/{project_id}/write
```

Must:

- Create `WritingRequest`
- Call Agentic Search if context is required
- Call Writing AI
- Call Writing Gate
- Return candidate and gate result

Must not:

- Directly save candidate as canonical draft without user acceptance
- Bypass Context Gate

---

### 11.2 Save API

```http
POST /api/projects/{project_id}/drafts/{draft_id}/save
```

Must:

- Save draft version
- Create immutable snapshot
- Create source blocks
- Trigger analysis job if requested

---

### 11.3 Context Search API

```http
POST /api/projects/{project_id}/search/context
```

Must:

- Create search request
- Build search plan
- Execute hybrid retrieval
- Reload MongoDB SOT
- Build context package
- Run Context Gate
- Return context package

---

### 11.4 Analysis API

```http
POST /api/projects/{project_id}/analysis/jobs
```

Must:

- Create analysis job
- Load snapshot from MongoDB
- Run Analysis AI
- Run Analysis Gate
- Store candidates
- Trigger index sync for accepted changes

---

## 12. Error Contract

Standard error:

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

Common error codes:

```text
PROJECT_SCOPE_VIOLATION
SOT_RELOAD_FAILED
STALE_INDEX_RESULT
SOURCE_REF_MISMATCH
CONTEXT_GATE_FAILED
WRITING_GATE_FAILED
ANALYSIS_GATE_FAILED
INVALID_ANALYSIS_SCHEMA
ENTITY_RESOLUTION_AMBIGUOUS
INDEX_SYNC_FAILED
LLM_PROVIDER_ERROR
```

---

## 13. Trace Contract

Every major operation must produce traceable logs.

Traceable operations:

```text
write_request
context_search
search_plan
retrieval_result
sot_reload
context_package
writing_candidate
analysis_job
analysis_candidate
gate_result
index_sync
review_action
```

Search trace example:

```json
{
  "search_trace_id": "search_trace_001",
  "project_id": "project_001",
  "request_id": "write_req_001",
  "query": "아린이 노스워치에 도착하는 장면",
  "steps": [
    {
      "tool": "elasticsearch",
      "query": "아린",
      "result_count": 3
    },
    {
      "tool": "chroma",
      "query": "노스워치 불길한 분위기",
      "result_count": 8
    },
    {
      "tool": "mongo",
      "action": "sot_reload",
      "result_count": 6
    }
  ],
  "context_package_id": "ctx_001"
}
```

---

## 14. Security and Scope Contract

Rules:

```text
- Every query must include project_id.
- Every retrieved item must match project_id.
- Cross-project search is disabled by default.
- User-specific data must not be included unless explicitly scoped.
- Candidate memory must not leak into unrelated projects.
- Private notes and draft content are never sent to external providers unless configured.
```

---

## 15. Minimal MVP Contract Set

For MVP, implement these contracts first:

```text
1. Pointer
2. SourceRef
3. DraftSave
4. SourceSnapshot
5. SourceBlock
6. AnalysisJob
7. AnalysisCandidate
8. AnalysisGate
9. IndexSync
10. ContextSearchRequest
11. SearchPlan
12. ContextPackage
13. ContextGate
14. WritingRequest
15. WritingCandidate
16. WritingGate
```

MVP extraction types:

```text
Character
Event
Location
Foreshadowing
Relation
```

MVP Gates:

```text
ContextGate
AnalysisGate
WritingGate
```

MVP indices:

```text
ChromaDB: project_memory_vectors
Elasticsearch: writing_memory_search
MongoDB: full SOT collections
```

---

## 16. Final Contract Summary

The system contract can be summarized as follows:

```text
MongoDB owns truth.
ChromaDB owns semantic search hints.
Elasticsearch owns lexical search hints.
Agentic Search owns context assembly.
Writing AI owns draft candidate generation.
Analysis AI owns structured memory candidate extraction.
Gate owns pass/revise/retrieve_more/review/block decisions.
User owns final acceptance and canon approval.
```

No component should violate these boundaries.
