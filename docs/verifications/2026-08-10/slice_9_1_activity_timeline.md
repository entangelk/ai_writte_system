# 독립 검증 — Slice 9.1 활동 타임라인 화면 (연결 가드 · F7 · 기준선)

| 항목 | 값 |
|---|---|
| 날짜 | 2026-08-10 |
| 요청자 | 오너 |
| 검증자 | 독립 세션(Slice 9.1 을 구현하지 않은) |
| 대상 | 미검증 구간 2커밋 — `86ca173`(구현) · `f220abd`(기록, SoT v1.7.94) |
| 정본 | [`system-contract-sot.md`](../../system-contract-sot.md) **v1.7.94** · [`plans/09-1-activity-timeline-screen-decisions.md`](../../plans/09-1-activity-timeline-screen-decisions.md)(Resolved) · [`guides/verification.md`](../../guides/verification.md) §"Mutation testing" |
| 소스 상태 | HEAD `f220abd`, 작업 트리 clean |
| 머신 | WSL2 · Python 3.12.3 · vitest 3.2.7 / vite 7.3.6 (backend test-mongo 미사용 — 이유는 §Outstanding) |

**이 검증이 존재하는 이유.** 구현자가 스스로 *"지금 미검증 구간이 이 두 커밋이다"* 라고 남겼고
(`work_log.md` §Task 5 Next steps · `HANDOFF.md`), 오너가 *"의심하고 또 의심해줄래"* 로
독립 검증을 요청했다. 구현자가 제시한 검증 축 셋 — **① 연결 가드가 진짜 연결인가(백엔드에
21번째를 실제로 더해 보는 뮤테이션) · ② M3 형태의 조용한 통과 · ③ F7 판단이 옳았는가** — 가
이 기록의 뼈다.

## 1. Scope

1. **연결 가드가 진짜 연결인가** — `tests/test_activity_ui_labels.py` 가 프론트 라벨표·링크표와
   백엔드 `ACTIVITY_ACTIONS` 를 **전수로** 맞물리게 하는가. 뮤테이션 양방향(under: 백엔드가 늘어
   도 · over: 프론트에 유령이 남아도) 으로 증명.
2. **M3 형태 조용한 통과 방어** — 라벨 *값* 에 리터럴을 복사하면(키 집합은 그대로라 1차 셀이
   못 잡는 형태) 2차 셀이 물어야 한다.
3. **target_type 분류의 연결** — 같은 가드 형태가 링크/비링크 전수 등재도 강제하는가.
4. **F7 사실 관계 + 비링크 잠금** — payload 에 `draft_id` 가 없어 `draft_version` 링크가
   불가능하다는 사실, 그리고 그 비링크 결정이 프론트 회귀 셀에 잠겨 있는가.
5. **회귀 셀** — 백엔드 4 cells/28 subtests · 프론트 7 cells 의 green + 구조(각 셀이 무엇을
   잠그는가).
6. **기준선 재도출** — backend delta(직접 실행) · frontend 전수(재실행) · build(모듈·청크) ·
   operation **77** 무변 · 응답 형태 무변.
7. **브리프 전제 반증(F7)의 정합성** — 구현자가 *"브리프 전제가 틀렸다"* 고 한 판단이 코드
   실측에 부합하는가.

## 2. Methodology

