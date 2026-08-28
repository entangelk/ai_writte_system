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

## Session 5 — 주 버튼 hover 가시성 · 삭제 기능 현황 조사

### Goals

- 관리 콘솔 "작업장으로 이동" 버튼이 hover 반응으로 보이지 않는 결함(오너 관측)을 고친다.
- 프로젝트·원고 삭제 기능의 현황을 정리하고, 원고 삭제 추가 시 분석 축·DB id 참조에
  문제가 되는 축을 식별해 오너 결정 재료로 올린다(구현은 별도 슬라이스).

### Completed work

- `--action-primary-hover` 를 blue-700 → **blue-800** 으로(램프 두 단계). 한 단계는 본색과
  실효 대비 ~1.4:1 이라 hover 피드백이 아니었다. admin ghost 버튼 글자색이 같은 토큰을
  공유하므로 같이 진해진다(대비 개선 방향).
- 검산 스크립트 2종을 실제 매핑에 맞춰 갱신 후 재실행 — 팔레트 대비 **실패 0건**,
  disabled 표 참조값 갱신. `designTokens.test.ts` 에 **hover-base 램프 두 단계 가드**
  신설(under: 한 단계 복귀 시 재실패 확인, mutation 검증 완료).

### Issues found

- **원고 아카이브(`DELETE .../drafts/{draft_id}`)는 이미 있다** — 색인 제거(outbox
  `DRAFT_ARCHIVED` → chroma `{"draft_id"}` 파기)까지 붙어 있다. 그런데 **프론트에 호출
  함수 자체가 없다**(`api/client.ts` 에 원고·프로젝트 archive 함수 부재) — "삭제 기능이
  없다"는 관측의 실체.
- **프로젝트 아카이브 UI 가 없어 admin purge 도달 경로가 막혀 있다** — 관리 콘솔 purge
  면(이름 확인+사유)은 `project.archived` 일 때만 노출되는데, 그 상태로 만드는 진입점이
  화면 어디에도 없다.
- **원고 영구 삭제(하드 딜리트)는 백엔드에도 없다** — core_sot 에 draft 단위 삭제
  메서드가 없다(`purge_project` 뿐).

### 삭제 기능 현황·영향 조사 (오너 질의: 분석·DB id 접근)

**이미 안전한 축 — 원고를 직접 참조하지 않는다:**

- **분석(analysis)**: 잡·후보·리뷰 큐의 축이 전부 `project_id + snapshot_id`(자료 스냅샷
  축)이다. draft 를 키/id 로 쓰는 곳이 없어 원고 삭제로 고아가 생기지 않는다.
- **memory**: 후보 승격 기반(project 스코프) — draft 참조 없음.
- **gate_findings**: 저장은 project 단위 열린 finding. 요청 순간 위치로만 `draft_id`를
  쓰고 남기지 않는다.
- **ES(lexical) 색인**: 원고는 아예 안 들어간다(자료·후보·기억 축만). 원고 벡터는
  chroma뿐이고 그 제거 파이프라인이 위의 `DRAFT_ARCHIVED` 다.

**원고 삭제 시 손봐야 할 축:**

1. `drafts`·`draft_versions`·저장요청(멱등)·수령영수증 — 삭제 본체. 메서드 신설 필요.
2. **chroma 색인** — 아카이브를 선행시키면 제거 파이프라인 재사용(프로젝트 purge 의
   "archive 선행" 패턴과 같은 모양).
3. **generation_job** — `draft_id` 를 저장한다. 진행 중 잡이 있으면 거부(409)하는 편이
   purge 철학과 일치한다. 완료 경로는 scratch 저장뿐이라 깨지진 않는다.
4. **scratch** — `delete_for_draft` 가 이미 있다. 호출만 하면 된다.
5. **activity** — append-only 원장이라 draft 행(`target_id`)이 남는다. **죽은 id 문제의
   실체는 여기뿐**이다. draft 행은 현재 링크형이므로 무링크 처리(draft_version 행의
   F7 과 같은 방식)가 필요하다. 행 파기는 append-only 위반이라 부적합.
6. id 재사용 우려는 없다 — `next_draft_id` 시퀀스라 삭제된 id 로 재발급되지 않는다.

**결론**: 오너가 우려한 "분석·DB id 접근" 축에는 구조적 충돌이 없다. 실제 과제는
activity 무링크 처리와 잡·스크래치 정리다.

### Verification

- 프론트 전수 34파일 **382/382** (hover 변경 후). 검산 스크립트 2종 PASS.
- Mutation: hover 를 blue-700 로 되돌리면 신규 가드 셀 재실패 → 복원 → tree clean 확인.

### Next steps

