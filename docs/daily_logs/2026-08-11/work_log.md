# 2026-08-11 작업 로그 (베타)

## Goals

1. 어제 마감 메모가 지목한 **①번** — 이미지 재빌드 후 `/me`·활동 타임라인 **육안 확인**
2. 오너가 UI 페이즈 착수를 지시하면 **Phase 10 착수 결정 브리프** 작성

## Completed work

### Task 1 — 이미지 재빌드 (오너 지시)

**상태 실측(재빌드 전)**: 스택이 반쯤 죽어 있었다 — `application`·`mongo`·`gateway`·
`embedding`·`chroma`·`elasticsearch` 가 **Exited (255)**(33분 전, 일괄이라 도커/WSL
재시작 흔적) · `generation_worker` 는 mongo 부재로 restart 루프 · `admin`·`frontend`·
`worker` 만 Up. 이미지는 **2026-08-10 13:52** 빌드이고 9.2 코드는 **15:41·16:00** 커밋.

**빌드 → `docker compose up -d`** 후 **healthy 8 + healthcheck 없는 2** 회복.

**★ HANDOFF 에 없던 함정 — `admin` 은 따로 빌드해야 한다.** HANDOFF 는 *"application
이미지 재사용·command 만 다름"* 이라 적고 있으나 [`docker-compose.yml`](../../../docker-compose.yml)
에 **자체 `build:` 블록**이 있어 `ai_writte_system-admin` **별도 태그**로 빌드된다.
`docker compose build application frontend` 로는 갱신되지 않고, 실제로 이 세션이
그것을 놓쳐 admin 만 옛 이미지로 한 번 떴다.

> **★ 정정(같은 날, Task 4).** 이 문단이 처음에 *"worker·generation_worker 는 진짜로
> application 이미지를 공유하지만 admin 은 아니다"* 라고 적었는데 **거짓이다.** 넷 다
> 각자 `build:` 를 갖고 각자 태그를 받고 있었고, **가장 뒤처진 것은 admin 이 아니라
> worker(07-27)였다.** 오너가 *"별도 태그를 한 특별한 이유가 있나? 서로 필요한거잖아"*
> 라고 물어 다시 봤고 그 지적이 맞았다 — 아래 Task 4 가 근본 수정이다.

**프론트 빌드 출력이 기준선과 일치** — 702 modules · 진입 420.08 kB · AdminConsole
lazy 8.50 kB · 관측 lazy 386.70 kB. 어제 검증이 정정한 **702** 가 맞음을 재확인.

### Task 2 — `/me/activity` 500 수정 (`d26059e`)

**재빌드 직후 관통 확인에서 발견.** 로그인 200, `GET /me/activity` **500**:

```
AttributeError: 'NoneType' object has no attribute 'list_projects_for_owner'
  services/application/app/routers/auth.py:180
```

