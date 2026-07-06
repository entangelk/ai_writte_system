# Verification — Phase 4 real vector backend 브리프 + B.1 embedding seam (commit e23a2f1)

## Subject metadata

- 검증일: 2026-07-05
- 요청자: owner ("다음작업 검증해줘. 커밋 완료(e23a2f1). B의 브리프 승인 + 첫 sub-slice B.1까지 마쳤습니다. ... ③ embedding 모델 정정 ... B.1 embedding provider seam 구현 ...")
- 검증자: 독립 검증 AI(Claude, 작업 AI와 다른 세션; `shared_vector_index_slice.md`, `deployed_smoke_rebuild_first.md`에 이어 동일 세션)
- 대상 slice/artifact: commit `e23a2f1` "Approve real vector backend brief + implement B.1 embedding seam" — `docs/plans/04-real-vector-backend-decisions.md`(신규 브리프 110행, 6 결정), `services/application/app/indexing/embedding.py`(신규 `RemoteEmbeddingProvider` 86행), `tests/test_embedding_provider.py`(신규 회귀 8개 111행). 동반 커밋 `5a45931`(직전 deployed smoke 검증의 비차단 관찰 real-app 회귀 보강)도 범위 확인.
- 정본 계약 참조:
  - `docs/plans/04-real-vector-backend-decisions.md`(상태 `Approved (2026-07-05)`) — Owner decisions §1–§6, sub-slice 계획 B.1–B.5.
  - 선행 `docs/plans/04-shared-vector-index-decisions.md` SoT v1.6.35 — 현재 `InMemoryVectorIndexAdapter`/`DeterministicFakeEmbeddingProvider`와 `EmbeddingProvider` Protocol.
  - `services/application/app/indexing/service.py:44-45` — `EmbeddingProvider` Protocol(`def embed(self, text: str) -> tuple[float, ...]`, sync); 사용처 `indexing/service.py:630`, `context_search/service.py:245`(둘 다 sync 호출).
  - work_log "User Decisions and Rationale — Phase 4 real vector backend (B) 착수" 섹션 — 2026-07-02 "최후속" 갱신 사유 + embedding 정정 경위.
- 검증 대상 작업 출처: branch `phase4-slice-4-2-planner` HEAD(`e23a2f1`), working tree clean(origin 대비 6 ahead, 미푸시).

## Scope

1. 브리프 6개 결정 자기 일관성 + 2026-07-02 "최후속" 결정 갱신이 owner 결정으로 정당한지, 선행 Phase 4 브리프와 충돌하는지.
2. **embedding 모델 정정(③) 기술적 사실 독립 확인** — `dragonkue/bge-reranker-v2-m3-ko`(cross-encoder reranker, embedding 불가) ↔ `dragonkue/BGE-m3-ko`(bi-encoder, 1024-dim, sentence-transformers) 주장을 WebSearch로 재확인.
3. B.1 embedding provider seam — sync Protocol 유지, sync httpx.Client POST /embed, wire 계약 `{text}`→`{embedding:[...]}`, response 검증, error 매핑이 브리프 B.1과 일치하는지.
4. boundary matrix 구축 — should-fire/should-NOT-fire/under-strict cell을 8개 회귀에 매핑; 특히 bool 거부 guard(int subclass 함정)와 expected_dimensions mismatch의 under-strict.
5. **mutation testing**(핵심) — (A) bool 거부 guard 제거, (B) expected_dimensions guard 제거, 각각 re-fail 실증.
6. suite 카운트 독립 재현(483 OK / pytest 439) + MockTransport 한계 인식.
7. 동반 커밋 `5a45931`이 직전 검증 비차단 관찰의 폐쇄인지 확인.

## Methodology

