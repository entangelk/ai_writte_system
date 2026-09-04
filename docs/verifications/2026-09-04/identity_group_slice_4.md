# identity group Slice 4(그룹 거절 액션)— 독립 검증

**조건부 합격** — **SoT v1.8.27 리터럴 ①의 두 미잠금 조항**(B1 superseded skip·B2 승격 무시)을 셀 2개 추가로 닫을 것. 리터럴 ①은 "terminal(confirmed·rejected·superseded) **전 종류**는 skip한다"·"승격 여부(`is_candidate_promoted`)는 **보지 않는다**(승격된 needs_review 후보도 거절되며 canonical은 append-only라 그대로 남는다)"를 확정 리터럴로 열거하나, 10셀 어디도 superseded 멤버의 skip·승격된 needs_review 멤버의 거절을 잠그지 않는다. 검증자 변이 VM-A(skip 열거에서 superseded만 제외하는 과잉 교정)가 **10 passed**로 B1의 무셀을 입증했고, 이때 superseded 멤버를 포함한 그룹은 `InvalidCandidateStateTransition`이 라우터 catch 목록 밖으로 새어 **미처리 예외로 배치 중단**된다(실측). B2는 전 suite 검색으로 상응 셀 부재를 확인했다(개별 reject 경로에도 없음 — "개별 reject와 같은 면" 상속 불성립). **행동 자체는 전부 계약대로다**(검증자 probe 2종 실측 — superseded skip ✓·승격 멤버 거절+canonical 잔존 ✓; probe를 폐쇄 셀 본체로 쓸 수 있다). Slice 1 B1~B3·Slice 2·3 B1과 같은 "빈 것은 잠금" 모양이다. 그 외 구현 주장 전부는 재현됐다 — 변이 재유도 **8/9종**이 구현자 표와 셀 짝까지 일치(M2 관측 동등·M8 보강 후 재실패 포함), 전수 **2768/1/3159 exit 0** 재실측, operation **101**·신규 path·오류 선언 {200,401,403,404,422,503}·`schema.d.ts` 재생성물 **바이트 동일**·등재 5곳(분류표 28·tier 75/101·오류 선언 22·라벨 28행·plans 인덱스 119)·프론트 기존 결함 2건의 **사전존재**(6cb6abc detached worktree 재현).

## Subject metadata

- 검증일: 2026-09-04
- 요청자: 오너 — "작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래? Slice 4(그룹 거절 액션) 마감. 커밋 5건(4b0d907→bb68bfa), 트리 clean, 푸시는 오너 몫."
- 검증자: 이 세션(구현 세션 4와 다른 세션). 구현자 보고(work_log 세션 4·SoT v1.8.27 행·커밋 메시지·HANDOFF·CHANGELOG)는 전부 **가설**으로 취급해 원본에서 재유도했다.
- 대상: 커밋 5건 — `4b0d907`(구현+셀 10종+브리프+분류표/라벨/카운트 가드+`schema.d.ts`)·`1b41177`·`227aeb4`(M8 무셀 발견 → 고정 클록·역순 added_at 셀 보강)·`0a6b884`(오류 선언 잠금 22·plans 인덱스 등재)·`bb68bfa`(마감 기록: SoT v1.8.27·work_log 세션 4·HANDOFF·CHANGELOG·README ②④). HEAD `bb68bfa`, 트리 clean, push 안 됨.
- 정규 계약: `docs/plans/pending-candidate-identity-grouping-implementation-phases.md` §Slice 4(규칙·검증 문장 + 완료 기록 리터럴) · `docs/system-contract-sot.md` **v1.8.27**(변경이력 행 — 리터럴 ①~⑥) · 착수 브리프 `pending-candidate-identity-grouping-slice4-activity-log-decisions.md`(**A 확정 — 그룹 행 1줄**, 2026-09-04 오너).

## Scope

