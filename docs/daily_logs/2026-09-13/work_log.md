# 2026-09-13 작업 로그

## 세션 76 — 승격 기록 선재 5건 판정 줄 정합 + 미수리 둘(HA-1·HP-1) 폐쇄 (오너 지시 "인덱스 합격인 애들 본문 업데이트 해주고 미수리 부분 작업 진행해줘")

### Goals

- `88a16fe`(세션 75 재감사)가 부채로 등재한 **"인덱스 판정 열 합격 ↔ 본문 판정 줄 조건부 합격"** 선재 5건을 선례 모양으로 올린다.
- 같은 재감사가 남긴 미수리 둘을 닫는다 — **HA-1**(휴면 절 가드의 실효 앵커가 한 낱말) · **HP-1**(수동 저장 replay 특성 셀이 행의 정체를 안 본다).
- 산출을 독립 검증 서브에이전트에 넘긴다.

### 전제 — 같은 트리에서 다른 검증 AI가 동시에 돌고 있다

오너가 두 축을 나눠 맡겼다. 다른 세션이 `docs/verifications/2026-09-12/activity_replay_c1_promotion_audit.md` 의 판정 승격을 진행 중이고 **작업 중 그 파일이 미커밋으로 나타났다**(본 세션 시작 시점에는 트리 clean이었다). HANDOFF 함정 절 그대로 대응했다:

- 그 파일 **무접촉** — 읽지도 고치지도 스테이징하지도 않았다.
- **변이는 전부 탈치 워크트리**(`scratchpad/mut`, `5a8e8c7` detached)에서 돌렸고 **본 트리에 `git checkout`·`restore`·`stash`·`reset` 을 한 번도 쓰지 않았다.**
- 스테이징은 **경로 명시**만(`git add <경로>` — `-A`·`.` 미사용).

### Completed work

#### 1. 선재 5건 본문 판정 줄 정합 (`a1d71fc`)

선례는 `2e025dc`(세션 73이 4/4로 처리한 모양)다 — **두 자리**를 고친다: 문서 머리에 최종 판정 한 줄, Verdict 섹션 선두 토큰 승격, **발행 시점 원문은 인용으로 보존**.

| 기록 | 조건 | 폐쇄 커밋 | 승격 근거 |
|---|---|---|---|
| `2026-09-11/landing_l2_terms_privacy.md` | LB1 | `7be433e`(SoT v1.8.57) | `2026-09-12/landing_l2_promotion.md` |
| `2026-08-20/mypy_guard_slice.md` | B1 | `5182cad` | `2026-08-20/mypy_guard_closure.md` |
| `2026-08-20/embedding_adapter_slice.md` | B1 | `a9bca6d` | `reranker_slice.md` §Findings 7 |
| `2026-08-20/reranker_slice.md` | C1 | `92b9b24` | `2026-08-21/reranker_c1_h1_h2_closure.md` |
| `2026-08-23/llm_key_fallback_slice.md` | B1 | `d71294a`·`b2be4ad` | 같은 기록 §사후 재검 |

인덱스 판정 열은 **원래 전부 합격**이었으므로 판정 분포(211/95/5)는 무변이고, 문서 수도 안 늘었다(문서 가드 **29 passed / 952 subtests** — 기준선 일치).

#### 2. HA-1 — 휴면 절 가드의 앵커 실효화 (`5a8e8c7`, `tests/test_docs_indexes.py`)

`test_the_dormant_section_says_what_the_old_name_was` 의 docstring 은 `verifications/`·`전신` **두 낱말**을 앵커로 잡았다고 적었으나, 휴면 절(`docs/README.md`) 안에 `verifications/` 가 **네 번 더** 나와 실효 앵커는 `전신` 하나였다.

처방: 앵커 범위를 **절 전체 → `verification_briefs/` 로 시작하는 불릿 행 하나**로 좁혔다. 근거는 범위 축소 자체가 아니라 **오너 지시의 내용**이다 — 지시가 요구한 것은 낱말의 존재가 아니라 *두 이름의 관계*("`verification_briefs/` 는 `verifications/` 의 전신")이므로 둘은 애초에 **같은 행**에 있어야 한다.

