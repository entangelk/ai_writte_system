# 2026-09-07 작업 로그

## 목표

- HANDOFF Next Tasks **4번(장면 메모 후속)** 을 닫는다 — 오너 결정 2026-09-06 이 남긴 두 자리.
  - ① 목록 행에 **수정 시각**(`updated_at` 은 payload 에 이미 있다).
  - ② **절단 표시("더 보기")** — `truncated` 를 화면이 처음 읽는다. SoT v1.8.37 이 이 자리에 붙여 둔 조건은 *"열 때 true/false 양방향 셀과 함께 연다"* 이므로, 셀이 조건이지 부록이 아니다.

---

## 세션 24 — 장면 메모 후속: 수정 시각 · 더 보기 (SoT v1.8.38)

### 1. 착수 전 — 이것은 결정 브리프 자리가 아니다

두 자리 모두 오너가 *무엇을* 여는지 이미 정했고(2026-09-06), 남은 것은 배치뿐이었다. 그중 하나는 이미 답이 있었다 — HANDOFF 4번이 *"전문은 단건 GET 이 주므로 '더 보기'는 그 호출이다(목록이 전문을 기대하게 만들지 말 것)"* 라고 못박아 두었다. 남은 판단은 **"더 보기"를 별도 화면에만 둘 것인가**였고, 선례로 답했다: `SceneNoteSearch` 는 두 화면이 공유하는 한 벌이고 완료 기준 1 이 *"두 화면이 같은 검색 결과를 읽는다"* 이다. 행이 하는 일(링크 vs 선택)만 갈리는 것이 종전 설계이므로, 목록 자신의 성질인 펼침을 화면마다 다르게 두면 그 축이 하나 더 늘어난다. **양쪽에 똑같이 두었고, 모드 분기가 없어 코드도 그쪽이 적다.**

### 2. 구현 (커밋 `f46a462`)

`frontend/src/notes/SceneNoteSearch.tsx` 한 파일 + 스타일 2규칙이 전부다. 백엔드·API 계약·`schema.d.ts` 무변(두 필드 모두 Slice 1 부터 payload 에 있었다).

- **행 꼬리줄** `.note-row-meta` 를 새로 두고 거기에 수정 시각과 "더 보기"를 실었다. 제목 줄에 얹지 않은 이유는 좁은 드로어에서 제목·장 배지·보관 배지와 같은 줄에 서면 **제목이 먼저 줄바꿈**되기 때문이다.
- 수정 시각은 `<time dateTime={note.updated_at}>수정 {…toLocaleString("ko-KR")}</time>`. 선례는 `AdminConsole` 의 `요청 {…}` 이다. 서버 값은 UTC-aware 라(`core_sot/mongo_repository.py::_aware`) 브라우저가 로컬로 옮긴다 — naive 함정이 없다.
- **펼침은 한 번에 한 행**(`expandedId`·`expandedBody`)이고, 전문은 `getSceneNote` 단건 GET 이 준다. 조회 실패는 **미리보기를 걷어내지 않는다**(걷어내면 사용자는 메모가 사라진 것으로 읽는다) — 목록 조회 실패의 종전 처방과 같은 모양이다.
- **목록이 새로 오면 접는다.** 저장 뒤 갱신(`refreshKey`)이나 새 검색에서 펼친 전문만 옛 본문으로 남으면 같은 행의 미리보기와 다른 사실을 말한다.
- `.note-expand` 는 **링크형 버튼**(`.rail-back` 과 같은 모양)이라 accent 면을 쓰지 않는다 → 기본 동작 버튼의 겉모습 자리(`buttonAppearance.test.ts`)에 등재하지 않는다. 등재가 필요한 쪽은 **타이포 축**이었다(아래 Issues 1).

### 3. 셀 (신규 6)

