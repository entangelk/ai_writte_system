# 계정 탈퇴 Slice 4b — 조건 폐쇄 승격 재검

**합격** — 발행 검증(검증 세션 71)의 조건 셋 **C1·C2·C3**이 폐쇄 커밋 **`a460237`**(test-only · 기록 `0769cc9` · SoT v1.8.63)로 닫혔고, 이 재검이 변이 재적용으로 그 폐쇄를 확증했다. 선행 기록 [`admin_residual_purge_slice4b.md`](admin_residual_purge_slice4b.md) 의 판정 **조건부 합격을 합격으로 승격**한다(발행 시점 판정은 인용으로 아래 보존).

- **일시**: 2026-09-12 · **검증자**: 독립 세션 — 구현(`2aa9e3f`·`b3e5ec0` 등)·발행 검증(세션 71)·조건 폐쇄(`a460237`) 어느 쪽도 아니다
- **검증 트리**: HEAD `0769cc9`. **검증 중 다른 AI 의 미커밋 작업이 같은 트리에 있었다**(변이 대상 파일과는 무관 — 원복은 내 대상 파일만 개별 경로로 `git checkout -- <절대경로>` + 백업 `cmp` 바이트 대조, 매 변이 전 대상 파일 diff 0 확인).
- **환경**: WSL2 · `python3 -m pytest`(test-mongo healthy) · 프런트는 `frontend/` 안에서 `npx vitest`. **전수는 돌리지 않았다**(공유 트리의 동시 작업 — 발행 검증과 같은 범위 제한).

## 변이 재적용 — 5종(폐쇄 삼각형 + 원본 둘) 전부 기명 셀로 재실패

| 변이 | 적용한 diff(실제 텍스트) | 발행 검증 시점 | 실측(폐쇄 후 현행 트리) |
|---|---|---|---|
| **M3** (under) | `routers/admin.py` POST 핸들러(`reconcile_account`)에서 `_stalled_user_or_error(user_id)` 한 줄 삭제(GET 쪽 유지) | **0셀 — 184 passed/1322 subtests 전건 초록** | **2 실패** `test_execute_for_a_missing_user_is_404` + `test_execute_for_an_unclaimed_account_is_409_and_unaudited` — `2 failed, 14 passed`. C1 폐쇄 셀 둘이 정확히 실행 측 재확인을 잠근다 |
| **M6** (under) | `auth/admin_audit.py` InMemory `list_destructive_events` 필터에 `"member_quota_policy"` 추가 | **0셀 — 171 passed 전건 초록** | **1 실패** `test_the_audit_surface_excludes_member_quota_events` — `1 failed, 15 passed`. C2 폐쇄 |
| **M5b** (over) | `auth/admin_audit.py:130` `target_user_id=requested.target_user_id,` → `target_user_id=requested.target_project_id,` | **계정 셀 1만 재실패 — 프로젝트 purge 축 오염은 무셀** | **2 실패** `test_execute_is_audited_in_two_stages_with_the_target_user`(계정 셀, 발행 검증과 동일) **+ `test_auth_api.py::AdminProjectPurgeTest::test_success_records_requested_and_succeeded_tombstones`**(C3 폐쇄로 더해진 `target_user_id is None` 단정) — `2 failed, 167 passed, 1222 subtests`. **과교정 방향이 살아났다.** 폐쇄 보고의 *"1셀 기명 재실패"* 는 새로 추가된 프로젝트 축 셀만 세어 적은 것이고, 계정 셀도 여전히 물음(발행 검증과 동일) — 차이가 아니라 보강 |
| **M1** (under·원본 재확인) | `deletion/account_reconcile.py:89` `if not projects and has_tombstone:` → `if not projects:` | 2셀 재실패 | **2 실패** `test_execute_keeps_the_row_without_a_tombstone` + `ReconcilerTest::test_a_missing_tombstone_also_holds_the_user_row_back` — 원본 잠금 생존 확인 |
| **M4** (under·원본 재확인) | `admin_audit.py` `record_account_reconcile_requested` 본문에서 `self._repo.insert(event)` 삭제 | 2셀 재실패 | **2 실패** `test_a_failed_execution_records_the_failed_outcome` + `test_execute_is_audited_in_two_stages_with_the_target_user` — 원본 잠금 생존 확인 |

## 폐쇄 ↔ 처방 대조

- **C1**: 처방("POST 셀 둘 — 없는 사용자 404, 파기 미시작 409 + 감사 행 없음 단정") 그대로 — 후자 셀 이름(`…and_unaudited`)이 순서(대상 검증 → 감사)까지 잠근다. M3 으로 둘 다 물린다.
- **C2**: 처방 그대로 — 회원 정책 행을 심은 뒤 `GET /admin/audit-events` 에 `account_reconcile` 은 보이고 `member_quota_policy` 는 안 보이는지. M6(InMemory 필터)으로 물린다.
- **C3**: 처방(기존 프로젝트 purge 감사 셀에 저장소 직접 `target_user_id is None` 단정) 그대로 — M5b 로 프로젝트 축이 물린다(과교정 방향 폐쇄의 실증).
- **하드닝 H3(범위 밖 인용부호 변경)도 원복 상태** — `AdminUserDetail.tsx` 에 곡은 인용부호 2건 존재(실측). 나머지 하드닝(H1·H2·H4~H6)은 발행 기록대로 비차단.

## 기준선(변이 전 초록)

- `test_admin_account_reconcile.py` **16 passed**(폐쇄로 13→16) · `test_auth_api.py` **153 passed / 1222 subtests EXIT=0**(발행 검증과 동일 수치) · `test_account_withdrawal_worker.py` 포함 묶음 초록 · 프런트 `AdminUserDetail + AdminConsole` **18 passed (2 files) EXIT=0**.

## Verdict

**합격** — 조건 C1·C2·C3 모두 폐쇄됐고 변이 재적용 다섯 종이 기명 셀로 문다(셋은 폐쇄로 *무셀→재실패*로 바뀐 자리, 둘은 원본 잠금의 생존 확인). 선행 기록 발행 시점 판정 원문:

> **조건부 합격** — C1(POST 측 404·409 재확인 셀)·C2(member_quota 화면 배제 셀)·C3(프로젝트 purge 감사 축 무변 셀)을 추가로 닫을 것.

## Outstanding items

- 스크립트 dry-run 스모크는 여전히 이 환경에서 Mongo 접속 불가로 미실행(발행 기록 그대로) — 배포 환경에서 한 번 돌려볼 것.
- H4(감사 payload 의 `target_user_id` 부재)·H5(스크립트 main 무셀) 등 하드닝은 오너 값 인정 대기.

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system
git status --short                          # 변이 대상 파일은 diff 0이어야 한다
python3 -m pytest tests/test_admin_account_reconcile.py tests/test_account_withdrawal_worker.py -q
python3 -m pytest tests/test_auth_api.py -q   # 153 passed / 1222 subtests
# M3 : admin.py POST reconcile_account 에서 _stalled_user_or_error(user_id) 삭제
#      → test_admin_account_reconcile.py 2 failed(404/409 재확인 셀 둘)
# M6 : admin_audit.py list_destructive_events 필터에 "member_quota_policy" 추가 → 1 failed
# M5b: admin_audit.py target_user_id=requested.target_project_id 로
#      → 계정 셀 + AdminProjectPurgeTest 무변 셀 = 2 failed
# M1 : account_reconcile.py 조건 → if not projects: → 2 failed
# M4 : record_account_reconcile_requested 의 insert 삭제 → 2 failed
# 매 변이: git checkout -- <절대경로> 원복 + 백업과 cmp 바이트 대조
```
