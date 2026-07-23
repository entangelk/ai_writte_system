# 검증 기록 — H3 에러 응답 계약 S1·S2 (SoT v1.7.29 / v1.7.30)

## Subject metadata

- **날짜**: 2026-07-23
- **요청자**: 오너("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?")
- **검증자**: 독립 검증자(Claude, 본 슬라이스 구현 무관)
- **대상 슬라이스**: H3 에러 응답 계약 **S1**(SoT 전역 HTTP 에러 계약 섹션, v1.7.29, 문서 전용) + **S2**(CRUD family 20 endpoint 에러 선언, v1.7.30, 런타임 0줄 변경)
- **정본 계약 참조**: `docs/plans/api-error-response-contract-decisions.md`(D1~D4=A 확정 + S2 lock 리스트 20행 + 슬라이스별 검증 방법), `docs/system-contract-sot.md` "HTTP 에러 응답 계약" 섹션
- **작업 소스**: working tree, **uncommitted**(작업자가 커밋 요청 없음으로 보류). `git diff HEAD` 기준 6파일: `main.py`·`test_application_api.py`·`schema.d.ts`·`system-contract-sot.md`·`HANDOFF.md`·`CHANGELOG.md`
- **선결 검증**: `docs/verifications/2026-07-22/h3_error_response_contract_plan.md`(브리프 조건부 합격, F1/F2/F3 정정 반영 완료)

## Scope (정본 계약 범위)

브리프 `api-error-response-contract-decisions.md`에서 H3 S1/S2가 담당하는 표면으로 한정:

1. **S1 정본 문서**: SoT "HTTP 에러 응답 계약" 섹션 — 본문 형태(D1=A 균일 `{detail}`), 3층 계약(상태/detail/reason), detail 비계약화, 422 계약 밖, D3=A(OpenAPI=기계적 진실/SoT=의미론), 상태코드 의미론 표, 503 두 얼굴, `InvalidDraftOrder` 비대칭, `start_next_unit` 500 누수 결손.
2. **S2 구현 선언**: 브리프 lock 리스트 20 endpoint의 `responses=` 선언 — `main.py` 공유 상수 7종 + 단일 `ErrorDetailResponse` 참조 + 503 migration description.
3. **S2 회귀 테스트**: `tests/test_application_api.py::CrudErrorContractDeclarationTest`(3건) + `CrudErrorBodyExactKeyTest`(4건).
4. **계약 일관성**: 정본 ↔ 구현 ↔ 테스트 ↔ 생성 타입(`schema.d.ts`)의 정합성.
5. **런타임 불변**: 상태코드·detail·분기·서비스 경로 무변경(D4=A).

스코프 밖(명시): S3(analysis) 이후 구역, 프론트 에러 UX, `reason` 코드, 동적 ProviderError 전체 열거 — 본 검증도 이 범위를 넘지 않는다.

## Methodology

"코드가 emit할 의도"가 아니라 1차 소스를 재검증했다. 작업자 주장은 전부 거짓 전제(가설)로 취급해 반박을 시도했다.

- **정본 읽기**: 브리프 전문(157행) + SoT 신규 섹션 diff + `CHANGELOG`/`HANDOFF` diff.
- **endpoint 본문 인라인 검증**: `main.py` 18개 선언 endpoint의 try/except 본문을 직독하여 **실제 raise 집합 == 선언 집합**을 양방향(under-strict: 누락 / over-strict: 허위 선언)으로 확인. 테스트가 OpenAPI==EXPECTED만 pin하므로 EXPECTED==실제 raise는 본 검증자가 직접 채웠다.
- **예외 계층 추적**: `core_sot/service.py`에서 `CoreSotError`/`NotFound`/`Archived`/`InvalidDraftOrder`/`DraftOrderIntegrityError` 계층과 `_require_ordered_drafts`·`reorder_drafts`·`start_next_unit` 호출부 추적. 비대칭·500 누수 주장을 정본 주장이 아닌 코드에서 재도출.
- **수치 재도출**: `grep -cE 'status_code=<code>'`로 SoT 동기부여 수치(404×62 등)를 교차검증(거짓 수치 방어).
- **OpenAPI self-discovery**: `create_app().openapi()`를 독립 덤프해 20 endpoint 선언 집합을 EXPECTED와 대照하고 CRUD family에 누락 endpoint가 없는지 전수 조사.
- **실행 검증**(host, 컨테이너 불필요):
  - 신규 7건: `PYTHONPATH=. python3 -m pytest tests/test_application_api.py::CrudErrorContractDeclarationTest tests/test_application_api.py::CrudErrorBodyExactKeyTest -v`
  - 백엔드 전체: `CORE_SOT_TEST_MONGO_URI=mongodb://localhost:27018 PYTHONPATH=. python3 -m pytest tests/ -q`
  - 프론트: `npm run gen:api`(drift) · `npx tsc --noEmit` · `npm run test` · `npm run build`
  - `PYTHONPATH=. python3 scripts/dump_openapi.py`(브리프 지정 검증 명령)

