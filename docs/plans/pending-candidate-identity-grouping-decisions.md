# 미승인 후보 정체성 그룹 착수 결정 브리프

**상태**: 확정 — C 채택 (2026-09-02 dogfood)
**정본**: `docs/system-contract-sot.md`  
**선행**: 2A candidate 멱등 저장 · 2B canonical compare · 2B.6/2B.7 의미/별칭 탐지 · Phase 6 Review Inbox

## Decision needed

서로 다른 분석 job이 만든 `needs_review` 후보가 같은 인물·사건을 가리키는 경우,
이를 화면에서만 묶을지 아니면 승인 결과까지 하나의 정체성 그룹으로 처리할지 결정해야
한다. 현재 compare는 승인된 canonical memory만 대조하므로 후보↔후보 중복을 방지하지
못하며, 단순 UI 그룹만으로는 그룹 전체를 승인했을 때 canonical 중복이 그대로 남는다.

## Options table

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 결정적 key로 화면에서만 그룹 | character는 정규화 name, event는 exact fingerprint가 같은 후보를 목록에서 묶는다. 승인·거절은 개별 그대로다. | 구현이 가장 작고 LLM 비용이 없다 | 별칭·의미적 동일 사건을 놓친다 · 모두 승인하면 canonical 중복이 남는다 |
| B. 동일성 판정을 저장하되 액션은 개별 유지 | 새 후보 생성 뒤 같은 project/type의 미승인 후보를 shortlist하고 `same\|different\|uncertain` 판정·근거를 저장해 같은 목록에 묶는다. | 원 후보·근거를 손실 없이 보존한다 · 판정을 재사용한다 | 개별 승인으로 canonical 중복을 완전히 막지 못한다 |
| **C. 영속 identity group + 그룹 승인/거절 (권장)** | B의 판정을 영속화하고 `same`을 하나의 review group으로 보여 준다. 그룹 승인은 첫 후보를 canonical로 승격한 뒤 나머지를 순서대로 기존 compare judge에 넣어 update/add-evidence/no-change/conflict로 적용한다. 그룹 거절은 전체를 거절한다. | 승인 전 묶음과 승인 후 canonical 중복 방지를 모두 닫는다 · 각 후보의 source ref를 보존한다 · 현재 versioned upsert/judge를 재사용한다 | 그룹 액션의 원자성·부분 실패·충돌 후 재개 계약이 필요하다 · 판정/judge 호출 비용이 늘어난다 |
| D. 승인 전 물리적 후보 병합 | `same`으로 판정한 후보를 하나의 candidate document로 합쳐 payload/source refs를 재작성한다. | 검토함에 항목이 가장 적게 보인다 | AI 판정 오류가 원 후보 경계를 없앤다 · payload 합성 규칙이 필요하다 · append-only 감사/출처 추적이 복잡해진다 |

## Recommendation + reason

**C를 채택한다.** dogfood의 핵심 문제는 목록이 반복되어 보이는 것뿐 아니라, 같은 대상을
승인했을 때 canonical memory가 여러 개 되는 것이다. B는 사람이 중복을 인지하게는 하지만
오류를 막지 못한다. C는 candidate를 물리적으로 합치지 않아 원문 근거를 보존하면서,
이미 검증된 canonical compare·versioned upsert 경로로 중복 승인을 수렴시킨다. 현재의
"자동 병합 금지, AI는 탐지·사람이 승인" 정책과도 맞는다.

## Follow-up considerations

- shortlist는 project/type 격리 후 character 결정적 name/alias 신호와 event/open-question vector 검색을 사용하고, 최종 `same|different|uncertain`은 전용 judge가 근거와 함께 낸다.
- pair별 verdict만 쌓으면 추이성 모순(A=B, B=C, A≠C)이 생길 수 있으므로 group revision과 모순 상태를 둔다.
- 그룹 승인은 멱등 key와 단계별 처리 현황을 저장해 재시도가 이전 성공을 중복 적용하지 않게 한다.
- `uncertain`은 자동으로 묶지 않고 “같은 대상일 수 있음” 관계만 표시해 사람이 합치기/분리하게 한다.
- character 같은 인물의 서로 다른 observation은 “중복 문장”이 아니라 “같은 identity의 추가 근거”로 다룬다.

## Deferred / out of scope

- canonical memory 간 기존 중복의 일괄 backfill/merge
- threshold 실데이터 캘리브레이션과 자동 production 값 설정
- project 간 정체성 공유, 사용자 공동 검토, bulk group 처리
- 동일성 판정을 근거로 canonical 승인을 사람 확인 없이 실행하는 자동 병합
