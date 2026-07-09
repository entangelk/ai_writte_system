# 착수 결정 브리프 — compose 전용 ES 서비스 (배포 lexical/hybrid 발화)

**상태**: `Resolved` (2026-07-09 오너 결정 — G0~G6 전부 추천 A)

## 오너 결정 (2026-07-09)

- **G0 = A**: compose에 ES 서비스 추가 + application `ELASTICSEARCH_URL` 배선. worker는 out-of-band 유지.
- **G1 = A**: 자체 `services/elasticsearch/Dockerfile`(공식 ES 8.13.4 + `elasticsearch-plugin install --batch analysis-nori`). repo 재현 가능·버전 핀. 로컬 harness 이미지 재사용은 거부(재현 불가).
- **G2 = A**: `${ELASTICSEARCH_VERSION:-8.13.4}`(live smoke nori 검증 버전, chroma `CHROMA_VERSION` 선례 대칭).
- **G3 = A**: `discovery.type=single-node` + `xpack.security.enabled=false`. 코드가 무인증 plaintext이고 MVP 단일 사용자. 보안 ON은 인증 slice 선행 필요(범위 밖).
- **G5 = A**: `connect_elasticsearch_memory_index`에 `request_timeout`(기본 30) 추가 → 앱/worker 부팅 시 cold nori create timeout 방지. v1.6.52 smoke 견고화 대칭. 미지정 호출자(main.py/worker)는 기본 30 자동 상속(§2 최소 변경).
- **G6 = A**: worker는 compose에 미추가(기존 Chroma reindex와 동일 out-of-band). retriever는 인덱스 비어도 graceful.

---

(원 브리프 — 참고)

**상태**: `Discussion` (오너 결정 대기)
**정본 SoT**: `docs/system-contract-sot.md` (현재 v1.6.52)
**선행 브리프**: `04-writing-memory-lexical-retrieval-decisions.md`(Resolved — v1.6.52 lexical/hybrid 코드 완성, "compose 전용 ES 서비스는 후속"으로 명시 위임).
**아이디에이션 근거**: SoT 아키텍처 표(`system-contract-sot.md:130` Elasticsearch = canonical memory lexical/metadata index), HANDOFF Next Tasks #1 (b-5).

---

## 왜 지금 열리나

