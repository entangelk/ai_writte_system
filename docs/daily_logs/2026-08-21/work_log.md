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
