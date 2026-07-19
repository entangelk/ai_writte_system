# W2 테스트 머신 운영 closure — 독립 검증

> **2026-07-19 독립 재감사 정정 및 closure:** 최초 기록의 전체
> `schema.d.ts` byte-identical 주장은 재현되지 않았고, 그 시점 판정은
> **조건부 합격**이 맞았다. 상세 반박은 `w2_operational_closure_audit.md`.
> 이후 fresh schema 재생성 + client 단일 component 정렬로 B1/B2를 닫았으며,
> 아래 Verdict는 보강 후 최종 상태를 함께 기록한다.

## Subject metadata

- **날짜**: 2026-07-19
- **요청자**: 오너("서브 머신에서 못했던거 검증작업부터 진행")
- **검증자**: Codex
- **검증 대상 slice/artifact**: Writing Workspace V2 W2의 서브 머신 미실행 축 — 지원 Node 프론트 재현, application/frontend 이미지, 실제 replica-set Mongo 동시 PUT, nginx ProjectBrief/API/overview 스모크
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.7.13(Approved), `docs/plans/writing-workspace-v2-w0-contract.md` §1·§4 PB-01~12/SC-01~02, `schemas/writing-workspace-v2-w0.schema.json`
- **최초 작업 출처**: `main`, commit `f5a0f3b` (`feat: Writing Workspace V2 W2 작품 정보와 개요 구현`), 검증 시작 시 clean working tree
- **재감사 closure 출처**: working tree, uncommitted(`frontend/src/api/client.ts`, generated `frontend/src/api/schema.d.ts`, 본 기록·work log·HANDOFF 정정)

## Scope

1. Node `>=22.22.0` 환경의 `npm ci`, 전체 Vitest, OpenAPI→TypeScript 재생성, production build.
2. 최신 source의 application/frontend Docker image build.
3. single-node replica-set Mongo에서 `tests/test_core_sot_mongo.py` 전체와 신규 ProjectBrief 동시 충돌 회귀의 fallback/transaction 양쪽 실행.
4. nginx `/api`를 통한 ProjectBrief PUT/current/history/version/replay와 SPA deep-link fallback.
5. 실제 Chrome DOM에서 ProjectBrief, canonical memory, pending count의 분리 및 pending payload 비노출.
6. 검증 중 사용한 격리 DB/일회성 컨테이너 정리.

기존 정적 W2 계약 감사(PB/SC matrix, 구현, unit/OpenAPI)는 `w2_project_brief_overview.md`가 이미 PASS로 닫았으므로 중복 감사하지 않았다. 이번 기록은 그 문서의 Outstanding인 운영 축만 독립적으로 닫는다.

## Methodology

- 먼저 W2 계약 범위를 확인했다. W2 소유권은 `writing-workspace-v2-w0-contract.md:16`, ProjectBrief version/API/replay 계약은 `:27-55`, named matrix는 `:143-154`와 `:191-192`다.
- `node:22-slim`의 실제 버전을 확인하고, Docker build stage(`services/frontend/Dockerfile:5-21`)에서 의존성 설치/build를 재현했다.
- git-ignored 중간물 `frontend/openapi.json`은 현재 Python app에서 다시 생성했다. 최초 검증은 지원 Node의 생성물과 커밋된 `schema.d.ts`가 byte-identical하다고 잘못 판정했지만, 독립 재감사는 **106805 bytes fresh vs 106941 bytes committed** 차이와 `WritingCandidatePayload-Input/-Output` drift를 재현했다. 보강에서는 fresh schema를 tracked 파일로 반영하고 client를 현재 app의 단일 component에 정렬한 뒤 두 번째 fresh 생성물과 byte 비교했다.
- Mongo 테스트는 테스트 자체의 throwaway DB/drop 계약(`tests/test_core_sot_mongo.py:1-13`)에 따라 실행했다. 샌드박스 내 최초 33 skip은 호스트 포트 차단 결과라 무효화하고, Docker 포트 접근 권한으로 재실행한 33 pass만 근거로 사용했다.
- UI smoke용 DB `ai_writing_system_w2_verify`에 canonical 1건과 `needs_review` 1건을 격리 seed했다. Chrome `--dump-dom` 결과에 required literal 6개가 모두 있고 pending payload literal 2개가 모두 없는지 프로그램으로 단정했다.

실행 명령:

```bash
COMPOSE_BAKE=false docker compose build application frontend
docker build --target build -t ai_writte_system-frontend-w2-verify \
  -f services/frontend/Dockerfile .
docker run --rm ai_writte_system-frontend-w2-verify \
  sh -lc 'node --version && npm --version && npm test -- --run'
python3 scripts/dump_openapi.py > frontend/openapi.json
docker run --rm -v /mnt/f/devel/ai_writte_system:/repo \
  -w /repo/frontend ai_writte_system-frontend-w2-verify \
  sh -lc 'PATH=/app/node_modules/.bin:$PATH openapi-typescript openapi.json -o /tmp/schema.d.ts && cmp -s /tmp/schema.d.ts src/api/schema.d.ts'
CORE_SOT_TEST_MONGO_URI='mongodb://localhost:27017/?directConnection=true' \
  python3 -m pytest tests/test_core_sot_mongo.py -q -p no:cacheprovider
curl -sS http://localhost:5173/api/projects/<project_id>/brief
curl -sS http://localhost:5173/api/projects/<project_id>/brief/versions
curl -sS http://localhost:5173/api/projects/<project_id>/brief/versions/<version_id>
google-chrome --headless --no-sandbox --disable-gpu \
  --virtual-time-budget=5000 --dump-dom \
  http://localhost:5173/projects/<project_id>/overview
```

## Findings

### 지원 Node·생성 타입·프론트

- `node:22-slim`은 **v22.23.1**, npm **10.9.8**로 `react-router` 요구 `>=22.22.0`을 만족했다.
- fresh `npm ci`: **195 packages**, audit vulnerability **0**.
- Vitest: **143 passed / 10 files**. overview 전용 4건도 포함됐다.
- **최초 주장 정정**: commit `f5a0f3b`의 `schema.d.ts`는 현재 app에서 재현되지 않았다. ProjectBrief 18행은 일치했지만 기존 Writing candidate/gate가 stale `-Input/-Output` component를 가졌고, fresh gen 뒤 `client.ts`의 두 참조 때문에 `tsc`가 실패했다.
- **보강 후**: current app authority에 따라 `schema.d.ts`를 fresh 재생성하고 `WritingCandidate`/`WritingGate` alias를 단일 `WritingCandidatePayload`/`WritingGatePayload`로 복원했다. 같은 openapi.json의 두 번째 생성물은 tracked schema와 byte-identical하고, fresh gen 뒤 build가 통과한다.
- production build: TypeScript clean, **96 modules**, CSS 17.54 kB(gzip 3.94), JS 284.19 kB(gzip 87.85).

### Docker image

- application/frontend 최신 이미지 빌드가 모두 PASS했다. frontend image는 Dockerfile의 `npm ci`와 `npm run build`를 실제 지원 Node stage에서 수행했다(`services/frontend/Dockerfile:5-21`).
- Compose v2.40.2의 기본 Bake 경로는 source와 무관한 내부 slice-bounds panic을 냈다. 기존 프로젝트 전례와 같은 `COMPOSE_BAKE=false`에서 동일 build가 성공했다.

### 실제 Mongo 동시성

- replica-set Mongo에 direct connection으로 `tests/test_core_sot_mongo.py` **33 passed / 0 skipped**.
- 동일 mixin을 `FallbackMongoTest`와 `TransactionMongoTest`가 각각 실행하므로(`tests/test_core_sot_mongo.py:93-109`, `:526-643`), `test_concurrent_project_brief_version_collision_has_one_success_one_stale`(`:160-199`)는 두 모드에서 모두 실제 실행됐다.
- 두 writer가 같은 empty base를 본 경계에서 success 1/stale 1, replay false, 저장 version 1개를 유지했다. W2 hardening H3의 live 축이 닫혔다.

### nginx/API/browser

- nginx `/api` prefix strip은 설정 literal(`frontend/nginx.conf:12-18`)대로 실제 application에 도달했다. PUT은 padding을 trim한 version 1을 만들었고 current/history/version GET이 같은 8-field brief를 반환했다.
- 같은 key에 의도적 stale base와 다른 body를 넣은 replay는 최초 version을 `idempotent_replay=true`로 반환했고 history는 1건이었다. 계약의 replay-before-stale(`writing-workspace-v2-w0-contract.md:53`)과 일치한다.
- `/projects/<id>/overview` 직접 진입은 nginx fallback(`frontend/nginx.conf:27-30`)을 거쳐 React 최종 DOM을 렌더했다.
- Chrome DOM 기계 단정 결과: `required_missing=[]`, `pending_body_leaked=[]`, `deep_link_rendered=True`. ProjectBrief version 1·정본 인물은 표시되고 `검토 전 1개 →`만 별도 표시됐으며 pending 이름/본문은 canonical grid에 노출되지 않았다. 이는 UI 구현의 서버 재조회·분리 지점(`frontend/src/projects/ProjectOverview.tsx:66-85`, `:213-238`)과 일치한다.

