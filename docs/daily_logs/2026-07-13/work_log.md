# Work Log — 2026-07-13

## Goals

- `HANDOFF.md`와 2026-07-12 작업 로그를 읽고 다음 순차 작업을 정본에 따라 착수한다.
- 로컬에서는 LLM 제외 테스트를 사용하고, 필요한 LLM live 검증은 `192.168.1.22:9080`의 응답·생성·Think 범위로 제한한다.

## Completed work

### Phase 5.5 Writing report 재평가 API 착수 점검

- 정본 우선순위를 확인했다: `docs/system-contract-sot.md`가 최상위이고 `docs/plans/README.md`가 개발 진입점이다.
- HANDOFF의 Writing 후속 중 이미 필수 기능으로 확정된 `/writing/report`를 다음 후보로 선정하고 SoT v1.6.71과 `05-writing-self-report-decisions.md` D3/D6를 대조했다.
- `docs/plans/05-writing-report-api-decisions.md`를 작성해 inline candidate 즉시 구현, persistence 후 id 기반 구현, 두 단계 구현의 현실적인 선택지와 추천안을 기록했다.
- owner 결정 전 public contract를 추측하지 않도록 production code는 변경하지 않았다.

### Phase 5.5 Writing report 재평가 API 구현 (SoT v1.6.72)

- 오너가 A를 승인하고 B의 persisted candidate/report 감사 이력 확장을 열어두라고 결정했다. A의 세부 경계는 inline candidate+서버 ContextPackage 재구성으로 확정했다.
- `main.py`에 `WritingReportRequest`, 주입 가능한 `writing_report_service`, `POST /projects/{id}/writing/report`를 추가했다. endpoint는 inline candidate를 만들고 기존 context search와 `WritingCandidateReportService.enrich`를 재사용하며 저장·Gate·accept·Analysis side effect는 만들지 않는다.
- 응답은 기존 public WritingCandidate envelope를 재사용한다. 내부 enum field 이름은 노출하지 않고 `candidate_id=null`이라 비영속 경계가 드러난다.
- 빈 request id/instruction/candidate text·unsupported task는 400, missing project 404, service/context 미구성 503, malformed report·일반 provider/context backend 502, provider timeout/context budget 504로 잠갔다.
- `tests/test_writing.py`에 HTTP 회귀 4개(+8 subtests)를 추가했다. 정상 server-context 관통, public `type` 직렬화, no-persistence 표시, 빈 입력 pre-provider 거부, dependency/project isolation, report/context error mapping을 양방향으로 검사한다.
- 실 LLM에서 report prompt가 실제 enum 목록과 item shape를 제공하지 않는 결함을 발견해 `writing/report.py` template에 exact JSON 골격·전 enum literal·confidence/empty-array 규칙을 명시했다. `tests/test_writing_report.py`가 initial/repair system prompt에 같은 schema가 존재함을 잠근다.
- 브리프를 Resolved로 전환하고 SoT·Phase 계획·CHANGELOG·HANDOFF를 v1.6.72 상태로 갱신했다.

## Issues found

- 문제: D3는 별도 `/writing/report` API를 후속 필수로 확정하지만, 같은 브리프의 Follow-up은 candidate persistence/identity 이후로 제한하고 Deferred는 candidate/report persistence를 범위 밖으로 둔다.
- 원인: v1.6.71 첫 slice에서 generate 합성만 구현하면서 재평가 API의 identity 경계를 후속 문구 두 곳에 서로 다르게 남겼다.
- 해결/결과: 입력 계약이 inline object인지 persisted candidate id인지 오너 결정 없이는 도출되지 않으므로 구현을 중단하고 결정 브리프로 전환했다.
- 문제: `192.168.1.22:9080` 실모델은 기존 report prompt의 “supplied enum literals” 지시만으로 typed item schema를 알 수 없어 첫 출력과 repair가 모두 strict parse에 실패했다.
- 원인: prompt가 top-level field 이름만 나열하고 claim/hint/risk의 exact fields와 enum 값을 실제로 제공하지 않았다. fake provider 회귀는 완성 JSON을 직접 반환해 이 결함을 가렸다.
- 해결/결과: exact JSON 골격과 모든 enum literal을 initial/repair prompt에 동일하게 제공했다. 재실행은 `status=ok`, claims 2, hints 1, risk 0으로 strict parser를 통과했다.
- 관찰: 첫 clean-exit 확인용 one-liner는 HTTP client를 다른 event loop에서 닫아 cleanup `RuntimeError`를 냈다. 같은 loop의 `/tmp` smoke로 재실행해 exit 0을 확인했으며 production 결함이 아니다.

## Decisions

- 사용자 제약: 이 머신에서는 LLM 제외 테스트가 가능하다. LLM live 검증은 `192.168.1.22:9080`을 사용하되, 프로젝트 전용 모델이 아니므로 응답·생성·Think 외 capability나 프로젝트 품질을 전제하지 않는다.
- 작업자 추천: 신규 persistence 없이 기존 extractor를 재사용하는 side-effect-free inline API(A)를 먼저 구현한다. 오너 확정 전에는 채택하지 않는다.
- 사용자 결정: A를 채택하되 B의 persisted candidate/report 감사 이력과 id 기반 API를 나중에 additive로 구현할 수 있게 둔다. 현재 slice에서는 speculative persistence/revision 모델을 만들지 않는다.
- 파생 결정: A의 ContextPackage는 client 제출을 신뢰하지 않고 서버가 기존 context-search 입력으로 재구성한다.

## Verification

- focused: `python3 -m pytest -q -p no:cacheprovider tests/test_writing_report.py tests/test_writing.py tests/test_writing_gate.py tests/test_writing_accept.py` → **68 passed / 53 subtests**.
- full: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **880 passed / 45 skipped / 154 subtests**. 종전 48 skip 대비 이 머신은 Elasticsearch Python dependency가 있어 3개가 실제 실행됐다.
- remote health: `curl ... http://192.168.1.22:9080/health` → `{"status":"ok"}`.
- remote report live: 실제 `LlamaCppProvider`+`WritingCandidateReportService`+strict parser/repair를 `192.168.1.22:9080`에 연결 → `{'status': 'ok', 'constraints': 0, 'claims': 2, 'hints': 1, 'risks': 0, 'claim_types': ['narrative_event', 'narrative_event']}`, exit 0.
- `git diff --check`, `python3 -m py_compile`은 최종 문서 반영 뒤 재확인한다.

### 독립 검증 조건부 합격 closure + hardening

- 독립 검증 `docs/verifications/2026-07-13/writing_report_api.md`를 직접 대조했다. 구현·enum exactness·NEW 성공/OLD 실패 live 재현은 통과했으나, report endpoint의 `unsupported task_type→400` 계약 셀이 전용 테스트 없이 비어 있다는 B1 판정이 타당했다.
- **B1 closure**: `/writing/report`에 `task_type="revise"`를 제출해 400이고 reporter가 호출되지 않음을 직접 잠갔다. 기존 generate endpoint 테스트에 의존하지 않는다.
- **H1**: code-enforced `InvalidContextSearchRequest→400`을 SoT v1.6.72 상태맵에 명시하고 전용 mapping subtest를 추가해 spec-silent gap을 닫았다.
- **H2**: `_NoWriteCoreSotService.save_draft` spy로 report 200 동안 save 호출이 0임을 직접 단언했다. `candidate_id=null` proxy에만 의존하지 않는다.
- **H3/H4**: explicit `query` override와 `current_position(draft_id/version_id)`가 context search request에 그대로 전달되는 HTTP 회귀를 추가했다.
- production 동작은 변경하지 않았다. 테스트·SoT·상태 기록만 보강했다.
- closure focused: **71 passed / 54 subtests**. closure full: **883 passed / 45 skipped / 155 subtests**.

## Next steps

- persisted WritingCandidate/report의 identity·revision·retention·idempotency를 별도 착수 브리프로 결정한 뒤 B의 감사 이력과 id 기반 API를 additive로 구현한다.
- stable ContextPackage pointer가 extractor 입력에 제공되면 full `related_context_pointers` schema를 연다.
- 다음 Writing 후보는 finding evidence 기반 부분 revise/retrieve orchestration이다.

## Phase 5.6 finding evidence 기반 부분 revise 착수 브리프

### Goals

- v1.6.72 커밋 후 HANDOFF의 다음 Writing 후보인 finding evidence 기반 부분 revise/retrieve orchestration의 구현 전 계약을 확정 가능한 결정 단위로 분리한다.

### Completed work

- v1.6.72 구현·독립 검증·closure 전체를 커밋 `25be309`(`feat: add writing report reevaluation API`)으로 묶었다.
- `05-writing-gate-decisions.md` D3/Follow-up, `05-writing-accept-decisions.md` revision patch 후속, SoT v1.6.69~72, `writing_agent_prompt.md` §16.2를 대조했다.
- `docs/plans/05-writing-partial-revise-decisions.md`를 작성해 첫 범위, evidence anchor, 모델 출력/splice 책임, finding 수, 재검증, public identity, budget/실패 의미와 unchanged 결과를 D1~D8로 분리했다.

### Issues found

- 기존 정본은 자동 전체 재생성을 금지하고 evidence 기반 부분 revise를 요구하지만, evidence 중복·overlap·replacement 형식·새 candidate identity·Gate 재평가·반복 budget을 확정하지 않았다.
- `retrieve_more`는 query/needs와 ContextPackage identity까지 추가로 결정해야 하므로 부분 revise와 한 slice에 묶으면 public 실패/budget 계약이 과도하게 커진다.

### Decisions

- 작업자 추천은 revise-only, 단일 continuity finding, evidence exact 단일 발생, 평문 replacement+서버 splice, Gate 별도 호출, inline API first+persistence 감사 이력 additive 후속, LLM 1회다.
- D1~D8은 owner-level public contract이므로 오너 승인 전 production code를 시작하지 않는다.

### Next steps

- 오너가 `05-writing-partial-revise-decisions.md` D1~D8을 확정하면 SoT 반영→boundary tests 우선→최소 revise service/API→비-LLM 전체 회귀→`192.168.1.22:9080` live smoke 순서로 진행한다.

## Phase 5.6 finding evidence 기반 부분 revise 구현 (SoT v1.6.73)

### Goals

- 승인된 D1~D8에 따라 모델은 replacement fragment만 생성하고 Application이 exact anchor 검증과 splice를 소유하는 첫 부분 revise slice를 구현한다.

### Completed work

