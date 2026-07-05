# Decision brief — Phase 4 real persistent vector backend (Chroma)

상태: `Approved (2026-07-05)`
정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md), [`04-agentic-search.md`](04-agentic-search.md), [`03-indexing-kickoff-decisions.md`](03-indexing-kickoff-decisions.md), [`04-shared-vector-index-decisions.md`](04-shared-vector-index-decisions.md)
목적: 현재 검색 가능한 파생 index(in-memory fake vector)를 real 영속 vector 백엔드로 올리는 첫 slice가 backend 종류, embedding 방식, 인프라 실행, 테스트 전략, 계약 표면을 추측하지 않도록 MVP 범위를 좁힌다. HANDOFF Next Tasks 1의 후보 B에 해당한다.

## Owner decisions — 2026-07-05 (approved)

- **§1 타이밍: A(지금 앞당김).** 2026-07-02 "real 백엔드/embedding model = 코어 이후 최후속" 결정을 갱신한다. 근거: 이 작업은 LLM 게이트와 무관해 2-환경(하나는 LLM 미가용) 제약과 맞고, vector need 영속화 이득을 조기 확보한다.
- **§2 첫 백엔드: A(Chroma persistent vector만).** ES lexical은 후속.
- **§3 embedding: B(real local embedding model 즉시).** 모델은 **`dragonkue/BGE-m3-ko`**(HuggingFace) — bi-encoder embedding model, **1024-dim dense vector**, sentence-transformers 구동, `BAAI/bge-m3`의 한국어 파인튜닝. (오너가 처음 링크한 `dragonkue/bge-reranker-v2-m3-ko`는 cross-encoder reranker라 embedding엔 부적합; `BGE-m3-ko` embedding model로 정정 확정.) reranker는 후속 rerank 단계 후보로 남긴다.
- **§4 인프라: A(전부 컨테이너).** Chroma는 compose 서비스 컨테이너, embedding model도 **별도 embedding 서비스 컨테이너**(llama gateway와 분리 — LLM-독립 유지)로 관리한다. opt-in override가 아니라 base compose에 서비스로 편입한다("다 컨테이너로 관리").
- **§5 테스트: A(skip-aware live Chroma/embedding + fake 단위).** 인프라 미가용 환경은 live만 skip, fake 기반 단위 스위트는 항상 실행.
- **§6 계약 표면:** `backend="chroma"` literal 추가, dimension 1024, stale-guard 불변, worker→Chroma 실제 mutation은 후속.

### 2-환경 제약 반영

embedding을 별도 컨테이너 서비스로 두고 llama gateway와 분리하므로 vector 백엔드 전체가 LLM 게이트와 독립이다. embedding/Chroma 컨테이너가 없는 환경에서는 live 통합 테스트가 skip되고 fake 기반 단위 스위트가 그대로 통과한다.

## 배경 (결정이 아니라 사실)

- 현재 vector index는 `InMemoryVectorIndexAdapter`(process-shared in-process fake, SoT v1.6.35)다. 프로세스 수명 in-memory이고 재시작 시 소실된다. `backend` literal은 `in_memory_fake`(`FAKE_VECTOR_BACKEND`, `IndexSyncTarget.IN_MEMORY_FAKE`)다.
- vector 경로는 이미 Protocol seam 뒤에 있다: `VectorIndexAdapter`(write, `upsert_records` — `services/application/app/indexing/service.py`)와 `VectorSearchAdapter`(read, `query_similar` — `services/application/app/context_search/service.py`). fake는 두 Protocol을 한 클래스로 구현한다. real 백엔드는 이 seam만 교체하면 rebuild/context-search 상류 코드를 안 건드린다.
- outbox target envelope에는 이미 `CHROMA_TARGET = "chroma"` literal이 있고(`targets.chroma.status/backend`), Phase 3B worker는 아직 recording-only fake mutation이다.
- `validate_source_block_record()` stale guard는 backend와 무관하게 Core SOT 정본을 재조회하므로 real 백엔드에서도 그대로 방어선이다.
- 2026-07-02 오너 결정(`03-indexing-kickoff-decisions.md` §2/§3): **실제 ChromaDB/Elasticsearch adapter와 embedding model 선택은 핵심 코어(Phase 5/6 포함) 이후 최후속**이다. 첫 index slice는 fake adapter + fake embedding으로 좁혔다.
- 현재 Python dependency는 `fastapi`, `httpx`, `pymongo`, `uvicorn`뿐이다. `chromadb`는 없다.
- 테스트 스위트(475개)는 LLM 게이트와 무관하다. 44개 skip은 전부 Mongo/pymongo 게이팅이고, LLM은 live smoke 스크립트에서만 탄다. 개발은 2개 환경에서 진행되며 그중 하나는 LLM 게이트를 못 쓸 수 있다.

