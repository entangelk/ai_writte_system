# 개인 글쓰기 AI + Narrative Memory + Agentic Search 설계문서 초안

> 문서 지위: 초기 아이디에이션 원본. 실제 개발 준비용 문서는 [`plans/README.md`](plans/README.md)에서 시작한다.
> 원문의 아이디어를 보존하기 위해 이 문서는 축약하거나 삭제하지 않는다.

## 0. 문서 목적

이 문서는 기존 `TF_AI_harness`의 검증형 RAG 구조와 `gemma4_12b`의 로컬 LLM gateway 구조를 응용하여, 개인 글쓰기 도우미 시스템을 설계하기 위한 아이디에이션 문서이다.

목표는 단순한 “AI 글쓰기 챗봇”이 아니다. 목표는 다음과 같다.

```text
사용자가 글을 쓴다
→ 글은 MongoDB에 정본으로 저장된다
→ 분석 AI가 글에서 인물, 사건, 장소, 떡밥, 관계, 설정, 시점 정보를 추출한다
→ 추출 결과는 MongoDB에 구조화 기억으로 저장된다
→ ChromaDB와 Elasticsearch에는 검색용 인덱스만 저장된다
→ 다음 글쓰기 AI는 직접 DB를 뒤지는 대신 Agentic Search 시스템에 필요한 컨텍스트를 요청한다
→ Agentic Search는 MongoDB SOT, ChromaDB, Elasticsearch를 조합해 근거와 기억을 패키징한다
→ 글쓰기 AI는 그 컨텍스트를 기반으로 초안, 수정안, 이어쓰기, 비평을 생성한다
→ 생성된 글은 다시 저장되고 분석되어 시스템 기억이 갱신된다
```

이 시스템의 본질은 다음과 같다.

```text
Writing AI = 생성기
Analysis AI = 창작 기억 컴파일러
Agentic Search = 기억 검색 및 컨텍스트 공급자
MongoDB = Source of Truth
ChromaDB = semantic vector cache
Elasticsearch = keyword / metadata / lexical search index
Gate = 생성 결과와 분석 결과의 품질 통제 장치
```

---

## 1. 핵심 제품 컨셉

### 1.1 한 문장 정의

이 시스템은 사용자의 글, 설정, 자료, 세계관, 과거 초안, 문체, 분석 결과를 장기 기억으로 축적하고, 글쓰기 시점마다 필요한 기억만 검색해 제공하는 개인 글쓰기 운영체제이다.

### 1.2 사용자가 체감하는 기능

사용자는 다음과 같은 방식으로 시스템을 사용한다.

```text
- 새 글을 쓴다
- 챗봇에게 “이어서 써줘”라고 말한다
- 챗봇에게 “이 장면에서 아직 회수 안 된 떡밥을 하나 살려줘”라고 말한다
- 챗봇에게 “아린이 현재 알고 있는 사실만 기준으로 대사를 써줘”라고 말한다
- 챗봇에게 “이전 설정과 모순되는 부분 찾아줘”라고 말한다
- 챗봇에게 “내 예전 문체처럼 고쳐줘”라고 말한다
- 챗봇에게 “3장 이후 등장한 인물 관계만 정리해줘”라고 말한다
```

겉으로는 글쓰기 에디터와 챗봇이 붙어 있는 형태다.

안쪽에서는 다음 레이어가 작동한다.

```text
Editor
Chat Interface
Writing AI
Analysis AI
Agentic Search
MongoDB SOT
ChromaDB Vector Cache
Elasticsearch Lexical Index
Gate / Verification Layer
```

---

## 2. 핵심 설계 원칙

### 2.1 MongoDB가 SOT이다

이 시스템에서 MongoDB는 단순한 메타데이터 저장소가 아니라 Source of Truth이다.

MongoDB에는 다음 데이터가 저장된다.

```text
- 원문 draft
- 저장된 글의 snapshot
- 문단, 장면, 섹션 단위 block
- block/span 위치 정보
- source_ref
- draft version
- project metadata
- 분석 AI가 추출한 구조화 데이터
- 인물, 사건, 장소, 물건, 조직, 설정, 떡밥, 관계, 타임라인
- 사용자가 승인한 canon
- candidate / confirmed / rejected / deprecated 상태
- 분석 실행 기록
- Gate 결과
- 검색 trace
```

중요한 원칙은 다음이다.

```text
원문 snapshot = primary SOT
사용자 승인 설정 = canonical SOT
분석 AI 추출 결과 = derived SOT
ChromaDB / Elasticsearch = retrieval index
```

즉 ChromaDB나 Elasticsearch에서 검색된 결과는 “진실”이 아니라 “MongoDB에서 무엇을 다시 읽어야 하는지 알려주는 후보”이다.

---

### 2.2 ChromaDB는 semantic vector cache이다

ChromaDB는 의미 검색을 위한 파생 인덱스다.

ChromaDB에는 다음이 들어간다.

```text
- 원문 chunk embedding
- 장면 요약 embedding
- 인물 profile summary embedding
- 사건 summary embedding
- 장소 summary embedding
- 떡밥 summary embedding
- 관계 summary embedding
- 문체 sample embedding
- 메모리 요약 embedding
```

ChromaDB record에는 실제 정본 데이터가 아니라 포인터와 검색용 텍스트가 들어간다.

예시:

```json
{
  "vector_id": "vec_character_arin_profile_v4",
  "text": "아린은 북부 출신의 신중한 검사이며 레온과 과거 동료였으나 현재 관계가 틀어져 있다.",
  "metadata": {
    "project_id": "novel_001",
    "kind": "character_profile",
    "mongo_collection": "entities",
    "mongo_id": "char_arin",
    "version": 4,
    "source_refs": ["src_ch01_s02_020_090", "src_ch03_s02_120_188"]
  }
}
```

ChromaDB가 반환하는 것은 다음이다.

```text
- vector_id
- similarity score
- metadata
- mongo pointer
- source_ref pointer
```

ChromaDB가 반환한 text를 그대로 LLM 근거로 넣지 않는다.
반드시 MongoDB에서 정본을 다시 로드한다.

---

### 2.3 Elasticsearch는 lexical / metadata search layer이다

Elasticsearch는 ChromaDB와 역할이 다르다.

ChromaDB가 의미적으로 비슷한 것을 찾는다면, Elasticsearch는 다음에 강하다.

