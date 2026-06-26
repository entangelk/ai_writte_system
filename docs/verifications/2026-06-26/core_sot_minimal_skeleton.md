# 검증 기록 — Slice 1 Core SOT minimal skeleton

## Subject metadata

- 날짜: 2026-06-26
- 요청자: 소유자("작업 AI가 작업한 부분에 대해서 검증하고 의심해줄래? … 의심하고 또 의심해봐줄래?")
- 검증자: 독립 검증 세션(Claude Code)
- 검증 대상 slice/artifact:
  - `services/application/app/core_sot/models.py`(신규, commit `eb55a20`)
  - `services/application/app/core_sot/splitter.py`(신규, commit `eb55a20`)
  - `services/application/app/core_sot/service.py`(신규, commit `eb55a20`)
  - `services/application/app/core_sot/__init__.py`(신규, commit `eb55a20`)
  - `services/application/app/main.py`(신규, commit `eb55a20`)
  - `tests/test_core_sot.py`(신규, 9개 회귀, commit `eb55a20`)
  - `tests/test_application_api.py`(신규, 2개 회귀, commit `eb55a20`)
- 정본 계약 참조(scope 한정):
  - `docs/system-contract-sot.md` v1.3 §"Source of Truth"(line 96-114) — raw_text 불변, Unicode code point offset, UTF-8 SHA-256 `content_hash`, deterministic source block split, explicit save only, idempotency_key 필수, archive/보존
  - 같은 문서 계약 변경 이력 v1.1/v1.2/v1.3(line 36-39) 및 "현재 구현 상태" Core SOT 행(line 326)
  - `docs/plans/01-core-sot.md` §"반드시 잠글 계약"(line 50-58)·§"승인된 텍스트 정본 계약"(line 60-70)·§"승인된 저장·보존 계약"(line 72-85)·§"수용 기준"(line 87-93)
  - `docs/plans/implementation-plan.md` §"Slice 1. Project Shell + Core SOT" 진행 상태(line 204-209)
- 검증 대상 작업 출처: commit `eb55a20`("Implement Core SOT minimal skeleton"). HEAD = `eb55a20`. 검증 시점 working tree clean(독립 probe 후 원복 불필요 — probe는 별도 임시 프로세스에서 실행, working tree 미변경).

## Scope

본 검증은 **Core SOT minimal skeleton slice(`eb55a20`)** 전체를 대상으로 한다. 이 slice는 이전에 **독립 검증 기록이 없었다**(worker 자체 회귀 11개 + HANDOFF/SoT "자체 회귀 완료" 표기만 존재). 아래 표면을 하나의 묶음으로 검증한다.

1. **계약 본문(self-consistency)**: `01-core-sot.md` §텍스트 정본·§저장/보존 ↔ `system-contract-sot.md` v1.2/v1.3 ↔ implementation-plan Slice 1 진행 상태의 경계·리터럴 일치.
2. **boundary matrix(spec → code → test)**: 계약의 모든 "should fire"/"should NOT fire" 분기를 회귀에 매핑. **빈 칸이 없어야 합격.**
3. **content_hash literal 독립 고정**: 계약 "raw UTF-8 bytes에 대한 SHA-256"(`01-core-sot.md:54`, SoT:101)이 회귀로 *독립적으로* pin되는가(tautological lock 여부).
4. **source_ref 재구성 + 경계**: offset semantics(Unicode code point), quote/hash 재구성, cross-block/bool offset 거부.
5. **idempotency 양방향**: same key → same version(under-strict: 중복 방지) + mutated body 무시(over-strict).
6. **archive/보존**: archive 후 새 save 차단 + snapshot/version/block 보존.
7. **회귀 직접 재실행 + 보고 숫자 독립 재현**(focused 11 / 전체 148).
8. **패턴 sweep**: 동일 hash/offset/split 계약의 분산·중복 구현 사이트.
9. **spec-silent-but-code-enforced gap** 및 **계약 자기모순** 탐지.

## Methodology

계약을 먼저 스코프하고(`01-core-sot.md` §텍스트 정본·§저장/보존과 SoT §Source of Truth를 끝까지 읽고 상호 교차), boundary matrix를 구축한 뒤 코드·테스트를 매트릭스 셀에 매핑했다. load-bearing literal 2종(`content_hash` 알고리즘, offset semantics)은 **독립 재계산/다바이트 입력 변별**으로, idempotency는 **양방향 단언** 존재 여부로, 빈 칸은 **probe + 회귀 grep**으로 입증했다. "코드가 돌아가는가"가 아니라 "코드가 계약을 고정하는가"를 감사한다.