## 1. 타이밍 — 2026-07-02 "최후속" 결정과의 충돌

2026-07-02 결정은 real 백엔드를 코어 이후로 미뤘다. 지금(Phase 4 중반, Phase 5/6 미구현) B를 하면 그 결정을 앞당기는 것이라 오너 확인이 필요하다.

| 옵션 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A. 지금 앞당김 | 2026-07-02 "최후속"을 갱신하고 real vector 백엔드를 지금 착수 | vector need가 재시작에도 살아남는 이득 조기 확보. 이 작업은 LLM-독립적이라 제약 환경에서도 빌드·테스트 가능 | 코어 완성 전 인프라 하나가 늘어남(운영 표면 증가) |
| B. 후속 유지 | 2026-07-02 결정을 지키고 C(prior-memory)/D(tool-call planner) 중 착수 가능한 것을 함 | 원 결정 준수, 코어에 집중 | vector need는 계속 배포에서 empty(fake). D는 상류 차단, C는 오너가 뒤로 미룸 |

추천: **A**. 근거 — (1) 이 slice는 LLM 게이트와 무관해 2-환경 제약과 정확히 맞고, (2) 앞당김 사유/트레이드오프를 work_log에 기록하면 2026-07-02 결정을 명시적으로 갱신하는 절차가 성립한다. 오너가 A를 승인하면 그 결정과 rationale을 work_log "User Decisions"에 남긴다.

## 2. 첫 백엔드 범위

§8은 vector(Chroma, 의미/분위기/유사 장면)와 lexical(ES, 이름/별칭/고유명사) 두 시스템을 본다. 현재 fake는 vector 경로뿐이다.

| 옵션 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A. Chroma persistent vector만 | fake in-memory vector adapter를 real 영속 Chroma로 교체 | context search의 `source_quote`/vector 경로가 이미 있어 직결. seam 교체만으로 완결 | ES lexical(이름 검색)은 계속 후속 |
| B. Elasticsearch lexical만 | 이름/별칭/고유명사용 ES 경로부터 | 고유명사 검색이 빠름 | 새 retrieval mode라 planner/need 배선 확장 필요. vector 품질은 계속 fake |
| C. Chroma + ES 둘 다 | 두 인프라 동시 도입 | 최종 그림에 가까움 | 첫 slice가 크게 부풀고 두 인프라·두 계약 동시 리스크 |

추천: **A**. 근거 — 현재 seam이 vector 전용이라 교체 비용이 가장 낮고, ES는 planner/need 확장까지 얽혀 별도 slice가 맞다.

## 3. embedding 방식

real Chroma는 벡터를 저장하지만, **벡터를 무엇으로 만드는지**가 검색 품질을 정한다. "real Chroma + 지금의 fake 4-dim 벡터"는 재시작 생존은 되지만 의미 품질은 0이다.

| 옵션 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A. fake 벡터 영속 우선 | real 영속 Chroma adapter + 계약/재시작 생존을 먼저 잠그고, 벡터는 당분간 `DeterministicFakeEmbeddingProvider` 유지 | 무거운 모델 dependency 결정 없이 인프라·계약·영속·stale 규칙을 안정화. LLM 무관 | 실제 semantic 품질은 미검증(별도 spike 필요) |
| B. real local embedding model 즉시 | sentence-transformers 등 로컬 모델을 지금 선택 | 실제 semantic 품질 확보, dimension 확정 | model/차원/dependency(torch 등 무거움) 결정을 지금 해야 하고 slice가 커짐. 제약 환경 리소스 이슈 가능 |
| C. Gateway LLM embedding endpoint | llama.cpp/Gateway에 embedding surface를 열어 서빙 통일 | 서빙 경계 통일 | Gateway embedding contract 미존재(상류 선행). **vector 백엔드가 LLM 게이트에 묶여 제약 환경에서 빌드 불가** |

