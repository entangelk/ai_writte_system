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
