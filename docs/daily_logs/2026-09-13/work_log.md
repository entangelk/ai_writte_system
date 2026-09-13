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

### 독립 검증 결과 (서브에이전트 세션 — 판정 **합격**)

기록 [`promotion_alignment_and_ha1_hp1_closure.md`](../../verifications/2026-09-13/promotion_alignment_and_ha1_hp1_closure.md) · 보강 `d3ef8cd`·`3681d77`.

- **승격 귀속 다섯 건 전부 1차 자료에서 재유도됨** — 근거 없이 올라간 것 0건. 원문 보존도 바이트 대조로 손실 0(두 줄짜리 `llm_key` 포함). `mypy_guard_slice` 의 *"발행 시점 문구는 그대로 둔다"* 선언과도 **양립** 판정(고쳐 쓴 게 아니라 덧붙였고, 그 선언이 지키려던 *"판정을 사후에 고쳐 쓰지 않는다"* 는 그대로다).
- **변이 넷 전건 재현 + 폐쇄 전 리비전 양단 대조로 갭 실재 증명** — MA 는 `a1d71fc` 에서 20 passed(조용) → `5a8e8c7` 에서 1 failed, MB2 는 폐쇄 전 50 passed(조용) → 폐쇄 후 1 failed.
- **★ 내 처방이 낳은 사각을 검증이 찾았다(MS-4)** — 내가 의심한 "불릿 모양 의존"은 구멍이 아니었고(MS-1·2·3 전부 `assertIsNotNone` 이 뭄), 진짜 사각은 **`next()` 가 "그 행"이 아니라 "첫 행"을 고르는 것**이었다. 미끼 `- ` 행을 앞에 끼우면 앵커가 조용히 옮겨 간다. docstring 의 *"범위는 … 행 하나"* 가 실제보다 한 칸 강했다. **검증이 직접 닫았다**(후보를 모아 정확히 하나임을 먼저 단정 — 재측 MS-4 1 failed · MA 1 failed 유지 · MA-over 20 passed 유지).
- **신규 MB3** — `target_type` 만 replay 경로에서 바꾸는 변이도 **1 failed**(폐쇄 전 조용). 내가 더한 두 단정이 **각각** 실효다.
- **D2 선점 아님**(검증의 정직한 판정) — 세 층으로 확인됐다: `draft_version_saved` 는 `activity/actions.py:95` 택소노미 등재 리터럴이고 · 같은 축 첫 저장 셀이 이미 같은 리터럴을 핀하며 · D2 가 정하는 것은 행의 **존재 여부**라 D2=ⓑ 면 `len(events) == before + 1` 부터 뒤집혀 새 두 줄은 셀과 함께 사라진다. **다만 재감사가 HP-1 을 "D2 와 같은 자리"로 묶어 둔 배치를 단독으로 푼 것은 사실이므로 오너에게 통지한다.**
- **내가 틀린 것 셋**(전부 비차단, 검증이 `d3ef8cd` 로 정정): ① `landing_l2_terms_privacy.md:97` 의 *"위 Verdict 는 조건부 합격 그대로"* 가 승격 뒤 자기 Verdict 와 충돌 — **내 편집이 만든 것**이다(편집 전엔 참이었다. 같은 병 선재 둘도 함께 정정) ② HA-1 docstring 의 범위 주장이 실제보다 강함(MS-4) ③ HP-1 docstring 이 짝 셀로 `test_the_first_final_save_is_recorded` 를 들었으나 그것은 **finalize 축**이고, 같은 수동 저장 축의 짝은 `test_saving_a_draft_version_records_who_and_when`(내 MB 가 물린 바로 그 셀)이다.

### 기준선

문서 가드 둘 양단 실측 **952(`5a8e8c7`) → 953(`9ccf9c7`) → 955(`1f4f95a`)** 가 HANDOFF **4229 → 4232** 와 일치하고, 검증 기록 등재분 +2 로 **4234**. `passed` 무변(셀 증가 0 — 새 단정은 기존 셀 안에 들었다) · `--collect-only` **3064** · 프런트 무변.

### Next steps

