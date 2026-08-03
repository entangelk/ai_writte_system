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

---

## Task — Slice 8.1 2차 결정 반영 + 정책 저장 계약 구현 (SoT v1.7.84)

### User Decisions and Rationale

- **P2-a = KST** ("당연히"). 매일 리셋이라 UTC 자정(한국 오전 9시)은 매일 어긋난다.
- **P2-b = 가입일로부터 7일** — 구현자 추천(달력 주·월요일)을 **기각**했다. 회원마다 온전한 7일을
  주는 쪽을 택한 것이며, 대가("이번 주"가 전역 개념이 아니다)는 브리프에 명시했다.
- **P6의 `status` 즉시 예외 = 기각.** "최대 1주 늦어지는 거 상관없음. 고객 입장에서 사용감 편의가
  먼저." → 정지도 다른 필드와 같은 규칙(불리 = 유예)을 따른다. 해제는 유리하므로 즉시다.
- **P7 잠정값** 이의 없음 → `일 20 / 주 100`. 요지는 값이 아니라 **자리**다.
- **P8은 구현자 판단에 위임**("페이즈 단위까지 커지면 페이즈 계획서 작업해서 하고") → **A(8.6으로
  미룸)** 를 택했고 **새 Phase 계획서는 만들지 않았다** — 구독/결제는 이미 부모 계획의 8.6으로 잡혀
  있어 Phase 단위로 커지는 작업이 아니다.

### Issues found

