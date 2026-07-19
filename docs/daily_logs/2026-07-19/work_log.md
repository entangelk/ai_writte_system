# Work Log — 2026-07-19

## Task — Writing Workspace V2 W2 ProjectBrief onboarding + canonical overview

### Goals

- W0의 exact ProjectBrief append-only version/API/clear 계약을 Core SOT, Mongo, HTTP, OpenAPI에 구현한다.
- 작품 정보를 Writing ContextPackage의 별도 authoritative item으로 공급한다.
- optional progressive onboarding과 canonical-only overview를 제공하고 pending을 정본과 분리한다.
- 서브 머신에서 의존성과 빌드를 다시 준비하되 LLM은 사용하지 않는다.

### User Decisions and Rationale

- 사용자는 `HANDOFF.md`와 2026-07-18 로그의 다음 작업을 이어서 진행하도록 요청했다. 현재 머신은 서브 머신이라 빌드 재수행이 필요하고 LLM은 사용할 수 없다는 실행 제약을 명시했다.
- W2 방향은 기존 오너 결정 D1=A(ProjectBrief), D5=A(canonical-only overview), 전체 C(세로 슬라이스)와 W0 exact contract에 이미 확정되어 있어 새 owner fork 없이 구현했다. W3 ordered unit/intent와 W4 export는 범위 밖으로 유지했다.

### Completed work

- **Core SOT / Mongo**: `ProjectBriefVersion`과 put result를 추가하고 in-memory/Mongo repository에 current/version/history/idempotency surface를 구현했다. Mongo는 `(project_id,version_number)`와 `(project_id,idempotency_key)` unique index를 사용한다.
- **서비스 계약**: first null-base version 1, current-base next version, stale/null 409, same-key replay 선행, different-key distinct version, project isolation, archived read/write 경계, all-null/empty clear의 history 보존을 구현했다.
- **HTTP/OpenAPI**: current GET, PUT, history GET, version GET 4개 endpoint와 exact request/response Pydantic model을 추가했다. unknown/missing key, blank scalar/constraint, trim 후 duplicate constraint는 422이며 response에 내부 idempotency key를 노출하지 않는다.
- **Writing context**: `ContextPackage.project_brief`에 current version을 별도 authoritative item으로 싣고 `<project_brief authority="canonical" version="N">`으로 직렬화했다. candidate/memory item 또는 원고 본문에 병합하지 않았다.
- **프론트**: `/projects/:projectId/overview`를 추가했다. ProjectBrief가 없으면 optional onboarding 폼과 “지금은 건너뛰기”, 있으면 version 표시·수정·“작품 정보 지우기(이력 보존)”를 제공한다. canonical memory만 인물/사건/떡밥·미해결 질문 카드로 표시하고 review candidate/gate finding은 별도 pending count/link로만 표시한다. archived project는 read-only다.
- **생성 타입/빌드 준비**: 서브 머신에 없던 npm 의존성을 `npm ci`로 재설치하고 OpenAPI 타입을 재생성했다. 현재 Python/FastAPI가 input/output schema를 분리해 생성하므로 Writing 소비 타입을 명시적 `-Output` component로 정렬했다.
- **문서**: SoT v1.7.13, Product Shell, readiness backlog, CHANGELOG, HANDOFF를 W2 완료/W3 READY로 갱신했다.

### Issues found

- **npm 의존성 부재**: 최초 `gen:api`가 `openapi-typescript: not found`로 실패했다. sandbox DNS에서 `npm ci`가 `EAI_AGAIN`이었고 승인된 네트워크 실행으로 195 packages를 설치했다. audit 취약점은 0건이다.
- **저수준 context fake 호환**: 전체 백엔드 첫 실행에서 project를 의도적으로 seed하지 않는 canonical/candidate retrieval seam 15개가 새 brief 조회로 실패했다. HTTP는 기존 project 404 authority를 유지하고, 저수준 `ContextSearchService`의 project-less fake에서는 brief 없음으로 처리해 기존 seam을 보존했다. 관련 집중 회귀 60개를 통과했다.
- **Docker CLI 부재**: `docker compose build application frontend`는 이 WSL distro에 `docker` 명령이 없어 실행할 수 없었다. npm production build는 완료했지만 compose image/live 재배포는 Docker가 있는 머신에서 다시 해야 한다.
- **Node engine 경고**: 설치된 Node v22.17.1은 `react-router@8.2.0`이 요구하는 `>=22.22.0`보다 낮아 `EBADENGINE` 경고가 있었다. 테스트/build는 통과했으나 서브 머신 runtime을 지원 범위에 맞추려면 Node를 올리는 것이 안전하다.

### Decisions

- ProjectBrief는 retrieval token budget의 후보 item으로 취급하지 않고 ContextPackage의 별도 정본 필드로 유지했다. 이로써 candidate/canonical memory status와 혼동하지 않으며 W0의 project 1:1 current authority를 그대로 보존한다.
- overview는 새 backend aggregate를 만들지 않고 기존 canonical memory와 review inbox를 독립 조회한다. canonical 목록은 `status=canonical`을 한 번 더 필터하고 pending 본문은 렌더하지 않아 권위 혼합을 방지한다.
- clear/skip 모두 hard delete가 아니라 all-null/empty 새 version PUT으로 구현했다. UI 문구에 이력 보존을 명시했다.

