# H-3 폐쇄(59fe1a1) + 기록 보강 4커밋 독립 검증 — 미검증 구간(da35489..9caa76c)

- **날짜**: 2026-08-06
- **의뢰자**: 오너("작업 AI가 작업한 거 검증하고 의심하고 또 의심해줄래? … 검증 기록 보강분(38b6e3a) 이후 커밋 5개입니다 — 이게 미검증 구간 전부입니다")
- **검증자**: Claude Code(독립 세션 — 구현에 관여하지 않음)
- **검증 대상**: 커밋 5개 `da35489..9caa76c`(38b6e3a 검증 기록 이후 전량). HEAD `9caa76c`, 작업 트리 clean. 성격별 4종:
  1. `59fe1a1` — 유일 코드 변경. `main.py` routers import 절대→상대(H-3) + 신규 [`tests/test_app_import_paths.py`](../../../tests/test_app_import_paths.py) 2 cells.
  2. `da35489`·`06d2b09` — work_log Task 5·6 + HANDOFF 서술.
  3. `e55aa24` — README 검증 건수 220/합격 148 손수 정렬.
  4. `9caa76c` — HANDOFF 전수 회귀 기준선 2193/1/1931 기재(오너 지적: 이 커밋 자신도 기준선 숫자가 검증 대상이라 5개로 잡음).
- **정본 참조**: 검증 절차 [`docs/guides/verification.md`](../../guides/verification.md). H-3 원 발견 기록 [`docs/verifications/2026-08-05/router_split_slice1_auth_admin.md`](../2026-08-05/router_split_slice1_auth_admin.md) §11 + Issues/H-3. 이 슬라이스의 계약은 "행위 무변 + import 이름 무관 로드"이다.
- **작업 출처**: 커밋(`da35489`→`9caa76c`, committed; working tree 미사용).

---

## Scope

오너가 짚은 4가지 의심 지점을 각 커밋 성격에 맞춰 잰다.

1. **코드(59fe1a1)** — 수정이 H-3을 정확히 닫는가 · 신규 가드가 **양방향**으로 물리는가(under-strict + over-strict) · 작업 세션이 "미실측"이라 스스로 신고한 **다른 로드 경로**(uvicorn `--reload`·`python -m`·컨테이너 `PYTHONPATH=/app`)를 직접 잰다.
2. **기록(da35489·06d2b09)** — work_log Task 5·6 + HANDOFF 서술이 1차 소스(코드·디스크)와 맞는가. 특히 "main.py 를 파일로 읽는 테스트 0건"·"경로 하드코딩 1자리"·"뮤테이션 1종" 주장.
3. **README 건수(e55aa24)** — 손으로 고친 220/합격 148 을 디스크 실측(파일 수·판정 분포)과 대조. `test_docs_indexes.py`가 분포의 **합·반복**만 잡고 **파일별 판정**은 안 잡는 간극을 의식한다.
4. **기준선(9caa76c)** — 전수 회귀 `2193/1/1931` 이 실제로 재현되는가.

## Methodology

검증자는 구현에 관여하지 않았고, 각 주장을 1차 소스에서 재도출했다. 트리는 clean이나, **전수 suite가 main 트리에서 병행 실행 중이었으므로** 뮤테이션은 별도 throwaway worktree(`git worktree add --detach /tmp/verify-h3 HEAD`)에서 돌려 main 트리의 `main.py`(suite 가 읽는 파일)를 보호했다. pre-split 비교는 `e8b9908~5`(`98e3e93`) worktree. 행위 무변은 커밋된 [`repro_router_split.py`](../2026-08-05/repro_router_split.py) 지문(pre/post `diff`)으로, openapi sha는 저장소 제공 `scripts/dump_openapi.py` 로 교차 확인. 판정 분포는 인덱스 표(`docs/verifications/README.md` 판정 열) 합산 + "불합격" verdict 의 독립 grep 로 이중 확인. 전수 suite 는 `test-mongo`(replica set `rs-test`, `127.0.0.1:27020` healthy) 기동 후 `python3 -m pytest tests/ -q`.