- **정지 유예를 받기 전에 안전망을 실측했다**: 계정 비활성화는 세션 해석이 매 요청 `is_active`를
  보므로([`main.py:1456`](../../../services/application/app/main.py#L1456)) **이미 발급된 세션까지 즉시**
  끊는다. 즉 "즉시 차단 수단이 없다"가 아니라 **quota 정지(요금 정책)와 계정 차단(출입)이 다른
  도구**인 것이다. 이 사실이 오너 결정을 안전하게 만든다 — 브리프·SoT에 근거로 남겼다.
- **가입 "일" vs 가입 "시각"이 미결이었다.** 오너 문언이 "가입일"이므로 기준점을 가입일의 **KST
  자정**으로 잡았다. 시각 기준이면 주 경계가 오후에 걸려 **두 창이 다른 순간에 넘어간다**("오늘
  리셋됐는데 왜 또 바뀌나"). 회귀가 이 선택을 직접 단정한다.

### Completed work

- **[`quota/policy.py`](../../../services/application/app/quota/policy.py)** — 창 파생(일 KST 자정 ·
  주 가입일 기준 7일) · 한도 표현(`int | None` + `status`) · 기본값 해석(env override) · 유·불리
  **필드별** 분리 · 저장소 seam · in-memory fake · 서비스. **이 저장소의 유일한 지역 시간대 지점**이다.
- **[`quota/policy_mongo.py`](../../../services/application/app/quota/policy_mongo.py)** —
  `request_quota_policies`, `_id`=`users._id`(회원당 한 행을 DB가 강제). 조회 축이 그것뿐이라
  **추가 인덱스 없음**이며 그 이유를 모듈과 컬렉션 문서에 적었다.
- **[`docs/mongo_collections.md`](../../mongo_collections.md) §43C** 등재. SoT **v1.7.84**, CHANGELOG,
  브리프 상태·구현 결과, plans index, README SoT 표기.
- **배선하지 않았다** — `create_app`에서 아무도 이 저장소를 만들지 않는다. 소비자가 8.3에서 생기며,
  소비자 없이 배선만 넣는 것은 이 저장소의 관례가 아니다.

### Regression guards and adversarial mutations

회귀 **26 cells**. 경계는 **직전·직후를 함께** 단정한다(한쪽만 보면 `<`↔`<=` 실수가 통과한다).

| # | 뮤테이션 | 방향 | 결과 |
|---|---|---|---|
| M1 | 경계 시간대를 UTC로 되돌림 | P2-a under-strict | 4 failed |
| M2 | 주 기준을 가입 **시각**으로(자정 정렬 제거) | P2-b | 2 failed |
| M3 | 하향도 즉시 적용(유예 제거) | P6 under-strict | 7 failed |
| M4 | 유·불리를 덩어리로 판정 | P6 필드별 | 1 failed |
| M5 | 무제한 rank를 0으로 뒤집음 | P5 | 1 failed |
| M6 | `_aware` 제거(naive 재부착 무력화) | Mongo 함정 | 2 failed |
| M7 | 무제한을 0으로 직렬화 | over-strict | 1 failed |
| M8 | env 미설정 시 무제한 반환 | 오배포 시뮬 | 6 failed |

M6·M7이 특히 중요하다 — 가짜 collection이 **드라이버처럼 naive를 돌려주게** 만들었기 때문에 잡힌다.
그 하네스가 aware를 돌려주도록 바뀌면 함정이 되살아나므로, **하네스 자체를 단정하는 셀**을 함께 뒀다
(`test_the_fake_really_returns_naive_dates`).

원복은 전부 백업 파일과 `diff`로 바이트 동일 확인(`git checkout --` 금지 — 미커밋 슬라이스를 날린다).

### Verification

- `python3 -m pytest -q tests/test_quota_policy.py tests/test_quota_policy_mongo.py`: **26 passed**.
- 전체 backend(test-mongo ON, 베타): **1952 passed / 1 skipped / 1715 subtests**(843s).
  직전 1926/1/1715 대비 **+26 passed = 이번 신규 셀 그대로**(subtests 는 subTest 를 안 써서 무변).
  **회귀 0건.**
- `python3 -m pytest -q tests/test_docs_indexes.py`: **9 passed / 10 subtests**. `git diff --check`: clean.

### Next steps

- **8.2 사용량 원장 브리프**가 다음이다. 입력은 이 슬라이스의 **창 키 정의**(`daily_key`·`weekly_key`)와
  8.0의 `action` 리터럴이며, 결정할 것은 append-only 범위·idempotency key 출처와 수명·보존 기간·
  집계 정본이다.
- 8.3 착수 시 **P6=C의 부작용**을 다뤄야 한다: "이미 쓴 양 > 새 한도"는 정상 상태로 인정됐고, 그때
  무엇을 하는지(거부만·회수 없음)는 아직 미정이다.

---

## Hardening — Slice 8.1 독립 검증(`756bf2e`) 반영 + 8.2 착수 브리프

### Verification review

- [`verifications/2026-08-03/slice_8_1_quota_policy.md`](../../verifications/2026-08-03/slice_8_1_quota_policy.md)
  원문 확인. 판정 **합격 · Blocking 0**. 검증자가 뮤테이션 8종을 독립 재실행하고 전체 회귀
  1952/1/1715를 재현했다. 정지 유예의 안전망 근거(`main.py:1456`)도 직접 실측해 참임을 확인했다.
- 비차단 3건(H1 창 함수의 awareness 가정 · H2 `clear_pending` 미자동 · H3 뮤테이션 카운트의 모양
  의존성)만 남아 그것들을 닫았다.

### 보강 — H1 (관습을 계약으로)

- 지적: `_local`이 `astimezone`을 쓰는데 **naive가 오면 시스템 로컬로 해석**해 비-UTC 호스트에서
  경계가 조용히 어긋난다. 현재 입력 경로는 전부 aware라 live 결함은 아니지만 **그것은 관습이지
  계약이 아니었다.**
- `_require_aware`를 `daily_key`·`weekly_cycle_bounds`·`effective_limits` 입구에 넣어 naive를 거부한다.
  **저장소 경계의 `_aware`와 방향이 반대인 것은 의도적**이며 그 이유를 docstring에 적었다 — BSON은
  UTC임이 알려져 있어 재부착이 재명명이지만, **도메인 입력의 naive는 무엇인지 알 수 없다.**
- 회귀 3 cells 추가(`AwarenessContractTest`). 뮤테이션 2종 양방향 확인: 단정 제거 → 1 failed,
  "UTC만 허용"으로 과잉 교정 → 1 failed(정상 KST 입력을 깨뜨린다).

### 보강 — H2 (읽는 쪽이 지나야 하는 문)

`QuotaPolicy` docstring에 **`limits`는 유효 한도가 아니다**를 못박았다 — 발효한 예약이 문서에 남아
있을 수 있고(`clear_pending`은 선택적 정리) 원본을 직접 읽으면 **만료된 예약이 "대기 중"으로 보인다**.
읽기는 항상 `effective_limits`/`limits_for`를 지나야 한다. 8.5 관리자 조회에 대한 권고는 브리프
"후속 고려"에 넣었다.

### 보강 — H3 (기록 해석 주의)

검증자의 변형이 구현자 변형과 달라 같은 가드가 다른 카운트를 냈다(덩어리 판정 1↔7, `None`→0 1↔2).
**카운트는 가드의 세기가 아니다** — 확증되는 것은 *물었는가*이지 *몇 개가 물었는가*가 아니라는 점을
브리프에 명시했다.

### Completed work — Slice 8.2 착수 브리프

- [`plans/08-2-usage-ledger-decisions.md`](../../plans/08-2-usage-ledger-decisions.md). 결정 5개
  (L1 행 필드·L2 중복 방지 키·L3 집계 정본·L4 보존 기간·L5 관리자 조정 표현), 각각 선택지 표 + 추천.

### Issues found — 실측이 뒤집은 가정 2건 (브리프 §1의 뼈대)

- **★ 클라이언트 `request_id`는 멱등키가 아니다.** 프론트가 "이어쓰기" 클릭마다 새 uuid를 만들고
  ([`WritingPanel.tsx:284`](../../../frontend/src/writing/WritingPanel.tsx#L284)) **그 하나를
  generate·gate·revise-and-gate·accept가 함께 쓴다**(`:289`·`:316`·`:328`·`:423`). 따라서
  `(user, request_id)`로 중복을 지우면 **한 흐름의 유료 동작 4개가 1개로 접혀 8.0의 "요청 1건 = 1회"가
  조용히 깨진다.** 반대로 사용자가 다시 클릭한 재시도는 새 uuid라 잡히지도 않는다. → L2의 추천이
  **키에 `action`을 포함**하는 형태인 이유다. 8.0 B5=A의 "(user, project, 멱등키)" 문언은 키가 있고
  안정적인 경로에서만 성립한다는 점을 브리프에 명시했다.
- **★ 원장이 `project_id`를 들면 project 영구 삭제가 과금 기록을 지운다.** purge reconciler는 컬렉션을
  하드코딩하지 않고 **DB에서 `project_id` 필드를 가진 컬렉션을 발견**해 고아를 지운다
  ([`purge_reconciler.py:50`](../../../scripts/purge_reconciler.py#L50)). D8-6이 삭제 감사에
  `target_project_id`를 쓴 이유가 정확히 이것이며, 원장도 같은 함정 위에 있다 → L1 추천은 **project
  축을 아예 안 남기는** 쪽이다(필요해지면 `target_project_id`로 넓히는 문은 열려 있다).
- 규모 실측이 L3 추천의 근거다: 외부 12B `total_slots=1`이라 창당 행이 수십 건이고, 그 위에서 count는
  인덱스 스캔 몇 문서다 — 카운터 캐시는 근거 없는 복잡도다.

### Verification

- `python3 -m pytest -q tests/test_quota_policy.py tests/test_quota_policy_mongo.py`: **29 passed**(종전 26).
- 전체 backend(test-mongo ON, 베타): **1955 passed / 1 skipped / 1715 subtests**(964s).
  직전 1952/1/1715 대비 **+3 = `AwarenessContractTest` 셀 그대로**. **회귀 0건.**
- `python3 -m pytest -q tests/test_docs_indexes.py`: **9 passed / 10 subtests** — 브리프 추가로 plans
  문서 수 가드가 또 물어 94/77로 정정했다(H3 보강 가드의 두 번째 실사례).
- 브리프 상대 링크 4건 전부 해석. `git diff --check`: clean.

### Next steps

- **오너 결정 대기: L1~L5.** 결정 뒤 계약·양방향 회귀(같은 dedupe 키 재삽입 · **다른 action은 같은
  request_id라도 각각 센다** · 회원/창 격리 · 조정 행의 부호 · 창 키를 8.1에서 가져오기) → 도메인 +
  Mongo 어댑터(유니크 + 집계 인덱스) → `mongo_collections.md` §43D → 8.3 인계.

---

## Task — Slice 8.2 오너 결정 반영·브리프 확정

### User Decisions and Rationale

- **L1 = B(구현자 추천 A를 기각).** "얼마나 썼는가"로 좁히면 **오히려 통로를 하나 더 만들게 되고**,
  **"어느 프로젝트에서 얼마나 썼는가"를 완성하는 편**이 낫다. 그리고 **프로젝트가 삭제되어도 사용
  기록은 남아야 한다** — 구현자가 B의 단점으로 적었던 "삭제 뒤에도 id가 남는다"가 여기서는 **의도된
  성질**이다.
- **L2 = A** + 요구 추가: 2번 시도와 중복 시도의 구분은 당연하고, 그 위에 **실수 중복 가드**가 있어야
  한다 — 이미 생성된 것의 재생성 확인 · **5초 이내 같은 요청은 확인 필수(프로젝트별 별개)** ·
  그 확인 경로에 **locking**.
- **L3 = A**, 다만 **두 창 카운트는 백엔드 판정 축이고 사용자에게는 통합 카운트**를 보여 준다.
- **L4 = A**(TTL 없음).
- **L5 = A**: "스페셜한 건 스페셜로 관리한다 — 본 원장에 그냥 섞이는 건 말이 안 되고, 그렇다고 별도
  컬렉션은 과하다."

### Completed work

- 브리프에 **§0 오너 결정**과 하위 절 넷을 넣고 L1~L5 절 제목·추천을 확정 상태로 갱신했다.
  구현 슬라이스 절에 **확정된 행 모양 표**(kind별 필드 구성)와 **인덱스 셋 3종**을 적었다.
- plans index 상태를 `Resolved — L1=B · L2~L5=A, 구현 대기`로 갱신.

### Issues found — 결정이 연 것 / 확인이 필요한 것 (전부 브리프에 명시)

- **★ L1=B의 필드명은 반드시 `target_project_id`다.** `project_id`로 적으면 purge reconciler가 DB에서
  그 필드를 발견해 **과금 기록을 고아로 지운다** — 오너 결정("삭제돼도 남아야 한다")과 정면으로
  어긋난다. **이름 하나가 결정의 성패를 가르는 자리**이므로 회귀가 이름 자체를 단정하게 했다(구현
  슬라이스 1번).
- **★ 삭제된 프로젝트의 "이름"은 남길 수 없다.** purge tombstone은 계약상 project 이름·소유자·본문을
  보존하지 않는다(§43B). 원장이 이름을 스냅샷으로 남기면 **과금 원장이 그 삭제 계약을 우회**한다.
  그래서 원장은 id만 들고, **삭제된 프로젝트는 id 수준으로만 답해진다**("이 id에서 37회"). 이것이
  L1=B의 정확한 사정거리이며 브리프 §0.4에 명시했다.
- **전 유료 동작 9개가 project-scoped**(`/projects/{project_id}/…`)임을 실측 확인했다 — 이 축은 항상
  채워지므로 nullable 특례가 필요 없다.
- **5초 가드의 소유자를 갈랐다**: 8.2는 원장이 "이 회원이 이 동작을 이 프로젝트에서 마지막으로 언제
  했는가"에 답하게만 한다(최근성 인덱스). **무엇을 돌려주는가(상태코드·재확인 필드)는 8.3**,
  **사용자에게 묻는 UX는 8.4**다. 그리고 **L2=A의 유니크 인덱스가 곧 locking**이라 애플리케이션 락을
  따로 들이지 않는다 — 확인하는 사이 두 건이 지나가는 창이 저장소 제약으로 닫힌다.
- **L1=B와 L2의 5초 가드가 서로를 지탱한다**: "프로젝트별 별개" 판정은 원장이 프로젝트 축을 들고
  있어야 성립한다.
- **L5 해석을 명시하고 확인을 요청했다**: "본 원장에 들어가는 건 말이 안 된다"를 **같은 컬렉션에 두되
  종류를 구조적으로 갈라 둔다**(= 선택지 A의 정의)로 읽었다. 사용 행과 조정 행의 **필드 구성이 겹치지
  않게** 설계한다. 이 해석이 틀렸으면 L5만 다시 짠다.
- **통합 카운트의 함정 하나**를 §0.2에 남겼다: 실질 잔여 = `min(일, 주)`인데 숫자만 주면 "어제 20 남았는데
  오늘 5"가 설명되지 않는다 — **무엇이 구속 중인지 한 줄**을 붙이기를 권했다(문구는 8.5 이후 결정).

### Verification

- `python3 -m pytest -q tests/test_docs_indexes.py`: **9 passed / 10 subtests**. `git diff --check`: clean.
- 코드 변경 0줄(브리프·인덱스·기록만).

### Next steps

- **L5 해석 확인만 받으면** 구현 착수: 계약·양방향 회귀(이름 단정 셀 포함) → 도메인 + Mongo 어댑터
  (인덱스 3종·naive/aware 왕복) → `mongo_collections.md` §43D → 8.3 인계.

---

## Task — Slice 8.2 오너 2차 지적 반영 (L6·L7 신설 + 구현자 오류 정정)

### User Decisions and Rationale

- **프로젝트 이름·제목을 히스토리로 남긴다**(오너). §0.4가 "삭제된 프로젝트는 id로만 답해진다"로
  닫았던 것을 **계약을 바꿔서 열기로** 했다 — 이름을 보관하고 원장의 id와 **연관(join)** 시키며,
  **삭제 요청이 그 히스토리를 지우지 않는다.** 히스토리 자체의 보관 기간은 나중에 별도 정책으로
  정하고, 그 정책으로 지워진 뒤의 id는 화면에서 **"삭제된 프로젝트"** 로 표시한다. → **L6** 신설.
- **5초 가드는 프론트만으로 부족하다 — 백엔드·DB 수준에도 잠금이 필요하다**(오너). "돈이 나가는
  지점이고 프론트 잠금은 간단한 우회로도 풀린다." → **L7** 신설.

### Issues found — ★ 구현자 오류 1건 (오너 지적이 드러냈다)

- **§0.1에 "L2=A의 유니크 인덱스가 곧 locking"이라 적은 것이 틀렸다.** 그 인덱스는 **dedupe 키가 같을
  때만** 문다. 그런데 프론트는 §1.2대로 **클릭마다 새 uuid**를 만들므로, 5초 안에 두 번 누르면 키가
  달라 **유니크 인덱스를 그대로 통과한다.** 즉 종전 서술은 전송 재시도만 막고 **오너가 말한 실수
  중복은 하나도 막지 못한다.** 브리프에서 해당 문장을 취소선으로 정정하고 §0.5에 정정 사유를 적었다.
  이 오류를 그대로 뒀다면 **잠금이 있다고 믿고 구현에 들어갔을 것**이다.

### Issues found — L6이 부르는 의무 3건

- **D8-6 삭제 계약 개정이 필요하다.** 정본은 purge가 "project 이름·소유자·본문을 보존하지 않는다"고
  단정한다(§43B). L6은 그중 **이름을 예외로 만든다** — 개정 없이 구현하면 정본과 코드가 갈라진다.
- **★ purge UI 문구가 거짓이 된다.** 현재 화면은 "원고·기억·감사·색인 전체가 삭제되며 복구할 수
  없습니다"라고 말한다([`AdminConsole.tsx:276`](../../../frontend/src/admin/AdminConsole.tsx#L276)).
  이름이 남으면 **부분적으로 거짓**이며, 관리자에게 거짓 경고를 주는 것은 D8-6이 확인 UX에 들인
  공을 무너뜨린다 → **같은 슬라이스에서 함께 고쳐야 한다**(분리하면 그 사이에 거짓 문구가 배포된다).
- **삭제 기대와의 충돌을 정본에 적어 둔다.** 프로젝트 제목은 사용자가 쓴 텍스트라 내용을 드러낼 수
  있다. "지웠는데 제목은 남는다"가 **의도된 결정**임을 근거와 함께 남겨야 나중에 결함으로 오독되지
  않는다.

### Completed work

- 브리프에 **§0.5(2차 지적·오류 정정)**, **L6**(이름 이력 — 전용 컬렉션/tombstone/행 스냅샷/현행 유지),
  **L7**(5초 DB 잠금 — 만료 잠금 문서/시간 버킷/read-then-write/트랜잭션)을 추가하고 각각 추천을 달았다.
- **범위 경고 절**을 새로 넣었다: L6·L7은 부모 계획이 8.2에 배정한 범위를 넓힌다. 세 가지 길
  (가: 8.2에 전부 / 나: 8.2b 분리 / 다: L7만 8.3으로)을 제시하고 **가**를 추천했다 — 나로 나누면
  "이름은 남는데 UI는 전체 삭제라고 말하는" 중간 상태가 생긴다.
- L7 추천의 핵심을 명시했다: **TTL은 판정이 아니라 청소에만 쓴다.** Mongo TTL 삭제는 약 60초 주기라
  판정을 맡기면 **5초가 아니라 최대 1분 잠기는** 버그가 된다.

### Verification

- `python3 -m pytest -q tests/test_docs_indexes.py`: **9 passed / 10 subtests**. `git diff --check`: clean.
- 코드 변경 0줄.

### Next steps

- **오너 결정 대기: L6 · L7 · 범위(가/나/다).** 셋이 닫히면 계약·양방향 회귀부터 구현한다.

---

## Task — Slice 8.2 사용량 원장 구현 (L1=B·L2~L5=A, SoT v1.7.85)

### User Decisions and Rationale

- **범위 = 나(분리)**(오너). 중간 독립 검증 단위를 작게 유지하고, 개발 중이라 중간 상태를
  감수한다. → **8.2**(원장) → **8.2b**(L7 잠금) → **8.2c**(L6 이름 이력 + 계약 개정 + UI).
- 구현자의 반대 논거("거짓 UI 문구 구간")는 **나에서 성립하지 않아 정정**했다 — L6을 통째로
  미루므로 이름 이력·계약 개정·UI 문구가 8.2c 안에서 함께 들어간다.

### Completed work

- **[`quota/ledger.py`](../../../services/application/app/quota/ledger.py)** — `UsageEntry`·
  `AdjustmentEntry`(필드 구성이 겹치지 않는다) · 저장소 seam · fake · 서비스. 창 키는 **8.1의
  `daily_key`/`weekly_key`를 부른다**(재계산 금지).
- **[`quota/ledger_mongo.py`](../../../services/application/app/quota/ledger_mongo.py)** —
  `request_usage_ledger`, 인덱스 3종(부분 유니크 1 + 집계 2), `_aware` 재부착.
- **[`docs/mongo_collections.md`](../../mongo_collections.md) §43D** 등재. SoT **v1.7.85**,
  CHANGELOG, README SoT 표기, 브리프 구현 결과, plans index.
- **배선하지 않았다** — 소비자는 8.3이다(8.1과 같은 규칙).

### Issues found — 구현이 드러낸 것

- **★ 유니크 인덱스는 부분(partial) 인덱스여야 한다.** 조정 행에는 `action`·`dedupe_key`가 없고
  **Mongo는 없는 필드를 `null`로 색인**하므로, 전체 유니크 인덱스로 걸면 **두 번째 조정 행이
  중복 키로 거부된다.** L5("두 종류가 한 컬렉션에 산다")가 만든 함정이며 브리프 단계에서는 안
  보였다. fake collection이 부분 인덱스 규칙을 흉내 내게 만들어 회귀로 잡았다(M3이 실증).
- 사용량이 **음수가 될 수 있다**(환급 > 사용). 깎지 않기로 했다 — "한도를 넘는 보너스"는 관리자가
  만든 정당한 상태이고, 0으로 clamp하면 그 의도가 사라진다. 잔여 해석은 8.3의 몫이며 M5가
  과잉 교정을 잡는다.

### Regression guards and adversarial mutations

회귀 **29 cells**. 가장 중요한 셀 둘: **같은 `request_id`라도 `action`이 다르면 각각 센다**(8.0
계약을 지키는 자리) · **프로젝트 축이 `project_id`로 불리지 않는다**(purge가 과금 기록을 지우는
것을 막는 자리).

| # | 뮤테이션 | 결과 |
|---|---|---|
| M1 | dedupe 키에서 `action` 제거 | 3 failed |
| M2 | 필드명을 `project_id`로 개명 | **26 failed** |
| M3 | 부분 인덱스 제거(조정 행이 막힌다) | 2 failed |
| M4 | 조정 합을 사용 카운트에 안 더함 | 2 failed |
| M5 | 사용량을 0으로 clamp(과잉 교정) | 1 failed |
| M6 | 창 키를 원장이 직접 계산(8.1 위임 파기) | 1 failed |
| M7 | `_aware` 제거 | 2 failed |

원복은 백업 파일과 `diff`로 바이트 동일 확인.

### Verification

- `python3 -m pytest -q tests/test_quota_ledger.py tests/test_quota_ledger_mongo.py`:
  **29 passed / 2 subtests**.
- 전체 backend(test-mongo ON, 베타): **1984 passed / 1 skipped / 1717 subtests**(900s).
  직전 1955/1/1715 대비 **+29 passed·+2 subtests = 이번 신규 셀 그대로**. **회귀 0건.**
- `python3 -m pytest -q tests/test_docs_indexes.py`: **9 passed / 10 subtests**. `git diff --check`: clean.

### Next steps

- **8.2b(L7 — 5초 중복 가드의 DB 잠금)** 이 다음이다. 착수 시 결정할 것은 잠금 컬렉션의 형태와
  차지 연산이며, 추천은 만료를 가진 잠금 문서 + 원자적 차지(**TTL은 판정이 아니라 청소에만** —
  Mongo TTL은 약 60초 주기라 판정을 맡기면 5초가 아니라 최대 1분 잠긴다). 8.3 시행이 곧바로 소비한다.
- 그 뒤 **8.2c(L6 — 프로젝트 이름 이력 + D8-6 계약 개정 + purge UI 문구 수정)**.

---

## Hardening — Slice 8.2 독립 검증(`afc9df0`) 반영

### Verification review

- [`verifications/2026-08-03/slice_8_2_usage_ledger.md`](../../verifications/2026-08-03/slice_8_2_usage_ledger.md)
  원문 확인. 판정 **합격 · Blocking 0**. 검증자가 두 핵심 주장을 **코드 밖까지 가서** 입증했다:
  `purge_reconciler.py`가 `project_id` 필드로 컬렉션을 **발견**한다는 것(하드코딩 목록이 아님)과,
  프론트 `DraftEditor.tsx:226`이 intent마다 uuid 하나를 만들어 **한 흐름의 여러 동작이 공유**한다는
  것(`DraftEditor.test.tsx:348-349`가 `calls[3]`·`calls[4]`의 동일 `intent-1`을 단정).
- 뮤테이션 7종 카운트가 **한 건도 어긋나지 않았다**(8.1 검증의 H3 같은 모양 의존성이 이번엔 없었다).

### 보강 — H1 (전이적 보호를 경계에서 잠갔다)

`member_created_at`·clock의 naive 거부는 8.1의 `_require_aware`에서 **전이적으로** 온다(원장이 창
키를 직접 계산하지 않기 때문). 검증자 판단대로 지금 안전하지만 **잠겨 있지는 않았다** — 8.1의
단정이 사라지면 원장 스위트의 어떤 셀도 실패하지 않는다. `AwarenessInheritanceTest` 3 cells를
더해 경계에서 다시 단정했다(over-strict 방향도 포함: 정상 aware 경로가 막히면 실패).

### 보강 — H2 (표본 한 건이면 컬렉션 전체가 sweep 대상이 된다)

- 지적: 파기 reconciler의 발견은 `find_one({project_id: {$exists: true}})`라 **표본**이다. 원장 문서
  **단 하나**에라도 `project_id`가 섞이면 그 컬렉션이 발견돼 과금 기록이 지워진다.
- 종전 셀은 **사용 행의 이름 부재만** 봤다. 두 가지를 고쳤다: ① 사용·조정 **두 종류를 모두** 보게
  하고 ② **저장 문서의 키 집합 전체를 고정**했다 — 이름 부재만으로는 "다른 새 필드"를 못 잡지만,
  키 집합을 못박으면 필드를 더하려면 이 셀을 함께 고쳐야 한다.
- 뮤테이션 2종: 사용 행에 `project_id` 추가 → **2 failed** · **조정 행에만** 추가 → **2 failed**
  (표본 한 건이면 충분하다는 지적을 그대로 재현한 변형이다).

### Regression guards and adversarial mutations

| # | 뮤테이션 | 결과 |
|---|---|---|
| H2-M1 | 사용 행 문서에 `project_id` 추가 | 2 failed |
| H2-M2 | **조정 행에만** `project_id` 추가 | 2 failed |
| H1-M | 8.1의 awareness 단정 제거(원장 경계가 잡는가) | 2 failed |

원복은 백업과 `diff`로 바이트 동일 확인.

### Verification

- `python3 -m pytest -q tests/test_quota_ledger.py tests/test_quota_ledger_mongo.py`:
  **33 passed / 4 subtests**(종전 29/2).
- 전체 backend(test-mongo ON, 베타): **1988 passed / 1 skipped / 1719 subtests**(882s).
  직전 1984/1/1717 대비 **+4 passed·+2 subtests = 이번 보강 셀 그대로**. **회귀 0건.**
- `git diff --check`: clean.

### Next steps

- 변함없이 **8.2b(L7 — 5초 중복 가드의 DB 잠금)**. 브리프부터 쓰고, 핵심 함정(TTL≠판정)과 필수 셀
  둘은 HANDOFF에 이미 있다.

---

## Task — Slice 8.2b 착수 브리프 (L7 — 실수 중복 요청의 DB 잠금)

### Goals

- 오너 요구("5초 이내 2번 요청은 확인 필수 + DB 수준 locking")를 저장 계약 결정으로 옮긴다.
- 성공 기준: ① 수치·선례가 전부 실측 ② 선택지 사전 필터링 없음 ③ 코드 0줄 ④ 인덱스 가드 통과.

### Issues found — ★ 실측이 요구의 형태를 바꿨다

- **이 제품의 동기 요청은 5초보다 훨씬 오래 걸린다.** 2026-07-15 벤치마크에서 도출된 생성 속도가
  **약 45 tok/s**이고 출력 프리셋이 short 1024 / medium 2048 / long 4096이므로,
  **동기 short 생성 하나가 약 23초**다(medium 45초·long 91초는 **너무 느려서 202 비동기로 뺀** 바로
  그 이유다). → **고정 5초 창은 "결과가 나오기 전 재클릭"을 거의 못 막는다**: 10초 뒤 재클릭이면
  창은 지났고 첫 요청은 아직 진행 중이라 **두 번 과금**된다. 오너가 막고 싶어 한 실수가 정확히
  그 형태인데 5초라는 숫자로는 안 잡힌다. → **G1(잠금의 수명)** 을 이 슬라이스의 핵심 결정으로 세우고
  **C(진행 중 유지 + 최소 5초)** 를 추천했다.
- **TTL 인덱스는 이 저장소에 사용처가 0곳**이다. 처음 도입하는 자리라 성질을 브리프에 못박았다 —
  Mongo TTL 삭제는 **백그라운드 모니터가 약 60초 주기**라, 존재 여부로 판정하면 **5초가 아니라 최대
  1분 잠긴다**. TTL은 청소용이고 판정은 `expires_at` 비교다. **fake에는 TTL 주기가 없어 테스트로는
  안 보이고 운영에서만 보이는** 종류의 결함이다.
- **원자적 차지는 새 패턴이 아니다.** 생성 job([`generation_job_mongo.py:79`](../../../services/application/app/writing/generation_job_mongo.py#L79))과
  색인 outbox가 이미 `find_one_and_update` 한 번으로 차지하고 **만료된 lease를 같은 연산으로
  회수**한다. 잠금은 그 모양의 재사용이다.
- **프론트는 이미 `busy`로 버튼을 막는다.** 오너 지적의 핵심은 그것이 **화면의 관례**라는 것이며
  (devtools·스크립트·다른 클라이언트는 통과), 이 슬라이스가 그 관례를 **서버 제약**으로 바꾼다.

### Completed work

- [`plans/08-2b-duplicate-request-lock-decisions.md`](../../plans/08-2b-duplicate-request-lock-decisions.md).
  결정 5개, 각각 선택지 표 + 추천:
  - **G1 잠금의 수명** — A) 고정 5초 / B) 진행 중 유지+해제 / **C) 둘 다(추천)** / D) 사용자당 동시 1건.
  - **G2 잠금 키의 축** — **A) `(user, action, target_project_id)`(추천)** / B) 프로젝트 무시 /
    C) 동작 무시 / D) + 본문 해시. C는 **정상 연쇄(generate → gate)를 깬다**.
  - **G3 원자적 차지의 형태** — **A) `find_one_and_update` upsert(추천)** / B) insert + TTL 의존 /
    C) read-then-write / D) 트랜잭션.
  - **G4 확인 통과의 저장 의미론** — **A) 강제 재차지(추천)** / B) `confirmed` 플래그 / C) 삭제 후 재차지
    (C는 **삭제와 차지 사이에 창이 열린다**).
  - **G5 실패가 돌려주는 것** — **A) 남은 시간 + 진행 중 여부(추천)** / B) boolean / C) 잠금 문서 전체.
