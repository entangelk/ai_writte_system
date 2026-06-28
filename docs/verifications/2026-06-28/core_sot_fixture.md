# Core SOT reusable fixture (plan 01 최소 산출물 #7) 검증

## Subject metadata

- 날짜: 2026-06-28
- 요청자: entangelk(사용자) — “작업 AI가 작업한 부분 보고 검증하고 의심하고 또 의심해줄래?”
- 검증자: Claude(독립 검증 세션, 작업 AI와 별개)
- 검증 대상 slice/artifact: commit `0b30d49` “Add reusable Core SOT fixture”
  - `tests/fixtures/__init__.py`(신규)
  - `tests/fixtures/core_sot.py`(신규, fixture 본체)
  - `tests/test_core_sot_fixture.py`(신규, 회귀 2건)
- canonical spec reference: `docs/plans/01-core-sot.md`(Draft)
  - 최소 산출물 #7(`01-core-sot.md:36`)
  - 반드시 잠글 계약(`01-core-sot.md:50-59`)
  - 승인된 텍스트 정본 계약(`01-core-sot.md:61-71`)
  - 수용 기준(`01-core-sot.md:89-95`)
  - HANDOFF Active Decisions(Core SOT text/reference 계약, `HANDOFF.md:31-35`)
- 작업 출처: commit `0b30d49`(branch `main`, committed). 작업 트리 clean.

## Scope

이 검증이 독립 확인하는 표면:

1. **계약(스펙)** — plan 01 #7과 cross-reference 체인(잠글 계약/정본 계약/수용 기준/HANDOFF)의 경계 정의와 내부 일관성.
2. **구현 코드** — `tests/fixtures/core_sot.py`와 그 의존체(`services/application/app/core_sot/{models,splitter,service}.py`).
3. **회귀 테스트** — `tests/test_core_sot_fixture.py`의 assertion이 실제로 계약을 고정하는지(under-strict / over-strict guard).
4. **fixture grounding** — `RAW_TEXT`에서 SHA-256 · block matrix · source_ref span/quote/block_index를 first-principles로 독립 재도출하여 fixture 상수와 비교.
5. **public envelope** — 전체 discovery 카운트(213 통과 / 27 skip) 직접 재실행.

scope 밖(이 slice가 담당하지 않음): Analysis candidate fixture(Phase 2 schema 미확정, 의도적 제외 — 아래 “정당” 항목), Mongo adapter · Docker · gateway, L53 code-point 계약의 multibyte stress 회귀(test_core_sot.py 책임 — 비차단 관찰 O2로 이관).

## Methodology

- **스펙 스코핑**: plan 01을 #7과 그것이 직접 chain 하는 절(잠글 계약/정본 계약/수용 기준)만 end-to-end 읽고 boundary matrix를 먼저 구축. unrelated 규칙(persistence/transaction/archive 등)은 #7 fixture의 경계를 규정하지 않으므로 제외.
- **독립 재계산(fixture grounding)**: fixture 모듈을 import하되, `RAW_TEXT` 상수에서 `hashlib.sha256(RAW_TEXT.encode("utf-8"))`, `split_source_blocks(RAW_TEXT)`, `RAW_TEXT[start:end]` slice로 hash·block·quote를 모두 재도출하고 fixture 상수(`CONTENT_HASH`/`EXPECTED_BLOCKS`/`EXPECTED_SOURCE_REFS`)와 비교. fixture 자신의 주장을 그대로 믿지 않음.
- **cross-check(build + service 출력)**: `build_core_sot_fixture()`를 실제로 빌드해 service가 내는 `snapshot`/`blocks`/`source_refs`가 fixture 상수와 일치하는지 확인.
- **mutation 증명(양방향 guard)**: 같은 Python 프로세스에서 `services.application.app.core_sot.service.materialize_blocks`를 monkeypatch해 `block_index`를 1-based(`index+1`)에서 0-based(`index`)로 변이한 뒤 fixture unittest를 그대로 구동. 어느 assertion이 FAIL하는지 확인 후 원상복구. **소스 파일 수정 없음**(같은 프로세스 심볼 교체 + 복구).
- **envelope 재실행**: `timeout 90 python3 -m unittest discover -s tests` 로 보고된 213/27을 직접 재확인.
- **L91 deterministic 직접 증명**: `build_core_sot_fixture()` 두 번 빌드하여 snapshot hash와 block 경계가 동일한지 비교.

사용한 정확한 명령은 **Reproduction**에 전부 기록.

## Findings

### 1. Canonical contract scope & 내부 일관성

