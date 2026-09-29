# 2026-09-29 Work Log

## Goals

- 배포에서 이미 성공한 원고의 후보를 거절한 뒤에도 새 분석이 실행되지 않는 원인을 확인한다.
- 오너가 확정한 확인 후 재분석 흐름을 구현하고 SoT에 반영한다.

## Completed work

- `AnalysisTrigger` → `analyzeVersion` → analysis job `/run` 경로를 추적했다. 첫 분석 key `analyze:{snapshot_id}`가 이미 `succeeded`면 job 생성은 replay이고 `/run`도 기존 후보를 반환한다. 후보 `reject`는 후보 상태만 `rejected`로 바꾼다. job의 `succeeded` 상태는 바꾸지 않는다. UI는 replay 결과를 신규 생성 후보 수처럼 표시했다. 배포 데이터 직접 조회 없이 저장소 코드와 기존 회귀로 구조 원인을 확정했다.
- `frontend/src/api/client.ts`: 성공한 첫 job을 발견하면 `/run` 없이 재분석 확인 필요 결과를 반환한다. 확인된 재분석은 `reanalyze:{snapshot_id}:{UUID}` key의 새 job을 만든다.
- `frontend/src/review/AnalysisTrigger.tsx`: “재분석 하시겠습니까?” 확인을 표시한다. 취소 시 `/run`을 호출하지 않고, 예를 누른 경우만 새 분석을 시작한다. 확인된 분석이 실패하거나 429 중복 요청 확인을 만나도 같은 key를 재사용한다.
- `frontend/src/review/AnalysisTrigger.test.tsx`: 성공 job 재생에서 확인이 필요한 경우, 취소 시 실행 없음, 확인 시 별도 job 실행, 실패한 새 job의 동일 key 재시도를 검증한다. 기존 첫 분석·실패 job·과금 확인 테스트를 유지했다. 새 확인 테스트 2개는 수정 전 구현에서 실패함을 확인했다.
- SoT v1.8.77, 관련 분석 job·Writing accept 계획, README 버전 참조, HANDOFF, CHANGELOG를 갱신했다. HTTP API와 데이터 스키마는 변경하지 않았다.

## Issues found

| 문제 | 원인 | 해결 | 결과 |
|---|---|---|---|
| 후보를 모두 거절해도 새 분석이 안 됨 | 후보 거절은 job 상태를 바꾸지 않고 첫 분석 key는 snapshot에 고정되어 성공 job으로 replay | 성공 job 발견 시 확인을 받은 뒤 새 key·새 job으로 실행 | 사용자 명시 의도로 같은 저장 원고를 재분석할 수 있음 |
| 기존 후보 수가 새 분석 결과처럼 표시됨 | replay된 `succeeded` job의 후보 수를 신규 결과로 렌더 | 성공 replay에서 `/run`과 결과 표시를 중단하고 확인 대기 | 오래된 후보를 새로 생성된 것으로 오인하지 않음 |

## Decisions

- 오너 결정: 기존 분석이 있으면 사용자에게 “재분석 하시겠습니까?”라고 묻고, 예를 누르면 재분석한다. SoT를 이에 맞춰 개정한다.
- 첫 분석의 `analyze:{snapshot_id}` 공유 key와 실패 job의 명시 retry는 유지한다. 성공 job만 별도 사용자 의도로 새 job을 만든다. 기존 job과 거절된 후보는 감사 기록으로 보존한다. 확인된 재분석에서 아직 검토 중인 후보가 있다면 새 후보와 함께 보일 수 있으므로, 재분석은 사용자 명시 확인이 필요하다.

## Verification

- 수정 전 `AnalysisTrigger` 회귀 2개 실패: 성공 replay에서 확인 대신 기존 결과 처리.
- 집중 프런트 회귀 37 passed (`AnalysisTrigger` 18, quota 19), `npm run build` 성공.
- 프런트 전체 `npm test`: 42 files / 494 passed. `npm run build`: 성공.
- 관련 백엔드·문서 회귀(`test_docs_indexes.py`, `test_writing_accept.py`, `test_analysis_job_state.py`): 95 passed / 357 subtests. `git diff --check`: 성공.
- 패턴 스윕: `analyzeVersion`의 호출자는 `AnalysisTrigger` 하나이며, accept의 `analysis_job_key`는 첫 분석 job 생성에만 쓰인다. `/run` replay 서버 경로는 API 멱등 계약이므로 유지한다. 기존 key 사용처의 2026-07-18 `git blame`은 중복 후보 방지를 위해 첫 분석을 accept job에 합친 의도임을 확인했다.

## Next steps

- 오너가 배포할 때 frontend 이미지를 재빌드·재생성한 뒤, 기존 성공 job이 있는 저장 원고에서 확인 → 예 → 새 후보 생성과 취소 → 실행 없음 경로를 확인한다. 이 세션에서는 배포 서버에 접속하거나 데이터를 변경하지 않았다.
