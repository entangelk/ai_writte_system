# Verification — `ConnectElasticsearchTest` skip guard (b-5 후속, 테스트 전용)

## Subject metadata

- **Date**: 2026-07-10
- **Requester**: owner ("작업 AI가 작업한 부분 확인하고 검증하고 의심하고 또 의심해줄래?")
- **Verifier**: Claude (독립 검증 — 본 변경을 구현한 작업자와 상이)
- **Target slice/artifact**: `tests/test_context_search_memory_lexical_retrieval.py` 내 `ConnectElasticsearchTest` 클래스에 `@unittest.skipUnless(importlib.util.find_spec("elasticsearch") is not None, …)` skip guard 추가. b-5(`connect_elasticsearch_memory_index` boot 경로 회귀 테스트) 도입 후속 소부채.
- **Canonical spec reference**: 본 변경은 계약·프로덕션 코드 무변의 **테스트 인프라** slice. 정본 계약 SoT(`docs/system-contract-sot.md`, v1.6.58 Approved)의 동작 literal·public interface를 건드리지 않으므로, 검증 기준은 (a) skip guard 논리의 정확성, (b) 작업자가 보고한 테스트 카운트(704/48, 13/3)의 독립 재현, (c) under-strict/over-strict guard 양방향, (d) 패턴 스윕의 격리성이다. b-5 회귀 테스트가 잠그는 계약 boundary(`request_timeout` 기본 30s 전달 + nori index 부재 시에만 생성)는 본 slice에서 무변 — 기존 회귀 `docs/verifications/2026-07-09/compose_elasticsearch_service_b5.md` 참조.
- **Source of work being verified**: working tree, uncommitted (`git status`: `M tests/test_context_search_memory_lexical_retrieval.py`, `M HANDOFF.md`, 신규 `docs/daily_logs/2026-07-10/work_log.md`). HEAD = `1bea1e1`(SoT v1.6.58).

## Scope

1. **구현 코드 diff** — skip guard 구문·위치·import 추가의 외과성.
2. **skip guard 논리** — `find_spec` 기반 `skipUnless`의 under-strict(패키지 없으면 skip)/over-strict(패키지 있으면 실행) 양방향.
3. **보고된 테스트 카운트** — 파일 단독(13 passed/3 skipped)·전체 스위트(704 passed/48 skipped)의 독립 재현.
4. **패턴 스윕 격리성** — `from elasticsearch import` / `mock.patch("elasticsearch…")` 패턴이 tests/·프로덕션 전체에서 어디에 존재하며, guard가 필요한 곳이 이 클래스 하나뿐인지.
5. **프로덕션 영향 0 주장** — 프로덕션 lazy import가 pytest 수집 시점에 실패하지 않는지(collection-safe).
6. **SoT bump 생략 판단** — 테스트 전용 변경에 버전 로그 항목을 만들지 않은 결정의 합리성.
7. **HANDOFF 갱신 적절성** — 테스트 카운트·Verification 섹션만 갱신하고 다른 영역을 건드리지 않았는지(surgical).
8. **선재 stale(HANDOFF:103)** — 작업자가 "정정할까요?"로 회신한 Project Structure 주석의 v1.6.57→v1.6.58 불일치.

## Methodology

재현 가능한 정확 명령 — 본 검증의 모든 관찰은 아래에서 도출됨.

