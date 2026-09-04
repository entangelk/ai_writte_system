# 미승인 후보 정체성 그룹 — 구현 페이즈

상태: `Active — Slice 0~5 완료(Slice 5 검증 대기), Slice 6(grouped UI) 다음`
작성: 2026-09-02
결정 정본: [`pending-candidate-identity-grouping-decisions.md`](pending-candidate-identity-grouping-decisions.md) — **C 채택**
계약 정본: [`../system-contract-sot.md`](../system-contract-sot.md) v1.8.29

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

## Slice 1 — shortlist와 판정 서비스 · **완료(2026-09-03, SoT v1.8.21)**

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

**완료 기록(2026-09-03):** `analysis/identity_judging.py`(서비스·seam)·
`tests/test_identity_judging.py`(17셀)로 구현(커밋 `f5c0ead`·`98c5c13`·`3dfef65`,
SoT v1.8.21). 이 Slice에서 확정한 리터럴 — ① **판정 재사용은 "저장 판정 승리 +
효과 멱등 재적용"**(pair에 relation이 있으면 judge 재호출 없이 재사용하되 그룹
연결·모순 표시는 다시 일어나 죽은 실행의 빈자리를 스스로 메운다), ② **모순 감지는
도착 순서와 무결** — 새 `different`가 same 성분과 충돌할 때와 `same`이 different
삼각형을 닫을 때 모두 group을 `contradicted`로 올린다(`open`일 때만 — 정확히 한 번
전환), ③ **두 그룹을 잇는 same은 병합** — 오래된 그룹이 살아남고 흡수된 그룹은
`closed` 껍데기(member 행은 남지만 소속 판정에서 제외; Slice 3 읽기면은 open
그룹만 본다), ④ judge 미구성은 판정할 pair가 있을 때만 명시 오류(빈 shortlist는
no-op), ⑤ relation `source` 리터럴 `identity_judge`. OpenAPI/`schema.d.ts` 무변
(덤프 바이트 동일 실측). 뮤테이션 10종 기명 재실패 — 과정에서 병합 셀이 클록
동률로 **우연히 통과하던 결함**을 발견·보강(결정적 id 순서+클록 전진). 전수
**2719/1/3132**(+17셀). 실 provider 호출이 없으므로 LLM audit 행 수 검증은
Slice 2 배선 때 잰다(공통 작업 규칙의 provider 미구성·parse error 축은
`IdentityJudgeNotConfigured`·`InvalidIdentityJudgement`·judge 예외 전파로
서비스 레벨에서 잠갔다).

## Slice 2 — 분석 runner 배선 · **완료(2026-09-03, SoT v1.8.23)**

**범위:** 분석 candidate가 저장된 뒤 Slice 1 서비스를 호출해 identity relation/group을 생성한다.
Review Inbox 응답과 액션은 아직 바꾸지 않는다.

**규칙:** candidate 저장 실패나 job 실패에는 group 판정을 시도하지 않는다. group 판정 실패는 job 전체를
실패로 바꾸지 말고, candidate는 `needs_review`로 남긴다. LLM 호출 계측은 기존 `llm_call_scope` 관례를
따르며 `correlation_id=analysis_job_id`를 쓴다.

**검증:** runner 성공 경로에서 후보 저장 뒤 group 서비스 호출, 후보 0개/no shortlist no-op, group judge
ProviderError/parse error의 실패 격리, LLM audit row 수를 잠근다.

**완료 기록(2026-09-03):** `analysis/identity_judge.py`(gateway judge adapter)·`analysis/runner.py`
배선(`identity_judging` 선택 주입)·`LlmCallSite.IDENTITY_JUDGE`(8→9종)·`main.py` 조립
(`_default_analysis_runner` 확장 + `AnalysisService.repository` 읽기 전용 프로퍼티)로 구현
(커밋 `488b867`·`e6a4c87`·`fd02e88`, SoT v1.8.23). 이 Slice가 확정한 리터럴 —

