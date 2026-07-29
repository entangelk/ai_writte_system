# 검증 기록 — 슬라이스 1 / 컨텍스트 예산 회계 수정 (포인터 렌더링 회계 반영)

## Subject metadata

- **날짜**: 2026-07-29
- **요청자**: 오너(entangelk) — "작업 AI가 작업한 거 확인해서 검증하고 의심하고 또 의심해줄래? 슬라이스 1 끝."
- **검증자**: Claude(본 세션)
- **검증 대상**: 컨텍스트 예산 슬라이스 1 **구현** — 항목 `token_estimate`가 항목 `text`가 아니라
  **렌더링된 형태(포인터 JSON 포함)**를 세도록 한 수정. 작업자 주장: 회계가 실제 렌더링의
  1/12.7이어서 예산이 창을 넘기는 프롬프트를 통과시켰던 것을, 항목별 렌더링 기준으로 정직하게
  고쳤다.
- **정본 사양 참조**: `docs/plans/context-budget-korean-tokens-decisions.md` **§2-3 ③·④**(루트원인)
  및 오너 결정(같은 문서 상단 — K-6=R-e, 착수 순서 "회계 → R-e → 가드 → 밀도"). 본 검증의 계약
  범위는 이 브리프가 정한 "회계는 항목이 *렌더링되는 형태*를 세야 한다"는 의무와 그 경계(구조적
  래퍼는 항목별 회계가 아닌 창 가드의 몫)로 한정한다.
- **검증 대상 작업의 출처**: 커밋 **`0740669`**(fix) · **`eb18930`**(test, 빨간불 선행) · `c9e16b3`·
  `4d3b614`(docs). **working tree clean**(`git status` 공백).

> **검증 성격**: 이 슬라이스는 구현이므로 §5의 **경계 매트릭스**를 그대로 적용한다 — every "should
> fire"/"should NOT fire" 분기와 리터럴을 정본에서 끌어내 각각 회귀 셀에 대응시키고, 빈 칸(계약 요구
> 분기에 테스트가 없는 것)이 없는지 확인한다.

## Scope

1. **계약 의무(should-fire)** — 회계가 렌더링 형태(pointer 포함)를 세는가. 3개 생산자 각각.
2. **경계(should-NOT-fire)** — 구조적 래퍼(`<context_package>`·섹션 태그)가 항목별 회계에 들어가지
   않는가(그것은 K-3 창 가드의 고정 오버헤드).
3. **두 정의의 일치** — 회계용 사본(`estimate_rendered_item_tokens`)과 정본 렌더러
   (`_format_item`+`pointer_json`)이 같은 문자열을 만드는가(의도된 중복의 드리프트 잠금).
4. **셀 독립성** — 3 생산자가 각각 *다른* 회귀 셀에 걸리는가(뮤테이션으로 재현).
5. **스윕 완전성** — 놓친 생산자/소비자가 없는가(전수 grep).
6. **양방향 가드** — under-strict(버그 재발)·over-strict(과잉 교정)가 둘 다 있는가.
7. **공개 계약 불변** — `schema.d.ts` / 생성 타입 / 응답 모델에 변화가 없는가.
8. **부수 효과 없음** — 수정된 기존 테스트(`test_need_priority`)가 잠그던 계약(need 우선순위)을
   여전히 잠그는가; 회귀 전량이 기준선 대비 +3인가.
9. **베타 실측 수치** — 887→4,049 · 항목 69→60 · 프롬프트 12,462→11,027(정합성·귀속).
10. **문서화** — 의도된 중복이 세 곳(코드 주석·HANDOFF 부채·work_log)에 명시됐는가.

## Methodology (재현 가능한 명령)

모든 주장은 작업자의 기록을 믿지 않고 1차 소스에서 재도출했다. 기계: WSL2, Python 3.12.3,
`PYTHONPATH=.` 로 repo root.

