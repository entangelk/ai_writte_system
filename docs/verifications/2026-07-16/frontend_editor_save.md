# 독립 검증 — Frontend editor/save A1 슬라이스 (SoT v1.6.98)

## Subject metadata

- **날짜**: 2026-07-16
- **요청자**: 오너 (“다음작업 검증해줘. A1 editor/save slice를 완료했습니다.”)
- **검증자**: 독립 검증 AI (Claude Code)
- **대상 슬라이스/산출물**: Product shell A1 — `/projects/:projectId/drafts/:draftId` editor route + 원고 행 deep link, latest/empty 본문 load, 평문 textarea, 명시적 save(`idempotency_key` UUID + exact 본문 결박), unchanged-suppress / nonempty→empty 허용, in-flight 중복 방지, archive/409 read-only.
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.6.98(버전 로그 행), `docs/plans/frontend-editor-save-decisions.md` D1=A(idempotency 수명 lock)·D2=A·D3=A + “선택 후 A1 code slice” #4-5(구현 lock list) + D1 implementation locks, `product-shell.md`.
- **검증 대상 작업 출처**: working tree, uncommitted. 신규 `frontend/src/drafts/DraftEditor.tsx`·`DraftEditor.test.tsx`(untracked), 변경 `App.tsx`·`App.test.tsx`·`api/client.ts`·`drafts/DraftList.tsx`·`DraftList.test.tsx`·`styles.css` + 문서. 백엔드 `services/`·`tests/`·`scripts/`·`docker-compose.yml` diff 0.

## Scope

결정 브리프가 **이 slice의 lock list**로 명시한 표면 전부와 그 전제(백엔드 무변·Core SOT 멱등 계약 정합)를 1차 소스에서 재도출한다.

1. **정본 계약(소비 면)**: SoT v1.6.98 행, 브리프 D1 implementation locks + A1 #4-5 회귀 항목.
2. **백엔드 계약(공급 면)**: editor가 호출하는 4 endpoint(`getDraft`/`listDraftVersions`/`getDraftVersion`/`saveDraft`) 실제 존재·`response_model`·오류 코드, 그리고 **`core_sot.save_draft`의 멱등 의미**(브리프가 “key에 바뀐 본문을 보내면 최초 version이 replay된다”로 명시한 핵심 계약).
3. **구현 코드**: `DraftEditor.tsx`(load/submit/idempotency intent lifecycle), `App.tsx`(editor route), `DraftList.tsx`(링크), `client.ts`(4 함수 추가).
4. **회귀 테스트**: `DraftEditor.test.tsx`(13) + 기존(App 4·DraftList 9·ProjectList 10) — 총 36.
5. **스키마 동기화**: `gen:api` 재생성 불변.
6. **정량 주장 재현**: 36/4 · build 90 modules · schema IDENTICAL · `git diff --check` clean.

## Methodology

정본·구현을 “읽어서” 맞다고 치지 않고, 각 표면을 실행·재계산했다.

- 회귀: `cd frontend && npm test` 및 `./node_modules/.bin/vitest run` (vitest 3.2.7, jsdom).
- 빌드/타입: `cd frontend && npm run build` (`tsc --noEmit && vite build`).
- OpenAPI 재생성 불변: `cp src/api/schema.d.ts /tmp/schema_a1.d.ts && npm run gen:api && diff /tmp/schema_a1.d.ts src/api/schema.d.ts` → IDENTICAL, 복원.
- 백엔드 무변: `git diff --stat -- services/ tests/ scripts/ docker-compose.yml` (빈).
- 백엔드 멱등 의미: `services/application/app/core_sot/service.py:310-369` `save_draft` 본문 직독.
- 코드 계약 정합: `main.py` route 선언과 `client.ts` URL 대조.
- **결함 실증(repro)**: 임시 테스트 `DraftEditor.race_repro.test.tsx`를 작성해 “저장 in-flight 중 타이핑이 보존되는가”를 단언 → 원본 코드에서 **실패** 관측 → `DraftEditor.tsx:124` 제거 mutation으로 **통과** 확인 + 기존 36개 green 유지 → mutation·repro를 모두 **원복/삭제**(검증자는 fix를 남기지 않음).

**라이브 관통 smoke은 본 검증에서 재실행하지 않았다.** 단위 테스트가 fetch URL·method·body·idempotency key·응답 소비를 pin 하고 백엔드 멱등 의미를 소스에서 직접 확인해 간접 증명했다.

## Boundary matrix (lock list)

