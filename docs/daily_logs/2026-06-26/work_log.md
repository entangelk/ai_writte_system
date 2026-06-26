# Work Log — 2026-06-26

## Goals

- HANDOFF를 읽고 다음 작업을 진행한다.
- `docs/system-contract-sot.md`가 Slice 1 착수 전 정본 역할을 할 수 있는지 재확인한다.
- 사용자 결정 없이 구현하면 안 되는 미확정 항목을 분리한다.

## Completed work

### System Contract SoT 승인

- 변경 파일: `docs/system-contract-sot.md`, `docs/README.md`, `docs/plans/README.md`, `HANDOFF.md`, `CHANGELOG.md`, 이 작업 로그.
- 사용자 요청으로 SoT를 `Approved` v1.0으로 승격하기 전에 다시 검토했다.
- 확인 결과 SoT와 `plans/README.md`의 문서 우선순위는 이미 같은 5-level tree이며, 독립 검증 기록도 SoT의 literal/link/status 일치를 합격으로 판정했다.
- 승인 범위를 문서 안에 명시했다. `Approved`는 정본 계약 인덱스와 문서 우선순위의 승인이지, 미확정 결정 목록의 기술 선택을 자동 확정하는 것이 아니다.
- 이후 사용자 결정으로 정본 계약이 바뀔 수 있으므로 `계약 버전 관리`와 `계약 변경 이력` 섹션을 추가했다.
- `docs/README.md`, `docs/plans/README.md`, `HANDOFF.md`의 "초안/Draft 승격 대기" 문구를 현재 상태에 맞게 갱신했다.

### Slice 1 실행 경계 승인

- 변경 파일: `docs/system-contract-sot.md`, `docs/plans/implementation-plan.md`, `HANDOFF.md`, `CHANGELOG.md`, 이 작업 로그.
- 사용자 결정으로 monorepo + 독립 LLM Gateway 경계를 승인했다.
- backend framework는 FastAPI로 승인했다. 사용자가 이미 경험한 framework이고, 현재 Python async/httpx 기반 코드와도 맞는다.
- frontend framework 최종 선택은 보류했다. 개인 로컬 시스템의 단일 서비스 UI로 충분할 수 있으므로, standalone frontend가 필요해지는 시점에 React 또는 Vue를 기본 후보로 검토한다.
- Worker는 Application 코드와 계약을 공유하되 느슨하게 연결하고, 나중에 별도 entrypoint/process로 분리 가능하게 둔다.
- 초기 local/personal runtime에서는 외부 queue 제품을 전제하지 않고 단순 in-process/background boundary로 시작한다.
- 이 결정은 서비스 경계와 구현 기술 계약에 영향을 주므로 SoT 계약 버전을 v1.0에서 v1.1로 올렸다.

### Core SOT text/reference 계약 승인

- 변경 파일: `docs/system-contract-sot.md`, `docs/plans/01-core-sot.md`, `docs/plans/03-indexing.md`, `HANDOFF.md`, `CHANGELOG.md`, 이 작업 로그.
- 사용자 결정으로 raw snapshot을 MongoDB SOT로 두고, 검색/인덱스/vector DB는 MongoDB pointer/version/hash로 재조회 가능한 파생물로 유지한다.
- offset 기준은 raw snapshot Unicode code point로 승인했다.
- raw snapshot은 저장 후 변경하지 않으며, `content_hash`는 raw UTF-8 bytes의 SHA-256으로 승인했다.
- `normalized_text_hash`는 v1 필수 계약이 아니며 정규화 기반 dedupe/search가 필요해질 때 별도 계약으로 추가한다.
- MVP `source_blocks`는 Markdown heading, 단독 `---`/`***` scene marker, 빈 줄 paragraph 기반 deterministic split으로 승인했다.
- AI 추론 기반 장면 분할은 SOT block split에 사용하지 않는다.
- adaptive chunking, semantic chunking, 길이 기반 episode/section chunking은 Phase 3 이후 파생 index 전략 후보로 남겼다. 이들은 MongoDB raw snapshot/source_ref 정본을 대체하지 않는다.
- 이 결정은 Core SOT 정본 계약에 영향을 주므로 SoT 계약 버전을 v1.1에서 v1.2로 올렸다.

