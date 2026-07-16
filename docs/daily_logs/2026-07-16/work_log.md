# Work Log — 2026-07-16

## Goals

- HANDOFF와 2026-07-15 work_log이 지정한 다음 작업(★ 프론트엔드 첫 슬라이스, D3=A Product shell 척추)을 착수한다. 브리프가 Resolved라 별도 오너 결정 없이 시작한다.
- 브리프가 명시적으로 "첫 슬라이스에서 결정한다"고 남긴 항목(프론트 테스트 도구)과 슬라이스 범위만 오너에게 확인한 뒤 구현한다.
- 백엔드·계약·회귀는 무변으로 둔다(프론트는 신규 백엔드 없이 조립).

## User Decisions and Rationale

- **H1(응답 모델) → H2(입력 검증) 순서로 백엔드 공개 계약을 조인다**: 오너가 v1.6.94 독립 검증의 H1/H2를 보고 "커밋해주고 H1 응답모델 먼저 한 다음 H2까지 하는게 맞겠네"로 지시했다. 이로써 v1.6.94가 "별도 결정"으로 남긴 갭(응답 무타입)과 검증자가 발견한 spec-silent 입력 검증이 함께 닫힌다. 세부 3결정은 브리프(`plans/frontend-api-contract-decisions.md`)로 표면화해 확정:
  - **D1=A(척추 14 endpoint 먼저)** — 추천 채택. 문제는 "50 endpoint에 타입이 없다"가 아니라 "프론트가 손선언하는 자리에 없다"이고 그 자리는 지금 척추뿐이다. Writing·Review envelope은 UI가 아직 만나지 않아 지금 고정하면 계약을 두 번 만지게 되고, 그 트랙의 핵심 2 endpoint는 `JSONResponse`라 어차피 안 덮인다. 나머지 34개는 해당 UI 슬라이스에서.
  - **D2=A(`response_model=` 파라미터, 헬퍼 dict 유지)** — 추천 채택. payload 생성 헬퍼 20개를 한 줄도 건드리지 않고 OpenAPI가 실제 schema를 내게 한다(§3 surgical). 각하: D2=B(반환 타입 주석 — dict를 반환하며 모델 반환이라 주석하는 거짓말), D2=C(헬퍼가 모델 반환 — 이 문제를 푸는 데 필요한 것보다 훨씬 큰 재작성, §2).
  - **D3=A(HTTP 경계 pydantic `Field` → 422)** — 추천 채택. 검증자가 든 우회 시나리오가 전부 HTTP를 지나므로 경계에서 보고된 위험이 닫히고 **Core SOT 정본 계약은 무변**이다. 각하: D3=B(서비스 계층 — 정본 계약을 여는 값에 비해 "scripts가 빈 이름 생성"만 추가로 삼), D3=C(이중화 — 같은 규칙 두 곳, 드리프트 위험).

- **슬라이스 범위 = scaffold + 프로젝트 목록/생성까지(에디터는 다음 슬라이스)**: 오너가 두 선택지(① scaffold+목록/생성 ② 척추 A 전체) 중 ①을 택했다. 근거로 제시하고 오너가 수용한 것: 스택 배선(Vite+nginx+타입 생성)이 실제로 도는지 먼저 확인하는 편이 안전하고, 에디터는 Core SOT 계약(명시적 version save only + `idempotency_key` 필수)이 두꺼워 독립 슬라이스로 다루는 게 낫다. 이는 브리프 D3 각주("A 자체도 한 슬라이스로 크면 `프로젝트 목록+생성` / `에디터+저장+version` 둘로 쪼갠다")의 발화이지 결정 변경이 아니다.
- **프론트 테스트 도구 = Vitest + React Testing Library**: 브리프 "이번 결정에 포함하지 않는 것"이 테스트 도구를 첫 슬라이스로 미뤄뒀고, 이번이 그 첫 슬라이스라 오너에게 확인했다. 오너가 추천(Vitest+RTL)을 채택했다. 근거: Vite와 설정/트랜스폼을 공유해 추가 빌드 체인이 0이고, 이 저장소의 양방향 회귀 관례(under-strict/over-strict guard)를 프론트에도 그대로 적용할 수 있다. 각하: 도구 미도입(§2에 가장 부합하나 첫 회귀가 늦어짐), Playwright e2e 추가(1인 로컬 스택에 운영 표면 증가, 첫 슬라이스 과대).

## Completed work

### Frontend 첫 슬라이스 — scaffold + 프로젝트 목록/생성 (SoT v1.6.94, D1=A/D2=B/D3=A)

**신규 파일**

