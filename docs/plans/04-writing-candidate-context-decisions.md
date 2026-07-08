# ⑤ §5 B 후속 — `needs_review` candidate의 Writing 포함 착수 결정 브리프

상태: `Resolved` (2026-07-08 오너 결정)

## 오너 결정 (2026-07-08)

- **D1=A**, **D2=A**, **D3=A**, **D5=A**, **D6=A**, **D7=A** (추천값 잠금).
- **D4=B**: 지금 `ContextItem.review_status` 필드를 신설한다(현재 `needs_review` 고정, Phase 6이 confirmed/rejected 도입 시 확장). candidate origin item만 의미 있고 canonical/source-block item은 비어 있다(inert).
- **안전선=A**: Phase 6 §62(승인 전 candidate의 canonical 위장 금지)를 candidate `status=candidate` 명시 라벨 + `micro_evidence`에만 배치 + `constraints`/`do_not_use`(권위 필드) 배제로 지키며 포함한다. Gate는 candidate step origin만 허용하고 다른 need의 candidate-status는 전역 금지 유지(반전 아님).

## 구현 중 정정 (CLAUDE.md §1)

- **D5 문구 정정 — "승격된 candidate가 set을 떠난다"는 아직 참이 아님**: `needs_review→confirmed/rejected` 상태 전이는 Phase 6(`06-review-ui.md` "confirmed 승격과 rejected 처리")다. 현재 시스템에서 2B.1 승격은 canonical `MemoryEntry`를 mint하지만 원본 candidate 상태는 건드리지 않으므로, 승격된 지식은 canonical 경로(승인)와 candidate 경로(여전히 needs_review) 양쪽에 나타날 수 있다 — 이는 **D7=A(dedup 안 함)** 케이스로 수용한다(각자 다른 라벨). retrieval은 D5대로 `needs_review`만 리스팅한다(정확). Gate의 `status≠needs_review→stale` 분기는 Phase 6이 confirmed/rejected를 도입할 때 도달 가능해지는 **forward-defense**이며, 회귀는 stub 상태로 실증했다.
- **v1.6.48 candidate 금지 계약 보존**: Gate 재편은 전역 candidate 금지를 없애는 게 아니라 "candidate origin(`analysis_candidates`)만 예외"로 **좁혔다**. memory/source-block origin의 candidate-status는 여전히 `candidate_item_not_allowed`(v1.6.48 `test_candidate_status_memory_item_still_rejected` 무변 통과 + 신규 over-strict 회귀).

---

(원 브리프 — 참고)

상태: `Discussion` (오너 결정 대기)
관련: SoT v1.6.48(⑤ Writing canonical 포함), v1.6.38(candidate 포함 Phase 2B 종속 D1=B), Phase 6 `06-review-ui.md`
선행 slice: `04-writing-canonical-context-decisions.md`(Resolved, D1=A canonical만)

## 배경

v1.6.48이 Writing ContextPackage에 **canonical** memory를 포함하며 machinery를 세웠다: `CanonicalMemoryRetriever` seam → `_run_canonical_memory_step` → `_item_from_memory`(memory→`ContextItem`) → `evaluate_context_gate`의 origin별(`pointer.collection`) 재검증 분기. v1.6.48은 candidate 포함을 "이 machinery를 재사용하는 **바로 다음 slice**"로 명시하고 candidate 금지는 유지했다.

이 slice는 그 다음 slice다: `needs_review` candidate를 Writing package에 **micro·라벨 필수**로 포함한다.

## 헤드라인 긴장 (CLAUDE.md §1 — 임의 구현 없이 surface)

1. **Writing 안전선 완화의 근거 (v1.6.38 D1=B ↔ 지금)**
   v1.6.38이 candidate 포함을 미룬 근본 이유는 "canonical store·승인 경로가 없는 상태의 '지금 포함'은 미검증 후보를 Writing 근거로 흘려보내는 것이라 `evaluate_context_gate`의 candidate 라벨 금지(Writing-안전성 방어선)를 **근거 없이** 완화한다"였다. Phase 2B(2B.1 승격 경로 + canonical store)가 이 종속을 해소했다. 이제 완화의 근거가 생겼으나, **Phase 6 §62의 불변식**이 걸린다: *"승인 전 candidate가 canonical UI와 검색 constraint로 위장되지 않는다."* 따라서 candidate 포함은 반드시 (a) `status=candidate`로 명시 라벨, (b) canonical과 구분되는 자리에, (c) 권위 필드(`constraints`/`do_not_use`)에 **넣지 않음**을 만족해야 한다. 이 slice는 "라벨을 정확히 실어 보내는 것"까지 책임지고, 소비자가 그 라벨을 존중하도록 강제하는 것은 Writing generation prompt 계약(Phase 5)/review(Phase 6)의 몫이다.

2. **Gate candidate 금지의 정확한 반전 범위**
   현재 `evaluate_context_gate`는 `item.status is CANDIDATE → candidate_item_not_allowed`로 **전역** 거부한다(canonical만 허용하는 Writing-안전선). 이걸 통째로 여는 게 아니라, **candidate step을 통해 들어온 candidate만** 허용하고 다른 need(canonical 등)에서 새어든 candidate-status는 여전히 금지해야 한다. origin 구분자는 canonical과 동형: `pointer.collection == "analysis_candidates"`.

