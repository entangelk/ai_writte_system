# 최종 저장과 분석 연동 — 착수 결정 브리프

상태: `Partially resolved` — 오너 결정 D1=B · D2=B · D3=B (2026-09-01); D4 실행 경로 결정 대기
작성: 2026-09-01
정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md) v1.8.13, [`frontend-editor-save-decisions.md`](frontend-editor-save-decisions.md), [`05-writing-accept-decisions.md`](05-writing-accept-decisions.md), [`scene-note-implementation-phases.md`](scene-note-implementation-phases.md) Slice 3~4

## 결정 완료

직접 편집한 Scene을 한 번만 **최종 저장**해 저장과 분석을 함께 시작하고, 그 뒤의 일반 저장·수동 분석을 최종화 이력과 구별하는 상태 계약을 확정했다. 현재 일반 저장은 version만 만들고 분석은 별도 수동 동작이라, 도그푸드에서 분석 시점을 놓치기 쉽다. 이 계약은 `Draft` 수명·분석 job·다음 장면 문맥 표시에 걸리므로 기존 구현만으로 선택할 수 없었다.

## Current behavior and constraints

- 일반 `저장`은 `draft_version`·snapshot을 만들지만 분석 job은 만들지 않는다. 편집기는 저장 상태와 분석 상태를 따로 보인다.
- `이 원고 분석`은 snapshot마다 `analyze:{snapshot_id}` 키로 job을 만들며, 이어쓰기 후보의 `채택하고 저장`도 같은 키를 사용한다. 같은 snapshot의 재클릭은 job·후보를 중복 생성하지 않는다.
- 현재 `Draft`에는 archive 외의 수명 상태가 없다. 따라서 최종 저장을 단순 UI 플래그로 만들면 다른 기기·재접속·다음 장면 생성에서 사라진다.
- 다음 장면 이어쓰기는 현재 Scene의 최신 version에서 현재 장면 구간·직전 문단 블록과 승인된 canonical memory를 읽는다. 장/Scene 압축 요약을 별도로 만들거나 자동 승인하지 않는다.
- canonical memory는 AI가 직접 쓰지 않고 분석 후보를 검토·승인한 뒤에만 다음 생성 문맥에 들어간다. 최종 저장이 이 원칙을 우회하면 안 된다.

## D1 — 최종 저장 뒤의 Scene 상태

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 최종 저장 후 수정 금지 | final snapshot 뒤에는 일반 저장도 막는다 | “최종”의 의미가 가장 단순하다 | 오타·후속 편집을 위해 archive/복제 같은 과한 우회가 필요하다 |
| **B. 최종화 이력 보존 + 후속 수정됨 상태** | 최초 final snapshot은 보존하고, 그 뒤 일반 저장이 생기면 `최종 저장 후 수정됨`으로 표시한다 | 사용자가 정한 “최종 저장은 한 번만”을 지키면서 수정·수동 분석을 허용한다 · 어떤 version이 final이었는지 잃지 않는다 | 화면에 상태가 하나 더 생기고 최종화와 최신 version을 구분해야 한다 |
| C. 일반 저장 시 final을 자동 취소 | 후속 저장이 final marker를 지워 상태를 다시 초안으로 만든다 | 화면 상태가 둘뿐이다 | 한 번 실행한 최종 저장 이력과 분석 기준 snapshot을 잃어 감사·다음 작업 판단이 흐려진다 |

### Recommendation + reason

**B를 권장한다.** 도그푸드에서 final 뒤에도 고치고 싶다는 요구를 수용하면서, “최종 저장은 다시 쓰지 않는다”를 불변 이력으로 남긴다. 현재 append-only version 모델과도 맞는다. UI는 최신 version을 보되 `최종 저장됨` 또는 `최종 저장 후 수정됨`을 명확히 보여 사용자가 수동 분석이 필요한 상태를 알 수 있다.

### 오너 결정

**D1=B.** 최초 final snapshot은 보존한다. 이후 일반 저장은 허용하되 final marker를 지우지 않고 `최종 저장 후 수정됨` 상태로 계산한다.

## D2 — 최종 저장의 분석 실패 의미

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 분석 성공 뒤에만 final marker를 기록 | 저장과 분석을 하나의 성공으로 취급한다 | 최종 상태가 항상 분석 완료를 뜻한다 | 분석 장애가 원고 저장 자체를 막거나 재시도 시 final one-shot 의미를 복잡하게 만든다 |
| **B. 저장·final marker를 먼저 확정하고 분석은 후속 job으로 둔다** | final snapshot은 즉시 확정하고 같은 snapshot의 분석 job을 생성한다. job 실패는 `분석 필요` 상태로 남긴다 | 기존 `채택하고 저장`의 saved-partial 선례·snapshot idempotency를 재사용한다 · 원고는 분석 장애에도 잃지 않는다 | final 상태와 분석 완료 상태를 화면에서 분리해야 한다 |
| C. 저장만 하고 분석은 화면이 나중에 자동 호출 | API 변경을 작게 보일 수 있다 | 네트워크 이탈·다른 기기에서 분석이 누락될 수 있어 “최종 저장하면 분석” 약속이 깨진다 |

