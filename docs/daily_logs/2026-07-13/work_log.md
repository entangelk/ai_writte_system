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
