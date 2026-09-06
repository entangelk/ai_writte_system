# 장면 메모 Slice 3·4(화면 둘) 독립 검증

## Subject metadata

| 항목 | 값 |
|---|---|
| 날짜 | 2026-09-06 |
| 요청 | 오너("장면 메모 Slice 3·4 를 의심하고 또 의심해봐줘" — 독립 검증) |
| 검증자 | Claude Opus 5 (1M context) — **구현자와 다른 세션** |
| 대상 슬라이스 | 장면 메모 Slice 3(별도 화면) · Slice 4(드로어 메모 탭·저장 UI) |
| 대상 커밋 | `fe358d0`(Slice 3 화면) · `aa9fcdf`(공용 검색 컴포넌트 + 드로어 패널) · `4d73f01`(드로어 배선) · `c64d4f7`·`4e52339`·`e3dc8a6`(셀 보강) · `58d9315`(기록) |
| 검증 시점 HEAD | `58d9315` — 워킹 트리 **clean**(`git status --short` 무출력, 변이 전 pre-flight 게이트 통과) |
| 정본(계약) | [`docs/system-contract-sot.md`](../../system-contract-sot.md) **v1.8.36 행**(화면 리터럴 ①~⑨) |
| 정본(계획) | [`docs/plans/scene-note-implementation-phases.md`](../../plans/scene-note-implementation-phases.md) Slice 3·Slice 4 절과 "완료 기준" 4항목 |
| 정본(결정) | [`docs/plans/scene-note-decisions.md`](../../plans/scene-note-decisions.md) D1=C+A · D2=A · D3=A · D4=A(본문 상한 12000자 · 초과 422 · 동일값 재저장은 행을 남기되 5초 연타는 활동 행만 접음 · 미리보기=검색 연계 200자 · 페이지네이션 없음 · 보관 장면 포함 + 두 축 표시) |
| 구현자 기록 | [`docs/daily_logs/2026-09-06/work_log.md`](../../daily_logs/2026-09-06/work_log.md) 세션 21 "장면 메모 Slice 3·4" (변이 표 MN-1~MN-10) |

**병렬 작업 주의**: 같은 시간대에 다른 세션이 identity group Slice 6 마감·최종 저장 5차 재검증 조건 B1 폐쇄를 진행 중이었다(`HANDOFF.md`·`CHANGELOG.md`·`docs/system-contract-sot.md`·`DraftEditor.tsx`·`DraftEditor.test.tsx` 공유). 이 검증은 **`git checkout -- <path>` 를 한 번도 쓰지 않았고**, 모든 변이를 `cp` 백업 → Edit 도구 편집 → **역방향 Edit 원복** → `diff` 바이트 대조로 처리했다(가이드 §"Mutation testing" 세 번째 행). 스테이징은 이 기록 파일과 인덱스 4개뿐이다.

## Scope

1. **경계 행렬** — 브리프 확정값 · 계획 Slice 3·4 범위/검증 문장 · SoT v1.8.36 리터럴 ①~⑨ 각각이 기명 셀에 매핑되는가. ★ 빈 칸은 차단 지적이다.
2. ★ **완료 기준 1**("`/projects/:id/notes` 와 편집기 드로어가 같은 검색 결과를 읽는다")이 실제로 **잠겨 있는가** — 컴포넌트 공유가 잠금인가, 한쪽이 갈라져도 초록인가.
3. **구현자 변이 표 MN-1~MN-10 재유도** — 줄 번호가 아니라 diff 를 직접 다시 써서 재실패 셀 **이름·개수**까지 대조. 특히 MN-8·MN-10 의 셀 보강(`4e52339`·`e3dc8a6`)이 실제로 잠금이 됐는가.
4. ★ **검증자 자체 변이**(구현자 표에 없는 방향) 최소 4종 — 물지 않는 것이 발견이다.
5. **계약 문언 대 코드** — SoT v1.8.36 행이 코드보다 넓게 말하는 곳, 그리고 구현자가 work_log 에 적은 판단 둘(`updated_at` 미표시 · 다른 장면은 읽기 전용)이 계약·계획과 모순되지 않는가.
6. **프런트 CSS 가드**(`designTokens`·`typeScale`·`buttonAppearance`·`pageLayout`·`disabledState`)가 새 규칙을 실제로 덮는가.
7. **API 계약 무변 주장**(`gen:api` 후 `schema.d.ts` 바이트 무변) 재현.

## Methodology

**환경 라벨** — 아래 모든 실측값은 이 환경의 것이다. 다른 환경에서 숫자가 달라질 수 있는 축(작업 디렉터리·트리 상태)을 함께 적는다.

