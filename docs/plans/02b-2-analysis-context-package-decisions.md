# Phase 2B.2 착수 결정 브리프 — prior-memory 검색과 Analysis 비교용 ContextPackage (⑧)

상태: `Resolved (2026-07-05) — D1=A, D2=A(semantic seam), D3=A, D4=B(A 포함 hybrid), D5=A, D6=B. 브리프 검증 F1(경로)·F2(§8 ⑧ 완성 문구) 정정 반영, F3/F4/F5는 착수 명시 항목. 코드 착수는 2026-07-06.`
기준 문서: [`../system-contract-sot.md`](../system-contract-sot.md), [`02b-analysis-compare-kickoff-decisions.md`](02b-analysis-compare-kickoff-decisions.md) §D6, [`analysis-memory-taxonomy.md`](analysis-memory-taxonomy.md) §비교용 ContextPackage, [`04-agentic-search-kickoff-decisions.md`](04-agentic-search-kickoff-decisions.md) §8, [`04-context-package-completion-decisions.md`](04-context-package-completion-decisions.md), [`02-analysis-pipeline.md`](02-analysis-pipeline.md) §Phase 2B
목적: Phase 2B.2(기존 canonical 기억을 검색해 비교용 package로 묶는 단계) 구현 전에 추측 구현을 피하기 위한 최소 결정을 한 화면에 모은다. Phase 2A/2B.1 패턴대로 첫 slice를 최소로 좁히고, action 판정(2B.3)과 versioned upsert(2B.4)는 이 slice에서 켜지 않는다.

## 현재 확정된 경계 (결정이 아니라 사실)

- 2B.1로 canonical `MemoryEntry` store가 섰다(SoT v1.6.40). 승격된 memory는 `memory_type`(2A 3종)/`payload`/`provenance`/`source_ref_ids`/`confidence`/`version`/감사 필드를 가지며 status는 `canonical` 단일이다. 이제 "대조 상대"가 실재한다.
- **2B.1은 D3 scope key(`memory_type + scope_type + scope_id + 정규화 name`) 매칭을 구현하지 않고 2B.3에 위임했다.** 2B.1 유일성은 `source_candidate_id`뿐이라, 같은 entity에 대한 canonical이 다수 존재할 수 있다(2B.3이 화해). `AnalysisCandidate`에는 `scope_type/scope_id/name` 필드가 없다(payload 안에 유형별로 `name`/`event`/`question`만 있음).
- §8(agentic search 착수 §8)은 ContextPackage를 **A(단일 schema + purpose literal)로 시작하되 C(Writing용 + Analysis 비교용 모두 완성)까지 도달**하기로 확정했고, analysis 비교용 확장 필드 결정을 Phase 2B 착수 브리프(=이 문서 계열)로 위임했다. 이 slice가 끝나야 §8이 닫힌다.
- taxonomy는 비교용 package가 Writing용과 목적이 다르며 **기존 값·상태·source·version·비교 이유가 반드시 포함**되어야 한다고 명시한다(§비교용 ContextPackage).
- SoT v1.6.38(D1=B)로 Phase 4 ⑧(Analysis 비교용 뷰)과 ⑤(candidate 포함)이 Phase 2B에 종속됐다. ⑧은 이 slice가 소유한다. ⑤(Writing에 canonical 포함)는 별도 후속.
- 현재 ContextSearch는 Writing용이다: `ContextSearchPurpose.WRITING_CONTEXT` 1종, need 4종(`current_scene/recent_scenes/event_context/source_quote`), `ContextItem`은 source block/SOT scene 텍스트 + `IndexPointer`를 담는다. `evaluate_context_gate`는 candidate 라벨 금지 등 Writing-안전성 방어선을 소유한다.
- 비교 작업 자체(action 판정)는 `analysis_compare` allowlist bounded flat loop, sub-agent 없음(불변).

