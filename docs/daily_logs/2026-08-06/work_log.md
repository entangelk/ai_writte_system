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
