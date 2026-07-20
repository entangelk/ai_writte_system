# 개인 글쓰기 AI 개발 계획

상태: `Draft`  
기준 원본: [`../abstract.md`](../abstract.md)  
목적: 2,000여 줄의 전체 초안을 실제 개발 전에 검토하고 확정할 수 있는 Phase 단위 계획으로 재구성한다.

서비스 경계와 확정된 계약을 먼저 볼 때는 [`../system-contract-sot.md`](../system-contract-sot.md)를 정본 SoT로 사용한다. 이 인덱스는 Phase별 세부 계획을 읽는 순서다.

## 읽는 순서

1. [`../system-contract-sot.md`](../system-contract-sot.md) — 서비스 경계, 확정 계약, 문서 우선순위
2. [`00-foundations.md`](00-foundations.md) — 제품 경계와 전 Phase 공통 원칙
3. [`implementation-plan.md`](implementation-plan.md) — 배포 경계, 구현 순서, 단계별 검증
4. [`gemma4-reuse.md`](gemma4-reuse.md) — 기존 `gemma4_12b`의 재사용 범위와 보강점
5. [`llm-gateway.md`](llm-gateway.md) — Gemma Q4 서빙 경계와 실모델 검증
6. [`product-shell.md`](product-shell.md) — 프로젝트 관리, 원고 작업 공간, 내보내기
7. [`01-core-sot.md`](01-core-sot.md) — 저장, 버전, snapshot, block, source reference
8. [`analysis-memory-taxonomy.md`](analysis-memory-taxonomy.md) — 분석 대상과 저장 단위 논의안
9. [`02-analysis-kickoff-decisions.md`](02-analysis-kickoff-decisions.md) — Phase 2A 착수 전 사용자 결정 브리프
10. [`02-analysis-job-state-decisions.md`](02-analysis-job-state-decisions.md) — Phase 2A job 상태 전이 결정 브리프
11. [`02-analysis-runner-execution-decisions.md`](02-analysis-runner-execution-decisions.md) — Phase 2A runner 실행 경계 결정 브리프
12. [`02-analysis-provider-wiring-decisions.md`](02-analysis-provider-wiring-decisions.md) — Phase 2A provider/Gateway wiring 결정 브리프
13. [`02-analysis-pipeline.md`](02-analysis-pipeline.md) — 최초 추출과 기존 기억 대조·갱신 후보
14. [`03-indexing-kickoff-decisions.md`](03-indexing-kickoff-decisions.md) — Phase 3 indexing 착수 결정 브리프
15. [`03-index-sync-outbox-decisions.md`](03-index-sync-outbox-decisions.md) — Phase 3B automatic sync/outbox 결정 브리프
16. [`03-index-worker-retry-decisions.md`](03-index-worker-retry-decisions.md) — Phase 3B worker/retry 실행 경계 결정 브리프
17. [`03-indexing.md`](03-indexing.md) — ChromaDB/Elasticsearch 파생 인덱스와 동기화
18. [`04-agentic-search-kickoff-decisions.md`](04-agentic-search-kickoff-decisions.md) — Phase 4 착수 전 사용자 결정 브리프
19. [`04-agentic-search.md`](04-agentic-search.md) — 검색 계획, 정본 재조회, ContextPackage
20. [`05-writing-ai.md`](05-writing-ai.md) — 컨텍스트 기반 글 생성과 Writing Gate
21. [`06-review-ui.md`](06-review-ui.md) — 후보 검토와 프로젝트 메모리 관리 UI
22. [`07-conversational-authoring.md`](07-conversational-authoring.md) — Phase 7: 대화형 수정·아이디에이션·저작 감독(directive). 아이디에이션 원본 [`../chat-revision-ideation.md`](../chat-revision-ideation.md)
23. [`flat-loop-gate.md`](flat-loop-gate.md) — flat agent loop 종료 decision, tool registry, budget policy, task별 completion criteria와 benchmark 기반 숫자 기본 한도. Phase 2/4/5가 소비하는 횡단 계약
24. [`05-writing-loop-benchmark-decisions.md`](05-writing-loop-benchmark-decisions.md) — Phase 5.10 B2b full-stack loop benchmark의 계측 경계·대표 workload·기본값 승격 결정 브리프
25. [`05-writing-gate-live-diagnostics-decisions.md`](05-writing-gate-live-diagnostics-decisions.md) — Phase 5.10 live `invalid_gate_result`의 raw output 관측 경계와 remediation 순서 결정 브리프
26. [`05-writing-report-live-diagnostics-decisions.md`](05-writing-report-live-diagnostics-decisions.md) — Phase 5.10 live `invalid_candidate_report`의 raw report output(first+repair) 관측 경계와 remediation 순서 결정 브리프
27. [`05-writing-loop-ceiling-composition-decisions.md`](05-writing-loop-ceiling-composition-decisions.md) — Phase 5.10 B2b aggregate ceiling을 per-stage 비용에서 최악경로로 합성하는 Option A 결정 브리프(`unexpected_loop_trace` 조사 결론 + Gate 독립성) + 측정 메커니즘 M-i
28. [`05-writing-multi-finding-revise-decisions.md`](05-writing-multi-finding-revise-decisions.md) — Writing loop이 Gate revise 분기의 다수 continuity finding을 순차 소진하도록 자격 함수를 완화하는 결정 브리프(D1=A continuity-only·D2=A sequential·D3=A severity desc)
29. [`05-writing-stable-context-pointer-decisions.md`](05-writing-stable-context-pointer-decisions.md) — candidate claim full schema의 stable `related_context_pointers` identity·모델 노출/검증·필수성을 잠근 결정 브리프(Resolved: D1=A·D2=A·D3=A; 기존 self-report D2=A first→B의 B 확장 승인)
30. [`frontend-kickoff-decisions.md`](frontend-kickoff-decisions.md) — 프론트엔드 착수의 framework/toolchain·서빙 경계·첫 슬라이스 범위 결정 브리프(Resolved: D1=A React+TS+Vite · D2=B 별도 nginx compose 서비스 · D3=A Product shell 척추 우선; v1.1부터의 "frontend framework 보류" 해소)
31. [`frontend-api-contract-decisions.md`](frontend-api-contract-decisions.md) — 백엔드 공개 계약 조이기(H1 응답 모델 · H2 이름 입력 검증)의 범위·방식·검증 위치 결정 브리프(Resolved: D1=A 척추 14 endpoint · D2=A `response_model=` 파라미터 · D3=A HTTP 경계 422; `JSONResponse` 2개는 구조적 예외로 Deferred)
32. [`product-readiness-backlog.md`](product-readiness-backlog.md) — 프론트 핵심 루프를 우선 완성하면서 `main.py` 점진 분리·Lite/Full·dogfood 품질 지표·문서 절차·저장소 이름·라이선스를 **각 착수 트리거가 왔을 때 하나씩 닫는 횡단 개선 백로그**(새 Phase/public contract 아님)
33. [`frontend-project-navigation-decisions.md`](frontend-project-navigation-decisions.md) — 프로젝트 목록→원고 작업 공간의 첫 상세 내비게이션 결정 브리프(Resolved: A `react-router` Declarative BrowserRouter; 오너는 B를 선호했으나 editor·Writing·Review 확장성을 우선, v1.6.96 구현)
34. [`frontend-editor-save-decisions.md`](frontend-editor-save-decisions.md) — Product shell A1/A2 editor·명시적 save 착수 브리프(Resolved: D1=A 저장 intent별 UUID/exact payload 결박 · D2=A draft route+version component state, B query는 additive 후속 · D3=A A1 editor/save→A2 history/export 분리; SoT v1.6.97)
35. [`frontend-writing-workspace-decisions.md`](frontend-writing-workspace-decisions.md) — Product shell C Writing 작업공간 착수 브리프(Resolved: D1=A clean latest+사용자 설명 · D2=A 기본 generate→Gate→accept 먼저 · D3=A 성공/partial HTTP model+OpenAPI · D4=A read-only candidate first, 부분 수정 UX는 C1 후 재검토 · D5=A C0→C1→C2)
36. [`writing-workspace-v2-w0-contract.md`](writing-workspace-v2-w0-contract.md) — 오너 승인 Workspace V2의 W0 exact contract(ProjectBrief version/API, ordered unit/reorder/migration, `append_current|start_next_unit` accept 원자성·멱등, 양방향 regression matrix). W0 완료, runtime 구현은 W2/W3에서 수행. W4 export 계약은 §6
37. [`unaccepted-candidate-persistence-decisions.md`](unaccepted-candidate-persistence-decisions.md) — 미채택 Writing candidate 영속. **완료** (D0=B/D1=B/D2=A, 구현·독립 검증 2회 합격, 보존/만료 정책은 SoT v1.7.20 정본 승격)
38. [`writing-style-and-length-control-decisions.md`](writing-style-and-length-control-decisions.md) — 문체/어투 계약(**설정·관찰·검증 3층**)과 생성 분량 제어 **제안 브리프(오너 결정 대기, 구현 미착수, D0~D6)**. 문체를 **키 유무로 3축 분해**(작품 문체=project / **캐릭터 어투=character** / 분위기=키 없음→Phase 7 몫). **어투 계약이 `ProjectBrief.tone`(정본·배선됨)과 `WritingBrief.tone`(Phase 5·죽은 경로)로 중복 존재하는 모순을 D1에서 정리**해야 하고, **D4(캐릭터 어투 payload)는 오너가 "taxonomy 동결"의 의미를 3종 유지인지 payload까지 불변인지 확인해 줘야 진행 가능**

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