### Recommendation + reason

**B를 권장한다.** final 저장은 정본 version의 사실이고 분석은 파생 작업이다. 저장 성공·분석 실패를 구분하는 현재 accept의 502 partial 선례를 그대로 사용하면, 실패가 사용자에게 숨지 않으면서 final snapshot도 보존된다.

### 오너 결정

**D2=B.** final marker와 본문 저장을 먼저 확정하고, 같은 snapshot의 분석 job을 후속으로 생성한다. 분석 장애는 final 저장을 되돌리지 않으며 `분석 필요`로 후속 조치한다.

## D3 — 화면 상태와 재실행 규칙

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. final 버튼을 성공 뒤 숨긴다 | 버튼이 사라져 한 번만 가능함을 보인다 | 구현이 작다 | 왜 사라졌는지·후속 수정이 어떤 상태인지 알기 어렵다 |
| **B. 상태 배지 + 비활성 final 버튼 + 수동 분석 안내** | `초안` / `최종 저장됨·분석 진행/완료/필요` / `최종 저장 후 수정됨`을 색과 문구로 보이고, final 버튼은 불가 사유를 표시한다 | 사용자가 현재 Scene의 다음 행동(수동 분석 또는 계속 편집)을 바로 안다 | 상태 문구·색상 접근성 회귀가 필요하다 |
| C. final 버튼을 일반 저장으로 바꿔 재사용 | 버튼 하나로 계속 저장한다 | 표면은 단순하다 | “최종 저장은 한 번”이라는 약속을 UI가 흐리고 일반 저장과 구별되지 않는다 |

### Recommendation + reason

**B를 권장한다.** finality·analysis·later edit는 서로 다른 사실이다. 색만으로 상태를 전달하지 않고 텍스트 배지와 상태 설명을 함께 두어야 한다. final 이후 본문을 수정하면 일반 `저장`은 계속 가능하고, 저장 직후 상태는 `최종 저장 후 수정됨 · 수동 분석 필요`가 된다.

### 오너 결정

**D3=B.** 작업실과 편집기 모두 상태 배지·비활성 final 버튼·수동 분석 안내를 보인다. 특히 최신 저장본이 분석되지 않았을 때는 작업실에서도 한 번 더 `분석 필요`를 상기시킨다.

## D4 — final 저장이 분석을 실제로 실행하는 경로

### Decision needed

현재 분석은 job을 만든 뒤 브라우저가 별도 `/run` 요청을 해야만 실행된다. final route가 job만 만들면
분석은 `pending`에 멈춰 “최종 저장하면 분석”을 충족하지 못한다. source-ref 준비·사용량 정산·장애
후속도 이 실행 경로와 함께 정해야 한다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. final API가 저장 뒤 동기로 분석 실행 (권장)** | final marker·snapshot을 먼저 확정한 뒤 서버가 기존 분석 runner를 호출한다. 분석 실패는 저장을 유지한 partial 응답과 `분석 필요` 상태로 끝난다. | 별도 worker·브라우저 후속 요청 없이 약속을 지킨다 · 현재 수동 분석 runner를 재사용한다 · 1인 로컬 단계의 가장 작은 구현이다 | final 클릭 응답이 분석 시간만큼 길어진다 · 이 endpoint도 분석 1회 사용량을 정산해야 한다 |
| B. durable analysis worker를 새로 둔다 | final은 pending job만 만들고 worker가 claim·실행한다. 화면은 polling으로 완료/실패를 받는다. | 응답이 빠르고 재시도·장애 복구가 견고하다 | analysis job lease·worker·배포 command·사용량 선차감/실행 차감 정책이 모두 새로 필요하다 |
| C. 브라우저가 저장 성공 뒤 기존 분석 버튼 흐름을 자동 호출 | final 응답 뒤 client가 source-ref 준비와 `/run`을 호출한다. | 서버 변경이 가장 작아 보인다 | 브라우저 이탈·네트워크 단절 때 분석이 누락된다. D2=C를 기각한 이유를 되살린다 |
| D. job만 만들고 수동 분석을 기다린다 | final은 pending analysis job만 기록한다. | 구현은 작다 | 자동 분석이 실행되지 않아 요구를 충족하지 못한다 |

### Recommendation + reason