환경 비고: application 컨테이너 down, frontend Restarting이나 본 슬라이스는 LLM 미사용이라 host-side 검증으로 충분. mongo `agent-memory-mongodb`(`:27018`)는 OPEN 확인.

## Findings

### F-S1.1 SoT 전역 에러 계약 섹션 — 정본 계약 대 일치

브리프 D1~D4=A가 요구하는 모든 정책 문안이 SoT에 누락 없이 명문화됐다.

| 계약 요구(브리프) | SoT 반영 | 검증 |
|---|---|---|
| D1=A 균일 `{detail}` 본문 | "균일한 단일 키 `{"detail": <string>}`" | `ErrorDetailResponse{detail:str}` 단일 모델(`writing/http_models.py:158`)로 확인 |
| detail 비계약화(패턴매칭 금지) | "`detail` 문자열 자체는 계약이 아니다" | 명시됨 |
| 3층(상태/detail/reason) | 상태=기계용·detail=사람용·후속 reason=기계용 | reason은 additive 자리로만 명시(D1=B 미도입, 정확) |
| 422 계약 밖 | FastAPI 자동, 본문 `{"detail":[…]}` 형태 상이 | 선언·테스트 모두 422 제외(아래 F-S2.2) |
| D3=A OpenAPI=기계적 진실 | "endpoint별 코드 집합은 OpenAPI가 기계적 진실… 중복 유지하지 않는다" | endpoint×코드 표가 SoT에 없음 확인(drift 방지 충족) |

상태코드 의미론 표의 "대표 원인(실코드)" 열이 요약이 아니라 실제 예외명임을 확인했다(예: 400=`ValueError`/`CoreSotError`/`UnsupportedExportFormat`/`InvalidContextSearchRequest`, 502=`ContextSearchFailed`/`InvalidWritingGateResult` 계열 등).

### F-S1.2 수치 재도출 — 브리프 인용 아닌 실코드에서 정확

작업자가 "브리프 요약을 인용하지 않고 재도출했다"는 주장을 독립 교차검증(`grep -cE 'status_code=<code>\b' main.py`):

| 코드 | SoT 주장 | 실측 | |
---|---|---|---
| 404 | 62 | 62 | ✅ |
| 400 | 30 | 30 | ✅ |
| 502 | 20(19 raise + 1 partial) | 20(1건 `JSONResponse`) | ✅ |
| 503 | 18(구성 15 + 무결성 3) | 18(3건 `DraftOrderIntegrityError` catch) | ✅ |
| 409 | 16 | 16 | ✅ |
| 504 | 7 | 7 | ✅ |
| 동적 `status_code=status` | 9 | 9 | ✅ |

503×18의 **내부 분해(브리프에 없던 축, 이번에 신설)**: 무결성 3 = `main.py:2012`(`list_drafts`)·`2139`(`export_project`)·`2186`(`create_draft`)의 `except DraftOrderIntegrityError` — 정확히 3건. 나머지 15 = app-wide `"is not configured"` 패턴 15건과 일치. 15+3=18 성립. 거짓 수치 없음.

### F-S1.3 `InvalidDraftOrder` 비대칭 — 실재(코드로 확인)

예외 계층: `DraftOrderIntegrityError <: InvalidDraftOrder <: CoreSotError <: ValueError`(`service.py:46/70/74`).

- `list_drafts`/`create_draft`/`export_project`는 `except DraftOrderIntegrityError`로 **503**.
- `put_draft_order`(reorder, `main.py:2209`)는 `except (Archived, InvalidDraftOrder)` → **409**. `DraftOrderIntegrityError`가 `InvalidDraftOrder` 서브클래스이므로 동일 무결성 에러도 409로 수렴.
- 성립 확인: `reorder_drafts`(`service.py:497`)가 `_require_ordered_drafts`(동 메서드, line 504)를 호출해 legacy 데이터에서 `DraftOrderIntegrityError`를 던질 수 있고, 이것이 reorder의 `(Archived, InvalidDraftOrder)` 절에 잡혀 409가 됨.

