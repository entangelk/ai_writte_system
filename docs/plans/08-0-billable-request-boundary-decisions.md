# Phase 8 Slice 8.0 — billable request 경계 착수 결정 브리프

상태: `Decision needed — 오너 결정 대기`
작성일: 2026-08-03
부모 계획: [`08-member-request-quota.md`](08-member-request-quota.md) §4 슬라이스 8.0
측정 기준: 베타 머신, HEAD `05286a6`, 정본 [`system-contract-sot.md`](../system-contract-sot.md) v1.7.82

## Decision needed

회원 quota의 단위인 **"서비스 요청 1회"가 코드의 무엇에 대응하는지**를 확정해야 한다. 오너는 기준을
토큰이 아니라 요청 횟수로 정했지만(2026-08-02), 현재 제품에서 하나의 HTTP 요청이 만드는 provider
호출은 **0회에서 15회까지** 변한다. 그래서 "요청 1회"는 기존 계약·코드에서 유도되지 않고, 지금 고르지
않으면 8.1(정책)·8.2(원장)·8.3(시행)이 각자 다른 단위를 가정하게 된다.

이 슬라이스는 **무엇을 세는가**만 정한다. 언제 차감하는지(선차감/예약-확정/성공차감), 기간, 한도 값,
초과 시 HTTP 계약은 8.1~8.3의 결정이다.

## 1. 실측 인벤토리 (2026-08-03, HEAD `05286a6`)

### 1.1 전체 표면

