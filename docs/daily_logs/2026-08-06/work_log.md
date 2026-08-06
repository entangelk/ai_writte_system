# 2026-08-06 작업 로그

머신: **베타**(오너 확인). 스택은 `frontend`·`worker`·`generation_worker`만 떠 있고,
검증용 `test-mongo`(27020, healthy)를 올려 두었다.

---

## Task 1 — 미검증 구간 5커밋 독립 검증 (`da35489`~`9caa76c`) · 합격

검증자 세션(구현·기록에 관여하지 않은 세션)이 수행했다. 상세는
[`verifications/2026-08-06/h3_closure_and_record_bundle.md`](../../verifications/2026-08-06/h3_closure_and_record_bundle.md).

### User Decisions and Rationale

- **오너가 검증 범위를 5커밋으로 확정했다**(2026-08-05 HANDOFF Next Tasks #0은 4개로 적었다).
  근거: 기준선 숫자를 HANDOFF에 박은 `9caa76c` **자신도 검증 대상**이라는 것. 실제로 그 커밋의
  `2193/1/1931`이 재현 항목이 됐다.

### Completed work — 검증자 세션

- **판정 합격 · Blocking 0.** 유일 코드 변경 `59fe1a1`(H-3, routers import 절대→상대)이 계약
  ("import 이름 무관 로드" + "행위 무변")을 닫았음을 확인.
- **작업 세션이 안 쟀던 것을 채웠다** — 신규 [`test_app_import_paths.py`](../../../tests/test_app_import_paths.py)의
  **over-strict 방향**(`from app.routers.*`로 FQ 파괴 → FQ 셀만 재실패). work_log 2026-08-05
  Task 6이 "뮤테이션 1종"이라 정직하게 적은 그 빈 칸이다.
- 행위 무변 [`repro_router_split.py`](../../verifications/2026-08-05/repro_router_split.py) 지문
  pre/post **IDENTICAL**, 기준선 `2193/1/1931` 재현(974s).

### Issues found — H-3-A: 분해가 `python -m`을 죽였다 (비차단)

`python -m services.application.app.main`이 **분해 전 exit 0 → 지금 circular import**다.
`main ↔ routers` 순환을 `python -m`의 이중 로드가 건드리는 것이라 **H-3의 1줄로는 안 닫힌다**.
**배포(uvicorn·컨테이너 `PYTHONPATH=/app`)는 FQ import 형태라 무관**하고, 단명 `python -m app.main`은
분해 전부터 죽어 있었다. H-3의 계약을 넘지 않으므로 차단이 아니다 → 오너 결정 사안으로 HANDOFF 등재.

---

## Task 2 — 검증 기록 보강 패스 + 인덱스·건수 동기화

### User Decisions and Rationale

- **오너 지시**: *"검증기록 확인해서 네가 보강할 부분 보강해줄래?"* — 검증자는 커밋하지 않으므로
  기록만 남아 있었고, 인덱스 등재·건수 동기화·부채 등재가 열린 채였다.
- **판정(합격)은 건드리지 않는다**는 것을 전제로 삼았다. 보강 패스는 검증을 다시 하는 것이 아니라
  **인용을 실측으로 바꾸고 남은 것을 닫는 것**이다.

### Completed work

| 파일 | 변경 |
|---|---|
| [`verifications/2026-08-06/h3_closure_and_record_bundle.md`](../../verifications/2026-08-06/h3_closure_and_record_bundle.md) | **§보강 패스 B1~B4 추가** — 재측정 3건 · §5 정정 · 같은 병 세 번째 자리 · Outstanding 처리표. `/tmp` 재현 경로 2곳을 커밋된 스크립트로 교체 |
| [`verifications/2026-08-06/tally_verification_ledger.py`](../../verifications/2026-08-06/tally_verification_ledger.py) | **신규(커밋).** 건수·일수·분포 + **파일별 판정 대조**(가드 밖 영역)를 재현 가능하게 만든다 |
| [`verifications/README.md`](../../verifications/README.md) | `2026-08-06` 절 + 행 추가 · `43일치 · 221건` · 합격 `149` · 분포 기준일 · **"27%"→26%**(가드 밖이라 낡아 있었다) |
| [`README.md`](../../../README.md) · [`docs/README.md`](../../README.md) | 건수 4곳(220→221) · 일수(42→43) · 분포 문장(합격 149) · **회귀 기준선 `2,170`→`2,193`** |
| [`HANDOFF.md`](../../../HANDOFF.md) | Next Tasks **#0 폐쇄**(다음 작업 = 1번) · 추적 부채 3건 등재(H-3-A · 판정 분포 대조 17건 · 가드 없는 기준선 주장) |

### Issues found — 검증 기록의 "위반 0건"이 실측과 달랐다 (정정)

검증 기록 §5는 판정 분포 가드의 간극(합계만 잠긴다)을 정확히 짚고 **"현재 위반 0건"**으로 닫았다.
스크립트로 실제 대조해 보니 **17건**이 어긋난다.

- **(A) 판정 절이 있는데 인덱스는 서술형(`—`) 13건** — [`auth_d8_slice1`](../../verifications/2026-07-27/auth_d8_slice1.md)은
  `## Verdict — **조건부 합격**`을 명시하는데 `—`다. 서술형의 정의(*"초기 기록"*)에 해당하지 않는다.
- **(B) 파일은 `합격`, 인덱스는 `조건부 합격` 4건** — 전부 **승격 기록**이다. 파일은 *최종* 판정을,
  인덱스는 *발행 시점* 판정을 말한다. **어느 쪽이 정본인지 정해진 적이 없다.**

**재분류하지 않았다** — (B)는 정의 미확정이고, 고치면 포트폴리오 정문의 "조건부 합격 26%"가 함께
움직인다. 오너 결정 사안으로 HANDOFF 추적 부채에 올렸다.

### Issues found — 내 초판 파서가 5건을 오분류했다 (자기 신고)

집계 스크립트 초판이 `## Verdict` **뒤 3줄**을 창으로 봤는데, 그 창이 판정 뒤 **근거 문장**의
"조건부"를 주웠고(`합격 — 단, …조건부…`), 어순이 뒤집힌
[`합격(조건부)`](../../verifications/2026-07-31/session_close_state.md) 표기는 놓쳤다. 판정 **문장
한 줄**만 보도록 좁혀 재실행한 것이 위 17건이다. 실측을 스크립트 주석에 남겼다 —
**자동 분류는 후보를 좁힐 뿐 판정을 대신하지 못한다.**

### Verification

- `python3 -m pytest tests/test_docs_indexes.py -q` → **12 passed / 10 subtests**
  (건수·일수·분포 합·README 반복·조건부 % 전부 디스크와 정합).
- **H-3-A 독립 재현**: HEAD에서 `python -m services.application.app.main` → circular import,
  `98e3e93` worktree에서 → **exit 0**. 검증 기록의 회귀 주장 그대로.
- **로드 경로 재측정**: `from services.application.app.main import app` → `FastAPI 80 routes` ·
  `PYTHONPATH=services/application` + `from app.main import create_app` → OK.
- 집계 스크립트: `python3 docs/verifications/2026-08-06/tally_verification_ledger.py` →
  `221건 / 43일치`, 분포 합 정합, 대조 후보 17건.

### 아직 안 한 것 (의도)

- **판정 17건 재분류** — 정의(발행 시점 vs 최종)가 오너 결정 사안이라 손대지 않았다.
- **H-3-A 수리** — ⓐ 범위 명시 / ⓑ 순환 제거 중 오너 선택 전.
- **H-3 수정의 실 컨테이너 관통** — 이미지가 낡아 재빌드가 선행돼야 하고 오너 판단 사안이다.
  여전히 **아무도 컨테이너에서 뜨는 것을 보지 못했다**.
- **전수 회귀 재실행** — 이 패스는 문서·스크립트만 건드렸고 코드 0줄이라 관련 가드
  (`test_docs_indexes.py`)만 돌렸다.

### Next steps

1. **다음 작업 = HANDOFF Next Tasks 1번** — 라우터 분해 Slice 1 잔여 7 도메인, 또는 Slice 2(ⓑ).
   선행은 **H-2(shim drift 가드) 하나**다.
2. **H-3-A는 Slice 2와 함께 보는 것이 자연스럽다** — 새 진입점을 만드는 작업이라 순환 제거를
   그때 판단하면 중복이 없다.
3. 판정 분포 정의(발행 시점 vs 최종)를 정하면 인덱스 17건 정리 + 가드 셀 추가가 한 번에 닫힌다.

---

## Task 3 — H-3-A 분석 + 공유 prelude 추출 결정 브리프

### User Decisions and Rationale

- **오너가 `python -m` 중심 프레이밍을 뒤집었다**(2026-08-06). 문언: *"지금 라우터 완전 분리 전
  테스트를 진행해서 생기는 문제라는거지? 그러면 cli 명령어가 필요 없는 상황을 만들어야 되는거
  아닌가? … 이 관점이면 b로 했다가 전부 정리되면 테스트 파일 재검수가 맞나?"*
- **그 관점이 맞고, 내 직전 추천(ⓒ 로드 순서 무해화 3줄)을 폐기했다.** ⓒ 는 *"ⓑ 는 비싸고
  Slice 1 잔여와 충돌한다"* 는 전제 위에 있었는데, **ⓑ 를 분해의 일부로 보면 충돌이 아니라
  선행**이다. ⓒ 는 ⓑ 가 오면 되돌릴 비계다.
- **결정 = ⓑ(공유 prelude 추출)를 잔여 7 도메인보다 먼저.** 마감에 테스트 파일 재검수.
- **남은 결정 1건**(대상 모듈 배치)은 브리프 §5 로 올리고 멈췄다.

### Completed work

| 파일 | 변경 |
|---|---|
| [`plans/router-split-shared-prelude-decisions.md`](../../plans/router-split-shared-prelude-decisions.md) | **신규 브리프** — 문제 규명 · 선택지 4 · 결정과 근거 · 크기 실측 · 모듈 배치 3지선다(§5) · 마감 항목 · 유예 |
| [`plans/README.md`](../../plans/README.md) · [`README.md`](../../../README.md) | 인덱스 등재 + 건수 101→102 · 브리프 83→84 |
| [`HANDOFF.md`](../../../HANDOFF.md) | 추적 부채 H-3-A 항목을 **결정 완료 + 실측**으로 교체 · Next Tasks 에 **1번(공유 prelude 추출)** 신설하고 이후 번호 재정렬 |

### 실측 — 세 가지를 새로 쟀다

1. **순환의 진짜 범위**: `python -m` 만의 문제가 아니다. **`routers.admin`·`routers.auth` 를
   먼저 import 해도 ImportError** 다. 즉 `main` 이 먼저 오는 **단 하나의 순서**에서만 산다.
   그리고 그 경로가 **Slice 2(`create_admin_app()`)가 하려는 바로 그 일**이다.
2. **`python -m` 은 곁가지**: `main.py` 에 `__main__` 블록 없음(말단 `app = create_app()`),
   repo 사용처 **0건**(Dockerfile=uvicorn, 워커=`python scripts/*.py`). 분해 전 `exit 0` 은
   *"로드되고 아무것도 안 했다"*.
3. **ⓑ 의 크기**: prelude 181 정의 중 **이동 134 / 956줄**(main.py 의 16%), 잔류 47 / ~896줄.
   **직접 참조만 세면 88인데 전이 폐포가 134** — 모델이 서로를 필드로 참조한다.
   테스트 결합과의 **겹침은 0**(테스트가 잡는 13개는 전부 조립 helper 라 남는다).

### Issues found — 분해를 끝내도 순환은 안 없어진다 (프레이밍 정정)

종전 내 서술은 "H-3-A = `python -m` 회귀"였다. 그 프레임이면 **분해를 끝내면 해결될 것처럼
읽힌다.** 실제는 반대다 — `from ..main` 하는 모듈이 **2개 → 9개**로 늘 뿐이고, 순환은
**공유 심볼이 `main.py` 를 떠날 때만** 사라진다. **ⓑ 는 수리가 아니라 분해의 종착점**이다.

### Verification

- `python3 -m pytest tests/test_docs_indexes.py -q` → **12 passed / 10 subtests**(브리프 등재·건수 정합).
- 순환 재현: HEAD 에서 `routers.admin` 먼저 import → ImportError · `main` 먼저 → OK(80 routes).
- 폐기한 ⓒ 도 throwaway worktree 에서 **동작은 확인**했다(4 경로 + 가드 2 passed) — 버린
  이유는 안 되기 때문이 아니라 되돌릴 비계이기 때문이다.
- 크기 측정은 AST 기반(전이 폐포 포함). 코드 변경 0줄이라 전수 회귀는 안 돌렸다.

### Next steps

1. **모듈 배치 결정**(브리프 §5) — 추천 ⓑ `app/api/{models,errors,dependencies}.py`.
2. 결정되면 **추출 착수**. 지문([`repro_router_split.py`](../../verifications/2026-08-05/repro_router_split.py))이
   **IDENTICAL** 이어야 한다 — 정의만 옮기므로 한 글자라도 달라지면 사고 신호다.
3. 마감에 [`tests/test_app_import_paths.py`](../../../tests/test_app_import_paths.py) 재검수
   (독스트링이 거짓이 되는데 셀은 통과한다).

---

## Task 4 — 공유 prelude 추출 (ⓑ 구현, `2f20fbb`·`2d68630`)

### User Decisions and Rationale

- **오너가 배치 ⓑ 를 확정했다**(2026-08-06, *"b로 가자"*) — `app/api/{models,errors,dependencies}.py`.
  근거는 브리프 §5: 이 저장소의 전수 가드가 이미 "에러 선언"·"의존성 tier" 를 **범주**로
  다루므로 파일 경계를 같은 축에 맞춘다.
- **`app/env.py` 는 구현자 판단으로 더한 4번째 모듈**이다(§5 "3분할" 의 보완, 브리프 §9 에 기록).
  `_env_int`·`_env_bool` 은 API 계약이 아니고 **이동분(19회)과 잔류 조립부(7회)가 둘 다** 써서,
  어느 한쪽에 넣으면 다른 쪽이 import 하며 방향이 뒤집힌다.

### Completed work

| 구분 | 내용 |
|---|---|
| 신규 | [`app/api/models.py`](../../../services/application/app/api/models.py)(78) · [`errors.py`](../../../services/application/app/api/errors.py)(38) · [`dependencies.py`](../../../services/application/app/api/dependencies.py)(17) · [`app/env.py`](../../../services/application/app/env.py)(2) — 본문 **byte-동일**, 원본 정의 순서 보존 |
| `main.py` | 이동분 제거 + 새 모듈 import. **5,843 → 4,808줄** |
| `routers/{admin,auth}` | `from ..main import` **제거**. 재수출 4종은 원래 모듈에서 직접 |
| 테스트·스크립트 8파일 | 이동 심볼 import 를 새 위치로 정렬 |
| [`tests/test_app_import_paths.py`](../../../tests/test_app_import_paths.py) | 재검수 — 독스트링 재작성 + 셀 3개 신설(라우터 먼저 · `python -m` · 모듈 동일성) |

**의존 방향은 단방향이다**: `errors → models → env`, `dependencies` 독립. AST 로 양방향 쌍 0 을
확인하고 착수했다 — AST 타입(클래스/함수/상수)으로 나누면 `const ↔ deps`·`const ↔ models` 가
순환이 됐고, **용도**로 나누니 DAG 가 됐다.

### Verification

- **행위 무변**: [`repro_router_split.py`](../../verifications/2026-08-05/repro_router_split.py)
  지문 **IDENTICAL**(route 76 · order-sensitive pairs 0 · openapi sha `f8b42ef1…`).
- **되살아난 로드 경로 4종**: 라우터 먼저 import · `python -m` · 짧은 이름 · uvicorn.
- 전수 회귀: 아래 "회귀 기준선".

### 뮤테이션 (3종)

**커밋 → 뮤테이션 → 원복 순서를 지켰다**(`git status --short` 공백 확인 후 착수, 전수 suite 가
main 트리에서 돌고 있어 **throwaway worktree** 에서 수행).

| 뮤테이션 | 재실패한 셀 | 뜻 |
|---|---|---|
| 추출 직전 코드(`10502a6`) + 새 테스트 | **새 셀 3개만**(라우터 먼저 ×2 · `python -m`), 기존 2개 통과 | under-strict — 새 셀이 기존 셀이 못 잡던 것을 정확히 잡는다 |
| `main.py` routers import → 절대 경로 | **모듈 동일성 셀 1개만**(1 failed / 4 passed) | 정정 후 그 자리가 실제로 잠겼다 |
| 라우터가 `..main` 을 다시 import | **그 시점 4 cells 전부**(모듈 동일성 셀을 넣기 전이다 — HEAD 기준으로는 **5 method**이며 독립 검증이 그렇게 실측했다) | 물기는 하나 정상 경로까지 죽여 분리가 안 된다 |

### Issues found — ★ 가드가 잠그는 성질이 바뀌었는데 독스트링만 갱신할 뻔했다

브리프 §6 은 "추출 후 독스트링이 거짓이 되는데 셀은 통과한다" 를 예고했다. **그보다 한 겹 더
있었다** — 순환이 사라지자 기존 두 셀은 **상대/절대 import 를 더 이상 가르지 못한다**(뮤테이션
실측: 절대로 되돌려도 **4 cells 전부 통과**). 순환이 있을 때만 이름 혼용이 치명적이었기 때문이다.

내가 재작성한 독스트링은 그 두 셀이 "모듈 동일성" 을 잠근다고 적었는데 **그것이 거짓이었다** —
피하자고 한 형태를 내가 만들 뻔했고, **뮤테이션이 그것을 드러냈다.** 정정하고, 그 자리를 실제로
잠그는 셀을 신설했다(짧은 이름 로드에서 라우터가 `app.routers.*` 에 사는지 단정).

### Issues found — import 재작성이 `as` 별칭을 버렸다 (전수 회귀 9 subtest)

1차 전수 회귀가 **9 failed**. 전부 한 셀의 subtest 였고
(`BillableRouteWiringTest::test_enforcement_is_declared_after_ownership`), 원인은 추출이 아니라
**내 import 재작성 스크립트가 `require_project_owner as owner` 의 별칭을 버린 것**이다.

- **하필 그 셀인 것이 시사적이다** — HANDOFF 가 *"앞으로 옮기는 리팩터링은 상태코드를 하나도
  바꾸지 않으므로 요청 구동 테스트로는 안 보인다(route 선언을 읽는 셀이 그 자리다)"* 라고
  예고해 둔 자리다. 예고대로 그 셀이 유일하게 물었다.
- 별칭 복원 후 38 passed / 180 subtests.

### Decisions (구현자 판단)

- **`main.py` 에 재수출 shim 을 두지 않았다.** 두면 기존 import 가 그대로 살아 편하지만,
  **핸들러는 새 모듈을 보는데 테스트는 `main` 을 patch 해서 조용히 빗나간다** — 이 저장소가
  H-2(shim drift)로 이미 경계하는 형태다. import 를 옮기면 틀렸을 때 시끄럽게 실패한다.
- **`main.py` 의 routers import 는 상대 경로 유지.** 이제 이유가 순환이 아니라 모듈 동일성이다.

### 아직 안 한 것

- **독립 검증** — 이 슬라이스는 구현자가 자기 코드를 검증한 상태다. 다음 세션이 검증자라면
  여기부터 본다.
- **실 컨테이너 관통** — 이미지가 낡아 재빌드가 선행돼야 하고 오너 판단 사안이다.
- **잔여 7 도메인 이동 · Slice 2** — 이 추출 위에서 기계적으로 진행한다.

### 회귀 기준선

**backend test-mongo ON: `2196 passed / 1 skipped / 1933 subtests / 0 failed`**(990.12s, 실측).

- 종전 `2193 / 1 / 1931`(2026-08-05 H-3)에서 **+3 = 신규 셀 3개가 전부**다
  (라우터 먼저 로드 · `python -m` · 모듈 동일성). **subtests +2** 는 그중 라우터 먼저 셀의
  subtest 2개(admin·auth)다.
- **operation 76 은 유지**된다 — 숫자가 아니라 `repro_router_split.py` 지문 IDENTICAL 이 그
  실측이다(route 76 · openapi sha 동일).
- skip 1 = 호스트에서 구조적으로 항상 skip 되는 live Chroma 셀.
- **1차 실행은 `9 failed`였고 전부 `as` 별칭 소실이었다**(위 Issues). 코드가 아니라 import
  재작성의 실수이며, 복구 후 이 값이다.

---

## Task 5 — 공유 prelude 추출 독립 검증 반영 + 보강 (`9b400d2` 대상)

독립 세션이 **합격 · Blocking 0** 으로 검증했다
([기록](../../verifications/2026-08-06/shared_prelude_extraction.md)). 7개 표면을 전부
재실측했고, 특히 **AST 이름 해석 양방향**(이동 코드 미해결 전역 0 · `main.py` 누락 import 0)은
구현자가 안 쟀던 축이다 — 잠재 호출시점 `NameError` 가능성을 소거했다.

### Completed work — 보강 패스

| 항목 | 처리 |
|---|---|
| 지적 ① `main.py` 4,806 → **4,808** | 네 커밋 전부 4,808 확인. **원인은 인용 시점** — 생성기 중간 출력(주석 재작성 전)을 최종값으로 옮겨 적었다. HANDOFF·브리프 §9·work_log 3곳 정정 |
| 지적 ② M1 "4 cells" vs 5 method | **둘 다 맞다 — 기준 시점이 다르다.** 구현자 M1 은 모듈 동일성 셀을 넣기 전이라 파일에 4 cells 뿐이었다. 표에 시점 명시 |
| **표본 한계 폐쇄** | 본문 byte-동일이 **14 샘플**이던 것을 **134 전수**로 바꿨다 → **134/134 IDENTICAL**. 계약이 "본문 byte-동일"이므로 표본이 아니라 전수가 맞는 축이다 |
| **인덱스 행 결함** | 검증 인덱스의 새 행이 **판정 열 구분자를 빠뜨려 2열**이었다(파이프 3, 정상 4). 판정 `합격` 이 설명 칸에 먹혔다. 복구 |

### Issues found — 예고된 가드 간극이 실제로 발현했다

`docs/verifications/README.md` 의 깨진 행을 **`test_docs_indexes.py` 는 잡지 못했다** — 그 가드는
분포 표의 **합계**와 링크만 보고 **행 구조는 안 본다**. 이것은 같은 날 앞선 기록이 올린
*"판정 분포 가드의 간극(합계만 맞으면 green)"* 이 **그 형태 그대로 발현한 것**이다.

- 발견은 [`tally_verification_ledger.py`](../../verifications/2026-08-06/tally_verification_ledger.py)
  가 했다 — 대조 후보가 17 → 18 로 늘었고, 구분자를 복구하니 17 로 복귀했다.
- **그 스크립트를 커밋해 둔 것이 값을 했다.** `/tmp` 에 뒀으면 이 결함은 안 보였다.
- 판정 분포 정의(발행 시점 vs 최종)는 **여전히 오너 결정 대기**이며, 그 결정이 나면
  행별 판정을 디스크에 묶는 셀이 이 형태까지 함께 닫는다.

### Verification

- `test_docs_indexes.py` **12 passed / 10 subtests**.
- 전수 byte-동일: 이동 이름 **134/134 IDENTICAL**(pre `10502a6` vs 새 4개 모듈, AST 구간 비교).
- 건수: **222건 / 43일치**, 분포 합 222(합격 150).
- 메모리 `router-split-python-m-circular` 는 검증자가 이미 폐쇄 상태로 갱신했고 내용이 정확하다
  (의존 방향 보존 주의 · 모듈 동일성 셀 설명 포함).

### Next steps

1. **라우터 분해 잔여 7 도메인** — 이제 기계적이다. 각 이동 후 `repro_router_split.py` 지문 diff.
2. **Slice 2(`create_admin_app()`)** — 선행이 닫혔다. `routers.admin` 을 그냥 import 할 수 있다.
3. 판정 분포 정의는 오너 결정 대기(위 Issues).

---

## Task 6 — 판정 분포 정의 확정 + 17건 정렬 + 전수 가드 (`abcface`)

### User Decisions and Rationale

- **오너 결정: 판정 열 = 그 기록의 *최종* 판정**(2026-08-06). 문언: *"에잉 뭐 별거 아니잖아.
  최종 판정으로 하지 뭐. 테스트의 목적은 조건이 닫히는거니까."*
- 대안(발행 시점 판정 유지)은 *"검증이 지적을 냈다"* 는 사실 보존이 근거였는데, 오너 판단은
  **절차의 목적이 조건을 닫는 것**이라는 쪽이다. 승격 기록은 그 자체로 조건이 닫힌 증거다.

### Completed work

| 항목 | 내용 |
|---|---|
| 17건 정렬 | 인덱스 판정 열을 기록 본문의 최종 판정으로. `—` 14건 + 합격→조건부 3건 |
| 분포 | 합격 150→**154** · 조건부 57→**66** · 불합격 1→**2** · 서술형 14→**0** |
| 비율 | 조건부 **26% → 30%**(최상위 README 인용 문장 포함 갱신) |
| 신규 가드 | `VerificationsIndexTest::test_every_record_row_states_a_verdict` — 222 전수 |
| 규칙 명시 | 검증 인덱스 상단에 "판정 열 = 최종 판정" 과 정렬 이력을 적었다 |

### Issues found — ★ 불합격이 하나 묻혀 있었다

[`2026-07-29/slice1b_context_window_output_cap_reaudit.md`](../../verifications/2026-07-29/slice1b_context_window_output_cap_reaudit.md)
는 `## Verdict — **FAIL**` 이다(*"중단된 감사의 PASS/차단 0건은 폐기한다"*). 그런데 인덱스는
`—` 였고, 이를 뒤집는 후속 기록도 없다. **"불합격 1건"이라 적어 온 주장은 틀렸다 — 2건이다.**

같은 날 앞선 검증 기록이 *"숨겨진 불합격 0건"* 이라 적었는데, 그 확인은 **판정 절의 grep** 로
했고 이 기록은 인덱스에서 `—` 라 후보에 안 들어왔다. **분포를 세는 축과 본문을 읽는 축이
따로 놀면 이렇게 샌다.**

### Issues found — 정규식은 판정을 대신하지 못한다 (두 번 실측)

판정 문구가 영·한 혼용에 형식도 제각각이다(`PASS` · `Conditional pass` · `조건부 승인` ·
`합격(조건부)` · 한 기록 안에 커밋별로 두 판정). 어휘를 넓혀 두 번 돌렸더니:

- 1차(좁은 창): **5건 오분류** — 판정 뒤 근거 문장의 "조건부" 를 주움.
- 2차(넓은 어휘): **4건 오분류** — `불합격` 을 4건으로 읽음(정본 2건). prose 의 "FAIL" 에 걸림.

**그래서 17건은 전부 본문을 읽고 손으로 정했다.** 그리고 가드는 판정 문구를 **파싱하지 않도록**
설계했다 — 행 구조와 "판정 열이 비어 있지 않은가" 만 본다. 분류는 사람 몫이다.

### 뮤테이션 (2종)

**커밋 → 뮤테이션 → 원복 순서 준수**(throwaway worktree).

| 뮤테이션 | 재실패 |
|---|---|
| 한 행의 판정을 `—` 로 되돌림 | 그 기록의 subtest 1개만 (`1 failed / 231 subtests passed`) |
| 판정 열 앞 파이프 제거(2열 행) | 그 기록의 subtest 1개만 |

### Verification

- `tests/test_docs_indexes.py` **13 passed / 232 subtests**(종전 12/10 — +1 셀, +222 subtest).
- 분포 합 154+66+2+0 = **222** = 디스크 실측. 조건부 66/222 = **30%**.

### Next steps

1. **라우터 분해 잔여 7 도메인** · **Slice 2(`create_admin_app()`)** — 선행 전부 닫혔다.
2. 새 검증 기록을 등재할 때 판정 열에 **최종** 판정을 적는다(`—` 불가).

---

## Task 7 — 판정 어휘를 가이드에서 고정 + `서술형` 폐기

### User Decisions and Rationale

- **오너 지시(2026-08-06)**: 표현 불일치의 발원지가 [`docs/guides/verification.md`](../../guides/verification.md)
  라고 보고 **가이드만 고친다**(①). *"소급정리는 안하는게 나도 맞다고 봐 … 어차피 지금 파싱 비용치뤘으니까."*
  기존 222건 본문은 손대지 않는다 — 인덱스 판정 열이 이미 정본이고 가드로 잠겼다.
- **`서술형` 은 걷어낸다** — 단, 오너가 *"정말 없으려나? 못찾지는 않은건 아니지?"* 라고 확인을
  요구했고, **전수 확인 후** 폐기했다(아래 Verification).
- **문서 언어 원칙 확인**(오너 정정): **가이드·컨텍스트 지침서는 영어**, 거기서 파생돼 작성되는
  **기록물은 한글**이다. 그래서 가이드는 영문을 유지하고 **한글은 인용되는 판정 토큰에만** 남겼다.

### Completed work

| 파일 | 변경 |
|---|---|
| [`guides/verification.md`](../../guides/verification.md) | **L20(Required sections)** 이 판정 값을 열거하는 유일한 자리인데 `pass / conditional pass / fail` 이었다 → **한글 세 토큰 + 첫 줄 형식**으로 고정하고 왜 규칙인지(111가지 표현·오분류 5·4건·묻힌 불합격) 근거를 남겼다. **L29·L78** 도 같은 세 토큰으로 정렬 |
| [`verifications/README.md`](../../verifications/README.md) | 판정 분포에서 **`서술형` 행 제거**(3종) + 폐기 근거 명시 |
| [`README.md`](../../../README.md) | 분포 문장에서 `서술형 0` 제거 |
| [`tests/test_docs_indexes.py`](../../../tests/test_docs_indexes.py) | `_distribution` 4종 → **3종**, README 분포 정규식에서 서술형 제거 |

### Verification — `서술형` 이 정말 0건인가 (오너 확인 요구)

**222건 전수**로 ① 판정 절(`## Verdict`/`판정`/`결론`)이 있는가 ② 그 절 앞 5줄에 판정 어휘가
있는가를 확인했다:

```
판정 절 자체가 없음        : 0
절은 있는데 판정 어휘 없음 : 0
판정 문구 확인됨           : 222
```

**파서가 못 찾은 것이 아니라 진짜 0건이다.** `서술형` 의 정의(*"초기 기록 — 판정 문구가
정형화되기 전"*)에 해당하는 기록은 처음부터 없었고, **가이드에 정의된 적도 없다** —
인덱스 표에만 있던 장부상 칸이 `—` 14건을 흡수하고 있었다.

- `tests/test_docs_indexes.py` **13 passed / 232 subtests**.

### Decisions (구현자 판단)

- **절 제목(`## Verdict` 등)은 영문 유지.** 222/222 이미 통일돼 있고 구조 표지다 — 잘 돌아가는
  것을 흔들면 새 편차만 생긴다. 오늘 파서가 그 통일성 덕에 222건을 다 찾았다.
- **소급 정리 안 함**(오너 합의). 신규 기록부터 적용된다.

### Next steps

- 형식이 고정됐으므로, 신규 기록에 한해 **본문 첫 줄 판정 == 인덱스 판정 열**을 강제하는 셀을
  추가할 수 있다. 오늘 가드가 일부러 판정 문구를 파싱하지 않은 이유(파서 불신)가 그때 해소된다.
  **오늘 샌 축(본문 축과 인덱스 축이 따로 논 것)이 그것으로 닫힌다.**
