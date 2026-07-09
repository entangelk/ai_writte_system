# 검증 기록 — ES-lexical backfill 스크립트 (SoT v1.6.58)

## Subject metadata

- **날짜**: 2026-07-09
- **요청자**: 오너 ("작업 AI가 작업한거 검증하고 의심하고 또 의심해줄래")
- **검증자**: 독립 검증 AI (작업자와 별개 세션)
- **대상 slice/artifact**: (b-6 후속) ES-lexical backfill — `scripts/phase2b5_reindex_memory.py`(memory vector+lexical)·`scripts/phase2b5_reindex_candidate.py`(candidate vector+lexical) + 회귀 2건
- **canonical spec reference**: `docs/system-contract-sot.md` v1.6.58 changelog + `docs/plans/04-es-lexical-backfill-decisions.md`(Resolved, G1=A·G2=A·G3=A·G4=A) + `HANDOFF.md`
- **source of work**: working tree, **uncommitted**(커밋 전). 최근 HEAD = `3ecfa2f`(v1.6.57). 변경: 6 modified + 3 untracked.
- **검증 effort**: max(오너 `/effort max` + "의심하고 또 의심")

## Scope

1. **계약 브리프 경계 매트릭스** — `plans/04-es-lexical-backfill-decisions.md`의 G1~G4 결정·검증계획·한계#1~#3에서 도출한 should-fire / should-NOT-fire 분기 + literal.
2. **구현 코드** — `scripts/phase2b5_reindex_memory.py`(modified)·`scripts/phase2b5_reindex_candidate.py`(untracked).
3. **회귀 테스트** — `tests/test_phase2b5_reindex_memory_script.py`(modified)·`tests/test_phase2b5_reindex_candidate_script.py`(untracked).
4. **helper 존재·시그니처** — 브리프 :18가 "전부 구현됨"이라 인용한 helper들이 1차 소스에서 실존 + 시그니처 일치.
5. **mutation 양방향 4건** — work_log :240가 CAUGHT라 주장한 4건의 독립 재실행.
6. **전체 스위트 카운트** — work_log/HANDOFF가 보고한 704 passed/45 skipped + 3 failed 재현.
7. **ES 환경 의존 실패(3 failed) 인과관계 단절** — 작업자 본문 정정("slice와 무관, 호스트 패키지 부재")의 진실성.
8. **문서 정합** — SoT v1.6.58 changelog·CHANGELOG·HANDOFF 갱신.

## Methodology

경계 매트릭스를 브리프 + changelog에서 먼저 구축한 뒤, 코드·테스트·smoke를 그 매트릭스에 대입. 작업자 주장을 그대로 수용하지 않고 1차 소스에서 재도출.

- `git status`·`git diff --stat`·`git diff --check`(whitespace).
- `git log --oneline`(최근 커밋으로 v1.6.58 미커밋·working tree 상태 확인).
- 1차 소스 직독: 브리프 전문·work_log·구현 2 스크립트·테스트 2건·`memory_lexical_index.py`/`candidate_lexical_index.py`/`candidate_index.py`/`memory_index.py`/`service.py`·`memory/service.py`·`analysis/service.py`·`analysis/models.py`.
- helper 시그니처 grep: 브리프 인용 symbol들이 실존 + 구현 호출부 시그니처 일치 여부.
- **3 failed 인과단절 실험**: `git show HEAD:scripts/phase2b5_reindex_memory.py`로 HEAD 원본 확보 → working tree에 덮어쓰기 → `pytest tests/test_context_search_memory_lexical_retrieval.py::ConnectElasticsearchTest -q` → 복원 → `git diff --stat`으로 원본 복귀 확인.
- ES 패키지 가용성: `python3 -c "import elasticsearch"` + `services/application/requirements.txt` grep.
- **mutation 양방향 4건 독립 재실행**: 각 mutation을 정확 문자열 교체로 적용 → focused pytest(1 failed 기대) → cp 복원 → focused pytest(1 passed 기대). 적용 대상:
  - MUT-1 memory canonical 필터 제거: `canonical = [m for m in memories if m.status is MemoryStatus.CANONICAL]` → `canonical = list(memories)`.
  - MUT-2 memory lexical leg 제거: `lexical_written = lexical_index.index_memory_records(...)` → `lexical_written = 0`.
  - MUT-3 candidate lexical leg 제거: `lexical_written = lexical_index.index_candidate_records(...)` → `lexical_written = 0`.
  - MUT-4 candidate vector leg 제거: `vector_written = vector_index.upsert_candidate_records(...)` → `vector_written = 0`.
