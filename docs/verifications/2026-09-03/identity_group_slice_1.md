# identity group Slice 1(shortlist와 판정 서비스)— 독립 검증

**조건부 합격** — 계약 요구 분기 3곳에 기명 셀이 없다: B1(event/open-question retriever 미주입 → 빈 shortlist no-op), B2(relation `source` 리터럴 `identity_judge`), B3(재사용 경로의 효과 멱등 재적용 — 그룹 연결·모순 표시 자가 치유). 세 셀이 추가되면 통과한다.

## Subject metadata

- 검증일: 2026-09-03
- 요청자: 오너 — "다음작업 검증해줘. Slice 1 완료. 네 커밋으로 마감했습니다."
- 검증자: 이 세션(구현 세션 4와 다른 세션). 구현자 보고(work_log 세션 4·SoT v1.8.21 행·커밋 메시지)는 전부 **가설**로 취급해 원본에서 재유도했다.
- 대상: 커밋 3+1개 — `f5c0ead`(구현: 서비스+17셀)·`98c5c13`·`3dfef65`(병합 셀 보강, 테스트 전용)·`6718bc5`(기록). HEAD `6718bc5`, 트리 clean. 선행 `2146da5`는 docs-only(2파일)라 코드 기준선은 `7ab3df6`이다.
- 정규 계약: `docs/plans/pending-candidate-identity-grouping-implementation-phases.md` §Slice 1(규칙·검증 문장 + 완료 기록 리터럴 ①~⑤) · `docs/system-contract-sot.md` **v1.8.21**(변경이력 행 + §Phase 2A identity 판정 서비스 조항 ①~⑥) · C 채택 브리프 `pending-candidate-identity-grouping-decisions.md`.

## Scope

1. 경계 행렬 — 계획 §Slice 1 규칙/검증 문장 + SoT v1.8.21 리터럴 전부를 should/should-NOT/리터럴로 전개해 셀 대응표를 만든다.
2. 구현 코드 감사 — shortlist 격리·판정 재사용·모순 표시·병합·seam(sync/async)·**Slice 0 public service 전용 사용**(인계 조항)·runner/HTTP 미배선.
3. 테스트 코드 감사 — 17셀 각각이 계약 조항에 대응하는지(단정이 계약을 잠그는지).
4. 뮤테이션 — 구현자 표 10종을 diff까지 재유도해 재실행 + 검증자 신설 3종(갭 입증용).
5. 전수 회귀 재실행 + OpenAPI 덤프 사전 트리 대조(독립 재덤프) + mypy·문서 가드.

## Methodology

환경(측정의 일부): WSL2 베타(GTX 1060), Python 3.12.3 / pytest 9.0.2, **`.env` 없음**(compose 기본값), test-mongo(127.0.0.1:27020, rs-test) `up -d` 후 `State.Health.Status=healthy` 게이트 후 개시. 이 머신 관례 skip 1(ES 패키지 탑재).

- 전수: `python3 -m pytest -q 2>&1 | tail -3`
- OpenAPI: `python3 scripts/dump_openapi.py`를 본 트리와 `git worktree add /tmp/pre_slice1 7ab3df6` 사전 트리에서 각각 실행 → `cmp`(md5 `10978d55571a90ccd52f65220fc354d3`·384,414B).
- 뮤테이션: 매번 `git status --short` empty 확인(사전 게이트) → 변이 → `pytest tests/test_identity_judging.py -q` → **요약줄+FAILED/SUBFAILED 함께 판독** → `git checkout -- <path>` → 원복 후 바이트 동일 확인(스크립트가 원문 대조). 적용 diff 는 아래 표에 축약 없이 기재.
- 가드 단독: `pytest tests/test_typecheck.py tests/test_docs_indexes.py -q`.

## Findings

### 1. 경계 행렬 — 셀 대응(잠긴 축)

