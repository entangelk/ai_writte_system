# Phase 2A Slice 3 (anchor order idempotency gap closure) 독립 검증

## Subject Metadata

- **날짜**: 2026-06-29
- **요청자**: 사용자 ("다음작업 검증해줘" — G1을 옵션 (a)로 닫은 gap closure)
- **검증자**: Claude (본 세션, 구현과 무관)
- **대상 slice**: Phase 2A logical_key derivation 정규화 — 같은 `source_anchors` set을 순서와 무관하게 같은 identity로 만드는 수정
- **정본 spec 참조**:
  - `docs/system-contract-sot.md` **v1.6.2** (changelog line 36; §130 anchor 순서 비포함 명시)
  - `docs/plans/02-analysis-pipeline.md` line 26, 30
  - `docs/plans/02-analysis-kickoff-decisions.md` line 66, 101
- **검증 대상 커밋**: `b5e3b7a` Close Phase 2A anchor order idempotency gap
- **작업 출처**: committed. working tree clean.
- **선행 검증**: `docs/verifications/2026-06-29/analysis_phase2a_slice2.md` (조건부 합격, 조건 C1 = G1 = logical_key anchor 순서 민감성)
- **사용자 판단 근거**: source_anchors는 "이 후보를 뒷받침하는 원문 근거들의 집합(set)"이지 ordered list가 아니다. 후보 identity는 `candidate_type + payload + source_anchors`로 dedupe가 목적이고, real LLM은 배열 순서를 안정적으로 보장하지 않으므로 순서를 identity에 넣으면 같은 후보가 retry 때 중복 저장된다. 순서 의미(ordered evidence chain)가 필요해지면 `anchor_role`/`sequence`/`evidence_order` 같은 명시 필드를 schema에 추가해 identity에 포함시키는 것으로 별도 계약화한다. 현재는 보수적으로 "의미 명시 안 된 순서는 identity에 넣지 않는다".
- **검증 입장**: (a) 정규화가 "evidence set" 의미론을 정확히 구현하는지(순서 무관·내용 민감·결정성), (b) slice2의 C1이 닫혀 verdict가 합격으로 전환되는지, (c) 정규화가 set/multiset 의미까지 다루는지를 주장 수용 없이 실험으로 증명.

## Scope

1. **C1(G1) 폐쇄 확인** — 정규화 code + named 회귀 + 정본 명시
2. **정규화 의미론 감사** — 순서 무관 / 내용 민감 / 결정성 / multiset 중복 / 빈·단일 anchor
3. **정본 일관성** — v1.6.2 ↔ plan ↔ kickoff 4곳 명시 + 버전 필드
4. **회귀 test 감사** — 새 회귀가 S9 분기를 pin 하는가
5. **스모크/보고 숫자 교차검증** — focused 31 / 전체 254-27 재현

## Methodology

```bash
# 1. 정규화 diff + 정본 명시
git show b5e3b7a -- services/application/app/analysis/extractor.py tests/test_analysis_extractor_schema.py
grep -nE "v1\.6\.2|순서.*무관|순서.*identity|순서.*포함하지 않" docs/system-contract-sot.md docs/plans/02-analysis-pipeline.md docs/plans/02-analysis-kickoff-decisions.md

# 2. 정규화 의미론 직접 실험 (순서 무관 / 내용 민감 / 결정성 / multiset)
python3 -c "..._logical_key((a1,a2)) vs (a2,a1) vs (a1,a2b) vs (a1,a1) vs (a1,)..."

# 3. focused + 전체 회귀
python3 -m unittest tests.test_analysis_extractor_schema tests.test_analysis_phase2a tests.test_analysis_source_validation  # 31
python3 -m unittest discover -s tests                                   # 254, 27 skip
```

## Findings

### Surface 1 — C1(G1) 폐쇄 (PASS)

