# Phase 3A Explicit Rebuild CLI 독립 검증

## Subject metadata

- 검증일: `2026-07-02`
- 요청자: 프로젝트 오너("다음작업 검증해줘 ... Phase 3A explicit rebuild CLI를 추가했습니다")
- 검증자: 독립 검증 AI (Claude)
- 검증 대상: Phase 3A 후속 slice — `scripts/phase3a_rebuild_source_block_index.py` + `tests/test_phase3a_rebuild_source_block_index_script.py` + SoT v1.6.22 갱신
- 정합 스펙 기준:
  - `docs/system-contract-sot.md` v1.6.22(변경 이력 행 + Phase 3 Indexing 단락 신규 bullet)
  - `docs/plans/03-indexing-kickoff-decisions.md` §구현 후속 — explicit rebuild script
  - `docs/plans/03-indexing.md` 2026-07-02 slice 노트의 script 문장
  - 교차 계약: 직전 commit `6d4d689`의 indexing domain(`IndexSyncRequest(project_id, snapshot_id, target)` / `IndexSyncResult(request, records_attempted, records_written)` / `IndexSyncTarget.VECTOR`), `core_sot/mongo_repository.py::MongoCoreSotRepository.from_uri`, `core_sot/service.py::CoreSotService`
- 검증 대상 작업 출처: working tree, uncommitted(직전 commit `6d4d689` 이후). `git status`로 신규 `scripts/phase3a_rebuild_source_block_index.py`, `tests/test_phase3a_rebuild_source_block_index_script.py`(untracked), 6개 doc modified 확인.

## 선행 — 직전 slice 검증 이슈(F1/F2) 폐쇄 확인

이 slice는 직전 `6d4d689`(SoT v1.6.21) 위에 올라간다. 이전 독립 검증(`docs/verifications/2026-07-02/phase3a_source_block_index.md`)의 블로킹 2건이 커밋에서 폐쇄됐는지 먼저 확인했다.

- **F1(IndexSyncRequest/Result 계약 미조정) 폐쇄**: `models.py`에 `IndexSyncRequest(project_id, snapshot_id, target)`와 `IndexSyncTarget` enum(`VECTOR="vector"`)이 추가됐고, `IndexSyncResult(request, records_attempted, records_written)`로 request를 품는 shape로 개정됐다. SoT v1.6.21이 이를 "explicit rebuild용 in-process 축소 계약"으로 명시하고 `contracts.md §7.3` persistent envelope과의 관계(후속 sync log slice)를 조정했다. ✓
- **F2(draft_archived 분기 미잠금) 폐쇄**: `tests/test_indexing_phase3a.py`에 `test_archived_draft_records_are_filtered_without_project_archive`(line 102, `archive_draft` 호출 후 제외 단언)이 추가됐다. 이제 `service.py`에서 `and not record.draft_archived` 절을 제거하면 이 테스트가 실패한다(이전 검증의 mutation 우려 해소). ✓

두 이슈 모두 정상 폐쇄. 이 slice 검증은 이 기준 위에서 수행했다.

## Scope

정합 스펙 스코프를 (1) SoT v1.6.22 changelog 행 + Phase 3 bullet, (2) kickoff 브리프 §구현 후속, (3) `03-indexing.md` slice 노트의 script 문장으로 좁혔다. CLI가 의존하는 indexing domain contract는 직전 commit의 committed 상태를 기준으로 삼았다.

검증 surface:

1. 정합 계약(SoT v1.6.22 + 브리프 §구현 후속)의 내부 정합성 + JSON summary literal 일치
2. 구현 코드: `scripts/phase3a_rebuild_source_block_index.py`(arg parsing, `rebuild_source_block_index`, `run_rebuild`, `_core_sot_from_mongo`, `main`, `terminal_status`)
3. 교차 결합: `MongoCoreSotRepository.from_uri` 시그니처, canonical Mongo db 이름, indexing `IndexSyncResult.request.{project_id,snapshot_id,target.value}` 접근
4. 회귀 테스트: `tests/test_phase3a_rebuild_source_block_index_script.py` 5개 테스트 — public CLI 표면(exit code, JSON summary, 에러 경로) pin 여부
5. 작업자 주장 카운트 재현 + 전체 suite + `git diff --check`