- 원고 삭제 슬라이스 착수 시: 아카이브 선행 → 하드 삭제 + scratch `delete_for_draft`
  → activity 무링크 처리 순서. active 잡 존재 시 409 를 명세에 넣을지 오너 결정.
- 프로젝트 아카이브 진입점(작업장 설정? 관리 콘솔?)을 정해 UI 를 열어야 purge 도달
  경로가 산다 — 오너 결정 필요.

## Session 6 — 삭제 기능 슬라이스: 원고 하드 삭제·소유자 프로젝트 purge·관리자 아카이브

### Goals

오너 결정(세션 5 보고에 대한 지시): ① active 생성 잡이 붙은 원고의 purge 는 409
② 삭제 진입점 — 사용자는 설정 탭, 관리자는 관리 콘솔 ③ 프로젝트 삭제는 설정 탭
버튼 + **이름 입력 가드 팝업** ④ 원고·장 삭제는 **체크박스 가드**. 장(유닛) 삭제는
장 편집 UI·unit_kind 존치 결정이 먼저라 **별도 슬라이스로 유예**(오너 선택).

### Completed work

- **원고 하드 삭제** `POST /projects/{pid}/drafts/{did}/purge`(소유자): core_sot
  6컬렉션(drafts·versions·snapshots·blocks·source_refs·receipts)을 draft 스코프로
  파기(인메모리+몽고, 몽고는 트랜잭션 경로 포함). 아카이브 선행 409 · active 생성
  잡 409 · scratch `clear_draft` · activity 는 append-only 원장에 `draft_purged` 행.
- **소유자 프로젝트 purge** `POST /projects/{pid}/purge`: admin purge 의 파괴 그래프를
  `execute_project_purge`(routers/admin.py)로 **한 벌로 공유** — 두 벌이 되면 어느
  한쪽만 새 서비스를 받아 조용한 고아가 된다(D5). 감사·이름 이력·outbox 도 같은 원장.
- **관리자 아카이브** `POST /admin/projects/{pid}/archive`: purge 진입 도달 경로
  보강(보관으로 만드는 화면 경로가 없어 purge 가 구조적으로 막혀 있었다). I3 에
  따라 활동 행은 남기지 않는다(관리자 축).
- **프론트**: 설정 탭 삭제 섹션(이름 확인 → archive→purge 순차 → 목록 복귀) ·
  원고 목록 행 삭제 버튼 + 체크박스 확인 패널 · 관리 콘솔 카드 "보관으로 전환" ·
  활동 타임라인의 죽은 draft 행 무링크(F7 과 같은 처방).

### Decisions

| # | 결정 | 근거 |
|---|---|---|
| D1 | active 생성 잡 존재 시 원고 purge 409 | 오너 세션 지시 — 잡의 결과물은 draft 에 표시되므로 앵커가 사라진 잡은 완료돼도 갈 곳이 없다 |
| D2 | 진입점 이원 — 사용자=설정 탭(이름 가드), 관리자=관리 콘솔 | 오너 세션 지시 |
| D3 | 소유자 purge 의 reason 을 화면에서 묻지 않고 "설정 탭에서 소유자 삭제"로 채운다 | 이름 확인이 진짜 가드(오너 지시). 감사 원장엔 그대로 남는다 |
| D4 | 장(유닛) 삭제는 별도 슬라이스 유예 | 장을 다루는 UI/API 가 없어 설계부터 필요 + unit_kind 존치(D6 유예)와 얽힘 |

### Issues found

- 소유자 purge/admin 아카이브가 activity 분류표에 등재돼 있지 않으면 전수가 잡는다
  — 분류표는 배선과 같은 정본이다(수습: EXCLUDED 2건 등재, 관리자 아카이브의
  activity 행 제거로 I3 정합).

### Verification

- 백엔드 전수 **2544 passed, 4 skipped**(mongo 통합 포함 — test-mongo 기동 후
  `test_core_sot_mongo` 79/79).
- 프론트 전수 **386/386** · `tsc --noEmit` clean · `vite build` OK.

### Mutation verification (정정 — 독립 검증 지적)

종전 이 자리에 *"Mutation 4종"* 을 서술로 적었는데 **실제 구현자 mutation은 3종**이고
나열도 없었다(검증 B6③). 표로 정정한다 — 이름 가드 무력화는 구현자가 돌리지 않았고
독립 검증(F3)이 물었으므로 이 표에 넣지 않는다.

