# 검증 기록 — (b-5) compose 전용 ES 서비스 (배포 lexical/hybrid 발화)

## Subject metadata

- **날짜**: 2026-07-09
- **요청자**: 오너("작업 AI가 작업한거 확인하고 검증하고 의심하고 또 의심해줄래?")
- **검증자**: Claude(독립 감사 — 구현 작업자와 별개)
- **대상 slice/artifact**: (b-5) compose 전용 Elasticsearch 서비스 + `connect_elasticsearch_memory_index` `request_timeout` 견고화. SoT v1.6.53.
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.6.53(버전 로그 행) + 착수 브리프 `docs/plans/04-compose-elasticsearch-service-decisions.md`(Resolved, 오너 결정 G0~G6=A).
- **검증 대상 work 출처**: working tree, uncommitted(`git status` — 6 modified + 3 untracked; commit hash 없음).

## Scope

이 slice는 "배포 인프라 + 소폭 견고성 코드"이며 계약 literal/public 표면 변경을 **하지 않는다**고 선언됨. 검증 표면:

1. **계약(브리프 G0~G6=A)** — 경계 매트릭스 빌드 및 교차 검증.
2. **구현 코드** — `services/application/app/indexing/memory_lexical_index.py`(`connect_elasticsearch_memory_index` 변경).
3. **인프라** — `services/elasticsearch/Dockerfile`, `docker-compose.yml`(`elasticsearch` 서비스 + application 배선).
4. **회귀 테스트** — `tests/test_context_search_memory_lexical_retrieval.py::ConnectElasticsearchTest`(+3) 및 교차 pin(`tests/test_index_sync_worker_script.py`).
5. **실 bring-up 표면** — nori 플러그인 로드, cluster health, 앱 `connect_` 경로 실 ES 인덱스 생성(unit test는 fake client만 사용하므로 실 ES 관통이 유일한 end-to-end 증거).
6. **문서** — SoT v1.6.53(버전 로그 + Phase 4 prose), CHANGELOG backfill(v1.6.51/v1.6.52), HANDOFF, work_log.
7. **"계약 literal 변경 없음" 주장** — SoT diff가 이를 지지하는지.

## Methodology

- **계약 scope 선행**: 브리프(`04-compose-elasticsearch-service-decisions.md`)의 오너 결정(G0~G6=A, 문서 상단)을 정본으로 하고, 논의 절("(원 브리프 — 참고)")은 참고로 취급. SoT v1.6.53 버전 로그 행과 교차.
- **경계 매트릭스**: 각 G 결정의 "should fire"(코드/인프라가 해야 할 것)·"should NOT fire"(하면 안 되는 것) literal을 코드에서 추적. 빈 셀 = blocking.
- **literal 정합**: 브리프/SoT literal이 코드에 변경 없이 나타나는지. paraphrase 불허.
- **테스트 코드 감사**: 테스트가 계약을 진정 pin하는지, under-strict/over-strict 양방향 guard 존재, assertion이 public 표면을 겨냥하는지.
- **mutation 양방향 재실증(독립)**: `connect_`의 `request_timeout`을 `10`으로 하드코드 → (a) default guard·(b) plumbing guard 양쪽 재실패 확인 → 복원 → 재통과. 백업/복원으로 working tree 보존.
- **실 bring-up 재현(독립)**: cached 이미지로 `docker compose up -d elasticsearch` → `_cat/plugins`·`_cluster/health` probe → `PYTHONPATH=. python3`로 `connect_elasticsearch_memory_index` 호출해 실 ES에 nori 인덱스 생성·검증·삭제 → 컨테이너·볼륨 정리(잔여 0).
- **호출부 무변경 주장**: `git diff` 대상 파일 목록 + 호출부 소스 읽기 + 기존 worker 회귀가 `url=/index_name=` 호출을 pin하는지 교차 확인.

