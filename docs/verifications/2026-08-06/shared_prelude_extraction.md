# 공유 prelude 추출(2f20fbb·2d68630·635d84b) 독립 검증 — H-3-A 순환 폐쇄

- **날짜**: 2026-08-06
- **의뢰자**: 오너("작업 AI가 작업한 거 확인해서 검증하고 의심하고 또 의심해줄래?")
- **검증자**: Claude Code(독립 세션 — 이 슬라이스 구현에 관여하지 않음)
- **검증 대상**: 커밋 3개 `2f20fbb..635d84b`(HEAD `635d84b`, 작업 트리 clean). 성격별 3종:
  1. `2f20fbb` — 본 코드. `main.py` 의 prelude 135 노드(134 이름)를 `app/env.py`·`app/api/{models,errors,dependencies}.py` 로 본문 byte-동일 추출. routers 가 `..main` 대신 `..api`·`..env` 를 본다.
  2. `2d68630` — 별칭 소실 복구(`require_project_owner as owner`)+ 모듈 동일성 셀 신설.
  3. `635d84b` — work_log·HANDOFF·결정 브리프 결과 기록 + 회귀 기준선 2196/1/1933.
- **정본 참조**: 검증 절차 [`docs/guides/verification.md`](../../guides/verification.md). 착수 결정 [`docs/plans/router-split-shared-prelude-decisions.md`](../../plans/router-split-shared-prelude-decisions.md). 이 슬라이스의 계약은 **"행위 무변 + `main↔routers` 순환 폐쇄"** 이다(브리프 §1).
- **작업 출처**: 커밋(`2f20fbb`→`635d84b`, committed; working tree 미사용). 뮤테이션은 throwaway worktree.

---

## Scope

구현자 보고를 hypothesis 로 취급해 7개 표면을 각각 독립 재실측한다.

1. **순환 폐쇄(H-3-A)** — 분해 전엔 죽던 로드 경로가 살아 있는가.
2. **행위 무변** — 조립된 `create_app()` 의 공개 표면 지문이 pre 와 동일한가.
3. **이동 무결성** — 이동이 복사가 아니며(move not copy), 중복 정의가 없는가.
4. **이름 해석** — 이동 코드가 `main.py` 잔류분 이름을 참조하거나(잠재 호출시점 NameError), `main.py` 가 이동명을 import 없이 참조하는가.
5. **본문 byte-동일** — 함수·상수 본문이 분해 전과 한 글자 같은가(값 변경 = 행위 변경).
6. **가드 양방향 물림** — 신규 셀이 under-strict·over-strict 양쪽에서 진짜로 무는가(뮤테이션).
7. **전수 회귀** — 보고 기준선 2196/1/1933/0 이 재현되는가.

---

## Methodology

모든 실측은 repo root `/mnt/d/devel/에베베/ai_writte_system` 에서 `python3`(system, fastapi 0.127.0·pydantic 2.12.5·pytest 9.0.2 내장). `test-mongo`(127.0.0.1:27020, healthy) 기동 확인 후 회귀.

- **정적**: `grep`·`git show`·`wc -l`·AST(`ast.get_source_segment` 로 pre/post 본문 비교, 미정의 전역 참조 탐지).
- **동적(로드)**: `python3 -c "from services.application.app.main import app"` / 라우터 먼저 import / `python3 -m services.application.app.main`.
- **행위 지문**: 커밋된 [`docs/verifications/2026-08-05/repro_router_split.py`](../2026-08-05/repro_router_split.py) 를 pre(`git worktree add /tmp/pre_prelude 10502a6`)와 HEAD에서 각각 돌려 `diff`.
- **뮤테이션**: `git worktree add /tmp/mut_prelude HEAD` 후 sed 1줄 변형 → `pytest` → `git checkout --` 원복 → `git status --short` 공백 확인(매번).
- **회귀**: `python3 -m pytest tests/ -q -p no:cacheprovider`.

---

## Findings

### 1. 순환 폐쇄 — 죽던 경로 3종 부활 확인

| 로드 경로 | 분해 전(종전 기록) | HEAD 실측 |
|---|---|---|
| FQ `from services.application.app.main import app` | OK(유일한 생존 순서) | **OK, routes total = 80** |
| 라우터 먼저 `import routers.admin`·`routers.auth` | ImportError | **OK** |
| `python3 -m services.application.app.main` | circular import | **exit 0** |

세 경로 전부 산다 → `main↔routers` 순환이 사라졌다. 의존 그래프를 직접 읽어 사유 확인: `main → {api.*, routers, env}` · `routers → {api.*, env}` · `api → {env, 외부}` · 역방향 간선(main 을 향함) 0. `routers/*` 의 `from ..main` 매치는 `routers/__init__.py:11` 의 **경고 주석**이 유일(grep).

