# Slice 8.4 — 제품 경로 배선 (프론트 계약 · 확인 UX · 잔여 표시 · 부트스트랩 면제) 독립 검증

- **날짜**: 2026-08-04
- **의뢰자**: 오너("작업 AI가 작업한 거 확인해서 검증하고 의심하고 또 의심해줄래")
- **검증자**: Claude Code (독립 세션 — 구현에 관여하지 않음)
- **검증 대상**: Slice 8.4, 커밋 범위 `3f0f166^..3663148`(7건). HEAD `3663148`, 작업 트리 clean.
- **정본 참조**: `docs/system-contract-sot.md` v1.7.89 · `docs/plans/08-4-product-wiring-decisions.md`(W1~W7, Resolved) · `docs/plans/08-2b-…decisions.md:168`(H3) · `docs/plans/08-3-…decisions.md`(Q5=B)
- **작업 출처**: 커밋 `4cfd950`(GET /me/quota) · `21de2b0`(W1) · `8d59236`(프론트) · `d3194e5`(H3 가드 강화) · `3663148`(SoT v1.7.89). 모두 커밋됨(working tree 미사용).

---

## Scope

1. **정본/계약 일치성** — W1~W7 결정이 코드와 일치하는가, H3·Q5=B·W5=B 계약이 정본에 반영됐는가, 정본 내부 충돌이 없는가.
2. **잔여 단일 출처(W5=B)** — `GET /me/quota`가 잔여를 두 번째로 계산하는 자리 없이 `snapshot()` 한 곳을 지나는가.
3. **확인 통로(W3·W4)** — 429 확인이 사용자 행동에서만 나오고, 연쇄 중간의 429가 앞 단계를 재과금하지 않는가.
4. **면제(W1)** — `enforce_quota`에 tier 분기가 0줄이고, 부트스트랩 관리자만 `limit=None` 정책 행을 받는가.
5. **Q5=B vs H3 충돌 해소** — 정지(403) 판정이 `detail` 분기가 아닌 `GET /me/quota`의 `status`로 옮겨졌는가.
6. **테스트 수치 재현** — backend 2170/4/1931 · frontend 262/18 · build 699 modules·414.13 kB.
7. **뮤테이션 5종** — 가드가 실제로 물며, 특히 detail 분기 가드의 "결함→수정" 서사가 코드 히스토리로 확인되는가.

## Methodology

검증자는 구현에 관여하지 않았고, 작업자의 주장을 1차 소스(코드·테스트·커밋·스모크 출력)에서 재도출했다. 뮤테이션은 매번 `git status --short` 공백을 확인한 뒤(검증 개시 시 clean), 변이 → focused 실행 → `git checkout -- <path>` 원복 → `git status --short` 공백 + grep으로 내용 복원 확인(verification.md §Mutation testing, clean-tree 분기).

```bash
git rev-parse --short HEAD          # 3663148
git status --short                  # (비어있음)

# test-mongo 기동 + healthy 대기
docker compose -f docker-compose.test.yml up -d
until [ "$(docker inspect -f '{{.State.Health.Status}}' ai_writte_system-test-mongo-1)" = healthy ]; do sleep 2; done

# 백엔드 전체(test-mongo ON)
python3 -m pytest -q -p no:cacheprovider -rs
# → 2170 passed, 4 skipped, 1931 subtests

# 프론트: 생성물·타입·번들·회귀
cd frontend && npm run gen:api      # schema.d.ts 무변 (git diff 공백)
npx tsc --noEmit && npm run build   # 699 modules, 진입 414.13 kB
npm run test                        # 262 passed / 18 files

# 인덱스·문서 수 가드
python3 -m pytest -q tests/test_docs_indexes.py
# → 9 passed / 10 subtests
```

## Findings

### 1. 정본/계약 일치성 — 합격

- **H3 정본 정의**(`docs/plans/08-2b-…decisions.md:168`): "본문은 균일 `{"detail"}`이고 **상태코드=기계용·detail=사람용**이다. **detail 문자열로 분기하는 것은 계약이 금지**한다". v1.7.89 changelog가 이를 인용해 W2=A를 굳힌다.
- **Q5=B 상태코드 매핑**(`main.py:1663-1667`): `LOCKED→429 · EXCEEDED→402 · SUSPENDED→403`. 결정 표와 문자 그대로 일치. 정지 detail은 `"this account is suspended; …"`(`enforcement.py:302-305`).
- **W5=B 단일 출처**(`main.py:3018-3055`): 엔드포인트 본문에 집계가 없다. 주석이 계약을 못박고 `snapshot()` 한 호출만 있다.
- 정본 내부 충돌 없음. v1.7.89 changelog·tier 표(76=public 4·auth 3·admin 8·project 61)·문서 수 주장이 일관.