```bash
# (S1) diff
git --no-pager diff tests/test_context_search_memory_lexical_retrieval.py
git --no-pager diff HANDOFF.md

# (S2) 패키지 존재 여부 (sandbox)
python3 -c "import importlib.util; print(importlib.util.find_spec('elasticsearch'))"
python3 -c "import elasticsearch" 2>&1 | tail -1

# (S3) 파일 단독
python3 -m pytest tests/test_context_search_memory_lexical_retrieval.py -q 2>&1 | tail -3

# (S4) 전체 스위트 (프로젝트 검증 관례)
python3 -m pytest -q --ignore=tests/test_memory_mongo.py 2>&1 | tail -8

# (S5) under-strict guard — guard를 제거(HEAD)한 뒤 해당 클래스만 실행 → 3 fail 재현 확인 후 복구
git stash push -m "understrict-verify" tests/test_context_search_memory_lexical_retrieval.py
python3 -m pytest "tests/test_context_search_memory_lexical_retrieval.py::ConnectElasticsearchTest" -q 2>&1 | tail -6
git stash pop
git --no-pager diff --stat tests/test_context_search_memory_lexical_retrieval.py

# (S6) 패턴 스윕
grep -rn "from elasticsearch\|import elasticsearch\|mock.patch(\"elasticsearch\|patch(\"elasticsearch" tests/ src/ services/ scripts/ 2>/dev/null
# 보강: from 없는 import 형태 + tests 내 elasticsearch 문자열 참조 파일
grep -rn "^\s*import elasticsearch\b" --include="*.py" . 2>/dev/null
grep -rln "elasticsearch" tests/ 2>/dev/null

# (S7) 프로덕션 lazy import 컨텍스트 (함수 본문 내부 = collection-safe)
# → Read services/application/app/indexing/memory_lexical_index.py:295-312
# → Read services/application/app/indexing/candidate_lexical_index.py:248-262
# → Read tests/test_context_search_memory_lexical_retrieval.py:184-251 (ConnectElasticsearchTest 본문)

# (S8) HANDOFF SoT 버전 언급 정합성
grep -n "v1\.6\.5[0-9]\|SoT" HANDOFF.md
```

## Findings

### S1 · 구현 diff — 외과적, claim과 정확 일치

`git diff`는 단 2 hunk, 5행 추가:
- `tests/test_context_search_memory_lexical_retrieval.py:16` — `import importlib.util` 추가(알파벳 순 위치, `import unittest` 직전 — PEP8 정합).
- `tests/test_context_search_memory_lexical_retrieval.py:187-190` — `ConnectElasticsearchTest` 클래스에 데코레이터 추가:
  ```python
  @unittest.skipUnless(
      importlib.util.find_spec("elasticsearch") is not None,
      "elasticsearch package not installed (this test patches elasticsearch.Elasticsearch)",
  )
  ```
  데코레이터는 클래스 본문(`class ConnectElasticsearchTest` = 191행) 직전에 위치 — unittest 클래스 데코레이터로 올바르게 적용되어 클래스 내 3개 메서드 전체를 커버.

프로덕션 코드(`services/`, `scripts/`)는 diff에 전혀 등장하지 않음 — claim "테스트 전용" 정확.

### S2 · skip guard 논리 — under-strict 실증 / over-strict 논리 정합

- **under-strict(핵심)**: `git stash`(guard 제거 = HEAD) 상태에서 `pytest ...::ConnectElasticsearchTest` 실행 → **3 failed** 재현:
  - `test_default_request_timeout_is_30_and_creates_nori_index_when_absent` — FAILED
  - `test_existing_index_is_not_recreated` — FAILED
  - `test_request_timeout_is_plumbed_not_hardcoded` — FAILED
  - 공통 원인: `tests/test_context_search_memory_lexical_retrieval.py:217` `from elasticsearch import Elasticsearch as _real` → `ModuleNotFoundError: No module named 'elasticsearch'`. CLAUDE.md "if the pre-fix bug is reintroduced, the test must re-fail" 조건 충족 — guard가 없으면 정확히 종전의 3 hard-fail이 되돌아옴. 즉 guard는 의미가 있고, 보고된 "3 failed 제거"는 guard에 의한 것.
  - `git stash pop` 후 `diff --stat` = "5 insertions"로 guard 정상 복구 확인(working tree 원상복귀 검증).
- **over-strict**: `skipUnless(cond)` → cond True면 실행, False면 skip. cond = `find_spec("elasticsearch") is not None`.
  - 패키지 있음 → `find_spec`이 모듈스펙 객체 반환 → `is not None` = True → **3개 실행**(회귀 잠금 유지).
  - 패키지 없음 → `find_spec` = `None` → skip.
  - 논리 정합. 단, **이 sandbox에는 `elasticsearch`가 미설치**(`find_spec` = `None`, `import elasticsearch` → `ModuleNotFoundError`)이므로 "패키지 있음 → 실행" 경로는 이 환경에서 실증 불가, **논리 검증만**. 작업자의 work_log가 이 제약을 정직하게 기술함("이 sandbox엔 elasticsearch 미설치라 guard가 skip 경로로 검증됨. 패키지 있는 환경…에선 종전대로 3개 실행되어 회귀 잠금 유지") — 은폐 아님. 패키지 있는 환경에서 실행 경로를 추가 실증하려면 sandbox 외 검증이 필요하나, 이는 본 slice의 범위 밖(운영 환경 의존)이며 blocking 사유가 아님.