- OS: WSL2 `Linux 6.6.87.2-microsoft-standard-WSL2`, 저장소는 `/mnt/f/devel/ai_writte_system`
- Node `v22.17.0` · npm `10.9.2` · Python `3.12.3` · vitest `3.2.7`(jsdom)
- **프런트 테스트는 반드시 `frontend/` 에서 실행**했다. 저장소 루트에서 실행하면 jsdom 이 붙지 않아 전건 실패한다 — 아래 숫자는 전부 `cd frontend` 기준이다.
- 트리 상태: 시작·종료 모두 `git status --short` **무출력**(clean). 변이 구간에서만 대상 파일 1~2개가 일시적으로 dirty 였고 매회 원복 후 바이트 대조했다.

```bash
# 계약·계획·기록 재독 (1차 출처)
sed -n '1,400p' docs/plans/scene-note-implementation-phases.md
grep -n "v1.8.36" docs/system-contract-sot.md
grep -n "세션 21" -A 400 docs/daily_logs/2026-09-06/work_log.md

# 전수·타입·계약
cd frontend && npx vitest run                       # 446 passed / 38 files
cd frontend && npx tsc --noEmit                     # rc=0
cd frontend && npm run gen:api && git status --porcelain src/api/schema.d.ts   # 무출력

# 집중
cd frontend && npx vitest run src/notes             # 25 passed / 3 files
cd frontend && npx vitest run src/notes src/drafts/DraftEditor.test.tsx  # 94 passed / 4 files

# 변이(매회) — 남의 미커밋 작업을 지우지 않는 절차
cp <대상> $SCRATCH/bak/            # 백업
#   Edit 도구로 변이 적용 → 집중 셀 실행 → **역방향 Edit** 로 원복
diff $SCRATCH/bak/<대상> <대상>    # 바이트 동일 확인 (매회 무출력)
git status --short                  # clean 확인
```

`sed -i`·`perl -0pi` 제자리 편집은 이 경로(`/mnt/f`)에서 파일을 실제로 손상시키므로 사용하지 않았다.

## Findings

### F1. 실측 재현 — 구현자 주장과 일치

| 축 | 구현자 주장 | 재현값(위 환경) | 판정 |
|---|---|---|---|
| 프런트 전수 | 446 passed | **446 passed / 38 files**(89.4s) | 일치 |
| 신규 집중 셀 | 25(page 7 · panel 14 · drawer 4) | **25 passed / 3 files** — `SceneNotesPage.test.tsx` 7 · `SceneNotePanel.test.tsx` 14 · `SceneNoteDrawer.test.tsx` 4 | 일치 |
| 타입 | 무오류 | `npx tsc --noEmit` **rc=0** | 일치 |
| API 계약 무변 | `gen:api` 후 `schema.d.ts` 무차이 | 재생성 후 `git status --porcelain src/api/schema.d.ts` **무출력**, 트리 전체 clean | 일치 |

**산술 한 자리가 안 닫힌다(하드닝 H5).** SoT v1.8.36 행은 *"프론트 신규 25셀 … + 작업 공간 입구 1 + AuthGate route 1, 전수 418→446"* 이라고 적었다. 열거의 합은 **27** 인데 델타는 **28** 이다. 남은 1은 같은 날 **다른 세션**의 커밋 `0a2fee4`(최종 저장 5차 재검증 B1 폐쇄 셀)의 것이다 — 그쪽 work_log 세션 21 기록(`docs/daily_logs/2026-09-06/work_log.md:547`)이 "418 → 428, 이 슬라이스 증분 +1, 나머지 +9 는 `fe358d0` 것"이라고 적어 두었으므로 **418 + 1 + 9 + 18 = 446** 으로 닫힌다. 숫자는 옳고 **귀속이 부정확**하다.

### F2. 경계 행렬 — SoT v1.8.36 리터럴 ①~⑨