- 후속 고려에 **"5초와 lease는 별개 값"**(최소 창은 제품 정책, lease는 가장 긴 동기 요청 91초·gateway
  120초보다 길어야 한다)과, `analysis_*`처럼 **클라이언트 키가 없는 동작도 이 잠금은 덮는다**는 구조를
  적었다 — dedupe가 못 덮는 자리를 잠금이 덮는다.
- 범위 밖: HTTP 계약(8.3) · 묻는 UX(8.4) · **"이미 생성된 것 재생성 확인"**(시간이 아니라 상태 기반) ·
  이름 이력(8.2c).
- [`plans/README.md`](../../plans/README.md) 등재(문서 수 가드가 또 물어 95/78로 정정 — 세 번째 실사례).

### Verification

- `python3 -m pytest -q tests/test_docs_indexes.py`: **9 passed / 10 subtests**. `git diff --check`: clean.
- 브리프 상대 링크 3건 전부 해석. 코드 변경 0줄.

### Next steps

- **오너 결정 대기: G1~G5.** 특히 **G1**이 핵심이다 — 5초를 그대로 둘지(A), 진행 중을 덮을지(B),
  둘 다 할지(C). 결정 뒤 계약·양방향 회귀(동시성·만료 재차지·두 구간 경계·정상 연쇄 비차단·
  강제 재차지 뒤 재차단·lease > 최소 창)부터 구현한다.