### 2. 행위 무변 — 지문 IDENTICAL (독립 재실측)

`repro_router_split.py` pre(10502a6) vs post(HEAD) JSON **byte-동일**:

```
route_count = 76              (양쪽 동일)
order_sensitive_pairs = 0     (양쪽 동일)
openapi_sha256 = f8b42ef191d95a2341debb0c879805b31ebc5c351dac1ca3c4ee51b2f809cfa1  (양쪽 동일)
```

지문은 (path,method) 76개 집합 · 라우트별 **해석된 의존성 트리**(`_REQUIRE_*` 보안 배선 포함, OpenAPI엔 안 나옴) · status_code · response_model · responses 키 · `app.openapi()` 전체 sha256 을 잰다. 134 정의 이동이 이 표면을 한 글자도 안 움직였다.

### 3. 이동 무결성 — 복사가 아니라 이동, 중복 0

이동명 샘플 13개(`_env_int`·`require_project_owner`·`enforce_quota`·`_ERRORS_404`·`_protected`·`_REQUIRE_PROJECT_OWNER_BILLABLE` 등)를 `main.py` 에서 grep → **정의/대입 0건**(전부 new 모듈로 옮겨갔고 main 잔존 없음). `main.py` 는 line 1596(`.env`)·1600(`.api.models`)·1639(`.api.errors`)·1658(`.api.dependencies`)에서 이동명을 다시 import 한다. 재수출 shim 을 **의도적**으로 안 둔 것은 건전하다(브리프: shim 을 두면 `patch` 가 조용히 빗나간다).

### 4. 이름 해석 — 숨은 순환/NameError 0 (양방향 AST)

가장 미묘한 위험(이동 함수가 `main.py` 잔류분 이름을 참조 → import/build엔 안 드러나고 **호출시점 NameError**)을 AST 로 직접 잡는다.

- **이동 코드 → 미해결 전역 참조**: `env`·`models`·`errors`·`dependencies` 4모듈 전부 **0건**(walrus `:=` 바인딩 보정 후). 이동 코드는 main 잔류분 이름을 하나도 참조하지 않는다. 전이 폐숬(134 이름)가 정확히 닫혔다.
- **main.py → 이동명 import 누락**: main.py 가 참조하는 이동명 80개, 전부 import/정의에 있음 → **누락 0건**.

### 5. 본문 byte-동일 — 14 샘플 전부 IDENTICAL

`ast.get_source_segment` 로 pre(10502a6 main.py) vs post(new 모듈) 본문을 직접 비교:

- 함수 6: `enforce_quota`(70줄)·`require_project_owner`(57)·`require_admin_user`(11)·`_provider_error_status`(19)·`_billable`(19)·`_env_int`(5) — 전부 **BYTE-IDENTICAL**.
- 상수/대입 8: `CONFIRM_DUPLICATE_HEADER`·`_REQUIRE_PROJECT_OWNER_BILLABLE`·`_STORAGE_503`·`_QUOTA_REFUSAL_STATUS`·`_ERRORS_404`·`_ERRORS_ADMIN`·`_ERRORS_STORAGE`·`_ERRORS_404_502_CONFIG`(AnnAssign 포함) — 전부 **BYTE-IDENTICAL**.

"본문 byte-동일" 주장은 사실이다. 값 변경(=행위 변경) 흔적 없음.

### 6. 가드 양방향 물림 — 3 뮤테이션 전부 재실패 (독립 재현)

`/tmp/mut_prelude` worktree(HEAD)에서 각 1줄 변형 → `git checkout --` 원복 → `git status --short` 공백 확인 매 수행.

| 뮤테이션 | 재실패 셀 | 뜻 |
|---|---|---|
| **M1** admin.py `from ..api.dependencies import` → `from ..main import` (순환 재도입) | **5 method** 사망: FQ 로드·short 로드·`router-먼저`(admin subtest)·`python -m`·모듈 동일성 | 순환 가드가 강하게 물림 |
| **M2** main.py 라우터 import 상대→절대 | **ONLY** 모듈 동일성 셀 1개 | 새 모듈 동일성 셀이 정확히 "상대 import" 성질을 잠금 |
| **M3** `require_project_owner as owner` → 별칭 제거 | **9 subtest** 사망(`BillableRouteWiringTest::test_enforcement_is_declared_after_ownership`) | HANDOFF 예고 "요청 구동으로는 안 보인다" 자리가 실제로 잠김 |

