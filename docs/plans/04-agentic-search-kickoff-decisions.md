# Decision brief — Phase 4 agentic search kickoff

상태: `Approved for Phase 4 first slices (2026-07-03)`
정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md), [`04-agentic-search.md`](04-agentic-search.md), [`flat-loop-gate.md`](flat-loop-gate.md)  
목적: Phase 4 첫 구현 slice가 intent taxonomy, planner 방식, retrieval surface, ranking/budget, Gate/fallback, package 계약을 추측하지 않도록 MVP 범위를 좁힌다.

## Owner decisions — 2026-07-03

- §1 purpose/need literal은 **A(최소 집합)**. 후속 slice에서 literal 확장이 가능함을 전제로 승인했다(schema 변경 없이 enum 확장).
- §2 planner는 **B(LLM planner)를 즉시 채택하되, 범위는 터미널 JSON planner**다. LLM이 한 turn에 SearchPlan JSON을 생성하고 tool-call은 쓰지 않는다(Phase 2A extraction과 같은 패턴). tool-call flat loop planner로의 전환 계획은 이 브리프 §2.1에 잡아 둔다 — "LLM tool-call 미가용 시 터미널 JSON으로 우회"는 반복될 결정 패턴이므로 문서로 남긴다. live Gateway(`192.168.1.29:9080` 경유)는 test/smoke로만 사용하고 구현은 provider 추상화 뒤에 둔다. 진입은 지금 IP지만 compose 내부 DNS(`http://gateway:8001`) + `LLAMA_BASE_URL` env 구조라 내부 통신 전환은 설정 변경이다.
- §3 retrieval surface는 **A**. 정확도 스코어링 계열은 시스템 전부 구현 후 후속이다.
- §4 ranking/budget은 **A(최소)**. 최종 튜닝은 후속 작업이다.
- §5 candidate 기억은 **A 먼저 + B 후속 확장**. status 라벨 필드는 A에서도 처음부터 계약에 열려 있어 확장 비용이 낮다는 확인 하에 승인했다(오너는 B 선호였으나 확장 비용이 낮으므로 A→B 순서 채택).
- §6 fallback은 **A**. 단, 오너 조건: 실패 error는 계열이 구별되어야 하고(서버 에러, 시스템 에러, LLM 에러 등), 이후 retry 로직이 어느 컴포넌트를 향할지 선택할 수 있도록 error taxonomy 스키마를 확장 가능하게 둔다.
- §7 package 저장은 **A(비persist)**. 원칙적으로는 C+후속 정리도 가능하나 어차피 후속 처리 대상이므로 A로 시작한다.
- §8 package 경계는 **A(단일 schema + purpose literal)로 시작하되, 이후 slice에서 C(Writing용/Analysis 비교용 모두 완성)까지 반드시 도달해야 한다**. 이 완성 의무는 잊으면 안 되는 추적 항목으로 SoT 미확정 목록과 HANDOFF Next Tasks에 남긴다.

## 현재 확정된 경계

- MongoDB가 정본이고, 검색 hit는 SOT 재조회 전까지 정본이 아니다.
- Agentic 실행은 sub-agent 없이 bounded flat loop만 사용하고, `context_search` profile의 tool allowlist는 `search_memory`, `load_memory`, `validate_context` 3종이다(`flat-loop-gate.md`).
- `validate_context`는 loop 중 preflight이며 종료 후 Context Gate를 대체하지 않는다.
- flat loop 종료 decision과 Context Gate decision은 직교하며 순차 합성한다(2026-06-24 소유자 확정).
- 실제 ChromaDB/Elasticsearch adapter와 embedding model 선택은 핵심 코어 이후 최후속이다(2026-07-02 오너 결정). 현재 검색 가능한 파생 index는 Phase 3A in-memory fake vector index(source block only, in-process 비지속)뿐이다.
- `validate_source_block_record(record)`가 query 계층의 hit 사용 전 stale 검증 guard로 이미 존재한다.

## 구현을 막는 상류 의존 (결정이 아니라 사실)

