# Work Log — 2026-08-28

## Goals

- 공개 배포 환경을 현재 `main` 기준으로 갱신하고 인터넷 경로에서 응답을 확인한다.
- 공개 저장소 문서에 원격 서버 접속·토폴로지 상세를 남기지 않는 기록 원칙을 명문화한다.

## Completed work

### 공개 배포 갱신

- 배포 환경의 서버 전용 설정과 비밀값 파일이 변경되지 않았음을 확인한 뒤 현재 `main`으로 소스를 정렬했다.
- 전체 서비스 이미지를 다시 빌드하고 기존 영속 저장소는 유지한 채 애플리케이션·관리자·게이트웨이·워커·프론트를 교체했다.
- 내부 health와 인터넷 경로의 공개 페이지·API health가 모두 HTTP 200임을 확인했다.
- 공개 응답이 이번 빌드의 새 프론트 자산을 참조하는 것을 확인했다.

### 공개 저장소 기록 보안 규칙

- `HANDOFF.md` 상단에 원격 배포 대상의 접속 정보·서버 내부 경로·구체 토폴로지·비밀값을 저장소 문서에 기록하지 않는 규칙을 추가했다.
- 이후 배포 기록은 역할 별칭과 민감정보를 제거한 결과만 남기며, 실제 접속 정보는 저장소 밖에서 관리한다.

## Issues found

- 서비스 기동 로그에 외부 라이브러리 telemetry 전송 경고가 보였으나 애플리케이션·워커 동작과 health에는 영향이 없었다. 이번 배포 범위에서는 수정하지 않았다.
- 공개 저장소가 된 뒤에도 원격 운영 상세를 기록에서 제외한다는 규칙이 HANDOFF 상단에 없었다. 오너 지시에 따라 명시해 재발 가능성을 낮췄다.

## Decisions

- 오너 결정: 공개 저장소의 `HANDOFF.md`, 일일 작업 로그, 검증 기록, 변경 로그 등에 원격 서버의 직접적이고 자세한 정보를 남기지 않는다.
- 배포 성공 증거는 커밋·서비스 상태·HTTP 결과처럼 재현에 필요한 최소 정보만 기록하고 접속 방법과 물리 환경 상세는 기록하지 않는다.

## Next steps

- 오너가 공개 사이트에서 신버전 UI를 육안 대조한다.
- 편집기 드로어·설정 탭·좁은 화면 배치에서 발견되는 문제를 별도 결함으로 기록한다.

---

## Session 2 — 도그푸드 UI 배치 결함 3건

### Goals

- 관리자에서 사용자별 상세·프로젝트 목록으로 들어가는 경로를 명확히 한다.
- 원고 단위 설명과 라벨의 폭·상하 정렬을 바로잡는다.
- 편집기 도구 독·드로어를 편집 영역이 아니라 뷰포트 오른쪽에 고정한다.

### Completed work

- 관리자 사용자 상세 화면은 이미 `/admin/users/:userId`에 존재하고 사용자 소유 프로젝트를 필터링하고 있었다. 새 화면을 중복 생성하지 않고 작은 `상세` 진입 문구를 `사용자 상세 보기 →`로 바꿔 발견성을 높였다.
- `.unit-kind-help`의 `max-width: 46rem`을 제거해 생성 폼 두 열 전체 폭을 사용하게 했다. `원고 단위` 라벨을 명시적 `.unit-kind-label`로 두고 `.form-controls`의 유일한 `align-items`를 `center`로 고정했다. 좁은 화면의 `stretch` 재정의도 제거했다.
- 편집기 독·드로어 자체는 이미 `position: fixed; right: 0`이었다. 문제는 조상 `.page-enter`가 애니메이션 종료 뒤 `transform: translateY(0)`을 유지해 fixed containing block을 뷰포트에서 편집기 박스로 바꾼 것이었다. 편집기 뿌리에서 `page-enter`만 제거하고 `workspace-page editor-page` 소속은 보존했다.

### Issues found

- `sr-only` 클래스는 저장소 CSS에 정의가 없어 라벨을 숨기지 못하고 있었다. 오너가 노출 라벨의 중앙정렬을 요구했으므로 새 숨김 유틸리티를 만들지 않고 실제 보이는 라벨로 정리했다.
- `position: fixed` 값만 읽으면 올바르게 보이지만 조상 transform까지 함께 보지 않으면 실제 containing block을 오판한다. 패턴 스윕 결과 fixed 표면은 편집기 독·드로어 두 곳뿐이어서 동일 결함의 추가 위치는 없었다(`git blame`: 독·드로어는 08-26 도입, page-enter는 07-16 선행).

### Decisions

- 기존 사용자 상세 페이지와 API를 재사용하며 새 operation·route는 만들지 않는다.
- 전체 페이지 진입 애니메이션을 전역 변경하지 않고 fixed 표면을 가진 편집기에서만 제외한다.
- 원고 단위 설명은 별도 좁은 읽기 폭을 두지 않고 생성 폼 전폭을 사용한다.

### Mutation verification

모든 mutation은 체크포인트 커밋 `b4e1a0d`와 clean tree 위에서 적용하고 `apply_patch` 역편집으로 복원했다.

| # | 방향 | mutation | 파일 | 재실패한 셀 |
|---|---|---|---|---|
| M1 | under | `사용자 상세 보기 →`를 작은 `상세`로 복귀 | `admin/AdminConsole.tsx` | `AdminConsole > loads users, project metadata, and the deployment KPI` |
| M2 | over | 상세 링크 목적지를 `/admin`으로 축소 | `admin/AdminConsole.tsx` | 위 셀의 href 단정 |
| M3 | under | 설명 폭 `max-width: 46rem` 복귀 | `styles.css` | `원고 생성 폼 배치 > centers the unit label…` |
| M4 | over | 설명의 `grid-column: 1 / -1` 제거 | `styles.css` | 위 셀의 전폭 단정 |
| M5 | over | 보이는 `.unit-kind-label`을 `sr-only`로 복귀 | `drafts/DraftList.tsx` | `DraftList > defaults the unit to 장…` |
| M6 | under | 편집기 뿌리에 `page-enter` 재부착 | `drafts/DraftEditor.tsx` | `DraftEditor > roots the fixed tool dock at the viewport…` |
| M7 | over | 애니메이션 제거와 함께 `editor-page`까지 제거 | `drafts/DraftEditor.tsx` | 위 셀의 페이지 소속 단정 |

### Verification

- 수정 전 신규 회귀 4개가 각 원인을 재현해 실패했다.
- 집중 회귀: 5파일 **82/82**.
- 프론트 전수: 34파일 **379/379**.
- `npm run build`: TypeScript clean, Vite **711 modules**, 진입 **435.89 kB**, CSS **37.32 kB**.
- 패턴 스윕과 7종 mutation 뒤 working tree가 체크포인트와 byte-identical한 clean 상태임을 확인했다.

### Next steps

- 공개 배포를 갱신한 뒤 관리자 상세 진입, 원고 단위 폼, 편집기 우측 독·드로어를 브라우저에서 다시 육안 확인한다.
