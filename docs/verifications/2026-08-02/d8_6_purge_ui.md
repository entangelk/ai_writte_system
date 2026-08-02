# D8-6 — archive-only purge + 삭제 감사(tombstone) + purge UI

## Subject metadata

- **날짜**: 2026-08-02
- **요청자**: 오너("다음작업 검증해줘. D8-6 구현")
- **검증자**: Claude Code(구현자와 다른 세션, 적대적 검증)
- **대상**: 커밋 `6c9b796`(구현) + `1843b78`(정본·기록, SoT v1.7.82)
- **정규 스펙**: `plans/auth-d8-6-purge-ui-decisions.md`(D1~D5=A), `system-contract-sot.md` v1.7.82
- **검증 소스**: 커밋 `1843b78`(HEAD). 코드·테스트·정본에서 재도출.
- **선행 검증 맥락**: `2026-08-02/purge_reconciler.md`(재시도 불가 한계 원처), `2026-08-02/d8_5d_admin_console.md`(관리 화면 베이스)

## Scope

불가역 project purge를 관리자 화면에 노출하며 생기는 5개 결정(D1~D5)의 시행. 보안 하중이 큰 두 축을 중심으로.

1. **D1 archive-only** — 활성 project purge → 409. backend+UI 양쪽 강제.
2. **D2 type-to-confirm** — project 이름 정확히 입력.
3. **D3 사유 + tombstone 감사** — `admin_audit_events`, `target_project_id`(project_id 아님).
4. **D4 현행 순서 + 재시도 금지** — 503 시 "상태 불확정", 재시도 버튼 없음. D4-D(journal)는 후속.
5. **★ D5 requested fail-closed / 결과 best-effort** — 보안 하중 핵심.

## Methodology

- 백엔드 `pytest -q`·프론트 `npm run test`/`npm run build`.
- 뮤테이션 7축은 독립 에이전트가 `Edit` → pytest/vitest → 원복 → `git status` clean으로 재현(커밋 0건).
- **target_project_id 분리는 실제 Mongo(127.0.0.1:27020) 프로브로 실증** — 감사 행 + 진성 고아를 넣고 reconciler를 돌려 감사가 살아남는지 확인.
- 코드 경로 직접 추적.

## Findings

### 회귀·빌드 — 정확히 재현
- 백엔드: **1911 passed / 4 skipped / 1625 subtests / 126.92s**, exit 0.
- 프론트: **236 passed / 17 files**; 빌드 exit 0(`AdminConsole` chunk 8.39 kB, purge UI 추가).

### main.py purge endpoint — 브리프 D1~D5 정확히 반영
- `get_project` → `if not project.archived: raise 409`(D1). 404/409 선언.
- `record_purge_requested`가 purge 실행 **전**, try/except 없이 → fail-closed(D5).
- purge 실행(core_sot→derived→access_grants→outbox) 뒤:
  - 실패 시 `record_purge_outcome(failed)`를 `try/except: pass`로, **실제 exc는 전파**(NotFound→404, storage→503). error_kind 안정 분류(storage_error/not_found/internal_error).
  - 성공 시 `record_purge_outcome(succeeded)`도 `try/except: pass` — "이미 끝난 파기를 503으로 거짓 재시도 안 시킨다"(D5 best-effort).
- D4=A 한계 주석 + reconciler 수습 + D4-D 후속 명시.

### 감사 도메인·저장소 — target_project_id 분리 + TTL 없음
- `AdminAuditEvent`: `target_project_id`(project_id 아님). `record_purge_requested`가 blank reason → ValueError(도메인 경계). `operation_id`로 requested/outcome 짝.
- `admin_audit_mongo.py`: `target_project_id`로 기록, TTL 없음("D5 exception that survives destruction"), `_aware` naive→UTC.

