# Phase 2A Slice 2 (taxonomy extraction schema + logical_key derivation) 독립 검증

## Subject Metadata

- **날짜**: 2026-06-29
- **요청자**: 사용자 ("다음 작업 검증해줘" — schema slice + 이전 slice 보강 포함 커밋)
- **검증자**: Claude (본 세션, 구현과 무관)
- **대상 slice**: Phase 2A 둘째 slice — 3종 최소 payload schema + AnalysisService 저장 경로 payload 검증 연결 + fake-provider extraction adapter + deterministic logical_key derivation
- **정본 spec 참조**:
  - `docs/system-contract-sot.md` **v1.6 / v1.6.1** (changelog line 36-37; §129 candidate retry identity + logical_key derivation; §300-301 최소 payload schema + extraction adapter)
  - `docs/plans/02-analysis-pipeline.md` line 26, 29-30 (Phase 2A schema/derivation/adapter)
  - `docs/plans/02-analysis-kickoff-decisions.md` line 66, 90, 100-101 (동일 계약)
- **검증 대상 커밋**:
  - `0232436` Implement Phase 2A taxonomy extraction schema (이번 slice 본체)
  - `72c81fc` Implement Phase 2A source validation (중간 slice, F4 해소)
  - `e81f12f` Implement Phase 2A analysis domain skeleton (domain slice + 검증기록/보강, F1/F2/F3 해소)
- **작업 출처**: committed. working tree clean.
- **선행 검증**: `docs/verifications/2026-06-29/analysis_phase2a_slice1.md` (조건부 합격, 조건 C1=NaN confidence 회귀, C2=action≠CREATE 회귀, C3=logical_key 정본 명시)
- **검증 입장**: (a) 선행 검증의 C1/C2/C3가 실제로 닫혔는지, (b) 이번 slice의 schema/derivation literal이 정본에 정확히 반영됐는지, (c) derivation이 정본 "같은 provider retry payload는 같은 key"를 정말 보장하는지(순서/정규화/비ASCII)를 주장 수용 없이 증명.

## Scope

1. **선행 검증 조건(C1/C2/C3/F4) 폐쇄 확인** — 코드 + named 회귀 존재 여부
2. **정본 v1.6.1 literal ↔ code 일치** — 3종 schema field / logical_key derivation 입력 / provider `{candidates:[...]}`
3. **정본 내부 일관성** — SoT §129/§300-301 ↔ plan ↔ kickoff 간 모순
4. **Boundary matrix → test 추적** — schema(extra/missing/non-empty), derivation(deterministic/payload-sensitive/anchor-순서), provider malformed 전 분기
5. **구현 code 감사** — `schema.py` / `extractor.py`(`_logical_key`) / `service.py` payload 연결 / `source.py`
6. **회귀 test 감사** — focused 30개가 contract를 pin 하는가 (green bar ≠ spec 검증)
7. **스모크/보고 숫자 교차검증** — focused 30 / 전체 253-27 재현

## Methodology

정본을 scope하고 이번 slice boundary matrix를 세운 뒤 code/test 대조. derivation 결정성은 의심 포인트를 직접 실험으로 증명.

```bash
# 1. 정본 literal 위치
grep -nE "logical_key|canonical JSON|SHA-256|name.*observation|event_observation \{|open_question|candidates:|source_anchors" \
  docs/system-contract-sot.md docs/plans/02-analysis-pipeline.md docs/plans/02-analysis-kickoff-decisions.md

# 2. focused + 전체 회귀 재현
python3 -m unittest tests.test_analysis_extractor_schema tests.test_analysis_phase2a tests.test_analysis_source_validation  # 30
python3 -m unittest discover -s tests                                   # 253, 27 skip

# 3. F1 service 보강 증명 (이전 검증에서 ACCEPTED → 이제 reject)
python3 -c "...record_candidate(confidence=float('nan'))..."            # rejected OK 확인

# 4. G1 derivation anchor-순서 민감성 증명
python3 -c "..._logical_key(source_anchors=(a1,a2)) vs (a2,a1)..."      # keys equal? False
```

## Findings

