# 검증 기록 — 라우터 분해 Slice 1 잔여 1차 (health·memory·observability·context-search)

- **날짜**: 2026-08-07
- **요청자**: 오너 ("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?")
- **검증자**: Claude Code (독립 검증 — 피검증 슬라이스 비생산)
- **검증 대상**: 커밋 `b6eec79`(이동) · `925a321`(factory 통합 + 가드 전수화). 기록 커밋 `187d4b2`.
  작업 로그 [`docs/daily_logs/2026-08-07/work_log.md`](../../daily_logs/2026-08-07/work_log.md).
- **정본 사양**: 이 슬라이스의 계약은 "행위 무변"이다(내부 이동). 정본은 [`docs/verifications/2026-08-05/repro_router_split.py`](../2026-08-05/repro_router_split.py) 가 정의하는 공개 표면 지문 + 이동 정의의 byte-동일.
- **소스**: `main` 브랜치 HEAD(`187d4b2`), 작업 트리 clean.

## Scope

1. **계약(행위 무변)** — `create_app()` 공개 표면: (path,method) 76 · 해석된 dependency 트리 · status_code/response_model/responses · `app.openapi()` sha256 · order-sensitive pair 수.
2. **이동 정의 byte-동일** — 옮겨간 정의 12종(handler 5 + 직렬화기 7)의 본문.
3. **패치 타깃 일관성** — 이동한 심볼을 가리키던 테스트 패치가 새 경로로 갱신됐는지(누락=조용한 무효화).
4. **전수 회귀** — backend 풀스위트(test-mongo ON).
5. **뮤테이션 5종** — 작업자 표의 셀-매칭 재현.
6. **잡동사니 주장** — 가드 보강(글롭) · factory 행위 동일 · 기준선 정렬 · scope_id 추적 부채 · 미사용 import 카운트.

## Methodology

- **(1) 행위 무변**: 슬라이스 직전 `9bc06e3` 을 워크트리로 만들어 repro 를 돌리고, HEAD 와 지문을 `diff`.
  ```bash
  git worktree add /tmp/pre_slice 9bc06e3
  (cd /tmp/pre_slice && python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/pre.json)
  python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/post.json
  diff /tmp/pre.json /tmp/post.json && echo IDENTICAL
  ```
- **(2) byte-동일**: `git show 9bc06e3:main.py` 와 HEAD 신규 파일에서 12 정의를 AST 로 이름별 추출해 `ast.unparse` 비교(들여쓰기 정규화, 리터럜/키/속성/호출인자는 보존). repro 가 `dict[str, object]` 응답의 직렬화기 본문을 못 보는 빈칸을 이게 닫는다.
- **(3) 패턴 스윕**: `grep -rn "app\.main\.(evaluate_context_gate|aggregate_kpi|_build_context_search_request|_memory_payload|_scope_payload|_project_brief_payload|_context_*|observability_kpi_endpoint|list_memory|get_memory|context_search_endpoint)" tests/`.
- **(4) 전수 회귀**: `docker compose -f docker-compose.test.yml up -d` 후 `python3 -m pytest tests/ -q`. (이 셸은 ES 8.19.3 설치 → 어휘 검색 3셀이 skip 아닌 pass, skip=1=live Chroma.)
- **(5) 뮤테이션**: 트리 clean 게이트 → mutate → focused pytest → `git checkout -- <path>` 원복 → 원복 clean 확인. (트리가 커밋된 상태라 HEAD 로 정확히 되돌아간다.)
- **(6) 정적**: 글롭 모듈 수 · `project_existence_check` 사용처 · README/HANDOFF 기준선 · test_memory_api 의 `scope` 언급 · AST 기반 미사용 import 카운트.

## Findings

### (1) 행위 무변 — IDENTICAL

`diff /tmp/pre.json /tmp/post.json` 출력 없음. 양쪽 `route_count=76`, `order_sensitive_pairs=[]`(0), `openapi_sha256` 동일, route 별 `deps`/`status_code`/`response_model`/`responses` 동일. stderr 의 이동 현황만 다르다(pre `in-routers=12` → post `in-routers=17`). **`{project_id}` route 가 register 로 나간 첫 실행에서 order-sensitive pairs 가 0 인 것이 실제 검사였음을 확인** — first-match 모호성 0건.

