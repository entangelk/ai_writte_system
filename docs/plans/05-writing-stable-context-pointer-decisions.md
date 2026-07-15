# 착수 결정 브리프 — Phase 5.x Writing stable context pointer

상태: `Resolved — D1=A · D2=A · D3=A (owner confirmed 2026-07-15)`

관련 정본: `docs/system-contract-sot.md` v1.6.91, `05-writing-self-report-decisions.md` D2=A first→B·D5=B·D6=A first→C, `05-writing-report-api-decisions.md`, `context_search/models.py::ContextItem`, `indexing/models.py::IndexPointer`, `writing/prompt.py::format_context_package`

## Decision needed

Writing candidate report의 `candidate_claims[].related_context_pointers`를 열기 위해, 현재 ContextPackage가 이미 보유한 어느 identity를 stable pointer로 삼고 모델에게 어느 범위로 노출·검증할지를 확정해야 한다. 기존 정본은 “stable pointer 입력이 생기면 pointer 없는 schema를 full schema로 additive 확장”만 잠갔고, pointer wire·허용 목록·필수성은 정하지 않았다.

## Owner decision and rationale

- 오너는 2026-07-15에 추천 조합 **D1=A / D2=A / D3=A**를 확정했다.
- 기존 `05-writing-self-report-decisions.md`의 **D2=A first→B**는 반드시 유지한다. 여기서 A는 이미 구현된 pointer 없는 최소 typed schema이고, 이번 결정으로 후속 B인 full `related_context_pointers` schema 확장을 승인했다. 실제 B 구현은 다음 code slice다.
- 이 문서의 **D2=A**는 위 단계 표기의 A와 다른 결정 축이다. 즉 B 확장을 구현할 때 pointer를 **report extractor에만 표시하고 current-package exact allowlist로 검증**한다는 노출·검증 선택이다. `D2=A first→B`를 되돌리거나 B를 다시 보류한다는 뜻이 아니다.
- 신규 registry나 retention 정책을 열지 않고 기존 `IndexPointer` authority를 재사용해 다음 slice를 작게 유지하는 것이 선택 이유다.

## 현재 확정된 사실

- `ContextItem` 각 항목은 이미 `IndexPointer(project_id, collection, document_id, version_id, content_hash)`와 `snapshot_id`, `source_ref_ids` 및 본문 `text`를 가진다.
- Writing compact formatter는 현재 `[canonical|candidate] text`만 보여 주고 pointer/id를 숨긴다. report extractor는 이 formatter를 그대로 쓰므로 모델이 유효한 pointer를 선택할 수 없다.
- `CandidateClaim` 현 schema는 `{text,type,requires_gate_check}`이고 `related_context_pointers`가 없다. 이는 오너 D2=A first의 의도된 축소 schema다.
- persisted Writing loop audit의 `pointer_ids` 요약과 Context Gate finding persistence는 이미 package pointer identity를 본문 없이 보존하지만, claim별 연결 계약은 아니다.
- 아이디에이션 문서의 `{mongo_collection,mongo_id}`는 초기 예시다. 현 구현의 `IndexPointer`는 version/hash까지 가져 stale/reload 검증에 더 적합하다.

## D1 — stable pointer identity / wire

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **D1=A. 기존 `IndexPointer` projection** | public/model wire는 `{collection,document_id,version_id,content_hash}` exact object. `project_id`는 trusted request/candidate context에서 주입하고 모델 필드에서 제외. | 신규 저장소 없음, version/hash로 stale 검증 가능, source block·memory·candidate ContextItem 모두 동일 shape. | Mongo internal collection/document identity가 public candidate report에 노출됨. |
| D1=B. `source_ref_ids` only | claim은 당시 package item의 source reference id만 연결. | Core SOT 근거와 직접 연결, wire가 작음. | source_ref가 없는 item을 가리키지 못하고, memory/candidate entity 자체보다 그 근거 span만 가리킴. |
| D1=C. 신규 opaque `context_pointer_id` | server가 pointer registry/id를 mint·persist하고 claim은 id만 반환. | DB identity 은폐, wire 작음, 후속 schema 변경 용이. | registry collection·retention·idempotency·dereference API가 새로 필요해 “작은 slice”가 아님. |

