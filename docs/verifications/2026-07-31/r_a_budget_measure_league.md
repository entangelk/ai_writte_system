# 독립 검증 — R-a/R-c 측정 리그 + 베타 실측 (989a1fc · b657f1b)

## Subject metadata

- **날짜**: 2026-07-31
- **요청자**: 오너("작업 AI가 작업한 거 확인해서 검증하고 의심하고 또 의심해줄래?")
- **검증자**: Claude (독립 — 작업 AI와 다른 세션)
- **대상 슬라이스**: 컨텍스트 예산 트랙 R-a/R-c **측정** 단계.
  커밋 `989a1fc`(측정 리그 + 베타 실측) · `b657f1b`(R-a 형태 오너결정으로 승격 + 낡은 서술 교체).
  작업 트리 clean, `main` 브랜치.
- **정규 스펙(정본)**: `docs/plans/context-budget-korean-tokens-decisions.md` §2-5(베타 실측) ·
  §2-5-1(R-a 형태 오너결정 브리프) · K-3 가드 식(§2·§2-1·§3 K-3).
- **검증 대상 작업 출처**: 커밋 `989a1fc`·`b657f1b`(HEAD).

## Scope

1. **정규 계약(스펙)** — §2-5/§2-5-1 경계 매트릭스 + K-3 가드 식 리터럴.
2. **측정 스크립트** — `scripts/report_budget_measure.py`의 패리티 배선(사본이 아니라 재사용인가).
3. **프로덕션 가드** — `services/llm_gateway/app/client.py` `_window_decision` 식·메시지.
4. **회귀 테스트** — `tests/test_report_budget_measure_script.py` 11건(계약 고정 여부).
5. **코드 변경** — `services/application/app/main.py`(주석 전용 + 숫자 정합).
6. **문서** — `HANDOFF.md`·work_log·decisions doc 간 정합 + 완료서술 중복 여부.
7. **실측 재현** — 시드 프로젝트로 측정 리그 재실행(표·오버헤드·판정).
8. **라이브 양방향** — 배포 가드가 초과를 거부·정상을 통과하는지 실관통.
9. **풀 스위트** — backend 전량 재실행(회귀 0 + 카운트).

## Methodology

정본을 먼저 읽어 경계 매트릭스(lock list)를 세운 뒤, 코드·테스트·실측·라이브를 각각
재도출했다(작업 AI의 클레임을 확인이 아니라 반증하려는 방향).

- 커밋 범위: `git show --stat 989a1fc b657f1b` · `git diff b657f1b~1 b657f1b -- main.py HANDOFF.md`.
- 가드 식/메시지: `services/llm_gateway/app/client.py:120-225` 직독.
- 스크립트 패리티: `scripts/report_budget_measure.py` 전체 직독(`TokenCounter`가 가드의
  `_count_prompt_tokens`/`_guard_window`/`_probe_context_window`를 호출하는지).
- 테스트 감사: `tests/test_report_budget_measure_script.py` 전체 직독(under/over-strict 각 방향).
- 머신 상태 직접 확인: `docker ps` · `curl /props`(host 및 app 컨테이너에서 python socket).
- **실측 재현**(재현 명령—아래 Reproduction):
  `docker compose run --rm --no-deps -v "$PWD/scripts:/app/scripts" -v "$PWD/services:/app/services" \
   -e LLAMA_BASE_URL=http://192.168.1.22:9080 application python scripts/report_budget_measure.py \
   --project-id 6a6be9c0dbb39de0a51ed8ba \
   --current-position 6a6be9c0dbb39de0a51ed8bb 6a6be9c0dbb39de0a51ed8bc \
   --budgets 4096,5120,6144,8192`
  (시드 프로젝트 재사용, `--seed` 없음 = 쓰기 0)
- **라이브 가드 관통**: gateway `/v1/generate`에 (a) `max_tokens=20000` 초과 요청,
  (b) `max_tokens=50` 정상 요청 각각 POST.