| # | 방향 | mutation | 파일 | 재실패한 셀 |
|---|---|---|---|---|
| M1 | under | hover 토큰을 blue-700(한 단계)로 되돌림 | `frontend/src/styles.css` | `designTokens > keeps the primary hover at least two ramp steps from its base` |
| M2 | under | 원고 삭제 확인의 `!purgeChecked` 조건 제거 | `frontend/src/drafts/DraftList.tsx` | `DraftList > permanently deletes a draft behind a checkbox confirmation`의 비활성 단정 |
| M3 | under | 타임라인의 `draftIds ?? undefined` → `undefined` | `frontend/src/projects/ActivityTimelinePage.tsx` | `ActivityTimelinePage > does not link a draft row whose draft no longer exists` |

### Next steps

- 장(유닛) 삭제 슬라이스 — unit_kind 존치 결정(D6)과 함께 오너 브리프 필요.
- 배포 환경 반영(기록은 보안 규칙에 따라 생략).

## Session 7 — 독립 검증 조건부 합격 보강 (B1~B6 + H1)

### Goals

검증 기록 [`deletion_slice.md`](../verifications/2026-08-28/deletion_slice.md)(조건부 합격)의
Blocking 6건을 닫는다. B5(소유자 면 503 재시도)는 오너 결정 **ⓐ 단계 구분+uncertain 잠금**,
나머지 5건은 셀·문서 등재로 기계적으로 폐쇄.

### Completed work

- **B2** — receipts 축 셀: 인메모리(`test_draft_purge` victim 소거+sibling 생존 양방향)
  ·mongo(`test_core_sot_mongo` purge_draft 셀에 동일 양방향). receipt 쓰기 경로는 accept
  트랜잭션 안에만 있어 repo/컬렉션에 직접 주입(소거 축을 재는 자리).
- **B3** — 종료 잡 should-not-fire 셀: SUCCEEDED 잡이 붙은 archived 원고 purge → 204.
  가드가 네 상태 전부로 확장되면 이 셀이 물린다.
- **B4** — Crud 에러 계약 EXPECTED에 제품 purge 2경로 추가(**20→22핀**).
- **B5(오너 ⓐ)** — 설정탭 삭제 버튼 단계 구분: 보관 단계 실패(파괴 없음)는 버튼 되살림,
  파기 단계 503은 **uncertain 잠금**(재시도 버튼 제거·취소/입력 잠금·"reconciler 확인"
  안내 — 관리자 면과 같은 문구), 재파기 404는 성공 처리. 셀 2종(uncertain/보관-실패).
- **H1** — draft purge에서 scratch 정리를 core 파기 **앞**으로(파생물 우선 — scratch 단계
  실패 시 원고가 남아 재시도로 수습).
- **B1** — SoT **v1.8.8** 등재: Product Shell에 삭제 표면 3축 계약 추가(409 조건 2종·
  6컬렉션·reason 리터럴·I3 무행·503 양면 대칭), 운용 수(총 91·tier 65·활동 21/23·
  admin 17·Crud 22핀), 변경 이력 행.
- **B6** — CHANGELOG 2026-08-28 삭제 슬라이스 항목 · HANDOFF(op 수 76→91·회귀 기준선
  2544·Next Tasks 마감 메모·분량 기록) · work_log 세션 6 mutation 표 교체(4종 주장→
  실제 3종, 셀 매핑 명기).
- **보고 정정** — 완료 보고 "커밋 10개"는 실제 슬라이스 8개(검증 메타데이터 지적).

### Decisions

| # | 결정 | 근거 |
|---|---|---|
| D5 | B5 = ⓐ 단계 구분 + uncertain 잠금 | 오너 선택(2026-08-28) — D4=A "503 후 UI 재시도 금지"를 소유자 경로까지 대칭 적용. 보관 단계(파괴 없음)만 재시도 허용 |

### Verification

- 집중: `test_draft_purge` 9셀 · `test_owner_project_purge` 7셀 · `test_core_sot_mongo`
  79/79(receipt 단정 포함) · `test_application_api` 전수 · `ProjectSettingsPage` 7셀.
- 보강 mutation 4종 — 검증이 뚫은 무셀 방향 그대로 되돌려 **전부 물림**을 확인:

| # | 방향 | mutation | 재실패한 셀 |
|---|---|---|---|
| R1 | under(B2) | 인메모리 receipt 재구성 제거 | `test_purge_removes_accept_receipts_and_keeps_siblings` |
| R2 | under(B2) | mongo receipt delete_many 제거 | mongo `test_purge_draft_removes_only_that_draft_graph` |
| R3 | over(B3) | 잡 가드에 SUCCEEDED·FAILED 추가 | `test_terminal_generation_job_does_not_block_purge` |
| R4 | under(B5) | 503을 일반 오류로 되돌림(uncertain 제거) | `locks the owner purge behind uncertain on a 503` |

### Next steps

- 독립 검증 재확인 요청(조건부 합격 조건 폐쇄).
- 장(유닛) 삭제 브리프 — unit_kind 존치 결정과 함께.
