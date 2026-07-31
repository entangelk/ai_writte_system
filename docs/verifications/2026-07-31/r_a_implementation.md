# 독립 검증 — R-a 구현 (02feebb): report 예산을 창에서 유도한다

## Subject metadata

- **날짜**: 2026-07-31
- **요청자**: 오너("다음작업 검증해줘. R-a 구현 완료, 커밋 02feebb")
- **검증자**: Claude (독립 세션)
- **대상 슬라이스**: R-a 구현 — (ii) 창에서 유도 + (iii) 후보 길이에서 유도 (오너 결정 2026-07-31).
  커밋 `02feebb`. 작업 트리 clean, `main`.
- **정규 스펙(정본)**: `docs/system-contract-sot.md` v1.7.65 엔트리 ·
  `docs/plans/context-budget-korean-tokens-decisions.md` §2-5·§2-5-1 · K-3 가드 식.
- **검증 대상 작업 출처**: 커밋 `02feebb`(HEAD). 참고로 직전 `b6def2c`는 **직전 독립 검증
  (`r_a_budget_measure_league.md`)의 비차단 권고를 반영한 보강**이다(5330 흔들림 수정·보강 3건·
  검증 기록 repo 반영; 기준선 1752/1502).

## Scope

1. **전제 정정(하중)** — 제품 경로가 `/writing/report`가 아니라 워커→생성→self-report인가.
2. **정규 계약** — SoT v1.7.65 엔트리가 구현과 일치하는가(식·null 계약·줄이기 전용·적용 지점).
3. **유도 식** — `report_budget.derive_context_budget`(상수 150·0.96·MIN 256·줄이기 전용).
4. **capabilities 클라이언트** — `model_capabilities.ModelCapabilities`(1회 캐시·전 실패 None).
5. **게이트웨이 노출** — `GET /v1/capabilities` · `POST /v1/tokenize`(provider 신메서드·null).
6. **배선** — `/writing/generate` · 생성 워커 · `/writing/report` 3지점 적용.
7. **회귀 테스트** — `test_report_budget_derivation.py` · `test_gateway_capabilities.py`(20건).
8. **라이브 관통** — 실제 게이트웨이로 유도가 5307을 내는지·창/system이 리그 실측과 같은지.
9. **풀 스위트** — 1772 passed / 1502 subtests 재현.

## Methodology

정본 SoT 엔트리를 먼저 읽어 경계 매트릭스를 세우고, 코드·테스트·라이브 관통을 재도출(반증 지향).

- 커밋 범위·diff: `git show --stat 02feebb` · `git show 02feebb -- <path>`.
- 전제: 프론트 `frontend/src/api/client.ts` 전수 grep + `WritingService.generate`(`service.py:126-127`
  `reporter.enrich`) 직독.
- 코어 모듈 직독: `report_budget.py`·`model_capabilities.py` 전체, gateway `client.py`·`main.py` diff,
  app `main.py`·`generation_worker.py` diff.
- 라이브 관통: `GET /v1/capabilities`·`POST /v1/tokenize` curl + 호스트 python에서 `ModelCapabilities`
  (base_url=`http://localhost:8521`)로 `derive_context_budget` 실실행(아래 Reproduction).
- 풀 스위트: `python3 -m pytest tests/`(test-mongo ON). 신규 2파일 collect-only 로 카운트 교차 검증.

## Findings

### 1. 전제 정정 — 제품 경로는 /writing/report가 아니다 ✅ (하중 클레임, 사실 확인)

- **프론트가 `/writing/report`를 부르지 않는다**: `frontend/src/api/client.ts`가 부르는 writing
  엔드포인트는 `generate`·`generation-jobs`·`gate`·`revise-and-gate`·`accept`·`scratch`뿐.
  `/writing/report`의 유일한 프론트 언급은 `api/schema.d.ts:935`(OpenAPI 타입 생성물 = 호출 아님).