- `frontend/` — Vite+React+TS SPA. `package.json`(스크립트 `dev`/`build`/`test`/`gen:api`), `tsconfig.json`(strict), `vite.config.ts`, `vitest.setup.ts`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/styles.css`(최소 CSS, 디자인 시스템 미도입 — 브리프 기본값).
- `frontend/src/api/client.ts` — 얇은 `fetch` 래퍼(브리프 기본값: 캐시 라이브러리는 실제로 아플 때). `ApiError{status, detail}`가 FastAPI `detail`을 보존하고, `API_BASE = "/api"` 상수 하나가 단일 origin을 강제한다.
- `frontend/src/api/schema.d.ts` — `npm run gen:api` 생성물(2722줄, 50 endpoint). **커밋한다**: 이미지 빌드 stage에는 Python이 없어 FastAPI 앱에서 재생성할 수 없다.
- `frontend/src/projects/ProjectList.tsx` — 프로젝트 목록/생성 화면. 생성 후 목록을 **서버에서 재조회**한다(클라이언트 낙관적 패치 없음 → 렌더된 목록이 항상 서버의 진실).
- `frontend/nginx.conf` · `services/frontend/Dockerfile` — node build → nginx 서빙 2-stage. deps 설치 레이어를 소스 복사보다 앞에 둬 빌드 캐시를 보존한다(HANDOFF Active Decisions).
- `scripts/dump_openapi.py` — FastAPI OpenAPI 스키마를 stdout으로 덤프하는 read-only 도구. `create_app()`을 기본(in-memory) collaborator로 조립만 하고 요청을 처리하지 않아 Mongo/Gateway/Chroma 연결이 없다.

**변경 파일**

- `docker-compose.yml` — `frontend` 서비스 추가(`${FRONTEND_PORT:-5173}:80`, `depends_on: application service_healthy`, wget healthcheck — alpine nginx에는 curl이 없다).
- `.dockerignore` — `frontend/node_modules/`·`frontend/dist/` 제외(호스트 산출물이 컨텍스트에 들어가 `npm ci` 레이어를 가리는 것 방지).
- `.gitignore` — `node_modules/`·`frontend/openapi.json` 제외. `package-lock.json`과 생성된 `schema.d.ts`는 **커밋 대상**임을 주석으로 명시.

**단일 origin 실현 (D2=B의 대가 상쇄)**

D2=B(별도 서비스)는 D2=A가 공짜로 주던 단일 origin을 잃는다. 브리프가 지정한 대로 nginx reverse-proxy로 상쇄했다:

- `location /api/` → `proxy_pass http://application:8000/` — **trailing slash가 prefix strip을 수행**한다(application은 `/projects`처럼 루트에 경로를 소유). dev는 Vite proxy의 `rewrite`가 같은 모양을 만든다.
- 결과: 브라우저가 cross-origin 호출을 하지 않으므로 **CORS 미개방 유지**(인증 없는 API의 노출을 늘리지 않는다 = D2=C 각하 근거를 D2=B 안에서 보존).
- `proxy_read_timeout 120s` — 배포 Writing loop의 wall-clock 기본은 60s(v1.6.89)다. 프록시 타임아웃이 그보다 작으면 nginx가 loop 자체 budget보다 **먼저** 끊어 Writing 워크스페이스(C 슬라이스)가 원인 불명으로 실패한다. 120s로 여유를 뒀다.
- `location /` `try_files ... /index.html` — SPA 클라이언트 라우팅(알 수 없는 경로가 404 대신 index.html).

**회귀 (양방향, 9개 — `frontend/src/projects/ProjectList.test.tsx`)**

- under-strict: 목록 렌더(archived 표시 포함)·빈 상태·POST 후 서버 재조회·trim 후 전송·list/create 실패 시 `status: detail` 노출.
- over-strict: **단일 origin 경로**(`fetch` 첫 인자가 정확히 `/api/projects` — 절대 URL로 바꾸면 조용히 CORS가 필요해지므로 이 assertion이 D2=B 계약을 잠근다)·**공백-only 이름 미전송**(trim 가드가 과교정돼 정상 이름을 막지 않는지도 함께)·실패 시 입력 보존·성공 시 이전 오류 해제.

### 독립 검증 PASS(조건 없음) + 비차단 hardening 반영 (프로덕션 코드 무변)

오너가 첫 슬라이스 독립 검증을 요청·완료했다(`docs/verifications/2026-07-16/frontend_first_slice.md`). **판정 합격(조건 없음), blocking 0.** 검증자가 1차 소스에서 재도출한 것 중 이 슬라이스의 핵심 위험을 직접 겨냥한 것: 손선언 응답 타입이 `main.py:1182 _project_payload`와 literal 1:1 일치, 단일 origin 상쇄가 구성+live(음성 `/api/nonexistent` 404 추가 확인)로 입증, 정량 주장 전부 독립 재현(`schema.d.ts` 재생성 IDENTICAL 포함), 백엔드 git 무변경(`services/**`·`tests/**` 0건).

비차단 hardening 6건 중 **3건 반영, 3건 코드 무변**:

- **H6 반영 — 이중 제출 회귀 추가**: `saving` 가드는 이미 프로덕션 코드(`ProjectList.tsx:27,30`)에 있었으나 잠금이 없었다. 신규 회귀는 in-flight POST를 deferred promise로 붙잡아 둔 채 **`fireEvent.submit`으로 disabled 버튼을 우회**해 `submit()` 내부 가드를 직접 pin한다(버튼 `disabled` 속성만 검사하면 코드 가드가 지워져도 통과하므로). **mutation 실증**: `if (trimmed === "" || saving)` → `if (trimmed === "")`로 가드를 제거하면 **정확히 이 1개만 실패**하고 나머지 9개는 통과(부수 효과 없음). 구현 무변.
- **H3 반영** — 브리프 `frontend-kickoff-decisions.md:5` "관련 정본"이 v1.6.92를 가리키고 있었다. v1.6.94로 정정하되 이력(작성 v1.6.92 → 결정 v1.6.93 → 구현 v1.6.94)을 함께 남겼다.
- **H4 반영** — compose `frontend` 주석이 "SoT v1.6.93"이라 결정과 구현이 뭉개져 있었다. "결정은 v1.6.93에서 잠기고, 이 서비스로 구현된 건 v1.6.94"로 분리했다.
- **H2 코드 무변 → 오너 결정으로 상향**: `core_sot/service.py`의 `create_project(name)`에 **빈/공백 이름 검증이 없다**. 프론트 trim 가드는 spec-silent UX 동작이라 다른 클라이언트·trim하지 않는 미래 화면이 우회하면 백엔드가 빈 이름 project를 mint한다(현 슬라이스는 프론트가 막아 영향 없음). **백엔드에 검증을 조용히 추가하지 않았다** — 공개 계약 표면을 어디까지 조일지는 오너 결정이고, 이 슬라이스의 "백엔드 무변" 목표 밖이다. H1(`response_model`)과 같은 축("백엔드 공개 계약을 얼마나 조일지")이라 묶어서 HANDOFF Owner Decisions에 올렸다.
- **H1 코드 무변** — 이미 상향된 항목이고 검증은 "에디터 슬라이스 전이 가장 싸다"는 권고를 강화했다.
- **H5 코드 무변** — 생성된 경로 타입이 call-site에서 아직 미소비. 검증자도 "결함 아님, 엔드포인트 배선이 늘면 자연 소비"로 판단했다. 지금 억지로 소비시키는 건 §2 speculative이라 보류한다.

