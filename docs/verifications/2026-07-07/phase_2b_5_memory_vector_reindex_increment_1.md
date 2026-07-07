# Verification — Phase 2B.5 memory→vector 재색인 증분 1(계약+fake+회귀)

## Subject metadata

- **Date**: 2026-07-07
- **Requester**: entangelk (오너) — “클로드 작업 AI가 작업한 부분 확인하고 검증하고 의심하고 또 의심해줄래? … Phase 2B.5 (memory→vector 재색인)을 진행했습니다.”
- **Verifier**: Claude (독립 검증, 구현 작업 미관여)
- **Target slice / artifact**: Phase 2B.5 **증분 1** — `services/application/app/indexing/memory_index.py`(신규: projection·`MemoryVectorIndexAdapter`/`InMemoryMemoryVectorIndexAdapter`·`MemoryIndexSyncAdapter`), `indexing/models.py`(`IndexRecordKind.MEMORY`·`IndexSyncEvent.MEMORY_UPSERTED`·`MemoryIndexRecord`), `indexing/service.py`(`enqueue_memory_upserted`·worker memory dispatch·`_enqueue_event` 개명·`MEMORIES_COLLECTION`), `analysis/apply.py`(`MemoryReindexOutbox` seam·`MemoryApplyService.reindex_outbox`·`_enqueue_reindex`), `main.py`(주석·미배선 명시), 회귀 `tests/test_memory_vector_index.py`(신규 14).
- **Canonical spec reference**:
  - `docs/system-contract-sot.md` v1.6.45(version-table 신규 행 + §Phase 2B prose 행).
  - `docs/plans/02b-5-memory-vector-reindex-decisions.md`(Resolved, D1~D7 + Owner decisions + 패턴 스윕 open item).
  - 하위 계약: v1.6.44(2B.4 append-only `SUPERSEDED`/`supersedes`/`MemoryStatus`), v1.6.40(2B.1 `MemoryEntry`/`promote_candidate`), v1.6.29/v1.6.37(worker claim/retry/backoff + terminal-move lifecycle).
- **Source of work being verified**: working tree, **uncommitted**(HEAD `1211957`). 커밋 전 상태로 검증.

## Scope

본 검증은 아래 표면을 2B.5 증분 1 계약(SoT v1.6.45 + 결정 브리프 D1~D7 + Owner decisions) 대비로 점검한다.

1. **계약(contract)**: SoT v1.6.45 경계(신설 literal·projection 투영·enqueue 조건·dedup·worker dispatch·canonical-only self-heal·no_change/conflict 무enqueue) + 브리프 D1~D7 추천/확정값 + Owner decisions(D3=B·D6=write-only·D4 교정).
2. **구현 코드**: `memory_index.py`(projection/adapter/self-heal), `indexing/service.py`(enqueue+dispatch+dedup), `indexing/models.py`(literal/record), `analysis/apply.py`(enqueue seam), `main.py`(미배선 명시).
3. **회귀 테스트**: `tests/test_memory_vector_index.py`(14 = projection 3 + enqueue 5 + worker 6).
4. **공개 표면/envelope**: outbox entry의 `event`/`source.{mongo_collection,mongo_id,mongo_version}`·`targets.chroma.backend`, `MemoryIndexRecord` literal, canonical-only vector 수렴 결과.
5. **전체 스위트**(증분 1은 infra-free fake 한정; live Chroma/배포 worker 배선은 증분 2 범위 밖).

## Methodology

scoped reading(SoT v1.6.45 신규 행 + 브리프 D1~D7/Owner decisions + 하위 v1.6.44 계약)로 boundary matrix(“실행되어야 할 분기” + “실행되지 않아야 할 분기” + literal/dedup/dispatch)를 만들고, 각 셀이 어느 회귀에 대응하는지 추적했다. 이후 코드·테스트를 1차 원천으로 재유도하고, 독립 probe와 변이(mutant)로 증명했다. dedup key 구성과 `MEMORY_UPSERTED` dispatch 동작은 소스를 직접 읽어 재확인했다.

정확한 명령:

