# 개인 글쓰기 AI 개발 계획

상태: `Draft`  
기준 원본: [`../abstract.md`](../abstract.md)  
목적: 2,000여 줄의 전체 초안을 실제 개발 전에 검토하고 확정할 수 있는 Phase 단위 계획으로 재구성한다.

서비스 경계와 확정된 계약을 먼저 볼 때는 [`../system-contract-sot.md`](../system-contract-sot.md)를 정본 SoT로 사용한다. 이 인덱스는 Phase별 세부 계획과 **모든 착수 결정 브리프**를 찾는 자리다.

> **브리프를 찾고 있다면 아래 "전체 인덱스"에서 트랙으로 좁힌다.** 이 디렉터리의 대다수(117개 중 97개)는
> `*-decisions.md` 착수 결정 브리프이며, **오너 결정의 근거 기록**이다. 파일명 접두 체계는 이미 무너져
> 있고(`00`~`07` 계열 + 접두 없는 최근 것들) 파일명만으로는 트랙을 알 수 없다 — 그래서 아래는 **접두가
> 아니라 트랙으로** 묶었다. 디렉터리 재편은 아직 결정되지 않은 별개 사안이다(HANDOFF 추적 부채).
>
> **새 계획·브리프를 쓰면 아래 표에 한 줄 추가한다.** 빠뜨리면 `tests/test_docs_indexes.py`가 실패한다 —
> 규칙이 아니라 강제다. 2026-08-02에 이 가드를 넣기 전까지 **90개 중 51개가 미등재**였고, 그래서
> 오너가 자기 결정 브리프를 찾지 못했다.

## 읽는 순서 (처음 오는 사람)

1. [`../system-contract-sot.md`](../system-contract-sot.md) — 서비스 경계, 확정 계약, 문서 우선순위. **여기가 정본이다**
2. [`00-foundations.md`](00-foundations.md) — 제품 경계와 전 Phase 공통 원칙
3. [`implementation-plan.md`](implementation-plan.md) — 배포 경계, 구현 순서, 단계별 검증
4. [`product-shell.md`](product-shell.md) — 프로젝트 관리, 원고 작업 공간, 내보내기
5. [`01-core-sot.md`](01-core-sot.md) — 저장, 버전, snapshot, block, source reference
6. [`flat-loop-gate.md`](flat-loop-gate.md) — Phase 2/4/5가 함께 소비하는 횡단 loop 계약

## 전체 인덱스

### 기반 · 횡단

| 문서 | 무엇 | 상태 |
|---|---|---|
| [`00-foundations.md`](00-foundations.md) | 제품 경계와 전 Phase 공통 원칙 | Draft |
| [`implementation-plan.md`](implementation-plan.md) | 배포 경계, 구현 순서, 단계별 검증 | Draft |
| [`product-shell.md`](product-shell.md) | 프로젝트/원고 작업 공간, 내보내기 | Draft |
| [`gemma4-reuse.md`](gemma4-reuse.md) | 기존 `gemma4_12b`의 재사용 범위와 보강점 | Reviewed |
| [`llm-gateway.md`](llm-gateway.md) | Gemma Q4 서빙 경계와 실모델 검증 | Proposed |
| [`flat-loop-gate.md`](flat-loop-gate.md) | flat agent loop 종료 decision·tool registry·budget·completion criteria | Draft(숫자 한도 확정) |
| [`analysis-memory-taxonomy.md`](analysis-memory-taxonomy.md) | 분석 대상과 저장 단위 논의안 | Discussion |
| [`product-readiness-backlog.md`](product-readiness-backlog.md) | 트리거가 올 때 하나씩 닫는 횡단 개선 백로그(새 Phase 아님) | Active |
| [`router-split-and-admin-separation-decisions.md`](router-split-and-admin-separation-decisions.md) | `main.py` 라우터 분해(**register 함수**) + 관리자 주소 분리(**ⓑ 별도 compose 서비스**) | **Resolved** — R1·A1(2026-08-05) · 구현 대기 |
| [`router-split-shared-prelude-decisions.md`](router-split-shared-prelude-decisions.md) | 공유 prelude 추출(라우터가 `..main` 을 안 보게) — H-3-A 순환 폐쇄 · 이동 134 정의/956줄 실측 | **Resolved·구현 완료**(2026-08-06, §5=ⓑ 범주 3분할 — `app/api/models.py`·`errors.py`·`dependencies.py`) |

### Phase 1 — Core SOT