### 백엔드 공개 계약 조이기 — H1 척추 응답 모델 + H2 이름 검증 (SoT v1.6.95, D1=A/D2=A/D3=A)

오너가 검증 H1/H2를 보고 **"H1 먼저 → H2"** 순서로 착수를 지시했다. 방향은 정해졌으나 범위·방식·검증 위치가 공개 계약을 구속해 브리프(`plans/frontend-api-contract-decisions.md`)로 fork를 표면화한 뒤 구현했다.

**착수 전 실측이 브리프의 그림을 바꾼 것** (추측으로 썼으면 틀렸을 지점):

- **`/writing/revise-and-gate`·`/writing/accept`의 partial-failure 응답은 `JSONResponse` 직접 반환**이라 FastAPI가 response_model을 **검증도 문서화도 우회**한다. H1이 구조적으로 못 덮는 구멍이고, 하필 Writing 트랙(C 슬라이스)이 소비할 표면이다. → 브리프에 명시하고 Deferred로 넘겼다. **(검증 후속 정정, H1-d2)**: 착수 당시 이를 "48개만 적용 가능 / 2개는 JSONResponse 직접 반환이라 불가"로 적었으나 **부정확**했다 — 두 endpoint의 **성공 경로는 dict를 반환하므로 `response_model` 적용이 가능**하고, uncoverable한 것은 endpoint 전체가 아니라 **partial-failure envelope**뿐이다. 결론(D1=A 척추 한정 + Deferred)과 fork 서술 (a)/(b)는 불변이라 정본 문구만 정확한 진술로 고쳤다.
- 요청 모델 5종 전부 제약 없는 `str`(`Field`/validator 사용처 **0**) → H2는 이 저장소의 첫 입력 제약.

**H1 구현 (D1=A 척추 14 endpoint, D2=A `response_model=` 파라미터)**

- **안전망을 모델보다 먼저 깔았다** — 이게 이 슬라이스의 핵심 절차다. `response_model`은 모델이 선언하지 않은 필드를 **조용히 삭제**하는데(오류·경고 0), 기존 회귀에는 exact-key set assertion이 **하나도 없었다**(개별 키만 읽음). 즉 모델부터 붙였으면 필드 유실이 green으로 통과했다. 신규 `SpineEnvelopeKeyTest` 5개로 척추 전 envelope의 완전한 키 집합을 잠그고, **현 dict payload에서 통과함을 먼저 확인**한 뒤 모델을 적용했다.
- **필드 유실 실증**: `SnapshotDetailPayload`에서 `project_id`를 빼면 공개 API 응답에서 그 필드가 사라지는데, **1104개 테스트 중 이 exact-key 회귀 1개만** 잡았다(나머지 1103개 통과). 안전망 없이 진행했다면 그대로 배포됐을 실패 양식이다.
- **save/read surface 모델 분리 강제**: `save_draft`와 `get_draft_version`이 **같은 키 이름(`draft_version`/`snapshot`/`blocks`)에 다른 shape**을 담는다(save는 `{id,version_number,snapshot_id}`, read는 `project_id`/`draft_id`까지). 모델을 공유했으면 save 응답에서 필드가 사라지거나 read가 좁아졌다. `SavedDraftVersionPayload`/`SavedSnapshotPayload`/`SavedSourceBlockPayload`를 read 모델과 별도로 선언하고 그 이유를 주석에 남겼다.
- **H1이 실제로 값을 내는지 실증**: 백엔드 `ProjectPayload.archived` → `is_archived` rename + `npm run gen:api` 재생성 → **프론트 `tsc`가 `ProjectList.tsx(71,24)`를 짚어 실패**. v1.6.94가 기록한 "백엔드 payload 변경이 컴파일 타임에 안 잡힌다"가 척추 구역에서 닫혔다. 이후 전부 복원.
- `client.ts`의 손선언 `Project` 삭제 → `components["schemas"]["ProjectPayload"]` 소비. v1.6.94 검증 H5(경로 타입 call-site 미소비)도 자연 해소됐다.

**H2 구현 (D3=A HTTP 경계)**

- `NonBlankName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]`를 project/draft의 create·rename 요청 모델 4종에 적용. **strip이 min_length보다 먼저** 돌아 `"  겨울 이야기  "`는 `"겨울 이야기"`로 저장되고 `"   "`는 **422**다(pydantic 2.12.5에서 순서 직접 확인 후 채택).
- **Core SOT 정본 계약은 건드리지 않았다**. 검증자가 든 우회 시나리오(다른 클라이언트·trim 안 하는 미래 화면)가 **전부 HTTP를 지나므로** 경계에서 막으면 보고된 위험이 닫힌다. D3=B(서비스 계층)는 정본 계약을 여는 값을 치르고 "scripts가 빈 이름을 만드는 것"만 추가로 사는데, 그건 지금 실재하는 위험이 아니다.
- 프론트 trim은 **UX 편의일 뿐 계약이 아니고**, 이제 계약은 이 경계 제약이라는 점을 SoT에 명시했다.

