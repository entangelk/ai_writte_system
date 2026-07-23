# 독립 검증 기록 — H3 S5: writing 트랙 12 endpoint 에러 선언 + `start_next_unit` 500 누수 폐쇄

## Subject metadata

- **날짜**: 2026-07-23
- **요청자**: 오너 (커밋 53b291a 작업분에 대해 "검증하고 의심하고 또 의심해줘" 요청)
- **검증자**: 독립 검증 AI (Claude, 구현자와 무관)
- **대상 슬라이스/아티팩트**: H3 에러 응답 계약 S5 — writing 트랙 12 endpoint 선언 + `writing_accept_endpoint`의 `except DraftOrderIntegrityError → 503` 추가
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.7.33 (changelog 행 + "503의 두 얼굴" 절 + "`start_next_unit`의 500 누수 — H3 S5에서 폐쇄됨" 절 + "절 순서 계약")
- **검증 대상 작업 출처**: commit `53b291a7` (branch `main`, 커밋 완료 상태, working tree clean)

## Scope

이 검증은 다음 표면을 하나의 전체로 검증한다 ("did it run"이 아니라 spec↔코드↔테스트↔fixture 스택 전체).

1. **정본 계약(SoT v1.7.33)** — S5 changelog 행, "503의 두 얼굴"·"`start_next_unit` 500 폐쇄"·"절 순서 계약" 절의 자기 정합성.
2. **구현 코드** — `services/application/app/main.py`(10개 endpoint 선언 + 무결성 절), `services/application/app/writing/http_models.py`(`_ACCEPT_503`).
3. **boundary matrix(선언 집합 == 실제 raise 집합, 양방향)** — 12개 writing endpoint 각각.
4. **예외 계층 & 런타임 경로** — `DraftOrderIntegrityError` 계층, `start_next_unit → _require_ordered_drafts` 경로, 절 순서의 의미.
5. **회귀 테스트** — `tests/test_application_api.py::WritingErrorContractDeclarationTest`·`WritingErrorBodyExactKeyTest`, `tests/test_writing_accept.py::StartNextUnitLegacyDataTest`.
6. **mutation(적대적)** — under-strict(무결성 절 제거/재발)·over-strict(부모 `InvalidDraftOrder`로 확대).
7. **수치/산출물** — backend·frontend suite, `gen:api` ±행, `tsc`, build JS 크기, schema.d.ts 충실도.
8. **범위 밖 부채 추적** — 미매핑 500 두 건의 HANDOFF 기록.

## Methodology

정본 계약을 먼저 스코핑한 뒤 코드를 읽었다 (코드부터 열면 자기 정합성만 검증하게 된다). 모든 주장은 1차 소스 `file:line`에서 재도출했다.

- **boundary matrix 구축**: 각 endpoint의 OpenAPI 선언 집합(`responses=`)과 코드 내 도달 가능한 `raise HTTPException(status_code=…)` 집합을 직독하여 양쪽을 독립 추출, 대조. 동적 분기(`status = 504 if exc.code is ProviderErrorCode.TIMEOUT else 502`)는 realistic 집합 `{502, 504}`로 정규화.
- **예외 계층 확인**: `class …(…)` 정의를 grep하여 무결성 절과 400 그룹의 상속 관계 유무 확인.
- **OpenAPI self-discovery**: `create_app().openapi()`를 코드 직독 도출과 대조 (테스트 `_declared`가 동일 방식).
- **런타임 수정 검증(under-strict mutation)**: `main.py` 백업(cp) → `except DraftOrderIntegrityError` 절의 raise를 `raise`(재발)로 변형 → `test_start_next_unit_on_legacy_data_is_503` 실행 → 실패 확인 → 백업에서 복원. (작업 AI의 `git checkout` 사고 교훈에 따라 cp 백업/복원 사용.)
- **over-strict mutation**: 동일 절을 `except DraftOrderIntegrityError` → `except InvalidDraftOrder`(부모)로 확대 → 4개 테스트 반응 관찰 → 복원.
- **수치 재실행**:
  - backend: `python3 -m pytest -q` (전용 test-mongo 27020 RS, `docker-compose.test.yml`).
  - frontend: `npx vitest run`.
  - `tsc --noEmit`, `vite build`.
  - `gen:api` 충실도: working tree에서 `dump_openapi.py` + `openapi-typescript`로 schema 재생성 → 커밋된 `schema.d.ts`와 diff(헤더 주석 제거 후).
  - 행 수: `git show 53b291a --numstat -- frontend/src/api/schema.d.ts`.

