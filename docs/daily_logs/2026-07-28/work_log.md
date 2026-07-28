# 2026-07-28 작업 로그

## Task — 인증 D8-3b project 소유권 시행 + 목록 저장소 필터

### Goals

- `HANDOFF.md`의 다음 작업 D8-3b를 이어서 수행한다.
- `/projects/{project_id}/…` 전 범위를 소유권 dependency로 잠가 타인 소유와
  `owner_id=None`을 403으로 거부한다.
- `GET /projects`는 응답 후 필터가 아니라 저장소 조회에서 현재 사용자 소유분만 읽는다.
- 401·404·정상 소유자 동작을 과잉 교정하지 않고, OpenAPI와 생성 타입을 실제 동작에 맞춘다.

### Completed work

- `services/application/app/main.py`
  - 모듈 수준 `require_project_owner`를 추가했다. 기존 `require_authenticated_user`를 하위
    dependency로 사용하고, project missing은 404, 타인 소유·무소유는 403 `forbidden`이다.
  - project-scoped 59 operation 전부를 `_REQUIRE_PROJECT_OWNER`로 전환했다. 인증 dependency를
    대체하지 않고 그 위에 별도 소유권 dependency를 얹었다.
  - `_owned(...)`가 59 operation의 OpenAPI에 403을 additive 선언한다. `POST /projects`와
    `GET /projects`는 특정 project를 지목하지 않으므로 인증만 유지하고 403을 선언하지 않는다.
  - dependency가 같은 Core SOT를 읽도록 `app.state.core_sot`를 배선했다.
- Core SOT 저장소 경계
  - `CoreSotRepository`·in-memory·Mongo·service에 `list_projects_for_owner(owner_id)`를 추가했다.
  - Mongo 구현은 `projects.find({"owner_id": owner_id}).sort("_id", ASCENDING)`이다.
  - `GET /projects`가 이 메서드에 인증 user id를 넘겨 다른 사용자·무소유 project의 id/name/archive
    상태가 응답 조립에 도달하지 않게 했다.
- 회귀
  - `ProjectAuthorizationTest` 5건: 소유자 200 + missing 404(over-strict), 타인 403,
    `owner_id=None` 403, 목록 wire 격리, 59 operation 실제 foreign-id 403, dependency/403 선언의
    project 범위 양방향 일치.
  - 실 Mongo 목록 필터 회귀를 fallback/transaction mixin 계약에 추가했다.
  - `tests/auth_support.py`는 인증과 소유권 dependency의 **해석만 override**한다. route 선언은
    건드리지 않으며 `TestSeamStaysAnOverrideTest`가 두 override와 선언 불변을 잠근다.
  - H3 exact lock list 5개 트랙(CRUD·analysis·memory/source·writing·observability)에 403을
    project operation별로 명시했다. 비project `POST/GET /projects`는 403 부재를 유지한다.
- 공개 계약·문서
  - `frontend/src/api/schema.d.ts`를 재생성해 59개 403 error arm을 additive 반영했다.
  - 정본을 v1.7.53으로 올리고 `CHANGELOG.md`, 인증 결정 브리프 구현 상태, `HANDOFF.md`를 현재
    상태로 다시 썼다.
- 독립 검증 보강
  - `docs/verifications/2026-07-28/auth_d8_3b_project_ownership.md`의 조건부 합격 B-1·B-2를
    폐쇄했다. 정본 v1.7.54에서 403/404 의미론을 분리하고, Mongo `find()` filter를 직접 단정하는
    스파이 회귀를 추가했다.
  - 비차단 H-2도 소유권 dependency 내부의 Mongo 장애가 500이 아니라 균일 503으로 매핑되는
    회귀를 추가해 닫았다.
  - H-4에 따라 HANDOFF의 주 기준선을 test-mongo ON 전량 실행으로 복구하고, 무인프라 실행은
    88개 Mongo 계약이 추가 skip되는 보조 수치로 구분했다.

### Issues found

#### 독립 검증 B-1 — 정본의 403 누락과 404 문면 충돌

- §H3 상태코드 의미론 표가 사용자 소유권 403을 담지 않았고, 기존 404 행의 "다른 project 소유"가
  새 403 결정과 문면상 충돌했다.
- 정본 v1.7.54에 403 행을 추가하고, 404는 요청한 하위 자원이 path의 `project_id`와 다른
  project에 속하는 자원 수준 격리로 한정했다.
- 코드 동작은 바뀌지 않았고, 다음 작업자가 표만 읽어도 두 경계를 반대로 해석하지 않게 됐다.

#### 독립 검증 B-2 — Mongo 쿼리 경계 테스트가 반환값만 단정

- 기존 테스트는 결과만 확인해 전체 목록을 읽은 뒤 Python에서 거르는 E2=A 위반 뮤테이션도
  통과했다.
- 실 Mongo 반환 회귀는 의미에 맞게 이름을 바꾸고, 별도 `MongoOwnerFilterQueryTest`가
  `_projects.find({"owner_id": "user:1"})`에 전달된 filter 문서를 직접 단정하게 했다.
- 비차단 H-2도 함께 보강해 dependency 내부 `AutoReconnect`가 503 균일 본문으로 매핑되는지
  잠갔다.

#### 샌드박스 안 TestClient·localhost Mongo 정지

- 증상: 최소 `/health` TestClient 요청과 localhost:27020 Mongo 연결이 응답 없이 대기하거나
  `Operation not permitted`였다.
- 원인: 코드 교착이 아니라 실행 샌드박스의 로컬 네트워크 제한이었다.
- 해결: 허용된 샌드박스 밖 pytest로 경계 테스트를 실행했다. 신규 소유권+실 Mongo 집중
  `6 passed / 126 subtests`, 인증 전체 `32 passed / 326 subtests`.
- 결과: 구현과 머신 하네스 문제를 분리했고, 실제 Mongo 쿼리 경계까지 검증했다.

#### 패턴 sweep — 저장소 장애 fake가 옛 목록 메서드를 override

