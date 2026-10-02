# 2026-10-02 작업 로그

## Goals

- 그룹 승인 후 화면이 멈추고 새로고침 시 첫 후보가 사라지는 증상을 배포 기록과 대조한다.
- 오래 걸리는 그룹 승인 요청의 진행 상태를 버튼 옆에서 알 수 있게 한다.

## Completed work

- 배포 서버 로그와 해당 그룹의 승인 진행 문서·LLM 감사 기록을 읽기 전용으로 확인했다. 10월 1일 14:14:27 KST 시작, 14:15:06 완료: 후보 2건 모두 `applied`, 첫 후보 `create`, 다음 후보 `add_evidence`, 정본 버전 2. AI 판정은 39,280ms, 승인 요청과 후속 목록 조회 모두 HTTP 200이었다.
- 14:14:58 목록 조회는 승인 완료 전이었다. 첫 후보는 이미 승인돼 검토함에서 빠졌고 두 번째 후보는 판정 중이었다. 사용자도 이 요청이 신고 대상이라고 확인했다.
- `frontend/src/review/ReviewInbox.tsx`: 해당 그룹 승인 버튼을 `그룹 승인 중…`으로 바꾸고 버튼 아래에 순차 판정 대기 및 새로고침 중간 상태 안내를 표시한다.
- `frontend/src/review/ReviewInbox.test.tsx`: 응답을 지연시킨 상태의 진행 안내·중복 클릭 잠금·실패 후 해제·개별 승인에는 안내를 표시하지 않는 경계를 검증한다. 기존 정상 승인 셀에도 안내 해제 단정을 추가했다.
- 구현 체크포인트: `e12cebd`. API·스키마·승인 처리 계약 변경 없음. `npm test -- --reporter=dot` 전체 42파일/502셀 통과. `npm run build` TypeScript 검사와 프로덕션 빌드 통과. 기존 WritingPanel의 `act(...)` 경고는 실패가 아니다.
- 변이 전 `git status --short`가 빈 출력인 것을 확인했다. 각 변이 후 HEAD의 파일 바이트를 복원하고 빈 작업 트리를 확인했다. 이 환경의 `git checkout`은 index.lock 쓰기가 거부돼, `git show HEAD:<path>` 출력으로 복원했다.

  | 적용한 변이 | 위치 | 실패한 셀 |
  | --- | --- | --- |
  | 버튼 문구를 `그룹 승인`으로 복원하고 안내 조건을 `{false && (`로 교체 | `frontend/src/review/ReviewInbox.tsx:349`, `:374` | `shows progress during group approval and clears it on failure, excluding individual approval` — 진행 버튼 부재, 1 failed/24 skipped |
  | 안내 조건을 `busy === group-confirm 키`에서 `busy !== null`로 확대 | `frontend/src/review/ReviewInbox.tsx:374` | 같은 셀 — 개별 승인 중 안내가 표시돼 `toBeNull()` 실패, 1 failed/24 skipped |

- 재현 명령: `cd frontend`, `npm test -- --reporter=dot src/review/ReviewInbox.test.tsx -t 'shows progress during group approval'`. 정상 완료 후 안내 해제는 기존 `approves a group with the revision the read surface gave it, then re-reads` 셀에서 잠근다.
- 두 변이 복원 후 `npm test -- --reporter=dot src/review/ReviewInbox.test.tsx` 25/25 재통과. 기록 참조 파일 존재와 `git diff --check`를 확인했다.
- 사용자 배포 지시에 따라 09:22 KST 프런트엔드를 재빌드·교체했다. Git bundle로 검증된 커밋까지 fast-forward했고, 기존 이미지는 롤백용 태그로 보관했다. 서버의 기존 미추적 Compose 파일은 그대로 보존했다.
- 배포 검증: Compose의 health 대기 통과, frontend `healthy`·restart 0, 컨테이너 내부 및 외부 HTTPS `/api/health` 200·`status=ok`. 외부 홈페이지가 새 JS 자산을 참조하고 내려받은 자산에 `그룹 승인 중…`과 순차 판정 안내가 모두 있음을 확인했다. 최근 프런트 로그에 오류 없음. 승인 요청을 재실행하지 않았다.

## Issues found

- 전체 그룹 승인 실패는 관측되지 않았다. 순차 처리 중간 상태를 새로고침으로 읽었고, 진행 표시가 없어 멈춤으로 보인 것이 이번 증상의 원인이다.
- 패턴 스윕: `ReviewInbox.tsx:135`의 공통 액션, `WorkspaceReviewPanel.tsx:318`, `ReviewInboxDetail.tsx:141`도 요청 중 버튼 비활성화만 표시한다. `git blame`으로 기존 구현임을 확인했다. 개별 confirm/reject는 그룹처럼 AI 순차 판정을 하지 않으므로 이번 수정 범위에서 제외한다. 후보 수정·병합 등 느린 동작의 진행 안내는 별도 UX 부채로 남긴다.
- 이번 테스트 첫 실행은 소스 로딩 전에 구현이 반영돼 구현 전 실패 증거로 사용할 수 없다. 회귀 실효는 체크포인트 이후 변이로 확인한다.

## Decisions / User Decisions and Rationale

- 사용자는 배포 서버의 로그 조회를 허용했고, 조회된 10월 1일 오후 그룹 승인 요청이 신고한 요청임을 확인했다.
- 사용자는 수정한 진행 안내의 배포를 요청했다. frontend만 재빌드·교체하고 기존 서버 Compose 설정을 유지했다. 원격 저장소 push는 하지 않았다.
- 기존 문서 우선순위는 `docs/system-contract-sot.md`에 있다. 그룹의 단계별 반영·부분 실패·재시도 계약을 유지하고 대기 안내만 보완한다.
- 소규모 UI 결함 수정이므로 기록 가이드에 따라 CHANGELOG 마일스톤과 SoT 계약 버전은 추가하지 않는다.

## Next steps

- 다음 그룹 승인에서 대기 안내와 완료 결과를 사용자 브라우저로 확인한다. 실제 승인 데이터는 변경하지 않았다.