- AgentLoopRunner의 domain tool-call branch는 미구현이다. Gateway tool-call parsing, model tool-call wire format, `ProviderTurnResult` 구조의 3중 상류 의존이 있어(HANDOFF), LLM이 tool을 호출하는 loop는 지금 구현하면 wire를 추측하게 된다.
- Elasticsearch는 adapter/mapping/analyzer 모두 미구현이다. lexical 경로는 첫 slice에서 라우팅 계약만 남기고 실행 대상이 없다.
- canonical memory store가 아직 없다. Phase 2A candidate는 전부 `needs_review`이며 승인/canonical 승격(Phase 6/2B)이 없다. 따라서 "기억 검색"의 실제 재료는 현재 source block과 Mongo SOT뿐이다.

## 1. MVP purpose/need literal 최소 집합

아이디에이션(`agentic_search_flow.md` §7)은 purpose 13종, need 16종을 나열한다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 최소 집합 | purpose는 `writing_context` 1종, need는 `current_scene`, `recent_scenes`, `event_context`, `source_quote` 4종만 | 현재 검색 재료(source block + Mongo SOT)로 전부 실제 서빙 가능, literal마다 회귀로 잠글 수 있음 | 나머지 literal은 후속 확장 |
| B. 아이디에이션 전체 채택 | 13 purpose / 16 need를 모두 enum에 올림 | 최종 그림과 가까움 | `character_state`, `voice` 등 대부분은 canonical memory 부재로 서빙 불가 — 지원하지 않는 literal이 열린 것처럼 보임 |
| C. purpose 2종 동시 | `writing_context` + `analysis_context` | Phase 2B 준비 병행 | analysis 비교용 package 요구 필드가 아직 미확정(§8) |

추천: **A**. Phase 2A taxonomy 결정과 같은 원리다 — 실제 서빙 가능한 literal만 열고, 나머지는 code enum에 올리지 않은 채 후속 candidate로 문서에만 남긴다. `character_state` 등 memory 기반 need는 canonical memory가 생길 때 연다.

## 2. Planner: 규칙 기반 vs LLM 포함

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 규칙 기반 deterministic planner | 요청의 명시 purpose/needs를 받아 need→tool 라우팅 표로 SearchPlan을 만든다. 자유 텍스트 intent 분류 없음 | 상류 tool-call 의존 없이 지금 구현 가능, plan이 결정적이라 회귀로 잠김 | 자유 질의 해석은 못 함 |
| B. LLM flat loop 즉시 사용 | `context_search` profile로 모델이 tool을 호출하며 계획 | 최종 그림 | domain tool-call branch가 상류 3중 의존으로 막혀 있어 wire 추측 구현이 됨 |
| C. hybrid | 규칙 기반 + LLM rerank | 품질 보완 | 첫 slice가 커짐 |

추천: **A**. 요청이 명시 purpose/needs를 담게 하고 `SearchIntentClassifier`(자유 텍스트 분류)와 risk level은 LLM planner와 함께 후속으로 미룬다. SearchPlan producer 계약을 지금 잠가 두면 나중에 LLM planner가 같은 계약 뒤로 들어온다.

채택(2026-07-03 오너 결정): **B의 터미널 JSON 축소형**. 규칙 기반 planner는 구현하지 않고, LLM이 versioned prompt template 기반 1-turn 호출로 SearchPlan JSON을 생성한다(strict parse + 1회 repair, Phase 2A `analysis_extract_v1` 패턴 재사용). tool-call은 wire format 미계약이므로 쓰지 않는다. planner는 주입 가능한 producer 계약 뒤에 두어, unit test는 fake planner/fake provider로 잠그고 live smoke만 실제 Gateway를 쓴다. `SearchIntentClassifier`/risk level은 계속 후속이다.

### 2.1 tool-call flat loop planner 전환 계획 (후속, 추적 항목)

터미널 JSON planner에서 tool-call planner로 넘어가는 조건과 순서를 미리 잠근다. 이 패턴("tool-call 미가용 → 터미널 JSON 우회")은 Phase 2A extraction에 이어 두 번째 적용이며, 이후에도 같은 순서를 따른다.

1. 선행 계약 3종 해소: (1) Gateway tool-call response parsing, (2) model tool-call wire format 확정, (3) `ProviderTurnResult`의 tool-call 수신 구조 확장. 셋 다 SoT 미확정 목록에 이미 있다.
2. 해소되면 `context_search` profile(flat-loop allowlist `search_memory`/`load_memory`/`validate_context`, budget 3/60s/1536/8/repeat 2)이 SearchPlan producer 계약 뒤로 들어온다. ContextPackage/Gate 계약은 변경 없다.
3. 전환 slice는 터미널 JSON planner를 제거하지 않고 fallback으로 유지할지 오너 결정을 받는다.