- `tests/test_application_api.py`의 503 전역 handler 회귀 2곳이 `list_projects`를 override했다.
  새 HTTP 목록은 `list_projects_for_owner`를 호출하므로 그대로 두면 의도한 저장소 장애를 더 이상
  발화하지 않는다.
- 두 fake를 새 메서드로 정렬했고 관련 회귀 `8 passed / 6 subtests`를 확인했다.
- `rg`로 목록 호출부를 전수 확인했다. 나머지 `list_projects()`는 migration·내부 전체 목록
  용도이므로 소유자 필터로 바꾸지 않았다. 해당 기존 경계는 `git blame`으로 원래 의도를 확인했다.

#### 첫 전체 실행의 OpenAPI lock 59칸

- 실 Mongo를 켠 첫 전체 실행은 기능 테스트 `1642 passed / 1 skipped`가 통과하고, 기존 exact
  lock list가 새 403을 모르는 project operation **59칸만** 실패했다.
- 다섯 lock list를 갱신한 뒤 집중 계약 회귀 `23 passed / 365 subtests`, 최종 전체 무인프라
  실행 `1554 passed / 89 skipped / 1058 subtests`로 green을 확인했다.
- skip 89는 테스트 Mongo를 내린 표준 무인프라 실행의 Mongo 통합 계약들 + live Chroma다.
  신규 Mongo 필터는 그 전에 실제 test-mongo 연결로 통과시켰다.

### Decisions

- 오너가 독립 검증 기록을 기준으로 보강 후 커밋을 요청했다. 차단 B-1·B-2는 전부 폐쇄하고,
  직접 관련된 저비용 hardening H-2·H-4도 같은 커밋에 포함했다.
- H-1의 59개 전수 정상/무소유/미존재 matrix는 이미 예정된 D8-3c의 본래 목표라 이 보강에서
  중복 선행하지 않았다. H-3은 프론트 403 UX 결정이 필요한 별도 범위이고, H-5는 계약 위반이
  아닌 guard 선행 순서의 정확도 메모이므로 후속으로 남겼다.
- 기존 오너 결정 E1=A·E2=A·E3=A를 그대로 구현했다. 새 owner-level fork는 없었다.
- 소유권 dependency는 project를 반환하지만 handler는 기존 service 조회를 유지했다. 이 슬라이스의
  목표는 경계 시행이며 59개 handler 시그니처/본문을 함께 리팩터링하면 범위가 불필요하게 커진다.
  dependency의 선행 조회는 보안 경계 비용으로 받아들이고, 중복 제거는 성능 근거가 생길 때 별도다.
- `list_projects`를 의미 변경하지 않고 `list_projects_for_owner`를 추가했다. migration과 내부
  유지보수는 전체 목록이 필요하고, 기존 메서드의 의미를 바꾸면 HTTP 보안 범위를 내부 작업까지
  확장하게 된다.
- 외부 노출 금지는 유지한다. HTTP 소유권은 섰지만 D8-3c 최종 결합 감사와 D8-7 Mongo·ES
  인프라 인증이 남아 있다.

### Verification

- 독립 검증 기록: 구현·정량·뮤테이션은 통과, B-1·B-2 조건부 합격 지적을 이번 보강에서 폐쇄.
- 신규 쿼리 filter + dependency 503 집중 회귀: `2 passed`.
- 보강 후 백엔드 전체(test-mongo ON): `1644 passed / 1 skipped / 1058 subtests`.
- 구문·diff: `python3 -m py_compile ...`, `git diff --check` 통과.
- route 정적 전수: 전체 65 operation, project-scoped 59, dependency/403 불일치 0.
- 신규 경계 + 실 Mongo: `6 passed / 126 subtests`.
- 인증 전체: `32 passed / 326 subtests`.
- 저장소 503 관련: `8 passed / 6 subtests`.
- H3 다섯 lock list: `23 passed / 365 subtests`.
- 백엔드 전체(테스트 Mongo off): `1554 passed / 89 skipped / 1058 subtests`.
- 프론트: `gen:api`, `tsc --noEmit`, build 성공, `217 passed / 14 files`.
  번들 진입 404.87 kB, 관측 lazy 청크 385.71 kB로 기존 기준선과 동일.

### Next steps

- D8-3c: 3-a의 61개 인증 범위와 3-b의 59개 소유권 범위를 하나의 최종 boundary matrix로
  결합 감사한다. 검증 H-1의 소유자 통과·무소유 403·미존재 404도 59개 전수 셀로 올려
  빈 칸·중복·거짓 401/403 선언을 잠근다. 새 정책·동작을 추가하지 않는 슬라이스다.
- 프론트 hardening 후보(H-3): 403을 `"403: forbidden"` 원문으로 노출하는 현재 UX를
  사용자용 안내로 바꿀지 별도 결정한다.
- 별도 추적 부채: `APPLICATION_BASE_URL` 사용 운영 smoke 4종에 로그인 자격증명 지원.
- 이후 D8-5 관리자 API/화면, D8-6 영구 삭제, D8-7 Mongo·ES 인프라 인증 순서.

---

## Task — 인증 D8-3c 최종 결합 감사(401·403 boundary matrix)

### Goals

- `HANDOFF.md`의 다음 작업 D8-3c를 수행한다.
- 3-a의 인증 축과 3-b의 소유권 축을 **하나의 매트릭스로 결합 감사**해 빈 칸·중복·거짓 선언을
  잠근다. 새 정책·endpoint 동작은 추가하지 않는다.
- 독립 검증 H-1(소유자 통과·`owner_id=None` 403·미존재 404가 1개 route 표본)을 59개 전수
  subtest로 올려 폐쇄한다.
- 새 셀이 실제로 무는지 뮤테이션으로 확인한다 — green 여부가 아니라 "무엇을 잠갔는가"를 본다.

### Completed work

