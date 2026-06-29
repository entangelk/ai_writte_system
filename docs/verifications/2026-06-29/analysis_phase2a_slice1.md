# Phase 2A Slice 1 (analysis domain model + in-memory repository) 독립 검증

## Subject Metadata

- **날짜**: 2026-06-29
- **요청자**: 사용자 ("작업 AI가 작업한 분에 대해서 검증하고 의심하고 또 의심해줄래?")
- **검증자**: Claude (본 세션, 구현과 무관)
- **대상 slice**: Phase 2A 첫 slice — analysis 도메인 모델 + in-memory repository/service + approved SoT v1.6 literal 런타임 강제
- **정본 spec 참조**:
  - `docs/system-contract-sot.md` **v1.6** (계약 변경 이력 line 36; §127 `create_source_ref` non-idempotent; §131-138 Candidate 원칙; §140-145 추적성; §287-299 Phase 2 Analysis Pipeline)
  - `docs/plans/02-analysis-kickoff-decisions.md` (Approved for Phase 2A kickoff, 2026-06-29)
  - `docs/plans/02-analysis-pipeline.md` Phase 2A 섹션 (line 15-26), 착수 전 결정사항 (line 108-118)
- **작업 출처**: working tree, **uncommitted** (`services/application/app/analysis/` 전체가 untracked; `tests/test_analysis_phase2a.py` untracked; `tests/test_core_sot_mongo.py` 및 5개 문서 modified). commit hash 없음.
- **검증 입장**: 작업 AI의 "잠근 경계" 주장을 그대로 수용하지 않고, 정본 계약에서 boundary matrix를 먼저 세운 뒤 code/test가 그 분기를 1:1로 잠갔는지, 그리고 정본이 spec-silent인 부분을 code가 임의로 contract화하진 않았는지를 증명.

## Scope

1. **정본 계약 ↔ code literal 일치**: Phase 2A approved literal(taxonomy 3종 / provenance 2종 / action / status / confidence range)이 code에 변경 없이 나타나는가
2. **정본 내부 일관성**: SoT v1.6 ↔ kickoff decisions ↔ plan Phase 2A 섹션 간 모순 유무
3. **Boundary matrix → test 추적**: 각 "should fire" / "should NOT fire" 분기가 named regression test에 매핑되는가 (빈 칸 = blocking)
4. **구현 code 감사**: `models.py` / `service.py` / `repository.py` — 경계가 runtime에서 실제 강제되는가, spec-silent-but-code-enforced gap 있는가
5. **회귀 test 감사**: `test_analysis_phase2a.py` 15개 — assertion이 contract를 pin 하는가, under/over-strict 양방향 가드 존재하는가 (green bar ≠ spec 검증)
6. **스모크/보고 숫자 교차검증**: 보고된 15 통과 / 238 통과 27 skip을 직접 재현
7. **Mongo skip probe 보강**: `tests/test_core_sot_mongo.py` cleanup 변경이 기존 "미가용 시 skip" 계약과 정합하는가

## Methodology

정본 계약을 먼저 scope하고 boundary matrix를 세운 뒤, code와 test를 matrix에 대해 감사. 작업 AI의 verification claim은 재도출.

```bash
# 1. 정본 literal 위치 확인
grep -niE "phase 2a|analysis_candidate|character_observation|source_observed|needs_review|user_declared|ai_inferred|open_question|event_observation|create_source_ref|v1\.6" \
  docs/system-contract-sot.md docs/plans/02-analysis-pipeline.md

# 2. focused 회귀 재현
python3 -m unittest tests.test_analysis_phase2a -v          # 15, 보고와 비교

# 3. confidence NaN/inf 우회 실험 (의심 포인트 직접 증명)
python3 -c "...record_candidate(confidence=float('nan'))..." # NaN ACCEPTED 확인

# 4. 누락 가드 실험 (action≠CREATE, logical_key 빈값)
python3 -c "...record_candidate(action='update', ...)..."    # reject는 되나 test 없음 확인

# 5. 전체 discovery 재현
python3 -m unittest discover -s tests                        # 238, 27 skip, 보고와 비교

# 6. Mongo probe 보강 diff
git diff tests/test_core_sot_mongo.py
```

## Findings

### Surface 1 — 정본 literal ↔ code 일치 (PASS)

