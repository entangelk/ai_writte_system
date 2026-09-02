# 미승인 후보 정체성 그룹 — 구현 페이즈

상태: `Active — Slice 0부터 진행`
작성: 2026-09-02
결정 정본: [`pending-candidate-identity-grouping-decisions.md`](pending-candidate-identity-grouping-decisions.md) — **C 채택**
계약 정본: [`../system-contract-sot.md`](../system-contract-sot.md) v1.8.16

## 목적과 완료 기준

서로 다른 분석 job이 만든 `needs_review` 후보가 같은 인물·사건·질문을 가리키는 경우,
검토함은 이를 하나의 검토 그룹으로 보여 주고, 사용자는 그룹 단위로 승인·거절할 수 있어야 한다.
원 후보 문서와 source ref는 물리적으로 합치지 않는다. 그룹 승인은 첫 후보를 canonical memory로
승격한 뒤, 나머지 후보를 기존 canonical compare/judge 경로로 `update|add_evidence|no_change|conflict`
에 수렴시킨다.

완료는 다음이 동시에 참일 때다.

1. 같은 project 안의 미승인 후보는 persistent identity group/revision에 연결된다.
2. shortlist+judge 결과가 `same|different|uncertain`과 근거로 저장되고, 재실행해도 같은 판정을 중복 생성하지 않는다.
3. Review Inbox API가 개별 후보와 그룹 항목을 함께 노출하되, 기존 개별 후보 소비자를 깨지 않는다.
4. 그룹 거절은 전체 후보를 한 번만 rejected로 만들고 재시도해도 멱등이다.
5. 그룹 승인은 단계별 처리 현황을 저장해 재시도 시 이미 승격·적용된 후보를 중복 처리하지 않는다.
6. grouped Inbox UI에서 같은 그룹 후보를 접고 펼치며, 그룹 승인/거절 실패·부분 실패를 사람이 이해할 수 있다.

## Slice 0 — 저장 모델과 수명 · **완료(2026-09-02, SoT v1.8.17)**

**범위:** identity group 저장소만 만든다. HTTP, runner 배선, LLM judge, Review Inbox UI는 만들지 않는다.

**계약:** 새 저장 단위는 최소 세 종류다.

- `candidate_identity_groups`: `{group_id, project_id, candidate_type, status, created_at, updated_at, revision}`
- `candidate_identity_group_members`: `{group_id, candidate_id, project_id, candidate_type, member_status, added_at}`
- `candidate_identity_relations`: `{project_id, left_candidate_id, right_candidate_id, verdict, rationale, source, group_id, created_at}`

`project_id`와 `candidate_type`은 모든 unique/index 축에 포함한다. group member는 원 후보를 소유하지 않고
참조만 한다. group `status`는 최소 `open|contradicted|closed`를 담는다. `contradicted`는 같은 group
안에서 `same` 추이와 상충하는 `different` relation이 관측된 상태이며, 이 Slice는 상태를 저장할 자리만
만들고 자동 분할·자동 병합은 하지 않는다. candidate purge/project purge는 그룹·멤버·관계 고아를 남기지
않는다.

**검증:** in-memory와 Mongo round-trip, project/type 격리, 중복 member idempotency, relation pair 정규화
(`A,B`와 `B,A` 동일), `contradicted` 상태 round-trip, project purge 정리를 잠근다. 이 Slice는 OpenAPI와
`schema.d.ts`를 바꾸지 않는다.

**완료 후 인계:** 다음 Slice는 저장소 public service만 사용한다. Mongo collection을 직접 읽어 그룹을
조립하지 않는다.

