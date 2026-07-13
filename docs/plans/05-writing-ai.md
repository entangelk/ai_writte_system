# Phase 5. Writing AI

상태: `Draft`  
선행 조건: Phase 4 ContextPackage와 Context Gate  
후속 소비자: Editor, 저장/분석 재진입, Review UI

## 목표

사용자 요청과 WritingBrief, 검증된 ContextPackage만을 사용해 글 후보를 만들고, 기존 기억과의 충돌을 검사한 뒤 editor에 제안한다.

## MVP 범위

- `WritingRequest`와 `WritingBrief`
- `continue_scene` 중심의 최소 task type
- ContextPackage prompt assembly
- `WritingCandidate`/`draft_candidate`
- Writing Gate의 기본 계약
- editor에 full text 또는 patch 제안
- 사용자 accept 후 Phase 1 save 흐름 재진입 (**v1.6.70 구현: pass Gate→immutable version save→pending Analysis job**)

후속 증분:

- revise, outline, critique, dialogue, scene plan
- Continuity/POV/Foreshadowing Gate 고도화
- Voice RAG와 Voice Gate
- 자동 retrieve-more/regeneration loop

## 핵심 흐름

```text
user instruction + editor pointers + WritingBrief
→ context request → Phase 4 ContextPackage
→ prompt assembly → Writing AI → WritingCandidate
→ Writing Gate → editor 제안/revise/retrieve_more/review/block
→ 사용자 accept → Phase 1 save → Phase 2 analysis
```

## Writing AI 경계

- DB나 검색 인덱스에 직접 접근하지 않는다.
- MVP `writing_generate` profile에는 domain tool을 등록하지 않고 검증된 ContextPackage만 입력받는다.
- ContextPackage에 없는 프로젝트 기억을 사실처럼 만들지 않는다.
- candidate 정보는 확정 canon처럼 단정하지 않는다.
- `do_not_use`와 POV/timeline constraint를 우선한다.
- 출력은 최종 원문이 아니라 사용자 검토 대상 후보다.

## Gate 계층

MVP에서 최소한 요청 적합성, 프로젝트 격리, hard constraint 위반을 검사한다. 원문에 제시된 고급 Gate는 증분 계획으로 분리한다.

- Continuity: 죽은 인물, 관계, 장소, 사건의 모순
- POV: 현재 장면에서 인물이 알 수 없는 사실
- Foreshadowing: 의도하지 않은 회수/재등장/과잉 노출
- Voice: WritingBrief 및 승인된 voice sample 위반

## 산출물

1. WritingRequest/Brief/Candidate 계약
2. 최소 Writing Agent system contract와 prompt
3. ContextPackage formatter
4. Writing Gate와 decision 처리
5. editor integration contract
6. accept → save → analysis 재진입 흐름

## 수용 기준

- `continue_scene` 후보가 사용자 요청과 현재 editor 위치를 반영한다.
- ContextPackage 밖의 프로젝트 사실을 단정한 후보가 검출된다.
- `do_not_use`와 명시된 POV constraint 위반이 통과하지 않는다.
- 정상적인 창작적 추가까지 모두 차단하는 과잉 검증을 피하는 정상 사례가 있다.
- Gate decision별 editor 동작이 명확하다.
- 사용자가 accept하기 전에는 원문 draft version이나 canon이 바뀌지 않는다.

## 착수 전 결정사항

- [x] 첫 task type을 `continue_scene` 하나로 제한할지 — **v1.6.68 확정**(브리프 `05-writing-generation-decisions.md`, D3=continue_scene 하나. enum은 후속 task로 확장).
- [x] 출력이 full text인지 patch인지, editor 적용 단위 — **v1.6.68 부분 확정**(Q2=평문 프로즈, output_type=draft_patch[이어쓸 새 프로즈]. editor 삽입 적용 단위는 accept→save slice로 보류).
- [x] Gate decision literal과 각 decision의 자동/수동 처리 — **v1.6.69 확정**: `pass|revise|retrieve_more|needs_user_review|block`, side-effect-free 판정, 우선순위 `block > needs_user_review > retrieve_more > revise > pass`; 부분 revise 자동화는 finding evidence를 소비하는 후속.
- [x] Continuity/POV 검사를 규칙, LLM, hybrid 중 어떻게 구성할지 — **v1.6.69 확정**: 생성과 분리된 별도 1-turn LLM Gate, 구조화 findings.
- [ ] 후보가 새 설정을 만든 경우 memory hint를 어떻게 다룰지 — 구조적 self-report(new_memory_hints) slice.
- [x] 첫 모델의 context/output budget과 timeout — **벤치마크값 사용**(writing_generate 1/120s/1024, `plans/flat-loop-gate.md`; `WRITING_GENERATE_MAX_TOKENS` env로 조정).
- [x] accept→save→analysis 재진입 — **v1.6.70 확정/구현**: latest base+paragraph append, Gate pass only, idempotent save+pending job. background run과 client offset patch는 additive 후속.
- [x] candidate report 별도 재평가 — **v1.6.72 확정/구현**: side-effect-free inline `/writing/report`, 서버 ContextPackage 재구성. persisted candidate/report 감사 이력과 id 기반 API는 additive 후속.
- [x] finding evidence 기반 부분 revise 첫 slice — **v1.6.73 확정/구현**: continuity+revise 단일 finding, exact evidence 단일 anchor, 모델 replacement 평문+Application splice, inline `/writing/revise`. retrieve_more·multi-finding·자동 Gate/loop·persisted revision은 순차 후속.

## 원문 및 상세 참고

- [`../abstract.md`](../abstract.md) §4.1, §6, §12.3~12.5, §13.1, §14.1
- [`../writing_agent_prompt.md`](../writing_agent_prompt.md)
- [`../contracts.md`](../contracts.md) §3, §6.2
