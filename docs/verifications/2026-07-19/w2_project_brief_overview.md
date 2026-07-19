# W2 ProjectBrief onboarding + canonical overview — 독립 검증

## Subject metadata

- **날짜**: 2026-07-19
- **요청자**: 오너("작업 AI의 작업한거 확인해서 검증하고 의심하고 또 의심해줄래? W2 작업을 완료했습니다. LLM은 사용하지 않았습니다.")
- **검증자**: 독립 검증 AI(Claude, max effort)
- **검증 대상 slice**: Writing Workspace V2 **W2** — `ProjectBrief` append-only version/persistence/API/OpenAPI/context 배선 + `/projects/:id/overview` canonical-only UI
- **정본 계약 참조**:
  - `docs/system-contract-sot.md` **v1.7.13**(Approved)
  - `docs/plans/writing-workspace-v2-w0-contract.md` §1(`ProjectBrief` exact contract)·§1.2(API)·§4(named regression matrix PB-01~12·SC-01/02)·§5(Deferred)
  - 기계 판독 catalog: `schemas/writing-workspace-v2-w0.schema.json` `$defs.projectBriefVersion`·`projectBriefPutRequest`·`projectBriefGetResponse`·`projectBriefPutResponse`·`projectBriefVersionListResponse`
- **작업 출처**: working tree, uncommitted(`git diff --stat HEAD` 기준 20 file changed, 1005 insertions / 120 deletions; HEAD=`674ff39`)

## Scope

W2는 W0 exact `ProjectBrief` 계약의 runtime 구현 slice다. 아래 표면을 독립 검증했다. **OU-01~14·WI-01~22 행은 W0 §범위와 §4가 명시적으로 W3로 귀속시킨 항목**이므로 본 검증의 blocking 범위에서 의도적으로 제외한다(W3 slice에서 채워야 한다).

1. **Core SOT domain**: `ProjectBriefVersion`/`PutProjectBriefResult` 모델 + 서비스 계약(first null→v1·current-base next·stale/null 409·same-key 선행 replay·different-key distinct·archived write 409·all-null/empty clear history 보존).
2. **Repository Protocol + in-memory + Mongo adapter**: current/version/list/find-request/record surface, `(project_id,version_number)`·`(project_id,idempotency_key)` unique index.
3. **HTTP/OpenAPI**: 4 endpoint(GET current·PUT·GET versions·GET version) + exact Pydantic request/response + trim/blank/duplicate/unknown/missing 422 + idempotency_key 비노출.
4. **Writing context 배선**: `ContextPackage.project_brief` 별도 authoritative item + `<project_brief authority="canonical" version="N">` 직렬화(원고/candidate/memory 병합 금지).
5. **프론트 overview**: `/projects/:projectId/overview` optional onboarding/skip/versioned edit/이력 보존 clear, canonical-only 인물·사건·떡밥 카드 + pending count/link 분리, archived read-only.
6. **문서 일관성**: SoT v1.7.13·CHANGELOG·product-shell·readiness-backlog·HANDOFF.
7. **재현 산출물**: backend pytest·frontend vitest·`npm run gen:api`·`npm run build`·`git diff --check`.

## Methodology

정본 계약을 먼저 읽어 **경계 매트릭스**(아래 Findings §1)를 구축한 뒤, 코드↔계약↔테스트를 교차 검증했다. 작업 AI의 work_log/HANDOFF 주장을 그대로 수용하지 않고 아래 명령으로 독립 재도출했다.

- 정본 읽기: `Read` `writing-workspace-v2-w0-contract.md`(전문)·`schemas/writing-workspace-v2-w0.schema.json`(전문)·`system-contract-sot.md`(헤드+changelog v1.7.13 행).
- 구현 읽기: `core_sot/{models,repository,mongo_repository,service}.py`·`main.py`(모델 917~1083·endpoint 1525~1587·context payload 2585~2614)·`context_search/{models,service}.py`·`writing/prompt.py`.
- 테스트 읽기: `tests/test_project_brief.py`(전문)·`tests/test_core_sot_mongo_indexes.py`(전문)·`tests/test_core_sot_mongo.py`(diff)·`frontend/src/projects/ProjectOverview.{tsx,test.tsx}`·`frontend/src/api/client.ts`(brief 부분)·`frontend/src/App.tsx`(diff)·`frontend/src/drafts/DraftList.tsx`(diff).
- 실행 명령(재현은 §Reproduction):
  - `python3 -m pytest tests/test_project_brief.py tests/test_core_sot_mongo_indexes.py -q -p no:cacheprovider`
  - `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider`
  - `cd frontend && npm test -- --run`
  - `cd frontend && npm run gen:api` 후 `schema.d.ts` byte diff
  - `cd frontend && npm run build`(`tsc --noEmit && vite build`)
  - `git diff --check`
  - `python3 -c "...create_app().openapi()..."` 로 ProjectBrief component dump
  - `format_context_package` cleared-brief 직렬화 probe