- 오너 결정: D1=A, D2=A first→C, D3=A, D4=A first→C, D5=A→B→C, D6=C, D7=A first→C, D8=A first→C. 모델/provider는 호출·응답에 집중하고 anchor 산술·검증·splice·loop/budget은 Application이 소유한다는 원칙을 SoT v1.6.73에 잠갔다.
- `writing/revise.py`에 `WritingRevisionService`와 전용 평문 replacement prompt를 추가했다. continuity+revise finding 하나, evidence exact 단일 발생만 provider에 전달한다.
- provider 응답은 replacement fragment로만 취급하고 Application이 `prefix + replacement + suffix`를 splice한다. 빈/unchanged replacement는 `InvalidWritingRevision`이며 첫 slice에서 502다.
- revised candidate는 기존 task/output/status를 유지하되 변경된 text와 불일치하는 report 네 필드를 비우고 `candidate_id=null`로 반환한다.
- `main.py`에 `WritingReviseRequest`, 주입/default revise service, `POST /projects/{id}/writing/revise`를 추가했다. ContextPackage는 서버가 재구성하며 저장·Gate·report·accept·Analysis는 자동 호출하지 않는다.
- `tests/test_writing_revise.py`를 추가해 prefix/suffix 보존, stale report reset, missing/duplicate anchor, non-continuity/non-revise, empty/unchanged, project isolation, prompt 책임 문구, HTTP server context/query/current_position, 400/404/502/503/504를 양방향으로 잠갔다.

### Issues found

- D8의 “502와 200+상태”는 한 응답에서 동시에 표현할 수 없다. 첫 slice A=502로 성공 위장을 막고, 후속 C=`200 changed=false revision_status=...`로 transport 실패와 분리하는 순차 migration으로 확정했다.
- revised text에 원 report를 보존하면 advisory가 stale해진다. report를 비우고 기존 `/writing/report`로 재평가하는 파생 안전선을 적용했다.

### Verification

- focused: `tests/test_writing_revise.py` + writing/gate/report/accept → **80 passed / 62 subtests**.
- remote live: `192.168.1.22:9080`에서 replacement=`그녀는 성문 앞에 서 있었다.`를 반환했고 Application splice 결과가 prefix/suffix를 그대로 보존, `status=ok`.
- full: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **892 passed / 45 skipped / 163 subtests**.
- `python3 -m py_compile`(main/revise/test)·`git diff --check` 통과.

### Next steps

- D5 B 자동 Gate 1회 합성 또는 D1 후속 retrieve_more를 별도 착수 브리프로 결정한다.
- D4 C multi-finding은 작은 replacement 호출의 실제 비용/latency를 측정한 뒤 structured mapping 계약을 연다.
- D5 C bounded pass loop 전에 사람 확인 대상과 자동 반복 허용 finding을 정책·fixture로 잠근다.

### 독립 검증 조건부 합격 closure + hardening

- 독립 검증 `docs/verifications/2026-07-13/writing_partial_revise.md`를 대조했다. splice/D8/live/SoT 원칙은 통과했으나 context budget 504/backend 502 HTTP 셀이 비어 있다는 B1 판정이 타당했다.
- **B1 closure**: `_Context`에 예외 주입을 추가해 `ContextSearchBudgetExceeded→504`, `ContextSearchFailed→502`를 revise endpoint에서 직접 잠갔다.
- **H1/H2**: 빈 instruction/request_id/candidate_text/evidence 4종을 `WritingRevisionService.validate_inputs`로 context search 전에 거부한다. context와 revise provider 호출이 모두 0임을 HTTP subtest로 단언했다.
- **H3**: `_NoWriteCoreSotService.save_draft` spy로 revise 200 동안 save 호출 0을 직접 잠갔다.
- **H4**: 명백한 Markdown triple-backtick fence만 Application이 결정적으로 unwrap한다. 정상 대화문 따옴표는 의미를 훼손할 수 있어 제거하지 않는다.
- validation 이동 patch가 처음 유사한 Gate endpoint에 오삽입됐으나 focused Gate 회귀가 즉시 잡았다. 오삽입을 제거하고 `validate_inputs` 호출이 revise endpoint에만 남음을 grep/회귀로 확인했다.
- closure focused: **84 passed / 68 subtests**. closure full: **896 passed / 45 skipped / 169 subtests**.

## Phase 5.7 partial revise → Gate 1회 합성 착수 브리프

### Goals

- v1.6.73 D5 로드맵의 다음 단계 B(자동 Gate 1회)를 구현하기 전에 public API와 partial-success 계약을 확정한다.

### Completed work

- clean commit `d8231cf` 이후 D5 B의 정본 범위와 accept partial-success 선례를 대조했다.
- `docs/plans/05-writing-revise-gate-decisions.md`를 작성해 API 경계, ContextPackage, report 위치, Gate 실패 envelope, non-pass, response shape, dependency/error, 반복 종료를 G1~G8로 분리했다.

### Issues found

- 기존 `/writing/revise`를 변경하면 v1.6.73의 flat candidate 응답·latency·dependency를 깨므로 additive endpoint 여부가 필요하다.
- revised candidate는 비영속이라 Gate 실패 시 오류만 반환하면 성공 artifact가 유실된다. 반대로 200 failed는 transport 실패를 성공처럼 보일 수 있어 partial-success status/envelope 결정이 필요하다.
- revised report는 비어 있어 report 재추출을 합성하면 LLM 3회와 새 partial 단계가 생긴다.

### Decisions

- 작업자 추천은 별도 `/writing/revise-and-gate`, 동일 package, report 없이 Gate, Gate 실패 502/504 partial candidate, non-pass 200, `{candidate,gate}` 중첩, revise/Gate 각 1회다.
- G1~G8은 owner-level public contract이므로 승인 전 production code를 시작하지 않는다.

### Next steps

- 오너가 G1~G8을 확정하면 SoT 반영→boundary tests→합성 service/API→전체 회귀→원격 LLM 2-turn live 순서로 진행한다.

## Phase 5.7 partial revise → Gate 1회 합성 구현 (SoT v1.6.74)

### Goals

- 승인된 G1~G8에 따라 기존 `/writing/revise`를 보존하면서 revise 성공 artifact를 잃지 않는 Gate 1회 합성 API를 구현한다.

### Completed work

- 오너 결정: G1=A, G2=A, G3=A first→B, G4=A, G5=A, G6=A, G7=A, G8=A first→B. 중간 수정 후 retrieve_more일 때만 재검색/메모리 재접근을 후속 설계한다.
- `writing/revise_gate.py`에 `WritingReviseGateService`, result, `WritingReviseGateFailure(candidate,cause)`를 추가했다. 동일 ContextPackage 객체로 reviser 1회→Gate 1회를 실행한다.
- `POST /projects/{id}/writing/revise-and-gate`를 추가했다. 성공은 `{candidate,gate}`, Gate decision 5종(pass + non-pass 4종) 모두 200이다.
- revise 성공 뒤 Gate 실패는 `{candidate,gate:null,gate_error:{type,detail}}`로 비영속 revised artifact를 보존한다. 입력/설정 검증은 400, provider·invalid 결과·예기치 않은 평가 실패는 502, timeout은 504다. revise/context 실패는 candidate가 없으므로 기존 400/502/504를 유지하고 Gate를 호출하지 않는다.
- report 재추출·두 번째 revise·save/accept/Analysis는 호출하지 않는다. revised candidate의 빈 report가 Gate에 전달된다.
- HTTP 회귀로 동일 package identity, revise/Gate 각 1회, 다섯 decision 200, Gate timeout/unavailable/invalid partial envelope, revise 실패 Gate 미호출, missing dependencies 503, context 504/502, no-save를 잠갔다.

### Issues found

- G4는 D8 unchanged와 다르다. D8은 revised candidate가 없고, G4는 candidate 생성 후 Gate만 실패하므로 partial artifact envelope가 필요하다.
- 원격 실모델 2-turn에서 revise는 성공했으나 Gate가 invalid/empty JSON을 반환했다. 합성 service가 `WritingReviseGateFailure`로 revised candidate를 보존해 `partial_ok`를 확인했다. Gate JSON 품질/repair는 v1.6.69 Gate 자체의 별도 후속이며 이번 합성은 실패를 숨기지 않는다.

### Verification

- focused: writing revise/gate/generate/report/accept → **91 passed / 78 subtests**.
- remote live: revise 성공 후 Gate `InvalidWritingGateResult`; partial candidate text 보존, `status=partial_ok`.
- full: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **903 passed / 45 skipped / 179 subtests**.
- `python3 -m py_compile`(main/revise_gate/test)·`git diff --check` 통과.

### Next steps

- G3 B(report 최신화 후 Gate)의 latency/partial 단계 계약을 별도 브리프로 연다.
- G8 B 내부 loop 전에 자동 반복 decision/finding, 사람 확인, budget, retrieve_more 재검색 lifecycle을 잠근다.

### 독립 검증 조건부 합격 closure + hardening

- 독립 검증 `docs/verifications/2026-07-13/writing_revise_gate.md`를 정본·코드·테스트와 대조했다. 합성 계약과 실모델 partial candidate 보존은 통과했으나, composition endpoint 자체의 revise validation 400과 revise provider timeout 504가 전용 회귀 없이 비어 있다는 B1 판정이 타당했다.
- **B1 closure**: duplicate evidence를 제출하면 context/revise/Gate 호출 전 400이고, 정상 unique evidence는 같은 fixture에서 200으로 관통하도록 under/over-strict 양방향을 잠갔다. revise provider timeout은 context/reviser까지만 호출하고 Gate 호출 0인 채 504임을 별도 테스트로 잠갔다.
- **H1**: Gate의 `WritingGateError→400 writing_gate_error`와 예상 밖 평가 예외 `→502 gate_error`도 실제 partial candidate envelope를 보존하는지 기존 table test에 추가했다. 전자는 템플릿 부재 같은 Gate 설정 실패에서도 도달 가능하므로 방어 분기로만 남기지 않았다.
- **H2**: G4 문구를 기존 동작 및 전체 taxonomy와 맞춰 보정했다. Gate 입력/설정 검증은 400, provider·invalid result·예기치 않은 평가 실패는 502, provider timeout은 504이며 모두 revised candidate를 포함한다. production 동작 변경은 없다.

### Verification

- focused: writing revise/gate/generate/report/accept → **93 passed / 80 subtests**.
- full: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **905 passed / 45 skipped / 181 subtests**.
- `python3 -m py_compile`(main/revise_gate/test)·`git diff --check` 통과.

## Phase 5.7 G3 B revise → report → Gate 착수 브리프

### Goals

- HANDOFF 우선순위에 따라 G3 B를 retrieve_more·G8 내부 loop보다 먼저 열고, LLM 3단계 및 report 실패 partial envelope 계약을 구현 전에 확정한다.