#### 3. HP-1 — 수동 저장 replay 행의 정체 단정 (`5a8e8c7`, `tests/test_activity_api.py`)

`test_resending_the_same_save_key_still_records_a_second_row` 가 행 **수**만 세어, replay 가 엉뚱한 action 을 남겨도 전건 초록이었다. 첫 저장 축의 짝(`test_the_first_final_save_is_recorded`)과 같은 모양으로 마지막 행의 `action`·`target_type` 을 함께 단정했다.

**★ 이것은 하드닝이지 계약 확장이 아니다.** 세션 75 재감사가 정정한 대로 계약(SoT v1.8.64 · HANDOFF §활동 로그)이 요구하는 것은 *행을 남기는가* 와 `idempotent_replay` 둘뿐이고 **replay 행의 action 리터럴은 계약 침묵**이다. docstring 에 그 사실을 적어 두었다 — 오너 D2=ⓑ 면 이 셀 자체가 뒤집힌다.

### 변이 표

전부 탈치 워크트리 `scratchpad/mut`(`5a8e8c7` detached). 각 변이마다 **앵커 `count == 1` 단정 → `shutil.copy2` 백업 → `pathlib.write_text` 치환 → 초점 실행 → 백업 복원 → `cmp` 바이트 대조 → `git status --short` 빈 것 확인**. `sed -i`·`perl -i` 미사용(저장소 규칙).

| 변이 | 적용한 diff | 파일 | 결과 | 기명 셀 |
|---|---|---|---|---|
| **MA**(under) | `**[\`verifications/\`](verifications/README.md) 의 전신이고` → `**앞선 관행의 전신이고` (해당 행에서만 `verifications/` 제거, `전신` 유지) | `docs/README.md:7` | **1 failed** / 19 passed · 324 subtests | `test_the_dormant_section_says_what_the_old_name_was` |
| **MA-over** | `의 전신이고 더는 쓰지 않는다` → `의 전신이며 지금은 쓰지 않는다`(수사만, 두 낱말 유지) | `docs/README.md:7` | **20 passed** / 324 subtests | — (의도대로 안 문다) |
| **MB**(under, 비분리) | `action="draft_version_saved", target_type="draft_version",` → `action="draft_version_touched", …` | `routers/drafts.py:652` | **2 failed** / 19 passed | `test_resending_the_same_save_key_still_records_a_second_row` · `test_saving_a_draft_version_records_who_and_when` |
| **MB2**(under, 분리 증명) | 같은 자리를 `action=("draft_version_touched" if result.idempotent_replay else "draft_version_saved"),` 로 — **replay 경로만** 다르게 | `routers/drafts.py:652` | **1 failed** / 20 passed | `test_resending_the_same_save_key_still_records_a_second_row` (실패 지점 `test_activity_api.py:214` = 이번에 더한 단정) |

**MA 가 폐쇄의 핵심이다** — 세션 75 재감사가 이 방향을 *"`verifications/` 만 걷으면 조용하다(20 passed)"* 로 실측했던 자리이고, 이제 **1 failed** 다.

**MB 는 분리 증명이 안 된다**(첫 저장 축도 함께 문다). HP-1 이 지적한 결함은 *"replay 만 엉뚱한 action 을 남기는"* 경우이므로 **MB2 로 다시 쟀고, 정확히 1실패 = 이번에 더한 단정 줄**이었다. 변이 하나로 끝내지 않은 이유가 이것이다.

### Issues found

- **부채 서술이 다섯을 한 덩어리로 묶었으나 실제로는 두 등급이었다**(편집 전 상태 실측).
  - **승격 사실이 본문에 아예 없던 것은 `landing_l2_terms_privacy` 하나**뿐이다(판정 줄도 뒤 문단도 승격을 안 적고, 폐쇄 보고 절만 따로 있었다).
  - 나머지 넷은 승격이 **이미 본문에 명시돼 있었다** — `embedding_adapter_slice`·`reranker_slice`·`llm_key_fallback_slice` 는 판정 **같은 줄**에 `**[→ 승격 … · 판정 합격]**`, `mypy_guard_slice` 는 판정 바로 아래 **인용 블록**에 `**★ 승격 — 합격**`.
  - 즉 갈라져 있던 것은 승격 사실이 아니라 [`guides/verification.md`](../../guides/verification.md) §Required sections 가 요구하는 **판정 줄의 선두 토큰**이다. 실질 위험(정규식 분류가 흔들린다)은 그대로지만 정도가 다르므로 커밋 메시지와 이 로그에 정정을 남긴다.