### Core SOT persistence/retention 계약 승인

- 변경 파일: `docs/system-contract-sot.md`, `docs/plans/01-core-sot.md`, `docs/plans/03-indexing.md`, `docs/plans/implementation-plan.md`, `HANDOFF.md`, `CHANGELOG.md`, 이 작업 로그.
- 사용자 결정으로 Docker 기반 정상 runtime은 MongoDB transaction을 기본으로 사용한다.
- non-transaction fallback은 transaction을 사용할 수 없는 local/test 환경의 제한적 경로로 두며, write order, idempotency lookup, orphan cleanup/retry guard를 요구한다.
- MVP는 명시적 version save만 지원한다. autosave는 AI 생성 결과가 항상 맞지 않는다는 제품 판단 때문에 초기 구현에서 제외하고, 실제 필요성이 확인될 때 별도 결정으로만 추가한다.
- draft save request는 `idempotency_key`를 필수로 가진다. 같은 `project_id + draft_id + idempotency_key` 재시도는 새 version을 만들지 않고 같은 `draft_version`을 반환한다.
- project/draft 삭제는 MVP에서 archive로 처리한다.
- `draft_versions`, `source_snapshots`, `source_blocks`, `source_refs`는 archive 이후에도 보존한다.
- archive/delete 이후 파생 index는 stale 처리, version/status filter, rebuild 대상으로 둔다.
- 사용자가 언급한 분석 후보의 부분 승인, 부분 저장, 나머지 retry는 Slice 1 draft save idempotency가 아니라 Phase 2/6 review action idempotency 계약에서 다룬다.
- 이 결정은 Core SOT 정본 계약에 영향을 주므로 SoT 계약 버전을 v1.2에서 v1.3으로 올렸다.

### Slice 1 Core SOT 최소 구현 골격

- 변경 파일: `services/application/app/core_sot/`, `services/application/app/main.py`, `services/application/requirements.txt`, `tests/test_core_sot.py`, `tests/test_application_api.py`, `docs/plans/implementation-plan.md`, `docs/system-contract-sot.md`, `HANDOFF.md`, `CHANGELOG.md`, 이 작업 로그.
- `core_sot.models`에 `Project`, `Draft`, `DraftVersion`, `SourceSnapshot`, `SourceBlock`, `SourceRef`, `SaveDraftResult` dataclass와 `BlockKind` literal을 추가했다.
- `core_sot.splitter`에 raw UTF-8 SHA-256 `content_hash`, Markdown heading/단독 `---`·`***`/빈 줄 paragraph 기반 deterministic splitter, block materializer를 추가했다.
- `core_sot.service`에 infrastructure-free `InMemoryCoreSotRepository`와 `CoreSotService`를 추가했다. 이는 Mongo adapter 전까지 application-level contract를 잠그는 skeleton이다.
- `save_draft`는 `idempotency_key`를 필수로 요구하고, 같은 `project_id + draft_id + idempotency_key` 재시도 시 기존 `draft_version`/snapshot/blocks를 반환한다.
- `create_source_ref`는 raw Unicode code point offset으로 exact quote/hash를 재구성하고, block boundary를 넘는 span과 bool offset을 거부한다.
- project/draft archive는 새 save를 막지만 기존 version/snapshot/source_blocks는 보존한다.
- `services/application/app/main.py`에 FastAPI shell을 추가했다: `/health`, project 생성, draft 생성, draft version save.
- `services/application/requirements.txt`에 `fastapi>=0.115,<1`을 추가했다.
- MongoDB adapter, transaction-backed repository, Docker compose, export, editor shell은 이번 맛보기 범위에서 제외했다.

### Docker build cache 제약 기록