## ⚠ 헤드라인 긴장 — 순서 의존 (CLAUDE.md §1에 따라 명시)

2B 착수 브리프는 순서를 **2B.2(검색/비교 package) → 2B.3(compare→action)**로 잡았다. 그런데 "이 candidate와 *같은 대상*인 기존 기억"을 정밀히 고르는 것은 2B.1이 2B.3으로 위임한 **D3 scope key 매칭 그 자체**다. 즉 2B.2가 2B.3의 identity 매칭에 의존하는 것처럼 보인다.

해소 프레이밍(D1에서 확정 요청): **2B.2는 "검색+패키징", 2B.3은 "판정"으로 분리한다.** 2B.2는 candidate와 *관련 후보군*(같은 project·같은 `memory_type`의 canonical 기억)을 결정적 coarse key로 모아 비교용 package로 제시하고, "이 중 어느 것이 같은 대상인가 / update·add_evidence·no_change·conflict 중 무엇인가"의 판정은 2B.3이 한다. scope key 정밀화도 2B.3 소관이다. 이렇게 하면 2B.2가 2B.3보다 먼저여도 성립한다(coarse 후보군 → 정밀 판정). 오너가 다른 순서(2B.3 먼저, 또는 2B.2에서 이미 scope key 도입)를 원하면 그 방향을 canonical로 명시해야 한다.

## 제안하는 slice 범위 (2B.2)

- `ContextSearchPurpose.ANALYSIS_CONTEXT = "analysis_context"` + `ContextNeed.PRIOR_MEMORY = "prior_memory"` literal 신설(enum 확장, schema 분기 없음).
- **prior-memory 검색**: 주어진 (project, memory_type[군])에 대해 `memory_entries`에서 `status="canonical"` 기억을 결정적으로 조회.
- **Analysis 비교용 package**: taxonomy 필수 필드(기존 값·상태·source·version·비교 이유)를 담는 item/section을 ContextPackage 계열에 추가(§8 C의 package 5필수 채움). ⑧ 위임 필드 중 `scope`는 MemoryEntry에 아직 없으므로(2B.1/D1=A가 2B.3에 위임) 여기서 닫지 않는다 — §8 ⑧ 추적 항목은 2B.3까지 열려 있다.
- 최소 HTTP surface 또는 내부 service 표면(2B.3이 소비).

이 slice가 **하지 않는 것**: action 판정(2B.3), 의미적/embedding 기반 memory 검색, D3 scope key 정밀 매칭, versioned upsert(2B.4), taxonomy 확장(2A 3종 유지), package persist, ⑤ Writing canonical 포함.

---

## 결정 필요 항목

### D1. 2B.2/2B.3 경계와 순서

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 검색+패키징 vs 판정 분리 (제안) | 2B.2는 coarse 후보군(project + memory_type) 검색·패키징만, 동일성/action 판정과 scope key 정밀화는 2B.3 | 순서 유지, 각 slice 최소, 2B.1 위임과 정합 | 2B.2 단독으로는 "관련"이 거칠다(같은 type 전부) |
| B. 순서 뒤집기 (2B.3 먼저) | scope key/판정을 먼저 정하고 검색을 그 key로 | 검색이 처음부터 정밀 | 2B.1이 2B.3으로 위임한 것을 앞당김, 착수 브리프 순서 변경 |
| C. 2B.2에서 scope key 도입 | 이 slice에서 D3 key 산출을 함께 확정 | 검색 정밀 | candidate→scope 매핑을 지금 추측(2B.1이 피한 이유), slice 비대 |

추천: **A.** 2B.1 위임과 착수 브리프 순서에 맞고, coarse 후보군은 2B.3 판정의 정당한 입력이다. "관련"의 정밀화는 판정과 함께 2B.3에서 잠근다.

