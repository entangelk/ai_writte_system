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

## 같은 장의 다음 장면 이어쓰기 조사
- 목표/사용자 요청: 배포에서 다음 장면 이어쓰기가 복사 결과만 보여 주고 새 Scene이나 생성 버튼이 없는 원인을 확인한다.
- 읽기 전용 결과: 12:56:03 KST 생성 요청은 `intent=start_next_unit`, 다음 장면 제목/목표를 포함했고 202를 반환했다. worker는 13:00:40에 succeeded로 종료했으며, scratch에 생성 본문 1,415자와 intent/제목/목표가 보존돼 있다. 해당 시간대 로그에 writing accept나 새 Scene 생성 요청은 없고, 프로젝트의 accept receipt도 0건이다. DB의 Scene 목록은 기존 두 개 그대로다. 생성 실패나 내용 유실이 아니다.
- 원인: `frontend/src/writing/WritingPanel.tsx:821`의 후보 액션은 본문 복사만 제공한다. `f66d6563`의 blame 및 2026-09-08 work_log 세션 46/SoT v1.8.49는 사용자 결정 “채택 버튼 제거, 통로만 유지”를 명시한다. 같은 패턴은 `ScratchRecovery.tsx`의 복구 패드에도 적용됐다.
- 계약 대조: `docs/plans/chapter-scene-hierarchy-decisions.md` D6=A는 accept를 통한 같은 Chapter의 다음 Scene 생성을 정의한다. 이 경로는 `services/application/app/writing/accept.py`에서 유지되지만 화면에서 호출하지 않는다. 다음 장면 제목/목표 입력은 생성 의도로 전송될 뿐 생성 endpoint가 Scene을 만들지는 않는다. 기존 회귀도 채택 버튼 부재와 복사 버튼을 명시적으로 잠근다.
- 문제/효과: “같은 장의 다음 장면 시작”이라는 화면 표현과 자동 Scene 생성에 대한 사용자의 기대가 현재 복사 전용 흐름과 맞지 않는다. 다음 Scene 생성 UI가 빠진 상태다.
- 제안(미결정): 채택 API 복구 대신 별도 “이 내용으로 다음 장면 만들기” 동작으로 같은 Chapter에 Scene을 만들고 생성문을 편집 가능한 초안으로 열어, 사용자가 일반 저장하도록 하는 흐름을 검토한다. 기존 채택 버튼 제거 방향을 보존하면서 누락된 장면 이동 동작을 채울 수 있다. 생성 즉시 자동 저장/유료 accept 재도입은 결정하지 않았다.
- 변경/검증: 서버 및 코드 변경 없이 DB·access log·worker log·코드·기존 결정/회귀를 대조했다. 기록 파일만 변경했고 관련 참조 및 `git diff --check`를 확인한다. 새 테스트 실행은 동작 변경이 없어 해당하지 않는다.
- 다음 단계: 다음 Scene을 만드는 시점과 생성문을 초안/저장 중 어느 상태로 여는지 사용자 방향을 정한 뒤 구현한다. 이미 저장된 scratch 후보로 이어갈 수 있으며 재생성을 전제하지 않는다.

## 다음 Scene 초안 열기 구현
- 사용자 결정/근거: 진단 후 제안한 “이 내용으로 다음 장면 만들기 → 같은 Chapter의 새 Scene → 생성문을 편집 초안으로 열기 → 사용자가 일반 저장” 흐름을 승인했다. 2026-09-08의 채택 버튼 제거는 유지한다. `chapter-scene-hierarchy-decisions.md`에 승인 방향을 반영하고 SoT v1.8.79를 기록했다.
- 구현 파일: `WritingPanel.tsx`·`ScratchRecovery.tsx`에 결과 자체의 intent/title/text를 사용하는 버튼을 추가했다. 현재 폼을 바꿔도 과거 결과의 대상이 바뀌지 않으며 append/legacy 결과에는 버튼을 붙이지 않는다. `NextSceneButton.tsx`는 두 표면의 요청 중 잠금·실패 시 인접 오류·재시도를 공유한다.
- `DraftEditor.tsx`: 기존 createDraft/listDrafts/putSceneOrder로 새 Scene을 같은 Chapter의 현재 Scene 바로 뒤에 둔다. 생성 후 순서 실패는 request별 생성 Scene을 기억해 재시도에서 새 Scene을 중복 생성하지 않는다. live/scratch의 동시 클릭은 부모 잠금으로 공유한다. 원본 dirty 이동 확인, 생성 중 본문 편집/저장 잠금과 원본 보관 제한을 적용한다.
- 편집기 이동 state는 대상 Draft ID와 본문을 함께 싣고, 대상에 version이 없을 때만 미저장 초안으로 읽는다. 저장된 version이 있으면 canonical 본문이 우선한다. route별 패널 key로 이전 Scene의 후보가 새 Scene에 남지 않게 한다. 기존 scratch는 보존한다.
- 공개 API/OpenAPI 및 backend 코드는 변경하지 않았다. Scene 생성 응답 유실 및 새로고침을 넘는 생성 멱등은 기존 API의 한계이고, 새로운 원자 endpoint는 이번 범위 밖이다. 배포·push는 요청 범위 밖이다.
- 회귀: 동기 후보·복구 후보의 버튼, append/legacy 제외, dirty 이동 취소, 같은 Chapter 바로 뒤 배치, 순서 실패 뒤 단일 create, 미저장·편집 가능·일반 저장, 저장된 version 우선, 중복 클릭·오류 복구·읽기 전용을 잠근다. 변경 행동의 회귀를 먼저 작성한 뒤 구현했고, 최초 순서 실패 테스트의 문자열은 실제 `503: ...` 오류 표시 형식에 맞춰 role=alert 검증으로 정정했다.
- 검증: focused 3파일/132 passed, 전체 프론트 43파일/510 passed(기존 502 대비 회귀 8개), `npm run build` TypeScript clean/723 modules 및 `git diff --check` 통과. 로컬 설치 의존성은 Vitest 3.2.7/Vite 7.3.6이다. 새 공개 API가 없어 `schema.d.ts`/OpenAPI diff는 0이고 기존 예제·literal은 유지한다.
- 패턴 sweep: 후보 동작은 live/scratch 두 표면이며 둘 다 연결했다. blame은 `f66d6563`의 의도된 채택 제거였다. 편집기 기본 로딩 `setRawText(nextText)`는 `3c176a12`의 정본 로딩 선례이므로 저장된 version을 유지하면서 빈 Scene에만 seed를 적용했다. 발견된 다른 동일 원인의 미연결 표면은 없다.
- 핵심 변이 검증은 아래에 기록한다.

