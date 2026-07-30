# 검증 기록 — R-e(K-6) 항목 번호 인용 구현

## Subject metadata

- **날짜**: 2026-07-30
- **요청자**: 오너(entangelk) — “작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?”
- **검증자**: Claude(독립 검증 에이전트)
- **대상 슬라이스/산물**: K-6=R-e — report extractor가 포인터 JSON을 베끼지 않고 항목 **번호**를 인용하며, **번호→`ContextPointer` 매핑은 서버**(`parse_report`)가 한다.
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.7.61(본문 §Phase 5 “후보 self-report의 근거 인용은 항목 번호다” 한 줄 + 버전 로그), `docs/plans/context-budget-korean-tokens-decisions.md` §2-1(R-e 결과 갱신 블록), `docs/plans/05-writing-stable-context-pointer-decisions.md`(2026-07-30 wire-갱신 주석)
- **검증 대상 소스**: 워킹 트리, 미커밋(HEAD = `474018b`). 14개 파일 수정 + 2개 신규(`services/application/app/context_search/item_render.py`, `docs/daily_logs/2026-07-30/`).

## Scope

정본 계약이 R-e에 대해 요구하는 경계 전부. 경계 행렬(fire/NOT-fire)을 계약 본문에서 먼저 세운 뒤, 각 셀이 코드·테스트·픽스처에 실제로 잠겨 있는지 추적.

1. **계약 본문**(정본): R-e에 관한 SoT 본문 한 줄 + v1.7.61 버전 로그 + 브리프 갱신 블록 — 내부 모순 여부.
2. **렌더링/번호 부여**: `item_render.render_context_item`, `prompt.format_context_package` — `- [N] [label] text` 형식, macro→micro 1-based 연속 번호.
3. **파서**: `report.parse_report` / `_cited_pointer` — 번호 1-based, 범위·타입(특히 `bool`)·구 wire 거부, fails-closed.
4. **번호 순서 == allowlist 순서**(하중 불변조건): `format_context_package` 번호 부여 순서 vs `context_pointer.package_pointers` 순서.
5. **도메인·공개 계약 무변**: `CandidateClaim.related_context_pointers` 여전히 `ContextPointer` tuple, accept advisory·Gate 프롬프트 wire 무변, `schema.d.ts` 재생성 diff 0.
6. **회계**: `service.estimate_rendered_item_tokens` — 정본 렌더러 공유, 세 자리(999) 상한, 의도적 여유(항목당 ≤1토큰) 회귀 단정.
7. **진단 버전**: `report_live_diag.format_report_diagnosis` — `REPORT_VERSION`에서 끌어오기(리터럴 아님).
8. **회귀 테스트** 5개 파일 + 뮤테이션 매트릭스(양방향).
9. **실측 before 값 교차참조**: 11,837/11,905 vs 어제 배포 레코드.

## Methodology

각 표면을 재현 가능한 명령으로 검증. 정본을 먼저 스코핑(전부 읽지 않고 R-e 체인만)하고 경계 행렬을 세운 뒤 코드를 댐.

- 계약 읽기: `git diff HEAD -- docs/plans/*.md docs/system-contract-sot.md`로 R-e 변경분만 추출, 본문 한 줄·버전 로그·브리프 블록 단위로 정독.
- 코드 읽기: `report.py`·`prompt.py`·`item_render.py`·`service.py`(회계 부분)·`context_pointer.py`·`report_live_diag.py` 전문.
- 공개 계약 무변: `frontend/package.json`의 `gen:api`(`dump_openapi.py` → `openapi-typescript`)로 **독립 재생성** 후 `diff src/api/schema.d.ts /tmp/schema_verify.d.ts`.
- 집중 회귀: `PYTHONPATH=. python3 -m pytest tests/test_writing_context_pointer.py tests/test_context_search.py tests/test_context_search_candidate_memory.py tests/test_context_search_canonical_memory.py tests/test_writing_report_live_diag.py -q`.
- 표면 전체 회귀: `PYTHONPATH=. python3 -m pytest tests/ -q -k "writing or context_search or report_live_diag or context_pointer or live_diag"`.
- 전체 수집(import 손상 점검): `PYTHONPATH=. python3 -m pytest --collect-only -q`.
- **독립 뮤테이션 실증**(Edit로 변형 → 해당 셀만 실행 → 실패 확인 → 역방향 Edit으로 원복): A 0-based 매핑, B bool 가드 제거, C micro 번호 재시작, D allowlist 순서 반전, E 회계 text-only, F 회계 과잉 집계, G 진단 버전 리터럸 — 7종.
- 패턴 스윕: 제거/개명 심볼(`_format_item` 단수, `include_pointers`, `_pointer`)의 잔류 참조 grep.
- before 교차참조: `grep -rn "11,837\|11,905" docs/daily_logs/2026-07-29/ docs/verifications/2026-07-29/`.