- **오너 결정 대기 신규 하나** — 검증이 코퍼스 전수로 찾은 **폐쇄 해시 선재 377종 미해소**(2026-08-23 `git filter-repo` 이력 재작성 잔여 · 구간별 해소율 65/66 · **1/264** · 269/272 로 경계가 칼같다). 처방 후보는 `docs/verifications/README.md` 머리 한 줄인데 **코퍼스 전체에 닿는 주장이라 임의로 적지 않았다**(미수리 표 등재).
- **D2 통지** — HP-1 폐쇄로 D2=ⓑ 때 함께 뒤집힐 줄이 둘 늘었다.
- 남은 미수리 표 항목은 전부 오너 결정 또는 트리거 대기다.

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

## 세션 78 — 오너 결정 셋 시행: 활동 로그 D2=ⓑ · 파기 뒤 취소 거부(ⓐ) · 옛 해시 주석(ⓒ)

### Goals

- 오너가 답한 셋을 같은 날 시행한다. **셋 다 브리프에 추천이 이미 있었다.**

### ★ 오너 피드백 — 브리프가 답한 것을 되묻지 마라

세 건을 브리프째 정리해 물었더니 오너가 명시적으로 지적했다: *"재시도가 사용자에게 보일 필요가 없잖아… 저번에도 얘기했던 건데 당연히 ⓑ고"* · *"파기가 됐다는 건 30일 지난 후잖아. 그때 탈퇴 취소는 당연히 되면 안 되지. 알아서 해"* · *"결정3은 이걸 왜 물어봐? 기록이잖아"* · *"바보 아니고 당연한 것들 물어보면 내가 어떻게 해야 하냐"*.

**셋 다 브리프 §Recommendation 이 이미 그 답을 지목하고 있었다.** 물어본 것 자체가 오너의 시간을 쓴 순비용이었다. 규칙으로 남긴다 — **브리프에 추천이 있고 그 추천이 기존 결정의 *뜻* 을 잇는 것이면 진행하고 결과만 보고한다.** 진짜로 물어야 하는 것은 **오너만 가진 정보**가 필요한 때다(법률 문언 · 제품 방향 · 돈 쓰는 선택 · 외부 서비스 승인 여부 · 트리거가 실제로 왔는지). HANDOFF 오너 결정 표 머리에도 같은 문장을 세웠다.

### Completed work

#### 1. 활동 로그 D2=ⓑ (`267ba22`)

replay 는 활동 행을 안 남긴다 — **세 경로가 한 답**이 됐다. 오너 근거: *"재시도가 사용자에게 보일 필요가 없다 — 쿼터에서 줄어드는 것도 아닌데"*(replay 는 provider 호출이 없어 차감되지 않는다).

- `routers/writing.py`: accept 기록에 `and not result.idempotent_replay`
- `routers/drafts.py`: 저장 기록을 `if not result.idempotent_replay:` 로
- **502 partial 경로는 D3=ⓐ 로 별개 축**이라 무접촉

**특성 셀 둘이 예고대로 뒤집혔다**(둘 다 docstring 이 *"D2=ⓑ 면 함께 뒤집힌다"* 고 적어 둔 자리) — `..._still_records_a_second_row` → `..._leaves_no_second_row`. 어제 HP-1 로 더한 `action`·`target_type` 단정은 **행 자체가 사라져 함께 걷혔고**, 그 축은 over-strict 짝이 계속 잠근다.

#### 2. 파기 청구 뒤 탈퇴 취소 = ⓐ 409 거부 (`463a042`)

D5 의 경계(*"파기 실행 전까지"*)가 **처음으로 시행된다**. 종전에는 `cancel_withdrawal` 이 `purge_started_at` 을 안 봐서 부분 파기된 계정이 취소로 활성 복귀했다.

- 신규 `WithdrawalPurgeAlreadyClaimed` → 라우터가 `WithdrawalNotRequested` 와 **같은 409**(ⓑ 새 상태코드 미채택 — 화면 처방이 재조회로 같고 H3 가 `detail` 분기를 금지한다)
- **거부는 아무것도 되돌리지 않는다** — 유예 스탬프·파기 표식 존치. ⓓ 를 안 택한 이유가 그대로 산다(표식은 reconciler 의 유일한 단서, v1.8.52 가 셀로 잠금)
- 특성 셀이 *"통과한다"* → *"거부된다 + 두 스탬프 존치"* 둘로 · HTTP 경계 셀 신설 · **정책 문서 §6 문장도 함께** D5 약속으로 복귀