- 참고: 테스트 본문 자체에 이미 over-strict assertion 존재(`tests/...:244` `# Over-strict guard: the param must reach the client, not a constant` — `test_request_timeout_is_plumbed_not_hardcoded`). 이는 skip guard와는 별개의(계약 수준) over-strict 잠금으로, 본 slice에서 무변.

### S3 · 파일 단독 카운트 — 재현

`python3 -m pytest tests/test_context_search_memory_lexical_retrieval.py -q` → `13 passed, 3 skipped in 0.82s`. 작업자 보고(13 passed/3 skipped)와 정확 일치. 3 skipped = guard가 발동한 `ConnectElasticsearchTest` 3개 메서드.

### S4 · 전체 스위트 카운트 — 재현

`python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → `704 passed, 48 skipped, 3 warnings, 99 subtests passed in 10.96s`(exit 0). 작업자 보고(704 passed/48 skipped)와 정확 일치. 종전 `704 passed / 45 skipped + 3 failed` 대비 failed 0, skip 45→48(+3) — guard가 3 failed를 3 skipped로 전환한 것과 수치 정합. 3 warnings는 `test_memory_api.py:26` `TestClient` `__init__` 수집 경고 등 **선재**이며 본 slice 무관.

### S5 · 패턴 스윕 격리성 — claim 정확

- `from elasticsearch import` / `mock.patch("elasticsearch…")` / `patch("elasticsearch…")` 패턴 grep → tests/ 내 유일 발생이 `tests/test_context_search_memory_lexical_retrieval.py:217,225`(둘 다 이제 guard된 `ConnectElasticsearchTest._connect` 내부). from 없는 `import elasticsearch` 형태는 repo-wide 0건.
- 프로덕션 lazy import 2곳: `services/application/app/indexing/memory_lexical_index.py:303`·`candidate_lexical_index.py:254`(둘 다 `# lazy: optional dependency` 주석). 추가로 `scripts/phase4_lexical_memory_live_smoke.py:89`(live smoke 전용, sandbox 밖).
- **추가 정밀 확인**: `tests/`에 elasticsearch **문자열**을 참조하는 파일이 4개이나, 나머지 3개는 **패키지 import/patch가 아님**:
  - `tests/test_index_sync_worker_script.py` — elasticsearch는 메서드명(`test_with_elasticsearch_url_builds_composite_memory_adapter`)·env 문자열; `mock.patch` 대상은 `os.environ`·`_REPO_PATH`(패키지 아님).
  - `tests/test_phase2b5_reindex_candidate_script.py`·`tests/test_phase2b5_reindex_memory_script.py` — `"lexical_backend": "elasticsearch"` **설정 dict 문자열값**(패키지 아님).
  - 전체 스위트가 704 passed로 통과한 것과 일관.
- 결론: guard가 필요한 패키지 의존 지점은 `ConnectElasticsearchTest` 하나뿐. 작업자의 "패턴이 한 클래스에 격리" claim 정확.

### S6 · 프로덕션 collection-safe — 확인

`memory_lexical_index.py:303`·`candidate_lexical_index.py:254`의 `from elasticsearch import Elasticsearch`는 모두 **함수 본문 내부**(`connect_elasticsearch_memory_index` / `connect_elasticsearch_candidate_index`). 특히 `memory_lexical_index.py:296-297` docstring이 "`elasticsearch` is imported here so unconfigured environments/tests never need the package"라고 명시 — pytest 수집(모듈 top-level import) 시점이 아닌 **함수 호출 시점** import → 패키지 부재 시에도 collection 안전. 전체 스위트가 collection error 없이 704 passed로 완료된 것이 이를 실증.

### S7 · SoT bump 생략 판단 — 합리적