```bash
# (1) 컴파일 + diff 위생
python3 -m py_compile services/application/app/indexing/memory_index.py \
  services/application/app/indexing/models.py services/application/app/indexing/service.py \
  services/application/app/analysis/apply.py services/application/app/main.py \
  tests/test_memory_vector_index.py
git diff --check   # clean

# (2) focused + 전체 스위트(mongo env 제외 — 작업자와 동일 조건)
python3 -m unittest tests.test_memory_vector_index -v        # 14 OK
python3 -m pytest -q --ignore=tests/test_memory_mongo.py     # 579 passed / 45 skipped

# (3) 미추적 분기 독립 probe(PYTHONPATH=repo root)
#     (a) MEMORY_UPSERTED + memory_adapter=None -> BACKEND_ERROR/RuntimeError (SoT v1.6.45)
#     (b) derive_memory_index_text unsupported type -> ValueError (defensive)
PYTHONPATH=. python3 - <<'PY'  # (요약; 전체 probe는 본 검증 세션에서 실행)
...IndexSyncWorker(memory_adapter=None).run_once(...)  # -> failed=1, requeued=1, last_error=BACKEND_ERROR
...derive_memory_index_text(<other enum>, {...})        # -> ValueError
PY

# (4) 변이(mutant) 증명 — 핵심 guard 2종의 under/over 방향 non-vacuity
#     MemoryIndexSyncAdapter 를 상속해 (a) supersedes-delete 무력화, (b) status self-heal 무력화
#     한 뒤 각각 test_update_replaces_prior_version_vector(==1)/test_superseded_id_is_dropped(==0) 가
#     재실패하는지 확인 → 둘 다 load-bearing 확인(MUT1->2 records, MUT2->1 record).
```

## Findings

### 1. 계약 경계 ↔ 회귀 추적 (boundary matrix)

scoped reading에서 뽑은 경계와 대응 회귀. **빈 셀(EMPTY)은 CLAUDE.md상 차단 후보**로 별도 취급(Findings 2).

| # | 계약 경계(SoT v1.6.45 / 브리프) | 코드 | 회귀 | 상태 |
|---|---|---|---|---|
| 1 | D1 projection character=`name\nobservation` | `memory_index.py:45-46` | `test_character_projects_name_and_observation` | LOCKED |
| 2 | D1 projection event=`event` | `memory_index.py:47-48` | `test_event_projects_event_text` | LOCKED |
| 3 | D1 projection open_question=`question` | `memory_index.py:49-50` | `test_open_question_projects_question_text` | LOCKED |
| 4 | D2/D5 `MemoryIndexRecord` + `IndexRecordKind.MEMORY` + `memory_vectors` collection | `models.py:11,135-153`·`memory_index.py:34` | (worker 테스트로 전이적) | LOCKED(전이) |
| 5 | D3=B create → enqueue `MEMORY_UPSERTED`(memory_id) | `apply.py:100-107`·`service.py:307-319` | `test_create_enqueues_reindex` | LOCKED |
| 6 | versioned(update/add_evidence) → enqueue **신규** memory_id/version | `apply.py:100-107` | `test_update_replaces_prior_version_vector`(version==2 전이) | LOCKED(전이) |
| 7 | no_change → enqueue **없음**(over-strict guard) | `apply.py:100` | `test_no_change_does_not_enqueue` | LOCKED |
| 8 | conflict → enqueue 없음 | `apply.py:100,119-122` | `test_conflict_does_not_enqueue` | LOCKED |
| 9 | outbox 미구성 → noop | `apply.py:89` | `test_no_outbox_configured_is_a_noop` | LOCKED |
| 10 | dedup per memory_id(**version 무관**) | `service.py:307-319` + `_dedup_key:667-670` | `test_enqueue_dedups_same_memory` | LOCKED |
| 11 | D4 canonical+supersedes → 신규 upsert + 이전 id delete(canonical-only) | `memory_index.py:147-163` | `test_update_replaces_prior_version_vector`(양방향) | LOCKED(mutant 증명) |
| 12 | D4 교정 non-canonical entry → 그 id delete + skip(순서 무관 self-heal) | `memory_index.py:147-154` | `test_superseded_id_is_dropped_not_reindexed`(고립) | LOCKED(mutant 증명) |
| 13 | missing memory → stale delete + no-crash | `memory_index.py:140-145` | `test_missing_memory_removes_stale_vector_without_crash` | LOCKED(no-crash; delete 절반 미 seed) |
| 14 | idempotent re-reindex → 1 record 동일 id | — | `test_reindex_is_idempotent` | LOCKED |
| 15 | event/open_question 항상 create → 누적(2 records) | — | `test_events_accumulate_as_separate_records` | LOCKED |
| 16 | **dispatch `MEMORY_UPSERTED` + adapter 미구성 → RuntimeError/BACKEND_ERROR**(SoT v1.6.45 “미구성 시 RuntimeError”) | `service.py:455-460` | **(없음)** | **EMPTY(조건)** |
| 17 | projection 미지원 type → `ValueError`(방어) | `memory_index.py:51` | **(없음)** | **EMPTY(minor, enum-도달불가)** |

