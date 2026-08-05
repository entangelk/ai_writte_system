# 라우터 분해 Slice 1(auth·admin) + billable 가드 modernization — 독립 검증

- **날짜**: 2026-08-05
- **의뢰자**: 오너("작업 AI가 작업한 거 검증하고 의심하고 또 의심해줄래? 라우터 분리 작업이라서 매우 신중하게 봐줘야 하고, 아직 작업 중이야")
- **검증자**: Claude Code(독립 세션 — 구현에 관여하지 않음)
- **검증 대상**: 커밋 5개 `539171f..e8b9908`(결정 브리프 + billable 가드 정규식→route-driven + auth 분해 + admin 분해 + 작업 로그). HEAD `e8b9908`, 작업 트리 clean. **Slice 1의 일부**(auth·admin 2 도메인만); 나머지 7 도메인과 Slice 2(관리자 주소 분리)는 미착수.
- **정본 참조**: 이 슬라이스의 계약은 "행위 무변"이다 — SoT에 라우터 파일 배치 규칙은 없으므로, 경계 매트릭스는 **(a) 76 operation (path,method) 보존 · (b) billable 9건 분류 보존 · (c) 데코레이터 배선(response_model·responses·status_code·dependencies) 보존 · (d) handler 본문 동일** 이다. 결정 근거(D8-7 G1=C)의 정본은 `docs/system-contract-sot.md` v1.7.75 · `docs/plans/auth-d8-7-infra-auth-decisions.md` · `docs/plans/router-split-and-admin-separation-decisions.md`.
- **작업 출처**: 커밋 `539171f` → `e8b9908`(committed; working tree 미사용). 실측 HEAD `e8b9908`.
- **보강 패스**: 같은 날 같은 HEAD에서 재현 경로를 커밋된 스크립트([`repro_router_split.py`](repro_router_split.py))로 복구하고, 표면 3개(OpenAPI 계약 §9 · 등록 순서 §10 · import 경로 §11)를 추가 검증했다. 판정은 그대로 **합격**, 비차단 1건(H-3) 추가.

---

## Scope

라우터가 `main.py` 한 파일에서 `register_auth`/`register_admin` 모듈로 나가도 **아무것도 안 변했는지**를 잡는다. 리팩터이므로 계약은 "행위 무변"이고, 뮤테이션은 modernization(정규식→route-driven) 가드에 대해 직접 돌렸다.

1. **route 집합 보존** — (path, method) 76개가 한 글자도 안 바뀌었는가(추가·누락 0).
2. **데코레이터 배선 보존** — 이동한 12개 route의 `response_model`·`responses`·`status_code`·`dependencies=_REQUIRE_*`가 옛 것과 동일한가(보안 배선이 빠지면 (path,method) 동일해도 회귀).
3. **handler 본문 동일** — 12개 이동 handler 본문이 byte-동일인가.
4. **billable 분류 보존** — `billable_actions.py` 무변 + 9개 유료 op는 이동 12건과 무관 + 가드 green.
5. **modernization 가드 뮤테이션** — route-driven 가드가 **이동한 파일**의 provider 호출을 실제로 잡아내는가(이것이 modernization의 존재 이유).
6. **순환 import / DI 배선** — `from ..main import` 심볼 해석 · register_* 로 전달되는 서비스 14개 일치.
7. **결정 전제(D8-7 G1=C)** — "compose 바인딩 접두어, 코드 0줄" 주장이 1차 소스에서 맞는가.
8. **전체 suite** — 작업자가 못 돌린 전수 회귀를 검증자가 직접 돌려 기준선과 비교.
9. **OpenAPI 계약 무변**(보강) — 저장소가 이미 가진 계약 표면(`scripts/dump_openapi.py`, 프런트 TS 코드젠 입력)이 분해 전후로 바이트 동일인가.
10. **등록 *순서*** (보강) — 집합이 같아도 순서가 바뀌었다(이동 route 는 이제 `register_*()` 호출 지점에서 등록). first-match 결과가 달라질 쌍이 있는가.
11. **import 경로 견고성**(보강) — 분해로 생긴 `main ↔ routers` 순환이 import 이름에 따라 다르게 풀리는가.

