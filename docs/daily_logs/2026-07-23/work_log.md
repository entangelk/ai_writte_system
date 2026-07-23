# 2026-07-23 작업 로그

## Task — H3 에러 응답 계약 S1: SoT 전역 HTTP 에러 계약 섹션 신설 (문서 전용, SoT v1.7.29)

### Goals

- 2026-07-22 세션이 남긴 "Next steps (다음 세션) — **S1 착수**"를 처리한다. 브리프 `plans/api-error-response-contract-decisions.md`(D1~D4=A, 독립 검증 조건부 합격 후 F1/F2/F3 정합화 완료)의 첫 슬라이스.
- 목표는 **정본 편집 하나**다: H1(성공 `response_model`, v1.6.95)·H2(입력 검증)가 남긴 **에러 응답**의 전역 의미론을 SoT "확정된 전역 계약"에 명문화하고, 503-migration 경계와 `start_next_unit` 500 누수 부채를 정본에 기록한다.
- **범위 밖(명시)**: endpoint별 `responses=` 선언은 S2부터. 런타임 동작·프론트 에러 UX·`reason` 코드는 이번 슬라이스에서 건드리지 않는다(D4=A/D1=A).

### Completed work

- **신규 섹션 `### HTTP 에러 응답 계약`** — [`docs/system-contract-sot.md`](../../system-contract-sot.md) "확정된 전역 계약"의 `추적성` 다음, `## 서비스별 계약 SoT` 앞.
  - **본문 형태(D1=A)**: 모든 에러 응답은 균일한 단일 키 `{"detail": <string>}`(`ErrorDetailResponse`, `writing/http_models.py:158`). 상태코드별 별도 에러 스키마 없음.
  - **3층 계약**: 상태코드=기계용 의미론 · `detail`=사람용 메시지 · (후속) `reason`=기계용 코드. **`detail` 문자열 자체는 계약이 아님**(클라이언트 패턴 매칭 금지). 기계 분기가 필요해지면 detail 파싱이 아니라 `reason`을 additive로 — D1=B가 스키마 파괴 없이 들어올 자리를 이 구조가 연다(브리프 Follow-up).
  - **422는 계약 밖**: FastAPI/Pydantic 자동 생성이라 본문이 `{"detail": [ …배열… ]}`로 형태부터 다르고 자동 문서화된다.
  - **자기발견성(D3=A)**: endpoint별 realistic 코드 집합은 **OpenAPI `responses=`가 기계적 진실**이고 SoT는 의미론만 고정한다(endpoint×코드 표를 SoT에 두면 61×N 이중 관리 drift). 검증은 `python3 scripts/dump_openapi.py` 재덤프 self-discovery.
  - **상태코드 의미론 표** 400/404/409/422/502/503/504 + 동적 `ProviderError` 매핑. 각 행의 "대표 원인"은 요약이 아니라 실코드에서 재도출한 예외 이름이다.
  - **503의 두 얼굴**: (1) 협력자 미구성(`"<X> is not configured"` — 배포 구성이 바뀌어야 함) (2) 저장 데이터 마이그레이션 필요(`DraftOrderIntegrityError` — 해결책은 `scripts/migrate_ordered_units.py`, 현재 방어 3곳). 공통 규칙 = "요청을 고쳐 성공시킬 수 없고 서버 측 조치가 선행돼야 하며, 그 전의 단순 재시도는 무의미".
  - **`InvalidDraftOrder` 의도적 비대칭 명문화**: reorder(`PUT …/draft-order`)는 서브클래스가 기존 `(Archived, InvalidDraftOrder)` 절에 잡혀 **409 유지**. 지금까지 이 비대칭은 07-22 work_log와 회귀에만 있었고 정본에는 없었다. (초안의 근거 문안["요청이 전체 순열을 실어 오므로 위반이 클라이언트 입력으로 판별된다"]은 입력 오류 face에만 성립해 **독립 검증 H-2로 교정**했다 — 아래 S2 task의 검증 반영 절.)
  - **알려진 결손 명문화**: `intent=start_next_unit` accept 경로의 500 누수(H3 S5에서 503으로 폐쇄 예정)를 "정본이 승인한 동작이 아니다"라고 못박았다.
- **버전 bump**: SoT `v1.7.28 → v1.7.29`, 최근 갱신일 `2026-07-23`, 변경 이력 행 추가.

### Issues found

- 없음(코드 결손 신규 발견 없음). 다만 **브리프의 실측 숫자를 그대로 옮기지 않고 재도출**했으며, 재도출 과정에서 `503×18`의 내부 분해가 브리프에 없다는 것을 확인해 SoT/이력에 **구성 15 + 무결성 3**으로 명시했다(아래 Verification).