## 3. 첫 retrieval surface와 실행 방식

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. fake vector + Mongo direct, 순차 실행 | Phase 3A in-memory fake vector index(semantic 경로)와 Mongo direct query(현재 위치/최근 scene)만 사용, step 순차 실행 | 존재하는 표면만 사용, 실패 지점 단순 | lexical 정확 검색은 후속 |
| B. fake lexical adapter 추가 | substring 기반 fake ES adapter도 만들어 3-way 라우팅을 잠금 | 라우팅 표 전체를 계약화 | 첫 slice가 커지고 fake lexical은 실제 analyzer 결정과 어긋날 수 있음 |
| C. real backend 대기 | Chroma/ES 도입 후 착수 | 추측 없음 | 오너 결정(최후속)과 충돌, Phase 4가 무기한 지연 |

추천: **A**. 병렬 실행과 tool별 timeout 세분화는 real backend가 생겨 실제 latency가 측정될 때 결정한다. 첫 slice는 순차 실행 + 요청 단위 wall-clock 한도(기본 60s, `flat-loop-gate.md` `context_search` 값 재사용, 계약 test는 명시값 주입)만 둔다.

## 4. Ranking 공식과 목적별 token budget

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. deterministic 최소 규칙 | need 우선순위 → step 내 vector similarity 순 → 동률은 `(draft_id, version, block_index)` 순. token 추정은 단순 문자수 기반 상수. budget 초과 시 낮은 순위 항목을 통째로 제외(절단 없음) | 결정적이라 회귀로 잠김, fake embedding에서도 계약 검증 가능 | 검색 품질은 미검증(fake embedding이라 지금은 어차피 무의미) |
| B. 가중치 scoring 공식 | 유사도/최근성/status 가중 합산 | 품질 미세 조정 | fake embedding 위에서 가중치를 정하는 것은 추측 |
| C. ranking 없음 | 모두 포함 | 단순 | budget 계약을 잠글 수 없음 |

추천: **A**. `context_budget`은 요청 필수 필드로 두고(§5.2 계약 형태 유지), 실제 embedding model이 들어올 때 ranking 품질을 별도 spike로 재검토한다.

## 5. Candidate 상태 기억 포함 조건

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 첫 slice 제외 | micro evidence는 source block/SOT 재조회만. `needs_review` candidate는 ContextPackage에 넣지 않되, item `status` 라벨 계약(`candidate`/`canonical` 구분 필드)은 지금 연다 | "candidate를 canon으로 표현하지 않음" 규칙을 가장 작게 지킴 | prior-memory context는 후속 |
| B. needs_review 포함 + 라벨 | candidate도 `status="candidate"`로 포함 | 재료 풍부 | 승인 전 후보가 Writing 근거로 흘러갈 위험, Phase 6 review 지위 미확정 |
| C. 승인된 canonical만 | canonical memory만 포함 | 원칙적 | 현재 canonical memory가 없어 사실상 A와 동일 |

추천: **A**. 라벨 필드는 지금 계약에 열어 두어 Phase 2B/6에서 schema 변경 없이 확장한다.

## 6. Retriever 장애 시 fallback 수준

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 명시적 degraded + SOT 실패는 전체 실패 | index retriever(step) 실패는 trace에 실패 이유를 기록하고 남은 step으로 진행하되 package에 `degraded=true` 표시. Mongo SOT reload 실패는 성공 package로 위장하지 않고 전체 실패 | 수용 기준("degraded mode", "성공 위장 금지")을 그대로 계약화 | degraded 판정 회귀 필요 |
| B. best-effort silent | 실패 step을 조용히 건너뜀 | 단순 | trace 설명 가능성 수용 기준 위반 |
| C. 어떤 실패든 전체 실패 | 한 step이라도 실패하면 실패 | 엄격 | ES/Chroma 한쪽 장애 시 degraded 동작 수용 기준과 충돌 |

추천: **A**.