### 2. 잔여 단일 출처(W5=B) — 합격

`QuotaSnapshot`(`enforcement.py:130-180`)의 `remaining` = `min(일, 주)`(둘 다 `None`이면 `None`, 음수는 0 바닥). **분자·분모·시계가 한 곳을 지난다**:
- 분자 `effective_usage`(`enforcement.py:326-340`) — 시행의 `_refuse_if_exhausted`(`:342-357`)가 쓰는 **그 함수**. 원장 + 조정 + 진행 중 잠금 + async job.
- 분모 `limits_for`(`enforcement.py:376`) — P6 예약을 해석하는 `effective_limits`(`policy.py:213`).
- 시계 `_policy.now()`(`enforcement.py:379`) — 시행과 같은 clock.

repo grep으로 두 번째 계산 자리가 없음을 확인: `effective_usage` 호출처는 `_refuse_if_exhausted`·`snapshot` 둘뿐, `snapshot()` 호출처는 `main.py:3037`(프로덕션) 한 곳, `main.py`에 `.used(` 직접 호출 0건. `next_daily_boundary`·`next_week_boundary`도 정책 모듈(`policy.py:133,179`)에 있어 시행·표시가 같은 "오늘"을 말한다. 조회는 잠금·뮤텍스를 잡지 않는다(`enforcement.py:361-388`).

### 3. 확인 통로(W3·W4) — 합격

- **명시 인자만 헤더**(`client.ts:379-399`): `BillableRequestOptions.confirmDuplicate` → `billableHeaders`(`:384-387`)가 `{"X-Confirm-Duplicate":"1"}`을 **confirm일 때만** 싣는다. 유료 5함수(generate·gate·reviseAndGate·accept·analyzeVersion) 전부 이 인자를 받는다.
- **자동 재전송 없음**: 확인 패널의 `run`은 사용자 클릭 onClick에서만 실행(`WritingPanel.tsx:666-671`, `AnalysisTrigger.tsx:163-167`). `handleQuotaRefusal`(`WritingPanel.tsx:307-329`)이 `confirmable`일 때만 `setPendingConfirm`하고 자동 호출은 없다.
- **연쇄 중간 429는 그 단계만 되묻는다**: `runGate`(`WritingPanel.tsx:408-465`)가 **자기 try/catch**를 갖고 예외를 재throw하지 않는다. gate에서 429 → `runGate(produced, context, {confirmDuplicate:true})`로 **gate만** 재전송. 이미 성공한 generate를 다시 부르지 않는다. 따라서 `runGenerate`의 catch(`:386-390`)에서 `runGenerate({confirmDuplicate:true})` 재호출은 **generate 자체의 429**에만 해당한다(재과금 없음).
- **빈 헤더는 확인 아님**(`main.py:1745`): `confirmed = bool(x_confirm_duplicate and x_confirm_duplicate.strip())`. 8.3 hardening(H-5)을 8.4가 그대로 유지.

### 4. 면제(W1) — 합격

- **tier 분기 0줄**: `enforce_quota`(`main.py:1703-1772`)에 `is_admin`/tier 분기 없음(grep으로 확인 — 나머지 `is_admin`은 관리 엔드포인트 전용).
- **부트스트랩만 무제한**: `scripts/create_user.py:68-87`가 `--admin`일 때 `limit=None·None·ACTIVE` 정책 행을 `policies.upsert(QuotaPolicy(...))`로 **직접** 쓴다. `set_limits`를 쓰지 않는 것도 계약(P6 유예를 타면 첫 주 동안 기본 한도로 막힌다). `POST /admin/users`(`main.py:3073-3089`)는 정책 행을 쓰지 않아 나중에 만드는 관리자는 기본 한도.
- **over-strict 셀**(`test_quota_enforcement_api.py:692-733`): `AdminIsNotExemptTest`가 행동으로 잠근다. `test_the_enforcement_dependency_never_looks_at_the_admin_flag`(`:733`)는 `is_admin=True` 관리자가 자기 정책 행(한도 0)을 갖고 402로 막히는 것을 단정(tier 예외가 생기면 실패).

### 5. Q5=B vs H3 충돌 해소 — 합격

Q5=B가 "정지 403은 소유권 403과 겹치고 문구로 가른다"고 한 반면 H3는 `detail` 분기를 금지 — 문장 그대로 구현하면 계약 위반이다. **해소**: `describeQuotaError`(`client.ts:802-838`)는 `status`로만 분기하되, 정지 판정의 정본을 상태코드가 아니라 `GET /me/quota`의 `status`로 옮겼다 — `err.status === 403 && quota?.status === "suspended"`(`:809`)일 때만 정지, 아니면 `null`로 소유권 거절에 맡긴다. 이것이 브리프가 "W5=B가 없었으면 못 닫혔을 자리"로 적은 곳이다.