- `tests/test_auth_api.py`에 `CombinedBoundaryMatrixTest`를 추가했다(신규 9 테스트).
  기존 3-a·3-b 가드는 각 슬라이스의 자기 가드이므로 손대지 않았다(결정 브리프 §E3의
  "각 단계에 자기 단계의 가드"). 소스 코드는 한 줄도 바뀌지 않았다.
  - **tier 분할** — 65개 operation을 *route의 dependency로부터* public 4 · 인증 전용 2 ·
    project-scoped 59로 분류하고 각 tier 구성원을 리터럴로 고정했다. public 리터럴은
    `AuthenticationBoundaryTest.PUBLIC`을 재사용한다(같은 목록을 두 벌 두면 언젠가 갈라진다).
  - **결합 선언 불변식** — 403 선언은 401 선언 없이 존재할 수 없고, 소유권 dependency는 인증
    dependency 없이 선언될 수 없으며, 같은 identity가 한 route에 두 번 선언될 수 없다.
    각 슬라이스의 가드는 자기 축만 보므로 이 세 가지는 어느 쪽도 말할 수 없던 문장이다.
  - **결합 실동작** — 세션 없는 요청이 **타인 소유** project를 지목해도 403이 아니라 401임을
    59개 전수로 구동했다. 두 거부 조건을 동시에 만족하는 유일한 입력이며, 여기서 403을 내면
    익명 호출자에게 project의 존재·소유 사실을 알리게 된다.
  - **H-1 폐쇄** — 소유자 통과 · 무소유 403 · 미존재 404를 각각 59개 전수 subtest로 올렸다.
    소유자 셀은 operation마다 새 project를 만든다(archive·변경 부수효과가 순서 의존을 만든다).
    소유자 셀의 단정은 `status not in (401, 403)`이다 — 이 슬라이스가 감사하는 것은 가드이고,
    그 뒤 handler가 내는 200/422/404는 각 endpoint 자신의 계약이다.
  - **public row** — `/health`·`/auth/logout` 200과 `POST /auth/login`의 본문 없는 호출이
    **422**임을 확인한다. 가드는 요청 검증보다 앞서므로 422는 "가드가 없다"는 양성 증거다.
- `docs/system-contract-sot.md`를 v1.7.55로 올리고, 제품 경계 절의 "D8-3c 남음"을 실제
  상태(HTTP 시행 3단계 종료, D8-7만 남음)로 고쳤다. `CHANGELOG.md`·`HANDOFF.md`도 갱신했다.

### Issues found

#### 뮤테이션 M3 — 인증 두 겹 중 한 겹을 빼도 관측 동작이 변하지 않는다

- 증상: `require_project_owner`의 인증 하위 dependency를 제거하고 미인증을 403으로 바꾸는
  뮤테이션을 넣었는데 **매트릭스 전체가 green**이었다.
- 원인: 코드 결함이 아니라 두 겹 방어다. project route는 `_REQUIRE_PROJECT_OWNER`에서
  인증 dependency를 **먼저** 선언하므로 하위 dependency가 사라져도 401이 먼저 나간다.
  실제로 누출되는 구성은 두 겹이 **모두** 빠진 경우이며(M3c), 그때는 매트릭스가 59개 전수로
  실패한다.
- 해결: 요청 구동으로는 원리적으로 한 겹 소실을 볼 수 없으므로, 안쪽 겹을
  `inspect.signature(require_project_owner)`의 하위 dependency로 직접 단정하는 셀을 추가했다.
  이제 M3 단독 뮤테이션도 실패한다.
- 결과: 두 겹이 **독립적으로** 잠긴다. 이 사실 자체가 다음 작업자에게 필요한 정보라
  테스트 주석과 정본 v1.7.55에 실측으로 남겼다.

#### 뮤테이션 6종 결과

| # | 뮤테이션 | 무는 셀 |
|---|---|---|
| M1 | `owner_id=None`을 허용 | 무소유 403 (59 subtest 실패) |
| M2 | 미존재 project를 403으로 | 미존재 404 (59) |
| M3 | 소유권 dependency의 인증 하위 dependency 제거 | 시그니처 셀(추가 후) |
| M3c | 두 겹 모두 제거 + 선언 순서 역전 | 401 우선 셀 (59) |
| M4 | 한 route만 소유권 dependency 상실 | tier 분할 + 결합 선언 불변식 |
| M5 | 소유자도 거부 | 소유자 통과 (59, over-strict) |

### Decisions

- 기존 3-a·3-b 가드를 새 매트릭스로 **흡수하지 않고 유지**했다. 각 슬라이스가 자기 단계의
  가드를 갖는 것은 결정 브리프 E3=A의 명시적 구조이고, 전수 구동이 일부 겹치는 비용보다
  "한 클래스가 무너지면 축 하나가 통째로 무방비"인 위험이 크다.
- 매트릭스의 tier를 **path 모양이 아니라 route dependency에서** 도출했다. 경로는 operation이
  어떻게 생겼는지를, dependency는 무엇이 실제로 시행하는지를 말한다 — 감사는 시행하는 쪽을
  읽어야 한다. 두 방향의 일치는 3-b의 기존 가드가 이미 잠근다.
- 새 테스트를 별도 모듈로 빼지 않고 `tests/test_auth_api.py`에 넣었다. 이 모듈의 계약은
  "override 없는 실제 앱을 구동하는 유일한 곳"이며(`TestSeamStaysAnOverrideTest`가 잠근다),
  새 모듈을 만들면 그 성질을 복제하거나 잃는다.
- 오너 결정 fork는 없었다. 이 슬라이스는 E1=A·E2=A·E3=A의 마지막 단계 실행이다.

### Verification

- `tests/test_auth_api.py`: `42 passed / 686 subtests`(신규 9 테스트 · 360 subtest).
- 뮤테이션 6종: 위 표대로 전부 해당 셀에서 실패, 사후 `git diff` 무변으로 원복 확인.
- 백엔드 전체(test-mongo ON): `1653 passed / 1 skipped / 1418 subtests` (700s).
  종전 기준선 `1644 / 1 / 1058`에서 신규 9 테스트·360 subtest만 늘었고 기존 실패·skip 변동 없음.
