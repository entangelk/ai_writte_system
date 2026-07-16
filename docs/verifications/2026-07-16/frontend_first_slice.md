# 독립 검증 — Frontend 첫 슬라이스 (SoT v1.6.94)

## Subject metadata

- 날짜: 2026-07-16
- 요청자: 오너("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?")
- 검증자: 독립 검증 AI(Claude, 별도 세션 — 구현 미관여)
- 대상 슬라이스/산출물: Frontend 첫 슬라이스 — Product shell scaffold + 프로젝트 목록/생성(D1=A / D2=B / D3=A, 오너 범위 분할)
- 정본 계약 참조:
  - `docs/system-contract-sot.md` v1.6.94(행 + 서비스 경계 §~181-186 "frontend framework … React+TS+Vite", "타입 계약 동기화의 실제 범위")
  - `docs/plans/frontend-kickoff-decisions.md`(Resolved 브리프, D1/D2/D3 + "이번 결정에 포함하지 않는 것" 기본값)
- 검증 대상 작업 출처: **working tree, uncommitted**(커밋 미요청). git status: `M .dockerignore .gitignore CHANGELOG.md HANDOFF.md docker-compose.yml docs/plans/frontend-kickoff-decisions.md docs/system-contract-sot.md` + untracked `frontend/ services/frontend/ scripts/dump_openapi.py docs/daily_logs/2026-07-16/`. 백엔드 `services/application/**`·`tests/**`는 **무변경**(git 확인).

## Scope

1. **계약(정본) 스코프 읽기** — 브리프의 잠긴 결정(D1=A/D2=B/D3=A, 범위 분할, 기본값) + SoT v1.6.94 행/서비스경계절이 이 슬라이스에 실제로 무엇을 요구하는지, 그리고 자기 모순이 없는지.
2. **백엔드 계약 일치(핵심)** — 손으로 선언한 프론트 응답 타입이 실제 백엔드 `_project_payload`·`list_projects`·`CreateProjectRequest`와 literal 일치하는지.
3. **OpenAPI→TS 타입 갭 주장** — "생성 타입은 경로·요청 바디만 잠그고 응답은 무타입"이라는 작업자 주장이 생성물에서 기계적으로 참인지.
4. **구현 코드** — `frontend/` 전체(client.ts, ProjectList.tsx, nginx.conf, Dockerfile, vite.config.ts, tsconfig.json 등).
5. **회귀 테스트 감사** — 9개 테스트가 계약을 진으로 잠그는지(under-strict/over-strict 양방향), 부산물 assertion이 아닌지.
6. **정적/구성 검증** — `docker compose config --quiet`, `git diff --check`, 이미지/추적 파일/`.gitignore` 분리.
7. **독립 실행 재현** — 프론트 회귀·빌드·백엔드 풀스위트·schema 재생성 diff·**실 컨테이너 live 관통**(단일 origin/nginx prefix strip/SPA fallback/한글 왕복/음성 404).
8. **문서 일관성** — SoT·CHANGELOG·HANDOFF·브리프·work_log 상호 모순·stale 참조.

## Methodology

모든 주장을 1차 소스에서 재도출. 작업자의 work_log/HANDOFF 기술을 그대로 수용하지 않음.