### Decisions (구현자 판단)

- **SoT 섹션 배치 = "확정된 전역 계약" 안**(D3=A가 지시한 위치). `구현 기술 결정`의 "타입 계약 동기화의 실제 범위"(H1/H2 기록) 옆이 아니라 전역 계약에 둔 이유: H1/H2 항목은 *어디까지 타입화됐는가*라는 진행 상태 기술이고, 이번 것은 상태와 무관하게 항상 참인 **정책**이다. 대신 섹션 서두에 H1/H2 계보와 계기(07-22 500→503 수정의 검증 H-2)를 적어 두 곳을 잇는다.
- **`구현 기술 결정` 219행(H1/H2 서술)은 수정하지 않았다** — §3 수술적 변경. 그 문단은 성공 응답 타입화 범위를 기술하며 이번 변경으로 거짓이 되지 않는다.
- **버전 bump는 patch가 아니라 신규 계약 항목으로 기록**: "계약 버전 관리"가 정본 계약 항목 추가를 bump 사유로 규정하고, 브리프 슬라이스 표도 S1 산물을 "버전 bump"로 명시한다.

### Verification

문서 전용 슬라이스이므로 CLAUDE.md §4 "Documentation-only changes" 기준 — 링크·참조·수치·우선순위 주장을 확인했다. **브리프 요약을 인용하지 않고 1차 소스(`main.py`/`core_sot/service.py`)에서 재도출**했다.

- **참조 존재 확인**: `plans/api-error-response-contract-decisions.md`, `verifications/2026-07-22/h3_error_response_contract_plan.md`, `scripts/migrate_ordered_units.py`, `scripts/dump_openapi.py` 전부 존재. `ErrorDetailResponse`는 `writing/http_models.py:158`.
- **수치 재도출**(`services/application/app/main.py`): endpoint(`@app.`) **61**, `status_code=` 리터럴 404×**62** · 400×**30** · 502×**20** · 503×**18** · 409×**16** · 504×**7**, 동적 `status_code=status`×**9**. 브리프 F1 정정(502 리터럴 20 중 1건은 partial `JSONResponse`라 에러-raise는 19)과 일치.
- **503×18 분해**(브리프에 없던 축, SoT에 새로 명시): 협력자 미구성 **15**(context search 7 · writing 6[service/gate/report/revision/revise-and-gate/accept] · analysis runner 1 · compare judge 1[`CompareJudgeNotConfigured`, detail이 `str(exc)`라 문자열 grep으로는 안 잡힘]) + 데이터 무결성 **3**(`DraftOrderIntegrityError` — `main.py:1969` list_drafts · `2090` project export · `2136` create_draft). 15+3=18로 총계 일치. **행 번호는 S1 시점(S2 선언 추가 전) 기준**이며, S2 반영 후에는 각각 2012/2139/2186으로 밀린다(독립 검증 기록의 인용과 동일 지점).
- **`start_next_unit` 500 누수 직접 확인**: `_require_ordered_drafts` 호출부 5곳 중 하나가 `core_sot/service.py:737`(= `start_next_unit`, 712행 정의) 이고, `main.py`의 `DraftOrderIntegrityError` catch는 3곳(1965/2087/2133)뿐이며 `writing_accept_endpoint`(3885~)의 except 절에는 없다. `DraftOrderIntegrityError <: InvalidDraftOrder <: CoreSotError`이고 accept가 잡는 것은 `ValueError`·`NotFound`·`Archived`·`StaleWritingBase`·writing 계열이라 **어느 절에도 걸리지 않는다** → 500. 주장 성립.
- **런타임 무변**: `git status --porcelain`이 `M docs/system-contract-sot.md` 단 하나. 코드·OpenAPI·스키마 무변이므로 테스트/`gen:api` 재실행 대상 없음(에러 선언 추가는 S2부터).

### Next steps

- **S2 착수**(아래 Task에서 이어서 완료). 이후 S3(analysis) → S4(memory/source) → S5(writing 잔여 + `start_next_unit` 503 방어).
- 이번 슬라이스는 **오너 dogfood(GATE-1) 갈림길과 무관**하다 — 계약 정직성 작업이라 dogfood와 병행 가능하다.

## Task — H3 에러 응답 계약 S2: CRUD family 20 endpoint 에러 선언 (SoT v1.7.30)

### Goals