## Methodology

검증자는 구현에 관여하지 않았고, 작업자 주장을 1차 소스(코드·SoT·compose·실 실행)에서 재도출했다. 트리는 clean이므로 뮤테이션 복원은 clean-tree 분기(`git checkout --`)를 썼고, 전후로 `git status --short` 공백 + 마커 grep으로 원복을 확인했다(`docs/guides/verification.md` §"The restore rule").

**보강 패스(같은 날, 같은 HEAD `e8b9908`, 트리 clean)** — 1차 기록 직후 작업 머신이 두 번 다운되며 `/tmp`가 날아갔고, 그때 §Reproduction이 가리키던 애드혹 스크립트 3종(`/tmp/cmp_routes.py`·`decorcmp.py`·`bodycmp.py`)이 **소실돼 이 기록이 재현 불가 상태였다**. 보강 패스는 (a) 소실된 재현 경로를 저장소 안의 커밋된 스크립트로 대체하고, (b) 1차 기록이 안 본 3개 표면(OpenAPI 계약·등록 순서·import 경로)을 추가로 뜯었다. 비교는 소스 텍스트가 아니라 **조립된 `create_app()` 실측**이고, 분해 전 트리는 `git worktree`로 따로 깔아 원본 트리를 건드리지 않았다. 아래 §9~11과 H-3이 보강 산물이며, 1차 findings §1~8은 그대로 둔다(§2·§8에 보강 주석만 덧붙였다).

```bash
# 분해 전/후를 나란히 두고 공개 표면 지문을 diff (원본 트리 무변)
git worktree add /tmp/pre e8b9908~5
(cd /tmp/pre && python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/pre.json)
python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/post.json
diff /tmp/pre.json /tmp/post.json      # → 차이 없음 (routes=76, order-pairs=0)

# 저장소 제공 계약 덤프로 교차 확인
(cd /tmp/pre && python3 scripts/dump_openapi.py) > /tmp/openapi_pre.json
python3 scripts/dump_openapi.py        > /tmp/openapi_post.json
sha256sum /tmp/openapi_pre.json /tmp/openapi_post.json   # → 동일 (1e275ab8…)

# import 경로 견고성: 폐기용 worktree에서만 뮤테이션(원본 트리 무접촉)
git worktree add /tmp/post e8b9908
```

```bash
git rev-parse HEAD                       # e8b9908
git status --short                       # (비어있음 — 뮤테이션 전후 매번)
git diff --stat HEAD~5 HEAD              # main.py -348 / routers 신규 479 / test 2파일
git diff --stat HEAD~5 HEAD -- services/application/app/quota/billable_actions.py  # (빈 = 무변)

# (1) route 집합: HEAD app.routes vs HEAD~5 정규식 추출(종전 가드가 쓰던 동일 정규식)
python3 /tmp/cmp_routes.py
# → HEAD 76 / HEAD~5 76 / added [] / dropped [] / IDENTICAL

# (2)(3) 데코레이터 배선 + 본문 byte-동일(이동 12개)
python3 /tmp/decorcmp.py   # → 12 decorators, diffs = 0, IDENTICAL
python3 /tmp/bodycmp.py    # → ALL body lines present verbatim in HEAD~5 main.py

# (5) modernization 뮤테이션: 이동한 파일(routers/auth.py /me/quota)에 llm_call_scope( 삽입
#   (Edit) → pytest -k "provider_calling or free_operations or readable_endpoint"
#   → 2 failed(B6 양방향 셀 + free-route 셀) → git checkout -- → status 비어있음 · 마커 grep 0

# (8) 전수 회귀(test-mongo 직접 기동 확인 후)
docker ps                                  # ai_writte_system-test-mongo-1 Up healthy 127.0.0.1:27020
python3 -m pytest tests/ -q                # → 2191 passed, 1 skipped, 1931 subtests, 0 failed (917.81s)
```

## Findings

