# Verification — Phase 4 real vector 백엔드 B.5 deployed live smoke

## Subject metadata

- **Date**: 2026-07-05
- **Requester**: 오너("클로드 작업 AI가 작업한 부분 확인하고 검증하고 의심하고 또 의심해줄래? B.5까지 끝냈습니다.")
- **Verifier**: 독립 검증 AI(Claude, 회의적 재검증)
- **Target slice/artifact**: Phase 4 real 영속 vector 백엔드 B.5(deployed live smoke) + B.5 진행 중 발견한 Chroma adapter numpy-like truthiness bug 수정
- **Canonical spec reference**:
  - `docs/plans/04-real-vector-backend-decisions.md` §B.5(line 105-106, 수용 기준), §6(line 84, 계약 표면), line 14(`backend="chroma"` literal / dimension 1024 / stale-guard 불변 / worker→Chroma mutation 후속)
  - `docs/system-contract-sot.md` v1.6.36(line 36 changelog, line 368 rebuild `backend` enum)
- **Source of work being verified**: working tree, uncommitted(`git status` — `services/application/app/indexing/chroma.py`, `tests/test_chroma_adapter.py`, `HANDOFF.md`, `CHANGELOG.md`, `docs/daily_logs/2026-07-05/work_log.md` modified). 마지막 커밋 `3fbeaf4`. live runtime: `docker compose -f docker-compose.yml -f docker-compose.llama.yml` stack(mongo/gateway/llama/embedding/chroma/application).

## Scope

1. **Canonical contract(B.5)**: 브리프 §B.5 수용 기준 + §6 계약 표면 + SoT v1.6.36이 요구하는 boundary.
2. **Implementation code**: `services/application/app/indexing/chroma.py`의 `_records_from_get`/`_records_from_query` numpy-like truthiness 수정.
3. **Regression tests**: `tests/test_chroma_adapter.py`에 추가된 numpy-like 회귀 2개(under-strict / over-strict guard).
4. **Pattern sweep**: 동일 root-cause(`result.get(...) or ...`)가 다른 곳에 존재하는지.
5. **Deployed live smoke**: `scripts/phase4_context_search_deployed_smoke.py` 전체 stack 관통 결과.
6. **재시작 생존**: application process restart 후 rebuild 없이 `/context-search`가 Chroma persistent volume hit을 서빙하는지.
7. **문서 정합**: HANDOFF / work_log / CHANGELOG가 실제 결과와 일치하는지.

## Methodology

> sandbox에서 `127.0.0.1:8000`으로 노출된 compose stack에 직접 접근 가능했으므로, live smoke와 restart 생존 검증을 **실제로 재실행**했다(모든 claim을 work_log 인용이 아니라 1차 산출물에서 재도출).

### 정적/단위 검증

- `git diff HEAD -- services/application/app/indexing/chroma.py tests/test_chroma_adapter.py` — 수정 범위와 정확한 diff.
- `grep -rn "result.get(\"embeddings\")...\|or \[None\] \* len" services/ scripts/` — 동일 root-cause sweep.
- `python3 -m unittest tests.test_chroma_adapter tests.test_phase4_context_search_deployed_smoke_script -v` — 사용자 주장 회귀 결과 재현.
- **Mutation(under-strict guard non-vacuity)**: 백업 후 `_records_from_get`만 원래 `or` 패턴으로 되돌려 테스트 실행 → 복원. 다시 `_records_from_query`만 되돌려 테스트 실행 → 복원. 각 mutation이 정확히 해당 회귀만 재실패시키는지, 복원이 `git diff`로 byte-clean인지 확인.
- `git diff HEAD -- services/application/app/indexing/chroma.py` — 복원 후 B.5 수정만 남았는지.

### Live 검증(실제 compose stack)

- `docker compose -f docker-compose.yml -f docker-compose.llama.yml ps` — 6 컨테이너 healthy.
- `docker exec ai_writte_system-application-1 env | grep -E 'CHROMA|EMBEDDING|LLAMA|GATEWAY|MONGO'` — application 컨테이너 실제 wiring env.
- `curl -sS -X POST http://127.0.0.1:8002/embed -d '{"text":"아린"}'` — 실제 embedding dimensions 직접 probe(B.5 수용 기준 "실제 1024-dim").
- `python3 scripts/phase4_context_search_deployed_smoke.py --application-base-url http://127.0.0.1:8000 --timeout-seconds 900` — deployed smoke 재실행.
- `docker compose ... restart application` + health poll → rebuild **없이** smoke가 만든 동일 project로 `POST /projects/{id}/context-search`를 `curl`로 직접 호출(request body는 `scripts/phase4_context_search_deployed_smoke.py:104-109`와 동일) → `micro_evidence` 수와 `trace.steps`(vector tool hits)로 Chroma persistent 생존 확인.
- `docker logs ai_writte_system-application-1` — rebuild 500/`ValueError`/`ambiguous` 부재 확인.