### Completed work

- SoT v1.6.71~74, 기존 revise→Gate 브리프, `/writing/report`, `WritingCandidateReportService`, Gate 실패 partial envelope 선례를 대조했다.
- `docs/plans/05-writing-revise-report-gate-decisions.md`를 작성해 endpoint 전환, ContextPackage lifecycle, report 실패 envelope/taxonomy, 성공 shape, dependency/호출 수를 R1~R6으로 분리했다.
- HANDOFF의 owner decision과 Next Tasks를 G3 B 브리프 대기 상태로 갱신했다.

### Issues found

- G3는 A first→B 목표만 승인됐고, 기존 endpoint를 승격할지 새 endpoint/flag로 열지는 확정되지 않았다.
- revise 성공 뒤 report가 실패하면 비영속 revised candidate가 이미 존재한다. 오류만 반환하면 artifact가 유실되고, 빈 report로 Gate를 계속 실행하면 G3 B가 조용히 종전 G3 A로 퇴행한다.
- report service는 논리 단계 1회 안에서 invalid JSON repair를 최대 1회 수행하므로, “LLM 3단계”와 실제 provider 최대 호출 수를 구분해야 한다.

### Decisions

- 사용자 방향: 다음 Writing 작업은 G3 부채를 우선한다. retrieve_more, G8 loop, persisted 감사 이력과 이후 확장은 그 뒤 후보로 둔다.
- 작업자 추천: R1~R6 모두 A. 기존 합성 endpoint를 같은 ContextPackage의 revise→report→Gate로 승격하고, report 실패는 502/504 + revised candidate + `report_error`, `gate=null`로 보존한다. Gate는 report 성공 뒤에만 호출한다.
- R1~R6은 owner-level public contract이므로 오너 승인 전 production code는 변경하지 않는다.

### Next steps

- 오너가 R1~R6을 확정하면 SoT 반영→boundary tests 우선→최소 합성 service/API 변경→focused/full 비-LLM 회귀→원격 3단계 live smoke 순서로 구현한다.

## Phase 5.7 G3 B revise → report → Gate 구현 (SoT v1.6.75)

### Goals

- 승인된 R1~R6에 따라 기존 합성 endpoint를 동일 ContextPackage의 revise→report 최신화→Gate 순서로 승격한다.
- report 실패 때 비영속 revised candidate를 보존하고 Gate를 호출하지 않는 양방향 회귀를 먼저 잠근다.

### Completed work

- 사용자 결정: R1/R2/R3/R4/R6=A. R5는 다회 합성 확장성을 원했으며, 현재 `{candidate,gate}`에 `stages`를 additive로 붙이는 비용이 작다는 확인에 따라 **A first→C later**로 확정했다. 다회 합성을 실제로 열 때 stage item/status/attempt/usage schema와 loop budget을 함께 결정한다.
- `WritingReviseGateService`에 `CandidateReporter`와 `WritingReviseReportFailure`를 추가했다. Application이 revise→report enrich→Gate를 순서대로 실행하며 세 단계가 같은 ContextPackage 객체를 사용한다.
- report 성공 candidate만 Gate에 전달하고 응답에도 반환한다. report 실패는 `{candidate,gate:null,report_error:{type,detail}}`로 revised candidate를 보존하며 Gate를 호출하지 않는다.
- report error는 provider timeout 504, provider unavailable/invalid report/예상 밖 실패 502로 구분한다. reporter가 없으면 합성 service 자체가 구성되지 않아 503이며 context/revise/Gate 호출은 0이다.
- 성공 envelope는 기존 `{candidate,gate}`를 유지했다. save/accept/Analysis/재검색/두 번째 revise와 `stages`는 추가하지 않았다.
- 브리프를 Resolved로 전환하고 SoT v1.6.75, Phase 5 계획, CHANGELOG, HANDOFF를 현재 동작으로 갱신했다.

### Issues found

- R5 C를 지금 구현하려면 단순 배열 추가가 아니라 stage item의 안정 literal(status, error, attempt, model/usage)을 새 public contract로 결정해야 했다. 반면 일반 JSON object에 `stages`를 나중에 additive로 붙이는 구현 비용은 작다.
- “report 1회”는 합성 단계 1회를 뜻하지만 strict parser가 invalid JSON을 받으면 기존 report service 내부에서 provider repair를 최대 1회 더 호출한다. 합성 service는 별도 retry를 추가하지 않았다.

### Decisions

- 사용자 결정과 이유: 다회 합성 가능성을 닫지 않는다. 현재 additive 확장 비용이 작으므로 R5=A first→C를 채택해 G3에 불필요한 stage schema를 선행 도입하지 않는다.
- report 실패 뒤 빈 report로 Gate를 계속 실행하지 않는다. 이는 G3 B가 종전 G3 A로 조용히 퇴행하는 것을 막는다.
- retrieve_more의 package 교체와 DB·메모리 재접근은 이번 동일-package 계약에 섞지 않고 다음 전용 브리프로 남긴다.

### Verification

- red-first: 새 합성 회귀가 종전 2단계 구현에서 reporter 0회, missing reporter 200, report failure 200으로 실패함을 확인했다.
- focused: `python3 -m pytest -q -p no:cacheprovider tests/test_writing_revise.py tests/test_writing_report.py tests/test_writing.py tests/test_writing_gate.py tests/test_writing_accept.py` → **94 passed / 84 subtests**.
- full: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **906 passed / 45 skipped / 185 subtests**.
- `python3 -m py_compile services/application/app/main.py services/application/app/writing/revise_gate.py tests/test_writing_revise.py` 통과.
- pattern sweep: `WritingReviseGateService`, `revise-and-gate`, 빈 `candidate_claims` 전달 패턴을 repo-wide grep하고 관련 기존 라인에 `git blame`을 확인했다. 추가로 report를 건너뛰는 합성 경로는 없었다.

### Next steps

- 다음 우선 후보는 `retrieve_more`의 query/needs, ContextPackage 교체, DB·메모리 재접근 lifecycle 결정 브리프다.
- 그 뒤 G8 B 내부 loop의 자동 반복 decision/finding, 사람 확인 조건, 전체 호출/token/time budget을 결정한다.
- persisted candidate/revision/report/GateRun identity와 `stages` 감사 envelope는 loop/persistence 경계가 실제로 열릴 때 함께 정한다.

### 독립 검증 B1 closure + H1 문구 보정

- 독립 검증 `docs/verifications/2026-07-13/writing_revise_report_gate.md`의 조건부 합격을 대조했다. 구현은 Gate 실패에서 enriched candidate를 보존하지만, 전용 partial envelope 테스트가 text와 taxonomy만 검사해 최신 report 보존 회귀를 잡지 못한다는 B1 판정이 타당했다.
- **B1 closure**: `test_gate_failure_returns_partial_candidate`가 모든 Gate 실패 taxonomy case에서 `candidate_claims[0].text == "fresh"`를 직접 단언한다. report 실패의 `candidate_claims == []` assertion과 대칭이며, `WritingReviseGateFailure(enriched, exc)`를 `revised`로 퇴행시키면 실패한다.
- 동일 `enriched→revised` mutation을 재주입해 전용 테스트가 5개 taxonomy subtest 모두 `IndexError`로 실패하는 것을 확인한 뒤 즉시 원복했다. 정상 구현 재실행은 통과했다.
- **H1**: `WritingGateDecision`은 전체 5종이고 non-pass는 4종이다. SoT v1.6.74/75, G3 B 브리프, CHANGELOG, 작업 로그의 “non-pass 5종” 오기를 “Gate decision 5종(pass + non-pass 4종)”으로 정정했다. 동작·public literal은 변경하지 않았다.
- H2(report repair/합성 retry)와 H3(accept/Analysis side-effect)는 검증 기록대로 현재 전용 report service 회귀와 합성 service 구조/no-save 회귀가 충분하므로 추가 코드를 만들지 않았다.
- closure focused: **94 passed / 84 subtests**. closure full: **906 passed / 45 skipped / 185 subtests**. `py_compile`·`git diff --check` 통과.

## Phase 5.8 `retrieve_more` 1회 lifecycle 착수 브리프

### Goals

- HANDOFF의 다음 순차 작업인 `retrieve_more`를 구현하기 전에 query/needs, ContextPackage 교체, report·Gate 재실행과 반복 종료의 public contract를 확정 가능한 결정 단위로 나눈다.

### Completed work

- 정본 우선순위가 `docs/system-contract-sot.md` → Approved/구현으로 잠긴 Phase 계획 → 미구현 계획 순으로 이미 정의돼 있음을 확인했다.
- SoT v1.6.69/v1.6.73~75, Writing Gate·partial revise·revise→report→Gate 브리프, Phase 4 `ContextSearchRequest`/`ContextNeed`, 현재 endpoint와 합성 service를 대조했다.
- `docs/plans/05-writing-retrieve-more-decisions.md`를 작성해 public API, trigger 입력, query 소유권, need 집합, package lifecycle, 재검색 뒤 순서, envelope, 반복/identity를 T1~T8로 분리했다.
- 모든 현실적인 선택지와 장단점을 남기고 T1~T8=A를 추천했다. 오너 결정 전 production code와 SoT 버전은 변경하지 않았다.
- `HANDOFF.md`의 Owner Decisions Needed와 Next Tasks를 Phase 5.8 결정 대기 상태로 갱신했다.

### Issues found

- 문제: Gate finding은 candidate exact evidence와 `retrieve_more` recommendation만 제공하며 검색 query/need를 제공하지 않는다. 기존 continue-scene 검색은 `current_scene|recent_scenes|canonical_memory`라 같은 요청을 반복해도 검색 범위가 실제로 넓어지지 않을 수 있다.
- 원인: v1.6.69는 side-effect-free 판정만, v1.6.75는 동일-package revise→report→Gate까지만 잠갔고 retrieval lifecycle은 의도적으로 후속으로 남겼다.
- 해결/결과: 임의 구현을 중단하고 결정 브리프로 전환했다. 추천안은 새 Gate schema 없이 instruction+finding message+evidence의 결정적 query fallback과 `event_context|source_quote`를 더한 canonical 확장 needs로 fresh package를 만든다.
- 충돌 점검: scoped 정본 안에서 자기모순은 발견하지 않았다. 다만 “재검색한다”는 목표만 있고 public contract가 비어 있어 오너 결정 없이는 구현할 수 없다.

### Decisions