채택(2026-07-03 오너 결정): **A + error taxonomy 확장 조건**. step 실패 기록은 닫힌 문자열이 아니라 계열 구분이 있는 error type을 가진다. 첫 slice literal은 `backend_error`(index/저장소 계열), `system_error`(orchestration/코드 계열), `llm_error`(planner provider 계열), `sot_error`(Mongo SOT reload 계열)로 시작하고, 이후 retry 로직이 error 계열에 따라 재시도 대상을 고를 수 있도록 스키마를 enum 확장 가능하게 둔다. `sot_error`는 degraded가 아니라 전체 실패다.

경계 명문화(2026-07-03 독립 검증 후속, 차단 조건 폐쇄):

- **`sot_error`의 범위는 NotFound만이 아니다.** SOT reload 호출(현재 위치 reload, vector hit stale-guard 검증, hit 재조회, Gate 재검증)에서 탈출하는 모든 non-NotFound 예외 — 실가동 Mongo 장애의 pymongo 예외 포함 — 는 원형으로 전파하지 않고 `ContextSearchFailed(sot_error)` 전체 실패로 매핑한다. try 블록은 SOT 호출만 감싸므로 orchestration 버그를 `sot_error`로 오분류하지 않는다.
- **NotFound는 경로별로 다르다(의도된 분기).** vector hit의 snapshot NotFound는 index drift이므로 해당 hit만 `snapshot_missing` stale 제외(soft, degraded 아님)하고, Mongo direct 경로의 position NotFound는 요청한 위치 자체를 정직하게 reload할 수 없으므로 `sot_error` 전체 실패다. 양쪽 모두 회귀로 잠근다.
- **`system_error`는 예약 literal이다.** 첫 slice에서 발화 경로가 없으며, SOT 호출 밖 orchestration 계열 실패를 분류할 때 사용한다. 발화 경로가 생기는 slice에서 회귀와 함께 연다.
- Context Gate의 SOT 재검증 실패도 같은 `sot_error` lineage를 따른다. Gate는 검증 불가를 pass나 잘못된 사유의 reject로 바꾸지 않는다.

## 7. ContextPackage 저장 기간과 민감 정보

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. persist하지 않음 | package/plan/trace는 응답 payload로만 반환. 저장·retention·TTL은 후속 결정 | 로컬 1인 시스템에서 민감 정보 잔류 없음, retention 결정 유예 | 사후 debug는 응답 로그에 의존 |
| B. Mongo 저장 + TTL | `context_packages` collection + 만료 | 사후 추적 | collection/retention 계약을 지금 정해야 함 |
| C. 영구 저장 | 전부 보존 | 완전한 이력 | 민감 정보/용량 정책 필요 |

추천: **A**. trace ID는 package 안에 포함하므로 추적성 수용 기준은 응답 단위로 충족된다. 운영상 사후 분석이 필요해지면 B를 별도 slice로 연다.

## 8. Writing용과 Analysis 비교용 package 경계

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 단일 schema + purpose literal | 하나의 ContextPackage schema에 `purpose` 필드. 첫 slice는 `writing_context`만 구현하고, analysis 비교용 추가 필드(기존 memory type/scope, status/version 등)는 Phase 2B 착수 브리프에서 결정 | schema 분기 없이 시작, 확장 지점 명시 | analysis 필드가 미정으로 남음 |
| B. 별도 계약 2종 | Writing/Analysis package를 처음부터 분리 | 각자 최적 | Phase 2B 요구가 미확정이라 절반은 추측 |
| C. 지금 둘 다 구현 | 두 variant 동시 | 최종 그림 | 첫 slice 비대 |

추천: **A**.

채택(2026-07-03 오너 결정): **A로 시작하되, 이후 slice에서 C(Writing용 + Analysis 비교용 모두)를 완성해야 한다.** analysis 비교용 확장 필드(기존 memory type/scope, status/version, 검색 이유)는 Phase 2B 착수 브리프에서 결정하고, 그 slice가 끝나야 §8이 닫힌다. 이 의무는 SoT 미확정 목록과 HANDOFF Next Tasks에 추적 항목으로 남긴다.

## 9. 첫 구현 slice (2026-07-03 승인 범위)

오너 결정 반영으로 planner가 규칙 기반에서 터미널 JSON LLM planner로 바뀌었다. Phase 2A와 같은 순서로 두 slice로 나눈다.

### Slice 4.1 — domain 계약 + orchestration + Context Gate (planner 주입)