```text
- 정확한 이름 검색
- 별칭 검색
- 고유명사 검색
- 대사 검색
- 특정 표현 검색
- nori 기반 한국어 형태소 검색
- BM25 lexical ranking
- project_id / chapter / scene / entity_type / status 필터
- unresolved foreshadowing 검색
- confirmed canon 검색
- version range 검색
```

예를 들어 사용자가 “검은 태양 문양 나온 장면 찾아줘”라고 말하면 Elasticsearch가 강하다.

반면 사용자가 “그때 불길한 분위기랑 비슷한 장면으로 써줘”라고 말하면 ChromaDB가 강하다.

따라서 Agentic Search는 기본적으로 hybrid search를 수행한다.

```text
Elasticsearch = 정확한 검색
ChromaDB = 의미적 검색
MongoDB = 최종 정본 재로드
```

---

### 2.4 Writing AI와 Analysis AI는 직접 데이터를 들고 있지 않는다

글쓰기 AI와 분석 AI는 거대한 컨텍스트를 직접 관리하지 않는다.
이 둘은 MongoDB, ChromaDB, Elasticsearch에 직접 접근하지 않는다.

대신 다음 형태로 작동한다.

```text
Writing AI:
- 현재 요청
- 현재 editor state pointer
- writing brief pointer
- 필요한 context request
- Agentic Search가 만든 Context Package
- 생성 결과 candidate

Analysis AI:
- 저장된 draft snapshot pointer
- 분석 task pointer
- Agentic Search 또는 Snapshot Loader가 제공한 분석 대상 text
- 추출 결과 candidate
```

즉 AI는 데이터를 “소유”하지 않는다.
AI는 필요한 데이터를 Agentic Search 또는 Loader에게 요청한다.

이 구조의 장점은 다음이다.

```text
- LLM context window 오염 방지
- DB 접근 책임 분리
- 검색 로직 교체 가능
- 추론과 데이터 계층 분리
- trace 가능성 확보
- hallucination 감소
- Gate에서 검증 가능
```

---

### 2.5 모든 AI 출력은 candidate이다

글쓰기 AI가 생성한 문장은 `draft_candidate`이다.

분석 AI가 추출한 인물, 사건, 떡밥도 `analysis_candidate`이다.

Agentic Search가 선택한 컨텍스트도 `context_candidate`이다.

최종 저장 또는 사용자 표시 전에는 Gate가 판단한다.

```text
Writing Gate:
- 요청 목적과 맞는가?
- canon과 충돌하지 않는가?
- 현재 인물이 알 수 없는 정보를 말하지 않는가?
- 톤과 문체가 맞는가?
- 금지 표현을 쓰지 않았는가?

Analysis Gate:
- 추출 결과가 원문 span에 anchored 되었는가?
- 기존 entity와 병합 가능한가?
- confidence가 충분한가?
- 새 canon으로 승격할 수 있는가?
- 사용자 review가 필요한가?

Retrieval Gate:
- 검색 결과가 요청과 관련 있는가?
- SOT 재로드가 성공했는가?
- source_ref/hash/version이 일치하는가?
- context budget에 맞는가?
```

---

## 3. 전체 시스템 아키텍처

### 3.1 상위 구성도

```text
┌─────────────────────────────────────────────────────────┐
│                      User Interface                     │
│                                                         │
│  ┌───────────────┐      ┌────────────────────────────┐  │
│  │ Writing Editor│      │ Chat / Assistant Panel      │  │
│  └───────┬───────┘      └─────────────┬──────────────┘  │
└──────────┼────────────────────────────┼─────────────────┘
           │                            │
           ▼                            ▼
┌─────────────────────────────────────────────────────────┐
│                  Application API Layer                  │
│                                                         │
│  Project API / Draft API / Chat API / Search API         │
│  Save API / Analysis API / Export API / Review API       │
└──────────┬────────────────────────────┬─────────────────┘
           │                            │
           ▼                            ▼
┌───────────────────────┐    ┌────────────────────────────┐
│      Writing Agent     │    │      Analysis Agent         │
│                       │    │                            │
│ - outline             │    │ - entity extraction         │
│ - draft               │    │ - event extraction          │
│ - revise              │    │ - foreshadowing extraction  │
│ - continue            │    │ - relation extraction       │
│ - critique            │    │ - continuity extraction     │
└──────────┬────────────┘    └─────────────┬──────────────┘
           │                               │
           ▼                               ▼
┌─────────────────────────────────────────────────────────┐
│                 Agentic Search System                   │
│                                                         │
│ Query Planner                                           │
│ Retrieval Orchestrator                                  │
│ Hybrid Search                                           │
│ SOT Resolver                                            │
│ Context Builder                                         │
│ Context Gate                                            │
└──────────┬────────────────────┬─────────────────────────┘
           │                    │
           ▼                    ▼
┌────────────────────┐   ┌────────────────────┐
│ Elasticsearch       │   │ ChromaDB            │
│ keyword / BM25      │   │ semantic vector     │
│ metadata filter     │   │ similarity search   │
└──────────┬─────────┘   └──────────┬─────────┘
           │                        │
           └──────────┬─────────────┘
                      ▼
┌─────────────────────────────────────────────────────────┐
│                      MongoDB SOT                        │
│                                                         │
│ projects / drafts / snapshots / blocks / entities        │
│ events / locations / foreshadowings / relations          │
│ timeline / analysis_runs / source_refs / gates           │
└─────────────────────────────────────────────────────────┘
```

---

## 4. 주요 런타임 흐름

### 4.1 글쓰기 요청 흐름

예시 요청:

```text
“아린이 노스워치에 도착하는 장면을 이어서 써줘.
전에 나온 단검 떡밥을 살짝 건드리고,
아직 레온의 배신은 모르는 상태로 써줘.”
```

흐름:

```text
1. 사용자가 Chat Panel에 요청한다.
2. Application API가 project_id, current_draft_id, cursor position, selected text를 수집한다.
3. Writing Intake가 요청을 WritingBriefPatch로 변환한다.
4. Writing Agent는 직접 검색하지 않고 Agentic Search에 context request를 보낸다.
5. Agentic Search Query Planner가 필요한 정보 범주를 분해한다.
   - current scene context
   - character: 아린
   - location: 노스워치
   - foreshadowing: 단검
   - timeline constraint
   - POV knowledge constraint
   - voice profile
6. Retrieval Orchestrator가 Elasticsearch + ChromaDB hybrid search를 실행한다.
7. 검색 결과의 mongo pointer를 사용해 MongoDB SOT에서 정본을 재로드한다.
8. SOT Resolver가 source_ref, version, status, canon 여부를 확인한다.
9. Context Builder가 WritingContextPackage를 만든다.
10. Context Gate가 context package 품질을 검사한다.
11. Writing Agent가 ContextPackage를 받아 draft_candidate를 생성한다.
12. Writing Gate가 canon, timeline, POV, style 충돌을 검사한다.
13. 통과하면 editor에 제안한다.
14. 사용자가 accept하면 draft version으로 저장된다.
15. 저장 이벤트가 Analysis Pipeline을 트리거한다.
```