실행한 명령(재현 가능):
```
docker compose config --quiet
python3 -m pytest -q tests/test_context_search_memory_lexical_retrieval.py::ConnectElasticsearchTest
python3 -m pytest -q --ignore=tests/test_memory_mongo.py
git diff --check
# mutation: cp 백업 → sed 's/...request_timeout=request_timeout)/...request_timeout=10)/' → pytest → cp 복원 → pytest
# bring-up: docker compose up -d elasticsearch; curl _cat/plugins; curl _cluster/health;
#   PYTHONPATH=. python3 -c '...connect_elasticsearch_memory_index(url=..., index_name=ephemeral)...'
#   docker compose down; docker volume rm ai_writte_system_es_data
```

## Findings

### 1. 계약(브리프 G0~G6=A) ↔ 구현/인프라 정합

경계 매트릭스(모든 셀 추적 완료, 빈 셀 없음):

| 결정 | literal(should fire) | 코드/인프라 추적 | should NOT fire | 확인 |
|---|---|---|---|---|
| G0=A | compose에 ES 서비스 + application `ELASTICSEARCH_URL` 배선; worker out-of-band | `docker-compose.yml:160` `elasticsearch:` 서비스, `:48` `ELASTICSEARCH_URL`; `grep worker docker-compose.yml` → 무 | worker compose 서비스 추가 | ✓ |
| G1=A | `FROM docker.elastic.co/elasticsearch/elasticsearch:${ES_VERSION}` + `bin/elasticsearch-plugin install --batch analysis-nori` | `services/elasticsearch/Dockerfile:8,10` verbatim | 로컬 harness 이미지 재사용 | ✓ |
| G2=A | `${ELASTICSEARCH_VERSION:-8.13.4}` | Dockerfile `ARG`(line 7) + compose build arg(`docker-compose.yml` build.args) | — | ✓ |
| G3=A | `discovery.type=single-node` + `xpack.security.enabled=false` | compose env(둘 다 설정) | 보안 ON | ✓ |
| G4=A | app `ELASTICSEARCH_URL: http://elasticsearch:9200` + `depends_on: elasticsearch: service_healthy` → 배포 기본=hybrid | compose `:48` + depends_on; `main.py:436-439` 둘 다 non-None→`HybridCanonicalMemoryRetriever`; app env에 `EMBEDDING_SERVICE_URL`+`CHROMA_HOST` 이미 존재 | — | ✓ |
| G5=A | `connect_` `request_timeout`(기본 30) 추가, client에 전달; 미지정 호출자는 기본 30 상속 | `memory_lexical_index.py:285`(signature `request_timeout: int = 30`)·`:298`(`Elasticsearch(url, request_timeout=request_timeout)`); main.py:478·worker:122 `request_timeout` 미전달(기본 상속) | 호출부 변경 | ✓ |
| G6=A | worker compose 미추가 | `grep worker docker-compose.yml` → 무 | worker 서비스 | ✓ |

G1/G3의 "공식 이미지에 nori 미포함"/"코드가 무인증 plaintext" 전제도 코드(`memory_lexical_index.py:298` `Elasticsearch(url, ...)` 무인증)와 정합.

### 2. 구현 코드 — `connect_elasticsearch_memory_index`

- `memory_lexical_index.py:284-305`: signature `(*, url, index_name, request_timeout: int = 30)`, 본문 `Elasticsearch(url, request_timeout=request_timeout)` → `indices.exists` → 부재 시 `indices.create(index=, settings=ELASTICSEARCH_MEMORY_SETTINGS, mappings=ELASTICSEARCH_MEMORY_MAPPINGS)`. 브리프 G5=A(정본 line 11)와 정합.
- 상수 정합: `ELASTICSEARCH_MEMORY_SETTINGS`(line 228-230) = `{"analysis": {"analyzer": {"korean": {"type": "nori"}}}}` — 테스트가 단언하는 값과 verbatim 일치.
- 호출부 무변경 주장 **사실**: main.py:478-483·`scripts/index_sync_worker.py:122-127`은 둘 다 `url=`/`index_name=` 키워드 호출에 `request_timeout` 미전달 → 기본 30 상속. `git diff` 대상 6개 파일에 main.py·worker **미포함**(무변경). 게다가 `tests/test_index_sync_worker_script.py:172` `connect.assert_called_once_with(url="http://es:9200", index_name="memory_lexical")`가 worker가 `request_timeout` 없이 호출함을 v1.6.52부터 이미 pin → 본 slice의 무변경을 교차 확인.
- §2 정당성: 브리프 논의 절(line 80)의 "env override 가능"은 구현에 **없음**. 작업자는 §2(요청 없는 configurability 금지)를 이유로 기본 30 + param만 두었다고 기록. 정본 오너 결정(line 11)은 "request_timeout(기본 30) 추가"만 명시하므로 구현은 정본과 일치(아래 Issues 참조).