## Findings

### 1. 계약 본문 — 내부 일관성

- SoT v1.7.61 본문 한 줄(`docs/system-contract-sot.md:663`)과 버전 로그(`:36`)가 R-e 계약을 동일하게 서술: 항목 번호 1-based, macro→micro, `package_pointers` 순서와 동일(갈라지면 “근거 오귀속”), `0`/음수/`bool`/구 wire 거부, 도메인·공개 계약 무변, 회계 999 상한. **본문 ↔ 로그 ↔ 브리프 간 모순 없음.**
- 브리프 상단 주석(`05-writing-stable-context-pointer-decisions.md`)은 “모델이 포인터를 베낀다”는 구 서술이 현행이 아님을 명시하고 D1·D3·P-i(모델은 identity를 못 만든다)는 유효함을 표기 — wire만 바뀌었다는 프레이밍이 코드와 일치.

### 2. 렌더링/번호 부여

- `item_render.py:30-37`: `number is None` → `- [label] text`, 번호 있으면 `- [N] [label] text`. 라벨은 `canonical` / `candidate (uncertain)`. 형식이 계약과 문자 그대로 일치.
- `prompt.py:91-106`: macro를 `1`부터, micro를 `1 + len(macro_items)`부터 번호 부여 → macro→micro 연속. `include_citation_numbers` 플래그(구 `include_pointers`)로 report 경로만 opt-in; 생성/revise는 평문.

### 3. 파서 — `report.py`

- `_cited_pointer`(`report.py:185-193`): `bool` 먼저 거부(`isinstance(v, bool) or not isinstance(v, int)`) → `1 <= v <= len(allowed)` → `allowed[v-1]`. 1-based, 범위 밖·음수·0·`True`·`1.0`·`"1"`·구 dict wire 모두 거부. 계약 리터럴과 일치.
- `parse_report`(`report.py:149-168`): `allowed = tuple(allowed_pointers)`(주석 “순서가 의미다 — set으로 바꾸면 매핑이 사라진다”). `frozenset`에서 `tuple`로 바뀐 것은 번호=위치 매핑을 보존하기 위함이고 정당함.
- 항목 내 중복 거부(`report.py:182`): 해결된 `ContextPointer` 기준 `len(set) != len` — `[1,1]` → 같은 포인터로 접혀 거부. 계약(“never repeat a number within one claim”)과 일치.

### 4. 번호 순서 == allowlist 순서(하중 불변조건) — 코드 교차검증

- `format_context_package`는 `package.macro_items`→`package.micro_evidence` 순으로 번호 부여(`prompt.py:91-106`).
- `package_pointers`는 `(*package.macro_items, *package.micro_evidence)` 순(`context_pointer.py:82-87`).
- 양쪽이 **같은 튜플을 같은 순서로** 소비하므로 number N → `concatenated[N-1]` 매핑이 일관. 발산은 구조적으로 불가(한쪽 반복 순서를 바꿔야만). 뮤테이션 C·D로 이 셀이 물린 것을 독립 확인(아래).

### 5. 도메인·공개 계약 무변

- `pointer_wire`가 `accept.py:29,258`·`gate_prompt.py:10,60`에 **그대로** 사용 중 — accept advisory와 Gate 프롬프트는 여전히 `ContextPointer` JSON을 싣는다(정본이 “무변”이라 한 바로 그 표면). R-e는 report 경로만 바꿨고 두 파일은 `git status`에서 수정 대상이 아님.
- `schema.d.ts`: **독립 재생성 후 `diff` 결과 빈 줄 0건** → 공개 계약 무변 확인.

