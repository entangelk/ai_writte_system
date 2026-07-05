# Verification — Phase 4 B.2 embedding 서비스 컨테이너 (commit d54408a)

## Subject metadata

- 검증일: 2026-07-05
- 요청자: owner ("다음작업 검증해줘. B.2를 완료·커밋했습니다(d54408a). ... 검증자 관찰 #1 폐쇄: build_embed_response를 단일 응답 shape 소스로 분리하고, producer↔consumer round-trip 회귀로 ...")
- 검증자: 독립 검증 AI(Claude, 작업 AI와 다른 세션; `shared_vector_index_slice.md`, `deployed_smoke_rebuild_first.md`, `real_vector_backend_brief_b1_embedding_seam.md`에 이어 동일 세션)
- 대상 slice/artifact: commit `d54408a` "B.2: embedding service container (dragonkue/BGE-m3-ko)" — `services/embedding/app/main.py`(신규 FastAPI 서비스 100행), `services/embedding/Dockerfile`, `services/embedding/requirements.txt`, `docker-compose.yml`(embedding 서비스 +32), `tests/test_embedding_service.py`(신규 회귀 5개 99행). 선행 `15389f0` "Track B.1 verification follow-up as a B.2 acceptance criterion"(브리프 수용기준 갱신)도 범위.
- 정본 계약 참조:
  - `docs/plans/04-real-vector-backend-decisions.md`(상태 `Approved (2026-07-05)`) — §3 embedding model(`dragonkue/BGE-m3-ko`, 1024-dim), §4 인프라(별도 컨테이너, LLM-독립), sub-slice B.2 + **15389f0로 추가된 B.2 수용기준(round-trip)**.
  - 선행 `services/application/app/indexing/embedding.py`(B.1 `RemoteEmbeddingProvider`) — wire 계약 consumer 측(request `{"text": str}` → response `{"embedding": [float,...]}`, non-empty, numeric).
  - 직전 검증 `docs/verifications/2026-07-05/real_vector_backend_brief_b1_embedding_seam.md` §Issues #1(MockTransport 한계 → wire 호환성 lock 필요).
- 검증 대상 작업 출처: branch `phase4-slice-4-2-planner` HEAD(`d54408a`), working tree clean(origin 대비 7 ahead, 미푸시).

## Scope

1. **round-trip wire 계약**(핵심) — `build_embed_response`가 단일 응답 shape 소스인지, round-trip 회귀가 B.1 `RemoteEmbeddingProvider`와 실제 호환되는지, producer shape 변경 시 consumer가 깨지는지 mutation으로 under-strict 증명. 직전 B.1 검증 비차단 관찰 #1의 폐쇄 확인.
2. 브리프 B.2 + 15389f0 수용기준 — wire 계약 생산 측을 잠근다는 수용기준이 회귀로 실현됐는지.
3. embedding 서비스 endpoint boundary — POST /embed, /health·/health/live·/health/ready(미로드 503), 빈 text 422, `create_app(model=None)` 주입 vs lazy 로드.
4. lazy import — sentence_transformers import가 stub 주입 시 실행되지 않아 torch 없이 단위 테스트가 돌는지.
5. wire 계약 일관성(B.1↔B.2) — request `{"text"}`, response `{"embedding", "dimensions"}`; B.1이 `dimensions`를 무시하고 `embedding`만 소비해 호환되는지.
6. Dockerfile(cache-friendly 레이어 순서) + compose(별도 컨테이너, port 8002, HF 캐시 볼륨, healthcheck) + `docker compose config` 유효.
7. suite 카운트 독립 재현(488 OK / pytest 444).

## Methodology

- 계약 스코프: 브리프 B.2 + 15389f0 수용기준 + B.1 `RemoteEmbeddingProvider`(consumer) + 직전 검증 §Issues #1만 종단 독해. B.3(Chroma)/B.4(wiring)/B.5(live)는 스코프 밖.
- boundary matrix 구축 후 5개 회귀의 각 assertion을 cell에 수동 매핑.
- **경험적 mutation testing**(핵심): `services/embedding/app/main.py`를 `/tmp`에 cp 백업 → `build_embed_response`의 `"embedding"` 키를 `"vector"`로 치환(producer wire shape 변경) → `python3 -m unittest tests.test_embedding_service -v` 재실행 → round-trip + app 자체 양쪽 re-fail 확인 → cp 복원 → `diff -q`로 byte-identical.
- wire 호환성: B.1 `_vector_from_body`가 `body.get("embedding")`만 보고 `dimensions`를 무시하는지 `embedding.py` 직독으로 확인.
- 테스트 실행: embedding service 회귀 단독, `python3 -m unittest discover tests`, `python3 -m pytest -q`, `py_compile`, `git diff --check`.
- compose 검증: `docker compose config --services`로 embedding 서비스 인식 + 전체 config 유효.

