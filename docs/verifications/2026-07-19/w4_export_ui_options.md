# W4 export UI 옵션화 (include_archived + manifest 토글) — 독립 검증

## Subject metadata

- **날짜**: 2026-07-19
- **요청자**: 오너(“다음 작업 검증해줘”)
- **검증자**: 독립 검증 AI(Claude, max effort)
- **검증 대상 slice/artifact**: **v1.7.19 — export UI 옵션화**(include_archived 토글 + manifest 토글, frontend-only, backend 무변)
- **canonical spec reference**:
  - `docs/plans/writing-workspace-v2-w0-contract.md` §6(W4 export exact contract) — 본 slice에서 **무변**, frontend가 `?include_archived`/`?manifest` 소비
  - `docs/system-contract-sot.md` v1.7.19 changelog
  - `docs/verifications/2026-07-19/w4_export_frontend_zip.md`(직전 v1.7.18 검증) — 본 slice의 **행동 변경**이 이 기록의 단정과 어떻게 관련되는지 추적
- **작업 출처**: commit **`a07995c`**(확정). 직전 커밋 `231ec99`(직전 검증 H2/H3/H4 hardening), `e508f83`(v1.7.18).

## Scope

본 slice는 v1.7.18 export UI의 **행동을 변경**한다(bundle manifest always-on → opt-in; archived-only 숨김 → disable+토글). 따라서 검증은 (1) 행동 변경이 투명하게 문서화됐는지, (2) opt-in 양방향·escape hatch가 named 회귀로 pin됐는지, (3) under-strict guard가 mutation으로 입증되는지에 집중한다.

1. **커밋 범위** — `a07995c`가 frontend + docs만(`services/` 0)
2. **정본 일관성** — v1.7.18 → v1.7.19 행동 변경(bundle opt-in, archived 재게이팅)의 SoT/work_log 명시
3. **DraftList 구현** — `frontend/src/drafts/DraftList.tsx`(두 토글, canExport, combined 2파일 manifest, bundle opt-in manifest)
4. **회귀 테스트** — `frontend/src/drafts/DraftList.test.tsx`(+3 신규, 기존 갱신)
5. **정량 재현** — 155/10, build, tsc, gen:api
6. **under-strict guard** — mutation testing(M1~M3)
7. **직전 검증 hardening 반영 추적** — 231ec99가 H2/H3/H4를 어떻게 다뤘는지

## Methodology

“코드를 먼저 보지 않고 계약을 먼저 읽는다.” W4 §6 backend 계약(무변)을 lock list로 세우고, frontend의 새 옵션 경계가 그 계약을 어떻게 소비하는지 추적. 행동 변경(bundle always-on→opt-in)은 직전 v1.7.18 검증 기록과 대조해 후퇴(regression)가 아닌 의도된 재설계임을 입증.

```bash
git show --stat a07995c                    # services/ 0 확인
git show a07995c -- docs/system-contract-sot.md docs/daily_logs/2026-07-19/work_log.md   # 행동 변경 명시 확인
git show a07995c -- frontend/src/drafts/DraftList.tsx frontend/src/drafts/DraftList.test.tsx
cd frontend && npm test -- --run            # 155/10
npm run build                               # 389.54 kB
npx tsc --noEmit                            # exit 0
npm run gen:api && diff /tmp/before.d.ts src/api/schema.d.ts   # byte-identical
```

**under-strict guard = mutation testing**: `Edit`로 결함 삽입 → 관련 테스트만 실행 → bite 확인 → `git checkout -- src/drafts/DraftList.tsx` 원복 → `git diff --stat`/grep으로 0 residual. M1~M3.

## Findings

### F1. 커밋 범위 — backend 무변 확정

