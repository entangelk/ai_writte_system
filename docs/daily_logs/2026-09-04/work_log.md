# Work Log — 2026-09-04 세션 1 (identity group Slice 3 — Review Inbox 읽기면, 베타)

## Goals

- 오너 지시("핸드오프 읽고 다음 작업 진행해줘. 슬라이스 3") — identity group **Slice 3(Review Inbox 읽기면)**
  구현. 착수점은 HANDOFF ★ 2026-09-03 문장(정본 v1.8.24, HEAD `4ace6c4` clean).
- 계획 정본: `docs/plans/pending-candidate-identity-grouping-implementation-phases.md` Slice 3 —
  "API payload에 group metadata를 additive로 싣는다. 프론트 UI와 그룹 액션은 아직 만들지 않는다."

## Completed work

구현 커밋 **`90cc4dd`** + 문서 커밋(이 세션 마감). SoT **v1.8.25**.

### 설계 — 계획에서 유도한 읽기면 리터럴

- **페이로드 모양**: 각 item(list+detail 공통 빌더 `_review_inbox_payload`)에 **키 하나** `identity_group` —
  값 `{group_id, group_size, group_status, group_member_ids, identity_rationale_summary}` 또는 ungrouped
  `null`. 내부 필드명은 계획 Slice 3의 열거 그대로. 중첩 객체+null은 `matched_memory: {...}|null`
  (conflict payload) 선례와 같은 모양이다.
- **소속의 정본은 open(non-closed) 그룹과 member 행** — 판정면 `identity_judging._group_of`(CLOSED만
  제외)과 같은 semantics. `contradicted`도 여전히 묶는다(상태값 그대로 노출 — UI 경고 라벨 재료).
  relation 행의 `group_id`는 소속·근거 선택 어디에도 쓰지 않는다(계획의 "표시 전용" 리터럴 시행).
- **roster는 멤버십 ∩ 검토함 population**(needs_review·미승격) — 검증 항목 "stale group member 정리"의
  시행. confirm/reject/edit로 검토함을 떠난 멤버는 roster에 싣지 않고 **가시 멤버 < 2면 그 항목은
  ungrouped로 읽는다**(묶을 것이 없음). 저장 멤버십은 불변 — member 수명 확정은 Slice 4·5(계획이
  `member_status` 확장을 그 슬라이스들에 배정).
- **`identity_rationale_summary`** = 이 후보와 가시 roster를 잇는 `same` relation 중 최신
  (`created_at`, 동률 pair id 순 — Slice 1 병합 셀의 "결정적 id 순서+클록 전진" 교훈 반영)의 rationale을
  **200자** 절단. 상한은 활동 로그 "짧은 값"(`ACTIVITY_VALUE_MAX_CHARS`)·장면 메모 목록 미리보기
  (`SCENE_NOTE_PREVIEW_MAX_CHARS`)와 같은 값 — 목록에 싣는 텍스트 조각에 두 번째 숫자를 만들지
  않는다(notes.py 선례). same relation이 없으면 `null`.
- 후보가 non-closed 그룹 둘에 동시에 있으면(서비스 불변식 밖의 비정상 상태) 병합 생존 규칙과 같은
  순서(오래된 그룹)가 이긴다 — 결정성만 위한 방어, 셀은 안 만들었다(불변식 위반 상태에 대한
  over-speculation 회피).

### 코드

- `analysis/review_inbox.py` — `IdentityGroupSummary` 데이터클래스, `ReviewInboxItem.identity_group`
  필드, `ReviewInboxService`에 `identity_groups: CandidateIdentityGroupService` 주입(생성은 main.py가
  항상 하므로 required), `IDENTITY_RATIONALE_SUMMARY_MAX_CHARS = 200`, `_identity_summaries`(목록 단위
  1회 계산 — groups·relations를 프로젝트별로 한 번씩만 읽는다).
- `routers/analysis.py` — `_identity_group_payload` + payload에 `"identity_group"` 키(list+detail).
- `main.py` — `ReviewInboxService(..., identity_groups=identity_groups)` 조립.
- 활동 분류표 무관(신규 mutating route 없음 — 읽기면만).

### 테스트(먼저 작성 — RED 13 failed `KeyError: 'identity_group'` 확인 후 구현)