| 계약 조항(계획§Slice 1 / SoT v1.8.21) | 셀 | 비고 |
|---|---|---|
| character shortlist = 정규화 이름 신호 | `test_character_shortlist_uses_normalized_name` | "  ariel "≈"Ariel" 정규화 실측 |
| project 격리 | `test_shortlist_is_isolated_by_project` | |
| type 격리(retriever pool에 같은 type만) | `test_shortlist_is_isolated_by_candidate_type` | pool 내용까지 단정 |
| 같은 job 후보 포함·자기 id 제외 | `test_same_job_candidates_are_eligible_but_self_is_excluded` | compare D6(자기-job 제외)와 방향이 다름을 SoT §738이 명시 |
| judge 미구성 = pair 있을 때만 명시 오류 | `test_missing_judge_is_an_explicit_error_only_when_pairs_exist` | |
| 빈 shortlist no-op(character 경로) | `test_empty_shortlist_is_noop_without_judge` | B1은 이 축의 event/open-question 경로(무셀) |
| `same`→member 연결+relation.group_id | `test_same_verdict_connects_group_members` | |
| `different`/`uncertain`→relation만 | `test_different_and_uncertain_leave_relation_only` | group_id=None 단정 포함 |
| verdict 축 밖 거부 | `test_invalid_judgement_is_rejected` | relation 잔류 없음까지 |
| judge 예외 전파 | `test_judge_exception_propagates` | |
| async judge await | `test_awaitable_judge_result_is_awaited` | CompareJudge 선례 겸용 seam |
| focal 존재+needs_review | `test_focal_must_exist_and_be_needs_review` | 타 project 404축·REJECTED 축 포함 |
| 같은 pair 재실행 멱등(재판정 없음) | `test_rerun_reuses_stored_relation_without_rejudging` | created_at·added_at·revision 불변까지. **효과 재적용 축은 무셀(B3)** |
| different-after-same contradicted+정확히 한 번 | `test_different_after_same_marks_group_contradicted` | revision==1 단정 |
| same 삼각형 완성 역순 contradicted | `test_same_closing_a_different_triangle_also_contradicts` | 도착 순서 무결 |
| same 성분 없는 different는 평범(over-strict 방어) | `test_plain_different_pair_never_contradicts` | |
| 두 그룹 병합·오래된 생존·껍데기 closed·제외 | `test_same_across_two_groups_merges_into_the_older_group` | 결정적 id+클록 전진(아래 3) |
| relation `source` 리터럴 `identity_judge` | **없음** | **B2** |
| retriever 미주입 → no-op | **없음** | **B1** |
| 재사용 경로 효과 재적용(자가 치유) | **없음** | **B3** |

### 2. 구현 코드(`analysis/identity_judging.py`)

- **shortlist 격리** — `_same_type_pool`(:200-216)이 `list_needs_review_candidates(project_id)`에서 같은 type·자기 id 제외로 pool을 만들고 id 정렬(결정적). `_shortlist`(:218-242)의 character 분기는 `normalize_name` 일치. **retriever 미주입 no-op 분기는 코드에 있으나(:233-235) 그 경로를 도는 셀이 없다(변이 NEW-A로 입증).**
- **판정 재사용** — `judge_candidate`(:152-186): relation 있으면 judge 재호출 없이 재사용하고 `_ensure_same_group` 재적용(:180-183)·`_mark_contradictions`(:184-186, uncertain 제외라 재사용 pair에도 실행). **이 "효과 재적용"은 관찰하는 셀이 없다(변이 M2b로 입증)** — 멱등 셀은 그룹이 이미 있는 순수 멱등 상태만 본다.
- **Slice 0 public service 전용** — 그룹 읽기/쓰기 전부 `CandidateIdentityGroupService`(get_relation·record_relation·create_group·add_member·set_group_status·list_groups·list_members·list_relations). 컬렉션 직접 조립 없음. 후보 읽기는 `AnalysisRepository`(인계 조항이 금지하는 것은 그룹 저장소 직접 접근 — 준수). `git diff 7ab3df6..HEAD -- identity_groups*.py` 빈 출력으로 Slice 0 면 무접촉(테스트의 `clock=`·`id_factory=` 주입은 Slice 0부터 있던 면).
- **미배선** — `CandidateIdentityJudgingService` 참조가 모듈·테스트 외 0건(grep services/·scripts/). 계획대로 runner·HTTP는 Slice 2.
- **source 리터럴** — `record_relation(..., source="identity_judge")`(:174). 코드는 계약과 일치하나 단정이 없다(**B2**, 변이 NEW-B로 입증).

### 3. 병합 셀 보강 두 커밋(`98c5c13`·`3dfef65`)

`98c5c13` — 그룹 id를 `cig:b`(생존)/`cig:a`(흡수)로 결정적 배정해 **흡수 껍데기가 목록 정렬에서 먼저** 오게 했다(`_group_of`가 closed 를 건너뛰는지 정렬 운이 아니라 잠금). `3dfef65` — 두 그룹 생성 사이 `clock.advance()`로 `created_at` 동률 제거(생존자가 확실히 오래된 그룹). 구현자가 밝힌 우연 통과 결함(M8이 재실패하지 않아 노출)의 보강이고, 보강 후 M8이 물리는 것을 이번 검증도 재현했다(아래 표). 교훈(시간 tie-break 셀은 클록이 실제로 흐르는지부터)은 기록 가치가 있다.

