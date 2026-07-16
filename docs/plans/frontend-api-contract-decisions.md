# 착수 결정 브리프 — 백엔드 공개 계약 조이기 (H1 응답 타입 · H2 입력 검증)

상태: `Resolved — D1=A · D2=A · D3=A (owner confirmed 2026-07-16)` · 구현: SoT v1.6.95

관련 정본: `docs/system-contract-sot.md` v1.6.94("타입 계약 동기화의 실제 범위" 절), `plans/frontend-kickoff-decisions.md`, `docs/verifications/2026-07-16/frontend_first_slice.md`(H1·H2 hardening), HANDOFF Owner Decisions Needed

## Decision needed

오너가 **H1(응답 모델) → H2(입력 검증)** 순으로 진행하기로 했다. 방향은 정해졌으나, 착수하려면 **범위(D1)**·**적용 방식(D2)**·**입력 검증 위치(D3)** 세 가지가 필요하다. 셋 다 50 endpoint의 **공개 계약 표면**을 건드리고 되돌리는 비용이 크며, 기존 정본에 답이 없다(v1.6.94는 갭을 기록만 하고 "별도 결정"으로 넘겼다).

## 착수 전 실측한 사실 (1차 소스, 이 결정이 딛는 바닥)

브리프의 추측을 줄이기 위해 `services/application/app/main.py`(3148줄)를 직접 셌다:

- **endpoint 50개** 중 `-> dict[str, object]` 주석이 원인이 되어 OpenAPI 응답 schema가 빈 object(`additionalProperties: true`)로 나온다. 이것이 v1.6.94가 기록한 갭의 기계적 원인이다.
- **성공 경로는 50개 모두 `response_model`이 동작**한다. 그러나 **`/writing/revise-and-gate`·`/writing/accept`의 partial-failure 응답은 `JSONResponse`로 직접 반환**되고 — **FastAPI는 `JSONResponse` 직접 반환에 `response_model`을 적용하지 않는다**(검증도 OpenAPI 문서화도 우회) — 이 두 endpoint에서는 그 partial envelope(`candidate`/`gate`/`loop`/`stages`/`audit_id`/`audit_error`/`*_error`)이 **실패 시에도 계약의 일부**라(부분 산출물 보존) 모델만 붙여선 덮이지 않는다. **H1이 구조적으로 못 덮는 구멍이며, 하필 Writing 트랙(C 슬라이스)이 소비할 표면이다.** *(정정: 이 브리프 초안은 "2개 endpoint가 JSONResponse 직접 반환 → response_model 적용 불가"로 썼으나 **부정확**했다 — 두 endpoint의 성공 경로는 dict를 반환한다. uncoverable한 것은 endpoint 전체가 아니라 **partial-failure envelope**이다. 결론과 Deferred는 불변. 독립 검증 H1-d2, 2026-07-16.)*
- 중첩 payload 헬퍼 **20개**(`_project_payload` … `_gate_finding_payload`). 응답 모델은 endpoint 수가 아니라 이 헬퍼들의 중첩 구조만큼 필요하다.
- **`Field`/`field_validator`/`min_length` 사용처 = 0**. 요청 모델 5종(`CreateProjectRequest{name}` 등)은 전부 제약 없는 `str`이다. **H2는 이 저장소의 첫 입력 제약**이 된다.
- `core_sot/service.py:195` `create_project(name)`은 `Project(id=…, name=name)` 직접 생성 — 빈/공백 검증 없음(H2가 지적한 지점).

**핵심 리스크(양쪽 결정에 공통)**: FastAPI `response_model`은 **선언되지 않은 필드를 조용히 필터링**한다. 모델이 실제 payload보다 좁으면 **필드가 소리 없이 응답에서 사라진다** — 500도 경고도 없다. 안전망은 기존 회귀 1099개이며, 그 중 일부는 이미 exact-key set을 assert한다(예: loop audit detail "top-level 15키 + stage row 6키"). 즉 **이 작업의 안전성은 회귀 커버리지에 비례**한다.

