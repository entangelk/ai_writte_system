# 2026-09-02 독립 검증 — identity group 구현 페이즈 계획 문서 (28a6dd3)

## Subject metadata

- 검증일: 2026-09-02
- 요청자: 오너 ("계획문서 작성한거 검증해줘")
- 검증자: Claude Code (구현자와 별도 세션)
- 대상: `28a6dd3` "Plan pending candidate identity group slices" (main, 작업 트리 clean). 문서 전용 슬라이스 — 회귀 스위트 대상 없음.
- 정본 참조: `docs/plans/pending-candidate-identity-grouping-decisions.md`(**확정 — C 채택**), `docs/system-contract-sot.md` **v1.8.16**, 신규 `docs/plans/pending-candidate-identity-grouping-implementation-phases.md`(134줄)

## Scope

1. 계획 ↔ 채택 브리프 C 정합 — 슬라이스가 C의 승인/거절 의미론과 Follow-up considerations를 빠짐없이 배정하는가
2. 계획 ↔ SoT v1.8.16 정합 및 저장소 관례(슬라이스 분할 단위·mutation·broader suite·결정 브리프 폴백·생성물 재생성)
3. 문서 인프라 — 인덱스 등재·수 주장·링크·분량 기록

## Methodology

계획·브리프·SoT v1.8.16 행을 전문 대독하고 브리프 Follow-up 5건을 슬라이스에 하나씩 대응시키는 대조표 작성. 가드·링크·수 주장은 실실행(아래 Reproduction). 본 슬라이스는 코드가 없으므로 변이는 부적용 — 문서 검증은 "계약이 계획에 흠집 없이 배정됐는가"가 경계 행렬이다.

## Findings

### 계획 ↔ 브리프 C (본체)

- **C 승인/거절 의미론 완전 반영**: 첫 후보 canonical 승격 → 나머지 기존 compare/apply로 `update|add_evidence|no_change|conflict`(Slice 5), 그룹 거절 전체 거절·멱등(Slice 4), 물리 병합 금지·source ref 보존(목적·Deferred), step 상태 `pending|applied|conflict|failed|skipped`와 재시래 재실행 금지(Slice 5) — SoT v1.8.16 행과 문언 수준에서 일치.
- **Follow-up 5건 대조**:

| 브리프 Follow-up | 계획 배정 | 판정 |
|---|---|---|
| shortlist project/type 격리 + character name/alias + event vector, 전용 judge 근거 저장 | Slice 1 (검증: 격리·자기 id 제외·fake judge 멱등) | ✓ |
| 추이성 모순 → "group revision과 **모순 상태**를 둔다" | Slice 0에 `revision`·`status` 필드만 있고 **모순 상태는 어느 슬라이스·Deferred에도 없음** | 부재(하드닝 1) |
| 그룹 승인 멱등 key·단계별 현황 | Slice 5 (step 저장·같은 key replay·revision mismatch 409) | ✓ |
| uncertain은 관계만 표시해 **사람이 합치기/분리** | Slice 1이 relation 저장까지만 — 표시/액션 슬라이스 없음·Deferred에도 없음 | 부재(하드닝 2) |
| 같은 인물 상이 observation = 추가 근거 | Slice 5의 `add_evidence` 분기(4분기 검증 포함) | ✓ |

- 두 부재 모두 **구조적으로는 폐쇄되지 않았다**(`status`/`revision` 필드가 있고 relation이 전량 저장돼 나중 슬라이스에서 채울 수 있으며, 계획의 공통 규칙 폴백 — "브리프가 열어 둔 계약 리터럴이 유도되지 않으면 구현을 멈추고 결정 브리프" — 도 작동한다). SoT v1.8.16 행 자체는 이 두 항목을 요구하지 않으므로 정본 위반은 아니다.

### 저장소 관례

