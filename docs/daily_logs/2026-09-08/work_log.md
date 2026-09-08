# 2026-09-08 작업 로그

## 목표

- HANDOFF Next Tasks **11번(셀프 계정 탈퇴 + 30일 유예 파기)** 의 **Slice 0 — 상태 축과 계약**을 연다. 착수 순서 정본은 HANDOFF 머리말(*"11번 → 12번 → 10번 → S-2"*)이고, 11번 안의 순서는 [`plans/account-withdrawal-implementation-phases.md`](../../plans/account-withdrawal-implementation-phases.md) 다(D4 는 2026-09-07 에 닫혔다).
- Slice 0 의 인계 문장이 곧 완료 기준이다: **"이 슬라이스는 상태만 만든다. 아무것도 지우지 않는다."**

---

## 세션 39 — 계정 탈퇴 Slice 0: 상태 축과 경계 판정 (SoT v1.8.45)

### 1. 착수 전 — 계획서 두 줄이 어긋나 있었다

계획서 **Slice 0** 은 *"유예 기간 30일은 상수 한 곳에 두고 **정책 문서 §6 이 그것을 가리키게 한다**(§1~7 과 같은 방식이라 값 대조 가드가 그 순간 자동으로 잠근다)"* 라고 적었는데, **Slice 5** 는 *"정책 문서 §8 의 계정 탈퇴 행을 **§6 으로 올리고** 정본 포인터를 단다"* 를 자기 범위로 적었다. 같은 편집을 두 슬라이스가 자기 것이라고 말한다.

**정책 문서 자신이 심판이다.** 문서 머리말과 §8 절 머리가 **같은 규칙을 두 번** 박아 두었다 — *"§1~§7 은 코드가 **지금 시행하는 것**이고 §8 은 오너가 정했지만 아직 코드에 없는 것이다. 섞으면 문서가 시행되지 않는 약속을 시행 중인 것처럼 말한다."* Slice 0 이 끝나도 **셀프 요청 경로도 파기 데몬도 없으므로 탈퇴는 시행 중이 아니다.** 여기서 §6 으로 올리면 문서가 없는 기능을 시행 중이라고 말한다.

→ **승격은 Slice 5 에 남긴다.** 다만 계획서의 *의도*(30일이 그 순간부터 잠긴다)는 버리지 않고 **핀 셀**로 받는다. 이 저장소의 계약 리터럴 선례 그대로다(`MIN_PASSWORD_LENGTH`·`MAX_PENDING_SIGNUPS`·`SCENE_NOTE_MAX_CHARS` — 상징 참조 셀은 상수를 60일로 바꿔도 자기 자신과 비교하느라 초록이다). 셀 docstring 에 **"시행되면 이 셀의 자리가 바뀐다 — §6 승격 시 `test_service_policy_contract.py` 가 대조를 맡는다"** 를 적어 두어 Slice 5 가 중복 정본을 만들지 않게 했다.

**오너 판단이 필요한 자리는 아니다** — 두 문서가 충돌한 것이 아니라 **계획서 한 줄이 정책 문서의 확정 규칙을 몰랐던 것**이고, 규칙 쪽이 명시적 정본이다. 계획서 Slice 0 항목을 그에 맞게 고쳤다.

### 2. 착수 전 실측 — 계획서의 실측 셋 외에 확인한 것

- **`UserRepository` 구현체는 정확히 둘**(`InMemoryUserRepository`·`MongoUserRepository`)이고 테스트에 다른 가짜가 없다 → seam 을 넓혀도 조용히 빠지는 구현이 없다. (`grep -rn "set_status\b"` — 다른 히트는 `quota/policy.py` 의 동명 무관 메서드뿐)
- **`User` 생성 지점은 4곳**(`create_user`·`request_signup` 신규/재요청·`_entry`)이고 전부 키워드 인자다 → 기본값 `None` 필드는 무변이다.
- **`AdminUserPayload` 는 필드를 명시 열거**한다(`api/models.py:205`) → Slice 0 이 응답 계약을 건드리지 않는다. operation 102 무변.
- **가입 재요청 경로와 안 만난다**: 재요청은 `status == rejected and is_active` 인 행에만 열리는데, 탈퇴 요청은 **로그인한 활성 계정**만 낼 수 있다(거절된 행은 세션을 못 얻는다). 재요청이 만드는 대체 행이 새 필드를 생략해 `None` 이 되는 것도 그래서 옳다 — 새 가입 요청이지 이어지는 탈퇴가 아니다.

### 3. 설계 판단 셋

**① `withdrawal_requested_at` 은 `is_active` 도 `status` 도 아닌 세 번째 축이다.**
접으면 두 계약이 깨진다 — 유예 중에도 **로그인해서 취소할 수 있어야 하고**(D1=C), `is_active` 는 **단방향**이 계약이라(D6=A) 되돌릴 수 있는 상태를 거기 얹으면 "비활성화는 단방향" 이 거짓이 된다. `status` 는 *가입이 승인됐는가* 를 답하는 축이라 해결된 행은 다시 안 바뀌는 것이 불변식이다.

**② 유예 산술은 한 곳(`purge_due_at`)** — 두 번 하면 화면의 "남은 N일"과 데몬의 "오늘이 그날인가"가 다른 날을 말한다. `activity` 창 문구가 백엔드 기본값과 두 겹으로 잠긴 것과 같은 계열의 함정이다.

**③ 판정은 `>=`.** 약속이 *"30일의 유예"* 이므로 30일째가 끝나는 순간 유예가 소진된다. 경계 셀을 **29일·정확히 30일·31일 + 30일 직전 1μs** 넷으로 두어 `>` 과잉 교정과 `-1` 축소 변이가 **각각 다른 기명 셀**에서 물리게 했다.

**④ 재요청 멱등은 "첫 시각 유지"다.** 두 번째 요청이 시각을 다시 찍으면 회원이 두 번 누르는 것만으로 자기 삭제일이 밀리고, 화면의 "남은 N일"이 이유 없이 되돌아간다. 반대로 **취소 뒤 재요청은 새 유예**여야 한다(그때는 상태가 실제로 없어졌다) — 두 셀이 이 구분을 함께 잠근다.

**⑤ 취소는 취소 기록을 남기지 않고 스탬프를 지운다**(D5=A). 그래야 *"취소한 뒤에는 제한이 전부 사라진다 — 별도 규칙이 아니라 상태가 돌아온 결과다"* 라는 확정 계약이 코드 모양 그대로가 된다. 셀 하나가 **취소한 계정이 요청한 적 없는 계정과 구별되지 않음**을 단정한다.

**⑥ D6 은 새 규칙을 안 만든다.** `deactivate_user` 의 `stored.is_active and self._is_last_active_admin(stored)` 를 **조건까지 그대로** 재사용했다. `is_active` 절반을 빼면 이미 비활성인 관리자의 탈퇴를 거부하게 되는데 그는 활성 관리자 인구에 없으므로 **아무것도 지키지 않는 거부**다(그 자리에 `deactivate_user` 의 기존 셀이 이미 있다).

### 4. 구현 (커밋 `9e2bb94`)

| 파일 | 무엇 |
|---|---|
| `auth/models.py` | `User.withdrawal_requested_at: datetime \| None = None` — 기본값 `None` 은 `must_change_password`·`status` 와 **같은 마이그레이션 자세** |
| `auth/users.py` | `WITHDRAWAL_GRACE_PERIOD = timedelta(days=30)` · `purge_due_at()` · `is_purge_due()` · `WithdrawalNotRequested` · seam `set_withdrawal_requested_at` · `UserService.request_withdrawal`/`cancel_withdrawal` |
| `auth/users_mongo.py` | `$set`(None 포함) · `_doc` 등재 · `_entry` 의 `.get` + `_aware()` naive→UTC |

**★ `_aware` 는 일관성이 아니라 수정이다.** `created_at` 의 재라벨링은 주석이 스스로 *"지금 아무것도 비교하지 않으므로 일관성"* 이라고 적어 둔 자리인데, 이 필드는 **`is_purge_due` 가 aware `now` 와 실제로 비교한다.** 빼면 파기 데몬이 탈퇴한 계정마다 `TypeError` 로 죽고, **그 실패는 드라이버가 있는 배포에서만** 드러난다(fake collection 은 넣은 그대로를 돌려준다). 그래서 셀이 **드라이버가 하는 일(tzinfo 벗기기)을 흉내 내고** 비교까지 실행한다.