### 4. 뮤테이션 13종 — 표(구현자 10종은 셀 짝까지 일치 재현)

| 변이(diff 요지) | 실측 |
|---|---|
| M1 `if relation is None:` → `if True or relation is None:`(항상 재판정) | 1 failed — `test_rerun_reuses_stored_relation_without_rejudging` |
| M2 판정 분기의 same→`_ensure_same_group` 블록을 `group_id = None`으로 | 5 failed — same 연결·awaitable·멱등·삼각형 역순·병합 |
| M3 `_mark_contradictions` 첫 줄 `return` | 2 failed — 삼각형 셀 2종 |
| M4 `_same_component` gate를 `pass`로(성분 확인 없이 different마다 표시, over-strict) | 1 failed — `test_same_closing_…`(중간 OPEN 단언) |
| M5 pool의 type 필터 제거 | 1 failed — `test_shortlist_is_isolated_by_candidate_type` |
| M6 pool에 `candidate.job_id != focal.job_id` 추가(같은 job 제외 — compare D6 오복사, over-strict) | 13 failed |
| M7 `_ensure_same_group` 양쪽 그룹 분기에서 병합 블록을 `return group_left`로 | 1 failed — 병합 셀 |
| M8 `_group_of`의 CLOSED skip 제거 | 1 failed — 병합 셀(보강 커밋의 실효 재현) |
| M9 `_judge_pair`의 verdict/rationale 검증 제거 | 1 failed — `test_invalid_judgement_is_rejected` |
| M10 `judge_candidate` 상단에 judge 필수(빈 shortlist 포함, over-strict) | 1 failed — `test_empty_shortlist_is_noop_without_judge` |

검증자 신설(갭 입증 — **전부 물지 않는다**):

| 변이 | 실측 | 의미 |
|---|---|---|
| NEW-A `_shortlist`의 `if self._shortlist_retriever is None: return ()` 제거 | **17 passed(무셀)** | event/open-question retriever 미주입 no-op 분기(B1)를 도는 셀 없음 |
| NEW-B `source="identity_judge"` → `"compare_judge"` | **17 passed(무셀)** | source 리터럴을 잠그는 단정 없음(B2). Slice 0 테스트의 `source="identity_judge"`는 fixture 입력값일 뿐 |
| NEW-C(=M2b) 재사용 분기의 `_ensure_same_group` 호출 제거 | **17 passed(무셀)** | 리터럴 ①의 "효과 멱등 재적용(자가 치유)"을 관찰하는 셀 없음(B3) |

매 변이 후 원복·바이트 동일 확인, 최종 트리 clean.

### 5. 전수·OpenAPI·가드

- 전수: **2719 passed / 1 skipped / 3133 subtests, exit 0, 2183초**(test-mongo healthy 후). 셀·skip은 구현자 주장(2719/1)과 정확히 일치. subtest 3132→3133의 +1은 **본 검증 기록의 판정 열 등재분**(런 중 인덱싱 — 문서 가드 단독 287 subtests와 정확히 합치; 검증 기록 건수 축의 알려진 자리). 검산: 직전 2702 + 신규 17셀 = 2719, subtest 3132 + 1(기록) = 3133, 잔차 없음.
- OpenAPI: 본 트리와 사전 트리(`7ab3df6`) 덤프 **바이트 동일**(각각 별도 실행, md5 `10978d55…`) — 공개 계약·`schema.d.ts` 무변 성립.
- mypy 8셀 + 문서 인덱스 13셀 green(`test_typecheck.py`·`test_docs_indexes.py` 21 passed/289 subtests — subtest 289는 typecheck 3 포함).

## Issues / Risks

### Blocking (계약 의무 — 판정 조건)

- **B1 — retriever 미주입 no-op 분기 무셀.** 계획 §Slice 1 규칙("adapter가 없으면 empty shortlist로 fail-closed가 아니라 no-op")과 SoT v1.8.21 §738②가 명시하는 should-NOT-fire 분기. 변이 NEW-A(가드 제거)가 17 passed로 통과해 입증. 잠금 셀 예: event focal + retriever=None → shortlist()==judge 미호출·오류 아님.
- **B2 — relation `source` 리터럴 무셀.** 완료 기록 리터럴 ⑤·SoT v1.8.21(행 및 §738⑥)이 못박은 리터럴. 변이 NEW-B(리터럴 변조)가 17 passed로 통과해 입증. 잠금 셀 예: 판정 후 relation.source == "identity_judge".
- **B3 — 재사용 경로의 효과 재적용(자가 치유) 무셀.** 완료 기록 리터럴 ①·SoT v1.8.21("그룹 연결·모순 표시는 다시 일어나 죽은 실행의 빈자리를 스스로 메운다"). 변이 M2b(재사용 분기 `_ensure_same_group` 제거)가 17 passed로 통과해 입증 — 멱등 셀은 그룹이 이미 있는 상태만 본다. 잠금 셀 예: SAME relation을 저장해 두고 그룹 없는 상태(죽은 실행)에서 `judge_candidate` 재실행 → judge 재호출 없이 그룹·멤버 생성(± 모순 미표시 상태에서 contradicted 재표시).