### 3. 인프라 — Dockerfile / compose

- `services/elasticsearch/Dockerfile:7-10`: `ARG ELASTICSEARCH_VERSION=8.13.4` → `FROM docker.elastic.co/elasticsearch/elasticsearch:${ELASTICSEARCH_VERSION}` → `RUN bin/elasticsearch-plugin install --batch analysis-nori`. G1=A verbatim.
- `docker-compose.yml:160-181` `elasticsearch` 서비스: `build`(context·args), env `discovery.type=single-node`·`xpack.security.enabled=false`·`ES_JAVA_OPTS`, port `${ELASTICSEARCH_PORT:-9200}:9200`, `es_data` 볼륨, curl `_cluster/health` healthcheck(start_period 60s·retries 20). volume 선언 `:197`. `docker compose config --quiet` exit=0(정상 파싱).
- application 배선 `:48` `ELASTICSEARCH_URL: "http://elasticsearch:9200"` + depends_on `service_healthy`.

### 4. 회귀 테스트 — ConnectElasticsearchTest(`tests/test_context_search_memory_lexical_retrieval.py:182-240`)

테스트 코드 감사(테스트는 감사 대상, not 감사자):
- `test_default_request_timeout_is_30_and_creates_nori_index_when_absent`(line 222): default `request_timeout==30`(under-strict: 하드코드 시 재실패) + nori settings(`ELASTICSEARCH_MEMORY_SETTINGS` 상수에 grounding). ✓
- `test_request_timeout_is_plumbed_not_hardcoded`(line 232): `request_timeout=5` 전달 → `es.request_timeout==5`(over-strict: 상수 하드코드 시 재실패). ✓
- `test_existing_index_is_not_recreated`(line 237): `exists=True` → `created is None`(멱등). ✓
- **mutation 양방향(독립 재실증)**: `Elasticsearch(url, request_timeout=10)` 하드코드 → (a)·(b) FAIL(30≠10, 5≠10), (c) PASS = "2 failed, 1 passed" → 복원 → 3 passed. 작업자 주장과 정확히 일치. working tree는 백업/복원으로 보존(git diff 8 insertions/3 deletions, 의도 변경만).
- assertion은 호출자가 의존하는 public 표면(connect_ factory + 인덱스 create 동작)을 겨냥. ✓
- nuance(비차단): fake factory `def factory(url, *, request_timeout)`가 `request_timeout`을 필수(keyword-only, 기본값 없음)로 받으므로, 구 코드 `Elasticsearch(url)`(request_timeout 미전달)로 되돌리면 assertion이 아닌 TypeError로 ERROR. "되돌리면 실패" guard는 유효하나 경로가 assertion이 아닌 error. 허용 범위.

### 5. 실 bring-up 표면(독립 재현)

- `docker compose up -d elasticsearch`(cached 이미지) → healthy.
- `curl _cat/plugins` = `analysis-nori 8.13.4` → nori 플러그인 로드 확인(Dockerfile이 실동작).
- `curl _cluster/health` = `status:green`(단, `active_primary_shards:0` — 인덱스 없는 빈 클러스터).
- `PYTHONPATH=. python3`로 `connect_elasticsearch_memory_index(url=..., index_name="ai_writte_verify_b5")`(기본 timeout) 호출 → 인덱스 생성 → `GET /idx/_settings`의 analyzer = `{'korean': {'type': 'nori'}}` 확인 → 인덱스 삭제. 앱 connect_ 경로가 실 ES에 nori 인덱스를 생성함을 end-to-end로 확인(unit test fake가 아닌 실 관통).
- 정리: `docker compose down` + `docker volume rm ai_writte_system_es_data` → 컨테이너·볼륨 잔여 0, 9200 down. `/tmp` 백업도 제거.