**추천: D1=A.** 현재 시스템이 이미 Mongo 정본을 재유도하는 포인터를 모든 ContextItem에 보유한다. 로컬 1인 프로젝트 단계에서 opaque registry를 추가하는 것은 지나치고, `source_ref_ids`만으로는 memory/candidate-origin item 정체성을 손실한다. `project_id`를 외부 모델이 반환하지 않게 하면 cross-project id 위조 표면도 늘리지 않는다.

## D2 — 모델 노출·선택·검증 경계

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **D2=A. report extractor에만 표시 + exact allowlist** | report request의 ContextPackage item에 pointer object를 표시. 모델이 claim에 반환한 각 pointer는 **동일 request package에 있던 exact object**여야 하며 unknown/cross-project/field mismatch/duplicate는 first parse 실패→1회 repair→계속 실패 502. | 만드는 모델은 prose만 생성하는 기존 계약 불변, hallucinated id fail-closed, 변경 표면 최소. | generation turn은 pointer를 모르고 report turn만 연결하므로 두 turn 사이의 의도를 직접 전달하지 못함(현 구조상 report가 candidate+package를 재해석). |
| D2=B. generation·revise·report·Gate 모두 pointer 표시 | 모든 Writing prompt의 compact ContextPackage에 pointer를 노출. | 모든 단계가 동일 identity를 봄. | 평문 generation/revise 프롬프트 token·주의 표면을 불필요하게 바꾸고, pointer 출력을 하지 않는 turn에 DB id를 노출. |
| D2=C. 모델 미노출 + server text-match 후부착 | report model은 종전 schema를 반환하고 server가 claim text와 package item text를 매칭해 pointer를 붙임. | 모델이 id를 만들 수 없음. | semantic alignment 규칙이 새로 필요하고, 잘못된 pointer를 server 권위로 붙일 수 있음. |

**추천: D2=A.** D2=A first→B의 문제는 “모델이 보지 못한 id를 만들 수 없다”였다. extractor에 package-scoped allowlist를 보여 주고 exact membership를 server가 검증하면 그 문제를 직접 닫는다. generation과 revise는 pointer를 출력하지 않으므로 현 프롬프트를 유지한다.

## D3 — candidate report schema 범위·필수성

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **D3=A. claim에 required array, empty 허용** | `candidate_claims[]` exact schema에 `related_context_pointers: ContextPointer[]` 필드를 **필수**로 추가. 직접 근거가 없는 새 사건/해석은 `[]`; package 근거를 사용한 claim은 해당 pointer 1개 이상. hint/risk schema는 무변. | strict full schema가 항상 동일 shape, missing-vs-empty 모호성 없음, D2=A first→B를 완전히 종결. | 신규 필드 없는 이전 report JSON은 신 parser에서 invalid(현 report는 비영속·재추출 가능). |
| D3=B. claim의 optional field | pointer가 있을 때만 field를 넣음. | 기존 report 호환. | strict exact-schema 원칙을 완화하고 missing과 empty가 다른 의미인지 모호. |
| D3=C. claim·hint·risk 모두 pointer | 네 report 개념 전반에 pointer 배열 추가. | 최대 추적성. | D2가 확정한 후속은 candidate **claim pointer**이며 hint/risk authority·소비자 계약은 미확정. scope 과대. |

**추천: D3=A.** strict terminal JSON 선례와 맞고, pointer가 없음을 `[]`로 명시해 선택적 field 분기를 없앤다. 현 report/candidate는 별도 entity로 영속하지 않아 migration이 필요 없고, accept가 새로 만든 immutable advisory copy에는 새 field를 그대로 실으면 된다.

## Recommendation + reason

