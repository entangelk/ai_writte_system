# Phase 3A Source-Block Stale Validation 독립 검증

## Subject metadata

- 검증일: `2026-07-02`
- 요청자: 프로젝트 오너("다음작업 검증해줘. 커밋했고 다음 작업도 한 slice 진행해서 커밋했습니다 … Phase 3A source-block index hit stale validation 추가")
- 검증자: 독립 검증 AI (Claude)
- 검증 대상: Phase 3A 후속 slice(commit `3bce5d8`) — `SourceBlockIndexingService.validate_source_block_record(record)` + `IndexStaleReason`(6 literal) + `IndexRecordValidation` + `tests/test_indexing_phase3a.py` 5개 신규 회귀 + SoT v1.6.24 갱신
- 정합 스펙 기준:
  - `docs/system-contract-sot.md` v1.6.24(변경 이력 행 + Phase 3 Indexing 단락 신규 bullet)
  - `docs/plans/03-indexing-kickoff-decisions.md` §구현 후속 — source-block stale validation
  - `docs/plans/03-indexing.md` 2026-07-02 slice 노트의 validate 문장 + archive 단락 후행 문장
  - 교차 계약: 직전 slice `IndexPointer`(`project_id`, collection/document id, version id, content hash), Phase 1 archive-only 정본 보존 정책(hard delete 없음)
- 검증 대상 작업 출처: commit `3bce5d8`(HEAD). 동시에 직전 commit `ed35ca8`(deployed rebuild smoke)이 본 검증자의 직전 조건부 합격 사유를 폐쇄했는지도 함께 확인한다.
- worktree 상태: clean(`git status --short` 공백, `git diff --check` clean).

## Scope

정합 스펙 스코프를 (1) SoT v1.6.24 changelog 행 + Phase 3 bullet, (2) kickoff 브리프 §구현 후속 — source-block stale validation, (3) `03-indexing.md` slice 노트 validate 문장로 좁혔다. validator가 재조회하는 Core SOT 계약(get_snapshot/get_project/get_draft, snapshot content_hash/draft_id/blocks)은 직전 slice의 committed 상태를 기준으로 삼았다.

검증 surface:

1. 정합 계약(SoT v1.6.24 + 브리프 + slice 노트) 내부 정합성 + 6 reason literal 일치
2. 구현 코드: `validate_source_block_record`(`service.py:183-219`), `IndexStaleReason`(`models.py:16-22`), `IndexRecordValidation`(`models.py:63-67`)
3. boundary matrix: 6 reason "should fire" + fresh "should NOT fire" 전 분기 추적 + reason 조합/배타语义
4. 회귀 테스트: `tests/test_indexing_phase3a.py` 5개 신규 validate 회귀 — 양방향 guard, 단독 실패 인자
5. scope discipline: validator가 query/Context Gate에 조기 wiring됐는지, automatic sync/outbox를 건드렸는지
6. 작업자 주장 카운트(11 / 75 / 388) 재현 + worktree/diff hygiene
7. 직전 조건부 합격(`phase3a_deployed_rebuild_smoke.md`) 폐쇄 여부

## Methodology

정합 스펙을 읽어 boundary matrix를 구성한 뒤 코드/테스트에 추적. 작업자 주장을 복사하지 않고 재실행·재도출. 카운트는 실제 discover로 입증.

실행한 명령:

- `git status --short`, `git diff --check`, `git diff --check HEAD~2..HEAD`, `git show --stat 3bce5d8`
- `git show 3bce5d8 -- <file>`로 SoT/plans/HANDOFF/CHANGELOG/work_log 각 diff 열독
- `Read`로 `tests/test_indexing_phase3a.py`·`tests/test_phase3a_deployed_rebuild_smoke_script.py` 전량 열독; serena symbolic로 `validate_source_block_record`·`IndexStaleReason`·`IndexRecordValidation`·`terminal_status` 본체 확보
- `grep -rn "validate_source_block_record" services/ scripts/`(scope discipline — 호출자 탐지)
- `git show <commit>:tests/test_indexing_phase3a.py | grep -c def test_`로 커밋별 테스트 수 추적(delta 리콩실)
- `python3 -m unittest tests.test_indexing_phase3a`(11), `+ deployed_smoke + cli_rebuild + application_api`(75), `python3 -m unittest discover tests`(388/37) 재실행
- `python3 -m unittest tests.test_phase3a_deployed_rebuild_smoke_script -v`(8)로 직전 조건부 사유 폐쇄 확인

