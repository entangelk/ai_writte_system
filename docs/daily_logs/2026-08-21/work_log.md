# 2026-08-21 작업 로그 (베타)

> **머신은 베타다.** 키 조달은 알파에서 하기로 오너가 정했으므로, 오늘 범위에서
> **외부 API 키가 필요한 것은 전부 열지 않는다**(리랭커 품질 판정 · 임베딩 배치 실측).

## Goals

- 인계가 권한 dogfood 는 **키가 선행**이라 오늘 열지 않는다. 대신 §Owner Decisions Needed 에서
  **키 없이 닫을 수 있는 항목**을 처리한다.
- **H2(API 문서의 제품명 잔재)** 를 오너 지시대로 *설명 → 결정 → 구현* 순서로 닫는다.
- `92b9b24` 독립 검증은 **다른 검증자에게 넘긴다**(오너 지시) — 오늘 손대지 않는다.

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

## Next steps

- **다음 작업 = dogfood(GATE-1) 착수** — 인계의 권고는 유지된다. **키 조달(알파)이 선행**이고,
  순서는 `키 조달 → dogfood 질의·정답 축적 → 판정` 이다.
- **`92b9b24` 독립 검증은 대기 중**(다른 검증자). 인계에 적힌 볼 축 셋 그대로:
  ① `except Exception` 경계 폭 ② `assertNoLogs` 가 다른 로거까지 막는지
  ③ **`repro_reranker_slice.sh` 의 R3b 블록 리터럴이 낡았다 — 검증자가 갱신한다.**
- **키 없이 열 수 있는 남은 오너 대기 항목**: Phase 10 프론트 디자인 시스템(브리프 미작성) ·
  Phase 8.5 관리자 quota 운영 API · `analysis_extractor` D4 정렬 · 타이포 이관(트리거 미도래).
