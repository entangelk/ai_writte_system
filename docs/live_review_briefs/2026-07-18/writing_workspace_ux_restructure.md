# 실검수 브리프 — Writing Workspace UX 구조 개편

상태: `Resolved — owner approved, implementation not started (W0 next)`
작성일: `2026-07-18`
발견 경로: 오너 실제 집필 dogfood
정본 연결: [`system-contract-sot.md`](../../system-contract-sot.md), [`product-shell.md`](../../plans/product-shell.md), [`frontend-writing-workspace-decisions.md`](../../plans/frontend-writing-workspace-decisions.md), [`06-review-ui.md`](../../plans/06-review-ui.md), [`07-conversational-authoring.md`](../../plans/07-conversational-authoring.md), [`product-readiness-backlog.md`](../../plans/product-readiness-backlog.md)

## 문제를 한 문장으로

현재 제품은 저장·생성·분석·검토 기능은 각각 관통하지만, **작품 정보·원고 단위·생성 목적·분석 결과가 하나의 명시적 작업공간 모델로 연결되지 않아** 사용자가 그 의미와 이동을 머릿속에서 보완해야 한다.

## 구조적 해결 원칙

오너의 “프롬프트에 명시하기보다 구조적으로 해결해야 하지 않는가”라는 판단에 동의한다. 프롬프트는 defense-in-depth이지 정본이나 상태 머신이 아니다.

권장 책임 순서는 다음과 같다.

1. **정본 데이터 구조**가 작품 정보와 원고 단위, 순서, 생성 대상을 표현한다.
2. **명시적 intent/API discriminator**가 “현재 원고에 붙이기”와 “다음 원고 시작”을 구분한다.
3. **서버 조립기**가 intent와 정본에서 ContextPackage/모델 입력을 만든다. 프론트가 자유문에 숨은 의미를 추론하거나 system prompt 문자열을 조립하지 않는다.
4. **validator와 accept 상태 전이**가 출력 대상과 저장 효과를 강제한다.
5. **프롬프트**는 이미 구조화된 의미를 모델에게 반복 설명하는 마지막 안전망으로만 남는다.

`analysis_extract_v3`가 repair turn에서 advisory report identifier를 제거하고 authoritative catalog만 전달한 방향이 이 원칙의 선례다. 같은 원칙을 Writing 전반에 적용하되, 모든 자유문을 schema로 바꾸지는 않는다. 창작 지시는 자유문으로 유지하고 **대상·저장 효과·권위 경계만 구조화**한다.

## 현재 구현에서 확인된 결손

### 1. 작품 시작 정보가 정본에 없다

- Core SOT `Project`는 `id/name/archived`만, `Draft`는 `id/project_id/title/archived`만 가진다.
- 프론트의 프로젝트 생성도 이름, 원고 생성도 제목만 받는다.
- 작품 premise·장르·톤·POV·핵심 제약을 넣을 전용 표면이나 API가 없다.
- 이를 첫 원고 본문이나 매번 Writing instruction에 넣으면 작품 정보와 실제 원고가 섞이고, 변경 이력·권위·재사용 경계도 사라진다.

### 2. “현재 이어쓰기”와 “다음 장/장면 시작”을 구분할 구조가 없다

- 현재 Writing literal은 `task_type=continue_scene`, `output_type=draft_patch` 하나다.
- accept는 같은 `draft_id/base_version_id`에 새 version을 append한다.
- Draft에는 `unit_kind`, 순서, 부모 chapter, 앞/뒤 원고 관계가 없다. 목록 순서는 서사 순서 계약이 아니다.
- 따라서 버튼 문구만 “다음 챕터”로 바꾸거나 자유문에서 추론하면 저장 대상이 틀릴 수 있다.

### 3. 분석과 편집이 서로 다른 장소에 있다

- editor → 별도 Review Inbox route → detail → editor 왕복이다.
- candidate source pointer는 제공되지만 editor route/selection/highlight deep-link가 없다.
- 분석 완료 상태·검토 대기 수·처리 진척을 editor 옆에서 지속적으로 볼 수 없다.
- Writing candidate도 React component state에만 있어 별도 route 이동 또는 새로고침 시 미채택 산출을 잃을 수 있다.

### 4. 작품 종합 정보 표면이 없다

- canonical memory list API는 이미 있지만 frontend consumer가 없다.
- 인물·사건·미해결 질문을 한 화면에 모으되, `canonical`과 `needs_review`를 섞어 확정 사실처럼 보이면 안 된다.
- 관계 graph·완전한 timeline은 현재 정본이 감당하지 못하므로 첫 overview에 넣기 어렵다.

### 5. 프로젝트 전체 export는 순서 계약이 선행돼야 한다

