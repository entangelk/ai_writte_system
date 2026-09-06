# identity group Slice 5(그룹 승인 오케스트레이션)— 독립 검증

## Subject metadata

- 검증일: 2026-09-06
- 요청자: 오너 — "다음 작업 검증해줄래? … Slice 5 독립 검증이 있을 꺼야. 그거 검증해줘. 지금 보강하고있으니까 서로 커밋 섞이지 않게 조심해서해줘."
- 검증자: 이 세션(구현 세션 7·2026-09-04와 다른 세션). 구현자 보고(work_log 세션 7·SoT v1.8.29 행·커밋 메시지)는 전부 가설로 취급해 원본에서 재유도했다.
- 대상: 커밋 3건 — `ffc9525`(구현+셀 28+브리프+등재)·`871b634`(terminal-skip 셀 superseded 선제 보강)·`ea55474`(유료 등재 6곳) + 기록 `fad29c5`. 기준점 = Slice 4 검증 발행 `a71c942`(그 사이 `c9b2e36`·`6fdb8f1`은 Slice 4 폐쇄).
- 정규 계약: [`pending-candidate-identity-grouping-slice5-approval-orchestration-decisions.md`](../../plans/pending-candidate-identity-grouping-slice5-approval-orchestration-decisions.md)(확정 D1=A·D2=A·D3=A·D4=A, 오너 2026-09-04) · [`system-contract-sot.md`](../../system-contract-sot.md) **v1.8.29 행**(리터럴 ①~⑨) · 페이즈 문서 §Slice 5(완료 기록).
- **동시 작업 컨텍스트**: 검증 중 Phase S-0 보강 세션(다른 작업 AI)이 같은 트리에서 활동했다(커밋 `7e7df39`·`a6fcd61`, 그 사이 work_log·HANDOFF·브리프·검증 인덱스 미커밋 편집 존재). 뮤테이션은 verification.md의 **dirty-tree 분기**(cp 백업 → Edit → 역편집 → `cmp` 바이트 비교)로 수행했고 그들의 파일은 무변·무커밋.

## Scope

1. 경계 행렬 — SoT v1.8.29 리터럴 ①~⑨ + 페이즈 §Slice 5 규칙/검증 문장을 should/should-NOT/리터럴로 전개해 33셀 대응표 작성. ★ 최우선 의심축: **리터럴 ⑦(judge 미구성 503의 경계)과 리터럴 ⑥ D3=A(행 불변)의 잠금 여부**.
2. 구현 코드 감사 — `identity_group_review.py`(`approve_group`)·`identity_group_approvals.py`·`identity_group_approvals_mongo.py`·`routers/analysis.py` 엔드포인트·`compare.py`의 `judge_against`/`has_judge`·`candidate_review.confirm`/`memory.promote_candidate` 멱등·유료 등재(`billable_actions`·`dedupe`)·파기 그래프.
3. 테스트 코드 감사 — `tests/test_identity_group_approve.py` 28셀 + `tests/test_identity_group_approvals_mongo.py` 5셀(4 fake + 1 live).
4. 뮤테이션 — 구현자 표 12종 중 2종 재유도(정확한 diff 기록) + 검증자 신규(probe 3종·처방 선적용 변이 1종).
5. 등재 표면 — OpenAPI 독립 재덤프·`schema.d.ts` 재생성 바이트 대조·분류표 logged 수·`BILLABLE_ACTIONS`·오류선언 EXPECTED·프론트 라벨·plans 인덱스·파기 커버리지.
6. 집중·인접·전수 재실행.

## Methodology

환경(측정의 일부): WSL2 `DESKTOP-27QM1FP` · test-mongo(`127.0.0.1:27020`, rs-test) healthy · mypy 2.3.1 설치.

- 트리 게이트: 검증 개시 시 트리는 **보강 세션의 미커밋 docs 편집으로 dirty** — verification.md §Mutation의 "dirty and must not commit" 분기(cp 백업 + 역편집 + `cmp`)를 전 변이에 적용. 매 변이 후 `cmp` 바이트 동일 + `git status`가 보강 세션의 파일만 보이는지 확인.
- 집중: `python3 -m pytest -q tests/test_identity_group_approve.py tests/test_identity_group_approvals_mongo.py` → **33 passed**.
- probe(트리 무변경 — test 모듈 헬퍼 import): P1 리터럴 ⑦ 경계 3시나리오 · P2 승인 후 행 불변 실측 + 멤버행 삭제의 관측 불가능성 · P3 채택 원천 멤버의 seed 분기(judge 설정 시).
- 변이(전부 `identity_group_review.py`, 복원 즉시 + 바이트 검증):
  - VM-1 = 구현자 M2 재유도 — `if expected_revision != group.revision:` → `if False and …`(409 제거).
  - VM-2 = 구현자 M7의 **넓은 버전** — 채택 호출 `canonical = self._adopt_member_canonical(…)` 전체를 `canonical = None`으로(채택 규칙 제거).
  - VM-3 = **처방 선적용** — `to_judge`의 seed 면제에 `canonical.source_candidate_id in runnable` 조건 추가(4줄).