행 1~15는 모두 추적 가능하며, 핵심 guard(11·12)는 변이 증명으로 load-bearing임을 확인했다(Findings 3).

### 2. 빈 셀(EMPTY) — 차단/조건 후보

- **행 16(조건)**: SoT v1.6.45가 “`IndexSyncWorker`가 `MEMORY_UPSERTED`를 optional `memory_adapter`로 dispatch(**미구성 시 RuntimeError**)”라고 명시한다. 본 세션 독립 probe(`IndexSyncWorker(memory_adapter=None)` + memory entry → `run_once`)로 동작은 확인했다: dispatch가 `RuntimeError`를 던지고 worker가 generic `except Exception`으로 잡아 `IndexSyncLastError(error_type=BACKEND_ERROR, detail="memory index adapter is not configured for MEMORY_UPSERTED")` 기록 + requeue. 그러나 **이 분기를 고정하는 회귀가 `tests/test_memory_vector_index.py`에 없다.** 증분 1 배포면(create_app이 `reindex_outbox` 미배선)에서는 memory entry 자체가 발생하지 않아 도달 불가지만, SoT가 명시한 계약 동작인 만큼 회귀로 잠가야 boundary matrix가 닫힌다. 이것이 본 검증의 **유일한 차단 조건**이다.
- **행 17(minor)**: `derive_memory_index_text`의 `raise ValueError`(지원하지 않는 memory_type) 분기. `AnalysisCandidateType` enum이 3종으로 고정이라 현재 도달 불가(사실상 §2 “impossible scenario” 방어 코드). 회귀 부재를 non-blocking 권고로만 둔다. 다만 이 분기가 정말 필요한지(§2 단순성)는 작업자 판단 영역.

### 3. D4 교정 canonical-only self-heal — 정확성 + non-vacuity 독립 증명

- **D4 교정의 정당성 확인**: 브리프 원 추천(“record id=memory_id, upsert가 최신 교체”)은 2B.4 append-only와 모순이다. 2B.4 `_versioned_upsert`(`memory/service.py:_versioned_upsert`)는 update/add_evidence 시 **새 `MemoryEntry` id**를 mint하고 이전 entry를 `SUPERSEDED`로 전이(`supersedes=이전 id`)한다. 따라서 단순 upsert(id=memory_id)면 각 version이 별개 id라 이전 version 벡터가 잔류해 canonical-only가 깨진다. 작업자의 교정(status reload + non-canonical self-delete + canonical supersedes-delete)이 이 모순을 정확히 해소함을 1차 소스(`memory_index.py:133-163`, `memory/service.py:_versioned_upsert`)로 확인했다.
- **멱등·순서 무관 추론 검증**: v1→v2→v3 연쇄를 손으로 추적. 각 version은 자기 enqueue entry를 가지므로, non-canonical self-heal(자기 id delete) + canonical의 직전-predecessor delete의 조합이 어떤 drain 순서에서도 “정확히 현 canonical만”으로 수렴함을 확인(직접 회귀는 v1→v2까지만 다루지만 분기가 개별 잠금돼 추론이 성립).
- **양방향 non-vacuity 변이(mutant) 재실증**(작업자 주장을 독립 재증명): `MemoryIndexSyncAdapter`를 상속해
  - (a) supersedes-delete 블록 무력화 → `test_update_replaces_prior_version_vector` 조건이 **2 records**(==1 위반)로 재실패 → guard load-bearing.
  - (b) non-canonical status self-heal 무력화 → `test_superseded_id_is_dropped_not_reindexed` 조건이 **1 record**(==0 위반)로 재실패 → guard load-bearing.
  - 두 방향 모두 의미 있게 재실패. 작업자의 non-vacuity 주장은 사실이다.