본 slice는 skip guard 1개 추가(테스트 실행 여부만 변경). 정본 계약 SoT의 동작 literal·public interface·프로덕션 코드 무변, 동작 변화 0. v1.6.53(connect 기본값 변경)처럼 프로덕션 동작을 건드린 slice와 성격 상이. "테스트 전용 → 버전 로그 항목 불필요" 결정은 CLAUDE.md CHANGELOG 규칙("Update on major design or feature changes (not every small edit)")에 부합.

### S8 · HANDOFF 갱신 — surgical, 그러나 선재 stale 존재

- `git diff HANDOFF.md`는 테스트 카운트 라인(Compose 런타임 섹션 내 "- **테스트**:" 항목)과 `## Verification` 섹션 2곳만 갱신. Next Tasks·Active Decisions·Project Structure 등 다른 영역은 무변 — surgical 원칙 준수.
- **선재 stale(작업자가 본인 범위 밖으로 회피 → 합리적)**: `HANDOFF.md:103` "├── system-contract-sot.md       # 정본 계약 SoT(Approved, **v1.6.57**)" — 실제 정본은 **v1.6.58**(`HANDOFF.md:8` "현재 **v1.6.58**(Approved)", `1bea1e1` SoT v1.6.58 커밋). 103행은 v1.6.58 slice(ES-lexical backfill)가 Project Structure 주석 갱신을 누락한 **선재 stale**이며, 본 slice(테스트 skip guard) 범위 밖. 작업자가 손대지 않고 사용자에게 "정정할까요?"로 회신한 것은 CLAUDE.md §3 Surgical Changes("Touch only what you must")에 부합.

## Issues / Risks

1. **(비차단, 환경 제약) over-strict 실행 경로 미실증**: 이 sandbox에 `elasticsearch` 미설치로 "패키지 있음 → 3개 실행(회귀 잠금 유지)" 경로를 직접 실행하지 못함. 논리(`skipUnless` + `find_spec`)로는 정합하며, 작업자가 work_log에 이 제약을 투명하게 기술했으므로 은폐/contract gap 아님. 패키지 설치 환경(b-5/b-6 작업 환경)에서의 실행 경로 추가 실증은 권장 후속이나 blocking 아님.
2. **(선재, 비차단) HANDOFF:103 Project Structure 주석 v1.6.57 stale**: v1.6.58 slice의 갱신 누락. 본 slice 범위 밖이나, HANDOFF의 동일 파일 내 버전 표기 불일치(8행 v1.6.58 vs 103행 v1.6.57)는 독자 오독을 유발할 수 있어 정정 권장. 작업자가 사용자에게 정정 여부를 이미 질의한 상태.

이 두 항목 모두 본 slice 자체의 결함이 아니며, green bar나 회귀 잠금에 영향을 주지 않음.

## Verdict

**합격(PASS)**.

이유(하중-bearing):
- 보고된 모든 카운트(파일 단독 13/3, 전체 704/48)가 독립 재현으로 정확.
- under-strict guard가 실증됨 — guard 제거 시 종전의 정확히 3 hard-fail이 재현되므로, guard가 "3 failed 제거"의 인과 원인임이 확정.
- skip guard 논리(`skipUnless(find_spec(...))`) 정합; over-strict는 sandbox 패키지 미설치로 실행 경로 실증 불가지만 논리 정합 + 제약 투명 기술.
- 패턴 스윹 정확 — 패키지 의존 패키지 import/patch는 `ConnectElasticsearchTest` 1곳에 격리, 프로덕션은 lazy/collection-safe, 타 테스트 파일은 문자열 참조만.
- 프로덕션·계약 무변이 확인되어 SoT bump 생략이 합리적; HANDOFF 갱신 surgical.
- 발견된 두 항목(over-strict 실행경로 미실증·HANDOFF:103 stale)은 모두 비차단·본 slice 범위 밖.

본 slice는 오너 지시("오너 결정 브리프 없이 처리 가능한 작은 자족 부채")에 정확히 부합하며, 임의 착수 불가능한 큰 후보((b-4) 튜닝·(c)~(e)·Phase 6)로 넘어가지 않은 범위 통제도 적절함.

## Outstanding items