- 7개 슬라이스는 오너의 "잘게 쪼개기" 지시 관례에 부합(각 슬라이스가 저장 모델→서비스→배선→읽기면→거절→승인→UI로 의존 단방향).
- 공통 작업 규칙이 **테스트 먼저→mutation→복원**, 위험 슬라이스 broader suite(Slice 5), additive payload 시 **OpenAPI/`schema.d.ts` 재생성 명시**(직전 라운드 조건 ②의 교훈이 계획에 제도화됨), 멱등 과잉 방향("다른 key로 이미 끝난 group") 잠금을 요구한다.
- Slice 0 검증에 in-memory+Mongo round-trip·project/type 격리·pair 정규화·purge 고아 제거 — 몽고 어댑터 round-trip 표준 관례(2026-08 선례)를 계획 단계에서 명시.
- Slice 2의 실패 격리(group 판정 실패가 job을 죽이지 않음)·`llm_call_scope`+`correlation_id=analysis_job_id`는 관측 계약·A4=A 격리 관례와 일치.

### 문서 인프라 (전부 정상)

- `docs/plans/README.md` 신규 행(Active — Slice 0부터)·`117개` 수 주장(헤더 노트·`README.md:328`) 일관. docs 가드 **13 passed, 283 subtests** green, `git diff --check` 성공, 트리 clean.
- HANDOFF 착수점이 "Slice 0부터"로 교체·분량 기록 753줄(트리거 783 미달, 관례 준수). work_log에 표·착수 경계 기록.
- 계획 내 상대 링크 유효 — `../system-contract-sot.md`는 실재하고 버전 표기 `v1.8.16`이 현재 정본과 일치한다.

## Issues / Risks

### Blocking (계약 의무)

- 없음 — SoT v1.8.16 행이 요구하는 승인/거절 의미론은 Slice 4·5·공통 규칙에 완전 대응하고, 저장 모델·격리·멱등·감사 관례가 계획에 배정돼 있다.

### Hardening recommendations (비차단)

1. **모순 상태 배정**: 브리프 "group revision과 모순 상태를 둔다"의 모순 상태(그룹 내 `same` 연쇄와 상충하는 `different` relation)를 Slice 0 저장 모델 또는 Slice 1 규칙에 명시하거나, 유예라면 트리거(예: "그룹 내 different relation 관측 시")와 함께 Deferred에 올린다. 미배정 상태로 두면 브리프의 설계 요소가 구현 중 임의 판단으로 흡수된다.
2. **uncertain의 사람 합치기/분리 경로 배정**: relation 저장(Slice 1)만으로 끝나지 않게, 표시·액션을 Slice 6 범위에 넣거나 트리거와 함께 Deferred에 명시한다.
3. **그룹 액션 경로 패밀리**: 계획의 `POST /projects/{pid}/review/groups/{group_id}/reject`는 기존 `/analysis/review-queue|review-inbox` 패밀리 밖의 새 최상위 `/review/`다. Slice 4 착수 시 `/analysis/...` 하위로 맞추는 것을 고려한다(계획이 "계열의"라 예시로 표기한 상태라 위반은 아님).
4. **슬라이스별 예상 operation 수**: Slice 4·5의 endpoint 추가로 100→101→102를 예고해 두면 전수 가드·tier 행렬 검산이 기계적이 된다(종전 페이즈 문서 관례).

## Verdict

**합격** — 채택된 C의 승인/거절 의미론·멱등·보존 경계가 7개 슬라이스에 완전·단방향으로 배정됐고 SoT v1.8.16과 모순이 없으며, 문서 인프라(인덱스·수 주장·가드·분량 기록)가 전부 green이다. 브리프 Follow-up 5건 중 2건(모순 상태·uncertain 사람 처리)이 미배정이나 정본 요구는 아니고 구조적으로 폐쇄되지 않았으므로 하드닝으로 남긴다.

## Outstanding items

- Slice 0(저장 모델과 수명) 착수가 다음 작업. 하드닝 1·2는 계획 증보 1커밋으로 반영 가능하다.
- 그룹 액션의 활동 로그 기록 여부는 Slice 4 착수 시 소결정 브리프로 남아 있다(계획 명시대로).

## Reproduction

```bash
git status --short        # clean
python3 -m pytest tests/test_docs_indexes.py -q   # 13 passed, 283 subtests
git diff --check          # 성공
# 브리프 Follow-up 대조: pending-candidate-identity-grouping-decisions.md §Follow-up 5행 ↔
# implementation-phases.md Slice 0·1·5·6·Deferred — 본 기록 대조표 참조
```
