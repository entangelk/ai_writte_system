# 독립 검증 — D8-6c-1·6c-1b vector/lexical 백엔드 파기 purge_project (commit d1fa777 + 5b73a86)

## Subject metadata

- **날짜**: 2026-08-01
- **요청자**: 오너("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?")
- **검증자**: Claude (독립 세션, max 노력)
- **대상 슬라이스**: D8-6c-1(memory vector/lexical) + 6c-1b(candidate vector/lexical) —
  vector(Chroma/in-memory)·lexical(ES/in-memory) 백엔드에 project 단위 hard delete(`purge_project`) 추가.
  **drain handler 연결 없음**(6c-2), **endpoint 없음**(6d). 6a `enqueue_project_purged` "메서드만, 미사용" 패턴 계승.
- **정규 스펙(canonical contract)**:
  - `docs/system-contract-sot.md` v1.7.69(D8-6a — PROJECT_PURGED 이벤트·`enqueue_project_purged` 정의·drain 미연결 명시) /
    v1.7.70·v1.7.71(D8-6b — derived 10컬렉션 파기 + 전수 가드).
  - `docs/plans/auth-d8-5-admin-decisions.md` §5(D5=A 영구 삭제 정책 — admin-only, 불가역, 부분 삭제 금지).
  - `docs/verifications/2026-07-31/d8_6a_purge_core_sot.md`(6a 검증 — `enqueue_project_purged` production 호출부 0건 확정) ·
    `d8_6b_purge_derived.md`(6b 검증 — 6c 검증 포인트 H2로 "memory_vectors(Chroma)·ES·worker drain + enqueue 실연결"을 명시적으로 위임).
  - `docs/daily_logs/2026-08-01/work_log.md`(6c-1·6c-1b 결정·회귀·뮤테이션 서술).
- **검증 대상 출처**: `d1fa777`(6c-1 memory 코드) + `643129e`(6c-1 문서) + `5b73a86`(6c-1b candidate 코드) + `844afe3`(6c-1b 문서).
  HEAD = `844afe3`. push 안 됨(오너 push).

## Scope

1. **정규 계약 합치성** — purge_project 의 멱등 계약(빈 결과 = 에러 아님)·composite 예외 전파(whole-event all-or-retry)·
   "drain 연결 없음"이 6a 패턴 및 D5 부분삭제금지 통제와 일치하는가.
2. **구현 코드** — 4 파일(memory_index·memory_lexical_index·candidate_index·candidate_lexical_index) + chroma.py 의
   Protocol·InMemory·ES·SyncAdapter·Composite 전 경로. composite `_sinks` 구조가 `purge_project` 위임에 적합한가.
3. **회귀 테스트** — under-strict(멱등)·over-strict(인접 project 유지)·composite 전파 가드가 실제로 계약을 잠그는가(test code is audit subject).
4. **양방향 뮤테이션** — purge 무력화/과잉삭제/composite 삼킴이 각 가드를 re-fail 시키는가(독립 재현).
5. **전체 suite green bar** — 1810 passed/4 skipped/1519 subtests 주장의 독립 재현.
6. **SoT 무변·컬렉션 분리** — SoT 미갱신이 타당한가; memory/candidate Chroma 컬렉션이 분리돼 purge 단일키 필터가 kind 누출을 일으키지 않는가.
7. **전수 가드 범위** — 18컬렉션 가드(`test_purge_project_coverage.py`)가 indexing 백엔드를 커버하는가(D5 고아 위험).

## Methodology

- 정규 계약 스코프 합성: SoT v1.7.69–71 + D5 §5 + 6a/6b 검증 기록만 읽 end-to-end(관련 없는 rule은 배제). boundary matrix:
  [should fire] project 스코프 전체 삭제 · [should NOT fire] 인접 project 유지 · 빈 결과 = 성공(에러 아님) · composite 실패 = 전파.