- `01-core-sot.md:36` #7 “후속 Phase가 재사용할 fixture — 구현: `tests/fixtures/core_sot.py`” ↔ 구현 위치 일치.
- 계약 cross-check(계약 vs 계약 자신): `content_hash = SHA-256(raw UTF-8)`(L55), `offset = Unicode code point`(L53), `source_ref span ⊆ 단일 block`(L54), 동일 입력 → 동일 hash/block(L91), idempotency 경계(L58)가 plan 본문 내에서 모순 없이 일관. HANDOFF Active Decisions(`HANDOFF.md:31`)와도 일치.
- 내부 불일치(blocking) 없음.

### 2. CONTENT_HASH — L55(`content_hash` = raw UTF-8 SHA-256)

| 출처 | 값 |
|---|---|
| fixture 상수(`core_sot.py:31-33`) | `459fc116afac0a93ad10ea43e529c88fe5c8a5516b37679e89f653a758462e78` |
| 독립 `hashlib.sha256(RAW_TEXT.encode("utf-8"))` | 동일 |
| 구현 `content_hash()`(`splitter.py:19-22`) | 동일 |

세 값 일치 → L55 충족. 회귀 `test_fixture_locks_snapshot_blocks_and_source_refs`(`test_core_sot_fixture.py:18`)가 `assertEqual(snapshot.content_hash, CONTENT_HASH)`로 lock.

### 3. Block matrix — L67-69(split 규칙) + L91(deterministic)

- `split_source_blocks(RAW_TEXT)` 출력 6개 block vs fixture `EXPECTED_BLOCKS`(`core_sot.py:63-75`): `kind`/`start_offset`/`end_offset`/`text` **전 field 0 mismatch**.
- offset→text 자체 일관: `RAW_TEXT[start:end] == block.text` 전 block 일치(offset이 raw 기준임을 독립 확인).
- kind 매핑이 L67-69 규칙을 준수: `#`/`##` → HEADING, 단독 `---` → SCENE_MARKER, 빈 줄 경고 → PARAGRAPH.
- materialize `block_index` 시퀀스 `[1,2,3,4,5,6]`, **1-based**(`splitter.py:106,109` `index + 1`).

### 4. Source refs — L54(단일 block) + quote 재구성

| ref | offset | quote(fixture) | `RAW_TEXT[s:e]`(독립) | owner block(1-based) | claimed `block_index` |
|---|---|---|---|---|---|
| brass | [29:34] | `brass` | `brass` | 2(PARAGRAPH 13-40) | 2 |
| old_promise | [117:128] | `old promise` | `old promise` | 6(PARAGRAPH 97-129) | 6 |

- quote가 offset slice와 정확히 일치.
- span이 단일 block 안에 포함(L54 충족).
- `create_source_ref`가 offset 기반으로 찾은 `block_id`(`service.py:319-332`) == expected `block_index`가 가리키는 block의 `id`(둘 다 `source-snapshot-1:block:{2|6}`).

### 5. Idempotent replay — L58 / L91 / L95

- 같은 `idempotency_key` + **다른 body**(`"changed retry body"`) 재시도 → 같은 version id · `idempotent_replay=True` · `snapshot.raw_text`가 `RAW_TEXT`로 불변.
- 다른 key → version 2 · `idempotent_replay=False`.
- 양방향 guard 모두 `test_fixture_idempotency_key_replays_same_version`(`test_core_sot_fixture.py:59-71`)에 존재. over-strict 방향(“다른 body여도 raw가 바뀌면 안 된다”)이 명시적으로 검사됨.

### 6. Mutation 증명(양방향 guard 실증)

`materialize_blocks`를 0-based로 변이해 fixture unittest를 구동한 결과:

- **block_index 1-based가 source_ref 매핑 경로로 lock됨(under-strict 방향 증명)**: `test_fixture_locks_snapshot_blocks_and_source_refs`가 source_ref subTest에서 FAIL
  - `brass`: `source_ref.block_id`(`...:block:1`) != `expected_block.id`(`...:block:2`) — `AssertionError`
  - `old_promise`: `blocks_by_index[6]` → `KeyError: 6`(0-based라 key 5까지만 존재)
- **block matrix tuple 비교는 `block_index`를 direct field로 보지 않음**: 0-based 변이 상태에서도 `(kind,start,end,text)` tuple 비교는 PASS. 즉 “order”는 tuple의 **위치(positional)** 로만 검증되고, `block_index` 값 자체는 matrix 비교의 field가 아님.

### 7. Envelope 재실행

`timeout 90 python3 -m unittest discover -s tests` → **Ran 213 tests … OK (skipped=27)**. HANDOFF `Verification`(`HANDOFF.md:122`)와 work_log(`docs/daily_logs/2026-06-28/work_log.md:271`) 보고와 정확히 일치.

### 8. L91 deterministic 직접 증명

