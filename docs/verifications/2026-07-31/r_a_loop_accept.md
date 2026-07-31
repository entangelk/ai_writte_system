# 독립 검증 — R-a 유도를 revise-and-gate 루프·/writing/accept로 확장 (작업 트리, uncommitted)

## Subject metadata

- **날짜**: 2026-07-31
- **요청자**: 오너("다음작업 검증해줘. ... revise-and-gate 루프에 적용 ... accept 동일 결함까지")
- **검증자**: Claude (독립 세션)
- **대상 슬라이스**: R-a 유도 적용 지점을 `/writing/revise-and-gate` 루프와 `/writing/accept`로 확장.
  SoT v1.7.65 ⑤가 "루프는 범위 밖, 별도 판단 필요"로 남긴 것 + 패턴 스윕으로 잡은 accept 누락.
  **작업 트리 uncommitted**(commit 안 됨 — 오너 확인 대기).
- **정규 스펙**: `docs/system-contract-sot.md` v1.7.66(헤더+변경이력) · v1.7.65(식·계약) ·
  `plans/context-budget-korean-tokens-decisions.md` §2-5·§2-5-1.
- **검증 대상 출처**: working tree(미커밋). 이전 커밋 `03f2791`(검증자 보강).

## Scope

1. **패턴 스윕 완전성(하중)** — accept가 정말 report 다리인가? raw로 남은 사이트 중 결함이 더 없는가?
2. **설계 판단(하중)** — 진입 1회 유도가 루프의 패키지 예산·merge 상한 양쪽을 묶는가(루프 본체 무변경)?
3. **배선** — revise-and-gate·accept 엔드포인트가 derive_context_budget를 거치는가.
4. **회귀 테스트** — 4건 wiring(양방향).
5. **뮤테이션** — 엔드포인트를 raw로 되돌리면 under-strict가 재실패하는가(경험적).
6. **문서** — SoT v1.7.66·CHANGELOG·HANDOFF 정합.
7. **풀 스위트** — 1777 passed / 1502 subtests.

## Methodology

정본 v1.7.66 엔트리 → 코드·테스트·뮤테이션 순서로 재도출(반증 지향).

- `ContextBudget(max_tokens=…)` 전수: `grep -rn` 로 8개 사이트 매핑(worker·generate·gate·report·
  revise·revise-and-gate·accept·scratch_discard).
- report 다리 전수: `.enrich(` 호출 3곳(accept.py:96·gate_live_diag.py:185·service.py:127)을
  프로덕션 경로 vs 진단 전용로 분류.
- 루프 설계: `revise_gate.py`의 `retrieve_more`·`merge_context_packages`가 `context_budget.max_tokens`
  를 쓰는지 + 엔드포인트가 루프에 `context_budget=search_request.context_budget`를 넘기는지 직독.
- 뮤테이션: 두 엔드포인트 derive 블록을 raw로 되돌려(`replace_all`) under-strict 2건 실행 → 복원.
- 풀 스위트: `python3 -m pytest tests/`(test-mongo ON).

## Findings

### 1. 패턴 스윕 — 완전·정확 ✅ (하중)

`ContextBudget` 사이트 8곳 전수:

| 사이트 | 파일:줄 | 유도 | report 다리 |
|---|---|---|---|
| 생성 워커 | generation_worker.py:107 | derive | O(service.generate→enrich) |
| /writing/generate | main.py:4307 | derive | O(같은 패키지 self-report) |
| /writing/report | main.py:4561 | derive | O(본연) |
| /writing/revise-and-gate | main.py:4738 | derive(신규) | O(루프 revise_gate.enrich) |
| /writing/accept | main.py:5087 | derive(신규) | O(accept.py:96 reporter.enrich) |
| /writing/gate | main.py:4462 | **raw(정상)** | X(WritingGateService, enrich 없음) |
| /writing/revise | main.py:4645 | **raw(정상)** | X(WritingRevisionService, enrich 없음) |
| /writing/scratch_discard | main.py:5281 | **raw(정상)** | X(LLM 호출 자체 없음) |

