# Decision brief — Phase 4 shared in-process vector index

상태: `Approved (2026-07-05)`
정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md), [`04-agentic-search-kickoff-decisions.md`](04-agentic-search-kickoff-decisions.md), [`04-agentic-search.md`](04-agentic-search.md)
목적: rebuild가 채운 파생 vector index를 같은 프로세스의 context search가 실제로 조회하도록 `create_app` 안에서 단일 in-process vector index를 공유한다. 이는 Phase 3A/4의 "fake vector adapter는 request마다 throwaway·비지속" 특성을 프로세스 수명 공유로 바꾸는 **비persistence 계약 변경**이라 착수 전 결정을 확정한다.

## 배경 (결정이 아니라 사실)

- 현재 rebuild HTTP endpoint(`POST /projects/{id}/snapshots/{sid}/index/source-blocks/rebuild`)는 `rebuild_source_block_index_summary()`가 호출마다 **새 throwaway** `InMemoryVectorIndexAdapter`를 만들어 쓰고 버린다(`services/application/app/indexing/service.py`).
- context search 기본 wiring(`_default_context_search_service`)은 **별도의** `InMemoryVectorIndexAdapter`를 만든다(`services/application/app/main.py`). rebuild가 이 인스턴스를 채우지 않는다.
- 두 인스턴스가 공유되지 않아서, 배포 환경에서 `source_quote` 등 vector need는 항상 empty hit이고 Mongo-direct need(`current_scene`/`recent_scenes`)만 서빙된다(Slice 4.3 검증에서 실증).
- `validate_source_block_record(record)` stale guard와 SOT 재조회는 이미 query 계층에 있어, index hit는 정본 재확인 전까지 결과에 들어가지 않는다(Slice 4.1).
- 실제 ChromaDB/Elasticsearch persistent backend와 embedding model 선택은 핵심 코어 이후 최후속이다(2026-07-02 오너 결정). 이 slice는 그 최후속을 앞당기지 않는다 — 여전히 deterministic fake adapter다.

## Owner decisions — 2026-07-05

- **방향: 공유 in-process vector index를 채택한다(옵션 A).** real Chroma/ES persistent backend(옵션 B)와 prior-memory purpose(§8 C, 옵션 C)는 계속 후속이다.
- **rebuild HTTP summary는 기존 계약을 유지한다(snapshot scope).** 공유 index가 여러 snapshot rebuild를 누적하더라도 summary count 필드(`records_indexed`/`records_query_visible`/`records_archived`)는 **해당 rebuild의 `snapshot_id`로 scope**해 per-rebuild 의미를 그대로 둔다. v1.6.23 rebuild summary 계약과 Slice 4.3가 잠근 "누적 없음" 회귀는 불변이다. index 누적은 뒤에서만 일어난다.

## 확정 계약

1. **공유 인스턴스**: `create_app`이 단일 `InMemoryVectorIndexAdapter`(+ `DeterministicFakeEmbeddingProvider`)를 소유한다. rebuild endpoint는 여기에 write하고, context search 기본 wiring은 여기서 read한다. 두 표면이 같은 records store를 본다.
2. **비persistence 의미**: 공유 index는 프로세스 수명 in-memory이며 **비durable**이다 — 재시작하면 사라진다. 외부 backend/영속 계층이 아니다. `backend` literal은 여전히 `in_memory_fake`다. 여러 project는 기존 `project_id` 필터로 격리된다(계약 변경 없음).
3. **rebuild summary 불변**: summary count는 snapshot scope per-rebuild 의미를 유지한다. throwaway 경로(CLI script)에서는 adapter가 이미 해당 snapshot만 담으므로 snapshot scope가 기존 값과 동일하고, 공유 경로에서도 같은 값을 낸다. rebuild HTTP 계약(v1.6.23)과 CLI script 계약(v1.6.22)은 그대로다.
4. **planner env와의 독립성**: 공유 vector index는 `LLM_GATEWAY_BASE_URL` 유무와 무관하게 `create_app`에서 항상 생성되고 rebuild가 채운다. context search planner wiring은 종전대로 env가 있을 때만 붙고, 없으면 `/context-search`는 503이다. 즉 planner 미구성 상태에서도 rebuild는 정상 동작하고 index를 채운다.
5. **staleness 안전성**: 공유·누적은 archive/drift 안전성을 해치지 않는다. context search는 hit마다 `validate_source_block_record()` stale guard + SOT 재조회를 거치므로, rebuild 후 archive되거나 content가 drift한 record는 결과에서 제외된다(Slice 4.1 회귀가 이미 잠금). 공유 adapter는 fake archive mutation을 받지 않지만, query-time 재검증이 방어선이다.
6. **테스트 seam**: `create_app`에 공유 adapter 주입 param을 열어, rebuild와 context search가 같은 adapter를 보는 것을 fake planner로 app 레벨에서 검증할 수 있게 한다.

## 수용 기준

- 같은 app 인스턴스에서 snapshot rebuild → 그 draft 위치로 context search를 하면, `source_quote` 등 vector need가 stale guard + SOT 재조회를 통과한 실제 vector hit(micro item)를 반환한다.
- rebuild HTTP summary의 count 필드는 두 번째 snapshot을 rebuild한 뒤에도 per-rebuild(snapshot scope) 값을 유지한다 — 누적 없음 회귀 불변.
- rebuild 후 draft/project archive 시 해당 record는 context search 결과에서 제외된다(stale guard).
- 새 `create_app` 인스턴스의 공유 index는 비어 있다(재시작=index 소실).

## 후속 (이 slice 범위 밖)

- real ChromaDB persistent vector adapter / ES lexical 경로(§8, 착수 전 별도 브리프).
- prior-memory(analysis 비교) purpose §8 C 완성(Phase 2B 착수 브리프에서 필드 확정).
- tool-call flat loop planner 전환(§2.1, 상류 wire 계약 해소 후).
