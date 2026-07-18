# 제품화 준비 — 트리거 기반 개선 백로그

상태: `Active`

성격: 구현 Phase가 아니라 **횡단 리스크·개선 항목의 착수 시점과 종료 조건을 관리하는 보조 계획**

정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md), [`frontend-kickoff-decisions.md`](frontend-kickoff-decisions.md), [`product-shell.md`](product-shell.md), [`06-review-ui.md`](06-review-ui.md)

## 목적

백엔드·운영·제품 품질·공개 준비에서 확인된 개선점을 한 번에 구현하지 않는다. 각 항목은 아래 표의 **착수 트리거가 실제로 발생했을 때만** `Ready`로 올리고, 그 시점의 사용자 경험과 실측 근거로 범위를 다시 확인한 뒤 하나씩 닫는다.

이 문서는 새 public contract나 SoT가 아니다. 확정 계약과 충돌하면 SoT가 우선하며, 계약·아키텍처·라이선스 선택처럼 오너 결정이 필요한 fork는 착수 시 별도 결정 브리프로 올린다.

## 상태와 운영 규칙

- `In progress`: 현재 제품 흐름을 위해 실제로 진행 중이다.
- `Standing`: 모든 변경에 계속 적용하는 운영 원칙이다.
- `Waiting`: 필요성은 확인됐지만 트리거 전이라 구현하지 않는다.
- `Ready`: 트리거가 발생해 다음 독립 slice로 착수할 수 있다.
- `Done`: 종료 조건과 검증 증거가 모두 충족됐다.
- `Dropped`: 실사용 근거로 불필요해졌으며 이유를 기록했다.

운영 규칙:

1. 현재 작업을 시작할 때 아래 `다음 점검 시점`과 맞닿는 항목만 확인한다.
2. 트리거 전 항목을 예방적 구현하지 않는다.
3. 트리거가 발생해도 기존 계약에서 답이 하나로 도출되지 않으면 결정 브리프가 먼저다.
4. 완료 시 이 표의 상태·증거 링크를 갱신하고 HANDOFF에서는 더 이상 현재 작업이 아닌 항목을 제거하거나 다음 트리거만 남긴다.
5. 새로운 백엔드 기능은 (a) 현재 UI slice가 요구한 계약 gap이거나 (b) dogfood에서 재현된 문제일 때만 이 백로그에 올린다.

## 활성 백로그

