# 착수 결정 브리프 — Frontend (제품 껍데기 + Writing 작업공간 + Review UI)

상태: `Resolved — D1=A · D2=B · D3=A (owner confirmed 2026-07-15)` · **첫 슬라이스 구현됨(SoT v1.6.94, 2026-07-16)** — scaffold + 프로젝트 목록/생성까지. 원고 목록→에디터는 다음 슬라이스(오너 범위 분할, D3 각주 "크면 둘로 쪼갠다"의 발화). 미결정으로 남겼던 **프론트 테스트 도구는 Vitest + RTL로 확정**(v1.6.94, 오너 결정).

관련 정본: `docs/system-contract-sot.md` v1.6.94(브리프 작성 시점 v1.6.92 → 결정 기록 v1.6.93 → 첫 슬라이스 구현 v1.6.94), `plans/product-shell.md`(제품 경계·최소 사용자 표면), `plans/06-review-ui.md`(화면 단위·사용자 흐름), `plans/05-writing-ai.md`, HANDOFF Active Decisions(아키텍처)

## Owner decision and rationale (2026-07-15)

오너가 **D1=A / D2=B / D3=A**를 확정했다. 이번 세션은 **브리프 확정·기록까지만**이고 구현은 다음 세션에 착수한다.

- **D1=A (React + TypeScript + Vite)** — 추천대로. HANDOFF·SoT의 "frontend framework 보류(React/Vue 후보)"가 이 결정으로 해소된다.
- **D2=B (별도 compose 서비스)** — **추천(A)과 다른 선택이며 오너 판단이 canonical이다.** 프론트 정적 서빙을 application 이미지에 섞지 않고 서비스 경계를 분리한다(monorepo + 독립 서비스 경계라는 이 저장소의 아키텍처 원칙 — Gateway/Worker/embedding/ES가 모두 독립 서비스인 것과 같은 결). 대가로 A가 공짜로 주던 "단일 origin"이 사라지므로, **구현 시 기본값은 nginx가 `/api`를 application으로 reverse-proxy**해 단일 origin을 유지하고 CORS를 열지 않는다(인증 없는 API에 CORS를 여는 건 D2=C의 단점으로 이미 각하됨). 이 proxy 방식은 D2=B 안의 구현 세부이며 착수 시 확정한다.
- **D3=A (Product shell 척추)** — 추천대로. 의존성이 방향을 강제한다(Writing은 `current_position`, Review는 저장된 원고에서 나온 candidate 전제). 이후 순서는 A → C(Writing 작업공간) → B(Review Inbox).

## Decision needed

오너가 프론트엔드 착수를 지시했다(2026-07-15). 구현을 시작하려면 **framework/toolchain(D1)**, **서빙·배포 경계(D2)**, **첫 슬라이스 범위(D3)** 세 가지가 필요하다. 셋 다 이후 모든 프론트 작업을 구속하고 되돌리는 비용이 크며, 기존 정본이 답을 갖고 있지 않다:

- HANDOFF Active Decisions: "frontend framework는 **보류**(필요해지면 React/Vue 후보)" — 후보만 있고 확정이 없다.
- HANDOFF Active Decisions: "editor shell(frontend)은 **현재 범위 밖**" — 이번 지시가 이 범위 경계를 여는 것이므로, 결정 시 Active Decisions를 갱신한다(기록된 결정과의 충돌이 아니라 "필요해지면"의 발화).
- `product-shell.md`·`06-review-ui.md`는 **화면 단위와 사용자 흐름까지는 확정**했으나 구현 스택은 다루지 않는다(둘 다 `Draft`).

## 현재 확정된 사실 (프론트가 딛는 바닥)

- **백엔드 표면은 이미 완성**: `main.py`에 **50개 HTTP endpoint**(analysis 15 · writing 8 · drafts 8 · snapshots 3 · projects 2 · memory 2 · source-refs 1 · context-search 1 · health 1 + 루트 3). 프론트는 신규 백엔드 없이 조립만 하면 된다.
- **인증 없음**: MVP는 계정/로그인/권한이 없는 단일 사용자 시스템이고 프로젝트 경계는 `project_id`다(`product-shell.md` 확정 제품 경계). 로그인 화면·세션·토큰은 범위 밖.
- **Review Inbox는 프론트를 위해 이미 설계됨**: v1.6.67 액션 어포던스가 list/detail·conflict·gate finding payload에 `{action, eligible, reason}`을 실어 "프론트가 한 계약으로 구동"하도록 만들어져 있다. `reason`은 display text, machine contract는 `action`+`eligible`.
- **Writing 흐름은 서버 오케스트레이션**: `/writing/generate`(context_search→generate), `/writing/revise-and-gate`(bounded loop), `/writing/accept`. 프론트는 상태 기계를 재구현하지 않고 결과를 표시한다.
- **Core SOT 계약**: 명시적 version save only(autosave 후속), draft save는 `idempotency_key` 필수, archive=읽기 허용+쓰기 409. 에디터는 이 계약을 그대로 따른다(자동 저장 도입은 별도 결정).
- Phase 7(대화형 수정·아이디에이션·저작 감독)은 계획·D1~D10 확정 상태이나 **순차상 프론트 이후**이며 슬라이스별 착수 브리프는 구현 시점에 만든다.

