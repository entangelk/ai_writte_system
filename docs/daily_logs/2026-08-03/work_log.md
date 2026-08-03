# 2026-08-03 작업 로그

## Task — 베타 머신 전환 확인 + Phase 8 Slice 8.0 착수 브리프

### Goals

- 알파→베타 전환 후 **과거 관측을 믿지 않고** 머신 상태를 다시 잰다(HANDOFF "머신 구성" 절의 요구).
- [`plans/08-member-request-quota.md`](../../plans/08-member-request-quota.md) §4의 **Slice 8.0**을
  착수한다 — "서비스 요청 1회"가 코드의 무엇인지 실측하고, 오너 결정 없이는 고를 수 없는 지점을
  decision brief로 낸다.
- 성공 기준: ① 브리프의 모든 수치가 HEAD 코드 실측 ② 선택지가 사전 필터링되지 않음 ③ 카운터·원장
  코드 0줄 ④ 인덱스 가드 통과.

### 베타 머신 상태 재측정 (2026-08-03)

| 항목 | 실측 | 판정 |
|---|---|---|
| GPU | `NVIDIA GeForce GTX 1060 3GB` | **베타 확정** |
| repo | HEAD `05286a6`, `git status` clean | 검증 커밋 `c2ca946`·마감 커밋 모두 존재 → 머신 간 동기화 완료 |
| compose | `frontend`(healthy) · `worker` · `generation_worker`만 Up. application·mongo·gateway·embedding·chroma·ES는 **없음** | 스택 부분 기동. 이 작업(문서/실측)에는 불필요해 올리지 않았다 |
| test-mongo | 없음 | 베타에는 안 떠 있다(알파에 남겨 둔 것과 다름) |
| 이미지 | gateway 07-31 · application/generation_worker 07-29 · frontend 07-27 · worker 07-27 | **코드보다 뒤처짐**. 특히 `application`(07-29)은 D8-5~D8-7 인증/관리자 작업 이전이다 |
| 외부 LLM | `http://192.168.1.22:9080` 응답, `n_ctx=16384`, `total_slots=1` | 살아 있음. HANDOFF 07-31 관측과 동일 |
| 모델 스냅샷 | `…/snapshots/29d097773436b69ff9feafd636ab4cf873786537/` | 외부 서버가 **새 리비전 `29d0977…`을 이미 쓰고 있다**(알파 `-hf` 부채가 가리키던 그 리비전) |

- **주의(다음 작업자)**: 화면 육안 확인이나 라이브 관통을 하려면 `application`·`frontend`를 먼저
  재빌드해야 한다. HANDOFF의 ★★ 항목대로 **낡은 `application` 이미지는 죽지 않고 "인증 없는 제품"으로
  뜬다** — 스택을 올렸다면 `curl :8520/projects`가 401인지부터 확인한다.
- `.env`는 `LLAMA_BASE_URL=http://192.168.1.22:9080` 한 줄만 유효하게 들고 있다(커밋되지 않음).

### Completed work — Slice 8.0 실측 인벤토리

코드 실측으로 다음을 확정했다(브리프 §1에 표로 수록).

- **75 operation** 중 provider(LLM)를 부르는 경로는 **10개** = endpoint 9 + `generation_worker` 1.
  판정 기준은 `llm_call_scope(` 개방 지점이며 `LlmCallSite` 리터럴 8개(어댑터 수)와는 다른 숫자다.
- 그중 **프론트가 실제로 부르는 것은 5개**(generate · gate · revise-and-gate · accept · analysis run).
  `report` · `revise` · `context-search` · `compare`는 현재 **API 전용**이다.
- 요청 1건당 provider 호출 수의 폭(기본 정책 기준):
  - `writing/generate`(short) **3~5**, medium/long은 **요청 시점 0**(202) + 워커에서 3~5
  - `writing/gate` **2~3** · `writing/report` **2~4** · `writing/revise` **2~3**
  - `writing/revise-and-gate` **4~15**(revise ≤2 · gate ≤3 · retrieve ≤1, `main.py:2536` 기본값)
  - `writing/accept` **3~5**
  - `analysis/jobs/{id}/run` **0**(replay) 또는 **1~2**
  - `analysis/jobs/{id}/compare` **0~2N**(매칭 후보 1건마다 판정 1 + repair 1)
  - `context-search` **1~2**
