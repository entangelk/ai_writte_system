# 문서 안내

> 저장소를 처음 본다면 최상위 [`../README.md`](../README.md)가 **기획 · 개발 · 서비스** 세 축의
> 진입점이다. 이 문서는 그보다 아래, **어떤 성격의 기록이 어디에 쌓이는지**의 지도다.

| 성격 | 어디 | 무엇이 쌓이나 |
|---|---|---|
| **기획** | [`product-overview.md`](product-overview.md) · [`observability-kpi-rationale.md`](observability-kpi-rationale.md) · [`plans/00-foundations.md`](plans/00-foundations.md) · [`plans/product-readiness-backlog.md`](plans/product-readiness-backlog.md) · (원본) [`abstract.md`](abstract.md) | 제품 컨셉·MVP 범위·설계 원칙·운영 KPI의 근거 |
| **계약** | [`system-contract-sot.md`](system-contract-sot.md) | 확정된 계약의 **현재 정본**과 버전별 변경 이유 |
| **결정** | [`plans/README.md`](plans/README.md) | Phase 계획 + 착수 결정 브리프 89개 |
| **검증** | [`verifications/README.md`](verifications/README.md) | 독립 검증 기록 237건(반증 시도·뮤테이션·판정) |
| **실행 이력** | [`daily_logs/`](daily_logs/) | 일자별 작업 로그·오너 결정·실측값 |
| **서비스/운영** | [`runbooks/`](runbooks/local-llama-server.md) · [`benchmarks/`](benchmarks/2026-07-15/writing_loop_per_stage_ceiling_q4.md) · [`live_review_briefs/`](live_review_briefs/2026-07-18/writing_workspace_ux_restructure.md) | 기동 절차·성능 실측·실사용 검수에서 온 계약 재협상 |
| **작업 절차** | [`guides/`](guides/records-and-handoff.md) | 기록·인수인계 규칙, 독립 검증 절차 |

아래는 각 영역의 상세다.

## 정본 계약 SoT

서비스 경계와 확정된 계약의 현재 정본은 [`system-contract-sot.md`](system-contract-sot.md)에서 시작한다.
구현자는 계획 문서를 세부 근거로 읽기 전에 이 문서의 우선순위와 미확정 항목을 먼저 확인한다.

## 계획 문서

실제 개발을 준비하기 위한 현재 계획은 [`plans/README.md`](plans/README.md)에서 시작한다.
계획 문서는 긴 아이디에이션 초안을 구현 Phase별로 재구성한 작업용 문서이며, 아직 모두 `Draft` 상태다.

## 실검수 브리프

실제 브라우저 dogfood에서 발견된 결함이 기존 승인 계약의 충돌이나 owner-level 수정 결정을 요구할 때는 [`live_review_briefs/`](live_review_briefs/)에 날짜별 브리프를 남긴다. 이 문서는 재현 증거·충돌 계약·오너 결정·구현/재검수 기준을 보존한다. 실행 이력은 `daily_logs/`, 독립 감사 결과는 `verifications/`에 둔다.

## 아이디에이션 문서

아래 문서는 초기 아이디어와 상세 설계 후보를 보존한 참고 자료다. 길고 풍부하지만 그 자체로 확정된 구현 명세는 아니다.
**전부 2026-06 초안이며 그 뒤 제품 범위가 바뀐 곳이 있다** — 현재 상태 기준의 제품 그림은 [`product-overview.md`](product-overview.md)를 먼저 본다.

- [`abstract.md`](abstract.md): 전체 시스템 초안
- [`mongo_collections.md`](mongo_collections.md): MongoDB 컬렉션 설계 후보
- [`analysis_pipeline.md`](analysis_pipeline.md): 분석 파이프라인 상세 후보
- [`agentic_search_flow.md`](agentic_search_flow.md): Agentic Search 상세 후보
- [`writing_agent_prompt.md`](writing_agent_prompt.md): Writing Agent 프롬프트 설계 후보
- [`contracts.md`](contracts.md): 공통 계약 설계 후보

아이디에이션 문서와 계획 문서가 충돌하면 임의로 구현하지 않는다. [`system-contract-sot.md`](system-contract-sot.md)의 문서 우선순위를 확인하고, 해당 Phase 문서에 충돌을 기록한 뒤 사용자 결정을 받아 계획을 갱신한다.