`tests/test_review_inbox_identity_groups.py` 13셀 — create_app에 in-memory identity group 서비스+
`_FixedClock`(relation created_at 순서용)을 주입해 시드. 계획 검증 항목 전부:
혼합 목록에서 기존 필드·affordance 유지 · ungrouped null · closed 그룹 제외 · contradicted 노출 ·
stale 멤버 제외 · 가시 <2 ungrouped · project 격리 · detail 동등 · 근거 최신 선택(same 아닌
판정은 제외) · 200자 절단 · relation.group_id 미사용 · same relation 없으면 근거 null.

### 회귀

- focused: 신규 파일 **13 passed**.
- 인접 suite: `test_analysis_apply_api.py`+`test_application_api.py` **166 passed / 546 subtests**.
- **전수 1차: 2743 passed / 12 skipped / 3134 subtests, exit 0(1941.82초)** — **기각 후 재실측**:
  skip가 baseline 1에서 12로 늘었다. 원인: test-mongo가 아직 `health: starting`일 때 collection이
  시작돼 Mongo-gated 모듈(`test_analysis_mongo.py` 등)의 import-time 가드가 skip됨(11건). 코드
  무관의 측정 오염이므로 **Mongo healthy 상태에서 재실측**.
- **전수 2차(채택): 2754 passed / 1 skipped / 3134 subtests, exit 0, 1804.50초.**
  **검산**: 2741(v1.8.24 폐쇄 기준선) + 13 신규 = 2754 ✓, skip 1 = chroma live(CHROMA_TEST_URL
  미설정 — 기존 축) ✓, subtest 3134 무변(신규 셀 subtest 없음) ✓, 잔차 없음.
- **OpenAPI/`schema.d.ts` 무변 실측**: `4ace6c4`(HEAD) 작업 트리 ↔ baseline 덤프 **바이트 동일**
  (md5 `10978d55…`·384,414B — Slice 2 검증이 확정한 지문과 동일). review-inbox 응답이
  `dict[str, object]`로 선언돼 additive payload가 선언 schema에 나타나지 않는다 → 프론트
  생성물 재생성 불요, 프론트 전수도 불요(프론트 무변경·스키마 무변).
- pyflakes(변경 4파일): 무지적.

### 뮤테이션 9종(전부 기명 재실패 — 복원 후 트리 clean 매번 확인)

| # | 변이 | 재실패 |
|---|---|---|
| M1 | closed 그룹 skip 제거(껍데기 member 행 누출) | 1 failed(closed 셀) |
| M2 | 가시 교집합 제거(roster=저장 멤버 전부) | 2 failed(stale 셀·가시<2 셀) |
| M3 | 가시 <2 가드 제거 | 1 failed(가시<2 셀) |
| M4 | 근거 선택 최신→최초 반전 | 1 failed(최신 선택 셀) |
| M5 | 200자 절단 제거 | 1 failed(절단 셀) |
| M6 | same-verdict 필터 제거(뒤집힌 different도 근거로) | 1 failed(최신 선택 셀) |
| M7 | 근거 선택을 relation.group_id 기반으로(정본 위반) | 4 failed(group_id 셀·메타데이터·절단·최신 — group_id 없는 relation 제외로 근거가 실종) |
| M8 | contradicted를 미참여로(과잉 교정 — closed 필터를 OPEN-only로) | 1 failed(contradicted 셀) |
| M9 | payload에서 `identity_group` 키 제거 | 13 failed(전 셀 — KeyError) |

양방향: under-strict M1·M4·M6·M7·M9 / over-strict M2·M3·M8(M5는 상한 리터럴 핀).
복원 후 focused 재실행 **13 passed**, `git status --short` clean.

## Decisions

- **별도 결정 브리프 없이 진행** — 페이로드 모양(중첩 객체+null)·roster 교집합·200자 상한 전부
  계획 Slice 3 문구("예를 들어" 필드 열거·"stale group member 정리" 검증 항목·읽기면 정본 문장)과
  저장소 선례(`matched_memory` null 객체·활동/장면메모 200자)에서 유도됐다. 공통 규칙의 브리프
  트리거("코드에서 유도되지 않는 계약 리터럴")에 해당하지 않음.
- **전수 1차를 기각하고 재실측했다** — 2743/12는 코드가 아니라 측정 창(test-mongo 기동 경합)이
  만든 수치. 기록은 healthy 상태의 2차(2754/1)로 채택하고 1차도 남긴다(같은 함정의 재현 기록).

## Next steps

- **Slice 4(그룹 거절 액션) 착수** — `POST .../review-inbox/groups/{group_id}/reject` 계열, 예상
  operation 100→101. 착수 시 짧은 결정 브리프 항목: 활동 로그 남길지 여부(계획이 명시적으로 열어둠).
