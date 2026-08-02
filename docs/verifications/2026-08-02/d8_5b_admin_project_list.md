# D8-5b — 전 프로젝트 메타데이터 목록 (GET /admin/projects)

## Subject metadata

- **날짜**: 2026-08-02
- **요청자**: 오너("다음작업 검증해줘. D8-5b 완료")
- **검증자**: Claude Code(구현자와 다른 세션, 적대적 검증)
- **대상**: 커밋 `ae14491`(구현) + `5fe5295`(정본·기록)
- **정규 스펙**: `plans/auth-d8-5-admin-decisions.md` §4(5-b), `system-contract-sot.md` v1.7.79
- **검증 소스**: 커밋 `5fe5295`(HEAD). 검증자는 코드·테스트·정본을 코드에서 재도출.

## Scope

관리자가 "무엇이 존재하고 누구 것인가"에 답하는 목록 endpoint. 경계가 이 슬라이스의 전부다.

1. **필드 집합(메타데이터만)** — id·name·archived·owner_id. 내용은 D8-5e 승격 필요. 목록이 내용을
   흘리면 승격을 우회하는 뒷문이 된다.
2. **★ 뮤테이션 겨냥 — 모델 vs 핸들러**: 작업 AI가 "핸들러 dict에 필드 추가는 response_model이
   걸러내 안 잡히고, 모델에 추가해야 잡힌다"고 보고. 이것이 사실인지 두 방향으로 증명.
3. **ADMIN tier + operation 카운트** — `/admin/projects` GET이 admin tier, operation 73→74.
4. **부수 판단** — owner_id raw · archive 포함 · 목록 조회 감사 미기록 · `_project_payload` owner_id 미노출(D8-2c 유예).

## Methodology

- 회귀·tsc 백그라운드 재현(`python3 -m pytest -q`, `npx tsc --noEmit`).
- 뮤테이션 4종(모델 필드 / 핸들러 dict / 소유자 좁힘 / 감사 기록)은 독립 에이전트가 `Edit` → `pytest` →
  원복 → `git status` clean으로 재현(커밋 0건).
- tier 분류·필드 집합·주석 정정은 코드 직접 실측. 모든 단언에 `file:line` 근거.

## Findings

### 회귀·tsc — 정확히 재현
- `python3 -m pytest -q`: **1887 passed / 4 skipped / 1602 subtests / 105.94s**, exit 0. 구현자 보고와 일치.
  직전 1881 대비 +4셀.
- `npx tsc --noEmit`: exit 0.

### ★ 뮤테이션 겨냥 통찰 — 에이전트 독립 증명 (이 슬라이스의 핵심)
작업 AI가 보고한 "모델 vs 핸들러" 진단을 에이전트가 두 방향으로 직접 실측:

| 뮤테이션 | 결과 | 증거 |
|---|---|---|
| `AdminProjectPayload`에 필드 추가 + 핸들러 dict에도 | **잡힘** | `test_the_listing_carries_no_project_contents` FAILED(`'brief'` 노출) |
| 핸들러 dict에만 필드 추가(모델 그대로) | **안 잡힘** | 4셀 전부 PASS. `response_model=AdminProjectListResponse`가 여분 키를 걸러 응답 불변 |

→ 작업 AI의 진단("셀이 약한 게 아니라 뮤테이션이 관측 가능 변화를 못 만들었다")이 정확함. 필드가
클라이언트에 닿는 유일한 경로가 모델이므로, 회귀가 단정하는 곳도 모델(`set(row) == {"id","name",
"archived","owner_id"}`, test_auth_api.py:1239). 셀 주석(L1233-1236)과 SoT v1.7.79 기술이 사실과
일치. 검증 가이드의 "테스트가 통과한다로는 무엇을 잡는지 모른다"를 작업 AI가 올바르게 적용.

