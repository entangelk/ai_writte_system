# Phase 2B.3 착수 결정 브리프 — compare→action 판정과 D3 scope key

상태: `Resolved (2026-07-06) — D1=A(터미널 JSON), D2=A(character만 결정적 대조, event/open_question은 대조 제외+semantic seam 후속), D3=A(하이브리드), D4=A(proposal only), D5=A(scope 저장+승격 시 산출, 2B.1 경계 확장), D6=fixture로 확정(self-exclusion 유지 무게), D7=A(POST .../compare). 코드 착수 2026-07-06.`
기준 문서: [`../system-contract-sot.md`](../system-contract-sot.md) v1.6.41, [`02b-analysis-compare-kickoff-decisions.md`](02b-analysis-compare-kickoff-decisions.md) §D3·§D4, [`02b-2-analysis-context-package-decisions.md`](02b-2-analysis-context-package-decisions.md)(Implemented), [`analysis-memory-taxonomy.md`](analysis-memory-taxonomy.md) §대조·§유형별 질문, [`02-analysis-pipeline.md`](02-analysis-pipeline.md) §Analysis AI 경계, [`flat-loop-gate.md`](flat-loop-gate.md) §analysis_compare
목적: Phase 2B.3(candidate ↔ 기존 canonical 기억 대조 → action 판정) 구현 전에 추측 구현을 피하기 위한 최소 결정을 한 화면에 모은다. 2B.1/2B.2가 2B.3으로 위임한 identity 경계(scope key)를 여기서 닫는다. versioned upsert 실쓰기(2B.4)는 이 slice에서 켜지 않는다.

## 현재 확정된 경계 (결정이 아니라 사실)

- 2B.1로 canonical `MemoryEntry` store가 섰다(SoT v1.6.40). 승격 memory는 `memory_type`(2A 3종)/`payload`/`provenance`/`source_ref_ids`/`confidence`/`version=1`/감사 필드를 가지며 status는 `canonical` 단일. **`scope_type`/`scope_id` 필드는 없다.**
- 2B.2로 prior-memory 검색+패키징이 섰다(SoT v1.6.41). `AnalysisContextService`가 (project, memory_type 집합)로 canonical memory를 coarse 조회해 `PriorMemoryItem`(memory_id/memory_type/value/status/version/source_ref_ids/match_reason)로 묶는다. **scope는 미포함 — 2B.3이 채워 §8 ⑧을 완전 완성하기로 명문화됨.** F4 self-exclusion(`exclude_job_id`)은 오너 승인 **잠정값**이고 2B.3 상호작용 관찰 후 확정하기로 되어 있다.
- 부모 브리프 확정: **D3=A** 결정적 key(`memory_type + scope_type + scope_id` + 정규화 name) 완전일치만, 별칭/동명이인은 `merge/split` review 후보(자동 병합 없음). **D4=A** action literal `create/update/add_evidence/no_change/conflict` + `merge/split`(review-only). 판정 경계는 "2B.3에서 fixture와 확정".
- Analysis AI 경계(불변): 원문에 없는 사실 보충 금지, 기존 기억 직접 덮어쓰기/merge 금지, canon 확정 금지. AI는 근거·비교 결과를 담은 candidate/proposal만 낸다.
- candidate payload 실제 shape(`analysis/schema.py`): character=`{name, observation}`, event=`{event}`, open_question=`{question}`. **character만 자연스러운 안정 식별자(`name`)를 가진다.** event/open_question은 엔티티 id가 없고 서술 텍스트뿐이다.
- agent_loop 계약층은 tool-call branch가 3중 상류 의존(Gateway tool-call parsing 미구현·model tool-call wire 미계약·`ProviderTurnResult` terminal content 전용)으로 **일시 정지** 상태다(HANDOFF). 2A extraction과 4.2 planner는 이 정지 때문에 **터미널 JSON 1-turn**(strict parse + 1회 repair)으로 구현됐다.

## ⚠ 헤드라인 긴장 — D3 scope key가 event/open_question에 없다 (CLAUDE.md §1)

D3=A는 `memory_type + scope_type + scope_id + 정규화 name`을 결정적 identity key로 확정했다. 그러나:
- **character**는 `name`이 있어 `scope_type="character", scope_id=정규화(name)`로 깔끔하게 key가 선다.
- **event/open_question**은 payload에 엔티티 이름/id가 없다(`{event}`/`{question}` 서술 텍스트뿐). "같은 event인가"는 본질적으로 **의미 판정**이라 결정적 key로 잡히지 않는다.

