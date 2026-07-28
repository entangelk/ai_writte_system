# 독립 검증 — 인증 D8-5a 관리자 경계 + 사용자 관리 (SoT v1.7.56)

## Subject metadata

- **날짜**: 2026-07-28
- **요청자**: 오너 ("다음작업 검증해줘. D8-5a 완료·커밋했습니다 (fb88754, 13 files).")
- **검증자**: 독립 검증 AI (구현 미관여 — 본 검증자는 코드·테스트를 한 줄도 쓰지 않았다)
- **대상 슬라이스**: D8-5a — `require_admin_user` 경계(3번째 인가 tier) + `/admin/users` 사용자 관리(목록·생성·비활성화). D6=A(최소 관리자)의 첫 하위 슬라이스.
- **정준 계약 참조**:
  - `docs/system-contract-sot.md` v1.7.56 변경이력 + §H3 상태코드 표(401·403 행) + §"제품과 프로젝트 경계"
  - `plans/auth-d8-5-admin-decisions.md` §2(F1=C·F2=A) · §3(구현자 선결) · §7(C-1~C-5, 5-b/5-d 선행 결정)
  - `plans/multi-user-auth-cms-decisions.md` §D6 · §D2(서버 세션 = JWT 각하 이유)
- **검증 대상 소스**: **커밋 `fb88754`**(HEAD, 작업 트리 깨끗함). D8-3c(3b99c80) 위에 적층. 13개 파일(코드 3 · 테스트 4 · 생성물 1 · 문서 5). 검증 종료 시 `git status` 무변, `git rev-parse HEAD = fb88754`.

## Scope

정준 계약이 이 슬라이스에 요구하는 표면만 감사한다(코드를 열기 전 계약 읽기 범위를 먼저 정한다).

1. **경계 tier** — `require_admin_user`가 `/admin/*` 3개 operation을 지키며 인증된 비관리자는 **403**(401·404가 아님)인가. 두 겹 배선(inner sub-dep + route-level)인가.
2. **결합 불변식 확장** — (a) 403 생산자가 소유권·관리자 **정확히 둘**, (b) 두 인가 dependency는 **대안이지 스택이 아님**(같은 route에 둘 다 없다), (c) tier 분할 `68 = public 4 + 인증 전용 2 + 관리자 3 + project 59`, (d) `/admin/*`는 project-scoped가 아님.
3. **사용자 관리 동작** — 목록(해시 미포함) · 생성(중복 409·빈 입력 400) · 비활성화(미존재 404·마지막 관리자 409).
4. **세션 즉시 무효화** — 비활성화가 살아 있는 세션을 즉시 죽이는가(D2 성질).
5. **F2=A population 불변식** — 마지막 활성 관리자 보호가 호출자가 아니라 활성 관리자 population에 대한 것인가(비활성 관리자는 생존자로 안 침, 재호출 멱등).
6. **공개 계약** — `schema.d.ts`에 3개 operation additive, `AdminUserPayload`에 `password_hash` 없음.
7. **계약 자기일관** — v1.7.56 ↔ §H3(401·403 행) ↔ 브리프 F1=C·F2=A.
8. **정량 재실행** — `53/707`, `1681/1/1455`, 프론트 `tsc`·`217`.

## Methodology

커밋된 코드를 1차 소스에서 재도출. mutation은 main.py/users.py(이미 커밋됨)를 패치 → 해당 셀 회귀 → `git checkout` 복원 → `git status` 무변 확인.

```bash
# 0. 인프라 — test-mongo(rs-test, 27020) ON
docker compose -f docker-compose.test.yml up -d   # 이미 기동 중

# 1. 초점 스위트
PYTHONPATH=. python3 -m pytest tests/test_auth_api.py -q
PYTHONPATH=. python3 -m pytest tests/test_auth_api.py tests/test_auth_users.py tests/test_auth_users_mongo.py -q

# 2. OpenAPI 독립 도출
PYTHONPATH=. python3 -c "from services.application.app.main import create_app; s=create_app().openapi(); ..."   # /admin/* 3개 + 응답 코드 집합

# 3. mutation 5종(N5·N5c·admin inner·last-admin·session-kill)
#    각: Edit → pytest 해당 셀 → git checkout -- <file> → git status 확인

# 4. 전량(test-mongo ON)
PYTHONPATH=. python3 -m pytest tests/ -q -p no:cacheprovider

# 5. 프론트
cd frontend && npm run gen:api && git diff --stat src/api/schema.d.ts   # 무차이 = 동기
npx tsc --noEmit ; npm test
```

