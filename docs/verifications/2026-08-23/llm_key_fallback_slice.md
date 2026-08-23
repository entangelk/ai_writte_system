# 외부 API 키 폴백 슬라이스(8단계) — 독립 검증

## Subject metadata

- 날짜: 2026-08-23 (검증 세션 — 구현 세션 2026-08-22과 다른 AI 세션)
- 요청자: 오너 — *"작업 AI가 작업한거 검증하고 의심하고 또 의심해줄래?"* (HANDOFF:307
  미검증 계열 지시에 따른 반증 — 지정 축: 쿨다운 경계(401/403=600s·429=60s),
  `KEY_REJECTED`→502 양방향, thought 걷기 미종결(빈 답), `KEY_REJECTED`가
  `retryable=False`인데도 회전하는 분기).
- 대상: 키 폴백 슬라이스 8단계 `d8ba6e7…7bf07c9` (2026-08-22) + 같은 지정 축이 살고 있는
  스모크 슬라이스 `21b1f1c`(주소 정규화)·`a330eff`(`LLAMA_API_FORMAT` + thought 걷기)의
  해당 축. 커밋 전부 HEAD(`22ff6c6`)에 포함, 작업 트리 클린에서 검증.
- 정규 스펙: [`plans/external-api-fallback-decisions.md`](../../plans/external-api-fallback-decisions.md)
  (오너 정책 확정 2026-08-22 §0 + 구현 결정 §1) + 부모 브리프
  [`plans/external-api-expansion-decisions.md`](../../plans/external-api-expansion-decisions.md) §4.
- 소스: `d8ba6e7`·`c374194`·`14fed04`·`2e48f90`·`a667fd7`·`99b1ccf`·`c73d351`·`7bf07c9`
  (8/8) 및 `21b1f1c`·`a330eff` (지정 축 범위).

## Scope

- 계약: 브리프 §0 오너 정책 6조 + §1 구현 결정 14개 항을 코드를 열기 전에 경계 행렬로
  먼저 세웠다 (시도 순서 a1→b1→c1→a2→b2→c2 · 라운드로빈 시작 키 · RPM 30 슬라이딩 60s ·
  소진 fail-fast · 3축 범위 · KEY_REJECTED/retryable=False·회전 · 502 표면 ·
  **쿨다운 401/403=600s·429=60s·timeout/5xx 없음** · 명시 모델 우선·중복 제거 ·
  체인 공유 시간 예산 · 소진 오류(0시도=OVERLOADED/임베딩 429, 시도 후=마지막 오류) ·
  env 이름 7종 · compose 대시/콜론 표기 · 로그 key_index만 · 무설정 무변 ·
  형식 주소 추론 금지 · thought 미종결=빈 답).
- ★ 최우선 의심 축(=HANDOFF 지정 4축): 쿨다운 리터럴·경계, 502 양방향, 미종결 thought,
  retryable=False 회전 분기.
- 구현: `llm_gateway/app/fallback.py`(신규)·`key_rotation.py`(신규)·
  `indexing/embedding.py`·`context_search/rerank.py`·`llm_gateway/app/main.py`·
  `errors.py`(양쪽)·`transport.py`·`httpx_transport.py`·`client.py`·`application/app/api/errors.py`·
  compose 2파일.
- 회귀셀: 신규·확장 11파일(`test_llm_fallback`·`test_key_rotation`·`test_llm_provider_env`·
  `test_llm_provider_errors`·`test_llm_transport_mapping`·`test_llm_gateway_app`·
  `test_httpx_transport`·`test_llama_provider_client`·`test_compose_backend_env`·
  `test_embedding_assembly`·`test_rerank`) — 감사의 대상으로 전수 정독.
- 전수 수트: HEAD에서 백엔드 전수 독립 재실행.

## Methodology

재현 환경(측정의 일부): WSL2 호스트, 메인 스택 기동 중(healthy), **test-mongo 기동**
(`docker compose -f docker-compose.test.yml up -d`, healthy 대기 후), `mypy` 설치됨
(`requirements-dev.txt` — 없으면 `test_typecheck`가 skip이 아니라 실패), `.env` 14키 존재
(LLM 외부 전환 구성). 모든 뮤테이션은 **tree clean 확인 → Edit 변이 → 표적 실행(요약
count 줄 + `FAILED|SUBFAILED` 둘 다 판독) → `git checkout -- <path>` → `git status
--short` 빈 확인** 절차. 적용한 diff 는 아래 표에 문구가 아니라 그대로 적는다.

