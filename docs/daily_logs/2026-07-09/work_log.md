# Work Log — 2026-07-09

## Goals

- HANDOFF와 2026-07-08 work log를 읽고 다음 작업을 진행한다.
- 오너가 다음 slice로 **(b-5) compose 전용 ES 서비스**를 선택 → 착수 브리프 → 오너 결정 → 구현·검증.
- 이어서 **(b-2) candidate lexical/vector retrieval** 선택 → 착수 브리프 → 오너 결정(2증분) → 증분1(색인 파이프라인)·증분2(retriever) 구현·검증.

## Completed work

### (b-5) compose 전용 ES 서비스 (SoT v1.6.53)

- **리듬**: 착수 브리프(`plans/04-compose-elasticsearch-service-decisions.md`) → 오너 결정(G0~G6 전부 A) → 구현 → 실 bring-up 검증. v1.6.52가 "compose 전용 ES 서비스는 후속"으로 남긴 배포 인프라 slice.
- **성격**: **순수 배포 인프라 + 소폭 견고성 코드 터치**. v1.6.52가 lexical/hybrid **코드**를 이미 완성·회귀 잠금했고 application/worker가 `ELASTICSEARCH_URL`를 읽는 배선도 존재했으나, compose 스택에 ES 서비스가 없어 배포에서 이 경로가 영구 미발화(env 미설정→vector-only/Mongo-direct fallback)였다. 이 slice가 인프라를 채워 배포에서 hybrid(RRF)가 실동작하게 한다. **계약 literal·public 표면 변경 없음.**
- **조사에서 확인한 사실**:
  - 공식 ES 이미지에 **analysis-nori 미포함**(플러그인). 머신 테스트 컨테이너 이미지명 `tf-ai-harness-elasticsearch-step1-nori:8.13.4`가 방증 → 배포 ES도 nori를 심은 자체 빌드 이미지 필요.
  - ES 8.x 보안 기본 ON(TLS+auth)이나 코드는 `Elasticsearch(url)` **plaintext·무인증**([memory_lexical_index.py:293](../../../services/application/app/indexing/memory_lexical_index.py#L293)) → 배포 ES도 보안 off여야 계약과 정합(테스트 컨테이너·MVP 단일 사용자 자세).
  - 앱/worker 부팅 시 `connect_elasticsearch_memory_index`가 nori 인덱스를 lazy create하는데 `Elasticsearch(url)` 기본 `request_timeout`=10s. cold nori create ~4s(부하 시 초과)라 flake 위험 — v1.6.52 live smoke가 정확히 이 이유로 `request_timeout=30`으로 견고화됐으나 production `connect_` 경로는 아직 기본 10s.
  - worker(`index_sync_worker.py`)는 compose 서비스가 아님(수동/out-of-band, 2B.5 Chroma reindex와 동일). → compose에서 lexical **retrieval**은 되지만 **색인 적재**는 worker 실행 필요(기존 Chroma 자세와 동일, 인덱스 비면 retriever graceful empty).
  - ES 8.13.4 이미지에 healthcheck 도구는 `curl`·`nc`만(python 없음) → curl 기반 `_cluster/health` probe.
- **구현**:
  - `services/elasticsearch/Dockerfile`(신규): `ARG ELASTICSEARCH_VERSION=8.13.4` → `FROM docker.elastic.co/elasticsearch/elasticsearch:${…}` + `RUN bin/elasticsearch-plugin install --batch analysis-nori`.
  - `docker-compose.yml`: `elasticsearch` 서비스 추가 — `build:`(context `.`, args `ELASTICSEARCH_VERSION`), env `discovery.type=single-node`·`xpack.security.enabled=false`·`ES_JAVA_OPTS`(기본 `-Xms512m -Xmx512m`), `${ELASTICSEARCH_PORT:-9200}:9200`, `es_data` 볼륨, curl `_cluster/health` healthcheck(start_period 60s). `application`에 `ELASTICSEARCH_URL: http://elasticsearch:9200` + `depends_on: elasticsearch: service_healthy`. `es_data` 볼륨 선언. → 배포 canonical retriever 기본이 **hybrid**(CHROMA_HOST+EMBEDDING_SERVICE_URL 이미 존재).
  - `services/application/app/indexing/memory_lexical_index.py`: `connect_elasticsearch_memory_index(*, url, index_name, request_timeout=30)` → `Elasticsearch(url, request_timeout=request_timeout)`. **미지정 호출자(main.py `_build_lexical_canonical_retriever`·worker `_build_memory_adapter`)는 기본 30 자동 상속** → 두 호출부는 무변경(§2 최소 변경).
- **§1 정정 없음**: 브리프 추천값과 구현이 일치. 단 브리프 원안 "request_timeout env override 가능"은 §2(요청 없는 configurability 금지)에 따라 넣지 않고 기본 30 + param만 두었다(smoke가 명시 override로 이미 사용, 추후 필요 시 param 존재).
- **회귀 +3**(`tests/test_context_search_memory_lexical_retrieval.py::ConnectElasticsearchTest`): `elasticsearch.Elasticsearch`를 fake로 patch — (a) 기본 `request_timeout=30` + 인덱스 부재 시 nori(`korean` analyzer) 인덱스 생성, (b) `request_timeout` param이 client로 plumbing(하드코드 아님, 명시 override 5 전달 확인 = over-strict), (c) 기존 인덱스는 재생성 안 함. **mutation 양방향**: `Elasticsearch(url, request_timeout=10)`으로 하드코드 시 (a) default(30≠10)·(b) plumbing(5≠10) 둘 다 재실패 → 복원 통과.
- **실 bring-up 검증(sandbox 안 docker 가용)**: `docker compose build elasticsearch`(nori 설치) → `up -d` → healthy(8회 polling). `curl _cat/plugins`=`analysis-nori 8.13.4`, `_cluster/health`=green·무인증 plaintext. 앱 `connect_elasticsearch_memory_index`(기본 timeout)로 실 ES에 ephemeral `ai_writte_smoke_b5` 인덱스 생성 → `text` 필드 analyzer=`korean`(nori) 확인 → 인덱스 삭제. 검증용 컨테이너·`es_data` 볼륨 정리(잔여 0).
- **검증**: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **654 passed / 45 skipped**(651 → +3). `docker compose config` 정상 파싱(ES 서비스·`ELASTICSEARCH_URL`·`es_data` 해석 확인). `git diff --check` clean.

## Issues found

- 없음.

## Decisions

- **SoT 버전 v1.6.53 bump 판단**: 이 slice는 계약 literal/public 표면을 바꾸지 않는 배포 인프라 + 소폭 코드 견고성(`connect_` request_timeout 기본값)이다. 그럼에도 프로젝트가 버전 로그를 slice 원장으로 운용하고(오너 선택 slice마다 1항목), `connect_` 동작이 미세하게 바뀌므로 v1.6.53으로 기록했다. 변경 이력에 "계약 literal 변경 없음, 배포 표면 실현"을 명시해 오너가 성격을 구분할 수 있게 했다.

## User Decisions and Rationale

- 오너가 다음 slice로 **(b-5) compose 전용 ES 서비스**를 선택했다. v1.6.52 lexical/hybrid를 배포에서 실동작시키는 인프라 완성이 목적이며, 코드 의존 없이 상대적으로 자족적이라는 점이 선택 근거.
- **G0~G6 전부 추천 A**: 자체 nori Dockerfile 빌드(G1 — 로컬 harness 이미지 재사용은 repo 재현 불가라 거부), 보안 off single-node(G3 — 코드가 무인증이라 사실상 강제, 보안 ON은 인증 slice 선행), `connect_` request_timeout=30(G5 — 부팅 시 cold nori create timeout 방지), worker는 compose 미추가·수동 유지(G6 — 기존 Chroma reindex와 동일 자세).

## 검증 후속 보강 (2026-07-09, 오너 독립 감사 → 비차단 관찰 #1·#2)

오너의 독립 감사 기록 `docs/verifications/2026-07-09/compose_elasticsearch_service_b5.md`는 **합격(PASS)** — 경계 매트릭스 G0~G6 빈 셀 없음, mutation 양방향·실 bring-up 독립 재현. 감사자가 짚은 비차단 관찰 3건 중 actionable 2건을 닫았다(#3은 b-5 비관여·선재라 미조치).

- **관찰 #1(single-node 영속 yellow)**: 감사자가 실 재현에서 앱 부팅 시 실 `memory_lexical` 인덱스 생성 직후 클러스터가 **yellow**(unassigned_shards:1, single-node+기본 replica=1)로 전환됨을 확인. healthcheck는 200(green/yellow 모두)이라 기능 결함은 아니나, 향후 "green" keyed readiness 게이트가 steady-state 통과 불가한 wart. **보강**: `ELASTICSEARCH_MEMORY_SETTINGS`에 `number_of_replicas: 0` 추가([memory_lexical_index.py:228](../../../services/application/app/indexing/memory_lexical_index.py#L228)). 근거 — 배포가 `discovery.type=single-node`라 replica 샤드가 영구 미할당이고, ES는 Mongo에서 재생성 가능한 파생 인덱스(SoT §166)라 durability용 replica 불필요. connect_·live smoke가 같은 상수를 공유하므로 한 곳 수정으로 일관 적용. **실 재현 검증**: replicas=0로 인덱스 생성 시 cluster status **green** / unassigned_shards **0**(기존 yellow/1). live smoke 여전히 통과(`ok:true, nori:true`, 잔여 0). 회귀는 기존 `ConnectElasticsearchTest`의 settings 어서션을 `analysis`(nori) + `number_of_replicas==0` 양쪽 확인으로 갱신.
- **관찰 #2(브리프 G5 내부 불일치)**: 논의 절(:80 "env override 가능")이 정본 오너 결정(:11, env override 무언급)·구현과 어긋남. **보강**: 논의 절을 정정 — "정본 §G5는 env override 없이 기본 30 + param만(§2 최소 변경), 구현이 이를 따름" 명시. 코드는 이미 정본을 따르고 있었으므로 문서 일관성만 회복.
- **미조치(§3)**: 관찰 #3(ES client 8.19.3 vs server 8.13.4 skew)은 v1.6.52 이래 상태이고 b-5가 건드린 표면이 아니라 선재 — 요청 없이 미조치(감사자도 "b-5 비관여" 분류).
- **재검증**: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **654 passed / 45 skipped**(무변 — 어서션 강화만). ES 정리 후 `git diff --check` clean.

## Next steps

- **실 배포 관통(sandbox 밖 후속)**: 전체 스택 `docker compose up`으로 application이 hybrid retriever를 부팅·서빙하고 worker composite drain이 ES `memory_lexical` 인덱스를 실제로 채우는 end-to-end 확인.
- **worker compose 서비스**(G6 후속): drain 주기 실행을 compose로 올리려면 restart/loop·health·중복 실행 설계 필요(별도 slice).
- **outbox per-target bookkeeping**: ES sink를 persisted envelope에 명시 추적하려면 outbox multi-target status 확장(v1.6.52 정정 참조).
- 그 외 HANDOFF Next Tasks #1 후보 (b-2)candidate 색인/(b-4)hybrid 튜닝/(c)/(d)/(e) 잔존.

---

## (b-2) candidate lexical/vector retrieval (SoT v1.6.54 색인 파이프라인 + v1.6.55 retriever)

오너가 b-5 완료 후 다음 slice로 **(b-2) candidate retrieval**을 선택 → 착수 브리프(`plans/04-writing-candidate-retrieval-decisions.md`) → 오너 결정(G0=A 2증분, G4=A vector+lexical+hybrid, G1/G2/G3/G5/G6 추천 A) → 2증분 구현·검증.

### 배경/성격

- canonical retrieval(v1.6.51 vector, v1.6.52 lexical/hybrid)은 색인(`memory_vectors`/ES `memory_lexical`)이 이미 있어 retriever 순수 교체였다. **candidate는 색인 표면이 아예 없어** 색인 파이프라인을 먼저 지어야 했다 — b-2는 사실상 2B.5(canonical 색인) + v1.6.51/52(canonical retrieval)를 candidate에 대해 재현한 slice다.
- **핵심 계약 사실**: candidate 상태는 `needs_review` 하나뿐([analysis/models.py:26](../../../services/application/app/analysis/models.py#L26)) — confirmed/rejected는 Phase 6. 승격(2B.1)은 canonical을 mint하되 candidate는 needs_review로 남긴다. 따라서 **de-index 이벤트가 없다**: 색인은 upsert-only, retriever의 needs_review 필터·drain의 self-heal delete는 Phase 6 전이 도입 시 도달하는 **forward-defense**(v1.6.50 Gate status-stale 분기와 동일 자세).

### 증분1 — candidate 색인 파이프라인 (v1.6.54)

- **신설 계약 literal**: `IndexRecordKind.CANDIDATE`, `IndexSyncEvent.CANDIDATE_UPSERTED`, `CandidateIndexRecord`([indexing/models.py](../../../services/application/app/indexing/models.py)).
- **신설 모듈**: `indexing/candidate_index.py`(vector adapter Protocol·InMemory·`build_candidate_index_record`·`CandidateIndexSyncAdapter`[needs_review→upsert, not-found·transitioned→delete]·`CompositeCandidateIndexSyncAdapter`); `indexing/candidate_lexical_index.py`(`CandidateLexicalRecord`·InMemory·`ElasticsearchCandidateIndexAdapter`[status: needs_review 필터]·`CandidateLexicalIndexSyncAdapter`·`connect_elasticsearch_candidate_index`). ES 설정(nori·replicas 0)은 memory index와 공유, 매핑만 candidate 전용(version 필드 없음).
- **저장소(G1 물리 분리)**: `candidate_vectors` Chroma collection + `candidate_lexical` ES index. `chroma.py`에 `ChromaCandidateVectorIndexAdapter` + round-trip.
- **enqueue choke point(G2)**: `AnalysisService`에 `reindex_outbox`(구조적 `CandidateReindexOutbox` Protocol, MemoryService 선례 대칭) 주입. `record_candidates`가 신규 candidate만(`new_candidates` 리스트) `enqueue_candidate_upserted` — idempotent replay는 미enqueue. `main.py`의 `_default_analysis_service(core_sot, reindex_outbox=sync_outbox)`로 배선(create_app에서 sync_outbox를 analysis보다 먼저 생성하도록 순서 조정).
- **worker(G6)**: `indexing/service.py`에 `enqueue_candidate_upserted`·`CandidateIndexMutationAdapter` Protocol·`IndexSyncWorker(candidate_adapter=…)`·`CANDIDATE_UPSERTED` drain dispatch(미구성 시 RuntimeError). `scripts/index_sync_worker.py`에 `_build_candidate_adapter`(Mongo analysis + embedding + Chroma/fake vector + ES composite) + summary `candidate_backend`.
- **outbox per-target bookkeeping은 미룸**(v1.6.52 정정과 동일 — enqueue는 배포 sink 구성 모름→worker가 configured sink로만 fan-out).
- **회귀 +19**(`tests/test_candidate_index.py`): enqueue choke point(신규/replay/absent) + vector·lexical drain(needs_review upsert / not-found·transitioned delete) + InMemory 랭킹·scope + Chroma round-trip·CRUD + ES 문서·needs_review 필터·멱등 delete + composite fan-out + worker dispatch·unconfigured. **mutation 양방향**: ES `needs_review`→`canonical`로 바꾸면 필터 테스트 재실패(재실증). → pytest 673 passed/45 skip.

### 증분2 — retriever + env 배선 (v1.6.55)

- **신설 retriever**(`context_search/service.py`, canonical과 동형): `VectorCandidateMemoryRetriever`(embed→per candidate_type `query_similar`→`get_candidate` 권위 재유도→needs_review만; `_merge_hits` 단일 풀 cosine), `LexicalCandidateMemoryRetriever`(ES search→권위 재유도), `HybridCandidateMemoryRetriever`(RRF k=60, candidate id dedup). `.retrieve()` 반환 타입(`tuple[AnalysisCandidate, ...]`) 불변 → `_run_candidate_memory_step`/`_item_from_candidate`/Gate 무변경(순수 주입 교체).
- **env 배선**: `main.py`의 `_build_candidate_memory_retriever(analysis)`가 canonical과 **동일 env 스위치**(`_build_vector_candidate_retriever`+`_build_lexical_candidate_retriever`): CHROMA_HOST+EMBEDDING_SERVICE_URL→vector, ELASTICSEARCH_URL→lexical, 둘 다→hybrid, 없으면 종전 `MongoDirectCandidateMemoryRetriever`. 종전 직접 배선을 이 빌더로 교체.
- **회귀 +9**(`tests/test_context_search_candidate_retrieval.py`): vector 권위 재유도+relevance·global limit·query-drives-ranking·stale(removed+transitioned) 격리[under-strict]·단일 풀 병합[over-strict]; lexical needs_review-only·stale skip; hybrid RRF 양신호 융합·id dedup; seam 불변 micro candidate item. **mutation 양방향**: retriever의 `status is NEEDS_REVIEW` 필터 제거 시 stale 격리 테스트 재실패(재실증). → pytest 682 passed/45 skip, git diff --check clean.

### Issues found (b-2)

- 없음. (작업 중 실수: 회귀 mutation 검증 때 `git checkout`으로 tracked `service.py`의 **미커밋 증분2 구현까지** 되돌아가 재적용 필요 → 이후 미커밋 파일 mutation은 파일 재작성이 아닌 인메모리/별도 방식으로 처리.)

### Decisions (b-2)

- **2개 SoT 버전(v1.6.54/55)으로 분리 기록**: 오너가 2증분 독립 커밋을 택했고(G0=A), 색인 파이프라인과 retriever는 독립 회귀 세트를 가진 의미상 구분된 slice라 2B.5(v1.6.45/46) 선례대로 버전을 나눴다.
- **candidate index 물리 분리(G1=A)**: memory index 재사용(kind 판별자) 대신 별도 collection/index — 권위 재유도 source(analysis vs memory store)와 라이프사이클(needs_review 불변 vs superseded self-heal)이 달라 섞으면 필터·삭제 로직이 흐려진다.

### User Decisions and Rationale (b-2)

- 오너가 b-5 완료 후 다음 slice로 **(b-2) candidate retrieval**을 선택. canonical retrieval 스레드의 직접 연장이고 candidate만 Mongo-direct로 남은 비대칭을 닫는다는 점이 근거.
- **G0=A(2증분)**: 색인 파이프라인 신설이 크므로 색인→retriever로 나눠 원장·검증 단위를 관리. **G4=A(vector+lexical+hybrid 한 slice)**: 색인을 이미 composite로 짓는데 retriever만 나누면 원장만 늘어남. 나머지 G1/G2/G3/G5/G6은 canonical 선례를 강하게 따라 추천 A 잠금.

### Next steps (b-2)

- **실 배포 관통(sandbox 밖)**: 전체 스택 기동 시 application이 candidate hybrid retriever를 부팅·서빙하고 worker `_build_candidate_adapter` composite drain이 실 `candidate_vectors`/`candidate_lexical`을 채우는 end-to-end 확인 + candidate backfill(색인 index가 비어도 retriever graceful).
- **candidate hybrid 튜닝**(b-4와 합류): RRF k·per-signal 가중치를 canonical과 함께 캘리브레이션.
- **Phase 6 전이 실발화**: confirmed/rejected 도입 시 candidate de-index(현재 forward-defense stub)가 실제로 도달 — 그때 회귀를 forward-defense에서 실경로로 승격.

---

## 검증 후속 보강 (2026-07-09, 오너 독립 감사 → b-2)

오너 독립 감사(8차원 대항 검증 + completeness critic, `docs/verifications/2026-07-09/candidate_lexical_vector_retrieval_b2.md`)가 b-2 코드·회귀·계약 일관성을 관통한 뒤, actionable 빈 경계 셀 4건 + 문서 정합 3건을 닫았다. 핵심 회귀·mutation 양방향은 작업자 구현대로 재실증됐고(683 → 보강 후 689 passed), 빈 셀만 보강했다.

- **문서 정합 #1 — SoT §Phase3 body prose([system-contract-sot.md:398](../../../docs/system-contract-sot.md#L398))**: "ES analyzer, analysis candidate indexing, actual Elasticsearch mutation, `analysis_completed` sync wiring은 미확정이다" 중 ES analyzer·ES mutation(v1.6.52)·analysis candidate indexing(v1.6.54) 3항은 이미 구현돼 stale. → "`analysis_completed` sync wiring만 미확정"으로 정정(나머지 3항은 구현 버전 명시). b-2 책임항(candidate indexing) 외에 v1.6.52/53 잔존 stale까지 한 문장에서 정합.
- **문서 정합 #2 — SoT §5B body prose([system-contract-sot.md:411](../../../docs/system-contract-sot.md#L411))**: "candidate lexical/vector는 색인 파이프라인 선행 후속"이 v1.6.54/55로 실현돼 stale(버전로그 표는 DONE인데 본문은 pending). v1.6.48/50/51/52/53이 매 slice 이 문장에 clause를 붙인 관례를 b-2가 누락. → v1.6.54(색인 파이프라인)·v1.6.55(vector/lexical/hybrid retrieval) clause 추가.
- **문서 정합 #3 — `CandidateMemoryRetriever` Protocol docstring([service.py:328](../../../services/application/app/context_search/service.py#L328))**: "Mongo-direct now; a later vector/search-engine layer…"가 v1.6.54/55로 실현돼 stale. → backend env 선택 + 권위 재유도 설명으로 갱신.
- **빈 셀 #1 — worker `_build_candidate_adapter` 회귀 부재([index_sync_worker.py:136](../../../scripts/index_sync_worker.py#L136))**: canonical `_build_memory_adapter`는 `test_index_sync_worker_script.py::BuildMemoryAdapterTest`로 잠겨 있으나 candidate builder는 무회귀. → `BuildCandidateAdapterTest` 3분기(no-Chroma→fake / CHROMA_HOST→chroma[G1 `candidate_vectors` collection mutation 재실증] / ELASTICSEARCH_URL→composite) 추가. 증분1 회귀(+3).
- **빈 셀 #2 — composite sink failure 전파 미회귀([candidate_index.py:198](../../../services/application/app/indexing/candidate_index.py#L198))**: docstring "if any sink raises, the entry fails and requeues"가 무회귀(기존 `test_fans_out_to_every_sink`는 비-예외 sink만). → `CompositeDrainTest::test_sink_failure_propagates_not_swallowed`(예외 sink → RuntimeError 전파) 추가.
- **빈 셀 #3 — lexical retriever transitioned-candidate guard + hybrid 단일 backend 저하 미회귀([service.py:472](../../../services/application/app/context_search/service.py#L472))**: vector retriever는 `test_stale_records_are_dropped`로 transitioned 격리를 잠갔으나 lexical retriever는 ghost(not-found)만 있었음(needs_review 필터 forward-defense 빈 셀). hybrid도 양신호만 있고 단일 backend 저하(브리프 G4 검증계획)가 무회귀. → `LexicalRetrieverTest::test_transitioned_candidate_is_dropped`(mutation 재실증)·`HybridRRFTest::test_single_backend_degradation_surfaces_the_other` 추가. 증분2 회귀(+2).
- **빈 셀 #4 — batch `record_candidates` enqueue 미회귀([analysis/service.py:417](../../../services/application/app/analysis/service.py#L417))**: 단수 `record_candidate`가 복수로 위임(service.py:338)하지만 기존 테스트는 N=1만 실행 → production 경로(runner.py:151 배치)의 iteration 로직이 무회귀. 감사가 mutation testing(MUT-A wrong-collection·MUT-C early-return)으로 "batch를 깨도 suite가 green"임을 증명. → `EnqueueChokePointTest::test_batch_record_enqueues_only_new_candidates`(new+new+batch-dup → new만 enqueue) 추가. early-return mutation 재실증(N=1 테스트는 잡지 못함). 증분1 회귀(+1).
- **감사 REFUTED(비결함)**: (a) `record_candidates` 복수 경로 미회귀 의심 → 단수 `record_candidate`가 복수로 위임(service.py:338)해 동일 메서드, production 경로(runner.py:151) 커버. (b) §62 권위필드 배제 미회귀 의심 → `test_context_search_candidate_memory.py`가 이미 `constraints==()`/`do_not_use==()`로 잠금(b-2가 item 생성을 안 바꿔 그대로 유효).
- **관찰(비차단, 추적유지)**: (a) candidate backfill 스크립트 부재(canonical `phase2b5_reindex_memory.py` 대칭 부재) — commit-후-enqueue orphan의 유일 수렴 수단이 없으나 HANDOFF Next Tasks #2가 이미 candidate backfill을 후속으로 추적중. (b) `connect_elasticsearch_candidate_index` 별도 회귀 부재 — nori·replicas 설정은 canonical `connect_` 테스트가 공유 상수로 커버, candidate 매핑만 남아 저값. (c) worker 요약의 `candidate_backend`가 `IndexSyncWorkerScriptTest` fake dict에 없으나 main()이 키를 관대히 다뤄 통과(비-b-2 기존 테스트, 무변).

**재검증**: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **689 passed / 45 skipped**(682 → +7: 증분2 +2[lexical transitioned·hybrid degradation] + 증분1 +5[worker builder×3·composite failure propagation·batch record_candidates enqueue]). mutation 양방향 4건(lexical needs_review 필터·ES needs_review 필터·G1 candidate collection·batch iteration early-return) 재실증. `git diff --check` clean.

**커밋 분할(G0=A)**: 증분1(v1.6.54 색인 파이프라인, +23 회귀) → 증분2(v1.6.55 retriever + 전체 b-2 문서, +11 회귀) 2커밋. `main.py`만 양 증분에 걸쳐(reindex_outbox 배선=증분1 / retriever builder=증분2) hunk 분할; 나머지 문서(SoT·CHANGELOG·work_log·HANDOFF)는 증분2에 일괄.

---

## Phase 7 신규 기획 — 대화형 수정·아이디에이션·저작 감독 (docs 전용)

레포를 다른 작업/검증 AI가 함께 쓰는 중이라 **docs 신규 문서 작성에만** 한정해 진행(코드·SoT·다른 AI 파일 무변).

- **요청(오너 아이디어)**: 생성된 글에 대한 챗봇 확장 — (1) 부분 수정, (2) 아이디에이션 회의, (3) 저작 지시 메타데이터(맥거핀 use/skip·중요도), 내부 컨텍스트 제공은 동일, 분석에도 확장, 생성물은 메모리 캐시가 아닌 DB 단위 관리.
- **진행**: 아이디에이션 문서 `docs/chat-revision-ideation.md` 신규 작성 → 오너와 3라운드 논의로 결정 잠금 → 정식 페이즈 `docs/plans/07-conversational-authoring.md`로 **승격**(plans/README 인덱스·Phase/MVP 표 갱신).
- **잠긴 결정(D1~D10)**: 회의⟂수정 분리(advisory→patch 자동승격 금지) / 3계층 영속(version=명시 시그널) / think 채널 분리 / span⟂mode 직교 / 정보관리 대상=(b) 별개 개체 레지스트리(추출 3종 유지) / directive=저작 감독 모드(macro·micro, micro는 draft patch+memory atomic) / **서사 사실 우선순위 트리(저자 directive > canonical > candidate, latest-win)** / §7 경계(AI 자동 canon 확정 금지, 저자만 override)+Phase 6 공동설계 / importance≠confidence / Core SOT 앵커 계약 재사용.
- **슬라이스**: P1 대화·생성물 영속 → P2 수정 → P5 저작 감독 → P3 아이디에이션 → P4 분석 대화. 순차상 Phase 5(생성)·6(검토) 이후 착수, 슬라이스별 착수 브리프는 구현 시점.
- **검토에서 오너에게 surface한 것(CLAUDE.md §1)**: 분석대화(D)가 근거 없으면 저작 지시(E)로 흡수 / directive는 memory 버전 id 아닌 scope key에 앵커(append-only 고아 방지) / 분위기·톤은 개체 아님(scope key 부적합→scene/style 태그) / timeline은 회상 때문에 전순서 아님(chapter-scene 서수 proxy) / 감독 모드는 Phase 6 review와 중복(공동 설계).

### User Decisions and Rationale (Phase 7 기획)

- 오너가 신규 기능으로 "생성 글에 대한 대화형 부분수정·아이디에이션 + 저작 정보관리(맥거핀 등)"를 제시. 근거: 완전 재생성만 있는 현 구조에 반복 편집 루프가 필요하고, 그러려면 생성물이 DB 1급이어야 함.
- **정보관리 대상 확장 = (b)**(별개 개체 레지스트리): 분석 추출 taxonomy 3종 축소(2A D5=A)를 다시 열지 않고 directive만 별도 레지스트리에 얹는다.
- **directive = 저작 감독 모드 + 우선순위 트리**(오너 제안): "메모리가 메인, 저자가 저장 버전을 감독", latest-win이되 directive에 더 힘("글은 쓰면서 수정된다"). AI는 canon 자동 확정 불가(저자만 override).
- **micro directive 원자성**: draft patch+memory 교정은 같은 것에서 파생이라 한 트랜잭션으로 묶는다.
- **Phase 7로 승격 + 순차 구현**: 페이즈는 순차이므로 5→6→7 순서. 착수 브리프는 지금까지처럼 슬라이스별로.

---

## (b-6) 증분1 — worker compose 서비스 (SoT v1.6.56 예정)

오너가 다음 slice로 **(b-6) worker compose 서비스 + outbox per-sink bookkeeping**를 선택 → 착수 브리프(`plans/04-worker-compose-outbox-bookkeeping-decisions.md`) → 오너 결정(G0=A·G1=A·G2=A·G3=B·G4=B·G5=A·G6=A·#8) → **2증분** 구현·검증. 본 절은 **증분1(worker compose 서비스, G0/G1/G2)**.

### 배경/성격

- v1.6.53(b-5) G6=A가 "worker는 compose 미추가(수동/out-of-band)"로 남기며, "restart/loop 정책·health·중복 실행 설계가 붙어 별도 slice"로 b-6을 지정. 색인 적재 worker가 수동 실행이라 배포에서 ES `memory_lexical`/`candidate_lexical`이 채워지지 않는 gap을, worker를 **상시 compose 서비스**로 올려 닫는다.
- 핵심 계약 사실(워크플로 6에이전트 병렬 조사 + 1차 소스 직독): per-target 필드 `targets: dict[str, IndexSyncTargetState]`가 **이미 존재·영속화되나 inert** — `_enqueue_event`가 모든 이벤트에 단일 placeholder `targets={chroma: PENDING/IN_MEMORY_FAKE}`를 하드코드(`service.py:363-368`), `record_outbox_success`(삭제)·`record_outbox_failure`(whole-event `$set`) 어느 경로도 `targets[].status`를 전이하지 않는다(`mongo_repository.py:155-210`). → 증분2는 "필드 추가"가 아니라 "inert 표면 wire-up". 또한 **중복실행 방지는 이미 claim 계층에 존재** — `claim_next_outbox_entry`가 atomic `find_one_and_update` PENDING→RUNNING + `claimed_at` lease(600s) + stale-reclaim(`mongo_repository.py:118-153`)이라 replica 수와 무관하게 이중 claim 불가 → leader guard 불필요.

### 구현 (증분1 — outbox 모델 미접촉, G5 준수)

- **`service.py`**: `IndexSyncWorker.run_once`에 `stop_check: Callable[[], bool] | None = None` 추가 — for-loop **각 claim 직전** 검사 → 이미 claim된 in-flight entry는 그 iteration 내에서 끝까지 처리되고 **다음 claim 경계**에서 정지. G2=A("현재 entry 처리 완료 후 루프 종료") 정확히 실현. 기본값 None이면 guard short-circuit → one-shot 후진호환 불변.
- **`scripts/index_sync_worker.py`**: `--loop`/`--interval`(기본 30, `INDEX_SYNC_INTERVAL` env override) 추가. `_GracefulShutdown`(SIGTERM/SIGINT → `request` → `is_requested` flag) + `_install_signal_handlers` + `run_loop`(worker를 **1회** build 후 `run_once` 반복: busy(claimed>0)면 즉시 재drain, idle(claimed==0)일 때만 `sleep_fn(interval)`, `stop_check=stop.is_requested` 주입, per-pass JSON emit → `loop_started`/`pass`/`loop_stopped`). `_build_index_sync_worker` 추출(양 경로 공유). `main`이 `--loop` 시 handler install + `run_loop`, 아니면 종전 one-shot. exit-code map 양 모드 보존(0/2).
- **`docker-compose.yml`**: `worker` 서비스 추가 — application 이미지 공유, `command: python scripts/index_sync_worker.py --loop`, env(CORE_SOT_MONGO_URI/EMBEDDING_SERVICE_URL/CHROMA_HOST/ELASTICSEARCH_URL/INDEX_SYNC_INTERVAL), `depends_on` mongo/embedding/chroma/elasticsearch `service_healthy`, `restart: unless-stopped`, `stop_grace_period: 120s`(composite 순차 fan-out 합 timeout 초과 방지 — 3-1 경계). healthcheck 없음(G1=A).
- **`services/application/Dockerfile`**: `COPY scripts/ ./scripts/` 추가(`COPY services/` 후 — deps 캐시 레이어 보존). **`.dockerignore`**: `scripts/` 제외 해제(worker 공유 이미지에 필요).

### 회귀 +10

- `test_indexing_phase3a.py::IndexSyncWorkerTest::test_run_once_stop_check_finishes_in_flight_entry_then_stops`: 3 시나리오(baseline full / stop_after_first→claimed=1·succeeded=1·잔여 2 / never_stop→claimed=3) **양방향** pin.
- `test_index_sync_worker_script.py::WorkerLoopTest`(3)·`ParseArgsLoopTest`(2).
- **검증 후속 보강 +4**(`Increment1SignalAndEdgeTest`, 오너 독립 감사 2-1/2-2 폐쇄): `test_install_signal_handlers_binds_stop_request`(SIGTERM/SIGINT→`stop.request` 등록)·`test_real_sigterm_flips_stop_flag`(실 `os.kill(SIGTERM)` → flag flip end-to-end) — **2-1 blocking test-gap 폐쇄**; `test_run_loop_exits_immediately_if_stop_already_requested`(退化: stop 선요청 시 passes=0·sleep 0)·`test_interval_reads_index_sync_interval_env`(env override) — 2-2 폐쇄. mutation 양방향: handler 미등록/stop_check 무시 시 각 재실패.

### 검증

- `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **699 passed / 45 skipped**(689 baseline → 증분1 +10). `git diff --check` clean.
- worker 이미지 빌드 + 이미지 내 `scripts.index_sync_worker`/`run_loop` import 확인. `docker compose config` `worker` 서비스 파싱 OK.
- **실 Mongo end-to-end drain smoke**(격리 standalone mongo:27117): entry 적재 → `--loop` → pass1 claimed=1/succeeded=1(drain) → pass2-5 idle → SIGTERM → `loop_stopped passes=5`·exit 0·outbox 0·success log.
- **오너 독립 감사**(`docs/verifications/2026-07-09/worker_compose_increment1_b6.md`): 6 감사자 + 반박 21건 전부 CONFIRMED, 독립 실 Mongo smoke(27018) 재현 → **조건부 합격**, 구현 결함 0.

### 검증 후속 보강 (오너 독립 감사 → 조건부→합격 전제 폐쇄)

- **6-1(브리프 G2 lease-release 자기모순, blocking)**: 결정 본문은 "finish-in-flight + lease 유지"인데 검증계획/한계#2/질문#3에 "lease-release → PENDING 복귀" 잔존. 구현은 canonical(finish-in-flight)을 따르고 있었으므로 **브리프 4곳 정정**(lease-release 언급 제거/수정). 오너 확인 대기.
- **6-3(HANDOFF 능동 모순)**: "worker는 compose 서비스가 아니다"가 신규 코드와 정면 충돌 → HANDOFF 현행(worker 상시 compose 서비스)으로 정정.
- **6-5(#8 정정)**: `docs/verifications/2026-07-08/canonical_memory_lexical_hybrid_rrf.md`의 "envelope `targets.chroma.status`가 combined 결과 반영"이 1차 소스와 모순(targets.status 결코 전이 안 됨) → **[2026-07-09 정정]** 마킹 후 사실 정정.
- **2-1/2-2**: 상기 +4 보강 테스트로 폐쇄. **3-1(비차단)**: `stop_grace_period` 60s→**120s** 상향 + 관계 주석. `INDEX_SYNC_INTERVAL`(30) < grace 만족.

### Decisions / Next steps

- **stop_check로 finish-in-flight 실현**(G2=A): lease-release(강제 PENDING 복귀)가 아닌 run_once 내 stop_check로 현재 entry 완료 후 다음 claim 경계 종료. lease 600s 유지(ungraceful crash만 bound).
- **오너 결정 대기**: (1) 6-1 방향 확정(finish-in-flight = a 확정), (2) SoT v1.6.56 bump + CHANGELOG 타이밍(즉시 vs 증분2 일괄 — b-2 선례는 증분2 일괄).
- **증분2(v1.6.57, G3=B/G4=B per-sink bookkeeping)**: `IndexSyncTargetState` per-sink `attempt_count`/`last_error` 확장 + composite all-or-nothing→per-sink outcome 전환 + worker claim 시 sink target materialize·갱신 + **all-terminal 시 entry 삭제** + per-sink 재시도 예산 + dedup 조정 + `test_sink_failure_propagates_not_swallowed` 재방문.
- **실 배포 관통(sandbox 밖)**: 전체 스택 기동 시 worker 서비스가 hybrid composite drain으로 실 `memory_lexical`/`candidate_lexical`을 채우는 end-to-end.

## (b-6) 증분2 — outbox per-sink bookkeeping (SoT v1.6.57)

### 배경/성격

- 브리프 `plans/04-worker-compose-outbox-bookkeeping-decisions.md`(Resolved) 잠긴 결정 **G3=B / G4=B / G6=A**로 오너 재확인 없이 착수. v1.6.52/54가 두 번 미룬 per-target bookkeeping를 해소하는 슬라이스.
- **핵심 사실(검증 확정)**: outbox `targets` 필드는 이미 존재·round-trip 되나 **inert**였다 — `record_outbox_success`=entry 즉시 삭제, `record_outbox_failure`=whole-event `$set`, 어느 쪽도 `targets[].status`를 전이하지 않음. 따라서 이 증분은 "필드 신설"이 아니라 "inert 표면을 worker가 실제로 갱신하도록 wire-up"이다.
- **성격**: 성공-경로 dedup 의미가 "성공=즉시 삭제"에서 "all-terminal 삭제"로 이동하고 `IndexSyncRepository` Protocol에 per-target 표면이 추가됨(changelog 대상). **새 SoT public literal 없음**(G6=A — 내부 `IndexSyncStatus` + free-form target key `"vector"`/`"lexical"` 재사용). enqueue의 sink-agnosticism은 targets를 빈 dict로 두고 worker가 claim 시 configured sink를 materialize하는 것으로 보존.

### 구현

- `indexing/models.py`: `IndexSyncTargetState`에 per-sink `attempt_count`/`last_error` 추가, `backend`를 `IndexSyncBackend`→`str` 완화(ES `"elasticsearch"` 허용, enum member 미추가). 신설 `SinkOutcome`(target/backend/ok/error). `IndexSyncLastError`를 `IndexSyncTargetState` 위로 이동(참조 순서).
- `indexing/service.py`: 상수 `VECTOR_TARGET`/`LEXICAL_TARGET`/`ELASTICSEARCH_BACKEND`·`_PER_SINK_EVENTS`. `_enqueue_event`가 placeholder targets → **빈 dict**. `IndexSyncWorker.run_once`가 event 종류로 분기 — `_drain_archive`(단일-sink whole-event, 종전 동작 보존) vs `_drain_sinks`(per-sink). `_drain_sinks`는 `skip=SUCCESS targets` 계산 → `adapter.drain(entry, skip=)` → `_merge_target_states`(SUCCESS sink 동결·outcome sink attempt_count+1) → `_classify_targets`(all-SUCCESS=삭제 / all-terminal=삭제 / else=requeue). `record_outbox_success`/`record_outbox_failure`에 `targets`/`terminal` optional 인자 추가(archive는 미전달 후진호환). `_Disposition` enum·`_backend_error` 헬퍼. `CHROMA_TARGET` 상수·`IndexSyncBackend` import 제거(내 변경이 만든 orphan).
- `indexing/memory_index.py`·`candidate_index.py`: composite 생성자가 `(target, backend, adapter)` named sink 튜플을 받고, `index_memory`/`index_candidate`(all-or-nothing raise) → `drain(entry, *, skip)`(각 sink try/except → `SinkOutcome` tuple, skip된 SUCCESS sink 미실행)으로 전환.
- `indexing/mongo_repository.py`: `_target_state_doc`/`_to_target_state` str backend·attempt_count·last_error round-trip; `record_outbox_success`/`record_outbox_failure` per-sink(targets/terminal) 지원, failure requeue 시 `targets` `$set` 영속. `IndexSyncBackend` import 제거.
- `scripts/index_sync_worker.py`: `_build_memory_adapter`/`_build_candidate_adapter`가 ES 무관 **항상 composite**(단일 vector sink or vector+lexical, named sink) 반환 → worker가 per-sink를 균일 처리.

### 회귀

- `tests/test_candidate_index.py`: `test_sink_failure_propagates_not_swallowed`(all-or-nothing propagate) → `test_sink_failure_is_isolated_not_swallowed_not_propagated`(per-sink 격리 — healthy ok=True·failing ok=False+BACKEND_ERROR, 양방향). 신설 `test_drain_skips_already_succeeded_targets`(over-strict: skip된 sink 미실행). 신설 `PerSinkBookkeepingTest`: (1) failing lexical이 자기만 requeue하며 per-sink attempt 1→2→3, healthy vector는 **미재색인**(calls==1), attempt 3==max에서 all-terminal → entry 삭제(under+over-strict); (2) transient 실패가 복구되면 all-SUCCESS로 entry 삭제(DLQ 아님). WorkerDispatch는 composite 경유로 갱신 + all-success 삭제 확인.
- enqueue 빈 targets: `test_indexing_phase3a`(assert `targets == {}`)·`test_indexing_mongo`(Mongo round-trip 빈 targets). composite drain: `test_context_search_memory_lexical_retrieval`. builder 항상-composite: `test_index_sync_worker_script`(vector leaf = `_sinks[0][2]`, named sink identity). worker construction: `test_memory_vector_index`(`_memory_composite` 헬퍼로 래핑).
- `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **703 passed / 45 skipped**, `git diff --check` clean.

### 수용 한계 / Next steps (b-6)

- **ES-lexical backfill 부재**: backfill(`phase2b5_reindex_memory.py`)은 vector-only. G4-B 아래 per-sink-max로 terminal drop된 ES 실패는 수렴 수단이 없다(accepted limitation) — ES-lexical backfill 스크립트는 별도 후속.
- **실 배포 per-sink 관통(sandbox 밖)**: 전체 스택에서 한 sink만 죽였을 때 outbox `targets`가 per-sink 상태를 반영하고 healthy sink가 재색인되지 않는지 end-to-end 확인.
- commit-후-enqueue skew(transaction 부재)는 증분2가 넓히지 않음(빈 targets는 enqueue를 더 단순하게 함).