| 정본 literal (SoT v1.6 line 36 / §291-295, kickoff #1-#5, plan line 19-24) | code 위치 | 일치 |
|---|---|---|
| `character_observation` | `models.py:12` | ✅ |
| `event_observation` | `models.py:13` | ✅ |
| `open_question_observation` | `models.py:14` | ✅ |
| `source_observed` | `models.py:18` | ✅ |
| `ai_inferred` | `models.py:19` | ✅ |
| `create` (action) | `models.py:23` | ✅ |
| `needs_review` (status) | `models.py:27` | ✅ |
| `0.0 <= confidence <= 1.0` | `service.py:234` (`if normalized < 0.0 or normalized > 1.0`) | ⚠️ literal은 일치하나 NaN 우회 — Surface 4 F1 |

파라프레이즈 없이 정본 literal이 그대로 code에 존재. `user_declared`는 enum에 없고 `service.py:261-263`(`_validate_provenance`, isinstance 검사)로 runtime reject. approved subset 범위 내 literal은 정합.

### Surface 2 — 정본 내부 일관성 (PASS)

- §127(create_source_ref non-idempotent + candidate/job 저장층 idempotency 소유) = kickoff #6 = plan line 25. 일치.
- §293-294(provenance/action/status) = kickoff #2/#3/#4 = plan line 21-23. 일치.
- §295(confidence range-only) = kickoff #5 = plan line 24. 일치.
- §36 v1.6 changelog entry = kickoff "승인된 결정 요약". 일치.
- 문서 우선순위: kickoff decisions("Approved for Phase 2A kickoff", SoT line 57) > plan 전체("Draft", SoT line 58). 구현은 approved subset을 따름. 정합.

정본 섹션 간 / changelog 간 모순 없음.

### Surface 3 — Boundary matrix → test 추적

| # | Boundary (정본) | should fire / NOT fire | code 강제 | test trace | 상태 |
|---|---|---|---|---|---|
| B1 | taxonomy 3종만 | fire 3종 / NOT 다른 type | `models.py:11-14`, `service.py:251-253` | `test_all_phase2a_candidate_types_can_create_tasks` (3종全覆盖) + `test_unknown_candidate_type_is_rejected` | ✅ 양방향 |
| B2 | `user_declared` runtime reject | NOT `user_declared` | `models.py:17-19`(enum 없음), `service.py:261-263` | `test_user_declared_provenance_is_rejected_until_writingbrief_exists` | ✅ |
| B3 | action `create` only | NOT `update`/`add_evidence`/… | `models.py:22-23`, `service.py:255-258`(`_validate_action`), `service.py:189`(stored value CREATE 강제) | **(없음)** — reject path 회귀 부재 | ⚠️ F2 빈 칸 |
| B4 | status `needs_review` 고정 | 항상 needs_review | `models.py:26-27`, `service.py:190` | `test_record_candidate_locks_phase2a_literals_and_needs_review` | ✅ |
| B5 | confidence `0.0..1.0` | fire 0.0/1.0 / NOT 범위 외 | `service.py:229-236` | `test_confidence_range_allows_zero_and_one_but_rejects_out_of_range` + `test_confidence_rejects_bool_and_non_number` | ⚠️ F1 NaN 우회 |
| B6 | 같은 logical candidate retry 중복 방지 | NOT 중복 | `service.py:174-181` | `test_same_task_retry_replays_logical_candidate_without_duplicate` | ✅ |
| B7 | 같은 span 여러 candidate 허용 | fire | `repository.py` key=(project,task,logical_key) | `test_same_source_span_can_support_different_logical_candidates` | ✅ over-strict 가드 포함 |
| B8 | project isolation | NOT cross-project | `service.py:208-227`, `service.py:202-206` | `test_task_creation_enforces_project_isolation` + `test_cross_project_candidate_access_is_not_listed` | ✅ |
| B9 | job retry idempotency | fire replay / NOT 중복 | `service.py:112-130` | 3개(idempotent replay / distinct key / empty key reject) | ✅ 양방향 |
| B10 | candidate_type == task type | NOT mismatch | `service.py:169-170` | `test_candidate_type_must_match_task` | ✅ |
| B11 | source_ref_ids required | NOT empty | `service.py:238-248` | `test_source_ref_ids_are_required_but_not_deduped_as_candidate_identity` | ✅ |
| B12 | logical_key required | NOT empty | `service.py:163-164` | **(없음)** | ⚠️ F3(contract-silent) |

12개 분기 중 9개는 code 강제 + test pin이 1:1. 빈 칸 3건(F1/F2/F3)은 아래 Issues에서 개별 처리.

### Surface 4 — 구현 code 감사

#### F1 — confidence NaN이 검증을 관통 (Medium, 정본 literal 위반)

`service.py:229-236`:
```python
@staticmethod
def _validate_confidence(confidence: float) -> float:
    if isinstance(confidence, bool) or not isinstance(confidence, Real):
        raise InvalidAnalysisCandidate("confidence must be a number")
    normalized = float(confidence)
    if normalized < 0.0 or normalized > 1.0:        # NaN: False or False → 통과
        raise InvalidAnalysisCandidate("confidence must be between 0.0 and 1.0")
    return normalized
```

직접 증명 (실행 결과):
```
NaN: ACCEPTED, stored confidence=nan   <== 정본 0.0 <= confidence <= 1.0 위반
+inf: rejected
-inf: rejected
bool-True: rejected
```

- 정본 §295 / kickoff #5 / plan line 24는 `0.0 <= confidence <= 1.0`만 강제. Python에서 `0.0 <= float('nan') <= 1.0`은 `False`이므로 NaN은 이 구간 밖이며 reject 대상이 자명함.
- code는 `+inf`/`-inf`는 막으면서 **NaN만 관통** — classic NaN 비교 함정이자 정본 literal에 대한 under-strict 위반.
- B5의 "NOT fire(범위 외)" 분기는 `-0.01`/`1.01`로 test되나 NaN 케이스는 우회. regression도 없음.
- 위험: AI extraction confidence가 0/0 등으로 NaN이 될 수 있으며, NaN candidate가 저장되면 향후 review/gate 비교 로직이 NaN 전파로 붕괴. 현재 slice는 in-memory service라 즉시 폭발하진 않으나 confidence 검증 메서드가 정본 literal을 enforce한다고 주장하면서 핵심 edge를 놓침.

#### F2 — action≠CREATE reject path 회귀 부재 (Low, boundary matrix 빈 칸)

`service.py:255-258`은 `action is not AnalysisCandidateAction.CREATE`이면 reject("Phase 2A only supports create"). 직접 실험에서 `action='update'` 문자열은 정상 reject됨을 확인.

- 그러나 `test_analysis_phase2a.py` 전체에서 action 파라미터는 항상 `CREATE`로만 전달되며, reject path를 검증하는 test가 **없음** (grep 확인).
- 완화 요인: `service.py:189`가 stored `candidate.action`을 입력과 무관하게 항상 `CREATE`로 강제하므로, 저장값 자체는 안전. reject path는 사실상 ergonomic defense.
- 그럼에도 B3 "NOT fire(action≠create)" 분기가 named test에 매핑되지 않으면, 향후 누군가 `_validate_action`을 제거해도 green bar가 깨지지 않음. boundary matrix 빈 칸.

#### F3 — logical_key가 candidate identity 핵심이나 정본에 정의 없음 (contract gap, spec-silent-but-code-enforced)

`service.py:163-164`(logical_key 필수), `service.py:174`(`find_candidate_request(project_id, task_id, logical_key)`), `repository.py:35-37` — candidate retry idempotency의 identity key는 `(project_id, task_id, logical_key)`.

- 정본(§127, kickoff #6, plan line 25)은 "같은 logical candidate retry"까지만 말하고, **logical candidate를 식별하는 key가 무엇인지, 그 key의 의미·형식·충돌 정책을 명시하지 않음**.
- code는 호출자 제공 임의 문자열 `logical_key`를 identity로 채택 — spec-silent 구현 결정이 runtime contract가 됨.
- 완화 요인: kickoff "추천 최소 slice" 검증 항목과 work_log Next steps가 "Snapshot Loader와 candidate source validation"을 다음 slice로 명시. logical_key semantic은 해당 slice에서 정의될 수 있음.
- 그러나 현재 slice가 이미 `logical_key`를 runtime 강제 + required + identity key로 사용하므로, 정본에 최소 "logical_key는 다음 slice에서 확정되는 candidate identity key(임시)"라는 명시가 없으면 다음 검증자가 identity 의미를 추측하게 됨. contract amendment 후보.

### Surface 5 — 회귀 test 감사 (green bar ≠ spec 검증)

15개 test 재실행 → 15 통과 재현 (보고 일치). 각 assertion을 읽어 contract pin 여부 확인:

- **양방향 가드가 충실한 test**: B1(taxonomy fire+NOT), B5(confidence 0/1 허용 + 범위 외 거부 + bool/비숫자 거부), B7(span 공유 허용 = over-strict 가드), B9(job idempotency 3종), B11. 이들은 단순 byproduct가 아닌 contract 분기를 직접 pin.
- **누락**: F1(NaN), F2(action≠CREATE) — 위와 동일.
- assertion은 모두 public surface(`AnalysisService` method 결과, `candidate.action`/`status`/`provenance`/`confidence`/`source_ref_ids`/`payload`, repo 길이)를 타겟. 내부 helper가 아닌 caller가 의존하는 envelope. ✅
- parametrized 경계값: B5에서 `-0.01`/`1.01`/`0.0`/`1.0`/`True`/`"0.8"`를 모두 개별 assert. NaN만 빠짐.

green bar는 필요조건이나 충분조건이 아님 — F1/F2가 green 상태에서도 존재함이 증명됨.

### Surface 6 — 스모크/보고 숫자 교차검증 (PASS)

직접 재현 결과:
```
python3 -m unittest tests.test_analysis_phase2a -v   → Ran 15 tests ... OK
python3 -m unittest discover -s tests                → Ran 238 tests ... OK (skipped=27)
```

보고된 "15 통과" / "238 통과 27 skip"과 정확히 일치. work_log/HANDOFF/CHANGELOG의 숫자가 재계산되지 않은 숫자가 아님을 확인.

### Surface 7 — Mongo skip probe 보강 (PASS)

`tests/test_core_sot_mongo.py` `_probe_mongo()` finally 블록: `client.drop_database(probe_db)`를 try로 감싸고 `PyMongoError`(Unauthorized `OperationFailure` 포함) 시 `client.close()` 후 `(False, False)` 반환.

- "Mongo 미가용이면 integration test skip"이라는 기존 계약(SoT v1.3~)과 정합. ping은 되나 write/drop 권한이 없는 인증 요구 환경을 skip 조건으로 편입.
- finally 내 `return`은 안티패턴이나 의도적이며 정상 경로(`return True, txn_supported`)를 가리지 않음.
- 이 변경은 analysis slice의 부수 보강이며 code 계약 위반 아님.

## Issues / Risks

- **F1 (Medium, blocking 조건)**: confidence NaN 관통. 정본 `0.0 <= confidence <= 1.0` literal 위반 + under-strict regression 부재. 저장값이 `nan`이 되는 것을 허용.
- **F2 (Low, blocking 조건)**: action≠CREATE reject path 회귀 부재. stored value는 force로 안전하나 boundary matrix 빈 칸.
- **F3 (contract amendment 후보)**: `logical_key` identity가 정본에 정의 없이 runtime 강제. 다음 slice에서 확정하거나 정본에 임시 명시 필요.
- **F4 (out of slice, tracked)**: kickoff "현재 확정된 경계"(모든 후보는 같은 `project_id`의 `source_ref`로 원문 근거를 다시 찾을 수 있어야)의 source_ref cross-project validation이 아직 미구현. `record_candidate`는 `source_ref_ids`를 non-empty string만 검증하고 같은 project 소속 여부는 검증 안 함. work_log가 다음 slice(Snapshot Loader + candidate source validation)로 명시 → 현재 slice 범위 밖이나 미구현 상태를 명시적으로 기록.
- **경계 위반 아닌 관찰**: `record_candidate`가 `action` 파라미터를 받으면서 stored value는 무시하고 `CREATE`를 강제(`service.py:189`) — defense-in-depth이나 API 표면에선 입력을 무시하는 혼란 요소. 변경 권장 아님(기록만).
- **경계 위반 아닌 관찰**: 같은 (job, candidate_type) task 중복 생성을 막지 않음. 정본이 task idempotency를 규정하지 않으므로 contract 밖. 현재 slice 범위 내 결함 아님.

## Verdict — 조건부 합격 (Conditional Pass)

**Load-bearing 이유**:

1. 정본 v1.6 approved literal은 code에 정확히(파라프레이즈 없이) 구현됨 (Surface 1 ✅).
2. 정본 내부 일관성 양호, 모순 없음 (Surface 2 ✅).
3. 12개 boundary 중 9개는 code 강제 + named test 1:1 pin, 양방향 가드 충실 (Surface 3/5 ✅).
4. 보고 숫자 15/238-27 재현 확인, 문서 갱신 정합 (Surface 6/7 ✅).

**조건 (합격으로 전환하기 위해 필요)**:

- **C1 (필수)**: F1 수정 — `_validate_confidence`에서 NaN reject (`math.isnan(normalized)` 또는 `not (0.0 <= normalized <= 1.0)`). `test_confidence_*`에 NaN reject 회귀 추가(under-strict 가드). 정본 literal 위반이므로 빈 칸을 채우기 전까지는 합격 불가.
- **C2 (필수)**: F2 보강 — action≠CREATE reject 회귀 추가. boundary matrix 빈 칸 폐쇄.
- **C3 (권장)**: F3 — `logical_key` identity를 정본(kickoff decisions 또는 plan Phase 2A)에 임시 명시하거나, 다음 slice 확정을 HANDOFF/kickoff에 명시적으로 연결.

**왜 "합격"이 아닌가**: CLAUDE.md 검증 원칙은 "boundary matrix에 빈 칸이 있으면, green bar와 무관하게, conditional/fail 이다. 누락된 over-strict/under-strict 가드를 'future risk'로 재분류하지 않는다." F1은 정본이 명시적으로 reject를 요구하는 confidence 범위의 under-strict 위반이며(단순 spec-silent가 아님), F2는 named test에 매핑되지 않은 NOT-fire 분기다. 두 조건이 채워지기 전까지 합격으로 전환하지 않는다.

**왜 "불합격"이 아닌가**: 위반은 국소적(confidence NaN edge, 단일 reject path 회귀 부재)이며, 정본 literal은 정확히 반영됐고 대다수 경계가 충실히 잠겼다. F1/F2는 회귀 1~2건 추가로 폐쇄 가능한 수준이라 전면 재구현이 필요하지 않다.

## Outstanding items

- 검증 대상은 **uncommitted working tree**. 커밋·발행은 사용자 결정 대기.
- C1/C2 회귀 추가 시 본 검증의 Verdict를 "합격"으로 갱신 필요(재검증 권장).
- F4(source_ref cross-project validation)는 다음 slice에서 회귀와 함께 폐쇄 예정 — 본 slice 범위 밖.
- F3(logical_key identity)의 정본 반영은 다음 slice 설계와 함께 결정.
- 본 검증은 code를 수정하지 않음 (CLAUDE.md: 검증 실패 시 검증자가 자동 수정하지 않고 사용자에게 회신).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# focused + 전체 회귀 (15 / 238-27)
python3 -m unittest tests.test_analysis_phase2a -v
python3 -m unittest discover -s tests

# F1: NaN confidence 관통 증명
python3 -c "
from services.application.app.analysis.service import AnalysisService, InMemoryAnalysisRepository
from services.application.app.analysis.models import AnalysisCandidateType, AnalysisCandidateAction, AnalysisProvenance
s=AnalysisService(InMemoryAnalysisRepository())
j=s.create_job(project_id='p',snapshot_id='s',idempotency_key='k').job
t=s.create_task(project_id='p',job_id=j.id,candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION)
r=s.record_candidate(project_id='p',task_id=t.id,logical_key='lk',candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,action=AnalysisCandidateAction.CREATE,provenance=AnalysisProvenance.AI_INFERRED,confidence=float('nan'),source_ref_ids=('r1',),payload={})
print('NaN confidence stored =', r.candidate.confidence)   # nan = F1 재현
"

# F2: action≠CREATE reject path (reject는 되나 test 없음)
git grep -n "_validate_action\|action=" tests/test_analysis_phase2a.py   # 매칭 없음 = 빈 칸

# 정본 literal 교차 확인
grep -nE "character_observation|event_observation|open_question_observation|source_observed|ai_inferred|needs_review" \
  docs/system-contract-sot.md services/application/app/analysis/models.py
```
