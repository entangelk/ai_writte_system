# Verification — Phase 4 B.4 real vector backend wiring (commit 7ad90ef, SoT v1.6.36)

## Subject metadata

- 검증일: 2026-07-05
- 요청자: owner ("다음작업 검증해줘. B.4를 완료·커밋했습니다(7ad90ef, SoT v1.6.36). … B의 코어 완성 — 남은 건 B.5 (live 검증) … B.5는 제가 이 sandbox에서 실행할 수 없습니다")
- 검증자: 독립 검증 AI(Claude, 작업 AI와 다른 세션; `shared_vector_index_slice.md`, `deployed_smoke_rebuild_first.md`, `real_vector_backend_brief_b1_embedding_seam.md`, `b2_embedding_service_container.md`, `b3_chroma_persistent_adapter.md`에 이어 동일 세션)
- 대상 slice/artifact: commit `7ad90ef` "B.4: wire real Chroma + embedding backend into create_app (SoT v1.6.36)" — `services/application/app/main.py`(`_build_embedding_provider`/`_build_chroma_vector_index`/`create_app` env 기반 wiring +70), `services/application/app/indexing/service.py`(`CHROMA_VECTOR_BACKEND` literal +1), `services/application/app/indexing/models.py`(`IndexSyncBackend.CHROMA` +1), `docker-compose.yml`(application env + depends_on +11), `docs/system-contract-sot.md`(v1.6.35→v1.6.36, +9), `tests/test_real_vector_backend_wiring.py`(신규 회귀 7개 159행).
- 정본 계약 참조:
  - `docs/plans/04-real-vector-backend-decisions.md`(상태 `Approved (2026-07-05)`) — sub-slice **B.4**(line 103) "create_app이 env 기반으로 RemoteEmbeddingProvider + Chroma adapter를 기본 wiring(미구성 시 fake 유지). rebuild summary backend='chroma', dimension 1024, stale-guard 통합. rebuild write → context-search vector read가 real Chroma+real embedding에서 hit"; **B.4 수용기준**(line 104, B.2 검증 후속) "RemoteEmbeddingProvider를 expected_dimensions=1024로 구성해, embedding 서비스가 다른 차원을 내면 배포 런타임에서 EmbeddingProviderError로 즉시 잡는다. env로 dimension 조정 가능하되 기본은 1024"; §6 계약 표면(`backend` literal `chroma` 추가).
  - 선행: B.1 `services/application/app/indexing/embedding.py`(`RemoteEmbeddingProvider._expected_dimensions`/차원 guard line 36/79-84), B.2 `services/embedding/`, B.3 `services/application/app/indexing/chroma.py`(`ChromaVectorIndexAdapter`/`connect_chroma_collection`).
  - stale guard 원천: `services/application/app/context_search/service.py:246`(query_similar) → `:272`(`validate_source_block_record`) → `:315`(`core_sot.get_snapshot` SOT 재조회); `services/application/app/indexing/service.py:564`(`validate_source_block_record` 정의, stale reason literal 집합).
  - 직전 B.3 검증 `docs/verifications/2026-07-05/b3_chroma_persistent_adapter.md` §Verdict(조건부 합격 — query_similar 빈 cell 2개) + §Outstanding.
  - `docs/system-contract-sot.md` v1.6.36 changelog + rebuild endpoint 계약 갱신 + Phase 4 §"v1.6.36 승격" 문단.
- 검증 대상 작업 출처: branch `phase4-slice-4-2-planner` HEAD(`7ad90ef`), working tree clean.

## Scope

