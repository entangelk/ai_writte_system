# Work Log — 2026-07-05

## Goals

- HANDOFF와 최신 work log를 읽고 다음 작업을 진행한다.
- HANDOFF Next Tasks 1이 "오너 우선순위 결정 필요"로 막혀 있으므로 다음 slice 방향을 오너에게 확인한다.
- 승인된 방향(공유 in-process vector index)을 브리프로 확정한 뒤 구현·검증한다.

## User Decisions and Rationale — Phase 4 real vector backend (B) 착수

- 오너가 HANDOFF Next Tasks 1의 후보 **B(real 영속 vector 백엔드)**를 다음 작업으로 선택했다. 브리프 `docs/plans/04-real-vector-backend-decisions.md`를 이전 kickoff 브리프 형식(옵션 표 + 추천)으로 작성해 6개 결정을 받았다.
- **2026-07-02 결정 갱신**: 그 시점 오너 결정은 "real ChromaDB/ES adapter와 embedding model 선택은 핵심 코어(Phase 5/6 포함) 이후 최후속"이었다. 오너가 지금(Phase 4 중반) B를 앞당기기로 결정해 이 부분을 갱신한다. 근거: 이 작업은 LLM 게이트와 무관해(테스트 스위트 전체가 LLM-독립, LLM은 live smoke 스크립트만 사용) 2-환경 개발(하나는 LLM 게이트 미가용) 제약과 정확히 맞고, vector need 영속화 이득을 조기 확보한다. ES lexical과 real embedding model 중 ES는 여전히 후속이다.
- **embedding model 확정 경위**: 오너가 처음 `dragonkue/bge-reranker-v2-m3-ko`를 지목했으나, 이는 cross-encoder **reranker**라 Chroma 벡터 생성(bi-encoder embedding)에는 부적합함을 확인·surface했다. 저장소에도 이 모델의 사전 확정 기록은 없었다(embedding model은 계속 "미확정"). 오너가 `dragonkue/BGE-m3-ko`(embedding model)로 정정했고, WebFetch로 bi-encoder·1024-dim·sentence-transformers·BAAI/bge-m3 한국어 파인튜닝을 확인했다. reranker는 후속 rerank 단계 후보로 남긴다.
- **인프라 방침**: "다 컨테이너로 관리하자"는 오너 지시에 따라 Chroma와 embedding model 모두 base compose 서비스 컨테이너로 둔다. embedding 서비스는 llama gateway와 분리해 vector 백엔드의 LLM-독립성을 유지한다.
- **embedding seam**: `EmbeddingProvider.embed`는 동기를 유지(짧은 호출, async 파급 회피)하고 `RemoteEmbeddingProvider`는 sync `httpx.Client`로 구현하기로 했다(단순성 우선).
- **B.1 독립 검증 후속(2026-07-05)**: `docs/verifications/2026-07-05/real_vector_backend_brief_b1_embedding_seam.md` 판정 **합격(조건 없음)**. 검증자가 WebSearch로 reranker/embedding 구분과 BGE-m3-ko 1024-dim을 독립 확인했고, bool 거부 guard·`expected_dimensions` guard의 양방향 mutation(bool guard 제거→test 8 재실패, dim guard 제거→test 2 재실패)을 재현했다. 비차단 관찰 2건은 B.1 범위 밖(생산 측은 B.2, wiring은 B.4)이라 B.1 코드는 손대지 않았다. 관찰 #1(MockTransport라 소비 측만 lock)을 잊지 않도록 **B.2 수용 기준에 "생산 측 wire 계약 + B.1↔B.2 round-trip 회귀"를 추적 항목으로 명시**했다(브리프 B.2).

## Completed work

### Phase 4 real vector 백엔드 B.1 embedding provider seam

- 변경 파일: `services/application/app/indexing/embedding.py`(신규), `tests/test_embedding_provider.py`(신규).
- `EmbeddingProvider` Protocol(동기 `embed`)에 맞는 `RemoteEmbeddingProvider`를 추가했다. embedding 호출은 짧아 sync `httpx.Client`로 구현해 indexing/context-search 전반의 async 파급을 피한다(단순성 우선). `POST /embed`에 `{"text": ...}`를 보내고 `{"embedding": [...]}`를 파싱해 float 튜플로 반환한다. optional `expected_dimensions` 검증과 timeout/request/non-200/non-JSON/빈·비배열 embedding/비수치·bool 값을 `EmbeddingProviderError`로 매핑한다(bool은 int subclass라 0.0/1.0 silent coercion을 막기 위해 명시 거부).
- 회귀 8개(MockTransport). 독립 검증 합격(위 User Decisions 후속 참고).

### Phase 4 real vector 백엔드 B.2 embedding 서비스 컨테이너