즉 D3=A의 결정적 key는 character에만 자연 적용되고, event/open_question의 identity를 어떻게 처리할지가 **미결(추측 금지 대상)**이다. D2에서 이를 확정한다.

## 제안하는 slice 범위 (2B.3)

- **scope key 산출**: candidate/memory에서 `scope_type`/`scope_id`/`normalized_name`을 결정적으로 도출(유형별 규칙은 D2). `MemoryEntry`·`AnalysisCandidate`·`PriorMemoryItem`에 scope 필드 추가(D5).
- **compare 판정**: (candidate, 매칭된 prior_memories) → action literal 1개(D4=A 집합) 산출. 메커니즘은 D1, system/LLM 분담은 D3.
- **산출물 = proposal only**: 실제 memory 쓰기(versioned upsert)는 2B.4. 2B.3은 action proposal(비교 결과)만 낸다(D6).
- **§8 ⑧ 완전 완성**: `PriorMemoryItem`에 scope 추가(D5).
- **F4 self-exclusion 확정**: compare가 no_change를 판정할 수 있게 되므로 self-exclusion 유지 vs no_change 흡수를 여기서 확정(D7).
- 최소 HTTP surface.

이 slice가 **하지 않는 것**: versioned upsert 실쓰기(2B.4), 의미적 entity resolution(D3=A 결정적만), taxonomy 확장(2A 3종 유지), merge/split 자동 실행(항상 review-only), tool-call flat loop planner.

---

## 결정 필요 항목

### D1. compare 판정 메커니즘

부모 브리프는 "compare는 `analysis_compare` allowlist bounded flat loop"라 했으나, tool-call branch는 상류 3중 의존으로 정지 상태다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 터미널 JSON 1-turn (2A/4.2 선례) | LLM에 candidate + 매칭 prior_memories를 prompt로 주고 action JSON을 strict parse(+1회 repair) | 상류 미차단, 2A extraction·4.2 planner와 동일 검증된 패턴, versioned prompt 재사용 | flat loop tool preflight(compare/validate 5종)는 후속 |
| B. analysis_compare bounded flat loop 지금 | 부모 브리프 문구대로 tool-call 루프 | 부모 문구에 문자 그대로 부합 | Gateway tool-call wire 미계약 → 지금 구현 시 wire 추측(정지 사유 그대로) |

추천: **A.** 2A/4.2가 같은 상류 정지 때문에 터미널 JSON을 택한 선례가 있고, compare는 (candidate, prior_memories)→action이라 1-turn으로 충분하다. flat-loop tool-call 전환은 Gateway tool-call 계약 해소 후(부모 §analysis_compare는 그때 실현). "bounded flat loop"는 계약 목표로 유지하되 첫 구현은 터미널 JSON.

### D2. scope key 산출 규칙 (유형별) — 헤드라인 긴장 해소

D3=A 결정적 key를 유형별 payload에서 어떻게 도출하는가.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. character만 결정적 name key, event/open_question은 identity 매칭 제외 | character: `scope_type="character", scope_id=정규화(name)`. event/open_question: 결정적 key 없음 → 항상 매칭 없음(=create 후보), no_change/conflict는 LLM 판정 대상에서 제외하거나 별도 처리 | 추측 없음, character의 안정 id만 신뢰, D3=A "별칭은 review"와 같은 정신 | event/open_question은 이 slice에서 대조 못 함(중복 event 누적 가능) |
| B. 모든 유형 normalized payload text hash를 scope_id | 대표 필드(name/event/question) 정규화 문자열의 hash | 전 유형 결정적 key | 동일 문구만 매칭 → 표현이 조금만 달라도 별개(사실상 add_evidence/no_change 협소), event/question 의미 매칭 불가 |
| C. character=name key, event/open_question=대표 필드 정규화 문자열 key | event: `scope_id=정규화(event)`, question: `정규화(question)` | 전 유형 key + 사람이 읽을 수 있음 | 긴 서술 문자열의 완전일치는 사실상 거의 안 맞음(B와 유사 한계) |

