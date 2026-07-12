# 독립 검증 — Phase 6 Review Inbox 액션 어포던스 (SoT v1.6.67)

## Subject metadata

- **Date**: 2026-07-12
- **Requester**: 오너("다음작업 검증해줘. … Phase 6 Review Inbox 액션 어포던스 (SoT v1.6.67) — 완료, 미커밋").
- **Verifier**: 독립 세션(검증자).
- **Target slice**: Review Inbox 액션 어포던스 — `ActionAffordance` descriptor + 순수 함수 3종(`candidate_affordances`/`conflict_affordances`/`gate_finding_affordances`) + list/detail/gate envelope에 `actions` additive.
- **Canonical spec reference**: `docs/plans/06-review-inbox-affordances-decisions.md`(Resolved, D1=자격 주석형·D2=3섹션 전부·D3=list+detail) + 경계 매트릭스 11행 + 자격 규칙 authority(`reconciliation.py:69-74`, gate_findings v1.6.65) + `docs/system-contract-sot.md` v1.6.67.
- **Source of work**: working tree, uncommitted(`git diff HEAD` 기준 7파일 + untracked 브리프). HEAD = `6e15798`(v1.6.66).

## Scope

1. **Spec contract** — 브리프 D1~D3, 매트릭스 11행, 자격 규칙 authority 대 일관성(cross-check).
2. **Implementation code** — `review_inbox.py`(`ActionAffordance`, 순수 함수 3종, 자격 판정), `main.py`(envelope additive + serializer 공유).
3. **자격 규칙 일치** — 어포던스 자격(merge/split/gate)이 실제 write authority(reconcile character-only+matched, gate open-only)과 일치→ "어포던스가 거짓말하지 않는다".
4. **Regression tests** — 회귀 +7(HTTP envelope 2 + pure 5).
5. **Boundary matrix** — 매트릭스 11행 각 분기가 named test로 매핑되는지 추적.
6. **Full suite + mutation** — 805/48/101 재도출 + 자격 규칙 변형 4종으로 bite 증명.

라이브 Mongo/Chroma는 무관(read-only 계층, 외부 의존 없음).

## Methodology

브리프 매트릭스 11행을 lock list로 세우고, 코드·테스트·스펙에 대입. 자격 규칙이 "어포던스가 eligible=True인데 실제 write가 실패"(over-strict 거짓) 또는 "eligible=False인데 실제 write가 성공"(under-strict 거짓)하는지 양방향 mutation으로 검증.

명령(재현은 §Reproduction):
- `git diff HEAD -- services/application/app/analysis/review_inbox.py services/application/app/main.py` — 프로덕션 diff.
- `git diff HEAD -- tests/test_analysis_apply_api.py` — 테스트 diff(+7).
- `python3 -m pytest tests/test_analysis_apply_api.py tests/test_candidate_review.py -q -p no:cacheprovider` — focused.
- `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` — 전체(805/48/101).
- mutation: `cp` 백업 → 정확한 문자열 replace → focused pytest → 복구(MA~MD 4종 + B1 closure의 edit M3 별도 기록).

## Findings

### 1. Spec contract — 내부 일관성

브리프 D1~D3 ↔ 자격 규칙 ↔ 매트릭스 11행 ↔ "성격"(read-only additive)이 전부 일관. 미확정 경계(부분 승인/retry·merge/split 일반화·frontend)가 §"Deferred"와 일치. D2로 gate finding payload가 확장되는데, 이것이 전용 `/gate-findings` API에도 동일하게 반영돼야 한다는 요구가 매트릭스 행 10으로 구체화됨 — 이 행이 없었다면 "gate actions가 review-inbox에만 붙고 전용 API엔 누락"되는 비일관을 놓칠 수 있었다. 내부 모순 없음.

### 2. Implementation code — 스펙 리터명 대 일치

- `review_inbox.py:104-115` `ActionAffordance` — frozen/slots, `action/eligible/reason`(reason default None). D1 자격 주석형과 일치.
- `review_inbox.py:118-125` `candidate_affordances` — confirm/reject/edit 전부 `eligible=True, reason=None`. inbox가 needs_review·미승격만 노출한다는 전제(D2 자격 규칙 첫 줄)와 일치 → 행 1.
- `review_inbox.py:128-143` `conflict_affordances` —
  - `is_character = conflict.entry.candidate_type is CHARACTER_OBSERVATION`
  - `has_matched = conflict.matched_memory is not None`(**resolved 실체** 기준, id 기준 아님)
  - 비-character: merge·split 둘 다 `eligible=False, reason="merge/split is character-only"`(행 4)
  - character+matched: merge·split 둘 다 eligible(행 2, 행 5)
  - character+matched 없음: merge False reason="merge requires a matched canonical memory", split True(행 3, 행 5)
