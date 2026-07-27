# D8-4 프론트 로그인 선행 독립 검증

## Subject metadata

- 날짜: 2026-07-27
- 요청자: 오너
- 검증자: Codex
- 대상: E1~E4 결정 반영 및 E4=A에 따른 D8-4 프론트 로그인/세션 경계
- 정본 계약: `docs/system-contract-sot.md` v1.7.51, 특히 문서 우선순위
  (§문서 우선순위)와 v1.7.51 변경 이력, §제품과 프로젝트 경계
- 세부 계약: `docs/plans/multi-user-auth-cms-decisions.md` D8,
  `docs/plans/auth-d8-3-enforcement-decisions.md` E1~E4
- 검증 대상 출처: working tree, uncommitted; 기준 HEAD
  `eff37d1 docs(plans): D8-3 인가 시행 결정 브리프 + 비-목표 가드를 403까지 확장 (D8-2 검증 합격 반영)`

## Scope

1. E1~E4 결정이 SoT·두 브리프·현재 상태 문서에서 서로 모순 없이 고정됐는지
2. `/auth/me` 선확인, 미인증/만료 전환, 현재 route 보존, 로그인 오류/비밀번호 처리,
   서버 로그아웃 선행이라는 D8-4 계약
3. 모든 프론트 API 요청의 same-origin cookie 전송 경계와 보호 API 401 전역 처리
4. 공통 `request()`를 우회하는 partial-envelope 두 경로의 인증 경계 수렴
5. 신규 회귀가 계약의 under-strict/over-strict 양방향을 실제로 잠그는지
6. 프론트 전체 회귀, 타입 검사·프로덕션 빌드, OpenAPI 생성물 무변, 배포 상태와 실제 렌더

백엔드 인가 D8-3a~3c, E1~E3의 후속 구현, 관리자/영구 삭제/인프라 인증은 이번
구현 및 검증 범위 밖이다.

## Methodology

계약부터 읽고 아래 경계 행렬을 만든 뒤 구현과 테스트를 역추적했다. 작업 AI의 작업 로그와
CHANGELOG 수치는 근거로 쓰지 않고 직접 재실행했다.

```bash
git status --short
git log -1 --oneline
rg -n "E1|E2|E3|E4|D8-4|v1\.7\.51" \
  docs/system-contract-sot.md docs/plans HANDOFF.md CHANGELOG.md
rg -n "\bfetch\s*\(" frontend/src --glob '!**/*.test.*' --glob '!api/client.ts'
git diff --check

cd frontend
npm test -- --reporter=verbose
npm test -- src/App.test.tsx --reporter=verbose
npm run build
sha256sum openapi.json src/api/schema.d.ts
npm run gen:api
sha256sum openapi.json src/api/schema.d.ts
git diff --exit-code -- openapi.json src/api/schema.d.ts

cd ..
docker compose ps --format json
curl -sS -D - -o /dev/null http://127.0.0.1:5520/api/auth/me
chromium --headless --no-sandbox --disable-gpu --hide-scrollbars \
  --virtual-time-budget=1500 --window-size=1440,1000 \
  --screenshot=d8-login-desktop.png http://127.0.0.1:5520/
chromium --headless --no-sandbox --disable-gpu --hide-scrollbars \
  --virtual-time-budget=1500 --window-size=390,844 \
  --screenshot=d8-login-mobile.png http://127.0.0.1:5520/
```

스크린샷은 육안 확인 뒤 삭제했다. 보조 확인으로 `python3 -m pytest tests/test_auth_api.py -q`를
시작했으나 이 실행 환경에서 출력 없이 장시간 종료되지 않아 중단했다. D8-4가 백엔드 코드를
바꾸지 않았고 본 판정은 이 미완료 실행에 의존하지 않는다.

## Contract boundary matrix

| 계약 경계 | 구현 | 명명 회귀 | 결과 |
|---|---|---|---|
| `/auth/me` 완료 전 보호 route 미렌더 | `AuthGate.tsx:21-47,67-72` | `App.test.tsx:134-146` | LOCKED |
| 유효 세션은 직접 route를 그대로 렌더 | `AuthGate.tsx:23-26,106-128` | `App.test.tsx:63-114` | LOCKED |
| 미인증은 로그인, 비-401 확인 장애는 재시도 | `AuthGate.tsx:27-34,75-103` | `App.test.tsx:148-190,290-312` | LOCKED |
| 로그인 중 현재 route 유지, 성공 후 복귀 | `AuthGate.tsx:93-103,162-168` | `App.test.tsx:148-190` | LOCKED |
| 401 로그인 실패는 단일 문구, 비밀번호 초기화 | `AuthGate.tsx:169-175` | `App.test.tsx:192-213` | LOCKED |
| 일반 보호 요청 401은 만료 로그인 표면으로 전환 | `client.ts:45-51`, `AuthGate.tsx:37-43` | `App.test.tsx:215-230` | LOCKED |
| partial `accept` 401도 같은 전환 | `client.ts:380-388` | `App.test.tsx:232-265` | LOCKED |
| partial `revise-and-gate` 401도 같은 전환 | `client.ts:335-346` | `App.test.tsx:267-301` | **LOCKED (closure)** |
| 로그아웃 응답 전에는 보호 UI 유지 | `AuthGate.tsx:49-65` | `App.test.tsx:303-331` | **LOCKED (closure)** |
| 로그아웃 실패면 인증 상태 유지·오류 표면 | `AuthGate.tsx:60-64,121-125` | `App.test.tsx:333-354` | **LOCKED (closure)** |
| 모든 API가 same-origin cookie 경계 사용 | `client.ts:28-52`; 생산 직접 `fetch`는 여기 1곳 | `App.test.tsx:44-61,148-190,356-377` | **LOCKED (closure)** |