- 변경 파일: `services/embedding/__init__.py`·`services/embedding/app/__init__.py`·`services/embedding/app/main.py`·`services/embedding/requirements.txt`·`services/embedding/Dockerfile`(신규), `docker-compose.yml`, `tests/test_embedding_service.py`(신규).
- `services/embedding/app/main.py`: 주입형 모델의 FastAPI 서비스. `create_app(model=None)`은 model이 주입되면 그대로 쓰고, 없으면 lifespan에서 env 기반 `SentenceTransformerEmbeddingModel`(`dragonkue/BGE-m3-ko`, 1024-dim)을 로드한다. `sentence_transformers` import는 lazy라 단위 테스트(stub 주입)는 무거운 dependency 없이 실행된다. `POST /embed`(`{text}`→`{embedding, dimensions}`), `/health`·`/health/live`, `/health/ready`(model 로드 전 503). 빈 text는 422. model 미로드 시 `/embed`·`/health/ready` 503.
- `build_embed_response(model, text)`를 단일 응답 shape 소스로 분리해 route와 round-trip 회귀가 공유한다.
- `Dockerfile`(cache-friendly layer, model은 startup 로드)·compose `embedding` 서비스(base, port 8002, `embedding_cache` HF 볼륨, `/health/ready` healthcheck + 넉넉한 start_period)·`.gitignore`는 기존대로. application→embedding wiring은 B.4 예약(아직 depends_on 미연결).
- 회귀 5개: 서비스 app 자체 회귀 4개(embed 벡터/차원, health/readiness, 빈 text 422, 미로드 503 — ASGITransport+stub) + **producer↔consumer round-trip 1개**(`build_embed_response` 출력을 B.1 `RemoteEmbeddingProvider`가 그대로 소비 → wire 계약 드리프트 방지, 검증자 관찰 #1을 회귀로 폐쇄). `docker compose config` 유효.

- **B.2 독립 검증 후속(2026-07-05)**: `docs/verifications/2026-07-05/b2_embedding_service_container.md` 판정 **합격(조건 없음)**. round-trip이 vacuous하지 않음을 검증자가 mutation(응답 키 `embedding`→`vector`)으로 2개 재실패(consumer `EmbeddingProviderError` + app `KeyError`)로 재실증했다. 비차단 관찰 2건은 B.2 범위 밖(1024-dim live→B.5, wiring→B.4)이라 B.2 코드는 손대지 않고, 뒤 slice 수용 기준으로 못 박았다: **B.4에 `RemoteEmbeddingProvider(expected_dimensions=1024)` 구성**(배포 런타임 차원 드리프트 즉시 검출), **B.5 live smoke에 실제 1024-dim assert + Chroma 저장/query hit 확인**을 브리프에 추가했다.

### Phase 4 real vector 백엔드 B.3 Chroma persistent adapter

- 변경 파일: `services/application/app/indexing/chroma.py`(신규), `tests/test_chroma_adapter.py`(신규), `docker-compose.yml`, `services/application/requirements.txt`.
- `ChromaVectorIndexAdapter`가 fake와 같은 `VectorIndexAdapter`(upsert)·`VectorSearchAdapter`(query_similar) seam + rebuild summary가 쓰는 `list_records`를 real Chroma collection 위에 구현한다. 인덱스가 프로세스 재시작에도 살아남는다.
- adapter는 **주입형 collection**(duck-typed upsert/query/get)을 받아 로직(project scoping, archived 제외, id 정렬, cosine 랭킹, limit, record 복원)을 인메모리 `FakeChromaCollection`으로 chromadb 없이 단위 테스트한다. `connect_chroma_collection(host, port)`가 `chromadb`를 lazy import해 real HttpClient collection(cosine space)을 만든다 — sandbox/제약 환경은 dependency 없이 통과.
- 직렬화: `record_to_chroma`(record→id/embedding/metadata, 모든 필드 metadata 보존)·`record_from_chroma`(복원, embedding→float 튜플, archived bool 복원). query_similar는 `_active_where`(project + 비archived)로 랭킹 후보를 fake와 동일하게 좁힌다.
- 인프라: compose `chroma` base 서비스(`chromadb/chroma`, `IS_PERSISTENT=TRUE`, port 8003→8000, `chroma_data` volume, port-open liveness healthcheck — API 버전 경로 비의존). `services/application/requirements.txt`에 `chromadb>=0.5,<0.7` 추가(B.4 wiring이 실제 client 사용). Chroma image tag/heartbeat 경로 정합은 B.5 live bring-up에서 확인.
- 회귀(초기 9개 → 검증 후속으로 11개): 직렬화 round-trip 2 + adapter 로직 8 + **skip-aware live Chroma 1**(`CHROMA_TEST_URL`+chromadb 설치 시 upsert/query/list + fresh client 재시작 생존; 미충족 시 skip). application→Chroma wiring은 B.4 예약.

- **B.3 독립 검증 후속(2026-07-05, 조건부 합격 → 폐쇄)**: `docs/verifications/2026-07-05/b3_chroma_persistent_adapter.md`. 차단 사유: `query_similar`의 `_active_where`는 3조건(project_id·project_archived·draft_archived)을 검사하나 회귀는 project_archived 제외만 lock해 boundary matrix에 빈 cell 2개(query 경로의 project scope·draft_archived). `list_records`는 별도 where라 query를 대신 못함. **폐쇄**: `test_query_similar_excludes_draft_archived`·`test_query_similar_is_project_scoped` 2개 추가(9→11), 각 절 제거 mutation으로 재실패 실증(draft_archived 절 제거→draft test 재실패, project_id 절 제거→scope test 재실패), 복원 byte-identical. 비차단 관찰(깨진 `include_embeddings=False` 옵션 → `record_from_chroma(None)` TypeError)은 옵션 자체를 제거해 단순화(embedding은 record 복원에 항상 필요, 아무도 False 미사용). 전체 pytest 454 passed/45 skip.

### Phase 4 real vector 백엔드 B.4 wiring (SoT v1.6.36)

- 변경 파일: `services/application/app/main.py`, `services/application/app/indexing/service.py`(`CHROMA_VECTOR_BACKEND` 상수), `services/application/app/indexing/models.py`(`IndexSyncBackend.CHROMA`), `docker-compose.yml`, `tests/test_real_vector_backend_wiring.py`(신규), `docs/system-contract-sot.md`.
- `create_app`이 env 기반으로 vector 백엔드를 선택한다: `_build_embedding_provider`(`EMBEDDING_SERVICE_URL` 설정 시 `RemoteEmbeddingProvider(expected_dimensions=1024)` — B.2 검증 후속 차원 guard armed, 없으면 fake)·`_build_chroma_vector_index`(`CHROMA_HOST` 설정 시 `ChromaVectorIndexAdapter(connect_chroma_collection(...))`, 없으면 None→InMemory). 주입된 `vector_index`(테스트)는 항상 fake backend label(`in_memory_fake`) 유지. rebuild summary `backend`는 wiring에 따라 `chroma`/`in_memory_fake`.
- stale-guard 통합은 별도 코드 불필요: `_default_context_search_service`가 shared vector_index(이제 Chroma)를 `vector_search`(query)와 `indexing_service`(stale guard, SOT 재조회)로 함께 wiring하므로 Chroma hit도 정본 재확인 후에만 ContextItem이 된다.
- compose application에 `EMBEDDING_SERVICE_URL=http://embedding:8002`·`EMBEDDING_DIMENSIONS=1024`·`CHROMA_HOST=chroma`·`CHROMA_PORT=8000` env와 embedding/chroma `depends_on: service_healthy` 추가. embedding은 llama gateway와 분리된 컨테이너라 vector 백엔드는 LLM-독립.
- 회귀 7개(`tests/test_real_vector_backend_wiring.py`): 빌더 env 분기 4(embedding fake/remote+1024 guard, chroma None/host·port) + create_app backend literal 3(기본 `in_memory_fake`, `CHROMA_HOST`+patched connect→`chroma`+collection write, 주입 vector_index는 `CHROMA_HOST` 있어도 fake 유지+connect 미호출). chromadb/live 서버 없이 patched `connect_chroma_collection`+`FakeChromaCollection`로 검증. 실서버·실모델 1024-dim 관통은 B.5 live.

- **B.4 독립 검증 후속(2026-07-05)**: `docs/verifications/2026-07-05/b4_real_vector_backend_wiring.md` 판정 **합격**. stale-guard 자동 통합 주장을 검증자가 코드 추적(`validate_source_block_record`가 vector_index 아닌 core_sot 사용)으로 확인. 검증자가 "승계 사항: B.3 query_similar 빈 cell 미해결"을 지적했으나 이는 B.3 조건부 합격 원본 기록 기준의 오인 — 실제로는 커밋 `37f82f7`(B.4 커밋 `7ad90ef`의 직계 부모)에서 이미 폐쇄됨(가드 2개 + mutation 재실증), 재작업 불필요. 비차단 관찰(B.4가 만든 staleness) 보강: `_default_context_search_service`의 타입 힌트를 `InMemoryVectorIndexAdapter | ChromaVectorIndexAdapter`·`EmbeddingProvider`로 넓히고 "real Chroma is a later slice" 주석을 env 기반 backend 선택 설명으로 정정(런타임 무변, Protocol duck-typed였음). 전체 OK(45 skip).

### Phase 4 real vector 백엔드 B.5 deployed live smoke

- 실행 환경: `docker compose -f docker-compose.yml -f docker-compose.llama.yml up -d --build`로 mongo/gateway/llama/embedding/chroma/application 전체 stack 기동. 첫 시도는 Docker Compose bake 경로 panic으로 실패해 `COMPOSE_BAKE=false docker compose -f docker-compose.yml -f docker-compose.llama.yml up -d --build`로 재실행했다.
- bring-up 관찰: Chroma `chromadb/chroma:0.5.23`는 port-open healthcheck로 healthy. embedding 서비스는 `dragonkue/BGE-m3-ko` 첫 다운로드로 약 2.2GB HuggingFace cache를 채운 뒤 healthy. application은 embedding/chroma/gateway/mongo health 이후 healthy.
- 실제 embedding 확인: `curl -sS -X POST http://127.0.0.1:8002/embed -H 'Content-Type: application/json' -d '{"text":"아린"}'` 응답이 `dimensions: 1024`를 반환했다.
- 최초 B.5 smoke에서 live-only 결함을 발견했다. `scripts/phase4_context_search_deployed_smoke.py --application-base-url http://127.0.0.1:8000 --timeout-seconds 900` 실행 결과 search는 Chroma hit(`micro_count=6`, gate pass)를 냈지만 rebuild endpoint가 500이었다. 원인은 real Chroma client가 `embeddings`를 numpy array-like 값으로 반환하는데 `_records_from_get()`이 `result.get("embeddings") or ...`로 truthiness를 평가해 `ValueError: The truth value of an array with more than one element is ambiguous`가 난 것.
- 수정: `services/application/app/indexing/chroma.py`의 `_records_from_get()`/`_records_from_query()`가 `embeddings`/`metadatas` 존재 여부를 `is None`으로만 판단하도록 변경했다. 같은 root-cause pattern sweep에서 동일한 `or` fallback은 이 두 곳뿐이었다.
- 회귀: `tests/test_chroma_adapter.py`에 `AmbiguousTruthValueList`를 추가해 numpy-like truthiness 오류를 재현하고, `test_list_records_accepts_chroma_numpy_like_embeddings`·`test_query_similar_accepts_chroma_numpy_like_embeddings`로 list/query 양쪽을 잠갔다.
- 수정 반영 후 application 재빌드/재기동(`COMPOSE_BAKE=false docker compose -f docker-compose.yml -f docker-compose.llama.yml up -d --build application`) 및 B.5 smoke 재실행 성공: `rebuild_http_status=200`, `rebuild_backend="chroma"`, `rebuild_records_written=6`, `search_http_status=200`, `gate_decision="pass"`, `degraded=false`, `macro_count=2`, `micro_count=6`, plan은 실제 12B planner가 `current_scene→mongo`, `source_quote→vector`를 생성.
- 재시작 생존 확인: `docker compose -f docker-compose.yml -f docker-compose.llama.yml restart application` 후 rebuild 없이 기존 `project_id=6a49ccf8baee0fccf1b3d35b`/`draft_id=6a49ccf8baee0fccf1b3d35c`/`version_id=6a49ccf8baee0fccf1b3d35d`로 `/context-search`만 호출해 `micro_evidence` 6개가 유지됨을 확인했다. 이는 application process 재시작 뒤 Chroma persistent volume hit가 살아 있음을 증명한다.
- 운영 관찰: embedding image build가 torch 2.12.1의 CUDA wheel 묶음을 대량 다운로드했다. 현재 live 검증은 통과했지만, embedding service image size/startup 최적화(CPU-only torch pin 또는 base image 전략)는 별도 후속 후보로 남긴다.

### B.5 verification follow-up — Chroma container persistence/cache check

- 독립 검증 기록 `docs/verifications/2026-07-05/b5_deployed_live_smoke.md`는 **합격(조건 없음)**이었다. 비차단 관찰 O1(ids/metadatas의 잔존 `or` truthiness pattern)은 작고 일관적인 보강이라 즉시 처리했다.
- `services/application/app/indexing/chroma.py`의 `_records_from_get()`/`_records_from_query()`가 `ids`도 `embeddings`/`metadatas`와 동일하게 `is None` fallback만 쓰도록 정리했다. `tests/test_chroma_adapter.py`의 `AmbiguousTruthValueList` 회귀를 ids/embeddings/metadatas 전체 container로 확장해 list/query 양쪽을 잠갔다.
- Docker/Compose cache 점검:
  - embedding model cache: `embedding_cache` named volume이 `/root/.cache/huggingface`에 mount되어 있고 실제 크기 `2.2G`. `services/embedding/Dockerfile`은 requirements 설치 layer가 source copy보다 앞이라 source edit/rebuild 시 pip dependency layer가 재사용된다. 모델은 image build 때가 아니라 startup 때 내려받고, volume에 남아 재시작/재생성 시 재사용된다.
  - llama model cache: `llama_models` named volume이 `/models`에 mount되어 있고 실제 크기 `6.7G`.
  - Chroma persistence: 최초 compose는 `chroma_data:/data`였지만 `chromadb/chroma:0.5.23`는 `IS_PERSISTENT=TRUE`에서 실제 DB를 `/chroma/chroma/chroma.sqlite3`에 썼다. `/data`는 4K로 비어 있어 Chroma 컨테이너 재생성 시 vector index가 날아갈 수 있는 구성이었다. `docker-compose.yml`을 `chroma_data:/chroma/chroma`로 수정했다.
- 수정된 Chroma volume 검증: `docker compose -f docker-compose.yml -f docker-compose.llama.yml up -d chroma application` + application 재기동 후 B.5 smoke 재실행 성공(`rebuild_backend="chroma"`, `rebuild_records_written=6`, `micro_count=6`). 이후 `docker exec ai_writte_system-chroma-1 du -sh /chroma/chroma`가 `4.3M`, mount는 `volume:ai_writte_system_chroma_data->/chroma/chroma`로 확인됐다.
- Chroma container restart 생존 확인: `docker compose -f docker-compose.yml -f docker-compose.llama.yml restart chroma application`은 compose restart 특성상 dependency health 대기를 하지 않아 application이 Chroma ready 전에 한 번 실패했다. Chroma가 healthy 된 뒤 `docker compose ... up -d application`으로 application을 다시 기동했고, rebuild 없이 새 smoke project(`project_id=6a49d1d8073f78a3eb24e1a4`, `draft_id=6a49d1d8073f78a3eb24e1a5`, `version_id=6a49d1d8073f78a3eb24e1a6`)로 `/context-search`를 호출해 `micro_count=6`, vector step `hits_considered=6/items_produced=6`, 모든 micro `sot_reloaded=true`를 확인했다. 이로써 Chroma 컨테이너 재시작 뒤에도 named volume hit가 생존함을 추가 확인했다.

### 다음 slice 방향 오너 결정

- HANDOFF Next Tasks 1의 후보 4종(A 공유 in-process vector index / B real Chroma·ES / C prior-memory purpose / D tool-call planner 전환)을 제시했다.
- 오너는 **A(공유 in-process vector index)**를 선택했다. C는 오너가 뒤로 미룬 항목, D는 상류 wire 계약 미해소로 차단이라 근시일 후보에서 제외됐다.
- A는 "fake vector adapter는 request마다 throwaway·비지속" 특성을 프로세스 수명 공유로 바꾸는 비persistence 계약 변경이라 착수 전 브리프가 필요했다.

### 공유 vector index 착수 브리프 (docs/plans/04-shared-vector-index-decisions.md)

- 신규 브리프를 작성하고 `Approved (2026-07-05)`로 확정했다.
- rebuild가 채운 파생 index를 같은 프로세스 context search가 실제로 조회하도록 `create_app`이 단일 in-process vector index를 공유하는 것이 목적이다.
- 오너 결정 2건: (1) 방향은 A 채택, (2) rebuild HTTP summary는 **기존 계약 유지(snapshot scope)**. 공유 index가 여러 snapshot rebuild를 누적하더라도 summary count는 해당 rebuild의 `snapshot_id`로 scope해 per-rebuild 의미(v1.6.22/v1.6.23 "누적 없음")를 그대로 둔다.

### 공유 in-process vector index 구현 (SoT v1.6.35)

- 변경 파일: `services/application/app/main.py`, `services/application/app/indexing/service.py`, `tests/test_context_search_shared_index.py`(신규), `docs/plans/04-shared-vector-index-decisions.md`(신규), `docs/system-contract-sot.md`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-05/work_log.md`.
- `create_app`이 단일 `InMemoryVectorIndexAdapter`(+ `DeterministicFakeEmbeddingProvider`)를 소유한다. `LLM_GATEWAY_BASE_URL` 유무와 무관하게 항상 생성되며, 테스트 주입용 `vector_index` param을 열었다.
- rebuild HTTP endpoint(`_rebuild_source_block_index_payload`)가 이 공유 adapter/embeddings를 `rebuild_source_block_index_summary(...)`에 넘겨 여기에 write한다.
- `_default_context_search_service`가 공유 `vector_index`/`embeddings`를 받아 context search의 `vector_search`(query)와 `indexing_service`(stale guard)를 같은 인스턴스로 wiring한다 → 같은 프로세스 rebuild 후 context search가 실제 vector hit을 서빙한다.
- `rebuild_source_block_index_summary`에 optional `vector_index`/`embeddings` 인자를 추가했다. 미제공 시 종전대로 throwaway adapter(CLI script 비지속 유지). summary count(`records_indexed`/`records_query_visible`/`records_archived`)는 항상 해당 rebuild의 `snapshot_id`로 필터해 per-rebuild 의미를 유지한다 — throwaway 경로에서는 adapter가 이미 해당 snapshot만 담으므로 값이 동일하고, 공유 경로에서도 같은 값을 낸다.
- staleness 안전성: 공유 adapter는 fake archive mutation을 받지 않지만 context search가 hit마다 `validate_source_block_record()` stale guard + SOT 재조회를 거치므로 rebuild 후 archive/drift record는 query-time에 제외된다(Slice 4.1 방어선 재사용).

## Issues found

- B.5 live에서 Chroma Python client의 embeddings 반환값이 numpy array-like라 truthiness 평가(`result.get("embeddings") or ...`)가 `ValueError`를 일으켜 rebuild endpoint 500을 냈다. cause: fake collection은 list를 반환해 단위 회귀가 이 컨테이너 타입 차이를 못 잡았다. resolution: embeddings/metadatas fallback을 `is None` 검사로 바꾸고 numpy-like truthiness 회귀 2개를 추가했다. outcome: B.5 smoke가 `rebuild_http_status=200`으로 통과했다.
- B.5 후속 cache 점검에서 `chroma_data` volume이 `/data`에 붙어 있었지만 실제 Chroma DB는 `/chroma/chroma`에 생성되는 것을 발견했다. cause: image default persist directory와 compose mount path 불일치. resolution: `docker-compose.yml` mount target을 `/chroma/chroma`로 변경. outcome: Chroma 컨테이너 재시작 후 rebuild 없이 vector hit `micro_count=6` 유지 확인.
- Docker Compose bake 빌드 경로가 Go panic으로 실패했다. resolution: `COMPOSE_BAKE=false`로 internal builder를 사용해 stack bring-up을 완료했다. outcome: live 검증 진행 가능.
- rebuild summary가 v1.6.23에서 "누적 없음"으로 잠긴 계약을 공유 index 누적이 깨뜨릴 위험이 있었으나, snapshot scope로 봉쇄했다.

## Decisions

- 방향은 A(공유 in-process vector index). B/C/D는 후속(사유: C 후순위, D 상류 차단).
- rebuild summary는 snapshot scope로 per-rebuild 계약을 보존한다(오너 결정). 이유: v1.6.22/v1.6.23 관측 계약과 Slice 4.3가 잠근 "누적 없음" 회귀를 불변으로 두고 계약 변경 blast radius를 최소화하기 위함. 트레이드오프: summary가 공유 index의 전체 상태를 드러내지 않지만, 그것은 이 slice의 목적이 아니다.

## Verification

- 자체 회귀: `python3 -m py_compile services/application/app/main.py services/application/app/indexing/service.py tests/test_context_search_shared_index.py` 통과.
- `python3 -m unittest tests.test_context_search_shared_index -v` 3개 통과: (1) rebuild HTTP endpoint가 채운 공유 index를 같은 프로세스 context search가 조회해 rebuild 전 empty → rebuild 후 non-empty micro_evidence(sot_reloaded=True), (2) 두 번째 큰 snapshot을 누적한 뒤에도 각 rebuild summary count가 snapshot scope per-rebuild 값을 유지(누적 total보다 작음), (3) rebuild 후 draft archive 시 hit이 stale guard로 제외.
- Mutation 실증(이 slice가 새로 넣은 guard마다): (A) rebuild payload에서 공유 `vector_index`/`embeddings` 주입을 제거하면 (1)/(3)이 재실패(`micro_evidence == []`). (B) `rebuild_source_block_index_summary`의 snapshot-scope 필터(`if record.snapshot_id == snapshot_id`)를 제거하면 (2)가 재실패(`records_indexed` 6 != 15, A+B 누적) → per-rebuild 계약 guard가 vacuous하지 않음을 실증. 복원은 `diff -q`로 byte-identical 확인.
- 관련 묶음 `python3 -m unittest tests.test_context_search_shared_index tests.test_context_search_api tests.test_application_api tests.test_phase3a_rebuild_source_block_index_script tests.test_indexing_phase3a tests.test_context_search -v` 117개 통과.
- 전체 `python3 -m unittest discover tests` Ran 473 OK(skipped=44). `python3 -m pytest -q` 429 passed / 44 skipped. `git diff --check` 통과.

### 독립 검증 후속 보강 (2026-07-05)

- 독립 검증 판정은 **합격**(`docs/verifications/2026-07-05/shared_vector_index_slice.md`), 조건 사유 없음. 경계 매트릭스 전 셀 lock, 빈 셸 없음.
- 검증 AI 비차단 관찰 2건을 보강했다:
  1. worker(자체) mutation 증명이 shared-wiring 제거만 다루고 이 slice가 새로 넣은 snapshot-scope 필터의 무력화 mutation을 빠뜨렸다. 위 "Mutation 실증 (B)"를 직접 돌려 `records_indexed` 6 != 15 재실패를 확인·기록했다(계약 guard non-vacuous 재입증). boundary 자체는 회귀로 이미 lock되어 있어 차단 사유가 아니었다.
  2. `tests/test_context_search_shared_index.py`의 httpx driver helper `TestClient`가 pytest `Test*` 수집 규칙에 걸려 `PytestCollectionWarning`을 냈다. `__test__ = False`를 달아 이 파일 경고를 제거했다(pytest warnings 3→2, 남은 2건은 기존 `test_context_search_api.py` 등 pre-existing이라 surgical 범위 밖). 기능 영향 없음.

### deployed smoke 확장 (rebuild → context-search)

- 변경 파일: `scripts/phase4_context_search_deployed_smoke.py`, `tests/test_phase4_context_search_deployed_smoke_script.py`.
- 기존 smoke는 rebuild를 호출하지 않아 배포 경로에서 공유 index vector hit을 검증하지 못했다. save version → snapshot_id 취득 → `POST .../index/source-blocks/rebuild` → `POST .../context-search` 2-step으로 확장했다.
- summary에 `snapshot_id`/`rebuild_http_status`/`rebuild_records_written`/`rebuild_backend`를 추가했다. exit 규칙을 `search_succeeded`→`smoke_succeeded`(rebuild 200 AND search 200)로 바꿔 두 status를 모두 게이팅한다.
- self-regression: rebuild가 search보다 먼저 호출되고(`summary_step_order_rebuild_before_search`) micro hit(`source_quote`)이 나는 성공 경로, search 502 실패, **rebuild 실패 시 search 200이어도 smoke 실패**(exit 규칙이 두 status 모두에 걸림) 3분기 + CLI 3방향(ok / search_err / rebuild_err). 4→5개.
- 실제 in-process app(진짜 endpoint + 공유 index 주입, fake planner)에 `httpx.ASGITransport`로 smoke를 구동해 mock이 아닌 실경로에서 `rebuild_records_written=6`, `micro_count=6`(source_quote vector need 실hit), gate `pass`, `smoke_succeeded=True`를 확인했다(이 slice 이전이라면 micro 0). compose stack + 실제 12B 관통 live 실행은 sandbox 밖 승인 네트워크가 필요해 미실행이다.

### 독립 검증 후속 보강 — real-app 관통 회귀 (2026-07-05)

- 독립 검증(`docs/verifications/2026-07-05/deployed_smoke_rebuild_first.md`) 판정은 **합격**(조건 없음). 비차단 관찰: 이 slice 회귀가 전부 MockTransport라 HTTP orchestration·exit 규칙·summary 파싱은 lock하지만 "rebuild가 실제로 공유 index를 채워 search가 실hit"은 committed 회귀가 아니었다(수동 ASGITransport 드라이브였음).
- 보강: 수동 드라이브를 committed 회귀로 전환했다. `test_real_app_rebuild_populates_shared_index_and_search_hits`가 real `create_app`(공유 index 주입 + fake planner)에 `httpx.ASGITransport`로 확장 smoke를 구동해 `rebuild_records_written>0`, `micro_count>0`(source_quote 실hit), `smoke_succeeded`를 잠근다. 5→6개.
- non-vacuity mutation: `create_app`에 `vector_index=shared_index` 주입을 빼면 rebuild가 별도 adapter에 쓰여 search가 empty가 되어 `micro_count 0`으로 재실패 → 회귀가 실제 관통을 검증함을 증명. 복원 byte-identical. 전체 475 OK(44 skip)/pytest 431 passed.

## Verification — real vector backend B.1/B.2

- B.1: `python3 -m unittest tests.test_embedding_provider -v` 8개 통과. (독립 검증 합격, 위 User Decisions 후속.)
- B.2: `python3 -m py_compile services/embedding/app/main.py tests/test_embedding_service.py` 통과. `python3 -m unittest tests.test_embedding_service -v` 5개 통과(app 자체 4 + round-trip 1). `docker compose config` 유효(embedding 서비스/볼륨 파싱). 전체 `python3 -m unittest discover tests` OK(44 skip), `python3 -m pytest -q` 444 passed / 44 skipped, `git diff --check` 통과. 실제 모델(`dragonkue/BGE-m3-ko`) 로드·1024-dim 관통은 컨테이너 기동 필요라 sandbox 밖 후속(B.5/live).
- B.3/B.5 live fix: `python3 -m py_compile services/application/app/indexing/chroma.py tests/test_chroma_adapter.py` 통과. `python3 -m unittest tests.test_chroma_adapter -v` 12 passed + 1 live skip(`CHROMA_TEST_URL`/host chromadb 미충족). live에서 발견한 numpy-like container truthiness 결함을 list/query 회귀 2개로 잠금(ids/embeddings/metadatas 모두). `CHROMA_TEST_URL=127.0.0.1:8003 python3 -m unittest tests.test_chroma_adapter.ChromaAdapterLiveTest -v`는 host Python에 `chromadb` 미설치라 skip(컨테이너 관통은 B.5 deployed smoke로 확인).
- B.4: `python3 -m py_compile services/application/app/main.py tests/test_real_vector_backend_wiring.py` 통과. `python3 -m unittest tests.test_real_vector_backend_wiring -v` 7개 통과. `docker compose config` 유효(application env/depends_on embedding·chroma). 전체 `python3 -m unittest discover tests` OK(45 skip), `python3 -m pytest -q` 461 passed / 45 skipped, `git diff --check` 통과.
- B.5: `COMPOSE_BAKE=false docker compose -f docker-compose.yml -f docker-compose.llama.yml up -d --build` 통과(첫 `docker compose ... up -d --build`는 Compose bake panic). `curl /embed` 직접 probe에서 `dimensions=1024`. `python3 scripts/phase4_context_search_deployed_smoke.py --application-base-url http://127.0.0.1:8000 --timeout-seconds 900` 통과(`rebuild_backend="chroma"`, `rebuild_records_written=6`, `micro_count=6`, gate pass). `docker compose ... restart application` 후 rebuild 없이 `/context-search` 호출해 `micro_evidence` 6개 유지. Chroma volume mount 수정 후에도 smoke 재통과, `chroma_data:/chroma/chroma`에 4.3M 데이터 확인, Chroma+application 재시작 뒤 rebuild 없이 `micro_count=6` 유지. Focused regression: `python3 -m unittest tests.test_chroma_adapter tests.test_phase4_context_search_deployed_smoke_script -v` 18개 통과 + 1 skip, `git diff --check` 통과.

## Completed work — worker→real Chroma archive mutation (SoT v1.6.37)

- **오너 결정**: HANDOFF Next Tasks 1의 B.1~B.5 완료 후 후속 후보 4개(worker→real Chroma / embedding 이미지 최적화 / ES lexical 브리프 / embedding quality spike) 중 **worker→real Chroma 배선**을 선택했다(AskUserQuestion).
- **설계 결정 (delete vs tombstone)**: archive worker의 real Chroma mutation은 **delete**로 구현했다. 근거: derived source-block record는 SOT에서 완전히 rebuild 가능하고, archive의 목표는 "검색 후보에서 제외"이며, delete는 단일 원자적 Chroma 연산이다. query-time stale guard(SOT 재조회)가 이미 정합성을 보장하므로 이 mutation은 실제 물리적 cleanup 역할이다. tombstone(metadata `*_archived=True` 갱신)은 embeddings 재읽기+re-upsert가 필요해 더 복잡하고, 이득(Chroma 내 history 보존)은 rebuild 가능성 때문에 불필요하다. 스펙 근거: 브리프 §8.2 선택지 B가 "archive/tombstone/delete 대상 record가 이미 없으면"이라며 delete를 허용 묶음으로 나열하고, §8.3이 fake adapter에 `mark_archived`/`delete_or_tombstone` equivalent를 권고한다 — 브리프가 두 방식을 "등가"로 명시하지는 않으나 delete는 spec-allowed 선택이다(검증 F2 정정).
- **변경 파일**:
  - `services/application/app/indexing/chroma.py`: `ChromaCollection` protocol에 `delete(where)` 추가. `ChromaArchiveIndexMutationAdapter`(seam `mark_archived(entry)`)와 `_archive_where(entry)` 추가. `project_archived`→`{project_id}`, `draft_archived`→project-scoped `{project_id, draft_id}`(`entry.source.mongo_id`=draft id). 삭제 전 `get(where, include=[])`로 존재 확인, `ids` 길이 0이면 `DerivedIndexRecordNotFound` raise(delete 미호출). numpy-like truthiness 회피 위해 truthiness 대신 `len()` 사용(B.5 fix 패턴 준수).
  - `scripts/index_sync_worker.py`: `_build_archive_adapter()` 추가 — `CHROMA_HOST` 설정 시 `ChromaArchiveIndexMutationAdapter`(`connect_chroma_collection`, `CHROMA_PORT`/`CHROMA_COLLECTION` env는 create_app B.4 규약과 동일), 미설정 시 `RecordingArchiveIndexMutationAdapter`. worker summary JSON에 `archive_backend`(`chroma`/`in_memory_fake`) field 추가.
- **효과**: worker command가 배포 stack(`CHROMA_HOST` 설정)에서 archive event를 실제 Chroma record 삭제로 처리하고, 대상이 없으면 idempotent success 처리한다. claim/retry/backoff/terminal-move lifecycle(v1.6.29)은 불변이다. `IndexSyncWorker`의 `DerivedIndexRecordNotFound`→success 분기가 real adapter에서도 작동함을 통합 회귀로 잠갔다.

## Verification — worker→real Chroma archive mutation

- `python3 -m py_compile services/application/app/indexing/chroma.py scripts/index_sync_worker.py tests/test_chroma_adapter.py tests/test_index_sync_worker_script.py` 통과. `python3 -c "from ...chroma import ChromaArchiveIndexMutationAdapter"` import 통과(chroma→service `DerivedIndexRecordNotFound` import에 순환 없음 확인).
- `python3 -m unittest tests.test_chroma_adapter tests.test_index_sync_worker_script tests.test_indexing_phase3a -v` 45개 통과(1 live skip).
- 잠근 범위:
  - **adapter delete 경계**(`ChromaArchiveMutationTest`, fake collection + `delete`): `project_archived`가 해당 project record만 삭제하고 타 project 무손상(delete 1회), `draft_archived`가 project-scoped 해당 draft만 삭제(같은 draft id의 타 project record 무손상), 삭제 대상 없음 시 `DerivedIndexRecordNotFound` raise + **delete 미호출**(project/draft 각각) + 타 record 무손상.
  - **not-found guard numpy-like under-strict lock**(`test_not_found_guard_uses_len_not_truthiness_on_numpy_like_ids`, 검증 F1 보강): `ambiguous_ids=True`로 fake `get`이 빈 `AmbiguousTruthValueList`(`__bool__`가 ValueError)를 반환할 때도 `len()` guard가 `DerivedIndexRecordNotFound`를 raise + delete 미호출. mutation 실증: guard를 `if not ids:`로 되돌리면 `ValueError: ambiguous truth value`로 재실패(→ real backend에서 §8.2 idempotent-success가 조용히 깨져 BACKEND_ERROR 3회 retry로 오분류됨을 lock). 복원 후 재통과.
  - **worker↔real adapter 통합**(`ChromaArchiveWorkerIntegrationTest`): worker가 real `ChromaArchiveIndexMutationAdapter`로 매칭 record 삭제 후 terminal success + outbox 제거 + success log, 대상 없음 시 idempotent success(delete 미호출, log error None).
  - **script env 분기**(`BuildArchiveAdapterTest`): `CHROMA_HOST` 미설정→`RecordingArchiveIndexMutationAdapter`+`in_memory_fake`, 설정→`ChromaArchiveIndexMutationAdapter`+`chroma`(`connect_chroma_collection` host/port/collection 인자 검증). summary JSON에 `archive_backend` 포함.
- 전체 `python3 -m unittest discover tests` Ran 517 OK(skipped=45). `python3 -m pytest -q` 472 passed / 45 skipped(신규 회귀 11개: chroma archive 6 + not-found numpy-like guard 1 + worker 통합 2 + script build 2). `git diff --check` 통과.
- 실제 Chroma 서버 관통 live smoke(worker가 컨테이너 Chroma에서 archive record 실삭제)는 sandbox 밖 승인 네트워크가 필요해 미실행(후속).

### 독립 검증 후속 보강 — F1/F2 (2026-07-05)

- 독립 검증 판정은 **조건부 합격**(`docs/verifications/2026-07-05/worker_real_chroma_archive_mutation.md`), 차단 조건 F1 1건.
- **F1(차단) 폐쇄**: `mark_archived`의 numpy-like ids guard에 under-strict 회귀가 빠져 있었다(B.5가 unit으로 잡을 수 있음을 증명한 패턴). `test_not_found_guard_uses_len_not_truthiness_on_numpy_like_ids`를 추가해 `ambiguous_ids=True` 빈 결과에서도 `DerivedIndexRecordNotFound`+delete 미호출을 잠갔고, guard를 `if not ids:`로 되돌리는 mutation이 `ValueError`로 재실패함을 실증했다.
- **F2(비차단) 정정**: "브리프 §8.3이 delete/tombstone을 등가로 뒀다"는 인용을 정정했다. 실제로는 §8.2 선택지 B가 delete를 허용 묶음으로 나열하고 §8.3이 fake에 `mark_archived`/`delete_or_tombstone` equivalent를 권고할 뿐 "등가" 명시 문구는 없다. delete는 spec-allowed 선택이며 근거는 유지된다.
- **F3/F4(비차단) 처리**: F3(`_archive_where` unsupported-event ValueError)은 worker `_process_entry`가 먼저 event를 필터링해 도달 불가한 defensive dead-path라 회귀를 추가하지 않는다(브리프 event set이 늘면 그때 lock). F4(live smoke)는 F1 보강으로 guard가 unit-proven이 됐고, 컨테이너 Chroma 관통 smoke는 여전히 후속이다.

## Next steps

- worker→real Chroma **live smoke**(배포 stack에서 project/draft archive → outbox → worker command → 실제 Chroma record 삭제 확인)는 후속(sandbox 밖 실행 필요).
- ES lexical 경로(§8, 착수 전 브리프)는 계속 후속.
- embedding service image size/startup 최적화 검토: 현재 build가 torch CUDA wheel 묶음을 크게 끌어오므로 CPU-only torch pin/base image 전략을 후속 후보로 둔다.
- prior-memory(analysis 비교) purpose §8 C 완성(Phase 2B 착수 브리프)도 후속.
