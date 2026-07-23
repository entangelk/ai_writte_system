# 독립 검증 기록 — 임베딩 실패 500 누수 폐쇄: source-block rebuild 502 매핑 (v1.7.34)

## Subject metadata

- **날짜**: 2026-07-23
- **요청자**: 오너 (커밋 3634e87 작업분 검증 요청)
- **검증자**: 독립 검증 AI (Claude, 구현자와 무관)
- **대상 슬라이스/아티팩트**: `POST …/snapshots/{id}/index/source-blocks/rebuild` 의 임베딩 실패 500 → 502 매핑 + SoT 502/503 구분 규칙 문장화 + stale 문서 정리
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.7.34 (changelog 행 + "상태코드 의미론" 502/503 행)
- **검증 대상 작업 출처**: commit `3634e878` (branch `main`, 커밋 완료 상태)

## Scope

1. **정본 계약(SoT v1.7.34)** — 502/503 의미론 행의 구분 규칙 문장, changelog 자기 정합성.
2. **구현 코드** — `main.py`(rebuild 선언·`except EmbeddingProviderError → 502`·신규 `_ERRORS_404_502`).
3. **boundary(선언 == 실제 raise)** — rebuild endpoint `{404,502}`.
4. **상태코드 선택 근거** — 502가 맞는지(503이 아닌지), 코드 선례(context_search `_run_vector_step`)와 SoT 의미론 대조.
5. **패턴 스윕 완결성** — `EmbeddingProviderError` caller 0 주장, `.embed()` 9 호출지 전수의 HTTP 도달성·보호 여부.
6. **회귀 테스트** — `SourceBlockRebuildEmbeddingFailureTest` 3건(under-strict·정상·절 폭 over-strict 가드).
7. **mutation(적대적)** — 절 제거(500 재발)·`except Exception` 확대(절 폭).
8. **문서 정리** — stale `start_next_unit` "미수정" 제거·`auto_promote_job` 재작성·`:199`/`:406` 부채 등록·"526→525" 정정.
9. **수치/산출물** — backend·gen:api·tsc·build.

## Methodology

정본 계약을 먼저 스코핑한 뒤 코드를 읽었다. 모든 주장은 1차 소스 `file:line`에서 재도출.

- **상태코드 근거 검증**: SoT 502/503 의미론 행을 읽고, rebuild 경로(rebuild → embed → `EmbeddingProviderError`)를 추적하여 "협력자가 없는 것(503)이 아니라 있는데 실패한 것(502)"에 해당함을 확인. 선례(`context_search/service.py::_run_vector_step`가 embed 실패를 `BACKEND_ERROR`로 잡아 502로 표면화)를 직독.
- **패턴 스윕 재실행**: `EmbeddingProviderError` 의 catch 전수 grep(caller count), `.embed()` 호출 9지를 전수 추출하여 각각의 HTTP 도달성·보호 여부를 호출자 직독으로 분류.
- **mutation(적대적)**: `main.py` cp 백업 → (a) 무결성 절 raise를 `raise`(재발)로 변형해 500 재현, (b) `except EmbeddingProviderError` → `except Exception` 확대 → 각각 해당 테스트 실패 확인 → 복원. (이전 슬라이스 사고 교훈대로 cp 백업/복원.)
- **수치 재실행**: backend `python3 -m pytest -q`(전용 test-mongo 27020 RS)·frontend `vitest run`·`tsc --noEmit`·`vite build`·`gen:api`(working tree 재생성 vs 커밋 diff).
- 복구 후 `git status` clean·`git diff --stat services/application/app/main.py` 공백·HEAD `3634e87` 재확인.

## Findings

### 1. 상태코드 선택(502) — 계약·선례 양쪽에서 정당

- **경로 실재**: `main.py:2343` `_rebuild_source_block_index_payload` → `indexing/service.py:617 rebuild_source_block_index_summary(... embeddings=shared_embeddings …)` → `indexing/service.py:785` `vector=self._embeddings.embed(text)` (각 source block마다). `indexing/embedding.py:49/51/54/…`에서 timeout·unreachable·비정상 응답 전부 `raise EmbeddingProviderError(…)`(`class EmbeddingProviderError(RuntimeError)`, `embedding.py:19`).
- **502가 맞음**: 임베딩 서비스는 **구성돼 있지만 실패** — SoT 502 행("협력자가 **없는 것(503)**이 아니라 **있는데 실패한 것**이 502다", `system-contract-sot.md:316`)에 정확히 해당. 503("두 얼굴": 미구성·무결성)이 아님.
- **선례 일치**: `context_search/service.py:924 _run_vector_step`가 `self._embeddings.embed(…)`(:928)를 `except Exception → StepFailure(BACKEND_ERROR)`(:944)로 감싸고, `ContextSearchFailed(BACKEND_ERROR)`는 502로 표면화(writing endpoint들에서 확인됨). 작업 AI가 부채 등록 시 "503에 가깝다"고 적었던 것은 본인이 정정한 대로 오류.