| 문서 | 무엇 | 상태 |
|---|---|---|
| [`01-core-sot.md`](01-core-sot.md) | 저장·버전·snapshot·block·source reference | Draft |

### Phase 2A — 최초 분석

| 문서 | 무엇 | 상태 |
|---|---|---|
| [`02-analysis-pipeline.md`](02-analysis-pipeline.md) | 최초 추출과 기존 기억 대조·갱신 후보 | Draft(2A subset Approved) |
| [`02-analysis-kickoff-decisions.md`](02-analysis-kickoff-decisions.md) | 2A 착수 결정 | Approved |
| [`02-analysis-job-state-decisions.md`](02-analysis-job-state-decisions.md) | job/task 상태 전이 | Approved |
| [`02-analysis-runner-execution-decisions.md`](02-analysis-runner-execution-decisions.md) | runner 실행 경계 | Approved |
| [`02-analysis-provider-wiring-decisions.md`](02-analysis-provider-wiring-decisions.md) | provider/Gateway wiring | Approved |

### Phase 2B — 기존 기억 대조 · canonical memory

| 문서 | 무엇 | 상태 |
|---|---|---|
| [`02b-analysis-compare-kickoff-decisions.md`](02b-analysis-compare-kickoff-decisions.md) | 2B 착수 — 대조와 canonical memory | Resolved |
| [`02b-2-analysis-context-package-decisions.md`](02b-2-analysis-context-package-decisions.md) | 2B.2 prior-memory 검색용 ContextPackage(⑧) | Implemented(v1.6.41) |
| [`02b-3-analysis-compare-action-decisions.md`](02b-3-analysis-compare-action-decisions.md) | 2B.3 compare→action 판정과 scope key | Resolved |
| [`02b-4-memory-versioned-upsert-decisions.md`](02b-4-memory-versioned-upsert-decisions.md) | 2B.4 proposal→memory versioned upsert | Resolved |
| [`02b-4-review-queue-persistence-decisions.md`](02b-4-review-queue-persistence-decisions.md) | 2B.4 후속 — conflict review queue 영속화 | 브리프 |
| [`02b-5-memory-vector-reindex-decisions.md`](02b-5-memory-vector-reindex-decisions.md) | 2B.5 memory→vector 재색인 | 브리프 |
| [`02b-6-semantic-identity-resolution-decisions.md`](02b-6-semantic-identity-resolution-decisions.md) | 2B.6 event/open_question 의미적 identity resolution | 브리프 |
| [`02b-7-character-alias-homonym-decisions.md`](02b-7-character-alias-homonym-decisions.md) | 2B.7 character 별칭/동명이인 semantic 보강 | 브리프 |

| [`pending-candidate-identity-grouping-decisions.md`](pending-candidate-identity-grouping-decisions.md) | 서로 다른 분석 job의 미승인 후보 정체성 그룹·그룹 승인 | **확정 — C 채택**(2026-09-02 dogfood) |
| [`pending-candidate-identity-grouping-implementation-phases.md`](pending-candidate-identity-grouping-implementation-phases.md) | C 채택 후 미승인 후보 identity group 구현 슬라이스 분할 | Active — **Slice 0 완료·검증 B1 폐쇄**(2026-09-02, SoT v1.8.18), Slice 1(shortlist·판정 서비스) 다음 |

### Phase 3 — 파생 색인

| 문서 | 무엇 | 상태 |
|---|---|---|
| [`03-indexing.md`](03-indexing.md) | Chroma/Elasticsearch 파생 인덱스와 동기화 | Draft |
| [`03-indexing-kickoff-decisions.md`](03-indexing-kickoff-decisions.md) | Phase 3 착수 | Approved |
| [`03-index-sync-outbox-decisions.md`](03-index-sync-outbox-decisions.md) | 3B automatic sync/outbox | Approved |
| [`03-index-worker-retry-decisions.md`](03-index-worker-retry-decisions.md) | 3B worker/retry 실행 경계 | Approved |

### Phase 4 — Agentic Search · ContextPackage