1. 경계 행렬 — 계획 §Slice 4 규칙/검증 문장 + 완료 기록 리터럴 + SoT v1.8.27 리터럴 ①~⑥을 should/should-NOT/리터럴로 전개해 셀 대응표를 만든다.
2. 구현 코드 감사 — `analysis/identity_group_review.py`(상태 기계 판정·closed 404·결과 분류·id 정렬)·`routers/analysis.py`(엔드포인트·owner 가드·활동 행 기록 조건·404 매핑)·`main.py`(조립 — 신규 `create_app` 파라미터 없음 주장)·`activity/actions.py`(분류표 등재)·프론트 `activityActions.ts`(라벨·비링크 사유).
3. 테스트 코드 감사 — 신규 10셀 각각의 단정이 계약 조항을 잠그는지(under/over 방향), RED 5 failed 산술.
4. 뮤테이션 — 구현자 표 9종 중 8종 재유도(정확한 diff로; M3만 미실행 — M4·M9가 같은 축 커버) + 검증자 신설 1종(VM-A).
5. probe 2종(미잠금 조항의 행동 실측): superseded skip·승격 멤버 거절 — 기록 옆 커밋.
6. 전수 회귀 재실행 + OpenAPI 독립 재덤프(operation 수·신규 path·오류 선언) + `schema.d.ts` 재생성 대조.
7. 프론트 기존 결함 2건 사전존재 실측(6cb6abc detached worktree).
8. 기록 감사 — SoT v1.8.27 행·README ①②③④·HANDOFF(착수점·분량 기록·프론트 결함 경고)·CHANGELOG·work_log 세션 4(변이 표·전수 1차 기각 사유).

## Methodology

환경(측정의 일부): WSL2(Linux 6.18.33.2-microsoft-standard-WSL2), Python 3.12.3 / pytest 9.0.2, test-mongo(`ai_writte_system-test-mongo-1`, 127.0.0.1:27020, rs-test replica set)는 검증 개시 시점에 **이미 healthy**(Up 7 hours — 구현 세션이 남긴 것; 세션 4 work_log "띄운 채 남김"과 일치). 이 머신 관례 skip 1 = chroma live. 전수 소요 2043.15초(부하 평균 6 하에서 — 세션 4 실측 1710.99초와 같은 축의 분산).

- 트리 게이트: `git status --short` empty — 개시 시·변이마다 복원 후 재확인(전부 통과). 대상이 커밋돼 clean하므로 clean-tree 분기(`git checkout -- <path>`).
- 집중: `python3 -m pytest -q tests/test_identity_group_reject.py` → **10 passed**.
- 변이(본 트리 6종 M1·M2·M5·M6·M8·M9): 전수 개시 **전에** 완료. 잔여 2종(M4·M7)은 전수 진행 중 `git worktree add --detach /tmp/s4_mut HEAD`에서 실행(본 트리 무손상 — 변이 창과 전수 창 분리, 세션 2 절차). VM-A 귀결 측정도 detached worktree(`/tmp/s4_vma`). 적용 diff는 §Findings 4 표. 판독은 요약줄 + `FAILED|SUBFAILED` 함께(M6의 SUBFAILED 포착).
- probe 2종: `repro_slice4_member_literals.py`(기록 옆 커밋) — P1 superseded skip·P2 승격 멤버 거절+canonical 잔존.
- OpenAPI: `python3 scripts/dump_openapi.py > /tmp/openapi_verify_s4.json` → operation 수·신규 path·responses 열거 실측. `schema.d.ts`는 gen:api 절차(`dump_openapi.py` → `openapi-typescript` 7.13.0)를 /tmp 출력으로 재실행해 커밋본과 `diff`.
- 프론트 사전존재: `git worktree add --detach /tmp/wt_6cb6abc 6cb6abc`(세션 시작 커밋)에서 `npx vitest run src/designTokens.test.ts src/typeScale.test.ts`(node_modules 심볼릭 링크 — 6cb6abc↔HEAD 의존성 무변).
- 전수: test-mongo healthy 확인 뒤 `python3 -m pytest tests/ -q`(백그라운드). **docs/ 편집은 전수 완료 뒤에만**(세션 3 절차 — 전수 창이 디스크의 문서 가드를 본다).

## Findings

### 1. 경계 행렬 — 계약 ↔ 셀 대응

계획 §Slice 4(규칙·검증 문장·완료 기록)와 SoT v1.8.27 리터럴 ①~⑥에서 유도한 분기의 대응:

| 계약 분기/리터럴 | 셀 |
|---|---|
| 전체 거절(needs_review 전 멤버 → rejected·응답 4키·검토함 비움) | 셀 1(전체 dict 동등성) |
| 응답 두 목록의 **후보 id 정렬**(어댑터와 무관한 결정성) | 셀 1(고정 클록·역순 added_at — M8 보강) |
| 일부 terminal skip + 나머지 거절 + skipped/rejected 싣기 | 셀 2(confirmed·rejected 2종) |
| 멱등 상태 유도 — 완료 그룹 재호출 no-op(같은 key 재전송=다른 key 재호출 붕괴) | 셀 3(replay 관측·행 수 2 유지) |
| unknown/cross-project/missing-project 404 | 셀 4·5·7 |
| **closed 그룹 404** | 셀 6(후보 무변까지) |
| **contradicted 허용** | 셀 8 |
| 활동 행 모양(그룹 행 1줄·`after`="rejected=N, skipped=M"·멤버별 행 부재) | 셀 9(행 수·target·`after` 리터럴) |
| **변경≥1일 때만 기록** | 셀 10(전후 목록 동등) |
| 401/403(owner 가드) | 기존 auth 전수 행렬(tier 75/101 카운트 갱신 — 자동 열거) |
| 멤버행 불변(거절 후에도 member 행 존재) | 셀 3이 결과로 잠금(replay skipped 전체 — 멤버행 삭제 시 공백으로 바뀜) |
| **terminal 전 종류 skip — superseded** | **빈칸(B1)** |
| **승격 무시 — 승격된 needs_review도 거절·canonical 잔존** | **빈칸(B2)** |
| 스토리지 503(전역 handler 상속) | 전역 핸들러 등록 셀(v1.7.38 축)·오류 선언 EXPECTED 22 — H1 참조 |

나머지는 전부 대응 셀이 있고, 변이 재유도(§4)가 셀 짝을 확인한다. **행렬의 빈칸 2곳 = 아래 B1·B2.**

### 2. 구현 코드 감사 — 계약 리터럴과의 일치

- 엔드포인트(`routers/analysis.py:892-929`): 경로·`_REQUIRE_PROJECT_OWNER`·`responses=_owned(_ERRORS_404)` 전부 계획 §Slice 4 범위 문장과 글자 일치. 활동 기록은 `if result.rejected:` 뒤 handler 본문에서(A7=A·N9의 분기 셀 요건 충족 — 셀 9·10이 행위 셀). `after` f-리터럴 `"rejected={n}, skipped={m}"`을 셀 9가 핀.
- 서비스(`identity_group_review.py`): 멤버 판정 `status is not NEEDS_REVIEW` 단일 비교(승격 참조 없음 — B2의 방어가 현재 구조적일 뿐: 서비스가 memory를 주입받지 않는다), closed→`CandidateIdentityGroupNotFoundError`, 결과 분류는 `result.idempotent_replay` 기반(auto_promote와 같은 방어선 — M2 관측 동등), 응답 `tuple(sorted(...))`.
- 조립(`main.py:1844-1851`): 신규 `create_app` 파라미터 **없음** 주장 확인 — 이미 주입된 `identity_groups`·`candidate_review`·`analysis`의 순수 조합이고 `register_analysis`에만 파라미터 추가.
- 분류표(`activity/actions.py`): `_REVIEW` 9→**10**(주석 갱신 포함), 전체 ActivityAction **28** 실측. 경로 문자열이 라우트와 일치 — M6의 SUBFAILED 키(`('…/groups/{group_id}/reject','post')`)가 전수 가드의 열거를 입증.
- 오류 선언(`tests/test_application_api.py` EXPECTED): 신규 행 `{401,403,404,503}`·카운트 21→**22** 실측. OpenAPI 덤프 responses {200,401,403,404,422,503}와 일치(422은 FastAPI 자동).
- 프론트(`activityActions.ts:50-51` 라벨 "정체성 그룹 거절"·`:81` 비링크 사유 "검토함 목록 안에만 있다") — 라벨 가드(`test_activity_ui_labels.py`)는 `set(labels) == LOGGED_OPERATIONS` 기계적 전수(28행)로 양방향 잠금(누락·과잉 모두 집합 불일치).
- 503 상속 전제: 전역 핸들러(`main.py:1773-1776`, `_STORAGE_ERRORS=(PyMongoError,)`) 등록 자체는 양방향 셀(`test_application_api.py:3100-3113`)이 잠금 — 이 슬라이스가 새 에러 처리 코드를 만들지 않았으므로 상속은 구조적으로 성립.

