# 2026-08-04 작업 로그

## Task — Slice 8.3 quota 시행 착수 브리프 작성 (Q1~Q9, 오너 결정 대기)

### Goals

- 어제 종료 시점(HEAD `8d4575b`, SoT v1.7.87)의 상태를 확인하고 다음 한 걸음을 정한다.
- 8.2b는 **독립 재검증 대기**라 조립이 금지돼 있으므로, 막히지 않은 트랙인 **8.3 착수 결정
  브리프**를 만들어 오너 결정을 받는다.

### User Decisions and Rationale

- **오너 선택: "8.3 착수 브리프 작성"**(2026-08-04). 재검증 대기 상태에서 무엇을 할지 물었고
  세 선택지(① 8.3 브리프 ② 내가 8.2b 재검증 수행 ③ 8.2c 브리프) 중 ①을 택했다.
- 근거로 제시한 것: **브리프 작성은 "조립"이 아니라 재검증과 병행 가능**하고, 재검증은
  구현에 관여하지 않은 독립 검증자(지금까지 전부 Codex 세션)가 맡는 것이 이 저장소의 관례다
  (`docs/guides/verification.md`).

### Completed work

- [`docs/plans/08-3-quota-enforcement-decisions.md`](../../plans/08-3-quota-enforcement-decisions.md)
  신설 — **Q1~Q9**, 각 항목이 `선택지 | 설명 | 장점 | 단점` 표 + 구현자 추천 + 근거를 갖는다.

  | 항목 | 질문 | 추천 |
  |---|---|---|
  | Q1 | 차감 시점 | A 선차감(요청 진입) |
  | Q2 | 실패·중단의 환원 | A 자동 환원 없음(관리자 조정이 통로) |
  | Q3 | 동시 요청의 초과 | A 검사-후-삽입 + 한계 명시 |
  | Q4 | 저장소 장애 방향 | A 전면 fail-closed(503) |
  | Q5 | 초과·정지 상태코드 | B 잠금 `429` / 초과 `402` / 정지 `403` |
  | Q6 | 확인 통로 | A 쿼리 파라미터 `?confirm=true` |
  | Q7 | 시행 seam | A `yield` dependency |
  | Q8 | 비동기 202 잠금 | C 202 해제 + 진행 중 job 상태 가드 |
  | Q9 | `dedupe_key` 매핑 | A 경로별 매핑표(코드 상수) |

- 인덱스 등재: [`docs/plans/README.md`](../../plans/README.md) Phase 8 표에 한 줄 추가.
  가드가 요구하는 **문서 수 주장 3곳**(최상위 `README.md` 브리프 수·전체 수, `plans/README.md`
  본문)을 78→79 · 95→96으로 함께 갱신했다.

### Issues found — 브리프를 쓰다 실측이 드러낸 것 넷