### (2) 이동 정의 byte-동일 — 12/12

`_project_brief_payload` · `_memory_payload` · `_scope_payload`(→`api/payloads.py`, 모듈 수준) · `_context_item_payload` · `_context_trace_payload` · `_context_package_payload` · `_build_context_search_request`(→`routers/context_search.py`) · `health` · `list_memory` · `get_memory` · `observability_kpi_endpoint` · `context_search_endpoint`. **12/12 `ast.unparse` 동일.** 세 직렬화기는 순수(입력을 인자로만 받고 create_app 지역을 클로저로 안 잡음)라 파일 이동이 안전함. 특히 `_scope_payload` 는 main.py:2916(잔류 핸들러)에서도 직접 쓰이므로 공유 모듈 행방이 강제됨을 확인(작업자 근거 부합).

### (3) 패치 타깃 — 누락 없음

`tests/test_context_search_api.py:246·277·296` 의 `patch(...)` 3곳이 전부 `…app.main.evaluate_context_gate` → `…app.routers.context_search.evaluate_context_gate` 로 갱신됐다(파일 내 patch 호출이 정확히 이 3개). `app.main.<이동심볼>` 로 패치하는 다른 테스트는 **0건**. 이동 심볜은 main.py 에서 **0 발생**(완전 제거) → 조용한 무효화 패치 없음.

### (4) 전수 회귀 — 2197/1/2159

`2197 passed, 1 skipped, 2159 subtests passed in 1009.60s`. 작업자 기준선(2197/1/2159, 889s)과 **셀·subtest·skip 전부 일치**(시간 차이는 dev stack 가동 중인 머신 부하).

### (5) 뮤테이션 5종 — 전부 주장대로 물림

| # | 뮤테이션 | 결과(재실측) |
|---|---|---|
| M5 | `_scope_payload` 에서 `scope_id` 제거 | `test_memory_api.py` **23 passed**(전부 통과 → scope_id 단정 셀 없음 확인) · analysis 셀 **FAIL** `{'scope_type':'character'} != {... 'scope_id':'ariel song'}`. 공유 직렬화기가 진짜 공유됨을 입증. |
| M1 | `routers/memory.py` → `from ..main import _memory_payload`(순환 복귀) | 5 cells 재실패. 결정적으로 `test_a_router_module_loads_before_main` 이 **`SUBFAILED(module='…routers.memory')`** 로 범인을 정확히 지목 → **이 슬라이스의 가드 보강이 순환을 직접 잠근다.** |
| M2 | `register_memory` 호출 삭제 | tier 전수 가드 **FAIL** `59 != 61`(project-tier 카운트가 `len(tiers)==76` 보다 먼저 물음). register 누락의 방어선 확인. |
| M4 | `except _STORAGE_ERRORS: raise` 절 제거 | storage-503 셀 **FAIL** `502 != 503`. 방어 제거 방향 재실패. |
| M3 | context-search dependency 순서 뒤집기 | enforcement-order 셀 **`SUBFAILED(operation=context-search)` 1개만**, 나머지 8 billable 통과. 넓은 셀이 흡수하지 않음. |

원복 후 `git status --short` 빈 트리 + 변이 4파일 전부 HEAD 와 byte-동일(`diff -q <(git show HEAD:f) f` OK). **뮤테이션 잔류 없음.**

### (6) 잡동사니 주장