```
# 1. 정본 계약 스코프
git diff docs/system-contract-sot.md CHANGELOG.md HANDOFF.md docs/plans/frontend-kickoff-decisions.md
# 2. 백엔드 계약 literal (정본↔코드 일치)
sed -n '880,881p;1182,1184p;1294,1301p' services/application/app/main.py
grep -n 'CORE_SOT_MONGO_URI' services/application/app/main.py
# 3. 응답 타입 갭 기계적 증거
grep -n 'list_projects_projects_get\|create_project_projects_post\|CreateProjectRequest' frontend/src/api/schema.d.ts
# 4. 구현·nginx·Dockerfile 읽기(전문)
# 5. 회귀 테스트 감사(9개 it() 전문 + under/over-strict 매핑)
grep -c '^  it(' frontend/src/projects/ProjectList.test.tsx
# 6. 정적/구성
docker compose config --quiet && echo OK ; git diff --check
git add -n frontend/ services/frontend/ scripts/dump_openapi.py   # 추적 대상 확인
git check-ignore frontend/node_modules frontend/dist frontend/openapi.json frontend/src/api/schema.d.ts frontend/package-lock.json
# 7. 독립 실행
cd frontend && npm test                       # 프론트 회귀
cd frontend && npm run build                  # tsc --noEmit && vite build
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider   # 백엔드(작업자와 동일 명령)
cd frontend && python3 ../scripts/dump_openapi.py > /tmp/o.json && npx openapi-typescript /tmp/o.json -o /tmp/s.d.ts && diff src/api/schema.d.ts /tmp/s.d.ts   # 재생성 diff
# 8. live 관통(격리 네트워크, application in-memory + frontend 컨테이너, trap 정리)
docker network create fsmoke-net
docker run -d --name fsmoke-app --network fsmoke-net --network-alias application ai_writte_system-application:latest
docker run -d --name fsmoke-fe  --network fsmoke-net -p 8013:80 ai_writte_system-frontend:latest
curl -s -w '\nHTTP %{http_code}\n' http://localhost:8013/                       # SPA index
curl -s -o /tmp/fb.html -w 'HTTP %{http_code}\n' http://localhost:8013/projects/anything   # SPA fallback
curl -s -w '\nHTTP %{http_code}\n' http://localhost:8013/api/projects           # prefix strip
curl -s -XPOST -H 'Content-Type: application/json' -d '{"name":"프록시 관통 확인"}' -w '\nHTTP %{http_code}\n' http://localhost:8013/api/projects
curl -s -w '\nHTTP %{http_code}\n' http://localhost:8013/api/health
curl -s -w '\nHTTP %{http_code}\n' http://localhost:8013/api/nonexistent        # 음성: app 404
docker rm -f fsmoke-app fsmoke-fe ; docker network rm fsmoke-net
```

## Findings

### 1. 백엔드 계약 일치 — 손선언 타입이 정확히 맞다 (핵심, PASS)

이 슬라이스의 가장 큰 위험은 "백엔드 payload가 손선언 타입과 어긋나는 것"이었다. 정확히 일치한다:

- `services/application/app/main.py:1182-1184` `_project_payload` → `{"id", "name", "archived"}`. 프론트 `frontend/src/api/client.ts:50-54` `Project { id: string; name: string; archived: boolean }`. **literal 1:1 일치**.
- `main.py:1299-1301` `list_projects` → `{"projects": [payload, ...]}`. 프론트 `client.ts:56-58` `listProjects(): Promise<{ projects: Project[] }>`. 일치.
- `main.py:1294-1297` `create_project` → `_project_payload`(단일 Project). 프론트 `client.ts:60-62` `createProject(): Promise<Project>`. 일치.
- `main.py:880-881` `CreateProjectRequest { name: str }`. 프론트 POST 바디 `{ name: trimmed }`(`ProjectList.tsx:32`) + 생성 타입 `client.ts:48` `components["schemas"]["CreateProjectRequest"]`. 일치.

live 관통(§7)에서 `POST /api/projects {"name":"프록시 관통 확인"}` → `{"id":"project-1","name":"프록시 관통 확인","archived":false}` 가 이 shape를 end-to-end로 확인.

### 2. 응답 타입 갭 주장 — 기계적으로 참 (PASS, 그리고 정당하게 상향됨)

작업자 주장("생성 타입은 경로·요청 바디만 잠그고 응답은 무타입")을 생성물에서 확인:

- `schema.d.ts` `list_projects_projects_get`·`create_project_projects_post` 의 200 응답 content는 `{ [key: string]: unknown }`(빈 object). 반면 create의 requestBody는 `components["schemas"]["CreateProjectRequest"]`로 정상 타입됨. → "요청 바디만 잠긴다" 정확.
- 근인도 확인: `main.py:1295,1300` 엔드포인트가 `-> dict[str, object]` 로 주석돼 있어 FastAPI가 응답 schema를 `additionalProperties: true` 로 내보낸다.

CLAUDE.md "Spec-silent-but-code-enforced is a contract gap" 규칙의 역방향 사례(계약이 타입 생성을 전제했으나 코드는 응답 타입을 주지 않음)인데, 작업자가 **조용히 손선언으로 넘기지 않고** SoT v1.6.94(서비스경계절 "타입 계약 동기화의 실제 범위")·브리프("v1.6.94 구현에서 드러난 실제 범위")·HANDOFF("Owner Decisions Needed: response_model")·work_log에 일관되게 기록하고 오너 결정으로 올렸다. 정본이 현실을 반영하도록 개정됐고, 잔여(response_model 도입 여부)는 오너 결정으로 올바르게 이월. **차단 아님**.

