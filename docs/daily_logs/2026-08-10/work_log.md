# 2026-08-10 작업 로그

## Goals

- 핸드오프·어제 로그가 가리키는 **다음 작업**을 집는다.
- 어제 남은 **미검증 구간**(accept 활동 로그 보강분 `66f2845`·`33fe4b2`)을 독립 검증한다.
- 조건이 실제로 닫혔으면 **판정 승격**까지 처리하고, 인덱스·기준선 숫자를 정합으로 만든다.

---

## Task 1 — 보강분 독립 검증 (`66f2845`·`33fe4b2`)

검증 서사·경계 행렬·재현 명령은 기록에 있다(여기 복사하지 않는다):
[`verifications/2026-08-10/accept_activity_cell_reinforcement.md`](../../verifications/2026-08-10/accept_activity_cell_reinforcement.md).

### User Decisions and Rationale

- **오너 지시(2026-08-10)**: *"핸드오프와 어제자 데일리로그 확인해서 다음작업 진행해줘."*
  다음 작업을 문서가 정하게 하라는 것. HANDOFF Next Tasks 와 어제 Task 8 이 **미검증 구간 =
  보강분**을 명시하고, 이 저장소의 표준 리듬은 *"미검증 구간을 남긴 채 다음 슬라이스를 열지
  않는다"* 이며 **어제 오너가 화면 슬라이스·재빌드·dogfood 를 제치고 검증을 고른 선례**가
  있다. 그래서 화면(활동 타임라인)이 아니라 **검증**을 집었다. 화면은 새 슬라이스라
  오너 브리프가 선행한다.

### 판정

**합격 — Blocking 0**, 비차단 1건.

| 축 | 결과 |
|---|---|
| 새 셀이 502 partial 분기를 잠그는가 | **네 방향 전부 재실패**(아래 표) |
| 전수 가드가 분기를 못 본다는 Blocking 전제 | 지금도 참 — V1 아래 `test_activity_actions.py` 전부 통과 |
| 계약의 3분기 열거가 완전한가 | **완전** — 저장 뒤 예외는 `_finalize` 하나(코드 근거) |
| 주석이 바꾼 수(20 경로 · 지점 21) | 코드 실측 일치 |
| `33fe4b2` 가 정정한 N10 페어링 | **정정대로 재현**(2 cells) |
| 기준선 `2250/1/2325` | **베타 원시값으로 재현**(939s) |

### 뮤테이션 (5종 — 2종은 재현, **3종은 이 세션이 추가**)

전부 [`routers/writing.py`](../../../services/application/app/routers/writing.py) 를 변형하고
`pytest -q tests/test_writing_accept.py tests/test_activity_actions.py`(기준선 `58 passed`)로
요약 줄을 읽었다.

| # | 방향 | 적용한 diff | 재실패 셀 |
|---|---|---|---|
| V1 | under | 502 분기의 `activity.record(...)` **6줄 삭제**(:1273) | `test_a_partial_accept_still_records_the_saved_version` (1) — `1 failed, 57 passed` |
| V2 | over | 같은 분기에 동일 호출 **한 번 더 삽입** | 같은 셀 (1) |
| **V3** | under | 같은 분기 리터럴만 `"draft_version_accepted"` → `"draft_version_saved"` | 같은 셀 (1) |
| **V4** | under | 같은 분기 `target_id=exc.saved.draft_version.id` → `exc.target_draft.id` | 같은 셀 (1) |
| **N10 재현** | over | 성공 경로 `if result.saved is not None:` → `if True:`(:1301) | `test_a_bounced_accept_is_not_recorded` · `test_non_pass_is_200_without_saved_artifacts` (2) — `2 failed, 56 passed` |

**V3·V4 를 추가한 이유**: V1·V2 만으로는 셀이 *"상태코드와 건수"* 만 재는 공허한 단정일
가능성이 남는다. 리터럴과 `target_id` 를 각각 흔들어 **무엇이 남았는지**까지 잠근다는 것을
확인했다. 둘 다 물었다.

**N10 을 재현한 이유**: 그 페어링 **정정 자체가 `33fe4b2` 의 산출물**이라 검증 대상이다.
정정된 표기와 문자 그대로 일치했고, 정정 전 표기(`test_a_saved_accept_is_recorded_…`)가
틀렸던 것도 함께 확인됐다 — 그 셀은 이 변이에서 통과한다(Gate PASS 경로라 조건 제거가
관측을 안 바꾼다).

### ★ 이 검증이 새로 채운 축 — 계약의 3분기 열거가 완전한가

어제 검증은 *"계약이 열거한 셋 중 하나가 빈 칸"* 을 봤다. 이 세션은 **열거 자체가 누락이
아닌지**를 물었다 — 계약이 세 개만 적은 것이 옳은가.

