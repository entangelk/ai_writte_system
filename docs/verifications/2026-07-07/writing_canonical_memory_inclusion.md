# Verification — Writing ContextPackage canonical memory 포함 (⑤ §5 B)

## Subject metadata

- **Date**: 2026-07-07
- **Requester**: entangelk (오너) — “클로드 작업 Ai가 작업한 부분 확인하고 검증하고 의심하고 또 의심해줄래?” (구현 완료 커밋 ce60cdb, SoT v1.6.48)
- **Verifier**: Claude (독립 검증, 구현 작업 미관여)
- **Target slice / artifact**: ⑤ §5 B — `services/application/app/context_search/models.py`(`ContextNeed.CANONICAL_MEMORY`·`NEED_ALLOWED_TOOLS`·`MACRO_NEEDS`), `context_search/service.py`(`CanonicalMemoryRetriever` seam·`MongoDirectCanonicalMemoryRetriever`·`_run_canonical_memory_step`·`_item_from_memory`·`evaluate_context_gate` memory 분기·`_gate_memory_findings`), `main.py`(retriever·gate `memory_service` 배선), 회귀 `tests/test_context_search_canonical_memory.py`(+8).
- **Canonical spec reference**:
  - `docs/system-contract-sot.md` **v1.6.48**(version-table 행 + §5 prose 2행 + “미확정으로 남은 것” 행 갱신).
  - `docs/plans/04-writing-canonical-context-decisions.md`(Resolved, D1~D7 + Owner decisions D1=A·D2=A·D3~D7 추천 잠금).
  - 하위 계약: v1.6.40(2B.1 `MemoryEntry`/`MemoryStatus`), v1.6.45(`derive_memory_index_text` projection D1=A), v1.6.38(`04-context-package-completion-decisions.md` D1=B로 ⑤를 Phase 2B 종속 — 본 slice가 해소), SoT §5 “retriever step 실패 error taxonomy는 `backend_error`/…”.
- **Source of work being verified**: commit **ce60cdb**(HEAD, `main`, working tree clean).

## Scope