### 다음 Scene 회귀 가드 변이

- `9ac6410` checkpoint 이후 `git status --short` 공백을 실행 확인했다. 각 변이 후 원본 바이트를 복원하고 `git diff --exit-code`로 clean 복원을 확인했다. 명령은 `npm test -- --run src/drafts/DraftEditor.test.tsx -t 'creates the next scene|never replaces'`다.

| 변이 diff | 위치 | 재실패 셀 |
|---|---|---|
| `setRawText(initialText ?? nextText)` → `setRawText(nextText)` | `frontend/src/drafts/DraftEditor.tsx:184` | `creates the next scene as an unsaved editable draft, with reorder retry=false` 및 `...retry=true` — 2 failed/1 passed/65 skipped |
| seed 조건의 `latest === null &&` 제거 | `frontend/src/drafts/DraftEditor.tsx:182` | `never replaces a saved version with next-scene navigation text` — 1 failed/2 passed/65 skipped |
| `let target = nextScenesRef.current.get(key)` → `let target: Draft \| undefined`(생성 Scene 재사용 제거) | `frontend/src/drafts/DraftEditor.tsx:256` | `creates the next scene as an unsaved editable draft, with reorder retry=true` — 1 failed/2 passed/65 skipped |

- 배포·push 없이 로컬 main에 구현을 커밋했다. 배포 후 기존 scratch에서도 버튼을 사용할 수 있으므로 재생성은 필요 없다.
- 원본 복원 뒤 같은 focused 명령이 3 passed/65 skipped로 재통과했다.
- 후속 검수에서 Scene 생성 대기 중 기존 version을 여는 경로도 잠갔다. 대기 중 version 조회가 늦게 끝나면 새 Scene 초안을 덮을 수 있으므로 `selectVersion`과 새 Scene 만들기를 상호 잠그고 버전 버튼을 disabled 처리했다. 생성 요청을 지연하는 회귀로 본문 읽기 전용·version 버튼 잠금·추가 version 조회 없음도 확인한다. 해당 변경 뒤 DraftEditor 68개 및 production build를 재검했다.

## 사용자 승인 배포
- 사용자 결정/제약: 그룹 승인 대기 안내와 다음 Scene 초안 열기의 배포를 승인했다. 배포 환경 접속 정보·식별 정보·내부 경로·구체 구성을 저장소 기록에 남기지 않는다. 이 기록은 변경 범위와 민감정보를 제거한 검증 결과만 다룬다.
- 검증한 커밋을 전달하고 프론트만 다시 빌드·교체했다. 이전 이미지는 복구용으로 보관했다. 기존 미추적 사용자 파일은 보존했으며 Git push는 수행하지 않았다. backend 코드·DB 마이그레이션은 변경 범위에 없다.
- 배포 검증: TypeScript/production build 통과, 프론트 health 정상, nginx 설정 검사 통과, 홈/SPA 경로 HTTP 200, API의 익명 접근 HTTP 401. 실제 제공된 JS가 로컬 검증 빌드와 바이트 해시 일치하며 다음 Scene 버튼·미저장 초안 안내·그룹 경과 시간·반영 보존 문구가 포함됨을 확인했다. application/gateway health도 정상이다.
- 실제 사용자 원고를 만드는 검증 요청은 보내지 않았다. Scene 생성·순서·미저장 본문·일반 저장은 앞선 회귀에서 검증했고, 기존 저장된 생성 결과는 화면 새로고침 후 새 버튼으로 사용할 수 있다.
- 변경 파일: 이 작업 로그와 HANDOFF의 화면 새로고침 주의. 기록에 접속 정보나 환경 내부 경로를 추가하지 않았고, `git diff --check`와 참조 확인 후 커밋한다.
