# 독립 검증 — 인증 D8-3b 프로젝트 소유권 시행 (SoT v1.7.53)

## Subject metadata

- **날짜**: 2026-07-28
- **요청자**: 오너 ("네가 저녀석이 작업한거 검증하고 의심하고 또 의심해줘야겠다")
- **검증자**: 독립 검증 AI (구현 미관여 — 구현은 별도 세션이 수행했고, 본 검증자는 코드를 한 줄도 쓰지 않았다)
- **대상 슬라이스**: D8-3b — project 소유권(403) + `GET /projects` 저장소 경계 필터
- **정준 계약 참조**:
  - `docs/system-contract-sot.md` v1.7.53 (changelog 36행 + 본문 §"제품과 프로젝트 경계" 255행)
  - `docs/plans/auth-d8-3-enforcement-decisions.md` §E1(=A, `owner_id=None` 항상 deny)·§E2(=A, project 경로는 소유권 + 목록은 **저장소 조회 경계** 필터)·§E3(=A, 하위 슬라이스 분할)·§3(구현자 선결: 미인증 401 / 비소유자 403 / `/health` 무인증 / **404 아닌 403**)
  - `docs/system-contract-sot.md` §H3 "상태코드 의미론" 표 (401 행은 v1.7.52가 추가한 선례)
- **검증 대상 소스**: **작업 트리(미커밋)**. HEAD = `e6ef32a feat(auth): D8-3a 인증 시행 …`. 변경 파일 14개(코드 5 · 테스트 4 · 생성물 1 · 문서 4) + 신규 `docs/daily_logs/2026-07-28/`. 검증 시점 `git diff` sha256 = `4d84daaf…`.

## Scope

계약을 먼저 좁혀 읽고 boundary matrix를 만든 뒤, 각 셀을 구현·회귀·실동작·뮤테이션으로 채웠다.

1. **정준 계약 자기일관** — v1.7.53 changelog ↔ SoT 본문 ↔ §H3 상태코드 표 ↔ 결정 브리프 E1/E2/§3.
2. **구현** — `require_project_owner`·`_REQUIRE_PROJECT_OWNER`·`_owned()`·`app.state.core_sot`·`list_projects_for_owner` 4계층(protocol·in-memory·Mongo·service).
3. **범위 독립 재계산** — 앱 route introspection으로 총/project-scoped/비project operation 수와 401·403·503 선언을 재도출.
4. **boundary matrix** — 계약이 요구하는 모든 "발화/미발화" 분기가 named 회귀에 매핑되는지.
5. **적대적 실동작 probe 8종** — 회귀가 **덮지 않는** 분기를 직접 구동(59개 전수 × 소유자/무소유/미존재, 저장소 장애, archive, 목록 대칭성, authn 선행).
6. **뮤테이션 6종** — 가드가 실제로 무는지(M1~M5) + 계약 조항을 우회하는 "행동은 같고 위치만 위반"하는 뮤테이션(B-2).
7. **공개 계약** — `gen:api` 재현성, 403 arm 수, tsc/vitest/build.
8. **전량 회귀 재현** — test-mongo를 **올린** 상태로 백엔드 전량.

## Methodology

환경: WSL2, 레포 루트 `/mnt/d/devel/에베베/ai_writte_system`, 베타 머신.