### 정리

- 격리 DB `ai_writing_system_w2_verify`를 drop했고 일회성 `w2-application`/`w2-frontend`를 `--rm` 정지했다. 검증을 위해 기동한 Mongo도 이전 정지 상태로 되돌렸다. 격리 smoke 데이터는 의도적으로 삭제되어 복구 대상이 아니다.
- 독립 재감사 H1에서 지적한 검증 전용 `ai_writte_system-frontend-w2-verify` image(377MB)도 B1/B2 최종 검증 후 삭제했다. 제품 application/frontend image는 유지했다.

## Issues / Risks

### Blocking (contract obligations)

- **B1(폐쇄)**: 최초 기록의 전체 `schema.d.ts` byte-identical 주장이 허위였다. 재감사 기록의 hash/size/diff를 수용하고 본 기록·work log·HANDOFF의 표현을 정정했다.
- **B2(폐쇄)**: fresh gen이 `client.ts`의 stale `-Output` 두 참조를 끊어 build를 실패시켰다. fresh `schema.d.ts` 반영과 단일 component alias 복원 후 같은 gen을 반복해 byte 동일성을 확인했고 focused backend 27 passed/5 subtests, frontend 143/10, build 96 modules를 통과했다.

### Hardening recommendations (non-blocking)

- **H1 — Compose Bake 도구 결함**: Docker Compose v2.40.2 기본 Bake가 내부 panic을 낸다. 프로젝트 source 결함은 아니며 `COMPOSE_BAKE=false`로 빌드는 재현된다. Compose/buildx 정비 시 우회 플래그를 제거한다.
- **H2 — W2-only smoke 명령 정밀화**: base compose의 application 환경은 Chroma/embedding/ES 주소를 설정하므로 dependency를 단순히 생략하면 app import 시 Chroma 연결로 실패한다. W2가 LLM 비의존이라는 계약은 맞지만, 경량 smoke는 이번처럼 optional backend env를 제외한 일회성 application 컨테이너를 쓰거나 full non-LLM dependency stack을 올리는 명령을 명시해야 한다.
- **H3 — 호스트 Node**: 호스트는 v22.17.0으로 계속 지원 범위 미달이다. 배포 및 이번 검증은 v22.23.1 container라 PASS지만, 호스트에서 직접 npm 명령을 표준화하려면 별도 upgrade가 필요하다.

## Verdict

**최종 PASS(조건 없음) — 독립 재감사 conditional의 B1/B2 closure 후.**

시간 순 판정은 다음과 같다.

1. 최초 운영 기록: PASS로 썼으나 byte-identical 근거가 틀렸으므로 **조건부 합격으로 정정**.
2. 독립 재감사: B1/B2 때문에 **조건부 합격**.
3. 본 보강: 기록 정정 + fresh schema/client 정렬 + gen/test/build green으로 두 조건 폐쇄 → **최종 PASS**.

Load-bearing reasons:

1. 지원 Node에서 fresh type generation을 반복해 tracked schema와 byte 동일성을 확인하고 test/build를 재현했다.
2. 실제 replica-set Mongo에서 fallback/transaction 포함 33개가 skip 없이 통과해 동시 PUT H3를 닫았다.
3. 최신 application/frontend 이미지와 nginx 경유 ProjectBrief API가 동작했고 same-key replay/history 불변을 확인했다.
4. 실제 Chrome DOM에서 deep-link, canonical-only 표시, pending count 분리와 pending 본문 비노출을 기계적으로 확인했다.

## Outstanding items

- 생성 schema·client 보강과 검증 기록·work log·HANDOFF 변경은 working tree에 미커밋 상태다.
- 호스트 Node upgrade와 Compose/buildx 정비는 운영 hardening이며 W2/W3 진입을 차단하지 않는다.
- 독립 재감사의 B1/B2가 닫혔으므로 다음 코드 slice는 기존 승인대로 W3다.

## Reproduction

최소 재현 순서는 Methodology의 image build → 지원 Node test/type compare → Mongo 33-test → 격리 application/frontend 기동 → curl/Chrome DOM assertion 순서다. Mongo 테스트는 `directConnection=true`를 사용해야 host에서 replica-set member의 compose DNS 이름(`mongo`) 재해석 문제 없이 transaction capability를 유지한다. smoke DB는 고유 이름을 사용하고 종료 시 drop한다.
