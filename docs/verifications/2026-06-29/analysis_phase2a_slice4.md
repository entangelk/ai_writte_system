# Phase 2A Slice 4 (extraction runner + anchor-set identity closure) 독립 검증

## Subject Metadata

- **날짜**: 2026-06-29
- **요청자**: 사용자 ("다음작업 검증해줘" — extraction runner slice)
- **검증자**: Claude (본 세션, 구현과 무관)
- **대상 slice**: Phase 2A extraction runner orchestration + (직전) source anchor set identity 명확화
- **정본 spec 참조**:
  - `docs/system-contract-sot.md` **v1.6.4** (changelog line 36; §305 extraction runner 계약) / **v1.6.3** (line 37; anchor-set identity + forward path)
  - `docs/plans/02-analysis-pipeline.md` line 31
  - `docs/plans/02-analysis-kickoff-decisions.md` line 91-93
- **검증 대상 커밋**:
  - `e479e84` Implement Phase 2A extraction runner (본 slice)
  - `342559f` Clarify Phase 2A source anchor set identity (slice3 검증 D1/D3 해소, runner 직전)
- **작업 출처**: committed. working tree clean.
- **선행 검증**: `docs/verifications/2026-06-29/analysis_phase2a_slice3.md` (합격, non-blocking D1=multiset / D2=버전필드 / D3=forward note)
- **검증 입장**: (a) slice3의 D1/D2/D3가 342559f/v1.6.4로 닫혔는지, (b) runner의 all-or-nothing과 job/task idempotency가 code + named 회귀로 보장되는지, (c) `validate_candidate`가 진짜 dry-run(저장 부작용 없음)인지를 주장 수용 없이 실험으로 증명.

## Scope

1. **slice3 non-blocking(D1/D2/D3) 폐쇄 확인**
2. **runner orchestration 계약 ↔ code** — 흐름 순서 / job·task 재사용 / preflight dry-run / all-or-nothing
3. **구현 code 감사** — `runner.py` / `service.py`(`_validate_candidate_request` 공유, `validate_candidate`, task 재사용) / `repository.py`(task index)
4. **회귀 test 감사** — `test_analysis_runner.py`(4개)가 all-or-nothing·idempotency를 양방향 pin 하는가
5. **스모크/보고 숫자 교차검증** — focused 37 / 전체 260-27 재현

## Methodology

```bash
# 1. 정본 + 변경 범위
grep -nE "v1\.6\.[34]|extraction runner|project_id \+ job_id \+ candidate_type|사전 검증|all-or-nothing" \
  docs/system-contract-sot.md docs/plans/02-analysis-pipeline.md
git show e479e84 --stat; git show 342559f --stat

# 2. dry-run / multiset / task 재사용 직접 실험
python3 -c "...validate_candidate 부작용 / (a1,a1)==(a1,) / create_task 재사용..."

# 3. focused + 전체 회귀
python3 -m unittest tests.test_analysis_runner tests.test_analysis_extractor_schema tests.test_analysis_phase2a tests.test_analysis_source_validation  # 37
python3 -m unittest discover -s tests                                   # 260, 27 skip
```

## Findings

### Surface 1 — slice3 non-blocking(D1/D2/D3) 폐쇄 (PASS)

| 항목 | 해소 근거 | 확인 |
|---|---|---|
| D1 (multiset 중복) | `342559f` `_dedupe_source_anchors`(extractor.py:220-226, 155, 205) — identity tuple로 dedupe | ✅ 실험 `(a1,a1)==(a1,): True` |
| D2 (SoT 버전 필드) | line 4/53 이제 `v1.6.4` | ✅ |
| D3 (forward path note) | v1.6.3 changelog "ordered evidence chain 필요 시 순서 의미를 별도 필드(`sequence`/`evidence_order` 등)로 계약화" | ✅ |

### Surface 2 — runner orchestration 계약 ↔ code (PASS)

| 계약 (§305 / plan line 31) | code 위치 | 일치 |
|---|---|---|
| job idempotent 생성/재사용 (`project_id + snapshot_id + idempotency_key`) | `runner.py:58-62` → `service.create_job` | ✅ |
| Snapshot Loader | `runner.py:63-66` | ✅ |
| provider extraction | `runner.py:67` | ✅ |
| task 생성/재사용 (`project_id + job_id + candidate_type`) | `runner.py:101-105` → `service.create_task` + repo `_task_request_index` | ✅ |
| 전체 draft 사전 검증 (logical_key/source/schema) | `runner.py:79-80` → `service.validate_candidate` | ✅ |
| candidate write는 검증 뒤 시작 (all-or-nothing) | `runner.py:82-84` (preflight 통과 후 record) | ✅ |

