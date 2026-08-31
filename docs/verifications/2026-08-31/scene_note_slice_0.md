# 장면 메모 Slice 0(저장·파기 수명) 독립 검증

## Subject metadata

- 날짜: 2026-08-31
- 요청자: 오너("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래")
- 검증자: Claude Code 세션(구현자와 다른 세션 — 구현은 Claude Opus 5 커밋 `cab1a7d`~`1458894`)
- 대상: 장면 메모 Slice 0 — `SceneNote` 모델·service/repository·in-memory/Mongo 어댑터·`scene_notes` 인덱스·Scene/Chapter/project 파기 연결. HTTP·프론트·활동 기록은 범위 밖
- 정본: `docs/system-contract-sot.md` **v1.8.11**(변경이력 행 + Phase 1 "장면 메모" 조항), `docs/plans/scene-note-decisions.md`(D1=C+A·D2=A·D3=A·D4=A + 본문 상한 12000자, 오너 2026-08-31), `docs/plans/scene-note-implementation-phases.md` Slice 0
- 검증 소스: 커밋 `cab1a7d`(구현)·`7a63d7a`(파기 가드 보강)·`257ce23`(정본·기록)·`1458894`(실측 기록), HEAD `1458894`, 트리 clean
- 환경: WSL2, 저장소 루트에서 `PYTHONPATH=.` pytest, test-mongo = `docker compose -f docker-compose.test.yml`(rs-test, `127.0.0.1:27020`, 컨테이너 healthy). `.env` 무관(URI 기본값 27020)

## Scope

1. ★정본 계약 대비 구현(경계 행렬: 발생해야 할 분기·발생하지 말아야 할 분기·리터럴 전량)
2. 파기 3축 연결(in-memory·Mongo)과 "조용한 고아" 가시성 — 구현자가 스스로 보고한 결함(M1)의 진위
3. 회귀 셀의 실채움(test code is part of the audit subject)
4. 문서 동기화(SoT v1.8.11·README ④칸·파기 로스터 가드·`execute_project_purge` docstring·reconciler 자동 포함 주장)
5. 구현자 변이표(M1~M7·MM1~MM3)의 대표 재검증 + **독자 변이 5종**(구현자가 안 덮은 방향)
6. 전수 회귀(test-mongo ON) 수치 재현

## Methodology

- 경계 행렬은 SoT v1.8.11 조항 문언에서 먼저 세운 뒤 코드를 읽어 대응시켰다(계약→코드, 코드→계약 아님).
- 변이 프로토콜: 사전 `git status --short` empty 확인 → 변이 적용 → 집중 셀 실행(요약 행 읽기, `grep FAILED` 아님) → `git checkout -- <path>` 복원 → `git status --short` 재확인. 매번 실시.
- 전수: `PYTHONPATH=. pytest -q`(32분 41초). 신규 셀 수는 `--collect-only`로 직접 계산.
- 참조 지점 전수: `grep -rn "scene_notes\|SceneNote\|SCENE_NOTE" services/ scripts/` — core_sot 외 참조 0건 확인.

## Findings

### 1. 경계 행렬 — 계약 조항 ↔ 셀 대응 (빈 칸 없음)