## Findings

### 1. Canonical contract — 브리프 §B.5 / §6 / SoT v1.6.36

- `docs/plans/04-real-vector-backend-decisions.md:105-106`: B.5는 "확장된 deployed smoke(rebuild→search)를 real Chroma + embedding 서비스 + 실제 12B planner 관통으로 실행. 재시작에도 vector hit 생존 확인." 수용 기준은 "실제 `dragonkue/BGE-m3-ko`를 관통해 embedding 벡터가 **실제 1024-dim**임을 assert하고, Chroma가 그 벡터를 저장·query해 hit를 낸다는 것까지 확인".
- `docs/plans/04-real-vector-backend-decisions.md:84` (§6): real adapter wiring 시 rebuild summary `backend`는 `chroma`, fake는 `in_memory_fake`.
- `docs/system-contract-sot.md:36` (v1.6.36 changelog): "`backend` literal enum에 `chroma`가 추가됐다. ... 실제 Chroma 서버/embedding 모델 관통(1024-dim assert, 재시작 vector hit 생존)은 B.5 live 검증이다."
- `docs/system-contract-sot.md:368`: rebuild `backend`는 wiring에 따라 `chroma`(`CHROMA_HOST` 설정 시) 또는 `in_memory_fake`.
- **계약 자체 모순 없음**. §B.5 수용 기준 ↔ §6 backend literal ↔ SoT v1.6.36 changelog ↔ SoT line 368이 일관. 브리프 line 14("stale-guard 불변")도 SoT v1.6.36("stale guard는 backend 무관하게 SOT를 재조회")과 일치.

### 2. Implementation code — chroma.py numpy-like truthiness 수정

- `services/application/app/indexing/chroma.py:164-175` (`_records_from_get`): `embeddings = result.get("embeddings") or [None] * len(ids)` / `metadatas = result.get("metadatas") or []` → `is None` 체크로 변경. real Chroma client가 embeddings를 numpy array-like로 반환할 때 `or`의 truthiness 평가가 `ValueError: The truth value of an array with more than one element is ambiguous`를 일으키던 결함의 수정.
- `services/application/app/indexing/chroma.py:178-194` (`_records_from_query`): 동일 root-cause. `(result.get("embeddings") or [[None] * len(ids)])[0]` → `embeddings_by_query` 변수 + `is None` 체크.
- 수정은 **minimal하고 surgical**하다 — truthiness 평가만 `is None`으로 바꾸고, fallback 값(`[None] * len(ids)` / `[]`)은 동일. 단순성 원칙 위반 없음.
- `record_from_chroma`(`chroma.py:75-96`)는 embedding이 `None`일 수 없다(`tuple(float(v) for v in embedding)`). 단, `_INCLUDE = ["embeddings", "metadatas"]`(`chroma.py:114`)로 항상 embeddings를 요청하므로 None fallback은 도달 불가능한 방어 경로 — 기존 동작과 동일, regression 아님.

### 3. Regression tests — under-strict / over-strict guard