`$unset` 이 아니라 `$set: None` 인 이유: 두 모양이 `_entry` 의 `.get` 을 지나면 똑같이 읽히므로 쓰기 모양을 **하나로** 둔다. 취소는 *"탈퇴 중이라고 말하기를 멈추는 것"* 이 아니라 *"탈퇴 중이 아니라고 말하는 것"* 이어야 한다.

### 5. 범위 밖으로 둔 것 (Slice 0 의 인계 문장)

라우트·활동 로그 등재·유예 중 접근 제한(D1=C)·파기 데몬·화면·정책 문서 §6 승격은 **전부 Slice 1~5** 다. **아무것도 지우지 않는다** 를 셀 하나가 직접 단정한다(요청 뒤에도 `is_active`·`status` 가 그대로이고 `authenticate` 가 성공한다) — 유예를 `is_active=False` 로 시행하려는 과잉 교정이 **취소 경로를 통째로 잠그는** 것이 이 자리의 함정이고, 그것은 장면 메모의 *"저장 버튼을 '변경 없음'으로 잠그지 말 것"* 과 같은 종류다.

### Issues found

없음. 계획서 실측 셋(파기 본체 한 벌 · 재시도 비멱등 · 원장 축)은 전부 Slice 3 이 만나는 자리이고 Slice 0 은 그 앞이다.

### Decisions

- **계획서 Slice 0 의 "정책 문서 §6" 문장을 Slice 5 로 넘기고 핀 셀로 대체**(위 1절). 정책 문서의 §8/§1~7 지위 규칙이 명시적 정본이라 그쪽을 따랐다. 계획서 해당 항목을 고쳤다.
- **유예 만료 판정은 `>=`**(30일째가 끝나면 유예 소진). 계약 문언 *"30일 유예 뒤 파기"* 의 자연스러운 독해이고, 경계 셀 넷이 양방향을 잠근다.

### 변이 (커밋 `9e2bb94` → 변이 → 원복 → 트리 clean 확인)

전부 **`git status --short` 가 빈 것을 확인한 뒤** 커밋하고 변이했다.

| 변이 | diff | 자리 | 재실패한 셀(이름) |
|---|---|---|---|
| MV-1 리터럴 되돌리기 | `days=30` → `days=60` | `auth/users.py` `WITHDRAWAL_GRACE_PERIOD` | `WithdrawalGracePeriodLiteralTest::test_the_grace_period_is_thirty_days` + 경계 3 + mongo 1 (**5실패**) |
| MV-2 **over-strict** 경계 | `now >= due` → `now > due` | `auth/users.py::is_purge_due` | `PurgeDueBoundaryTest::test_exactly_day_30_is_due` (+ mongo naive 셀) (**2실패**) |
| MV-3 멱등 파괴 | 재요청 조기 반환 2줄 삭제 | `auth/users.py::request_withdrawal` | `WithdrawalStateAxisTest::test_a_repeat_request_keeps_the_first_stamp` (**1실패**) |
| MV-4 naive 재라벨링 제거 | `_aware(doc.get(…))` → `doc.get(…)` | `auth/users_mongo.py::_entry` | `MongoUserRepositoryTest::test_a_naive_stored_stamp_reads_back_aware` (**1실패**) |
| MV-5 옛 행 잠그기 | `doc.get(…)` → `doc[…]` | 같은 자리 | `…::test_a_row_written_before_the_withdrawal_axis_reads_back_as_not_withdrawing` (+ C-6·status 선례 셀 2) (**3실패**) |
| MV-6 **over-strict** D6 | `stored.is_active and _is_last_active_admin(…)` → `stored.is_admin` | `auth/users.py` 두 자리(sed 가 `deactivate_user` 도 함께 바꿨다) | `WithdrawalStateAxisTest::test_a_second_active_admin_makes_the_first_able_to_withdraw` + `ListAndDeactivateTest` 3 (**4실패**) |
| MV-7 취소 no-op | `set_withdrawal_requested_at(…, at=None)` → `stored` | `auth/users.py::cancel_withdrawal` | `test_cancelling_clears_the_stamp` · `test_a_cancelled_account_is_indistinguishable_from_one_that_never_asked` · `test_cancelling_then_requesting_again_starts_a_new_grace_period` (**3실패**) |

**MV-6 주의**: `sed` 가 같은 문자열을 `deactivate_user` 에서도 바꿔 그쪽 셀 3개가 함께 물렸다. 탈퇴 축의 판정은 **기명 셀 `…first_able_to_withdraw` 가 물었다**는 사실이고, 나머지는 선례 가드가 살아 있다는 부수 증거다.

### Verification

- 신규 셀 **26** (전이 13 · 경계 7 · 리터럴 핀 1 · Mongo 5). `tests/test_auth_users.py` 39→60 · `tests/test_auth_users_mongo.py` 17→22 — 센 것은 **그 두 파일의 `def test` 수**다.
- 초점 전수 **229 passed / 1054 subtests**(`test_auth_users`·`test_auth_users_mongo`·`test_auth_api`·`test_create_user_script`·`test_service_policy_contract`·`test_typecheck`, 110초).
- 변이 **7종 전부 기명 셀 재실패** · 매 회 원복 후 `git status --short` 빈 것 확인.
- **백엔드 전수 `2936 passed / 1 skipped / 3876 subtests · EXIT=0`**(알파, 1893초, test-mongo ON). `skip 1 = live Chroma` 하나뿐이라 호스트 패키지 공백은 없다. 출력은 파일로 통째 캡처했다.

### ★ 기준선 줄이 세 슬라이스 동안 뒤처져 있었다 (유도 기록)

전수 뒤 HANDOFF 기준선(**2903 / 3839**)과 실측(**2936 / 3876**)의 차가 **+33** 인데 내가 더한 셀은 **26** 이었다. 7 을 추측으로 덮지 않고 유도했다.

`git worktree add --detach <경로> <리비전>` 으로 옛 리비전을 따로 펼치고 양쪽에서 `python3 -m pytest --collect-only -q` 를 돌렸다(**수집 수 = passed + skipped** 라 31분짜리 전수를 다시 돌리지 않아도 된다).

| 리비전 | 수집 | 무엇이 더해졌나 |
|---|---|---|
| `6eeedf5`(D4 원장 개명) | **2904** | = 기록된 2903 passed + 1 skipped — **기준선은 이 커밋의 값이었다** |
| `285205b`(D4 하드닝 H1·H2) | 2906 | +2 (SoT v1.8.44 의 *"마이그레이션 셀 5→7"*) |
| `8083a94`(actions.py 개수 가드) | 2909 | +3 |
| `5759d9e`(진입점 부트스트랩) | 2911 | +2 |
| HEAD(이 슬라이스) | **2937** | **+26** — 내 셀 수와 정확히 일치 |

**결론: 기준선 줄이 틀린 게 아니라 세 슬라이스가 갱신을 안 했다.** 셀을 더한 슬라이스가 그 줄을 함께 고치는 것이 규칙이고(HANDOFF 계약 절이 README 한 줄에 대해 같은 말을 한다), 이번에 **HANDOFF·README 둘 다** 갱신했다 — README 절차 표의 칸은 `2,903` 처럼 **쉼표가 들어 있어** 순진한 `grep 2903` 이 못 찾는다(실제로 한 번 놓쳤다).

subtest 축(3839→3876, +37)도 같은 방식으로 귀속했다: `test_script_entrypoints.py` 신설 **+29** · 하드닝/가드 두 파일 **+4** · `test_repo_hygiene.py` **+3**(추적 파일마다 subtest 를 내므로 그 사이 문서 커밋들이 파일을 더한 만큼 늘었다) — **내 슬라이스의 subtest 기여는 +1**(새 work_log 파일 한 개가 repo_hygiene 에 한 칸). 나머지 **1** 은 개별 파일까지 못 짚었다. 파일 인벤토리 가드의 성질과 방향이 같아 더 파지 않았다 — **적어 두는 이유는 다음 사람이 같은 1 을 보고 결함으로 읽지 않게 하기 위해서다.**

**★ 그래서 subtest 수는 커버리지 대리지표가 아니다**(HANDOFF 계약 절이 이미 경고하는 바로 그 성질이 여기서 다시 확인됐다): 이 저장소에서 subtest 는 **테스트를 더하지 않아도 문서 파일 하나로 늘어난다.**

---

