# Decision brief — 임베딩 어댑터 슬라이스

> 작성 2026-08-18. **오너 결정 대기.** 부모 결정은 [`external-api-expansion-decisions.md`](external-api-expansion-decisions.md) D1~D4(2026-07-27), 직전 결정은 [`reranker-slice-decisions.md`](reranker-slice-decisions.md) 결정 1=A(2026-08-18, *"임베딩 어댑터 먼저"*)다. **이 문서는 그 둘을 뒤집지 않는다** — 그 둘이 정하지 않고 남긴 **어댑터의 모양·배치 전략·차원 전환·조립 누락 방지**를 정한다.
>
> **오너가 준 방향**(2026-08-18): *"곧바로 리랭커 외부 API를 찾아서 연결할꺼니까 참고로 알고있어. **임베딩도 마찬가지고**."* — 즉 **외부 임베딩 API 로 붙인다**가 전제이고, 이 브리프는 그 방법을 정한다.

## 결정 필요

**OpenAI 형식 임베딩 API 를 어떤 모양으로 붙이고, 단건 seam 에 배치를 어떻게 다루며, 차원이 바뀌는 것을 어떻게 처리하고, 조립 지점 6곳의 누락을 무엇으로 막는가.**

넷 다 정해진 적이 없고, 그 넷이 지금 구현을 막는다.

---

## 배경 — 지금 무엇이 있고 무엇이 없는가 (2026-08-18 코드 실측)

