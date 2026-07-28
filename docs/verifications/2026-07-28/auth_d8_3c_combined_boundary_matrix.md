# 독립 검증 — 인증 D8-3c 401·403 최종 결합 boundary matrix 감사 (SoT v1.7.55)

## Subject metadata

- **날짜**: 2026-07-28
- **요청자**: 오너 ("D8-3c 완료했다. 작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?")
- **검증자**: 독립 검증 AI (구현 미관여 — 본 검증자는 코드·테스트를 한 줄도 쓰지 않았다)
- **대상 슬라이스**: D8-3c — 3-a(인증 축)·3-b(소유권 축)이 각자 전수였던 것을 **하나의 401·403 boundary matrix로 결합 감사**. 새 정책·endpoint 동작은 추가하지 않는 최종 감사 슬라이스.
- **정준 계약 참조**:
  - `docs/system-contract-sot.md` v1.7.55 변경이력 본문 + §"제품과 프로젝트 경계"
  - `plans/auth-d8-3-enforcement-decisions.md` §3(구현자 선결: 미인증=401 · 비소유자=403 · `owner_id=None` 항상 deny · 남의 project=403) · §E3(A: 3-a→3-b→3-c, "각 단계에 자기 단계의 가드")
  - 선행 독립 검증 `docs/verifications/2026-07-28/auth_d8_3b_project_ownership.md`의 비차단 H-1("소유자 통과·무소유 403·미존재 404를 59개 전수 subtest로 올리면 폐쇄")
- **검증 대상 소스**: **작업 트리(미커밋)**. HEAD = `9692a7c feat(auth): enforce project ownership isolation`. 변경 파일 5개(테스트 1 · 문서 4), **소스(`services/`)·공개 계약(`schema.d.ts`) 무변**. 검증 시점 `git diff` sha256 = `a42ae150…`.

## Scope

정준 계약이 이 슬라이스에 요구하는 표면만 감사한다(계약 읽기 범위를 먼저 정한 뒤 코드를 연다 — CLAUDE.md 검증 규칙).

1. **tier 분할 계약** — 65개 operation이 *route dependency 기준*으로 public 4 · 인증 전용 2 · project-scoped 59 중 정확히 하나로 분류되고 tier 구성원이 리터럴로 고정되는가.
2. **결합 선언 불변식** — (a) 403 선언은 401 선언 없이 존재할 수 없고, (b) 소유권 dependency는 인증 dependency 없이 선언될 수 없으며, (c) 같은 dependency identity가 한 route에 두 번 선언될 수 없는가.
3. **결합 실동작 셀** — 세션 없는 요청이 **타인 소유** project를 지목할 때 403이 아니라 **401**인가(두 거부 조건이 동시에 만족되는 유일한 교차 칸).
4. **H-1 폐쇄** — 소유자 통과 · `owner_id=None` 403 · 미존재 404가 1개 route 표본이 아니라 59개 전수 subtest인가.
5. **두 겹 방어 실측** — 안쪽 인증 sub-dependency가 요청 구동으로는 보이지 않는다는 주장이 사실이며, 시그니처 직접 단정 셀이 그 겹을 독립적으로 잠그는가.
6. **public row** — `/auth/login` 본문 없는 호출이 401이 아니라 422로 "가드가 아니라 handler가 답한다"를 양성 증명하는가.
7. **계약 자기일관** — v1.7.55 본문 ↔ §제품 경계 ↔ §3/§E3 ↔ 선행 버전(v1.7.52·v1.7.53) 사이에 모순이 없는가.
8. **정량 재실행** — 보고된 `42/686`, `9/360`, `1653/1/1418`이 재현되는가.

## Methodology

작업자 주장을 전제로 쓰지 않고 1차 소스에서 재도출한다. mutation은 원본 `main.py`(HEAD에 이미 커밋됨 — 수정 집합에 없음)를 패치 → 회귀 → `git checkout` 복원하고 `git status`로 무변을 확인하는 방식.