## Findings

### 1. 경계 매트릭스(W2 slice) — 모든 행이 named 회귀에 매핑, empty cell 없음

W0 §4의 matrix에서 W2가 소유하는 14행(PB-01~12 + SC-01/02)을 전수 추적했다. 각 행은 named test node에 매핑되고, 방향(fire=under-strict / not fire=over-strict)에 맞는 guard를 가진다.

| ID | dir | 검증 지점(코드↔테스트) |
|---|---|---|
| PB-01 | fire | first null base → version 1. `service.py:330-345`(current None→version_number 1)·`test_project_brief.py:87-90`(version_number==1, idempotent_replay False) |
| PB-02 | not fire | brief 없음 GET → `{"brief": null}`(404 아님). `main.py:1528-1535`(NotFound→404, brief None→null)·`test_project_brief.py:145-148` |
| PB-03 | fire | current base+새 key → next version. `service.py:330-345`·`test_project_brief.py:92-100`(version 2) |
| PB-04 | not fire | stale/null base → 409, write 0. `service.py:331-333`(StaleProjectBriefBase)·`main.py:1556-1557`(409)·`test_project_brief.py:150-163`(409×2 + versions 불변) |
| PB-05 | fire | same key replay → same version, dup 0. `service.py:322-328`(replay lookup이 base 검사 **선행**)·`test_project_brief.py:102-107`(idempotent_replay True, brief 동일, len==1) |
| PB-06 | not fire | 다른 key → distinct version. `service.py:330-357`·`test_project_brief.py:109-114`(id 상이) |
| PB-07 | fire | trim + exact public keys. `main.py:917-919`(`NonBlankBriefString`=strip_whitespace+min_length)·`test_project_brief.py:165-184`(`"  Premise  "`→`"Premise"`, exact 8-key brief + 2-key envelope) |
| PB-08 | not fire | blank/dup/unknown/missing → 422, write 0. `main.py:1066`(extra=forbid)·`1078-1083`(post-trim duplicate validator)·`test_project_brief.py:186-197`(5 case×subTest 422 + versions==[]) |
| PB-09 | fire | all-null/empty clear, history 보존. `service.py:335-357`·`test_project_brief.py:116-132`(version 2·premise None·list==(first, cleared)) |
| PB-10 | not fire | cross-project version read 미노출. `service.py:289-296`(brief.project_id≠path→NotFound)·`test_project_brief.py:199-205`(404) |
| PB-11 | not fire | archived PUT 409, GET/history 유지. `service.py:319-320`(archived→Archived)·`main.py:1556-1557`(409)·`test_project_brief.py:207-218`(409 + GET brief 보존 + versions 보존) |
| PB-12 | not fire | missing/cross current GET → 404(위장 null 아님). `service.py:285-287`(`_require_project` 선행)·`test_project_brief.py:220-227`(missing→404, 다른 프로젝트→null) |
| SC-01 | fire | OpenAPI가 catalog `$defs`와 동형. `test_project_brief.py:239-263`(required set 일치·additionalProperties False·uniqueItems True·path 존재) |
| SC-02 | not fire | catalog root를 endpoint schema로 사용 금지. `test_project_brief.py:265-271`(`/brief` path에 `*.schema.json` 미포함 + named component 참조) |

**추가 W2 표면**(matrix 외 자발적 보강):
- ContextPackage 배선: `test_project_brief.py:274-328`(`ProjectBriefWritingContextTest` 2건 — 별도 authoritative item + brief 없음 미발명).
- Mongo 영속: `test_core_sot_mongo.py` 신규 `test_project_brief_versions_persist_in_order_and_replay`(순차 append + replay 동일).
- Mongo index: `test_core_sot_mongo_indexes.py:49-105`(2개 index 호출 exact + conflicting index→setup error).
- 프론트 overview: `ProjectOverview.test.tsx` 4건(onboarding/normalize·canonical 분리·clear/history·archived read-only).

### 2. 코드 ↔ 계약 literal 일치