### Verification

- `python3 -m pytest tests/test_project_brief.py tests/test_core_sot_mongo_indexes.py -q -p no:cacheprovider` → **18 passed**.
- ProjectBrief context 및 인접 retrieval root-pattern 집중 실행 → **60 passed**.
- `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **1142 passed, 50 skipped**.
- `npm test -- --run` → **143 passed / 10 files**.
- `npm run gen:api` → PASS.
- `npm run build` → PASS, **96 modules**; CSS 17.54 kB(gzip 3.94), JS 284.19 kB(gzip 87.85).
- `git diff --check` → PASS.
- `docker compose build application frontend` → **미실행/환경 차단**: Docker CLI 없음.
- LLM 호출/실모델 검증 → 사용자 제약에 따라 수행하지 않음; W2의 deterministic 계약에는 필요하지 않음.

### Next steps

- 추가 승인 없이 W3를 착수한다: W0 §2~4의 ordered unit migration/reorder/previous-next, legacy `other` 재분류 안내, `append_current|start_next_unit` binding과 next-unit accept 원자 저장, OU/WI/SC named matrix를 구현한다.
- Docker 사용 가능한 머신에서 `docker compose build application frontend` 후 W2 API/overview smoke를 수행한다.
- 서브 머신 Node를 `>=22.22.0`으로 올려 react-router engine 경고를 제거한다.

---

## Task — W2 독립 검증 PASS 후 hardening·커밋 준비

### Goals

- 독립 검증 `docs/verifications/2026-07-19/w2_project_brief_overview.md`의 PASS 근거와 hardening H1~H5를 직접 확인한다.
- 현재 머신에서 유효한 보강을 반영하고, 실제 Docker/Mongo/Node 테스트 머신에서 재실행할 항목을 HANDOFF에 남긴다.
- 전체 회귀와 생성 타입/build를 다시 통과시킨 뒤 W2 작업을 한 커밋으로 묶는다.

### User Decisions and Rationale

- 오너는 독립 검증 기록을 근거로 보강 가능한 부분을 반영하고, 테스트 머신 재실행 항목을 핸드오프에 기록한 뒤 커밋하도록 승인했다. 외부 publish/push는 요청 범위가 아니므로 수행하지 않는다.

### Completed work

- **검증 기록 확인**: W2 소유 matrix PB-01~12·SC-01/02의 empty cell 없음과 PASS(조건 없음), 재현 수치, outstanding을 전문 확인했다. 독립 기록 자체는 역사적 감사 artifact이므로 수정하지 않았다.
- **H1 OpenAPI 정밀도**: `NonBlankBriefString`에 `pattern=r"\S"`를 명시했다. runtime trim/min-length 동작을 바꾸지 않으면서 generated OpenAPI가 W0 catalog의 nonblank pattern을 노출하고, SC-01이 payload id와 PUT idempotency key의 pattern을 exact 단정한다.
- **H2 no-brief service 경로**: 실제 existing project를 만들고 brief version 없이 `ContextSearchService.build_context_package()`를 실행해 `project_brief is None`과 prompt section 미발명을 named 회귀로 잠갔다.
- **H3 collision 경계**: deterministic repository collision이 different-key replay로 오인되지 않고 `StaleProjectBriefBase`가 되는 회귀를 추가했다. 실제 Mongo에서는 두 writer가 같은 empty base를 읽도록 barrier를 건 병렬 integration test를 추가했다. 현 머신 Mongo 부재로 skip되며 테스트 머신 실행 항목으로 인계했다.
- **H4/H5 판단**: cleared brief의 `(empty)` prompt 표현은 W0에 없는 owner 의미 결정이므로 변경하지 않았다. history client binding은 이미 확정·구현된 4개 ProjectBrief API의 대칭 read surface라 유지했다.
- **HANDOFF**: 독립 PASS/hardening closure, 최신 수치, Node `>=22.22.0`·Docker image build·Mongo 병렬 회귀·nginx/API/overview smoke 명령과 LLM 불필요 경계를 기록했다.

### Issues found

- 현재 머신에는 Docker CLI와 live Mongo가 없어 신규 병렬 integration test 2개(transaction/fallback)가 skip된다. 이 상태를 green bar에 숨기지 않고 backend skipped 수치와 HANDOFF 테스트 머신 항목에 명시했다.

### Decisions

- 검증 H1·H2는 public schema/실 service 경로를 더 정확히 잠그면서 동작 의미를 바꾸지 않아 즉시 반영했다.
- H3는 deterministic mapping과 실제 Mongo test node를 모두 코드에 두되, 실제 실행 완료 주장은 하지 않는다.
- H4는 owner fork를 만들 수 있어 조용히 선택하지 않았고, H5는 speculative 새 기능이 아니라 현 API의 얇은 client 대칭이므로 유지했다.

### Verification

- focused PB/SC+Mongo index: **20 passed**.
- backend full: **1144 passed / 52 skipped**(live Mongo 신규 2개 포함 infrastructure skips).
- frontend full: **143 passed / 10 files**.
- `npm run gen:api`: PASS.
- `npm run build`: PASS, **96 modules**.
- `git diff --check`: PASS.

### Next steps

- Docker/Node/Mongo 테스트 머신에서 HANDOFF의 W2 운영 closure를 먼저 수행한다. 특히 신규 `test_concurrent_project_brief_version_collision_has_one_success_one_stale`가 transaction/fallback 양쪽에서 실제 통과해야 H3 live 축이 닫힌다.
- 그 뒤 W3 ordered unit/explicit intent를 착수한다.

---

## Task — W2 테스트 머신 운영 closure 독립 검증

### Goals

- 서브 머신에서 미실행이던 지원 Node, Docker image, 실제 Mongo 동시성, nginx/API/browser 축을 독립 검증한다.
- W2의 LLM 비의존 경계를 유지하면서 canonical-only/pending 분리를 실제 배포 이미지에서 확인한다.
- 재현 가능한 독립 검증 기록을 남기고 HANDOFF의 완료/다음 작업 상태를 현재 사실로 갱신한다.

### User Decisions and Rationale

- 사용자는 `HANDOFF.md`와 오늘 로그를 기준으로 서브 머신에서 못 했던 검증부터 진행하도록 지시했다. 따라서 W3 구현보다 W2 운영 closure를 우선했고, 검증 중 발견한 결함은 임의 수정하지 않는 독립 감사 범위를 유지했다.

### Completed work

- **지원 Node 프론트 재현**: `node:22-slim` v22.23.1/npm 10.9.8에서 fresh `npm ci`(195 packages, 취약점 0), Vitest 143/10, production build 96 modules를 통과했다.
- **OpenAPI 생성 타입(후속 정정)**: 당시 현재 Python app에서 git-ignored `openapi.json`을 다시 만들고 byte-identical이라고 기록했으나 독립 재감사가 이를 반박했다. 실제로는 ProjectBrief 영역만 일치하고 전체 schema는 stale Writing `-Input/-Output` component 때문에 달랐다. 아래 후속 task에서 기록과 코드를 정렬했다.
- **이미지**: 최신 source로 application/frontend image를 빌드했다. frontend image의 지원 Node stage에서 `npm ci`와 build가 실제 실행됐다.
- **실 Mongo**: replica-set Mongo에서 `tests/test_core_sot_mongo.py` 33개를 skip 없이 통과했다. 신규 ProjectBrief 동시 충돌 회귀가 fallback/transaction 양쪽에서 success 1/stale 1, replay false, version 1개를 유지해 H3 live 축을 닫았다.
- **nginx/API/UI**: 격리 DB와 최신 image의 일회성 application/frontend를 사용해 nginx `/api` PUT/current/history/version/same-key replay를 확인했다. 실제 Chrome DOM에서 ProjectBrief version 1, canonical memory 1건, pending count 1을 확인하고 pending 이름/본문이 canonical grid에 노출되지 않음을 기계 단정했다.
- **정리/문서**: 격리 DB를 drop하고 일회성 컨테이너와 검증용 Mongo를 정지했다. `docs/verifications/2026-07-19/w2_operational_closure.md`를 신설하고 HANDOFF에서 W2 운영 closure를 완료 처리했다.

### Issues found

- **Compose Bake panic**: Compose v2.40.2 기본 Bake 경로가 내부 slice-bounds panic을 냈다. source 결함이 아니며 기존 전례와 같은 `COMPOSE_BAKE=false`로 동일 image build가 성공했다.
- **경량 compose smoke 지시 정밀도**: base compose application은 Chroma/embedding/ES 주소를 주입하므로 `--no-deps`로 Mongo/application/frontend만 띄우면 app import 시 Chroma 연결 실패가 난다. W2가 LLM 비의존이라는 계약은 유지되지만, 경량 smoke는 optional backend env를 제외한 일회성 app 또는 full non-LLM dependency stack이 필요하다.
- **호스트 Node 미달**: 호스트 v22.17.0은 여전히 `react-router@8.2.0`의 `>=22.22.0`보다 낮다. 이번 deployment/test 근거는 지원 범위인 container v22.23.1에서 확보했다.
- **샌드박스 false skip**: 호스트 Docker 포트가 샌드박스에서 차단되어 Mongo 첫 실행이 33 skipped였다. 권한 있는 동일 명령으로 33 passed/0 skipped를 재도출했고 첫 결과는 판정에서 제외했다.

### Decisions

- 검증 전용 DB와 일회성 컨테이너를 사용해 기존 사용자 데이터/볼륨을 변경하지 않았다.
- application의 optional backend 환경을 빼는 일회성 runtime을 사용해 W2 image/nginx/API를 검증하되 LLM·embedding·Chroma·ES는 기동하지 않았다.
- Compose/buildx 및 호스트 Node 정비는 W2 계약 결함이 아닌 운영 hardening으로 분리해 W3 진입을 차단하지 않는다.

### Verification

- 지원 Node: **v22.23.1**, npm **10.9.8**.
- fresh install: **195 packages**, audit vulnerability **0**.
- frontend: **143 passed / 10 files**.
- OpenAPI→TypeScript: 최초 **byte-identical 주장은 재감사에서 반박됨**(fresh 106805 vs committed 106941 bytes). 아래 후속 closure 전까지 conditional이었다.
- production build: **96 modules**, CSS 17.54 kB(gzip 3.94), JS 284.19 kB(gzip 87.85).
- Docker image: application/frontend **PASS**(`COMPOSE_BAKE=false` 우회).
- live Mongo: **33 passed / 0 skipped**(fallback+transaction).
- Chrome overview DOM: `required_missing=[]`, `pending_body_leaked=[]`, `deep_link_rendered=True`.
- 상세 명령·근거·판정: `docs/verifications/2026-07-19/w2_operational_closure.md` — 최초 PASS 주장은 정정, 독립 재감사 conditional 뒤 아래 B1/B2 closure로 최종 PASS.

### Next steps

- W2 운영 closure가 끝났으므로 W3 ordered unit/explicit Writing intent를 착수한다.
- 호스트 Node upgrade와 Compose/buildx 정비는 별도 운영 hardening으로 처리한다.

---

## Task — W2 운영 closure 독립 재감사 B1/B2 보강

### Goals

- `w2_operational_closure_audit.md`의 전체 schema 재현 불가와 fresh gen→build break를 직접 재현한다.
- 승인된 Writing C0 계약과 git precedent에서 정렬 방향을 재도출하고 최소 변경으로 gen:api 재현성을 복구한다.
- 잘못된 최초 검증 주장과 현재 상태 문서를 투명하게 정정한다.

### User Decisions and Rationale

- 사용자는 독립 재감사 기록을 제시하고 보강 가능한 부분을 보강하도록 요청했다. 재감사가 제시한 두 옵션 중 방향을 임의 선택하지 않고 먼저 정본과 이력을 확인했다.
- 확인 결과 `-Input/-Output`은 승인된 공개 literal이 아니라 W2 커밋에서만 생긴 generator artifact였다. C0의 승인 계약은 성공/partial envelope를 OpenAPI 생성 타입으로 소비하는 것이고, W2 직전과 현재 app 모두 단일 `WritingCandidatePayload`/`WritingGatePayload`를 낸다. 따라서 owner-level fork가 아니라 정본/precedent로 답할 수 있는 drift로 판정해 옵션 (b)(현재 app에 schema/client 정렬)를 적용했다.

### Completed work

- **red 재현**: fresh `openapi.json`에서 tracked `schema.d.ts`를 재생성하자 `client.ts`의 `WritingCandidatePayload-Output`/`WritingGatePayload-Output` 두 참조가 TS2339로 실패했고, 그 결과 WritingPanel의 finding callback 네 곳이 implicit-any로 연쇄 실패했다.
- **최소 정렬**: generated `schema.d.ts`를 현재 app의 단일 component 출력으로 갱신하고, client alias 두 곳을 `WritingCandidatePayload`/`WritingGatePayload`로 복원했다. backend/public payload/runtime 동작은 변경하지 않았다.
- **재현성 확인**: 같은 fresh `openapi.json`을 지원 Node/openapi-typescript 7.13.0으로 두 번째 생성해 tracked schema와 byte-identical임을 확인했다.
- **기록 정정**: `w2_operational_closure.md`에 최초 PASS→재감사 conditional→B1/B2 closure→최종 PASS의 시간 순서를 명시했다. 독립 재감사 기록은 감사 artifact라 수정하지 않았다. HANDOFF도 conditional과 closure를 함께 반영했다.
- **재감사 H1 정리**: 검증 전용 `ai_writte_system-frontend-w2-verify` image(377MB)를 최종 지원 Node 검증 후 삭제했다. application/frontend 제품 image는 유지했다.

### Issues found

- **B1 확인**: 최초 운영 기록의 전체 `schema.d.ts` byte-identical 주장은 사실이 아니었다. 재감사의 106805/106941 bytes 차이와 Writing component drift를 직접 확인했다.
- **B2 확인**: stale generated file을 현재 app에 맞춰 갱신하면 기존 client가 실제로 build를 깨뜨렸다. green bar는 stale schema를 사용한 결과였고 gen:api 재현성을 증명하지 못했다.
- **환경성 테스트 강제 종료**: Windows bind mount 위의 Node 컨테이너 테스트가 로그 없이 종료됐다. 현재 source를 build-stage image 내부 `/app`에 복사한 뒤 같은 지원 Node에서 재실행해 143/143을 확보했다. 코드 실패 근거로 사용하지 않았다.
- **비차단 생성환경 차이**: FastAPI 허용 범위가 넓어 host/application image가 일부 OpenAPI 표현을 다르게 낸다. 이번 blocker의 `-Input/-Output` 부재는 두 환경에서 동일하지만, 장기 재현성은 생성환경 고정 후보로 남는다.

### Decisions

- `-Input/-Output` generator 이름을 새 public contract로 승격시키지 않았다. 의미적으로 같은 단일 Pydantic model을 app authority로 유지하고 frontend generated artifact/alias만 정렬했다.
- 새 CI/생성 컨테이너 도입이나 FastAPI pin은 이번 blocking closure보다 범위가 크므로 비차단 hardening으로 남겼다.
- 독립 재감사 기록은 수정하지 않고, 잘못된 피감사 기록과 HANDOFF만 정정했다.

### Verification

- red: fresh gen 후 `client.ts:67,69` **TS2339 2건** + 파생 TS7006 4건.
- schema determinism: 같은 fresh input의 두 번째 openapi-typescript 생성물과 tracked `schema.d.ts` **byte-identical**.
- focused backend PB/SC + Writing envelope: **27 passed / 5 subtests**.
- 지원 Node v22.23.1 frontend: **143 passed / 10 files**.
- production build: **96 modules**, CSS 17.54 kB(gzip 3.94), JS 284.19 kB(gzip 87.85).
- 프로젝트 exact pipeline `npm run gen:api && npm run build`: PASS.
- 검증 전용 image: 삭제 완료.

### Next steps

- 재감사 합격 조건 B1/B2가 모두 닫혔으므로 W3를 착수할 수 있다.
- OpenAPI 생성환경 pin/CI check는 실제 CI 또는 dependency 재현성 정비 trigger에서 별도 처리한다.

---

## Task — Writing Workspace V2 W3 증분 1: ordered unit

### Goals

- W0 §2의 Draft `unit_kind/position`, archived-inclusive total order와 full-permutation reorder를 구현한다.
- legacy Draft를 명시 one-shot으로 이관하고 transaction/fallback 원자 경계를 실제 Mongo까지 검증한다.
- 프론트가 생성 단위와 서버 소유 순서를 소비하게 하고 OpenAPI 생성→build 회귀를 유지한다.

### User Decisions and Rationale

- 사용자는 W2 closure 커밋 뒤 다음 작업 진행을 승인했다. W3의 ordered unit과 Writing Intent는 W0 v1.7.10에 이미 exact 계약과 named matrix가 확정돼 있어 새 owner fork 없이 §2부터 독립 증분으로 진행했다.
- W3 전체 완료로 과장하지 않고 OU-01~14만 이번 증분에서 닫고, 원자 accept receipt가 필요한 Writing Intent WI-01~22는 다음 증분으로 분리했다.

### Completed work

- **Core SOT/API**: Draft에 `unit_kind`와 `position`을 추가하고 create default `other`/N+1, position-order list, archive slot 보존을 구현했다. `PUT /projects/{project_id}/draft-order`는 archived 포함 전체 draft ID의 정확한 완전순열만 받고 exact 1..N을 반환한다.
- **Mongo/migration**: repository metadata replace와 `(project_id,position)` unique-index 설치 경계를 추가했다. 명시 `scripts/migrate_ordered_units.py`가 legacy repository order를 `other/1..N`으로 이관하고 mixed/unknown/duplicate/gapped 상태는 project 단위 fail-closed하며 전체 성공 뒤에만 index를 설치한다. non-transaction local/test 경로는 project raw before-image를 복구한다.
- **프론트/OpenAPI**: generated Draft/CreateDraft/reorder 타입을 반영하고 생성 폼 단위 선택, 목록 position/kind 표시, 전체순열 위/아래 reorder를 연결했다.
- **회귀**: canonical 이름 그대로 OU-01~14를 추가했다. 실제 replica-set에는 ordered field/reorder 공통 회귀와 fallback 중간 실패 raw before-image 복구·정상 commit/index 설치를 추가했다.

### Issues found

- fresh OpenAPI 생성 직후 `CreateDraftRequest.unit_kind`를 기존 프론트 호출이 보내지 않아 TypeScript build가 실패했다. 서버의 호환 기본값은 유지하면서 새 UI가 명시 단위를 보내도록 정렬했다.
- 첫 live Mongo 실행은 샌드박스의 localhost socket 차단으로 37개가 skip됐다. 권한 있는 동일 명령으로 다시 실행해 37 passed/0 skipped를 확보했으며 skip 결과는 판정에 사용하지 않았다.

### Decisions

- position은 client create 입력으로 받지 않고 서버만 N+1을 부여한다. reorder만 full ID permutation으로 순서를 바꿔 fractional/partial move를 열지 않았다.
- migration은 read-time default를 두지 않고 배포 전 maintenance-window 명시 runner로 유지했다. 한 project 실패 시 index를 설치하지 않지만 이미 성공한 project는 재실행에서 valid no-op으로 재사용한다.
- Writing Intent는 ordered-unit 기반 위의 별도 원자 write/receipt 경계이므로 이번 커밋에 반쪽 구현하지 않았다.

### Verification

- OU named + Core/API focused: **111 passed / 27 subtests**.
- backend full: **1159 passed / 60 skipped / 293 subtests**.
- live replica-set Mongo: **37 passed / 0 skipped**.
- frontend full: **144 passed / 10 files**.
- `npm run gen:api && npm run build`: PASS, **96 modules**; CSS 17.81 kB(gzip 4.00), JS 285.37 kB(gzip 88.19).
- `git diff --check`: PASS.

### Next steps

- W0 §3의 `append_current|start_next_unit` discriminator, candidate binding, start-next six-surface Core SOT transaction, accept receipt/replay와 Analysis partial convergence를 WI-01~22로 구현한다.
- WI 완료 뒤 W0 schema fragment와 실제 OpenAPI를 SC-01/02로 다시 대조하고 W3 전체 closure를 수행한다.

---

## Task — W3 ordered-unit 독립 검증 B1 closure

### Goals

- 독립 검증의 조건부 합격 사유인 duplicate reorder 422↔§2.2 exact 409 불일치를 재현하고 닫는다.
- OU-08이 모든 invalid full-permutation branch의 status와 write 0을 직접 잠그게 한다.
- 비차단 hardening 중 현재 증분에 안전하게 포함 가능한 ID 보존·프론트 계약 fixture/표시를 보강한다.

### User Decisions and Rationale

- 사용자는 독립 검증 기록을 확인해 보강한 뒤 커밋하도록 지시했다. W0 §2.2는 누락·중복·foreign/unknown·평가 중 set-change를 모두 409로 명시하므로 status authority는 option (a)로 정본에서 도출했다.
- schema `uniqueItems:true`는 유효 요청의 구조를 설명하지만 HTTP 오류 코드를 정하지 않는다. 따라서 schema를 바꾸지 않고 runtime 중복 판정 위치만 Core SOT service로 내리는 것이 최소 변경이며 §2.2와 schema를 동시에 보존한다.

### Completed work

- `DraftOrderPutRequest`의 duplicate field validator를 제거했다. OpenAPI `uniqueItems:true`는 유지하고 service의 기존 complete-set/duplicate 검사가 `InvalidDraftOrder`를 내어 409로 매핑한다.
- OU-08의 `(409,422)` 허용을 제거하고 missing/duplicate/foreign/unknown 전부 exact 409와 repository state/write count 불변을 단정했다.
- OU-04에 migration 전후 Draft ID 보존을 직접 단정했다.
- DraftList fixture를 required `unit_kind/position` shape로 정렬하고 canonical position 표기를 “정본 순서”로 명확히 해 visible ordinal과 혼동하지 않게 했다.
- 독립 검증 record는 피감사 시점의 conditional verdict를 보존하고 수정하지 않았다.

### Issues found

- 강화된 OU-08은 수정 전 duplicate subtest에서 `422 != 409`로 정확히 실패해 감사 B1을 재현했다. validator 제거 후 같은 test가 14 passed/12 subtests로 green이 됐다.
- H1(SC-01/02 OU fragment 자동 대조)은 SoT v1.7.14가 WI 완료 후 W3 전체 closure로 명시한 필수 후속이므로 이번 보강에서 앞당기지 않았다.

### Decisions

- Pydantic 구조 검증 실패 422와 domain full-permutation conflict 409를 구분했다. duplicate ID는 JSON 구조 오류가 아니라 현재 project Draft set과의 의미적 충돌이므로 service 409가 authority다.
- 독립 검증의 H2는 현재 UI가 archived Draft도 숨기지 않아 canonical/visible order가 우연히 같지만, 향후 active-only UI에서도 오해하지 않도록 canonical position label을 명시했다.

### Verification

- red: `OrderedUnitApiTest::test_invalid_permutation_rejected_without_write` duplicate case → **422 != 409**.
- green: `tests/test_ordered_units.py` → **14 passed / 12 subtests**.
- backend full → **1159 passed / 60 skipped / 293 subtests**.
- live replica-set Mongo → **37 passed / 0 skipped**; 검증용 컨테이너 종료·자동 삭제 완료.
- DraftList focused → **10 passed**.
- frontend full → **144 passed / 10 files**.
- `npm run gen:api && npm run build` → PASS, **96 modules**; CSS 17.81 kB(gzip 4.00), JS 285.39 kB(gzip 88.20).

### Next steps

- W3 Writing Intent WI-01~22를 구현한다.
- WI 완료 뒤 SC-01/02의 ProjectBrief+OU+Writing Intent fragment 전체를 자동 대조해 W3를 최종 closure한다.

---

## Task — Writing Workspace V2 W3 증분 2: explicit Writing intent + W3 전체 closure

### Goals

- W0 §3의 `append_current|start_next_unit` discriminator, candidate binding, start-next six-surface Core SOT transaction, accept receipt/replay와 Analysis partial 수렴을 WI-01~22로 구현한다.
- WI 완료 뒤 SC-01/02로 ProjectBrief + OU + Writing intent fragment 전체를 W0 schema catalog와 자동 대조해 W3를 최종 closure한다.
- LLM 없이 결정적 계약만 구현·검증한다.

### User Decisions and Rationale

- 사용자는 HANDOFF와 오늘 로그의 다음 작업(WI-01~22 → SC-01/02)을 이어서 진행하도록 지시했다. W0 v1.7.10에 exact 계약과 named matrix가 이미 확정돼 있어 새 owner fork 없이 §3부터 독립 증분으로 구현했다.
- `nextUnitSpec`의 `goal`은 W0 prose가 "optional"이라 표현하지만 정본 schema catalog `$defs`는 `goal`을 `required`(nullable)로 명시한다. 구조 계약(schema catalog)이 wire shape의 정본이므로 `goal`을 required-nullable 키로 맞추고 "optional"은 "값이 null 가능"으로 해석했다. 프론트는 항상 `goal`(값 또는 null)을 보낸다.

### Completed work

- **모델/계약**: `writing/models.py`에 `WritingIntent` enum과 `NextUnit{title,unit_kind,goal}`를 추가하고 `WritingRequest`/`WritingCandidate`에 `intent`/`next_unit`(append 기본)를 실었다. generate 서비스는 candidate가 request의 intent/next_unit를 echo하게 했다(기본값으로 append 호환).
- **accept 검증**: `_validate`가 provider/write 전에 append+next_unit·start+missing next_unit·candidate/request intent·next_unit 불일치·blank title·blank goal을 400으로 막는다.
- **Core SOT 6-surface 원자 write**: `WritingAcceptReceipt` 모델과 `start_next_unit`을 추가했다. current 뒤 position을 archived 포함 +1 shift하고 current+1에 새 active Draft, version 1/snapshot/blocks, accept receipt를 한 transaction으로 commit한다. in-memory before-image rollback과 Mongo transaction/single-writer fallback rollback을 구현하고, `(project_id,idempotency_key)` unique index와 실패 주입 seam(`_after_start_next_write`)을 추가했다.
- **accept 서비스**: intent로 분기해 append는 기존 3-surface 저장+save-key read-through replay, start_next는 receipt replay+원자 저장을 사용한다. replay lookup은 stale base·Gate보다 먼저 수행한다. `WritingAcceptResult`/`WritingAcceptAnalysisError`가 `intent`와 `target_draft`(unit_kind/position)를 싣고 두 intent 모두 `analyze:{snapshot_id}` job으로 수렴한다.
- **HTTP**: `NextUnitBody`(extra=forbid, goal required-nullable)와 `WritingAcceptRequest`의 `intent`/`next_unit`, 응답 `intent`, `AcceptedSavePayload`의 `draft_id/unit_kind/position`, partial 502의 `intent`+넓힌 saved를 추가했다.
- **회귀**: WI-01~22 named 행을 `WritingIntentAcceptTest`/`WritingIntentCompatibilityTest`/`WritingIntentApiTest`/`WritingIntentMongoTest`(WI-11)로 구현하고, in-memory rollback hardening과 mongo index under-strict guard를 보강했다. SC-01/02(`WorkspaceW0SchemaIntegrationTest`)를 W3 OU·Writing intent fragment까지 확장했다.
- **프론트**: WritingPanel에 채택 방식 라디오(현재 이어쓰기|다음 유닛 시작)와 새 유닛 title/kind/goal 입력을 추가하고 accept body에 intent/next_unit를 배선했다. 제목 미입력 시 accept 차단·안내를 추가했다. `gen:api`로 타입 재생성 후 build·테스트를 통과시켰다.

### Issues found

- 기존 accept envelope-key 회귀 2개와 WritingPanel accept-body 단정 2개가 새 `intent`/넓힌 `saved` 필드로 실패해 새 계약에 맞게 갱신했다(예상된 계약 변경).
- `NextUnitBody`가 catalog `additionalProperties:false`와 어긋나 `extra="forbid"`를 붙였고, `goal` optional↔required 불일치는 정본 catalog에 맞춰 required-nullable로 정렬했다. WI API 테스트 body에 `goal: null`을 명시했다.
- 첫 live Mongo 실행은 샌드박스 socket 차단으로 skip됐다. WI-11 등 Mongo transaction 회귀는 실 replica-set 실행이 남는 항목이다.

### Decisions

- append 경로는 receipt를 쓰지 않고 기존 save-key read-through replay를 유지해 legacy 호환(WI-17)과 byte-identical append 동작을 보존했다. receipt는 target draft가 사전 미지인 start_next에만 필요하다.
- 계약이 accept 중심이라 generate HTTP 표면은 intent를 받지 않고, candidate echo만 서비스 계층에서 유지했다. goal은 본문에 저장하지 않으며(WI-16) 프론트가 생성 지시로만 전달한다.
- accept 요청은 W0 catalog의 `writingAcceptRequestV2` oneOf를 literal FastAPI oneOf로 강제하지 않고 §3.1의 flat/backward-compat shape을 유지했다. SC-01은 동형이 성립하는 response·reorder·enum·nextUnit fragment를 대조한다.

### Verification

- `python3 -m pytest tests/test_writing_accept.py tests/test_project_brief.py -q` → **62 passed / 24 subtests**.
- backend full `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **1181 passed / 73 skipped(Mongo-gated) / 297 subtests**.
- frontend `npm test -- --run` → **146 passed / 10 files**.
- `npm run gen:api` 두 번째 생성물과 tracked `schema.d.ts` **byte-identical**; `npm run build` → **96 modules**; `git diff --check` clean.
- LLM 호출 없음(결정적 계약, 사용자 제약).

