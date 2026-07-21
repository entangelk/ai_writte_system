# 검증 기록 — 문체/분량 슬라이스 증분 3 (D4+D5+D6): character aspect + Gate `style` finding + 문체 우선순위

## Subject metadata

- **날짜**: 2026-07-21
- **요청자**: 오너(entangelk) — “작업 Ai의 작업 내용 확인해서 검증하고 의심하고 또 의심해줄래? 증분 3(D4+D5+D6)을 완료하고 커밋했다.”
- **검증자**: 독립 AI(Claude, 검증 요청 받은 세션). 구현 작업 Ai와 다른 세션.
- **검증 대상 슬라이스/아티팩트**: 문체/분량 슬라이스 증분 3 — D4(`character_observation` optional `aspect`)·D5(Gate `style` finding)·D6(문체 우선순위 계약). 커밋 `41999ef`(D4, SoT v1.7.23) + `8f900f0`(D5+D6, SoT v1.7.24).
- **정본 참조(canonical spec)**: `docs/system-contract-sot.md` v1.7.24 (버전 로그 v1.7.22/v1.7.23/v1.7.24 엔트리 + §Phase 2A 최소 payload schema 조항 + §Phase 5 생성/게이트 `style`·`output_length` 조항).
- **검증 대상 작업의 source**: `main` 브랜치 커밋 `8f900f0`(HEAD), `41999ef`. working tree clean (검증 시점).

## Scope (계약 스코핑)

정본 계약 스코프(이 슬라이스가 지배하는 surface만):

1. **정본 문서**
   - `docs/system-contract-sot.md` — v1.7.23/v1.7.24 버전 로그 엔트리, §Phase 2A “최소 payload schema” 조항(aspect optional), §Phase 5 “Gate `style` finding + 문체 우선순위”·“생성 분량 프리셋” 조항.
   - `docs/plans/writing-style-and-length-control-decisions.md` — D4=B(오너=optional)·D5=A·D6=A 절 + 2026-07-21 구현 리터럴 보완 결정 2건.
2. **구현 코드**
   - D4: `services/application/app/analysis/schema.py`(`_OPTIONAL_FIELDS`, `validate_candidate_payload`), `extractor.py`·`prompt_templates.py`(추출 프롬프트), `main.py`(payload 직렬화).
   - D5/D6: `services/application/app/writing/models.py`(`WritingGateFindingType.STYLE`), `gate.py`(parse 경계 제약 + decision 우선순위), `gate_prompt.py`(Gate 프롬프트), `revise_gate.py`(`_is_eligible_continuity_revise`).
3. **회귀 테스트**
   - `tests/test_analysis_extractor_schema.py::CharacterAspectPayloadTest`(7).
   - `tests/test_writing_gate.py::GateStyleFindingTest`(5).
   - `tests/test_writing_revise.py`(style ineligible subtest +1).
   - `frontend/src/writing/WritingPanel.test.tsx`(“style advisory (증분 3)” +1).
4. **공공 envelope/schema**: `frontend/src/api/schema.d.ts` `WritingGateFindingType` enum, gen:api 재생성 byte-identical.
5. **전체 suite**: backend pytest(전체), frontend vitest(전체), `tsc --noEmit`, `git diff --check`.

Out of scope(명시): 증분 1(D1+D2, v1.7.21)·증분 2(D3, v1.7.22, 이미 `verifications/2026-07-21/increment2_d3_output_length_preset.md`에서 합격). LLM 비결정 동작(프롬프트 지시를 LLM이 따르는지)은 슬라이스가 “LLM 미사용”으로 명시했고 결정적 계약(parse/priority/자동revise 배제)만이 hard test 대상 — 이 한계는 본 기록 Methodology·Verdict에 명시.

## Methodology