- 코드 diff: `git show d1fa777 -- <files>` / `git show 5b73a86 -- <files>` 로 추가 라인 전수 독해.
- 회귀: `python3 -m pytest <4 파일> -q`(86 passed/3 skipped) → `python3 -m pytest -q`(전량).
- 양방향 뮤테이션(작업 트리에서 일시적 변이 → re-fail 확인 → `git checkout` 원복, CLAUDE.md §6 절차):
  - A: `InMemoryMemoryVectorIndexAdapter.purge_project` no-op(`pass`) → drop/delegate/fan-out re-fail.
  - B: 동 purge를 `self.records = {}`(과잉 삭제) → 인접 project-2 생존 assertion re-fail.
  - C: `CompositeMemoryIndexSyncAdapter.purge_project` try/except 삼킴 → propagation 가드 re-fail.
- 컬렉션 분리: 컬렉션 상수·wiring(`main.py`)·어댑터 `__init__` 추적으로 memory/candidate 가 별도 컬렉션인지 확인.
- green bar·subtests 수치는 work_log 주장을 믿지 않고 직접 재실행해 대조.

## Findings

### 1. 정규 계약 합치성 ✅

- **"drain 연결 없음" = 6a 패턴**: `enqueue_project_purged`는 `indexing/service.py:337`에 정의만 있고 services/ 내 **production 호출부 0건**(테스트만 — `test_indexing_phase3a.py:287`). 이는 6a 검증(`d8_6a_purge_core_sot.md:88,157`)이 이미 확정한 의도적 미연결. 6c-1/6c-1b 의 `purge_project`도 동일하게 "메서드만, 미사용"(`memory_index.py:145` 등)으로, endpoint(6d)가 유일 production 호출자. **D5 부분삭제금지 통제**: 6d 이전엔 정본 파기→vector 잔류 고아가 생길 수 없다(파기를触发하는 경로 자체가 없음). ✅ 정본과 일치.
- **멱등 계약(빈 결과 = 성공)**: `purge_project`는 빈 매칭(이미 파기/미인덱스)에서 `DerivedIndexRecordNotFound`를 raise **안 함**. 이는 `mark_archived`의 soft raise(`service.py:444` `DerivedIndexRecordNotFound` + `_drain_archive`가 이를 잡아 success 처리, `service.py:530-534`)과 **의도적 차이** — 불가역+멱등인 purge 와 단일-sink archive 의 의도 차이. 형제 백엔드(mongo `delete_many`, analysis dict-filter `analysis/service.py:236-242`)도 데이터 수준 멱등이므로 일관. core_sot 서비스의 `_require_project`(`core_sot/service.py:933-938`)는 project-존재 **사전조건** 체크이지 index-record 부재와는 다른 층위 — 6c-2 worker drain 시점엔 core_sot 이 이미 파기된 뒤라 vector purge 는 project-존재를 요구하면 안 된다. 계약 양립 가능. ✅
- **D8-6 분할 일치**: a(core_sot)·b(derived)·c(vector/drain)·d(endpoint). 6c-1/6c-1b는 c 의 "vector/index 백엔드 purge 메서드" 반을 담당, 6c-2(worker `_drain_purge` 연결)·6d(endpoint)는 후속. work_log 2026-08-01:11-13,73-75 의 인수인계 설계와 코드가 정합.

### 2. 구현 코드 ✅

