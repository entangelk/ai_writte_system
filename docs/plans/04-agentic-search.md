# Phase 4. Agentic Search

상태: `Draft`  
선행 조건: Phase 1 pointer/version, Phase 2 기억 상태, Phase 3 검색 adapter  
후속 소비자: Writing AI, Analysis prior-memory comparison

## 목표

요청을 검색 계획으로 분해하고, ES/Chroma 후보를 MongoDB 정본으로 다시 확인한 뒤 목적에 맞는 최소한의 추적 가능한 ContextPackage를 제공한다. 글쓰기 컨텍스트뿐 아니라 새 분석 결과를 기존 기억과 대조하기 위한 prior-memory context도 지원한다.

## MVP 모듈

```text
SearchIntentClassifier
→ QueryPlanner
→ SearchToolRouter
→ ElasticsearchRetriever / ChromaRetriever / Mongo direct query
→ candidate merge
→ MongoSOTResolver
→ rank/budget
→ ContextPackageBuilder
→ Context Gate
→ TraceLogger
```

graph expansion, multi-hop search, 고급 reranking, retriever plugin은 후속 범위다.

## Agentic 실행 경계

참조 구현은 [`gemma4-reuse.md`](gemma4-reuse.md)의 bounded flat loop를 사용한다.

- 하나의 AgentLoopRunner가 [`flat-loop-gate.md`](flat-loop-gate.md)의 `context_search` allowlist만 호출한다.
- tool은 Application/Worker가 소유하고 LLM Gateway는 tool을 직접 실행하지 않는다.
- `validate_context`는 loop 중 preflight이며, 종료 후 Context Gate 검사를 대체하지 않는다.
- iteration뿐 아니라 time/token/tool-call/repeated-call budget을 검사한다.
- loop 종료는 `completed`와 budget/error 종료를 명시적으로 구분한다.
- sub-agent spawn, delegate tool, nested agent loop 호출은 지원하지 않는다.

## 검색 라우팅 원칙

| 필요 | 우선 도구 | 최종 단계 |
|---|---|---|
| 정확한 이름·별칭·표현 | Elasticsearch | Mongo 재조회 |
| 분위기·유사 장면·의미 | ChromaDB | Mongo 재조회 |
| canon·상태·관계·timeline | MongoDB | 상태/version 검증 |
| 혼합 요청 | ES + Chroma + Mongo | merge 후 Mongo 재조회 |

검색 hit의 text는 후보 표현일 뿐 Writing AI의 근거로 그대로 전달하지 않는다.

## ContextPackage 최소 구조

- 요청과 project scope
- macro context
- micro evidence와 source pointers
- hard/soft constraints
- candidate/canonical 상태 구분
- `do_not_use` 또는 excluded items
- token estimate/budget
- search plan 및 trace ID

Analysis 대조용 패키지에는 추가로 기존 memory type/scope, 현재 값, status/version, source refs, 후보가 검색된 이유가 필요하다. Writing용과 Analysis용 package를 하나의 schema variant로 둘지 별도 계약으로 둘지는 착수 전에 정한다.

## Context Gate 최소 검사

- 모든 항목의 `project_id` 일치
- MongoDB SOT reload 성공
- pointer/version/hash 유효
- stale index 제거 또는 명시적 실패
- candidate를 canon으로 표현하지 않음
- private/excluded memory 차단
- 목적별 context budget 준수

## 산출물

1. ContextSearchRequest/SearchPlan/ContextPackage 계약
2. intent/need taxonomy
3. hybrid retrieval orchestration
4. candidate merge와 SOT resolver
5. ranking/budgeting의 최소 규칙
6. Context Gate, trace, fallback/error 정책
7. context search API
8. Phase 2B용 prior-memory search 목적과 비교 context 계약
9. flat agent loop, domain tool registry, Loop Gate와 trace

## 수용 기준

- exact lookup, semantic lookup, direct status query가 각각 의도한 저장소를 사용한다.
- 반환된 모든 사실이 MongoDB 문서와 source pointer로 추적된다.
- stale, missing, cross-project 후보는 ContextPackage에 들어가지 않는다.
- ES 또는 Chroma 한쪽 장애 시 계약에 정의된 degraded mode로 동작한다.
- MongoDB 정본을 읽을 수 없으면 성공한 ContextPackage로 위장하지 않는다.
- 같은 요청의 trace에서 계획, 도구, 후보 제외 이유를 설명할 수 있다.

## 착수 전 결정사항

- [ ] MVP intent와 need literal의 최소 집합
- [ ] planner를 규칙 기반으로 시작할지 LLM을 포함할지
- [ ] ES/Chroma 병렬 실행과 timeout budget
- [ ] ranking 공식과 목적별 token budget
- [ ] candidate 상태 기억을 포함할 조건과 표현 방식
- [ ] ES/Chroma 장애 시 허용할 fallback 수준
- [ ] ContextPackage 저장 기간과 민감 정보 처리
- [ ] Writing용 ContextPackage와 Analysis 비교용 package의 공통/분리 경계
- [x] flat loop 종료 decision과 기존 Context Gate decision은 직교하며 순차 합성(2026-06-24 소유자 확정)

## 원문 및 상세 참고

- [`../abstract.md`](../abstract.md) §4.3, §5, §8.14, §12.2, §13.3, §14.3
- [`../agentic_search_flow.md`](../agentic_search_flow.md)
- [`../contracts.md`](../contracts.md) §5, §6.1, §13~14
- [`gemma4-reuse.md`](gemma4-reuse.md)
