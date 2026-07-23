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
  - **`InvalidDraftOrder` 의도적 비대칭 명문화**: reorder(`PUT …/draft-order`)는 서브클래스가 기존 `(Archived, InvalidDraftOrder)` 절에 잡혀 **409 유지**. 지금까지 이 비대칭은 07-22 work_log와 회귀에만 있었고 정본에는 없었다. (초안의 근거 문안["요청이 전체 순열을 실어 오므로 위반이 클라이언트 입력으로 판별된다"]은 입력 오류 face에만 성립해 **독립 검증 H-2로 교정**했다 — `reorder_drafts`도 `_require_ordered_drafts`를 순열 검사보다 먼저 호출하므로 legacy 데이터에서는 입력과 무관하게 무결성 에러가 먼저 발화한다. 검증 기록 `docs/verifications/2026-07-23/h3_error_response_contract_s1_s2.md`.)
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

- **S2 착수**(다음 슬라이스, 별도 커밋): CRUD family **20** endpoint에 realistic `responses=` 선언. 이후 S3(analysis) → S4(memory/source) → S5(writing 잔여 + `start_next_unit` 503 방어).
- 이번 슬라이스는 **오너 dogfood(GATE-1) 갈림길과 무관**하다 — 계약 정직성 작업이라 dogfood와 병행 가능하다.