- **composite `_sinks` 구조 적합**: `CompositeMemoryIndexSyncAdapter.__init__(sinks: tuple[tuple[str, str, Any], ...])`(`memory_index.py:236`), 각 원소 `(target, backend, adapter)`. purge 는 `for _target, _backend, adapter in self._sinks: adapter.purge_project(...)`(`memory_index.py:274-275`). `adapter` 는 `MemoryIndexSyncAdapter`/`MemoryLexicalIndexSyncAdapter`(둘 다 `purge_project` 보유, `memory_index.py:217`·`memory_lexical_index.py:320`)이므로 위임 타입 안전. candidate 동형(`candidate_index.py:252-259`). ✅
- **composite 예외 전파(whole-event all-or-retry)**: try/except 없이 예외가 상위로 전파(`memory_index.py:266-275`, `candidate_index.py:252-259`). worker 재시도 모델(`_drain_archive`, `service.py:535-543`)은 generic Exception 시 `record_outbox_failure` + requeue(attempt 잔량) — 전파된 예외가 entry 를 재시작시키는 all-or-retry 와 양립. ✅
- **drain↔purge 의도적 발산**: drain 은 per-sink `SinkOutcome` 격리(`memory_index.py:239-264`, b-6 증분2), purge 는 전파. 사유(work_log 2026-08-01:57-59, 코드 주석 `memory_index.py:270-271`): PROJECT_PURGED 한 entry 가 memory/candidate **두 composite** 로 흘러야 하는데 per-sink target 키("vector"/"lexical")가 양 composite 에서 충돌해 flat per-sink bookkeeping 가 불가. purge 멱등(재파기 무해)이므로 all-or-retry 가 단순·건전. 기존 drain 테스트 `test_candidate_index.py:722`("sink failure is isolated, **not propagated**")가 drain 의 반대 의미를 명시적 re-lock 하므로, 두 의미가 모두 테스트에 잠겨 있어 향후 "불일치"로 purge 를 per-sink 로 오수정할 위험 낮음. ✅
- **ES `delete_by_query` 8.x 시그니처**: `ElasticsearchClient` Protocol 에 `delete_by_query(*, index, query)` 추가(`memory_lexical_index.py:161-163`). 기존 `index`/`delete`/`search` 도 동일 keyword-only 8.x 형태(`memory_lexical_index.py` 동 파일)로 일관. `body=` 미사용은 8.x 정합. candidate 가 이 Protocol 을 import 재사용(`candidate_lexical_index.py:188-194` 주석 명시) → Protocol 중복 정의 없음. ✅

### 3. 회귀 테스트(test code = audit subject) ✅

- **memory(12 케이스)**: InMemory/Chroma/ES/in-memory-lexical 각 *drops-only-target*(over-strict: 인접 project 생존 단언) + *idempotent-on-empty*(under-strict: 빈 결과 no-raise) + SyncAdapter 위임 + composite fan-out + composite 전파. assertion 이 부산물이 아닌 계약 직결(`test_memory_vector_index.py:466-564`, `test_chroma_memory_adapter.py:199-221`, `test_context_search_memory_lexical_retrieval.py:114-278`). ✅
- **candidate(7 케이스)**: InMemory vector(drops+idempotent 결합, `test_candidate_index.py:332`)/Chroma(drops, `:439`)/in-memory-lexical(drops, `:544`)/ES(drops+idempotent, `:647`·`:678`) + composite fan-out(`:937`)·전파(`:960`). ✅
- **composite 전파 양쪽 잠금**: memory `test_composite_purge_propagates_sink_failure`(`test_memory_vector_index.py:552-563`, `_BoomVector`) + candidate `test_purge_propagates_sink_failure`(`test_candidate_index.py:960-968`). 둘 다 `assertRaises(RuntimeError)`. ✅
- **`_FakeChromaCollection.delete` 일반화 충실**: candidate fake 를 `$and` 하드코딩 → `clauses = where["$and"] if "$and" in where else [where]` 로 확장(`test_candidate_index.py:399-404`). 실제 ChromaCollection.delete 가 임의 where 형태를 받는 점에 부합. 기존 `$and` 케이스(delete_candidate_record) 동작 보존. memory fake(`test_chroma_memory_adapter.py:59-66` `_match`)는 이미 단일키 where 를 처리해 수정 불필요 → 작업자 주장과 일치. ✅

### 4. 양방향 뮤테이션(독립 재현) ✅

세 변이 모두 작업 트리에서 적용 → 대상 가드 re-fail → `git checkout` 원복 → green 재확인(working tree clean).

| 변이 | 코드 | 결과 |
|---|---|---|
| A. under-strict(purge no-op) | `memory_index.py:148-152` → `pass` | `test_inmemory_purge_drops_only_target_project`·`test_sync_adapter_purge_delegates_to_vector_backend`·`test_composite_purge_fans_out_to_vector_sink` **3 re-fail**(idempotent 2건은 여전 pass — 빈 결과 기대라 정상). ✅ |
| B. over-strict(과잉 삭제) | 동 → `self.records = {}` | 동 3건 re-fail(인접 project-2 `p2` 생존 단언 위반, `tests/...:523`). ✅ |
| C. composite 삼킴 | `memory_index.py:274-275` → try/except pass | `test_composite_purge_propagates_sink_failure` **1 re-fail**(RuntimeError not raised), 나머지 4건 pass — 전파 가드만 정확히 격리. ✅ |