브리프 D1 locks + A1 #4-5의 계약 요구 분기를 1차 소스에서 추출해 named test로 추적. **빈 셀 없음.**

| # | 계약 요구 분기 (브리프) | 잠근 테스트 (file:행) | 방향 |
|---|---|---|---|
| 1 | 원고 행 → `/projects/:pid/drafts/:did` deep link | `DraftList.test.tsx:58` href exact | under |
| 2 | editor route + direct URL project/draft 격리 | `DraftEditor.test.tsx:67` fetch 경로 exact; `App.test.tsx` editor route(+1) | under |
| 3 | 0-version → 빈 editor, save 비활성(unchanged 미전송) | `DraftEditor.test.tsx:55` | under+over |
| 4 | 최신(max `version_number`) detail exact `raw_text` | `DraftEditor.test.tsx:74` | under |
| 5 | Save exact body·URL·새 version baseline 채택 | `DraftEditor.test.tsx:104` | under |
| 6 | unchanged suppression(accidental mint 방지) | `DraftEditor.test.tsx:135` 저장 후 `fireEvent.submit` → fetch 4회(증가 없음) | under |
| 7 | nonempty→empty dirty save **허용** | `DraftEditor.test.tsx:141` body `raw_text:""` | over-strict |
| 8 | in-flight 중복 submit → 1 POST(ref 동기 write-lock) | `DraftEditor.test.tsx:177` | under |
| 9 | ambiguous(5xx) 동일 본문 → **같은 key 재사용** | `DraftEditor.test.tsx:234` `intent-1` | under |
| 10 | 실패 후 본문 변경 → **새 key**(stale key 재사용 금지) | `DraftEditor.test.tsx:240` `intent-2` | over-strict |
| 11 | `idempotent_replay=true` → 새 version 아님 UI(“재확인됨”) + intent 폐기 | `DraftEditor.test.tsx:239` + 이후 새 key | under |
| 12 | archived project/draft → 처음부터 read-only·Save 숨김 | `DraftEditor.test.tsx:267`(param×2) | over-strict |
| 13 | save **409** → 입력 보존 + read-only 전환 | `DraftEditor.test.tsx:246` | under |
| 14 | 확정적 404 → 본문 보존 + 재시도 시 **새 key** | `DraftEditor.test.tsx:325` `intent-1`→`intent-2` | under+over |
| 15 | list/detail/save 404 → 오류, 타 원고 본문 미노출 | `DraftEditor.test.tsx:288`(param×2)·`:312` | under |
| 16 | intent key가 exact payload에 결박(`crypto.randomUUID`) | `DraftEditor.test.tsx:129` body `idempotency_key:"intent-1"` | under |

모든 계약 요구 분기가 named test로 trace된다. **boundary matrix에 빈 셀 없음 = 계약 자체는 완전히 잠김.**

## Findings

### 1. 정본 계약(소비 면) — PASS
SoT v1.6.98 행과 브리프 D1=A·D2=A·D3=A + A1 lock list가 구현과 1:1. 계약 내부 모순 없음.

### 2. 백엔드 계약·멱등 의미 — PASS (핵심)
- editor 호출 4 endpoint 실재(전부 `response_model` 부착): `GET /drafts/{did}`(`main.py:1502`)·`GET .../versions`(`:1513`)·`GET .../versions/{vid}`(`:1526`)·`POST .../versions`(`:1610`).
- save 오류 매핑: NotFound→404·Archived→409·CoreSotError→400(`main.py:1623-1628`). 프론트 `DEFINITIVE_SAVE_FAILURES={400,404,409,422}`(422=pydantic 검증)와 정합.
- **`core_sot.save_draft` 멱등(`service.py:322-326`)**: `find_save_request(project,draft,key)`로 key 단독 조회 → hit 시 **본문 비교 없이** 최초 version을 `idempotent_replay=True` 반환. 동시성 race까지 `DuplicateSaveRequest`(`:358-363`)로 방어.
  - **이것이 프론트 D1 가드를 load-bearing로 만든다**: 서버는 key만 보고 dedup하므로, 프론트가 “바뀐 본문에 같은 key”를 보내면 **새 본문이 조용히 무시되고 최초 version이 replay**된다(=silent data loss). 프론트의 `intentRef.current?.rawText === rawText` 가드(`DraftEditor.tsx:114`)가 이를 막고, 행 #10 테스트가 그 가드를 pin 한다. 계약이 정확히 맞물림.