## Methodology

정합 스펙을 읽어 boundary matrix를 구성한 뒤 코드/테스트에 추적. 작업자 주장을 복사하지 않고 재실행·재도출. 발견은 직접 `python3 -c` 실행과 signature 조회로 입증.

실행한 명령:

- `git show --stat 6d4d689`, `git log --oneline`, `git status --short`(직전 commit 범위 + 현재 변경)
- `Read`로 신규 script와 test 전체, committed `indexing/models.py`·`service.py` 열독
- `git diff docs/system-contract-sot.md CHANGELOG.md docs/plans/03-indexing*.md`(CLI slice 계약 diff)
- serena `find_symbol`로 `MongoCoreSotRepository/from_uri` 본체 확인
- `grep`로 canonical db 이름(`ai_writing_system`) 비교 + indexing 테스트의 F2 closure(`archive_draft`) 확인
- `python3 -m unittest tests.test_phase3a_rebuild_source_block_index_script`(5), `... tests.test_indexing_phase3a tests.test_core_sot`(38), `discover tests`(371/37) 재실행
- adversarial 실행: 실제 `run_rebuild`(fake 아님)의 no-uri ValueError, `main()` exit 1(partial write), 존재하지 않는 snapshot_id의 `NotFound` 처리, `NotFound`가 `ValueError` subclass인지(`CoreSotError` MRO)

## Findings

### Surface 1 — 정합 계약 내부 정합성 + literal 일치

- SoT v1.6.22 changelog 행, Phase 3 bullet, kickoff 브리프 §구현 후속, `03-indexing.md` slice 노트가 동일한 script 계약을 서술한다. 모순 없음.
- **JSON summary literal(양방향)**: SoT v1.6.22가 명시한 8개 field `project_id, snapshot_id, target, records_attempted, records_written, records_indexed, records_query_visible, records_archived`가 `rebuild_source_block_index` 반환 dict(script:83-92)와 정확히 일치한다. 테스트(line 29-36)가 전 field를 단언. ✓
- `target` = `result.request.target.value` = `IndexSyncTarget.VECTOR.value` = `"vector"`(script:86). 테스트 `assertEqual(summary["target"], "vector")`. ✓

### Surface 2 — 구현 코드 vs 스펙/경계

- `rebuild_snapshot_source_block_index(core_sot, project_id, snapshot_id, embedding_dimensions=4)`(script:61-92)는 `SourceBlockIndexingService`로 rebuild 후 adapter에서 `list_records(include_archived=True/False)`로 summary를 채운다. in-memory adapter를 script-local로 생성하므로 매 호출마다 fresh(상태 비저장). explicit rebuild delivery(브리프 §4-A)와 일치.
- `main()`(script:99-116): `run_rebuild_fn`을 DI 받아 test가 Mongo 없이 exit-code 경로를 검증 가능. `except ValueError` → stderr + exit 2; 정상 시 JSON 출력 + `terminal_status`에 따라 exit 0/1.
- **에러 degrade(양방향 입증)**: `NotFound`의 MRO가 `NotFound → CoreSotError → ValueError`라 `except ValueError`가 잡는다. 존재하지 않는 snapshot_id로 실제 호출 시 `NotFound("snapshot not found")` → exit 2 + stderr로 정상 처리됨을 확인. CLI가 bad input에서 traceback 없이 degrade함. ✓
- `_core_sot_from_mongo`(script:119-132): no-uri → `ValueError("CORE_SOT_MONGO_URI or --mongo-uri is required")`. 실제 `run_rebuild`(fake 아님)로 동일 메시지·exit 2 재현 확인.

### Surface 3 — 교차 결합 정합

