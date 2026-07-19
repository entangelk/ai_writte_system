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
