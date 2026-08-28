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

---

## Session 3 — 관리자 상세 진입·편집 도구 가시성 보강

### Goals

- 관리자 사용자 목록에서 아이디 자체를 상세 진입점으로 만들고 목적을 함께 표시한다.
- 사용자 상세의 검색·프로젝트 목록과 계정 비활성화 액션 사이에 구획 간격을 둔다.
- 편집기 우측의 이어쓰기·분석·검토 탭을 축소 화면에서도 쉽게 찾고 누를 수 있게 한다.
- 제품 핵심 흐름이 안정되는 시점의 사용자 가이드 작성을 후속 작업으로 남긴다.

### Completed work

- 사용자 아이디와 `상세 보기 →`를 하나의 링크로 묶고 접근성 이름과 사용자별 상세 경로를 명시했다. 종전의 별도 상세 액션은 제거해 진입점 중복을 없앴다.
- 사용자 상세 화면에 전용 클래스 세 개를 부여하고 계정 액션 및 프로젝트 목록 위에 `--space-4` 간격을 적용했다.
- 우측 도구 독의 각 탭을 최소 `4.75rem × 3.5rem`, `--type-small`로 키웠다. 선택 탭은 accent 면과 반전 글자색, 비선택 탭은 hover/focus tint, 독은 패널 그림자로 구분한다.
- 사용자 가이드는 지금 바로 만들지 않고 도그푸드에서 핵심 흐름과 UI가 안정된 뒤 공개 전 작성하도록 `HANDOFF.md`의 다음 작업에 트리거를 명시했다.
- 서버 전용 설정과 비밀값 파일의 체크섬을 보존한 채 공개 배포의 프론트만 새 이미지로 교체했다. 컨테이너 health와 인터넷 경로의 HTML·API health가 모두 HTTP 200이고 새 JS/CSS 자산 해시가 일치함을 확인했다.

### Issues found

- 링크 안의 아이디와 보조 문구는 JSX 노드 경계에서 접근성 이름 공백이 보장되지 않았다. `aria-label`로 `아이디 상세 보기 →`를 명시해 화면과 보조기술 양쪽에서 목적을 고정했다.
- 기존 `typeScale.test.ts`는 독 탭을 `meta` 크기로 고정하고 있어 이번 가시성 요구와 충돌했다. 새 요구가 의도적인 크기 변경이므로 이관 계약을 `small`로 함께 갱신했다.
- 패턴 스윕 결과 같은 상세 링크나 별도 우측 독 구현은 추가로 없었다. 기존 독은 2026-08-26에 도입된 단일 구현이었다.

### Decisions

- 오너 결정: 관리자 목록에서는 별도 액션보다 사용자 아이디 자체를 상세 링크로 쓰고, `상세 보기` 라벨로 목적을 드러낸다.
- 오너 결정: 사용자 상세의 프로젝트 목록과 비활성화 액션은 바로 위 콘텐츠에 붙이지 않고 명시적 간격을 둔다.
- 오너 결정: 이어쓰기·분석·검토 독은 작은 화면 배율에서도 발견 가능한 충분한 크기와 선택 강조를 가져야 한다.
- 오너 결정: 제품이 어느 정도 완성되어 핵심 흐름과 UI가 안정되면 사용자 가이드를 작성한다.

### Mutation verification

모든 mutation은 체크포인트 커밋 `f025c8f`와 clean tree 위에서 적용하고 `apply_patch` 역편집으로 복원했다.

| # | 방향 | mutation | 파일 | 재실패한 셀 |
|---|---|---|---|---|
| M1 | over | 아이디 링크의 `상세 보기 →` 표시와 접근성 라벨 제거 | `admin/AdminConsole.tsx` | `AdminConsole > loads users, project metadata, and the deployment KPI`의 accessible-name 단정 |
| M2 | under | 상세 화면 액션·프로젝트 목록 공통 `margin-top` 규칙 제거 | `styles.css` | `관리 상세와 편집기 도구 독 배치 > separates account actions and the project list from the content above them` |
| M3 | over | 선택된 도구 탭의 accent 배경·반전 글자색 제거 | `styles.css` | `관리 상세와 편집기 도구 독 배치 > gives every fixed tool tab a large target and a visible selected state`의 selected 단정 |
| M4 | under | 도구 탭을 종전 작은 padding·`--type-meta`로 복귀 | `styles.css` | 위 셀의 최소 폭 단정 + `타이포 축 > keeps the migrated rules on the scale instead of raw literals` |
| M5 | under | 사용자별 상세 링크를 사용자 목록 경로로 축소 | `admin/AdminConsole.tsx` | `AdminConsole > loads users, project metadata, and the deployment KPI`의 href 단정 |

### Verification

- 수정 전 신규 회귀는 사용자 링크, 상세 전용 클래스, 간격 규칙, 도구 독 크기·선택 강조의 결손을 재현해 실패했다.
- 집중 회귀: 3파일 **19/19**.
- 프론트 전수: 34파일 **381/381**.
- `npm run build`: TypeScript clean, Vite **711 modules**, 진입 **435.89 kB**, CSS **38.01 kB**.
- 패턴 스윕과 5종 mutation 뒤 working tree가 체크포인트와 byte-identical한 clean 상태임을 확인했다.
- 공개 배포: 프론트 컨테이너 healthy, 인터넷 HTML·API health **HTTP 200**, 서빙 자산 해시가 로컬 빌드와 일치했다.

### Next steps

- 공개 환경에서 사용자 아이디 링크, 상세 화면 간격, 우측 도구 독의 실제 크기와 열림 동작을 육안 확인한다.
- 도그푸드 핵심 흐름과 UI가 안정되면 공개 전에 사용자 가이드를 작성한다.