- OpenAPI: `python3 scripts/dump_openapi.py` 독립 덤프 + `openapi-typescript 7.13.0` 재생성 → 커밋본과 `diff`.
- 인접: compare 3모듈·billable·거절·llm_call_sites·quota_enforcement_api → **146 passed**.
- 전수: `python3 -m pytest -q`(백그라운드. 개시 HEAD `7e7df39` + 보강 세션 docs 3파일 dirty — 하단 마커).

## Findings

### 1. 경계 행렬 — 두 빈칸(B1·B2), 나머지 전부 대응

| 계약 분기/리터럴(SoT v1.8.29) | 셀 |
|---|---|
| ① revision 불일치 409(detail에 현재 revision) | `test_a_revision_mismatch_is_409_with_the_current_revision_in_detail` |
| ① 같은 revision 재전송 replay(무변경·judge 재호출 없음·행 무증가) | `test_a_completed_approval_replay_is_a_full_noop` |
| ② seed 승격(confirm 경로·create·v1·confirmed) | `test_first_eligible_member_becomes_the_canonical_seed` |
| ② update/add_evidence/no_change/conflict 4분기 | 셀 4종(update supersedes·증거 합집합·무쓰기·needs_review 잔류+대기열) |
| ② 판정 대상=그룹 canonical(scope matcher·create 폴스루 봉쇄) | `test_the_judge_target_is_always_the_group_canonical` |
| ② 채택 규칙(개별 승격 중복 방지) | `test_an_individually_promoted_member_is_adopted_not_duplicated` + 저장복구 셀(VM-2로 3셀 재실패 확인) |
| ③ step 저장·재시도 applied 재실행 금지 | `test_a_retry_resumes_without_reexecuting_applied_steps` + 저장소 round-trip 2셀 + Mongo 5셀 |
| ③ mid-loop 스토리지 503→재호출 이어가기(**Slice 4 H1 이관**) | `test_storage_failure_midway_answers_503_and_the_retry_resumes` |
| ④ D2=A 부수효과(de-index + 대기열 resolve) | `test_an_applied_member_leaves_the_index_and_resolves_its_queue` |
| ⑤ 판정 실패 step=failed·패스 종료·200 | `test_a_judge_failure_marks_the_step_failed_and_ends_the_pass` |
| ⑤ parse 거부 재분류(endpoint 경계) | `test_a_terminal_parse_rejection_is_reclassified_and_fails_the_step` |
| ⑥ 행 불변 — 그룹행 축 | 우연 잠금: 그룹 closed/revision 변경 시 replay 셀의 200 기대가 404/409로 깨진다 |
| ⑥ 행 불변 — **멤버행 축** | **빈칸(B2)** |
| ⑦ judge 미구성 503 — 남은 멤버 실재 | `test_judge_not_configured_fails_fast_with_503_and_nothing_started` |
| ⑦ eligible==1 무판정 통과(채택 없음) | `test_a_single_eligible_member_approves_without_a_judge` |
| ⑦ eligible==1 무판정 통과 — **채택 원천 멤버 단독** | **빈칸 + 행동 위반(B1)** |
| ⑧ 활동 로그(그룹 행 1줄·after 3수·멤버행 없음·변경≥1) | `GroupApproveActivityLogTest` 2셀 |
| ⑧ eligible 0 = 무변경 replay·행 없음 | `test_a_group_with_no_eligible_members_is_a_noop_replay` |
| closed 404 · contradicted 허용 · unknown/cross/missing 404 | 셀 5종(superseded 선제 포함 — Slice 4 B1 교훈 이식) |
| ⑨ 유료(402/429·SERVER dedupe·fan_out·COVERAGE) | billable·quota·오류선언·`_BILLABLE_404_409_JUDGE`(전수 가드) |
| 감사(compare_judge site·correlation_id=group_id·pair당 1행) | `GroupApproveAuditRowsTest` 2셀(실 adapter) |

