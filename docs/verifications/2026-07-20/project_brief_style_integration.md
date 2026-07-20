# Verification — 문체/분량 슬라이스 증분 1: ProjectBrief 문체 정본 통합 (D1+D2)

## Subject metadata

- **Date**: 2026-07-20
- **Requester**: 오너 ("작업 AI 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?")
- **Verifier**: Claude (독립 검증, 구현 미관여)
- **Target slice**: 문체/분량 슬라이스 증분 1 — `WritingBrief` 삭제 + `style_rules`·`preferred_patterns`·`forbidden_patterns`·`style_examples` 네 배열을 append-only `ProjectBriefVersion` required key로 통합 (D1=A / D2=A, 오너 보완 결정 1=A·2=B)
- **Canonical spec reference**:
  - [`docs/system-contract-sot.md`](../../system-contract-sot.md) v1.7.21 — changelog entry(line 36) + Phase 5 §(line 497)가 authority
  - [`docs/plans/writing-style-and-length-control-decisions.md`](../../plans/writing-style-and-length-control-decisions.md) — Owner decisions 절(line 165-190), 특히 상한 literal(line 173)
  - [`schemas/writing-workspace-v2-w0.schema.json`](../../schemas/writing-workspace-v2-w0.schema.json) `x-contract-version: v1.7.21` — `projectBriefVersion`(line 25-61)·`projectBriefPutRequest`(line 62-102)의 required/uniqueItems/nonBlank
- **Source of work being verified**: working tree, uncommitted (`git status` — 24 files modified, untracked 없음)
- **작업 AI self-claim**: backend 1225 passed/76 skipped/305 subtests, focused backend 46 passed/24 subtests, frontend 159 passed/11 files, TS/Vite build 101 modules, OpenAPI 재생성 + `git diff --check` clean

## Scope

계약 스코프는 SoT changelog v1.7.21 + decision brief Owner decisions + W0 schema에서 이 증분이 닿는 anchor로 한정했다 (D3 분량 프리셋·D4 character aspect·D5/D6 Gate style은 명시적으로 다음 증분이므로 제외).

1. **정본 계약** — SoT changelog v1.7.21(line 36), Phase 5 §(line 497), decision brief Owner decisions D1=A/D2=A + 보완 1=A/2=B(line 165-190), W0 schema `projectBriefVersion`/`projectBriefPutRequest`.
2. **구현 코드** — `core_sot/models.py`·`mongo_repository.py`·`service.py`, `main.py`(env·Pydantic·HTTP·response payload), `writing/models.py`·`prompt.py`·`service.py`(WritingBrief 제거).
3. **회귀 테스트** — `tests/test_project_brief.py`·`test_writing.py`·`test_core_sot_mongo.py`, `frontend/src/projects/ProjectOverview.tsx/.test.tsx`.
4. **공개 계약 표면** — W0 schema catalog, OpenAPI 생성 타입(`frontend/src/api/schema.d.ts`), Writing ContextPackage prompt 직렬화.

## Methodology

- **계약 우선 읽기**: 코드를 먼저 열지 않고 SoT changelog → Owner decisions → W0 schema 순으로 boundary matrix를 먼저 세운 뒤 코드를 그 matrix에 비교.
- **self-claim 수치 재실측**: focused backend·전체 backend·frontend를 직접 재실행해 작업 AI 보고 수치와 대조 (CLAUDE.md §5 "Reported numbers that nobody recomputed are unverified").
- **mutation testing**: 핵심 fire 분기 under-strict guard가 실제로 bite하는지 코드를 일시 변형·복구해 입증 (이전 검증 기록과 동일 방식).
- **grep 기반 empty-cell 탐색**: env limit 변수·read-path 상한 분기를 참조하는 테스트를 전수 검색해 "should NOT fire" 분기 잠금 여부 확인.
- 사용 명령(재현은 아래 Reproduction 절):
  - `git status --short && git diff --stat`
  - `git diff -- <file>` (각 코드/문서)
  - `python3 -m pytest tests/test_project_brief.py tests/test_writing.py tests/test_core_sot_mongo.py -q -p no:cacheprovider`
  - `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider`
  - `cd frontend && npx vitest run --reporter=dot`
  - mutation: `enforce_style_example_limits`의 max_items 라인을 `if False and ...`로 무력화 → focused run → 복구 후 `grep "if False and"`로 잔여 0 확인 + 재 green.

