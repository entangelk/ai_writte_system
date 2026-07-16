# 착수 결정 브리프 — Frontend Writing 작업공간

상태: `Resolved — D1=A · D2=A · D3=A · D4=A · D5=A, owner confirmed 2026-07-16`

관련 정본: `docs/system-contract-sot.md` v1.7.0, `frontend-editor-save-decisions.md`, `frontend-api-contract-decisions.md`, `05-writing-ai.md`, `product-shell.md`, `product-readiness-backlog.md`, HANDOFF Next Tasks

## Decision needed

Product shell A가 완료되어 다음 C slice에서 editor에 `continue_scene` 생성·Gate 근거·accept/save를 연결해야 한다. 구현 전에 다음 다섯 경계를 확정해야 한다.

1. editor가 dirty하거나 과거 version을 보고 있을 때 어떤 저장 version을 Writing의 기준으로 삼을지
2. 첫 UI가 기본 generate→Gate→accept만 닫을지, 자동 revise/retrieve loop까지 함께 노출할지
3. 성공뿐 아니라 저장된 부분 산출물을 포함하는 4xx/5xx partial envelope을 OpenAPI와 프론트에서 어떻게 타입화할지
4. 생성 후보를 read-only 제안으로 둘지, 저장 전 편집 가능한 별도 버퍼로 둘지
5. backend 계약 보강과 frontend 흐름을 몇 개의 작은 code slice로 나눌지

이 선택들은 기존 backend 계약만으로 하나로 도출되지 않는다. 특히 dirty editor를 조용히 허용하면 화면의 미저장 본문과 `/writing/accept`가 append하는 저장된 base version이 갈라질 수 있고, partial 502를 일반 실패로 취급하면 이미 저장된 새 version을 사용자에게 숨길 수 있다.

## Owner decision and rationale (2026-07-16)

- **D1=A** — clean latest 저장 version에서만 Writing을 허용한다. 이 제약은 내부 구현 조건으로 숨기지 않고, dirty·과거 version·zero-version 각각에서 **왜 지금 생성할 수 없는지와 무엇을 해야 하는지 설명하는 사용자 텍스트**를 C1 구현에 포함한다.
- **D2=A** — 첫 UI는 generate→Gate 근거→accept/save 기본 루프를 먼저 닫고 bounded revise/retrieve loop는 C2로 분리한다.
- **D3=A** — 성공과 partial artifact를 backend HTTP model·`response_model`·`responses={}`·exact-key 회귀로 함께 계약화한다. 이에 따라 `ARCH-1` trigger가 발화하며 C0에서 Writing HTTP model부터 분리한다.
- **D4=A** — 첫 slice는 read-only candidate panel로 시작한다. 다만 candidate 일부 수정의 의미와 “저장 후 수정·재생성” UX는 아직 최종 답으로 고정하지 않는다. 실제 C1 화면을 사용한 뒤 부분 수정 요구와 stale report/Gate 비용을 관찰해 editable candidate(D4=B) 또는 다른 적용 흐름을 재검토한다.
- **D5=A** — C0 contract→C1 basic UI→C2 bounded loop의 세 작은 slice로 진행한다.

결정은 frontend 소비 정책과 다음 구현 경계를 잠근다. 현재 backend runtime·public payload·SoT 저장 의미는 바꾸지 않으며, 실제 response model과 UI 코드는 다음 C0/C1 slice에서 구현한다.

## 확인된 현재 계약과 선례