- **전체 스위트**: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py`(프로젝트 관례).

## Findings

### 1. 계약 브리프 경계 매트릭스 — 빈 셀 없음

브리프(`plans/04-es-lexical-backfill-decisions.md`)의 성격 선언(:11 "순수 운영 스크립트 + 회귀 — 새 계약 literal 없음, forward-defense stub과 무관")이 핵심. literal 잠금 대상이 아니므로 매트릭스는 **행동 분기** 중심.

should-fire:
- (a) memory ES 구성 시 canonical memory lexical 적재 → memory test `lexical_records_written==1`(`test_phase2b5_reindex_memory_script.py:87`).
- (b) candidate needs_review vector+lexical 적재 → candidate test `vector_records_written==1`/`lexical_records_written==1`(`test_phase2b5_reindex_candidate_script.py:82-83`).
- (c) summary lexical/vector 필드 노출 → 양 test summary assertion.

should-NOT-fire:
- (d) memory superseded 제외(canonical 필터) → `canonical_count==1`(`:85`) + MUT-1로 pin.
- (e) memory/candidate lexical leg 제거 시 0 → `lexical_records_written==1` pin(MUT-2/MUT-3).
- (f) candidate vector leg 제거 시 0 → `vector_records_written==1` pin(MUT-4).
- (g) project 격리 → memory `canonical_count==1`(m3 project-2 배제, `:57-65` seed)·candidate `candidate_count==1`(c2 project-2 배제, `:55-59`).
- (h) candidate needs_review-only → list API 위임(test 주석 `:65-67` 명시).

모든 분기가 회귀 또는 mutation으로 추적됨. **빈 셀 없음.**

### 2. 구현 코드 — worker composite 대칭 정확

- `phase2b5_reindex_memory.py`: `_build_memory_lexical_index`(`:88-109`, ELASTICSEARCH_URL 시 `connect_elasticsearch_memory_index`·아니면 `InMemoryMemoryLexicalIndexAdapter` + `FAKE_VECTOR_BACKEND`) 추가. `run_reindex`(`:142-163`)가 같은 canonical 순회에서 `derive_memory_index_text` 한 번 계산(`:147`)해 vector·lexical 양쪽 재사용 — text 중복 계산 없음. summary를 `vector_backend`/`lexical_backend`/`vector_records_written`/`lexical_records_written`로 개환(`:156-163`). worker `_build_memory_adapter` composite와 자세 대칭.
- `phase2b5_reindex_candidate.py`(신규 189줄): `AnalysisService.list_needs_review_candidates` 전수(`:145`) → `candidate_index_text`+embed → vector+lexical 동시 적재. memory와 동일한 leg/fake/summary 구조.
- canonical 필터는 memory만(`:143` `m.status is MemoryStatus.CANONICAL`). candidate는 list API가 needs_review만 반환하므로 필터 불필요(브리프 :20 사실 일치).

### 3. 회귀 테스트 — assertion이 계약을 pin

memory test `test_reindexes_only_project_canonical`(`:70-87`)는 docstring에 under-strict(d→ 2)/over-strict(e→ 0)/project 격리(g) 양방향을 명시. candidate test 동등(`:64-83`). 둘 다 `mock.patch(_REPO_PATH, return_value=_seeded_repo())`로 Mongo 우회, `os.environ` `clear=True`로 InMemory fake 강제 — sandbox 안 결정성 보장. `main` exit-code map(0/2)도 양쪽 pin.

### 4. helper 존재·시그니처 — 브리프 인용 전부 실존

1차 소스 직독 결과(브리프 :18 인용 대조):
- `build_memory_lexical_record(memory, *, text)`(`memory_lexical_index.py:48`) — 구현 호출 `build_memory_lexical_record(entry, text=text)` 일치.
- `InMemoryMemoryLexicalIndexAdapter.index_memory_records`(`:94`)·`connect_elasticsearch_memory_index`(`:291`)·`MEMORY_LEXICAL_INDEX`(`:28`) — 일치.
- `derive_memory_index_text(memory_type, payload)`(`memory_index.py:41`) — 구현 `:147` 호출 `derive_memory_index_text(entry.memory_type, entry.payload)`, **worker `memory_index.py:194`와 동일 시그니처**(composite 대칭 확증).
- candidate측 `build_candidate_lexical_record`(`candidate_lexical_index.py:62`)·`candidate_index_text`(`candidate_index.py:127`)·`build_candidate_index_record`(`:133`)·`index_candidate_records`(`:96`/`:148`)·`connect_elasticsearch_candidate_index`(`:247`)·`CANDIDATE_LEXICAL_INDEX`(`:30`)·`CANDIDATE_VECTOR_COLLECTION`(`candidate_index.py:41`) — 전부 실존·일치.
- service.py 상수 `FAKE_VECTOR_BACKEND="in_memory_fake"`(`:36`)·`CHROMA_VECTOR_BACKEND`(`:37`)·`ELASTICSEARCH_BACKEND`(`:49`)·`DeterministicFakeEmbeddingProvider`(`:263`) — 일치.

### 5. mutation 양방향 4건 — 전부 CAUGHT 독립 재실증

| MUT | 적용(기대 1 failed) | 복원(기대 1 passed) | 판정 |
|---|---|---|---|
| 1 memory canonical 필터 제거 | `:85 AssertionError` → 1 failed | 1 passed | CAUGHT |
| 2 memory lexical leg 제거 | `:87 AssertionError` → 1 failed | 1 passed | CAUGHT |
| 3 candidate lexical leg 제거 | `:83 AssertionError` → 1 failed | 1 passed | CAUGHT |
| 4 candidate vector leg 제거 | `:82 AssertionError` → 1 failed | 1 passed | CAUGHT |

4건 전부 mutation 시 1 failed / 복원 시 1 passed. work_log :240 "CAUGHT" 주장 재실증. 복원 후 `diff -q`로 두 스크립트 원본 일치 확인.

### 6. 전체 스위트 카운트 — 정확 재현

`pytest -q --ignore=tests/test_memory_mongo.py` → **3 failed, 704 passed, 45 skipped, 99 subtests passed**(11.90s). work_log :248·HANDOFF Verification 보고(704 passed/45 skipped + 3 failed)와 정확 일치. 3 failed는 전부 `ConnectElasticsearchTest::*`.

### 7. 3 failed 인과관계 단절 — 작업자 본문 정정 진실 확증

- 호스트 `python3 -c "import elasticsearch"` → `ModuleNotFoundError: No module named 'elasticsearch'`. 반면 `services/application/requirements.txt:2` = `elasticsearch>=8,<9`(line 1 `chromadb`). → 작업자 "컨테이너 이미지엔 있고 호스트엔 없다" 정정 정확.
- `ConnectElasticsearchTest._connect`(`test_context_search_memory_lexical_retrieval.py:212`)가 `from elasticsearch import Elasticsearch as _real`를 **메서드 본문 내**에서 import — 모듈 수집 단계가 아닌 테스트 실행 시 ModuleNotFoundError. `@skipUnless`/`importorskip` skip guard 부재(b-5 도입).
- slice는 이 파일을 전혀 건드리지 않음(`git status --short tests/test_context_search_memory_lexical_retrieval.py` 빈 출력).
- **HEAD 인과단절 실험**: `git show HEAD:scripts/phase2b5_reindex_memory.py`로 덮어쓴 뒤 동일 3개 failed 재현(동일 `ModuleNotFoundError` at `:212`). working tree 복원 후 `git diff --stat` 원본 일치. → slice 변경과 3 failed의 인과관계 단절 확증.

### 8. 문서 정합 — v1.6.58 일관 갱신

- `system-contract-sot.md`: 헤더 `v1.6.57`→`v1.6.58` + changelog 표 v1.6.58 행 추가(G1~G4=A·accepted limitation #1 해소·mutation 4건·704/45+3 failed 환경 의존 명시). v1.6.57 changelog에 accepted limitation #1 원문("ES-lexical backfill 부재 → G4-B 아래 per-sink-max로 terminal drop된 ES 실패는 수렴 수단 없음")이 존재 → v1.6.58이 닫는 대상이 정확히 정합.
- `CHANGELOG.md`: v1.6.58 행 추가. `HANDOFF.md`: Current Status v1.6.58·Indexing 란 ES-lexical backfill 행·Next Tasks #1(완료로 이동)·Verification(704/45+3 failed + 인과단절 설명) 갱신. 3 failed를 투명하게 기록(숨기지 않음).

## Issues / Risks

1. **[non-blocking, 문서 정정 권장] work_log :240 mutation 분류 어휘 부정확**: "candidate vector leg 제거(under-strict)"라 기술했으나, leg 제거는 **over-strict** 성격(정상 leg를 제거했을 때 assertion이 잡는지). under-strict는 "원 버그(잘못된 동작) 재도입 감지"이며, candidate vector leg는 정상 동작. 단, mutation이 CAUGHT된다는 **본질 주장은 검증됨**(§5). 또한 candidate backfill 자체에는 under-strict guard(비-needs_review 상태 포함 감지)가 없으나 — 이는 `list_needs_review_candidates`에 위임 + `AnalysisCandidateStatus`가 `NEEDS_REVIEW` 단일(`analysis/models.py:26-27`, CONFIRMED/REJECTED는 Phase 6 전 미존재)으로 자명. 위임이 test 주석(`:65-67`)에 명시되어 빈 셀 아님. 분류 어휘만 정정 권장.
2. **[non-blocking, 추적유지] `ConnectElasticsearchTest` skip guard 부재**: work_log :267가 b-5 후속으로 명시한 대로, `elasticsearch` 패키지 없는 환경에서 3개가 hard-fail. 이 slice 범위 밖이나, 패키지 없는 sandbox에서는 "green bar"가 3 failed로 오해될 수 있음. skip guard(`@unittest.skipUnless(importlib.util.find_spec("elasticsearch"), ...)`) 또는 sandbox `pip install` 권장.
3. **[non-blocking, 한계#1 인지] live backfill 미실행**: 회귀는 InMemory fake + `DeterministicFakeEmbeddingProvider`로 sandbox 안 결정성. 실 Mongo + real ES nori backfill은 sandbox 밖(브리프 한계#1·work_log :266). 이 slice는 코드-완료 + 회귀-잠금이지 live smoke가 아님 — 오너가 "정지" 선택한 상태에서 후속 추적 합리.

## Verdict

**합격(PASS)**.

근거:
- 경계 매트릭스(8 분기) 빈 셀 없음 — 모든 should-fire/should-NOT-fire가 회귀·mutation으로 추적(§1).
- helper 전부 실존 + worker composite 대칭 시그니처 일치(§2/§4).
- mutation 양방향 4건 전부 독립 재실증 CAUGHT(§5).
- 전체 스위트 카운트 704/45+3 failed 정확 재현(§6).
- 3 failed 인과단절 확증 — HEAD 인력으로도 동일 재현, slice 비관여(§7). 작업자 본문 정정(ES 패키지 호스트 부재·requirements.txt:2·컨테이너엔 존재) 진실.
- SoT/CHANGELOG/HANDOFF v1.6.58 일관 갱신, 3 failed 투명 기록(§8).
- `git diff --check` clean.

조건 없는 합격. 단, 비차단 정정 3건(위 Issues) 권장.

## Outstanding items

- **미커밋 working tree**: 6 modified + 3 untracked. 오너가 "정지"를 선택했으나 커밋 여부는 미확정 — 이 검증은 working tree 기준. 커밋 시 본 검증의 source-of-work 필드를 commit hash로 갱신 필요.
- **ES 환경 의존 failed**: 오너 지시 시 (a) sandbox에 `pip install -r services/application/requirements.txt` 또는 (b) `docker compose run application python -m pytest` 로 컨테이너 안 실행, (c) b-5 후속으로 `ConnectElasticsearchTest` skip guard 추가 — 셋 중 하나로 3 failed 회피.
- **다음 slice는 오너 정지**: HANDOFF Next Tasks #1 잔존 후보(b-4 hybrid 튜닝·(c)~(e)·Phase 6). 오너 지시 시 착수 브리프부터.

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system

# (1) 전체 스위트 — 3 failed, 704 passed, 45 skipped 재현
python3 -m pytest -q --ignore=tests/test_memory_mongo.py

# (2) 3 failed 인과단절 — HEAD memory.py로도 동일 재현
git show HEAD:scripts/phase2b5_reindex_memory.py > /tmp/m.py.bak
cp scripts/phase2b5_reindex_memory.py /tmp/m_wt.py
cp /tmp/m.py.bak scripts/phase2b5_reindex_memory.py
python3 -m pytest tests/test_context_search_memory_lexical_retrieval.py::ConnectElasticsearchTest -q  # 3 failed 동일
cp /tmp/m_wt.py scripts/phase2b5_reindex_memory.py  # 복원

# (3) mutation 양방향 4건 (각: 적용→1 failed→복원→1 passed)
#   MUT-1 memory canonical 필터: 'canonical = [m for m in memories if m.status is MemoryStatus.CANONICAL]' -> 'canonical = list(memories)'
#   MUT-2 memory lexical leg:    'lexical_written = lexical_index.index_memory_records(tuple(lexical_records))' -> 'lexical_written = 0'
#   MUT-3 candidate lexical leg: 'lexical_written = lexical_index.index_candidate_records(tuple(lexical_records))' -> 'lexical_written = 0'
#   MUT-4 candidate vector leg:  'vector_written = vector_index.upsert_candidate_records(tuple(vector_records))' -> 'vector_written = 0'
python3 -m pytest 'tests/test_phase2b5_reindex_memory_script.py::RunReindexTest::test_reindexes_only_project_canonical' -q
python3 -m pytest 'tests/test_phase2b5_reindex_candidate_script.py::RunReindexTest::test_reindexes_only_project_needs_review' -q

# (4) whitespace
git diff --check   # clean
```