- 현재 export는 선택한 **단일 draft version**만 정확히 내보낸다.
- 프로젝트의 draft 순서와 각 draft에서 채택할 version 규칙이 없으므로 프론트가 임의 concatenation하면 잘못된 책 순서를 만들 수 있다.
- AI metadata는 본문에 섞지 않는 기존 계약을 유지해야 한다.

## 추가로 권장하는 UX 보강

- **작업 상태 바**: 저장됨/dirty, 분석 없음·진행·실패·완료, 검토 대기 수를 한곳에 표시한다.
- **근거 점프**: review source quote 선택 시 해당 version/offset을 editor에서 열고 highlight한다. 최신과 다른 snapshot이면 “과거 근거”를 명시한다.
- **이전/다음 원고 탐색**: 명시적 ordered unit 계약 뒤 keyboard/button으로 이동한다.
- **패널 상태 보존**: split pane tab·선택 candidate·filter를 URL query 또는 route state로 복원한다. 생성 후보의 새로고침 보존은 Phase 7 P1 영속과 겹치므로 별도 결정한다.
- **반응형 경계**: 넓은 화면은 2분할, 좁은 화면은 같은 정보구조의 tab/drawer로 전환한다. 모바일에서 억지 2열은 쓰지 않는다.
- **권위 배지**: overview/review에서 `검토 전`과 `정본`을 색뿐 아니라 텍스트로 구분한다.
- **다음 미처리 항목**: 검토 후 같은 pane에서 다음 candidate로 이동해 왕복을 줄인다. bulk 승인부터 만들지는 않는다.
- **점진적 onboarding**: 작품 brief는 필수 필드를 늘리지 않고 “지금은 건너뛰기”와 완료도를 제공한다.

## 확정된 오너 결정

2026-07-18 오너는 아래 권장 조합을 그대로 확정했다.

- **D1=A**: 작품 정보는 별도 `ProjectBrief` 정본이다.
- **D2=A**: 첫 원고 구조는 `unit_kind=chapter|scene|other`와 명시적 `position`을 가진 평면 ordered unit이다.
- **D3=C**: 생성 목적은 `append_current|start_next_unit` discriminator로 구분하고, 다음 unit 생성은 채택 시에만 원자적으로 저장한다.
- **D4=A**: editor 옆 docked right rail을 기본으로 하고 좁은 화면은 같은 정보구조의 tab/drawer를 쓴다.
- **D5=A**: 작품 overview는 canonical-only이고 pending은 별도 count/link로 분리한다.
- **D6=A**: 프로젝트 export는 ordered latest TXT/Markdown과 별도 manifest다.
- **전체 접근=C**: 구조를 big-bang이 아닌 W0~W4 세로 슬라이스로 구현한다.

결정 이유는 프롬프트나 화면 문구가 저장 대상·순서·권위를 추론하지 않게 하고, 실제 dogfood 가치가 큰 사용자 행동 단위로 검증하기 위해서다. 아래 옵션 표는 결정 당시의 대안과 tradeoff를 보존한다.

### D1. 작품 정보의 정본 위치

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 별도 `ProjectBrief` 정본 | project 1:1 구조로 premise·genre·tone·POV·constraints를 저장하고 version/audit 경계를 둔다 | 원고와 분리, Writing/overview가 같은 authority 소비, 필드 확장 가능 | 새 schema/API/context 조립 필요 |
| B. `Project` 필드 확장 | Project에 description/genre 등을 직접 추가 | 단순 CRUD, 조회 한 번 | 자유문·정책 필드가 Project core를 빠르게 비대화, 변경 이력 애매 |
| C. 첫 “설정 원고”를 convention으로 사용 | 일반 draft 하나를 작품 정보 문서로 취급 | 새 backend 적음 | 본문/설정 혼합, export·분석 제외 규칙과 권위 혼란 |

**Recommendation: A.** 작품 brief를 원고와 분리된 구조화 정본으로 둔다. 첫 필드는 `premise`, `genre`, `tone`, `pov`, `constraints` 정도의 optional 값만 두고, 인물/사건은 분석 memory와 중복 입력하지 않는다. Writing은 ProjectBrief를 별도 ContextPackage item으로 소비하고 프롬프트 문자열에 임의 병합하지 않는다.

### D2. 원고 계층과 순서

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 최소 ordered unit | Draft에 `unit_kind=chapter|scene|other`, `position`을 추가하고 project 안에서 명시 reorder | 다음/이전·전체 export·새 단위 생성에 충분, 구현 범위 통제 | chapter 안 scene 중첩은 아직 표현 못함 |
| B. chapter→scene 트리 | 부모/자식과 순서를 처음부터 정식 모델링 | 장편 구조를 정확히 표현 | migration·reorder·export·UI가 한 번에 커짐 |
| C. 제목 convention 유지 | `1장`, `2장` 제목과 생성 순서를 UI가 해석 | backend 변경 적음 | rename/삽입에 깨지고 순서 authority가 없음 |

