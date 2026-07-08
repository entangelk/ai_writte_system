# 착수 결정 브리프 — Writing canonical memory retrieval의 ES lexical 확장 (⑤ §5 B / §8)

**상태**: `Resolved` (2026-07-08 오너 결정)

## 오너 결정 (2026-07-08)

- **E0/E1 = A**: ES 색인 파이프라인(outbox `targets.elasticsearch` + worker ES drain + ES 색인 adapter) **+** `LexicalCanonicalMemoryRetriever`를 한 slice로. outbox는 기존 골격 확장(v1.6.25/26이 남긴 "actual Elasticsearch mutation" 자리).
- **E2 = A**: lexical retriever는 vector와 대칭(ES query→hit metadata의 mongo_id→`get_memory` 권위 재유도→canonical-only).
- **E3 = hybrid(RRF) 지금** *(추천 A 대신 오너가 상향)*: vector(v1.6.51) + lexical을 **RRF(Reciprocal Rank Fusion)로 결합**한 `HybridCanonicalMemoryRetriever`가 canonical retriever가 된다. 각 sub-retriever의 순위 리스트를 RRF로 융합 후 권위 재유도. 단일 backend만 구성되면 그 backend 단독(hybrid는 둘 다 있을 때).
- **E4 = A**: ES 문서 = `{mongo_id, mongo_collection="memory_entries", mongo_version, project_id, memory_type, status, text(nori 분석)}`. 정본 아님(재유도 전제).
- **E5 = A**: fake 회귀 + **실 ES live smoke를 이 slice에서 작성·실행**(컨테이너 가용). `ai_writte_smoke_*` 네임스페이스 ephemeral.
- **E6 = A**: `create_app`의 canonical retriever 배선을 확장 — vector/lexical/hybrid/Mongo-direct를 env로 선택.

---

(원 브리프 — 참고)

**상태**: `Discussion` (오너 결정 대기)
**정본 SoT**: `docs/system-contract-sot.md` (현재 v1.6.51)
**선행 브리프**: `04-writing-memory-vector-retrieval-decisions.md`(Resolved, D5=A로 "ES lexical §8은 범위 밖 별도 브리프"로 위임), `04-writing-canonical-context-decisions.md`(D2=A "retrieval 교체·권위 재유도 불변").
**아이디에이션 근거**: `docs/agentic_search_flow.md`(⑤ retrieval flow), `docs/contracts.md` §1.3(ES = lexical/metadata index), SoT 아키텍처 표(`system-contract-sot.md:129`).

---

## 왜 지금 열리나

v1.6.51이 canonical retrieval의 **vector leg**를 완성하며 seam(`.retrieve(project_id, query, limit) → tuple[MemoryEntry, ...]`)이 순수 주입 교체점임을 실증했다. ES lexical은 그 **두 번째 retrieval backend**다: BM25/nori 어휘 매칭으로 id를 찾고, MongoDB memory store로 권위 재유도(vector와 동일). 아이디에이션은 ES를 "canonical memory의 lexical/metadata 검색 인덱스"로 규정하고 한국어 lexical(nori)을 명시한다.

## 현재 확정된 경계 (사실 — 코드·인프라 재확인)

- **seam은 v1.6.51이 검증한 주입 교체점이다.** `_run_canonical_memory_step`은 주입된 retriever의 `.retrieve()`만 호출하고 step/item/Gate는 retriever-무관. lexical retriever도 같은 시그니처면 step/item/Gate **무변경**.
- **권위 재유도 계약은 이미 있다.** contracts.md §80-82: "ChromaDB/Elasticsearch에서 온 데이터는 grounding 전 MongoDB 재조회 필수." → lexical hit도 `get_memory` 재유도 + `status is CANONICAL` 필터(vector와 동일 방어선 + Gate 최종 재검증).
- **⚠ ES 인덱스가 없다(핵심 선행 의존).** memory_vectors(Chroma)는 canonical memory의 vector 인덱스지만, ES에는 canonical memory 인덱스가 **전무**하다. lexical retrieval을 하려면 canonical memory를 ES에 색인하는 파이프라인이 **선행**돼야 한다 — candidate vector가 색인 부재로 막혔던 것과 같은 구조.
- **outbox/worker 골격은 이미 있다.** `IndexSyncOutboxEntry`는 `targets.chroma`(status/backend)를 가지고, worker가 memory reindex를 Chroma memory_vectors로 drain한다(2B.5). v1.6.25/26이 "actual Elasticsearch mutation"을 **명시적 후속**으로 남겼다. → ES 색인은 outbox에 `targets.elasticsearch`를 더하는 확장 형태가 자연스럽다.
- **`SearchTool` enum에 lexical/ES 리터럴이 없다.** 현재 `VECTOR`/`MONGO`뿐. 단 memory need는 need로 dispatch(tool 무관)하므로 v1.6.51처럼 tool 리터럴 없이 배포 배선으로 backend를 고를 수 있다.
- **테스트용 ES 컨테이너가 실제로 가용하다(실측함).** 이 머신에 `tf-ai-harness-elasticsearch-step1`(**ES 8.13.4, 인증 없음, analysis-nori 설치됨**, host 포트 **9201**)가 떠 있다. 기존 인덱스는 `tf_ai_harness_*` 네임스페이스라 `ai_writte_*` 계열로 충돌 없이 쓸 수 있다. **단 다른 프로젝트와 공유하는 컨테이너**라 테스트는 명시 네임스페이스 + ephemeral(생성→검증→삭제) 취급해야 한다.