- `MongoCoreSotRepository.from_uri(cls, uri, *, db_name=DEFAULT_DB_NAME, use_transactions=True)`(mongo_repository.py:69-81). CLI 호출 `from_uri(args.mongo_uri, db_name=args.mongo_db, use_transactions=...)`(script:127-131)이 시그니처와 일치. ✓
- canonical db 이름: `DEFAULT_DB_NAME = "ai_writing_system"`(mongo_repository.py:42), `docker-compose.yml:33 CORE_SOT_MONGO_DB: "ai_writing_system"`, `main.py` 3곳. CLI `DEFAULT_MONGO_DB = "ai_writing_system"`(script:22) 일치. ✓
- `CORE_SOT_MONGO_DB`/`CORE_SOT_MONGO_TRANSACTIONS` env override가 `main.py`의 기존 패턴과 동일. ✓

### Surface 4 — 회귀 테스트가 public CLI 표면을 pin 하는지

- `test_rebuild_source_block_index_outputs_summary`: 8개 summary field 단언. JSON envelope pin. ✓
- `test_terminal_status_requires_full_write_count`: `terminal_status`를 양방향(2==2→True, 2 vs 1→False) pin. ✓
- `test_main_prints_summary_and_uses_terminal_exit_rule`: fake로 main() exit 0 + JSON 출력 pin. ✓
- `test_main_reports_missing_mongo_uri_as_usage_error`: fake ValueError → exit 2 + stderr pin. ✓ (단 아래 O2)
- `test_script_file_path_invocation_can_import_repo_packages`: `python3 scripts/...py --help` subprocess로 exit 0 + `--project-id`/`--snapshot-id` 출력 pin. path/독립 실행 검증. ✓

### Surface 5 — 작업자 주장 카운트 재현

- `tests.test_phase3a_rebuild_source_block_index_script` → **5 OK**(주장 일치)
- `+ test_indexing_phase3a + test_core_sot` → **38 OK**(주장 일치)
- `discover tests` → **371 OK (skipped=37)**(주장 일치)
- `git diff --check` → 종료 0(주장 일치)

## Issues / Risks

블로킹 이슈 없음. 비블로킹 관찰만:

### O1 — CLI exit code가 spec-silent(권장: SoT 보강)

SoT v1.6.22는 JSON summary field는 정밀하게 pin하지만 exit code를 문서화하지 않는다. 코드는 `0`(full write) / `1`(partial, `records_attempted != records_written`) / `2`(usage·config·domain error: no-uri, NotFound, Archived)를 강제한다(adversarial로 전 경로 확인). exit code는 scripting caller가 의존하는 machine-readable CLI envelope의 일부다. SoT v1.6.22 행이나 브리프 §구현 후속에 exit code 표를 한 줄 추가할 것을 권장.

### O2 — main() exit-1 경로와 실제 Mongo runtime 경로가 미검증(비블로킹, coverage)

- **main() exit 1(partial write)**: `terminal_status` helper는 양방향 잠겨 있고 main() exit 0은 잠겨 있으나, main()이 `attempted != written`일 때 exit 1을 반환하는 wiring은 커밋된 테스트가 직접 거치지 않는다(실제로 exit 1 반환함은 adversarial로 확인). fake가 `records_attempted != records_written`을 반환하는 main() 테스트를 추가하면 public exit-code 계약이 완전히 잠긴다.
- **실제 Mongo runtime**: `run_rebuild`/`_core_sot_from_mongo`/`MongoCoreSotRepository.from_uri`는 자동화 테스트가 없다(live Mongo 필요). 프로젝트의 skip-aware 통합 테스트 패턴과 일관되고, `from_uri` 시그니처와 no-uri ValueError는 확인했다. HANDOFF/SoT가 persistent vector backend를 후속으로 미뤘으므로 이 slice 범위에서 수용. live-Mongo smoke(예: `phase2a_deployed_e2e_smoke` 패턴)가 자연 후속.
- **missing-uri 테스트의 seam**: `test_main_reports_missing_mongo_uri_as_usage_error`는 실제 `run_rebuild`가 아닌 같은 메시지를 던지는 fake를 쓴다. 실제 no-uri 경로가 동일 메시지·exit 2를 냄은 별도 실행으로 확인했으므로 seam은 충실(faithful)하지만, 테스트가 실제 경로를 실행하는 것은 아니다.

### O3 — DEFAULT db 이름 literal 중복(trivial, DRY)