- 변경 파일: `HANDOFF.md`, 이 작업 로그.
- 사용자 결정으로 Dockerfile/Compose를 추가할 때 빌드할 때마다 새로 전부 빌드되지 않도록 build cache를 고려해야 한다.
- 향후 Dockerfile은 dependency manifest 복사·설치 레이어를 소스 복사보다 앞에 두고, 불필요한 전체 rebuild를 유발하는 `COPY .`/캐시 무효화 패턴을 피한다.
- 이 지시는 다음 Docker/Docker Compose slice의 구현 제약으로 남겼다.

### Core SOT minimal skeleton 독립 검증 보강

- 변경 파일: `tests/test_core_sot.py`, `docs/system-contract-sot.md`, `docs/plans/01-core-sot.md`, `HANDOFF.md`, `CHANGELOG.md`, 이 작업 로그.
- 독립 검증 기록 `docs/verifications/2026-06-26/core_sot_minimal_skeleton.md`의 판정은 조건부 합격이었다.
- C1 보강: `***` scene marker, `##` heading, `archive_project` 후 신규 draft/save 차단과 history 보존 회귀를 추가했다.
- C2 보강: `content_hash("두번째")`의 known SHA-256/UTF-8 vector를 하드코딩해 동일 함수 비교 tautology를 제거했다.
- C3 보강: MVP `source_ref` span은 하나의 `source_block` 안에 포함되어야 한다는 계약을 SoT와 Phase 1 계획에 명시했다. 여러 block을 가로지르는 인용은 후속 후보/review 계약에서 별도로 다룬다.
- focused Core SOT/API 회귀는 11개에서 14개로 늘었다.

### HANDOFF 기반 다음 작업 검토

- 변경 파일: `HANDOFF.md`, 이 작업 로그.
- HANDOFF의 현재 상태, 다음 작업, 검증 기록을 확인했다.
- 현재 구현 완료 범위는 LLM Gateway 0.1~0.6과 AgentLoopRunner A1/A2/A3/parser/provider composition이다.
- runner domain tool-call branch와 task별 `artifact_present` 구조 평가는 상류 계약이 없으므로 계속 후속 범위로 유지한다.

### System Contract SoT 착수 가능성 재검토

- 변경 파일: `HANDOFF.md`, 이 작업 로그.
- `docs/system-contract-sot.md`, `docs/plans/README.md`, `docs/plans/implementation-plan.md`, `docs/plans/01-core-sot.md`를 대조했다.
- SoT와 `plans/README.md`의 문서 우선순위는 같은 5-level tree로 통일되어 있다.
- SoT는 현재 `Approved` v1.3이며, 본문은 미확정 항목을 추측해 구현하지 말라고 명시한다.
- Slice 1 Core SOT 착수 전 결정은 text/reference와 persistence/retention까지 해소됐다.
- 후속 결정이 SoT v1.3과 충돌하면 구현 전에 사용자 확인이 필요하다.

## Issues found

### Slice 1 착수 전 결정 미해소

- 문제: 다음 구현 작업은 Slice 1(Project Shell + Core SOT)이지만, 작업 초반에는 Core SOT의 persistence/retention 결정사항이 아직 열려 있었다.
- 원인: SoT v1.2 시점에는 Phase 1 계획이 transaction/idempotency/save mode/delete policy 같은 계약 선택을 별도 사용자 결정 전까지 열어두었다.
- 해결: 사용자 결정을 받아 transaction 기본, limited fallback, explicit save only, idempotency key, archive/preserve 정책을 SoT v1.3과 Phase 1 계획에 반영했다.
- 결과: Slice 1 Core SOT 착수 전 결정이 해소됐다.

### Core SOT source_ref bool offset 방어

- 문제: Python에서는 `bool`이 `int`의 하위 타입이라 `start_offset=False`, `end_offset=True` 같은 값이 정수 검사에 통과할 수 있었다.
- 원인: 초기 `create_source_ref` 검사가 `isinstance(value, int)`만 사용했다.
- 해결: bool을 명시적으로 거부하는 `_is_int` helper와 회귀 `test_source_ref_offsets_reject_bool_values`를 추가했다.
- 결과: source_ref offset 계약이 `BudgetPolicy`의 정수 방어와 같은 방향으로 정리됐다.