- 첫 task/output literal은 `continue_scene` + `draft_patch`다.
- `POST /projects/{project_id}/writing/generate`는 `current_position{draft_id,version_id}`를 기준으로 ContextPackage를 만들고 평문 후보와 구조화 report를 반환한다. 저장 side effect는 없다.
- `POST .../writing/gate`는 후보를 다시 평가해 `pass|revise|retrieve_more|needs_user_review|block`와 findings를 반환한다. 저장 side effect는 없다.
- `POST .../writing/revise-and-gate`는 **기존 후보와 revise finding 하나가 있어야 시작**한다. bounded loop가 revise/report/Gate와 필요 시 retrieve_more를 수행하며, 성공과 partial failure 모두 마지막 candidate·gate·loop·stages를 보존한다. 즉 이것은 최초 생성 endpoint가 아니라 non-pass 후보의 후속 경로다.
- `POST .../writing/accept`는 `base_version_id`가 현재 최신이 아니면 409다. Gate를 다시 실행해 pass일 때만 candidate patch를 최신 원고에 append하고 immutable 새 version과 pending Analysis job을 만든다.
- accept의 200 `accepted=false`는 정상적인 non-pass 결과이며 저장 산출물이 없다.
- accept가 version 저장 후 Analysis job 생성에서 실패하면 **502이지만 `accepted=true`이고 `saved`가 존재**한다. 같은 idempotency key 재시도는 같은 version으로 수렴해 Analysis job만 재유도한다.
- accept idempotency는 key만으로 replay되고 재시도 body 비교를 하지 않는다. 따라서 frontend는 editor Save와 마찬가지로 accept key를 **exact accept request body 전체**에 결박해야 한다(`request_id`·`candidate_text`·`draft_id`·`base_version_id`가 핵심 identity).
- Writing endpoint 응답은 아직 OpenAPI에서 실질 타입이 없다. 성공 경로에는 `response_model`을 적용할 수 있지만 `JSONResponse` partial envelope은 runtime response validation을 우회한다. 다만 `responses={...}`로 OpenAPI 문서화하고 exact-key 회귀로 실제 payload를 잠그는 것은 가능하다.
- A 종료 체크포인트에서 `ARCH-1`은 미발화했지만, C에서 Writing response model을 새로 추가하면 readiness backlog의 trigger가 발생한다. 규칙은 해당 도메인의 HTTP 모델부터 분리하고 전 `main.py` 일괄 분리는 하지 않는 것이다.

## D1 — Writing 기준 version과 dirty editor

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. clean latest version에서만 Writing 허용 (추천)** | 현재 선택이 최신이고 `rawText === baseline`일 때만 generate를 활성화한다. dirty면 먼저 명시적 Save, 과거 version이면 최신 version으로 돌아오도록 안내한다. | 화면·ContextPackage·accept base가 하나의 version으로 일치한다. 기존 “명시적 Save만 version mint” 계약을 보존하며 새 backend 합성이 없다. | 아이디어를 적다가 저장하지 않고 바로 생성할 수 없다. 한 번 더 Save가 필요하다. |
| B. dirty text를 `draft_excerpt`로 보내되 accept 전 수동 Save 요구 | 생성은 현재 textarea를 참고하고, accept 시 dirty면 먼저 저장하도록 막는다. 저장 뒤 base version이 바뀌므로 기존 후보를 새 context에서 다시 Gate할지 결정해야 한다. | 미저장 문맥으로 빠르게 생성 후보를 볼 수 있다. | 후보가 생성된 context와 실제 accept base가 달라진다. 저장 후 재Gate·stale candidate UX가 추가되고 첫 slice가 커진다. |
| C. generate 전에 자동으로 editor를 Save | dirty generate 클릭이 먼저 새 version을 mint한 뒤 그 version으로 생성한다. | 사용자 클릭 수가 적고 기준 version이 일치한다. | “명시적 Save only”를 사실상 generate-triggered autosave로 바꾼다. 생성 취소만 해도 version이 생긴다. |
| D. dirty text+candidate를 accept가 한 번에 저장 | accept request가 unsaved editor 본문과 candidate를 함께 받아 새 version을 만든다. | 저장과 채택이 한 번에 된다. | `/writing/accept` 공개 계약·Core SOT append 의미·멱등 payload를 바꾸는 새 backend 기능이다. 이번 frontend 연결 범위를 크게 넘는다. |

### Recommendation + reason