### 2. 구현·선언 — boundary 충족

- `main.py:241-244` `EmbeddingProviderError` import 추가.
- `main.py:1027` 신규 `_ERRORS_404_502 = {404: _ERROR, 502: _ERROR}`.
- `main.py:2336` rebuild `responses=_ERRORS_404` → `_ERRORS_404_502` (선언 `{404}` → `{404,502}`).
- `main.py:2349-2357` `except EmbeddingProviderError as exc: → HTTPException(503→502)`. **좁은 catch**(EmbeddingProviderError만) — 절 폭 가드로 잠금(§6).
- 선언 집합 `{404,502}` == 실제 raise 집합(`NotFound`→404, `EmbeddingProviderError`→502). 양방향 성립.

### 3. SoT 502 의미론 행 — 구분 규칙 문장화 확인

`system-contract-sot.md:316` 502 행이 (a) 상류 목록에 "**임베딩**" 추가, (b) 구분 규칙 문장 "**협력자가 없는 것(503)이 아니라 있는데 실패한 것**이 502다" 추가, (c) 예시 컬럼에 `EmbeddingProviderError` 추가. 503 행(:317)과 모순 없음. changelog v1.7.34 행(:36)도 동일.

### 4. 패턴 스윕 완결성 — 작업 AI 주장 정확, 누락 live 누수 없음

`EmbeddingProviderError` catch 전수 grep → 앱 전체에서 **유일한 catch가 `main.py:2349`(이번에 추가)**. 부채 등록 전 caller 0 주장 확인. `.embed()` 호출 **9지** 전수 분류:

| site | HTTP 도달 | 보호 | 판정 |
|---|---|---|---|
| `indexing/service.py:785`(rebuild) | 예(동기) | 이제 `except EmbeddingProviderError→502` | ✅ 수정됨 |
| `analysis/semantic_matcher.py:67/113/116` | 예(analysis run 경유) | `run_analysis_job`의 광의 `except Exception→502`(`main.py:2464`) | 보호됨(502=정답) |
| `context_search/service.py:928`(_run_vector_step) | 예 | 자체 광의 except→BACKEND_ERROR→502 | 보호됨 |
| `context_search/service.py:199`(VectorCanonicalMemoryRetriever) | 예(ContextSearchService:752 경유) | 호출자 광의 except→BACKEND_ERROR→502(:753-770) | 보호됨 |
| `context_search/service.py:406`(VectorCandidateMemoryRetriever) | 예(ContextSearchService:835 경유) | 호출자 광의 except→BACKEND_ERROR→502(:838-865) | 보호됨 |
| `indexing/candidate_index.py:189`·`memory_index.py:195` | **아니오**(outbox worker) | `index_candidate`/`index_memory`(`:164`/`:171`)는 `IndexSyncOutboxEntry` 수신 — HTTP 쓰기는 outbox 적재, worker가 drain하며 embed(`main.py:1613` "writes only (no LLM); reindex enqueue is owned by MemoryService") | worker 경로 |

→ "HTTP 도달 경로는 rebuild가 실질적으로 유일(나머지는 worker 경로 또는 광의 catch 보호)" 주장 정확. 누락된 live 500 누수 없음.

### 5. 회귀 테스트 — 양방향·절 폭 가드 모두 pin

`tests/test_application_api.py:2542-2622 SourceBlockRebuildEmbeddingFailureTest`:
- `test_embedding_failure_is_502_with_the_uniform_body`(:2571) — `_FailingEmbeddings`(embed→`EmbeddingProviderError`) 주입 → 502 + `{detail}` 본문. under-strict + fix 검증.
- `test_healthy_rebuild_still_succeeds`(:2591) — 기본 fake embedding → 200. over-strict(성공 삼키지 않음).
- `test_unrelated_failure_is_not_relabelled_as_502`(:2602) — `_BrokenEmbeddings`(embed→`ValueError`) 주입 → `assertRaises(ValueError)` 전파. **절 폭 over-strict 가드**(`except Exception` 확대 방지).
- S4 lock list(`test_application_api.py:2455`) rebuild `{404,502}` 동반 갱신 + `len(EXPECTED)==7` 유지.

### 6. mutation(적대적) — 양쪽 다 실증