### Next steps

- Docker/replica-set 테스트 머신에서 WI-11(`WritingIntentMongoTest`) six-surface transaction rollback과 Mongo start_next 경로를 실행해 마지막 live 축을 닫는다.
- W3 전체 closure에 대한 독립 검증(요청 시)과 W4 export 착수.

---

## Task — W3 증분 2 독립 검증 PASS 후 H1 hardening + 커밋

### Goals

- 독립 검증 `docs/verifications/2026-07-19/w3_writing_intent.md`의 PASS(조건 없음)와 hardening H1/H2를 확인하고 보강 가능한 부분을 반영한다.
- 검증 대상 uncommitted 변경을 하나의 커밋으로 묶는다.

### User Decisions and Rationale

- 사용자는 독립 검증 기록을 근거로 보강 가능한 부분을 보강한 뒤 커밋하도록 지시했다. 독립 검증 기록 자체는 감사 artifact이므로 수정하지 않고, 그 H1 권고만 테스트에 반영했다.

### Completed work

- **H1 hardening**: WI-11(`WritingIntentMongoTest`)이 6-surface 중 version·block surface를 간접 cover하던 것을 명시적으로 pin했다. 실패 주입 전 versions/snapshots/blocks/receipts count를 캡처하고 rollback 후 모두 불변임을 단정한다. 로컬에서 실제 실행되는 `WritingIntentInMemoryRollbackTest`에도 동일하게 version/snapshot/block surface 명시 단정을 추가해 6-surface 전부(draft/position·version·snapshot·block·receipt)를 로컬에서도 잠갔다.
- **H2**: uncommitted 변경 전체(W3 증분 2 + H1 hardening)를 하나의 커밋으로 묶어 다음 worker가 깨끗한 base에서 W4를 착수할 수 있게 했다.