### 2. 구현 코드 감사 — 리터럴 무불일치(결함은 §4)

- 409 detail `"expected revision N but the group is at revision M"`(`identity_groups.py:312-318`) — 현재 revision 포함 ✓.
- `judge_against`(`compare.py:158-187`): 강제 대상·JUDGE_ACTIONS 4값 검증·judge None이면 `CompareJudgeNotConfigured` — scope matcher/create 폴스루를 거치지 않는다 ✓.
- 채택의 이중 안전선: `promote_candidate`가 `find_memory_by_candidate`로 멱등 재생(`memory/service.py:234`) → 채택 원천 멤버의 seed 분기 confirm이 기존 memory를 돌려준다 — 두 번째 canonical 구조적 봉쇄 ✓(P3 실측: judge.calls에서 원천 제외·memory 1건).
- 진행 문서: 그룹당 1문서·step마다 저장·`truncate_to_ms` 공개 승격·시각 stamp는 service 정본 ✓. 저장복구 시나리오의 `changed` 재계산은 "문서에 canonical 없음" 상태에서만 도달하며 그 상태는 durable applied step을 가질 수 없어 이중 계산 없음(경로 분석).
- 라우터(`routers/analysis.py:950-1016`): `_REQUIRE_PROJECT_OWNER_BILLABLE`·409/503/404 매핑·감사 scope(correlation_id=group_id)·`reclassify_last_as_parse_error`(D4 첫 실패 종료라 재분류 대상은 최대 1행)·활동 행 리터럴(`identity_group_approved`·`after` 3수)·응답 5키 ✓.
- 유료: `BILLABLE_ACTIONS` 11행 중 `identity_group_approve`(fan_out=True)·SERVER dedupe 키 ·402/429 선언 ✓. 분류표 logged **29** ✓.
- 파기: `execute_project_purge`(`routers/admin.py:64`)에 `identity_group_approvals` 파라미터 실재, 커버리지·소유자 파기 테스트가 저장소 Protocol 등재 ✓.
- `3a2a3ee`(S-1 D3 판정 상한)은 `identity_judging.py`/`runner.py` 축 — 승인의 `judge_against`(compare 서비스)와 무관, 상호작용 없음 확인.

### 3. 등재 표면·생성물 — 전부 재현

- OpenAPI 독립 재덤프: **총 102 operation**·approve path·responses {200,401,**402**,403,404,**409**,422,**429**,503}·`ApproveGroupRequest` ✓.
- `schema.d.ts` 재생성(openapi-typescript 7.13.0): 커밋본과 **바이트 동일** ✓.
- 오류선언 EXPECTED 행(`test_application_api.py:2654`)·프론트 라벨 "정체성 그룹 승인"+비링크 사유(`frontend/src/projects/activityActions.ts:52-53`)·plans 인덱스 등재(확정 표기) ✓.

### 4. 뮤테이션·probe — 구현자 주장의 재현과 두 결함의 입증

| 변이/probe | 내용 | 실측 |
|---|---|---|
| VM-1(=구현자 M2) | revision 409 제거 | **1 failed**(409 셀) — 구현자 표와 셀 짝 일치 ✓ |
| VM-2(구현자 M7의 넓은 버전) | 채택 호출 전체 제거 | **3 failed**(채택 셀·저장복구 셀·no-eligible 셀) — 구현자 M7 기록(1 failed)과 짝이 다르지만 이는 변이 폭 차이이며, "채택은 셀 2종이 잠근다"는 주장이 참임을 확인 ✓ |
| **P1 probe** | 채택 원천 멤버가 유일 runnable + judge 미구성 | **503**("group approval needs the compare judge…") — 리터럴 ⑦("eligible==1이면 무판정 통과") 위반. 단독 형태·terminal 동반 형태 모두 실측. 대조: 판정 대상이 실재하는 시나리오의 503은 정당 |
| **P2 probe** | 승인 후 행 불변 실측 + 멤버행 1행 삭제 후 replay | 행동은 계약대로(open→open·revision 0→0·멤버행 2행 유지). 그러나 멤버행 삭제 후 replay가 **200·steps 동일** — 승인 관측면이 진행 문서(steps) 기반이라 멤버행 변경이 관측면 전체에 보이지 않는다 |
| **VM-3(처방 선적용)** | `to_judge` 면제에 채택 원천 멤버 포함(4줄) | **33 passed — 아무 셀도 안 물었다**(P1 시나리오는 200/applied/memory 1건으로 계약대로 변화) — 리터럴 ⑦ 분기의 무셀 입증 |
| P3 probe | judge 설정 시 동일 시나리오 | 원천 멤버는 seed 분기로 무판정 종결(judge.calls에 없음) — 503이 `to_judge` 과잉 산정 탓임을 확정 |

