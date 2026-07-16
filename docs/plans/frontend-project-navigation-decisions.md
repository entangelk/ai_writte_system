# 착수 결정 브리프 — Frontend 프로젝트 상세 내비게이션

상태: `Resolved — A (React Router Declarative BrowserRouter), owner confirmed 2026-07-16`

관련 정본: `frontend-kickoff-decisions.md` D3=A, `product-shell.md` 최소 사용자 표면, `product-readiness-backlog.md` UX-1, HANDOFF Next Tasks

## Decision needed

프로젝트 목록에서 원고 목록·에디터로 진입하려면 **프로젝트 선택 상태를 URL route로 둘지, 화면 내부 state로만 둘지** 결정해야 한다. 현재 SPA에는 router가 없고, HANDOFF가 프로젝트 상세 라우팅 도입 여부를 이 slice의 첫 결정으로 남겼다. 이 선택은 다음 원고 editor·Writing·Review 화면의 주소 구조와 테스트 방식을 계속 구속하므로 조용히 고를 수 없다.

## Options

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. React Router Declarative mode + BrowserRouter** | 공식 `react-router` 패키지를 추가하고 `/`는 프로젝트 목록, `/projects/:projectId`는 원고 목록으로 둔다. 이후 `/projects/:projectId/drafts/:draftId`를 additive로 연다. loader/action을 쓰지 않고 기존 얇은 `fetch` 계층은 유지한다. | 표준 URL·새로고침·뒤로가기·deep link를 즉시 얻는다. 동적 segment/nested route가 editor·Writing·Review 확장과 정확히 맞는다. nginx `try_files ... /index.html`이 이미 BrowserRouter fallback을 지원한다. | runtime dependency 1개와 router test wrapper가 추가된다. 첫 slice만 보면 state-only보다 코드가 조금 늘어난다. |
| B. 자체 History API 최소 router | `window.history.pushState`·`popstate`와 pathname parser를 직접 감싸 `/projects/:id`만 지원한다. | 외부 dependency가 없다. 지금 필요한 route만 구현할 수 있다. | routing·back/forward·404·테스트 seam을 직접 소유한다. draft/editor route가 늘 때 검증 코드가 커지고 표준 router를 재구현하게 된다. |
| C. component state-only 화면 전환 | `selectedProject`를 `App` state로 두고 목록과 원고 화면을 조건부 렌더한다. URL은 계속 `/`다. | 이번 원고 목록/생성 slice가 가장 작고 dependency가 없다. | 새로고침·deep link·브라우저 뒤로가기가 프로젝트 문맥을 잃는다. 바로 다음 editor에서 draft 선택까지 state가 중첩되고, React Router로 옮길 때 화면 경계를 다시 뜯는다. |
| D. React Router HashRouter | `/#/projects/:projectId`로 URL을 관리한다. | 서버 fallback 설정 없이 deep link가 안전하다. React Router의 route API를 쓴다. | nginx SPA fallback이 이미 있어 hash가 주는 이득이 없다. 주소가 제품 URL로 덜 명확하고 anchor와 섞인다. dependency 비용은 A와 같다. |

## Recommendation + reason

**A. React Router Declarative mode + BrowserRouter를 추천한다.**

현재는 프로젝트 선택 한 번이지만 확정된 다음 표면이 원고 editor, Writing workspace, Review Inbox라 `project_id`와 `draft_id`가 주소 계층에 계속 필요하다. A는 공식 문서가 제공하는 basic matching/navigation/active-state 범위만 쓰므로 기존 `fetch` 구조와 책임이 겹치지 않는다. Data/Framework mode를 도입하지 않아 loader·action·서버 렌더링까지 범위를 키우지 않는다.

또한 배포 nginx는 이미 알 수 없는 경로를 `index.html`로 돌리므로 BrowserRouter의 유일한 운영 전제도 충족돼 있다. 로컬 1인 프로젝트 단계에서도 새로고침과 뒤로가기는 기본 작업 복귀 경험이라, 다음 slice에서 다시 마이그레이션하는 것보다 지금 route spine만 세우는 편이 싸다.