- S1이 정본화한 전역 의미론을 **첫 endpoint 집합**에 적용한다. 대상은 브리프 lock 리스트의 **20**(H1 spine 14 + CRUD 형제 6).
- 목표는 "런타임에는 정확히 반환되지만 공개 계약에는 없던" 404·409·400·503을 OpenAPI와 프론트 생성 타입에 나타나게 하는 것. **런타임 동작은 한 줄도 바꾸지 않는다**(D4=A).

### Completed work

- **`main.py` 에러 선언 상수 7종 신설**(spine 응답 모델 바로 위): `_ERROR = {"model": ErrorDetailResponse}`를 조립한 `_ERRORS_404` · `_ERRORS_400_404` · `_ERRORS_404_409` · `_ERRORS_400_404_409` · `_ERRORS_404_MIGRATION` · `_ERRORS_400_404_MIGRATION` · `_ERRORS_404_409_MIGRATION`. 20 endpoint를 7개 상수로 덮으므로 ad-hoc dict 20개가 생기지 않는다.
  - **`_MIGRATION_503`은 별도 description을 갖는다**: CRUD family의 503은 전부 데이터 무결성 얼굴(`DraftOrderIntegrityError`)이라 "`scripts/migrate_ordered_units.py`를 실행하라, 재시도만으로는 성공할 수 없다"를 선언에 적었다. 상태코드만 적어 두면 이 페이즈가 없애려는 "로그에서 유추" 갭이 그대로 남는다.
  - `ErrorDetailResponse`를 `writing/http_models`에서 import(기존 `ACCEPT_RESPONSES` import 옆). 새 에러 모델을 만들지 않고 **단일 모델 재사용**(D1=A).
- **18개 endpoint에 `responses=` 부착**. `POST /projects`·`GET /projects`는 도메인 에러가 없어 대상 아님(20행 lock 리스트 중 이 둘은 "—"/422 자동) → 선언은 18, lock 대상은 20.
- **회귀 신규 7건**(`tests/test_application_api.py`):
  - `CrudErrorContractDeclarationTest` 4건 — (a) 20 endpoint × 선언 상태 집합 **exact** 일치(subTest 20; under-strict=선언 누락, over-strict=안 던지는 코드 선언 양방향), (b) 선언된 모든 에러 본문이 `#/components/schemas/ErrorDetailResponse` 단일 참조(subTest 30), (c) migration 503 description이 운영 조치를 명시(subTest 3 — 검증 H-3 반영 후), (d) lock 리스트 길이 20 고정.
  - `CrudErrorBodyExactKeyTest` 4건 — 404/409/400/503의 **실제 wire 본문**이 정확히 `{detail}` 단일 키 + non-empty string. 선언이 정직하려면 본문이 그래야 하고, 후속 `reason` 필드(D1=B)는 drift가 아니라 명시 결정으로만 들어와야 한다.

### Issues found

- 없음. 착수 전 브리프의 S2 코드 맵(20행)을 `main.py`에서 **재도출**했고 전 행이 실코드와 일치했다(브리프 독립 검증 결과와도 일치).

### Decisions (구현자 판단)

- **선언 대상에서 422 제외**: FastAPI가 자동 문서화하고 본문 형태(`{"detail": [ … ]}`)가 다르다 — S1이 정본에 못박은 경계를 그대로 따랐다.
- **`responses=` 상수를 `main.py`에 두고 `writing/http_models.py`로 옮기지 않았다**: 후자는 writing 도메인 모듈이고 CRUD 계열이 거기 의존을 늘릴 이유가 없다. 공유하는 것은 `ErrorDetailResponse` 하나뿐이며 이미 그쪽이 정의처다.
- **503 description만 개별화**: 나머지 코드는 전역 의미론(SoT 표)으로 충분하고 endpoint마다 문장을 쓰면 SoT와 이중 관리가 된다. 503은 "서버 측 조치 선행"이라 **어떤 조치인지**가 없으면 실행 불가능한 정보라 예외.

### Verification

- **OpenAPI self-discovery**: `create_app().openapi()`를 재덤프해 20 endpoint의 선언 집합(200/422 제외)이 기대와 정확히 일치함을 확인(mismatch 0). 코드가 emit할 의도가 아니라 실제 스펙을 읽었다.
- **mutation 3종 실증(양방향)**:
  - project-export 선언에서 503 제거 → `test_migration_503_description_names_the_operator_action` SUBFAIL(under-strict).
  - `_ERRORS_404`에 아무도 안 던지는 502 추가 → `test_declared_error_statuses_match_the_lock_list` SUBFAIL(over-strict).
  - `_MIGRATION_503`의 모델을 다른 모델로 교체 → `test_every_declared_error_body_is_the_uniform_detail_model`이 503 3곳에서 SUBFAIL.
