# Phase 7 — 대화형 수정 · 아이디에이션 · 저작 감독 (Conversational Authoring)

상태: `Draft` (계획) — 구현 착수 전 슬라이스별 착수 브리프(`plans/07-*-decisions.md`)로 세부 확정.
아이디에이션 원본: [`../chat-revision-ideation.md`](../chat-revision-ideation.md)(근거·논의 이력).
의존: Phase 5(글 생성 + Writing Gate), Phase 6(후보 검토/큐레이션 — directive 감독면 **공동 설계**), Core SOT(draft/version·raw-offset·source_ref 앵커), ⑤ ContextPackage(검색 컨텍스트 재사용), Phase 2B(memory·scope key).

---

## 1. 목표

현재 글쓰기는 "새로 작성"에 가깝다. Phase 7은 **생성된 글을 놓고 반복 상호작용**하는 층을 더한다.

1. **부분 수정(revise)** — 이미 쓴 글의 선택 구간만 고친다(전체 재생성 아님).
2. **아이디에이션 회의(ideate)** — 초안을 놓고 브레인스토밍한다(초안 미반영 자문).
3. **저작 감독(directive)** — 저자가 메모리를 감독·관리하며 use/hold/skip·중요도·override를 남긴다(맥거핀 포함, 모든 분석 산출 대상).

**불변 제약**: 검색 컨텍스트 제공은 지금과 **동일**(⑤ ContextPackage seam 재사용). 대화 상태는 그 위에 직교로 얹는다.

## 2. 범위

**한다**: 생성물·대화의 DB 영속(1급 엔티티), revise/ideate task mode, 저작 감독 directive 층(개체 레지스트리 + 우선순위 트리), 분석 대화, micro/macro directive, Writing Gate·Phase 6 review와의 연동.

**안 한다(범위 밖)**: frontend editor/chat UI 자체(HANDOFF: editor shell 보류), 분석 추출 taxonomy 확장(2A D5=A 유지 — directive는 별개 개체 레지스트리 위에 얹음), 자동 canon 확정(§7 경계: 저자만 override).

## 3. 확정된 설계 결정 (아이디에이션에서 잠금, 2026-07-09)

착수 브리프는 아래를 **전제로** 시작한다(재논의 아님, 세부만 확정).

- **D1. 회의 ⟂ 수정 분리** — revise 산출은 candidate·Writing Gate 적용; ideate 산출은 advisory 로그(Gate 비적용/경량). **advisory→patch 자동 승격 금지**(승격은 사용자 명시 시그널만).
- **D2. 3계층 영속 + version=명시 시그널** — `draft_version`(저장/중간저장/채택 시그널 때만) ⟂ 미채택 AI 산출(low-stakes) ⟂ `conversation`/`conversation_turn`(대화 로그). 매 생성 턴은 version이 아니다.
- **D3. think 채널 분리** — `conversation_turn`에 `content_channel: thinking|answer`. thinking은 초안 미편입 + 컨텍스트 재주입 기본 제외(또는 요약).
- **D4. span ⟂ mode 직교** — 원문 span 지정(=grounding)과 모드(revise/ideate)는 별개 축. 같은 span을 양쪽에 써도 출력은 별도 채널에 기록.
- **D5. 정보관리 대상 = (b) 별개 개체 레지스트리** — 분석 추출은 3종 유지, directive는 개체 레지스트리 위에 얹는다(§4.5 (b)).
- **D6. directive = 저작 감독 모드** — 메모리가 메인, 저자가 저장 버전을 감독. macro(거버넌스)·micro(국소 즉석 교정) 두 스케일. **micro는 draft patch + memory 교정을 한 트랜잭션(atomic)으로 묶는다.**
- **D7. 서사 사실 우선순위 트리** — `저자 directive(override) > canonical 관찰 > candidate 관찰`. latest-win 기본, directive 우선. 충돌 시 임의 판단 없이 이 트리로 조정.
- **D8. §7 경계 + Phase 6 통합** — AI 감독 모드는 canonical **자동 확정/덮어쓰기 금지**(append-only 보존), override 권한은 저자만. 감독 큐레이션 표면은 Phase 6 review UI와 **중복 설계 금지·공동 설계**.
- **D9. importance ≠ confidence** — 저자 무게 vs AI 관찰 확신도는 별개 축. importance는 검색 랭킹 힌트로 연결(b-4 hybrid 튜닝 접점).
- **D10. 앵커 계약 재사용** — span·patch는 Core SOT raw-offset/`content_hash`/`source_block` 계약과 source_ref stale guard를 재사용(임의 다중-block 인용은 후속).