## Findings

### 1. 정본 계약 — boundary matrix 세우기

SoT changelog v1.7.21(line 36)이 이 증분의 authority이며 네 가지 계약을 못박는다:

- (a) `WritingBrief` 삭제 + `style_rules`·`preferred_patterns`·`forbidden_patterns`(이전)·`style_examples`(신규 자유 텍스트)를 `ProjectBriefVersion`의 **required 배열 key**로 통합.
- (b) 네 배열은 **trim 후 blank·중복을 HTTP 422로 거부**.
- (c) `style_examples`는 기본 **최대 3개·항목당 1,000자**, `PROJECT_BRIEF_STYLE_EXAMPLES_MAX_ITEMS`·`PROJECT_BRIEF_STYLE_EXAMPLE_MAX_CHARS`로 조정, **두 값이 1 미만이면 app 기동 실패**.
- (d) "환경별 상한의 authority는 HTTP validator이고 schema catalog는 required shape·nonblank·uniqueItems를 잠근다." schema `$comment`(line 57, 98)도 "Runtime max items/chars are environment-adjustable; **HTTP validation is authoritative**."로 동일.

Owner decisions(brief line 170, 173)이 (a)(c)의 literal을 보완한다 (1=A: 네 배열 모두 이전·required key / 2=B: 3개·1000자·env 조정·1 미만 기동 실패). Phase 5 §(line 497)가 "별도 `WritingBrief` 계약은 v1.7.21에서 삭제됐다"로 (a)를 재확인.

이에서 계약-required boundary matrix (15행):

| # | 분기 | 방향 | 잠금 위치(코드) | regression 테스트 | 상태 |
|---|---|---|---|---|---|
| 1 | 5 배열 blank 항목 | fire 422 | `NonBlankBriefString`(main.py:953) | `test_invalid_content_rejected_without_write` | ✓ |
| 2 | 5 배열 post-trim 중복 | fire 422 | `reject_normalized_duplicates`(main.py:1184-1197, 5필드) | `test_invalid_content_rejected_without_write`(각 배열별 subTest) | ✓ |
| 3 | `style_examples` > MAX_ITEMS | fire 422 | `enforce_style_example_limits`(main.py:1199-1204) | `style_examples=["a","b","c","d"]` | ✓ (mutation 입증) |
| 4 | `style_examples` 항목 > MAX_CHARS | fire 422 | `enforce_style_example_limits`(main.py:1205-1208) | `style_examples=["x"*1001]` | ✓ |
| 5 | 네 배열 required key 누락 | fire 422 | `PutProjectBriefRequest` required(main.py:1173-1188) | missing-field subTest 4종 | ✓ |
| 6 | env `..._MAX_ITEMS` < 1 | fire 기동실패 | `_project_brief_style_example_limits`(main.py:971-975) + `create_app`(main.py:1394-1395) | `test_invalid_style_example_limit_fails_app_creation`(ITEMS=0) | ✓ |
| 7 | env `..._MAX_CHARS` < 1 | fire 기동실패 | 동일 루프(main.py:971-975) | — | △ 명시 subTest 없음(동작은 올바름) |
| 8 | env 비숫자 | fire 기동실패 | `_env_int`→`int(raw)`(main.py:481) raise | — | △ 명시 테스트 없음(선례 동형) |
| 9 | legacy Mongo 문서(네 필드 없음) | not-fire 빈배열 read | `_to_project_brief` `doc.get(..., ())`(mongo_repository.py:558-565) | `test_legacy_project_brief_document_reads_with_empty_style_arrays` | ✓ |
| 10 | 정상 네 배열 | not-fire 200 | — | `test_put_normalizes_and_returns_exact_envelope` | ✓ |
| 11 | 빈 배열(clear) | not-fire 200 | — | `test_empty_version_clears_current_and_preserves_history` | ✓ |
| 12 | env 상한 상향 + 다수 예시 write | not-fire 200 | — | `test_style_example_limits_are_environment_adjustable_both_directions`(4/1001) | ✓ |
| 13 | **env 상한 하향 + 기존 append-only read** | **not-fire 200(read 상한 무관)** | `ProjectBriefVersionPayload`는 limit validator **없음**(main.py:990-998) | **—** | **✗ empty cell (B-1)** |
| 14 | ContextPackage prompt 네 배열 직렬화 | fire(prompt 라인) | `format_context_package`(prompt.py:80-84) | `ProjectBriefWritingContextTest::test_brief_style_fields_render_in_writing_prompt` | ✓ |
| 15 | `WritingBrief` dead path 제거 | fire(import/서명 정리) | writing/models.py·prompt.py·service.py | `test_writing.py`에서 brief 케이스 2건 삭제 | ✓ |