- **계약 스코핑 우선**: 코드를 읽기 전 정본(SoT v1.7.23/v1.7.24 + decisions D4/D5/D6)에서 boundary matrix를 먼저 구축. 각 “발화해야/하면 안 될” 분기와 리터럴(style, warning, needs_user_review, decision 우선순위 제외, aspect optional, character-only, taxonomy 3종, 마이그레이션 불요)을 나열한 뒤 코드·테스트가 이를 채우는지 추적.
- **정량 재계산(신뢰 금지)**: 커밋 메시지/SoT의 self-claim 수치를 인용하지 않고 backend/frontend/tsc/gen:api를 직접 재실행해 비교.
- **적대적 mutation 검증(양방향 가드 증명)**: under-strict 방향을 docstring 주장만 믿지 않고, 3개 가드를 실제로 mutation해 해당 회귀 테스트가 FAIL로 반응하는지 증명.
- **사용 명령**(재현성은 아래 Reproduction에 전문 기록).

## Findings

### F1. 정량 수치 — 재계산 결과 커밋 주장과 정확히 일치

| surface | 커밋/SoT 주장 | 재계산 결과 | 일치 |
|---|---|---|---|
| backend pytest(전체) | 1250 passed / 73 skipped / 326 subtests | 1250 passed, 73 skipped, 326 subtests passed (53.41s) | ✅ |
| frontend vitest(전체) | 162 passed / 11 files | Test Files 11 passed (11), Tests 162 passed (162) | ✅ |
| `tsc --noEmit` | clean | exit 0 | ✅ |
| `gen:api` | `WritingGateFindingType`에 `style` 1개 additive | 재생성 후 `schema.d.ts` diff 0(byte-identical) | ✅ |
| `git diff --check` | clean | clean | ✅ |

- 증분간 delta 정합성도 확인: D4 commit 주장 1245/322 → D5+D6 주장 1250/326. delta +5 passed / +4 subtests는 신규 `GateStyleFindingTest`(5 method, 그중 `test_style_may_only_recommend_needs_user_review`의 subtest 3개) + revise style ineligible subtest(+1)와 정확히 일치.

### F2. D4 — `character_observation` optional `aspect` 구현이 계약 리터럴과 일치

- `schema.py:27-29` `_OPTIONAL_FIELDS = {CHARACTER_OBSERVATION: ("aspect",)}`. character-only. ✅(SoT v1.7.23 “optional `aspect` … 캐릭터 어투 식별”)
- `schema.py:42-48` exact-match 단정이 (a) `required ⊆ observed`(누락 required 거절, “payload is missing required fields”), (b) `observed ⊆ required∪optional`(unknown field 거절, “payload has unknown fields”)로 분해. ✅
- `schema.py:52-58` present field(required·optional 무관) non-empty string 검증, normalized는 required→optional 순 결정적 조립. ✅
- 마이그레이션 불요: `{name, observation}`이 그대로 유효 → `(a)` 만족, `(b)` 만족. ✅(SoT “기존 `{name, observation}` payload는 그대로 유효, 마이그레이션 불요”)
- `event`/`open_question`은 `_OPTIONAL_FIELDS`에 없음 → aspect가 unknown field로 거절. ✅(SoT “`event`/`open_question`에는 허용되지 않는다”)
- aspect 값은 자유 문자열(enum 검증 부재). ✅(SoT “자유 문자열(예: `voice`/`trait`)”)
- 추출 프롬프트 2곳 안내: `prompt_templates.py:37`(기본), `extractor.py:206`(repair) — “optional aspect (e.g. voice/trait), omit for plain”. ✅
- wholesale 직렬화 surface: `main.py:1646`·`main.py:2673` `"payload": dict(candidate.payload)`. aspect가 추가 코드 없이 review inbox/candidate detail/conflict diff에 노출. ✅(SoT/decisions “저장 payload는 wholesale 직렬화 … 추가 코드 없이 surface”)
- **정본 자기모순 부재**: decisions D4=B 옵션 표의 원 리터럴(exact tuple 필수)은 2026-07-21 보완 결정으로 optional로 대체됐고, SoT v1.7.23 엔트리 + §Phase 2A 조항이 동일하게 optional을 서술. 정본 내부 충돌 없음. ✅