### 4. dedup “per memory_id” 주장 검증

- `IndexSyncOutboxService.enqueue_memory_upserted`(`service.py:307-319`) → `_enqueue_event` → `get_outbox_entry_by_dedup_key`. dedup key는 `_dedup_key = (project_id, event, mongo_collection, mongo_id)`(`service.py:667-670`)로 **`mongo_version`을 포함하지 않는다**. 따라서 브리프/SoT의 “dedup per memory_id(version 무관)” 주장이 정확하다. 같은 memory_id의 replay는 하나의 pending entry로 collapse된다. 한편 update는 **새 id**를 mint하므로 v1 entry와 v2 entry는 애초에 dedup 충돌하지 않고 별개 entry로 enqueue된다 — 이것이 self-heal 설계와 정합.

### 5. enqueue seam 배선 상태(create_app 미배선) 검증

- `enqueue_memory_upserted`의 참조는 `apply.py:103`(seam)·`service.py:307`(정의)·`tests/test_memory_vector_index.py`에만 존재한다(`grep` 확인). `main.py`의 promote(`:981-989` `memory.promote_candidate` 직접)·auto-promote(`:1001-1027` `memory.auto_promote_candidate` 직접)·apply endpoint(`:1217`) 어디에도 reindex 배선이 없다. 특히 `main.py:471`의 `apply_service = MemoryApplyService(memory_service=memory)`는 `reindex_outbox`를 주입하지 않아 **live apply 경로도 enqueue하지 않는다**. 이는 증분 1의 명시적 결정(drain 측 실 adapter 부재 시 undrainable entry 미생성, 2B.3 judge-None seam 리듬)이며, SoT v1.6.45 prose와 일치한다. 주석(`main.py:466-470`)도 그렇게 서술한다.

### 6. 패턴 스윕(작업자 surface) 검증

- 작업자가 브리프 “패턴 스윕 발견”에서 **canonical 생성 경로가 apply만이 아님**(2B.1 수동 promote 활성, auto-promote 기본 off)을 surface하고, enqueue 배선을 증분 2 오너 확인 항목으로 이월했다. 이는 CLAUDE.md §1(모순/경계 surface)와 §“pattern sweep”에 부합하며, Findings 5의 `grep` 결과와 정확히 일치한다. 증분 1 범위(브리프 D3=B infra note가 enqueue를 apply에 한정)를 넘는 정당한 이월이다.

### 7. 테스트 코드 감사(test code is audit subject, not auditor)

- `tests/test_memory_vector_index.py`의 assertion이 계약을 pin하는지 확인: `test_create_enqueues_reindex`는 `event==MEMORY_UPSERTED` + `source.mongo_id==memory_id`(=신규 version id)를 직접 단정(envelope). `test_update_replaces_prior_version_vector`는 `version==2`·`text=="Ariel\nbold"`·prior id 부재를 단정(canonical-only). `test_superseded_id_is_dropped_not_reindexed`는 adapter를 **직접 구동**해 supersedes-delete에 기대지 않고 self-heal 분기를 고립(작업자가 최초 stale 테스트의 우연 커버를 mutation으로 적발해 교정했다는 주장과 부합). assertion은 전부 public surface(record/outbox entry)를 겨냥하고 내부 헬퍼가 아니다.
- **over-strict guard 존재 확인**: no_change(`test_no_change_does_not_enqueue`)·conflict(`test_conflict_does_not_enqueue`)가 enqueue=0을 단정해 “실행되지 않아야 할 분기”를 잠근다(CLAUDE.md 양방향).

### 8. 문서 정합