**D1=A를 추천한다.** 현재 단계의 핵심은 자동화보다 저장 기준의 단일성이다. clean latest를 전제로 하면 기존 version·ContextPackage·Gate·accept 계약을 그대로 조립할 수 있고, dirty 본문 유실이나 stale candidate라는 새 상태를 만들지 않는다.

구현 lock:

- version이 0개인 새 draft는 먼저 명시적 Save로 base version을 만든 뒤 Writing을 사용할 수 있다.
- 과거 version 선택 상태에서는 generate를 비활성화하고 최신으로 돌아가는 안내를 제공한다.
- dirty 상태에서는 generate/accept를 비활성화하고 “먼저 저장”을 표시한다.
- 위 세 상태는 disabled control만 두지 않는다. 사용자가 이유와 해소 행동을 이해하도록 각각 `첫 version을 저장해야 함`·`최신 version에서 실행해야 함`·`현재 변경을 먼저 저장해야 함`에 해당하는 설명 텍스트를 함께 표시하고 회귀로 잠근다. 최종 한국어 문구 자체는 localization 가능한 display text이며 machine contract로 취급하지 않는다.
- generate부터 accept 완료까지 base version id를 intent에 고정한다. 그 사이 새 latest가 생겨 accept 409가 나면 candidate를 보존하고 새 base에서 재생성하도록 안내한다.

## D2 — 첫 사용자 흐름 범위

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. generate → Gate 근거 → accept/save 기본 루프 먼저 (추천)** | generate 후 별도 Gate를 호출해 candidate와 findings를 보여준다. pass일 때 accept를 허용하고, non-pass는 후보·근거를 보존한 채 재생성 또는 후속 slice 진입점으로 둔다. | UX-1의 핵심 가치가 가장 작은 상태 수로 닫힌다. generate/gate/accept 각각의 공개 계약을 명확히 검증할 수 있다. | `revise`/`retrieve_more`가 첫 slice에서는 자동 처리되지 않는다. |
| B. 기본 루프 + eligible revise의 `revise-and-gate`까지 | Gate가 continuity+revise finding을 반환하면 같은 화면에서 bounded loop를 실행해 pass 후보를 다시 제안한다. | backend 자동 개선 능력을 첫 UI부터 활용한다. | partial candidate·loop stage·budget exhaustion·not eligible까지 한 번에 UX를 정해야 해 첫 slice가 커진다. |
| C. generate 후 Gate 화면 없이 accept 직접 호출 | accept가 Gate를 다시 실행하므로 generate 후보에 바로 “채택”을 제공하고 결과만 표시한다. | 호출과 화면이 가장 단순하다. | 사용자가 채택 전에 Gate 근거를 볼 수 없고, 제품 목표인 “Gate 확인 → 채택” 순서를 충족하지 않는다. |
| D. `revise-and-gate`를 최초 생성 endpoint처럼 사용 | generate 없이 instruction만으로 bounded loop를 시작한다. | 겉보기에는 단일 호출이다. | 현재 endpoint는 candidate와 revise finding을 필수로 요구하므로 계약에 맞지 않는다. 새 orchestration endpoint가 필요하다. |

### Recommendation + reason

**D2=A를 추천한다.** C의 첫 목적은 backend의 모든 loop 상태를 노출하는 것이 아니라 “이어쓰기 생성 → 근거 확인 → 사람이 채택 → 새 version”을 실제 화면에서 관통하는 것이다. 자동 revise/retrieve는 기본 루프가 안정된 뒤 같은 candidate panel에 additive로 붙일 수 있다.

기본 UI lock:

- instruction은 공백-only를 보내지 않고 in-flight 중복 generate를 막는다.
- generate 성공 candidate는 editor 본문과 분리해 보존한다.
- Gate decision과 findings의 type/severity/message/evidence/recommended_decision을 표시한다.
- `pass`만 accept 버튼을 활성화한다. `accepted=false` 200은 실패 toast가 아니라 새 Gate 결과로 표시한다.
- 400/404/409/422는 확정 거부, transport/5xx는 입력·candidate·base intent를 보존한다.

