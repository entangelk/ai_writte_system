# mongo_collections.md

# Personal Writing AI System — MongoDB Collections Design

Version: `0.1.0-draft`  
Status: `ideation / architecture draft`  
Depends on: `contracts.md`  
Primary SOT: `MongoDB`  
Vector Cache: `ChromaDB`  
Lexical Index: `Elasticsearch`

---

## 0. Purpose

This document defines the MongoDB collection design for the Personal Writing AI System.

MongoDB is the Source of Truth for:

- User projects
- Writing briefs
- Drafts and versions
- Immutable source snapshots
- Source blocks and source refs
- Structured narrative memory
- Analysis candidates
- Canonical project state
- Gate results
- Search traces
- Index synchronization logs
- Review decisions

ChromaDB and Elasticsearch are derived indices.  
They must be rebuildable from MongoDB.

```text
MongoDB = Source of Truth
ChromaDB = semantic vector cache
Elasticsearch = lexical / metadata search index
```

---

## 1. Design Principles

### 1.1 MongoDB Owns Truth

Every meaningful object must exist in MongoDB before it is indexed elsewhere.

The following must never exist only in ChromaDB or Elasticsearch:

```text
draft text
source snapshot
source block
source ref
character
event
location
foreshadowing
relation
timeline fact
character knowledge
canon status
analysis candidate
gate result
```

---

### 1.2 Snapshots Are Immutable

Draft content may evolve, but source snapshots must be immutable.

Rules:

```text
- A draft_version creates one source_snapshot.
- A source_snapshot is never mutated.
- A source_snapshot may be deprecated.
- New content creates a new draft_version and a new source_snapshot.
```

---

### 1.3 Structured Memory Is Derived but Stored

Analysis AI extracts structured memory from source snapshots.

These extracted memories are stored in MongoDB as derived SOT.

However, they must preserve their status:

```text
candidate
confirmed
canonical
needs_review
rejected
deprecated
```

---

### 1.4 All Structured Memory Requires Evidence

Any structured memory item should have at least one `source_ref`.

Exceptions may exist for user-authored canon notes, but these should use:

```json
{
  "source_type": "user_canon_note",
  "created_by": "user"
}
```

---

### 1.5 Every Collection Is Project-Scoped

Almost every collection must include:

```json
{
  "project_id": "project_001",
  "user_id": "user_001"
}
```

`project_id` is required for all project data.

Account/session data and administrator audit tombstones are explicit exceptions:
they describe a user or an administrative action rather than living inside a
project graph. In particular, `admin_audit_events.target_project_id` identifies
the graph that was purged but is deliberately **not** named `project_id`; D8-6
keeps that minimal tombstone after the graph no longer exists.

`user_id` is required where authorization or ownership checks are needed.

No search, write, analysis, or gate operation may cross project boundaries unless explicitly configured.

---

## 2. Naming Conventions

### 2.1 ID Style

This design uses string IDs for readability.

Examples:

```text
project_001
draft_003
draft_v012
snap_draft_003_v12
block_ch06_s01_p003
src_ch06_s01_240_306
char_arin
event_royal_fire
foreshadow_black_sun_knife
rel_arin_leon_001
```

In actual implementation, either of the following may be used:

```text
Option A: MongoDB ObjectId as _id + readable public_id
Option B: deterministic string _id
```

Recommended MVP:

```text
Use string _id for domain objects.
Use ObjectId only for logs, queue jobs, and append-only records if preferred.
```

---

### 2.2 Common Fields

Most collections should include:

```json
{
  "_id": "string",
  "project_id": "project_001",
  "user_id": "user_001",
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z",
  "status": "active"
}
```

Common status values:

```text
active
archived
deleted
deprecated
```

For AI-derived objects, use memory status:

```text
candidate
confirmed
canonical
needs_review
rejected
deprecated
```

---

## 3. Collection Overview

### 3.1 Core Project Collections

```text
users
projects
project_settings
writing_briefs
```

### 3.2 Draft and Source Collections

```text
drafts
draft_versions
source_snapshots
source_blocks
source_refs
```

### 3.3 Narrative Memory Collections

```text
entities
events
locations
organizations
items
concepts
foreshadowings
open_questions
relations
timeline_facts
character_knowledge
```

### 3.4 Style and Voice Collections

```text
style_profiles
voice_samples
style_rules
user_preferences
```

### 3.5 AI Runtime Collections

```text
writing_requests
writing_candidates
analysis_jobs
analysis_runs
analysis_tasks
analysis_results
analysis_candidates
context_search_requests
search_plans
context_packages
gate_results
```

### 3.6 Operational Collections

```text
index_sync_outbox
index_sync_logs
search_traces
review_requests
review_results
system_events
job_queue
```

---

# PART A. CORE PROJECT COLLECTIONS

---

## 4. users

### 4.1 Purpose

Stores user-level identity and default settings.

### 4.2 Document Example

```json
{
  "_id": "user_001",
  "email": "user@example.com",
  "display_name": "Yohan",
  "timezone": "Asia/Seoul",
  "locale": "ko-KR",
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z",
  "status": "active"
}
```

### 4.3 Indexes

```javascript
db.users.createIndex({ email: 1 }, { unique: true })
db.users.createIndex({ status: 1 })
```

---

## 5. projects

### 5.1 Purpose

Represents a writing project.

A project may be:

```text
novel
essay
blog
newsletter
research_note
screenplay
memoir
worldbuilding
```

### 5.2 Document Example

```json
{
  "_id": "project_001",
  "user_id": "user_001",
  "title": "검은 태양의 도시",
  "type": "novel",
  "language": "ko",
  "genre": ["fantasy", "mystery"],
  "description": "북부 국경 도시와 검은 태양단을 둘러싼 장편 판타지.",
  "default_writing_brief_id": "brief_001",
  "default_style_profile_id": "style_default",
  "status": "active",
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 5.3 Required Fields

```text
_id
user_id
title
type
language
status
created_at
updated_at
```

### 5.4 Indexes

```javascript
db.projects.createIndex({ user_id: 1, status: 1 })
db.projects.createIndex({ user_id: 1, updated_at: -1 })
db.projects.createIndex({ title: "text", description: "text" })
```

---

## 6. project_settings

### 6.1 Purpose

Stores project-level configuration.

### 6.2 Document Example

```json
{
  "_id": "project_settings_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "memory_policy": {
    "auto_analyze_on_save": true,
    "auto_confirm_high_confidence_candidates": false,
    "require_user_review_for_canon": true,
    "allow_cross_project_memory": false
  },
  "retrieval_policy": {
    "use_chroma": true,
    "use_elasticsearch": true,
    "always_reload_sot": true,
    "max_context_tokens": 6000
  },
  "analysis_policy": {
    "extract_characters": true,
    "extract_events": true,
    "extract_locations": true,
    "extract_foreshadowings": true,
    "extract_relations": true,
    "extract_timeline_facts": true,
    "extract_character_knowledge": true,
    "extract_style_signals": true
  },
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 6.3 Indexes

```javascript
db.project_settings.createIndex({ project_id: 1 }, { unique: true })
db.project_settings.createIndex({ user_id: 1 })
```

---

## 7. writing_briefs

### 7.1 Purpose

Stores the current writing contract for a project.

A writing brief defines:

```text
purpose
audience
genre
tone
style constraints
default retrieval policy
forbidden patterns
output preferences
```

### 7.2 Document Example

