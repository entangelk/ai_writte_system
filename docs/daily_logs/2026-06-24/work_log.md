# Work Log — 2026-06-24

## Goals

- 2,091줄의 `docs/abstract.md`를 실제 개발 전 검토에 적합한 Phase 단위 계획으로 재구성한다.
- 기존 `docs/` 문서는 초기 아이디에이션으로 보존하고 계획 문서와 지위를 구분한다.
- 구현 Phase와 MVP 가치 묶음의 차이를 명시해 이후 범위 혼동을 줄인다.
- 단일 사용자용 프로젝트·원고 관리 껍데기와 분석 기억 세분화 논의안을 계획에 포함한다.
- LLM 배포 경계와 Gemma 12B Q4를 포함한 실제 구현 순서·검증 계획을 작성한다.
- 기존 `/mnt/d/devel/gemma4_12b` 구현을 확인해 안전한 재사용 범위와 Agentic Loop Gate 보강점을 계획에 반영한다.

## Completed work

### 계획 문서 구조 생성

- 변경 파일: `docs/plans/README.md`, `docs/plans/00-foundations.md`, `docs/plans/01-core-sot.md`~`06-review-ui.md`
- 전체 초안을 공통 기반과 6개 구현 Phase로 나눴다.
- 각 Phase에 목표, 범위, 산출물, 수용 기준, 착수 전 결정사항, 원문 참고 링크를 추가했다.
- Phase와 MVP가 1:1 관계가 아님을 표로 분리해 MVP 1이 Phase 1~5를 가로지르는 구조를 드러냈다.
- 상세 JSON과 대안은 아이디에이션 원문에 보존하고 계획에는 착수 판단 정보만 남겼다.

### 문서 지위와 진입점 정리

- 변경 파일: `docs/README.md`, `docs/abstract.md`
- `docs/README.md`에서 계획 문서와 아이디에이션 문서를 구분했다.
- `abstract.md` 상단에 원본 보존 안내와 계획 진입점 링크를 추가했다.
- 계획 인덱스에 충돌 시 우선순위를 정의했다. 동일 우선순위 충돌은 사용자 확인 없이 선택하지 않는다.

### 프로젝트 상태 문서 생성

- 변경 파일: `HANDOFF.md`, `CHANGELOG.md`, 이 작업 로그
- 현재 계획 상태와 다음 검토 순서를 후속 작업자가 이어받을 수 있게 기록했다.

### Product Shell 계획 추가

- 변경 파일: `docs/plans/product-shell.md`, `00-foundations.md`, `01-core-sot.md`, 계획 인덱스
- 계정/인증 없는 단일 사용자 제품이라는 경계를 확정 기록했다.
- 프로젝트와 draft 기본 CRUD, 프로젝트 작업 공간, 제작 상태, 원고 내보내기를 내부 AI 시스템 바깥의 제품 표면으로 분리했다.
- 제작 관리의 세부 기능과 export 형식은 실제 필요를 확인할 논의사항으로 남겼다.

### 분석 대상과 갱신 흐름 세분화

- 변경 파일: `docs/plans/analysis-memory-taxonomy.md`, `02-analysis-pipeline.md`, `04-agentic-search.md`, `06-review-ui.md`
- 분위기, 목표, 인물, 줄거리, 떡밥 등을 포함한 분석 대상 후보를 scope와 해석 성격별로 정리했다.
- 원문 사실, 해석적 분석, 창작 의도를 서로 다른 provenance와 검토 강도로 다루도록 논의 기준을 세웠다.
- 기존 기억과 대조한 `create`, `update`, `add_evidence`, `no_change`, `conflict`, merge/split proposal 흐름을 추가했다.
- update는 직접 overwrite하지 않고 Agentic Search/RAG 비교, Gate, review, versioned upsert를 거치도록 계획했다.

### 구현 계획과 LLM Gateway 계획 추가