- 백엔드 전체(test-mongo OFF 보조): `1565 passed / 89 skipped / 1418 subtests` (188s).
  두 실행의 passed+skipped가 1654로 일치하므로 89 skip은 Mongo 통합 계약 + live Chroma뿐이다.
- 소스·공개 계약: `services/` 무변이므로 `schema.d.ts` 재생성·프론트 회귀는 대상 아님.

### Next steps

- D8-3 시행은 닫혔다. 다음은 **D8-5 관리자 API/화면 → D8-6 영구 삭제 → D8-7 Mongo·ES 인프라
  인증** 순서이며, 외부 노출 금지는 D8-7까지 유지된다.
- 프론트 hardening(H-3): 403 원문 노출 UX를 사용자용 안내로 바꿀지는 여전히 별도 결정이다.
- 추적 부채: `APPLICATION_BASE_URL` 사용 운영 smoke 4종의 로그인 지원.

### 독립 검증 후속 보강 (같은 슬라이스)

독립 검증 `docs/verifications/2026-07-28/auth_d8_3c_combined_boundary_matrix.md`는
**합격(차단 0건)**이었고 비차단 후보 3건을 남겼다. 그중 H-a를 닫았다.

- **H-a 폐쇄 — 시그니처 단정을 격리 구동으로 교체했다.** 종전 셀은
  `inspect.signature(require_project_owner)`의 매개변수 기본값이 정확히
  `Depends(require_authenticated_user)`임을 단정해서, 보안을 유지한 채 합성·래퍼
  dependency로 리팩터링하면 **거짓 경보**로 실패했다. 이제 바깥 겹을 일부러 뺀 일회용
  앱에 `require_project_owner`만 마운트해 상태코드로 단정한다 — 세션 없음 **401** ·
  소유자 **200** · 타인 **403**. 소유자/타인 두 줄은 401이 "프로브 앱이 잘못 조립돼서"가
  아니라 안쪽 겹이 실제로 거부한 것임을 보증하는 over-strict 절반이다.
  - 양방향 실측: M3(안쪽 겹 제거)는 여전히 **실패**하고, 합성 dependency
    (`Depends(_auth_chain)`)로 바꾸는 정당한 리팩터링은 **통과**한다. 검증이 지적한
    거짓 경보 조건이 실제로 사라졌음을 뮤테이션으로 확인했다.
- **H-c — 귀속 상호참조를 매트릭스 docstring에 명시했다.** "세션 없음 → 401(61개)"은
  `AuthenticationBoundaryTest`, "인증됐으나 타인 소유 → 403(59개)"은
  `ProjectAuthorizationTest`가 소유한다. 3c만 읽는 사람이 매트릭스에 빈 칸이 있다고
  오독하지 않도록, 흡수하지 않은 이유(한 클래스가 무너지면 축 하나가 무방비)를 함께 적었다.
- **H-b — 조치 없음.** test-mongo OFF 보조 기준선 `1565 / 89`는 검증자가 재실행하지
  않았을 뿐 본 작업에서 같은 날 실측한 값이고, ON 실행과 passed+skipped=1654로 일치한다.
  권위 기준선은 ON이다.

보강 후 재검증: `tests/test_auth_api.py` `42 passed / 686 subtests`, 백엔드 전량
(test-mongo ON) `1653 passed / 1 skipped / 1418 subtests`. 테스트 수는 그대로다 —
셀 하나의 **잠금 방식**만 바뀌었고 계약·소스는 무변이다.

---

## Task — 인증 D8-5a 관리자 경계 + 사용자 관리

### Goals

- `HANDOFF.md`의 다음 트랙 D8-5(관리자 API·화면, D6=A)를 착수한다.
- 착수 차단 결정을 브리프로 올려 오너 판단을 받고, **그 결정에 의존하지 않는 부분만** 먼저 짓는다.
- 관리자 경계(`require_admin_user`)와 최소 사용자 관리(목록·생성·비활성화)를 세우고
  기존 boundary matrix에 관리자 tier를 정식으로 편입한다.
- 새 가드가 실제로 무는지 뮤테이션으로 확인한다.

### Completed work

- **결정 브리프** `docs/plans/auth-d8-5-admin-decisions.md`를 썼다. D6=A로 범위는 이미 결정돼
  있었지만, **관리자가 타인 소유 project에 접근하는가(F1)**는 D8-3이 방금 전수로 잠근 경계를
  다시 설계하는 문제라 구현자가 고를 수 없어 오너 결정을 받았다.
- `services/application/app/auth/users.py`
  - `UserRepository` Protocol에 `list_all()`·`set_active(user_id, is_active=…)`를 추가하고
    in-memory 구현을 붙였다. 목록은 `(created_at, id)` 순이다.
  - `UserService.list_users()`·`deactivate_user(user_id)`를 추가했다. 후자는 미존재
    `UserNotFound`, 마지막 활성 관리자 `LastActiveAdmin`을 던진다.
  - `_is_last_active_admin`은 **활성 관리자 population**을 본다 — 자기 자신 제외 후 활성
    관리자가 0이면 거부다.
- `services/application/app/auth/users_mongo.py`
  - `list_all()`은 `find({}).sort("created_at", ASCENDING)`으로 **서버측 정렬**한다.
  - `set_active()`는 `find_one_and_update(..., return_document=AFTER)`로 갱신 후 문서를 돌려준다.
- `services/application/app/main.py`
  - `require_admin_user`(하위 dependency로 인증) + `_REQUIRE_ADMIN` 두 겹 배선. 소유권과 같은 형태다.
  - `_admin(...)` 선언 헬퍼(403 additive). `_owned`와 상태코드는 같지만 **의미가 달라** 별도
    헬퍼로 뒀다 — 하나로 합치면 선언 가드가 "어느 경계 뒤인지"를 말할 수 없다.
  - endpoint 3종: `GET /admin/users` · `POST /admin/users`(409/400) ·
    `POST /admin/users/{user_id}/deactivate`(404/409).
  - `AdminUserPayload`는 `id`·`username`·`is_admin`·`is_active`만 싣는다.