### F3. D5/D6 — Gate `style` finding + decision 우선순위 구현이 계약 리터럴과 일치

- `models.py:63-72` `WritingGateFindingType.STYLE = "style"` 추가. ✅(SoT v1.7.24 “`WritingGateFindingType`에 `style` 추가”)
- `gate.py:157-163` style parse 제약: `severity is not WARNING or recommendation is not NEEDS_USER_REVIEW` → `ValueError`. 즉 warning+needs_user_review만 허용, error/block/revise/retrieve_more는 전부 거절. ✅(SoT “parse 경계에서 … 고정(그 외는 `ValueError`)”)
- `gate.py:122-130` decision 우선순위에서 style 제외: `decision_driving` = style 아닌 findings, `max(..., key=_PRIORITY.get, default=PASS)`. style-only → 빈 → default `PASS`. ✅(SoT “decision 우선순위 계산에서 제외되어 findings가 style뿐인 후보는 여전히 `pass`”)
- `gate.py:32-36` `_PRIORITY` = block(4) > needs_user_review(3) > retrieve_more(2) > revise(1) > pass(0). `gate_prompt.py:30` 서술 순서와 일치. ✅
- `revise_gate.py:533-538` `_is_eligible_continuity_revise` = `finding_type is CONTINUITY and rec==REVISE and evidence 비어있지 않음 and 정확히 1회 출현`. type으로 style 배제 → style은 자동 revise 대상 아님. ✅(SoT/decisions “자동 revise 대상 아님(continuity 전용)”)
- block 불가: style rec=block → `gate.py:157-163`에서 `ValueError`. ✅(SoT “`block`이 될 수 없다”)
- **Gate가 실제로 문체 설정을 받는가(inert 점검)**: `gate_prompt.py:69` `build_writing_gate_request`가 `"context_package": format_context_package(package)`를 직렬화하고, `prompt.py:72-90`(특히 80-83행)가 `package.project_brief`의 `style_rules`/`preferred_patterns`/`forbidden_patterns`/`style_examples`를 `<project_brief>` 섹션으로 렌더링. 즉 Gate LLM은 저자 문체 설정을 실제로 수신 → `style` finding이 발화 불가(inert)하지 않음. ✅ (이 점검은 본 검증이 계약 일치성을 넘어 기능 실연 가능성까지 확인한 지점.)
- **정본 자기모순 부재**: decisions D5=A(“warning 전용·자동 revise 제외·block 없음”)와 2026-07-21 보완 결정(“style은 advisory, decision을 escalate하지 않는다”)이 SoT v1.7.24 엔트리 + §Phase 5 조항에서 동일 서술. “pass only with no findings” → “no non-style findings” 완화도 decisions·SoT 양쪽에 명시. 정본 내부 충돌 없음. ✅
- D6 우선순위(“저자 설정 > canonical 관찰 > candidate 관찰”, “Gate는 설정 기준만 판정, 관찰→설정 자동 반영 없음”): Gate 프롬프트가 “judge it only against the author’s stated style”(`gate_prompt.py:28`)로 지시하며 관찰→설정 자동 반영 코드는 존재하지 않음. ✅ (LLM 행동 계약이라 hard code test 대상은 아님 — 한계는 Verdict에 명시.)

### F4. Boundary matrix — contract-required 분기가 전부 테스트로 매핑됨 (빈 셀 없음)

**D4 (`CharacterAspectPayloadTest`, 7)**