1. **env 기반 wiring 분기** — `_build_embedding_provider`(EMBEDDING_SERVICE_URL → remote 1024 / fake), `_build_chroma_vector_index`(CHROMA_HOST → Chroma / None), `create_app`(vector_index 주입 / chroma / fake 3분기, backend label follow).
2. **1024-dim guard armed (B.2 수용기준)** — remote provider가 `expected_dimensions=1024`로 구성되는지, env override 가능하되 기본 1024인지.
3. **stale guard 통합 주장 (핵심)** — "shared vector_index가 양쪽(vector_search + indexing_service)으로 wiring → Chroma hit도 SOT 재조회 후에만 ContextItem"이라는 작업자 주장이 코드로 참인지. 새 코드 없이 구조적으로 보장되는지.
4. **backend literal / enum 계약** — `CHROMA_VECTOR_BACKEND="chroma"` 상수, `IndexSyncBackend.CHROMA`, rebuild summary `backend` literal, SoT v1.6.36 반영 정합.
5. **compose wiring** — application 서비스 embedding/chroma env + depends_on: service_healthy.
6. **회귀 유효성 (mutation testing)** — 7개 회귀(4 builder + 3 literal)가 vacuous하지 않은지 under-strict 가드 증명.
7. **B.3 조건부 합격 사유 승계 확인** — B.4가 B.3의 query_similar 빈 cell 2개를 보강했는지.
8. **suite 카운트 독립 재현**(506 OK / 45 skip, pytest 461 / 45 skip).

## Methodology

- 계약 스코프: 브리프 B.4 + B.4 수용기준(line 104) + §6 + stale guard 원천(context_search/indexing service.py 직독) + SoT v1.6.36 changelog만 종단 독해. B.5(live)는 스코프 밖.
- boundary matrix 구축 후 7개 회귀의 assertion을 cell에 수동 매핑.
- **stale guard 추적(핵심)**: `query_similar` 반환값이 ContextItem이 되기까지의 경로를 `context_search/service.py` line 246→272→310-315→405 직독으로 추적. `validate_source_block_record`가 `vector_index`가 아니라 `core_sot` 기반으로 동작하는지, 그래서 Chroma/fake 무관한지 확인.
- **경험적 mutation testing**(핵심): `main.py`를 `/tmp`에 cp 백업 → 특정 분기/literal 치환 → B.4 회귀 재실행 → re-fail(가드 존재) 판정 → cp 복원 → `diff -q`로 byte-identical. 3개 mutation:
  1. `_build_embedding_provider` 기본 `"1024"` → `"999"` → 1024 guard 회귀 re-fail?
  2. `create_app`의 `shared_backend = CHROMA_VECTOR_BACKEND` → `FAKE_VECTOR_BACKEND` → backend literal 회귀 re-fail?
  3. `_build_chroma_vector_index` 항상 `return None` → chroma 분기 회귀 re-fail?
- B.3 승계 확인: `git show 7ad90ef --name-only | grep chroma`로 chroma.py/test_chroma_adapter.py 미수정 확인 + `git show 7ad90ef -- tests/test_chroma_adapter.py` 빈 확인.
- literal 일관성: `service.py`/`models.py`/`main.py`/SoT 간 `chroma` literal 직독 교차검증.
- 테스트 실행: B.4 회귀 단독, `python3 -m unittest discover tests`, `python3 -m pytest -q`, `py_compile`, `git diff --check`, `docker compose config --services`.

사용한 정확한 명령은 §Reproduction에 열거.

## Findings

### 1. env 기반 wiring 분기 — 부합 (3×2 매트릭스 모두 회귀로 lock)

`create_app`(`main.py:366-378`) 분기:
- `vector_index is not None`(테스트 주입) → fake + `FAKE_VECTOR_BACKEND` (line 366-369)
- else + `_build_chroma_vector_index()` not None → `ChromaVectorIndexAdapter` + `CHROMA_VECTOR_BACKEND` (line 372-375)
- else → `InMemoryVectorIndexAdapter` + `FAKE_VECTOR_BACKEND` (line 376-378)

`_build_embedding_provider`(`main.py:270-278`): `EMBEDDING_SERVICE_URL` 없으면 `DeterministicFakeEmbeddingProvider()`, 있으면 `RemoteEmbeddingProvider(..., expected_dimensions=int(os.environ.get("EMBEDDING_DIMENSIONS", "1024")))`.
`_build_chroma_vector_index`(`main.py:285-296`): `CHROMA_HOST` 없으면 `None`, 있으면 `ChromaVectorIndexAdapter(connect_chroma_collection(host, port=CHROMA_PORT default 8000, collection_name=CHROMA_COLLECTION default DEFAULT_COLLECTION_NAME))`. lazy import는 `connect_chroma_collection` 내부 → 미구성 환경 chromadb 불필요.

