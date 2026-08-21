# 2026-08-21 작업 로그 (베타)

> **머신은 베타다.** 키 조달은 알파에서 하기로 오너가 정했으므로, 오늘 범위에서
> **외부 API 키가 필요한 것은 전부 열지 않는다**(리랭커 품질 판정 · 임베딩 배치 실측).

## Goals

- 인계가 권한 dogfood 는 **키가 선행**이라 오늘 열지 않는다. 대신 §Owner Decisions Needed 에서
  **키 없이 닫을 수 있는 항목**을 처리한다.
- **H2(API 문서의 제품명 잔재)** 를 오너 지시대로 *설명 → 결정 → 구현* 순서로 닫는다.
- `92b9b24` 독립 검증은 **다른 검증자에게 넘긴다**(오너 지시) — 직접 검증하지 않는다.
- **(오후 추가) 그 재검이 합격과 함께 남긴 Hardening 3건을 오너 지시로 닫는다**(Task 4).

## Completed work

### Task 1 — H2: FastAPI `title=` 세 자리를 제품명으로 통일

**착수 전 설명이 계약이었다.** HANDOFF §Owner Decisions Needed 가 *"착수 전에 오너에게 자세히
설명하고 시작할 것(오너 지시 2026-08-11)"* 을 걸어 두었고, 그 이유도 함께 적혀 있었다 — 오너가
*"무슨 내용인지 모른다"* 고 명시한 항목이다. 그래서 **무엇인가 · 어디서 보이는가 · 왜 10.0 에서
안 했나 · 고치면 무엇이 따라오나** 넷을 먼저 풀어 설명하고 선택지를 냈다.

**설명하면서 인계 문서의 사실 둘을 실측으로 갱신했다.**

| 인계가 적던 것 | 오늘 실측 | 조치 |
|---|---|---|
| `application/main.py:1581` | 실제 **1611** (파일이 자라며 밀렸다) | 아래 §Issues |
| `schema.d.ts` 에 이 문자열 0건(2026-08-11 실측) | **여전히 0건** — `npm run gen:api` 재생성해도 **diff 0** | 유지 |