- **풀 스위트**: `python3 -m pytest tests/` (test-mongo ON, host). 1750 collected 확인.

## Findings

### 1. 측정 표 — 실측 재현 결과 (load-bearing) ✅ 정확히 재현

시드 프로젝트(`6a6be9c0…ba`, 밀도 1.63)로 재측정한 표가 정본 §2-5 및 작업 AI 클레임과
**행·항목 수·회계·컨텍스트(실측)·입력·입력+출력·창 여유·판정 전부 일치**:

| 예산 | 항목 | 회계 | 컨텍스트(실측) | 입력 | 입력+출력 | 창 여유 | 판정 |
|---:|---:|---:|---:|---:|---:|---:|:--|
| 4096 | 31 | 4,091 | 4,198 | 8,916 | 15,060 | +1,324 | PASS |
| 5120 | 38 | 5,017 | 5,136 | 9,854 | 15,998 | +386 | PASS |
| 6144 | 46 | 6,073 | 6,210 | 10,928 | 17,072 | −688 | REJECT |
| 8192(현행) | 62 | 8,185 | 8,358 | 13,076 | 19,220 | −2,836 | REJECT |

고정 오버헤드 **system 465 + 후보 산문 4,159 + 래퍼 94 = 4,718**, 창 **16,384**, 밀도 **1.63 자/tok**
전부 재현. 종전 `−1,914`가 외삽이었음이 확인됐고, 작업 AI의 숫자는 실측이며 날조/외삽이 아니다.

### 2. 가드 식 + 패리티 배선 ✅

- 프로덕션 가드 `client.py:158` `if input_tokens + max_output <= window: return None`(PASS),
  초과 시 `ProviderError` — **포함 경계(≤)**. `BudgetRow.verdict`(`total <= window`)와 동일 식.
- 스크립트 `TokenCounter`는 가드 메서드를 **그대로 호출**(사본 아님):
  `prompt_tokens` → `_count_prompt_tokens`(`/apply-template`+`/tokenize`, `add_special=True`),
  `window` → `_probe_context_window` 후 `_guard_window()`(`/props`).
- report 페이로드는 프로덕션 `reporter._request(...)` + `build_llama_payload`, 컨텍스트 조립은
  `diagnose_writing_gate.build_services`의 프로덕션 경로. 창을 상수로 박지 않는다.
- 즉 스크립트의 판정=가드의 판정, 스크립트의 계수=가드의 계수 — **구조적 동일성**.

### 3. 라이브 양방향 관통 ✅ (배포 가드, gateway 07-30 빌드)

gateway `/v1/generate` 실관통:
- **초과(under-strict)**: tiny prompt + `max_tokens=20000` →
  `{"code":"provider_context_window_exceeded","message":"context window exceeded before the call:
  input 17 + output cap 20000 = 20017 > window 16384"}` — **모델 호출 전** 거부(왕복 0).
  메시지 양식이 `client.py:160-169` 템플릿과 문자 그대로 일치.
- **정상(over-strict)**: `max_tokens=50` → 실제 모델 호출 성공, `context_window:16384` 보고.

경계가 `input+max_tokens > window → reject / ≤ → pass`로 양쪽에서 살아 있음을 직접 확인.
작업 AI가 인용한 `input 13076 + output cap 6144 = 19220 > window 16384`는 (재현된 13076) ×
(동일 계수 경로) ×(동일 메시지 템플릿)이므로 **delta 0은 구조적으로 성립**.

### 4. 회귀 테스트 11건 ✅ (양방향 고정)

`test_report_budget_measure_script.py` 11 passed(1.68s). 평가:
- VerdictTest 2건이 **경계 양방향**을 잠근다: `total==window → headroom 0 → PASS`,
  `+1토큰 → headroom −1 → REJECT`. under-strict·over-strict 모두.
- saturation 3건(ManuscriptTest): 제목 없음(over-strict), 전 블록이 현재 장면에(under-strict),
  결정론적 크기. 포화하지 못한 실행이 경계처럼 보이지 않게 하는 FormatTest 3건과 CLI 3건.