### Decisions

- 독립 검증의 verdict은 조건 없는 합격이므로 계약·구현 변경은 하지 않고 H1(명시적 surface pin)만 테스트 강화로 반영했다. 이는 W0 §3.2 "transaction 실패 시 6 surface 모두 0건"을 회귀에서 완전히 명시화한다.

### Verification

- `python3 -m pytest tests/test_writing_accept.py::WritingIntentInMemoryRollbackTest tests/test_core_sot_mongo.py -q` → **1 passed / 54 skipped(Mongo-gated)** (Mongo 미기동 시).
- backend full(Mongo 미기동) → **1181 passed / 73 skipped / 297 subtests**(H1은 기존 테스트에 단정 추가라 수치 불변).

### Next steps

- ~~Docker/replica-set 머신에서 WI-11의 명시적 6-surface pin이 실 transaction에서 통과하는지 확인한다.~~ → 아래 live 검증에서 완료.
- W4 ordered-latest export 착수.

---

## Task — WI-11 + Mongo 통합 live replica-set 실증 (이 머신 = 풀테스트 머신)

### Goals

- 앞 task가 "테스트 머신에 남김"으로 처리한 WI-11 six-surface transaction rollback을 이 머신에서 실제 replica-set Mongo로 실행해 닫는다.

### User Decisions and Rationale

