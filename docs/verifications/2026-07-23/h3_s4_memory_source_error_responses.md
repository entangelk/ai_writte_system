# 독립 검증 기록 — H3 에러 응답 계약 S4: memory/source 트랙 7 endpoint 에러 선언

## Subject metadata

- **날짜**: 2026-07-23
- **요청자**: 오너 ("다음작업 검증해줘. S4 완료, 커밋 f0b1d15")
- **검증자**: 독립 검증자(Claude, 본 슬라이스 구현 미관여)
- **대상 슬라이스/산물**: H3 S4(commit `f0b1d15`) — `main.py` memory/source 구역 7 endpoint의 OpenAPI `responses=` 선언 + 신규 상수 `_ERRORS_400_404_502_504_CONFIG` + 회귀 9건(`MemorySourceErrorContractDeclarationTest`·`MemorySourceErrorBodyExactKeyTest`·`ContextSearchErrorBodyExactKeyTest`)
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.7.32 §HTTP 에러 응답 계약(L295–329). 브리프 `docs/plans/api-error-response-contract-decisions.md`(D1=A/D2=A/D3=A/D4=A, S4 행 L94). 선행 검증 `docs/verifications/2026-07-23/h3_s3_analysis_error_responses.md`(S3)·`h3_error_response_contract_s1_s2.md`(S1+S2).
- **작업 원천**: commit `f0b1d15`(clean — `git status` empty, working tree == HEAD). S3는 별도 commit `3dcb0c2`.

## Scope (계약 스코프)

S3와 동일한 D3=A 원칙 — SoT는 endpoint×코드 표를 유지하지 않으므로(L302) "각 endpoint가 선언해야 할 코드 집합"의 authority는 **실제 endpoint 본문의 `except → HTTPException` 매핑**이다(OpenAPI는 그 산출물). 감사 표면:

1. **정본 계약**: SoT §HTTP 에러 응답 계약(L295–329) — 특히 **504 행**(L315 "예산 소진, `ContextSearchBudgetExceeded`")·**503 두 얼굴**(L318–323)·동적 `ProviderError` 9곳은 realistic 집합만(L316, 브리프 L42).
2. **브리프**: `api-error-response-contract-decisions.md` S4 행(L94 "memory read 2, snapshots/source-refs/index-rebuild, context-search")·D1~D4·스코프 밖 "동적 9곳 전체 열거 안 함"(L42).
3. **구현**: `main.py` 상수 `_ERRORS_400_404_502_504_CONFIG`(L1058)·`_CONFIG_503`(S3, L1043) + 7 endpoint 본문(create/list/get source-ref·rebuild·memory list/get·context-search).
4. **회귀**: `tests/test_application_api.py::MemorySourceErrorContractDeclarationTest`(L2417)·`MemorySourceErrorBodyExactKeyTest`(L2497)·`tests/test_context_search_api.py::ContextSearchErrorBodyExactKeyTest`(L405).
5. **공개 envelope**: `frontend/src/api/schema.d.ts`(gen:api 산물)·OpenAPI dump.
6. **런타임 무변성**: backend 전체 + frontend suite.

경계 매트릭스를 본문 직독으로 먼저 세우고(아래 §1), 나머지 표면이 그것을 뒷받침하는지 대조.

## Methodology (재현 명령)

```bash
# 0. 정본 스코프 — docs/system-contract-sot.md:295-329, plans/api-error-response-contract-decisions.md S4 행·D1~D4
# 1. 커밋 diff + endpoint 본문 직독 (경계 매트릭스)
git show f0b1d15 -- services/application/app/main.py
sed -n '2281,2345p;2587,2615p;3124,3170p' services/application/app/main.py
# 2. 504 매핑 전수 + context-search 유일성 (브리프 스코프 주장)
grep -nE "ContextSearchBudgetExceeded|504|status_code=status" services/application/app/main.py
# 3. OpenAPI self-discovery
python3 scripts/dump_openapi.py > /tmp/openapi.json   # 7 endpoint 코드 집합 + 504 선언자 전수 직접 대조
# 4. 회귀 9건 + subtest
python3 -m pytest tests/test_application_api.py::MemorySourceErrorContractDeclarationTest \
  tests/test_application_api.py::MemorySourceErrorBodyExactKeyTest \
  tests/test_context_search_api.py::ContextSearchErrorBodyExactKeyTest -v -p no:cacheprovider
# 5. mutation (edit→run→revert; `git diff f0b1d15 --numstat` 로 잔류 0 확인)
# 6. backend 전체 (전용 test-mongo 27020 RS) + frontend 재생성/타입/빌드/테스트
python3 -m pytest -q -p no:cacheprovider
cd frontend && git diff 3dcb0c2 f0b1d15 --numstat -- src/api/schema.d.ts   # +108/-0
npm run gen:api && npx tsc --noEmit && npm run build && npm run test
```