**회귀 +12 (양방향, mutation 전부 bite 실증)**

- `SpineEnvelopeKeyTest` 5: 척추 전 envelope exact-key. mutation ① `ProjectPayload.archived` 제거 → 새 회귀 + 기존 3개 bite / ② `SnapshotDetailPayload.project_id` 제거 → **새 회귀만** bite(안전망의 고유 가치 실증).
- `BlankNameRejectionTest` 7(subtest 13): 공백-only 4종 거부·rename 거부·**빈 이름이 store에 안 닿음**(over-strict) · **padding은 거부가 아니라 strip**(under-strict — 과교정 방지) · 일반 이름 통과 · **내부 공백 보존**(strip이 중간까지 정규화하지 않음). mutation ① 제약 제거 → 12 실패 / ② strip 누락(min_length만) → 10 실패.

### v1.6.95 독립 검증 PASS(조건 없음) + 비차단 정정 반영 (코드 무변, 주석 1곳 포함)

오너가 H1/H2 슬라이스 독립 검증을 요청·완료했다(`docs/verifications/2026-07-16/backend_contract_tightening.md`). **판정 합격(조건 없음), blocking 0.** 검증자가 mutation 4종(A 안전망 단독 bite·B 프론트 `tsc` rename 검출·C/D H2 양방향)과 정량·live 키 집합을 전부 독립 재현했고, "안전망 먼저" 판단이 옳았음을 A로 재입증했다(1111개 중 1개만 bite).

비차단 4건 중 **3건 반영**:

- **H1-d2 반영 — 내 진술이 부정확했다(가장 중요)**: 착수 실측에서 "48개만 적용 가능 / 2개는 `JSONResponse` 직접 반환이라 response_model 불가"로 적었으나, 1차 소스 재확인 결과 **두 endpoint 모두 성공 경로는 평범한 dict를 반환**하고 `JSONResponse`는 **partial-failure에만** 쓰인다. 즉 `response_model`은 그 성공 경로에도 **적용 가능**하고, uncoverable한 것은 **partial-failure envelope**뿐이다. 결론(D1=A 척추 한정)과 Deferred fork (a)/(b)는 영향 없지만, **이유가 틀리면 다음 사람이 잘못된 전제로 판단**하므로 SoT 계약 절·버전 로그·HANDOFF 2곳·브리프 2곳·work_log를 정확한 진술로 고쳤다.
- **H1-d1 반영** — 브리프 D1=A 행이 "척추 13개(projects 2+drafts 8+snapshots 3)"였으나 실제 구성은 **14개(projects 5+drafts 5+versions 4)**이고 source-refs/index rebuild는 척추가 아니다. SoT·HANDOFF·코드는 처음부터 14로 정확했고 브리프 option 텍스트만 부정확 → 정정(범위 의도 동일).
- **H1-d3 반영** — `main.py` 모델 분리 주석이 "공유하면 save 응답에서 필드가 사라진다"고 방향을 뭉갰다. 정확히는 **양방향으로 다르게 깨진다**: 넓은 read 모델을 좁은 save payload에 쓰면 **필드 누락 검증 에러**, 좁은 save 모델을 read payload에 쓰면 **조용한 필드 삭제**. 결론(모델 분리)은 불변이고 주석만 정정.
- **422 detail 표시**는 기존 follow-up 유지(프론트 trim+disable로 현재 사용자가 볼 일 없음).

## Issues found

### `vite.config.ts`의 `process` 타입 부재로 빌드 실패

- 문제: `npm run build`의 `tsc --noEmit`이 `TS2591: Cannot find name 'process'`로 실패.
- 원인: `vite.config.ts`는 Node에서 실행되는데 `@types/node`가 없었다.
- 해결: `@types/node` devDependency 추가 + `tsconfig.json` `types`에 `"node"` 추가.
- 결과: `tsc --noEmit && vite build` 통과(31 modules, 195kB → gzip 62kB). dev proxy 대상의 env 오버라이드(`VITE_API_TARGET`)는 유지했다 — 이 저장소의 스택은 실제로 `APPLICATION_PORT`를 바꿔 기동하는 관례가 있어(dev stack env overrides) 고정 literal이면 dev proxy가 깨진다.

### OpenAPI 응답 페이로드에 타입이 없다 (계약 갭, 이번 슬라이스 밖)

- 문제: 브리프 기본값 "OpenAPI→TS 타입 생성"이 50 endpoint를 다 잠글 것으로 읽히지만, 실제 생성물은 **경로와 요청 바디만** 타입이 있다.
- 원인: HTTP 엔드포인트가 `-> dict[str, object]`로 주석돼 있어 FastAPI가 응답 schema를 `additionalProperties: true`(빈 object)로 내보낸다. 요청 바디는 pydantic 모델(`CreateProjectRequest` 등)이라 정상 생성된다.
- 조치: 이번 슬라이스가 소비하는 응답 shape(`Project{id,name,archived}`)만 `client.ts`에 손으로 선언하고 그 이유를 주석에 남겼다. SoT v1.6.94 계약 절에도 "타입 계약 동기화의 실제 범위"로 명시했다.
- 미해결(오너 결정 필요): 갭을 닫으려면 백엔드 엔드포인트에 `response_model`을 붙여야 하는데, 이는 50 endpoint의 public envelope에 pydantic 검증·직렬화를 도입하는 변경이라 "백엔드 무변" 목표 밖이고 별도 결정 사안이다. **현 상태의 실질 위험**: 백엔드 payload가 바뀌어도 프론트는 컴파일 타임에 못 잡고 런타임에 깨진다.
- **→ 같은 날 해소(척추 한정)**: 오너가 H1 착수를 지시해 **SoT v1.6.95에서 척추 14 endpoint에 `response_model` 적용**(위 "백엔드 공개 계약 조이기" 참조). 그 구역은 이제 컴파일 타임에 잡힌다(rename mutation으로 실증). **나머지 34 endpoint는 여전히 무타입**이고, `/writing/revise-and-gate`·`/writing/accept`의 **partial-failure envelope**은 `JSONResponse` 직접 반환이라 **구조적으로 response_model이 안 먹는다**(성공 경로는 dict라 적용 가능 — H1-d2 정정) — Writing 슬라이스에서 별도 처리.