행 13이 빈 칸이다 — 아래 B-1 참조.

### 2. 구현 코드 ↔ 계약 literal 대조

- **`ProjectBriefVersion`**(core_sot/models.py:44-47): 네 배열이 `tuple[str, ...] = ()` 기본값으로 추가됐다. frozen dataclass 끝에 추가라 기존 생성 호출 호환. ✓
- **Mongo 영속**(mongo_repository.py): `_project_brief_doc`(line 539-542)가 네 배열을 `list()`로 직렬화, `_to_project_brief`(line 558-565)가 `doc.get(..., ())`로 복원. 주석이 "v1.7.13 ProjectBrief documents predate the style arrays"로 legacy 의도를 명시. ✓ 행 9의 회귀로 잠김.
- **`CoreSotService.put_project_brief`**(service.py:422-426, 456-460): 시그니처·brief 생성에 네 배열 전달. ✓
- **HTTP request/response**(main.py): `ProjectBriefVersionPayload`(line 990-998)와 `PutProjectBriefRequest`(line 1173-1188) 양쪽에 네 배열이 `NonBlankBriefString` + `uniqueItems`로 선언. **오직 `PutProjectBriefRequest`(write 경계)에만 `enforce_style_example_limits` validator**(line 1199-1209)가 붙어 있다 — response/read 모델에는 없다. 이것이 행 13(read 상한 무관)의 코드 구현이며 올바르다. 다만 잠금이 없다(B-1).
- **env 상한 + 기동 검사**(main.py:955-975): `PROJECT_BRIEF_STYLE_EXAMPLES_MAX_ITEMS=3`·`PROJECT_BRIEF_STYLE_EXAMPLE_MAX_CHARS=1000` 상수, `_env_int` 파싱, `< 1` 시 `ValueError`를 `create_app`(line 1394-1395)이 기동 시 강제. `_env_int`(line 481)는 `int(raw)`라 비숫자도 raise. compose(`docker-compose.yml`)에 두 env가 `${...:-3}`/`${...:-1000}`로 노출. ✓
- **WritingBrief 제거**: `writing/models.py`(dataclass 삭제), `writing/prompt.py`(`_format_brief` 삭제, `build_writing_request`의 `brief=` 파라미터 제거, `format_context_package`에 네 라인 추가), `writing/service.py`(`generate`/`_validate`의 `brief=` 제거). `main.py`에서 `WritingBrief`를 참조하는 코드는 변경 전에도 0회였으므로(dead path) 삭제가 런타임 동작을 바꾸지 않는다는 work_log 주장이 성립. ✓
- **Prompt 직렬화**(prompt.py:80-84): `f"- style rule: {rule}"`·`f"- prefer: {pattern}"`·`f"- avoid: {pattern}"`·`f"- style example: {example}"`로 `<project_brief authority="canonical">` 섹션에 네 배열이 실린다. 기존 `constraints`(`- constraint:`)와 동형. test assertion 4종과 일치. ✓

literal 대조 결과: SoT changelog (a)(b)(c)(d) 네 조항이 코드에 축자 일치. paraphrase 없음.

### 3. W0 schema catalog 대조