#### 3. 옛 커밋 해시 주석 = ⓒ (두 자리)

2026-08-23 `git filter-repo` 재작성으로 **2026-07-06~08-23 구간 기록의 해시가 264개 중 263개 해소 불가**다. 오기가 아니라 그때의 사실이므로 **고치지 않고** 두 자리에 적었다 — `docs/verifications/README.md` 머리 · HANDOFF 함정 절. ⓑ(인덱스만)를 안 택한 것은 work_log 독자가 못 보기 때문이다.

### Decisions — User Decisions and Rationale

- **D2=ⓑ**: 재시도는 회원에게 보일 정보가 없고 과금 축과도 무관하다. ⓒ(스키마 표식)의 비용은 표본 없이 치를 이유가 없다는 §추천 판단은 유지된 채, ⓐ 가 남기던 *"같은 개념에 답이 셋"* 이 해소됐다.
- **파기 뒤 취소 = ⓐ**: 청구는 유예가 **끝난** 뒤에만 일어나므로 ⓒ·ⓓ 가 전제하던 *"회원이 막히면 안 된다"* 가 이 축에서 성립하지 않는다.
- **해시 = ⓒ**: 기록은 고치지 않는다(이력 문서 불변 원칙).

### Verification

- 초점: `test_activity_api`·`test_writing_accept` **77 passed / 19 subtests** · `test_auth_users`·`test_auth_api`·`test_service_policy_contract`·`test_docs_indexes` **256 passed / 1618 subtests** · 문서 가드 둘 **29 passed / 957 subtests**.
- **백엔드 전수 미실행** — 독립 검증 서브에이전트에 넘긴다(코드 변경이 있으므로 기준선은 그쪽 실측이 정본이다).
- SoT **v1.8.66** 등재 · README ④행 동반 갱신 · 브리프 둘 상태·인덱스 상태 열 갱신 · legal 대조표에 `미기재` 행 하나 신설.

### Next steps

- 독립 검증(서브에이전트) 결과 반영 + 보강.
- **오너 결정 대기 표가 비었다**(2026-09-13 현재 0건).

## 세션 79 — 오너 결정 셋 시행의 독립 검증(+ 보강): 조건 C1 = accept 502 partial 무셀

### Goals

- 세션 78 산출(`267ba22`·`463a042`·`d9a1bd2`)을 **구현자가 아닌 세션**이 적대적으로 재검하고, 보강할 곳은 직접 닫는다.

### Completed work

#### 1. 검증 — 판정 **조건부 합격**(조건 C1, 같은 세션이 닫음)

기록: [`verifications/2026-09-13/owner_decision_set_d2_and_purge_cancel.md`](../../verifications/2026-09-13/owner_decision_set_d2_and_purge_cancel.md). 변이 **열넷**(M1~M12·M14·M15), 전부 탈치 워크트리에서. 등가 변이 0 · 흡수 0.

- **열거된 세 경로는 흠 없음** — M1~M6 이 각각 정확히 1셀만 물어 **분리 소유** 실증.
- **잃은 커버리지 0** — 구현자의 *"`action`·`target_type` 축은 over 짝이 계속 잠근다"* 주장을 M7·M8 로 반증 시도했고 실패했다(주장이 맞다).
- **파기 뒤 취소 거부** — under 3셀(M9) · **over 6셀(M10)** · 스탬프 되돌림 2셀(M12) · 라우터 매핑 1셀(M11). 경계가 `purge_started_at` 하나로 충분함을 **파기 그래프 1단계 = 청구**에서 유도(표식 전에는 아무것도 파괴되지 않는다). 선언·tier 예외 집합·파기 완료 계정 축 전부 무변 확인.

#### 2. ★ 조건 C1 폐쇄 (`867ba15`) — D2=ⓑ 를 `writing/accept` 502 partial 까지

