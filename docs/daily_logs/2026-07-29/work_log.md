# 2026-07-29 작업 로그

## Task — 컨텍스트 예산: `long` report 실패의 베타 실측 (코드 변경 0)

### Goals

- `HANDOFF.md` 추적 부채의 ★ 항목("`long` 프리셋의 self-report가 창 부족으로 잘릴 수 있다 —
  **미확인**")을 확인한다. HANDOFF가 지정한 확인 경로는 **스택을 올려 `llm_call_audits`에서
  `writing_report`의 `parse_error` 비율을 보는 것**이며, 그것은 이 머신(베타)에서만 할 수 있다.
- 어제(C-1 후속) 알파에서 얻은 것은 **산술 대조**였다("관측 report 출력 분포의 4/6이 창 여유
  3,598을 넘는다"). **실행 중인 시스템에서 실제 실패를 본 사람은 아직 없었다.**
- **구현 슬라이스가 아니다.** 컨텍스트 예산 트랙은 K-1·K-3~K-6이 전부 오너 결정 대기라
  코드를 고칠 수 없다. 실측과 기록만 한다.

### 측정 환경 (머신-로컬 관측치, 2026-07-29)

- **베타 머신**. GPU는 `nvidia-smi` 실측 **GTX 1060 3GB** — 12B를 못 올리므로 LLM은 외부
  서버(`.env`의 `LLAMA_BASE_URL=http://192.168.1.22:9080`)다.
- 외부 LLM은 살아 있고 `/props` 실측 **`n_ctx=8192` · `total_slots=1`**
  (모델 `gemma-4-12b-it-qat-q4_0.gguf`). **즉 이 머신은 브리프 §2-2 세 번째 행("창 8192")의
  조건 그 자체다.**
- 시작 시점 스택은 application·gateway·mongo·ES·embedding·chroma가 `Exited (255) 24 hours ago`
  였고 worker 2종만 재시작 루프였다. **application 이미지가 2026-07-27 17:03 빌드**라
  인증 5커밋(D8-3a·3b·3c·5a·5c)이 들어 있지 않아 **재빌드 후 기동**했다.
- 기동 후 정상 상태 확인: **healthy 7 + healthcheck 없는 2**(worker·generation_worker).

### Completed work — ① 얇은 입력: report는 살아남고, repair가 1/3 발화한다

`long` 프리셋으로 파이프라인을 관통시켰다(project→draft→version→`POST …/writing/generate`,
`output_length=long`). `long`은 async 경로이고(main.py:4121) 그 job을 도는 워커는
`llm_call_scope`를 열므로(generation_worker.py:85) 워커의 호출도 감사에 남는다.

시드 약 700자 · 평범한 지시문 3회. **아래 표는 project `6a6945433804e2f6405702aa` 하나의
집계다**(`GET /projects/{id}/observability/kpi`):

| 호출부 | calls | success | provider_error | parse_error | correlations | multi_call |
|---|---|---|---|---|---|---|
| `query_planner` | 3 | 3 | 0 | 0 | 3 | 0 |
| `writing_generation` | 3 | 3 | 0 | 0 | 3 | 0 |
| `writing_report` | **4** | 4 | 0 | **0** | 3 | **1** |

> **얇은 입력 project는 사실 둘이다.** 위 표 이전에 프로브 스크립트의 버그(중첩된 `job_id`를
> 못 읽음)로 **중단된 run이 하나** 있고, 그것이 project `6a6945263804e2f6405702a6`에 자기
> 몫을 남겼다(`query_planner` 1 · `writing_generation` 1 · `writing_report` 1, 전부 success).
> **두 project를 합치면 report 5 calls · generation 4**가 된다.
> **다만 합산할 때 correlation은 합치면 안 된다** — `request_id`가 `long-report-probe-1`로
> 겹쳐서 두 project에 같은 문자열이 존재하기 때문이다. 이것이 정확히 v1.7.57이 버킷 키를
> `(project_id, correlation_id)`로 바꾼 이유이고, project 축을 빼고 세면 **일어나지 않은
> repair를 세게 된다**. 위 표를 project 하나로 한정한 것은 그래서다.

- **`parse_error`는 0이다.** 이 조건에서는 잘리지 않는다.
- **다만 report가 3회 요청에 4번 불렸다** — `multi_call_correlations=1`, 즉 **3번 중 1번은
  repair가 발화**했고 두 번째 호출이 회수했다. HANDOFF의 dogfood 관찰 항목
  "`report field must be an array` 실패율"이 가리키는 그 구조다.
- **그러나 이 표본은 가설을 시험하지 못한다**: `writing_generation`의 `total_tokens`가 평균
  1,160(프롬프트+완성 합)이라 **모델이 실제로 쓴 산문이 짧다.** 브리프 §2-2가 문제 삼는 조건은
  후보 산문이 프리셋 상한(4,096)에 가까울 때다.

### Completed work — ② 무거운 입력: `long`이 **4/4 전부 실패**한다

실제 1화 분량에 가까운 시드(**3,586자**, 빈 줄로 나뉜 산문)와 "한 회차 분량으로 끝까지
전개하라"는 지시문으로 4회 반복했다.

| 호출부 | calls | success | provider_error | parse_error |
|---|---|---|---|---|
| `query_planner` | 4 | 4 | 0 | 0 |
| `writing_generation` | 4 | **4** | 0 | 0 |
| `writing_report` | 4 | **0** | **4** | 0 |

- **생성은 4/4 성공**했고 `total_tokens`는 **4,570~5,209**(5,209 · 4,623 · 4,685 · 4,570)로
  얇은 입력의 4배다 — 즉 모델이 실제로 긴 산문을 썼다.
- **그 직후 report가 4/4 `provider_error`**(`total_tokens=0`)이고, **generation job 4개가 모두
  `status=failed`, `failure_reason=provider_error`**로 끝났다.
- **즉 오늘 베타 배포에서 `long` 프리셋은 실제 원고 분량 입력에 대해 100% 실패한다.**

### Completed work — ②-b 후보 산문 길이를 쓸어봐도 전부 실패한다 (④의 예고편)

②의 실패가 "후보 산문이 길어서"인지 확인하려고, 동기 endpoint `POST …/writing/report`에
**후보 산문 길이만 바꿔 가며**(다른 축은 고정) 7회 던졌다. 이 endpoint는 `candidate_text`를
호출자가 직접 주므로 생성 단계의 변동성이 빠진다. project는 `6a6947573804e2f6405702b2`
(시드 3,586자, 위 heavy와 같은 본문).

| 후보 산문 | 1,000자 | 2,000자 | 3,000자 | 4,000자 | 5,000자 | 6,000자 | 7,000자 |
|---|---|---|---|---|---|---|---|
| 실측 토큰 | 587 | 1,170 | 1,744 | 2,328 | 2,917 | 3,499 | 4,078 |
| HTTP | **502** | **502** | **502** | **502** | **502** | **502** | **502** |

- **7/7 전부 실패**이고(`writing_report` `provider_error` 7건이 이 project에 남아 있다),
  **가장 짧은 587 토큰 후보에서도 실패한다.**
- 이것이 ④를 찾게 만든 관측이다. 후보 산문이 원인이라면 짧은 쪽은 통과해야 하는데 그러지
  않았으므로, **창을 넘기는 것은 후보 산문이 아니라 컨텍스트 쪽**이라는 뜻이었다.
- (이 7건은 ②의 관통 8회와 **별개**다. 총 `writing_report` `provider_error` 11건 =
  heavy 4 + 이 스윕 7.)

### Issues found — ③ ★ 실패 방식이 예측과 다르다: 조용한 잘림이 아니라 **하드 거부**

브리프 §2-2가 예측한 실패는 **"200인데 출력만 조용히 잘려 `invalid_report`"**(→ `parse_error`)
였다. **실제로 관측된 것은 그것이 아니다.**

- 워커의 실패 사유는 `provider_error` / `provider rejected the request`이고, 그 문자열은
  게이트웨이가 **provider의 4xx**를 `REQUEST_REJECTED`로 매핑할 때만 나온다
  ([`transport.py:122-128`](../../../services/llm_gateway/app/transport.py#L122-L128) — 408·429·5xx는
  다른 코드로 간다).
- 이 서버가 그 4xx를 내는 조건을 **직접 확인**했다: 과대 프롬프트 →
  `HTTP 400 {"type":"exceed_context_size_error","n_prompt_tokens":20016,"n_ctx":8192}`.
- **반대 방향도 확인해 다른 원인을 배제했다**(추측으로 좁히지 않기 위해):
  - `프롬프트 + n_predict > n_ctx`(prompt 2,166 + `max_tokens` 6,144 = 8,310)는 **HTTP 200**이다.
    베타 서버도 알파와 같은 거동이며, **§1 실측 ②는 이 머신에서도 성립한다.**
  - report 전용 파라미터가 원인일 가능성도 배제했다 — `max_tokens` 6144(report)와 4096(생성),
    `chat_template_kwargs={"enable_thinking":false}`를 그대로 실은 요청이 **둘 다 200**이다.
    (`enable_thinking`은 게이트웨이가 **모든** 호출에 붙이므로 애초에 report만의 차이가 아니다 —
    [`payload.py:69-71`](../../../services/llm_gateway/app/payload.py#L69-L71).)
- **결론**: 남는 원인은 **프롬프트 자체가 창을 넘는 것**뿐이고, 그것은 §1 실측 ①의 경로
  (**400 하드 거부, 자르지 않음**)다. 사용자에게는 조용한 품질 저하가 아니라 **job 실패**로 나온다.

### Issues found — ④ ★★ 근본 원인: 포인터 렌더링이 예산 회계에서 통째로 빠져 있다

"프롬프트가 창을 넘는다"까지는 위에서 확정됐지만 **왜 넘는가**가 남았다. 어림으로 계산하면
넘지 않아야 했기 때문에(시드가 3,586자뿐이다) 실제로 쟀다 — 운영과 같은 요청으로
ContextPackage를 만들고, report와 **같은 렌더링 형식**
(`- [label] {pointer_json} {text}`, [`prompt.py:113-126`](../../../services/application/app/writing/prompt.py#L113-L126))으로
재구성해 **실제 모델 토크나이저(`/tokenize`)로** 쟀다.

시드 **3,586자** 하나짜리 project에서:

| 측정 대상 | 실측 |
|---|---|
| 패키지 항목 수 | **69개** (`macro_items`) |
| **예산 코드가 믿는 값** (`token_estimate_total`) | **887 tok** |
| **생성 호출이 싣는 컨텍스트**(`include_pointers=False`) | 4,588자 / **2,412 tok** |
| **report 호출이 싣는 컨텍스트**(`include_pointers=True`) | 18,586자 / **11,304 tok** |
| report system 프롬프트 | 473 tok |
| **report 프롬프트 합계**(후보 산문 1,000자 기준) | **12,462 tok** |
| 창 | **8,192** |

- **예산 회계는 항목의 `text`만 센다.** 항목마다 붙는 포인터 JSON
  (`collection`·`document_id`·`version_id`·**64자 `content_hash`**,
  [`context_pointer.py:26`](../../../services/application/app/writing/context_pointer.py#L26)·[`:94-99`](../../../services/application/app/writing/context_pointer.py#L94-L99))은
  **한 토큰도 세지 않는다.** 그래서 887 → 11,304, **12.7배 과소평가**다.
- **포인터 몫이 report 컨텍스트의 79%다**(11,304 − 2,412 = 8,892 tok). 즉 이 경로에서
  **지배적인 항은 원고도 후보 산문도 아니고 포인터 메타데이터**다.
- **이것이 "생성은 되는데 report만 죽는" 비대칭을 정확히 설명한다**: 같은 69개 항목을 생성은
  포인터 **없이**(2,412 tok) 싣고 report만 포인터 **포함**으로(11,304 tok) 싣는다.
  `include_pointers=True`는 report 한 곳뿐이다([`report.py:139-141`](../../../services/application/app/writing/report.py#L139-L141)).
- **얇은 입력이 살아남은 이유도 같다** — 시드가 700자면 항목이 적어 포인터 몫도 작다.

**브리프와의 관계**: §2-1은 포인터 몫을 알고 있었지만 **"표는 과소평가된 하한"이라는 단서**로만
다뤘다. 실측은 그것이 보정 항이 아니라 **지배 항**임을 보여준다. **한글 밀도(2.4배)보다 훨씬 큰
오차원이며, K-1(토큰을 어떻게 셀지)을 아무리 정확히 고쳐도 이 12.7배는 남는다** — 밀도는
`text`를 재는 문제이고 이것은 **`text` 밖을 아예 안 세는** 문제이기 때문이다.

### Issues found — ⑤ 감사 레코드로는 잘림을 볼 수 없다 (관측 한계)

HANDOFF가 지정한 확인 경로("`llm_call_audits`에서 `parse_error` 비율을 보라")를 실행하면서
**그 경로의 한계**가 드러났다.

- `StoredLlmCall`은 `total_tokens`(= prompt + completion,
  [`provider.py:13-18`](../../../services/llm_gateway/app/provider.py#L13-L18))만 싣고
  **prompt/completion 분해도, `finish_reason`도, llama.cpp의 `truncated`도 기록하지 않는다.**
- 따라서 **"출력이 조용히 잘렸다"는 감사 레코드만으로는 원리적으로 관측 불가능**하다.
  볼 수 있는 신호는 `outcome`(잘린 JSON이 파싱에 실패해야 `parse_error`가 된다)뿐이다.
- 오늘 실패가 `provider_error`로 보인 것은 **다행히** 4xx라 잡힌 것이고, 예측된 잘림 경로였다면
  `parse_error`로만 보였을 것이다. **두 경로는 감사에서 다른 얼굴을 갖는다** — 브리프가 예측한
  쪽이 아니라 다른 쪽이 발화했다는 사실 자체가 이 구분 없이는 안 보였다.

### Issues found — ⑥ 401 부채 목록이 실제보다 좁다

HANDOFF 추적 부채는 D8-3a 이후 401을 받는 스크립트를 **4종**으로 적는다. 오늘 원인 규명에
`scripts/diagnose_writing_report.py`를 쓰려다 같은 401을 받았다:

```
RuntimeError: context seed draft failed: HTTP 401: {"detail":"not authenticated"}
```

- 실제로는 **최소 6종**이다 — 목록의 4종 + [`diagnose_writing_report.py`](../../../scripts/diagnose_writing_report.py)
  + 그것이 시드를 위임하는 [`diagnose_writing_gate.py:240`](../../../scripts/diagnose_writing_gate.py#L240).
- **영향이 부채 설명보다 크다**: 이 두 스크립트는 "운영 smoke"가 아니라 **report/gate 실패를
  진단하는 유일한 도구**다. 즉 오늘 같은 장애가 났을 때 **원인을 보는 도구가 인증 때문에 막혀
  있다.** 나는 우회해서(앱 코드로 직접 재구성) 원인을 찾았지만, 그 우회는 스크래치패드에만 있다.

### Issues found — ⑦ 프론트는 이 실패를 되돌릴 수 없는 형태로 보여준다

- `provider_error`의 사용자 문구는 **"생성 모델 호출에 실패했습니다."**
  ([`GenerationPad.tsx:20`](../../../frontend/src/writing/GenerationPad.tsx#L20))이다. 원인이
  "입력이 창을 넘었다"임을 알 수 없고, 사용자가 할 수 있는 조치를 시사하지 못한다.
- 그리고 **"다시 시도" 버튼이 함께 제공된다.** 이 실패는 **결정적**이다(같은 입력 → 같은
  프롬프트 → 같은 400). **재시도는 반드시 같은 실패로 끝난다.** 게이트웨이도 이 4xx를
  `retryable=False`로 분류하는데([`transport.py:126`](../../../services/llm_gateway/app/transport.py#L126))
  그 정보가 화면까지 오지 않는다.
- **육안 확인은 아직 안 했다**(HANDOFF Next Tasks 3의 항목). 위는 코드 인용이다.

### Decisions

- **코드는 한 줄도 바꾸지 않았다.** 컨텍스트 예산 트랙은 K-1·K-3~K-6이 전부 오너 결정
  대기이고, 오늘 찾은 것은 그중 **K-6의 입력**이다. 여기서 예산 축을 손대면 결정 없이 경계를
  정하는 일이 된다(어제 C-1이 같은 이유로 창 기본값을 안 바꾼 것과 같은 판단).
- **`AUTH_COOKIE_SECURE`를 끄지 않았다.** 세션 쿠키가 `Secure`라 httpx가 http 대상에서 쿠키를
  조용히 버리는데(HANDOFF 함정), 배포 설정을 바꾸는 대신 **프로브가 `Set-Cookie` 값을 직접
  헤더로 싣게** 했다. 측정 편의로 배포의 보안 설정을 바꾸면 그 뒤의 관측이 운영 조건이 아니게 된다.
- **원인을 "창 초과"로 단정하기 전에 반증을 먼저 시도했다.** 4xx는 창 초과 말고도 나올 수
  있으므로 `max_tokens` 6144·`chat_template_kwargs`·프롬프트+출력 초과를 각각 200으로
  확인해 배제한 뒤에야 결론을 적었다. 어림 계산으로는 "넘지 않아야 한다"가 나왔고, 그
  불일치를 무시하지 않고 실제로 잰 것이 ④를 찾은 경로다.
- **측정 리그는 repo에 넣지 않았다**(스크래치패드). 일회성이고, 재사용 가치가 있는 것은
  오히려 ⑥의 진단 스크립트에 로그인을 붙이는 쪽이다.
- **프로브가 만든 project 4개를 지우지 않았다**(얇은 입력 2 — 중단된 run 몫 포함 · heavy 1 ·
  threshold 스윕 1). 베타 DB에 `llm_call_audits`가 쌓였고, HANDOFF Next Tasks 3(a)의 관측
  화면 육안 확인은 **데이터가 있어야** 할 수 있다. 지우면 그 작업이 다시 빈 화면이 된다.

### Verification

- **두 방향으로 잡았다**: 얇은 입력(report 4/4 success)과 무거운 입력(report 4/4
  provider_error)을 같은 코드·같은 배포에서 각각 구동했다. 한쪽만 쟀다면 "원래 되는데
  가끔 실패한다" 또는 "원래 안 된다"는 **반대 결론**이 나왔을 것이다.
- 무거운 실패는 **4회 반복 전부** 같은 사유로 재현됐다(1회 관측이 아니다).
- 창 초과 → 400 매핑은 **이 서버에서 직접** 확인했고(20,016 tok 요청), 알파 §1 실측 ①과
  독립적으로 일치한다.
- 프롬프트 크기는 **추정이 아니라 실제 모델 토크나이저**로 쟀고, 렌더링은 소스의 형식
  (`pointer_json`의 키 4개·`separators=(",",":")`)에 맞췄다. **처음 재구성은 `project_id`를
  포인터에 넣고 기본 separator를 써서 11,304 대신 13,926이 나왔다** — 소스와 대조해 고쳤다.
  (즉 이 수치는 한 번 틀렸다가 정정된 값이다.)
- 감사 집계는 Mongo 직접 조회가 아니라 **`GET /projects/{id}/observability/kpi`**로도 읽어
  두 경로가 같은 수를 말하는지 확인했다.
- **재현 명령**은 아래 "Reproduction"에 있다.

### Reproduction

```bash
# 1. 스택 (베타: .env에 LLAMA_BASE_URL이 외부 서버를 가리켜야 한다)
docker compose up -d --build
# 정상 상태 = healthy 7 + healthcheck 없는 2

# 2. 계정 (PYTHONPATH=/app 필수)
docker exec -e PYTHONPATH=/app -e AUTH_BOOTSTRAP_PASSWORD='...' \
  ai_writte_system-application-1 python scripts/create_user.py probe --admin

# 3. 창 초과 → 400 확인
curl -s -X POST http://192.168.1.22:9080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"x","messages":[{"role":"user","content":"'"$(python3 -c 'print("가"*40000)')"'"}],"max_tokens":64}'
# → 400 exceed_context_size_error, n_ctx 8192

# 4. 무거운 long 관통 (실패 재현) — 프로브는 스크래치패드에 있다
```

### Next steps

- **K-6은 이제 결정 근거가 하나 더 늘었다**(아래 "브리프 갱신"). 다만 **결정은 오너 몫**이고,
  ④가 R-a("report 전용 컨텍스트 예산")의 형태를 바꿀 수 있다 — 예산을 줄여도 **포인터 몫을
  세지 않으면 같은 일이 반복**되므로, "얼마로 줄일지"보다 **"무엇을 세는지"**가 먼저다.
- ⑥(진단 스크립트 401)은 **다음에 같은 장애가 났을 때 원인을 볼 수 없게 만드는** 부채이므로
  우선순위를 올려 두었다.
- 스택이 떠 있고 감사 데이터가 있으므로 **HANDOFF Next Tasks 3(a) 관측 화면 육안 확인**을
  지금 할 수 있다(브라우저가 필요해 사람 손이 든다).

### 독립 검증 후속 보강 (같은 슬라이스)

독립 검증 `docs/verifications/2026-07-29/beta_long_report_pointer_root_cause.md`는
**합격(차단 0건)**이었다. 검증자는 프로덕션 서비스·프로덕션 렌더러·프로덕션 토크나이저로
골드 재구성을 독립 수행해 핵심 수치를 재현했다 — 69개/887, report 컨텍스트 **11,303**(내 값
11,304), 생성 컨텍스트 **2,411**(내 2,412), 합계 **12,461**(내 12,462). **1 tok 차이는
`add_special`(BOS) 유무**이고 방향·결론은 동일하다. 비블로킹 정밀도 지적 6건 중 **5건을 닫고
1건은 지적 쪽이 부분적으로 틀려 다르게 처리**했다. **코드는 여전히 무변이다.**

- **① 무거운 generation 토큰 범위 — 내 값이 틀렸다.** "4,623~5,209"로 적었는데 DB 실측 최소는
  **4,570**(`heavy-long-4`)이다. 4회차가 끝나기 전에 앞 3건만 보고 범위를 적은 것이 원인이다.
  네 값을 전부 나열하는 형태로 고쳤다(5,209 · 4,623 · 4,685 · 4,570).
- **② 얇은 입력 콜 수 — 지적이 절반만 맞다.** 검증자는 DB가 "report 5 calls / 3 corr, gen 4"인데
  표는 "4 / 3 corr, gen 3"이라고 지적했다. **표는 그 project(`…702aa`)에 대해서는 정확하다** —
  차이는 프로브 버그로 **중단된 run**이 별도 project(`…702a6`)에 1건씩 남긴 몫이다.
  그런데 **두 project를 합치면서 correlation은 3으로 둔 것은 성립하지 않는다**: `request_id`가
  `long-report-probe-1`로 겹쳐 두 project에 같은 문자열이 있고, 이것이 정확히 **v1.7.57이 버킷
  키를 `(project_id, correlation_id)`로 바꾼 이유**다. project 축을 빼고 세면 일어나지 않은
  repair를 센다. 따라서 **표를 고치는 대신 표의 범위를 명시**하고, 중단된 run과 합산 시의
  함정을 각주로 붙였다.
- **③ threshold 스윕 7건 미열거 — 맞고, 열거하니 오히려 증거가 됐다.** `②-b` 절을 새로 넣었다.
  후보 산문만 1,000~7,000자로 쓸어도 **7/7 실패**이고 **가장 짧은 587 tok 후보에서도 실패**한다.
  후보 산문이 원인이라면 짧은 쪽은 통과해야 하므로, 이 스윕이 "창을 넘기는 것은 후보가 아니라
  컨텍스트"라는 ④의 단서였다는 경위도 함께 적었다.
- **④ 잔류 project 3개 → 4개.** work_log·HANDOFF 둘 다 고쳤고, 감사 레코드 수도 재집계해
  갱신했다(HANDOFF 기록 시점 24건 → 현재 **44건**. 이후 실행으로 또 늘 수 있는 값이다).
- **⑤ HANDOFF "202줄" vs `wc -l` 201 — 내가 틀렸다.** `split("\n")`의 마지막 빈 원소를 셌다.
  201로 고치고 **왜 틀렸는지를 자가 검수 줄에 남겼다** — 다음 검수자가 같은 방식으로 세면
  같은 오차가 난다.
- **⑥ 시드 "3,586자" vs 색인 3,449자 — 조치 없음.** 검증자도 "블록 경계 정규화로 설명 가능·
  사소함"으로 분류했고, 3,586은 **입력 파일의 문자 수**로 명시돼 있어 서술이 틀리지 않다.

**검증자가 별도로 남긴 정밀도 지적(권고 목록 밖)도 반영했다** — 브리프 §2-3 ⑦의 창 16384 행을
**측정처럼 과거형으로 단정**한 문제다. 실제로 측정된 것은 **"400이 아니라 200"**까지이고
(`프롬프트 < 창 ∧ 프롬프트+출력 > 창` → 200을 베타에서 재확인), **창 16,384 환경에서 실제
잘림과 `parse_error`를 본 것은 아니다**(이 머신은 외부 서버라 창을 못 바꾼다). 표에 **근거 열**을
추가해 행마다 실측/추론을 구분하고, 무엇이 확인되면 그 칸이 닫히는지를 적었다. HANDOFF의 같은
문장도 함께 고쳤다.