```bash
git rev-parse HEAD                       # 9caa76c
git status --short                       # (비어있음)

# (1) 신규 가드 + 뮤테이션 양방향(throwaway worktree)
git worktree add --detach /tmp/verify-h3 HEAD
#   baseline: pytest tests/test_app_import_paths.py            → 2 passed
#   under-strict (import → 절대 복귀):                          → short FAIL / FQ PASS
#   over-strict (import → app.routers.* 로 FQ 파괴):            → FQ FAIL / short PASS
#   git checkout -- services/application/app/main.py (worktree clean 분기)

# (2) 미실측 로드 경로 실측(같은 worktree, clean 상태)
python3 -c "from services.application.app.main import app; print(type(app).__name__, len(app.routes))"  # uvicorn 해석
python3 -m services.application.app.main          # FQ python -m
(cd services/application && python3 -m app.main)   # short python -m
#   pre-split(e8b9908~5) worktree 에서 동일 4경로 재측 → 회귀 여부

# (3) 행위 무변 — repro 지문 pre/post diff
python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/post.json   # HEAD
(cd /tmp/pre && python3 repro.py > /tmp/pre.json)                              # 98e3e93
diff /tmp/pre.json /tmp/post.json && echo IDENTICAL
python3 scripts/dump_openapi.py | sha256sum                                    # → 1e275ab8…

# (4) README 건수 — 디스크 실측
find docs/verifications -mindepth 2 -name '*.md' | wc -l                       # → 220
python3 docs/verifications/2026-08-06/tally_verification_ledger.py             # 건수·일수·분포·파일별 판정 대조

# (5) 전수 회귀
docker compose -f docker-compose.test.yml up -d                                # test-mongo
python3 -m pytest tests/ -q                                                    # → 2193/1/1931/0failed
```

## Findings

### 1. 코드(59fe1a1) — 수정 정확, 가드 양방향 물림 ★

`main.py:2701-2702` 의 두 import 가 상대 경로(`from .routers.admin import register_admin` / `from .routers.auth import register_auth`)로 바뀌었다. router 쪽(`routers/admin.py`·`routers/auth.py`)이 `from ..main import …` 상태이므로, main 도 상대여야 **로드 이름에 무관하게** 같은 패키지 안에서 해석된다(H-3 원 기록 §11 의 처방과 일치). 모듈 맨 아래 `app = create_app()`(main.py 말단) + Dockerfile `CMD uvicorn services.application.app.main:app` 로드 경로가 이 상대 import 위에 서 있다.

**신규 가드 `tests/test_app_import_paths.py` 2 cells, 양방향 뮤테이션으로 물림 증명:**

| 뮤테이션 | 방향 | 결과(throwaway worktree) |
|---|---|---|
| `from .routers.*` → `from services.application.app.routers.*`(절대 복귀, H-3 이전) | under-strict | `test_the_short_package_name_also_loads` **FAILED** / `…_fully_qualified_name_loads` PASSED |
| `from .routers.*` → `from app.routers.*`(FQ 파괴, 단명은 유지) | over-strict | `…_fully_qualified_name_loads` **FAILED** / `…_short_package_name_also_loads` PASSED |

under-strict 는 원 기록·work_log Task 6 이 잰 것과 동일(재확인). **over-strict 는 작업 세션이 잰 적이 없는 방향**이다(work_log Task 6 line 480 "뮤테이션 (1종)"/line 486 표에 절대 복귀 1행만 있음) — 테스트 독스트링은 양방향을 주장했으나 실측은 절반이었고, **이 검증에서 나머지 절반을 채워 물림을 확정**했다. 각 뮤테이션 후 `git checkout --` 원복 + `git status --short` 공백 확인(clean-tree 분기, 안전).

### 2. 미실측 로드 경로 실측 — `python -m` 가 회귀했다 (비배포 경로) ★

오너가 "실측은 두 이름뿐"이라 지적한 경로를 HEAD(수정 포함)에서 직접 재:

