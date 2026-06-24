# HANDOFF

## Current Status

- `docs/` 루트의 기존 설계 문서는 초기 아이디에이션 자료로 분류되어 있다.
- 실제 개발 준비용 진입점은 `docs/plans/README.md`다.
- 계획은 공통 기반, Product Shell, 분석 memory taxonomy, Phase 1~6으로 나뉘어 있다.
- Product Shell과 Phase 계획은 `Draft`, 분석 taxonomy는 `Discussion` 상태다.
- 전체 구현 순서 문서는 `Draft`, LLM Gateway 경계는 `Proposed` 상태다.
- 구현은 아직 시작하지 않았다.
- 현재 경로에는 Git metadata가 없다.

## Active Decisions

- 긴 `abstract.md` 원본은 보존한다.
- 구현 Phase를 계획의 주 축으로 사용하고 공통 설계 원칙은 별도 문서로 관리한다.
- Phase와 MVP를 서로 다른 축으로 관리한다.
- 아이디에이션과 계획이 충돌하면 임의로 구현하지 않고 사용자 결정을 받는다.
- MVP는 계정/인증이 없는 단일 사용자 시스템이며 프로젝트 경계는 `project_id`로 유지한다.
- 기존 기억의 갱신은 AI가 직접 덮어쓰지 않고 검색·대조·Gate·검토·versioned upsert를 거친다.
- 제안 아키텍처는 monorepo + modular Application + 독립 LLM Gateway/Worker다. 사용자 승인 전이다.
- `/mnt/d/devel/gemma4_12b` commit `485c4e2`를 참조 구현으로 검토했으며 model/quant는 공식 QAT GGUF Q4_0으로 확인됐다. 실제 실행 hardware는 미확정이다.
- sub-agent spawn은 제외하고 bounded flat loop만 사용한다.

## Next Tasks

1. 실제 GPU/VRAM과 참조 환경 일치 여부 확인
2. `docs/plans/gemma4-reuse.md`의 선택 이관 경계 승인
3. flat loop decision/tool/budget 계약 확정
4. Slice 0에서 참조 contract tests와 실모델 smoke 재현

## Verification

- 계획 문서의 상대 링크와 원문 추적표 확인
- 각 Phase 문서의 필수 planning section 확인
- 원본 `docs/abstract.md` 본문 보존 확인
- Product Shell과 analysis taxonomy의 계획 링크 및 Phase 연결 확인
- 구현 slice의 선후 관계와 LLM Gateway contract/model-test 분리 확인
- 참조 repo unit contract test 8개 통과; live Gemma container가 없어 실모델 smoke는 미실행

## Project Structure

```text
docs/
├── README.md                    # 문서 분류와 진입점
├── abstract.md                  # 보존된 전체 아이디에이션 원본
├── *.md                         # 주제별 상세 아이디에이션
├── plans/
│   ├── README.md                # 계획 인덱스, 우선순위, Phase/MVP 관계
│   ├── 00-foundations.md
│   ├── product-shell.md         # 프로젝트/원고 관리와 내보내기
│   ├── analysis-memory-taxonomy.md # 분석 대상 및 갱신 논의안
│   ├── implementation-plan.md   # vertical slice와 검증 계획
│   ├── llm-gateway.md           # 모델 서빙 경계와 Gemma Q4 검증
│   ├── gemma4-reuse.md          # 기존 구현 선택 이관과 Loop Gate 보강
│   └── 01-core-sot.md ~ 06-review-ui.md
└── daily_logs/2026-06-24/work_log.md
```