| 문서 | 무엇 | 상태 |
|---|---|---|
| [`04-agentic-search.md`](04-agentic-search.md) | 검색 계획, 정본 재조회, ContextPackage | Draft |
| [`04-agentic-search-kickoff-decisions.md`](04-agentic-search-kickoff-decisions.md) | Phase 4 착수 | Approved |
| [`04-context-package-completion-decisions.md`](04-context-package-completion-decisions.md) | ContextPackage 완성(§8 C / §5 B) | Resolved |
| [`04-shared-vector-index-decisions.md`](04-shared-vector-index-decisions.md) | 공유 in-process vector index | Approved |
| [`04-real-vector-backend-decisions.md`](04-real-vector-backend-decisions.md) | 영속 vector 백엔드(Chroma). **cross-encoder 리랭커 유예의 출처** | Approved |
| [`04-compose-elasticsearch-service-decisions.md`](04-compose-elasticsearch-service-decisions.md) | compose 전용 ES 서비스(배포 lexical/hybrid) | 브리프 |
| [`04-es-lexical-backfill-decisions.md`](04-es-lexical-backfill-decisions.md) | ES-lexical backfill 스크립트 | 브리프 |
| [`04-worker-compose-outbox-bookkeeping-decisions.md`](04-worker-compose-outbox-bookkeeping-decisions.md) | index-sync worker compose 서비스 + outbox per-target bookkeeping | 브리프 |
| [`04-canonical-candidate-dedup-decisions.md`](04-canonical-candidate-dedup-decisions.md) | canonical↔candidate 승격 dedup | Resolved |
| [`04-writing-canonical-context-decisions.md`](04-writing-canonical-context-decisions.md) | Writing ContextPackage에 canonical memory 포함 | 브리프 |
| [`04-writing-candidate-context-decisions.md`](04-writing-candidate-context-decisions.md) | `needs_review` candidate의 Writing 포함 | Resolved |
| [`04-writing-candidate-retrieval-decisions.md`](04-writing-candidate-retrieval-decisions.md) | candidate lexical/vector retrieval | Resolved |
| [`04-writing-memory-vector-retrieval-decisions.md`](04-writing-memory-vector-retrieval-decisions.md) | memory retrieval의 vector 확장 | 브리프 |
| [`04-writing-memory-lexical-retrieval-decisions.md`](04-writing-memory-lexical-retrieval-decisions.md) | memory retrieval의 ES lexical 확장 | 브리프 |

### Phase 5 — Writing AI

| 문서 | 무엇 | 상태 |
|---|---|---|
| [`05-writing-ai.md`](05-writing-ai.md) | 컨텍스트 기반 생성과 Writing Gate | Draft |
| [`05-writing-generation-decisions.md`](05-writing-generation-decisions.md) | 5.1 생성 첫 슬라이스 | Resolved |
| [`05-writing-gate-decisions.md`](05-writing-gate-decisions.md) | 5.2 Writing Gate | Resolved |
| [`05-writing-accept-decisions.md`](05-writing-accept-decisions.md) | 5.3 accept→save→analysis 재진입 | Resolved |
| [`05-writing-self-report-decisions.md`](05-writing-self-report-decisions.md) | 5.4 candidate structured report | Resolved |
| [`05-writing-report-api-decisions.md`](05-writing-report-api-decisions.md) | 5.5 report 재평가 API | Resolved |
| [`05-writing-partial-revise-decisions.md`](05-writing-partial-revise-decisions.md) | 5.6 finding evidence 기반 부분 revise | Resolved |
| [`05-writing-revise-gate-decisions.md`](05-writing-revise-gate-decisions.md) | 5.7 partial revise → Gate 1회 합성 | Resolved |
| [`05-writing-revise-report-gate-decisions.md`](05-writing-revise-report-gate-decisions.md) | 5.7 partial revise → report → Gate 합성 | Resolved |
| [`05-writing-retrieve-more-decisions.md`](05-writing-retrieve-more-decisions.md) | 5.8 `retrieve_more` 1회 lifecycle | Resolved |
| [`05-writing-bounded-loop-decisions.md`](05-writing-bounded-loop-decisions.md) | 5.9 bounded revise/retrieve loop | Resolved |
| [`05-writing-persisted-loop-audit-decisions.md`](05-writing-persisted-loop-audit-decisions.md) | 5.9 후속 persisted loop audit(opt-in) | Resolved |
| [`05-writing-loop-budget-decisions.md`](05-writing-loop-budget-decisions.md) | 5.10 loop aggregate token/time budget | Resolved |
| [`05-writing-loop-benchmark-decisions.md`](05-writing-loop-benchmark-decisions.md) | 5.10 B2b full-stack loop benchmark | Resolved |
| [`05-writing-loop-ceiling-composition-decisions.md`](05-writing-loop-ceiling-composition-decisions.md) | 5.10 per-stage 비용에서 최악경로 합성(Option A) + 측정 M-i | Resolved |
| [`05-writing-gate-live-diagnostics-decisions.md`](05-writing-gate-live-diagnostics-decisions.md) | 5.10 live `invalid_gate_result` 관측·remediation | Resolved |
| [`05-writing-report-live-diagnostics-decisions.md`](05-writing-report-live-diagnostics-decisions.md) | 5.10 live `invalid_candidate_report` 관측·remediation | Resolved |
| [`05-writing-multi-finding-revise-decisions.md`](05-writing-multi-finding-revise-decisions.md) | 다수 continuity finding 순차 소진 | Resolved |
| [`05-writing-stable-context-pointer-decisions.md`](05-writing-stable-context-pointer-decisions.md) | stable `related_context_pointers` identity | Resolved |

