# 2026-09-30 작업 로그

## Goals

- 분석 `/run` 응답이 524로 끊길 때 사용자 화면이 작업 실패를 단정하지 않도록 수정.
- 검토함 그룹 설명 여백과 작업공간 바의 그룹 표시·후보 수정을 보완.
- 그룹의 인물 이름을 승인 전에 모든 검토 대기 후보에 반영.

## Completed work

- `frontend/src/api/client.ts`: 분석 `/run` 요청의 524만 별도 지연 응답으로 분류했다.
- `frontend/src/review/AnalysisTrigger.tsx`: 지연 안내와 검토함 링크를 표시하고 자동 재시도 버튼을 숨겼다. 자동 상태 조회 요청은 추가하지 않았다.
- `frontend/src/review/AnalysisTrigger.test.tsx`: `/run`의 524는 지연 안내, 실행 전 524와 일반 502는 기존 오류 처리로 남는 양방향 회귀를 추가했다. 새 524 셀은 구현 전 실패했고 구현 뒤 통과했다.
- 검증: 분석 화면 20/20, 프런트 전체 496/496, TypeScript 검사와 프로덕션 빌드 통과.

- `frontend/src/styles.css`, `frontend/src/pageLayout.test.ts`: 그룹 상자의 좌우 여백을 복원하고 재발 검사를 추가했다.
- `frontend/src/review/reviewEntries.ts`, `ReviewInbox.tsx`, `WorkspaceReviewPanel.tsx`, `WorkspaceReviewPanel.test.tsx`: 검토함의 기존 그룹 묶기 규칙을 작업공간 바에서 공유하고, 기존 후보 수정 API를 작업공간 바에서 사용할 수 있게 했다.
- 검증: 프런트 전체 499/499, TypeScript 검사, 프로덕션 빌드 통과.
- 회귀 변이 확인:

  | 적용한 변이 | 위치 | 실패한 셀 |
  | --- | --- | --- |
  | 그룹 padding을 `var(--space-4) 0`으로 되돌림 | `frontend/src/styles.css` `.review-group` | `keeps explanatory text inset on both sides of the group box` |

- `services/application/app/analysis/service.py`, `identity_group_review.py`, `identity_groups.py`, `routers/analysis.py`, `api/models.py`: 그룹 이름 교정 API가 이름만 바꾼 검토 대기 새 후보 버전을 만들고 옛 후보를 보존하도록 했다. 그룹 revision·멤버십, 색인 outbox와 열린 대기열을 갱신하며 중간 실패의 후계 버전을 재사용한다.
- `frontend/src/review/ReviewInbox.tsx`, `WorkspaceReviewPanel.tsx`, `api/client.ts`: 검토함과 작업공간 바에서 그룹 이름을 함께 교정하고 서버 목록을 다시 읽는다.
- `activity/actions.py`, `frontend/src/projects/activityActions.ts`: 그룹 교정을 활동 로그 한 행으로 기록한다. 공개 API 스키마를 재생성했다.
- `tests/test_identity_group_approve.py`, 검토 화면 테스트: 교정 전 정본 없음, 관찰·출처 보존, 그룹 승인 후 단일 정본, 저장 실패 재시도, 두 화면의 요청 본문을 검증한다. `review_inbox.py`는 후보 버전 이력에서 기존 relation을 찾아 그룹 설명 근거를 유지한다.
- 검증: 프런트 전체 501/501, 프로덕션 빌드, 관련 백엔드 321 passed·1 skipped·1952 subtests, 문서 링크·계약 검사 통과.

## Issues found

- 동기 `/run`은 결과가 오기 전에 앞단 응답 제한에 걸릴 수 있다. 524는 작업의 성공·실패를 확정하지 않는다.
- 기존 `/edit`는 수정과 동시에 정본 승인·원본 종료를 수행한다. 이를 그룹의 모든 후보에 반복하면 정본이 중복되고 기존 그룹 승인 계약과 충돌한다. 사용자가 승인 전 교정을 선택해 별도 경로로 해결했다.
- 패턴 스윕: 검토함과 작업공간 바 모두 `buildEntries`를 공유하며, 다른 후보 수정 진입점은 검토 상세 화면에 있다. 그룹 여백 규칙의 원래 위치는 `git blame`으로 확인했다.
- 패턴 스윕: `services/application/app/routers/drafts.py:754`의 최종 저장 분석도 동기 실행이다(`git blame`: 2026-09-01 최종 저장 배선). 응답 계약이 다른 경로이므로 이번 화면 수정 범위에는 넣지 않았다.

## Decisions

- 사용자는 폴링으로 인한 추가 조회를 원치 않는다. 524가 났을 때 작업을 실패로 표시하지 않고, 지연 가능성과 검토함의 수동 새로고침을 안내한다.
- 별도의 자동 조회, 서버 실행 방식 변경, 재시도 요청은 이번 수정에 포함하지 않는다. 검토함에 후보가 보이지 않는 것만으로 작업 실패가 확정되는 것은 아니라는 한계를 유지한다.

- 사용자는 그룹 후보 전체에 인물 이름만 함께 반영하고 각 후보의 관찰·사건 문장은 유지하기를 원한다. 기존 `/edit`의 즉시 정본 승인과 충돌하므로 **승인 전 교정(A)**을 선택했다. 새 후보 버전은 `needs_review`로 남기고 그룹 승인으로 정본 하나에 수렴한다. [결정 브리프](../../plans/group-name-correction-decisions.md).

## Next steps

- 최종 저장 분석의 긴 응답 문제는 해당 화면과 응답 계약을 기준으로 별도 검토한다.