### 6. "계약 literal 변경 없음" 주장

- SoT diff(`docs/system-contract-sot.md`): 버전 `v1.6.52→v1.6.53`, 갱신일 변경, 신규 버전 로그 행(v1.6.53, 설명적), Phase 4 prose 1문장 추가("v1.6.53으로 ... compose 전용 ES 서비스(nori)가 추가됐다" — 설명적). 새 enum/field/decision_status/policy path/threshold **없음**. 주장 지지됨. ✓
- Phase 4 prose 추가는 "배포 표면 실현"을 서술하는 것이지 계약 literal이 아님.

### 7. 문서 — CHANGELOG backfill 정확성

- backfill된 행: v1.6.51=`(b)`, v1.6.52=`(b-3)`. `docs/daily_logs/2026-07-08/work_log.md`에서 (b)=v1.6.51(line 86,90,93,114)·(b-3)=v1.6.52(line 124,151)로 사용됨을 확인 → backfill 식별자 사실 정합. ✓
- SoT v1.6.51/v1.6.52 행 자체는 (b)/(b-3) 식별자를 안 가짐 → CHANGELOG가 식별자를 보충(모순 아님).
- HANDOFF: 버전 v1.6.53, compose 런타임에 elasticsearch 추가, 테스트 수 654/45, Next Tasks (b-5)→(b-6) 재편, Project Structure에 `services/elasticsearch/Dockerfile` 추가. 정합.

## Issues / Risks

1. **(비차단, 사실 nuance) "cluster health green" 표현의 정밀도**: SoT/work_log/CHANGELOG이 "cluster health green"을 서술. 독립 재현 결과, 빈 클러스터(인덱스 0)에서는 green이 맞으나, 앱 부팅 시 실 `memory_lexical` 인덱스가 생성되면 single-node + 기본 replica 1로 인해 cluster는 **yellow**(`unassigned_shards:1`)로 전환됨(재현으로 확인: 생성 후 yellow, 삭제 후 green 복귀). compose healthcheck `curl -sf _cluster/health`는 200=green/yellow 모두 허용하므로 **기능적 결함 아님**. 단, 향후 readiness 게이트가 "green"에 keyed되면 steady-state에서 통과 불가. 문구 정정(None-blocking) 권장: "green" → "responsive(green/yellow)" 또는 healthcheck comment가 이미 yellow를 허용하므로 그대로 유지도 가능.
2. **(비차단, 문서 일관성) 브리프 G5 내부 불일치**: 논의 절(`:80`) "request_timeout(기본 30s, env override 가능)" vs 정본 오너 결정(`:11`) "request_timeout(기본 30) 추가"(env override 무언급). 구현은 정본(`:11`)을 따르고 §2를 이유로 env override 미구현. 정본이 canonical이므로 구현은 정합. 작업자 §1 노트 "브리프 추천값과 구현이 일치"는 논의 절 기준이면 부정확(정본 기준이면 정확). 브리프 논의 절의 "env override 가능"을 정본에 맞게 삭제하면 일관성 확보(1줄 정정).
3. **(비차단, 관찰) ES client 8.19.3 vs server 8.13.4**: 설치된 `elasticsearch` client=8.19.3, 서버=8.13.4. client가 server보다 최신. 8.x 내 backward compat로 `request_timeout` kwarg 지원엔 문제 없음(재현 통과). 본 slice가 client 버전을 바꾼 것은 아니므로 b-5 결함 아님(v1.6.52 이래 상태). requirements pin `elasticsearch>=8,<9` 준수.

## Verdict

**합격(PASS).**