---

## Task — Slice 8.2b 브리프 보강: 에러 통로·상태코드 (G6 신설)

### User Decisions and Rationale

- 오너 질문: **"TTL 주기 때문에 제너레이팅이 안 될 경우 이용자에게 에러 노티를 보여줘야 하는데,
  그것에 대한 에러 넘버링과 통로가 있는지도 고려했어?"** → 초판은 **절반만** 고려했다. G5가 저장
  계층의 반환값을 정했지만 **사용자까지 옮기는 통로는 8.3으로 미뤘고**, 에러 번호 체계가 이
  저장소에 있는지는 확인조차 하지 않았다.

### Issues found — 실측

- **★ 에러 넘버링은 이 저장소에 없다.** 앱 전체에 `error_code`류 필드가 **0곳**이고, 계약(H3)이
  본문을 균일 `{"detail": <string>}`로 못박으면서 **`detail` 문자열로 분기하는 것을 금지**한다
  (상태코드=기계용·`detail`=사람용). 즉 **기계 판독 축은 HTTP 상태코드 하나뿐**이다.
- **통로 자체는 있다.** 프론트에 `ApiError { status, detail }`이 있고 화면이 **실제로 `status`로
  분기**한다(401·409·502·503 실측). `detail`은 그대로 표시한다 — **금지된 것은 분기이지 표시가
  아니다.** 따라서 새 번호 체계를 만들 필요가 없다.