### 5. 전수

**2883 passed / 4 skipped / 3789 subtests, exit 0, 337.30s**(개시 HEAD `7e7df39` — S-0 보강 커밋 포함, 보강 세션 docs 편집 dirty 상태에서 기동. skip 4 = lexical retrieval 3(`elasticsearch` 미설치) + 기존 기준선 1 — 직전 검증과 동일). subtest 7886→3789 급감은 보강 세션의 가드 재구성(`7e7df39`, 가드 단독 5 passed/4670 → 9 passed/572 — 파일×값 subtest 구조 폐지)이고 Slice 5 축과 무관하다.

### 6. 기록 감사

- SoT v1.8.29 행 리터럴 ①~⑨·셀 33종·뮤테이션 12종·"채택은 설계 중 발견" 서술 — 코드·셀과 무불일치(단 M7 셀 짝은 좁은 변이 기준 — H3). "유료 9→10경로" 오기는 v1.8.31 B3가 이미 정정(11번째) — 이 검증에서도 `BILLABLE_ACTIONS` 11행 실측으로 확인.
- work_log 세션 7: 변이 표·RED 비고(관측 못 함 — 뮤테이션으로 갚음)·유료 전환 경위가 정직 기록 ✓. Slice 4 검증의 "폐쇄 전 Slice 5 착수 보류" 권고도 지켜졌다(`c9b2e36`·`6fdb8f1` 폐쇄가 `ffc9525`보다 선행).

## Issues / Risks

### Blocking (계약 의무)

- **B1 — 리터럴 ⑦ 위반 행동 + 무셀: 채택된 canonical의 원천 멤버가 유일한 runnable일 때 judge 미구성이면 503.** `to_judge = len(runnable) - (0 if canonical is not None else 1)`(`identity_group_review.py:292`)은 canonical 채택 시 seed 면제를 잃는다 — 그런데 채택 원천 멤버(개별 promote로 canonical 보유·needs_review 유지 경로: `POST /candidates/{id}/promote`)는 루프에서 **seed 분기로 무판정 종결**된다(P3). 판정이 필요 없는 승인이 503으로 거부돼 judge를 구성하지 않는 한 해당 그룹은 승인 불가다. 리터럴 ⑦ 문언("남은 멤버가 있을 때만… eligible==1이면 무판정 통과")과 구현자 셀 13 docstring의 자기 해석 양쪽과 모순. VM-3(처방 4줄)을 선적용해도 33 passed — 잠금 셀도 없다. **폐쇄: VM-3 diff 채택 + 짝 셀 2종(채택 원천 단독 + judge 없음 → 200·판정 대상 실재 + judge 없음 → 503 유지).**
- **B2 — 리터럴 ⑥ D3=A "그룹·멤버·relation 행 불변"의 멤버행 축 무셀.** 행동은 계약대로(P2)지만 승인 응답·replay가 진행 문서(steps) 기반이라 멤버행 삭제가 관측면 전체에 보이지 않는다(P2: 삭제 후 replay 200·steps 동일). Slice 4의 우연 잠금(거절 응답이 live 멤버 순회)은 승인 구조에서 성립하지 않는다. 그룹행 축은 우연 잠금(replay 200)이 있으므로 조건은 멤버행에 한정한다. **폐쇄: 승인 완료 후 그룹행(status·revision 무변)·멤버행 전건 존재를 단정하는 셀 1종.**

### Hardening (비차단)