`schemas/writing-workspace-v2-w0.schema.json`:
- `x-contract-version: v1.7.21`(line 6) 갱신. ✓
- `projectBriefVersion`(line 28)·`projectBriefPutRequest`(line 65)의 `required`에 네 배열 추가. ✓
- 네 배열 모두 `uniqueItems: true` + `items: nonBlankString`. ✓ schema integration test(`WorkspaceW0SchemaIntegrationTest`)가 `ProjectBriefVersionPayload`·`PutProjectBriefRequest` 양쪽 네 필드의 `uniqueItems`를 pin.
- `style_examples`의 `$comment`(line 57, 98): "Runtime max items/chars are environment-adjustable; **HTTP validation is authoritative**." — 정적 `maxItems`/`maxLength`를 두지 않은 근거가 명시됐고, 이것이 (d) 계약과 일치. ✓

### 4. 회귀 테스트 감사 (test code is audit subject, not auditor)

`tests/test_project_brief.py`:
- `test_invalid_content_rejected_without_write`: 네 배열 blank/duplicate + `style_examples` 4개/1001자 + missing 4종을 각각 subTest로 422 단언. PUT 거부 뒤 `GET .../versions == {"versions": []}`로 **write 0**까지 pin(이 구조가 mutation 시 cascading fail을 유발 — 아래).
- `test_style_example_limits_are_environment_adjustable_both_directions`: env를 **4/1001로 상향** patch하고 4개/1001자 write → 200. over-strict(상향이 안 먹히는 mutation)를 잡는다. ✓
- `test_invalid_style_example_limit_fails_app_creation`: env `..._MAX_ITEMS=0` → `create_app()`이 `ValueError("must be at least 1")`. ✓
- `ProjectBriefWritingContextTest`: `build_context_package` → prompt 렌더에 네 라인(`- style rule:`·`- prefer:`·`- avoid:`·`- style example:`) 포함 단언. end-to-end(ContextPackage.project_brief → ProjectBriefVersion → prompt) 경로 잠금. ✓
- `ProjectBriefContractTest`: clear 시 네 배열 모두 `[]` 전송, replay 동등성 등.

`tests/test_core_sot_mongo.py`: `test_legacy_project_brief_document_reads_with_empty_style_arrays`가 네 필드 없는 legacy doc을 `insert_one`으로 심고 read가 네 배열 `()`를 반환하는지 pin. ✓ 행 9.

감사 결론: assertion들이 (a) 계약을 실제로 pin하고 (b) under-strict guard(버그 재현 가능)를 갖추고 (c) missing-field 4종을 각각 커버. 행 1-6, 9-12, 14-15는 양호. **행 13만 빈 칸.**

### 5. mutation testing (adversarial)

- **mutation (행 3 under-strict 입증)**: `enforce_style_example_limits`의 max_items 검사를 `if False and len(value) > max_items:`로 무력화 → `tests/test_project_brief.py` 실행 → **8 failed / 20 passed**. `style_examples=["a","b","c","d"]`가 422를 통과해 version 1을 만들자, "write 0"을 검증하는 이후 GET assertion들이 state pollution으로 cascading fail. fire 분기 under-strict guard가 확실히 bite함을 입증. 즉시 `grep "if False and"` 잔여 0 확인 후 복구, focused 재실행 **20 passed / 15 subtests**로 green 복귀.
- 행 13(read-path over-strict)은 mutation으로 "테스트가 없다"를 입증하는 셈이므로 grep으로 대체(아래 Issues).

### 6. 수치 재실측 (self-claim 대조)

| 항목 | 작업 AI 보고 | 검증자 실측 | 일치 |
|---|---|---|---|
| focused backend | 46 passed / 24 subtests(사용자 메시지) | 46 passed / 57 skipped / **24 subtests** | ✓ (subtests) |
| focused backend(work_log 본문 line 310) | "46 passed / 20 subtests(보강 전)" | 24 subtests | ✗ work_log 본문이 stale |
| 전체 backend | 1225 passed / 76 skipped / 305 subtests | 1225 passed / 76 skipped / **309 subtests** | △ passed/skipped 일치, subtests 4 차이 |
| frontend | 159 passed / 11 files | 159 passed / 11 files | ✓ |
| build | 101 modules | (재실행 생략 — schema.d.ts diff가 additive 16줄이고 tsc 오류 0 확인) | — |