- **비-LLM AI 경로**를 따로 분류했다: 색인 rebuild·`auto-promote`의 재색인 outbox·색인 worker(임베딩),
  그리고 LLM·임베딩을 모두 쓰지 않는 `analysis/jobs/{id}/context`·`writing/budget`.

### Issues found (결정에 직접 영향을 준 실측 함정)

- **`/writing/accept`의 멱등 replay는 무료가 아니다.** 자기보고서 호출이 멱등 조회보다 **먼저**
  일어난다([`accept.py:95`](../../../services/application/app/writing/accept.py#L95) vs `:105`). 같은
  accept를 두 번 보내면 저장은 1회지만 provider는 두 번 불린다.
- **반대로 `/analysis/jobs/{id}/run`의 replay는 완전 무료다**([`runner.py:84`](../../../services/application/app/analysis/runner.py#L84)).
  → 현재 제품에는 "멱등 = 무과금"과 "멱등인데 유과금"이 **공존**한다. quota의 논리 요청 정의(B5)가
  이 불일치를 알고 내리는 결정이 되도록 브리프 §1.4에 명시했다.
- **`compare`는 fan-out이다** — 매칭된 후보 수 N에 비례해 판정 호출이 늘어난다
  ([`compare.py:147`](../../../services/application/app/analysis/compare.py#L147)). `auto-promote`도 같은
  형태(N건의 재색인 enqueue)다. "요청 1건 = 1회"를 그대로 적용하면 비용이 데이터 크기에 비례하는
  경로가 예외 없이 1회가 된다 → 별도 결정 항목(B3)으로 분리했다.
- **이미 있는 비용 상한은 전부 "요청 단위"다**(출력 프리셋 · K-3 창 가드 · 루프 집계 토큰 예산
  `writing/metering.py`). 회원 단위 상한은 없으므로 Phase 8을 대체하지 않지만, "1회의 비용 폭은 위가
  이미 막혀 있다"는 근거가 되어 B1/B3 추천의 논거로 썼다.

### Completed work — 브리프

- [`plans/08-0-billable-request-boundary-decisions.md`](../../plans/08-0-billable-request-boundary-decisions.md)
  작성. 결정 항목 6개, 각각 선택지 표(`선택지 | 설명 | 장점 | 단점`) + 추천·근거:
  - **B1 차감 단위** — A) billable action 목록의 HTTP 요청 1건 / B) provider 호출 1건 / C) 동작별 가중치 /
    D) 토큰(부모 계획이 이미 배제). **추천 A**.
  - **B2 내부 repair·설계된 라운드** — A) 전부 1회에 포함 / B) 라운드만 차감 / C) 전부 차감. **추천 A**.
  - **B3 fan-out 경로** — A) 1회로 세고 표에 표시 / B) 항목 수만큼 / C) 요청당 내부 호출 상한 400.
    **추천 A**(+ 8.3에서 C 재검토).
  - **B4 조회성·비-LLM 경로** — A) LLM을 부르면 유료, 임베딩·색인은 무료 / B) AI 자원 전부 유료 /
    C) 산출물을 받는 것만 유료. **추천 A**.
  - **B5 "같은 한 번"의 정의** — A) `(user, project, 멱등키)` + 비동기는 enqueue 1회 / B) HTTP 1건 =
    항상 새 요청 / C) 본문 해시 중복 판정. **추천 A**.
  - **B6 전수 가드 형태** — A) 분류 상수 + 미분류 실패 테스트 / B) 문서 표만 / C) 데코레이터·dependency.
    **추천 A**.
- 후속 고려(A→가중치 승격 여지, accept 보고서 호출 위치 수정, 외부 provider·Phase 7 자동 편입,
  KPI와의 대조 용도)와 **범위 밖**(차감 시점·기간·원장 스키마·면제·초과 HTTP 계약)을 명시했다.
- [`plans/README.md`](../../plans/README.md) Phase 8 절에 등재했다(인덱스 가드가 미등재를 막는다).

### Decisions

- **8.0에서 정하는 것은 "무엇을 세는가"뿐이고 "언제 차감하는가"는 8.3에 남긴다.** 부모 계획의 슬라이스
  분할이 그렇게 되어 있고, 차감 시점까지 여기서 정하면 seam 모양을 시행 결정 전에 굳히게 된다.