구현자는 네 자리(커밋 메시지·라우터 주석·SoT v1.8.66·브리프)에 *"502 partial 은 D3=ⓐ 로 별개 축"* 이라 적었는데 **오귀속**이다 — D3 은 `analysis/jobs/{id}/auto-promote` 의 **503** partial(침묵)을 다루는 **다른 endpoint** 축이고, 이 자리는 **D2 브리프의 실측표가 세 표면 중 하나로 명시 열거**한 곳이다. 프로브 실측: 같은 키 2회 → **502·502 · 저장 version 1개 · 활동 행 2건**.

`if not exc.saved.idempotent_replay:` 로 감싸고 under 셀 `test_a_replayed_partial_accept_leaves_no_second_row` 신설(over 짝은 기존 partial 셀). M14·M15 로 양방향 실효 확인. **네 표면이 한 답을 말한다.**

#### 3. 하드닝 정정 셋

- SoT v1.8.66 근거 링크 `work_log 세션 76`(다른 슬라이스) → **세션 78**.
- `_ERRORS_WITHDRAWAL` 주석 *"409 는 두 생산자"* → **셋**(선언 자체는 이미 409 를 담아 **누락 없음**).
- **옛 해시 주석의 구간별 분모가 재현되지 않는다** — 원 측정이 밝힌 방법으로 재측정하면 `1/264`→**`1/371`**, `269/272`→**`229/239`**, `65/66`→**`69/70`**(미해소 총계 377→**376**). 두 리비전에서 같은 값이라 드리프트가 아니다. **분자 `1` 과 경계는 정확히 재현**되므로 결론은 그대로. 발행된 두 자리에 **유도 명령이 없던 것**이 원인이라 명령을 붙였고 **수치 교체는 오너 몫**으로 남겼다(오너 결정 ⓒ 로 들어간 문장이다).

#### 4. ★ 패턴 스윕 — 다섯째 표면을 찾았고 **고치지 않았다**