사용한 정확한 명령은 §Reproduction에 열거.

## Findings

### 1. round-trip wire 계약 — 부합 (직전 검증 관찰 #1 폐쇄 실증)

- `build_embed_response(model, text)`(`main.py:44-49`)가 `{"embedding": vector, "dimensions": len(vector)}` 단일 소스. `/embed` route(`main.py:95`)와 round-trip 회귀(`test_embedding_service.py:85`)가 **같은 함수** 호출 → producer 측 shape 드리프트 원천 차단.
- round-trip 회귀 `test_service_response_is_consumable_by_remote_provider`(`test:80-95`): `build_embed_response(model, text)` 출력을 `MockTransport` handler가 반환 → B.1 `RemoteEmbeddingProvider`(expected_dimensions=8)가 소비 → `vector == tuple(model.embed(...))` 검증. producer↔consumer가 같은 shape으로 만나는지를 실제로 실행해 확인.
- **mutation 실증**(핵심): `build_embed_response`의 `"embedding"` 키를 `"vector"`로 치환 시 **2개 re-fail**:
  - round-trip: B.1 `_vector_from_body`가 `body.get("embedding")` → None → `EmbeddingProviderError: embedding response must include a non-empty 'embedding' array`.
  - app 자체 `test_embed_returns_vector_and_dimensions`: `body["embedding"]` → `KeyError`.
  - → wire 계약의 양측(producer app + consumer round-trip)이 `embedding` 키에 의존하며, **producer가 shape을 바꾸면 consumer 측에서 즉시 잡힘**을 증명. 회귀가 vacuous하지 않다.
- 직전 B.1 검증 `real_vector_backend_brief_b1_embedding_seam.md` §Issues #1 "회귀는 MockTransport 기반이라 wire 호환성은 lock 안 함, B.2가 wire 계약을 생산 시 별도 확인 필요"가 **정확히 폐쇄**됨 — B.2가 round-trip 회귀로 producer 측을 lock.

### 2. 브리프 B.2 + 15389f0 수용기준 — 부합

- `15389f0`가 B.2 수용기준에 "B.2 서비스 handler ↔ B.1 RemoteEmbeddingProvider round-trip(인프라 없이 stub)"을 명시 추가. commit message "bake it into B.2's acceptance criteria"가 검증-피드백→수용기준 승격의 명시적 절차.
- B.2 구현이 이 수용기준을 이행: (a) app 자체 회귀 4개(producer 측 shape/endpoint), (b) round-trip 회귀 1개(producer↔consumer 호환). 브리프가 요구한 두 축 모두 회귀로 실현.

### 3. wire 계약 일관성(B.1↔B.2) — 부합

- request: B.1 `client.post("/embed", json={"text": text})`(`embedding.py:47`) ↔ B.2 `EmbedRequest.text: str`(`main.py:40-41`). 일치.
- response: B.2 `{"embedding": [...], "dimensions": int}`. B.1 `_vector_from_body`는 `body.get("embedding")`만 소비(`embedding.py:66`)하고 `dimensions` 필드는 무시 → B.2의 `dimensions` 추가 필드가 B.1 consumer에 영향 없음. 호환.
- 다만 B.1의 optional `expected_dimensions`가 B.4 wiring 시 실제 모델 1024와 일치해야 함(브리프 §6). B.2 자체는 `dimensions`를 응답에 포함하므로 B.4가 이 값을 신뢰할 수 있음.

### 4. embedding 서비스 endpoint boundary — 모든 cell lock