```bash
git status --short                                        # 빈 것 확인(뮤테이션 전 게이트)
python3 -m pytest -q tests/test_llm_fallback.py tests/test_key_rotation.py \
  tests/test_llm_provider_env.py tests/test_llm_provider_errors.py \
  tests/test_llm_transport_mapping.py tests/test_llm_gateway_app.py \
  tests/test_httpx_transport.py tests/test_llama_provider_client.py \
  tests/test_compose_backend_env.py tests/test_embedding_assembly.py tests/test_rerank.py
# → 171 passed, 204 subtests passed (16.7s)
python3 -c "import hashlib; from services.application.app.analysis.prompt_templates import \
  ANALYSIS_EXTRACT_TEMPLATE_V4 as v4, ANALYSIS_EXTRACT_TEMPLATE as v5; \
  print(hashlib.sha256(v4.encode()).hexdigest()); print(hashlib.sha256(v5.encode()).hexdigest())"
docker compose -f docker-compose.test.yml up -d           # healthy 대기
python3 -m pytest -q                                      # 2489 passed, 4 skipped, 2718 subtests (229.8s)
python3 -m pytest -q tests/test_chroma_adapter.py tests/test_context_search_memory_lexical_retrieval.py
# → 4 skipped (Chroma 1 + ES 3) — skip 4의 구성 확인
docker compose -f docker-compose.test.yml down
```

## Findings

### 1. 정본 ↔ 코드 리터럴 대조 — §0·§1 전 항 일치 (B1 제외, 아래 Issues)

| 계약 조항 | 코드 좌표 | 판정 |
|---|---|---|
| 401/403=600s·429=60s 쿨다운 | `fallback.py:40-42`, `key_rotation.py:27-29` (600.0/60.0) | 일치(게이트웨이 축) · **동기 축은 timeout/5xx 항에서 불일치 — B1** |
| 시도 순서 a1→b1→c1→a2→b2→c2 | `fallback.py:151-152` (모델 외곽·키 내곽) + `RecordingProvider` 교차 순서 셀 | 일치 |
| 시작 키 라운드로빈 | `fallback.py:236-244` (`_next_start` 요청마다 순환), 동기 축은 `threading.Lock` 보호 | 일치 |
| RPM 30·슬라이딩 60s 창(시작 시각 기록) | `try_acquire`가 확인·기록을 한 덩어리로(원자성) | 일치 |
| 소진 fail-fast | 0시도→`OVERLOADED` retryable(임베딩/리랭커는 `status_code=429`)·시도 후→마지막 오류 그대로 | 일치 |
| 3축 범위(게이트웨이 키×모델·임베딩/리랭커 키만) | 임베딩·리랭커 래퍼에 모델 축 없음 | 일치 |
| KEY_REJECTED 신규 코드·retryable=False·회전 | `errors.py`(enum)·`transport.py:146-152`(401/403 매핑)·`fallback.py:169-187`(`key_fatal`) | 일치 |
| 게이트웨이 표면 502 | `main.py:180-181` + 앱 `api/errors.py` 기본 502(앱은 게이트웨이 enum 직접 import — 미러 없음) | 일치 |
| 명시 모델 첫 순위·중복 제거 | `fallback.py:221-234` | 일치 |
| 체인 공유 시간 예산 | 게이트웨이 `asyncio.timeout` 전체 · 동기 축 "첫 시도 후 deadline 점검"(`attempted and …`) — 브리프 문구 그대로 | 일치 |
| env 이름 7종·compose 대시/콜론 표기 | base 3종(gateway)·external 4종×3서비스 + `test_compose_backend_env` 표기 셀 확장 | 일치 |
| 로그 위생(key_index만) | `FallbackProvider`는 키 값을 모름(구조적 비유출) + `assertNotIn("Bearer"/"sk-")` 셀 | 일치 |
| 무설정 무변 | `len(keys)<=1 且 len(models)<=1` → 단일 provider·헤더 없음(over-strict 총괄 셀) | 일치 |
| 형식 주소 추론 금지 | `LLAMA_API_FORMAT` 미지정=llamacpp 그대로(구글 주소만 넣어도 추론 안 함 셀) | 일치 |
| thought 미종결=빈 답 | `client.py` `_strip_thought_block`(미종결 `return ""`) | 일치 |

### 2. 뮤테이션 12종 — 지정 축 4개 전부 잠금 확인, 비지정 2개 축에서 무가드 발견