passed/skipped는 정확히 일치. subtests 수가 work_log/사용자 메시지보다 **실측이 4개 많다**(305 vs 309). passed/skipped가 동일한데 subtests만 다른 것은 보고 시점·collection 순서 차이일 수 있으나, 검증자 실측이 사실이므로 기록해 둔다(H4).

## Issues / Risks

### Blocking (계약 의무)

**B-1 — "read 상한 무관" should-NOT-fire 분기의 regression test 부재 (행 13 empty cell).**

- **계약 근거**: SoT changelog (d) "환경별 상한의 authority는 HTTP validator" + W0 schema `$comment`(line 57) "HTTP validation is authoritative" + work_log Decisions(명시) "상한은 write 경계에만 적용한다... response model/read adapter는 기존 값을 그대로 허용한다." 이 세 곳이 합쳐 **"운영자가 env 상한을 낮춰도 이미 저장된 append-only version의 read는 거부되지 않는다"**는 should-NOT-fire 분기를 계약화한다.
- **코드 구현**: 올바르다 — `ProjectBriefVersionPayload`(main.py:990-998, response model)에는 `enforce_style_example_limits`가 **없고** `PutProjectBriefRequest`(write)에만 있다. 따라서 현재 read는 상한에 영향받지 않는다.
- **empty cell**: env limit 변수를 참조하는 테스트는 `tests/test_project_brief.py` 단 하나뿐이고, 그 안에서도 env를 **상향**(4/1001)해 write 허용을 검증하는 것만 있다. env를 **하향**(1/1)한 뒤 이미 3개/1000자가 저장된 brief의 `GET`/`PUT` response가 여전히 그 값을 반환하는지 검증하는 regression test가 **없다**.
- **왜 blocking인가**: 이 분기가 계약(schema $comment + work_log 명시)에 존재함에도 regression이 없다. 누군가 `ProjectBriefVersionPayload`에 `enforce_style_example_limits`를 "write와 대칭으로" 추가하는 자연스러운 실수를 하면, 운영자가 `PROJECT_BRIEF_STYLE_EXAMPLES_MAX_ITEMS`를 1로 낮추는 순간 과거에 3개 예시로 저장된 모든 brief의 `GET`/`PUT` 응답이 500으로 깨지는데, 현재 어떤 테스트도 이 over-strict regression을 잡지 못한다. CLAUDE.md §5 "over-strict guards exist for every should NOT fire branch" + "An untraced contract-required branch is a blocking finding regardless of the green bar." 해석의 여지가 SoT changego (d)의 "간접성"에 있으나, schema `$comment` + work_log 명시가 합쳐져 분기는 성립하므로 보수적으로 blocking으로 둔다.
- **해결 방향(오너 선택)**: (a) regression test 추가 — env 하향 + 3개 예시 저장 brief의 GET이 200 + 3개 반환 pin; 그리고 SoT changelog 또는 W0-contract §1에 "read 경계는 runtime 상한을 적용하지 않는다"를 명시적 driving clause로 올려 ambiguity를 닫는다. 또는 (b) 오너가 "read도 동일 상한을 적용한다"로 결정하면 코드 변경(response model에 limit 추가)이 필요하나 append-only 이력 read가 깨지므로 비권장. 또는 (c) "구현 디테일로 계약화 불필요" 결정 시에도 최소 regression test는 권장.

### Hardening recommendations (non-blocking)

