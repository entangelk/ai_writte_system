# 실검수 브리프 — 이어쓰기 후 재분석 `source_ref not found`

상태: `Resolved — Option C approved`
발견일: `2026-07-18`
승인일: `2026-07-18`
근거 스택: working tree `99cd40a`, application/frontend 재배포 스택, 실 12B
정본 연결: [`system-contract-sot.md`](../../system-contract-sot.md), [`02-analysis-job-state-decisions.md`](../../plans/02-analysis-job-state-decisions.md), [`02-analysis-provider-wiring-decisions.md`](../../plans/02-analysis-provider-wiring-decisions.md), [`05-writing-accept-decisions.md`](../../plans/05-writing-accept-decisions.md)

## 이 문서의 성격

`docs/live_review_briefs/`는 오너의 실제 브라우저 검수에서 발견된 결함 중 기존 승인 계약끼리 충돌하거나, 수정 방향이 owner-level 선택을 요구하는 항목을 구현 전에 기록하는 폴더다. 대화 이력이 아니라 **재현 증거, 충돌 계약, 오너 결정, 구현·재검수 기준**을 보존한다. 상세 실행 이력은 같은 날짜 `daily_logs`에, 독립 감사 결과는 `verifications`에 둔다.

## 재현과 정본 증거

재현 순서:

1. 저장 snapshot을 분석해 `needs_review` 후보를 만들되 승인/채택하지 않는다.
2. AI 이어쓰기를 accept해 본문과 snapshot을 확장한다.
3. 새 snapshot에서 다시 “이 원고 분석”을 실행한다.
4. 첫 run이 HTTP 400 `source_ref not found`로 실패한다.

라이브 대상은 project `6a59899206eb78cecda6d4a6`, 새 snapshot `6a5aeba0b339f88750c0a94f`, job `6a5aeba1b339f88750c0a950`이다.

- 새 snapshot의 full-span source_ref catalog 9개는 snapshot/block/span/quote/hash가 모두 일치했다. catalog 누락·부분 빌드가 아니다.
- accept가 job에 실은 `writing_candidate_report`는 생성 시점 구 snapshot `6a59899206eb78cecda6d4a9`의 stable `source_blocks` pointer 2개를 보유한다.
- Analysis prompt는 새 snapshot의 authoritative `source_ref_catalog`와 위 advisory report를 함께 전달한다. strict source resolver는 catalog 밖 anchor를 `source_invalid/source_ref not found`로 거절했다.
- raw provider output은 저장되지 않으므로 모델이 구 `document_id`를 `source_ref_id`로 그대로 복사했는지는 확정할 수 없다. 다만 related pointer가 비었던 accept-report 라이브는 성공했고, 이번 실패 입력만 구 source pointer namespace를 함께 노출해 혼동의 강한 유발 요인이다.
- D5=A는 key를 `analyze:{snapshot_id}`로 고정하고, 기존 Phase 2A Fork B는 FAILED를 불변 terminal로 둔다. 따라서 재클릭은 같은 failed job을 HTTP 200 replay하며 candidate 0개를 반환한다. 프론트는 job status를 검사하지 않아 이를 “새 후보 없음” 성공으로 오인한다.
- 첫 분석 후보의 미채택 상태는 직접 원인이 아니다. 실패 경계는 accept report의 구 snapshot pointer와 새 catalog가 함께 들어간 추출/run이다.

## Decision needed

strict source 근거 계약을 완화하지 않으면서 prompt namespace 혼동을 예방하고, D5=A의 snapshot당 단일 job identity 안에서 failed 분석을 사용자가 복구할 방법을 정해야 한다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. Prompt만 보강 | 새 prompt version에서 report pointer와 source_ref ID namespace를 명확히 분리 | 상태 계약 무변, 변경 작음 | 다시 실패하면 같은 snapshot은 계속 dead-end |
| B. Retry만 추가 | FAILED job을 명시적으로 같은 job에서 재실행 | 사용자가 복구 가능, snapshot당 job 1개 유지 | prompt 혼동이 반복될 수 있음 |
| C. 둘 다 | 새 prompt version + 명시적 same-job retry + 프론트 failed 판별 | 예방·복구·정확한 UX를 함께 해결 | prompt/public API/job-state 계약을 함께 개정해야 함 |
| D. Report pointer 제거 | Analysis에 전달할 report에서 related pointers를 삭제 | namespace 혼동을 결정적으로 줄임 | stable report provenance 활용 계약이 약해지고 원인 정보가 사라짐 |

## Recommendation + reason

**C**를 권장한다. 현재 로컬 1인 dogfood 단계에서는 strict 근거 검증을 유지하면서도 사용자가 같은 원고를 다시 시도할 수 있어야 한다. prompt만 고치면 비결정적 provider 실패의 dead-end가 남고, retry만 열면 동일 혼동을 반복한다. same-job 명시 retry는 D5=A의 orphan 0/job 1개 경계를 보존한다.

## Owner decision

오너는 **C**를 승인했다.