### 3. 백엔드 무변 — PASS
`git diff --stat -- services/ tests/ scripts/ docker-compose.yml` → 빈. Core SOT 계약 무변 주장 확인.

### 4. 회귀 테스트 — PASS (코드 감사 포함)
`npm test` → **36 passed / 4 files**(DraftEditor 13·App 4·DraftList 9·ProjectList 10). 각 테스트를 읽어 (a) 계약 pin (b) under-strict (c) over-strict (d) 경계값 (e) 공개 표면 단언 기준 충족. 특히 행 #8 in-flight 테스트는 `fireEvent.submit`로 버튼 disabled를 우회해 `savingRef` write-lock을 직접 pin(work_log 이슈에서 작업자가 의식적으로 ref를 둔 이유와 일치), 행 #9/#10이 idempotency key lifecycle 양방향을 잠근다.

### 5. 스키마 동기화·정량 — PASS
`gen:api` 재생성 `diff` **IDENTICAL**. build **90 modules**(CSS 5.62 kB/gzip 1.79, JS 238.19 kB/gzip 76.18). `git diff --check` clean. 정량 주장 전부 독립 재현.

## Issues / Risks

### Blocking — correctness defect (실증됨)

**B1 — 저장 in-flight 중 타이핑한 본문이 silent data loss된다.** `DraftEditor.tsx:124`의 `setRawText(intent.rawText)`.

- **메커니즘**: textarea는 `saving` 중에도 editable하다(`readOnly`는 archived/forcedReadOnly일 때만 true). 사용자가 Save 클릭 → `await saveDraft(...)` 대기 중 입력 → `onChange`가 `rawText`를 “AB”로. 저장 응답 도착 → `setRawText(intent.rawText)`가 다시 “A”로 되돌려 “B”를 c룹링. `setBaseline("A")`로 `dirty=false`가 돼 “B”는 state·표시 모두에서 영구 소실.
- **실증**: 임시 repro `DraftEditor.race_repro.test.tsx` — “A” 입력→저장 보류→“B” 입력→저장 완료 → `expect(editor).toHaveValue("AB")`. **원본 코드에서 `Expected: AB / Received: A`로 실패**(“B” 소실 관측).
- **root cause 확정**: 동일한 테스트에서 `DraftEditor.tsx:124` 한 줄 제거 시 repro **통과** + 기존 36개 **전부 green**(37/5). 즉 그 줄이 정확히 원인이고 fix는 1줄 제거이며 부수 효과 0.
- **위상**: 이 결함은 **계약 위반이 아니다** — boundary matrix(16행)는 빈 셀 없이 잠겼고 백엔드 멱등 계약과도 정합이다. 그러나 집필 도구의 **핵심 write 경로에서의 silent data loss**이며 현재 untested다. `setRawText(intent.rawText)`는 원래부터 **잉여**(intent.rawText는 항상 저장 시점 rawText와 동일)라, 제거해도 정상 동작이 보존된다.
- **fix(검증자가 적용하지 않음, 원복함)**: `DraftEditor.tsx:124` 제거 + “저장 중 타이핑 보존” 회귀 1개 추가. 또는 저장 중 textarea `readOnly`화.

### Hardening recommendations (비차단)

- **H1**: 행 #11 테스트가 `idempotent_replay=true`를 **새 key(intent-2)+새 본문** mock으로 발생시킨다. 실제 백엔드에서 새 key+새 본문은 항상 `idempotent_replay=false`여야 한다(본문 비교 없이 key만 본다고 해도, 새 key는 미조회→새 version). 표시 분기(“재활인됨”)만 고립시키려는 합리적 설계이나 시나리오가 비현실적 — 회귀가 “재확인됨” 표시 자체를 pin하므로 결함은 아니다.
- **H2**: 최신 version 선택이 client-side `max(version_number)`(`DraftEditor.tsx:55-61`). `list_draft_versions`이 현재 전체를 반환해 정상이나, 향후 cap/pagination이 붙으면 silent break. 작업자도 work_log 이슈에 명시한已知 사항. 코멘트/후속 권장.
- **H3**: `beforeunload` dirty 경고(`DraftEditor.tsx:90-97`)가 jsdom 한계로 미검증. 안전망일 뿐이라 비차단.

## Verdict

**CONDITIONAL PASS.**