- public 필드 8종(`id/project_id/version_number/premise/genre/tone/pov/constraints`)이 `models.py:28-37` dataclass·`main.py:922-934` payload·`schemas/...projectBriefVersion`(line 25-44)·`_project_brief_payload`(`main.py:1387-1397`)에서 동일. `idempotency_key`는 model(`models.py:37`)에는 있으나 **read response에서 의도적 비노출**(`main.py:1387-1397`에 key 없음, 주석 `main.py:967-969`·`1407-1409`로 선례와 일치).
- first PUT은 `base_version_id=null`만 허용(`service.py:330-333`: current None일 때 expected_base=None). version 존재 시 null/wrong base→`StaleProjectBriefBase`(`service.py:331-333`)→HTTP 409(`main.py:1556-1557`).
- replay lookup이 stale base 검사·version 생성 **앞**에 선행(`service.py:322-328`) — W0 §1.2 "같은 key replay는 base stale 검사/provider 호출/version 생성 없이 최초 version 반환" 정확 부합. (WI-19의 같은 패턴이 ProjectBrief에도 동일하게 적용.)
- archived 검사(`service.py:319-320`)는 replay lookup **앞** — archived PUT은 동일 key여도 409. W0 §1.2 "write는 active project만 허용하며 archived는 409"의 literal 부합(replay 예외 명시 없음).
- Mongo unique index 2종(`mongo_repository.py:100-109` `(project_id,version_number)`·`(project_id,idempotency_key)`)이 append-only version 정확성과 idempotent replay를 DB 경계에서 강제.
- ContextPackage.project_brief는 `service.py:627`에서 별도 kwarg로 조립되어 `macro_items`/`micro_evidence`/`token_estimate_total`(`service.py:611-620`)에 **병합되지 않음** — "별도 authoritative item" 계약(D1=A) 부합. 직렬화는 `writing/prompt.py:75-89` `<project_brief authority="canonical" version="N">`.

### 3. 테스트 코드 감사(audit subject, not auditor)

- PB-07(`test_put_normalizes_and_returns_exact_envelope`): trim 전후를 양방향으로 검증(`"  Premise  "`→`"Premise"`, `genre=None` 유지, `["  Rule one ", "Rule two  "]`→trim 결과). envelope key set을 `{"brief","idempotent_replay"}`로, brief key set을 8종으로 exact 단정 → over-strict(idempotency_key 등 내부 필드 노출 시 실패).
- PB-08: `invalid` 5개 case(`premise="  "`·`["ok","  "]`·`["same"," same "]`·unknown key·tone 누락)를 `subTest`로 순회하며 **422 + GET versions==[]**(write 0)를 동시 단정. under-strict(422 미발생 시 실패) + over-strict(정상 입력이 422로 바뀌면 `versions==[]` 단정이 의미 없어져도 case 자체가 방어) 양방향. **post-trim duplicate**(`["same"," same "]`) case가 trim-then-dedup authority를 직접 pin.
- PB-04: stale(`base=None`)·wrong(`base="wrong"`) **둘 다** 409 단정 + versions 컬렉션 불변 단정 → write 0를 행동으로 증명.
- PB-09: cleared version이 version 2 + premise None + **history `(first, cleared)` 보존**을 동시 단정 → hard delete 아님을 pin.
- PB-11: archived PUT 409 + **GET current 보존** + **GET versions 보존**을 함께 단정 → read는 허용·write만 차단을 pin.
- `ProjectBriefWritingContextTest`: brief 존재 시 `macro_items==()`·`micro_evidence==()` 단정으로 candidate/memory로 flatten 금지를 pin하고, 직렬화에 `<project_brief authority="canonical" version="1">`·`- premise:`·`- constraint:` 포함을 단정.

### 4. Pydantic 검증 순서 독립 추론 + 경험적 확증

`NonBlankBriefString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]`(`main.py:917-919`)와 `@field_validator("constraints")`(기본 `mode="after"`, `main.py:1078`)의 순서: pydantic v2는 list field의 core schema 검증(각 item의 strip_whitespace+min_length 적용)이 끝난 뒤 after-validator가 동작하므로, `reject_normalized_duplicates`는 **이미 trim된** list를 받는다. 따라서 `["same"," same "]`→core 단 strip→`["same","same"]`→after 단 `len!=len(set)`→422. **집중 회귀 18 passed가 이 추론을 경험적으로 확정**(PB-08의 `["same"," same "]` case가 422를 반환).

### 5. OpenAPI component ↔ catalog 동형(구조적)

