# 오너 결정 셋 검증 조건 C1 승격 재검 — 폐쇄(`867ba15`)를 변이 재적용으로 확증

**합격** — 조건을 닫은 세션(79)이 자기 판정을 올리면 독립성이 사라지므로(v1.8.52·v1.8.63·v1.8.65·세션 77 선례), 판정 승격을 독립 세션(81)이 변이 재적용으로 확증했다. **대상 기록의 변이 표에서 핵심 확증 재료 M14·M15(502 partial 폐쇄의 양방향)를 정확히 재적용해 건수·기명 셀·subtests까지 전부 일치**시켰고, 표본 셋(M9·M10·M1 — 파기 취소 축 양방향 + 세 경로 분리 소유 중 수동 저장 under)을 더해 대상 기록의 다른 주장도 독립 확인했다. 다섯 회 전부 **치환 횟수 1 단정 → 초점 재실행 → 바이트 동일 복원 → 워크트리 clean** 절차로 돌렸다. 폐쇄의 실체(502 분기 배선 + under 셀)가 최종 트리(`1715bae`)에 그대로 살아 있다.

## Subject metadata

- **검증일**: 2026-09-13 · **요청자**: 오너(이 세션 지시 — 대상 기록 §Verdict 의 *"합격 승격은 다음 독립 세션의 변이 재적용 몫"* 을 수행).
- **검증자**: 독립 세션(세션 81). 구현(세션 78: `267ba22`·`463a042`·`d9a1bd2`) · 독립 검증+조건 폐쇄(세션 79: `449784d`·`867ba15`) 어느 커밋에도 관여하지 않았고 이 축의 코드·테스트·기록을 한 줄도 쓰지 않았다.
- **대상**: 대상 기록 [`owner_decision_set_d2_and_purge_cancel.md`](owner_decision_set_d2_and_purge_cancel.md)(발행 판정 **조건부 합격**, 조건 C1) · 폐쇄 커밋 **`867ba15`**. 검증 트리 기준은 현 HEAD `1715bae`(그 사이 문서 커밋만 — `542e087`·`1715bae` 둘 다 백엔드 소스·테스트 무변, 변이·기준선 불변의 근거).
- **정규 스펙(계약 스코프)**: [`guides/verification.md`](../../guides/verification.md) §Required sections(세 판정 토큰 · 인덱스 일치) · §Mutation testing(원복 규칙 · `grep FAILED` 맹점 · "diff 원문을 적어라") · 대상 기록 §2·§변이 표.
- **검증 트리**: 변이는 탈치 워크트리 `/tmp/vs81-mut`(`1715bae` detached)에서 돌렸다. **본 트리에 `git checkout`·`restore`·`stash`·`reset` 을 한 번도 쓰지 않았다.**
- **환경**: WSL2 · 호스트 `python3 -m pytest`(user-site). 이 재검의 초점 셋(activity 3종+accept · auth 2종)은 전부 in-memory 라 **Mongo 도달성과 무관**하다(skip 0).

## Scope

1. **C1 폐쇄의 실체가 최종 트리에 살아 있는가** — 폐쇄 배선(`routers/writing.py:1355`의 `if not exc.saved.idempotent_replay:`)과 under 셀(`test_a_replayed_partial_accept_leaves_no_second_row`)의 1차 소스 확인.
2. **핵심 변이 재적용** — M14(under: 배선 → `if True:`)·M15(over: 배선 → `if False:`), 기대는 대상 기록 변이 표의 실측치.
3. **표본 변이** — M9·M10(파기 취소 거부의 under·over 양방향) · M1(세 경로 분리 소유 중 수동 저장 under) — 대상 기록의 다른 주장 독립 확인.
4. 판정 승격(선례 `1f4f95a` 모양) · 인덱스·수치 갱신 · 기준선 유도(문서 가드 양단 실측).

## Methodology