[`writing/accept.py`](../../../services/application/app/writing/accept.py) 에서 저장 지점은
넷(`start_next_unit` :127 · `save_draft` :143 · `_replay` :163·:174)이고 **그 뒤 모든 경로가
`_finalize`(:179) 하나로 모인다.** `_finalize` 가 던질 수 있는 것은 `except Exception` 이
감싼 **`WritingAcceptAnalysisError` 하나뿐**(:186) = 502 partial 분기다. 나머지 예외는 전부
저장 **이전**에 난다.

**결론: "정본이 바뀌었는데 기록이 없는 경로"는 남아 있지 않다.** 부수로, **replay 도
`_finalize` 를 지나므로 기록된다**는 코드 근거가 나왔다 — 어제 비차단 ②(replay 가 이벤트를
매번 추가)의 정확한 기전이며, 여전히 오너 결정 대기다.

### Issues found — 비차단 1건: "73 → 74 cells" 는 파일 하나의 수가 아니다

**문제.** 어제 기록 §6-b 표와 work_log Task 8 Completed work 표가 **`tests/test_writing_accept.py`
행에** `73 → 74 cells` 를 적었다. 그 파일은 실제로 **50 → 51 cells** 다.

**원인.** 숫자 자체는 맞고 **귀속 대상이 틀렸다**. 73/74 의 출처는 같은 기록 §4 의
**3-파일 세트**(`test_writing_accept.py` + `test_activity_actions.py` + `test_activity_log.py`)
이며, 그 세트를 test-mongo ON 으로 돌리면 정확히 `74 passed / 79 subtests` 다(실측).

**왜 비차단인가.** 계약이 요구하는 잠금이 아니라 기록의 서술이고, 셀은 실재하며 네 방향으로
문다. **왜 그래도 적는가.** 이 저장소의 표준 확인법이 *"그 파일을 열어 세어 보는 것"* 이라,
다음 사람이 51 을 세고 23 만큼 어긋난 채 *"셀이 사라졌나"* 를 조사하게 된다.

**처리.** **고치지 않았다** — 가이드 §*"the verifier does not silently fix the defect"*.
고치는 법은 두 표의 행 라벨을 3-파일 세트로 바꾸는 한 줄이고, 반영은 오너 판단이다.

### 판정 승격 (이 세션이 한 것)

어제는 **조건을 낸 검증 세션 자신이 조건을 닫아** 판정을 올리지 않았고, 승격 권한을
*"다음 독립 세션 또는 오너"* 로 남겼다. 이 세션이 그 독립 세션이고 폐쇄를 재현했으므로,
오너 결정(2026-08-06) *"판정 열은 그 기록의 **최종** 판정이다"* 에 따라 승격했다.

| 대상 | 처리 |
|---|---|
| [`service_activity_log_accept_extension.md`](../../verifications/2026-08-09/service_activity_log_accept_extension.md) §8 | `조건부 합격` → **`합격`**. **발행 시점 원문을 인용 블록으로 보존**했다(무엇이 원래 지적이었는지 지워지면 안 된다) |
| `docs/verifications/README.md` | 인덱스 판정 열 승격 + 새 행 · 건수 230 → **231** · 46 → **47**일치 · 분포 합격 161 → **163** · 조건부 67 → **66** |
| `README.md` · `docs/README.md` | 같은 수 세 자리 + 분포 문장 |

**★ 분포가 +2 인 이유**: 승격 1(조건부 → 합격) + 이 기록 신규 1. 합 231 = 163 + 66 + 2.

### 머신 전환 관측 (알파 → 베타)

`nvidia-smi` **GTX 1060 3GB** = 베타다(어제 기록은 알파 실측). HANDOFF 전환 절차대로 확인:
HEAD `33fe4b2` clean · `docker compose ps` 는 `frontend`(healthy)·`worker`·`generation_worker`
셋뿐 · test-mongo 는 회귀 때만 올렸다 내렸다.

**★ 이 전환이 준 뜻밖의 증거**: 알파는 `elasticsearch` 패키지가 없어 3건이 skip 돼
`2247/4` 를 **보정**해 `2250/1` 을 얻어 왔는데, 베타에는 그 패키지가 있어 3 cells 가 실제로
돌았다 — 즉 **보정값을 다른 머신이 원시값으로 재현**했다. 보정이 옳았다는 독립 증거다.
소요는 939초(알파 185초).

### Verification