### Phase 6 — Review UI

| 문서 | 무엇 | 상태 |
|---|---|---|
| [`06-review-ui.md`](06-review-ui.md) | 후보 검토와 프로젝트 메모리 관리 UI | Draft |
| [`06-review-inbox-backend-decisions.md`](06-review-inbox-backend-decisions.md) | Review Inbox 백엔드 착수 | 브리프 |
| [`06-review-inbox-affordances-decisions.md`](06-review-inbox-affordances-decisions.md) | Review Inbox 액션 어포던스 | Resolved |
| [`06-candidate-state-transition-decisions.md`](06-candidate-state-transition-decisions.md) | candidate 상태 전이 | Resolved |
| [`06-candidate-edit-decisions.md`](06-candidate-edit-decisions.md) | candidate edit 백엔드 계약 | Resolved |
| [`06-gate-finding-persistence-decisions.md`](06-gate-finding-persistence-decisions.md) | Gate finding 영속 + Review Inbox 통합 | Approved |

### Phase 7 — 대화형 저작 (미착수)

| 문서 | 무엇 | 상태 |
|---|---|---|
| [`07-conversational-authoring.md`](07-conversational-authoring.md) | 대화형 수정·아이디에이션·저작 감독. 원본 [`../chat-revision-ideation.md`](../chat-revision-ideation.md) | Draft |

### Phase 8 — 회원별 요청 제한 · Billing Readiness (계획됨)

| 문서 | 무엇 | 상태 |
|---|---|---|
| [`08-member-request-quota.md`](08-member-request-quota.md) | 회원별 **요청 횟수** quota·사용량 원장·관리자 CMS 백엔드·향후 결제 연결 seam | 상위 방향 승인 · 슬라이스별 브리프 대기 |
| [`08-0-billable-request-boundary-decisions.md`](08-0-billable-request-boundary-decisions.md) | 8.0 — "서비스 요청 1회"의 코드 대응(차감 단위·내부 repair/라운드·fan-out·조회성 경로·논리 요청 동일성·전수 가드) | **Resolved** — B1~B6=A |
| [`08-1-request-quota-policy-decisions.md`](08-1-request-quota-policy-decisions.md) | 8.1 — 한도 저장 계약(저장 위치·**일/주 이중 사용량 창**·창 파생/저장·기본과 override·무제한/정지 표현·변경 효력·기본값·구독 축 분리) | **Resolved** — P1~P8=확정, 구현 완료 |
| [`08-2-usage-ledger-decisions.md`](08-2-usage-ledger-decisions.md) | 8.2 — 사용량 원장(행 필드와 삭제 내성·중복 방지 키·집계 정본·보존 기간·관리자 조정 표현). L6(이름 이력)·L7(5초 DB 잠금)은 **8.2c·8.2b로 분리** | **Resolved** — L1=B·L2~L5=A, 구현 완료(v1.7.85) |
| [`08-2b-duplicate-request-lock-decisions.md`](08-2b-duplicate-request-lock-decisions.md) | 8.2b — 실수 중복 요청의 **DB 잠금**(L7: 잠금 수명·키 축·원자적 차지·확인 통과·실패 반환·에러 통로/상태코드) | **Resolved** — G1=C·G2~G6=A, 구현 완료(v1.7.87) · 재검증 **PASS**(2026-08-04) |
| [`08-2c-project-name-history-decisions.md`](08-2c-project-name-history-decisions.md) | 8.2c — 프로젝트 **이름 이력**(L6: 저장 위치·범위·쓰기 시점·조회 통로) + **D8-6 삭제 계약 개정** + **purge UI 문구** | **Resolved** — N1~N6=A(오너 2026-08-05) · 구현 대기 |
| [`08-3-quota-enforcement-decisions.md`](08-3-quota-enforcement-decisions.md) | 8.3 — quota **시행**(차감 시점·"성공"의 정의·비동기 차감·동시성 초과와 **입장 뮤텍스**·저장소 장애 방향·초과/정지 상태코드·확인 통로·시행 seam·`dedupe_key` 매핑) | **Resolved** — Q1~Q9 + Q1-a·Q1-b·Q3-a 확정, **구현 완료**(SoT v1.7.88) · 독립 검증 **PASS**(비차단 5건 처리) |
| [`08-4-product-wiring-decisions.md`](08-4-product-wiring-decisions.md) | 8.4 — 제품 경로 배선(관리자·내부 **면제** 여부·402/429/403 프론트 계약·**확인 대화 UX**·확인 헤더 층·**잔여 표시 API**·프론트 안정 키·유료 화면 전수 가드) | **Resolved** — W1(A+부트스트랩 무제한)·W2~W7 확정 |
| [`08-5-usage-admin-cms-decisions.md`](08-5-usage-admin-cms-decisions.md) | 8.5 — 관리자 quota 운영 API(조회·한도 변경·**정지/해제**·사유·감사 — endpoint 5종, ADMIN 11→16) | **Resolved** — D1~D3 확정(2026-08-23) · **구현 완료**(8.5-a v1.8.1 · 8.5-b v1.8.2, 독립 검증 대기) |

