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