`a07995c` stat: `CHANGELOG.md`, `HANDOFF.md`, `docs/daily_logs/...`, `docs/system-contract-sot.md`, `frontend/src/drafts/DraftList.test.tsx`, `frontend/src/drafts/DraftList.tsx`, `frontend/src/styles.css`. **`services/**` 0건**. `gen:api` 재실행이 `schema.d.ts` byte-identical → backend/OpenAPI 무변 교차 검증. “backend 무변” 주장 확인.

### F2. 정본 일관성 — 행동 변경 투명 명시 (핵심)

본 slice는 v1.7.18의 두 동작을 **변경**한다. SoT v1.7.19 changelog와 work_log가 이를 투명하게 기록:

- **bundle manifest.json: v1.7.18 always-on → v1.7.19 opt-in**. SoT: “bundle의 manifest.json을 v1.7.18 always-on에서 opt-in으로 변경해 두 export가 한 토글로 일관된다”. work_log: “v1.7.18 검증 기록의 ‘zip에 manifest.json 항상 포함’ 단정은 그 시점 동작의 역사 기록으로 남는다”. — 직전 검증(`w4_export_frontend_zip.md`)의 단정이 역사 기록으로 명시됨. **정본 모순 없음**.
- **archived-only gating: v1.7.18 숨김 → disable + 토글**. SoT: “archived-only project gating 재정의: v1.7.18 ‘컨트롤 숨김’(H4) → ‘컨트롤 표시 + 내보낼 unit 0이면 버튼 disable + 토글로 활성화’(빈 export 방지 의도는 disable로 보존, 토글이 탈출구)”. `canExport = drafts.some(includeArchived || !archived)` 공식까지 명시.

CHANGELOG v1.7.18 행은 시점 기록으로 보존(HANDOFF는 v1.7.18/19 export 항목을 하나의 현재-상태 bullet로 통합). 이는 CLAUDE.md “HANDOFF는 스냅샷, 모순 방지” 원칙과 정합.

### F3. DraftList 구현 — 두 토글 + canExport

`runExport`:
- **combined**: `exportProject(projectId, format, { includeArchived, manifest: withManifest })`. body 다운로드 후, `if (withManifest && exported.manifest !== null)` → 별도 `{projectId}.manifest.json`(application/json) 다운로드. 즉 withManifest on = body + manifest 2파일.
- **bundle**: `exportProject(projectId, format, { includeArchived, manifest: true })`(unit 열거용으로 항상 manifest 요청) → `if (withManifest)`일 때만 `zip.file("manifest.json", ...)` 추가(opt-in).

`canExport = drafts !== null && drafts.some((draft) => includeArchived || !draft.archived)`:
- includeArchived=false → non-archived 1개 이상 필요
- includeArchived=true → drafts 1개 이상이면 true (archived-only 탈출구)

컨트롤 표시 조건: `{drafts.length > 0 && ...}`(v1.7.18 non-archived 존재에서 변경). 4개 버튼 `disabled={exporting !== null || !canExport}`. include_archived 토글은 `drafts.some(d => d.archived)`일 때만 렌더. note 메시지 3종(canExport/includeArchived 상태별). 모두 계약/주장과 일치.

### F4. 회귀 테스트 — opt-in 양방향 pin + escape hatch

**+3 신규**:
- **“passes include_archived when the archived toggle is on”**: mixedDrafts에서 토글 on → export call이 `include_archived=true` 포함 단정.
- **“downloads a separate manifest file alongside the combined export”**: 토글 on → `downloads == ["p1.txt","p1.manifest.json"]` + manifest blob `type == "application/json"` + `JSON.parse(...).project_id == "p1"`(content까지 단정).
- **“adds manifest.json to the zip when the manifest toggle is on”**: 토글 on → zip files `["01-1장.md","manifest.json"]`.

**기존 갱신**:
- **“bundles each unit...”**: zip files를 `["01-1장.md","02-2장.md"]`로(기본 withManifest=false, manifest.json **없음**).
- **“disables export for an archived-only project until archived units are opted in”**(구 “hides...”): archived-only에서 버튼 `toBeDisabled()` + “내보낼 원고가 없습니다” + 토글 클릭 후 `toBeEnabled()`. **disable + escape 양방향 pin**.
- sanitize 테스트에서 `manifest.json` 제거(opt-in 반영).