### Phase 9 — 서비스 활동 로그 (계획됨)

| 문서 | 무엇 | 상태 |
|---|---|---|
| [`09-service-activity-log.md`](09-service-activity-log.md) | 사용자 행위 기록(누가·언제·무엇을 바꿨는가). **`system_events`는 문서에만 있고 코드 0줄**이라는 실측 공백에서 출발한다. 8.2c §N2-a가 발원 | 페이즈 신설 확정(오너 2026-08-05) · **9.0 구현·검증 완료(2026-08-09)** · 부모 계획 |
| [`09-0-service-activity-log-decisions.md`](09-0-service-activity-log-decisions.md) | 9.0 — 착수 결정(저장 위치·**기록 범위**·문서 형태·**실패 방향**·조회 통로·보존·**쓰기 지점과 누락 가드**·원장 중복) | **Resolved(2026-08-09)** — A1~A8 확정 · 구현·검증 완료 · **A2 추가 확정 19→20**(`writing/accept`) |
| [`09-1-activity-timeline-screen-decisions.md`](09-1-activity-timeline-screen-decisions.md) | 9.1 — 활동 타임라인 **화면** 착수 결정(화면의 자리 · **최신 100건 상한** · 행위자 표시 · 라벨 정본 · **replay 중복** · target 링크) | **Resolved(2026-08-10) · 구현 완료(SoT v1.7.94)** — S1~S6 확정 · **계약 영향 0 · backend 프로덕션 0줄** · 구현이 S6 전제를 반증(→ **F7**) · ★ §"나중에 여는 문" **F1~F7**(트리거 포함, 구현 뒤에도 유지) |
| [`09-2-personal-hub-and-ia-decisions.md`](09-2-personal-hub-and-ia-decisions.md) | 9.2 — 개인 페이지(**전체 통합 허브**) + 프론트 IA 재배치(**통합 활동 조회** · 상한 · 관측 통합 여부 · 주소 · 관리자 랜딩 · 로그인/랜딩 · 프로젝트 화면 링크 정리) | **Resolved · 구현 완료(2026-08-10, SoT v1.7.96)** — P1~P8 · operation 77 → **78** · ★ 독립 검증이 P1 논거를 반증(fan-out 은 N≤상한이면 정확) → 근거 재작성·**P8 신설** · P4 보안 3항(S-1 AuthGate 축소 · S-2 open redirect · S-3 IDOR) |

### 프론트 디자인 (Phase 10)

| 문서 | 무엇 | 상태 |
|---|---|---|
| [`10-frontend-design-system-decisions.md`](10-frontend-design-system-decisions.md) | Phase 10 — 디자인 시스템 착수 결정(범위 · 토큰 체계 · **활동 100건 표시** · **`/me` 진입점** · 제품명 · 다크 모드) | **Resolved(2026-08-11) · 구현 대기** — D1~D6 확정 · **계약 영향 0 · backend 0줄** · ★ **D2 는 구현자 권고(현행 유지)를 오너가 기각**했고 그것이 옳았다(현행 크림+테라코타 = AI 디자인 기본값) → **잉크블루 팔레트**를 OKLCH+WCAG 2.2 로 계산해 세움([`10_palette_contrast.py`](10_palette_contrast.py), 18짝 전수 통과) · ★ 실측: `toHaveClass` **0**·`ByTestId` **0** 이라 **순수 시각 변경은 회귀 비용 0**, 비싼 것은 문구 311곳·접근성 semantics 478곳 |