1. `services/application/app/context_search/`에 pure domain model 추가
   - purpose/need literal enum (§1 최소 집합)
   - `ContextSearchRequest(project_id, purpose, needs, query, current_position, context_budget)`
   - `SearchPlan`/`SearchPlanStep(step_id, need, tools, query)`
   - `ContextItem(need, status, text, pointer, snapshot_id, sot_reloaded, token_estimate, source_ref_ids)` — `candidate`/`canonical` 라벨 필드 포함 (구현 확정 필드명; 초안 스케치의 `pointers`/`source_refs`는 단수 `pointer: IndexPointer`/`source_ref_ids`로 확정)
   - `ContextPackage(project_id, purpose, macro/micro/constraints/do_not_use, trace, degraded, status="candidate")`
   - step 실패 error taxonomy (§6 채택 literal 4종, enum 확장 가능)
2. planner는 주입 가능한 producer Protocol로 두고, Slice 4.1 테스트는 deterministic fake planner를 주입
3. retrieval orchestration: fake vector hit → `validate_source_block_record()` stale guard → Mongo SOT reload → ContextItem. Mongo direct 경로는 `current_scene`/`recent_scenes`를 현재 위치 기준으로 조회
4. deterministic ranking/budget: need 우선순위·similarity·tie-break 순서, 문자수 기반 token 추정, 초과 항목 제외
5. Context Gate 최소 검사: project_id 일치, SOT reload 증거, stale 제거, candidate 라벨, budget 준수 → `GateDecision(pass/reject + findings)`
6. 회귀
   - project isolation (다른 project record가 package에 들어가지 않음)
   - archive/drift 후 stale hit가 package에서 제외됨 (guard 경유)
   - Mongo SOT reload 실패 시 성공 package로 위장하지 않음 (`sot_error` 전체 실패)
   - budget 준수와 초과 항목 제외 (양방향)
   - retriever step 실패 시 degraded 표시 + trace에 계열 구분된 error type 기록
   - 빈 검색 결과도 trace로 설명 가능
   - Gate reject 분기 (should-fire / should-NOT-fire 양방향)

### Slice 4.2 — 터미널 JSON LLM planner adapter

1. versioned prompt template `context_search_plan_v1` (기존 `prompt_templates` 저장소 재사용)
2. Gateway `/v1/generate` 1-turn 호출 → SearchPlan JSON strict parse + 1회 repair (Phase 2A adapter 패턴)
3. 유효 need/tool literal 검증: 모델이 §1 집합 밖 literal을 내면 repair 1회, 그래도 남으면 `llm_error`
4. unit은 fake provider, live smoke script만 실제 Gateway endpoint 사용

HTTP API surface, tool-call flat loop planner(§2.1), lexical(ES) 경로, prior-memory(analysis 비교) purpose(§8 C 완성), package persist는 모두 후속 slice다.

### Slice 4.3 — HTTP API surface + service async wiring

1. `ContextSearchService.build_context_package`를 async로 올려 async 터미널 JSON planner를 await한다. sync fake planner(Slice 4.1)는 `inspect.isawaitable`로 계속 동작한다. `evaluate_context_gate`는 planner 미호출이라 sync 유지.
2. `POST /projects/{project_id}/context-search`: body(query/needs/purpose/current_position/max_tokens) → ContextSearchRequest, build_context_package + Context Gate 실행, ContextPackage + gate 결정 직렬화 반환.
3. create_app이 env(`LLM_GATEWAY_BASE_URL`) 기반으로 TerminalJsonSearchPlanner를 wiring한다(`_default_context_search_service`). 미구성이면 503.
4. 오류 매핑: invalid 400 / wall-clock 504 / ContextSearchFailed 502 / missing project 404 / 미구성 503.

deployed vector adapter는 non-persistent fake라 vector need hit은 없고 Mongo-direct need만 서빙한다(real Chroma 후속). tool-call planner(§2.1), ES lexical, prior-memory purpose(§8 C), package persist는 계속 후속이다.

## 구현 후속 — Slice 4.1 (2026-07-03)