- 계약 스코프: 브리프 6 결정 + sub-slice 계획 + work_log User Decisions 섹션 + EmbeddingProvider Protocol/사용처만 종단 독해. ES lexical / prior-memory / tool-call planner는 스코프 밖.
- **embedding 모델 정정 독립 확인**(핵심): WebSearch로 두 HuggingFace 모델 페이지를 각각 조회해 작업자 주장(cross-encoder vs bi-encoder, 1024-dim, sentence-transformers)을 재확인. 작업자 WebFetch 결과에만 의존하지 않음.
- boundary matrix 구축 후 8개 회귀의 각 assertion을 cell에 수동 매핑.
- **경험적 mutation testing**(핵심): `embedding.py`를 `/tmp`에 cp 백업 → guard 무력화 → `python3 -m unittest tests.test_embedding_provider -v` 재실행 → re-fail 수/메시지 기록 → 백업에서 cp 복원 → `diff -q`로 byte-identical 확인.
  - Mutation A: bool 거부(`isinstance(value, bool) or ...`)에서 bool 절 제거 → True가 int subclass라 통과.
  - Mutation B: expected_dimensions mismatch guard 블록 제거.
- 테스트 실행: embedding 회귀 단독, `python3 -m unittest discover tests`, `python3 -m pytest -q`, `py_compile`, `git diff --check`.
- 동반 커밋 확인: `git show --stat 5a45931`과 work_log "독립 검증 후속 보강" 섹션이 직전 검증 비차단 관찰과 대응하는지 교차 검증.

사용한 정확한 명령은 §Reproduction에 열거.

## Findings

### 1. embedding 모델 정정(③) — 작업자 주장 정확 (독립 확인)

WebSearch로 두 HuggingFace 모델 페이지를 독립 조회:

| 모델 | HF 페이지 명시 | 작업자 주장 | 판정 |
|---|---|---|---|
| `dragonkue/bge-reranker-v2-m3-ko` | *"Reranker (Cross-Encoder). Different from embedding model, reranker uses question and document as input and directly output similarity"* | cross-encoder reranker, embedding 생성 불가 | ✓ 정확 |
| `dragonkue/BGE-m3-ko` | *"sentence-transformers model... maps sentences & paragraphs to a 1024-dimensional dense vector space"*, BAAI/bge-m3 기반 | bi-encoder embedding model, 1024-dim, sentence-transformers, 한국어 파인튜닝 | ✓ 정확 |

owner가 처음 링크한 reranker를 embedding으로 쓸 수 없다는 점을 작업자가 정확히 포착해 surface했고, owner가 올바른 embedding model로 정정. 이것은 CLAUDE.md "모순 탐지 시 사용자에게 surface"의 모범 사례. 브리프 §3/§3-배경/§3-옵션표가 정정 내역과 rationale을 명시.

### 2. 브리프 6개 결정 자기 일관성 + "최후속" 갱신 정당성 — 부합

- **§1 타이밍(2026-07-02 "최후속" 갱신)**: 브리프 §1/배경이 "2026-07-02 오너 결정: real 백엔드/embedding model은 핵심 코어 이후 최후속"을 명시하고, §1 옵션 A가 이를 "지금 앞당김"으로 갱신. work_log "User Decisions and Rationale" 섹션(work_log:12)에 근거가 명시 기록됨 — "이 작업은 LLM 게이트와 무관해(테스트 스위트 전체가 LLM-독립, LLM은 live smoke 스크립트만 사용) 2-환경 개발 제약과 정확히 맞고, vector need 영속화 이득을 조기 확보". CLAUDE.md "recorded user decision과 충돌 시 사용자에게 확인" 요건을 owner 명시 승인 + work_log rationale으로 충족. 갱신 절차 정당.
- **§2–§6 일관**: §2 Chroma-only(ES 후속) ↔ §6 `backend="chroma"` literal; §3 embedding model 확정(1024-dim) ↔ §6 dimension 1024; §4 전부 컨테이너 + embedding 별도 서비스(LLM-독립) ↔ "2-환경 제약 반영" 단락; §5 skip-aware live + fake 단위 ↔ 기존 Mongo 패턴. 선행 `04-shared-vector-index-decisions.md`/SoT v1.6.35와 충돌 없음 — fake adapter/`DeterministicFakeEmbeddingProvider`를 교체하지 않고 **추가** real 경로를 여는 방향.
- sub-slice 계획 B.1–B.5가 "한 커밋에 몰지 않고 작은 세로 slice"로 분리되어 각 sub-slice가 인프라 무관 단위 테스트로 잠기도록 명시 — 복잡도 통제 타당.

### 3. B.1 embedding provider seam — 부합