### D2. prior-memory 검색 메커니즘

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 결정적 key 조회만 | `memory_entries`에서 `(project_id, memory_type, status="canonical")`로 조회. 새 index 1개 | 추측 없음, 재현 가능, D3=A 정신과 일치 | 별칭/의미 유사는 못 잡음(2B.3/후속) |
| B. 의미적(embedding) 검색 | memory를 vector로 색인해 유사도 검색 | 별칭 흡수 | memory embedding/색인 부재 → fake 위 추측(D3=B를 뺀 이유와 동일) |
| C. Writing vector index 재사용 | 기존 source-block index로 검색 | 인프라 재사용 | 그 index는 원문 블록을 반환하지 memory record가 아님 — 대상 불일치 |

추천: **A.** 첫 slice는 결정적 조회만. memory 의미 검색은 별도 색인 결정이 선 뒤 후속.

### D3. 비교용 package 형태 (§8 ⑧ package 필드)

taxonomy 필수: 기존 값(`payload`), 상태(`status`), source(`source_ref_ids`), `version`, 비교 이유(왜 이 기억이 후보로 뽑혔는가 = match/retrieval reason).

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 단일 schema 확장(§8 A→C) | `prior_memory` need로 조회된 결과를 담는 `PriorMemoryItem`(memory_id/memory_type/value/status/version/source_ref_ids/match_reason)을 ContextPackage 계열에 추가. purpose=analysis_context일 때 채워짐 | §8의 "단일 schema + purpose" 약속 유지하며 5필수 채움, Writing item과 공존 | ContextItem과 다른 item 타입이 하나 늘어남; scope는 미포함(2B.3) |
| B. 별도 `AnalysisComparisonPackage` 계약 | 비교용을 완전 분리 | 각자 최적 | §8이 A→C(한 schema 계열 완성)를 택함 — 과분기 |

추천: **A.** `PriorMemoryItem`(위 7필드, `match_reason`은 첫 slice에서 `memory_type` 일치 등 결정적 사유 문자열)를 추가하고 package가 purpose에 따라 macro/micro 대신 `prior_memories` section을 담는다. taxonomy 5필수(값·상태·source·version·비교 이유)를 정확히 채운다. **`value`는 MemoryEntry에 `value` 필드가 없으므로 `payload`(Mapping)로 명시한다**(F3). `scope`(scope_type/scope_id)는 MemoryEntry에 부재라 이 slice에서 담지 않고 2B.3에서 닫는다 — 따라서 §8 ⑧은 여기서 "5필수 완성"이지 "전체 완성"이 아니다.

### D4. 비교용 검색 요청 입력

Writing 요청은 `query/needs/current_position`이 자연스럽지만, memory 조회의 실제 key는 candidate의 `memory_type`(+후속 scope)이다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. memory_type 파라미터화 | 요청이 대상 `memory_type`(들) + project를 담고 `needs=[prior_memory]` | 조회 key와 정확히 일치, 결정적 | Writing 요청 필드(query/current_position)와 형태가 다름 → optional 처리 필요 |
| B. analysis_job 기준 | job/snapshot id로 그 job의 candidate type들을 유도해 자동 조회 | 호출자 편의(2B.3 통합에 자연) | job↔memory_type 유도 로직이 이 slice에 추가됨 |

추천: **A를 계약으로, B는 2B.3 통합에서 얹기.** 2B.2는 `memory_type` 파라미터화된 결정적 조회 표면을 열고, "job의 candidate type들로 자동 호출"은 2B.3 compare 통합이 조립한다. 요청은 `ContextSearchRequest`를 재사용하되 analysis_context에서 `query/current_position`은 optional, `memory_types` 필터를 추가한다.

### D5. Context Gate 적용 범위

`evaluate_context_gate`의 candidate 라벨 금지는 Writing-안전성 방어선이다. analysis_context의 소비자는 Writing이 아니라 Analysis compare(2B.3)다.