`build_core_sot_fixture()` 두 번 빌드 결과: `snapshot.content_hash` 동일 · `raw_text` 동일 · 6개 block 경계(kind/start/end/text) 동일. (참고: `snapshot.id` 도 두 빌드에서 동일한데, 이는 각 빌드가 fresh `InMemoryCoreSotRepository` 시퀀스를 1부터 다시 쓰는 **deterministic ID 체계** 때문이며 L91 위반이 아님 — L91은 hash/block 경계 동일을 요구하고 이를 충족.)

## Boundary matrix(lock list)

| 계약 경계(plan) | should-fire / should-NOT-fire | fixture 상수 | 회귀 추적 | 확인 |
|---|---|---|---|---|
| L55 `content_hash`=SHA-256(raw UTF-8) | hash == sha256(RAW_TEXT) | `CONTENT_HASH` | `test:18` | 독립 hashlib 일치 |
| L91 deterministic | 동일 입력→동일 hash/block | `RAW_TEXT`,`EXPECTED_BLOCKS` | `test:17,35` + rebuild×2 | 일치 |
| L67 heading | `#`/`##` → HEADING | `EXPECTED_BLOCKS[0,4]` | `test:35` matrix | 일치 |
| L68 scene marker | 단독 `---` → SCENE_MARKER | `EXPECTED_BLOCKS[2]` | `test:35` matrix | 일치 |
| L69 paragraph | 빈 줄 경계 → PARAGRAPH | `EXPECTED_BLOCKS[1,3,5]` | `test:35` matrix | 일치 |
| L53 offset=code point | Python str index | `EXPECTED_BLOCKS` offsets | `test:35`(matrix) | 구현 OK, ASCII-only라 byte와 구분 불가(O2) |
| block order/index | 순서 보존 | tuple 위치 | `test:35`(positional) + source_ref 경로 | direct field는 아님(O1), 1-based는 source_ref로 mutation 증명 |
| L54 source_ref ⊆ 단일 block | span ⊆ one block | `EXPECTED_SOURCE_REFS` | `test:46` block_id match | mutation으로 lock |
| source_ref quote | quote == raw[offsets] | quote 필드 | `test:49` | 독립 slice 일치 |
| L58/L95 idempotent replay | 같은 key+다른 body→같은 version, raw 불변 | `IDEMPOTENCY_KEY` | `test:69-71` | 양방향 확인 |

**빈 칸(empty cell) 없음.** 모든 분기가 회귀로 추적됨. O1은 “분기는 cover됐으나 direct field 표현이 아닌” 형태 gap, O2는 “splitter 구현은 올바르나 multibyte stress 회귀 부재”로, 둘 다 비차단(아래 Issues/Risks).

## Issues / Risks

비차단 관찰:

