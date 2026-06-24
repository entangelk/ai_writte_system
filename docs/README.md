# 문서 안내

이 저장소의 문서는 성격에 따라 두 영역으로 구분한다.

## 계획 문서

실제 개발을 준비하기 위한 현재 계획은 [`plans/README.md`](plans/README.md)에서 시작한다.
계획 문서는 긴 아이디에이션 초안을 구현 Phase별로 재구성한 작업용 문서이며, 아직 모두 `Draft` 상태다.

## 아이디에이션 문서

아래 문서는 초기 아이디어와 상세 설계 후보를 보존한 참고 자료다. 길고 풍부하지만 그 자체로 확정된 구현 명세는 아니다.

- [`abstract.md`](abstract.md): 전체 시스템 초안
- [`mongo_collections.md`](mongo_collections.md): MongoDB 컬렉션 설계 후보
- [`analysis_pipeline.md`](analysis_pipeline.md): 분석 파이프라인 상세 후보
- [`agentic_search_flow.md`](agentic_search_flow.md): Agentic Search 상세 후보
- [`writing_agent_prompt.md`](writing_agent_prompt.md): Writing Agent 프롬프트 설계 후보
- [`contracts.md`](contracts.md): 공통 계약 설계 후보

아이디에이션 문서와 계획 문서가 충돌하면 임의로 구현하지 않는다. 해당 Phase 문서에 충돌을 기록하고 사용자 결정을 받아 계획을 갱신한다.