## 세션 40 — 독립 검증 수령 · 하드닝 H1 폐쇄 (기록 `0bd8153`)

독립 검증 세션이 같은 트리에서 병행으로 돌았고 **판정 합격 · 차단 0**([`verifications/2026-09-08/account_withdrawal_slice0_state_axis.md`](../../verifications/2026-09-08/account_withdrawal_slice0_state_axis.md)). 초점 229/1054·전수 2936/1/3876·경계 행렬 26/26·변이 7종 셀 수까지 재현됐고, 계획서 §6 이관의 심판 근거도 원문 확인됐다.

**★ 병행 세션과 한 트리를 쓸 때의 함정을 하나 실측했다.** 검증자가 문서를 쓰는 도중 내가 문서 가드를 돌려 **9실패**(부모 2 + subTest 7)를 봤다 — 디스크에는 검증 기록이 291건인데 인덱스 문언은 아직 290이던 **중간 상태**였다. 결함이 아니라 **경합**이다. 판별법: 실패가 *"디스크 N vs 문언 N-1"* 모양이면 먼저 `git status --short` 로 **내가 안 만든 파일이 있는지** 본다. 겸하여 내 미커밋 `README.md` 편집(기준선 칸)이 검증자 커밋 `0bd8153` 에 함께 실려 갔다 — 내용은 정확하나, **한 트리를 나눠 쓸 때는 `git add -A` 가 아니라 경로를 지정해 커밋한다**(그렇게 해서 검증자의 미커밋 기록을 내 커밋에 쓸어 담지 않았다).

### H1 폐쇄 — 쓰기면 왕복 셀 (커밋에 포함)

검증자의 **대항 변이 X1**(`_doc` 에서 `withdrawal_requested_at` 등재 제거)이 **0실패**였다. 내 Mongo 셀이 전부 `set_withdrawal_requested_at`(=`find_one_and_update`)로 값을 넣어 **`_doc` 을 한 번도 지나지 않았다** — 전형적인 빈 셀이다.

- **왜 지금 닫는가**: 지금은 `insert`·`replace` 가 쓰는 값이 늘 `None` 이라 무해하지만, **`replace` 는 행을 통째로 덮는다**. Slice 1 이후 탈퇴 상태를 든 행이 그 경로를 지나면 **스탬프가 조용히 사라지고**, 파기 예정 계정이 예정에서 빠진 것을 아무도 못 본다. 검증자는 Slice 1 로 미뤄도 된다고 했으나 **셀 하나로 닫히는 내 슬라이스의 구멍**이라 여기서 닫았다.
- **처방**: `insert`(스탬프를 든 채) → 읽기 + **저장면 키 직접 확인** → `replace`(다른 시각) → 읽기. `_doc` 을 지나는 두 경로를 모두 왕복시킨다.
- **재검증**: X1 재적용 → `test_the_write_face_carries_the_stamp_through_insert_and_replace` **1실패**(종전 0실패) → 원복 → 트리 clean.

### H2 — 받아 적고 열지 않는다 (트리거 있음)

`request_withdrawal` 의 첫 시각 보존은 **읽기-쓰기라 원자적이지 않다**(동시 첫 요청 둘 → 나중 시각이 이긴다). **지금 열지 않는 이유**: 도달 경로가 없다(Slice 1 전이라 HTTP 표면 자체가 없고, 생기면 같은 동작 5초 최소 창이 연속 클릭을 429로 막는다). **트리거**: *"Slice 1 이 이 전이를 유료 아닌 경로로 열면서 확인 헤더 재전송을 허용하는 순간"*, 또는 **Slice 3 데몬이 같은 행을 경쟁적으로 claim 하게 될 때** — 그때 필요한 것은 잠금이 아니라 **조건부 갱신**(`withdrawal_requested_at` 이 없을 때만 set)이고, 그것은 저장소 seam 의 모양을 바꾸는 결정이라 Slice 1 착수 브리프에서 다룬다.

### CHANGELOG 를 안 쓴 판단 — ❌ **틀렸다(2026-09-08 세션 42 정정)**

> **아래 단락의 근거가 사실이 아니다.** *"D4 도 CHANGELOG 행이 없다"* 고 적었는데 **D4 는 행을 갖고 있다**(`계정 탈퇴 D1~D6 확정 + 원장 소유 축 개명(SoT v1.8.43)`). 잘못 추측한 문구로 grep 해 0건이 나온 것을 *"선례 없음"* 으로 단정했다. 이 저장소의 관행은 **SoT 버전이 오르는 슬라이스마다 한 행**이고 코드 무변 문서 슬라이스까지 포함한다. Slice 0·1 을 묶은 행을 세션 42 에서 실었다. 경위는 세션 42 ③.
>
> **원문을 지우지 않고 남긴다** — 틀린 판단이 어떤 모양이었는지가 교훈의 일부다.

**Slice 0 은 CHANGELOG 행을 만들지 않는다.** 기록 규칙이 *"major design or feature changes (not every small edit)"* 이고, 이 슬라이스는 **사용자에게 보이는 것이 하나도 없는 백엔드 상태 축**이다. 바로 앞 선례가 같은 성질이었고 같은 판단을 받았다 — ~~**D4(원장 소유 축 개명)도 CHANGELOG 행이 없다**(SoT v1.8.43 만 있다)~~. 탈퇴 기능의 CHANGELOG 행은 **화면이 붙는 Slice 4~5 에서** 한 번 쓴다. *(검증자가 "행이 오는지 확인해 달라"고 남긴 열린 질문에 대한 답이다 — 누락이 아니라 판단이다.)*

### 별건 — 개발 스택이 8일 내려가 있었다 (검증자 발견·복구)

검증자가 인프라 6컨테이너(`mongo`·`application`·`gateway`·`chroma`·`elasticsearch`·`embedding`)가 내려가 있는 것을 발견해 복구했다. **주장을 직접 확인했다**(작업자의 보고를 그대로 받지 않는다):

- `docker inspect` 실측 — 그 여섯은 **2026-09-08T00:2x 에 재생성**됐고 지금 `unless-stopped` 를 든다. 나머지(`frontend`·`worker`·`generation_worker`·`admin`)는 2026-08-11·08-26 생성인데도 이미 `unless-stopped` 다.
- `git show 1a0b94a` — 그 커밋(2026-09-06)이 정확히 **정책이 없던 다섯**(mongo·application·gateway·chroma·elasticsearch)에 `restart` 를 더했고, 이미 갖고 있던 넷이 위의 넷이다. **HANDOFF 가 경고하던 함정이 그대로 터진 것**이다 — 파일은 고쳤지만 **그때 떠 있던 컨테이너는 재생성 전까지 옛 정책(`no`)을 든다.**
- **이 머신은 재생성으로 닫혔다(실측).** **배포 호스트는 미확인**이고 여기서 잴 수 없다 → HANDOFF 함정 절에 실측 근거와 함께 올렸다.

### Verification (세션 40)

- `tests/test_auth_users.py`·`test_auth_users_mongo.py` **83 passed**(신규 1 포함, 26→**27셀**) · `test_docs_indexes.py` **15 passed / 301 subtests**.
- 변이 X1 재적용 → 기명 셀 1실패 → 원복 → `git status --short` 공백 확인.
- **백엔드 전수 재측정 `2937 passed / 1 skipped / 3878 subtests · EXIT=0`**(알파, 1661초). H1 셀을 세션 39 전수 **뒤에** 더했으므로 기준선 한 칸을 추정으로 고치지 않고 다시 쟀다. **증분이 전부 설명된다**: 셀 **+1**(H1) · subtest **+2** — 검증 기록 파일이 커밋되며 추적 대상이 돼 `test_repo_hygiene`(파일마다 subtest)과 `test_docs_indexes`(검증 목록)가 각각 하나씩 늘었다. **테스트를 안 더해도 문서 파일 하나로 subtest 가 는다**는 세션 39 의 관찰이 같은 날 두 번째로 확인됐다.
- HANDOFF 기준선 · README ② 행 둘 다 이 값으로 갱신했다.

---

## 세션 41 — 계정 탈퇴 Slice 1: 요청·취소 API (SoT v1.8.46)

오너 *"진행시켜"*. 오너가 답할 것이 없는 유일한 큰 덩어리라 Slice 1 로 읽었다(약관 대괄호 넷은 오너만 채울 수 있어 진행 불가).

### 1. 착수 전 — 계획서 체크리스트가 프로젝트 축 계약을 몰랐다