`create_app().openapi()` dump:
- `ProjectBriefVersionPayload`: required 8종 일치·`additionalProperties:false`·`version_number minimum:1`·`premise/genre/tone/pov` nullable·`constraints.uniqueItems:true`. catalog `projectBriefVersion`과 구조 동형.
- `PutProjectBriefRequest`: required 7종 일치·`additionalProperties:false`·`base_version_id` nullable·`idempotency_key` non-blank·`constraints.uniqueItems:true`. catalog `projectBriefPutRequest`과 동형.

### 6. 재현 산출물 — 작업 AI 주장과 정확 일치

| 산출 | work_log 주장 | 독립 재도출 결과 |
|---|---|---|
| 집중 PB/SC+index | 18 passed | **18 passed in 4.42s** |
| backend 광역 | 1142 passed / 50 skipped | **1142 passed, 50 skipped** (60.18s) |
| frontend | 143 passed / 10 files | **143 passed / 10 files** (40.50s) |
| `gen:api` | PASS, 재현 가능 | exit 0, `schema.d.ts` **106941 bytes 양측 동일**(byte-identical) |
| `npm run build` | 96 modules, CSS 17.54/JS 284.19 | **96 modules**, `tsc --noEmit` clean, CSS 17.54(gzip 3.94)/JS 284.19(gzip 87.85) |
| `git diff --check` | PASS | **exit 0** |

### 7. 문서 자기 일관성

- SoT 헤드 `v1.7.13`·갱신일 `2026-07-19`(line 4-5)·changelog 행(line 36)이 W2 내용과 일치.
- CHANGELOG 최상단 2026-07-19 행·product-shell.md(v1.7.13 W2 완료로 갱신)·product-readiness-backlog.md(W2 종료 체크포인트, UX-1 In progress 유지)·HANDOFF Current Status(W2 완료/W3 READY)가 상호 모순 없음.
- W0 §1과 schema catalog 간 literal 모순 미발견(uniqueItems의 trim authority도 catalog `$comment`로 명시됨).

## Issues / Risks

### Blocking(계약 의무)

없음. W2 slice의 경계 매트릭스 14행이 모두 named 회귀에 매핑되고, 코드↔계약 literal이 일치하며, under-strict/over-strict 양방향 guard가 확인됐다. 빈 cell 없음. OU-01~14·WI-01~22은 W0 §범위가 W3로 귀속시킨 항목이라 W2 blocking 범위가 아니다(아직 구현되지 않은 것이 계약 순서상 정상).

### Hardening recommendations(비차단, spec을 넘는 보강 후보)

- **H1 — OpenAPI 정밀도 gap(문서 정밀도, 동작 정상)**: `NonBlankBriefString`의 `strip_whitespace=True`는 JSON Schema keyword로 표현되지 않아 생성 OpenAPI는 `minLength:1`만 내고 `pattern:\S`가 없다. whitespace-only scalar/constraint는 **runtime에서 422로 정확히 거부**(PB-08로 pin됨)하고 catalog는 `pattern:\S`로 명시하지만, OpenAPI만 따르는 client는 `"  "`를 valid로 오인해 예상치 못한 422를 받을 수 있다. 또한 nullable 표현이 catalog의 `oneOf [ref,null]` 대신 `anyOf [string,null]`이고, `uniqueItems:true`는 raw array 기준이라 runtime의 post-trim dedup(`["a"," a"]`→422)을 OpenAPI가 반영하지 못한다. → **보강 후보**: SC-01에 `pattern`/nullable 표현/`uniqueItems` post-trim authority 단정을 추가하거나, Pydantic에 명시 `pattern=r"\S"`를 붙여 catalog와 동형으로 만든다. 동작은 이미 정확하므로 slice 합격에는 영향 없음.
- **H2 — "project 존재, brief 없음 → ContextPackage.project_brief=None" named 누락**: `test_missing_brief_does_not_invent_an_authoritative_item`는 package를 **직접构造**해 rendering만 검증한다. `ContextSearchService.build_context_package`가 project는 존재하지만 version이 없을 때 `_load_project_brief`→`get_current_project_brief`→None 경로를 named로 pin하는 test가 없다(project-less NotFound-swallow 경로는 기존 15 seam으로 간접 커버). → **보강 후보**: existing project + no brief로 `build_context_package`를 돌려 `package.project_brief is None`을 named 단정.
- **H3 — Mongo 동시 version 충돌→409 회귀 미실증**: `(project_id,version_number)` unique index가 동시 PUT 충돌을 `DuplicateKeyError`→service 매핑(`service.py:346-356`)으로 409로 환원하지만, index 존재는 pin되어도 충돌→409 path의 named 회귀는 없다(W0 matrix에 동시성 PB 행 자체가 없음 — sequential contract). → **보강 후보**: live Mongo 동시 충돌 회귀(sandbox 불가, 풀스택 머신 필요). 우선순위 낮음.
- **H4 — cleared/empty brief의 prompt rendering 관찰**: all-null+empty brief version도 `<project_brief authority="canonical" version="N">(empty)</project_brief>`로 직렬화된다(`format_context_package` probe로 확인). "비었지만 정본"을 "정본 없음"과 구분하는 의도로 방어 가능하나, W0는 empty brief의 prompt 표현을 명시하지 않는다. 결함이 아니라 관찰. → **보강 후보**(선택): empty brief를 section 생략로 처리할지 잔존으로 처리할지 owner 판단 후 prompt 계약에 명문화.
- **H5 — `listProjectBriefVersions` 클라이언트 UI 미사용**: `frontend/src/api/client.ts:111-115`에 GET versions 바인딩이 있으나 overview 등 어떤 UI도 사용하지 않는다(`grep` 확인). backend endpoint가 존재하므로 1:1 대칭 바인딩으로 방어 가능하나, CLAUDE.md §2(Simplicity First) 관점에서는 사용처 없는 forward-looking 바인딩이다. → **보강 후보**(선택): version history UI(W3/W4 또는 overview 확장)에서 실제 사용 시점까지 보류하거나, 제거. 영향 없음.