- **카운터·저장 모델·차감 코드는 한 줄도 쓰지 않았다**(HANDOFF Next Tasks의 명시 조건).
- 추천을 달되 선택지를 사전 필터링하지 않았다 — B1의 C(가중치)·D(토큰)처럼 지금 채택하지 않을
  선택지도 근거와 함께 행으로 남겼다(CLAUDE.md "오너 결정 브리프" 요구).

### Verification

- `python3 -m pytest -q tests/test_docs_indexes.py`: **7 passed / 4 subtests**.
- `git diff --check`: clean.
- 브리프의 수치는 전부 HEAD `05286a6` 코드에서 직접 센 값이다(라우트 데코레이터 전수 파싱,
  `llm_call_scope` 개방 지점, 루프 정책 기본값, repair 유무 파일별 확인, 프론트 `client.ts` 호출 목록).

### Next steps

- 오너 결정(B1~B6)을 받는 즉시 분류 확정 → 전수 가드 → 기록 → 8.1 인계.
- 화면 육안 확인 2건(HANDOFF Next Tasks 2번)은 이미지 재빌드가 선행돼야 한다. 이번 작업은 스택을
  올리지 않았으므로 손대지 않았다.

---

## Task — Slice 8.0 결정 반영·분류표·전수 가드 (SoT v1.7.83)

### Goals

- 같은 날 받은 오너 결정 **B1~B6 = 전부 A**를 코드 정본과 계약에 반영한다.
- 성공 기준: ① 분류표가 코드에 있고 ② 전수 가드가 **양방향**으로 물며 ③ 카운터·원장·차감 코드는
  여전히 0줄 ④ 기존 회귀 기준선 무변.

### User Decisions and Rationale

- **B1 = A (요청 1건 = 1회).** 오너 근거는 원가 정확성이 아니라 **제품 성격**이다 — "우리는
  사용자에게 쉬운 서비스를 제공해야 한다". 그리고 **동작별 원가 차이는 요금 단위로 옮기지 않고
  내부 BM(요금제 설계·원가 관리)에서 흡수한다**고 명시 지시했다. 따라서 가중치안(C)은 "나중에
  얹을 수 있는 것"이 아니라 **회원에게 보이는 단위로는 채택하지 않기로 한 것**이다. 회원이 보는
  숫자는 끝까지 "요청 몇 회"다. 이 문장을 브리프 §0·모듈 docstring·SoT에 그대로 남겼다.
- **B2 = A, 단서 있음.** 내부 repair·재시도는 "우리가 서비스로서 처리하는 기술 문제"라 청구하지
  않는다(B1과 같은 사고). **다만 repair를 포함한 내부 호출은 전부 우리 관측 안에 있어야 한다.**
  → 과금과 관측을 분리한 요구다. 새 계측을 만들지 않고 기존 구조로 충족됨을 확인해 근거를
  브리프 §3.1에 적고 가드로 잠갔다(아래 "관측 요구 충족 근거").
- **B3·B4·B5 = A.** "B1·B2와 동일한 사고이기 때문"이라는 오너 설명 그대로, 같은 방향으로 확정.
- **B6 = A.** 분류표를 코드 정본으로 두고 미분류를 테스트가 실패시킨다.

### Completed work

- **[`quota/billable_actions.py`](../../../services/application/app/quota/billable_actions.py) 신규** —
  유료 동작 **9개**의 정본 표(`BillableAction` 리터럴·method·path·`fan_out`)와 `BILLABLE_OPERATIONS`
  조회 집합. docstring이 B1~B6 결정과 **표에 일부러 없는 것 둘**(generation worker 실행 · job retry,
  둘 다 같은 논리 요청)의 이유를 담는다. **카운터·차감·저장 코드 없음.**
- **[`tests/test_billable_actions.py`](../../../tests/test_billable_actions.py) 신규** — 8 cells.
  핵심은 `opens_scope == BILLABLE_OPERATIONS` 집합 동치라 **한 셀이 양방향을 동시에 문다**.
  파싱이 라우트를 놓치면 다른 셀이 조용히 약해지므로 **파싱 결과를 실제 `app.routes`와 대조하는
  셀을 먼저** 뒀다(가드의 가드).
- **문서** — 브리프에 §0 오너 결정·§3 확정 표·§3.1 관측 근거·§4 뮤테이션 기록을 더하고 상태를
  `Resolved`로, plans index도 갱신. SoT **v1.7.83** 변경이력 + 헤더 버전/갱신일. CHANGELOG 1행.