- 작업자 추천: 별도 `/writing/retrieve-and-gate`가 candidate+단일 retrieve finding을 받아 fresh ContextPackage를 한 번 만들고, 새 package에서 report→Gate를 한 번 실행한다(T1~T8=A).
- 추천안은 candidate memory를 canonical 근거 부족 해소 수단에서 제외하고, candidate text 수정·두 번째 검색·자동 revise·save/accept/Analysis·persistence를 이번 slice 밖에 둔다.
- 이번 기록은 추천이며 사용자 결정이 아니다. 승인 전 계약 literal이나 SoT를 확정 상태로 올리지 않는다.

### Verification

- 문서 참조 확인: 브리프가 인용한 `05-writing-gate-decisions.md`, `05-writing-revise-report-gate-decisions.md`, SoT v1.6.69/v1.6.75, Phase 4 `ContextSearchRequest`/`ContextNeed`가 모두 존재하고 기술한 현재 literal과 일치함을 grep/원문 대조했다.
- production code 무변. `git diff --check`로 문서 diff와 Markdown whitespace 이상이 없음을 확인했다.

### Next steps

- 오너가 `05-writing-retrieve-more-decisions.md` T1~T8을 확정하면 결정을 SoT/브리프/작업 로그에 반영한다.
- 승인 후 boundary tests red-first → 최소 search→report→Gate service/API → focused/full 비-LLM 회귀 → 필요 시 live retrieval/Gate smoke 순서로 진행한다.
- 그 뒤 G8 B의 자동 반복 decision/finding, 사람 확인 조건과 전체 search/provider/token/time budget을 별도 브리프로 연다.

## Phase 5.8 targeted `retrieve_more` 구현 (SoT v1.6.76)

### Goals

- 필요한 needs만 내부 LLM이 선택해 재조회하고, 이전 ContextPackage와 이어지는 targeted retrieval을 최대 한 번 실행한다.
- candidate/report를 불필요하게 다시 만들지 않으면서 merged grounding으로 Writing Gate를 재평가한다.

### Completed work

- 사용자 결정에 따라 브리프를 T1=B, T2=B, T3/T4=E, T5/T6=B, T7/T8=A first→B로 확정하고 SoT를 v1.6.76으로 올렸다.
- `writing/retrieval.py`에 strict terminal-JSON follow-up retrieval planner를 추가했다. 첫 Gate의 모든 retrieve_more finding, candidate, instruction과 현재 사용 가능한 canonical need allowlist를 입력으로 `query+needs`를 선택하며 malformed/out-of-set 결과는 1회 repair한다.
- 현재 position이 없으면 `current_scene|recent_scenes`를 planner allowlist에서 제외한다. `candidate_memory`, 빈/중복/미지원 needs와 빈 query는 검색 전에 거부한다.
- `merge_context_packages`가 targeted delta를 먼저 배치하고 pointer `(collection,document_id,version_id,content_hash)`로 dedup한 뒤 전체 max_tokens budget을 다시 적용한다. 기존 package가 예산을 모두 점유해 새 근거를 굶기는 문제를 막는다.
- `WritingReviseGateService`가 revise→report→첫 Gate 뒤 retrieve_more일 때만 planner→targeted context search→merge→두 번째 Gate를 실행한다. report는 candidate text가 변하지 않으므로 재호출하지 않고 최신 report 필드를 그대로 보존한다.
- `max_retrieval_rounds=1`을 강제했다. 두 번째 Gate도 retrieve_more면 200 정상 outcome으로 종료하며 추가 planner/search/Gate는 없다.
- endpoint 성공 `{candidate,gate}`는 최종 Gate로 유지했다. 첫 Gate 뒤 planner/context 실패는 `{candidate,gate:<첫 Gate>,retrieval_error}` 400/502/503/504 partial envelope로 candidate와 판정 artifact를 보존한다.
- 신규 `tests/test_writing_retrieval.py`와 확장 `tests/test_writing_revise.py`가 planner/repair/allowlist, merge 양방향, no-rereport, 1회 상한, partial taxonomy와 두 번째 Gate failure를 잠근다.

### Issues found

- 문제: 기존 Phase 4 LLM planner는 전달받은 needs 안에서 step/query/tool을 계획할 뿐 needs 자체를 선택하지 않는다.
- 원인: ContextSearchRequest의 needs가 planner 호출 전에 이미 확정되는 계약이다.
- 해결/결과: Writing Gate schema를 확장하지 않고 그 앞에 follow-up retrieval planner를 두었다. 두 planner는 각각 “무엇을 찾을지”와 “선택된 need를 어떤 tool/step으로 찾을지”를 소유한다.
- 문제: T5=B merge는 이전 package가 필요하지만 ContextPackage는 비영속이고 public response에도 없다.
- 해결/결과: 독립 endpoint(T1=A) 추천을 폐기하고 기존 합성 호출 내부(T1=B)에서 첫 Gate 직후 이어가도록 했다.
- 문제: 전체 budget을 base-first로 재적용하면 이미 찬 package 때문에 targeted delta가 모두 탈락할 수 있다.
- 해결/결과: delta-first+pointer dedup으로 새 근거를 우선하고 남는 예산에 이전 context를 유지한다.

### Decisions

- 사용자 결정과 이유: 로컬 LLM 재호출 비용은 감당 가능하지만 부분적으로 충분한 package에서 고정 3종/5종을 전부 재실행하는 낭비는 피한다. 별도 LLM이 필요한 needs를 내부 판단한다.
- 사용자 결정: 이전 결과와 이어지는 package merge(T5=B), candidate/report 유지 후 Gate만 재평가(T6=B), 성공 envelope A first→후속 stages(B), retrieval 상한 1 first→후속 다회(B)를 채택한다.
- 파생 결정: 새 LLM은 판정 authority가 아니므로 Writing Gate가 아닌 `follow-up retrieval planner`로 명명한다. 기존 Phase 4 planner와 책임이 겹치지 않는다.
- tradeoff: report prompt도 ContextPackage를 입력받으므로 context-relative report가 달라질 수 있으나, candidate text는 불변이고 최종 Gate가 merged package를 직접 보므로 이번 slice는 report 재호출 비용을 생략한다.

### Verification

- red-first: 신규 테스트는 `services.application.app.writing.retrieval` 부재로 collection error가 발생해 구현 전 실패를 확인했다.
- lifecycle focused: `tests/test_writing_retrieval.py tests/test_writing_revise.py` → **34 passed / 39 subtests**.
- Writing focused: retrieval/revise/report/generate/gate/accept → **105 passed / 93 subtests**.
- full: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **917 passed / 45 skipped / 194 subtests**.
- `python3 -m py_compile`(main/retrieval/revise_gate/tests)·`git diff --check` 통과.
- pattern sweep: `RETRIEVE_MORE|retrieve_more|max_retrieval|merge_context_packages|build_context_package`를 repo-wide grep하고 기존 합성 service/endpoint 라인에 `git blame`을 확인했다. 자동 retrieve_more를 중복 실행하는 다른 Writing 경로는 없었다.

### Next steps

- G8 B에서 `max_retrieval_rounds>1` 또는 retrieve→revise 자동 분기를 열기 전에 사람 확인 decision/finding, 반복별 report 정책과 전체 search/provider/token/time budget을 결정한다.
- 성공 단계 관측성이 필요해지면 R5/T7의 `stages` additive schema를 persisted candidate/GateRun identity와 함께 연다.
- 실 LLM smoke에서는 planner가 fixture별 최소 needs를 고르는지와 merged package가 Gate 결정을 바꾸는지 관찰한다. wiring은 fake 회귀로 완결됐으며 production 품질 채택은 live 라벨과 분리한다.

## Phase 5.8 독립 검증 B2 closure + H1~H3 hardening

### Goals

- `docs/verifications/2026-07-13/writing_retrieve_more.md`의 조건부 합격 사유 B2를 정본과 코드가 같은 경계를 말하도록 폐쇄한다.
- 비차단 H1~H3 중 작은 전용 회귀로 직접 잠글 수 있는 retrieval taxonomy, no-save, identity/candidate_id를 보강한다.

### Completed work

- 검증 기록을 전수 읽고 9행 boundary matrix, 코드, 테스트와 대조했다. B2의 `current_position` 부재 시 `MACRO_NEEDS` 제외가 코드·테스트에는 있으나 브리프/SoT에는 없는 spec-silent gap이라는 판정이 타당했다.
- `05-writing-retrieve-more-decisions.md`의 Owner T3/T4, T4 채택문, boundary 3과 SoT v1.6.76에 “`current_position` 부재 시 `current_scene|recent_scenes` 제외”를 명시했다. CHANGELOG에도 같은 position 조건을 반영했다.
- H1: endpoint retrieval taxonomy에서 빠졌던 `provider_unavailable`(502), `invalid_retrieval_plan`(502), `retrieval_planner_error`(503), `invalid_context_request`(400)를 기존 partial table test에 추가했다. 기존 5종과 함께 candidate+첫 Gate 보존을 직접 검사한다.
- H2: 실제 retrieve_more 성공 경로에 `_NoWriteCoreSotService`를 주입해 두 번째 Gate까지 완료돼도 `save_draft` 호출이 0임을 단언했다.
- H3: 같은 성공 경로 응답에서 `request_id` 유지, `project_id` 유지, `candidate_id is None`을 직접 단언했다.
- production code는 변경하지 않았다. 검증 기록 자체는 독립 감사 원문으로 보존하고 HANDOFF에 closure 및 독립 재판정 대기를 기록했다.

### Issues found

- 문제: T4/경계 3이 canonical 5종을 position 조건 없이 서술해, position 없을 때 3종으로 좁히는 코드가 정본보다 엄격했다.
- 원인: 구현 시 Phase 4 `ContextSearchService._validate_request`의 position-required 계약을 planner 앞에서 선제 적용했지만 브리프와 SoT에는 파생 조건을 옮기지 않았다.
- 해결/결과: 합리적인 코드 동작을 완화하지 않고 정본에 조건을 명시했다. repo-wide pattern sweep에서 `MACRO_NEEDS`는 Phase 4가 동일하게 `current_position is None`을 거부하므로 기존 상위 계약과 일치한다.

### Decisions

- 사용자 요청: 독립 검증 기록의 보강 필요 항목을 확인해 반영한다.
- 파생 결정: B2 선택지 중 코드 완화가 아니라 정본 보충을 채택한다. position 없는 current/recent는 Phase 4에서 실행 불가능하므로 5종 항상 허용은 downstream 400을 늦출 뿐이다.
- H1~H3은 public literal과 side-effect/identity boundary를 직접 잠그는 저비용 회귀라 함께 보강한다. 새 기능이나 error taxonomy는 추가하지 않는다.

### Verification