- **전수 가드 편입** — 새 tier가 기존 가드 3개를 정확히 깨뜨렸고(설계대로), 계약을 의도적으로 넓혔다.
  - `ProjectAuthorizationTest`: "403 선언 ⟺ project-scoped"를 "403 ⟺ project-scoped **또는**
    관리자"로 넓혔다. dependency 쪽 ⟺ `{project_id}`는 **그대로 정확**하고, "관리자 route는
    절대 project-scoped가 아니다"를 함께 단정한다.
  - `CombinedBoundaryMatrixTest`: tier가 넷이 됐다(68 = public 4 + 인증 전용 2 + 관리자 3 +
    project 59). 결합 불변식에 **403의 생산자는 정확히 둘**과 **두 인가 dependency는 대안이지
    스택이 아니다**를 추가했다.
  - 관리자 tier 실동작 3셀: 비관리자 403 전수 · 관리자 통과 전수 · 안쪽 겹 격리 구동.
- 회귀: `AdminUserApiTest` 8건(목록·해시 부재·생성·중복 409·빈 입력 400·세션 즉시 사망·미존재
  404·마지막 관리자 409·2인 시 해제·비활성 관리자는 생존자로 세지 않음),
  `ListAndDeactivateTest` 9건(서비스 계층), Mongo fake-collection 4건.
- `tests/test_application_api.py`에 `AdminErrorContractDeclarationTest`(H3 여섯 번째 트랙)를 추가했다.
- `frontend/src/api/schema.d.ts`를 재생성해 3개 operation을 additive 반영했다(화면은 5-d).

### Issues found

#### 뮤테이션 N5 — 핸들러가 해시를 넣어도 통과한다(결함 아님)

- 증상: `_admin_user_payload`에 `password_hash`를 추가하는 뮤테이션이 **통과**했다.
- 원인: `response_model=AdminUserPayload`가 모델에 없는 필드를 구조적으로 걸러낸다. 즉 해시는
  애초에 wire에 닿지 않으므로 이 뮤테이션은 결함이 아니다.
- 확인: 실제로 누출되는 두 구성은 **모두 회귀가 문다** — N5b(response_model 제거 + 핸들러 누출)
  → `test_list_returns_every_account_and_never_a_password_hash` 실패, N5c(모델 자체에 필드 추가)
  → 같은 테스트 + 생성 응답 exact 비교 실패.
- 결과: 보호하는 겹은 **wire model**이고 그것이 양방향으로 잠겨 있음을 실측으로 확인했다.
  D8-3c의 "두 겹 중 한 겹" 상황과 같은 구조이며, 여기서는 추가 셀이 필요하지 않다.

#### 뮤테이션 루프 타임아웃이 소스를 오염시킬 뻔했다

- 증상: 5종 뮤테이션 루프가 N4 도중 2분 제한에 걸려 종료됐고, **원복 `cp`가 실행되지 않았다.**
  같은 시각 백그라운드 전량 회귀가 돌고 있어 뮤테이트된 소스를 수집했을 수 있다.
- 조치: 즉시 원복하고 `git diff --stat`으로 무변을 확인한 뒤, 그 전량 회귀를 **폐기**하고
  깨끗한 트리에서 다시 돌렸다. 남은 뮤테이션은 `-k`로 좁혀 개별 실행했다.
- 교훈: 뮤테이션과 전량 회귀를 **동시에 돌리지 않는다** — 수집 시점이 겹치면 결과가 무의미하다.

### Decisions

- **오너 결정 F1=C(감사 남기는 impersonation)** — 추천은 A(예외 없음)였으나 오너가 C를 골랐다.
  관리자는 기본 상태에서 타인 project에 접근하지 못하고, **감사 기록을 남기고 만료되는 승격**을
  통해서만 접근한다. "관리자가 조용히 볼 수 있다"는 상태를 만들지 않으면서 지원 시나리오는
  기록을 대가로 지원하겠다는 판단이다. 이 슬라이스(5-a)는 승격을 구현하지 않으며, 소유권 403은
  관리자에게도 그대로 적용된다.
- **오너 결정 F2=A(마지막 활성 관리자 비활성화 금지)** — 락아웃 복구 경로가 컨테이너 exec뿐이라
  검사 한 줄이 훨씬 싸다는 추천을 그대로 채택했다.
- F1=C에 **의존하는 5-b·5-d는 착수하지 않았다.** C가 새로 여는 하위 결정(승격 수명·범위, 승격
  아래 쓰기 허용 여부, 감사 대상이 발급인지 개별 요청인지, 사용자 통지 여부)이 남아 있고,
  추측 구현은 보안 경계를 임의로 정하는 일이다. 5-a는 그 어느 것에도 의존하지 않는다.
- 재활성화(reactivate)는 만들지 않았다. D6=A가 "목록·생성·비활성화"만 열거하며, 지금 추가하면
  트리거 없는 예방 구현이다. **비활성화가 단방향 문이라는 점은 5-d 화면 착수 시 재검토할 항목이다.**
- 관리자 목록에 `created_at`을 넣지 않았다. 필요해지면 additive이며 지금은 소비자가 없다.

### Verification

- `tests/test_auth_api.py` `53 passed / 707 subtests`.
- `tests/test_auth_users.py`+`test_auth_users_mongo.py` `33 passed`.
- 계약·인증 4개 모듈 합산 `209 passed / 1102 subtests`.
- 뮤테이션: N1(관리자 검사 무력화)·N2(마지막 관리자 가드 제거)·N3(활성 여부 무시)·N4(route가
  관리자 dependency 상실)이 각각 해당 셀에서 실패. N5/N5b/N5c는 위 "Issues found" 참조.
- 프론트: `gen:api` 재생성, `tsc --noEmit` 통과, build 성공(진입 404.87 kB · 관측 lazy 385.71 kB로
  기존과 동일), `217 passed / 14 files`.