### 관측 요구(B2 단서) 충족 근거 — 새 계측 없이 성립한다

1. **유료 경로 9개가 전부 `llm_call_scope`를 연다.** 실제로는 그 역이 분류 기준(B4)이라 구조적으로
   참이며, 새 가드의 집합 동치 셀이 이것을 잠근다.
2. **repair 호출은 자기 레코드로 남는다.** seam C가 provider를 감싸므로 구조적이고, 이미
   `test_llm_call_scope.py::test_a_repaired_extraction_leaves_two_records_not_one`과
   `test_llm_call_sites.py::test_a_repaired_verdict_leaves_two_records_both_successful`이 잠그고 있다.
   **중복 셀을 만들지 않고 참조**했다.
3. **비동기 실행도 관측된다.** `generation_worker`가 job의 `project_id`/`request_id`로 scope를 연다 →
   새 셀 `test_the_generation_worker_is_observed_but_not_billed`가 "관측은 되고 과금은 안 된다"를
   한 자리에서 단정한다.
- 같은 `correlation_id` 아래 레코드가 모이므로 "요청 1회에 내부 호출이 몇 번이었는가"를 사후에
  셀 수 있다(KPI `multi_call_correlations`가 이미 그 축).
- **공백 1건을 정직하게 남긴다**: 루프 내부 gate 레코드에는 `decision`·`gate_quality_score`가 없다
  (v1.7.47 기존 공백). **호출 수 차원의 관측 요구는 충족**되고 이것은 파생 필드 공백이라 별건이다.

### Regression guards and adversarial mutations

가드가 실제로 무는지 **뮤테이션 7종**으로 확인했다. 전부 넣고 원복했으며, 원복은 백업 파일과
`diff`로 동일함을 확인했다(`git checkout --` 금지 — 미커밋 슬라이스를 날린다, HANDOFF 함정).

| # | 뮤테이션 | 방향 | 결과 |
|---|---|---|---|
| M1 | `context_search` 분류 삭제 | under-strict | 3 failed |
| M2 | 무료 `GET …/writing/budget`를 유료로 오분류 | over-strict(B4) | 2 failed |
| M3 | 분류 경로 오타(`writing/gate`→`gates`) | over-strict | 3 failed |
| M4 | action 리터럴 개명(`writing_accept`→`accept_v2`) | over-strict | 1 failed |
| M5 | 재시도 endpoint를 유료로 추가 | B5 위반 | 3 failed |
| M6 | **분류 없이 새 LLM endpoint 추가**(다중행 데코레이터) | under-strict | 2 failed |
| M7 | 파서 약화(다중행 데코레이터 미인식) | 가드의 가드 | 1 failed |

M6이 이 가드의 존재 이유다 — 부모 계획 §5의 "새 AI 경로가 분류 없이 조용히 열리면 실패해야 한다"가
실제로 성립함을 보인다. M7은 나머지 셀이 전부 소스 파싱에 기대므로 **파서가 약해지면 가드가
조용히 약해진다**는 것을 잡는다.

### Pattern sweep

- `llm_call_scope(` 개방 지점을 repo 전체로 다시 스윕했다: `main.py` 9곳 + `generation_worker.py` 1곳
  **뿐**이다(scripts·diagnostic 포함 그 외 0건). 분류표가 덮는 범위와 정확히 일치한다.
- 임베딩 호출부(`.embed(`) 9곳도 확인했다 — 전부 B4=A의 무료 쪽(색인·검색·semantic matcher)이며
  유료 경로와 겹치지 않는다.

### Issues found

- 없음. 기존 코드는 한 줄도 고치지 않았다(분류는 추가만).
- 부수 관측: `docker compose -f docker-compose.test.yml up -d`가 test-mongo를 **Recreated**해
  `docker port`가 `127.0.0.1:27020`을 보였다 — D8-7 G1=C의 loopback 바인드가 이 컨테이너에서는
  **런타임으로도** 적용됐다(HANDOFF의 "파일 수준 시행" 함정이 재생성으로 닫히는 실례).

### Verification