- 이 슬라이스의 독립 검증은 검증 가이드 절차대로 별도 세션이 한다(구현자 자기 검증 아님).
- 푸시는 오너 몫.

---

# Work Log — 2026-09-04 세션 2 (identity group Slice 3 독립 검증, 베타)

## Goals

- 오너 요청("작업 ai가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?") — 구현 세션 1이 마감한
  identity group **Slice 3(Review Inbox 읽기면)**(`90cc4dd`·`e9680e4`·`2223ba3`, SoT v1.8.25)의 독립 검증.

## Completed work

판정 **조건부 합격** — 검증 기록
[`verifications/2026-09-04/identity_group_slice_3.md`](../verifications/2026-09-04/identity_group_slice_3.md)
(인덱스·판정 분포 279건/조건부 85 갱신, 문서 가드 green).

- **재현**: 집중 13셀 green, RED 재현(부모 구현 3파일 복귀 시 **13 failed**·`KeyError: 'identity_group'`
  실측), OpenAPI **코드 경계(4ace6c4↔HEAD) 바이트 동일** 독립 재덤프(md5 `10978d55…`·384,414B),
  `schema.d.ts` 무변, 소속 정본이 판정면 `_group_of`와 같은 semantics·public service 전용 사용·
  검토함 population 정의·edit 이탈 경로(계약의 세 이탈 원인 열거가 사실임) 확인. SoT v1.8.25 행·
  HANDOFF 착수점·CHANGELOG·README ④ 대조 무불일치.
- **뮤테이션 6종 실측** — 구현자 표 M1·M2·M5·M7·M8 재유도가 셀 짝까지 일치(1/2/1/4/1 failed).
  검증자 신설 **VM1**(근거 선택의 관계 양끝 가시 roster 필터 제거)은 **13 passed로 물지 않았다** →
  차단 B1. 본 트리 변이(RED·VM1·VM2·VM3)는 전수 개시 전에, 잔여 3종은 `/tmp` detached worktree에서
  실행해 전수 창과 분리.
- **probe 1종**(기록 옆 커밋): `repro_rationale_out_of_roster.py` — 가시 roster 밖 pair의 same
  relation이 근거가 되지 않는 행동(rationale `null`) 실측. B1은 잠금 부재뿐(Slice 1·2 B1과 같은 모양).
- **하드닝 4건(H1~H4)**: created_at 동률 tie-break 무셀·방향 미기재, stale 이탈 세 번째 원인 edit 무셀,
  relation `candidate_type` 필터 계약 미기재, 이중 non-closed 소속 "오래된 그룹 first" 규칙 계약 미기재.

## 회귀

- 전수(test-mongo healthy 개시, 검증 기록이 인덱스 등재 전 디스크에 있는 채): **2752 passed /
  9 failed / 1 skipped, 3128+7 subtests, 1858.78초** — 실패 9건은 전부 문서 가드(부모 2+subTest 7)가
  279번째 기록을 본 것이고 단독 재실행으로 같은 9개 재현·전량 귀속. 코드 축 산술: 2752 = 2754−가드
  부모 2, 3128+7 = 3134+이 기록 subTest 1 — **회귀 0, 구현자 2754/1/3134 성립**. 인덱스 갱신 뒤
  `test_docs_indexes.py` green.

## Next steps

- **B1 폐쇄**: probe 본체를 기명 셀로 추가(예: `test_rationale_ignores_relations_to_members_outside_the_roster`)
  + VM1 재실측으로 물림 확인 — **Slice 4 착수 전에**. H1~H4는 폐쇄 세션에서 함께 볼 것(계획·SoT 한 줄
  또는 셀).
- 푸시는 오너 몫. test-mongo는 띄운 채 남김(`docker compose -f docker-compose.test.yml down`으로 정리).

---

# Work Log — 2026-09-04 세션 3 (identity group Slice 3 검증 조건 B1 폐쇄 + 하드닝 H1~H4, 베타)

## Goals

- 오너 지시("검증기록 확인해서 보강할 부분 보강해줘") — 독립 검증
  `verifications/2026-09-04/identity_group_slice_3.md`(판정 **조건부 합격**, 커밋 `73d1b10`)의
  차단 B1 폐쇄 + 비차단 하드닝 4건(H1~H4) 반영. Slice 2의 세션 7(2026-09-03)과 같은 흐름.