### 6. 테스트 수치 재현 — 합격(작업자 주장 그대로)

| 항목 | 작업자 주장 | 독립 실측 |
|---|---|---|
| backend | 2170 passed / 4 skipped / 1931 subtests | **2170 / 4 / 1931** (exit 0) |
| skip 사유 | 4 중 3 = elasticsearch 부재 | **3 = elasticsearch, 1 = chroma**(`-rs` 확인) |
| frontend | 262 passed / 18 files | **262 / 18** |
| build | 699 modules, 진입 414.13 kB, lazy 무변 | **699 / 414.13 kB / AdminConsole 8.39·관측 386.70** |
| gen:api | schema.d.ts 무변 | **git diff 공백**(생성물 일치) |
| 인덱스 가드 | — | **9 passed / 10 subtests** |

### 7. 뮤테이션 5종 — 전부 가드가 물음(상세 매핑)

| # | 변이(독립 설계) | 파일 | 실측 cell | 작업자 주장 |
|---|---|---|---|---|
| ① | `remaining`을 일 창만(`min` 제거) | `enforcement.py:168-172` | **3** | 3 ✓ |
| ② | `enforce_quota`에 `is_admin` early-return(admit 우회) | `main.py:1745` 뒤 | **1** | 2 |
| ③ | `billableHeaders` 상시 부착 | `client.ts:384-387` | **5** | 5 ✓ |
| ④ | `request`에 429 자동 재전송 | `client.ts:52-60` | **4** | 3 |
| ⑤ | `describeQuotaError`를 `detail` 분기(H3 위반) | `client.ts:809-837` | **3** | 2 |

- 모든 변이 후 focused 셀이 재실패하고, `git checkout --` 원복 후 `git status --short` 공백 + grep으로 내용 복원을 확인했다.
- **★ ⑤의 "가드 결함→수정" 서사가 코드 히스토리로 입증됨**: `d3194e5` diff가 보여주듯, 과거 셀은 `expect(a?.kind).toBe(b?.kind)` 동등성 단정이었다(detail 분기에서 a·b 모두 `null`이면 `undefined===undefined`로 통과 = 결함). 현재는 `for(detail) expect(…?.kind).toBe("locked")` 값 자체 단정으로 바뀌어 잡는다. 내 변이 ⑤로도 현재 가드가 3 cell을 물었다.
- ②④⑤의 cell 수가 작업자 주장과 다르다(②는 1 vs 2, ④는 4 vs 3, ⑤는 3 vs 2). 이 격차는 **변이의 정확한 형태·범위**에서 온다(②는 admit만 우회 vs 정산까지 우회, ④는 request 전역 vs 단일 함수, ⑤는 detail 키워드 집합). 모든 변이가 가드에 잡혔으므로 **가드 결함이 아니며**, 작업자가 work_log에 "어떤 변이가 어떤 cell을 물었는지"를 기록하지 않아(verifiation.md 권고) 독립 재현이 cell 수까지는 닿지 못한 것이다. 결과 자체는 건전하다.

## Issues / Risks

### Blocking (계약 의무)

- **없음.** 정본이 요구하는 분기(should fire / should NOT fire) 전부가 이름 붙은 회귀 셀로 잠겨 있고, 정본 내부 충돌·계약 위반·단일 출처 위반·over-strict 부재가 발견되지 않았다.

### Hardening recommendations (비차단 — 현 정본이 요구하지 않음)

- **`describeQuotaError`의 403 정지 — quota 미로드 시 소유권으로 위장**: `quota`가 아직 로드 전(`null`)인 상태에서 유료 요청이 403을 받으면, 함수는 `null`을 돌려 소유권 거절 경로로 흐른다. 잔여 타일이 mount 시 `/me/quota`를 부르므로 실제로는 거의 항상 `status`를 알지만, **정지된 계정의 첫 유료 요청이 잔여 조회보다 먼저 도착하는** 경합 창이 이론적으로 존재한다. 정지 계정은 `/me/quota` 자체가 `status:"suspended"`를 반환하므로(P6: 정지는 status이고 세션은 살아 있다) 보통 즉시 보정된다. 정본이 요구하는 범위는 아니나, 403 수신 시 `/me/quota`를 재조회해 정지 여부를 확정하는 한 셀이 이 창을 닫는다.
- **mutation-cell 매핑 기록**: 작업자가 5종 뮤테이션을 "전부 재실패"로만 기록하고 어떤 변이가 어떤 셀을 물었는지 적지 않았다(verifiation.md "Record which mutation hit which cell"). 본 검증이 cell 수(②④⑤)까지는 재현하지 못한 직접 원인이다. 향후 슬라이스에서 변이-셀 짝을 work_log 한 줄로 남기면 독립 검증이 같은 자리까지 닿는다.
- **최상위 README 분포 stale(발견·즉시 수정)**: 검증 도중 `README.md:93` "합격 142"가 `docs/verifications/README.md` 분포(등재 후 145)와 불일치했다 — 8.3·8.2b 합격 +2가 검증 인덱스 분포표에는 올랐으나 최상위 README의 서술형 문장만 누락된 부초다(`_COUNT_CLAIMS`가 건수 패턴은 잡지만 서술형 분포 문장은 안 본 빈 구멸). 본 검증이 8.4를 등재하면서 142→145로 바로잡았다.