행동적 사실(reorder → legacy에서도 409)은 정확히 문서화됐고 선언 `{404,409}`는 실제 반환과 일치. (근거 문안의 정밀도는 이슈 H-2에서 별도 취급.)

### F-S1.4 `start_next_unit` 500 누수 — 실재(코드로 확인)

- `CoreSotService.start_next_unit`(`service.py:712`)가 line 736-737에서 `_require_ordered_drafts(drafts)` 호출 → legacy 데이터에서 `DraftOrderIntegrityError`.
- `writing_accept_endpoint`(`main.py:3937`)의 두 번째 try 블록(`writing_accept.accept(...)` 호출, 4007-4041) except 절: `NotFound`/`(Archived, StaleWritingBase)`/`(WritingAcceptError, WritingGateError, InvalidContextSearchRequest)`/`InvalidWritingGateResult`/`WritingAcceptAnalysisError`/`ContextSearchBudgetExceeded`/`ContextSearchFailed`/`ProviderError`. **`DraftOrderIntegrityError`(또는 `CoreSotError`/`ValueError`) 절 없음**.
- `DraftOrderIntegrityError <: CoreSotError <: ValueError`이나 첫 번째 try의 `except ValueError`(3958)는 parsing 블록 한정이라 accept 호출을 안 감싼다 → 매칭 절 없음 → **500 누수 성립**.

SoT가 이를 "알려진 결손… 본 정본이 승인한 동작이 아니다, H3 S5에서 폐쇄"로 못박은 것은 정확. 브리프도 동일(scope-out 예외로 S5 방어 수정 명시, line 39/142).

### F-S2.1 18 endpoint 선언 == 실제 raise 집합(양방향, 본 검증자 직독)

테스트는 OpenAPI==EXPECTED만 pin하므로, EXPECTED dict 각 항목이 실제 raise와 일치하는지 endpoint 본문을 직접 읽어 확인. **전 18행 정합**(요약):

| endpoint | 선언 | 실제 raise 절 | |
|---|---|---|---|
| `GET /projects/{id}` | {404} | NotFound | ✅ |
| `PATCH /projects/{id}` | {404,409} | NotFound, Archived | ✅ |
| `DELETE /projects/{id}` | {404} | NotFound(idempotent archive) | ✅ |
| `GET/PUT .../brief`, brief versions×2 | {404}/{404,409}/{404}×2 | NotFound (+Archived+StaleProjectBriefBase for PUT) | ✅ |
| `GET .../drafts` | {404,503} | NotFound, DraftOrderIntegrityError | ✅ |
| `POST .../drafts` | {404,409,503} | NotFound, DraftOrderIntegrityError, Archived | ✅ |
| `GET/PATCH/DELETE .../drafts/{id}` | {404}/{404,409}/{404} | NotFound (+Archived for PATCH) | ✅ |
| draft versions list/detail/export/save | {404}/{404}/{400,404}/{400,404,409} | 각 본문 절과 일치 | ✅ |
| `GET .../export`(project) | {400,404,503} | UnsupportedExportFormat, NotFound, DraftOrderIntegrityError | ✅ |
| `PUT .../draft-order` | {404,409} | NotFound, (Archived, InvalidDraftOrder) | ✅ |

over-strict(안 던지는 코드 선언)·under-strict(실제 raise 누락) 어느 쪽도 발견 안 됨. except 절 순서도 올바름(`create_draft`: NotFound→DraftOrderIntegrityError→Archived 순, 서브클래스가 선행 명시 catch되어 축소 없음).

### F-S2.2 422 제외·단일 모델·migration description — 정확

- `POST /projects`·`GET /projects`는 도메인 에러 0 → 선언 대상 아님(EXPECTED에서도 `set()`). 422는 FastAPI 자동이라 어느 endpoint에도 `_ERRORS_*`에 포함 안 됨.
- 7개 상수(`_ERRORS_404`/`_400_404`/`_404_409`/`_400_404_409`/`_404_MIGRATION`/`_400_404_MIGRATION`/`_404_409_MIGRATION`)는 전부 `_ERROR={"model": ErrorDetailResponse}` 또는 `_MIGRATION_503`을 조립 → **단일 모델 참조**(D1=A). 새 에러 모델 0개.
- `_MIGRATION_503`의 description이 `"Run scripts/migrate_ordered_units.py; retrying the request alone cannot succeed."`를 담음 — 상태코드만 적었으면 남을 "로그에서 유추" 갭을 선언이 닫음(페이즈 목적과 정합).