## Findings

### 1. 경계 매트릭스 — 선언 == 본문 직독 raise 집합 (7/7, 빈 cell 없음)

| # | endpoint (method) | 선언 상수 → 집합 | 본문 직독 raise 집합 (file:line) | match |
|---|---|---|---|---|
| 1 | /memory (get) | `_ERRORS_404`→{404} | NotFound→404 (L2593) | ✓ |
| 2 | /memory/{memory_id} (get) | {404} | (MemoryNotFound,NotFound)→404 (L2607) | ✓ |
| 3 | /snapshots/…/source-refs (post) | `_ERRORS_400_404`→{400,404} | NotFound→404 (L2295)·CoreSotError→400 (L2297) | ✓ |
| 4 | /snapshots/…/source-refs (get) | {404} | NotFound→404 (L2312) | ✓ |
| 5 | /source-refs/{source_ref_id} (get) | {404} | NotFound→404 (L2327) | ✓ |
| 6 | /snapshots/…/index/source-blocks/rebuild (post) | {404} | NotFound→404 **단일** (L2344) | ✓(매핑)† |
| 7 | /context-search (post) | `_ERRORS_400_404_502_504_CONFIG`→{400,404,502,503,504} | 404(L3132)·400(L3134,3157)·**503 config**(L3136–3140)·504(L3159)·502(L3161,3166) | ✓ |

**7/7 정확히 일치, 빈 cell 없음.** 상수 카운트도 정확 — 신규 `_ERRORS_400_404_502_504_CONFIG` 1종 + 재사용 `_ERRORS_404`(5)·`_ERRORS_400_404`(1) = 7.

† (6 rebuild) endpoint 본문이 `except NotFound` **하나**만 가진다. vector/embedding 협력자를 쓰지만 그 장애를 매핑하는 절이 없어 500이 된다. 그래서 {404}만 선언한 것이 **정직**하다 — 안 던지는 503을 선언하면 over-strict 거짓말. D4=A(선언만, 매핑 새로 만들지 않음)를 정확히 지켰다.

### 2. 504 주장 — context-search는 writing 밖에서 유일한 예산 endpoint (성립), 그러나 표현 과장

- `ContextSearchBudgetExceeded→504` 매핑이 context-search(L3159)에 있고, 나머지 전부(L3408/3534/3603/3681/3797/4088)는 writing 구역(≥L3172).
- OpenAPI에서 504를 선언한 endpoint는 **정확히 3**: `/context-search`(S4 신규)·`/writing/accept`·`/writing/revise-and-gate`.
- **성립 부분**: context-search는 writing 트랙 **밖**에서 504를 선언하는 유일한 endpoint. ✓
- **과장 부분**: "S1이 SoT 표에 적어 둔 504 의미론이 여기서 처음 기계 판독 가능해진다"는 부정확 — `writing/accept`·`writing/revise-and-gate`는 **H3 이전**부터 OpenAPI에 504를 선언했다(브리프 L25, 본 OpenAPI dump로 확인). 정확한 문장은 "writing 밖의 endpoint로는 처음"이다. 아래 Issues H-1.

### 3. context-search 503 = 구성 face → `_CONFIG_503` 재사용 정당

`if context_search is None: raise HTTPException(503, "context search service is not configured")`(L3136–3140). SoT L320의 **구성 face**(협력자 미구성)이므로 S3의 `_CONFIG_503`을 재사용하는 것이 맞다(`_MIGRATION_503` 아님). 회귀가 migrate 문안 차용을 차단.