### 1. route 집합 — IDENTICAL (76 = 64 + 12)
HEAD의 `create_app().routes`(APIRoute)에서 (path, method) 76개를 실측하고, HEAD~5의 `main.py`에서 종전 가드가 쓰던 **동일 정규식**으로 76개를 추출해 비교했다. 추가·누락 0. main.py 잔류 64 + routers 이동 12(auth 4·admin 8). 독립 2경로 교차 확인: `CombinedBoundaryMatrixTest`가 `len(tiers)==76`·`by_tier["project"]==61`을 **명시 단정**(`tests/test_auth_api.py:1215-6`)으로 못박고 통과했다.

### 2. 데코레이터 배선 — IDENTICAL (12/12)
이동 12개 route의 `@app.METHOD(...)` 인자(response_model·responses·status_code·dependencies)를 옛 main.py와 정규화 비교. **diff 0**. 특히 `dependencies=_REQUIRE_AUTH`(/me/quota 등)·`_REQUIRE_ADMIN`(admin 8)·`status_code=204`(purge)가 한 글자도 안 바뀌었다. (path,method) 동일성으로는 잡히지 않는 보안 배선 회귀가 없음.

**(보강) 소스 텍스트 → 런타임 실측으로 승격.** 위 비교는 데코레이터 *글자*를 봤다 — `_REQUIRE_ADMIN` 이라는 이름이 같아도 그 상수가 다른 것을 가리키게 됐다면 통과해버린다. 보강 패스는 조립된 앱에서 **76개 route 전부의 해석된 dependant 트리**(중첩 dep까지 평탄화한 호출 이름)를 status_code·response_model·responses와 함께 찍어 분해 전후로 비교했다 → **76/76, diff 0**(`endpoint.__module__`만 의도대로 다름). admin 8개가 전부 `require_admin_user`를 실제로 물고 있고, `/admin/**/access-grants`·`purge` 2건은 route-level `_REQUIRE_ADMIN` + handler-level dep가 겹쳐 `require_admin_user` 2회가 그대로 유지된다. 이름이 아니라 **실제 호출될 함수**가 같음이 확인됐다.

### 3. handler 본문 — byte-동일 (12/12)
12개 이동 handler의 nontrivial 본문 라인이 전부 HEAD~5 main.py에 축어로 존재한다. 본문 drift 0.

### 4. billable 분류 — 보존
`billable_actions.py`가 HEAD~5~HEAD에서 **무변**(diff 빈). 9개 유료 op는 전부 writing/analysis/context-search route이고 이들은 main.py에 **잔류**(이동 12건 중 유료 op 0). 가드 green(`test_billable_actions` + `test_auth_api` = 112 passed / 863 subtests — 작업자 주장과 정확 일치).

### 5. modernization 가드 — 뮤테이션으로 물림 증명 ★
작업자 주장의 핵심("라우터가 main.py 밖으로 나가도 분류가 살아있다")을 뮤테이션으로 부정하려 했다. `routers/auth.py`의 `/me/quota`(이동한 파일·비-유료 route) handler에 `llm_call_scope(` 마커를 넣자:
- `test_every_provider_calling_operation_is_classified`(B6 양방향) — left 집합에 `/me/quota`가 남아 실패.
- `test_free_operations_never_open_a_provider_scope` — `/me/quota` subtest에서 실패.

**2개 셀이 즉시 재실패** → `inspect.getsource(route.endpoint)`가 **파일 위치와 무관**하게 이동한 handler에서 provider 호출을 잡아냄이 증명됐다. 원복 후 `git status --short` 공백·마커 grep 0 확인. 종전 카나리("정적 정규식 == app.routes")는 본문 집합이 이제 app.routes에서 직도출되어 자명해져 "모든 endpoint 소스 가독"으로 정확히 교체됐다 — 이것은 약화가 아니라 동치를 따름정리로 만든 재설계.

### 6. 순환 import / DI 배선 — OK
`create_app()` 실 로드 `LOAD_OK`. `from ..main import`로 가져오는 심볼(모델·`_REQUIRE_*`·에러 dict·`require_*_user`)이 import 라인(`main.py:2693`) **위**에 전부 정의돼 있어 순환 없이 해석된다 — 어느 하나라도 아래였으면 Python이 ImportError를 낸 상태(경험적 증명). `register_admin` 14 서비스 인자가 호출부(`main.py:2962-71`) 14 kwargs와 이름·개수 일치. app.state(users·sessions·core_sot·access_grants·admin_audit·quota)가 register 호출(2960+) **이전**에 세팅된다 — 인가 dep는 요청 시 app.state를 읽으므로 순서 안전.

