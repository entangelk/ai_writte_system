# Phase 2B.4 착수 결정 브리프 — proposal→실제 memory versioned upsert / 재색인

상태: `Resolved (2026-07-06) — D1=A(분리 apply, 안전 action 자동), D2=A(append-only+supersedes+superseded), D3=추천(update:conf candidate·source union / add_evidence:conf max·source union), D4=A(재색인 분리→2B.5), D5=A((project,source_candidate_id) idempotency), D6=A(POST .../apply), D7=A(conflict/merge/split review-only). 코드 착수 2026-07-06.`
기준 문서: [`../system-contract-sot.md`](../system-contract-sot.md) v1.6.43, [`02b-analysis-compare-kickoff-decisions.md`](02b-analysis-compare-kickoff-decisions.md) §versioned upsert, [`02b-3-analysis-compare-action-decisions.md`](02b-3-analysis-compare-action-decisions.md)(Resolved), [`analysis-memory-taxonomy.md`](analysis-memory-taxonomy.md) §기존 기억과의 대조·§Agentic 흐름, [`02b-2-analysis-context-package-decisions.md`](02b-2-analysis-context-package-decisions.md)(prior_memory canonical-only 필터)
목적: Phase 2B.3/2B.3.2가 낸 action proposal(create/update/add_evidence/no_change/conflict)을 **실제 `MemoryEntry` version 쓰기**로 반영하기 전에 추측 구현을 피하기 위한 최소 결정을 한 화면에 모은다. 2B.1이 `version=1` create-only로 세운 store에 versioned upsert(이전 version 보존)를 얹고, `MemoryStatus` 두 번째 literal을 도입해 2B.2가 남긴 O1(prior_memory non-canonical 제외) 추적을 닫는다.

## 현재 확정된 경계 (결정이 아니라 사실)

- 2B.1 canonical store(SoT v1.6.40): `MemoryEntry`는 status `canonical` **단일 literal**, `version=1` create-only, 유일성은 `(project_id, source_candidate_id)` unique index(`uniq_memory_candidate_promotion`). `supersedes`/이전 version 링크 **필드 없음**. 승격 두 경로(manual / auto_threshold).
- 2B.3 compare(SoT v1.6.42~43): `AnalysisCompareService.compare_job`이 candidate별 `ActionProposal(candidate_id, candidate_type, action, matched_memory_id, rationale)`를 낸다. `create`=결정적 no-match, `update/add_evidence/no_change/conflict`=매칭 시 LLM judge 라벨, 복수 canonical 동일 identity=결정적 `conflict`. **proposal only — memory 쓰기 없음**(D4=A). `merge/split`은 미산출(review-only 후속).
- taxonomy 계약(불변): `update`는 "기존 문서를 덮어쓰지 않고 이전 version과 source를 보존해야 한다". 흐름은 "사용자 검토 **또는** 허용된 versioned upsert → 영향받은 index 재생성". conflict는 "자동 처리 가능한가?"가 유형별 미결.
- 2B.2 prior_memory 필터: `DeterministicPriorMemoryBackend`는 `status is MemoryStatus.CANONICAL`만 담는다. 지금은 status가 canonical 단일이라 non-canonical 제외 방향을 **테스트할 수 없다**(2B.2 O1: 두 번째 status 도입 시 회귀 추가하라는 코드 마커가 `prior_memory.py`에 있음).
- Analysis AI 경계: AI는 기존 기억 직접 덮어쓰기/merge 금지, canon 확정 금지. proposal만 낸다. 실제 version 쓰기는 **시스템 결정적 연산**(AI 아님)이어야 한다.
- memory→vector 색인은 **아직 없다**. 현재 Chroma/embedding 파이프라인(Phase 3A/4)은 `source_block`만 색인한다(collection 이름은 `project_memory_vectors`지만 실제 records는 source block). memory record용 임베딩 대상 필드·색인 트리거·재색인 배선은 전부 신규다.

## ⚠ 헤드라인 긴장 — 재색인 범위가 이 slice를 크게 만든다 (CLAUDE.md §1·§2)

HANDOFF Next Task #1은 "**Chroma 재색인(memory→vector)도 이때**"라고 2B.4에 묶었다. 그러나:
- memory→vector 색인 자체가 **존재하지 않는다**. 재색인을 켜려면 (a) memory record 임베딩 대상 payload 정규화, (b) 별도 collection/schema, (c) 임베딩 producer 배선, (d) upsert→재색인 트리거(inline vs outbox/worker)가 전부 필요하다 — 이는 Phase 3A/4 vector 백엔드에 준하는 **독립 slice 규모**다.
- versioned upsert(이전 version 보존 + status 전이 + idempotency)만으로도 이미 온전한 slice다.