## Decisions

- **응답 타입을 손으로 선언(백엔드 `response_model` 도입 대신)**: 슬라이스 목표가 "백엔드·회귀 무변"이고, `response_model` 도입은 50 endpoint의 public envelope에 검증 계층을 추가하는 큰 결정이다. 프론트 편의를 위해 백엔드 공개 계약을 조용히 바꾸지 않고 갭을 기록해 오너 결정으로 올린다. 대가: payload 변경이 컴파일 타임에 안 잡힌다.
- **생성된 `schema.d.ts`를 커밋**: 이미지 빌드 stage(node)에 Python이 없어 빌드 중 재생성이 불가능하다. 생성물 커밋은 중복이지만, 대안(빌드 stage에 Python 추가)은 이미지와 빌드 시간을 늘린다.
- **생성 후 목록 재조회(낙관적 갱신 없음)**: 서버가 id를 mint하고 archived 상태를 소유하므로, 재조회가 한 번 더 왕복하는 대신 클라이언트가 서버 상태를 추측하지 않게 한다. 로컬 1인 도구라 왕복 비용이 문제되지 않는다.
- **`frontend/`는 저장소 루트, Dockerfile은 `services/frontend/`**: 소스를 `services/frontend/`에 넣지 않은 이유는 기존 `services/*`가 전부 Python 서비스이고 그 안에 node 프로젝트를 섞으면 `.dockerignore`·PYTHONPATH 관례와 충돌하기 때문이다. Dockerfile 위치는 다른 서비스와 같은 자리(`services/<name>/Dockerfile`)로 맞춰 compose가 일관되게 읽는다.

## Verification

- **프론트 회귀**: `cd frontend && npm test` → **10 passed (1 file)**(초기 9 + 검증 hardening H6 이중 제출 1). H6는 가드 제거 mutation에서 단독 bite 실증 후 구현 복원.
- **프론트 빌드/타입**: `npm run build`(`tsc --noEmit && vite build`) → 통과, 31 modules transformed.
- **백엔드 회귀**: 프론트 슬라이스 시점 `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **1099 passed / 45 skipped / 260 subtests** = 착수 전 기준선과 정확히 일치(백엔드 무변 확인). 이후 v1.6.95(H1/H2)로 회귀 +12 → **1111 passed / 45 skipped / 273 subtests**.
- **compose**: `docker compose config --quiet` 통과. `docker compose build frontend` 성공.
- **live 관통(격리 네트워크, frontend+application 컨테이너)**: application을 in-memory(`CORE_SOT_MONGO_URI` 미설정) 단독 기동 + frontend 컨테이너를 같은 네트워크(`--network-alias application`)에 붙여 nginx 프록시를 실제로 관통시켰다:
  - SPA index `GET /` → **200 text/html**
  - SPA fallback `GET /projects/anything` → **200**(404 아님 = `try_files` 동작)
  - `GET /api/projects` → `{"projects":[]}` (prefix strip 동작)
  - `POST /api/projects {"name":"프록시 관통 확인"}` → `{"id":"project-1","name":"프록시 관통 확인","archived":false}` (한글 왕복)
  - `GET /api/projects` 재조회 → 생성된 프로젝트 1건
  - `GET /api/health` → `{"status":"ok"}`
  - 스모크 컨테이너·네트워크는 정리했다(`docker rm -f` + `docker network rm`).
- `git diff --check` clean.

### v1.6.95 (H1/H2) 검증

- **회귀**: 백엔드 **1111 passed / 45 skipped / 273 subtests**(+12: 척추 exact-key 5, blank name 7/subtest 13). 프론트 **10 passed**, `npm run build`(`tsc --noEmit && vite build`) 통과.
- **mutation 4종 전부 bite 실증(후 복원)**: ① `ProjectPayload.archived` 제거 → 새 회귀 + 기존 3개 / ② `SnapshotDetailPayload.project_id` 제거 → **1104개 중 새 회귀 1개만**(안전망 고유 가치) / ③ `NonBlankName`→`str` → 12 실패 / ④ strip 누락(min_length만) → 10 실패.
- **H1 성과 실증**: 백엔드 `archived`→`is_archived` rename + `gen:api` 재생성 → 프론트 `tsc`가 `ProjectList.tsx(71,24)` 짚어 실패(이전이라면 조용히 빌드). 복원 후 `tsc` clean.
- **live 관통(격리 네트워크, frontend+application, trap 정리)**: padding strip(`"  겨울 이야기  "`→`"겨울 이야기"`) · 공백-only **422** · 척추 envelope 키 전부 보존(가장 넓은 version detail의 `draft_version` 5키·`snapshot` 6키·`blocks` 8키) · `BlockKind` enum이 `"heading"`으로 직렬화 · export body 원문(`# 제목\n\n본문.`) PASS.
- `docker compose config --quiet`·`py_compile`·`git diff --check` 통과.