- **★ 상태코드 선택지가 실측으로 좁혀졌다.** 유료 9경로가 쓰는 코드를 전수로 재 보니
  **`409`는 `writing_accept`(stale base)와 `analysis_extract`(job 상태 전이)에서 이미 다른 뜻**이라
  충돌하고, **`429`는 앱 전체에서 사용처가 0곳**이며 의미도 정확하다("Too Many Requests").
- **오너 우려의 절반은 설계로 이미 해소된다**: G3=A(판정은 `expires_at` 비교)이면 **TTL 지연 자체는
  생성을 막지 않는다**. 문서가 1분 더 남아 있어도 만료된 잠금은 그 자리에서 다시 차지된다.
- **그러나 크래시는 실제로 막는다.** 요청이 진행 중 죽으면 잠금이 **lease 만료까지**(long 91초·
  gateway 120초보다 길어야 하므로 **최대 2분가량**) 살아 있다. 이것이 사용자에게 노출되는 유일한
  "생성이 안 되는" 경우이며, **탈출구는 G4=A(강제 재차지)** 다 — 확인으로 즉시 뚫는다. **초판이
  G4를 UX 편의로만 적었는데 실은 크래시 복구 경로이기도 하다**는 것을 §1.6에 추가했다.

### Completed work

- 브리프에 **§1.5(에러 통로 실측)**, **§1.6(TTL·lease가 실제로 막는 경우)**, **G6(상태코드와 이유
  전달)** 을 추가했다. G6 선택지: **A) `429` 하나 + `detail` 문구(추천)** / B) 두 상태코드 /
  C) H3 개정해 기계 판독 코드 필드 도입.
