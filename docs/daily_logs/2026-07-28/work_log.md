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
