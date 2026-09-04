# 착수 결정 브리프 — 공유 prelude 추출 (라우터 분해 S1, H-3-A 폐쇄)

상태: **Resolved · 구현 완료**(2026-08-06, §5=ⓑ 범주 3분할 — `app/api/models.py`·`errors.py`·`dependencies.py`)  

- **작성**: 2026-08-06
- **상위 계획**: [`router-split-and-admin-separation-decisions.md`](router-split-and-admin-separation-decisions.md) (R1·A1 = Resolved)
- **발원**: 2026-08-06 독립 검증 비차단 **H-3-A** — [`verifications/2026-08-06/h3_closure_and_record_bundle.md`](../verifications/2026-08-06/h3_closure_and_record_bundle.md) §2
- **상태**: **Resolved · 구현 완료**(2026-08-06). 방향 §3 · 배치 §5 = ⓑ(범주 분할) 확정 후 추출 완료(`2f20fbb`·`2d68630`)

---

## 1. 무엇이 문제인가 — `python -m` 은 증상이고 순환이 원인이다

라우터 분해가 **`main` ↔ `routers` 순환**을 만들었다. `routers/{admin,auth}.py` 가
`from ..main import …` 로 **31개 심볼**(모델·`_ERRORS_*`·`_REQUIRE_*`·인가 dependency)을
되가져오기 때문이다.