- **추천 A의 근거**: 프론트가 분기해야 하는 것은 "확인 후 재요청을 제안할까" **하나**이고 그에는 코드
  하나면 충분하다. 두 이유의 차이는 **사람이 읽는 문장**이지 기계 동작이 아니다. C는 H3가 페이즈
  전체를 들여 만든 균일 본문을 분기 하나를 위해 깨는 것이라 대가가 맞지 않는다(필요해지면 그때
  여는 문은 닫히지 않는다).
- **따라오는 의무를 명시**했다: 429를 쓰면 그 경로들의 `responses=`에 **선언**하고 tier 전수 가드에
  등재해야 한다(선언 없는 상태코드는 이 저장소에서 계약 위반). 그 시행은 8.3이고, **코드 선택만**
  여기서 확정해 8.3이 다시 열지 않게 했다.
- 범위 밖 절에서 "상태코드는 8.3"을 **"시행은 8.3, 선택은 G6"** 으로 정정했다.

### Verification

- `python3 -m pytest -q tests/test_docs_indexes.py`: **9 passed / 10 subtests**. `git diff --check`: clean.
- 코드 변경 0줄.

### Next steps

- **오너 결정 대기: G1~G6.** G1(잠금 수명)과 G6(상태코드)이 핵심이다.

---

## Task — Slice 8.2b 브리프 확정 (G1=C · G2~G6=A)

### User Decisions and Rationale

- **G1 = C**(진행 중 유지 + 최소 5초). 구현자 추천대로이며, **실측이 요구의 형태를 바꾼 것**을 오너가
  받아들인 결과다 — 동기 생성이 약 23초라 고정 5초 창은 "결과가 나오기 전 재클릭"을 못 막는다.
- **G6 = A**(`429` 하나 + `detail` 문구). **H3 균일 본문 계약을 개정하지 않는다.**
- **G2·G3·G4·G5 = A**(추천 그대로).

### Completed work

- 브리프에 **§0 오너 결정**과 하위 절 셋을 넣고 G1~G6 절 제목을 확정 상태로 갱신했다.
- **§0.1 — 확정된 잠금 문서의 모양.** G1=C를 고르면 상태가 둘(진행 중 / 냉각)인데, **필드 하나로
  갈린다**는 것을 못박았다:
  - `_id` = `"{user}:{action}:{project}"`(G2의 키가 곧 문서 id라 **추가 인덱스 불필요**)
  - `claimed_at` · `expires_at`(**판정의 유일한 축**) · `released_at`(`None`이면 진행 중)
  - 연산 셋 — 차지(`expires_at = now + lease`) · 해제(`expires_at = max(now, claimed_at + 최소 창)`,
    이것이 G1=C의 "둘 다"다) · 강제 재차지(G4)
  - **막힌 이유가 `released_at`에서 파생**되므로 G5가 저장 필드를 늘리지 않고 성립한다.
- **§0.2 — 두 상수는 다른 것이다.** 최소 창 5초는 **제품 정책**, lease(잠정 180초)는 **기술 한계**
  (gateway timeout 120초보다 커야 한다). 합치면 둘 다 틀린다.
- **§0.3 — 알려진 한계를 정직하게 남겼다.** lease가 만료됐는데 원래 요청이 살아 있으면 중복이 샌다.
  실측으로 확인한 것: `WRITING_LOOP_MAX_WALL_CLOCK_MS`가 **기본 미설정(무제한)**이라 동기 경로의
  이론적 상한을 코드로 증명할 수 없다. 그래서 **잠금은 최선 노력 통제이지 절대 보장이 아니다**라고
  적었고, 절대 보장이 필요하면 **루프에 wall-clock 상한을 걸어 최대 시간을 증명 가능하게 만든 뒤
  lease를 그보다 크게** 잡는 것이 순서임을 남겼다.

### Verification

- `python3 -m pytest -q tests/test_docs_indexes.py`: **9 passed / 10 subtests**. `git diff --check`: clean.
- 코드 변경 0줄.

### Next steps

- **8.2b 구현**: 계약·양방향 회귀(동시성 · 만료 재차지 · 진행 중/냉각 두 구간의 경계 직전·직후 ·
  정상 연쇄 비차단 · 강제 재차지 뒤 재차단 · lease > 최소 창 · 이유가 `released_at`에서 파생) →
  도메인 + Mongo 어댑터(청소용 TTL) → `mongo_collections.md` §43E → 8.3 인계.

