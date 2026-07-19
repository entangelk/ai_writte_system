# W4 export UI + 회차별 개별 ZIP — 독립 검증

## Subject metadata

- **날짜**: 2026-07-19
- **요청자**: 오너(“다음작업 검증해줘”)
- **검증자**: 독립 검증 AI(Claude, max effort)
- **검증 대상 slice/artifact**: **v1.7.18 — 프로젝트 export UI + 회차별 개별 ZIP bundle**(frontend-only, backend 무변)
- **canonical spec reference**:
  - `docs/plans/writing-workspace-v2-w0-contract.md` §6(W4 export exact contract) — 본 slice에서 **무변**, frontend가 이 계약을 소비
  - `docs/system-contract-sot.md` v1.7.18 changelog
  - 단일 version export 선례(`export_draft_version`, `DraftVersionExportResponse`) — ZIP이 per-unit 본문 취득에 재사용
- **작업 출처**: commit **`e508f83`**(확정). 직전 커밋 `1d4d1c5`(W4 backend, v1.7.17).

## Scope

본 slice는 frontend 전용이므로, 검증은 “backend가 정말 무변인가 + frontend가 기존 계약을 올바르게 소비하는가 + ZIP bundle이 올바른가”에 집중한다. W4 backend 계약 자체는 이미 `docs/verifications/2026-07-19/w4_project_export.md`에서 PASS시켰다.

1. **커밋 범위** — `e508f83`이 frontend + docs만인지(`services/` 0)
2. **client 계약 소비** — `frontend/src/api/client.ts::exportProject`(W4 query param 준수)
3. **DraftList 구현** — `frontend/src/drafts/DraftList.tsx`(combined download, ZIP bundle, 동시실행 가드, 0원고 숨김)
4. **회귀 테스트** — `frontend/src/drafts/DraftList.test.tsx`(+4)
5. **정량 재현** — frontend full test/build/gen:api
6. **의존성** — `jszip@^3.10.1`(package.json/lock 정합)
7. **정본 일관성** — SoT v1.7.17→v1.7.18 changelog, EX-13 보강(직전 slice) 추적

## Methodology

“코드를 먼저 보지 않고 계약을 먼저 읽는다.” 우선 W4 backend 계약(§6)과 단일 version export 선례를 lock list로 세우고, frontend가 그걸 어떻게 소비하는지 추적했다. 작업 AI의 모든 주장(“backend 무변”·“실제 zip 언팩”·“양방향 가드”·“verbatim”)을 전제하지 않고 primary source에서 재도출.

```bash
git show --stat e508f83                          # backend 무변 확인(services/ 0)
git show e508f83 -- frontend/src/api/client.ts frontend/src/drafts/DraftList.tsx frontend/src/drafts/DraftList.test.tsx
cd frontend && npm test -- --run                  # 150/10 재현
npm run build                                     # 388.62 kB 재현
npm run gen:api && diff /tmp/before.d.ts src/api/schema.d.ts   # byte-identical
git diff HEAD --check                             # 제어문자/whitespace 0
```

**under-strict guard = mutation testing**: 각 결함을 `Edit`로 넣고 관련 테스트만 실행 → bite 확인 → `git checkout -- src/drafts/DraftList.tsx`로 원복 → `git diff --stat`/grep으로 0 residual 확인. 4종 mutation(M1~M4).

## Findings

### F1. 커밋 범위 — backend 무변 확정

`e508f83` stat: `CHANGELOG.md`, `HANDOFF.md`, `docs/daily_logs/...`, `docs/system-contract-sot.md`, `frontend/package-lock.json`, `frontend/package.json`, `frontend/src/api/client.ts`, `frontend/src/drafts/DraftList.test.tsx`, `frontend/src/drafts/DraftList.tsx`, `frontend/src/styles.css`. **`services/**` 0건**. 작업 AI “backend 무변” 주장 확인. `gen:api` 재실행 결과 `schema.d.ts`가 byte-identical → OpenAPI/정본 무변 교차 검증.

### F2. client 계약 소비 — W4 §6 준수

`client.ts::exportProject(projectId, format, {manifest?, includeArchived?})`:
- query = `{format}`, `options.manifest` truthy일 때만 `manifest=true`, `options.includeArchived` truthy일 때만 `include_archived=true` set.
- 즉 **기본 manifest=null, include_archived=false** → W4 §6.1/§6.4 default와 정확히 일치. (제 W4 검증에서 잠근 계약 준수.)

### F3. DraftList 구현 — combined / bundle / 가드