사용한 명령(repo root `/mnt/d/devel/에베베/ai_writte_system` 기준):

- focused 회귀: `python3 -m unittest tests.test_core_sot tests.test_application_api -v`
- 전체 회귀: `python3 -m unittest discover -s tests -p 'test_*.py'`
- per-module count: `grep -cE '^\s*def test_' tests/test_core_sot.py tests/test_application_api.py`
- 독립 hash 재계산/변별: `hashlib.sha256(raw.encode("utf-8"))` vs `md5`/`utf-16-le`/`utf-32-le`(다바이트 한국어 입력)
- 미커버 분기 probe: `***` scene marker / `##` heading / `archive_project` / cross-block source_ref / whitespace idempotency key
- 패턴 sweep: `grep -rn "sha256\|content_hash\|normalized_text_hash\|\.encode(" services/ tests/`
- 리터럴은 직접 Read로 행 단위 교차(`models.py`, `splitter.py`, `service.py`, `main.py`, 계약 문서, 테스트).

## Findings

### F1. spec ↔ implementation literal 일치 — PASS(단, hash 알고리즘은 F2 별도)

핵심 literal이 계약과 행 단위로 일치한다.

| 계약 literal | code | 계약 근거 | 비고 |
|---|---|---|---|
| `content_hash = sha256(raw_text.encode("utf-8")).hexdigest()` | `splitter.py:19-22` | `01-core-sot.md:54`, SoT:101 | 알고리즘 자체는 정확(독립 재계산으로 확인, F2) |
| offset = Unicode code point(Python str slice) | `splitter.py:55-57`(`offset += len(line)`), `service.py:208`(`raw_text[start:end]`) | `01-core-sot.md:53`, SoT:100 | 한국어로 code point vs byte 변별 입증(F4) |
| `BlockKind` = heading/scene_marker/paragraph | `models.py:14-17` | `01-core-sot.md:65-69` | literal 일치 |
| `normalized_text_hash` = v1 필수 아님 → **존재하지 않음** | (부재, 정확) | `01-core-sot.md:55`, SoT:102 | 올바르게 미구현(absence) |
| `raw_text` 저장 후 불변 | `models.py:46`(frozen) + `service.py:160`(as-is 저장) | `01-core-sot.md:52`, SoT:99 | ✓ |
| `idempotency_key` 필수 | `service.py:135-136`(`if not idempotency_key: raise`) | `01-core-sot.md:80`, SoT:110 | ✓ (빈문자열/None 거부; I6 비고) |
| 같은 key → 같은 version | `service.py:139-143`(`find_save_request` lookup) | `01-core-sot.md:81`, SoT:110 | ✓ (F6 양방향) |
| archive = 삭제, 보존 | `service.py:213-224`(flag만 flip, 미삭제) | `01-core-sot.md:82-83`, SoT:112 | ✓ (draft 경로; project 경로는 F3 빈 칸) |

패턴 sweep: `content_hash` 정의는 `splitter.py` 단일이며 `service.py:161,209`·`main.py:85`가 동일 함수를 사용. **동일 계약의 분산/중복 hash·offset 구현 사이트 없음**(F8).

### F2. content_hash 알고리즘 — code는 정확하나 test lock은 tautological(CONDITIONAL)

- `test_core_sot.py:24`가 `from ...splitter import content_hash`를 하고, `test_core_sot.py:47`이 `self.assertEqual(result.snapshot.content_hash, content_hash(raw_text))`를 단언한다. 우변은 **검증 대상 모듈의 동일 함수**다. service가 splitter의 `content_hash`를 호출하는지만 확인할 뿐, literal "SHA-256 over UTF-8 bytes"를 *독립적으로* pin하지 못한다. `content_hash`가 MD5로 바뀌거나 정규화된 text를 hash해도 양변이 함께 바뀌어 **회귀는 여전히 green**이다.
- **독립 재계산으로 알고리즘 자체는 정확함을 입증**: `hashlib.sha256(raw.encode("utf-8")).hexdigest() == content_hash(raw)` 성립. 다바이트 한국어 `"두번째 문장"`에서 `content_hash`는 `utf-16-le`/`utf-32-le` 기반 hash와 **상이**하며, latin-1은 한국어를 인코딩조차 못한다(→ UTF-8만이 계약 인코딩으로 작동). 즉 **code는 faithful, test는 약한 guard**.
- 계약 literal(`01-core-sot.md:54`)의 "SHA-256/UTF-8" 분기는 사실상 **독립 회귀로 잠기지 않은 셀**이다.

### F3. boundary matrix — 빈 칸 3건 존재(CONDITIONAL, blocking)