## Findings

### 1. 경계 tier — 두 겹 배선 정확, 비관리자 403

[`main.py:1383-1392`](../../../services/application/app/main.py#L1383) `require_admin_user(current=Depends(require_authenticated_user))` — inner 인증 sub-dep 보유(소유권과 동일 구조). [`main.py:1402-1405`](../../../services/application/app/main.py#L1402) `_REQUIRE_ADMIN=[require_authenticated_user, require_admin_user]` — route-level 두 겹. 비관리자 → `{"detail":"forbidden"}` 403(세션은 살아 있어 401이 아님, 존재 은닉 404도 아님). §H3 403 행(생산자 ① 소유권 ② 관리자)과 일치.

### 2. 결합 불변식 — 올바른 **강화**(약화 아님)

[`CombinedBoundaryMatrixTest`](../../../tests/test_auth_api.py#L668)가 admin tier를 제대로 편입:
- `_tiers()` 분류 순서 `project → admin → auth → public`([`test_auth_api.py:691`](../../../tests/test_auth_api.py#L691))로 admin op가 auth tier로 잘못 떨어지지 않음.
- 분할 단정 `by_tier["admin"]==ADMIN(3)`, `len(project)==59`, `len(tiers)==68`([`:735-739`](../../../tests/test_auth_api.py#L735)).
- **새 잠금**(D8-3c엔 없던 것): `403 ⇔ tier in (project, admin)` · `assertFalse(require_project_owner in declared and require_admin_user in declared)`([`:760-768`](../../../tests/test_auth_api.py#L760)) — "403 생산자 둘"·"두 인가 dep는 대안이지 스택"을 양방향으로 고정.
- [`ProjectAuthorizationTest`](../../../tests/test_auth_api.py#L350)는 dependency 쪽 `ownership ⟺ {project_id}`를 **그대로 정확**히 유지하면서 선언 쪽만 `403 ⟺ project-scoped 또는 admin`으로 넓히고, `assertFalse(admin_guarded and expected)`로 "관리자 route는 절대 project-scoped 아님"을 추가.

확장이지 완화가 아님 — 관리자 op가 빠져 관통하거나 다른 tier로 숨을 수 없다.

### 3. inner 겹 격리 구동 — D8-3c 교훈이 더 강한 잠금으로 재현

[`test_the_admin_dependency_cannot_run_without_authentication`](../../../tests/test_auth_api.py#L928)가 `require_admin_user`를 **route-level auth를 뺀 일회용 probe app에 단독 탑재**해 세션 없음→401·비관리자→403을 단정. **행위 기반 잠금**(D8-3c의 `inspect.signature` 구조 잠금보다 강하며 합성·래퍼 dependency에 거짓 경보 없음).

> **참고 — 이전 슬라이스의 사후 개선**: D8-3c 검증(본 검증자)이 비차단 H-a로 "소유권 inner 셀이 구현 형태에 결합"을 지적했고, 작업자가 D8-3c 커밋(3b99c80) 시점에 **소유권 inner 셀도 동일 probe-app 방식으로 개선했다**(v1.7.55 본문이 "시그니처를 단정하지 않고 상태코드를 단정…(H-a 폐쇄)"로 실측). 본 검증이 이 개선된 ownership probe 셀도 green임을 확인했다(아래 회귀). 내 검증 이후 바뀐 부분이나 방향은 옳고 H-a를 닫는다.

### 4. 동작·상태코드 — 계약 리터럴 일치

- 생성: [`users.py:103-120`](../../../services/application/app/auth/users.py#L103) `create_user`가 blank username/password → `InvalidUserInput`(400), 중복 → `DuplicateUsername`(409). 핸들러 매핑 정확([`main.py:2316-2330`](../../../services/application/app/main.py#L2316)).
- 비활성화: 미존재 → `UserNotFound`(404), 마지막 활성 관리자 → `LastActiveAdmin`(409)([`main.py:2338-2348`](../../../services/application/app/main.py#L2338)).
- OpenAPI 선언이 [`AdminErrorContractDeclarationTest.EXPECTED`](../../../tests/test_application_api.py#L500) 락 리스트와 정확히 일치(GET {401,403,503} · POST {400,401,403,409,503} · deactivate {401,403,404,409,503}; 422은 FastAPI 자동이라 의도적 제외). 양방향 exact-set 가드.

### 5. 세션 즉시 무효화 — D2 성질, 행위로 잠금

[`test_deactivating_a_user_kills_their_live_session`](../../../tests/test_auth_api.py#L566): alice 로그인 → admin 비활성화 → alice 기존 쿠키로 `/auth/me` **401**, 재로그인도 401. 메커니즘 = [`current_user_or_none`](../../../services/application/app/main.py#L1338)이 세션 해석 후 사용자를 다시 읽어 `is_active` 재확인. §H3 401 행이 "계정 비활성이 전부 같은 401"으로 이를 반영.

### 6. F2=A population 불변식 — 호출자 무관, 멱등

[`users.py:149-155`](../../../services/application/app/auth/users.py#L149) `_is_last_active_admin` = `not any(other active admin)`. [`:139`](../../../services/application/app/auth/users.py#L139)에서 `stored.is_active`일 때만 검사 → 이미 비활성 대상은 검사 우회(재호출 멱등, 자리 미차지). 인증된 비관리자 alice·2번째 관리자 존재 시 해제·비활성 관리자는 생존자 안 침 등 3셀이 over/under 양쪽을 잠근다.

### 7. 공개 계약 — additive, 해시 부재 구조적

`schema.d.ts` 재생성 결과 커밋본과 **무차이**(동기화됨). `AdminUserPayload` 타입 = `{id, username, is_admin, is_active}` 전부(`password_hash` 없음). response_model=AdminUserPayload가 구조적 장벽.

### 8. mutation 5종 — 전부 작업자 주장대로

| mutation | 결과 | 비고 |
|---|---|---|
| N5(handler에 해시 추가·model 클린) | **통과** | response_model이 model에 없는 필드를 걸러 해시가 wire 미도달. 결함 아님. |
| N5c(model+handler 모두 해시) | **적중** | list 테스트 keys 집합 + raw text `assertNotIn` 이중 가드, 생성 exact 비교도 실패 |
| admin inner 겹 제거 | **probe 셀만 적중** | probe 셀: 세션 없음→403(401 아님). 실앱 셀 19 passed/369 subtests green(route-level이 가림). 두 겹 방어 실증. |
| last-admin 검사 제거 | **deny 2셀 적중, 허용 셀 통과** | 마지막 관리자·비활성 생존자 셀 200→실패, 2번째 관리자 있을 때 해제 셀은 정상 통과 |
| session-kill(`is_active` 검사 제거) | **적중** | 비활성화 후 기존 세션 `/auth/me`→200(401 아님). 셀이 is_active 재검사에 의존 실증 |

### 9. 정량 — 보고 수치 재현

| 항목 | 작업자 보고 | 본 검증 실측 |
|---|---|---|
| `test_auth_api.py` | 53 / 707 subtests | **53 / 707**(27.3s) |
| `AdminUserApiTest` | 8 | **8 passed** |
| 백엔드 전량(mongo ON) | 1681 / 1 / 1455 (664s) | **1681 passed / 1 skipped / 1455 subtests**(875.9s) |
| 프론트 tsc | exit 0 | **exit 0** |
| 프론트 vitest | 217 / 14 files | **217 passed / 14 files**(264.6s) |
| schema.d.ts 동기 | 재생성 | **git diff 무변** |

종전 기준선 `1653/1418`에서 `+28 테스트·+37 subtest`만 늘고 기존 실패·skip 변동 없음. `1681-1653=28`, `1455-1418=37` 정합.

### 10. 정준 계약 자기일관 — 모순 없음

- v1.7.56(403 생산자 둘) ↔ §H3 403 행(① 소유권 ② 관리자, "둘 외의 operation이 403을 선언하면 거짓") ↔ §H3 401 행("계정 비활성이 전부 같은 401") ↔ 브리프 F1=C·F2=A: 리터럴 일치.
- 관리자가 타인 project에 접근 못 하는 것(F1=C, 별도 감사 승격) → "project-scoped 59개의 소유권 403은 관리자에게도 그대로"가 구조와 일치(관리자 route는 `require_project_owner` 없음, project route는 관리자라도 소유권 검사 통과해야).
- spec-silent-but-code-enforced: 재활성화(reactivate) 미구현은 브리프·work_log가 명시적(D6=A 범위 밖, 5-d 재검토 항목)이므로 계약 공백 아님.

## Issues / Risks

### Blocking (계약 의무)

**없음.** 3번째 인가 tier의 계약 요구 셀(경계 403·결합 불변식 4종·동작 상태코드·세션 즉시 무효화·F2=A population·공개 계약 additive)이 전부 명명된 회귀로 매핑되고, mutation 5종으로 실제로 무는 것을 확인했다. 계약 자기일관에 모순 없음.

### Hardening recommendations (비차단)

- **H-a(이전 슬라이치에서 이월, 작업자가 이미 폐쇄)** — D8-3c의 ownership inner 셀이 구조(inspect) 결합이었던 것을 작업자가 probe-app 행위 잠금으로 개선했다. 본 검증이 개선판도 green임 확인. 추가 조치 불필요.
- **H-b — test-mongo OFF 보조 기준선은 본 검증이 재실행하지 않았다**. ON 기준선 `1681/1`만 재현. 단 ON의 passed+skipped=1682가 종전(1654)+28과 정합.
- **H-c(운영 고려, 이 슬라이스 범위 밖)** — `POST /admin/users`가 관리자가 초기 비밀번호를 **평문으로 제공**받는다(`CreateUserRequest.password`). `scripts/create_user.py`와 동일 선이며 임시 비밀번호 자동 발급·전달 채널이 없어合理하나, 관리자가 설정한 비밀번호를 관리자가 알게 되는 점은 F1=C 하위 결정(C-1~C-5)과 함께 5-b/5-d에서 볼 수 있는 항목. 코드 주석이 이미 이 맥락을 적고 있다.

## Verdict

**합격(PASS).**

이유(실측에 기반):
1. 3번째 인가 tier의 계약 요구 셀에 빈 칸이 없고, 기존 3개 전수 가드를 **약화가 아닌 강화**로 편입했다(새 "403 생산자 둘"·"대안이지 스택 아님" 잠금 추가).
2. 헤드라인 보안 성질 두 개 — **세션 즉시 무효화**(D2)와 **F2=A population 불변식** — 를 행위로 잠갔고, mutation으로 두 셀이 모두 load-bearing임을 입증했다.
3. 두 겹 방어(admin inner 겹)가 D8-3c 교훈대로 probe-app 격리 구동으로 잠겼고, 한 겹 제거 시 실앱 셀은 green이지만 probe 셀이 적중한다.
4. 정량(`53/707`·`1681/1/1455`·tsc 0·`217`)이 재현됐고, 공개 계약이 재생성 무차이로 동기화됐다.
5. 계약 자기일관에 모순이 없다.

비차단 H-a(이미 폐쇄)·H-b·H-c는 합격을 가리지 않는다.

## Outstanding items

- **커밋 완료**: 본 슬라이스는 `fb88754`로 커밋돼 있고 작업 트리 깨끗함. 본 검증자가 만든 변경은 없다(검증 기록 파일 제외).
- **오너 결정 대기(F1=C 하위 C-1~C-5)**: 승격 수명·쓰기 허용 여부·감사 대상·소유자 통지·사유 필수. 5-b(전 프로젝트 목록)·5-d(관리자 화면) 착수 선행 조건. 브리프 §7에 정리됨.
- **5-c(전역 KPI)**: F1과 무관해 즉시 착수 가능(감사 저장소에 전역 조회 추가, 기존 집계 재사용).
- **비활성화 단방향**: reactivate 미구현은 설계적(D6=A 범위 밖), 5-d 화면 착수 시 재검토 항목.
- **test-mongo**: 본 검증을 위해 기동한 상태 그대로(문서화된 ON 기준선). 종료 여부는 오너 판단.

## Reproduction

```bash
# 인프라
docker compose -f docker-compose.test.yml up -d

# 초점
PYTHONPATH=. python3 -m pytest tests/test_auth_api.py -q           # 53 / 707
PYTHONPATH=. python3 -m pytest "tests/test_auth_api.py::AdminUserApiTest" -q   # 8

# 전량(mongo ON)
PYTHONPATH=. python3 -m pytest tests/ -q -p no:cacheprovider       # 1681 / 1 / 1455

# 프론트
cd frontend && npm run gen:api && git diff --stat src/api/schema.d.ts   # 무변
npx tsc --noEmit                                                    # exit 0
npm test                                                            # 217 / 14

# mutation 예(session-kill): main.py current_user_or_none 의
#   `if user is None or not user.is_active:` -> `if user is None:`
# -> pytest test_auth_api.py::AdminUserApiTest::test_deactivating_a_user_kills_their_live_session
#    기대: 1 failed (200 != 401)
# -> git checkout -- services/application/app/main.py   # 복원, git status 무변
```
