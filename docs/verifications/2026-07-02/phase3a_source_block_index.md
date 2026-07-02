# Phase 3A Source Block Indexing 첫 slice 독립 검증

## Subject metadata

- 검증일: `2026-07-02`
- 요청자: 프로젝트 오너("클로드 작업 AI가 작업한 분에 대해서 검증하고 의심하고 또 의심해줄래?")
- 검증자: 독립 검증 AI (Claude)
- 검증 대상: Phase 3A 첫 slice — `services/application/app/indexing/` source block indexing domain + `tests/test_indexing_phase3a.py` + SoT v1.6.20 갱신
- 정합 스펙 기준:
  - `docs/system-contract-sot.md` v1.6.20(변경 이력 표 행 + Phase 3 Indexing 단락의 두 신규 bullet + 미확정 목록 개정)
  - `docs/plans/03-indexing-kickoff-decisions.md` "Approved for Phase 3A first slice"(§6 첫 구현 slice 제안 + §승인 결과 계약)
  - `docs/plans/03-indexing.md`(§목표/§역할 구분/§MVP 범위/§수용 기준/§단방향 동기화 + 2026-07-02 slice 축소 노트)
  - 교차 계약: `docs/contracts.md §7.2 IndexSyncRequest` / `§7.3 IndexSyncResult`(canonical JSON shape), `docs/mongo_collections.md §11 source_blocks`
- 검증 대상 작업 출처: working tree, uncommitted(직전 commit `9986da2` 이후 변경분). `git status`로 `services/application/app/indexing/`(untracked), `tests/test_indexing_phase3a.py`(untracked), 6개 doc modified 확인.

## Scope

정합 스펙 스코프를 (1) SoT v1.6.20 changelog 행 + Phase 3 Indexing 단락 bullet, (2) kickoff 브리프 §6 첫 구현 slice 제안(승인됨) + §승인 결과, (3) `03-indexing.md §수용 기준`으로 좁혔다. 브리프가 chain하는 `contracts.md §7.2/§7.3`와 `mongo_collections.md §11`만 포함했고, Phase 3B 이후(ChromaDB/ES/자동 sync)와 이전 Phase 1/2 slice는 carried-forward로만 취급했다.

검증 surface:

1. 정합 계약(SoT v1.6.20 + kickoff 브리프 + plan §수용 기준 + contracts §7)의 내부 정합성
2. 구현 코드: `indexing/models.py`(`IndexRecordKind`/`IndexPointer`/`SourceBlockIndexRecord`/`IndexSyncResult`), `indexing/service.py`(`DeterministicFakeEmbeddingProvider`/`InMemoryVectorIndexAdapter`/`SourceBlockIndexingService.rebuild_snapshot_source_block_index`)
3. 교차 경계: `core_sot/service.py::{get_snapshot,get_project,get_draft,save_draft,archive_project,archive_draft}` 표면과 pointer/collection literal 일치
4. 회귀 테스트: `tests/test_indexing_phase3a.py` 5개 테스트 — 각 분기가 계약을 실제로 pin 하는지(under-strict + over-strict)
5. 작업자 주장 카운트 재현 + 전체 suite + `git diff --check` + hygiene

## Methodology

정합 스펙을 end-to-end 읽어 boundary matrix를 구성한 뒤, 각 분기를 코드와 테스트에 추적했다. 작업자의 work log/HANDOFF 주장을 복사하지 않고 primary source에서 재도출했다. 발견은 직접 실험과 mutation test로 입증했다.

실행한 명령:

- `git status`, `git diff --stat`, `git diff -- <doc>`(변경 범위 + 각 doc diff)
- `Read`로 `indexing/models.py`, `indexing/service.py`, `indexing/__init__.py`, `tests/test_indexing_phase3a.py` 전체 열독
- serena symbolic tools로 `core_sot/service.py::CoreSotService` 메서드 표면 확인 후 `get_snapshot`/`get_draft`/`save_draft`/`archive_project`/`archive_draft` 본체 열독
- `python3 -m unittest tests.test_indexing_phase3a -v`(5개), `... tests.test_indexing_phase3a tests.test_core_sot -v`(32개), `python3 -m unittest discover tests`(365개/37 skip) 재실행
- `git diff --check`
- `grep -rn "IndexSyncRequest"` — `.py`/`.md` 전 검색(존재/미존재 확인)
- `grep -rn "source_blocks"` + `git check-ignore` — collection literal 정합 + pycache hygiene
- adversarial 실험(`python3 -c`): (a) draft만 archive 후 rebuild → 제외 여부, (b) rebuild 후 project archive → 여전히 노출되는지
- mutation test: `service.py`에서 `and not record.draft_archived` 절을 제거하고 suite 재실행 → lock 존재 여부 입증 후 원복