### Surface 3 — 구현 code 감사 (우수)

- **검증 로직 통합**: `service._validate_candidate_request`(`service.py:268-`)를 `record_candidate`(write)와 `validate_candidate`(dry-run)가 공유. preflight를 통과한 draft는 record에서 같은 검증을 통과 → record 단계 검증 실패가 원천 차단. 이것이 all-or-nothing의 load-bearing 설계.
- **`validate_candidate` dry-run**: `find_candidate_request`/`put_candidate` 호출 없이 `_validate_candidate_request`만 수행. 실험 `validate_candidate(...) → candidates stored: 0`. 부작용 없음. ✅
- **task 재사용**: `repository._task_request_index[(project, job, type)]` + `service.create_task`의 `find_task_request` 조회. 실험 동일 `(job,type)` → 같은 task(`tasks stored: 1`), 다른 type → 별개 task. ✅
- **all-or-nothing**: `runner.run`이 모든 draft의 `_validate_draft`(preflight, line 79-80)를 먼저 수행하고, 예외가 없을 때만 record loop(line 82-84). invalid draft가 preflight에서 raise → record 도달 불가 → candidate write 0건. runner 주석(line 77-78)이 "Job/task creation is idempotent setup; candidate persistence remains all-or-nothing"로 명시 — task는 candidate write가 아니므로 preflight 전 생성을 허용하는 계약과 정합.

### Surface 4 — 회귀 test 감사 (양호)

`test_analysis_runner.py` 4개가 핵심 분기를 pin:
- `test_runner_loads_extracts_validates_and_stores_candidates`: happy path 2 candidate + job_idempotent_replay=False + provider에 snapshot raw_text 전달.
- `test_runner_replays_same_job_tasks_and_candidates`: 동일 idempotency_key 재실행 → `jobs=1, tasks=1, candidates=1`, `candidate_idempotent_replays=(True,)`. 전체 idempotency.
- `test_runner_preflights_all_drafts_before_candidate_writes`: valid 1 + invalid(quote mismatch) 1 → `InvalidAnalysisCandidate` + **`candidates: 0`**(valid draft도 write 안 됨 = over-strict 가드). all-or-nothing 핵심.
- `test_runner_preflights_logical_key_before_candidate_writes`: 빈 logical_key draft → `candidates: 0`. under-strict 가드.

all-or-nothing 분기를 양방향(valid 것도 막힘 + invalid 감지)으로 lock. assertion은 repo 길이·idempotent_replay tuple 등 public surface 타겟. ✅

### Surface 5 — 스모크/보고 숫자 교차검증 (PASS)

```
python3 -m unittest tests.test_analysis_runner tests.test_analysis_extractor_schema tests.test_analysis_phase2a tests.test_analysis_source_validation
  → Ran 37 tests ... OK
python3 -m unittest discover -s tests
  → Ran 260 tests ... OK (skipped=27)
```

보고 "focused 37" / "전체 260, 27 skip"과 정확히 일치.

## Issues / Risks

- **F1 (Low-Med, non-blocking, contract tension)**: `service._validate_candidate_request`는 `source_ref_resolver`가 None이면 source_anchors 검증을 skip한다. `AnalysisExtractionRunner.__init__`는 resolver 설정 여부를 강제하지 않으므로, resolver 없는 `AnalysisService`를 주입하면 runner preflight가 source 검증을 조용히 우회한다. §305 "candidate write는 모든 draft의 logical_key/source/schema 검증 뒤 시작"과 service의 "resolver optional" 계약 사이의 tension. runner 회귀는 항상 `CoreSotSourceAdapter`(resolver)를 주입하므로 **resolver 없는 경로는 untested**. typical 사용은 resolver 있지만, §305가 "source 검증"을 명시하는 한 runner가 resolver 주입을 강제하거나 §305를 "resolver 구성 시"로 한정하는 contract amendment + 회귀가 일관적이다.
- **F2 (Low, outstanding → 다음 slice)**: all-or-nothing은 현재 in-memory repository 기준. `record_candidate` loop 중 실패 시 partial write 가능성은 in-memory에선 발생하지 않으나, 다음 slice(Mongo persistence)에서 transaction/atomicity 재검토가 필요하다.
- **F3 (Low, 경미)**: `AnalysisExtractionRunResult.candidates`는 같은 run에서 동일 logical_key draft가 2개 들어오면 같은 candidate을 tuple에 2번 포함할 수 있다(저장은 1건, `candidate_idempotent_replays=(False, True)`로 caller가 판별 가능). caller가 candidates 자체를 dedupe로 가정하면 혼란. 현 contract는 dedupe를 약속하지 않는다.