---

## Session 4 — 편집 도구 드로어 내부 전환과 선택 상태 유지

### Goals

- 열린 드로어 안에서 닫았다 다시 열지 않고 이어쓰기·분석·검토를 바로 전환한다.
- 드로어를 닫아도 마지막으로 본 탭과 우측 독의 활성 표시를 일치시킨다.
- 우측 독을 한 단계 더 키워 축소 화면에서도 충분히 눈에 띄게 한다.
- 다음 UI 작업은 텍스트+화살표 링크 가시성 개선, 그다음은 메모 기능 순서로 남긴다.

### Completed work

- 드로어 머리글을 세 칸 탭 목록으로 바꿨다. 각 탭은 드로어를 유지한 채 기존 마운트된 레이어를 전환하고, 이어쓰기 완료 배지도 같은 상태를 표시한다.
- URL의 `panel`은 열린 상태를 정하고 별도 `lastPanel` 상태가 마지막 선택을 보존하게 분리했다. 닫을 때 쿼리는 제거하되 활성 탭은 유지해 우측 독 표시가 이어쓰기로 되돌아가지 않는다.
- 드로어가 열린 동안 뒤에 가려진 우측 독은 `aria-hidden`으로 접근성 트리에서 제외해 같은 이름의 탭 두 벌이 동시에 포커스되지 않게 했다.
- 우측 독 탭을 최소 `5.5rem × 4.25rem`, `--type-base`로 확대했다. 드로어 상단 탭도 최소 높이 `3.25rem`과 선택 accent·hover/focus 처리를 적용했다.
- 서버 전용 설정을 보존한 채 공개 환경의 프론트 이미지만 교체하고, 새 JS/CSS 자산이 인터넷 경로까지 전달된 것을 확인했다.

### Issues found

- 종전에는 `activePanel`을 쿼리에서만 계산해 `panel` 제거가 곧 `writing` 복귀였다. 드로어 열림 상태와 선택 상태를 같은 값으로 표현한 것이 원인이었다.
- 첫 전체 회귀에서 존재하지 않는 `--type-body`, `--border-strong` 참조를 디자인 토큰 가드가 잡았다. 정의된 `--type-base`, `--border-control`로 교체하고 전수를 다시 통과시켰다.
- 패턴 스윕 결과 패널 선택 상태 계산과 독·드로어 탭 구현은 `DraftEditor` 한 곳뿐이었다. 2026-07-18의 쿼리 기반 선택 위에 2026-08-26 드로어가 추가된 구조였다.

### Decisions

- 오너 결정: 열린 드로어 상단에도 이어쓰기·분석·검토 탭을 두고 닫기 없이 상호 전환한다.
- 오너 결정: 닫힌 우측 독의 활성 표시는 마지막 드로어 탭 선택과 연동한다.
- 오너 결정: 우측 독은 기존 확대치보다 한 단계 더 크게 만든다.
- 오너 결정: 후속 순서는 텍스트+화살표 링크 가시성 개선이 먼저이고 메모 기능은 그다음이다.

### Mutation verification

모든 mutation은 체크포인트 커밋 `ca1a833`과 clean tree 위에서 적용하고 `apply_patch` 역편집으로 복원했다.

| # | 방향 | mutation | 파일 | 재실패한 셀 |
|---|---|---|---|---|
| M1 | under | 드로어 상단 탭 목록의 식별 이름을 일반 패널 이름으로 축소 | `drafts/DraftEditor.tsx` | `DraftEditor > switches panels from the drawer header and keeps the last tab selected after close`의 tablist 단정 |
| M2 | under | 쿼리 제거 시 마지막 탭 대신 항상 `writing`을 활성화 | `drafts/DraftEditor.tsx` | 위 셀의 닫힘 후 `분석` 선택 단정 |
| M3 | over | 드로어 상단 탭의 클릭을 no-op으로 변경 | `drafts/DraftEditor.tsx` | 위 셀의 분석 패널 전환 단정 |
| M4 | under | 우측 독을 직전 `4.75rem × 3.5rem`, `--type-small`로 축소 | `styles.css` | `관리 상세와 편집기 도구 독 배치 > gives every fixed tool tab…` + `타이포 축 > keeps the migrated rules…` |

### Verification

- 수정 전 신규 회귀는 드로어 상단 탭 부재와 닫힘 후 `writing` 복귀를 재현해 실패했다.
- 집중 회귀: 4파일 **68/68**.
- 프론트 전수: 34파일 **382/382**.
- `npm run build`: TypeScript clean, Vite **711 modules**, 진입 **436.28 kB**, CSS **38.66 kB**.
- 패턴 스윕과 4종 mutation 뒤 working tree가 체크포인트와 byte-identical한 clean 상태임을 확인했다.
- 공개 배포: 프론트 healthy, 인터넷 HTML·API health **HTTP 200**, 서빙 자산 해시가 로컬 빌드와 일치했다.

### Next steps

- 텍스트와 화살표만 있는 이동 링크를 전수 확인해, 주요 이동은 버튼형으로 만들고 보조 이동은 일관된 강조를 주는 UI 슬라이스를 진행한다.
- 링크 가시성 개선 뒤 메모 기능의 위치·저장 단위·공개 범위를 결정하는 오너 브리프를 작성한다.
- 공개 환경에 이번 프론트 빌드를 반영한 뒤 열린 드로어 탭 전환과 닫힘 후 선택 유지, 확대된 독을 육안 확인한다.