추천: **A.** character만 자연스러운 결정적 identity(`name`)를 가지며, event/open_question의 "같은 대상"은 의미 판정이라 결정적 key로 잡으면 오매칭/무매칭만 양산한다. 첫 slice는 character에 대해서만 결정적 identity 대조를 켜고, event/open_question은 identity 매칭 없이(항상 create 후보) 두되 **후속에서 의미적 resolution(D3=B, semantic seam)** 으로 연다. 이는 2B.2 D2=A(결정적만, semantic은 seam)와 같은 방향이다. **오너 확인 대상**: event/open_question을 첫 slice에서 대조 제외로 두는 것이 맞는지, 아니면 옵션 C로 완전일치라도 거는지.

### D3. action 판정의 system/LLM 분담

action literal `create/update/add_evidence/no_change/conflict`를 누가 정하는가.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 하이브리드(결정적 key → LLM 라벨) | 결정적 scope key로 "매칭 prior 있음/없음" 판정 → 없으면 `create`(결정적). 있으면 그 prior와 새 관찰을 LLM이 `update/add_evidence/no_change/conflict` 중 1개로 판정(터미널 JSON) | AI 경계 유지(AI는 라벨 proposal만, canon 확정 안 함), 결정적 부분은 재현 가능 | LLM 라벨 판정 경계는 fixture로 잠가야 함 |
| B. 전량 LLM | 매칭 여부까지 LLM이 | 유연 | 결정적 identity를 LLM에 맡겨 재현성↓, D3=A 위배 |
| C. 전량 결정적 | 값 diff 규칙으로 라벨까지 결정적 | 재현성 최고 | update vs add_evidence vs conflict의 의미 구분은 결정적 규칙으로 표현 곤란 |

추천: **A.** D3=A(결정적 identity)와 Analysis AI 경계(AI는 proposal만)를 동시에 만족. 결정적 key가 매칭 후보를 좁히고, 의미 라벨은 LLM terminal-JSON이 낸다. 판정 경계(특히 update↔add_evidence↔no_change, conflict 발화 조건)는 fixture로 양방향 잠금. `merge/split`은 이 slice에서 산출하지 않음(별칭 자동 판정 안 함, review-only 후속).

### D4. 2B.3 산출물 — proposal only (write는 2B.4)

| 선택지 | 설명 |
|---|---|
| A. proposal only | 2B.3은 action proposal(비교 결과: candidate_id ↔ matched_memory_id ↔ action ↔ 근거)만 낸다. 실제 memory version 쓰기는 2B.4 | slice 최소, AI 경계(직접 덮어쓰기 금지)와 정합, 2B.4가 실쓰기 소유 |
| B. 지금 upsert까지 | 판정 즉시 memory update/버전 | compare 가치 즉시 | 부모 브리프가 versioned upsert=2B.4로 분리, slice 비대·직접 쓰기 경계 위험 |

추천: **A.** 부모 브리프의 slice 분해(2B.3 판정 / 2B.4 upsert)를 지키고, "AI가 기존 기억 직접 덮어쓰기 금지" 경계와 정합. proposal은 저장하되(review/2B.4 소비) memory 본문은 건드리지 않는다.

### D5. scope 필드 추가 위치 (§8 ⑧ 완성 + 2B.1/2B.2 위임 회수)

D2의 scope key를 어디에 실체화하는가.

| 선택지 | 설명 |
|---|---|
| A. MemoryEntry + AnalysisCandidate + PriorMemoryItem에 scope 추가, 승격 시 결정적 산출 | 2B.1 승격이 candidate→memory 시 scope 계산(character=name). 기존 memory는 백필 또는 조회 시 산출 | 
| B. 파생만(조회 시 계산, 저장 안 함) | scope를 필드로 저장하지 않고 매칭 시 즉석 산출 |

추천: **A(저장), 단 백필 최소.** compare가 재현·감사 가능하려면 scope가 memory에 기록되는 편이 낫다. 2B.1 승격 경로에 scope 산출을 추가하고(character=정규화 name, event/question=null 또는 미설정), `PriorMemoryItem.scope`를 채워 §8 ⑧을 완전 완성한다. 기존 memory 백필은 이 slice의 fixture 범위에서만(운영 마이그레이션은 후속). **오너 확인 대상**: 2B.1 승격 코드에 scope 산출을 더하는 것(2B.1 경계 확장)이 허용되는지.

### D6. F4 self-exclusion 확정 (잠정값 → 확정)

2B.2는 `exclude_job_id`로 그 job 자신이 승격한 memory를 prior에서 제외했다(잠정값). compare가 no_change를 판정할 수 있게 된 지금 확정한다.