| 리터럴 | 코드 | 기명 셀 | 상태 |
|---|---|---|---|
| ① 검색은 서버가 한다(`?query=` 전달 · 브라우저 재필터 금지) | `SceneNoteSearch.tsx:43-57`, `api/client.ts:586-601` | `SceneNotesPage.test.tsx:98` "hands the search box to the server instead of filtering in the browser"(over-strict 방향 포함) | ✅ 잠김(MN-1·MV-H 재실패) |
| ② 목록은 미리보기만 읽는다(`body_preview`·`truncated`) | `SceneNoteSearch.tsx:135` — `body_preview` 만 읽는다 | `SceneNotesPage.test.tsx:67` · `SceneNotePanel.test.tsx:94-95` | ⚠️ **`truncated` 무참조·무셀 → B4** |
| ③ 보관은 두 축(`scene_archived`·`chapter_archived`) | `SceneNoteSearch.tsx:132-133` | `SceneNotesPage.test.tsx:148` "shows scene archiving and chapter archiving as the two axes they are"(양방향) | ✅ 잠김 |
| ④ 빈 프로젝트 ≠ 빈 검색 결과 · 실패한 검색이 목록을 지우지 않는다 | `SceneNoteSearch.tsx:50-54, 96-104` | `:119` · `:137` · `:177` · `:186` 네 셀 | ✅ 잠김(MN-2 → 2셀 재실패) |
| ⑤ 별도 화면과 드로어가 **`SceneNoteSearch` 한 컴포넌트**를 공유(완료 기준 1) | `SceneNotesPage.tsx:26` · `SceneNotePanel.tsx:176-185` | 없음 — 두 파일이 각자 "URL 이 `/notes` 다"만 단정 | ❌ **무잠금 → B1** |
| ⑥ 편집 대상은 현재 Scene 하나 · 다른 장면은 읽기 전용 전문 · 장면 이동 시 대상이 따라감 · 마운트 유지 + 활성 탭만 조회 | `SceneNotePanel.tsx:59-94`, `DraftEditor.tsx:979-992` | `:185` · `:208` · `:229` · `:299` · `:98` + `SceneNoteDrawer.test.tsx:107` | ✅ 잠김(MN-7·MN-8 재실패). 단 `:299` 의 시나리오 명명은 배선과 어긋난다 → H3 |
| ⑦ 명시적 저장 · 요청 중만 잠금(변경 없음으로는 잠그지 않음) · 저장 뒤 목록 재조회 | `SceneNotePanel.tsx:96-116, 150-156` | `:117` · `:173` · `:149` | ✅ 잠김(MN-3 1셀 · MN-4 3셀 · MV-G 1셀) |
| ⑧ 12000자 상한 = **경고 + 저장 차단**, 잘라내기 아님(`maxLength` 금지) | `SceneNotePanel.tsx:20, 61, 146-152` | `:361` — 차단(12000/12001 경계)·`maxlength` 부재는 단정, **경고 문구는 미단정** | ⚠️ **"경고" 절반 무셀 → B3** |
| ⑨ grant 읽기 전용은 **PUT 403 뒤에** 드러난다(`forcedReadOnly` 선례) · 탭 셋→넷 · `?panel=` 은 `TOOL_PANELS` 에서 유도 | `SceneNotePanel.tsx:110-112`, `DraftEditor.tsx:87-88, 42-52` | `:329` "turns a refused write into a read-only surface" · `SceneNoteDrawer.test.tsx:69·83·95` | ⚠️ under-strict 만 잠김. **"403 만" 이라는 over-strict 방향 무셀 → B2** |

### F3. 경계 행렬 — 계획 "완료 기준" 과 Slice 3·4 검증 문장

완료 기준 4항목 중 **이 두 슬라이스의 범위는 1번뿐**이다(2=Slice 2 인가 · 3=Slice 0 파기 · 4=Slice 2 활동 기록, 모두 API 슬라이스에서 닫혔다).

| 계획 문장 | 매핑 셀 | 상태 |
|---|---|---|
| 완료 기준 1 "두 화면이 같은 검색 결과를 읽는다" | — | ❌ **B1** |
| Slice 3 검증 "검색 query 전달" | `SceneNotesPage.test.tsx:98` | ✅ |
| Slice 3 검증 "빈 결과" | `:119`·`:137` | ✅ |
| Slice 3 검증 "보관 … 오류 표현" | `:148` | ✅ |
| Slice 3 검증 "404/403 오류 표현" | `:177`(404) · `:186`(503) | △ 코드에 상태별 분기가 없어 한 셀이 전부를 덮는다. 다만 **구현자 변이 표 MN-2 의 "초기 403" 은 실제로 404 픽스처**다(`:178`) — 표의 라벨 오류 → H6 |
| Slice 3 검증 "편집기 링크" | `:67` | ✅ |
| Slice 3 검증 "route 가 AuthGate 안" | `App.test.tsx:126` — `/auth/me` 가 목록 요청보다 먼저임을 순서로 단정 | ✅ |
| Slice 3 "작업 공간 입구" | `DraftList.test.tsx:70` | ✅ |
| Slice 4 검증 "드로어와 페이지가 같은 API 계약" | `SceneNotePanel.test.tsx:78` | △ URL 만 같음을 단정 — 결과 동일성은 B1 |
| Slice 4 검증 "현재 Scene 전환" | `:208`·`:229` | ✅ |
| Slice 4 검증 "저장 성공" | `:117`·`:149` | ✅ |
| Slice 4 검증 "저장 **실패**" | `:329`(403 만) | ❌ **B2** — 403 이외 실패(409 보관·5xx)의 셀이 없다 |
| Slice 4 검증 "grant 읽기 전용" | `:329` | ✅ |
| Slice 4 검증 "drawer close 뒤 선택 상태" | `:299` | △ prop 수준만 — H3 |
| Slice 4 검증 "기존 writing/analysis/review 탭 과도 변경 금지 회귀" | `SceneNoteDrawer.test.tsx:69`·`:83`(탭 목록 4개를 라벨·순서까지 단정) + `DraftEditor.test.tsx:1305` | ✅ |