## D3 — Writing 성공·partial 응답 타입 계약

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 성공 response model + partial `responses={}` 모델, exact-key 회귀 (추천)** | Writing HTTP 모델을 별도 모듈에 정의한다. generate/gate/accept/revise-and-gate 성공에는 `response_model=`, partial status에는 generic error와 partial artifact 모델의 union을 `responses={}`로 문서화한다. JSONResponse runtime 우회는 exact-key 회귀로 잠근다. | 생성 TypeScript 타입이 성공·부분 성공을 함께 설명한다. 저장된 artifact를 가진 502를 일반 오류와 구분할 수 있다. silent field loss를 안전망 먼저 절차로 방어한다. | 모델 수와 exact-key 테스트가 늘어난다. JSONResponse partial은 문서화돼도 runtime Pydantic validation은 받지 않는다. `ARCH-1`이 발화한다. |
| B. 성공만 response model, partial은 프론트 손선언 union | 2xx는 생성 타입을 쓰고 `candidate`/`saved`가 있는 4xx/5xx만 `client.ts` type guard로 정의한다. | backend diff가 작고 기본 UI를 빨리 시작할 수 있다. | 가장 중요한 partial artifact 계약이 OpenAPI 밖에 남고 backend/frontend가 따로 드리프트할 수 있다. Review UI에서도 같은 문제가 반복될 가능성이 높다. |
| C. Writing 응답 전부 프론트 손선언 | backend는 무변, 현재 payload를 TypeScript interface로 복사한다. | 가장 빠르며 `ARCH-1` 미발화다. | v1.6.94에서 이미 확인한 silent contract drift를 Writing의 더 복잡한 envelope에 다시 허용한다. |
| D. partial도 모두 HTTP 200으로 정규화 | transport 성공이면 `{ok:false, partial...}`로 반환해 단일 response model을 쓴다. | 프론트 분기가 단순하고 runtime response validation이 가능하다. | 확정된 400/502/503/504 taxonomy를 바꾸는 공개 계약 개정이며 운영 관측 의미가 약해진다. |

### Recommendation + reason

**D3=A를 추천한다.** accept의 `502 + accepted=true + saved`는 단순 오류가 아니라 데이터가 이미 커밋된 상태다. 이 구분을 손선언에만 두면 가장 위험한 write 경계가 OpenAPI 밖에 남는다. `responses={}`가 runtime 검증을 대신하지는 못하지만, exact-key 회귀와 함께 쓰면 생성 타입·문서·실 payload를 하나의 contract stack으로 관리할 수 있다.

구현 lock:

- 모델을 붙이기 전에 현재 dict/JSONResponse payload의 top-level 및 핵심 nested exact-key 회귀를 먼저 추가한다.
- `WritingCandidate`, `WritingGate`, `WritingLoop`, `WritingStage`, accepted save, Analysis job summary, typed error payload를 재사용 가능한 HTTP 모델로 분리한다.
- 같은 status가 generic `{"detail": ...}`과 partial envelope 둘 다 가질 수 있음을 OpenAPI union으로 표현한다.
- `main.py` 전체 router 추출은 하지 않는다. 우선 Writing HTTP 모델만 별도 모듈로 분리하고 route 추출은 의존성 전달이 실제로 단순해질 때 판단한다.
- 프론트는 생성 타입을 소비하고, status만으로 성공/실패를 단정하지 않고 envelope discriminator(`accepted`, `candidate`, `*_error`)를 확인한다.

