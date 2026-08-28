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
- **최종 전수(보강 완료 후)**: backend **2546 passed / 4 skipped / 2907 subtests**
  (test-mongo ON — 셀 +2: B2 인메모리 receipts·B3 종료 잡) · frontend **388/388**
  (+2: uncertain·보관 실패) · `tsc --noEmit` clean · build 439.59 kB. docs 인덱스
  카운터 갱신(258건/58일치·판정 분포 183/73/2·v1.8.8) — 검증 기록 등재로 낡은
  카운터를 인덱스 가드가 잡았다.
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

---

## Session 8 — 장→장면 계층화 방향 확정·결정 브리프

### Goals

- `unit_kind` 존치 문제를 오너가 정한 실제 장→장면 계층 방향으로 좁힌다.
- 기존 평면 원고 계약과 저장 데이터를 손상하지 않고 구현하려면 필요한 세부 결정을 브리프로 올린다.

### Completed work

- 오너가 **“계층화한다. 장은 장면의 집합”**으로 방향을 확정했다.
- 현재 `Draft`·ordered-unit·reorder·Writing accept·export 계약을 실측했다. 현행은 부모 필드 없이
  archived 포함 전 Draft가 project 단위 `position=1..N`을 공유하고, W0가 chapter→scene nesting을
  명시적으로 금지한다.
- [`chapter-scene-hierarchy-decisions.md`](../../plans/chapter-scene-hierarchy-decisions.md)를 작성했다.
  저장 모델, 장 본문 소유, 기존 데이터 이관, `other`, 2단계 순서, AI 다음 단위 생성, 장 삭제, export/보관의
  선택지·권고·후속 문을 분리했다.
- 계획 인덱스에 새 브리프를 등재했다.

### Issues found

- 기존 `chapter` Draft도 version·snapshot·분석 참조를 가진 실제 본문일 수 있어, 이를 곧바로
  본문 없는 Chapter로 바꾸면 참조 ID를 대량 재작성해야 한다.
- 계층화는 SoT v1.7.9 D2=A와 W0의 “nesting 미도입”을 뒤집는 계약 변경이다. 세부 결정을
  확정하지 않은 채 parent 필드만 추가하면 reorder·export·삭제가 서로 다른 트리를 말한다.

### Decisions

- 오너 결정: `unit_kind`를 제거하거나 이름표로만 두지 않고 실제 계층을 도입한다.
- 오너 결정: 장은 장면의 집합이다. 장 자체 본문 허용, 저장 엔티티, 기존 데이터 이관 등
  세부 계약은 아래와 같이 확정했다.
- D1=A 별도 Chapter · D2=A metadata-only · D3=A 기존 Draft ID/본문 무손실 이관 ·
  D4=A `other` 제거 · D5=A parent별 연속 순열 · D6=A AI는 같은 장 다음 Scene만 ·
  D7=B 안전 가드 포함 Chapter cascade purge · D8=A 계층 export/파생 보관.
- D3 정정: 오너는 테스트 단계라 데이터 삭제를 허용했으나 D3=C는 삭제가 아니라 legacy
  이중 계약이다. 오너가 A 선택을 허용했고 A가 단일 runtime 계약과 무손실을 함께 만족해 채택했다.
- D6 근거: 장 마지막 장면의 이어쓰기가 다음 장을 자동 생성하는 것은 일반적인 저작 흐름이
  아니다. 새 장은 사용자 명시 동작으로만 만든다.

### Next steps

- 모델/마이그레이션부터 회귀 우선으로 구현한다.

### Verification

- `tests/test_docs_indexes.py`: **13 passed / 268 subtests**.
- 계획 문서 **112개**, 결정 브리프 **94개** 카운터와 루트/계획 README 주장이 일치한다.
- 세부 결정 확정 뒤 SoT **v1.8.9**와 README 버전 주장을 함께 갱신했다.
- `git diff --check` 통과.

---

## Session 9 — Chapter/Scene 정본 모델·migration 첫 슬라이스

### Goals

- 별도 Chapter와 parent별 Scene 순서 불변식을 Core SOT에 세운다.
- 기존 평면 Draft의 ID·version·snapshot·본문을 건드리지 않는 one-shot migration을 구현한다.

### Completed work

- metadata-only `Chapter{id,project_id,title,archived,position}`와 legacy-only
  `Draft.unit_kind`, runtime `Draft.chapter_id` 경계를 추가했다.
- in-memory/Mongo repository에 Chapter CRUD, Chapter reorder, hierarchy 원자 교체, project purge의
  Chapter 정리를 추가했다. Mongo migration은 낡은 project-wide position index를 제거하고
  `(chapter_id,position)` unique index로 교체한다.