승인 당일 Slice 4.1을 구현했다. `services/application/app/context_search/`에 §9 domain model 전부와 `ContextSearchService`(planner 주입, 순차 실행, wall-clock 한도 기본 60s), `evaluate_context_gate()`(독립 재검증: cross-project, SOT reload 증거, candidate 라벨 금지, stale 재검출, budget)를 추가했다. `InMemoryVectorIndexAdapter`에 project-scoped `query_similar(project_id, vector, limit)` cosine 유사도 query 표면을 추가했다. `current_scene`/`recent_scenes`는 SOT block kind(heading/scene marker) 기반 deterministic 경계로 잘라 AI 추론 split을 쓰지 않는다. vector hit는 stale guard → SOT 재조회를 거친 뒤에만 ContextItem이 되고, hit의 index text는 사용하지 않는다. 회귀가 §9 목록의 양방향 분기를 잠갔다. Slice 4.2(터미널 JSON planner adapter)와 HTTP surface는 다음이다.

## 검증 후속 — 차단 조건 폐쇄 (2026-07-03)

독립 검증(`docs/verifications/2026-07-03/context_search_slice_4_1.md`, 조건부 합격)이 "SOT 백엔드 다운(non-NotFound 예외) → `sot_error`" boundary가 코드·회귀 모두에서 잠기지 않았음을 실증했다(당시 회귀는 이름과 달리 NotFound 경로만 탔고, 백엔드 예외는 원형 탈출). 다음으로 폐쇄했다.

- 코드: SOT reload 호출 4곳(vector stale-guard 검증, vector hit 재조회, Mongo position reload, Gate 재검증 2곳)의 catch를 non-NotFound 예외까지 넓혀 `ContextSearchFailed(sot_error)`로 매핑했다. try 블록은 SOT 호출만 감싼다.
- 회귀: toggle repo(정상 → `fail_reads=True`에서 raw `RuntimeError`)로 진짜 백엔드 예외를 주입하는 양방향 회귀 3개(Mongo position/vector hit/Gate — 정상 시 통과 + 다운 시 `sot_error`)와, vector snapshot NotFound soft 제외(ghost record, `snapshot_missing` + 비degraded) 회귀 1개를 추가했다. 기존 오해 소지 테스트는 `test_missing_position_version_maps_to_sot_error`로 의도/동작을 일치시켰다. 변이 증명: 세 catch를 `CoreSotError`로 되돌리면 5개 재실패, 복원 시 전체 통과.
- 계약: §6에 sot_error 범위/NotFound 경로별 분기/`system_error` 예약을 명문화했다(SoT v1.6.32).
- suite: context_search 28개, 전체 439개 실행 중 395 passed / 44 skipped (이전 기록의 "435개 통과(44 skip)"는 unittest "Ran N" 오독으로, 정확히는 391 passed / 44 skipped였다 — 함께 정정).

## 구현 후속 — Slice 4.2 (2026-07-04)

§9.2를 구현했다. `services/application/app/context_search/planner.py`에 아래를 추가했다.

1. versioned prompt template `context_search_plan_v1`(task_type `context_search_plan`, 상수 + `seed_context_search_plan_template()`). 기존 `analysis/prompt_templates.py`의 `PromptTemplateService.seed_template()` 저장소를 그대로 재사용하고, analysis 모듈은 건드리지 않았다.
2. `build_context_search_plan_request()`: system=template, user=JSON payload(project_id/purpose/query/has_current_position/needs+need별 allowed_tools/tool_literals/output_contract). `project_id`는 모델이 아니라 request에서 주입한다.
3. `parse_search_plan(content, project_id)`: strict JSON object → `steps` 배열 → 각 step(step_id 비어있지 않은 str, need∈`ContextNeed`, tools 비어있지 않은 배열 각 원소∈`SearchTool`, query str). enum literal 위반은 `SearchPlanParseError`.
4. `TerminalJsonSearchPlanner.build_plan()`(async): template 조회 → Gateway `/v1/generate` 1-turn → strict parse. parse 실패 시 원문 output/parser error/원 user payload로 1회 repair 후 재parse. 그래도 실패하면 `ContextSearchFailed(llm_error)`. template 부재도 `llm_error`.

경계 결정: adapter는 §1 enum literal(need/tool) **멤버십만** 검증하고, plan 의미 검증(미요청 need, need별 불허 tool, project 일치)은 Slice 4.1 `ContextSearchService._validate_plan`이 계속 소유한다(중복 없음). provider가 async라 adapter도 async이며(Phase 2A `VersionedPromptAnalysisExtractionAdapter` 패턴), Slice 4.1의 sync `SearchPlanner` Protocol/`build_context_package`는 fake 주입 seam으로 유지된다 — async planner를 sync service에 통합하는 일은 HTTP wiring slice에서 service를 async로 올릴 때 처리한다.