### 4. OpenAPI self-discovery — 코드가 emit할 의도가 아니라 실제 스펙

`dump_openapi.py`(169KB)에서 독립 스크립트로 7 endpoint의 responses 코드 집합을 EXPECTED와 대조: `endpoints=7 mismatches=0`. **TRACK 조각(`/memory`·`/snapshots/`·`/source-refs`·`/context-search`)에 매칭되면서 EXPECTED에 없는 operation = 0** — closure guard가 7개를 정확히 덮고 과잉/과소 매칭이 없다. body_model subtest 총수 = `sum(|EXPECTED|)` = **12**.

### 5. 회귀 테스트 감사 + mutation

`MemorySourceErrorContractDeclarationTest`(L2417): lock_list exact 집합(subTest 7)·track closure(`/memory`등 fragment)·body_model `$ref==ErrorDetailResponse`(subTest **12**)·context-search 503 구성 face 문안. `MemorySourceErrorBodyExactKeyTest`(L2497): 404·400 wire 본문. `ContextSearchErrorBodyExactKeyTest`(test_context_search_api.py L405): 502·503·504 wire 본문 — 이 셋은 planner/clock 픽스처가 이미 그 파일에 있어 하네스를 복제하지 않았다(합리적 판단). 신규 **9 tests / 19 subtests**(7+12).

mutation 독립 실증(revert 후 `git diff f0b1d15 --numstat` 잔류 0·9 테스트 green으로 확인):
- **E over-strict**: `list_memory`에 inline 409 추가 → lock_list가 memory에서만 SUBFAIL ✓
- **F track-wide**: `/projects/{id}/memory-stats` 추가 → closure가 `('…/memory-stats','get')` 명시 FAIL ✓(TRACK 조각 `/memory` 매칭)
- (under-strict 선언 삭제·config_503 문안 lock은 S3에서 동일 패턴 실증; `_CONFIG_503` 공유 상수라 문안 mutation은 S3 Mutation A로 이미 bite 확인)

### 6. 수치 전부 독립 재도출

| 항목 | 주장 | 재측정 | 일치 |
|---|---|---|---|
| backend | 1437/1/462 | **1437 passed/1 skipped/462 subtests**(621s) | ✓ |
| 신규 회귀 | 9 tests/+19 subtests | **9/19** | ✓ |
| gen:api | +108/-0 | `git diff 3dcb0c2 f0b1d15`=108/0; 재gen sha 동일(멱등) | ✓ |
| tsc | clean | exit 0 | ✓ |
| build JS | 399.03 kB | **399.03 kB**(S2~S4 동일) | ✓ |
| frontend | 194/13 | **194 passed/13 files** | ✓ |
| baseline delta | 1428/443 → +9/+19 | 1428+9=1437, 443+19=462 | ✓ |

## Issues / Risks

### Blocking (계약 의무 위반)
**없음.** 경계 매트릭스 7/7(§1)·504 유일성 성립(§2)·503 구성 face 정당(§3)·closure 건전(§4)·mutation bite(§5)·수치 전부 일치(§6). 계약 요구 lock(under/over-strict·두 얼굴 분리·track 전수)에 누락 없다.

### Hardening recommendations (비차단)