- **accept의 report 다리는 진짜**(`accept.py:96` `reporter.enrich`) — 패턴 스윕 발견이 사실.
- **raw 3곳은 올바르게 raw**: `WritingGateService`(gate.py:45)·`WritingRevisionService`(revise.py:52)는
  `enrich` 정의 자체가 없다. `gate_live_diag.py:185`의 enrich는 **진단 전용**(`GateDiagnosis` 반환,
  "Side-effect free" 주석)이며 프로덕션 `/writing/gate`(`_default_writing_gate_service`→WritingGateService)는
  이것을 쓰지 않는다. scratch_discard는 LLM을 부르지 않는다.
- **놓친 결함 없음** — 5곳 derive(모두 report 다리)·3곳 raw(다리 없음)로 빈칸 없음. 작업 AI가
  "/context-search 헬퍼"라 부른 셋째 raw는 실제로 scratch_discard(미라벨, 본질 동일).

### 2. 설계 판단 — 진입 1회 유도가 양쪽을 묶는다 ✅ (하중)

- 엔드포인트(revise-and-gate)는 `search_request.context_budget = ContextBudget(max_tokens=derive(...))`
  로 유도값을 넣고, 루프를 부를 때 `context_budget=search_request.context_budget`(유도값)을 전달.
- 루프(`revise_gate.py`)는 그 값을 **양쪽에** 그대로 쓴다: ① `retrieve_more(..., context_budget=context_budget)`
  (490) ② `merge_context_packages(..., max_tokens=context_budget.max_tokens)` (501). 즉 merge 상한 = 유도값이어서
  retrieve_more가 패키지를 유도값 너머로 키우지 못한다.
- **루프 본체 무변경** — 루프는 원래 `context_budget.max_tokens`를 양쪽에 썼으므로, 엔드포인트만 올바른 값을
  넣으면 된다. per-round 재유도 기각은 타당: 이미 만들어진 패키지는 merge 없이 못 줄인다.
- **후보 성장은 K-3 가드가 백스톱** — 후보가 revise partial patch로 유의하게 자라지 않지만, 설령 자라도
  report 다리의 초과는 K-3 가드가 400으로 잡는다(조용한 잘림 아님). 설계가 안전.

### 3. 배선 ✅

두 엔드포인트 모두 report 엔드포인트와 같이 `candidate_tokens_from_text(body.candidate_text)`를 후보 상한으로
`derive_context_budget` 호출(후보가 이미 존재). gate 엔드포인트는 report 다리가 없어 의도적으로 raw.

### 4. 회귀 4건 + 뮤테이션 양방향 ✅ (경험적)

`test_writing.py::WritingReviseGateBudgetDerivationTest`·`WritingAcceptBudgetDerivationTest` 각 2건
(under-strict: 창 알면 줄인다 / over-strict: 모르면 건드리지 않는다). 관측은 `_FakeContextSearch.last_request.context_budget.max_tokens`.
`expected`를 같은 derive 함수로 계산해 토큰 카운트에 robust.

**뮤테이션(검증자 실측)**: 두 엔드포인트 derive 블록을 raw(`body.max_tokens`)로 되돌리자 under-strict 2건이
**`8192 != 1182`**로 정확히 재실패(작업 AI 클레임과 일치). 복원 후 4건 재통과. main.py diff 변형 잔재 0.

### 5. 문서 정합 ✅

- SoT v1.7.66: 헤더 버전 승격 + 변경이력 행(루프 무변경·merge 양쪽 묶음·per-round 기각·accept 동일 결함·
  gate raw·description 정렬). 구현과 정합.
- CHANGELOG v1.7.66 행 · HANDOFF(자가검수 216줄, Next Tasks #2를 "5곳 전부 완료·알파 R-c 관측만 남음"으로
  **교체**, Owner Decisions "결정·구현 완료"). 완료 서술 적재 아님 — 규격 준수.

### 6. 카운트 ✅ (최종 확정)

