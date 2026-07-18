# Phase 2A Provider/Gateway Wiring 결정 브리프

상태: `Approved for Phase 2A provider wiring pre-implementation`  
기준 문서: [`system-contract-sot.md`](../system-contract-sot.md), [`02-analysis-pipeline.md`](02-analysis-pipeline.md), [`02-analysis-runner-execution-decisions.md`](02-analysis-runner-execution-decisions.md), [`llm-gateway.md`](llm-gateway.md)  
작성일: `2026-07-01`  
승인일: `2026-07-01`  
목적: Phase 2A `run` endpoint에 실제 provider/Gateway runner factory를 연결하기 전에 prompt, JSON output, source_ref 생성 경계를 확정한다.

## 현재 확정된 경계

- Phase 2A 최소 taxonomy는 `character_observation`, `event_observation`, `open_question_observation` 3종이다.
- Phase 2A provider extraction output은 top-level `{candidates: [...]}` JSON object여야 한다.
- 각 candidate는 approved literal, provenance, confidence, `source_anchors`, payload schema를 통과해야 한다.
- `source_anchors`는 기존 `SourceRef`와 대조한다. source_ref 없음, cross-project, span/quote/hash mismatch는 candidate 저장을 거절한다.
- `POST /projects/{project_id}/analysis/jobs/{job_id}/run`은 runner dependency가 구성된 경우에만 pending job을 실행한다. pending job에서 runner 미구성은 503이다.
- `run` endpoint는 source_ref 자동 생성과 Gateway runtime wiring을 아직 소유하지 않는다.
- LLM Gateway는 model lifecycle, inference, provider error, usage/timing을 소유한다. prompt의 업무 의미, source_ref 생성/검증, domain tool 실행은 소유하지 않는다.
- Gateway/model tool-call response wire format은 미확정이다. 따라서 이번 브리프는 **tool-call 없이 terminal JSON extraction만** 다룬다.

## 결정해야 할 질문

### 1. Phase 2A 실제 extraction은 tool-call을 요구하는가?

선택지:

| 옵션 | 설명 | 장점 | 리스크 |
|---|---|---|---|
| A. tool-call 없이 terminal JSON만 받는다 | 모델은 최종 content에 `{candidates: [...]}` JSON을 반환한다 | 이미 구현된 `AnalysisExtractionAdapter`와 Gateway text generation 계약을 재사용할 수 있음 | source_ref 후보를 모델이 직접 만들 수 없으므로 입력 anchor 선택 방식이 필요함 |
| B. model tool-call로 source_ref 생성/후보 저장을 지시한다 | 모델이 domain tool call을 반환한다 | 장기 agent loop 구조와 가까움 | Gateway tool-call parsing, model wire format, handler payload가 모두 미확정 |
| C. Gateway structured endpoint가 parsed output을 보장한다 | Gateway가 schema/grammar를 강제해 parsed JSON을 반환한다 | malformed JSON 감소 | `/v1/generate-structured` 계약과 schema failure envelope가 아직 없음 |

결정: **A**. Phase 2A 실제 provider wiring 첫 slice는 tool-call 없이 terminal JSON만 받는다.

이유:

- 글쓰기 프로그램의 source reference 후보는 정적으로 만들 수 있고, 기계적으로 anchor 선택이 가능하다는 사용자 판단을 반영한다.
- 현재 `ProviderTurnResult`와 `AnalysisExtractionAdapter`가 terminal content를 이미 소유하고 있다.
- tool-call branch는 Gateway parsing, model wire format, handler payload가 모두 미확정이다.

### 2. 모델은 source_ref를 어떻게 참조하는가?

선택지:

| 옵션 | 설명 | 장점 | 리스크 |
|---|---|---|---|
| A. 입력에 기존 source_ref anchor catalog를 주고 모델이 `source_ref_id`를 선택한다 | Application/Worker가 snapshot의 source_ref catalog를 prompt에 포함한다 | 모델이 새 source_ref를 만들지 않으므로 기존 validation 경계와 일치 | source_ref가 미리 없으면 후보를 만들 수 없음 |
| B. 모델이 quote/span을 반환하고 Application이 source_ref를 생성한다 | source_ref 사전 생성이 없어도 실행 가능 | provider output에서 span 계산/검증/생성 idempotency 경계를 새로 정해야 함 |
| C. runner가 source_blocks를 모두 source_ref로 pre-materialize한다 | 모델은 준비된 anchor만 선택 | source_ref가 대량 생성될 수 있고 non-idempotent primitive와 운영 의미가 섞임 |