**완료 기록(2026-09-02):** `analysis/identity_groups.py`(도메인·서비스·in-memory)·
`analysis/identity_groups_mongo.py`(3컬렉션 어댑터)로 구현. 아래 계약 리터럴을 이 Slice에서
확정했다 — ① relation 스키마에 `candidate_type` 포함(위 "모든 unique/index 축" 문장과 필드
목록의 충돌을 오너 결정으로 상위집합 쪽으로 해소), ② Slice 0 유일 `member_status`=`active`,
③ 그룹 `revision`은 0에서 시작해 상태 변경마다 +1, ④ relation 재기록은 upsert(마지막 판정
승리)하되 `created_at`은 첫 판정 유지 — 판정 재사용 정책 자체는 Slice 1, ⑤ **클록 해상도는
BSON ms**(서비스 클록 절단)이고 Mongo 읽기는 naive datetime을 UTC로 재라벨링한다 — 실몽고
왕복은 데이터클래스 동등성으로 잠근다(검증 B1 폐쇄, SoT v1.8.18). "candidate purge"
경로는 현재 코드에 없다(후보 문서 hard delete는 project purge뿐)므로 `purge_project` 한 벌로
고아 없음 계약이 닫힌다. 파기 그래프는 10계약/22컬렉션이 됐고 소유자·admin purge 양 경로
스파이가 호출을 잠근다. 독립 검증(`verifications/2026-09-02/identity_group_slice_0.md`)은
조건부 합격이었고 B1·H1~H4는 같은 날 폐쇄했다.

## Slice 1 — shortlist와 판정 서비스

**범위:** 후보 하나를 기준으로 같은 project/type의 `needs_review` 후보를 shortlist하고,
주입된 identity judge seam으로 `same|different|uncertain` relation을 저장한다. runner나 HTTP에는 아직
붙이지 않는다.

**규칙:** character는 normalized name/alias 신호를 우선 shortlist한다. event/open-question은 기존
candidate text derivation과 vector/lexical retriever가 있으면 그것을 쓰되, adapter가 없으면 empty
shortlist로 fail-closed가 아니라 no-op 처리한다. `same`만 group member로 연결하고, `uncertain`은 relation만
남긴다. 새 `different` relation이 기존 `same` 연결 성분과 충돌하면 relation은 보존하고 group status를
`contradicted`로 올린다.

**검증:** 같은 project/type만 후보가 되고, 같은 job 자기 후보도 비교 대상이 될 수 있으나 같은
candidate id는 제외한다. judge 미구성은 서비스 레벨에서 명시 오류로 드러내되, Slice 2 전까지 runner에는
배선하지 않는다. fake judge로 `same`→member 연결, `different`/`uncertain`→member 미연결, 같은 pair
재실행 멱등, A=B·B=C·A≠C 추이성 모순이 group `contradicted`로 남는 것을 잠근다.

## Slice 2 — 분석 runner 배선

**범위:** 분석 candidate가 저장된 뒤 Slice 1 서비스를 호출해 identity relation/group을 생성한다.
Review Inbox 응답과 액션은 아직 바꾸지 않는다.

**규칙:** candidate 저장 실패나 job 실패에는 group 판정을 시도하지 않는다. group 판정 실패는 job 전체를
실패로 바꾸지 말고, candidate는 `needs_review`로 남긴다. LLM 호출 계측은 기존 `llm_call_scope` 관례를
따르며 `correlation_id=analysis_job_id`를 쓴다.

**검증:** runner 성공 경로에서 후보 저장 뒤 group 서비스 호출, 후보 0개/no shortlist no-op, group judge
ProviderError/parse error의 실패 격리, LLM audit row 수를 잠근다.

## Slice 3 — Review Inbox 읽기면

**범위:** Review Inbox API payload에 group metadata를 additive로 싣는다. 프론트 UI와 그룹 액션은 아직
만들지 않는다.

**계약:** 기존 개별 item 필드는 그대로 유지한다. 새 필드는 예를 들어 `group_id`, `group_size`,
`group_status`, `group_member_ids`, `identity_rationale_summary`처럼 목록 렌더에 필요한 최소값만 싣는다.
detail source refs와 conflict/edit 경계는 개별 후보 기준으로 유지한다.

**검증:** grouped 후보와 ungrouped 후보가 같은 목록에 섞여도 기존 후보 액션 affordance가 유지되는지,
project 격리, stale group member 정리, OpenAPI/`schema.d.ts` 재생성을 확인한다.

## Slice 4 — 그룹 거절 액션

**범위:** `POST /projects/{pid}/analysis/review-inbox/groups/{group_id}/reject` 계열의 그룹 거절만 추가한다.
기존 `/analysis/review-queue|review-inbox` 패밀리에 맞춘다. 그룹 승인은 아직 없다. 예상 operation 수는
직전 100에서 **101**이다.