| 선택지 | 설명 |
|---|---|
| A. purpose별 Gate 규칙 분리 | analysis_context에는 cross-project·SOT 격리 같은 구조 검사는 적용하되, "candidate 금지"는 무의미(대상이 canonical memory)하므로 적용 안 함. Writing-only 규칙과 분리 |
| B. Gate 동일 적용 | 한 Gate가 모든 purpose에 |

추천: **A.** analysis_context는 canonical memory만 담으므로 candidate 금지 규칙은 애초에 위반 대상이 없다. cross-project 격리는 유지. 단 첫 slice에서 Gate를 analysis_context에 확장할지, 아니면 조회 자체가 project-scoped라 Gate 없이 충분한지는 구현 시 최소로 정한다(과설계 회피).

### D6. HTTP surface 여부

| 선택지 | 설명 |
|---|---|
| A. service 표면만 | 2B.2는 내부 service 메서드로 열고, HTTP는 2B.3 compare 통합에서 함께 | slice 최소, 2B.3이 실소비자 |
| B. 지금 HTTP도 | `POST /projects/{project_id}/analysis/jobs/{job_id}/context` 즉시 노출(D4 job-aware 진입면) | 독립 검사 쉬움 | 실소비자(2B.3) 없이 표면 먼저 |

추천: **A(service 표면 우선), 단 최소 read 확인용 HTTP는 선택.** 2B.1은 HTTP까지 열었지만 그건 사용자 승인이라는 실사용자가 있었다. analysis_context의 실소비자는 2B.3이므로 service 계약을 먼저 잠그고 HTTP는 2B.3과 함께 여는 편이 자연스럽다. (오너가 독립 검증 편의를 위해 HTTP를 원하면 B.)

## 후속 (이 브리프 범위 밖)

- 2B.3 compare→action 판정(D4 literal 실현) + **D3 scope key 산출/매칭**(2B.1·2B.2가 위임한 identity 경계), 2B.4 versioned upsert/재색인.
- ⑤ Writing context에 canonical 포함(Gate 규칙 정련), memory 의미 검색(embedding 색인), taxonomy 확장, package persist, tool-call flat loop planner.

## Owner decisions — 2026-07-05

- **D1 = A.** 2B.2=검색+패키징(coarse 후보군: project + memory_type), 2B.3=판정 + scope key 정밀화. 정밀 매칭은 차후. 근거(오너): 글쓰기(소설)라 scope/청킹 단위가 비교적 정해져 예측 가능하므로 유형 단위 coarse로 근시일 충분하다. **단 확장성 있게** — 후속 scope key 정밀화가 같은 계약 뒤로 들어올 수 있게 seam을 연다.
- **D2 = A (semantic seam 포함).** 첫 slice는 결정적 key 조회만. **단 후속 LLM의 의미적 검색 쿼리 생성이 연결될 것을 전제로**, 검색 backend를 주입 가능한 seam(현재 planner/vector adapter 주입 패턴과 동일)으로 두어 나중에 semantic 검색이 같은 인터페이스로 들어오게 처리한다.
- **D3 = A.** 단일 ContextPackage schema에 `PriorMemoryItem`(memory_id/memory_type/value/status/version/source_ref_ids/match_reason) 추가. taxonomy 5필수(값·상태·source·version·비교 이유)를 정확히 채운다. **§8 ⑧은 "5필수 완성"이며 scope(scope_type/scope_id)는 MemoryEntry 부재로 담지 않아 ⑧ 추적은 2B.3까지 열림**(F2 정정: D1=A가 scope를 2B.3에 위임했으므로 지금 scope를 넣으면 MemoryEntry에 scope를 추가해야 해 D1과 모순 — 문구를 "완전 완성"에서 "5필수 완성"으로 정정). `value`는 MemoryEntry의 `payload`(Mapping)로 명시(F3).
- **D4 = B (A 포함 hybrid).** 검색 primitive는 memory_type 파라미터화(A, 재사용·격리 테스트 코어), 그 위에 job-aware 진입면(B, job → candidate_type 집합 유도 → primitive 호출)을 얹는다. HTTP(D6=B)가 노출하는 표면은 job 단위, 내부는 memory_type primitive. job 유도는 "그 job이 만든 memory_type 집합"까지만(coarse, D1=A와 일치); candidate 단위 정밀은 2B.3. 근거(오너): 분석 LLM(compare)에 파라미터가 흘러들어가야 하므로 primitive와 job-context 진입면이 둘 다 필요하다.
- **D5 = A.** purpose별 Gate 규칙 분리. analysis_context는 canonical만 담아 candidate 금지 규칙이 무적용, cross-project 격리는 유지. 근거(오너): 각 금지 규칙/단계에 서로 다른 레벨이 적용·분기되어 세부 조정되어야 한다(에러 taxonomy `backend/system/llm/sot_error` 계열 분기와 같은 방향). Gate를 단계·purpose별로 분기 가능한 구조로 둔다.
- **D6 = B.** 지금 HTTP surface를 연다(`POST /projects/{project_id}/analysis/jobs/{job_id}/context` 형태, D4 job-aware 진입면). 근거(오너): 어차피 처리해야 하고 TDD 방식이라 검증에도 필요하다.