```bash
# 0. 인프라 — test-mongo(rs-test, 27020) 기동 후 writable primary 확인
docker compose -f docker-compose.test.yml up -d
python3 -c "import pymongo;print(pymongo.MongoClient('mongodb://localhost:27020/?replicaSet=rs-test&serverSelectionTimeoutMS=3000').admin.command('hello')['isWritablePrimary'])"
# -> True

# 1. 초점 스위트(메모리 저장소, Mongo 불필요)
PYTHONPATH=. python3 -m pytest tests/test_auth_api.py -q
PYTHONPATH=. python3 -m pytest "tests/test_auth_api.py::CombinedBoundaryMatrixTest" -q

# 2. tier 분할·결합 불변식을 앱 객체에서 독립 도출(테스트 코드 안 읽고 재계산)
PYTHONPATH=. python3 - <<'PY'   # app.routes 순회 → tier 분류 → 4/2/59, {project_id} 일치, 불변식 위반 0건 도출
PY

# 3. 뮤테이션 3종 재현(M3 · M3c · M5)
#   M3:  require_project_owner 의 inner auth sub-dep 를 current_user_or_none 로 + 미인증→403
#   M3c: _REQUIRE_PROJECT_OWNER 에서 route-level auth 제거 + M3 동일 → 두 겹 모두 제거
#   M5:  require_project_owner 가 owner 도 거부(`or True`)
#   각각: Edit main.py → pytest 해당 셀 → git checkout -- services/application/app/main.py → git status 확인

# 4. 전량 회귀(test-mongo ON)
PYTHONPATH=. python3 -m pytest tests/ -q -p no:cacheprovider
```

## Findings

### 1. tier 분할 — 작업자 주장·정본과 정확히 일치(독립 도출)