즉 "version 쓰기"와 "재색인"을 한 slice에 묶으면 slice가 비대해지고 검증 표면이 흐려진다(CLAUDE.md §2 단순성). D4에서 재색인을 이 slice에 포함할지/분리할지 오너가 확정한다. 추천은 **분리**(2B.4=version 쓰기, 2B.5=memory 재색인).

## 제안하는 slice 범위 (2B.4, 재색인 분리 가정)

- **versioned upsert 실쓰기**: `ActionProposal` → 결정적 memory 쓰기.
  - `create` → 새 canonical `MemoryEntry`(`version=1`). (2B.3 create는 이미 no-match이므로 새 candidate 승격 경로와 정합; 2B.1 승격이 아직 안 된 candidate라면 여기서 canonical 생성.)
  - `update`/`add_evidence` → 이전 version 보존한 **새 version**(`version=prev+1`, `supersedes=prev.id`), 이전 entry `status→superseded`.
  - `no_change` → 쓰기 없음(감사 로그만).
  - `conflict`(및 후속 `merge/split`) → **자동 실행 금지**, review 후보로 표면화(쓰기 없음).
- **`MemoryStatus` 두 번째 literal 도입**(`superseded`) + `supersedes`/version 링크 필드.
- **2B.2 O1 폐쇄**: prior_memory canonical-only 필터에 non-canonical(superseded) 제외 양방향 회귀 추가.
- **idempotency**: 같은 proposal 재적용이 중복 version을 만들지 않음.
- **최소 HTTP surface**.

이 slice가 **하지 않는 것**(추천 경계): memory→vector 재색인(2B.5), merge/split 자동 실행(review-only 유지), review queue 영속화(후속), event/open_question 의미적 resolution(D2 semantic seam), taxonomy 확장.

---

## 결정 필요 항목

### D1. apply 트리거 / 실행 경계 (proposal → write)

taxonomy는 "사용자 검토 **또는** 허용된 versioned upsert"라 했다. MVP는 계정/리뷰 UI가 없다. 누가 언제 쓰는가.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. compare와 분리된 명시 apply | compare는 proposal만(현행). 별도 `apply` 연산이 proposal 목록을 받아 결정적 쓰기. 안전 action(create/update/add_evidence/no_change)만 자동, conflict/merge/split은 review-only(쓰기 없음) | AI 경계 정합(쓰기는 시스템 결정적), 2B.3 proposal only 유지, 검증 표면 분리 | 2단계(compare→apply) |
| B. compare가 안전 action 즉시 apply | 매칭 판정 직후 안전 action inline 쓰기 | 1-shot | compare(판정)와 write(반영)를 섞어 slice 경계·회귀 흐림, proposal only 계약 되돌림 |

추천: **A.** 2B.3의 proposal only 계약을 유지하고, 쓰기를 별도 결정적 연산으로 둔다. conflict/merge/split은 자동 실행 금지(taxonomy). **오너 확인 대상**: 안전 action 4종을 자동 apply로 두는 것이 맞는지, 아니면 MVP에서도 전량 명시 승인만 허용할지.

### D2. version 링크 모델 + `MemoryStatus` 두 번째 literal

"이전 version과 source 보존"을 어떻게 실체화하는가.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. append-only 새 row + supersedes 링크 + `superseded` status | update/add_evidence 시 새 `MemoryEntry`(version=prev+1, `supersedes=prev.id`) 삽입, 이전 entry `status→superseded`. canonical은 항상 최신 1개 | 이전 version 불변 보존(감사), prior_memory canonical-only 필터가 superseded 자연 제외(O1 폐쇄), Phase 3/4 append-only 정신과 정합 | row 증가 |
| B. 최신 row in-place mutate + 별도 version 이력 collection | canonical row는 최신값으로 갱신, 이전 값은 history collection | canonical 조회 단순 | 최신 row mutate가 "덮어쓰기 금지" 경계와 미묘, 이력/본문 이원화 |

추천: **A.** taxonomy "덮어쓰기 금지·이전 version 보존"에 가장 직접 부합하고, canonical-only prior 필터가 superseded를 자동 제외해 2B.2 O1을 자연스럽게 닫는다. `MemoryStatus.SUPERSEDED` 도입 + `MemoryEntry`에 `supersedes: str | None` 필드 추가.