### 6. 회계 — `service.py`

- `estimate_rendered_item_tokens`(`service.py:553-571`): 정본 렌더러 `render_context_item`을 `number=_BUDGET_CITATION_NUMBER`(=999)로 호출. 항목 생성 시점에 실제 번호를 모르므로 3자리 상한(과대평가가 안전 방향).
- 슬랙 산술 검증: 회계 라인은 “999”, 실제는 “1..N” → 자리수 차 ≤ 2 → 토큰 차 ≤ 1/항목 → 총 슬랙 ≤ N. `assertGreaterEqual(slack,0)`(밑돌 방지=2026-07-29 장애 방향)와 `assertLessEqual(slack,len(items))`(과잉 방지)가 양쪽을 잠금.

### 7. 진단 버전 — `report_live_diag.py`

- `format_report_diagnosis`의 기본값 `prompt_version: str = REPORT_VERSION`(`report_live_diag.py:236`) — 리터럴이 아닌 import에서 끌어옴. 뮤테이션 G로 이 셀이 물림을 확인.

### 8. 회귀 테스트 + 뮤테이션

- 집중 5파일: **102 passed / 26 subtests**.
- 표면 전체: **598 passed / 22 skipped(인프라 선택) / 284 subtests / 실패 0**.
- 전체 수집: **1720 collected**(=작업자 주장 1719+1 skipped와 일치), import/수집 손상 없음.
- **독립 뮤테이션 7종, 전부 해당 셀에서 실패 확인**(역방향 Edit으로 원복 후 집중 suite 102/26 재확인):
  - A `allowed[v-1]`→`allowed[v]`(0-based): 매핑 셀 3 subtest 실패(IndexError/위치 오정렬).
  - B `isinstance(v,bool) or` 제거: `True` 값이 통과 → “must be an item number” 미발생.
  - C micro 시작 `1+...`→`1`(재시작): e2e 매핑 셀 + 연속 번호 셀 **둘 다** 실패.
  - D `package_pointers` 순서 micro→macro 반전: e2e 매핑 셀 실패(claim [2]가 content_hash 다른 항목으로 매핑 = “조용한 오귀속”을 정확히 포착).
  - E 회계 `estimate_tokens(text)`(text-only): 슬랙 −38 < 0 → under-strict 방향 물림.
  - F 회계 `+5/항목`(과잉): 슬랙 42 > 8=N → over-strict 방향 물림.
  - G 진단 기본값 리터럴 `…_v1`: 헤더가 v1 출력 → 버전 셀 물림.

### 9. before 실측 교차참조

- 작업자 “old 11,841은 어제 레코드(11,837·11,905)와 사실상 일치 → before는 재구성이 아니다” 주장 검증: `docs/daily_logs/2026-07-29/work_log.md:770,775,884,890`와 `docs/verifications/2026-07-29/slice1b_context_window_output_cap_reaudit.md:87`에 11,905(첫 호출 prompt_tokens)·11,837(audit 첫 입력)이 **실측값**으로 기록. 11,841은 그 사이. 교차참조 성립.

## Issues / Risks

### Blocking (계약 의무) — 없음

경계 행렬의 모든 fire/NOT-fire 셀이 코드와 테스트에 매핑됨. 계약이 요구하는 잠금(1-based·`bool`·범위·구 wire 거부, fails-closed, 번호 순서==allowlist 순서, 회계 양방향, 공개 계약 무변)이 누락 없이 존재. 계약 내부 모순 없음. spec-silent-but-enforced 갭(코드가 계약이 안 다룬 것을 거부/허용) 발견 안 됨 — `1.0`/`[1]`/항목내 중복 거부는 모두 템플릿 지시문과 일치.

### Hardening recommendations (비차단)