`script:22 DEFAULT_MONGO_DB = "ai_writing_system"`이 `mongo_repository.DEFAULT_DB_NAME` import 대신 hardcode다. 현재 값 일치. canonical 기본값이 바뀌면 CLI 복사본이 따라가지 못한다. `--help`를 가볍게 유지하려는 의도라면 합리적이므로 필수는 아니다.

## Verdict

**합격(pass).**

이유:

- 블로킹 이슈가 없다. JSON summary 8개 field가 SoT v1.6.22와 정확히 일치하고, CLI가 의존하는 indexing domain(`IndexSyncResult.request.{project_id,snapshot_id,target.value}`)이 직전 commit의 committed contract와 일치하며, `MongoCoreSotRepository.from_uri` 시그니처와 canonical db 이름이 맞다.
- public CLI 표면이 대부분 테스트로 pin돼 있다(summary field, exit 0, exit 2, `--help`, terminal_status 양방향). bad input(NotFound)이 `CoreSotError → ValueError` 계층으로 인해 exit 2로 정상 degrade함을 입증했다.
- 작업자 주장 카운트(5/38/371+37)와 `git diff --check`가 정확히 재현됐다.
- 선행 — 이전 검증의 블로킹 F1/F2가 직전 commit(6d4d689, SoT v1.6.21)에서 정상 폐쇄됐음을 확인했다.

O1(exit code SoT 보강 권장)·O2(exit-1·Mongo runtime coverage)·O3(db 이름 DRY)는 모두 비블로킹이며, slice의 fake-adapter/admin-script 성격과 후속 handoff(persistent backend, live smoke)를 고려하면 합격을 막지 않는다. O1은 권장, O2는 자연 후속 coverage, O3은 trivial.

## Outstanding items

- 작업 트리에 uncommitted(오너 커밋 승인 전). 본 검증은 working tree 기준.
- 권장(비블로킹): 커밋 전에 (a) SoT v1.6.22에 exit code 표 추가, (b) `main()` exit-1 회귀 추가, (c) `DEFAULT_DB_NAME` import로 DRY. 어느 것도 합격 판정을 바꾸지 않는다.
- 후속 slice 후보(이미 HANDOFF/SoT에 반영): persistent vector backend, Application HTTP API endpoint, live-Mongo smoke.

## Reproduction

```bash
# 카운트 재현(작업자 주장과 동일)
python3 -m unittest tests.test_phase3a_rebuild_source_block_index_script                # 5
python3 -m unittest tests.test_phase3a_rebuild_source_block_index_script \
    tests.test_indexing_phase3a tests.test_core_sot                                    # 38
python3 -m unittest discover tests                                                     # 371, skipped=37
git diff --check                                                                       # clean

# 실제 no-uri / partial-write / NotFound 경로 adversarial 확인
python3 -c "
import io, os; os.environ.pop('CORE_SOT_MONGO_URI', None)
from scripts.phase3a_rebuild_source_block_index import run_rebuild, parse_args, main, rebuild_source_block_index
from services.application.app.core_sot.service import CoreSotService, InMemoryCoreSotRepository, NotFound
# 1) real run_rebuild, no uri -> ValueError -> main exit 2
try: run_rebuild(parse_args(['--project-id','p','--snapshot-id','s']))
except ValueError as e: print('no-uri:', e)
print('main exit(no uri):', main(['--project-id','p','--snapshot-id','s'], stderr=io.StringIO()))
# 2) partial write -> main exit 1
print('main exit(partial):', main(['--project-id','p','--snapshot-id','s'],
      run_rebuild_fn=lambda a:{'records_attempted':3,'records_written':1}, stdout=io.StringIO()))
# 3) bad snapshot -> NotFound(ValueError subclass) -> exit 2
cs=CoreSotService(InMemoryCoreSotRepository()); p=cs.create_project(name='N')
try: rebuild_source_block_index(core_sot=cs, project_id=p.id, snapshot_id='nope')
except NotFound as e: print('bad snapshot:', type(e).__name__, 'is ValueError:', isinstance(e,ValueError))
"

# F2 폐쇄 확인(직전 commit): draft-only archive 회귀 존재
grep -n "archive_draft\|def test_archived_draft_records_are_filtered_without_project_archive" tests/test_indexing_phase3a.py
```
