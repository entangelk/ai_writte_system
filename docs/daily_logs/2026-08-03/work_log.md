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