- **H1** — `test_each_number_maps_to_its_own_package_item`(`test_writing_context_pointer.py`)이 all-micro 픽스처를 써서 macro/micro 순서 발산을 단독으로는 감지 못 함. 해당 발산은 e2e 셀(`test_extractor_cites_a_number_and_the_service_maps_it_back`, 혼합 macro+micro 패키지)과 연속 번호 셀이 잡으므로 **매트릭스 셀은 채워져 있음**(빈 셀 아님). 혼합 픽스처 한 판으로 그 테스트 자체를 자급자족하게 만들면 더 직접적이지만, 계약 요구사항은 아님.
- **H2** — 실측(−72.8%, 3/3 strict parse)은 **이 검증에서 독립 재실측하지 못함**(외부 12B `n_ctx=16384` + 베타 Mongo 69-항목 heavy project가 필요). 결정론적 부분형식(before 교차참조, 회계 산술, 렌더 형식)은 검증됐으나, 토큰 절감량과 실제 strict-parse OK는 작업자 보고치. 오너가 공표 전 재실측 권장.

## Verdict

**합격(PASS).**

이유(하중): (1) 경계 행렬에 빈 셀 없음 — 계약이 요구하는 모든 fire/NOT-fire 분기가 명명된 회귀로 매핑; (2) 계약 본문·로그·브리프 간 모순 없음; (3) 공개 계약 `schema.d.ts` 재생성 diff 0으로 무변 확인; (4) 뮤테이션 7종(양방향)이 독립적으로 해당 셀을 물음 — 특히 하중 불변조건(번호 순서==allowlist 순서)의 양 절반(C micro 재시작·D 순서 반전)이 모두 포착; (5) accept/Gate는 `pointer_wire` 그대로라 “도메인 무변” 주장이 코드로 입증. 비차단 후보(H1·H2)는 스펙을 넘어서는 보강 후보이며 합격을 가리지 않음.

## Outstanding items

- **미커밋 워킹 트리**: 작업물 14파일 + 2 신규가 커밋되지 않은 채 남아 있음. 오너의 커밋 결정 대기.
- **검증 중 과정 메모(투명성)**: 뮤테이션 원복을 위해 `git checkout -- report.py`를 썼다가 — 이것이 커밋되지 않은 R-e(v2) 작업을 지우고 HEAD(v1)로 되돌리는 실수였음. 즉시 최초 Read한 v2 내용으로 정확히 복구했고, `git diff --stat`(318+/243−, 시작 시점과 동일)·`py_compile`·집중 suite 102/26·변형 마커 잔류 0로 복구 충실성 확인. 작업자 의도 상태로 복원됨. (이후 뮤테이션은 `git checkout` 대신 역방향 Edit만 사용.)
- **실측 재실측**(H2): 외부 12B 경로에서 −72.8%·3/3 parse를 오너가 재확인할 것.
- **다음 슬라이스(K-3 가드)**: 계약이 이미 남겨둔 사안 — 창 8192에서 `3,216 + 6,144 = 9,360 > 8,192`이고 초과가 400이 아닌 조용한 잘림. “초과 시做什么”는 오너 결정(조용히 제외 / 400 거부 / 경고 실어 통과).

## Reproduction

```bash
# 공개 계약 무변
cd frontend && npx --no-install openapi-typescript <(python3 ../scripts/dump_openapi.py) -o /tmp/s.d.ts \
  && diff src/api/schema.d.ts /tmp/s.d.ts   # expect: no output

# 집중 + 표면 회귀
PYTHONPATH=. python3 -m pytest tests/test_writing_context_pointer.py tests/test_context_search.py \
  tests/test_context_search_candidate_memory.py tests/test_context_search_canonical_memory.py \
  tests/test_writing_report_live_diag.py -q                                   # 102 passed / 26 subtests
PYTHONPATH=. python3 -m pytest tests/ -q -k "writing or context_search or report_live_diag or context_pointer or live_diag"  # 598 passed / 22 skipped

# 전체 수집
PYTHONPATH=. python3 -m pytest --collect-only -q                              # 1720 collected

# 뮤테이션(예: D 순서 반전) — Edit로 context_pointer.py package_pointers를
# (*micro_evidence, *macro_items)로 바꾼 뒤:
PYTHONPATH=. python3 -m pytest \
  "tests/test_writing_context_pointer.py::ReportServicePointerTest::test_extractor_cites_a_number_and_the_service_maps_it_back" -q
# expect: FAILED (claim [2] → 다른 항목 매핑) → 역방향 Edit 원복
```