---

### 4.2 저장 후 분석 흐름

```text
1. 사용자가 글을 저장한다.
2. Draft Save API가 MongoDB에 draft_version과 source_snapshot을 저장한다.
3. Snapshot Splitter가 글을 chapter / scene / paragraph / span 단위로 나눈다.
4. Analysis Job이 생성된다.
5. Analysis Agent는 snapshot_id만 받는다.
6. Snapshot Loader가 MongoDB에서 분석 대상 text와 span map을 로드한다.
7. Analysis Agent가 구조화 데이터를 candidate로 추출한다.
8. Analysis Gate가 다음을 검사한다.
   - JSON schema valid
   - source_ref 존재
   - span boundary valid
   - quote match
   - confidence threshold
   - 기존 entity와의 충돌
9. Entity Resolver가 기존 MongoDB entity와 병합 또는 새 entity 생성을 결정한다.
10. MongoDB에 candidate / confirmed / needs_review 상태로 저장한다.
11. Indexer가 변경된 문서만 ChromaDB와 Elasticsearch에 반영한다.
12. Index Sync Log를 남긴다.
```

---

### 4.3 다음 글쓰기 시 기억 제공 흐름

```text
1. Writing Agent가 필요한 정보 목록을 만든다.
2. Agentic Search가 검색 계획을 세운다.
3. Elasticsearch로 정확한 키워드와 entity name을 찾는다.
4. ChromaDB로 의미적으로 관련된 장면과 기억을 찾는다.
5. MongoDB에서 정본 문서를 재로드한다.
6. candidate 상태의 기억은 낮은 우선순위 또는 주석 처리한다.
7. confirmed/canonical 상태의 기억은 강한 constraint로 제공한다.
8. ContextPackage를 macro context와 micro evidence로 나눈다.
9. Writing Agent는 이 패키지만 보고 글을 생성한다.
```

---

## 5. Agentic Search System 설계

### 5.1 존재 이유

Agentic Search는 단순 검색 API가 아니다.

이 시스템에서 Agentic Search는 Writing AI와 Analysis AI 사이에 있는 지식 중개자다.

역할은 다음과 같다.

```text
- 사용자의 요청을 검색 가능한 계획으로 분해한다
- Elasticsearch, ChromaDB, MongoDB를 조합한다
- 검색 결과를 검증한다
- MongoDB SOT에서 정본을 재로드한다
- context budget에 맞춰 압축한다
- Writing AI / Analysis AI가 사용할 수 있는 안전한 패키지를 만든다
- 어떤 데이터를 왜 넣었는지 trace를 남긴다
```

### 5.2 Agentic Search 내부 모듈

```text
AgenticSearchService
├── SearchIntentClassifier
├── QueryPlanner
├── SearchToolRouter
├── ElasticsearchRetriever
├── ChromaRetriever
├── MongoSOTResolver
├── EntityGraphWalker
├── ContextRanker
├── ContextCompressor
├── ContextGate
├── TraceLogger
└── ContextPackageBuilder
```

---

### 5.3 SearchIntentClassifier

사용자 요청 또는 AI 내부 요청을 검색 의도로 분류한다.

예시:

```json
{
  "intent": "writing_context",
  "sub_intents": [
    "character_state",
    "location_context",
    "open_foreshadowing",
    "timeline_constraint",
    "voice_reference"
  ],
  "risk_level": "medium",
  "requires_sot_reload": true
}
```

검색 의도 종류:

```text
writing_context
analysis_context
continuity_check
canon_lookup
entity_lookup
scene_lookup
voice_lookup
style_lookup
foreshadowing_lookup
timeline_lookup
relationship_lookup
source_evidence_lookup
```

---

### 5.4 QueryPlanner

QueryPlanner는 “무엇을 검색할지”를 결정한다.

입력:

```json
{
  "project_id": "novel_001",
  "request": "아린이 노스워치에 도착하는 장면을 써줘",
  "current_draft_pointer": {
    "draft_id": "draft_003",
    "scene_id": "scene_014"
  },
  "writing_brief_id": "brief_001"
}
```

출력:

```json
{
  "plan_id": "search_plan_001",
  "steps": [
    {
      "step": 1,
      "target": "character",
      "query": "아린",
      "tools": ["elasticsearch", "mongo"],
      "filters": {
        "project_id": "novel_001",
        "entity_type": "character",
        "status": ["confirmed", "canonical"]
      }
    },
    {
      "step": 2,
      "target": "location",
      "query": "노스워치",
      "tools": ["elasticsearch", "chroma", "mongo"],
      "filters": {
        "project_id": "novel_001",
        "entity_type": "location"
      }
    },
    {
      "step": 3,
      "target": "foreshadowing",
      "query": "단검 문양 검은 태양",
      "tools": ["elasticsearch", "chroma", "mongo"],
      "filters": {
        "status": ["unresolved", "active"]
      }
    },
    {
      "step": 4,
      "target": "timeline",
      "query": "current scene prior knowledge",
      "tools": ["mongo"],
      "filters": {
        "scene_lte": "scene_014"
      }
    }
  ]
}
```

---

### 5.5 SearchToolRouter

각 검색 단계마다 어떤 저장소를 쓸지 결정한다.

기본 규칙:

```text
정확한 이름 / 별칭 / 고유명사
→ Elasticsearch 우선

분위기 / 유사 장면 / 의미적 연결
→ ChromaDB 우선

canon / status / version / relation / timeline
→ MongoDB 우선

검색 결과의 최종 본문
→ 항상 MongoDB SOT 재로드
```

라우팅 예시:

```text
“아린”
→ ES exact alias search
→ Mongo entity lookup

“불길한 분위기의 장면”
→ Chroma scene embedding search
→ Mongo scene snapshot reload

“아직 회수 안 된 떡밥”
→ Mongo foreshadowings status filter
→ ES keyword boost
→ Chroma semantic rerank

“레온과 아린의 관계”
→ Mongo relations query
→ Chroma relationship summaries
→ Mongo reload
```