## D4 — 생성 후보의 편집 가능성

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 첫 slice는 read-only 후보 panel (추천)** | candidate prose와 Gate 근거를 editor 옆 별도 panel에 표시한다. 채택 전 원고 textarea는 바뀌지 않는다. accept 성공 뒤 saved version detail을 다시 읽어 editor baseline/history를 갱신한다. | “accept 전 원문 무변” 계약이 화면 구조로 드러난다. candidate와 원고 dirty state가 섞이지 않고 저장 결과를 서버 정본에서 재조회한다. | 후보 일부만 손보고 채택할 수 없다. 수정하려면 채택 후 editor에서 편집하거나 재생성해야 한다. |
| B. 별도 editable candidate buffer | candidate panel 자체를 textarea로 제공하고 수정된 exact text를 Gate/accept에 보낸다. | 사용자가 AI 제안을 다듬은 뒤 채택할 수 있어 집필 UX가 좋다. | candidate dirty·재Gate·accept idempotency intent 수명이 추가된다. report metadata가 편집 전 후보와 stale해질 수 있어 재report/Gate 정책이 필요하다. |
| C. candidate를 즉시 main editor에 삽입하되 미저장 표시 | 생성 성공 시 현재 textarea 끝에 붙이고 사용자가 Save/되돌리기를 선택한다. | 직접 편집 흐름이 자연스럽다. | accept/save/Analysis 경로를 우회하고 AI 제안과 사용자 본문 dirty state가 합쳐진다. 취소·재생성·Gate 근거의 대상 text가 불명확해진다. |

### Recommendation + reason

**D4=A를 추천한다.** 첫 C slice는 candidate 편집기가 아니라 AI 제안의 provenance와 채택 경계를 만드는 작업이다. read-only panel은 accept 전 원문 불변을 가장 명확히 지킨다. 오너는 A를 승인했지만 일부 수정의 의미와 저장 후 수정·재생성 UX는 실제 프론트 경험 뒤 다시 판단하기로 했다. 따라서 B는 각하가 아니라 명시적 additive 재검토 후보다.

accept intent lock:

- accept 클릭 시 UUID와 exact accept request body 전체를 한 쌍으로 보존한다.
- transport/5xx 뒤 같은 payload만 같은 key로 재시도한다. candidate/base가 바뀌면 새 key다.
- `502 + accepted=true + saved`는 새 version 생성 성공으로 처리한다. saved version detail을 로드해 editor/history를 갱신하고 Analysis 재시도 가능 상태를 별도로 표시한다.
- `200 + accepted=true`도 saved detail을 서버에서 다시 읽어 raw text와 baseline을 갱신한다.
- `200 + accepted=false`는 candidate를 보존하고 반환 Gate를 표시한다.

## D5 — Code slice 경계

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. C0 계약 → C1 기본 UI → C2 자동 loop (추천)** | C0: exact-key tests+Writing response models/OpenAPI. C1: clean-latest generate→Gate→accept/save read-only panel. C2: eligible finding의 revise-and-gate·partial loop UX. | 각 slice가 독립적으로 검증 가능하고 write 경계 전에 생성 타입이 준비된다. 기본 사용자 가치가 C1에서 닫힌다. | 문서·검증 체크포인트가 세 번 필요하다. |
| B. C0+C1 한 slice → C2 | response model과 기본 UI를 함께 구현하고 loop만 분리한다. | 기본 루프 완료가 한 단계 빠르다. | backend exact-key/OpenAPI와 frontend state machine을 동시에 디버깅한다. diff가 커진다. |
| C. C1 프론트 손선언 → C0 계약 후속 → C2 | UI를 먼저 만들고 타입 계약을 나중에 교체한다. | 화면을 가장 빨리 볼 수 있다. | 손선언을 곧바로 버리는 이중 작업이고 partial write 경계가 첫 구현 동안 잠기지 않는다. |
| D. C0+C1+C2 한 slice | 타입·기본 흐름·bounded loop를 한 번에 완료한다. | C 전체를 한 번에 닫는다. | 상태와 실패 분기가 너무 많아 작은 slice 원칙과 현재 TDD 검증 방식에 맞지 않는다. |

### Recommendation + reason

**D5=A를 추천한다.** C0는 backend 공개 계약만, C1은 사용자가 실제로 쓰는 최소 write loop, C2는 복잡한 자동화 상태만 소유한다. C1 종료 후 `ARCH-1+OPS-1` 체크포인트를 판단할 수 있고, C2는 기본 제품 사용에 필요하다고 확인될 때 바로 이어갈 수 있다.