### F4. 구현자 변이 표 MN-1~MN-10 재유도 (diff 를 직접 다시 씀)

| 변이 | 내가 적용한 diff | 구현자 주장 | 재유도 결과(재실패 셀 이름) | 대조 |
|---|---|---|---|---|
| MN-1 검색 축 | `listSceneNotes(projectId, query)` → `listSceneNotes(projectId)` + `result.filter(scene_title.includes(query.trim()))` | 화면 1셀 | **1** — `hands the search box to the server…` | 일치 |
| MN-2 실패 처리 | catch 안에 `setNotes([])` 삽입 | 화면 2셀(초기 403 · 검색 503) | **2** — `surfaces a refused list…` · `keeps a failed search from erasing…` | 개수 일치, **라벨 오류**(첫 셀 픽스처는 403 이 아니라 404) |
| MN-3 in-flight | `disabled={saving \|\| overLimit}` → `disabled={overLimit}` | 패널 1셀 | **1** — `saves the exact body once and keeps the button locked…` | 일치 |
| MN-4 dirty 과잉교정 | `savedBody` state 신설(로드·저장 뒤 갱신) + `disabled` 에 `body === savedBody` 추가 | 3셀 | **3** — `re-reads the list after a save…` · `does not lock saving an unchanged body…` · `turns a refused write into a read-only surface…` | 일치 |
| MN-5 읽기 전용 표시 | `readOnly={!writable}` → `readOnly={false}` | 2셀 | **2** — `turns a refused write…` · `keeps an archived scene readable…` | 일치 |
| MN-6 403 승격 | `if (cause instanceof ApiError && cause.status === 403) setForcedReadOnly(true);` 줄 삭제 | 1셀 | **1** — `turns a refused write…` | 일치 |
| MN-7 탭 게이팅 | 패널 `if (!tabActive) return;` + 검색 `if (!active) return;` 둘 다 삭제 | 패널 1 + 드로어 1 | **2** — `stays quiet until its drawer tab is open` · `does not fetch notes while another tab is the open one` | 일치 |
| MN-8 장면 전환 초기화 | `useEffect(() => {setSelected(null); setOtherBody(null); setNotice(null);}, [draftId])` 블록 삭제 | 보강 후 1셀 | **1** — `returns to the new scene's note when the editor moves while another note is selected` | 일치 — **보강(`4e52339`+`e3dc8a6`)이 실제 잠금**임을 확인 |
| MN-9 상한 경계 | `>` → `>=` | 1셀 | **1** — `blocks a body past the 12000 limit…` | 일치 |
| MN-10 미저장 글 보존 | `if (loadedFor === draftId) return;` 삭제 | 보강 후 1셀 | **1** — `does not clobber unsaved note text when the tab is closed and reopened` | 일치 — 보강이 실제 잠금 |

**결론: 구현자 변이 표는 정직하다.** 10종 전부 셀 이름·개수까지 재유도됐고, "처음엔 안 물었다"고 자기 보고한 MN-8·MN-10 도 보강 후 지금 물린다. 유일한 흠은 MN-2 의 상태 코드 라벨(403↔404)이다.

### F5. 검증자 자체 변이 9종 — **3종이 물지 않았다**

| 변이 | 적용한 diff | 실행 대상 | 결과 |
|---|---|---|---|
| **MV-A** 드로어만 갈라짐 | `SceneNoteSearch.load`: `setNotes(result)` → `setNotes(onSelect === undefined ? result : result.filter((n) => n.scene_title.includes(query.trim())))` (= 드로어 절반만 브라우저 필터) | `src/notes` | ❌ **무물림 — 25 passed** → **B1** |
| **MV-B** 403 승격 과잉 | `cause instanceof ApiError && cause.status === 403` → `cause instanceof ApiError` (모든 실패가 읽기 전용을 강제) | `src/notes` | ❌ **무물림 — 25 passed** → **B2** |
| **MV-C** 상한 경고 제거 | `{overLimit && \` / 상한 …자 초과 — 저장할 수 없습니다\`}` 줄 삭제(차단은 유지) | `src/notes` | ❌ **무물림 — 25 passed** → **B3** |
| **MV-F** 이탈 가드 무력화 | `guardNavigation` 본문 `if (onBeforeNavigateAway?.() === false) event.preventDefault();` → `void event;` | `src/notes` + `DraftEditor.test.tsx` | ❌ **무물림 — 94 passed** → **B5** |
| MV-D `null`↔`""` 뭉개기 | `setMissing(note.body === null)` → `… === null \|\| note.body === ""` | `src/notes` | ✅ 1 재실패 — `blocks a body past the 12000 limit…`(이름이 상한 셀이다 → H1) |
| MV-E `?panel=notes` 해석 제거 | `TOOL_PANELS.find(...)` → 종전 3분기 하드코딩 | `src/notes` + `DraftEditor.test.tsx` | ✅ 1 재실패 — `opens the memo panel from the address and loads this scene's note` |
| MV-G `refreshKey` 무시 | 효과 의존성 `[load, active, refreshKey]` → `[load, active]` | `src/notes` | ✅ 1 재실패 — `re-reads the list after a save…` |
| MV-H 매 입력마다 요청 | `onChange` 에 `void load(event.target.value)` 추가 | `src/notes` | ✅ 2 재실패 — `hands the search box…` · `keeps a failed search from erasing…` |
| MV-I `idempotency_key` 과잉 교정 | `putSceneNote` body 에 `idempotency_key: crypto.randomUUID()` 추가 | `src/notes` | ✅ 1 재실패 — `saves the exact body once…` |

