# CHANGELOG

| Date | Change | Detail |
|---|---|---|
| 2026-06-24 | 개발 계획 문서 구조 도입 | [work log](docs/daily_logs/2026-06-24/work_log.md) |

## 2026-06-24

### Added

- 초기 아이디에이션과 실제 개발 계획의 문서 지위를 분리했다.
- `abstract.md`를 공통 기반과 Phase 1~6 계획으로 재구성했다.
- 구현 Phase와 MVP 가치 묶음이 별도 축이라는 계획 기준을 명시했다.
- 단일 사용자 Product Shell과 프로젝트/원고 CRUD·내보내기 계획을 추가했다.
- 분석 memory taxonomy와 Agentic Search/RAG 기반 변경 후보 흐름을 추가했다.
- monorepo 기반 구현 순서와 독립 LLM Gateway/Gemma Q4 검증 계획을 추가했다.
- 기존 `gemma4_12b`의 선택 이관 계획과 flat Agentic Loop Gate 보강 기준을 추가했다.
- 외부 참조 repo 없이 동작하는 portable LLM payload, provider/fake, stable errors와 fake-transport llama.cpp client를 구현했다.

사용자는 기존 문서를 초기 아이디에이션으로 보존하면서 실제 개발 전 검토가 쉽도록 긴 초안을 세분화하기를 선택했다. 이에 원문은 유지하고 `docs/plans/`를 작업용 계획 진입점으로 추가했다.

또한 혼자 사용하는 제품이므로 계정 시스템은 MVP에서 제외하고, 프로젝트 관리와 원고 내보내기를 사용자 제품 표면에 포함하기로 했다. 분석 대상은 고정 5종으로 확정하지 않고 분위기·목표·줄거리 등을 논의한 뒤, 기존 기억과의 대조 및 versioned update까지 고려한다.

LLM 운영은 같은 monorepo에서 계약을 함께 관리하되 Gateway를 독립 프로세스/컨테이너로 분리하는 제안안을 채택 후보로 기록했다. 참조 repo에서 Gemma 12B QAT GGUF Q4_0과 llama.cpp CUDA 구성을 확인했으며, 실제 하드웨어 benchmark 전에는 성능 기준을 확정하지 않는다.

사용자는 기존 `gemma4_12b`의 loop/agentic 구현 재사용과 sub-agent spawn 제외를 요청했다. 검토 결과 inference 구성과 평면형 loop 골격은 선택 이관하되, domain tool 실행은 Application/Worker가 소유하고 반복·인자·시간·token budget Gate를 보강하도록 정리했다.

여러 개발 머신에서 참조 repo가 없을 수 있으므로 외부 경로는 runtime dependency로 사용하지 않는다. 첫 구현 slice로 llama.cpp thinking payload 경계를 현재 repo에 자립적으로 이관했으며, 작업용 머신의 real-model smoke는 보류한다.