1. **계약**: D1=A(canonical만, candidate 금지 유지)·D2=A(Mongo-direct retrieval + retrieval/권위-재유도 분리)·D3=A(`ContextItem` 재사용 + `pointer.collection` origin 분기)·D4=A(Gate memory 분기 = memory store 재조회로 존재+`status is CANONICAL`+project 재검증)·D5=A(micro 전용)·D6=A(신규 `canonical_memory` need·tool mongo)·D7=A(계약+fake 증분). framing 전환(candidate→canonical)과 ⑤ 종속 해소 사실.
2. **구현 코드**: `models.py`(need/tool/macro 매핑), `service.py`(retriever·step·item·gate 4분기), `main.py`(배선).
3. **회귀**: `test_context_search_canonical_memory.py`(+8). 기존 context_search 회귀 무변(seam optional) 확인.
4. **공개 표면/envelope**: `ContextItem`(memory pointer: collection=`memory_entries`·document_id·version_id·content_hash=""), `GateFinding` check literal(`candidate_item_not_allowed`·`memory_gate_unconfigured`·`stale_item`), `SearchStepTrace`(tool=MONGO·failure=`BACKEND_ERROR`).
5. **전체 스위트**(infra-free 단위; `test_memory_mongo.py`는 Mongo env artifact로 프로젝트 검증 관례상 ignore — 하단 Issues #1 참조).

## Methodology

scoped reading(SoT v1.6.48 행 + 브리프 D1~D7 + 하위 v1.6.40/v1.6.45/v1.6.38)로 boundary matrix(should-fire 10 + should-NOT-fire 3) 작성 후 분기→회귀 추적. 1차 소재(`file:line`) 재유도 + 독립 변이(mutant) 2종로 non-vacuity 증명. 프로덕션 도달성은 HTTP request→planner→service 체인으로 추적.

```bash
# (1) 위생 + 컴파일
git status --porcelain && git log --oneline -1          # clean / ce60cdb
git show ce60cdb --stat                                  # 9 files, +678/-13
python3 -m py_compile services/application/app/context_search/service.py \
  services/application/app/context_search/models.py services/application/app/main.py \
  tests/test_context_search_canonical_memory.py

# (2) focused + 전체 스위트(프로젝트 관례: mongo env artifact ignore)
python3 -m pytest tests/test_context_search_canonical_memory.py -q          # 8 passed
python3 -m pytest -q --ignore=tests/test_memory_mongo.py                    # 618 passed / 45 skipped

# (3) non-vacuity 변이 — guard 양방향 재실패 증명(후술 Findings §3)
#   mutation-1: service.py `_gate_memory_findings` `is not CANONICAL` → `is CANONICAL`
#     → test_superseded_..._rejected_stale(under-strict) + test_canonical_memory_item_passes(over-strict) 실패
#   mutation-2: service.py retriever `if entry.status is MemoryStatus.CANONICAL` 제거
#     → test_canonical_memory_lands_in_micro + test_returns_canonical_only_and_respects_limit 실패
#   (각 변이 후 원본 복구, git diff --check clean 재확인)

# (4) mongo memory 실패의 사전-존재 성격 증명(회귀 아님)
git checkout f730791 -- services/application/app/memory/ tests/test_memory_mongo.py
python3 -m pytest tests/test_memory_mongo.py -q   # 동일 4 failed (부모 커밋에서 재현)
git checkout ce60cdb -- services/application/app/memory/ tests/test_memory_mongo.py
```

## Findings

### 1. 계약 — D1~D7 + framing 전환 (PASS)

- **framing 전환 사실 확인**: 원 브리프 `04-context-package-completion-decisions.md` D1=B(⑤를 candidate 포함 전제로 Phase 2B 종속)가 Phase 2B(2B.1~2B.6)로 canonical store 해소됨 → 본 slice 대상이 candidate가 아닌 canonical로 전환된 점은 SoT v1.6.48 행·브리프 “왜 지금 열리나”·§5 prose 3곳이 모두 정합. 계약 내부 모순 없음.
- **D1=A(canonical만, candidate 금지 유지)**: Gate candidate 검사 `service.py:636`(`if item.status is ContextItemStatus.CANDIDATE → candidate_item_not_allowed`)가 origin 분기(645) **이전**에 전 item에 적용 — memory item도 예외 없이 candidate 라벨이면 reject. 문구 “later slice” → “not allowed in Writing context (canonical only)” 정정(`service.py:641`)으로 금지 의미 명확화.
- **D2=A(retrieval/권위 분리)**: `CanonicalMemoryRetriever` Protocol(`service.py:98`)이 retrieval seam이고, 권위 재유도는 항상 `MongoDirectCanonicalMemoryRetriever`→`MemoryService`(`service.py:122-133`) + Gate `_gate_memory_findings`→`get_memory`(`service.py:682`). vector/ES는 동일 `retrieve` 메서드만 구현하면 item/Gate 불변 — 분리 구조 계약과 일치.
- **D3=A(item 형태)**: `_item_from_memory`(`service.py:344-370`)가 `ContextItem` 재사용, pointer = `IndexPointer(collection=MEMORIES_COLLECTION, document_id=entry.id, version_id=str(entry.version), content_hash="")`(`service.py:358-364`). `MEMORIES_COLLECTION="memory_entries"`(`indexing/service.py:42`) == SoT literal.
- **D4=A(Gate 분기)**: `evaluate_context_gate`가 `pointer.collection == MEMORIES_COLLECTION`로 분기(`service.py:645`) — memory item은 `_gate_memory_findings`(`get_memory` 재조회: None service→`memory_gate_unconfigured` 673 / `MemoryNotFound`→`stale_item` 685 / `status is not CANONICAL`→`stale_item` 693), source-block은 종전 `_gate_stale_findings` 유지(649). `get_memory`가 project-scoped(`memory/service.py:326-329`, 불일치 시 `MemoryNotFound`)라 cross-project도 `stale_item`로 폐쇄.
- **D5=A(micro 전용)**: `models.py` `MACRO_NEEDS`에 `CANONICAL_MEMORY` 미포함 → `build_context_package` 분리 `service.py:197-198`(`need in MACRO_NEEDS`)에서 micro로만 분류.
- **D6=A(need/tool)**: `ContextNeed.CANONICAL_MEMORY="canonical_memory"`(`models.py:43`), `NEED_ALLOWED_TOOLS[CANONICAL_MEMORY]=(SearchTool.MONGO,)`(`models.py:76`). `DEFAULT_CANONICAL_MEMORY_LIMIT=8`(`service.py:97`).

### 2. 구현↔계약 literal 일치 (PASS)

| literal | 계약(SoT/브리프) | 구현 | 일치 |
|---|---|---|---|
| need 이름 | `canonical_memory` | `ContextNeed.CANONICAL_MEMORY="canonical_memory"` (`models.py:43`) | ✓ |
| tool | mongo | `NEED_ALLOWED_TOOLS=(SearchTool.MONGO,)` (`models.py:76`) | ✓ |
| pointer.collection | `memory_entries` | `MEMORIES_COLLECTION="memory_entries"` (`indexing/service.py:42`) | ✓ |
| pointer.document_id | memory_id | `entry.id` (`service.py:361`) | ✓ |
| pointer.version_id | `str(version)` | `str(entry.version)` (`service.py:362`) | ✓ |
| pointer.content_hash | `""` | `content_hash=""` (`service.py:363`) | ✓ |
| status | `CANONICAL` | `ContextItemStatus.CANONICAL` (`service.py:352`) | ✓ |
| text projection | `derive_memory_index_text` 재사용 | `derive_memory_index_text(entry.memory_type, entry.payload)` (`service.py:355`) — signature `derive_memory_index_text(memory_type, payload)`(`memory_index.py:38`)과 일치 | ✓ |
| macro 배치 | micro(macro 금지) | `MACRO_NEEDS` 미포함 (`models.py`) | ✓ |
| Gate check literal | candidate/memory_gate_unconfigured/stale_item | 각각 `service.py:639,676,688,696` | ✓ |

`MemoryStatus` enum은 `{CANONICAL, SUPERSEDED}` 두 literal만(`memory/models.py:23-27`) — candidate는 memory 수준이 아니라 `ContextItemStatus` 라벨 개념이므로, Gate의 candidate 금지가 `ContextItemStatus.CANDIDATE`를 검사하는 것(`service.py:636`)은 계약과 정합.

### 3. 회귀 — boundary matrix + non-vacuity 변이 (CONDITIONAL: 1 empty cell)

`test_context_search_canonical_memory.py`(+8) 추적 결과:

| # | 분기 | 방향 | 회귀 | 상태 |
|---|---|---|---|---|
| 1 | memory present+canonical+동일 project → PASS | should-fire | `test_canonical_memory_item_passes`(210) | ✓ |
| 2 | memory superseded → stale_item REJECT | should-fire | `test_superseded_..._rejected_stale`(230) | ✓ 변이-1로 under-strict 증명 |
| 3 | memory missing/cross-project → stale_item REJECT | should-fire | `test_missing_..._rejected_stale`(256) | ✓ |
| 4 | `memory_service=None` → memory_gate_unconfigured REJECT | should-fire | `test_memory_item_without_memory_service_is_rejected`(276) | ✓ |
| 5 | candidate-status memory item → candidate_item_not_allowed REJECT | should-fire | `test_candidate_status_memory_item_still_rejected`(298) | ✓ |
| 6 | retriever canonical-only(superseded 제외) | should-fire | `test_returns_canonical_only_and_respects_limit`(188) + `test_canonical_memory_lands_in_micro`(165) | ✓ 변이-2로 증명 |
| 7 | retriever limit 준수 | should-fire | `test_returns_canonical_only_and_respects_limit`(196-200) | ✓ |
| 8 | memory item → micro(macro 금지) | should-fire | `test_canonical_memory_lands_in_micro`(169) | ✓ |
| 9 | retriever 미주입 → 빈 step·무실패 | should-fire | `test_unwired_retriever_yields_empty_without_failure`(178) | ✓ |
| **10** | **retriever 예외 → `BACKEND_ERROR` failure** | **should-fire** | **없음** | **⚠ EMPTY CELL** |
| 11 | (over-strict) canonical memory가 stale로 오탐되지 않음 | should-NOT-fire | `test_canonical_memory_item_passes`(228) — 변이-1로 재실패 증명 | ✓ |
| 12 | (over-strict) canonical-only filter가 canonical을 덜지 않음 | should-NOT-fire | limit=10이 {m1,m3} 반환(200) — 변이-2로 재실패 | ✓ |
| 13 | (over-strict) memory origin이라 candidate 금지가 우회되지 않음 | should-NOT-fire | `test_candidate_status_memory_item_still_rejected`(298) | ✓ |

**변이-1**(gate `is not CANONICAL` → `is CANONICAL`, `service.py:693`): `test_superseded_..._rejected_stale`(under-strict) **와** `test_canonical_memory_item_passes`(over-strict) **둘 다** 실패 → guard 양방향 non-vacuous. **변이-2**(retriever canonical filter 제거, `service.py:131`): `test_canonical_memory_lands_in_micro` + `test_returns_canonical_only_and_respects_limit` 실패 → retriever guard non-vacuous. 두 변이 모두 원본 복구 후 `git diff --check clean`·8/8 green 재확인.

### 4. 공개 표면/envelope + 도달성 (PASS)

- **도달성(reachability) 확인**: Writing HTTP 요청이 `body.needs`를 `ContextSearchRequest.needs`로 변환(`main.py:1435-1452`)하고, planner 프롬프트가 “use only the needs listed in the request”(`planner.py:51,55`) + `request.needs` iterate로 need를 LLM에 전달(`planner.py:147-154`). 서비스는 `step.need not in requested`면 거부(`service.py:255`). → 클라이언트가 `needs=["canonical_memory"]`를 보내면 `_run_canonical_memory_step`(`service.py:287`) 도달. **dead code 아님**. 기존 Writing 흐름이 이 need를 요청하지 않으면 step 미발생 → “기존 55 무변(seam optional)” 주장 정합.
- **배선**: `create_app`이 `_default_context_search_service(memory=memory)`(`main.py:568`)로 retriever `MongoDirectCanonicalMemoryRetriever(memory)`(`main.py:411`) + gate `memory_service=memory`(`main.py:1405`) 배선. — 프로덕션에서 메모리 item이 오면 항상 memory store 재검증됨.
- **envelope count 재계산**: 회귀 파일 8 test method == SoT v1.6.48 “회귀 8개” 주장과 일치(스모크 재실행으로 재유도, 신뢰).

### 5. 전체 스위트 (PASS w/ env note)

`pytest -q --ignore=tests/test_memory_mongo.py` → **618 passed / 45 skipped**(SoT v1.6.48 “618 passed / 45 skip”과 정확 일치). `--ignore` 없이 실행 시 `test_memory_mongo.py` 4개가 추가로 **fail**하지만 — 이는 본 slice가 아닌 Mongo env artifact(하단 Issues #1).

## Issues / Risks

### Issue #1 (BLOCKING) — boundary cell #10 empty: retriever 예외→`BACKEND_ERROR` 분기에 회귀 부재

`_run_canonical_memory_step`가 `self._canonical_memory_retriever.retrieve(...)`를 `try/except Exception`으로 감싸 `StepFailure(error_type=ContextSearchErrorType.BACKEND_ERROR, detail="canonical memory retrieval failed: …")`를 내보낸다(`service.py:302-314`). 이 분기는 **계약-grounded**다 — SoT §5 “retriever step 실패 error taxonomy는 `backend_error`/`system_error`/`llm_error`/`sot_error`”가 canonical_memory step(=retriever step)의 실패 매핑을 규정하며, 프로덕션에선 Mongo memory store(`list_memories`)가 pymongo 장애로 raise할 수 있어 **도달 가능(reachable)** 하다(불가능 시나리오 아님). 그러나 `test_context_search_canonical_memory.py`와 repo 전체에 이 분기를 exercise하는 회귀가 **없다**(retriever raise를 주입해 `BACKEND_ERROR` failure + step이 search 전체를 crash시키지 않음을 단언하는 테스트 부재).

→ CLAUDE.md “boundary matrix has no empty cells — empty cells are blocking findings” / “An untraced branch is a blocking finding regardless of the green bar.” 선행 검증 v1.6.45(`phase_2b_5_...increment_1.md`)가 동형 패턴(worker `MEMORY_UPSERTED`+adapter 미구성→`BACKEND_ERROR`+requeue 회귀 부재)을 차단으로 분류하고 `test_memory_upserted_without_adapter_records_backend_error`로 폐쇄한 선례와 정확히 대칭. **“후속 보강”/“차단 아님”으로 재분류 금지** — 빈 셀이 채워질 때까지 본 slice는 미폐쇄.

**권장 폐쇄**: retriever가 raise하는 fake를 주입해 (a) `StepStepTrace.failure.error_type == BACKEND_ERROR` 단언(under-strict: raise가 failure로 매핑됨) + (b) step이 `()` item을 반환하고 `build_context_package`가 예외 전파 없이 완료됨을 단언(over-strict: failure가 전체 search 중단이 아님)하는 회귀 1개 추가.

### Issue #2 (non-blocking) — `sot_reloaded=True` / `snapshot_id=""` 는 memory item에서 inert placeholder

`_item_from_memory`가 memory item에 `sot_reloaded=True`(`service.py:368`)·`snapshot_id=""`(`service.py:367`)를 설정. `sot_reloaded` 유일 소비자는 `service.py:628`(`if not item.sot_reloaded → missing_sot_reload`)이고 `snapshot_id` 소비자(`service.py:711,717,743`)는 모두 `_gate_stale_findings` 내부 — memory item은 origin 분기(645)로 이 경로를 **우회**하므로 두 필드는 memory item에서 **의미상 inert**(dataclass 필수 필드를 채우는 placeholder). `True`로 두는 것이 오히려 `missing_sot_reload` 오탐을 피해 정확. 결함 아님 — 다만 필드명이 memory origin에서 약간 오도적이므로 D3=A(`ContextItem` 재사용)의 의도된 비용으로 문서화 가치.

### Risk #3 (non-blocking) — Mongo env: 샌드박스 run이 worker run과 skip/fail 분류가 다름

본 sandbox에서 `pytest -q`(ignore 없음)는 `test_memory_mongo.py::MongoMemoryRepositoryTest` 4개가 **fail**(`create_index` 중 `localhost:27017` pymongo 연결 오류; probe `_probe_mongo`가 reachable로 오탈새해 skip 대신 fail). 부모 커밋 `f730791`에서 `memory/`·`test_memory_mongo.py`만 checkout해 동일 실행 → **동일 4 failed** 재현. ce60cdb는 `memory/`를 건드리지 않음(`git show ce60cdb --stat`: `memory/` 파일 없음). 따라서 **사전-존재 sandbox 환경 artifact**이며 본 slice의 회귀가 아니다. worker의 “618 passed / 45 skip”은 프로젝트 검증 관례(`--ignore=tests/test_memory_mongo.py`) 기준이며, “618 passed”는 본 sandbox에서도 정확히 일치. 비차단.

## Verdict

**조건부 합격 → 폐쇄(합격) (conditional pass → closed: pass).** 하단 “Closure” 절 참조.

- 계약(D1~D7 + framing 전환)·구현 literal·도달성·envelope count·전체 스위트(618/45)는 모두 PASS. 핵심 안전 guard 2종(gate superseded→stale, retriever canonical-only)을 **독립 변이로 양방향 non-vacuity 증명** — 커밋의 “gate·retriever guard mutation 재실증” 주장을 신뢰 없이 재확증.
- **차단 조건**: Issue #1. boundary cell #10(retriever 예외→`BACKEND_ERROR`)이 empty cell이다. 계약-grounded이고 도달 가능한 분기에 회귀가 없으므로, CLAUDE.md에 따라 빈 셀이 채워질 때까지 slice 폐쇄 불가. 선행 v1.6.45 검증의 동형 선례와 동일 취급.
- Issue #2·#3은 비차단(문서화/환경 관찰).

## Outstanding items

- **(차단 해소용) 회귀 1개 추가**: retriever-raise→`BACKEND_ERROR` + step-non-crash 양방향 단언(Issue #1). 추가 후 본 검증의 boundary cell #10을 채운 것으로 재확인 필요.
- 본 검증은 working tree를 변경하지 않음(변이 2종은 원복 완료, `git diff --check clean`). 신규 회귀 추가는 오너/구현자 결정 후 별도 slice 또는 follow-up.
- 후속 slice(본 slice 범위 밖, 브리프 “후속” 명시): (a) `needs_review` candidate 포함(본 slice machinery 재사용), (b) relevance vector/검색엔진 retrieval 레이어 교체(D2 연장).

## Reproduction

```bash
git checkout ce60cdb
git status --porcelain                                        # clean
python3 -m pytest tests/test_context_search_canonical_memory.py -q        # 8 passed
python3 -m pytest -q --ignore=tests/test_memory_mongo.py                  # 618 passed / 45 skipped

# Issue #1 재현(retriever-raise 분기에 회귀 없음 확인): grep으로 분기는 있으나
grep -nE "BACKEND_ERROR|except Exception" services/application/app/context_search/service.py
grep -rnE "BACKEND_ERROR|raises|retrieve.*raise|class .*Retriever" tests/test_context_search_canonical_memory.py  # → 매핑 단언 없음

# Risk #3 재현(사전-존재 mongo env fail):
git checkout f730791 -- services/application/app/memory/ tests/test_memory_mongo.py
python3 -m pytest tests/test_memory_mongo.py -q                           # 동일 4 failed
git checkout ce60cdb -- services/application/app/memory/ tests/test_memory_mongo.py
```

## Closure (post-verification, 2026-07-07)

오너가 “차단 및 비차단 포함해서 보강”을 지시해, 본 검증의 차단(Issue #1)과 비차단 #2를 폐쇄/보강했다. (인계: 구현 AI가 `ContextSearchErrorType` import 추가 후 중단 → 검증 AI가 폐쇄 수행.)

- **Issue #1 (BLOCKING) → closed**: `tests/test_context_search_canonical_memory.py`에 `CanonicalMemoryRetrieverFailureTest.test_retriever_failure_maps_to_backend_error_without_crashing` 추가. `_RaisingRetriever`(항상 raise)를 `_service(retriever=…)` override로 주입해 — (a) 예외가 `BACKEND_ERROR` failure로 기록됨(under-strict), (b) failure가 step에 격리되어 package가 `degraded=True`로 완성·search 비-crash(over-strict) — boundary cell #10 채움.
  - **mutation 재실증(양방향)**: `except Exception`→`except TypeError`(RuntimeError 미포착→전파) 시 본 테스트 재실패(under-strict); 매핑 `BACKEND_ERROR`→`SYSTEM_ERROR` 시 재실패(over-strict). 두 변이 모두 원복.
- **Issue #2 (non-blocking) → reinforced**: `_item_from_memory`(`service.py`) 주석에 `snapshot_id`/`sot_reloaded`가 memory item에서 inert placeholder인 이유(origin 분기가 `_gate_stale_findings`를 bypass)를 문서화. 코드 동작 변경 없음.
- **Issue #3 (non-blocking) → no action**: 사전-존재 Mongo env artifact(본 검증 Risk #3에서 이미 부모 커밋 재현·회귀 아님 입증).
- **재검증**: `pytest tests/test_context_search_canonical_memory.py -q` → **9 passed**(8→9). `pytest -q --ignore=tests/test_memory_mongo.py` → **619 passed / 45 skipped**. `git diff --check` clean. boundary matrix cell #10 이외 셀은 변동 없음(신규 셀만 충원).
- **SoT/기록 연동**: SoT v1.6.48 entry에 closure note append(회귀 +1·619 passed), `docs/daily_logs/2026-07-07/work_log.md` “⑤ §5 B 검증 후속 보강” 절 추가.