- `ChapterSceneHierarchyMigration`이 기존 chapter Draft를 같은 제목 Chapter 아래 `본문` Scene으로,
  뒤따르는 scene/other를 같은 Chapter로, 선행 chapter 없는 묶음을 `미분류` Chapter로 결정적으로
  이관한다. Draft와 하위 정본 ID는 그대로 둔다.
- 신규 실행 스크립트 `scripts/migrate_chapter_scene_hierarchy.py`를 추가했다.
- Chapter/Scene 독립 연속 순서, 교차 장 reorder 거부, 독립 reorder 정상 경로, 결정적 migration,
  정상 계층 no-op의 양방향 회귀 5개를 추가했다.

### Issues found

- 기존 Mongo unique `(project_id,position)`은 장마다 Scene position이 1부터 시작하는 새 계약과
  공존할 수 없다. migration maintenance window에서 낡은 index를 제거한 뒤 새 parent-scoped
  index를 설치하도록 했다.
- D3=C는 데이터 삭제가 아니라 legacy 이중계약이어서 runtime 분기가 계속 남는다. 확정한 D3=A가
  migration 뒤 단일 계층 계약으로 수렴한다.

### Decisions

- `unit_kind`는 migration 입력을 읽기 위해 내부 모델에만 임시 nullable로 남기고, 신규 Scene은
  `unit_kind=None`으로 만든다. 공개 payload 제거는 API 슬라이스에서 수행한다.
- 첫 슬라이스는 정본 불변식과 migration만 잠근다. 공개 API·UI·Writing·export·cascade purge는
  이 기반 위의 후속 슬라이스로 분리한다.

### Verification

- 신규 집중 회귀: `tests/test_chapter_hierarchy.py` **5/5**.
- 기존 ordered-unit 순수 도메인 회귀 **11개 연속 통과** 후 이 머신의 TestClient 셀에서 장시간
  대기해 90초 상한으로 중단했다. 실패 출력은 없었고 API 슬라이스에서 해당 표면을 다시 실행한다.
- Core SOT + migration script mypy: **9 source files, no issues**.
- `py_compile` 및 `git diff --check` 통과.

### Next steps

- Chapter/Scene 공개 API와 계층 payload를 추가하고 기존 평면 API를 폐기한다.
- 프론트 목록·생성·재정렬을 새 계층 payload로 이관한다.

---

## Session 10 — Chapter/Scene 계층 공개 계약·Writing·export·cascade purge·UI 완결

### Goals

- Session 9의 정본 모델과 migration 위에 Chapter→Scene 공개 계약 전체를 연결한다.
- 오너가 고른 D6=A·D7=B를 Writing과 안전한 cascade purge에 반영하고 양방향 회귀로 잠근다.
- 계층화 완료 상태를 브리프·SoT 파생 산출물·기록물에 일치시킨다.

### Completed work

- Chapter 목록·생성·보관·파기와 Chapter/Scene 독립 reorder API를 추가했다. Scene 생성은
  `chapter_id`를 필수로 받고 공개 `unit_kind` 및 project-wide `draft-order`를 제거했다.
- Writing `start_next_unit`은 현재 Scene과 같은 Chapter 끝에 다음 Scene만 만든다. candidate·accept
  payload에서 `unit_kind`를 제거하고 저장 결과에 `chapter_id`를 연결했다.
- Markdown/TXT/ZIP export를 Chapter position→Scene position 순으로 바꾸고, Chapter 보관은 자식
  `archived`를 덮어쓰지 않는 파생 가시성으로 구현했다. ZIP 파일명은 두 position을 함께 써 장마다
  Scene position이 다시 1부터 시작해도 충돌하지 않는다.
- Chapter cascade purge는 보관 선행, 모든 자식 active 생성 잡 사전 검사(write 0/409), scratch와
  종료 생성 잡 정리, Core SOT 자식 그래프+Chapter 원자 파기를 적용했다. 기존 단일 Scene purge도
  종료 생성 잡을 남기지 않도록 같은 저장소 경계를 보강했다.
- 프론트 원고 목록을 Chapter 안에 Scene이 중첩된 구조로 교체하고 장/장면 생성·독립 순서 이동,
  장면 체크박스 삭제, Chapter 정확 제목 cascade 확인을 연결했다. purge 503은 uncertain으로 확인창을
  유지하고, purge 요청 이후 재시도 404만 이미 완료된 성공으로 처리한다.
- OpenAPI 파생 타입 `frontend/src/api/schema.d.ts`를 재생성하고 공개 계약의 `unit_kind` 제거를 확인했다.

### Issues found

- Chapter purge가 Core SOT만 지우면 완료·실패 generation job이 고아로 남았다. draft-scoped
  `purge_draft`를 generation job repository/service에 추가해 Chapter와 기존 Scene purge 양쪽에서
  종료 잡을 함께 제거했다.