```bash
git status --short                  # ★ pre-flight: 매 뮤테이션 전 반드시 빈 것 확인
git show --stat 86ca173 f220abd     # 대상 diff 전량 (backend 프로덕션 0줄 확인)

# baseline — 연결 가드 4 cells
python3 -m pytest tests/test_activity_ui_labels.py -v          # → 4 passed, 28 subtests
# baseline — 프론트 7 cells
cd frontend && npx vitest run src/projects/ActivityTimelinePage.test.tsx   # → 7 passed

# 뮤테이션 5종 (clean-tree branch: HEAD=f220abd 이 정확한 사전 상태 → git checkout -- 복구)
# M-A: 백엔드 21번째 action 추가(기존 target_type "draft") → 라벨 셀 under 방향
sed -i '/writing\/accept", "draft_version"),/a\    ActivityAction("comment_added", "POST", "/projects/{project_id}/comments", "draft"),' services/application/app/activity/actions.py
python3 -m pytest tests/test_activity_ui_labels.py::ActivityUiLabelTableTest::test_the_ui_table_labels_exactly_the_logged_actions
git checkout -- services/application/app/activity/actions.py

# M-B: 라벨 칸에 리터럴 복사(draft_version_saved: "draft_version_saved") → 2차 셀
sed -i 's/  draft_version_saved: "원고 저장",/  draft_version_saved: "draft_version_saved",/' frontend/src/projects/activityActions.ts
python3 -m pytest tests/test_activity_ui_labels.py::ActivityUiLabelTableTest::test_every_label_is_korean_prose_not_the_literal
git checkout -- frontend/src/projects/activityActions.ts

# M-C: 기존 action 의 target_type "project"→"comment"(프론트가 모르는 새 값) → target_type 셀
sed -i '/draft-order/s/"project"/"comment"/' services/application/app/activity/actions.py
python3 -m pytest tests/test_activity_ui_labels.py::ActivityUiTargetTypeTest::test_every_target_type_is_classified_as_linkable_or_not
git checkout -- services/application/app/activity/actions.py

# M-D: 유령 라벨(ghost_action) 추가 → 라벨 셀 over 방향
#   (Edit 도구로 gate_finding_dismissed 행 뒤에  ghost_action: "유령 행",  삽입)
python3 -m pytest tests/test_activity_ui_labels.py::ActivityUiLabelTableTest::test_the_ui_table_labels_exactly_the_logged_actions
git checkout -- frontend/src/projects/activityActions.ts

# M7: activityTargetHref 가 draft_version 도 링크 → 프론트 셀(F7 비링크 잠금)
#   (Edit: if (targetType === "draft" || targetType === "draft_version"))
cd frontend && npx vitest run src/projects/ActivityTimelinePage.test.tsx
git checkout -- frontend/src/projects/activityActions.ts

# 매 복구 뒤: git status --short 가 빈 것 + git diff --stat 이 빈 것을 확인(내용 비교)

# F7 사실 — payload 필드 전량 + target_id 의 실제 의미
sed -n '96,124p' services/application/app/routers/projects.py          # 응답 8필드, draft_id 없음
sed -n '330,340p' services/application/app/routers/drafts.py            # target_id=result.draft_version.id
sed -n '1270,1310p' services/application/app/routers/writing.py         # accept 양 분기 同
grep -n 'drafts/:draftId' frontend/src/App.tsx                         # 편집 route = draftId 필수

# 기준선 — frontend 전수 재실행 + build
cd frontend && npx vitest run                  # → 272 passed / 19 files (1차 run 1 flake, 2차 run green)
cd frontend && npm run build                   # → 701 modules · 진입 417.19 kB · lazy 무변
```

`grep FAILED` 함정([`verification.md`](../../guides/verification.md) §"Reading the result") 대비: subTest
실패는 `SUBFAILED(...)` 로 나므로 tail 의 summary 행(`1 failed, N passed, M subtests`)을 읽었다.
M-C 1차 시도는 sed 치환이 no-op(diff 빈)이라 "green" 이 무의미했다 — **diff 를 확인해 잡고** 변형 C
(`/draft-order/s/"project"/"comment"/`)로 다시 적용했다.

## 3. Findings

### 3.1 연결 가드는 진짜 연결이다 (axis ① — 양방향 뮤테이션으로 증명)