### 7. 결정 전제 D8-7 G1=C — FAITHFUL (서브에이전트 1차 소스 교차 검증)
서브에이전트가 적대적으로 4방향 부정을 시도했으나 못 부쉈다. `system-contract-sot.md:51`(v1.7.75)·`:294-5`·`auth-d8-7-infra-auth-decisions.md:60-65`가 전부 "저장소 `127.0.0.1:` loopback 바인딩, **코드 0줄**"로 못박고, `docker-compose.yml:16/144/175/204/240`이 그 바인딩을 실현한다. ASGI/supervisord는 SoT·브리프에 **0회** 등장. ⓐ(2차 ASGI) vs ⓑ(이미지 공유 compose 서비스) 비용이 ⓑ로 기울어는 합리적이며, `worker`/`generation_worker`(compose 268-352)가 이미 이미지-공유·포트-미게시 패턴으로 존재한다.
**유일한 단서(수사적, 사실 오류 아님)**: 작업자가 이를 "SoT 오독의 정정"으로 프레이밍했으나, SoT는 애초에 G1=C를 ASGI와 결부해 말한 적이 없다. 실제로 정정한 대상은 2026-08-04 work_log의 **느슨한 비유**("ⓐ가 G1=C의 재료를 그대로 쓴다")다 — 루프백 부분만 참이고 2차 앱/uvicorn/supervisord는 전부 신규라는 비판은 타당하다. 하중 받는 사실(G1=C≠ASGI·0코드·ⓑ로 기울음)은 전부 확인.

### 8. 전수 회귀 — 기준선과 한 자리 차이 없음 ★
`2191 passed / 1 skipped / 1931 subtests / 0 failed / 0 error`(917.81s). 이 숫자는 라우터 분해 **직전** 기준선(work_log Task 3: `2191 / 1 / 1931`)과 동일하다 → 테스트 델타 0. `1931 subtests` 무변이 곧 operation 76 + tier 분포 보존의 실측. warnings 3종은 리팩터 무관한 기존 `TestClient` 수집 경고(에러 아님).

### 9. OpenAPI 계약 — 바이트 동일 (보강) ★
저장소는 이미 계약 표면을 갖고 있다: `scripts/dump_openapi.py`(독스트링 — "프런트가 이 스키마에서 TS path/request 타입을 생성한다"). 1차 기록은 이것을 안 썼다. 분해 전/후 worktree에서 각각 덤프한 결과가 **293,924 바이트 · sha256 `1e275ab8…` 로 완전 동일**(`diff` 무출력). 이 한 번의 비교가 76 route의 path·method·요청/응답 스키마·상태코드·operationId·태그를 한꺼번에 덮는다 → **프런트 코드젠 재생성이 불필요함이 실측으로 확인**됐다(리팩터가 TS 타입에 파급 0).
단, OpenAPI는 `dependencies=`를 **스키마에 싣지 않는다** — 인가 배선은 §2 보강(런타임 dependant 트리)이 덮는다. 두 검사는 상호 보완이고, 어느 한쪽만으로는 구멍이 남는다.

### 10. 등록 *순서* — 바뀌었으나 무해함이 증명됨 (보강) ★
1차 기록은 route **집합**이 같음을 봤다. 그러나 분해는 순서를 바꾼다 — 이동한 12개는 이제 원래 자리가 아니라 `create_app()` 안 `register_auth(...)`/`register_admin(...)` 호출 지점(`main.py:2960-71`)에서 등록된다. FastAPI/Starlette는 **첫 매치**로 라우팅하므로, literal 경로와 `{param}` 경로가 같은 자리에서 겹치면 순서가 곧 동작이다(예: `/admin/users/me` 가 `/admin/users/{user_id}` 뒤로 밀리면 조용히 죽는다).
76개 route의 동일-method·동일-세그먼트수 쌍을 전수로 돌려 literal↔`{param}` 충돌 후보를 셌다 → **0쌍**. 겹치는 쌍이 아예 없으므로 등록 순서는 매칭 결과에 영향을 줄 수 없다. 순서 변경이 이번엔 무해하다는 것이 **우연이 아니라 검사된 사실**로 남는다.
※ 이 성질은 Slice 1의 나머지 7 도메인에서 자동 보존되지 않는다 — `projects`·`drafts`처럼 `{project_id}` 를 쓰는 도메인이 이동할 때 재확인 대상이다(→ Outstanding).