---

## Closeout — 2026-08-03 작업 종료

### 오늘 한 것 (커밋 12건, `05286a6` → `dd2f729`)

| 트랙 | 결과 |
|---|---|
| 머신 전환 | 알파 → **베타** 확인·재측정(GPU·HEAD·compose·이미지·외부 LLM `/props`) |
| **Slice 8.0** | billable request 경계 **B1~B6=A** 확정·시행·**독립 검증 합격** + H1~H4 보강. SoT v1.7.83 |
| **Slice 8.1** | quota 정책 저장 계약 **P1~P8** 확정·구현·**독립 검증 합격** + H1~H3 보강. SoT v1.7.84 |
| **Slice 8.2** | 사용량 원장 **L1=B·L2~L5=A** 확정·구현·**독립 검증 합격** + H1·H2 보강. SoT v1.7.85 |
| **Slice 8.2b** | 중복 요청 DB 잠금 **G1=C·G2~G6=A** 확정. **브리프까지, 구현은 다음 작업자** |
| 부수 | `docs/plans` 문서 수 주장 4곳·검증 "N일치"를 **가드에 편입**(H3 보강, 오늘 세 번 물었다) |

- 회귀 기준선 **1911/4/1625(알파) → 1988/1/1719(베타)**. 증가분은 전부 신규 셀로 설명되고 **회귀 0건**.
- 독립 검증 **3건 전부 합격·Blocking 0**, 비차단 지적 **9건 전부 폐쇄**.

### 다음 작업자가 바로 이어갈 것

**8.2b 구현**이 다음 한 걸음이다. 결정이 전부 닫혀 있고 **잠금 문서의 필드·연산까지 브리프 §0.1에
확정**돼 있어 브리프를 읽고 곧바로 회귀부터 쓰면 된다. 회귀에 넣을 셀 목록은 HANDOFF Next Tasks 1에
그대로 있다.

**반드시 알고 시작할 것 셋**(전부 HANDOFF에 있다):
1. **TTL은 청소용, 판정은 `expires_at` 비교** — 존재 여부로 판정하면 Mongo TTL 주기(~60초) 때문에
   5초가 최대 1분이 되고, **fake에는 TTL 주기가 없어 테스트로는 안 보인다**.
2. **최소 창(5초)과 lease(잠정 180초)는 다른 상수다** — 합치면 둘 다 틀린다.
3. **알려진 한계를 없앤 척하지 말 것** — lease 만료 시 원래 요청이 살아 있으면 중복이 샌다
   (브리프 §0.3). 최선 노력 통제이지 절대 보장이 아니다.

### 종료 후 추가 — 오너 질문이 드러낸 설계 공백 (8.2b 브리프 보강)

- **오너 질문**: "사용자가 **의도적으로** 중복 생성하려 하면? 같은 내용의 여러 안을 받아보고 싶어서
  누른 것일 수도 있잖아."
- **답 자체는 설계에 있었다**: G4=A(강제 재차지)가 그 통로이고, 두 번째 생성은 사용량 1회를 더
  쓴다(8.0 B1=A). 잠금의 목적은 "두 번 못 하게"가 아니라 **"두 번인 줄 모르고 두 번 하지 않게"** 다.
- **★ 그러나 시나리오를 끝까지 따라가니 공백이 나왔다.** ① A가 차지하고 생성 시작(약 23초)
  ② 사용자가 확인 → B가 **강제 재차지**(잠금은 B의 것) ③ **먼저 시작한 A가 완료되며 `해제`를 부른다**
  → 소유권 검사가 없으면 **B의 잠금을 푼다** ④ B가 20초 남았는데 보호가 사라진다.
  **G4(의도적 중복 허용)를 고른 순간 `해제`에 소유권 검사가 필수**가 된다 — 분산 잠금의 고전적
  fencing 문제이며, 질문이 없었으면 구현 단계에서야(혹은 운영에서야) 나왔을 자리다.
- **보강**: 잠금 문서에 `holder`(차지 토큰)를 더하고, 차지가 그것을 돌려주며 **해제는 토큰이 일치할
  때만** 동작하게 §0.1·G4를 고쳤다. 회귀에 **"먼저 시작한 요청이 남의 잠금을 해제하지 못한다"**
  (+ over-strict 짝 "자기 토큰이면 정상 해제")를 넣었다.
- **확인 문구의 성격도 못박았다**(방향만 — 문구는 8.4): 정당한 사용자를 꾸짖으면 안 된다.
  ✗"중복 요청입니다" / ○"**다른 안을 하나 더 만들까요? 사용량 1회가 추가됩니다**".
- **근본 해결은 별건**: 지금 "2안 받기"의 유일한 방법이 같은 버튼 재클릭이라 UI에서 실수와 의도가
  구분되지 않는다. **"다른 안 생성" 버튼**이 있으면 확인 대화 자체가 불필요해진다 — 새 제품 기능이라
  Phase 8 범위 밖이고 8.4가 프론트를 만질 때 후보다.

### 머신 상태 (그대로 두고 종료)

- 베타. `frontend`(healthy)·`worker`·`generation_worker`만 Up. test-mongo는 **내렸다**.
- 이미지는 여전히 코드보다 뒤처져 있다(application 07-29 등) — **화면 확인이 필요한 작업(8.2c·8.4)에
  들어가기 전 재빌드**가 선행돼야 한다.
- 작업 트리 clean, push 안 함.

---

## Task — Slice 8.2b 중복 요청 DB 잠금 구현 (G1=C·G2~G6=A, SoT v1.7.86)

브리프 [`plans/08-2b-duplicate-request-lock-decisions.md`](../../plans/08-2b-duplicate-request-lock-decisions.md)가
결정을 전부 닫아 둔 상태에서 이어받았다. 새 오너 결정 없음 — **결정 반영 구현**이다.

### Goals

1. 계약을 **양방향 회귀로 먼저** 잠근다(브리프 §"결정 뒤 구현 슬라이스" 1의 셀 목록) → verify: 새 회귀가
   구현 전에 실패하고 구현 뒤 통과한다.
2. 도메인 + Mongo 어댑터 → verify: 뮤테이션으로 각 셀이 무는지 실측한다.
3. `mongo_collections.md` §43E · 정본 v1.7.86 → verify: 문서 인덱스 가드 통과.
4. 전체 회귀 무회귀 → verify: 기준선 대비 증가분이 전부 신규 셀로 설명된다.

### Completed work

| 산출물 | 내용 |
|---|---|
| [`quota/lock.py`](../../../services/application/app/quota/lock.py) | 잠금 도메인 — 세 연산(차지·해제·강제 재차지), 두 구간(진행 중·냉각), 두 상수(최소 창·lease), in-memory 저장소 |
| [`quota/lock_mongo.py`](../../../services/application/app/quota/lock_mongo.py) | `request_locks` 어댑터 — `find_one_and_update` 한 번으로 차지, 청소용 TTL 인덱스 하나 |
| [`tests/test_quota_lock.py`](../../../tests/test_quota_lock.py) | 도메인 회귀 **40 cells**(+4 subtests) |
| [`tests/test_quota_lock_mongo.py`](../../../tests/test_quota_lock_mongo.py) | 어댑터 회귀 **21 cells** — 그중 4는 **어댑터 위에서 서비스를 구동**해 두 저장소가 갈라지는 것을 막는다 |
| `docs/mongo_collections.md` §43E · SoT v1.7.86 · `plans/README.md` · README 숫자 | 문서 |

