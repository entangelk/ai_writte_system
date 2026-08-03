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

- **오너 결정 대기: B1~B6.** 결정 뒤 순서는 브리프 "결정 뒤 구현 슬라이스"대로 ① 분류 확정 →
  ② 전수 가드 테스트 먼저 → ③ 기록 → ④ 8.1 정책 브리프로 인계다.
- 화면 육안 확인 2건(HANDOFF Next Tasks 2번)은 이미지 재빌드가 선행돼야 한다. 이번 작업은 스택을
  올리지 않았으므로 손대지 않았다.