**A를 권장한다.** 현재 수동 분석은 이미 동기 runner로 제공되고, final은 Scene당 한 번인 명시적
사용자 행위다. 저장을 먼저 커밋하면 분석 timeout/provider 장애도 D2=B대로 원고를 잃지 않는다.
worker는 대량·장시간 분석이 실제 병목으로 측정될 때 열어도 늦지 않다.

### Follow-up considerations

- A를 고르면 final route는 분석 provider 호출을 여는 유료 route로 분류하고, 기존 분석과 같은
  quota·소유권·LLM audit 경계를 적용한다. final의 한 번 실행은 분석 한 번의 정산이다.
- source-ref catalog은 final snapshot에 대해 서버가 준비해야 한다. 이 준비 또는 runner가 실패하면
  final marker는 유지하고 최신 snapshot을 `분석 필요`로 보여 준다.
- final 요청 재전송은 marker·snapshot을 중복 생성하지 않는다. 분석이 실패한 뒤의 재실행은 D1의
  사용자 방향대로 기존 수동 분석 경로가 담당한다.

## 확정 계약

- Scene별로 `finalized_snapshot_id`, `finalized_at`을 한 번만 기록한다. final marker를 덮거나 삭제하는 public 경로는 제공하지 않는다.
- `POST /projects/{project_id}/drafts/{draft_id}/finalize`가 최신 본문을 새 version으로 저장하고 final marker 및 `analyze:{snapshot_id}` 분석 job을 만든다. 같은 final 요청의 재시도는 동일 결과로 수렴해야 한다.
- 일반 저장은 marker가 없으면 `초안`, marker가 최신 snapshot과 같으면 `최종 저장됨`, marker보다 최신 version이 있으면 `최종 저장 후 수정됨`으로 상태를 계산한다.
- final marker 뒤의 일반 저장은 허용하되 분석을 자동으로 만들지 않는다. 사용자는 기존 수동 분석으로 최신 snapshot을 분석한다.
- 분석 최신성은 시간 비교가 아니라 **snapshot 동일성**으로 계산한다. 최신 snapshot에 `analyze:{snapshot_id}` job이 `succeeded`이면 `분석 완료`, `pending`/`running`이면 `분석 진행 중`, job이 없거나 `failed`이면 `분석 필요`다. 과거 성공 job의 snapshot이 최신 저장본과 다르면, 성공 기록이 있어도 최신 저장본은 `분석 필요`다.
- final 저장 요청은 archive·소유권·본문 4000자 상한을 일반 저장과 같은 순서로 적용한다. 저장 성공 뒤에만 활동 행을 남긴다.
- Scene 목록·편집기·작업실 화면은 상태를 보여 줄 수 있도록 final marker·최신 version·최신 snapshot analysis job 관계를 읽는다. 색은 보조 수단이며 상태 텍스트가 정본이다.

## Follow-up considerations

- 분석 job이 완료됐는지와 final marker는 별개다. 현재 `AnalysisJob`에는 완료 시각이 없고 비동기 재시도 순서도 있을 수 있으므로, “마지막 분석 시간”을 비교하지 않는다. 최신 snapshot과 job의 `snapshot_id` 관계가 정본이다.
- final snapshot의 분석 후보는 현재와 같이 review를 거쳐 canonical memory가 된다. 다음 장면 생성이 이 후보를 자동으로 신뢰하지 않도록 한다.
- 같은 snapshot의 분석 job은 기존 `(project_id, snapshot_id, analyze:{snapshot_id})` idempotency로 한 건에 수렴한다. 이 보장은 final 저장과 수동 분석이 공유한다.
- 한 Scene final이 같은 Chapter 전체의 종료를 뜻하지는 않는다. 장 단위 compacting·다음 장면 전용 handoff summary는 별도 계약이 필요하다.
- 퍼지 시 marker는 Draft의 자식 수명으로 함께 사라져야 한다. archive는 현재 원고 정책처럼 읽기 허용·쓰기 차단을 유지한다.
- 새 mutating route면 OpenAPI·`schema.d.ts`·activity 분류표·tier 행렬·소유자/grant 경계를 함께 갱신한다.

## Deferred / out of scope

- 장/프로젝트 단위 compacting, 요약의 저장 위치, 다음 장면 프롬프트 주입
- 분석 후보의 자동 canonical 승인 또는 review 우회
- final marker 해제·재최종화·여러 final milestone
- 4000자 상한 변경(현재 상한은 이어쓰기 문맥 예산을 위한 별도 Approved 계약)
- 공동 편집자의 final 권한·승인 흐름, export에 final 표시
- 서로 다른 snapshot인데 본문과 분석기 버전이 같은 경우의 content-hash 분석 중복 억제
- 분석기/프롬프트/스키마 버전별 재분석 정책과 분석 결과의 세대(generation) 표시
- D4=B를 선택할 때의 analysis worker 모델·lease·재시도·배포 command