| 로드 경로 | 분해 전(`98e3e93`) | HEAD(`9caa76c`, 수정 포함) |
|---|---|---|
| FQ import `from services.application.app.main import create_app; create_app()` | LOAD OK | **LOAD OK** |
| 단명 import `PYTHONPATH=services/application` + `from app.main import create_app; create_app()` | LOAD OK | **LOAD OK** ← H-3 이 복구 |
| uvicorn 해석(`from services.application.app.main import app` → 모듈 수준 `app`) | LOAD OK(FastAPI, 80 routes) | **LOAD OK**(FastAPI, 80 routes) |
| **`python -m services.application.app.main`** (FQ) | **LOAD OK(exit 0)** | **FAIL — ImportError: cannot import name 'register_admin' from partially initialized module … (circular import)** |
| `python -m app.main` (단명, `cd services/application`) | FAIL(`No module named 'services'`) | FAIL(동일) |

- **배포 진입점(uvicorn = FQ import 형태)은 정상**이다. 컨테이너 `PYTHONPATH=/app`(= repo root) 도 동일한 FQ 해석이므로 포함.
- **`python -m services.application.app.main` 이 분해가 회귀시킨 새 결함**이다: 분해 전 exit 0, 분해 후 `main ↔ routers` 순환을 `python -m` 의 `__main__`↔FQ 이중 로드가 건드려 죽는다. **H-3 의 "1줄" 상대 import 전환으로는 안 고쳐진다** — 이중 로드 자체가 순환을 재유발하기 때문(순환을 끊어야 = shared 심볼을 main.py 밖으로 빼야, H-3 범위 밖). 단명 `python -m app.main` 은 `main.py:16` 의 절대 `from services.application.app.auth.cookies import …`(main.py 전체가 절대 `services.*` 를 씀) 때문에 **분해 전부터 죽어 있었고** H-3 무관이다.
- **H-3 의 계약은 "import 이름 무관 로드"이지 `python -m` 지원이 아니다.** 원 기록 §11·커밋 메시지·테스트 독스트링 전부 `from {module} import create_app`(import 형태)만 주장하고 `python -m` 을 주장한 적 없다 → **과잉 주장(overclaim) 아님, 계약 위반 아님.** 다만 "import 경로 견고성"이라는 넓은 프레임과, H-3 이 지우려 한 바로 그 "원인과 동떨어진 순환 import 메시지"가 `python -m` 에선 여전히 뜬다. 오너가 묻는 "다른 로드 경로에서도 성립하는가"에 대한 정직한 답: **import 형태 3종(배포 포함)은 성립, `python -m` 2종은 아니다(1종은 분해 회귀).**

### 3. 행위 무변 — repro 지문 IDENTICAL ★

`repro_router_split.py` 를 분해 전(`98e3e93`)과 HEAD 에서 각각 돌려 stdout 지문을 `diff`: **차이 없음**. `route_count=76`·`order_sensitive_pairs=[]`·`openapi_sha256=f8b42ef191d95a2341debb0c879805b31ebc5c351dac1ca3c4ee51b2f809cfa1`(스크립트 문서 기대치와 일치)·routes 76개 deps/status/response_model/responses 전부 byte-동일. stderr 의 `in-routers`(pre 0 / post 12)만 다르고 이는 지문 바깥(이동 현황). `scripts/dump_openapi.py` @ HEAD sha = `1e275ab8c779a46766edbfaa9e75a38d990cab8b9c7536291a58a8f64bf270b6`(원 기록·HANDOFF 주장과 일치). → H-3 수정(및 분해 전체)이 공개 표면을 한 글자도 안 바꿨다.

### 4. 기록(da35489·06d2b09) — 서술, 1차 소스와 정합