- lifecycle focused: `tests/test_writing_retrieval.py tests/test_writing_revise.py` → **34 passed / 43 subtests**.
- Writing focused(6파일): **105 passed / 97 subtests**.
- full: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **917 passed / 45 skipped / 198 subtests**.
- `python3 -m py_compile`(main/retrieval/revise_gate/tests)·`git diff --check` 통과.
- pattern sweep: `current_position is None|is not None|MACRO_NEEDS`를 repo-wide grep했다. Phase 4 request validation이 같은 position dependency를 이미 강제하며, 다른 spec-silent Writing allowlist는 발견하지 못했다.

### Next steps

- 독립 verifier가 B2 closure를 재판정하면 `writing_retrieve_more.md` verdict를 조건부 합격에서 합격으로 승격할 수 있다.
- v1.6.76 구현+closure는 `51f2723 feat: add targeted writing retrieval loop`로 커밋했다.

## Phase 5.9 G8 bounded loop 착수 결정 브리프

### Goals

- targeted retrieval 다음 단계인 G8 내부 loop의 자동 decision/finding, 사람 확인, report/package 갱신과 종료 예산을 구현 전에 확정 가능한 선택지로 분리한다.
- 현재 계측 가능한 구조적 반복 상한과 아직 강제 불가능한 aggregate token/time budget을 혼동하지 않는다.

### Completed work

- G8/D4/D5/D7/D8, R5, T7/T8과 generic flat-loop budget 선례를 scoped 정본으로 대조했다.
- `docs/plans/05-writing-bounded-loop-decisions.md`를 작성해 public 경계, 자동 자격, 상태 전이, 구조적 상한, budget 도입 순서, stages/종료 literal, unchanged/partial error, identity/persistence를 L1~L9로 분리했다.
- 추천안은 기존 endpoint에서 single continuity finding auto-revise 1회와 targeted retrieval 1회를 순서와 무관하게 허용하고, 총 revision 2·retrieval 1·Gate 3으로 종료한다. 사람 decision과 multi-finding은 자동화하지 않는다.
- HANDOFF Owner Decisions Needed와 Next Tasks를 오너 결정 대기 상태로 갱신했다. production code와 SoT는 변경하지 않았다.

### Issues found

- 문제: 기존 generic AgentLoop는 5차원 budget 모델을 갖지만 Writing domain service 결과가 provider token usage를 전달하지 않아 aggregate token budget을 실제로 집계할 수 없다.
- 원인: 현재 Writing slice는 component별 1-turn 호출/repair와 Application의 retrieval round만 소유하며, domain result에 usage/latency를 승격하지 않았다.
- 해결/결과: 근거 없는 token/time 숫자를 박거나 generic runner를 억지로 재사용하지 않고, 실제 강제 가능한 call cap을 B1로 제안했다. usage plumbing·live 계측·aggregate 기본값은 명시적 B2 후속 선택지로 남겼다.
- scoped 정본 안에서 `needs_user_review|block` 사람 경계와 candidate 변경 뒤 report refresh는 일치한다. 다만 unchanged를 loop 정상 종료로 볼지 현행 502를 유지할지는 계약 fork라 L8에 노출했다.

### Decisions

- 작업자 추천이며 아직 사용자 결정이 아니다: L1~L9=A.
- 추천 이유: 로컬 호출 비용이 낮아도 partial pass에서 전체 단계를 재실행할 이유는 없고, 현재 single-finding/exact-anchor 안전 경계를 보존한 최소 loop가 먼저다.
- aggregate token/time은 폐기하지 않는다. 관측값과 usage contract가 생긴 뒤 B2에서 운영 기본값을 확정한다.

### Verification

- 브리프가 인용한 G8/D4/D5/D7/D8/R5/T7/T8와 `flat-loop-gate.md` budget 차원을 원문 대조했다.
- documentation-only 변경이며 production code/정본 version 무변이다. `git diff --check`와 참조 파일 존재 여부를 확인한다.

### Next steps

- 오너가 L1~L9를 확정하면 결정을 work log와 SoT에 반영한다.
- 승인 후 boundary tests red-first → 최소 state machine/response model → focused/full 비-LLM 회귀 순서로 구현한다.
- L5=B를 선택하면 loop 구현 전에 provider usage plumbing과 aggregate 기본값을 별도 수치 결정으로 먼저 잠가야 한다.

## Phase 5.9 G8 bounded revise/retrieve loop 구현 (SoT v1.6.77)

### Goals

- 단일 continuity finding auto-revise와 targeted retrieval을 부분 pass 결과에서 필요한 만큼만 이어가되 설정 가능한 구조적 상한 안에서 결정적으로 종료한다.
- 최초/standalone unchanged 오류와 자동 loop의 정상 no-change를 타입과 public literal로 구분하고, 각 단계의 최소 관측/partial artifact를 보존한다.

### Completed work

- 사용자 L1~L9 결정을 브리프와 SoT v1.6.77에 반영했다. L4 기본값은 총 revision 2·retrieval 1·Gate 3이며 `WritingLoopPolicy`, `WRITING_LOOP_MAX_REVISION_ROUNDS`, `WRITING_LOOP_MAX_RETRIEVAL_ROUNDS`, `WRITING_LOOP_MAX_GATE_EVALUATIONS`로 조정 가능하다. Compose application 환경에도 세 설정을 노출했다.
- `WritingReviseGateService`를 bounded state machine으로 승격했다. `pass`는 성공, `needs_user_review|block`은 사람 terminal, 자격 밖 revise는 `not_eligible`, 잔여 action/Gate 상한 부족은 `budget_exhausted`로 호출 전에 종료한다.
- 자동 revise 자격을 Gate finding 정확히 1개, continuity, recommended revise, candidate exact evidence 1회로 제한했다. revise 뒤 현재 merged package로 report→Gate를 수행하고, retrieval 뒤 candidate/report를 유지한 채 targeted delta merge→Gate만 수행한다.
- 성공/정상 종료에 `loop:{status,revision_rounds,retrieval_rounds,gate_evaluations}`와 최소 `stages[{stage,ordinal,status}]`를 additive 공개했다. 단계는 `revise|report|gate|retrieve_plan|context_search|merge`, 상태는 `completed|failed|no_change`다.
- `UnchangedWritingRevision`을 `InvalidWritingRevision`의 명시적 하위 타입으로 추가했다. 최초 합성/standalone은 기존 502를 유지하고 자동 후속 revise만 200 `loop.status=no_change`로 소비한다.
- initial/auto revision, report, retrieval, Gate 실패는 마지막 완전한 candidate와 이전 Gate(있으면), `loop.status=failed`, 실패 stage를 partial envelope에 보존한다. auto revision에는 `revision_error` taxonomy를 추가했다.
- L6=A first→C, L9=A first→B에 따라 전체 중간 candidate/report/context payload와 persistence는 추가하지 않았다. save/accept/Analysis side effect도 열지 않았다.

### Issues found

- 문제: v1.6.76의 `max_retrieval_rounds`는 생성자에서 0/1만 받는 코드 literal이라 관측 뒤 운영값을 바꿀 수 없었다.
- 원인: targeted retrieval 1회 slice가 일반 G8 policy보다 먼저 구현돼 의도적으로 상한을 고정했다.
- 해결/결과: revision/retrieval/Gate 상한을 하나의 validated policy로 승격하고 env/Compose까지 배선했다. 기본 동작은 retrieval 1회를 유지하지만 설정이 실제 상태 전이를 바꾼다는 양방향 회귀를 추가했다.
- 문제: 기존 `InvalidWritingRevision("replacement did not change...")` 문자열만으로는 standalone 502와 auto-loop 정상 `no_change`를 안전하게 구분할 수 없었다.
- 해결/결과: 전용 하위 타입을 사용해 메시지 문자열에 의존하지 않는다. 빈 replacement 등 다른 invalid 결과는 여전히 502다.
- pattern sweep: `max_retrieval_rounds=1|max_retrieval_rounds not in|replacement did not change|InvalidWritingRevision`을 repo-wide 확인했다. 이전 T8 문구는 “G8 결정 전 기본 1”이라는 역사적 경계이며 v1.6.77 후속 채택문으로 명시 승계했다. 동일한 문자열 분기나 고정 production 상한은 남지 않았다.
- `git blame` 확인: 고정 retrieval 0/1 제한은 v1.6.76 targeted slice에서 의도적으로 도입됐고, unchanged 502는 v1.6.73 최초 partial revise 계약이었다. 둘 다 이번 사용자 결정의 순차 확장 대상과 일치했다.

### Decisions

- 사용자 결정: **L1~L9 추천 A를 기본 채택**한다.
- 사용자 결정: L4 기본 A 상한은 관측 뒤 설정에서 관리할 수 있도록 변수화한다. 호출 횟수 증가는 코드 변경 없이 policy/env 값으로 가능하다.
- 사용자 결정: L6은 최소 stages A first, 전체 artifact C는 필요 가능성을 보존한다. L9도 ephemeral A first, persisted loop 감사 B까지 확장 가능성을 보존한다.
- 사용자 결정: L8 auto no-change와 standalone 오류의 의미 차이는 명시적으로 구분해 혼동을 예방한다. 구현은 전용 exception type과 서로 다른 public envelope로 잠갔다.
- 파생 결정: stage/provider 실패는 정상 business outcome과 섞이지 않는 `loop.status=failed`를 사용한다. action count는 완료 횟수가 아니라 시작된 호출/round를 세어 실패/no-change도 budget 관측에 포함한다.

### Verification

- red-first: 신규 테스트는 `WritingLoopPolicy`가 없어 import collection error로 실패해 구현 전 경계를 확인했다.
- lifecycle focused: `tests/test_writing_revise.py tests/test_writing_retrieval.py` → **43 passed / 51 subtests**.
- Writing focused(6파일) → **115 passed / 108 subtests**.
- full: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **927 passed / 45 skipped / 209 subtests**.
- `python3 -m py_compile`(main/revise/revise_gate/tests), `docker compose config --quiet`, `git diff --check` 통과.
- 양방향 lock: 기본 상한은 revise↔retrieve 두 순서를 모두 pass까지 허용하고, 축소 policy/env는 action 전에 budget_exhausted로 멈춘다. exact 단일 continuity는 자동 수정되지만 0/다중/non-continuity/없는·중복 anchor는 provider 0회 `not_eligible`이다. auto unchanged는 200 no_change지만 standalone unchanged는 502다.

### Next steps

- aggregate token/time budget은 provider usage/latency/search 계측을 domain result에 전달한 뒤 실측값으로 별도 결정한다.
- L6 C/L9 B를 열 때 stage ordinal과 trigger finding fingerprint, candidate hash, ContextPackage pointer를 persisted loop 감사 모델에 연결한다.
- multi-finding과 non-continuity 자동 수정은 현재 자격 경계를 넓히지 않고 별도 정책/anchor drift 브리프로 다룬다.

