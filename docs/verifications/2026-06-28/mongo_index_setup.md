# Mongo index setup hardening (Slice 1 잔여 회귀) 검증

## Subject metadata

- 날짜: 2026-06-28
- 요청자: entangelk(사용자) — “다음작업 검증해줘”(commit `679a132`)
- 검증자: Claude(독립 검증 세션, 작업 AI와 별개)
- 검증 대상 slice/artifact: commit `679a132` “Harden Mongo index setup handling”
  - `services/application/app/core_sot/mongo_repository.py`(`MongoRepositorySetupError` 신규, `ensure_indexes()` wrapping)
  - `tests/test_core_sot_mongo_indexes.py`(신규, 단위 회귀 2건)
  - `HANDOFF.md`(Next Tasks #1 정리, Verification 1줄, Project Structure 1줄)
  - `docs/daily_logs/2026-06-28/work_log.md`(섹션 추가)
- canonical spec reference: 이 slice의 직접 계약 출처는 **HANDOFF Next Tasks #1 “index 부재/충돌 시 동작”**(구 추적 항목). `docs/system-contract-sot.md`(Approved v1.5)의 §76(transaction 범위)/§83(idempotency)를 참조하나, **MongoDB collection index 이름·스펙·setup error 처리에 대한 SoT 명시 절은 없음**(아래 O1).
- 작업 출처: commit `679a132`(branch `main`, committed). 작업 트리 clean(사용자 보고 + `git show --stat`로 단일 커밋 확인).

## Scope

1. **계약(스펙)** — SoT v1.5에서 이 영역(index setup / OperationFailure / setup error)을 명시하는지, 그리고 HANDOFF/plan과의 일관성.
2. **구현 코드** — `mongo_repository.py`의 `ensure_indexes` wrapping과 `MongoRepositorySetupError`, `__init__` 호출부(`mongo_repository.py:68`).
3. **회귀 테스트** — `test_core_sot_mongo_indexes.py`의 assertion이 실제로 계약을 고정하는지(under/over-strict).
4. **query path 일관성** — 생성하는 3개 index가 실제 조회 query path와 일치하는지.
5. **public envelope** — 전체 discovery 카운트(216 통과 / 27 skip) 직접 재실행.

scope 밖: archive 후 파생 인덱스 stale 이벤트(HANDOFF Next Tasks #1이 Phase 3 indexing 계약(Draft) 확정 뒤로 이관됨을 확인), transaction/fallback write path(별도 slice에서 이미 검증), live MongoDB 통합(이 slice는 인프라 없는 단위 테스트가 목적).

## Methodology

- **스펙 스코핑**: SoT v1.5에서 `index`/`ensure`/`OperationFailure`/`unique` 키워드를 grep하고, §76/§83/§102/§110/§296을 확인해 이 영역의 명시 계약 존재 여부를 판단.
- **query path 분석**: `mongo_repository.py`의 모든 `find_one`/`find`/`sort` 호출을 grep해 3개 index가 어느 조회에서 실제 사용되는지 대조.
- **mutation 증명(양방향 guard)**: 같은 Python 프로세스에서 `MongoCoreSotRepository.ensure_indexes`를 monkeypatch해 3가지 변이를 가한 뒤 단위 테스트를 그대로 구동, 어느 assertion이 FAIL하는지 확인 후 원상복구. **소스 파일 수정 없음**.
  - M1: try/except wrapping 제거(OperationFailure가 그대로 노출)
  - M2: `versions` index keys 변경(spec `[("project_id",1)]`로 축소)
  - M3: `raise ... from exc`의 `from exc` 제거(cause chain 단절)
- **envelope 재실행**: `timeout 90 python3 -m unittest discover -s tests`.
- **import 견고성**: pymongo 미설치 시 `try/except ImportError` + `skipUnless`로 discovery가 깨지지 않는지(이전 R1 패턴 일관 적용) 확인.

사용한 정확한 명령은 **Reproduction**에 기록.

## Findings

### 1. 구현 정확성

- `MongoRepositorySetupError(RuntimeError)` 신규 정의(`mongo_repository.py:45-46`).
- `ensure_indexes()`(`mongo_repository.py:84-106`)가 3개 index 생성을 `try`로 감싸고 `except OperationFailure as exc: raise MongoRepositorySetupError(...) from exc`로 변환. **`from exc`로 `__cause__` 체인 보존**.
- `OperationFailure` import 추가(`mongo_repository.py:29`).
- `__init__`(`mongo_repository.py:68`)이 생성 시점에 `ensure_indexes()`를 호출 — 운영 startup 시 index 실패가 곧 SetupError로 표면화.

### 2. 3개 index spec — 단위 테스트(under-strict)가 정확히 lock

`test_ensure_indexes_creates_required_absent_indexes`(`test_core_sot_mongo_indexes.py:48-85`)가 각 collection의 `create_index` 호출 `(keys, kwargs)`를 정확히 비교:

| collection | keys | kwargs | name |
|---|---|---|---|
| `_versions` | `(project_id, draft_id, idempotency_key)` | `unique=True` | `uniq_save_request` |
| `_blocks` | `(snapshot_id, block_index)` | — | `blocks_by_snapshot` |
| `_source_refs` | `(project_id, snapshot_id)` | — | `source_refs_by_snapshot` |

### 3. conflict → stable setup error — 단위 테스트(over-strict)가 lock

`test_conflicting_index_failure_is_stable_setup_error`(`test_core_sot_mongo_indexes.py:87-95`):
- 충돌 index(`fail_on_name="uniq_save_request"`) 시 `assertRaises(MongoRepositorySetupError)`.
- `assertIsInstance(raised.exception.__cause__, OperationFailure)`로 cause chain 보존 검증.
- docstring 명시: “a conflicting index must not look like save logic” — 즉 save path의 `DuplicateSaveRequest`로 오인되지 않아야 함.

### 4. Mutation 증명(양방향 guard 실증)

같은 프로세스 monkeypatch로 3변이 구동 결과(어느 테스트가 FAIL로 변이를 잡았는지):

| 변이 | 기대 FAIL 테스트 | 실제 결과 |
|---|---|---|
| BASELINE(변이 없음) | (없음) | 2개 통과 ✓ |
| **M1** wrapping 제거 | over-strict | `test_conflicting_..._setup_error` **ERROR**(`OperationFailure` 노출) ✓ |
| **M2** `versions` keys 축소 | under-strict | `test_ensure_indexes_creates_required_absent_indexes` **FAIL**(keys 불일치) ✓ |
| **M3** `from exc` 제거 | over-strict | `test_conflicting_..._setup_error` **FAIL**(`__cause__ is None`) ✓ |

→ wrapping 존재(M1), index spec 정확성(M2), cause chain 보존(M3)이 각각 독립된 assertion으로 양방향 lock됨. 빈 칸 없음.

### 5. Envelope 재실행

`timeout 90 python3 -m unittest discover -s tests` → **Ran 216 tests … OK (skipped=27)**. HANDOFF(`HANDOFF.md:124`)·work_log(`docs/daily_logs/2026-06-28/work_log.md:290`) 보고와 정확히 일치(이전 fixture slice 214 + 신규 2 = 216).

### 6. import 견고성

`tests/test_core_sot_mongo_indexes.py:10-23`가 `try/except ImportError` + `@unittest.skipUnless(_PYMONGO_AVAILABLE, ...)`(`:46`)로 pymongo 미설치 시 모듈 import가 discovery를 깨뜨리지 않고 skip 처리. mongo_adapter 재검증 R1에서 확립한 패턴과 일관.

## Boundary matrix(lock list)

| 경계 | should-fire / should-NOT-fire | 회귀 추적 | mutation 증명 |
|---|---|---|---|
| 3개 required index spec 정확 | 각 collection의 keys/kwargs/name 일치 | under-strict `:48-85` | M2 → FAIL |
| OperationFailure → SetupError | conflict 시 save 에러 아닌 setup 에러 | over-strict `:87-93` | M1 → FAIL |
| cause chain 보존 | `__cause__`가 `OperationFailure` | over-strict `:95` | M3 → FAIL |
| save logic과 구분 | `DuplicateSaveRequest`로 오인 X | over-strict(assertRaises SetupError) | M1 간접 |
| pymongo 미설치 skip | discovery 안 깨짐 | `:10-23,46` | (R1 패턴 일관) |

**빈 칸 없음.** 모든 분기가 mutation으로 lock됨.

## Issues / Risks

비차단 관찰:

- **O1(spec-silent 영역 → SoT amendment 권고)**: 이 slice가 다루는 “MongoDB index 부재/충돌 시 동작”(3개 index 생성 · `OperationFailure`→`MongoRepositorySetupError` 매핑)은 SoT v1.5에 **명시적 계약이 없음**. SoT는 source_ref offset(§102)과 Chroma/ES 파생 index 후보(§110, §296)만 다루고, MongoDB collection index 이름·스펙·setup error taxonomy는 침묵. `MongoRepositorySetupError`가 이제 public symbol이므로, SoT에 “Core SOT MongoDB required indexes와 setup-failure 표면화”를 한 줄 명시하면 future verifier/호출자가 guess하지 않아도 됨. 단, (a) 3개 index 선정 자체는 이 slice **이전**에 정해진 것이고 이 slice는 wrapping만 추가, (b) error wrapping은 입력의 accept/reject를 결정하는 행동 boundary가 아니라 error taxonomy이므로, CLAUDE.md “Spec-silent-but-code-enforced is a contract gap(차단)”의 엄격한 범주(데이터 reject/accept)에는 해당하지 않음 → **비차단 amendment 권고**로 분류.
- **O2(`source_refs_by_snapshot`이 현재 dead index)**: query path 분석(`mongo_repository.py:128-194`) 결과, `source_refs` collection에 대한 non-`_id` query가 현재 없다. `get_source_ref`(`:192-194`)는 `find_one({"_id": ...})`로 `_id` index를 쓰고, `create_source_ref`(service)는 `get_blocks`로 block을 찾지 `source_refs`를 query하지 않음. 즉 `(project_id, snapshot_id)` index는 현재 어느 조회 경로에서도 사용되지 않음. under-strict test가 이 index 존재를 lock하므로, 사용되지 않는 index가 회귀로 고정됨. 반면 `uniq_save_request`(`find_save_request` `:165` 사용)와 `blocks_by_snapshot`(`get_blocks` `:184` 사용)는 실제 query path와 일치. → 비차단(Phase 2 snapshot별 source_ref 목록 조회를 대비한 선행 index일 수 있으나, YAGNI 관점에서 “index ↔ 실제 query path 일치” 검증 부재로 기록. 이 slice 이전 index 선정이므로 이 slice 책임은 아니나 이 slice가 그것을 lock함).
- **O3(테스트가 `__init__`→`ensure_indexes` 통합 경로 미 cover)**: 테스트가 `object.__new__(MongoCoreSotRepository)`(`test:39`)로 `__init__`을 우회해 fake collection 3개만 주입. `ensure_indexes()` 자체는 직접 호출하므로 로직은 cover되나, 실제 운영 startup 시 `__init__`(`mongo_repository.py:68`)이 `ensure_indexes()`를 호출해 SetupError가 전파되는 통합 경로와 그것이 `main.py`에서 어떻게 처리되는지는 이 단위 테스트 범위 밖. 통합 검증은 live Mongo slice가 담당. 비차단.
- **O4(`except OperationFailure`만 catch)**: 네트워크/연결 에러(`ConnectionFailure`, `NetworkTimeout` 등 `PyMongoError` subclass)는 잡지 않고 그대로 표면화. “index 부재/충돌” 범위에 맞는 의도적 좁은 catch로 합리적. 비차단(범위 명시만 기록).

## Verdict

**합격.** HANDOFF Next Tasks #1 “index 부재/충돌 시 동작”이 코드 + 단위 회귀로 폐쇄됐다. 3개 index spec 정확성(under-strict), `OperationFailure`→`MongoRepositorySetupError` 매핑과 cause chain 보존(over-strict)이 mutation 증명으로 양방향 lock됨; envelope 216/27 재실행 일치; pymongo 미설치 skip 패턴 일관. boundary matrix에 blocking 빈 칸 없음 — O1~O4는 모두 비차단(spec-silent amendment 권고 / dead index 관찰 / 단위-통합 범위 분리 / 좁은 catch 범위 명시).

## Outstanding items

- commit `679a132`는 `main`에 이미 committed(작업 트리 clean). 추가 게시(push) 권한은 별도 결정.
- O1: 소유자 판단으로 SoT에 “Core SOT MongoDB required indexes + setup-failure 표면화(`MongoRepositorySetupError`)” 명시 여부 결정. (비차단 권고)
- O2: `source_refs_by_snapshot` index가 실제 query path에 추가될 시점(Phase 2)까지 dead index로 남음. 소유자 인지 권고.
- HANDOFF Next Tasks #1은 “archive 후 파생 인덱스 stale 이벤트(Phase 3 indexing 계약 확정 뒤)”로 정리됨을 확인 — 본 slice가 “index 부재/충돌”을 닫았으므로 일관.

## Reproduction

```bash
# 1. 단위 테스트 + py_compile (작업 AI 보고 재현)
python3 -m unittest tests.test_core_sot_mongo_indexes -v          # 2 통과
python3 -m py_compile services/application/app/core_sot/mongo_repository.py tests/test_core_sot_mongo_indexes.py

# 2. SoT 명시 계약 부재 확인
grep -nE "index|ensure|OperationFailure|unique" docs/system-contract-sot.md

# 3. query path vs 생성 index 대조
grep -nE "find_one|find\(|create_index|\.sort\(" services/application/app/core_sot/mongo_repository.py

# 4. mutation 증명(M1/M2/M3) — 같은 프로세스 monkeypatch, 파일 수정 없음
python3 - <<'PY'
import unittest
import services.application.app.core_sot.mongo_repository as mod
from pymongo.errors import OperationFailure
from services.application.app.core_sot.mongo_repository import MongoRepositorySetupError
ORIG = mod.MongoCoreSotRepository.ensure_indexes
def run(label):
    from tests.test_core_sot_mongo_indexes import MongoIndexSetupTests
    r = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestLoader().loadTestsFromTestCase(MongoIndexSetupTests))
    print(label, "->", [t.id().split('.')[-1] for t,_ in r.failures+r.errors])
    return r
run("BASELINE")
V = [("project_id",1),("draft_id",1),("idempotency_key",1)]
def m1(self):  # no wrap
    self._versions.create_index(V, unique=True, name="uniq_save_request")
    self._blocks.create_index([("snapshot_id",1),("block_index",1)], name="blocks_by_snapshot")
    self._source_refs.create_index([("project_id",1),("snapshot_id",1)], name="source_refs_by_snapshot")
def m2(self):  # spec change
    try:
        self._versions.create_index([("project_id",1)], unique=True, name="uniq_save_request")
        self._blocks.create_index([("snapshot_id",1),("block_index",1)], name="blocks_by_snapshot")
        self._source_refs.create_index([("project_id",1),("snapshot_id",1)], name="source_refs_by_snapshot")
    except OperationFailure as e: raise MongoRepositorySetupError("x") from e
def m3(self):  # no from exc
    try:
        self._versions.create_index(V, unique=True, name="uniq_save_request")
        self._blocks.create_index([("snapshot_id",1),("block_index",1)], name="blocks_by_snapshot")
        self._source_refs.create_index([("project_id",1),("snapshot_id",1)], name="source_refs_by_snapshot")
    except OperationFailure: raise MongoRepositorySetupError("no cause")
for nm,fn in [("M1",m1),("M2",m2),("M3",m3)]:
    mod.MongoCoreSotRepository.ensure_indexes = fn; run(nm)
mod.MongoCoreSotRepository.ensure_indexes = ORIG
print("restored:", mod.MongoCoreSotRepository.ensure_indexes is ORIG)
PY

# 5. envelope 재실행
timeout 90 python3 -m unittest discover -s tests   # 216 통과, 27 skip
```