복구 후 `git status` clean, `git diff --stat services/application/app/main.py` 공백, HEAD `53b291a` 재확인.

## Findings

### 1. 정본 계약 자기 정합성 — 일치

SoT v1.7.33의 S5 changelog 행, "503의 두 얼굴" 절(방어 지점 3→**4곳** 명시), "`start_next_unit`의 500 누수 — H3 S5에서 폐쇄됨" 절, "절 순서 계약" 절은 서로 모순 없이 정합. HANDOFF Current Status·추적 부채·Next Tasks, work_log의 Goals/Completed/Decisions/Verification/Next steps 도 동일 주장. 계약 내 단절(conflict) 없음.

### 2. boundary matrix(선언 == 실제 raise, 양방향) — 12/12 cell 충족, 빈 칸 없음

각 endpoint의 선언 집합(`main.py` `responses=`)과 도달 가능 `raise` 집합을 직독하여 대조. 동적 `ProviderError` 분기(`504 if TIMEOUT else 502`)는 `{502, 504}`로 정규화.

| endpoint | 선언(`responses=`) | 실제 raise (직독) | 판정 |
|---|---|---|---|
| `generate` post | `{202,400,404,502,503,504}` (`GENERATE_ASYNC_RESPONSES`{202} ∪ `_ERRORS_400_404_502_504_CONFIG`) | 400(`ValueError`/`WritingError`/`InvalidContextSearchRequest`/task_type)·404(`NotFound`)·202(async arm)·503(config×2)·502(`InvalidCandidateReport`/`ContextSearchFailed`/`ProviderError`)·504(`ContextSearchBudgetExceeded`/`ProviderError` TIMEOUT) | ✅ |
| `generation-jobs/{job_id}` get | `{404}` (`_ERRORS_404`) | 404(`NotFound` + job 누락/타 프로젝트) | ✅ |
| `generation-jobs/{job_id}/retry` post | `{404,409}` (`_ERRORS_404_409`) | 404·409(`InvalidGenerationJobStateTransition`) | ✅ |
| `gate` post | `{400,404,502,503,504}` (`_ERRORS_400_404_502_504_CONFIG`) | 400·404·503(config×2)·502·504(동적 분기 포함) | ✅ |
| `report` post | `{400,404,502,503,504}` | 400·404·503(config×2)·502·504 | ✅ |
| `revise` post | `{400,404,502,503,504}` | 400(`WritingRevisionError` 포함)·404·503(config×2)·502·504 | ✅ |
| `revise-and-gate` post(기선언) | `{400,404,502,503,504}` (`REVISE_AND_GATE_RESPONSES`) | 400·404·503(config×2)·502·504 | ✅ (순환 아님) |
| `loop-audits` get | `{404}` | 404(`NotFound`) | ✅ |
| `loop-audits/{audit_id}` get | `{404}` | 404(`NotFound` + `WritingLoopAuditNotFound`) | ✅ |
| `accept` post(기선언) | `{400,404,409,502,503,504}` (`ACCEPT_RESPONSES`) | 400(`WritingAcceptError`/`WritingGateError`/`InvalidContextSearchRequest`/`ValueError`)·404·409(`Archived`/`StaleWritingBase`)·502(`InvalidWritingGateResult`/`WritingAcceptAnalysisError`/`ContextSearchFailed`/`ProviderError`)·**503(config×2 + `DraftOrderIntegrityError`[S5 신규])**·504(`ContextSearchBudgetExceeded`/`ProviderError` TIMEOUT) | ✅ (순환 아님, 504 실제 raise 존재) |
| `scratch` get | `{404}` | 404(`NotFound`) | ✅ |
| `scratch` delete | `{404}` | 404(`NotFound`) | ✅ |

상수 정의(`main.py:1025-1059`): `_ERRORS_400_404_502_504_CONFIG = {400:_ERROR, 404:_ERROR, 502:_ERROR, 503:_CONFIG_503, 504:_ERROR}`. `_CONFIG_503`는 협력자 미구성 face 문안이므로 gate/report/revise/generate의 503는 config face 전용 — 이들은 `DraftOrderIntegrityError`를 전혀 다루지 않는다(직독 확인). accept만 유일하게 config face + 무결성 face 양쪽 503를 가진다. **"두 얼굴" 유일성 주장 성립.**