- **런타임 불변**: backend 전체 **1379 passed / 41 skipped / 384 subtests**(`CORE_SOT_TEST_MONGO_URI=mongodb://localhost:27018`). 기존 상태코드 회귀(`LegacyOrderedDraftMigration503Test`의 503 3종·reorder 409 유지 포함) 전부 green.
- **프론트 타입**: `npm run gen:api` → `schema.d.ts` **+270행 / -0행**(순수 additive), `npx tsc --noEmit` clean, `npm run build` 성공(JS 399.03 kB), frontend **194 passed / 13 files**(프론트 소스 무변).
- **변경 표면**: `main.py`(선언만), `tests/test_application_api.py`, `schema.d.ts`(생성물), SoT/HANDOFF/work_log. 서비스 로직·프론트 소스 0줄.

### 오너 독립 검증 PASS + 비차단 hardening 반영

- **오너 독립 검증 합격(조건 없음)**: `docs/verifications/2026-07-23/h3_error_response_contract_s1_s2.md`. 경계 매트릭스 빈 cell 없음. 검증자가 **18 endpoint 선언 == 실제 raise 집합을 endpoint 본문 직독으로 양방향 재확인**했고(테스트는 OpenAPI==EXPECTED만 pin하므로 EXPECTED 자체의 정확성은 코드 직독이 authority), 503×18의 15+3 분해·`InvalidDraftOrder` 비대칭 실재·`start_next_unit` 500 누수 실재·SoT 동기부여 수치 7종·런타임 무변 수치를 전부 1차 소스에서 재도출해 성립을 확인했다.
- **H-1(문서 오기) 반영**: body-model 테스트 subTest 수를 27→**30**으로 정정(총 52는 정확했다). 실측 재확인: 선언 exact 20 + body-model 30 + migration description 3 = **53**(H-3 반영 후).
- **H-2(근거 정밀도) 반영 — SoT 문안 교체**: reorder 비대칭의 원 근거("위반이 클라이언트가 보낸 순열로 판별")는 **입력 오류 face에만** 성립한다. `reorder_drafts`는 `_require_ordered_drafts(current)`를 **순열 검사보다 먼저** 호출하므로([core_sot/service.py:504](../../../services/application/app/core_sot/service.py#L504)) legacy 데이터에서는 입력과 무관하게 무결성 에러가 먼저 발생하고 기존 절에 흡수되어 409가 된다. SoT 문안을 "reorder의 409는 입력 오류 face에 대해서만 정확한 의미론이고, 무결성 face에서는 07-22 수정이 500 누수만 닫는 수술적 범위를 지킨 **무변경의 결과**이며, 503 재분류는 별도 개정 사항"으로 좁혔다. **행동·선언은 원래 정확했고 바뀌지 않았다** — 다음 검증자의 오독을 막는 근거 문안 교정이다.
- **H-3(테스트 보강) 반영**: migration description subTest가 list/export 2곳만 직접 pin하고 create는 같은 상수를 쓴다는 이유로 간접 검증이었다. `(path, method)` 쌍으로 바꿔 **`POST …/drafts`를 3번째로 직접 pin**했다(subTest 2→3). 상수 공유는 구현 세부이지 계약이 아니므로, 계약이 요구하는 3곳은 3곳 다 명시적으로 잠근다.
- **H-4(구조 관찰)**: 조치 없음. "EXPECTED == 실제 raise"를 AST로 자동 대조하는 것은 현재 20 endpoint 규모에서 과설계이고(§2), 검증자도 "현재 충분"으로 판단했다. S3~S5로 대상이 늘어 직독 대조 비용이 커지면 그때 재평가한다.

### Next steps

- **S3(analysis 트랙)**: analysis jobs/candidates/context/compare/apply/review-queue/review-inbox/gate-findings. S2와 달리 **동적 `ProviderError` 매핑 지점이 섞여** 있어 endpoint별 realistic 집합만 선언하고 전체 열거는 하지 않는다(브리프 스코프 밖 명시).
- 이후 S4(memory/source) → S5(writing 잔여 + `start_next_unit` 503 방어 = SoT v1.7.29가 "알려진 결손"으로 기록한 500 누수 폐쇄).
- **주의**: S3 이후 구역은 `response_model`이 없는 무타입 endpoint가 많다(`dict[str, object]`). 에러 선언은 성공 모델과 독립이므로 `response_model` 부착을 함께 하려는 유혹을 피할 것 — 그건 H1의 잔여 범위이고, 섞으면 silent field loss 위험(§v1.6.95)이 이 페이즈로 들어온다.