| 검사 | 결과 |
|---|---|
| 전수 회귀(베타, test-mongo ON) | `2250 passed / 1 skipped / 2325 subtests in 939s` — **원시값이 곧 보정값** |
| skip 사유 | live Chroma 1건뿐(`test_chroma_adapter.py:490`) |
| 문서 갱신 후 `test_docs_indexes.py` | `13 cells / **241** subtests`(240 → +1, 새 기록 1건) |
| 문서 갱신 후 전수 회귀 | `2250 / 1 / **2326**` |
| 뮤테이션 전후 `git status --short` | 매회 비어 있음 · 마지막 원복 뒤 `git diff HEAD` 도 비어 있음 |

### 아직 안 한 것 (의도)

- **비차단 1건(라벨 정정)** — 검증자가 고치지 않는다. 오너 판단.
- **replay 축** — 계약 침묵, 오너 결정 사안. 트리거는 화면 슬라이스.
- **화면(활동 타임라인)** — 새 슬라이스라 오너 브리프 선행.
- **스택 재빌드 · nginx 한 홉 · dogfood 착수** — 오너 대기 유지.

### Next steps (다음 작업자에게)

1. **미검증 구간이 없다.** 보강분까지 독립 검증이 끝났고 판정도 승격됐다.
2. **자연스러운 다음은 화면(활동 타임라인)** — API 는 operation 77 로 서 있고 `schema.d.ts` 도
   재생성돼 있다. **새 슬라이스이므로 오너 decision brief 가 먼저다**(replay 표시 방식이 그
   브리프 안에서 함께 결정되는 자리다 — 어제 비차단 ②의 트리거가 바로 이것이다).
3. **오너 대기 두 건 유지**: 재빌드 후 `curl :5520/api/admin/users` = 401 · dogfood 착수(GATE-1).

---

## Task 2 — 비차단 지적 폐쇄 (숫자 귀속 정정)

### User Decisions and Rationale

- **오너 지시(2026-08-10)**: *"보강이 필요한 부분 보강해주고 없다면 화면 브리프 작성해줘."*
  Task 1 이 낸 비차단 1건을 닫으라는 것. 어제 Task 8 과 같은 형태의 지시이고, 이번에는
  **판정 승격 문제가 없다** — 이 기록의 판정이 원래 `합격`이라 폐쇄가 판정을 건드리지 않는다.

### Completed work

| 파일 | 변경 |
|---|---|
| [`verifications/2026-08-09/service_activity_log_accept_extension.md`](../../verifications/2026-08-09/service_activity_log_accept_extension.md) §6-b | `추가(73 → 74 cells)` → **3-파일 세트 73 → 74 · 파일 하나 50 → 51** 을 함께 적는다 |
| [2026-08-09 work_log Task 8](../2026-08-09/work_log.md) Completed work | 같은 정정(그 행이 가리키는 것이 파일 하나임을 명시) |
| [`verifications/2026-08-10/…reinforcement.md`](../../verifications/2026-08-10/accept_activity_cell_reinforcement.md) §5-1 | **발행 뒤 추가** 블록으로 폐쇄 표기 — **지적 원문은 그대로 둔다** |
| `HANDOFF.md` 추적 부채 | 폐쇄 + 일반 규칙 한 줄로 축약 |

### 남긴 일반 규칙 (부채를 지우는 대신 남기는 것)

**셀 수를 적을 때는 "무엇을 돌린 수인지"를 같은 줄에 적는다.** 이 저장소의 확인법이
*"그 파일을 열어 세어 보기"* 라, 세트 수를 파일 행에 적으면 **재현할 수 없는 숫자**가 된다.
이번 건은 23 만큼 어긋나 있었고, 값이 맞았기 때문에 오히려 더 오래 살아남을 수 있었다.

### Verification

| 검사 | 결과 |
|---|---|
| `test_docs_indexes.py` | `13 cells / 241 subtests` — 무변(문서 본문 수정이라 건수를 안 건드린다) |
| 코드 변경 | **0줄** |

---

## Task 3 — 화면(활동 타임라인) 착수 결정 브리프 작성

브리프: [`plans/09-1-activity-timeline-screen-decisions.md`](../../plans/09-1-activity-timeline-screen-decisions.md)
(**Open — S1~S6 오너 결정 대기**). 선택지 표·권고·근거는 브리프에 있다(여기 복사하지 않는다).

### User Decisions and Rationale

- **오너 지시(2026-08-10)**: *"보강이 필요한 부분 보강해주고 **없다면 화면 브리프 작성**해줘."*
  보강(Task 2)이 문서 두 줄로 끝나는 크기라 같은 세션에서 브리프까지 갔다. **브리프는
  결정을 묻는 문서이지 구현이 아니므로 착수하지 않았다** — CLAUDE.md §1 "Owner decision
  brief (kickoff)".

