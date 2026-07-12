# 착수 결정 브리프 — Phase 5.1 Writing 생성 (첫 slice)

상태: `Resolved` (오너 결정 Q1=생성만[Gate 다음 slice]·Q2=평문 프로즈[서비스 래핑]. D3~D7은 코드베이스 패턴에서 도출)
관련: Phase 5 `plans/05-writing-ai.md` §74 착수 결정·아이디에이션 `docs/writing_agent_prompt.md`·Phase 4 ContextPackage(`context_search/models.py`)·1-turn Gateway 패턴(`analysis/compare_judge.py`·`gateway_provider.py`)·budget(`plans/flat-loop-gate.md` writing_generate 1/120s/1024/no tool)

## Decision needed

Phase 5(Writing AI)는 순차 계획상 Phase 6보다 앞이지만 미구현이다(`agent_loop/registry.py`에 `WRITING_GENERATE` 프로파일만 존재, 실제 생성 서비스 없음). 입력 인프라(ContextPackage·Gate·Gateway)는 준비됐다. 첫 slice로 무엇을 어떤 형식으로 만들지가 blocking.

## Options table (검토)

| 결정 | 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|---|
| Q1 slice 범위 | **생성만(Gate 다음)**(채택) | WritingCandidate 생성까지, Writing Gate는 별도 slice | 최소·테스터블, Gate는 LLM 기반이라 크므로 분리 타당 | 수용 기준(do_not_use/POV 검출)은 Gate slice에서 충족 |
| Q1 | 생성+최소 Gate 한 slice | 생성과 Gate를 함께 | 수용 기준 즉시 | 의미 있는 do_not_use/POV 검사는 LLM 필요 → slice 비대·검증 복잡 |
| Q2 출력 형식 | **평문 프로즈(서비스 래핑)**(채택) | 모델은 프로즈만, 서비스가 WritingCandidate 래핑 | 로컬 Gemma의 긴 한국어 프로즈를 JSON string에 넣는 fragility 회피, 견고 | self-report 구조 필드는 Gate slice에서 도입(당장 소비자 없음) |
| Q2 | 구조적 JSON(self-report 즉시) | 모델이 {text, self_reported_constraints,...} JSON | 지킨 제약 self-report 원칙 즉시 | JSON-in-창작프로즈 escaping fragility, Gate 전엔 소비자 없음 |

## Recommendation + reason (채택 근거)

로컬 1인 프로젝트·로컬 Gemma 단계에서 **생성 slice의 관심사를 좁히고 견고성을 확보**하는 게 우선이다. 의미 있는 Writing Gate(do_not_use/POV 위반을 프로즈에서 탐지)는 결정적 문자열 매칭으로 불가능하고 LLM 기반이라 독립 slice가 맞다(Q1=생성만). 첫 생성 slice엔 self-report 구조 필드를 소비할 Gate가 아직 없으므로, 긴 창작 프로즈를 JSON에 싸는 fragility를 피하고 평문 출력을 서비스가 래핑한다(Q2=평문). WritingCandidate **계약은 self-report 필드를 미리 정의**하되 slice 1은 비워둔다(Gate slice가 채움).

## 파생 결정 (코드베이스 패턴에서 도출, 명시)

- **D3 task type = `continue_scene` 하나**(MVP §76). enum은 후속 task로 확장 가능.
- **D4 생성 메커니즘 = 직접 1-turn Gateway 호출**(`WritingService` + `GatewayGenerateProvider`, extractor/compare_judge/planner와 동형). agent_loop runner는 계약층으로 "현재 더 진행 안 함"(HANDOFF Active Decisions)이고 writing_generate는 tool 없는 단일 turn이라 runner가 더할 게 없다. versioned prompt는 `PromptTemplateService`(compare_judge 선례).
- **D5 output_type = `draft_patch`**(continue_scene은 이어쓸 새 프로즈 = 추가분, 아이디에이션 §9.1). editor 삽입 단위 semantics는 accept→save slice.
- **D6 결정적 안전선 = project isolation + task/instruction 검증**만. Writing AI는 DB 미접근이라 cross-project 누출 경로가 없지만, `request.project_id == package.project_id`를 명시 검증(불일치→`WritingError`→400). do_not_use/POV 의미 검증은 Gate slice(LLM).
- **D7 오케스트레이션 = HTTP가 context_search→generate**(핵심 흐름 §32). ContextPackage는 비영속(SoT)이라 caller가 id로 못 참조 → 엔드포인트가 내부에서 package를 만든다. context_search 미구성 시 503, ProviderError→502.

## WritingCandidate 계약 (slice 1)

`{request_id, project_id, task_type, output_type, text, status="candidate", self_reported_constraints=(), candidate_id=None, generated_by_model}`. `status`는 항상 `candidate`(Writing AI는 canon 확정 안 함, 아이디에이션 §5.2). `candidate_id`는 save slice에서 부여(현재 None). `used_context_package_id`는 package가 비영속·무id라 slice 1에서 미포함.

## Deferred / out of scope

Writing Gate(pass/revise/retrieve_more/needs_user_review/block, LLM 기반)·accept→save 재진입·revise/retrieve_more 재생성 루프·구조적 self-report(candidate_claims/new_memory_hints/risk_notes)·revise/outline/critique/rewrite_style task·Continuity/POV/Voice Gate 고도화·editor 적용 단위·WritingBrief 영속. 첫 모델 budget/timeout은 벤치마크값(writing_generate 1/120s/1024) 사용.

## 경계 매트릭스 (구현 시 회귀 잠금)

| # | 분기 | 방향 | 잠금 대상 |
|---|---|---|---|
| 1 | ContextPackage+request→prompt에 instruction·draft_excerpt·macro/constraints/do_not_use 포함 | under-strict | prompt 조립 누락 시 실패 |
| 2 | 평문 프로즈 응답 → WritingCandidate(text=프로즈, status=candidate) 래핑 | under-strict | 래핑/status 오류 시 실패 |
| 3 | do_not_use/constraints가 prompt에 hard-priority로 실림 | under-strict | 컴팩트 포맷에서 누락 시 실패 |
| 4 | project isolation: request.project_id≠package.project_id → WritingError(400) | over-strict | 불일치 통과 시 실패 |
| 5 | task_type≠continue_scene → WritingError | over-strict | 미지원 task 통과 시 실패 |
| 6 | 빈 instruction → WritingError | over-strict | 빈 지시 통과 시 실패 |
| 7 | ProviderError(Gateway 실패)가 삼켜지지 않고 전파 → HTTP 502 | under-strict | 삼킴 시 실패 |
| 8 | status는 항상 "candidate"(canon 확정 아님) | over-strict | 다른 status 시 실패 |
| 9 | HTTP: context_search→generate 오케스트레이션·미구성 503 | under/over | 배선 오류 시 실패 |
| 10 | candidate memory가 있으면 candidate 라벨로만(단정 금지 프롬프트 지시) | under-strict | 라벨 누락 시 실패 |

## 성격

신규 `writing/` 패키지(models·prompt·service) + HTTP 엔드포인트 1개 + versioned prompt seed. 신규 public 표면(`WritingRequest`/`WritingCandidate` 계약, `POST /writing/generate`). Gate·save·구조적 self-report는 후속 → **minor bump(v1.6.68)**. Phase 5의 나머지(§21 착수 결정 대부분)는 후속 slice.