- **원인**: [`main.py:1824`](../../../services/application/app/main.py#L1824) 가
  `register_auth(..., core_sot=service, ...)` 로 **해석 전 원시 파라미터**를 넘겼다.
  `create_app` 은 `core_sot = service or _default_core_sot_service()` 로 해석하는데,
  `register_auth` 만 그 앞 값을 받았다.
- **패턴 스윕(§4)**: `core_sot=` 전수 grep — **14개 호출 지점 중 이 한 곳만** 예외였다.
  나머지 13개는 전부 해석된 `core_sot` 을 넘긴다. 인접 확산 없음.
- **왜 회귀 2266셀이 green 이었는가**: 모든 테스트가 `create_app(service=…)` 로 주입해
  **두 값이 같은 객체**가 된다. 배포만 아무것도 주입하지 않아 `None` 이다. 요청 구동
  테스트로 **원리적으로 볼 수 없는** 자리였고 육안 확인이 잡았다.
- **수정**: 한 줄(`core_sot=service` → `core_sot=core_sot`).
- **가드**: `PersonalActivityAssemblyTest` 2셀 — **주입 없이 조립한 앱**을 구동한다.
- **라이브 재확인**: 재빌드 후 `/me/activity` **200 · 5건**, 최신순, `before → after` 정상.

### Task 3 — Phase 10 착수 결정 브리프 (`c222cf2`·`505bc03`·`c4d6545`)

[`plans/10-frontend-design-system-decisions.md`](../../plans/10-frontend-design-system-decisions.md)
· 검산 스크립트 [`plans/10_palette_contrast.py`](../../plans/10_palette_contrast.py).

**★ 이 브리프의 핵심 실측 — 회귀가 무엇을 잠그는가** (전 테스트 grep):

| 단정 | 건수 | 잠그는 것 |
|---|---|---|
| `ByRole` | 299 | 접근성 semantics |
| `ByText` | 251 | 화면 문구 |
| `ByLabelText` | 179 | 폼 라벨 |
| `toHaveTextContent` | 60 | 문구 |
| **`toHaveClass`** | **0** | — |
| **`ByTestId`** | **0** | — |

HANDOFF 의 *"285셀이 문구·구조를 상당히 잠근다"* 경고를 축별로 갈랐다: **순수 시각
변경은 회귀 비용 0**, 비싼 것은 **문구 311곳**과 **접근성 semantics 478곳**이다.

### Task 4 — 앱 이미지 하나로 통합 (오너 지적에서 출발)

오너 질문: *"빌드쪽은 계속 놓치게 된다면 컴포즈에서 같이 묶어두는게 맞지 않나? 별도 태그를
한 특별한 이유가 있나? 서로 필요한거잖아"*

**답: 특별한 이유가 없었다 — 오히려 주석이 이미 공유를 의도한다고 적고 있었다.** `admin`
주석은 *"Shares the application image and changes only the command"*, `worker` 주석은
*"Shares the application image (same Python runtime + deps + indexing code)"* 다.
**의도는 처음부터 공유였고 설정만 그것을 구현하지 않았다** — compose 는 `image:` 가 없으면
서비스마다 `<project>-<service>` 태그를 만든다.

**실측한 피해**(이 질문이 없었으면 안 봤을 것이다):

| 서비스 | 이미지 날짜 | 뒤처짐 |
|---|---|---|
| `application` | 08-11 | — (오늘 재빌드) |
| `admin` | 08-11 | — (오늘 재빌드, Task 1 에서 놓쳤다가 수습) |
| `generation_worker` | **07-29** | **13일** |
| `worker` | **07-27** | **15일** |

**★ 그리고 그것이 기능을 죽이고 있었다.** 실행 중인 `worker` 컨테이너 안을 직접 봤다:

```
docker compose exec worker grep -c "_drain_purge" .../indexing/service.py  →  0   (현행 코드는 2)
docker compose exec worker grep -rl "PROJECT_PURGED" .../indexing/          →  (없음)
```

즉 **D8-6 파기의 워커 절반이 죽어 있었다** — 관리자 purge 가 `PROJECT_PURGED` 를 outbox 로
넘기는데(`f81d145`, 08-02) 실행 중 워커는 그 이벤트 타입을 **모르는 07-27 코드**였다.
`generation_worker` 는 8.3 의 **워커 차감**(`9a6a500`)이 빠져 있었다.
**다만 잠복이었다** — `index_sync_outbox` 실측 **0건**이라 아직 아무 파기도 발생하지 않았다.

**수정**: 네 서비스에 `image: ai_writte_system-app` 을 명시해 태그를 공유시켰다.

**검증**:

- `docker compose config --quiet` 통과 · 네 서비스가 같은 이미지로 해석됨
- `docker compose build` 에서 **`ai_writte_system-app Building/Built` 가 정확히 1회** —
  compose 가 빌드를 dedupe 한다(추측이 아니라 출력으로 확인)
- 재기동 후 **네 컨테이너의 이미지 ID 가 동일**(`sha256:a8a3ed19ec376`)
- 워커 안 `_drain_purge` **0 → 2**, `PROJECT_PURGED` 존재로 전환
- 제품 관통 무변: `/health` 200 · `/me/activity` 401 · 제품앱 `/admin/users` **404** ·
  nginx `/api/admin/users` **401**(Slice 2 토폴로지 유지)
- compose 를 읽는 테스트 **전수**(`test_compose_exposure` · `test_admin_surface_separation` ·
  `test_core_sot_mongo`) **92 passed / 87 subtests**

**정리 대상**: 참조를 잃은 옛 이미지 4개(~2.0 GB) — `ai_writte_system-application` ·
`-admin` · `-worker` · `-generation_worker`. **삭제는 오너 판단**이라 남겨 뒀다
(`docker image rm` 하면 회수된다).

### Task 5 — Phase 10 Slice 10.0: 계정 메뉴 + 제품명 (`387bfe7`·`5965c9b`)

D4 = ⓐ+ⓒ · D5 = ⓐ 구현. [`AuthGate.tsx`](../../../frontend/src/auth/AuthGate.tsx) 의
새 `SessionMenu` + `styles.css` 배치.

**★ 브리프에서 한 가지 벗어났다 — `role="menu"` 를 안 썼다.** 브리프 §D4 가
`role="menu"`/`menuitem` 을 적었으나 구현하며 고쳤다. ARIA 의 menu 는 **애플리케이션
명령 메뉴**용이고 화살표 키 탐색·타입어헤드를 사용자에게 약속하는데, 여기 담긴 것은
**내비게이션 링크 둘 + 액션 하나**라 그 약속을 지킬 이유가 없다 → 표준 **disclosure**
(버튼 `aria-expanded`/`aria-controls` + 접히는 영역). **부수 효과로 기존 셀이 살았다**:
`role="menuitem"` 을 얹으면 `<a>` 의 link 역할이 덮여 `getByRole("link", {name:"관리"})`
가 무효가 되는데 disclosure 는 보존한다. 브리프에 취소선으로 정정 기록.

**판단 하나** — 로그아웃 클릭에 패널을 닫지 않는다. 닫으면 `"나가는 중…"`·`disabled` 가
그 즉시 사라져 **진행 중이라는 유일한 신호를 잃는다**. 초판이 그렇게 썼다가 고쳤고,
그 성질을 M4 가 잠근다.

### 뮤테이션 (6종 전부 작동)

| # | 적용한 diff | 위치 | 실패한 셀 |
|---|---|---|---|
| M1 | `<Link to="/me">` → `<span>` | `AuthGate.tsx` `SessionMenu` | **3 failed** — 진입점 셀 + 비관리자 셀 + 제품명 셀(같은 렌더 경유) |
| M2 | `triggerRef.current?.focus()` → `void 0` | 같은 파일 `close()` | **1 failed** — `closes on Escape and gives focus back` |
| M3 | `{user.is_admin && (` → `{true && (` | 같은 파일 | **1 failed** — 비관리자 over-strict 셀 |
| M4 | `onClick={onLogout}` → `onClick={() => { setOpen(false); onLogout(); }}` | 같은 파일 | **2 failed** — 진행 신호 셀 + 기존 로그아웃 셀 |
| M5 | 헤더 `에-라잇` → `AI Writing System` | 같은 파일 | **1 failed** — 제품명 셀 |
| M6 | `{open && (` → `{true && (` | 같은 파일 | **2 failed** — 닫힘 상태 셀 + Esc 셀 |

**★ M2 는 처음에 안 물었다(24 passed) — 그것이 신호였다.** 초판 셀이 트리거를 클릭한
직후 Esc 를 눌렀는데 **그 시점 포커스가 이미 트리거에 있어** 복귀 코드를 통째로 지워도
통과했다. 포커스를 패널 안으로 옮긴 뒤(`userEvent.tab()`) 눌러야 복귀를 잰다. 강화 후
같은 뮤테이션이 문다(`5965c9b`). **어제 배운 "뮤테이션이 안 물면 그것이 신호다"가
오늘 다시 적중했다.**

### 기존 셀 갱신 (6줄)

드롭다운으로 옮겼으므로 `관리`·`로그아웃` 을 집기 전에 메뉴를 연다. 비관리자 셀은
**닫힌 채로 없음**을 보던 것을 **열어서 없음**으로 강화했다(닫혀 있으면 무엇이든 없다).

### 회귀·부하

frontend **285/20 → 289 passed / 20 files**(**+4 cells**, 파일 무변).
build **702 modules 무변** · 진입 **420.08 → 420.81 kB**(+0.73) · CSS 26.21 → 26.62 kB ·
**lazy 청크 무변**(AdminConsole 8.50 · 관측 386.70). backend 무관(프로덕션 0줄) —
프론트를 읽는 유일한 백엔드 가드 `test_activity_ui_labels.py` **6 passed / 30 subtests**.

**배포 확인**: `docker compose build frontend && up -d` 후 번들에 `에-라잇`·`내 작업`
포함 확인, frontend healthy.

## Issues found

| # | 문제 | 원인 | 처리 | 결과 |
|---|---|---|---|---|
| 1 | `/me/activity` 배포에서 500 | `register_auth` 만 해석 전 `core_sot`(None) 수령 | 한 줄 수정 + 주입 없는 조립 가드 2셀 | `d26059e` · 라이브 200 확인 |
| 2 | 전수 회귀 **5 failed** | **작성자 과실** — 새 브리프를 `docs/plans/README.md` 인덱스에 미등재 + 두 README 개수 주장(104/86)이 낡음 | 인덱스에 "프론트 디자인 (Phase 10)" 절 신설 · 105/87 로 갱신 | `505bc03` · 재측정 green |
| 3 | `admin` 이미지가 재빌드에서 누락 | compose 에 자체 `build:` 가 있어 별도 태그 | `docker compose build admin` 추가 실행 | 임시 수습 |
| 4 | **★ `worker` 가 15일 뒤처져 `PROJECT_PURGED` drain 이 없었다** | Issue 3 과 **같은 뿌리** — 네 서비스가 한 Dockerfile 을 쓰면서 `image:` 미명시라 각자 태그 | 네 서비스에 `image: ai_writte_system-app` 공유 (Task 4) | 워커 `_drain_purge` 0 → 2 · 이미지 ID 4개 동일 · 빌드 1회 |

**Issue 2 에 대해**: `docs/plans/README.md` 가 *"새 계획·브리프를 쓰면 아래 표에 한 줄
추가한다. 빠뜨리면 `tests/test_docs_indexes.py` 가 실패한다 — 규칙이 아니라 강제다"* 라고
**명시하고 있는데 읽지 않았다.** 2026-08-02 에 이 가드를 넣기 전 *"90개 중 51개 미등재"*
였던 그 병을 그대로 재현했다. 가드가 잡았으므로 손실은 없으나, **새 문서를 만들 때는
그 디렉터리의 README 를 먼저 읽는다**가 교훈이다.

## Decisions (오너 2026-08-11)

브리프 [`10-frontend-design-system-decisions.md`](../../plans/10-frontend-design-system-decisions.md)
§확정값에 표로 있다. 여기에는 **왜** 만 남긴다.

- **D2 = ⓑ 팔레트 재정의 (구현자 권고 기각).** 구현자는 ⓐ(현행 크림+테라코타 유지)를
  권고하며 *"글쓰기 도구에 어울리는 방향이 이미 잡혀 있다"* 고 적었다. **오너가 기각했고
  그것이 옳았다** — 오너 표현은 *"현행이 이상해서 바꾸자고 했는데"*. 조사 결과 현행
  값(`#f4f0e7` 크림 + `#a4452f` 테라코타)은 **생성형 AI 디자인이 수렴하는 대표 기본값
  좌표**였다. 구현자가 기본값을 "선택된 방향"으로 오독하고 근거 없이 방어한 것이다.
  - **교훈**: 미학 판단에서 *"이미 방향이 잡혀 있다"* 는 관찰은 **그 방향이 선택된
    것인지 기본값인지** 확인하기 전에는 근거가 못 된다.
  - 오너 선호: *"블루계열 파스텔 쪽을 선호하는데 대비성있게"*. 파스텔과 대비는 충돌하므로
    **파스텔은 면(surface)에만, 잉크·강조는 같은 hue 의 깊은 쪽**으로 역할을 갈라 풀었다.
  - 오너 지시 *"인터넷 찾아봐서 좋은 색 토큰 기준이 있을꺼야"* 에 따라 기준을 조사해
    적용: **3계층 토큰**(값이 아니라 의도로 명명) · **OKLCH 지각 균등 램프** ·
    **WCAG 2.2 AA 를 설계 입력으로**. 출처는 브리프 §참고문헌.
- **D4 = ⓐ+ⓒ (구현자 권고 확장).** 구현자는 ⓒ(드롭다운)를 *"항목이 2~3개뿐이라
  과설계"* 로 기각했으나 오너가 **관용성**을 근거로 채택했다(*"일반적으로 C가 맞지 않나?
  a랑 C랑 같이 해"*). username 이 버튼이면서 그 클릭이 메뉴를 연다.
- **D1=ⓒ · D3=ⓓ · D5=ⓐ · D6=ⓑ** — 권고 수용. D3 은 **커서 페이징을 각하가 아니라
  유예**한 것이며 트리거는 *실사용자가 100건을 채워 "더 이전"을 필요로 할 때*.
- **소팅·검색은 패스**(오너: *"있으면 더 좋긴하겠지만 일단 패스"*). 트리거는 *날짜 그룹
  뒤에도 특정 활동을 찾으려 스크롤하게 될 때*.

## 팔레트를 어떻게 세웠는가 (재현 가능)

`python3 docs/plans/10_palette_contrast.py` — 의존성 없이 OKLCH→sRGB 와 WCAG 대비를
계산한다. **브리프의 숫자는 전부 이 출력이며 손으로 적은 것이 없다.**

- 램프: hue 250 고정, chroma 고정, **L 등간격** → 지각 균등
- 중립도 hue 250(채도 .005~.022) — 순회색은 파스텔 면 옆에서 누렇게 뜬다
- **색역 이탈 5건은 L 을 유지한 채 채도만 이진 탐색으로 축소**(`blue-100` .028→.0277 ·
  `blue-700` .135→.1275 · `blue-800` .105→.1021 · `danger-100` .040→.0358 ·
  `warn-700` .110→.0993). **L 을 건드리면 램프의 지각 균등이 무너지고 대비 수치가 어긋난다.**
- **WCAG 2.2 AA 18짝 전수 검산, 실패 0.** 본문 3짝은 AAA(14.01 · 15.00 · 12.81)로 잡았다
  — 장시간 읽고 쓰는 도구라 본문만은 AA 로 만족하지 않았다.
- `--border-hairline`(`slate-300`, 1.47:1)은 검산표에 **없다** — 장식 구분선은 WCAG
  1.4.11 대상이 아니다(**의미를 전달하는** 비텍스트만 3:1). **구분선이 의미를 나르기
  시작하면 `--border-control` 로 올려야 한다.**

## 부수 실측 — 10.1 이 깨뜨릴 것

[`ObservabilityDashboard.tsx`](../../../frontend/src/observability/ObservabilityDashboard.tsx)
가 차트 색을 **JS 리터럴**로 들고 있어 `var(--)` 교체가 닿지 않고, **옛 팔레트 값이 직접
박혀 있다** — `#f4f0e7`(구 배경)이 막대 stroke 로 반복, `#d8d0c1`(구 `--line`)·
`#746f65`(구 `--muted`)가 축·격자에. 그리고 **`:53` 주석이 "이 앱의 paper surface
(`#f4f0e7`)에 대해 검증했다"** 고 적고 있어 배경이 바뀌면 그 검증이 무효다. 계열색 기준은
본문 대비가 아니라 **인접 계열 구분**이라 램프를 그대로 쓸 수 없다 → 브리프 follow-up 등재,
10.3~ 에서 별도 수립.

## 회귀 기준선

**backend test-mongo ON `2268 passed / 1 skipped / 2367 subtests`**(2026-08-11 베타 실측,
986초). 직전 `2266/1/2367` 에서 **셀 +2 · subtest 0** — 신규 `PersonalActivityAssemblyTest`
2셀이고 subtest 를 만들지 않는다. 문서 3건 추가는 `test_docs_indexes.py` 의 판정 열
전수 셀을 건드리지 않았다(브리프는 `verifications/` 가 아니라 `plans/` 라서).

frontend·build 는 **이 세션에서 프론트 코드를 0줄 바꾸지 않았으므로 무변**이며 재측정하지
않았다 — `285/20` · `702 modules` · 진입 `420.08 kB`. (702·420.08 은 Task 1 재빌드
출력으로 **확인**됐다.)

**★ 1차 회귀는 5 failed 였고 그것은 이 세션이 만든 문서 문제였다**(Issue 2). 수정 후
2차를 **다시 돌려** 위 값을 얻었다 — 산술로 채우지 않았다(어제 배운 *"측정하지 않은
숫자를 적었다"* 의 반복을 피함).

## Next steps

1. **Phase 10 Slice 10.0** — 헤더 드롭다운(D4 ⓐ+ⓒ) + 제품명 "에-라잇"(D5). 회귀 +3~5 예상.
2. 10.1 팔레트 교체 → **회귀 0이라 육안 확인이 유일한 검증 수단**. 13개 표면 전수 훑기.
3. 10.2 활동 날짜 그룹 → 10.3~ 화면별(관측 차트 계열 팔레트 포함).
4. 오너 결정 잔여: **dogfood 착수(GATE-1)**.
5. **미검증 구간**: 오늘 `d26059e`(코드) + 어제 `8ddf282`·`8f6ee5e`. 브리프 3커밋은 문서다.