## 결정 항목

### D1 — candidate need 신설 + 배치 (추천: A)
- **A(추천)**: 신설 `ContextNeed.CANDIDATE_MEMORY`(`NEED_ALLOWED_TOOLS`=(mongo,), `MACRO_NEEDS` 미포함 = micro). canonical(`CANONICAL_MEMORY`)과 대칭. candidate item은 `micro_evidence`에만 들어가고 macro/constraints/do_not_use에는 절대 안 들어간다(§62).
- B: 기존 need에 얹기 — 거부(canonical과 라벨·Gate 자세가 달라 origin 분기가 흐려짐).

### D2 — retrieval 레이어 (추천: A, canonical D2=A 대칭)
- **A(추천)**: `CandidateMemoryRetriever` seam + `MongoDirectCandidateMemoryRetriever`(project-wide `needs_review` candidate 리스팅, limit, query 무시=랭킹 후속). 새 서비스/repo 메서드 필요 — 현재 `list_candidates_for_job`(job별)만 있고 project-wide `needs_review` 리스팅이 없다. retrieval 레이어와 권위 재유도(항상 analysis store 재검증)를 분리해 후속에서 vector/ES 교체 가능.
- B: vector 먼저 — 거부(랭킹 인프라 미검증, canonical 선례가 Mongo-direct 먼저).

### D3 — Gate 반전 범위 + candidate 재검증 (추천: A)
- **A(추천)**: candidate item은 origin이 `pointer.collection=="analysis_candidates"`일 때만 허용. `_gate_candidate_findings`가 analysis store `get_candidate`로 (존재 + `status is NEEDS_REVIEW` + project) 재검증 → 없거나 상태가 바뀌었으면(예: 이미 canonical 승격/reject) `stale_item`. analysis service 미주입이면 `candidate_gate_unconfigured`. **다른 need에서 온 candidate-status는 종전대로 `candidate_item_not_allowed` 유지**(전역 금지 반전 아님). canonical의 `_gate_memory_findings`와 완전 대칭.

### D4 — 라벨/소비 계약 (Phase 6 review 지위) — **오너 결정 필요** (v1.6.48 명시)
- **A(추천, minimal)**: 기존 `ContextItemStatus.CANDIDATE`를 유일 라벨로 사용. Phase 6이 `confirmed`/`rejected` 상태를 도입할 때 `review_status` 같은 필드를 추가한다(현재 candidate 상태는 `needs_review` 하나뿐이라 지금 여는 필드는 값이 1종뿐 = 정보 없음). 소비 강제는 Phase 5 prompt/Phase 6.
- B(forward-compat): 지금 `ContextItem`에 `review_status`(현재 `needs_review` 고정) 필드를 신설해 소비자 계약을 미리 연다. 비용: 값 1종 필드를 미리 여는 것(2A `needs_review` 고정 선례와 유사한 추측).

### D5 — 어느 candidate (추천: A)
- **A(추천)**: `needs_review`만. 이미 canonical 승격된 것은 canonical 경로가 서빙하므로 제외(중복·위장 회피).

### D6 — item 변환 (추천: A, canonical `_item_from_memory` 대칭)
- **A(추천)**: `_item_from_candidate`가 `derive_memory_index_text(candidate_type, payload)` **재사용**(candidate payload는 memory와 동일 taxonomy 필드). `ContextItem`(status=CANDIDATE, pointer.collection=`analysis_candidates`·document_id=candidate_id·version_id=""·content_hash="", snapshot_id=""·sot_reloaded=True inert placeholder는 canonical과 동일 문서화). retriever 미주입 시 빈 step(무실패), retriever 예외 → `BACKEND_ERROR` step failure(canonical cell #10 선례).

### D7 — canonical ↔ candidate 중복 (추천: A)
- **A(추천)**: 이 slice에서 dedup 안 함. 같은 지식이 canonical·candidate 양쪽에 있으면 둘 다 각자 라벨로 실린다(소비자가 status로 구분). semantic dedup은 후속.

## 검증 계획 (구현 시)
- 신규 `tests/test_context_search_candidate_memory.py`: candidate가 micro 배치 + candidate pointer(macro/constraints/do_not_use 빈), retriever 미주입→빈 무실패, retriever needs_review-only + limit, **Gate 4방향**(needs_review pass / 승격되어 status≠needs_review → stale under-strict / missing → stale / analysis 미주입 → unconfigured), **다른 need의 candidate-status는 여전히 candidate_item_not_allowed**(전역 금지 반전 아님 over-strict), retriever 예외→BACKEND_ERROR 격리(canonical cell #10 대칭). Gate·retriever guard mutation 양방향 재실증.
- §62 불변식 lock: candidate item이 macro/constraints/do_not_use에 **절대** 안 들어감을 직접 assert(over-strict).

## 범위 밖
- vector/ES relevance retrieval(D2 후속), semantic canonical↔candidate dedup(D7 후속), review_status 다중 상태(Phase 6), Writing generation의 candidate 소비 강제(Phase 5).