boundary matrix:

| cell | 방향 | lock 회귀 | 상태 |
|---|---|---|---|
| embedding: default → fake | should-fire | `test_embedding_provider_defaults_to_fake` | ✓ |
| embedding: configured → remote + 1024 | should-fire | `test_embedding_provider_is_remote_with_1024_guard...` | ✓ |
| chroma: no host → None | should-fire | `test_chroma_index_is_none_without_host` | ✓ |
| chroma: host → adapter + connect(host,port) | should-fire | `test_chroma_index_built_from_env_host_and_port` | ✓ |
| backend: default → in_memory_fake | should-fire | `test_default_backend_is_in_memory_fake` | ✓ |
| backend: CHROMA_HOST → chroma + collection write | should-fire | `test_chroma_env_uses_chroma_backend_and_writes_to_collection` | ✓ |
| backend: injected vector_index → fake + connect 미호출 | should-NOT-fire | `test_injected_vector_index_keeps_fake_backend...`(`connect.assert_not_called()`) | ✓ |

빈 cell 없음. `test_chroma_env_uses_chroma_backend...`가 `body["records_written"] > 0` + `fake.upsert_calls >= 1`로 chroma collection에 실제 write까지 lock.

### 2. 1024-dim guard armed (B.2 수용기준) — 부합

- `_build_embedding_provider`가 `RemoteEmbeddingProvider(expected_dimensions=int(os.environ.get("EMBEDDING_DIMENSIONS","1024")))`(`main.py:277`) — 기본 1024, env override 가능. B.2 수용기준 "env로 dimension 조정 가능하되 기본은 1024" 정확 부합.
- `RemoteEmbeddingProvider._expected_dimensions`(`embedding.py:36`) + guard(`embedding.py:79-84`: `len(vector) != self._expected_dimensions` → `EmbeddingProviderError`). B.1 guard가 B.4 wiring에서 1024로 armed.
- **mutation A(1024→999)**: `test_embedding_provider_is_remote_with_1024_guard...` re-fail(`provider._expected_dimensions == 1024` 단언). → 1024 기본값이 회귀로 실제 lock됨(vacuous 아님).

### 3. stale guard 통합 주장 — 부합 (코드 추적으로 입증, 작업자 주장 참)

작업자 주장 "stale guard needs no new code: shared vector_index가 양쪽으로 wiring → Chroma hit도 SOT 재조회 후에만 ContextItem"을 코드로 입증:
- `context_search/service.py:246` `hits = self._vector_search.query_similar(...)` — vector hit 조회. `vector_search`는 shared_vector_index(Chroma 또는 fake).
- `context_search/service.py:272` `validation = self._indexing.validate_source_block_record(hit)` — 각 hit마다 stale guard. `validate_source_block_record`(`indexing/service.py:564`)는 `core_sot`로 정본 재조회(content_hash/draft/snapshot 검증)하고 `vector_index`에 의존하지 않음.
- `context_search/service.py:310-315` `detail = self._core_sot.get_snapshot(...)` + `:405` `sot_reloaded=True` — SOT 재조회 후 ContextItem.
- main.py wiring(`main.py:381-385` → `_default_context_search_service` line 252-263)이 동일 `shared_vector_index`를 `indexing.vector_index`와 `context_search.vector_search` 양쪽에 전달. 단, stale guard는 `vector_index` 객체가 아니라 `core_sot` 기반이므로, vector 백엔드가 Chroma든 fake든 **무관하게** 동일 경로를 거침.
- 결론: 브리프 line 103 "stale-guard 통합" + §6 "stale guard는 backend와 무관하게 그대로"가 코드로 성립. "새 코드 없이 자동 통합" 주장은 정확. 단, 이 경로는 본 B.4 회귀가 **직접 lock하지 않음**(B.4 회귀는 rebuild write만; read path는 기존 `test_context_search_*`가 fake로 cover) — Issue #1 참조.