v1.6.52가 canonical memory retrieval의 **ES lexical + hybrid(RRF) 코드**를 완성했다. application `_build_lexical_canonical_retriever`([main.py:471](../../services/application/app/main.py#L471))와 worker([index_sync_worker.py:109](../../scripts/index_sync_worker.py#L109))가 이미 `ELASTICSEARCH_URL`(+ `ELASTICSEARCH_MEMORY_INDEX`)를 읽어 lexical/hybrid로 자동 승격한다. 그러나 **compose 스택에 ES 서비스가 없어** 배포에서 이 경로가 영구 미발화(env 미설정→Mongo-direct/ vector-only fallback)다. 이 slice는 **인프라만** 채워 배포에서 lexical/hybrid가 실동작하게 한다.

## 현재 확정된 경계 (사실 — 코드·인프라 재확인)

- **코드는 완성·회귀 잠금됨.** 이 slice에 새 앱 로직 없음. 배선 표면은 env 2개(`ELASTICSEARCH_URL` 필수, `ELASTICSEARCH_MEMORY_INDEX` 선택, 기본 `MEMORY_LEXICAL_INDEX`)뿐.
- **공식 ES 이미지에 nori 미포함(핵심).** analysis-nori는 코어 번들이 아니라 플러그인이다. 머신의 테스트 컨테이너 이미지명이 `tf-ai-harness-elasticsearch-step1-nori:8.13.4`인 것이 방증 — nori를 심은 **커스텀 이미지**다. 배포 ES도 `elasticsearch-plugin install analysis-nori`를 심은 자체 빌드 이미지가 필요하다.
- **ES 8.x 보안 기본 ON.** 8.x는 TLS+비밀번호가 기본 켜짐. 코드는 `Elasticsearch(url)` **plaintext·무인증**([memory_lexical_index.py:293](../../services/application/app/indexing/memory_lexical_index.py#L293))이라 배포 ES도 `xpack.security.enabled=false`여야 계약과 맞다(테스트 컨테이너·MVP 단일 사용자와 동일 자세).
- **인덱스 생성은 앱/worker가 lazy로 한다.** `connect_elasticsearch_memory_index`가 없으면 nori 인덱스를 생성. 앱 부팅 시 `_build_lexical_canonical_retriever`가 이 경로를 탄다. `Elasticsearch(url)` 기본 `request_timeout`=10s인데 cold nori create는 ~4s(부하 시 초과 가능) — v1.6.52 live smoke가 정확히 이 이유로 `request_timeout=30`으로 견고화됐으나 **production `connect_` 경로는 아직 기본 10s**다.
- **worker는 compose 서비스가 아니다.** `index_sync_worker.py`는 수동/out-of-band 실행(2B.5 Chroma memory reindex도 동일). 즉 compose에서 lexical **retrieval**은 되지만 ES **색인 적재**는 worker를 돌려야 채워진다 — 기존 Chroma 자세와 동일(비면 retriever가 graceful empty).
- **테스트는 기존 컨테이너 유지.** 회귀·live smoke는 머신의 `tf-ai-harness-elasticsearch-step1`(9201, nori, ephemeral 네임스페이스)를 계속 쓴다. 배포 ES는 **별개** 서비스다(선행 브리프 E5 제외 항목 그대로).

---

## ⚠ 헤드라인 긴장 (임의 구현 없이 surface — CLAUDE.md §1)

### 긴장 1 — nori 커스텀 이미지 필요 (재현성 vs 로컬 이미지 재사용)
공식 이미지에 nori가 없으니 배포 ES는 자체 Dockerfile(`FROM …/elasticsearch:8.13.4` + `elasticsearch-plugin install --batch analysis-nori`)이 필요하다. 머신의 `…-nori:8.13.4` 로컬 이미지를 그냥 재사용하는 건 **repo 재현 불가**(외부 harness 산출물)라 배포용으론 부적합.

### 긴장 2 — 배포 기본이 hybrid로 바뀐다
application에 이미 `CHROMA_HOST`+`EMBEDDING_SERVICE_URL`가 있어 `ELASTICSEARCH_URL`를 더하면 canonical retriever 기본이 **hybrid(RRF)**가 된다(vector+lexical). 이게 이 slice의 목적이지만, 배포 기본값 변경이므로 명시 확인이 필요.

### 긴장 3 — 앱 부팅 시 인덱스 생성 timeout (작은 코드 터치)
production `connect_elasticsearch_memory_index`가 기본 10s timeout이라, cold ES에 앱이 붙어 nori 인덱스를 만들 때 `ConnectionTimeout` 위험. `depends_on: service_healthy`가 ES ready를 보장하지만 인덱스 create 자체 시간은 별개. smoke는 이미 `request_timeout=30`으로 고쳤다 — production 경로도 같게 할지(작은 코드 터치)가 결정 대상.

---

## 결정 필요 항목

### G0 — slice 경계
- **A(추천)**: compose에 ES 서비스 추가 + application에 `ELASTICSEARCH_URL` 배선(+ `depends_on`). worker는 out-of-band 유지(기존 Chroma memory reindex와 동일 자세, §2 범위 유지).
- B: worker까지 compose 서비스로 추가 → G4 참조(범위 확대).
- 추천: **A**.

### G1 — nori 이미지 [헤드라인 1]
- **A(추천)**: 자체 `services/elasticsearch/Dockerfile`(`FROM docker.elastic.co/elasticsearch/elasticsearch:${ES_VERSION}` + `bin/elasticsearch-plugin install --batch analysis-nori`). compose `build:` 컨텍스트로 빌드. 재현 가능·버전 핀.
- B: 머신의 기존 `…-nori:8.13.4` 이미지를 compose `image:`로 재사용 — repo 밖 산출물이라 재현·이식 불가. 거부.
- 추천: **A**.

### G2 — 버전 핀
- **A(추천)**: `8.13.4`(v1.6.52 live smoke에서 nori 관통 검증된 버전) with `${ELASTICSEARCH_VERSION:-8.13.4}` override(chroma의 `CHROMA_VERSION` 선례 대칭).
- 추천: **A**.

### G3 — 보안/인증 [헤드라인, 코드 계약 종속]
- **A(추천)**: `discovery.type=single-node` + `xpack.security.enabled=false`. 코드가 무인증 plaintext이고 MVP는 단일 사용자·로컬(HANDOFF Active Decisions "계정/인증 없는 단일 사용자")이며 테스트 컨테이너와 동일 자세. 보안 강화는 인증 도입(Phase 밖) 시 별도.
- B: 보안 ON(TLS+auth) — 코드에 auth/cert 배선이 없어 지금은 앱이 못 붙음. 인증 slice 선행 필요. 거부(범위 밖).
- 추천: **A**.

### G4 — application 배선 & 배포 기본값 [헤드라인 2]
- **A(추천)**: application env에 `ELASTICSEARCH_URL: http://elasticsearch:9200` + `depends_on: elasticsearch: service_healthy`. 결과: 배포 canonical retriever 기본 = **hybrid(RRF)**(vector+lexical). 이 slice의 목적.
- B: env는 주석 처리로 두고 opt-in(오버라이드 파일) — lexical/hybrid를 배포 기본에서 빼면 slice가 무의미(발화 안 됨).
- 추천: **A**.

### G5 — 인덱스 생성 견고성 [헤드라인 3, 코드 터치]
- **A(추천)**: `connect_elasticsearch_memory_index`(+ `Elasticsearch(url)`)에 `request_timeout`(기본 30s)을 추가해 앱/worker 부팅 시 cold nori create timeout을 막는다. v1.6.52 smoke 견고화와 대칭. 작은 코드 터치 + 회귀 1(client kwargs 전달 확인). *(정본 결정 §G5는 env override를 넣지 않고 기본 30 + param만 둔다 — §2 최소 변경. 구현이 이를 따름.)*
- B: 코드 무변, `depends_on: service_healthy`만 의존 — ES는 ready여도 create 시간 자체가 10s 넘으면 부팅 실패 잔존.
- 추천: **A** (배포 견고성이 이 slice 목적의 일부).

### G6 — worker compose 서비스 [G0-B]
- **A(추천, 안 함)**: worker 미추가. ES 색인 적재는 기존처럼 수동 `index_sync_worker.py`(Chroma reindex와 동일). retriever는 인덱스 비어도 graceful empty. §2 범위 유지.
- B: `worker` 서비스 추가(ES+Chroma drain 주기 실행) — restart/loop 정책·health·중복 실행 설계가 붙어 별도 slice 규모. 후속.
- 추천: **A**.

---

## 제안 slice 범위 (추천값 기준)
**포함**: `services/elasticsearch/Dockerfile`(nori) + `docker-compose.yml`에 `elasticsearch` 서비스(single-node, 보안 off, healthcheck, volume, heap) + application `ELASTICSEARCH_URL` 배선 + `depends_on` + (G5=A 시) `connect_` request_timeout + 회귀/문서.
**제외(후속)**: worker compose 서비스, hybrid 파라미터 튜닝(b-4), candidate lexical/vector(b-2), outbox per-target bookkeeping.

## 검증 계획 (구현 시)
- **compose 정적 검증**: `docker compose config`로 스키마·해석 확인(빌드 없이). ES 서비스·env·depends_on·healthcheck 정상 파싱.
- **(가능 시) 실 bring-up**: `docker compose build elasticsearch && docker compose up -d elasticsearch` → nori 플러그인 로드 확인(`_cat/plugins`), cluster health, application이 붙어 hybrid 발화. sandbox에서 docker 가용하면 이 slice에서 닫고, 아니면 out-of-band로 위임.
- **코드 회귀(G5=A 시)**: `connect_elasticsearch_memory_index`가 `request_timeout`을 client에 전달함을 fake client로 잠금. 기존 lexical/hybrid 회귀(651)는 무변(인프라 변경).
- **문서**: HANDOFF Project Structure에 `services/elasticsearch/`·compose ES 반영, runbook 필요 시 갱신.

## 열린 질문 (오너에게)
1. **G1**: 배포 ES를 자체 nori Dockerfile로 빌드(A)하는 데 동의하는가, 아니면 다른 이미지 전략?
2. **G3**: 로컬 MVP 배포 ES를 보안 off(single-node, 무인증)로 두는 데 동의하는가(코드가 무인증이라 A가 사실상 강제)?
3. **G5**: 앱/worker 부팅 시 nori 인덱스 생성 timeout을 막게 production `connect_`에 `request_timeout=30`을 더할까(A, 작은 코드 터치), 아니면 인프라만 손대고 코드 무변(B)?
4. **G6**: worker는 compose에 안 넣고 수동 유지(A)에 동의하는가?