브리프 초안 추천은 A였으나 **오너가 B로 결정**했다(위 Owner decisions §3). 모델을 `dragonkue/BGE-m3-ko`(1024-dim)로 확정해 dependency/dimension 불확실성을 없앴고, embedding을 별도 컨테이너로 두어 C가 우려한 LLM 결합을 피한다. C(Gateway embedding)는 그대로 배제한다.

## 4. Chroma 실행 / 인프라

| 옵션 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A. Chroma server 컨테이너 + thin client | compose에 Chroma 서비스 추가(Mongo/llama와 같은 패턴), adapter는 Chroma REST를 httpx로 호출(또는 `chromadb` HttpClient) | 기존 인프라 패턴과 일치. app 이미지 dependency를 얇게 유지 가능(httpx 직접) | 컨테이너 하나 추가. persistence volume 관리 |
| B. embedded persistent client | `chromadb` 라이브러리를 in-process persistent mode(로컬 파일 경로)로 사용, 컨테이너 없음 | 별도 컨테이너 불필요, 로컬 1인 MVP에 단순 | `chromadb` python dep(무거움)이 app 이미지에 들어감. 프로세스 결합 |

추천: **A(컨테이너 + thin client)**. 근거 — Mongo/gateway와 같은 "컨테이너 + skip-aware live test" 패턴에 정확히 얹히고, app 이미지 dependency를 얇게 유지한다. base compose에 넣을지 opt-in override(`docker-compose.chroma.yml`)로 둘지는 구현 세부로, `docker-compose.llama.yml` 선례를 따라 **opt-in override**를 기본 추천한다(외부/미구성 환경 배려).

## 5. 테스트 전략

| 옵션 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A. skip-aware live Chroma + fake 단위 | Mongo 패턴 그대로: `CHROMA_TEST_URL`(또는 유사) env가 가리키는 실제 Chroma가 있을 때만 live 통합 테스트, 없으면 skip. fake adapter 단위 테스트는 항상 실행 | 인프라 없는 환경(2번째 환경)에서도 전체 스위트가 skip-aware로 통과. 실제 영속/query는 live에서 검증 | live 검증은 Chroma 인프라를 요구 |

추천: **A**. 근거 — Mongo(`CORE_SOT_TEST_MONGO_URI`)·outbox live smoke와 동일한 skip-aware 방식이라 2-환경 제약에 이미 맞다.

## 6. 계약 표면 변화 (구현 시 반영)

- `backend` literal에 `chroma`를 추가한다(`IndexSyncTarget`/rebuild summary `backend`). real adapter가 wiring되면 rebuild summary `backend`는 `chroma`, fake 경로는 `in_memory_fake`를 유지한다.
- rebuild summary count의 snapshot-scope per-rebuild 의미(v1.6.35)는 유지한다. 다만 real Chroma는 durable이므로 **재시작 생존**이라는 동작 변화가 생긴다 — v1.6.35의 "재시작 소실" 특성은 chroma-backed 경로에 한해 갱신된다.
- `validate_source_block_record()` stale guard는 backend와 무관하게 그대로다(계약 변경 없음).
- Phase 3B worker의 archive mutation은 현재 recording-only fake다. real Chroma 도입 시 archive 대상 부재에 `DerivedIndexRecordNotFound`류를 raise해야 idempotent success가 유지된다(HANDOFF Next Tasks 4). **이 worker→Chroma 실제 mutation 배선은 이 slice 범위 밖의 후속**으로 두고, 이 slice는 rebuild write + query read 경로만 real로 올린다.

## 2-환경 제약 정리 (LLM 게이트 미가용 환경)

- 브리프 / 구현 / 단위·통합(skip-aware) 테스트 = **LLM 무관** → 두 환경 모두 진행 가능.
- live context-search smoke(planner가 Gateway 관통) = **LLM 필요** → LLM 되는 환경 전용, 이미 sandbox 밖 승인 네트워크 단계로 분리돼 있다.
- 그래서 embedding 3-C(Gateway embedding)를 배제하면 vector 백엔드 전체가 LLM-독립이 되어, 제약 환경에서도 B를 온전히 빌드·검증할 수 있다.

## 구현 sub-slice 계획 (승인됨)