### 3. 테스트 코드 감사

10셀 전부 읽었다. 단정은 전부 공개 면(HTTP 응답 dict·활동 API 행)을 겨냥한다. 셀 1·2·3은 전체 dict 동등성(키 누락·과잉 양방향). 셀 1의 `_FixedClock`+역순 added_at은 **결정성 잠금의 핵심 보강**이다 — 구현자가 M8 1차 관측 동등(in-memory 순차 id+ms 절단 동률이 아이디 tie-break로 붕괴)을 발견하고 `1b41177`·`227aeb4`로 넣었고, 재유도에서 sorted() 제거가 셀 1을 물었다(§4). RED 선행 "행동 셀 5 failed"도 산술로 정확하다 — 라우트 부재 시 POST가 404를 반환하므로 404 기대 셀 4종(unknown·cross·closed·missing)은 통과하고, 200/활동 행을 기대하는 셀 1·2·3·8·9만 실패한다(셀 10은 라우트 없이도 before==after로 우연 통과 — 라우트 생긴 뒤에만 의미 있음, H2).

### 4. 뮤테이션 재유도 — 구현자 표 9종 중 8종 + 검증자 1종

| 변이 | 적용 diff | 실측 | 구현자 표 |
|---|---|---|---|
| M1 상태 필터 반전 | `is not NEEDS_REVIEW` → `is NEEDS_REVIEW` | **5 failed**(full·terminal·replay·contradicted·활동행) | 5셀 ✓ |
| M2 무조건 rejected 분류 | `if result.idempotent_replay: …else: …` → `rejected.append(candidate.id)` 1줄 | **10 passed(관측 동등)** | ✓ 방어선 |
| M4 closed→OPEN-only | `is CLOSED` → `is not OPEN` | **1 failed**(contradicted) | 1셀 ✓ |
| M5 항상 기록 | `if result.rejected:` → `if True:` | **2 failed**(no-op 무기록·replay) | 2셀 ✓ |
| M6 action 리터럴 | `action="identity_group_rejected"` → `"candidate_rejected"` | **2건**(활동행 FAILED + 분류표 literal **SUBFAILED** — 키 `('…/groups/{group_id}/reject','post')`) | 2건 ✓ |
| M7 replay 항상 False | `return not self.rejected` → `return False` | **1 failed**(replay) | 1셀 ✓ |
| M8 sorted 제거 | `tuple(sorted(x))` → `tuple(x)` 양쪽 | **1 failed**(full — 보강 셀) | ✓ |
| M9 404 매핑 제거 | except 튜플에서 `CandidateIdentityGroupNotFoundError,` 제거 | **3 failed**(unknown·cross·closed) | 3셀 ✓ |
| **VM-A(검증자)** skip 열거에서 superseded 제외 | `is not NEEDS_REVIEW` → `in (CONFIRMED, REJECTED)` | **10 passed** → **B1 입증** | (표에 없음) |

M3(closed 체크 제거)만 미실행 — M9가 같은 셀(closed 404)을 다른 방향에서 이미 물고 M4가 closed/contradicted 축을 커버한다. 복원 후 `git status --short` clean 매번 확인.

### 5. probe — 미잠금 조항의 행동 실측(B1·B2)

`repro_slice4_member_literals.py`(기록 옆 커밋, 선례 `repro_rationale_out_of_roster.py` 모양 — 폐쇄 셀 본체로 이식 가능):

- **P1(superseded skip)**: 그룹 {a, b}에서 b를 edit(원본 superseded·승격 후보는 그룹 밖 신규 id) → 거절 → **200, rejected=[a], skipped=[b]** — 계약대로.
- **P2(승격 무시)**: `memory.promote_candidate`(AUTO_THRESHOLD)로 a 승격(상태 needs_review 유지 — `memory/service.py:181` "a promoted candidate still carries `needs_review` status"가 도메인 문서로 명시) → 거절 → **200, rejected=[a,b], skipped=[]·canonical 잔존** — 계약대로.
- **VM-A 귀결 실측**(detached worktree): VM-A 하에서 superseded 포함 그룹 거절은 `InvalidCandidateStateTransition: cannot transition candidate from superseded to rejected`가 라우터 catch(404 3종만) 밖으로 새어 나간다 — 개별 reject 라우트는 이 예외를 409로 잡지만(`routers/analysis.py:343` 등 4곳) 그룹 라우트는 잡지 않는다. 즉 과잉 교정이 배치 mid-flight로 요청 전체를 죽여도 suite는 침묵한다.