Slice 1 검증 목록에 *"활동 로그 기록"* 이 있는데 **불가능하다.** `activity_events` 는 `project_id` 를 쓰는 **프로젝트 축**이고 파기와 함께 사라진다(D8-6 I1) — 탈퇴는 계정 축이라 지목할 프로젝트가 없다. 선례가 이미 셋이다: `/auth/login`·`/auth/logout`·`/auth/signup` 이 전부 `EXCLUDED("not_project_scoped")` 다.

`admin_audit` 도 아니다 — `admin_user_id`·`action: Literal["project_purge","member_quota_policy"]` 를 요구하는 **관리자 행위** 축이고, 셀프 탈퇴는 **행위자가 곧 대상**이라 그 필드가 거짓말이 된다. 넓히려면 Literal 을 늘리고 `admin_user_id` 를 optional 로 만들어야 하는데 그것은 감사면의 성격을 바꾸는 일이다.

→ **사유와 함께 EXCLUDED 등재.** 브리프가 필요한 갈림길이 아니라 **계약이 이미 정한 것**이고, 체크리스트 문언이 그 계약을 몰랐던 것이다.

### 2. 설계 판단

**① 경로가 대상을 지목하지 않는다.** `/me/withdrawal` 이라 주체는 세션이 정하고 남의 계정을 향한 요청은 **만들 수 없다** — 그래서 403 이 없다. 계획서의 *"타인 403"* 은 이 모양에서 **도달 불가**이고, 그것을 두 면으로 잠갔다: 행위 축(두 사람이 각각 요청해도 서로에게 안 닿는다)과 **선언 축**(`route.responses` 에 403 이 없다). 선언 셀이 있어야 나중에 403 을 더하는 과잉 교정이 물린다 — 실제로 MW-3 에서 6 subtests 가 물었다(내 셀 2 + 기존 경계 행렬 4).

**② 200 이지 201 이 아니다.** 재요청은 새 자원을 만들지 않는다. 201 이면 재요청이 무언가를 새로 만든 것처럼 읽히고 화면의 *남은 N일* 이 되돌아간 것처럼 보인다.

**③ 취소 없는 취소는 404 가 아니라 409.** 계정은 **있고** 취소할 것이 없을 뿐이다. 404 면 *"그런 회원 없음"* 으로 읽힌다 — `SignupNotPending` 이 해결된 가입 요청에 409 를 주는 것과 같은 선례.

**④ `purge_due_at` 를 응답에 싣는다.** 유예의 정본이 서버 상수 한 곳이라, 프런트가 30 을 박으면 두 번째 정본이 생기고 상수를 고친 날 화면만 다른 날짜를 말한다.

### 3. ★ 내 처방이 한 번 무가드였다 (MW-4)

H2(첫 시각 보존의 원자성)를 저장소 조건부 쓰기(`only_if_absent`)로 닫고 **커밋 메시지에 "닫는다"고 썼는데**, 변이 MW-4(조건부 → 무조건)가 **83셀 전건 통과**했다. **처방만 넣고 셀을 안 둔 것이라 그 시점의 H2 는 닫힌 적이 없다** — 검증자가 X1 로 잡았던 것과 **같은 종류의 빈 자리**이고, 같은 슬라이스 안에서 두 번째다.

규칙대로 **먼저 "변이가 안 먹었나"를 의심**했다 — 재적용 후 `grep` 으로 427행이 실제로 `only_if_absent=False` 가 된 것을 확인했다. 변이는 정확히 먹었고 **가드가 없는 쪽이 맞았다.**

셀 6을 붙여 닫았다:
- **seam 조건 자체** — 이미 찍힌 계정에 조건부 쓰기가 거부되고 옛 시각이 남는다. over-strict 짝 둘: 없을 때는 찍혀야 하고(첫 요청), 무조건 쓰기는 여전히 덮어야 한다(**취소가 그 경로다** — 조건을 전역으로 켜는 과잉 교정이 취소를 잠근다).
- **서비스가 그 조건을 실제로 쓰는가** — `get_by_id` 가 한 번 낡은 값을 주게 해 **조기 반환을 지나치게** 만든다. 동시 요청 둘 중 늦게 쓰는 쪽이 정확히 그 상태이고, 그 뒤 계정을 지키는 것은 조건부 쓰기 하나뿐이다.
- **Mongo 필터** — 조건이 질의로 내려가는가, 그리고 **키가 없는 옛 행도 고르는가**. 후자를 놓치면 **기존 계정 전부가 탈퇴를 요청하지 못하고** 첫 요청이 조용히 실패한다(`_entry` 가 `None` 과 키 없음을 같은 값으로 읽으므로 쓰기면도 같아야 한다).

**★ 남는 교훈**: *"처방을 넣었다"* 와 *"닫았다"* 는 다른 말이다. 이 저장소에서 그 둘을 가르는 것은 변이 하나뿐이고, **자기 처방에도 변이를 걸어야 한다** — 검증자가 잡아 준 자리를 고치면서 같은 병을 반복했다.

### 4. 닫히지 않는 것도 계약에 적었다

조건이 *"없을 때만"* 이라 **취소를 가로지르는 지연 요청은 여전히 걸린다**(A 가 읽고 멈춘 사이 B 가 찍고 사용자가 취소하면, 깨어난 A 가 다시 찍는다). 처음 쓴 주석은 이것까지 막는다고 **과장했고 틀렸다** — 취소 뒤엔 필드가 다시 `None` 이라 조건이 통과한다. 정정해서 *막는 것* 과 *안 막는 것* 을 나눠 적었다. 결함이 아니라 순서의 모호함이다(저장소가 보기에 늦게 온 요청과 새 요청은 같고, 계정은 그 뒤로도 취소할 수 있다). 막으려면 요청마다 토큰이 필요한데 그 값을 살 피해가 없다.

### 변이 (커밋 → 변이 → 원복 → clean, 매회 프리플라이트 공백 확인)

| 변이 | diff | 재실패한 셀(이름) |
|---|---|---|
| MW-1 멱등 파괴 | 조기 반환 삭제 + `only_if_absent=False` | API `test_a_repeat_request_is_idempotent…` · 도메인 `test_a_repeat_request_keeps_the_first_stamp` · `test_the_service_survives_a_stale_read…` (**3**) |
| MW-2 취소 no-op | `WithdrawalNotRequested` raise 삭제 | `test_cancelling_without_a_request_is_409_not_404` · `test_the_subject_is_the_session_not_a_path_argument` · `test_cancelling_an_account_that_never_asked_is_refused` (**3**) |
| MW-3 **over-strict** 403 선언 | `_ERRORS_WITHDRAWAL` 에 `403` 추가 | `test_neither_operation_declares_a_403` 2 + 기존 경계 행렬 `ProjectAuthorizationTest`·`CombinedBoundaryMatrixTest` 각 2 (**6 subtests**) |
| MW-4 조건부 → 무조건 | `only_if_absent=False` | **셀 추가 전 0실패**(무가드) → 추가 후 `test_the_service_survives_a_stale_read_of_a_withdrawing_account` (**1**) |
| MW-5 활동 등재 제거 | `ExcludedOperation` 2행 삭제 | `test_every_mutating_operation_is_classified` · 절 주석 subtest · 머리 수 (**3**) |
| MW-6 Mongo 조건 제거 | 필터 한 줄 → `pass` | `test_a_conditional_stamp_is_decided_by_the_query_not_the_caller` (**1**) |

### Verification (세션 41)