## Phase 5.9 독립 PASS 후 H1/H2 hardening

### Goals

- `docs/verifications/2026-07-13/writing_bounded_loop.md`의 비차단 보강 후보를 원문·코드와 대조하고, 실제 계약 drift를 잡는 저비용 회귀를 추가한다.

### Completed work

- 독립 검증의 boundary matrix, literal 삼관교차, H1~H3와 Mongo 환경 관찰을 전수 확인했다. PASS 판정과 “slice 차단 없음”은 코드/테스트 상태와 일치했다.
- H1: 기존 policy validation test에 `WritingLoopPolicy()` 기본값이 정확히 `(max_revision_rounds=2,max_retrieval_rounds=1,max_gate_evaluations=3)`임을 단언했다. 상향/하향 drift를 모두 막되 비기본 `(3,2,5)` 설정 허용은 함께 보존한다.
- H2: 기본 policy에서 첫 Gate revise→두 번째 revise/report/Gate까지 허용한 뒤 다시 revise가 나와도 세 번째 reviser 호출 전에 200 `budget_exhausted`로 종료하는 endpoint 회귀를 추가했다. candidate/마지막 Gate와 round count 2/0/2, provider/reporter/Gate 각 2회를 직접 잠갔다.
- H3: `/writing/revise-and-gate`의 직접 `InvalidWritingRevision` catch는 현재 loop wrapping 아래에서는 도달하지 않지만, endpoint taxonomy 방어선이고 제거해도 동작 이득이 없다. production code는 유지했다.
- 독립 검증 기록 자체는 감사 원문이므로 수정하지 않았다.

### Issues found

- H1의 기존 pass-reaching 테스트는 기본 revision/gate 하한만 암시해 기본값이 3/2/5로 상향 drift해도 통과할 수 있었다. exact default assertion으로 폐쇄했다.
- H2의 configurable cap=1 테스트는 분기 구현을 증명하지만 기본 revision=2에서 action 직전 검사 순서를 직접 샘플링하지 않았다. 기본값 전용 실행 회귀로 폐쇄했다.
- 독립 검증에서 보고한 `test_memory_mongo.py` 4개 실패는 Writing 변경과 byte-independent인 부분 도달 Mongo index 환경 문제다. 프로젝트 관례의 non-Mongo 전체 명령을 유지하며 이번 slice에서 Mongo 코드/인프라는 변경하지 않았다.

### Decisions

- 사용자 요청에 따라 PASS 뒤에도 비차단 보강 후보를 검토해 H1/H2를 반영한다.
- H3는 dead-code 정리가 아니라 public 502 fallback 방어선으로 보고 유지한다. 인접 코드를 정리하기 위한 제거는 이번 요청 범위가 아니다.

### Verification

- lifecycle focused: `tests/test_writing_revise.py tests/test_writing_retrieval.py` → **45 passed / 54 subtests**.
- Writing focused(6파일) → **116 passed / 108 subtests**.
- full non-Mongo: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **928 passed / 45 skipped / 209 subtests**.
- 기본값/환경값/Compose 값의 `2|1|3`과 `WritingLoopPolicy` 사용처를 repo-wide 대조했다. `python3 -m py_compile`, `docker compose config --quiet`, `git diff --check` 통과.

### Next steps

- bounded-loop slice는 독립 PASS와 H1/H2 closure까지 완료됐다. 다음 Writing 후보 B2를 진행해도 되는 상태다.
- Mongo index 생성 실패는 Writing과 분리된 인프라 진단 과제로만 추적한다.

## Phase 5.9 L9 B persisted loop audit 착수 브리프 + 구현 (SoT v1.6.78)

### Goals

- HANDOFF 다음 작업 후보 중 오너 선택으로 **persisted loop 감사 API** 트랙을 착수한다.
- bounded loop(v1.6.77) L9=A first→B의 후속으로 loop 실행을 durable 감사 trail로 영속화한다.

### Completed work

- 착수 전 정본 스코프를 대조했다: SoT v1.6.77 로그, `05-writing-bounded-loop-decisions.md`(L6=A first→C·L9=A first→B·follow-up considerations line 129), 선례 `06-gate-finding-persistence-decisions.md`(v1.6.65 durable store 패턴). 현재 loop 표면(`revise_gate.py`의 5개 종료 경로가 `loop`+`stages`를 실어 나름)과 endpoint 직렬화를 매핑했다.
- persistence 모델·identity·트리거·읽기 API·lifecycle이 기존 계약에서 하나로 도출되지 않아 CLAUDE.md §1 Owner decision brief를 먼저 작성했다(`docs/plans/05-writing-persisted-loop-audit-decisions.md`): P1 입도, P2 트리거, P3 identity, P4 읽기 API, P5 lifecycle.
- 신설 `writing/audit_hash.py`(공유 fingerprint: `hash_text`·`finding_fingerprint`·`package_pointer_ids` — loop와 audit가 같은 규칙을 써 `final_candidate_hash==마지막 stage candidate_hash`가 성립하고 순환 import를 피함).
- `WritingLoopStage`에 per-stage 감사 필드(`candidate_hash`·`finding_fingerprint`·`pointer_ids`)를 default와 함께 additive로 추가했다. `record()`는 closure의 `current_candidate`를 읽어 stage별 hash를 자동 계산하고, revise stage엔 trigger finding, retrieval stage엔 package pointer를 실는다. ephemeral 응답(`_writing_stages_payload`)은 여전히 `{stage,ordinal,status}` 3키만 노출하고 감사 필드는 persisted trail만 읽는다.
- 신설 `writing/loop_audit.py`(`StoredLoopStage`·`StoredWritingLoopRun`·`WritingLoopAuditRepository` Protocol·`InMemory*`·`WritingLoopAuditService.record/list_runs/get`)와 `writing/loop_audit_mongo.py`(`writing_loop_audits` 컬렉션, insert-only append, project+created_at desc index).
- `main.py`: `_default_writing_loop_audit_service()`(Mongo URI 시 어댑터, 없으면 in-memory — 항상 가용해 P2=A), `create_app` 파라미터 배선, `/writing/revise-and-gate`의 5개 종료(성공+4 실패)에서 `_record_loop_audit()`로 감사 1건 기록 후 `audit_id` additive 응답, 읽기 endpoint 2종(`GET .../writing/loop-audits`, `GET .../writing/loop-audits/{audit_id}`).

### Decisions

- 오너가 추천 묶음 **P1=B, P2=A, P3=A, P4=A, P5=A**를 승인했다.
- **P3=A(append-only uuid)의 근거**: loop는 provider 샘플링으로 비결정적이라 같은 요청의 재시도는 다른 candidate/Gate/stages를 낳는 별개의 감사 사건이다. 선례(Gate finding)는 결정적 id였지만 그건 idempotent dedup 대상이었기 때문이고, loop에 결정적 id를 쓰면 두 번째 실행이 감사에서 사라진다.
- **오너 추가 지시(P5/P3)**: 오래된 run은 검증 보조자료로 쓰일 수 있으니 보존을 기본으로 둔다. append-only(P3)로 재시도까지 전부 남기고 immutable(P5)로 자동 삭제하지 않는다. **retention(TTL/archive)은 이 슬라이스에서 구현하지 않되 스키마가 막지 않도록 두고 명시된 운영과제로 남긴다** — P5 미룸은 "정리 로직 없음"이지 "run 폐기"가 아니다. 브리프에 이 결정을 기록했다.
- P1=B의 per-stage hash/pointer/fingerprint는 loop 내부 상태에서만 얻을 수 있어 `WritingLoopStage`를 enrich하는 것이 브리프 승인 계약(under-narrow 금지)에 맞다고 판단했다. ephemeral 응답 3키 계약은 그대로 유지했다.

### Issues found

- 테스트 작성 중 `ContextItemStatus.OK`가 존재하지 않아(`CANONICAL`/`CANDIDATE`) retrieval pointer fixture가 context_search 단계에서 502로 실패했다 — 테스트 fixture 오류였고 프로덕션 무관, `CANONICAL`로 정정했다.

### Verification

- 신규 회귀 `tests/test_writing_loop_audit.py` +12(service 5·HTTP 7): 재시도=distinct id·immutable(frozen), bodyless per-stage trail+final text, failed run error_type/null gate, project-scoped newest-first list, cross-project/missing 404 / 성공 loop 전체 trail+`final_candidate_hash==stages[-1].candidate_hash`, 모든 종료 감사(성공+gate 실패), 재시도 append+요약 bodyless newest-first, retrieval pointer_ids 캡처, no Core SOT save, **pre-loop 거부(400) 미기록(over-strict guard)**.
- Writing focused(7파일) → **128 passed / 108 subtests**.
- full non-Mongo: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **940 passed / 45 skipped / 209 subtests**. `git diff --check` clean, `py_compile` 통과.
- HTTP 통합 테스트가 실제 ASGI로 context build→loop→감사 persist→GET list/detail 관통을 구동하므로 런타임 표면을 관측 검증했다.

### Next steps

- 다음 Writing 후보는 B2(provider usage/latency/search 계측→aggregate token/time 기본값 브리프). 이후 multi-finding, stable pointer.
- persisted 감사 후속: retention(TTL/archive) 운영과제, 전체 중간 artifact 본문(P1=C)/byte-for-byte replay, B2 usage 필드 additive, stable candidate/GateRun pointer로 hash 대체.
- 독립 검증은 후속 verifier 대상(sandbox 밖 live 불요 — in-memory/Mongo 결정적 경로).

### 독립 검증 조건부 합격 closure + hardening (v1.6.78)