- 어설션이 계약을 고정하고, 버그 재도입 시 재실패한다.

### 5. 코드 변경 — 주석 전용 + 숫자 정합 ✅

`main.py` diff는 **전행이 `#` 주석**. 새 주석 산술
`8,358 + 465 + 4,159 + 94 + 6,144 = 19,220`(input 13,076)이 실측과 정합.
유일한 비주석 런타임 코드 변경은 **없다**(스크립트는 standalone CLI로 앱 런타임에 import되지 않음)
→ 회귀 원천 부재. collection 1750 = 1749 pass + 1 skip(작업 AI 클레임과 정합).

### 6. 문서 정합 + HANDOFF ✅

- HANDOFF(b657f1b)는 낡은 외삽 서술(`−1,914`·산식 후보 6,000·"재현 데이터 없다"·두 갈래)을
  **삭제하고** 실측·세 갈래·알파 1회 절차로 교체(완료서술 적재 아님 — 규격 준수).
  자가검수 헤더(216줄)·회귀 기준선(1749/1499)·베타 관측치(재부팅/복구/시드 id) 갱신.
- 머신-로컬 관측치(시드 ObjectId·외부 서버 주소)는 명시적으로 날짜·용도 표기(프로젝트 사실로 둔갑 아님).
- decisions doc §2-5-1은 선택지 표·추천·근거·후속·deferred를 갖춘 오너결정 브리프(규격 준수).

## Issues / Risks

### Blocking (계약 의무) — 없음

정본이 요구하는 경계 분기(PASS at window / REJECT over window, 양방향)가 테스트에 매핑돼 있고,
측정 리그의 패리티는 재사용으로 성립하며, 프로덕션 가드와 메시지 양식이 일치한다.
스펙 내부 모순(선택지 표 vs 가드 식 등)도 발견되지 않았다.

### Hardening recommendations (비차단)

1. **★ "회계 단위 권장 예산 약 5,330"이 스크립트 실출력(5,381)과 불일치.**
   - 근거: 스크립트는 `allowance(5,522) × ratio(4,091/4,198=0.9745) = 5,381`을 출력(재실행으로 확인).
     그러나 정본 §2-5·work_log·커밋 메시지·HANDOFF·작업 AI 멘트는 모두 "약 5,330".
   - 5,330 ≈ wrapper=150(낡은 추정)을 allowance에 넣은 값(5,466×0.9745≈5,327)으로 보임 —
     allowance 줄은 실측(4,718→5,522)으로 바꿨으나 파생 권장치만 낡은 손계산이 남은 듯.
   - **영향**: 2차 파생 수치(약≈표시)라 **경계·판정·오버헤드·결정 어느 것에도 영향 없음**.
     결정 추천은 (ii)+(iii)이고, (i)조차 "≈5,000"으로 서술. 다만 "스크립트를 돌리면 5,381이
     나오는데 문서는 5,330"인 불일치라 다음 독자가 의심하게 됨.
   - **권장**: 스크립트 출력(5,381)을 단일 출처로 삼아 네 곳(§2-5·work_log·커밋메시지는 불가·
     HANDOFF)의 5,330을 5,381로 맞추거나, "약 5,400"으로 반올림 통일. (medium 후보 측정의
     "권장 약 7,400"도 같은 손계산 경로이므로 함께 재확인 권장.)

2. **스크립트 판정 ↔ 가드 판정의 cross-parity 테스트 부재.**
   - VerdictTest는 `BudgetRow.verdict`(스크립트 규칙)을 경계에서 잠근다. 가드
     `client._window_decision`과 **현재는 동일**(코드 직독 확인)하지만, 가드 식이 미래에
     드리프트하면(예: 누군가 `<=`를 `<`로) 이 테스트들이 잡지 못한다.
   - **권장**: 경계 입력에 대해 `BudgetRow.verdict` == 가드 결정 함수 결과를 단언하는 테스트 1건
     추가(스크립트와 가드가 서로 다른 숫자를 말하는 회귀를 잡는 용도 — 스크립트 자체 주석이
     강조하는 실패 모드).