- CHANGELOG 최상단 행(2026-07-07, SoT v1.6.45)과 work log 링크 정확.
- SoT version-table v1.6.45 행이 구현(literal/projection/dispatch/회귀 수)과 정합. §Phase 2B prose에 v1.6.45 행 추가됨.
- HANDOFF Current Status(`:126`)·Next Tasks #1(`:138`) 증분 2 라이브 배선으로 갱신됨.
- **문서 간 경계 차이(비차단)**: 브리프 D1 Owner decision(`plans/02b-5-...md:114`) prose가 “character=name+**description**류”로 쓰지만, 코드(`memory_index.py:46`)·SoT v1.6.45 행·2A 스키마(`character_observation {name, observation}`)는 모두 `observation`이다. 코드/SoT가 정본 스키마와 일치하므로 **브리프 prose만 느슨한 표기**. 비차단 doc 정정 권고.
- **(사전 이슈, 본 slice 비관여)** 본 slice 이전 SoT 헤더가 v1.6.40이었으나 version-table에 v1.6.41~44 행이 이미 존재했다(2B.2~2B.4가 헤더 미갱신). 본 slice가 헤더를 v1.6.45로 올려 table 최신 행과 일치시켰다. 정보성 기록.

## Issues / Risks

- **[차단/조건] 행 16 미추적 분기**: `MEMORY_UPSERTED` + `memory_adapter` 미구성 → `RuntimeError`(worker 관점 `BACKEND_ERROR`+requeue) 분기가 SoT v1.6.45에 명시돼 있으나 회귀가 없다. CLAUDE.md boundary-matrix 원칙상 빈 셀. 회귀 1개(예: `test_memory_upserted_without_adapter_records_backend_error`) 추가 시 폐쇄. 독립 probe로 동작 자체는 확인했으므로, 코드 수정이 아닌 **테스트 추가**만으로 닫힌다.
- **[비차단] 행 17**: projection 미지원 type `ValueError` 분기 무회귀. enum 고정으로 도달 불가(방어 코드). 필요성은 작업자 판단.
- **[비차단] 행 13 delete 절반 미 seed**: `test_missing_memory_removes_stale_vector_without_crash`가 ghost id(벡터 없음)로 no-crash·success만 증명. “이미 존재하는 stale 벡터 삭제” 절반은 seed하지 않는다. 2B.4에 hard-delete가 없어 현재 도달 불가이나, self-heal의 delete 호출을 seed로 입증하면 더 강건(행 12가 supersedes-delete를 seed로 입증하므로 같은 `delete_memory_record` 경로는 이미 검증됨).
- **[비차단, 증분 2 이월] `targets.chroma.backend` stamping**: `enqueue_memory_upserted`가 memory entry의 `targets.chroma.backend`를 `IN_MEMORY_FAKE`로 고정(`service.py:_enqueue_event`). archive 경로(v1.6.26)와 동일 패턴이며 worker 실 backend는 env(`CHROMA_HOST`) 결정이라 정확성 영향 없으나, 증분 2 real Chroma 배선 시 fidelity 점검 항목.
- **[비차단, 증분 2 이월] promote/auto-promote 경로 enqueue 부재**: 작업자가 정확히 surface했고 브리프 범위 밖(apply 한정)이므로 증분 2 오너 확인 항목. 본 slice 결함 아님.
- **[비차단, 설계 수용] 배치 중간 예외 시 커밋-됐지만-enqueue-누락 memory**: `apply_proposals`(`apply.py:86-92`)가 `_apply_one` generator를 tuple로 즉시 소비한 뒤에만 enqueue loop가 돈다. 따라서 proposal[1]이 `UnknownCandidate`/`MissingMatchedMemory`로 예외를 던지면, 이미 proposal[0]이 커밋한 memory write는 index에 enqueue되지 않은 채 남는다(예외가 tuple 구성 중 전파 → enqueue 미도달). 이는 2B.4 apply의 “proposal별 커밋, 배치 단위 트랜잭션 없음” 의미를 그대로 상속한 것이고, D3=B(skew 무관용·backfill로 수렴) 철학과 정합하므로 결함이 아니라 수용된 경계. 단 eventual convergence가 D7 backfill(증분 2)에 의존함을 인지해야 한다.