- **`mypy_guard_slice.md` 는 발행 세션이 *"발행 시점 문구는 그대로 둔다"* 고 본문에 선언한 자리**다. 선례 모양은 원문을 인용으로 보존하므로 그 선언과 **양립**한다고 판단했다 — 원문은 한 글자도 지우지 않고 인용 블록 안으로 옮겼을 뿐이다.

### Decisions — User Decisions and Rationale

- **오너 지시**: 다른 검증 AI가 감사 기록 승격을 맡았으니, 이 세션은 **인덱스 합격 건들의 본문 업데이트 + 미수리 작업**을 하고, 끝나면 **서브에이전트 하나를 스폰해 검증하고 보강까지** 한다. 다른 검증 AI가 돌고 있다는 사실을 서브에이전트에게도 알린다.
- **범위 판단**: "미수리 부분"을 미수리 표 전체가 아니라 **세션 75가 새로 등재한 둘(HA-1·HP-1)**로 읽었다. 표의 나머지 행은 오너 결정 대기(프론트 `detail` 분기·자료 길이 상한 등)이거나 트리거 대기다.
- **HP-1 을 D2 결정 전에 닫은 이유**: 처방이 한 줄이고, 지금 잠그는 것의 값은 *replay 가 엉뚱한 action 을 남기는 회귀*를 막는 것이다. D2=ⓑ 가 되면 이 셀은 어차피 그 슬라이스가 뒤집는다(특성 셀의 성질). 대신 **계약 침묵임을 docstring 에 명시**해 다음 사람이 이것을 "옳은 동작"으로 읽지 않게 했다.

### Verification

- 초점 회귀: `python3 -m pytest tests/test_activity_api.py tests/test_docs_indexes.py tests/test_repo_hygiene.py -q` → **50 passed / 952 subtests**.
- 문서 가드만 따로: **29 passed / 952 subtests** — HANDOFF 기준선 줄의 952 와 일치(문서 수 무변).
- **백엔드 전수는 돌리지 않았다** — 같은 트리에서 다른 AI가 작업 중이라 과부하 오탐이 난다(HANDOFF 함정). 이 세션의 work_log·검증 기록이 문서 가드 subtest 를 늘리므로 **기준선 갱신은 그 문서들이 확정된 뒤의 몫**이다.
- 프런트 무변(이 슬라이스는 백엔드 테스트·문서만 건드렸다).
- 독립 검증은 **서브에이전트 세션**에 넘겼다(대상 `a1d71fc`·`5a8e8c7` + 이 기록 커밋).

### Next steps

- 서브에이전트 독립 검증 결과 반영(보강 포함).
- 감사 기록 `activity_replay_c1_promotion_audit.md` 의 판정 승격은 **다른 검증 AI 몫**이다 — 이 세션은 무접촉.
- 기준선 줄(3063/1/4229) 갱신은 양쪽 세션의 문서가 확정된 뒤 한 번에.

## 세션 77 — 재감사 조건 AC1 승격 재검: activity_replay_c1_promotion_audit.md 판정 승격 (오너 지시 "작업좀 하자. 감사기록 승격이고 검증확인해줘. 보강이 필요하다면 서브 에이전트 스폰해서 독립적으로 보강해주고. 다른 ai가 다른 작업 할꺼니까 놀라지 말고 서브 에이전트 활용할꺼면 그 애 한테도 알려주고")

### Goals