### 프론트엔드

| 문서 | 무엇 | 상태 |
|---|---|---|
| [`frontend-kickoff-decisions.md`](frontend-kickoff-decisions.md) | framework/toolchain·서빙 경계·첫 슬라이스(React+TS+Vite, 별도 nginx) | Resolved |
| [`frontend-project-navigation-decisions.md`](frontend-project-navigation-decisions.md) | 프로젝트 목록→원고 내비게이션(react-router) | Resolved |
| [`frontend-editor-save-decisions.md`](frontend-editor-save-decisions.md) | editor·명시적 save | Resolved |
| [`frontend-writing-workspace-decisions.md`](frontend-writing-workspace-decisions.md) | Writing 작업공간 | Resolved |
| [`frontend-review-inbox-decisions.md`](frontend-review-inbox-decisions.md) | Review Inbox 첫 슬라이스 범위 | Resolved |
| [`writing-workspace-v2-w0-contract.md`](writing-workspace-v2-w0-contract.md) | Workspace V2 W0 exact contract(ProjectBrief·ordered unit·accept 원자성) | W0~W4 완료 |
| [`chapter-scene-hierarchy-decisions.md`](chapter-scene-hierarchy-decisions.md) | 평면 ordered unit을 **장→장면 실제 계층**으로 전환(저장 모델·본문 소유·무손실 이관·정렬·Writing intent·삭제·export) | **Resolved(2026-08-28)** — D1~D6·D8=A, D7=B · 구현 진행 |
| [`scene-note-decisions.md`](scene-note-decisions.md) | 장면 메모 기능(화면 위치·저장 단위·공개 범위·저장 경험) | **Resolved** — D1=C+A · D2~D4=A |
| [`scene-note-implementation-phases.md`](scene-note-implementation-phases.md) | 장면 메모 구현 순서(Slice 0~4: 저장→읽기→쓰기→화면→드로어) | **Active** — Slice 0·1·2 완료, Slice 3부터 |
| [`final-save-analysis-decisions.md`](final-save-analysis-decisions.md) | Scene 최종 저장 1회·분석 연동·후속 수정 상태 | **Resolved(2026-09-01)** — D1~D3=B · D4=A(서버 동기 실행) · D5=A(분석 실패는 200 + `analysis_error`) |

### 공개 API 계약

| 문서 | 무엇 | 상태 |
|---|---|---|
| [`frontend-api-contract-decisions.md`](frontend-api-contract-decisions.md) | H1 응답 모델 · H2 이름 입력 검증 | Resolved(v1.6.95) |
| [`api-error-response-contract-decisions.md`](api-error-response-contract-decisions.md) | H3 에러 응답 계약(균일 `{"detail"}`·상태코드 의미론) | Resolved |
| [`auto-promote-partial-failure-decisions.md`](auto-promote-partial-failure-decisions.md) | `auto_promote_job` 부분 실패 의미론 | Approved |

### 생성 제어 · 컨텍스트 예산

| 문서 | 무엇 | 상태 |
|---|---|---|
| [`writing-style-and-length-control-decisions.md`](writing-style-and-length-control-decisions.md) | 문체/어투 3층 계약과 생성 분량 프리셋 | 구현 완료 |
| [`unaccepted-candidate-persistence-decisions.md`](unaccepted-candidate-persistence-decisions.md) | 미채택 candidate 영속(scratch) | 완료(v1.7.20) |
| [`async-generation-pad-decisions.md`](async-generation-pad-decisions.md) | 비동기 생성 + 결과 패드 | 구현 완료 |
| [`context-budget-korean-tokens-decisions.md`](context-budget-korean-tokens-decisions.md) | 한글 토큰 환산·K-3 창 가드·R-e·R-a 유도·K-4 카운터. **트랙 종료** | 완료 |

### 관측 KPI

| 문서 | 무엇 | 상태 |
|---|---|---|
| [`observability-kpi-decisions.md`](observability-kpi-decisions.md) | 관측 KPI 페이즈 착수 | Approved |
| [`observability-instrumentation-seam-decisions.md`](observability-instrumentation-seam-decisions.md) | 계측 seam(=provider 데코레이터 C) | Approved |
| [`observability-site-mapping-decisions.md`](observability-site-mapping-decisions.md) | site 매핑 · scope 개방 범위 · `parse_error` 재분류 | Approved |
| [`observability-kpi-readout-decisions.md`](observability-kpi-readout-decisions.md) | 집계 API read-out | Approved |
| [`observability-dashboard-decisions.md`](observability-dashboard-decisions.md) | 대시보드 화면 첫 슬라이스 | Approved |