계약 분기 → code → 회귀 매핑 결과 **3개 "should fire" 분기가 회귀에 trace되지 않는다.**

| # | 계약 분기 | 계약 근거 | code | 회귀 trace | lock |
|---|---|---|---|---|---|
| 1 | heading `#` → HEADING | `01-core-sot.md:66` | `splitter.py:119-123` | `test_core_sot.py:37,57` | ✓ |
| 2 | heading `##`~`######`(계약 "`#`, `##` 등") | `01-core-sot.md:66` | `splitter.py:119-123`(1≤len≤6) | **없음**(단일 `#`만) | **빈 칸**(probe로 `##`→HEADING 정상 확인) |
| 3 | scene marker `---` | `01-core-sot.md:67` | `splitter.py:126-128` | `test_core_sot.py:37,59` | ✓ |
| 4 | scene marker `***`(계약 "`---` 또는 `***`") | `01-core-sot.md:67` | `splitter.py:126-128` | **없음** | **빈 칸**(probe로 `***`→SCENE_MARKER 정상 확인) |
| 5 | paragraph 빈 줄 경계 | `01-core-sot.md:68` | `splitter.py:62-92` | `test_core_sot.py:58` | ✓ |
| 6 | AI 추론 split 금지 | `01-core-sot.md:69` | (deterministic only) | N/A(부재) | ✓ |
| 7 | archive **draft**: save 차단 + 보존 | `01-core-sot.md:82-83` | `service.py:219-224` | `test_core_sot.py:203-225` | ✓ |
| 8 | archive **project**: save 차단 + 보존 | `01-core-sot.md:82`("project/draft … archive") | `service.py:213-217` | **없음** | **빈 칸**(probe로 `archive_project` 정상 동작 확인) |

code는 세 분기 모두 올바르게 동작하지만(독립 probe로 입증), **회귀가 없으므로** 향후 회귀 도입 없이 해당 코드가 망가져도 green bar가 이를 잡지 못한다. 가이드라인상 "untraced branch is a blocking finding regardless of the green bar".

### F4. source_ref offset semantics + 재구성 — PASS

- 한국어 원문 `"첫 문장입니다.\n두번째 문장입니다."`에서 `"두번째"`의 `raw_text.index`/`len`으로 계산한 code point offset으로 slice → `quote == "두번째"` 정확 재구성(`test_core_sot.py:123-146`). byte/UTF-16 offset이었으면 slice가 깨졌을 것. under-strict 의미로 **code point semantics이 실제로 고정**됨. ✓
- `source_ref.content_hash == snapshot.content_hash`(snapshot의 hash 재사용) ✓
- `block_id`가 해당 span을 포함하는 block으로 매핑 ✓

### F5. spec-silent-but-code-enforced: within-block source_ref 제약(CONDITIONAL — contract gap)

- `service.py:201-211`은 span이 **정확히 하나의 source block 내에** 들어맞아야 `SourceRef`를 반환하고, 아니면 `InvalidSourceRef("source_ref span must fit within one source block")`를 raise. `test_core_sot.py:148-166`이 이 거부를 lock.
- **그러나 계약은 "source_ref는 하나의 block 내에 있어야 한다"고 명시하지 않는다.** `01-core-sot.md:90`(수용기준)은 "임의의 source_ref로 정확한 snapshot, block, span, quote를 재구성한다"라고만 하고, `01-core-sot.md:18`/SoT:128은 source_ref를 "snapshot/block/span/quote"로 기술한다. SoT:103이 source_blocks를 "deterministic source reference 단위"라고 함은 within-block을 *시사*할 뿐 거부 literal은 없다.
- 가이드라인 "Spec-silent-but-code-enforced is a contract gap, not an implementation detail"에 해당. **코드가 over-restrictive일 수도(다중 block 인용이 필요한 caller 차단) 있고, 계약이 불완전할 수도** 있다. 둘 중 하나로 정렬되어야 slice가 닫힌다(계약에 within-block 문장 추가, 또는 코드 완화 + 그에 맞는 회귀).

### F6. idempotency 양방향 guard — PASS(우수)

`test_core_sot.py:62-84`는 단일 테스트에서 양방향을 모두 잠근다:
- **under-strict**: 같은 key 재시도 → `idempotent_replay=True`, 동일 `draft_version.id`, `version_count==1`(중복 version 생성 차단).
- **over-strict**: 재시도 body를 `"mutated retry body must not create a new version"`로 바꿔도 반환 `snapshot.raw_text == "first text"`(변형 body 무시).
추가로 `test_distinct_idempotency_key_creates_next_version`(`:86-106`)가 다른 key → `version_number==2` over-strict 방향을 보강. ✓

