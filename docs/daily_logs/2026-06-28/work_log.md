# Work Log — 2026-06-28

## Goals

- HANDOFF를 읽고 다음 작업(Next Task #1)을 진행한다.
- in-memory Core SOT service contract를 실제 MongoDB 저장소에 연결한다.
- 승인된 persistence/retention 계약(transaction 기본 + 제한적 non-transaction fallback, idempotency, isolation, archive 보존)을 코드와 회귀로 잠근다.

## Completed work

### Repository 인터페이스 추출 (service ↔ storage 분리)

- 변경 파일: `services/application/app/core_sot/repository.py`(신규), `services/application/app/core_sot/service.py`.
- 기존 `CoreSotService`가 repository 내부 dict(`.projects`, `.snapshots`, `.blocks_by_snapshot` 등)에 직접 접근하고 있어 저장소 교체가 불가능했다.
- 좁은 method 기반 `CoreSotRepository` Protocol을 정의했다(`get_/put_project`, `get_/put_draft`, `get_version/snapshot/blocks`, `version_count`, `find_save_request`, `record_save`, `next_*_id`).
- `InMemoryCoreSotRepository`에 동일 method를 추가하되 기존 public dict 속성은 보존해 기존 14개 테스트를 그대로 통과시켰다(surgical change).
- `CoreSotService`를 dict 직접접근 대신 Protocol method만 사용하도록 리팩터하고, 생성자 타입을 `CoreSotRepository`로 넓혔다.
- 효과: 동일 service 로직이 in-memory와 Mongo 양쪽 저장소에서 동작한다.

### MongoDB adapter + transaction-backed repository

- 변경 파일: `services/application/app/core_sot/mongo_repository.py`(신규), `services/application/requirements.txt`(pymongo 추가).
- pymongo(sync) 기반 `MongoCoreSotRepository`를 추가했다. 컬렉션: `projects`, `drafts`, `draft_versions`, `source_snapshots`, `source_blocks`.
- idempotency 경계를 `draft_versions`의 unique index `(project_id, draft_id, idempotency_key)`로 강제했다.
- **transaction 경로(기본, Docker/replica-set runtime)**: save write set(version → snapshot → blocks)을 한 transaction으로 commit한다. version을 먼저 insert해 중복 키가 transaction 전체를 즉시 abort하게 했고, `DuplicateKeyError`를 `DuplicateSaveRequest`로 번역한다.
- **non-transaction fallback(local/test 제한 경로)**: ① retry guard(commit된 version 존재 시 dependents를 건드리지 않고 replay 신호) → ② 직전 실패 시도의 orphan dependents 정리 → ③ immutable dependents 먼저, commit marker(version) 마지막의 ordered write. 동시성 race로 version insert가 중복되면 이 시도가 쓴 dependents만 정리하고 replay를 신호한다.
- 두 경로 모두 MongoDB write 완료 이후에만 성공을 반환한다(후속 분석 성공을 저장 성공보다 먼저 응답하지 않는다는 계약 준수).
- `DuplicateSaveRequest`는 `repository.py`에 정의했고, `CoreSotService.save_draft`가 이를 잡아 commit된 version을 재조회해 idempotent replay로 반환한다(service는 정상 흐름에서 `find_save_request`로 먼저 short-circuit, 이 경로는 race 안전망).
- id 생성은 `str(ObjectId())`로 했다(고유성만 요구, 포맷은 in-memory 골격용 sequence와 달라도 계약 무관).

### FastAPI app wiring

- 변경 파일: `services/application/app/main.py`.
- `CORE_SOT_MONGO_URI`가 설정되면 Mongo(기본 transaction)로, 아니면 기존 in-memory로 동작하는 `_default_service()`를 추가했다. `CORE_SOT_MONGO_DB`, `CORE_SOT_MONGO_TRANSACTIONS`로 db명/transaction 사용 여부를 조정한다.
- pymongo import는 lazy로 두어 in-memory 경로는 pymongo 설치 없이도 동작한다.

### 회귀 테스트

- 변경 파일: `tests/test_core_sot_mongo.py`(신규).
- live Mongo가 없으면 skip(fail 아님)하도록 `_probe_mongo()`로 가용성과 transaction 지원 여부를 탐지한다. URI는 `CORE_SOT_TEST_MONGO_URI`(기본 `mongodb://localhost:27017`).
- 공통 계약을 mixin으로 두고 fallback/transaction 두 경로에 동일 적용: save 후 snapshot/blocks/version 재구성, deterministic hash/blocks, idempotent replay(중복 없음), distinct key version 증가, unique index 중복 거절, project_id 격리, archive 보존, source_ref quote 재구성.
- fallback 전용: orphan cleanup(직전 실패 시도 dependents 제거), retry guard(commit된 dependents 미삭제).
- transaction 전용: 중복 키 abort 후 partial write 잔류 없음.

## Issues found

- 문제: Docker로 띄운 단일 노드 replica set은 rs config host가 컨테이너 내부 `localhost:27017`이라 host에서 replica set discovery가 primary를 못 찾는다.
- 원인: pymongo replica set 모드가 rs config의 hostname으로 topology를 구성.
- 해결: 검증 시 `?directConnection=true`로 연결해 discovery를 우회. transaction은 replica set primary 직결에서도 정상 동작.
- 결과: fallback/transaction 양 경로 통합 테스트가 동일 컨테이너에서 통과.

## Decisions

- 사용자 결정: Mongo adapter는 **real pymongo + live Mongo 통합 테스트(미가용 시 skip)** 방식, 드라이버는 **pymongo(sync)**. 이유: transaction을 실제로 검증해야 하고(mongomock은 transaction 미지원), 로컬 단일 사용자 MVP에는 sync가 단순하다. 트레이드오프로 기존 "전부 인프라 없는 단위 테스트" 컨벤션이 통합 테스트 층에서는 깨지지만, skip-aware로 두어 기본 단위 스위트는 인프라 없이 그대로 돌아간다.
- repository Protocol 추출은 surgical refactor 범위로 판단했다(저장소 교체를 위한 최소 선행조건이며 기존 테스트를 보존).

## Verification

- `python3 -m unittest discover -s tests`: 168개 중 17개 skip(Mongo 미지정), OK.
- `CORE_SOT_TEST_MONGO_URI=mongodb://localhost:27018/?directConnection=true python3 -m unittest discover -s tests`: 168개 전부 통과(신규 17개 fallback+transaction 포함).
- FastAPI app wiring smoke: `CORE_SOT_MONGO_URI` 설정 후 TestClient로 project→draft→save→replay 수행, replay가 같은 version 반환 확인.
- 검증용 Mongo는 `docker run -d --name coresot-mongo-test -p 27018:27017 mongo:7 --replSet rs0`로 띄운 단일 노드 replica set + `rs.initiate`.

## 검증 후 보강 (재검증 R1~R3 대응)

독립 재검증(`docs/verifications/2026-06-28/mongo_adapter_recheck.md`, 조건부 합격)이 발견한 3건에 대응했다.

### R1 (load-bearing 조건) — 해결

- 변경 파일: `tests/test_core_sot_mongo.py`.
- 증상: module-level `from pymongo import ...` / `from ... mongo_repository import ...`가 pymongo 패키지 부재 시 전체 `unittest discover`를 ImportError로 깨뜨렸다(파일 docstring의 "infrastructure-free unit suite stays runnable everywhere" 약속 위반).
- 수정: pymongo와 Mongo adapter import를 `try/except ImportError`로 감싸 `_PYMONGO_AVAILABLE` 플래그로 두고, `_probe_mongo()`가 플래그 False면 즉시 `(False, False)` 반환해 skip 처리하도록 했다. service/adapter 코드는 무관.
- 검증: pymongo 차단 후 discovery가 `errors=1`→`errors=0, skipped=17`로 복원. Mongo 연결 시 통합 17개 여전히 통과.

### R2 (방향 결정) — 사용자 결정 option (b): fallback single-writer 제약 명시

- 사용자 결정: fallback의 동시성 correctness bug(동시 같은 key save 시 orphan cleanup이 다른 writer의 committed dependents를 삭제 → orphaned version)에 대해, 구현을 그대로 두고 계약을 명확화하는 (b)를 선택했다. 근거: fallback은 spec상 "local/test 제한 경로"이고 production은 transaction path(동시성 안전)를 쓰며, 단일 사용자 로컬 MVP에 동시성 방어 복잡도를 더하는 것은 과하다. sequential retry는 현재 구현이 정확하다.
- 변경 파일: `docs/system-contract-sot.md`(§112에 single-writer 제약 추가, v1.3→v1.4, 계약 변경 이력 추가), `docs/plans/01-core-sot.md`(fallback 섹션 동일 제약), `services/application/app/core_sot/mongo_repository.py`(fallback docstring + `_record_save_fallback` 주석에 single-writer 근거 명시).
- 트레이드오프: 동시 fallback writer는 계약상 미보장으로 남는다. 동시성이 필요해지면 transaction 기본 경로 사용 또는 후속 결정으로 (a) 보강.

### R3 (추적 포인트) — source_refs 보존

- sot §113의 `source_refs` 보존 literal은 존재하나 `source_refs` collection은 아직 미구현이다(`create_source_ref`는 `SourceRef`를 반환만 하고 persist하지 않음 — minimal skeleton 시점과 동일). 본 slice(draft save write set + idempotency + transaction/fallback) scope 밖이며, 별도 SourceRef persistence slice에서 보존 정책을 적용한다. HANDOFF Next Tasks에 추적으로 남긴다.

## Dockerfile / Compose 추가 (Next Task #1)

- 변경 파일: `services/application/Dockerfile`(신규), `docker-compose.yml`(신규), `.dockerignore`(신규), `services/application/requirements.txt`(uvicorn 추가).
- Dockerfile은 Active Decision(빌드 캐시 보존)을 따른다: `requirements.txt`를 먼저 복사·설치하고 소스(`services/`)는 그 뒤에 복사해, 소스 변경이 의존성 install 레이어를 무효화하지 않게 했다. base는 `python:3.12-slim`(StrEnum 등 3.11+ 문법 사용). entrypoint는 `uvicorn services.application.app.main:app`.
- `.dockerignore`로 `__pycache__`/`.git`/`docs`/`tests` 등을 build context에서 제외해 컨텍스트 크기와 캐시 안정성을 확보했다.
- `docker-compose.yml`은 Slice 1 runtime을 정의한다: MongoDB 단일 노드 replica set(`--replSet rs0`) + application. 승인된 persistence 계약이 transaction 기본이므로 replica set이 필수다. mongo healthcheck가 `rs.initiate`를 idempotent하게 수행하고, member host를 `mongo:27017`로 두어 application이 compose 네트워크 내 hostname으로 replica set discovery를 성공한다(host 직결의 directConnection 우회가 불필요).
- application은 `CORE_SOT_MONGO_URI=mongodb://mongo:27017/?replicaSet=rs0`, `CORE_SOT_MONGO_TRANSACTIONS=true`로 transaction 경로를 쓰며 `depends_on: mongo healthy`로 기동 순서를 보장한다.

### 검증

- `docker compose config` OK, `docker compose build application` 성공(레이어 캐시 순서 확인: requirements → install → source).
- `docker compose up -d` 후 mongo healthy, app `/health` → `{"status":"ok"}`.
- API end-to-end(transaction 경로): project→draft→save(version 1, 4 blocks)→같은 key replay가 `idempotent_replay=true, version_number=1`, `draft_versions` count=1(중복 없음). transaction이 실제 사용됨을 확인.
- `docker compose down -v`로 정리, 단위 스위트 재확인 OK(skipped=17).

### Docker 검증 후 보강 (비차단 observation 대응)

- 독립 검증(`docs/verifications/2026-06-28/slice1_docker_and_recheck_closure.md`, 합격)의 비차단 observation 3건 중 #1만 보강했다.
- #1(적용): `docker-compose.yml`의 application 서비스에 healthcheck를 추가했다. slim 이미지에 curl이 없어 stdlib `urllib`로 `/health`를 probe한다. 검증: `docker compose up` 후 application 컨테이너가 ~3s 내 `healthy` 도달 확인, `down -v` 정리.
- #2(유지): mongo `--bind_ip_all`은 compose 네트워크에서 application 컨테이너가 mongo에 도달하기 위해 필요한 설정이라 현행 유지(localhost-only 바인딩이면 cross-container 접속 불가). 검증자도 로컬 MVP에서는 OK로 명시. 공유/운영 환경 진입 시 bind 제한은 그때 별도 적용.
- #3(유지): uvicorn 단일 worker는 단일 사용자 로컬에 적합(검증자 확인). 변경은 speculative라 미적용.

## Next steps

- gateway 서비스 Dockerfile/compose 편입(현재는 application+Mongo만; gateway는 외부 llama.cpp endpoint 의존, Slice 1 범위 밖).
- SourceRef persistence slice에서 `source_refs` collection과 §113 보존 계약 적용(R3).
- 동시성이 필요해지면 fallback (a) 보강 재검토(현재는 single-writer 계약으로 닫힘, R2).