- 유일하게 열려 있던 검증 축 — 재감사 기록 `2026-09-12/activity_replay_c1_promotion_audit.md`(조건부 합격, 조건 AC1: 인덱스 판정 열 ↔ 선행 기록 본문 판정 줄 불일치)의 판정 승격을 독립 세션에서 확정한다.
- 오너 지시 변이 재적용 대상: 그 기록의 **MA-2~MA-5**(휴면 절 가드 경계 넷) + **재현된 MP-1~MP-11b 중 표본**.
- 병행 AI 작업(공유 트리 — 위 세션 76)에 간섭하지 않는다.

### 전제 — 세션 번호와 충돌

이 파일을 먼저 쓴 세션이 "세션 76"을 자칭했다(선재 5건 정합 `a1d71fc` · 미수리 둘 `5a8e8c7` — 위 기록). 이 세션은 **세션 77**로 등재한다. 감사 기록 승격 담당을 세션 76 기록이 "다른 검증 AI 몫 — 무접촉"으로 명시했으므로 역할 분담은 성립한다.

### Completed work

- **AC1 폐쇄 확인(세 층)**: ① `git show 88a16fe` — 선행 기록 `activity_replay_and_dormant_docs.md` 머리 요약 줄·§Verdict 줄 둘 다 승격, 발행 시점 판정 원문은 두 자리 모두 인용 보존(선례 `2e025dc` 모양). ② 인덱스 311행 판정 열 ↔ 본문 선두 토큰 전수 대조 — **병 0건**(선두 토큰 있는 91건 기준 · 옛 영어 병기 220건은 폐쇄 보고가 지정한 범위 밖). ③ 폐쇄 보고가 부채로 등재한 선재 5건은 `a1d71fc`(세션 76)가 정합.
- **변이 재적용 열 회 — 전건 일치**(탈치 워크트리 `/tmp/verify_ac1`, `88a16fe` detached · 원복 규약: 앵커 count==1 단정 → copy2 백업 → 치환 → 초점 실행 → 복원 → 바이트 동일성 단정 → `git status` 확인 · `sed -i`/`perl -i` 미사용):

| 변이 | diff 요약 | 위치 | 재실패 셀(기명) |
|---|---|---|---|
| MP-1(=MB-8) | `if result.saved is not None:` → `… and not result.idempotent_replay:` | `routers/writing.py:1368` | 1 failed · `WritingAcceptApiTest::test_resending_the_same_accept_key_still_records_a_second_row` |
| MP-2(=MB-9) | 수동 저장 `activity.record(` 블록을 `if not result.idempotent_replay:` 로 감쌈 | `routers/drafts.py:650` | 1 failed · `ActivityRecordingTest::test_resending_the_same_save_key_still_records_a_second_row` |
| MP-3(=MV-1) | finalize `if not finalized.idempotent_replay:` → `if True:` | `routers/drafts.py:706` | 1 failed · `ActivityRecordingTest::test_resending_the_same_final_save_key_leaves_no_second_row` |
| MP-7 | 지시 문장을 두 낱말(`verifications/`·`전신`) 보존해 다듬음 | `docs/README.md:43` | 없음(초록 — over 확인) |
| MP-8b | `KEY_REPLAY_ACTIONS["writing_accept"]` `"handler"`→`"consume"` | `quota/dedupe.py:92` | 2 failed · `KeyConsumptionTest` 두 셀 |
| MP-11b | 절 제목 → `## 휴면 디렉터리 (보존)` | `docs/README.md:37` | 없음(초록) |
| MA-2 | 지시 문장에서 `verifications/` 낱말만 제거(`전신` 유지) | `docs/README.md:43` | 없음(초록 — HA-1 사각 재현. `5a8e8c7` 이후로는 1 failed — 세션 76 MA 실측) |
| MA-3 | 절 제목 꼬리 통째 제거 | `docs/README.md:37` | 없음(초록) |
| MA-4 | 절 제목 접두 뒤 글자 추가 | `docs/README.md:37` | 없음(초록) |
| MA-5 | 절 제목 접두 내부 공백 추가 | `docs/README.md:37` | 1 failed · `DocsReadmeIndexTest::test_the_dormant_section_says_what_the_old_name_was` |

