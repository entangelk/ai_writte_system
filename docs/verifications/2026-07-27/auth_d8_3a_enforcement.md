# 독립 검증 — 인증 D8-3a 시행 (SoT v1.7.52)

## Subject metadata

- **날짜**: 2026-07-27
- **요청자**: 오너 ("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?")
- **검증자**: 독립 검증 AI (구현 미관여)
- **대상 슬라이스**: D8-3a — 인증 dependency + 401 선언 + 두 겹 전수 가드
- **정준 계약 참조**:
  - `docs/system-contract-sot.md` v1.7.52 (changelog + 본문 4곳: 제품/프로젝트 경계, H3 표 401 행 추가, 503 선언 61→64 정정)
  - `docs/plans/auth-d8-3-enforcement-decisions.md` §E3(분할 방식=A)·§3(구현자 선결: 401/403, /health 무인증)
  - `docs/daily_logs/2026-07-27/work_log.md` D8-2 검증 반영 H-2 — "비-목표 가드는 역명제로 재작성(삭제 금지)" 계약
- **검증 대상 소스**: 작업 트리(미커밋). HEAD = `40b7fb8 feat(auth): add frontend session gate and close D8-4 verification`. 변경은 `services/application/app/main.py`·`tests/test_auth_api.py`·`tests/auth_support.py`(신규)·`frontend/src/api/schema.d.ts`·`docs/system-contract-sot.md`·HANDOFF·CHANGELOG·work_log.

## Scope

정준 계약을 먼저 읽어 D8-3a의 boundary matrix(아래)를 구축한 뒤, 각 셀을 구현·테스트·실동작에서 채웠다.

1. **정준 계약 자기일관** — v1.7.52 changelog ↔ 본문 ↔ 결정 브리프 §E3/§3 간 숫자·한정어·선언 일치.
2. **구현(main.py)** — `require_authenticated_user`/`_REQUIRE_AUTH` 단일 identity·공개 예외 4개 분류·`_protected()` 401 부여·POST /projects owner 재해석.
3. **operation 수 독립 재계산** — 앱 라우트 introspection으로 총/공개/보호/non-health를 재도출(65/4/61/64).
4. **boundary matrix(test_auth_api.py)** — 선언 가드·런타임 가드·over-strict 3종·비-목표 역명제·무 side-effect·만료 세션 arm 각 분기가 테스트에 매핑됐는지.
5. **실제 테스트 + mutation** — 백엔드 1629/4/873 재현, dependency 제거 mutation(두 가드 동시 발화), /health 401 선언 mutation(over-strict 발화).
6. **공개 계약·운영 부채** — gen:api 멱등(해시 비교), frontend tsc/217/14/build, smoke 스크립트 4종 401, 워커 Mongo 직결, argon2-cffi 핀, 미커밋 상태.

## Methodology

재현 가능한 정확 명령. 환경: WSL2, 레포 루트 = `/mnt/f/devel/ai_writte_system`.