### 6. 전수·OpenAPI·생성물

- 집중: **10 passed**. 라벨 가드 6 passed/41 subtests. OpenAPI 독립 재덤프: **총 101 operation**, 신규 path 존재, responses {200,401,403,404,422,503}.
- `schema.d.ts`: gen:api 절차 재실행(openapi-typescript 7.13.0) → 커밋본과 **diff IDENTICAL**.
- 전수(test-mongo healthy 개시·문서 편집 전 창): **2768 passed / 1 skipped / 3159 subtests, exit 0, 2043.15초** — 구현자 실측(2768/1/3159, 1710.99초)과 수치 완전 일치(소요만 부하 차이). 검산: 2758(Slice 3 기준선)+10셀=2768 ✓, skip 1=chroma 관례 ✓, 3135+24=3159(신규 operation의 auth 행렬·분류표·라벨·오류 선언·문서 인덱스 열거 subtest) ✓.

### 7. 프론트 기존 결함 2건 — 사전존재 실측

6cb6abc detached worktree에서 `npx vitest run src/designTokens.test.ts src/typeScale.test.ts`: **동일 2 failed**(designTokens "defines every custom property it consumes"·typeScale "keeps the migration list identical…", `expected […(49)] to deeply equal […(54)]`까지 work_log 기술과 동일). 세션 시작 이전 결함 확정 — 구현자가 "고치지 않고 기록으로 남겼다"는 처리(Slice 6 착수 전 확인)는 적절하다.

### 8. 기록 감사

- SoT v1.8.27 행: 리터럴 ①~⑥·셀 10·변이 8/9·전수 2768/1/3159·구현 커밋 열거 — 실측과 무불일치.
- README ①(plans 98→99·"계획 · 결정 브리프 인덱스 (119)")·②(2768/3159)·④(v1.8.27) ✓. HANDOFF: 착수점 Slice 4 완료 서술·분량 기록 768→769(+1, 검수 미달 사유 명시)·프론트 결함 경고 ✓. CHANGELOG 행 ✓. plans README: 브리프 행(확정 A)·페이즈 상태 Slice 0~4 ✓.
- work_log 세션 4: 변이 표 9종 — 재유도 8종 전부 셀 짝 일치. "전수 1차 6 failed = 등재 누락(문서 인덱스 5+오류 선언 1) 후 재실측" 처리는 측정 오염 기각의 정당한 선례(세션 1의 mongo 경합 기각과 같은 축)이고 최종 수치를 정본으로 명시했다.

## Issues / Risks

### Blocking (계약 의무)

- **B1 — 리터럴 ① "terminal 전 종류 skip"의 superseded 값이 무셀.** 셀 2는 confirmed·rejected만 시드한다. 검증자 변이 VM-A(skip을 `in (CONFIRMED, REJECTED)` 열거로 바꾸는 과잉 교정)이 **10 passed** — 이 방향을 잡는 셀이 없다. 귀결: superseded 멤버 포함 그룹(도달 가능 — edit가 원본을 superseded로 남긴다, Slice 3 H2 셀이 같은 상태를 읽기면에서 이미 시드)이 미처리 예외로 배치 중단. **폐쇄: probe P1을 기명 셀로 이식 + VM-A 재실측으로 물림 확인.**
- **B2 — 리터럴 ① "승격 여부는 보지 않는다"가 무셀.** 승격된 needs_review 멤버의 거절(+canonical 잔존)을 잠그는 셀이 이 파일에도, 개별 reject 경로에도 없다(전 suite 검색 — "같은 면" 상속 불성립). 방어가 현재 구조적일 뿐이다(서비스가 memory를 주입받지 않음 — 주입해서 검사를 넣는 날 아무 셀도 물지 않는다). 도달 가능 상태는 도메인 문서가 명시한다(`memory/service.py:181`). **폐쇄: probe P2를 기명 셀로 이식 + (가능하면) 승격 스킵 변이 재실측.**