- **sync Protocol 유지**: `RemoteEmbeddingProvider.embed(self, text: str) -> tuple[float, ...]`(`embedding.py:39`)는 `EmbeddingProvider` Protocol(`service.py:44-45`)과 signature 일치. 사용처 `indexing/service.py:630`(`vector=self._embeddings.embed(text)`)와 `context_search/service.py:245`(`vector = self._embeddings.embed(...)`)가 둘 다 sync 호출이므로 async 파급 없음 — 브리프 B.1 "embed는 동기를 유지... async 파급 회피"와 일치.
- **sync httpx.Client**: `with httpx.Client(...)`로 동기 컨텍스트 매니저(`embedding.py:41-46`), `client.post("/embed", json={"text": text})`(`embedding.py:47`). wire 계약 `{text}` → `{embedding:[...]}` 브리프 B.1/B.2와 일치.
- **error 매핑**: `TimeoutException`→"timed out"(`embedding.py:48-49`), `RequestError`→"unavailable"(`embedding.py:50-51`), `status_code >= 400`(`embedding.py:53-56`), JSON parse 실패→"not JSON"(`embedding.py:57-60`). `EmbeddingProviderError(RuntimeError)`로 통일.
- **response 검증(`_vector_from_body`)**: dict 여부(`embedding.py:64-65`), `embedding` list + non-empty(`embedding.py:66-70`), 각 값 numeric-and-not-bool(`embedding.py:75`), optional `expected_dimensions` mismatch(`embedding.py:78-85`), float coercion + tuple 반환(`embedding.py:77,86`). int는 float로 coercion하되 **bool은 int subclass라도 거부** — malformed body가 0.0/1.0으로 silent coercion되는 함정 방지.
- 주의: B.1은 클래스만 추가하고 `create_app` wiring은 B.4에 예약(브리프 sub-slice 계획). 현재 `RemoteEmbeddingProvider`를 참조하는 곳은 test뿐 — 이것은 sub-slice 계획상 자명.

### 4. boundary matrix — 모든 cell lock, 빈 cell 없음

| cell | 계약 | 방향 | lock 회귀 |
|---|---|---|---|
| POST /embed with `{"text": ...}` | wire 계약 | should-fire | `test_posts_text_and_returns_float_vector`(method/path/body assertion) |
| float coercion + tuple 반환 | Protocol | should-fire | 동일(int 4 → 4.0) |
| expected_dimensions 일치 시 통과 | §6 dim | should-fire | `test_expected_dimensions_pass_and_mismatch`(dim 3 pass) |
| expected_dimensions mismatch 거부 | §6 dim | should-NOT-fire | 동일(dim 1024 mismatch → error) |
| timeout → error | error 매핑 | should-fire | `test_timeout_maps_to_embedding_error` |
| ConnectError → error | error 매핑 | should-fire | `test_request_error_maps_to_embedding_error` |
| non-200 → error | error 매핑 | should-fire | `test_non_200_status_maps_to_embedding_error` |
| non-JSON body → error | error 매핑 | should-fire | `test_non_json_body_maps_to_embedding_error` |
| empty array 거부 | response 검증 | should-NOT-fire | `test_missing_or_empty_embedding_array_rejected`(4 subTest: empty/string/missing key/non-dict) |
| embedding string 거부 | response 검증 | should-NOT-fire | 동일 |
| missing key 거부 | response 검증 | should-NOT-fire | 동일 |
| non-dict body(list) 거부 | response 검증 | should-NOT-fire | 동일 |
| non-numeric value(string) 거부 | response 검증 | should-NOT-fire | `test_non_numeric_or_bool_values_rejected`(3 subTest) |
| **bool value 거부** | **int subclass 함정** | should-NOT-fire | 동일(`[0.1, True, 0.3]`) |
| None value 거부 | response 검증 | should-NOT-fire | 동일 |

boundary matrix에 빈 cell 없음. 특히 bool 거부 guard의 under-strict lock은 회귀 품질이 우수(자명하지 않은 함정을 잡음).

### 5. mutation testing — 양 guard 모두 re-fail 실증