| contract 분기 | 테스트 | 결과 |
|---|---|---|
| `{name,observation}` accepted(하위호환) | `test_aspect_is_optional_and_backward_compatible` | ✅ |
| `{name,observation,aspect}` accepted + 보존 | `test_aspect_is_accepted_and_preserved` | ✅ |
| aspect 자유 문자열(enum 아님) | `test_aspect_value_is_a_free_string_not_an_enum` | ✅ |
| aspect 빈 문자열 → 거절 | `test_empty_aspect_is_rejected` | ✅ |
| aspect on event → 거절 | `test_aspect_is_rejected_on_non_character_types`(event) | ✅ |
| aspect on open_question → 거절 | 동상(question) | ✅ |
| 기타 unknown field(mood) → 거절 | `test_other_unknown_fields_still_rejected` | ✅ |
| required 누락 → 거절 | `test_missing_required_field_still_rejected` | ✅ |

**D5/D6 (`GateStyleFindingTest` 5 + revise 1 + frontend 1)**

| contract 분기 | 테스트 | 결과 |
|---|---|---|
| style-only → decision PASS(D6 crux) | `test_style_only_findings_still_pass` | ✅ (mutation 증명) |
| style + revise-finding → REVISE | `test_style_does_not_lift_a_non_style_decision` | ✅ |
| style + block-finding → BLOCK, style carried | `test_style_is_carried_but_not_decision_driving_under_block` | ✅ |
| style severity=error → ValueError | `test_style_must_be_warning_not_error` | ✅ (mutation 증명) |
| style rec=block → ValueError | `test_style_may_only_recommend_needs_user_review`(block) | ✅ (mutation 증명) |
| style rec=revise → ValueError | 동상(revise) | ✅ (mutation 증명) |
| style rec=retrieve_more → ValueError | 동상(retrieve_more) | ✅ (mutation 증명) |
| style 자동 revise 대상 아님(type 배제) | `test_writing_revise.py` STYLE in invalid_findings | ✅ |
| frontend: pass+style accept 활성 | `WritingPanel — style advisory` (`acceptButton` enabled) | ✅ |
| frontend: advisory 문구 표시 | 동상(`getByText(/문체 참고 사항…채택/`)`) | ✅ |
| frontend: style은 loop 유발 안 함 | 동상(`fetchMock` 2회 = generate+gate만) | ✅ |

- **boundary matrix에 빈 셀 없음**. contract가 요구하는 모든 hard 분기(발화해야/하면 안 될)가 named 테스트로 추적됨.

### F5. 양방향 가드 — mutation test로 under-strict 발화를 경험적으로 증명

docstring 주장만 믿지 않고 3개 핵심 가드를 mutation해 해당 테스트가 FAIL로 반응함을 확인(매 mutation 후 `git checkout`으로 원복, working tree clean 유지).

| mutation | 기대 FAIL 테스트 | 실제 결과 |
|---|---|---|
| `gate.py:127` `if item.finding_type is not ...STYLE` → `if True`(style을 우선순위에 포함) | `test_style_only_findings_still_pass` | FAIL — `ValueError: decision does not match finding priority` ✅ |
| `gate.py:157` style 제약 조건 → `if False and …`(가드 중화) | `test_style_must_be_warning_not_error` + `test_style_may_only_recommend_needs_user_review`(3 subtest) | 4 failed ✅ |
| `schema.py:29` `EVENT_OBSERVATION: ("aspect",)` 추가(aspect 전역 허용) | `test_aspect_is_rejected_on_non_character_types`(event) | FAIL — `AssertionError: InvalidAnalysisPayload not raised` ✅ |

- 즉 under-strict(bug 재발 시 재실패)와 over-strict(정상 케이스 오경고 시 실패) 양방향 모두 테스트가 실제로 잡아냄이 증명됨.

### F6. 부수 점검 — benign

- `models.py`에서 `STYLE = "style"`이 2회(72행 `WritingGateFindingType`, 107행 `RiskNoteType`) 등장. 107행은 별개 enum `RiskNoteType`의 기존 멤버(리스크 노트용)이며 본 슬라이스 diff는 `WritingGateFindingType`만 추가 → 우연한 중복 아님, 이슈 아님.
- 옛 에러 메시지 “payload fields do not match candidate type” 잔존 0건(grep exit=1). 신 메시지 2종(“missing required fields”/“unknown fields”)로 깔끔히 대체되었고 어떤 테스트도 옛 메시지를 assertion하지 않음.
- `frontend/openapi.json`은 gitignored → gen:api 재생성이 repo를 dirty하게 만들지 않음.

## Issues / Risks

### Blocking (contract 위반)

**없음.**

- spec 위반, 추적 안 된 contract-required 분기, 누락된 over-strict guard, 정본 내부 모순 어느 것도 발견되지 않았음.
- 정량 수치는 전부 재계산되어 커밋 주장과 일치.
- contract-required hard 분기는 전부 named 회귀 테스트로 매핑(boundary matrix 빈 셀 없음).
- 양방향 가드는 mutation으로 경험적으로 증명됨.

### Hardening recommendations (non-blocking, spec을 넘어서는 보강 후보)

이하 모두 현 spec이 열거하지 않는 경계로, 슬라이스 실패 사유가 아님.

> **처리(2026-07-21 후속 커밋)**: #1·#2·#3는 code-testable이라 독립 검증 직후 회귀 테스트 3건으로 보강했다(양방향 가드 mutation으로 under-strict 발화를 경험적으로 증명). #4는 LLM 행동 계약이라 code test 불가 → 그대로 후속 풀스택 12B smoke 권장으로 남김. 보강 상세는 `docs/daily_logs/2026-07-21/work_log.md` “증분 3 독립 검증 후 비차단 hardening 보강” Task. 본 절은 검증 시점(합격)의 audit 소견을 그대로 보존한다.

1. **D4 — aspect 비문자열 타입(aspect=123 등) 거절 미명시** *(후속 보강 적용: `test_non_string_aspect_is_rejected`)*: 동일 `isinstance` 가드가 잡지만(aspect=” “·required non-string 케이스로 간접 커버), aspect=number 전용 케이스가 없었음.
2. **D4 — `{name,observation,aspect,mood}`(aspect+다른 unknown 혼합) 미열거** *(후속 보강 적용: `test_aspect_does_not_permit_other_unknown_fields_alongside`)*: 동일 unknown-field 가드가 잡지만(test_other_unknown_fields_still_rejected는 mood 단독) 혼합 케이스가 미명시였음.
3. **D5 — style + 비style `needs_user_review` 혼합 → decision `needs_user_review` 미명시** *(후속 보강 적용: `test_style_does_not_suppress_a_non_style_needs_user_review`)*: `max over decision_driving`가 정확히 처리하나, style+revise·style+block만 열거되고 style+needs_user_review(비style) 케이스가 없었음.
4. **D6 “설정 기준만 판정 / 관찰→설정 자동 반영 없음”은 prompt-level 계약** *(후속 보강 불가 — live smoke 권장 유지)*: LLM 행동이라 결정적 code test가 불가. 결정적 envelope(parse 제약·decision 제외·auto-revise 배제)은 본 기록처럼 hard test되었으나, “LLM이 실제로 관찰을 설정에 반영하지 않는가”는 live 12B smoke만이 확인 가능(슬라이스는 “LLM 미사용” 명시). 후속 풀스택 smoke 시 이 행동을 관찰할 것을 권장.

## Verdict

**합격 (PASS, 조건 없음).**

이유(load-bearing):
1. 정량 수치(backend 1250/73/326, frontend 162/11, tsc clean, gen:api byte-identical)를 self-claim이 아닌 재실행으로 재도출했고 전부 일치.
2. D4/D5/D6 모든 contract-required hard 분기가 boundary matrix에서 named 테스트로 매핑되며 빈 셀이 없음.
3. 핵심 가드 3종(D6 decision 제외, D5 style parse 제약, D4 character-only)을 mutation으로 under-strict 발화를 경험적으로 증명.
4. 정본 자기모순 부재(SoT v1.7.23/v1.7.24 ↔ decisions D4/D5/D6 ↔ 구현 리터럴 전 일치).
5. 기능 inert 의심(Gate가 문체 설정을 실제 수신하는가)까지 추적하여 `format_context_package`가 `project_brief` style 필드를 렌더링함을 확인.

오너 결정 2건(D4 aspect=optional, D5/D6 style advisory·decision 미escalate)은 decisions doc + SoT + CHANGELOG + work_log에 일관되게 기록됨. 본 검증은 결정 자체를 재평가하지 않고 “구현이 결정된 계약과 일치하는가”만 판정했다.

## Outstanding items (결함 아님, 오너 다음 단계 관련)

- **문체/분량 슬라이스 전체(증분 1~3) 종료**. 다음 갈림길은 비동기 생성 + 결과 패드(`plans/async-generation-pad-decisions.md` D1~D7 확정, 미구현). 증분 2의 2048/4096 프리셋으로 D5(1024 동기 / 2048·4096 비동기) 분기 기준이 성립함.
- **캐릭터 어투(D4 `aspect`) 기반 Gate 대조는 캐릭터-어투 설정 저장이 deferred라 이번엔 프로젝트 문체 설정 대조까지**. aspect는 저장+surface만 되고 Gate는 소비하지 않음 — 이는 SoT v1.7.24가 명시적으로 forward-defense로 서술한 사항(결함 아님). 후속: 캐릭터 어투 설정 저장 + aspect 기반 대조 배선.
- **mood**는 키가 없어 Phase 7.
- 검증 과정에서 working tree를 일시 mutation했으나 매번 `git checkout` 원복, 최종 `git status`·`git diff --check` clean. repo 변경 사항 0(본 검증 기록 파일 신규 작성 제외).

## Reproduction

```bash
# 0. 사전: main 브랜치, HEAD=8f900f0, working tree clean 인증
git -C /mnt/d/devel/에베베/ai_writte_system log --oneline -3
git -C /mnt/d/devel/에베베/ai_writte_system status --short
git -C /mnt/d/devel/에베베/ai_writte_system diff --check