### F-S2.3 회귀 테스트 — 통과 + 양방향 guard 구조 확인

실행: `7 passed, 52 subtests passed`. 구조 적대 검증:

- `test_declared_error_statuses_match_the_lock_list`: OpenAPI 집합 == EXPECTED를 subTest 20으로 pin. **under-strict**(선언 누락 → 집합 축소 → SUBFAIL)·**over-strict`(안 던지는 코드 추가 → 집합 확대 → SUBFAIL) 양방향. `assertEqual(len(EXPECTED), 20)`로 lock 크기도 고정.
- `test_every_declared_error_body_is_the_uniform_detail_model`: 선언된 전 에러 본문이 `#/components/schemas/ErrorDetailResponse` `$ref`인지 pin. 모델 교체 시 SUBFAIL(작업자 mutation 주장과 정합).
- `test_migration_503_description_names_the_operator_action`: `migrate_ordered_units.py` substring pin.
- `CrudErrorBodyExactKeyTest`: `set(body) == {"detail"}`로 **wire 본문이 단일 키**임을 pin → 후속 `reason`이 drift로 들어오면 즉시 실패(over-strict 방어). 404/409/400/503 각 실제 hit.

subTest 총계 52 = lock 20 + body-model **30** + migration 2. (※ work_log는 body-model을 "subTest 27"로 기술했으나 실제는 30 — 이슈 H-1.)

### F-S2.4 OpenAPI self-discovery — 20/20 + scope 누락 없음

`create_app().openapi()` 독립 덤프로 `/projects` 하위 60개 operation 전수 조사: EXPECTED 20개가 정확히 선언되었고, CRUD family(spine 14 + 형제 6)에 **누락 endpoint 없음**. 미선언 나머지는 전부 S3(analysis)·S4(memory/source)·S5(writing) 스코프(`context-search`/`memory`/`source-refs`/`writing/*` 등)로 정확히 분리됨 — S2 범위 이탈 아님.

### F-S2.5 런타임 불변 — full suite green으로 확인

- `git diff`: `main.py` 변경이 **import 1행 + 상수/주석 블록 + 18개 decorator의 `responses=` kwarg 추가**뿐. except 절·`status_code=` 리터럴·detail 문자열·서비스 호출 **0줄 변경**.
- 백엔드 전체: **1379 passed / 41 skipped / 383 subtests**(작업자 주장과 정확히 일치). 기존 `LegacyOrderedDraftMigration503Test`(503 3종)·reorder 409 회귀 전부 green.
- 프론트: `tsc --noEmit` clean · `npm run test` **194 passed / 13 files**(소스 무변) · `npm run gen:api` 재생성이 working-tree 본과 **동일(drift 없음, +270/-0 순수 additive)** · `npm run build` 성공(JS **399.03 kB**, 103 modules, 작업자 주장 일치).

## Issues / Risks

### Blocking (계약 의무 위반)

**없음.** 경계 매트릭스의 모든 "should fire"/"should NOT fire" 분기가 named regression test로 추적되고, 정본 ↔ 구현 ↔ 테스트 ↔ 생성 타입이 정합하며, 정본 자기모순이나 spec-silent-but-code-enforced 갭도 없다(비대칭·500 누수 모두 SoT에 명시됨). green bar가 아니라 계약 요구 분기가 채워진 것이 확인된다.

### Hardening recommendations (비차단, 정본 요구는 아님)

- **H-1 (문서 정확성, work_log)**: S2 work_log가 body-model 테스트를 "(subTest 27)"로 기술했으나 **실제는 30**(lock 20 + body 30 + migration 2 = 총 52, 총합은 정확). CHANGELOG/SoT/HANDOFF의 "+52 subtest"는 맞으므로 work_log의 "27"만 "30"으로 정정 권장. 계약 문안·테스트 동작에는 무영향.
- **H-2 (문서 정밀도, SoT 비대칭 근거)**: SoT의 reorder 비대칭 근거 "위반이 클라이언트가 보낸 순열로 판별된다"는 입력검증 분기(`service.py:511/522/525`)에만 성립한다. legacy-data 분기는 `_require_ordered_drafts`(line 504)가 순열 검사 **이전**에 `DraftOrderIntegrityError`를 던지므로, 이 경우 409는 클라이언트 순열이 아닌 광범위 `(Archived, InvalidDraftOrder)` catch에 기인한다. 행동적 사실(legacy에서도 reorder=409)과 선언 `{404,409}`는 정확하므로 계약은 정직하나, 근거 문안을 "입력검증 face에 한정"으로 좁히거나 legacy face를 별도 언급하면 다음 검증자가 오독하지 않는다. 해결(503화 여부) 자체는 S5 판단.
- **H-3 (테스트 커버리지)**: `test_migration_503_description`이 `GET /drafts`(list)·`GET /projects/{id}/export` 2곳만 subTest. `POST /drafts`(create)의 503도 동일 `_MIGRATION_503` 상수를 쓰므로 description 자체는 간접 검증되나, create 경로가 다른 dict로 fork되면 description 회귀를 잡지 못한다. 3번째 subTest 추가 권장(상수 공유라 비용은 1행).
- **H-4 (구조 관찰)**: 선언 exact 테스트는 OpenAPI==EXPECTED를 pin하고, EXPECTED==실제 raise 등가는 본 검증자의 직독으로 확인했다(전 18행 정합). endpoint가 단순 try/except 18개라 현재 충분하나, 향후 hardening으로 AST scan으로 "선언 집합 ⊇ 실제 `raise HTTPException(status_code=…)` 코드"를 자동 검증하면 under-strict를 기계적으로 닫는다(정본 요구 아님).