- 변이는 `python3` 헬퍼 하나로만 적용했다 — 「앵커 `count == 1` 단정 → `shutil.copy2` 백업(`/tmp`) → `pathlib.write_text` 치환 → 초점 실행 → 백업 복원 → **바이트 동일성 단정** → 워크트리 `git status --short` 빈 것 확인」이 스크립트에 단정으로 박혀 있다. `sed -i`·`perl -i`는 쓰지 않았다(저장소 규칙).
- 앵커 유일성은 사전에 확인했다: `if not exc.saved.idempotent_replay:` 는 `writing.py` 에 1회(`:1355` — 성공 분기 `:1393` 은 문자열이 다르다) · `if stored.purge_started_at is not None:` 은 `auth/users.py` 에 1회(`:570` — `:287` 은 `stored is None or` 접두가 붙어 다른 줄) · `if not result.idempotent_replay:` 는 `drafts.py` 에 1회(`:656` — `:713`·`:748` 은 `finalized` 다). HANDOFF 함정("같은 문자열 두 곳")은 셋 다 해당 없음.
- 결과는 **요약 줄 + `FAILED|SUBFAILED`** 를 함께 읽었다(가이드 §★).
- 초점 셋은 대상 기록의 것을 재구성해 **무변이 기준을 먼저 쟀다**(아래 표) — 변이 결과는 이 기준과의 차분으로 읽는다.

## Findings

### 1. C1 폐쇄의 실체 — 최종 트리에서 1차 소스 확인