- **"main.py 를 파일로 읽는 테스트 0건"**(HANDOFF 낡은 단언 삭제 근거): `tests/` 에서 `main.py` 를 `open`/`read_text`/정규식 으로 읽는 셀 0건(grep 비어). `test_billable_actions.py:45-57` 은 `inspect.getsource(route.endpoint)` over `app.routes` 로 **route-driven** 전환 완료 — 주장 정확.
- **"경로 하드코딩 남은 자리 하나 = test_auth_api.py:1610"**: 정확히 1곳(`("POST /admin/users", "services/application/app/routers/admin.py")`). `_create_user_flags` 가 handler 소스에서 `create_user(...)` 키워드를 직도출하려 의도적 — 주장 정확.
- **work_log "뮤테이션 (1종)"**(line 480/486): 정직하게 1종(절대 복귀)만 기록. §1 에서 내가 over-strict 를 채움.
- **"재도출 vs 1차 인용" 명시**(work_log line 421-423): modernization 뮤테이션·전수 suite(2191)를 1차 인용이라 표기한 것, 원 기록 §Reproduction 의 (D)(F) 표기와 일치 — 정직.
- 줄번호 불일치(원 기록 §11 `main.py:2693` vs work_log `2701-2`)는 59fe1a1 이 삽입한 주석 8줄 때문 — 모순 아님.

### 5. README 건수(e55aa24) — 220/합격 148, 디스크와 정확 일치 ★

- **건수**: `docs/verifications/*/*.md`(날짜 디렉터리 하위, README 제외) = **220**. 날짜 디렉터리 = **42**. README "220건 / 42일치" 정확.
- **판정 분포**: 인덱스 표(`docs/verifications/README.md` 판정 열) 합산 = **합격 148**(plain 142 + bold 6) · **조건부 합격 57** · **서술형(—) 14** · **불합격 1**, 합 220. README "합격 148 · 조건부 57 · 불합격 1 · 서술형 14" 정확.
- **"불합격 1건" 독립 검증**(포트폴리오 정문의 "절차가 형식적이지 않다" 근거): verdict 절에서 `불합격`/`FAIL` grep → 12후보 중 진짜 불합격은 [`slice_8_2b_duplicate_request_lock.md`](../2026-08-03/slice_8_2b_duplicate_request_lock.md) 1건뿐, 나머지 11은 prose 의 "fail"(재현 시 테스트가 실패 등)에 걸린 non-FAIL. **숨겨진 불합격 0건.**
- **가드의 구조적 간극(비차단)**: `VerificationCountClaimsTest`(`tests/test_docs_indexes.py`)는 분포의 **총합(=220)** 과 **README 반복**만 잡고, **각 파일의 실제 판정 ↔ 인덱스 표 분류** 대조는 안 한다. 즉 한 건을 잘못 분류해도 총합만 맞으면 green. e55aa24 의 숫자는 실측과 맞지만, 이 간극 때문에 "가드 green" 이 분포의 진실성을 증명하진 않는다 — 그래서 손실측(W2 아래)을 본 검증이 잰 것이다.

### 6. 전수 회귀(9caa76c) — 기준선 2193/1/1931 재현 ★

`test-mongo`(`rs-test`, 27020 healthy) 기동 · ES 패키지 존재(8.19.3) · 외부 12B 도달(`192.168.1.22:9080`) 확인 후 `python3 -m pytest tests/ -q`: **`2193 passed / 1 skipped / 1931 subtests / 0 failed`**(974.18s). 9caa76c 이 HANDOFF 에 박은 기준선과 **한 자리 차이 없음**. +2(2191→2193) = 신규 가드 2 cells 전부, subtests 1931 무변(operation 76 유지의 실측). skip 1 = 구조적 live Chroma 셀. 소요 974s vs 기록 919s(≈+6%, 같은 머신·같은 결과, 런 간 분산).

## Issues / Risks

### Blocking (계약 의무) — 없음

H-3 의 계약("import 이름 무관 로드" + "행위 무변")이 코드·양방향 뮤테이션·repro 지문·전수 suite 로 닫혔다.

### Hardening / 권고 (비차단)

