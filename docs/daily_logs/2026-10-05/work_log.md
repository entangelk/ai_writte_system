# 2026-10-05 Work Log

## Goals
- 배포 환경의 그룹 승인 부분 실패가 정본에 안전하게 저장됐는지 조회하고, 수분 대기에 필요한 검토함 안내를 검토한다.

## Completed work
- 배포 서버에서 승인 진행 문서·후보·정본·검토 대기열·LLM 호출 감사·서비스 로그를 읽기 전용으로 대조했다. 서비스/계약 문서 우선순위는 `docs/system-contract-sot.md`의 문서 역할을 확인했다.
- 승인 패스는 12:51:28.962~12:53:11.911 KST(약 103초). 이름 교정으로 superseded된 원 후보 둘은 skipped, 교정 후 첫 후보는 confirmed 및 canonical v1 생성, 다음 후보는 InvalidJudgeResult로 failed였다. 화면 결과와 저장 문서가 일치한다.
- compare_judge 호출은 최초 40,213ms(출력 토큰 0), 보정 62,713ms(출력 토큰 5·parse_error)였다. 해당 시간대 gateway에 provider_unavailable 및 키 fallback 로그가 있다. 두 호출 시간이 패스 소요 대부분을 설명한다. 응답 본문·세부 파서 오류는 감사에 없어 마지막 형식 오류의 정확한 종류는 단정할 수 없다.
- 실패 후보는 이후 12:53:53 KST 개별 confirm됐으며 현재 confirmed이고 별도 canonical v1이 존재한다. 관찰 두 건이 보존됐지만 그룹의 단일 canonical로 수렴된 상태는 아니다. 승인 진행 문서는 당시 failed를 유지한다. 검토 대기열에 해당 후보 행은 없다.
- 배포 코드와 로컬 `frontend/src/review/ReviewInbox.tsx`에는 버튼 busy 표시와 그룹 내부 정적 대기 안내가 이미 있다. 경과 시간·수분 소요 설명·실시간 단계 진행 표시는 없다.
- 코드/배포/데이터 변경은 하지 않았다. 기록 파일만 수정했다.

## Issues found
- 기존 안내의 “잠시”는 실제 103초 대기와 맞지 않는다. 화면이 멈춘 것인지 AI를 기다리는지 구분하기 어렵다.
- 실패 결과가 예외명만 보여 준다. 완료된 반영 보존 여부와 실패한 AI 판정의 의미를 사용자 문장으로 안내할 필요가 있다.
- 개별 confirm 뒤에도 그룹 결과의 failed는 과거 패스 기록이다. 현재 후보 상태와 과거 결과를 구분하는 재동기화 안내가 후속 검토 대상이다.

## Decisions / User Decisions and Rationale
- 사용자 요청 범위는 처리 상태 확인 및 장시간 작업의 사용자 알림 검토다. UX 구현·서버 재시도·데이터 병합은 이번 요청에서 수행하지 않았다.
- 제안: 승인 시작부터 “AI가 후보를 정본과 비교 중이며 수분 걸릴 수 있습니다” 및 경과 시간을 페이지 수준 상태 영역에 표시한다. 장기 대기 문구와 완료/부분 실패 알림을 추가하고, 실패 시 이미 반영한 결과가 유지됨을 설명한다.
- 경과 시간은 진행률이 아니다. 후보별 완료 건수와 현재 판정/보정 단계는 서버 진행 조회 계약이 필요한 별도 범위이며, 프론트 타이머로 추정하지 않는다. 백그라운드 작업화·브라우저 알림은 이번 제안의 최소 범위 밖이다.

## Verification
- 배포 DB 및 서비스 로그 조회, 배포 compare adapter와 프론트 대기 안내 대조.
- 기록 변경에 `git diff --check`를 적용한다. 동작 변경이 없어 테스트 실행·변이 검증은 해당하지 않는다.

## Next steps
- 검토함 그룹 승인 대기/부분 실패 UX를 개선하고, 현재 후보 상태와 과거 승인 결과의 구분을 검토한다.
- 필요 시 provider 응답 형식 실패의 진단 정보와 fallback 대기 정책을 별도 조사한다.

## 그룹 승인 대기 UX 구현
- 사용자 결정: 제안한 수분 대기 안내·경과 시간·완료/부분 실패 설명을 구현한다. 서버 진행 조회·백그라운드 작업화·배포는 이번 수정 범위 밖이다.
- `frontend/src/review/ReviewInbox.tsx`: 승인 중 페이지 수준 상태 영역을 표시한다. 접힌 그룹에서도 수분 소요 설명과 경과 시간이 보이며, 60초 이후 응답 지연/판정 재시도 가능성을 안내한다. interval은 안내가 사라질 때 정리하고 다음 승인에는 시간을 초기화한다. 경과 시간을 실제 진행률로 제시하지 않는다.
- 완료된 패스는 완료 문구를, 부분 실패는 실패 건수와 반영된 내용의 보존을 안내한다. InvalidJudgeResult/ProviderError를 사람이 읽을 수 있는 설명과 함께 표시한다. 기존 결과 상자의 재조회 후 보존과 재시도 안내를 유지한다.
- `frontend/src/review/ReviewInbox.test.tsx`: 0초/59초/61초 경과·장기 대기 안내·그룹 접기·실패 후 종료·개별 승인 제외 및 완료/부분 실패 문구를 검증한다. 양방향 가드: 장시간 안내 누락과 일반 승인/완료 결과의 잘못된 실패 표시를 모두 잡는다.
- 패턴 검색: 그룹 승인 대기 안내는 ReviewInbox 한 곳이다. 기존 안내의 blame은 `e12cebd5`(2026-10-02)로, 순차 판정과 새로고침 주의 안내를 추가한 선례를 유지했다.
- 검증: 로컬 설치 의존성(Vitest 3.2.7/Vite 7.3.6)으로 검토함 25개 및 전체 프론트 42파일/502개 통과. `npm run build`의 TypeScript 검사 및 production build 통과. WritingPanel의 기존 act 경고는 있지만 테스트 실패는 없다. 테스트 작성 중 fake timer와 비동기 userEvent 조합이 timeout을 일으켜 해당 시간 검증의 클릭만 동기 fireEvent로 바꾼 뒤 정상 통과했다.
- 변경분을 `7b5f2f1`에 먼저 커밋하고, `git status --short`가 비어 있음을 실행으로 확인한 뒤 다음 변이를 수행했다. 매번 원본 바이트를 복원하고 git diff가 없음을 확인했다.

| 변이 diff | 위치 | 재실패 셀 |
|---|---|---|
| `elapsedSeconds >= 60` → `>= 600`(장기 대기 안내 지연) | `frontend/src/review/ReviewInbox.tsx:94` | `shows progress during group approval and clears it on failure, excluding individual approval` — 1 failed/24 skipped, 61초 장기 안내 누락 |
| `elapsedSeconds >= 60` → `>= 0`(즉시 장기 대기 안내) | 같은 위치 | 같은 셀 — 1 failed/24 skipped, 0초에 추가 status가 생겨 초기 상태 가드 재실패 |

- 배포·push는 수행하지 않았다. 과거 승인 결과와 이후 개별 승인 상태의 재동기화는 별도 후속 범위로 남긴다.
- 변이 복원 후 같은 focused 명령이 1 passed/24 skipped로 재통과했고, 기록 링크 대상 존재 및 `git diff --check`도 확인했다.