## Findings

### 1. 계약과 문서 스택

SoT가 Approved v1.7.51이고 문서 우선순위가 명시돼 있다
(`docs/system-contract-sot.md:3-20`). E1~E4=A와 D8-4 선행, 로그인/세션 계약은
SoT 변경 이력에 고정돼 있다(`docs/system-contract-sot.md:36`). 두 브리프도
`owner_id=None` always-deny, project 소유권/비-project 인증, 3-a→3-b→3-c,
D8-4→D8-3 순서로 같은 결정을 적는다
(`docs/plans/auth-d8-3-enforcement-decisions.md:28-32,34-93`;
`docs/plans/multi-user-auth-cms-decisions.md:52-63,201-211`). 내부 모순은 찾지 못했다.

E1~E3 구현을 이번 슬라이스가 선점하지 않았고, SoT도 `/auth/*` 외 백엔드 인가는 아직 없다고
명시한다(`docs/system-contract-sot.md:252-255`). 이는 E4=A의 의도와 맞는다.

### 2. 구현

`AuthGate`는 세션 확인이 끝날 때까지 자식 route를 mount하지 않고, 401/비-401을 각각
anonymous/error로 분리한다(`frontend/src/auth/AuthGate.tsx:21-47,67-103`). 현재 route를
변경하는 navigate가 없어 로그인 성공 뒤 원래 route가 그대로 mount된다. 로그인 401은 서버 detail을
노출하지 않고 단일 문구를 사용하며 성공/실패 양쪽에서 password state를 비운다
(`frontend/src/auth/AuthGate.tsx:154-178`).

로그아웃 구현 자체는 `await logout()` 뒤에만 user/state를 버리고, 실패하면 인증 상태를 유지한다
(`frontend/src/auth/AuthGate.tsx:49-65`). 구현은 정본과 일치하지만 아래 테스트 결손 때문에 이
순서가 회귀로 잠기지는 않았다.

모든 생산 API 전송은 `fetchApi` 한 곳의 `fetch`를 통과하고 `credentials: "same-origin"`을
명시한다(`frontend/src/api/client.ts:28-52`). repo-wide 생산 코드 검색에서도 이 한 곳 외 직접
`fetch`는 0건이었다. partial 두 경로도 공통 전송 경계를 호출하면서 각자의 partial envelope 해석은
보존한다(`frontend/src/api/client.ts:335-367,380-405`).

### 3. 회귀 테스트

신규 테스트는 세션 확인 전 보호 route 차단, 유효 세션의 직접 route 허용, 로그인 복귀,
단일 실패 문구/비밀번호 초기화, 일반 401, `accept` partial 401, 세션 확인 장애를 검사한다
(`frontend/src/App.test.tsx:134-265,290-312`). 이 부분은 assertion이 공개 UI/API 표면을
직접 단정한다.

그러나 전체 실행은 **1 failed / 213 passed / 14 files**였다. 실패한
`renders the project index at the root route`는 프로젝트 heading이 보인 직후 effect의
`GET /projects`가 기록되기 전에 호출 수 2를 즉시 단정한다
(`frontend/src/App.test.tsx:44-60`). 관측은 1회(`/auth/me`)였다. 같은 파일만 재실행하면
11/11 통과해 안정 구현 실패가 아니라 flaky wait 결손임을 재현했다. 따라서 작업 AI의
“프론트 전체 214 passed”는 이번 독립 실행에서 재현되지 않았다.

또한 로그아웃 성공 테스트는 resolve된 응답만 사용한다
(`frontend/src/App.test.tsx:267-288`). 로컬 상태를 `await logout()` 전에 버리는 mutation도
이 테스트를 통과하며, 실패 응답 시 인증 상태/오류 표면을 확인하는 테스트도 없다.
`revise-and-gate` partial 경로는 코드상 공통 경계를 사용하지만 그 호출부만 직접 `fetch`로
되돌리는 mutation을 현재 `accept` 테스트가 잡지 못한다.

### 4. 타입·생성 계약·빌드

- `npm run build`: 성공. `tsc --noEmit` 통과, Vite 694 modules.
- 산출물: entry **404.87 kB**, `ObservabilityDashboard` **385.71 kB**.
- `npm run gen:api` 전후 SHA-256:
  - `openapi.json`: `fcb090d723d75ecd4c0e08708df9b347141ac5e18dc3555e7c1aa4d74a1077c0`
  - `src/api/schema.d.ts`: `c5bf248c138425110d143981e8bb56400e882a73c10811eac1fb631ded648c13`