## Verdict

**합격(PASS).**

이유(load-bearing):
1. S1 정본 문서가 브리프 D1~D4=A의 모든 계약 문안을 충실히 반영했고, 동기부여 수치 전부를 실코드에서 재도출해 거짓이 없다(F-S1.2).
2. 503 두 얼굴(15+3)·`InvalidDraftOrder` 비대칭·`start_next_unit` 500 누수를 코드로 직접 확인해 정본 기록이 사실과 일치한다(F-S1.2/F-S1.3/F-S1.4).
3. S2 18 endpoint 선언이 실제 raise 집합과 양방향으로 정합하고(F-S2.1), 단일 모델·migration description으로 페이즈 목적(로그 유추 갭 제거)을 달성한다(F-S2.2).
4. 경계 매트릭스에 빈 cell이 없고(F-S2.3), 런타임이 full backend 1379/41/383 + frontend 194/13 + build 399.03 kB로 무변임을 확인했다(F-S2.5).
5. 비차단 4건(H-1~H-4)은 문서 정밀도·테스트 보강 후보로, 정본 요구 분기 누락이나 자기모순이 아니다.

조건 없는 합격. H-1~H-4는 권장 사항이며 본 슬라이스 통과 요건이 아니다.

## Outstanding items

- **미커밋**: 작업 6파일이 working tree에만 있음(작업자가 커밋 요청 없음으로 보류). 오너가 커밋을 승인하면 S1·S2 별도 커밋 권장(브리프가 "각각 별도 커밋"을 명시).
- **환경**: application 컨테이너 down·frontend Restarting 상태. 본 슬라이스는 LLM 미사용이라 host-side 검증으로 완결됐고 라이브 확인 불필요. S3 이후 구역도 동적 ProviderError 매핑이 endpoint별 realistic 집합 한정이라 LLM 없이 선언 가능(HANDOFF 함정과 일치).
- **후속 슬라이스**: S3(analysis) → S4(memory/source) → S5(writing 잔여 + `start_next_unit` 503 방어로 500 누수 폐쇄). S5가 SoT v1.7.29 "알려진 결손"을 닫는 시점.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# 1. 신규 회귀 7건 (+52 subtest)
PYTHONPATH=. python3 -m pytest \
  tests/test_application_api.py::CrudErrorContractDeclarationTest \
  tests/test_application_api.py::CrudErrorBodyExactKeyTest -v

# 2. CRUD 영역 회귀(legacy 503·reorder 409 포함)
PYTHONPATH=. python3 -m pytest tests/test_application_api.py -q

# 3. 백엔드 전체(런타임 불변 확인, mongo 27018 필요)
CORE_SOT_TEST_MONGO_URI=mongodb://localhost:27018 PYTHONPATH=. \
  python3 -m pytest tests/ -q

# 4. OpenAPI self-discovery(브리프 지정 명령)
PYTHONPATH=. python3 scripts/dump_openapi.py > openapi.json   # exit 0, ~159KB

# 5. 프론트 타입/빌드
cd frontend && npm run gen:api && npx tsc --noEmit && npm run test && npm run build
```

재현 결과(검증자 실측): (1) 7 passed / 52 subtests · (2) 84 passed / 65 subtests · (3) 1379 passed / 41 skipped / 383 subtests · (4) exit 0 · (5) gen:api drift 없음 / tsc exit 0 / 194 passed(13 files) / build JS 399.03 kB.