| SoT v1.8.11 조항 | 구현 | 잠금 셀 | 변이 증명 |
|---|---|---|---|
| 정체성 `(project_id, draft_id)`, Scene당 1건 | `service.py:135-136`(in-memory dict), `mongo_repository.py:147-151`(unique `uniq_scene_note`) | `test_notes_are_per_scene_within_one_project`, `test_scene_note_upsert_round_trips_and_keeps_one_row_per_scene`(count==1) | V4(unique→non-unique): **2셀** |
| 행 모양 `{project_id, draft_id, body, updated_at}` | `models.py:93-110`, `mongo_repository.py:876-884` | upsert round-trip 셀 | — |
| 명시적 저장 = 값 통째 교체(버전 없음) | `service.py:1365-1374`, `mongo_repository.py:532-538`(replace_one upsert) | `test_second_put_replaces_the_body_and_advances_updated_at` | V2(setdefault 보존): **2셀** |
| 빈 본문 = 빈 현재값(삭제 아님) | `put_scene_note`에 빈 본문 특례 없음 | `test_empty_body_is_stored_as_an_empty_current_value_not_a_deletion` | V2·구현자 M5 |
| 상한 `SCENE_NOTE_MAX_CHARS = 12000` | `service.py:101`, 검사 `service.py:1354`(초과 시 `SceneNoteTooLong`) | 경계값 2셀(정확히 12000 허용=over-strict / 12001 거절+현재값 보존) | 구현자 M3(`>=`)·M4(검사 삭제) |
| 읽기는 archive 무관 | `get_scene_note` = `_require_project`+`_require_draft`(`service.py:1382-1392`, 둘 다 archive 무검사) | `test_archived_scene_keeps_the_note_readable_but_blocks_writes` | 구현자 M7(읽기를 active 전환) |
| 쓰기는 원고 저장과 같은 축(project/draft/chapter 3축 거절) | `put_scene_note` → `_require_active_project_and_draft`(`service.py:1400-1410`, `save_draft` `service.py:1104`와 동일 헬퍼) | archive 2셀(scene 읽기/쓰기 + chapter·project 쓰기) | 구현자 M6 |
| 파기 고아 0 — Scene/Chapter(project) 3축 | in-memory `service.py:309`·`246-255`·`320-330`(chapter는 purge_draft 경유), Mongo `mongo_repository.py:287-289`·`223`·`253-254` | in-memory 4셀 + Mongo 3셀 ×3경로 | M1 재실행 **2셀**, V1(과잉 파기) **2셀**, V5(Mongo 과잉 파기) **1셀**, 구현자 M2·MM1·MM2 |
| D2=A 격리(원고·export·프롬프트 무관) | 참조 지점 전수 grep: `scene_notes`는 core_sot 4파일 + `routers/admin.py:92` docstring에만 존재. export/프롬프트/활동 경로 0접촉 | 구조적 성립 + `test_docs_indexes` | — |
| reconciler 자동 포함 | `scripts/purge_reconciler.py:49-58` — 컬렉션 목록 하드코딩 없이 DB에서 `project_id` 필드 실사용으로 발견. `_scene_note_doc`이 항상 `project_id` 기록 | 구조적 성립(동적 발견 + round-trip 셀) | — |

### 2. 구현자 보고 결함(M1)의 진위 — 사실로 확인

구현자는 "초기 파기 가드가 `service.get_scene_note`로 부재를 단정해, in-memory `purge_draft`에서 메모 삭제를 지워도 0셀이 깨졌다"고 보고하고 `repo.scene_notes` 직접 단정으로 고쳤다(커밋 `7a63d7a`). 검증자가 동일 변이(pop 라인 삭제)를 재적용한 결과 **정확히 2셀 재실패**(`test_scene_purge_removes_its_note_and_keeps_the_sibling_scene_note`·`test_chapter_purge_cascades_to_child_scene_notes_only`) — 보고된 결함과 수습이 모두 실재한다. 근거 진술(`_require_draft`가 메모 행 생사와 무관하게 NotFound — `service.py:1388-1392`)도 코드와 일치.

패턴 sweep 주장("기존 파기 회귀에 같은 뿌리 재발 0건")도 반박 시도했으나 뒷받침된다: `test_core_sot.py:546-552`는 `repo.projects/drafts/versions/snapshots` 직접 단정, `test_draft_purge.py:137`은 `repo.version_count`(부모 불필요 키), 동일 파일:180의 `get_writing_accept_receipt`는 `(project_id, idempotency_key)` 키로 부모 draft를 요구하지 않는다(`service.py:1155-1159`는 repo 패스스루) — 서비스 조회라도 고아를 가리지 않는 구조.

### 3. 회귀 셀 실채움

- 신규 셀 **33개 실측**(`--collect-only`): `test_scene_notes.py` 15 + `_MongoContractMixin` 6셀 × 3 서브클래스(Fallback·Transaction·WritingIntent) 18. 주장과 일치.
- Mongo 셀은 매 테스트 uuid db(`test_core_sot_mongo.py:136-149` + tearDown drop)에서 실행 — 인덱스/잔류 오염 없음.
- 유일성은 2층: fake 인덱스 가드가 `("unique": True, "name": "uniq_scene_note")` kwargs를 정확히 단정(`test_core_sot_mongo_indexes.py:148-157`)하고, 실제 Mongo에서 중복 insert가 `PyMongoError`(DuplicateKeyError)로 거부되는 행위 셀이 별도(`test_unique_index_blocks_a_second_note_row_for_one_scene`).
- 문서 가드: `tests/test_docs_indexes.py` 포함 13 passed / 272 subtests(README ↔ SoT v1.8.11 일치), 파기 로스터 가드 2셀 green(9계약 — core_sot 내부 합류는 컬렉션 수 변화이므로 로스터 불변, docstring 수치 갱신은 `test_purge_project_coverage.py:8-9`에 반영).