`runExport(kind, format)`:
- **combined**: `exportProject(projectId, format)` → `Blob([exported.body], {type: exported.content_type})`, filename = `exported.filename`(backend가 `{project_id}.{ext}` 생성). heading 합성 없이 backend body를 그대로 다운로드.
- **bundle(ZIP)**: `exportProject(projectId, format, {manifest: true})`로 delivery manifest 취득 → `manifest === null` 가드 → 각 `unit`에 대해 `exportDraftVersion(projectId, unit.draft_id, unit.version_id, format)`로 **per-unit verbatim 본문**(단일 version export는 heading 합성 없이 `raw_text`만 반환 — 제 W4 검증 F2에서 확인) → `bundleEntryName`으로 entry 추가 + `manifest.json`(backend manifest 그대로 `JSON.stringify`) → `zip.generateAsync({type:"blob"})` → `${projectId}.zip`.
- **이중 동시실행 가드**: `exportingRef`(useRef, 동기적) + `exporting`(state, 렌더) + 4개 버튼 전부 `disabled={exporting !== null}`.
- **0원고 숨김**: `{drafts.length > 0 && (<section export-controls>)}`.
- **보관 제외**: frontend는 include_archived를 set하지 않으므로 backend default(false)가 archived를 제외 → manifest.units에 archived 미포함 → 자동으로 bundle에서도 제외.

`bundleEntryName`: position zero-pad(2) + sanitize(`\/:*?"<>|`→`_`) + 빈 title이면 draft_id fallback + `.{ext}`. 커밋 메시지·주석이 명시한 대로 “presentation concern, not canonical”.

### F4. 회귀 테스트 — real-zip-unpack + 양방향 가드

`DraftList.test.tsx` +4:
- **combined**: 파일명 `p1.txt` 단정 + export hit이 `format=txt` 포함·`manifest=true` **미포함** 단정. (endpoint 소비 패턴 pin.)
- **bundle**: `mockFetch`로 manifest + per-unit 2개 본문 세팅 → `JSZip.loadAsync(blobs.at(-1)!)`로 **실제 zip 언팩** → entry names `["01-1장.md","02-2장.md","manifest.json"]` 단정 + `zip.file("01-1장.md").async("string")` == `"first"`(본문 단정). 작업 AI “실제 zip 언팩해 항목명·본문까지 검증” 주장 **정확**.
- **가드**: pending Promise로 첫 export를 in-flight로 고정 → “내보내는 중…” 버튼·다른 버튼 `toBeDisabled()` 단정 + 두 번째 클릭 후 fetch 횟수 3 유지(차단) + release 후 `toBeEnabled()`(해제). 양방향.
- **빈 project**: `drafts: []` → “TXT로 내보내기”/“Markdown ZIP” 버튼 `toBeNull()` 단정.

### F5. under-strict guard — mutation testing 실증

| mutation | 위치 | bite 결과 |
|---|---|---|
| M1 `{drafts.length > 0 &&`→`{true &&` | DraftList.tsx | **empty-hide**만 실패(버튼 노출) — 1 failed |
| M2 entry `${prefix}-${stem}`→`${stem}` | bundleEntryName | **bundle**만 실패(`2장.md`≠`02-2장.md`) — 1 failed |
| M3 bundle content `exported.body`→`# ${unit.title}\n\n${exported.body}` | zip.file | **bundle**만 실패(`# 1장\n\nfirst`≠`first`) — verbatim 위반 감지 — 1 failed |
| M4 `disabled={exporting !== null}`→`disabled={false}` | 4개 버튼 | **guard**만 실패(`toBeDisabled` not disabled) — 1 failed |

모든 mutation이 정확히 자기 clause만 bite. 각 mutation 후 `git checkout` 원복 + `git diff --stat`/grep 0 residual 확인. M3은 특히 “ZIP에 heading 합성 없이 verbatim” 계약을 직접 공격해 잡았다.

### F6. 정량 주장 독립 재현

| 주장 | 재현 |
|---|---|
| frontend **150 passed / 10 files** | ✅ 일치 |
| build **JS 388.62 kB**(JSZip) | ✅ 일치 |
| gen:api **byte-identical** | ✅ 일치(schema.d.ts regen 후 동일) |
| `jszip@^3.10.1` 추가 | ✅ package.json/lock 정합 |
| `git diff --check` clean | ✅ 제어문자/whitespace 0 |

직전 v1.7.17의 146 passed + 신규 4 = 150. 산술 정합.

### F7. 정본 일관성 — EX-13 보강 추적

제 직전 W4 검증(`w4_project_export.md`) H4(빈 project body="" 명시 회귀 부재)를 반영해, 직전 커밋 `1d4d1c5`에서 **EX-13**(`test_empty_project_returns_empty_body`, not-fire)이 §4 matrix에 추가됐고 SoT v1.7.17 changelog가 “오너 독립 검증 PASS(조건 없음) 뒤 §6.3 빈-body clause 빈 셀을 EX-13으로 보강”이라 명시. backend **1198 passed**(1197 + EX-13). 본 v1.7.18 slice는 이 위에 frontend를 얹었고, 정본 changelog가 구현과 정합.

## Issues / Risks

### Blocking(contract obligations)

**없음.** 본 slice는 frontend-only이며 backend 계약(§6)을 변경하지 않고 올바르게 소비한다. frontend 동작 경계(combined/bundle TXT·MD, 0원고 숨김, 동시실행 가드, entry 이름, verbatim 본문)가 전부 named 회귀로 채워졌고 under-strict guard가 mutation으로 검증됐다. backend 무변을 commit stat과 gen:api byte-identical로 이중 확인.

