# Live Smoke Record — Context Gate finding 라이브 유발 + resolve/dismiss 관통

## Subject metadata

- **날짜**: 2026-07-18
- **요청자**: 오너 ("gate finding 라이브 유발" 트랙 선택 — 2026-07-17 dogfood가 라이브로 못 채운 2/7 action을 닫는다)
- **실행자**: 작업 AI(본 세션)
- **대상**: `POST /projects/{id}/context-search`의 Context Gate `reject` → `persist_rejection` durable gate finding 영속화 → review-inbox 노출 → **gate finding resolve / dismiss** 라이프사이클(2026-07-17 `review_inbox_live_e2e.md` §4가 남긴 유일한 라이브 미실행 표면).
- **소스**: 작업 트리(프로덕션 코드 무변). 신규 파일은 라이브 스모크 스크립트 1개(`scripts/phase6_gate_finding_live_smoke.py`)뿐 — 서비스/스키마/테스트 무변.
- **스택**: 이 머신 내부 풀스택 — `docker-compose.yml` + `docker-compose.llama.yml` + scratchpad `-m` 캐시 blob override. 실 Mongo(replica set)·Chroma·Elasticsearch(nori)·embedding(BGE-m3-ko)·worker·gateway·**in-stack llama.cpp 12B**(`google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`, RTX 3060, GPU). application/frontend 이미지는 2026-07-17 dogfood 재빌드본(현 코드, review 라우트 포함) 재사용 — 프로덕션 무변이라 재빌드 불필요.
- **경로**: 두 경로로 각각 관통 — application 직접(`http://localhost:8000`)과 **브라우저 동등**(프론트 nginx `/api` 프록시, `http://localhost:5173/api`).

## Scope

1. Context Gate `reject`를 **결정적으로** 유발(어제는 빈 package로 pass만 관측).
2. `persist_rejection` durable gate finding 영속화(실 Mongo).
3. review-inbox `gate_findings` + 어포던스(`{action,eligible,reason}`) 방출.
4. gate finding detail read.
5. **resolve**(open→resolved) + **dismiss**(open→dismissed) 라이프사이클 전이.
6. 전이 후 open list 서버 재조회로 처리된 항목 이탈 확인(낙관적 패치 없음).

## Methodology

### 결정적 reject 레시피(코드 재도출)

라이브 유발의 핵심은 "package에 아이템이 최소 1개 있어야 gate가 reject할 게 생긴다"였다. 코드 재도출로 두 가지를 확정:

- **`budget_exceeded`는 라이브 엔드포인트에서 도달 불가**(어제 max_tokens=1 시도가 실패한 근본 원인): `ContextSearchService._apply_budget`([service.py:1092](../../../services/application/app/context_search/service.py#L1092))이 예산 초과 아이템을 package에 **넣기 전에** 잘라내므로 included total은 항상 `<= max_tokens`다. Gate의 `total > request.context_budget.max_tokens`([service.py:1205](../../../services/application/app/context_search/service.py#L1205))는 build와 gate가 **같은 request budget**을 쓰는 엔드포인트 경로에서 절대 참이 될 수 없다. (기존 회귀 `test_gate_rejects_budget_violation`은 build 후 **더 작은** budget으로 gate를 재평가해야만 발화 — 엔드포인트는 그러지 않는다.)
- **도달 가능한 결정적 reject = `stale_item`(archived draft)**: `_gate_stale_findings`([service.py:1350-1363](../../../services/application/app/context_search/service.py#L1350))가 `project.archived`/`draft.archived`를 재유도해 finding을 낸다. 기존 회귀 `test_gate_rejects_stale_item_when_project_archived_after_build`([tests/test_context_search.py:750](../../../tests/test_context_search.py#L750))가 바로 이 `evaluate_context_gate` + archive → `stale_item` reject를 잠근다.
- **`current_scene`(Mongo-direct)를 써야 아이템이 gate까지 도달**: source-block **vector** hit은 retrieval-time stale 가드가 archived를 package에서 **배제**한다(`test_archived_draft_hit_excluded_by_stale_guard`, [tests/test_context_search_shared_index.py:212](../../../tests/test_context_search_shared_index.py#L212)) → 빈 package → pass(어제 시나리오). 반면 `current_scene`은 `_run_mongo_step`([service.py:1013](../../../services/application/app/context_search/service.py#L1013))이 `get_draft_version` 블록을 배제 가드 없이 서빙하므로, archived draft의 scene 아이템이 **package에 남아 gate까지 도달** → `stale_item` reject.

### 레시피(스크립트 `scripts/phase6_gate_finding_live_smoke.py`)

1. project → draft → version(단일 단락 snapshot, heading/마커 없음 → current scene = 그 단락 1개, 항상 비어있지 않음).
2. draft archive(`DELETE /projects/{id}/drafts/{draft_id}`) — archive는 읽기 허용이라 scene은 계속 서빙되지만 gate가 `draft.archived`를 재유도.
3. `POST /context-search`(needs=`[current_scene]`, current_position, max_tokens 넉넉) — scene 아이템 included → gate `stale_item` reject → `persist_rejection` 영속화. planner(LLM)가 current_scene step을 못 내면 0 아이템→pass가 되므로 최대 5회 재시도(같은 idempotency_key는 같은 finding id로 수렴 → 중복 없음).
4. **서로 다른 idempotency_key로 2회** reject 유발 → 서로 다른 finding id 2개(하나는 resolve용, 하나는 dismiss용).
5. review-inbox 목록/detail read → 첫 finding **resolve**, 둘째 **dismiss** → open list 서버 재조회.

성공 판정: draft archived · 두 search 모두 reject · open findings ≥ 2 · resolve 200/`resolved` · dismiss 200/`dismissed` · 처리 후 open = before−2.

## Findings

### 1. application 직접 경로(`http://localhost:8000`) — 완전 관통 (PASS, exit 0)

```
archive_http_status : 200,  draft_archived : true
resolve_search      : gate_decision=reject, checks=[stale_item], attempts=1
dismiss_search      : gate_decision=reject, checks=[stale_item], attempts=1
inbox_open_findings : 2
  - 각 finding: check=stale_item, status=open, actions={resolve:true, dismiss:true}
detail_check        : stale_item
resolve             : 200, status=resolved,  idempotent_replay=false
dismiss             : 200, status=dismissed, idempotent_replay=false
inbox_open_findings_after : 0
```

- gate가 실 12B planner(current_scene step)로 package를 채운 뒤 **결정적으로 `stale_item` reject** → 실 Mongo에 gate finding 영속(id `gf:<sha256>`).
- review-inbox `gate_findings`가 프론트가 소비하는 어포던스 `{resolve:eligible=true, dismiss:eligible=true}`(open 상태)를 실 서버에서 방출 — `gate_finding_affordances(is_open=True)` 계약과 일치.
- **resolve·dismiss 둘 다 HTTP 200 + 올바른 terminal status**로 실 전이(2026-07-17 미실행 2/7 action 닫힘).
- 전이 후 open list = 0 = 서버 진실(낙관적 패치 없음).

### 2. 브라우저 동등 경로(프론트 nginx `/api` 프록시, `http://localhost:5173/api`) — 완전 관통 (PASS, exit 0)

동일 스크립트를 `APPLICATION_BASE_URL=http://localhost:5173/api`로 재실행 → 동일 결과(두 search reject·2 findings·resolve `resolved`·dismiss `dismissed`·after 0). **실제 브라우저가 쓰는 경로 그대로** gate finding 유발→검토→resolve/dismiss가 관통.

### 3. 초기 실행에서 발견한 판정식 결함(수정 완료)

첫 실행은 RAW_TEXT가 **3개 단락**이라 search당 `stale_item` finding 3개(단락/블록당 1개, ordinal 0/1/2)를 내 총 6개가 됐고, "정확히 2개" 가정 판정식이 exit 1을 냈다(기능은 이미 resolve/dismiss 200 성공). **단일 단락 RAW_TEXT**로 search당 1 finding으로 만들고 판정식을 `after == before − 2`로 견고화 → 클린 exit 0. (블록 수가 늘어도 판정식은 올바르게 동작.)

## Issues / Observations

- **`budget_exceeded` gate check는 실질적 dead branch**(엔드포인트 경로 한정): build/gate가 같은 budget을 쓰는 한 included total이 budget을 초과할 수 없다. 방어적 코드로 유지는 무방하나, 라이브에서 이 경로로 reject를 유발하려던 어제 접근은 구조상 불가였다. 프로덕션 변경 아님(관찰 기록).
- **gate finding은 `stale_item` 위주로 유발되기 쉽다**: 정상 흐름에서 나머지 check(`cross_project_item`/`missing_sot_reload`/`candidate_item_not_allowed`)는 오염된 입력이 있어야 발화. dogfood에서 실제 유용한 gate finding(예: 실 원고 편집 중 stale pointer)은 별도 관측 대상.
- llama `-hf` 재다운로드 정체(2026-07-17 관측)는 이번에도 유효 → scratchpad `-m` 캐시 blob override(snapshot `f6e7774e`)로 우회. llama 44s만에 healthy(캐시 blob 빠른 로드).

## Verdict

**PASS(라이브 실행 범위, exit 0 ×2 경로).** 2026-07-17 dogfood가 라이브로 남긴 유일한 표면인 **gate finding resolve/dismiss**를 실 스택·실 12B·실 Mongo로 완전 관통했다. Context Gate `reject`를 결정적으로 유발(`stale_item` via archived-draft `current_scene`)해 durable gate finding을 영속화하고, review-inbox 어포던스 방출·detail read·resolve(`resolved`)·dismiss(`dismissed`)·서버 재조회 이탈을 application 직접 경로와 브라우저 동등 프록시 경로 양쪽에서 확인했다. 이로써 **Review Inbox 7/7 write action이 전부 라이브 검증**됐다(2026-07-17의 5/7 + 오늘의 2/7).

## Outstanding items

- **스택 실행 중**: 9개 컨테이너 + 12B llama가 GPU 점유 중(오너가 종료 미선택 — 2026-07-17 선례대로 유지). 브라우저 확인 후 회수: `LLAMA_DEFAULT_MODEL="google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0" docker compose -f docker-compose.yml -f docker-compose.llama.yml -f <scratchpad override> down`(Mongo volume 유지).
- **스모크가 만든 데이터**: 매 실행 새 project(3개 project + archived draft + resolved/dismissed gate findings)가 Mongo에 남는다 — 격리된 스모크 데이터라 정본 원고와 무관.
- **`OPS-1` 트리거**: 이로써 "실 12B 관통 확인" 조건이 gate finding 표면까지 완결됐다. Ready 승격·dogfood 착수는 여전히 오너 결정.

## Reproduction

```bash
# 1) 스택(캐시 blob -m override; application/frontend는 07-17 재빌드본 재사용)
OV=<scratchpad>/docker-compose.llama-cached.yml   # llama command를 -m <cached blob> + --alias 로 교체
LLAMA_DEFAULT_MODEL="google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0" \
  docker compose -f docker-compose.yml -f docker-compose.llama.yml -f "$OV" up -d
# gateway ready / served model 확인
curl -fsS http://localhost:8001/health/ready              # {"status":"ready"}
curl -fsS http://localhost:9080/v1/models                 # google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0

# 2) gate finding 라이브 유발 + resolve/dismiss (application 직접)
APPLICATION_BASE_URL=http://localhost:8000 python3 scripts/phase6_gate_finding_live_smoke.py   # exit 0

# 3) 브라우저 동등(프론트 nginx /api 프록시)
APPLICATION_BASE_URL=http://localhost:5173/api python3 scripts/phase6_gate_finding_live_smoke.py  # exit 0
```