12 cell 중 빈 칸(계약 요구 분기의 미잠금) 없음. 기선언 2개(revise-and-gate·accept)도 lock list를 선언에서 복사한 순환값이 아니라 실제 raise에서 도출됐음을 502/504 raise 근거로 확인.

### 3. 런타임 수정 — 경로·절 순서·의미 전부 확인

- **경로 실재**: `core_sot/service.py:712-737` `start_next_unit`이 `drafts = self._repo.list_drafts(project_id)` 후 `self._require_ordered_drafts(drafts)`(737행) 호출. `core_sot/service.py:894-907` `_require_ordered_drafts`는 legacy(`unit_kind`/`position` None, 또는 비연속 position)에서 `raise DraftOrderIntegrityError(…)` — 두 분기 모두 동일 예외. accept의 `intent=start_next_unit`이 이 경로에 도달함이 확인됐다.
- **절 추가·위치**: `main.py:4083-4092` `except DraftOrderIntegrityError as exc: → HTTPException(503)`. 이 절은 400 그룹 절 `(WritingAcceptError, WritingGateError, InvalidContextSearchRequest) → 400`(`main.py:4093-4095`) **위**에 위치. diff와 일치.
- **"상속 없음" 주장 확인**: `DraftOrderIntegrityError(InvalidDraftOrder)`(`core_sot/service.py:74`)는 `WritingAcceptError(ValueError)`(`writing/accept.py:49`), `WritingGateError(ValueError)`(`writing/gate.py:24`), `InvalidContextSearchRequest(ContextSearchError)`(`context_search/service.py:97`) 어느 것의 서브클래스가 아니다. 따라서 **오늘 절 순서는 결과를 바꾸지 않는다**(주장 정확). 순서 계약은 훗날 재상속 시의 방어용이다.
- **수술적 범위 보존**: `append_current` intent는 `start_next_unit`을 부르지 않으므로 `_require_ordered_drafts`에 도달하지 않는다 → legacy 데이터에서도 200. 이는 2026-07-22 수정의 의도적 비대칭 보존.

### 4. 회귀 테스트 — 계약을 잠그고 있다

- `WritingErrorContractDeclarationTest`(`test_application_api.py:2538-2667`):
  - `EXPECTED` 12행 exact lock(2606-2610): `self._declared(path, method)`(2598-2600)는 **live OpenAPI**(`self.spec["paths"]…`)에서 읽으므로, 코드 선언이 drift하면 bite한다. 위 §2 표와 동일.
  - `test_the_whole_writing_track_is_declared`(2612-2620): lock list 밖 `/writing/` operation이 0이어야 — 신규 endpoint가 선언 없이 실리는 것 차단.
  - `test_every_declared_error_body_carries_the_uniform_detail_model`(2622-2634): 모든 error 본문이 `ErrorDetailResponse`(`$ref` 또는 `anyOf` arm) — D1=A.
  - `test_union_bodies_appear_only_where_the_contract_allows`(2636-2646): `UNION_BODIES`(2590-2593) = revise-and-gate{400,502,503,504} ∪ accept{502} = **정확히 5곳**. 새 Union의 drift 차단.
  - `test_accept_503_names_both_operator_actions`(2648-2654): accept 503 description에 "not configured" + "migrate_ordered_units.py" 모두 포함 — 두 얼굴 명시 lock.
  - `test_writing_endpoints_declare_the_dynamic_provider_pair_together`(2656-2667): `_declared`(live spec) 기준으로 `"502" in declared == "504" in declared`. **작업 AI가 밝힌 자기 정합성 함정 수정이 실제로 됐음을 확인** — EXPECTED 값이 아니라 live spec을 읽으므로 코드 drift에 bite.
- `WritingErrorBodyExactKeyTest`(`test_application_api.py:2670-2712+`): 404·503-config·400 wire 본문이 `{"detail": str}` 단일 키.
- `StartNextUnitLegacyDataTest`(`test_writing_accept.py:846-951`) 4건:
  - under-strict: `test_start_next_unit_on_legacy_data_is_503`(911) — legacy → 503, 본문 `{"detail"}`.
  - over-strict: no-legacy → 200(921) · `append_current`+legacy → 200(930) · binding 오류+legacy → 400(943).

### 5. mutation(적대적) — under-strict 실증, over-strict 한계 확인