### 3. 단일 origin 실현 (D2=B 대가 상쇄) — 구성·live 양면 PASS

- `frontend/nginx.conf:12-15` `location /api/` + `proxy_pass http://application:8000/;`(trailing slash = prefix strip). `:28-30` `try_files $uri $uri/ /index.html;`(SPA fallback). `:23-24` `proxy_read_timeout/send_timeout 120s` > Writing loop wall-clock 60s(v1.6.89). CORS 미개방.
- `client.ts:5` `API_BASE = "/api"`(상수)가 단일 origin을 강제. `vite.config.ts:10-17` dev proxy도 `/api`→`rewrite` strip으로 같은 모양.
- live 관통(§7): SPA `/` 200 text/html(`<div id=root>` 확인) · fallback `/projects/anything` **200**(index.html, 404 아님) · `GET /api/projects` `{"projects":[]}`(prefix strip 동작) · POST 한글 왕복 · 재조회 1건 · `/api/health` `{"status":"ok"}`. **음성 검증 추가**: `/api/nonexistent` → FastAPI `{"detail":"Not Found"}` **404**. 이 404+detail 포맷은 application이 낸 것이지 nginx가 낸 것이 아니므로, `/api`가 application까지 진짜로 관통함을 증명(프록시 우회/단절이면 nginx 자체 404/502).

### 4. 회귀 테스트 감사 — 테스트 코드는 audit subject, 계약을 진으로 잠근다 (PASS)

`ProjectList.test.tsx` 9개 `it()`(grep 카운트 9 일치). boundary matrix(빈 셀 없음):

| 계약 분기 | 잠그는 테스트 | 양방향 |
|---|---|---|
| 목록 렌더 + archived `(보관됨)` 표시 | "lists projects returned by GET /projects" | under |
| 단일 origin — `fetch` 첫 인자 exact `/api/projects` | "calls the single-origin /api path…" (calls[0][0]) + POST 경로는 "posts a new project…" (calls[1][0]) | over(절대 URL로 바꾸면 fail) |
| 빈 상태(목록 미렌더) | "shows an empty state…" | under |
| POST 후 **서버 재조회**(낙관적 패치 금지) | "posts a new project and reloads the list" — `toHaveBeenCalledTimes(3)` 가 재조회를 잠금 | under |
| trim 후 전송 | "trims the name before posting…" | under + over(과교정 방지) |
| 공백-only **미전송**(button disabled + fetch 1회) | "does not post a whitespace-only name" | over |
| list/create 실패 시 `status: detail` 노출 | "surfaces the API error detail…"(list·create 각) | under |
| 실패 시 입력 보존 | "…keeps the input" | over |
| 성공 시 이전 오류 해제 | "clears a previous error…" | over |

- 부산물 assertion 아님: `toBe("/api/projects")`(경로 literal), `toHaveBeenCalledTimes(3)`(재조회 의미), `toEqual({name})`(바디), `toHaveTextContent("409: project is archived")`(detail 포맷) 등 전부 공개 표면을 잠금.
- over-strict 검증: 작업자 주장("절대 URL로 바꾸면 조용히 CORS 필요 → 대신 테스트가 터진다")을 확인. `API_BASE`를 절대 URL로 바꾸면 calls[0][0] ≠ "/api/projects" 로 test 2가 fail.

### 5. 독립 실행 — 작업자 수치 전부 재현 (PASS)

| 항목 | 작업자 주장 | 독립 재현 |
|---|---|---|
| 프론트 회귀 | 9 passed | **9 passed** |
| 프론트 빌드 | tsc+vite build, 31 modules, ~195kB/gzip ~62kB | **31 modules, 195.14 kB / gzip 61.64 kB** |
| 백엔드 | 1099 passed / 45 skipped / 260 subtests | **1099 passed / 45 skipped / 260 subtests (58.09s)** |
| compose config | --quiet 통과 | **CONFIG OK** |
| build frontend | 성공 | 이미지 존재(48.4 MB)·live 관통으로 검증 |
| git diff --check | clean | **CLEAN** |

추가로 **schema 재생성 diff**: `dump_openapi.py`→`openapi-typescript` 로 재생성한 타입이 커밋(예정) `schema.d.ts`와 **IDENTICAL**. 즉 커밋된 생성물이 현재 백엔드 기준 최신이며, `dump_openapi.py`가 in-memory 기본 collaborator로 정상 동작함(연결 부작용 없음 — 재생성 시 Mongo/Gateway/ES 무구동으로 성공).