## D1 — framework / toolchain

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **D1=A. React + TypeScript + Vite (추천)** | SPA. 컴포넌트 단위로 에디터/Inbox/워크스페이스 구성, OpenAPI→TS 타입 생성. | 생태계·레퍼런스 최다(에디터/diff/가상 스크롤 라이브러리 선택지 넓음). LLM 보조 코딩의 학습 데이터가 가장 두꺼워 이 프로젝트의 작업 방식과 궁합이 좋다. TS가 50개 endpoint 계약을 컴파일 타임에 잡아준다. | 빌드 체인·의존성이 늘어난다. JSX/상태 관리 관례를 새로 도입. |
| D1=B. Vue 3 + TypeScript + Vite | 동일 SPA 구조, SFC(`.vue`) 기반. | 단일 파일 컴포넌트가 솔로 개발에 읽기 쉽고 보일러플레이트가 적다. 반응성 모델이 직관적. | React보다 레퍼런스·라이브러리 폭이 좁고, 이 저장소의 AI 보조 코딩 품질도 상대적으로 얇다. |
| D1=C. 서버 렌더링(Jinja2 + HTMX) | FastAPI가 HTML을 직접 렌더, 부분 갱신은 HTMX. 빌드 스텝 없음. | 빌드/의존성 0, CORS·클라이언트 상태 이중화 없음. 로컬 1인 도구에 가장 가벼움. | 에디터·candidate/gate 인터랙션·diff 뷰처럼 **클라이언트 상태가 두꺼운 화면**에서 금방 한계. Writing loop 결과(candidate+gate+stages)를 다루는 UI를 서버 왕복으로 만들면 오히려 복잡해진다. |
| D1=D. vanilla JS + Web Components | 프레임워크 없이 표준만. | 의존성 0, 수명 김. | 에디터·목록·diff를 전부 손으로. 속도가 가장 느리고 이득이 없다. |

**추천: D1=A.** 만들 화면이 폼 몇 개가 아니라 **원고 에디터 + Writing candidate/Gate 흐름 + Review Inbox diff**라 클라이언트 상태가 실제로 두껍다. D1=C는 이 프로젝트가 로컬 1인 도구라는 점에선 매력적이지만, 위 세 화면이 정확히 HTMX가 약한 지점이다. React/Vue 중에선 생태계와 AI 보조 코딩 품질에서 React가 앞선다 — 다만 오너가 Vue에 익숙하다면 **그 익숙함이 이 추천을 뒤집을 충분한 이유**다(솔로 프로젝트에서 유지보수자는 오너 본인).

## D2 — 서빙 / 배포 경계

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **D2=A. dev=Vite proxy, prod=application이 static 서빙 (추천)** | 개발은 Vite dev server가 `/api`를 application으로 proxy. 배포는 `npm run build` 산출물을 FastAPI가 StaticFiles로 서빙. | 단일 origin이라 **CORS 설정 자체가 불필요**. compose 서비스 추가 0. dev는 HMR 그대로. | application 이미지가 빌드 산출물을 포함(프론트 변경 시 이미지 재빌드). |
| D2=B. 별도 compose 서비스(nginx) | `frontend` 서비스가 정적 파일을 서빙, application은 API만. | 관심사 분리, 백/프론트 배포 독립. | compose 서비스·CORS 또는 nginx proxy 설정 추가. 1인 로컬 스택에 운영 표면만 늘린다. |
| D2=C. 완전 분리(프론트 별도 저장소/포트, CORS 허용) | application에 CORS 미들웨어 추가. | 프론트를 독립적으로 배포·교체. | monorepo 원칙과 어긋나고, 인증 없는 API에 CORS를 여는 건 로컬 도구에 불필요한 노출. |

**추천: D2=A.** 인증이 없는 단일 사용자 시스템에서 CORS를 여는 것(D2=C)은 이득 없이 표면만 넓힌다. D2=B의 배포 독립성은 1인 로컬 스택에서 쓸 일이 없다. A는 "dev는 편하고 prod는 단일 origin"을 둘 다 얻는다.

## D3 — 첫 슬라이스 범위

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **D3=A. Product shell 척추 먼저 (추천)** | 프로젝트 목록/생성 → 원고 목록 → 에디터(본문 편집·명시적 저장·version 목록) → 내보내기. | **내 글을 시스템에 넣는 유일한 경로.** 나머지 화면(Writing·Review)은 전부 project+draft가 존재해야 의미가 생긴다. 붙는 endpoint가 projects/drafts/snapshots로 좁아 첫 슬라이스가 작다. | 가장 "AI다운" 화면이 아니라, 첫 슬라이스에서 느끼는 재미는 적다. |
| D3=B. Review Inbox 먼저 | Phase 6 백엔드(어포던스 포함)를 그대로 구동하는 검토 화면. | 백엔드가 프론트를 위해 이미 설계돼 있어 조립이 가장 매끄럽다. | 검토할 candidate가 있으려면 원고 저장→분석이 선행. 에디터 없이는 API로 씨앗 데이터를 넣어야 해서 실사용 흐름이 안 닫힌다. |
| D3=C. Writing 작업공간 먼저 | generate→gate→accept 흐름 화면. | 이 시스템의 핵심 가치(이어쓰기)를 가장 먼저 눈으로 본다. | 역시 project+draft+context가 선행. current_position(draft/version)이 필요해 에디터 없이는 반쪽. |