연결 셀 [`test_activity_ui_labels.py:62-77`](../../../tests/test_activity_ui_labels.py#L62) 는
`set(프론트 라벨표) == {a.action for a in ACTIVITY_ACTIONS}` 를 단정한다. 백엔드 모듈을 **직접
import** 하므로([L26-29](../../../tests/test_activity_ui_labels.py#L26)) 두 정본을 같은 자리에서
본다 — `schema.d.ts` 가 `action` 을 `string` 으로만 준다는 구현자 사유(L15-16)는 타당하다.

| 뮤테이션 | diff | 결과 |
|---|---|---|
| **M-A** under | 백엔드 `_CANONICAL` 에 21번째 `ActivityAction("comment_added", …, "draft")` 추가 | 라벨 셀 **FAIL** — `Items in the second set but not the first: 'comment_added'`. target_type 셀은 통과(재사용한 "draft" 로 고립) |
| **M-D** over | 프론트 라벨표에 `ghost_action: "유령 행"` 추가 | 같은 셀 **FAIL** — `Items in the first set but not the second: 'ghost_action'` |

양방향 모두 정확히 어긋난 리터럴을 지목하며 물었다. **연결은 진짜다** — 백엔드가 21번째를
더해도, 프론트에 오타·삭제 잔해가 남아도 셀이 문다. 구현자의 M1(라벨 1행 삭제)/M2(유령 라벨)가
같은 셀을 쳤다고 한 기록([work_log L370-371](../../../docs/daily_logs/2026-08-10/work_log.md))과
정합이다(방향만 반대).

### 3.2 M3 형태(조용한 통과)는 2차 셀이 잠근다 (axis ②)

라벨 **값** 에 리터럴을 복사하는 변이는 키 집합을 안 바꿔 1차 셀(set 동치)을 빠져나간다.
폴백 `?? action`([`activityActions.ts:77`](../../../frontend/src/projects/activityActions.ts#L77)) 이
있어 **화면은 영어 스네이크인데 테스트는 green** 이 되는 형태다.

- **M-B**: `draft_version_saved: "draft_version_saved"` → 1차 셀 **PASS**(키 집합 무변), 2차 셀
  [`test_every_label_is_korean_prose_not_the_literal`](../../../tests/test_activity_ui_labels.py#L79)
  **SUBFAILED(action='draft_version_saved')** — `assertNotEqual(label, action)` 가 `'draft_version_saved' == 'draft_version_saved'`.

2차 셀의 존재 이유가 입증됐다. 1차·2차의 분업(1차 = 키 집합 전수, 2차 = 값이 한국어 문구인지)
은 구현자 M3 설명([work_log L372, L378-380](../../../docs/daily_logs/2026-08-10/work_log.md))과 일치한다.

### 3.3 target_type 분류도 같은 형태의 연결이다

[`test_every_target_type_is_classified_as_linkable_or_not`](../../../tests/test_activity_ui_labels.py#L94)
는 `linkable ∪ non_linkable == {a.target_type for a in ACTIVITY_ACTIONS}` ∧ `linkable ∩ non_linkable == ∅`.
- **M-C**: `draft_order_changed` 의 target_type `"project"→"comment"`(프론트가 모르는 새 값).
  라벨 셀은 **PASS**(action 리터럴 무변 → 고립 성공), target_type 셀 **FAIL** — `Items in the
  second set but not the first: 'comment'`.

`LINKABLE_TARGET_TYPES`(배열)·`NON_LINKABLE_TARGET_TYPES`(사유표) 가 백엔드 9종 target_type 을
전수로 덮는다(project·project_brief·draft·draft_version·source_ref·candidate·analysis_job·
review_queue_entry·gate_finding). 새 종류가 생기면 링크하거나 사유와 함께 비링크로 등재해야 한다
— `billable_actions.py` 관례와 같다. 구현자 M4(`gate_finding` 미등재 → 같은 셀)와 정합.

### 3.4 F7 판단은 사실에 부합하고 비링크는 잠겨 있다 (axis ③)

**사실 관계**(코드 실측, 구현자 주장과 정합):
- `draft_version_saved` 의 `target_id = result.draft_version.id`(**version id**) —
  [`drafts.py:335`](../../../services/application/app/routers/drafts.py#L335). endpoint 는
  `draft_id` 를 알지만([L321](../../../services/application/app/routers/drafts.py#L321)) `activity.record`
  에 넘기지 않는다.
- `draft_version_accepted` 양 분기 모두 `target_id = …draft_version.id` —
  [`writing.py:1275,1304`](../../../services/application/app/routers/writing.py#L1275).
- 응답은 **정확히 8 필드** `id·actor_user_id·action·target_type·target_id·at·before·after`,
  **`draft_id` 없음** — [`projects.py:112-124`](../../../services/application/app/routers/projects.py#L112).
- 편집 route `/projects/:projectId/drafts/:draftId`(`draftId` 필수) — [`App.tsx:54`](../../../frontend/src/App.tsx#L54).

`draft_version` 행을 링크하려면 `draft_id` 가 필요한데 payload 에는 version id 만 있다. 링크를
만들면 version id 를 draft id 자리에 넣는 **깨진 링크**가 된다. 넣으려면 응답 필드 추가 =
**operation 77 계약 변경**이며, 이 슬라이스가 오너 승인 아래 지키기로 한 *"계약 영향 0"*([브리프
L17-18](../../plans/09-1-activity-timeline-screen-decisions.md))과 어긋난다. **구현자가 그 자리에서
계약을 넓히지 않은 것은 옳았다.** draft 만 링크하고 draft_version 은 사유와 함께 비링크표에
등재([`activityActions.ts:67`](../../../frontend/src/projects/activityActions.ts#L67)), 유예 F7(트리거:
payload 에 `draft_id` 가 생기면)로 올렸다.

**비링크 잠금**(뮤테이션):
- **M7**: `activityTargetHref` 가 `draft_version` 도 링크하게 변경 → 프론트 셀
  [`links only the target types that have a screen`](../../../frontend/src/projects/ActivityTimelinePage.test.tsx#L63)
  **FAIL** — `expect(links).toHaveLength(1)` 가 **2**(draft 행 + draft_version 행 모두 "원고 열기").
  이때 파이썬 가드는 **green 유지**(테이블이 아니라 함수를 바꿨으므로) — 즉 연결 가드(python)와
  행위 셀(frontend)은 **상보적**이며, F7 비링크를 잠그는 것은 프론트 셀이다.

### 3.5 회귀 셀 — 구조와 green

- **백엔드** `tests/test_activity_ui_labels.py`: 4 cells/28 subtests green. 각 셀의 잠금 대상 —
  라벨 키 집합 전수(L62) · 라벨 값=한국어 문구(L79) · target_type 분류 전수(L94) · 비링크 사유
  필수(L115). 28 subtests = 라벨 20 + target_type 비링크 8.
- **프론트** [`ActivityTimelinePage.test.tsx`](../../../frontend/src/projects/ActivityTimelinePage.test.tsx):
  7 cells green — 라벨 한국어화(L35) · 상한 문구 "최근 100건"(L43, S2) · before→after(L53) ·
  링크 대상 1종·draft_version 비링크(L63, S6/F7) · 행위자 열 없음(L77, S3 over-strict) · 빈
  상태(L87) · 에러 노출(L94). 브리프 S1~S6 의 화면 결정이 셀로 대응된다.

### 3.6 기준선 재도출

| 항목 | 구현자 주장 | 재측정 | 일치 |
|---|---|---|---|
| 백엔드 연결 가드 delta | +4 cells / +28 subtests | `4 passed, 28 subtests`(직접) | ✓ |
| frontend 전수 | 272 passed / 19 files | **1차**: 271/1 failed(DraftEditor emoji flake) · **2차**: **272/272 · 19/19** | ✓(2차) |
| build modules | 701 | **701 modules transformed** | ✓ |
| build 진입 청크 | 417.19 kB | **`index-*.js` 417.19 kB** | ✓ |
| lazy 청크 | 무변 | `AdminConsole` 8.50 · `ObservabilityDashboard` 386.70 kB(기존) | ✓ |
| `tsc --noEmit` | 통과 | build 스크립트 안pass | ✓ |
| operation | **77** 무변 · 응답 형태 무변 | 커밋 stat 에 backend 프로덕션 파일 0 → endpoint·응답 무변 | ✓ |

frontend 1차 run 의 실패 1건(`DraftEditor.test.tsx` "restores a historical source by exact snapshot
and code-point offsets", `selectionStart` emoji 단정)은 **과부하下的 일시 flake** 다 — 단독 실행
41/41 green, 전수 2차 run 272/272 green. Slice 9.1 이 건드린 파일이 아니며(App.tsx·client.ts·
DraftList.tsx + 신규 파일), 결정론적 회귀가 아니다. §Hardening 참조.

### 3.7 브리프 전제 반증(F7)의 정합성 — 브리프·SoT·코드 삼자 일치

브리프 §"구현이 반증한 전제 하나"([L193-208](../../plans/09-1-activity-timeline-screen-decisions.md))·
SoT v1.7.94 행([`system-contract-sot.md:36`](../../system-contract-sot.md))·코드 실측(§3.4)이 모두
같은 사실(payload 에 `draft_id` 없음 → `draft_version` 링크 불가 → 계약 영향 0 하에 비링크 등재)
을 말한다. 삼자 사이 모순 없음. "종류(`target_type`)가 있다고 route 를 만들 재료가 있는 것은
아니다"라는 교훈도 회귀로 뒷받침된다(M7).

## 4. Issues / Risks

### Blocking (계약 의무)

**없음.** 브리프가 요구한 모든 연결(① 라벨 전수 가드 · ② target_type 전수 등재 · ③ 화면 결정
S1~S6)이 셀로 잠겨 있고, 뮤테이션 5종(M-A·M-B·M-C·M-D·M7)이 전부 재실패했다. F7 은 사실에
부합하며 비링크가 잠겨 있다. 계약(operation 77 · 응답 형태)은 무변이고 backend 프로덕션은 0줄이다.

### Hardening recommendations (비차단)

1. **표시 상한(100) ↔ 서빙 상한(100) 이 비연결이다.** 프론트 상수
   [`ACTIVITY_PAGE_SIZE = 100`](../../../frontend/src/projects/ActivityTimelinePage.tsx#L11) 와 백엔드
   기본값 [`limit: int = 100`](../../../services/application/app/activity/log.py#L142) 은 **독립된 두
   하드코딩**이다. S4 의 라벨표-분류표는 전수 가드로 연결됐지만, 이 100-100 은 가드가 없다 —
   백엔드 기본이 바뀌면(F1 커서 페이징 등) 화면 "최근 100건" 문구가 **서빙 상한과 조용히 갈릴 수
   있다**. S2=ⓐ 가 요구한 것은 "화면이 상한을 **문장으로** 말한다"이지(프론트 셀
   [`says the 100-item ceiling out loud`](../../../frontend/src/projects/ActivityTimelinePage.test.tsx#L43)
   가 잠금) 두 100 의 연결까지는 아니다 — 그래서 **비차단**이다. S4 와 같은 패턴의 교차 파일
   단정(`log.py` 기본값 ↔ 프론트 상수)을 보강 후보로 남긴다.
2. **DraftEditor emoji selectionStart 테스트의 과부하 flake.**
   `DraftEditor.test.tsx` "restores a historical source by exact snapshot and code-point offsets"
   (`selectionStart/End` surrogate-pair 단정) 가 전수 1차 run 에서 1건 실패했다. 단독 41/41 green ·
   전수 2차 272/272 green 이라 결정론적이지 않고, jsdom 의 textarea 선택 동작이 병렬 과부하에
   민감한 것으로 보인다. Slice 9.1 무관·기존 테스트이므로 이 슬라이스의 책임이 아니다. 분리
   태스크로 (타이밍 안정화 또는 `selectionStart` 단정의 robust 화) 검토 권한다.

## 4-b. Hardening 폐쇄 (2026-08-10, 발행 뒤 추가)

오너 지시(*"검증기록 확인해서 보강할 부분 보강해줘"*)로 **같은 날 비차단 2건이 모두 닫혔다**
(`4097437`). 아래는 발행 후 추가된 사실이며 **§4 의 원 지적 문언은 그대로 둔다**(발행 시점
기록이 바뀌면 다음 사람이 무엇이 원래 지적이었는지 알 수 없다). **판정은 원래 `합격` 이라
승격 문제가 없다.**

| 항목 | 처리 | 실측 |
|---|---|---|
| **H1** 상한 비연결 | `ActivityCeilingClaimTest::test_the_screen_promises_exactly_what_the_service_serves` 추가 — 백엔드 기본값을 `inspect.signature` 로 읽어 프론트 상수와 대조(소스 regex 회피) | **양방향** — 백엔드 `100→50`, 프론트 `100→250` 둘 다 그 셀이 재실패 |
| **H2** selection flake | 두 selection 단정을 `waitFor` 로 감쌌다 — 선택은 값과 **다른 effect**(`pendingSelection` → `setSelectionRange`)라 동기 읽기가 경쟁이었다. **패턴 스윕으로 같은 형태를 한 곳 더**(`:1465`) 찾아 함께 고쳤다 | 기대값 `2→3` 뮤테이션에서 여전히 재실패 = **느슨해지지 않았다**. 백엔드 전수와 **동시 실행**(원 flake 의 과부하 조건)에서 green |

**★ H1 이 S4 와 같은 종류라는 것이 이 폐쇄의 요점이다** — 두 100 을 하나로 합치는 것이 아니라
(서빙 정책과 UI 문구는 다른 관심사다) **나눈 채로 연결**한다. 오너 원칙(2026-08-10)의 ③이
가드로 실현되는 세 번째 자리다(라벨표 · `target_type` 분류 · 상한).

## Verdict

**합격** — Blocking 0.

연결 가드는 진짜 연결이다(양방향 뮤테이션 M-A·M-D 로 증명), M3 형태의 조용한 통과는 2차 셀이
잠근다(M-B), target_type 분류도 같은 형태로 연결된다(M-C). F7 판단은 코드 실측에 부합하며
(payload 에 `draft_id` 없음 · `target_id`=version id · 편집 route 는 draftId 필수) 계약을 넓히지
않은 것이 옳았고, 비링크 결정은 프론트 셀에 잠겨 있다(M7). 기준선은 재현됐다(backend delta 직접
green · frontend 272/272 재실행 green · build 701/417.19 kB · lazy 무변). 비차단 2건(상한 비연결 ·
기존 emoji flake)은 hardening 으로 남긴다.

## Outstanding items

- **육안 확인 미실시** — 렌더 로직은 회귀로 잠갔지만 실제 화면을 사람이 본 적은 없다. 구현자가
  프론트 이미지 재빌드를 선행 조건으로 오너 판단 사안으로 남겼다(`work_log` §"아직 안 한 것").
  `/projects/:id/activity` 렌더 확인은 별도.
- **backend 전수(2254/1/2354) 미재실행** — 커밋 `86ca173` stat 이 backend 프로덕션 파일 0줄(변경
  전부 frontend + `tests/` 신규 1파일)임을 확인했으므로 기존 2250 셀이 이 슬라이스에 영향받을
  경로가 없다. delta(신규 4 cells/28 subtests)만 직접 green 으로 잡았다. 벨트서스펜더가 필요하면
  test-mongo ON 으로 `python3 -m pytest -q`(≈906s) 재실행.
- **F1~F7 유예** — 브리프 §"나중에 여는 문"에 트리거와 함께 산다. 이 검증은 그 트리거가 살아
  있음을 확인했다(F7 트리거 = payload 에 `draft_id` 생김).

## Reproduction

```bash
git checkout f220abd && git status --short    # clean
python3 -m pytest tests/test_activity_ui_labels.py -v        # 4 passed, 28 subtests
cd frontend && npx vitest run src/projects/ActivityTimelinePage.test.tsx   # 7 passed
# 뮤테이션 5종은 §2 Methodology 의 블록을 순서대로(각 git checkout -- 복구 + diff 확인 포함)
cd frontend && npx vitest run                   # 272/272 (과부하 시 1차 flake 가능 — 2차 green)
cd frontend && npm run build                    # 701 modules · index 417.19 kB
```