### 브리프를 쓰기 전에 코드에서 확인한 것 (추측으로 쓰지 않았다)

| 사실 | 값 | 왜 브리프에 필요한가 |
|---|---|---|
| 응답 상한 | **100건 하드코딩**([`log.py:142`](../../../services/application/app/activity/log.py#L142) 기본값, endpoint 가 `limit` 미전달) | S2 전체가 이 사실 위에 선다 |
| 페이징 파라미터 | **없음**(쿼리스트링 0개) | "더 보기"는 **계약 변경**이라는 것 |
| 정렬 | 최신순 `at` DESC([`log_mongo.py:47`](../../../services/application/app/activity/log_mongo.py#L47)) | 화면이 정렬을 안 해도 된다 |
| action / target_type | **20종 / 9종** | S4 라벨표 크기와 S6 링크 대상 |
| 선례 화면 | [`AccessLogPage.tsx`](../../../frontend/src/projects/AccessLogPage.tsx) 56줄 · eager · `DraftList:241` 진입 | S1 권고의 근거 |

### ★ 브리프를 쓰다가 발견한 것 — 행위자 열이 필요 없다

**관리자 행위는 이 컬렉션 밖이고**(분류표 `admin_audited` 로 제외 — `admin_audit_events`·
`access_grant_uses` 가 담는다) **프로젝트는 소유자 1인 소유**다. 그래서 `actor_user_id` 는
**항상 화면을 보고 있는 그 사람**이다 — 열을 만들어도 정보량이 0이다(S3=ⓑ 권고의 근거).

이것은 A2/A8 결정의 **부수 효과**이지 누군가 설계한 것이 아니라, 브리프에 적어 두지 않으면
다음 구현자가 `actor_user_id` 를 그대로 렌더하고(access-log 선례를 따라) 화면에 24자 hex 가
줄마다 뜬다.

### 계약을 움직이는 자리를 분리해 둔 이유

S2(페이징)·S4(라벨 정본)·S5(replay)는 **고르는 순간 operation 77 계약이 바뀌거나 정본이
둘이 되는** 자리다. 전부 *"먼저 만들고 보고 나서"* 를 권고했다 — **아직 아무도 이 데이터를
본 적이 없어서** 지금 고르면 사용 근거 없이 형태에 갇힌다. **예외 하나가 S4 의 가드**이며,
라벨표는 만드는 순간 두 번째 정본이 되므로 그 셀이 같은 커밋에 있어야 한다고 적었다.

### Completed work

| 파일 | 변경 |
|---|---|
| [`plans/09-1-activity-timeline-screen-decisions.md`](../../plans/09-1-activity-timeline-screen-decisions.md) | **신규** — S1~S6 선택지 표 + 권고 + follow-up + Deferred + 구현 순서 |
| [`plans/09-service-activity-log.md`](../../plans/09-service-activity-log.md) | 부모 계획 상태에 9.1 브리프 포인터 |
| [`plans/README.md`](../../plans/README.md) · `README.md` | 인덱스 행 + 건수 102 → **103** · 브리프 84 → **85** |

### Verification

| 검사 | 결과 |
|---|---|
| `test_docs_indexes.py` | `13 cells / 241 subtests` — **가드가 먼저 실패해 건수 주장 3자리를 잡아냈다**(README 2 · plans README 1) |
| 코드 변경 | **0줄**(브리프는 결정 문서다) |

### Next steps

1. **오너가 S1~S6 을 정하면** 브리프 §"결정 뒤 구현 순서" 1~7 로 착수한다. 1번이 회귀 먼저다.
2. 정해진 값은 브리프에 `Resolved` 로 적고 SoT 행은 **구현과 함께** 간다(계약이 실제로
   움직이는 것은 S2-ⓑⓒ·S4-ⓑ·S5-ⓒ 를 고를 때뿐이다).

---

## Task 4 — 9.1 브리프 확정 (S1~S6) + 정본 분할 원칙

브리프: [`plans/09-1-activity-timeline-screen-decisions.md`](../../plans/09-1-activity-timeline-screen-decisions.md)
(**Resolved**). 확정값 표·근거는 브리프에 있다.

### User Decisions and Rationale

- **S3 = ⓑ(행위자 열을 안 만든다)** — 오너: *"c가 되어야 하지 않을까 생각했는데 **공동 작업이…
  있을까?** 싶어서. **개인 시스템**이라고 하면 되겠지."* username 조인(ⓒ)을 먼저 떠올렸으나
  **행위자가 항상 한 사람**이라는 실측(관리자 행위는 이 컬렉션 밖 · 소유자 1인 소유)을 받아들여
  ⓑ. **전제는 "개인 시스템"이며, 그 전제가 바뀌면 F4 로 되살린다**(응답 필드는 남겨 뒀으므로
  backend 0줄).
- **S4 = ⓐ(프론트 상수표 + 전수 가드)** — 선택은 권고와 같지만 **오너가 근거를 고쳤다**:
  *"이거 정본을 나누는 것에 대해서 **두려움을 갖지 말라**고 얘기하는 거야. 서로 다른 섹션의
  정본이면(중복된 내용이 아니라면) **정본은 몇 개가 되든 상관없어. 인덱싱만 제대로 되어 있고
  연결만 되어 있으면.**"*
- **S1·S2·S5·S6 = 권고 그대로** — *"나머지는 괜찮은 거 같아."*
- **기록 지시**: *"특히 **선구현 후확장 목록**들은 해당 결정이 나중에 묻히지 않게 메모 잘
  해주고."*

### ★ 오너 정정이 실제로 바꾼 것 (선택이 아니라 판단 기준)

초판 브리프는 ⓐ 의 단점을 *"**정본이 둘**이 된다"*, ⓑ 의 장점을 *"정본 하나"* 로 적었다.
**그 프레이밍이 틀렸다.** 새 기준은 셋이다:

1. **중복인가** — 같은 내용을 두 곳이 말하는가?
2. **인덱싱돼 있는가** — 찾을 수 있는가?
3. **연결돼 있는가** — 한쪽이 바뀔 때 다른 쪽이 알게 되는가?

이 건은 ①에서 **중복이 아니다**: 백엔드 `activity/actions.py` 의 정본은 *"어떤 route 가 무엇을
기록하는가"*(배선·분류), 프론트 라벨표의 정본은 *"그 리터럴을 사람에게 뭐라 부르는가"*(UI 문구).
**서로 다른 섹션의 서로 다른 사실**이다. 그래서 ⓑ 의 "정본 하나"는 장점이 아니라 **관심사
혼합**이 된다(서버가 UI 문구를 든다).

**전수 가드의 의미도 뒤집힌다** — *"정본이 둘이라 위험해서 두는 벌칙"* 이 아니라 **둘로 나눠도
되게 만드는 연결선**이다. 나쁜 것은 분할이 아니라 **끊긴 분할**이다.

이 원칙은 이 슬라이스보다 넓어서 **HANDOFF Active Decisions** 에 표준 제약으로 올렸다.

### ★ 선구현 → 후확장을 "묻히지 않게" 한 방법 (오너 지시)

브리프에 **§"나중에 여는 문"** 절을 만들고 **F1~F6 각 행에 "여는 트리거"를 붙였다** —
*무엇을 보면 여는가*. **트리거 없는 유예는 유예가 아니라 망각**이라는 것이 이 저장소의 실측
근거다: §43 `system_events` 가 문서에만 있고 코드 0줄로 **한 페이즈 내내** 남아 있었고, 그것을
발견한 것이 Phase 9 의 발원이었다.

| # | 미뤄 둔 것 | 트리거 |
|---|---|---|
| F1 | 커서 페이징(S2-ⓒ) | "최근 100건" 아래가 궁금해지는 순간 — **관측 화면 `?since=` 와 같은 축이라 따로 열지 않는다** |
| F2 | replay 접기(S5-ⓑ) | 같은 저장이 화면에서 실제로 여러 줄로 보이면 |
| F3 | replay 기록 정책(S5-ⓒ) | F2 로도 부족할 때 — A7·A8 재검토 동반 |
| F4 | 행위자 열(S3) | **공동 작업이 생기는 날** — 전제("개인 시스템")가 바뀌는 것이 트리거다 |
| F5 | 링크 확장(S6-ⓒ) | candidate·gate_finding·review_queue_entry 에 전용 화면이 생기면 |
| F6 | 필터·검색 | F1 종속 |

**인덱싱은 세 곳**(오너 원칙 ②를 이 표 자신에게도 적용했다): 브리프 · HANDOFF 추적 부채 ·
부모 계획 상태 줄. **구현이 끝나도 이 표는 지우지 않는다** — 트리거가 살아 있는 한 유효하다.

### Completed work

| 파일 | 변경 |
|---|---|
| [`plans/09-1-…-decisions.md`](../../plans/09-1-activity-timeline-screen-decisions.md) | **Resolved** · 확정값 표 · **§S4 근거 재작성**(오너 정정 인용 포함) · **§"나중에 여는 문" F1~F6 신설** · "정본이 둘" 프레이밍 3곳 정정 |
| [`plans/09-service-activity-log.md`](../../plans/09-service-activity-log.md) · [`plans/README.md`](../../plans/README.md) | 상태 Resolved + F 표 포인터 |
| `HANDOFF.md` | Owner Decisions 에서 9.1 제거(결정됨) · Next Tasks 를 구현 대기로 · **추적 부채에 F1~F6** · **Active Decisions 에 정본 분할 원칙** |

### Verification

| 검사 | 결과 |
|---|---|
| `test_docs_indexes.py` | `13 cells / 241 subtests` — 무변 |
| 코드 변경 | **0줄**(결정 문서 확정) |

### Next steps

1. **9.1 구현 착수 가능** — 브리프 §"결정 뒤 구현 순서" 1~7, **1번이 회귀 먼저**(20 리터럴 전수 가드).
2. 계약 영향이 0이라 **SoT 행은 구현과 함께** 간다(지금 올릴 것이 없다).

---

## Task 5 — Slice 9.1 구현 (활동 타임라인 화면)

### User Decisions and Rationale

- **오너 지시(2026-08-10)**: *"오케이 바로 진행해보자."* 브리프 확정 직후 착수. 확정값
  S1~S6 을 그대로 구현했고, **계약을 넓히지 않는다**는 제약을 구현 중에도 지켰다(아래 F7).

### Completed work

| 파일 | 변경 |
|---|---|
| [`frontend/src/projects/activityActions.ts`](../../../frontend/src/projects/activityActions.ts) | **신규** — UI 문구 정본 20행 + `target_type` 링크/비링크 **전수 분류**(사유 포함) |
| [`tests/test_activity_ui_labels.py`](../../../tests/test_activity_ui_labels.py) | **신규 4 cells / 28 subtests** — ★ 두 정본을 잇는 **연결선** |
| [`frontend/src/projects/ActivityTimelinePage.tsx`](../../../frontend/src/projects/ActivityTimelinePage.tsx) | **신규** — 타임라인 · 빈 상태 · 에러 · **상한 문구** |
| `ActivityTimelinePage.test.tsx` | **신규 7 cells** |
| `App.tsx` · `DraftList.tsx` | route + 진입 링크(access-log 링크 옆) |
| `api/client.ts` | `listProjectActivity` + `ActivityEvent` 타입 |

**프로덕션 백엔드 0줄** — 새로 생긴 파이썬 파일은 테스트뿐이다.

### ★ 연결 가드를 프론트가 아니라 pytest 에 둔 이유

S4=ⓐ 의 조건이 *"백엔드가 21번째 action 을 더하면 실패한다"* 인데, **프론트는 백엔드 리터럴
목록을 알 방법이 없다** — `schema.d.ts` 는 `action` 을 `string` 으로만 준다(enum 이 아니다).
두 표를 동시에 볼 수 있는 자리가 pytest 뿐이라 거기 뒀다. 파이썬 테스트가 저장소의
비-파이썬 파일을 읽는 것은 `test_docs_indexes.py`(문서)·`test_compose_exposure.py`(compose)
선례를 따른다.

`target_type` 도 같은 형태로 **전수 등재**를 강제했다(`billable_actions` 관례) — 새 종류가
생기면 링크하거나 **사유와 함께** 비링크로 등재해야 한다. 빠진 것과 일부러 뺀 것을 구분한다.

### ★ 구현이 브리프 전제를 반증했다 — S6 이 좁혀졌고 F7 이 생겼다

브리프는 `draft`·`draft_version` 둘을 링크한다고 적었지만, 편집 화면 route 는
`/projects/:projectId/drafts/:draftId` 이고 **이벤트 payload 에 `draft_id` 가 없다**
(`target_id` 는 version id). 넣으려면 **operation 77 계약 변경**이라 오너 승인 아래 지키기로 한
*"계약 영향 0"* 과 어긋난다.

**그래서 `draft` 만 링크하고 `draft_version` 은 사유와 함께 비링크로 등재했다** — 그 자리에서
계약을 넓히지 않았고 **유예 F7** 로 올렸다(트리거: payload 에 `draft_id` 가 생기면).

**교훈**: 브리프 §0 실측 표가 **응답 필드를 나열했는데도** S6 을 쓸 때 대조하지 않았다.
화면 결정은 *"필요한 데이터가 응답에 있는가"* 를 **필드 단위**로 봐야 한다 — 종류가 있다고
route 를 만들 **재료**가 있는 것은 아니다.

### 뮤테이션 (7종 — 양방향)

**전부 커밋(`86ca173`) 뒤에 돌렸고**(§6 순서), 매회 전후로 `git status --short` 가 비어 있음을
확인했으며 마지막 원복 뒤 `git diff HEAD` 도 비어 있다.

| # | 방향 | 적용한 diff | 재실패 셀 |
|---|---|---|---|
| M1 | under | `activityActions.ts` 라벨 1행 삭제(`gate_finding_dismissed`) — 백엔드가 21번째를 더한 것과 같은 집합 차이 | `test_the_ui_table_labels_exactly_the_logged_actions` (1) |
| M2 | **over** | 백엔드가 모르는 유령 라벨 1행 추가(`memory_manually_edited`) | 같은 셀 (1) |
| M3 | under | 라벨 칸에 **리터럴을 복사**(`draft_version_saved: "draft_version_saved"`) — 집합은 맞고 화면만 영어가 되는 형태 | `test_every_label_is_korean_prose_not_the_literal` (**SUBFAILED** 1) |
| M4 | under | `NON_LINKABLE_TARGET_TYPES` 에서 `gate_finding` 삭제(미등재) | `test_every_target_type_is_classified_as_linkable_or_not` (1) |
| M5 | **over** | 화면이 `actor_user_id` 를 렌더(access-log 선례를 따라가는 회귀) | `does not show an actor column` (1) |
| M6 | under | "최근 100건까지 보여줍니다" 문구 삭제 | `says the 100-item ceiling out loud` (1) |
| M7 | **over** | `draft_version` 도 링크(version id 를 draft id 자리에 넣는 깨진 링크) | `links only the target types that have a screen` (1) |

**M3 이 중요한 자리다** — M1·M2 만으로는 "집합이 같으면 통과"라 라벨 칸에 리터럴을 복사해도
가드가 만족된다. 폴백(`?? action`)이 있어서 **화면은 영어 스네이크가 되는데 테스트는 green**
이 되는 형태이며, 두 번째 셀이 그것을 막는다.

### Verification

| 검사 | 결과 |
|---|---|
| backend 전수(베타, test-mongo ON) | **`2254 passed / 1 skipped / 2354 subtests in 906s`** — 종전 `2250/1/2326` 대비 **셀 +4 · subtest +28**(전부 새 가드) |
| frontend | **`272 passed / 19 files`** — 종전 `265/18` 대비 **+7 cells · +1 file** |
| build | **701 modules**(698 → +3) · 진입 **417.19 kB**(414.36 → +2.83) · **lazy 청크 무변** |
| `tsc --noEmit` | 통과 |
| operation | **77 무변** · 응답 형태 무변 |
| 뮤테이션 | 7종 전부 재실패, 원복 후 트리 clean |

### 아직 안 한 것 (의도)

- **육안 확인** — 렌더는 회귀로 잠갔지만 실제 화면을 사람이 본 적은 없다(프론트 이미지
  재빌드가 선행이고 그것은 오너 판단 사안이다). HANDOFF 의 "화면 육안 확인" 목록과 같은 성격.
- **F1~F7** — 트리거와 함께 브리프에 산다.
- **독립 검증** — 이 슬라이스가 지금 미검증 구간이다.

### Next steps

1. **미검증 구간 = Slice 9.1 두 커밋**. 이 저장소의 리듬대로 다음은 독립 검증이다.
   볼 만한 축: **연결 가드가 진짜 연결인가**(백엔드에 21번째를 실제로 더해 보는 뮤테이션) ·
   M3 형태(폴백이 만드는 조용한 통과) · **F7 판단이 옳았는가**(계약을 안 넓힌 것).
2. 육안 확인은 프론트 재빌드 뒤 `/projects/:id/activity`.

---

## Task 6 — 9.1 독립 검증 반영: 비차단 2건 폐쇄

검증 기록: [`verifications/2026-08-10/slice_9_1_activity_timeline.md`](../../verifications/2026-08-10/slice_9_1_activity_timeline.md)
(**합격 · Blocking 0**, `b18cb83` — 다른 세션). 폐쇄 표기는 그 기록 **§4-b**(발행 뒤 추가)에 있고
**원 지적 문언은 그대로 뒀다**.

### User Decisions and Rationale

- **오너 지시(2026-08-10)**: *"검증기록 확인해서 보강할 부분 보강해줘."* 검증이 낸 hardening 2건을
  닫으라는 것. **판정이 원래 `합격` 이라 승격 문제가 없다** — 어제 accept 확장 때와 다른 점이다.
- **검증 보고를 그대로 받지 않고 기록 실물과 커밋을 먼저 확인했다**(`b18cb83` 존재 · §4 문언 ·
  인덱스 232/164). 요약과 기록이 일치했다.

### H1 — 표시 상한 ↔ 서빙 상한을 **나눈 채 연결**했다

**무엇이 구멍이었나**: 프론트 `ACTIVITY_PAGE_SIZE = 100` 과 백엔드
`ActivityLogService.list_for_project(limit=100)` 이 **서로 모르는 독립 하드코딩**이었다. 백엔드
기본이 바뀌면(F1 커서 페이징 작업이 정확히 그 자리다) 화면은 여전히 *"최근 100건"* 이라고
말하는데 서버는 다른 수를 준다 — **문구는 남아 있으므로 프론트 셀도 백엔드 셀도 아무것도 못 본다.**

**어떻게 닫았나**: `ActivityCeilingClaimTest` 한 셀. 백엔드 값은 **`inspect.signature` 로 읽는다** —
소스 regex 를 쓰면 서명이 바뀔 때 가드가 조용히 못 찾는다(그 자체가 두 번째 구멍이 된다).

**★ 합치지 않고 연결한 것이 요점이다.** 서빙 정책과 UI 문구는 다른 관심사라 한 곳으로 모으면
오히려 섞인다 — 오너 원칙(2026-08-10) ③이 가드로 실현되는 **세 번째 자리**다(라벨표 ·
`target_type` 분류 · 상한).

### H2 — flake 는 테스트 설계 결함이었고, 마스킹하지 않고 고쳤다

**원인**: 선택 영역은 값과 **다른 effect** 에서 적용된다
([`DraftEditor.tsx:190-195`](../../../frontend/src/drafts/DraftEditor.tsx#L190) — `pendingSelection`
effect → `setSelectionRange`). 값 도착 직후 `selectionStart` 를 **동기로** 읽으면 그 effect 가 아직
안 돌았을 수 있다. 단독 실행이 green 이고 과부하 전수에서만 깨진 이유가 이것이다.

**처리**: 단정을 `waitFor` 로 감쌌다. **느슨하게 만든 것이 아니다** — 기대값을 `2→3` 으로 바꾼
뮤테이션에서 여전히 재실패한다(정확히 2·4 를 계속 요구한다). 바뀐 것은 *"언제 읽는가"* 뿐이다.

**패턴 스윕**(CLAUDE.md §4): 같은 형태를 **한 곳 더** 찾아 함께 고쳤다(`:1465`, 선택 0–2). 검증이
보고한 것은 한 자리였지만 근본 원인이 같으므로 둘 다 닫았다.

### 뮤테이션 (3종 — 커밋 `4097437` 뒤 실행)

| # | 방향 | 적용한 diff | 재실패 셀 |
|---|---|---|---|
| H1-M1 | under | `log.py` 기본값 `100 → 50`(서버가 덜 주는데 화면은 100 이라 말한다) | `ActivityCeilingClaimTest::test_the_screen_promises_exactly_what_the_service_serves` (1) |
| H1-M2 | under | 프론트 상수 `100 → 250`(화면이 더 준다고 말한다) | 같은 셀 (1) |
| H2-M1 | **검증용** | 기대 offset `2 → 3` — `waitFor` 가 단정을 느슨하게 만들었는지 | `restores a historical source by exact snapshot and code-point offsets` (1) — **여전히 문다** |

매회 전후 `git status --short` 비어 있음, 마지막 원복 뒤 `git diff HEAD` 도 비어 있음.

### Verification

| 검사 | 결과 |
|---|---|
| backend 전수(베타, test-mongo ON) | **`2255 passed / 1 skipped / 2355 subtests in 1024s`** — 종전 `2254/1/2354` 대비 **셀 +1**(상한 가드) · **subtest +1**(검증 기록 `b18cb83`, 코드 무관) |
| frontend 전수 | **`272 passed / 19 files`** — ★ **백엔드 전수와 동시 실행**으로 원 flake 의 과부하 조건을 일부러 재현했고 green |
| `DraftEditor.test.tsx` 단독 | 41/41 |
| `tsc --noEmit` | 통과 |
| `test_docs_indexes.py` | `13 cells / 242 subtests` |
| 계약 | operation **77** · 응답 형태 무변 · **SoT 버전 유지**(v1.7.94 행에 접어 넣었다 — v1.7.90 선례) |

### 아직 안 한 것 (의도)

- **육안 확인** — 프론트 재빌드 선행이고 오너 판단 사안(검증자도 동의했다).
- **F1~F7** — 트리거와 함께 브리프에 산다. **H1 가드가 F1 의 트리거 지점을 실제로 지킨다** —
  커서 페이징 작업이 백엔드 기본값을 건드리면 그 셀이 실패하면서 *"화면 문구도 같이 고쳐라"* 를
  말해 준다.

### Next steps

1. **미검증 구간이 없다** — 9.1 은 구현·검증·hardening 폐쇄까지 끝났다.
2. 남은 것은 **육안 확인 하나**(재빌드 후 `/projects/:id/activity`)와 오너 대기 두 건
   (`curl :5520/api/admin/users` = 401 · dogfood 착수).