## Next steps

- **다음 슬라이스 = 척추 A의 나머지(원고 목록 → 에디터)**: `GET /projects/{id}/drafts`·`POST /projects/{id}/drafts` 목록/생성 → 에디터(평문 `textarea` + **명시적 저장** + version 목록). 붙는 계약: `POST /projects/{id}/drafts/{did}/versions`는 `idempotency_key` 필수이고 같은 키 재시도는 같은 version을 반환한다(프론트가 키를 mint·재시도에 재사용해야 함), archive된 project/draft 쓰기는 409, export는 `?format=txt|markdown`. **프로젝트 상세 라우팅이 이 슬라이스에서 처음 필요해진다** — 현재 SPA는 라우터가 없고 `try_files`만 깔려 있으니 라우터 도입(또는 최소 상태 기반 화면 전환) 여부를 그때 정한다.
- 이후: C(Writing 작업공간: generate→gate→accept, 진행 표시는 60s 동기 요청 후속 결정) → B(Review Inbox: v1.6.67 어포던스 `{action,eligible,reason}` 구동) → Phase 7.
- **~~오너 결정 대기(H1/H2)~~ → 같은 날 확정·구현 완료**(SoT v1.6.95, D1=A/D2=A/D3=A). 남은 후속: (1) **나머지 34 endpoint 응답 모델**은 해당 UI 슬라이스에서(D1=A 계약), (2) **`/writing/revise-and-gate`·`/writing/accept`의 partial-failure envelope** — 성공 경로는 dict라 `response_model`을 붙일 수 있으나 `JSONResponse`로 나가는 partial 응답은 구조적으로 안 덮이므로 Writing 작업공간 슬라이스에서 별도 결정(성공 경로만 모델+에러는 `responses={}` 문서화 vs 손선언 유지), (3) `raw_text`·`idempotency_key` 제약은 에디터 슬라이스에서 실제 필요가 보일 때.
- **422 detail 표시**: D3=A가 422를 도입했다. 프론트 `ApiError`는 status+detail을 보존하지만 422 detail은 FastAPI validation error 구조(배열)라 현재 `readDetail`이 `JSON.stringify`로 떨어뜨린다. 지금은 프론트가 trim+disable로 막아 사용자가 볼 일이 없지만, 사용자에게 보일 문구가 필요해지면 그때 매핑한다(브리프 follow-up).
- **autosave**는 에디터 슬라이스에서 사용자가 가장 먼저 기대할 기능이지만 "저장=version mint" 계약 변경 위험이 있어 여전히 별도 오너 결정이다(브리프 follow-up).

---

## Task 3 — 제품화 준비 트리거 기반 개선 백로그

### Goals

- 전체 리팩터링·운영 경량화·품질 측정·공개 준비를 지금 한꺼번에 수행하지 않고, 각 항목을 **실제 착수 시점과 종료 조건**으로 관리한다.
- 현재 제품 우선순위인 A→C→B 프론트 기본 루프를 보호하고 Phase 7의 진입 조건을 명시한다.
- 새 계획을 plans 인덱스·HANDOFF·CHANGELOG에 연결해 다음 작업자가 트리거를 놓치거나 Waiting 항목을 선행 구현하지 않게 한다.

### Completed work

- `docs/plans/product-readiness-backlog.md` 신설:
  - 문서 성격을 새 Phase/public contract가 아닌 **횡단 리스크·개선 백로그**로 고정했다.
  - `UX-1`, `ARCH-1`, `OPS-1`, `QUAL-1`, `PROC-1`, `REPO-1`, `LEGAL-1`, `GATE-1` 각각에 상태·착수 트리거·그때 할 일·종료 조건·다음 점검 시점을 부여했다.
  - 현재는 UX-1만 `In progress`, 문서 계층화 PROC-1은 `Standing`, 나머지는 트리거 전 `Waiting`으로 뒀다.
  - A 종료→ARCH 점검, C 종료→ARCH+OPS 점검, dogfood 1/2주→QUAL 점검, B+dogfood 종료→Phase 7 게이트라는 체크포인트를 고정했다.
- `docs/plans/README.md`: 읽기 순서에 backlog를 추가하고 SoT보다 아래인 보조 계획의 역할을 명시했다.
- `docs/plans/07-conversational-authoring.md`·`frontend-kickoff-decisions.md`: 종전의 넓은 “프론트 이후 Phase 7” 순서에 후속 `GATE-1`을 연결해 새 진입 조건이 선택적으로 보이지 않게 했다.
- `HANDOFF.md`: Current Status와 Next Tasks에 활성 상태·점검 시점을 연결했다. 다음 작업 자체는 원고 목록→에디터로 유지했다.
- `CHANGELOG.md`: 오너의 관리 방식 결정과 이유, 새 backlog 링크를 문서 전용 변경으로 기록했다. SoT/public contract/code는 변경하지 않았다.

### Issues found

- 처음 표현 후보였던 “별도 Phase”는 이 항목들의 성격과 맞지 않았다. Phase는 순차 기능 개발로 읽히지만 `main.py` 분리·Lite/Full·라이선스는 서로 다른 사건에서 발화하는 횡단 과제다.
- 해결: **트리거 기반 개선 백로그**로 이름을 고정하고, 트리거 전 구현 금지와 완료 증거 갱신 규칙을 함께 뒀다.

### Decisions