원복은 9회 전부 역방향 Edit + `diff` 바이트 동일(무출력)로 확인했고, 마지막에 4개 대상 파일(`SceneNotePanel.tsx`·`SceneNoteSearch.tsx`·`api/client.ts`·`DraftEditor.tsx`) 전부와 `git status --short` clean 을 함께 확인했다.

### F6. 계약 문언 대 코드

- **`truncated` 는 문언에만 있다.** SoT ② 는 *"목록은 미리보기만 읽는다(`body_preview`·`truncated`)"* 라고 두 필드를 명시하는데, `grep -rn truncated frontend/src`(schema 제외)의 결과는 **픽스처 3곳(전부 `false`)과 주석 1곳뿐**이며 컴포넌트가 읽지 않고 어떤 셀도 단정하지 않는다. `schema.d.ts:2559-2561` 의 계약 주석은 *"`truncated` 는 화면이 '더 보기'를 낼지 판단하는 신호"* 라고 적는데 화면에 그 자리가 없다. 코드를 넣을지(계획 Slice 3 범위 문장은 "…본문 미리보기·해당 Scene 편집기 이동**만**"이라 넣지 않는 쪽이 정합적) 문언을 고칠지는 **오너 판단**이다 → B4.
- **구현자 판단 ① `updated_at` 미표시**: 계획 Slice 3 범위 문장의 열거("전체 목록·검색 입력·Scene 제목/Chapter 제목·본문 미리보기·해당 Scene 편집기 이동만")에 없고 SoT ②~⑤ 어느 문장도 요구하지 않는다. **모순 없음.**
- **구현자 판단 ② 다른 장면은 읽기 전용**: SoT ⑥ 이 *"다른 장면을 고르면 전문을 읽기 전용으로 보여 주고"* 라고 같은 말을 명시하고, 브리프 D1=A 의 "집필 맥락 보존"과도 일치한다. **모순 없음.**
- **연타 축(브리프 2026-08-31 추가 확정)**: "화면은 요청 중 버튼을 비활성화해 같은 실수를 앞단에서도 막는다"는 문장이 `SceneNotePanel.tsx:152` + 셀 `:117` 로 성립한다. 서버의 5초 창은 Slice 2 소관이라 이 슬라이스가 건드리지 않았다. **정합.**

### F7. CSS 가드 4종이 새 규칙을 덮는가

- **`typeScale.test.ts`**: 4번 셀(`keeps the migration list identical to what the stylesheet actually migrated`)이 목록을 **스타일시트에서 유도**하므로, 새로 추가된 `var(--type-*)` 규칙 4개(`.note-preview`·`.rail-note-editor`·`.note-body`·`.rail-note-status`)는 등재하지 않으면 실패한다. 실제로 `typeScale.test.ts:115-118` 에 등재돼 있다. **덮는다.**
- **`buttonAppearance.test.ts`**: accent 면 + `cursor: pointer` 동시 선언으로 "겉모습을 정하는 자리"를 유도한다. 저장 버튼은 새 자리를 만들지 않고 기존 `.row-actions button` 을 그대로 쓰며(`SceneNotePanel.tsx:151`), `.note-select` 는 `background: transparent`라 정체 규칙에 들어가지 않는다(설계대로). **덮는다 — 위반 없음.**
- **`disabledState.test.ts`**: `:disabled` 규칙을 스타일시트에서 유도한다. 저장 버튼의 비활성 농도는 기존 공통 규칙이 담당하고 새 리터럴이 추가되지 않았다. **덮는다.**
- **`pageLayout.test.ts`**: `SceneNotesPage` 는 `.workspace-page`(수식자 없음)를 쓰고 새 `width` 선언이 없다. 2번 셀이 마크업에서 수식자를 유도하므로 폭을 하나 더 얹었다면 실패했을 것이다. **덮는다.**
- **`designTokens.test.ts`**: 신규 CSS 는 색을 전부 토큰(`--text-muted`·`--surface-raised`·`--border-hairline`·`--text-link`·`--text-body`)으로 쓴다. 전수 green 으로 확인.