- **H-3-A [`python -m services.application.app.main` 회귀] — 오너 결정 사안.** §2 참조. 분해가 만든 `main ↔ routers` 순환이 `python -m` 의 이중 로드에서 드러나, 분해 전 exit 0 이던 경로를 circular import 로 죽인다. **H-3 의 1줄 처방으로는 안 닫힌다**(순환 자체를 끊어야). 배포(uvicorn) 무관이므로 차단은 아니나, (a) H-3 테스트 독스트링/원 기록 에 "import 형태 한정, `python -m` 은 범위 밖"을 한 줄 명시하거나, (b) `python -m` 지원이 필요하면 shared 심볼을 `main.py` 밖으로 빼 순환을 제거(Slice 2 설계와 함께 보는 것이 자연스럽다). 어느 쪽이든 오너가 정한다.
- **판정 분포 가드의 간극(§5)** — `test_docs_indexes.py` 가 총합·반복만 잡고 파일별 판정 대조를 안 한다. 지금 숫자는 맞지만, "한 건 잘못 분류해도 green" 인 형태. 분포의 진실성도 디스크에 묶는 셀을 추가하면 완전히 닫힌다(비차단 — 현재 위반 0건).
- **기준선 소요 시간 분산** — 919s(기록) vs 974s(본 검증). 결과 무변이 요점이나, HANDOFF 에 초 단위 단정을 남길 때 런 간 ±수% 를 전제로 적는 것이 위험 낮다.

## Verdict

**합격(PASS) · Blocking 0.**

5개 커밋 중 유일 코드 변경인 `59fe1a1` 은 H-3 를 정확히 닫았다: 상대 import 전환이 import 형태 3종(배포 uvicorn 포함)을 분해 전 상태로 복구했고(§2), 신규 가드가 **양방향**으로 물림을 증명했다(§1 — 특히 over-strict 는 작업 세션이 안 잰 방향을 본 검증이 채워 확정). 행위 무변은 repro 지문 IDENTICAL·openapi sha `1e275ab8…` 로 실측(§3). 기록 서술은 1차 소스와 정합(§4), README 220/합격 148 은 디스크와 정확히 일치(§5), 기준선 2193/1/1931 은 재현(§6).

비차단 3건(H-3-A `python -m` 회귀·판정 분포 가드 간극·소요 시간 분산)은 합격을 가리지 않는다. **H-3-A 가 오너가 묻는 "다른 로드 경로"에 대한 정직한 답**이다 — import 형태(배포)는 성립, `python -m` 은 분해 회귀 1종 + 사전 존재 1종. H-3 의 명시적 계약(import 형태)을 넘지 않으므로 차단 아니다.

## Outstanding items