### Surface 1 — 선행 검증 조건 폐쇄 (PASS, C1/C2/C3 + F4 모두 해소)

| 선행 조건 | 코드 보강 | named 회귀 | 결과 |
|---|---|---|---|
| C1 (NaN confidence reject) | `service.py:258` `if not (0.0 <= normalized <= 1.0)` (NaN → `not False` → raise). `extractor.py:147` 동일 패턴 | `test_confidence_rejects_nan` (phase2a line 279) + extractor NaN case(line 206) | ✅ 실험으로 service NaN reject 직접 확인 |
| C2 (action≠CREATE 회귀) | `service.py:311-314` `_validate_action` (기존) | `test_action_other_than_create_is_rejected` (phase2a line 303, `action="update"`) | ✅ |
| C3 (logical_key 정본 명시) | SoT §129 + `service.py:331-334` `_validate_logical_key` | — (정본/구조) | ✅ |
| F4 (source_ref cross-project) | `service.py:274-304` `_validate_source_anchors` (72c81fc) | `test_record_candidate_rejects_cross_project_source_ref` / `_quote_hash_and_span_mismatch` / `_anchor_id_list_mismatch` / `_requires_source_anchors_when_resolver_is_configured` | ✅ |

slice1의 conditional pass 조건 3개(C1/C2/C3)와 out-of-slice로 남았던 F4가 모두 닫혔음을 1차/2차 source에서 재확인.

### Surface 2 — 정본 literal ↔ code 일치 (PASS)