### D3. update vs add_evidence 쓰기 의미 (payload/source/confidence)

두 action이 새 version에서 무엇을 바꾸는가. 추측 금지 대상.

| 필드 | `update` | `add_evidence` |
|---|---|---|
| payload | candidate.payload로 교체(값 변화) | 이전 version payload **보존**(값 동일) |
| source_ref_ids | union(prev, candidate) 또는 candidate | union(prev, candidate) — 근거 추가가 핵심 |
| confidence | candidate.confidence | max(prev, candidate) 또는 prev 유지 |
| provenance | candidate.provenance | prev 유지 |

추천: **update = payload를 candidate로 교체 + source_ref_ids union + confidence는 candidate값**; **add_evidence = payload 보존(값 동일) + source_ref_ids union + confidence는 max(prev, candidate)**. 근거: taxonomy의 정의("update=값/유효상태 변화", "add_evidence=값 동일·새 원문 근거 추가"). **오너 확인 대상**: confidence 갱신 규칙(candidate값 vs max)과 source_ref_ids가 union인지 교체인지.

### D4. Chroma 재색인 범위 (이 slice 포함 vs 분리) — 헤드라인 긴장 해소

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 재색인 분리(2B.4=version 쓰기만, 2B.5=memory 재색인) | 2B.4는 upsert/version/status/idempotency만. memory→vector 색인은 별도 slice에서 임베딩 대상·collection·트리거 확정 | slice 최소·검증 표면 선명, memory 색인 미존재라 어차피 신규 설계 필요, 4.1→4.2 리듬 | version 쓰기 후 색인 최신화는 후속까지 열림(단, MVP 소비자 아직 memory→vector 없음) |
| B. inline 동기 재색인 | apply 시 memory→vector 즉시 재색인 | version과 index 즉시 일관 | memory 색인 파이프라인 전체를 이 slice에 끌어와 비대(임베딩·collection·guard) |
| C. outbox/worker 재색인(Phase 3B 패턴) | apply가 outbox entry 적재, worker가 재색인 | Phase 3B와 정합·비동기 | outbox schema 확장 + memory 색인 파이프라인 둘 다 이 slice |

추천: **A(분리).** memory→vector 색인이 존재하지 않아 재색인은 어차피 독립 설계(임베딩 대상 payload·collection·트리거)를 요하는 slice 규모다. version 쓰기만으로 온전한 slice이며 CLAUDE.md §2(단순성)에 맞다. 재색인 slice(2B.5)는 Phase 3B outbox/worker 패턴 재사용을 기본 후보로 둔다. **오너 확인 대상**: HANDOFF가 "재색인도 이때"라 묶었으므로, 분리(A)가 오너 의도와 맞는지 반드시 확인.

### D5. apply idempotency

같은 proposal 재적용이 중복 version을 만들지 않아야 한다.

| 선택지 | 설명 |
|---|---|
| A. `(project_id, source_candidate_id)` 기준 | 한 candidate는 최대 1회 반영(2B.1 승격 유일성과 동일 키). 재적용은 idempotent replay |
| B. proposal 서명(candidate_id+action+target+payload_hash) 기준 | 같은 proposal 내용 재적용만 replay |

추천: **A.** 2B.1이 이미 candidate→memory를 `(project_id, source_candidate_id)`로 유일화한다. compare도 candidate 단위라 "한 candidate=한 반영"이 자연스럽고 replay가 단순하다. update/add_evidence가 만든 새 version도 그 version을 만든 source candidate로 유일화한다. **오너 확인 대상**: 같은 target memory에 서로 다른 candidate가 순차 update하는 경우(정상 version 체인)와 같은 candidate 재적용(replay)을 이 키가 정확히 가르는지.

### D6. HTTP surface

| 선택지 | 설명 |
|---|---|
| A. `POST /projects/{id}/analysis/jobs/{job_id}/apply` | job의 proposal들을 받아 결정적 반영, 반영 결과(적용/스킵/충돌) 요약 반환. compare(`.../compare`)와 대칭 |
| B. per-proposal endpoint | proposal 단위 apply |
| C. service 표면만 | HTTP는 review 통합 slice에서 |

추천: **A.** 2B.2 `.../context`, 2B.3 `.../compare`가 job 단위 대칭이니 `.../apply`도 job 단위가 자연스럽고 TDD에 유리. 응답에 action별 결과(created/versioned/no_change/conflict-skipped) 요약.

### D7. conflict / merge / split 처리 (자동 금지 확인)