회귀 13개(`tests/test_context_search_planner.py`): valid parse(literal + project_id 주입), plan_id 기본값, 알 수 없는 need/tool literal parse error, non-JSON/bad shape 5종, prompt payload(template + needs/allowed_tools) 확인, markdown-fenced 1회 repair, invalid literal 1회 repair 후 성공, repair prompt에 parser_error/invalid_output 포함, repair 후에도 실패 시 `llm_error`, 1회 초과 재시도 금지(정확히 2회 호출), template 부재 `llm_error`. live smoke는 `scripts/phase4_context_search_planner_live_smoke.py`(실제 Gateway → llama.cpp, sandbox 밖 실행 필요).

후속으로 남긴 것: HTTP API surface, service async 통합/wiring, tool-call flat loop planner(§2.1), lexical(ES) 경로, prior-memory(analysis 비교) purpose(§8 C), package persist.

## 구현 후속 — Slice 4.3 (2026-07-04)

§9.3(HTTP API surface + service async wiring)을 구현했다.

- `ContextSearchService.build_context_package`를 async로 전환하고, planner 결과를 `inspect.isawaitable`로 await한다. Slice 4.1 sync fake planner와 Slice 4.2 async 터미널 JSON planner가 같은 seam에 꽂힌다. `_build_plan`은 planner가 이미 분류한 `ContextSearchFailed`(예: llm_error)는 re-raise하고 나머지 예외만 `llm_error`로 감싼다. `evaluate_context_gate`는 planner 미호출이라 sync 유지.
- Slice 4.1 회귀 2개 클래스(`ContextSearchPackageTest`/`ContextGateTest`)를 `IsolatedAsyncioTestCase`로 전환하고 `build_context_package`/`_package` 호출에 await를 붙였다(기계적, fake planner 클래스는 무수정). 나머지 sync 테스트(`TokenEstimateTest`/`VectorQuerySimilarTest`)는 그대로다.
- `POST /projects/{project_id}/context-search`: body(query/needs/purpose/current_position/max_tokens) → `_build_context_search_request`로 ContextSearchRequest 구성(미지원 purpose/need literal은 ValueError→400), build_context_package + `evaluate_context_gate` 실행, `{package, gate}` 직렬화 반환(package: project_id/purpose/status/degraded/token_estimate_total/macro_items/micro_evidence/constraints/do_not_use/trace, gate: decision/findings).
- 오류 매핑: invalid(ValueError·InvalidContextSearchRequest) 400 / ContextSearchBudgetExceeded(wall-clock) 504 / ContextSearchFailed 502(detail에 error_type) / missing project 404 / planner 미구성 503.
- create_app에 `context_search_service` 주입 param + env 기반 `_default_context_search_service`(TerminalJsonSearchPlanner + `context_search_plan_v1` seed + fake vector/embeddings) 추가. `LLM_GATEWAY_BASE_URL` 부재면 None → 503.
- 회귀 7개(`tests/test_context_search_api.py`): 200 package+gate(macro/micro 존재, sot_reloaded, plan step id), fresh package gate pass, 미지원 need 400, empty needs 400, missing project 404, planner 실패 502(llm_error), 미구성 503. analysis run 회귀 1개(`test_analysis_run_endpoint_uses_env_configured_default_runner`)는 create_app이 이제 analysis+context search 두 provider를 만들어 `assert_called_once`가 깨지므로 env 구성 사용을 검증하는 `assert_called_with`로 정정(계약 유지).

deployed vector adapter는 non-persistent fake라 vector need hit은 없고 Mongo-direct need(current/recent scene)만 서빙한다(real Chroma 후속). tool-call planner(§2.1), ES lexical, prior-memory purpose(§8 C), package persist는 계속 후속이다.

## 원문 및 상세 참고

- [`../abstract.md`](../abstract.md) §5, §12.2, §13.3, §14.3
- [`../agentic_search_flow.md`](../agentic_search_flow.md) §7, §10~13
- [`../contracts.md`](../contracts.md) §5, §6.1
- [`04-agentic-search.md`](04-agentic-search.md)
- [`flat-loop-gate.md`](flat-loop-gate.md)