### 뮤테이션 7축 — 전부 작동 (에이전트 독립 재현)
| 축 | 변이 | 실패 셀 |
|---|---|---|
| D1 archive 409 | 활성 통과 허용 | `test_active_project_is_409_before_audit_or_purge`(204 != 409) |
| ★ D5 requested fail-closed | 선기록 무시 | `test_requested_audit_failure_prevents_the_purge`(204 != 503) |
| ★ D5 outcome best-effort | 성공 감사 실패→503 | `test_outcome_audit_failure_does_not_turn_a_completed_purge_into_503` |
| D3 사유 필수 | blank 허용 | `test_reason_is_required_and_non_blank` |
| D2 이름 입력(프론트) | 이름 비교 완화 | `AdminConsole.test.tsx:207` |
| D4 503 재시도 금지(프론트) | 503에 재시도 버튼 | `AdminConsole.test.tsx:250` |
| D3 target_project_id 분리 | project_id로 기록 | `test_tombstone_wire_uses_target_project_id_not_project_id` |

### ★ target_project_id 분리 — 실제 Mongo 프로브로 실증
에이전트가 127.0.0.1:27020에 감사 tombstone 2건(`target_project_id: "purged-ghost"`)+진성 고아 1건(`llm_call_audits`의
`project_id: "purged-ghost"`)을 넣고 `_collections_scoped_by_project`를 실행 → `discovered_collections = ['llm_call_audits']`,
**`admin_audit_events`는 발견되지 않음**, 고아 처리 후 감사 카운트 2 유지. reconciler가 `target_project_id` 필드 이름 때문에
감사 컬렉션을 구조적으로 건너뛴다 — 브리프의 "이것이 핵심" 단언이 실제로 작동.

## Issues / Risks

### Blocking (계약 의무 위반)
없음.

### Hardening recommendations (비차단)
특별한 것 없음. D3 사유 필수 셀이 HTTP 계층 검사 비활성화 후 서비스 계층 재검사(`raise ValueError`)로 포착되는 것은
main.py 주석이 명시하는 **의도적 심층 방어**(non-HTTP callers cannot skip it)이며 강점이다.

## Verdict

**합격.** D1~D5(A)가 코드·테스트·정본에서 일관되고, 7개 축 가드가 전부 작동하며(작업 AI "5축"은 과소평가),
보안 하중 두 축(fail-closed·best-effort)이 전용 셀로 잠겨 있다. target_project_id 분리는 실제 Mongo 프로브로
실증됐다. 이전 `purge_reconciler` 검증의 교훈(재시도 불가)이 D4=A + 503 재시도 금지 UI로 정확히 처리됐다.

## Outstanding items

- D4-D operation journal/saga — 원격 저장소·다중 worker에서 수동 reconciler가 실제 부담이 될 때 후속(브리프·HANDOFF에 추적 약속).
- 본 검증은 기록만 작성 후 커밋.

## Reproduction

```bash
python3 -m pytest -q                  # 1911 passed / 4 skipped / 1625 subtests
cd frontend && npm run test           # 236 passed / 17 files
cd frontend && npm run build          # exit 0

# 뮤테이션(Edit → pytest/vitest → 원복, 커밋 금지)
# 1. main.py purge 의 if not project.archived: 409 제거 → test_active_project_is_409... 실패
# 2. record_purge_requested 를 purge 뒤로 / try/except 삼킴 → test_requested_audit_failure_prevents... 실패 (fail-closed)
# 3. 성공 감사 try/except: pass → raise → test_outcome_audit_failure... 실패 (best-effort)
# 4. blank reason 허용 → test_reason_is_required_and_non_blank 실패
# 5. AdminConsole.tsx 이름 비교 완화 → AdminConsole.test.tsx:207 실패
# 6. 503에 재시도 버튼 추가 → AdminConsole.test.tsx:250 실패
# 7. target_project_id → project_id 로 기록 → test_tombstone_wire_uses_target... 실패
#    + 실측: 실제 Mongo 에 target_project_id 감사 + project_id 고아 넣고 reconciler → admin_audit_events 건너뜀 확인
```