3. **래퍼(wrapper) 항이 루프 마지막 예산(8192)의 분해로만 보고된다.**
   - `overheads`가 매 iteration마다 덮어써서 마지막 예산의 wrapper(94)만 출력된다.
     구조상 2-메시지 고정 프레이밍이라 예산 무관 상수임은 맞지만, 스크립트 출력만으로는
     예산별 wrapper 변동을 읽을 수 없다. 영향 없으나, "고정"이라는 단언을 출력이 직접 증명하진 않음.

## Verdict

**합격(PASS).** 핵심 하중 클레임(측정 표·오버헤드·경계·양방향 관통·패리티 재사용·주석 전용 변경)
을 독립 재현·실관통·코드 직독으로 확인했다. 종전 `−1,914`가 외삽이었고 실측은 `−2,836`임이
재현됐다. 차단 사유 없음.

**단, 비차단 정정 1건**: "회계 단위 권장 예산 약 5,330"은 스크립트 실출력(5,381)과 불일치 —
2차 파생 수치라 판정/결정에 영향은 없으나, 다음 독자가 스크립트-문서 불일치로 의심하게 되므로
문서를 실출력에 맞추는 정정을 권장(Hardening #1).

## Outstanding items

- **풀 스위트 재실행 — 완료·일치**: `python3 -m pytest tests/ --ignore=tests/test_report_budget_measure_script.py`
  → **1738 passed / 1 skipped / 1499 subtests**(830.91s, test-mongo ON). 여기에 별도 확인한 새 테스트
  11건을 더하면 **1749 passed / 1 skipped / 1499 subtests** — 작업 AI 클레임과 정확히 일치, **회귀 0**.
  collection 1750(=1749+1skip)과도 정합. wall-clock(830s)은 부하 편차(작업 AI 766s, 기록엔 712~904s) 범위.
- 오너 결정 대기: R-a 형태 (i)/(ii)/(iii) — 검증 범위 밖(오너 판단).
- 알파 R-c 1회(`LLAMA_CTX_SIZE=32768`에서 같은 스크립트) — 알파 머신 필요, 검증 범위 밖.

## Reproduction

```bash
# 0. 머신 상태 직접 확인 (stale note 신뢰 금지)
docker ps                                   # ai_writte_system-application-1 healthy?
curl -s http://192.168.1.22:9080/props | python3 -c "import sys,json;print(json.load(sys.stdin)['default_generation_settings']['n_ctx'])"
#   → 16384 여부

# 1. 측정 표 재현 (시드 재사용, 쓰기 없음)
docker compose run --rm --no-deps \
    -v "$PWD/scripts:/app/scripts" -v "$PWD/services:/app/services" \
    -e LLAMA_BASE_URL=http://192.168.1.22:9080 \
    application python scripts/report_budget_measure.py \
    --project-id 6a6be9c0dbb39de0a51ed8ba \
    --current-position 6a6be9c0dbb39de0a51ed8bb 6a6be9c0dbb39de0a51ed8bc \
    --budgets 4096,5120,6144,8192
#   → 표의 입력 8916/9854/10928/13016, 판정 PASS/PASS/REJECT/REJECT 재현

# 2. 라이브 가드 양방향 (gateway /v1/generate)
curl -s -X POST http://localhost:8521/v1/generate -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"이어서 써줘"}],"max_tokens":20000,"thinking":false}'
#   → provider_context_window_exceeded, 모델 호출 전 거부
curl -s -X POST http://localhost:8521/v1/generate -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"안녕"}],"max_tokens":50,"thinking":false}'
#   → 정상 생성, context_window:16384

# 3. 회귀 + 풀 스위트
docker compose -f docker-compose.test.yml up -d
python3 -m pytest tests/test_report_budget_measure_script.py -q   # 11 passed
python3 -m pytest tests/ -q                                        # 1749 passed / 1 skipped (예상)
```