- 오너 독립 적대적 검증(`docs/verifications/2026-07-13/writing_persisted_loop_audit.md`)이 **조건부 합격**으로, 차단 발견 **B1**(detail trail 표면에 token/latency 부재·stage 본문 부재 forward-defense lock 없음 — 브리프 §102/§106)을 지적했다. mutation으로 실증됨: detail payload에 `token_usage`+stage `candidate_text` 주입 시 12 tests 전부 통과(빈 셀).
- **B1 closure(test-only, production 무변)**: `test_success_loop_persists_full_trail_and_returns_audit_id`에 detail top-level 15키 exact-set + stage row 6키 exact-set assertion을 추가했다. 재-mutation 시 `1 failed`로 bite 확인 후 원복(잔여 0). summary(8키)·ephemeral stages(3키)에 이어 detail 표면까지 잠가 B2 stage-level usage가 붙을 자리를 강제로 계약 변경 대상으로 만든다.
- **H1 보강**: 선례 `test_gate_findings_mongo.py` 패턴(브리프가 "채택된 기본값"으로 인용)을 따라 `tests/test_writing_loop_audit_mongo.py` 신설 — fake collection round-trip(`_doc`↔`_run` 필드 대칭), append-only insert(중복 `_id` raise), newest-first·project isolation·stable index name.
- **H2 보강**: `test_each_non_pass_200_status_leaves_a_record_with_that_status`로 나머지 4종 200 status(terminal_decision/not_eligible/budget_exhausted/no_change)가 각각 매칭 `loop_status` 감사 레코드를 남김을 잠갔다(uniform success site 회귀 방어).
- **H3 미구현(오너 결정 대기)**: `_record_loop_audit`가 감사 쓰기 실패를 catch하지 않아 Mongo `insert_one` 실패 시 성공한 loop 결과를 잃고 raw 500이 된다. 정본 미규정이고 fail-loud vs degrade-gracefully는 오너 정책 결정이라 임의 구현하지 않고 surface했다.
- Verification: `tests/test_writing_loop_audit*.py` → 16 passed/4 subtests, full non-Mongo → **944 passed / 45 skipped / 213 subtests**, `git diff --check` clean.

### 감사 opt-in 재개정 P2=A→B (SoT v1.6.79)

- H3(감사 쓰기 실패 정책)를 오너에게 질문하자, 오너가 더 근본적 방향을 지시했다: **감사와 실제 loop 작업을 분리하고, 항상이 아니라 필요할 때만, on/off 토글로 loop 실행 시 바로 적용.** 이는 같은 날 승인·잠근 **P2=A(항상 감사)와 충돌**하므로 CLAUDE.md §5대로 충돌을 명시하고 어느 쪽이 canonical인지 확인한 뒤 진행했다.
- 오너 확정: **A(request 플래그) + 기본 off**. 브리프에 "P2 재개정" 섹션을 추가하고 SoT를 v1.6.79로 올렸다.
- 구현: `WritingReviseRequest.persist_audit: bool | None = None`(null→env `WRITING_LOOP_AUDIT_DEFAULT` 기본 off, 요청 플래그 override). 엔드포인트에서 `persist_audit`를 1회 resolve하고, `_record_loop_audit`를 `(audit_id, audit_error)` 반환으로 리팩터 — 플래그 off면 `(None, None)`, on이면 `record()` 결과 id, 예외면 `(None, {"type":"audit_persist_error","detail":...})`. 5개 종료 응답에 `audit_error` additive.
- **H3 구조적 해소**: persist를 loop critical path 밖에서 try/except로 격리했으므로 쓰기 실패가 loop 결과를 죽이지 못한다. degrade vs fail-loud 질문 자체가 소멸했다(감사는 부차 side-effect, loop 결과 보존 우선).
- 회귀: 기존 HTTP 테스트는 `_post`가 기본 `persist_audit=true`를 싣도록 하고, 신규 3종 추가 — `test_opt_in_default_off_persists_nothing`(플래그 없음/false → audit_id·audit_error null, 목록 빈), `test_env_default_enables_audit_without_request_flag`(env true→플래그 없이 감사, false override), `test_persist_failure_is_isolated_from_the_loop_result`(raising repo → loop 200+pass 유지, audit_id null, audit_error=audit_persist_error). pre-loop 거부 미기록은 플래그 on에서도 유효.
- **바뀐 계약(문서화)**: boundary 1a/1b "모든 종료 감사"는 "persist on일 때만 감사"로 re-scope. 검증 기록 closure addendum에 H3 해소와 re-scope를 명시했다.
- Verification: loop-audit focused → 19 passed/6 subtests, full non-Mongo → **947 passed / 45 skipped / 215 subtests**, `py_compile`·`git diff --check` clean. B1 detail lock은 감사 detail payload(무변)에 그대로 유효.

### v1.6.79 opt-in delta 독립 재검증 + B2 closure

- 오너 요청("의심하고 또 의심해줘")으로 v1.6.79 opt-in delta의 독립 재검증을 수행했다(별도 verifier 컨텍스트). 검증 기록: `docs/verifications/2026-07-13/writing_loop_audit_optin_reverification.md`.
- boundary matrix(opt-in O1-O10): opt-in 게이트(O1-O5, 양방향)·persist 실패 격리·`audit_error` taxonomy(O6-O8)·pre-loop 미감사(O10)는 모두 filled. B1 detail exact-set(15키/6키)은 mutation re-bite로 두 독립 assertion(`:278` stage / `:271` top)에서 각각 bite함을 확인했다. `final_candidate_hash == stages[-1].candidate_hash`의 "by construction" 주장도 정밀 추적으로 반박 실패(주장 확인).
- **발견(B2, blocking)**: SoT v1.6.79가 "persist 미요청/**성공** 시 `audit_error`=null"을 명시하지만, "persist 성공 시 null"을 assertion하는 테스트가 없었다. mutation으로 `_record_loop_audit` 성공 return에 `audit_error`를 채우니 **16 passed**(bite 없음)로 빈 셀을 증명.
- **B2 closure(test-only, 1 line)**: `test_success_loop_persists_full_trail_and_returns_audit_id`에 `self.assertIsNone(response.json()["audit_error"])` 추가. 동일 mutation이 이제 `:250`에서 bite(1 failed). 빈 셀 filled.
- smoke: full non-Mongo **944 passed/48 skipped/215 subtests**(verifier 머신, ES 미설치). 작업자 머신(ES 설치) 기준 947/45/215 — 차이 3은 `elasticsearch` package skip, subtests 215 일치, HANDOFF에 문서화된 환경 차이.
- 결정: B2를 SoT 명시 contract-required로 보아 blocking을 유지(closure 조건으로). trivial test-only fix로 합격 re-promote.

## Phase 5.10 Writing loop aggregate budget ("B2 increment") 착수 결정 브리프

> 주의: 여기의 "B2 increment"는 L5=A에서 미룬 **aggregate token/time budget 후속**(SoT v1.6.77/78이 "B2"로 참조)이다. 바로 위 v1.6.79 재검증의 "B2 closure"(verification blocking finding 2)와는 다른 개념이다.

### Goals

- HANDOFF Next Tasks #1의 다음 Writing 후보 "B2 provider usage/latency/search 계측→aggregate token/time 기본값 브리프"를 구현 전 결정 단위로 분리한다.
- 계측 기계(전파·집계·강제)와 live 계측이 필요한 숫자 기본값을 혼동하지 않는다.

### Completed work

- 착수 전 정본 스코프를 대조했다: SoT v1.6.77 L5(구조적 call cap first, aggregate는 usage 계측 뒤 B2)·v1.6.78(token/latency 집계는 B2 후속)·§251-252(usage 누락→`provider_invalid_response`)·§292-293(budget 5차원 literal), `05-writing-bounded-loop-decisions.md` L4/L5/L6, `flat-loop-gate.md` §Budget 계약과 §production 기본값(2026-06-30 Gemma Q4 benchmark 절차).
- 코드 표면을 매핑했다: provider 경계는 이미 `GenerationResult.usage: TokenUsage`(prompt/completion/total, `provider.py:12-27`)를 반환하지만, **모든 Writing domain service**(`service.generate`·`revise`·`report.enrich`[+repair]·`gate.evaluate`·`retrieval.plan`[+repair])가 `result.usage`를 버리고 `.content`/`.model`만 소비한다. 구조적 cap(L4)은 round만 세고 token/시간/repair 호출은 안 센다. 5차원 중 실제로 비어 있는 loop 차원은 **total-token**과 **wall-clock** 둘뿐(search-hit/context-token은 Context Gate `ContextBudget` 소관).
- `docs/plans/05-writing-loop-budget-decisions.md`를 작성해 M1(범위 분리)·M2(강제 차원)·M3(usage 전파 방식)·M4(강제 시맨틱)·M5(관측 표면)·M6(기본값 posture/숫자 출처)를 owner-level 결정으로 분리했다. 각 선택지의 장단점을 남기고 추천 묶음 **M1=A, M2=A, M3=A, M4=A, M5=A first→B, M6=A first(ceiling B 후속)**를 근거와 함께 기록했다.

### Issues found

- 문제: aggregate token/time budget은 정의상 두 층으로 갈린다 — (1) usage plumbing·집계·강제 기계(fake provider로 결정적 검증 가능)와 (2) production 기본 숫자값(loop-level live 계측 없이 추측 불가). 한 slice로 묶으면 "근거 없는 숫자 금지"(L5 기각 논리)를 재현한다.
- 원인: 현재 domain 결과가 provider usage를 loop까지 전달하지 않고, loop-level aggregate 실측값이 없다(단일 turn benchmark만 존재).
- 해결/결과: 임의 구현을 중단하고 결정 브리프로 전환했다. 기계는 이번 slice(M1=A), 숫자는 B2b(full-stack 머신 loop-level benchmark)로 명시 분리했다. M3=A(내부 채널)로 public envelope 무변, M6=A(off/opt-in 기본)로 v1.6.79 opt-in posture와 대칭.
- 충돌 점검: scoped 정본 안에서 자기모순은 없었다. `flat-loop-gate.md` 5차원과 Writing loop L4 구조적 cap의 관계(중복 없이 total-token·wall-clock만 비어 있음)를 브리프 §"현재 확정된 경계"에 명시했다.

### Decisions

- 작업자 추천이며 아직 사용자 결정이 아니다: M1~M6 추천 묶음(위). 오너 승인 전 production code·SoT 버전은 변경하지 않았다.
- 추천 이유: 로컬 1인 프로젝트 단계에서 이 increment의 가치는 aggregate 차원을 "강제 가능한 형태로 확정"하는 것이지 검증 안 된 숫자를 박는 게 아니다. 기계를 지금 결정적으로 잠그고 숫자만 live 계측 뒤로 미룬다.

### Verification

- documentation-only 변경. 브리프가 인용한 파일/라인(벤치마크 JSON, SoT §251-252/§292-293, `provider.py:12-27`, 5개 domain service의 usage-drop)을 grep/원문 대조로 확인했다.
- `git diff --check` clean. production code·SoT 버전 무변.

### Next steps

- 오너가 `05-writing-loop-budget-decisions.md` M1~M6을 확정하면 결정을 이 로그와 SoT에 반영한다.
- 승인 후 boundary tests red-first → domain 결과 usage 내부 전파 + loop 집계/강제 → focused/full 비-LLM 회귀 순서로 구현한다. production 숫자값은 B2b(full-stack 머신 loop-level benchmark)로 별도 확정한다.

## Phase 5.10 Writing loop aggregate budget 구현 (SoT v1.6.80)