직전(03f2791) **1773/1502** + 본 슬라이스 **+4**(wiring) = **1777 passed / 1502 subtests**.
풀 스위트 재실행(test-mongo ON) → **1777 passed / 1 skipped / 1502 subtests(697s)**. 작업 AI 클레임과
정확히 일치, **회귀 0건**(subtest +0, 신규 4건은 비-파라미터).

## Issues / Risks

### Blocking (계약 의무) — 없음

패턴 스윕이 완전하고(accept 다리 실재·raw 3곳 정상), 설계가 코드로 검증됐으며(진입 1회 유도→merge 양쪽 묶음),
4건 wiring이 양방향으로 잠겼고 뮤테이션으로 under-strict 재실패를 경험적으로 확인했다. SoT v1.7.66와 코드 정합.

### Hardening recommendations (비차단)

1. **accept wiring 테스트가 `accept.run`의 실패 순서에 의존** — `base_version_id`를 unseeded("v1")로 둬
   accept.run이 `build_context_package` **뒤에** 실패하게 만들고 `last_request`를 캡처한다. 테스트 주석에 명시돼
   있으나, accept.run의 단계 순서가 바뀌면 캡처가 안 될 수 있다. `build_context_package` 호출 자체를 가짜
   context_search로 가로채는 지금 방식이 핵심이므로 영향은 낮으나, 순서 의존성을 한 줄로 더 명시 권장.
2. **루프의 후보 성장은 derivation이 아니라 K-3 가드가 담보** — 설계가 의도한 바이고 현재 revise는 partial
   patch라 문제없으나, 향후 revise가 append형으로 바뀌면 진입 시점 후보 크기 기반 유도가 실제 후보를
   과소평가할 수 있다(그때도 가드가 400으로 막지만). SoT ②에 "후보가 유의하게 자라면 가드가 백스톱"이라
   적혀 있으므로 계약상 열려 있고, 추가 조치 불필요 — 인지 항목으로만.

## Verdict

**합격(PASS).** 하중 클레임 둘 — **패턴 스윕 완전성**(accept 다리 실재·raw 3곳 정상·gate_live_diag는
진단 전용)과 **설계 판단**(진입 1회 유도가 retrieve_more·merge 양쪽을 묶는다, 루프 본체 무변경) — 을 코드로
검증했다. 4건 wiring이 양방향이고 뮤테이션(`8192 != 1182`)을 경험적으로 확인. 풀 스위트 **1777/1skip/1502**
(회귀 0). **차단 사유 없음.**

## Outstanding items

- **미커밋 상태**: 본 슬라이스는 작업 트리에 커밋되지 않았다(작업 AI가 "커밋을 원하시면 말씀해 주세요"로
  남김). 검증 합격이므로 커밋 가능 — 오너 결정 대기. (이번엔 검증만 요청받아 검증자도 커밋하지 않았다.)
- 알파 R-c 관측(LLAMA_CTX_SIZE=32768 → 유도 자동 확대, 루프 포함) — 알파 머신 필요, 범위 밖.

## Reproduction

```bash
# 1. 패턴 스윕: ContextBudget 전수 + report 다리(enrich) 전수
grep -rn "ContextBudget(max_tokens=" services/application/app/main.py services/application/app/writing/generation_worker.py
grep -rn "\.enrich(" services/application/app/writing/*.py | grep -v "def enrich\|_metered"
#   → 8 사이트(5 derive + 3 raw) / enrich 3곳(accept=prod, service=prod, gate_live_diag=진단)

# 2. 루프 설계: merge가 context_budget.max_tokens를 쓰는지
grep -n "retrieve_more\|merge_context_packages\|max_tokens=context_budget" services/application/app/writing/revise_gate.py

# 3. wiring + 뮤테이션
python3 -m pytest tests/test_writing.py -q -k BudgetDerivation          # 4 passed
#   뮤테이션: 두 엔드포인트 derive 블록을 ContextBudget(max_tokens=body.max_tokens)로 바꾸면
#   under-strict 2건이 8192 != 1182 로 실패 (본 검증에서 실측)

# 4. 풀 스위트
docker compose -f docker-compose.test.yml up -d
python3 -m pytest tests/ -q    # 1777 passed / 1 skipped / 1502 subtests (예상)
```