| id | 적용한 diff | 물린 셀 |
|---|---|---|
| M1 | `fallback.py:40` `KEY_REJECTED_COOLDOWN_SECONDS = 600.0` → `60.0` | **0셀 — 전 수트가 게이트웨이 600 리터럴에 무관심** (H1) |
| M2 | `key_rotation.py:27` 같은 변경(600.0→60.0) | 1셀 `test_401_cools_long_and_429_cools_short`(장>단 관계만 핀 — 절대값 아님) |
| M3 | `fallback.py:169-171` `key_fatal = (exc.code is ProviderErrorCode.KEY_REJECTED)` → `key_fatal = (False)` | 1셀 `test_key_rejected_cools_the_key_long` — **지정 축 "retryable=False인데도 회전" 잠금 확인** |
| M4a | `main.py:181` KEY_REJECTED 분기 `return 502` → `return 401` | 1 SUBFAILED `test_provider_error_uses_stable_public_envelope`(HTTP 관통+봉투 단정) — **지정 축 "502 양방향" 정방향** |
| M4b | `main.py:177-181` 분기 5줄 삭제(주석 유지, `return 502`만 남김) | **0셀** — 뒤따르는 기본 `return 502`가 흡수. 문서용 분기이며 행동 자체는 M4a 셀이 잠금(설계된 무해함, 비이슈) |
| M5 | `client.py` `_strip_thought_block` 미종절 `return ""` → `return content` | 1셀 `test_openai_format_an_unclosed_thought_block_yields_empty` — **지정 축 "미종결 빈 답" 잠금 확인** |
| M6 | `client.py:296` `if not self._llama_extras:` → `if True:`(llamacpp에서도 걷기) | 1셀 `test_the_llamacpp_format_does_not_strip_anything`(over-strict 방향) |
| M7 | `fallback.py:151-152` 루프 중첩 상전(`for model in chain:` ↔ `for slot, provider in rotated:` 교환) | 2셀 시도 순서·명시 모델 우선 |
| M8 | `fallback.py:239` `start = self._next_start` → `start = 0` | 1셀 라운드로빈 배분 |
| M9a | `fallback.py:180-183` 뒤에 `elif UNAVAILABLE: cool(RATE_LIMIT)` 추가(게이트웨이에 5xx 쿨다운 얹는 과잉 교정) | 3셀(시도 순서 계열 — 얼어붙은 FakeClock 덕에 같은 요청 안 스킵이 순서 셀에 잡힘). **게이트웨이의 "5xx 무쿨다운"은 잠겨 있었다** — 정적 예측(미잠금)을 뒤집은 실측 |
| M9b | `embedding.py` cool else-분기 통째 `RATE_LIMIT_COOLDOWN_SECONDS` → `0.0`(429 포함 제거) | 1셀 `test_401_cools_long_and_429_cools_short`(429 단기 쿨다운 핀) |
| M9c | `embedding.py` cool else-분기를 `RATE_LIMIT if exc.status_code == 429 else 0.0`로(429 유지·**네트워크/5xx만 제거**) | **0셀 — 동기 축의 5xx/네트워크 쿨다운은 무가드** (B1의 실측 근거) |

전 뮤테이션 후 `git status --short` 빈 것 확인(12회 전부 복구·클린).

### 3. 전수 재실측

HEAD(`22ff6c6`)에서 **2489 passed / 4 skipped / 2718 subtests (229.8s, exit 0)** —
이 슬라이스를 포함한 기준선과 일치. skip 4의 구성도 실측(Chroma 1 + ES 3 — 위 명령).
단 이 숫자는 두 슬라이스가 섞인 HEAD 기준이며 슬라이스별 분리 측정이 아니다.

## Issues / Risks

### Blocking (계약 의무)

- **B1 — 브리프 §1 쿨다운 조항과 동기 축(임베딩·리랭커) 구현이 모순된다.**
  브리프는 축 구분 없이 "*timeout/5xx는 쿨다운 없이 그냥 다음 조합*"이라고 못박았다.
  게이트웨이 `FallbackProvider`는 그대로 시행한다(KEY_REJECTED·OVERLOADED만 cool —
  M9a로 잠금 확인). 그러나 동기 축은 `key_rotatable`인 오류 **전부**에 쿨다운을 걸어
  네트워크·408·5xx도 60초 쉰다(`embedding.py`·`rerank.py`의 `self._limiter.cool(slot,
  (KEY_REJECTED if status in (401,403) else RATE_LIMIT))`). 더불어 세 docstring이 이것을
  "게이트웨이 형제와 **같은 정책**: … 429/5xx/네트워크 단기(60s) 쿨다운"으로 서술해 —
  게이트웨이도 브리프도 아닌 제3의 정책을 정책인 양 기록했다. M9c로 이 이탈 행동이
  **어떤 셀에도 잠겨 있지 않음**을 입증했다(제거해도 전 수트 green). 검증 지침의 두 규칙
  — "계약이 요구하는 분기는 이름 붙은 회귀 테스트에 대응해야 한다(초록바와 무관)"·
  "정본 내부 불일치는 blocking" — 에 정확히 해당한다. 해소는 둘 중 하나며 오너 결정 사항:
  ① 동기 축의 5xx/네트워크 쿨다운을 의도적 정책으로 승인해 **브리프를 개정** + 그 행동을
  잠그는 셀 추가(예: 네트워크 실패 후 `is_cooling(slot)` 참·429와 같은 60s), 또는
  ② 동기 축을 브리프에 맞춰 5xx/네트워크 쿨다운을 제거 + no-cool 가드 셀 추가.
  어느 쪽이든 docstring의 "같은 정책" 서술은 실제와 맞게 고쳐야 한다.