## Findings

### Surface 1 — 정합 계약 내부 정합성

- SoT v1.6.20 changelog 행과 kickoff 브리프 §승인 결과, plan §2026-07-02 노트가 동일한 계약을 서술한다: target source block only, Chroma-like vector contract + deterministic fake adapter, fake embedding only, explicit rebuild, archive/delete는 status/version filter. 모순 없음.
- **pointer literal 정합(양방향)**: SoT v1.6.20이 "Index record는 `project_id`, collection, document/block id, version id, content hash를 가진 Mongo pointer"라고 서술하고, `IndexPointer(project_id, collection, document_id, version_id, content_hash)`(`models.py:13-19`)가 정확히 일치한다. `collection="source_blocks"`(`service.py:17,133`)는 canonical Mongo collection(`core_sot/mongo_repository.py:66 self._db["source_blocks"]`, `mongo_collections.md §11`)과 일치한다. `version_id` = `snapshot.version_id`(`service.py:95`), `content_hash` = `snapshot.content_hash`(`service.py:96`)로 Core SOT 표면과 연결된다.
- **contracts §7 vs 구현 — 미조정 모순(블로킹)**: `contracts.md §7.3 IndexSyncResult` canonical shape는 `sync_result_id, sync_request_id, project_id, targets{chroma,elasticsearch}, started_at, finished_at`이다. 구현 `IndexSyncResult(project_id, snapshot_id, records_attempted, records_written)`(`models.py:37-42`)과 공통 필드는 `project_id`뿐이다. SoT v1.6.20과 kickoff 브리프 어디서도 이 reduced shape가 §7.3의 Phase 3A 축소판임을 명시하지 않는다. → Issues F1 참조.

### Surface 2 — 구현 코드 vs 스펙 literal/경계

- `rebuild_snapshot_source_block_index(project_id, snapshot_id)`(`service.py:81-112`)는 Core SOT에서만 읽어 record를 materialize하고 adapter에 upsert한다. 단방향 동기화(plan §단방향 동기화 "ChromaDB/ES가 MongoDB를 직접 갱신하지 않는다")와 explicit rebuild delivery(브리프 §4-A)를 만족한다.
- idempotency: record id가 `source-block:{project_id}:{snapshot_id}:{block_id}`(`service.py:129`)로 결정적이고, adapter upsert가 dict-keyed(`service.py:48-49`)라 같은 snapshot 재처리 시 덮어쓴다. plan §수용기준 #4 "같은 sync event 재처리 시 중복 record 없음" 만족.
- adapter failure 경로(`service.py:106`): rebuild는 save 이후 별도 호출이라 구조적으로 save를 rollback할 수 없고, 실패 시 예외가 전파된다. plan §수용기준 #3 "adapter 실패가 MongoDB 정본 저장을 rollback/오염시키지 않는다" 만족.
- embedding: `DeterministicFakeEmbeddingProvider`(`service.py:28-40`)는 sha256 기반 결정적 vector. 브리프 §3-A "deterministic fake dimension" 만족.

### Surface 3 — 회귀 테스트가 계약을 pin 하는지(audit subject)

테스트 5개 중 4개는 해당 boundary를 양방향으로 잠근다:

- `test_rebuild_indexes_source_blocks_with_sot_pointer_hash_and_version`: pointer 5필드 + text + vector len + archived=False 기본값 단언. 계약 literal을 직접 pin. ✓
- `test_rebuild_is_idempotent_for_same_snapshot`: 2회 rebuild 후 record 수 2 유지. idempotency under-strict. ✓
- `test_project_isolation_filters_index_records`: project A/B 교차 색인 후 각 project query가 자기 record만 반환. 수용기준 #6. ✓
- `test_adapter_failure_does_not_rollback_core_sot_save`: failing adapter → 예외 + snapshot content_hash/blocks 보존. 수용기준 #3. ✓

**`test_archived_project_or_draft_records_are_filtered_from_query_results`는 project half만 잠근다(블로킹)**: 테스트는 `archive_project`만 호출한다. 필터(`service.py:60-65`)는 `project_archived`와 `draft_archived` 두 flag를 모두 검사하지만, draft-archived 분기는 어떤 테스트도 거치지 않는다. → Issues F2 참조.

### Surface 4 — 작업자 주장 카운트 재현

작업자 주장을 그대로 믿지 않고 모두 재실행해 재도출:

- `python3 -m unittest tests.test_indexing_phase3a -v` → **Ran 5 tests, OK**(주장 5개 일치)
- `python3 -m unittest tests.test_indexing_phase3a tests.test_core_sot -v` → **Ran 32 tests, OK**(주장 32개 일치)
- `python3 -m unittest discover tests` → **Ran 365 tests, OK (skipped=37)**(주장 365/37 일치)
- `git diff --check` → 종료 0, clean(주장 일치)
- `git check-ignore services/application/app/indexing/__pycache__/models.cpython-312.pyc` → ignored. `.gitignore`(`__pycache__/`, `*.pyc`)가 새 dir의 pycache를 다루므로 hygiene 이슈 아님.

## Issues / Risks

### F1 — `IndexSyncRequest`/`IndexSyncResult` 계약 미조정(블로킹, contract gap)

- **F1a**: kickoff 브리프 §6 item 1(승인된 slice)과 plan §산출물 #1("공통 IndexSyncRequest/Result 계약")이 `IndexSyncRequest`를 pure domain model로 추가하라고 명시한다. `grep -rn "IndexSyncRequest" --include="*.py"` 결과 `.py` 정의가 전혀 없다. 구현은 `IndexSyncResult`만 있다. 더불어 work log는 model 목록에서 `IndexSyncRequest`를 조용히 빼버렸다(문서화되지 않은 이탈).
- **F1b**: 구현 `IndexSyncResult` shape이 `contracts.md §7.3` canonical과 크게 다르다(공통 필드 `project_id`뿐). SoT v1.6.20도 kickoff 브리프도 이 reduced shape를 §7.3와 조정하지 않는다. CLAUDE.md "Spec-silent-but-code-enforced is a contract gap"에 해당 — 코드가 §7.3와 다른 shape를 강제하면서 어느 쪽이 canonical인지 문서가 말해주지 않는다.
- **해결(오너 결정 필요)**: (i) `IndexSyncRequest`를 추가하고 SoT에 "Phase 3A IndexSyncResult는 explicit-rebuild reduced shape, §7.3는 후속 full target"이라 명시, 또는 (ii) SoT/브리프를 개정해 `IndexSyncRequest`와 §7.3 shape를 Phase 3A slice에서 명시적으로 후속으로 빼기. CLAUDE.md상 묵히 선택하는 것은 허용되지 않는다.
- **참고**: CLAUDE.md §2(Simplicity First)는 사용되지 않는 `IndexSyncRequest` dataclass 생략을 정당화할 여지가 있다(rebuild가 explicit kwargs를 받으므로). 하지만 그 결정은 문서화돼야 한다.

### F2 — `draft_archived` query 제외 분기가 테스트에 없음(블로킹, 미잠금 boundary)

- 브리프 §6 item 5와 SoT v1.6.20이 "archived **project/draft** record가 query 결과에서 제외"를 명시한다. 필터는 두 flag를 모두 검사하지만, 회귀 테스트는 project archive만 다룬다.
- **adversarial 입증**: draft만 archive(project 활성)하고 rebuild하면 `draft_archived=True`로 capture돼 default query가 0건을 반환함을 확인했다(분기 자체는 동작). 그러나 mutation test로 `service.py`에서 `and not record.draft_archived` 절을 제거하면 **5개 테스트 전부 여전히 green**이다. 즉 이 분기를 잠그는 테스트가 없고, 누군가 draft 절을 실수로 지워도 아무 테스트가 잡지 못한다.
- CLAUDE.md 검증 규칙: "should NOT fire" 분기가 untraced면 green bar와 무관하게 블로킹이며, 미issing over-strict guard를 "후속 보강 후보"로 재진술할 수 없다.
- **해결**: draft를 archive(project 활성)한 뒤 record가 제외됨을 양방향(under-strict + over-strict)으로 잠그는 회귀를 추가하거나, slice의 회귀 조건을 project-only로 좁히고 SoT/브리프의 "project/draft"를 "project"로 정정할 것.

### R1 — archive 제외가 point-in-time이라 live query 보장 아님(비블로킹, 명확화 권장)

- `list_records`는 rebuild 시점에 capture된 per-record `project_archived`/`draft_archived` flag로 필터한다. **입증**: rebuild 후 project를 archive하면 다음 rebuild 전까지 record 2건이 여전히 query에 노출된다(record.project_archived=False로 고정).
- SoT v1.6.20 / 브리프 문장 "archived record는 query 결과에서 제외한다"는 live query 보장처럼 읽히지만, 구현은 rebuild 반영 후에만 보장한다.
- **부분 완화**: HANDOFF Next Tasks #3이 "archive event 자동 sync는 아직 없다"로 인지하고, SoT 미확정 목록이 "삭제 rebuild 정책 미확정"으로 둔다. 권장: SoT v1.6.20 entry가 "제외는 rebuild 반영 후"로 명시해 문장이 과대 약속하지 않게 할 것. 브리프 §5-A가 언급한 `snapshot_version` filter는 stale 영역이라 후속으로 빠져 있고(일관됨), 구현은 status half만 다룬다.