### 5. 전체 suite green bar(독립 재현) ✅

`python3 -m pytest -q`(test-mongo healthy) → **1810 passed / 4 skipped / 1519 subtests / 92.83s**. work_log 주장(2026-08-01:106)과 **수치 완전 일치**. 회귀 +19(6c-1 +12·6c-1b +7). 영향 4 파일 단독 **86 passed / 3 skipped**. ✅

### 6. SoT 무변·컬렉션 분리 ✅ (SoT 미갱신은 확인 권고 — Issues 참조)

- **컬렉션 분리(의심 기각)**: `MEMORY_VECTOR_COLLECTION = "memory_vectors"`(`memory_index.py:38`) vs `CANDIDATE_VECTOR_COLLECTION = "candidate_vectors"`(`candidate_index.py:43`). wiring 도 분리 — memory adapter `CHROMA_MEMORY_COLLECTION`(`main.py:906-913`), candidate adapter `CHROMA_CANDIDATE_COLLECTION`(`main.py:1069-1076`). 따라서 `ChromaMemoryVectorIndexAdapter.purge_project(where={"project_id":...})`(`chroma.py:364-369`)는 memory_vectors 만, candidate(`chroma.py:516-520`)는 candidate_vectors 만 타격. **project_id 단일 필터가 kind 누출을 일으키지 않음**(각 컬렉션이 단일 kind). 제기한 공유컬렉션 의심은 기각. ✅ (운영자가 두 env 를 동일값으로 오설정하면 병합되나, 그 경우 기존 list/query 격리도 이미 깨지므로 6c 범위 밖.)
- **operation 카운트 무변은 타당**: endpoint(6d) 전엔 purge 가 카운트 대상 operation 으로 노출되지 않는다. work_log 2026-08-01:76 의 "6d 에서 ADMIN +1·총 +1"과 정합. ✅

### 7. 전수 가드 범위 ⚠️ (자가 식별·6c-2 연기 — Issues #1)

`test_purge_project_coverage.py`(6b-2)는 **mongo repository 9종/18컬렉션만** 검사. indexing vector/lexical 백엔드(Protocol 기반)는 미커버. 이는 작업자가 work_log 에 **스스로 명시**(2026-08-01:63-65, 118-119)하고 6c-2 끝에서 indexing 백엔드 purge 전수 가드 추가를 **후보**로 기록. 6c-1/6c-1b 시점엔 indexing 백엔드 purge 가 각 백엔드별 회귀(존재)로 커버되므로 D5 고아 위험은 닫혀 있으나, 단일 전수 가드 부재는 6c-2 인수인계 항목.

## Issues / Risks

### Blocking (계약 의무) — 없음

boundary matrix 의 모든 계약 필수 분기(project 스코프 전체 삭제·인접 유지·빈 결과=성공·composite 전파)가 명명된 회귀로 매핑되고, 양방향(under/over-strict) 가드가 뮤테션으로 실증됨. 빈 칸 없음.

### Hardening recommendations (non-blocking)