| 정본 literal (v1.6.1 §300 / kickoff #90) | code 위치 | 일치 |
|---|---|---|
| `character_observation {name, observation}` | `schema.py:16` | ✅ |
| `event_observation {event}` | `schema.py:17` | ✅ |
| `open_question_observation {question}` | `schema.py:18` | ✅ |
| 모든 field non-empty string | `schema.py:40` | ✅ |
| 추가/누락 field malformed reject | `schema.py:34` (`observed_fields != allowed_fields`) | ✅ closed set 비교 |
| logical_key = `candidate_type + payload + source_anchors` canonical JSON SHA-256 | `extractor.py:193-214` | ✅ |
| provider 출력 top-level `{candidates:[...]}` | `extractor.py:72-76` | ✅ |

파라프레이즈 없이 일치. logical_key prefix `f"{candidate_type.value}:{sha256...}"`(`extractor.py:214`)는 정본이 명시하지 않은 구현 detail이나 identity에 영향 없음.

### Surface 3 — 정본 내부 일관성 (PASS)

- §129(candidate retry identity = project_id+task_id+logical_key, derivation = candidate_type+payload+source_anchors canonical JSON SHA-256) = plan line 26 = kickoff line 66/101. 일치.
- §300(schema 3종 + extra/missing reject) = plan line 29 = kickoff line 90. 일치.
- §301(provider `{candidates:[...]}`, type/provenance/confidence/source_anchors/payload 검증) = plan line 30. 일치.
- §300 "모든 payload field는 non-empty string이며 추가 field와 누락 field는 malformed payload로 거절한다" ↔ `schema.py:34/40` 양방향 대응.

모순 없음.

### Surface 4 — Boundary matrix → test 추적

| # | Boundary | should fire / NOT fire | code 강제 | test trace | 상태 |
|---|---|---|---|---|---|
| S1-3 | 3종 schema shape | fire 각 type | `schema.py:15-19` | `test_all_three_phase2a_payload_shapes_are_accepted` (subTest 3종全覆盖) | ✅ |
| S4 | extra field reject | NOT extra | `schema.py:34` | `test_malformed_payload_is_rejected_by_service` (`mood` 추가) | ✅ |
| S5 | missing field reject | NOT missing | `schema.py:34` | 동일 (`observation` 누락) | ✅ |
| S6 | non-empty string | NOT empty | `schema.py:40` | 동일 (`observation: ""`) | ✅ |
| S7 | logical_key deterministic | fire 같은입력→같은key | `extractor.py:213` sort_keys | `test_logical_key_is_stable_but_changes_when_payload_changes` (replay==first) | ✅ |
| S8 | logical_key payload-sensitive | NOT 다른payload 같은key | payload 포함 | 동일 (distinct!=first) | ✅ |
| S9 | logical_key anchor-순서 독립 | fire 같은set 다른순서→같은key | `extractor.py:202` **list 순서 보존** | **(없음)** | ⚠️ G1 |
| S10 | provider `{candidates:[...]}` | fire / NOT 비object·empty | `extractor.py:72-76` | `test_extractor_rejects_malformed_provider_payload` (`[]`, empty) | ✅ |
| S11 | candidate 5 field 정확히 | NOT extra/missing | `extractor.py:82-91,124-126` | 동일 (malformed) | ✅ |
| S12 | provider unsupported type | NOT 다른 type | `extractor.py:129-133` | 동일 (`location_observation`) | ✅ |
| S13 | provider user_declared | NOT user_declared | `extractor.py:136-140` | 동일 (`user_declared`) | ✅ |
| S14 | provider NaN confidence | NOT NaN | `extractor.py:147` `not (0<=x<=1)` | 동일 (`float("nan")`) | ✅ |
| S15 | provider anchor offset valid | NOT end<=start | `extractor.py:168` | 동일 (end==start) | ✅ |
| S16 | service 경로 payload 검증 연결 | fire schema 경유 | `service.py:183,322-329` | `test_malformed_payload_is_rejected_by_service` | ✅ |

16개 분기 중 15개는 code 강제 + named test 1:1 pin. 빈 칸 1건(G1/S9)은 아래 Issues에서 처리.

### Surface 5 — 구현 code 감사

#### schema.py — closed-set 검증 (양호)

`schema.py:31-43`: `observed_fields != allowed_fields`(set 비교)로 **extra/missing 동시 차단**, field 순서 무관. 각 값 `isinstance(value, str) or not value`로 non-empty string 강제. 반환은 normalized `dict[str,str]`(값 복사)로 derivation에 안전하게 feed. contract §300과 정합.

- 경미 관찰: whitespace-only field(`"  "`)는 non-empty로 통과. contract "non-empty string" 해석상 허용 가능(위반 아님).

#### extractor.py — confidence/field 검증 (양호, F1 보강 반영)

- `_confidence`(line 143-149): `not (0.0 <= normalized <= 1.0)`로 NaN reject. service.py와 동일 패턴. ✅
- `_require_fields`(line 124-126): candidate 5 field / anchor 5 field를 set 비교로 closed-set 강제. ✅
- `_source_anchor`(line 158-178): `end_offset <= start_offset` reject(line 168). ✅

#### G1 — logical_key derivation의 source_anchors 순서 민감성 (Medium, idempotency 위험 + contract gap)

`extractor.py:193-214`:
```python
canonical = {
    "candidate_type": candidate_type.value,
    "payload": dict(payload),
    "source_anchors": [ {...} for anchor in source_anchors ],   # list — 순서 보존
}
encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode("utf-8")
return f"{candidate_type.value}:{hashlib.sha256(encoded).hexdigest()}"
```

`sort_keys=True`는 **dict key만 정규화**한다. `source_anchors`는 list이므로 **element 순서가 그대로 hash에 들어간다**. 직접 실험 증명:

```
G1 anchor-order: 같은 set, 순서만 swap → keys equal? False
G1 via parse path: swap 순서 candidate 2개 → same logical_key? False
```

- 정본 §129는 "같은 provider retry payload는 같은 key가 되고, payload 또는 anchor가 다른 관찰은 별도 candidate가 된다"고 한다. "같은 payload"가 anchor **순서**를 포함하는지는 **spec-silent**.
- LLM provider는 비결정적이므로, 같은 관찰에 대해 anchor를 `[A,B]`로 낼 때도 `[B,A]`로 낼 때도 있음 → 같은 후보가 서로 다른 logical_key로 derive → 같은 task에 **중복 candidate**로 저장됨. 정본 idempotency 보장("같은 provider retry payload는 같은 key")이 무너진다.
- 현재 fake provider는 deterministic이라 latent. real provider 연결 시 폭발.
- S9(anchor 순서 독립성) 회귀 부재 → boundary matrix 빈 칸.
- CLAUDE.md: "Spec-silent-but-code-enforced is a contract gap — surface it as a contract amendment request before the slice can close." anchor 순서 동등성을 정본이 명시하거나, idempotency를 원하면 derivation이 anchor를 정렬/정규화해야 한다.

### Surface 6 — 회귀 test 감사 (green bar ≠ spec 검증)

focused 3개 파일 재실행 → **30 통과**(보고 일치). 각 assertion 확인:

- `test_all_three_phase2a_payload_shapes_are_accepted`: subTest로 3종 shape全覆盖 + 저장 payload 원문 보존 assert. over-strict 가드. ✅
- `test_malformed_payload_is_rejected_by_service`: missing/empty/extra/wrong-type 4개 subTest. under-strict 가드. ✅
- `test_extractor_rejects_malformed_provider_payload`: root array / empty candidates / unsupported type / user_declared / NaN / missing field / invalid offset 7개 subTest. 풍부한 under-strict. ✅
- `test_logical_key_is_stable_but_changes_when_payload_changes`: 동일 입력 동일 key + 다른 payload 다른 key. over/under 양방향. ✅
- **누락**: S9(anchor 순서). 위 G1과 동일.

assertion은 모두 public surface(`AnalysisCandidateDraft.logical_key`/`payload`/`source_anchors`, `candidate.payload`, provider request)를 타겟. ✅

### Surface 7 — 스모크/보고 숫자 교차검증 (PASS)

```
python3 -m unittest tests.test_analysis_extractor_schema tests.test_analysis_phase2a tests.test_analysis_source_validation
  → Ran 30 tests ... OK
python3 -m unittest discover -s tests
  → Ran 253 tests ... OK (skipped=27)
```

보고 "focused 30" / "전체 253, 27 skip"과 정확히 일치.

## Issues / Risks

- **G1 (Medium, blocking 조건)**: logical_key derivation이 `source_anchors` list 순서에 민감. 같은 anchor set을 다른 순서로 주면 다른 key → 같은 관찰 중복 candidate. 정본 idempotency("같은 provider retry payload는 같은 key") 위반 가능. 실험으로 확정. 회귀도 없음.
- **경미 관찰 (contract 위반 아님)**: `service.record_candidate`가 여전히 `logical_key`를 호출자 제공 파라미터로 받는다(`service.py:167`). extractor를 거치지 않으면 derivation을 우회해 임의 key를 줄 수 있음. 정본 §129는 "기본 derivation은 extraction adapter"로 한정하므로 service 직접 호출 경로는 별도이나, 두 경로가 섞이면 idempotency identity가 일관되지 않을 수 있음. 현재 회귀는 extractor-derived 경로만 다룸.
- **경미 관찰**: logical_key에 confidence/provenance 미포함은 정본 §129와 일치(의도적 — 같은 관찰의 confidence 변동은 같은 후보). 동일 logical_key로 다른 confidence replay 시 service가 첫 값을 유지(`service.py:201-205`)하여 정합.
- **경미 관찰**: whitespace-only payload field 허용. "non-empty string" 해석상 허용 가능.

## Verdict — 조건부 합격 (Conditional Pass)

**Load-bearing 이유**:

1. 선행 검증(slice1) 조건 C1/C2/C3 + F4가 모두 코드·named 회귀로 닫혔음을 재확인 (Surface 1 ✅).
2. 정본 v1.6.1 literal(3종 schema / derivation 입력 / provider envelope)이 code에 정확히 반영됨 (Surface 2 ✅).
3. 정본 내부 일관성 양호, 모순 없음 (Surface 3 ✅).
4. 16개 boundary 중 15개는 code 강제 + named test 1:1 pin, 양방향 가드 충실 (Surface 4/6 ✅).
5. 보고 숫자 30 / 253-27 재현 확인 (Surface 7 ✅).

**조건 (합격으로 전환하기 위해 필요)**:

- **C1 (필수)**: G1 해소 — 다음 둘 중 하나.
  - (a) 정본(§129/kickoff)에 "같은 anchor set은 순서와 무관하게 같은 logical_key"를 명시하고 derivation이 anchor를 정렬·정규화(`sorted(...)` 또는 frozenset 기반 canonical)하도록 변경 + 순서 무관 idempotency 회귀 추가, 또는
  - (b) 정본이 "anchor 순서도 identity에 포함"을 명시적 계약으로 채택(현재 구현과 일치) + S9 회귀 추가로 그 경계를 lock.
  - 어느 쪽이든 **contract가 anchor 순서 동등성을 silent로 두면 안 된다**. real provider 연결 전에 결정해야 한다.

**왜 "합격"이 아닌가**: G1은 정본 idempotency 보장("같은 provider retry payload는 같은 key")의 빈 칸이자 spec-silent-but-code-enforced contract gap이다. CLAUDE.md는 이런 경우 "close 전에 contract amendment로 surface하라"고 요구한다. S9 분기가 named test에 매핑되지 않았으므로 boundary matrix에 빈 칸이 존재한다.

**왜 "불합격"이 아닌가**: G1은 현재 fake provider가 deterministic이라 즉시 발현되지 않는 latent risk이며, 정본 해석(순서를 "다른 anchor"로 볼지)에 따라 (b) 경로로 회귀 1건만 추가해도 폐쇄 가능하다. 나머지 15개 경계·정본 일치·선행 조건 폐쇄는 모두 양호하다.

## Outstanding items

- 검증 대상은 committed(3개 커밋), working tree clean. 추가 발행은 사용자 결정 대기.
- G1(C1) 해소 시 본 검증 Verdict를 "합격"으로 갱신 필요(재검증 권장).
- "service 직접 호출 시 derivation 우회" 경미 관찰은 다음 slice(extraction runner/orchestration)에서 service 진입점 정책이 정해지면 함께 정리 권장.
- 본 검증은 code를 수정하지 않음 (CLAUDE.md: 검증 실패 시 검증자가 자동 수정하지 않고 사용자에게 회신).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# focused + 전체 회귀 (30 / 253-27)
python3 -m unittest tests.test_analysis_extractor_schema tests.test_analysis_phase2a tests.test_analysis_source_validation
python3 -m unittest discover -s tests

# F1 service 보강 확인 (이전 검증 ACCEPTED → 이제 reject)
python3 -c "
from services.application.app.analysis.service import AnalysisService, InMemoryAnalysisRepository, InvalidAnalysisCandidate
from services.application.app.analysis.models import AnalysisCandidateType, AnalysisCandidateAction, AnalysisProvenance
s=AnalysisService(InMemoryAnalysisRepository())
j=s.create_job(project_id='p',snapshot_id='s',idempotency_key='k').job
t=s.create_task(project_id='p',job_id=j.id,candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION)
try:
    s.record_candidate(project_id='p',task_id=t.id,logical_key='lk',candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,action=AnalysisCandidateAction.CREATE,provenance=AnalysisProvenance.AI_INFERRED,confidence=float('nan'),source_ref_ids=('r1',),payload={'name':'x','observation':'y'})
    print('NaN ACCEPTED')
except InvalidAnalysisCandidate as e:
    print('NaN rejected:', e)   # rejected = C1 보강 확인
"

# G1 derivation anchor-순서 민감성 증명
python3 -c "
from services.application.app.analysis.extractor import _logical_key
from services.application.app.analysis.models import CandidateSourceAnchor, AnalysisCandidateType
a1=CandidateSourceAnchor(source_ref_id='r1',start_offset=0,end_offset=2,quote='민아',content_hash='h1')
a2=CandidateSourceAnchor(source_ref_id='r2',start_offset=5,end_offset=7,quote='편지',content_hash='h2')
p={'name':'민아','observation':'x'}
k12=_logical_key(candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,source_anchors=(a1,a2),payload=p)
k21=_logical_key(candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,source_anchors=(a2,a1),payload=p)
print('same set swapped order -> same key?', k12==k21)   # False = G1 재현
"

# 정본 literal 교차 확인
grep -nE "name.*observation|event_observation \{|open_question_observation \{|logical_key|canonical JSON SHA-256|candidates:" \
  docs/system-contract-sot.md services/application/app/analysis/schema.py services/application/app/analysis/extractor.py
```