## Verdict

**조건부 합격(conditional pass).**

이유(차단 조건 1건):
- boundary matrix 행 16(`MEMORY_UPSERTED` + adapter 미구성 → `RuntimeError`/`BACKEND_ERROR`)이 SoT v1.6.45에 명시된 계약 분기인데 회귀가 없다. CLAUDE.md “boundary matrix has no empty cells” 원칙상 빈 셀. **회귀 1개 추가 시 합격으로 승격**.

합격 근거(이미 입증된 것):
- 핵심 canonical-only self-heal(D4 교정)은 1차 소스로 정당하고, 변이(mutant) 증명으로 두 guard 모두 load-bearing(non-vacuity)임을 독립 확인.
- dedup “per memory_id(version 무관)” 주장이 소스와 정확히 일치.
- enqueue 조건(create/versioned enqueue, no_change/conflict 무enqueue, 미구성 noop) 양방향 회귀로 잠김.
- 전체 스위트 **579 passed / 45 skipped** 독립 재실행으로 재현(작업자 주장과 동일). `git diff --check` clean. py_compile OK.
- create_app 미배선 결정·패턴 스윕(promote 경로) surface가 SoT/브리프와 정합하고 CLAUDE.md 리듬에 부합.
- 회귀 14개는 public surface를 겨냥하고 over-strict guard(no_change/conflict)를 포함.

## Outstanding items

- **[본 slice 차단 조건] 행 16 회귀 추가** — 작업자(또는 후속)가 `tests/test_memory_vector_index.py`에 adapter 미구성 dispatch 회귀를 추가하면 합격으로 승격. 본 검증은 verifier가 코드/테스트를 수정하지 않으므로(CLAUDE.md), 오너 결정을 기다린다.
- **[증분 2 — sandbox 밖, 본 slice 범위 밖]** 실 Chroma `memory_vectors` adapter(`record_to_chroma`/`connect` memory 대응) + `scripts/index_sync_worker.py` memory adapter 배선 + `create_app` apply에 `reindex_outbox` 배선 + `scripts/phase2b5_reindex_memory.py` backfill + live smoke(apply→outbox→worker→실제 Chroma record).
- **[오너 확인, 증분 2]** promote/auto-promote 경로 reindex enqueue 배선 vs 정기 backfill 수렴 중 택1.
- 미커밋 상태(working tree). 커밋/브랜치 분리는 오너 지시 대기.

## Reproduction

```bash
cd "/mnt/d/devel/에베베/ai_writte_system"

# (1) 컴파일 + diff 위생
python3 -m py_compile services/application/app/indexing/memory_index.py \
  services/application/app/indexing/models.py services/application/app/indexing/service.py \
  services/application/app/analysis/apply.py services/application/app/main.py \
  tests/test_memory_vector_index.py && git diff --check

# (2) focused 신규 회귀(14) + 전체 스위트(mongo env 제외)
python3 -m unittest tests.test_memory_vector_index -v
python3 -m pytest -q --ignore=tests/test_memory_mongo.py    # 기대: 579 passed / 45 skipped

# (3) 행 16 미추적 분기 동작 확인(adapter 미구성 -> BACKEND_ERROR)
PYTHONPATH=. python3 - <<'PY'
from services.application.app.indexing.service import (
    InMemoryIndexSyncRepository, IndexSyncOutboxService, IndexSyncWorker,
    RecordingArchiveIndexMutationAdapter,
)
repo = InMemoryIndexSyncRepository(); outbox = IndexSyncOutboxService(repo)
outbox.enqueue_memory_upserted(project_id="p1", memory_id="m1", version=1)
s = IndexSyncWorker(repository=repo, archive_adapter=RecordingArchiveIndexMutationAdapter(),
                    memory_adapter=None).run_once(limit=5)
e = list(repo.outbox_entries.values())
print(s.entries_succeeded, s.entries_failed, s.entries_requeued, e[0].last_error if e else None)
# 기대: 0 1 1 IndexSyncLastError(error_type=BACKEND_ERROR, detail='memory index adapter is not configured...')
PY
```