## Issues / Risks

### Blocking (계약 의무)

**B1. 완료 기준 1("두 화면이 같은 검색 결과를 읽는다")과 SoT ⑤ 가 어디에도 잠겨 있지 않다.**
`MV-A` — `SceneNoteSearch.tsx:46-47` 에서 **드로어 모드(`onSelect !== undefined`)일 때만** 서버 결과를 제목으로 브라우저 필터하도록 바꿨다. 즉 두 화면이 같은 검색어에 **다른 행 집합**을 그린다(본문에서 매치돼 올라온 행이 드로어에서만 사라진다 — ① 이 금지한 바로 그 현상). 결과: **`src/notes` 25 passed 전건 초록.**
현재 셀은 화면 절반(`SceneNotesPage.test.tsx:98`)에만 있고, 드로어 쪽 `SceneNotePanel.test.tsx:78` 은 *"URL 이 `/api/projects/p1/notes` 다"* 만 본다. 컴포넌트 공유는 **구현 사실**이지 잠금이 아니다.
- 처방: `SceneNotePanel.test.tsx` 에 드로어에서 **검색을 제출하는** 셀을 추가한다 — (a) 요청 URL 이 `?query=…` 를 싣는지, (b) **제목에는 검색어가 없고 `body_preview` 에만 있는 행**이 드로어 목록에 그대로 남는지(over-strict 방향). `SceneNotesPage.test.tsx:98-117` 의 모양을 드로어 픽스처로 옮기면 된다. 더 강한 대안: 같은 stub 응답으로 두 표면을 렌더해 **행 집합이 동일**함을 단정하는 셀 하나.

**B2. "PUT 403 뒤에만 읽기 전용" (SoT ⑨) 의 over-strict 방향과 계획 Slice 4 검증 "저장 실패"가 무셀이다.**
`MV-B` — `SceneNotePanel.tsx:112` 을 `if (cause instanceof ApiError) setForcedReadOnly(true);` 로 넓혔다(=409 보관·5xx 도 영구 읽기 전용으로 승격). 결과: **25 passed 전건 초록.**
실사용 영향이 있다: 보관된 장에 속한 장면은 서버가 409 를 주는데(계획 Slice 2 "archived 3축 409"), 이 과잉 교정이 들어가면 화면이 "grant 읽기 전용"이라는 **틀린 이유**로 저장 버튼을 영구히 없앤다.
- 처방: `SceneNotePanel.test.tsx` 에 PUT 이 **409(또는 500)** 를 주는 셀을 추가한다 — 오류 문구는 뜨고 **"메모 저장" 버튼은 그대로 남아 있어야 한다**(403 셀 `:329` 와 짝을 이루는 over-strict 가드).

**B3. SoT ⑧ 의 "경고" 절반이 무셀이다.**
`MV-C` — 상한 초과 안내 문자열(`SceneNotePanel.tsx:148`)만 지우고 차단은 남겼다. 결과: **25 passed 전건 초록.** 사용자는 12001자를 붙여넣은 뒤 이유 없이 회색이 된 버튼만 보게 되는데 아무도 실패하지 않는다. ⑧ 은 "경고 + 저장 차단"을 한 문장으로 못박았고 지금은 차단·비잘라내기 두 축만 잠겨 있다.
- 처방: 기존 상한 셀(`SceneNotePanel.test.tsx:361`)을 넓힌다 — 12001자에서 `role="status"` 줄이 상한 초과 문구를 포함하고, 12000자에서는 포함하지 않음(양방향).

**B4. SoT ② 가 코드에 없는 리터럴 `truncated` 를 읽는다고 말한다(계약 문언 > 코드).**
`grep` 결과 `truncated` 는 픽스처(항상 `false`)와 주석에만 있고 어떤 컴포넌트도 읽지 않으며 어떤 셀도 단정하지 않는다. 가이드의 "spec-silent / spec-wider 는 계약 수정 요청 사안"에 해당한다 — 조용히 문언을 줄이지도, 조용히 넘어가지도 말아야 한다.
- 처방(오너 선택): ⓐ 문언을 코드에 맞춘다 — ② 를 *"목록은 `body_preview` 만 읽는다(`truncated` 는 payload 에 있으나 이 슬라이스의 화면은 쓰지 않는다 — '더 보기'는 Deferred)"* 로 정정. ⓑ 또는 절단 표시를 구현하고 `truncated` true/false 두 방향 셀을 추가한다. 계획 Slice 3 범위 문장의 "…만 제공한다"와 정합적인 것은 ⓐ 다.