| cell | 방향 | lock 회귀 |
|---|---|---|
| POST /embed → {embedding, dimensions} 200 | should-fire | `test_embed_returns_vector_and_dimensions` |
| `dimensions` 필드 == len(embedding) | literal | 동일(`body["dimensions"]==8`, `len(body["embedding"])==8`) |
| embedding == model.embed(text) | should-fire | 동일 |
| /health/live 200(model 무관) | should-fire | `test_health_and_readiness...` + `test_not_loaded...`(live 200) |
| /health/ready 200(model 있을 때) | should-fire | `test_health_and_readiness...` |
| /health/ready 503(model None) | should-NOT-fire | `test_not_loaded_model_returns_503` |
| 빈 text → 422 | should-NOT-fire | `test_empty_text_is_rejected`(pydantic `Field(min_length=1)`) |
| 미로드 /embed → 503 | should-NOT-fire | `test_not_loaded_model_returns_503` |
| round-trip(B.1 consumer 호환) | should-fire | `test_service_response_is_consumable_by_remote_provider` |
| round-trip under-strict(shape 변경) | under-strict | mutation 2 re-fail(§1) |

`/health`와 `/health/live`가 같은 handler(`main.py:79-81`)로 200, `/health/ready`가 model 상태 게이팅(`main.py:84-88`) — health/live(프로세스 alive) vs health/ready(model 로드) 분리가 compose healthcheck와 정확히 맞음. 빈 cell 없음.

### 5. lazy import — 부합 (torch 없이 단위 실행)

- `SentenceTransformerEmbeddingModel.__init__`에서 `from sentence_transformers import SentenceTransformer`(`main.py:30`) — 클래스 인스턴스화 시에만 import. stub 주입 시 이 클래스를 건드리지 않으므로 torch 불필요.
- `create_app(model=None)`은 lifespan에서만 `_build_model_from_env()` 호출(`main.py:72-73`). ASGITransport는 lifespan을 실행 안 하므로 `test_not_loaded` 경로에서도 lazy import 미발생. 모듈 레벨 `app = create_app()`(`main.py:100`)도 import 시 model=None이고 lifespan 안 돌아 안전.
- **실증**: 이 sandbox(torch/sentence_transformers 미설치)에서 전체 suite가 488 OK로 통과 → lazy import가 단위 테스트를 인프라 없이 실행시킴을 확인.

### 6. Dockerfile + compose — 부합

- **Dockerfile cache-friendly**: `python:3.12-slim`, `requirements.txt` COPY + `pip install`을 source COPY보다 **먼저**(`Dockerfile:9-13`), source COPY는 그 뒤(`Dockerfile:15-16`). 기존 application/gateway Dockerfile 패턴(HANDOFF Active Decisions "빌드 캐시 보존 레이어 순서")과 일치. sentence-transformers가 torch를 끌어 layer가 크므로 source copy 앞에 둔 근거가 주석으로 명시.
- **compose embedding 서비스**: 별도 컨테이너(llama gateway와 분리 → 브리프 §4 LLM-독립), port `${EMBEDDING_PORT:-8002}:8002`, `EMBEDDING_MODEL_NAME` default `dragonkue/BGE-m3-ko`, `HF_HOME` + `embedding_cache` 볼륨(모델 재다운로드 방지), `/health/ready` healthcheck(python urllib — slim 이미지에 curl 없어도 동작), `start_period: 300s` + `retries: 20`(첫 모델 다운로드 넉넉).
- `docker compose config --services` → `application embedding gateway mongo` 4개 인식, 전체 config 유효.

### 7. suite 카운트 + envelope 주장 독립 재현 — 부합

- embedding service 회귀 단독 → Ran 5, OK.
- `python3 -m unittest discover tests` → **Ran 488, OK (skipped=44)** — 작업자 주장("전체 OK(44 skip)") 재현(직전 483 + B.2 5 = 488).
- `python3 -m pytest -q` → **444 passed, 44 skipped** — 작업자 주장(pytest 444) 재현(직전 439 + 5 = 444).
- `py_compile` + `git diff --check` 통과(working tree clean).

## Issues / Risks

1. **(비차단, B.2 성격상 타당) 실제 1024-dim 관통 미검증** — 회귀는 `StubEmbeddingModel`(dimensions=8) 기반이라 실제 `dragonkue/BGE-m3-ko`의 1024-dim 응답을 lock하지 않는다. 브리프 B.2 "1024-dim 응답, live smoke로 실제 임베딩 차원 확인"대로 real 1024-dim은 컨테이너 기동 필요 → B.5/live로 연기. `dimensions` 필드가 `len(vector)`로 계산되므로 실제 모델이 1024를 내면 응답도 1024를 보고한다(코드는 올바름). 비차단.

2. **(비차단, sub-slice 계획상 자명) application↔embedding wiring 미연결** — embedding 서비스는 독립 실행만 가능하고, Application의 `RemoteEmbeddingProvider`가 이 서비스를 가리키도록 wiring하는 것은 B.4. 현재 production 경로에 영향 없음. 브리프 sub-slice 계획 일치.