### 검색 명령 quoting 주의

- 문제: `rg` 패턴에 backtick을 double quote 안에 넣어 shell command substitution 경고가 발생했다.
- 원인: Markdown literal 검색어를 shell quoting 없이 전달했다.
- 해결: 출력 자체는 필요한 위치를 찾는 데 충분했지만, 이후 유사 검색은 single quote로 감싸야 한다.
- 결과: 파일 변경이나 검증 결과에는 영향이 없다.

## Decisions

- **[사용자 결정, 2026-06-26]** `docs/system-contract-sot.md`를 정본 계약 인덱스로 승인했다. 승인 범위는 문서 우선순위와 이미 확정·검증된 계약의 인덱스 역할이며, 미확정 결정 목록은 계속 추측 구현 금지로 남긴다.
- 정본 계약은 앞으로 사용자 결정으로 업데이트될 수 있으므로 SoT 내부에 계약 버전과 변경 이력을 둔다.
- **[사용자 결정, 2026-06-26]** Slice 1 실행 경계는 monorepo + 독립 LLM Gateway, FastAPI backend, 느슨하게 분리 가능한 Worker 구조로 승인했다. frontend framework는 보류하며 standalone frontend가 필요할 때 React/Vue 중 선택한다. 초기 개인 로컬 runtime은 외부 queue 제품 없이 단순 in-process/background boundary로 시작한다.
- **[사용자 결정, 2026-06-26]** Core SOT text/reference 계약은 raw snapshot 기준으로 승인했다. offset은 raw Unicode code point, `content_hash`는 raw UTF-8 SHA-256, `normalized_text_hash`는 v1 필수 아님, MVP block split은 Markdown heading/scene marker/paragraph 기반 deterministic 규칙이다. adaptive/semantic/length-based chunking은 Phase 3 이후 파생 index 전략 후보로 남긴다.
- **[사용자 결정, 2026-06-26]** Core SOT persistence/retention 계약은 MongoDB transaction 기본, local/test 제한 fallback, 명시적 version save only, autosave 제외, `idempotency_key` 필수, project/draft archive, snapshot/version/source_ref 보존으로 승인했다.
- **[사용자 결정, 2026-06-26]** 분석 후보의 부분 승인, 부분 저장, 나머지 retry는 Slice 1 draft save idempotency가 아니라 Phase 2/6 review action idempotency 계약에서 다룬다.
- **[사용자 결정, 2026-06-26]** Dockerfile/Compose를 추가할 때 dependency layer cache를 보존해 매번 전체 rebuild가 일어나지 않도록 한다.
- 오늘 구현은 실제 MongoDB adapter 없이 application core contract를 잠그는 최소 skeleton으로 제한했다. 이는 뼈대를 먼저 세우고 storage adapter를 후속으로 붙이기 위한 선택이다.

## Next steps

1. MongoDB adapter와 transaction-backed repository를 추가해 현재 in-memory Core SOT service contract를 실제 저장소에 연결한다.
2. Mongo transaction path, non-transaction fallback guard, idempotency unique constraint, archive 후 stale/index 이벤트 후보를 회귀로 잠근다.
3. Slice 1 결정이 현재 SoT 정본 계약을 바꾸면 계약 버전을 올리고 변경 이력에 사용자 결정 근거를 남긴다.

## Verification

- `python3 -m py_compile services/application/app/core_sot/models.py services/application/app/core_sot/splitter.py services/application/app/core_sot/service.py services/application/app/main.py tests/test_core_sot.py tests/test_application_api.py`
- `python3 -m unittest tests.test_core_sot tests.test_application_api -v` — 14개 통과
- `python3 -m unittest discover -s tests -p 'test_*.py'` — 151개 통과