- 신규 **17셀**(API 11 · 도메인 4 · Mongo 2). `test_auth_api.py` +11 · `test_auth_users.py` 27→31 · `test_auth_users_mongo.py` 23→25.
- 초점 전수 **283 passed / 1244 subtests**(auth_api·auth_users·auth_users_mongo·activity_actions·activity_log·billable_actions·typecheck, EXIT=0).
- `schema.d.ts` 재생성 후 `npx tsc --noEmit` **rc=0**. **★ `cwd` 가 `frontend/` 로 남는다** — 함정 절이 경고하는 자리라 이후 명령을 전부 절대경로로 썼다.
- 변이 6종 기명 재실패(위 표) · 매회 원복 후 트리 clean.
- **백엔드 전수 `2954 passed / 1 skipped / 3900 subtests · EXIT=0`**(알파, 1371초). `skip 1 = live Chroma` 하나뿐.
- **증분 22 를 전부 귀속했다**(추정 없이 커밋 전후 실측 — `git worktree add --detach <경로> 936ae4f`):

  | 축 | 이전 → HEAD | 무엇 |
  |---|---|---|
  | 셀 | 2937 → **2954**(+17) | 내 신규 셀과 **정확히 일치**(API 11 · 도메인 4 · Mongo 2) |
  | subtest, 경로 순회 가드 5파일 | 1341 → 1359(+18) | `test_auth_api`·`test_activity_actions`·`test_admin_surface_separation`·`test_billable_actions`·`test_app_import_paths` |
  | subtest, 나머지 4파일 | 827 → 831(+4) | `test_application_api`·`test_quota_enforcement_api`·`test_observability_kpi`·`test_prompt_templates` |

  **★ 전부 "새 operation 2 × 순회 자리" 다.** 내 셀이 직접 낸 subtest 는 **2** 뿐이고(`test_neither_operation_declares_a_403` 가 POST·DELETE 를 각각 단정), 나머지 20 은 **기존 가드들이 늘어난 operation 을 도는 것**이다 — `test_auth_api` 안에서만 전 operation 순회 × subTest 자리가 **4곳**이다(`_operations()` 3 · `_tiers()` 1).

  이로써 오늘 같은 관찰이 **세 번째**다: subtest 수는 커버리지 대리지표가 아니다. 문서 파일 하나로도(세션 39·40), **operation 하나로도** 는다.
- HANDOFF 기준선 · README ② 행 둘 다 이 값으로 갱신했다.

---

## 세션 42 — Slice 1 독립 검증 수령 · 기록 정확성 3건 보강 (기록 `f55ad01`)

독립 검증 **판정 합격 · 차단 0**([`verifications/2026-09-08/`](../../verifications/2026-09-08/)). 초점 283·전수 2954/1/3900·403 부재 계약·계획서 두 줄 정정·등재 6축·변이 9종(구현자 6 재유도 + 대항 3)이 전부 재현됐고, **내 자기포착(MW-4 무가드)의 폐쇄가 셀 수준에서 실증**됐다(X1·MW-4 각 1실패).

비차단 지적 셋을 **그대로 받지 않고 직접 확인**한 뒤 전부 반영했다.

### ① 초점 "277" 은 낡은 측정이었다 — 확인

세션 41 이 적은 277 은 **H2 셀 6개 커밋(`374d93f`) 이전 트리**에서 잰 값인데 마감 기록까지 흘러들었다. 최종 트리 재측정 **283**(277+6 정확히 성립, subtests 1244 불변). 표기 문제이지 잠금 문제가 아니다.

**★ 교훈은 순서다** — 초점 전수를 *셀을 더하기 전에* 재고 그 수를 마감 기록에 옮겨 적었다. 셀을 더하는 커밋이 뒤에 오면 **그 앞의 모든 측정치가 낡는다.** 마감 기록의 수는 **마지막 커밋 뒤에** 다시 잰다.

### ② 변이 표 MW-1 "2실패" 도 같은 낡음 — 확인

최종 트리 재측정 **3**(경쟁 재현 셀 `test_the_service_survives_a_stale_read_of_a_withdrawing_account` 가 추가로 문다 — MW-1 이 조기 반환과 조건부 쓰기를 **함께** 되돌리므로 당연히 그 셀도 걸린다). ①과 같은 뿌리다.

### ③ ★ CHANGELOG 판단이 틀렸다 — 잘못 추측한 grep 하나 위에 세운 결론

세션 40 에서 *"Slice 0 은 CHANGELOG 행을 만들지 않는다"* 고 적으며 근거로 **"D4 도 CHANGELOG 행이 없다"** 를 들었다. **사실이 아니다.** D4 는 행을 갖고 있다 — `| 2026-09-07 | **계정 탈퇴 D1~D6 확정 + 원장 소유 축 개명(SoT v1.8.43).**` 이고, D4 하드닝(v1.8.44)도 별도 행이며, **코드가 전혀 안 바뀐 문서 슬라이스**(v1.8.40·v1.8.41·v1.8.42)까지 행이 있다.

**왜 놓쳤나**: `grep "원장의 소유 축 개명\|target_user_id" CHANGELOG.md` 로 찾았는데 실제 문구는 *"원장 소유 축 개명"*(**의** 없음)이었다. 0건이 나오자 **"선례 없음"으로 단정**했고 그 위에 판단을 세웠다.

**★ 남는 교훈**: *"grep 이 0 건"* 은 **"없다"가 아니라 "내가 추측한 문구가 없다"** 이다. 부재를 근거로 판단할 때는 **넓은 축으로 한 번 더** 본다(여기서는 `grep -o "^| 2026-09-07 | \*\*[^*]*\*\*"` 로 그날 행 전체를 보는 것 — 11행이 한눈에 나왔고 D4 가 그 안에 있었다). 이 저장소의 실제 관행은 **SoT 버전이 오르는 슬라이스마다 한 행**이다.

→ Slice 0·1 을 **묶은 행 하나**를 CHANGELOG 에 실었다(두 SoT 버전을 함께 명기 — 검증자 권고는 1행, 저장소 관행은 버전당 1행이라 양쪽을 만족시킨다). 세션 40 의 그 판단 단락은 **틀린 근거를 남기지 않도록** 정정 표시와 함께 고쳤다.

### Verification (세션 42)

- 초점 7파일 재측정 **283 passed / 1244 subtests**(89초).
- MW-1 최종 트리 재측정 → 기명 셀 **3실패** → 원복 → 트리 clean(프리플라이트 공백 확인).
- CHANGELOG 선례를 그날 행 전체 열거로 재확인(11행 중 D4 행 실재).
- `test_docs_indexes` 는 CHANGELOG 행 추가 뒤 함께 돌린다.

---

## 세션 43 — 열린 결정 전부에 브리프를 붙였다 (오너 지시)

오너 지시: *"남은 브리프들 다 써주고, 핸드오프에 다음작업에 내가 확인해야한다고 해줘. 너 작업은 브리프까지다."*

### 1. 착수 전 실측 — 브리프가 **하나도 없었다**

HANDOFF ⚠️ 오너 결정 표의 9행 중 `docs/plans/*-decisions.md` 브리프를 가진 것이 **0개**였다. 선택지는 표 칸에 ⓐⓑⓒ 로만 적혀 있고 정본 열은 브리프가 아니라 **근거 기록**(검증 파일·SoT 버전·소스 파일)을 가리켰으며, **셋은 근거조차 `—`** 였다(휴면 디렉터리 · `docs/plans` 재편 · llama 리비전).

즉 오너가 답하려면 매번 근거를 다시 찾아야 했다. 이것이 오너 지적(*"이미 작성되어있으면 어디있는지까지 알려줘야 대답을 하던 말던 할 거 아냐"*)의 실체다 — 나는 앞선 답에서 **위치를 안 준 것이 아니라 없다는 사실을 안 말했다.**

### 2. 쓴 것 — 브리프 7건

| 브리프 | 결정 | 추천 |
|---|---|---|
| `slice2-withdrawal-grace-read-surface-decisions.md` | 유예 상태를 어디서 읽는가 | **ⓑ 별도 `GET /me/withdrawal`** — 되돌리기 비용이 비대칭(`UserPayload` 는 `LoginResponse` 와 공유) |
| `activity-log-replay-and-partial-decisions.md` | N3 · replay · auto-promote 503 **셋** | D1=ⓑ(선례에 맞춘다) · D2=지금 안 정한다 · D3=ⓐ |
| `k3-context-window-guard-decisions.md` | 창을 모르는 호출 | **ⓓ 신설**(설정 대체값) 또는 ⓐ 유지 |
| `analysis-extractor-alignment-and-gate-exposure-decisions.md` | D4 정렬 · gate 노출 | 둘 다 **트리거 확정이 목적** |
| `landing-page-scope-decisions.md` | 랜딩 범위·푸터 + 대괄호 넷 | D1=ⓒ(정직한 한계) · D2=ⓐ(앱 안 페이지 + 가드) |
| `docs-directory-dormant-and-restructure-decisions.md` | 휴면 셋 · plans 재편 | D1=ⓐ(휴면 명시) · D2=ⓐ(지금 안 한다) |
| `llama-model-revision-pin-decisions.md` | 리비전 고정 | ⓒ 방향이되 **지금 착수 안 함** |