# 1. D4 신규 클래스
python3 -m pytest tests/test_analysis_extractor_schema.py::CharacterAspectPayloadTest -v -p no:cacheprovider
# 기대: 7 passed (+ subtests)

# 2. D5/D6 신규 클래스
python3 -m pytest tests/test_writing_gate.py::GateStyleFindingTest -v -p no:cacheprovider
# 기대: 5 passed (+ 3 subtests in test_style_may_only_recommend_needs_user_review)

# 3. backend 전체 (정량 재현)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
# 기대: 1250 passed, 73 skipped, 326 subtests passed

# 4. frontend 전체
cd frontend && npx vitest run
# 기대: Test Files 11 passed (11), Tests 162 passed (162)

# 5. tsc
cd frontend && npx tsc --noEmit   # exit 0

# 6. gen:api byte-identical (재생성 후 추가 diff 0)
cd frontend && npm run gen:api && git diff --stat src/api/schema.d.ts   # 출력 없음 = byte-identical

# 7. 양방향 가드 mutation 증명 (각 후 git checkout -- <file> 로 원복)
#  (a) gate.py:127 의 `if item.finding_type is not WritingGateFindingType.STYLE` -> `if True`
#      → pytest tests/test_writing_gate.py::GateStyleFindingTest::test_style_only_findings_still_pass  # FAIL
#  (b) gate.py:157 의 `if finding_type is ... STYLE and (` 앞에 `False and` 삽입(가드 중화)
#      → pytest ...::test_style_must_be_warning_not_error ...::test_style_may_only_recommend_needs_user_review  # 4 FAIL
#  (c) schema.py _OPTIONAL_FIELDS 에 `AnalysisCandidateType.EVENT_OBSERVATION: ("aspect",)` 추가
#      → pytest ...::CharacterAspectPayloadTest::test_aspect_is_rejected_on_non_character_types  # FAIL(event)
git checkout -- services/application/app/writing/gate.py services/application/app/analysis/schema.py
git status --short   # clean
```