## D1 — 적용 범위

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **D1=A. Product shell 척추 14개 먼저 (추천)** | 프론트가 지금·다음 슬라이스에서 실제 소비하는 것만: projects 5(create/list/get/rename/archive) + drafts 5(create/list/get/rename/archive) + versions 4(list/detail/save/export). *(구현 시 정정: 초안의 "13개(projects 2+drafts 8+snapshots 3)"는 endpoint 분류가 부정확했다 — 실제 척추 구성은 위 14개이고 source-refs/index rebuild는 척추가 아니다. 범위 의도는 동일.)* | 손선언이 **실제로 존재하는 자리**(`client.ts`)를 정확히 덮는다. 에디터 슬라이스가 붙기 직전에 계약이 잠긴다. payload가 단순(`{id,name,archived}` 수준)해 silent-field-loss 위험이 가장 낮고 회귀가 이미 두껍다. diff가 작아 검증 가능. | 나머지 37개는 계속 무타입. "언제 나머지를 하나"가 남는다. |
| D1=B. 48개 전체 한 번에 | 적용 가능한 모든 endpoint에 응답 모델. | 갭이 한 번에 닫히고 이후 슬라이스는 생성 타입만 쓴다. 계약 표면이 균일. | **20개 중첩 헬퍼 전부를 모델링**해야 한다(analysis·memory·context_search·writing·review inbox 어포던스 중첩까지). 큰 기계적 diff + silent-field-loss가 복잡한 envelope에서 가장 위험. **아직 UI가 만나보지 않은 envelope**(Writing·Review)까지 지금 고정하는데, C·B 슬라이스에서 모양이 바뀔 여지가 크다. 2개 JSONResponse 구멍은 어차피 안 덮인다. |
| D1=C. 슬라이스마다 그때그때 | 프론트가 소비하는 시점에 해당 endpoint만. | 낭비 0, 항상 실사용 근거. | A와 실질 차이는 "계획 없음". 에디터 슬라이스 중간에 계약 작업이 끼어들어 슬라이스 경계가 흐려진다. |

**추천: D1=A.** 이유: (1) 문제는 "50 endpoint에 타입이 없다"가 아니라 "**프론트가 손선언하는 자리에 타입이 없다**"이고, 그 자리는 지금 척추뿐이다. (2) Writing·Review envelope은 아직 UI가 만나지 않아 지금 고정하면 **UI가 요구를 발견할 때 계약을 두 번 만지게 된다** — 게다가 그 트랙의 핵심 2 endpoint는 `JSONResponse`라 H1으로 덮이지도 않는다. (3) silent-field-loss 리스크를 payload가 가장 단순하고 회귀가 가장 두꺼운 구역에서 먼저 감수해 패턴을 검증한 뒤 넓힐 수 있다.

## D2 — 적용 방식

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **D2=A. `response_model=` 파라미터, 헬퍼는 dict 유지 (추천)** | `@app.get("/projects", response_model=ProjectListResponse)`. 함수는 계속 `-> dict[str, object]`를 반환. | 표준 FastAPI 관용구(손으로 만든 dict를 모델로 검증). **payload 생성 코드 무변**(§3 surgical) — 헬퍼 20개를 건드리지 않는다. OpenAPI가 즉시 실제 schema를 낸다. | 함수 주석(`dict`)과 실제 계약(모델)이 두 곳에 나뉜다. |
| D2=B. 반환 타입 주석(`-> ProjectPayload`) | FastAPI가 주석에서 response_model을 추론. | 근본 원인(빈 schema를 만든 그 주석)을 그 자리에서 고친다. 선언이 한 곳. | 함수는 실제로 **dict를 반환**하는데 모델을 반환한다고 주석하게 된다(타입 검사기엔 거짓말). 헬퍼까지 모델로 바꾸면 D2=C가 된다. |
| D2=C. 헬퍼가 pydantic 모델을 반환 | `_project_payload`가 `ProjectPayload`를 반환. | 타입 안전성 최상, 주석이 진실. | 20개 헬퍼 + 모든 호출부 재작성. 이번 문제(프론트 타입)를 푸는 데 필요한 것보다 훨씬 큰 변경 = §2 위배. |

**추천: D2=A.** 이유: 우리가 풀려는 문제는 "OpenAPI가 응답 schema를 내지 않는다"이고, D2=A가 그걸 **payload 생성 코드를 한 줄도 건드리지 않고** 푼다. D2=B는 우아해 보이지만 dict를 반환하면서 모델 반환이라고 주석하는 거짓말을 남기고, D2=C는 이 슬라이스가 필요로 하지 않는 대규모 재작성이다.

