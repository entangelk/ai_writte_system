# 계정 탈퇴 Slice 5 — 정책 문서 §8 → §6 승격 독립 검증

**조건부 합격** — 조건 셋: **B1** §6 *"취소는 파기가 시작되기 전까지다"* 가 코드에 없다(무셀 + 미시행 — 파기 청구 뒤에도 취소가 200 으로 통과한다) · **B2** 방침 머리말의 *"제3조 안내 상자는 아직 기능이 제공되지 않습니다"* 가 거짓인 채 회원 화면에 서 있다(HANDOFF 가 그 정리를 **Slice 5 몫**이라 적어 둔 채 Slice 5 를 닫았다) · **B3** `legal/README.md` §8 절이 자기 표와 모순한다(*"남은 전제는 한 줄 = 제3조 안내 상자"* vs 그 행의 `시행 전제` = *없음*, 그리고 전제가 실제로 열린 행은 `추론 경계 밖 전송 고지` 인데 그 전제도 이미 닫혔다).

**승격 자체는 사실에 근거한다** — §6 의 다섯 문장 중 넷(유예 중 권한 · 재요청 멱등 · 판정 경계 · 파기 뒤 잔존)은 코드에서 재확인됐고, 신규 조항↔상수 가드는 변이 재적용으로 실제로 물었다. 핀 셀 존치 논증도 **실측으로 옳다**(문서와 상수를 함께 60일로 바꾸면 정책 가드 10/70 전건 초록이고 핀만 빨개진다). 막는 것은 *승격의 근거* 가 아니라 **§6 문장 하나와 회원이 읽는 면에 남은 거짓 문장**이다.

## Subject metadata

| 항목 | 값 |
|---|---|
| 검증일 | 2026-09-12 |
| 요청자 | 오너(*"다른 AI가 프론트엔드쪽 작업중"* 고지 동반 — 공유 트리 금기 명시) |
| 검증자 | 독립 세션(구현자와 다른 세션. 이 슬라이스의 코드·문서를 쓰지 않았다) |
| 대상 | 커밋 **`e169e96`** *"docs(policy): Slice 5 — 계정 탈퇴를 §8 에서 §6 으로 승격 + 조항↔상수 가드"* |
| 동반 커밋 | `311616d`(SoT 행 번호 v1.8.59→v1.8.60 정정) · `bcd30b2`(기록 — SoT v1.8.60 · work_log 세션 69 · HANDOFF · README ④행) |
| 검증 시작 시점의 트리 | HEAD `e169e96` · **미커밋 7파일**(동시 진행 AI 몫: `CHANGELOG.md`·`HANDOFF.md`·`README.md`·`docs/system-contract-sot.md`·`docs/plans/README.md`·`docs/plans/account-withdrawal-*.md`·`daily_logs/2026-09-12/work_log.md`) |
| 검증 종료 시점의 트리 | HEAD **`bcd30b2`** · 작업 트리 **clean**(검증 중 동시 진행 AI 와 구현자가 각각 커밋했다 — 아래 §Outstanding) |
| 정규 스펙 | [`plans/account-withdrawal-implementation-phases.md`](../../plans/account-withdrawal-implementation-phases.md) §Slice 5·D5 · [`service-policy-contract.md`](../../service-policy-contract.md) §6·§8 · [`legal/README.md`](../../legal/README.md) 대조표 · SoT `v1.8.60` |
| 환경 | WSL2 · `python3 -m pytest`(pytest-subtests) · 라이브 Mongo 없음 · `node_modules` 설치된 상태의 `npx vitest`(단일 파일만) |

## Scope

1. **★ 승격이 사실에 근거하는가** — §6 의 새 문장 다섯을 각각 **코드에서** 확인(문서 대조가 아니라 구현 확인).
2. **★ 신규 가드가 실제로 잠그는가** — 구현자 보고 변이 3종(MU-A·MO-B·MO-C) 재적용 + **검증자가 고른 블라인드스폿 8종**.
3. 핀 셀 존치 논증의 참·거짓(문서와 상수를 함께 움직이면 대조가 초록인가 · 승격된 다른 축도 둘을 드는가).
4. 대조표 양방향 + 신규 `미기재` 행의 **사실성**(약관·방침에 정말 그 조항이 없는가).
5. 머리말 편집(회원이 읽는 면)의 잔여 거짓·낡음 · 프런트 사본 바이트 동일.
6. 보고된 수(9셀/66 → 10셀/70 · 초점 110/1008)의 재실측.
7. 기록 의무(SoT 행 · work_log 세션)의 실제 상태.

## Methodology

읽기는 1차 출처만 본다(구현자 보고는 *반증할 가설*로 취급). 변이는 **`git checkout`·`stash`·`reset`·`clean` 을 한 번도 쓰지 않았다** — 검증 시작 시점에 남의 미커밋 작업이 트리에 있었으므로 가이드의 *남의 트리 감사* 분기(`cp` 백업 → 역방향 복원 → `cmp`)를 썼다. 원복은 전부 절대 경로다.

```bash
cd /mnt/f/devel/ai_writte_system
git show e169e96                      # 대상 전문
git log --oneline -8 && git status --short

# 기준 리비전은 worktree 로(작업 트리를 건드리지 않는다)
git worktree add --detach <scratch>/wt-b6fd464 b6fd464
git worktree add --detach <scratch>/v-0379fe3 0379fe3

# 수 재실측
python3 -m pytest tests/test_service_policy_contract.py -q
python3 -m pytest tests/test_docs_indexes.py tests/test_repo_hygiene.py \
  tests/test_product_name.py tests/test_service_policy_contract.py \
  tests/test_auth_users.py -q
cd frontend && npx vitest run src/legal/legalSource.test.ts

# 변이 절차(매 변이마다)
cp -p <대상> <scratch>/bak2/<대상>          # 먼저 백업
python3 -c "… 새 파일로 써서 치환 …"        # sed -i·perl -i 금지(이 저장소에서 파일 손상 이력)
python3 -m pytest <초점> -q                 # FAILED 와 SUBFAILED 를 함께 읽는다
python3 <scratch>/mut.py restore <키…>      # 백업에서 복원 + cmp 로 바이트 동일 확인
```