```bash
# 0. 인프라: 작업자 보고와 달리 test-mongo를 올린 상태로 검증한다
docker compose -f docker-compose.test.yml up -d

# 1. 범위·선언 독립 재계산 (openapi.json 을 직접 파싱)
python3 - <<'PY'
import json; spec=json.load(open("frontend/openapi.json"))
scoped=sum(1 for p,o in spec["paths"].items() for m in o if "{project_id}" in p)
# → project-scoped 59 / 비project 6 / 총 65, 403 미선언·거짓선언 0건, 401=63, 503=64
PY

# 2. 적대적 probe 8종 (회귀가 덮지 않는 분기)
PYTHONPATH=. python3 scratchpad/adversarial.py       # 본 파일 Findings §5

# 3. Mongo 쿼리 경계 스파이 — 반환값이 아니라 find()에 전달된 filter 문서를 확인
PYTHONPATH=. python3 - <<'PY'
from services.application.app.core_sot.mongo_repository import MongoCoreSotRepository
sent=[]
class SpyCursor(list):
    def sort(self,*a,**k): return self
class SpyCollection:
    def find(self,*a,**k): sent.append(a[0] if a else k.get("filter")); return SpyCursor()
repo=MongoCoreSotRepository.__new__(MongoCoreSotRepository); repo._projects=SpyCollection()
repo.list_projects_for_owner("user:1"); repo.list_projects()
print(sent)     # → [{'owner_id': 'user:1'}, None]
PY

# 4. 요청 본문/쿼리로 project_id 를 재지정하는 권한 상승 경로 탐색
PYTHONPATH=. python3 - <<'PY'
from fastapi.routing import APIRoute
from services.application.app.main import create_app
app=create_app()
# 각 project-scoped route 의 body/query 모델에 project_id 필드가 있는지 → NONE
PY

# 5. 뮤테이션 6종 (원본 cp 백업 → 패치 → 회귀 → 복원, sha256 로 복원 확인)
bash scratchpad/mutate.sh        # M1~M5
bash scratchpad/mutate_b2.sh     # B-2: 행동 동일 + 위치만 계약 위반

# 6. 전량 회귀 (test-mongo ON)
python3 -m pytest -q -rs         # 1642 passed, 1 skipped, 1058 subtests (677s)

# 7. 공개 계약
cd frontend && npm run gen:api && sha256sum src/api/schema.d.ts   # adcdbfcf… (재생성 후 diff 0)
grep -c "403: {" src/api/schema.d.ts                              # 59
npx tsc --noEmit && npx vitest run && npm run build
```

## Findings

### 1. 범위·선언 — 작업자 주장과 정확히 일치

`frontend/openapi.json`을 직접 파싱해 독립 재도출:

| 항목 | 재도출 값 | 작업자 주장 | 일치 |
|---|---|---|---|
| 총 operation | **65** | 65 | ✔ |
| project-scoped(`{project_id}`) | **59** | 59 | ✔ |
| 비project operation | **6**(`/health`·`/auth` 3종·`POST /projects`·`GET /projects`) | 6 | ✔ |
| 403 선언 누락(project-scoped) | **0** | 0 | ✔ |
| 403 거짓 선언(비project) | **0** | 0 | ✔ |
| 401 선언 | **63**(보호 61 + login + me) | 무변 | ✔ |
| 503 선언 | **64**(non-health 전부) | 무변 | ✔ |
| `schema.d.ts`의 403 arm | **59** | 59 | ✔ |

`npm run gen:api` 재생성 결과가 커밋 대상 `schema.d.ts`와 **바이트 동일**(sha256 `adcdbfcf…`) — 생성물이 현재 코드에서 재현된다.

### 2. 구현 — 계약 리터럴과 일치