**추천: D3=A → C → B.** 의존성이 방향을 강제한다: Writing은 `current_position`(draft_id+version_id)을, Review는 저장된 원고에서 나온 candidate를 전제한다. 척추(프로젝트→원고→에디터)를 먼저 세우면 C·B는 그 위에 얹는 화면이 된다. A 자체도 한 슬라이스로 크면 `프로젝트 목록+생성` / `에디터+저장+version` 둘로 쪼갠다.

## 추천 조합

**D1=A · D2=A · D3=A**(Vue 익숙 시 D1=B). 근거: 백엔드 50 endpoint가 이미 계약으로 잠겨 있어 프론트의 리스크는 "무엇을 만들까"가 아니라 "스택을 어디에 묶을까"다. 세 추천은 전부 **표면을 늘리지 않는 쪽**(CORS 없음, compose 서비스 없음, 신규 백엔드 없음)이며, 되돌릴 일이 생겨도 D3=A 척추는 어떤 framework에서도 다시 쓰인다.

## 이번 결정에 포함하지 않는 것 (기본값으로 진행)

브리프를 부풀리지 않기 위해, 아래는 관례적 기본값으로 두고 필요해질 때 바꾼다:

- **타입 계약 동기화**: FastAPI가 이미 OpenAPI를 노출하므로 스키마→TS 타입 **생성**을 기본으로 한다(50 endpoint를 손으로 타이핑하지 않는다). → **v1.6.94 구현에서 드러난 실제 범위**: 생성 타입은 **경로와 요청 바디만** 잠근다. 엔드포인트가 `-> dict[str, object]`로 주석돼 있어 OpenAPI 응답 schema가 `additionalProperties: true`(빈 object)로 나오기 때문이며, **응답 shape는 `frontend/src/api/client.ts`에 손으로 선언**한다. 갭 해소(백엔드 `response_model`)는 오너 결정 대기 — HANDOFF Owner Decisions Needed 참조.
- **데이터 계층**: 우선 얇은 `fetch` 래퍼. 캐시/무효화가 실제로 아플 때 TanStack Query 등을 도입한다(§2 — 미리 넣지 않는다).
- **에디터**: 1차는 `textarea` 수준의 평문 편집 + 명시적 저장. 리치 에디터(ProseMirror 등)는 실제 필요가 확인된 뒤.
- **테스트**: 프론트 테스트 도구는 첫 슬라이스에서 결정한다(백엔드 회귀 계약은 무변). → **v1.6.94에서 Vitest + React Testing Library로 확정**(오너 결정): Vite와 설정/트랜스폼을 공유해 추가 빌드 체인이 없고, 이 저장소의 양방향 회귀 관례를 프론트에도 그대로 적용한다. 각하: 도구 미도입(첫 회귀가 늦어짐), Playwright e2e(1인 로컬 스택에 운영 표면 증가).
- **스타일**: 최소 CSS로 시작, 디자인 시스템 미도입.

## Follow-up considerations

- **자동 저장**: Core SOT는 명시적 version save only이며 autosave는 기록된 후속이다. 에디터가 생기면 사용자가 가장 먼저 기대하는 기능이라, 도입 시 "저장=version mint" 계약을 바꿀지 별도 결정이 필요하다(무분별한 version 폭증 위험).
- **Writing loop 진행 표시**: `/writing/revise-and-gate`는 최대 60초(배포 기본 wall-clock)까지 걸릴 수 있다. 동기 요청의 로딩 UI로 갈지, 후속에 진행 스트리밍을 열지는 사용 후 결정.
- **Phase 7 접점**: P5 directive 감독면은 Phase 6와 공동 설계로 계획돼 있어, Review UI를 만들 때 Phase 7이 얹힐 자리를 의식해 둔다(지금 구현하지는 않는다).
- 프론트가 생기면 `product-shell.md`·`06-review-ui.md`의 `Draft` 상태를 구현과 함께 정리한다.

## Deferred / out of scope

- 계정·로그인·권한(제품 경계상 MVP 없음)
- 관계 graph visualization, 완전한 timeline 편집기, bulk review, style/voice 콘솔(`06-review-ui.md` 후속 범위)
- 리치 텍스트 에디터, 오프라인/PWA, 모바일 레이아웃
- 프론트 배포 파이프라인·CDN, 다중 사용자 동시 편집
- Phase 7 구현(순차상 프론트 이후, 슬라이스별 브리프 별도)