- 백엔드 전량(test-mongo ON): `1681 passed / 1 skipped / 1455 subtests` (664s).
  종전 기준선 `1653 / 1 / 1418`에서 신규 28 테스트·37 subtest만 늘었고 기존 실패·skip 변동 없음.
  이 실행은 뮤테이션이 모두 원복된 뒤 시작한 것이며, 겹쳤던 앞선 실행은 폐기했다.

### Next steps

- **F1=C 하위 결정이 5-b·5-d의 착수 차단**이다: 승격의 수명·범위, 승격 아래 쓰기 허용 여부,
  감사 대상(발급 vs 개별 요청), 사용자 통지 여부. 브리프 §7에 정리해 오너 결정을 받는다.
- 5-c(전역 관측 KPI)는 F1과 무관하므로 먼저 진행할 수 있다 — 감사 저장소에 전역 조회를 더하고
  기존 집계 함수를 재사용하되, 오독 방어 3종이 전역에서도 성립해야 한다.
- 이후 D8-6 영구 삭제, D8-7 Mongo·ES 인프라 인증.

### 독립 검증 후속 보강 (D8-5a, 같은 슬라이스)

독립 검증 `docs/verifications/2026-07-28/auth_d8_5a_admin_boundary.md`는 **합격(차단 0건)**이었고
비차단 3건을 남겼다. 코드 변경은 없고(검증이 요구하지 않았다) **기록 정확성과 결정 항목 승격**만
처리했다.

- **D8-3c 검증 기록에 구현자 추기를 달았다.** 그 기록은 커밋 전 작업 트리를 기술하는데, 구현자가
  기록의 H-a 지적을 받아 **커밋 전에** 소유권 inner 셀을 `inspect.signature` 구조 결합에서
  probe-app 행위 잠금으로 교체했다. 즉 기록의 H-a 서술과 커밋 `3b99c80`의 코드가 한 셀에서
  다르다. 검증자 본문·판정은 손대지 않고 **구현자 작성임을 명시한 별도 절**로 덧붙여, 이 기록만
  읽는 사람이 코드와 대조하다 혼란을 겪지 않게 했다("정본과 코드가 맞고 이 기록이 더 이른 시점").
- **H-c를 브리프 §7의 결정 항목 C-6으로 승격했다.** `POST /admin/users`는 관리자가 초기
  비밀번호를 평문으로 지정하므로 **관리자가 사용자 비밀번호를 아는 상태**가 남는다. 지금은
  `scripts/create_user.py`와 같은 계약이고 전달 채널이 없어 합리적이지만, 비차단 지적을 검증
  기록에만 두면 5-d 화면 작업 때 아무도 다시 보지 않는다. 구현자 의견은 **최초 로그인 시 변경
  강제**(채널 없이 얻을 수 있는 가장 큰 개선)이며, 같은 항목에 **비밀번호 정책 부재**(현재
  `create_user`는 빈 문자열만 거부)를 함께 적었다.
- **H-b(test-mongo OFF 보조 기준선)를 실측했다** — 검증자는 ON만 재현했고 OFF는 D8-3c 시점
  값이 남아 있었다. 실측 결과 `1593 passed / 89 skipped / 1455 subtests`(211s)이며 ON 실행과 passed+skipped=1682로 일치한다. HANDOFF 기준선 줄을 이 값으로 갱신했다.

코드·공개 계약 무변이므로 전량 회귀 재실행은 하지 않았다(검증자가 `fb88754`에서 ON 기준선
`1681/1/1455`를 이미 독립 재현했고, 이 보강은 문서 전용이다).

---

## Task — 인증 D8-5c 전역 관측 KPI (`GET /admin/observability/kpi`)

### Goals

- 앞 슬라이스가 "F1과 무관해 먼저 진행 가능"으로 남긴 5-c를 착수한다.
- 감사 저장소에 전역 조회를 더하고, 집계 함수는 **입력만 넓혀 재사용**한다(두 번째 구현 금지).
- 집계 계약이 방어하는 **오독 3종**(분모 동반 · 표본 0이면 `null` · `multi_call_correlations`≠
  repair 수)이 전역에서도 성립하는지를 *가정하지 않고* 넓힌 입력으로 직접 구동해 확인한다.
- 관리자 tier의 네 번째 operation으로서 기존 전수 가드(boundary matrix · H3 lock list)에 편입한다.

### Completed work

- **집계(`services/application/app/observability/kpi.py`)**
  - `aggregate_kpi`와 새 `aggregate_global_kpi`가 공용 `_fold(calls, loop_runs)`를 쓴다.
    `totals`·`sites`·`gate`·`loop` 계산이 **한 코드 경로**이므로 오독 방어 3종이 전역에서
    구성상 성립한다(같은 규칙을 두 번 적어 놓고 동기화하는 구조를 만들지 않았다).
  - `GlobalObservabilityKpi`는 `project_id` 대신 `projects_considered`를 싣는다 — 레코드를
    하나라도 남긴 project 수. 레코드가 없는 project는 세지 않는다(그 아래 per-call 수치의
    출처가 흐려진다).
  - **`_rows_per_correlation`의 버킷 키를 `(project_id, correlation_id)`로 바꿨다.** 아래
    "Issues found" 참조 — 전역에서만 드러나는 오집계다. per-project 결과는 불변이다.
- **저장소 — 전역 조회 추가**
  - `LlmCallAuditRepository`/`WritingLoopAuditRepository` Protocol + in-memory + Mongo에
    `list_all()`, 서비스에 `list_all_calls()`/`list_all_runs()`.
  - **nullable `project_id`가 아니라 별도 메서드**로 했다. `list_for_project(None)`이 전
    project를 반환하는 형태였다면 None이 실수로 흘러 들어가는 순간 조용히 경계를 넘는다.
  - Mongo 두 컬렉션에 `created_at` 단독 index를 더했다(`*_by_created`). 기존 복합
    `(project_id, created_at)` index는 project 없는 정렬을 태우지 못하고, 미색인 정렬은
    컬렉션이 커지면 32MB sort buffer 초과로 **실패**한다.
  - loop 감사도 전역 조회를 받는다. 빈 목록을 넘겨 `loop`를 채우면 `runs_considered=0`이
    되는데, 계약이 그 값을 "잰 적 없음"으로 정의하므로 rollup이 켜진 배포에서 거짓이 된다.