- [`main.py:1337-1349`](../../../services/application/app/main.py#L1337) `require_project_owner`: 모듈 수준(3-a가 세운 단일 identity 규칙 준수), `Depends(require_authenticated_user)`를 **하위 dependency**로 받아 인증을 대체하지 않고 그 위에 얹는다. `NotFound` → 404, `owner_id is None or != current.id` → **403 `{"detail": "forbidden"}`**. 계약 리터럴 `forbidden` 그대로.
- [`main.py:1355-1358`](../../../services/application/app/main.py#L1355) `_REQUIRE_PROJECT_OWNER`가 인증·소유권 **두 dependency를 모두** 나열 — 3-a의 전수 가드(`require_authenticated_user in route.dependencies`)가 계속 유효하다. 소유권으로 대체했다면 401 가드가 조용히 눈이 멀었을 자리다.
- [`main.py:1246-1249`](../../../services/application/app/main.py#L1246) `_owned()`는 403을 **additive**로만 얹는다. 공유 상수를 오염시키지 않고 호출 지점마다 감싸므로 `POST/GET /projects`가 쓰는 `_ERRORS_STORAGE`에 403이 번지지 않는다.
- 저장소 4계층 전부에 `list_projects_for_owner`: [`repository.py:72`](../../../services/application/app/core_sot/repository.py#L72) protocol · [`service.py:165`](../../../services/application/app/core_sot/service.py#L165) in-memory · [`mongo_repository.py:174`](../../../services/application/app/core_sot/mongo_repository.py#L174) `find({"owner_id": owner_id})` · [`service.py:415`](../../../services/application/app/core_sot/service.py#L415) service. 기존 `list_projects()`는 의미를 바꾸지 않고 남겨 migration([`ordered_unit_migration.py:38`](../../../services/application/app/core_sot/ordered_unit_migration.py#L38))이 계속 전체를 본다 — 내부 유지보수 경로에 HTTP 보안 의미를 섞지 않은 판단은 타당하다.
- **권한 상승 경로 없음**: project-scoped 59개 route의 body/query 모델 중 `project_id`를 싣는 것이 **0개**(스크립트 #4). 가드가 검사한 path project와 handler가 실제로 다루는 project가 갈라질 수 있는 자리가 구조적으로 없다.

### 3. 전량 회귀 — 재현되나, 작업자가 보고한 기준선은 약한 실행이다

- **본 검증 실행(test-mongo ON)**: `1642 passed, 1 skipped, 3 warnings, 1058 subtests passed` (677.74s).
- 작업자 보고 "백엔드 전체 **1554 passed / 89 skipped**"는 **test-mongo를 내린 상태**의 실행이다(work_log가 스스로 밝히고 있고, 89 = Mongo 통합 계약 88 + live Chroma 1). 같은 파일에 "실 Mongo를 켠 첫 전체 실행 1642 passed / 1 skipped"도 적혀 있어 **은폐는 아니다**. 두 수의 합(1643)이 일치해 정합적이다.
- 다만 **HANDOFF의 "회귀 기준선"이 1554/89로 재정의됐다**(종전 기준선은 mongo-up의 1631/4). 다음 작업자가 이 줄을 기준으로 삼으면 Mongo 계약 88건이 skip된 상태를 정상으로 읽는다 → 아래 Hardening H-4.
- 프론트: `217 passed / 14 files`, `tsc --noEmit` exit 0, build **진입 404.87 kB · 관측 lazy 385.71 kB** — 작업자 주장 및 기존 기준선과 정확히 일치(403은 타입만 넓히므로 번들 무변이 맞다).

### 4. boundary matrix — 계약 분기 매핑

| 계약 분기(근거) | 방향 | 잠근 회귀 | 상태 |
|---|---|---|---|
| 59개가 소유권 dependency 선언 (v1.7.53) | should fire | `test_ownership_dependency_and_403_declaration_match_project_scope` | ✔ 전수 |
| 비project 6개는 **미선언** (E2=A) | should NOT | 같은 테스트(양방향 `assertEqual`) | ✔ 전수 |
| 59개가 403 선언 (H3 D3=A) | should fire | 같은 테스트 | ✔ 전수 |
| 비project 6개는 403 **미선언** (v1.7.53) | should NOT | 같은 테스트 | ✔ 전수 |
| 타인 소유 → 403 (E2=A) | should fire | `test_every_project_scoped_operation_refuses_a_foreign_project` | ✔ 전수(59) |
| `owner_id=None` → 403 (**E1=A**) | should fire | `test_other_owner_and_unowned_project_are_both_403` | △ 1 route |
| 소유자는 통과 (§3) | should NOT | `test_owner_can_read_own_project_and_missing_project_stays_404` | △ 1 route |
| 미존재 project → 404 (v1.7.53) | should NOT(403 아님) | 같은 테스트 | △ 1 route |
| 403 본문 = `{"detail":"forbidden"}` | 리터럴 | `test_other_owner_and_unowned_project_are_both_403` | ✔ |
| handler·요청 검증 **전에** 멈춤 (v1.7.53) | should fire | 위 전수 테스트가 **본문 없이** 호출 | ✔ |
| 목록은 본인 소유만 (E2=A) | should fire | `test_list_returns_only_the_authenticated_users_projects` | ✔ |
| 목록에 타인·무소유의 id·name·archived 미노출 (E2=A) | should NOT | 같은 테스트(dict 완전일치) | ✔ |
| **필터가 저장소 조회 경계에서 적용 (E2=A 명시)** | 위치 조항 | `test_list_projects_for_owner_filters_at_the_mongo_query_boundary` | ✘ **이름만 그렇고 단정하지 않음 → B-2** |
| 401이 403보다 앞선다 | 순서 | `AuthenticationBoundaryTest::test_every_protected_operation_refuses_a_sessionless_request` | ✔ 전수(61) |
| override seam이 선언을 지우지 않음 | should NOT | `TestSeamStaysAnOverrideTest`(두 override로 갱신) | ✔ |

△ 표시 3건은 **1개 route에만 명시 잠금**이 있다. 다만 (a) 선언 가드가 59개 전부에 **동일 dependency identity**가 붙어 있음을 전수로 잠그고, (b) 본 검증이 59개 전수 실동작으로 확인했으므로 계약 분기 자체는 충족된다 → 차단 아님, Hardening H-1.

### 5. 적대적 probe 8종 — 전부 통과 (회귀가 덮지 않는 분기)

`ProjectAuthorizationTest`가 1개 route에서만 확인하는 분기를 **59개 전수**로 직접 구동했다.

| # | 공격 | 결과 |
|---|---|---|
| 1 | 소유자가 59개 전부에서 401/403을 받지 않는가 | **통과** — 거부 0건 |
| 2 | `owner_id=None`이 59개 **전부**에서 403인가(E1=A) | **통과** — 예외 0건 |
| 3 | 소유권 dependency 안에서 pymongo 예외 발생 시 500이 아니라 **503**인가 | **통과** — 503(전역 handler가 dependency 예외까지 덮는다) |
| 4 | 미존재 project가 59개 전부에서 404인가 | **통과** — 59/59 404 |
| 5 | **archive된 자기 project**를 소유자가 여전히 읽는가(archive=읽기 허용) | **통과** — 200 |
| 6 | 목록 응답 본문에 타인·무소유 project의 **이름 문자열**이 섞이는가 | **통과** — 미검출 |
| 7 | 두 번째 사용자 관점에서도 대칭인가(교차 오염) | **통과** |
| 8 | 세션 없는 project 경로가 403이 아니라 **401**인가(authn 선행) | **통과** — 59/59 401 |

추가로 소유자 정상 경로에서 **요청 검증·도메인 의미론이 보존**됨을 확인했다: 본문 없음 → 422, 정상 본문 → 200, 잘못된 본문 → 422, archive된 project rename → 409.

### 6. 뮤테이션 — 가드가 실제로 문다 (M1·M2·M3·M4·M5) / B-2만 통과해 버린다

| 뮤테이션 | 기대 | 실측 |
|---|---|---|
| **M1** KPI route에서 소유권 dependency만 제거(403 선언은 잔류) | 선언·런타임 두 가드 동시 발화 | **발화** — `test_every_project_scoped_operation_refuses_a_foreign_project` + `test_ownership_dependency_and_403_declaration_match_project_scope` 가 같은 route subtest에서 동시 실패 |
| **M2** `owner_id is None` deny 분기 제거(E1=A 파기) | 무소유 arm 실패 | **발화** — `SUBFAILED(owner_id=None)` |
| **M3** 목록 필터 제거(전체 반환) | 목록·Mongo 회귀 실패 | **발화** — 6 failed |
| **M4** 비project operation(`_ERRORS_STORAGE`)에 거짓 403 선언 | over-strict 발화 | **발화** — `CrudErrorContractDeclarationTest::test_declared_error_statuses_match_the_lock_list`가 `POST /projects`·`GET /projects` subtest에서 실패(4 failed) |
| **M5** 소유권 검사 무력화(항상 통과) | 전수 403 회귀 실패 | **발화** — **61 failed**(59개 route subtest + 타인/무소유 arm 2) |
| **B-2** 필터를 저장소 경계에서 **파이썬 후처리로 이동**(행동 동일, E2=A 위반) | 어떤 테스트든 실패해야 정상 | **발화하지 않음 — `101 passed / 326 subtests`, 전부 green** ⇠ 아래 B-2 |

뮤테이션 후 원본은 sha256 대조로 복원 확인했다(main.py `352e5446…`, service.py `527e88c6…`, "restored byte-identical").

M1~M5는 이 슬라이스의 가드가 **실제로 문다**는 직접 증거다. 특히 M1은 3-a가 세운 성질("선언만 있고 배선이 빠진 drift는 OpenAPI만 봐서는 안 보인다")이 403 쪽에서도 유지됨을 보인다 — 선언 가드와 런타임 가드가 **동시에** 같은 route에서 실패했다.

반면 **B-2는 통과해 버린다**: `list_projects()`로 전체를 읽고 파이썬에서 거르는 구현은 E2=A가 명시적으로 금지한 형태인데, `test_list_projects_for_owner_filters_at_the_mongo_query_boundary`를 포함해 **단 한 건도 실패하지 않았다**.

### 7. 정준 계약 자기일관 — **모순 1건 발견 (B-1)**

§H3 "상태코드 의미론" 표([`system-contract-sot.md:331-343`](../../system-contract-sot.md))는 이 저장소가 "어떤 상태코드가 무엇을 뜻하는가"를 고정하는 자리다.

- **401 행은 v1.7.52(D8-3a)가 추가했다** — 3-a 검증 기록이 "본문 변경 4곳: … ② H3 표에 401 행 추가"로 확인한 선례다.
- **v1.7.53은 403을 59개 operation의 새 face로 도입하면서 이 표에 403 행을 넣지 않았다.** 문서 전체에서 `403`은 changelog와 §"제품과 프로젝트 경계" 문장에만 있고, 상태코드 의미론 표에는 없다.
- 더구나 표의 **404 행**은 지금 이렇게 읽힌다: *"대상이 없거나 **다른 project 소유**다. project isolation 위반은 존재를 알리지 않고 404로 수렴한다."* 이는 자원 수준 `project_id` 경계를 말한 문장이지만, **사용자 소유권 경계는 정반대로 403(존재를 드러냄)으로 결정**됐다(브리프 §3: "404 vs 403 … 지금은 403으로 간다"). 표만 읽는 다음 작업자는 경계 위반이 404로 수렴한다고 결론내린다.

CLAUDE.md의 검증 규칙은 이 형태를 **차단**으로 분류한다 — "changelog가 잠근 경계를 rule body가 언급하지 않은" 경우이며, 같은 표에 대해 바로 앞 슬라이스가 세운 선례를 이번 슬라이스가 따르지 않았다.

## Issues / Risks

### Blocking (계약 의무)

- **B-1 — §H3 상태코드 의미론 표에 403 행이 없고, 404 행이 새 경계와 충돌한다.**
  - 위치: [`docs/system-contract-sot.md:331-343`](../../system-contract-sot.md) (표), 특히 404 행.
  - 왜 차단인가: v1.7.52가 401에 대해 **같은 표에 행을 추가**하는 선례를 세웠고, 이 표가 상태코드 의미론의 정본이다. 403이 59개 operation의 상시 face가 됐는데 표는 그것을 모른다. 동시에 404 행의 "project isolation 위반은 404로 수렴"이 사용자 소유권 경계(403, 존재 노출)와 **문면상 충돌**한다.
  - 해소 조건: 403 행 추가(의미 = 살아 있는 세션은 있으나 **이 project의 소유자가 아니다**; `owner_id=None` 포함; handler·422보다 앞선다; 복구는 로그인 전환이지 요청 수정이 아니다) + 404 행에 "**자원 수준 `project_id` 경계**"라는 한정어를 달아 사용자 소유권 경계(403)와 구분.
  - 성격: **문서 전용**. 코드·회귀 변경 불필요.

- **B-2 — E2=A의 "저장소 조회 경계" 조항을 잠그는 회귀가 없다. 테스트 이름만 그렇게 주장한다.**
  - 위치: [`tests/test_core_sot_mongo.py:206`](../../../tests/test_core_sot_mongo.py#L206) `test_list_projects_for_owner_filters_at_the_mongo_query_boundary`.
  - 실측: 이 테스트는 **반환된 행만** 단정한다. `self._repo.list_projects()`로 전부 읽은 뒤 파이썬에서 `owner_id`로 거르는 구현으로 바꿔 `tests/test_auth_api.py` + `tests/test_core_sot_mongo.py`를 돌린 결과 **101 passed / 326 subtests — 전부 green**이었다(뮤테이션 B-2). 즉 이 테스트는 준수 구현과 위반 구현을 구분하지 못한다.
  - 왜 차단인가: E2=A는 "필터는 응답 후 클라이언트 필터링이 아니라 **저장소 조회 경계에서** 적용"을 오너 결정 문면으로 명시했고, 이는 성능이 아니라 **보안 경계** 조항이다(타인 행이 프로세스로 들어오지 않게 한다). 이름이 조항을 잠근다고 주장하는데 단정이 그 조항을 구분하지 못하면, 다음 작업자에게는 잠긴 것으로 보인다 — 빈 셀보다 나쁜 형태다.
  - 해소 조건: `find()`에 전달된 filter 문서를 단정하는 회귀 1건(본 검증 Methodology #3의 스파이 10줄이면 충분). **구현은 이미 옳다** — 현행 코드는 `find({"owner_id": owner_id})`이며 본 검증이 직접 확인했다. 잠금만 없다.

### Hardening recommendations (비차단 — 계약이 요구하지 않으나 두면 강해진다)

- **H-1 — 소유자 통과 / 무소유 403 / 미존재 404가 59개 중 1개 route에만 명시 잠금.** 본 검증이 59개 전수로 확인했고 선언 가드가 동일 identity를 전수 보장하므로 계약 분기는 충족된다. 다만 3-c(결합 감사)가 이 세 분기를 전수 subtest로 올리면 "1개 route 표본"이라는 서술 자체가 사라진다.
- **H-2 — 소유권 dependency 안에서 발생한 저장소 예외의 503 face에 회귀가 없다.** 본 검증 probe #3으로 503임을 확인했다. 위험은 미래 변경 쪽이다 — HANDOFF가 이미 경고하는 "endpoint를 광의 `except Exception`으로 감싸면 저장소 예외가 502로 샌다" 패턴이 **dependency에도 그대로 적용**되는데, 지금은 그 회귀가 없어 조용히 샐 수 있다.
- **H-3 — 프론트는 403을 원문 그대로 노출한다.** [`client.ts`](../../../frontend/src/api/client.ts)는 401만 세션 만료 경로로 처리하고 나머지는 `` `${status}: ${detail}` ``로 표시하므로, 무소유(legacy) project를 북마크한 사용자는 "403: forbidden"을 본다. D8-3b 범위 밖이지만 D8-3c/프론트 트랙의 실제 UX 항목이다.
- **H-4 — HANDOFF 회귀 기준선이 약한 실행으로 재정의됐다.** 현재 "표준 무인프라 실행 **1554 passed / 89 skipped**"가 기준선 줄이다. 종전 기준선은 mongo-up의 1631/4였고, 이 머신의 mongo-up 실측은 **1642 passed / 1 skipped**다. 두 값을 함께 적고 어느 쪽이 기준인지 명시하지 않으면, Mongo 계약 88건이 skip된 상태가 정상으로 읽힌다.
- **H-5 — 정확도 1건**: 작업자 요약의 "미존재 프로젝트는 기존 404를 유지"는 최종 상태코드로는 맞지만, **20개 operation에서는 (본문 없는 요청 × 미존재 project) 조합이 422 → 404로 앞당겨졌다**(가드가 검증보다 앞서기 때문이며, 3-a가 401에 대해 세운 성질과 같다). 두 코드 모두 이미 선언돼 있어 계약 위반은 아니다. 소유자 정상 경로의 422/200/409는 보존됨을 확인했다.

## Verdict

**조건부 합격 (conditional pass).**

**구현은 옳다.** 59개 project-scoped operation 전부가 타인 소유·무소유를 403으로 막고, 소유자는 59개 전부를 통과하며, 미존재는 404, 세션 없음은 401, 저장소 장애는 503, archive 의미론과 요청 검증은 보존된다 — 전부 본 검증이 **회귀에 의존하지 않고 직접 구동해** 확인했다. `GET /projects`는 실제로 Mongo `find({"owner_id": …})`로 좁히며, 요청 본문으로 project를 재지정하는 권한 상승 경로는 구조적으로 없다. 정량 주장(65/59/6 operation, 59개 403 arm, 프론트 217/14·404.87/385.71 kB, `gen:api` 재현성)은 전부 독립 재도출해 일치했고, 전량 회귀는 test-mongo를 올린 상태에서 **1642 passed / 1 skipped / 1058 subtests**로 재현됐다. 뮤테이션 M1~M5로 새 가드가 실제로 문다는 것도 입증했다.

**조건은 두 가지이며 둘 다 좁고 싸다:**

1. **B-1** — SoT §H3 상태코드 표에 403 행 추가 + 404 행에 "자원 수준 `project_id` 경계" 한정어(문서 전용).
2. **B-2** — `find()` filter 문서를 단정하는 회귀 1건 추가(구현 변경 없음; 테스트 이름이 이미 주장하는 것을 실제로 잠근다).

두 조건 모두 **코드 동작을 바꾸지 않는다** — 계약 표면과 잠금만 채운다. 해소되면 무조건 합격이다.

## Outstanding items

- **미커밋**: 변경 14개 파일 전부 작업 트리에 있다(HEAD `e6ef32a`). 작업자의 "아직 커밋하지 않았습니다" 주장은 정확하다.
- **동시 편집 사고**: 본 검증 세션 시작 시점에 **다른 세션이 같은 파일을 편집 중**이었다(09:05~09:52). 검증은 편집이 멈춘 뒤(10:21~)의 스냅샷을 대상으로 했다. 취소됐다는 그 세션의 pytest 프로세스 1개가 **네트워크 격리 샌드박스 안에서 09:10부터 멈춘 채 남아 있다**(PID 17414) — 정리하면 좋다.
- **배포 스택은 지금 내려가 있다**(`application`·`mongo`·`gateway`·`embedding`·`chroma`·`elasticsearch` 미기동, `worker`·`generation_worker`는 mongo 부재로 crash-loop 중, `frontend`만 healthy). 따라서 **D8-3b의 실 스택 라이브 관통 검증은 이번에도, 작업자도 수행하지 않았다** — 모든 근거는 in-process(TestClient·실 test-mongo) 수준이다. 3-a와 같은 수준의 라이브 확인을 원하면 스택 기동이 선행돼야 한다.
- **`owner_id=None` 잔존 데이터**: E1=A대로 영구 403이다. 배포 Mongo가 내려가 있어 현재 잔존 행 수는 확인하지 못했다. 스택 기동 시 `projects` 컬렉션에 `owner_id: null` 행이 있으면 그 project는 오너 본인에게도 잠긴다(E1=A가 의도한 결과이며, 폐기 또는 브리프 §E1의 선택지 D 귀속 스크립트가 해법).
- **운영 smoke 스크립트 4종**: 3-b가 새 부채를 더하지 않는다 — 4종 모두 `POST /projects`로 **자기 project를 만들어** 쓰므로, 401 부채(로그인 지원)만 해소되면 403은 발생하지 않는다(코드 확인: `phase4…:76`, `phase6…:136` 등).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
docker compose -f docker-compose.test.yml up -d
python3 -m pytest -q -rs                                   # 1642 passed, 1 skipped, 1058 subtests
PYTHONPATH=. python3 <scratchpad>/adversarial.py           # probe 8종 (Findings §5)
bash <scratchpad>/mutate.sh                                # M1~M5 (원본 cp 백업/복원 포함)
bash <scratchpad>/mutate_b2.sh                             # B-2 조항 우회 뮤테이션
cd frontend && npm run gen:api && npx tsc --noEmit && npx vitest run && npm run build
```