### 6. 백엔드 무변경 — 독립 확인 (PASS)

git status에 `services/application/**`·`tests/**` 0건. `scripts/dump_openapi.py`는 `create_app().openapi()` 덤프만 하고 파일·상태 쓰기 0(read-only). 백엔드 풀스위트 1099/45/260 green. "백엔드·계약·회귀 무변" 목표 달성.

### 7. 정적/구성/추적 — PASS

- `git add -n`: 추적 대상이 정확히 `index.html·nginx.conf·package-lock.json·package.json·src/**·tsconfig.json·vite.config.ts·vitest.setup.ts` + `schema.d.ts`. `git check-ignore`로 `node_modules·dist·openapi.json`은 ignore, `schema.d.ts·package-lock.json`은 **추적** 확인(`.gitignore` 주석 의도와 일치).
- Dockerfile 2-stage(node:22-slim build → nginx:1.27-alpine)에서 `npm ci`가 소스 COPY보다 선행(캐시 보존). build stage에 Python 없음 → "schema.d.ts 커밋 불가피" 주장 타당.
- 잔여 스모크 컨테이너/네트워크 0건(작업자 정리 + 본 검증 trap 정리 모두 확인).

### 8. 문서 일관성·자기 모순 점검 — PASS(사소한 stale 2건, 아래 Hardening)

SoT v1.6.94 행·CHANGELOG·HANDOFF(Current Status/Owner Decisions Needed/Next Tasks/Verification/Project Structure)·브리프 상태·work_log가 D1=A/D2=B/D3=A·범위 분할·Vitest+RTL·응답 타입 갭·1099/45(ES 설치)/1096/48(미설치) 구분·live 관통 결과에서 **상호 모순 없음**. 특히 "1099/45 = 착수 전 기준선과 동일"은 백엔드 무변경 사실과 정합(이 머신은 ES 설치 환경 → 기준선이 1099/45). Project Structure의 stale v1.6.91 → v1.6.94 정정도 확인.

## Issues / Risks

### Blocking (계약 의무)

**없음.** 경계 매트릭스에 빈 셀이 없고(9 행동 분기 + 계약 의무 전부 named 증거/테스트), 정본↔코드 literal이 일치하며, 정본 자기 모순이 없고, 응답 타입 갭은 정당하게 상향됐다(조용히 숨기지 않음).

### Hardening recommendations (비차단, 계약이 요구하지 않는 보강)

- **H1 — 응답 타입 갭(response_model)은 이미 오너 결정으로 이월됨**: 본 검증은 작업자의 "에디터 슬라이스 전에 정하는 게 가장 싸다" 권고가 타당함을 확인(화면 증가 → 손선언 표면 증가). 새 발견이 아니라 추천 강화. 의사결정 시 H2와 함께 처리하면 자연스럽다.
- **H2 — 프론트 공백 가드는 spec-silent, 백엔드 검증 무입력**: `core_sot/service.py` `create_project(name)`은 `Project(id=…, name=name)` 직접 생성으로 **빈/공백 이름 검증이 없다**. 프론트 `ProjectList.tsx:26-27`의 trim+거부는 프론트 전용 UX 동작이며 계약이 요구한 것이 아니다. 우회(다른 클라이언트·공백을 안 trim 하는 미래 화면) 시 백엔드가 빈 이름 project를 mint 한다. 현재 슬라이스에 영향 없음(프론트가 막음). 에디터 슬라이스(입력增多)에서 "입력 검증을 프론트 전용으로 둘지 백엔드 Field 로 잡을지"를 H1(response_model)과 묶어 정하면 좋다.
- **H3 — 브리프 "관련 정본" 줄이 여전히 SoT v1.6.92**: `frontend-kickoff-decisions.md:5`가 v1.6.92 를 가리키나 정본은 v1.6.94. 상태 줄은 갱신했으나 이 포인터는 미갱신. 사소한 doc 정정.
- **H4 — compose frontend 주석 "SoT v1.6.93"**: `docker-compose.yml` frontend 서비스 주석이 v1.6.93 표기(D1/D2 가 v1.6.93 kickoff에서 잠긴 것은 사실이나 구현된 슬라이스는 v1.6.94). 방어 가능한 표기이나 정확히는 v1.6.94. 사소.
- **H5 — schema.d.ts 경로 타입이 생성됐으나 아직 call-site에서 미소비**: `client.ts`가 `CreateProjectRequest`만 import. 경로 수준 타입 체크는 타입 정의엔 존재하나 호출부에 연결되지 않아 "경로를 잠근다"가 call-site에서는 미검증. 엔드포인트 배선이 늘면 자연 소비됨. 결함 아님.
- **H6 — 이중 제출(double-submit) 회귀 미작성**: `ProjectList.tsx:27,30` 의 `saving` 가드가 동시 제출을 막지만 이에 대한 명시 회귀가 없다. 에디터 슬라이스(저장 의미론 더 민감)에서 추가 후보.