- **판정은 성공 경로에서만** — 저장 실패·job 실패에는 시도조차 하지 않는다(셀: 후보 저장 실패 시
  judge 무호출).
- **판정은 `mark_job_succeeded` 뒤에 돈다** — job이 이미 종결이므로 판정 경로의 어떤 실패도 job
  상태를 되돌릴 수 없다(격리의 구조화. 셀 `test_judging_runs_after_the_job_reaches_success` —
  judge가 불릴 때 job이 SUCCEEDED여야 한다).
- **판정 실패는 전체 단위 격리 + 첫 실패로 단계 종료** — ProviderError·`InvalidIdentityJudgement`·
  judge 미구성 어느 것이 와도 job은 succeeded·후보는 `needs_review` 잔류. 세분화(후보별 격리)는
  죽은 게이트웨이에 남은 pair만큼 timeout을 태우므로 과잉으로 잡았다(뮤테이션 M4′). 부분 적용된
  단계는 Slice 1의 판정 재사용+자가 치유(B3 셀)로 회복된다. **세 축 전부 v1.8.24부터 기명 셀로
  잠긴다** — judge 미구성 축은 독립 검증 B1 폐쇄(2026-09-03, 셀
  `test_missing_judge_is_isolated_in_the_runner`; M2 격리 제거에 물리는 것 재실측).
- **focal은 이번 job에 기록된 후보만** — pool의 옛 후보는 비교 대상이 될 뿐 스스로 판정을 다니지
  않는다(셀: 옛 후보 2·신규 1에서 calls는 2쌍, 옛-옛 pair 무판정).
- **terminal parse 거부의 D4 재분류는 runner 격리 경계에서** — compare endpoint 선례를 이식한
  것으로, 판정 실패가 HTTP 오류로 올라오지 않아 endpoint가 그 예외를 볼 수 없기 때문이다.
  "마지막 호출이 곧 실패한 repair 호출"은 **기본 조립에서만 성립하는 가정이다**(시드를 조립점에서
  하므로 provider 호출 없이 그 예외가 날 경로가 없다) — 시드 안 템플릿의 손조립·smoke에서는
  재분류가 같은 scope의 관계 없는 마지막 행을 오염시킬 수 있다(독립 검증 H1 실증, compare 선례와
  같은 모양).

judge는 compare judge와 같은 모양이다(프롬프트 `analysis_identity_v1`·task_type `analysis_identity`·
strict parse·repair 1회·판정 축 세 값 전부 허용), 조립 env 게이팅은 `LLM_GATEWAY_BASE_URL`,
judge `max_tokens`는 `ANALYSIS_IDENTITY_JUDGE_MAX_TOKENS` 기본 **512**. OpenAPI/`schema.d.ts` 무변
(덤프 바이트 동일 384,414B·md5 `10978d55…` — 코드 기준선 `2d467b5`↔HEAD 대조, 독립 검증 §6에서 확정; 구현 세션의 첫 대조는 경계가 테스트 커밋 전후로 무효였다 — 검증 H3 정정). 감사 행 수: 판정 pair당 1행(`identity_judge`
site·`correlation_id`=job_id — run endpoint의 scope를 탄다)·repair는 둘째 행·terminal 거부는 마지막
행 `parse_error`·provider 실패는 자기 taxonomy 유지 — 전부 실 adapter+seam C 셀로 잠금.
셀 18종(신규 파일 16 + `test_llm_call_sites.py` 조립 가드·max_tokens 핀 2). 뮤테이션 11회 중 10종
기명 재실패(가드 제거 1종은 관측 동등 — 격리 경계가 AttributeError를 대신 삼키는 이중 보호).
전수 **2740/1/3133**(+18셀, 1952.43초).