- `review_inbox.py:146-153` `gate_finding_affordances(*, is_open: bool)` — open이면 resolve/dismiss eligible, terminal이면 False reason="gate finding is already terminal"(행 6, 7). **`is_open: bool` 파라미터**로 gate_findings 모듈에 의존하지 않음 → review_inbox↛gate_findings 모듈 경계 유지.
- `main.py:1750-1755` `_affordance_payload` — action/eligible/reason 직렬화.
- `main.py:1767-1770`(list+detail 공통)·`:1793-1796`(detail conflict)·`:1848-1853`(gate finding)에 `actions` additive. D3(list+detail)와 일치 → 행 8, 9.
- `main.py:1834` `_gate_finding_payload`가 review-inbox list(1816)·review-inbox detail·`/gate-findings` list(1863)·`/gate-findings/{id}`(1876)·resolve/dismiss 응답(1890) **전부**에서 호출 → gate actions가 양쪽에 공유 → 행 10.

### 3. 자격 규칙 authority 일치 ("어포던스가 거짓말하지 않는다")

- merge 자격을 `conflict.matched_memory` 실체 기준으로 판정(`review_inbox.py:131`). `ConflictDetail`(`review_inbox.py:25-27, 80-90`)은 `entry.matched_memory_id is not None`일 때 memory를 조회해 채우고, 조회 실패 시 `matched_memory=None`. 따라서 matched_memory_id가 있어도 memory 유실 시 merge `eligible=False` — 실제 reconcile이 그 조건에서 실패하므로 정직(브리프 Follow-up #2와 일치).
- 자격 규칙이 브리프 인용 authority(`reconciliation.py:69-74` character-only+matched 강제, gate_findings open-only)와 일치 — eligible=True인 분기(character+matched merge, character split, open gate)와 실제 write 허용 조건이 대응.

### 4. Boundary matrix — lock 추적 (11행)

| # | 분기 | 방향 | 잠근 테스트 | mutation bite |
|---|---|---|---|---|
| 1 | candidate 전부 eligible | under-strict | `test_candidate_actions_all_eligible` | — |
| 2 | character+matched merge eligible(True, reason=None) | under-strict | `test_affordances_declared_on_list_detail_and_gate_findings`(HTTP detail, 실객체) | MA |
| 3 | character·matched 없음 merge False | over-strict | `test_character_conflict_without_matched_blocks_merge_only` | MA |
| 4 | 비-character 둘 다 False | over-strict | `test_non_character_conflict_blocks_merge_and_split` | MB |
| 5 | character split eligible(matched 불요) | under/over | `test_character_conflict_without_matched...`(split True) | MD |
| 6 | gate open resolve/dismiss eligible | under-strict | `test_gate_finding_open_allows_resolve_and_dismiss` | MC |
| 7 | gate terminal False | over-strict | `test_gate_finding_terminal_blocks_resolve_and_dismiss` | MC |
| 8 | list item candidate actions | under-strict | `test_affordances_declared...`(list item) | — |
| 9 | detail conflict actions | under-strict | `test_affordances_declared...`(detail conflict) | — |
| 10 | gate actions 양쪽 payload | under-strict | `test_affordances_declared...` + `test_gate_finding_actions_present_on_dedicated_endpoint` | — |
| 11 | read-only(상태·색인 무변) | over-strict | 정적: 순수 함수 3종은 입력 `AnalysisCandidate`/`ConflictDetail`/bool만 읽고 tuple 반환(입력 불변 dataclass), write 엔드포인트는 호출 안 함 | — |

11행 전부 추적됨(8행 named test + mutation bite, 3행 정적/구조 커버). 빈 cell 없음.

### 5. Mutation testing — 자격 규칙 bite 실증

| 변형 | 기대 | 결과 |
|---|---|---|
| MA: `conflict_affordances` merge 자격 `is_character and has_matched`→`is_character`(matched 요구 제거) | 행 3 under-strict 붕괴 | `test_character_conflict_without_matched...` FAIL ✅ |
| MB: merge/split 자격 `is_character`→`True`(character-only 완화) | 행 4 over-strict 붕괴 | `test_non_character_conflict_blocks_merge_and_split` FAIL ✅ |
| MC: gate `is_open`→`True`(terminal도 eligible) | 행 7 over-strict 붕괴 | `test_gate_finding_terminal_blocks_resolve_and_dismiss` FAIL ✅ |
| MD: split 자격 `is_character`→`is_character and has_matched`(matched 요구 추가, over-strict drift) | 행 5 under-strict 붕괴 | `test_character_conflict_without_matched...`(split) FAIL ✅ |

4개 변형 전부 guard가 bite. 자격 규칙이 양방향으로 잠겨 있음.

### 6. Full suite

`python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **805 passed / 48 skipped / 101 subtests passed**. 작업자 클레임과 정확히 일치(종전 798 → +7). mutation 복구 후 `git diff --stat HEAD`로 무결성 확인(review_inbox.py +57/-1, candidate_review.py 무변).

### 7. 행 2의 실객체 흐름 검증

`_open_conflict` 헬퍼(`tests/test_analysis_apply_api.py:427-448`)가 `memory.promote_candidate(...)`로 실제 canonical memory를 mint하고 CHARACTER type conflict를 `matched_memory_id=prior_memory.id`로 enqueue. 그래서 `test_affordances_declared...`의 detail conflict에서 `afford["merge"]["eligible"]==True, reason is None`이 **진짜 matched 실체**로 판정됨 — stub/null 경로가 아님. 작업자 클레임 "character+matched(merge eligible)는 실객체가 흐르는 HTTP detail로 잠금"과 일치.

## Issues / Risks

### Blocking (contract obligations)

- 없음. 매트릭스 11행이 named test로 잠겨 있고(8행), 자격 규칙 변형 4종이 모두 bite하며, 자격 판정이 실제 write authority와 일치한다.

### Hardening recommendations (non-blocking)

- **H1 — 행 11(read-only)이 직접 assertion으로 잠기지 않음**. 순수 함수 3종이 입력을 변경하지 않는다는 over-strict(상태·색인 side effect 발생 시 실패)는 정적 독해(tuple 반환, 불변 dataclass, write 엔드포인트 미호출)로 커버하지만, "어포던스 호출 전후로 candidate/queue/memory 상태 불변"을 직접 assert하는 회귀는 없다. pure 함수라 실질적 위험은 없으나, 매트릭스가 명시한 행이므로 snapshot-before/after assertion을 추가하면 행 11도 named test로 승격.
- **H2 — `reason` 문자열이 계약 리터럴로 고정 안 됨**. `"merge/split is character-only"`, `"merge requires a matched canonical memory"`, `"gate finding is already terminal"`가 코드에 리터럴로 박혀 있고 테스트도 이 값을 assert하나, SoT/브리프가 reason 문자열을 계약으로 고정하지 않았다. 현재 테스트가 값을 고정하므로 비결함이나, reason이 사용자 노출 문구라 localization/문구 변경 시 계약 업데이트가 필요 — SoT에 reason 표준 문구를 명시하면 경계가 더 또렷.

## Verdict

**합격(Pass, 조건 없음).**

이유(load-bearing):
- 코드가 브리프 D1~D3 자격 규칙과 정확히 일치하고, 계약 내부(changelog ↔ 브리프 ↔ 매트릭스 ↔ authority 인용)에 모순이 없다.
- 매트릭스 11행이 named test 또는 정적 커버로 전부 잠겨 있고, 자격 규칙 변형 4종(MA~MD)이 guard의 bite를 실증했다.
- 어포던스 자격이 실제 write authority(reconcile character-only+matched, gate open-only)와 일치 → "어포던스가 거짓말하지 않는다"를 merge 자격의 resolved-실체 기준 판정이 보장.
- read-only로 도메인 write·상태 모델·색인 무변(additive만). 전체 suite 805/48/101이 작업자 클레임과 정확히 일치.
- 비차단 H1(행 11 직접 assertion)·H2(reason 표준 문구)는 향후 보강 후보.

## Outstanding items

- 작업 미커밋(working tree). 커밋 여부는 오너 결정 대기.
- B1 closure(별도 `candidate_edit_b1_closure.md`)과 함께 이 슬라이스는 합격 — 커밋 진행에 검증상 이견 없음.

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system

# focused (affordance + edit)
python3 -m pytest tests/test_analysis_apply_api.py tests/test_candidate_review.py -q -p no:cacheprovider

# full suite (805 passed / 48 skipped / 101 subtests)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider

# mutation MA (merge drops matched) — must FAIL row 3
cp services/application/app/analysis/review_inbox.py /tmp/ri.bak
python3 - <<'PY'
p="services/application/app/analysis/review_inbox.py"
s=open(p,encoding="utf-8").read()
open(p,"w",encoding="utf-8").write(s.replace(
'        ActionAffordance("merge", is_character and has_matched, merge_reason),',
'        ActionAffordance("merge", is_character, merge_reason),',1))
PY
python3 -m pytest tests/test_analysis_apply_api.py -q -p no:cacheprovider | tail -3   # expect FAIL
cp /tmp/ri.bak services/application/app/analysis/review_inbox.py
git diff --stat HEAD -- services/application/app/analysis/review_inbox.py              # empty
```