---

## ⚠ 헤드라인 긴장 (임의 구현 없이 surface — CLAUDE.md §1)

### 긴장 1 — ES 색인 파이프라인이 선행 의존이다 (slice 크기)
lexical retrieval 자체는 v1.6.51처럼 작은 주입 교체지만, 그 앞에 **canonical memory → ES 색인 파이프라인**(outbox target 확장 + worker drain + ES 색인 adapter + 문서 매핑)이 필요하다. 이건 2B.5(memory→Chroma) 규모다. 한 slice에 다 넣으면 비대해진다. → E0에서 "색인 파이프라인 + 최소 lexical retriever"를 한 slice로 묶을지, 파이프라인을 선행 slice로 분리할지 결정한다.

### 긴장 2 — lexical과 vector를 어떻게 결합하나 (hybrid vs 대체)
canonical retriever는 현재 **단일 주입점**이다(vector 또는 Mongo-direct 택1). lexical을 더하면 "vector·lexical 동시 사용(hybrid: score fusion/RRF)"인지 "배포가 하나를 택"인지 결정해야 한다. hybrid는 아이디에이션(agentic_search_flow.md:905-908 need별 primary/secondary retriever)과 맞지만 score 정규화·중복 병합 설계가 커진다. MVP는 "선택 가능한 별개 retriever"가 v1.6.51 리듬과 맞다(hybrid는 후속).

### 긴장 3 — 실 ES를 이 slice에서 관통할지 (컨테이너가 sandbox 안에 있음)
Chroma leg(v1.6.51)는 fake-first·실 관통 sandbox 밖이었다. 그러나 ES 컨테이너는 **이 sandbox에서 접근 가능**하다. → 실 ES 관통(색인+nori query+삭제)을 이 slice에서 할지(회귀 가치 큼, 단 공유 컨테이너 의존), 아니면 fake-first 유지하고 실 관통은 live smoke로 둘지 결정(E5).

---

## 결정 필요 항목

### E0 — slice 경계 [헤드라인 1]
- **A(추천)**: 이 slice = ES 색인 파이프라인(outbox `targets.elasticsearch` + worker drain + ES memory 색인 adapter) **+** `LexicalCanonicalMemoryRetriever`(최소). candidate·hybrid 제외. 파이프라인과 retriever가 한 쌍이라야 end-to-end 검증 가능.
- B: 파이프라인만 먼저(retriever는 다음 slice) — 검증 대상(소비처)이 없어 무의미(canonical vector 브리프의 "Gate 라벨만 열기" 반례와 동일).
- C: retriever만(색인은 수동/후속) — 색인 없으면 lexical hit이 항상 빔.
- 추천: **A**.

### E1 — ES 색인 파이프라인 형태 [헤드라인 1]
- **A(추천)**: 기존 `IndexSyncOutboxEntry`에 `targets.elasticsearch`(status/backend) 추가, worker의 memory reindex drain이 Chroma와 **병렬로** ES 색인도 수행(v1.6.25/26이 남긴 "actual Elasticsearch mutation" 자리). enqueue는 기존 `MemoryService` choke point 재사용(2B.5 선례).
- B: 별도 ES 전용 outbox/worker — 중복. 거부.
- 추천: **A** — canonical memory 색인 트리거(promote/versioned upsert)를 Chroma와 공유.