### 나머지 뮤테이션 2종 — 전부 잡힘
- **소유자로 좁힘**(`list_all_projects`에 `current`를 받아 `if p.owner_id == current.id`):
  `test_it_lists_projects_of_every_owner_including_unowned` FAILED + 파급 2건.
- **목록 조회를 감사에 기록**(핸들러에서 `record_use`): `test_listing_a_project_is_not_recorded_as_an_access`
  FAILED. 타깃 셀만 단독 실패.

### tier 분류 + 카운트
- `CombinedBoundaryMatrixTest::test_every_operation_lands_in_exactly_one_named_tier` PASSED.
- `len(tiers) == 74` · `len(by_tier["project"]) == 61` · admin tier = 7(test_auth_api.py:905-909).
- `("/admin/projects", "get")`는 **admin tier**로 정확히 분류 — `require_admin_user` 의존성에서 파생(경로
  모양 아님). 주석(L829-831)과 일치.

### 필드 집합 + 부수 판단 — 전부 정확
- `AdminProjectPayload`: id·name·archived·owner_id(정확히 4필드, main.py:1630).
- `_project_payload`: id·name·archived(**3필드, owner_id 없음**) — D8-2c(공개 표면 owner_id 노출) 유예
  정확히 유지. 공개 payload와 관리자 payload의 차이가 owner_id 한 필드.
- archived 포함(`list_projects()` 전체) + 플래그.
- owner_id raw(username join 안 함 — N+1 방지).
- 목록 조회는 access-log에 기록 안 됨(`test_listing_a_project_is_not_recorded_as_an_access`).

### 함께 정정 — Project 모델 주석
`core_sot/models.py` Project 주석이 "non-null owner_id does NOT restrict access yet — it is only
recorded"라고 단언했는데 D8-3b(v1.7.53)부터 시행 중이라 거짓이었다. 정정: "Enforced since D8-3b —
owner_id=None은 항상 denied(E1=A), never adopted." 정정 방향 정확.

## Issues / Risks

### Blocking (계약 의무 위반)
없음.

### Hardening recommendations (비차단)
특별한 것 없음. 이 슬라이스는 경계가 단순명확하고 셀이 양방향으로 든든하다.

## Verdict

**합격.** 필드 집합(메타데이터만)이 코드·테스트·정본에서 일관되고, 뮤테이션 4종이 전부 예상대로
작동하며, 작업 AI의 "모델 vs 핸들러" 겨냥 통찰이 에이전트 독립 실측으로 증명됐다. tier 분류·카운트·
주석 정정·D8-2c 유예 유지 전부 정확.

## Outstanding items

- 남은 D8-5: 5-d(관리자 화면 — 프론트 슬라이스, 이제 목록·사용자·KPI·승격·감사가 다 있어 그릴 것이
  갖춰짐) · C-6(최초 로그인 비밀번호 변경 강제 + 비밀번호 정책, 오너 확정·별개 축).
- 본 검증은 커밋하지 않은 상태에서 기록만 작성 후 커밋(검증자는 결함을 고치지 않고 보고).

## Reproduction

```bash
# 회귀(test-mongo 127.0.0.1:27020 선행)
python3 -m pytest -q            # 1887 passed / 4 skipped / 1602 subtests
cd frontend && npx tsc --noEmit # exit 0

# 뮤테이션(각각 Edit → pytest tests/test_auth_api.py::AdminProjectListTest -q → 원복, 커밋 금지)
# 1. AdminProjectPayload 에 필드 추가(+ 핸들러 dict) → test_the_listing_carries_no_project_contents 실패
# 2. 핸들러 dict 에만 필드 추가(모델 그대로) → 4셀 전부 통과(response_model이 걸러냄) ★ 통찰 증명
# 3. 소유자로 좁힘(current 로 필터) → test_it_lists_projects_of_every_owner_including_unowned 실패
# 4. 목록 조회를 감사에 기록 → test_listing_a_project_is_not_recorded_as_an_access 실패
```