- **H-1(문서 정밀도 — "504 처음 기계 판돉" 과장)**: "S1이 SoT 표에 적어 둔 504 의미론이 여기서 처음 기계 판돉 가능해진다"는 3곳에 반복된다 — commit message·SoT changelog v1.7.32(`docs/system-contract-sot.md:36`)·work_log(`docs/daily_logs/2026-07-23/work_log.md:263`). `writing/accept`·`writing/revise-and-gate`가 H3 이전부터 OpenAPI에 504를 선언했으므로(브리프 L25, dump 확인) "처음 기계 판돉"은 사실이 아니다. 정확한 문장: "writing 트랙 **밖**의 endpoint로는 처음 504를 선언한다" / "context-search는 writing 밖에서 504를 선언하는 유일한 endpoint". 실질 주장(context-search=writing 밖 유일 예산 endpoint)은 참이고 선언 자체는 정확하므로 **verdict 무관**, 문안 정정만으로 닫힌다. (참고: S3의 "나머지 18" 오기는 커밋 시 "19"로 정정돼 있음 — 본 검증자의 S3 기록이 지적한 것과 동일 축.)
- **H-2(미매핑 500 — 사전 존재, S3 부채와 동일 부류)**: `rebuild_source_block_index`(L2335)는 `except NotFound`만 있어 vector/embedding 협력자 장애가 500으로 샌다. S3가 지적한 `auto_promote_job` 루프와 동일 부류이며 작업자가 HANDOFF에 S5 점검 부채로 명시했다. (a) S4는 `responses=`만 추가하고 try/except를 건드리지 않았고(사전 존재), (b) SoT L329가 500 누수를 "승인 안 된 알려진 결손"으로 분류하므로 **선언 계약 위반이 아니다**, (c) {404}만 선언한 것이 오히려 over-strict 회피의 정석. verdict 무관. S5(`start_next_unit` 503 방어) 착수 시 이 부채 2건(rebuild·auto-promote) 점검 권장.

## Verdict

**합격(조건 없음).** S1/S2/S3에 이어 동일 기준. 근거: 경계 매트릭스 7/7(선언==본문 직독 raise 집합)·context-search 504/503/502/400/404 정확·503 구성 face로 `_CONFIG_503` 재사용 정당·rebuild {404}-only가 over-strict 회피로 정직·track closure 건전·mutation bite·런타임 무변(1437/1/462, 동일 분기/detail)·gen:api 순수 additive 멱등·tsc/build/vitest green·수치 전부 독립 재도출 일치. H-1(문안 과장)·H-2(사전 존재 미매핑)는 비차단이며 본 슬라이스의 계약 의무가 아니다.

## Outstanding items

- **커밋 완료**: 본 슬라이스는 commit `f0b1d15`로 반영돼 있고 working tree는 clean. 검증자의 mutation 실험은 전부 revert(`git diff f0b1d15 --numstat -- main.py` = empty, 잔류 probe 0, 9 테스트 green).
- **H-1 문안 정정 여부**: 오너 판단. commit message·SoT changelog·work_log 3곳의 "처음 기계 판돉 가능"을 "writing 밖의 endpoint로는 처음"으로 좁히는 정정(코드/테스트 무변경).
- **다음 = S5(페이즈 마지막)**: writing 잔여 + `start_next_unit` 503 방어(=SoT L329 "알려진 결손" 폐쇄). 본 페이즈에서 **유일하게 런타임을 바꾸는** 슬라이스(브리프 명시 예외). 동적 `ProviderError` 매핑 9곳이 전부 이 구역이라 realistic 집합은 {502,504}(`status = 504 if TIMEOUT else 502`). 누적 미매핑 500 부채 2건(rebuild·auto-promote, 본 검증 H-2 + S3 H-2)도 함께 점검 대상.

## Reproduction

```bash
docker compose -f docker-compose.test.yml up -d test-mongo
sed -n '2281,2345p;2587,2615p;3124,3170p' services/application/app/main.py   # 본문 직독 경계 매트릭스
python3 scripts/dump_openapi.py > /tmp/openapi.json   # 7 endpoint 집합 + 504 선언자 3개 직접 대조
python3 -m pytest tests/test_application_api.py::MemorySourceErrorContractDeclarationTest \
  tests/test_application_api.py::MemorySourceErrorBodyExactKeyTest \
  tests/test_context_search_api.py::ContextSearchErrorBodyExactKeyTest -v -p no:cacheprovider
python3 -m pytest -q -p no:cacheprovider              # 1437/1/462 예상
cd frontend && git diff 3dcb0c2 f0b1d15 --numstat -- src/api/schema.d.ts   # 108/0
npm run gen:api && npx tsc --noEmit && npm run build && npm run test       # 399.03 kB / 194/13 예상
# mutation E/F(edit→run→revert)는 본문 §5 / Methodology step 5 참조
```