| ID | 상태 | 항목 | 착수 트리거 | 그때 할 일 | 종료 조건 | 다음 점검 시점 |
|---|---|---|---|---|---|---|
| UX-1 | **In progress** | 실제 작가 기본 루프 닫기 | 이미 발생: Frontend 첫 slice 완료 | A: 원고 목록·생성→`textarea`→명시적 저장→version→export, C: generate→Gate 근거→eligible bounded revise/retrieve→accept/save, B: Review Inbox 최소 action UI 순서로 연결 | 화면에서 `프로젝트 생성 → 원고 입력·저장 → 이어쓰기 생성 → Gate/자동 개선 확인 → 채택·새 version → Review action`을 API 수동 씨딩 없이 관통하고 회귀·live smoke가 존재 | 매 frontend slice 종료 |
| ARCH-1 | **Done** | `main.py` 점진 분리 | **발화: C D3=A 확정으로 Writing response/partial model을 실제 수정해야 함**. 단순 프론트 조립만이면 미발화 | ~~C0에서 먼저 Writing `http_models.py`를 분리한다. 의존성 전달이 명확할 때만 router를 추출하며 전 도메인 일괄 이동은 금지한다.~~ **완료(v1.7.1)**: Writing HTTP 모델을 `services/application/app/writing/http_models.py`로 분리, route는 추출하지 않음(의존성 전달이 아직 복잡). | ✅ Writing HTTP 모델이 별도 모듈로 분리돼 `main.py`는 모델 정의를 늘리지 않았고, focused/full 회귀(1117 passed)와 OpenAPI exact-key 계약(`Writing*EnvelopeKeyTest` 9)이 유지됨 | — (완료) |
| OPS-1 | Waiting | Lite / Full 실행 모드 | A+C 최소 UI가 동작하고 2주 dogfood를 시작하기 직전 | Lite의 보장 기능과 degraded 기능, worker/outbox backlog 처리, Mongo-direct fallback을 먼저 고정한 뒤 `mongo + application + gateway + frontend` 중심 실행 경로와 Full 경로를 제공 | Lite 기동 명령 하나로 편집·저장·generate·accept가 관통하고, 제외 기능·Full 전환·pending outbox 동작이 문서화·검증 | 실 12B 관통 확인 + 오너 dogfood 착수 결정 시 |
| QUAL-1 | Waiting | 실제 원고 dogfood와 제품 품질 지표 | A+C가 UI에서 사용 가능하고 Lite 또는 Full 중 시험 실행 경로가 안정화됐을 때 | 새 telemetry 백엔드를 만들지 않고 우선 수동 기록: 생성/채택, 채택 후 대폭 수정 여부, Gate 경고 유용성, 장면 완료 시간. 최소 2주 실제 장편에 사용 | 최소 2주·5회 이상 집필 세션의 기록과 반복 문제 목록이 있고, 다음 백엔드/UX 우선순위를 실사용 근거로 결정 | A+C·OPS-1 후 시작, 1주/2주차 검토 |
| PROC-1 | **Standing** | 문서화 비용 계층화 | 지금부터 모든 변경 | work log는 유지하되, 결정 브리프는 genuine fork에만, 독립 verification record는 명시적 검증 요청에만, SoT/CHANGELOG는 계약·주요 설계·기능 변화에만 사용한다. 일반 UI/CSS는 구현 후 간단 기록 | 각 slice 기록이 해당 artifact의 trigger와 맞고, 되돌리기 쉬운 UI 선택 때문에 구현이 멈추지 않음 | 모든 slice 종료 |
| REPO-1 | Waiting | `ai_writte_system` 이름 정정 | 공개 포트폴리오 URL 확정, 첫 외부 협업자 초대, 또는 외부 배포 설정 추가 중 가장 이른 시점 | 제품명과 저장소 slug를 결정한 뒤 remote·문서 링크·경로 의존 설정을 한 번에 갱신 | 새 이름으로 clone/build/run 가능하고 repo-wide 이전 slug 검색 결과가 의도된 이력 외 0건 | 외부 공개/협업 직전 |
| LEGAL-1 | Waiting | 코드·문서 라이선스 경계 재결정 | 상업 pilot/유료 제공 검토, 외부 기여 수락, 또는 공개 배포 중 가장 이른 시점 | 현재 CC BY-NC-SA 4.0 단일 적용을 유지할지, 코드용 소프트웨어 라이선스와 문서 라이선스를 분리할지 오너 결정. 필요 시 법률 검토와 제3자 구성요소 조건 확인 | 선택한 코드/문서 경계가 LICENSE·README·기여 정책에 일치하고 제품화 방식과 모순 없음 | 외부 기여/상업 검토 전 |
| GATE-1 | Waiting | Phase 7 진입 게이트 | UX-1 완료 + QUAL-1 2주 검토 완료 | dogfood에서 반복 재현된 문제와 Phase 7 P1~P5를 대조해 가치가 입증된 첫 slice만 선택 | 오너가 실사용 근거와 함께 Phase 7 첫 slice를 확정하고 그 slice의 착수 브리프가 준비됨 | B 완료 및 dogfood 2주차 |

## 고정 순서와 체크포인트

2026-07-16 A 체크포인트: editor/save/history/export 구현과 프론트 회귀를 완료했다. backend route/request/response model을 수정하지 않은 순수 프론트 조립이므로 **ARCH-1은 Waiting 유지(미발화)**하며 다음은 C(Writing generate·Gate·accept)다.

2026-07-16 C 착수 결정 체크포인트: D3=A로 Writing 성공·partial response model과 OpenAPI 계약을 C0에서 실제 수정하기로 확정했다. 따라서 **ARCH-1은 Ready로 전환**하며, 범위는 Writing `http_models.py` 우선 분리까지다. 전 `main.py` 또는 타 도메인 router 일괄 이동은 여전히 범위 밖이다.