### F7. bool offset 거부 — spec-silent-but-documented(비고 수준)

- `service.py:45-46`의 `_is_int`가 `bool`을 명시 거부하고 `test_core_sot.py:168-185`가 lock. 계약(`01-core-sot.md:53`)은 "Unicode code point index"만 말하고 bool 언급이 없으므로 **spec-silent tightening**이나, work_log(line 100-105)가 BudgetPolicy 정수 방어와 같은 방향이라고 *명시적으로 문서화*했다. bool은 의미상 유효한 code point index가 아니므로 합리적 방어. F5보다 낮은 심각도로 비고 처리.

### F8. 회귀 직접 재실행 + 보고 숫자 독립 재현 — PASS

- `python3 -m unittest tests.test_core_sot tests.test_application_api -v` → **Ran 11 tests ... OK**. HANDOFF:97 / work_log:134의 "11개"와 일치.
- `python3 -m unittest discover -s tests -p 'test_*.py'` → **Ran 148 tests ... OK**. work_log:135의 "148개"와 일치.
- per-module 실측: `test_core_sot.py` 9 + `test_application_api.py` 2 = 11. **보고 숫자 부정합 없음**(이전 provider-runner slice의 I1류 문서 결함 없음).
- 패턴 sweep(`grep -rn "sha256\|content_hash\|normalized_text_hash\|\.encode(" services/ tests/`): `content_hash` 정의 단일(`splitter.py:19`), 분산 hash/offset 사이트 없음. ✓

## Issues / Risks

- **I1(차단, boundary matrix 빈 칸 — empty cells)**: 3개 "should fire" 분기가 회귀에 trace되지 않는다. (a) scene marker `***`(`01-core-sot.md:67` literal, `splitter.py:126-128`), (b) heading `##`~`######`(`01-core-sot.md:66` "`##` 등", `splitter.py:119-123`), (c) archive **project** 경로(`01-core-sot.md:82`, `service.py:213-217`). 가이드라인상 빈 칸은 green bar와 무관하게 blocking. 권고: 세 분기에 대한 회귀 추가(`***`→SCENE_MARKER, `##`→HEADING, `archive_project` 후 신규 draft/save 차단 + snapshot/version 보존).
- **I2(차단, tautological hash lock)**: `content_hash` 알고리즘이 회귀로 독립 pin되지 않는다(F2). code는 정확하나 test가 동일 함수를 비교. 권고: known SHA-256 vector로 단언(예: `hashlib.sha256(b"...").hexdigest()` 하드코드드 기대값, 또는 fixture `source_manifest` 재계산).
- **I3(차단, contract gap — spec-silent enforcement)**: within-block source_ref 제약이 계약에 없다(F5). 권고: `01-core-sot.md`/SoT에 "source_ref span은 하나의 source block 내에 한정된다" 문장 추가 **또는** 코드 완화 + 회귀 재조정. 소유자 결정 필요.
- **I4(비차단, scope — source_refs 미영속)**: `create_source_ref`(`service.py:181-211`)는 `SourceRef` 값을 반환할 뿐 **저장하지 않는다**. repo에 source_refs collection이 없다. 따라서 계약 `01-core-sot.md:83` "source_refs는 archive 이후에도 보존한다"는 이 skeleton에서 구조적으로 실현/테스트 불가(보존 대상이 애초에 없음). in-memory skeleton으로서 수용 가능하나, Phase 1 최소 산출물 #1이 `source_refs` 계약을 포함하는 만큼 Mongo adapter slice에서 영속 collection과 함께 실현해야 한다. 회귀 관점에서는 빈 칸이 아니라 scope 비고.
- **I5(비차단, minor — spec-silent documented)**: bool offset 거부(F7). work_log가 문서화했으나 계약 본문에 문장이 없다. 권고: `01-core-sot.md:53`에 "offset은 bool을 허용하지 않는다" 한 줄 추가(선택).
- **I6(비차단, minor ambiguity)**: whitespace-only idempotency key `"   "`가 수용된다(`service.py:135` `if not idempotency_key` = truthiness 검사). 계약은 "필수"만 규정하고 빈 문자열/whitespace semantics을 정의하지 않는다. probe로 `"   "` → ACCEPTED 확인. 명백한 위반은 아니나 해석 여지.
- **I7(비차단, 관찰)**: `source_ref` 생성은 service 계층에만 있고 FastAPI shell(`main.py`)에 노출되지 않는다. plan(`implementation-plan.md:206-209`)이 editor shell을 명시적으로 범위 밖으로 두었으므로 skeleton으로서 수용 가능. API envelope 확장은 후속 slice.
- **계약 자기모순**: 본 slice 범위의 `01-core-sot.md` §텍스트 정본·§저장/보존 ↔ SoT v1.2/v1.3 ↔ implementation-plan 진행 상태 간 literal 모순 없음. 단, within-block 제약은 *코드-계약 간* gap(I3)이지 계약 내 모순이 아니다.