### Hardening recommendations (비차단)

- **H1 — mid-loop 스토리지 실패 → 503·재호출 이어가기 셀.** SoT 리터럴 ⑤의 "재호출이 끝난 멤버를 skip하며 이어간다"는 부분이 skip 셀·개별 멱등 셀에서 **유도적**으로 성립한다(직접 셀 없음). 전역 503 핸들러 등록 셀은 있으나(v1.7.38 축) 그룹 루프를 관통하는 발화 셀은 없다. Slice 5(단계별 진행 저장) 착수 시 스펙이 근접하므로 그때 함께 볼 것을 권고.
- **H2 — RED의 우연 통과 표시.** 셀 10(no-op 무기록)은 라우트 부재 상태에서 before==after로 우연 통과한다(구현자 RED 기록 5 failed의 산술과 정확히 일치하므로 구현자는 정확히 알고 있었다) — 셀 3이 먼저 거절을 완료하는 순서 의존이 이미 문서화돼 있어 조치 불필요, 기록만 남긴다.

## Verdict

**조건부 합격** — B1·B2(리터럴 ①의 superseded skip·승격 무시 잠금 부재)를 기명 셀 2개로 닫을 것. 행동은 전부 계약대로이고(§5 probe), 구현·기록·회귀 주장 전부가 재현됐다(§2~§4·§6~§8). 잠금 부재는 Slice 1·2·3 B1과 같은 모양이며 폐쇄 후 Slice 5(그룹 승인 — 활동 로그 모양이 이번 A안에 묶여 있다) 착수 가능하다.

## Outstanding items

- B1·B2 폐쇄 세션이 필요하다(셀 2개 + VM-A 재실측; probe가 본체). 폐쇄 전 Slice 5 착수는 보류 권고.
- 프론트 기존 결함 2건(typeScale 49↔54·designTokens `--type-body`)은 이 슬라이스 밖 — Slice 6 착수 전 선행 확인(구현자 기록 유지).
- 푸시는 오너 몫. test-mongo는 띄운 채 남긴다(다음 세션 관례).
- 검증 기록 인덱스 등재 후 `test_docs_indexes` green 확인과 같은 커밋.

## Reproduction

```bash
# 전제: test-mongo healthy(docker compose -f docker-compose.test.yml up -d 후 대기)
git status --short                      # empty 확인
python3 -m pytest -q tests/test_identity_group_reject.py        # 10 passed
python3 docs/verifications/2026-09-04/repro_slice4_member_literals.py
# → PROBE-OK 2행(B1·B2 행동)

# OpenAPI/생성물
python3 scripts/dump_openapi.py > /tmp/o.json
python3 -c "import json;s=json.load(open('/tmp/o.json'));print(sum(len(m) for m in s['paths'].values()))"  # 101
cd frontend && python3 ../scripts/dump_openapi.py > openapi.json && \
  ./node_modules/.bin/openapi-typescript openapi.json -o /tmp/s.d.ts && diff /tmp/s.d.ts src/api/schema.d.ts
# → IDENTICAL

# VM-A(B1 입증; 복원 절차 주의 — CLAUDE.md §6)
python3 - <<'EOF'
p='services/application/app/analysis/identity_group_review.py';s=open(p).read()
s=s.replace("if candidate.status is not AnalysisCandidateStatus.NEEDS_REVIEW:",
            "if candidate.status in (AnalysisCandidateStatus.CONFIRMED, AnalysisCandidateStatus.REJECTED):")
open(p,'w').write(s)
EOF
python3 -m pytest -q tests/test_identity_group_reject.py        # 10 passed = 무셀 입증
git checkout -- services/application/app/analysis/identity_group_review.py

# 프론트 사전존재
git worktree add --detach /tmp/wt 6cb6abc && ln -s "$PWD/frontend/node_modules" /tmp/wt/frontend/node_modules
cd /tmp/wt/frontend && npx vitest run src/designTokens.test.ts src/typeScale.test.ts   # 2 failed

# 전수
python3 -m pytest tests/ -q
```