---

### 5.6 MongoSOTResolver

MongoSOTResolver는 검색 결과에서 pointer를 받아 정본 데이터를 재로드한다.

입력:

```json
{
  "candidates": [
    {
      "source": "chroma",
      "mongo_collection": "entities",
      "mongo_id": "char_arin",
      "version": 4
    },
    {
      "source": "elasticsearch",
      "mongo_collection": "source_blocks",
      "mongo_id": "block_ch03_s02_012"
    }
  ]
}
```

처리:

```text
1. mongo_collection과 mongo_id 유효성 확인
2. project_id 권한 확인
3. version 확인
4. status 확인
5. source_ref 확인
6. hash 확인
7. 원문 span 또는 구조화 문서 로드
8. stale index 여부 검사
```

출력:

```json
{
  "resolved_items": [
    {
      "kind": "character",
      "mongo_id": "char_arin",
      "status": "confirmed",
      "version": 4,
      "payload": {},
      "source_refs": []
    }
  ],
  "stale_candidates": [],
  "missing_candidates": []
}
```

---

### 5.7 ContextPackageBuilder

ContextPackageBuilder는 검색 결과를 AI에게 넣을 수 있는 형태로 바꾼다.

핵심은 모든 데이터를 그냥 넣지 않는 것이다.

Context는 다음 두 층으로 나눈다.

```text
Macro Context
- 현재 프로젝트 설명
- 장르
- 문체
- 현재 장면 목표
- 관련 인물 요약
- 관련 장소 요약
- 최근 사건 요약
- 열린 떡밥 목록
- timeline / POV constraints

Micro Evidence
- 실제 원문 span
- 관련 대사
- canon 문장
- 설정 근거
- source_ref
- quote
```

Writing AI에게는 다음처럼 제공된다.

```json
{
  "context_package_id": "ctx_001",
  "project_id": "novel_001",
  "task": "continue_scene",
  "macro_context": {
    "current_scene_summary": "...",
    "characters": [],
    "locations": [],
    "open_foreshadowings": [],
    "timeline_constraints": [],
    "pov_constraints": [],
    "voice_profile": {}
  },
  "micro_evidence": [
    {
      "source_ref": "src_ch02_s01_084_112",
      "quote": "낡은 단검 손잡이에는 검은 태양 문양이 새겨져 있었다.",
      "supports": "foreshadow_black_sun_knife"
    }
  ],
  "do_not_use": [
    "아린은 아직 레온의 배신을 모른다.",
    "검은 태양단의 정체는 아직 공개하지 않는다."
  ],
  "trace": {
    "search_plan_id": "search_plan_001",
    "retrieval_ids": [],
    "resolved_mongo_ids": []
  }
}
```

---

## 6. Writing AI 설계

### 6.1 Writing AI의 역할

Writing AI는 다음을 수행한다.

```text
- outline 생성
- 장면 이어쓰기
- 문단 작성
- 문체 변환
- 초안 수정
- 대사 개선
- 장면 비평
- 설정 반영
- 독자 반응 예측
- 요약
- 제목 제안
```

하지만 Writing AI는 다음을 하지 않는다.

```text
- DB 직접 검색
- MongoDB 직접 조회
- ChromaDB 직접 조회
- Elasticsearch 직접 조회
- canon 여부 자체 판단
- source_ref 위조
- 분석 결과 확정
```

Writing AI는 ContextPackage를 받아 candidate text를 생성한다.

---

### 6.2 WritingRequest

```json
{
  "request_id": "write_req_001",
  "project_id": "novel_001",
  "user_id": "user_001",
  "task_type": "continue_scene",
  "input": {
    "user_instruction": "아린이 노스워치에 도착하는 장면을 이어서 써줘",
    "current_draft_pointer": {
      "draft_id": "draft_003",
      "version": 12,
      "selection": {
        "start": 1200,
        "end": 1800
      }
    }
  },
  "writing_brief_id": "brief_001",
  "context_request": {
    "needs": [
      "current_scene",
      "character_state",
      "location_context",
      "timeline",
      "open_foreshadowing",
      "voice"
    ]
  },
  "generation_options": {
    "length": "1200-1800자",
    "language": "ko",
    "tone": "차분하고 불길함",
    "output_mode": "draft_patch"
  }
}
```

---

### 6.3 WritingOutput

```json
{
  "candidate_id": "draft_candidate_001",
  "request_id": "write_req_001",
  "output_type": "draft_patch",
  "text": "...",
  "used_context_package_id": "ctx_001",
  "self_reported_constraints": [
    "아린은 레온의 배신을 모르는 상태로 작성함",
    "단검 떡밥은 직접 회수하지 않고 암시만 함"
  ],
  "claims": [
    {
      "claim_text": "아린은 노스워치에 처음 도착했다.",
      "claim_type": "narrative_event",
      "requires_canon_check": true
    }
  ],
  "status": "candidate"
}
```

---

### 6.4 Writing Gate

Writing Gate는 생성 결과를 검사한다.

검사 항목:

```text
1. Intent Match
   - 사용자 요청을 따랐는가?
   - 분량, 톤, 형식을 지켰는가?

2. Canon Consistency
   - 기존 설정과 충돌하지 않는가?
   - confirmed/canonical memory와 모순되지 않는가?

3. Timeline Consistency
   - 사건 순서가 맞는가?
   - 현재 장면 이전/이후 정보가 섞이지 않았는가?

4. POV Consistency
   - 해당 인물이 아직 모르는 사실을 말하지 않는가?
   - 서술 시점이 갑자기 깨지지 않는가?

5. Foreshadowing Control
   - unresolved 떡밥을 갑자기 회수하지 않는가?
   - 이미 회수된 떡밥을 다시 미해결처럼 다루지 않는가?

6. Style / Voice Match
   - 사용자의 문체와 맞는가?
   - 금지 표현을 쓰지 않았는가?
   - 지나치게 AI스러운 문장을 만들지 않았는가?

7. Safety / Privacy
   - 개인 메모를 부적절하게 노출하지 않는가?
   - 다른 프로젝트의 데이터를 섞지 않았는가?
```

Gate 결과:

```json
{
  "gate_id": "writing_gate_001",
  "candidate_id": "draft_candidate_001",
  "decision": "pass | revise | retrieve_more | needs_user_review | block",
  "findings": [
    {
      "type": "pov_violation",
      "severity": "high",
      "message": "아린은 scene_014 시점에서 레온의 배신을 알 수 없음",
      "evidence": {
        "mongo_id": "timeline_fact_023",
        "source_ref": "src_ch05_s03_100_144"
      }
    }
  ]
}
```

---

## 7. Analysis AI 설계

### 7.1 Analysis AI의 역할

Analysis AI는 저장된 글을 읽고 구조화 기억을 추출한다.

추출 대상:

```text
- Character
- Event
- Location
- Organization
- Item
- Concept
- Foreshadowing
- OpenQuestion
- Relationship
- TimelineFact
- CharacterKnowledge
- SettingRule
- StyleSignal
```

Analysis AI는 글을 저장할 때마다 자동 실행될 수 있다.

실시간 실행도 가능하지만, 초반 MVP에서는 저장 시점 batch job이 적합하다.

---

### 7.2 AnalysisJob

```json
{
  "analysis_job_id": "analysis_job_001",
  "project_id": "novel_001",
  "snapshot_id": "snap_draft_003_v12",
  "trigger": "draft_saved",
  "tasks": [
    "scene_split",
    "entity_extraction",
    "event_extraction",
    "foreshadowing_extraction",
    "relationship_extraction",
    "timeline_extraction",
    "style_signal_extraction"
  ],
  "status": "queued"
}
```

---

### 7.3 Analysis AI 입력

Analysis AI에게 전체 DB를 주지 않는다.

입력은 다음처럼 제한한다.

```json
{
  "analysis_task_id": "analysis_task_001",
  "task_type": "entity_extraction",
  "project_id": "novel_001",
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
        "end": 120
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
  "output_schema": "CharacterExtractionCandidate[]"
}
```

---

### 7.4 Analysis Output

```json
{
  "analysis_result_id": "analysis_result_001",
  "task_type": "entity_extraction",
  "snapshot_id": "snap_draft_003_v12",
  "candidates": [
    {
      "candidate_type": "character",
      "name": "아린",
      "matched_existing_entity_id": "char_arin",
      "new_facts": [
        {
          "fact": "아린은 노스워치에 도착했다.",
          "fact_type": "location_arrival",
          "source_ref": "src_ch06_s01_020_088",
          "confidence": 0.92
        }
      ],
      "status": "candidate"
    }
  ]
}
```

---

### 7.5 Analysis Gate

Analysis Gate는 분석 결과를 바로 canon으로 승격하지 않는다.

검사 항목:

```text
- JSON schema valid
- source_ref 존재
- source_ref가 현재 snapshot에 속하는가
- span boundary가 유효한가
- quote가 원문과 일치하는가
- 기존 entity와 병합 가능한가
- 새 entity 생성이 필요한가
- confidence가 충분한가
- 기존 confirmed canon과 충돌하는가
- 사용자 review가 필요한가
```

결과 상태:

```text
candidate
confirmed
canonical
needs_review
rejected
deprecated
```

상태 의미:

```text
candidate:
- AI가 추출했지만 아직 신뢰 낮음

confirmed:
- 원문 근거와 충돌 검사를 통과함

canonical:
- 사용자 또는 강한 규칙에 의해 정본 설정으로 승격됨

needs_review:
- 모순 또는 애매한 해석이 있어 사용자 검토 필요

rejected:
- 잘못된 추출로 판정

deprecated:
- 과거에는 유효했지만 이후 설정 변경으로 폐기됨
```

---

## 8. MongoDB 데이터 모델

### 8.1 Collections 개요

```text
projects
writing_briefs
drafts
draft_versions
source_snapshots
source_blocks
source_refs
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
style_profiles
voice_samples
analysis_runs
analysis_candidates
gate_results
search_traces
index_sync_logs
context_packages
```

---

### 8.2 projects

```json
{
  "_id": "project_001",
  "user_id": "user_001",
  "title": "검은 태양의 도시",
  "type": "novel",
  "language": "ko",
  "genre": ["fantasy", "mystery"],
  "status": "active",
  "created_at": "2026-06-23T00:00:00Z",
  "updated_at": "2026-06-23T00:00:00Z"
}
```

---

### 8.3 writing_briefs

```json
{
  "_id": "brief_001",
  "project_id": "project_001",
  "purpose": "장편 판타지 소설 작성",
  "target_reader": "성인 판타지 독자",
  "tone": ["차분함", "불길함", "서늘함"],
  "style_rules": [
    "과도한 감탄사 금지",
    "직접 설명보다 장면으로 보여주기",
    "대사는 짧고 긴장감 있게"
  ],
  "forbidden_patterns": [
    "그는 알 수 없는 감정을 느꼈다",
    "운명처럼"
  ],
  "default_context_policy": {
    "include_voice": true,
    "include_open_foreshadowing": true,
    "include_timeline": true,
    "include_recent_scenes": true
  }
}
```

---

### 8.4 draft_versions

```json
{
  "_id": "draft_v012",
  "project_id": "project_001",
  "draft_id": "draft_003",
  "version": 12,
  "title": "6장 - 노스워치",
  "content": "...",
  "snapshot_id": "snap_draft_003_v12",
  "parent_version": 11,
  "created_by": "user",
  "created_at": "2026-06-23T00:00:00Z",
  "analysis_status": "completed"
}
```

---

### 8.5 source_snapshots

```json
{
  "_id": "snap_draft_003_v12",
  "project_id": "project_001",
  "source_type": "draft_version",
  "source_id": "draft_v012",
  "content_hash": "sha256:...",
  "normalized_text_hash": "sha256:...",
  "version": 12,
  "created_at": "2026-06-23T00:00:00Z",
  "status": "active"
}
```

---

### 8.6 source_blocks

```json
{
  "_id": "block_ch06_s01_p003",
  "project_id": "project_001",
  "snapshot_id": "snap_draft_003_v12",
  "block_type": "paragraph",
  "chapter_id": "chapter_06",
  "scene_id": "scene_014",
  "order": 3,
  "text": "낡은 단검 손잡이에는 검은 태양 문양이 희미하게 떠올라 있었다.",
  "start_offset": 240,
  "end_offset": 306,
  "hash": "sha256:..."
}
```

---

### 8.7 source_refs

