# 2026-08-22 작업 로그 (베타)

## Goals

- 오너 요청: 외부 API용 **폴백 장치** — API 키 리스트(1개만 있어도 동작) + 모델 리스트(0번째
  기본, 나머지 폴백), 키당 기본 RPM 30, 폴백 우선순위 ① 키 교체 ② 모델 교체.
- 계기: 배포 서버가 외부 API로만 돌는데(`docker-compose.external.yml`) 세 축(LLM 게이트웨이·
  임베딩·리랭커) 모두 단일 키·단일 모델이라 429/5xx 한 번에 호출이 죽는다.

## Completed work

슬라이스 8단계, 단계마다 체크포인트 커밋(오너 규칙 §6 — 뮤테이션 검증의 안전망).

### Task 1 — `KEY_REJECTED` 오류 분류 (커밋 d8ba6e7)

401/403을 "요청 거부"(`REQUEST_REJECTED`)에서 "키 거부"(`KEY_REJECTED`)로 분리 — 폴백 계층이
"키를 바꾸면 고쳐진다"를 판단하는 신호. 부모 브리프(`external-api-expansion-decisions.md`) §4가
유예했던 매핑 질문을 닫는다. 게이트웨이 표면은 **502** — 클라이언트(앱) 쪽 자격증명 문제가
아니기 때문(401은 "너의 인증을 고쳐라"라는 거짓 메시지가 된다). 집합-완전성 테스트 4곳
(enum 리터럴·앱/게이트웨이 상태 매핑)을 같은 커밋에서 갱신 — 이 슬라이스에서 예상치 못했던
발견: 새 enum 값을 더하면 **두 개의 set-전수 셀이** 깨진다(Plan 검증이 잡음).

### Task 2 — `HttpxJsonTransport` 인증 헤더 (커밋 c374194)

`headers` 파라미터 추가 — 부모 브리프 §0가 지목한 "인증 헤더 주입 지점 없음"을 닫는다.
기본 `None`이라 직접 생성하는 스크립트 4곳과 로컬 llama 경로는 무변.

### Task 3 — `FallbackProvider` (커밋 14fed04)

`services/llm_gateway/app/fallback.py` 신규. 시도 순서 a1→b1→c1→a2→b2→c2, 키당 RPM 슬라이딩
60초 창, 401/403 장기(600s)·429 단기(60s) 쿨다운, 체인 전체가 `asyncio.timeout` 하나를 공유
(N 조합이 지연을 배가하지 않게). 구현 중 잡은 설계 결함: `KEY_REJECTED`는 `retryable=False`라
즉시-중단 분기에 걸려 회전하지 않았다 — "키 치명"과 "요청 치명"을 갈라 lock(테스트 2방향이
각각 잠금). 키 값은 이 클래스가 아예 모른다(구조적 비유출).

### Task 4 — 게이트웨이 조립 (커밋 2e48f90)

`_build_provider()`가 `LLAMA_API_KEYS`·`LLAMA_MODELS`·`LLAMA_KEY_RPM`을 읽는다. **키 ≤1 且
모델 ≤1이면 오늘과 동일한 단일 provider**(로컬 llama 무변 — over-strict 총괄 가드). 1키는
Bearer 헤더만. lifespan은 transport 전부 종료로 일반화. `RPM < 1`은 기동 거부.

### Task 5 — 임베딩 키 회전 (커밋 a667fd7)

`services/application/app/key_rotation.py`(동기 창 계수기·env 파싱 — provider 생성자는 절대
부르지 않는다, AST 조립 가드 호환) + `KeyRotatingEmbeddingProvider`. 오류 구조화:
`EmbeddingProviderError`에 `status_code`/`network` 추가(메시지 문자열 불변), 차원 가드·400류는
회전 없이 즉시 재발생. `EMBEDDING_API_KEYS` + native 형식은 기동 거부. **계획에서 한 치 조정**:
회전 래퍼를 key_rotation.py가 아니라 각 축 파일에 뒀다 — 에러 클래스를 import하면 조립
사이클이 생긴다.