### 11. import 경로 견고성 — 분해가 만든 새 취약점 (보강, 비차단 → H-3)
`main.py:2693`은 **절대** 경로(`from services.application.app.routers.admin import …`)로, `routers/admin.py:24`는 **상대** 경로(`from ..main import …`)로 서로를 부른다. 이 혼합 때문에 순환이 **import 이름에 따라 다르게 풀린다**:

| 로드 방식 | 분해 전(`e8b9908~5`) | 분해 후(`e8b9908`) |
|---|---|---|
| `services.application.app.main`(FQ) | LOAD OK | LOAD OK |
| `app.main`(`PYTHONPATH=services/application`) | **LOAD OK** | **ImportError: cannot import name 'register_admin' from partially initialized module** |

짧은 이름으로 들어가면 `app.main` 과 `services.application.app.main` 이 서로 다른 모듈 객체가 되고, 두 번째 로드가 반쯤 초기화된 `routers.admin` 을 만나 죽는다. **분해 전에는 살아 있던 경로가 분해 후 하드 실패로 바뀌었다.**
지금은 사고가 아니다 — 저장소 전 진입점이 FQ를 쓴다(Dockerfile `CMD uvicorn services.application.app.main:app`, tests 전부, `scripts/*`). 단 `docs/daily_logs/2026-07-22/work_log.md:125`에 `PYTHONPATH=services/application python3 -m pytest …` 형태가 남아 있어 짧은 이름이 sys.path에 노출되는 실행 방식 자체는 이 저장소에 선례가 있다(그 상태에서도 아무도 `app.` 로 import 하지 않아 무사).
**해법이 1줄**임을 폐기용 worktree에서 실증했다: `main.py`의 두 import를 상대 경로(`from .routers.admin import register_admin`)로 바꾸면 **FQ·짧은 이름 양쪽 다 LOAD OK**(필요 심볼이 전부 import 라인 위에 있어 상대 경로에서는 부분 초기화 모듈로도 해석된다). 원본 트리는 건드리지 않았다.

## Issues / Risks

### Blocking (계약 의무) — 없음

경계 매트릭스의 모든 칸(76 route · 분류 9건 · 데코레이터 배선 · 본문)이 코드·테스트·뮤테이션으로 채워졌고, 전수 suite가 기준선 무변으로 닫혔다.

### Hardening / 프로세스 권고 (비차단)