### 4. backend literal / enum 계약 — 부합

- `service.py:36` `CHROMA_VECTOR_BACKEND = "chroma"`(B.4 diff +1). `main.py:61` import. `create_app`이 `shared_backend`로 사용 → `rebuild_source_block_index_summary(...).to_dict(backend=shared_backend)`(`main.py:474`).
- `models.py` `IndexSyncBackend.CHROMA = "chroma"`(B.4 diff +1, StrEnum). `FAKE_VECTOR_BACKEND`/`CHROMA_VECTOR_BACKEND` 상수가 `IndexSyncBackend` enum과 일관(`in_memory_fake`/`chroma`).
- literal 정합: 코드(`chroma`) ↔ SoT v1.6.36 changelog("`backend` literal enum에 `chroma` 추가") ↔ rebuild endpoint 계약 갱신(line 368 "`backend`는 wiring에 따라 `chroma` 또는 `in_memory_fake`") — 모두 동일 literal, 드리프트 없음.

### 5. compose wiring — 부합

`docker-compose.yml` application 서비스(B.4 diff +11):
- env: `EMBEDDING_SERVICE_URL: http://embedding:8002`, `EMBEDDING_DIMENSIONS: ${EMBEDDING_DIMENSIONS:-1024}`, `CHROMA_HOST: chroma`, `CHROMA_PORT: 8000`.
- `depends_on`에 `embedding: service_healthy` + `chroma: service_healthy` 추가(기존 mongo/gateway에 추가).
- 브리프 §4 "별도 embedding 서비스 컨테이너(llama gateway와 분리 → LLM-독립)" + line 103 wiring 부합. embedding/chroma healthcheck가 service_healthy 조건이므로 app 기동 전 백엔드 준비 보장.
- `docker compose config --services` → application chroma embedding gateway mongo(5개 인식, config 유효).

### 6. 회귀 유효성 (mutation testing) — 부합 (3 mutation 모두 re-fail)

- **mutation A(1024→999)**: 1024 guard 회귀 re-fail → under-strict 가드 존재.
- **mutation B(CHROMA→FAKE label)**: `test_chroma_env_uses_chroma_backend...` re-fail → backend literal 가드 존재.
- **mutation C(항상 None)**: `test_chroma_index_built_from_env_host_and_port` re-fail → chroma 분기 가드 존재.
- 결론: 7개 회귀의 builder 4 + literal 3 cell이 모두 실제 분기를 lock. vacuous 회귀 없음.

### 7. B.3 조건부 합격 사유 승계 — 미해결 잔존 (B.4가 보강 안 함)

- `git show 7ad90ef --name-only | grep -iE "chroma\.py|test_chroma_adapter"` = 빈 결과. `git show 7ad90ef -- tests/test_chroma_adapter.py` = 빈. → **B.4는 `chroma.py`/`test_chroma_adapter.py`를 전혀 수정하지 않음**.
- 따라서 직전 B.3 검증의 조건부 합격 사유 — `query_similar`의 `project_id` scope·`draft_archived` 제외 cell 2개 under-strict 가드 부재 — 가 **그대로 잔존**. owner가 B.3 검증의 AskUserQuestion(빈 cell 처리)을 reject하고 B.4로 넘어갔으므로, 명시적 결정 없이 방치된 상태.
- 본 B.4 검증은 B.4 자체 범위이므로 이것으로 B.4 verdict를 뒤집지 않지만, **Outstanding으로 승계 명시**. 이 cell들은 B.4 wiring이 의존하는 `ChromaVectorIndexAdapter.query_similar` 동등성에 해당하므로, B.5 live 전에 owner 결정이 필요(회귀 1-2건 보강 권장).

### 8. suite 카운트 + 정합 — 부합