결정: **A**. 첫 실제 wiring slice는 기존 source_ref anchor catalog를 입력으로 주고 모델이 `source_ref_id`를 선택하게 한다. source_ref 자동 생성은 별도 slice로 둔다.

이 추천안을 채택하면 `run`을 실행하기 전에 같은 project/snapshot에 필요한 source_ref가 준비되어 있어야 한다. source_ref가 없어서 후보를 만들 수 없는 상태는 provider/runtime 오류가 아니라 입력 준비 정책의 문제로 남는다. 이 정책을 HTTP에서 어떻게 표면화할지는 구현 slice 전에 별도 확인이 필요하다.

2026-07-01 follow-up: source_ref catalog 준비용 Application HTTP surface가 추가됐다. `POST /projects/{project_id}/snapshots/{snapshot_id}/source-refs`가 snapshot span에서 source_ref를 만들고, `GET /projects/{project_id}/snapshots/{snapshot_id}/source-refs`와 `GET /projects/{project_id}/source-refs/{source_ref_id}`가 같은 project 안에서 catalog/ref를 조회한다.

### 3. prompt 조립은 어디서 소유하는가?

선택지:

| 옵션 | 설명 | 장점 | 리스크 |
|---|---|---|---|
| A. Application/Worker runner factory가 prompt를 조립한다 | Gateway는 generic generation만 수행 | SoT의 Gateway 책임 경계와 일치 | prompt version 추적을 Application 쪽에 둬야 함 |
| B. Gateway가 `task_type=analysis_extract`의 prompt를 안다 | Gateway 호출이 단순 | Gateway가 업무 의미를 소유하게 되어 경계 위반 |
| C. prompt template을 DB에 저장한다 | 운영 중 변경 가능 | MVP 첫 slice에는 과함 |

결정: **C**. Prompt template은 DB에 저장하고 versioned 관리한다.

이유:

- prompt 변경과 version 추적은 실제 운영 중 필요할 가능성이 높다.
- Agentic loop context, ContextPackage, prompt assembly 같은 후속 계약도 체계적으로 관리해야 하므로 template/version 저장 경계를 미리 둔다.
- Gateway는 여전히 업무 의미를 소유하지 않는다. DB 저장 prompt template은 Application/Worker domain contract이며, Gateway에는 generic messages, generation params, request id만 전달한다.

첫 구현은 과도한 template 관리 UI를 만들지 않는다. 최소 저장소/seed/fetch 경계만 두고, 편집 UI와 운영 정책은 후속 Product Shell 또는 Worker configuration slice에서 다룬다.

### 4. 첫 prompt/output schema의 최소 literal은 무엇인가?

결정 contract:

- `prompt_version`: `analysis_extract_v1`
- `task_type`: `analysis_extract`
- 입력에는 snapshot metadata, source_ref anchor catalog, 최소 taxonomy 설명을 포함한다.
- 모델은 JSON object 하나만 반환한다.
- top-level key는 `candidates` 하나다.
- `candidates`는 list다.
- 각 item은 기존 extraction adapter가 요구하는 field를 그대로 사용한다.
- 모델은 새로운 `source_ref_id`를 만들지 않고 입력 catalog에 있는 id만 사용한다.
- 모델은 원문에 없는 사실을 보충하지 않는다.
- 후보가 없으면 `{"candidates": []}`를 반환한다.

구체 payload 예시는 구현 slice에서 test fixture와 함께 고정한다. `analysis_extract_v1`과 `analysis_extract`는 Phase 2A provider wiring의 첫 prompt/template literal로 사용한다.

#### 2026-07-18 dogfood amendment — `analysis_extract_v2` → `analysis_extract_v3`