taxonomy는 conflict "자동 처리 가능한가?"를 유형별 미결로 뒀고, AI 경계는 자동 merge를 금지한다.

| 선택지 | 설명 |
|---|---|
| A. 이 slice에서 전부 review-only(쓰기 없음), apply 응답에 skipped로 표면화 | conflict/merge/split은 반영 안 하고 결과에 "review 필요"로 반환. review queue 영속화는 후속 |
| B. review queue 영속화까지 | conflict를 review collection에 적재 |

추천: **A.** AI 직접 실행 금지 경계 유지, review queue 영속화는 별도 slice. 2B.4는 안전 action만 결정적 반영하고 conflict/merge/split은 skipped로 반환한다.

## 후속 (이 브리프 범위 밖)

- **2B.5** memory→vector 재색인(임베딩 대상 payload·collection·트리거; Phase 3B outbox/worker 패턴 후보).
- review queue 영속화 + merge/split 실행 경로, event/open_question 의미적 entity resolution(D2 semantic seam), ⑤ Writing canonical 포함, tool-call flat loop compare.
- 2B.3.2 live smoke 실행(sandbox 밖)·판정 경계 회귀 잠금.

## 누적 오너 확인 대상 (2B.1~2B.3에서 이월)

- 2B.1이 scope-key 유일성을 2B.3에 위임한 경계(2B.1은 `source_candidate_id`로만 유일화)가 브리프 의도와 맞는지.
- 2B.3이 event/open_question을 identity 대조 제외(항상 create)로 둔 것이 브리프 의도와 맞는지 — 2B.4에서 event/open_question은 항상 `create`로 반영되어 중복 누적 가능(의미적 resolution 전까지).

## Owner decisions — 2026-07-06

- **D1 = A.** compare와 분리된 명시 apply. 안전 action 4종(create/update/add_evidence/no_change)만 결정적 자동 반영, conflict/merge/split은 review-only(쓰기 없음). 근거: 2B.3 proposal only 계약 유지 + AI 직접 덮어쓰기 금지 경계와 정합.
- **D2 = A.** append-only 새 row + `supersedes` 링크 + `MemoryStatus.SUPERSEDED`. canonical은 항상 최신 1개, 이전 version 불변 보존. prior_memory canonical-only 필터가 superseded를 자연 제외 → 2B.2 O1 폐쇄.
- **D3 = 추천.** `update` = payload를 candidate로 교체 + source_ref_ids union + confidence=candidate값 + provenance=candidate. `add_evidence` = payload 보존(값 동일) + source_ref_ids union + confidence=max(prev, candidate) + provenance=prev.
- **D4 = A.** memory→vector 재색인은 분리(2B.5). 2B.4는 versioned upsert/version/status/idempotency만. memory 색인 자체가 미존재라 어차피 독립 설계(임베딩 대상·collection·트리거) 필요. 오너가 분리를 확정.
- **D5 = A.** `(project_id, source_candidate_id)` idempotency. 한 candidate=한 반영, 재적용은 idempotent replay. update/add_evidence의 새 version도 그것을 만든 source candidate로 유일화.
- **D6 = A.** `POST /projects/{id}/analysis/jobs/{job_id}/apply`. action별 반영 결과(created/versioned/no_change/conflict-skipped) 요약 반환.
- **D7 = A.** conflict/merge/split은 이 slice에서 review-only(쓰기 없음), apply 응답에 skipped로 표면화. review queue 영속화는 후속. (구현 주: `merge`/`split`은 2B.3가 산출하지 않아 `CompareAction` enum에도 없으므로 apply에 실제 도달하는 review-only action은 `conflict` 하나뿐이다. `merge`/`split`을 body로 보내면 unknown action → 400.)

## 결정 요약 (추천)

| 결정 | 추천 | 핵심 |
|---|---|---|
| D1 | A | compare와 분리된 명시 apply, 안전 action 4종만 자동 |
| D2 | A | append-only 새 row + `supersedes` + `superseded` status(O1 폐쇄) |
| D3 | update=payload 교체·source union·conf=candidate / add_evidence=payload 보존·source union·conf=max | taxonomy 정의 기반, 세부 오너 확인 |
| D4 | A | 재색인 분리(2B.4=version 쓰기, 2B.5=memory 재색인) — **오너 의도 확인 필수** |
| D5 | A | `(project_id, source_candidate_id)` idempotency |
| D6 | A | `POST .../jobs/{job_id}/apply` |
| D7 | A | conflict/merge/split review-only(쓰기 없음, skipped 반환) |