M3 는 구현자가 1차 회귀에서 겪은 9건 실패의 재현이기도 하다(별칭 복구 = `2d68630`). M2 의 모듈 동일성 셀은 구현자가 **독스트링이 거짓이 될 뻔했음을 뮤테이션으로 발견하고 신설**한 셀이다 — 추출 뒤 순환이 사라져 기존 2셀(FQ·short)은 상대/절대를 못 가리게 됐고, 그 빈 자리를 이 셀이 대신한다. 구현자 자기 신고와 정확히 일치.

> 셀 수 표기 차이: 구현자는 M1 을 "4 cells"라 했고, 본 검증 실측은 **5 method**(4 메서드 + admin subtest; auth subtest는 admin 만 변형해 통과). 라벨링 차이일 뿐 순환 가드가 물린다는 본질은 양쪽 일치.

### 7. 전수 회귀 — 기준선 완전 재현

```
2196 passed, 1 skipped, 1933 subtests passed, 0 failed   (1130.97s)
```

구현자 보고(2196/1/1933/0, 990s)와 **건수 완전 일치**. 시간 차(990s→1131s)는 기계 부하. 회귀는 지문이 놓칠 수 있는 런타임 경로(이동 함수 본문의 실 호출)까지 덮는 안전망이다 — 0 failed 로 이름 해석(§4)의 런타임 측면도 확인.

---

## Issues / Risks

### Blocking (계약 위반) — 없음

순환 폐쇄(계약 1)·행위 무변(계약 2)·이름 해석 무결성·가드 양방향 물림 전부 입증됐다. boundary 의 empty cell 없음.

### Hardening (비차단)

- **보고 수치 사소 오차 2건**(행위·계약 무관):
  - `main.py` post 줄 수: 보고 **4,806** / 실측 **4,808**(2줄; pre 5,843 은 정확). `5843 - 1163 + 128 = 4808`.
  - M1 셀 수: 보고 "4 cells" / 실측 5 method(subtest 라벨링).
  - "135 노드(134 이름)"은 노드 수 vs 이름 수 — 불일치 아님(커밋 메시지로 확인).
- **구현자 자기 신고 3건 전부 정확**: ①독스트링 거짓 발견·정정 ②9건 별칭 실수·복구 ③브리프 §4 "테스트 파급 0" 오측 표시(취소선 + §9 정정, "틀린 채로 남겨 둔다" 명시). 검증이 이 셋을 독립 확인했다.

---

## Verdict — **합격**

이 슬라이스는 계약(행위 무변 + 순환 폐쇄)을 완전히 닫는다. 근거:

1. **행위 무변**: 지문 pre/post **IDENTICAL**(route 76·order-pairs 0·openapi sha `f8b42ef1…`). 의존성 트리·response_model·status·responses·openapi 전체가 불변.
2. **순환 폐쇄**: 죽던 로드 경로 3종(FQ·라우터 먼저·`python -m`) 부활. 역방향 간선 0.
3. **이동 무결성 + 이름 해석**: 중복 정의 0, 미해결 전역 참조 0(양방향), 본문 byte-동일(14 샘플).
4. **가드**: 신규 셀이 양방향으로 물림(M1·M2·M3). HANDOFF 가 "안 보인다" 한 자리(M3)가 실제로 잠김.
5. **회귀**: 2196/1/1933/0 재현.

Blocking 0. 사소 보고 오차 2건은 hardening 으로 남기고 판정에 영향 없음.

---

## Outstanding

- 이 슬라이스는 **독립 검증 완료**(구현자 자기검증 상태에서 벗어남). HANDOFF Next Tasks 1번(잔여 7 도메인 이동·Slice 2 `create_admin_app()`)의 선행이 닫렸다 — 이제 `routers.admin` 을 그냥 import 할 수 있어 Slice 2 가 제품 앱을 짓지 않는다.
- 회귀 중 `test-mongo`(27020) 사용. 스택은 그대로 둠.
- 본 검증은 코드를 고치지 않았다(검증 기록·인덱스만 추가).

---

---

## 보강 패스 (2026-08-06, 구현자 세션 — 지적 반영 + 표본 한계 폐쇄)

검증자가 올린 Hardening 2건을 닫고, **표본으로 남겨 둔 축 하나를 전수로 바꿨다.** 판정(합격)은 바뀌지 않는다.

### S1. 지적 2건 반영 — 둘 다 검증자가 옳다