- `python3 -m pytest -q tests/test_billable_actions.py`: **8 passed / 75 subtests**.
- 전체 backend(test-mongo ON, 베타): **1922 passed / 1 skipped / 1700 subtests** (776s).
  - **직전 기준선은 알파의 1911/4/1625다.** 차이는 전부 설명된다: **+8 passed·+75 subtests = 이번 신규
    파일**, **+3 passed·−3 skipped = 알파에서 skip되던 3건이 베타에서는 실행됐다**(머신·인프라 차이).
    남은 skip 1건은 호스트 pytest에서 구조적으로 항상 skip되는 live Chroma 셀
    (`test_chroma_adapter.py:490`, `-rs`로 사유 확인). **회귀는 0건이다.**
  - HANDOFF의 "skip 수는 머신마다 다르니 같은 환경에서 비교한다"가 그대로 관측된 사례다.
- `python3 -m pytest -q tests/test_docs_indexes.py`: **7 passed / 4 subtests**.
- `git diff --check`: clean. 뮤테이션 원복은 `diff`로 바이트 동일 확인.

### Next steps

- **8.1 정책 모델 브리프**가 다음 작업이다. 입력은 브리프 §3의 확정 표이고, 결정할 것은 기간·기본
  한도·개별 override·무제한/정지 표현·정책 변경 효력 시점이다.
- 8.2 원장 설계 시 **행에 `action` 리터럴을 남긴다** — 회원 단위에는 가중치를 안 쓰기로 했으므로,
  원가를 사업 쪽에서 계산하려면 그 리터럴이 유일한 축이다.
- 별도 증분 후보: `/writing/accept`의 자기보고서 호출을 멱등 replay 조회 뒤로 옮기면 "멱등 =
  무과금"이 전 경로에서 성립한다.

---

## Hardening — Slice 8.0 독립 검증(`3b7afc8`) 반영

### Goals

- 검증 판정은 **합격(Blocking 0)**이므로 계약을 바꾸지 않는다. 비차단 지적 H1~H4만 닫는다.
- 원칙: **표현이 과했으면 표현을 고치고, 관습이던 것은 가드로 바꾼다.**

### Verification review

- [`verifications/2026-08-03/slice_8_0_billable_boundary.md`](../../verifications/2026-08-03/slice_8_0_billable_boundary.md)
  원문 확인. 검증자가 scope 스윕·정규식 재파싱·전체 suite(778s)·뮤테이션 2종을 **독립 재도출**했고
  구현자 주장(9=9 동치, 1922/1/1700, M1=3·M2=2 failed)과 전부 일치했다.
- 검증자가 B2 의존처(`test_llm_call_scope.py`·`test_llm_call_sites.py`의 repair 셀)를 **본문 직독**해
  `len(calls)==2` + over-strict 짝까지 있는 진짜 양방향 가드임을 확인했다 — 브리프 §3.1의 위임이
  빈 칸이 아니다.

### 보강 — H1 (표현이 과했다)

지적: 브리프·모듈이 B4 기준을 "기계적으로 확인된다"·"강제"라고 적었으나, 강제되는 것은 **scope를
여는 route까지**다. `ObservedProvider.generate`가 scope 없는 호출을 미기록 통과시키므로(worker·script를
위한 기존 계약) provider를 부르되 scope를 안 여는 미래 route는 관측도 분류도 비껴간다.

- **표현 정정 3곳** — 모듈 docstring B4 항·브리프 B4 추천·테스트 모듈 docstring에 **사정거리**를
  명시했다. SoT v1.7.83 항목에도 같은 문장을 넣었다(계약 문서가 과장을 들고 있으면 안 된다).
- **관습을 가드로** — 검증자가 "완화층은 있다(per-endpoint 셀)"고 했는데, **그 대응이 관습**이라
  새 유료 동작이 관측 셀 없이 추가돼도 아무것도 실패하지 않았다. `BillableActionObservabilityCoverageTest`를
  더해 ① 대응표의 키가 유료 동작 전수와 같은지 ② 지목한 셀이 실제로 **실존**하는지를 단정한다.
  대응 실측: 7개는 `EndpointOpensAScopeTest`, `analysis_extract`는 `RunEndpointOpensAScopeTest`,
  `writing_gate`는 `WritingGateObservabilityTest`(다른 파일이라 처음엔 공백을 의심했으나 직독해 보니
  endpoint를 구동해 레코드를 단정하는 진짜 셀이었다 — **주장 전에 확인했다**).
- **잔존 한계는 닫지 않고 표면화** — 정적 탐지나 scope-None 진단 메트릭은 별도 판단이라 하지 않고
  HANDOFF 추적 부채에 "새 호출부는 감싸기·scope·분류 셋이 함께 간다"로 남겼다.

