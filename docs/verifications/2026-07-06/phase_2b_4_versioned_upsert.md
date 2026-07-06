# Verification — Phase 2B.4 proposal→실제 memory versioned upsert

## Subject metadata

- **Date**: 2026-07-06
- **Requester**: entangelk (오너) — “클로드 작업 AI가 작업한 분 확인하고 검증하고 의심하고 또 의심해줄래?”
- **Verifier**: Claude (독립 검증, 구현 작업 미관여)
- **Target slice / artifact**: Phase 2B.4 — `services/application/app/analysis/apply.py`(신규 `MemoryApplyService`), `memory/{models,service,repository,mongo_repository}.py`(versioned upsert + `SUPERSEDED`/`supersedes`), `main.py`(`POST .../jobs/{job_id}/apply`), `context_search/prior_memory.py`(O1), 회귀 `tests/test_memory_apply.py`·`tests/test_analysis_apply_api.py`·`tests/test_analysis_context.py`·`tests/test_memory_mongo.py`.
- **Canonical spec reference**:
  - `docs/system-contract-sot.md` v1.6.44(version-table line 36) + v1.6.42(2B.3 compare/proposal) + v1.6.40(2B.1 store).
  - `docs/plans/02b-4-memory-versioned-upsert-decisions.md`(Resolved, D1~D7).
  - `docs/plans/02b-3-analysis-compare-action-decisions.md`(2B.3 proposal contract) · `analysis-memory-taxonomy.md`(“덮어쓰기 금지·이전 version 보존”).
- **Source of work being verified**: working tree, **uncommitted**(branch `phase2b-slice-2b-2-prior-memory-context`). 커밋 전 상태로 검증.

## Scope

본 검증은 아래 표면을 2B.4 계약(SoT v1.6.44 + 결정 브리프 D1~D7) 대비로 점검한다.

1. **계약(contract)**: SoT v1.6.44 경계(literal·전이·거절·idempotency·HTTP 매핑) + 결정 브리프 D1~D7 추천/확정값.
2. **구현 코드**: `apply.py`, `memory/service.py`(`_versioned_upsert`/`record_*_version`), `memory/models.py`(`SUPERSEDED`/`supersedes`), `memory/{repository,mongo_repository}.py`(`update_memory`), `main.py`(apply endpoint + 에러 매핑 + `_memory_payload` supersedes), `prior_memory.py`(O1 주석).
3. **회귀 테스트**: `test_memory_apply.py`(10), `test_analysis_apply_api.py`(8), `test_analysis_context.py` O1(+1), `test_memory_mongo.py` versioned round-trip(+1).
4. **공개 표면/envelope**: apply HTTP 응답(`applied[]` outcome/memory_id/superseded_memory_id/version/idempotent_replay), `_memory_payload`의 `supersedes`.
5. **전체 스위트 + 라이브 Mongo smoke**.

## Methodology

계약을 먼저 읽어 boundary matrix(“실행되어야 할 분기” + “실행되지 않아야 할 분기” + 거절/idempotency/HTTP 매핑)를 만들고, 각 셀이 어느 회귀에 대응하는지 추적했다. 이후 코드·테스트를 1차 원천으로 재유도하고, 스스로 실행·변이(mutant)로 증명했다.

정확한 명령:

```bash
# (1) 컴파일 + diff 위생
python3 -m py_compile services/application/app/analysis/apply.py services/application/app/memory/service.py \
  services/application/app/memory/models.py services/application/app/main.py \
  services/application/app/memory/mongo_repository.py services/application/app/context_search/prior_memory.py \
  tests/test_memory_apply.py tests/test_analysis_apply_api.py
git diff --check

# (2) focused + 전체 스위트(mongo 제외 — 작업자와 동일 조건)
python3 -m pytest -q tests/test_memory_apply.py tests/test_analysis_apply_api.py tests/test_analysis_context.py
python3 -m pytest -q --ignore=tests/test_memory_mongo.py

# (3) 라이브 Mongo round-trip 독립 재실행(throwaway, 정리 포함)
docker run -d --name verify-mongo-2b4 -p 27055:27017 mongo:7
CORE_SOT_TEST_MONGO_URI="mongodb://localhost:27055" python3 -m pytest -q tests/test_memory_mongo.py
docker rm -f verify-mongo-2b4

# (4) 변이(mutant) 증명 — 각 잠금의 under/over 방향
#     (a) non-canonical target 분기 도달 가능성: /tmp/verify_noncanonical.py 로 2개 update 연쇄
#     (b) update confidence 규칙(candidate vs max) 식별력: service.py 를 max 로 치환 후 해당 회귀 실행
#     (c) O1 non-vacuity: prior_memory.py 필터 약화 후 O1 회귀 실행
```