- **바뀐 것 세 줄** — 전부 `FastAPI(title=…)` 인자다.
  - [`services/application/app/main.py:1611`](../../../services/application/app/main.py#L1611) → `"에-라잇 Application"`
  - [`services/embedding/app/main.py:76`](../../../services/embedding/app/main.py#L76) → `"에-라잇 Embedding Service"`
  - [`services/llm_gateway/app/main.py:127`](../../../services/llm_gateway/app/main.py#L127) → `"에-라잇 LLM Gateway"`
- **효과** — `/docs`·`/redoc` 상단과 OpenAPI `info.title` 이 제품명을 말한다. 실측:
  `python3 scripts/dump_openapi.py` → `{'title': '에-라잇 Application', 'version': '0.1.0'}`.
- **프론트는 안 흔들렸다** — `npm run gen:api` 재실행 후 `git status` 에
  [`frontend/src/api/schema.d.ts`](../../../frontend/src/api/schema.d.ts) 가 **안 나타난다**
  (openapi-typescript 가 `info.title` 을 타입으로 옮기지 않는다). 중간 산출물
  `frontend/openapi.json` 은 gitignore 대상이라 역시 무영향.

### Task 2 — 그 세 줄이 살아남은 이유를 닫는다: 백엔드 스윕 가드

**세 자리를 고치는 것만으로는 같은 일이 다시 난다.** 프론트에는
[`frontend/src/productName.test.ts`](../../../frontend/src/productName.test.ts) 스윕이 있어
옛 이름의 재유입을 막는데 **백엔드에는 짝이 없었고**, 그래서 이 셋이 10.0 이후 열 달을 green 인
채로 살아남았다. 프론트에서 `<title>` 이 그랬던 것과 **같은 병**(렌더/행위 테스트의 사정거리 밖)
이므로 처방도 같게 했다 — DOM 이 아니라 **앱 객체와 파일을 읽는다**.

- 신규 [`tests/test_product_name.py`](../../../tests/test_product_name.py) · 3셀(subtest 3).
  - `test_every_service_titles_its_api_docs_with_the_product_name` — 세 서비스의 앱을 실제로 조립해
    `app.title` 을 본다(subtest 3). 소스 문자열 grep 이 아니라 **OpenAPI 에 실제로 나가는 값**이다.
  - `test_the_retired_working_title_survives_in_no_backend_source` — 완전성. 네 번째 자리가 생기면 문다.
  - `test_the_rename_does_not_reach_the_database_identifier` — **over-strict**. 아래 참조.
- **스캔 범위를 `services`·`scripts` 로 하드코딩하지 않았다.** 저장소 전체의 `.py` 와
  `docker-compose*` 에서 `tests`(부재를 단정하려면 그 문자열을 적어야 한다 — 이 파일 자신이 그
  예다) · `docs`(이력 기록이라 옛 이름이 **남아 있는 것이 맞다**) · `frontend`(자기 스윕이 있다) ·
  `node_modules`·`__pycache__`·`.git` 을 뺀다. 2026-08-20 리랭커 검증이 비차단으로 지적한
  *"가드 스캔 범위 하드코딩(세 번째 파일 계열)"* 과 같은 모양을 만들지 않기 위해서다.
- **★ over-strict 셀이 겨누는 것은 가상의 위험이 아니다.** `ai_writing_system` 은 표시명이 아니라
  **Mongo DB 이름**이고(`core_sot/mongo_repository.py:50` · `scripts/*` 다수 · `docker-compose.yml`),
  이름 통일을 식별자까지 밀면 앱이 **조용히 빈 DB 를 가리킨다** — 이 저장소가 이미 밟은 함정이다
  (`ai_writing` 이 0건을 냈다). 그래서 대소문자·공백을 정확히 구분하는 문자열
  (`"AI Writing System"`)만 금지하고, 식별자는 셀로 **못 바꾸게** 잠갔다.

### Task 3 — HANDOFF 자가 검수 (트리거를 밟았다)

인계 헤더가 *"다음 사람이 트리거를 밟는다 — `함정` · `Active Decisions` · `완료 슬라이스`
세 절은 **08-14 이후 아무도 안 봤다**"* 라고 지목해 둔 상태였고(파일은 **466줄**, 트리거는
~200줄마다), 오늘 그 셋을 열었다.

- **좌표·파일 12종을 실측 대조 — 부패 0건.** `quota/billable_actions.py` · 원장 필드명
  `target_project_id`(enforcement 14 · ledger 8 · lock 11회) · `ScratchRecovery.tsx:83`(여전히
  `<pre>` 한 줄) · `describeWritingError`(`api/client.ts:880`) · `sessions_mongo._aware`(5회) ·
  compose `ulimits.nofile` · `context_search/item_render.py` · `activity/log_mongo.py` ·
  SoT 계약 버전 `v1.7.96` · 프롬프트 sha256 핀 · `https://testserver` 쿠키 관례 · `pytest` 실행법.
- **지운 것 하나 — 프론트 플레이크 항목이 자기 트리거를 충족했다.** 그 항목은
  *"2026-08-10 에 과부하 조건(백엔드 전수와 동시 실행)을 재현했으나 green 이었고, 그 뒤 프론트가
  236 → 323 셀로 늘도록 **재관측이 없었다** … 다음에 또 재현 안 되면 지운다"* 였다.
  오늘 **백엔드 전수와 동시에** 프론트 전수를 돌려 **27파일 · 323셀 green**(550초) — 조건도
  현행 규모도 충족했으므로 지웠다. 관측 상세는
  [`verifications/2026-07-31/k4_front_counter_budget.md`](../../verifications/2026-07-31/k4_front_counter_budget.md) 에 남는다.
- **헤더의 검수 서사 두 문단을 한 줄로 줄였다** — 규칙 셋(순 결과로 판정 · 마지막 단계는 헤더
  갱신 · 지우기 전 grep)만 남기고 과거 검수의 서사는 지웠다. 그 문단들이야말로 이 파일이
  경고하는 **누적**의 표본이었다(1441자 한 줄).
- **결과: 466 → 430줄.** 오늘 슬라이스와 마감 메모를 얹고도 **순증 0**이다.

### Task 4 — 리랭커 재검이 남긴 비차단 3건 보강 (오너 취사 → 셋 다 채택)

같은 날 다른 세션의 독립 재검([`verifications/2026-08-21/reranker_c1_h1_h2_closure.md`](../../verifications/2026-08-21/reranker_c1_h1_h2_closure.md),
`96294c8`)이 **합격**을 내며 Hardening 3건을 *"오너 취사 — 어느 쪽도 이 슬라이스 계약에
필요하지 않다"* 로 남겼다. 오너가 보강을 지시해 셋 다 닫았다. **프로덕션 코드 0줄**(`cfcb182`).

- **H2-a·H2-b — 동률 셀**: `test_ties_keep_the_request_order` → `test_ties_keep_the_response_order`.
  안정 정렬이 보존하는 것은 **응답에 담긴 순서**이고 요청 순서와 겹치는 것은 정합 서버가
  동률을 요청 순서로 보낼 때뿐인데(2026-08-20 H2 가 주석을 그렇게 정정했다), **셀 이름과
  입력에는 정정 전 문언이 남아 있었다.** 두 해석이 갈리는 입력(응답 `[2,0,1]` 전부 동점 →
  기대 `(2,0,1)`)을 subtest 로 더하고 종전 입력은 회귀로 남겼다.
- **비순열 경로 로그**: `FailOpenScopeTest::test_a_response_that_is_not_a_permutation_is_logged_too`.
  *"순열 검사가 `try` 안에 있다"* 는 주장의 **관측 가능한 차이는 로그뿐**이다 — 검사가 경계
  밖에 있어도 반환값은 같다. 원인이 `not a permutation` 으로 남는 것까지 단정한다(프로바이더
  장애와 구별되지 않으면 부분 응답 `top_n` 을 장애로 오진한다).

**★ 지적 둘이 가상이 아니었다는 것이 뮤테이션으로 나왔다.**

| 뮤테이션 | diff | 무는 셀 | 수 |
|---|---|---|---|
| **N1** 동률을 **오름차순 인덱스**로 tie-break | `sort(key=lambda p: (-p[0], p[1]))` | `…keep_the_response_order` **새 subtest 만** (`SUBFAILED(response='응답이 다른 순서로 왔다')`) | 1 |
| N2 동률을 내림차순 인덱스로(변형) | `sort(key=lambda p: (p[0], -p[1]), reverse=True)` | 같은 새 subtest 만 | 1 |
| **N3** 순열 검사를 경계 밖 배치와 동형으로 | `raise RerankProviderError(…)` → `return items` | **새 로그 셀만** — 기존 `FailOpenTest` 비순열 **5 subtest 는 전부 green** | 1 |
| N4 원인 제거 | `exc_info=True` → `False` | 새 로그 셀 + 기존 `…logged_rather_than_swallowed` | 2 |

- **N1 이 핵심이다** — 그 배치에서는 동률이 요청 순서와 같아지므로 **종전 셀의 기대값이 그대로
  나온다.** 즉 H2-b 는 "성질이 안 잠겼다" 를 넘어 **실재하는 뮤테이션 계열 하나가 통째로 안
  보이는 상태**였다. N3 도 같은 모양이다 — 반환값이 동형이라 **로그 말고는 갈릴 것이 없다.**
- **R6b(원본 리터럴) 페어링이 1 → 2 로 바뀐다** — [`repro_reranker_slice.sh`](../../verifications/2026-08-20/repro_reranker_slice.sh)
  재실행 실측 `2 failed, 23 passed, 24 subtests`. **스크립트 리터럴은 무변**이고, 그 스크립트는
  전 구간(Part 1~4) 재실행해 **트리 clean** 까지 확인했다.
- **기록 정리**: 재검 기록의 §Hardening 세 항에 폐쇄 결과를 붙이고(원문은 발행 시점 그대로),
  [`verifications/README.md`](../../verifications/README.md) 인덱스 행에도 폐쇄를 표기했다.
- **★ 그 기록의 사실 하나를 정정했다** — §Outstanding items 의 *"이 승격으로 **미검증 커밋 0**"*
  은 **리랭커 계열에 대해서만 참**이다. 같은 날 먼저 들어온 `29299e5`·`1f9df97` 이 미검증이었고,
  HANDOFF §마감 메모 ②는 처음부터 그렇게 적고 있었다. **이 저장소가 다섯 번 밟은 계열**(미검증
  목록을 문구에서 유도)이라 취소선 + 정정으로 남겼다.

### Task 5 — 합동 재검이 남긴 셋 (H-P1·H-P2·M7) — 오너 결정 하나 포함

두 번째 독립 재검([`verifications/2026-08-21/product_name_and_hardening.md`](../../verifications/2026-08-21/product_name_and_hardening.md),
`a46110f`)이 `29299e5`·`cfcb182` 를 **둘 다 합격**시키면서, 검증자 **자체 축**으로 침묵 둘을
찾고 **새 잔존 하나**를 발견했다. 셋 다 닫았다.

- **H-P2(M8) — 서비스 구분자가 안 잠겨 있었다** (`924b0ab`, 프로덕션 0줄). `title="에-라잇 App"`
  으로 바꿔도 **3셀 전부 침묵**했다 — `startswith(제품명)` + 은퇴명 부재만 봤기 때문이다.
  구분자는 취향이 아니라 **D-2026-08-21-a 가 정한 글자**이고 그 결정의 근거가 *"코드·로그·compose
  서비스명과 글자가 이어진다"* 였으므로, `_DECIDED_TITLES` 표로 **정확 일치**를 잠갔다.
  **표는 데이터라 표 자체가 규칙을 벗어날 수 있다** → 표를 검사하는 둘째 셀을 함께 뒀다.
- **M7 — 표기 변형** (`924b0ab`). `"AI writing System"` 주입에 침묵했다. 검증자는 *"잔존 0실측,
  조치 불필요"* 로 분류했는데 **닫는 비용이 한 줄이라 닫았다**(판정을 뒤집은 것이 아니라 비용
  판단이다). 정규식 `ai[ \t]+writing[ \t]+system`/`IGNORECASE` — **밑줄·하이픈 형태는 여전히
  안 잡는다**(식별자다). 줄바꿈도 안 건너뛴다 — 우연한 적중을 만들지 않기 위해서다.
- **★ H-P1 — 저장소 정문에 살아있는 은퇴명** (`c1fed21`, 오너 결정 D-2026-08-21-d).
  `README.md:1` H1 과 `LICENSE:1` 제목줄이 **모든 스윕 밖**에 있었다(백엔드는 `.py`+compose,
  프론트는 `frontend/`). **이 슬라이스가 치유하려던 병과 정확히 같은 모양**이고 과거 어느 검증
  기록에도 지적된 적이 없다. 그래서 **자리를 고치는 것으로 끝내지 않고 스윕을 그 자리까지
  넓혔다** — `_FRONT_DOOR = ("README.md", "LICENSE")`.
  - **확장자 규칙으로 열지 않은 이유**: `HANDOFF.md`·`CHANGELOG.md` 가 함께 들어오는데
    **그 둘은 이력이라 은퇴명이 남아 있는 것이 맞다**(재검이 `HANDOFF.md:164` 를 무해로 분류한
    것과 같은 판단). 대신 **이름 목록은 자기가 비는 것을 못 보므로** 존재 트립와이어를 뒀다.
  - **남는 대가는 적어 둔다**: 트립와이어는 *존재* 를 보지만 **빠뜨린 세 번째 정문**은 못 본다.
    다음 검증자에게 볼 축으로 넘겼다(HANDOFF §마감 메모 ②).

| 뮤테이션 | diff | 무는 셀 | 수 |
|---|---|---|---|
| **P1**(= M8 재유도) | `title="에-라잇 App"` | `…titles_its_api_docs_with_the_decided_letters` **SUBFAILED(application)** | 1 |
| **P2** 표 자체를 규칙 밖으로 | `_DECIDED_TITLES["application"] = "AI Writing App"` | 위 셀 + `…decided_letters_themselves_follow_the_naming_rule` | 2 |
| **P3**(= M7 재유도) | `scripts/index_sync_worker.py` 에 `# AI writing System` | `…survives_in_no_backend_source` | 1 |
| **P4 (over-strict)** 식별자 형태 주입 | `# ai_writing_system / ai-writing-system-frontend` | **없음 — 4 passed(오탐 0)** | 0 |
| **P5** README H1 되돌림 | `# AI Writing System` | `…survives_in_no_backend_source` | 1 |
| **P6** LICENSE 제목줄 되돌림 | `AI Writing System — License` | 같은 셀 | 1 |
| **P7** 정문 파일 소실 | `LICENSE` 를 옮김 | 트립와이어 **SUBFAILED(LICENSE)** + 스윕 셀(읽기 실패로 시끄럽게 죽는다) | 2 |

P5·P6 은 **종전에는 둘 다 침묵**이었다 — 그것이 H-P1 의 실체다. P4 는 반대 방향으로,
식별자 개명을 막는 over-strict 셀과 **같은 경계**를 스윕도 지킨다는 확인이다.

### Task 6 — Phase 10 부채 ④ 폐쇄: 비활성 농도를 한 값으로

오너가 Phase 10 에서 이 항목을 먼저 열기로 했다. **고르기 전에 계산했다** —
값 하나를 고르는 것은 디자인 판단이고, 이 저장소는 그런 판단에
**계산 + 재현 스크립트**를 붙이는 선례(10.1 팔레트)를 갖고 있다.

- **신규 [`docs/plans/10_disabled_contrast.py`](../../plans/10_disabled_contrast.py)** — `opacity` 가
  요소를 배경과 합성하므로 실효 겉모습은 **합성된 색**이고, 그것을 그 자리의
  배경과 견준다. 의존성 없음, `10_palette_contrast.py` 와 같은 자세.
- **★ 부채의 전제가 흔들렸다.** 부채는 *"값이 넷이라 흩어져 있다"* 로 열렸는데,
  네 자리는 **글자색이 서로 다르다**(흰색 · `blue-700` · `blue-900` · `slate-600`).
  합성해서 재면 현행 네 값의 실효 대비는 **1.89 – 2.21** 로 이미 좁았고,
  alpha 를 한 값(0.45)으로 모으면 **1.99 – 2.75** 로 오히려 **벌어진다**
  (`.order-controls` 는 글자가 가장 진해 혼자 튄다).
- **실물을 냈다** — 네 자리를 앱의 실제 색·표면 그대로 렌더한 명세서(아티팩트)를
  만들어 오너가 후보값을 눈으로 견줬다. **2026-08-11 오너 지적**(*"타이포 스코프
  볼 수 있는 곳이 없네… 뭐가 뭔지도 잘 모르겠고"* → **이런 판단을 물을 때는 화면이나
  실물 예시를 함께 낸다**)을 이번에 적용한 것이다.
- **구현**(`c37d77b`) — `:root` 에 `--disabled-opacity: 0.45` 를 두고 네 자리를 옮겼다.
  **의도된 예외 둘은 접지 않았다**: `.session-menu button:disabled`(`cursor: wait` =
  **진행 중**이라 다른 상태) · `.login-form input:disabled`(**버튼이 아니다** — 입력은
  글자색까지 함께 죽인다).
- **신규 가드 [`frontend/src/disabledState.test.ts`](../../../frontend/src/disabledState.test.ts) 3셀** —
  잠그는 것은 **값이 아니라 자리의 수**다(같은 값에서도 실효 대비는 흩어지고,
  그것을 알고 고른 것이므로 값을 잠그면 거짓이 된다). 예외 목록은 손으로 들지 않고
  **스타일시트에서 유도**한다.

| 뮤테이션 | diff | 무는 셀 | 수 |
|---|---|---|---|
| **Q1** 새 자리가 리터럴을 들고 온다 | `.order-controls` 를 `0.35` 로 되돌림 | `dims every disabled button…` + `leaves the two states…`(예외 집합이 커진다) | 2 |
| **Q2** 토큰이 둘로 갈린다 | `--disabled-opacity` 두 번 선언 | `declares that token exactly once…` | 1 |
| **Q3 (over-strict)** 진행 중 예외를 접는다 | `.session-menu` 를 토큰으로 | `leaves the two states…` | 1 |
| **Q4 (over-strict)** `cursor: wait` 제거 | `wait` → `not-allowed` | 같은 셀 | 1 |

Q1 이 **두 셀**을 무는 것은 설계대로다 — 완전성 셀과 예외 셀이 같은 자리를 반대
방향에서 본다(리터럴이 늘면 한쪽은 *"토큰을 안 썼다"*, 다른 쪽은 *"예외가 늘었다"*).

## Issues found

- **문제**: HANDOFF §Owner Decisions Needed 의 H2 항목이 `application/main.py:1581` 을 가리켰는데
  실제 자리는 **1611** 이었다.
  **원인**: 그 줄을 적은 2026-08-11 이후 `main.py` 가 자랐다. `file:line` 은 코드가 아니라
  **좌표**라 커밋마다 낡는다.
  **조치**: HANDOFF 의 H2 항목 자체가 오늘 닫혀서 함께 사라졌다. 남기는 규칙은
  §함정 에 이미 있는 것과 같다 — **인계 문서의 좌표는 인용 전에 그 자리에서 다시 확인한다.**
  **결과**: 세 자리를 정확히 짚었고 놓친 자리는 없다(스윕 셀이 그것을 단정한다).

- **관측(고치지 않음)** — `frontend/package.json` 의 npm 패키지명이
  `ai-writing-system-frontend` 이고 Docker 이미지·컨테이너 이름 접두도 저장소 디렉터리 이름을
  따른다. **둘 다 표시명이 아니라 식별자**이고 사용자·`/docs` 어디에도 안 나오므로
  오늘 범위 밖으로 둔다. 바꾸면 이미지·볼륨 이름이 함께 흔들려 성질이 다른 작업이 된다.

- **문제**: Task 5 뒤 전수에서 `test_quota_enforcement_live_mongo.py::…test_only_one_of_many_concurrent_requests_takes_the_last_slot`
  **1건 실패**(`2359 passed · 1 failed · 1 skipped · 2598 subtests`).
  **원인**: **부하 의존 플레이크였다 — 내 변경 탓이 아니다.** §추적 부채가 적어 둔 분류 절차를
  그대로 밟았고 셋 다 일치했다: ① 실패 메시지에 `AdmissionUnavailable` 이 섞였다
  (`['QuotaRefused'×6, 'AdmissionUnavailable'×13]`) ② **`admitted == 1` 은 지켜졌다**(초과 입장 없음 —
  2 이상이면 그때가 진짜 결함이다) ③ **단독 재실행 3/3 통과**. 그 회차에 나는 같은 머신에서
  다른 pytest 를 동시에 돌리고 있었다 — 20 스레드가 한 뮤텍스에 몰릴 때 `_acquire` 예산
  (5회 × 20 ms)이 굶는 스레드를 만든다.
  **조치**: 코드는 안 고쳤다. **2026-08-05 이후 16일 만의 재관측**이라 §추적 부채 항목에 날짜와
  관측치를 더했다. 그 항목이 적어 둔 **권고 수정**(셋째 단정을 `QuotaRefused` **또는**
  `AdmissionUnavailable` 허용으로)은 **여전히 미실시** — 8.3 은 검증된 표면이라 별도 판단이다.
  **결과**: 부하 없는 전수를 다시 돌려 기준선을 다시 잡았다(아래 §Verification).

## Decisions

### D-2026-08-21-a — 세 서비스의 API 문서 제목 표기 (오너)

- **결정**: **제품명만 한글로 통일하고 서비스 구분자는 영문 유지** —
  `"에-라잇 Application"` · `"에-라잇 Embedding Service"` · `"에-라잇 LLM Gateway"`.
- **오너의 말**: *"제품명은 에-라잇으로 통일한 거 아니었나? AI write 같은 느낌이지."*
  → 통일 대상이라는 것은 이미 정해진 것(9.2 P6 · 10.0 D5)이고, 열려 있던 것은 **세 서비스의
  글자를 각각 무엇으로 쓸지**뿐이었다.
- **트레이드오프**: 전부 한글(`"에-라잇 임베딩 서비스"`)이 API 문서만 읽을 때 더 자연스럽지만,
  코드·로그·compose 서비스명(`application`·`embedding`·`llm_gateway`)과 글자가 끊겨 검색이 안 이어진다.
  로마자 통일은 **"에-라잇" 의 로마자형이 정해진 바 없어** 새 명명 결정을 하나 더 낳는다.
  선택안은 그 둘을 피하면서 제품명 통일이라는 목적을 달성한다.

### D-2026-08-21-b — 오늘 범위 (오너)

- **키 조달은 알파에서** 한다. 그래서 dogfood 및 키가 선행인 항목 둘(리랭커 품질 판정 · 임베딩
  배치 실측)은 **오늘 열지 않는다** — 열어도 `no-op 대 no-op` 비교라 못 닫는다.
- **`92b9b24` 독립 검증은 다른 검증자에게 넘긴다.** 오늘 이 세션은 구현자이므로
  자기 검증으로 대체하지 않는다.

### D-2026-08-21-c — 재검 Hardening 3건: 셋 다 채택 (오너)

- **결정**: 재검이 *"오너 취사"* 로 남긴 H2-a·H2-b·비순열 로그를 **전부 보강**한다.
- **트레이드오프**: 셋 다 슬라이스 계약에 **필요하지 않다** — 검증자 판단이 맞고, 계약은
  보강 전에도 성립한다. 그럼에도 채택한 근거는 뮤테이션이 보여 준 것이다: **N1·N3 은 종전
  잠금이 원리적으로 못 보는 계열**이고, 이 저장소가 반복해 만난 실패 모양(*"계약 문언이
  잠금보다 넓다"*)이 정확히 그 간극이다. 비용은 **테스트 전용 · 프로덕션 0줄**.

### D-2026-08-21-d — 저장소 정문(README·LICENSE)의 은퇴명 (오너)

- **결정**: **둘 다 제품명으로 교체**한다 — `README.md:1` `# 에-라잇` · `LICENSE:1` `에-라잇 — License`.
  저작권자(`entangelk`)는 무변이라 법적 의미는 바뀌지 않는다.
- **선택지**: ⓐ 둘 다 교체(+스윕 확장) · ⓑ README 만 교체하고 LICENSE 는 발행 시점 텍스트로 유지
  (제외 사유를 문언화) · ⓒ 둘 다 유지하고 *"저장소 메타데이터"* 로 의도 문언화.
- **왜 ⓐ 인가**: D5 가 정한 것은 *"제품명은 하나"* 이고, README H1 은 **사람이 가장 먼저 읽는
  자리**다. ⓒ 도 성립하는 입장이지만 그 근거(*"관객이 개발자뿐"*)는 H2(=API 문서)에서 이미 한 번
  유예의 근거였고 **오늘 닫힌 자리**다 — 같은 이유를 두 번 쓰면 유예가 아니라 방치가 된다.
- **함께 정한 것**: 결정은 자리 둘이지만 **이행은 스윕 확장까지**다. 검증자 지적의 핵심이
  *"모든 스윕 밖"* 이었으므로, 글자만 고치면 **다음 재유입 때 또 아무도 못 본다.**

### D-2026-08-21-e — 비활성 버튼 농도 (오너)

- **결정**: **alpha 한 값으로 통일**(`--disabled-opacity: 0.45`). 세 선택지는
  ⓐ 실효 대비로 통일(solid 만 0.42→0.50) · ⓑ **alpha 한 값** · ⓒ 현행 유지 + 문언화.
- **왜 ⓑ 인가** — 오너가 실물 명세서를 보고 **문제의 축이 다르다**고 판단했다:
  *"대비가 문제가 아니라 색 선택의 문제인 것 같다."* 대비를 맞추는 것은
  **잘못된 축에서 정밀해지는 것**이고, 그렇다면 규칙이 읽기 쉬운 쪽이 낫다.
- **★ 그 판단이 새 축을 열었다** — 관리자 카드의 *"영구 삭제"* 는 **red 계열**이어야
  하고, 버전 내보내기·원고 순서는 **진한 블랙/회색**이어야 눈에 보인다.
  버튼을 **위험·일반·특수** 카테고리로 나누고 **카테고리별 색을 실측**하는 작업이
  필요하다 — 추적 부채로 등재했고 **트리거는 육안 확인**이다.
- **알고 고른 대가**: 이 값에서 네 자리의 실효 대비는 1.99 / 2.21 / 2.75 / 2.02 로
  흩어진다. 그래서 가드는 **값이 아니라 자리의 수**를 잠근다.

## Verification

- **뮤테이션 5종 — 전부 페어링까지 실측**(체크포인트 커밋 `29299e5` 뒤에 변형, `git status --short`
  빈 것 확인 후 시작 · 각 변형마다 `git checkout --` 원복 · 마지막에 트리 클린 재확인).

  | 뮤테이션 | file:line | 무는 셀 | 수 |
  |---|---|---|---|
  | M1 application title 을 옛 이름으로 | `application/app/main.py:1611` | `…titles_its_api_docs…` **SUBFAILED(service='application')** + `…survives_in_no_backend_source` | 2 |
  | M2 embedding title 을 옛 이름으로 | `embedding/app/main.py:76` | 같은 두 셀 (**SUBFAILED(service='embedding')**) | 2 |
  | M3 gateway title 을 옛 이름으로 | `llm_gateway/app/main.py:127` | 같은 두 셀 (**SUBFAILED(service='llm_gateway')**) | 2 |
  | M4 무관한 파일에 옛 이름 주입(`scripts/index_sync_worker.py:1`) | `scripts/index_sync_worker.py` | `…survives_in_no_backend_source` 단독 | 1 |
  | **M5 (over-strict)** 식별자까지 개명 `DEFAULT_DB_NAME = "e_right"` | `core_sot/mongo_repository.py:50` | `…does_not_reach_the_database_identifier` 단독 | 1 |

  M1~M3 이 **두 셀을 동시에** 무는 것은 설계대로다 — 행위 셀(앱의 실제 title)과 완전성 셀(소스
  스윕)이 같은 자리를 다른 층에서 본다. M4 는 **행위 셀이 원리적으로 못 보는 자리**(네 번째 파일)를
  완전성 셀이 혼자 무는 것을 보인다. M5 가 반대 방향이다.
- **focused**: `test_product_name` · `test_admin_surface_separation` · `test_app_import_paths` ·
  `test_embedding_service` · `test_llm_gateway_app` · `test_gateway_capabilities` · `test_docs_indexes`
  → **52 passed · 359 subtests**.
- **frontend 전수**: `npx vitest run` → **27 files · 323 passed**(550초). **백엔드 전수와 동시 실행**했다 — 그것이 §함정 의 프론트 플레이크 항목이 적어 둔 과부하 조건이라 같은 회차로 재관측까지 겸했다(Task 3).
- **계약 산출물**: `npm run gen:api` 재생성 → `schema.d.ts` **diff 0**.
- **전수**: `python3 -m pytest tests -q` → **`2357 passed · 1 skipped · 2589 subtests`**(1409초, 프론트 전수와 동시 실행). **skip 을 먼저 봤다** — 1건이며 정상값인 live Chroma 그것이다. 직전 기준선 `2354 / 1 / 2586`(2026-08-20 `90164df`) 대비 **passed +3 · subtest +3** 으로, 오늘 더한 3셀(그중 한 셀이 subtest 3)과 **정확히 일치**한다.
- **[Task 4 보강 뒤 재측정] 전수 `2358 passed · 1 skipped · 2592 subtests`**(1087초). skip 은 여전히 1(live Chroma).
  **증분을 항으로 분해했다** — 오전 기준선 `2357 / 1 / 2589` 대비: **passed +1** = 새 로그 셀 하나 ·
  **subtest +2** = 동률 셀이 subtest 둘로 갈린 것 · **subtest +1** = **검증자 기록(`96294c8`)이 문서 인덱스에
  등재된 몫**(`test_docs_indexes` 를 단독으로 재 보면 **259 → 260**, 직접 확인). 검증자 기록은 그 값을
  이미 **"등재 전 트리 실측"** 이라고 라벨해 두었으므로 정정할 것이 없다 — 여기 적는 이유는 **내 새 기준선이
  왜 +3 인지**가 셀 증분(+2)만으로는 설명되지 않기 때문이다. 08-20 기록 둘이 적어 둔 *"기록 등재분 +1"* 과 같은 자리다.
- **Task 4 회귀**: `tests/test_rerank.py` → **23 passed · 26 subtests**(보강 전 22 / 24).
  뮤테이션 N1~N4 는 위 표(체크포인트 `cfcb182` 뒤에 변형 · 매 회 `git checkout --` 원복 · 트리 clean 확인).
  [`repro_reranker_slice.sh`](../../verifications/2026-08-20/repro_reranker_slice.sh) **전 구간 재실행** — 전부 물고 트리 clean.
- **[검증자 세션 — 같은 날 이 뒤에 추가] `92b9b24` 독립 검증 완료 → 합격.**
  [`verifications/2026-08-21/reranker_c1_h1_h2_closure.md`](../../verifications/2026-08-21/reranker_c1_h1_h2_closure.md)
  — C1-M1~M3·RV-B1/B2 같은 diff 재유도 전부 일치, 전수 `2357/1/2589` 재현. 인계 볼 축 셋 판정 및
  **R3b 리터럴 갱신 이행**(`33461cc`). reranker_slice 조건부 합격 **승격 확정**(임베딩 B1 선례와 같은
  절차 — 인덱스 행·Verdict 줄·분포 정리). 세부는 그 기록으로 — 여기 중복하지 않는다.
- **[검증자 세션 — 저녁 추가] `29299e5`·`cfcb182` 합동 독립 검증 완료 → 합격.**
  [`verifications/2026-08-21/product_name_and_hardening.md`](../../verifications/2026-08-21/product_name_and_hardening.md)
  — M1~M5(구현자)·M6~M8(검증자 자체축)·N1~N4·R6b(페어링 1→2) 전부 같은 diff 일치,
  `info.title` 실측, 전수 `2358/1/2592` 재현. **★ 신규 발견(H-P1, 오너 결정 대기)**: README H1·
  LICENSE 제목줄의 은퇴명이 **모든 스윕 밖의 살아있는 잔존**. cfcb182 볼 축 둘은 판정 완료(둘 다 결함 아님).
  세부는 그 기록으로 — 여기 중복하지 않는다.
- **[Task 5 뒤 · 부하 없는 재측정] 전수 `2360 passed · 1 skipped · 2598 subtests`**(1245초, 동시 실행 없음).
  **증분 분해** — 직전 `2358 / 1 / 2592` 대비: **passed +2** = 표 검사 셀 · 정문 트립와이어 셀 ·
  **subtest +5** = 그 둘(3 + 2) · **subtest +1** = **검증자 기록 `a46110f` 의 문서 인덱스 등재분**
  (`test_docs_indexes` 단독 **260 → 261**, 직접 확인). skip 은 여전히 1(live Chroma).
  **★ 그 앞 회차는 `1 failed` 였고 그것이 부하 플레이크였다**(§Issues) — 같은 트리에서 부하만
  걷어내 다시 쟀고, **passed 를 뺀 나머지 수치가 두 회차에서 동일**하다(2359+1 = 2360 · 2598 · 1).
- **Task 5 회귀**: `tests/test_product_name.py` → **5 passed · 8 subtests**(H-P2·M7 폐쇄 전 3/3 →
  구분자·표 셀까지 4/6 → 정문 확장 후 5/8). 뮤테이션 P1~P7 은 위 표(체크포인트 `924b0ab`·`c1fed21`
  뒤에 변형 · 매 회 원복 · 트리 clean 확인).
- **[Task 6] frontend 전수 `28 files · 326 passed`**(616초, 보강 전 27/323 — 신규 가드 1파일·3셀).
  backend [`test_design_token_provenance.py`](../../../tests/test_design_token_provenance.py) **5 passed · 90 subtests**
  (CSS 토큰 출처 가드 — 새 토큰이 그 규약을 안 깼다). 뮤테이션 Q1~Q4 는 위 표.

## Next steps

- **다음 작업 = dogfood(GATE-1) 착수** — 인계의 권고는 유지된다. **키 조달(알파)이 선행**이고,
  순서는 `키 조달 → dogfood 질의·정답 축적 → 판정` 이다.
- ~~**`92b9b24` 독립 검증은 대기 중**(다른 검증자)~~ — **완료(같은 날 검증자 세션, 합격·승격)**.
  볼 축 셋(① 경계 폭 ② `assertNoLogs` 스코프 ③ R3b 리터럴 갱신) 전부 판정·이행 —
  [`verifications/2026-08-21/reranker_c1_h1_h2_closure.md`](../../verifications/2026-08-21/reranker_c1_h1_h2_closure.md)
  Findings 5. ~~**미검증 커밋 0.**~~ **[정정 후 폐쇄]** 리랭커 계열만 0 이었다 — 같은 날 먼저 들어온
  `29299e5`·`1f9df97` 과 그 뒤 `cfcb182`(Task 4) 는 **저녁 검증자 세션이 합동 재검해 합격**
  ([`product_name_and_hardening.md`](../../verifications/2026-08-21/product_name_and_hardening.md)).
  코드 커밋 미검증은 다시 0 — **개수를 적지 말고 `git log <최신 검증기록 커밋>..HEAD` 로 유도할 것**
  (이 저장소가 다섯 번 밟은 계열).
- **`cfcb182` 볼 축 둘**(다음 검증자에게): ~~① 동률 셀이 잠그는 "응답 순서 보존" 이 어댑터
  계약인가 **안정 정렬의 우연한 성질**인가 — `_order_from_body` 의 정렬을 바꾸면 계약이
  바뀌는가 셀만 바뀌는가 ② 새 로그 셀이 `not a permutation` 을 **traceback(`exc_info`)에서**
  읽는다 — 예외 문자열에 묶인 단정이 과대한가~~ — **판정 완료(같은 날 저녁 검증자 세션,
  둘 다 결함 아님)**: ① 안정성은 언어 보증+주석 문언과 셀이 일치(정렬 교체는 의식적 계약
  개정 강요) ② exc_info 의존은 "원인이 남는다"의 목적 자체(N4 실증), 문구는 진단 계약.
  [`product_name_and_hardening.md`](../../verifications/2026-08-21/product_name_and_hardening.md) Findings 6.
- **키 없이 열 수 있는 남은 오너 대기 항목**: Phase 10 프론트 디자인 시스템(브리프 미작성) ·
  Phase 8.5 관리자 quota 운영 API · `analysis_extractor` D4 정렬 · 타이포 이관(트리거 미도래).

## [알파 세션 — 같은 날 추가] 시각 검증 환경 조성 (운영 슬라이스, 코드 0줄)

오너가 **D-2026-08-21-e 의 새 축(버튼 카테고리별 색) 트리거 = 육안 확인**을 실행한다고 하여
알파에서 최신 빌드·기동을 마쳤다. 머신은 **알파(RTX 3060)** — 위 Tasks는 베타 세션이다.

- **재빌드**: `application`(=`app` 이미지 4서비스 공유)·`frontend`·`gateway`·`embedding`.
  08-15 이미지는 `services/` 6커밋(리랭커·OpenAI 임베딩·제품명 등)과 `frontend` `c37d77b`
  뒤처져 있었다. 빌드 지표: **704 modules · 진입 421.78 kB · AdminConsole 8.50 kB ·
  관측 lazy 387.43 kB 전부 무변, CSS 30.79 → 30.90 kB**(토큰 추가분).
- **빌드 최신성 실측**: served CSS(`index-BavOddu5.css`)에 `--disabled-opacity:.45` +
  `var()` 소비 4자리 → `c37d77b` 반영. `:8520/openapi.json` `info.title="에-라잇 Application"`
  → `29299e5` 반영.
- **★ llama 리비전 함정 재발**(07-28 함정, 부채 미해결): 볼륨 `refs/main`(`29d0977…`)이
  스냅샷 둘 어느 쪽도 아니어서 `-hf` 기동이 ~6.5GB 재다운로드로 갔다. **다운로드가 끝나면
  캐시가 자체 치유된다**(스냅샷 완성). 그때까지 LLM 경로(원고 생성 등)는 불가 — 버튼 육안
  확인과 무관하므로 기다리지 않고 진행했다.
- **기동**: llama healthy가 `up -d` 전체의 관문이라 **분리 기동**으로 우회했다 —
  `up -d --no-deps gateway`(헬스가 liveness 전용이라 upstream 없이 healthy) →
  `--no-deps application generation_worker` → `frontend`. 결과 **healthy 8 + 워커 2**
  (llama는 다운로드 계속, 완료 후 자동 healthy).
- **환경**: `.env` 없던 알파에 `LLAMA_CTX_SIZE=16384`만 넣어 생성(커밋 금지 분).
  mongo 볼륨은 **계정 0명**이어서 확인 전용 계정 생성 — `visual_demo`(admin,
  quota 무제한 정책 행 동반). 1회용 비밀번호는 이 세션에서 교체까지 마쳤고
  최종 비밀번호는 오너에게 전달. 프로젝트 1건 시드(**육안 확인용 프로젝트**,
  `6a8835cdc216173e8e5a906c`) — 비-LLM 경로(생성·로그인)만 사용했다.