### E2 — lexical retriever [헤드라인 2 역]
- **A(추천)**: `LexicalCanonicalMemoryRetriever`가 (1) ES에 nori 분석 BM25 query(query text), (2) hit metadata에서 `mongo_id`(+collection/version) 확보, (3) `get_memory` 권위 재유도, (4) `status is CANONICAL`만 반환. vector `VectorCanonicalMemoryRetriever`와 **완전 대칭**(embed→query_similar 자리에 ES query가 들어감). seam·반환 타입 불변 → step/item/Gate 무변경.

### E3 — lexical + vector 결합 [헤드라인 2]
- **A(추천, MVP)**: 결합 안 함. 배포 배선이 vector·lexical·Mongo-direct 중 하나를 canonical retriever로 주입(v1.6.51 env 배선 확장). hybrid는 후속.
- B: hybrid(RRF/score fusion) 지금 — score 정규화·병합 설계로 slice 확대. 후속.
- 추천: **A**.

### E4 — ES 문서 매핑
- **A(추천)**: `{ mongo_id, mongo_collection="memory_entries", mongo_version, project_id, memory_type, status, text(nori 분석 필드) }`. 검색은 text(nori) + project_id/memory_type/status 필터. 정본 아님(contracts.md §140) — 재유도 전제.
- nori analyzer 매핑 필수(한국어 형태소, contracts.md:131 + 컨테이너 nori 확인).

### E5 — 실 ES 관통 범위 [헤드라인 3]
- **A(추천, fake-first + 실 live smoke)**: 회귀는 in-memory fake lexical adapter(결정적). 실 ES adapter는 env(`ELASTICSEARCH_URL`)로 배선. **실 관통 live smoke를 이 slice에서 작성·실행**(컨테이너 가용 — 색인→nori query→재유도→삭제, `ai_writte_smoke_*` 네임스페이스 ephemeral). Chroma leg와 달리 sandbox 안에서 실 검증까지 닫을 수 있음.
- B: fake-only(실 관통 전부 후속) — 컨테이너가 있는데 미룰 이유 약함.
- 추천: **A** — 단 공유 컨테이너라 smoke는 명시 네임스페이스 + 생성/삭제 격리.

### E6 — 배포 배선
- **A(추천)**: `create_app`의 `_build_canonical_memory_retriever`를 확장 — `ELASTICSEARCH_URL` 있으면 lexical, 아니면 기존(vector/ Mongo-direct) 우선순위. tool 리터럴은 `mongo` 유지(need dispatch).

---

## 제안 slice 범위 (추천값 기준)
**포함**: outbox `targets.elasticsearch` + worker ES memory drain + ES 색인 adapter(fake+real) + `LexicalCanonicalMemoryRetriever` + nori 매핑 + fake 회귀 + 실 ES live smoke(컨테이너).
**제외(후속)**: candidate lexical, vector+lexical hybrid(RRF), lexical을 primary로 쓰는 need별 라우팅(아이디에이션 905-908), compose에 전용 ES 서비스 추가(테스트는 기존 컨테이너, 배포 ES는 별도).

## 검증 계획 (구현 시)
- fake 회귀(신규 `tests/test_context_search_memory_lexical_retrieval.py`): 권위 재유도(ES hit id→`get_memory`, 문서 text 아님)·canonical-only(superseded/deleted 격리, 양방향)·seam 불변(lexical retriever→step→micro memory item)·query가 ES query에 전달됨 lock(v1.6.51 #4 대칭). worker ES drain: canonical 색인/ superseded 삭제(2B.5 대칭 회귀).
- 실 ES live smoke(`scripts/…_lexical_live_smoke.py`): `ELASTICSEARCH_URL` 실 컨테이너에 nori 인덱스 생성→canonical memory 색인→한국어 query 매칭→`get_memory` 재유도→ephemeral 인덱스 삭제.
- mutation 양방향: canonical 필터 무력화(under-strict), query 무시 하드코드(under-strict).

## 열린 질문 (오너에게)
1. **E0/E1**: ES 색인 파이프라인(outbox `targets.elasticsearch` + worker drain)을 이 slice에 함께 넣는 데 동의하는가(A), 아니면 파이프라인을 선행 slice로 더 쪼갤까?
2. **E3**: MVP는 vector·lexical을 결합 않고 배포가 택1(A)로 가고 hybrid는 후속으로 미루는 데 동의하는가?
3. **E5**: 컨테이너가 가용하니 실 ES live smoke를 이 slice에서 닫을까(A), fake-only로 두고 실 관통은 후속(B)?