- B.4 회귀 단독 → Ran 7, OK.
- `python3 -m unittest discover tests` → **Ran 506, OK (skipped=45)** — 작업자 주장(45 skip) 재현.
- `python3 -m pytest -q` → **461 passed, 45 skipped** — 작업자 주장(pytest 461) 재현.
- `py_compile` + `git diff --check` 통과(working tree clean).
- 참고: 직전 B.3(497 OK / pytest 452) 대비 +9. B.4 회귀 7 + 부수 2(main.py wiring 변경에 따른 기존 테스트 수집/parametrize 효과 추정) — 작업자 주장과 재현이 일치하므로 비차단.

## Issues / Risks

1. **(비차단, B.4 회귀 설계상) rebuild→context_search read end-to-end(chroma 경로) 회귀 미lock** — B.4 회귀는 rebuild write(`records_written`, `upsert_calls`)만 lock. 브리프 line 103 핵심 "rebuild write → context-search vector read가 real Chroma에서 hit"의 read 절반은 B.4 회귀가 직접 검증 안 함. 단, (a) shared_vector_index가 동일 인스턴스로 양쪽 wiring(main.py:381-385 + 252-263)되어 구조적으로 보장, (b) stale guard 경로는 §3에서 코드로 입증, (c) 기존 `test_context_search_*`가 fake로 read hit를 cover하므로 비차단. 진짜 chroma 경로 end-to-end read는 B.5 live 관통.

2. **(비차단, 타입/주석 부정확) `_default_context_search_service` 시그니처·주석 stale** — `main.py:227` 시그니처 `vector_index: InMemoryVectorIndexAdapter`이나 B.4가 `ChromaVectorIndexAdapter`도 여기로 전달(`main.py:383`). 런타임은 `SourceBlockIndexingService`/`ContextSearchService`가 Protocol(duck-typed)이라 동작. `main.py:246-251` 주석 "The vector adapter is the process-shared in-process fake (real Chroma is a later slice)… non-durable and lost on restart"도 B.4로 틀려짐(B.4가 같은 함수에 shared 인스턴스를 전달하므로). 정적 분석(mypy)은 타입 불일치 지적 가능. 동작 영향 없으나 B.4 자신의 변경으로 인한 stale이므로 수정 권장. `create_app`의 `vector_index: InMemoryVectorIndexAdapter | None`(`main.py:349`)도 동일.

3. **(비차단, 브리프 결정사항) base compose env 하드코딩** — `EMBEDDING_SERVICE_URL`/`CHROMA_HOST`가 base compose에 고정되어, 2번째 환경에서 chroma 경로를 끄려면 env override(`CHROMA_HOST=` 공백 등)가 필요. 단 B.3에서 chroma 컨테이너 자체가 base compose에 들어갔고 브리프 오너 결정 §4 "base compose에 서비스로 편입"과 일관. 비차단.

4. **(정보) suite +9의 부수 2** — B.4 회귀 7 + 2의 정체가 명확치 않으나(main.py 변경의 수집 효과 추정), 작업자 주장 카운트(461)와 독립 재현(461)이 일치하므로 검증에는 무영향.

## Verdict

**합격 (B.4 자체 범위).**

load-bearing 이유:
- env 기반 wiring 3×2 매트릭스(7 cell)가 7개 회귀에 빈 cell 없이 매핑되고, mutation A/B/C 모두 re-fail로 under-strict 가드 실증.
- B.2 수용기준(1024-dim guard armed)이 `_build_embedding_provider` expected_dimensions=1024(기본값, env override 가능)로 구현되고 회귀로 lock됨.
- **stale guard 통합 주장이 코드 추적으로 입증됨** — `query_similar` → `validate_source_block_record`(core_sot 기반, vector_index 무관) → SOT 재조회 경로가 존재하여, Chroma hit도 정본 재확인 후에만 ContextItem이 됨. "새 코드 없이 자동 통합" 주장 참.
- backend literal(`chroma`)/`IndexSyncBackend.CHROMA`/`CHROMA_VECTOR_BACKEND`가 코드·SoT v1.6.36·rebuild endpoint 계약 간 드리프트 없이 일관.
- compose application env + depends_on(service_healthy)가 브리프 §4·line 103과 부합, config 유효.
- suite 카운트(506/45, pytest 461/45) 독립 재현.