accept report의 구 snapshot `related_context_pointers.document_id`와 새 snapshot의 `source_ref_catalog.source_ref_id`가 같은 prompt payload에 들어갈 때 실 12B가 anchor namespace를 혼동할 수 있음이 확인됐다. 오너 결정 C(`docs/live_review_briefs/2026-07-18/analysis_retry_after_accept.md`)로 immutable literal `analysis_extract_v2`를 추가했으나, 실제 실패 job 재실행에서 주의 문구만으로는 같은 `source_invalid`가 재현됐다. 이미 seed된 v2는 덮어쓰지 않고 보존하며, 출력 필드 계약·advisory→authoritative 직렬화 순서·report 식별자를 제외한 repair catalog를 구조적으로 잠근 새 immutable **`analysis_extract_v3`**를 기본 prompt로 승격한다.

- `writing_candidate_report.related_context_pointers`는 advisory provenance이며 Analysis output의 source anchor가 아니다.
- `source_anchors[].source_ref_id`는 현재 payload의 `source_ref_catalog[].source_ref_id` literal만 복사한다. report의 `document_id`/`version_id`/`content_hash`를 source anchor identity로 사용하지 않는다.
- 위 구분을 first system prompt와 repair prompt 양쪽에 명시한다.
- v1 template은 이력/재현을 위해 보존하고 v2를 새로 seed한다. strict schema/catalog validation과 repair 1회 상한은 무변이다.

### 5. Gateway 호출 surface는 어느 것을 쓰는가?

결정: **첫 구현 slice는 `/v1/generate` 임시 사용으로 진행한다.**

사용자 방향:

- `/v1/generate`와 structured generation surface는 서로 분리되는 편이 좋아 보인다.
- 다만 현재 단계에서는 임시 통합 후 분리가 가능한지, 그리고 structured path를 지금 여는 비용이 어느 정도인지 먼저 확인한다.
- 어차피 구현해야 할 가능성이 높은 통로라면 미리 열어두는 것도 허용한다.

확인할 선택지:

| 옵션 | 설명 | 채택 조건 |
|---|---|---|
| A. `/v1/generate` 임시 사용 | 현재 text generation surface로 content JSON을 받고 Application adapter가 검증한다 | structured endpoint를 지금 열 비용이 크고, adapter 경계로 후속 분리가 쉬움 |
| B. `/v1/generate-structured` 최소 구현 | Gateway가 schema/grammar 또는 structured-output contract를 별도 endpoint로 제공한다 | 구현 비용이 작고, Phase 2A fixture로 schema failure envelope를 안정적으로 잠글 수 있음 |

구현 중 코드 구조를 확인한 결과, `/v1/generate-structured`를 지금 제대로 열려면 Gateway public schema failure envelope와 structured-output contract를 새로 정해야 한다. 현재 Phase 2A Application adapter가 provider content JSON parsing과 schema validation을 이미 소유하므로 첫 slice는 `/v1/generate`를 사용한다. 대신 Application→Gateway adapter 경계를 별도로 두어 structured endpoint가 생기면 교체 가능하게 한다.

현재 판단 기준:

- `/v1/generate-structured`는 계획 초안에 있지만 아직 구현된 public contract가 아니다.
- current provider client는 text completion 성공 응답의 `message.content`와 usage를 검증한다.
- Phase 2A adapter가 content JSON parsing과 schema validation을 이미 담당한다.

structured generation/grammar는 malformed JSON 비율이나 schema failure envelope 필요가 확인되면 후속 Gateway slice로 올린다.

2026-07-01 live smoke follow-up:

- 실제 Gemma/llama.cpp 호출에서 첫 output은 markdown-fenced JSON이거나 adapter가 요구하는 candidate schema보다 얕은 JSON일 수 있음을 확인했다.
- `chat_template_kwargs.enable_thinking=false`를 명시하면 simple JSON 요청은 `message.content`로 정상 반환된다. `response_format={"type":"json_object"}`도 endpoint에서 거절되지는 않았지만, 이번 slice의 Application/Gateway 계약은 아직 `/v1/generate` text surface를 사용한다.
- 사용자 결정에 따라 `/v1/generate-structured` public contract를 바로 열기보다 Application-side repair를 먼저 적용한다. Versioned extraction adapter는 strict parser 실패 시 원문 output과 parser error, 원래 prompt payload를 포함해 repair prompt를 1회만 재호출한다. repair output도 같은 strict parser와 source validation을 통과해야 하며 실패하면 `schema_invalid`로 보존한다.
- HTTP source_ref 준비 경로를 탄 live smoke에서 model이 catalog id `source-ref-1`을 `source_ref-1`로 바꾸는 실패가 확인됐다. Versioned extraction adapter는 parsed output의 source anchors를 입력 catalog와 대조하고, catalog literal mismatch도 같은 1회 repair 대상으로 삼는다. 자동 normalization은 하지 않으며 repair 후에도 mismatch가 남으면 기존 source validation 실패를 보존한다.

### 6. runner factory의 최소 구성은 무엇인가?

결정:

1. Application/Worker가 `CoreSotSourceAdapter`로 snapshot raw text/hash/block ids를 로드한다.
2. 같은 project/snapshot의 기존 source_ref catalog를 조회한다.
3. DB에서 versioned prompt template `analysis_extract_v1`을 로드해 prompt를 만든다.
4. Gateway `/v1/generate`를 호출하는 provider adapter를 `AnalysisExtractionRunner`에 주입한다.
5. Provider content는 기존 `AnalysisExtractionAdapter`를 통과한다.
6. Source validation과 candidate 저장은 기존 runner/service 경계를 그대로 사용한다.

이 slice는 domain tool-call branch, source_ref 자동 생성, background Worker polling을 포함하지 않는다. structured Gateway endpoint는 비용 확인 결과에 따라 포함 여부를 결정한다.

## 추천 최소 slice

승인 뒤 구현 순서:

1. SourceRef catalog read + HTTP preparation surface 추가
   검증: 같은 project/snapshot source_ref만 prompt input으로 제공, cross-project ref 제외. HTTP로 snapshot span에서 source_ref를 만들고 catalog/ref를 다시 읽는다.
2. Prompt template DB 최소 저장소/seed/fetch surface 추가  
   검증: `analysis_extract_v1` version을 조회하고, 없는 version은 명시적으로 실패한다.
3. `analysis_extract_v1` prompt builder 추가  
   검증: prompt가 catalog id를 포함하고 Gateway/domain 책임 경계를 넘지 않는다.
4. Gateway surface 비용 확인 spike  
   완료: `/v1/generate-structured`는 Gateway schema failure envelope 계약이 필요하므로 후속 slice로 보류하고, `/v1/generate` adapter를 separable하게 구현한다.
5. Gateway-backed extraction provider adapter 추가  
   검증: 선택한 Gateway surface의 content/parsed output을 기존 `AnalysisExtractionAdapter`로 넘기고 provider error를 runner의 `provider_error`로 보존한다.
6. `create_app` 기본 runtime runner factory wiring 추가  
   검증: runner 미구성 503이 실제 구성 환경에서는 pending job 실행으로 바뀌고, fake/contract tests는 그대로 유지된다.
7. live smoke는 기존 Gemma/llama.cpp endpoint가 있을 때 별도 실행  
   검증: 최소 snapshot/source_ref fixture에서 `run`이 terminal job을 만들거나 provider/schema failure를 안정적으로 보존한다.

## 승인 결정 요약

- Phase 2A 실제 provider wiring 첫 slice는 **tool-call 없이 terminal JSON extraction**으로 구현한다.
- source_ref 후보는 정적으로 만들 수 있고 기계적으로 anchor 선택이 가능하다는 전제 아래, 모델은 새 source_ref를 만들지 않고 **입력 source_ref catalog의 id를 선택**한다.
- source_ref 자동 생성은 별도 slice로 미룬다.
- prompt template은 DB에 저장하고 versioned 관리한다. prompt 조립과 prompt version은 Application/Worker domain contract다.
- 첫 prompt version literal은 `analysis_extract_v1`, task_type은 `analysis_extract`다.
- Gateway 호출 surface는 첫 구현 slice에서 `/v1/generate`를 사용한다. `/v1/generate-structured`는 후속 Gateway slice로 둔다.
- runner factory 최소 구성은 추천안대로 진행한다.