- **계약은 완전히 충족**: boundary matrix 16행 빈 셀 없음(브리프 D1 locks + A1 #4-5 전부 named test로 양방향 pin), 백엔드 무변, Core SOT 멱등 계약과 프론트 D1 가드 정합, 정량 주장(36/4·build 90·schema IDENTICAL·diff --check) 전부 독립 재현.
- **조건(명시)**: **B1 — 저장 in-flight 타이핑 silent data-loss race**를 fix(`DraftEditor.tsx:124` 제거, 1줄·부수효과 0·실증 완료)하거나, 오너가 이 위상을 의식적으로 수용할 것. 집필 도구 핵심 write 경로의 데이터 손실이므로 commit 전 결정을 권장한다. 이 조건은 contract gap이 아니라 contract를 넘는 correctness 결함에 대한 것이다.

## Outstanding items

- **커밋 대기**: 본 슬라이스는 working tree에 uncommitted(`DraftEditor.tsx`/`.test.tsx`는 untracked 신규). B1 결정(수리/수용) 후 커밋.
- **검증자가 남긴 변경**: 없음. fix mutation과 repro 테스트는 모두 원복/삭제했고, working tree는 작업자 상태 + 이 검증 기록만 추가.
- **라이브 smoke 미재실행**: 단위·빌드·소스 증거로 대체(방법론에 명시).
- **다음 slice A2**: version history 선택·dirty 전환 확인·txt/Markdown export.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
(cd frontend && npm test)                                          # 36 passed / 4 files
(cd frontend && npm run build)                                     # 90 modules, exit 0
cp frontend/src/api/schema.d.ts /tmp/schema_a1.d.ts
(cd frontend && npm run gen:api) && diff /tmp/schema_a1.d.ts frontend/src/api/schema.d.ts  # IDENTICAL
cp /tmp/schema_a1.d.ts frontend/src/api/schema.d.ts               # 복원
git diff --stat -- services/ tests/ scripts/ docker-compose.yml   # 빈
git diff --check                                                   # clean

# B1 결함 재현(검증자가 사용한 임시 repro — 기록용, tree에 남기지 않음):
# 1) frontend/src/drafts/DraftEditor.race_repro.test.tsx 작성
#    (빈 draft → "A" 입력 → 저장 보류 → "B" 입력 → 저장 완료 → editor 값 "AB" 단언)
# 2) (cd frontend && ./node_modules/.bin/vitest run src/drafts/DraftEditor.race_repro.test.tsx)
#    → 원본: FAIL (Received: "A") / DraftEditor.tsx:124 제거 후: PASS + 기존 36 green
```

## Post-verification disposition (Codex, owner-requested follow-up)

- **B1 closed**: 오너가 수리를 지시했다. `DraftEditor.tsx`의 저장 성공 경로에서 `setRawText(intent.rawText)`를 제거해 응답이 저장 시점 이후의 현재 편집값을 덮지 않게 했다. 전용 회귀 `preserves edits typed while a save is in flight`가 원본에서 **Expected AB / Received A**로 red인 것을 재현한 뒤 수정 후 green을 확인했다. 회귀는 요청 body가 저장 시점 `"A"`, textarea가 최신 `"AB"`, Save가 다시 enabled임을 함께 단언해 저장 baseline과 현재 편집값의 분리를 양방향으로 잠근다.
- **H1 closed**: 비현실적인 `새 key+새 본문+idempotent_replay=true` mock을 제거했다. changed-body/new-key 회귀는 `idempotent_replay=false`로 정정하고, 별도 회귀가 5xx 뒤 **동일 key+동일 본문** 재시도에서만 `idempotent_replay=true`와 “재확인됨” 표시를 검증한다.
- **H3 closed**: cancelable `beforeunload` event를 직접 dispatch해 dirty 상태에서는 `defaultPrevented=true`, 성공 저장 후 clean 상태에서는 `false`인 양방향 회귀를 추가했다.
- **H2 deferred by trigger**: 현재 API는 전체 version 목록을 반환하므로 client-side max가 정확하다. pagination/cap 도입 시 latest 선택 권한을 서버 계약과 함께 재검토하며, 존재하지 않는 미래 pagination을 위해 현재 코드를 늘리지 않는다.

후속 검증은 `DraftEditor` **16 passed**, 전체 프론트 **39 passed / 4 files**, build **90 modules**, `gen:api` IDENTICAL, backend 범위 diff 0, `git diff --check` clean이다. 원 독립 검증의 역사적 판정은 CONDITIONAL PASS로 보존하지만, 명시된 유일 조건 B1은 폐쇄되어 **현재 작업 트리는 commit-ready**다. 상세는 `docs/daily_logs/2026-07-16/work_log.md` Task 8에 기록한다.