**검증 조건 폐쇄(2026-09-03, SoT v1.8.24):** 독립 검증
[`verifications/2026-09-03/identity_group_slice_2.md`](../verifications/2026-09-03/identity_group_slice_2.md)
판정 **조건부 합격** — 구현 주장 전부(전수 산술·OpenAPI 경계 대조·셀·뮤테이션 재유도·기록) 재현됐고
검증자 신설 변이 2종(focal 확대·max_tokens 변조)도 구현 셀이 물렸다. 차단 **B1**(러너 레벨 judge 미구성
격리 무셀)은 셀 1개로 폐쇄(위 ③) — 전수 **2741/1/3134**(subtest 3134 = 검증 기록의 문서 가드 subTest
포함). 비차단 H1(재분류 가정 문구)·H3(측정 경계 정정)은 위에 반영했고 H2(HANDOFF 사이트 열거)는
HANDOFF에 반영했다. 판정 열은 승격하지 않는다(Slice 0·1 선례).

## Slice 3 — Review Inbox 읽기면 · **완료(2026-09-04, SoT v1.8.25)**

**범위:** Review Inbox API payload에 group metadata를 additive로 싣는다. 프론트 UI와 그룹 액션은 아직
만들지 않는다.

**계약:** 기존 개별 item 필드는 그대로 유지한다. 새 필드는 예를 들어 `group_id`, `group_size`,
`group_status`, `group_member_ids`, `identity_rationale_summary`처럼 목록 렌더에 필요한 최소값만 싣는다.
detail source refs와 conflict/edit 경계는 개별 후보 기준으로 유지한다. **읽기면의 정본은 open 그룹과
member 행이다** — relation 행의 `group_id`는 기록 시점 값이라 병합으로 흡수된(`closed`) 그룹을 계속
가리킬 수 있으므로(Slice 1 검증 비차단 #1, 2026-09-03) 표시 전용으로만 쓰고 소속 판단에 쓰지 않는다.
승격 시 relation.group_id 갱신 정책은 Slice 5에서 정한다.

**검증:** grouped 후보와 ungrouped 후보가 같은 목록에 섞여도 기존 후보 액션 affordance가 유지되는지,
project 격리, stale group member 정리, OpenAPI/`schema.d.ts` 재생성을 확인한다.

**완료 기록(2026-09-04):** `analysis/review_inbox.py`(`IdentityGroupSummary`·`_identity_summaries`·
서비스에 `CandidateIdentityGroupService` 주입)·`routers/analysis.py`(`_identity_group_payload`)·
`main.py`(조립)로 구현(커밋 `90cc4dd`, SoT v1.8.25). 새 키는 하나 — `identity_group`(list+detail 공통
빌더, ungrouped는 `null`)이고 내부 필드명은 위 계약의 열거 그대로다. 이 Slice가 확정한 리터럴 —

- **소속의 정본은 open(non-closed) 그룹과 member 행** — 판정면 `_group_of`와 같은 semantics로
  `contradicted`도 여전히 묶는다(상태값을 그대로 노출해 UI 경고 라벨의 재료로 쓴다). relation 행의
  `group_id`는 소속·근거 선택 어디에도 쓰지 않는다 — 셀 `test_rationale_ignores_relation_group_id_pointing_elsewhere`가
  잠근다.
- **roster는 멤버십 ∩ 검토함 population** — confirm/reject/edit로 검토함을 떠난 stale member는
  `group_member_ids`/`group_size`에 싣지 않는다. **가시 멤버 < 2인 그룹은 ungrouped로 읽는다.**
  저장 멤버십은 이 판단으로 불변(member `member_status` 수명 확정은 Slice 4·5).
- **`identity_rationale_summary`는 이 후보와 가시 roster를 잇는 `same` relation 중 최신**
  (`created_at` 순, **동률은 큰 pair id 승리** — 검증 H1 폐쇄로 방향 명문화)의 rationale을 200자 절단 —
  상한은 활동 로그 "짧은 값"(`ACTIVITY_VALUE_MAX_CHARS`)·장면 메모 목록
  미리보기(`SCENE_NOTE_PREVIEW_MAX_CHARS`)와 같은 값이다. same relation이 없으면 `null`(없는 사실을
  지어내지 않는다). **근거 relation의 양끝은 모두 가시 roster 안** — 상대가 이탈한 same relation은
  근거가 될 수 없다(검증 B1 폐쇄). relation `candidate_type`이 그룹 type과 다른 행도 근거가 될 수
  없다(검증 H3 — 저장 면이 이 행을 거부하지 않으므로 읽기면의 방어).

셀 13종(`tests/test_review_inbox_identity_groups.py` — create_app에 identity group 서비스를 주입해
시드). **OpenAPI/`schema.d.ts` 무변** — review-inbox 응답이 `dict[str, object]`로 선언돼 additive payload가
선언 schema에 나타나지 않는다(경계 `4ace6c4`↔작업 트리 덤프 바이트 동일, md5 `10978d55…`·384,414B —
Slice 2 검증이 확정한 지문. 프론트 생성물 재생성 불요). 변이 9종 기명 재실패(표는 work_log 세션 1).
전수 **2754/1/3134**(+13셀, 1804.50초).

**검증 조건 폐쇄(2026-09-04, SoT v1.8.26):** 독립 검증
[`verifications/2026-09-04/identity_group_slice_3.md`](../verifications/2026-09-04/identity_group_slice_3.md)
판정 **조건부 합격** — 구현 주장 전부(전수 산술·OpenAPI 경계 대조·셀 13·변이 재유도 5종·RED 선행)가
재현됐다. 차단 **B1**(가시 roster 밖 pair의 근거 차단 무셀 — 검증자 변이 VM1이 13 passed로 입증)은 셀
1개로 폐쇄(커밋 `0ff8d13`) — `test_rationale_ignores_relations_to_members_outside_the_roster`(trio에서
1명 reject 후 가시 2명 유지·근거 `null`). VM1 재실측 **2 failed**(B1 셀+edit 셀). 하드닝 4종도 같이
반영 — **H1** 동률 tie-break 방향(큰 pair id 승리)을 위 리터럴에 명문화+셀
`test_rationale_tie_breaks_by_the_larger_pair_id`(변이 MH1 반전에 2 failed) · **H2** stale 이탈 세 번째
원인 edit(원본 superseded) 셀 `test_edited_member_leaves_the_group_roster`(confirm·reject·edit 열거의
문서-셀 대응 완결) · **H3** 타 type relation의 근거 배제를 위 리터럴에 기재+셀
`test_rationale_ignores_relations_of_another_candidate_type`(변이 MH3에 1 failed) · **H4** 이중 non-closed
소속 시 "오래된 그룹 first"(결정성 방어, 셀 없음)를 명문화. 폐쇄 후 전수 **2758/1/3135**(2256.74초;
검산 2754+4셀, subtest +1 = 검증 기록의 문서 가드 subTest).

## Slice 4 — 그룹 거절 액션 · **완료(2026-09-04, SoT v1.8.27)**

**범위:** `POST /projects/{pid}/analysis/review-inbox/groups/{group_id}/reject` 계열의 그룹 거절만 추가한다.
기존 `/analysis/review-queue|review-inbox` 패밀리에 맞춘다. 그룹 승인은 아직 없다. 예상 operation 수는
직전 100에서 **101**이다.

**규칙:** owner만 실행한다. 같은 idempotency key 재전송은 이미 rejected인 후보를 다시 건드리지 않는다.
그룹 안의 후보 일부가 이미 terminal이면 나머지만 거절하되 응답에 skipped/changed 수를 싣는다.

**검증:** 전체 거절, 일부 terminal skip, 같은 key 재전송, 다른 key로 이미 rejected 재호출, project/group
404, 401/403, 활동 로그를 남길지 여부는 이 Slice 착수 시 짧은 결정 브리프로 확인한다.

**완료 기록(2026-09-04):** 착수 브리프
[`pending-candidate-identity-grouping-slice4-activity-log-decisions.md`](pending-candidate-identity-grouping-slice4-activity-log-decisions.md)
— **A 채택(그룹 행 1줄)**. `analysis/identity_group_review.py`(`CandidateIdentityGroupReviewService`·
`GroupRejectResult`)·`routers/analysis.py`(엔드포인트)·`main.py`(조립 — 신규 `create_app` 파라미터
없음, 이미 주입된 서비스들의 순수 조합)로 구현(커밋 `4b0d907`·셀 보강 `1b41177`, SoT v1.8.27).
operation 100→**101** 실측(tier 행렬 75/101), `schema.d.ts` 재생성(gen:api). 이 Slice가 확정한 리터럴 —

- **멤버 판정은 후보 상태 기계만 본다** — 저장 멤버십에서 `needs_review`만 거절하고 terminal
  (confirmed·rejected·superseded) 전 종류는 skip한다. 승격 여부(`is_candidate_promoted`)는 보지
  않는다(개별 reject와 같은 면 — 승격된 needs_review 후보도 거절되며 canonical은 append-only라
  그대로 남는다). 응답은 `{group_id, rejected[], skipped[], idempotent_replay}`이고 두 목록은 후보
  id 정렬이다(어댑터와 무관한 결정성 — 변이 M8이 무셀임을 발견해 고정 클록·역순 added_at 셀로 잠금).
- **멱등은 상태에서 유도한다**(요청 body 없음 — 개별 reject와 대칭) — 완료된 그룹의 재호출은
  skipped 전체·rejected 공백·`idempotent_replay=true`, 부수효과 재발 없음. "같은 key 재전송"과
  "다른 key 재호출"이 같은 관측으로 붕괴한다(명시적 key는 단계별 진행을 저장하는 Slice 5).
- **closed 그룹은 404**, `contradicted`는 거절된다(읽기면 정본과 같은 순서).
- **그룹·멤버 행은 바꾸지 않는다** — 이것이 이 Slice의 member 수명 결정이다: 멤버십은 append-only
  참조, 수명은 후보 상태로 표현, 가시성은 roster 교집합(Slice 3)이 정리한다. `member_status` 신규
  값 없음(Slice 0 "유일 literal `active`" 유지).
- **부분 실패(스토리지 503)는 전역 handler로 넘긴다**(개별 reject와 같은 모양) — 각 멤버 쓰기가
  독립적·멱등이라 재호출이 끝난 멤버를 skip하며 이어간다. 단계별 진행 저장은 Slice 5.
- **활동 로그는 그룹 행 1줄**(브리프 A안) — `identity_group_rejected`·target_type
  `candidate_identity_group`·`after`="rejected=N, skipped=M", **변경≥1일 때만**(일괄 승격
  `if promoted:` 선례). 멤버별 `candidate_rejected` 행은 남기지 않는다. 분류표 logged 27→**28**
  (검토 결정 10), 프론트 라벨 "정체성 그룹 거절"+비링크 사유 등재. 이 결정은 Slice 5 그룹
  승인의 기록 모양에도 묶는다. 이 슬라이스의 기록 배선은 전수 가드(존재)·활동 행 셀(모양)·변이
  M5/M6(조건·리터럴)이 잠근다.

셀 10종(`tests/test_identity_group_reject.py`)·뮤테이션 9종 중 8종 기명 재실패(1종 관측 동등 —
결과 기반 분류의 방어선; M2). 401/403은 기존 전수 행렬이 자동으로 잠근다(project tier 75/101
카운트만 갱신). 전수·프론트 수치는 work_log 2026-09-04 세션 4에 실측으로 남긴다.

**검증 조건 폐쇄(2026-09-04, SoT v1.8.28):** 독립 검증
[`verifications/2026-09-04/identity_group_slice_4.md`](../verifications/2026-09-04/identity_group_slice_4.md)
판정 **조건부 합격** — 구현 주장 전부(전수 산술·OpenAPI·등재 5곳·변이 재유도 8/9종·RED 산술·
프론트 결함 사전존재)가 재현됐다. 차단 2건은 같은 날 셀로 폐쇄(커밋 `c9b2e36`) —
**B1** superseded skip 무셀(검증자 변이 VM-A가 skip을 confirmed·rejected 두 값 열거로 좁혀도
10 passed; 그 좁힘 아래 superseded 멤버 포함 그룹은 `InvalidCandidateStateTransition`이 그룹
라우터 catch 밖으로 새어 배치 mid-flight로 죽는다 — 검증 실측) → 셀
`test_superseded_members_are_skipped_like_other_terminal_states`(probe P1 본체; VM-A 재실측
**1 failed**) · **B2** "승격 여부는 보지 않는다" 무셀(승격+needs_review 멤버의 거절·canonical
잔존을 잠그는 셀이 전 suite에 없었다 — 방어가 구조적일 뿐) → 셀
`test_promoted_members_are_still_rejected_and_canonical_survives`(probe P2 본체; 승격 스킵
드리프트 변이 — 서비스에 memory 주입+승격 멤버 skip — 재실측 **1 failed**). 비차단 하드닝 —
**H1** mid-loop 스토리지 실패→503·재호출 이어가기 셀(리터럴 ⑤가 skip 셀·개별 멱등 셀에서
유도적으로만 성립)은 **Slice 5에 이관**한다(단계별 진행 저장 스펙이 근접 — 아래 Slice 5 참조) ·
**H2** 셀 10의 RED 우연 통과(라우트 부재 시 before==after)를 셀 docstring에 표시. 폐쇄 후
전수 수치는 work_log 2026-09-04 세션 5에 실측으로 남긴다.

## Slice 5 — 그룹 승인 액션 · **완료(2026-09-04, SoT v1.8.29)**

**범위:** C 채택의 핵심인 그룹 승인 orchestration을 만든다. UI는 아직 없다.
예상 operation 수는 Slice 4 완료 후 101에서 **102**다.

**규칙:** 그룹의 첫 eligible 후보를 canonical로 승격한다. 이후 후보는 같은 canonical을 대상으로 기존
compare/apply 경로를 써서 `update|add_evidence|no_change|conflict`로 처리한다. 각 member step은
`pending|applied|conflict|failed|skipped` 상태와 결과 memory/version id를 저장한다. 재시도는 `applied`
step을 재실행하지 않는다.

**검증:** 첫 후보 승격, 둘째 후보 update/add_evidence/no_change/conflict 4분기, 중간 실패 뒤 재시도,
같은 key replay, 그룹 revision mismatch 409, canonical 중복 생성 방지를 잠근다. 이 Slice는 가장 위험하므로
focused 뒤 analysis compare/apply broader suite를 함께 돌린다.

**이관(Slice 4 검증 H1, 2026-09-04):** mid-loop 스토리지 실패→503·재호출 이어가기 셀을 여기서
함께 만든다 — Slice 4 리터럴 ⑤("재호출이 끝난 멤버를 skip하며 이어간다")가 skip 셀·개별 멱등
셀에서 유도적으로만 성립해서다(그룹 루프를 관통하는 발화 셀 없음 — 검증 기록 §H1). 단계별 진행
저장 스펙이 근접하므로 이 슬라이스의 자연스러운 일부다.
**완료 기록(2026-09-04):** 착수 브리프
[`pending-candidate-identity-grouping-slice5-approval-orchestration-decisions.md`](pending-candidate-identity-grouping-slice5-approval-orchestration-decisions.md)
— 오너가 **D1=A·D2=A·D3=A·D4=A**로 확정. 구현은 `analysis/identity_group_approvals.py`(진행
저장: 도메인·in-memory·서비스)·`analysis/identity_group_approvals_mongo.py`
(`candidate_identity_group_approvals`, 그룹당 1문서·steps 내장)·`identity_group_review.py`
의 `approve_group`·`AnalysisCompareService.judge_against`(강제 대상 판정)+`has_judge`·
`MemoryService.memory_for_candidate`(채택 규칙)·라우터 엔드포인트·조립(커밋 `ffc9525`·
셀 보강 `871b634`·유료 등재 `ea55474`). 이 Slice가 확정한 리터럴 —

- **revision이 멱등 key를 겸한다**(D1=A) — body `{"expected_revision": N}`. 불일치 409
  (detail에 현재 revision), 같은 revision 재전송은 진행 문서와 붕괴해 replay/이어가기.
- **canonical은 그룹이 정한다** — 나머지 멤버는 scope matcher를 다시 돌리지 않고 그룹
  canonical을 강제 대상으로 판정한다(create 폴스루 봉쇄). 멤버 중 승격 memory가 있으면
  (개별 승격·저장 상실 패스 재구성 모두) added_at 최순의 CANONICAL을 **채택**한다 —
  채택이 없으면 seed가 두 번째 canonical을 mint한다(설계 중 발견, 셀 2종이 잠금).
- **step마다 진행을 저장한다** — pending|applied|conflict|failed|skipped + memory/version
  id. 재시도는 applied를 재실행하지 않는다. **Slice 4 검증 H1 이관 셀**(mid-loop
  스토리지 503 → 재호출이 seed canonical을 채택해 이어간다)을 이 슬라이스에 포함.
- **applied 멤버는 confirm의 부수효과 세트로 닫는다**(D2=A) — confirmed 전이 + de-index +
  대기열 resolve. conflict 멤버는 needs_review 잔류 + 대기열 적재. 버전 적용 뒤 canonical
  포인터는 최신으로 이동한다.
- **첫 판정 실패에 step=failed·패스 종료**(D4=A) — 응답은 200에 step 상태. terminal parse
  거부의 감사 재분류는 endpoint 경계(compare·Slice 2 선례).
- **그룹·멤버·relation 행 불변**(D3=A) — relation.group_id는 영구 표시 전용(Slice 3 유예
  확정).
- **judge 미구성은 남은 멤버가 있을 때만 시작 전 503**(eligible==1이면 무판정 통과).
- **활동 로그는 A안 묶임** — 그룹 행 1줄 `identity_group_approved`·변경≥1(분류표
  logged 29·검토 결정 11).
- **유료 10번째 경로**(8.0 B4/B6) — 1차 전수가 미등재를 물어 전환: fan-out 표시·
  `_REQUIRE_PROJECT_OWNER_BILLABLE`(402/429)·SERVER dedupe 키(재개 재호출은 진짜
  재실행 — analysis_compare와 같은 모양)·관측 COVERAGE 등재.

셀 33종(승인 28 + Mongo 어댑터 4 fake+1 live — Slice 4 B1 교훈의 superseded 멤버를
terminal-skip 셀에 선제 포함)·뮤테이션 12종 전부 기명 재실패(표는 work_log 세션 7).
파기 그래프 11계약/23컬렉션·tier 76/102·오류 선언 23행(+409/+402/429)·`truncate_to_ms`
공개 승격. OpenAPI/`schema.d.ts` 재생성(+128줄). 전수 **2803/1/3189**(2396.68초; 1차
3 failed = 유료 등재 2(수리) + quota 타이밍 1(flake — 단독·2차 모두 통과)). RED는 별도
관측 못 함(구현 뒤 첫 실행) — 뮤테이션이 방향성을 대신 잠금.


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
`contradicted` group을 사람이 해소해야 하는 첫 사례가 생길 때 별도 Slice로 연다. **shortlist 상한·페이징**도
유예다(Slice 1 검증 비차단 #3, 2026-09-03) — 같은 이름 후보가 수백 개면 판정 재사용의 성분 확인(BFS)이
O(pool×relations)로 커지는데 dogfood 규모에서 문제된 징후가 없으므로, **트리거: Review Inbox의 그룹 수가
세 자리로 관측될 때** 상한·페이징을 논의한다.