### 다중 사용자 인증 (D8)

| 문서 | 무엇 | 상태 |
|---|---|---|
| [`multi-user-auth-cms-decisions.md`](multi-user-auth-cms-decisions.md) | **부모 브리프** — 인증·소유권·CMS/관리자 D0~D8 | D0~D8 결정됨 |
| [`auth-d8-3-enforcement-decisions.md`](auth-d8-3-enforcement-decisions.md) | D8-3 인가 시행(E1~E4) | Resolved |
| [`auth-d8-5-admin-decisions.md`](auth-d8-5-admin-decisions.md) | D8-5 관리자 API·화면·승격·최초 비밀번호 교체 | Implemented(v1.7.56~v1.7.81) |
| [`auth-d8-6-purge-ui-decisions.md`](auth-d8-6-purge-ui-decisions.md) | D8-6 영구 삭제 UI·2단계 시행·삭제 감사·재시도 의미 | Verified PASS(v1.7.82, c2ca946) |
| [`auth-d8-7-infra-auth-decisions.md`](auth-d8-7-infra-auth-decisions.md) | D8-7 인프라 노출면·자격증명 | **G1=C 확정** / G2~G6 유예 |
| [`auth-signup-approval-decisions.md`](auth-signup-approval-decisions.md) | 자기 가입(승인제) — v1.7.82 가입 금지 문구 개정·403 생산자 셋·브루트포스 잠금·시드 정리 | **Resolved(2026-08-22)** — 403+사유 / 방어 동봉 / 시드 정리+오너 계정 |

### 외부 확장 (배선 완료 · 어댑터 미착수)

| 문서 | 무엇 | 상태 |
|---|---|---|
| [`external-api-expansion-decisions.md`](external-api-expansion-decisions.md) | **부모 브리프** — 외부 LLM·임베딩·뉴럴 리랭커 확장(D1~D6) | D1~D6 결정됨 · compose 배선 완료(2026-08-14) · 임베딩/리랭커 어댑터 미착수 |
| [`reranker-slice-decisions.md`](reranker-slice-decisions.md) | D5 가 남긴 넷 — 착수 순서·조달 순서(self-host↔외부)·삽입 모양·완료 기준 | **Resolved(2026-08-18)** — 1=A·2=A·3=A·4=A+C(하네스 선작성). 착수는 임베딩 어댑터 뒤 |
| [`script-rot-guard-decisions.md`](script-rot-guard-decisions.md) | 실행되지 않는 코드(`scripts/`)의 시그니처 부패를 무엇으로 막는가 · 감마의 부분 green 표기 | **Resolved(2026-08-20)** — 1=B(mypy 단독) · 1-b=가(`requirements-dev.txt`) · 2=D. **초판 추천 A 가 실측으로 뒤집혔다** |
| [`embedding-adapter-slice-decisions.md`](embedding-adapter-slice-decisions.md) | **다음 슬라이스** — OpenAI 형식 어댑터 자리·배치·차원 전환·조립 누락 방지 | **Resolved(2026-08-19)** — 넷 다 A. 재색인 설명은 README 절로 함께 나간다(오너 조건) |
| [`external-api-fallback-decisions.md`](external-api-fallback-decisions.md) | 키 회전(1순위)·모델 폴백(2순위) — 세 축 공통 폴백 정책(a1→b1→c1→a2→b2→c2·RPM 30·fail-fast) | **구현 완료(2026-08-22)** — 부모 브리프 §4의 401/429/5xx 매핑을 `KEY_REJECTED`로 폐쇄 |

## 문서 지위와 우선순위

현재 구현 계획은 검토 전 `Draft`이고 분석 taxonomy는 `Discussion`이다. 개발 착수 전 관련 `착수 전 결정사항`을 해소하고 구현 기준 문서의 상태를 `Approved`로 바꿔야 한다.

충돌 시 문서 우선순위는 [`../system-contract-sot.md`](../system-contract-sot.md)의 **문서 우선순위**를 정본으로 따른다. 요약:

1. 사용자가 명시 승인해 SoT 또는 해당 Phase 계획에 반영된 결정
2. `Approved` 상태의 SoT와 Phase 계획
3. `Draft` 상태이지만 구현·검증·커밋으로 잠긴 계약 문서
4. `docs/plans/`의 미구현 Phase 계획
5. `docs/` 루트의 아이디에이션 문서