### Task 6 — 리랭커 키 회전 (커밋 99b1ccf)

같은 패턴(`RERANK_API_KEYS`). URL 없음이 우선한다 — 키만 있다고 리랭킹이 켜지지 않는다
(결정 2=A 계약 유지). 소진은 기존 fail-open 경계가 융합 순서로 내려준다.

### Task 7 — compose env 통과 (커밋 c73d351)

base(gateway) 3종 + external 3서비스 × 4종. 표기는 코드 읽기 방식을 따른다: 리스트는 대시
(빈 값 = unset), RPM은 콜론 `:-30`(`_env_float`은 빈 값에 `float("")` 크래시 — Plan 검증이
잡은 정정). 표기 잠금 셀 확장.

### Task 8 — 문서

`docs/plans/external-api-fallback-decisions.md` 신규(정책 정본), README env 표 + 폴백 절,
plans 인덱스 등재, CHANGELOG, HANDOFF 갱신.

## Issues found

- **enum 값 추가는 set-전수 셀 2곳을 깨뜨린다**(`test_llm_provider_errors.py` 16-27·127-139) —
  예상 셀(transport 매핑) 말고도 상태 매핑 전수 셀이 있었다. 계약 enum을 늘리는 다음 슬라이스도
  이 비용을 미리 세야 한다.
- **`retryable` 플래그 하나가 두 질문을 겹쳐 입고 있다** — "이 요청을 그대로 재시도하면 되는가"(
  앱 계약)와 "조합을 바꾸면 고쳐지는가"(폴백 내부). `KEY_REJECTED`에서 둘이 갈라졌고, 폴백 루프는
  코드로(key_fatal) 갈랐다. 후속 축에서도 이 긴장은 재현될 수 있다.
- WSL `/mnt/f`에서 Edit 도구가 성공한 쓰기에 대해 가끔 ENOENT를 반환한다(README·docker-compose.yml
  에서 2회). 적용 여부는 grep으로 확인했다 — 이 세션에서만 유효한 환경 노이즈.

## Decisions

### D-2026-08-22-a — 폴백 정책 전체 (오너)

키 리스트(1개 OK)·모델 리스트(0번째 기본)·키당 RPM 30·폴백 순서 ①키 ②모델·시도 순서
a1→b1→c1→a2→b2→c2. 원문: *"키가 abc 모델이 12면 a1 b1 c1 a2 b2 c2 이런식으로 시도하라는 뜻이야."*

### D-2026-08-22-b — 시작 키는 라운드로빈 (오너, 같은 날 정정)

최초 안 "랜덤" → 정정 *"랜덤이라기보다는 라운드로빈 배분으로, 한 곳으로 집중되지 않게"*.
랜덤은 통계적으로만 분산, 라운드로빈은 정확히 분산 — 배분이 곧 RPM 예산이므로 정확한 쪽.
부수 효과로 테스트 결정성 확보(rng 시드 주입 불필요).

### D-2026-08-22-c — 범위: 세 축 모두, 임베딩·리랭커는 키만 (오너)

LLM 게이트웨이(키×모델) + 임베딩·리랭커(키만). 임베딩 모델 폴백은 차원 가드 설계(2026-08-19
결정 3=A — 모델이 바뀌면 재색인)와 충돌하므로 제외. 축마다 독립 슬라이스였던 D1 선례와 달리
한 슬라이스에 묶은 것은 오너가 이날 명시적으로 선택(구현은 축별 파일·커밋으로 분리).

### D-2026-08-22-d — 전 조합 소진 시 fail-fast (오너)

대기 없이 retryable 오류로 즉시 반환. 앱에 이미 provider_retry_cap 재시도 예산이 있고,
게이트웨이가 창이 풀릴 때까지 붙잡으면 다른 요청의 예산도 함께 태운다.

### D-2026-08-22-e — `KEY_REJECTED` → HTTP 502 (구현자, 오너 정책에서 유도)

401이 아닌 이유: 게이트웨이의 클라이언트(앱)는 게이트웨이에 자격증명이 없다 — 401은 "너의
인증을 고쳐라"라는 거짓 메시지. 실패한 자격증명은 게이트웨이→상류 방향이므로 502가 정직하다.
앱 쪽 기본 매핑도 502(단순 일치, 별도 합의 불요).