1. **`analysis_extract`·`analysis_compare`는 요청 본문이 아예 없다**([`main.py:3618`](../../../services/application/app/main.py#L3618)·[`:3972`](../../../services/application/app/main.py#L3972)).
   → 확인(confirm)을 **본문 필드로 받을 수 없다**. 이 한 줄이 Q6을 사실상 결정한다(쿼리 파라미터).
2. **`analysis_extract`의 replay는 provider를 부르지 않는다**([`main.py:3622`](../../../services/application/app/main.py#L3622)).
   → 8.2 L2=A 문언 그대로(클라 키 없으면 서버 생성)로 가면 **아무 일도 안 한 replay마다 과금**된다.
   Q9가 `job_id`를 dedupe 키로 쓰라고 추천하는 이유이며, 같은 논리가 `analysis_compare`에는
   **반대로** 적용된다(재실행이 매번 provider를 부르므로 매번 세야 한다) — 비대칭이 의도다.
3. **404·403은 이미 차감 밖이다.** [`require_project_owner`](../../../services/application/app/main.py#L1474)가
   dependency 단계에서 먼저 답하므로, 시행 dependency를 그 뒤에 선언하면 존재하지 않는·남의
   프로젝트는 **구조적으로 무과금**이다. Q1=A(선차감)의 실질 부담이 작다는 근거가 여기서 나온다.
4. **비동기 202가 동기보다 덜 보호된다.** 8.2b 계약("요청 경로가 잠금의 주인")을 그대로 적용하면
   202 반환 시 잠금이 냉각 5초로 넘어가는데 워커는 최대 91초를 돈다 → 그 사이 재클릭은
   **새 uuid → 새 job → 2회 과금**. 가장 비싼 실수 중복이 정확히 이 자리에 남는다. Q8이 이
   공백을 명시적 선택지로 올렸고, `list_for_draft`가 이미 있어([`generation_job.py:164`](../../../services/application/app/writing/generation_job.py#L164))
   상태 가드는 새 저장소 없이 닫힌다.

### Decisions (구현자 판단, 오너 확정 전)

- **예약-확정(2단계 차감)을 추천에서 뺐다** — 이 스택에는 스케줄러가 없어 **고아 예약을 치울 것이
  없다**. 8.1 P3이 "리셋 작업을 만들지 않는다"로 같은 문제를 피한 결정과 정면 충돌한다.
- **Q5는 "프론트가 다르게 행동해야 하는가"를 기준으로 갈랐다.** 잠금(확인 후 통과) · 초과(창
  리셋 대기) · 정지(관리자만 해제)는 행동이 셋이고, H3가 `detail` 분기를 금지하므로 코드도 셋이
  필요하다. `402`의 RFC 논쟁이 부담이면 **초과를 `429`로 접고 정지만 `403`** 으로 두는 절충을
  브리프에 함께 적었다.
- **Q3은 원자성을 포기하고 한계를 적는 쪽**을 추천했다. 8.2b가 "잠금은 최선 노력"을 정직하게
  적은 것과 같은 형태이며, 실제 노출(다른 action·project 동시 요청)이 이 배포 규모에서 작다.

### Verification

- `python3 -m pytest -q tests/test_docs_indexes.py` → **9 passed / 10 subtests**.
  - 처음에는 **4 failed** — 가드가 설계대로 물었다(미등재 문서 + 문서 수 주장 3곳 불일치).
    등재와 숫자 갱신 뒤 통과. 이 가드가 없었으면 README 숫자가 또 갈라졌을 자리다.
- 문서 전용 변경이라 앱 회귀는 돌리지 않았다(코드 0줄).
- 브리프의 모든 사실 주장은 `file:line`으로 코드에서 재확인했다 — 특히 `429`·`402` 미사용
  (앱 전체 grep 0곳), 유료 9경로의 선언된 상태코드, dependency 선언 순서.

### Next steps

1. **오너가 Q1~Q9를 확정한다.** 확정 뒤 브리프 §0 표를 결정으로 채우고 이 로그에 근거를 남긴다.
2. **8.2b 독립 재검증**(구현에 관여하지 않은 검증자). 통과 전에는 8.3 **조립 금지**.
3. 재검증 통과 + Q 확정이 모이면 8.3 구현 — 회귀 먼저(브리프 §"결정 뒤 구현 슬라이스"의 셀 목록),
   그다음 `quota/enforcement.py` → dependency 배선 → `responses=` 선언 + 전수 가드 → 프론트
   `gen:api`.

---

## Hardening — 독립 검증(8.3 브리프 B-1·N-2 / 8.2b 재검증 PASS) 반영

### Verification review

오너가 두 독립 검증 결과를 전달했다. **판정은 8.3 브리프 = 합격(수정 1건), 8.2b = PASS.**
지적 두 건을 **받기 전에 코드로 직접 확인했다**(다른 작업자의 보고를 그대로 옮기지 않는다는 규칙).

| 지적 | 내 확인 | 조치 |
|---|---|---|
| **B-1** — 브리프 §1.1의 `analysis_compare` 칸에 400이 빠졌다 | **타당.** `responses=_owned(_ERRORS_404_502_CONFIG)`([`main.py:3970`](../../../services/application/app/main.py#L3970))이고 그 상수 본문은 400을 담는다([`:1423`](../../../services/application/app/main.py#L1423)) | 표 정정 + **400의 두 얼굴**을 절로 신설 |
| **N-2** — Q5의 H3 전제가 약하다(프론트가 이미 detail로 분기) | **타당.** [`describeWritingError`](../../../frontend/src/api/client.ts#L725)가 `status`보다 **먼저** `detail.includes(...)` 세 개로 갈라진다(`client.ts:729-748`) | §1.6 신설 + Q5 추천에 교환 조건 명시 + HANDOFF 추적 부채 |

### Issues found — 지적을 확인하다 **한 칸 더** 나왔다

B-1을 "400을 표에 더한다"로 끝내면 **틀린 채로 닫힌다.** 그 400은 **사전 검증 400과 성격이 다르다**:

- 사전 검증(`task_type`·`output_length`·async 위치 누락)은 provider를 **부르기 전**이다.
- **K-3 창 가드 400**은 게이트웨이 provider client가 던지는 것이라([`llm_gateway/app/client.py:160`](../../../services/llm_gateway/app/client.py#L160))
  **provider 호출이 이미 일어난 뒤**다 — 모델 왕복만 0회이고 `llm_call_audits`에는 행이 남는다.

따라서 **"400이면 provider를 안 불렀다"가 성립하지 않는다.** 이것은 표 한 칸이 아니라 **Q2 선택지 C
(provider 미호출이 확실한 실패만 무과금)의 실현 가능성**을 바꾼다 — 상태코드로는 판정할 수 없고
관측 행 유무를 봐야 하며, 그러면 시행 seam이 관측에 결합된다. Q2=C의 단점 칸을 그 내용으로 교체했다.

**덤(8.3 작업 시 정리값)**: 상수 이름 `_ERRORS_404_502_CONFIG`와 본문(400 포함)이 어긋나 있다.
이 브리프 초판이 한 칸을 놓친 직접 원인이 **이름만 읽은 것**이다.

### Completed work

- [`plans/08-3-quota-enforcement-decisions.md`](../../plans/08-3-quota-enforcement-decisions.md)
  - §1.1 `analysis_compare` 선언 코드 **400 추가** + "★ `400`은 얼굴이 둘이다" 항목 신설.
  - **§1.6 신설** — 프론트의 기존 `detail` 분기 실측(N-2). Q5=A의 실현 가능성을 **높이는 동시에**
    그것이 계약 예외를 하나 더 만드는 선택임을 함께 적었다.
  - Q5 추천에 **교환 조건**을 명시: "B는 계약을 지키며 세 행동을 가르고, A는 위반을 한 칸 넓히는
    대신 코드 하나로 끝낸다."
  - Q2 선택지 C 단점 교체, "Decision needed" 2번의 H3 전제 문장 완화, 머리말 **착수 조건**을
    재검증 PASS로 갱신.
- [`HANDOFF.md`](../../../HANDOFF.md)
  - 8.2b를 **재검증 PASS(2026-08-04)** 로 갱신하고 "조립 금지" 문구 두 곳을 걷었다.
  - Next Tasks 1을 **8.3 구현**으로 교체(남은 게이트 = Q1~Q9 확정).
  - 회귀 기준선 **2062/1/1725**로 갱신 — 다만 **내가 재측정한 값이 아니라 재검증 보고를 옮긴 것**임을
    줄 안에 밝혔다. 직전 2059/4와의 차이 +3은 코드가 아니라 `elasticsearch` 패키지 유무에 따른
    **skip 해소**다(셀 수는 같다).
  - 추적 부채에 **H3 detail 분기 위반 1건**(N-2) 등재 — 닫는 방법 둘(H3 개정 / 프론트 정리)과
    **8.3 범위가 아님**을 함께 적었다.
- **내 실수 하나 정리**: 어제 HANDOFF에 8.3 브리프 bullet이 **두 번** 들어가 있었다(`bfcfdbc`에
  그대로 커밋됐다 — Edit 도구가 ENOENT를 보고했는데 실제로는 써졌고, 그것을 파이썬으로 한 번 더
  넣었다). 중복을 지웠다. **교훈**: 도구가 실패를 보고해도 `git diff`로 결과를 확인한다.

### Verification

- 지적 2건의 근거를 **1차 소스에서 재확인**: `_ERRORS_404_502_CONFIG` 본문, compare의
  `_provider_error_status` 분기([`main.py:4007-4015`](../../../services/application/app/main.py#L4007)),
  창 가드 위치, `describeWritingError`의 분기 순서.
- `python3 -m pytest -q tests/test_docs_indexes.py` → **9 passed / 10 subtests**(링크·등재·숫자 주장).
- 문서 전용 변경(코드 0줄)이라 앱 회귀는 돌리지 않았다. HANDOFF 245줄(다음 자가 검수 트리거 300줄).

### Next steps

1. **Q1~Q9 오너 확정** — 이제 8.3의 **유일한** 게이트다.
2. **선택**: 8.2b 재검증 PASS의 검증 기록(`docs/verifications/2026-08-04/`) 작성 여부·주체.
   지금은 PASS가 세션 보고로만 존재하고 디스크에는 2026-08-03 FAIL 기록만 있다 —
   HANDOFF에 그 상태를 그대로 적어 두었다.
3. 확정되면 8.3 구현(회귀 먼저 → `quota/enforcement.py` → dependency 배선 → `responses=` + 전수
   가드 → 프론트 `gen:api`).

---

## Task — Slice 8.3 오너 결정 1차 (Q1·Q4·Q5·Q7·Q8 확정 · Q3·Q6·Q9 재고)

### User Decisions and Rationale

| 항목 | 결정 | 오너 근거 |
|---|---|---|
| **Q1** | **C — 성공차감**(구현자 추천 A를 기각) | *"실패에는 과금하지 않는다. 이 부분은 서비스적인 정책이니까."* 원가 손실은 8.0 B1의 "원가 차이는 내부 BM에서 흡수한다"와 같은 자리에서 흡수된다 |
| **Q2** | 해소 | Q1=C가 실패를 안 세므로 환원할 것이 없다 |
| **Q4** | **A — 전면 fail-closed** | *"DB가 흔들리면 서비스 자체가 문제인 거니까."* |
| **Q5** | **B — 429/402/403** | 그대로 승인 |
| **Q7** | **A — dependency** | 미들웨어는 *"서비스가 커지면"* 다시 본다(D7=A와 같은 판단) |
| **Q8** | **C — 202 해제 + 상태 가드** | *"가드는 많으면 좋지. 실제로 막아야 하고."* |

**재고 요청 3건**: Q3(잔여 캐싱 아이디어), Q6(쿼리 파라미터 보안·선례), Q9(A의 위험·A와 C를 섞을 수
있는가). 오너가 못박은 원칙 하나 — **"아무 일도 안 한 요청에 과금은 절대로 일어나서는 안 된다."**

### Issues found — ★ Q1=C가 조용히 만든 구멍 (재고보다 이것이 먼저다)

**성공차감을 상태코드 2xx로 판정하면 이 저장소에서는 양쪽으로 틀린다.** 실측 두 자리:

1. **partial envelope 6곳** — provider가 돌고 성공 부분이 **이미 영속됐는데** 상태코드는
   400·502·503·504다([`http_models.py:278`](../../../services/application/app/writing/http_models.py#L278)·[`:304`](../../../services/application/app/writing/http_models.py#L304)).
   2xx 기준이면 **일했는데 무과금**.
2. **`analysis_extract` replay** — provider를 한 번도 안 부르고 200을 돌려준다. 2xx 기준이면
   **아무 일도 안 했는데 과금** — 오너가 "절대 안 된다"고 한 사건이 정확히 여기다.

그래서 **Q1-a**(성공의 정의)를 신설하고 **A(2xx **그리고** provider 호출)** 를 추천했다. 오너의 두
문장이 각각 조건 하나씩이고, AND로 묶으면 그대로 규칙이 된다.

### Decisions (재고 결과 — 오너 확인 대기)

- **Q3 → 새 선택지 E 추천: 진행 중 요청을 사용량에 포함한다.** 오너의 "잔여 캐싱" 직관을 신뢰할 수
  있는 자리에 두면 **8.2b 잠금이 곧 예약 장부**다(`released_at is None && expires_at > now`).
  새 컬렉션·새 수명·청소 작업이 **하나도 안 는다**(lease·TTL이 이미 청소한다 — Q1=B를 기각했던 근거가
  여기서는 성립하지 않는다). 창이 **91초 → 밀리초**로 줄고, 실패하면 잠금이 풀려 **자동 리캐싱**된다.
  - 프론트 캐싱(B)은 **UX로 병행하되 가드로 세지 않는다** — 오너가 8.2b에서 직접 말한 "프론트만으로는
    간단한 우회로도 풀린다"가 그대로 적용된다.
  - 백엔드 메모리 캐시(C)는 **반대** — 8.2 L3=A(행이 정본)를 깨고 정본이 둘이 된다. count는 이미 싸다.
  - 구현 계약 셋: `_id` 접두 정규식(8.2b "추가 인덱스 없음" 무변) · **원장 삽입이 잠금 해제보다 먼저**
    (뒤집히면 그 틈으로 초과가 샌다) · 남는 밀리초 창을 계약에 적는다.
- **Q6 → 추천을 A(query)에서 C(header)로 변경.** 선례 실측: 쿼리 파라미터는 **4 operation뿐이고 전부
  GET/DELETE**(POST 0곳), 헤더 파라미터는 0곳. `confirm`은 비밀이 아니라 기밀성 위험은 없지만,
  **상태를 바꾸는 의도를 URL·로그에 싣지 않는다**는 원칙과 이 저장소의 관례(쿼리는 조회용)가 같은
  방향을 가리킨다. 프론트 비용도 0이다 — [`fetchApi`](../../../frontend/src/api/client.ts#L38)가 이미
  `init.headers`를 병합한다. 대신 헤더는 눈에 덜 띄므로 **9경로 전수 가드**를 함께 넣는다.
- **Q9 → A 유지, 근거 재구성.** 오너 질문("A와 C를 못 섞나")의 답은 **A가 이미 C를 섞은 것**이다 —
  C를 9경로에 적용한 결과가 A의 표이고 다른 칸은 `analysis_extract` 하나(`job_id`)뿐이다. 그리고
  **Q1=C가 dedupe의 역할을 바꿨다**: replay가 200으로 성공하므로 dedupe 키가 "무노동 과금"의 1차
  방어가 된다. `analysis_extract`의 키가 **경로 파라미터라 클라이언트가 우회할 수 없다**는 점이 A의
  핵심 가치다. A의 유일한 잔여 위험(`analysis_compare` 서버 생성 키)은 **8.2b 잠금이 덮는다**.
  - **결론: 한 겹으로는 오너 원칙을 못 지킨다.** Q9=A(DB가 막는다) + Q1-a=A(시행이 안 센다) 두 겹.

### Completed work

- [`plans/08-3-…decisions.md`](../../plans/08-3-quota-enforcement-decisions.md) —
  §0을 **오너 결정 표**로 교체, Q1에 결정·파급 기록, **Q1-a 신설**, Q2를 해소 처리(Q1=C에서도 남는
  한 자리 명시: 성공 뒤 삽입 실패는 무과금으로 샌다 — 로그로 남기고 응답은 뒤집지 않는다),
  **Q3·Q6·Q9 전면 재작성**, Q4·Q5·Q7·Q8 헤더에 확정 표시, 구현 셀 목록을 성공차감 기준으로 갱신.

### Verification

- 재고 3건의 근거를 전부 실측했다: OpenAPI 전수로 쿼리/헤더 파라미터 사용처(4 operation·0곳),
  partial envelope 상수 본문, `fetchApi`의 헤더 병합, 잠금 `_id` 접두 조회 가능성.
- `python3 -m pytest -q tests/test_docs_indexes.py` → **9 passed / 10 subtests**.

### Next steps

1. **오너가 Q1-a·Q3·Q6·Q9 확인** — 넷 다 추천이 붙어 있고, Q1-a가 제일 중요하다(오너 원칙을
   코드로 옮기는 자리).
2. 확정되면 8.3 구현 착수(8.2b 재검증은 이미 PASS).

---

## Task — Slice 8.3 오너 결정 2차 (Q1-a·Q3·Q6·Q9 확정) + 원자성 추가 요구 → Q3-a·Q1-b 신설

### User Decisions and Rationale

- **Q1-a=A · Q3=E · Q6=C · Q9=A 전부 확정**("모두 알겠어").
- **추가 요구**: *"Q3에서 보완이 되면서도 원자성 확보가 될 수 있는 방법은 없나? ms라고 하지만…
  그 ms를 블로킹한다든지."* → **Q3-a 신설**. 오너는 "실질적으로 작다"를 받아들이지 않고 **구조적
  불가능**을 요구했다.

### Issues found — 원자성을 파고들다 **더 큰 구멍**이 나왔다 (Q1-b)

Q3-a를 설계하려면 "진행 중 요청"을 정확히 세야 하는데, **비동기 202가 그 계수에서 빠진다**(Q8=C가
202에서 잠금을 푼다). 거기서 Q1=C의 더 근본적인 문제가 드러났다 — **202는 "생성 성공"이 아니라
"접수 성공"** 이다. 202 시점에 차감하면 **생성이 실패해도 과금**되어, 오너가 방금 확정한 정책이
**가장 비싼 경로(long 91초)에서만** 안 지켜진다.

**실측이 선택지를 좁혔다**: [`WritingGenerationJob`](../../../services/application/app/writing/generation_job.py#L94)에
**`user_id`가 없다.** 워커가 원장 행을 쓰려면 회원을 알아야 하므로 **한 필드 비정규화가 강제된다** —
부모 계획이 8.4에 배정한 "워커의 주체 전달"을 Q1=C가 앞당긴 것이다.

### Decisions (재고 결과 — 오너 확인 대기)

- **Q3-a → A: 회원 단위 입장 뮤텍스.** `①뮤텍스 → ②사용량 계산 → ③잠금 차지 → ④뮤텍스 해제`이며
  **임계 구역이 모델 호출을 포함하지 않는다**(수 ms). 그러면 다음 요청이 반드시 앞 요청의 잠금을 보게
  되어 **초과가 구조적으로 불가능**해진다.
  - **걷어낸 후보 하나 — Mongo 트랜잭션은 이 문제를 못 푼다.** 스냅샷 격리라 문서 쓰기 충돌만 막고
    count 술어(phantom)는 직렬화하지 않는다. 서로 다른 문서를 세고 쓰는 두 트랜잭션은 **둘 다
    커밋된다.** 이 저장소가 정본 저장에 트랜잭션을 쓰기 때문에 오해하기 쉬운 자리라 브리프에 적었다.
  - 카운터 문서(`$inc`)·단일 문서 `$expr`는 왕복 1회로 원자성을 얻지만 **8.2 L3=A(행이 정본)를 깬다**.
    특히 `$expr` 안은 행 수를 밖에서 읽어 상한으로 넘기면 **여전히 1건 초과가 가능**하다(읽은 뒤
    완료된 요청이 in_flight→행으로 옮겨 가는 사이).
  - 구현 계약 넷: 키 `admission:{user}`(8.2b 세 축 키와 접두가 달라 충돌·오계수 없음) · **짧은
    lease ≈5초**(8.2b의 180초와 다른 축) · 획득 실패는 fail-closed 503 · 해제는 `finally`이고
    **뮤텍스를 쥔 채 provider를 부르지 않는다**.
  - 남는 한계는 정직하게 적었다: 잠금 lease(180초)가 만료됐는데 요청이 살아 있으면 계수에서 빠진다 —
    8.2b §0.3의 "최선 노력"을 상속한다. 뮤텍스는 **동시 입장**을 닫지 그것까지 닫지 않는다.
- **Q1-b → A: 워커가 생성 성공 시 차감.** dedupe 키가 `request_id` 그대로라 이중 과금이 구조적으로
  불가능하고, 재시도 endpoint도 같은 키라 B5=A가 유지된다. 대가는 job에 `user_id` 한 필드 +
  `(user_id, status)` 인덱스, 그리고 **진행 중 job을 한도 계수에 포함**하는 것(그래야 async가
  admission을 우회하지 못한다).

### Completed work

- [`plans/08-3-…decisions.md`](../../plans/08-3-quota-enforcement-decisions.md) — §0 표를 2차 결정으로
  갱신(확정 9건), **§Q1-b·§Q3-a 신설**, 구현 셀 목록에 입장 직렬화·async 차감 셀 추가.

### Verification

- `python3 -m pytest -q tests/test_docs_indexes.py` → **9 passed / 10 subtests**.
- 설계 주장 두 개를 코드로 확인: 재사용할 원자적 차지 패턴([`lock_mongo.py:69`](../../../services/application/app/quota/lock_mongo.py#L69)),
  job 문서에 회원 축이 없다는 것([`generation_job.py:94`](../../../services/application/app/writing/generation_job.py#L94)).

### Next steps

1. **오너가 Q3-a·Q1-b 확인** → 확정되면 8.3 구현 착수(다른 게이트 없음).
2. Q1-b=A를 고르면 **8.4 범위 일부(워커 주체 전달)가 8.3으로 당겨진다** — 부모 계획 표에 그 이동을
   기록해야 한다.

---

## Closeout — Slice 8.3 브리프 확정 (Q1~Q9 + Q1-a·Q1-b·Q3-a)

### User Decisions and Rationale

- **Q3-a=A(입장 뮤텍스) · Q1-b=A(워커 성공 시 차감) 확정** — 오너: *"DB 고질 문제라면 어쩔 수 없지.
  서버 성능에 따라 완전히 해결되는 건 아니지만 보완은 가능하겠네."*
- **덧붙은 판단**: 저장소 교체는 **지금 하지 않는다**. 오너가 분석 의견만 요청했고, 그 분석은 아래
  "Next steps"의 트리거 조건으로 남긴다(브리프 §후속 고려에도 한 항목으로 들어갔다).

### Completed work

- [`plans/08-3-…decisions.md`](../../plans/08-3-quota-enforcement-decisions.md) → **상태 `Resolved`**.
  §0 표에 확정 12건, 오너 총평, §후속 고려에 "저장소 교체는 이 설계의 전제가 아니다" 항목 추가.
- [`HANDOFF.md`](../../../HANDOFF.md) — 8.3을 **Owner Decisions Needed에서 결정 완료 절로 이동**하고
  확정 내용을 구현자가 바로 쓸 수 있는 형태로 압축(성공의 정의·두 겹 초과 방지·상태코드 셋·헤더 통로·
  워커 차감과 그것이 8.4에서 당겨 오는 것). Next Tasks 1을 **구현 착수**로 교체.
- [`plans/README.md`](../../plans/README.md) — 8.3 행을 Resolved로 갱신.

### Verification

- `python3 -m pytest -q tests/test_docs_indexes.py` → **9 passed / 10 subtests**.
- Mongo 결합 표면 실측(저장소 교체 분석의 근거): `*_mongo.py` **12개**, pymongo를 직접 쓰는 파일
  **50개**, `mongo_collections.md` **65개 절**, 트랜잭션 사용처 **2곳**(core_sot·analysis).

### Next steps

1. **8.3 구현 착수** — 게이트 없음. 회귀 먼저 → `quota/enforcement.py` → dependency 배선 →
   `responses=`·전수 가드 → 워커 차감 배선(job `user_id`) → 프론트 `gen:api`.
2. **저장소 교체는 트리거가 오면 다시 본다**(지금 아님): ① 다중 worker·원격 배포로 잠금 경합이
   실제 부하가 될 때 ② 8.6 결제에서 원장·entitlement·결제를 한 트랜잭션으로 묶어야 할 때
   ③ 8.5 관리자 집계가 SQL 없이 버거워질 때. D4-D(operation journal)를 유예한 트리거와 같은 구조다.

---

## Closeout — 2026-08-04 작업 종료

### 오늘 한 것 (커밋 5건, `8d4575b` → HEAD)

| 트랙 | 결과 |
|---|---|
| **Slice 8.3 브리프** | 신설 → 독립 검증 반영 → 오너 결정 2회전 → **Resolved(12건 확정)**. 코드 0줄 |
| **8.2b** | 독립 **재검증 PASS** 반영 — "조립 금지" 게이트 해제 |
| 문서 정합 | `plans/README.md` 등재·문서 수 주장 3곳, HANDOFF 상태·추적 부채 2건, CHANGELOG 1건 |

- 오너 결정은 구현자 추천을 **두 번 뒤집었다**: Q1(선차감 → **성공차감**, 서비스 정책), 그리고
  Q3의 원자성 요구(실질적으로 작다 → **구조적으로 불가능하게**). 두 번 다 뒤집힌 쪽이 옳았고,
  뒤집히면서 **숨어 있던 구멍 둘**(Q1-a "성공"의 정의, Q1-b 비동기 202)이 드러났다.

### 다음 작업자가 바로 이어갈 것

**8.3 구현**이 다음 한 걸음이고 **게이트가 없다**(8.2b 재검증 PASS · 결정 12건 확정).
브리프 §"결정 뒤 구현 슬라이스"에 셀 목록이 그대로 있다.

**반드시 알고 시작할 것 넷**:

1. **"성공"은 상태코드가 아니다**(Q1-a=A) — `2xx` **그리고** provider 호출. 이 규칙이 없으면
   `analysis_extract` replay가 **아무 일도 안 하고 과금**된다(오너가 "절대 안 된다"고 한 사건).
2. **뮤텍스를 쥔 채 provider를 부르면 설계 전체가 무의미해진다**(Q3-a=A). 임계 구역은 Mongo 왕복
   두 번이다. over-strict 셀로 잠근다.
3. **원장 삽입이 잠금 해제보다 먼저다**(Q3=E). 뒤집히면 행도 잠금도 없는 한 칸으로 초과가 샌다.
4. **비동기는 워커가 차감한다**(Q1-b=A) → job에 `user_id` 비정규화 + `(user_id, status)` 인덱스가
   필요하고, 이는 **부모 계획이 8.4에 배정한 범위를 8.3으로 당기는 것**이다(그 이동을 기록할 것).

**선택 사항 하나**: 8.2b 재검증 **PASS의 검증 기록이 `docs/verifications/`에 없다**. 디스크에는
2026-08-03 FAIL 기록만 있고 PASS는 세션 보고로만 존재한다 — 남길지·누가 쓸지는 오너 판단이다.

### 머신 상태 (그대로 두고 종료)

- 베타. `frontend`(healthy)·`worker`·`generation_worker`만 Up. **test-mongo는 내려가 있다**.
- 이미지는 여전히 코드보다 뒤처져 있다(application 07-29 등) — 화면 확인이 필요한 작업(8.2c·8.4)
  전에는 재빌드가 선행돼야 하고, 스택을 올렸으면 `curl :8520/projects`가 401인지 먼저 본다.
- 작업 트리 clean, push 안 함. **오늘 코드 변경 0줄**이라 회귀 기준선은 그대로다.

---

## Task — Slice 8.3 구현 (quota 시행 조립: 입장·성공차감·정산)

### Goals

브리프 [`plans/08-3-…decisions.md`](../../plans/08-3-quota-enforcement-decisions.md)
§"결정 뒤 구현 슬라이스" 그대로. 회귀 먼저 → `quota/enforcement.py` → dependency 배선
→ `responses=`·전수 가드 → 워커 차감 → 프론트 `gen:api`. 오너 결정 12건은 확정 상태라
새 결정은 없다.

### Completed work

| 산출물 | 내용 |
|---|---|
| [`quota/enforcement.py`](../../../services/application/app/quota/enforcement.py) | 신설. `admit`(정책 → 뮤텍스 → 유효 사용량 → 한도 → 잠금)·`settle`(원장 → 해제)·`charge_completed_generation`(워커)·`AdmissionMutex`·`GenerationJobCharger` |
| [`quota/dedupe.py`](../../../services/application/app/quota/dedupe.py) | 신설. Q9=A 매핑표 + 해석 함수. 미분류 동작은 fail-closed |
| [`quota/lock.py`](../../../services/application/app/quota/lock.py)·`lock_mongo.py` | `count_in_flight` 추가(`^{user}:` 앵커, escape). 8.2b "추가 인덱스 없음" 유지 |
| [`main.py`](../../../services/application/app/main.py) | `enforce_quota` dependency · `_REQUIRE_PROJECT_OWNER_BILLABLE` · `_billable()` 선언 · `QuotaSettledRoute` 정산 wrapper · `_default_quota_enforcement_service` · `app.state.quota` |
| [`llm_call_scope.py`](../../../services/application/app/observability/llm_call_scope.py) | `ProviderCallTally` + `provider_call_tally` — Q1-a 판정 재료 |
| `writing/generation_job*.py` | `user_id` 비정규화 · `(user_id, status)` 인덱스 · `count_active_for_user` · `has_other_active_for_draft` |
| `writing/generation_worker.py` | 성공 시 차감(`quota` collaborator, Optional) |
| 회귀 3파일 + 기존 5파일 보강 | 아래 Verification |
| 문서 | SoT **v1.7.88** · `mongo_collections.md` §43E(키 공간 둘) · 이 로그 · HANDOFF · CHANGELOG |

### Issues found — 구현이 결정을 정밀화한 지점 넷

1. **★ `yield` dependency는 응답 상태코드를 볼 수 없다.** Q7=A의 문언은 "차감은 `yield`
   뒤"였는데, 이 앱의 **partial envelope 6곳과 async 202는 예외가 아니라
   `JSONResponse`를 *반환*한다**. dependency의 exit에는 아무 신호도 오지 않으므로 그
   자리에서 정산하면 **일하고도 실패한 응답과 접수만 한 202가 과금된다**(= Q1-a·Q1-b를
   동시에 어긴다). 그래서 **입장은 dependency(선언·전수 가드 가능), 정산은 실제 응답을
   보는 route wrapper**로 갈랐다. **결정 변경이 아니라 결정을 지키기 위한 배치**이며,
   wrapper는 정책을 정하지 않는다(dependency가 남긴 영수증이 있을 때만 동작).
2. **Q8=C의 상태 가드가 멱등 replay까지 막았다.** 브리프 문언("그 draft에 실행 중 job이
   있으면")을 그대로 구현하면 **같은 `request_id`의 재전송**도 429가 된다 — 그 replay는
   `enqueue`가 기존 job을 돌려주므로 새 job도 새 과금도 만들지 않는데, 폴링·재전송하는
   클라이언트가 자기 job을 못 받게 된다. 막아야 하는 것은 **새 job이 생기는 경우**뿐이라
   `has_other_active_for_draft(request_id=…)`로 좁혔다(over-strict 셀로 잠갔다).
3. **★ Q1-a의 두 겹이 실제로 겹쳐 있다 — 그래서 한 겹을 지워도 통합 셀이 안 물렸다.**
   뮤테이션 M4(provider 호출 조건 제거)가 replay 셀을 통과했다: 같은 `job_id`를 dedupe
   키로 쓰므로(Q9=A) **원장이 두 번째 행을 DB 수준에서 거부**하기 때문이다. 결함이 아니라
   오너가 요구한 "한 겹으로는 부족하다"가 성립한다는 증거지만, 그 탓에 통합 경로만으로는
   한 겹을 지우는 변경이 **안 보인다**. `_is_charged`의 (상태코드 × provider 호출 수)
   행렬을 단위 셀로 직접 잠갔다.
4. **8.2b 잠금이 켜지면서 도메인 스위트 30여 셀이 429로 떨어졌다.** 같은 유료 동작을
   연달아 두 번 POST하는 셀(멱등 replay 단정·잘못된 본문 표)이 최소 창 5초에 걸린 것이며
   **제품 동작으로는 정상**이다. `tests/auth_support.authenticate`가 인증·소유권의
   *해석*만 우회하던 선례를 따라 **입장만** 우회하게 확장했다 — 정산은 그대로 돌고,
   확인 헤더도 endpoint까지 살아 간다. `test_auth_api`의 override 목록 핀이 이 추가를
   **강제로 명시하게 만들었다**(그 가드가 의도대로 물었다).

### Verification

- 집중 회귀: quota 5파일 + 생성 job·워커·billable 4파일 → **203 passed / 268 subtests**.
- 전체(test-mongo ON): **2145 passed / 1 skipped / 1921 subtests**
  (직전 2062/1/1725 → **+83 passed·+196 subtests**, 전부 이번 슬라이스 신규 셀).
- 실 Mongo 동시성: 한도 1칸에 **동시 20건 → 정확히 1건 입장**(각자 다른 `action`이라
  8.2b 잠금은 아무도 막지 않는다 = 뮤텍스만 재는 셀).
- **뮤테이션 10종 전부 재실패**. 그중 **뮤텍스 제거는 실 Mongo에서 초과 통과**를 만들었다 —
  "초과가 실제로 새는 것"의 실측이다. **건수는 race라 실행마다 다르다**(이 실행에서 3건,
  독립 검증 재실험은 5회 중 4회에서 2~3건) — 고정 계약값으로 읽으면 안 된다.
- 프론트: `gen:api`(+189줄) · `tsc --noEmit` 통과 · build **동일 번들 크기**(진입 410.29 kB·
  AdminConsole 8.39 kB·관측 386.70 kB) · `vitest run` **236 passed / 17 files**.

### Next steps

1. **독립 검증**(다른 작업자) — `docs/guides/verification.md`. 특히 볼 자리: 정산 wrapper가
   모든 종료 경로에서 잠금을 푸는가 · 뮤텍스 임계 구역에 provider 호출이 없는가 ·
   `auth_support` 우회가 전수 가드의 사정거리를 줄이지 않았는가.
2. **8.4**(프론트 배선·확인 대화 UX·면제·잔여 표시)와 **8.2c**(이름 이력)는 그대로 남는다.
3. ~~선택: 8.2b 재검증 PASS의 검증 기록이 없다~~ — **낡은 서술이었다**(독립 검증 Outstanding). 그 기록은 `91ae4e0`의 [`verifications/2026-08-04/slice_8_2b_duplicate_request_lock_recheck.md`](../../verifications/2026-08-04/slice_8_2b_duplicate_request_lock_recheck.md)로 이미 존재하고 인덱스·카운트에도 들어 있다.

---

## Hardening — Slice 8.3 독립 검증 반영 (PASS · 비차단 5건)

검증 기록: [`verifications/2026-08-04/slice_8_3_quota_enforcement.md`](../../verifications/2026-08-04/slice_8_3_quota_enforcement.md)
— **합격, 차단 결함 0**. 작업자가 스스로 밝힌 의심 지점 셋(정산 wrapper 이동 · Q8=C
정밀화 · `auth_support` 우회)이 전부 반증 시도를 견뎠고, 회귀 수치(2145/1/1921)와
뮤테이션 재실패가 검증자 실측으로 재현됐다.

### Completed work — 비차단 5건 처리

| 지적 | 처리 | 근거 |
|---|---|---|
| **H-1** 정산의 잠금 해제가 성공 응답을 왜곡할 수 있음 | **수리** — `settle`의 `release`를 감싸고 로그로 남긴다 | 이 함수는 응답이 **이미 만들어진 뒤** 불린다. 원장 삽입에 적용한 Q2 잔여 원칙("성공한 응답을 뒤집지 않는다")이 해제에도 그대로 적용된다 — 잠금은 lease가 회수하지만 뒤집힌 응답은 되돌릴 수 없다 |
| **H-2** "3건 통과"는 race 인스턴스 | **문서 정정** — SoT·CHANGELOG·work_log 세 곳을 "초과 통과(건수는 실행마다 다르다)"로 | 재검증자가 "정확히 3"을 기대하면 정상 재현이 실패로 읽힌다 |
| **H-3** 미분류 동작이 `KeyError` → 500 | **수리** — `UnclassifiedBillableAction`을 신설해 **503**(Q4=A와 같은 fail-closed)으로 | 도달 불가지만(1:1 가드) 도달하면 그 요청은 **중복 방지 없이 도는 유료 요청**이다. 그리고 500은 H3의 "미매핑 500 부채 0건"과 충돌한다. 분류표·매핑표 **양쪽**이 같은 예외를 올리게 맞췄다 |
| **H-4** 워커·app이 별개 `QuotaEnforcementService` | **수리 안 함, 기록** | 배포(Mongo)는 같은 컬렉션을 공유하므로 무영향이고, async 우회 방지의 핵심(진행 중 job 계수)은 원장이 아니라 **공유 job 저장소**를 직접 본다. in-memory 조립에서만 원장이 갈라지며 그것은 인프라 없는 테스트 조립의 성질이다 — 인스턴스를 공유시키려면 워커가 app 객체에 의존하게 되어 경계가 나빠진다 |
| **H-5** 빈 확인 헤더도 확인으로 읽음 | **수리** — 존재가 아니라 **내용**을 본다 | 확인 한 번은 사용량 1회를 더 쓴다(8.0 B1=A). 프록시·클라이언트가 실수로 붙인 빈 값이 회원에게 청구되면 안 된다 |

**stale 서술 하나도 정리했다**(검증 Outstanding): HANDOFF·이 로그의 "8.2b 재검증 PASS의
검증 기록이 없다"는 낡은 문장이었다 — 그 기록은 `91ae4e0`에 이미 있고 인덱스·카운트에도
들어 있다.

### Issues found — ★ `git checkout --` 함정에 세 번째로 걸렸다

hardening 세 건을 **커밋하기 전에** 뮤테이션 검증을 돌렸고, 원복에
`git checkout -- services/application/app/main.py`(및 `enforcement.py`)를 써서
**미커밋 hardening이 통째로 날아갔다**. `git status`와 grep으로 즉시 발견해 재적용했고
회귀로 복구를 확인했다(손실 구간 없음).

**이 저장소에서 세 번째다**(2026-07-30 검증자 · 2026-08-03 8.2b · 오늘). CLAUDE.md 함정
절이 이미 **"수정을 먼저 커밋 → 뮤테이션 → `git checkout`으로 원복"** 을 순서로 못박고
있었는데, 앞선 슬라이스 본체는 그 순서를 지켰으면서 **뒤따르는 작은 hardening에서
어겼다** — "작은 수정이라 곧 커밋할 것"이라는 판단이 정확히 그 자리다. 규칙을 아는
것으로는 부족하다는 증거가 하나 더 쌓였고, 이번에는 **순서를 어긴 대가가 즉시
드러났다**는 점만 달랐다.

### Verification

- 집중 회귀: `test_quota_enforcement.py` + `..._api.py` → **65 passed / 180 subtests**
  (+5 cells: 해제 실패 무영향 · 그때도 원장 행은 남는다 · 빈 헤더 2종 · 정상 확인 ·
  매핑 누락 503).
- **되돌리기 뮤테이션 3종 전부 재실패**: 해제 감싸기 제거 → H-1 셀 2건 · 빈 헤더 허용 →
  H-5 셀 · `UnclassifiedBillableAction` 포획 제거 → H-3 셀. **이번에는 커밋 뒤에 돌렸다.**
- 전체(test-mongo ON): **2150 passed / 1 skipped / 1923 subtests**.

---

## Task — `git checkout --` 사고를 규칙으로 닫았다 (오너 지시)

### User Decisions and Rationale

- 오너: *"이 사고나는 게 참 많이 나네? … 핸드오프가 아니라 verification.md에 추가되어야 할 것 같은데?
  체크아웃 하기 전 커밋이 되어있는지 아닌지 확인 절차가 필요하다 같은?"* → 이어서 **"6장을 고쳐버리고
  가이드에도 서술해두자. 그럼 더 확실하지?"** 로 확정.
- **근거가 된 실측**: 오너는 "최근 5일 내 4~5건"으로 기억했으나 로그 전수 조사 결과 **9건**이었고,
  **8건이 구현자**(검증자는 2026-07-30 한 건)였다. 2026-08-02에는 **같은 사람이 하루에 세 번** 밟았다.
  → verification.md에만 적으면 사고의 8/9에 안 닿는다는 것이 §6도 함께 고친 이유다.

### Completed work

| 문서 | 역할 |
|---|---|
| [`docs/guides/verification.md`](../../guides/verification.md) | **절차 정본** — §"Mutation testing" 신설. 사전 게이트(`git status --short` 공백), **상황별 원복 분기 3종**(clean → `checkout` / dirty이고 커밋 가능 → 먼저 커밋 / **dirty이고 커밋하면 안 되는 검증자** → `cp` 백업 + 역방향 Edit + 바이트 대조), 원복 후 확인, 무엇을 변형할지(방어적 단언은 **defence를 제거**해야 보인다), 그리고 **뮤테이션이 안 물릴 때의 처리**(오늘 Q1-a 두 겹 사례) |
| `CLAUDE.md`·`AGENTS.md` §6 | **전제조건 + 포인터**. 종전 문장("mutation을 미커밋으로 두고 `git checkout`으로 원복")이 **`checkout`을 시키면서 전제조건을 안 적어** 사고의 기여 원인이었다. 이제 순서를 못박고(커밋 → 뮤테이션 → 원복 → 트리 확인) 게이트 명령과 실측 9건을 적은 뒤 가이드로 링크한다. 두 파일은 여전히 바이트 동일 |
| `HANDOFF.md` 함정 절 | 사고 서술을 규칙 중복이 아니라 **정본 위치를 가리키는 포인터**로 교체 + 전수 조사 결과 |

**왜 §5 패턴을 따랐나**: verification.md 첫 줄이 이미 *"This doc is the canonical home for that policy;
`CLAUDE.md` §5 and `AGENTS.md` §5 link here instead of inlining"* 이다. 절차는 한 곳(가이드),
규칙 파일은 전제조건 한 줄 + 링크 — 같은 규칙이 두 곳에서 갈라질 여지를 만들지 않는다.

### Verification

- `python3 -m pytest -q tests/test_docs_indexes.py` → **9 passed / 10 subtests**(링크·인덱스 가드).
- `diff` 로 `CLAUDE.md` §6 == `AGENTS.md` §6 **바이트 동일** 확인.