real embedding model + Chroma 컨테이너 도입이라 한 커밋에 몰지 않고 작은 세로 slice로 나눈다. 각 sub-slice는 fake 기반 단위 테스트(인프라 무관, 두 환경)로 잠그고, 실제 컨테이너 관통은 skip-aware live/deployed로 뒤에 둔다.

- **B.1 embedding provider seam** — `EmbeddingProvider` Protocol에 맞는 `RemoteEmbeddingProvider`(embedding 서비스 `/embed` 호출) 추가. `embed`는 기존 Protocol대로 **동기**를 유지하고 sync `httpx.Client`로 구현한다 — embedding 호출은 짧아(수십 ms) indexing/context-search 전반의 async 파급을 감수할 이유가 없다(단순성 우선, generation과 달리 long-poll 아님). `DeterministicFakeEmbeddingProvider`는 단위 테스트용으로 유지(dimension 주입식). MockTransport 단위 테스트로 요청/응답·차원·오류 매핑을 잠근다. 인프라 불필요 → 두 환경.
- **B.2 embedding 서비스 컨테이너** — `services/embedding/`에 sentence-transformers로 `dragonkue/BGE-m3-ko`를 로드해 `POST /embed`(+ `/health`)를 노출하는 FastAPI 서비스 + Dockerfile + base compose 서비스. 1024-dim 응답. live smoke(컨테이너 기동 시)로 실제 임베딩 차원 확인.
  - **수용 기준(B.1 검증 후속, 관찰 #1 추적)**: B.1 회귀는 MockTransport라 wire 계약의 *소비* 측만 잠근다. B.2는 계약을 *생산*하는 쪽이므로, 서비스가 B.1이 소비하는 정확한 wire 계약(`POST /embed` 요청 `{"text": str}` → 응답 `{"embedding": [float, ...]}`, non-empty, numeric)을 낸다는 것을 (a) 서비스 app 자체 회귀와 (b) **B.2 서비스 handler ↔ B.1 `RemoteEmbeddingProvider` round-trip**(embedding 모델은 fake/stub로 대체해 인프라 없이) 회귀로 함께 잠근다. 이로써 생산/소비 양측이 계약에서 드리프트하지 못하게 한다.
- **B.3 Chroma persistent adapter** — 기존 `VectorIndexAdapter`/`VectorSearchAdapter` seam 뒤로 real 영속 Chroma adapter(thin client) 구현. Chroma는 base compose 서비스 컨테이너 + persistence volume. skip-aware live Chroma 통합 테스트로 upsert/query/재시작 생존을 잠근다.
- **B.4 wiring + 계약 표면** — `create_app`이 env 기반으로 `RemoteEmbeddingProvider` + Chroma adapter를 기본 wiring(미구성 시 fake 유지). rebuild summary `backend="chroma"`, dimension 1024, stale-guard 통합. rebuild write → context-search vector read가 real Chroma+real embedding에서 hit.
  - **수용 기준(B.2 검증 후속, 관찰 #1 추적)**: wiring 시 `RemoteEmbeddingProvider`를 `expected_dimensions=1024`로 구성해, embedding 서비스가 다른 차원을 내면 배포 런타임에서 `EmbeddingProviderError`로 즉시 잡는다(B.1이 만든 guard를 실제 배포 경로에서 활성화). env로 dimension을 조정 가능하게 두되 기본은 1024다.
- **B.5 deployed live smoke(LLM 환경 전용)** — 확장된 deployed smoke(rebuild→search)를 real Chroma + embedding 서비스 + 실제 12B planner 관통으로 실행. 재시작에도 vector hit 생존 확인.
  - **수용 기준(B.2 검증 후속, 관찰 #1 추적)**: 단위 회귀는 stub(dim=8)이라 실제 임베딩 차원이 미검증이다. B.5 live smoke는 실제 `dragonkue/BGE-m3-ko`를 관통해 embedding 벡터가 **실제 1024-dim**임을 assert하고, Chroma가 그 벡터를 저장·query해 hit를 낸다는 것까지 확인한다(sandbox 밖 승인 환경 실행).

## 후속 (이 slice 범위 밖)

- real embedding model quality spike(sentence-transformers 등, dimension 확정).
- Elasticsearch lexical 경로(이름/별칭 검색, planner/need 확장).
- Phase 3B worker → real Chroma archive mutation 배선(`DerivedIndexRecordNotFound` idempotent success).
- prior-memory(analysis 비교) purpose §8 C 완성.