```json
{
  "_id": "src_ch06_s01_240_306",
  "project_id": "project_001",
  "snapshot_id": "snap_draft_003_v12",
  "block_id": "block_ch06_s01_p003",
  "start_offset": 240,
  "end_offset": 306,
  "quote": "낡은 단검 손잡이에는 검은 태양 문양이 희미하게 떠올라 있었다.",
  "hash": "sha256:..."
}
```

---

### 8.8 entities

```json
{
  "_id": "char_arin",
  "project_id": "project_001",
  "entity_type": "character",
  "name": "아린",
  "aliases": ["은빛 눈의 검사"],
  "summary": "북부 출신의 신중한 검사. 왕실을 불신하며 레온과 과거 동료였다.",
  "traits": ["신중함", "검술에 능함", "왕실 불신"],
  "status": "confirmed",
  "canon_level": "project",
  "source_refs": ["src_ch01_s02_020_090"],
  "versions": [
    {
      "version": 1,
      "updated_from_analysis_run": "analysis_run_001"
    }
  ],
  "updated_at": "2026-06-23T00:00:00Z"
}
```

---

### 8.9 events

```json
{
  "_id": "event_royal_fire",
  "project_id": "project_001",
  "event_type": "backstory",
  "name": "왕궁 화재",
  "summary": "10년 전 왕궁 별관에서 원인 불명의 화재가 발생했다.",
  "participants": ["char_arin", "char_king"],
  "location_id": "loc_capital_palace",
  "narrative_order": 3,
  "story_time": "10년 전",
  "consequences": [
    "아린의 가족이 실종됨",
    "아린이 왕실을 불신하게 됨"
  ],
  "status": "confirmed",
  "source_refs": ["src_ch02_s04_300_420"]
}
```

---

### 8.10 foreshadowings

```json
{
  "_id": "foreshadow_black_sun_knife",
  "project_id": "project_001",
  "title": "검은 태양 문양의 단검",
  "setup": "낡은 단검 손잡이에 검은 태양 문양이 새겨져 있다.",
  "introduced_at": {
    "chapter_id": "chapter_02",
    "scene_id": "scene_005"
  },
  "status": "unresolved",
  "related_entities": ["item_black_sun_knife", "org_black_sun"],
  "possible_payoff": "검은 태양단과 연결될 가능성",
  "source_refs": ["src_ch02_s01_084_112"],
  "confidence": 0.91,
  "reviewed_by_user": false
}
```

---

### 8.11 relations

```json
{
  "_id": "rel_arin_leon_001",
  "project_id": "project_001",
  "from_entity_id": "char_arin",
  "to_entity_id": "char_leon",
  "relation_type": "former_ally",
  "status_label": "strained",
  "valid_from": "chapter_04",
  "valid_until": null,
  "source_refs": ["src_ch04_s01_080_130"],
  "status": "confirmed"
}
```

---

### 8.12 timeline_facts

```json
{
  "_id": "timeline_fact_023",
  "project_id": "project_001",
  "fact": "아린은 chapter_08 이전에는 레온의 배신을 알지 못한다.",
  "applies_to": ["char_arin", "char_leon"],
  "valid_from_scene": "scene_001",
  "valid_until_scene": "scene_021",
  "constraint_type": "pov_knowledge",
  "status": "canonical",
  "source_refs": ["src_ch05_s03_100_144"]
}
```

---

### 8.13 character_knowledge

```json
{
  "_id": "knowledge_arin_001",
  "project_id": "project_001",
  "character_id": "char_arin",
  "knows_fact": "레온이 북부 전투에 참여했다.",
  "does_not_know": [
    "레온이 왕실과 거래했다."
  ],
  "valid_at_scene": "scene_014",
  "source_refs": ["src_ch04_s02_300_350"],
  "status": "confirmed"
}
```

---

### 8.14 context_packages

```json
{
  "_id": "ctx_001",
  "project_id": "project_001",
  "request_id": "write_req_001",
  "search_plan_id": "search_plan_001",
  "macro_context": {},
  "micro_evidence": [],
  "constraints": [],
  "excluded_items": [],
  "token_estimate": 5400,
  "created_at": "2026-06-23T00:00:00Z"
}
```

---

## 9. ChromaDB 설계

### 9.1 Collection 분리

초기에는 하나의 collection으로 시작할 수 있지만, 장기적으로는 분리하는 편이 좋다.

```text
writing_chunks
narrative_entities
narrative_events
narrative_locations
narrative_foreshadowings
voice_samples
project_memories
```

MVP에서는 다음처럼 시작한다.

```text
collection: project_memory_vectors
```

metadata에 kind를 넣는다.

```json
{
  "kind": "source_block | character | event | location | foreshadowing | relation | voice"
}
```

---

### 9.2 Vector record 원칙

ChromaDB에 들어가는 text는 검색용 representation이다.
정본이 아니다.

```json
{
  "id": "vec_foreshadow_black_sun_knife_v2",
  "document": "검은 태양 문양이 새겨진 단검은 아직 회수되지 않은 떡밥이다. 검은 태양단과 관련 있을 가능성이 있다.",
  "metadata": {
    "project_id": "project_001",
    "kind": "foreshadowing",
    "mongo_collection": "foreshadowings",
    "mongo_id": "foreshadow_black_sun_knife",
    "status": "unresolved",
    "version": 2
  }
}
```

---

## 10. Elasticsearch 설계

### 10.1 Index 구성

```text
project_source_blocks
project_entities
project_events
project_locations
project_foreshadowings
project_relations
project_voice_samples
```

MVP에서는 하나의 index로 시작해도 된다.

```text
writing_memory_search
```

---

### 10.2 Elasticsearch document 예시

```json
{
  "mongo_collection": "foreshadowings",
  "mongo_id": "foreshadow_black_sun_knife",
  "project_id": "project_001",
  "kind": "foreshadowing",
  "title": "검은 태양 문양의 단검",
  "body": "낡은 단검 손잡이에 검은 태양 문양이 새겨져 있다.",
  "aliases": ["검은 태양", "단검", "문양"],
  "status": "unresolved",
  "chapter_id": "chapter_02",
  "scene_id": "scene_005",
  "source_refs": ["src_ch02_s01_084_112"]
}
```

---

### 10.3 ES가 담당할 주요 쿼리

```text
- 이름 정확 검색
- 별칭 검색
- 대사 검색
- 특정 물건/장소 등장 장면 검색
- unresolved status 필터
- chapter/scene 범위 검색
- confirmed/canonical status 검색
- source_ref 검색
- 한국어 형태소 기반 검색
```

---

## 11. Index Sync 설계

### 11.1 기본 원칙