- **H-1(프로세스) — 작업자의 "전수 suite 못 돌림"은 낡은 환경 가정이었다.** work_log Task 4가 *"test-mongo 미기동으로 백엔드 전수 suite가 live 테스트에서 멈춰 끝까지 못 돌림"* 이라 썼으나, **test-mongo는 그 시점에 이미 5시간째 healthy하게 떠 있었다**(`docker ps`: `ai_writte_system-test-mongo-1`, `127.0.0.1:27020`, ping OK). 검증자가 직접 올려 917.81s 만에 전수 green을 확인했다. 이 저장소의 반복된 실측 항목("live 불가 말기 전에 `docker ps`·포트 도달성 직접 확인")의 재발이며, 결과적으로 작업자가 **15분이면 되는 회귀를 건너뛰었다**. 코드 결함은 아니지만, "라우터 분해는 신중하게"라는 의뢰 맥락에서 검증 커버리지 구멍으로 기록한다.
- **H-3 [폐쇄됨 2026-08-05 `59fe1a1` — 오너 지시로 Slice 2 착수 전 수정]**(보강 — 분해가 만든 import 경로 취약점) — §11 참조. 권고대로 `main.py`의 두 import를 상대 경로로 바꿨고, 회귀 [`tests/test_app_import_paths.py`](../../../tests/test_app_import_paths.py)가 두 이름을 서브프로세스로 로드해 양방향을 잠근다. **뮤테이션 실증**: 절대 경로로 되돌리면 짧은 이름 셀만 실패하고 FQ 셀은 통과한다(= 가드가 정확히 H-3만 겨냥한다). 수정 후 §Reproduction (A) 지문이 분해 전 트리와 여전히 **IDENTICAL**이라 행위 무변도 유지된다. 이하 원문은 발견 시점 기록으로 남긴다. `main.py`(절대) ↔ `routers/*`(상대) 혼합 import 때문에 앱이 **FQ 이름으로만** 로드된다. 분해 전에는 `app.main` 로도 로드됐다. 지금은 전 진입점이 FQ라 사고가 없지만, 실패 모드가 "순환 import" 라는 **원인과 동떨어진 메시지**여서 처음 밟는 사람이 시간을 태우기 쉽다. **Slice 2가 바로 그 시점**이다 — `create_product_app`/`create_admin_app` + 별도 compose 서비스는 정의상 **새 진입점을 하나 더 만든다**. 권고: Slice 2 착수 전에 `main.py:2693-4`를 상대 import로 바꾼다(1줄×2, 양쪽 경로 LOAD OK 실증 완료). 이 기록은 코드를 고치지 않았다 — 검증자 권한 밖이고, 오너 판단 사안이다.
- **H-2(Slice 2 설계 감시 — 현재 결함 아님)** — 작업자가 스스로 발견·기록한 분기: `create_app()`에서 `/admin`을 빼면 `CombinedBoundaryMatrixTest`(76 + admin 8 op 기대)가 깨진다. 제안된 `create_app()` 테스트-호환 shim + `create_product_app`/`create_admin_app` 분리 방식이 합리적이나, **shim이 진짜 배포 앱과 달라지는 것을 막는 별도 가드가 Slice 2에 필수**다. 이 저장소가 `ObservedProvider` 계측 누락(fake green이 배포에서만 드러남)으로 이미 데인 형태와 동형이며, HARDEN-1 선례(8.2c에서 실 Mongo 조립 가드를 신설한 이유)가 정확히 이 사태를 가리킨다. Slice 2 착수 전 오너 확인 사안으로 남겨둘 것.

## Verdict

**합격(PASS) · Blocking 0.**

라우터 분해 Slice 1(auth·admin)은 "행위 무변" 계약을 **독립 6경로 교차 확인**으로 이행했다: (1) route 집합 IDENTICAL(76) (2) 데코레이터 배선 IDENTICAL(12/12) + **해석된 dependant 트리 IDENTICAL(76/76)** — 이름이 아니라 실제 호출 함수 수준 (3) handler 본문 byte-동일(12/12) (4) billable 분류 보존(표 무변 + 가드 green) (5) **OpenAPI 스키마 바이트 동일**(sha256 `1e275ab8…`, 프런트 TS 코드젠 파급 0) (6) **등록 순서 변화가 무해**(순서민감 쌍 0). modernization 가드는 **이동한 파일에서 provider 호출을 잡아내는 것을 뮤테이션으로 증명**했고(2 셀 재실패), 전수 suite는 기준선 `2191/1/1931`과 무변 green. 결정 전제(D8-7 G1=C)는 1차 소스로 FAITHFUL.

비차단 3건(H-1 프로세스·H-2 Slice 2 shim 감시·H-3 import 경로)은 합격을 가리지 않는다. **H-3은 분해가 실제로 만든 유일한 새 취약점**이지만 현재 전 진입점이 FQ import라 미발현이고, 1줄×2로 닫히는 것이 실증됐다 — Slice 2가 새 진입점을 만들기 전이 적기다.

## Outstanding items