## Verification

- **전체 백엔드 스위트: `2301 passed · 119 skipped · 0 failed`**(3:09). 슬라이스 전에는
  이 머신에 mypy 가 없어 `test_typecheck` 3셀이 환경 실패 중이었다 — 가드의 안내대로
  `requirements-dev.txt`(mypy)를 사용자 사이트로 설치해 복구했다(PEP 668 환경이라
  `--user --break-system-packages`). 설치 후 mypy 가 잡은 **내 코드의 타입 오류 2건**을
  고쳤다(`keys` 리스트의 `str | None` 어노테이션 — embedding·rerank).
- **문서 인덱스 개수 셀 4건**: 브리프 추가로 전체 108→109·브리프 90→91, README 두 곳·
  plans/README 한 곳 갱신(세는 규칙은 `test_docs_indexes.py` 가 소유).
- 신규 테스트 파일: `test_llm_fallback.py`(18셀)·`test_llm_provider_env.py`(7셀)·
  `test_key_rotation.py`(임베딩+리랭커) — 전 셀 양방향(under-strict/over-strict) 코멘트.
- **뮤테이션 회귀 가드(문서 커밋 후, 전부 커밋 위에서)**:
  - M1 `fallback.py` 루프 순서 뒤집기(키↔모델) → `test_attempt_order_is_keys_first_then_models`
    재실패 ✓ → 복구 ✓
  - M2 `embedding.py` 회전 루프에서 `if not exc.key_rotatable: raise` 제거(차원 가드 오류까지
    삼킴) → `test_a_dimension_guard_error_does_not_rotate` 재실패 ✓ → 복구 ✓
  - M3 `main.py` 무설정 단일 provider 분기(`len(keys) <= 1 and len(models) <= 1`)를 `False`로
    → `test_no_keys_no_models_builds_today_s_provider` 재실패 ✓ → 복구 ✓
  - 각 복구 후 `git status --short` 빈 확인(오너 규칙 §6 — 커밋 후 뮤테이트, 복구는 HEAD 로).
- 기존 스위트 무변 통과: `test_llm_gateway_app`·`test_embedding_assembly`(AST 가드 포함)·
  `test_rerank`·`test_compose_backend_env`(표기 잠금)·`test_httpx_transport`.

## [홈서버 세션 — 같은 날 추가] 홈서버 배포 시험 기동 (오너 요청 — **접속 정보·주소는 기입하지 않는다**)

오너: *"내 홈서버에서 테스트 해볼꺼야. 개인정보니까 워크로그나 문서에는 기입하지 말고,
네가 들어가서 어떤게 필요할지 확인해봐. 몽고db는 떠있어서 굳이 또 다른 몽고 DB 띄울
필요까지는 없을꺼같고 엘라스틱 서치는 거기서 빌드 해야하고."* — SSH 접근 제공받아
직접 진행. 서버 특성(RAM 7.5G, 기존 컨테이너 다수)이 모양을 정했다:

- **배포 모양 = base + 서버 전용 override**(이 파일들은 **서버에만 있고 repo 에
  미커밋** — 개인정보). override 내용: `embedding` 서비스를 프로파일 밖으로(그 머신은
  BGE 모델을 내리지 않는다 — 앱은 구글 임베딩만 씀, RAM 절약) + `application`·`worker`·
  `generation_worker`의 `depends_on: !override`(embedding 대기 제거).
- **몽고 재사용은 사실상 불가** — 서버의 공유 몽고는 인증 걸려 있고(자격증한 없음),
  우리 앱은 레플리카셋(트랜잭션)이 필수라 공유 인프라에 rs 를 켜는 것은 침범.
  스택 전용 mongo 를 127.0.0.1:27520 에(기존 27017 과 무충돌). 오너 희망과 달라진
  점 — 사유를 보고했다.