**★ 묶은 기준은 "축"이다.** 활동 로그 셋은 *아무 일도 안 한 요청이 행을 남기는가* 하나의 축이고, 지금 코드가 **두 방향으로 갈려 있다**(accept 는 replay 를 안 남기는데 수동 저장·finalize 는 남긴다) — 따로 답하면 그 갈림이 굳는다. 문서 디렉터리 둘도 *찾을 수 있는가* 한 축이다.

**★ 쓰면서 실측이 두 개를 바꿨다.**
- **K-3 의 동기가 달라져 있었다.** 표에 적힌 선택지 ⓐⓑⓒ 는 전부 *"조회가 언젠가 성공한다"* 를 전제하는데, **배포가 외부 API 라 `/props` 자체가 없다** — 셋 다 실제 동기를 못 푼다. 그래서 **ⓓ(설정 대체값)를 신설**했다. 낡은 선택지를 그대로 옮겨 적었으면 오너가 답해도 문제가 안 닫혔을 것이다.
- **`docs/plans` 재편의 값을 실측했다** — 파일 133 · 인용 **285문서**. 종전 표는 *"1,083건/253파일 중 183개가 과거 검증 기록"* 이라 적었는데, 지금 실측과 세는 단위가 다르다(건 vs 문서). 브리프에는 **오늘 잰 수와 세는 단위**를 함께 적었다.

### 3. HANDOFF — 다음 작업이 오너 확인이라는 것

Next Tasks 머리의 착수 순서를 **"오너 확인이 먼저"** 로 바꾸고 브리프 7건을 **우선순위 표**로 실었다. 이 시점의 특징이 그렇다 — **착수 가능한 항목이 전부 결정 대기로 모였다**(Slice 1 이 닫히면서 Slice 2 가 결정 없이는 못 여는 자리에 섰고, 10·12번은 원래 오너 병목이다). 결정 없이 할 수 있는 것(S-2 · 육안 확인 · 확인용 계정 정리)도 같은 자리에 적었다.

⚠️ 표의 **정본 열 9칸을 브리프 링크로** 바꾸고, 표 머리에 *"답은 브리프에 기록하고 상태를 `Resolved` 로 — 파일 머리 `상태:` 와 plans 인덱스 상태 열이 **둘 다** 바뀌어야 가드가 통과한다"* 를 적었다.

### 4. 가드가 개수 주장 네 자리를 잡았다

브리프 7개를 더하자 `test_docs_indexes` 가 실패했다 — `README.md`(전체·브리프) · `docs/README.md` · `docs/plans/README.md` 넷이 옛 수(126/105)를 들고 있었다. **가드가 유도한 값 그대로** 133/112 로 고쳤다(가드는 `README.md` 를 세지 않으므로 디스크 134가 아니라 **133** 이다 — 내가 처음 쓴 134가 그래서 틀렸고 가드가 잡았다).

### Verification (세션 43)

- `test_docs_indexes` **15 passed / 302 subtests** · `test_repo_hygiene` 초록(브리프에 사설 주소·비밀값 없음).
- 브리프 7건 전부 `상태:` 선언 + plans 인덱스 상태 열 일치(선두 토큰 `Proposed`) — 갈리면 가드가 실패한다.
- **코드 변경 0.** 이 세션은 문서만 만졌다.

---

## 세션 44 — 오너 결정 9건 수령·브리프 확정 (SoT v1.8.47)

세션 43 이 쓴 브리프 7건에 **같은 날 답이 왔다.** 표는 SoT v1.8.47 과 각 브리프의 `✅ 오너 결정` 절에 있다 — **여기 옮겨 적지 않는다**(세 번째 정본이 된다).

### User Decisions and Rationale

- **계정 탈퇴 Slice 2 = ⓑ 별도 `GET /me/withdrawal`** · **활동 로그 D1=ⓑ · D2=유예 · D3=ⓐ** · **`analysis_extractor` 둘 다 유예(트리거 확정)** · **문서 디렉터리 D1=ⓐ · D2=ⓐ** · **랜딩 D1=ⓒ · D2=ⓐ** — 전부 구현자 추천안 채택(*"나머지는 네 추천대로"*).
- **약관 대괄호 넷 확정**: `[운영자]`=entangelk · `[문의 연락처]`=오너 개인 이메일 · `[시행일]`=2026-09-08 · `[추론 서비스 사업자]`=Google.
- **K-3 = ⓐ**(추천 ⓓ 와 다름) · **llama `-hf` = ⓐ 최신 추종**(추천 ⓒ 와 다름). 오너 선택이며 그대로 확정했다.

### ★ 오너 근거의 전제 하나를 정정했다 (결정은 유지)

llama 를 ⓐ 로 고른 근거가 *"어차피 빌드할 때 볼륨으로 들어가서 한 번만 다운로드 받고 할 테니"* 였다. **볼륨 캐시는 맞지만 결론이 안 따라온다** — HANDOFF 함정 절의 실측이 정확히 반대를 적는다: `-hf …:Q4_0` 은 **리비전을 고정하지 않으므로** 캐시에 온전한 모델이 있어도 업스트림 `refs/main` 이 움직이면 **~6.5GB 를 다시 받는다.** *"한 번만 받는다"* 는 **고정(ⓑ·ⓒ)이 주는 성질**이다.

착수 전에 이 점을 오너에게 밝혔고 결정은 유지됐다. **브리프에 정정을 남긴 이유**: 결정은 오너 것이지만 **근거가 틀린 채 남으면 다음 사람이 그것을 사실로 인용한다.** 기록은 *결정 = ⓐ · 근거 = "이 경로는 알파 로컬 기동에서만 물리고 빈도가 낮다"* 로 읽도록 고쳐 두었다(그쪽이 ⓐ 를 실제로 지탱하는 이유다).

**문의 연락처가 개인 Gmail 이라는 점도 함께 밝혔다** — 랜딩 푸터·약관·방침 셋에 나가므로 스크래핑 대상이 된다. 오너 확인 후 그대로 확정했고, **한 값이 7곳에 있다**는 사실(나중에 폼·별칭으로 바꿀 때의 치환 지점)을 브리프에 적었다.

### K-3 = ⓐ 는 **조건부 정당**이라 그 조건을 이행했다

브리프가 ⓐ 를 *"정당하다"* 고 한 조건이 **"가드가 꺼져 있음을 알고 둔다"** 였다. 그래서 HANDOFF 함정 절에 한 줄을 올렸다 — *외부 API 배포에서 컨텍스트 예산 가드는 사실상 걸리지 않고, `exercised: false` 는 과도기가 아니라 정상 상태이며, 예산 초과는 벤더의 400·잘린 출력으로 **원인에서 가장 먼 자리**에 나타난다.* 그 문장이 없으면 다음 사람이 `false` 를 *"아직 안 쟀다"* 로 읽는다.

### HANDOFF 를 어떻게 고쳤나

- **⚠️ 오너 결정 표가 비었다.** 답을 표 칸에 옮겨 적지 않고 **브리프를 가리키는 요약 표**로 바꿨다(옮겨 적으면 두 번째 정본이다). 표 머리에 *"비었다는 것은 상태이지 완료가 아니다 — 새 대기 항목이 생기면 **브리프를 먼저 쓰고** 올린다"* 를 적었다.
- **Next Tasks 머리를 착수 순서로 되돌렸다.** 종전 머리는 *"오너 확인이 먼저"* 였고 그것이 답을 받았다. 지금 순서는 **11번 Slice 2~5 → 12·10번(랜딩+동의 게이트, S-2·AdSense 와 한 창) → 2번 6차 재검증 → 6·8번**.
- **결정이 만든 작은 후속 둘**을 같은 자리에 적었다(독립 슬라이스를 열 크기가 아니라 다음 슬라이스에 얹는다): 활동 로그 D1=ⓑ 시행 · 휴면 디렉터리 인덱스 등재.

### 확정의 경계 — 아직 안 한 것

**값 넷은 확정됐지만 `docs/legal/*.md` 는 그대로다**(`draft-0` · 대괄호 · 미시행 표식). 치환은 **구현**이고 HANDOFF 12·10번의 몫이며, 지금 채우면 `test_service_policy_contract::test_both_drafts_stay_marked_as_unenforced_drafts` 가 실패한다 — **그 가드가 "초안이 시행 중인 문서로 읽히면 안 된다"를 지키고 있고, 시행은 오너가 그 표식을 걷는 것으로 시작한다.** 착수 순서를 랜딩 브리프에 적어 두었다.

### Verification (세션 44)