조건 사유: 없음. 비차단 관찰(Issue #1~#4)은 합격을 뒤집지 않음. 단, **B.3 조건부 합격 사유(query_similar 빈 cell 2개)가 미해결 잔존**이며 이것은 B.4 범위 밖이나 B.4 wiring이 의존하는 adapter 동등성에 해당 — §Outstanding에서 승계.

## Outstanding items

- **(owner 결정 필요, B.3 승계) query_similar 빈 cell 2개** — B.4가 `chroma.py`/`test_chroma_adapter.py`를 수정하지 않아 직전 B.3 검증의 조건부 합격 사유가 잔존(`_active_where`의 project_id scope·draft_archived 제외 under-strict 가드 부재, mutation으로 실증 완료). B.4 wiring이 `ChromaVectorIndexAdapter.query_similar`에 의존하므로, B.5 live 전에 회귀 1-2건 보강(타 project 제외 + draft_archived 제외 케이스)으로 B.3을 합격으로 전환할지 owner 결정. 이전 AskUserQuestion이 reject되었으므로 명시적 방침 필요.
- **Issue #2 처리**: `_default_context_search_service` 시그니처/주석(`main.py:227, 246-251`)·`create_app` 시그니처(`main.py:349`)의 `InMemoryVectorIndexAdapter` 타입 힌트를 `VectorIndexAdapter` Protocol(또는 union)으로, 주석을 B.4 wiring 실태에 맞게 갱신 권장.
- **B.5 live(owner 환경)**: 실제 12B planner + real Chroma + embedding 서비스 관통 — embedding 벡터 실제 1024-dim assert, Chroma 저장/query hit, 재시작 vector hit 생존, backend="chroma", image tag/heartbeat/volume 정합, 그리고 rebuild→context_search read end-to-end(이 검증 Issue #1의 진짜 관통). sandbox 불가.
- **origin 미푸시**: branch가 origin 대비 11 ahead(B.3 10 + B.4 1). 요청 시 push.

## Reproduction

```bash
# 1. B.4 회귀 단독 (7개)
python3 -m unittest tests.test_real_vector_backend_wiring -v   # Ran 7, OK

# 2. 전체 suite (506 OK / 45 skip, pytest 461 / 45 skip)
python3 -m unittest discover tests                             # Ran 506, OK (skipped=45)
python3 -m pytest -q                                           # 461 passed, 45 skipped

# 3. 컴파일 + whitespace
python3 -m py_compile services/application/app/main.py tests/test_real_vector_backend_wiring.py
git diff --check                                               # clean

# 4. compose config 유효
docker compose config --services                               # application chroma embedding gateway mongo

# 5. B.3 빈 cell 잔존 확인 (B.4가 chroma.py/test_chroma_adapter.py 미수정)
git show 7ad90ef --name-only | grep -iE "chroma\.py|test_chroma_adapter"   # (no output)
git show 7ad90ef -- tests/test_chroma_adapter.py                          # (empty)

# 6. stale guard 통합 추적 (query_similar -> validate -> SOT 재조회)
grep -n "validate_source_block_record\|query_similar\|get_snapshot" \
  services/application/app/context_search/service.py
#   246: hits = self._vector_search.query_similar(...)
#   272: validation = self._indexing.validate_source_block_record(hit)
#   315: detail = self._core_sot.get_snapshot(...)

# 7. mutation testing — B.4 회귀 under-strict 가드 증명
cp services/application/app/main.py /tmp/main.py.bak
# (a) "EMBEDDING_DIMENSIONS", "1024" -> "999"        → 1024 guard 회귀 re-fail
# (b) shared_backend = CHROMA_VECTOR_BACKEND -> FAKE  → backend literal 회귀 re-fail
# (c) _build_chroma_vector_index 항상 return None     → chroma 분기 회귀 re-fail
python3 -m unittest tests.test_real_vector_backend_wiring -v   # (각 mutation마다 1 re-fail)
cp /tmp/main.py.bak services/application/app/main.py
diff -q /tmp/main.py.bak services/application/app/main.py      # identical
rm -f /tmp/main.py.bak
```