**bundle manifest가 양방향으로 pin됨**: 기본(“bundles each unit”)=manifest.json 없음 / 토글(“adds manifest.json...”)=있음. 단순 단정 제거가 아니라 opt-in 양쪽을 모두 잠근다.

### F5. under-strict guard — mutation testing 실증

| mutation | 위치 | bite 결과 |
|---|---|---|
| M1 `if (withManifest)`→`if (true)`(bundle 항상 manifest) | zip.file 블록 | **“bundles each unit”**만 실패(`[…(1)]`≠기대, manifest.json 누출) — opt-in 기본 guard |
| M2 canExport `includeArchived \|\| !archived`→`!archived`(토글 무시) | canExport | **“disables export for archived-only”**만 실패(`toBeEnabled` disabled) — escape hatch guard |
| M3 combined `exportProject(..., {includeArchived, manifest})`→`{manifest}` | combined exportProject | **“passes include_archived”**만 실패(`to contain 'include_archived=true'`) — 전달 guard |

3종 모두 정확히 자기 clause만 bite. 각 mutation 후 `git checkout` 원복 + `git diff --stat` 0 residual 확인.

### F6. 정량 주장 독립 재현

| 주장 | 재현 |
|---|---|
| frontend **155 passed / 10 files** | ✅ 일치 |
| build **JS 389.54 kB** | ✅ 일치(100 modules) |
| `tsc --noEmit` clean | ✅ exit 0 |
| `gen:api` byte-identical | ✅ 일치(schema.d.ts regen 후 동일) |
| `git diff --check` clean | ✅ 제어문자/whitespace 0 |

직전(v1.7.18 + 231ec99) 152 passed + 신규 3 = 155. 산술 정합. DraftList 파일 alone 19 passed(14 + H3/H4 +2 + 본 slice +3).

### F7. 직전 검증 hardening 반영 추적 (231ec99)

`231ec99 test(frontend): harden project export UI after verification (H2/H3/H4)`가 제 직전 검증(`w4_export_frontend_zip.md`)의 hardening을 반영:
- **H3(sanitize/fallback)** → “sanitizes unit titles and falls back to the draft id” 회귀 추가. **해소**.
- **H4(archived-only)** → “hides export controls when every unit is archived”(1차, 숨김) 추가. 이후 본 slice(a07995c)에서 **disable+토글로 재설계**해 완전 해소.
- **H2(combined blob content)** → 본 slice의 “downloads a separate manifest file”이 combined manifest의 content_type + JSON 내용까지 단정. **부분 해소**(body 자체 content는 여전히 파일명 위주).

## Issues / Risks

### Blocking(contract obligations)

**없음.** 본 slice는 frontend-only이며 W4 §6 backend 계약을 무변 소비한다. 새 옵션 경계(include_archived query, combined 2파일 manifest, bundle opt-in manifest, archived-only disable+escape)가 전부 named 회귀로 채워졌고, 행동 변경(bundle opt-in, archived 재게이팅)이 SoT/work_log에 투명하게 명시돼 정본 모순이 없다. under-strict guard가 mutation으로 검증됐다.

### Hardening recommendations(non-blocking)