## Findings

### 1. 계약 경계 ↔ 회귀 추적 (boundary matrix)

scoped reading(SoT v1.6.44 line 36 + 브리프 D1~D7)에서 뽑은 경계와 대응 회귀:

| # | 계약 경계(soot/브리프) | 코드 | 회귀 | 상태 |
|---|---|---|---|---|
| 1 | create → 새 canonical v=1 | `apply.py:96-110`(`promote_candidate(MANUAL)`) | `test_create_mints_new_canonical_version_one` + HTTP `test_create_proposal_mints_canonical` | ✓ |
| 2 | update → 새 version, payload=candidate 교체·source union·conf=candidate·prov=candidate·`supersedes=prev` | `service.py:254-257`(else 분기), `apply.py:117-122` | `test_update_versions_prior_and_replaces_payload` + HTTP `test_update_proposal_versions_prior_and_supersedes` | ✓(단 §3 참고) |
| 3 | add_evidence → payload 보존·source union·conf=max(prev,candidate)·prov=prev | `service.py:250-253`(evidence 분기) | `test_add_evidence_preserves_payload_unions_source_max_confidence` | ✓ |
| 4 | version=prev+1, `supersedes=prev.id` | `service.py:268,274` | #2·#3 회귀가 assertion | ✓ |
| 5 | append-only: 이전 version 불변 보존(status→superseded, payload 미변경) | `service.py:286-288`(`replace(target, status=SUPERSEDED)`) | `test_update_versions_prior_and_replaces_payload`(old payload "brave"·status SUPERSEDED) | ✓ |
| 6 | source_ref_ids order-preserving union | `service.py:37-44` | 정확 튜플 `("source-ref-1","source-ref-2")` assertion | ✓ |
| 7 | scope 는 target.scope 계승(재산출 아님) | `service.py:273` | `new_entry.scope == prior.scope` | ✓ |
| 8 | no_change → 쓰기 없음 | `apply.py:83-84` | `test_no_change_writes_nothing` + HTTP | ✓ |
| 9 | conflict → review-only skipped, 쓰기 없음(D7) | `apply.py:85-88` | `test_conflict_is_review_only_no_write` + HTTP | ✓ |
| 10 | 타입 불일치 → 거절 | `service.py:242-245` | `test_update_type_mismatch_rejected` | ✓ |
| **11** | **non-canonical target → 거절** | `service.py:240-241` | **(없음)** | **✗ BLOCKING** |
| 12 | candidate 부재 → 거절 | `apply.py:90-94` | `test_proposal_for_missing_candidate_raises` + HTTP `test_candidate_not_in_job_returns_400` | ✓ |
| 13 | update/add_evidence 에 matched_memory_id 누락 → 거절 | `apply.py:113-116` | `test_update_without_matched_memory_raises`(service); HTTP None-케이스 미테스트(§4 O3) | ~ |
| 14 | create idempotent replay(D5) | `service.py:127-132` | `test_create_is_idempotent_replay_on_reapply` | ✓ |
| 15 | update idempotent replay — 3번째 version 미생성(D5) | `service.py:232-237` | `test_update_is_idempotent_replay` + HTTP `test_reapply_is_idempotent` | ✓ |
| 16 | add_evidence replay(D5) | `service.py:232-237`(공유 경로) | 개별 회귀 없음(update replay 가 동일 `_versioned_upsert` 상단 체크 커버, §4 O2) | ~ |
| 17 | HTTP `POST .../jobs/{job_id}/apply` + action별 결과 요약(D6) | `main.py:1157-1227` | `test_create_proposal_mints_canonical` 등 | ✓ |
| 18 | unknown action → 400 | `main.py`(CompareAction ValueError→400) | `test_unknown_action_returns_400` | ✓ |
| 19 | matched memory 부재(non-existent id) → 404 | `main.py`(MemoryNotFound→404) | `test_update_missing_matched_memory_returns_404` | ✓ |
| 20 | missing project/job → 404; cross-project 격리 | `main.py`(AnalysisNotFound/NotFound→404), `_require_memory` project_id 검사 | `test_missing_project_and_job_return_404` | ✓ |
| 21 | prior canonical-only 필터가 superseded 제외(2B.2 O1) | `prior_memory.py:79-85` | `test_superseded_memories_excluded_from_prior_memory`(양방향 1케이스) | ✓(§2 mutation 재확인) |
| 22 | Mongo `update_memory`(replace_one) + supersedes round-trip | `mongo_repository.py:96-97,131,159` | `test_versioned_update_round_trips_supersedes_and_status`(live) | ✓(§5 독립 재실행) |