- **사용자 결정과 이유**: 오너는 우려 항목 전체를 지금 한 번에 처리하지 않고, 적절한 시기가 올 때마다 체크해 하나씩 제거하는 방식을 선택했다. 목적은 개선점을 잊지 않으면서도 현재 프론트 핵심 루프를 중단하지 않는 것이다.
- **새 Phase로 만들지 않음**: 기능 의존 순서가 아니라 사건 기반 착수 조건을 가진 항목들이므로 backlog가 더 정확하다.
- **Phase 7 기본 진입 게이트**: UX-1 기본 루프와 QUAL-1 2주 dogfood 검토를 완료한 뒤 첫 Phase 7 slice를 고른다. 새 근거로 오너가 우선순위를 바꾸면 해당 결정을 기록하고 갱신할 수 있다.
- **선행 구현 금지**: 이번 task는 문서화만 수행한다. `main.py`, Compose, telemetry, repository name, LICENSE는 변경하지 않는다.

### Next steps

- 즉시 다음 작업은 변함없이 A의 나머지인 원고 목록→에디터다.
- A slice 종료 시 backlog의 `ARCH-1` 트리거를 확인하되, 백엔드 변경이 없으면 Waiting을 유지한다.
- C Writing UI 종료 시 `OPS-1`을 Ready로 올릴지 확인하고 2주 dogfood 실행 경로를 준비한다.

---

## Task 4 — Product shell 원고 목록 slice 착수 점검

### Goals

- 사용자 지시대로 다음 원래 작업인 Product shell A를 작은 slice로 재개한다.
- 이번 slice를 프로젝트 선택→원고 목록/생성으로 제한하고 editor/save/version/export를 다음 slice로 분리한다.
- 프로젝트 상세 화면이 처음 생기며 발생한 routing owner fork를 코드 전에 표면화한다.

### Completed work

- `product-shell.md`·`frontend-kickoff-decisions.md`·`product-readiness-backlog.md`·HANDOFF와 현재 React/API/test를 다시 읽어 governing scope를 고정했다.
- 백엔드의 draft list/create 응답 모델과 endpoint가 이미 완성돼 있어 이번 slice가 프론트 조립만으로 가능함을 확인했다. `ARCH-1`은 backend route/model을 수정하지 않으므로 아직 미발화다.
- `docs/plans/frontend-project-navigation-decisions.md`를 작성해 A React Router Declarative BrowserRouter, B 자체 History API, C state-only, D HashRouter를 빠짐없이 비교했다.
- 공식 React Router 현재 문서의 Vite declarative 설치(`npm i react-router`)·BrowserRouter·dynamic segment·nested route 방식을 확인했다. 현재 React 19/Vite 7 구성과 맞고, nginx SPA fallback도 이미 준비돼 있다.
- 오너 선택 A를 브리프에 Resolved로 기록하고 `react-router@8.2.0`을 추가했다. 이 버전의 peer requirement가 재설치 때도 manifest에 드러나도록 React/React DOM 선언을 `^19.2.7`로 맞췄다.
- 회귀를 먼저 추가해 기존 프로젝트 행의 `/projects/:id` 진입, direct route, project별 exact API path, 원고 목록/빈 상태, 생성 후 서버 재조회, trim/공백-only, in-flight 이중 submit, archived read-only, 오류/입력 보존, 뒤로가기와 404 shell을 잠갔다.
- `frontend/src/App.tsx`·`main.tsx` — `BrowserRouter`와 `/`·`/projects/:projectId`·`*` route spine. Data/Framework mode와 loader/action은 추가하지 않았다.
- `frontend/src/drafts/DraftList.tsx` — URL의 `projectId`로 프로젝트와 원고를 병렬 조회하고, 생성 성공 후 서버 목록을 다시 읽는다. 보관 프로젝트는 기존 원고를 표시하되 생성 form을 숨긴다.
- `frontend/src/api/client.ts` — 생성 OpenAPI 타입을 쓰는 `getProject`·`listDrafts`·`createDraft`와 공유 API 오류 표시를 추가했다. backend route/model은 바꾸지 않았다.
- `frontend/src/projects/ProjectList.tsx`·`styles.css` — 프로젝트 이름을 상세 route 링크로 만들고 종이/잉크 계열의 조용한 작업면, resource row, 짧은 전환과 reduced-motion 대응을 구현했다. 별도 디자인 시스템·card grid는 만들지 않았다.
- SoT를 v1.6.96으로 올리고 브리프·Product shell 진행 상태·plans 인덱스·CHANGELOG·HANDOFF를 현재 구현과 다음 editor/save slice로 동기화했다.

### Issues found

- HANDOFF가 “프로젝트 상세 라우팅이 여기서 처음 필요 — 라우터 도입 여부를 그때 정한다”고 남긴 genuine fork가 실제로 도달했다.
- state-only를 조용히 택하면 바로 다음 editor에서 project+draft 선택 상태가 중첩되고 URL/deep-link/back 동작을 다시 설계해야 한다. 반대로 router dependency 도입도 이후 구조를 구속하므로 오너 선택 없이 진행할 수 없다.
- 최초 dependency install은 sandbox DNS 제한으로 실패해 승인된 외부 실행으로 재시도했다. 설치 후 Node 22.22.2·React 19.2.7·React Router 8.2.0의 engine/peer 조건을 확인했다.
- 개발 `StrictMode` smoke 로그에서 초기 GET이 두 번 보였으나 React 개발 검증 동작이며 mutation 요청은 submit handler에만 있어 중복 write는 없었다. 이 slice의 create 중복은 별도 in-flight 회귀로 잠갔다.

### Decisions