- **code**: `extractor.py:202-211`이 `source_anchors`를 `_canonical_anchor(anchor)`로 변환 후 5-필드 tuple key로 `sorted(...)`.
- **회귀**: `test_logical_key_treats_same_anchor_set_as_order_insensitive`(`test_analysis_extractor_schema.py`) — first(anchors [A,B]) / replay(reversed [B,A]) / distinct([A, 다른 C]) 3후보로 `replay.logical_key == first.logical_key`(over-strict 가드: 순서 바껴도 같음) + `distinct.logical_key != first.logical_key`(under-strict 가드: 내용 다르면 다름) 양방향 pin.
- **정본**: v1.6.2 changelog + §130 + plan line 26/30 + kickoff line 66/101 — 4곳에 "같은 source_anchors set은 provider 출력 순서와 무관하게 같은 identity로 정규화" 명시.

slice2의 conditional pass 조건 C1이 code·회귀·정본 3축에서 모두 닫힘.

### Surface 2 — 정규화 의미론 감사

직접 실험 결과:
```
order-independent  (a1,a2)==(a2,a1): True    # G1 fix 확정
content-sensitive  (a1,a2)!=(a1,a2b): True   # end_offset 달라지면 다른 key
deterministic      (a1,a2)==(a1,a2): True
dup vs single      (a1,a1)==(a1,): False     # D1
three-permuted     (a1,a2,a1)==(a2,a1,a1): True   # multiset 순서 무관
```

- 순서 무관 / 내용 민감 / 결정성 / multiset 순서 무관: 모두 보장. ✅
- 정렬 key tuple `(source_ref_id, start_offset, end_offset, quote, content_hash)`는 anchor 5필드 전부를 포함하므로, 어느 필드가 바뀌어도 identity가 달라짐. 정본 "Anchor 내용이 다르면 별도 candidate identity"와 정합. ✅
- non-ASCII(한국어 quote) 정렬은 code point 기준이나 deterministic이면 충분. ✅

### Surface 3 — 정본 일관성 (PASS, 단 D2)

- §130 / plan / kickoff 4곳이 동일 계약을 가리킴. v1.6.2 entry는 slice2 검증 기록을 근거로 올라감. ✅
- **D2**: `docs/system-contract-sot.md:4` "계약 버전" 필드가 여전히 `v1.6`이고 changelog는 v1.6.2까지 있다. minor를 v1.6 family로 해석할 수 있으나, changelog가 v1.6.1/v1.6.2를 별도 entry로 구분하므로 line 4는 최신(v1.6.2)을 가리키는 것이 일관적이다. (slice2 검증에서 필자가 이 mismatch를 놓쳤음.)

### Surface 4 — 회귀 test 감사

새 회귀 `test_logical_key_treats_same_anchor_set_as_order_insensitive`는 slice2의 S9 빈 칸을 정확히 폐쇄:
- assertion이 byproduct가 아닌 contract 분기(순서 무관 + 내용 민감)를 직접 pin. ✅
- public surface(`AnalysisCandidateDraft.logical_key`) 타겟. ✅
- `_anchor` 헬퍼 도입으로 가독성 개선 (surgical).

boundary matrix의 S9 분기가 이제 named test에 매핑됨.

### Surface 5 — 스모크/보고 숫자 교차검증 (PASS)

```
python3 -m unittest tests.test_analysis_extractor_schema tests.test_analysis_phase2a tests.test_analysis_source_validation
  → Ran 31 tests ... OK
python3 -m unittest discover -s tests
  → Ran 254 tests ... OK (skipped=27)
```

보고 "focused 31" / "전체 254, 27 skip"과 정확히 일치.

## Issues / Risks

- **D1 (Low, non-blocking)**: 정규화가 `sorted(list)`라 multiset 중복을 유지한다. 실험 `(a1,a1) != (a1,)`. 사용자 rationale과 정본이 "**set**"이라 명시하므로, 이론적으로 `{A,A} == {A}`여야 하나 구현은 그렇지 않다. 같은 anchor를 provider가 중복 출력하는 극희귀 케이스에서만 영향이며, 현 contract가 multiset을 명시적으로 다루지 않으므로 위반은 아니다. "evidence set" rationale을 엄밀히 적용하려면 dedupe가 일관적이지만, 현실 발생 빈도와 현 contract silent를 고려해 blocking에서는 제외한다.
- **D2 (Low-Med, non-blocking, 문서)**: SoT line 4 버전 필드가 v1.6.2로 갱신되지 않음. 정본 계약 인덱스의 버전 표시가 실제 버전과 불일치.
- **D3 (Low, 권장)**: 사용자 rationale의 forward path("순서 의미 필요시 `anchor_role`/`sequence`/`evidence_order`로 별도 계약화")가 정본에 추적 가능하게 기록되지 않음. 현재 contract(순서 비포함)에는 영향 없으나, ordered evidence chain이 필요해지는 시점에 확장 정책이 ambiguous해진다. 미확정/확장 후보로 정본에 한 줄 note를 두면 다음 검증자가 guess하지 않는다.