## 추천 조합

**D1=A · D2=A · D3=A · D4=A · D5=A**

- clean latest 저장 version만 Writing 기준으로 사용한다.
- generate→Gate 근거→accept/save 기본 루프를 먼저 닫는다.
- 성공과 partial artifact를 backend HTTP 모델+OpenAPI+exact-key 회귀로 함께 잠근다.
- 후보는 첫 slice에서 read-only side panel로 제공한다.
- C0 계약, C1 기본 UI, C2 bounded loop UI의 세 작은 slice로 진행한다.

## 선택 후 첫 구현 순서

### C0 — Writing HTTP contract

1. 기존 generate/gate/revise-and-gate/accept payload exact-key 회귀를 현재 dict 응답에서 먼저 통과시킨다.
2. Writing HTTP response/error 모델을 `services/application/app/writing/http_models.py`에 추가한다.
3. 성공 `response_model`과 partial `responses={}`를 route에 연결한다.
4. OpenAPI를 재생성하고 frontend generated type에서 성공·partial envelope literal을 확인한다.
5. C0 착수 시 `ARCH-1`을 Ready→In progress로, HTTP model 분리와 검증 완료 시 Done으로 갱신한다.

### C1 — 기본 Writing 작업공간

1. latest clean editor에 instruction 입력과 generate action을 추가한다.
2. candidate prose·Gate decision/findings를 read-only panel에 표시한다.
3. pass candidate의 accept intent를 exact payload에 결박한다.
4. accepted save의 version detail을 재조회해 editor baseline/history를 새 latest로 갱신한다.
5. accepted=false·partial analysis failure·409 stale·provider/context failure에서 입력과 candidate를 보존한다.
6. focused frontend 회귀, full build/OpenAPI, 실제 compose generate→Gate→accept smoke를 수행한다.

### C2 — 자동 revise/retrieve loop

1. eligible revise finding에서만 `revise-and-gate`를 호출한다.
2. 마지막 candidate·Gate·loop status·stage progress를 표시한다.
3. partial 4xx/5xx에서도 candidate를 보존하고 error 종류와 재시도 가능성을 구분한다.
4. `pass|terminal_decision|not_eligible|budget_exhausted|no_change|failed`를 사용자 행동으로 매핑한다.

## Follow-up considerations

- candidate를 채택 전에 자주 수정한다면 D4=B를 열고 “편집 후 report/Gate 재평가”를 함께 결정한다.
- D4 재검토는 단순히 editable textarea를 붙이는 문제가 아니다. 후보 일부 수정 뒤 기존 report/Gate 근거가 stale해지는지, 저장 후 editor 수정→재생성이 충분한지, 사용자가 어느 흐름을 더 자연스럽게 느끼는지를 C1 UX에서 관찰한 뒤 결정한다.
- dirty context 생성 요구가 반복되면 D1=B를 검토하되, base 저장 후 candidate stale 판정과 재Gate가 한 계약으로 설계돼야 한다.
- C1 종료 직후 `OPS-1` trigger를 점검해 dogfood용 Lite/Full 실행 경로를 정한다.
- Writing 화면에서 loop stage가 실제 사용자에게 과도한 내부 정보라면 C2는 상세 접기 또는 운영 진단 전용으로 축소할 수 있다.
- 실 12B pointer 준수 관측은 C1 live smoke의 candidate report에서 함께 확인할 수 있으나, 실패가 재현되기 전 prompt를 변경하지 않는다.

## Deferred / out of scope

- autosave·dirty text 자동 합성·offline Writing request journal
- candidate inline diff/merge, 부분 선택 accept, candidate history
- `revise|outline|critique|rewrite_style` task type
- WritingBrief 편집 UI, voice/style 관리
- persisted loop audit 목록 UI와 retention 정책
- Review Inbox UI, memory card, source deep link
- `main.py` 전 도메인 router 일괄 분리
- Phase 7 대화형 수정·아이디에이션·directive 감독