- **생성이 같은 패키지로 self-report한다**: `WritingService.generate`(`service.py:126-127`)가
  `self._reporter.enrich(candidate, package)`를 부른다 — `generate`에서 **패키지 한 번** 조립해
  생성과 report가 공유. report 다리(출력 상한 6144 + 후보 산문)가 항상 구속하므로, **생성 시점
  패키지 예산에서 유도하는 것이 정확한 구속 지점**이다.
- 종전 결정들(§2-1·§2-5)이 "report 전용 예산"으로 표현했으나 실제 구속 지점은 생성 시점 패키지.
  작업 AI가 착수 시 이것을 먼저 잡고 설계를 그에 맞춘 것은 정확했다. (3지점 모두에 유도를 넣어
  직접 `/writing/report` 호출까지 덮었다 — 전제가 틀려도 빈칸 없음.)

### 2. 유도 식 — 5307 재현 ✅

`derive_context_budget`: `allowance = 창 − 출력상한 − system − 후보상한 − 150`;
`derived = int(allowance × 0.96)`; `max(256, min(requested, derived))`.
- 상수: `FRAMING_RESERVE=150`(실측 94 + 여유, **낡은 150이 아니라 의도적 패드** — 주석 명시),
  `PACKAGE_ACCOUNTING_RATIO=0.96`(실측 0.965~0.979 중 낮은 쪽), `MIN=256`.
- 베타 창 16384·long(4096): 16384−6144−465−4096−150 = 5529 → ×0.96 = **5307**. 작업 AI 클레임 일치.
- **줄이기 전용**(`min(requested, derived)`), 모르면 requested 그대로(`capabilities is None` /
  `window is None`), 양수 하한(256). 코드·테스트·라이브 모두 확인.

### 3. 라이브 관통 — 실게이트웨이로 5307 · 창/system == 리그 실측 ✅

실 gateway(`localhost:8521`, 07-31 01:35 재빌드)에 `ModelCapabilities`를 물려 실행:
- `window=16384` · `system_template_tokens=465` — **측정 리그가 llama에 직접 물은 값과 정확히 동일**
  (작업 AI "게이트웨이가 앱에 준 값이 리그 실측과 같다" 확인).
- 유도: long→**5307**, medium→7273, short→8192(요청 상한 캡). (iii) 프리셋 민감도 확인.
- shrink-only(requested 2048→2048)·null 계약(capabilities None→8192) 라이브 확인.
- **5307이 가드를 통과함**: 단위테스트 `test_the_derived_budget_actually_fits_the_window`가
  비관 비율(0.979)로 되돌려도 `5307/0.979 + 465 + 4159 + 150 + 6144 = 16338 ≤ 16384`임을 검산.
  직전 측정 경계(5120 PASS input 9854 · 6144 REJECT input 10928)에서 5307은 통과 쪽에 속한다.

### 4. 게이트웨이 노출 + capabilities 클라이언트 ✅

- `GET /v1/capabilities`→`{context_window}`(provider.context_window, 비-llama면 getattr None).
  `POST /v1/tokenize`→`{tokens}`. 라이브: `{"context_window":16384}` · `{"tokens":9}`.