## Verdict

**조건부 합격(Conditional Pass).**

load-bearing 이유(코드 자체는 faithful):
1. 핵심 literal이 계약과 행 단위로 일치(F1). `content_hash` 알고리즘은 **독립 재계산**으로 SHA-256/UTF-8 정확함을 입증했고(F2), offset은 다바이트 한국어로 code point semantics을 변별 입증(F4).
2. idempotency가 단일 테스트에서 양방향(under-strict 중복 차단 + over-strict 변형 body 무시)을 잠근다(F6). 보고 숫자 11/148 독립 재현(F8).
3. 패턴 sweep에서 동일 계약의 분산/중복 구현 사이트 없음(F1/F8). 계약 자기모순 0건.

조건(합격 → 완전 합격으로 승격 전):
- **C1(I1)**: 빈 칸 3종(`***` scene marker, `##`~`######` heading, `archive_project`)에 회귀 추가.
- **C2(I2)**: `content_hash`를 known SHA-256 vector로 독립 pin.
- **C3(I3)**: within-block source_ref 제약을 계약에 명시 **또는** 코드 완화 결정(소유자).

가이드라인 "빈 칸은 green bar와 무관하게 blocking" / "spec-silent-but-code-enforced는 contract gap"에 따라, 위 세 조건이 해소되기 전에는 **"합격 with risks"로 환원하지 않고 조건부 합격**을 유지한다. 비차단 I4~I7은 verdict에 영향을 주지 않는다.

**검증자는 본 검증에서 코드/테스트를 수정하지 않았다.** C1~C3의 실제 반영은 소유자 결정 사항이다.

## Outstanding items

- 본 검증은 working tree를 변경하지 않았다(probe는 별도 임시 Python 프로세스에서 실행). C1~C3 회귀/계약 보강은 소유자가 수행.
- Mongo adapter slice에서 I4(source_refs 영속 collection)를 실현해야 archive 보존 계약이 source_refs에까지 의미를 갖는다.
- transaction 기본 + non-transaction fallback guard(`01-core-sot.md:74-77`, SoT:111)와 "Mongo 저장 완료 전 분석 성공 응답 금지"(`01-core-sot.md:58,77`)는 명시적으로 본 skeleton 범위 밖이며(work_log:66, plan:209), Mongo adapter slice에서 별도 검증 필요.
- C1~C3 반영 후 본 기록 verdict를 "합격"으로 회신 갱신 가능.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# focused 회귀(worker 보고 11개)
python3 -m unittest tests.test_core_sot tests.test_application_api -v

# 전체 회귀(worker 보고 148개)
python3 -m unittest discover -s tests -p 'test_*.py'

# per-module count(실측 11 = 9 + 2)
grep -cE '^\s*def test_' tests/test_core_sot.py tests/test_application_api.py

# 독립 hash 재계산 + 다바이트 인코딩 변별(알고리즘이 SHA-256/UTF-8임을 독립 입증)
python3 - <<'PY'
import hashlib
from services.application.app.core_sot.splitter import content_hash
ko = "두번째 문장"
h = content_hash(ko)
print("sha256(utf-8)?", h == hashlib.sha256(ko.encode("utf-8")).hexdigest())
print("differs utf-16?", h != hashlib.sha256(ko.encode("utf-16-le")).hexdigest())
print("differs utf-32?", h != hashlib.sha256(ko.encode("utf-32-le")).hexdigest())
PY

# 빈 칸 probe(코드는 동작하지만 회귀 없음)
python3 - <<'PY'
from services.application.app.core_sot.splitter import split_source_blocks
from services.application.app.core_sot.models import BlockKind
print("*** scene_marker?", BlockKind.SCENE_MARKER in [b.kind for b in split_source_blocks("a\n\n***\n\nb")])
print("## heading?", split_source_blocks("## x")[0].kind == BlockKind.HEADING)
PY

# I1 archive_project 경로 회귀 부재 확인(두 테스트 파일 전체에 archive_project 호출 없음)
grep -rn "archive_project" tests/

# 패턴 sweep(content_hash 단일 구현, 분산 사이트 없음)
grep -rn "sha256\|content_hash\|normalized_text_hash" services/ tests/ | grep -v test_
```
