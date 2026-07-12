# 착수 결정 브리프 — Phase 5.2 Writing Gate

상태: `Resolved` (2026-07-12, D1=A·D2=B·D3=A·D4=A)
관련: `system-contract-sot.md` v1.6.68, `plans/05-writing-ai.md` §착수 전 결정사항, `plans/05-writing-generation-decisions.md`(생성만·Gate 후속), `writing_agent_prompt.md` §16

## Decision needed

WritingCandidate를 LLM으로 `do_not_use`/POV/continuity 검증할 때 사용할 공개 Gate 결과 계약과 decision별 처리 경계를 확정해야 한다. 기존 정본은 `pass|revise|retrieve_more|needs_user_review|block` 후보와 LLM 기반 의미 검증 필요성까지만 잠갔으므로, 구현자가 출력 schema와 자동 재실행 범위를 임의로 정할 수 없다.

## Owner decisions — 2026-07-12

- **D1=A**: 내부 LLM 호출 수보다 정확도를 우선해 생성과 분리된 별도 1-turn Gate를 채택한다.
- **D2=B**: decision과 구조화 findings를 함께 반환한다.
- **D3=A, 느슨한 후속 연결**: 오너가 원한 것은 위반 판정 단위만 후속 재생성하는 구조다. 현재 candidate는 단일 `draft_patch`이고 부분 patch anchor 계약이 없으므로 자동 전체 재생성인 B와 다르다. Gate는 side-effect-free 판정만 하고 각 finding에 `evidence`와 `recommended_decision`을 남겨 후속 revise가 해당 범위를 소비하게 한다.
- **D4=A first**: 별도 evaluate API를 구현하되 generate→gate 합성(B)은 additive 확장 가능하게 둔다.

## Options table

### D1 — Gate 판정 방식

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 별도 1-turn LLM Gate | 생성 결과와 동일 ContextPackage를 별도 판정 prompt로 검증한다 | 생성자 자기검증과 분리되고 compare judge/Gateway 선례를 재사용한다 | 후보당 LLM 호출이 1회 늘어난다 |
| B. 생성 호출의 self-report로 동시 판정 | 생성 모델이 prose와 Gate 결과를 한 응답에 함께 낸다 | 호출 수가 적다 | v1.6.68의 평문 출력 결정을 뒤집고 긴 prose JSON fragility가 돌아온다 |
| C. hybrid(결정적 규칙 + LLM) | 명시 literal 규칙은 코드, 의미 연속성은 LLM이 판정한다 | 명백한 위반을 싸게 잡을 수 있다 | 현재 `do_not_use`/POV는 자연어 규칙이라 첫 slice의 결정적 규칙 경계를 새로 설계해야 한다 |

채택: **A**. 생성 평문 계약을 보존하면서 판정 책임을 분리한다.

### D2 — 공개 Gate 결과 형태

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. decision만 | 다섯 literal만 반환한다 | 가장 작다 | editor/사용자가 왜 revise 또는 block인지 알 수 없고 회귀가 판정 근거를 잠그지 못한다 |
| B. decision + 구조화 findings | `decision`, `findings[{type,severity,message,evidence}]`, `checked_constraints`를 반환한다 | editor 표시·회귀·후속 review persistence에 필요한 근거가 있다 | schema와 JSON parse/repair가 필요하다 |
| C. decision + 자유문 explanation | decision과 설명 문자열만 반환한다 | B보다 schema가 작다 | 위반 종류와 severity를 기계적으로 소비하기 어렵다 |

채택: **B**. finding `type`은 `do_not_use|pov|continuity`, `severity`는 `warning|error`로 제한한다. `evidence`는 후보 prose의 짧은 발췌이며 각 finding은 후속 연결용 `recommended_decision`을 갖는다. 첫 slice는 비영속 응답으로 둔다.

### D3 — decision literal의 처리 의미

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 판정 전용 계약 | `pass`=editor 제안 가능, `revise`=후보 수정 필요, `retrieve_more`=컨텍스트 부족, `needs_user_review`=모호/상충해 사람 판단 필요, `block`=hard constraint 위반으로 제안 금지. 첫 slice는 어떤 decision도 자동 실행하지 않는다 | 다섯 literal이 상호 배타적이고 API가 부작용 없이 안정된다 | revise/retrieve 루프는 후속이다 |
| B. revise/retrieve_more 자동 실행 | Gate가 revise면 재생성, retrieve_more면 재검색 후 재생성한다 | 사용자에게 더 완성된 흐름을 제공한다 | budget·반복 종료·새 request/candidate identity를 동시에 결정해야 해 slice가 커진다 |
| C. pass/block 2종으로 축소 | 첫 slice는 통과/차단만 구현한다 | 가장 작다 | 계획에 명시된 모호성·검색 부족·수정 가능 상태를 잃고 후속 contract migration이 필요하다 |