- **H1** — `execute_project_purge` docstring의 "22컬렉션(… identity group 3)"이 approvals 합류 후 실제(SoT v1.8.29 서술 23컬렉션)와 1 어긋나는 낡은 산문. 동작·커버리지 셀은 정상 — 다음 파기 축 슬라이스에서 한 줄 정정.
- **H2** — 응답 `steps`의 "후보 id 정렬"이 셀에 명시 잠금 안 됨(모든 셀에서 added_at 순 = ID 순이라 관측 동등). Slice 4 M8 교훈과 같은 형태 — fixed clock + 역순 added_at 시드 셀 권고. 문서 저장이 항상 정렬해 저장하므로 replay 축은 안전하다.
- **H3** — 구현자 변이 표의 셀 짝은 좁은 변이 기준(M7 "1 failed" ↔ 검증자 넓은 변이 3 failed). 표에 diff 문언이 없어 라인 번호(`ea55474` 기준)만으로는 재유도 불가였다 — "적용한 변형" 열에 diff를 남기는 verification.md 규칙을 구현자 표에도 권고.
- **H4** — B1 수정 시 과잉 방향 짝 셀 필수(판정 대상 실재 + judge 없음 → 503 유지) — 면제 조건을 넓혀 정상 503까지 지우는 over-strict 교정을 막는다.

## Verdict

**조건부 합격** — 조건: ① B1 행동 수정(채택 원천 멤버 seed 면제, VM-3 diff)+짝 셀 2종, ② B2 멤버행 불변 셀 1종. 근거: 구현·등재·생성물·기록 주장은 전부 재현됐고(집중 33·인접 146·OpenAPI 102·`schema.d.ts` 바이트 동일·유료 11행·파기 합류), 핵심 오케스트레이션(채택·진행 저장·재개·Slice 4 H1 이관)은 전용 셀로 실재 잠금(VM-2). 그러나 리터럴 ⑦의 경계 하나가 **행동으로** 어긋나 있고(무판정 통과여야 할 승인이 503), 리터럴 ⑥ 멤버행 축이 무셀이다 — Slice 6(grouped UI)이 이 액션을 UI에 얹기 전에 닫아야 한다.

## Outstanding items

- B1·B2 폐쇄 세션 필요(합쳐 셀 3종 + 4줄 수정). 폐쇄 전 Slice 6 착수는 보류 권고.
- 프론트 기존 결함 2건(typeScale·designTokens) 사전존재 유지 — Slice 6 착수 전 확인(Slice 4 검증 이래 동일).
- 푸시는 오너 몫. test-mongo는 띄운 채 유지.
- 본 검증은 Phase S-0 보강 세션(동시 진행)과 커밋을 분리했다 — 뮤테이션은 dirty-tree 분기(cp + 역편집 + `cmp`), 커밋은 본 기록 + 인덱스 3건만 경로 지정 staged.

## Reproduction

```bash
# 전제: test-mongo healthy(docker compose -f docker-compose.test.yml up -d 후 대기)
python3 -m pytest -q tests/test_identity_group_approve.py \
  tests/test_identity_group_approvals_mongo.py            # 33 passed

# P1 probe(리터럴 ⑦ 위반): _build(judge=None) → 멤버 1명을
# POST /candidates/{id}/promote 로 승격(needs_review 유지) → 단독 그룹 approve →
# 503 관측(계약은 200). terminal 멤버 동반 형태도 동일.
# VM-3(처방): identity_group_review.py 의
#   to_judge = len(runnable) - (0 if canonical is not None else 1)
# 를
#   exempt = 1 if (canonical is None
#                  or canonical.source_candidate_id in runnable) else 0
#   to_judge = len(runnable) - exempt
# 로 바꾸고 재실행 — 33 passed(무셀 입증)·P1 시나리오는 200.
# VM-2(채택 제거): canonical = self._adopt_member_canonical(...) 호출을
#   canonical = None 1줄로 → 3 failed(채택·저장복구·no-eligible).
# 변이 복원은 dirty-tree 분기: cp 백업 ↔ 역편집 + cmp 바이트 비교(verification.md §Mutation).

# 생성물·인접
python3 scripts/dump_openapi.py > /tmp/o.json   # 102·approve path·402/409/429
cd frontend && ./node_modules/.bin/openapi-typescript /tmp/o.json -o /tmp/s.d.ts \
  && diff /tmp/s.d.ts src/api/schema.d.ts        # IDENTICAL
cd .. && python3 -m pytest -q tests/test_analysis_compare.py \
  tests/test_analysis_compare_api.py tests/test_analysis_compare_judge.py \
  tests/test_billable_actions.py tests/test_identity_group_reject.py \
  tests/test_llm_call_sites.py tests/test_quota_enforcement_api.py  # 146 passed

# 전수(개시 상태 마커: git log -1 = 7e7df39, git status = 보강 세션 docs dirty)
python3 -m pytest -q    # 2883 passed / 4 skipped / 3789 subtests, exit 0
```
