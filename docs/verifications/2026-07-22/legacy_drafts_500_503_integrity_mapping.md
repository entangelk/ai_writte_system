# 검증 기록 — 레거시-데이터 `/drafts` 500 근본 수정 (DraftOrderIntegrityError 서브클래스 + 503 매핑)

## Subject metadata

- **날짜**: 2026-07-22
- **요청자**: 오너(entangelk) — 명시적 검증 요청("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?")
- **검증자**: Claude(독립 감사, 작업 AI의 기록을 가설로 취급해 반박 시도)
- **대상 슬라이스/산물**: pre-W3 레거시 draft(`unit_kind`/`position` 누락)로 인한 `/drafts` 500 누수 근본 수정 — `DraftOrderIntegrityError(InvalidDraftOrder)` 서브클래스 신설, `_require_ordered_drafts` 재분류, `list_drafts`/`create_draft`/`export_project` 3 endpoint의 503 매핑. (reorder 409 유지, start_next_unit 500 누수는 추적 부채)
- **정본 계약 참조**:
  - 본 슬라이스의 지배 계약 = **오너 결정 A(마이그레이션 + endpoint 방어, 상태코드 503)**, 기록: [`docs/daily_logs/2026-07-22/work_log.md`](../../daily_logs/2026-07-22/work_log.md) "Task — 레거시-데이터 `/drafts` 500 근본 수정" User Decisions and Rationale 절.
  - 기저 계약 = W3 ordered-unit invariant, [`docs/system-contract-sot.md`](../../system-contract-sot.md) v1.7.16(W3) + [`scripts/migrate_ordered_units.py`](../../../scripts/migrate_ordered_units.py)(W3 산물, commit `56a73a3`).
- **검증 대상 작업 출처**: working tree, **uncommitted**(HEAD = `ef97c6a`).

## Scope

1. **계약/결정**: 오너 결정(503, A=둘 다)의 내부 정합성, W3 invariant와의 충돌 여부, 마이그레이션 스크립트 역할.
2. **구현**: `DraftOrderIntegrityError` 서브클래스 설계(무결성 vs 입력오류 분리), `_require_ordered_drafts` 두 분기 재분류, 3 endpoint 503 매핑, reorder 409 유지(§3 수술적 무변경) 기계적 타당성.
3. **회귀 테스트**: 신규 6건(5 API + 1 service)의 양방향(under-strict/over-strict) 잠금 — 테스트 본문을 감사 대상으로 직독.
4. **패턴 스윕 완전성**: `_require_ordered_drafts` 호출 5개 메서드 → endpoint 노출 매핑이 빠짐없는지.
5. **정량/부채**: full suite 카운트, start_next_unit 부채 등록(무단 skip 아님) 여부, HANDOFF 부채 rewrite 위생.

## Methodology

- `git diff HEAD --stat` + 파일별 diff(6개 파일, 176 insertions/3 deletions).
- `grep -rn` 로 `_require_ordered_drafts`/`InvalidDraftOrder`/`DraftOrderIntegrityError` 호출·참조 전량 추적.
- service.py 본문 직독: `create_draft` 356-378, `list_drafts` 491-495, `reorder_drafts` 497-526, `export_project` 584-594, `start_next_unit` 720-738, `_require_ordered_drafts` 893-908.
- main.py 핸들러 직독: 1949(list), 2071(export), 2117(create), 2139(reorder), 3866/3938/3945(writing-accept).
- `accept.py:127` → `start_next_unit` 호출 직확인; 마이그레이션 스크립트가 W3 선례(`git log 56a73a3`, Jul 19)임 확인.
- **기계 상태 직접 확인**: `docker ps`로 `agent-memory-mongodb`(27018) 정상, `/dev/tcp` 포트 도달, pytest 9.0.2. (memory 규칙 준수)
- **Under-strict 실험 1**(endpoint catch 제거): main.py의 3개 503-raise(`raise HTTPException(status_code=503, detail=str(exc)) from exc`)를 `raise`(원 예외 재발생→미포착 500)로 치환 후 `LegacyOrderedDraftMigration503Test` 실행 → 기대: legacy 3건 FAIL. 원본은 `/tmp` 백업 후 정확 복구.
- **Under-strict 실험 2**(서브클래스 되돌림): `_require_ordered_drafts`의 `raise DraftOrderIntegrityError(` 2건을 `raise InvalidDraftOrder(`로 되돌린 후 서브클래스 단정 테스트 + API legacy 테스트 실행 → 기대: FAIL. 백업 후 복구.
- **Full suite**: `CORE_SOT_TEST_MONGO_URI=mongodb://localhost:27018 PYTHONPATH=services/application python3 -m pytest tests/ -q`.

## Findings

### 1. 근본 원인 — CONFIRMED

