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
| M1 | `<Link to="/me">` → `<span>` | `AuthGate.tsx` `SessionMenu` | **3 failed** — 진입점 셀 + 비관리자 셀 + **Esc 포커스 복귀 셀**([`App.test.tsx:641`](../../../frontend/src/App.test.tsx#L641), 열린 뒤 `tab()` 이 그 링크로 가므로 함께 깨진다) |
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

### Task 6 — Phase 10 Slice 10.1: 잉크블루 토큰 체계 (`dcd2ad5`·`3465192`)

색을 전부 토큰 뒤로 보냈다. 화면은 semantic 만 보고 primitive 는 `:root` 안에서
semantic 이 참조할 때만 등장한다(3계층 중 2계층).

**이관 규모**: 옛 토큰 참조 **178곳**(`--ink` 32 · `--muted` 53 · `--line` 41 ·
`--accent` 30 · `--accent-dark` 12 · `--danger` 10) · 하드코딩 **hex 30곳 · rgba 15곳**
→ 전부 0. radius **6곳**, spacing **37곳** 스케일 채택(값 전체가 한 길이인 선언만 —
`padding: 1rem 2rem` 같은 복합값은 손대지 않았다. 부분 치환은 읽기 어려워지고 실수
여지가 크다).

**★ 타이포 스케일은 범위 밖으로 뒀다(스코프 판단).** 현행 `font-size` 가 **29종**이다
(0.7~1.8rem에 0.72/0.74/0.75/0.76/0.78 같은 근접 중복 다수). 스케일에 맞춰 스냅하는 것은
토큰 이관이 아니라 **눈으로 판단해야 하는 시각 재설계**이고, 팔레트 교체와 겹치면 diff 를
검토할 수 없게 된다. 10.3~ 첫 항목으로 넘기고 사유를 `:root` 주석에 남겼다.

#### ★ 구현이 브리프 가정 셋을 반증했다

| # | 브리프 가정 | 실제 | 처리 |
|---|---|---|---|
| 1 | surface 는 page·card·sunken·accent-soft | **이 앱에는 침강면보다 융기면이 많다** — `#fbf8f1`·`#fffdf8` 처럼 page 보다 **밝은** 면이 카드·패널 다수 | `--surface-raised` 신설. 밝기 순서 page < raised < card, sunken 만 page 보다 어둡다 |
| 2 | `slate-400` 테두리 3:1 · `slate-500` placeholder 4.5:1 | **카드에서만** 맞았다. 페이지에서 2.95 / 3.97 로 미달 | 최악 배경에서 목표 대비를 내는 가장 밝은 L 을 이분 탐색으로 재계산 |
| 3 | (2 의 수정) 최악 배경 = 페이지 `blue-50` | **틀렸다 — 침강면 `blue-100` 이 더 어둡다.** `.gate-finding` 매핑에서야 드러났다 | 다시 풀었다. **교훈: 최악 배경은 "주로 쓰는 면"이 아니라 정의된 표면 전체의 최소다** |

`placeholder` 는 이분 탐색이 낸 L 이 실수공간에서 정확히 4.50 이었는데 **hex 8비트
양자화로 4.49 가 됐다** — 경계값은 양자화 뒤에 다시 재고 여유를 둔다. 최종 **30짝 전수
검산 실패 0**(본문 4짝은 AAA).

#### ★ 이관이 만든 결함 하나 — 스스로 잡았다

`#f4f0e7` 이 **두 역할을 겸하고 있었다**: `body` 의 **페이지 배경**과 카드 안
`.gate-finding` 의 **침강 블록**. 일괄 매핑해서 `body` 가 `--surface-sunken`(한 단계
어두움)이 됐다. 배포 CSS 를 확인하다 발견해 `--surface-page` 로 정정했다.
**가드가 못 잡는 종류다** — 둘 다 정의된 토큰이라 참조는 멀쩡하고 **의미만 틀렸다.**

#### 새 가드 둘

**① `frontend/src/designTokens.test.ts` (3셀) — 이 저장소 최초의 CSS 가드.**
CSS 는 지금까지 무엇을 바꿔도 회귀가 침묵했다(`toHaveClass` 0 · `ByTestId` 0). 178곳
기계적 치환에서 오타 하나는 `var(--typo)` 로 남고 **CSS 는 조용히 아무것도 그리지
않는다** — 빌드도 테스트도 통과하고 화면만 깨진다. 스타일시트를 파싱해 ① 쓰는 토큰이
전부 정의됐는지 ② 규칙부에 리터럴 색이 없는지(D6=ⓑ 의 실체) ③ 화면이 primitive 를
직접 쓰지 않는지 본다.

**★ 그 가드가 첫 실행에서 8.4 가 남긴 실제 결함을 잡았다.** `.writing-confirm`(quota
확인 대화)이 `var(--border)` 와 `var(--surface-muted, transparent)` 로 **정의된 적 없는
토큰 둘**을 써서 **2026-08-04 부터 테두리도 배경도 없이** 렌더되고 있었다(`8d59236`).
HANDOFF 가 *"8.4 확인 대화는 렌더 미검증"* 이라 적어 둔 바로 그 화면이다. 그리고
**초판 정규식이 `)` 로 끝나는 형태만 봐서 fallback 쪽을 놓칠 뻔했다** — 결함이 정확히
그 형태로 숨어 있었으므로 `var(--x, y)` 도 세도록 강화했다.

**② `tests/test_design_token_provenance.py` (3셀) — 팔레트의 출처를 잇는 연결선.**
`styles.css` 주석이 *"hex 를 손으로 고치지 말 것"* 이라 적었지만 **적어 두는 것만으로는
아무도 막지 못한다.** 손으로 한 글자 고치면 팔레트는 "계산해서 세웠다" 가 아니게 되고
대비 검산이 화면의 색을 말하지 않게 되는데 회귀는 전부 green 이다(프론트 가드는 토큰
체계의 무결성을 볼 뿐 **값의 출처**는 모른다). pytest 인 이유는 생성기가 파이썬이라
두 정본을 같은 프로세스에서 볼 수 있는 자리가 여기뿐이기 때문이다
(`test_activity_ui_labels.py` 선례).

#### 뮤테이션 (7종 전부 작동)

| # | 적용한 diff | 대상 | 실패한 셀 |
|---|---|---|---|
| M9 | `var(--text-muted)` → `var(--text-mutted)` | `styles.css` | **1** — 미정의 토큰 셀 |
| M10 | `var(--surface-raised)` → `var(--surface-muted, transparent)` (8.4 결함 재현) | `styles.css` | **1** — 미정의 토큰 셀(fallback 강화 후) |
| M11 | 규칙부에 `color: #25231f` 주입 | `styles.css` | **1** — 리터럴 색 셀 |
| M12 | `var(--text-link)` → `var(--blue-700)` | `styles.css` | **1** — primitive 누출 셀 |
| M13 | `--blue-900` hex 를 손으로 수정 | `styles.css` | **1** — 출처 일치 셀 |
| M14 | 생성기만 수정하고 CSS 미반영 | `10_palette_contrast.py` | **1** — 같은 셀(양방향) |
| M15 | 생성기·CSS 를 **나란히** 나쁘게(본문을 AA 경계로) | 둘 다 | **4** — 검산 셀 + AAA 셀 |

**★ M11 은 처음에 안 물었는데 뮤테이션이 잘못 조준된 경우였다** — 첫 번째
`color: var(--text-body)` 가 `:root` **안**(리터럴이 허용되는 정의부)이라 규칙부를 안
건드렸다. 규칙부로 재조준해 확인했다. **"안 물면 신호"를 적용하기 전에 뮤테이션이
의도한 자리를 쳤는지부터 본다.**

#### 독립 검증 대응 (조건부 → 합격 승격, 그리고 잔여 니트)

검증 [`slice_10_1_palette.md`](../../verifications/2026-08-11/slice_10_1_palette.md).
**Blocking 0**, 조건 둘 + 니트 하나가 전부 **문서가 구현과 갈린** 것이었다 — 값·가드는
독립 재계산으로 통과했다.

| 지적 | 실제 | 처리 |
|---|---|---|
| **C1** 브리프 §D2 primitive 표가 구현과 갈림 | 맞다. 값을 스크립트로 다시 풀면서 브리프를 안 고쳤다 | 10.0 의 취소선 인라인 정정 패턴으로 정정 + 대비표를 "착수 시점 스냅샷"으로 명시하고 정본을 스크립트·가드로 지정 |
| **H1** 짝 수를 세 곳이 다르게 말함(18·28·18, 실제 30) | 맞다 | 30 통일 + **검증자 권고대로 prose 를 `len(PAIRS)` 에 묶는 셀 추가** |
| **니트** semantic 표에 2행 누락 | **실제로는 9행 누락 + 매핑 오류 1건**(`--border-hairline` slate-300 → 실제 slate-200) | §4 패턴 스윕으로 전수 대조 → 표를 `:root` 에서 **재생성** + **표↔`:root` 를 묶는 셀 추가** |

**★ 같은 병이 세 번 나왔다** — primitive hex · 짝 수 prose · semantic 표. 셋 다
*"사람이 두 곳을 동시에 기억해야 하는 구조"* 가 원인이지 부주의가 원인이 아니라고 보고,
**세 번 다 가드로 묶었다**(provenance 3 → **5 cells / 89 subtests**). 뮤테이션 M16~M20
전부 작동.

**★ 이 과정에서 §6 을 한 번 어겼다** — 뮤테이션 원복에 `git checkout` 을 쓰면서 같은
파일의 **커밋 안 한 편집을 함께 날렸다**(`styles.css` 짝 수 30 → 28 로 되돌아감). 저장소가
아홉 번 겪은 그 사고다. **다만 방금 만든 prose 가드가 즉시 실패해 잡혔다** — 가드가 없었으면
문서가 조용히 틀린 채로 커밋됐을 것이다. 이후 뮤테이션은 체크포인트 커밋을 먼저 하고 돌렸다.

#### 회귀·부하

frontend **291/21 → 294 passed / 22 files**(**+3 cells · +1 file**).
build **702 modules 무변** · 진입 **420.81 kB 무변**(색은 CSS 에만 있다) ·
CSS **26.62 → 30.47 kB**(토큰 정의 + 주석). backend 는 아래 기준선 절.

**배포 확인**: 재빌드 후 CSS 에 `--surface-page: var(--blue-50)` 확인,
`body` 배경이 `--surface-page`, 옛 팔레트(`#f4f0e7`·`#a4452f`) **0건**.

**알려진 중간 상태**: 색 리터럴이 남은 tsx 는 [`ObservabilityDashboard.tsx`](../../../frontend/src/observability/ObservabilityDashboard.tsx)
**한 파일 11곳**뿐이다 — 브리프 follow-up 에 등재된 그대로이며 10.3~ 에서 계열 팔레트를
따로 세운다. **10.1~10.3 사이에는 차트만 이질적으로 보인다**(D1=ⓒ 점진의 대가).

### Task 7 — Phase 10 Slice 10.2: 활동 날짜 그룹 (`34ed87f`)

D3=ⓓ 구현. 공유 모듈 [`activityDays.ts`](../../../frontend/src/projects/activityDays.ts)
+ 두 화면(`ActivityTimelinePage` · `PersonalHubPage`) 적용. **backend 0줄.**

날짜 머리글을 얹고 **행에서 날짜를 뺐다**(시각만 남김) — 같은 정보를 두 번 쓰지 않는
것이 그룹핑을 한 이유다.

**★ 커서 페이징이 아닌 이유(D3=ⓓ)**: 100건 상한을 없애려면 operation 78 이 움직여야
하는데 **지금 100건이 부족하다는 증거가 없다.** 커서는 유예이고 트리거는 *실사용자가
100건을 채워 "더 이전"을 필요로 할 때*(9.1 브리프 F1 이 정본). 상한 문구는 그대로 두고
셀이 그것을 잠근다 — **그룹핑이 상한을 올린 것처럼 보이면 안 된다.**

**모듈이 지키는 것 셋** (docstring + 셀):

| # | 규칙 | 왜 |
|---|---|---|
| 1 | **서버 순서를 다시 정렬하지 않는다** | 정렬 정본은 `log_mongo.py` 의 `at` DESC. 여기서 또 정렬하면 **순서를 정하는 곳이 둘**이 되고 언젠가 갈린다. 뒤섞인 입력이 그대로 나오는지 보는 셀이 그 자리다 |
| 2 | **그룹 경계는 브라우저 로컬 날짜** | 행이 로컬 시각을 찍으므로 머리글만 고정 시간대로 계산하면 *"오늘"* 아래 어제 시각이 앉는다. **`quota/policy.py` 의 KST 와 다른 판단이고 이유도 다르다** — 그쪽은 **시행 창**(서버 계약), 여기는 **표시**(보는 사람의 달력) |
| 3 | **날짜를 못 읽는 행을 버리지 않는다** | 행이 조용히 사라지는 것이 잘못된 머리글보다 나쁘다 |

#### ★ 테스트가 시계에 의존하면 안 된다 — 두 번 헛디뎠다

① 화면 셀이 8/10 을 `"8월 10일"` 로 기대했는데 **그날이 마침 "어제"** 라 깨졌다.
② 고치려고 `vi.useFakeTimers()` 를 썼더니 **`findBy*` 의 `waitFor` 가 멈춰 세워져
세 셀 전부 5초 타임아웃**이 됐다.
→ **연도가 다른 날짜**(2024)를 쓰면 라벨이 무슨 날에 돌려도 같다. "오늘"·"어제" 자체는
**모듈 셀이 `now` 를 주입해** 결정적으로 잰다 — 화면 셀이 재는 것은 *"화면이 그 모듈을
실제로 쓰는가"* 이지 라벨 규칙이 아니다. **재는 것을 그 자리에서 잴 수 있는 층으로
내리면 시계 의존이 사라진다.**

#### 뮤테이션 (4종 전부 작동)

| # | 적용한 diff | 실패한 셀 |
|---|---|---|
| M21 | 입력을 `at` 로 다시 정렬 | **1** — 순서 보존 셀 |
| M22 | 로컬 대신 UTC 날짜로 그룹 | **4** — 로컬 달력 셀 + 라벨 셀 3 |
| M23 | 화면이 모듈을 안 쓰고 평면 리스트(배선 누락) | **2** — 두 화면의 머리글 셀 |
| M24 | 날짜 못 읽는 행을 `continue` 로 버림 | **1** — 보존 셀 |

#### 회귀·부하

frontend **294/22 → 305 passed / 23 files**(**+11 cells · +1 file**).
build **702 → 703 modules** · 진입 **420.81 → 421.78 kB**(+0.97) · CSS 30.47 → 30.66 kB.
프론트를 읽는 백엔드 가드 3종(`test_activity_ui_labels` · `test_design_token_provenance` ·
`test_docs_indexes`) **24 passed / 364 subtests**. **backend 전수는 프로덕션 파이썬 0줄이라
재측정하지 않았다** — 기준선 `2271/1/2430` 유효.

## Issues found

| # | 문제 | 원인 | 처리 | 결과 |
|---|---|---|---|---|
| 1 | `/me/activity` 배포에서 500 | `register_auth` 만 해석 전 `core_sot`(None) 수령 | 한 줄 수정 + 주입 없는 조립 가드 2셀 | `d26059e` · 라이브 200 확인 |
| 2 | 전수 회귀 **5 failed** | **작성자 과실** — 새 브리프를 `docs/plans/README.md` 인덱스에 미등재 + 두 README 개수 주장(104/86)이 낡음 | 인덱스에 "프론트 디자인 (Phase 10)" 절 신설 · 105/87 로 갱신 | `505bc03` · 재측정 green |
| 3 | `admin` 이미지가 재빌드에서 누락 | compose 에 자체 `build:` 가 있어 별도 태그 | `docker compose build admin` 추가 실행 | 임시 수습 |
| 5 | **★ `.writing-confirm`(8.4 quota 확인 대화)이 정의된 적 없는 토큰 둘을 써서 2026-08-04 부터 테두리·배경 없이 렌더** | `var(--border)`·`var(--surface-muted, transparent)` — 후자는 fallback 이 있어 **조용히** 렌더됐다. 렌더 테스트는 CSS 를 안 보고, 이 화면은 육안 확인 목록에 있었으나 아직 안 봤다 | 실제 토큰으로 교체 + `designTokens.test.ts` 신설(그 가드가 첫 실행에서 잡았다) | `dcd2ad5` |
| 6 | body 배경이 한 단계 어두워짐 | **10.1 이 만든 결함** — `#f4f0e7` 이 페이지 배경과 침강 블록 **두 역할**을 겸했는데 일괄 매핑 | `--surface-page` 로 정정 | 배포 CSS 확인 중 발견. **가드가 못 잡는 종류**(둘 다 정의된 토큰이라 참조는 멀쩡하고 의미만 틀림) |
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
- **타이포 스코프 = ⓐ 축소 수용**(오너 2026-08-11, 독립 검증 H2 폐쇄). *"그냥 축소로 하고
  나중에 필요하면 확장하지 뭐."* **트리거**: 화면 하나를 10.3~ 에서 실제로 다시 그릴 때
  그 화면의 font-size 부터 정리한다(전역 스케일을 먼저 정하지 않는다).
  - **★ 이 결정에서 구현자가 배운 것**: 오너가 *"타이포 스코프 볼 수 있는 곳이 없네…
    뭐가 뭔지도 잘 모르겠고"* 라고 했다. **"font-size 29종"이라는 숫자만으로는 오너가
    무엇을 고르는지 알 수 없다.** 미학·UI 판단을 물을 때는 **화면이나 실물 예시**를 함께
    내야 한다 — 안 그러면 오너는 판단이 아니라 위임을 하게 된다.
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
- **WCAG 2.2 AA 30짝 전수 검산, 실패 0.** 본문 4면은 AAA 로 잡았다
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

**backend test-mongo ON `2271 passed / 1 skipped / 2430 subtests`**(2026-08-11 베타 실측,
1093초 — Slice 10.1). **셀 +3 · subtest +63**, 귀속:

- **셀 +3 · subtest +62** = 신규 [`test_design_token_provenance.py`](../../../tests/test_design_token_provenance.py)
  (primitive 28짝 대조 + 대비 30짝 + 본문 AAA 4면)
- **subtest +1** = 검증 기록 한 건(`bd2c679`, 오너의 10.0 독립 검증) — `test_docs_indexes.py`
  의 판정 열 전수 셀이 기록 한 건당 1 오르는 자리이며 **코드와 무관하다**

frontend **294 passed / 22 files** · build **702 modules · 진입 420.81 kB 무변** ·
CSS 26.62 → 30.47 kB.

### ★ 재현되지 않은 이상 현상 하나 (무시하지 말 것)

전수 회귀 직후 `test_design_token_provenance.py` 단독 실행이 **한 번** `1 failed /
61 subtests` 를 냈다(정상은 `3 passed / 62 subtests`). 그 뒤 **20회 연속 재실행 전부
통과**했고, 트리는 clean·같은 커밋이라 두 실행이 **같은 바이트를 읽었다** — 즉 코드가
아니라 읽기가 흔들린 것으로 보인다. **이 세션에서 같은 마운트가 `HANDOFF.md` 에 허위
`ENOENT` 를 두 번 냈다**(쓰기는 성공했는데 에러를 반환). WSL/drvfs 의 일시적 읽기 문제로
추정하되 **단정하지 않는다.** 같은 증상이 다시 보이면 파일시스템으로 넘기기 전에
`git status` 와 생성기-CSS diff 를 먼저 본다.

**그 아래는 이력이다** — 종전 backend `2268 passed / 1 skipped / 2367 subtests`(2026-08-11 베타 실측,
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