### 4. 검증자 독자 변이 5종 + M1 재검증 (전부 물림, 전부 복원 후 tree clean)

| # | 방향 | 적용 diff | 물린 셀 |
|---|---|---|---|
| V1 | **over(과잉 파기)** in-memory `purge_draft`의 `scene_notes.pop((project_id, draft_id))` → 프로젝트 전체 wipe comprehension | `SceneNotePurgeTest::test_scene_purge_removes_its_note_and_keeps_the_sibling_scene_note`·`::test_chapter_purge_cascades_to_child_scene_notes_only` (2 failed) |
| V2 | **over(교체→보존)** in-memory `put_scene_note` dict 대입 → `setdefault` | `SceneNoteStorageTest::test_second_put_replaces_the_body_and_advances_updated_at`·`::test_empty_body_is_stored_as_an_empty_current_value_not_a_deletion` (2 failed) |
| V3 | **under(타임존)** Mongo `_to_scene_note`의 `_aware(doc["updated_at"])` → 원값 통과 | `FallbackMongoTest::test_scene_note_upsert_round_trips_and_keeps_one_row_per_scene` (1 failed, tzinfo 단정) |
| V4 | **under(유일성 플래그)** `uniq_scene_note` 생성의 `unique=True` → `False` | `MongoIndexSetupTests::test_ensure_indexes_creates_required_absent_indexes`(kwargs 불일치) + `FallbackMongoTest::test_unique_index_blocks_a_second_note_row_for_one_scene`(insert 성공) (2 failed) |
| V5 | **over(Mongo 과잉 파기)** `_purge_draft`의 scene_notes delete에서 `draft_id` 필터 제거 | `FallbackMongoTest::test_scene_purge_removes_the_note_and_keeps_the_sibling_note` (1 failed) |
| M1 재실행 | under(구현자 표의 사후 재현) | in-memory `purge_draft` pop 라인 삭제 | 구현자 보고와 동일 2셀 |

구현자의 M1~M7·MM1~MM3 10종은 under(삭제·부재)·over(경계 과잉)를 폭넓게 덮으나 **"너무 많이 지우는" 방향(형제 보존 단정이 실제로 물리는지)은 본 검증의 V1·V5가 처음 증명**했다.

### 5. 전수 재현

`PYTHONPATH=. pytest -q`: **2610 passed / 1 skipped / 3024 subtests, 32:41, exit 0** — 구현자 보고(2610/1/3024, 32:55)와 수치·규모 정확히 일치. 1 skipped의 개별 정체는 `-rs` 미사용으로 특정하지 않았다(카운트만 재현).

## Issues / Risks

### Blocking (contract obligations)

**없음.** 경계 행렬의 모든 계약 요구 분기(should-fire / should-NOT-fire)는 명명된 셀에 대응하고, 16종 변이(구현자 10 + 검증자 5 + M1 재검증) 전부 대상 셀을 물었다.

### Hardening recommendations (non-blocking)