| 지적 | 확인 | 처리 |
|---|---|---|
| `main.py` post 줄 수 **4,806 → 실측 4,808** | 네 커밋(`2f20fbb`·`2d68630`·`635d84b`·`9b400d2`) **전부 4,808**. pre `10502a6` = 5,843 정확 | **원인은 인용 시점이다** — 4,806 은 생성기가 뱉은 **중간 출력**(routers import 주석을 재작성하기 전)이고, 그 뒤 주석 2줄이 늘었는데 구현자가 중간값을 최종값으로 옮겨 적었다. HANDOFF·브리프 §9·work_log 3곳을 4,808 로 정정하고 **왜 틀렸는지도 함께 적었다** |
| M1 셀 수 "4 cells" vs 실측 **5 method** | 둘 다 맞다 — **기준 시점이 다르다** | 구현자의 M1 은 모듈 동일성 셀을 **넣기 전**에 돌아 그때 파일에 4 cells 뿐이었다. HEAD 기준으로는 5 다. 브리프·work_log 표에 그 시점을 명시했다(검증자 수치가 현행 기준) |

### S2. ★ 표본 한계를 전수로 닫았다 — 본문 byte-동일 14 샘플 → **134 전수**

§5 는 함수 6 + 상수 8 = **14 샘플**로 byte-동일을 확인했다. 이 추출의 계약이 *"본문 byte-동일"* 이므로 **표본이 아니라 전수가 맞는 축**이다. AST 로 pre(`10502a6` `main.py`)와 post(4개 새 모듈)에서 같은 이름의 정의 구간을 각각 잘라 문자열 비교했다:

```
이동 이름 134개 전수 대조 (샘플 아님)
  BYTE-IDENTICAL : 134
  본문 상이       : 0
  pre 에 없음     : 0
```

**134/134 일치.** 이로써 "샘플은 같지만 나머지 120개 중 하나가 다르다" 는 가능성이 닫혔다. 지문 IDENTICAL·전수 회귀와 **독립적인 축**이라는 점이 요점이다 — 앞의 둘은 *동작*을 재고 이것은 *본문*을 잰다.

### S3. 이 기록 자신의 결함 하나 — 인덱스 행이 깨져 있었다

[`docs/verifications/README.md`](../README.md) 의 본 기록 행이 **판정 열 구분자(`|`)를 하나 빠뜨려** 3열이어야 할 행이 2열이었다(파이프 3개, 정상 4개). 그래서 **판정 `합격` 이 설명 칸에 먹혀** 표의 판정 열이 비어 있었다.

- **`test_docs_indexes.py` 는 통과했다** — 그 가드는 분포 표의 **합계**와 링크만 보고 **행 구조는 안 본다**. 2026-08-06 앞선 기록이 올린 *"판정 분포 가드의 간극"* 이 **바로 이 형태로 실제 발현한 것**이다.
- 발견 경로는 [`tally_verification_ledger.py`](tally_verification_ledger.py) 였다 — 대조 후보가 17 → **18** 로 늘어 새 행이 잡혔다. 구분자를 복구하니 **17 로 복귀**(원래 후보 수)했다.
- **교훈**: 인덱스에 행을 더할 때 **파이프 개수를 세는 것**이 마크다운 렌더보다 빠른 확인이다.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
# 행위 무변 지문 (pre vs post)
git worktree add /tmp/pre_prelude 10502a6
( cd /tmp/pre_prelude && python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/pre.json 2>/dev/null )
python3 docs/verifications/2026-08-05/repro_router_split.py > /tmp/post.json 2>/dev/null
diff /tmp/pre.json /tmp/post.json && echo IDENTICAL          # → IDENTICAL
git worktree remove --force /tmp/pre_prelude

# 순환 폐쇄 (3 경로)
python3 -c "from services.application.app.main import app; print(len(app.routes))"   # 80
python3 -c "import services.application.app.routers.admin, services.application.app.routers.auth"  # OK
python3 -m services.application.app.main; echo exit=$?                              # exit=0

# 뮤테이션 (throwaway worktree; 매번 git checkout -- 원복 + git status --short 공백 확인)
git worktree add /tmp/mut_prelude HEAD
cd /tmp/mut_prelude
# M1: sed -i 's/^from \.\.api\.dependencies import (/from ..main import (/' services/application/app/routers/admin.py
#   → pytest tests/test_app_import_paths.py  (5 failed)
# M2: sed -i 's|^from \.routers\.admin import register_admin|from services.application.app.routers.admin import register_admin|' services/application/app/main.py  (auth 동일)
#   → pytest tests/test_app_import_paths.py  (1 failed: module-identity)
# M3: tests/test_quota_enforcement_api.py 573줄 'require_project_owner as owner,' → 'require_project_owner,'
#   → pytest tests/test_quota_enforcement_api.py::BillableRouteWiringTest::test_enforcement_is_declared_after_ownership  (9 failed)
git worktree remove --force /tmp/mut_prelude

# 전수 회귀 (test-mongo 27020 기동 필요)
python3 -m pytest tests/ -q -p no:cacheprovider   # 2196 passed / 1 skipped / 1933 subtests / 0 failed
```
