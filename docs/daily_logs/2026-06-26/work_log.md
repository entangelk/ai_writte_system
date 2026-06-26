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

### HANDOFF 기반 다음 작업 검토

- 변경 파일: `HANDOFF.md`, 이 작업 로그.
- HANDOFF의 현재 상태, 다음 작업, 검증 기록을 확인했다.
- 현재 구현 완료 범위는 LLM Gateway 0.1~0.6과 AgentLoopRunner A1/A2/A3/parser/provider composition이다.
- runner domain tool-call branch와 task별 `artifact_present` 구조 평가는 상류 계약이 없으므로 계속 후속 범위로 유지한다.

### System Contract SoT 착수 가능성 재검토

- 변경 파일: `HANDOFF.md`, 이 작업 로그.
- `docs/system-contract-sot.md`, `docs/plans/README.md`, `docs/plans/implementation-plan.md`, `docs/plans/01-core-sot.md`를 대조했다.
- SoT와 `plans/README.md`의 문서 우선순위는 같은 5-level tree로 통일되어 있다.
- SoT는 현재 `Approved` v1.1이며, 본문은 미확정 항목을 추측해 구현하지 말라고 명시한다.
- Slice 1 착수에 필요한 결정은 아직 남아 있다: Core SOT의 block split·offset·hash/normalization·transaction/idempotency·삭제 보존 정책.
- 위 항목은 구현 계약과 저장 스키마를 직접 바꾸므로 작업자가 임의로 선택하지 않고 사용자 확인이 필요하다.

## Issues found

### Slice 1 착수 전 결정 미해소

- 문제: 다음 구현 작업은 Slice 1(Project Shell + Core SOT)이지만, Core SOT 계획의 착수 전 결정사항이 아직 체크되지 않았다.
- 원인: SoT v1.1은 미확정 항목을 계속 추측 구현 금지로 두며, Phase 1 계획도 offset/hash/block/idempotency/delete policy 같은 계약 선택을 별도 사용자 결정 전까지 열어두었다.
- 해결: 코드 구현 대신 결정 필요 항목을 HANDOFF에 더 명확히 남겼다.
- 결과: 다음 작업자는 같은 지점에서 스키마를 추측하지 않고 사용자 결정부터 받을 수 있다.

### 검색 명령 quoting 주의

- 문제: `rg` 패턴에 backtick을 double quote 안에 넣어 shell command substitution 경고가 발생했다.
- 원인: Markdown literal 검색어를 shell quoting 없이 전달했다.
- 해결: 출력 자체는 필요한 위치를 찾는 데 충분했지만, 이후 유사 검색은 single quote로 감싸야 한다.
- 결과: 파일 변경이나 검증 결과에는 영향이 없다.

## Decisions

- **[사용자 결정, 2026-06-26]** `docs/system-contract-sot.md`를 정본 계약 인덱스로 승인했다. 승인 범위는 문서 우선순위와 이미 확정·검증된 계약의 인덱스 역할이며, 미확정 결정 목록은 계속 추측 구현 금지로 남긴다.
- 정본 계약은 앞으로 사용자 결정으로 업데이트될 수 있으므로 SoT 내부에 계약 버전과 변경 이력을 둔다.
- **[사용자 결정, 2026-06-26]** Slice 1 실행 경계는 monorepo + 독립 LLM Gateway, FastAPI backend, 느슨하게 분리 가능한 Worker 구조로 승인했다. frontend framework는 보류하며 standalone frontend가 필요할 때 React/Vue 중 선택한다. 초기 개인 로컬 runtime은 외부 queue 제품 없이 단순 in-process/background boundary로 시작한다.
- Slice 1의 저장 스키마, offset 기준, hash/normalization, block split, transaction/idempotency, 삭제 정책을 임의로 정하지 않았다.
- 이번 작업은 SoT 승인과 문서 상태 정리까지만 수행했다. 실제 Slice 1 구현은 사용자 선택을 받은 뒤 진행한다.

## Next steps

1. Slice 1 착수 전 Core SOT 결정을 해소한다: offset/hash/normalization, block split/scene marker, version save/idempotency, archive/delete policy.
2. 결정이 내려지면 Project Shell + Core SOT의 최소 저장 골격과 회귀 테스트를 구현한다.
3. Slice 1 결정이 현재 SoT 정본 계약을 바꾸면 계약 버전을 올리고 변경 이력에 사용자 결정 근거를 남긴다.
