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
- 백엔드 전수는 아래 세션 마감에 기록.

### Next steps

- **Slice 1**(탈퇴 요청·취소 API): 라우트 둘 + `activity/actions.py` 등재 + `test_auth_api.py` tier 전수 가드 등재. 유료 경로가 아니므로 quota 분류표는 대상이 아니다. `WithdrawalNotRequested` → 409, `LastActiveAdmin` → 409(관리자 비활성화 선례와 같은 코드).
- Slice 2~5 는 계획서 순서 그대로.