**8.3이 소비할 표면**: `RequestLockService.claim(...) -> LockGranted | LockBlocked` ·
`force_claim(...) -> LockGranted` · `release(..., holder=...) -> bool`. 실패는
`retry_after_seconds`(올림, 최소 1)와 `in_flight`를 들고 온다. **`create_app` 배선은 하지 않았다** —
소비자가 8.3이라 지금 조립하면 쓰지 않는 배선이 생긴다(8.1·8.2와 같은 판단).

### Issues found — 구현이 드러낸 것

- **★ `holder`가 없으면 fencing 회귀를 쓸 수조차 없다.** 브리프 §0.4가 이미 잡아 둔 자리지만, 구현
  순서상 **차지가 토큰을 돌려주지 않으면 "먼저 시작한 요청"을 테스트가 지목할 방법이 없다**. 토큰은
  fencing의 수단이자 **회귀의 언어**다.
- **`released_at`은 재차지에서 반드시 지워져야 한다.** 만료된 잠금을 다시 차지할 때 옛 `released_at`이
  남으면, 지금 **생성 중인** 요청이 8.3에게 "방금 요청함(냉각 중)"으로 보고된다 — 화면이 "N초 뒤 다시
  시도하세요"라고 말하는데 실제로는 23초짜리 생성이 돌고 있는 상태다. 브리프에 없던 항목이라
  `StoredShapeTest`에 셀로 세웠다.
- **남은 시간은 올림해야 한다.** 0.5초 남은 상태에서 내림하면 "0초 뒤 다시"가 되고, 그 재시도는 다시
  막힌다. 하한 1초를 둔다.
- **해제의 읽기-쓰기 사이는 안전하다** — `claimed_at`은 그 holder에게 불변이고 소유권은 **갱신 필터가
  다시 확인**하므로, 그 사이 강제 재차지가 일어나면 아무 문서도 안 맞는다. 파이프라인 갱신($max)으로
  한 연산으로 줄일 수 있지만 fake가 파이프라인을 해석해야 해 **회귀의 값이 떨어진다** — 안 했다.
- **차지의 "막은 문서가 곧바로 사라지는 경우"는 사실상 닫힌 경로다**(TTL은 **만료된** 문서만 지우는데,
  `DuplicateKeyError`가 났다는 것은 그 순간 잠금이 살아 있었다는 뜻이다). 그래도 도달하면 "잠금이 없다"가
  사실이므로 **차지한 것으로 본다** — 여기서 터지면 8.3이 이유 없이 요청을 막는다. 셀로 고정했다.

### Regression guards and adversarial mutations

**뮤테이션 12종 전부 재실패**(원복은 `git checkout -- services/application/app/quota/`, 슬라이스는
그 전에 커밋해 두었다 — 미커밋 상태에서 그 명령을 쓰면 슬라이스가 통째로 날아간다).

| # | 변형 | 재실패 |
|---|---|---|
| M1 | 판정을 **존재 여부**로(`expires_at` 비교 제거) — TTL 함정 그 자체 | 7 cells |
| M2 | 해제에서 **소유권 검사 제거**(도메인+어댑터 둘 다) | 5 cells |
| M3 | Mongo 차지를 **read-then-write**로 | 2 cells |
| M4 | 냉각 기준을 **해제 시각**으로(차지 시각이 아니라) | 9 cells |
| M5 | 해제가 **냉각을 안 남긴다**(G1=B로 후퇴) | 7 cells |
| M6 | 확인이 잠금을 **옮기지 않고 지운다**(G4=C) | 4 cells |
| M7 | 키 축에서 **`action` 제거** | 2 cells |
| M8 | **두 상수를 하나로** 합친다(+ 생성자 검사 무력화) | 4 cells |
| M9 | `in_flight`를 늘 `True`로(이유 파생 손실) | 2 cells |
| M10 | 재차지가 **`released_at`을 잔류**시킨다 | 1 cell |
| M11 | 남은 시간에서 **올림·하한 제거** | 1 cell |
| M12 | TTL 인덱스에서 `expireAfterSeconds` 제거 | 1 cell |

**over-strict 짝을 함께 둔 자리 셋**: 경계 직후 통과(`..._right_after_the_minimum_window_ends`) ·
자기 토큰이면 정상 해제(`test_the_owner_releases_normally`) · 오래 걸린 요청은 냉각 없이 곧바로 풀림
(`..._unlocks_immediately`). M5·M2의 과잉 교정이 이 셋에 걸린다.

**어댑터 위 서비스 구동 4 cells**를 따로 둔 이유: 계약은 in-memory로 잠기는데 두 저장소가 갈라지면
**유닛은 전부 green인데 배포만 다르게 동작한다**. 구간 둘·강제 재차지·fencing을 어댑터 위에서 다시 돌린다.

### Verification

- `python3 -m pytest -q tests/test_quota_lock.py tests/test_quota_lock_mongo.py`:
  **61 passed / 4 subtests**.
- 전체 backend(test-mongo ON, 베타): **2046 passed / 4 skipped / 1723 subtests**(116s).
  직전 기준선 **1988/1/1719** 대비 **+58 passed · +3 skipped · +4 subtests**이며 **합계 +61 = 이번 신규
  셀 그대로**다. **회귀 0건.** skip 3건 증가는 내 변경과 무관하다 — `elasticsearch` 파이썬 패키지가
  이 셸의 인터프리터에 없어 `test_context_search_memory_lexical_retrieval.py`의 3 cells가 **자기
  skip 가드**로 빠진 것이다(`-rs`로 사유 확인). 남은 1건은 늘 skip되는 live Chroma 셀.
- `python3 -m pytest -q tests/test_docs_indexes.py`: 9 passed / 10 subtests(문서 인덱스·링크·숫자 주장).
- `git diff --check`: clean.

### Next steps

- **8.3(시행)**이 다음이다. 이 슬라이스가 넘기는 것: 차지 실패의 두 이유를 **`429` 하나 + `detail`
  문구**로 옮기고(브리프 G6, H3 개정 없음), 유료 9경로의 `responses=`에 429를 선언하며 **tier 전수
  가드에 등재**한다. 확인 통로는 `force_claim`이고, **문구는 8.4**이되 방향은 브리프 §0.4에 못박혀 있다
  (정당한 사용자를 꾸짖지 않는다).
- 조립 시 주의: 잠금은 **차지 → 요청 처리 → 해제**가 한 요청 안에서 닫혀야 한다. 비동기 생성(202)은
  **워커가 아니라 요청 경로가** 차지·해제의 주인이다 — 워커까지 잠금을 끌고 가면 lease와 job 수명이
  서로 다른 두 시계가 된다.
- **8.2c**(L6 이름 이력 + D8-6 삭제 계약 개정 + purge UI 문구)는 여전히 미착수.