앱 객체에서 직접 도출한 결과(스크립트 #2):
- `total_ops=65`, tier_counts `{public:4, auth:2, project:59}`, project tier 59개 전부 `{project_id}` 보유.
- `public = {(/health,get),(/auth/login,post),(/auth/logout,post),(/auth/me,get)}` — [`AuthenticationBoundaryTest.PUBLIC`](../../../tests/test_auth_api.py#L382) 리터럴과 동일.
- `auth_only = {(/projects,get),(/projects/post),(/projects,post)}` — [`CombinedBoundaryMatrixTest.AUTH_ONLY`](../../../tests/test_auth_api.py#L506) 리터럴과 동일.
- 결합 불변식 위반 **0건**(403-without-401 · ownership-without-auth · identity 중복 · tier⇔403선언).

새 endpoint가 dependency 없이 들어오면 `public` 집합이 5개가 돼 [`test_every_operation_lands_in_exactly_one_named_tier`](../../../tests/test_auth_api.py#L548)가 실패한다 — "조용히 통과"가 아니라 "예상치 못한 public operation"으로 드러난다. v1.7.55 본문의 tier 서술과 문자 그대로 일치.

### 2. 구현 — 계약 리터럴 그대로, 소스 무변 확인

- [`main.py:1337-1349`](../../../services/application/app/main.py#L1337) `require_project_owner`: `current=Depends(require_authenticated_user)`를 **하위 dependency**로 받아 인증을 *대체하지 않고* 그 위에 얹는다. `NotFound`→404, `owner_id is None or != current.id`→**403 `{"detail":"forbidden"}`**(§3 리터럴).
- [`main.py:1355-1358`](../../../services/application/app/main.py#L1355) `_REQUIRE_PROJECT_OWNER`가 인증·소유권 **두 dependency를 모두** 나열 — 3-a의 route-level 전수 가드가 계속 유효.
- **소스·공개 계약 무변**: `git status`에 `services/`·`schema.d.ts` 없음. 3c가 동작을 더하지 않았으므로 `schema.d.ts` 재생성·프론트 회귀는 대상 아니다(403 arm은 이미 v1.7.53에서 additive로 반영됨). 정량·계약 모두 이 전제와 충돌 없음.

### 3. 결합 실동작 셀(401 우선) — 로드베어링 셀이 trivially green이 아님을 입증

[`test_authentication_answers_before_ownership_on_every_project_route`](../../../tests/test_auth_api.py#L605)는 세션 없는 요청이 타인 project를 지목할 때 **59개 전수**로 401을 단정. 이 셀의 의미를 두 방향에서 실측했다:
- **M3c(두 겹 모두 제거)**: route-level auth 제거 + inner sub-dep를 `current_user_or_none`+403-on-None로 바꾸자, 이 셀이 59 subtest 전수 실패(403이 새어 나옴). 즉 이 셀은 "두 겹이 모두 빠지면 401이 403으로 샌다"를 정확히 잡는다 — trivially green이 아니다.
- **M3(한 겹만 제거)**: inner sub-dep만 제거하면 route-level이 살아 있어 이 셀은 **여전히 green**. 이것이 작업자의 핵심 주장("요청 구동으로는 한 겹 소실을 볼 수 없다")이며, 아래 #5에서 별도 셀이 잠근다.

401-first는 단순 UX가 아니라 보안 의미론이다 — 403을 내면 익명 호출자에게 project 존재·소유 사실을 알리고, 소유권 조회가 미인증 요청에서 실행됐음을 뜻한다(§3·v1.7.55 본문).

### 4. H-1 폐쇄 — 1-route 표본이 59 전수 subtest로 승격

3개 셀이 각각 59개 전수 subtest로 owner/None/missing을 잠근다:
- [`test_the_owner_passes_the_guard_on_every_project_operation`](../../../tests/test_auth_api.py#L651): 소유자가 `status not in (401,403)` — operation마다 **새 project**를 만들어(archive·변경 부수효과의 순서 의존 회피) 가드만 단정, handler가 내는 200/422/404는 각 endpoint 자기 계약에 맡긴다(주석 명시).
- [`test_an_unowned_project_is_refused_on_every_project_operation`](../../../tests/test_auth_api.py#L669): `owner_id=None`→403 + 본문 `{"detail":"forbidden"}` 리터럴.
- [`test_a_missing_project_is_404_on_every_project_operation`](../../../tests/test_auth_api.py#L685): 미존재→404(403으로 접히지 않음).

D8-3b 검증의 비차단 H-1("1개 route 표본")이 정확히 이 슬라이스로 폐쇄됐다 — 3b 기록 스스로 "3-c가 전수 subtest로 올리면 '1개 route 표본' 서술이 사란다"고 예약해 둔 것이다. **M5(over-strict: owner도 거부)** 재현에서 owner-pass 셀이 59 subtest 실패해 over-strict 방향도 문다.

### 5. 두 겹 방어 — 작업자의 가장 의심스러운 주장을 실측으로 확인

이 슬라이스에서 가장 적대적으로 검증한 지점. 작업자는 "inner 인증 sub-dep를 제거해도 매트릭스가 green이라, 시그니처를 직접 단정하는 셀로 따로 잠갔다"고 주장했다 — 이것이 (a) 사실인가, (b) 시그니처 셀이 실제로 무는가를 실측:

- **M3 재현(inner sub-dep 제거)**: `require_project_owner`의 `current=Depends(require_authenticated_user)`→`Depends(current_user_or_none)` + `current is None`→403. 결과 `CombinedBoundaryMatrixTest` = **8 passed, 1 failed, 360 subtests passed**. 360 subtest 전부 green(어떤 요청 구동 셀도 한 겹 소실을 못 본다)이고, 실패한 1개는 정확히 [`test_the_ownership_dependency_cannot_run_without_authentication`](../../../tests/test_auth_api.py#L624). 이 셀은 `inspect.signature(require_project_owner)`에서 `require_authenticated_user`를 sub-dep로 직접 단정 — 에러 메시지 `not found in [None, None, <current_user_or_none>]`로 무는 것을 확인.
- **결론**: 두 겹은 **독립적으로** 잠긴다 — route-level은 3-a·결합 선언 셀이, inner는 시그니처 셀이 잠근다. 작업자의 "원리적으로 요청 구동으로는 볼 수 없어 별도 셀로 잠갔다"는 설명이 팩트다. 안쪽 겹이 죽은 코드가 아니라 진짜 방어층임도 M3c(두 겹 모두 제거 시 누출)가 입증한다.

### 6. public row·인증 전용 tier — over-strict 양성 증거

- [`test_the_public_row_is_answered_by_handlers_not_by_a_guard`](../../../tests/test_auth_api.py#L715): `/health`·`/auth/logout`→200, `POST /auth/login`(본문 없음)→**422**, `GET /auth/me`→401. 가드는 요청 검증보다 앞서므로 422는 "가드가 없다"는 양성 증거.
- [`test_the_non_project_operations_serve_any_authenticated_user`](../../../tests/test_auth_api.py#L695): bob이 소유한 project가 없어도 `GET /projects`→200(빈 목록), `POST /projects`→200 — 소유권이 인증 전용 tier로 번지지 않음(저장소 조회 경계가 좁힌 결과, 가드 거부 아님).

### 7. 정량 재실행 — 보고 수치 한 자리까지 재현

| 항목 | 작업자 보고 | 본 검증 실측 |
|---|---|---|
| `test_auth_api.py` | 42 passed / 686 subtests | **42 passed / 686 subtests**(22.2s) |
| `CombinedBoundaryMatrixTest` | 9 passed / 360 subtests | **9 passed / 360 subtests**(9.2s) |
| 백엔드 전량(test-mongo ON) | 1653 / 1 skipped / 1418 subtests(700s) | **1653 passed / 1 skipped / 1418 subtests**(727.0s) |
| 수집 총합 | (1654) | **1654 collected** — 1653+1=1654 정합 |

종전 기준선 `1644/1058`에서 신규 +9 테스트·+360 subtest만 늘었고 기존 실패·skip 변동 없음 — `1418-1058=360`, `1653-1644=9`로 산술 일치.

### 8. 정준 계약 자기일관 — 모순 없음

- v1.7.55(65 = 4+2+59) ↔ v1.7.53(59 project-scoped, 6개 비-403 = 2 auth-only + 4 public) ↔ v1.7.52(61 protected + 4 public, 61=2+59): 세 버전의 operation 산술이 모두 정합.
- v1.7.55 본문 ↔ §"제품과 프로젝트 경계"(두 축이 하나의 matrix로 결합 감사됨, D8-7만 남음) ↔ §3(401/403/None-deny): 리터럴 일치.
- 시그니처 직접 단정 셀은 코드가 강제하지만 계약이 잠묵하는 경우가 **아니다** — v1.7.55 본문이 "안쪽 겹은 dependency 시그니처를 직접 단정하는 별도 셀로 잠갔다"로 명시하고 HANDOFF 함정 절도 같은 사실을 실측으로 남겼다. spec-silent-but-code-enforced 계약 공백 아님.

## Issues / Risks

### Blocking (계약 의무)

**없음.** boundary matrix의 계약 요구 셀(tier 분할·결합 선언 3종·401 우선·H-1 owner/None/missing·두 겹 방어·public row)이 전부 명명된 회귀 셀로 매핑되고, 각 셀이 뮤테이션으로 실제로 무는 것을 확인했다. 빈 칸 없음. 내부 계약 모순 없음.

### Hardening recommendations (비차단 — 계약이 요구하지 않으나 두면 강해진다)

- **H-a — 시그니처 셀의 구현 결합**. [`test_the_ownership_dependency_cannot_run_without_authentication`](../../../tests/test_auth_api.py#L624)은 `require_project_owner`의 매개변수 기본값이 **정확히** `Depends(require_authenticated_user)`임을 단정한다. 보안을 보존하면서 합성/래퍼 dependency로 리팩터링하면(예: `Depends(_auth_chain)`) 이 셀이 거짓 경보로 실패한다. fail-loud > silent라 허용되지만, 인증 배선 리팩터링 시 이 셀을 함께 갱신해야 한다는 점을 HANDOFF 함정 절이 이미 경고하고 있으므로 **추가 조치 불필요**(문서화됨).
- **H-b — test-mongo OFF 보조 기준선은 본 검증이 재실행하지 않았다**. 작업자 보고 `1565 passed / 89 skipped`는 본 검증자가 돌리지 않았다(ON 기준선 `1653/1`만 재현). 단 ON 실행의 passed+skipped=1654가 수집 총합 1654와 일치하므로 89 skip = Mongo 통합 계약 + live Chroma라는 작업자 해석은 정합적이다. ON이 권위 기준선이므로 비차단.
- **H-c — "인증됐으나 타인 소유 project → 403" 전수 셀은 3c가 아니라 3b에 있다**. [`ProjectAuthorizationTest.test_every_project_scoped_operation_refuses_a_foreign_project`](../../../tests/test_auth_api.py#L333)(59 subtest)이 이 셀을 소유하며, 3c의 "결합" 틀이 이 셀을 기대하게 될 수 있다. 정확한 귀속이고 SoT도 3b로 돌리므로 조치 불필요 — 다만 3c만 읽는 사람을 위해 매트릭스가 "두 축의 전수 가드를 흡수하지 않고 나란히 둔다"는 점(work_log Decisions)을 이미 명시했으므로 충분하다.

## Verdict

**합격(PASS).**

이유(실측에 기반):
1. 계약 요구 boundary 셀에 빈 칸이 없다 — tier 분할·결합 선언 3종·401 우선·H-1(owner/None/missing)·두 겹 방어·public row가 전부 명명된 회귀로 매핑.
2. **가장 의심스러운 주장**(inner sub-dep 제거 시 매트릭스 green, 시그니처 셀만 red)을 M3로 정확히 재현했고, 그 보완(M3c: 두 겹 모두 제거 시 401 우선 셀 대량 실패)과 over-strict(M5: owner 거부 시 59 실패)로 셀이 trivially green이 아님을 입증.
3. 정량(42/686 · 9/360 · 1653/1/1418)이 한 자리까지 재현됐고, 계약 자기일관에 모순이 없다.
4. 소스·공개 계약 무변이 "동작 무변" 주장과 충돌 없다.

비차단 H-a·H-b·H-c는 모두 문서화됐거나 권위 기준선으로 흡수되므로 합격을 가리지 않는다.

## Outstanding items

- **커밋 미수행**: 작업 트리는 5개 파일만 수정된 미커밋 상태(diff sha256 `a42ae150…`). 오너가 커밋을 지시하면 진행.
- **본 검증 중 인프라 변동**: test-mongo(`ai_writte_system-test-mongo-1`, 27020)를 본 검증을 위해 기동했다. 작업자는 이미 test-mongo ON을 기준선으로 쓰므로 상태 일관됨 — 종료 여부는 오너 판단.
- **D8-3 시행 종료**: HTTP 시행(3-a·3-b·3-c)이 닫혔다. 남은 구현은 D8-5(관리자 API/화면) → D8-6(영구 삭제) → **D8-7(Mongo·ES 인프라 인증, 외부 노출 금지 해제 조건)**이며 착수 순서는 오너 결정 대기중.
- **dogfood(GATE-1)**: "인가 없이 dogfood하면 데이터가 섞인다"는 종전 걸림돌이 사라졌다. D8-5~7과의 순서 역시 오너 판단 사항.

## Reproduction

```bash
# 인프라
docker compose -f docker-compose.test.yml up -d

# 초점 스위트(메모리, Mongo 불필요)
PYTHONPATH=. python3 -m pytest "tests/test_auth_api.py::CombinedBoundaryMatrixTest" -q
# 기대: 9 passed, 360 subtests passed

# 전량(test-mongo ON)
PYTHONPATH=. python3 -m pytest tests/ -q -p no:cacheprovider
# 기대: 1653 passed, 1 skipped, 1418 subtests passed

# M3 재현(inner sub-dep 제거 → 매트릭스 green, 시그니처 셀만 red)
# 1) services/application/app/main.py 의 require_project_owner 에서
#    current=Depends(require_authenticated_user) -> Depends(current_user_or_none),
#    403 조건에 `current is None or` 추가
# 2) PYTHONPATH=. python3 -m pytest "tests/test_auth_api.py::CombinedBoundaryMatrixTest" -q
#    기대: 1 failed, 8 passed, 360 subtests passed (실패 = test_the_ownership_dependency_cannot_run_without_authentication)
# 3) git checkout -- services/application/app/main.py   # 복원, git status 로 services/ 무변 확인

# M3c(두 겹 모두 제거) / M5(owner 거부, 403 조건에 `or True`) 도 동일 패턴.
```