**있는 것: 자체 형식 어댑터 하나.** [`RemoteEmbeddingProvider`](../../services/application/app/indexing/embedding.py#L23) 가 아는 계약은 **우리 임베딩 서비스의 형식**이다.

| | 우리 형식 (지금) | OpenAI 형식 (붙이려는 것) |
|---|---|---|
| 경로 | `POST /embed` | `POST /v1/embeddings` |
| 요청 | `{"text": "…"}` (**단건**) | `{"input": …, "model": …}` (**단건 또는 배열**) |
| 응답 | `{"embedding": [...], "dimensions": N}` | `{"data": [{"embedding": [...], "index": 0}], "usage": {…}}` |
| 인증 | **없음** | `Authorization: Bearer …` |
| 모델 지정 | 서버가 env 로 안다(`EMBEDDING_MODEL_NAME`) | **요청마다 보낸다** |

**넷이 전부 다르다 — 경로·요청 키·응답 구조·인증.** 그래서 [`docker-compose.external.yml`](../../docker-compose.external.yml) 이 *"`EMBEDDING_SERVICE_URL` 에 넣을 수 있는 것은 **그 계약을 말하는 엔드포인트**뿐"* 이라고 주석에 못박아 뒀다(§"아직 안 되는 것"). **이 슬라이스가 그 제약을 없앤다.**

**seam 은 단건·동기다.** Protocol 은 `embed(self, text: str) -> tuple[float, ...]` 이고 **세 곳에 같은 모양으로 선언**돼 있다([`analysis/semantic_matcher.py:28`](../../services/application/app/analysis/semantic_matcher.py#L28) · [`indexing/memory_index.py:58`](../../services/application/app/indexing/memory_index.py#L58) · [`indexing/service.py:63`](../../services/application/app/indexing/service.py#L63)). 동기인 것은 의도다 — 모듈 docstring 이 *"async ripple 을 피하려고 sync httpx"* 라고 적는다.

**★ 조립 지점이 여섯이다 — 이것이 이 슬라이스의 가장 큰 위험이다.**

| # | 자리 | 형태 |
|---|---|---|
| 1 | [`main.py:1126`](../../services/application/app/main.py#L1126) | 앱. `EMBEDDING_SERVICE_URL` 이 **빈 값이면 fake 로 내려간다** |
| 2 | [`scripts/index_sync_worker.py:66`](../../scripts/index_sync_worker.py#L66) | 색인 워커 |
| 3 | [`scripts/phase2b5_reindex_memory.py:58`](../../scripts/phase2b5_reindex_memory.py#L58) | memory 재색인 |
| 4 | [`scripts/phase2b5_reindex_candidate.py:59`](../../scripts/phase2b5_reindex_candidate.py#L59) | candidate 재색인 |
| 5 | [`scripts/phase2b7_character_alias_live_smoke.py:170`](../../scripts/phase2b7_character_alias_live_smoke.py#L170) | live smoke |
| 6 | [`scripts/calibrate_character_identity_threshold.py:20`](../../scripts/calibrate_character_identity_threshold.py#L20) | 임계값 보정 — **★ 지금 깨져 있다(아래)** |

**차원 가드는 클라이언트 쪽에 있다.** `expected_dimensions` 가 맞지 않으면 `EmbeddingProviderError` 로 **fail-fast** 한다([:78](../../services/application/app/indexing/embedding.py#L78)). 값은 `EMBEDDING_DIMENSIONS` (기본 **1024** = `dragonkue/BGE-m3-ko`)이고 **자리 5곳이 각자 읽는다.**

**없는 것: 배치.** 지금은 텍스트 하나에 HTTP 요청 하나다. 재색인 스크립트는 그 호출을 **루프로 돈다.**

## ★ 착수 전 알아야 하는 실측 하나 — 조립 지점 6번은 이미 깨져 있다

[`scripts/calibrate_character_identity_threshold.py:20`](../../scripts/calibrate_character_identity_threshold.py#L20) 이 `RemoteEmbeddingProvider(args.embedding_url)` 로 **위치 인자**를 넘긴다. 그런데 생성자는 **키워드 전용**(`def __init__(self, *, base_url: str, …)`)이라 **호출 즉시 `TypeError`** 다.

```
TypeError: RemoteEmbeddingProvider.__init__() takes 1 positional argument but 2 were given
```

- **언제부터**: `a74c4c7`(2026-07-12, *"feat: add character homonym reconciliation"*) 이후 계속. **테스트가 이 스크립트를 부르지 않아**(`grep tests/` 0건) 아무도 몰랐다.
- **이 브리프가 고치지 않는다**(CLAUDE.md §3 — 남의 결함은 알리되 손대지 않는다). **다만 이 슬라이스가 조립 지점 6곳을 전부 만지므로 그때 함께 닫는 것이 자연스럽다** — 결정 4 의 선택지가 그것을 다룬다.
- **★ 시사점이 더 중요하다**: 조립 지점이 **한 달 넘게 깨진 채로 green** 이었다. 결정 4(조립 가드)가 있어야 하는 이유가 추측이 아니라 **이미 일어난 사고**다.

---

## 결정 1 — 어댑터를 어디에 두는가

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 앱 안에 두 번째 Provider 클래스** | `OpenAIEmbeddingProvider` 를 `indexing/embedding.py` 에 나란히 두고 **env 로 조립에서 고른다** | 리랭커 결정 2=A 와 **같은 형태**(Protocol 뒤 나란히) · 이 저장소의 선례(`RemoteEmbeddingProvider` ↔ `DeterministicFakeEmbeddingProvider`) · 새 컨테이너 0개 | 조립 지점 6곳이 **각자 골라야** 한다(결정 4 가 처방) |
| B. 기존 클래스에 형식 분기 | `RemoteEmbeddingProvider` 안에서 `wire_format` 로 갈린다 | 조립이 안 바뀐다 | **한 클래스가 두 계약**을 안다 · 응답 파서가 분기투성이 · 형식이 셋이 되면 무너진다 |
| C. gateway 서비스에 임베딩 경로 추가 | LLM 처럼 `llm_gateway` 가 임베딩도 프록시한다 | 인증 키가 **앱 밖**에 머문다 · LLM 과 대칭 | **gateway 의 책임이 바뀐다**(LLM 프록시 → 범용 프록시) · 홉이 하나 는다 · 배포에서 gateway 가 임베딩 장애의 단일 지점이 된다 |
| D. 임베딩 서비스가 외부로 프록시 | 우리 `embedding` 컨테이너가 외부 API 앞에 선다 | 앱 코드 0줄 | **배포에서 그 컨테이너를 끄는 것이 목적**인데 다시 켜야 한다(external override 와 정면 충돌) |

**추천: A.** 이유 셋이다. ① **이 저장소가 이미 그 형태**다 — Protocol 뒤에 provider 를 나란히 두고 **env 유무로 조립에서 고른다**. ② **리랭커 결정 2=A 와 같은 규율**이라 두 축이 같은 모양으로 자란다. ③ **D 는 external override 의 목적과 충돌**하고(`embedding` 을 profile 뒤로 보낸 것이 그 파일의 존재 이유다), C 는 gateway 의 책임을 바꾼다 — **지금 필요하지 않은 변경**이다.

> **C 를 완전히 버리지는 않는다.** 인증 키를 앱 밖에 두는 것은 실제 이점이고, **리랭커까지 외부로 나가면 프록시가 셋이 된다.** 그때 *"범용 외부 프록시"* 를 다시 볼 만하다 — 아래 §후속 고려.

## 결정 2 — 배치를 지금 다루는가

seam 이 단건(`embed(text) -> vector`)인데 OpenAI 형식은 배열을 받는다. **재색인은 수천 건 루프**라 여기서 비용·시간이 갈린다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 지금은 단건만. seam 무변** | 어댑터가 `{"input": text}` 를 보내고 `data[0].embedding` 을 읽는다 | **슬라이스가 가장 작다** · Protocol 세 곳·호출부 전부 무변 · 되돌리기 쉽다 | 재색인이 **건당 1 HTTP** — 외부 API 에서는 지연·요금이 그대로 곱해진다 |
| B. `embed_many` 를 Protocol 에 더한다 | 배치 메서드를 선언하고 재색인 경로가 그것을 쓴다 | 재색인이 빨라지고 싸진다 | **Protocol 이 세 곳**이라 셋 다 바뀐다 · 호출부·fake·테스트가 함께 움직인다 · **지금 측정된 병목이 아니다** |
| C. 어댑터 내부 버퍼링 | 호출을 모았다가 보낸다 | seam 무변 + 배치 이득 | **동기 단건 seam 에 버퍼링은 거짓말**이다(호출자는 즉시 결과를 기대한다) · 순서·에러 대응이 복잡 |

**추천: A.** ① **B 는 지금 병목이라는 증거가 없다** — 재색인 지연을 아무도 안 쟀고, CLAUDE.md §2 는 요청되지 않은 유연성을 금한다. ② **A → B 는 additive** 다(Protocol 에 메서드를 더하는 것이라 기존 호출부가 안 깨진다). 반대로 B 를 먼저 하면 **측정 없이 세 Protocol 을 건드린다.** ③ **C 는 seam 의 계약을 어긴다.**

**★ 다만 A 를 고르면 그 대가를 적어 둬야 한다** — 외부 API 는 **호출 수가 곧 요금**이다. 재색인 한 번이 수천 호출이면 그것이 눈에 보이는 비용으로 온다. **트리거를 함께 적는다: 재색인을 실제로 돌려 지연·호출 수를 재고, 그 숫자가 아프면 B 를 연다.**

## 결정 3 — 차원이 바뀌는 것을 어떻게 다루는가

**이것이 이 슬라이스의 숨은 본체다.** 지금 차원은 **1024**(`BGE-m3-ko`)인데 외부 모델은 대개 다르다. 차원이 바뀌면 **이미 저장된 벡터가 전부 무효**다 — 다른 공간의 좌표라 비교가 의미를 잃는다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 차원 불일치는 기동 거부(현행 가드 유지) + 재색인은 수동** | `expected_dimensions` 를 그대로 두고, 바꿀 거면 `EMBEDDING_DIMENSIONS` 를 함께 바꾸고 **기존 재색인 스크립트로 다시 만든다** | **코드 0줄** — 가드도 스크립트도 이미 있다 · fail-fast 라 조용한 오염이 없다 · 저장소 관례와 일치 | 사람이 순서를 지켜야 한다(env 바꾸고 재색인 안 하면 **옛 벡터와 새 질의가 섞인다**) |
| B. 차원을 컬렉션 메타데이터에 기록하고 자동 감지 | 저장 시 차원을 남기고 불일치를 런타임에 잡는다 | 사람 실수를 코드가 잡는다 | **새 상태를 하나 만든다** · chroma·mongo 양쪽에 이관이 필요 · 지금 이 사고가 난 적이 없다 |
| C. 재색인 자동 트리거 | 차원이 바뀌면 스스로 다시 만든다 | 손이 안 간다 | **수천 건 재색인이 기동에 붙는다** · 실수로 env 를 바꾸면 멀쩡한 색인을 날린다 |

**추천: A.** ① **가드와 스크립트가 이미 다 있다** — `expected_dimensions` fail-fast 와 `phase2b5_reindex_*` 둘. 새로 만들 것이 없다. ② **B·C 는 지금 없는 문제를 푼다**(§2 위반). ③ **A 의 약점은 문서로 닫는 종류**다 — 순서를 runbook 한 줄로 적으면 된다.

**★ 그러나 A 를 고르면 반드시 함께 적어야 하는 것이 있다 — "섞인 색인" 은 조용하다.** 차원이 맞으면 가드가 통과하므로, **차원이 같은 다른 모델**로 바꾸면(예: 1024 짜리 다른 모델) 가드는 아무 말도 안 하고 **옛 벡터와 새 질의가 한 공간인 척 섞인다.** 검색은 계속 결과를 내고 **품질만 조용히 떨어진다.** 그래서 규칙은 *"차원이 바뀌면 재색인"* 이 아니라 **"모델이 바뀌면 재색인"** 이다. 이 문장이 runbook 에 그대로 들어가야 한다.

## 결정 4 — 조립 누락을 무엇으로 막는가

조립 지점이 **여섯**이고, 그중 하나는 **한 달 넘게 깨진 채 green** 이었다(위 §착수 전 알아야 하는 실측). 이 저장소는 같은 병을 `ObservedProvider` 에서 이미 겪었고 처방이 **조립 가드**였다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 조립 헬퍼 하나 + 전수 가드** | `build_embedding_provider_from_env()` 를 한 곳에 두고 6 자리가 그것을 부른다. 가드가 **"직접 생성자를 부르는 자리가 없는가"** 를 단정 | **자리가 하나가 된다** · env 해석 규칙이 갈라지지 않는다(지금 `EMBEDDING_DIMENSIONS` 를 5곳이 각자 읽는다) · **6번의 결함이 구조적으로 불가능**해진다 | 스크립트가 앱 모듈을 하나 더 import 한다(이미 하고 있다) |
| B. 가드만 추가 | 6 자리를 그대로 두고 리터럴을 단정하는 셀 | 변경이 가장 작다 | **중복이 남는다** — 새 자리가 생기면 목록에 등재해야 하고, 등재를 잊으면 가드가 침묵한다(리랭커 브리프가 `typeScale` 이관 목록에서 실측한 M5 함정) |
| C. 아무것도 안 한다 | 지금처럼 | 0줄 | **6번이 이미 답이다** — 안 하면 또 난다 |

**추천: A.** ① **결함이 이미 실증됐다** — 추측이 아니다. ② **env 해석이 다섯 곳에 흩어져 있는 것 자체가 부채**다(`EMBEDDING_DIMENSIONS` 기본값 `"1024"` 이 다섯 번 적혀 있다. 하나를 고치고 넷을 잊으면 조용히 갈린다). ③ 이 저장소의 처방이 이미 **조립 가드**로 정해져 있다(`ObservedProvider` 선례).

**★ 다만 A 의 범위를 넘기지 말 것.** 헬퍼는 **env → provider** 만 한다. 재색인 정책·차원 결정·배치를 여기 넣으면 그것이 두 번째 조립 지점이 된다.

---

## 권고 요약

| 결정 | 추천 | 한 줄 이유 |
|---|---|---|
| 1. 어댑터 자리 | **A — 앱 안 두 번째 Provider** | 이 저장소가 이미 쓰는 형태 · 리랭커와 같은 규율 · 새 컨테이너 0 |
| 2. 배치 | **A — 지금은 단건, seam 무변** | 병목이 측정된 적 없다 · A→B 는 additive |
| 3. 차원 전환 | **A — fail-fast 가드 + 수동 재색인** | 가드도 스크립트도 이미 있다. **규칙은 "모델이 바뀌면 재색인"** |
| 4. 조립 누락 | **A — 헬퍼 하나 + 전수 가드** | 조립 지점 6곳 중 하나가 **한 달 넘게 깨져 있었다** |

**넷 다 "가장 작은 슬라이스" 방향이다.** 이 슬라이스가 여는 것은 *"외부 임베딩 API 에 붙는다"* 하나이고, 배치·자동 재색인·범용 프록시는 전부 **트리거와 함께 미룬다.**

## 후속 고려 — 이 결정이 열어 둬야 하는 문

- **★ 인증 키가 앱 프로세스 안으로 들어온다**(결정 1=A 의 대가). 지금 LLM 키는 gateway 에 있고 앱에는 없다. D3=A(env 기반 키)라 형태는 정해져 있지만, **키를 읽는 프로세스가 하나 느는 것**은 사실이라 적어 둔다. **리랭커까지 외부로 나가면 앱이 키 둘을 든다** — 그때 결정 1 의 C(gateway 를 범용 외부 프록시로)를 다시 볼 값이 생긴다.
- **`docker-compose.external.yml` 의 주석이 거짓이 된다.** §"아직 안 되는 것" 이 *"임베딩은 아직 진짜 외부 API 에 못 붙는다"* 고 적는데, 이 슬라이스가 끝나면 **그 문단을 고쳐야 한다.** 안 고치면 다음 사람이 없는 제약을 믿는다.
- **`EMBEDDING_SERVICE_URL` 의 의미가 둘이 된다** — 자체 형식 주소인가 OpenAI 형식 주소인가. **변수를 하나 더 둘지 형식을 별도 env 로 뺄지**는 결정 1=A 를 고른 뒤 구현에서 정할 문제이며, **external override 의 `:?` 필수 표기와 짝**이다(env 표기 규칙: `os.environ.get(x, DEFAULT)` 면 콜론, `if not …get(x)` 면 dash — 지금 `_build_embedding_provider` 는 **후자**라 base 가 dash 다).
- **리랭커 평가 하네스가 임베딩에서 먼저 쓰일 수 있다**(리랭커 결정 4-② 의 열어 둔 문). 임베딩 모델을 바꾸면 *"검색 순위가 정답을 얼마나 앞에 두는가"* 가 그대로 필요하다 — **이 슬라이스가 그 하네스의 첫 고객이 될 수 있다.**

## 유예 / 범위 밖 — 이 브리프가 정하지 않는 것

- **어떤 외부 임베딩 API 를 쓸지** — 오너가 조달 중이다. D2=A(generic OpenAI 호환)라 **특정 벤더 어댑터는 additive** 다.
- **`scripts/calibrate_character_identity_threshold.py:20` 의 결함 수정** — 결정 4=A 를 고르면 헬퍼 이관으로 **함께 닫힌다.** 다른 결정을 고르면 **별도 항목으로 남는다**(지금은 추적 부채로만 등재).
- **배치(`embed_many`)** — 결정 2=A 면 미룬다. **트리거 = 재색인 지연·호출 수 실측이 아플 때.**
- **차원 메타데이터·자동 재색인** — 결정 3=A 면 미룬다. **트리거 = "모델만 바꾸고 재색인을 잊는" 사고가 실제로 날 때.**
- **재색인 성능·비용 실측** — **아무도 안 쟀다.** 외부 API 로 붙은 뒤가 재는 자리다.
- **`embedding` 컨테이너를 언제 없앨지** — 로컬은 계속 쓴다(감마처럼 키가 없는 환경). 배포에서만 profile 뒤다.

## 승인 전 보류

이 문서의 결정 1~4 가 확정되기 전에는 **코드를 쓰지 않는다.** 특히 **결정 4 는 되돌리는 비용이 크다** — 6 자리를 헬퍼로 모았다가 되돌리려면 6곳을 다시 벌려야 한다. 그리고 **결정 3 은 잘못 고르면 조용하다**(섞인 색인은 실패가 아니라 품질 저하로만 나타난다).

**감마(GPU 없음)에서 할 수 있는 것은 여기까지다** — 어댑터 구현·재색인 실측은 외부 키 또는 알파/베타가 필요하다.
