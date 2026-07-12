# Phase 6. Review UI

상태: `Draft`  
선행 조건: Phase 2 후보/상태 전이, Phase 5 editor 연동  
후속 가치: Project Memory Console, Gate review 운영

## 목표

AI가 만든 구조화 기억과 Gate finding을 사용자가 이해하고 승인·거절·수정할 수 있게 한다.

## MVP 범위

- 분석 candidate/needs_review 목록
- source quote와 원문 위치 확인
- 기존 기억과 신규 분석값의 diff 및 변경 작업 후보 확인
- `confirmed` 승격과 `rejected` 처리
- 미회수 foreshadowing 목록
- 인물, 장소, 사건 기본 카드
- Gate finding 확인 및 관련 후보/원문 이동

후속 범위:

- 관계 graph visualization
- 완전한 사건 timeline 편집기
- bulk review와 복잡한 merge
- style/voice 관리 콘솔
- 자동 canon 승격

## 핵심 사용자 흐름

```text
review inbox → 후보와 근거 확인
→ create/update/add_evidence/conflict 근거 비교
→ approve / reject / edit / defer
→ 상태 전이와 사용자 기록 저장
→ 영향받은 검색 문서 재색인
```

## 화면 단위

1. Review Inbox: 유형, risk, confidence, 생성 job 기준 필터
2. Candidate Detail: 작업 후보, 새 값, source quote, 기존 기억/version과 diff
3. Memory List/Card: 인물, 장소, 사건, 떡밥 상태
4. Gate Findings: 위반 문장, 근거 constraint, 권장 action

## 산출물

1. review request/result와 상태 전이 계약
2. 후보 목록/상세 API
3. 승인·거절·수정 action
4. update/add_evidence/conflict와 merge/split proposal 검토
5. source location deep link
6. memory card와 unresolved foreshadowing view
7. 상태 변경 후 index sync 연결

## 수용 기준

- 사용자가 후보의 원문 근거와 기존 기억 차이를 확인할 수 있다.
- update 승인 시 이전 기억 version과 근거가 보존된다.
- approve/reject/edit가 권한과 상태 전이 규칙을 따른다.
- 같은 review action 재시도로 중복 전이나 sync가 생기지 않는다.
- 승인 전 candidate가 canonical UI와 검색 constraint로 위장되지 않는다.
- 상태 변경 후 MongoDB가 먼저 갱신되고 인덱스는 그 결과를 따른다.
- 다른 프로젝트의 후보나 기억은 목록·상세·deep link에서 노출되지 않는다.

## 착수 전 결정사항

- [x] 사용자가 승인하면 `confirmed`인지 `canonical`인지 — **v1.6.61 확정**(브리프 `06-candidate-state-transition-decisions.md`, D1=분리 모델: 둘 다 — candidate는 `confirmed`, canonical `MemoryEntry`로 promotion). 백엔드 상태 전이만 구현; 아래 UI/merge/split은 계속 미확정.
- [ ] 후보 수정이 원 후보의 새 version인지 별도 사용자 기억인지
- [ ] entity merge/split을 MVP UI에 포함할지
- [ ] create/update/add_evidence/conflict별 승인 UI와 권한
- [x] Gate finding과 Analysis candidate를 하나의 inbox에 합칠지 — **v1.6.64 결정**: 현재 영속 surface인 Analysis candidate+open conflict를 먼저 통합. Gate finding store가 생기면 origin literal로 additive 확장.
- [x] source deep link에 필요한 editor route/selection 계약 — **v1.6.64 결정**: frontend route는 보류하고 source_ref 정본 pointer(snapshot/block/offset/hash/quote)만 백엔드가 제공.
- [ ] 상태 변경이 영향받는 기억과 인덱스를 어디까지 invalidate할지

## 원문 및 상세 참고

- [`../abstract.md`](../abstract.md) §15.4, §17 Phase 6
- [`../analysis_pipeline.md`](../analysis_pipeline.md) §19, §29, §32
- [`../mongo_collections.md`](../mongo_collections.md) §41~42
- [`../contracts.md`](../contracts.md) §10