```bash
# 0. 사전: argon2-cffi 확인(auth 모듈 수집에 필요)
python3 -c "import argon2"   # 23.1.0 설치됨

# 1. operation 수 독립 재계산 (APIRoute × method 순회)
PYTHONPATH=. python3 - <<'PY'
from fastapi.routing import APIRoute
from services.application.app.main import create_app, require_authenticated_user
app=create_app(); spec=app.openapi()
ops=[(r.path,m.lower()) for r in app.routes if isinstance(r,APIRoute) for m in sorted(r.methods)]
PUBLIC={("/health","get"),("/auth/login","post"),("/auth/logout","post"),("/auth/me","get")}
# 각 route의 route.dependencies 에 require_authenticated_user 가 있는지, PUBLIC 분류와 일치하는지 검사
# → guarded=61, open=4, mismatch=0, protected missing 401 decl=0, non-health declaring 503=64
PY

# 2. auth boundary 스위트 (override 없는 실제 앱)
PYTHONPATH=. python3 -m pytest tests/test_auth_api.py -q          # 25 passed, 200 subtests

# 3. 백엔드 전량
PYTHONPATH=. python3 -m pytest tests/ -q -p no:cacheprovider       # 1629 passed, 4 skipped, 873 subtests

# 4. mutation A — GET /projects 에서 dependencies=_REQUIRE_AUTH 만 제거(401 선언은 잔류)
cp services/application/app/main.py /tmp/main.py.bak
# (Edit: GET /projects 데코레이터에서 dependencies=_REQUIRE_AUTH 제거)
PYTHONPATH=. python3 -m pytest tests/test_auth_api.py::AuthenticationBoundaryTest -q
# → 선언 가드 + 런타임 가드 둘 다 GET /projects 에서 실패
cp /tmp/main.py.bak services/application/app/main.py              # 복원

# 5. mutation B — /health 에 responses={401: _ERROR} 추가
# (Edit: @app.get("/health", responses={401: _ERROR}))
PYTHONPATH=. python3 -m pytest \
  "tests/test_auth_api.py::AuthenticationBoundaryTest::test_no_public_operation_declares_401_it_cannot_return" -q
# → /health subtest 실패 ('401' unexpectedly found)
cp /tmp/main.py.bak services/application/app/main.py              # 복원, grep -c _REQUIRE_AUTH = 65 확인

# 6. 공개 계약 (frontend/)
cd frontend
npm run gen:api && sha256sum src/api/schema.d.ts openapi.json     # 826e4b2… / 43c8865…
npm run gen:api && sha256sum src/api/schema.d.ts openapi.json     # 동일 → 멱등
npx tsc --noEmit                                                  # exit 0
npm run test                                                      # 217 passed (14 files)
npm run build                                                     # entry 404.87 kB, observability lazy 385.71 kB

# 7. 운영 부채·미커밋 확인
git log --oneline -1                                              # 40b7fb8 (HEAD, D8-4)
git status --short services/application/app/main.py tests/test_auth_api.py tests/auth_support.py
grep -rn "test_no_non_auth_operation_is_protected_yet\|SliceBoundaryTest" tests/   # → NONE (역명제로 대체)
```

## Findings

### 1. 정준 계약 자기일관 — 일치

v1.7.52 changelog·본문 4곳·결정 브리프 §E3/§3 간 모순 없음.
- 숫자 정합: 총 **65 operation**(APIRoute×method), 공개 예외 **4**, 보호 **61**, non-health **64**. changelog "61개 operation"·503 선언 문장 "64개"·brief §1 "전체 65"가 모두 같은 체계의 다른 면(보호/선언/총)이며 충돌 아님.
- 본문 변경 4곳 모두 계약과 일치: ① 제품/프로젝트 경계 "인증 시행 섰다(v1.7.52) · 인가는 아직 없다" ② H3 표에 401 행 추가("살아 있는 세션이 없다 · handler에 닿지 않으므로 부수효과 없음 · 422보다 앞선다") ③ 503 선언 61→64 노화 정정(v1.7.51 /auth 3종 추가 반영) ④ `require_authenticated_user` 를 401 원인으로 명시.
- **사내 계약 모순(blocking) 0건**. brief 가 "재측정 시 숫자가 계약 문장에 박혀 있으면 endpoint가 늘 때마다 늙는다"고 한 노화 패턴을 이 슬라이스가 503 선언에 대해 스스로 정정한 것도 확인.

### 2. 구현(main.py) — 계약과 정확히 일치

- **단일 identity(계약 핵심)**: `require_authenticated_user`(`main.py:138`)·`current_user_or_none`(`:122`)·`_REQUIRE_AUTH = [Depends(require_authenticated_user)]`(`:1334`) 모두 **모듈 수준**. 종전 `_current_user` 클로저는 제거됐고, `app.state.users/sessions`를 통해 per-app 서비스에 접근. 단일 identity여야 전수 가드가 "이 route가 보호되는가"를 판정할 수 있다는 근거가 코드에 실려 있음.
- **공개 예외 4개**: `/health`(dependency 없음)·`POST /auth/login`(public)·`POST /auth/logout`(public, `_ERRORS_LOGOUT` 사용)·`GET /auth/me`(public이나 자기 본문에서 401). 각 사유가 코드 주석(`:2127-2176`)과 계약에 모두 기록됨.
- **401 선언 중앙화**: `_protected(declaration) = {401: _ERROR, **declaration}`(`:1247`)가 `_ERRORS_*` 공유 상수 전체에 401을 얹되, `_ERRORS_LOGOUT`(logout)과 `_ERRORS_401`(login·me, 이미 401 포함)은 별도 경로. logout 에 공유 상수 401이 번지는 것을 물리적으로 차단.
- **POST /projects owner 재해석 금지(계약)**: `current=Depends(require_authenticated_user)` 로 가드가 해석한 값을 파라미터로 받아 `owner_id=current.id`(`:2358`). 쿠키를 다시 읽지 않음 → `owner_id=None` 이 이 endpoint 로 만들어지는 경로가 제거됨. 종전 `_current_user(http_request)` 재읽기는 삭제.