- **가드 보강**: 글롭이 `routers/*.py` 에서 정확히 **6개**(admin·auth·context_search·health·memory·observability)를 잡는다. `_ROOT=parents[1]`(repo root) 정확. 종전 하드코딩(admin·auth 2개) 대비 subtest 2→6. ✓
- **factory**: `project_existence_check(core_sot)`([`api/dependencies.py:334`](../../services/application/app/api/dependencies.py)) 는 인자로 받은 `core_sot` 를 잡는 동일 클로저. main.py:2052 + 라우터 3곳(memory·observability·context_search)에서 사용, 잔여 인라인 `def _require_project_exists` 는 **factory 1곳만**. ✓
- **기준선 정렬**: [`README.md:88`](../../README.md) `2,197 passed / 2,159 subtests` · [`HANDOFF.md:70`](../../HANDOFF.md) `2197/1/2159` 로 갱신 + 낡은 `2196/1/1933` 설명. ✓
- **미사용 import**: AST 검출기로 슬라이스 전후 **동일 21개**(`annotations` __future__ 위양성 1개 제외). 제거한 6개는 이동 전 사용 / 후 미사용 / 제거 로 일관(양쪽 어디에도 안 나타남). 새 미사용 0. 21개는 기존 부채. ✓

## Issues / Risks

### Blocking (계약 의무)

없음.

### Hardening recommendations (비차단)

- **`GET …/memory` 응답의 `scope.scope_id`(나아가 `scope` 자체)를 단정하는 셀이 `test_memory_api.py` 에 없다** — `scope` 언급 **0건**(scope_type 도 안 단정). 현재 analysis 셀([`test_analysis_compare_api.py:238`](../../tests/test_analysis_compare_api.py))에 전이적으로만 걸려 있다(M5 로 입증). **이 슬라이스가 만든 결함이 아니다** — `test_memory_api.py` 를 슬라이스가 한 줄도 안 건드렸고(`git diff 9bc06e3 HEAD -- tests/test_memory_api.py` 공백), `_scope_payload` 본문은 byte-동일이다. 작업자가 추적 부채로 올린 항목에 동의하며, memory 응답 형태를 직접 단정하는 셀을 별도 hardening 에서 추가하면 boundary 가 견고해진다(현재 spec 이 이 필드를 강제하는지는 별도 계약 확인 필요).

- (화술적) 작업자 M2 서술이 tier 가드를 "76 operation 이 안 맞는다" 로 적었으나, 실측으론 **project-tier 카운트(61)** assertion 이 먼저 물린다. 셀이 물린다는 사실엔 영향 없음.

## Verdict

**합격** — 행위 무변이 repro 지문 IDENTICAL(경로 76 · pairs 0 · openapi sha · dependency 트리 전부 무변) 과 이동 정의 12/12 AST-동일로 입증됐고, 패치 타깃 누락 없으며, 전수 회귀 2197/1/2159 재현, 뮤테이션 5종 전부 주장 셀에 물렸다(가드 보강 셀이 순환을 직접 지목). 유일한 빈칸(scope_id 단정 셀 부재)은 이 슬라이스 이전의 test-coverage 부채로 hardening 영역이지 이 슬라이스의 계약 위반이 아니다.

## Outstanding items

- test-mongo 회수함(검증자가 기동했던 것 회수 — dev stack 본체는 건드리지 않음).
- 슬라이스는 그대로 둔다(차단 발견 없음). 작업자가 별도 슬라이스로 올린 보류 사항 — main.py 기존 미사용 import 21개 정리 · `GET …/memory` scope 단정 셀 추가(hardening) · 잔여 도메인(projects·drafts·analysis·writing, 59 operation) 이동.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# (1) 행위 무변
git worktree add /tmp/pre_slice 9bc06e3
(cd /tmp/pre_slice && python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/pre.json)
python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/post.json
diff /tmp/pre.json /tmp/post.json && echo IDENTICAL   # 기대: IDENTICAL
git worktree remove /tmp/pre_slice --force

# (2) byte-동일(12 정의 AST 비교) — docs/verifications/2026-08-07/repro_byte_identical.py
python3 docs/verifications/2026-08-07/repro_byte_identical.py   # 기대: 12/12 byte-동일(AST 정규화)

# (4) 전수 회귀
docker compose -f docker-compose.test.yml up -d
python3 -m pytest tests/ -q                            # 기대: 2197 passed, 1 skipped, 2159 subtests

# (5) 뮤테이션 5종 — docs/verifications/2026-08-07/repro_mutations.py (각 mutate→focused→git checkout 원복)
python3 docs/verifications/2026-08-07/repro_mutations.py        # 기대: M5 memory PASS·analysis FAIL / M1·M2·M4·M3 각 FAIL
```