| 파일 | 셀 | 잠그는 것 |
|---|---|---|
| `SceneNotesPage.test.tsx` | shows each row its own last-modified time | 행마다 **자기** `updated_at`. 실행 머신 시간대에 기대 문자열이 달리므로 같은 변환을 기대값으로 쓴다 — 잠그는 것은 문자열이 아니라 출처다 |
| " | offers 더 보기 only where the server said the preview was cut | `truncated` **양방향** — 참인 행에만 |
| " | pulls the full body from the single-note GET and folds back to the preview | 펼침이 **단건 GET** 이라는 것 + 접기 |
| " | keeps the preview on screen when the full body cannot be read | 실패가 미리보기를 지우지 않는다 |
| " | folds an expanded row back when a new list arrives | 목록 갱신에서 접기(변이 MN-8 이 드러낸 자리) |
| `SceneNotePanel.test.tsx` | expands a cut preview in place without moving the editing target | 드로어 목록에도 같은 자리가 있고, **펼침 ≠ 선택**(편집 대상 불변) |

### 4. 변이 (커밋 → 변이 → 원복, 매회 `git status --short` 로 바이트 대조)

| 변이 | diff | 재실패 셀 |
|---|---|---|
| MN-1 신호 무시(over) | `{note.truncated && (` → `{true && (` | 화면 truncated 셀 1 + 드로어 펼침 셀 1 |
| MN-2 신호 안 읽음(under) | `{note.truncated && (` → `{false && (` | 4(truncated · 단건 GET · 실패 유지 · 드로어) |
| MN-3 시각 오귀속(over) | `note.updated_at` → `notes[0].updated_at` | 수정 시각 셀 1 |
| MN-4 시각 제거(under) | `<time>` 블록 → `{null}` | 수정 시각 셀 1 |
| MN-5 목록이 전문을 준다(over) | `await getSceneNote(…)` → `setExpandedBody(note.body_preview)` | 3(단건 GET · 실패 유지 · 드로어) |
| MN-6 펼침을 선택에 물림(over) | `onClick` 에 `onSelect?.(note)` 추가 | 드로어 펼침 셀 1 |
| MN-7 실패가 목록을 지움(under) | catch 에 `setNotes([])` 추가 | 실패 유지 셀 1 |
| MN-8 갱신에서 안 접음 | `load` 성공부의 `setExpandedId(null)`·`setExpandedBody(null)` 삭제 | **처음엔 0 → 셀 보강 후 1**(커밋 `9262f27`) |

### Issues found

1. **타이포 축 가드가 새 규칙을 잡았다** — `.note-row-meta` 가 `var(--type-micro)` 를 쓰는데 `typeScale.test.ts` 의 이관 목록에 없어 전수에서 1실패(*"keeps the migration list identical to what the stylesheet actually migrated"*). 이것이 **가드가 설계대로 작동한 것**이다(4번 셀은 목록을 스타일시트에서 유도해 대조한다 — 목록이 뒤처지는 것 자체가 불일치다). 목록에 한 행 더해 닫았다. `.note-expand` 는 `font-size: inherit` 이라 유도 집합에 안 들어가고, 그래서 목록에도 없다.
2. **MN-8 이 처음에 안 물었다** — 접는 동작에 셀이 없었다. 사용자 관점의 손상은 *"새 목록이 준 매치 중심 스니펫 대신 옛 전문이 그 행에 남는다"* 이므로, 펼친 뒤 검색을 제출해 스니펫이 이기는지 단정하는 셀로 닫았다. 세션 21 의 MN-8·MN-10 과 같은 처방(무잠금을 드러내면 셀을 새로 넣고 재실패 확인)이다.

### Decisions

- **"더 보기"는 두 화면 모두에 둔다** — 위 1절. 드로어에서 행 제목(선택)과 "더 보기"(펼침)는 다른 일이고, 그 구분 자체를 셀이 잠근다.
- **펼침은 한 번에 한 행이다.** 여럿을 동시에 펼치게 하면 상태가 맵이 되고 목록 갱신마다 정리 규칙이 하나 늘어난다 — 지금 요구에 없다.
- **접기 버튼은 조회 중 `불러오는 중…` 으로 잠근다.** 응답 전 접으면 뒤늦게 도착한 전문이 접힌 행에 붙는다.
- 세션 21 의 *"목록 행에 `updated_at` 을 싣지 않았다 … 오너 판단 자리라 적어 둔다"* 는 이 세션으로 닫혔다.