| 항목 | 실측 | 근거 |
|---|---|---|
| 공개 operation | **75개**(ADMIN 8) | [`main.py`](../../services/application/app/main.py) 라우트 데코레이터 전수 |
| provider(LLM)를 부르는 경로 | **10개** = endpoint 9 + 배경 worker 1 | `llm_call_scope(` 개방 지점 |
| LLM 어댑터 종류 | **8개**(`LlmCallSite` 리터럴) | [`observability/llm_call_audit.py:42`](../../services/application/app/observability/llm_call_audit.py#L42) |
| 나머지 65 operation | CRUD·조회·승인·색인·감사 — provider 호출 0회 | 같은 스윕 |
| 프론트가 실제로 부르는 AI 경로 | **5개**(generate·gate·revise-and-gate·accept·analysis run) | `frontend/src` grep. 나머지 4개는 현재 API 전용 |

### 1.2 AI 비용을 쓰는 경로 10개 — 요청 1건당 provider 호출 수

`repair`는 응답이 JSON이 아닐 때 한 번 더 부르는 내부 재시도이고, `라운드`는 계약이 설계한 반복이다.

| 경로 | 트리거 | provider 호출(최소~최대) | 변동의 정체 | 같은 요청 재전송 |
|---|---|---|---|---|
| `POST …/writing/generate` (short) | 프론트 | **3 ~ 5** | 질의 플래너 1(+repair) · 생성 1 · 자기보고서 1(+repair) | 멱등 없음 — 재전송하면 다시 다 부른다 |
| `POST …/writing/generate` (medium/long) | 프론트 | **0** (202 즉시 반환) | 실행은 워커가 한다 | `(project_id, request_id)` 멱등 → 기존 job 반환 |
| `generation_worker` 배경 실행 | 큐 | **3 ~ 5** | 위 short와 같은 3단 | job 1건당 1회 실행, 실패 시 retry endpoint로 재실행 |
| `POST …/writing/generation-jobs/{id}/retry` | 프론트 | **0** (상태만 PENDING으로) | — | 실패 job만 409 없이 통과 |
| `POST …/writing/gate` | 프론트 | **2 ~ 3** | 플래너 1(+repair) · gate 1 | 멱등 없음 |
| `POST …/writing/revise-and-gate` | 프론트 | **4 ~ 15** | 플래너 · revise ≤2 · 보고서 ≤2(+repair) · gate ≤3 · 검색 플래너 1(+repair) · 재검색 플래너 1(+repair) | 멱등 없음 |
| `POST …/writing/accept` | 프론트 | **3 ~ 5** | 플래너 · 보고서 · gate | **replay여도 2~4회를 쓴다**(아래 §1.4) |
| `POST …/writing/report` | API 전용 | **2 ~ 4** | 플래너 · 보고서(+repair) | 멱등 없음 |
| `POST …/writing/revise` | API 전용 | **2 ~ 3** | 플래너 · revise | 멱등 없음 |
| `POST …/context-search` | API 전용 | **1 ~ 2** | 질의 플래너(+repair) | `idempotency_key`는 감사 상관키일 뿐 재실행을 막지 않는다 |
| `POST …/analysis/jobs/{id}/run` | 프론트 | **0** 또는 **1 ~ 2** | 추출 1(+repair) | job이 PENDING이 아니면 **LLM 0회**로 replay |
| `POST …/analysis/jobs/{id}/compare` | API 전용 | **0 ~ 2N** | 매칭된 후보 **1건마다** 판정 1(+repair) | 멱등 없음 |

`revise-and-gate`의 상한 15는 기본 정책(`max_revision_rounds=2`·`max_retrieval_rounds=1`·
`max_gate_evaluations=3`, [`main.py:2536`](../../services/application/app/main.py#L2536))에서 나온 값이다.
env로 올리면 그만큼 커진다.

### 1.3 AI지만 LLM은 아닌 경로

| 경로 | 무엇을 쓰는가 | 규모 |
|---|---|---|
| `POST …/snapshots/{id}/index/source-blocks/rebuild` | 임베딩 서비스 | 스냅샷 블록 수만큼 |
| `POST …/analysis/jobs/{id}/auto-promote` | LLM 0회. 승격 1건마다 재색인 outbox 1건 | 후보 수 N에 비례 |
| 색인 worker(`worker`) | 임베딩 | outbox 소비량만큼 |
| `POST …/analysis/jobs/{id}/context` | 저장소 조회만 | LLM·임베딩 모두 0 |
| `GET …/writing/budget` | 계산만 | 0 |

### 1.4 결정에 영향을 주는 실측 함정 3가지

- **`/writing/accept`의 replay는 공짜가 아니다.** 자기보고서 호출이 멱등 조회보다 **먼저** 일어난다
  ([`writing/accept.py:95`](../../services/application/app/writing/accept.py#L95) → 저장 replay는
  `:105`). 즉 같은 accept를 두 번 보내면 저장은 한 번이지만 provider는 두 번 부른다.
- **`/analysis/jobs/{id}/run`의 replay는 공짜다.** PENDING이 아닌 job은 LLM을 부르지 않고 기존 후보를
  돌려준다([`analysis/runner.py:84`](../../services/application/app/analysis/runner.py#L84)).
  즉 **현재 제품에는 "멱등 = 무과금"인 경로와 "멱등이지만 유과금"인 경로가 함께 있다.**
- **비용 상한이 이미 두 곳에 있다.** 요청별 토큰 상한(출력 프리셋 + K-3 창 가드)과 루프 집계 토큰
  예산([`writing/metering.py`](../../services/application/app/writing/metering.py))이다. 둘 다
  **회원 단위가 아니라 요청 단위**이므로 Phase 8을 대체하지 않지만, "1회의 비용 폭은 이미 위가
  막혀 있다"는 것은 아래 B1·B3 판단의 근거가 된다.

## B1 — 무엇을 1회로 셀 것인가

### Decision needed

quota 원장에 1을 더하는 사건의 정의. 이것이 회원에게 설명되는 숫자이고 8.2 원장의 행 단위가 된다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 명시한 billable action 목록의 HTTP 요청 1건 = 1회** | §1.2의 경로를 "유료 동작" 목록으로 못박고, 그 endpoint 요청 1건이 1회 | 회원에게 설명 가능("이어쓰기 1회") · 차감 지점이 HTTP 경계 하나라 전수 가드가 쉽다 · 오너가 정한 "요청 횟수" 기준 그대로 | 동작마다 실제 원가가 3~15배 차이 · 원가와 매출의 상관이 느슨 |
| B. provider 호출 1건 = 1회 | 감사 레코드처럼 LLM 호출마다 차감 | 원가에 가장 비례 · 이미 seam C가 전 호출을 지난다 | 회원이 예측 불가(같은 버튼이 3회 또는 15회) · 내부 repair 횟수가 요금이 된다 · 계측 seam을 과금 정본으로 승격하게 되어 부모 계획 §5 불변식과 충돌 |
| C. 동작별 가중치(이어쓰기 3, 검사 1 …) | A와 같은 경계에 배수를 곱한다 | 원가 반영과 설명 가능성의 절충 | 지금 가중치를 정할 근거 데이터가 없다 · 상품 정책을 코드로 선결 · 8.1 이후 언제든 A 위에 얹을 수 있다 |
| D. 토큰 기준 | 실제 토큰량으로 차감 | 원가 정확 | **부모 계획이 이미 범위 밖으로 확정**(2026-08-02) |

**Recommendation + reason: A.** 오너 결정의 문언("토큰량이 아니라 서비스 요청 횟수")에 가장 곧게
대응하고, 회원이 자기 사용량을 예측할 수 있는 유일한 선택지다. 원가 비례성은 C가 낫지만 **가중치를
정할 실측 데이터가 아직 없다** — 관측 KPI가 site별 호출 수를 이미 모으고 있으므로, dogfood 데이터가
쌓인 뒤 A의 경계를 그대로 두고 배수만 얹으면 된다(A → C는 무손실, B → A는 아니다). B는 계측
컬렉션을 과금 정본으로 재사용하지 않는다는 부모 계획 불변식과 정면으로 부딪힌다.

## B2 — 내부 repair와 설계된 라운드의 취급

### Decision needed

한 번의 사용자 동작 안에서 일어나는 JSON repair 재시도와 루프 라운드(revise ≤2 · gate ≤3 ·
retrieve ≤1)를 회원에게 청구할지.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 전부 그 1회에 포함(추가 차감 없음)** | repair도 라운드도 내부 구현 | 회원이 제품 내부 품질 문제(비-JSON 응답)의 비용을 지지 않는다 · 프롬프트·모델 개선의 이득이 사업자에게 귀속 | 루프가 긴 요청과 짧은 요청이 같은 값 |
| B. 설계된 라운드는 차감, repair는 무료 | gate 라운드마다 +1 | 원가 반영이 조금 나아짐 | 회원이 통제할 수 없는 gate 판정 수가 요금이 된다 · 화면에 라운드 수를 노출해야 설명 가능 |
| C. 전부 차감 | 호출 수 그대로 | 원가 비례 | B1=B와 사실상 같아진다 |

**Recommendation + reason: A.** repair 재시도는 **12B 모델이 JSON을 어긴 것**이지 회원이 요청한 것이
아니다(HANDOFF의 `report field must be an array` 관찰 항목이 그 빈도를 추적 중이다). 라운드 역시 gate
판정이 정하는 것이라 회원의 선택이 아니다. 통제할 수 없는 것에 과금하면 문의가 발생하고, 그 문의에
답하려면 내부 파이프라인을 설명해야 한다.

## B3 — 항목 수에 비례하는 경로(fan-out)

### Decision needed

`compare`(매칭 후보 N건마다 판정 1회)와 `auto-promote`(후보 N건마다 재색인 1건)처럼 **한 요청의
비용이 데이터 크기에 비례**하는 경로를 1회로 셀지.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 1회로 세고, 표에 fan-out으로 표시한다** | 다른 동작과 동일 취급하되 인벤토리에 명시 | 단순 · 두 경로 모두 현재 프론트 표면에 없다 · N은 원고 길이에서 오지 회원이 임의로 부풀리는 값이 아니다 | 큰 job 1건이 작은 요청 1건과 같은 값 |
| B. 항목 수만큼 차감 | N건이면 N회 | 원가 비례 | B1=A와 단위가 어긋난다 · 회원이 사전에 N을 모른다 · 원장이 한 요청에 N행 |
| C. 요청당 내부 호출 상한을 두고 초과는 400 | 비용을 요금이 아니라 계약으로 제한 | 폭주를 구조적으로 차단 | 정상 큰 원고를 거부할 수 있다 · 상한 값 근거가 아직 없다 |

**Recommendation + reason: A**(+ 8.3에서 C를 재검토). 지금 두 경로는 프론트에 없고 API 전용이라
실제 노출이 작다. 다만 **fan-out 경로임을 인벤토리 표의 열로 남겨** 8.3 시행 슬라이스가 "요청당 내부
호출 상한"을 별도로 판단할 수 있게 한다. B를 고르면 B1=A의 "요청 1건 = 1회"가 예외를 갖게 되고,
회원에게는 "이 버튼은 몇 회인지 누르기 전엔 모른다"가 된다.

## B4 — 조회성·비-LLM AI 경로의 취급

### Decision needed

질의 플래너만 부르는 `/context-search`, 임베딩·색인 경로, 계산만 하는 `/writing/budget`을 유료로
볼지.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. LLM provider를 부르는 경로만 유료. 임베딩·색인은 무료** | §1.2의 10개가 유료, §1.3은 무료 | 경계가 코드로 판정 가능(`llm_call_scope` 개방 여부) · 임베딩은 self-host라 한계비용이 낮다 · 색인 worker는 회원 주체가 없어 귀속 자체가 8.4 난제 | 큰 rebuild가 무료 |
| B. AI 자원을 쓰면 전부 유료 | 임베딩·색인도 차감 | 원가 반영 | 색인 worker에 회원 주체를 실어야 함(비동기 outbox라 귀속 설계가 커진다) · 승인 1번이 재색인 N건을 낳아 설명 불가 |
| C. 사용자가 "산출물"을 받는 것만 유료(생성·gate·보고서·수정·추출) | `/context-search`·`/compare`도 무료 | 회원 관점에서 가장 직관적 | 조회 endpoint로 플래너를 무제한 호출 가능 · API 전용 경로가 무료 우회로가 된다 |

**Recommendation + reason: A.** 유료/무료의 경계가 **코드에서 기계적으로 판정되는** 유일한 안이고
(`llm_call_scope`를 여는가), 그래서 B6의 전수 가드가 "새 AI 경로가 분류 없이 열리면 실패"를 실제로
강제할 수 있다. C는 직관적이지만 무료 경로 하나가 외부 LLM 비용을 그대로 태우는 구멍을 남긴다.
임베딩은 self-host라 지금 단계에서 회원 요금으로 옮길 이유가 약하고, 외부 임베딩 API를 도입하는
슬라이스에서 다시 열면 된다.

## B5 — "같은 한 번"의 정의(재전송·비동기·재시도)

### Decision needed

무엇을 **같은 논리 요청**으로 보아 중복 차감하지 않을지. 부모 계획 §5는 "재전송과 worker 재처리가
같은 논리 요청을 여러 번 세지 않아야 한다"를 불변식으로 못박았고, §1.4는 현재 코드가 경로마다 다르게
행동함을 보여 준다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. `(user_id, project_id, 요청 멱등키)`가 논리 요청. 비동기 job은 enqueue 1회로 세고 worker 실행·retry는 재차감하지 않는다** | 이미 body에 있는 `request_id`/`idempotency_key`를 quota 키로 재사용 | 새 필드 없이 오늘 코드로 성립 · 202 replay와 job 재시도가 자동으로 무료 · 실패한 job을 회원이 다시 돌려도 벌금이 없다 | `request_id`를 안 보내거나 매번 새로 만드는 클라이언트는 보호받지 못함 · gate/report/revise/context-search는 멱등키가 상관키일 뿐이라 재전송이 새 요청이 된다 |
| B. HTTP 요청 1건 = 항상 새 논리 요청 | 멱등을 quota에 반영하지 않는다 | 가장 단순 | 네트워크 재전송·새로고침이 곧 요금 · 부모 계획 불변식 위반 |
| C. 서버가 요청 본문 해시로 중복 판정 | 키 없이도 중복 흡수 | 클라이언트 협조 불필요 | 의도적 재생성(같은 입력, 다른 결과 원함)까지 막는다 · 보관 기간·해시 충돌 정책이 새로 필요 |

**Recommendation + reason: A.** 현재 코드가 이미 두 경로에서 그 키로 멱등을 구현하고 있고
(`writing_generation_jobs.enqueue`·`analysis.create_job`), 8.2 원장의 idempotency key 출처를 새로
발명하지 않아도 된다. **함께 확정할 것**: `/writing/accept`의 replay는 §1.4대로 provider를 이미
부른 뒤이므로, A를 고르면 **"accept replay는 차감하지 않는다"가 원가와 어긋나는 것을 알고 받는
것**이다(대안은 accept의 보고서 호출을 replay 조회 뒤로 옮기는 별도 수정이며, 그 편이 옳지만
8.0의 결정이 아니라 별도 증분이다 — 아래 후속 고려).

## B6 — 인벤토리와 전수 가드의 형태

### Decision needed

부모 계획이 8.0의 완료 증거로 요구한 "billable-action 표 + 호출 경로 전수 가드"를 무엇으로 만들지.
새 AI 경로가 분류 없이 열리는 것을 무엇이 막는가.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 코드 상수 분류표 + 미분류 실패 테스트** | `main.py`의 라우트 전수와 분류 상수를 대조해, `llm_call_scope`를 여는데 분류에 없는 경로가 있으면 실패 | 규칙이 아니라 강제 · `test_compose_exposure.py`(새 포트 분류 강제)와 `test_auth_api.py` tier 전수 가드의 기존 선례 그대로 · quota 저장/차감 코드 없이도 지금 만들 수 있다 | 분류 상수가 아직 아무것도 시행하지 않는 동안 "쓰이지 않는 상수"로 보인다 |
| B. 문서 표만 유지 | 브리프와 SoT에 표를 적는다 | 비용 0 | 새 경로가 조용히 누락된다 — 부모 계획 §5 불변식을 만족하지 못한다 |
| C. 데코레이터·dependency로 표시 | endpoint마다 `Depends(billable(...))` | 시행과 분류가 한 자리 | 8.3 시행 설계를 8.0에서 선결 · 차감 시점 결정 전에 seam 모양을 굳힌다 |

**Recommendation + reason: A.** 8.0이 만들 것은 **분류이지 시행이 아니다**. A는 분류만으로 완결되고,
8.3이 시행을 붙일 때 그 상수를 그대로 소비하면 된다. C는 아직 결정되지 않은 차감 시점(선차감/
예약-확정/성공차감)을 seam 모양으로 미리 정하게 된다.

## 후속 고려 (이 결정이 열어 두어야 하는 문)

- **A → 가중치(C)로의 승격**: B1=A로 정해도 원장 행에 `action` 리터럴이 남으므로, dogfood 데이터가
  쌓인 뒤 요금 배수만 8.1 정책에 얹을 수 있다. 원장 스키마를 action 리터럴 없이 만들면 이 문이 닫힌다.
- **`/writing/accept`의 보고서 호출 위치**(§1.4): replay 조회 뒤로 옮기면 "멱등 = 무과금"이 전 경로에서
  성립한다. 별도 증분이며, 이 브리프는 그 수정을 전제하지 않는다.
- **외부 API 확장**: 외부 LLM provider가 붙어도 분류 기준이 `llm_call_scope` 개방이면 새 provider가
  자동으로 같은 분류를 받는다. provider별로 요금이 달라지는 것은 8.1 이후 정책 문제다.
- **Phase 7 대화형 수정**: 새 호출부가 생기면 B6의 가드가 분류를 강제한다 — 계측(`LlmCallSite` 추가)과
  분류가 같은 시점에 요구되도록 두 가드를 같은 슬라이스에서 본다.
- **관측 KPI와의 관계**: `llm_call_audits`는 과금 정본이 아니지만 **대조 자료로는 유효하다**(요청 1회에
  실제 호출이 몇 번이었는지). 8.7 검증에서 두 숫자를 나란히 보는 것은 유용하다.

## 이번 슬라이스에서 결정하지 않는 것 (범위 밖)

- 차감 시점(요청 시작·예약-확정·성공) 및 실패·취소·timeout의 환원 — **8.3**
- quota 기간(월/일/rolling), 기본 한도 값, 무제한·정지 표현 — **8.1**
- 원장 스키마, 보존 기간, 집계 정본 — **8.2**
- 관리자·내부 작업 면제 여부, worker의 주체 전달 — **8.4**
- 한도 초과 HTTP status와 `detail` 리터럴 — **8.3**
- 결제·플랜·가격 — Phase 8 범위 밖

## 결정 뒤 구현 슬라이스

1. **분류 확정** — B1~B4의 결과를 billable-action 표로 확정하고 이 문서와 SoT에 반영한다.
2. **전수 가드**(B6=A일 때) — 라우트 전수 대비 분류 누락을 실패시키는 테스트를 **먼저** 쓴다.
   양방향으로 잠근다: 분류를 빠뜨리면 실패하고, 무료 경로를 유료로 잘못 넣어도 실패한다.
3. **문서** — `docs/mongo_collections.md`는 아직 손대지 않는다(원장은 8.2). work_log·HANDOFF 갱신.
4. **8.1로 인계** — 정책 모델 브리프가 이 표를 입력으로 받는다.

카운터·원장·차감 코드는 이 슬라이스에서 만들지 않는다.