레거시 draft(`unit_kind=None`/`position=None`) → `_require_ordered_drafts`([service.py:903](../../../services/application/app/core_sot/service.py#L903))가 예외를 던지고, 수정 전 endpoint는 `NotFound`만 잡아 미포착 → **500**. Under-strict 실험 1로 500 재현 확인(아래 Findings 4). 작업 AI의 근본 원인 서술 정확.

### 2. 서브클래스 설계 — CONFIRMED sound

`_require_ordered_drafts`의 두 분기(903 metadata 누락, 906 non-contiguous position)는 **저장 데이터만** 검증한다. 클라이언트 입력 오류 경로는 별도이며 bare `InvalidDraftOrder` 유지:
- unit_kind 입력검증: [service.py:367](../../../services/application/app/core_sot/service.py#L367), [:734](../../../services/application/app/core_sot/service.py#L734)
- reorder 입력검증: [:511](../../../services/application/app/core_sot/service.py#L511)(완전 집합 아님), [:522](../../../services/application/app/core_sot/service.py#L522)/[:525](../../../services/application/app/core_sot/service.py#L25)(동시 변경)

따라서 서브클래스 재분류는 입력 오류를 503으로 오분류하지 않는다 — over-strict 가드(bad unit_kind → HTTP 422 / service `InvalidDraftOrder` non-subclass)가 이를 확인.

### 3. Endpoint 매핑 — CONFIRMED

- `list_drafts` [main.py:1949](../../../services/application/app/main.py#L1949) → 503
- `export_project` [main.py:2071](../../../services/application/app/main.py#L2071) → 503
- `create_draft` [main.py:2117](../../../services/application/app/main.py#L2117) → 503
- `reorder_drafts` [main.py:2139](../../../services/application/app/main.py#L2139): `except (Archived, InvalidDraftOrder)` → `DraftOrderIntegrityError`가 `InvalidDraftOrder`의 서브클래스라 이 절에 잡혀 **409 유지**. 기계적으로 타당(500 누수 없음).

### 4. 양방향 가드 — 직접 실험으로 양방향 CONFIRMED(가용 최강 증거)

- **Under-strict 1**(endpoint catch 제거): legacy 3건(list/create/export) 테스트가 raw `DraftOrderIntegrityError` 전파 → **500**으로 FAIL. over-strict 2건(정상→200, bad unit_kind→422)은 PASS로 무관. → endpoint catch가 없으면 버그 재발을 테스트가 잡는다.
- **Under-strict 2**(서브클래스 되돌림 → bare `InvalidDraftOrder`): (a) service 테스트 `test_stored_legacy_data_raises_integrity_subclass`가 parent type으로 FAIL, (b) API list legacy 테스트가 endpoint의 `except DraftOrderIntegrityError`가 parent를 못 잡아 **500**으로 FAIL. → 서브클래스 자체가 필수(서비스 단정 + endpoint catch 양쪽이 의존).
- **Over-strict**: 정상 프로젝트→200, bad unit_kind→422, 두 실험 모두에서 영향 없이 PASS.

### 5. 정량 — CONFIRMED(독립 재도출)

- 포커스(`test_ordered_units.py` + `test_application_api.py`): **91 passed / 25 subtests**(work_log 주장 일치).
- 전체 백엔드(`CORE_SOT_TEST_MONGO_URI=mongodb://localhost:27018`): **1364 passed / 41 skipped / 328 subtests / 0 failed**(203.98s). baseline 1358(retry 슬라이스) + 6 = 1364 산술 성립. work_log·HANDOFF 주장과 정확 일치.

### 6. 패턴 스윕 — CONFIRMED complete

`_require_ordered_drafts` 서비스 호출 5개 전량 매핑: create(369)/list(494)/reorder(504)/export(594)/start_next_unit(737). endpoint 노출 4개 중 3개(list/create/export) 수정→503, reorder→409(기존 방어 유지). 잔여 1개(start_next_unit)는 부채로 등록. 누락 없음.

### 7. 부채 등록(무단 skip 아님) — CONFIRMED

`start_next_unit` 500 누수 실재 확인: [`accept.py:127`](../../../services/application/app/writing/accept.py#L127) → `core_sot.start_next_unit` → [service.py:737](../../../services/application/app/core_sot/service.py#L737) `_require_ordered_drafts`에서 레거시 시 `DraftOrderIntegrityError` throw, writing_accept endpoint([main.py:3945](../../../services/application/app/main.py#L3945))는 `(Archived, StaleWritingBase)`만 잡아 미포착 → **500**. 도달성이 낮다는 인용(list가 상류 가드)은 타당(list가 503이면 UI가 writing-accept 진입 전 차단). HANDOFF 추적 부채 절이 **구 `/drafts` 500 부채 → 해결(Current Status)로 이동, 신규 `start_next_unit` 부채로 rewrite** — HANDOFF 위생("새 note가 대체하면 rewrite") 규칙에 부합.

### 8. 마이그레이션 스크립트 역할 — CONFIRMED

`scripts/migrate_ordered_units.py`가 데이터 실해결. **단, 이 파일은 W3 선례(commit `56a73a3`, Jul 19)이지 오늘 작업 산물이 아님**. work_log/HANDOFF는 이를 "데이터 실해결"로 참조(creation 미주장) — 본질 정확. endpoint 방어는 미마이그레이션 상태 안전망. 오너 결정 A(둘 다)에 부합.

## Issues / Risks

### Blocking(계약 의무) — **없음**

- 계약이 요구하는 모든 분기가 회귀 테스트에 매핑됨: list/create/export legacy→503, bad unit_kind→4xx, normal→200, 서브클래스 분리. reorder→409 계약 요구는 기존 order-error 테스트로 충족(`DraftOrderIntegrityError` ⊂ `InvalidDraftOrder`, reorder endpoint가 parent catch).
- 계약 내부 모순 없음. 오너 결정 근거(왜 503 not 409; 왜 reorder를 §3로 scope-out)가 내부 정합적이고 기록됨.
- empty boundary cell 없음.

### Hardening(비차단 권고)

- **H-1 (reorder 잠금 갭)**: "reorder on legacy data → 409(not 500)"를 고정하는 **신규** 회귀 테스트가 없다. 작업 AI의 "reorder 409 유지/500 누수 없음" 주장은 load-bearing(§3 무변경 정당화)이나, 서브클래스-포착 기계론 + 기존 order-error 테스트에만 의존한다. legacy draft를 seed해 reorder→409를 assert하는 1-line API 테스트가 향후 reorder catch를 분리하는 리팩터에 대한 잠금이 됨. (legacy-during-reorder는 별도 계약-열거 분기가 아니므로 비차단.)
- **H-2 (503 미반영)**: 503-for-migration은 caller가 의존하는 신규 HTTP 상태인데, work_log + HANDOFF에만 기록되고 `system-contract-sot.md`(SoT bump 없음)와 OpenAPI schema(`responses={503}` 없음)에는 반영되지 않았다. 최근 관행(백엔드 전용 상태코드 변경은 SoT bump 안 함 — retry/dirty-guard)과 일관되어 수용 가능하나, 다음 검증자가 503을 로그가 아닌 정본 계약/schema에서 유추해야 한다. SoT 버전 엔트리 또는 `responses={503:...}` 선언 권고.
- **H-3 (문서 정확도, cosmetic)**: (a) work_log prose가 pre-edit line 번호 인용(unit_kind "354·721" → 실제 367·734; reorder "498/509/512" → 실제 511/522/525) — 추가된 서브클래스 클래스로 전체 하향 shift. (b) API 테스트 docstring "fixes every endpoint that touches the ordered set: list, create, export"가 reorder(409)·start_next_unit(500-부채)을 누락해 "every"가 약간 부정확.
- **H-4 (마이그레이션 스크립트 출처 명시)**: work_log/HANDOFF가 `scripts/migrate_ordered_units.py`를 데이터 실해결로 정확히 참조하나, W3 선례(`56a73a3`)임을 명시하지 않아 독자가 오늘 생성으로 오독 가능. "W3 선례 마이그레이션(참조, 본 슬라이스 비작성)" 1줄 명시 권고.

## Verdict — **합격 (PASS)**

핵심 수정 정확, **직접 되돌림 실험으로 양방향 검증**(가용 최강 증거: under-strict 1·2 모두 버그 재현→테스트 FAIL, over-strict 무영향 PASS), full suite 독립 재현(1364/41/328, 0 failed). 유일한 지연 항목(start_next_unit 500)은 무단 skip이 아닌 **정확한 file:line 포인터를 갖춘 추적 부채로 등록**. 차단 계약 위반 없음 — reorder 409 vs 503 비대칭은 명시적 오너 scope-out(§3, 문서화)으로 결함 아님. Hardening H-1..H-4는 비차단이며 본 슬라이스 계약 의무에 영향 없음.

## Outstanding items

- 작업 트리 **uncommitted**(commit은 오너 요청 시 진행 예정 per 작업 AI summary).
- `start_next_unit` 500 누수: 본 슬라이스 미수정, HANDOFF 추적 부채로 잔존.
- 실 레거시 데이터가 남은 dev/deploy Mongo 대상 마이그레이션 미실행 — 실행 전까지 endpoint 방어가 안전망.

## Reproduction

```bash
# 전체 백엔드
CORE_SOT_TEST_MONGO_URI=mongodb://localhost:27018 PYTHONPATH=services/application python3 -m pytest tests/ -q
# → 1364 passed / 41 skipped / 328 subtests

# 포커스
CORE_SOT_TEST_MONGO_URI=mongodb://localhost:27018 PYTHONPATH=services/application python3 -m pytest tests/test_ordered_units.py tests/test_application_api.py -q
# → 91 passed / 25 subtests

# Under-strict 1: main.py의 3개 endpoint 503-raise를 `raise`로 치환 후
#   ... pytest "tests/test_application_api.py::LegacyOrderedDraftMigration503Test" -q
# → list/create/export legacy 3건 FAIL(500), over-strict 2건 PASS

# Under-strict 2: service.py _require_ordered_drafts의
#   `raise DraftOrderIntegrityError(` 2건을 `raise InvalidDraftOrder(`로 되돌린 후
#   ... pytest "tests/test_ordered_units.py::OrderedUnitContractTest::test_stored_legacy_data_raises_integrity_subclass" \
#              "tests/test_application_api.py::LegacyOrderedDraftMigration503Test::test_list_drafts_on_legacy_data_returns_503" -q
# → 2건 FAIL(서브클래스 단정 + 500)
```