### 보강 — H2 (셀이 문자열만 봤다)

`test_the_generation_worker_is_observed_but_not_billed`가 worker 소스에 `llm_call_scope(`가 있는지만
보고 **어떤 상관키로 여는지**는 안 봤다. 상관키가 B5의 실체(같은 논리 요청 귀속)이므로
`project_id=job.project_id`·`correlation_id=job.request_id`를 셀에 못박았다.

### 보강 — H3 (가드 밖의 숫자가 얼어 있었다)

- 지적: `docs/verifications/README.md`·`README.md`가 **39일치**라 적는데 실제는 **40일치**. 원인은
  `VerificationCountClaimsTest`의 패턴이 `39일치`를 **리터럴로 고정**해 일수가 가드 대상이 아니었다는
  것 — 게다가 40으로 고치면 패턴이 매칭에 실패해 **고치는 쪽이 깨지는** 상태였다.
- 패턴을 `(\d+)일치`로 바꾸고 `_DAY_COUNT_CLAIMS` + 전용 셀을 더해 **일수도 디스크에서 유도**하게
  했다. 두 문서를 40으로 바로잡았다.
- **패턴 스윕에서 같은 병 4곳을 더 찾았다**(같은 가드 밖의 숫자 주장): `README.md`가 브리프 **73개**·
  인덱스 **89개**, `docs/plans/README.md`가 **89개 중 73개**라 적는데 실제는 **92개 중 75개**였다.
  세는 규칙(전체 = `docs/plans/*.md` − 인덱스 자신, 브리프 = `*-decisions.md`)을 가드에 고정하고
  네 주장을 전부 실측값으로 고쳤다.

### 보강 — H4 (내가 만든 드리프트)

최상위 `README.md`의 회귀 기준선 **1,911 / 1,625 subtests** → **1,922 / 1,700**, SoT **v1.7.82** →
**v1.7.83**. 슬라이스 8.0에서 HANDOFF·CHANGELOG·SoT는 고치고 README만 놓친 자리다.

### Regression guards and adversarial mutations

새로 만든 가드가 무는지 **4종**으로 확인(전부 백업 원복, `git status`로 원복 확인):

| # | 뮤테이션 | 결과 |
|---|---|---|
| H1b-M1 | 새 유료 동작을 **관측 셀 없이** 분류표에 추가 | 3 failed(대응표 셀 포함) |
| H1b-M2 | 대응표가 지목한 관측 셀을 개명(삭제 시뮬) | 1 failed |
| H2-M | 워커 상관키를 `job.request_id` → `job.id`로 | 1 failed |
| H3-M | 일수를 39로 되돌림 | 1 failed |

### Verification

- `python3 -m pytest -q tests/test_billable_actions.py`: **10 passed / 84 subtests**(종전 8/75).
- `python3 -m pytest -q tests/test_docs_indexes.py`: **9 passed / 10 subtests**(종전 7/4).
- 전체 backend(test-mongo ON, 베타): **1926 passed / 1 skipped / 1715 subtests**(920s).
  보강 전 1922/1/1700 대비 **+4 passed·+15 subtests = 이번에 더한 셀 그대로**(관측 대응표 2 · 일수 1 · plans 수 1, subtests 9+2+4). **회귀 0건.**
- `git diff --check`: clean. 뮤테이션 4종 원복은 `git status`로 확인.

### Next steps

- 변함없이 **8.1 정책 모델 브리프**. 이번 보강은 계약을 바꾸지 않았다(표현 정정 + 가드 추가).

---

## Task — Phase 8 Slice 8.1 정책 모델 착수 브리프

### Goals

- 8.0이 닫은 "요청 1회"에 **한도를 붙이는 저장 계약**을 결정 브리프로 낸다.
- 성공 기준: ① 수치·관례가 전부 HEAD 실측 ② 선택지 사전 필터링 없음 ③ 저장/시행 코드 0줄
  ④ 인덱스 가드 통과.

### Completed work — 실측

브리프 §1에 표로 수록. 결정에 직접 영향을 준 것 넷:

- **백엔드에 지역 시간대 개념이 0곳이다.** 전부 `datetime.now(UTC)`이고 `zoneinfo` 사용처가 없다.
  프론트만 `toLocaleString("ko-KR")`로 브라우저 로컬 렌더. → "매월 1일 리셋"의 1일이 **어느 시간대의
  1일인지**가 이 슬라이스의 새 결정이 된다(P2).