- provider 신메서드 `context_window()`는 **조회를 기다린다**(생성 경로 `_guard_window()` 비-대기와
  다름) — 하지만 이것은 창을 "묻는" 호출이고, **생성 경로는 손대지 않았다**(v1.7.60 "생성을
  창 조회로 지연시키지 않는다" 유지). 캐시 찬 뒤엔 왕복 0.
- `ModelCapabilities`: 프로세스당 1회 캐시(`_window_probed`+`asyncio.Lock` 이중검사),
  `count_tokens`는 본문 키 캐시, 전 실패→None(K-3 fail-open과 동일 계약).

### 5. 배선 — 3지점 ✅

- `/writing/generate`(main.py): 후보 미존재 → `candidate_tokens_upper_bound=output_tokens`.
  `output_tokens = _writing_output_length_tokens()[output_length]` = **출력 프리셋** 확인(생성 상한이자
  후보 상한으로 일관). (iii).
- `/writing/report`: 후보 존재 → `candidate_tokens_from_text(body.candidate_text)` 실측.
- 생성 워커: 프리셋 사용 + `report_output_cap is None`이면 capabilities도 None(유도 안 함).
  **상한 기본값을 워커에 복제하지 않는다**(리터럴 사본 회피 — 주석 명시).

### 6. 회귀 테스트 20건 ✅ (양방향 고정)

collect-only 로 **정확히 20건**(작업 AI "+20건"과 일치).
- `test_report_budget_derivation.py`(10): 줄인다·**가드 통과 크기 검산**·(iii) short>long·(ii) 큰창>작은창·
  null 3종·shrink-only 2종·MIN 양수·candidate 추정(len/1.7). under/over-strict 양쪽.
- `test_gateway_capabilities.py`(10→실 11 메서드 중 20 묶음): 창 보고·null 4종·비-llama null·
  tokenize·1회 캐시·fail-open·null-not-cached.
- 계약이 요구하는 경계 분기 전부 테스트에 매핑, 빈칸 없음.

### 7. 카운트 정합 ✅ (최종 확정)

b6def2c 기준선 **1752/1502** + 02feebb **+20** = **1772 passed / 1502 subtests**.

**주의(검증자 실수 정정)**: 최초 풀 스위트 실행이 **1684 passed / 89 skipped / 1502 subtests(205s)**로
나왔는데, 이는 test-mongo 컨테이너가 내려가 있어 **88개 Mongo 통합 테스트가 skip**된 때문이었다
(총합 1773은 같고, 89-skip은 본 프로젝트의 "test-mongo OFF" 서명). test-mongo 재기동 후 **Mongo ON**으로
재실행해 **1773 passed / 1 skipped / 1502 subtests(795s)** 확정 — 이것은 본 검증의 비차단 보강 #1
(동시성 회귀 테스트 +1)까지 포함한 값이며, **1773 − 1(보강분) = 1772**로 원본 02feebb 카운트와
정확히 일치한다. **회귀 0건.**

## Issues / Risks

### Blocking (계약 의무) — 없음

SoT v1.7.65가 요구하는 경계(줄인다·모르면 건드리지 않는다·늘리지 않는다·MIN 양수·null 계약·캐시)가
전부 코드+테스트에 매핑되고, 라이브 관통으로 값이 재현됐다. 전제 정정도 사실로 확인.
스펙 내부 모순 없음.

### Hardening recommendations (비차단)

1. **동시 첫 호출의 미세한 fail-open 미검증**. `ModelCapabilities.context_window`는 lock 안에서
   `_window_probed=True`를 probe **전**에 세팅한다 — lock 밖 첫 check가 probe 진행 중에 True를 보면
   `_window`(아직 None)을 반환할 수 있다(정직한 "모른다"라 무해하나 벤ign). 순차 캐시 테스트는
   있으나 **동시성 경로 테스트는 없음**. 영향 0에 가깝지만, 동시 첫 요청 폭주 시 "1회 왕복" 단언의
   엣지를 닫으려면 동시 테스트 1건 권장.
2. **max_tokens 의미 변경("그대로 쓰는 예산"→"상한")이 공개 스키마엔 반영 안 됨**. SoT·HANDOFF엔
   적혀 있으나 OpenAPI description은 무변 — 스키마만 보는 미래 호출자가 "요청한 max_tokens가
   그대로 쓰인다"로 오독할 수 있다(실제로는 같거나 작다). 스키마 description에 "ceiling, may be
   reduced to fit the window"를 추가하면 계약이 스키마 자체에 선다(프론트 영향 0).
3. **medium 유도 7273 vs 직전 리그 권장 "약 7,400"**. 둘은 다른 계산(리그 권장 vs 실제 유도식)이라
   모순은 아니나, 같은 §에 숫자가 둘 있으면 독자가 헷갈린다. 어느 쪽이 "실제로 쓰이는 값"인지
   한 줄로 명시 권장.

## Verdict

**합격(PASS).** 하중 클레임인 **전제 정정을 사실로 확인**했고(프론트는 `/writing/report`를 부르지
않고 생성이 같은 패키지로 self-report한다), 유도식 **5307**을 라이브 게이트웨이로 재현했으며,
창·system 토큰이 측정 리그의 직접 실측과 정확히 일치한다. null/fail-open 계약과 "줄이기 전용"이
코드·테스트·라이브 모두에서 성립한다. 풀 스위트 **1773/1skip/1502subtests**(= 원본 1772 + 보강 1,
회귀 0). **차단 사유 없음.**

위 3건의 비차단 보강은 본 검증 직후 검증자가 구현했다(아래 "Hardening implemented").

## Outstanding items

- (검증 시점엔 풀 스위트 재실행이 남아 있었으나 확정 완료 — 위 §7·Verdict.)
- 알파 R-c 관측(`LLAMA_CTX_SIZE=32768` → 유도 자동 확대) — 알파 머신 필요, 범위 밖.
- revise-and-gate 루프에 유도 미적용 — 작업 AI가 **명시적으로 다음 슬라이스로 미룸**(패키지 병합·
  retrieve_more 상호작용 별도 판단). 본 버전 범위 밖, SoT에 명시됨.

## Hardening implemented (검증자 실시, 본 검증 직후)

위 비차단 보강 3건을 검증자가 구현해 커밋했다(`work_log.md` "Task — R-a 독립 검증 비차단 보강"):

1. **#1 동시성 경쟁 실결함 수정**(`model_capabilities.py`): `_window_probed=True`를 probe **뒤**로
   옮겨 cold-boot 동시 첫 호출이 같은 창을 받게 함(전에는 None을 받아 derivation이 건너뛰고 가드에
   400 거부). 양방향 회귀테스트 추가(결함 코드에서 `None != 16384`로 실패 확인).
2. **#2 `max_tokens` description**(`main.py`): `WritingGenerateRequest`·`WritingReportRequest`에
   "창에 맞춰 줄일 수 있는 상한" 추가. 구조·기본값 무변.
3. **#3 SoT ⑥ 명확화**: 프리셋별 유도값(long 5,307/medium 7,273/short 8,192) + medium이 리그 권고
   7,417보다 작은 이유 + #2로 인한 "스키마 구조 무변, description만" 정정.
- 알파 R-c 관측(`LLAMA_CTX_SIZE=32768` → 유도 자동 확대) — 알파 머신 필요, 범위 밖.
- revise-and-gate 루프에 유도 미적용 — 작업 AI가 **명시적으로 다음 슬라이스로 미룦**(패키지 병합·
  retrieve_more 상호작용 별도 판단). 본 버전 범위 밖, SoT에 명시됨.

## Reproduction

```bash
# 0. 머신 상태
docker ps                                            # gateway 재빌드(07-31) 확인
curl -s http://localhost:8521/v1/capabilities        # → {"context_window":16384}
curl -s -X POST http://localhost:8521/v1/tokenize \
  -H 'Content-Type: application/json' -d '{"text":"You are a report assistant."}'

# 1. 라이브 유도 관통 (host python, 실게이트웨이)
PYTHONPATH=. python3 -c "
import asyncio
from services.application.app.writing.model_capabilities import ModelCapabilities
from services.application.app.writing.report_budget import derive_context_budget
from services.application.app.writing.report import TEMPLATE as T
async def m():
    c=ModelCapabilities(base_url='http://localhost:8521',timeout_seconds=10,trust_env=False)
    print('window',await c.context_window(),'system',await c.count_tokens(T))
    for p,ub in [('long',4096),('medium',2048),('short',1024)]:
        print(p, await derive_context_budget(requested_tokens=8192,capabilities=c,
            report_output_cap=6144,report_system_template=T,candidate_tokens_upper_bound=ub))
asyncio.run(m())"
#   → window 16384 system 465 / long 5307 / medium 7273 / short 8192

# 2. 회귀 + 풀 스위트
docker compose -f docker-compose.test.yml up -d
python3 -m pytest tests/test_report_budget_derivation.py tests/test_gateway_capabilities.py -q  # 20 passed
python3 -m pytest tests/ -q    # 1772 passed / 1 skipped / 1502 subtests (예상)
```