- **7 도메인(health·projects·drafts·analysis·memory·context_search·writing·observability) Slice 1 잔여** — 동일 R1 패턴의 기계적 정리. 본 검증이 종단 증명한 패턴이 그대로 적용된다. **재검증은 `repro_router_split.py` 를 새 기준 커밋으로 다시 돌리면 끝난다**(지문 diff 무출력 = 행위 무변). 단 §10 순서 성질은 자동 보존이 아니다 — `{project_id}`·`{draft_id}` 를 쓰는 도메인이 이동하면 order-sensitive pairs 가 0을 유지하는지 그 실행에서 확인할 것.
- **H-3(import 경로) 처리 여부** — Slice 2 착수 전 `main.py:2693-4` 상대 import 전환. 오너 결정 사안.
- **Slice 2(관리자 주소 분리 ⓑ)** — `_assemble_services()` 추출 → `create_product_app`/`create_admin_app` → compose `admin` 서비스(포트 미게시) → nginx `/api/admin/` → 노출·분리 가드. **H-2의 shim-drift 가드가 선행 조건**.
- **push 미수행** — 커밋 5개는 main에만 있고 오너 push 대기.

## Reproduction

1차 기록의 재현 경로는 `/tmp` 애드혹 스크립트 3종에 의존했고 머신 재부팅으로 **소실됐다**. 보강 패스에서 저장소 안 커밋된 스크립트로 대체했다(`docs/verifications/2026-07-24/repro_*.py` 선례를 따름). 아래는 전부 현재 트리에서 그대로 돌아간다.

```bash
git checkout e8b9908 && git status --short              # clean

# (A) 공개 표면 지문 — route 집합·해석된 dep 트리·status/response_model/responses·
#     openapi sha·순서민감 쌍을 한 번에. 분해 전/후에서 돌려 diff.
git worktree add /tmp/pre e8b9908~5
(cd /tmp/pre && python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/pre.json)
python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/post.json
diff /tmp/pre.json /tmp/post.json && echo IDENTICAL
# → 차이 없음. stderr: pre=in-routers=0 / post=in-routers=12, routes=76, order-pairs=0

# (B) 저장소 제공 계약 덤프로 교차 확인(프런트 TS 코드젠 입력)
(cd /tmp/pre && python3 scripts/dump_openapi.py) > /tmp/openapi_pre.json
python3 scripts/dump_openapi.py                  > /tmp/openapi_post.json
sha256sum /tmp/openapi_pre.json /tmp/openapi_post.json
# → 둘 다 1e275ab8c779a46766edbfaa9e75a38d990cab8b9c7536291a58a8f64bf270b6 (293,924 B)

# (C) 가드 + tier
python3 -m pytest tests/test_billable_actions.py tests/test_auth_api.py -q
# → 112 passed, 863 subtests (보강 패스에서 재실행, 1차 수치와 일치)

# (D) modernization 뮤테이션(routers/auth.py /me/quota 에 '# MARK llm_call_scope(' 삽입 후)
python3 -m pytest tests/test_billable_actions.py -k "provider_calling or free_operations"
# → 2 failed → git checkout -- services/application/app/routers/auth.py → clean

# (E) import 경로(§11) — 폐기용 worktree에서만
git worktree add /tmp/post e8b9908
PYTHONPATH=/tmp/post/services/application python3 -c "from app.main import create_app"   # → ImportError
PYTHONPATH=/tmp/post python3 -c "from services.application.app.main import create_app"   # → OK
PYTHONPATH=/tmp/pre/services/application  python3 -c "from app.main import create_app"    # → OK (분해 전)

git worktree remove /tmp/pre && git worktree remove /tmp/post

# (F) 전수 회귀 — test-mongo 기동 확인 후(1차 패스 수치, 보강 패스에서는 미재실행)
docker compose -f docker-compose.test.yml up -d
python3 -m pytest tests/ -q                             # → 2191/1/1931, 0 failed
```

**보강 패스에서 실제로 다시 돌린 것**: (A)(B)(C)(E) — 전부 HEAD `e8b9908`·clean tree에서 재도출. **(D)(F)는 1차 패스 결과를 그대로 인용**한다(재부팅으로 test-mongo가 내려가 있고, 그 사이 트리·HEAD가 바뀌지 않았으므로 재실행 사유 없음). (C)가 1차 수치(112/863)와 정확히 일치하는 것이 그 사이 무변경의 방증이다.