`grep -E "^FAILED"` 만 읽지 않았다 — `pytest-subtests` 는 `SUBFAILED(...)` 로 찍으므로 **요약 줄과 `FAILED|SUBFAILED` 를 함께** 읽었다(가이드 §★).

## Findings

### A. 승격은 사실에 근거한다 — 다섯 문장 중 넷은 코드가 실제로 시행한다

§6 의 새 문장은 [`service-policy-contract.md:85-90`](../../service-policy-contract.md) 이다. 각 문장을 코드에서 확인했다.

| §6 문장 | 코드 | 잠그는 셀 | 판정 |
|---|---|---|---|
| (a) 유예 중 로그인·조회·취소는 되고 **일반 쓰기·유료 경로는 403** | `api/dependencies.py:74-90`(`require_active_user_for_write` — GET/HEAD 통과, 그 외 403) · `_REQUIRE_AUTH`/`_REQUIRE_PROJECT_OWNER`/`_REQUIRE_ADMIN` 에 배선(`dependencies.py:351-376`) · 탈퇴 두 operation 만 `_REQUIRE_AUTH_DURING_WITHDRAWAL` 로 면제 | `test_auth_api.py:187`(읽기 200 / 쓰기 403) · `:352`(전수 선언 가드 — 면제 둘만) · `:412`(quota 앞 순서) · `:377`(dependency 이음매 양방향) | **참** |
| (a') **유료 경로** 전건 | 직접 열거: `enforce_quota` 를 단 **11 라우트 전부 POST** 이고 전부 `require_active_user_for_write` 를 앞에 둔다(검증자 실측 — `create_app()` 내성) | `test_auth_api.py:412` | **참** |
| (b) 재요청은 **첫 요청 시각을 지키는 멱등** — 유예가 연장되지 않는다 | `auth/users.py:479-523`(조기 반환 + 저장소 조건부 쓰기 `only_if_absent=True` + 경쟁 패배 시 재읽기) | `test_auth_users.py` 요청·취소 셀군 | **참** |
| (c) 판정 시점은 한 곳이고 **그 시점이 되면** 파기 대상 | `auth/users.py:122-145`(`purge_due_at` 가 유일한 산술 · `is_purge_due` 가 `>=`) · 데몬도 그 함수를 부른다(`deletion/account_purge.py:90-101`) | `test_auth_users.py:868` `PurgeDueBoundaryTest`(29·30·31일) | **참** |
| (d) **취소는 파기가 시작되기 전까지다**(D5) | `auth/users.py:525-546` `cancel_withdrawal` — **`purge_started_at` 을 보지 않는다.** 조건은 *"탈퇴 스탬프가 있는가"* 뿐이다 | **없음** — `tests/test_auth_users.py`·`tests/test_auth_api.py` 에 `purge_started_at` 토큰이 **0건** | **거짓(B1)** |
| (e) 파기 뒤 남는 것 = **사용량 기록 + 사용자명 한 값** | `deletion/account_axis_sweep.py:30-34,43-46`(보존 축은 `target_user_id` — 원장·감사·묘비) · 묘비는 파괴 **앞**에 먼저 남긴다(`account_purge.py:12-14`) | `test_account_purge.py` 순서·잔존 셀군 | **참**(단 코드가 남기는 것은 **셋**이다 — H4) |

셀프 경로·데몬·화면은 모두 실재한다: `routers/auth.py:269-317`(GET/POST/DELETE `/me/withdrawal`) · `scripts/account_withdrawal_worker.py` + `docker-compose.yml:436` 의 `--loop` 서비스 · `deletion/account_purge.py`. **§8("아직 코드에 없는 것")에 남아 있던 것이 거짓이었다는 구현자 주장은 옳다.**

**(d) 의 실측** — 파기가 청구된 계정의 취소가 예외 없이 통과한다:

```
purge_started_at = 2026-10-12 00:00:00+00:00
list_withdrawing (데몬이 보는 목록) = []     ← 데몬은 다시 청구하지 않는다
cancel_withdrawal() 반환 = OK
  withdrawal_requested_at = None            ← 유예 배너 사라짐 · 쓰기 403 해제
  purge_started_at        = 2026-10-12 ...   ← 부분 파기 표식은 그대로
```

즉 **"취소됐다"고 답한 계정이 이미 파기 중/부분 파기 상태**일 수 있다. 경로는 둘이다 — ⓐ 파기 진행 중(행이 아직 살아 있는 수초~수분), ⓑ **파기 실패 뒤 영구 창**(`account_purge.py:21-27` 이 *"실패한 계정은 `purge_started_at` 이 찍힌 채 남는다"* 를 설계로 적는다 — 운영자가 reconciler 를 돌릴 때까지 며칠일 수 있다). 회원 쪽 결과는 *"취소했는데 원고는 없고, 뒤늦게 계정도 사라진다"* 다(`account_purge_reconciler.py:52-56` 은 `purge_started_at != None` 만 보므로 취소와 무관하게 쓸어 간다 — 조용한 고아는 아니지만 **취소가 지켜지지도 않는다**).

D5 원문은 [`plans/account-withdrawal-implementation-phases.md:141`](../../plans/account-withdrawal-implementation-phases.md) *"ⓐ — 파기 실행 전까지 언제나 취소 가능"* 이다. §6 문장은 **오너 결정을 충실히 옮겼고 코드가 그 경계를 시행하지 않는다** — 승격이 이 갭을 §6(시행 중) 으로 들어올렸다.

### B. 신규 가드는 실제로 잠근다 — 변이 11종(보고 3종 재적용 + 검증자 8종)

신규 셀은 [`test_service_policy_contract.py:292`](../../../tests/test_service_policy_contract.py) `LegalDraftCoverageTest::test_the_withdrawal_grace_period_matches_the_constant`(앵커는 `:78 _GRACE_CLAUSE_ANCHORS`).

| 변이 | 적용한 diff(실제 텍스트) | 관측 결과 |
|---|---|---|
| **MU-A**(under) | `users.py:109` `WITHDRAWAL_GRACE_PERIOD = timedelta(days=30)` → `timedelta(days=60)`, 문서 무변 | **7 실패** — `SUBFAILED(axis='계정 탈퇴 유예 기간')`(§6 행 대조) · `SUBFAILED(document='terms-of-service-draft.md')` + `SUBFAILED(document='privacy-policy-draft.md')`(신규 셀, 문서 기명) · `FAILED WithdrawalGracePeriodLiteralTest::test_the_grace_period_is_thirty_days`(핀) · `FAILED PurgeDueBoundaryTest::{test_day_31_is_due, test_exactly_day_30_is_due, test_the_due_date_is_the_request_plus_the_grace_period}`. **구현자 보고와 완전 일치.** |
| **MU-C2**(핀 논증 결정 실험 — 검증자 추가) | MU-A 를 유지한 채 문서도 함께 60일로: 약관 `요청 후 **30일**이 지나면 … 30일 이내에는` → `**60일** … 60일 이내에는` · 방침 `**탈퇴를 요청하면 30일 뒤에 …** 30일 이내에는` → `60일`/`60일` · §6 행 `| 계정 탈퇴 유예 기간 | 30일 |` → `| 60일 |` | **정책 가드 10 passed / 70 subtests 전건 초록.** 실패는 `WithdrawalGracePeriodLiteralTest` 1 + 경계 3 뿐. → **핀 존치 논증은 옳다**(§C) |
| **MO-B**(over) | 약관만: `요청 후 **30일**이 지나면` → `요청 후 **60일**이 지나면`(같은 항의 두 번째 `30일` 은 그대로) | **1 실패** — `SUBFAILED(document='terms-of-service-draft.md')`. 같은 조항 안에서 수가 갈린 것도 문다(집합 `{30,60}` ≠ `{30}`). 보고와 일치 |
| **MO-C**(over) | 수를 유지한 꼬리 문장 다듬기: `요청 후 **30일**이 지나면 계정과 회원이 작성한 문서가 파기됩니다. 30일 이내에는 탈퇴를 취소할 수 있습니다.` → `요청한 날부터 **30일**이 지난 때에 계정 및 회원이 작성한 문서를 파기합니다. 그 30일 동안에는 언제든지 탈퇴 요청을 철회할 수 있습니다.` | **10 passed / 70 subtests 초록 = 거짓양성 없음.** 보고와 일치 |
| **MX-D**(검증자 — 행 통째 삭제) | `service-policy-contract.md:83-86` 의 표 머리 2줄 + `| 계정 탈퇴 유예 기간 | 30일 | \`auth/users.py::WITHDRAWAL_GRACE_PERIOD\` |` + 빈 줄 삭제 | **조용히 통과** — `10 passed, 68 subtests`(실패 0, subtest 만 −2). 포인터가 사라져도 아무 셀도 안 문다. **모듈 docstring(`:22-26`)이 미리 적어 둔 한계**이고 값 자체는 신규 셀+핀이 계속 든다 → 비차단(H3) |
| **MX-E**(검증자 — 포인터 재조준) | 같은 행의 포인터를 `\`auth/users.py::WITHDRAWAL_GRACE_PERIOD\`` → `\`auth/users.py::MAX_USERNAME_LENGTH\`` | **1 실패** — `SUBFAILED(axis='계정 탈퇴 유예 기간')`(적힌 30 vs 상수 64). 재조준은 막힌다 |
| **MX-F**(검증자 — 값 등가 표현) | 약관 `요청 후 **30일**이 지나면 … 30일 이내에는` → `요청 후 **1개월**이 지나면 … 그 기간 안에는` | **1 실패** — `SUBFAILED(document='terms-of-service-draft.md')`(*"조항이 [1] 을 적는데 시행값은 30일"*). 의도된 보수성이지만 약관 개정 시 빨개지는 자리이므로 기록한다(H5) |
| **MX-G**(검증자 — 무해한 표기) | 약관 `**30일**이` → `**30 일**이` | **10/70 초록**. 공백 표기는 통과한다(정상) |
| **MX-H**(검증자 — 대조표 행 삭제, under) | `legal/README.md:34` `| 계정 탈퇴 유예 기간 | 제8조 3항 | 제5조 3항 |` 줄 삭제 | **1 실패** — `FAILED test_the_mapping_table_covers_every_policy_axis`, `AssertionError: ['계정 탈퇴 유예 기간'] != []`. **표 사이 이동 뒤에도 대조표 양방향은 산다** |
| **MX-I**(검증자 — `미기재` 행 삭제) | `legal/README.md:59` `| **유예 중에는 쓰기와 유료 경로가 막힌다** | **미기재** | **미기재** |` 줄 삭제 | **조용히 통과** — 10/70 초록. **공백을 기록한 행 자체는 아무것도 잠그지 않는다** → H2 |
| **MX-J**(검증자 — 앵커 문장 다듬기) | 약관 `3. **회원은 탈퇴를 요청할 수 있습니다.**` → `3. **회원은 언제든 탈퇴를 신청할 수 있습니다.**`(수 무변) | **1 실패** — `SUBFAILED(document='terms-of-service-draft.md')`: *"탈퇴 유예 조항의 자리를 못 찾았다 — 문장을 고쳤다면 이 앵커도 함께 고친다"*. 진단이 값 불일치와 갈라지는 것이 설계이고 메시지가 그것을 말한다. **다만 보고의 *"문장 다듬기는 통과"* 는 앵커 밖 절반에만 참이다** |
| **MX-K**(검증자 — §6 산문 삭제) | `service-policy-contract.md:87` 의 403 문장(`- **유예 중에도 계정은 살아 있다** — … 403 이다. …`) 줄 삭제 | **조용히 통과** — 10/70 초록. §6 산문은 기계가 안 본다(표 행만 본다) → H2 와 같은 계열 |

모든 변이 뒤 **백업에서 복원 + `cmp` 로 바이트 동일 확인**했고, 마지막 전량 복원에서 7파일 전부 `cmp rc=0` 이었다.

### C. 핀 셀 존치 논증 — 옳다(실측)

- **대조 가드는 값을 잠그지 않는다**: MU-C2 가 결정적이다 — 문서(약관·방침·§6 행)와 상수를 **함께** 60일로 옮기면 정책 가드는 `10 passed / 70 subtests` 전건 초록이고, 빨개지는 것은 `test_auth_users.py:633` 핀과 경계 셀뿐이다. 따라서 종전 예고대로 핀을 지웠다면 **30일이라는 값은 어느 셀도 안 들게 됐다.**
- **선례 주장도 참이다**: `MIN_PASSWORD_LENGTH` = §1 행 + 핀 `tests/test_auth_api.py:2603`(`assertEqual(MIN_PASSWORD_LENGTH, 12)`) · `SCENE_NOTE_MAX_CHARS` = §4 행 + 핀 `tests/test_scene_notes.py:154-161`(`assertEqual(SCENE_NOTE_MAX_CHARS, 12000)`). **승격된 축은 둘을 함께 든다**는 문장은 디스크에서 확인된다.
- 정정이 세 곳(핀 docstring `test_auth_users.py:617-629` · 계획서 Slice 0 절 · `service-policy-contract.md` §8 말미)에 적혔는지 확인 — 셋 다 적혀 있다.

### D. 대조표 양방향 · `미기재` 행의 사실성

- **양방향 유지**: MX-H 가 under 방향을 증명한다(정책 축이 대조표에서 빠지면 실패). over 방향(조항 번호만 고치기)은 첫 칸만 보는 구현상 통과하고, 그것이 docstring 이 적은 설계다. `_axes()` 17개 ⊆ `_mapped_axes()` 47개 · `missing == []` 를 직접 계산해 확인했다.
- **`미기재` 행은 사실이다 — 검증자가 직접 훑었다.** 약관·방침 전문에서 유예 중 제한을 적는 조항은 **없다**:
  - 약관 제8조 3항은 *"30일이 지나면 파기 · 30일 이내에는 취소할 수 있습니다"* 까지만 적는다.
  - 가장 가까운 후보 **제4조 4항**은 *"계정이 **정지** 상태가 되면 한도가 남아 있어도 연산이 드는 요청을 이용할 수 없습니다"* 로 **다른 상태**(정지)를 말한다 — 탈퇴 유예를 여기에 끼워 인용하면 거짓이 된다. 제11조(이용 제한)도 제10조 위반에 따른 정지다.
  - 오히려 **제4조 5항**이 *"글을 읽고 **저장**하는 등 연산이 들지 않는 이용에는 위 한도가 적용되지 않습니다"* 라고 적는다 — 유예 중에는 그 저장이 403 이므로, 회원이 읽는 문장과 실제 경험의 거리는 *"안 적혔다"* 보다 한 걸음 더 멀다.
  - 방침에는 해당 축이 없다(제9조는 세션·남용 방지).
  → **인용할 기존 조항이 없으니 조항 문장을 지어내지 않고 `미기재` 로 세운 판단은 옳다.** 다만 그 행 자체가 무셀이다(MX-I) → H2.

### E. 머리말 편집(회원이 읽는 면)

- **약관**: 미제공 고지 줄을 통째로 걷었다. 그 문서에서 미제공이던 조항은 제8조 3·4항뿐이고 둘 다 이제 참이므로 **옳다**(잔여 거짓 없음).
- **방침**: `privacy-policy-draft.md:10` 이 **여전히** *"다만 제3조 안내 상자는 아직 기능이 제공되지 않습니다 — 가입 절차의 동의 기록이 그것입니다."* 라고 적는다. **거짓이다** — 동의 게이트는 `58a8ac9`(이 슬라이스보다 **앞선** 커밋)에서 시행됐다: `auth/users.py:385`(`agreed_terms_version != TERMS_VERSION` → 거부) · `:413,436`(`terms_agreed_at`·`terms_version_agreed` 저장) · `api/models.py:90`. 그리고 *안내 상자* 자체는 **기능이 필요 없는 사실 진술**이라 어느 쪽으로 읽어도 참이 아니다. → **B2**
- **프런트 사본 둘은 바이트 동일**: `cmp docs/legal/terms-of-service-draft.md frontend/src/legal/terms-of-service.md` → 동일 · privacy 도 동일(md5 `d54e8f9d…` / `91245df6…` 쌍). `npx vitest run src/legal/legalSource.test.ts` → **4 passed · EXIT=0**(26.8초). 파일명이 `-draft` 없이 다른 함정도 실제로 지켜졌다.
- **`legal/README.md` 의 낡음 둘** → **B3**:
  - `:69` *"**남은 전제는 한 줄이다**(2026-09-12) — 방침 제3조 안내 상자, 즉 가입 절차의 동의 기록이다."* ↔ 같은 절 표 `:74` 의 그 행 `시행 전제` = *"없음 — '소급하지 않는다' 는 사실을 적은 것이라 지금도 참이다"*. **같은 파일 안의 모순**이고 이 커밋이 새로 넣은 문장이다.
  - 전제가 실제로 적힌 유일한 행은 `:73` `추론 경계 밖 전송 고지 … | 가입 동의 게이트 구현(HANDOFF 10번)` 인데 **그 게이트는 닫혔다**(HANDOFF `:304` 가 *"완료(2026-09-12, SoT v1.8.59)"* 라고 적는다). 즉 §8 세 행 중 **열린 전제는 0개**인데 절 머리는 *"한 줄 남았다"* 고 말한다.
- **책임 귀속이 서로를 가리킨다(B2 의 무게)**: HANDOFF `:304` 는 *"**남는 것은 Slice 5(동시 진행)에 합류**: 방침 머리말 고지의 '가입 절차의 동의 기록' 축과 `legal/README.md` §8 표의 동의 행 갱신"*, `:318` ⓔ 도 *"방침 머리말 고지와 `legal/README.md` §8 표의 갱신은 Slice 5 몫이다"* 라고 적는다. 두 줄은 **Slice 5 를 닫은 구현자의 기록 커밋 `bcd30b2` 에서도 그대로 살아 있고**, 같은 커밋이 Next Tasks 3번·11번·SoT v1.8.60 으로 Slice 5 를 **완료**로 바꿨다. 한편 Slice 5 의 work_log 세션 69 는 *"제3조 안내 상자는 세션 68 몫이라 그대로"* 라고 적는다 — **양쪽이 서로에게 넘긴 결과, 회원이 읽는 거짓 문장의 담당자가 없다.**

### F. 수 재실측 — 보고와 일치(단 측정 시점의 함정 하나)

| 주장 | 재실측 | 일치 |
|---|---|---|
| 정책 가드 `b6fd464` = **9셀 / 66 subtests** | worktree `b6fd464`: `9 passed, 66 subtests passed` | ✔ |
| 슬라이스 뒤 = **10셀 / 70 subtests**(+1셀 / +4) | 작업 트리: `10 passed, 70 subtests passed` | ✔ |
| +4 의 내역(행 +2 · 신규 셀 +2) | `_rows()` 가 13 → **14행**(행마다 `…points_at_a_constant…` 와 `…stated_number…` 에 subtest 하나씩 = +2) · 신규 셀은 문서 둘 = +2. MX-D(행 삭제)가 70 → **68** 로 떨어지는 것이 그 귀속의 역확인 | ✔ |
| 문서·정책 초점 5파일 = **110 passed / 1008 subtests** | 커밋 `0379fe3` worktree: `110 passed, 1008 subtests` · 현재 트리(`bcd30b2`): `110 passed, 1008 subtests` · `b6fd464`: `109 / 1004` | ✔ |
| 프런트 바이트 가드 4/4 | `4 passed (4)` EXIT=0 | ✔ |
| 백엔드 소스 무변 | `git show e169e96 --stat` 에 `services/` 0파일 | ✔ |

**★ 측정 시점의 함정(해소됨)**: 검증 중간(HEAD `0379fe3`, SoT 가 미커밋으로 `v1.8.60` 이던 창)에 같은 5파일을 돌렸을 때 **`1 failed, 109 passed, 1008 subtests`** 였다 — `test_docs_indexes.py::VerificationCountClaimsTest::test_the_readme_names_the_current_contract_version`(SoT 헤더 `v1.8.60` vs `README.md:106` `v1.8.59`). 구현자의 `bcd30b2` 가 README ④행을 함께 올려 닫혔고, **지금은 초록이다.** 기록해 두는 이유는 이 가드가 *SoT 헤더와 README 를 한 커밋에서 함께 올려야 한다* 는 규칙을 강제한다는 점이 공유 트리에서 값이 크기 때문이다. 절대 기준선(백엔드 전수)은 **이 기록이 재지 않았다** — 같은 창의 두 슬라이스가 함께 움직였고 그 귀속은 그들 몫이다(HANDOFF 함정: 백엔드 전수와 프런트 전수를 겹쳐 돌리지 말 것).

### G. 기록 의무 — 검증 중에 닫혔다

검증 시작 시점에는 SoT 행도 work_log 세션도 **없었다**(공유 파일에 동시 진행 AI 의 미커밋 변경이 있어 구현자가 보류한 상태였고, 그 판단은 옳다 — 스테이징하면 남의 작업을 함께 커밋한다). 검증 중 `bcd30b2` 가 들어와 지금은:

- `docs/system-contract-sot.md` 계약 버전 **`v1.8.60`** + 같은 번호의 행(내용이 이 슬라이스의 실제 편집과 일치한다 — 교차 확인했다).
- `docs/daily_logs/2026-09-12/work_log.md:288` **세션 69**(Goals·Completed·Issues·Decisions·Verification 절 구비). 변이 3종 표가 내 재실측과 일치하고, **스스로 남긴 한계 둘**(§6 행 삭제 무셀 · 조항 내용은 기계가 안 본다)이 내가 독립적으로 찾은 MX-D 와 같다.
- `docs/plans/*`·`HANDOFF.md`·`README.md`·`CHANGELOG.md` 도 v1.8.60 로 정합.

**내부 정합성**: 계획서·SoT·HANDOFF·README 가 모두 `v1.8.60` 을 말한다(`311616d` 가 v1.8.59 선점 충돌을 정정했다). 기록 의무는 **충족**이며, 남은 불일치는 B2·B3 의 *내용* 문제뿐이다(번호·링크·절 구조는 정합).

## Issues / Risks

### Blocking (계약 의무)

**B1 — §6 *"취소는 파기가 시작되기 전까지다"* 를 코드가 시행하지 않고, 그 경계를 잠그는 셀이 0개다.**
`auth/users.py:525-546` `cancel_withdrawal` 은 `purge_started_at` 을 보지 않는다. 파기가 청구된(또는 실패해 표식만 남은) 계정의 `DELETE /me/withdrawal` 이 200 으로 통과하고 유예 제한이 풀린다(§A 실측). `tests/` 전체에서 `cancel` 과 `purge_started_at` 을 함께 보는 셀은 없다 — **계약이 요구하는 분기가 무셀**이다. 승격은 이 문장을 *"코드가 지금 시행하는 것"* 으로 올렸으므로, 닫는 길은 둘 중 하나다.
- ⓐ 코드를 D5 에 맞춘다 — `cancel_withdrawal` 이 `purge_started_at is not None` 이면 거부(409 가 선례다: 취소 409 = *취소할 것이 없음*. 이 경우는 뜻이 달라 **오너 결정이 필요한 갈래**다 — 새 얼굴을 만들지, 같은 409 에 합칠지), + 양방향 셀(청구 전 취소는 계속 200 · 청구 뒤는 거부 · 취소 뒤 재청구 경로).
- ⓑ §6 문장을 **코드가 하는 말**로 바꾸고(*"탈퇴 스탬프가 있는 동안 취소할 수 있다"*), D5 와의 거리를 추적 부채로 등재한다.
ⓐ·ⓑ 어느 쪽이든 **문장과 셀이 같은 것을 말하는 상태**가 조건이다.

**B2 — 방침 머리말의 거짓 문장이 회원 화면에 서 있고, 담당자가 없다.**
`docs/legal/privacy-policy-draft.md:10`(+ 바이트 동일 사본 `frontend/src/legal/privacy-policy.md:10`). 동의 게이트는 `58a8ac9` 에서 시행됐다. HANDOFF `:304`·`:318` 이 그 정리를 **Slice 5 몫**이라 적은 채 같은 커밋(`bcd30b2`)이 Slice 5 를 완료로 닫았다. 닫는 길: 그 줄을 걷고(약관과 같은 모양) 프런트 사본을 함께 옮긴 뒤 `cmp`·`legalSource.test.ts` 로 확인, **또는** 오너가 *"이 줄은 다른 슬라이스가 쓴다"* 를 명시해 귀속을 한쪽으로 확정한다. 회원이 읽는 면이므로 *"비차단 보강"* 으로 미룰 수 없다 — 이 슬라이스가 나머지 절반을 같은 이유로 이미 고쳤다.

**B3 — `legal/README.md` §8 절이 자기 표와 모순한다.**
`:69` *"남은 전제는 한 줄 = 방침 제3조 안내 상자"* ↔ `:74` 그 행의 전제 *"없음 — 지금도 참"*. 그리고 전제가 적힌 유일한 행 `:73`(추론 경계 밖 전송 고지 — 전제 *"가입 동의 게이트 구현"*)의 그 게이트는 닫혔다. 닫는 길: §8 표의 전제 열을 현재 사실로 갱신(게이트 축이 닫혔으면 그 행도 승격 후보인지 함께 판단)하고 절 머리 문장을 표와 같은 말로 맞춘다. *(B2 와 한 번에 닫히는 자리이지만 별개 편집이라 따로 세운다.)*

### Hardening (비차단)

- **H1 — §6 의 *"유예 중 로그인 된다"* 에 셀이 없다.** 잠기는 것은 *기존 세션이 계속 산다*(`test_auth_api.py:179`)까지다. `POST /auth/login` 은 탈퇴 상태를 보지 않아(`routers/auth.py` login — `status`·`must_change_password` 만 본다) 실제로 되지만, 문장이 열거한 셋 중 하나가 무셀이다. 유예 중 **재로그인 200** 셀 하나가 값싸다.
- **H2 — 공백을 기록한 `미기재` 행과 §6 산문이 무셀이다**(MX-I·MX-K 실측: 지워도 10/70 초록). 코드가 시행하는 미고지 제한의 **유일한 흔적**이 그 행이므로, *"`미기재` 행은 약관·방침이 그 말을 적기 전까지 존재한다"* 를 잠그는 셀 하나가 후보다(예: 약관·방침에 유예 제한 문구가 없으면 대조표에 그 행이 있어야 한다 — 양방향이 성립한다).
- **H3 — §6 표 행을 통째로 지우면 아무도 안 문다**(MX-D). 모듈 docstring 이 적어 둔 기존 한계이고 값은 신규 셀+핀이 계속 든다. `test_the_document_exists_and_carries_pinned_rows` 의 하한 `>= 10` 이 디스크 실제 **14행**보다 넉넉해 부분 방어조차 비어 있다 — 하한을 현재 수에 맞춰 올리면 *행 삭제*의 절반은 값싸게 잡힌다(늘어날 때 같이 올리는 비용은 있다).
- **H4 — 파기 뒤 남는 것이 §6 에는 둘, 코드에는 셋이다.** `account_axis_sweep.py:30-34` 는 `request_usage_ledger`·**`admin_audit_events`**·`user_name_history` 를 남긴다. 회원 고지 쪽은 방침 제5조 4항(*"관리자 열람 기록은 삭제되지 않습니다"*)이 받고 있어 **거짓은 아니지만**, §6 의 잔존 문장이 열거형이라 한 축이 빠져 있다. 한 단어 보강 후보.
- **H5 — 조항↔상수 대조의 두 진단을 HANDOFF 함정으로 등재.** 값 등가 표현(`1개월`)은 빨개지고(MX-F), 앵커 문장을 다듬으면 *값 불일치*가 아니라 *앵커 실종*으로 빨개진다(MX-J). 둘 다 설계대로이고 메시지도 좋지만, 약관을 고치는 사람이 *"왜 빨간가"* 를 두 가지로 만난다는 사실은 함정 표에 한 줄 값이 있다.

## Outstanding items (결함 아님 — 오너의 다음 걸음)

- **공유 트리 동시 작업이 검증 중에도 진행됐다.** 검증 시작 시 HEAD `e169e96` + 미커밋 7파일 → 변이 전량 복원 직후 HEAD `bcd30b2` + **clean**(복원이 바이트 동일임을 `git status` 가 비어 있는 것으로 교차 증명) → 기록 작성 중 동시 진행 AI 가 자기 검증 기록(`landing_l3_gate_and_landing.md`)과 코드 둘(`frontend/src/App.test.tsx`·`tests/test_auth_users_mongo.py`)을 다시 열었다. 그 사이 `9d47c32`·`311616d`·`0379fe3`·`bcd30b2` 가 들어왔다. **이 기록의 모든 수치는 각각 측정 시점의 리비전을 함께 적었다.**
- **검증자가 쓴 파일은 넷이다** — 이 기록 + 등재에 필요한 색인 셋(`docs/verifications/README.md` 행·건수·분포 · `docs/README.md` 건수 · `README.md` 건수 둘·분포 문장). 건수 주장은 `test_docs_indexes.py::VerificationCountClaimsTest` 가 **세 파일을 한 수로 묶어** 잠그므로 색인 한 곳만 고치면 전수가 빨개진다. 값은 색인 표에서 **유도**했다(디스크 303건 · 합격 201 / 조건부 97 / 불합격 5) — 같은 창에서 검증 기록 둘이 동시에 등재돼 한쪽만 세면 갈라지는 자리라, 손으로 +1 하지 않고 표를 다시 셌다. 등재 뒤 `tests/test_docs_indexes.py` **17 passed / 316 subtests**, 초점 5파일 **110 passed / 1012 subtests**(신규 기록 둘이 기록 구동 셀 셋을 각각 지나 +4).
- **오너 결정 대기(구현자가 올린 것)**: 유예 중 쓰기 차단 고지를 약관·방침에 넣을지. 본 검증은 **인용할 기존 조항이 없다**는 것을 독립 확인했다(§D) — 즉 *"어느 조항을 가리킨다"* 로는 닫히지 않고 **문언이 새로 필요하다**.
- **B1 ⓐ 갈래는 오너 결정을 품는다**(파기 청구 뒤 취소 거부의 얼굴 — 새 상태코드인지, 409 합류인지).
- Slice 4b(관리자 잔여 정리)는 브리프 선행·트리거 없음 — 계정 탈퇴 축의 마지막 칸이다.

## 검증하지 못한 것(과 이유)

- **백엔드 전수·프런트 전수**: 돌리지 않았다. HANDOFF 가 *두 전수를 겹쳐 돌리면 이 기계에서 거짓 타임아웃이 난다* 고 적고 있고 동시 진행 AI 가 같은 창에 있었다. 프런트는 바이트 가드 **단일 파일**만 돌렸다(지시된 범위).
- **실 mongod 경로**: 라이브 Mongo 없이 측정했다. 파기 데몬·스윕의 실주행(청구 조건의 원자성, `_id` 규칙의 실제 삭제 건수)은 `2026-09-10` 기록이 다뤘고 이번 슬라이스는 백엔드 소스 무변이라 재측정하지 않았다.
- **B1 의 HTTP 면 재현**: 서비스 계층에서 실측했다(`cancel_withdrawal` 직접 호출 + 저장소 `claim_for_purge`). `DELETE /me/withdrawal` 로의 end-to-end 재현은 하지 않았다 — 엔드포인트가 같은 서비스 메서드를 부르고(`routers/auth.py:314`) 인증 스택이 `is_active` 만 보므로 도달 가능성은 코드로 확인했다.
- **회원 화면의 실제 렌더**: 방침 머리말이 화면에서 어떻게 보이는지(렌더러가 그 줄을 남기는지)는 확인하지 않았다. 머리말 접두 규칙은 `근거:`·메타 줄만 걷으므로 이 고지 줄은 남는다고 읽었지만, 육안 확인은 프런트 축이라 범위 밖이다.
- **구현자의 `b6fd464` 양단 worktree 실측 자체**: 나는 같은 두 리비전을 **내 worktree 에서 다시 재어** 같은 수를 얻었다(구현자의 worktree 를 재사용하지 않았다).

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system
git show e169e96                                   # 대상
git worktree add --detach /tmp/wt-b6 b6fd464
(cd /tmp/wt-b6 && python3 -m pytest tests/test_service_policy_contract.py -q)   # 9 / 66
python3 -m pytest tests/test_service_policy_contract.py -q                      # 10 / 70
python3 -m pytest tests/test_docs_indexes.py tests/test_repo_hygiene.py \
  tests/test_product_name.py tests/test_service_policy_contract.py \
  tests/test_auth_users.py -q                                                   # 110 / 1008
(cd frontend && npx vitest run src/legal/legalSource.test.ts)                   # 4 passed
cmp docs/legal/terms-of-service-draft.md frontend/src/legal/terms-of-service.md
cmp docs/legal/privacy-policy-draft.md  frontend/src/legal/privacy-policy.md

# B1 재현(파기 청구 뒤 취소가 통과한다)
python3 - <<'PY'
import sys; sys.path[:0] = ["/mnt/f/devel/ai_writte_system", "/mnt/f/devel/ai_writte_system/tests"]
from datetime import UTC, datetime
from test_auth_users import _service
from services.application.app.auth.users import InMemoryUserRepository
repo = InMemoryUserRepository(); svc = _service(repo)
u = svc.create_user(username="alice", password="pw123")
svc.request_withdrawal(u.id)
print("claimed:", repo.claim_for_purge(u.id, at=datetime(2026,10,12,tzinfo=UTC)).purge_started_at)
print("cancel:", svc.cancel_withdrawal(u.id).withdrawal_requested_at, "← None 이면 취소가 통과했다")
PY

# 변이는 cp 백업 → 파이썬으로 치환 → 백업에서 복원 → cmp (git checkout 금지)
```

---

## 폐쇄 보고 (구현자, 2026-09-12 · SoT v1.8.61)

> **판정은 이 절이 올리지 않는다.** 조건을 닫은 세션이 자기 판정을 승격하면 독립성이 사라지므로(선례 v1.8.52), **승격 재검(변이 재적용)은 다음 검증 세션 몫**이다. 아래는 *무엇을 어떻게 닫았는가* 의 보고다.

| 조건 | 어떻게 닫았는가 | 증거 |
|---|---|---|
| **B1** | 검증이 제시한 갈래 중 **ⓑ** — §6 문장을 **코드가 하는 말**로 고쳤다(*"취소는 탈퇴 스탬프가 있는 동안 된다 · 코드는 파기 청구를 보지 않는다"*) + D5 와의 거리를 문장 안에 명시. 코드 변경(ⓐ)은 **거부의 얼굴을 고르는 오너 결정**을 품어 브리프로 올렸다. 무셀이던 분기는 **특성 셀**이 받는다 — docstring 이 *이 동작을 승인하지 않는다* 고 적고 ⓐ 선택 시 **셀과 문장이 함께 뒤집히는 자리**임을 표시한다 | `tests/test_auth_users.py::WithdrawalCancelAfterPurgeClaimTest`(1 passed) · 브리프 [`slice5-withdrawal-cancel-after-purge-claim-decisions.md`](../../plans/slice5-withdrawal-cancel-after-purge-claim-decisions.md) · HANDOFF 오너 결정 표 |
| **B2** | 방침 머리말의 그 줄을 **걷었다**(약관과 같은 모양) + 프런트 사본 동반 이동. **두 법률 문서에 미제공 고지가 0 이 됐다** | `cmp` 바이트 동일 · `npx vitest run src/legal/legalSource.test.ts` **4 passed** |
| **B3** | §8 절 머리를 표와 같은 말로 맞췄다 — **열린 시행 전제 0**. 남은 두 행은 *아직 시행되지 않은 것* 이 아니라 **코드가 따로 할 일이 없던 것**임을 적고, **§8 을 비울지는 오너 판단**으로 남겼다(구현자가 고르지 않는다). 고지 축은 §8 → §1~§7 승격이 남아 전제 열에 닫힘을 적은 채 뒀다(두 문서의 §8 표가 어긋나지 않게) | `docs/legal/README.md` §8 · `docs/service-policy-contract.md` §8 |

**하드닝 다섯도 같은 세션에 닫았다** — **H1** 유예 중 재로그인 200 셀(취소 경로 도달까지 단정) · **H2** `미기재` 행을 **코드 가드와 양방향으로** 묶었다(`require_active_user_for_write` 유무가 행의 유무를 결정한다) · **H3** 행 수 하한 `>= 10` → **14**(디스크 실제 수) · **H4** §6 잔존 **둘 → 셋**(`admin_audit_events`) · **H5** 두 진단(값 불일치 vs 앵커 실종)을 HANDOFF 함정에 등재.

**★ 검증이 "조용히 통과한다"고 실측한 변이 둘이 이제 물린다** — 같은 변이를 재적용해 확인했다(`cp` 백업 → 역복원 → `cmp`, `git checkout` 미사용):

| 변이 | 검증 시점 | 폐쇄 후 |
|---|---|---|
| **MX-D** — §6 의 `계정 탈퇴 유예 기간` 행 1줄 삭제 | 10/70 **초록** | `FAILED test_the_document_exists_and_carries_pinned_rows` |
| **MX-I** — 대조표의 `미기재` 행 1줄 삭제 | 10/70 **초록** | `FAILED test_the_undisclosed_restriction_keeps_its_row_while_code_enforces_it` |

**★ 보강 중 가드가 구현자의 새 결함을 잡았다** — §8 행의 상태 칸에 `모듈.py::상수` 꼴을 적었더니 그 행이 **정본 포인터 행으로 파싱**돼 `_rows()` 가 14 → 15 가 됐다. §8 에 포인터를 달지 않는다는 **이 문서 자신의 규칙** 위반이고 H3 하한의 근거도 함께 흔들렸다. 표기를 끊고(코드 스팬을 둘로 나눔) 그 규칙을 행 안에 적었다.

**수치**: 정책 가드 **10셀/70 → 11셀/70 subtests** · `test_docs_indexes` **17 passed / 316 subtests**(브리프 등재 + 건수 주장 셋 **139/117** 갱신) · `SelfWithdrawalApiTest` **21 passed / 169 subtests** · `test_auth_users` 특성 셀 1 passed. **백엔드 소스 무변**(`services/` 0줄 — B1 을 ⓑ 로 닫았으므로 코드는 그대로다).

**남은 것**(이 기록의 Outstanding 과 같다): 판정 승격 재검 · 오너 결정 둘(**파기 청구 뒤 취소의 얼굴** · **유예 중 쓰기 차단 고지 문언**) · §8 의 남은 두 행을 올릴지.