MongoDB가 SOT이므로 인덱스는 언제든 재생성 가능해야 한다.

```text
MongoDB → ChromaDB
MongoDB → Elasticsearch
```

역방향은 없다.

ChromaDB와 Elasticsearch는 MongoDB를 갱신하지 않는다.
단, 검색 trace와 stale index finding은 MongoDB에 기록할 수 있다.

---

### 11.2 Index Sync 이벤트

```text
draft_saved
analysis_completed
entity_confirmed
entity_updated
foreshadowing_resolved
canon_changed
voice_sample_added
draft_deleted
project_archived
```

---

### 11.3 index_sync_logs

```json
{
  "_id": "sync_001",
  "project_id": "project_001",
  "event": "analysis_completed",
  "mongo_collection": "foreshadowings",
  "mongo_id": "foreshadow_black_sun_knife",
  "targets": ["chroma", "elasticsearch"],
  "status": "success",
  "started_at": "2026-06-23T00:00:00Z",
  "finished_at": "2026-06-23T00:00:02Z"
}
```

---

## 12. Gate / Verification Layer

### 12.1 Gate 종류

```text
Context Gate
Writing Gate
Analysis Gate
Index Gate
Continuity Gate
Canon Gate
POV Gate
Voice Gate
```

---

### 12.2 Context Gate

ContextPackage가 AI에게 제공되기 전에 검사한다.

```text
- 모든 item이 project_id와 일치하는가
- stale index 결과는 제거되었는가
- MongoDB SOT reload가 완료되었는가
- source_ref가 유효한가
- candidate 상태의 정보를 canon처럼 넣지 않았는가
- context budget을 넘지 않았는가
- 금지된 private memory가 포함되지 않았는가
```

---

### 12.3 Continuity Gate

생성된 글이 기존 세계관과 모순되는지 검사한다.

검사 예시:

```text
- 죽은 인물이 다시 살아서 등장하지 않는가
- 아직 만나지 않은 인물이 서로를 아는 척하지 않는가
- 장소의 지리 정보가 바뀌지 않았는가
- 이미 회수된 떡밥이 다시 미회수로 등장하지 않는가
- 특정 장면 시점에서 알 수 없는 정보를 인물이 말하지 않는가
```

---

### 12.4 POV Gate

POV Gate는 장편 창작에서 매우 중요하다.

예시 finding:

```json
{
  "type": "pov_violation",
  "severity": "high",
  "message": "아린은 현재 scene_014 시점에서 레온의 배신을 알 수 없음.",
  "violating_text": "아린은 레온의 배신을 떠올렸다.",
  "constraint_ref": {
    "mongo_collection": "timeline_facts",
    "mongo_id": "timeline_fact_023"
  },
  "decision": "revise"
}
```

---

### 12.5 Foreshadowing Gate

떡밥 관리용 Gate이다.

검사 항목:

```text
- unresolved 떡밥을 의도 없이 회수하지 않았는가
- 회수된 떡밥을 다시 unresolved처럼 쓰지 않았는가
- 너무 노골적으로 설명하지 않았는가
- 사용자가 요청한 암시 강도를 지켰는가
```

---

## 13. API 설계 초안

### 13.1 글쓰기 요청

```http
POST /api/projects/{project_id}/write
```

Request:

```json
{
  "task_type": "continue_scene",
  "instruction": "아린이 노스워치에 도착하는 장면을 이어서 써줘",
  "draft_pointer": {
    "draft_id": "draft_003",
    "version": 12,
    "selection": {
      "start": 1200,
      "end": 1800
    }
  },
  "context_policy": {
    "use_agentic_search": true,
    "include_voice": true,
    "include_timeline": true,
    "include_foreshadowing": true
  }
}
```

Response:

```json
{
  "candidate_id": "draft_candidate_001",
  "text": "...",
  "gate_decision": "pass",
  "context_package_id": "ctx_001",
  "trace_id": "trace_001"
}
```

---

### 13.2 저장 요청

```http
POST /api/projects/{project_id}/drafts/{draft_id}/save
```

Request:

```json
{
  "content": "...",
  "message": "노스워치 도착 장면 추가",
  "trigger_analysis": true
}
```

Response:

```json
{
  "draft_version_id": "draft_v012",
  "snapshot_id": "snap_draft_003_v12",
  "analysis_job_id": "analysis_job_001"
}
```

---

### 13.3 Agentic Search 요청

```http
POST /api/projects/{project_id}/search/context
```

Request:

```json
{
  "purpose": "writing_context",
  "query": "아린이 노스워치에 도착하는 장면",
  "needs": [
    "character_state",
    "location_context",
    "open_foreshadowing",
    "timeline",
    "pov"
  ],
  "current_scene_id": "scene_014"
}
```

Response:

```json
{
  "context_package_id": "ctx_001",
  "macro_context": {},
  "micro_evidence": [],
  "constraints": [],
  "trace_id": "search_trace_001"
}
```

---

### 13.4 분석 결과 조회

```http
GET /api/projects/{project_id}/analysis/jobs/{analysis_job_id}
```

Response:

```json
{
  "analysis_job_id": "analysis_job_001",
  "status": "completed",
  "created_entities": [],
  "updated_entities": [],
  "needs_review": []
}
```

---

## 14. 프롬프트 / 에이전트 계약

### 14.1 Writing Agent System Contract

```text
너는 글쓰기 AI이다.
너는 MongoDB, ChromaDB, Elasticsearch에 직접 접근하지 않는다.
너는 제공된 ContextPackage 안의 정보만 사용한다.
ContextPackage의 candidate 정보는 확정된 canon처럼 단정하지 않는다.
do_not_use에 있는 정보는 직접 서술하지 않는다.
현재 시점의 인물이 모르는 사실을 대사나 내면에 넣지 않는다.
사용자 요청과 WritingBrief를 우선한다.
출력은 최종 글이 아니라 draft_candidate이다.
```

---

### 14.2 Analysis Agent System Contract

```text
너는 저장된 글을 분석하는 AI이다.
너는 원문에서 명시되거나 강하게 암시된 정보만 추출한다.
모든 추출 결과는 source_ref 또는 span 근거를 가져야 한다.
추정은 fact로 저장하지 않고 hypothesis/candidate로 표시한다.
기존 entity와 같은 대상일 가능성이 있으면 matched_existing_entity_id를 제안한다.
새 canon을 확정하지 않는다.
출력은 analysis_candidate이다.
```