## Verdict

**PASS(조건 없음).**

이유(load-bearing):
1. W2 slice의 경계 매트릭스 14행(PB-01~12·SC-01/02)이 전수 named 회귀에 매핑되고 empty cell이 없다(§1).
2. 코드 literal이 W0 §1·catalog와 정확 일치하며 idempotency_key 비노출·replay 선행·archived write 차단·all-null clear history 보존이 모두 구현+테스트로 잠겼다(§2~§4).
3. 모든 재현 산출물(backend 1142/50·frontend 143/10·gen:api byte-identical·build 96 modules+tsc clean·diff --check exit 0)을 독립 재도출해 작업 AI 주장과 정확히 일치함을 확인했다(§6).
4. 계약 자기 모순 미발견, 문서 일관(§7).
5. OU/WI 행은 W3 귀속이라 W2 범위 외이며, W2가 W3 schema를 선행 노출할 의무가 없다.

H1~H4는 모두 "spec을 넘는 정밀도/보강"이지 contract-required lock 누락이 아니다. 동작(whitespace 422 등)은 이미 정확히 구현·테스트됐다. 따라서 conditional이 아닌 합격.

## Outstanding items

- **Docker compose image build/live smoke 미실행**: 서브 머신에 Docker CLI가 없어 `docker compose build application frontend` 및 실 12B/라이브 overview smoke를 돌리지 못했다(작업 AI 제약과 동일). 정적 계약은 unit/OpenAPI/build로 충분하나, **실 배포 smoke는 Docker 가능 머신에서 owner가 추가 확인**해야 한다(unit이 잡지 못하는 nginx proxy/CORS/route fallback 동작 포함).
- **Node engine 경고**: 서브 머신 Node v22.17.1이 `react-router@8.2.0` 요구 `>=22.22.0`보다 낮아 `EBADENGINE` 경고. build/test는 통과했으나 런타임 지원 범위 정렬을 위해 Node upgrade 권장(운영 정리).
- **W2 작업은 uncommitted 상태**: HEAD=`674ff39` 기준 working tree에 반영만 되어 있고 commit되지 않았다. owner의 publish 승인 대기.

## Reproduction

```bash
cd /mnt/c/develops/ai_writte_system

# 1. 집중 회귀(PB/SC + Mongo index)
python3 -m pytest tests/test_project_brief.py tests/test_core_sot_mongo_indexes.py -q -p no:cacheprovider
# 기대: 18 passed

# 2. backend 광역
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
# 기대: 1142 passed, 50 skipped

# 3. OpenAPI 재현 가능성(schema.d.ts byte-identical)
cd frontend
cp src/api/schema.d.ts /tmp/schema.before.d.ts
npm run gen:api
diff -u /tmp/schema.before.d.ts src/api/schema.d.ts   # 기대: 출력 없음
diff <(python3 -c "from services.application.app.main import create_app; import json; print(json.dumps(create_app().openapi()['components']['schemas']['ProjectBriefVersionPayload'], ensure_ascii=False, indent=2))") <(echo)

# 4. frontend vitest + production build(tsc --noEmit 포함)
npm test -- --run              # 기대: 143 passed / 10 files
npm run build                  # 기대: 96 modules, tsc clean

# 5. whitespace 단정
cd ..
git diff --check               # 기대: exit 0
```
