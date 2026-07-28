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