## 4. 구현 슬라이스 (권장 순서: P1 → P2 → P5 → P3 · P4)

| 슬라이스 | 내용 | 의존 | 착수 브리프에서 확정할 것 |
|---|---|---|---|
| **P1 대화·생성물 영속** | `conversation`/`conversation_turn`(content_channel 포함) + 저장 계약. version=명시 시그널(D2). 미채택 산출 별도 1급 여부(검토 D). | Core SOT | turn↔후보 겸용 vs 별도 컬렉션, 보존/만료 정책, 대화 상태 주입 채널(D3/T3) |
| **P2 수정 모드(revise)** | `task_type=revise` + patch 앵커(D10/T7) + Writing Gate 재사용. 채택→patch 전체 병합→새 version(T8). | P1, Phase 5 | 대상(커밋 version vs 미채택 턴), 다중 block 선택 허용 시점, 병합 충돌 처리 |
| **P5 저작 감독 / 정보관리** | 개체 레지스트리(D5) + `authoring_directive`(scope key 앵커, 우선순위 트리 D7, latest-win) + macro/micro(D6) + Gate Foreshadowing Control(D8/D9). | P1, Phase 6(공동) | 레지스트리 등록 경로, micro→macro 승격 임계, directive 이력(감사) 정책, 동명이인(HANDOFF (c)) |
| **P3 아이디에이션(ideate)** | `task_type=ideate` advisory 대화(Gate 비적용/경량, D1). | P1 | Gate 자세(비적용 vs 안전성만), 회의→수정 링크(승격 아님) |
| **P4 분석 대화** | analysis conversation. 근거 있으면 candidate 경로, 없으면 P5 directive(D4/T5). | P5 | 근거 판정 주체(span 지정 vs AI), 애매 시 기본 directive |

## 5. Phase 6와의 관계 (공동 설계)

D8대로 "저자가 메모리 버전을 큐레이션/감독"은 Phase 6 review UI(confirmed/rejected)와 같은 표면이다. Phase 6를 directive 감독 모드의 **데이터·상태 전이 기반**으로 삼고, Phase 7 P5는 그 위에 저자 의도 메타(use/hold/skip/importance·override·우선순위 트리)를 얹는다. 둘을 별도 서브시스템으로 중복 구현하지 않는다. *착수 시 Phase 6 계획과 P5 브리프를 함께 검토한다.*

## 6. 남은 미결 (착수 브리프 대상, 아이디에이션 §6 참조)

핵심 순: (1) micro→macro 승격 임계, (2) Phase 6 통합 범위(흡수 vs 선행 슬라이스), (3) 개체 레지스트리 등록 경로, (4) 속성형(분위기·톤)=scene/style 태그 분리, (5) timeline 순위 모델(chapter-scene 서수 proxy + partial order), (6) 앵커 staleness·patch 병합, (7) 대화 상태 주입/요약, (8) 동명이인 scope key. 전체 목록은 아이디에이션 §6.

## 7. 공통 완료 기준

- 각 슬라이스는 회귀(양방향 mutation)로 잠그고, 계약 literal 변경은 SoT 버전 로그에 기록한다(프로젝트 리듬).
- ⑤ ContextPackage seam·item·Gate 계약은 불변(대화/directive는 직교 확장). 위반 시 착수 브리프에서 계약 갱신을 명시 결정한다.
- §7 경계(AI 자동 canon 확정 금지)·append-only는 모든 슬라이스에서 보존한다.