- **H1 — env `..._MAX_CHARS` < 1 거부의 명시적 subTest 부재(행 7)**. `test_invalid_style_example_limit_fails_app_creation`는 `..._MAX_ITEMS=0`만 다룬다. `_project_brief_style_example_limits`(main.py:971-975)가 같은 `for` 루프로 두 값을 검사하므로 동작은 올바르나, 루프에서 `max_chars` 검사를 빼는 mutation을 잡을 subTest가 없다. `..._MAX_CHARS=0` subTest 추가 권장.
- **H2 — env 비숫자 거부의 명시적 테스트 부재(행 8)**. `_env_int`의 `int(raw)`(main.py:481)가 비숫자에 raise하므로 기동 실패는 올바르나, 명시적 regression이 없다. `WRITING_LOOP_MAX_*` 선례와 동형이라 낮은 우선순위. (참고: 작업 AI work_log는 다른 슬라이스(scratch)에서는 non-numeric 거부 subTest를 추가한 선례가 있어, 일관성을 위해 여기서도 두는 것이 깔끔하다.)
- **H3 — W0-contract.md §1이 stale 구 스키마.** SoT line 4(정본 연결)와 decision brief line 4(정본 연결)가 둘 다 `writing-workspace-v2-w0-contract.md (§ProjectBrief)`를 가리키나, 해당 §1(line 49)의 PUT request schema는 여전히 `{base_version_id, idempotency_key, premise, genre, tone, pov, constraints}` — 네 배열이 **없다**. schema file은 `x-contract-version: v1.7.21`로 갱신했는데 plan 문서는 v1.7.10/W2 시점 스키마인 비대칭. SoT changelog가 authority이므로 *동작*은 올바르나, "정본 연결"이 stale 세부 문서를 가리키면 미래 작업자가 "constraints만 required네?"로 오독할 수 있다. W0-contract.md §1에 v1.7.21 확장에 대한 포인터를 추가하거나 "W0(v1.7.10) 시점 exact contract; 문체 배열 확장은 SoT changelog v1.7.21 + schema file 참조"로 명시 권장.
- **H4 — work_log 수치 부정확.** (1) focused suite를 본문(line 310)에서 "46 passed / 20 subtests(최종 exact-key 보강 전 수치)"로 기록 — 실측은 **24 subtests**. "보강 전"이라고 명시는 했으나 최종 수치를 안 적었다. (2) 전체 backend subtests를 305로 보고 — 실측 **309**. passed/skipped(1225/76)는 정확. 수치는 최종 실측으로 기록하는 것이 검증 이력 정확도에 유리.
- **H5 — `reject_normalized_duplicates` 메시지 변경의 영향 범위.** 기존 "constraints must not contain duplicates" → "brief arrays must not contain duplicates"로 바뀌었다(main.py:1196). 이 메시지를 pattern-match하는 소비자가 없는지 전수 확인은 안 했으나, OpenAPI error detail은 안정 literal이 아니므로 회귀상 무해로 판단. 기록만 남긴다.

## Verdict

**조건부 합격 (conditional pass) — 조건: B-1 closure.**

이유:
- 정본 계약(SoT changego v1.7.21 + Owner decisions + W0 schema)의 네 조항(a/b/c/d)이 코드·schema·OpenAPI·prompt·UI에 축자 일치하며 paraphrase가 없다.
- boundary matrix 15행 중 14행이 named regression test로 잠겨 있고, fire 분기 under-strict guard를 mutation(행 3)으로 직접 입증했다.
- 수치 재실측에서 passed/skipped가 정확히 일치(1225/76, frontend 159/11).
- WritingBrief 제거가 dead path(변경 전 런타임 0회)였으므로 동작 회귀 없이 계약 모순이 소멸했다.

그러나 **행 13(read 상한 무관)의 regression test 부재(B-1)**가 contract-required should-NOT-fire 분기의 empty cell이다. 현재 코드는 올바르지만(schema $comment + work_log 명시에 부합), over-strict regression(누군가 response model에 limit를 넣으면 env 하향 시 GET 전체 500)을 잡을 테스트가 없다. CLAUDE.md §5 보수적 기준에 따라 이 분기가 잠길 때까지 conditional pass로 둔다. B-1은 코드 변경 최소(regression test 1건 + SoT/W0-contract 명시 1줄)로 닫을 수 있다.

## Outstanding items