- **오너 결정 A**: 오너는 B(자체 History API)의 무의존·직접 제어를 개인적으로 선호하지만, editor·Writing·Review까지 이어질 project/draft route 확장성을 우선해 A(React Router Declarative BrowserRouter)를 선택했다.
- **A의 승인 경계**: `react-router` Declarative mode만 사용한다. Data/Framework mode, loader/action은 범위 밖으로 두고 기존 얇은 fetch client를 유지한다.
- **UI 기준**: 마케팅 hero나 card grid 없이 따뜻한 종이/잉크 계열의 조용한 작업면, 명확한 프로젝트→원고 계층, 절제된 route/list 전환을 사용한다(frontend-skill 적용).

### Next steps

- 다음 작은 slice는 `/projects/:projectId/drafts/:draftId` editor다: 평문 `textarea` → 명시적 save/version mint → version 목록 → txt/markdown export.
- 착수 전에 `idempotency_key` 생성·재시도 수명과 version 선택을 URL에 둘지 현재 선택 state로 둘지 기존 계약/선례에서 확정 가능한지 확인한다. genuine fork일 때만 새 브리프를 만든다.
- Product shell A 전체가 끝날 때 `product-readiness-backlog.md`의 `ARCH-1` trigger를 점검한다. 이번 slice는 backend 파일 무변이라 아직 발화하지 않았다.

### Verification

- red-first: 새 project link와 `DraftList` module이 없을 때 focused 회귀가 실패함을 확인한 뒤 구현했다.
- `cd frontend && npm test -- --reporter=dot` → **22 passed / 3 files**.
- `cd frontend && npm run build` → PASS, 89 modules, CSS 4.53 kB(gzip 1.62), JS 234.46 kB(gzip 75.18).
- `cd frontend && npm run gen:api` → PASS, 생성 `schema.d.ts` diff 없음.
- in-memory application + Vite 실 API smoke → 프로젝트 `겨울 이야기`·원고 `1장 — 첫눈` 생성 후 `/`와 direct `/projects/project-1` 렌더/GET·POST 200 확인.
- `services/`·`tests/`·`scripts/`·`docker-compose.yml` diff 0, `git diff --check` PASS. 자체 구현의 routine self-check이므로 독립 verification record는 만들지 않았다.

---

## Task 5 — 프로젝트 내비게이션 독립 검증 hardening 반영·커밋 준비

### Goals

- `docs/verifications/2026-07-16/frontend_project_navigation.md`의 PASS 판정과 hardening 4건을 1차 소스에서 확인한다.
- 계약 경계를 넓히지 않고 실제 회귀 가치가 있는 보강만 반영한다.
- 전체 프론트 검증과 문서 동기화를 마친 뒤 v1.6.96 슬라이스를 커밋 가능한 상태로 만든다.

### Completed work

- 독립 검증 기록의 boundary matrix 16행, 백엔드 endpoint/409 정합, 타입 재생성, 비차단 H1~H4 근거를 전부 읽었다. PASS(조건 없음) 판정과 백엔드 무변 결론은 타당하다.
- **H3 반영**: `DraftList.test.tsx` 공백-only 케이스가 disabled 버튼 확인에 그치지 않고 `fireEvent.submit(form)`으로 submit 경계를 직접 우회하도록 보강했다. 프로덕션의 `trimmed === ""` 가드를 독립적으로 잠근다.
- **H2 명확화**: `frontend-project-navigation-decisions.md`의 interaction thesis에서 이번 slice의 의무를 “생성 후 서버 목록 재조회”로 명확히 했다. 새 항목 강조는 실제 사용에서 재조회 후 위치 상실이 관측될 때만 추가한다.
- 검증 기록에 post-verification disposition을 추가해 H3 반영, H2 명확화, H1/H4 보류 이유를 원 독립 판정과 구분해 남겼다.

### Issues found

- H3의 기존 테스트는 버튼 disabled와 fetch 미증가를 확인했지만, `submit()` 내부 공백 가드만 제거하는 mutation에는 실패하지 않았다. UI 버튼 외의 submit 경계도 프로덕션이 방어하고 있으므로 테스트가 그 방어를 직접 pin해야 했다.
- H4를 CSS animation 때문에 route component에 `key`를 부여하면 단순 polish를 넘어 입력·조회 state 수명까지 바꾼다. 현재 계약과 사용자 문제 없이 적용할 변경이 아니다.

### Decisions

- **즉시 반영 = H3**, **문서 명확화 = H2**, **보류 = H1/H4**. H1은 editor slice의 404 UX와 함께, H4는 실제 route 전환 polish 문제가 관측될 때 다룬다.
- 새 항목 강조·route remount·전용 404를 검증 목록에 있다는 이유만으로 미리 구현하지 않는다. 현재 slice의 최소 계약과 되돌리기 쉬운 UI 원칙을 유지한다.

### Next steps

- v1.6.96 전체 변경과 독립 검증 기록을 한 커밋으로 묶는다.
- 다음 code slice는 HANDOFF의 editor/save 경계에서 새로 시작한다.

### Verification

- mutation: `DraftList.submit()`에서 `trimmed === ""`만 제거 → focused 회귀가 **1 failed / 8 passed**, `expected fetch 2, got 3`으로 정확히 bite. 가드 복원.
- 가드 복원 후 `cd frontend && npm test` → **22 passed / 3 files**.
- `npm run build` → PASS, 89 modules, CSS 4.53 kB(gzip 1.62), JS 234.46 kB(gzip 75.18).
- `npm run gen:api` → PASS, `schema.d.ts` diff 없음. backend 범위 diff 0, `git diff --check` clean.