**Recommendation: A.** 먼저 평면 ordered unit으로 시작한다. `unit_kind`는 UI/생성 의도에 쓰고, scene nesting이 실제로 필요해질 때 `parent_unit_id`를 additive로 연다. position은 문자열 제목에서 파싱하지 않는다.

### D3. Writing 생성 목적과 저장 효과

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 현 draft append만 유지 | “현재 원고 이어쓰기”만 제공, 다음 원고는 수동 생성 후 이동 | 현재 계약 재사용 | 사용자가 지적한 모호성과 단절이 남음 |
| B. 자유문에서 모델이 판단 | instruction을 보고 current/next를 추론 | UI 단순 | 저장 target을 AI가 결정, 오작동 시 위험 |
| C. 명시적 두 intent | `append_current`와 `start_next_unit`을 UI/API discriminator로 분리. 후자는 새 unit accept를 원자적으로 생성 | 의미·저장 효과가 명확, prompt 의존 제거 | 새 accept contract와 idempotency 필요 |

**Recommendation: C.** 두 mode를 radio/segmented control로 명시한다. `append_current`는 기존 `continue_scene/draft_patch`; `start_next_unit`은 unit kind/title/goal을 받고, **채택 시에만** 새 Draft+첫 version을 하나의 idempotent operation으로 만든다. 별도로 “빈 다음 원고 만들고 바로 이동” 점프도 제공해 AI 생성을 강제하지 않는다.

### D4. editor·Writing·Analysis·Review 배치

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. editor + docked right rail | 왼쪽 본문, 오른쪽 `이어쓰기/분석/검토/작품 정보` 내부 탭. 좁은 화면은 단일 tab/drawer | 왕복 제거, candidate state 유지, 근거 대조에 적합 | component 분리·route/query 상태·접근성 작업 필요 |
| B. 전체 화면 top tabs | Editor/Writing/Review/Overview를 같은 route 계층의 tab으로 | 화면 너비 확보, 구현 중간 | 본문과 근거 동시 비교 불가 |
| C. 현 별도 route 유지 + deep link | 이동만 개선 | 변경 작음 | 오너가 느낀 반복 왕복의 핵심이 남음 |

**Recommendation: A.** 데스크톱 로컬 집필 도구라는 현재 사용에 맞다. 다만 Review 상세를 별도 시스템으로 복제하지 않고 기존 action/API를 pane consumer로 재사용한다. URL은 draft route를 유지하고 `?panel=review&candidate=...`처럼 복원 가능하게 한다.

### D5. 작품 종합 정보의 권위와 첫 범위

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. canonical-only overview | 승인된 인물·사건·미해결 질문만 카드로 표시, pending 수는 별도 badge/link | 정본과 후보가 섞이지 않음, 기존 memory API 활용 | 아직 승인하지 않은 분석은 상세에서만 보임 |
| B. canonical+pending 혼합 | 한 목록에서 상태 badge로 구분 | 전체 현황 한눈에 봄 | 후보가 사실처럼 읽힐 위험, 필터 복잡 |
| C. 분석 candidate 그대로 요약 | 가장 빠른 UI | 구현 적음 | 권위 경계 위반 가능, 누적/중복이 overview 품질 훼손 |

**Recommendation: A.** 첫 overview는 canonical 인물·사건·미해결 질문과 unresolved review count만 보여준다. storyline은 확정된 event를 단순 목록으로 시작하고, 완전 timeline/관계 graph/자동 synopsis는 후속으로 둔다. `open_question_observation`은 현재 제품 언어에서 “떡밥/미해결 질문”으로 표시하되 자동 해결 여부를 추론하지 않는다.

### D6. 프로젝트 전체 export

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. ordered latest export | 비보관 unit을 position 순으로, 각 latest version을 합쳐 TXT/Markdown 생성 | 기대 동작 단순, D2와 정합 | 과거 version 조합 선택 불가 |
| B. export manifest 선택 | unit별 version을 선택한 manifest를 저장/내보냄 | 출판본 재현성 최고 | UI/API/manifest 정본이 큰 별도 기능 |
| C. 프론트에서 현재 목록 순 concatenate | backend 없이 빠름 | 구현 작음 | 순서·version traceability·대용량 오류 처리 취약 |

**Recommendation: A.** D2 ordered unit 이후 backend가 조립한다. 본문 export는 AI metadata를 넣지 않고, 별도 manifest에 project/unit/version/snapshot/hash를 기록한다. B의 saved export manifest는 실제 출판본 고정 요구가 생길 때 확장한다.

