# Work Log — 2026-07-09

## Goals

- HANDOFF와 2026-07-08 work log를 읽고 다음 작업을 진행한다.
- 오너가 다음 slice로 **(b-5) compose 전용 ES 서비스**를 선택 → 착수 브리프 → 오너 결정 → 구현·검증.

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