**B5. 드로어 메모 링크의 이탈 가드(`onBeforeNavigateAway`)가 선례와 달리 무셀이다.**
`MV-F` — `SceneNotePanel.tsx:118-120` 의 가드를 통째로 무력화했다(원고에 미저장 본문이 있어도 다른 장면으로 그냥 이동). 결과: **`src/notes` + `DraftEditor.test.tsx` 합계 94 passed 전건 초록.**
같은 모양의 가드를 쓰는 **선례 둘은 전부 셀로 잠겨 있다** — `review/WorkspaceReviewPanel.test.tsx:132` "lets the editor guard cancel a full-inbox link while text is dirty", `review/AnalysisTrigger.test.tsx:262`. 방어 절(`"이럴 땐 이동하지 않는다"`)은 결함을 심어도 아무 셀이 없으면 초록이므로 **방어를 걷어내 보는** 방식으로만 드러나는 종류다(가이드 §"Defensive assertions need the opposite move").
- 처방: 선례 셀을 그대로 옮긴다 — `onBeforeNavigateAway={vi.fn(() => false)}` 로 패널을 렌더하고, 다른 장면을 고른 뒤 `"… 열기 →"` 링크를 클릭해 (a) 가드가 1회 호출되고 (b) route 가 바뀌지 않음을 단정.

### Hardening (비차단)

**H1. `body === ""`(빈 메모 저장됨) 쪽은 상한 셀이 우연히 잡고 있다.** `MV-D`(`missing` 판정에 `|| body === ""` 추가)는 물지만, 재실패한 셀 이름은 `blocks a body past the 12000 limit…`(`:361`)이다 — 그 셀이 조회 완료를 `findByText("0자")` 로 기다리기 때문이다. 전용 셀 `:389` 는 `null` 쪽만 본다. 상한 셀의 대기 방식이 바뀌면 `""`↔`null` 계약이 조용히 풀린다. → `:389` 에 "빈 메모가 저장된 장면은 '아직 메모가 없습니다' 라고 말하지 않는다"를 짝으로 추가.

**H2. 드로어의 읽기 전용은 보관 3축 중 2축만 반영한다.** `DraftEditor.tsx:210` 의 `readOnly = forcedReadOnly || project?.archived || draft?.archived` 에는 **장(chapter) 축이 없다**(`DraftPayload` 에 그 필드가 없다 — 편집기가 물려받은 선결함이지 이 슬라이스의 회귀가 아니다). 그래서 보관된 장의 장면에서는 저장 버튼이 살아 있고 PUT 409 로만 알게 된다. 목록 payload 에는 `chapter_archived` 가 이미 있으므로 패널이 유도할 여지가 있다. 계약 위반은 아니다 — ③ 은 *목록 표시*의 두 축을 말하고 그것은 지켜졌다.

**H3. `keeps the selection while the drawer is closed and reopened`(`:299`)가 재현하는 상황은 실제 배선에서 일어나지 않는다.** 이 셀은 드로어 닫힘을 `tabActive={false}` 로 모사하는데, 실제 `DraftEditor` 는 닫아도 `activePanel = routedPanel ?? lastPanel`(`:89-94`, `:269`)로 `"notes"` 를 유지하므로 `tabActive` 는 **계속 true** 다(즉 닫힌 드로어 뒤에서도 조회가 나간다 — `WorkspaceReviewPanel` 과 동일한 선례 동작이라 새 결함은 아니다). 셀이 잠그는 성질(탭 토글을 넘겨도 선택이 살아 있다)은 진짜지만 **이름이 말하는 시나리오는 아니다.** 계획의 "drawer close 뒤 선택 상태"를 배선 수준에서 보려면 `SceneNoteDrawer.test.tsx` 에서 `closeDrawer` 를 실제로 눌러야 한다.

**H4. 드로어 행의 선택 표시(`aria-pressed`, `SceneNoteSearch.tsx:123`)에 셀이 없다.** 선택 강조가 사라져도 전건 초록이다. `:185` 셀에 `aria-pressed` 단정 한 줄이면 닫힌다.

**H5. SoT v1.8.36 행의 회귀 산술이 한 자리 안 맞는다.** 열거 합 27 vs 델타 28 — 남은 1은 병렬 세션의 `0a2fee4`. "전수 418→446(그중 +1 은 같은 날 다른 세션의 `0a2fee4`)" 식으로 귀속을 적으면 다음 검증자가 재산출에 시간을 쓰지 않는다.

**H6. 구현자 변이 표 MN-2 의 "초기 403" 은 실제로 404 픽스처다**(`SceneNotesPage.test.tsx:178` — `{ detail: "project not found", status: 404 }`). 개수는 맞고 셀도 맞다. 겸해서, 계획 Slice 3 검증이 열거한 **403** 은 목록 표면에 전용 픽스처가 없다(코드에 상태별 분기가 없어 404 셀이 같은 경로를 덮는다 — 그래서 차단으로 세지 않는다).