- **기준선(`88a16fe` 트리)**: 문서 가드 20/324(감사의 323 에서 +1 = 감사 기록 등재분) · 두 파일 77/19 · 넓은 셋 237 passed + 1 skipped / 694(skip = 이 호스트 Mongo 미도달 — 감사의 "238"은 passed+skip 합산 · 셀·서브테스트·기명 셀 무변) · quota 54/2.
- **판정 승격**: 감사 기록 머리·§Verdict 둘 다 `**합격**`(감사 자신의 HA-2 처방대로 세 토큰으로 시작) + 발행 시점 원문 인용 보존 · 인덱스 70행 판정 열·요약 셀 갱신 · 신규 기록 `docs/verifications/2026-09-13/activity_replay_ac1_promotion.md`(합격) 등재.
- **수치 갱신**: 검증 기록 311→312건 · 72→73일치 · 분포 213/94/5(조건부 30%) · 기준선 4,229→**4,232**(문서 가드 둘 952→**955** — 이 기록 +2 · 오늘 work_log 신규 파일 +1[세션 76 과 공유] · passed 무변) — HANDOFF·루트 README(②행·분포 산문)·docs/README·검증 인덱스·CHANGELOG. HANDOFF 부채 표(선재 5건)는 병 0건·처방 ⓑ(대조 셀)만 남은 것으로 정리했고, "판정 승격은 다음 세션 몫" 문단을 완료 처리했다.

### Issues found

- **변이 재적용 결과 오염 측정 함정(실측)**: 문서 가드를 돌릴 때 미갱신 수치로 2셀이 실패하면 pytest-subtests 의 `SUBFAILED` 가 *passed subtests 카운트에서 빠져* 954 로 읽혔다 — 같은 트리에서 전부 초록인 상태의 실측은 **955** 다(955-952=+3 산술과 정확히 일치). 실패가 섞인 실행의 subtests 합계를 기준선으로 적지 말 것.
- **work_log 세션 번호 충돌**: 이 파일에 세션 76(병행 세션) 기록이 먼저 실렸다 — 이 세션은 77 로 등재했다. 병행 세션의 `5a8e8c7` 이 이 세션의 검증 중 커밋으로 확정되면서, 재검 기록의 "병행 세션 보강 중" 서술을 폐쇄 확정으로 정정했다.
- 감사 환경과 이 세션의 호스트 Mongo 도달 차이(넓은 셋 skip 1) — 수치가 아니라 라벨 문제였고 기록에 환경을 명시했다(가이드 §"Recording a measurement").

### Decisions

- **서브에이전트 스폰 안 함** — 오너이 조건부로 허용한 "보강이 필요하다면"의 사유가 생기지 않았다: 변이 열 회 전건 일치, 전수 대조 병 0건, 기준선 산술 성립. 보강 대상 없음. (세션 76 은 자기 산물 검증을 위해 서브에이전트를 쓴다고 기록해 두었다 — 오너 지시의 "그 애 한테도 알려주고"는 그 세션이 이미 이행 중이다.)
- **승격 문구는 감사 자신의 처방(HA-2)을 따름** — 선례 넷의 `**최종 판정은 합격이다**` 대신 `**합격**` 토큰으로 시작(가이드 §Required sections 의 세 토큰 규칙). 폐쇄 보고가 선행 기록에 쓴 모양과 이번 승격 모양이 다르지만 둘 다 인덱스와 같은 말을 하므로 병이 아니다.

### Next steps

- 남은 검증 승격 백로그 없음(이 재검으로 종결). 열린 부채는 HANDOFF 부채 표 참조 — 본문↔인덱스 대조 셀(처방 ⓑ), HA-2 머리 줄 통일(선례 넷), H1 남은 절반·H2·H4·HP-2. 세션 76 이 HA-1·HP-1 을 `5a8e8c7` 로 닫았다(그 산출의 독립 검증은 그 세션의 서브에이전트 몫).
- 오너 결정 대기 두 건 그대로: 활동 로그 D2(replay 행 action 처분) · 파기 청구 뒤 탈퇴 취소 경계.