셋 다 행동 무결(구현이 계약대로 동작함) — 빈 것은 **잠금**이다. 셀 3개 추가(파일 내 신규 3메서드)로 조건 폐쇄 가능하고, 그 시점 기대 전수는 2719+3=**2722/1/3132**다.

### Hardening recommendations (비차단)

1. **병합 후 relation.group_id의 낡은 값** — 흡수된 그룹을 가리키는 relation 행이 갱신되지 않는다(설계상 member 행도 남기므로 대칭). Slice 3 읽기면은 open 그룹/멤버 기준으로 읽는 계획이므로 결함은 아니나, 읽기면 설계 시 relation.group_id를 표시 전용으로 문서화하거나 승격(Slice 5)에서 갱신 정책을 정할 것.
2. **B3 셀을 잡으며 모순 재표시 축도 함께** — SAME relation + different 삼각형이 있고 그룹이 OPEN(표시를 놓친 죽은 실행)인 상태의 재실행에서 contradicted가 다시 일어나는지까지 같은 셀에 넣으면 리터럴 ①의 두 효과(연결·표시)를 한 셀이 잠는다.
3. **shortlist 상한** — 같은 이름 후보가 수백 개면 O(pool×relations) BFS가 커진다. dogfood 규모에서 문제될 징후는 없으므로 트리거 유예: Review Inbox 그룹 수가 세 자리로 관측될 때 상한·페이징 논의.

## Verdict

**조건부 합격** — B1(retriever 미주입 no-op 셀)·B2(`source` 리터럴 셀)·B3(재사용 효과 재적용 셀)의 기명 셀 3개가 추가될 때까지.

- 구현 자체는 계약과 문구 수준에서 일치(경계 행렬의 잠힌 17축 전부 코드가 계약대로 동작 — 변이 10종 재현 포함).
- 전수·OpenAPI 바이트 동일·가드 green을 독립 재현(아래 실측).
- 갭 3곳은 전부 "행동은 있으나 잠금이 없는" 빈 칸이다(가이드 "boundary matrix has no empty cells" 위반 — green bar와 무관).

## Outstanding items

- **조건 3건 폐쇄 대기(구현자 몫)** — 셀 3개 추가 후 집중 재실행 + 다음 전수 기대값 2722/1/3132(+3셀, subtest 무변 예상). 폐쇄 시 본 기록 판정 열은 승격하지 않고 폐쇄 커밋이 별도로 남긴다(Slice 0 B1 선례).
- Slice 2(분석 runner 배선)는 폐쇄 후 착수가 자연스럽다(B3 셀이 Slice 2의 "판정 실패 job 격리" 신뢰 기반이 된다).
- 푸시는 오너 몫. 이 검증 세션은 코드를 건드리지 않았다(변이는 전부 원복·바이트 대조 완료).

## Reproduction

```bash
# 환경: .env 없음, compose 기본값
docker compose -f docker-compose.test.yml up -d
until [ "$(docker inspect -f '{{.State.Health.Status}}' ai_writte_system-test-mongo-1)" = healthy ]; do sleep 2; done
python3 -m pytest -q                                   # 2719/1/3133(기록 등재 전 트리는 3132), exit 0

# OpenAPI (사전 트리 대조)
git worktree add /tmp/pre_slice1 7ab3df6
python3 scripts/dump_openapi.py > /tmp/head.json
(cd /tmp/pre_slice1 && python3 scripts/dump_openapi.py > /tmp/pre.json)
cmp /tmp/head.json /tmp/pre.json                       # byte-identical
git worktree remove /tmp/pre_slice1 --force

# 갭 입증 예시(NEW-B): git status --short empty 확인 → identity_judging.py의
# source="identity_judge"를 "compare_judge"로 → pytest tests/test_identity_judging.py -q
# → 17 passed(무셀 입증) → git checkout -- services/application/app/analysis/identity_judging.py
```