- **O1(block “order” direct-field 부재)**: `ExpectedBlock` dataclass(`core_sot.py:36-41`)가 `kind`/`start_offset`/`end_offset`/`text`만 가지고 **`block_index` 필드가 없음**. work_log/HANDOFF 선언 “block kind/**order**/offset/text matrix” 중 order가 tuple의 위치로만 표현되고, test의 `actual_blocks` tuple(`test_core_sot_fixture.py:22-34`)이 `(kind,start,end,text)`라 `block_index`는 direct 비교 field가 아님(§6 mutation으로 실증: 0-based 변이에도 matrix tuple PASS). 다만 `block_index` 1-based는 source_ref 매핑 경로(`test:43,46`)로 변이 시 FAIL하므로 **분기 자체는 cover**(blocking 아님). 보강(선택): `ExpectedBlock`에 `block_index`를 추가하고 비교 tuple에 넣으면 order가 direct field로 lock.
- **O2(L53 code-point stress 부재)**: `RAW_TEXT`가 **pure ASCII**(non-ASCII code point 없음, 129 code points == 129 UTF-8 bytes)이므로, L53 “Unicode code point index” 계약을 multibyte 입력으로 stress할 수 없음. splitter 구현(`splitter.py` 전체가 Python `str` index = code point)은 올바르나, code-point vs byte를 구분하는 multibyte 회귀가 **현재 repo 전체에 부재**(`tests/test_core_sot.py:5` docstring에 언급만, `encode(`/한글 literal stress 케이스 없음). 이 slice(#7 fixture)의 직접 책임은 아니나, boundary completeness 관점에서 별도 code-point stress 회귀 권고.
- **정당(issue 아님)**: Analysis candidate fixture 의도적 제외 — Phase 2 AnalysisJob/Candidate schema가 미확정이라 추측 구현 금지(plan L36 + HANDOFF Active Decisions `HANDOFF.md:34`) 원칙을 준수. fixture는 Core SOT의 확정 표면(snapshot/block/source_ref/idempotent save)만 제공.

## Verdict

**합격.** plan 01 #7 “후속 Phase가 재사용할 fixture”가 잠글 계약(content_hash=SHA-256·deterministic block split·source_ref 단일-block span·idempotent replay)을 정확히 충족한다. 모든 핵심 리터럴(SHA-256, offsets, texts, quotes, block_index 1-based, within-block)이 독립 재계산으로 일치; mutation 증명으로 `block_index` 1-based와 source_ref 바인딩 guard가 양방향 확인; envelope 213/27 재실행 일치. boundary matrix에 blocking 빈 칸 없음 — O1은 분기가 cover된 상태의 direct-field 표현 gap, O2는 splitter 구현이 올바른 상태의 test-stress 부재(둘 다 비차단).

## Outstanding items

- commit `0b30d49`는 `main`에 이미 committed(작업 트리 clean). 추가 게시(push) 권한은 별도 결정 사항.
- O1/O2는 소유자 판단 사항. O2(code-point multibyte stress)는 #7 fixture slice를 벗어나므로 별도 `test_core_sot.py`/code-point stress slice에서 추적 권고.

## Reproduction

스펙 스코핑은 `docs/plans/01-core-sot.md:36,50-95`와 `HANDOFF.md:31-35` 읽기. 이하 명령을 순서대로 실행하면 본 검증이 end-to-end 재현된다(인프라 불요, in-memory).

```bash
# 1. 독립 재계산: hash / block matrix / source_ref quote·within-block·block_index
python3 - <<'PY'
import hashlib
from tests.fixtures.core_sot import (RAW_TEXT, CONTENT_HASH, EXPECTED_BLOCKS,
    EXPECTED_SOURCE_REFS)
from services.application.app.core_sot.splitter import content_hash, split_source_blocks
print("hash match:", hashlib.sha256(RAW_TEXT.encode("utf-8")).hexdigest() == CONTENT_HASH == content_hash(RAW_TEXT))
rb = split_source_blocks(RAW_TEXT)
print("blocks match splitter:", all(
    (b.kind,b.start_offset,b.end_offset,b.text)==(e.kind,e.start_offset,e.end_offset,e.text)
    and RAW_TEXT[e.start_offset:e.end_offset]==e.text for b,e in zip(rb,EXPECTED_BLOCKS)))
for sr in EXPECTED_SOURCE_REFS:
    print("ref", sr.name, RAW_TEXT[sr.start_offset:sr.end_offset]==sr.quote, "block_index", sr.block_index)
PY

# 2. fixture 빌드 + block_index 1-based + source_ref 바인딩 + idempotent replay
python3 - <<'PY'
from tests.fixtures.core_sot import build_core_sot_fixture, RAW_TEXT, EXPECTED_SOURCE_REFS
fx = build_core_sot_fixture()
print("indices 1-based:", [b.block_index for b in fx.save.blocks] == [1,2,3,4,5,6])
by = {b.block_index:b for b in fx.save.blocks}
for n,e in [("brass",EXPECTED_SOURCE_REFS[0]),("old_promise",EXPECTED_SOURCE_REFS[1])]:
    print(n, fx.source_refs[n].block_id == by[e.block_index].id)
rep = fx.service.save_draft(project_id=fx.project.id, draft_id=fx.draft.id,
    raw_text="changed retry body", idempotency_key="fixture-save-1")
print("replay:", rep.idempotent_replay, rep.snapshot.raw_text==RAW_TEXT)
PY

# 3. mutation 증명(block_index 1-based 양방향 guard) — 같은 프로세스 monkeypatch, 파일 수정 없음
python3 - <<'PY'
import unittest, services.application.app.core_sot.service as m
from services.application.app.core_sot.models import SourceBlock
orig = m.materialize_blocks
zero = lambda *,project_id,snapshot_id,raw_blocks: tuple(
    SourceBlock(id=f"{snapshot_id}:block:{i}", project_id=project_id, snapshot_id=snapshot_id,
    block_index=i, kind=b.kind, start_offset=b.start_offset, end_offset=b.end_offset, text=b.text)
    for i,b in enumerate(raw_blocks))
m.materialize_blocks = zero
from tests.test_core_sot_fixture import CoreSotReusableFixtureTest
r = unittest.TextTestRunner(verbosity=2).run(
    unittest.TestLoader().loadTestsFromTestCase(CoreSotReusableFixtureTest))
m.materialize_blocks = orig
print("mut failures:", len(r.failures), "errors:", len(r.errors), "restored:", m.materialize_blocks is orig)
PY

# 4. envelope 재실행 + L91 deterministic(build x2)
timeout 90 python3 -m unittest discover -s tests   # 213 통과, 27 skip
python3 - <<'PY'
from tests.fixtures.core_sot import build_core_sot_fixture
a,b = build_core_sot_fixture(), build_core_sot_fixture()
sig = lambda f: tuple((x.kind,x.start_offset,x.end_offset,x.text) for x in f.save.blocks)
print("L91:", a.save.snapshot.content_hash==b.save.snapshot.content_hash, sig(a)==sig(b))
PY
```