## Findings

### 1. 정합 계약 내부 정합성 + 6 reason literal

- SoT v1.6.24 changelog 행·Phase 3 bullet이 나열하는 6 literal(`project_archived`, `draft_archived`, `snapshot_missing`, `draft_mismatch`, `content_hash_mismatch`, `block_missing`)은 `IndexStaleReason`(`models.py:16-22`)의 6 enum value와 **문자열까지 완전 일치**. kickoff 브리프·slice 노트도 동일 6 literal. 계약 내부 충돌 없음.
- 계약이 명시하는 "이 검증은 automatic sync가 아니라 query/Context Gate 계층이 hit 사용 전 호출하는 explicit guard"를 코드가 충족한다(아래 surface 5).

### 2. 구현 코드 — validate_source_block_record / models

- `validate_source_block_record`(`service.py:183-219`)는 `self._core_sot.get_snapshot(...)`로 정본을 재조회한다. `NotFound` 시 `IndexRecordValidation(usable=False, stale_reasons=(SNAPSHOT_MISSING,))`로 **early return**(단독). 이후 `get_project`/`get_draft`(snapshot의 `draft_id`로) 조회 뒤 project/draft archived, `record.draft_id != snapshot.draft_id`, `record.pointer.content_hash != snapshot.content_hash`, `record.block_id not in {block.id}`를 각기 검사해 `reasons`에 append. 최종 `usable = not reasons`, `stale_reasons = tuple(reasons)`.
- "Core SOT 재조회" 주장 확인: validator는 record 자체 metadata가 아니라 live Core SOT 상태를 읽는다. 회귀(test 8/9)가 rebuild **후** archive를 걸고 validate가 이를 검출하는 것으로 재조회 semantics를 입증한다.
- `IndexRecordValidation`(`models.py:63-67`): `record_id: str`, `usable: bool`, `stale_reasons: tuple[IndexStaleReason, ...]`. frozen/slots dataclass. tuple 타입이 복수 reason 반환을 허용한다.

### 3. boundary matrix — stale 분기 추적 (전 분기 잠금, 빈 cell 없음)

| 분기 | 기대 | 추적 테스트 | 단독 실패 인자 | 상태 |
|---|---|---|---|---|
| fresh live record → usable=True, `()` | should NOT fire stale | `test_validate_source_block_record_accepts_current_live_record`(`assertIsTrue(usable)`, `assertEqual(stale_reasons, ())`) | over-strict | ✅ |
| `project_archived` | fire | `test_..._detects_archive_after_rebuild`(exact `(PROJECT_ARCHIVED,)`) | 단독 | ✅ |
| `draft_archived` | fire | `test_..._detects_draft_archive_after_rebuild`(exact `(DRAFT_ARCHIVED,)`) | 단독 | ✅ |
| `snapshot_missing`(early return, 배타) | fire | `test_..._detects_missing_snapshot`(exact `(SNAPSHOT_MISSING,)`) | 단독 | ✅ |
| `draft_mismatch` | fire | `test_..._detects_pointer_drift`(exact 3-tuple) | exact-tuple로 단독 pin | ✅ |
| `content_hash_mismatch` | fire | `test_..._detects_pointer_drift`(exact 3-tuple) | exact-tuple로 단독 pin | ✅ |
| `block_missing` | fire | `test_..._detects_pointer_drift`(exact 3-tuple) | exact-tuple로 단독 pin | ✅ |

- 양방향 guard 확인:
  - **under-strict**(bug 재발): 각 reason check를 제거하면 대응 테스트의 exact-tuple 단정이 깨진다. 예컨대 `draft_mismatch` check 제거 시 pointer_drift 테스트 기대 tuple `(DRAFT_MISMATCH, CONTENT_HASH_MISMATCH, BLOCK_MISSING)`가 실제 `(CONTENT_HASH_MISMATCH, BLOCK_MISSING)`이 돼 fail. 6 reason 전부 동일.
  - **over-strict**(정상 case 오flag): fresh 테스트가 live record에서 `usable=True`/`reasons=()`을 단정해, check가 정상 hit를 잘못 stale화하면 fail.