- **스택에 스케줄러가 없다.** 워커 2종은 폴링 루프이고 cron/APScheduler 0건. → "매월 리셋 작업"은
  기능이 아니라 **새 인프라**이며, 이것이 P3(기간 파생 vs 저장)을 별도 결정으로 분리한 이유다.
- **무제한 표현 선례가 이미 있다** — `_env_opt_int`의 `None`=상한 없음(루프 토큰 예산). P5 추천의 근거.
- **기본값 표현 선례** — 루프 정책의 "코드 기본 + env override". 전역 기본을 DB에 두지 않는 관례이며
  P4 추천의 근거.
- 그 밖에 `users` 모델·인덱스 명명 규칙·`docs/mongo_collections.md` §43B 형식·naive/aware 함정을
  기준선 표에 적어 구현 슬라이스가 다시 재지 않게 했다.

### Completed work — 브리프

- [`plans/08-1-request-quota-policy-decisions.md`](../../plans/08-1-request-quota-policy-decisions.md).
  결정 7개, 각각 선택지 표 + 추천·근거:
  - **P1 저장 위치** — A) 별도 컬렉션 / B) `users` 필드 / C) env 기본+override. **추천 A**.
  - **P2 기간 종류·경계** — A) 달력 월 KST / B) 달력 월 UTC / C) 가입일 30일 / D) rolling. **추천 A**.
  - **P3 기간 파생 vs 저장** — A) 파생(리셋 작업 없음) / B) 저장+갱신 / C) 혼합. **추천 A**.
  - **P4 기본과 override** — A) 행 없으면 코드 기본 / B) 가입 시 전원 행 생성 / C) DB 전역 설정 행.
    **추천 A**.
  - **P5 무제한·정지 표현** — A) `limit: int|None` + `status` enum / B) sentinel 숫자 / C) boolean 2개.
    **추천 A**.
  - **P6 변경 효력 시점** — A) 즉시 / B) 다음 기간 / C) 상향만 즉시. **추천 A**.
  - **P7 기본 한도 값** — A) 넉넉히 시작해 dogfood로 조정 / B) 보수적 / C) 기본 무제한. **추천 A**.
- 후속 고려(기간 키 계산은 한 곳·8.6 결제 갱신 자리·회원 삭제와의 관계·관리자 면제는 구조 변경 없이
  가능)와 **범위 밖**(차감 시점·초과 HTTP·원장·관리자 API·면제·결제)을 명시했다.
- [`plans/README.md`](../../plans/README.md)에 등재.

### Decisions

- **P3을 P2에서 분리했다.** 부모 계획은 8.1의 결정 항목으로 "기간 종류와 경계 시각"만 적었지만,
  실측해 보니 **기간을 파생할지 저장할지가 새 인프라(스케줄러) 필요 여부를 가르는** 더 큰 갈림길이다.
  묶어서 제시하면 오너가 그 비용을 못 보고 고르게 된다.
- **P6=A의 부작용을 브리프가 미리 인정한다** — 즉시 반영을 고르면 "이미 쓴 양 > 새 한도"가 표현
  가능해진다. 그 상태를 **정상으로 인정**하는 것까지만 8.1이 정하고, 그때 무엇을 하는지는 8.3에 넘겼다.
- 저장·시행 코드는 0줄이다. 8.0과 같은 규칙.

### Verification

- `python3 -m pytest -q tests/test_docs_indexes.py`: **9 passed / 10 subtests**.
  - **오늘 아침 보강한 가드가 바로 물었다** — 브리프를 추가하자 `docs/plans` 문서 수 주장 4곳이
    92/75로 뒤처져 실패했고, 93/76으로 고쳐 통과했다. H3 보강이 의도대로 동작한 첫 사례다.
- 브리프의 상대 링크 5건 전부 디스크에서 해석됨. `git diff --check`: clean.

### Next steps

- **오너 결정 대기: P1~P7.** 결정 뒤 순서는 브리프 "결정 뒤 구현 슬라이스"대로 ① 계약·양방향 회귀
  먼저(기간 경계·무제한/정지/0회 구분·행 없음→기본·naive/aware 왕복) → ② 도메인+Mongo 어댑터
  (fake-collection 왕복 필수) → ③ `docs/mongo_collections.md` 등재 → ④ 8.2 원장 브리프.