### 2. O1 non-vacuity 변이 재실증(독립)

`prior_memory.py`의 canonical-only 필터(`if entry.status is MemoryStatus.CANONICAL and entry.memory_type in wanted`)를 `if entry.memory_type in wanted`로 약화 → `test_superseded_memories_excluded_from_prior_memory` **FAILED**(AssertionError). 복원 후 PASS. under-strict 방향 잠금 확인됨. 작업자 주장과 일치.

### 3. update confidence 규칙 — over-strict guard 약함(비차단)

D3 는 update confidence = **candidate.confidence** 라 명시. 회귀 `test_update_versions_prior_and_replaces_payload`는 prior=0.5·candidate=0.8 로 `confidence==0.8`을 검사한다. 그러나 이 값은 `max(prev,candidate)` 와 동일(0.8)이라 규칙을 식별하지 못한다. 변이 증명: `service.py:256`을 `confidence = max(target.confidence, candidate.confidence)`로 바꾸어도 해당 회귀 + HTTP 회귀 **모두 통과**(2 passed). under-strict(계약값 0.8 assertion)는 잠겨 있으나, candidate 규칙과 max 규칙을 구분하려면 prior > candidate 인 update 케이스가 필요하다.

### 4. 기타 비차단 관찰

- **O2**(add_evidence replay): `#16`. update/add_evidence 모두 `_versioned_upsert` 최상단의 동일 `find_memory_by_candidate` replay 체크를 공유하므로 update replay 가 메커니즘을 커버. 정통 boundary-matrix 에서는 별도 케이스를 권장.
- **O3**(MissingMatchedMemory→400 HTTP): `main.py` except 매핑은 존재하나, matched_memory_id=None 케이스는 service 레벨에서만 잠기고 HTTP 미테스트. HTTP 회귀는 non-existent id→404 만 다룬다. 얇은 wrapper라 영향은 작다.
- **O4**(문서 뉘앙스): 브리프 D7 본문은 “conflict/merge/split 은 skipped 로 반환”이라 하나, `merge`/`split` 은 `CompareAction` enum 에 없어(2B.3 미산출) POST 시 400(unknown action)이지 SKIPPED_REVIEW 가 아니다. SoT v1.6.44 “merge/split은 2B.3 미산출”로 모순 없으나, 브리프 D7 표현이 살짝 과대. 코드/SoT 정합.

### 5. 라이브 Mongo round-trip 독립 재실행

throwaway `mongo:7`(localhost:27055)로 `tests/test_memory_mongo.py` 실행 → **4 passed**(신규 `test_versioned_update_round_trips_supersedes_and_status` 포함). `update_memory`(replace_one) + supersedes/superseded round-trip·source union·version=2 가 실제 Mongo 에서 재현됨. 컨테이너 정리 완료. 작업자 주장(throwaway mongo 통과·컨테이너 정리) 일치. 기본 sandbox localhost:27017 auth error 는 종전 환경 이슈(본 변경 무관)로 확인.

### 6. 전체 스위트 / 위생

`pytest -q --ignore=tests/test_memory_mongo.py` → **561 passed / 45 skipped**(작업자 주장과 정확 일치). focused(apply+api+context) 29 passed. `git diff --check` clean. `py_compile` 전 대상 OK.