3. **(정보, 좋은 패턴) 검증-피드백-폐쇄 루프 4회 연속 작동** — shared_index(snapshot-scope mutation) → deployed_smoke(real-app 회귀) → B.1(브리프 수용기준 추적) → B.2(round-trip 회귀). 직전 검증의 비차단 관찰이 다음 slice에서 수용기준 승격 또는 회귀 폐쇄로 이어지는 루프가 살아 있음. 본 검증 합격 여부와 무관하나 프로세스 품질 지표.

## Verdict

**합격.**

load-bearing 이유:
- round-trip wire 계약이 `build_embed_response` 단일 소스 + round-trip 회귀로 lock되었고, mutation(`embedding`→`vector`) 2 re-fail로 under-strict까지 실증 → 직전 B.1 검증 비차단 관찰 #1이 정확히 폐쇄됨.
- 15389f0가 B.2 수용기준으로 round-trip을 못 박았고, B.2 구현이 이를 이행(app 자체 4 + round-trip 1).
- wire 계약 B.1↔B.2 일관(request `{"text"}`, response `{"embedding","dimensions"}`, consumer가 `dimensions` 무시).
- endpoint boundary 10 cell이 5개 회귀에 매핑되고 빈 cell 없음.
- lazy import가 torch 없이 단위 실행됨을 sandbox suite 통과로 실증.
- Dockerfile cache-friendly + compose 별도 컨테이너(LLM-독립)가 기존 패턴/브리프 §4와 일치, `docker compose config` 유효.
- suite 카운트(488 OK/44 skip, pytest 444/44 skip) 독립 재현.

조건 사유: 없음. 비차단 관찰(1024-dim live 미검증→B.2 본질, wiring 미연결→sub-slice 계획)은 합격을 뒤집지 않는다.

## Outstanding items

- **B.3 Chroma persistent adapter**: `VectorIndexAdapter`/`VectorSearchAdapter` seam 뒤 real 영속 Chroma adapter(thin client) + base compose Chroma 컨테이너 + volume + skip-aware live 통합 테스트(upsert/query/재시작 생존). LLM-독립, fake embedding으로 계약 lock 가능 → 두 환경 모두 단위 테스트 가능(live는 Chroma 컨테이너 필요 시 skip-aware). **Chroma 컨테이너 + chromadb 클라이언트 의존성이 붙는 인프라 변경이라 owner 확인 대기**(작업자 짚은 대로).
- **1024-dim live 관통**: 실제 모델 로드 + 1024-dim 응답 확인은 컨테이너 기동 가능한 owner 환경 필요 → B.5/live.
- **origin 미푸시**: branch가 origin 대비 7 ahead. 요청 시 push.

## Reproduction

```bash
# 1. embedding service 회귀 (5개)
python3 -m unittest tests.test_embedding_service -v   # Ran 5, OK

# 2. 전체 suite (488 OK / 44 skip, pytest 444 / 44 skip)
python3 -m unittest discover tests                      # Ran 488, OK (skipped=44)
python3 -m pytest -q                                    # 444 passed, 44 skipped

# 3. 컴파일 + whitespace
python3 -m py_compile services/embedding/app/main.py tests/test_embedding_service.py
git diff --check                                        # clean

# 4. compose config 유효
docker compose config --services                        # application embedding gateway mongo

# 5. round-trip mutation — build_embed_response 의 "embedding" 키를 "vector"로 치환 → 2 re-fail
cp services/embedding/app/main.py /tmp/emb_main.py.bak
# Edit main.py:49 return {"embedding": vector, ...} → return {"vector": vector, ...}
python3 -m unittest tests.test_embedding_service -v
#   → 2 errors:
#     test_service_response_is_consumable_by_remote_provider (EmbeddingProviderError: ... non-empty 'embedding' array)
#     test_embed_returns_vector_and_dimensions (KeyError: 'embedding')
cp /tmp/emb_main.py.bak services/embedding/app/main.py
diff -q /tmp/emb_main.py.bak services/embedding/app/main.py   # identical
python3 -m unittest tests.test_embedding_service               # Ran 5, OK
rm -f /tmp/emb_main.py.bak

# 6. 브리프 수용기준 갱신 확인
git show 15389f0 -- docs/plans/04-real-vector-backend-decisions.md   # round-trip 수용기준 추가
```