- **이 기록은 커밋되지 않았다**(검증자는 커밋하지 않는다 — [`docs/guides/verification.md`](../../guides/verification.md) · HANDOFF Next Tasks #0). 오너가 커밋할 때: ① 인덱스 [`docs/verifications/README.md`](../../verifications/README.md) 표에 본 행 추가 ② 건수 220→**221**(최상위 `README.md` 2곳·`docs/README.md` 1곳·`docs/verifications/README.md`) ③ 판정 분포 "합격 148→**149**"(조건부 % = 57/221 = 25.8→26 % 무변). `VerificationCountClaimsTest` 가 이 동기화를 검증한다.
- **H-3-A 처리 여부 = 오너 결정.** (a) 범위 명시 한 줄, 또는 (b) Slice 2 와 함께 순환 제거.
- **push 미수행** — 5개 커밋 + 본 기록 전부 main 에만 있고 오너 push 대기.
- **test-mongo 기동 중** — 본 검증이 올린 `ai_writte_system-test-mongo-1`(27020). 종전 절차(쓸 때 올리고 끝나면 내린다)대로 오너 판단.

---

## 보강 패스 (2026-08-06, 오너 세션 — 검증자와 다른 세션)

검증자가 남긴 Outstanding items를 닫으면서, **인용하지 않고 다시 잰 것**과 **위 본문을 정정하는 것**을 여기 분리해 적는다. 판정(합격)은 바뀌지 않는다.

### B1. 재측정 — 본문 주장 3건을 독립 재현

| 주장 | 본문 | 이 보강 패스의 실측 | 판정 |
|---|---|---|---|
| `python -m services.application.app.main`이 **분해로 회귀**했다(§2) | HEAD FAIL / pre-split exit 0 | HEAD = `ImportError: cannot import name 'register_admin' from partially initialized module … (circular import)` @ `main.py:2701` · pre-split(`98e3e93`) worktree = **exit 0** | **재현됨** |
| uvicorn 해석·단명 import는 성립(§2) | LOAD OK | `from services.application.app.main import app` → `FastAPI 80 routes` · `PYTHONPATH=services/application` + `from app.main import create_app` → OK | **재현됨** |
| 디스크 건수 220 / 42일치(§5) | 220 / 42 | 본 기록 추가 **전** 220 / 42, 추가 **후** 221 / 43 | **재현됨** |

### B2. ★ 정정 — §5 "현재 위반 0건"은 실측과 다르다

본문 §5·Hardening 2번은 판정 분포 가드의 간극을 정확히 짚었으나 **"현재 위반 0건"**이라고 닫았다. 그 간극을 실제로 재 보니 **대조 후보 17건**이 있다(본 기록 자신 제외). 집계는 커밋된 [`tally_verification_ledger.py`](tally_verification_ledger.py)로 재현한다.

두 가지 모양이며 **성격이 다르다**:

- **(A) 판정 절이 있는데 인덱스는 서술형(`—`) — 13건.** 인덱스는 서술형을 *"초기 기록(판정 문구가 정형화되기 전)"*으로 정의하는데, [`2026-07-27/auth_d8_slice1.md`](../2026-07-27/auth_d8_slice1.md)는 `## Verdict — **조건부 합격(Conditional pass)**`를 명시하고도 `—`다. 초기 기록이 아니다.
- **(B) 파일은 `합격`, 인덱스는 `조건부 합격` — 4건.** 전부 **승격 기록**이다([`llm_gateway_f1_f2_closure`](../2026-06-24/llm_gateway_f1_f2_closure.md)·[`agent_loop_a2_registry`](../2026-06-25/agent_loop_a2_registry.md)·[`phase2a_analysis_http_api_i1_closure`](../2026-06-30/phase2a_analysis_http_api_i1_closure.md)·[`rail-tab-layering`](../2026-07-22/rail-tab-layering.md) — 본문이 *"조건부 합격을 합격으로 승격한다"*). **파일은 최종 판정을, 인덱스는 발행 시점 판정을 말하고 있다** — 어느 쪽이 정본인지는 정해진 적이 없다.

**그래서 재분류하지 않았다.** (A)는 인덱스 오분류로 보이고 (B)는 *정의 미확정*이라, 고치면 포트폴리오 정문의 "조건부 합격 26%"가 함께 움직인다(위로). 오너 결정 사안으로 추적 부채에 올렸다.

**이 보강 패스의 자기 신고**: 위 집계의 초판 파서가 **5건을 오분류했다** — 넓은 창을 봐서 판정 뒤 근거 문장의 "조건부"를 주웠고, 어순이 뒤집힌 `합격(조건부)`([`session_close_state`](../2026-07-31/session_close_state.md))를 놓쳤다. 판정 **문장 한 줄**만 보도록 좁혀 재실행한 것이 위 숫자이며, 스크립트 주석에 그 실측을 남겼다. **자동 분류는 후보를 좁힐 뿐 판정을 대신하지 못한다**는 것이 이 자리의 교훈이다.

### B3. 같은 병의 세 번째 자리 — README 회귀 기준선이 가드 밖에서 낡아 있었다

본문이 §6에서 기준선 `2193/1/1931`을 재현했는데, **최상위 [`README.md`](../../../README.md) 절차 표 ②는 `2,170 passed`에 얼어 있었다**(디스크 실측·work_log·본 검증 셋 다 2,193). 건수·분포와 **같은 병**(가드 밖의 숫자 주장)이고, 검증 기록 건수와 달리 **테스트 수 주장은 가드가 구조적으로 불가능하다**(전수 suite를 돌려야 알 수 있다). 이 보강 패스에서 2,193으로 정렬했고, "가드 없는 숫자 주장"으로 추적 부채에 등재했다.

### B4. Outstanding items 처리

| 항목 | 처리 |
|---|---|
| 인덱스 표에 행 추가 | 완료([`docs/verifications/README.md`](../README.md) `### 2026-08-06`) |
| 건수 220→221 (4곳) · 일수 42→**43**(2곳) | 완료. **본문 Outstanding은 일수 갱신을 빠뜨렸다** — 새 날짜 디렉터리를 만들었으므로 `_DAY_COUNT_CLAIMS` 2곳도 함께 움직인다(안 고치면 `test_every_stated_day_count_matches_the_directories_on_disk` 실패) |
| 판정 분포 합격 148→149 | 완료. 인덱스 표의 "27%" 서술도 26%로 정렬 — **그 자리는 가드 밖이었다**(가드는 최상위 README의 백분율만 본다) |
| `VerificationCountClaimsTest` 확인 | `python3 -m pytest tests/test_docs_indexes.py -q` → **12 passed / 10 subtests** |
| §Methodology의 `/tmp/tally_ledger.py` | 커밋된 [`tally_verification_ledger.py`](tally_verification_ledger.py)로 대체(선례 `repro_router_split.py` — `/tmp`를 가리키는 재현 경로는 재부팅 한 번에 사라진다) |
| H-3-A 처리 방향 | **오너 결정 대기.** HANDOFF 추적 부채에 등재 |
| test-mongo(27020) | 기동 유지 — 종전 절차대로 쓰는 동안 올려 두고 끝나면 내린다 |

## Reproduction

```bash
git checkout 9caa76c && git status --short              # clean

# (A) 가드 + 뮤테이션 양방향(throwaway worktree — 전수 suite 병행 시 트리 보호)
git worktree add --detach /tmp/v HEAD
(cd /tmp/v && python3 -m pytest tests/test_app_import_paths.py -q)                 # 2 passed
# under-strict: sed -i 's|^from \.routers\.admin|from services.application.app.routers.admin|; s|^from \.routers\.auth|from services.application.app.routers.auth|' services/application/app/main.py
#   → pytest tests/test_app_import_paths.py -q   ⇒ 1 failed(short) / 1 passed(FQ)
# over-strict: sed -i 's|^from \.routers\.admin|from app.routers.admin|; s|^from \.routers\.auth|from app.routers.auth|' services/application/app/main.py
#   → pytest tests/test_app_import_paths.py -q   ⇒ 1 failed(FQ) / 1 passed(short)
git -C /tmp/v checkout -- services/application/app/main.py && git -C /tmp/v status --short   # 비어있음

# (B) 미실측 로드 경로 + pre-split 회귀 비교
python3 -c "from services.application.app.main import app; print(type(app).__name__, len(app.routes))"   # uvicorn 해석 → OK
python3 -m services.application.app.main                                 # HEAD: FAIL(circular) / pre-split(98e3e93): exit 0
git worktree add --detach /tmp/pre 98e3e93
(cd /tmp/pre && python3 -m services.application.app.main; echo "pre FQ -m exit=$?")   # exit 0 = 회귀 입증

# (C) 행위 무변 — repro 지문 pre/post IDENTICAL
python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/post.json
cp docs/verifications/2026-08-05/repro_router_split.py /tmp/pre/repro.py
(cd /tmp/pre && python3 repro.py > /tmp/pre.json)
diff /tmp/pre.json /tmp/post.json && echo IDENTICAL                       # routes=76, order-pairs=0, sha f8b42ef1…
python3 scripts/dump_openapi.py | sha256sum                              # 1e275ab8…
git worktree remove --force /tmp/v && git worktree remove --force /tmp/pre

# (D) README 건수 — 디스크 실측
find docs/verifications -mindepth 2 -name '*.md' | wc -l                  # 220 (본 기록 추가 전)
python3 docs/verifications/2026-08-06/tally_verification_ledger.py        # 분포 148/57/1/14 + 파일별 판정 대조(B2)

# (E) 전수 회귀
docker compose -f docker-compose.test.yml up -d                          # test-mongo(rs-test, 27020)
python3 -m pytest tests/ -q                                              # → 2193 passed / 1 skipped / 1931 subtests / 0 failed
```