## Verdict

**합격(PASS, 조건 없음).**

이유(합격을 떠받치는 사실):
1. 손선언 응답 타입이 백엔드 `_project_payload`/`list_projects`/`CreateProjectRequest` 와 literal 1:1 일치(§1).
2. D2=B 단일 origin 대가 상쇄가 nginx 구성 + live 관통(음성 404 포함)으로 입증됐다(§3, §7).
3. 회귀 9개가 계약을 양방향으로 잠그고 부산물이 없다; 경계 매트릭스 빈 셀 없음(§4).
4. 작업자의 모든 정량 주장(9 passed / 빌드 수치 / 1099·45·260 / compose / diff --check / schema 재생성 동일)을 독립 재현했다(§5).
5. 백엔드 무변경(git + green suite) 확인(§6).
6. 유일한 계약 갭(응답 타입)을 조용히 넘기지 않고 정본 개정 + 오너 결정 상향으로 처리했다(§2) — CLAUDE.md 가 요구하는 정확한 처리.

Hardening 6건은 전부 비차단(현재 계약이 요구하지 않는 보강 또는 사소한 doc 정정). 그 중 H1(응답 타입)·H2(입력 검증)는 에디터 슬라이스 전 오너 결정으로 묶어 처리하면 가장 효율적이다.

## Outstanding items

- **작업물은 working tree에 uncommitted**(커밋 미요청). 추적 파일 목록은 §7에 확정됨.
- **오너 결정 대기(기존)**: 백엔드 `response_model` 도입 여부 — 안 하면 응답 타입 계속 손선언(컴파일 타임 미검출). 에디터 슬라이스 전이 비용 최소(H1/H2).
- **다음 슬라이스(★)**: 원고 목록 → 에디터. 여기서 `idempotency_key` 계약·archive 409·프로젝트 상세 라우팅이 처음 붙는다(HANDOFF Next Tasks).

## Reproduction

```
# 정본 계약 스코프
git diff docs/system-contract-sot.md docs/plans/frontend-kickoff-decisions.md
# 백엔드 계약 literal
sed -n '880,881p;1182,1184p;1294,1301p' services/application/app/main.py
grep -n 'list_projects_projects_get\|create_project_projects_post' frontend/src/api/schema.d.ts

# 프론트 회귀·빌드
cd frontend && npm test && npm run build

# 백엔드(ES 설치 환경 → 1099/45 기대; 미설치 → 1096/48)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider

# schema 재생성 동일성
cd frontend && python3 ../scripts/dump_openapi.py > /tmp/o.json \
  && npx openapi-typescript /tmp/o.json -o /tmp/s.d.ts \
  && diff src/api/schema.d.ts /tmp/s.d.ts   # 빈 출력 = identical

# 정적/구성
docker compose config --quiet ; git diff --check

# live 관통(격리 네트워크, trap 정리 필수)
docker network create fsmoke-net
docker run -d --name fsmoke-app --network fsmoke-net --network-alias application ai_writte_system-application:latest
docker run -d --name fsmoke-fe  --network fsmoke-net -p 8013:80 ai_writte_system-frontend:latest
# app /health 가 뜰 때까지 대기 후:
curl -s -w '\n%{http_code}\n' http://localhost:8013/                            # 200 SPA
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8013/projects/anything # 200 fallback
curl -s -w '\n%{http_code}\n' http://localhost:8013/api/projects               # {"projects":[]}
curl -s -XPOST -H 'Content-Type: application/json' -d '{"name":"프록시 관통 확인"}' -w '\n%{http_code}\n' http://localhost:8013/api/projects
curl -s -w '\n%{http_code}\n' http://localhost:8013/api/health                 # {"status":"ok"}
curl -s -w '\n%{http_code}\n' http://localhost:8013/api/nonexistent            # {"detail":"Not Found"} 404
docker rm -f fsmoke-app fsmoke-fe ; docker network rm fsmoke-net
```