**규칙:** owner만 실행한다. 같은 idempotency key 재전송은 이미 rejected인 후보를 다시 건드리지 않는다.
그룹 안의 후보 일부가 이미 terminal이면 나머지만 거절하되 응답에 skipped/changed 수를 싣는다.

**검증:** 전체 거절, 일부 terminal skip, 같은 key 재전송, 다른 key로 이미 rejected 재호출, project/group
404, 401/403, 활동 로그를 남길지 여부는 이 Slice 착수 시 짧은 결정 브리프로 확인한다.

## Slice 5 — 그룹 승인 액션

**범위:** C 채택의 핵심인 그룹 승인 orchestration을 만든다. UI는 아직 없다.
예상 operation 수는 Slice 4 완료 후 101에서 **102**다.

**규칙:** 그룹의 첫 eligible 후보를 canonical로 승격한다. 이후 후보는 같은 canonical을 대상으로 기존
compare/apply 경로를 써서 `update|add_evidence|no_change|conflict`로 처리한다. 각 member step은
`pending|applied|conflict|failed|skipped` 상태와 결과 memory/version id를 저장한다. 재시도는 `applied`
step을 재실행하지 않는다.

**검증:** 첫 후보 승격, 둘째 후보 update/add_evidence/no_change/conflict 4분기, 중간 실패 뒤 재시도,
같은 key replay, 그룹 revision mismatch 409, canonical 중복 생성 방지를 잠근다. 이 Slice는 가장 위험하므로
focused 뒤 analysis compare/apply broader suite를 함께 돌린다.

## Slice 6 — grouped Inbox UI

**범위:** Review Inbox 화면에서 grouped item을 접고 펼치며, 그룹 승인/거절 버튼을 제공한다. 개별 후보
detail과 edit/conflict 화면은 유지한다. `uncertain` relation은 "같은 대상일 수 있음"으로 표시하되,
수동 합치기/분리 확정 액션은 아래 Deferred의 트리거 전까지 열지 않는다.

**규칙:** 목록 첫 화면에서 실제 후보 payload가 보이게 한다. 그룹 안 후보는 source/job 단위 차이를
확인할 수 있어야 한다. 부분 실패와 conflict는 성공처럼 닫지 않고, 남은 조치가 보이는 상태로 남긴다.

**검증:** grouped/ungrouped 혼합 렌더, expand/collapse, group reject/approve 요청 body와 idempotency key,
partial failure 표시, 기존 개별 approve/reject affordance 유지, 모바일 폭에서 버튼/텍스트 겹침 없음.

## 공통 작업 규칙

- 각 Slice는 **테스트 먼저 → 최소 구현 → focused test → relevant broader suite → checkpoint commit → mutation
  → 복원** 순서다.
- 계약을 바꾸는 Slice 0·3·4·5는 `docs/system-contract-sot.md`, OpenAPI 생성물, `docs/daily_logs/`,
  `HANDOFF.md`를 같은 커밋 계열에서 갱신한다.
- LLM judge를 도입하는 Slice 1·2·5는 provider 미구성, parse error, ProviderError, audit row 수를
  명시적으로 검증한다.
- 멱등 액션은 같은 key replay뿐 아니라 "다른 key로 이미 끝난 group을 다시 누르는" 과잉 방향도 잠근다.
- Slice 진행 중 원자성·부분 실패·활동 로그처럼 C 브리프가 열어 둔 계약 리터럴이 코드에서 유도되지 않으면
  구현을 멈추고 해당 Slice 전용 짧은 결정 브리프를 작성한다.

## Deferred

canonical memory 간 기존 중복 backfill/merge, threshold 운영 캘리브레이션, project 간 identity 공유,
bulk group 처리, 사람이 확인하지 않는 자동 병합, candidate document 물리 병합은 이 페이즈 밖이다.
`uncertain` relation의 수동 합치기/분리 확정 액션은 dogfood에서 uncertain 표시가 실제 검토를 막거나,
`contradicted` group을 사람이 해소해야 하는 첫 사례가 생길 때 별도 Slice로 연다.