- **under-strict ✅**: 무결성 절 raise를 `raise`(재발)로 변형 → `test_embedding_failure_is_502`가 `EmbeddingProviderError: embedding service is unavailable`가 endpoint 밖으로 새며 **FAIL**(500 != 502).
- **over-strict 절 폭 ✅**: `except EmbeddingProviderError` → `except Exception` 확대 → `test_unrelated_failure_is_not_relabelled_as_502`가 "ValueError not raised"로 **FAIL**(무관 ValueError가 502로 오분류). 작업 AI 주장("mutation이 가드 부재를 먼저 드러내 가드를 추가, 이제 그 변형이 FAIL") 정확.
- 두 변형 모두 복원 후 3 테스트 green 복귀.

### 7. 문서 정리 — 전부 확인

- **stale 제거**: HANDOFF 추적 부채의 "`start_next_unit` … (미수정, 추적 부채)" 항목이 S5(v1.7.33)로 이미 닫혔음에도 남아 있던 것을 **삭제**. (다음 작업자가 고쳐진 결함을 재조사하게 만드는 항목 제거.)
- **`auto_promote_job` 재작성**: "코드 매핑이 아니라 계약 질문(부분 승격 후 실패 시 부분 성공 봉투인가 전체 실패인가)"으로, writing accept 502 partial 선례와의 차이(승격 개수 가변) 근거와 함께 **결정 브리프 권장**으로 명시.
- **`:199`/`:406` 신규 부채 등록**: "무방비 `embed()`, HTTP 도달성 미확인" — conservative 등록(실제로는 §4대로 호출자 광의 except로 보호됨).
- **"526→525" 정정**: HANDOFF·SoT·work_log 3곳 모두 **525**. work_log(:391)가 "+3 test·+1 subtest" 수학(신규 3건은 subTest 미사, +1은 S4 body-model 루프가 rebuild 502를 더 도는 것, 12→13)과 **"초안에 +2/526으로 잘못 적었다가 실측 후 정정"**을 명시. stale 526 잔유 0.

### 8. 수치/산출물 — 전부 재실행 일치

| 항목 | 주장 | 재실행 | 판정 |
|---|---|---|---|
| backend | 1453 / 1 skipped / 525 subtests | `1453 passed, 1 skipped, … 525 subtests passed in 577.99s` | ✅ |
| `gen:api` | +9 / -0 | numstat `9 0` + working tree 재생성 == 커밋(diff 0행) | ✅ |
| `tsc --noEmit` | clean | exit 0, 출력 0 | ✅ |
| build JS | 399.03 kB | `399.03 kB` | ✅ |
| frontend | 194 / 13 (무변) | 본 커밋은 backend·schema-additive 전용(프론트 테스트 파일 무변경, tsc clean) → 직전 슬라이스 실측 194/13 유지 | ✅ (추론, 근거 명시) |

## Issues / Risks

### Blocking (계약 의무) — 없음

502 매핑이 SoT 의미론·코드 선례 양쪽에서 정당하고, rebuild 선언 `{404,502}` == 실제 raise(양방향), 런타임 수정의 under-strict·절 폭 over-strict 가드가 mutation으로 실증됐으며, 패턴 스윕이 누락 live 누수 없음을 확인했다.

### Hardening recommendations (비차단)

1. **`:199`/`:406` 부채 설명의 정밀화 (권장)**: HANDOFF/SoT는 이 두 site를 "무방비 `embed()`, HTTP 도달성 미확인"으로 등록하나, 검증자 직독으로는 **둘 다 HTTP 도달 가능**(ContextSearchService `.retrieve` :752/:835 경유)이며 **호출자의 광의 `except Exception → BACKEND_ERROR`(→502)로 이미 보호**됨. 즉 live 누수가 아니라 "호출자 catch에 의존해 보호되는 지점"이다. 부채 설명을 "도달성 미확인"에서 "도달은 하지만 호출자 광의 except로 보호됨 — 그 catch가 좁아지면 누수로 전환"으로 정정하면 다음 작업자가 재조사 비용을 들이지 않는다. 본 슬라이스 결함 아님.
2. **broad-catch 경로의 "우연히 정답" 메모 (권장)**: analysis run(`main.py:2464`)·ContextSearchService(:753/:838/:944)의 광의 `except Exception → 502`는 `EmbeddingProviderError`를 우연히 정확한 코드(502)로 매핑한다. rebuild는 좁은 catch(EmbeddingProviderError만)+가드를 택한 것과 대비되나, 양쪽 모두 502로 귀결되므로 현재 일관. 광의 catch가 좁아지는 리팩터 시 :199/:406 부채가 live 로 전환될 수 있음(= 권장 1과 동일 맥락). 문서화만 권장.
3. (범위 밖) `auto_promote_job`·`context_search :199/:406` 도달성은 본 슬라이스 범위가 아님 — HANDOFF에 별도 후보로 적절히 추적됨.