1. **indexing 백엔드 purge 전수 가드(자가 식별, 6c-2 연기)** — `test_purge_project_coverage.py` 가 mongo repository 만 커버. 6c-1(memory vec/lex)·6c-1b(candidate vec/lex) 백엔드가 이제 모두 `purge_project` 를 갖췄으므로, 6c-2 종료 시 이 백엔드들을 포함하는 단일 전수 가드 추가 권장(D5 고아 보증을 repository 층에서 indexing 층으로 확장). 현재는 백엔드별 회귀로 대체 커버 중.
2. **candidate 멱등 테스트 비대칭** — memory 는 4 백엔드 모두 idempotent-on-empty 명시 단언. candidate 는 InMemory-vector(결합 케이스)·ES 만 명시; **candidate Chroma(`test_candidate_index.py:439`)·candidate in-memory-lexical(`:544`)에 idempotent-on-empty 단언이 없음**. 계약 자체는 동일 구조(dict-comprehension/collection.delete)라 대표 구현에서 가드되나, memory 와의 대칭을 위해 1줄 idempotent 단언 추가 권장.
3. **SoT 버전 미갱신(6c-1/6c-1b)** — SoT 가 v1.7.71(D8-6b-2)에서 stop. 6a·6b-1·6b-2 는 **코드만 있는 슬라이스**인데도 SoT 를 올렸으나, 6c-1/6c-1b 는 "SoT 무변"을 주장(work_log 본문엔 미갱신 사유 명시 없음). 두 해석: (a) indexing adapter Protocol method 면이 SoT 추적 범위 밖(SoT 는 repository/service/endpoint/operation-count 추적)이면 미갱신 타당; (b) adapter 계약 추가라면 v1.7.72 entry 필요. 오너 확인 권장 — (b)면 6c(또는 6d) 종료 시 SoT 갱신. operation-count 무변은 (a)/(b) 무관 타당.
4. **composite purge per-sink 관측성 부재(설계적)** — all-or-retry 설계상 purge 는 `SinkOutcome` bookkeeping 없이 전파. 부분 실패 시 outbox 에 per-sink 진단 없이 entry 전체 재시도. drain 의 per-sink 관측성이 purge 경로엔 의도적 결여 — 6c-2 설계 선택으로 타당하나(멱등 재시도로 eventual consistency), drain 대비 관측성 비대칭은 향후 운영 시 인지 필요.

## Verdict

**합격(PASS).** blocking 없음.

- 정규 계약(D5·SoT v1.7.69–71·6a/6b 검증)과 합치: 멱등 계약·composite whole-event all-or-retry·"drain 미연결 = 6a 패턴"·컬렉션 분리 모두 정본/선행과 일관.
- green bar 독립 재현(1810/4/1519, 수치 완전 일치).
- 양방향 뮤테이션 3종(no-op·과잉삭제·composite 삼킴) 독립 재현 — 모든 가드가 실제로 계약을 잠금.
- 회귀 +19(6c-1 +12·6c-1b +7), 회귀 0.
- hardening 4건은 모두 non-blocking(1건은 작업자 자가 식별·6c-2 연기, 1건은 오너 SoT 확인). 조건 없는 합격.

## Outstanding items

- **6c-2(next)**: worker `_drain_purge` + `run_once` 분기(`elif entry.event is PROJECT_PURGED`) + source_block archive(`ChromaArchiveIndexMutationAdapter`) purge + memory/candidate composite purge 호출 + 어제 깨진 guard `_archive_where` PURGED `ValueError` 교체 + worker drain 회귀. 인수인계 설계 정립(work_log 2026-08-01:73-75,123-126).
- **Hardening #1(indexing 전수 가드)·#3(SoT 확인)**: 6c-2/6d 종료 시 처리 권장.
- **test-mongo**: healthy(이 세션에서 39분 가동). 6c-2 회귀용으로 그대로 재사용 가능 — 재기동 불필요.
- 작업 트리 clean. push 는 오너.

## Reproduction

```bash
# 전체 green bar 재현
python3 -m pytest -q
# → 1810 passed, 4 skipped, 1519 subtests (test-mongo ON)

# 영향 4 파일
python3 -m pytest tests/test_memory_vector_index.py tests/test_chroma_memory_adapter.py \
  tests/test_context_search_memory_lexical_retrieval.py tests/test_candidate_index.py -q
# → 86 passed, 3 skipped

# 양방향 뮤테이션(각각: 변이 → re-fail 확인 → git checkout -- <file> 원복)
# A(under-strict): memory_index.py:148-152 본문을 `pass` 로
python3 -m pytest tests/test_memory_vector_index.py -q -k MemoryVectorPurge   # 3 re-fail
# B(over-strict): 동 본문을 `self.records = {}` 로            # 3 re-fail
# C(composite 삼킴): memory_index.py:274-275 를 try/except pass # 1 re-fail(propagation)
git checkout -- services/application/app/indexing/memory_index.py            # 원복
```