공식 현재 설치·사용 기준: `npm i react-router`, `<BrowserRouter>` + `<Routes>/<Route>`, dynamic segment `:projectId`. 구현 시 package-lock이 고정한 실제 버전을 기록한다.

## Owner decision and rationale (2026-07-16)

오너는 외부 dependency 없이 직접 제어하는 **B(자체 History API)**를 개인적으로 선호하지만, 이 제품은 바로 다음에 editor·Writing·Review로 project/draft 주소 계층이 확장되므로 **확장성을 우선해 A를 선택**했다. 이 결정은 B의 장점을 부정하는 것이 아니라, 앞으로 늘어날 route·deep link·뒤로가기 검증을 직접 소유하는 비용이 현재 선호보다 크다고 판단한 것이다.

확정 범위는 `react-router`의 Declarative mode뿐이다. Data/Framework mode, loader/action, route-level cache는 승인 범위가 아니며 필요가 실재할 때 별도로 검토한다.

## 구현된 첫 code slice (SoT v1.6.96)

선택 A 기준 최소 범위를 그대로 구현했다:

1. `/` — 기존 프로젝트 목록/생성 유지, 프로젝트 이름을 `/projects/:projectId` 진입 action으로 변경.
2. `/projects/:projectId` — 선택 프로젝트 이름, “프로젝트로 돌아가기”, 원고 목록/빈 상태/생성.
3. API client — 생성 OpenAPI 타입으로 `listDrafts(projectId)`·`createDraft(projectId, body)`만 추가.
4. 회귀 — 프로젝트 격리 path, list/create reload, 공백-only 미전송, in-flight 중복 방지, archived 프로젝트 read-only, route back/deep-link 양방향.
5. 본문 editor·version save·export는 다음 slice.

고정 의존성은 `react-router@8.2.0`이며 해당 peer requirement를 manifest에도 드러내도록 React/React DOM을 `^19.2.7`로 맞췄다. 회귀 22개(3 files), production build, OpenAPI 타입 재생성, 실 API direct-route smoke를 통과했다. 백엔드 route/model은 바꾸지 않았다.

## UI 기준 (routing 선택과 무관)

- **Visual thesis**: 따뜻한 종이색 바탕과 잉크색 타이포그래피의 조용한 집필 작업대. 장식보다 작품→원고 계층이 먼저 보인다.
- **Content plan**: 앱 이름/현재 위치 → 한 개의 주 작업면(프로젝트 또는 원고 목록) → 생성 action → 오류·빈 상태. 마케팅 hero·dashboard card grid 없음.
- **Interaction thesis**: 목록 행의 절제된 hover/focus, route 전환 시 짧은 opacity/translate 등장, 생성 성공 후 서버 목록 재조회. 새 항목 강조는 실제 사용에서 재조회 뒤 위치를 잃는 문제가 관측될 때 추가하며, `prefers-reduced-motion`에서는 전환을 제거한다.

## Follow-up considerations

- editor route는 `/projects/:projectId/drafts/:draftId`를 기본 후보로 둔다. version id를 URL에 둘지는 version 선택 UX slice에서 결정한다.
- Writing/Review를 nested route로 둘지 project workspace 안 탭으로 둘지는 해당 UI가 실제로 생길 때 결정한다.
- route-level data loader는 현재 얇은 `fetch`+component state가 아플 때만 검토한다.
- 404 project/draft와 archived read-only 표시는 editor slice에서 public 상태 요구를 보고 확장한다.

## Deferred / out of scope

- editor, save/idempotency, version 목록·상세, export
- autosave, rich-text editor, data router loader/action, code splitting
- global state/cache library, breadcrumbs system, mobile navigation
- backend route/model 변경과 `main.py` 분리(이번 slice는 프론트 조립만 목표)