2026-07-16 C0 종료 체크포인트: Writing HTTP 모델을 `services/application/app/writing/http_models.py`로 분리하고 4 endpoint에 성공 `response_model`·partial `responses={}`를 연결했다(SoT v1.7.1). router는 추출하지 않았다(의존성 전달이 아직 복잡). **ARCH-1은 Done**으로 종결한다 — 범위였던 "Writing HTTP 모델 우선 분리"가 완료됐고, 이후 다른 도메인 router 추출은 그 도메인의 실제 트리거가 다시 발생할 때만 판단한다. 다음은 C1 기본 generate→Gate→accept/save UI다.

2026-07-16 C1 종료 체크포인트: 기본 Writing 작업공간(generate→Gate 근거→pass accept/save, D1=A 게이팅+설명 텍스트)을 구현했다(SoT v1.7.2, `WritingPanel`). 이로써 A(편집/저장/history/export)+C1(기본 집필 루프)이 UI에서 동작한다. **`OPS-1` trigger 점검**: OPS-1은 "A+C 최소 UI가 동작하고 2주 dogfood를 시작하기 직전"에 발화한다. C1이 최소 집필 루프를 닫았으나 (1) **실 LLM 관통(compose generate→Gate→accept smoke)이 아직 미실행**(12B 필요, sandbox 불가)이고 (2) dogfood 착수는 오너 결정이라 **OPS-1은 Waiting 유지**한다 — 오너가 실 스택에서 기본 루프를 관통 확인하고 dogfood를 시작하기로 할 때 Ready로 올린다. `ARCH-1`은 C1이 backend/schema 무변(순수 소비)이라 재발화하지 않는다. 다음은 C2 bounded loop UI다.

2026-07-16 C2 종료 체크포인트: `/writing/revise-and-gate` 자동 loop UI와 6종 status·partial 재시도 매핑을 구현해 C 전체를 완료했다(SoT v1.7.3). **`OPS-1` trigger 재점검**: A+C 코드 UI는 완료됐지만 실 12B generate→Gate→loop→accept 관통이 미실행이고 dogfood 착수는 아직 오너가 결정하지 않아 **Waiting을 유지**한다. 두 조건이 충족될 때 Ready로 올린다. 프론트 고정 순서의 다음 작업은 B Review Inbox다.

2026-07-18 Review Inbox 라이브 관통 종료 체크포인트: B Review Inbox의 7 write action이 실 스택·실 12B로 전부 라이브 검증됐다(2026-07-17 candidate/conflict 5개 + 2026-07-18 gate finding resolve/dismiss 2개, `docs/verifications/2026-07-18/gate_finding_live_trigger.md`). **`OPS-1` trigger 재점검**: OPS-1의 두 조건 중 **"실 12B 관통 확인"은 이제 gate finding 표면까지 완결돼 충족**됐고, 남은 조건 **"오너 dogfood 착수 결정"만 대기**한다. 따라서 **Waiting 유지** — 오너가 dogfood 착수를 결정할 때 Ready로 올린다(그 시점에 Lite의 보장/degraded 기능·worker/outbox backlog·Mongo-direct fallback을 먼저 고정하는 결정 브리프가 선행). 프론트 고정 순서의 다음 단계는 dogfood 시작이다.

```text
현재
  → A: 원고·에디터·저장·version·export
      [ARCH-1 점검]
  → C: Writing generate·Gate·bounded revise/retrieve·accept
      [ARCH-1, OPS-1 점검]
  → B: Review Inbox 최소 UI
      [ARCH-1 점검]
  → Lite/Full 준비 + 실제 원고 dogfood 시작
      [OPS-1 착수, QUAL-1 1주/2주 점검]
  → UX-1 + QUAL-1 충족
      [GATE-1: Phase 7 착수 여부 결정]

외부 공개·협업·상업 검토가 먼저 오면
  → REPO-1 / LEGAL-1만 해당 트리거에 따라 별도 착수
```

## 현재 범위 밖

- 이 문서 작성과 동시에 `main.py`를 일괄 분리하지 않는다.
- Compose Lite/Full 구조나 fallback 계약을 지금 추측 구현하지 않는다.
- 제품 지표를 위한 telemetry/event store를 미리 만들지 않는다.
- 저장소 이름이나 라이선스를 지금 변경하지 않는다.
- UX-1과 QUAL-1을 건너뛰고 Phase 7을 착수하지 않는다. 단, 오너가 새 근거와 함께 우선순위를 명시적으로 바꾸면 그 결정을 기록하고 갱신한다.