- **계약 읽기**: `docs/plans/context-budget-korean-tokens-decisions.md` §2-3 전문 + 오너 결정 블록.
- **코드 읽기**: `service.py`(582-601·855-880·957-985·1139-1162·680·1172-1191) ·
  `writing/prompt.py`(48-126) · `writing/context_pointer.py`(26-99) ·
  `writing/retrieval.py`(270-303) · `prior_memory.py`(100-151) · `main.py`(3360-3375).
- **뮤테이션 매트릭스**(결정적 증거): 각 생산자의 `estimate_rendered_item_tokens(...)` 호출을
  `estimate_tokens(text)`/`estimate_tokens(block.text)`로 되돌리고 3개 셀을 돌린 뒤 `git checkout`으로
  복구. 과잉 방향은 포인터 중복·3배 부풀림으로 특성화.
- **전수 스윕**: `grep -rn "token_estimate=\|estimate_tokens(" services/application/app/`.
- **schema 확인**: `grep -c token_estimate frontend/src/api/schema.d.ts` + 응답 모델 필드 grep.
- **회귀**: test-mongo 기동(`docker compose -f docker-compose.test.yml up -d`, healthy 확인) 후
  `PYTHONPATH=. python3 -m pytest tests/ -q` (647.5s).
- **베타 데이터 교차**: `docker exec ai_writte_system-application-1 python` → pymongo로 프로젝트·
  `source_blocks` 집계.

## Findings

### 1. 계약 의무 충족 — 회계는 렌더링 형태를 센다 (should-fire ✓)

