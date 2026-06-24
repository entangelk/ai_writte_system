# 개인 글쓰기 AI 개발 계획

상태: `Draft`  
기준 원본: [`../abstract.md`](../abstract.md)  
목적: 2,000여 줄의 전체 초안을 실제 개발 전에 검토하고 확정할 수 있는 Phase 단위 계획으로 재구성한다.

## 읽는 순서

1. [`00-foundations.md`](00-foundations.md) — 제품 경계와 전 Phase 공통 원칙
2. [`implementation-plan.md`](implementation-plan.md) — 배포 경계, 구현 순서, 단계별 검증
3. [`gemma4-reuse.md`](gemma4-reuse.md) — 기존 `gemma4_12b`의 재사용 범위와 보강점
4. [`llm-gateway.md`](llm-gateway.md) — Gemma Q4 서빙 경계와 실모델 검증
5. [`product-shell.md`](product-shell.md) — 프로젝트 관리, 원고 작업 공간, 내보내기
6. [`01-core-sot.md`](01-core-sot.md) — 저장, 버전, snapshot, block, source reference
7. [`analysis-memory-taxonomy.md`](analysis-memory-taxonomy.md) — 분석 대상과 저장 단위 논의안
8. [`02-analysis-pipeline.md`](02-analysis-pipeline.md) — 최초 추출과 기존 기억 대조·갱신 후보
9. [`03-indexing.md`](03-indexing.md) — ChromaDB/Elasticsearch 파생 인덱스와 동기화
10. [`04-agentic-search.md`](04-agentic-search.md) — 검색 계획, 정본 재조회, ContextPackage
11. [`05-writing-ai.md`](05-writing-ai.md) — 컨텍스트 기반 글 생성과 Writing Gate
12. [`06-review-ui.md`](06-review-ui.md) — 후보 검토와 프로젝트 메모리 관리 UI
13. [`flat-loop-gate.md`](flat-loop-gate.md) — flat agent loop 종료 decision, tool registry, budget policy 계약(숫자 기본 한도/completion은 후속 slice). Phase 2/4/5가 소비하는 횡단 계약

## 문서 지위와 우선순위

현재 구현 계획은 검토 전 `Draft`이고 분석 taxonomy는 `Discussion`이다. 개발 착수 전 관련 `착수 전 결정사항`을 해소하고 구현 기준 문서의 상태를 `Approved`로 바꿔야 한다.

충돌 시 우선순위는 다음과 같다.

1. 사용자가 명시적으로 승인해 해당 Phase 문서에 반영된 결정
2. `Approved` 상태의 Phase 계획과 공통 기반 문서
3. `docs/` 루트의 아이디에이션 문서

동일 우선순위 문서끼리 충돌하면 어느 한쪽을 조용히 선택하지 않고 사용자에게 기준을 확인한다.

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