| mutation | 무력화 | 결과 | 의미 |
|---|---|---|---|
| **A** bool 거부 guard 제거 | `isinstance(value, bool) or ...`에서 bool 절 제거 → True가 int subclass라 통과, 1.0으로 coercion | **1 re-fail**: `test_non_numeric_or_bool_values_rejected`(subTest `[0.1, True, 0.3]`, `AssertionError: EmbeddingProviderError not raised`) | under-strict ✓ — int subclass 함정 guard가 vacuous 아님 |
| **B** expected_dimensions guard 제거 | mismatch guard 블록 제거 → 어떤 차원이든 통과 | **1 re-fail**: `test_expected_dimensions_pass_and_mismatch`(`AssertionError: EmbeddingProviderError not raised`, actual 3 vs expected 1024) | under-strict ✓ — dimension 검증 guard가 vacuous 아님 |

- 복원: `/tmp` 백업에서 cp 복원 후 `diff -q`로 byte-identical 확인, embedding 회귀 8개 재통과.

### 6. suite 카운트 + envelope 주장 독립 재현 — 부합

- embedding 회귀 단독 `python3 -m unittest tests.test_embedding_provider -v` → Ran 8, OK.
- `python3 -m unittest discover tests` → **Ran 483, OK (skipped=44)** — 작업자 주장(483 OK/44 skip) 재현(직전 475 + B.1 8 = 483).
- `python3 -m pytest -q` → **439 passed, 44 skipped** — 작업자 주장(pytest 439) 재현. pytest warning이 3→2로 감소한 것은 직전 shared-index 검증의 비차단 관찰(TestClient `PytestCollectionWarning`)을 `__test__ = False`로 보강한 효과(work_log:62).
- `py_compile` + `git diff --check` 통과(working tree clean).

### 7. 동반 커밋 5a45931 — 직전 deployed smoke 검증 비차단 관찰의 폐쇄 확인

- `5a45931` "Add committed real-app penetration regression for deployed smoke": `tests/test_phase4_context_search_deployed_smoke_script.py`에 `test_real_app_rebuild_populates_shared_index_and_search_hits` 추가(5→6개). real `create_app`(공유 index 주입 + fake planner)에 `httpx.ASGITransport`로 smoke 구동 → `rebuild_records_written>0`, `micro_count>0`(source_quote 실hit), `smoke_succeeded` lock. non-vacuity mutation(`vector_index=shared_index` 주입 제거 시 `micro_count 0` 재실패) 포함.
- 이것은 직전 검증(`deployed_smoke_rebuild_first.md` §6 "회귀는 전부 MockTransport라 real-app 관통이 회귀가 아님")의 비차단 관찰을 정확히 폐쇄. 검증→피드백→폐쇄 루프 작동 확인. 본 B.1 검증과는 별개 선행 보강이나, 루프가 살아 있음을 보여주는 증거로 기록.

## Issues / Risks

1. **(비차단, B.1 성격상 타당) 회귀는 MockTransport 기반** — 8개 회귀가 전부 `httpx.MockTransport(handler)` 기반. wire 계약(request `{text}`, response `{embedding:[...]}`)의 **소비 측**을 lock하지만, B.2가 구현할 **embedding 서비스 실제 응답과의 호환성**은 lock하지 않는다. B.2(sentence-transformers 서비스) 구현 시 서비스가 이 wire 계약을 정확히 생산하는지 별도 확인이 필요하다. 이것은 seam sub-slice의 본질적 한계이지 결함이 아니다.

2. **(비차단, sub-slice 계획상 자명) B.1은 아직 create_app에 wiring 안 됨** — `RemoteEmbeddingProvider`를 참조하는 곳은 test뿐이고, `create_app` 기본 wiring은 B.4에 예약. 따라서 현재 production 경로에 영향 없음. 브리프 sub-slice 계획과 일치.

3. **(비차단, 품질) B.1 wire 계약이 브리프/코드/test에 일관** — request `{"text": text}`, response `{"embedding": [...]}`. 단 response의 추가 필드(예: `dim`, `model`)에 대한 forward-compatible 처리는 명시 안 됨. 현재 `body.get("embedding")`만 보므로 추가 필드는 무시되어 안전. 비차단.

## Verdict

**합격.**