1. `analysis_extract_v2`를 새 immutable prompt literal로 추가한다. `writing_candidate_report.related_context_pointers`는 advisory provenance이며 source anchor가 아니고, output `source_anchors[].source_ref_id`는 **현재 `source_ref_catalog[].source_ref_id`에서만** 복사해야 함을 first/repair prompt에 명시한다.
2. strict catalog/source validation과 1회 repair 상한은 유지한다. invalid anchor를 묵인·자동 remap하지 않는다.
3. FAILED는 일반 replay에서는 계속 terminal이다. 신규 **명시적 retry command**만 같은 job을 `FAILED → PENDING`으로 되돌리고 failure fields를 비운다. `SUCCEEDED`는 계속 불변이며 자동 retry하지 않는다.
4. 프론트의 “다시 분석”은 create replay가 FAILED이면 명시 retry 후 run한다. run이 HTTP 200이어도 job status가 `failed`/`running`이면 성공 candidate 0으로 처리하지 않는다.

### 구현 중 실 12B 반례와 v3 승격

초기 v2 배포 뒤 위 동일 job을 재실행했으나 `source_invalid/source_ref not found`가 다시 발생했다. 상태 retry 축은 정상이나 주의 문구만으로 예방 축이 닫히지 않은 반례다. 진단 호출의 first output은 현재 catalog ID를 선택했지만 구형 `claim/type` shape와 ID만 든 불완전 anchor를 반환해 repair로 진입했다. 따라서 seed된 v2를 변경하지 않고 다음을 구조화한 `analysis_extract_v3`를 새 기본값으로 둔다.

- first prompt에 정확한 candidate taxonomy/payload/full-anchor 필드 계약을 명시한다.
- serialized user payload에서 advisory report 뒤에 authoritative current catalog를 둔다.
- repair turn에는 구 report identifier namespace를 다시 노출하지 않고 snapshot text와 authoritative current catalog만 전달한다.

strict validation, 자동 remap 금지, repair 1회 상한은 그대로다.

## 구현·재검수 결과

- backend/frontend 전체 회귀와 build/OpenAPI 생성 통과: backend 1126 passed/48 skipped/276 subtests, frontend 124 passed/8 files.
- 원 실패 job `6a5aeba1b339f88750c0a950`은 신규 retry로 같은 ID를 유지한 채 pending으로 복구되고 failure fields가 비워졌다.
- 첫 v3 live run은 원 `source_ref not found`가 아니라 별도 비결정적 malformed JSON으로 한 번 실패했다. 진단 first output은 현재 catalog ID와 full anchor를 사용했다. 다음 명시 retry가 succeeded로 끝나 candidate 5개를 저장했다.
- succeeded job 재호출은 `idempotent_replay=true`; 같은 candidate ID 5개가 반환돼 중복 생성 0을 확인했다.
- application health 200/healthy, frontend HTTP 200. 기존 frontend healthcheck의 localhost→`::1` false-negative는 이 결함과 무관한 비차단 운영 항목이다.

판정: **Resolved**. 원 source namespace 오류의 예방과 failed dead-end 복구는 닫혔다. 모델의 비결정적 malformed JSON이 반복 관측되면 raw Analysis output 관측/품질을 별도 실검수 브리프로 연다.

## Acceptance matrix

| 경계 | 기대 결과 | 회귀 방향 |
|---|---|---|
| 구 source-block pointer가 든 report + 새 catalog | v2 prompt가 namespace를 명시하고 catalog ID로 정상 추출 | under-strict |
| report/pointer 없는 기존 snapshot 분석 | 종전처럼 정상 추출 | over-strict |
| provider가 catalog 밖 anchor를 계속 반환 | strict `source_invalid`, candidate 저장 0 | over-strict/fail-closed |
| FAILED job 일반 create/run replay | 재실행 없이 failed 그대로 | over-strict(명시성) |
| FAILED job 명시 retry | 같은 job ID가 pending→run, failure fields clear | under-strict |
| retry 성공 후 재클릭 | succeeded replay-only, candidate ID/수 불변 | 양방향 |
| SUCCEEDED/RUNNING/PENDING에 retry command | 409, 상태 무변 | over-strict |
| HTTP 200 failed run envelope | 프론트 오류 표시, “후보 없음” 미표시 | under-strict |

## Follow-up considerations

- retry attempt count/audit가 운영상 필요해지면 additive field로 별도 결정한다. 이번 slice는 상태·기존 failure 이력 overwrite 외 새 감사 schema를 만들지 않는다.
- raw Analysis provider output 관측 도구는 동일 문제가 재발할 때 별도 live diagnostics 브리프로 연다.
- cross-snapshot 후보 의미 중복은 compare/review 정책의 별도 문제이며 same-job retry와 섞지 않는다.

## Deferred / out of scope

- source anchor 자동 remap 또는 validator 완화
- report의 stable related pointer 삭제/스키마 변경
- provider repair 횟수 증가
- RUNNING stale lease/자동 복구
- 구버전 random-key failed job 데이터 정리