- **under-strict(실증 ✅)**: 무결성 절의 raise를 `raise`(재발)로 변형(= 폐쇄 전 500 누수 재현) → `test_start_next_unit_on_legacy_data_is_503`가 **`DraftOrderIntegrityError: draft metadata migration is required`가 endpoint 밖으로 새며 실패**(500 != 503). 이 테스트가 진짜 회귀 방지 역할을 함이 입증됐다.
- **over-strict(한계 확인, 비차단)**: 절을 `DraftOrderIntegrityError` → 부모 `InvalidDraftOrder`로 확대 → **4개 테스트 전부 여전히 통과**. accept 경로에서 실제 발생하는 `InvalidDraftOrder` 서브클래스가 `DraftOrderIntegrityError`뿐이라 확대가 동작 변화 없는 no-op이기 때문. 즉 독스트링의 "InvalidDraftOrder 전체로 넓히면 over-strict 2건이 깨진다"는 **과장**임을 경험 확인 (상세는 Hardening).

### 6. 수치/산출물 — 전부 재실행 일치

| 항목 | 주장 | 재실행 결과 | 판정 |
|---|---|---|---|
| backend suite | 1450 passed / 1 skipped / 524 subtests | `1450 passed, 1 skipped, … 524 subtests passed in 516.93s` | ✅ |
| frontend suite | 194 passed / 13 files | `Test Files 13 passed (13) / Tests 194 passed (194)` | ✅ |
| `tsc --noEmit` | clean | exit 0, 출력 0 | ✅ |
| build JS | 399.03 kB | `dist/assets/index-*.js 399.03 kB` | ✅ |
| `gen:api` | +244 / -1 | numstat `244 1` + schema.d.ts가 working tree 재생성과 **완전 동일**(diff 0행) | ✅ |
| S5 회귀 신규 | 13 test / 62 subtest | focused run `13 passed, 62 subtests passed` | ✅ |

`gen:api`의 유일한 `-1`은 accept 503의 JSDoc `@description Service Unavailable` → 두-얼굴 문장 교체 한 줄(`schema.d.ts` diff 직독, `git show` numstat `1` deletion과 일치). 타입/필드 손실 0.

### 7. 범위 밖 부채 — 추적 적정

HANDOFF 추적 부채("미매핑 500 경로 2건"): (1) `auto_promote_job` 승격 루프·일부 list 호출이 try 밖, (2) `POST …/index/source-blocks/rebuild`가 `NotFound`만 잡아 협력자 장애 500. 둘 다 H3 이전 별개 결손이고 브리프의 런타임 변경 예외는 `start_next_unit` 한 건만 명시하므로, S5에서 고치지 않은 것은 오너 승인 스코프 준수. 별도 슬라이스 후보로 근거와 함께 남아 있음. ✅

## Issues / Risks

### Blocking (계약 의무) — 없음

정본 계약이 요구하는 모든 "should fire"/"should NOT fire" 분기와 리터럴이 boundary matrix에 매핑됐고, 12개 endpoint 전부 "선언 == 실제 raise" 양방향이 성립하며, 런타임 수정의 under-strict guard가 실증됐다. 빈 칸 없음.

### Hardening recommendations (비차단)

1. **`StartNextUnitLegacyDataTest` 독스트링 overclaim 정정 (권장)**: 클래스 독스트링(846-866)과 `test_binding_errors…`(943)는 over-strict guard가 "InvalidDraftOrder 전체로 매핑 widening"을 잡는다고 서술하지만, 검증자가 실제로 `except InvalidDraftOrder` 확대 mutation을 돌린 결과 **4개 테스트 전부 통과** — 이 확대를 잡지 못한다. 원인: accept 경로에 도달하는 `InvalidDraftOrder` 서브클래스가 `DraftOrderIntegrityError`뿐이라 widening이 no-op. 테스트 자체는 올바른 동작을 양방향으로 잠그므로 계약 결함은 아니나, 독스트링의 특정 mutation 주장은 부정확하다. 권장: 독스트링을 "widening to `InvalidDraftOrder`는 현재 경로에서 no-op이므로 이 테스트들이 잡지 않는다 — 잡는 것은 under-strict(절 제거)와 세 over-strict branch(200/200/400) 자체"로 정정. 또는 `InvalidDraftOrder("draft unit_kind is invalid")`가 endpoint에서 도달 가능해지는 시점에 대비한 별도 테스트 추가.
2. **절 순서 guard의 명명 정확화 (권장)**: `test_binding_errors_still_map_to_400_not_503`는 "clause ordering" guard로 서술되나, `DraftOrderIntegrityError`와 `WritingAcceptError`가 무관 타입이라 순서가 오늘 이 테스트에 영향을 주지 않는다. 실제로 pin하는 것은 "다른 예외 타입이 분리를 유지해 binding 오류는 400"이다. 명명/주석 정도의 정확화.
3. (범위 밖 부채 2건은 위 §7대로 별도 슬라이스 대상 — 본 슬라이스 결함 아님.)