### 3. operation 수 독립 재계산 — 작업자 주장과 정확히 일치

앱 자체 라우트를 순회해 독립 도출(스크립트 #1):
- TOTAL = **65** · GUARDED = **61** · OPEN = **4**(`/auth/login`·`/auth/logout`·`/auth/me`·`/health`)
- **declaration mismatch = 0**(모든 route의 dependency 유무가 PUBLIC 분류와 일치 — 배선 빠짐 0건)
- **protected missing 401 declaration = 0**(보호 61개 전부 OpenAPI 에 401 선언)
- non-health **64** 전부 503 선언
- 공개 예외 401 선언: login=True(자기 본문) · logout=False · me=True(자기 본문) · health=False(503도 False)
- `/docs`·`/openapi.json`·`/redoc` 은 APIRoute 가 아니라 가드 순회에 잡히지 않음(초기 우려 해소 — docs 가 닫힐 일 없음).

### 4. boundary matrix(test_auth_api.py) — 빈 셀 없음

`AuthenticationBoundaryTest` 가 비-목표 가드의 역명제로 재작성됐고, 구 이름 `SliceBoundaryTest`/`test_no_non_auth_operation_is_protected_yet` 은 **잔류 0건**(둘이 공존하는 모순 없음). 각 계약-required 분기가 named test 에 매핑됨:

| 계약 분기 | 방향 | 잠근 테스트 |
|---|---|---|
| 비-공개 op 는 dependency 선언 | should fire | `test_every_operation_is_either_protected_or_a_named_exemption`(route 객체 검사) |
| 비-공개 op 는 401 선언 | should fire | `test_every_protected_operation_declares_401` |
| 비-공개 op 는 세션 없이 401(본문 없이도, 422 아님) | should fire | `test_every_protected_operation_refuses_a_sessionless_request`(실제 호출 61개) |
| 유효 세션은 통과(전부 거부 아님) | over-strict | `test_a_logged_in_request_passes_the_guard` |
| /health·logout 은 낼 수 없는 401 미선언 | over-strict | `test_no_public_operation_declares_401_it_cannot_return` + `test_auth_endpoints_declare_401_and_the_storage_503` |
| /health 개방 | over-strict | `test_health_stays_open` |
| 401 시 부수효과 잔류 없음 | should fire | `test_anonymous_create_is_401_and_stores_nothing`(list_projects()==[] 까지) |
| 만료 세션 → 401 | should fire | `test_expired_session_is_401`·`test_expired_session_cannot_create` |
| 로그아웃 후 생성 → 401 | should fire | `test_create_after_logout_is_401` |
| owner 미노출(payload) | should fire | `test_owner_is_not_exposed_on_the_public_payload_yet` |
| 단일 identity(모듈 수준) | should fire | 구현 + 가드의 identity 비교(`require_authenticated_user in declared`) |

빈 셀 0건. over-strict 와 under-strict 양방향이 모두 named assertion 으로 존재.

### 5. mutation — 두 가드 모두 실제 발화 (적대 검증 핵심)

- **mutation A**(`GET /projects` 에서 `dependencies=_REQUIRE_AUTH` 만 제거, 401 선언은 `responses=` 에 잔류): 선언 가드(`test_every_operation_is_either_protected_or_a_named_exemption`)와 런타임 가드(`test_every_protected_operation_refuses_a_sessionless_request`)가 **동시에** GET /projects subtest 에서 실패. 핵심 성질 확인 — *"선언만 있고 배선이 빠진 drift 는 OpenAPI 만 봐서는 안 보이지만 route 객체 검사와 실제 호출이 각각 잡는다"*(관측 페이즈에서 실측된 "배선을 빠뜨려도 green"의 인가판이 여기서는 발화함).
- **mutation B**(`/health` 에 `responses={401: _ERROR}` 추가): over-strict 가드 `test_no_public_operation_declares_401_it_cannot_return` 가 /health subtest 에서 `'401' unexpectedly found` 로 실패. "낼 수 없는 401 을 선언하지 않는다" 잠금 확인.
- 복원 후 `grep -c "_REQUIRE_AUTH" main.py` = 65(정의 1 + route 61 + 주석 참조 3)로 원복 확인.

### 6. 백엔드 스위트 — 1629/4/873 정확 재현

`1629 passed, 4 skipped, 873 subtests passed`(70.9s). 작업자 주장과 정확히 일치. 도메인 스위트 19개 파일(`auth_support.py` 로 `app.dependency_overrides[require_authenticated_user]` 고정 사용자로 덮음)이 전부 green — override 가 route 의 dependency **선언을 제거하지 않는다**는 것도 확인(도메인 스위트가 선언 누락을 우연히 통과시키지 않음). **경계 자체는 `test_auth_api.py` 가 `auth_support` 미사용·override 없는 실제 앱으로 전수 검사** — 이것이 안전 성질의 하중 지점.

### 7. 공개 계약(frontend) — 정확 재현

- `gen:api` 멱등: 2회 연속 재생성이 동일 해시(schema.d.ts `826e4b2…`·openapi.json `43c8865…`), 작업자 보고값과 정확히 일치. 커밋된 schema.d.ts 가 현재 openapi.json 과 정합.
- `tsc --noEmit` exit 0(401 추가 schema.d.ts 가 프론트 코드와 정합).
- `vitest` **217 passed (14 files)**.
- build: 진입 **404.87 kB**·관측 lazy **385.71 kB**(작업자 보고값과 정확히 일치). 프론트 코드는 이 슬라이스에서 무변(D8-4 가 이미 로그인 게트를 세움).

### 8. 운영 부채·환경 — 전부 확인

- **smoke 스크립트 4종 401**(작업자 주장 확인): `phase2a_deployed_e2e_smoke.py:33`·`phase3a_deployed_rebuild_smoke.py:36`·`phase4_context_search_deployed_smoke.py:56`·`phase6_gate_finding_live_smoke.py:71` 이 `APPLICATION_BASE_URL` + `httpx.AsyncClient(trust_env=False)` 로 어떤 인증 헤더·쿠키도 없이 앱 HTTP API 를 침 → 이제 401. **HANDOFF:116 에 file:line 4개 + 사유로 추적됨**.
- **워커 무영향**: `scripts/index_sync_worker.py:85·261` 은 `MongoMemoryRepository.from_uri`·`MongoIndexSyncRepository.from_uri` 로 Mongo 직결. HTTP client(httpx/requests) 사용 0건. brief §1 실측 그대로 유효.
- **argon2-cffi 핀**: `services/application/requirements.txt:1` `argon2-cffi>=23,<24`(설치 23.1.0, 핀 범위 내). 작업자가 "requirements.txt" 라 한 것은 이 파일(정확)이며, 루트 requirements.txt 가 아님.
- **미커밋**: HEAD=`40b7fb8`(D8-4) 이고 D8-3a 변경은 전부 작업 트리. 작업자 "커밋하지 않았다" 주장 정확.

## Issues / Risks

### Blocking (계약 의무) — 없음

boundary matrix 의 빈 셀 0건, 정준 계약 자기일관, mutation 양방향 발화, 공개 계약 정합이 모두 확인됐다. 계약-required 분기 중 테스트에 매핑되지 않은 것이 없고, 계약이 요구하지 않는 것을 코드가 조용히 시행하는(spec-silent) 구간도 없다. `/auth/me` 의 "public 이나 자기 본문에서 401"·`owner_id=None` 의 "deny 는 D8-3b" 모두 SoT v1.7.52 에 명시돼 있다.

### Hardening recommendations (비차단, 계약 범위 초과)

1. **운영 smoke 스크립트 4종의 로그인 지원**(별도 증분): 현재 401. 작업자가 정당히 이 슬라이스 범위 밖(운영 도구)으로 미뤘고 HANDOFF:116 에 추적됨. 계약-required 가 아니므로 차단 아님.
2. **`auth_support.py` 의 "magic off switch" 오독 방지**: 작업자가 스스로 work_log 에서 짚고 docstring 으로 "dependency 를 제거하지 않는다"를 명시했음. 경계 자체는 `test_auth_api.py` 의 override 없는 앱으로 잠겨 있어 이미 완화됨. 추가 hardening 으로 `authenticate(app)` 가 sample route 의 `dependencies` 를 비우지 않음을 단언하는 회귀를 둘 수 있으나, 현재 설계로 실제 경계가 이미 독립적으로 잠겨 있어 필수는 아님.
   - **[검증 후 조치, 2026-07-27] 채택됨.** 작업자가 `tests/test_auth_api.py::TestSeamStaysAnOverrideTest` 로 두 성질을 회귀에 넣었다 — ① `authenticate(app)` 이 route 의 `dependencies` 를 건드리지 않고 `dependency_overrides` 에만 더한다 ② 이 모듈이 쓰는 앱은 `dependency_overrides` 가 비어 있다(경계가 실제 해석 경로로 검사됨). `authenticate` 가 route dependency 를 비우도록 하는 mutation 으로 ①이 실패함을 확인. 백엔드 스위트는 **1631 passed / 4 skipped / 873 subtests**(+2)로 갱신. **판정은 변하지 않는다**(합격, 조건 없음) — 이 항목은 계약-required 가 아니었고, 이제 문서가 아니라 회귀가 성질을 든다.
3. **argon2-cffi 설치는 머신-로컬 설정 단계**(코드 변경 아님): 핀은 `services/application/requirements.txt` 에 있고, 이 머신의 수집 실패는 이미 해소됨. 부채 아님.

## Verdict

**합격 (pass) — 조건 없음.**

정준 계약(v1.7.52 + 결정 브리프 §E3/§3 + D8-2 H-2 역명제 계약)이 구현·회귀·공개 계약·실동작 전 단계에서 일치한다. boundary matrix 에 빈 셀이 없고, mutation A·B 로 두 겹 전수 가드와 over-strict 가드가 모두 실제로 발화함을 입증했다. 작업자의 모든 정량 주장(65/4/61/64 operation, 백엔드 1629/4/873, 프론트 217/14, build 404.87/385.71 kB, gen:api 해시 826e4b2/43c8865)을 독립 재도출해 정확히 일치함을 확인했다. 인가(403·소유권)의 부재는 E3=A 슬라이스 경계상 정확히 D8-3b 로 남겨졌고, 외부 노출 금지가 유지됨이 계약·HANDOFF 모두에 명시돼 있다.

## Outstanding items

- ~~**미커밋 작업**~~: 오너가 검증 기록을 읽고 **커밋을 승인**했다(2026-07-27). Hardening #2 반영 후 커밋됨.
- **D8-3b(소유권 + `GET /projects` 저장소 경계 필터, `owner_id=None` 항상 deny)**: 다음 슬라이스. 인가가 들어오기 전까지 외부 노출 금지 유지.
- **운영 smoke 스크립트 4종 로그인 지원**: 별도 증분(HANDOFF:116 추적).

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system
PYTHONPATH=. python3 -m pytest tests/ -q -p no:cacheprovider        # 1629 passed, 4 skipped, 873 subtests
PYTHONPATH=. python3 -m pytest tests/test_auth_api.py -q            # 25 passed, 200 subtests
# operation 재계산 스크립트: 본 파일 Methodology #1
# mutation A/B: 본 파일 Methodology #4·#5 (cp 백업/복원 필수 — 미커밋 작업)
cd frontend && npm run gen:api && npx tsc --noEmit && npm run test && npm run build
```