### 7. 계약 자기정합성(cross-check)

SoT v1.6.44 ↔ 브리프 D1~D7 ↔ 코드는 D1~D6 모두 정합. D3 update/add_evidence payload·source·confidence·provenance 규칙, D5 `(project_id, source_candidate_id)` idempotency(재적용 replay, 3번째 version 미생성), D2 append-only + SUPERSEDED + supersedes(이전 version 불변), D6 HTTP surface·400/404 매핑, D7 conflict skipped — 모두 코드와 일치. work_log 2B.4 테스트 목록(10+8+1)은 실재 테스트와 정확히 일치하며 non-canonical-target 테스트를 **허위로 주장하지 않음**(즉 누락은 있되 과대 보고는 아님).

## Issues / Risks

- **[BLOCKING] non-canonical target 거절 분기에 회귀 없음(#11)**. SoT v1.6.44(line 36)가 거절 경계 3종(타입 불일치·non-canonical target·candidate 부재)을 명시하고, 코드(`service.py:240-241`)는 이를 시행하나, 타입 불일치(`test_update_type_mismatch_rejected`)·candidate 부재(`test_proposal_for_missing_candidate_raises`)와 달리 **non-canonical target 을 잠그는 회귀가 없다**. 분기는 도달 가능하다(독립 입증: 서로 다른 candidate 2개가 같은 prior 를 순차 update → 두 번째가 superseded target 에 도달 → `MemoryError: cannot version a non-canonical memory entry`). CLAUDE.md boundary-matrix 규칙상 “실행되어야 할 분기”의 빈 셀은 green bar 와 무관하게 차단이다. **이것이 조건부 합급의 사유**.
- [NON-BLOCKING] update confidence over-strict guard 약함(§3). candidate 규칙과 max 규칙을 구분 못함.
- [NON-BLOCKING] add_evidence replay / MissingMatchedMemory-None HTTP / D7 merge·split 표현(§4 O2~O4).

## Verdict

**조건부 합격(conditional pass).**

하중 사유(load-bearing):
- 유일한 차단 조건은 **non-canonical target 거절 분기의 회귀 부재**다. 코드는 정확히 동작하지만(거절함), SoT v1.6.44 가 명명한 거절 경계 중 이 한 셀만 빈 칸이다. CLAUDE.md “An untraced branch is a blocking finding regardless of the green bar” 에 따라 회귀가 추가되기 전까지 합격으로 승급 불가.
- 그 외 모든 표면 — D1~D7 구현 정합, 19개 신규 회귀 + 라이브 Mongo round-trip, 561 passed/45 skip, O1 non-vacuity, diff/compile 위생 — 은 독립 재현·입증 완료.

조건: `service.py:240-241`의 `if target.status is not MemoryStatus.CANONICAL` 분기를 잠그는 회귀 추가(예: 같은 prior 를 두 candidate 가 순차 update 하는 batch 케이스, 또는 superseded target 직접 주입 단위 테스트). 추가 후 본 차단은 즉시 폐쇄 가능.

권장(비차단, 본 판정과 무관): update confidence 회귀에 prior>candidate 케이스 추가(§3), add_evidence replay·MissingMatchedMemory-None HTTP 케이스(§4).

## Outstanding items

- **미커밋**: 본 변경은 working tree(uncommitted) 상태. 커밋 전 F1(non-canonical target 회귀) 추가를 권장 — 커밋 메시지가 “회귀 19개”를 포함하므로, 빈 셀을 채운 뒤 커밋하는 것이 계약-테스트 정합에 부합.
- **오너 결정 대기**: 본 검증은 결함을 ** silently fix 하지 않음**(CLAUDE.md). F1 회귀를 (a) 지금 2B.4 에서 보강할지, (b) 2B.5 착수 전 별도 보강으로 둘지 오너가 정할 것.
- **2B.5(memory→vector 재색인)**: 본 slice 와 무관하나 D4=A 로 분리된 후속. 색인 파이프라인이 신규라 별도 kickoff 브리프 필요(HANDOFF Next Tasks #1).
- **event/open_question 중복 누적**: scope key 없이 항상 create 로 반영되어 의미적 resolution(D2 seam) 전까지 중복 가능. HANDOFF 누적 오너 확인 대상 유지(본 slice 범위 밖).

## Closure (작업자 후속, 2026-07-06 — 오너 지시로 보강)

검증자의 판정 이후, 오너 지시("보강해줘")로 작업자가 차단 + 비차단을 보강했다. 상세는 work_log `## 2B.4 검증 후속 보강` 참조.

- **[BLOCKING #11 폐쇄]** `tests/test_memory_apply.py::ApplyUpdateTest::test_update_of_superseded_target_rejected` 추가 — 서로 다른 candidate 2개가 같은 prior를 순차 update → 두 번째가 superseded target 도달 → `MemoryError`. mutation 재실증: `service.py`의 `if target.status is not MemoryStatus.CANONICAL` guard 무력화 시 재실패(exit 1), 복원 후 통과. boundary matrix #11 빈 셀이 채워짐.
- **[NON-BLOCKING §3 폐쇄]** `test_update_takes_candidate_confidence_even_when_lower`(prior 0.8 > candidate 0.4 → conf=0.4). mutation 재실증: update를 `max(...)`로 치환 시 재실패.
- **[NON-BLOCKING O2 폐쇄]** `test_add_evidence_is_idempotent_replay`.
- **[NON-BLOCKING O3 폐쇄]** `test_analysis_apply_api.py::test_update_without_matched_memory_returns_400`(matched_memory_id=None → 400).
- **[NON-BLOCKING O4 폐쇄]** 브리프 D7에 "merge/split은 2B.3 미산출이라 실제 도달 review-only action은 conflict뿐(merge/split body→unknown action 400)" 명시.
- 재검증: 회귀 19→23, `pytest -q --ignore=tests/test_memory_mongo.py` → **565 passed / 45 skipped**, `git diff --check` 통과. SoT v1.6.44 회귀 수·work_log·HANDOFF 갱신.

이로써 조건부 합격의 유일한 차단 조건이 폐쇄되어 **합격 승급 가능**하다.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# 전체 스위트(작업자 동일 조건)
python3 -m pytest -q --ignore=tests/test_memory_mongo.py        # 561 passed / 45 skipped

# 라이브 Mongo round-trip(throwaway)
docker run -d --name v -p 27055:27017 mongo:7
CORE_SOT_TEST_MONGO_URI="mongodb://localhost:27055" python3 -m pytest -q tests/test_memory_mongo.py  # 4 passed
docker rm -f v

# BLOCKING 입증: non-canonical target 분기 도달 + 회귀 부재
python3 - <<'PY'
import sys; sys.path.insert(0,".")
from services.application.app.analysis.models import (AnalysisCandidate,AnalysisCandidateAction,AnalysisCandidateStatus,AnalysisCandidateType,AnalysisProvenance)
from services.application.app.memory.service import MemoryService, InMemoryMemoryRepository, MemoryError
from services.application.app.memory.models import PromotionMode
def c(i,p): return AnalysisCandidate(id=i,project_id="p",job_id="j",task_id="t",candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,action=AnalysisCandidateAction.CREATE,status=AnalysisCandidateStatus.NEEDS_REVIEW,provenance=AnalysisProvenance.SOURCE_OBSERVED,confidence=.5,source_ref_ids=("s",),payload=p)
s=MemoryService(InMemoryMemoryRepository())
m=s.promote_candidate(project_id="p",candidate=c("c1",{"name":"A","observation":"x"}),mode=PromotionMode.MANUAL).memory
s.record_updated_version(project_id="p",candidate=c("c2",{"name":"A","observation":"y"}),target_memory_id=m.id)
try:
    s.record_updated_version(project_id="p",candidate=c("c3",{"name":"A","observation":"z"}),target_memory_id=m.id)
    print("NO RAISE")  # 분기 미도달 시에만 출력
except MemoryError as e:
    print("RAISED:",e)  # 기대: cannot version a non-canonical memory entry
PY
grep -rn "cannot version a non-canonical\|non-canonical target" tests/   # (공백 = 회귀 없음, 빈 셀)
```