- working tree 전체가 **uncommitted**(사용자 명시). B-1 closure 전까지 커밋 보류 권장.
- B-1 미해결 상태로는 slice close 불가 — 오너가 해결 방향((a)/(b)/(c))을 결정해야 함.
- H1-H4는 non-blocking이나, H3(W0-contract stale)과 H4(수치)는 문서 정합 관점에서 다음 커밋에 함께 정리하면 깔끔하다.

## Reproduction

```bash
# 1. 수치 재실측
python3 -m pytest tests/test_project_brief.py tests/test_writing.py tests/test_core_sot_mongo.py -q -p no:cacheprovider
#   기대: 46 passed, 57 skipped, 24 subtests
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
#   기대: 1225 passed, 76 skipped, 309 subtests
cd frontend && npx vitest run --reporter=dot
#   기대: 159 passed / 11 files

# 2. 행 13 empty cell 확인 (read-path 상한 regression test 부재)
grep -rn "PROJECT_BRIEF_STYLE_EXAMPLE" tests/
#   기대: test_project_brief.py 1파일만, 그 안도 env "상향"(4/1001)뿐

# 3. 행 3 mutation (max_items 무력화 → bite 입증, 수행 후 반드시 복구)
#    services/application/app/main.py:1203 을
#      if False and len(value) > max_items:
#    로 변경 후
python3 -m pytest tests/test_project_brief.py -q -p no:cacheprovider
#    기대: 8 failed (cascading) → 복구 → grep "if False and" 잔여 0 → 20 passed / 15 subtests 재green

# 4. H3 확인 (W0-contract §1 stale)
grep -n "style_examples\|style_rules\|preferred_patterns\|forbidden_patterns" docs/plans/writing-workspace-v2-w0-contract.md
#    기대: 출력 없음 (네 배열이 plan 문서에 침묵)
```

## Closure note — 2026-07-20 B-1 + H1~H4

원 조건부 합격 본문과 판결은 당시 감사 상태로 보존한다. 오너가 권장안 (a)를 승인해 다음과 같이 조건을 닫았다.

- **B-1 closed**: `ProjectBriefApiTest::test_lowered_style_example_limits_do_not_break_existing_reads`가 기본 상한에서 3개 예시를 저장한 뒤 env를 `MAX_ITEMS=1`·`MAX_CHARS=1`로 낮추고 current/history/detail 세 GET의 `200`과 3개 원문 반환을 모두 pin한다. SoT v1.7.21 changelog, decision brief, W0 §1과 schema `$comment`에 runtime 상한은 write-only이며 기존 append-only read에는 적용하지 않는다고 명시했다. boundary matrix의 빈 행 13은 W0 named row **PB-13**으로 채워졌다.
- **B-1 over-strict mutation bite**: `ProjectBriefVersionPayload`에 write 상한 validator를 일시 복사한 자연스러운 과잉 수정에서 PB-13이 `ResponseValidationError`로 즉시 실패했다. mutation을 완전 원복한 뒤 PB-13 `1 passed`, mutation literal 잔여 0을 확인했다.
- **H1/H2 closed**: `MAX_CHARS=0`과 두 env의 non-numeric 값도 app creation `ValueError` subTest로 잠갔다.
- **H3 closed**: W0 §1 field table, PUT exact request, clear/trim clause를 네 배열과 v1.7.21 read boundary로 갱신했다.
- **H4 closed**: 최종 재실측 수치로 work log/HANDOFF/CHANGELOG를 교정했다.
- **H5 assessed, no code change**: duplicate validation detail을 pattern-match하는 저장소 소비자는 0건이며 이 문자열은 안정 public literal이 아니다.

재검증:

- focused backend: `47 passed / 57 skipped / 28 subtests`
- full backend: `1226 passed / 76 skipped / 313 subtests`
- frontend: `159 passed / 11 files`
- OpenAPI/type generation + TypeScript/Vite build: PASS(101 modules)
- `git diff --check`, schema JSON parse, mutation residue `if False and` 0: PASS

**Closure verdict: PASS (조건 없음).** 원 판결의 유일한 blocking B-1과 non-blocking H1~H4가 닫혔고, 15행 boundary matrix에 빈 셀이 없다.