- 변경 파일: `docs/plans/implementation-plan.md`, `docs/plans/llm-gateway.md`, 계획 인덱스, `00-foundations.md`
- monorepo 안에서 Application은 modular monolith로 시작하고 LLM Gateway는 독립 프로세스/컨테이너로 두는 제안안을 작성했다.
- 모델 weight는 repo/image 밖의 volume에 두고 Application은 Gateway URL과 inference 계약만 의존하도록 경계를 정리했다.
- Foundation Spike부터 Product/SOT, Analysis 2A, Indexing, Search, Analysis 2B, Writing, Review까지 vertical slice와 단계별 검증을 작성했다.
- fake provider 기반의 결정적 contract/integration test와 실제 Gemma Q4 evaluation/smoke를 분리했다.
- `gemma4_12b 4bit q`의 정확한 artifact와 quant format이 불명확하므로 GGUF Q4 + llama.cpp 호환 runtime은 승인 전 가정으로만 기록했다.

### `gemma4_12b` 참조 구현 검토 및 재사용 계획

- 변경 파일: `docs/plans/gemma4-reuse.md`, `implementation-plan.md`, `llm-gateway.md`, `02-analysis-pipeline.md`, `04-agentic-search.md`
- 참조 기준을 clean working tree의 commit `485c4e2fe78323c408fcb64d08c2cdc9ec94f9e3`로 고정했다.
- 실제 모델 설정이 `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`, llama.cpp CUDA, RTX 3050 6GB 하이브리드 목표임을 확인했다.
- Compose model service, inference schema/client, thinking control, tool allowlist, bounded flat loop 골격과 관련 테스트를 재사용 대상으로 분류했다.
- AgentEngine은 Gateway에 그대로 두지 않고 Application/Worker로 이동하며 demo tool은 제외하도록 계획했다.
- max iteration의 정상 응답 위장, invalid tool arguments의 `{}` 대체, 반복 call/time/token budget 부재를 Loop Gate 보강점으로 기록했다.
- sub-agent spawn/delegation/nested agent loop를 명시적으로 제외했다.

## Issues found

### Phase와 MVP 축 불일치

- 문제: 원문의 Phase 1~6은 기술 구현 순서이고 MVP 1~4는 사용자 가치 묶음이라 직접 대응하지 않는다.
- 원인: 하나의 아이디에이션 문서에 roadmap과 release scope가 함께 기술되어 있었다.
- 해결: Phase 문서를 주 구조로 사용하고 각 Phase가 기여하는 MVP를 인덱스에 별도로 표시했다.
- 결과: 구현 순서와 출시 가치 범위를 독립적으로 검토할 수 있다.

### Analysis prior context의 순서 의존성

- 문제: 상세 분석 아이디에이션은 Agentic Search를 prior context에 사용하지만 구현 순서상 Analysis는 Phase 2, Agentic Search는 Phase 4다.
- 원인: 최종 아키텍처와 초기 부트스트랩 경로가 구분되지 않았다.
- 해결: Phase 2의 착수 전 결정사항으로 명시했다.
- 결과: Snapshot Loader/제한 Mongo 조회로 먼저 갈지 Phase 4까지 통합을 미룰지 사용자 결정이 필요하다.

### Git metadata 부재

- 문제: 현재 작업 경로는 Git repository가 아니어서 `git status`나 diff 기반 검증을 사용할 수 없다.
- 해결: 파일/링크/헤딩 기반 문서 검사를 사용한다.
- 결과: commit/branch 기반 변경 추적은 현재 불가능하다.

### Update-aware 분석의 순환 의존성

- 문제: 기존 기억을 RAG로 대조하려면 인덱스와 Agentic Search가 필요하지만, 해당 인덱스의 초기 데이터는 먼저 분석되어야 한다.
- 원인: 최초 추출과 반복 분석/갱신이 하나의 Phase로 묶여 있었다.
- 해결: Phase 2A 최초 추출과 Phase 3~4 이후 Phase 2B 대조 분석으로 나누는 검토안을 작성했다.
- 결과: 정확한 milestone 분할은 Phase 2 착수 전에 확정해야 한다.

### 4-bit 표기의 runtime 불확실성