## Verdict

**조건부 합격** — 조건 **B1**(두 화면 "같은 검색 결과" 무잠금: 드로어만 갈라져도 25 passed), **B2**(PUT 403 만 읽기 전용으로 승격한다는 over-strict 방향 무셀 = 계획 "저장 실패" 빈 칸), **B3**(SoT ⑧ "경고" 절반 무셀), **B4**(SoT ② 가 코드에 없는 `truncated` 를 읽는다고 말함 — 문언 정정 또는 구현 중 오너 선택), **B5**(이탈 가드 무셀 — 선례 둘은 잠겨 있음).

근거가 되는 것:

1. **구현 자체는 계약대로다.** SoT ①~⑨ 의 동작을 코드에서 1차로 재유도했고 어긋난 동작을 하나도 찾지 못했다. 브리프 확정값(12000 · 명시적 저장 · 변경 없음으로 잠그지 않음 · 두 축 보관 표시 · 페이지네이션 없음)이 전부 코드에 있다.
2. **구현자 변이 표 10종은 정직하다** — 셀 이름·개수까지 재유도로 일치했고, 자기 보고한 두 무잠금(MN-8·MN-10)의 보강도 실제로 물린다.
3. **그러나 검증자 변이 9종 중 4종이 물지 않았다**(MV-A·MV-B·MV-C·MV-F). 그중 B1 은 **이 페이즈의 완료 기준 1 그 자체**이고, B5 는 같은 저장소가 두 선례에서 이미 셀로 잠근 방어 절이다. 가이드는 계약이 요구하는 분기의 빈 칸을 "보강 후보"로 부르는 것을 금지하므로, 이 넷은 조건이다.
4. **API 계약 무변·타입·전수 주장은 전부 재현됐다**(446/38 · rc=0 · `schema.d.ts` 무변).

B1~B5 는 전부 **셀 추가 또는 계약 한 문장 정정**으로 닫히며, 코드 변경을 요구하는 것은 없다(B4 를 ⓑ 로 고르는 경우 제외).

## Outstanding items

- **B1~B5 의 보강은 구현 세션 몫이다.** 검증자는 결함을 직접 고치지 않는다(가이드 마지막 줄). 위 처방은 그대로 시행 가능한 형태로 적었다.
- **B4 는 오너 결정 자리**다(문언 정정 ⓐ vs 절단 표시 구현 ⓑ). ⓐ 를 고르면 `docs/system-contract-sot.md` v1.8.36 ② 한 문장과 `frontend/src/api/client.ts:583` 주석을 함께 고친다.
- 이 검증은 **백엔드를 실행하지 않았다**(프런트 전용 슬라이스, 계획 "UI Slice 3~4 는 API 계약을 바꾸지 않는다"). `gen:api` 바이트 무변으로 그 주장을 확인했다.
- 병렬 세션의 미커밋 작업은 이 검증 동안 관측되지 않았다(시작·종료 모두 트리 clean). `git checkout` 미사용, `git add` 는 이 기록과 인덱스 4개만.

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system
git status --short                                  # 비어 있어야 한다 (변이 전 게이트)

cd frontend
npx vitest run                                      # 446 passed / 38 files
npx vitest run src/notes                            # 25 passed / 3 files
npx tsc --noEmit                                    # rc=0
npm run gen:api && git status --porcelain src/api/schema.d.ts   # 무출력

# 차단 4종 재현 — 각 변이 후 `npx vitest run src/notes` (MV-F 는 + src/drafts/DraftEditor.test.tsx)
#   MV-A  SceneNoteSearch.tsx:47  setNotes(result)
#         → setNotes(onSelect === undefined ? result
#             : result.filter((note) => note.scene_title.includes(query.trim())))   ⇒ 25 passed
#   MV-B  SceneNotePanel.tsx:112  cause instanceof ApiError && cause.status === 403
#         → cause instanceof ApiError                                              ⇒ 25 passed
#   MV-C  SceneNotePanel.tsx:148  {overLimit && ` / 상한 …`} 줄 삭제                 ⇒ 25 passed
#   MV-F  SceneNotePanel.tsx:119  if (onBeforeNavigateAway?.() === false) event.preventDefault();
#         → void event;                                                            ⇒ 94 passed
#
# 원복은 반드시 역방향 편집으로. 이 저장소에서 `git checkout -- <path>` 는
# 병렬 세션의 미커밋 작업을 지운다. 매회:
#   cp <대상> /tmp/.../bak/  (변이 전)  →  Edit 로 변이  →  Edit 로 역변이  →  diff 로 바이트 대조
```