1. **읽기-아카이브 축의 파라미터화**: "읽기는 archive를 막지 않는다"가 직접 셀로 잠긴 것은 scene(=draft) 보관뿐이다. project·chapter 보관 상태의 읽기는 직접 셀이 없다. 현 구조에서 읽기 경로(`_require_project`+`_require_draft`)는 chapter를 아예 안 보고 project 보관도 안 보므로 실질 회귀 경로는 헬퍼 치환(구현자 M7로 입증)뿐이지만, 1줄 짜리 셀(`test_archived_project_and_chapter_do_not_block_reads`)로 명시적 잠금 권장.
2. **검사 순서 선언(Slice 2 선결과)**: `put_scene_note`는 길이 검사를 `_require_active_project_and_draft`보다 먼저 한다(`service.py:1354` → `:1359`). 보관된 장면에 12000자 초과 본문을 보내면 `Archived`가 아니라 `SceneNoteTooLong`이 먼저 난다. 현재 정본은 순서를 못박지 않았지만 HTTP 상태 매핑(409 vs 413/422)이 생기는 Slice 2 전에 오너가 우선순위를 정해 조항에 남기는 것이 좋다.
3. **HANDOFF 용량 산정의 부호 단위**: "장면 200개 = 최악 2.4MB"는 1바이트/문자 가정이다. 한국어 UTF-8은 3바이트/문자라 최악 ≈ **7.2MB**(JSON 이스케이프 추가). 미리보기 절단의 결론은 변하지 않지만 Slice 1 설계 근거로는 문자수 또는 바이트 계산을 명시하는 편이 안전하다.
4. **work_log 인용 오류**: `daily_logs/2026-08-31/work_log.md:47` "커밋 `ae2fc9d` 계열" — **존재하지 않는 해시**다(`git cat-file -t ae2fc9d` 실패). 실제 가드 보강 커밋은 `7a63d7a`. 1줄 정정 권장.
5. **SoT v1.8.11 행의 회귀 기술 과소**: "Mongo 6셀 × transaction/fallback **양 경로**" — 실제는 **3 실행 경로**(Fallback·Transaction·WritingIntent, collect-only 18셀)다. 커버리지를 과소 기술한 것이므로 경계는 안전하나, 다음 SoT 갱신 시 3경로로 정정 권장.
6. (구현자가 이미 Issues #2로 기록) `mongo_collections.md` 미등재 부채 — `chapters`·`writing_drafts_scratch`에 이어 `scene_notes`도 빠진다. ideation 상태 문서라 이 slice에서 안 건드린 판단은 타당. 정리는 별도 작업으로.

## Verdict

**합격**

- 경계 행렬에 빈 칸이 없고, 양방향(under·over) 변이 16종 전부 대상 셀을 물었으며, 그중 구현자가 안 덮은 과잉 파기·유일성 플래그·타임존 방향을 검증자 독자 변이가 보완했다.
- 구현자가 스스로 보고한 가드 결함(M1)과 수습이 실재함을 재현으로 확인했다(동일 변이 → 동일 2셀).
- 전수 수치(2610/1/3024)가 독립 재실행으로 재현됐다.
- 정본 v1.8.11의 계약 문언·리터럴(12000·`uniq_scene_note`·행 모양·빈 본문·아카이브 축·파기 3축)이 코드와 어긋나지 않는다.
- 남는 발견은 모두 기록 정합성(hardening 4·5) 또는 후속 slice 선결과(2·3)로, 현 계약 위반이 아니다.

## Outstanding items

- **CHANGELOG.md 미기록**: 장면 메모(저장 계약 변경 + 파기 그래프 18→19)는 가이드 기준 "major feature change"에 가깝지만 기능이 Slice 0/5 중간이고 SoT·work_log·HANDOFF가 최신이다. Slice 완성 시점 일괄 등재 여부는 오너 판단.
- 본 검증의 문서 정정 후보(work_log 해시·SoT 양경로 표기)는 검증자가 임의로 고치지 않았다(가이드: 검증자는 결함을 조용히 고치지 않는다). 오너 승인 시 1줄씩.
- test-mongo 컨테이너(rs-test 27020)이 계속 가동 중이다(검증 전 구현자 세션이 띄운 것).

## Reproduction

```bash
# 환경: 저장소 루트, test-mongo 기동
docker compose -f docker-compose.test.yml up -d

# 집중
PYTHONPATH=. pytest tests/test_scene_notes.py tests/test_core_sot_mongo_indexes.py \
  tests/test_purge_project_coverage.py tests/test_docs_indexes.py -q   # 35 passed / 272 subtests
PYTHONPATH=. pytest "tests/test_core_sot_mongo.py::FallbackMongoTest::test_scene_note_upsert_round_trips_and_keeps_one_row_per_scene" -q

# 셀 수 실측
PYTHONPATH=. pytest tests/test_scene_notes.py --collect-only -q | tail -1        # 15
PYTHONPATH=. pytest tests/test_core_sot_mongo.py --collect-only -q | grep -cE \
  "scene_note_upsert_round_trips|unique_index_blocks_a_second_note_row_for_one_scene|scene_note_is_isolated_across_projects|scene_purge_removes_the_note_and_keeps_the_sibling_note|chapter_purge_cascades_to_child_scene_notes_only|project_purge_removes_scene_notes_and_keeps_other_project"  # 18

# 변이(예: V1) — 사전 git status --short empty 확인 필수
# service.py:309 pop → 프로젝트 전체 wipe 후
PYTHONPATH=. pytest tests/test_scene_notes.py -q   # 2 failed 기대
git checkout -- services/application/app/core_sot/service.py && git status --short  # empty

# 전수
PYTHONPATH=. pytest -q   # 2610 passed / 1 skipped / 3024 subtests, ~33분
```