- 조합语义: pointer_drift 테스트가 한 record에 3 reason을 동시 발생시켜 복수 reason 반환(`tuple`)을 잠근다. `snapshot_missing`은 early return으로 배타(단독)임도 exact `(SNAPSHOT_MISSING,)` 단정으로 pin.

### 4. 회귀 테스트 — 양방향 guard 품질

- 5개 신규 validate 회귀 + 기존 6개 = 11개. fresh(over-strict) 1 + 단독 reason 3(project/draft/snapshot) + 다중 reason 1(draft/hash/block 동시). boundary matrix에 빈 cell 없음.
- 직전 slice(deployed smoke) 대비 대조: 직전은 partial-write 분기 2개가 untraced(조건부 합격)였으나, 본 slice는 모든 should-fire / should-NOT-fire 분기를 단독 또는 exact-tuple로 잠갔다. 테스트 품질이 한 단계 높다.

### 5. scope discipline — 조기 wiring / automatic sync 미건드림 확인

- `grep -rn "validate_source_block_record" services/ scripts/`(test 제외) 결과 = `service.py:184` 정의 **1건만**. query endpoint, Context Gate, analysis 어디에도 호출자가 없다. → validator는 순수 helper로만 추가됐고, query/Context Gate wiring이나 automatic sync/outbox는 건드리지 않았다. 계약("guard로만 열었다")과 일치. CLAUDE.md §3(surgical) 충족.
- `services/application/app/indexing/models.py`(+16), `service.py`(+42) 외에 application runtime 코드(main.py 등) 변경 없음(`git show --stat 3bce5d8` 확인).

### 6. 작업자 주장 카운트 재현 + hygiene

| 항목 | 작업자 주장 | 재실행 결과 | 일치 |
|---|---|---|---|
| focused `test_indexing_phase3a` | 11 통과 | `Ran 11 tests` OK | ✅ |
| 관련 묶음(4 module) | 75 통과 | `Ran 75 tests` OK | ✅ |
| 전체 discover | 388 / 37 skip | `Ran 388 tests` OK (skipped=37) | ✅ |
| worktree clean | clean | `git status --short` 공백 | ✅ |
| `git diff --check` | 통과 | clean | ✅ |

- 카운트 delta 리콩실(본 검증자 턴-1 381 → 현재 388의 +7): deployed smoke 테스트 6→8(+2, 직전 조건부 사유 폐쇄 분기 회귀) + `test_indexing_phase3a` 6→11(+5, validate 회귀) = +7. 381 + 7 = 388. 정합. (본 검증자 턴-1 산술 예상 386은 deployed smoke가 6→8로 자란 것을 누락한 것으로, 작업자 주장 388이 정확하다.)

### 7. 직전 조건부 합격(`phase3a_deployed_rebuild_smoke.md`) 폐쇄 확인

- 본 검증자 직전 판정의 조건이었던 "smoke `terminal_status` partial-write 분기 2개 untraced"가 commit `ed35ca8`에서 **단독 회귀 2건 추가로 폐쇄**됐음을 확인.
  - `test_terminal_status_rejects_http_partial_without_cli`(`tests/...:115-125`): http `records_written=1`, cli 없음 → `http_complete=False`가 **단독** 실패 인자. `http_complete` check 제거 시 True 반환 → `assertFalse` fail. **Gap 1 폐쇄**.
  - `test_terminal_status_rejects_cli_partial_even_when_summaries_match`(`tests/...:127-137`): http 완전, cli `records_written=1`, `summaries_match=True` → `cli_complete=False`가 **단독** 실패 인자. `cli_complete` check 제거 시 True 반환 → `assertFalse` fail. **Gap 2 폐쇄**.
- `terminal_status` 본체는 불변(http_complete + cli_complete + summaries_match 그대로). 폐쇄는 코드 변경이 아니라 테스트 추가로 이뤄졌다. deployed smoke 모듈 8개 전부 통과 확인.

## Issues / Risks