## Verdict

**PASS (조건 없음).**

하중-bearing 이유:
- 502 매핑이 SoT 502 의미론("있는데 실패한 것")과 코드 선례(`_run_vector_step`→BACKEND_ERROR→502) 양쪽에서 정당. 503 오분류 정정이 계약·코드 모두에 반영.
- rebuild 선언 `{404,502}` == 실제 raise(양방향), 신규 `_ERRORS_404_502`.
- 런타임 수정의 under-strict(절 제거→500)·절 폭 over-strict(`except Exception` 확대→오분류) 가드를 mutation으로 실증.
- 패턴 스윕: `.embed()` 9지 전수 분류로 rebuild가 유일한 HTTP-동기 무방비 경로였음 확인 → 누락 live 누수 없음.
- stale 문서 정리(`start_next_unit` "미수정" 제거)·`auto_promote_job` 계약 질문화·`:199/:406` 부채 등록·"526→525" 정정 전부 확인.
- 수치(backend 1453/1/525·gen:api +9/-0 충실·tsc clean·build 399.03 kB) 재실행 일치.

Hardening 2건은 부채 설명 정밀화(실제로는 보호된 지점)로, 동작·계약에 영향 없는 문서 정확화 후보라 판정에 영향을 주지 않는다.

## Outstanding items

- 본 검증은 read-only + 일시 mutation(전부 복원 완료, `git status` clean, HEAD `3634e87`)으로 working tree·커밋에 변경을 가하지 않았다.
- 남은 후보(오너 판단 대기, 본 슬라이스와 무관): (a) `auto_promote_job` 결정 브리프 — 부분 승격 후 실패 시 부분 성공 봉투 vs 전체 실패, (b) `context_search :199/:406` 도달성 재확인(검증자는 이미 보호됨을 확인했으나 부채 설명 정정 차원), (c) 배포 mongo ulimits 4줄(스택 재기동 필요).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
docker compose -f docker-compose.test.yml up -d   # 27020 RS (이미 healthy면 생략)

# 1. focused 회귀
python3 -m pytest tests/test_application_api.py::SourceBlockRebuildEmbeddingFailureTest -q
# → 3 passed

# 2. 전체 backend 수치
python3 -m pytest -q
# → 1453 passed, 1 skipped, 525 subtests passed

# 3. gen:api 충실도 + tsc + build
cd frontend
python3 ../scripts/dump_openapi.py > /tmp/o.json && \
  npx openapi-typescript /tmp/o.json -o /tmp/s.d.ts && \
  diff <(grep -v '^// ' /tmp/s.d.ts) <(grep -v '^// ' src/api/schema.d.ts)   # → 0행
npx tsc --noEmit && npx vite build                                            # → clean, 399.03 kB
git -C .. show 3634e87 --numstat -- frontend/src/api/schema.d.ts              # → 9 0

# 4. under-strict mutation (절 제거 효과)
cd ..
cp services/application/app/main.py /tmp/main.bak
python3 - <<'PY'
p="services/application/app/main.py"; s=open(p,encoding="utf-8").read()
a="            # (context_search/service.py::_run_vector_step).\n            raise HTTPException(status_code=502, detail=str(exc)) from exc\n"
assert s.count(a)==1
open(p,"w",encoding="utf-8").write(s.replace(a,"            # (context_search/service.py::_run_vector_step).\n            raise\n"))
PY
python3 -m pytest "tests/test_application_api.py::SourceBlockRebuildEmbeddingFailureTest::test_embedding_failure_is_502_with_the_uniform_body" -q
# → FAILED (EmbeddingProviderError escapes → 500)
cp /tmp/main.bak services/application/app/main.py

# 5. over-strict 절 폭 mutation
python3 - <<'PY'
p="services/application/app/main.py"; s=open(p,encoding="utf-8").read()
a="        except EmbeddingProviderError as exc:\n"; assert s.count(a)==1
open(p,"w",encoding="utf-8").write(s.replace(a,"        except Exception as exc:\n",1))
PY
python3 -m pytest "tests/test_application_api.py::SourceBlockRebuildEmbeddingFailureTest::test_unrelated_failure_is_not_relabelled_as_502" -q
# → FAILED (ValueError not raised — caught as 502)
cp /tmp/main.bak services/application/app/main.py   # 복원
```