### Verification

- 신규·기존 focused: `src/notes/` **36 passed**(페이지 12 · 패널 19 · 드로어 5).
- 스타일 가드 3파일 16 passed(`typeScale`·`buttonAppearance`·`pageLayout`).
- `tsc --noEmit` 0.
- 프론트 전수 **451 → 457 passed / 38 files**(캡처 실행 `EXIT=0`, 38파일 전건).
- **★ 그 앞 실행 하나가 1실패를 보고했는데 정체를 못 남겼다** — `tail` 파이프에 실패 블록이 잘렸다(운영 실수). 같은 트리를 전체 출력 캡처로 **두 번 연속** 다시 돌려 둘 다 **457/457 초록**(`EXIT=0`)이고, 파일을 읽는 가드 10개(`typeScale`·`buttonAppearance`·`pageLayout`·`designTokens`·`navigationLinks`·`disabledState`·`scratchPadCss`·`adsense`·`productName`·`chartColors`)도 따로 돌려 35 passed 다. 그 실행 창(09:30~09:47)에 SoT·CHANGELOG·HANDOFF·README 를 편집하고 있었지만 **그 가드들이 저장소 문서를 읽지 않는다는 것은 확인했으므로 원인으로 지목하지 않는다**. ~~머신 부하가 극단적이었다(같은 실행 `environment 1778s`)~~ — **이 해석은 2026-09-07 독립 검증 F7 이 반증했다**: 실패 실행의 `environment 1778s` vs 검증자 **초록** 실행의 **1712s**, 겨우 4% 차이라 그 실행이 특별히 무거웠다는 근거가 없다. 부하를 원인으로 적은 것은 **측정 없이 고른 설명**이었다(같은 축의 다른 실행과 대조했어야 했다). 남는 가설은 **재현율이 낮은 타이밍 플레이크** 하나뿐이다. **정체 미상으로 남긴다** — 다음 전수에서 재현되면 그때 잡는다. 덧붙여 검증자가 별건 함정 하나를 실측했다: **vitest 를 저장소 루트에서 돌리면** jsdom 환경이 없어 `ReferenceError: document is not defined` 로 **전멸**한다(2회 재현). 실패 모양이 "1개 실패"와 달라 그 실행의 정체는 아니지만, 전수 실행의 **cwd 도 변인**이다 — `frontend/` 안에서 돌린다.
- 백엔드는 돌리지 않았다 — 이 슬라이스가 `services/`·`tests/`·`schemas/` 를 한 바이트도 건드리지 않았다(`git show --stat`).

### Next steps

- 육안 확인 누적 목록에 두 자리를 더한다(좁은 드로어에서 꼬리줄 줄바꿈 · 긴 전문 펼침의 스크롤).
- 독립 검증 대기.

---

## 세션 25 — 독립 검증 하드닝 H1~H3 폐쇄 (SoT v1.8.39)

독립 검증([`scene_note_follow_up.md`](../../verifications/2026-09-07/scene_note_follow_up.md)) 판정 **합격**, 차단 0. 비차단 하드닝 셋과 기록 정정 하나가 이 세션의 범위다. **검증 기록 자체는 고치지 않는다** — 검증자 소유이고, 선례(Slice 3·4 검증 기록)도 폐쇄 세션이 손대지 않았다.

### 1. H1 — 진짜 결함이었다(셋 중 유일하게 동작이 틀렸다)

H2·H3 는 잠금 공백이지만 **H1 은 코드가 틀린 자리**다. 펼침은 행마다 따로 나가는 요청인데 `expand()` 가 응답의 **주인을 확인하지 않았다**:

- A 를 펼치는 중에 B 를 누르면, A 의 늦은 **성공**이 `expandedBody` 에 A 본문을 싣는데 펼친 행은 B 다 → **B 행이 A 본문을 말한다**(B 응답이 오면 자기 교정되지만 그 사이가 거짓이다).
- A 의 늦은 **실패**는 더 나쁘다 — `setExpandedId(null)` 로 **열려 있던 B 를 접고** A 의 오류를 배너로 띄운다. 사용자는 자기가 떠난 행 때문에 지금 보던 것을 잃는다.