1. **(비블로킹, 계약 under-specification)** `snapshot_missing`이 early return으로 다른 reason과 **배타**(단독)다. SoT는 6 literal을 나열하나 조합/배타 semantic을 명시하지 않는다. 단, snapshot이 없으면 draft_id/blocks/content_hash를 조회할 수 없어 early return이 **유일한 정합 구현**이므로 진성 gap은 아니다. SoT가 한 줄로 "snapshot_missing은 다른 check를 short-circuit한다"를 명시해도 좋다.
2. **(비블로킹, semantic 메모)** `draft_archived` 판정이 record의 stale draft_id가 아니라 **snapshot의 현재 draft** 기준이다. `draft_mismatch`가 동시에 fire하므로 실사용에 영향은 없으나, spec-silent한 선택이다.
3. **(비블로킹)** validator가 `version_id`가 아니라 `content_hash`(snapshot-level)로 drift를 잰다. content_hash가 canonical drift signal이므로 semantic상 더 정확하고 pointer 계약과 일치하지만, SoT가 "version mismatch/stale"을 언급하는 점과 대비해 "content_hash 기준"임이 명시되면 더 명확하다.
4. **(비블로킹, 불가능 시나리오)** `get_project`/`get_draft`의 `NotFound`가 uncaught다. 단 Phase 1 정본은 archive-only(hard delete 없음)이므로 project/draft가 존재하지 않는 경로는 현 계약상 불가능. CLAUDE.md §2(불가능 시나리오 error handling 생략)와 양립.

## Verdict

**합격.**

하중 이유:
- 정합 계약(SoT v1.6.24 + 브리프 + slice 노트)의 6 reason literal이 `IndexStaleReason` enum과 문자열까지 완전 일치. 계약 내부 충돌 없음.
- boundary matrix에 빈 cell 없음: 6 reason "should fire" 전 분기 + fresh "should NOT fire"가 모두 추적됐고, 각각 단독 또는 exact-tuple로 단독 실패 인자로 pin(under-strict), fresh로 over-strict guard 확보. 다중 reason 조합과 snapshot_missing 배타 semantic까지 pin.
- "Core SOT 재조회" 주장을 회귀(rebuild 후 archive → validate 검출)로 입증.
- scope discipline: validator는 순수 helper만 추가, query/Context Gate 조기 wiring·automatic sync/outbox 미건드림. 계약("guard로만")과 일치.
- 작업자 카운트 11 / 75 / 388 전부 재현, worktree clean, `git diff --check` clean.
- 부수: 본 검증자 직전 조건부 합격(deployed smoke partial-write 분기 2개)이 단독 회귀 2건 추가로 **폐쇄**됨을 확인. 직전 판정은 이제 full 합격으로 승격 가능.

이슈 1~4는 모두 비블로킹(under-specification / semantic 메모 / 불가능 시나리오)이며 판정에 영향 없음.

## Outstanding items

- 작업은 commit `3bce5d8`(HEAD)로 반영됐고 worktree는 clean. 게시(push)는 오너 결정.
- validator는 아직 query/Context Gate에 wiring되지 않았다(의도적). wiring은 별도 slice이며, 그 시점에 본 guard의 호출 계약이 회귀로 추가돼야 한다.
- 후보(미확정): persistent Chroma-like adapter, archive 후 automatic sync/outbox 이벤트(HANDOFF Next Tasks).
- 직전 검증 기록 `phase3a_deployed_rebuild_smoke.md`의 조건부 사유가 폐쇄됐으므로 동 기록에 폐쇄 addendum을 추가했다(아래 Note).

## Note — 직전 검증 기록 폐쇄 addendum

본 검증에서 `docs/verifications/2026-07-02/phase3a_deployed_rebuild_smoke.md`의 조건부 합격 사유(smoke `terminal_status` partial-write 분기 2개 untraced)가 commit `ed35ca8`의 단독 회귀 2건으로 폐쇄됨을 확인했고, 동 기록 Verdict/Outstanding에 폐쇄 addendum을 기록했다. 직전 판정은 이제 full 합격으로 승격된다.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
git status --short                                  # clean
git diff --check                                    # clean
git show --stat 3bce5d8                             # models.py/service.py/test_indexing_phase3a.py + 4 doc

python3 -m unittest tests.test_indexing_phase3a                                              # 11
python3 -m unittest tests.test_phase3a_deployed_rebuild_smoke_script \
                       tests.test_phase3a_rebuild_source_block_index_script \
                       tests.test_application_api tests.test_indexing_phase3a                 # 75
python3 -m unittest discover tests                                                           # 388 / 37 skip
python3 -m unittest tests.test_phase3a_deployed_rebuild_smoke_script -v                      # 8 (직전 폐쇄 확인)

# scope discipline
grep -rn "validate_source_block_record" services/ scripts/ | grep -v test_                   # service.py 정의 1건만
```