---

### 14.3 Agentic Search System Contract

```text
너는 검색 계획을 세우고 컨텍스트를 구성하는 에이전트이다.
VectorDB와 Elasticsearch 결과는 후보일 뿐이다.
최종 제공 데이터는 MongoDB SOT에서 재로드해야 한다.
stale index 결과는 제거하거나 낮은 신뢰도로 표시한다.
ContextPackage에는 요청에 필요한 최소한의 정보만 넣는다.
모든 컨텍스트 항목에는 trace 가능한 pointer를 포함한다.
```

---

## 15. MVP 범위 제안

### 15.1 MVP 1: 저장-분석-검색 루프

목표:

```text
사용자가 글을 저장하면 분석 AI가 핵심 요소를 뽑고,
다음 글쓰기 요청에서 Agentic Search가 그 요소를 찾아 제공한다.
```

범위:

```text
- MongoDB draft 저장
- source_snapshot / source_block 생성
- Analysis AI로 5종 추출
  - Character
  - Event
  - Location
  - Foreshadowing
  - Relation
- MongoDB 저장
- ChromaDB indexing
- Elasticsearch indexing
- Agentic Search context API
- Writing AI context 기반 이어쓰기
```

제외:

```text
- 완전한 UI
- 복잡한 graph visualization
- 자동 canon 승격
- 고급 문체 학습
- 실시간 multi-agent loop
```

---

### 15.2 MVP 2: Continuity Gate

목표:

```text
작성 결과가 기존 설정과 충돌하는지 검사한다.
```

추가 기능:

```text
- TimelineFact
- CharacterKnowledge
- POV Gate
- Foreshadowing Gate
- Gate finding UI
- 수정 재생성 loop
```

---

### 15.3 MVP 3: 개인 문체 / Voice RAG

목표:

```text
사용자의 과거 글과 문체 선호를 기반으로 초안을 다듬는다.
```

추가 기능:

```text
- voice_samples
- style_profiles
- forbidden_patterns
- preferred_phrases
- Voice Gate
- AI스러운 문장 감지
```

---

### 15.4 MVP 4: Project Memory Console

목표:

```text
사용자가 세계관/인물/사건/떡밥 DB를 직접 보고 수정한다.
```

추가 기능:

```text
- 인물 카드
- 장소 카드
- 사건 타임라인
- 미회수 떡밥 목록
- 관계 목록
- candidate → confirmed 승인 UI
- rejected / deprecated 관리
```

---

## 16. 핵심 위험과 대응

### 16.1 분석 AI의 과잉 추론

문제:

```text
AI가 원문에 없는 설정을 추측해서 저장할 수 있음
```

대응:

```text
- 모든 분석 결과에 source_ref 필수
- confidence 저장
- candidate 상태로 저장
- canon 승격은 Gate 또는 사용자 승인 필요
```

---

### 16.2 ChromaDB stale index

문제:

```text
MongoDB 정본은 바뀌었는데 ChromaDB index가 오래된 데이터를 반환할 수 있음
```

대응:

```text
- vector metadata에 mongo version 저장
- SOT Resolver에서 version 비교
- stale이면 결과 폐기
- index_sync_logs 기록
```

---

### 16.3 Elasticsearch stale index

대응은 ChromaDB와 동일하다.

```text
- ES document에 mongo version 저장
- MongoDB reload 시 version mismatch 검사
- mismatch면 재색인 job 생성
```

---

### 16.4 Writing AI가 context를 오해함

대응:

```text
- ContextPackage에 confirmed/candidate 구분
- do_not_use 명시
- constraints 명시
- Writing Gate에서 사후 검사
```

---

### 16.5 프로젝트 간 기억 오염

대응:

```text
- 모든 collection에 project_id 필수
- Agentic Search에서 project_id 강제 필터
- Context Gate에서 cross-project item 제거
```

---

## 17. 구현 순서

### Phase 1: Core SOT

```text
1. MongoDB collection 정의
2. draft_versions 저장 구현
3. source_snapshot 생성
4. source_block 분할
5. source_ref 생성
```

### Phase 2: Analysis Pipeline

```text
1. AnalysisJob 생성
2. Snapshot Loader 구현
3. Analysis Agent prompt 구현
4. Character/Event/Location/Foreshadowing/Relation 추출
5. Analysis Gate 구현
6. MongoDB 저장
```

### Phase 3: Indexing

```text
1. ChromaDB indexing adapter
2. Elasticsearch indexing adapter
3. index_sync_logs
4. stale index check
```

### Phase 4: Agentic Search

```text
1. SearchIntentClassifier
2. QueryPlanner
3. ES Retriever
4. Chroma Retriever
5. MongoSOTResolver
6. ContextPackageBuilder
7. Context Gate
```

### Phase 5: Writing AI

```text
1. WritingRequest schema
2. WritingBrief schema
3. ContextPackage 기반 prompt
4. draft_candidate 생성
5. Writing Gate
6. editor 반영
```

### Phase 6: Review UI

```text
1. 분석 candidate 목록
2. confirmed 승격
3. rejected 처리
4. 미회수 떡밥 목록
5. 인물/장소/사건 카드
```

---

## 18. 최종 구조 요약

이 시스템의 최종 구조는 다음과 같다.

```text
MongoDB
= 정본 저장소
= 원문, snapshot, block, schema, canon, memory 저장

ChromaDB
= 의미 검색 캐시
= 유사 장면, 문체, 의미적 관련성 검색

Elasticsearch
= 키워드/메타데이터 검색
= 이름, 별칭, 대사, 상태, 필터 검색

Agentic Search
= 검색 계획 수립
= ES + Chroma + Mongo 조합
= SOT 재로드
= ContextPackage 생성

Writing AI
= ContextPackage 기반 글 생성
= 직접 DB 접근 없음
= 출력은 draft_candidate

Analysis AI
= 저장된 글을 구조화 기억으로 컴파일
= 출력은 analysis_candidate

Gate
= candidate를 검사하고 통과/수정/재검색/review/block 결정

Editor + Chat
= 사용자가 체감하는 인터페이스
```

한 문장으로 정리하면 다음과 같다.

```text
이 시스템은 MongoDB를 정본 기억으로 삼고, ChromaDB와 Elasticsearch를 검색 인덱스로 사용하며, Agentic Search가 글쓰기 AI와 분석 AI에게 필요한 기억만 포인터 기반으로 제공하는 개인 창작 메모리 운영체제이다.
```