- 문제: `4bit q`만으로 GGUF/AWQ/GPTQ/bitsandbytes 중 format을 알 수 없어 inference engine과 메모리 요구량을 확정할 수 없다.
- 원인: 현재 아이디에이션에는 `Gemma / llama.cpp compatible provider`와 `gemma-4-12b-q4` 이름만 있고 실제 artifact 정보가 없다.
- 해결: Gateway 경계를 engine-neutral하게 두고 Slice 0에서 artifact/hardware를 고정한 뒤 benchmark하도록 계획했다.
- 결과: 참조 model ID와 GGUF Q4_0, 첫 llama.cpp server 후보는 확인했다. 실제 실행 장비와 실측 재현은 여전히 필요하다.

### 참조 문서와 현재 code의 thinking 설명 불일치

- 문제: 일부 README/설계 문서는 legacy `<|think|>` 주입을 설명하지만 현재 code/test는 `chat_template_kwargs.enable_thinking`을 사용한다.
- 원인: thinking control 결함 수정 후 일부 이전 문서가 갱신되지 않았다.
- 해결: 이관 기준을 현재 code, tests, 최근 work log로 명시했다.
- 결과: legacy prompt token 주입 설명과 코드는 가져오지 않는다.

### 참조 loop의 Gate 한계

- 문제: 현재 AgentEngine은 allowlist와 max iteration은 있지만 업무 완료/실패 decision, invalid args 차단, 반복 call과 복합 budget이 없다.
- 원인: generic demo gateway의 단일 tool loop로 구현됐다.
- 해결: loop 골격만 재사용하고 Application/Worker에 domain registry와 Loop Gate를 추가하도록 계획했다.
- 결과: 실제 구현 전 양방향 회귀와 decision literal 확정이 필요하다.

## Decisions

- 사용자 결정: 기존 `docs/` 문서들은 초기 아이디에이션으로 취급하고, 긴 `abstract.md`를 실제 개발 기획에 용이하도록 세분화한다.
- 선택 방향: 기능 영역만 따로 나누기보다 구현 Phase를 주 탐색축으로 삼고, 모든 Phase가 공유하는 설계 원칙은 별도 공통 기반 문서로 둔다.
- 이유: 개발 순서와 의존성을 바로 검토할 수 있으면서 공통 원칙의 중복·표류를 줄일 수 있다.
- tradeoff: 원문의 모든 상세 예시를 새 계획 문서에 복제하지 않아 계획이 짧아진 대신, 세부 계약 검토 시 원문 링크를 따라가야 한다.
- 원본 정책: `abstract.md`와 주제별 상세 문서는 삭제·축약하지 않고 참고 자료로 보존한다.
- 사용자 결정: MVP는 혼자 사용하는 시스템이므로 계정·로그인·사용자 권한 기능을 제외한다. 프로젝트 간 데이터 경계는 `project_id`로 유지한다.
- 사용자 방향: 내부 AI 파이프라인뿐 아니라 프로젝트 CRUD, 제작 관리, 원고 내보내기를 포함하는 외부 제품 껍데기를 계획한다.
- 사용자 방향: 분석 대상을 5종으로 고정하지 않고 분위기·목표·인물·줄거리·떡밥 등을 논의하며, 기존 기억이 있으면 Agentic 분석/RAG 대조 후 안전한 갱신까지 고려한다.
- 아키텍처 제안: 같은 monorepo에서 LLM Gateway만 독립 서비스로 실행하고 필요 시 URL 변경으로 원격 GPU host로 이동한다. 본격 멀티레포 MSA는 현재 규모에 비해 운영비가 커 보류한다.
- 확인된 기준: 참조 repo의 첫 model/runtime은 `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`과 llama.cpp CUDA다. 실제 실행 hardware와 benchmark는 미확정이다.
- 사용자 결정: `/mnt/d/devel/gemma4_12b`의 loop Gate와 Agentic 구현을 재사용하되 sub-agent spawn은 도입하지 않는다.
- 재사용 결정: 전체 repo 복제 대신 선택 이관하며, inference는 Gateway, domain agent loop/tool은 Application/Worker가 소유한다.

## Next steps

1. 실제 실행 장비가 참조 환경과 같은 RTX 3050 6GB인지 확인한다.
2. monorepo 내부 package/framework와 이관 대상 파일 경로를 확정한다.
3. flat loop 종료 decision과 domain tool 최소 목록을 확정한다.
4. Slice 0에서 참조 8개 테스트와 실모델 smoke를 재현한다.