- **endpoint(`main.py`)**
  - `GET /admin/observability/kpi`, `responses=_ERRORS_ADMIN`(401·403·503),
    `dependencies=_REQUIRE_ADMIN`. per-project read-out과 달리 **404를 선언하지 않는다** —
    해석하는 project가 없으므로 없을 것도 없다.
  - `AdminObservabilityKpiResponse`는 별도 model이다. 한 model로 합치면 항상 존재하는
    `project_id`를 nullable로 만들어야 하고, 그 순간 per-project 계약이 느슨해진다.
    `sites` 행 타입(`ObservabilityKpiSitePayload`)은 두 응답이 **공유**한다.
- **회귀 신규 19 / subtest +13**
  - `GlobalAggregationTest` 8: 전 project fold · **같은 `correlation_id`가 두 project에 있으면
    한 워크플로가 아니다**(under-strict) · **같은 project 안의 2건은 여전히 센다**(over-strict) ·
    토큰 분모 · 표본 0 → null · 진짜 0.0 도달 · loop-only project도 분모에 포함 · 중복 미가산.
  - `AdminKpiEndpointTest` 5: payload 전 필드 · **관리자가 소유하지 않은 project의 레코드까지
    센다**(이 endpoint의 존재 이유) · 빈 배포 · 200 model `$ref` · site 행 타입 공유.
    이 클래스는 **override 없는 실 앱**을 구동한다 — `tests/auth_support.py`는 dependency 두
    개만 해석하고 `require_admin_user`는 거기 없으므로, 실 관리자 세션 외에는 들어갈 길이 없다.
  - 저장소 4건(in-memory·Mongo × 감사 2종): `list_all`이 project 경계를 넘고 정렬을 유지 ·
    빈 상태 · fake-collection 왕복 · index 2종 이름 고정.
- **문서**: 정본 `v1.7.57`(변경이력 + 본문 §"LLM 파이프라인 관측(KPI)"에 전역 read-out 조항과
  버킷 키 조항, §H3 403 행 `/admin/*` 3→4개), `CHANGELOG.md`, `HANDOFF.md`.

### Issues found