- `tests/test_chroma_adapter.py:30-34`: `AmbiguousTruthValueList(list)` — `__bool__`이 `ValueError`를 raise해 real Chroma client의 numpy array-like truthiness 동작을 모방. list를 상속해 iterable은 정상, truthiness 평가만 막힘 → 정확히 real Chroma의 embeddings 반환 타입 특성 재현.
- `tests/test_chroma_adapter.py:188-194` (`test_list_records_accepts_chroma_numpy_like_embeddings`): `ambiguous_embeddings=True` fake collection에서 `list_records`가 `["a"]` / vector `(1.0, 0.0)`을 올림.
- `tests/test_chroma_adapter.py:247-256` (`test_query_similar_accepts_chroma_numpy_like_embeddings`): 동일하게 `query_similar` 경로.
- `FakeChromaCollection.ambiguous_embeddings` 플래그(`test_chroma_adapter.py:76, 102-106, 127-131`)가 get/query 양쪽 `embeddings` 반환값을 `AmbiguousTruthValueList`로 감싸도록 주입 — 회귀가 실제 결함 조건을 정확히 재현.
- **Over-strict guard**: 기존 11개 회귀(정상 list embeddings)가 동일 파일에서 통과 — `is None` 수정이 정상 케이스를 깨지 않음.
- **Under-strict guard(non-vacuity) — 직접 mutation 실증**:
  - `_records_from_get`만 원래 `or`로 되돌림 → `test_list_records_accepts_chroma_numpy_like_embeddings` **정확히 `ValueError: ambiguous truth value`로 재실패**(`chroma.py:166`에서 `result.get("embeddings") or ...` 평가). query 회귀는 통과 유지.
  - `_records_from_query`만 원래 `or`로 되돌림 → `test_query_similar_accepts_chroma_numpy_like_embeddings` **정확히 동일 `ValueError`로 재실패**(`chroma.py:183`). list 회귀는 통과 유지.
  - 백업 복원 후 `git diff HEAD -- chroma.py`는 B.5 수정만 표시(14 insertions, 4 deletions) — mutation이 깨끗이 제거됨(byte-clean).

### 4. Pattern sweep — 같은 root-cause

- `grep -rn "result.get(\"embeddings\")\|\.get(\"embeddings\") or\|or \[None\] \* len" services/ scripts/` → `chroma.py` 내 2곳(수정된 `_records_from_get`/`_records_from_query`)만. 다른 파일에 동일 패턴 없음.
- **관찰(비차단, 아래 Issues 참조)**: `chroma.py:165` `ids = result.get("ids") or []`와 `chroma.py:182` `ids = (result.get("ids") or [[]])[0]`는 여전히 `or` 평가를 쓴다. real Chroma Python SDK는 ids를 plain `list[str]`로 반환하므로 truthiness는 안전하지만, embeddings가 numpy-like였던 것과 같은 맥락이라 boundary 관점에서 명시적 언급이 필요하다.

### 5. Deployed live smoke — 실제 재실행

- application 컨테이너 env(`docker exec ... env`): `CHROMA_HOST=chroma`, `CHROMA_PORT=8000`, `EMBEDDING_SERVICE_URL=http://embedding:8002`, `EMBEDDING_DIMENSIONS=1024`, `LLM_GATEWAY_BASE_URL=http://gateway:8001` → B.4 wiring이 실제 runtime에 적용됨.
- `curl POST /embed {"text":"아린"}` → `dimensions=1024`, `len(embedding)=1024`(first3 실수 벡터). 브리프 §B.5 수용 기준 "실제 1024-dim" 충족.
- `python3 scripts/phase4_context_search_deployed_smoke.py --application-base-url http://127.0.0.1:8000 --timeout-seconds 900` → **EXIT=0**, 결과:
  - `rebuild_http_status=200`, `rebuild_backend="chroma"`, `rebuild_records_written=6`
  - `search_http_status=200`, `gate_decision="pass"`, `degraded=false`
  - `macro_count=2`(current_scene → mongo), `micro_count=6`(source_quote → vector)
  - `plan_steps`: `[(current_scene,[mongo]),(source_quote,[vector])]` — 실제 12B planner가 정확한 plan 생성
  - `trace.steps`에서 `source_quote` step이 `tool="vector"`, `hits_considered=6`, `items_produced=6` → Chroma vector hit가 실제 발생
  - 모든 `micro_evidence`가 `sot_reloaded=true`, `status="canonical"` → vector hit가 stale guard + SOT 재조회를 통과(SoT v1.6.36 "stale guard는 backend 무관" 계약 충족)
- `smoke_succeeded` 게이트(`scripts/phase4_context_search_deployed_smoke.py:153-156`): `rebuild_http_status==200 AND search_http_status==200` — 두 status 모두에 걸림. 사용자가 주장한 envelope 숫자를 독립 재도출해 **정확히 일치**.
- application 로그에 `ValueError`/`ambiguous`/rebuild 500 부재 — 수정이 live runtime에 반영됨. (`docker logs`에서 rebuild `POST .../rebuild HTTP/1.1 200 OK` 확인.)

### 6. 재시작 생존 — 실제 재실행(B.5 핵심 claim)