---

## Task — Slice 8.1 오너 1차 결정 반영 (P2 재구성)

### User Decisions and Rationale

- **★ 사용량 초기화 주기와 구독 이용기간은 다른 축이다**(오너, 2026-08-03). 초판 P2가 그 둘을 "기간"
  하나로 묶어 물은 것이 잘못이었다. 사용량 창은 **매일 자정 리셋 + 주간 사용 횟수 상한**(이중 창)이고,
  **구독 개월 카운트는 별도 축**으로 가입/결제일 기준이다. 초판 선택지 C("가입일 기준")는 사용량이
  아니라 **구독 축**에 적용된다는 뜻으로 확인했다.
- **P5** — A의 원칙(수량과 상태 분리, `None`=무제한) 유지. 다만 창이 둘이 됐으니 형태는 재설계하라는
  지시. → `daily_limit`·`weekly_limit`(각각 `int | None`) + `status` enum.
- **P6** — C(상향 즉시·하향 유예)를 기본으로 하되 **유예분은 저장되어 현재 주의 끝에 발효**해 다음
  주부터 적용.
- **P7** — 데이터가 없으므로 **숫자를 지금 하드코딩하지 않는다**. 지금은 서비스가 아니라 테스트
  단계이므로 나중에 고치기 쉬운 자리에 두고, 계산이 필요해지면 계산 코드가 들어갈 자리를 남긴다.
- P1·P3·P4는 이의 없음 → 추천 A 유지.

### Completed work

- 브리프에 **§0 오너 1차 결정** 절을 넣고 P2를 재구성(확정 사항 + 신규 하위 결정 P2-a·P2-b),
  P5를 창 2개에 맞춰 재설계, P6을 발효 시점까지 확정, P7을 "값이 아니라 자리"로 확정, **P8(구독 축을
  이번에 저장할지)** 을 신규 결정으로 추가했다. plans index 상태도 `부분 확정`으로 갱신.

### Issues found — 오너 결정이 새로 연 것 (전부 브리프에 결정 항목으로 세움)

- **매일 리셋이 되면서 시간대 문제가 커졌다**(P2-a). 초판에서는 월 1회 어긋나던 것이 이제 **매일**
  어긋난다 — UTC 자정은 한국에서 매일 09:00이다. 추천 KST(경계 계산만 지역 시간대, 저장은 UTC).
- **"주"의 기준이 미정이다**(P2-b). 달력 주(월요일) vs 가입일 rolling 7일. P6이 "현재 주의 끝"을
  발효 시점으로 쓰기 때문에, 주 경계가 전 회원 공통이 아니면 "언제 바뀌나요"의 답이 회원마다 달라진다.
  추천 달력 주·월요일 시작.
- **정지(`status`)를 하향으로 취급하면 남용 대응이 최대 1주 늦어진다.** P6의 유예 규칙은 수량 두
  필드에만 걸고 `status`는 즉시 적용하기를 추천(브리프에 예외로 명시).
- **P6 판정은 필드별이어야 한다.** 일↑·주↓ 같은 혼합 변경에서 덩어리로 보면 한쪽 때문에 다른 쪽까지
  즉시/유예가 된다.
- **주 한도가 의미를 가지려면 `주 < 일 × 7`** 이지만, 저장 계약이 이 부등식을 강제하지는 않기로 했다
  (무의미한 조합 금지는 과잉이고, 일시적으로 주만 크게 두는 것도 정당한 설정이다).
- **P6은 예약 저장을 요구하지만 worker는 필요 없다** — `유효 정책(정책, 지금)`이 순수 함수라
  "지금이 발효 주 키 이후인가"만 보면 된다. P3(파생)과 같은 성질이라 스케줄러 없이 성립한다.

### Verification

- `python3 -m pytest -q tests/test_docs_indexes.py`: **9 passed / 10 subtests**. `git diff --check`: clean.
- 코드 변경 0줄(브리프·인덱스·기록만).

### Next steps

- **오너 결정 대기: P2-a(시간대) · P2-b(주 기준) · P8(구독 축 범위)**, 그리고 P6의 `status` 즉시 예외와
  P7 잠정값(`일 20 / 주 100` 제안) 확인. 이 다섯이 닫히면 곧바로 계약·양방향 회귀부터 구현한다.