### Hardening recommendations (비차단)

- **H1 — 게이트웨이 쿨다운 리터럴(600/60)이 무가드다.** M1에서 600→60으로 바꿔도 전
  수트가 green이었다. 게이트웨이 셀들은 상수를 import해 `상수−1/+1` 기준으로 쓰므로 임의
  값에 대해 항상 참이고, 절대값을 핀하는 곳은 동기 축의 관계 단정(장>단)뿐이다. 오너 정책
  리터럴이므로 `assertEqual(KEY_REJECTED_COOLDOWN_SECONDS, 600.0)`류의 한 셀(또는
  두 축 각각)이면 잠긴다.
- **H2 — env 리스트 파싱 규칙(중복 제거·빈 항목 무시)이 브리프에 없다.** 코드·docstring·
  셀(`test_splits_strips_and_dedups`)은 있으나 §1 env 항은 이름만 정의한다. 경계 분기가
  아니라 파싱 세부라 비차단으로 분류하되, 차기 SoT/브리프 개정(HANDOFF:262 추적 부채에
  합칠 예정인 taxonomy 개정)에 한 줄로 명시할 것을 권장.

### 관찰(비이슈)

- M4b: `main.py`의 KEY_REJECTED 명시 분기는 기본 `return 502`와 행동이 같은 문서용
  분기다. 제거해도 아무 셀이 안 물지만 행동(502) 자체는 M4a 셀이 잠그므로 가드 구멍이
  아니다.
- openai 형식에서 `/v1/capabilities` 호출 시 `context_window()`가 `/props`를 1회 조회하나
  실패를 삼키고 `_window_probed`가 이미 True라 재시도가 없다 — "모른다=None"의 정직한
  경로이며 기존 계약(B1, v1.7.60)과 무모순.

## Verdict

**조건부 합격** — 브리프 §1의 "timeout/5xx는 쿨다운 없이" 조항과 동기 축(임베딩·리랭커)
구현의 모순(B1)이 오너 결정으로 화해될 때까지.

근거: 지정 반증 축 4개(쿨다운 경계·502 양방향·미종결 빈 답·retryable=False 회전)는
전부 잠금 확인(M2/M3/M4a/M5, M4b는 설계된 무해함), 정본 리터럴 대조는 B1 단 한 곳을
제외하고 전 항 일치, 전수 2489/4/2718 재현. B1은 초록바와 무관하게 "계약 필요 분기
미추적 + 정본 내부 불일치" 규칙에 걸리는 결함이다.

## Outstanding items

- B1 화소 방향(브리프 개정 vs 코드 정렬) — 오너 결정 대기. 검증자는 고치지 않는다
  (지침: 검증이 결함을 찾으면 표면화만 한다).
- SoT 부채(폴백 taxonomy 미개정, HANDOFF:262) — 본 검증과 무관하게 이미 추적 중.
- `e952506`(임베딩 구글 확장 — 경로 정규화·dimensions)의 세부 축은 본 검증의 명명된
  범위 밖(관련 셀 green 확인만). 라이브 스모크 13/13·키 분포 [1,5,2,2,2,2]는 구현자
  기록으로만 확인(재실측 안 함).

## Reproduction

```bash
git status --short                                  # 빈 것 확인
# 포커스: 위 Methodology 의 11파일 pytest 명령 → 171 passed / 204 subtests
# 뮤테이션: Issues/H2 표의 diff 를 그대로 Edit → 표적 파일 pytest → git checkout -- <path>
#   (M4a·X류 판독은 FAILED 아닌 SUBFAILED 로 나오므로 요약 count 줄로 본다)
docker compose -f docker-compose.test.yml up -d && \
  until [ "$(docker inspect -f '{{.State.Health.Status}}' ai_writte_system-test-mongo-1)" = healthy ]; do sleep 2; done
python3 -m pytest -q                                # 2489 / 4 / 2718
docker compose -f docker-compose.test.yml down
```