동일 우선순위 문서끼리 충돌하면 어느 한쪽을 조용히 선택하지 않고 사용자에게 기준을 확인한다. 상세와 최종 판정은 SoT에 있다.

## Phase와 MVP의 관계

원문의 Phase는 기술 의존성에 따른 구현 순서이고, MVP는 사용자에게 전달할 가치 묶음이다. 둘은 1:1 관계가 아니다.

| 계획 단계 | 주 산출물 | 기여하는 가치 묶음 |
|---|---|---|
| Foundation Spike | 실행 골격, LLM 계약, Gemma Q4 기준선 | 전 Phase 기술 기준 |
| Product Shell | 프로젝트 CRUD, 작업 공간, 원고 내보내기 | 전 MVP의 사용자 진입점 |
| Phase 1 | MongoDB 정본과 근거 포인터 | MVP 1 기반 |
| Phase 2A | 최초 원고의 구조화 기억 후보 추출 | MVP 1 기반 |
| Phase 3 | 검색용 파생 인덱스 | MVP 1 기반 |
| Phase 4 | 검증된 ContextPackage | MVP 1 검색 루프 |
| Phase 2B | 기존 기억과 대조한 신규·갱신·충돌 후보 | 반복 분석 정확도 |
| Phase 5 | 이어쓰기와 생성 검증 | MVP 1 완성, MVP 2·3 확장점 |
| Phase 6 | 후보 검토/승인 UI | MVP 4 기반, MVP 2 운영 화면 |
| Phase 7 | 대화형 수정·아이디에이션·저작 감독(directive) | 반복 편집 루프, 저자 정보관리(맥거핀 등) |
| Phase 8 | 회원별 요청 횟수 제한·사용량 운영·결제 연결 seam | 서비스 BM/구독 전환 기반 |
| Phase 9 | 사용자 행위 기록(생성·개명·저장·archive)과 그 조회 | 다중 사용자 운영·문의 대응 |

MVP 2의 Continuity/POV, MVP 3의 Voice RAG는 초기 6개 Phase 이후 별도 증분 계획으로 구체화해야 한다. Phase 6에서 모든 고급 기능을 한꺼번에 구현한다는 뜻은 아니다.

Phase 2는 순환 의존성을 피하기 위해 두 구현 slice로 검토한다. 2A는 prior memory 없이 최초 후보를 만들고, Phase 3~4가 준비된 뒤 2B가 Agentic Search/RAG로 기존 기억과 대조한다. 이 순서는 아직 `Draft`이며 Phase 2 착수 전에 확정한다.

## 공통 완료 기준

각 Phase는 다음 조건을 만족해야 다음 단계의 안정적인 입력으로 간주한다.

- 공개 입력·출력 계약과 상태값이 확정되어 있다.
- 정상 흐름과 실패 흐름의 수용 기준이 있다.
- `project_id` 격리와 source pointer 추적성이 유지된다.
- MongoDB와 파생 인덱스의 책임 경계가 뒤집히지 않는다.
- 후속 Phase가 사용할 최소 예제 또는 fixture가 있다.
- 검증 방법과 완료 증거를 작업 로그에 남긴다.

## 원문 추적표

| `abstract.md` 영역 | 계획 문서 |
|---|---|
| §0~4, §16, §18 | `00-foundations.md` 및 관련 Phase 흐름 |
| §0의 로컬 LLM gateway 전제 | `implementation-plan.md`, `gemma4-reuse.md`, `llm-gateway.md` |
| 원문에 상세 계획 없음 | `product-shell.md` |
| §8 일부, §13.2 | `01-core-sot.md` |
| §7~8의 분석 대상 후보 | `analysis-memory-taxonomy.md` |
| §7, §12.3 일부, §13.4, §14.2 | `02-analysis-pipeline.md` |
| §9~11, §16.2~16.3 | `03-indexing.md` |
| §5, §12.2, §13.3, §14.3 | `04-agentic-search.md` |
| §6, §12.3~12.5, §13.1, §14.1 | `05-writing-ai.md` |
| §15.4 및 Phase 6 항목 | `06-review-ui.md` |
| §15~17 | 이 인덱스와 각 Phase의 범위/후속 계획 |

상세 JSON 예시와 대안은 원문 및 주제별 아이디에이션 문서에 그대로 보존한다. Phase 계획에서는 착수 판단에 필요한 계약, 경계, 산출물, 결정사항만 관리한다.