- **코드 변경 0.**
- 브리프 7건의 `상태:` 가 전부 `Resolved` 이고 [`plans/README.md`](../../plans/README.md) 상태 열과 **선두 토큰이 일치**한다 — 한쪽만 고치면 가드가 실패한다.
- `test_docs_indexes` **15 passed / 302 subtests** · `test_repo_hygiene` 초록(이메일은 위생 가드 대상이 아니다 — 규칙은 사설 호스트 주소뿐임을 확인).
- SoT `v1.8.46 → v1.8.47`, README·HANDOFF 의 버전 핀 둘 함께 갱신.

### Next steps

- **Slice 2**(유예 중 접근 규칙, D1=C): 유예 중 **쓰기와 유료 경로를 막고** 로그인·조회·취소는 연다. **★ 취소 경로가 유예 내내 도달 가능한지를 별도 셀로** — 장면 메모의 *"저장 버튼을 잠그지 말 것"* 과 같은 종류의 함정이고, Slice 1 에도 이미 그 셀이 하나 있다(`test_requesting_deletes_nothing_and_leaves_the_session_usable`). 상태를 읽는 표면(남은 일수)이 여기서 필요해진다 — `/auth/me` 확장인지 별도 GET 인지가 이 슬라이스의 첫 판단이다.
- Slice 3~5 는 계획서 순서 그대로.

---

## 세션 46 — 오너 도그푸드: 채택 400 추적 → 채택 버튼 제거 · 후보 접기 · 본문 상한 6000

> **슬라이스 2(계정 탈퇴) 작업자와 동시 진행.** 워킹트리를 공유하므로 커밋은 **내 경로만
> `git add`** 했고 `git checkout` 은 내 파일(커밋 완료분)에만 썼다. 작업자 파일
> (`api/dependencies.py`·`routers/auth.py`)은 한 번도 건드리지 않았다.

### 1. 오너 보고 — 채택이 400

오너 콘솔: `POST …/writing/accept 400 (Bad Request)`. **화면에는 아무것도 안 떴다.**

**착수 전 확인(추측 금지)**: 배포는 Cloudflare 뒤 다른 호스트라 이 머신에서 로그를 못 본다
(로컬 `application` 컨테이너 6시간 로그는 `/health` 뿐, 프로젝트 id 도 로컬 Mongo 에 없음).
그래서 **detail 문자열을 오너에게 물었다** — 그전에 원인을 하나로 좁히지 않았고, accept 가
400 을 낼 수 있는 자리를 전수로 세어 표로 냈다(`_validate` 9 · 상한 2 · Gate 4 · 컨텍스트
검색 3 · enum 3).

**오너 답**: `400: accepted text would exceed the 4000-character unit limit`.

### 2. "아무것도 안 뜬다" 의 원인 — 어제 고친 그 함정의 형제

400 이 나면 패널은 빨간 상자에 `400: <이유>` 를 **분명히 그린다**([`WritingPanel.tsx`](../../../frontend/src/writing/WritingPanel.tsx) 오류 상자).
그런데 **그 상자는 패널 위쪽**(생성 버튼 아래)이고 **누른 버튼은 맨 아래**였다. 사이에 후보
본문 전체가 끼어 있어 아래에서 누른 사람에게는 화면 밖이다. 오너의 관측 *"바로 안 나오고
슬롯 닫았다 여니까 나오네"* 가 정확히 그 증상이다.

**이것은 2026-09-07 `c23d7bf` 가 고친 것과 같은 결함이다.** 그 커밋은 원인을 정확히 짚고
스크롤·포커스를 넣었는데 **확인 대화(`pendingConfirm`)에만** 넣었고 **바로 옆 오류 상자에는
안 넣었다.** 어제 남긴 교훈(*"동작은 아래, 피드백은 위면 그 피드백은 없는 것과 같다"*)이
하루 만에 형제 표면에서 재발한 것이다. ★ **패턴 스윕이 같은 파일 안에서 멈췄다** — 고친
표면의 *형제 표면*까지 세는 것이 스윕이다.

### 3. 오너 결정 셋

오너에게 (a) 400 의 정체와 지금 뚫는 법(*채택 방식을 "같은 장의 다음 장면 시작" 으로*),
(b) **채택은 저장이 아니라 심사 후 저장**이라 유료인 것(보고서+Gate 재검사+저장),
(c) 복사+저장 경로는 **무료**이고 본문만 남기면 그것으로 충분하다는 비교표를 냈다.

| 결정 | 오너 말 | 반영 |
|---|---|---|
| 채택 버튼 제거 | *"채택은 완전 자동화일때 사용 할 수 있을꺼같아. 일반 사용자에게는 불필요한 항목같아. 버튼을 그냥 없애주고 통로만 열어두자."* | 패널·패드 **양쪽** 버튼 제거. **엔드포인트와 API 클라이언트는 유지** |
| 후보 접기 | *"후보는 접게 해주고"* | 네이티브 `<details>`. 새 후보 기본 펼침 · 패드 항목 기본 접힘 |
| 상한 상향 | *"4000자는 사실 하나의 원고치고는 적은 편이라서 이참에 6000자로 변경하자"* | 상수 하나(env)와 프론트 미러를 6000 으로 |

**정정 하나**: 내가 앞선 답에서 *"채택을 누르면 유료 쿼터 1회가 소진된다"* 고 했는데 **틀렸다** —
차감 조건은 `2xx` **그리고** provider 호출이라(`main.py` settle 미들웨어) 400 은 차감되지 않는다.
다만 400 **이전에** 근거 검색(플래너 호출)은 이미 돌았다. 원장에는 안 남고 기계는 일했다.

### 4. 상한 6000 — 알고 받은 대가

4000 의 근거는 창 안전이 아니라 **이어쓰기 품질**이었다(2026-08-27 실측 정정). 원고는 매
생성마다 **현재 장면 문단 전부 + 직전 5문단**으로 프롬프트에 실린다.

- 4000자 ≈ 2,353 tok = 예산(요청 상한 8192)의 **~29%**
- 6000자 ≈ 3,529 tok = **~43%**

현재 장면이 예산의 절반 가까이를 가져가므로 직전 문단·기억 조각이 그만큼 먼저 밀린다.
**실패가 아니라 조용한 품질 저하**라 셀이 잡지 못한다 — 그래서 두 상수 주석과 HANDOFF
길이 상한 줄에 수치째로 적었다. 오너가 알고 택한 트레이드오프다.

**파생 숫자 정정**: 장면 메모 상한 12000 의 근거가 *"원고 4000 의 3배 = 3 장면"* 이었는데
배수가 2 가 됐다. **12000 은 그대로 뒀다** — 메모는 프롬프트에 실리지 않아 이어쓰기 예산에서
파생된 값이 아니고, 값을 정한 것은 "여러 장면 분량의 재료를 담는다"는 쓰임이기 때문이다.
근거 문장만 고쳤다([`scene-note-decisions.md`](../../plans/scene-note-decisions.md),
`tests/test_scene_notes.py` docstring).

### 5. 무엇을 지웠는가 — 내 변경이 고아로 만든 것만

`accept()` · 멱등키 intent(`intentRef`) · `contextRef`/`acceptContextReady` · `canAccept` ·
`DEFINITIVE_ACCEPT_FAILURES` · `OUTPUT_TYPE` · `DraftEditor.reloadLatest` · 패드의 quota 배선
(`handleQuotaRefusal`·확인 대화·`useMemberQuota`) · `.scratch-recovery-gate`/`-note` CSS ·
`onAccepted` prop 둘. **tsc `noUnusedLocals` 가 고아를 하나씩 지목했고 그것을 목록으로 썼다.**

채택이 사라져 **거짓이 된 문구**도 함께 고쳤다(문구는 코드와 같이 낡는다):
`채택 가능 (pass)`→`통과 (pass)` · 잔여 툴팁에서 채택 제외 · legend `채택 방식`→`이어쓰기 방식` ·
루프 pass 안내 · 문체 참고 문구 · 패드 머리말.

**남긴 것(의도)**: 서버 `POST …/writing/accept`, `acceptWriting` 클라이언트, 백엔드 셀 전부.
HANDOFF 유예 절 머리에 *"완전 자동화가 쓸 통로 — 지우지 말 것 · 되살릴 트리거: 완전 자동화
착수"* 를 박아 뒀다(트리거 없는 유예는 망각이다).