`PUT /projects/{id}/brief`([`routers/projects.py:211`](../../../services/application/app/routers/projects.py#L211))이 응답에 `idempotent_replay` 를 실으면서도 `activity.record` 를 **무조건** 돈다 — D2=ⓑ 가 고친 수동 저장 경로와 **글자 그대로 같은 모양**이다. 실측: 같은 키 2회 PUT → `false`·**`true`** · `project_brief_saved` **2건**. `git blame` → `d422bc4`(2026-08-09 Phase 9 Slice 9.0) = **의도적 이탈이 아니라 D1·D2 이전의 기본값**.

**고치지 않은 이유**: C1 의 502 표면은 브리프 §D2 실측표가 **명시 열거**했고 구현자가 그 축을 다뤘다고 주장한 자리라 미시행분이 분명했다. 이 자리는 **어느 브리프도 열거한 적이 없다** — 검증자가 넓히면 오너 결정의 범위를 대신 늘리는 것이다. HANDOFF 미수리 표에 등재하고 **오너 결정 대기**로 올렸다(ⓐ 넓힌다 · ⓑ 열거된 넷으로 둔다 — 구현자 추천 **ⓐ**).

※ `analysis.py` 의 나머지 `activity.record` 자리는 멱등 키가 없거나(후보 승격·확정·거부·편집은 상태 전이라 재전송이 409) 이미 분기가 있다(`:497`·`:994`). 스윕이 낸 실제 구멍은 이 하나다.

### Decisions — User Decisions and Rationale

- 이 세션은 새 오너 결정을 만들지 않았다. C1 폐쇄는 **오너가 이미 답한 D2=ⓑ 의 미시행분**이라는 판단이고(브리프가 그 표면을 열거했다), 구현자가 명시적 반대 판단을 적었으므로 **검증 기록 §Outstanding 1 에 오너 통지 항목으로 올렸다**.

### Verification

- 백엔드 전수(최종 트리 실측) · EXIT=0 · **skip 1(live Chroma)** — 값은 HANDOFF 기준선 줄·`README.md` 절차 표 ②행에 반영.
- 프런트 **무변**(이 슬라이스는 프런트 파일을 한 줄도 안 건드렸다 — `git diff --stat` 무차분).
- SoT **v1.8.67** 등재 · README ④행 동반 · 검증 기록 313→**314건**.

### Next steps

- **합격 승격은 다음 독립 세션 몫** — 조건을 닫은 세션이 자기 판정을 올리면 독립성이 사라진다(v1.8.52·v1.8.63·v1.8.65 선례). 변이 M14·M15 재적용이 승격의 확증 재료다.
- 옛 해시 수치 교체 여부는 오너 결정 대기.

## 세션 80 — 이어받기: 기준선 줄 확정(최종 트리 전수 + 두 리비전 통제 대조)

### Goals

- 세션 리밋으로 쓰러진 작업 AI(세션 78)의 마지막 미완 — 검증 커밋 `449784d` 가 *"기준선 줄은 최종 트리 전수 뒤 별도 커밋으로 갱신한다"* 고 예고한 그 커밋 — 을 닫는다.
- 세션 78 이 시작해 놓은 측정 둘(최종 트리 전수 · `d9a1bd2` 탈치 클론 대조 전수)을 수습해 기존 기준선(3063/4234)부터의 차분을 전부 귀속한다.

### Completed work

#### 1. 측정 수습(두 run 다 완료 상태로 남아 있었다)

- **최종 트리(`542e087`) 전수**: **3066 passed / 1 skipped / 4236 subtests · EXIT=0 · 357초**(skip 1 = live Chroma).
- **대조 — 탈치 클론 `d9a1bd2`(세션 78 끝) 전수**: **3065 / 1 / 4234 · EXIT=0 · 294초**.

#### 2. 차분 귀속(3063/4234 → 3066/4236 = +3 passed / +2 subtests)

| 구간 | 차분 | 귀속 | 근거 |
|---|---|---|---|
| 구 기준선 → `d9a1bd2` | +2 passed | `463a042`(파기 뒤 취소) | 셀 +3/−1(특성 셀 분리 +1 · HTTP 경계 셀 +1). `267ba22`(D2=ⓑ)은 셀 개명 2쌍(+2/−2)이라 수 무변 — 대조 전수 3065 가 직접 확인 |
| `d9a1bd2` → `542e087` | +1 passed | `867ba15` | under 셀 하나 순증가(diff 확인 — 본문에 subTest 없음) |
| `d9a1bd2` → `542e087` | +2 subtests | `449784d` | 검증 기록 문서 하나 — 문서 가드 둘 **957 → 959** 양단 실측(문서당 1씩) |

#### 3. 기록 갱신

- `HANDOFF.md` 기준선 줄 **3063/4234 → 3066/4236** + 귀속 문장 삽입(세션 77 단계 뒤, 연대순 사슬 끝).
- `README.md` 절차 표 ②행 같은 값 — 가드 `test_the_readme_repeats_the_regression_baseline` 가 둘을 묶는다.

### Issues found

- **중간 무효값은 발행되지 않았다** — 세션 78 서사에 언급된 트리 중간 변화 무효 측정(3066/1/4235)은 기록 파일 어디에도 남지 않았음을 grep 으로 확인했다. 확정값만 발행됐다.
- **전수 소요가 대조 클론(294초, `/tmp`)과 메인 트리(357초, `/mnt/f`)에서 1.2배 차이** — WSL 드라이브 마운트 I/O 차이. 기준선 줄의 *"소요는 머신-로컬 값"* 경고가 파일시스템 축까지는 못 덮는다 — 소요로 회귀를 판정하지 말라는 규칙은 그대로 유효.

### Decisions

- 이 세션은 새 결정 축이 없다(측정 수습·기록 마감). **CHANGELOG 별도 행 없음** — 세션 79 행이 오늘의 변화를 이미 덮고, 기준선 갱신은 설계·기능 변화가 아니다(가이드 *"not every small edit"*).

### Verification

- 문서 가드 둘 메인 트리 재실행(갱신 뒤): **29 passed / 959 subtests** — README↔HANDOFF 기준선 가드 포함 전건 초록.
- 이 세션은 코드·프런트 무변(문서 세 파일만).

### Next steps

- 대기 셋(전부 세션 79 가 발의하고 HANDOFF 가 싣는다): 검증 기록 판정 승격(**독립 세션 몫** — M14·M15 재적용이 확증 재료) · **H4** 다섯째 표면 오너 결정(ⓐ 넓힌다 / ⓑ 열거된 넷 — 구현자 추천 ⓐ) · 옛 해시 분모 수치 교체 여부.