**지금 이 순환이 안 터지는 이유는 단 하나 — 로드 순서다.** 그 31개가
[`main.py:2701`](../../services/application/app/main.py#L2701) 의 routers import 보다 **위**에
정의돼 있어서, `main` 이 먼저 로드되면 2701 에 닿았을 때 routers 가 필요한 것이 이미 다 있다.
[`main.py:2690-2699`](../../services/application/app/main.py#L2690-L2699) 주석이 그 취약함을
이미 적어 두었다 — *"router 모듈이 가져가는 공유 심볼이 전부 이 위에 정의돼 있어야 순환 import
없이 해석된다."*

**그래서 `main` 보다 `routers` 가 먼저 오는 모든 경로가 죽는다**(2026-08-06 실측):

| 로드 방식 | 결과 |
|---|---|
| `import …app.main`(uvicorn·컨테이너·테스트 170곳) | **OK** — 유일하게 사는 순서 |
| `import …app.routers.admin` **먼저** | **ImportError**(circular) |
| `import …app.routers.auth` **먼저** | **ImportError**(circular) |
| `python -m …app.main` | **ImportError** — runpy 가 `__main__` 으로 올려 **두 번째 사본**을 새로 로드 |

### 왜 `python -m` 은 곁가지인가

`main.py` 에는 **`if __name__ == "__main__":` 블록이 없다**(말단은 `app = create_app()` 한 줄).
분해 전의 `exit 0` 은 *"로드되고 아무것도 안 했다"* 는 뜻이고, repo 안 **사용처는 0건**이다
(Dockerfile = `uvicorn …main:app`, 워커 2종 = `python scripts/*.py`). **요구사항은 `python -m`
이 아니라 import 순서 독립성**이며, `python -m` 은 그 성질을 밖에서 건드려 보는 값싼 관측
창일 뿐이다.

### 왜 지금 결정해야 하는가 — Slice 2 가 정확히 이 벽에 부딪힌다

[`routers/admin.py`](../../services/application/app/routers/admin.py#L1-L8) 자기 독스트링이
A1=ⓑ 설계를 이렇게 적어 놓았다 — *"`create_admin_app()` 가 이 `register_admin` 만 호출하는
별도 앱을 올리면 product 앱에는 `/admin` 라우트가 남지 않는다."* 그 앱은 `routers.admin` 을
import 해야 하는데 **그것이 지금 죽는 경로다.** 우회하려면 `main` 을 먼저 import 해야 하고,
그러면 말단 `app = create_app()` 이 실행돼 **80 route 짜리 제품 앱 전체가 관리자 프로세스
안에 만들어진다**(실측 2.38초).

**그리고 분해를 끝낸다고 저절로 없어지지 않는다 — 나빠진다.** 지금 `from ..main` 하는 모듈이
2개인데 잔여 7 도메인이 나가면 **9개**가 된다. 순환은 *라우트가 나가서* 사라지는 것이 아니라
**공유 심볼이 `main.py` 를 떠날 때만** 사라진다.

## 2. 선택지

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **ⓐ 범위 명시만** | 테스트 독스트링·기록에 "import 형태 한정, `python -m` 은 범위 밖" 한 줄 | 코드 0줄. `python -m` 은 잃은 기능이 없으므로 정직한 처리 | **Slice 2 가 그대로 벽을 만난다.** 그때 다시 결정해야 함 |
| **ⓑ 공유 prelude 추출** | 라우터가 보는 심볼을 `main.py` 밖으로 → routers 가 main 을 **아예 안 본다** | 순환이 개념적으로 사라짐. 이후 도메인 이동이 전부 기계적. **분해의 종착점 그 자체** | 이동 134 정의 / 956줄(§4). 한 번은 크게 움직여야 함 |
| **ⓒ 로드 순서 무해화** | routers import 를 `create_app()` 안으로 + 말단 `app = create_app()` 제거 + `uvicorn --factory` | **main.py 2줄 + Dockerfile 1줄.** 네 경로 전부 살아남(2026-08-06 worktree 실측) | 순환 자체는 남음. **ⓑ 가 오면 되돌릴 비계** |
| **ⓓ 방치** | 부채로 두고 Slice 2 에서 마주치면 그때 | 지금 비용 0 | 되던 것이 죽은 채 남고, 다음 사람이 원인과 동떨어진 메시지를 받는다 |

## 3. 결정 — ⓑ, 잔여 7 도메인보다 **먼저** (오너 2026-08-06)

오너 문언: *"이 관점이면 b로 했다가 전부 정리되면 테스트 파일 재검수가 맞나?"* → **맞다.**

**근거 셋**:

1. **ⓑ 는 H-3-A 의 수리가 아니라 라우터 분해의 종착점이다.** `main.py` 5,843줄 =
   prelude 2,704줄 + `create_app` 본문 3,138줄이고, 분해가 옮기는 것은 본문이다. 분해가
   끝나면 남는 것이 정확히 저 prelude이며, 그것이 `main.py` 에 있는 한 순환도 남는다.
2. **순서가 먼저여야 이후 7번의 이동이 기계적이 된다.** 나중에 하면 9개 모듈이 의존하는
   순환을 한꺼번에 풀어야 한다.
3. **ⓒ 는 폐기.** 3줄이지만 ⓑ 가 오면 되돌릴 비계다. ⓒ 를 추천했던 전제("ⓑ 는 비싸고
   Slice 1 잔여와 충돌한다")가 ⓑ 를 *분해의 일부*로 보는 순간 무너진다 — 충돌이 아니라 선행이다.

**범위 단서**: *"지금 2개 라우터가 쓰는 31개"로 잡지 않는다.* 그러면 도메인마다 또 옮기게 된다.
**범주 단위**로 한 번에 옮긴다(§4 의 134개).

## 4. 실측 — ⓑ 의 크기 (2026-08-06)

`main.py` prelude 정의 **181개** 중, 잔여 64 handler 가 참조하는 것 + 이미 나간 31개 +
**그것들이 서로 참조하는 전이 폐포**까지:

| 범주 | 정의 | 줄 |
|---|---|---|
| 요청/응답 모델 | 70 | 537 |
| 함수(의존성·헬퍼) | 20 | 299 |
| 상수/기타 | 20 | 57 |
| `_ERRORS_*` 에러 선언 | 20 | 50 |
| `_REQUIRE_*` 의존성 묶음 | 4 | 13 |
| **이동 합계** | **134** | **956** (main.py 의 16%) |
| `main.py` 잔류(조립 팩토리 `_default_*`·`_build_*` 43 + Protocol + `QuotaSettledRoute` 등) | 47 | ~896 |

**전이 폐포가 중요하다** — 직접 참조만 세면 88개인데, 모델이 서로를 필드로 참조하므로
실제로는 134개다. 88 로 잡고 시작하면 이동 중에 46개가 따라 나온다.

> **위 숫자는 재현 가능하다** — `python3 docs/plans/router_split_shared_prelude_sizing.py`
> ([`router_split_shared_prelude_sizing.py`](router_split_shared_prelude_sizing.py)). 이 결정을
> 지탱하는 수치이므로 `/tmp` 에 두지 않고 브리프 옆에 커밋했다(선례
> [`repro_router_split.py`](../verifications/2026-08-05/repro_router_split.py)). 추출을 진행하며
> 다시 돌리면 **남은 이동 대상이 줄어드는 것**으로 진척을 잴 수 있다.

**끝나면 `main.py` = 조립 모듈**이 된다(기본 협력자 팩토리 + `create_app` + `register_*` 호출).

### 파급 — 테스트는 0 ~~(★ 이 절은 오측이다 — §9 참조)~~

> **★ 정정(2026-08-06 구현 중 발견).** 아래 "겹침 0" 은 **틀렸다.** 실제로는 **8개 파일**이
> 이동 심볼을 `main` 에서 가져오고 있었다. 원인 둘: 측정이 ⓐ **여러 줄 괄호 import 를
> 정규식에서 제외**했고 ⓑ 비교 대상을 이동 134개가 아니라 **라우터가 쓰는 31개**로 잡았다.
> 상세와 처리는 §9. 아래 표는 **틀린 채로 남겨 둔다** — 무엇을 잘못 쟀는지가 기록이다.

| 항목 | 실측 |
|---|---|
| ⓑ 이동 대상 | 134개 |
| 테스트가 `main` 에서 직접 잡는 심볼(import·`patch`) | 13개 |
| **겹치는 것** | **0개** |

테스트가 잡는 것은 전부 `_default_*`·`_build_*` **조립 helper** 라 `main.py` 에 남는다.
모듈 수준 `app` 객체를 쓰는 곳도 [`Dockerfile:22`](../../services/application/Dockerfile#L22)
**한 줄뿐**이고 나머지 170곳은 `create_app()` 이다.

### 안전망 — 이미 있다

[`repro_router_split.py`](../verifications/2026-08-05/repro_router_split.py) 지문(route 76 ·
order-sensitive pairs 0 · openapi sha)이 **IDENTICAL** 이어야 한다. **정의만 옮기는 작업이므로
한 글자라도 달라지면 그것이 사고 신호다.**

## 5. ★ 남은 결정 — 대상 모듈 배치

134개를 **어디로** 옮기는가. 이 이름들은 9개 라우터 모듈의 import 대상이 되고 Phase 9 A7
가드도 이 자리를 지목하게 되므로, 나중에 바꾸면 비싸다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **ⓐ 단일 모듈** | `app/api_contract.py` 하나에 134개 | 이동이 가장 단순. import 한 줄 | 956줄 단일 파일 — `main.py` 의 병을 작게 재현 |
| **ⓑ 범주 3분할**(추천) | `app/api/models.py`(70+상수) · `app/api/errors.py`(`_ERRORS_*` 20) · `app/api/dependencies.py`(`_REQUIRE_*` 4 + 인가 dep) | 범주가 곧 파일이라 찾기 쉽다. **에러 선언·의존성은 전수 가드가 이미 범주로 다루는 단위**다 | 파일 3개 + `__init__` 판단 |
| **ⓒ 도메인별 분할** | `app/api/models/{project,writing,admin,…}.py` | 라우터와 1:1 | 모델이 도메인을 가로지른다(공용 payload) — **순환을 그 안에서 재생산**할 위험 |

**결정 = ⓑ**(오너 2026-08-06: *"b로 가자"*). 이 저장소의 전수 가드가 이미 "에러 선언"·"의존성 tier"를 **범주**로 다루므로
파일 경계를 같은 축에 맞추면 가드와 배치가 어긋나지 않는다. ⓒ 는 모델 간 참조(전이 폐포 46개가
바로 그 증거)가 도메인을 가로질러서 같은 순환을 작게 재현할 위험이 있다.

## 6. 마감 항목 — 테스트 파일 재검수 (결정 아님, 필수)

[`tests/test_app_import_paths.py:3-12`](../../tests/test_app_import_paths.py#L3-L12) 는
*"라우터 분해가 main 과 routers 사이에 순환을 만들었다. 그 순환은 심볼 순서로 풀리지만…"* 을
전제로 두 셀을 설명한다. **ⓑ 후엔 순환이 없으므로 그 설명이 거짓인데 셀은 그대로 통과한다.**

이 저장소가 반복해서 데인 형태다 — **가드는 살아 있는데 왜 있는지가 낡은 것**. ⓑ 후 그 가드가
잠그는 성질은 다른 것(이름 혼용 시 모듈 사본 2개 → `patch` 타깃 어긋남)이므로 **독스트링과 셀
이름을 다시 쓴다.** 재검수는 선택이 아니라 ⓑ 의 마감 항목이다.

## 7. 후속 고려

- **Slice 2(ⓑ 별도 compose 서비스)가 이 작업으로 열린다** — `create_admin_app()` 이
  `routers.admin` 을 그냥 import 할 수 있게 되고, 제품 앱을 짓지 않는다.
- **Phase 9 A7 가드**는 `main.py` 를 파일로 읽지 않아야 한다(HANDOFF 기록). 이 추출로
  "어느 파일을 읽을 것인가" 자체가 사라진다 — route-driven 가드가 자연스러워진다.
- **`python -m` 은 부작용으로 살아난다.** 그것이 목적이 아니었음을 기록해 둔다.

## 8. 유예 / 범위 밖

- **짧은 이름 `python -m app.main`** 은 어느 선택지로도 안 살아난다(`main.py` 전체가 절대
  `services.*` 를 쓴다). **분해 전부터 죽어 있었고** H-3 무관이다.
- **잔여 7 도메인의 실제 이동**은 이 브리프 범위가 아니다. 이 추출이 끝난 뒤 기계적으로 진행한다.
- **`main.py` 잔류 47개(조립 팩토리)의 재배치**는 다루지 않는다. 그것은 DI 컨테이너 논의이며
  이 저장소가 피해 온 것이다.

---

## 9. 구현 결과 (2026-08-06, `2f20fbb`·`2d68630`)

### 배치 — 3분할 + `app/env.py` (§5 ⓑ의 보완)

| 모듈 | 정의 | 내용 |
|---|---|---|
| [`app/api/models.py`](../../services/application/app/api/models.py) | 78 | 요청/응답 모델 + 그 제약·상수(`NonBlankName`·`PROJECT_BRIEF_*` …) |
| [`app/api/errors.py`](../../services/application/app/api/errors.py) | 38 | `_ERRORS_*`·`_BILLABLE_*_CONFIG` + 선언 조립 함수(`_protected`/`_owned`/`_billable`/`_admin`) |
| [`app/api/dependencies.py`](../../services/application/app/api/dependencies.py) | 17 | 인증·소유권·관리자·quota 시행 dependency + `_REQUIRE_*` |
| [`app/env.py`](../../services/application/app/env.py) | 2 | `_env_int`·`_env_bool` |

**★ `app/env.py` 는 §5 가 적은 "3분할"의 보완이다.** `_env_int`/`_env_bool` 은 **API 계약이
아니고**, 이동분(19회)과 `main.py` 잔류 조립부(7회)가 **둘 다** 쓴다 — 어느 한쪽에 넣으면
다른 쪽이 그것을 import 하며 방향이 뒤집힌다. 그래서 `api/` 밖의 별도 모듈로 뺐다.

**의존 방향은 단방향이다**: `errors → models → env`, `dependencies` 는 독립. AST 로 확인했고
(양방향 쌍 0), 이 방향이 뒤집히면 추출이 없앤 순환이 형태만 바꿔 돌아온다.

### 결과

- `main.py` **5,843 → 4,808줄**(= `5843 - 1163 + 128`). ★ 초판은 **4,806**이라 적었는데 그것은 주석 재작성 전 **생성기 중간 출력**을 최종값으로 인용한 것이다 — 독립 검증이 잡았다. `routers/*` 의 `from ..main import` **0건**.
- **행위 무변**: `repro_router_split.py` 지문 **IDENTICAL**(route 76 · order-sensitive 0 ·
  openapi sha `f8b42ef1…`).
- **되살아난 로드 경로 4종**: 라우터 먼저 · `python -m` · 짧은 이름 · uvicorn.
- 재수출 4종(`NotFound`·`AdminAuditEvent`·`QuotaEnforcementService`·`aggregate_global_kpi`)은
  라우터가 **원래 모듈에서 직접** 가져온다 — main 을 경유할 이유가 없다.

### ★ 예측이 틀린 것 하나 — "테스트 파급 0" 은 오측이었다

§4 는 겹침 0 이라 적었으나 **8개 파일이 이동 심볼을 `main` 에서 가져오고 있었다**
(`enforce_quota`·`require_project_owner`·`DEFAULT_CONTEXT_BUDGET_TOKENS` 등). 원인은 측정
스크립트가 ⓐ 여러 줄 괄호 import 를 정규식에서 제외했고 ⓑ 비교 대상을 이동 134개가 아니라
**라우터가 쓰는 31개**로 잡은 것이다. 전부 새 위치로 정렬했다.

**`main.py` 에 재수출 shim 을 두지 않은 것은 의도다.** 두면 핸들러는 새 모듈을 보는데
테스트는 `main` 을 patch 해서 **조용히 빗나간다** — 이 저장소가 H-2(shim drift)로 이미
경계하는 형태다. import 를 옮기면 틀렸을 때 시끄럽게 실패한다.

### 마감 — 테스트 파일 재검수(§6)에서 실제로 드러난 것

§6 은 "독스트링이 거짓이 되는데 셀은 통과한다" 를 예고했다. **그보다 한 겹 더 있었다**:
추출 뒤 기존 두 셀은 **상대/절대 import 를 더 이상 가르지 못한다**(뮤테이션 실측 — 절대로
되돌려도 **4 cells 전부 통과**). 순환이 있을 때만 이름 혼용이 치명적이었기 때문이다.

그래서 독스트링을 정정하고 그 자리를 대신할 셀을 새로 넣었다 —
`test_the_short_name_load_keeps_the_routers_in_one_tree` 는 짧은 이름 로드에서 라우터가
`app.routers.*` 에 사는지 단정하며, 절대 경로로 되돌리면 **그 셀만** 실패한다(1 failed /
4 passed, 실측).

### 뮤테이션

| 뮤테이션 | 재실패 | 뜻 |
|---|---|---|
| 추출 직전 코드(`10502a6`) + 새 테스트 | **새 셀 3개만**(라우터 먼저 ×2 · `python -m`), 기존 2개 통과 | under-strict — 새 셀이 기존 셀이 못 잡던 것을 정확히 잡는다 |
| `main.py` routers import → 절대 | **모듈 동일성 셀 1개만** | 정정 후 그 자리가 실제로 잠겼다 |
| 라우터가 `..main` 을 다시 import | **그 시점 4 cells 전부**(모듈 동일성 셀을 넣기 전이다 — HEAD 기준으로는 **5 method**이며 독립 검증이 그렇게 실측했다) | 물기는 하나 정상 경로까지 죽여 분리가 안 된다 |