- export 화면이 flat Scene 목록만 읽으면 보관된 Chapter의 파생 가시성을 알 수 없었다. Chapter
  목록을 함께 읽어 기본 export와 ZIP 선택이 같은 가시성 규칙을 쓰게 했다.
- 이 머신에서 FastAPI TestClient/ASGI 통합 셀은 첫 요청 단계에서 장시간 대기했다. 실패 assertion은
  관측되지 않았고 중단했으며, direct endpoint 회귀와 OpenAPI introspection으로 공개 계약을 검증했다.
  정상 TestClient 환경에서 전수 재실행은 배포 전 남은 검증이다.
- purge 재시도 404 성공 처리가 UI에서 빠진 것을 최종 계약 대조에서 발견했다. purge 요청 시작 여부를
  경계로 추가해 archive 단계 404까지 성공으로 삼는 과잉 보정을 막았다.

### Decisions

- 오너 결정 D3=A: 테스트 데이터 삭제도 허용됐지만 D3=C는 삭제가 아니라 legacy 이중 계약이므로,
  기존 Draft ID·version·snapshot·본문을 보존하면서 runtime을 단일 계층으로 수렴시키는 A를 적용했다.
- 오너 결정 D6=A: 이어쓰기는 같은 Chapter의 다음 Scene만 만들며 새 Chapter는 사용자 명시 동작이다.
- 오너 결정 D7=B: Chapter 삭제는 자식 Scene을 포함한다. 파괴 범위가 넓으므로 제목 확인과 생성 잡
  write-0 가드, 503 uncertain, purge-stage 404 멱등 성공을 함께 계약으로 둔다.
- 나머지는 확정 브리프대로 D1=A·D2=A·D4=A·D5=A·D8=A를 적용했다.

### Verification

- backend 집중 회귀: Chapter/activity/admin/Writing/ordered-unit 묶음 **60 passed**. generation job +
  Chapter 묶음 **51 passed**(앞 묶음과 일부 중복하므로 합산하지 않음).
- mypy: application과 선택 테스트 **154 source files, no issues**. 전체 대상의
  `tests/test_application_api.py:51`에는 기존 `_STORAGE_FAILURE=None` 대입 오류 1건이 있어 해당 파일만
  제외했다.
- frontend 집중 회귀: DraftList·WritingPanel·ProjectExportPanel **71/71**, 최종 DraftList **7/7**.
  production build **711 modules** 통과.
- OpenAPI introspection: project-wide `/draft-order` 없음, Scene 생성 `title/chapter_id` 필수·extra 금지,
  Draft/NextUnit/AcceptedSave의 `chapter_id`와 `unit_kind` 제거/추가 방향 확인.
- `py_compile`, `git diff --check`, 생성 schema 대조 통과. ASGI TestClient 전수는 위 환경 대기로 미완료.

| 방향 | 적용한 diff | 위치 | 재실패한 셀 |
|---|---|---|---|
| under-strict | `chapter_id: NonBlankName` → `chapter_id: NonBlankName \| None = None` | `services/application/app/api/models.py:693` | `ChapterHierarchyApiTest.test_scene_create_contract_requires_parent_and_rejects_unit_kind` |
| over-strict | `if chapter.archived and not include_archived:` → `if chapter.archived:` | `services/application/app/core_sot/service.py:951` | `ChapterHierarchyContractTest.test_export_uses_chapter_then_scene_headings_and_derived_archive` |
| under-strict | purge 성공 status `404` → `410` | `frontend/src/drafts/DraftList.tsx:161` | `treats a repeated chapter purge 404 as an already-completed success` |
| over-strict | `purgeRequested &&` 제거로 모든 단계의 404를 성공 처리 | `frontend/src/drafts/DraftList.tsx:161` | `does not mistake an archive-stage 404 for a completed purge` |

### Next steps

- disposable Mongo에서 `scripts/migrate_chapter_scene_hierarchy.py`를 dry-run→apply→재실행 no-op 순으로
  검증한 뒤 실제 maintenance window에 적용한다.
- TestClient가 정상 시작되는 환경에서 backend 전수와 Chapter API ASGI 관통을 재실행한다.
- 구현 커밋 범위를 다른 작업자가 독립 검증한다.

---

## Session 11 — 독립 검증(불합격) Blocking 5건 보강 마감

### Goals

- 독립 검증 [`verifications/2026-08-28/chapter_scene_hierarchy.md`](../../verifications/2026-08-28/chapter_scene_hierarchy.md)
  (판정 **불합격**)의 Blocking 5건을 폐쇄한다. 작업 AI가 B1~B4와 H2·H3을 구현하다 중단했고,
  본 세션이 B5·전수 수습·기록물을 마감했다.