- 사용자가 이 머신이 Docker/Mongo를 갖춘 **풀테스트 머신**임을 지적했다. 앞 task는 서브 머신 컨텍스트(Docker CLI 없음)를 그대로 넘겨짚어 Mongo를 시도조차 하지 않고 skip으로 남긴 잘못이 있었다. 실제로 이 머신엔 `docker 28.5.1`/`compose v2.40.2`가 있어 replica-set을 띄울 수 있었다.

### Completed work

- `COMPOSE_BAKE=false docker compose up -d mongo`로 단일 노드 replica-set(`rs0`)을 기동했다. RS member가 `mongo:27017`로 광고되고 호스트 `/etc/hosts` 수정 권한이 없어, 검증 동안만 RS member host를 `localhost:27017`로 `rs.reconfig`한 뒤 호스트 pytest가 트랜잭션까지 붙는 것을 확인했다.
- `CORE_SOT_TEST_MONGO_URI=mongodb://localhost:27017/?replicaSet=rs0`로 실행:
  - `WritingIntentMongoTest`(WI-11 포함) → **17 passed / 0 skipped**. WI-11 `test_start_next_transaction_rolls_back_entire_write_set`가 실 transaction에서 6-surface(draft/position·version·snapshot·block·receipt) 명시 pin으로 통과.
  - `tests/test_core_sot_mongo.py` 전체 → **54 passed / 0 skipped**.
  - backend full(Mongo 포함, ignore 없음) → **1254 passed / 4 skipped / 297 subtests**. 남은 4 skip은 W3와 무관한 live Chroma 1 + Elasticsearch 3(패키지 미설치)뿐이다.
- 검증 후 RS member host를 `mongo:27017`로 원복(compose 스택 정상 동작 보장)하고 mongo 컨테이너를 정지해 머신을 원래(미기동) 상태로 되돌렸다. data volume은 보존.

### Issues found

- 앞 task의 "Mongo-gated 73 skipped"는 이 머신에서는 인프라 부재가 아니라 **Mongo 미기동** 때문이었다. 기동하면 73→4로 줄고 전부 통과한다. skip 수를 인프라 한계로 오인해 시도하지 않은 것이 실책이다.

### Verification

- WI-11 + Mongo core sot: **17 / 54 passed, 0 skipped**(live replica-set).
- backend full(Mongo 포함): **1254 passed / 4 skipped(Chroma 1 + ES 3, W3 무관) / 297 subtests**.

### Next steps

- W4 ordered-latest export 착수. W3는 live Mongo까지 포함해 전부 닫혔다.