이유:
- 경계 매트릭스 G0~G6=A의 모든 "should fire"/"should NOT fire" 셀이 코드·인프라·테스트로 추적됨(빈 셀 없음).
- 모든 literal이 verbatim 정합(Dockerfile, compose env, signature, nori 상수).
- 회귀 +3이 계약을 진정 pin하며, under-strict/over-strict 양방향 guard가 mutation 재실증으로 확인됨.
- 호출부 무변경 주장이 git diff + 소스 + 기존 worker 회귀 교차 pin으로 사실 확인.
- "계약 literal 변경 없음" 주장이 SoT diff로 지지됨(설명적 prose만 추가).
- 실 bring-up을 독립 재현해 nori 로드·앱 connect_ 실 인덱스 생성을 end-to-end로 확인(unit test fake 한계 보완).
- pytest 654 passed/45 skipped, `docker compose config` exit=0, `git diff --check` clean — 모두 재실행으로 확인.
- CHANGELOG backfill 식별자가 work_log와 정합.

Issues는 3건 모두 **비차단**(healthcheckyellow 허용·정본 canonical·client 버전 v1.6.52 이래). 계약 literal/public 표면을 변경하지 않은 배포 인프라 + 소폭 견고성 slice로서 계약을 충족.

## Outstanding items

- **미커밋 상태**: 검증 대상 work는 working tree에 uncommitted(6 modified + 3 untracked). 커밋 여부는 오너 결정 대기(작업자가 "커밋할까요?"로 질의 중).
- **오너 판단 2건(작업자가 이미 surface)**: (a) SoT v1.6.53 bump 적절성(검증자 소견: 적절 — 버전 로그를 slice 원장으로 운용하는 프로젝트 리듬 + connect_ 동작 미세 변경), (b) CHANGELOG v1.6.51/v1.6.52 backfill 유지 여부(검증자 소견: 유지 권장 — backfill이 사실 정합하고 원장 일관성 회복).
- **sandbox 밖 후속**: 전체 스택 `docker compose up` end-to-end(application hybrid retriever 부팅·서빙 + worker composite drain이 ES 인덱스 실제 적재)은 본 검증 범위 밖(본 검증은 ES 서비스 단독 bring-up + connect_ 경로만 관통).
- **비차단 권장(선택)**: (1) SoT/work_log "green" → "responsive(green/yellow)" 문구 정정, (2) 브리프 논의 절 `:80` "env override 가능" 삭제로 정본과 일치.

## Reproduction

```
cd /mnt/d/devel/에베베/ai_writte_system

# 정적/회귀
docker compose config --quiet                                          # exit 0
python3 -m pytest -q tests/test_context_search_memory_lexical_retrieval.py::ConnectElasticsearchTest  # 3 passed
python3 -m pytest -q --ignore=tests/test_memory_mongo.py                # 654 passed, 45 skipped
git diff --check                                                        # clean

# mutation 양방향(독립 재실증)
F=services/application/app/indexing/memory_lexical_index.py
cp "$F" /tmp/mli_backup.py
sed -i 's/client = Elasticsearch(url, request_timeout=request_timeout)/client = Elasticsearch(url, request_timeout=10)/' "$F"
python3 -m pytest -q tests/test_context_search_memory_lexical_retrieval.py::ConnectElasticsearchTest  # 2 failed, 1 passed
cp /tmp/mli_backup.py "$F" && rm /tmp/mli_backup.py                     # 복원

# 실 bring-up(독립 재현)
docker compose up -d elasticsearch
curl -sf http://localhost:9200/_cat/plugins                             # analysis-nori 8.13.4
curl -sf http://localhost:9200/_cluster/health                          # green(빈 클러스터)
PYTHONPATH=. python3 - <<'PY'
from services.application.app.indexing.memory_lexical_index import connect_elasticsearch_memory_index
import requests
url="http://localhost:9200"; IDX="ai_writte_verify_b5"
connect_elasticsearch_memory_index(url=url, index_name=IDX)
print(requests.get(f"{url}/{IDX}/_settings", timeout=10).json()[IDX]["settings"]["index"]["analysis"]["analyzer"])  # {'korean': {'type': 'nori'}}
print(requests.get(f"{url}/_cluster/health", timeout=10).json()["status"])  # yellow(인덱스 생성 후)
requests.delete(f"{url}/{IDX}", timeout=10)
PY
docker compose down && docker volume rm ai_writte_system_es_data        # 잔여 0
```