**D1=A / D2=A / D3=A**를 추천한다.

로컬 1인 프로젝트·정본 보존 제약에서 이 조합이 신규 persistence 없이 현 `IndexPointer` authority를 재사용하고, 모델이 보지 못한 id를 만드는 것을 exact allowlist로 차단하며, pointer 생산 책임을 report extractor 한 turn에만 제한한다. 신규 registry(D1=C)나 semantic post-match(D2=C)와 달리 다음 code slice가 dataclass·formatter·parser·serializer 확장으로 제한된다.

## 승인 시 잠김 구현 계약

1. 신규 immutable `ContextPointer` = `collection`, `document_id`, `version_id`, `content_hash` 네 non-empty string. public/model key도 동일 literal을 쓴다.
2. `project_id`는 pointer object에 실지 않고 trusted candidate/package project에서 유도. package item pointer가 다른 project면 provider 호출 전 거부.
3. report extractor용 formatter만 ContextItem text 앞에 canonical JSON pointer를 표시한다. generation/revise 평문 formatter는 무변하도록 별도 함수/옵션을 쓴다.
4. `CandidateClaim` / public HTTP wire / accept→Analysis advisory copy에 `related_context_pointers` required array를 additive 추가. Gate prompt가 받는 candidate claim에도 동일 pointer를 실어 D5=B 소비 경계를 보존하되, Gate decision schema는 무변.
5. report parser는 exact fields/type 후 package allowlist membership를 검증. unknown pointer·rogue field·cross-project package·중복 pointer는 invalid이며 1회 repair로도 복구 안 되면 기존대로 502.
6. pointer는 근거 연결이지 source_ref mint·canon 승격·자동 save 권한이 아니다. Mongo/Core SOT/loop audit 쓰기 수는 무변.

## 양방향 회귀 매트릭스

- **under-strict**: package에 있는 source-block/memory/candidate 포인터를 각각 claim이 반환하면 parse·HTTP·Gate·accept advisory까지 exact object 보존.
- **over-strict**: 근거 없는 새 claim의 `[]`는 유효하고 정상 prose/report를 거부하지 않음.
- hallucinated document/version/hash·다른 package의 valid-looking pointer·cross-project item·rogue/missing pointer field·duplicate는 모두 거부.
- 마크다운 fence 추출은 유효 pointer JSON에도 동일하게 적용되지만 schema/allowlist를 완화하지 않음.
- pointer 추가 후도 generation/revise prompt·Gate decision literal·report provider repair 횟수·loop stage/audit bodyless schema·Core SOT/Analysis candidate mint 수는 무변.

## Follow-up considerations

- 후속 persisted candidate/report entity가 열리면 `ContextPointer` object를 그대로 저장하고, 조회 시 project+version+hash로 stale/dereference 검증할 수 있다.
- `source_ref_ids`는 pointer identity에 포함하지 않고 ContextItem의 별도 provenance로 유지한다. 후속 UI가 인용 span을 필요로 하면 pointer를 재유도한 뒤 source_ref catalog를 조회한다.
- public DB identity 노출이 문제가 되는 multi-user/auth 단계에선 D1=C opaque projection을 additive API version으로 열 수 있다.
- 현 `IndexPointer.version_id`/`content_hash`는 collection kind에 따라 생성 근거가 다르다. 구현 전 source-block·memory·candidate 세 origin의 non-empty 불변식을 fixture로 재확인하고, 현 실경로에서 empty가 가능하면 owner 승인 없이 빈값을 허용하지 않는다.

## Deferred / out of scope

- opaque pointer registry·pointer id persistence·dereference HTTP API
- persisted WritingCandidate/report entity·report revision history·retention
- pointer로 AnalysisCandidate 또는 MemoryEntry 직접 mint
- hint/risk pointer, `used_context_package_id`, context package persistence
- frontend citation UI·source span preview
- persisted loop audit `pointer_ids` schema 변경(현 run-level/stage-level package 요약은 그대로 유지)