## Verdict — 합격 (Pass)

**Load-bearing 이유**:

1. slice3의 non-blocking 3건(D1/D2/D3)이 `342559f` + v1.6.4로 code·정본에서 닫혔음을 재확인 (Surface 1 ✅).
2. runner orchestration 계약(흐름 순서·job·task 재사용·preflight·all-or-nothing)이 정본 §305와 code에 정확히 대응 (Surface 2 ✅).
3. all-or-nothing의 load-bearing 설계(`_validate_candidate_request` 공유 + dry-run preflight)가 code에서 증명되고, empirical로 dry-run 부작용 없음·task 재사용·multiset dedupe를 확인 (Surface 3 ✅).
4. 회귀 4개가 all-or-nothing·idempotency 분기를 양방향 가드로 pin (Surface 4 ✅).
5. 보고 숫자 37 / 260-27 재현 (Surface 5 ✅).

**F1/F2/F3은 합격을 뒤집지 않는다**: F1은 contract tension(§305 vs resolver-optional)이자 typical 사용 바깥의 설정 경로 — runner 회귀가 resolver 있는 경로의 source 검증을 lock하므로 현재 경계는 닫혀 있고, 남은 것은 resolver-없는 경로의 계약 명확화(권장). F2는 in-memory에선 해당 없는 다음 slice 과제. F3은 caller의 dedupe 가정 주의. 어느 것도 현재 정본 경계를 위반하거나 boundary matrix 빈 칸이 아니다.

## Outstanding items

- F1: runner의 resolver 주입 강제 또는 §305 "resolver 구성 시 source 검증" 한정 + 회귀 권장.
- F2: 다음 slice(Mongo repository/persistence)에서 candidate write의 transaction/atomicity 계약 수립.
- F3: `AnalysisExtractionRunResult.candidates`의 dedupe 의미를 결정(문서 1줄 또는 tuple dedupe).
- 본 검증은 code를 수정하지 않음. 본 slice는 합격이므로 발행·다음 slice 진행은 사용자 결정.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# focused + 전체 회귀 (37 / 260-27)
python3 -m unittest tests.test_analysis_runner tests.test_analysis_extractor_schema tests.test_analysis_phase2a tests.test_analysis_source_validation
python3 -m unittest discover -s tests

# dry-run / multiset / task 재사용 증명
python3 -c "
from services.application.app.analysis.extractor import _logical_key
from services.application.app.analysis.models import CandidateSourceAnchor, AnalysisCandidateType, AnalysisCandidateAction, AnalysisProvenance
from services.application.app.analysis.service import AnalysisService, InMemoryAnalysisRepository
a1=CandidateSourceAnchor(source_ref_id='r1',start_offset=0,end_offset=2,quote='민아',content_hash='h1')
CT=AnalysisCandidateType.CHARACTER_OBSERVATION; P={'name':'민아','observation':'x'}
print('D1 multiset:', _logical_key(candidate_type=CT,source_anchors=(a1,a1),payload=P)==_logical_key(candidate_type=CT,source_anchors=(a1,),payload=P))
s=AnalysisService(InMemoryAnalysisRepository()); j=s.create_job(project_id='p',snapshot_id='s',idempotency_key='k').job
t1=s.create_task(project_id='p',job_id=j.id,candidate_type=CT); t2=s.create_task(project_id='p',job_id=j.id,candidate_type=CT)
print('task reuse:', t1.id==t2.id, 'tasks:', len(s._repo.tasks))
s.validate_candidate(project_id='p',task_id=t1.id,logical_key='lk',candidate_type=CT,action=AnalysisCandidateAction.CREATE,provenance=AnalysisProvenance.AI_INFERRED,confidence=0.5,source_ref_ids=('r1',),payload=P)
print('dry-run candidates:', len(s._repo.candidates))   # 0 = 부작용 없음
"

# all-or-nothing 회귀 직접 확인
python3 -m unittest tests.test_analysis_runner.AnalysisExtractionRunnerTest.test_runner_preflights_all_drafts_before_candidate_writes -v

# 정본 계약 교차 확인
grep -nE "v1\.6\.4|extraction runner|project_id \+ job_id \+ candidate_type|사전 검증|candidate write는" \
  docs/system-contract-sot.md docs/plans/02-analysis-pipeline.md
```