- **H1 — `exportingRef` ref 가드 독립 검증 부재**(직전 검증에서 지적, 미반영). 여전히 `disabled`(state)가 load-bearing이고 ref는 safety net. 본 slice에서 `disabled` 조건이 `exporting !== null || !canExport`로 확장됐지만 ref 노출 여부는 동일. non-blocking.
- **H2 — combined body 자체 content 미검증**(잔존). “downloads a separate manifest file”이 manifest쪽 content는 단정하지만, combined body blob의 텍스트 자체는 여전히 파일명/endpoint 위주. bundle은 본문까지 단정하므로 대칭이 약간 어긋난다.
- **H5 — version 없는 non-archived unit만 있는 edge**(직전 검증 지적, 미반영). drafts가 non-archived라 `canExport=true`(버튼 enable)지만, 모든 unit이 version이 없으면 backend manifest.units가 빈 배열 → 빈 body / (withManifest 시) manifest-only ZIP. UI 기준(drafts)과 실제 export 기준(backend latest version)이 희귀 케이스에서 어긋난다. list_drafts가 version 존재 여부를 주지 않아 UI 입장 한계. 권고: 빈 결과 안내 메시지.
- **H-new — combined manifest opt-in의 독립 mutation 미실행**. M1(bundle)로 opt-in 패턴은 검증했으나, combined의 `if (withManifest && ...)` 가드 자체는 mutation 대칭 검증을 안 했다. 다만 “downloads the whole project”(기본, `downloads == ["p1.txt"]`)가 항상-2파일 mutation을 잡으므로 실질 보호는 됨.

## Verdict

**PASS(조건 없음).**

근거(load-bearing):
1. **backend 무변** — `a07995c`가 frontend+docs만(`services/` 0), `gen:api` byte-identical.
2. **행동 변경 투명성** — bundle always-on→opt-in, archived 숨김→disable+토글이 SoT v1.7.19 changelog와 work_log에 명시되고, 직전 검증 단정이 역사 기록으로 처리돼 정본 모순 없음.
3. **opt-in 양방향 pin** — bundle manifest가 기본(없음)/토글(있음) 양쪽 named 회귀; archived-only가 disable/escape 양쪽; include_archived query와 combined 2파일 manifest(content까지) 신규 pin. boundary matrix 빈 셀 없음.
4. **under-strict guard mutation 실증** — M1~M3 각각 정확한 clause만 bite.
5. **정량 전부 독립 재현** — 155/10, 389.54 kB, tsc clean, byte-identical, 제어문자 0.
6. **직전 검증 hardening 반영 추적** — 231ec99가 H3(해소)·H4(1차), 본 slice가 H4 재설계(완전 해소)·H2(부분).

“green bar ≠ 계약 검증”: F5 mutation이 각 테스트의 pin 의미를 입증. Hardening H1/H2/H5/H-new는 계약 요구가 아니므로 verdict에 영향 없다.

## Outstanding items

- **다음 slice는 owner brief 필요**(작업 AI가 HANDOFF에 기록): Deferred 중 기본 기능 — (a) 미채택 Writing candidate 영속, (b) saved publication manifest 정본. 둘 다 brief 선행.
- **H1/H2/H5/H-new 반영 여부**: 오너 판단. 전부 테스트만(production 코드 무변)으로 반영 가능.
- 본 slice는 이미 `a07995c`로 커밋 확정.

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system

# 1. backend 무변 (services/ 0)
git show --stat a07995c | grep -c "services/"   # expect: 0

# 2. 행동 변경 명시
git show a07995c -- docs/system-contract-sot.md | grep -i "opt-in\|disable\|canExport"

# 3. 정량 재현
cd frontend
npm test -- --run                       # expect: 155 passed/10 files
npm run build                            # expect: JS 389.54 kB
npx tsc --noEmit                         # expect: exit 0
cp src/api/schema.d.ts /tmp/b.d.ts && npm run gen:api && diff /tmp/b.d.ts src/api/schema.d.ts  # expect: identical
cd .. && git diff HEAD --check           # expect: clean

# 4. under-strict guard(mutation) — Edit 적용 후 focused 실행, bite 확인, git checkout 원복
#    M1: if (withManifest){ zip.file("manifest.json"...) } → if (true){...} → "bundles each unit" 실패
#    M2: canExport ... includeArchived || !draft.archived → !draft.archived → "disables export for archived-only" 실패
#    M3: combined exportProject({includeArchived, manifest}) → exportProject({manifest}) → "passes include_archived" 실패
```