- **(오너 결정 대기) HANDOFF:103 stale 정정 여부**: 작업자가 회신한 "정정할까까?" 질문이 미응답. 정정 시 1행 변경(`v1.6.57` → `v1.6.58`), 본 slice와 무관하므로 독립 1-line 커밋 가능.
- **(오너 선택 대기) 다음 slice**: 작업자가 "다음 slice는 여전히 오너의 선택 대기"로 종료 — (b-4) hybrid 튜닝[오너 지시상 최후순위]·(c)~(e)·Phase 6 중 착수 결정 브리프가 선행되어야 함.
- **(sandbox 밖, 무변) over-strict 실행 경로 실증**: `elasticsearch` 패키지가 있는 환경에서 `ConnectElasticsearchTest` 3개가 실행되어 회귀 잠금을 유지하는지 확인 — 본 sandbox 제약으로 미실증, 운영/CI 환경에서 보강 권장.

## Reproduction

```bash
# 전체 검증 end-to-end (본 sandbox = elasticsearch 미설치)
python3 -c "import importlib.util; assert importlib.util.find_spec('elasticsearch') is None"
python3 -m pytest tests/test_context_search_memory_lexical_retrieval.py -q   # 13 passed, 3 skipped
python3 -m pytest -q --ignore=tests/test_memory_mongo.py                      # 704 passed, 48 skipped

# under-strict (guard 제거 → 3 fail 재현 → 복구)
git stash push -m v tests/test_context_search_memory_lexical_retrieval.py
python3 -m pytest "tests/test_context_search_memory_lexical_retrieval.py::ConnectElasticsearchTest" -q  # 3 failed
git stash pop

# 패턴 스윕
grep -rn "from elasticsearch\|mock.patch(\"elasticsearch\|patch(\"elasticsearch" tests/ services/ scripts/
```

---

## 검증 후속 보강 (2026-07-10, 오너 지시 "보강할 부분 보강해줘" → over-strict 실행 경로 실증 + HANDOFF:103 정정)

오너가 본 검증 기록의 outstanding 2건을 보강하도록 지시. 작업자가 두 항목을 닫았고, 검증자가 재확인함.

- **outstanding #1 closed — over-strict 실행 경로 실증(더 이상 논리-only 아님)**: 이 sandbox에 `elasticsearch>=8,<9`(requirements.txt:2 핀)를 scratchpad 격리 디렉토리에 `pip install --target`으로 설치하고 **PYTHONPATH 주입으로만** 노출(시스템 Python 무오염 — 주입 없이 `find_spec`이 다시 `None` 확인, 가역적). 설치 버전 8.19.3(b-5 각주의 client 버전과 일치).
  - **패키지 present → guard가 skip하지 않고 3개 실행·전부 PASS**: `ConnectElasticsearchTest` 3 메서드 verbose 실행 = `3 passed`(skip 0). 파일 단독 = `16 passed / 0 skipped`(종전 absent 시 13/3). → over-strict 방향(`find_spec is not None` → True → 실행) 실증, b-5 회귀 잠금이 guard 추가 후에도 **패키지 있는 환경에서 실제로 실행되어 유지**됨을 확인.
  - **전체 스위트 present = `707 passed / 45 skipped`**(absent 704/48 대비 3개가 skip→pass로 이동, 수치 정합). 다른 테스트 무영향.
  - **absent 원상복구 확인**: PYTHONPATH 미주입 시 `find_spec` = `None`, 파일 단독 다시 `13 passed / 3 skipped`. → 격리 설치가 기본 sandbox를 오염시키지 않음.
  - 결론: Issues/Risks #1(비차단, 환경 제약)이 **실행 경로 실증으로 해소**. under-strict(guard 제거 시 3 fail)와 over-strict(패키지 present 시 3 실행·pass) 양방향 모두 실증 완료.
- **outstanding #2 closed — HANDOFF:103 stale 정정**: 오너 승인 하에 `HANDOFF.md:103` Project Structure 주석 `(Approved, v1.6.57)` → `(Approved, v1.6.58)` 1행 정정(8행과 정합). 본 slice와 무관한 선재 stale로, 독립 정정.

**재검증**: 기본 sandbox(패키지 absent) `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → `704 passed / 48 skipped`(무변). `git diff --check` clean. Verdict **합격(PASS)** 유지 — 보강은 outstanding 항목 closure이며 기존 판정을 바꾸지 않음.