```json
{
  "_id": "brief_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "name": "기본 장편 소설 브리프",
  "purpose": "장편 판타지 소설 작성",
  "target_reader": "성인 판타지 독자",
  "genre": ["fantasy", "mystery"],
  "tone": ["차분함", "불길함", "서늘함"],
  "style_rules": [
    "직접 설명보다 장면으로 보여주기",
    "대사는 짧고 긴장감 있게",
    "과도한 감탄사 금지"
  ],
  "forbidden_patterns": [
    "그는 알 수 없는 감정을 느꼈다",
    "운명처럼",
    "설명하듯 모든 설정을 밝히는 문장"
  ],
  "preferred_patterns": [
    "감정은 행동과 사물 묘사로 암시한다",
    "떡밥은 직접 설명보다 반복 이미지로 남긴다"
  ],
  "default_context_policy": {
    "include_voice": true,
    "include_open_foreshadowing": true,
    "include_timeline": true,
    "include_recent_scenes": true,
    "include_character_knowledge": true
  },
  "status": "active",
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 7.3 Indexes

```javascript
db.writing_briefs.createIndex({ project_id: 1, status: 1 })
db.writing_briefs.createIndex({ user_id: 1, updated_at: -1 })
```

---

# PART B. DRAFT AND SOURCE COLLECTIONS

---

## 8. drafts

### 8.1 Purpose

Represents a logical writing document.

A draft may have many versions.

### 8.2 Document Example

```json
{
  "_id": "draft_003",
  "project_id": "project_001",
  "user_id": "user_001",
  "title": "6장 - 노스워치",
  "draft_type": "chapter",
  "current_version_id": "draft_v012",
  "current_snapshot_id": "snap_draft_003_v12",
  "chapter_id": "chapter_06",
  "scene_ids": ["scene_014", "scene_015"],
  "status": "active",
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 8.3 Indexes

```javascript
db.drafts.createIndex({ project_id: 1, status: 1 })
db.drafts.createIndex({ project_id: 1, updated_at: -1 })
db.drafts.createIndex({ project_id: 1, chapter_id: 1 })
```

---

## 9. draft_versions

### 9.1 Purpose

Stores each saved version of a draft.

This collection contains the full content for version history.

### 9.2 Document Example

```json
{
  "_id": "draft_v012",
  "project_id": "project_001",
  "user_id": "user_001",
  "draft_id": "draft_003",
  "version": 12,
  "title": "6장 - 노스워치",
  "content": "아린은 해가 기울 무렵 노스워치의 성문 앞에 도착했다...",
  "content_hash": "sha256:...",
  "snapshot_id": "snap_draft_003_v12",
  "parent_version_id": "draft_v011",
  "created_by": "user",
  "message": "노스워치 도착 장면 추가",
  "analysis_status": "completed",
  "created_at": "2026-06-23T00:00:00Z"
}
```

### 9.3 Required Fields

```text
_id
project_id
user_id
draft_id
version
content
content_hash
snapshot_id
created_by
created_at
```

### 9.4 Indexes

```javascript
db.draft_versions.createIndex({ project_id: 1, draft_id: 1, version: -1 })
db.draft_versions.createIndex({ snapshot_id: 1 }, { unique: true })
db.draft_versions.createIndex({ project_id: 1, created_at: -1 })
```

---

## 10. source_snapshots

### 10.1 Purpose

Immutable snapshot of a draft version or imported source.

All grounded analysis and source refs are anchored to snapshots.

### 10.2 Document Example

```json
{
  "_id": "snap_draft_003_v12",
  "project_id": "project_001",
  "user_id": "user_001",
  "source_type": "draft_version",
  "source_id": "draft_v012",
  "draft_id": "draft_003",
  "version": 12,
  "content_hash": "sha256:...",
  "normalized_text_hash": "sha256:...",
  "char_count": 5820,
  "language": "ko",
  "status": "active",
  "created_at": "2026-06-23T00:00:00Z"
}
```

### 10.3 Source Types

```text
draft_version
imported_document
user_note
user_canon_note
voice_sample
external_reference
```

### 10.4 Indexes

```javascript
db.source_snapshots.createIndex({ project_id: 1, source_type: 1, source_id: 1 })
db.source_snapshots.createIndex({ project_id: 1, draft_id: 1, version: -1 })
db.source_snapshots.createIndex({ content_hash: 1 })
db.source_snapshots.createIndex({ status: 1 })
```

---

## 11. source_blocks

### 11.1 Purpose

Stores block-level chunks derived from source snapshots.

Blocks are used for:

```text
source anchoring
analysis
retrieval
indexing
quote matching
span validation
```

### 11.2 Document Example

```json
{
  "_id": "block_ch06_s01_p003",
  "project_id": "project_001",
  "user_id": "user_001",
  "snapshot_id": "snap_draft_003_v12",
  "draft_id": "draft_003",
  "block_type": "paragraph",
  "chapter_id": "chapter_06",
  "scene_id": "scene_014",
  "order": 3,
  "text": "낡은 단검 손잡이에는 검은 태양 문양이 희미하게 떠올라 있었다.",
  "start_offset": 240,
  "end_offset": 306,
  "hash": "sha256:...",
  "created_at": "2026-06-23T00:00:00Z"
}
```

### 11.3 Block Types

```text
chapter
scene
paragraph
dialogue
sentence
section
note
```

### 11.4 Indexes

```javascript
db.source_blocks.createIndex({ project_id: 1, snapshot_id: 1, order: 1 })
db.source_blocks.createIndex({ project_id: 1, scene_id: 1, order: 1 })
db.source_blocks.createIndex({ project_id: 1, chapter_id: 1, scene_id: 1 })
db.source_blocks.createIndex({ hash: 1 })
db.source_blocks.createIndex({ text: "text" })
```

---

## 12. source_refs

### 12.1 Purpose

Stores exact span references inside source snapshots.

`source_refs` are the anchor for all claims, extracted memory, and gate evidence.

### 12.2 Document Example

```json
{
  "_id": "src_ch06_s01_240_306",
  "project_id": "project_001",
  "user_id": "user_001",
  "snapshot_id": "snap_draft_003_v12",
  "block_id": "block_ch06_s01_p003",
  "draft_id": "draft_003",
  "chapter_id": "chapter_06",
  "scene_id": "scene_014",
  "start_offset": 240,
  "end_offset": 306,
  "quote": "낡은 단검 손잡이에는 검은 태양 문양이 희미하게 떠올라 있었다.",
  "hash": "sha256:...",
  "created_at": "2026-06-23T00:00:00Z"
}
```

### 12.3 Indexes

```javascript
db.source_refs.createIndex({ project_id: 1, snapshot_id: 1, start_offset: 1, end_offset: 1 })
db.source_refs.createIndex({ project_id: 1, block_id: 1 })
db.source_refs.createIndex({ hash: 1 })
```

### 12.4 Integrity Rules

```text
- source_ref quote must match snapshot text span.
- source_ref must not be generated by LLM.
- source_ref must be generated by source storage layer.
- source_ref must remain stable for the same snapshot and span.
```

---

# PART C. NARRATIVE MEMORY COLLECTIONS

---

## 13. entities

### 13.1 Purpose

Stores general entities.

Characters are stored here as `entity_type: character`.

Other entity types may include:

```text
character
organization
item
concept
species
faction
title
artifact
```

Dedicated collections may exist for high-volume types, but `entities` is the central entity registry.

### 13.2 Document Example

```json
{
  "_id": "char_arin",
  "project_id": "project_001",
  "user_id": "user_001",
  "entity_type": "character",
  "name": "아린",
  "aliases": ["은빛 눈의 검사"],
  "summary": "북부 출신의 신중한 검사. 왕실을 불신하며 레온과 과거 동료였다.",
  "traits": ["신중함", "검술에 능함", "왕실 불신"],
  "attributes": {
    "origin": "북부",
    "occupation": "검사",
    "affiliation": null
  },
  "first_seen": {
    "chapter_id": "chapter_01",
    "scene_id": "scene_002",
    "source_ref": "src_ch01_s02_020_090"
  },
  "last_seen": {
    "chapter_id": "chapter_06",
    "scene_id": "scene_014",
    "source_ref": "src_ch06_s01_020_088"
  },
  "source_refs": ["src_ch01_s02_020_090"],
  "status": "confirmed",
  "canon_level": "project",
  "confidence": 0.95,
  "reviewed_by_user": false,
  "version": 4,
  "created_from_analysis_run": "analysis_run_001",
  "updated_from_analysis_run": "analysis_run_012",
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 13.3 Canon Levels

```text
candidate
scene
chapter
project
global
```

### 13.4 Indexes

```javascript
db.entities.createIndex({ project_id: 1, entity_type: 1, status: 1 })
db.entities.createIndex({ project_id: 1, name: 1 })
db.entities.createIndex({ project_id: 1, aliases: 1 })
db.entities.createIndex({ project_id: 1, updated_at: -1 })
db.entities.createIndex({ name: "text", aliases: "text", summary: "text", traits: "text" })
```

---

## 14. events

### 14.1 Purpose

Stores narrative events.

Events may be:

```text
backstory
current_plot
world_event
personal_event
battle
meeting
reveal
death
arrival
departure
conflict
```

### 14.2 Document Example

```json
{
  "_id": "event_royal_fire",
  "project_id": "project_001",
  "user_id": "user_001",
  "event_type": "backstory",
  "name": "왕궁 화재",
  "summary": "10년 전 왕궁 별관에서 원인 불명의 화재가 발생했다.",
  "participants": ["char_arin", "char_king"],
  "location_id": "loc_capital_palace",
  "narrative_order": 3,
  "story_time": "10년 전",
  "chapter_id": "chapter_02",
  "scene_id": "scene_004",
  "causes": [],
  "consequences": [
    "아린의 가족이 실종됨",
    "아린이 왕실을 불신하게 됨"
  ],
  "source_refs": ["src_ch02_s04_300_420"],
  "status": "confirmed",
  "confidence": 0.91,
  "version": 2,
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 14.3 Indexes

```javascript
db.events.createIndex({ project_id: 1, event_type: 1, status: 1 })
db.events.createIndex({ project_id: 1, narrative_order: 1 })
db.events.createIndex({ project_id: 1, chapter_id: 1, scene_id: 1 })
db.events.createIndex({ project_id: 1, participants: 1 })
db.events.createIndex({ name: "text", summary: "text", consequences: "text" })
```

---

## 15. locations

### 15.1 Purpose

Stores places.

### 15.2 Document Example

```json
{
  "_id": "loc_northwatch",
  "project_id": "project_001",
  "user_id": "user_001",
  "name": "노스워치",
  "aliases": ["북부 감시성"],
  "location_type": "city",
  "region": "북부 국경",
  "summary": "북부 국경에 위치한 폐쇄적이고 군사적인 도시.",
  "mood": ["춥다", "군사적", "폐쇄적", "불길함"],
  "features": ["성벽", "검문소", "오래된 종탑"],
  "parent_location_id": "region_north_border",
  "related_events": ["event_border_battle"],
  "source_refs": ["src_ch06_s01_000_160"],
  "status": "confirmed",
  "confidence": 0.9,
  "version": 1,
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 15.3 Indexes

```javascript
db.locations.createIndex({ project_id: 1, name: 1 })
db.locations.createIndex({ project_id: 1, aliases: 1 })
db.locations.createIndex({ project_id: 1, location_type: 1, status: 1 })
db.locations.createIndex({ project_id: 1, region: 1 })
db.locations.createIndex({ name: "text", aliases: "text", summary: "text", mood: "text", features: "text" })
```

---

## 16. organizations

### 16.1 Purpose

Stores factions, institutions, guilds, kingdoms, cults, and groups.

### 16.2 Document Example

```json
{
  "_id": "org_black_sun",
  "project_id": "project_001",
  "user_id": "user_001",
  "name": "검은 태양단",
  "aliases": ["검은 태양"],
  "organization_type": "secret_society",
  "summary": "검은 태양 문양을 사용하는 비밀 조직.",
  "known_members": [],
  "symbols": ["검은 태양 문양"],
  "related_items": ["item_black_sun_knife"],
  "source_refs": ["src_ch02_s01_084_112"],
  "status": "candidate",
  "confidence": 0.72,
  "reviewed_by_user": false,
  "version": 1,
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 16.3 Indexes

```javascript
db.organizations.createIndex({ project_id: 1, name: 1 })
db.organizations.createIndex({ project_id: 1, aliases: 1 })
db.organizations.createIndex({ project_id: 1, organization_type: 1, status: 1 })
db.organizations.createIndex({ name: "text", aliases: "text", summary: "text", symbols: "text" })
```

---

## 17. items

### 17.1 Purpose

Stores important objects, artifacts, weapons, documents, clues, or symbolic items.

### 17.2 Document Example

```json
{
  "_id": "item_black_sun_knife",
  "project_id": "project_001",
  "user_id": "user_001",
  "name": "검은 태양 문양의 단검",
  "aliases": ["낡은 단검", "검은 태양 단검"],
  "item_type": "weapon",
  "summary": "손잡이에 검은 태양 문양이 새겨진 낡은 단검.",
  "current_owner": "char_arin",
  "symbolic_meaning": ["떡밥", "검은 태양단과의 연결 가능성"],
  "related_foreshadowings": ["foreshadow_black_sun_knife"],
  "source_refs": ["src_ch02_s01_084_112"],
  "status": "confirmed",
  "confidence": 0.9,
  "version": 1,
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 17.3 Indexes

```javascript
db.items.createIndex({ project_id: 1, name: 1 })
db.items.createIndex({ project_id: 1, aliases: 1 })
db.items.createIndex({ project_id: 1, item_type: 1, status: 1 })
db.items.createIndex({ project_id: 1, current_owner: 1 })
db.items.createIndex({ name: "text", aliases: "text", summary: "text", symbolic_meaning: "text" })
```

---

## 18. concepts

### 18.1 Purpose

Stores abstract concepts, rules, magic systems, ideologies, themes, or technical ideas.

### 18.2 Document Example

```json
{
  "_id": "concept_black_sun_symbol",
  "project_id": "project_001",
  "user_id": "user_001",
  "name": "검은 태양 문양",
  "concept_type": "symbol",
  "summary": "검은 태양단과 관련된 것으로 보이는 반복 상징.",
  "related_entities": ["org_black_sun", "item_black_sun_knife"],
  "source_refs": ["src_ch02_s01_084_112"],
  "status": "candidate",
  "confidence": 0.78,
  "version": 1,
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 18.3 Indexes

```javascript
db.concepts.createIndex({ project_id: 1, name: 1 })
db.concepts.createIndex({ project_id: 1, concept_type: 1, status: 1 })
db.concepts.createIndex({ name: "text", summary: "text" })
```

---

## 19. foreshadowings

### 19.1 Purpose

Stores setup/payoff structures.

### 19.2 Document Example

```json
{
  "_id": "foreshadow_black_sun_knife",
  "project_id": "project_001",
  "user_id": "user_001",
  "title": "검은 태양 문양의 단검",
  "setup": "낡은 단검 손잡이에 검은 태양 문양이 새겨져 있다.",
  "introduced_at": {
    "chapter_id": "chapter_02",
    "scene_id": "scene_005",
    "source_ref": "src_ch02_s01_084_112"
  },
  "status": "unresolved",
  "memory_status": "confirmed",
  "related_entities": ["item_black_sun_knife", "org_black_sun"],
  "possible_payoff": "검은 태양단과 연결될 가능성",
  "payoff": null,
  "payoff_at": null,
  "source_refs": ["src_ch02_s01_084_112"],
  "confidence": 0.91,
  "reviewed_by_user": false,
  "version": 2,
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 19.3 Foreshadowing Status

```text
unresolved
developing
resolved
abandoned
false_lead
deprecated
```

### 19.4 Indexes

```javascript
db.foreshadowings.createIndex({ project_id: 1, status: 1 })
db.foreshadowings.createIndex({ project_id: 1, memory_status: 1 })
db.foreshadowings.createIndex({ project_id: 1, "introduced_at.chapter_id": 1, "introduced_at.scene_id": 1 })
db.foreshadowings.createIndex({ project_id: 1, related_entities: 1 })
db.foreshadowings.createIndex({ title: "text", setup: "text", possible_payoff: "text", payoff: "text" })
```

---

## 20. open_questions

### 20.1 Purpose

Stores unresolved narrative questions.

Open questions are broader than foreshadowings.

### 20.2 Document Example

```json
{
  "_id": "oq_leon_motive",
  "project_id": "project_001",
  "user_id": "user_001",
  "question": "레온은 왜 왕실과 거래했는가?",
  "question_type": "character_motive",
  "introduced_at": {
    "chapter_id": "chapter_05",
    "scene_id": "scene_003",
    "source_ref": "src_ch05_s03_100_144"
  },
  "status": "open",
  "related_entities": ["char_leon", "royal_court"],
  "possible_answers": [],
  "resolved_answer": null,
  "source_refs": ["src_ch05_s03_100_144"],
  "confidence": 0.87,
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 20.3 Status

```text
open
partially_answered
answered
abandoned
deprecated
```

### 20.4 Indexes

```javascript
db.open_questions.createIndex({ project_id: 1, status: 1 })
db.open_questions.createIndex({ project_id: 1, question_type: 1 })
db.open_questions.createIndex({ project_id: 1, related_entities: 1 })
db.open_questions.createIndex({ question: "text", possible_answers: "text", resolved_answer: "text" })
```

---

## 21. relations

### 21.1 Purpose

Stores edges between narrative objects.

Relations can connect:

```text
character → character
character → location
character → item
event → event
event → location
foreshadowing → item
organization → character
concept → organization
```

### 21.2 Document Example

```json
{
  "_id": "rel_arin_leon_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "from_id": "char_arin",
  "from_collection": "entities",
  "to_id": "char_leon",
  "to_collection": "entities",
  "relation_type": "former_ally",
  "status_label": "strained",
  "summary": "아린과 레온은 과거 동료였으나 현재 관계가 틀어져 있다.",
  "valid_from": {
    "chapter_id": "chapter_04",
    "scene_id": "scene_001"
  },
  "valid_until": null,
  "source_refs": ["src_ch04_s01_080_130"],
  "memory_status": "confirmed",
  "confidence": 0.9,
  "version": 1,
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 21.3 Indexes

```javascript
db.relations.createIndex({ project_id: 1, from_id: 1, relation_type: 1 })
db.relations.createIndex({ project_id: 1, to_id: 1, relation_type: 1 })
db.relations.createIndex({ project_id: 1, from_id: 1, to_id: 1 })
db.relations.createIndex({ project_id: 1, memory_status: 1 })
db.relations.createIndex({ summary: "text", relation_type: "text", status_label: "text" })
```

---

## 22. timeline_facts

### 22.1 Purpose

Stores timeline constraints and facts.

Used by:

```text
Continuity Gate
POV Gate
Writing Agent context
Agentic Search
```

### 22.2 Document Example

```json
{
  "_id": "timeline_fact_023",
  "project_id": "project_001",
  "user_id": "user_001",
  "fact": "아린은 chapter_08 이전에는 레온의 배신을 알지 못한다.",
  "constraint_type": "pov_knowledge",
  "applies_to": ["char_arin", "char_leon"],
  "valid_from": {
    "chapter_id": "chapter_01",
    "scene_id": "scene_001"
  },
  "valid_until": {
    "chapter_id": "chapter_08",
    "scene_id": "scene_002"
  },
  "source_refs": ["src_ch05_s03_100_144"],
  "memory_status": "canonical",
  "confidence": 0.98,
  "reviewed_by_user": true,
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 22.3 Constraint Types

```text
pov_knowledge
event_order
location_presence
character_alive_status
relationship_status
item_ownership
world_rule_validity
```

### 22.4 Indexes

```javascript
db.timeline_facts.createIndex({ project_id: 1, constraint_type: 1, memory_status: 1 })
db.timeline_facts.createIndex({ project_id: 1, applies_to: 1 })
db.timeline_facts.createIndex({ project_id: 1, "valid_from.chapter_id": 1, "valid_from.scene_id": 1 })
db.timeline_facts.createIndex({ fact: "text" })
```

---

## 23. character_knowledge

### 23.1 Purpose

Tracks what a character knows or does not know at a given narrative point.

### 23.2 Document Example

```json
{
  "_id": "knowledge_arin_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "character_id": "char_arin",
  "knows": [
    {
      "fact": "레온이 북부 전투에 참여했다.",
      "source_refs": ["src_ch04_s02_300_350"]
    }
  ],
  "does_not_know": [
    {
      "fact": "레온이 왕실과 거래했다.",
      "valid_until": {
        "chapter_id": "chapter_08",
        "scene_id": "scene_002"
      },
      "source_refs": ["src_ch05_s03_100_144"]
    }
  ],
  "valid_at": {
    "chapter_id": "chapter_06",
    "scene_id": "scene_014"
  },
  "memory_status": "confirmed",
  "confidence": 0.9,
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 23.3 Indexes

```javascript
db.character_knowledge.createIndex({ project_id: 1, character_id: 1 })
db.character_knowledge.createIndex({ project_id: 1, "valid_at.chapter_id": 1, "valid_at.scene_id": 1 })
db.character_knowledge.createIndex({ project_id: 1, memory_status: 1 })
```

---

# PART D. STYLE AND VOICE COLLECTIONS

---

## 24. style_profiles

### 24.1 Purpose

Stores project-level or user-level style configuration.

### 24.2 Document Example

```json
{
  "_id": "style_default",
  "project_id": "project_001",
  "user_id": "user_001",
  "name": "기본 서술 문체",
  "scope": "project",
  "summary": "차분하고 서늘하며 직접 설명을 피하는 문체.",
  "positive_rules": [
    "감정은 행동과 주변 사물로 암시한다.",
    "문장은 지나치게 길지 않게 유지한다."
  ],
  "negative_rules": [
    "과장된 감탄사를 피한다.",
    "AI스러운 일반론을 피한다."
  ],
  "preferred_phrases": [],
  "forbidden_phrases": [
    "알 수 없는 감정",
    "운명처럼"
  ],
  "status": "active",
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 24.3 Indexes

```javascript
db.style_profiles.createIndex({ project_id: 1, scope: 1, status: 1 })
db.style_profiles.createIndex({ user_id: 1, status: 1 })
```

---

## 25. voice_samples

### 25.1 Purpose

Stores user writing samples for style retrieval and voice matching.

### 25.2 Document Example

```json
{
  "_id": "voice_sample_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "style_profile_id": "style_default",
  "title": "어두운 장면 샘플",
  "text": "비가 그친 골목에는 물웅덩이만 남아 있었다...",
  "source_snapshot_id": "snap_voice_sample_001",
  "source_refs": ["src_voice_001_000_120"],
  "tags": ["dark", "calm", "descriptive"],
  "language": "ko",
  "status": "active",
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 25.3 Indexes

```javascript
db.voice_samples.createIndex({ project_id: 1, style_profile_id: 1 })
db.voice_samples.createIndex({ user_id: 1, tags: 1 })
db.voice_samples.createIndex({ text: "text", tags: "text" })
```

---

## 26. style_rules

### 26.1 Purpose

Stores individual style rules, including rules extracted by Analysis AI.

### 26.2 Document Example

```json
{
  "_id": "style_rule_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "style_profile_id": "style_default",
  "rule_type": "negative",
  "rule": "감정을 직접 설명하는 문장을 피한다.",
  "examples": [
    {
      "bad": "그는 알 수 없는 감정을 느꼈다.",
      "better": "그는 손끝으로 젖은 난간을 문질렀다."
    }
  ],
  "source_refs": [],
  "memory_status": "canonical",
  "created_by": "user",
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 26.3 Indexes

```javascript
db.style_rules.createIndex({ project_id: 1, style_profile_id: 1, rule_type: 1 })
db.style_rules.createIndex({ project_id: 1, memory_status: 1 })
db.style_rules.createIndex({ rule: "text", examples: "text" })
```

---

## 27. user_preferences

### 27.1 Purpose

Stores reusable user preferences.

Some preferences are project-specific.  
Some preferences are global.

### 27.2 Document Example

```json
{
  "_id": "pref_001",
  "user_id": "user_001",
  "project_id": "project_001",
  "scope": "project",
  "key": "avoid_ai_tone",
  "value": true,
  "source": "user",
  "status": "active",
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 27.3 Indexes

```javascript
db.user_preferences.createIndex({ user_id: 1, scope: 1 })
db.user_preferences.createIndex({ project_id: 1, key: 1 })
db.user_preferences.createIndex({ user_id: 1, key: 1 })
```

---

# PART E. AI RUNTIME COLLECTIONS

---

## 28. writing_requests

### 28.1 Purpose

Stores user writing requests and system-generated writing tasks.

### 28.2 Document Example

```json
{
  "_id": "write_req_001",
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
    "include_foreshadowing": true
  },
  "generation_options": {
    "language": "ko",
    "length": "1200-1800자",
    "output_mode": "draft_patch",
    "tone": ["차분함", "불길함"]
  },
  "status": "completed",
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 28.3 Indexes

```javascript
db.writing_requests.createIndex({ project_id: 1, created_at: -1 })
db.writing_requests.createIndex({ user_id: 1, created_at: -1 })
db.writing_requests.createIndex({ project_id: 1, task_type: 1 })
```

---

## 29. writing_candidates

### 29.1 Purpose

Stores AI-generated draft candidates.

### 29.2 Document Example

```json
{
  "_id": "draft_candidate_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "request_id": "write_req_001",
  "output_type": "draft_patch",
  "text": "아린은 해가 기울 무렵 노스워치의 성문 앞에 도착했다...",
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
  "gate_result_id": "writing_gate_001",
  "status": "candidate",
  "created_at": "2026-06-23T00:00:00Z"
}
```

### 29.3 Indexes

```javascript
db.writing_candidates.createIndex({ project_id: 1, request_id: 1 })
db.writing_candidates.createIndex({ project_id: 1, created_at: -1 })
db.writing_candidates.createIndex({ project_id: 1, status: 1 })
```

---

## 30. analysis_jobs

### 30.1 Purpose

Top-level analysis job triggered by save/import/manual analysis.

### 30.2 Document Example

```json
{
  "_id": "analysis_job_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "snapshot_id": "snap_draft_003_v12",
  "trigger": "draft_saved",
  "tasks": [
    "scene_split",
    "entity_extraction",
    "event_extraction",
    "location_extraction",
    "foreshadowing_extraction",
    "relationship_extraction",
    "timeline_extraction"
  ],
  "status": "completed",
  "created_at": "2026-06-23T00:00:00Z",
  "started_at": "2026-06-23T00:00:01Z",
  "finished_at": "2026-06-23T00:00:12Z"
}
```

### 30.3 Status

```text
queued
running
completed
failed
cancelled
partial
```

### 30.4 Indexes

```javascript
db.analysis_jobs.createIndex({ project_id: 1, created_at: -1 })
db.analysis_jobs.createIndex({ project_id: 1, snapshot_id: 1 })
db.analysis_jobs.createIndex({ status: 1, created_at: 1 })
```

---

## 31. analysis_runs

### 31.1 Purpose

Stores actual model/provider run metadata.

An analysis job may have multiple runs.

### 31.2 Document Example

```json
{
  "_id": "analysis_run_012",
  "project_id": "project_001",
  "user_id": "user_001",
  "analysis_job_id": "analysis_job_001",
  "task_type": "foreshadowing_extraction",
  "provider": "gemma_local",
  "model": "gemma-4-12b-q4",
  "input_snapshot_id": "snap_draft_003_v12",
  "input_block_ids": ["block_ch06_s01_p003"],
  "prompt_version": "analysis_foreshadowing_v1",
  "status": "completed",
  "token_usage": {
    "input_tokens": 2200,
    "output_tokens": 600
  },
  "created_at": "2026-06-23T00:00:00Z",
  "finished_at": "2026-06-23T00:00:04Z"
}
```

### 31.3 Indexes

```javascript
db.analysis_runs.createIndex({ project_id: 1, analysis_job_id: 1 })
db.analysis_runs.createIndex({ project_id: 1, task_type: 1, created_at: -1 })
db.analysis_runs.createIndex({ status: 1 })
```

---

## 32. analysis_tasks

### 32.1 Purpose

Stores per-task payload metadata.

### 32.2 Document Example

```json
{
  "_id": "analysis_task_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "analysis_job_id": "analysis_job_001",
  "task_type": "entity_extraction",
  "snapshot_id": "snap_draft_003_v12",
  "block_ids": ["block_ch06_s01_p001", "block_ch06_s01_p002"],
  "known_entities": ["char_arin", "char_leon"],
  "status": "completed",
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:06Z"
}
```

### 32.3 Indexes

```javascript
db.analysis_tasks.createIndex({ project_id: 1, analysis_job_id: 1 })
db.analysis_tasks.createIndex({ project_id: 1, task_type: 1, status: 1 })
```

---

## 33. analysis_results

### 33.1 Purpose

Stores raw structured output of Analysis AI before candidate merge.

### 33.2 Document Example

```json
{
  "_id": "analysis_result_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "analysis_job_id": "analysis_job_001",
  "analysis_task_id": "analysis_task_001",
  "analysis_run_id": "analysis_run_012",
  "task_type": "entity_extraction",
  "snapshot_id": "snap_draft_003_v12",
  "raw_output": {
    "candidates": []
  },
  "schema_valid": true,
  "status": "processed",
  "created_at": "2026-06-23T00:00:00Z"
}
```

### 33.3 Indexes

```javascript
db.analysis_results.createIndex({ project_id: 1, analysis_job_id: 1 })
db.analysis_results.createIndex({ project_id: 1, analysis_task_id: 1 })
db.analysis_results.createIndex({ project_id: 1, task_type: 1 })
```

---

## 34. analysis_candidates

### 34.1 Purpose

Stores individual extracted memory candidates.

This is an important review boundary.

### 34.2 Document Example

```json
{
  "_id": "analysis_candidate_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "analysis_result_id": "analysis_result_001",
  "analysis_job_id": "analysis_job_001",
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
  "gate_result_id": "analysis_gate_001",
  "review_result_id": null,
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 34.3 Candidate Types

```text
character
character_fact
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
style_signal
```

### 34.4 Indexes

```javascript
db.analysis_candidates.createIndex({ project_id: 1, status: 1 })
db.analysis_candidates.createIndex({ project_id: 1, candidate_type: 1, status: 1 })
db.analysis_candidates.createIndex({ project_id: 1, matched_existing_id: 1 })
db.analysis_candidates.createIndex({ project_id: 1, analysis_job_id: 1 })
db.analysis_candidates.createIndex({ confidence: -1 })
```

---

## 35. context_search_requests

### 35.1 Purpose

Stores requests to Agentic Search.

### 35.2 Document Example

```json
{
  "_id": "search_req_001",
  "project_id": "project_001",
  "user_id": "user_001",
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
  },
  "status": "completed",
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:01Z"
}
```

### 35.3 Indexes

```javascript
db.context_search_requests.createIndex({ project_id: 1, created_at: -1 })
db.context_search_requests.createIndex({ project_id: 1, purpose: 1 })
db.context_search_requests.createIndex({ user_id: 1, created_at: -1 })
```

---

## 36. search_plans

### 36.1 Purpose

Stores Agentic Search plans.

### 36.2 Document Example

```json
{
  "_id": "search_plan_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "search_request_id": "search_req_001",
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
    }
  ],
  "status": "executed",
  "created_at": "2026-06-23T00:00:00Z"
}
```

### 36.3 Indexes

```javascript
db.search_plans.createIndex({ project_id: 1, search_request_id: 1 })
db.search_plans.createIndex({ project_id: 1, created_at: -1 })
```

---

## 37. context_packages

### 37.1 Purpose

Stores final context packages passed to AI agents.

### 37.2 Document Example

```json
{
  "_id": "ctx_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "search_request_id": "search_req_001",
  "search_plan_id": "search_plan_001",
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
      "text": "레온의 배신 사실을 직접 서술하지 말 것."
    }
  ],
  "token_estimate": 5400,
  "gate_result_id": "ctx_gate_001",
  "status": "confirmed",
  "created_at": "2026-06-23T00:00:00Z"
}
```

### 37.3 Indexes

```javascript
db.context_packages.createIndex({ project_id: 1, search_request_id: 1 })
db.context_packages.createIndex({ project_id: 1, purpose: 1, created_at: -1 })
db.context_packages.createIndex({ project_id: 1, status: 1 })
```

---

## 38. gate_results

### 38.1 Purpose

Stores verification results.

### 38.2 Document Example

```json
{
  "_id": "writing_gate_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "gate_type": "writing_gate",
  "target_type": "writing_candidate",
  "target_id": "draft_candidate_001",
  "decision": "block",
  "severity": "high",
  "findings": [
    {
      "type": "pov",
      "severity": "error",
      "message": "아린은 현재 scene_014 시점에서 레온의 배신을 알 수 없음.",
      "evidence": "아린은 레온의 배신을 떠올렸다.",
      "recommended_decision": "block"
    }
  ],
  "created_at": "2026-06-23T00:00:00Z"
}
```

이 문서는 future persistence sketch다. v1.6.69 Writing Gate는 비영속이며,
실제 저장 collection·pointer envelope는 별도 persistence 결정 전까지 미확정이다.

### 38.3 Gate Types

```text
context_gate
writing_gate
analysis_gate
index_gate
continuity_gate
canon_gate
pov_gate
voice_gate
```

### 38.4 Decisions

```text
pass
revise
retrieve_more
needs_user_review
block
```

### 38.5 Indexes

```javascript
db.gate_results.createIndex({ project_id: 1, gate_type: 1, created_at: -1 })
db.gate_results.createIndex({ project_id: 1, target_type: 1, target_id: 1 })
db.gate_results.createIndex({ project_id: 1, decision: 1 })
```

---

# PART F. OPERATIONAL COLLECTIONS

---

## 39A. index_sync_outbox

### 39A.1 Purpose

Stores pending one-way index synchronization requests before worker execution.

Direction:

```text
MongoDB → index_sync_outbox → worker/adapter → index_sync_logs
```

Phase 3B first slice creates outbox entries for archive events only:

```text
project_archived
draft_archived
```

`analysis_completed` is a later event candidate and is not enabled until candidate indexing/review status is defined.

### 39A.2 Document Example

```json
{
  "_id": "sync_req_001",
  "sync_request_id": "sync_req_001",
  "project_id": "project_001",
  "user_id": null,
  "event": "project_archived",
  "source": {
    "mongo_collection": "projects",
    "mongo_id": "project_001",
    "mongo_version": null
  },
  "targets": {
    "chroma": {
      "status": "pending",
      "backend": "in_memory_fake"
    }
  },
  "status": "pending",
  "attempt_count": 0,
  "max_attempts": 3,
  "next_attempt_at": null,
  "claimed_at": null,
  "last_error": null
}
```

`last_error.error_type` must distinguish server/backend failures from missing-data failures:

```text
backend_error
not_found
```

### 39A.3 Idempotency

Repeated archive calls must not create duplicate active requests.

Dedup key:

```javascript
{ project_id: 1, event: 1, "source.mongo_collection": 1, "source.mongo_id": 1 }
```

`index_sync_outbox` and `index_sync_logs` join by `sync_request_id`.

`index_sync_outbox` is the active queue. When a request reaches terminal
`success` or `failed`, the active outbox document is removed and terminal
attempt/result history remains in `index_sync_logs`. This keeps the existing
unique index scoped to active outbox documents while still allowing a later
archive event with the same dedup key to create a new active request.

### 39A.4 Indexes

```javascript
db.index_sync_outbox.createIndex(
  { project_id: 1, event: 1, "source.mongo_collection": 1, "source.mongo_id": 1 },
  { unique: true, name: "uniq_index_sync_outbox_event_source" }
)
db.index_sync_outbox.createIndex(
  { status: 1, next_attempt_at: 1, claimed_at: 1, sync_request_id: 1 },
  { name: "index_sync_outbox_by_status_next_attempt" }
)
```

---

## 39B. memory_entries

### 39B.1 Purpose

Canonical (approved) narrative memory store. Phase 2B.1 creates the first
version of a memory by promoting a Phase 2A `needs_review` analysis candidate.
It preserves the candidate's payload, provenance, source refs, and confidence
and records the promotion audit trail. Entity/scope key resolution and versioned
upsert are later slices (2B.3/2B.4).

Promotion paths:

```text
manual          # user approval; always canonical, confidence-independent
auto_threshold  # deterministic system threshold gate; only when confidence >= threshold
```

Status is `canonical` (single literal). Candidates below the auto-promotion
threshold stay `needs_review` in `analysis_candidates`; they do not appear here.

### 39B.2 Document Example

```json
{
  "_id": "mem_001",
  "project_id": "project_001",
  "memory_type": "character_observation",
  "status": "canonical",
  "provenance": "source_observed",
  "confidence": 0.9,
  "source_ref_ids": ["source_ref_001"],
  "payload": { "name": "Ariel", "observation": "brave under pressure" },
  "version": 1,
  "analysis_job_id": "analysis_job_001",
  "source_candidate_id": "candidate_001",
  "promotion_mode": "auto_threshold",
  "applied_threshold": 0.9
}
```

`applied_threshold` is `null` for manual promotion.

### 39B.3 Idempotency

Promoting the same candidate twice returns the same memory (no duplicate).

Dedup key:

```javascript
{ project_id: 1, source_candidate_id: 1 }
```

Phase 2B.1 uniqueness is scoped to `source_candidate_id` only. Deterministic
entity/scope key matching (`memory_type + scope_type + scope_id + name`) and the
reconciliation of duplicate canonical entries for the same entity are compare
(2B.3) concerns and are not enforced here.

### 39B.4 Indexes

```javascript
db.memory_entries.createIndex(
  { project_id: 1, source_candidate_id: 1 },
  { unique: true, name: "uniq_memory_candidate_promotion" }
)
db.memory_entries.createIndex(
  { project_id: 1 },
  { name: "memory_entries_by_project" }
)
```

---

## 39. index_sync_logs

### 39.1 Purpose

Stores one-way index synchronization attempt/result history.

Direction:

```text
MongoDB → index_sync_outbox → worker/adapter → index_sync_logs
```

### 39.2 Document Example

```json
{
  "_id": "sync_001",
  "sync_log_id": "sync_001",
  "sync_request_id": "sync_req_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "event": "analysis_completed",
  "source": {
    "mongo_collection": "foreshadowings",
    "mongo_id": "foreshadow_black_sun_knife",
    "mongo_version": 2
  },
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
  "status": "success",
  "attempt_count": 1,
  "error": null,
  "started_at": "2026-06-23T00:00:00Z",
  "finished_at": "2026-06-23T00:00:02Z"
}
```

### 39.3 Indexes

```javascript
db.index_sync_logs.createIndex({ project_id: 1, started_at: -1 })
db.index_sync_logs.createIndex({ project_id: 1, "source.mongo_collection": 1, "source.mongo_id": 1 })
db.index_sync_logs.createIndex({ status: 1, started_at: -1 })
db.index_sync_logs.createIndex({ sync_request_id: 1, attempt_count: 1 })
db.index_sync_logs.createIndex({ project_id: 1, sync_request_id: 1 })
```

---

## 40. search_traces

### 40.1 Purpose

Stores Agentic Search execution traces.

### 40.2 Document Example

```json
{
  "_id": "search_trace_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "search_request_id": "search_req_001",
  "search_plan_id": "search_plan_001",
  "query": "아린이 노스워치에 도착하는 장면",
  "steps": [
    {
      "tool": "elasticsearch",
      "query": "아린",
      "filters": {
        "entity_type": "character"
      },
      "result_count": 3,
      "candidate_ids": ["es_char_arin_v4"]
    },
    {
      "tool": "chroma",
      "query": "노스워치 불길한 분위기",
      "result_count": 8,
      "candidate_ids": ["vec_loc_northwatch_v1"]
    },
    {
      "tool": "mongo",
      "action": "sot_reload",
      "result_count": 6,
      "resolved_ids": ["char_arin", "loc_northwatch"]
    }
  ],
  "context_package_id": "ctx_001",
  "status": "completed",
  "created_at": "2026-06-23T00:00:00Z"
}
```

### 40.3 Indexes

```javascript
db.search_traces.createIndex({ project_id: 1, created_at: -1 })
db.search_traces.createIndex({ project_id: 1, search_request_id: 1 })
db.search_traces.createIndex({ project_id: 1, search_plan_id: 1 })
```

---

## 41. review_requests

### 41.1 Purpose

Stores items that require user review.

### 41.2 Document Example

```json
{
  "_id": "review_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "object_type": "analysis_candidate",
  "object_id": "analysis_candidate_001",
  "reason": "Possible new canon conflicts with existing timeline.",
  "options": ["confirm", "reject", "edit", "defer"],
  "status": "open",
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 41.3 Indexes

```javascript
db.review_requests.createIndex({ project_id: 1, status: 1, created_at: -1 })
db.review_requests.createIndex({ user_id: 1, status: 1 })
db.review_requests.createIndex({ object_type: 1, object_id: 1 })
```

---

## 42. review_results

### 42.1 Purpose

Stores user decisions on review requests.

### 42.2 Document Example

```json
{
  "_id": "review_result_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "review_request_id": "review_001",
  "decision": "confirm",
  "user_edit": null,
  "applied_to": {
    "mongo_collection": "analysis_candidates",
    "mongo_id": "analysis_candidate_001"
  },
  "created_at": "2026-06-23T00:00:00Z"
}
```

### 42.3 Decisions

```text
confirm
reject
edit
defer
```

### 42.4 Indexes

```javascript
db.review_results.createIndex({ project_id: 1, created_at: -1 })
db.review_results.createIndex({ user_id: 1, created_at: -1 })
db.review_results.createIndex({ review_request_id: 1 }, { unique: true })
```

---

## 43. system_events — **폐기됨 (Phase 9, 2026-08-09). 후속은 §43G `activity_events`.**

> **★ 이 절은 구현되지 않았고 앞으로도 구현되지 않는다.** 2026-08-05 실측에서
> `services/`·`scripts/`·`tests/` 전수 grep **0건**이었고(문서에만 있던 스펙 유령),
> Phase 9 오너 결정 **A1=A**(2026-08-09)가 그 자리를 **§43G `activity_events`** 로
> 대체했다. **이름이 내용과 어긋난 것이 폐기 사유다** — 담기려던 것은 사용자 행위인데
> "system" 이라, 훗날 진짜 시스템 이벤트(배포·워커 장애)가 생기면 섞인다. 이 저장소는
> 이름이 뜻과 어긋나 사고가 날 뻔한 적이 있다(8.2 `project_id` vs `target_project_id`).
>
> 아래 스펙은 **역사로만 남긴다** — 특히 `payload` 자유형은 A3=B 가 기각했다(문서 키
> 집합을 고정해야 파기 reconciler 의 표본 한 건 판정이 안전하다).

### 43.1 Purpose

General event log for debugging and audit. **(미구현·폐기)**

### 43.2 Document Example

```json
{
  "_id": "evt_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "event_type": "draft_saved",
  "payload": {
    "draft_id": "draft_003",
    "draft_version_id": "draft_v012",
    "snapshot_id": "snap_draft_003_v12"
  },
  "created_at": "2026-06-23T00:00:00Z"
}
```

### 43.3 Indexes

```javascript
db.system_events.createIndex({ project_id: 1, created_at: -1 })
db.system_events.createIndex({ event_type: 1, created_at: -1 })
db.system_events.createIndex({ user_id: 1, created_at: -1 })
```

---

## 43G. activity_events

### 43G.1 Purpose

**누가 · 언제 · 무엇을 바꿨는가.** Phase 9 Slice 9.0(오너 결정 A1~A8, 2026-08-09,
`docs/plans/09-0-service-activity-log-decisions.md`). §43 `system_events` 를 대체한다.

**★ 이 컬렉션은 프로젝트 자식이다** — `project_id` 필드를 쓰고 **파기와 함께 사라진다**.
§43F `project_name_history` 와 **정반대 방향이고 그것이 의도다**: 그쪽은 `_id` 를 project id
로 써서 파기 reconciler 의 고아 sweep 을 구조적으로 피하고, 여기는 **반드시 발견되어야**
한다. 활동 로그를 파기 생존으로 만들면 개명 이력·제목·저장 이벤트 전체가 삭제 예외로
승격돼 **D8-6 삭제 계약이 무너진다**(부모 계획 §4 I1·I2).

**무엇이 담기는가(A2=B)**: 정본 변경 **11** + 검토 결정 9 = **20 경로**(착수 결정은 19 였고 2026-08-09 에 오너가 `writing/accept` 를 더했다 — 그 경로는 정본 draft version 을 저장한다). AI 요청은 여기 담기지
않는다 — `llm_call_audits`(호출 단위)와 `request_usage_ledger`(과금 단위)가 이미 담으며,
세 번째 사본은 두 정본 문제다(A8=A). 분류 정본은 **코드**
(`services/application/app/activity/actions.py`)이고 mutating operation **40 전수**가
`logged`/`excluded(사유)` 로 등재된다 — 미등재는 `tests/test_activity_actions.py` 가
실패시킨다.

### 43G.2 Document Example

```json
{
  "_id": "evt_001",
  "project_id": "project_001",
  "actor_user_id": "user_001",
  "action": "project_renamed",
  "target_type": "project",
  "target_id": "project_001",
  "at": "2026-08-09T00:00:00Z",
  "before": "옛 이름",
  "after": "새 이름"
}
```

**키 집합이 계약이다.** 새 필드는 계약 변경이며 회귀가 고정한다. `before`/`after` 는
**짧은 라벨만**(이름·제목·상태, 200자 상한 — A3=B) 담는다: 본문 이력은 이미
`draft_versions`+`source_snapshots` 에 있고 복제하면 두 정본이 된다. 값 변화가 없는
행(생성·저장·검토 결정)은 둘 다 `null` 이다.

### 43G.3 Indexes

```javascript
db.activity_events.createIndex({ project_id: 1, at: -1 })
```

**TTL 인덱스는 두지 않는다(A6=A)** — 수명은 프로젝트가 정한다(파기가 지운다). 이 저장소의
모든 감사 컬렉션이 같다. 부피가 실제로 문제가 되면 project 당 최근 N 건 상한(밀어내기)이
다음 수단이며, 지금 N 일을 고를 근거가 없다.

### 43G.4 실패 방향

**기록 실패는 요청을 실패시키지 않는다(A4=A, 격리)** — `llm_call_audits` 와 같고
`access_grant_uses` 와 반대다. 판정 기준은 *"보안 경계에 하중을 지는가"* 이고, 활동 로그가
없다고 잘못 열리는 문은 없다. **대가는 조용한 구멍**이다(로그가 비어도 아무도 모른다).
**반면 파기 실패는 삼키지 않는다** — 삼키면 지워지지 않은 로그가 남은 채 "파기 성공"이 되고
그것이 D5 부분 삭제다.

---

## 43B. admin_audit_events

### 43B.1 Purpose

Minimal administrator-action tombstones that survive project purge. D8-6 stores
one `requested` event before destructive work and a best-effort `succeeded` or
`failed` outcome event with the same `operation_id`.

This is the explicit exception to project-wide deletion. It stores no project
name, owner, manuscript, memory, prompt, or index content. `target_project_id`
is an audit target, not project ownership; using `project_id` here would cause
the purge reconciler to treat the audit as an orphaned project child and delete it.

> **Exception pointer (Slice 8.2c, owner 2026-08-05).** "Stores no project name"
> is still true *of this collection*, but it is no longer true of the purge as a
> whole: a purge now snapshots the project **name** into
> [§43F `project_name_history`](#43f-project_name_history) before it destroys
> anything, so that a usage-ledger row can be read by a human instead of
> answering with a bare id. The name deliberately lives in its own collection —
> putting it here would mix product data into an administrator-action audit and
> tie its retention to this collection's lifetime.



### 43B.2 Document Example

```json
{
  "_id": "audit_event_001",
  "operation_id": "purge_operation_001",
  "admin_user_id": "user_admin_001",
  "action": "project_purge",
  "target_type": "project",
  "target_project_id": "project_001",
  "reason": "고객 삭제 요청",
  "outcome": "requested",
  "at": "2026-08-02T12:00:00Z",
  "error_kind": null
}
```

`outcome` is one of `requested`, `succeeded`, or `failed`. Failure rows expose a
stable `error_kind`, not an internal exception body. The collection has no TTL;
a future legal/operational retention policy is a separate decision.

### 43B.3 Indexes

```javascript
db.admin_audit_events.createIndex(
  { action: 1, at: -1 },
  { name: "admin_audit_events_by_action_at" }
)
db.admin_audit_events.createIndex(
  { operation_id: 1, at: 1 },
  { name: "admin_audit_events_by_operation_at" }
)
```

---

## 43C. request_quota_policies

### 43C.1 Purpose

Per-member request quota policy (Phase 8 Slice 8.1). Stores **only** the limits and
the applied state — never usage counts. Usage is a separate ledger (Slice 8.2) and
the observability collection `llm_call_audits` is not a billing source.

A member without a document uses the code default, so this collection holds only
deliberate exceptions. That is what keeps a default change from leaving stale
copies behind on every member row.

The two usage windows are **derived, never stored**: the daily window turns over at
KST midnight and the weekly window runs in 7-day cycles anchored to the member's
signup date (also at KST midnight). There is no reset job — a reset is a key
changing, not a task running.

`pending` carries a policy change that is not in force yet. A change that favours
the member (raising a limit, lifting a suspension) is applied immediately; an
unfavourable one waits until the member's current 7-day cycle ends. Readers resolve
this with a pure function, so nothing needs to run at the boundary.

### 43C.2 Document Example

```json
{
  "_id": "user_001",
  "limits": {
    "daily_limit": 20,
    "weekly_limit": 100,
    "status": "active"
  },
  "pending": {
    "limits": {
      "daily_limit": 5,
      "weekly_limit": 30,
      "status": "active"
    },
    "effective_at": "2026-08-10T15:00:00Z"
  },
  "updated_at": "2026-08-03T05:00:00Z"
}
```

`_id` is the `users._id` of the member, so the one-row-per-member rule is enforced
by the database itself. `daily_limit`/`weekly_limit` are `null` for "no ceiling on
that window"; `0` means "zero requests allowed" and is a different state from
`status: "suspended"`. `status` is one of `active` or `suspended`. `pending` is
`null` when no deferred change is outstanding, and a new change replaces any
outstanding one rather than queueing behind it.

Dates are stored as UTC BSON dates. Readers must re-attach UTC on the way out
(pymongo returns naive datetimes), otherwise the `effective_at` comparison raises
`TypeError` against an aware `datetime.now(UTC)` — a failure the in-memory fake
cannot reproduce.

### 43C.3 Indexes

None. The only query axis is the member, and `_id` already is the member id.
A second axis (for example "list every suspended member") would add one then.

---

## 43D. request_usage_ledger

### 43D.1 Purpose

Member request usage (Phase 8 Slice 8.2). One row per billable action, plus
administrator adjustment rows in the same collection under a different `kind`.
This is the billing source of record; the observability collection
`llm_call_audits` is deliberately not reused for it.

Two row kinds share the collection but **do not share their field sets**:

- `kind: "usage"` — carries `action` and `dedupe_key`, never `delta`/`reason`.
- `kind: "adjustment"` — carries `delta` (signed), `reason` and `admin_user_id`,
  never `action`/`dedupe_key`. `delta` is added to usage: refunding twenty
  requests is `-20`.

Usage for a window is `count(usage rows) + sum(adjustment deltas)`. It may go
below zero when an administrator refunds more than was used; that is a real
state (a bonus beyond the limit), not an error to clamp away.

The project axis is `target_project_id`, **never `project_id`**. The purge
reconciler discovers collections carrying a `project_id` field and deletes rows
whose project no longer exists — under that name, permanently deleting a project
would erase its billing history, which the owner decision explicitly rejects
("usage records survive project deletion"). The same reasoning as
`admin_audit_events` in §43B.

Window keys are computed by `quota/policy.py` (daily = KST calendar date, weekly
= the start date of the member's 7-day cycle anchored to their signup date) and
stored on the row. The ledger never recomputes them.

There is no TTL. A retention policy is a later, separate decision.

### 43D.2 Document Example

```json
{
  "_id": "usage_entry_001",
  "kind": "usage",
  "user_id": "user_001",
  "target_project_id": "project_001",
  "action": "writing_generate",
  "dedupe_key": "b4f1c6e2-0a7d-4f52-9a1e-6b2c8d3e5f70",
  "daily_key": "2026-08-03",
  "weekly_key": "2026-07-06",
  "at": "2026-08-03T05:00:00Z"
}
```

```json
{
  "_id": "adjustment_entry_001",
  "kind": "adjustment",
  "user_id": "user_001",
  "target_project_id": "project_001",
  "delta": -20,
  "reason": "생성 실패 보상",
  "admin_user_id": "user_admin_001",
  "daily_key": "2026-08-03",
  "weekly_key": "2026-07-06",
  "at": "2026-08-03T06:10:00Z"
}
```

Dates are stored as UTC BSON dates and readers re-attach UTC on the way out
(pymongo returns naive datetimes).

### 43D.3 Indexes

```javascript
db.request_usage_ledger.createIndex(
  { user_id: 1, action: 1, dedupe_key: 1 },
  {
    name: "request_usage_ledger_dedupe_unique",
    unique: true,
    partialFilterExpression: { kind: "usage" }
  }
)
db.request_usage_ledger.createIndex(
  { user_id: 1, daily_key: 1 },
  { name: "request_usage_ledger_by_user_day" }
)
db.request_usage_ledger.createIndex(
  { user_id: 1, weekly_key: 1 },
  { name: "request_usage_ledger_by_user_week" }
)
```

`action` belongs in the unique key: the web client mints one request id per
"continue writing" flow and sends it with `writing_generate`, `writing_gate`,
`writing_revise_and_gate` and `writing_accept`. Without `action`, those four
billable actions would collapse into one row.

The unique index **must be partial**. Adjustment rows have no `action` or
`dedupe_key`, Mongo indexes missing fields as `null`, and a non-partial unique
index would therefore reject the second adjustment row.

---

## 43E. request_locks

### 43E.1 Purpose

Server-side lock against accidentally duplicated requests (Phase 8 Slice 8.2b).
The ledger's dedupe index in §43D only bites when the client key repeats, and
the web client mints a fresh uuid per click — a second click therefore passes it.
This collection is what actually stops it.

The lock is a **control, not a fact**. Losing a document costs nothing (billing
history lives in §43D), which is why TTL cleanup is safe here and a retention
policy is not a discussion.

One document per `(user_id, action, target_project_id)`; that triple **is** the
`_id`, so no additional index exists. The axis keeps the product's normal chain
(`writing_generate` → `writing_gate` → `writing_revise_and_gate` →
`writing_accept`) unblocked, and keeps work in two projects independent.

The lock covers **two segments**, split by one field:

- `released_at: null` — the request is still running. Synchronous generation
  takes about 23 seconds (91 for `long`), so this is where accidental
  double-clicks actually happen; a fixed five-second window would miss them.
- `released_at` set — the request finished, and the lock stays until
  `claimed_at` + the minimum window (5 s, product policy). A request that took
  longer than that window is unlocked as soon as it finishes.

`expires_at` is the **only axis of judgment**: a lock is held while
`expires_at > now`. The TTL index is **cleanup only**. Mongo's TTL monitor runs
roughly every 60 seconds, so judging by document existence would turn the
five-second window into a minute-long one — and no test would show it, because
fakes have no TTL cycle.

`holder` is a fencing token. A confirmed ("yes, give me a second draft") request
force-claims the lock and becomes its new owner; the earlier request then
finishes and calls release. Without the ownership check, that release would free
the **new** owner's lock and leave the second generation unprotected. Release
therefore only acts when `holder` matches.

There is **no `project_id` field** — the project axis lives inside `_id`. The
purge reconciler discovers collections carrying a `project_id` field, and there
is no reason to put locks in its path (§43D has the same reasoning, for a
weightier cause).

Known limit: if the lease expires while the original request is still running,
a duplicate can slip through. The lease is set well above the longest
synchronous path (gateway timeout 120 s) as the defence. This is a best-effort
control, not a guarantee.

**Two key spaces live here (Phase 8 Slice 8.3, Q3-a=A).** Besides the request
locks above, the collection also holds the **member admission mutex** under
`admission:{user_id}`. Enforcement counts a member's in-flight requests and
claims their lock inside that mutex, which is what makes going over the limit
structurally impossible rather than merely unlikely (Mongo transactions cannot
do this: snapshot isolation does not serialise a `count` predicate).

The two spaces are deliberately disjoint, and both directions matter:

- The prefix scan that counts in-flight requests anchors on `^{user_id}:`, so a
  mutex document — which starts with `admission:` — is never counted. Sharing a
  prefix would cost the member a slot for as long as they held the mutex.
- The mutex's lease is **~5 seconds**, not the 180 above. Its critical section is
  two Mongo round-trips, so 5 s is ample for crash recovery, and a longer lease
  would block that member for that long after a crash. It is released
  immediately (no cooldown) — it is a critical section, not a duplicate guard.
- **A provider call must never happen inside it.** The whole point is that the
  serialised segment is milliseconds while the model call is 23–91 seconds.

### 43E.2 Document Example

```json
{
  "_id": "user_001:writing_generate:project_001",
  "holder": "0f6a1c4e8b2d4f7a9c3e5d1b7f0a2c48",
  "claimed_at": "2026-08-03T05:00:00Z",
  "expires_at": "2026-08-03T05:03:00Z",
  "released_at": null
}
```

After the request completes at 05:00:01 the same document reads:

```json
{
  "_id": "user_001:writing_generate:project_001",
  "holder": "0f6a1c4e8b2d4f7a9c3e5d1b7f0a2c48",
  "claimed_at": "2026-08-03T05:00:00Z",
  "expires_at": "2026-08-03T05:00:05Z",
  "released_at": "2026-08-03T05:00:01Z"
}
```

Dates are stored as UTC BSON dates and readers re-attach UTC on the way out
(pymongo returns naive datetimes).

### 43E.3 Indexes

```javascript
db.request_locks.createIndex(
  { expires_at: 1 },
  { name: "request_locks_ttl", expireAfterSeconds: 0 }
)
```

That is the only index. The claim is one operation —

```javascript
db.request_locks.findOneAndUpdate(
  { _id: key, expires_at: { $lte: now } },
  { $set: { holder, claimed_at: now, expires_at: now + lease, released_at: null } },
  { upsert: true, returnDocument: "after" }
)
```

— and a live lock makes the upsert collide on `_id`. Read-then-write is not an
option: two simultaneous requests would both read "absent".

**The collision is a signal, not a verdict.** Between the collision and the
follow-up read, the original request may release (moving `expires_at` into the
past) or the TTL monitor may remove the document. Trusting that state as-is
produces either a false block on an already-expired lock, or — worse — a
"success" that was never stored, which lets the next request through as well.
The adapter therefore re-checks that the blocking lock is live and otherwise
claims again, a bounded number of times; exhausting them fails closed. A granted
claim always means the collection holds that holder.

---

## 43F. project_name_history

### 43F.1 Purpose

The one piece of product data a purge deliberately leaves behind: the **name** a
project was last known by. Slice 8.2c (owner 2026-08-05) added it because
`request_usage_ledger` rows key on `target_project_id` alone, so a purged
project could otherwise only be answered as an id.

This revises the D8-6 expectation recorded in §43B — deletion is still total for
manuscript, memory, prompts and index content; the name is the single named
exception, and the purge UI says so.

**`_id` is the project id and there is no `project_id` field.** That is not a
style choice: `scripts/purge_reconciler.py` discovers sweep targets by looking
for documents carrying `project_id`, so a document with that field would make
this collection an orphan-sweep target and the reconciler would delete exactly
what the slice exists to keep. Same root cause as §43B's `target_project_id`.

Scope is one row per project — the **latest** name, not a rename history, and
not draft titles (N2=A). The write happens **only at purge time** (N3=A): while a
project is alive, `projects` is the single source of truth for its name.

### 43F.2 Document Example

```json
{
  "_id": "project_001",
  "name": "첫 장편",
  "purged_at": "2026-08-05T12:00:00Z"
}
```

Exactly three keys. The write is fail-closed and ordered **before** destruction:
if it fails, the purge does not begin and the request answers 503.

### 43F.3 Indexes

None beyond the primary key; lookups are by `_id`. **No TTL** — the retention
policy for these names is a separate owner decision, and giving the names their
own collection is what keeps that door open.

### 43F.4 Reading it

No query API yet (N4=A). The consumer is the usage-ledger read path in Slice 8.5,
which joins `target_project_id` to this `_id`; when the join finds nothing, the
contract is to display **"삭제된 프로젝트"**.

---

## 44. job_queue

### 44.1 Purpose

Simple internal job queue for MVP.

Later, this may be replaced with Redis Queue, Celery, Temporal, or another workflow system.

### 44.2 Document Example

```json
{
  "_id": "job_001",
  "project_id": "project_001",
  "user_id": "user_001",
  "job_type": "analysis_job",
  "payload": {
    "analysis_job_id": "analysis_job_001"
  },
  "status": "queued",
  "attempts": 0,
  "max_attempts": 3,
  "run_after": "2026-06-23T00:00:00Z",
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

### 44.3 Indexes

```javascript
db.job_queue.createIndex({ status: 1, run_after: 1 })
db.job_queue.createIndex({ project_id: 1, created_at: -1 })
db.job_queue.createIndex({ job_type: 1, status: 1 })
```

---

# PART G. CROSS-COLLECTION RELATIONSHIPS

---

## 45. Draft Save Relationship

```text
drafts
  └── draft_versions
        └── source_snapshots
              ├── source_blocks
              └── source_refs
```

When a draft is saved:

```text
1. Create draft_version
2. Create source_snapshot
3. Split into source_blocks
4. Generate source_refs where needed
5. Create analysis_job
```

---

## 46. Analysis Relationship

```text
analysis_jobs
  ├── analysis_tasks
  ├── analysis_runs
  ├── analysis_results
  └── analysis_candidates
          ├── entities
          ├── events
          ├── locations
          ├── foreshadowings
          ├── relations
          ├── timeline_facts
          └── character_knowledge
```

Analysis candidates do not automatically become confirmed memory.

They must pass Analysis Gate.

---

## 47. Retrieval Relationship

```text
context_search_requests
  └── search_plans
        └── search_traces
              └── context_packages
```

Agentic Search must:

```text
1. Search ChromaDB and/or Elasticsearch
2. Resolve MongoDB pointers
3. Reload MongoDB SOT
4. Build context_package
5. Run Context Gate
```

---

## 48. Writing Relationship

```text
writing_requests
  ├── context_packages
  ├── writing_candidates
  └── gate_results
```

A writing candidate should not become a saved draft unless accepted by the user or explicit automation policy.

---

## 49. Indexing Relationship

```text
MongoDB collections
  ├── ChromaDB records
  └── Elasticsearch documents

index_sync_outbox records pending sync requests.
index_sync_logs records derived index sync attempts/results.
gate_findings records durable Context Gate reject findings for Phase 6 review.
```

Indexing is one-way.

```text
MongoDB → ChromaDB
MongoDB → Elasticsearch
```

---

# PART H. STATUS VALUES

---

## 50. Memory Status

Used by:

```text
entities
events
locations
organizations
items
concepts
relations
timeline_facts
character_knowledge
style_rules
analysis_candidates
```

Values:

```text
candidate
confirmed
canonical
needs_review
rejected
deprecated
```

---

## 51. Runtime Status

Used by jobs and requests.

Values:

```text
queued
running
completed
failed
cancelled
partial
```

---

## 52. Document Status

Used by user-facing documents.

Values:

```text
active
archived
deleted
deprecated
```

---

## 53. Foreshadowing Status

Values:

```text
unresolved
developing
resolved
abandoned
false_lead
deprecated
```

---

## 54. Open Question Status

Values:

```text
open
partially_answered
answered
abandoned
deprecated
```

---

# PART I. MVP COLLECTION SET

---

## 55. Required MVP Collections

For the first implementation, create these collections first:

```text
projects
project_settings
writing_briefs
drafts
draft_versions
source_snapshots
source_blocks
source_refs
entities
events
locations
foreshadowings
relations
timeline_facts
character_knowledge
analysis_jobs
analysis_runs
analysis_results
analysis_candidates
context_search_requests
search_plans
context_packages
writing_requests
writing_candidates
gate_results
index_sync_outbox
index_sync_logs
search_traces
review_requests
review_results
```

Optional for MVP:

```text
organizations
items
concepts
open_questions
style_profiles
voice_samples
style_rules
user_preferences
system_events
job_queue
```

---

## 56. MVP Extraction Targets

MVP Analysis AI should extract only:

```text
Character
Event
Location
Foreshadowing
Relation
TimelineFact
CharacterKnowledge
```

This gives enough structure for:

```text
- 이어쓰기
- 인물 일관성
- 장소 일관성
- 떡밥 관리
- 시점 지식 제한
- 사건 순서 검증
```

---

## 57. MVP Indexing Targets

ChromaDB:

```text
source_blocks
entities
events
locations
foreshadowings
relations
voice_samples
```

Elasticsearch:

```text
source_blocks
entities
events
locations
foreshadowings
relations
timeline_facts
```

MongoDB remains the only SOT.

---

# PART J. Example Workflows

---

## 58. Workflow: Save Draft

```text
Input:
- project_id
- draft_id
- content
- message
- trigger_analysis = true

Steps:
1. Save draft_versions.
2. Create source_snapshots.
3. Create source_blocks.
4. Generate source_refs.
5. Update drafts.current_version_id.
6. Create analysis_jobs.
7. Push job_queue entry.
```

---

## 59. Workflow: Analysis Complete

```text
Steps:
1. Analysis AI returns analysis_results.
2. Create analysis_candidates.
3. Run Analysis Gate.
4. Confirm safe candidates or mark needs_review.
5. Upsert confirmed memory into target collections.
6. Create index_sync_outbox.
7. Worker updates ChromaDB and Elasticsearch.
8. Append index_sync_logs attempt/result.
```

---

## 60. Workflow: Writing Context Search

```text
Steps:
1. Create context_search_requests.
2. Create search_plans.
3. Execute Elasticsearch and ChromaDB search.
4. Reload all candidate data from MongoDB.
5. Detect stale index records.
6. Build context_packages.
7. Run Context Gate.
8. Return context_package to Writing AI.
```

---

## 61. Workflow: Writing Candidate

```text
Steps:
1. Create writing_requests.
2. Request context from Agentic Search.
3. Writing AI generates writing_candidates.
4. Run Writing Gate.
5. If pass, show to user.
6. If user accepts, save as draft_version.
```

---

# PART K. Implementation Notes

---

## 62. Recommended MongoDB Validation Strategy

MongoDB schema validation should be introduced gradually.

MVP recommendation:

```text
Phase 1:
- Validate required top-level fields only.
- Enforce project_id, status, created_at.

Phase 2:
- Add JSON Schema validation for core collections.
- Validate source_ref structure.
- Validate memory_status enums.

Phase 3:
- Add stricter payload validation per candidate_type.
```

---

## 63. Recommended Transaction Boundaries

Use MongoDB transactions for:

```text
- draft_version + source_snapshot + source_blocks creation
- analysis_candidate acceptance + target collection update
- review_result + candidate state update
```

Avoid long transactions around:

```text
- LLM calls
- ChromaDB writes
- Elasticsearch writes
```

LLM and index writes should be outside DB transactions and tracked via logs.

---

## 64. Stale Index Detection

Every ChromaDB / Elasticsearch record must include:

```json
{
  "mongo_collection": "entities",
  "mongo_id": "char_arin",
  "mongo_version": 4
}
```

When Agentic Search reloads from MongoDB:

```text
if index.mongo_version != mongo.version:
    mark stale
    exclude from context
    create index_sync job
```

---

## 65. Final Summary

The MongoDB model is designed around one principle:

```text
MongoDB owns the project memory.
Everything else is an access path.
```

ChromaDB helps the system find semantically similar memories.

Elasticsearch helps the system find exact or filtered memories.

Agentic Search turns those hits into verified context.

Writing AI and Analysis AI only receive pointer-backed data.

Gate components decide whether candidate outputs can be used.