- `git show 867ba15 --stat`: `routers/writing.py`(배선+주석) · `tests/test_writing_accept.py`(under 셀 신설) · `api/errors.py`(주석 정정) · 브리프 — 대상 기록 §2 폐쇄 서술과 일치.
- 현 HEAD(`1715bae`)의 [`routers/writing.py:1355`](../../../services/application/app/routers/writing.py#L1355) 에 `if not exc.saved.idempotent_replay:` 배선이 있고 [`tests/test_writing_accept.py:451`](../../../tests/test_writing_accept.py#L451) 에 under 셀이 있다. 그 사이 커밋(`542e087`·`1715bae`)은 문서만 손댔다(`--stat` 확인).

### 2. ★ 변이 재적용 — 다섯 회 전건 일치

무변이 기준(전부 `/tmp/vs81-mut`, `1715bae`): activity 3종+accept(`test_activity_api`+`test_activity_actions`+`test_writing_accept`) = **88 passed / 113 subtests** · auth 2종(`test_auth_users`+`test_auth_api`) = **225 passed / 1222 subtests** · activity 2종(`test_activity_api`+`test_writing_accept`) = **78 passed / 19 subtests**.

> "기대"는 대상 기록 §변이 표의 실측치다. diff 는 표의 원문 그대로 적용했다.

| # | 방향 | 파일:줄 · diff(원문) | 대상 기록 실측(기대) | **내 실측** | 일치 |
|---|---|---|---|---|---|
| **M14** | under(결함 재도입) | [`routers/writing.py:1355`](../../../services/application/app/routers/writing.py#L1355) `if not exc.saved.idempotent_replay:` → `if True:` | 1 failed / 87 passed / 113 subtests · `WritingAcceptApiTest::test_a_replayed_partial_accept_leaves_no_second_row` | **1 failed, 87 passed, 113 subtests** · 같은 기명 셀 | ✅ |
| **M15** | over(과잉 교정) | 같은 줄 → `if False:` | 1 failed / 87 passed · `WritingAcceptApiTest::test_a_partial_accept_still_records_the_saved_version` | **1 failed, 87 passed, 113 subtests** · 같은 기명 셀 | ✅ |
| **M9** | under(경계 벗기기) | [`auth/users.py:570`](../../../services/application/app/auth/users.py#L570) `if stored.purge_started_at is not None:` → `if False:` | 3 failed / 222 passed / 1222 subtests · `WithdrawalCancelAfterPurgeClaimTest::test_cancelling_is_refused_after_the_purge_was_claimed` · `…::test_the_refused_cancel_leaves_both_stamps_intact` · `SelfWithdrawalApiTest::test_cancelling_after_the_purge_was_claimed_is_409` | **3 failed, 222 passed, 1222 subtests** · 같은 기명 셋 | ✅ |
| **M10** | over(더 나쁜 결함: 항상 거부) | 같은 줄 → `if True:` | 6 failed / 219 passed · `WithdrawalStateAxisTest::test_a_cancelled_account_is_indistinguishable_from_one_that_never_asked` · `…::test_cancelling_clears_the_stamp` · `…::test_cancelling_then_requesting_again_starts_a_new_grace_period` · `SelfWithdrawalApiTest::test_a_withdrawing_member_can_sign_in_again` · `…::test_cancelling_removes_every_grace_period_restriction` · `…::test_cancelling_returns_the_account_to_never_having_asked` | **6 failed, 219 passed, 1222 subtests** · 같은 기명 여섯 | ✅ |
| **M1** | under(세 경로 분리 — 수동 저장) | [`routers/drafts.py:656`](../../../services/application/app/routers/drafts.py#L656) `if not result.idempotent_replay:` → `if True:` | 1 failed / 76 passed / 19 subtests · `ActivityRecordingTest::test_resending_the_same_save_key_leaves_no_second_row` | **1 failed, 77 passed, 19 subtests** · 같은 기명 셀 | ✅ |

**M1 의 passed 가 76→77 로 하나 다른 것은 트리 드리프트로 정확히 설명된다** — 대상 기록의 M1 은 폐쇄 전 트리(`d9a1bd2`)에서 잰 값이고, 그 뒤 `867ba15` 가 under 셀 하나를 순증가시켰으므로 같은 초점 셋(activity 2종)이 77→78 셀로 늘었다(세션 80 의 두 리비전 통제 대조가 같은 귀속을 확정). 실패 셀의 정체·건수·subtests 는 무변. **나머지 넷은 건수·기명 셀·subtests까지 한 치도 다르지 않다.**

**등가 변이 0 · 흡수 0 · 복원 불량 0.** 다섯 회 전부 치환 횟수 1 단정을 통과했고(유일하지 않은 앵커였다면 단정이 먼저 실패한다), 복원 뒤 바이트 동일성과 워크트리 `git status --short` 공백을 매번 단정했다.

### 3. 판정 승격 · 수치 갱신

- **대상 기록**: 머리에 최종 판정 한 줄 + §Verdict 선두 토큰 `**합격**`(승격 문구 + 승격 재검 링크). 발행 시점 판정 원문은 두 자리 모두 인용(`>`)으로 보존했다 — 한 글자도 지우지 않았다(선례 `1f4f95a` 가 승격 넷에서 쓴 모양).
- **인덱스**(`docs/verifications/README.md`): 대상 기록 행의 판정 열 `조건부 합격` → `합격` + 승격 문구, 신규 재검 기록(이 문서) 행 등재. 머리 **314→315건**(직접 세아림: 디스크 `docs/verifications/*/*.md` = 315) · 분포 **합격 216 · 조건부 94 · 불합격 5**(합계 315 ✓ · 승격 전환 +1 · 신규 합격 +1) · 일수 **73 무변**(같은 날).
- **루트 README ③행·문서 목록** · **docs/README.md** 의 314건 주장 전부 315 로(grep 으로 전건 확인 — CHANGELOG 세션 79 행의 `313→314건` 은 그때의 변화 서술이라 그대로 둔다).
- **기준선(문서 가드 양단 실측)**: 이 슬라이스는 백엔드 소스·테스트 무변이라 전수 대신 가드 둘(`test_repo_hygiene`·`test_docs_indexes`) 양단으로 유도했다. `1715bae` 워크트리에서 **29 passed / 959 subtests**(세션 80 실측과 동일) → 이 슬라이스 뒤 **29 passed / 961 subtests**(+2 = 승격 기록 문서 하나: `test_repo_hygiene` 문서당 1 + 검증 인덱스 행 1 = `test_docs_indexes` 1). **passed 무변**이므로 기준선은 **3066/1/4236 → 3066/1/4238** — HANDOFF 회귀 기준선 줄과 루트 README 절차 표 ②행을 같은 값으로(`test_the_readme_repeats_the_regression_baseline` 가 묶는 쌍).

## Issues / Risks

### Blocking (계약 의무)

없다. C1 폐쇄(`867ba15`)의 배선·셀이 최종 트리에 실재하고, 양방향 변이가 기명 셀까지 재현된다.

### Hardening (비차단)

- 새로 연 것은 없다. 대상 기록이 올린 오너 통지 항목(§Outstanding 1 — 구현자의 명시적 반대 판단을 이 검증이 뒤집었다)은 **판정과 별개의 오너 확인 사항**으로 그대로 열려 있다(되돌릴 곳이 `867ba15` 한 커밋이라는 서술도 그대로).
- M15 의 subtests(113)는 대상 기록 표에 적혀 있지 않았다(값이 틀린 것이 아니라 미기재) — 이 재검이 채워 실측치를 완전한 형태로 남긴다.

## Verdict

**합격**

승격의 근거:

1. **핵심 확증 재료가 전건 일치한다** — M14·M15 가 각각 자기 셀만 정확히 물고(under: `test_a_replayed_partial_accept_leaves_no_second_row` · over: `test_a_partial_accept_still_records_the_saved_version`), 흡수·등가 변이가 없었으므로 C1 폐쇄의 두 셀이 502 partial 축을 **분리 소유**한다.
2. **대상 기록의 다른 주장도 독립 확인됐다** — 파기 취소 거부의 양방향(M9 3셀 · M10 6셀, 기명 셀까지 동일)과 세 경로 분리 소유(M1)가 같은 절차로 재현된다.
3. **폐쇄와 승격 사이에 훼손이 없다** — `867ba15` 이후 백엔드 소스·테스트를 건드린 커밋이 없고(`--stat` 확인), 기준선 산술(959→961 · passed 무변)이 그와 일치한다.
4. **판정 어휘·인덱스 정합** — 승격된 머리 줄과 §Verdict 첫 줄이 모두 `**합격**` 토큰으로 시작하고 인덱스 판정 열과 같은 말을 한다(가이드 §Required sections).

## Outstanding items

1. 이 기록(+2)이 기준선을 4236→**4238** 로 올렸다(HANDOFF 회귀 기준선 줄 · 루트 README ②행 같은 값).
2. 검증 인덱스 머리·분포·루트 README·docs/README 의 건수·분포를 승격(조건부→합격)과 이 기록 등재(합격 +1)에 맞춰 갱신했다 — **315건 · 합격 216 / 조건부 94 / 불합격 5 · 73일치**(조건부 30% — round(94/315·100)).
3. 오너 결정 대기 둘(H4 다섯째 표면 `PUT /projects/{id}/brief` · 옛 해시 분모 수치 교체)은 이 슬라이스 범위 밖이라 그대로 둔다. 대상 기록 §Outstanding 1(구현자 반대 판단 뒤집기 통지)도 그대로 열려 있다.
4. SoT 는 올리지 않았다 — 승격-only 커밋(`2e025dc`·`432f790`·`1f4f95a`)이 SoT를 한 번도 안 올린 선례를 따랐다(계약 변화가 없으므로).

## Reproduction

```bash
# 0) 본 트리를 건드리지 않는다 — 변이는 탈치 워크트리에서만
git -C /mnt/f/devel/ai_writte_system worktree add --detach /tmp/vs81-mut 1715bae
cd /tmp/vs81-mut

# 1) 무변이 기준
PYTHONPATH=$PWD python3 -m pytest tests/test_activity_api.py tests/test_activity_actions.py \
    tests/test_writing_accept.py -q                  # 88 passed / 113 subtests
PYTHONPATH=$PWD python3 -m pytest tests/test_auth_users.py tests/test_auth_api.py -q   # 225 / 1222
PYTHONPATH=$PWD python3 -m pytest tests/test_activity_api.py tests/test_writing_accept.py -q  # 78 / 19

# 2) 변이 — 매번 「앵커 count==1 단정 → copy2 백업 → write_text 치환 → 초점 재실행 →
#    백업 복원 → 바이트 대조 → git status 확인」. diff 원문은 §2 표. 결과는 요약 줄과
#    FAILED|SUBFAILED 를 함께 읽는다. M15 결과 예:
#    1 failed, 87 passed, 113 subtests — FAILED …test_a_partial_accept_still_records_the_saved_version

# 3) 폐쇄 실체 확인
git -C /mnt/f/devel/ai_writte_system show 867ba15 --stat
grep -n "if not exc.saved.idempotent_replay:" \
    /mnt/f/devel/ai_writte_system/services/application/app/routers/writing.py   # :1355

# 4) 문서 가드(양단) — 승격 전 1715bae 워크트리에서 29/959, 슬라이스 뒤 메인 트리에서 29/961
PYTHONPATH=$PWD python3 -m pytest tests/test_repo_hygiene.py tests/test_docs_indexes.py -q

# 5) 정리
git -C /mnt/f/devel/ai_writte_system worktree remove /tmp/vs81-mut
```