## 전체 접근 방식

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. UI facade 우선 | 기존 API만으로 split pane·overview처럼 보이게 구성 | 빠른 화면 변화 | 순서·intent·brief authority가 없어 다시 뜯을 가능성 큼 |
| B. 전체 정보 모델 먼저 | ProjectBrief·트리·intent·overview·export를 backend부터 한 번에 설계 | 구조 완결 | 변경이 너무 커 검증과 dogfood feedback이 늦음 |
| C. 구조를 세로 슬라이스로 | 각 사용자 행동에 필요한 최소 정본+API+UI를 함께 추가 | 의미와 UX를 함께 검증, 되돌리기 쉬움 | 여러 checkpoint 필요 |

**Recommendation: C.** 구조적 해결을 하되 big-bang으로 만들지 않는다.

## 권장 실행 순서

### Slice W0 — 계약 확정과 migration 경계

- D1~D6 오너 결정은 본 브리프·SoT·관련 계획에 기록 완료.
- ProjectBrief, ordered unit, Writing intent/accept의 public contract와 기존 데이터 기본값을 확정.
- 기존 Draft는 migration 시 `unit_kind=other`, 현재 저장 순서를 deterministic position으로 둘지 결정한다.

다음 작업자는 **W0부터 시작**한다. W0의 산출물은 (1) ProjectBrief exact schema/API/version 경계, (2) ordered unit position·reorder·기존 데이터 migration 규칙, (3) `append_current|start_next_unit` request/accept/idempotency·원자성 계약, (4) 각 should-fire/should-NOT-fire branch의 named 양방향 회귀 계획이다. 이 네 항목이 정본 문서와 schema에 반영되기 전에는 W1 UI 코드를 시작하지 않는다. 기존 데이터 순서나 position 충돌 처리처럼 저장소 precedent로 하나가 도출되지 않는 새 fork가 발견되면 별도 owner brief로 올린다.

### Slice W1 — 한 화면 집필 루프

- editor + docked right rail(`이어쓰기/분석/검토`)와 responsive fallback.
- 기존 API/action을 재사용하고 analysis status·review pending count 표시.
- candidate/detail 선택을 query state로 복원.
- source quote → editor version/offset highlight deep link.
- 이 slice에서는 backend 의미를 꾸미지 않고 기존 current-draft Writing만 명확히 표시한다.

### Slice W2 — 작품 시작/종합 정보

- ProjectBrief CRUD + 신규 프로젝트 progressive onboarding.
- Writing ContextPackage에 ProjectBrief authoritative item 배선.
- canonical-only overview(인물·사건·미해결 질문)와 pending badge.

### Slice W3 — 원고 구조와 다음 글 점프

- ordered unit + kind + reorder/previous/next.
- “빈 다음 원고 만들기”와 즉시 이동.
- explicit `append_current|start_next_unit`; 후자는 accept 시 새 Draft+첫 version 원자 생성.

### Slice W4 — 프로젝트 export

- ordered latest TXT/Markdown + 별도 manifest.
- archived 제외/default, 포함 여부와 heading separator를 contract로 잠금.

### Deferred

- 관계 graph, 완전 timeline editor, 자동 synopsis canon화
- bulk approval
- rich-text editor, autosave
- 대화형 부분 수정/아이디에이션과 미채택 AI 산출 영속(Phase 7 P1/P2/P3)
- DOCX/PDF/EPUB, saved publication manifest
- chapter→scene 중첩 트리

## 수용 기준

- 작품 설명은 원고 본문이나 임의 system prompt에 섞이지 않고 ProjectBrief 정본에서 조회된다.
- 사용자가 생성 전에 current append와 next unit start를 구분하고, accept의 저장 효과가 선택과 일치한다.
- editor를 떠나지 않고 분석 실행·상태 확인·후보 검토·근거 대조가 가능하다.
- source click은 정확한 version/offset으로 이동하며 stale/latest 차이를 숨기지 않는다.
- overview는 canonical과 pending을 혼동시키지 않는다.
- 전체 export의 unit 순서와 version/hash가 재현 가능하고 본문에 AI metadata가 삽입되지 않는다.
- 기존 단일 draft edit/save/history/export와 `continue_scene` 흐름은 migration 후에도 동작한다.

## 인계 상태

오너 결정은 완료됐으며 추가 승인 없이 **W0 계약·migration slice**를 착수할 수 있다. W0가 닫히면 첫 code slice는 W1(editor + right rail + analysis/review/source jump)이다. W1의 source deep-link는 version/offset selection 계약을 함께 잠그며 단순 CSS 2열로 끝내지 않는다.