## D3 — H2 입력 검증 위치

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **D3=A. HTTP 경계(pydantic `Field`) (추천)** | `CreateProjectRequest.name: str = Field(min_length=1)` + 공백 strip. 위반은 **422**. | **검증자가 지적한 위험을 정확히 닫는다** — "다른 클라이언트·trim 안 하는 미래 화면"도 전부 HTTP를 지나므로 경계에서 막힌다. Core SOT 정본 계약 무변. FastAPI 관용구이고 OpenAPI에 제약이 문서화돼 프론트 생성 타입에도 실린다. | `core_sot` 서비스를 직접 부르는 코드(scripts/worker/tests)는 여전히 빈 이름 생성 가능. 새 422 taxonomy 도입(현 400/409와 다른 채널). |
| D3=B. 서비스 계층(`core_sot`) | `create_project`가 빈 이름에 `CoreSotError` → HTTP 400. | **모든 호출자**(HTTP·scripts·worker) 커버. 정본 데이터 불변식이 정본 코드에 산다. | **Core SOT 정본 계약 변경**(새 거부 조건) → SoT 개정 필요. 기존 in-memory/Mongo 양 경로·회귀 영향. 로컬 1인 MVP엔 과하다. |
| D3=C. 둘 다 | 경계 422 + 서비스 400. | 심층 방어. | 같은 규칙이 두 곳(드리프트 위험). 지금 필요 없는 이중화 = §2. |

**추천: D3=A.** 이유: 검증자가 든 우회 시나리오("다른 클라이언트", "trim 안 하는 미래 화면")는 **전부 HTTP를 통과**한다 — 경계에서 막으면 보고된 위험은 닫힌다. D3=B는 정본 계약을 여는 값을 치르는데, 그게 추가로 사주는 건 "scripts가 빈 이름을 만드는 것"뿐이고 그건 지금 실재하는 위험이 아니다.

**D3에 딸린 sub-question**: strip을 서버가 할지(`" 이름 "` → `"이름"` 저장) 아니면 거부할지. 추천은 **서버 strip 후 검증** — 프론트가 이미 trim해서 보내고 있어 동작이 일치하고, 다른 클라이언트가 공백을 붙여 보내도 정본에 공백이 섞인 이름이 저장되지 않는다.

## Follow-up considerations

- **`revise-and-gate`·`accept`의 partial-failure envelope**: 두 endpoint의 성공 경로는 dict라 `response_model`을 붙일 수 있지만, `JSONResponse`로 나가는 partial 응답은 H1이 구조적으로 못 덮는다. Writing 작업공간(C 슬라이스)이 이 envelope을 소비할 때 (a) 성공 경로만 `response_model`+에러는 `responses={}`로 문서화할지, (b) partial envelope을 그대로 두고 프론트가 손선언할지를 그때 정한다. **지금 정하지 않는다** — UI가 무엇을 요구하는지 보고 정하는 게 싸다.
- **silent-field-loss 안전망**: D1=A 적용 후 회귀가 여전히 green이면 "모델이 payload를 좁히지 않았다"의 증거다. 척추 회귀가 실제로 envelope 키를 assert하는지 착수 시 확인하고, 부족하면 exact-key assertion을 먼저 보강한 뒤 모델을 붙인다(그래야 필드 유실이 테스트로 잡힌다).
- **프론트 후속**: D1=A가 끝나면 `npm run gen:api` 재생성 → `client.ts`의 손선언 `Project` 삭제하고 생성 타입 소비. 이때 H5(경로 타입 call-site 미소비)도 자연 해소된다.
- **422 vs 400**: D3=A는 422를 도입한다. 프론트 `ApiError`는 이미 status+detail을 보존하지만, 422 detail은 FastAPI validation error 구조(배열)라 현재 `readDetail`이 JSON.stringify로 떨어뜨린다. 사용자에게 보일 문구가 필요하면 그때 매핑한다.

## Deferred / out of scope

- 나머지 37 endpoint(analysis·memory·context_search·writing·review) 응답 모델 — D1=A 채택 시 해당 UI 슬라이스에서
- `JSONResponse` 2개의 partial envelope 계약 — 위 follow-up
- 요청 모델 5종 중 `name`/`title` 외 필드 제약(`raw_text` 빈 문자열 허용 여부, `idempotency_key` 형식) — 에디터 슬라이스에서 실제 필요가 보일 때
- Core SOT 정본 불변식 강화(D3=B) — 별도 결정
- mypy 등 타입 검사기 도입