## Verdict

**합격(조건 없음).** Slice 8.4는 정본 v1.7.89의 모든 계약(H3·Q5=B·W1~W7)을 코드에서 문자 그대로 지키고, 잔여는 시행이 쓰는 함수를 한 곳에서 지나며, 확인은 사용자 행동에서만 나오고, 부트스트랩 면제는 코드 tier 분기가 아니라 정책 행 하나로 표현된다. 테스트 수치(2170/4/1931 · 262/18 · 699/414.13 kB)는 독립 실측으로 정확히 재현됐고, 5종 뮤테이션 전부 가드가 물었으며, 핵심 주장인 detail 분기 가드의 "결함→수정" 서사가 `d3194e5` 코드 히스토리로 입증됐다. 차단 결함 0.

## Outstanding items

- **렌더 육안 확인 미검증**(작업자가 이미 밝힘): 확인 대화·잔여 타일의 시각 렌더는 회귀로 로직이 잠겨 있으나 화면 자체는 보지 않았다. application/frontend 이미지가 코드보다 뒤처져 `docker compose build application frontend`가 선행되고, 스택을 올리면 `curl :8520/projects`가 401인지 먼저 봐야 한다. 본 검증도 동일하게 렌더까지는 가지 않았다.
- **다음 작업**: 독립 검증(본 기록) 완료 → 8.2c(이름 이력 + D8-6 계약 개정 + purge UI 문구) → 그 뒤 `main.py` 라우터 정리.
- **test-mongo**: 본 검증이 기동했다가 `docker compose -f docker-compose.test.yml down`으로 정리했다(네트워크는 다른 서비스가 써서 일부 잔류). 머신 상태는 작업 종료 시점(work_log)으로 복귀 — test-mongo는 내려가 있는 것이 원 상태.
- **작업 트리 clean, push 안 함**(본 검증은 검증 기록 1건을 제외하고 코드 변경 없음).

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system
git rev-parse --short HEAD          # 3663148
git status --short                  # (비어있어야)

# test-mongo 기동 + healthy 대기
docker compose -f docker-compose.test.yml up -d
until [ "$(docker inspect -f '{{.State.Health.Status}}' ai_writte_system-test-mongo-1)" = healthy ]; do sleep 2; done

# 백엔드 전체(test-mongo ON) — 2170 passed / 4 skipped (3 elasticsearch + 1 chroma) / 1931 subtests
python3 -m pytest -q -p no:cacheprovider -rs

# 프론트
cd frontend
npm run gen:api && git diff --stat src/api/schema.d.ts   # 공백(생성물 무변)
npx tsc --noEmit && npm run build                        # 699 modules, 진입 414.13 kB
npm run test                                             # 262 passed / 18 files
cd ..

# 인덱스·문서 수 가드 — 9 passed / 10 subtests
python3 -m pytest -q tests/test_docs_indexes.py -p no:cacheprovider

# 뮤테이션(각각: 변이 → focused 실행 → git checkout -- <path> 원복 → git status --short 공백 확인)
# ① enforcement.py:168-172 remaining 을 `return self.daily_remaining` →
#    pytest tests/test_quota_enforcement.py tests/test_quota_enforcement_api.py -q  → 3 failed
# ② main.py enforce_quota confirmed 뒤에 is_admin early-return → pytest ..._api.py -k admin → 1 failed
# ③ client.ts:384-387 billableHeaders 를 `return {"X-Confirm-Duplicate":"1"}` → vitest quota.test.ts → 5 failed
# ④ client.ts request 에 429 자동 재전송 → vitest quota+AnalysisTrigger+WritingPanel → 4 failed
# ⑤ client.ts:809-837 describeQuotaError 를 detail 분기 → vitest quota.test.ts → 3 failed
docker compose -f docker-compose.test.yml down
```