수정은 `estimate_rendered_item_tokens()`를 더하고 3개 생산자가 이것을 쓴다
([`service.py:582-601`](../../../services/application/app/context_search/service.py#L582)):

```python
return estimate_tokens(f"- [{label}] {_pointer_wire_json(pointer)} {text}")
```

3개 생산자 모두 포인터를 **포함한** 형태를 센다 — 메모리([`:873`](../../../services/application/app/context_search/service.py#L873)) ·
후보([`:983`](../../../services/application/app/context_search/service.py#L983)) · source block([`:1156`](../../../services/application/app/context_search/service.py#L1156)).
좌변은 `token_estimate_total = sum(item.token_estimate for included)`
([`service.py:680`](../../../services/application/app/context_search/service.py#L680))로, 생산자 값의 합이다.

### 2. 두 정의는 문자열 수준에서 동일하다 (드리프트 잠금 전제 ✓)

회계용 사본 `_pointer_wire_json`과 정본 렌더러 `pointer_json`은 **같은 문자열**을 만든다:

| | 회계 사본 | 정본 렌더러 |
|---|---|---|
| 키 | `_RENDERED_POINTER_KEYS`(=`POINTER_KEYS`) | `POINTER_KEYS` |
| 직렬화 | `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",",":"))` | 동일 |
| 라인 | `f"- [{label}] {pj} {text}"` | 동일([`prompt.py:126`](../../../services/application/app/writing/prompt.py#L126)) |

`context_pointer_of`는 4필드를 **값 그대로 통과**한다([`context_pointer.py:74-79`](../../../services/application/app/writing/context_pointer.py#L74-L79),
검증·변환만 하고 값을 바꾸지 않음). 따라서 IndexPointer를 직접 읽는 사본과 ContextPointer를 거치는
정본이 같은 문자열을 낸다. 회귀는 **좌변=회계(사본 경로) · 우변=실제 렌더러(`_format_item`)**
로 서로 다른 코드 경로를 유지해 자명해지지 않는다
([`test_context_search.py:457+`](../../../tests/test_context_search.py#L457)).

### 3. 셀 독립성 — 3 생산자가 각각 다른 셀에 걸린다 (뮤테이션 매트릭스, 독립 재현 ✓)

작업자 주장을 **뮤테이션으로 재현**했다(각 행: 해당 생산자를 text-only로 되돌림):

| 뮤테이션 | 메인(source) 셀 | 정본메모리 셀 | 후보 셀 |
|---|---|---|---|
| 전부 되돌림 | FAIL | FAIL | FAIL |
| 메모리만 | PASS | **FAIL** | PASS |
| 후보만 | PASS | PASS | **FAIL** |
| source만 | **FAIL** | PASS | PASS |

→ ① under-strict 가드가 3 셀 전부에서 가동. ② 메모리/후보를 되돌려도 메인 테스트가 **통과** =
그 두 셀이 *꼭 필요했다*(메인 픽스처가 source_blocks 8개뿐이라 두 생산자를 잠그지 못함). 작업자의
"칸을 채운 이유" 주장이 정확히 재현됐다.

### 4. 스윕 완전성 — 놓친 생산자/소비자 없음 (독립 전수 grep ✓)

- `token_estimate=`를 갖는 ContextItem 생성은 **정확히 3곳**(service.py 873·983·1156).
- `estimate_tokens(` 호출은 prior_memory.py:151(`_value_tokens`)와 service.py:601(새 함수 본체)뿐.
- 소비자 2곳은 `item.token_estimate`를 **소비만**:
  [`_apply_budget:1181`](../../../services/application/app/context_search/service.py#L1181) ·
  [`retrieval.py:280-282`](../../../services/application/app/writing/retrieval.py#L280)(자체 estimate 0건,
  `token_estimate_total=total` at `:303`는 누적값). 생산자 수정이 그대로 전파된다.
- prior_memory.py:117/151은 **같은 버그가 아님**: `format_context_package`가 렌더링하는 섹션은
  do_not_use·constraints·project_brief·macro_items·micro_evidence뿐
  ([`prompt.py:60-108`](../../../services/application/app/writing/prompt.py#L60-L108))이고 `prior_memories`는
  없으므로 포인터가 붙지 않는다. 범위 밖 분류가 맞다.

### 5. 래퍼 경계 (should-NOT-fire ✓)

항목별 회계가 구조적 래퍼를 담지 않는다는 것을 별도 단정으로 못박았다
([`test_context_search.py`](../../../tests/test_context_search.py)의 `wrapper_only` 단정 —
`wrapper = 전체렌더링 − 항목별렌더링`이 0보다 크고 항목 몫보다 작다). 생산자는 렌더링 라인만 세므로
래퍼가 들어갈 수 없고(구조적으로 조립 이후에 생김), 이 몫은 K-3 창 가드가 system 프롬프트·후보
산문과 함께 고정 오버헤드로 더해야 할 자리로 명시됐다.

### 6. 공개 계약 불변 (✓)

- `frontend/src/api/schema.d.ts`에 `token_estimate` **0건**(grep).
- `token_estimate`/`token_estimate_total`은 응답의 **untyped dict**에만 실린다
  ([`main.py:3362`](../../../services/application/app/main.py#L3362) `_analysis_context_payload(...) -> dict[str, object]`,
  값 할당 at `:3370`/`:3808`/`:3862`). Pydantic 응답 모델 필드가 아니므로 OpenAPI 생성 타입에
  등장하지 않는다. → 계약 변화 0. 슬라이스 4개 커밋이 건드린 파일에 schema 파일 0건(`git diff
  --name-only`).

### 7. 부수 효과 — 기존 테스트는 계약을 계속 잠근다; 회귀 +3 (✓)

- `test_need_priority_order_drives_ranking_bidirectional`의 예산을 `2`·`4` 리터럴에서 **실제 항목
  비용에서 파생**한 값으로 바꿨다(budget = 상위 need 항목 1개 비용 → greedy 로 단 1개만 포함 → 그
  항목의 need가 `needs` 튜플 첫 원소와 일치). 단정은 손대지 않았으므로 이 테스트가 잠그던
  **need 우선순위**가 그대로 잠긴다. 랭킹은 token_estimate에 의존하지 않으므로(need 우선순위 기준)
  값 변경이 순서에 영향을 주지 않는다.
- **전량 회귀(test-mongo ON): `1703 passed / 1 skipped / 1468 subtests`(647.5s, exit 0).**
  기준선 `1700/1/1468` 대비 **+3 passed** = 신규 3 셀과 정확히 일치. 실패·설명 안 되는 증감 0.
  작업자 주장과 **정확히 일치**(독립 재실행).
- 토큰 의존 12개 모듈 집중 회귀: **178 passed**(context_search 8모듈 + writing budget/retrieval +
  gate_findings + context_pointer).

### 8. 베타 실측 수치 — 정합성·귀속 (부분 독립 확인)

- **귀속 논리 성립**: 창 단독(16384)은 프롬프트 12,462+출력 6,144=18,606>16,384 → 200 조용한 잘림
  (미수리). 회계 수정 단독(창 8192)은 프롬프트 11,027>8,192 → 여전히 400. **성공은 둘의 합작**이며,
  회계 효과(887→4,049, 69→60)는 창과 무관하게 분리 측정됐다. 작업자 서술이 정확하다.
- **내부 산술 일관**: 회계 4,049(len/4 단위) × 2.44(한글 밀도) ≈ 9,891 = 수정 후 렌더링 실측.
  렌더링 16,262자 ÷ 4 ≈ 4,066 ≈ 회계 4,049. 두 오차원(회계·밀도)이 분리돼 측정됨이 수치로 확인.
- **베타 데이터 존재 교차**(DB 직접 조회): heavy-seed 프로젝트 `6a694675…0ae`가 실재하고
  **source_blocks 69개** = 작업자 "패키지 항목 69개"와 일치. 프로브가 만든 프로젝트 4종 확인됨.
- **수정 후 4,049·60개·11,027·4/4 성공은 독립 재측정하지 않았다**: 스크래치 프로브의 전체 writing
  요청을 재구성해야 하고 외부 LLM 서버가 필요하다. 단, 수정 전 887/11,304/69는 이전 독립 검증
  `beta_long_report_pointer_root_cause.md`가 프로덕션 토크나이저로 골드 재구성해 이미 확인했고,
  수정 후 수치는 *검증된 수정*이 그 69 항목에 미치는 산술 귀결이다.

### 9. 문서화 — 의도된 중복이 세 곳에 (✓)

코드 주석([`service.py:545-580`](../../../services/application/app/context_search/service.py#L545),
왜 순환인지·언제 없앨지) · HANDOFF 추적 부채([`HANDOFF.md:130`](../../../HANDOFF.md), 판단 시점 R-e
직후·드리프트 잠금 설명) · work_log(경위, 457-459). 오너 지시 "테스트만으로 잠그지 말고 문서에도
남길 것"이 반영됐다. HANDOFF 자가 검수 줄도 존재(7행, 201줄, 정정 포함).

## Issues / Risks

### Blocking (계약 의무) — **0건**

경계 매트릭스의 모든 칸이 채워져 있다: 회계-렌더링-형태(should-fire, 3 셀) · 래퍼-제외
(should-NOT-fire) · 양방향 가드 존재 · 회귀 +3만 · 공개 계약 무변. 계약 요구 분기에 테스트가 없는
빈 칸은 없다.

### Hardening recommendations (비차단)

- **H1 — over-strict 상한이 느슨하다.** 3 셀의 over-strict 단정은
  `token_estimate_total <= per_item_rendered * 2`다. 두 정의가 **현재 정확히 일치**하므로 자연스러운
  단정은 동등(또는 `<= 1.1×` 수준)이다. 뮤테이션 실측: **포인터를 중복 집계하는 과잉 교정은
  통과**(1 passed)하고, 3배 부풀림에서야 발화(1 failed)한다. 즉 현실적인 과잉 교정(포인터 중복)을
  잡지 못한다. → 권고: 단정을 동등 기준으로 조이면 같은 코드 경로가 아님에도 작은 드리프트까지
  잡는다. **비차단**: 계약 의무(렌더링 형태 세기)는 충족됐고, 실제 버그 방향(under-strict, 과소평가)
  은 3 셀 전부에서 단단히 잠겨 있으며, 브리프가 "과소평가가 버그 방향이라 보수적으로 잡는다"고
  명시해 over-strict 느슨함은 설계 의도와 충돌하지 않는다.
- **H2 — "더 큰(report) 형태를 모든 생산자에 적용" 정책이 정본 문서에 명시 안 됨.** 회계는 생성
  경로(포인터 미렌더링)에까지 포인터-포함(report) 형태를 적용해 보수적으로 잡는다(코드 주석에 근거
  있음). 이 정책이 회귀 단정으로 고정돼 있고 코드 주석·HANDOFF·work_log에 서술했으나, 정본
  decisions 문서(§2-3 / 슬라이스 정의)에는 "두 렌더링 형식 중 큰 쪽을 모든 경로에 적용"이라는
  문장이 명시돼 있지 않다. → 권고: 브리프에 이 정책을 한 줄 추가해 정본에 올린다(spec-silent-but-
  documented를 spec에 흡수). **비차단**: 정책은 올바른(보수적) 방향이고 세 곳에 문서화됐으며 회귀가
  고정한다.

## Verdict — **합격 (PASS)**

차단 사유 0건. 계약 의무(회계 = 렌더링 형태) 충족, 3개 생산자 전부 수정, 놓친 생산자/소비자 없음,
양방향 가드 존재(under-strict는 3 셀에서 뮤테이션으로 확인), 래퍼 경계 단정, 공개 계약 무변,
회귀 1703/1/1468(기준선 +3, 작업자 주장과 정확히 일치). 하드닝 2건(H1 over-strict 조임 · H2 정본
문서 정책 명시)은 비차단이며 다음 슬라이스나 별도 티켓에서 다룬다.

## Outstanding items (오너 다음 행동에 영향, 결함 아님)

- **수정 후에도 창 기준으로는 빠듯하다**: 프롬프트 11,027 + 출력 상한 6,144 = **17,171 > 16,384**.
  실제 report 출력(2,500~3,300)이면 성공하지만 상한을 다 쓰면 잘린다. 작업자가 work_log(441-448)에
  기록했고 승인된 순서가 이를 다룬다 — **K-3 가드**가 이 상태를 소리 나게 만들고, **K-1 밀도**가
  프롬프트를 줄여 여유를 돌려주며, **R-e(K-6)**가 포인터를 빼 프롬프트를 크게 줄인다.
- **슬라이스 1 단독으로는 베타 구 창에서 고치지 않는다**: 회계 수정 단독(창 8192)은 프롬프트
  11,027>8,192로 여전히 400. 관측된 4/4 성공은 회계 수정 + 창 16384의 합작이다(work_log 435-439).
  승인된 순서(회계→R-e→가드→밀도)가 이 의존성과 맞다.
- **test-mongo를 본 검증에서 기동했다**(`ai_writte_system-test-mongo-1`). 작업자가 내린 상태와 다르다.
  회귀 재실행용이며, 그대로 둬도 무방하다(독립 포트).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
# 3개 신규 회귀 셀
PYTHONPATH=. python3 -m pytest \
  tests/test_context_search.py::ContextSearchPackageTest::test_budget_counts_what_the_model_actually_receives_bidirectional \
  tests/test_context_search_canonical_memory.py::CanonicalMemoryStepTest::test_canonical_memory_budget_counts_the_rendered_item_bidirectional \
  tests/test_context_search_candidate_memory.py::CandidateMemoryStepTest::test_candidate_memory_budget_counts_the_rendered_item_bidirectional -v

# 뮤테이션 매트릭스: service.py 의 3개 estimate_rendered_item_tokens 호출을 estimate_tokens(text)로
# 되돌려 각 셀을 돌리고 git checkout -- services/application/app/context_search/service.py 로 복구.
#   전부 되돌림 → 3 셀 전부 FAIL / 메모리만 → 정본메모리 셀만 FAIL / 후보만 → 후보 셀만 FAIL / source만 → 메인 셀만 FAIL

# 전수 스윕 (놓친 생산자 없음 확인)
grep -rn "token_estimate=\|estimate_tokens(" services/application/app/ --include=*.py

# 공개 계약 불변
grep -c token_estimate frontend/src/api/schema.d.ts   # → 0

# 전량 회귀 (test-mongo ON 필요)
docker compose -f docker-compose.test.yml up -d   # healthy 대기
PYTHONPATH=. python3 -m pytest tests/ -q          # → 1703 passed / 1 skipped / 1468 subtests
```