### 6. 복사 실패 문구는 버튼 옆에 — 어제 교훈의 형제 표면을 닫는다

채택을 없애고 그 자리에 [본문 복사]를 넣으면서 **똑같은 함정을 다시 팔 뻔했다**: 복사 실패를
`setError` 로 보내면 그 문구도 **패널 위쪽 오류 상자**에 뜬다. 그래서 `copyError` 를 따로
두고 **버튼 옆**에 그린다. 셀이 위치까지 단정한다(`closest(".candidate-actions")` 는 있고
`closest(".writing-error")` 는 없다) — 문구만 재면 위로 옮겨도 초록이기 때문이다.

**패널 위쪽 오류 상자 자체는 그대로 남아 있다**(생성·Gate 실패용). 그건 생성 버튼 바로 아래라
그 동작에 대해서는 옳은 자리다. HANDOFF 14번에 *"새 하단 동작의 실패는 그 자리에서 말할 것"*
으로 남겼다.

### 7. 변이 — 7종, 전부 기명 재실패

| # | 변이 diff | 자리 | 재실패한 셀(이름) |
|---|---|---|---|
| M1 | `candidate-actions` 에 `<button>채택하고 저장</button>` 추가 | `WritingPanel.tsx` 후보 동작 | `채택 버튼이 없고, 후보에는 복사 버튼이 있다` (1 failed / 51) |
| M2 | 복사 버튼 블록 삭제 | 같은 자리 | `채택 버튼이 없고…` · `Gate 가 통과가 아니어도…` · `복사 버튼이 후보 본문을…` · `클립보드를 못 쓰면…` · `carries the loop's final candidate text into the copy path` · `preserves the candidate and offers retry…` · `enters revise-and-gate only for an eligible finding…` (7 failed / 51) |
| M3 | `<details className="candidate-fold" open>` → `open` 제거 | 후보 접기 | `후보 본문은 기본 펼침이고 접을 수 있다` (1 failed / 51) |
| M4 | `<details className="scratch-recovery-fold">` → `open` 추가 | 패드 접기 | `접힌 항목을 펼치면 본문이 보인다` (1 failed / 10) |
| M5 | `writeText(candidate.text)` → `writeText(instruction)` | 복사 핸들러 | `복사 버튼이 후보 본문을…` · `carries the loop's final candidate text into the copy path` (2 failed / 51) |
| M6 | `RAW_TEXT_MAX_CHARS = 6000` → `4000` | `tokenEstimate.ts` | `warns as the body approaches the limit` · `keeps save disabled for a body already past the limit` (2 failed / 65) |
| M7 | `DRAFT_RAW_TEXT_MAX_CHARS = 6000` → `4000` | `app/env.py` | 백엔드 상한 4셀(`exactly_at_the_limit_saves`·`one_over_the_limit_is_rejected`·`append_composed_exactly_at_the_limit_passes`·`start_next_unit_seed_past_the_limit…`) (4 failed / 9) |

**M2 가 값을 했다** — 복사 버튼을 지우니 *채택 제거* 셀뿐 아니라 **생성·루프 쪽 셀 3개**가
같이 물었다. 이 버튼이 "후보를 꺼내는 유일한 길"이 되면서 여러 흐름의 종점이 됐다는 뜻이고,
그래서 지우면 조용히 넘어가지 않는다.

**M6·M7 은 상한 상수의 양방향을 잠근다** — 반대 방향(문서만 4000, 상수는 6000)은 변이가
아니라 실제로 겪었다: `test_service_policy_contract.py` 가 *"문서가 [4000] 이라고 적었는데
상수는 [6000] 다"* 로 빨개졌고, 그것을 본 뒤 문서를 고쳤다.

### 8. 고쳤지 않고 남긴 것 (관측)

- **패드의 `버리기`·`복사` 는 읽기 전용 원고에서도 눌린다.** 종전에도 `readOnly` 는 **채택
  버튼에만** 걸려 있었고 버리기에는 없었다 — 채택이 사라지면서 `readOnly` prop 이 소비자를
  잃어 제거됐을 뿐 **동작은 종전과 동일**하다. 보관된 원고의 스크래치를 버릴 수 있어야 하는지는
  별개 질문이라 손대지 않았다.
- **패널 위쪽 오류 상자에 스크롤·포커스가 없다.** 오늘 400 이 안 보인 직접 원인이지만, 채택
  버튼이 사라져 *하단 동작의 실패*는 이제 그 자리에서 말한다(위 6절). 생성·Gate 실패는 생성
  버튼 바로 아래라 자리가 맞다. 남은 위험은 **미래에 하단에 동작을 또 더할 때**이고 그 경고를
  HANDOFF 14번에 붙였다.

### 9. 다음 단계

- **배포되어야 오너에게 도달한다** — 이 슬라이스는 전부 프론트 + 상수 하나다. HANDOFF 5번
  배포 항목에 미배포분이 하나 더 쌓였다.
- **채택 설계 질문은 열린 채다**(오너에게 브리프로 내겠다고 했고 오너가 버튼 제거를 택했다):
  *방금 통과한 Gate 를 채택이 다시 사는 것이 맞는가*. 완전 자동화 슬라이스가 이 통로를 쓸 때
  다시 만난다.
- 육안 확인: 후보 접기/펼침, 패드 미리보기 40자 절단, 복사 버튼 문구 전환.
### 10. 전수와 그 대가 — 무엇을 돌렸고 무엇을 안 돌렸는가

**동시 작업의 실제 비용을 적어 둔다.** 슬라이스 2 작업자가 컨테이너에서 백엔드를 돌리는
동안 내가 프론트 전수 + 백엔드 전수를 함께 띄우자 3중 경합이 됐다 — 프론트 전수가 평소
~5분에서 **17분**, 백엔드 전수는 **12분에 13%**(추정 90분)였다. 그래서:

- **백엔드 전수는 중단하고 범위를 지정해 돌렸다**: `test_draft_raw_text_limit` ·
  `test_service_policy_contract` · `test_writing` · `test_writing_accept` ·
  `test_writing_scratch` · `test_scene_notes` · `test_docs_indexes` · `test_repo_hygiene` ·
  `test_application_api` → **344 passed / 1545 subtests**(499초). 이 슬라이스의 백엔드 델타는
  **상수 하나**이고 그 축은 전용 가드 두 방향(M7)과 정책 값 대조 가드 두 방향으로 이미
  잠갔다. **전수는 이 세션에서 돌리지 않았다** — 다음 백엔드 슬라이스가 기준선(2954)을
  다시 잰다.
- **프론트는 전수를 돌렸다**(내 변경이 거기 있으므로). 첫 실행 **446 passed / 3 failed** →
  아래 셋을 닫고 재실행 **449 passed / 38 files, 0 failed**.

**★ 실패 3건 중 2건이 내 등재 누락이었다** — 새 CSS 규칙이 `var(--type-*)` 를 쓰면
`typeScale.test.ts` 이관 목록에 등재해야 하는데(HANDOFF 4번 항목이 *"이번에 실제로 걸렸다"*
고 적어 둔 바로 그 가드), 접기 summary 와 복사 오류 문구를 넣고 등재를 안 했다. 지운 규칙
둘(`.scratch-recovery-note`·`-gate`)도 목록에 남아 있었다. 가드가 **양쪽 방향을 다 잡았다**
— 없는 규칙이 목록에 있는 것도, 있는 규칙이 목록에 없는 것도. 등재 후 4셀 초록.

같은 계열로 **README 의 SoT 버전 한 줄**도 놓쳤다(v1.8.48 → v1.8.49). `test_docs_indexes`
가 잡았다. HANDOFF 기준선 절이 *"README 절차 표의 수는 아무 가드도 안 잡는다"* 고 적어
두었는데 **버전 문자열 쪽은 가드가 있다** — 그 구분을 여기 적어 둔다.

**나머지 1건은 회귀가 아니라 플레이크였다**: `AdminUserDetail > shows only this user's
projects and filters them by name` — 전수에서 **11938ms 타임아웃**, 단독 재실행 **497ms
초록**. 내가 건드리지 않은 화면이고 부하에서 느려지는 계열이라 HANDOFF 미수리 표의 *알려진
플레이크* 행에 **둘째 사례로 등재**했다(첫째는 `PersonalHubPage`). ★ 등재하면서 **경합이
방아쇠였다는 사실**을 함께 적었다 — 다음 사람이 같은 실패를 보고 회귀로 오인하지 않도록.