- **문제**: 전역 집계에서 `multi_call_correlations`가 일어나지 않은 repair를 셀 수 있었다.
  **원인**: 버킷 키가 `correlation_id` 단독이었다. 그 값은 호출자가 준 `request_id`·
  `idempotency_key`이므로 서로 다른 project가 **같은 문자열을 쓸 수 있다** — per-project
  집계에서는 모든 행이 이미 같은 project라 드러나지 않지만, 전역에서는 두 project의 1회
  호출이 한 워크플로 2건으로 접힌다. 계약이 방어하는 오독 3종 중 하나가 입력을 넓히는
  것만으로 스스로 무너지는 자리였다(브리프 §5의 "전역 KPI는 `project_id` 축을 잃지 않아야
  한다"가 가리키는 지점).
  **해결**: 키를 `(project_id, correlation_id)`로 바꾸고 양방향으로 잠갔다 — 두 project의
  같은 id는 별개(under-strict), 한 project 안의 2건은 여전히 1건의 multi-call(over-strict).
  **결과**: per-project 집계 결과는 비트 단위로 불변이고(모든 행이 같은 project), 전역에서만
  달라진다. 뮤테이션 2종으로 양방향 확인.
- **문제**: `/admin/observability/kpi`가 두 개의 exact-set lock list에 동시에 걸린다
  (`AdminErrorContractDeclarationTest`는 `/admin/` 접두, `KpiErrorContractDeclarationTest`는
  `/observability/` 포함으로 폐쇄를 주장한다).
  **원인**: 두 track의 폐쇄 가드가 경로 패턴으로 정의돼 있고 이 경로가 둘 다 만족한다.
  **해결**: 상태 집합이 관리자 계열(401·403·503)이므로 **관리자 track이 소유**하고, 관측
  track의 폐쇄 가드는 개별 나열이 아니라 **규칙**으로 `/admin/`을 제외한다. 새 관리자 관측
  endpoint가 생겨도 유지 대상이 늘지 않는다.
  **결과**: 한 operation을 두 exact-set이 소유해 서로 어긋나는 구조를 만들지 않았다.

### Decisions

- **per-project 분해는 전역 응답에 넣지 않았다.** 넣으면 관리자에게 project 식별자를 노출하게
  되는데, 그것은 5-b(전 프로젝트 목록)이고 F1=C의 하위 결정 C-1~C-5 뒤에 오는 슬라이스다.
  전역 KPI가 그 문을 먼저 열면 아직 정해지지 않은 경계를 구현자가 정하는 일이 된다.
  대신 `projects_considered`로 **project 축은 분모의 형태로만** 남겼다 — 이 절의 다른 반직관
  수치가 전부 분모를 동반하는 것과 같은 방식이고, 어떤 project도 이름 짓지 않는다.
- **전역 조회는 별도 메서드**(위 "Completed work" 참조). nullable 인자보다 한 줄 길지만,
  경계를 넘는 호출이 호출부에서 눈에 보인다.
- **오독 방어 3종을 "성립할 것"으로 두지 않고 전역 입력으로 다시 구동했다.** 셋 중 둘은
  코드 공유만으로 성립했지만 하나(`multi_call_correlations`)는 성립하지 않았고, 구동하지
  않았다면 green인 채로 틀린 숫자를 냈을 자리였다.

### Verification

- 뮤테이션 5종(전수 기재 — 각 뮤테이션은 해당 셀만 물었다):
  1. 버킷 키에서 project 제거 → 전역 2셀(`test_the_same_correlation_id_in_two_projects_is_not_one_workflow`
     + 과분할 셀) + endpoint payload 셀 실패.
  2. 버킷 키를 `(project, call_id)`로 과분할 → per-project `MultiCallCorrelationTest` 1셀 +
     per-project endpoint payload + 전역 over-strict 셀 실패.
  3. `_REQUIRE_ADMIN`을 `_REQUIRE_AUTH`로 교체 → boundary matrix 4셀 실패(tier 분할·결합
     불변식·비관리자 403 전수·소유권 선언 대조).
  4. endpoint가 `loop_runs=()` → 전역 payload 셀 실패.
  5. 관측 track 폐쇄 가드에서 `/admin/` 제외 규칙 제거 →
     `KpiErrorContractDeclarationTest::test_the_whole_observability_track_is_declared` 실패.
     이 규칙이 실제로 load-bearing임을 읽기가 아니라 구동으로 확인한 것이다.
- 프론트: `gen:api` 재생성(`schema.d.ts` +74줄, additive), `tsc --noEmit` 통과, build 성공
  (진입 404.87 kB · 관측 lazy 385.71 kB로 무변), `217 passed / 14 files`.
  (첫 vitest 실행에서 1건이 실패했으나 동일 커밋에서 두 번 재실행해 모두 217 통과 — 재현되지
  않는 flake이며 이 슬라이스의 변경은 `schema.d.ts` additive뿐이다.)
- 백엔드 전량(test-mongo ON): `1700 passed / 1 skipped / 1468 subtests` (870s).
  종전 기준선 `1681 / 1 / 1455` 대비 **+19 passed / +13 subtests**이고 설명되지 않는 증감은 0이다.
  - +19 = 이 슬라이스의 신규 테스트 함수 수와 정확히 일치(전역 집계 8 · 관리자 endpoint 5 ·
    저장소 6). 영향 모듈만 따로 재보아도 250→231(stash 전후)로 같은 델타다.
  - +13 = 새 operation 1개가 기존 전수 가드를 지나며 생긴 칸 11 + 신규 subTest 2.
    (인증 경계 3 · 소유권 선언 대조 1 · 결합 매트릭스 3 · 관리자 H3 lock list 4)

### Next steps

- **5-b·5-d는 여전히 오너 결정 대기**다(브리프 §7 C-1~C-6). 5-c는 그 결정에 의존하지 않으므로
  여기서 닫힌다.
- 이후 D8-6 영구 삭제, D8-7 Mongo·ES 인프라 인증.
- 관리자 화면(5-d)이 생기면 이 endpoint가 첫 소비자가 된다. 지금은 프론트 소비자가 없고
  `schema.d.ts`에 타입만 additive로 들어가 있다.

### 독립 검증 후속 보강 (D8-5c, 같은 슬라이스)

독립 검증 `docs/verifications/2026-07-28/auth_d8_5c_global_kpi.md`는 **합격(차단 0건)**이었고
비차단 3건을 남겼다. 검증자는 in-process 뮤테이션 탐침(실소스 무변)으로 버킷 키 양방향을 독립
재현했고, 전량 회귀 `1700 / 1 / 1468`과 delta 회계(신규 19)를 재도출해 주장과 일치시켰다.

- **H-1(기록 정확성) — 실제로는 내 기록이 틀렸고, 고치는 김에 다섯 번째를 구동했다.** work log에
  "뮤테이션 5종"이라 적고 4종만 상술했는데, 실제로 돌린 것도 4종이었다(검증자는 관측 track
  `/admin/` 제외 규칙 뮤테이션을 다섯 번째로 정합 해석해 카운트를 살려 줬지만, 그것은 검증자가
  **읽기로** 도출한 것이지 누가 구동한 것이 아니었다). 숫자를 4로 낮추는 대신 **그 다섯 번째를
  실제로 돌렸다** — 제외 규칙을 지우면
  `KpiErrorContractDeclarationTest::test_the_whole_observability_track_is_declared`가 실패한다.
  이제 "5종"이 사실이고 다섯 개가 전부 prose에 있으며, 검증자가 "읽기로 입증"이라고 적은 칸이
  구동으로 잠겼다.
- **H-2(미래 부채) — 가드를 추가하지 않고 이유를 코드에 적었다.** `projects_considered`가 `None`
  `project_id`를 한 project로 셀 수 있다는 지적은 맞지만, 그 입력은 **오늘 도달 불가능**하다:
  `StoredLlmCall.project_id`는 `str`이고 `correlation_id`만 `str | None`이며([`llm_call_audit.py:108`](services/application/app/observability/llm_call_audit.py#L108)·[`:113`](services/application/app/observability/llm_call_audit.py#L113)),
  Mongo 매퍼도 `doc["project_id"]`(없으면 KeyError)와 `doc.get("correlation_id")`(None 허용)로
  갈라져 있다([`llm_call_audit_mongo.py:68`](services/application/app/observability/llm_call_audit_mongo.py#L68)·[`:70`](services/application/app/observability/llm_call_audit_mongo.py#L70)).
  즉 **가드의 비대칭은 레코드 타입의 비대칭을 그대로 반영한 것**이고, 지금 가드를 넣으면 도달
  불가능한 시나리오의 에러 처리가 된다(작업 규칙 §2). 대신 `_rows_per_correlation` 주석에 그
  근거와 **"그 필드가 nullable이 되는 순간이 가드를 넣을 시점"**을 적어, 다음 독자가 같은 지적을
  다시 하거나 반대로 조용히 넘기지 않게 했다. 코드 동작 무변(주석만).
- **H-3(재현 불가 flake)**: 검증자도 vitest 217 passed로 재현하지 못했다. 기록은 이미 정확하므로
  조치 없음. 반복될 때만 추적한다.

동작 변경은 없다(주석 1개 + 문서). 영향 모듈 재실행 `tests/test_observability_kpi.py 38 passed /
15 subtests`로 확인했고, 검증자가 방금 `1700 / 1 / 1468`을 독립 재도출했으므로 전량 재실행은
하지 않았다.