load-bearing 이유:
- embedding 모델 정정(③)이 WebSearch로 독립 확인됨 — cross-encoder reranker(embedding 불가) vs bi-encoder 1024-dim embedding model 구분이 정확.
- 브리프 6개 결정 자기 일관성 부합; 2026-07-02 "최후속" 갱신이 owner 명시 승인 + work_log rationale으로 정당.
- B.1 seam이 sync `EmbeddingProvider` Protocol을 정확히 만족(사용처 sync 호출과 호환), wire 계약·error 매핑·response 검증이 브리프와 일치.
- boundary matrix의 모든 cell(15 cell)이 8개 회귀에 매핑되고 빈 cell 없음. 특히 bool 거부(int subclass 함정) guard의 under-strict lock은 회귀 품질 우수.
- mutation 양방향 실증: bool guard 제거 → test 8 re-fail, dimensions guard 제거 → test 2 re-fail. 두 핵심 guard가 모두 vacuous 아님.
- suite 카운트(483 OK/44 skip, pytest 439/44 skip) 독립 재현.
- 동반 커밋 5a45931이 직전 검증 비차단 관찰을 폐쇄 — 검증-피드백 루프 작동 중.

조건 사유: 없음. 비차단 관찰(MockTransport 한계→B.1 본질, wiring 미연결→sub-slice 계획, 추가 필드 무관)은 합격을 뒤집지 않는다.

## Outstanding items

- **B.2 embedding 서비스 컨테이너**: `services/embedding/`에 sentence-transformers로 `dragonkue/BGE-m3-ko` 로드, `POST /embed`(+ `/health`) FastAPI + Dockerfile + base compose 서비스. wire 계약을 B.1과 일치시켜야(§Issues #1). 실제 모델(수백 MB~GB, torch) 다운로드 필요 → 이 sandbox에서 live 실행 불가, owner 환경(컨테이너 기동 가능)에서 live 차원 확인 필요.
- **owner 결정 대기**: B.2(compose에 새 서비스 + 무거운 의존성 추가)로 바로 갈지, B.3(Chroma adapter)를 먼저 할지 순서 확인 필요(작업자가 짚은 대로 인프라 변경이라 확인받고 진행).
- **origin 미푸시**: branch가 origin 대비 6 ahead. 요청 시 push.

## Reproduction

```bash
# 1. embedding 회귀 단독 (8개)
python3 -m unittest tests.test_embedding_provider -v   # Ran 8, OK

# 2. 전체 suite (483 OK / 44 skip, pytest 439 / 44 skip)
python3 -m unittest discover tests                       # Ran 483, OK (skipped=44)
python3 -m pytest -q                                     # 439 passed, 44 skipped

# 3. 컴파일 + whitespace
python3 -m py_compile services/application/app/indexing/embedding.py tests/test_embedding_provider.py
git diff --check                                         # clean

# 4. Mutation A — bool 거부 guard 제거 → test 8 re-fail
cp services/application/app/indexing/embedding.py /tmp/emb.py.bak
# Edit line 75: "if isinstance(value, bool) or not isinstance..." → "if not isinstance..."
python3 -m unittest tests.test_embedding_provider -v
#   → 1 failure: test_non_numeric_or_bool_values_rejected (subTest [0.1, True, 0.3], EmbeddingProviderError not raised)
cp /tmp/emb.py.bak services/application/app/indexing/embedding.py

# 5. Mutation B — expected_dimensions guard 제거 → test 2 re-fail
# Edit: _vector_from_body 의 expected_dimensions mismatch 블록(if self._expected_dimensions ...) 제거
python3 -m unittest tests.test_embedding_provider -v
#   → 1 failure: test_expected_dimensions_pass_and_mismatch (EmbeddingProviderError not raised)
cp /tmp/emb.py.bak services/application/app/indexing/embedding.py

# 6. 복원 확인
diff -q /tmp/emb.py.bak services/application/app/indexing/embedding.py   # identical
python3 -m unittest tests.test_embedding_provider                        # Ran 8, OK
rm -f /tmp/emb.py.bak

# 7. embedding 모델 정정 독립 확인 (WebSearch)
#   dragonkue/bge-reranker-v2-m3-ko  → HF: "Reranker (Cross-Encoder)... not embedding"
#   dragonkue/BGE-m3-ko              → HF: "sentence-transformers... 1024-dimensional dense vector"

# 8. 동반 커밋 확인
git show --stat 5a45931 | tail -5        # real-app 회귀 보강 (직전 검증 비차단 관찰 폐쇄)
git show --stat e23a2f1 | tail -8        # 브리프 + embedding.py + test 8개
```