- `docker compose ... restart application` → `Up 6 seconds (healthy)`(chroma/mongo는 26분+ 유지, restart와 무관 → persistent volume 보존 증거).
- rebuild **없이** smoke가 만든 동일 project(`6a49cf9d6a0d59e2a5e3430e`)로 `/context-search`를 `curl` 직접 호출 → 결과:
  - `gate_decision=pass`, `degraded=False`, `macro_count=2`, **`micro_count=6` 유지**
  - `plan_steps` 동일: `current_scene→mongo`, `source_quote→vector`
  - `trace.steps`: `source_quote` step `tool="vector"`, `hits_considered=6`, `items_produced=6` → application process restart 후에도 **Chroma persistent volume의 vector가 재조회**됨
  - 모든 `micro_evidence` `sot_reloaded=True`, `status=canonical`
- 이것은 in-memory fake(shared index, SoT v1.6.35 — restart 시 소실)와 real Chroma(SoT v1.6.36 — 재시작 생존)의 **결정적 차이**를 live로 증명한다. fake였다면 restart 후 micro 0이어야 한다.

### 7. 문서 정합

- `docs/daily_logs/2026-07-05/work_log.md:57-67`(B.5 section), `:90-93`(Issues — numpy-like bug cause/resolution/outcome), `:136`(Verification) — 실제 결과와 일치(`rebuild_backend="chroma"`, `records_written=6`, `gate=pass`, `micro_count=6`, restart 후 6 유지).
- `HANDOFF.md:118`(Current Status B.5), `:139`(Verification), `:129`(Next Tasks — embedding image size/startup 최적화, worker→real Chroma mutation 배선 후속) — actionable 상태로 정합.
- `CHANGELOG.md` 최상단 B.5 행 — "real embedding + Chroma + 실제 12B planner 관통, `backend='chroma'` rebuild와 vector hit, application 재시작 후 hit 생존 확인" — 실제 결과와 일치.
- work_log에 "embedding image CPU-only/경량화" 후속 후보 명시(`:67`, `:141`) — Docker Compose bake panic → `COMPOSE_BAKE=false` 우회도 Issues에 기록(`:93`). 이 두 운영 관찰은 코드 결함이 아니라 후속 후보로 정확히 분류됨.

## Issues / Risks

- **관찰 O1(비차단, contract gap 후보)**: `chroma.py:165`(`ids = result.get("ids") or []`), `chroma.py:182`(`ids = (result.get("ids") or [[]])[0]`)는 embeddings와 같은 `or` truthiness 패턴을 여전히 쓴다. real Chroma 0.5.23 Python SDK는 ids를 plain `list[str]`로 반환하므로 현재 runtime에서는 안전(직접 smoke/restart 검증으로 200/hit 확인). 그러나 embeddings가 numpy-like였던 사실은 "Chroma client 반환 컨테이너 타입이 plain list라는 가정"이 항상 성립하지 않음을 보여준다. **권고**: 동일한 "Chroma client가 numpy-like를 반환할 수 있다" 전제 아래 ids/metadatas 경로도 `is None`으로 통일하거나, 최소한 회귀 `AmbiguousTruthValueList`를 ids/metadatas 반환값에도 주입해 두 경로의 안전성을 명시적으로 lock하는 것이 일관적이다. 단, 현재 결함이 아니므로 차단 사유는 아니다.
- **관찰 O2(비차단)**: 재시작 vector hit 생존 검증은 committed regression이 아니라 live 수동 검증이다. 브리프 §B.5가 "LLM 환경 전용 live smoke"로 명시했으므로 acceptable이지만, real Chroma의 영속성을 CI에서 반복 검증할 surface는 없다(B.3의 `ChromaAdapterLiveTest`는 `CHROMA_TEST_URL`+`chromadb` 설치 시 skip-aware로 upsert/query/restart-survival을 잠그지만, host 환경 미충족으로 기본 skip). 후속으로 live regression 격리 환경을 두면 재현성이 올라간다.
- **관찰 O3(비차단)**: embedding 서비스 로그에서 `dragonkue/BGE-m3-ko` 모델 로드 라인이 `grep`에 잡히지 않았다(로깅 레벨/형식 추정). 단, `/embed`가 실수 1024-dim 벡터를 반환하므로 실제 모델 로드는 확정이며, 이는 검증 결함이 아니라 로깅 표면의 가시성 문제다.

## Verdict

**합격(조건 없음)**.

가장 중요한 claim 세 가지를 독립 재실행으로 1차 산출물에서 재도출해 모두 확인했다:

