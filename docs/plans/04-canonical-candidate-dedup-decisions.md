# 착수 결정 브리프 — canonical↔candidate 승격 dedup ((e), v1.6.50 D7 후속)

상태: `Resolved`
관련: HANDOFF Next Tasks #1 (e) · v1.6.50 D7(no-dedup 수용) · D5=A(승격 candidate는 canonical 경로로 서빙) · Phase 6 candidate 상태 전이

## 문제

v1.6.50 D7은 "같은 지식이 **승격 후** canonical·candidate 양쪽에 노출"되는 것을 수용된 한계로 남겼다. 원인은 결정적이다:

- 승격 시 canonical `MemoryEntry.source_candidate_id = candidate.id`가 박히고
  (`memory/service.py:167`), memory store는 `find_memory_by_candidate(project_id, candidate_id)`로
  승격 여부를 결정적으로 조회할 수 있다(`memory/mongo_repository.py:77` · `InMemoryMemoryRepository:79`).
- 그러나 candidate status는 승격돼도 `needs_review`로 남는다(`needs_review→confirmed` 전이는
  Phase 6). 따라서 candidate retriever(`list_needs_review_candidates`)가 승격된 candidate를
  **계속 반환**하고, context package에 canonical 사본과 candidate 사본이 동시에 실린다.
- `context_search/service.py:349-350`의 D5=A 주석("promoted candidates are served by the
  canonical path instead")은 현재 **aspirational** — status 축으로는 걸러지지 않는다.

즉 이 중복은 embedding/semantic이 아니라 `source_candidate_id` **identity 링크**로 결정적이다.
따라서 라이브 embedding·threshold 캘리브레이션 없이 sandbox 안에서 완결 가능하다.

## 오너 결정

- **D1 = 승격됐으면 항상 억제** (store 권위). candidate가 memory store에 승격 링크를 가지면
  (`find_memory_by_candidate` != None) canonical이 이번 package에 함께 retrieval됐든 아니든
  candidate 노출을 억제한다. "canonical·candidate가 같은 package에 둘 다 있을 때만 dedup"하는
  merge-only 방식은 배제 — D5=A("승격 candidate는 canonical 경로로만 서빙")에 정확히 부합하는
  쪽은 store-authoritative 억제다.
- **D2 = 지금 retrieval-time interim 억제**. context_search 조립 단계(candidate step)에서 additive
  하게 억제한다. 상태 모델·색인 무변. Phase 6에서 `needs_review→confirmed` 전이 + candidate
  de-index가 실경로가 되면, 승격 candidate는 애초에 candidate 색인/retrieval에서 빠져 이 억제는
  자연히 상위집합으로 흡수된다(forward-defense, 현재 stub와 동형).

## 메커니즘 (최소·additive)

- 신규 seam `PromotedCandidateResolver` (structural `Protocol`, `context_search/service.py`):
  `is_candidate_promoted(project_id, candidate_id) -> bool`. `MemoryService`가
  `is_candidate_promoted`(→ `repo.find_memory_by_candidate is not None`)로 구조적 충족.
- `ContextSearchService.__init__`에 optional `promoted_candidate_resolver` 주입.
  **미주입 시 억제 없음**(하위호환 = 종전 D7 동작). 기존 테스트·요청 무영향.
- `_run_candidate_memory_step`: retrieval 후 candidates를 kept/suppressed로 분할.
  suppressed는 `ExcludedHit(record_id=candidate.id, reason="candidate_promoted")`로 trace에 기록
  (hits_considered=전체, items_produced=kept). resolver 예외는 기존 retrieval try/except와 같은
  `backend_error` degrade 경로로 접힌다(정직한 degrade).

## 계약 영향

- public 응답 envelope literal 무변(억제는 candidate가 애초에 package에 안 실리는 것). trace의
  `ExcludedHit.reason` 문자열 `"candidate_promoted"`가 신규(내부 trace, schema/gate 대상 아님).
- 신규 `MemoryService.is_candidate_promoted` public 메서드(얇은 조회 위임).
- SoT v1.6.60 bump(새 seam + 동작 확장; 기존 literal 무변경, D7 posture를 "no-dedup 수용"→
  "승격 identity dedup"으로 좁힘).

## 경계 매트릭스 (회귀 잠금)

| 분기 | 방향 | 잠금 |
|---|---|---|
| 승격 candidate → 억제 + trace excluded(candidate_promoted) | under-strict | 억제 제거 시 재실패 |
| 비승격 needs_review candidate → 유지 | over-strict | 정상 candidate가 잘못 억제되면 실패 |
| resolver 미주입 → 억제 없음(하위호환) | over-strict | 종전 D7 동작 보존 |
| 혼합(c1 승격·c2 비승격) → c2만 kept, c1 excluded | 양방향 | 부분 억제 정확성 |
| resolver 예외 → backend_error degrade | 안전 | 정직한 degrade |