### Goals

- 중단된 B2 increment 작업을 승인된 M1~M6 계약에 맞게 완성한다.
- aggregate token/wall-clock을 강제하되 ephemeral loop payload와 standalone Writing endpoint 계약을 보존한다.
- success뿐 아니라 repair·최종 parse 실패가 소비한 provider usage도 감사 aggregate에 정확히 반영한다.

### Completed work

- 사용자 승인 기록을 복원했다: **M1=A**(기계 지금·production 숫자 B2b 후속), **M3=A**(내부 채널), **M6=A**(off 기본)를 직접 선택했고 **M2=A/M4=A/M5=A first→B**는 추천대로 확정했다. 브리프를 `Resolved`로, SoT를 v1.6.80으로 승격했다.
- `writing/metering.py`에 usage 합산과 내부 `MeteredCallError(error+usage)` 채널을 추가했다. revise/report/Gate/retrieval planner는 기존 public 메서드를 유지하고 loop 전용 `*_metered` 변형에서 success usage를 반환한다. provider 응답 뒤 parsing/repair가 실패하면 usage를 예외와 함께 전달하며, standalone 호출은 원래 domain/provider 예외를 그대로 다시 던져 HTTP taxonomy를 보존한다.
- `WritingLoopPolicy`에 optional `max_total_tokens`/`max_wall_clock_ms`를 추가했다. token은 논리 provider 단계 직후 누적해 `> limit` 결과를 채택하지 않고 `budget_exhausted`, `== limit` 완료는 허용한다. wall-clock은 revise/report/Gate/retrieval planner/context search 시작 전에 monotonic deadline을 검사한다. 첫 Gate 전 소진은 원 candidate 또는 마지막 완전 candidate를 보존하고 정상 200 `gate=null`을 반환한다.
- `main.py`와 Compose에 `WRITING_LOOP_MAX_TOTAL_TOKENS`/`WRITING_LOOP_MAX_WALL_CLOCK_MS`를 배선했다. unset/빈 값은 `None`(off)이며 구조적 round cap은 계속 유효하다.
- persisted audit `StoredWritingLoopRun`·Mongo doc·list/detail payload에 run-level `total_tokens`/`wall_clock_ms`를 additive로 추가했다. Mongo 구문서는 두 필드 부재 시 0으로 읽는다. ephemeral `loop` 4키와 stage row 공개 shape는 그대로다.
- boundary tests를 추가/보강했다: 네 concrete collaborator의 success·repair·parse-failure usage, failed-stage 누적, initial/revise/report/Gate/planner token 경계, retrieval planner 정확히 1회 집계, deadline pre-initial·pre-report·pre-context-search, provider timeout 분리, env on/empty-off, persisted audit aggregate와 legacy Mongo default를 직접 잠갔다.
- 주요 변경 파일: `services/application/app/writing/{metering,revise,report,gate,retrieval,revise_gate,loop_audit,loop_audit_mongo}.py`, `services/application/app/main.py`, `docker-compose.yml`, `tests/test_writing_{loop_budget,revise,report,gate,retrieval,loop_audit,loop_audit_mongo}.py`, SoT/브리프/HANDOFF/CHANGELOG.

### Issues found

- 문제: 중단된 구현은 token 초과를 각 provider 단계 직후가 아니라 다음 revise/retrieve 분기에서 검사해, 초과 Gate 결과를 채택하거나 report/Gate를 추가 호출할 수 있었다. wall-clock도 report/Gate/context-search 앞에서 검사하지 않았다.
- 원인: `over_budget()`가 while decision 분기에만 배치돼 M4의 post-accounting/deadline 경계가 stage lifecycle에 연결되지 않았다.
- 해결/결과: stage별 결과를 임시 변수로 받은 뒤 token 검사를 통과할 때만 current candidate/Gate에 채택하고, provider/search 전 deadline guard를 공통 배치했다. `gate`를 optional로 좁혀 첫 Gate 전 정상 budget 소진도 partial artifact를 잃지 않는다.
- 문제: provider는 성공 응답했지만 revise/Gate parser 또는 report/retrieval repair가 최종 실패하면 반환형 채널이 열리지 않아 소비 token이 failed audit에서 누락됐다.
- 해결/결과: 내부 `MeteredCallError`가 usage와 원인 예외를 함께 운반하고 loop이 usage를 먼저 합산한 뒤 원인을 복원한다. 이 응답으로 token이 초과되면 generic runner 선례대로 parse 오류보다 `budget_exhausted`가 먼저다. standalone error mapping은 기존 회귀로 무변을 확인했다.
- pattern sweep: `over_budget|max_total_tokens|deadline_reached`를 repo-wide 확인했다. Writing의 지연 검사 외 동일 결함은 없었고 generic `AgentLoopRunner`는 이미 provider usage 기록 직후 token overrun을 completion보다 먼저 판정한다. `git blame`상 `flat-loop-gate.md:83-93`의 post-accounting/deadline 계약은 2026-06-24 최초 결정으로 의도된 선례라 그대로 미러했다.

### Decisions

- 사용자 결정과 이유: 계측·강제 기계는 지금 확정하되 근거 없는 production 숫자를 넣지 않는다. 실제 기본 한도는 B2b full-stack loop benchmark 이후 결정한다.
- public candidate/Gate dataclass에 usage를 넣지 않고 내부 return/error 채널만 사용한다. aggregate 관측은 opt-in persisted audit에 한정하고 ephemeral `loop`/`stages`는 유지한다.
- search-hit/context-token은 Context Gate `ContextBudget` 소관으로 유지하며 이번 loop aggregate 차원에 중복 추가하지 않는다.
- 전체 중간 artifact/per-stage usage, standalone usage 공개, save/accept/Analysis side effect, B2b 숫자는 이번 커밋 범위 밖이다.

### Verification

- focused: `python3 -m pytest -q -p no:cacheprovider tests/test_writing_loop_budget.py tests/test_writing_gate.py tests/test_writing_revise.py tests/test_writing_retrieval.py tests/test_writing_report.py tests/test_writing_loop_audit.py tests/test_writing_loop_audit_mongo.py` → **116 passed / 90 subtests**.
- full non-Mongo: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **971 passed / 48 skipped / 215 subtests**, warnings 3개는 기존 `TestClient` collection warning이다.
- `python3 -m py_compile`(변경된 Application/Writing 모듈), `docker compose config --quiet`, `git diff --check` 통과.
- 이번 검증은 자체 구현의 routine self-check이므로 별도 `docs/verifications/` 기록은 생성하지 않았다.

### Next steps

- B2b: full-stack Gemma Q4에서 `revise→report→gate`, `retrieve→gate`, 반복 조합의 aggregate token/wall-clock p95를 측정하고 production 기본값 off→on 여부와 숫자를 결정한다.
- 그 전까지 aggregate cap은 env opt-in이며 구조적 revision/retrieval/Gate 상한이 기본 안전선이다.
- 이후 후보는 multi-finding/stable pointer, persisted audit retention/전체 artifact 또는 Phase 6 UI 잔여다.

## Phase 5.10 aggregate budget 독립 검증 B1 closure

### Goals

- 독립 검증 기록 `docs/verifications/2026-07-13/writing_loop_aggregate_budget.md`의 blocking B1을 닫고 H1~H3 보강 후보를 계약 범위 안에서 판정한다.

### Completed work

- B1 test-only closure: `test_legacy_doc_without_aggregate_fields_reads_zero`가 v1.6.80 이전 Mongo 문서를 재현하도록 저장 doc에서 `total_tokens`/`wall_clock_ms`를 제거하고 두 값이 모두 0으로 복원됨을 단언한다. 기존 field-for-field round-trip(`123`/`456`)이 present-value 방향을 계속 잠근다.
- H2: `token_over_budget()`에 token strict `>`(post-accounting)와 deadline `>=`(pre-stage)의 의도적 비대칭 및 `flat-loop-gate` §Budget 근거를 주석으로 추가했다. 동작은 무변이다.
- 검증 기록에 owner-authorized closure addendum을 추가해 B1 closure, M7 재-bite, H1/H3 보류 근거와 재현 결과를 남겼다. 원 독립 verdict는 역사적 기록으로 유지하고 독립 재판정을 가장하지 않았다.

### Issues found

- B1 원인: 기존 Mongo round-trip fixture가 신규 aggregate 필드를 항상 포함해 `doc.get(key, 0)`을 `doc[key]`로 바꿔도 legacy-doc 경로가 실행되지 않았다.
- 해결/결과: field-less legacy doc을 직접 구성하는 named regression을 추가했다. M7 변이에서 신규 test가 `KeyError: total_tokens`로 1 failed, 원복 뒤 1 passed해 guard bite를 확인했다.
- H1은 production 네 collaborator가 모두 `*_metered`를 가지므로 현재 도달 불가다. active token cap에서 bare fallback을 fail-fast로 바꾸면 새 collaborator injection/configuration 오류와 HTTP taxonomy가 생겨 현 정본 밖이므로 보류했다.
- H3은 token-overrun planner 결과를 채택하지 않는 M4 규칙과 Gate-overrun 대칭이다. 이를 `completed`로 기록하면 거짓이고 새 `budget_exhausted` stage literal은 M5=C per-stage 관측 schema 결정이므로 보류했다.

### Decisions

- 사용자 요청에 따라 contract-required B1과 의미 무변 H2만 즉시 보강한다.
- H1/H3은 비차단 권고이며 현재 계약을 넓히므로 구현하지 않고 각각 injection fail-fast 결정과 M5=C stage schema 후속으로 남긴다.

### Verification

- focused audit/B2: `python3 -m pytest -q -p no:cacheprovider tests/test_writing_loop_audit_mongo.py tests/test_writing_loop_audit.py tests/test_writing_loop_budget.py` → **39 passed / 6 subtests**.
- B1 mutation re-bite: `doc.get(key, 0)`→`doc[key]` 임시 변이 시 신규 test **1 failed**(`KeyError`), 원복 뒤 **1 passed**.
- full non-Mongo: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **972 passed / 48 skipped / 215 subtests**. warnings 3개는 기존 `TestClient` collection warning이다.
- `python3 -m py_compile services/application/app/writing/revise_gate.py services/application/app/writing/loop_audit_mongo.py`, `git diff --check` 통과.

### Next steps

- 독립 재검증이 필요하면 같은 verification record의 B1 cell과 M7 mutation만 재판정한다.
- H1은 production collaborator 교체/외부 injection이 실제 요구가 될 때 fail-fast taxonomy 브리프로, H3은 M5=C per-stage usage/artifact 관측 schema와 함께 결정한다.