### Hardening recommendations(non-blocking)

- **H1 — `exportingRef` ref 가드의 독립 검증 부재**. M4(disabled 제거)에서 `toBeDisabled()`가 먼저 bite했지, ref 자체가 테스트에 직접 노출되지는 않는다. disabled(state)가 load-bearing이고 ref는 safety net(belt-and-suspenders). 사용자 경험 보호는 disabled로 충분하므로 계약 위반 아님. 권고: disabled를 bypass하는 경로(예: 키보드 직접 submit)를 가정한 ref-only 회귀가 있으면 안전망을 독립적으로 pin.
- **H2 — combined 테스트 blob content 미검증**. combined는 파일명 + endpoint 소비 패턴만 검증하고, `Blob`의 content/body를 직접 단정하지 않는다. bundle은 본문까지 단정하므로 대칭이 약간 어긋난다. 권고: combined blob text/content_type 직접 단정.
- **H3 — `bundleEntryName` sanitize·fallback 미검증**. happy-path title(`1장`/`2장`)만. `\/:*?"<>|`→`_` 치환과 빈 title→draft_id fallback이 회귀로 없다. 파일명에 path-separator가 들어오는 입력에서 의미.
- **H4 — archived-only project edge**. `drafts.length > 0`(archived draft만)이면 export 컨트롤은 표시되지만 backend export는 archived를 제외해 **빈 body/빈 ZIP**이 된다. UI 표시 기준(drafts)과 실제 export 기준(backend non-archived)이 희귀 케이스에서 어긋난다. 권고: non-archived draft 수로 숨김 기준을 맞추거나, 빈 결과 시 안내.
- **H5 — 0-unit manifest edge**. drafts는 있지만 version 없는 unit만으로 manifest.units가 빈 배열이면 ZIP은 manifest.json만(항목 0)이 된다. EX-13(빈 body)의 frontend 대응이 별도로 없다.

## Verdict

**PASS(조건 없음).**

근거(load-bearing):
1. **backend 무변** — `e508f83`이 frontend + docs만(`services/` 0), `gen:api` 재실행이 `schema.d.ts` byte-identical. W4 §6 계약은 본 slice에서 변경되지 않았고(이미 `w4_project_export.md`에서 PASS), frontend가 그 계약을 올바르게 소비한다(client 기본 manifest=null/include_archived=false).
2. **frontend 동작 경계가 named 회귀로 충원** — combined/bundle TXT·MD, 0원고 숨김, 동시실행 가드 양방향, real-zip-unpack(entry 이름+본문).
3. **under-strict guard mutation 실증** — M1~M4 각각 정확한 clause만 bite. 특히 M3이 “ZIP verbatim, heading 합성 없음” 계약을 직접 공격해 잡음.
4. **정량 주장 전부 독립 재현** — 150/10, 388.62 kB, gen:api byte-identical, jszip ^3.10.1 정합, 제어문자 0.
5. **정본 일관성** — 제 직전 검증 H4가 EX-13으로 보강된 흔적(1d4d1c5) 추적 완료.

“green bar ≠ 계약 검증” 구분: F5 mutation이 단순 통과를 넘어 각 테스트의 pin 의미를 입증했다. Hardening H1~H5는 계약 요구가 아니므로 verdict에 영향 없다.

## Outstanding items

- **다음 code slice는 오너 결정**(작업 AI가 HANDOFF에 기록): (a) export의 `include_archived` 토글 UI, (b) 통합 파일에도 manifest 동시 제공, (c) Deferred(미채택 candidate 영속 등 — brief 선행).
- **H1~H5 반영 여부**: 오너 판단. H2~H5는 테스트만, H1도 테스트만(production 코드 무변 가능).
- 본 slice는 이미 `e508f83`으로 커밋 확정됨.

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system

# 1. backend 무변 확인 (services/ 0건이어야 함)
git show --stat e508f83 | grep -E "services/|frontend/"

# 2. 정량 재현
cd frontend
npm test -- --run                       # expect: 150 passed/10 files
npm run build                            # expect: JS 388.62 kB
cp src/api/schema.d.ts /tmp/before.d.ts && npm run gen:api && diff /tmp/before.d.ts src/api/schema.d.ts  # expect: identical
cd .. && git diff HEAD --check           # expect: clean

# 3. under-strict guard(mutation) — Edit로 결함 적용 후 focused 실행, bite 확인, git checkout 원복
#    M1: {drafts.length > 0 && → {true &&           → "hides export controls" 실패
#    M2: bundleEntryName `${prefix}-${stem}`→`${stem}` → "bundles each unit" 실패
#    M3: zip.file content exported.body → `# ${unit.title}\n\n${exported.body}` → "bundles each unit" 실패
#    M4: disabled={exporting !== null} → disabled={false} (×4) → "does not start a second export" 실패
```