## Completed work

### B1 폐쇄(커밋 `0ff8d13`)

- **셀 `test_rationale_ignores_relations_to_members_outside_the_roster`** — probe
  `repro_rationale_out_of_roster.py`의 본체를 그대로 셀로 옮겼다(검증 기록이 제안한 폐쇄 방식):
  trio 그룹 {a,b,c}에서 b reject → 가시 {a,c}로 그룹 생존(≥2)·`group_member_ids` 교차 검증까지
  단정하고, **a-b same relation의 상대 b가 가시 roster 밖이므로 a의 근거는 `null`**임을 잠근다.
- **VM1 재실측**(검증 기록의 정확한 diff — relation 양끝 roster_set 필터 제거): **2 failed**
  (B1 셀 + edit 셀) — 13 passed로 입증됐던 무셀 축이 닫혔다.

### 하드닝 H1~H4

- **H1(동률 tie-break 방향)** — 셀 `test_rationale_tie_breaks_by_the_larger_pair_id`: 클록을
  전진하지 않고(같은 `created_at`) focal과 두 파트너의 same relation을 기록하면 **큰 id 파트너의
  relation이 이긴다**(focal 고정 시 pair 튜플의 대소 = 파트너 id 대소라 런타임 산출으로 단정).
  변이 MH1(비교 반전 `>`→`<`)에 2 failed(동률 셀+최신 선택 셀). 방향을 계획·SoT 리터럴에
  "동률은 큰 pair id 승리"로 명문화.
- **H2(edit 이탈 원인)** — 셀 `test_edited_member_leaves_the_group_roster`: edit의 승격은 새
  후보 id로 나가고 원본은 superseded → roster {a,c}·근거 null. confirm(기존 셀)·reject(기존
  셀)·edit(신규) 열거의 문서-셀 대응이 완결됐다.
- **H3(타 type relation 방어)** — 셀 `test_rationale_ignores_relations_of_another_candidate_type`:
  `candidate_type=EVENT`로 기록된 relation이 character roster 후보 id를 참조해도 근거가 되지
  않는다(그룹 자체는 member 행으로 생존). 변이 MH3(필터 제거)에 1 failed. 계획·SoT에 근거 한 줄
  반영 — 판정 경로는 같은 type pool만 짝짓지만 저장 면이 이 행을 거부하지 않으므로 읽기면의 방어.
- **H4(이중 소속 규칙 명문화)** — 코드만 존재하던 "non-closed 그룹 둘에 동시 소속 시 오래된
  그룹 first"(병합 생존 규칙과 같은 순서, 결정성 방어)를 계획·SoT에 기재. 셀은 만들지 않았다
  (세션 1 결정 유지 — 서비스 불변식 밖 상태에 대한 잠금은 over-speculation).

### 회귀(세션 3)

- focused: **17 passed**(13+4). OpenAPI 무변(셀만 추가 — 응답 선언 무변, 재덤프 불요).
- 전수(test-mongo healthy 확인 후 개시): **2758 passed / 1 skipped / 3135 subtests, exit 0,
  2256.74초**. **검산**: 2754(세션 1 기준선) + 4셀 = 2758 ✓, subtest 3135 = 3134 + 1(검증
  기록 279건째의 문서 가드 subTest — 인덱스 등재 후 green) ✓, skip 1 = chroma 관례 ✓.
- 문서 편집은 전수 완료 **뒤에** 했다 — 검증 기록 §6가 관측한 함정(전수 창 중 문서 가드가
  디스크를 봄)을 그대로 밟지 않기 위해.

## Decisions

- **B1·H1~H3은 셀로, H4는 문서로 닫았다** — H4의 방어는 서비스 불변식 밖 상태용이므로 셀을
  만들면 그 상태를 계약으로 승격하는 모양이 된다. 검증 권고("한 줄 추가하거나 방어 제거 결정")에서
  한 줄 쪽을 택했다.
- **검증 기록의 "README ② 낡은 수수" Outstanding도 이번 마감에 함께** 갱신했다(2702/3132 →
  2758/3135) — 검증이 "다음 문서 마감 때 함께 맞추면 된다"고 지정한 시점이 바로 이 세션이다.

## Next steps

- **Slice 4(그룹 거절 액션) 착수** — B1 폐쇄로 길이 열렸다. 착수 시 짧은 결정 브리프: 활동 로그
  남길지 여부(계획이 명시적으로 열어둠).
- 푸시는 오너 몫.