- ES(nori) 는 그 머신에서 빌드(compose 빌드로 자연히 해결) · chroma/mongo 스택 안.
- 코드는 rsync 로 전송(HEAD `f67b46b` 동일), 서버 .env 는 구글 LLM·임베딩 블록만
  (리랭커 없음 = 기본). external override 의 사전 검증도 병행(스토어 없으면 `:?`
  기동 거부 발화 확인 + 스토어 플레이스홀더로 전 env 정합 렌더 — LLM·임베딩·리랭커
  off 전부 예상값).

**검증 결과(전부 통과)**: 9컨테이너 전 healthy(embedding 컨테이너 없음) · 게이트웨이
실호출 `gemma-4-31b-it` 응답 · 임베딩 실호출(5키 회전 래퍼, 1536차원) · 앱 /health ok ·
프론트 200 · RAM 3.2G/7.5G 사용(임베딩 컨테이너 제외 효과).

## [알파 세션 3 — 같은 날 추가] 임베딩 구글 전환 시행 (gemini-embedding-2 · 1536차원)

오너 결정(AskUserQuestion): **차원 1536, 지금 착수.** 검토 결론("전용 어댑터 불필요 —
어댑터 확장 2건")을 그날 바로 시행했다.

1. **어댑터 확장**(커밋 e952506): `_embeddings_endpoint` 경로 정규화(구글
   `/v1beta/openai` 루트 인식 — 호스트 루트만 넣으면 404) + `OpenAIEmbeddingProvider`가
   `EMBEDDING_DIMENSIONS` 값을 요청의 `dimensions`로 전송(안 보내면 구글 기본 3072).
   base compose 3서비스에 임베딩 API env 5종 통과 — **in-stack chroma/es 를 유지한 채
   외부 임베딩만** 쓰는 길(external override 와 병합 시 override 승리).
2. **.env 전환** → 실조립 실호출 2회: `KeyRotatingEmbeddingProvider`(키 5개), **1536차원**.
3. **스택 재빌드**(코드+env) → **크로마 볼륨 와이프**(`ai_writte_system_chroma_data` —
   기존 1024차원 BGE-m3 벡터. 옆 프로젝트 볼륨 `agent-memory-system_chroma_data` 는
   무손상). 컬렉션은 첫 삽입 벡터가 차원을 정한다.
4. **재색인**: application 컨테이너 안에서 44개 프로젝트 전부 memory+candidate 스크립트
   실행(정본 8건·후보 53건 upsert — 멱등).
5. **검증**: `memory_vectors` count=8 dims=1536 · `candidate_vectors` count=53 dims=1536 ·
   실쿼리("아린은 항구에 도착했다") → 두 컬렉션 상위 히트 코사인 0.52–0.58. 앱 어댑터의
   query 경로는 이미 `[list(vector)]` 변환을 한다(임시 질의가 tuple 거부된 것과 무관).
6. 전체 백엔드 스위트 **2316 passed · 0 failed**.

**알파 스택 최종 상태**: LLM·임베딩 모두 구글(같은 AI Studio 키 5개 라운드로빈),
mongo/chroma/elasticsearch 는 in-stack, llama·embedding 컨테이너 중 llama 는 제거
(embedding 컨테이너는 떠 있으나 앱이 부르지 않는다).

**오너 제공 관측 + 부하분산 실측(같은 날)**: 오너가 콘솔 한도를 알려줬다 — 임베딩
무료층 RPM 100 · TPM 30K · **RPD 1K**("충분하겠어. 그래도 부하분산은 해주고"). 임베딩
회전 실측: 스택 안에서 10호출 → 키별 `[2,2,2,2,2]` 정확 분산. ★ 캐비애트를 답변에
남긴다: 구글 무료층 한도는 통상 **프로젝트 단위**로 집계되므로 5키가 같은 프로젝트면
회전이 한도를 곱하지 않는다(내구성은 곱한다 — LLM의 IP 제한 키가 실증). 리랭커 없이
구동 = 현행 기본(RRF 융합, 결정 2=A)임도 확인 답변.

## [알파 세션 2 — 같은 날 추가] 키 정리·스택 전환·임베딩 검토

오너 지시 셋: *"키는 지우지 뭐. 스택 전환 해주고, 임베딩은 (gemini-embedding-2 표)
이거 한번 검토해줘. 지금 구조랑 다를 수 있어서 전용 어댑터를 만들어야할 수도 있겠다."*

**① IP 제한 키 제거** — key[0] 삭제, 5키. (오너가 말한 "5개"와 이제 일치.)

**② 스택 전환(외부 LLM)** — 전환 전 상태 실측: 핵심 컨테이너(mongo·application·
gateway·llama 등 7개)가 2시간 전 코드 255로 전부 죽어 있었고(WSL/도커 사고 추정)
worker·admin은 mongo 없이 재시작 루프. `docker compose -f docker-compose.yml -f
docker-compose.llama.yml down` 후 **base 만 재빌드 기동**(llama 서비스 없음 =
외부 전환, 볼륨 보존). 전 컨테이너 healthy, 실제 게이트웨이 경로 생성 확인:
`model: gemma-4-31b-it`, `"네, 스택 전환이 완료되었습니다."` — 키 회전·thought
걷기 모두 스택 안에서 동작.

**③ gemini-embedding-2 검토(실측, 전용 어댑터 필요성 판정):**

| 프로브 | 결과 |
|---|---|
| OpenAI 호환 `/v1beta/openai/embeddings` | **200 OK** — wire 계약은 우리와 같음 |
| 기본 차원 | **3072** (`dimensions` 파라미터로 768 실측 변경 가능 — **전송 안 하면 3072**) |
| `task_type`(네이티브 확장) | 400 Unknown name — 호환 경로로는 못 씀 |
| 네이티브 `:embedContent` | 200 OK — `taskType`·`outputDimensionality`(768·1024) 다 됨, 같은 키 |
| **QUERY vs DOCUMENT 임베딩** | **코사인 1.0000 — 이 모델은 비대칭 없음. taskType 구분이 검색 품질에 실질 영향 없음(전용 어댑터의 근거 소멸)** |

결론: **전용 어댑터 불필요 — 기존 `OpenAIEmbeddingProvider` 확장 2건으로 족하다.**
① 경로 정규화(LLM `_chat_endpoint`와 같은 관례 — 지금은 `/v1/embeddings`를 무조건
붙여 구글에선 404), ② `dimensions` 요청 파라미터 전송(안 보내면 3072로 나와
차원 가드와 불일치). 운영 쟁점: **모델 교체 = 재색인 필수**(차원과 무관 — 임베딩
공간 자체가 다름. 차원 1024를 골라도 기존 BGE-m3 벡터와 섞으면 무의미), 차원은
권장값 768/1536/3072 중 선택(1024도 기술적 가능), 입력 상한 8,192 토큰(메모리
조각은 짧아 무관), **alpha 배선 공백 — 임베딩 API env 통과가 external override 에만
있고 base compose 에는 없음**(in-stack chroma/es 를 유지한 채 앱만 외부 임베딩을
쓰려면 base 에도 통과 필요) → 슬라이스에 포함.

## [알파 세션 — 같은 날 추가] 외부 LLM 실호출 스모크 (구글 Gemini API)

오너: *"넣었어. 5개 키 넣었으니까 테스트 진행해봐."* (실제로는 **6개**가 들어 있었다 —
말씀과 달라 보고했고, 그대로 진행.) 모델: `gemma-4-31b-it`(오너 지정, 공식 id 하이픈
표기 확인). 스모크는 스택 바깥 스크립트(`/tmp/llm_external_smoke.py`, 일회용)로 실조립
(`_build_provider`)을 그대로 돌렸다 — **스택은 무변**(in-stack llama 유지).

**실측 다섯 가지(구글 붙이며 발견 → 그 자리에서 수정):**

1. **구글의 OpenAI 호환 루트에는 `/v1`이 없다**(`…/v1beta/openai` + `/chat/completions`) —
   그대로 두면 404. `_chat_endpoint` 정규화로 해결(커밋 21b1f1c): 접미 `/v1` 벗김
   (OpenAI·OpenRouter)·구글 루트 인식·전체 엔드포인트 붙여넣기 허용.
2. **`chat_template_kwargs` → 400 "Unknown name"** — llama.cpp 전용 필드를 OpenAI 호환
   서버가 거부. `LLAMA_API_FORMAT=llamacpp|openai`(기본 llamacpp, 형식은 주소로 추론
   안 함 — 임베딩 축과 같은 결)로 해결. openai 는 확장·프로브(/props·/tokenize)도 끔.
3. **`reasoning_effort` → 400 "Thinking budget is not supported"** — 이 모델의 thinking을
   끌 방법이 없고 content가 `<thought>…</thought>답변` 모양으로 온다. openai 형식에서
   thought 블록을 걷어 계약(content=답변) 유지. **닫히지 않은 블록은 빈 문자열** —
   지어내지 않는다.
4. **짧은 `max_tokens`(64)로는 사고가 예산을 전부 써 전부 빈 답** — 512에서 정상.
   짧은 상한의 호출부가 있다면 영향 검토 필요(앱의 호출부는 상한을 크게 잡는다).
5. **key[0]이 IP 주소 제한**(403 PERMISSION_DENIED, 이 머신 발신 IP 미허용) — 오히려
   실전 폴백 검증 기회가 됐다: 첫 호출에서 `provider_key_rejected` 로그 1회 → 즉시
   key[1]로 회전 → 성공. **600s 쿨다운 실전 확인 — 13번 호출 내내 key[0]은 딱 1회만
   시도됨.**

**최종 결과(13/13 성공)**: 시도 분포 `[1, 5, 2, 2, 2, 2]`(key0=거부 1회, 나머지 5키에
라운드로빈 균등 분산), 전 호출 한국어 인사 정상 생성, 모델 `gemma-4-31b-it`.

**검증**: 전체 백엔드 스위트 `2311 passed · 119 skipped · 0 failed`. 뮤테이션 가드 2건
(커밋 후): M4 thought 걷기 비활성화 → 2셀 재실패 ✓ 복구 ✓; M5 조립의 형식 스위치를
상시 off → 어셈블리 셀 재실패 ✓ 복구 ✓ — **첫 짝이었던 client 직접생성 셀은 조립 변이를
못 보는 짝이었다**(그 셀들은 provider 기본값을 검사한다) — 조립을 검사하는 셀로 다시 맞춰
확인했다. 각 복구 후 트리 클린 확인.

**오너에게 남은 것**: ① key[0]의 IP 제한 — 허용 목록에 이 머신 IP(X.X.X.X)를
추가하거나 키를 하나 지우거나. ② 이 머신 스택의 LLM 전환 여부 — `.env`가 이미 외부를
가리키므로 재기동하면 in-stack llama 대신 구글로 돈다(오너 규칙 ①). ③ 임베딩·리랭커
실측은 키 확보 뒤 후속.

## Next steps

- **dogfood(GATE-1) 착수 — 키 선행 조건 소멸.** LLM·임베딩 축 실측 완료, 리랭커는 키 불필요(no-op 비교).
- 리랭커 축: 다른 공급자 키 필요(구글엔 rerank API 없음). 없어도 정상 구성.
- 관측 연결 확인: 폴백으로 살아난 호출이 `ObservedProvider` 감사 레코드에 어떤 모양으로
  남는지(모델 필드는 실제로 쓰인 폴백 모델명으로 남는다 — 확인 셀은 아직 없음).
- **독립 검증 대기**: 오늘 커밋(`d8ba6e7…`)은 구현자 뮤테이션만 받음 — 다음 검증자가 반증 시도.
- **SoT 부채**: KEY_REJECTED·폴백 정책이 SoT 미개정(추적 부채에 등재) — 다음 SoT 슬라이스에 합산.
- `Retry-After` 헤더 존중 여부는 실제 429 응답을 보고 나서(유예 목록 참조).
- (세션 마무리: README 점검 `cba1d2c` + HANDOFF 인계 갱신으로 하루 종료. 오너 요청으로
  홈서버 관련 세부는 본 로그 어디에도 없다.)