처방은 기다리는 대상을 `useRef` 로 들고 응답마다 대조하는 것이다. **`expandedId` 상태로는 판정할 수 없다** — handler 가 닫아 둔 옛 값이라 늘 자기 자신과 같다. 패널의 `let active = true` 정리와 같은 계열이고, 접기·목록 갱신도 그 ref 를 비운다.

### 2. ★ H1 셀이 처음에 새고 있었다 — 변이가 아니었으면 못 봤다

늦은 실패 셀이 `resolve` **직후에** 단정하고 있었다. 상태 갱신이 아직 안 붙은 시점이라 **가드를 걷어낸 변이(MN-10)가 35셀 전건 초록**으로 통과했다. `act` 로 흘려 보내 닫았다(커밋 `8e415ab`). 늦은 성공 셀은 뒤에 `findAllByRole` 이 있어 **우연히** 물고 있었는데, 같은 이유로 `deliver()` 를 태우고 `getAllByRole` 로 바꿨다 — 우연한 대기에 기대지 않는다.

이것이 이 세션에서 가장 값이 큰 발견이다: **하드닝을 닫으면서 새 셀을 넣으면 그 셀도 변이로 재야 한다.** 안 그러면 "닫았다"는 기록만 남고 잠금은 없다.

### 3. 변이 (커밋 `fdb4c69`·`8e415ab` → 변이 → 원복, 매회 `git status --short` 대조)

| 변이 | diff | 재실패 셀 |
|---|---|---|
| MN-9 늦은 성공 가드 제거 | 성공부 `if (awaiting.current !== target) return;` 삭제 | drops a late expand success … 1 |
| MN-10 늦은 실패 가드 제거 | catch 의 같은 줄 삭제 | **처음엔 0 → 셀 보강 후 1**(drops a late expand failure …) |
| MN-11 로딩 잠금 제거 | 접기 버튼 `disabled={expandedBody === null}` 삭제 | locks the fold control … 1 |
| MN-12 드로어에서만 시각 끄기 | `<time>` 을 `onSelect === undefined` 뒤로 | carries the row metadata into the drawer list too 1 |

MN-12 는 검증자가 예고한 모양 그대로다 — **컴포넌트 공유는 잠금이 아니다**(v1.8.37 B1 과 같은 종).

### 4. 기록 정정 — 부하 해석은 반증됐다

세션 24 가 미확인 1실패에 *"머신 부하가 극단적이었다"* 를 붙였는데, 검증 F7 이 실패 실행 `environment 1778s` vs 초록 실행 **1712s**(4% 차)로 반증했다. **측정 없이 고른 설명**이었다 — 같은 축의 다른 실행과 대조했으면 그 자리에서 무너졌다. 세션 24 의 해당 문장을 취소선으로 정정하고 남는 가설(낮은 재현율의 타이밍 플레이크)만 남겼다. 검증자가 실측한 별건 함정(**루트에서 vitest 실행 시 `document is not defined` 전멸**, 2회 재현)도 같은 자리에 박았다.

### Issues found

1. 위 2절 — 새 셀 자신이 무잠금이었다(MN-10).

### Decisions

- **검증 기록은 고치지 않는다.** 폐쇄는 SoT·work_log 에 남긴다(선례: Slice 3·4 검증 기록은 조건 폐쇄 뒤에도 단일 커밋).
- **`awaiting` 은 ref 다.** 상태로 두면 같은 경쟁이 판정 쪽으로 옮겨 갈 뿐이다.

### Verification

- focused `src/notes/` **40 passed**(페이지 15 · 패널 20 · 드로어 5).
- 프론트 전수 457 → **461 passed / 38 files**(전량 캡처, `EXIT=0`) · `tsc --noEmit` 0.
- 백엔드 무변(`services/`·`tests/`·`schemas/` 0건) — 문서 가드만 별도 확인.

### Next steps

- 배포 대기(프론트 이미지 재빌드 선행) · 육안 확인 누적.