| 선택지 | 설명 |
|---|---|
| A. self-exclusion 유지 | 같은 job 승격 memory는 애초에 prior 후보에서 제외 |
| B. no_change 흡수 | self-exclusion 제거하고, 같은 대상이면 compare가 `no_change`로 판정 |

추천: **관찰 후 A 유지 쪽 무게, 단 fixture로 확정.** self가 prior로 잡히면 항상 no_change라 노이즈다 — 제외가 단순하고 결과 동일. 단 B가 "감사 로그에 no_change를 남긴다"는 이점이 있으면 오너가 선택. 이 slice에서 fixture로 결정하고 근거를 work_log에 남긴다.

### D7. HTTP surface

| 선택지 | 설명 |
|---|---|
| A. `POST /projects/{id}/analysis/jobs/{job_id}/compare` | job의 candidate들을 대조해 action proposal 목록 반환(2B.2 context 진입면과 대칭) |
| B. service 표면만 | 2B.4/review 통합에서 HTTP |

추천: **A.** 2B.2가 `.../context`를 job 단위로 열었으니 `.../compare`도 job 단위 대칭이 자연스럽고 TDD 검증에 유리. proposal은 응답으로 반환(persist는 2B.4).

## 후속 (이 브리프 범위 밖)

- 2B.4 versioned upsert/재색인(proposal→실제 memory version 쓰기 + Chroma 재색인), merge/split review 실행 경로.
- event/open_question 의미적 entity resolution(D2 semantic seam), tool-call flat loop compare(Gateway tool-call 계약 후), taxonomy 확장, ⑤ Writing canonical 포함.

## Owner decisions — 2026-07-06

- **D1 = A.** 터미널 JSON 1-turn compare. 근거: 2A extraction·4.2 planner가 같은 상류 정지(tool-call wire 미계약) 때문에 택한 검증된 패턴. flat-loop tool-call은 Gateway tool-call 계약 해소 후 후속.
- **D2 = A.** character만 결정적 name key(`scope_type="character", scope_id=정규화(name)`)로 identity 대조. event/open_question은 엔티티 id가 없어 첫 slice에서 identity 매칭 제외(항상 create 후보), 의미적 resolution은 semantic seam으로 후속(2B.2 D2=A와 같은 방향, 추측/오매칭 회피).
- **D3 = A.** 하이브리드: 결정적 scope key로 매칭 후보를 좁히고(없으면 결정적 `create`), 매칭 시 action 라벨(`update/add_evidence/no_change/conflict`)은 LLM 터미널 JSON이 낸다. AI 경계(proposal만, canon 확정 안 함) 유지. 판정 경계는 fixture로 양방향 잠금. `merge/split`은 이 slice 미산출(review-only 후속).
- **D4 = A.** proposal only. 실제 memory version 쓰기는 2B.4. AI 직접 덮어쓰기 금지 경계와 정합.
- **D5 = A.** scope를 `MemoryEntry`에 저장하고 2B.1 승격이 candidate→memory 시 산출(character=정규화 name, 그 외 None). `PriorMemoryItem.scope`를 채워 §8 ⑧ 완전 완성. candidate 측 scope는 compare 시 payload에서 즉석 산출(2A candidate 저장 스키마 미변경 — 최소 확장). 오너가 2B.1 승격 코드 확장을 승인함.
- **D6 = fixture로 확정(self-exclusion 유지 무게).** 구현 시 fixture로 결정하고 근거를 work_log에 남긴다. self가 prior로 잡히면 항상 no_change라 노이즈이므로 제외 유지가 기본.
- **D7 = A.** `POST /projects/{id}/analysis/jobs/{job_id}/compare`, job 단위(2B.2 `.../context`와 대칭). proposal 반환, persist는 2B.4.

## 결정 요약 (추천)

| 결정 | 추천 | 핵심 |
|---|---|---|
| D1 | A | 터미널 JSON 1-turn compare(2A/4.2 선례), flat-loop은 후속 |
| D2 | A | character만 결정적 name key, event/open_question은 대조 제외(semantic seam 후속) |
| D3 | A | 하이브리드: 결정적 key 매칭 → LLM action 라벨, merge/split 제외 |
| D4 | A | proposal only, 실쓰기는 2B.4 |
| D5 | A | scope를 MemoryEntry/candidate/PriorMemoryItem에 저장, 승격 시 산출(2B.1 경계 확장 확인 필요) |
| D6 | fixture로 확정 | self-exclusion 유지 무게, 근거 기록 |
| D7 | A | `POST .../jobs/{job_id}/compare` |