## Verdict

**조건부 합격(conditional pass).**

이유(지불하는 조건):

1. **F2(블로킹 미잠금)**: `draft_archived` query 제외 분기가 어떤 테스트에도 추적되지 않는다(mutation test 입증). CLAUDE.md 검증 규칙상 untraced "should NOT fire" 분기는 green bar와 무관하게 합격을 막는다. draft-archive 회귀를 추가하거나 slice 범위/계약 문장을 project-only로 정정해야 한다.
2. **F1(블로킹 contract gap)**: `IndexSyncRequest`가 승인된 slice item 대비 누락되고, `IndexSyncResult` shape가 `contracts §7.3`와 조정되지 않은 채 공존한다. SoT에서 Phase 3A reduced shape/§7.3 관계를 명시하거나 둘을 후속으로 명시적으로 빼야 한다.

완전 합격이 아닌 이유는 위 두 블로킹 조건이 남아 있어서다. 반면, **구현된 동작 자체는 정확하고 내부 일관적**이며, pointer/version/hash 보존·idempotency·project isolation·adapter-failure non-rollback는 테스트로 제대로 잠겨 있고, 작업자가 보고한 모든 카운트(5/32/365+37)와 `git diff --check`가 정확히 재현됐다. R1은 비블로킹 명확화 항목이다.

## Outstanding items

- 작업 트리에 uncommitted(오너가 커밋 승인 전). 본 검증은 working tree 기준.
- F1/F2 해결 후에만 커밋/승인 권장. 해결 없이 커밋하면 "5개 통과" green bar가 미잠금 분기와 미조정 계약을 숨기는 상태로 확정된다.
- F1 해결 방향(i 모델 추가 + SoT 명시 vs ii 후속으로 명시적 제외)과 F2 해결 방향(회귀 추가 vs slice 범위 정정)은 오너 결정 사항. 검증자는 코드를 자동 수정하지 않는다(CLAUDE.md).

## Reproduction

```bash
# 카운트 재현(작업자 주장과 동일)
python3 -m unittest tests.test_indexing_phase3a -v                   # 5
python3 -m unittest tests.test_indexing_phase3a tests.test_core_sot -v  # 32
python3 -m unittest discover tests                                    # 365, skipped=37
git diff --check                                                      # clean

# F2 입증(mutation): draft_archived 절 제거 시에도 suite가 green → lock 없음
cp services/application/app/indexing/service.py /tmp/svc.bak
sed -i 's/if not record.project_archived and not record.draft_archived/if not record.project_archived/' \
  services/application/app/indexing/service.py
python3 -m unittest tests.test_indexing_phase3a                       # 여전히 5 OK (lock 없음 입증)
cp /tmp/svc.bak services/application/app/indexing/service.py && rm /tmp/svc.bak

# F2/R1 입증(동작 실험): draft-only archive 제외 / rebuild 후 archive 노출
python3 -c "
from services.application.app.core_sot.service import CoreSotService, InMemoryCoreSotRepository
from services.application.app.indexing.service import (SourceBlockIndexingService, DeterministicFakeEmbeddingProvider, InMemoryVectorIndexAdapter)
def mk(n):
    cs=CoreSotService(InMemoryCoreSotRepository()); p=cs.create_project(name=n)
    d=cs.create_draft(project_id=p.id,title='E')
    sv=cs.save_draft(project_id=p.id,draft_id=d.id,raw_text='문장1.\n\n문장2.',idempotency_key=f'k-{n}')
    idx=InMemoryVectorIndexAdapter()
    return cs,idx,SourceBlockIndexingService(core_sot=cs,embeddings=DeterministicFakeEmbeddingProvider(),vector_index=idx),p,d,sv
cs,idx,svc,p,d,sv=mk('A'); cs.archive_draft(project_id=p.id,draft_id=d.id); svc.rebuild_snapshot_source_block_index(project_id=p.id,snapshot_id=sv.snapshot.id)
print('draft-only archive default list(len, expect 0):', len(idx.list_records(project_id=p.id)))
cs,idx,svc,p,d,sv=mk('B'); svc.rebuild_snapshot_source_block_index(project_id=p.id,snapshot_id=sv.snapshot.id); cs.archive_project(project_id=p.id)
print('rebuild-then-archive default list(len, expect 2 → stale 노출):', len(idx.list_records(project_id=p.id)))
"

# F1 입증: IndexSyncRequest 가 .py 에 정의 없음
grep -rn "IndexSyncRequest" --include="*.py" .   # (매칭 없음)
grep -n "IndexSyncRequest" docs/contracts.md docs/plans/03-indexing.md docs/plans/03-indexing-kickoff-decisions.md  # 문서에는 존재
```
