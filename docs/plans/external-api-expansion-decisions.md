# 외부 API 확장 (LLM · 임베딩 · 뉴럴 리랭커) 결정 브리프

상태: `D1~D6 승인 대기 (초안)`
계기: 오너 요청(2026-07-27) — "임베딩, 리랭커, LLM을 외부 API로 연결해서 사용할 수 있는 확장성이 되어 있는지 확인" → 확인 결과를 바탕으로 "외부 API 확장 계획을 세워보자". 착수 순서는 **인증(다중 사용자 D1~D8) 다음**으로 오너가 이미 정했다.
관련: `plans/multi-user-auth-cms-decisions.md`(시크릿 관리 재사용), `plans/04-real-vector-backend-decisions.md`(임베딩 seam·리랭커 유예 근거), HANDOFF "추적 부채"(cross-encoder 리랭커 미구현), SoT §"LLM 파이프라인 관측(KPI)"(call-site 8종).

---

## 0. 현재 상태 — 코드 실측 (무엇이 이미 있고 무엇이 막혀 있나)

착수 전 세 축을 1차 사료로 확인했다. **seam은 대체로 있으나 "외부 상용 API"를 막는 공통 공백은 두 가지 — 인증 헤더 주입 지점과 provider 선택 config.**

| 축 | seam(추상화) | wire 형식 | 인증 헤더 | provider 선택 | 결론 |
|---|---|---|---|---|---|
| **LLM** | 강함 — application은 항상 gateway 경유([`gateway_provider.py:14`](../../services/application/app/analysis/gateway_provider.py#L14)), gateway가 `LLAMA_BASE_URL`로 백엔드 교체([`llm_gateway/main.py:54`](../../services/llm_gateway/app/main.py#L54)), `LLMProvider` Protocol([`provider.py:31`](../../services/llm_gateway/app/provider.py#L31)) | **OpenAI 호환** — `/v1/chat/completions`, `choices/message/usage` 파싱([`client.py:45`](../../services/llm_gateway/app/client.py#L45)) | **없음** — `HttpxJsonTransport.post_json`이 `json=`만, `Authorization` 주입 지점 없음([`httpx_transport.py:37`](../../services/llm_gateway/app/httpx_transport.py#L37)) | **없음** — `LlamaCppProvider` 하드코딩 | keyless OpenAI 호환 서버는 **지금도 됨**(베타 12B). 상용 키 API는 헤더+config 필요 |
| **임베딩** | 있음 — `EmbeddingProvider` Protocol([`indexing/service.py:63`](../../services/application/app/indexing/service.py#L63)), `EMBEDDING_SERVICE_URL` env로 fake↔real([`main.py:1017`](../../services/application/app/main.py#L1017)) | **인하우스 전용** — `/embed`에 `{"text"}`→`{"embedding"}`([`embedding.py:47`](../../services/application/app/indexing/embedding.py#L47)). OpenAI(`/v1/embeddings`)·Cohere와 다름 | **없음** | **없음** — `RemoteEmbeddingProvider` 하드코딩 | Protocol 덕에 **새 어댑터 1개**면 붙음. 외부 API 어댑터는 0 |
| **뉴럴 리랭커** | — | — | — | — | **개념 자체가 net-new.** 현재 리랭킹은 RRF 융합만([`context_search/service.py:279`](../../services/application/app/context_search/service.py#L279)). cross-encoder는 2026-07-05 의도 유예 |

**요약**: "URL만 바꿔 외부로" 되는 건 keyless OpenAI 호환 LLM 하나뿐. 나머지는 (a) 인증 헤더 계층, (b) provider 선택 config, (c) 비-인하우스 wire 어댑터, (d) 리랭커는 삽입 지점 자체가 새로 필요.

---

## 1. 결정 항목

### D1 — 확장 범위: 어느 축을 이번에 여는가

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. LLM + 임베딩** | 두 축에 인증·provider-선택 seam 추가. 리랭커는 D5로 분리 | seam이 이미 있어 어댑터+인증만 추가하는 저비용 · "provider-agnostic"이라는 포트폴리오 스토리가 완성됨 | 리랭커는 별도 슬라이스로 미룸 |
| B. LLM만 | 생성 provider만 | 가장 작은 첫 슬라이스 · 영향 최대 | 임베딩은 그대로라 "확장성" 스토리가 반쪽 |
| C. 세 축 전부 동시 | LLM·임베딩·뉴럴 리랭커를 한 번에 | 완결성 | 리랭커는 net-new(파이프라인 삽입+평가)라 슬라이스가 크게 부풀고 성격이 이질적 |

**추천: A.** LLM·임베딩은 seam이 이미 있어 "인증 헤더 + provider 선택 config + 어댑터"라는 **동일한 확장 패턴**을 공유한다 — 한 번 설계하면 두 축에 재사용된다. 리랭커는 삽입 지점·평가 기준이 별개라(D5) 같은 슬라이스에 묶으면 두 종류의 작업이 섞인다. 포트폴리오 관점에서도 "로컬↔상용 provider를 config로 교체"가 핵심 스토리이고 그건 A로 완성된다.

### D2 — 연결 방식: generic OpenAI-호환 어댑터 vs 특정 상용 전용 어댑터

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. generic OpenAI-호환 우선** | `base_url` + `api_key`로 OpenAI 호환 엔드포인트 일반 지원. LLM은 기존 wire 파서 재사용, 임베딩은 `/v1/embeddings` 형식 어댑터 1개 | 최소 코드로 최대 커버(OpenAI·Groq·Together·OpenRouter·vLLM·로컬) · 기존 `/v1/chat/completions` 파서 그대로 | Anthropic(`/v1/messages`)·Cohere(전용 형식)는 미포함 |
| B. 특정 상용 전용 어댑터 | Anthropic·Cohere 등 각 provider별 wire 어댑터 | 해당 provider의 고유 기능(예: Anthropic 시스템 프롬프트·툴)까지 | provider마다 어댑터·유지보수 · 첫 슬라이스가 커짐 |
| C. 둘 다 | generic + 필요한 상용 전용 | 포괄적 | 범위 폭발 |

**추천: A.** OpenAI 호환은 사실상 업계 공통분모라 어댑터 하나로 대부분을 커버하고, LLM 축은 **기존 파서를 그대로 재사용**한다(추가 코드가 인증 헤더+config에 국한). Anthropic/Cohere 전용은 실제 필요가 관측될 때 같은 seam 뒤에 어댑터로 추가하면 되므로(B는 A의 상위집합이 아니라 A 이후의 additive) 지금 넣을 이유가 없다.

### D3 — 시크릿/키 관리

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. env 기반 + 인증 슬라이스의 시크릿 관리와 통합** | 키는 env(`OPENAI_API_KEY` 등), 로컬은 `.env`(커밋 금지), 배포는 인증이 도입할 시크릿 메커니즘을 재사용 | 이미 있는 `.env` 패턴 · 인증이 세션 시크릿을 도입하므로 **같은 메커니즘 한 번만 설계** · 착수가 인증 다음이라 타이밍이 맞음 | 배포 시크릿 저장소는 인증 슬라이스에 의존 |
| B. 독립 시크릿 관리 | 외부 API 전용 키 저장/주입을 따로 | 인증과 디커플 | 시크릿 처리를 두 번 설계 · 표면 중복 |
| C. 평문 config | env 없이 코드/파일에 | 가장 단순 | 키 유출 위험 · 포트폴리오/배포에 부적절 |

**추천: A.** 외부 API 키와 세션 시크릿은 **같은 문제**(비밀값을 코드 밖에서 안전히 주입)다. 인증이 먼저 착수되며 그 슬라이스가 시크릿 처리를 도입하므로, 외부 API 확장은 그 위에 얹는다. `.gitignore`의 `.env`는 이미 이 프로젝트가 쓰는 패턴이다(베타 머신 `LLAMA_BASE_URL`이 선례).

### D4 — provider 선택 구조: 전역 1개 vs call-site별

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 전역 기본 + call-site별 오버라이드(선택적, 후속)** | 1차는 전역 provider 하나. 관측 KPI의 8개 call-site별 오버라이드는 additive로 남겨 둠 | 1차가 단순 · KPI가 이미 call-site를 구분하므로 "site별 모델 비교"는 나중에 자연스럽게 열림 | site별은 지금 안 됨(설계만 열어 둠) |
| B. 처음부터 call-site별 | 8개 site 각각 provider 지정 | 세밀한 비용/품질 튜닝 즉시 | config 표면이 8배 · 1차엔 과설계(§2) |
| C. 전역 고정만 | 오버라이드 없음 | 최소 | 나중에 site별로 갈 때 재설계 |

**추천: A.** 로컬 1인/포트폴리오 단계에서 8개 site를 각각 다른 provider로 돌릴 필요는 아직 관측되지 않았다(§2). 다만 **관측 KPI가 이미 call-site를 1급 개념으로 구분**하므로("어느 site가 비싼가"가 KPI의 실제 질문), config를 전역 기본 + site 오버라이드 형태로 **설계만** 열어 두면 나중에 "site별 모델 A/B"가 재설계 없이 들어온다.

### D5 — 뉴럴 리랭커: 이번에 넣는가 + 조달 방식

현재 RRF 융합 뒤에 cross-encoder 재채점 단계가 없다. 넣는다면 **삽입 지점은 RRF 결과 뒤, `retrieve()` seam 다음**이다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 이번 범위에서 제외(유예 유지)** | D1=A(LLM+임베딩)만 하고 리랭커는 별도 슬라이스 | 성격이 다른 net-new를 분리 · 인증→외부 API 흐름이 가벼워짐 | RAG 정교화가 미뤄짐 |
| B. self-host 서비스로 추가 | `bge-reranker` 등을 임베딩 서비스와 같은 패턴의 별도 컨테이너로 | 아키텍처 일관성(임베딩 서비스 선례) · per-call 비용 0 · "인프라를 다룰 줄 안다"는 포트폴리오 스토리 | 새 서비스·모델 로딩·GPU/CPU 비용 · 슬라이스가 큼 |
| C. 외부 API로 추가 | Cohere Rerank 등을 D2 seam 뒤 어댑터로 | "상용 API 통합" 스토리 · 인프라 부담 0 | per-call 비용·키 관리 · 리랭킹 품질이 외부에 종속 |

**추천: A(지금) → 이후 B 또는 C를 별도 슬라이스.** 리랭커는 삽입 지점·오프라인 평가(리랭킹이 실제로 Gate 품질을 올리는지)까지 필요한 **독립 기능**이라, LLM/임베딩 provider 확장과 한 슬라이스에 묶으면 두 성격이 섞인다. 별도로 갈 때는, 이 프로젝트가 이미 임베딩을 self-host 서비스로 돌리는 선례가 있어 **B(self-host)가 아키텍처적으로 일관**되고 포트폴리오에서 "로컬 RAG 풀스택"을 보여준다. 단 외부 API 확장이 목적이라면 C를 같은 seam 뒤 어댑터로 두는 것도 유효 — D2의 generic 어댑터 패턴과 대칭이다.

### D6 — 인증(D1~D8)과의 선후

오너가 이미 "인증부터, 그다음 외부 API"로 정했다. 이 브리프는 그 순서를 전제로 하며, **D3(시크릿)이 인증 슬라이스의 산출물을 재사용**하도록 설계된 것이 그 선후의 직접적 이득이다. 인증이 시크릿 저장/주입을 세우고, 외부 API 키가 그 위에 얹힌다. 별도 결정 불요 — 기록만.

---

## 2. 추천 요약 (한눈에)

- **D1=A** — LLM + 임베딩을 이번 확장 범위로. 리랭커는 분리.
- **D2=A** — generic OpenAI-호환 어댑터 우선(base_url + api_key). Anthropic/Cohere 전용은 후속 additive.
- **D3=A** — env 기반 키, 인증 슬라이스의 시크릿 관리 재사용.
- **D4=A** — 전역 기본 + call-site별 오버라이드는 설계만 열어 두고 후속.
- **D5=A(지금 제외)** — 뉴럴 리랭커는 별도 슬라이스, 이후 self-host(B) 우선 검토.
- **D6** — 인증 다음(결정 완료, 기록만).

## 3. 예상 작업 표면 (승인 시, 추정)

- **인증 헤더 계층**: `HttpxJsonTransport`/`RemoteEmbeddingProvider`에 `headers`(Authorization) 주입 경로 추가. 가장 작은 공통 변경.
- **provider 선택 config**: gateway는 `LLM_PROVIDER`(llamacpp|openai_compatible) + `LLM_API_KEY`, 임베딩은 `EMBEDDING_PROVIDER` + 형식 어댑터. 미설정 시 현행(keyless 인하우스) 그대로 — 하위호환.
- **임베딩 OpenAI-호환 어댑터**: `/v1/embeddings` 요청/응답(`{"input"}`→`{"data":[{"embedding"}]}`) 어댑터 1개, `EmbeddingProvider` Protocol 구현.
- **회귀**: provider 선택 분기(설정↔미설정), 인증 헤더 주입, 어댑터 wire 계약 round-trip, 미설정 시 현행 무변 over-strict.
- **관측 KPI**: provider/model이 레코드에 남는지 확인(현재 `model`은 응답에서 옴 — provider 라벨 추가 여부는 D4 오버라이드와 함께).

## 4. Follow-up considerations (열어 둘 문)

- **provider별 실패 taxonomy 정합**: 상용 API의 429(rate limit)·401(auth)·5xx를 기존 `ProviderError` 계보에 어떻게 매핑할지 — 인증 헤더가 틀리면 401이 오는데 이걸 provider_error로 셀지 config 오류로 셀지.
- **call-site별 provider**(D4-후속): KPI가 "site별 비용/품질"을 이미 물을 수 있으므로 config만 열면 A/B가 열린다.
- **임베딩 차원 불일치**: 외부 임베딩(예: OpenAI 1536-dim)이 현재 Chroma 컬렉션(1024-dim BGE-m3-ko)과 다르면 재색인이 필요 — `expected_dimensions` 가드가 이미 fail-fast로 잡는다([`embedding.py:78`](../../services/application/app/indexing/embedding.py#L78))는 점을 재색인 계획과 함께 봐야 함.

## 5. Deferred / out of scope (이번에 정하지 않는 것)

- 뉴럴 리랭커 구현 자체(D5=A로 분리 — 별도 브리프).
- Anthropic/Cohere 등 비-OpenAI-호환 전용 어댑터(D2 후속).
- call-site별 provider 오버라이드 구현(D4 설계만).
- 외부 임베딩 전환 시 대규모 재색인 마이그레이션 절차(차원이 바뀌는 경우에 한함).
