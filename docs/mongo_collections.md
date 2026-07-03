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
  "decision": "revise",
  "severity": "high",
  "findings": [
    {
      "type": "pov_violation",
      "severity": "high",
      "message": "아린은 현재 scene_014 시점에서 레온의 배신을 알 수 없음.",
      "violating_text": "아린은 레온의 배신을 떠올렸다.",
      "pointers": [
        {
          "mongo_collection": "timeline_facts",
          "mongo_id": "timeline_fact_023"
        }
      ]
    }
  ],
  "created_at": "2026-06-23T00:00:00Z"
}
```

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

## 43. system_events

### 43.1 Purpose

General event log for debugging and audit.

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