## Verdict

**PASS (조건 없음).**

이유(하중-bearing):
- boundary matrix 12/12 cell 충족, 빈 칸 없음 — 12개 writing endpoint 전부 "선언 집합 == 실제 raise 집합" 양방향 성립, 기선언 2개도 순환 아님.
- 런타임 수정(`DraftOrderIntegrityError → 503`)의 under-strict guard를 mutation으로 실증(절 제거 시 500 재발로 테스트 실패). 수술적 범위(append_current·binding 보존)도 over-strict 3건이 잠근다.
- 예외 상속 무관 → 절 순서 계약은 훗날 재상속 방어용이며, "두 얼굴" 유일성(accept만 config+무결성)과 `_ACCEPT_503` 두 조치 명시가 계약·코드·선언·테스트 전면에 정합.
- 수치(backend 1450/1/524 · frontend 194/13 · tsc clean · build 399.03 kB · gen:api +244/-1 · schema 충실) 전부 재실행 일치.
- 범위 밖 부채 2건은 오너 승인 스코프 준수로 적정 추적.

Hardening 2건(독스트링 overclaim·명명)은 계약 요구가 아니며 동작에 영향 없는 문서 정확화 후보라 판정에 영향을 주지 않는다.

## Outstanding items

- 본 검증은 read-only + 일시 mutation(전부 복원 완료, `git status` clean, HEAD `53b291a`)으로, working tree·커밋에 변경을 가하지 않았다.
- 오너의 다음 갈림길은 본 슬라이스와 무관하게 dogfood 착수(GATE-1). 본 검증은 dogfood 관련 사항을 다루지 않는다.
- Hardening 권장 2건은 오너가 원할 경우 후속 마이너 커밋으로 반영 가능하나, 슬라이스 판정을 좌우하지 않는다.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# (사전) 전용 test-mongo 기동(이미 27020 RS healthy면 생략)
docker compose -f docker-compose.test.yml up -d

# 1. boundary matrix 직독 (각 endpoint의 responses= vs raise 집합)
grep -n "responses=" services/application/app/main.py | grep writing
# → main.py:3304/3441/3460/3484/3549/3620/3700/3970/3985/4000.../4144/4161 등

# 2. S5 focused 회귀
python3 -m pytest tests/test_writing_accept.py::StartNextUnitLegacyDataTest \
  tests/test_application_api.py::WritingErrorContractDeclarationTest \
  tests/test_application_api.py::WritingErrorBodyExactKeyTest -q
# → 13 passed, 62 subtests passed

# 3. 전체 backend suite (수치 재확인)
python3 -m pytest -q
# → 1450 passed, 1 skipped, 524 subtests passed

# 4. frontend + tsc + build
cd frontend && npx vitest run && npx tsc --noEmit && npx vite build
# → 194 passed (13 files); tsc clean; index-*.js 399.03 kB

# 5. gen:api 충실도 (working tree 재생성 == 커밋)
python3 ../scripts/dump_openapi.py > /tmp/o.json && \
  npx openapi-typescript /tmp/o.json -o /tmp/s.d.ts && \
  diff <(grep -v '^// ' /tmp/s.d.ts) <(grep -v '^// ' src/api/schema.d.ts)   # → 0행
git -C .. show 53b291a --numstat -- frontend/src/api/schema.d.ts            # → 244 1

# 6. under-strict mutation (무결성 절 제거 효과)
cd ..
cp services/application/app/main.py /tmp/main.bak
python3 - <<'PY'
p="services/application/app/main.py"; s=open(p,encoding="utf-8").read()
a="            # the caller's fault. The over-strict regression pins 503, not 400.\n            raise HTTPException(status_code=503, detail=str(exc)) from exc\n"
assert s.count(a)==1
open(p,"w",encoding="utf-8").write(s.replace(a,"            # the caller's fault. The over-strict regression pins 503, not 400.\n            raise\n"))
PY
python3 -m pytest tests/test_writing_accept.py::StartNextUnitLegacyDataTest::test_start_next_unit_on_legacy_data_is_503 -q
# → FAILED (DraftOrderIntegrityError escapes → 500 != 503)
cp /tmp/main.bak services/application/app/main.py   # 복원
```