- 두 hash는 전후 동일하고 `git diff --exit-code`도 0이었다. 공개 OpenAPI 생성물 변경 없음.
- `git diff --check`: 통과.

### 5. 배포·실렌더

`docker compose ps --format json`에서 healthcheck가 있는 7개 서비스
(`application`, `gateway`, `mongo`, `elasticsearch`, `embedding`, `chroma`, `frontend`)가
모두 healthy였다. healthcheck가 없는 `worker`, `generation_worker`는 running이다.
배포 프론트 프록시의 쿠키 없는 `/api/auth/me`는 실제 **401 Unauthorized**를 반환했다.

미인증 로그인 화면을 1440×1000과 390×844로 독립 캡처해 확인했다. 두 viewport 모두
아이디/비밀번호 입력과 CTA가 화면 안에 있고 가로 overflow나 잘림을 발견하지 못했다.

## Issues / Risks

### Blocking (contract obligations)

1. **B1 — RESOLVED.** 전체 프론트 회귀가 flaky하여 214/14 green 주장을 재현하지 못함.
   `frontend/src/App.test.tsx:56-60`이 `GET /projects` effect 완료를 기다리지 않는다.
   `App.test.tsx:57`이 `waitFor`로 호출 수 2를 기다리도록 고쳤고 전체 **217/14 green**을
   재현했다.
2. **B2 — RESOLVED.** 서버 로그아웃 선행 계약의 양방향 회귀가 비어 있음.
   pending logout 동안 보호 UI가 유지되는 under-strict guard와, logout 실패 시 인증 상태를
   유지하고 오류를 보이는 over-strict guard를 각각 `App.test.tsx:303-354`에 추가했다.
3. **B3 — RESOLVED.** 두 partial-envelope 경로 중 `revise-and-gate`의 401 경계 회귀가 비어 있음.
   `reviseAndGateWriting` 호출부를 직접 통과해 401→만료 로그인 전환을 단정하는 회귀를
   `App.test.tsx:267-301`에 추가했다.

### Hardening recommendations (non-blocking)

- 로그인 성공 시 password state는 코드에서 비워지고 화면이 unmount되므로 실제 DOM에서 별도
  관측하기 어렵다. 향후 로그인 form state가 route와 분리돼 유지되는 구조로 바뀐다면 성공 방향의
  password 초기화 회귀를 추가하는 것이 좋다.

## Verdict

**합격 (2026-07-27 closure).**

초기 판정은 계약-required regression matrix의 빈 셀 B1~B3 때문에 조건부 합격이었다.
오너가 보강을 지시한 뒤 세 조건을 모두 회귀로 잠갔고, 집중 **14/14**와 전체
**217 passed / 14 files**를 재현했다. 타입 검사·프로덕션 빌드가 다시 통과했고 OpenAPI 생성물
SHA-256도 전후 동일하다. 따라서 빈 셀은 0개이며 D8-4는 검증 완료로 닫는다.

## Outstanding items

- D8-4 구현·B1~B3 closure·이 검증 기록은 같은 커밋으로 게시한다.
- 백엔드 인가는 아직 시행 전이므로 외부 노출 금지 상태는 유지된다.

## Closure reproduction (2026-07-27)

```bash
cd frontend
./node_modules/.bin/vitest run src/App.test.tsx \
  --reporter=verbose --pool=forks --maxWorkers=1
# 14 passed / 1 file

npm test -- --reporter=dot --pool=forks --maxWorkers=4
# 217 passed / 14 files

npm run build
# entry 404.87 kB / ObservabilityDashboard 385.71 kB

sha256sum openapi.json src/api/schema.d.ts
npm run gen:api
sha256sum openapi.json src/api/schema.d.ts
git diff --exit-code -- openapi.json src/api/schema.d.ts
# hashes unchanged:
# openapi.json fcb090d723d75ecd4c0e08708df9b347141ac5e18dc3555e7c1aa4d74a1077c0
# schema.d.ts c5bf248c138425110d143981e8bb56400e882a73c10811eac1fb631ded648c13
```

첫 전체 재실행은 verbose 출력 상태에서 환경 실행 한도에 걸려 종료 코드 143으로 중단됐으며
테스트 실패 출력은 없었다. 출력량을 줄이고 worker 4개로 같은 14파일 전체를 재실행해
217/217 green을 확인했다. 판정은 완료된 두 번째 실행에만 의존한다.

## Reproduction

```bash
cd frontend
npm test -- src/App.test.tsx --reporter=verbose
npm test -- --reporter=verbose
npm run build
npm run gen:api
git diff --exit-code -- openapi.json src/api/schema.d.ts

cd ..
git diff --check
docker compose ps --format json
curl -sS -D - -o /dev/null http://127.0.0.1:5520/api/auth/me
```