1. **`backend="chroma"` real 영속 경로 관통** — smoke 재실행 EXIT=0, `rebuild_backend="chroma"`/`records_written=6`/`micro_count=6`/`gate=pass`, `source_quote` step이 실제 `tool=vector`로 `hits_considered=6, items_produced=6`, 모든 hit `sot_reloaded=true`+`canonical`.
2. **실제 1024-dim embedding** — `curl /embed` 직접 probe `dimensions=1024`, `len=1024`.
3. **재시작 vector hit 생존** — application restart 후 rebuild 없이 동일 project `/context-search` → `micro_count=6` 유지, `source_quote` vector hit 6개 재조회. 이는 v1.6.35 in-memory fake(restart 시 소실)와의 결정적 차이.

Chroma adapter numpy-like truthiness bug 수정은 mutation 양방향 실증으로 non-vacuous임을 증명했다(get mutation → list 회귀 재실패, query mutation → query 회귀 재실패, 각각 정확히 해당 테스트만, 복원 byte-clean). boundary matrix에 빈 cell 없다. 문서(HANDOFF/work_log/CHANGELOG)가 실제 결과와 정합하다.

비차단 관찰 O1(ids/metadatas의 잔존 `or` 패턴), O2(restart 생존 committed regression 부재), O3(embedding 로그 가시성)은 차단 사유가 아니며 후속 후보로 기록한다.

## Outstanding items

- **Uncommitted working tree**: B.5 수정(chroma.py, test_chroma_adapter.py) + 문서(HANDOFF, CHANGELOG, work_log)가 아직 커밋되지 않았다. 오너가 커밋을 승인하면 별도 커밋으로 마무리한다.
- **Live stack 유지**: compose 6 컨테이너가 현재 healthy로 떠 있다. 검증 중 application을 1회 restart했고(재시작 생존 검증용), 그 외 영구 변경 없음. 재시작 검증용으로 만든 project(`6a49cf9d6a0d59e2a5e3430e`)가 Chroma volume에 남아 있다(검증 부산물).
- **후속 후보(브리프 범위 밖, work_log/HANDOFF에 이미 추적)**: embedding service image size/startup 최적화(CPU-only torch pin), worker→real Chroma archive mutation 배선, ES lexical 경로.

## Reproduction

```bash
# 1. 단위 회귀 + smoke script 회귀
python3 -m unittest tests.test_chroma_adapter tests.test_phase4_context_search_deployed_smoke_script -v
# 기대: 18 passed + 1 skipped

# 2. under-strict mutation(non-vacuity) — _records_from_get만 원래 or로
cp services/application/app/indexing/chroma.py /tmp/chroma.py.bak
# (chroma.py:166-171을 `embeddings = result.get("embeddings") or [None] * len(ids)` / `metadatas = result.get("metadatas") or []`로 되돌림)
python3 -m unittest tests.test_chroma_adapter.ChromaAdapterLogicTest.test_list_records_accepts_chroma_numpy_like_embeddings -v
# 기대: ERROR ValueError: ambiguous truth value
cp /tmp/chroma.py.bak services/application/app/indexing/chroma.py

# 3. under-strict mutation — _records_from_query만 원래 or로
# (chroma.py:183-190을 `embeddings = (result.get("embeddings") or [[None] * len(ids)])[0]` / `metadatas = (result.get("metadatas") or [[]])[0]`로 되돌림)
python3 -m unittest tests.test_chroma_adapter.ChromaAdapterLogicTest.test_query_similar_accepts_chroma_numpy_like_embeddings -v
# 기대: ERROR ValueError: ambiguous truth value
cp /tmp/chroma.py.bak services/application/app/indexing/chroma.py

# 4. live: 실제 1024-dim embedding
curl -sS -X POST http://127.0.0.1:8002/embed -H 'Content-Type: application/json' -d '{"text":"아린"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['dimensions'], len(d['embedding']))"
# 기대: 1024 1024

# 5. live: deployed smoke
python3 scripts/phase4_context_search_deployed_smoke.py --application-base-url http://127.0.0.1:8000 --timeout-seconds 900
# 기대: exit 0, rebuild_backend="chroma", rebuild_records_written=6, micro_count=6, gate_decision="pass"

# 6. live: 재시작 생존
docker compose -f docker-compose.yml -f docker-compose.llama.yml restart application
# (healthy 대기 후, smoke가 만든 project_id로 rebuild 없이 /context-search 직접 호출)
# 기대: micro_count=6 유지, source_quote step tool=vector hits_considered=6
```