채택: **A**. 우선순위는 `block > needs_user_review > retrieve_more > revise > pass`로 잠근다. `error` finding이 hard `do_not_use`/POV 위반이면 `block`, 상충·판단 불가능이면 `needs_user_review`, 근거 부족이면 `retrieve_more`, 고칠 수 있는 continuity 위반이면 `revise`, finding이 없을 때만 `pass`다.

### D4 — 첫 code slice의 API 경계

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 별도 evaluate API | `POST /projects/{id}/writing/gate`가 WritingCandidate+동일 ContextPackage 재구성 입력을 받아 GateResult를 반환한다 | 생성 API를 깨지 않고 Gate만 독립 검증한다 | 클라이언트가 generate→gate 두 호출을 조율한다 |
| B. generate 응답에 Gate 포함 | 기존 generate endpoint가 생성 직후 Gate까지 실행해 `{candidate, gate}`를 반환한다 | 핵심 사용자 흐름이 한 호출이다 | 기존 공개 응답 변경과 이중 provider error/budget 의미를 함께 정해야 한다 |
| C. A와 B 동시 제공 | 별도 평가와 generate orchestration을 모두 연다 | 사용 유연성이 높다 | 단일 slice에 중복 표면과 테스트가 생긴다 |

채택: **A first**. Gate service/model/prompt와 독립 API를 먼저 잠그고, generate→gate orchestration은 additive로 연다. 입력에는 `request_id`, `candidate.text`, 원 생성 instruction/task/draft excerpt를 포함하고 서버가 project-scoped ContextPackage를 다시 구성한다. 다른 프로젝트 candidate/package는 모델 호출 전에 거부한다.

## Recommendation + reason

**D1=A, D2=B, D3=A, D4=A**를 추천한다. 로컬 1인 프로젝트 단계에서 생성 평문 계약을 보존하고, 의미 판정은 별도 LLM 책임으로 분리하며, editor가 소비할 최소 근거를 구조화한다. 자동 revise/retrieve 루프와 저장 부작용을 제외하면 provider fake로 양방향 회귀를 완결할 수 있고 후속 budget/identity 결정을 강제하지 않는다.

## Follow-up considerations

- `findings` envelope는 후속 Writing Gate persistence가 Context Gate finding store와 같은 collection을 재사용할지 별도 origin을 둘지 결정할 수 있도록 `origin=writing_gate` 확장 여지를 남긴다.
- `retrieve_more` 자동화 시 새 ContextSearchRequest의 query/needs, 최대 반복 수, candidate/request identity를 별도 브리프로 잠근다.
- `revise` 자동화 시 원 후보와 수정 후보의 append-only 관계 및 budget을 잠근다.
- revise loop는 `writing_agent_prompt.md` §16.2의 v1.6.69 finding shape(`type`/`severity`/`message`/`evidence`/`recommended_decision`)를 입력으로 사용하되, `evidence`→부분 patch anchor 변환 계약을 먼저 확정한다.
- 실 Gemma smoke에서는 JSON schema 준수, 한국어 finding 품질, POV/do_not_use 양방향 fixture를 관찰한다. production 판정 품질 채택은 fake 회귀와 분리한다.

## Deferred / out of scope

- revise/retrieve_more 자동 재실행 및 flat-loop tool-call branch
- Gate finding 영속화와 Review Inbox 통합
- accept→save→analysis 재진입
- `candidate_claims`/`new_memory_hints`/`risk_notes` 구조적 self-report
- Voice/Foreshadowing Gate 고도화와 새 writing task type
- frontend/editor 삽입 UX

## 승인 후 첫 회귀 경계

1. `pass`: 세 검사 finding 없음 → editor 제안 가능.
2. `block`: do_not_use 위반과 명시 POV hard constraint 위반 각각 block(under-strict), 정상 prose는 block 금지(over-strict).
3. `revise`: 수정 가능한 continuity error → revise; 단순 warning만으로 block 금지.
4. `retrieve_more`: 판정에 필요한 canonical 근거 부족 → retrieve_more; 근거가 충분한 정상 후보는 retrieve_more 금지.
5. `needs_user_review`: context 내부 상충/진짜 모호성 → needs_user_review; 명백한 hard 위반을 review로 약화 금지.
6. 우선순위: 복수 finding에서 `block > needs_user_review > retrieve_more > revise > pass`.
7. parser: 잘못된 JSON/미지원 literal/누락 필드/빈 provider 응답은 성공으로 위장하지 않는다.
8. project isolation: cross-project 입력은 provider 호출 전에 거부한다.
9. HTTP: 정상 200, 미구성 503, project 없음 404, invalid input 400, malformed/provider fault 502, provider timeout 504. Candidate는 아직 비영속 inline 입력이라 별도 candidate-not-found 분기는 없다.