## 결정 요약

| 결정 | 선택 | 핵심 |
|---|---|---|
| D1 | A | 검색+패키징 vs 판정 분리, coarse(project+memory_type), 확장성 seam |
| D2 | A | 결정적 조회만 + 후속 semantic 검색 주입 seam |
| D3 | A | 단일 schema에 `PriorMemoryItem`, taxonomy 5필수 |
| D4 | B(A 포함) | primitive=memory_type, 진입면=job 유도 hybrid |
| D5 | A | purpose/단계별 Gate 분기, candidate 금지 무적용 |
| D6 | B | 지금 HTTP(job 단위), TDD |

신설 literal: `ContextSearchPurpose.ANALYSIS_CONTEXT`, `ContextNeed.PRIOR_MEMORY`.

## 착수 시 명시/회귀 항목 (검증 F3/F4/F5, non-blocking)

착수 전 결정은 아니지만 구현 중 반드시 명시하고 회귀로 잠근다.

- **F3 — PriorMemoryItem 필드 출처 명시.** `value`는 MemoryEntry의 `payload`(Mapping)로 명시(MemoryEntry에 `value` 필드 없음). MemoryEntry에 있으나 5필수에 없는 `provenance`/`confidence`는 2B.3 compare가 의존하면 그때 PriorMemoryItem에 추가한다(지금은 5필수만).
- **F4 — self-match 제외 경계.** D4 job-aware 진입면이 "그 job이 만든 memory_type 집합"을 조회하면, 2B.1 auto-promote로 **같은 job에서 승격된 memory가 자기 자신을 prior-memory로 잡는다.** 기본값(오너 승인, 2026-07-05): 조회에서 `analysis_job_id == 조회 대상 job`인 memory를 제외(결정적 self-exclusion)하고 2B.2 회귀로 잠근다. **단 오너가 "일단 기본값으로 하되 실제 구현하며 확인" 입장이므로 잠정값이다** — 2B.3 compare(no_change/충돌 판정)와의 상호작용을 실구현에서 관찰한 뒤, self-exclusion 유지 vs no_change 흡수를 확정하고 근거를 work_log에 남긴다.
- **F5 — Gate 실제 적용 여부.** D5는 "purpose/단계별 분기 구조"를 결정했고, "이 slice에서 analysis_context에 Gate를 실제로 호출할지"는 착수 시 최소로 정한다. 조회 자체가 project-scoped라 cross-project 격리는 조회 계약이 이미 보장하므로, 첫 slice는 별도 Gate 호출 없이 조회 격리로 충분한지 vs 최소 Gate 분기를 붙일지를 구현 시 결정하고 근거를 work_log에 남긴다.