### Completed work

- **B1(작업 AI분 + 셀 보강)** — migration 전 평면 legacy Draft를 서비스 `list_drafts` 경계와 라우터
  `_require_migrated_scene` 양쪽에서 쓰기 전 **503** `scene hierarchy migration is required`로 fail-closed.
  Writing accept는 대상 draft의 장 귀속·보관 상태를 enrich 앞에 검사한다(보관 장 409 포함).
  서비스 경계 셀을 신설해 2층 방어의 **각 층을 따로** 잠갔다.
- **B5(본 세션)** — Chapter purge 503을 오너 ⓐ 패턴으로 전환: 보관 단계 실패(파괴 없음)만 재시도를
  되살리고, 파기 단계 503은 재시도 버튼 제거·제목 입력·취소 잠금으로 uncertain 처리한다.
  `purgeRequested` 플래그는 2단계 try 분리로 구조적으로 대체했다.
- **B2·B3·H2·H3(작업 AI분)** — TXT 계층 export 단정, migration version/snapshot/본문 byte·archived
  보존·부분 상태 fail-closed 셀, mongo chapter 대칭 셀 2종, App/ProjectSettings mock `/chapters`
  이관, `report_budget_measure` chapter+scene 씨드.
- **B4(작업 AI분 + 활동 수 보태기)** — SoT v1.8.9 "(구현 진행)"→완료, Product Shell에서
  "draft/chapter/scene 계층은 미확정이다" 제거·계층 조항·총 96 operation 등재. 본 세션이 활동
  분류표 수(canonical **25**·EXCLUDED **29**)를 조항에 보탰다.
- **전수 재개에서 발견한 잔여 이관(본 세션)** — 전수를 돌리지 않아 숨어 있던 B1 여파 4곳:
  mongo 셀 4건(round-trip 3클래스·start_next_unit rollback — 죽은 `unit_kind=` 인자 포함),
  `ordered_units` OU-10(legacy 메타데이터 축은 repo 읽기로), `writing_scratch` accept 셀 4건,
  프론트 활동 라벨표(장 5종 라벨·`draft_order_changed` 제거·`chapter` 비링크 등재 — 연결 가드가
  잡았다). 이 머신에서 ASGI/TestClient 셀은 **대기 없이 정상 실행**됐다(세션 10의 "시작 단계
  대기" 주장은 이 환경에서 재현되지 않았다).

### Decisions

- B5의 uncertain 잠금은 새 결정이 아니라 오너 ⓐ(2026-08-28, 프로젝트 purge D4=A·세션 7 B5의
  대칭 적용)와 SoT v1.8.9 리터럴 "503 uncertain 잠금"(v1.8.8이 재시도 금지로 정의)을 그대로
  이어받은 시행이다.

### Mutation verification

모든 mutation은 체크포인트 커밋 위 clean tree에서 적용하고 `git checkout --` 로 복원했다(매번
`git status --short` 0건 확인).

| # | 방향 | mutation | 재실패한 셀 |
|---|---|---|---|
| M-A | under(B5) | 503에서 `setChapterPurgeUncertain(true)` 제거 | `locks the chapter purge behind uncertain on a 503` |
| M-B | over(B5) | 보관 단계 catch에도 uncertain 설정 | `revives the chapter purge retry when only the archive step failed` |
| M-C | under(B1) | `list_drafts` legacy 거부를 legacy 반환으로 복귀 | `test_legacy_drafts_fail_closed_at_the_service_boundary` |
| M-D | under(B1) | `_draft_payload`에서 `_require_migrated_scene` 호출 제거 | `test_legacy_scene_crud_fails_closed_with_503_before_any_write`의 `get_draft` subtest — 목록 subtest는 서비스층이 흡수(2층 방어 확인) |
| M-E | under(B1) | accept legacy 가드 `or`→`and` 완화 | `test_append_current_targeting_legacy_draft_is_503` |

### Verification

- backend 전수(test-mongo ON): 아래 Reproduction 참조 — 최종 수치는 커밋 시점 기록.
- mongo 집중: `test_core_sot_mongo` **85/85**(+신규 6), `test_writing_generation_job_mongo` **14/14**.
- frontend 전수 **383/383**(exit 0) · `npm run build` 통과(진입 442.34 kB) · `schema.d.ts` 재생성 0줄 차.
- `tests/test_docs_indexes.py` 13 passed. `test_activity_ui_labels` 6 passed(라벨표 25행 전수).
- OpenAPI 실측 96 operation — SoT v1.8.9 조항·HANDOFF와 일치.

### Next steps

- 독립 재검증 요청(불합격 조건 B1~B5 폐쇄 확인).
- disposable Mongo migration dry-run→apply→재실행 no-op 검증 후 maintenance window 적용(잔여).