## Verdict — 합격 (Pass)

**Load-bearing 이유**:

1. slice2의 conditional pass 조건 C1(G1)이 code 정규화 + named 회귀 + 정본 v1.6.2 명시 3축에서 닫혔음 (Surface 1 ✅).
2. 정규화가 "evidence set" 의미론의 핵심 — 순서 무관·내용 민감·결정성·multiset 순서 무관 — 을 실험으로 증명 (Surface 2 ✅).
3. 새 회귀가 slice2의 S9 boundary 빈 칸을 양방향 가드로 폐쇄 (Surface 4 ✅).
4. 정본 4곳 일관 (D2 버전 필드 표시 제외), 보고 숫자 31 / 254-27 재현 (Surface 3/5 ✅).

**조건부 → 합격 전환 근거**: 이전 검증(slice2)이 conditional였던 유일한 load-bearing 이유는 G1이었다. G1이 (a) 방식(정규화)으로 code·회귀·정본 모두에서 닫혔으므로 conditional의 조건이 충족되어 합격으로 전환한다.

**D1/D2/D3은 합격을 뒤집지 않는다**: 모두 non-blocking이다 — D1은 극희귀 multiset edge이자 현 contract silent 영역, D2는 문서 버전 표시, D3은 확장 note 권장. 어느 것도 현재 정본 계약을 위반하거나 boundary matrix 빈 칸이 아니다.

## Outstanding items

- D1(set vs multiset): "evidence set" rationale을 엄밀히 하면 dedupe가 일관적이나, 현실 발생 극희귀. 사용자 판단 시后续 보강 가능(정본 multiset 정의 + dedupe + 회귀).
- D2: SoT line 4 버전 필드를 v1.6.2로 갱신 권장.
- D3: 정본에 "순서 의미는 별도 필드로 확장" note 추가 권장(다음 slice에서 ordered evidence chain 필요 시).
- 본 검증은 code를 수정하지 않음 (CLAUDE.md: 검증 실패 시 검증자가 자동 수정하지 않고 사용자에게 회신). 본 slice는 합격이므로 발행 결정은 사용자에게.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# focused + 전체 회귀 (31 / 254-27)
python3 -m unittest tests.test_analysis_extractor_schema tests.test_analysis_phase2a tests.test_analysis_source_validation
python3 -m unittest discover -s tests

# G1 fix + 정규화 의미론 증명 (D1 포함)
python3 -c "
from services.application.app.analysis.extractor import _logical_key
from services.application.app.analysis.models import CandidateSourceAnchor, AnalysisCandidateType
CT=AnalysisCandidateType.CHARACTER_OBSERVATION; P={'name':'민아','observation':'x'}
a1=CandidateSourceAnchor(source_ref_id='r1',start_offset=0,end_offset=2,quote='민아',content_hash='h1')
a2=CandidateSourceAnchor(source_ref_id='r2',start_offset=5,end_offset=7,quote='편지',content_hash='h2')
a2b=CandidateSourceAnchor(source_ref_id='r2',start_offset=5,end_offset=8,quote='편지',content_hash='h2')
def k(a): return _logical_key(candidate_type=CT,source_anchors=a,payload=P)
print('order-independent:', k((a1,a2))==k((a2,a1)))          # True = G1 fix
print('content-sensitive:', k((a1,a2))!=k((a1,a2b)))         # True
print('dup vs single   :', k((a1,a1))==k((a1,)))             # False = D1 (multiset)
"

# 정본 명시 교차 확인
grep -nE "v1\.6\.2|순서와 무관|순서는 identity에 포함하지 않" \
  docs/system-contract-sot.md docs/plans/02-analysis-pipeline.md docs/plans/02-analysis-kickoff-decisions.md
```
